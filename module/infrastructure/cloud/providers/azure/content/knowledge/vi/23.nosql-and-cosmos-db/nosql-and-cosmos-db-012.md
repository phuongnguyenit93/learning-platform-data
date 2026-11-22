# Cosmos DB Java SDK và xử lý throttling

## 1. Khi dữ liệu NoSQL nhanh nhưng ứng dụng vẫn nhận lỗi 429

Một ứng dụng bán hàng Java lưu giỏ hàng, đơn hàng và lịch sử thao tác vào **Azure Cosmos DB**. Trong ngày bình thường, các API phản hồi nhanh. Khi chiến dịch khuyến mãi bắt đầu, lượng ghi tăng đột biến, nhiều requests bị chậm và log xuất hiện **HTTP 429 Too Many Requests**.

Phản ứng tự nhiên là tăng số Pod hoặc tạo thêm Java threads. Nhưng nếu dữ liệu trong Cosmos DB đang bị giới hạn bởi **Request Units per second (RU/s)**, tăng số requests đồng thời có thể tạo thêm throttling, tăng thời gian chờ và chi phí retry mà không tăng số thao tác thành công tương ứng.

Bài học này giải thích cách dùng **Azure Cosmos DB Java SDK v4 cho Azure Cosmos DB for NoSQL**, xử lý response, đọc diagnostics, quản trị retry và tối ưu throughput. Đây là một nội dung của chương **Dữ liệu NoSQL với Cosmos DB** thuộc module khám phá Microsoft Azure, gắn với resource group, Microsoft Entra ID, App Service/AKS/Functions, mạng, bảo mật, giám sát và kiểm soát chi phí.

**Phân biệt ngay ba ý:**

- **429** thường cho biết request bị giới hạn vì không đủ RU/s sẵn có trong một khoảng thời gian ở phạm vi liên quan.
- **SDK retry** có thể chờ theo thời gian broker yêu cầu và gửi lại. Nó giúp ứng dụng chịu được những đợt giới hạn ngắn, nhưng không làm tăng công suất RU/s.
- **Sửa gốc** có thể là tối ưu truy vấn, thiết kế partition key, giảm request charge, điều tiết concurrency hoặc tăng throughput phù hợp, chứ không nhất thiết tăng số Java workers.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mô hình database, container, item, id và logical partition trong Cosmos DB for NoSQL.
2. Hiểu RU, RU/s, request charge và throughput provisioned, autoscale, serverless.
3. Chọn partition key phục vụ truy vấn và phân phối tải.
4. Tạo một CosmosClient/CosmosAsyncClient bằng Java SDK v4, sử dụng credential an toàn.
5. Thao tác create, read, upsert, replace, delete và query với partition key chính xác.
6. Đọc status code, request charge, activity ID và Cosmos diagnostics.
7. Giải thích HTTP 429, retry-after và automatic retry của SDK.
8. Thiết kế bounded retries, jitter, deadlines, idempotency và backpressure.
9. Điều chỉnh sync/async concurrency, pagination và bulk workloads.
10. Phân biệt hot logical partition với thiếu throughput toàn container.
11. Theo dõi throttled requests, RU consumption, latency và failures bằng Azure Monitor.
12. Lập bài kiểm thử tải, runbook incident và phương án chi phí phù hợp.

## 3. Phạm vi: Cosmos DB for NoSQL, không phải mọi API của Cosmos DB

Azure Cosmos DB cung cấp những mô hình API khác nhau, trong đó có **Azure Cosmos DB for NoSQL**. Bài tập trung vào Java SDK có package **com.azure.cosmos**, hỗ trợ API for NoSQL.

| Khái niệm | Vai trò |
|---|---|
| **Cosmos account** | Tài nguyên Azure quản lý endpoints, regions, authentication và các thiết lập dịch vụ |
| **Database** | Nhóm logic gồm các containers |
| **Container** | Đơn vị lưu items, cấu hình partition key, indexing, TTL và throughput ở phạm vi phù hợp |
| **Item** | JSON document với thuộc tính id và các field nghiệp vụ |
| **Logical partition** | Những items có cùng partition key value |
| **Physical partition** | Đơn vị hạ tầng chịu trách nhiệm lưu và phục vụ phần dữ liệu/throughput |
| **RU (Request Unit)** | Đơn vị đo chi phí tài nguyên của thao tác |
| **RU/s** | Tốc độ RU khả dụng theo cấu hình/cơ chế capacity |
| **429** | Request bị rate-limited/throttled khi thiếu năng lực tại thời điểm đó |

SDK và semantics cho MongoDB, Cassandra hoặc Gremlin có thể khác. Đừng áp đặt cấu hình hoặc phương thức Java SDK for NoSQL cho mọi API của Cosmos DB.

## 4. Kiến trúc ứng dụng điển hình

~~~mermaid
flowchart LR
    CLIENT[Web / Mobile] --> API[Java API trên AKS / App Service]
    API --> SDK[Azure Cosmos DB Java SDK]
    SDK --> NET[Private endpoint / Network / TLS]
    NET --> COSMOS[(Cosmos DB for NoSQL)]
    COSMOS --> MON[Azure Monitor]
    API --> APPMON[Application Insights]
    ID[Microsoft Entra ID / Managed identity] --> SDK
~~~

Đường dữ liệu cần được xem theo nhiều tầng:

1. Client gọi API, có deadline và retry policy riêng.
2. Java API sử dụng Cosmos DB SDK và connection pool/resource scheduling.
3. SDK định tuyến operations đến service/replica phù hợp.
4. Cosmos DB tính RU cho request.
5. Request thành công hoặc nhận lỗi như 429/400/404/409/412/503.
6. SDK có thể tự retry một số tình huống theo cấu hình.
7. Ứng dụng ghi business outcome và telemetry.

**Đo latency của Java API và latency request thực tế sau SDK retry riêng biệt.** Một lời gọi Java trả HTTP 200 sau ba lần retry của Cosmos DB vẫn có thể đã mất nhiều thời gian.

## 5. Model JSON và partition key đúng từ đầu

Ví dụ lưu mỗi đơn hàng thành một item:

~~~json
{
  "id": "ORD-1001",
  "tenantId": "tenant-42",
  "customerId": "C-20",
  "status": "CREATED",
  "amount": 125000,
  "schemaVersion": 1
}
~~~

Giả sử container được tạo với **partition key path** là **/tenantId**. Khi đó:

- Item có tenantId = tenant-42 thuộc logical partition tương ứng.
- Phần lớn point operations cần cung cấp **id và partition key value**.
- Các items có cùng tenantId có thể tập trung thành một hot logical partition nếu tenant này chiếm quá nhiều traffic.
- Query không biết tenantId có thể phải truy vấn nhiều partitions và tốn RU hơn.

### 5.1. Đừng nhầm partition key path và giá trị

- Partition key path của container: **/tenantId**.
- Partition key value của item: **tenant-42**.
- Java SDK truyền giá trị qua **new PartitionKey("tenant-42")**, không truyền chuỗi **"/tenantId"** cho point read.

### 5.2. Một id không nhất thiết duy nhất toàn container

Đối với một partitioned container, cặp **id + partition key value** xác định item theo semantics của mô hình. Hai tenants khác nhau có thể dùng cùng id trong những thiết kế phù hợp. Vì vậy, đọc item chỉ theo id mà không biết partition key là một lỗi thiết kế phổ biến.

### 5.3. Chọn key theo access pattern

| Workload | Partition key gợi ý | Cần lưu ý |
|---|---|---|
| Đơn hàng multi-tenant | /tenantId | Tenant lớn có thể nóng |
| Giỏ hàng | /customerId hoặc khóa ghép do ứng dụng thiết kế | Xem số carts/customer và điểm nóng |
| IoT telemetry | /deviceId nếu tải từng device phù hợp | Một device rất nóng có thể là bottleneck |
| User profile | /userId | Point reads rẻ khi biết id và userId |
| Dữ liệu cực lệch tải | Synthetic hoặc hierarchical key khi tính năng hỗ trợ | Thiết kế queries, hot keys và dữ liệu cũ |

Không có partition key tối ưu cho mọi ứng dụng. Thử phân phối tải với dữ liệu dự kiến, không chỉ chọn theo tên field có vẻ tự nhiên.

## 6. Request Unit và request charge là gì?

**Request Unit (RU)** là thước đo tài nguyên Cosmos DB cần để thực hiện thao tác: CPU, I/O và các thành phần liên quan. Mỗi request tiêu thụ một **request charge** có thể đo được.

Những thao tác khác nhau tiêu thụ lượng RU khác nhau:

- Point read của một item nhỏ với id và partition key thường hiệu quả.
- Query lọc thiếu partition key có thể cần đọc nhiều partitions.
- Query scan nhiều documents có thể tốn RU lớn hơn chỉ lấy một item.
- Ghi item lớn hoặc cập nhật các fields được index có thể tăng charge.
- Độ phức tạp query, kết quả, indexing policy và dữ liệu ảnh hưởng RU.

Để hiểu xu hướng, giả sử phép thử đo được:

| Thao tác minh họa | Request charge đo được (ví dụ) |
|---|---:|
| Point read item nhỏ | 1 RU |
| Tạo item | 5 RU |
| Query trong một partition | 12 RU |
| Query qua nhiều partitions | 80 RU |

**Các số là ví dụ minh họa, không phải đơn giá hoặc charge bảo đảm của dịch vụ.** Dùng **response.getRequestCharge()** trên request thực để biết giá trị.

### 6.1. RU/s là ngân sách tốc độ

Nếu container được provision 1.000 RU/s và workload trung bình cần 5 RU/request, mức thông lượng lý tưởng gần 200 requests/giây, giả sử tải phân bố đều và không có bottleneck khác:

\[
\text{Requests/second tối đa theo RU}
\approx \frac{\text{RU/s khả dụng}}{\text{RU/request trung bình}}
\]

Nhưng phép chia này chưa tính peaks, physical partitions, hot keys, multi-region, consistency, payload variation, retries hoặc giới hạn kết nối.

## 7. Provisioned throughput, autoscale và serverless

Ba mô hình capacity cần cân nhắc tùy tính năng/tier/region hiện hành:

| Mô hình | Ý tưởng | Hợp khi |
|---|---|---|
| **Manual provisioned throughput** | Cấp lượng RU/s cấu hình | Tải tương đối ổn định và dự báo được |
| **Autoscale throughput** | Điều chỉnh năng lực trong dải được hỗ trợ, tới mức tối đa đã đặt | Tải biến thiên mạnh theo giờ/sự kiện |
| **Serverless** | Tính theo mức tiêu thụ request trong phạm vi tính năng/giới hạn | Workload thấp hoặc ngắt quãng, ít yêu cầu always-on throughput |

### 7.1. Autoscale không có nghĩa vô hạn

Autoscale có giới hạn maximum RU/s, cơ chế cấp capacity và giới hạn theo physical partition. Nếu workload vượt ngưỡng hoặc dồn vào một partition nóng, 429 vẫn có thể xảy ra.

### 7.2. Serverless cũng có throttling

Serverless không phải một lựa chọn cho phép gửi lượng request tùy ý trong mọi thời điểm. Cần kiểm tra giới hạn RU/s thực tế, storage và vùng/khả năng hỗ trợ trước khi chọn.

### 7.3. Database-level và container-level throughput

Throughput có thể được cấu hình ở phạm vi container hoặc chia sẻ trong database theo mô hình supported. Khi nhiều containers chia sẻ database throughput, chúng có thể ảnh hưởng nhau.

### 7.4. Chọn mô hình theo bài toán

- Web API hoạt động đều, có SLO: đo RU và chọn manual/autoscale phù hợp.
- Traffic flash sale: autoscale và backpressure; cần kiểm tra giới hạn peak.
- Batch jobs không thường xuyên: đánh giá serverless hoặc giới hạn throughput/cost theo điều kiện hỗ trợ.
- Multi-tenant có tenant cực lớn: giải quyết partition skew ngay cả khi tăng tổng RU/s.

## 8. Logical partition, physical partition và hot partition

Một **logical partition** gồm các items có cùng partition key value. Hạ tầng chia dữ liệu thành **physical partitions**, mỗi physical partition có giới hạn tài nguyên và phần RU/s được phân phối.

~~~mermaid
flowchart TD
    APP[Requests từ Java SDK] --> PK{Partition key}
    PK --> A[tenant-42 - logical partition]
    PK --> B[tenant-17 - logical partition]
    PK --> C[tenant-88 - logical partition]
    A --> P1[(Physical partition A)]
    B --> P2[(Physical partition B)]
    C --> P2
~~~

Đây là sơ đồ khái niệm. Cách bố trí physical partitions được nền tảng quản lý và có thể thay đổi khi dữ liệu/capacity tăng.

### 8.1. Vì sao tăng tổng RU/s đôi khi chưa giải quyết 429?

Giả sử 80% writes đều đến một tenant. Dù account/container có nhiều RU/s, giới hạn ở phạm vi physical partition hoặc logical hot key có thể khiến tenant ấy bị throttled trong khi phần khác chưa sử dụng hết capacity.

### 8.2. Dấu hiệu hot partition

- 429 xuất hiện chủ yếu ở một tenant/key.
- RU utilization theo physical partition không đều nếu telemetry hỗ trợ.
- Tăng RU/s tổng không cải thiện tương xứng.
- Một key có lượng writes/queries vượt trội.
- Latency của các tenants khác vẫn tốt.

### 8.3. Phương án xử lý

1. Đo RU theo thao tác và key.
2. Kiểm tra chọn partition key có quá thô không.
3. Phân tán workload theo business subkey hoặc synthetic key nếu truy vấn cho phép.
4. Sử dụng tính năng hierarchical partition keys khi tương thích và hợp mô hình.
5. Tránh một transaction nghiệp vụ cần atomicity xuyên nhiều logical partitions nếu kiến trúc không đáp ứng.
6. Lập kế hoạch migration khi thay partition key path vì không thể đơn giản đổi nó trên container có dữ liệu đang dùng.

## 9. Chuẩn bị dự án Java và SDK v4

Bài này giả định có dự án Java đã thiết lập Maven/Gradle và dùng **Azure Cosmos DB Java SDK v4**, artifact **com.azure:azure-cosmos**. Nếu dùng Microsoft Entra identity, cần thêm **com.azure:azure-identity**.

Ví dụ Maven dependencies:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-cosmos</artifactId>
    <version>YOUR_COMPATIBLE_4_X_VERSION</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>YOUR_COMPATIBLE_IDENTITY_VERSION</version>
  </dependency>
</dependencies>
~~~

Thay placeholders bằng các phiên bản stable tương thích với JDK và SDK policy của dự án. Có thể quản lý versions bằng BOM được tổ chức chấp thuận. Không hardcode một phiên bản cũ rồi giả định an toàn mãi.

### 9.1. Các lớp thường dùng

| Lớp | Chức năng |
|---|---|
| **CosmosClientBuilder** | Khởi tạo đồng bộ/bất đồng bộ client |
| **CosmosClient** | Client đồng bộ sử dụng lại cho nhiều requests |
| **CosmosAsyncClient** | Client bất đồng bộ/reactive |
| **CosmosDatabase** | Đại diện database |
| **CosmosContainer** | Thực hiện CRUD/query trên container |
| **PartitionKey** | Giá trị partition key của request |
| **CosmosItemResponse** | Status, item, request charge, diagnostics |
| **CosmosException** | Lỗi HTTP/service và metadata |
| **CosmosQueryRequestOptions** | Tùy chọn query |
| **CosmosPagedIterable** | Kết quả query có phân trang |

### 9.2. Không tạo client mỗi request

CosmosClient được thiết kế để **tái sử dụng trong ứng dụng**. Tạo client mới trên mọi HTTP request tốn tài nguyên, gây connection churn và làm tăng độ trễ.

### 9.3. Không viết keys vào source

Với demo có thể dùng account key được truyền từ secret store ở runtime; production ưu tiên Microsoft Entra data-plane RBAC và managed identity nếu kiến trúc/SDK hỗ trợ.

## 10. Authentication, Microsoft Entra ID và data-plane RBAC

Có hai lựa chọn phổ biến:

1. **Account key:** đơn giản cho lab nhưng có quyền lớn và cần kiểm soát nghiêm ngặt.
2. **Microsoft Entra token credential:** phù hợp identity-based access, cần role assignment trên **Cosmos DB SQL data plane** và quyền phù hợp.

### 10.1. Khởi tạo Java client bằng Entra credential

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;

public final class CosmosConnection {
    public static CosmosClient connect() {
        String endpoint = System.getenv("COSMOS_ENDPOINT");
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException("COSMOS_ENDPOINT missing");
        }

        return new CosmosClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }
}
~~~

**Lưu ý:** đây là ví dụ cho SDK v4 có hỗ trợ TokenCredential. Role assignments và quyền cần tồn tại trước khi truy cập; một Azure ARM Reader/Contributor không mặc nhiên cho phép đọc/ghi items.

### 10.2. Data-plane role và management-plane role

- **Azure RBAC management:** tạo/sửa resources và settings.
- **Cosmos DB for NoSQL data-plane RBAC:** cho phép đọc/ghi items/query theo built-in/custom data roles tại scope phù hợp.
- **SDK identity:** managed identity, Workload Identity hoặc developer credential theo môi trường.

Ví dụ quyền dữ liệu có thể dùng **Cosmos DB Built-in Data Reader** hoặc **Cosmos DB Built-in Data Contributor** (tên role theo mô hình NoSQL RBAC). Cấp scope tối thiểu; không cấp account Owner để chữa lỗi 403 một cách tùy tiện.

### 10.3. Managed identity trên AKS/App Service/Functions

Các runtime có thể sử dụng managed identity hoặc AKS Workload Identity. Kiểm tra đúng tenant, client ID, token, role scope và thời gian propagation. DefaultAzureCredential có thể chọn credential khác nhau giữa local và cloud, cần log loại identity an toàn khi debug.

## 11. Khởi tạo CosmosClient đồng bộ

Trong lab, nếu tổ chức chưa cấu hình Entra identity, bạn có thể dùng key từ environment hoặc secret store:

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.ConsistencyLevel;

public final class CosmosClientFactory {
    private CosmosClientFactory() {}

    public static CosmosClient build() {
        String endpoint = require("COSMOS_ENDPOINT");
        String key = require("COSMOS_KEY");

        return new CosmosClientBuilder()
            .endpoint(endpoint)
            .key(key)
            .consistencyLevel(ConsistencyLevel.SESSION)
            .buildClient();
    }

    private static String require(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing " + name);
        }
        return value;
    }
}
~~~

**Account key là bí mật**: không đặt COSMOS_KEY vào file commit, container image hay command/logs công khai. Ví dụ dùng key chỉ để giới thiệu SDK. Production nên ưu tiên identity-based access nếu được hỗ trợ và đáp ứng yêu cầu.

### 11.1. Đóng client đúng vòng đời

Tạo một client cho ứng dụng/bean và đóng khi ứng dụng tắt:

~~~java
CosmosClient client = CosmosClientFactory.build();
try {
    // Thực hiện nghiệp vụ...
} finally {
    client.close();
}
~~~

Không đóng client sau mỗi lời gọi database trong một ứng dụng có nhiều requests.

### 11.2. Đồng bộ và bất đồng bộ

- **CosmosClient:** API sync, dễ học, lời gọi block thread.
- **CosmosAsyncClient:** API reactive với Reactor, thích hợp pipeline I/O-heavy khi vận hành nonblocking đúng cách.

Không chọn async chỉ vì nó có chữ “nhanh”: concurrency không giới hạn có thể làm quá tải SDK/ứng dụng hoặc Cosmos DB.

## 12. Database/container và vai trò của infrastructure provisioning

Trong production, **tạo database, container, indexing policy, partition key và throughput** thường thuộc quy trình IaC/management được phê duyệt. Runtime app không nên mỗi lần khởi động đều gọi create database/container hoặc tự đổi throughput.

Ví dụ truy cập resources đã tồn tại:

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.CosmosDatabase;

public final class CosmosResources {
    public static CosmosContainer orders(CosmosClient client) {
        CosmosDatabase database = client.getDatabase("shopdb");
        return database.getContainer("orders");
    }
}
~~~

Việc lấy proxy object không chắc đã kiểm tra được resource/permissions ngay; lỗi có thể xuất hiện ở operation thật.

### 12.1. Cấu hình container quan trọng

- Partition key path, ví dụ **/tenantId**.
- Indexing policy và các fields được index.
- Unique key policy nếu ứng dụng cần.
- TTL nếu lưu dữ liệu có vòng đời xác định.
- Provisioned throughput/autoscale hoặc chế độ capacity được chọn.
- Regions và consistency settings của account.

### 12.2. Sai partition key thường phải migrate

Partition key path là quyết định kiến trúc quan trọng khi tạo container; không nên giả định có thể sửa tại chỗ đơn giản cho container đang có dữ liệu. Khi cần đổi, thường phải lập kế hoạch tạo container mới và chuyển dữ liệu.

## 13. Java POJO và serialization

SDK for NoSQL lưu documents dạng JSON. Một Java POJO đơn giản:

~~~java
public class OrderDocument {
    public String id;
    public String tenantId;
    public String customerId;
    public String status;
    public long amount;
    public int schemaVersion;

    public OrderDocument() { }

    public OrderDocument(String id, String tenantId, long amount) {
        this.id = id;
        this.tenantId = tenantId;
        this.amount = amount;
        this.status = "CREATED";
        this.schemaVersion = 1;
    }
}
~~~

Các fields public giúp ví dụ dễ hiểu; trong dự án thật có thể dùng getters/setters, immutable models, validation và Jackson annotations phù hợp.

### 13.1. id và partition key phải thống nhất

Nếu container partition key path là **/tenantId**, item cần field tenantId có kiểu và giá trị đúng. Gửi giá trị PartitionKey khác với tenantId trong body có thể gây lỗi.

### 13.2. Chọn định dạng tiền an toàn

Ví dụ dùng **long amount** đại diện số tiền ở đơn vị nhỏ nhất theo quy ước nghiệp vụ; không dùng floating-point để lưu giá trị tài chính cần chính xác. Có thể dùng decimal serialization khi contract hỗ trợ phù hợp.

### 13.3. Schema version

Có **schemaVersion** để hỗ trợ quá trình nâng cấp consumers, migration và phân biệt document cũ/mới. Cosmos DB linh hoạt schema không có nghĩa ứng dụng không cần hợp đồng dữ liệu.

## 14. CRUD Java: create, point read, upsert và delete

Giả sử container **orders** có partition key path **/tenantId**.

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

public final class OrdersStore {
    private final CosmosContainer container;

    public OrdersStore(CosmosContainer container) {
        this.container = container;
    }

    public void create(OrderDocument order) {
        CosmosItemResponse<OrderDocument> response =
            container.createItem(
                order,
                new PartitionKey(order.tenantId),
                new CosmosItemRequestOptions());

        System.out.println(
            "create RU=" + response.getRequestCharge());
    }

    public OrderDocument read(String id, String tenantId) {
        CosmosItemResponse<OrderDocument> response =
            container.readItem(
                id,
                new PartitionKey(tenantId),
                OrderDocument.class);

        System.out.println(
            "read RU=" + response.getRequestCharge());

        return response.getItem();
    }

    public void delete(String id, String tenantId) {
        container.deleteItem(
            id,
            new PartitionKey(tenantId),
            new CosmosItemRequestOptions());
    }
}
~~~

### 14.1. Create khác upsert

- **createItem:** tạo mới; có thể trả **409 Conflict** nếu item có cùng unique identity đã tồn tại.
- **upsertItem:** tạo mới nếu chưa có, hoặc cập nhật nếu có, theo semantics của SDK/API.
- **replaceItem:** thay một item hiện có, có thể kết hợp ETag để kiểm tra phiên bản.
- **deleteItem:** xóa theo id và partition key.

Không dùng upsert tùy tiện cho xử lý retry nếu nghiệp vụ phải phát hiện duplicate thay vì ghi đè dữ liệu.

### 14.2. Point read thường hiệu quả hơn query bằng id

Nếu đã có **id + partition key**, dùng **readItem** thay vì query SQL tìm id. Nó giảm query planning/cross-partition work và thường có request charge thấp hơn.

### 14.3. Response không tự chứng minh nghiệp vụ đúng

HTTP 200/201 chứng minh Cosmos operation thành công, nhưng không chứng minh toàn bộ workflow thanh toán, email hoặc Service Bus publish đã hoàn tất. Cần transaction/outbox/idempotency ở tầng nghiệp vụ.

## 15. Optimistic concurrency với ETag

Nhiều clients có thể đọc và thay đổi cùng một item. Nếu chỉ replace không có điều kiện, một client có thể ghi đè thay đổi của client khác.

Cosmos DB cung cấp **ETag** và conditional writes để phát hiện dữ liệu đã bị thay đổi.

Quy trình:

1. Đọc item và ETag.
2. Thực hiện business validation trên snapshot.
3. Replace với **If-Match ETag**.
4. Nếu item đổi trước khi replace, nhận **412 Precondition Failed** và xử lý conflict.

Ví dụ:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

public void updateStatus(CosmosContainer container,
                         String id,
                         String tenantId,
                         String newStatus) {

    PartitionKey pk = new PartitionKey(tenantId);

    CosmosItemResponse<OrderDocument> current =
        container.readItem(id, pk, OrderDocument.class);

    OrderDocument order = current.getItem();
    order.status = newStatus;

    CosmosItemRequestOptions options =
        new CosmosItemRequestOptions();
    options.setIfMatchETag(current.getETag());

    container.replaceItem(order, id, pk, options);
}
~~~

### 15.1. 412 không phải 429

**412** là optimistic concurrency conflict, không phải thiếu RU/s. Thử lại bằng cách đọc item mới và đánh giá lại logic nghiệp vụ, không lặp replace mù.

### 15.2. Conditional writes và idempotency

ETag giúp tránh lost updates nhưng không thay thế business idempotency key. Một operation “trừ tiền” chạy hai lần có thể vẫn sai nếu mỗi lần retry dùng ETag mới mà không kiểm tra operation ID.

## 16. Query với partition key và parameters

Ví dụ query các đơn hàng của một tenant:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosQueryRequestOptions;
import com.azure.cosmos.models.PartitionKey;
import com.azure.cosmos.models.SqlParameter;
import com.azure.cosmos.models.SqlQuerySpec;

import java.util.Arrays;

CosmosQueryRequestOptions options =
    new CosmosQueryRequestOptions()
        .setPartitionKey(new PartitionKey("tenant-42"));

SqlQuerySpec query = new SqlQuerySpec(
    "SELECT * FROM c WHERE c.tenantId = @tenant AND c.status = @status",
    Arrays.asList(
        new SqlParameter("@tenant", "tenant-42"),
        new SqlParameter("@status", "CREATED")
    )
);

container.queryItems(
    query, options, OrderDocument.class
).forEach(order -> {
    System.out.println(order.id);
});
~~~

### 16.1. Query không biết partition key

Nếu không chỉ định partition key, query có thể phải fan-out tới nhiều partitions. Điều này có thể tăng RU, latency và cơ hội bị throttled. Có những workloads phân tích cần cross-partition query, nhưng phải đo và dự toán.

### 16.2. Dùng parameterized queries

Không nối input người dùng trực tiếp vào SQL text. SqlQuerySpec với SqlParameter giúp xử lý dữ liệu có kiểm soát hơn.

### 16.3. Không SELECT * theo thói quen

Chỉ lấy các fields cần thiết, thêm index phù hợp và phân trang. Response body lớn tạo thêm network overhead và có thể tăng request charge.

## 17. Đọc request charge và diagnostics của SDK

Để tối ưu throttling, cần đo **RU/operation** thay vì chỉ đếm số request.

~~~java
import com.azure.cosmos.models.CosmosItemResponse;

CosmosItemResponse<OrderDocument> response =
    container.readItem(
        "ORD-1001",
        new com.azure.cosmos.models.PartitionKey("tenant-42"),
        OrderDocument.class);

double charge = response.getRequestCharge();
int status = response.getStatusCode();

System.out.println(
    "Cosmos response status=" + status + " RU=" + charge);
~~~

Các SDK response khác nhau (item, query page, stored procedures...) có cách truy cập request charge và diagnostics phù hợp. Với query phân trang, tổng RU của **cả query** là tổng charge của các pages được thực sự đọc, không chỉ một kết quả đầu tiên.

### 17.1. Cosmos diagnostics

SDK có cơ chế diagnostics để phân tích latency, backend requests, regions, retry và network behavior theo thông tin khả dụng. Có thể ghi diagnostics khi một request vượt latency threshold.

**Không log toàn bộ diagnostics ở throughput cao** nếu chưa kiểm tra volume, overhead và thông tin nhạy cảm. Dùng sampling/threshold và correlation ID.

### 17.2. Activity ID

Service responses/errors có thể kèm **activity ID** để truy vết và hỗ trợ điều tra. Cần giữ activity ID an toàn trong logs/incident, nhưng không coi nó là business idempotency key.

### 17.3. Ba thước đo riêng

- **RU/request:** chi phí hiệu quả từng operation.
- **Requests/second:** tải và throughput thực.
- **p95/p99 latency:** trải nghiệm ứng dụng, kể cả thời gian retry.

Tối ưu một số đo mà bỏ hai số còn lại có thể gây kết quả sai.

## 18. Lỗi HTTP 429: điều gì xảy ra?

Khi một request đòi hỏi RU vượt mức capacity đang khả dụng tại phạm vi liên quan, Cosmos DB có thể trả **HTTP 429 Too Many Requests**. Server thường cung cấp gợi ý khoảng chờ trước khi retry như **Retry-After** hoặc header **x-ms-retry-after-ms** tùy protocol/SDK.

~~~mermaid
sequenceDiagram
    participant A as Java application
    participant S as Cosmos DB Java SDK
    participant C as Azure Cosmos DB
    A->>S: CreateItem
    S->>C: Request cần RU
    C-->>S: 429 + retry-after
    S->>S: Chờ theo retry policy
    S->>C: Retry request
    C-->>S: 201 + request charge
    S-->>A: Success response
~~~

### 18.1. 429 không luôn chứng minh hệ thống hỏng

Trong một hệ thống tối ưu cost, một tỷ lệ 429 nội bộ có thể được SDK retry thành công mà khách hàng không nhìn thấy lỗi. Nhưng **429 kéo dài, retries quá nhiều hoặc latency vượt SLO** là vấn đề cần giải quyết.

### 18.2. 429 vẫn có thể đến từ hot partition

Nếu một logical partition nóng, chỉ tăng tổng throughput có thể không phân phối đủ tài nguyên tới partition đó do giới hạn vật lý hoặc thiết kế key. Phải xem metrics ở cấp partition và phân phối workload.

### 18.3. Khi nào client thấy CosmosException 429?

Nếu retries của SDK hết budget/thời gian, request bị cancel hoặc chính sách không retry tình huống đó, ứng dụng có thể nhận CosmosException status 429. Đừng ngộ nhận mọi 429 ban đầu đều lộ trực tiếp cho Java code.

## 19. Automatic retries của Cosmos DB Java SDK

Java SDK v4 có cơ chế retry nội bộ cho những tình huống như throttling theo chính sách và các giới hạn được triển khai trong phiên bản SDK. Mục tiêu là tự chờ theo tín hiệu server và phục hồi từ những đợt RU exhaustion ngắn.

**Các điểm quan trọng:**

- SDK có thể retry một số requests mà application code chỉ thấy response cuối cùng.
- Retry có thể làm **tăng end-to-end latency**.
- SDK retry không thay thế việc nâng throughput hoặc sửa hot partition.
- Giới hạn số lần và tổng thời gian retry phụ thuộc SDK version/configuration; không giả định một con số mặc định đúng cho mọi dự án.
- Không bọc mọi SDK call trong vòng lặp retry vô hạn ở tầng ứng dụng.

### 19.1. Tránh double-retry

Nếu SDK đã retry nhiều lần, sau đó application retry nguyên operation thêm nhiều vòng và API gateway cũng retry HTTP request, tổng số requests có thể tăng rất lớn.

Ví dụ tư duy:

~~~text
SDK retry budget
     x
Application retry budget
     x
HTTP client retry budget
     =
Nhiều attempt hơn tưởng tượng
~~~

Cần xác định tầng nào chịu trách nhiệm retry và giới hạn tổng latency/attempts.

### 19.2. Retry-After là tín hiệu điều tiết

Khi tự viết retry cho tình huống SDK trả 429 ra ứng dụng, ưu tiên thông tin **retry-after** do service cung cấp thay vì gửi lại ngay. Thêm jitter và deadline để tránh các workers đồng loạt bùng nổ.

### 19.3. Không ngủ vô hạn trong Java request thread

Dùng backoff bounded trong ứng dụng sync khi phù hợp hoặc scheduler/nonblocking delay trong reactive pipeline. Không dùng Thread.sleep nhiều phút trong request handler để giải quyết thiếu throughput lâu dài.

## 20. Đọc và phân loại CosmosException

Một bộ xử lý lỗi nên phân loại status:

| Status | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| **400 Bad Request** | Payload/query/partition key hoặc request sai | Sửa đầu vào/code, không retry mù |
| **401 Unauthorized** | Credential/token không hợp lệ hoặc hết hạn | Kiểm tra authentication |
| **403 Forbidden** | Không có quyền hoặc cấu hình policy | Kiểm tra data RBAC/firewall/permissions theo substatus |
| **404 Not Found** | Item/container/database không tồn tại theo request | Xác minh id + partition key + resource |
| **409 Conflict** | Tạo item đã tồn tại/unique conflict | Kiểm tra idempotency |
| **412 Precondition Failed** | ETag không khớp | Đọc mới rồi xử lý conflict |
| **429 Too Many Requests** | RU/capacity throttling | Retry-after, giảm tải/tối ưu RU |
| **408/503** | Timeout/service unavailable trong điều kiện cụ thể | Bounded retry, kiểm tra service/network |
| **5xx khác** | Lỗi server hoặc trung gian | Phân loại theo SDK docs và policy |

Ví dụ:

~~~java
import com.azure.cosmos.CosmosException;

try {
    store.create(order);
} catch (CosmosException ex) {
    int status = ex.getStatusCode();

    if (status == 429) {
        System.err.println("Cosmos DB throttling: review RU and latency");
    } else if (status == 409) {
        System.err.println("Document already exists: check idempotency");
    } else {
        System.err.println("Cosmos operation failed, status=" + status);
    }

    throw ex; // Caller quyết định mapping lỗi phù hợp.
}
~~~

Trong production, không map tất cả CosmosException thành HTTP 500. Ví dụ 404 có thể là nghiệp vụ “không tìm thấy”, 409 là conflict, 429 có thể cần trả 503/429 hoặc phản hồi theo API contract và deadline, có telemetry và retry hints cho caller.
## 21. Application-level retry: giới hạn số lần và tôn trọng Retry-After

SDK thường đã thực hiện retry cho một số lỗi 429 theo chính sách nội bộ. Vì vậy, **retry ở tầng ứng dụng nên là lớp ngoài có giới hạn**, chỉ khi SDK vẫn trả lỗi và còn deadline. Không tạo vòng lặp vô hạn.

Ví dụ Java sync sau chỉ dành cho **point read idempotent**:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.CosmosException;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class SafeRead {
    public static OrderDocument readWithBudget(
            CosmosContainer container,
            String id,
            String tenantId) throws InterruptedException {

        int maxOuterAttempts = 3;
        long deadline = System.nanoTime()
            + Duration.ofSeconds(5).toNanos();

        for (int attempt = 1; attempt <= maxOuterAttempts; attempt++) {
            try {
                CosmosItemResponse<OrderDocument> result =
                    container.readItem(
                        id,
                        new PartitionKey(tenantId),
                        OrderDocument.class);
                return result.getItem();

            } catch (CosmosException ex) {
                if (ex.getStatusCode() != 429
                        || attempt == maxOuterAttempts) {
                    throw ex;
                }

                long remainingMs =
                    Duration.ofNanos(Math.max(
                        0, deadline - System.nanoTime()))
                        .toMillis();

                if (remainingMs <= 0) {
                    throw ex;
                }

                Duration retryAfter = ex.getRetryAfterDuration();
                long waitMs = retryAfter == null
                    ? 250
                    : Math.max(0, retryAfter.toMillis());

                long jitterMs =
                    ThreadLocalRandom.current().nextLong(0, 101);

                long delayMs =
                    Math.min(remainingMs, waitMs + jitterMs);

                if (delayMs <= 0) {
                    throw ex;
                }

                Thread.sleep(delayMs);
            }
        }

        throw new IllegalStateException("Retry budget exhausted");
    }
}
~~~

### 21.1. Những điều cần hiểu

- **getRetryAfterDuration()** được sử dụng theo API SDK v4 thích hợp; kiểm tra version khi đưa vào dự án.
- SDK đã có retry; đoạn code chỉ retry **sau khi SDK vẫn trả 429 ra ngoài**.
- Deadline 5 giây trong ví dụ chỉ được kiểm tra **giữa các calls**; nó không tự hủy một SDK call đang block. Production cần operation/client timeout và cancellation ở tầng thích hợp.
- Thread.sleep chiếm một thread; tránh chạy hàng nghìn retries ngủ đồng thời trong HTTP handlers.
- Demo chỉ retry **read**. Retry write phải đánh giá idempotency và khả năng write trước đó đã commit.

### 21.2. Retry-After và jitter

Khi server đưa gợi ý chờ, hãy tôn trọng để giảm tải. Jitter giúp các workers không đồng thời retry đúng một thời điểm. Nhưng retry không thay thế capacity hoặc điều tiết tốc độ gửi.

### 21.3. Không retry mọi status

400 do query sai, 403 do quyền, 409 do duplicate và 412 do ETag conflict cần cách xử lý riêng; lặp lại cùng request vô hạn không sửa được root cause.

## 22. Write retry và tính idempotent

Giả sử:

~~~text
Client gửi CREATE Order id=ORD-1001
  -> Cosmos DB ghi thành công
  -> Mạng mất trước khi client nhận response
  -> Client tưởng lỗi và gửi lại
~~~

Nếu mỗi lần retry sinh một **id mới**, có thể tạo hai đơn hàng.

### 22.1. Giữ business operation ID

Sử dụng cặp **id + partition key** cố định và một operationId để xác định cùng nghiệp vụ. Nếu create trả **409**, đọc lại item và xác minh dữ liệu/operationId. Chỉ coi duplicate là thành công khi thực sự cùng operation đã được commit.

### 22.2. Upsert không luôn an toàn

Upsert có thể ghi đè trạng thái mới hơn khi một request cũ được retry. Với nghiệp vụ quan trọng, dùng **ETag/If-Match**, business version và quy tắc chuyển trạng thái.

### 22.3. Ghi Cosmos DB rồi gửi Service Bus

Hai thao tác không tự nằm trong một transaction atomic. Cân nhắc **transactional outbox**, change feed hoặc cơ chế phát sự kiện có checkpoint/idempotency để giảm nguy cơ dữ liệu đã commit nhưng message không được phát.

## 23. CosmosAsyncClient và Reactor: bất đồng bộ có giới hạn

**CosmosAsyncClient** thích hợp với Java application dùng reactive programming, nhưng không tự động tiết kiệm RU hoặc tránh 429. Nếu flatMap không có giới hạn, ứng dụng có thể gửi quá nhiều operations đồng thời.

Ví dụ reactive pipeline:

~~~java
import com.azure.cosmos.CosmosAsyncClient;
import com.azure.cosmos.CosmosAsyncContainer;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.PartitionKey;
import reactor.core.publisher.Flux;

import java.util.List;

CosmosAsyncClient client = new CosmosClientBuilder()
    .endpoint(System.getenv("COSMOS_ENDPOINT"))
    .credential(
        new com.azure.identity.DefaultAzureCredentialBuilder().build())
    .buildAsyncClient();

CosmosAsyncContainer container =
    client.getDatabase("shopdb").getContainer("orders");

List<OrderDocument> orders = loadOrdersFromApprovedSource();

Flux.fromIterable(orders)
    .flatMap(order ->
        container.createItem(
            order,
            new PartitionKey(order.tenantId),
            new CosmosItemRequestOptions()
        ).doOnNext(result ->
            System.out.println("RU=" + result.getRequestCharge())
        ),
        8
    )
    .blockLast();

client.close();
~~~

**loadOrdersFromApprovedSource() là placeholder**, không phải hàm sẵn có. Đoạn code minh họa cách ghép SDK với Reactor; cần xây dựng nguồn dữ liệu, per-item error handling và lifecycle đúng trước khi chạy.

### 23.1. Vì sao flatMap concurrency = 8?

Đây là giới hạn **số subscriptions/operations cùng lúc** trong đoạn pipeline, không phải giá trị mặc định được Azure khuyến nghị. Điều chỉnh theo RU budget, độ trễ và kích thước items.

### 23.2. Tránh block trong event loop

blockLast có thể hợp lý ở một batch main/CLI. Không gọi block trên Reactor event-loop của HTTP reactive service khi có thể tránh.

### 23.3. Reactive error semantics

Nếu một operation thất bại, Flux có thể kết thúc sớm. Production cần thiết kế xử lý lỗi theo item, retry/quarantine có giới hạn và không làm mất các records còn lại. Không tự áp dụng onErrorContinue mà không hiểu hiệu ứng.

## 24. Concurrency không phải throughput

Ví dụ có 10 AKS Pods, mỗi Pod tạo 100 Cosmos requests in-flight:

\[
10 \times 100 = 1.000\text{ requests đang chạy}
\]

Nếu database chỉ có capacity cho một số lượng nhỏ hơn về RU/s theo charge hiện tại, một nghìn requests in-flight có thể tạo rất nhiều 429 mà không tăng số requests thành công tương ứng.

### 24.1. Dấu hiệu

- 429 tăng khi tăng số Pods/threads.
- p99 tăng nhưng throughput thành công gần như giữ nguyên.
- SDK retries kéo dài.
- JVM memory/GC và pending requests tăng.
- API timeout hoặc backlog cao.

### 24.2. Hướng xử lý

- Giảm per-Pod concurrency.
- Dùng rate limiter theo RU budget.
- Đưa batch việc vào queue và điều tiết workers.
- Cân nhắc tăng RU/s sau khi đo.
- Chia tenant hot, tối ưu partition key.
- Thiết kế deadline và xử lý quá tải có kiểm soát.

### 24.3. Semaphore trong một Pod không giới hạn cả cluster

Semaphore với 20 permits trong mỗi Pod vẫn cho phép 30 Pods có tổng 600 operations. Với RU capacity chia sẻ, cần rate limiting/coordination theo toàn ứng dụng hoặc theo tenant/workload.

## 25. Backpressure: concurrency limit, rate limit và queue budget

**Backpressure** giữ tốc độ gửi tới Cosmos DB trong khoảng phù hợp với năng lực thực.

| Cơ chế | Ý nghĩa | Tác dụng |
|---|---|---|
| Concurrency limit | Tối đa bao nhiêu requests đang hoạt động | Hạn chế memory/threads/in-flight |
| Rate limit | Tối đa requests/giây hoặc RU dự kiến/giây | Tránh vượt sustained RU/s |
| Queue capacity | Tối đa số công việc chờ | Tránh queue vô hạn trong RAM |
| Timeout/deadline | Giới hạn thời gian một request tồn tại | Không giữ client chờ quá SLO |
| Fairness | Chia tài nguyên cho tenants/workloads | Tránh tenant lớn gây đói tải |

### 25.1. Ví dụ token bucket theo RU

Giả sử container được provision 2.000 RU/s, cần dành headroom 20%:

~~~text
RU budget dùng cho API: 1.600 RU/s
Point read đo được: 2 RU/read
Write đo được: 8 RU/write

Nếu chỉ có reads:  ~800 reads/s
Nếu chỉ có writes: ~200 writes/s
~~~

Đây là ước lượng giả định. Thực tế RU/operation biến thiên theo kích thước document, indexing, consistency và query. Dùng request charge đo được và cập nhật rate limiter.

### 25.2. Concurrency thấp vẫn có thể gửi request quá nhanh

Nếu mỗi operation nhanh, concurrency 8 vẫn có thể đẩy hàng nghìn requests/giây. Rate limit bảo vệ RU/s khác với concurrency limit bảo vệ in-flight operations.

### 25.3. Tránh overload trong retry

Khi server trả 429, giảm tốc hoặc tạm ngừng phát requests mới, không chỉ thêm nhiều requests vào local queue. Tránh retry storm và queue growth không giới hạn.

## 26. Bulk operations: hiệu năng và tính đúng

Nhập hàng triệu documents thường cần async/bulk capabilities được SDK version hỗ trợ. Nhưng bulk cũng phải quản lý:

- Input chunks và memory pressure.
- Số operations song song.
- RU budget và retry count.
- Kết quả thành công/thất bại từng item.
- Idempotency của writes.
- Checkpoint tiến độ import.
- Throttling theo physical/logical partitions.
- Tác động lên API đang dùng chung throughput.

### 26.1. Bulk không mặc định atomic

Một đợt import có thể thành công một phần. Đừng ghi “batch complete” chỉ vì một số writes đã thành công.

### 26.2. Transactional batch khác bulk

Cosmos DB hỗ trợ transactional batch với những ràng buộc trong **cùng logical partition**, theo API và giới hạn của dịch vụ. Không sử dụng như transaction xuyên tất cả partition keys.

### 26.3. SDK versions có API khác nhau

Tính năng bulk hoặc tính chất concurrency có thể thay đổi giữa SDK versions. Cần xác nhận docs/SDK release notes của phiên bản dự án, đo actual RU/throughput thay vì copy tùy chọn tuning từ thư viện legacy.

## 27. Pagination và tổng request charge của query

Query có thể trả nhiều pages. **Tổng RU của một query không phải RU của page đầu**.

Ví dụ:

~~~java
import com.azure.cosmos.models.CosmosQueryRequestOptions;
import com.azure.cosmos.models.FeedResponse;

CosmosQueryRequestOptions options =
    new CosmosQueryRequestOptions();

double totalRu = 0;
long totalItems = 0;

for (FeedResponse<OrderDocument> page :
        container.queryItems(
            "SELECT * FROM c WHERE c.status = 'CREATED'",
            options,
            OrderDocument.class
        ).iterableByPage(100)) {

    totalRu += page.getRequestCharge();
    totalItems += page.getResults().size();
}

System.out.println(
    "Result items=" + totalItems + ", total RU=" + totalRu);
~~~

Đoạn query này cố tình không có partition key để quan sát cross-partition cost trong lab. Không dùng làm pattern mặc định cho mỗi HTTP request.

### 27.1. Continuation token

SDK hỗ trợ cách xử lý pagination/continuation theo APIs phù hợp. Lưu token đúng contract để đọc tiếp thay vì query lại toàn bộ. Token không phải business cursor bất biến qua mọi thay đổi dữ liệu.

### 27.2. Page size ảnh hưởng round trips

Giảm page size có thể tăng số requests/round trips, nhưng tổng RU còn phụ thuộc indexing, dữ liệu và query. Đo toàn bộ query thay vì suy đoán.

## 28. Indexing policy và document size

Cosmos DB indexing hỗ trợ nhiều query patterns, nhưng index cũng tạo overhead khi ghi.

### 28.1. Tối ưu theo access pattern

- Xác định các trường WHERE/ORDER BY thường dùng.
- Kiểm tra indexing policy và composite indexes khi thích hợp.
- Tránh index những paths không cần nếu write-heavy và tính năng cho phép.
- Đo request charge của reads/writes sau khi thay đổi.

### 28.2. Tránh documents quá lớn

Nếu một item chứa lịch sử sự kiện khổng lồ tăng liên tục, write RU và network overhead có thể tăng. Cân nhắc tách event history thành items/containers khác theo access pattern.

### 28.3. Chỉ trả field cần dùng

Không SELECT * nếu API chỉ cần id, status và tổng tiền. Projection có thể giảm payload/network và một phần chi phí theo query.

### 28.4. Không tắt indexing chỉ vì muốn RU write thấp

Thiếu index có thể làm query quan trọng tốn RU hơn nhiều. Đánh giá cả read/write mix.

## 29. Autoscale vẫn cần tránh burst vượt giới hạn

Ví dụ một workload thay đổi:

~~~text
Bình thường: 200 RU/s được tiêu thụ
Cuối tuần:  1.500 RU/s được tiêu thụ
Flash sale: 8.000 RU/s được yêu cầu
~~~

Nếu autoscale max thấp hơn nhu cầu, hoặc một hot logical partition gặp giới hạn, 429 vẫn có thể xuất hiện.

### 29.1. Autoscale max phải dựa trên peak

Chọn max quá thấp làm tải peak bị throttled; chọn quá cao có thể tăng chi phí theo mô hình tính phí và mức sử dụng.

### 29.2. Capacity nhiều vùng

Trong tài khoản multi-region, cần xem distribution và throughput theo region theo contract hiện hành. Không lấy tổng RU/s lý thuyết của các regions làm ngân sách duy nhất cho một client ở một region.

### 29.3. Autoscale không thay thế query tuning

Một query scan rất nhiều documents vẫn tốn RU lớn, dù autoscale có thể cung cấp thêm capacity ở mức nào đó.

## 30. Hot logical partition trong hệ thống multi-tenant

Giả sử container partition key **/tenantId**; một tenant có 75% writes và nhiều queries.

~~~text
tenant-big: 75% request volume
tenants-other: 25% request volume
~~~

### 30.1. Phương án

1. Tối ưu reads/writes của tenant lớn.
2. Đặt per-tenant rate limit để bảo vệ tenants khác.
3. Tách hot tenant sang container/capacity riêng nếu kiến trúc cho phép.
4. Dùng synthetic key hoặc hierarchical partition keys theo tính năng hỗ trợ.
5. Thiết kế lại data model/query routing dựa trên đo đạc.

### 30.2. Đánh đổi của synthetic key

Chia một tenant ra nhiều buckets có thể giảm hotspot, nhưng query toàn tenant có thể fan-out và transaction trong cùng logical partition không bao trùm toàn tenant.

### 30.3. Thay partition key đòi migration

Một container đang có dữ liệu không thể mặc định thay partition key path bằng việc sửa một field. Cần kế hoạch tạo đích, copy, catch-up, cutover, validation và cleanup.

## 31. Direct mode và Gateway mode

Cosmos DB Java SDK có các hình thức kết nối như Direct/Gateway theo cấu hình SDK và tính năng.

| Chế độ | Tư duy | Quan tâm |
|---|---|---|
| **Direct** | Kết nối tối ưu hơn đến backend partitions/replicas theo cơ chế hỗ trợ | Ports, private networking, connection counts, NAT |
| **Gateway** | Gửi operations qua HTTPS gateway | Proxy/network policy, latency và capacity |

Không khẳng định một mode tốt nhất mọi nơi. Cần đo trên network topology thật.

### 31.1. Client reuse và network

Không tạo CosmosClient mỗi HTTP request. Mỗi client có connection management và background resources riêng.

### 31.2. Private endpoints và DNS

Kiểm tra FQDN/private DNS zone, VNet integration, route/firewall và mode kết nối phù hợp. Không tắt TLS hoặc mở Internet rộng để khắc phục lỗi private DNS.

### 31.3. Đừng tăng connection settings mù quáng

Tăng connection count trên nhiều Pods có thể làm memory/ports/NAT pressure cao hơn, không tạo RU/s mới.

## 32. Consistency levels và latency

Cosmos DB hỗ trợ các mức consistency theo cấu hình/tính năng như Strong, Bounded Staleness, Session, Consistent Prefix và Eventual.

### 32.1. Ảnh hưởng của consistency

- Tính mới và tính nhất quán của dữ liệu đọc.
- Read-after-write semantics.
- Khả năng hoạt động và latency trong nhiều regions.
- Chi phí tài nguyên ở một số patterns/cấu hình.

### 32.2. Session consistency

Session consistency là mô hình được dùng phổ biến; client/session token hỗ trợ các bảo đảm theo contract. Nếu nhiều clients độc lập không chia sẻ session context, trải nghiệm read-after-write có thể cần xử lý rõ trong ứng dụng.

### 32.3. Không giảm consistency bằng mọi giá

Thanh toán và inventory có thể có quy tắc nghiệp vụ đòi trạng thái mới nhất ở một số thao tác. Tối ưu RU không được làm sai business invariants.

## 33. Change Feed, Azure Functions và workload nền

~~~mermaid
flowchart LR
    APP[Java orders-api] --> COSMOS[(Cosmos DB)]
    COSMOS --> FEED[Change Feed]
    FEED --> WORKER[Azure Function / Java worker]
    WORKER --> Q[Service Bus / Analytics]
~~~

Change Feed cung cấp luồng thay đổi từ Cosmos DB để các processors xử lý bất đồng bộ theo semantics/tính năng của chế độ feed.

### 33.1. Không tự động exactly-once

Worker có thể gửi một message rồi crash trước khi ghi tiến độ Change Feed. Khi chạy lại, event có thể được xử lý lại. Cần idempotency ở sink và checkpoints.

### 33.2. Change Feed có dùng tài nguyên

Các hoạt động đọc feed có thể đóng góp vào request charge/throughput consumption. Theo dõi RU và tránh làm API SLO giảm vì background analytics.

### 33.3. Batch job cần budget riêng

Một job backfill quét hàng triệu documents có thể gây 429 cho API cùng container. Giới hạn tốc độ và sắp lịch hoặc tách capacity khi hợp lý.
## 34. TTL và vòng đời dữ liệu

Cosmos DB hỗ trợ **Time-to-Live (TTL)** cho các items/containers theo cài đặt tương ứng.

TTL có thể hợp với:

- Session data và cache có thời hạn.
- Temporary workflow state.
- Telemetry không cần lưu lâu.
- Kết quả xử lý tạm hoặc audit với retention được phê duyệt.

### 34.1. TTL không phải backup

Khi dữ liệu hết hạn và bị xóa theo lifecycle policy, TTL không tự tạo bản sao để khôi phục. Nếu cần backup/restore, phải dùng cơ chế được Cosmos DB và tổ chức hỗ trợ.

### 34.2. Xem xét RU và storage

Expiration/lifecycle, indexes và kích thước dữ liệu có thể tác động tới resource usage và billing theo chế độ. Không khẳng định mọi thao tác xóa TTL có cùng charge như một lệnh delete thủ công.

### 34.3. Tuân thủ lưu trữ dữ liệu

Không đặt TTL ngắn cho dữ liệu đơn hàng, thanh toán hoặc hồ sơ cần retention pháp lý nếu chưa được phê duyệt.

## 35. Bảo mật Java SDK và Cosmos DB

Các nguyên tắc:

- Ưu tiên **Microsoft Entra ID/managed identity** và Cosmos DB for NoSQL data-plane RBAC khi kiến trúc/SDK hỗ trợ.
- Phân tách quyền đọc, ghi, admin và migration.
- Dùng TLS và private networking theo chính sách.
- Không hardcode account keys, tokens hoặc connection strings.
- Dùng Key Vault/secret manager nếu cần account key.
- Xác minh tenant authorization ở application layer.
- Không log raw documents có dữ liệu cá nhân.
- Không in toàn bộ Cosmos diagnostics ra logs công khai.
- Quản lý secret/credential rotation và revoke.
- Có quy trình audit cho operations nhạy cảm.

### 35.1. 403 khác 429

HTTP 403 thường cần điều tra quyền, credential, chính sách network hoặc substatus; tăng RU/s không giúp sửa lỗi này.

### 35.2. Biết partition key không có nghĩa được phép đọc tenant

API cần xác minh principal có quyền đối với tenantId đã yêu cầu, sau đó mới gọi Cosmos DB. Không dựa vào việc client biết tenantId để coi đó là phân quyền.

### 35.3. Development identity khác production identity

DefaultAzureCredential có thể dùng credential từ Azure CLI trên máy dev nhưng managed identity ở cloud. Xác nhận role scope và danh tính thực dùng; không lấy account key production làm giải pháp tạm cho developer.

## 36. Azure Monitor, SDK metrics và Application Insights

Một dashboard vận hành nên kết hợp Cosmos DB resource metrics và application telemetry:

| Tầng | Chỉ số | Câu hỏi cần trả lời |
|---|---|---|
| RU consumption | Total consumed RU/s và RU per operation | Capacity có đủ? |
| Throttling | 429 count/rate | Throttling có tăng? |
| Successful throughput | Hoàn tất ops/s | Tăng concurrency có tăng kết quả? |
| Latency | p50/p95/p99 request, API latency | SDK retry có làm user chờ? |
| Retry | SDK retry/outer retry theo diagnostics | Có retry storm? |
| Partition usage | Normalized RU utilization/hot partition khi hỗ trợ | Một key có quá nóng? |
| Request type | Point read, create, query, patch, bulk | Operation nào tốn RU? |
| Client health | JVM CPU, GC, in-flight, network connections | App bị nghẽn? |
| Errors | 400/401/403/404/409/412/429/503 | Data/permission/capacity hay service? |
| Cost | Provisioned throughput, autoscale, storage, logs | Hóa đơn có hợp lý? |

### 36.1. Đừng chỉ đo final API errors

SDK có thể đã gặp 429 rồi tự retry thành công. Client chỉ thấy HTTP 200 nhưng p99 latency tăng. Cần xem service-side 429 metrics, SDK diagnostics và API durations.

### 36.2. Request charge phải gắn với thao tác

Nên phân loại RU theo endpoint, query shape, tenant group và payload size (không ghi dữ liệu nhạy cảm). Một tổng RU duy nhất khó chỉ ra query nào cần tối ưu.

### 36.3. Metrics có thể khác theo cấu hình

Tên Azure Monitor metrics, diagnostic log categories và KQL tables thay đổi theo account type/cấu hình. Kiểm tra schema thực tế trước khi áp query; không giả định mọi metric chi tiết đều có sẵn mặc định.

### 36.4. Sampling và p99

Một số traces chậm rất hiếm có thể bị sampling bỏ qua. Dùng metrics tổng hợp, slow-operation diagnostics và sampling có chủ đích.

## 37. Phân biệt 429 có thể chấp nhận và sự cố

Không phải mỗi 429 nội bộ đều là incident nếu SDK xử lý thành công và ứng dụng vẫn đạt SLO.

Các dấu hiệu đáng cảnh báo:

- p95/p99 vượt SLO.
- Final 429/5xx hoặc timeout tăng.
- Retry budget thường xuyên hết.
- Queue/backlog lớn dần.
- Autoscale đã tới giới hạn.
- Một tenant liên tục bị throttled.
- JVM resources bị chiếm bởi hàng nghìn requests chờ.
- Tổng chi phí tăng nhưng successful throughput không cải thiện.

Ví dụ SLO mang tính minh họa:

~~~text
p95 API latency: dưới 500 ms
p99 API latency: dưới 1.500 ms
successful operations: trên 99,9% trong kỳ đo
background queue age: dưới 2 phút
~~~

Các giá trị không phải SLA chung của Cosmos DB. Đặt theo yêu cầu ứng dụng, subscription, region, traffic và contract.

### 37.1. Quan sát cả retries và kết quả cuối

Nếu 100 requests đều thành công sau 5 lần retry, API success rate vẫn 100%, nhưng hệ thống có thể đang tiêu tốn latency và gây tải không cần thiết. Điều này cần được đo.

## 38. Runbook điều tra 429 trong production

### Bước 1 — Khoanh vùng

429 xảy ra trên mọi requests hay chủ yếu một tenant/endpoint/partition key? Có bắt đầu sau deploy hoặc chạy backfill không?

### Bước 2 — Xác định mức độ ảnh hưởng

Đo p95/p99, final errors, queue age, latency của API và business success. Không xếp mọi 429 có internal retry thành một incident giống nhau.

### Bước 3 — Đo RU và query shapes

Tìm operations có request charge tăng đột ngột, query fan-out hoặc item size lớn hơn sau schema change.

### Bước 4 — Kiểm tra capacity

Manual, autoscale hay serverless? Đã chạm max RU/s hay service limits chưa? Có nhiều containers chia sẻ database throughput không?

### Bước 5 — Xác định hot partition

Normalized RU/physical partition, phân bố tenants và request charges có lệch không? Nếu tất cả tải tập trung một hot key, tăng tổng RU/s có thể không hiệu quả.

### Bước 6 — Đọc SDK diagnostics

Retries, activity IDs, network timings, regions, Direct/Gateway behavior và client timeouts. Redact thông tin nhạy cảm trước khi chia sẻ.

### Bước 7 — Kiểm tra Java app

Số Pods, executor threads, Reactor flatMap concurrency, số CosmosClients, JVM memory/GC và retry policies ở nhiều tầng.

### Bước 8 — Chọn biện pháp dựa trên bằng chứng

- Chuyển query thành point read nếu có id + partition key.
- Điều chỉnh indexing/filters/pagination.
- Giới hạn background worker và tốc độ ingest.
- Giảm concurrency hoặc thêm rate limiting.
- Tăng RU/s/autoscale max khi đúng nguyên nhân.
- Thiết kế lại partition key/hot-tenant isolation nếu cần.
- Kiểm tra networking nếu nghi ngờ lỗi không phải 429 thuần túy.

### Bước 9 — Đo lại và rollback nếu cần

So sánh same-workload p95/p99, success throughput, 429/retry rates, RU/operation và chi phí.

## 39. Lỗi thường gặp không nên nhầm với 429

### 39.1. 400 Bad Request

Query, payload hoặc partition key không hợp lệ. Cần sửa dữ liệu/code; không retry mù.

### 39.2. 401/403

Credential sai, token hết hạn, data-plane role thiếu hoặc network policy. Kiểm tra identity/scope/substatus.

### 39.3. 404 Not Found

Item có thể tồn tại ở **partition key value khác**. Xem cặp id + pk và resource names trước khi kết luận dữ liệu mất.

### 39.4. 409 Conflict

Create item trùng. Xử lý business idempotency hoặc conflict đúng nghĩa; không tự đổi id rồi tạo trùng nghiệp vụ.

### 39.5. 412 Precondition Failed

ETag bị thay đổi. Đọc trạng thái mới và quyết định lại theo business rule, không lặp replace vô điều kiện.

### 39.6. 503, connection timeout

Kiểm tra service/network regions, private DNS, Direct/Gateway mode, proxy và client resource pressure. Retry có giới hạn và alert khi kéo dài.

### 39.7. Latency cao nhưng 429 thấp

Có thể do cross-partition query, payload lớn, CPU/GC của ứng dụng, network RTT hoặc tạo CosmosClient liên tục.

## 40. Capacity planning từ dữ liệu đo RU

Ví dụ workload:

| Operation | Tốc độ peak | RU/operation minh họa | RU/s |
|---|---:|---:|---:|
| Point reads | 300/s | 2 | 600 |
| Create orders | 100/s | 8 | 800 |
| Tenant queries | 30/s | 15 | 450 |
| Background writes | 50/s | 6 | 300 |
| **Tổng** | | | **2.150** |

Đây là bài toán ví dụ để hiểu cách cộng RU budget. Không phải charge chuẩn cho từng loại operation.

### 40.1. Headroom

Cần dự phòng burst, charge variation, retries và workloads khác. Không dùng một hệ số headroom duy nhất cho mọi hệ thống; load test theo distribution thật.

### 40.2. Đừng chỉ lấy RU trung bình

Query trên tenant nhỏ có thể tốn 5 RU nhưng trên tenant lớn tốn 200 RU. Đo p95/p99 request charge và per-tenant distribution.

### 40.3. Autoscale max và physical partitions

Ngay cả khi tổng capacity đủ theo phép tính, hot logical partition có thể chạm giới hạn cục bộ. Phải xem distribution và region metrics.

### 40.4. Replay/backfill có RU cost

Một triệu writes có thể tạo lượng RU lớn. Lên kế hoạch theo budget, thời điểm, throughput và ảnh hưởng đến API.

## 41. Chi phí và tối ưu kinh tế

Các nguồn chi phí:

- Provisioned RU/s hoặc autoscale throughput.
- Serverless request consumption khi sử dụng mô hình đó.
- Data storage và index size.
- Multi-region replication/read-write topology.
- Network egress/Private Link.
- Azure Functions, AKS, App Service compute.
- Azure Monitor/Log Analytics logs và retention.
- Backup/DR theo cấu hình và cơ chế giá.
- Background imports, bulk jobs và retries.

### 41.1. Những thay đổi có thể giảm RU lẫn latency

- Point reads thay query theo id.
- Có partition key trong query.
- Dùng index phù hợp và projections.
- Giảm document size khi hợp nghiệp vụ.
- Chia workload nóng theo key strategy đúng.
- Giới hạn batch concurrency và duplicate writes.
- Không fan-out cross-partition mỗi HTTP request.

### 41.2. Khi nào tăng throughput là đúng?

Khi đã tối ưu queries/data model nhưng workload vẫn thật sự cần nhiều RU/s hơn; chọn capacity theo đo thực, SLO và ngân sách.

### 41.3. Khi nào tăng throughput chưa đúng?

Nếu app query toàn container cho một item hoặc một tenant cực nóng, sửa access pattern/partitioning trước có thể hiệu quả hơn.

## 42. Đồng bộ và bất đồng bộ: chọn đúng mô hình Java

| Góc nhìn | CosmosClient sync | CosmosAsyncClient reactive |
|---|---|---|
| Cách gọi | Imperative, thread chờ I/O | Mono/Flux |
| Dễ hiểu | Thường đơn giản | Cần quản trị reactive lifecycle |
| Concurrency | Executor/thread pools | flatMap/scheduler/backpressure |
| Rủi ro | Nhiều blocked threads | Requests phát quá nhiều nếu không giới hạn |
| Request charge | Do Cosmos DB tính | Cùng loại operation có RU tương ứng, không tự giảm |
| Retry | SDK + bounded outer policy nếu cần | SDK + reactive error/deadline logic |
| Phù hợp | Java APIs/batch kiểu imperative | I/O-heavy reactive services |

### 42.1. Async không tự sửa throttling

Nếu 1.000 sync requests bị 429 do thiếu RU, chuyển thành 1.000 async requests không tự tạo RU/s mới.

### 42.2. Không block Reactor event-loop

Trong reactive web handler, tránh gọi block() gây starvation. Với CLI batch entry point, blockLast() có thể phù hợp để chờ kết quả.

### 42.3. Chọn concurrency bằng số liệu

Đo request charge, throughput, SDK diagnostics, JVM memory và p95/p99; không chọn concurrency chỉ dựa trên số CPUs.

## 43. Bài lab: tạo Cosmos DB for NoSQL và kết nối SDK

**Điều kiện:** dùng Azure subscription/resource group được cấp quyền, có quota/ngân sách và không chứa dữ liệu thật.

### 43.1. Tạo resource

Trong Azure Portal:

1. Tạo resource group riêng, ví dụ **rg-cosmos-sdk-lab**.
2. Tạo **Azure Cosmos DB for NoSQL account**.
3. Chọn region và capacity mode phù hợp lab.
4. Tạo database **shopdb**.
5. Tạo container **orders** với partition key path **/tenantId**.
6. Ghi lại throughput/capacity limit.
7. Cấu hình networking, TLS, access permissions.
8. Cấp data-plane role phù hợp cho managed/developer identity nếu dùng Entra.
9. Bật Azure Monitor metrics.
10. Ghi account endpoint để cấu hình Java.

### 43.2. Chuẩn bị Java

1. Cài dependency azure-cosmos v4 và azure-identity phiên bản được phê duyệt.
2. Đặt **COSMOS_ENDPOINT** bằng endpoint thực.
3. Dùng DefaultAzureCredential với identity có data-plane role.
4. Nếu lab dùng account key, lưu ở secret store hoặc environment không commit.
5. Tạo một CosmosClient theo vòng đời app.
6. Create/read vài items với id + tenantId.

### 43.3. Phân loại lỗi kết nối

- 403: có thể thiếu data-plane role hoặc policy.
- 401: credential/token sai.
- 404: resource/id/partition key không đúng.
- Timeout: DNS, firewall, Direct/Gateway settings.
- 429: không đủ RU capacity vào lúc request, cần kiểm tra metrics.

Không tăng RU/s chỉ vì một lỗi 401 hoặc DNS.

## 44. Bài lab: đo 429 và backpressure an toàn

**Mục tiêu:** chứng minh RU/request, throughput, 429 và tác động của concurrency/retry bằng một phép thử nhỏ, kiểm soát chi phí.

### A. Baseline

1. Tạo vài trăm items giả với nhiều tenantId.
2. Đọc bằng point read id + partition key.
3. Query trong một tenant.
4. Chạy một query cross-partition có giới hạn.
5. Ghi RU mỗi request và tổng RU query.
6. Đo p50/p95/p99 và requests thành công/giây.

### B. Tăng tải theo nấc nhỏ

1. Thử concurrency 1.
2. Thử concurrency 4, 8 nếu môi trường cho phép.
3. Quan sát 429 trong metrics, retries và final errors.
4. Dừng ngay khi vượt ngưỡng tải/chi phí an toàn.
5. Không cố tình phá quota hoặc gây sự cố trên account dùng chung.

### C. Thử hot partition

1. Tạo nhiều requests cho cùng tenantId giả.
2. Tạo cùng lượng requests phân tán nhiều tenants.
3. So sánh latency, throttling và RU distribution.
4. Không kết luận từ một lần chạy; thử nhiều vòng với điều kiện tương tự.

### D. Tối ưu từng yếu tố

- Point read thay query theo id.
- Query có partition key.
- Giảm số fields trả về.
- Giới hạn Reactor concurrency.
- Áp dụng rate limiter theo RU budget đã đo.
- Nếu được phép, thay RU throughput/autoscale max và so sánh.

### E. Bảng báo cáo

| Chỉ số | Baseline | Sau tối ưu |
|---|---|---|
| Successful operations/s | Đo thực | Đo thực |
| RU/operation | Đo thực | Đo thực |
| p95/p99 latency | Đo thực | Đo thực |
| Service 429 count | Đo thực | Đo thực |
| SDK retry count | Đo thực | Đo thực |
| Final 429/5xx | Đo thực | Đo thực |
| In-flight requests | Đo thực | Đo thực |
| Max partition usage | Đo thực | Đo thực |
| Estimated cost | Đo thực | Đo thực |

**Tiêu chí hoàn thành:** có bằng chứng một thay đổi giảm RU/429 hoặc cải thiện p95/p99 mà không làm mất dữ liệu và không phát sinh chi phí bất hợp lý.

## 45. Tình huống ứng dụng thực tế

### 45.1. Flash sale gây 429 trên mọi tenants

Kiểm tra overall RU utilization, autoscale max, API burst, batch workers, SDK retries và latency. Điều tiết ingress, chuyển việc dài sang queue, tăng capacity khi có căn cứ và thử lại.

### 45.2. Một tenant lớn bị 429 nhiều hơn các tenants khác

Kiểm tra partition key path /tenantId, hot partition, per-tenant RU usage và data distribution. Tối ưu theo key hoặc cân nhắc isolation/migration theo kế hoạch.

### 45.3. Backfill làm API chậm

Background job quét nhiều documents có thể tiêu thụ RU budget chung. Đặt job rate limit, giảm concurrency, chạy vào giờ ít tải hoặc dùng capacity riêng.

### 45.4. API trả 200 nhưng p99 tăng

SDK có thể retry 429 nội bộ. Xem diagnostics, RU metrics và total elapsed time chứ không chỉ final HTTP status.

### 45.5. App tạo CosmosClient cho từng request

Connection churn, nhiều background resources và độ trễ startup. Tái sử dụng một client theo lifecycle ứng dụng rồi đo lại.

### 45.6. CreateItem trả 409 sau timeout

Có thể request đầu đã ghi thành công nhưng client không nhận response. Đọc lại theo id + partition key và so operationId; không tạo item mới với id khác để né conflict.

## 46. Checklist production

- [ ] Dùng SDK v4 cho Cosmos DB for NoSQL và pin version phù hợp.
- [ ] Account/database/container được provision có kiểm soát.
- [ ] Partition key chọn theo access pattern và phân phối tải.
- [ ] Đã đánh giá hot logical partitions và tenants lớn.
- [ ] Items có business id và idempotency key phù hợp.
- [ ] CosmosClient được reuse, không tạo trên mỗi request.
- [ ] Ưu tiên identity và data-plane RBAC khi khả thi.
- [ ] Secrets không nằm trong code/container image/logs.
- [ ] TLS/private networking đã được kiểm thử.
- [ ] Point reads dùng đúng id + partition key.
- [ ] Queries parameterized và có partition key khi phù hợp.
- [ ] Có phân trang và đo tổng RU toàn query.
- [ ] Indexing policy dựa trên query/write mix thực tế.
- [ ] Request charge được ghi theo operation/tenant.
- [ ] Có metrics 429, RU consumption và normalized partition usage.
- [ ] Có p95/p99 latency và final error rate.
- [ ] Hiểu SDK automatic retries theo đúng version.
- [ ] Outer retries có deadline và giới hạn số lần.
- [ ] Tôn trọng retry-after, thêm jitter và tránh retry storm.
- [ ] Không retry mù 400/403/409/412.
- [ ] Writes có idempotency và ETag khi cần.
- [ ] Reactor/executor concurrency có giới hạn.
- [ ] Có rate limiting, admission control và backpressure.
- [ ] Batch jobs không làm cạn RU budget của API.
- [ ] Manual/autoscale/serverless được chọn dựa trên đo tải.
- [ ] Kiểm tra autoscale max và khả năng multi-region.
- [ ] Có kế hoạch cho hot tenant hoặc migration partition key.
- [ ] SDK diagnostics được bảo vệ và sampling phù hợp.
- [ ] Có runbook 429, 503, DNS, auth và client overload.
- [ ] Có budget/alerts cho RU, storage, compute và logs.
- [ ] Đã load test với dữ liệu/consistency giống production.
- [ ] Đã diễn tập timeout, throttling và pod restart.

## 47. Câu hỏi tự kiểm tra

1. Request Unit khác RU/s như thế nào?
2. Vì sao Cosmos DB trả 429?
3. SDK Java v4 có thể tự retry 429 theo tín hiệu nào?
4. Tại sao ứng dụng vẫn có thể chậm dù SDK retry cuối cùng thành công?
5. Vì sao outer retry quá nhiều có thể gây retry storm?
6. Khi nào nên tôn trọng Retry-After và thêm jitter?
7. Partition key path khác PartitionKey value ra sao?
8. Point read cần id và thông tin gì khác?
9. Vì sao cross-partition query có thể tốn RU hơn?
10. Một container có 10.000 RU/s có luôn cho một hot logical partition dùng tất cả capacity không?
11. Tăng số Java Pods có tự tăng Cosmos RU/s không?
12. Autoscale có bao giờ gặp 429 không?
13. Serverless có nghĩa không giới hạn throughput không?
14. CosmosClient nên được tạo và đóng theo lifecycle nào?
15. CosmosAsyncClient có tự giảm request charge không?
16. flatMap concurrency quá cao gây vấn đề gì?
17. Vì sao semaphore trong một Pod không giới hạn toàn cluster?
18. Backpressure khác retries thế nào?
19. Cần số liệu gì để rate limit theo RU?
20. Vì sao createItem 409 sau timeout có thể là retry của write đã thành công?
21. Upsert có luôn idempotent theo business semantics không?
22. ETag 412 giúp phát hiện vấn đề nào?
23. Có thể lấy request charge từ Java SDK response bằng cách nào?
24. Vì sao phải cộng RU của tất cả pages?
25. Có nên log toàn bộ diagnostics cho mọi request production không?
26. Direct và Gateway mode khác nhau về network path ra sao?
27. Consistency level ảnh hưởng tới read-after-write thế nào?
28. Nếu background job làm API bị 429, có những cách điều tiết nào?
29. Cosmos DB data-plane RBAC khác Azure ARM Contributor thế nào?
30. Khi 429 tăng, nên tối ưu query/partitioning hay tăng RU/s trước?

## 48. Tổng kết

**Azure Cosmos DB Java SDK v4** cung cấp CosmosClient/CosmosAsyncClient, thao tác CRUD, query, request charge và diagnostics để Java applications làm việc với Cosmos DB for NoSQL. Thiết kế hiệu quả bắt đầu từ **partition key, RU/operation, throughput model và access pattern**.

**HTTP 429** cho biết một request bị giới hạn tài nguyên trong thời điểm/phạm vi liên quan. SDK có thể retry theo gợi ý của server, nhưng retry không tạo thêm RU/s. Ứng dụng phải dùng **bounded retries, Retry-After, deadlines, backpressure, giới hạn concurrency và idempotency** để tránh làm áp lực tăng thêm.

Hướng tối ưu bền vững gồm **point reads, queries có partition key, indexing phù hợp, document size hợp lý, tổng RU của mọi pages, quan sát hot partitions, p95/p99 latency và successful throughput**. Chỉ tăng provisioned/autoscale capacity khi phép đo chứng minh nhu cầu và ngân sách phù hợp.

Kết hợp **Microsoft Entra ID/data-plane RBAC, private networking, Java SDK diagnostics, Azure Monitor/Application Insights và Azure Cost Management** giúp vận hành Cosmos DB an toàn, có thông lượng dự báo được, xử lý throttling đúng cách và không lãng phí tài nguyên Azure.




