# Pagination, long-running operation và quản lý tài nguyên client

Một ứng dụng Java trên **Azure Container Apps** cần liệt kê hơn hai triệu blob trong Azure Storage, cập nhật tài nguyên Azure qua management SDK và thực hiện các công việc provisioning mất vài phút. Bản thử nghiệm chạy được với vài chục đối tượng, nhưng khi đưa lên production lại xuất hiện ba vấn đề: **tải toàn bộ kết quả vào RAM**, **HTTP request chờ quá lâu để đợi tác vụ cloud hoàn thành**, và **mỗi request tạo một Azure SDK client mới**, làm tăng connections, chi phí xác thực và độ trễ. Đây là ba nhóm vấn đề khác nhau, nhưng thường cùng xuất hiện trong ứng dụng gọi Azure SDK for Java.

Bài học này giải thích cách sử dụng **pagination** để đọc tập kết quả lớn theo trang, xử lý **long-running operation (LRO)** qua cơ chế polling thay vì nhầm phản hồi khởi tạo với kết quả hoàn tất, và **quản lý vòng đời clients/HTTP transport/credentials** để tránh cạn tài nguyên. Mục tiêu là thiết kế một chương trình Java vừa hoạt động đúng vừa phù hợp với throughput, độ trễ, bảo mật và chi phí trên Azure.

Nội dung thuộc chương **Azure SDK cho Java**, module **CLOUD_PROVIDERS_AZURE**: học từ Azure subscription, resource group, Microsoft Entra ID đến mạng ảo, compute, storage và dữ liệu; triển khai, giám sát, bảo vệ và kiểm soát chi phí hệ thống. Ví dụ sử dụng Azure SDK for Java hiện đại (các packages `com.azure.*`), Azure Blob Storage và các mẫu polling dùng trong SDK dịch vụ/management. Cần lưu ý **không phải tất cả Azure service clients có cùng API paging/LRO hoặc đều cần đóng tài nguyên giống nhau**.

> **Phiên bản và tính tương thích:** Azure SDK for Java, Maven BOM, tên các overload của `PagedIterable`/`PagedFlux`, status classes, HTTP provider và long-running operation poller có thể thay đổi giữa thư viện và phiên bản. Mã Blob Storage là ví dụ thực hành cho một SDK cụ thể; mẫu LRO dùng một **phương thức giả định** `beginOperation(...)` để minh họa logic chung, không phải lệnh có sẵn của mọi Azure service. Trước khi áp dụng production, kiểm tra API reference và khả năng của phiên bản thư viện đã khóa trong dự án. Các thao tác liệt kê hoặc thay đổi tài nguyên có thể phát sinh phí.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **collection lớn**, **page**, **page size**, **continuation token**, **offset** và **cursor**.
2. Sử dụng **`PagedIterable<T>`** của Azure SDK Java để đọc đồng bộ theo item hoặc theo page.
3. Sử dụng **`PagedFlux<T>`** để xử lý bất đồng bộ với Reactor và giới hạn concurrency/backpressure.
4. Thiết kế resume/checkpoint an toàn khi liệt kê hàng triệu đối tượng, tránh bỏ sót hoặc xử lý trùng khi retry.
5. Nhận diện các operations trả trạng thái chưa hoàn tất, phân biệt HTTP **202 Accepted** với thành công cuối cùng.
6. Sử dụng tư duy **`SyncPoller<P,T>`** và **`PollerFlux<P,T>`**, hiểu trạng thái, kết quả cuối, timeout và giới hạn cancellation.
7. Thiết kế idempotency và operation tracking cho API Java bắt đầu một Azure LRO.
8. Biết khi nào Azure clients được tái sử dụng và khi nào cần giải phóng **tài nguyên mà ứng dụng thực sự sở hữu**.
9. Cấu hình identity/RBAC, HTTP transport, retry/timeouts và observability an toàn.
10. Chọn giải pháp phù hợp cho workload web, batch, multi-tenant hoặc tác vụ quản trị Azure.

## 2. Ba vấn đề và ba cơ chế giải quyết

| Bài toán | Triệu chứng | Cơ chế chính |
|---|---|---|
| Kết quả danh sách quá lớn | RAM tăng, API chậm, timeout khi list | **Pagination + streaming/checkpoints** |
| Thao tác Azure xử lý lâu | HTTP 202, trạng thái vẫn InProgress, request đợi hàng phút | **Long-running operation + polling/status tracking** |
| Client được tạo liên tục | Connection churn, token fetching, thread/pool pressure | **Client reuse + lifecycle ownership** |

Chúng liên quan nhưng không thay thế nhau. Một API có thể dùng một client singleton để duyệt trang, đồng thời khởi chạy LRO cho từng mục đã duyệt. **Pagination không bảo đảm LRO hoàn tất**, và **polling không tự chữa connection leak**.

~~~mermaid
flowchart LR
  APP["Java application"] --> CLIENT["Reusable Azure SDK client"]
  CLIENT --> LIST["Paged listing"]
  LIST --> PAGE["Items in bounded pages"]
  PAGE --> WORK["Idempotent task workers"]
  WORK --> LRO["Start LRO"]
  LRO --> POLL["Poll status / final result"]
  POLL --> STORE["Checkpoint + observability"]
  CLIENT -.-> RES["Shared HTTP pipeline / credential / connection pool"]
~~~

## 3. Kiến trúc Azure SDK Java: client, pipeline, transport

Những khái niệm thường gặp:

- **Service client:** `BlobServiceClient`, `BlobContainerClient`, `BlobContainerAsyncClient` hoặc các clients dịch vụ khác; cung cấp phương thức nghiệp vụ.
- **Builder:** `BlobServiceClientBuilder` cấu hình endpoint, credential, client options và tạo client.
- **HTTP pipeline:** tập hợp policy như authentication, retry, diagnostics và transport.
- **HTTP transport:** implementation thực thi HTTP, kết nối/TLS/connection pooling.
- **TokenCredential:** ví dụ `DefaultAzureCredential`; lấy token dựa trên Microsoft Entra ID.
- **PagedIterable/PagedFlux:** lớp abstraction phục vụ liệt kê có nhiều trang.
- **SyncPoller/PollerFlux:** abstraction cho long-running operation ở những clients có hỗ trợ.

Azure SDK clients thường được thiết kế **thread-safe và tái sử dụng**. Một client có thể dùng cho nhiều operations và threads; không cần tạo một client mới sau mỗi lần gọi `listBlobs()` hoặc sau mỗi HTTP request tới ứng dụng.

Tuy nhiên, phải xác nhận **tài nguyên nào do client và ứng dụng sở hữu**. Không phải mọi Azure SDK client đều implements `AutoCloseable` hoặc có `close()`. Tránh thêm `client.close()` theo thói quen nếu API loại client đang dùng không có.

## 4. Pagination là gì?

Một cloud service có thể lưu hàng triệu objects. Thay vì trả toàn bộ trên một HTTP response, service trả một **page** và có thể kèm **continuation token** để truy vấn trang kế tiếp.

~~~text
Request: list(prefix="invoices/", maxPageSize=100)
Response page 1:
  100 items
  continuation = "opaque-token-1"

Request: list(prefix="invoices/", token="opaque-token-1")
Response page 2:
  100 items
  continuation = "opaque-token-2"

...
Response page N:
  37 items
  continuation = null (completed)
~~~

**Page size** là kích thước mong muốn, thường là **hint/giới hạn do service quyết định** chứ không phải bảo đảm mọi page có đúng N items. Một page có thể rỗng nhưng vẫn mang continuation token trong một số dịch vụ, nên không kết luận kết thúc chỉ dựa vào `items.size() == 0`.

### Offset và continuation token khác nhau

- **Offset pagination:** yêu cầu “bỏ qua 10.000 hàng, lấy 100 hàng tiếp theo”. Có thể tốn chi phí khi offset lớn và dễ sai khi tập dữ liệu thay đổi.
- **Continuation token/cursor:** một giá trị opaque do service cấp để tiếp tục từ vị trí hợp lệ theo semantics của chính service.
- **Snapshot pagination:** tập kết quả được cố định trong một thời điểm, **không mặc định** có trên tất cả Azure listing APIs.

Trong Azure SDK, không tự giả định token là page number, last blob name hoặc ID có thể tự cộng một.

## 5. Continuation token phải được xem là opaque

Một continuation token:

1. Được service sinh ra, không có format mà ứng dụng được phép dựa vào.
2. Có thể mã hóa state/filter/server-side pagination.
3. Có thể hết hạn, bị từ chối hoặc không hợp lệ sau thay đổi schema/API/version tùy service.
4. Có thể bị ràng buộc với cùng tài nguyên, query, prefix, region và request options.
5. Cần được bảo vệ như **application state có thể nhạy cảm**, không log ra nơi công khai.
6. Không được dùng thay cho authentication/authorization.
7. Khi resume phải dùng **cùng listing scope và request options** nếu service yêu cầu.

### Ví dụ checkpoint

~~~json
{
  "jobId": "blob-audit-20261120",
  "account": "storage-lab",
  "container": "invoices",
  "prefix": "2026/11/",
  "continuationToken": "<OPAQUE_TOKEN>",
  "processedItems": 7400,
  "schemaVersion": 1,
  "status": "RUNNING"
}
~~~

Token thực không được đưa vào log/telemetry công khai. Nếu checkpoint lưu ở database, quyền đọc/sửa phải giới hạn; cập nhật atomically theo **job ID/generation** để tránh hai workers ghi đè state của nhau.

## 6. Maven: quản lý dependencies bằng Azure SDK BOM

Với Maven, nên dùng BOM để quản lý các phiên bản Azure SDK có tương thích theo khuyến nghị cho dự án:

~~~xml
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

Đây là **mảnh cấu hình POM**. Phải khai báo property `azure.sdk.bom.version` trong project hoặc thay bằng phiên bản BOM được tổ chức duyệt; không dùng “latest” không kiểm soát. Nếu có BOM của Spring Boot hoặc framework khác, kiểm tra dependency resolution và conflict.

### Các packages cần nhận diện

| Package/Class | Vai trò |
|---|---|
| `com.azure.storage.blob.*` | Clients Azure Blob Storage |
| `com.azure.storage.blob.models.*` | `BlobItem`, `ListBlobsOptions` |
| `com.azure.core.http.rest.PagedIterable` | Phân trang đồng bộ |
| `com.azure.core.http.rest.PagedFlux` | Phân trang bất đồng bộ |
| `com.azure.core.http.rest.PagedResponse` | Page, values, continuation token |
| `com.azure.core.util.polling.SyncPoller` | Polling LRO đồng bộ |
| `com.azure.core.util.polling.PollerFlux` | Polling LRO reactive |
| `com.azure.identity.DefaultAzureCredentialBuilder` | TokenCredential cho Azure |

Tên overload cụ thể phụ thuộc SDK package/version. Kiểm tra import/API reference trước khi biên dịch các snippet.

## 7. Tạo và tái sử dụng Azure Blob client

Ví dụ Java 17 dùng Microsoft Entra authentication:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import com.azure.storage.blob.BlobContainerClient;

public final class BlobClients {
    private final TokenCredential credential;
    private final BlobServiceClient serviceClient;

    public BlobClients(String endpoint) {
        this.credential = new DefaultAzureCredentialBuilder().build();
        this.serviceClient = new BlobServiceClientBuilder()
            .endpoint(endpoint)
            .credential(credential)
            .buildClient();
    }

    public BlobContainerClient container(String name) {
        return serviceClient.getBlobContainerClient(name);
    }
}
~~~

Ứng dụng tạo `BlobClients` **một lần lúc khởi động** (hoặc dùng DI singleton) và dùng lại. Endpoint ví dụ là `https://<account>.blob.core.windows.net`, không chứa account key. Không tự tạo `DefaultAzureCredential` hoặc `BlobServiceClient` trong mỗi lần lặp qua blob.

### Quyền để list

Danh tính cần data-plane permission tương ứng, ví dụ **Storage Blob Data Reader** tại scope phù hợp, đồng thời storage account firewall/private network phải cho phép đường truy cập. Resource Group Contributor **không tự động** cấp quyền đọc blob.

`DefaultAzureCredential` trong local có thể dùng developer login; trong Azure Container Apps/AKS/VM cần managed identity/workload identity và cách cấu hình phù hợp. Không log access tokens hoặc connection strings.

## 8. PagedIterable: duyệt item đồng bộ

Azure Blob Storage có thể trả `PagedIterable<BlobItem>` khi liệt kê blobs.

~~~java
import com.azure.core.http.rest.PagedIterable;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;

import java.time.Duration;

public final class BlobListing {
    public static long count(BlobContainerClient container) {
        ListBlobsOptions options = new ListBlobsOptions()
            .setPrefix("invoices/");

        PagedIterable<BlobItem> blobs =
            container.listBlobs(options, Duration.ofSeconds(30));

        long count = 0;
        for (BlobItem blob : blobs) {
            // Mỗi bước iteration có thể kích hoạt network khi cần page mới.
            if (blob.getName() != null) {
                count++;
            }
        }
        return count;
    }
}
~~~

### Không phải toàn bộ dữ liệu đã được tải ngay

`PagedIterable` cung cấp trải nghiệm giống Java Iterable nhưng các pages thường được lấy **lazy/on demand**. Khi lặp đến cuối page hiện tại, SDK gửi HTTP request tiếp theo. Vì vậy:

- Tạo object `PagedIterable` chưa chắc đã fetch tất cả.
- Lặp `for` xuyên hàng triệu items có thể chạy lâu và phát sinh nhiều API calls.
- Iterator có thể throw exception giữa chừng khi HTTP request trang sau thất bại.
- Một `timeout` truyền vào list API không có nghĩa **toàn bộ vòng lặp** chắc chắn phải hoàn thành trong 30 giây; semantics timeout cần xem overload cụ thể.
- Đừng chạy toàn bộ listing trong một HTTP request có timeout ngắn nếu kết quả quá lớn.

### Nguy hiểm của ép danh sách

~~~java
// Anti-pattern minh họa:
List<BlobItem> all = new ArrayList<>();
for (BlobItem item : container.listBlobs()) {
    all.add(item); // Có thể giữ hàng triệu objects trong RAM.
}
~~~

Với streaming, nên **xử lý từng item/page và giải phóng tham chiếu**, chỉ giữ state tối thiểu cần thiết. Nếu thực sự cần aggregate tất cả, cân nhắc external storage/database thay vì JVM heap.

## 9. Duyệt theo page và giới hạn batch

`PagedIterable` cho phép xem các pages. Một cách thực hành:

~~~java
import com.azure.core.http.rest.PagedIterable;
import com.azure.core.http.rest.PagedResponse;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;

import java.time.Duration;

public final class PageProcessing {
    public static void scan(BlobContainerClient container) {
        PagedIterable<BlobItem> listing = container.listBlobs(
            new ListBlobsOptions().setPrefix("invoices/"),
            Duration.ofSeconds(30)
        );

        for (PagedResponse<BlobItem> page : listing.iterableByPage(200)) {
            for (BlobItem item : page.getValue()) {
                processOne(item);
            }
            String nextToken = page.getContinuationToken();
            System.out.println("Page complete; hasNext="
                + (nextToken != null));
        }
    }

    private static void processOne(BlobItem item) {
        // Đọc metadata cần thiết hoặc gửi một job có idempotency key.
        System.out.println(item.getName());
    }
}
~~~

`iterableByPage(200)` đặt **preferred page size**; service có thể trả ít hơn. Khi lặp pages, không assume `page.getValue()` luôn có 200 items hoặc page number bắt đầu từ 1.

### Vì sao xử lý theo page?

- Có thể checkpoint sau khi hoàn thành cả page.
- Dễ tạo batch metrics, kiểm soát memory và downstream concurrency.
- Giảm overhead so với lưu từng item vào application database.
- Dễ resume sau khi worker crash.
- Có thể áp dụng per-page transactional semantics nếu downstream hỗ trợ.

**Không ghi checkpoint quá sớm.** Nếu mới xử lý 80/200 items đã lưu token trang kế tiếp, khi crash bạn có thể **bỏ qua 120 items** chưa xử lý.

## 10. Resume listing từ continuation token

Khi job dài chạy hàng giờ, một Azure VM có thể reboot hoặc Container Apps replica bị thay. Không nên bắt đầu lại toàn bộ nếu service hỗ trợ resume.

Mẫu:

~~~java
import com.azure.core.http.rest.PagedIterable;
import com.azure.core.http.rest.PagedResponse;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;

import java.time.Duration;

public final class ResumeBlobScan {
    public static void run(
            BlobContainerClient container,
            String savedNextPageToken) {

        PagedIterable<BlobItem> listing = container.listBlobs(
            new ListBlobsOptions().setPrefix("2026/11/"),
            Duration.ofSeconds(30)
        );

        for (PagedResponse<BlobItem> page :
                listing.iterableByPage(savedNextPageToken, 200)) {

            for (BlobItem item : page.getValue()) {
                processIdempotently(item);
            }

            // Thực tế: commit checkpoint atomically sau khi xử lý page.
            persistCheckpoint(page.getContinuationToken());
        }
    }

    private static void processIdempotently(BlobItem item) {
        // Ví dụ: upsert (account, container, name, etag)
        // vào một bảng có unique key/idempotency key.
    }

    private static void persistCheckpoint(String token) {
        // Lưu vào durable store, kèm scope/prefix/job generation.
        // token == null nghĩa đã duyệt hết tại thời điểm service báo.
    }
}
~~~

Đây là **mẫu ghép thêm**: `persistCheckpoint` và `processIdempotently` chưa có triển khai storage. API `iterableByPage(token, size)` phải được kiểm tra trên phiên bản `azure-core` đang dùng.

### Checkpoint đúng

- Lưu token đại diện **trang kế tiếp**, không lưu token trước khi page hiện tại được xử lý.
- Ghi checkpoint **sau** khi downstream commit thành công.
- Nếu xử lý page song song, đợi **tất cả** items/page thành công rồi commit.
- Nếu bất kỳ item thất bại, có chiến lược retry hoặc quarantine trước khi đánh dấu cả page hoàn tất.
- Dùng unique key/upsert để **retry không tạo duplicate side effects**.
- Lưu prefix/filter và account/container cùng token.
- Khi token invalid/expired, cần runbook restart từ checkpoint khác hoặc scan lại có dedup.

### Exactly-once có được bảo đảm không?

Không. Nếu downstream commit thành công nhưng worker crash **trước khi** ghi checkpoint, page có thể được replay. Nếu checkpoint commit trước downstream, có thể mất items. Không có atomic transaction chung tự động giữa Azure Blob listing và database downstream, nên thường áp dụng **at-least-once + idempotency**.

## 11. Listing khi dữ liệu thay đổi

Trong lúc listing, các blobs có thể được tạo/xóa/đổi metadata. Nhiều listing APIs **không cam kết snapshot nhất quán** xuyên toàn bộ pages. Hậu quả có thể là:

- Object mới chưa chắc xuất hiện trong run hiện tại.
- Object bị xóa có thể không còn tại thời điểm xử lý.
- Metadata/ETag thay đổi giữa lúc list và đọc.
- Re-run có thể trả tập kết quả khác dù prefix giống nhau.

### Các giải pháp theo nghiệp vụ

1. **Audit inventory gần đúng:** chấp nhận eventual reconciliation, chạy định kỳ.
2. **Snapshot/immutable input:** dùng manifest hoặc versioned dataset khi cần tái lập.
3. **Change feed/events:** phát hiện thay đổi liên tục nếu dịch vụ/kiến trúc hỗ trợ.
4. **ETag/version-aware processing:** xác định đối tượng được xử lý là phiên bản nào.
5. **Watermark + dedup:** kết hợp với scan nếu nguồn có mốc thay đổi đáng tin.
6. **Stable partitioning:** chia work theo container/prefix/date, hạn chế một run vô hạn.

`ContinuationToken` chỉ giúp **tiếp tục phân trang theo semantics service**, không tự biến listing thành transaction snapshot.

## 12. PagedFlux: phân trang bất đồng bộ

Azure SDK cho Java thường cung cấp **sync** và **async** clients. Async listing có thể trả `PagedFlux<BlobItem>`, tích hợp **Project Reactor**.

~~~java
import com.azure.core.http.rest.PagedFlux;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;

import reactor.core.publisher.Mono;

public final class AsyncBlobListing {
    public static Mono<Long> count(
            BlobContainerAsyncClient container) {

        PagedFlux<BlobItem> blobs = container.listBlobs(
            new ListBlobsOptions().setPrefix("invoices/")
        );

        return blobs
            .filter(item -> item.getName() != null)
            .count();
    }
}
~~~

`count()` trả `Mono<Long>`, chỉ được thực thi khi **có subscription**. Với hàng triệu items, pipeline không nhất thiết giữ toàn bộ items cùng lúc, nhưng **vẫn phải duyệt toàn bộ pages** và giữ request/response resources theo behavior của Reactor/SDK.

### Không dùng `collectList()` vô hạn

~~~java
// Anti-pattern: collectList() gom tất cả item vào một list trong RAM.
// Mono<List<BlobItem>> all = container.listBlobs().collectList();
~~~

Thay bằng streaming `doOnNext`/`concatMap`/`flatMap` với concurrency giới hạn, hoặc đi theo page và checkpoint.

## 13. Reactive page processing, concurrency và backpressure

Đọc theo pages cho phép xử lý bất đồng bộ nhưng tránh “bắn” quá nhiều downstream requests cùng lúc.

~~~java
import com.azure.core.http.rest.PagedFlux;
import com.azure.core.http.rest.PagedResponse;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class AsyncPageWorkflow {

    // Các methods processAsync/checkpointAsync cần được triển khai.
    public static Mono<Void> scan(BlobContainerAsyncClient container) {
        PagedFlux<BlobItem> pages = container.listBlobs(
            new ListBlobsOptions().setPrefix("invoices/")
        );

        return pages.byPage(200)
            .concatMap(page ->
                Flux.fromIterable(page.getValue())
                    .flatMap(AsyncPageWorkflow::processAsync, 8)
                    .then(checkpointAsync(page.getContinuationToken()))
            )
            .then();
    }

    private static Mono<Void> processAsync(BlobItem item) {
        // Production: async upsert có unique idempotency key.
        return Mono.empty();
    }

    private static Mono<Void> checkpointAsync(String nextToken) {
        // Production: async durable write, token null => completed.
        return Mono.empty();
    }
}
~~~

**Phân tích:**

- `byPage(200)` xử lý page responses, không đòi thu toàn bộ items vào một list lớn của cả container.
- `concatMap` giữ thứ tự xử lý **giữa các pages**, giúp checkpoint từng page.
- `flatMap(..., 8)` cho tối đa khoảng 8 item operations đồng thời **trong từng page** theo Reactor semantics.
- `then(checkpointAsync(...))` chỉ chạy sau khi các item publishers thành công; nếu lỗi không được xử lý, checkpoint không nên tiến.
- `processAsync`/`checkpointAsync` **là placeholders có chủ ý**, chưa cung cấp DB persistence.
- `Mono.empty()` trong snippet mô phỏng “thành công” nên cần thay bằng implementation thật trước khi triển khai.

### Backpressure là gì?

Subscriber có thể yêu cầu một lượng dữ liệu phù hợp khả năng xử lý, giúp giảm flood. Nhưng **backpressure không tự bảo đảm không có request queue, không giới hạn total concurrency của tất cả tasks hoặc không gây 429**. Ngoài Reactor demand, cần giới hạn:

- Số page scans/job.
- Số jobs đang chạy trên pod.
- Downstream DB/Storage request concurrency.
- Rate limit per account/tenant.
- Số LRO đang hoạt động đồng thời.

### Không block trong reactive event loop

Tránh gọi JDBC blocking hoặc `Thread.sleep()` trong `flatMap` trên event-loop threads. Nếu bắt buộc dùng API blocking, chuyển sang scheduler phù hợp (`Schedulers.boundedElastic()`) với concurrency budget, hoặc dùng async client/driver thực sự.

## 14. Đọc một phần kết quả và hủy enumeration

Không phải lúc nào ứng dụng cũng cần list hết. Ví dụ UI chỉ hiển thị 20 objects đầu tiên:

~~~java
Mono<java.util.List<BlobItem>> firstTwenty =
    containerAsync.listBlobs().take(20).collectList();
~~~

`take(20)` **cancel upstream subscription** sau khi có đủ items theo Reactor behavior, nhưng không có nghĩa service chỉ trả đúng 20 items hoặc không có request/page được prefetch trước đó. Pagination granularity và SDK implementation quyết định network calls.

Với HTTP API, tránh tự trả toàn bộ hai triệu items trong một response; thay vào đó trả **page + opaque next-page cursor** và giới hạn page size tối đa. Nếu token được đưa cho client bên ngoài, cần validate scope, sign/encrypt theo security policy và không để user dùng token của tenant khác.

### Resume token trong REST API

Không trả raw continuation token như thể nó là “chứng chỉ truy cập”. Ví dụ REST wrapper:

~~~json
{
  "items": [
    {"name": "2026/11/invoice-001.json"},
    {"name": "2026/11/invoice-002.json"}
  ],
  "nextCursor": "<OPAQUE_APPLICATION_CURSOR>",
  "count": 2
}
~~~

Application cursor nên bind tenant/resource/prefix/page size hoặc server-side checkpoint reference theo policy; khi decode/lookup phải kiểm tra user quyền đọc tài nguyên trước. Không tin cursor client tự khai báo prefix khác.

## 15. Retry khi một page lỗi

Paged listing thường gồm nhiều HTTP requests, nên một request ở page 42 có thể gặp:

- `429 Too Many Requests` (throttling).
- `503 Service Unavailable` hoặc transient network timeout.
- `401/403` do token/identity/role/network thay đổi.
- `404` vì container/resource bị xóa.
- Invalid continuation token, service-side query mismatch.
- Connection pool exhaustion, proxy/TLS error.

**Không retry tất cả lỗi như nhau.**

### Retry policy

Azure SDK thường có retry policy cho các lỗi tạm thời theo implementation/config. Phải biết:

- Có tự động retry không? Lỗi nào và tối đa bao nhiêu lần?
- Có tôn trọng `Retry-After`/server delay không?
- Lệnh đang thực hiện có **idempotent** không?
- Request deadline và tổng timeout của job là bao lâu?
- Retries của SDK và retries của business worker có bị **nhân chồng** không?

Ví dụ: SDK retry 3 lần, worker retry 5 lần, hệ queue redeliver 4 lần → một lỗi tạm thời có thể tạo rất nhiều attempts. Kết hợp **bounded exponential backoff + jitter + retry budget** và đo retry count.

### Phân biệt lỗi

| HTTP/trạng thái | Hướng xử lý |
|---|---|
| 429 | Tôn trọng retry hint, giảm concurrency/rate, kiểm tra service quotas |
| 503/transient 5xx | Retry có budget, giám sát availability |
| 401 | Kiểm tra credential token và authentication; không lặp vô hạn |
| 403 | Kiểm tra RBAC/data-plane ACL/network firewall; thường không tự hết nếu sai cấu hình |
| 404 | Xác định resource/object đã bị xóa hay tenant/scope sai |
| Invalid cursor | Checkpoint và query scope; restart an toàn nếu cần |
| Timeout | Không biết request/server-side write đã thành công hay chưa; cần idempotency |

## 16. Long-running operation (LRO) là gì?

Nhiều thao tác Azure management/data plane có thể mất từ vài giây tới nhiều phút: tạo/sửa/xóa resource, bắt đầu copy/restore, provisioning network/compute hoặc job processing. Server có thể **chấp nhận** một yêu cầu rồi xử lý phía sau.

~~~mermaid
sequenceDiagram
  participant A as Java client
  participant S as Azure service
  A->>S: Begin operation
  S-->>A: 202 Accepted + operation/status URL
  loop Poll theo Retry-After/backoff
    A->>S: GET status URL
    S-->>A: Running / InProgress
  end
  A->>S: GET status URL
  S-->>A: Succeeded / Failed / Canceled
  A->>S: GET final resource/result nếu API yêu cầu
  S-->>A: Final result hoặc terminal metadata
~~~

**Lưu ý:** đây là một pattern Azure REST phổ biến, **không phải contract cố định cho mọi dịch vụ**. Một số LRO bắt đầu với HTTP 200/201 hoặc 202, trả `Azure-AsyncOperation`, `Operation-Location`, `Location` hay protocol/service-specific status URL. SDK có thể che giấu chi tiết này qua poller abstractions.

### HTTP 202 không phải job thành công

`202 Accepted` nghĩa service **đã tiếp nhận yêu cầu để xử lý**, không bảo đảm tài nguyên đã sẵn sàng. Nếu API Java nhận 202 và trả “đã tạo xong” ngay thì dễ xảy ra race khi downstream gọi resource chưa hoàn tất provisioning.

## 17. Các trạng thái LRO cần hiểu

Một LRO có thể đi qua:

~~~text
NOT_STARTED → IN_PROGRESS → SUCCESSFULLY_COMPLETED
                          ↘ FAILED
                          ↘ USER_CANCELLED (nếu dịch vụ hỗ trợ)
~~~

Tên trạng thái thực tế tùy service/poller: có thể gặp `Accepted`, `Running`, `Succeeded`, `Failed`, `Canceled`, `Updating` hoặc trạng thái riêng.

### Điều kiện xử lý

1. **In progress:** tiếp tục polling theo interval/hint, không lấy result cuối vội.
2. **Succeeded:** đọc final resource/result nếu API yêu cầu và kiểm tra postconditions.
3. **Failed:** ghi error code/correlation ID, không tạo business success record.
4. **Canceled:** xác nhận trạng thái server thực, không chỉ cancellation ở client.
5. **Timeout phía client:** **không được suy rằng operation server đã thất bại hoặc tự hủy**.

### Không đồng nhất LRO với thread

Một LRO chạy trên dịch vụ Azure, không phải thread Java nhất thiết phải tồn tại suốt thời gian đó. Client có thể lưu operation reference/status và kiểm tra sau, miễn service hỗ trợ cơ chế resume và token/status URL còn hiệu lực.

## 18. SyncPoller<P, T>: mẫu đồng bộ

Azure Core SDK cung cấp abstraction **`SyncPoller<P,T>`** cho những API có long-running operation đồng bộ. `P` là kiểu **intermediate polling value**, `T` là kiểu **final result**; không mặc định cả hai là cùng một loại.

Mẫu cấu trúc (phương thức `beginSomeSupportedOperation` là **pseudocode adapter** của SDK dịch vụ thực, không phải phương thức được mọi client cung cấp):

~~~java
import com.azure.core.util.polling.LongRunningOperationStatus;
import com.azure.core.util.polling.PollResponse;
import com.azure.core.util.polling.SyncPoller;

import java.time.Duration;

public final class LroWaiter {

    public static <P, T> T await(
            SyncPoller<P, T> poller,
            Duration maximumWait) {

        PollResponse<P> finalPoll =
            poller.waitForCompletion(maximumWait);

        if (!LongRunningOperationStatus.SUCCESSFULLY_COMPLETED
                .equals(finalPoll.getStatus())) {
            throw new IllegalStateException(
                "LRO did not complete successfully: "
                + finalPoll.getStatus()
            );
        }

        return poller.getFinalResult();
    }
}
~~~

Mẫu trên giả định SDK version có `waitForCompletion(Duration)`, `PollResponse.getStatus()` và `getFinalResult()`. Một số API/poller có semantics timeout hoặc exception khác nhau; kiểm tra API reference đang dùng. Nếu poller throw khi failed/timeout, cần xử lý exception xung quanh, không tin rằng lúc nào cũng trả `PollResponse` terminal.

### Không bắt đầu operation hai lần

~~~java
// Conceptual pseudocode:
SyncPoller<ProvisioningInfo, ResourceInfo> poller =
    serviceClient.beginSomeSupportedOperation(request);

// Poller được tạo từ một lần bắt đầu operation.
ResourceInfo result = LroWaiter.await(
    poller, Duration.ofMinutes(15)
);
~~~

`beginSomeSupportedOperation`, `ProvisioningInfo`, `ResourceInfo` **chỉ là tên giả định**. Với Azure Resource Manager, SDK có thể cung cấp phương thức khác (chẳng hạn fluent create/update chờ hoàn tất hoặc API begin...), không ép mọi resource manager client phải trả SyncPoller.

### PollResponse và final result

- `PollResponse<P>` chứa trạng thái và thông tin từ lần poll tương ứng.
- `getFinalResult()` trả result cuối khi operation đã hoàn thành theo contract.
- Có LRO **không có response body cuối**: final result có thể là `Void` hoặc metadata riêng.
- Đừng coi `response.getValue()` ở lần poll trung gian là kết quả tài nguyên cuối cùng.

## 19. PollerFlux<P, T>: mẫu bất đồng bộ

Với async SDK dùng Reactor, `PollerFlux<P,T>` cho phép xử lý LRO không block thread đang nhận HTTP request.

~~~java
import com.azure.core.util.polling.PollerFlux;
import reactor.core.publisher.Mono;

import java.time.Duration;

public final class AsyncLroWaiter {

    public static <P, T> Mono<T> await(
            PollerFlux<P, T> poller) {

        return poller.getFinalResult()
            .timeout(Duration.ofMinutes(20));
    }
}
~~~

Ở đây **client cụ thể** phải trả một `PollerFlux<P,T>` từ phương thức `begin...` mà nó hỗ trợ. `getFinalResult()` biểu diễn chuỗi lấy final result theo PollerFlux contract; cần xác minh behavior và subscription semantics của phiên bản dùng.

### Điểm quan trọng

- Reactive publisher chỉ chạy khi **có subscriber**.
- Không gọi `block()` trong Reactor event-loop/WebFlux request handlers.
- Có error path rõ cho timeout, service failure và cancellation.
- Dùng `doOnNext`/`doOnError`/tracing khi cần log metadata, không in request secrets.
- `timeout(Duration)` ở phía client **không đảm bảo operation server tự bị hủy**.
- Không subscription lặp đi lặp lại vào publisher bắt đầu LRO nếu chưa rõ tác động; giữ operation identity/reference.
- Với job dài hàng giờ, tốt hơn tách thành **status endpoint + durable operation tracker** thay vì giữ HTTP connection.

### Async không có nghĩa vô hạn concurrency

Một dịch vụ nhận 5.000 LRO đồng thời có thể bị throttling hoặc quota limit. Dùng bounded concurrency, rate limit, queue và retry policy cho **begin requests** lẫn **poll requests**.

## 20. Poll interval, Retry-After và thundering herd

Polling quá thường xuyên có thể làm tăng chi phí HTTP, gặp 429 và gây áp lực lên control plane. Polling quá chậm làm người dùng đợi lâu hơn sau khi job thực tế đã hoàn tất.

### Chiến lược

1. Ưu tiên **polling interval/hint mà service và SDK cung cấp**.
2. Nếu API yêu cầu tự poll, tôn trọng `Retry-After` khi có.
3. Dùng interval giới hạn tối thiểu/tối đa và **jitter** nếu nhiều jobs cùng đợi.
4. Không dùng `while(true)` + `Thread.sleep(100)` cho mọi job.
5. Ghi số lần poll, duration, 429 và estimated time-to-completion.
6. Có overall timeout/deadline theo SLO và background tracker khi timeout.

Ví dụ:

~~~text
Job A created at 10:00:00
Poll hint: retry after 10 seconds
Poll 1 at 10:00:10 -> Running
Poll 2 at 10:00:20 -> Running
Poll 3 at 10:00:30 -> Succeeded
Fetch final resource and verify readiness
~~~

Không tự parse mọi `Retry-After` giống nhau: chuẩn HTTP có thể dùng số giây hoặc ngày giờ; một số Azure APIs dùng header millisecond-specific. Azure SDK poller thường xử lý protocol tương ứng; tránh override tùy tiện làm sai behavior.

## 21. Timeout của request, LRO và job khác nhau

Có ít nhất ba thời hạn:

| Timeout/deadline | Ví dụ | Ý nghĩa |
|---|---|---|
| HTTP per-call | 20–30 giây | Một request tới service/đọc page/status |
| Polling wait deadline | 10–20 phút | Client chờ LRO đạt terminal state |
| Business job deadline | Trước 06:00 | Quy trình nghiệp vụ phải hoàn tất |

### Cảnh báo quan trọng

- HTTP timeout khi **begin** có thể xảy ra **sau khi service đã nhận request**: retry begin không có idempotency dễ tạo nhiều operations.
- Timeout khi poll **không** có nghĩa server operation đã thất bại.
- API gateway timeout 30 giây không phù hợp giữ request đồng bộ cho LRO 20 phút.
- Một LRO Succeeded nhưng downstream side effect chưa được xác minh (resource health, DNS readiness...) có thể chưa đáp ứng business postconditions.
- SDK-specific cancellation phải phân biệt **cancel local subscription** với cancel operation trên server.

### Mô hình HTTP API đề xuất

~~~text
POST /provisioning-jobs
  -> validate request
  -> create durable job record + idempotency key
  -> start one Azure operation
  -> return HTTP 202 with application jobId/status URL

GET /provisioning-jobs/{jobId}
  -> return local job state + Azure operation state
  -> optionally refresh state with rate limits

Background worker
  -> poll Azure LRO
  -> update terminal status and final resource ID
  -> notify business workflow
~~~

Không trả `201 Created` và resource ID “sẵn sàng dùng” trước khi operation terminal + postconditions đạt yêu cầu.

## 22. Resume LRO và lưu trạng thái bền vững

Một LRO có thể kéo dài lâu hơn vòng đời Java process. Cần lưu:

~~~json
{
  "jobId": "provision-20261120-001",
  "operationType": "CreateOrUpdateResource",
  "resourceId": "/subscriptions/.../resourceGroups/.../providers/...",
  "idempotencyKey": "<APPROVED_REQUEST_ID>",
  "trackingReference": "<SERVICE_OPERATION_REFERENCE>",
  "status": "IN_PROGRESS",
  "attempt": 1,
  "createdAtUtc": "2026-11-20T10:00:00Z",
  "nextPollAfterUtc": "2026-11-20T10:00:10Z"
}
~~~

**Điểm khó:** không phải mọi `SyncPoller/PollerFlux` hỗ trợ xuất một **resume token** có thể lưu qua process và tạo lại poller, hoặc token có thể hết hạn. Với Azure REST/SDK, một số service cung cấp operation ID/status URL và cơ chế reattach; một số không. Không tuyên bố một `getResumeToken()` là luôn có hoặc luôn dùng được.

### Chiến lược an toàn

1. Nếu SDK/service hỗ trợ resume chính thức: lưu reference/token được thiết kế cho việc đó.
2. Nếu không: lưu resource ID và dùng supported **GET status/resource** semantics để đối soát sau restart.
3. Nếu trạng thái không rõ sau timeout: **reconcile trước khi retry begin**.
4. Dùng idempotency key/unique request record để chỉ một worker sở hữu begin.
5. Poll tracker có lease/lock nhưng phải xử lý lease expiry/failover.
6. Khi status URL hết hạn, có fallback dựa trên resource state hay manual review.
7. Không lưu bearer token/access key trong tracking record.
8. Có TTL/retention cho operation history để không phình DB/log.

### Cancel có phải rollback?

Không. Nếu service hỗ trợ cancel server-side, nó có thể trả trạng thái Canceled nhưng **tác dụng phụ đã hoàn thành một phần vẫn tồn tại**. Cần kế hoạch compensation/cleanup riêng; không giả định stop polling sẽ rollback provisioning.

## 23. Idempotency và retry khi quản lý tài nguyên Azure

Ví dụ quản trị Azure VM:

1. Ứng dụng gửi begin create VM với tên `batch-worker-01`.
2. Client timeout trước khi nhận response.
3. Server thực tế đã nhận operation và đang tạo VM.
4. Ứng dụng retry begin mà không kiểm tra resource state.
5. Có thể gặp conflict, duplicate side effects hoặc thay đổi cấu hình ngoài ý muốn.

### Thiết kế

- Chọn tên/resource ID **deterministic** khi có thể.
- Mỗi business request có **idempotency key** lưu bền vững.
- Trước retry begin, đọc operation/resource status theo service contract.
- Dùng optimistic concurrency/ETag/If-Match khi API hỗ trợ.
- Kiểm tra outcome thực sau terminal state.
- Giới hạn begin retries và poll retries riêng.
- Nếu job bị timeout nhưng server vẫn chạy, báo `IN_PROGRESS/UNKNOWN` thay vì giả thành FAILED.
- Có rollback/cleanup cho partial resources.

**Không suy rằng mọi Azure PUT đều hoàn toàn idempotent trong mọi tình huống** nếu request body, conditional headers, secrets hoặc server-side defaults có thể khác nhau giữa các attempts. Theo dõi contract của resource provider.

## 24. Quản lý client: một client dùng được bao lâu?

Azure SDK clients thường được thiết kế để reuse lâu dài. So sánh:

~~~java
// Anti-pattern: tạo credential + client cho mỗi request.
public void listOnce(String endpoint) {
    var credential = new DefaultAzureCredentialBuilder().build();
    var client = new BlobServiceClientBuilder()
        .endpoint(endpoint)
        .credential(credential)
        .buildClient();
    client.getBlobContainerClient("invoices").listBlobs()
        .iterator().hasNext();
}
~~~

Các hệ quả có thể là:

- Thừa object/pipeline allocations.
- Tăng token discovery/authentication overhead.
- Connection pools/threads bị phân mảnh khi tạo transport riêng.
- Cold-start/latency tăng.
- Khó áp dụng telemetry/timeouts/retry policy thống nhất.
- Khó dọn tài nguyên khi shutdown.

### Mẫu đúng

Tạo `TokenCredential` và client khi ứng dụng khởi động hoặc khi cần cho một **endpoint/configuration tenant-specific** có cache/eviction. Reuse client qua các requests, đảm bảo cấu hình immutable/ổn định và hạn chế số clients không giới hạn.

**Thread-safe client** không đồng nghĩa mọi object quanh nó thread-safe: request builders/options, mutable maps và collections cần dùng theo contract; đừng chia một object `ListBlobsOptions` có thread khác đang mutate.

## 25. Khi nào phải close/dispose?

Không có một quy tắc `try-with-resources` cho tất cả Azure SDK Java clients.

| Tài nguyên | Cách quản lý |
|---|---|
| `BlobServiceClient` hoặc các service clients tương tự | Thường reuse, không tự gọi `close()` nếu class không có |
| Credential có resource ownership riêng | Xem API/documentation; không giả định `TokenCredential` luôn AutoCloseable |
| Custom HTTP transport/connection pool | Nếu tự tạo và sở hữu, giải phóng theo API chính thức của implementation |
| Reactor subscription | Cancel/dispose khi job bị dừng; không đồng nghĩa cancel server LRO |
| InputStream/OutputStream/FileChannel | Đóng bằng try-with-resources khi ứng dụng mở |
| ExecutorService/Scheduler tự tạo | Shutdown khi ứng dụng kết thúc |
| SDK service client có `close()` | Chỉ close khi API cụ thể yêu cầu/cho phép, theo ownership |

### Sai lầm thường gặp

~~~java
// Không làm mặc định nếu BlobServiceClient không implements AutoCloseable:
// try (BlobServiceClient client = builder.buildClient()) { ... }
~~~

Thay vào đó:

~~~text
Application startup:
  create shared credential
  create service client(s)
  configure telemetry/retries/timeouts

Application lifetime:
  reuse clients for concurrent operations

Application shutdown:
  stop accepting new jobs
  drain/cancel outstanding publishers as needed
  flush checkpoint/logs
  close only resources explicitly owned and closable
~~~

**Client reuse không có nghĩa giữ mãi mọi thứ mà không giới hạn**. Nếu hệ multi-tenant tạo một client cho mỗi storage account, cần cache keyed by endpoint/auth scope, TTL/eviction và lifecycle control; không cho cache client tăng vô hạn.

## 26. HTTP transport, connection pool và threads

Azure SDK Java có các HTTP transport implementations khác nhau (ví dụ Netty hoặc OkHttp) tùy dependency và cấu hình. Thực tế ứng dụng cần quan tâm:

- Number of concurrent in-flight HTTP requests.
- TCP/TLS connection reuse/keepalive.
- Connection pool size và pending-acquire queue.
- Event loop threads so với blocking worker threads.
- DNS, proxy và Private Endpoint routing.
- Connect/read/response timeout semantics.
- Resource ownership khi bạn cấu hình custom transport.

### Vì sao một transport được chia sẻ hữu ích?

Một HTTP pipeline/transport được quản lý đúng có thể reuse network connections và metrics, giảm handshake. Nhưng **không tự tăng connection pool vô hạn** để chữa 429: server throughput/quota và client backpressure vẫn là giới hạn.

### Nguy hiểm khi dùng Reactive + Blocking

Một WebFlux handler như:

~~~java
// Anti-pattern trong reactive event loop:
return Mono.fromCallable(() -> syncClient.listBlobs().iterator().hasNext());
~~~

Nếu thực thi trên event-loop thread, đoạn blocking I/O có thể làm nghẽn server. Nếu bắt buộc dùng sync SDK:

~~~java
return Mono.fromCallable(
        () -> syncClient.listBlobs().iterator().hasNext())
    .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

Điều này **chỉ chuyển blocking work sang boundedElastic scheduler**, không biến I/O thành non-blocking hoặc thay concurrency budget. Ưu tiên async SDK khi xây một pipeline Reactor end-to-end.

## 27. Spring Boot: quản lý client bằng dependency injection

Ví dụ bean singleton cho Azure Blob SDK:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AzureBlobConfiguration {

    @Bean
    TokenCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    BlobServiceClient blobServiceClient(
            TokenCredential credential,
            @Value("${azure.storage.blob.endpoint}") String endpoint) {

        return new BlobServiceClientBuilder()
            .endpoint(endpoint)
            .credential(credential)
            .buildClient();
    }
}
~~~

Dùng trong service:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobContainerClient;

import org.springframework.stereotype.Service;

@Service
public final class InvoiceStorageService {
    private final BlobContainerClient container;

    public InvoiceStorageService(BlobServiceClient client) {
        this.container = client.getBlobContainerClient("invoices");
    }

    public long countInvoices() {
        long result = 0;
        for (var item : container.listBlobs()) {
            result++;
        }
        return result;
    }
}
~~~

### Giới hạn ví dụ

- `countInvoices()` là operation có thể kéo dài; không gắn trực tiếp vào HTTP endpoint có SLA thấp.
- Bean `BlobServiceClient` **không có giả định destroy method**; Spring lifecycle phải theo API client cụ thể và transport ownership.
- Endpoint lấy từ externalized configuration, không chứa account key.
- Với nhiều storage accounts, tạo named clients/configuration thay vì chia một client tới nhiều endpoints không tương thích.
- Tránh ghi mutable state của một enumeration vào singleton field dùng chung giữa requests.
- Với long-running listing, dùng background job/queue và checkpoint.

## 28. Timeout và cancellation ở ứng dụng

Một API GET `/blob-inventory` trả full kết quả có thể chạy 15 phút trong khi ingress timeout 30 giây. Sử dụng:

~~~text
POST /inventory-jobs
  -> 202 Accepted, jobId
GET /inventory-jobs/{jobId}
  -> status, processed, lastCheckpoint, errors
GET /inventory-jobs/{jobId}/results
  -> bounded page of processed results
~~~

### Khi request bị hủy

- Hủy `Flux` subscription có thể ngừng các HTTP requests sắp tới, nhưng một request đang xử lý phía server có thể vẫn tiếp tục.
- Tắt Java process trước khi persist checkpoint khiến page bị replay.
- Hủy waiting thread của SyncPoller không nhất thiết cancel LRO server-side.
- `Future.cancel(true)` là tín hiệu local, không phải bằng chứng backend đã rollback.
- Với write operations, reconcile server state trước khi retry/cancel.

### Deadline propagation

Nếu end-to-end deadline chỉ 30 giây, không nên cho ba lớp retry mỗi lớp 30 giây. Phân chia budget:

~~~text
API request budget:       30s
Identity/token:           bounded
Per-page/request timeout: bounded
Retries:                 budget-aware
Fallback:                fail fast or async job
Background run deadline: independent from HTTP client timeout
~~~

Tất cả timeouts trong ví dụ là lựa chọn kiến trúc, không phải Azure SDK defaults.

## 29. Observability: đo điều gì?

Để tránh “service chậm không rõ lý do”, cần giám sát:

| Tín hiệu | Đơn vị/chiều | Mục đích |
|---|---|---|
| Pages fetched | pages/job | Tiến độ enumeration |
| Items processed | items/job | Business throughput |
| Preferred/actual page size | items/page | Kiểm tra page behavior |
| Time per page | ms | Phát hiện network/throttling |
| Continuation checkpoint age | min | Resume health |
| 429/503/retry count | attempts | Throttling/transient errors |
| Active LRO count | operations | Quản lý capacity |
| LRO status/duration | state, s | Provisioning reliability |
| Poll attempts | polls/operation | Tránh polling quá mức |
| Connection pool pending/timeout | count/ms | Client transport pressure |
| JVM heap/GC/threads | MiB/ms/count | Phát hiện collectList/client churn |
| Authentication failures | 401/403 | RBAC, token, network |
| Application p95/p99 | ms | UX/SLO |
| Storage/management API request cost | per operation | FinOps và quota |
| Replayed/duplicate items | count | Idempotency chất lượng |

### Correlation IDs

Theo dõi `jobId`, `tenantId` (đã pseudonymize theo policy), Azure `x-ms-request-id` hoặc correlation fields do SDK/service cung cấp. **Không log continuation token, SAS, access token, connection string hoặc customer data**.

### OpenTelemetry/Application Insights

Azure SDK có thể tham gia tracing/diagnostic instrumentation khi được cấu hình phù hợp. Gắn custom spans:

~~~text
HTTP POST /inventory-jobs
  -> schedule job
     -> list blobs page 12
        -> process 200 items
        -> save checkpoint
        -> begin Azure LRO
           -> status polls
           -> final resource validation
~~~

Không coi trace một request là một transaction nhiều giờ; dùng durable job records và event/correlation IDs để nối các phần.

## 30. Bảo mật và ranh giới truy cập

### Client credentials

- Ưu tiên `DefaultAzureCredential` và managed identity/workload identity khi hỗ trợ.
- Local development dùng credential được đăng nhập có kiểm soát, không hard-code account keys.
- Grant **data-plane RBAC** cho Blob listing (Storage Blob Data Reader), thêm quyền ghi nếu job xử lý write thực.
- Grant **management-plane RBAC** riêng cho LRO tạo/xóa resource.
- Không cho một worker duyệt inventory tự có quyền Owner trên toàn subscription nếu không cần.
- Tách identity và permission scope theo tenant/environment.
- Key Vault để giữ secrets cần thiết, rotate và audit.

### Network

- Storage firewall, Private Endpoint, VNet, Private DNS và outbound connectivity phải cùng hoạt động.
- Endpoint authentication và network reachability là **hai điều kiện khác nhau**.
- Nếu dùng proxy, kiểm tra service client transport và trust store/TLS.
- Không tắt certificate verification chỉ để “fix” TLS.
- Với SDK async, kiểm tra DNS/endpoint routing của HTTP provider.
- Không đưa raw private endpoint IP vào code thay hostname nếu TLS hostname verification phụ thuộc FQDN.

### Chống lộ continuation token

Continuation token đôi khi chứa internal state hoặc resource identifiers. Không đặt thẳng vào URL query logs công khai; nếu cần đưa cursor cho frontend, dùng opaque application cursor hoặc signed reference có scope, expiry và authorization validation.

## 31. Cost và quota

Một listing tưởng như “chỉ đọc danh sách” vẫn có chi phí:

- Azure Storage **List operations** theo request/transaction meter.
- Egress/network giữa regions hoặc tới on-prem theo kiến trúc.
- JVM/Container Apps/AKS/VM compute chạy job.
- Database/checkpoint storage và Log Analytics ingestion.
- Azure management API quotas, polling requests.
- Retry/duplicate processing tăng số calls.
- HTTP connections và memory pressure làm phải scale compute.

### Ví dụ số trang

~~~text
Total blobs:      1.200.000
Preferred page:   200 items
Theoretical pages: 1.200.000 / 200 = 6.000 pages
Actual pages:     có thể khác theo service-side behavior
~~~

Nếu page size thực tế chỉ 100 items, có thể cần khoảng 12.000 page requests. Mỗi request có overhead latency, rate limits và billing phù hợp. **Không tự kết luận giá** từ công thức trên; xem Azure pricing meter và telemetry thực.

### Ước lượng thời gian

~~~text
Average page fetch: 80 ms
Pages: 6.000
Sequential fetch lower bound ~480.000 ms = 8 phút

Total job còn thêm:
  processing items, retries, storage writes, checkpoint commits,
  throttling, network variance và startup.
~~~

Nếu page throughput nhiều item nhưng downstream xử lý chậm, network fetch không còn là bottleneck. Tăng page size có thể tăng RAM và thời gian replay khi crash; cân bằng **latency, checkpoint frequency và memory**.

## 32. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| `collectList()` trên hàng triệu items | Heap/GC/OOM | Streaming pages |
| Toàn bộ list trong HTTP GET | Timeout và bộ nhớ | Async job + paginated result |
| Giả định page size cố định | Bỏ sót items hoặc index lỗi | Duyệt từ response values/token |
| Tự parse continuation token | Sai khi service đổi format | Token opaque, persist nguyên vẹn |
| Checkpoint trước xử lý page | Mất dữ liệu khi crash | Commit page rồi checkpoint |
| Không idempotency | Replay tạo duplicate side effects | Unique key/upsert |
| Duyệt list như snapshot | Bỏ/đúp khi dữ liệu thay đổi | Reconciliation/versioning |
| Gọi begin LRO lại khi client timeout | Duplicate/conflict | Reconcile resource/operation status |
| Coi HTTP 202 là Succeeded | Dùng resource chưa ready | Poll terminal + postconditions |
| Poll status 100ms trong hàng giờ | 429/quota/chi phí | Retry-After, bounded intervals |
| Client timeout = server canceled | Sai trạng thái nghiệp vụ | Durable tracking |
| Mỗi request tạo credential/client | Connection/auth churn | Singleton/client cache |
| `close()` client không hỗ trợ | Lỗi biên dịch/ownership sai | Theo API cụ thể |
| `block()` trong WebFlux event loop | Thread starvation | Async SDK hoặc boundedElastic |
| Retry vô hạn | Throttling/storm | Retry budget + jitter |
| Logs chứa token và SAS | Rò rỉ dữ liệu/credentials | Redaction và access controls |

## 33. Troubleshooting theo triệu chứng

### Duyệt blob chậm hoặc lỗi giữa chừng

1. Xác minh endpoint/account/container/prefix đã đúng.
2. Kiểm tra SDK version, preferred page size và số items/page thực.
3. Quan sát HTTP status, x-ms-request-id, Retry-After và retry count.
4. Kiểm tra role Data Reader và Storage network/firewall.
5. Xem JVM heap, GC, client allocations, thread pools và HTTP connections.
6. Xác định checkpoint gần nhất; resume cùng scope/prefix.
7. Nếu token invalid, restart scan có idempotent dedup.
8. Đánh giá dữ liệu có thay đổi trong lúc list hay không.

### LRO bị kẹt InProgress

1. Xác nhận begin call chỉ thực hiện một lần hay đã retry.
2. Ghi operation/resource ID, poll attempts, status và age.
3. Đọc service-specific provisioning state/errors và activity logs.
4. Kiểm tra quota, dependencies, network, permissions của resource.
5. Tôn trọng Retry-After; không spam poll.
6. So client timeout và server operation state.
7. Nếu status không xác định, reconcile rồi mới quyết định retry/cleanup.
8. Có escalation với x-ms-request-id/correlation ID đã lọc.

### Client nhiều connections hoặc token requests

1. Tìm nơi gọi `new ClientBuilder` trong per-request loop.
2. Xem có tạo custom HTTP transport/pool cho mỗi request không.
3. Đếm distinct client instances theo endpoint/tenant.
4. Kiểm tra connection pool limits/queues và HTTP provider metrics.
5. Kiểm tra `DefaultAzureCredential` có bị build liên tục không.
6. Kiểm tra Reactor subscriptions hoặc blocking operations không được giải phóng.
7. Chuyển sang DI singleton/cached clients và bounded concurrency.
8. Kiểm thử load trước/sau, không chỉ xem source code.

## 34. Case study: kiểm kê blob và provisioning job

### Bối cảnh

Một nền tảng SaaS lưu hơn 5 triệu blobs cho nhiều tenants. Mỗi ngày cần kiểm kê metadata và, với các containers mới, bắt đầu một số Azure operations cấu hình tài nguyên. Ứng dụng Java trên AKS có 8 replicas, mỗi replica có thể bị rescheduled.

**Yêu cầu:**

- Không tải toàn bộ inventory vào RAM.
- Không để hai pods đồng thời xử lý cùng job.
- Nếu worker restart, tiếp tục từ checkpoint.
- Không tạo tài nguyên trùng nếu begin LRO bị timeout.
- Jobs kéo dài không khóa HTTP request.
- Quyền Storage read và management write tách biệt.
- Có dashboard progress, retries và chi phí.

### Kiến trúc

~~~mermaid
flowchart LR
  API["Java API / AKS"] --> QUEUE["Job queue"]
  QUEUE --> WORK["Bounded workers"]
  WORK --> BLOB["Blob listing PagedFlux/PagedIterable"]
  BLOB --> CKPT["Durable checkpoint DB"]
  WORK --> LRO["Azure management LRO"]
  LRO --> TRACK["Operation tracker"]
  TRACK --> CKPT
  CKPT --> STATUS["Job status API"]
  WORK --> MON["Azure Monitor"]
  LRO --> MON
~~~

### Kế hoạch xử lý

1. API nhận yêu cầu tạo `inventory-job-id`, kiểm tra identity/tenant scope, enqueue.
2. Worker lấy lease/job ownership từ durable store.
3. Dùng shared `BlobServiceClient` hoặc `BlobContainerAsyncClient` đã cấu hình.
4. List theo prefix/container từng page 200–500 items theo benchmark.
5. Upsert metadata với unique key (tenant, container, blob name, ETag/version).
6. Chỉ lưu continuation sau page hoàn tất.
7. Với yêu cầu tạo tài nguyên, lưu idempotency key và begin một LRO.
8. Poll LRO với interval hợp lý, lưu terminal status/final resource ID.
9. Nếu worker chết, worker mới khôi phục checkpoint và reconcile active LRO.
10. Dashboard progress, 429, heap, LRO duration, duplicate count, cost.

### Phân tích sự cố

Khi nhóm trước đó dùng `collectList()`, 8 pods có memory spikes, OOM và bắt đầu lại từ đầu; database downstream có duplicate entries. Sau khi chuyển sang paging + checkpoint + idempotent upsert, peak memory giảm và retries không làm nhân đôi dữ liệu. Với LRO, nhóm không còn gọi begin lần hai ngay khi client timeout mà đối soát operation/resource state trước.

Đây là kiến trúc mẫu, không phải kết quả benchmark thực tế của một hệ Azure cụ thể. Cần load test theo quota, network và data distribution.

## 35. Bài thực hành tổng hợp

> **An toàn:** làm trên Azure Storage container và subscription/resource group **lab** được cấp phép. List requests, tạo tài nguyên, LRO và logging có thể phát sinh phí; tránh thao tác xóa/cập nhật production. Không tạo file khác trong repo ngoài nội dung bài theo hợp đồng worker; người học tự tạo source files khi thực hành.

### Phần A — Thiết lập

1. Chọn storage account/container lab có 1.000–5.000 blobs test.
2. Cấp Storage Blob Data Reader cho managed/developer identity.
3. Cấu hình `AZURE_STORAGE_BLOB_ENDPOINT` từ môi trường.
4. Tạo project Java 17/Maven với Azure SDK BOM và dependencies.
5. Tạo shared `BlobServiceClient` qua `DefaultAzureCredential`.
6. Kiểm tra network/Private Endpoint/DNS nếu tài nguyên không public.
7. Xác định chi phí List operations, giới hạn requests và budget.

### Phần B — Pagination

1. Dùng `listBlobs()` và `PagedIterable` đếm items.
2. Dùng `iterableByPage(200)` và log số items/page (không log continuation token).
3. Đo số pages, thời gian và peak heap.
4. Cố tình dừng sau 3 pages; lưu checkpoint ở test DB.
5. Resume với same prefix/options/token.
6. Chạy lại 1 page để xác minh idempotent upsert.
7. Thử thay đổi dữ liệu trong lúc scan; quan sát vì sao listing không được xem như snapshot.
8. So sánh `collectList()` (chỉ trên dữ liệu nhỏ) với streaming, **không gây OOM cố ý**.

### Phần C — Async và backpressure

1. Tạo `BlobContainerAsyncClient` được tái sử dụng.
2. Dùng `PagedFlux` và `byPage(200)`.
3. Viết `processAsync` ghi vào datastore lab.
4. Giới hạn `flatMap` concurrency khoảng 4–8 theo benchmark.
5. Dùng `concatMap` để checkpoint theo thứ tự pages.
6. Inject failure một item trong page; xác minh checkpoint không tiến.
7. Kiểm tra Reactor pipeline không gọi blocking JDBC trong event loop.
8. Đo throughput, 429 và memory khi thay concurrency.

### Phần D — Long-running operation

1. Chọn một Azure operation **thật có support LRO** được phép trong resource group lab.
2. Xác định method `begin...` và kiểu `SyncPoller`/`PollerFlux` thực tế của SDK dịch vụ đó; nếu không có, dùng REST operation status theo tài liệu.
3. Start một operation, ghi operation ID và timestamp.
4. Theo dõi InProgress đến terminal state bằng interval có giới hạn.
5. Kiểm tra Succeeded/Failed và final resource postconditions.
6. Thử client polling deadline ngắn hơn thời gian operation server hoàn tất; xác nhận server state không tự mất.
7. Xây durable tracker/status API và idempotency key.
8. Thử restart worker và reconcile server state trước retry begin.
9. Không dùng resource production và không tự thực hiện destructive operations.

### Phần E — Quản lý client và monitoring

1. So code tạo client per request với bean singleton.
2. Đo số connections, latency, token calls trong lab.
3. Đặt retry/timeouts cho workload theo SDK/version.
4. Thiết lập metric pages/items/retries/LRO duration/heap.
5. Bật tracing/diagnostics không chứa secrets.
6. Kiểm tra subscription RBAC management khác Storage data-plane role.
7. Viết shutdown routine giải phóng streams/executors/custom transport mà ứng dụng thực sự sở hữu.
8. Tính cost per inventory job và cost per successful provisioning operation.
9. Viết runbook xử lý 429, invalid continuation, LRO timeout, stale operation state.
10. Cleanup tài nguyên lab và ghi bài học vận hành.

## 36. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao listing hai triệu blobs không nên trả một Java `List<BlobItem>` đầy đủ?

**Câu 2.** `PagedIterable` khác `PagedFlux` ở cơ chế thực thi và xử lý luồng thế nào?

**Câu 3.** `iterableByPage(200)` có bảo đảm mọi page có đúng 200 items không?

**Câu 4.** Continuation token khác offset/page number ra sao?

**Câu 5.** Vì sao cần giữ nguyên token và listing scope khi resume?

**Câu 6.** Vì sao checkpoint cần lưu **sau** khi xử lý page thành công?

**Câu 7.** Làm sao giảm duplicate side effects khi worker crash sau DB commit nhưng trước checkpoint?

**Câu 8.** Listing có bảo đảm snapshot nhất quán khi blob thay đổi giữa các pages không?

**Câu 9.** `collectList()` nguy hiểm thế nào với tập dữ liệu lớn?

**Câu 10.** `concatMap` và `flatMap(..., 8)` phục vụ hai mục đích khác nhau thế nào trong async page processing?

**Câu 11.** Backpressure có tự bảo đảm không bị Azure Storage 429 không?

**Câu 12.** Vì sao HTTP 202 chưa đủ kết luận Azure resource đã provisioning xong?

**Câu 13.** `SyncPoller<P,T>` phân biệt kiểu polling và final result thế nào?

**Câu 14.** Khi polling thất bại vì timeout client, có được kết luận server operation đã FAILED không?

**Câu 15.** `PollerFlux` khác `SyncPoller` thế nào trong ứng dụng WebFlux?

**Câu 16.** Vì sao phải tôn trọng Retry-After và không poll mỗi 100ms vô hạn?

**Câu 17.** Stop subscription của PollerFlux có luôn cancel server operation không?

**Câu 18.** Nếu begin LRO đã được nhận nhưng response timeout, nên làm gì trước retry begin?

**Câu 19.** Tại sao một số LRO không thể resume bằng token trong mọi SDK?

**Câu 20.** Khi nào cần durable operation tracker và background worker thay vì giữ HTTP request?

**Câu 21.** Azure SDK clients có nên tạo mới cho từng servlet request không?

**Câu 22.** `BlobServiceClient` có cần gọi `close()` mặc định không?

**Câu 23.** Nếu ứng dụng tự tạo custom HTTP connection pool, ai chịu trách nhiệm dispose?

**Câu 24.** Tại sao gọi sync `listBlobs()` trong Reactor event loop có thể gây starvation?

**Câu 25.** `DefaultAzureCredential` và RBAC có tự tạo network route tới Private Endpoint không?

**Câu 26.** Resource Group Contributor có tự có Storage Blob Data Reader không?

**Câu 27.** Cần những metrics nào để phân biệt service throttling, connection pool pressure và Java heap OOM?

**Câu 28.** Vì sao một LRO Succeeded vẫn có thể cần kiểm tra resource postconditions?

**Câu 29.** Vì sao cost của pagination không chỉ là memory CPU?

**Câu 30.** Đâu là ba biện pháp quan trọng nhất khi một job vừa duyệt hàng triệu blobs vừa kích hoạt Azure LRO?

**Tiêu chí hoàn thành:** người học giải thích đúng các abstraction của Azure SDK Java, lập trình liệt kê có giới hạn bộ nhớ, sử dụng continuation token/checkpoint, hiểu polling LRO và timeout/cancellation/idempotency, quản lý client/credential/HTTP transport phù hợp, có quan sát và kiểm soát chi phí.

## Kết luận

**Pagination, long-running operation và quản lý tài nguyên client** là ba kỹ năng trọng yếu khi ứng dụng Java gọi Azure ở quy mô lớn. **`PagedIterable`/`PagedFlux`** giúp duyệt hàng triệu objects mà không gom mọi dữ liệu vào heap, nhưng cần sử dụng continuation tokens như giá trị opaque, checkpoint sau khi downstream commit và xây idempotency vì retries có thể phát lại một page. **`SyncPoller`/`PollerFlux`** giúp quản lý operations kéo dài, nhưng phải phân biệt yêu cầu được chấp nhận với trạng thái terminal; timeout hoặc stop polling ở client không có nghĩa Azure đã hủy operation.

Về vận hành, **tái sử dụng Azure SDK clients, credentials và HTTP pipelines**, tránh tạo client mới trong mỗi request, giới hạn concurrency và chỉ giải phóng những resources mình thực sự sở hữu. Kết hợp với **Microsoft Entra RBAC, network security, Retry-After/backoff, tracing, Azure Monitor, durable job tracking và FinOps**, hệ thống Java trên Azure sẽ bền vững hơn trước lỗi tạm thời, dữ liệu lớn và những tác vụ quản lý tài nguyên kéo dài.

