# Thời gian chờ kết nối, thao tác Key-Value và truy vấn

## 1. Vì sao cần phân biệt các loại thời gian chờ?

Trong **Spring Data Couchbase**, cùng một ứng dụng có thể gặp ba tình huống: không bootstrap được cluster khi khởi động, đọc document theo ID bị chậm, hoặc truy vấn SQL++ không hoàn tất. Cả ba có thể xuất hiện dưới tên *timeout*, nhưng phạm vi của chúng khác nhau. Nếu điều chỉnh nhầm, ứng dụng chỉ chờ lâu hơn mà không giải quyết nguyên nhân.

Bài học thuộc chương **Cấu hình kết nối** của module **SPRING_DATA_COUCHBASE**. Nắm vững timeout giúp xây dựng tầng dữ liệu dựa trên document mapping, repository, `CouchbaseTemplate` và SQL++, đồng thời chuẩn bị cho lựa chọn chỉ mục, TTL, CAS, giao dịch và API reactive theo yêu cầu hiệu năng, nhất quán, vận hành.

Sau bài học, bạn có thể:

- Giải thích **connect timeout**, **Key-Value (KV) timeout** và **query timeout**.
- Cấu hình timeout qua Spring Boot và Couchbase Java SDK.
- Đặt giới hạn riêng cho một phép đọc KV hoặc một truy vấn SQL++.
- Thiết kế ngân sách thời gian cho toàn bộ HTTP request, gồm retry và xử lý kết quả.
- Phân biệt timeout với lỗi DNS, TLS, RBAC, bucket/collection hoặc thiếu index.
- Hiểu vì sao một thao tác **ghi bị timeout không đồng nghĩa chắc chắn chưa được ghi**, tránh retry tạo lỗi dữ liệu.

Các ví dụ dùng **Spring Boot 3.x** cùng Spring Data Couchbase và Couchbase Java SDK 3.x tương thích. Cấu hình nâng cao, giá trị mặc định và API có thể khác theo phiên bản; luôn đối chiếu configuration metadata của phiên bản triển khai.

## 2. Ba đồng hồ thời gian ở ba tầng khác nhau

Giả sử ứng dụng quản lý sản phẩm truy cập keyspace:

~~~text
Couchbase Cluster
└── Bucket: inventory
    └── Scope: catalog
        └── Collection: products
~~~

Một request đi qua các tầng logic:

~~~mermaid
flowchart TD
    A["HTTP / Service"] --> B["Spring Data Repository hoặc CouchbaseTemplate"]
    B --> C["Couchbase Java SDK"]
    C --> D{"Nhóm thao tác?"}
    D --> E["Bootstrap / Kết nối<br/>connect timeout"]
    D --> F["KV: get, upsert, remove<br/>KV timeout"]
    D --> G["SQL++: SELECT, JOIN<br/>query timeout"]
    E --> H["Cluster / topology"]
    F --> I["Data service"]
    G --> J["Query / Index service"]
~~~

| Loại | Phạm vi | Khi nào liên quan? | Ví dụ |
| --- | --- | --- | --- |
| Connect | Thiết lập kết nối, bootstrap SDK tới cluster | Mở client/thiết lập liên lạc và topology | Không kết nối được seed node |
| KV | Thao tác đọc/ghi bằng document key | `get`, `exists`, `insert`, `upsert`, `replace`, `remove` | `repository.findById(id)` chờ quá lâu |
| Query | Request SQL++ | Truy vấn thuộc tính, tổng hợp, join | `findBySku(...)` hoặc `cluster.query(...)` chờ quá lâu |

**Không đánh đồng ba timeout.** Tăng `connect` không làm SQL++ chạy nhanh hơn. Tăng `kv` không giải quyết câu Query thiếu index. Tăng `query` không sửa mật khẩu sai hay endpoint TLS không truy cập được.

### 2.1. Timeout không phải thời gian thực thi cố định

Một cấu hình `kv: 2s` không có nghĩa mọi KV request phải chờ đủ hai giây; một request lành mạnh có thể hoàn tất sau vài mili giây. Đây là ngân sách thời gian của loại thao tác tương ứng. Khi giới hạn hết, SDK phát sinh lỗi dù ứng dụng có thể chưa biết kết quả cuối cùng ở phía server.

Thời gian quan sát được có thể bao gồm nhiều giai đoạn như chờ điều phối, truyền qua mạng, thử lại và xử lý dịch vụ. Vì thế cần đọc **error context** và metrics, không chỉ nhìn tên exception.

### 2.2. Deadline của HTTP request là giới hạn khác

Một API có thể đọc KV, chạy một query rồi trả response. Nếu gateway đặt giới hạn toàn request là 3 giây, bạn phải xét toàn bộ chuỗi thực thi:

~~~text
HTTP request budget: 3.0 giây (chỉ minh họa)
├── Xử lý và kiểm tra đầu vào: 0.2 s
├── KV read budget:            0.5 s
├── SQL++ budget:              1.5 s
└── Serialize / mạng / dự phòng: 0.8 s
~~~

Các con số trên là ví dụ cách phân bổ **time budget**, không phải SLA tiêu chuẩn. Nếu có retry hoặc nhiều thao tác nối tiếp, cần tính ngân sách bổ sung; nếu tác vụ song song, cần tính theo đường găng. Việc chọn timeout phải phù hợp thời gian đáp ứng tổng.

## 3. Cấu hình thời gian chờ qua Spring Boot

Với Spring Boot, dependency đồng bộ thông dụng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-couchbase</artifactId>
</dependency>
~~~

Ví dụ `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: inventory-service

  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
    env:
      timeouts:
        connect: 10s
        kv: 2s
        query: 8s

  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET:inventory}"
~~~

Ba thuộc tính cần nhớ:

| Property | Chức năng | Giá trị ví dụ |
| --- | --- | --- |
| `spring.couchbase.env.timeouts.connect` | Ngân sách connect/thiết lập kết nối SDK | `10s` |
| `spring.couchbase.env.timeouts.kv` | Ngân sách mặc định cho thao tác KV thông thường | `2s` |
| `spring.couchbase.env.timeouts.query` | Ngân sách mặc định cho request Query/SQL++ | `8s` |

Các property `spring.couchbase.connection-string` và `spring.couchbase.username/password` xác định cluster và danh tính truy cập; `spring.data.couchbase.bucket-name` chọn bucket mặc định cho Spring Data. Chúng không cùng loại với timeout.

**Về giá trị:** `10s`, `2s` và `8s` chỉ là ví dụ cho bài học. Không sao chép chúng vào production nếu chưa đo độ trễ tải thực tế, kỳ vọng nghiệp vụ và giới hạn từ gateway hoặc hệ thống phụ thuộc.

### 3.1. Đơn vị thời gian và nguồn cấu hình

Spring Boot hỗ trợ cấu hình thời gian với đơn vị tường minh như `500ms`, `2s` và `1m` cho những property kiểu `Duration`. Nên ghi rõ đơn vị thay vì một số trần không thể hiện ý nghĩa.

Đưa timeout ra biến môi trường:

~~~yaml
spring:
  couchbase:
    env:
      timeouts:
        connect: "${COUCHBASE_CONNECT_TIMEOUT:10s}"
        kv: "${COUCHBASE_KV_TIMEOUT:2s}"
        query: "${COUCHBASE_QUERY_TIMEOUT:8s}"
~~~

`COUCHBASE_CONNECT_TIMEOUT`, `COUCHBASE_KV_TIMEOUT` và `COUCHBASE_QUERY_TIMEOUT` là **tên biến do ví dụ ứng dụng đặt ra**, được tham chiếu bằng placeholder. Kiểm tra active profile và thứ tự ưu tiên property sources nếu runtime dùng giá trị khác với YAML.

Không log toàn bộ environment để gỡ lỗi timeout: môi trường có thể chứa cả mật khẩu và secret.

### 3.2. Timeout cho durable KV

Một mutation có yêu cầu durability thường phải chờ điều kiện xác nhận mạnh hơn thao tác KV thông thường. Couchbase SDK có khái niệm `kvDurableTimeout` dành cho nhóm này. Một số phiên bản Spring Boot hỗ trợ property tương ứng trong nhóm `spring.couchbase.env.timeouts`; tên property cụ thể cần được xác minh qua metadata của phiên bản.

**Không mặc định** rằng thao tác KV đọc và durable write nên sử dụng cùng time budget, nhưng cũng không nên tự bịa tên YAML khi chưa kiểm tra API đang chạy.

## 4. Connect timeout: bootstrap và khả năng truy cập cluster

Connection string có thể có một hoặc nhiều seed nodes:

~~~text
# Local, không TLS
couchbase://127.0.0.1

# Hai seed nodes nội bộ
couchbase://cb-node-a.internal,cb-node-b.internal

# TLS
couchbases://cb.example.internal
~~~

SDK liên hệ seed node, nhận topology và sử dụng địa chỉ node/dịch vụ phù hợp cho các thao tác tiếp theo. Một seed node có thể reachable nhưng những địa chỉ được cluster quảng bá lại không truy cập được từ môi trường Kubernetes, Docker hoặc mạng private/public của ứng dụng.

Những nguyên nhân phổ biến:

1. DNS không phân giải được hoặc endpoint sai.
2. Network policy, firewall, route hoặc cổng dịch vụ bị chặn.
3. Cluster quảng bá địa chỉ private không truy cập được từ application container.
4. TLS handshake hoặc xác minh chứng chỉ/hostname thất bại.
5. Cluster bị quá tải hoặc chưa sẵn sàng khi ứng dụng khởi động.

**Tăng `connect: 30s` không sửa DNS, firewall hay trust chain.** Với production không vô hiệu hóa kiểm tra chứng chỉ để vượt qua lỗi TLS.

### 4.1. Client được tạo chưa chứng minh sẵn sàng đọc/ghi

Ví dụ SDK:

~~~java
import java.time.Duration;
import com.couchbase.client.java.Bucket;

Bucket bucket = cluster.bucket("inventory");
bucket.waitUntilReady(Duration.ofSeconds(10));
~~~

`waitUntilReady` kiểm tra mức readiness của bucket theo điều kiện SDK; nó không thay thế kiểm tra quyền trên collection `catalog.products` và không xác minh Query service/index. Một ứng dụng có thể tạo Spring context thành công nhưng chỉ phát sinh lỗi khi thực hiện I/O đầu tiên.

Kiểm thử truy cập KV theo document ID giúp tách lỗi Data service khỏi lỗi SQL++:

~~~java
boolean present = bucket.scope("catalog")
        .collection("products")
        .exists("probe::missing")
        .exists();

// false là kết quả hợp lệ khi key không tồn tại.
~~~

Phép thử trên không ghi dữ liệu; nó chỉ có giá trị khi keyspace tồn tại và user được quyền KV.

## 5. KV timeout: thao tác theo document ID

Couchbase KV API thao tác trực tiếp trên document key. Khi Spring Data repository đọc bằng `findById`, đường truy cập thường là KV; khi truy vấn bằng `findBySku`, đường truy cập thường là SQL++.

| Thao tác KV | Mục đích | Lưu ý |
| --- | --- | --- |
| `get(id)` | Lấy document bằng ID | Không cần secondary index |
| `exists(id)` | Kiểm tra ID tồn tại | Hữu ích cho smoke test |
| `insert(id, content)` | Tạo document mới | Thất bại nếu ID đã tồn tại |
| `upsert(id, content)` | Tạo hoặc thay toàn bộ nội dung | Cân nhắc ngữ nghĩa ghi đè |
| `replace(id, content)` | Sửa document đã có | Có thể kết hợp CAS |
| `remove(id)` | Xóa theo ID | Timeout ghi/xóa có thể cần đối soát |

Với cấu hình:

~~~yaml
spring:
  couchbase:
    env:
      timeouts:
        kv: 2s
~~~

SDK có ngân sách mặc định cho KV thông thường theo phạm vi hỗ trợ của phiên bản. Nếu một nghiệp vụ cần giới hạn riêng, Couchbase Java SDK có thể đặt timeout trên *operation options*:

~~~java
import java.time.Duration;
import com.couchbase.client.java.kv.GetOptions;
import com.couchbase.client.java.kv.GetResult;

// products là com.couchbase.client.java.Collection đã chọn.
GetResult result = products.get(
        "product::SKU-001",
        GetOptions.getOptions().timeout(Duration.ofMillis(800))
);
~~~

Ví dụ này chỉ thay giới hạn của **một lần `get`**. Nó không đổi `kv` mặc định cho toàn cluster, cũng không tự thay giới hạn của mọi phương thức Spring Data repository.

### 5.1. Vì sao KV có thể timeout dù không chạy SQL++?

Các lý do đáng điều tra gồm Data service hoặc node chậm, request bị xếp hàng, mạng không ổn định, chuyển đổi topology, số lượng thao tác đồng thời quá lớn hoặc timeout đặt quá thấp so với phân bố độ trễ. Không cần tạo secondary index để `get(id)` hoạt động.

Nếu tăng timeout mà tỷ lệ lỗi vẫn cao, tiếp tục kiểm tra tải cluster, hàng đợi, các retry đã xảy ra và điều kiện mạng. Tăng ngân sách có thể làm request chờ lâu hơn nhưng không tăng năng lực xử lý của Data service.

### 5.2. Mutation có durability cần ngân sách riêng

Ví dụ upsert yêu cầu durability:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.DurabilityLevel;
import com.couchbase.client.java.kv.UpsertOptions;

products.upsert(
        "product::SKU-001",
        JsonObject.create().put("sku", "SKU-001"),
        UpsertOptions.upsertOptions()
                .durability(DurabilityLevel.MAJORITY)
                .timeout(Duration.ofSeconds(5))
);
~~~

`DurabilityLevel.MAJORITY` yêu cầu ngữ nghĩa xác nhận khác với thao tác không thiết lập durability. Ngưỡng 5 giây chỉ minh họa cách đặt timeout trên một mutation. Thao tác thực tế phụ thuộc trạng thái cluster và các ràng buộc durability; không nên mặc định durable write nhanh bằng KV read.

## 6. Query timeout: truy vấn SQL++ và chỉ mục

Trong Spring Data Couchbase, query theo thuộc tính thường được thực hiện thông qua Query service. Ví dụ:

~~~sql
SELECT p.sku, p.name
FROM `inventory`.`catalog`.`products` AS p
WHERE p.sku = "SKU-001";
~~~

Thao tác này không giống `products.get("product::SKU-001")`. SQL++ cần quyền Query service và index thích hợp trên đúng keyspace. Index minh họa:

~~~sql
CREATE INDEX ix_products_sku
ON `inventory`.`catalog`.`products`(`sku`);
~~~

Index nên được tạo và duy trì qua quy trình migration/hạ tầng có tài khoản đủ quyền, không tự động tạo bằng account nghiệp vụ ở mỗi startup.

### 6.1. Đặt timeout cho SQL++ qua Boot

~~~yaml
spring:
  couchbase:
    env:
      timeouts:
        query: 8s
~~~

Query timeout là ngân sách của **request SQL++**, không phải giới hạn kết nối TCP. Query có thể chậm do index không phù hợp, quét nhiều document, sort/join lớn, consistency mạnh, Query service quá tải hoặc mạng.

Khi gặp query timeout, nên kiểm tra execution plan, tài nguyên server và độ chọn lọc index trước khi nới `query`.

### 6.2. Override timeout cho một SQL++ query bằng SDK

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;

String sql = """
    SELECT p.sku, p.name
    FROM `inventory`.`catalog`.`products` AS p
    WHERE p.sku = $sku
    LIMIT 20
    """;

QueryResult result = cluster.query(
        sql,
        QueryOptions.queryOptions()
                .parameters(JsonObject.create().put("sku", "SKU-001"))
                .timeout(Duration.ofSeconds(3))
);
~~~

`$sku` là named parameter của SQL++, giúp tách dữ liệu đầu vào khỏi cú pháp truy vấn. `QueryOptions.timeout` giới hạn riêng request đó theo API SDK.

Khi dùng `CouchbaseRepository` hoặc `CouchbaseTemplate`, lựa chọn per-query options phụ thuộc API Spring Data ở phiên bản đang chạy. Không đặt một annotation chưa được Spring Data hỗ trợ và kỳ vọng nó tự thay timeout.

### 6.3. Kiểm tra chỉ mục và kế hoạch truy vấn

~~~sql
EXPLAIN
SELECT p.sku, p.name
FROM `inventory`.`catalog`.`products` AS p
WHERE p.sku = "SKU-001"
LIMIT 20;
~~~

Hãy kiểm tra:

- Truy vấn có nhắm đúng bucket/scope/collection và index phù hợp không?
- Query có sử dụng index mong đợi hay quét quá nhiều document?
- Có join, sort, group hoặc payload trả về không cần thiết?
- Query service có đủ tài nguyên hay đang quá tải?
- Scan consistency có yêu cầu chờ index cập nhật không?
- Sau tối ưu, độ trễ p95/p99 có phù hợp SLA chưa?

**Thao tác `findById` chạy thành công không chứng minh SQL++ sẽ chạy được.** Hai đường đi có thể sử dụng các dịch vụ, quyền và index khác nhau.

## 7. Timeout và tính nhất quán sau ghi

Một KV mutation thành công và một SQL++ query nhìn thấy dữ liệu mới ngay lập tức **không hoàn toàn cùng một cam kết**. Dịch vụ Query và chỉ mục có cơ chế cập nhật riêng. Một mức scan consistency yêu cầu khả năng quan sát dữ liệu mới hơn có thể phát sinh thêm thời gian chờ.

| Trường hợp | Hạ tầng chính | Ý nghĩa với budget |
| --- | --- | --- |
| `get(id)` sau khi biết document key | KV / Data service | Không cần SQL++ index |
| `SELECT ... WHERE sku = ...` | Query + Index service | Cần index và Query budget |
| SQL++ yêu cầu mức nhất quán mạnh hơn | Query và thời gian index bắt kịp | Có thể dùng thêm ngân sách Query |

Nếu truy vấn không thấy document mới hoặc timeout do chờ index, không sửa bằng `connect: 30s`. Xác nhận yêu cầu read-your-own-write, chọn scan consistency theo nghiệp vụ và đo latency thực tế. Những nghiệp vụ giao dịch có deadline và điều kiện riêng, không thể được thiết kế chỉ bằng ba property cơ bản.

## 8. Cấu hình timeout bằng SDK `ClusterEnvironment`

Khi không dùng Boot auto-configuration, có thể tạo SDK environment trực tiếp:

~~~java
import java.time.Duration;
import com.couchbase.client.java.env.ClusterEnvironment;
import com.couchbase.client.java.env.TimeoutConfig;

ClusterEnvironment environment = ClusterEnvironment.builder()
        .timeoutConfig(
                TimeoutConfig
                        .connectTimeout(Duration.ofSeconds(10))
                        .kvTimeout(Duration.ofSeconds(2))
                        .queryTimeout(Duration.ofSeconds(8))
                        .kvDurableTimeout(Duration.ofSeconds(5))
        )
        .build();
~~~

Tạo SDK client dùng environment này:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;

Cluster cluster = Cluster.connect(
        connectionString,
        ClusterOptions.clusterOptions(username, password)
                .environment(environment)
);
~~~

Nếu bạn **tự tạo** environment và cluster trong một ứng dụng SDK độc lập, phải đóng cluster trước rồi mới shutdown environment khi không còn thao tác nào sử dụng:

~~~java
try {
    // Sử dụng SDK client.
} finally {
    try {
        cluster.disconnect();
    } finally {
        environment.shutdown();
    }
}
~~~

Đoạn đóng trên giả định cả hai đối tượng đã được khởi tạo thành công; chương trình thực tế cần xử lý cả lỗi lúc tạo client. Với Spring Boot, ưu tiên dùng `spring.couchbase.env.timeouts.*` và bean được container quản lý. Đừng tạo thêm `ClusterEnvironment` hoặc `Cluster` mới chỉ để thay timeout, vì repository có thể dùng một client khác và phát sinh vấn đề vòng đời/bean.

**Durable KV:** `kvDurableTimeout` trong SDK là ranh giới riêng cho yêu cầu durability. Đối với YAML Spring Boot, kiểm tra chính xác nhóm property và tên được phiên bản hỗ trợ thay vì suy luận tên property từ Java method.

## 9. Một mutation timeout có thể đã được áp dụng

Đây là điểm quan trọng nhất khi kết hợp timeout với tính nhất quán dữ liệu. Với `upsert`, `replace` hoặc `remove`, có tình huống request tới được Couchbase Server nhưng response bị trễ hoặc mất. SDK có thể không chắc liệu server đã áp dụng thao tác.

Hai loại lỗi đáng biết:

- `UnambiguousTimeoutException`: SDK có thể xác định tình trạng timeout theo hướng không mơ hồ về khả năng thực thi theo hợp đồng lỗi.
- `AmbiguousTimeoutException`: SDK **không xác định chắc chắn** mutation đã được áp dụng hay chưa.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant SDK as SDK
    participant DB as Couchbase Server
    App->>SDK: upsert(order::123)
    SDK->>DB: mutation
    DB->>DB: Có thể đã ghi dữ liệu
    Note over DB,SDK: Response chậm hoặc mất
    SDK-->>App: AmbiguousTimeoutException
    Note over App,DB: Không được kết luận mutation chắc chắn thất bại
~~~

Vì thế:

1. **Đọc** thường có thể retry với giới hạn nếu thao tác và hoàn cảnh phù hợp.
2. **Ghi** phải xét idempotency theo nghiệp vụ. Upsert cùng key/content có thể khác bản chất với tăng tồn kho, trừ tiền hay tạo đơn hàng mới bằng ID mới.
3. Khi kết quả ghi mơ hồ, nên đối soát trạng thái qua document key/idempotency key trước khi quyết định thử lại.
4. **CAS** hoặc Spring Data `@Version` giúp bảo vệ cập nhật cạnh tranh, nhưng không biến mọi mutation thành an toàn để retry mù.
5. Timeout không phải cơ chế rollback một mutation đã được xử lý.

TTL điều khiển thời hạn tồn tại document; giao dịch có thời hạn, ngữ nghĩa commit/rollback và yêu cầu riêng. Không dùng KV timeout để đại diện tất cả các loại thời gian này.

## 10. Timeout, retry và deadline tổng phải phối hợp

Một HTTP request có nhiều giới hạn:

~~~text
Client gọi HTTP
└── Gateway / API deadline
    └── Service logic
        ├── KV call (SDK KV timeout)
        ├── SQL++ call (SDK Query timeout)
        └── Retry / xử lý nghiệp vụ
~~~

Nếu SDK timeout dài hơn deadline HTTP, client có thể đã bỏ cuộc nhưng thao tác còn đang chạy. Nếu timeout quá ngắn, request bình thường có thể thất bại khi tải tăng nhẹ.

| Lớp | Giá trị minh họa | Cách suy nghĩ |
| --- | --- | --- |
| API deadline | 3 s | Phải bao phủ toàn bộ công việc và phản hồi |
| KV read timeout | 800 ms | Theo p95/p99 và ngân sách nghiệp vụ |
| Query timeout | 1.5 s | Sau khi đã có index/plan phù hợp |
| Retry | Có giới hạn | Tính trong ngân sách tổng; xét idempotency |
| Connect timeout | 10 s | Chủ yếu liên quan lifecycle/client startup |

Các ngưỡng trên chỉ để minh họa cách phân bổ. Khi đặt time budget thực tế, hãy tính cả queueing, network, serialization, các lần retry, thao tác nối tiếp và yêu cầu SLA.

**Không mở một `Cluster.connect(...)` cho mỗi request để “làm mới” ngân sách timeout.** SDK client và Spring Data factory được thiết kế cho việc dùng chung. Nếu cần đặt giới hạn riêng, hãy dùng operation options hoặc ranh giới xử lý ở service.

## 11. Reactive: SDK timeout khác Reactor timeout

Spring Data Couchbase hỗ trợ `ReactiveCouchbaseRepository`, `ReactiveCouchbaseTemplate`, trong khi SDK cung cấp API reactive. Có hai lớp thời gian chờ:

- **SDK timeout**: cho thao tác Couchbase cụ thể.
- **Reactor `timeout(...)`**: cho pipeline reactive ở tầng ứng dụng, có thể bao trùm nhiều công việc.

Ví dụ:

~~~java
import java.time.Duration;
import com.couchbase.client.java.kv.GetOptions;
import com.couchbase.client.java.kv.GetResult;
import reactor.core.publisher.Mono;

Mono<GetResult> lookup = products.reactive()
        .get(
                "product::SKU-001",
                GetOptions.getOptions().timeout(Duration.ofMillis(900))
        )
        .timeout(Duration.ofSeconds(1));
~~~

Ở đây SDK get có budget 900 ms, pipeline Reactor có giới hạn 1 giây. Operator nào kết thúc trước ảnh hưởng lỗi quan sát. `timeout` hoặc cancel subscription **không bảo đảm một mutation chưa được server thực thi**.

Trong WebFlux, tránh `block()` trên event loop. Nếu thêm `retryWhen`, đừng quên tổng ngân sách và phân biệt read idempotent với mutation có kết quả mơ hồ. Reactive không tạo index hay tự tối ưu SQL++.

## 12. Chẩn đoán timeout theo đường đi

~~~mermaid
flowchart TD
    A["Timeout trong ứng dụng"] --> B{"Nhóm thao tác nào?"}
    B -- "Connect" --> C["DNS, mạng, TLS, topology<br/>connect budget"]
    B -- "KV" --> D["Data service, queue, node,<br/>KV / durable KV budget"]
    B -- "SQL++" --> E["Query service, index,<br/>plan, consistency, query budget"]
    C --> F["Đọc error context và metrics"]
    D --> F
    E --> F
    F --> G{"Mutation có kết quả mơ hồ?"}
    G -- "Có" --> H["Đối soát trạng thái, idempotency,<br/>CAS; tránh retry mù"]
    G -- "Không" --> I["Sửa nguyên nhân gốc,<br/>đo lại budget"]
~~~

| Triệu chứng | Nên kiểm tra | Không nên làm đầu tiên |
| --- | --- | --- |
| Timeout lúc bootstrap | Connection string, DNS, TLS, firewall, topology | Tạo index mới |
| `get(id)` timeout | Data service, queue, network, `kv` | Tăng `query` |
| Durable upsert timeout | Durability level, trạng thái cluster, ngân sách ghi | Coi như chắc chắn chưa ghi |
| `findById` chạy nhưng `findBySku` timeout | Query service, index đúng keyspace, plan, consistency | Tăng `connect` |
| Chậm dưới tải lớn | Concurrency, p95/p99, node metrics, retry | Tăng mọi timeout đồng loạt |
| HTTP deadline hết trước SDK | Tổng time budget, luồng hủy/retry | Mở client mới mỗi request |
| Mutation timeout rồi vẫn có dữ liệu | Ambiguous timeout, trạng thái document | Retry không kiểm tra |

### 12.1. Dữ liệu cần theo dõi

Nên ghi lại nhóm thao tác, thời gian thực tế, giới hạn được dùng, số lần retry, thông tin request context/error, bucket/scope/collection (không chứa bí mật), tỷ lệ lỗi và độ trễ P50/P95/P99 theo loại operation. Với query, nên thêm thông tin execution plan và trạng thái index khi điều tra.

Không log username/password, query parameters nhạy cảm hoặc toàn bộ nội dung document người dùng. Đặc biệt tránh dump mọi biến môi trường.

### 12.2. Đặt giả thuyết rồi đo lại

Nếu `findBySku` timeout:

1. Xác minh `findById` hoạt động trên đúng bucket/collection.
2. Kiểm tra Query service, RBAC và index.
3. Phân tích `EXPLAIN` và mức độ chọn lọc index.
4. Đo độ trễ ở tải thấp và khi tải thực tế.
5. Mới điều chỉnh `query` nếu ngân sách không phù hợp với truy vấn đã tối ưu.

Nếu `get(id)` timeout, không giải quyết bằng primary index: KV lookup theo ID không cần secondary index SQL++.

## 13. Kịch bản triển khai: ba API trên một client dùng chung

Giả sử inventory service có:

| Endpoint | Hành vi | Timeout liên quan nhất |
| --- | --- | --- |
| `GET /products/{id}` | KV read theo ID | KV timeout |
| `GET /products?sku=...` | SQL++ theo thuộc tính | Query timeout |
| `PUT /products/{id}` | Mutation, có thể durability/CAS | KV hoặc durable KV budget; kết quả ghi |

Một cấu hình ban đầu:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
    env:
      timeouts:
        connect: "${COUCHBASE_CONNECT_TIMEOUT:10s}"
        kv: "${COUCHBASE_KV_TIMEOUT:2s}"
        query: "${COUCHBASE_QUERY_TIMEOUT:8s}"
  data:
    couchbase:
      bucket-name: inventory
~~~

Giả sử dưới tải `GET /products/{id}` ổn định nhưng query tìm theo SKU thường vượt 8 giây: cần xem index `ix_products_sku`, plan và tài nguyên Query service. Không có lý do trực tiếp để tăng connect hay KV.

Nếu `PUT` gặp `AmbiguousTimeoutException`, phải tránh kết luận dữ liệu chưa ghi. Dùng document key ổn định, đối soát kết quả, thiết kế idempotency và CAS khi thích hợp.

## 14. Bài tập thực hành

Ứng dụng đơn hàng có bucket `orders`, scope `sales`, collection `order_documents`, mục tiêu API không quá 4 giây. Khi thử tải:

- `findById` thường kết thúc dưới 100 ms.
- Truy vấn SQL++ theo `customerId` đôi khi mất 9 giây.
- Mutation có durability trả timeout, nhưng sau đó đọc lại thấy document đã đổi.
- Instance mới trong container đôi khi không bootstrap được cluster.

Hãy thực hiện:

1. Phân loại bốn hiện tượng theo connect, KV, durable KV hoặc SQL++.
2. Viết cấu hình YAML có `connect`, `kv`, `query` với đơn vị thời gian.
3. Kiểm tra DNS, network, TLS và topology của container mới trước khi tăng connect budget.
4. Kiểm tra index trên keyspace `orders.sales.order_documents` và query plan trước khi tăng query budget.
5. Giải thích vì sao phải đối soát mutation và xây dựng idempotency/CAS thay vì retry ngay.
6. So sánh deadline 4 giây với ngân sách các thao tác bên trong; nếu query không thể đạt SLA, cân nhắc tối ưu hoặc thiết kế xử lý khác.

Index minh họa:

~~~sql
CREATE INDEX ix_order_customer
ON `orders`.`sales`.`order_documents`(`customerId`);
~~~

**Đáp án định hướng:** vấn đề bootstrap thuộc tầng connect; `findById` thuộc KV; query theo `customerId` thuộc Query; durable mutation có rủi ro kết quả mơ hồ. Index và query plan liên quan SQL++, còn HTTP deadline phải bao phủ tổng thời gian thao tác và xử lý. Timeout chỉ nên điều chỉnh sau khi đã tìm và đo nguyên nhân gốc.

## 15. Tổng kết

**Connect timeout** giới hạn giai đoạn kết nối SDK, **KV timeout** liên quan thao tác theo document ID, **query timeout** liên quan SQL++ qua Query service. Với Spring Boot, những cấu hình này thường nằm dưới `spring.couchbase.env.timeouts.*`; `spring.data.couchbase.bucket-name` vẫn chỉ xác định bucket mặc định.

Một chiến lược timeout vận hành tốt phải kết hợp client dùng chung, chỉ mục SQL++ phù hợp, tính nhất quán sau ghi, deadline tổng, metrics, retry có giới hạn và xử lý mutation có kết quả mơ hồ. Khi hiểu những ranh giới này, bạn có thể thiết kế repository, `CouchbaseTemplate`, TTL, CAS, giao dịch và reactive API hiệu quả mà không đánh đổi tính đúng đắn dữ liệu để lấy một timeout lớn hơn.

