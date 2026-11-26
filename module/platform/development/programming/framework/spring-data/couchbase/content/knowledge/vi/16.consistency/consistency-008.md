# Phân biệt kết quả cũ do chỉ mục với dữ liệu cũ trong bộ nhớ đệm

## 1. Vấn đề: cùng một bản ghi nhưng người dùng nhìn thấy phiên bản khác nhau

Trong ứng dụng **Spring Data Couchbase**, người dùng vừa cập nhật trạng thái đơn hàng từ `CREATED` sang `PAID`. API chi tiết đơn trả `PAID`, còn màn hình lịch sử vẫn hiển thị `CREATED`. Nhóm phát triển bật `REQUEST_PLUS` cho truy vấn SQL++ nhưng màn hình vẫn chưa đổi. Có phải Couchbase Index Service đang cập nhật chậm?

**Không thể kết luận như vậy.** Dữ liệu cũ có ít nhất hai nguyên nhân rất khác nhau:

1. **Chỉ mục chưa bắt kịp (index lag):** Query Service đang sử dụng secondary index chưa phản ánh mutation mới. SQL++ query có thể trả thiếu row, còn match điều kiện cũ hoặc có kế hoạch fetch/covering bị ảnh hưởng.
2. **Bộ nhớ đệm chưa được làm mới (stale cache):** Application, Redis, Caffeine, HTTP gateway/CDN hoặc browser đang trả lại **kết quả của một lần đọc trước**, thậm chí không gửi truy vấn mới tới Couchbase.

Hai nguyên nhân cần hai phương án khắc phục khác nhau. Đặt `REQUEST_PLUS` có thể giúp một truy vấn SQL++ thực sự được gửi tới Couchbase đợi index đủ mới; **nó không tự xóa kết quả đã được cache và không buộc cache gọi lại database**.

Bài học thuộc chương **Tính nhất quán** của module **SPRING_DATA_COUCHBASE**, nơi chúng ta xây tầng truy cập Couchbase qua document mapping, Repository, `CouchbaseTemplate`, SQL++ và Java SDK; đồng thời cân nhắc bucket/scope/collection, chỉ mục, TTL, CAS, transaction, reactive API, hiệu năng và khả năng vận hành.

**Sau bài này, bạn cần làm được:**

- Nhận diện chính xác nguồn dữ liệu cũ: document nguồn, GSI, Search index, cache hoặc lớp trình bày.
- Vẽ đường đi read/write và chỉ ra nơi có thể phát sinh độ trễ.
- Chẩn đoán theo thứ tự: KV source → SQL++ thực thi trực tiếp → service có/không cache → HTTP/UI.
- Giải thích vì sao `NOT_BOUNDED`, `REQUEST_PLUS` và `MutationState` không thay thế cache invalidation.
- Viết Spring Data Repository, SQL++ và Spring Cache minh họa chiến lược cache-aside, eviction và TTL.
- Tránh lỗi cache key thiếu tenant, invalidation không đầy đủ, race condition khi refill và lỗi self-invocation trong Spring.
- Thiết kế kiểm thử tích hợp có thể tái hiện cache stale một cách **deterministic**, nhưng không ép index luôn có lag.
- Đặt SLO độ mới riêng cho nguồn dữ liệu, chỉ mục và bộ nhớ đệm.

## 2. Bức tranh tổng thể: hai nơi “cũ” nằm ở hai tầng khác nhau

~~~mermaid
flowchart TD
    U["Client / Browser"] --> H["HTTP cache / CDN / reverse proxy"]
    H --> A["Spring Controller"]
    A --> C{"Application cache hit?"}
    C -->|Hit| R["Trả giá trị cache đã lưu"]
    C -->|Miss| S["Service / Repository / Template"]
    S --> KV["KV get theo document ID"]
    S --> Q["SQL++ query theo field"]
    KV --> D[("Data Service: document nguồn")]
    D --> I[("Index Service: secondary index")]
    I --> Q
    Q --> S
    S --> C
    R --> A
    A --> U
~~~

Sơ đồ khái quát; tùy ứng dụng, cache có thể ở service, Redis dùng chung, gateway, trình duyệt hoặc nhiều tầng cùng lúc. Không phải ứng dụng nào cũng bật sẵn những cache này.

**Sự khác biệt quan trọng:**

- **Index lag:** SQL++ query **đã chạy trên Couchbase**, nhưng index phục vụ truy vấn chưa phản ánh mutation ở mốc cần thiết.
- **Cache stale:** Có thể **chưa hề chạy query mới**; một giá trị đã lưu từ trước được trả lại theo cache key và chính sách hết hạn/invalidation.

Có trường hợp **cả hai cùng tồn tại**: một SQL++ query NOT_BOUNDED trả kết quả chưa mới, rồi application cache lại giữ kết quả đó thêm vài phút. Khi ấy khắc phục index freshness một mình không đủ.

## 3. Ví dụ xuyên suốt: khách hàng và đơn hàng

Giả sử collection nghiệp vụ là:

~~~text
Bucket       : shop
Scope        : sales
Collection   : orders
Document ID  : order::o-1001
~~~

Body trước khi thanh toán:

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 350000
}
~~~

Sau khi thanh toán thành công, dữ liệu nguồn trở thành:

~~~json
{
  "customerId": "c-1001",
  "status": "PAID",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 350000
}
~~~

Ứng dụng cung cấp:

1. `GET /orders/o-1001`: đọc một Order theo ID, có thể dùng KV và có thể được `@Cacheable`.
2. `GET /customers/c-1001/orders?status=PAID`: query SQL++ theo các field và index.
3. Trang lịch sử: dùng HTTP cache hoặc frontend state riêng tùy triển khai.
4. Một endpoint thanh toán: cập nhật Order qua Repository/SDK với kiểm soát concurrency.

Cùng một thay đổi `CREATED → PAID` có thể tạo các triệu chứng:

| Triệu chứng | Nguyên nhân cần nghi ngờ |
| --- | --- |
| KV đọc Order đã là PAID, SQL++ lọc status=PAID chưa có Order | Index/query plan/filter/consistency |
| KV đọc Order đã PAID, chạy SQL++ trực tiếp thấy PAID, service vẫn trả CREATED | Cache ở service/Redis, mapping hoặc đường code khác |
| Service trả PAID nhưng HTTP response trình duyệt vẫn CREATED | Gateway/CDN/browser cache hoặc UI state |
| Cache service miss nhưng lần SQL++ đầu trả CREATED rồi bị cache lại | Index lag **kết hợp** cache stale |
| Hai instance Spring trả khác nhau cho cùng URL | Cache local riêng từng instance hoặc cấu hình deployment khác |
| SQL++ REQUEST_PLUS thành công nhưng UI vẫn cũ | Cache/frontend nằm **sau** SQL++ hoặc không gửi query mới |

Hãy luôn xác nhận đường dữ liệu thực tế thay vì mặc định “do Couchbase”.

## 4. Khái niệm nền: “độ mới” không phải một thuộc tính duy nhất

Có ít nhất năm lớp cần tách:

| Lớp | Định nghĩa độ mới | Ví dụ công cụ |
| --- | --- | --- |
| **Document nguồn** | Mutation đã được xác nhận và đọc theo đúng active KV path | SDK `Collection.get`; `findById` |
| **Secondary index GSI** | Index đã xử lý mutation tới mốc nào trước khi scan | SQL++, `QueryScanConsistency` |
| **Application cache** | Giá trị trong cache có được thay thế/loại bỏ sau mutation hay chưa | Spring Cache, Caffeine, Redis |
| **HTTP/CDN cache** | HTTP response có được cache và còn hiệu lực theo header/policy không | `Cache-Control`, `ETag`, gateway |
| **Frontend state** | UI đang hiển thị response mới hay snapshot đã lưu trong client | Query cache của SPA, state store |

Ngoài ra còn **replica reads**, **Search/FTS index**, đồng bộ cross-cluster và background read models. Chúng có semantics riêng; đừng gộp vào “SQL++ index lag” chỉ vì triệu chứng đều là dữ liệu chưa cập nhật.

### 4.1. Spring Data Couchbase không có persistence context kiểu JPA

Một entity Java đã đọc không tự được Spring Data Couchbase quản lý dirty checking như trong JPA. Thay đổi object Java **không tự flush xuống database**. Nhưng một object đã được **ứng dụng giữ lại trong memory/cache** vẫn có thể cũ. Đây là hai vấn đề riêng:

- **Không gọi `save`:** database có thể chưa bao giờ nhận mutation.
- **Đã gọi `save` thành công nhưng cache chưa invalidation:** database đã đổi, application vẫn trả bản cũ.

Đừng dùng tư duy `EntityManager.refresh` của JPA để giải quyết vấn đề thiếu invalidation trong Spring Cache.

## 5. Timeline A: dữ liệu cũ do secondary index

~~~text
T0  KV replace Order.status = PAID thành công
T1  Active KV get(order::o-1001) -> PAID
T2  GSI theo status chưa áp dụng mutation
T3  SQL++ NOT_BOUNDED WHERE status = "PAID"
    -> có thể chưa trả Order mới đổi trạng thái
T4  Index Service bắt kịp mutation
T5  SQL++ theo status -> có thể trả Order
~~~

Cách quan sát trực tiếp:

- Đọc KV theo metadata ID để xác minh body nguồn.
- Chạy **SQL++ thực sự tới Couchbase**, không đi qua cached service.
- Đối chiếu cùng query với `NOT_BOUNDED` và `REQUEST_PLUS` nếu API hỗ trợ.
- Xem index trạng thái online, generated SQL++ và `EXPLAIN`.

`REQUEST_PLUS` yêu cầu index liên quan theo kịp các mutation tới mốc xác định khi query bắt đầu, nên có thể tránh việc đọc trước khi index đủ mới. Nó có thể phải chờ Index Service và tăng latency/timeout.

**Không có quy tắc SQL++ NOT_BOUNDED luôn stale.** Trên cluster ít tải, index có thể cập nhật kịp trước lần query đầu tiên.

## 6. Timeline B: dữ liệu cũ do cache

~~~text
T0  GET /orders/o-1001
    -> cache miss -> KV get status=CREATED
    -> cache lưu Order(CREATED)

T1  POST /orders/o-1001/pay
    -> Couchbase ghi status=PAID thành công
    -> cache entry cũ KHÔNG bị loại bỏ

T2  GET /orders/o-1001
    -> cache hit -> Order(CREATED)
    -> KHÔNG có KV get mới

T3  TTL cache hết hạn hoặc entry bị evict
T4  GET /orders/o-1001
    -> cache miss -> KV get status=PAID
~~~

Ở đây không liên quan index. Ngay cả `REQUEST_PLUS` mạnh nhất trên một SQL++ query **cũng không tác động** vì request tại T2 được phục vụ ngay từ cache. Nếu data source của entry cache là KV read, thậm chí không có SQL++ trong luồng này.

### 6.1. Một tình huống nguy hiểm: cache lại kết quả query index chưa mới

~~~text
T0  Ghi Order mới thành công
T1  Query NOT_BOUNDED (index chưa bắt kịp) -> lịch sử thiếu Order
T2  Application cache lưu danh sách thiếu Order (TTL 5 phút)
T3  Index bắt kịp mutation
T4  Lịch sử vẫn thiếu Order vì cache hit
T5  Sau TTL hoặc invalidation, query mới mới lấy kết quả khác
~~~

Nguyên nhân đầu tiên là index lag nhưng **thời gian tồn tại kết quả sai kéo dài do cache**. Đây là lý do cần chẩn đoán **cả index lẫn cache**, không chọn một trong hai như những khả năng loại trừ hoàn toàn nhau.

## 7. Bảng phân biệt nhanh khi điều tra sự cố

| Phép thử | Nếu lỗi do index lag | Nếu lỗi do application cache |
| --- | --- | --- |
| Active KV get theo ID | Có thể thấy mutation mới | Cũng có thể thấy mutation mới |
| Query SQL++ trực tiếp bypass app cache | Có thể stale với NOT_BOUNDED | Thường đã mới nếu index kịp |
| SQL++ trực tiếp với REQUEST_PLUS | Có cơ chế đợi index đủ mới | Không thay cache entry |
| Gọi service khi cache hit | Có thể không chạm Index Service | Có thể trả giá trị cũ lặp lại |
| Evict riêng cache key rồi gọi lại | Có thể vẫn stale nếu SQL++ chưa bắt kịp | Thường thấy mới nếu nguồn/query mới |
| Đợi index bắt kịp nhưng không evict | Query trực tiếp trở nên mới | Service cache có thể vẫn cũ |
| Hai application instance trả khác nhau | Không đủ chứng minh chỉ do index | Gợi ý local cache không đồng bộ, nhưng còn phải kiểm tra đường code |
| Query Service log/metric không tăng khi gọi endpoint | Khó do một SQL++ query mới ở request đó | Dấu hiệu request đã được trả ở cache hoặc lớp trước |

**Một phép thử đơn lẻ không phải kết luận tuyệt đối.** Ví dụ evict cache rồi vẫn cũ có thể là index lag, cache ở tầng HTTP khác, sai collection hoặc query filter. Dùng nhiều bằng chứng ghép lại.

## 8. Phương pháp chẩn đoán có thứ tự

~~~mermaid
flowchart TD
    A["Người dùng báo dữ liệu cũ"] --> B{"Write đã được ACK?"}
    B -->|Không rõ / timeout| C["Kiểm tra trạng thái theo key và idempotency"]
    B -->|Có| D["Đọc active KV theo ID"]
    D --> E{"KV phản ánh giá trị mới?"}
    E -->|Không| F["Kiểm tra write path, keyspace, replica, TTL, transaction"]
    E -->|Có| G["Gọi SQL++ trực tiếp, bỏ qua cache ứng dụng"]
    G --> H{"SQL++ trực tiếp đúng?"}
    H -->|Không| I["Xem index plan, WHERE, REQUEST_PLUS, index lag"]
    H -->|Có| J["Gọi service với và không với cache"]
    J --> K{"Service còn cũ?"}
    K -->|Có| L["Cache key/eviction/TTL/instance"]
    K -->|Không| M["HTTP gateway/CDN/browser/frontend state"]
~~~

### 8.1. Giai đoạn 1 — Xác minh write

- Request trả thành công thật hay chỉ optimistic UI?
- Document ID, bucket, scope, collection có đúng không?
- Thao tác `save`/`replace` đã được gọi hay object Java chỉ thay đổi trong memory?
- Có optimistic locking/CAS conflict hoặc transaction rollback không?
- Nếu timeout, có nguy cơ ghi thành công nhưng client không nhận ACK không?

Không nên kết luận “index chưa cập nhật” nếu database thực sự **chưa được ghi**.

### 8.2. Giai đoạn 2 — Xác minh source qua KV

Dùng `findById` hoặc Couchbase Java SDK `collection.get(id)` trên **đúng collection và active path**. Nếu source vẫn CREATED thì giải quyết đường ghi, không bắt đầu bằng xóa mọi cache.

### 8.3. Giai đoạn 3 — Xác minh query index

Thực thi SQL++ trực tiếp với đúng parameter, cùng keyspace, kiểm tra `EXPLAIN` và mức scan consistency. Nếu REQUEST_PLUS thành công và query logic đúng mà kết quả đã mới, nguồn SQL++ không phải nguyên nhân của **response service đang cũ** ở thời điểm này.

### 8.4. Giai đoạn 4 — Bypass từng tầng cache

Tại môi trường test/diagnostics được kiểm soát:

- Gọi trực tiếp Repository/Template/SDK thay vì method `@Cacheable`.
- So sánh cache hit/miss và thời gian source query.
- Evict **đúng key** và gọi lại, kiểm tra cache khác có đang bọc tiếp không.
- Thử qua từng instance để nhận biết local cache khác nhau.
- Kiểm tra HTTP headers, status `304`, CDN caching và frontend query cache.
- Không bật cơ chế “bypass cache” công khai cho người dùng bất kỳ nếu nó gây tải hoặc lộ dữ liệu.

## 9. Tách sai khác của kết quả query và body document

Trong SQL++, cách query dùng index ảnh hưởng dạng sai khác:

- **Index chưa có insert mới:** query theo field có thể thiếu ID mới.
- **Index chưa áp dụng thay đổi field:** query có thể còn/không còn match điều kiện lọc.
- **Index chưa áp dụng xóa:** index có thể còn dấu vết của document đã remove.
- **Covering query:** một số field có thể được trả từ index mà không fetch body.
- **Non-covering query:** Query Service có thể fetch body nguồn khi cần, khiến row/value quan sát khác so với việc chỉ đọc index.

Vì vậy, **không khẳng định** “index lag đồng nghĩa SQL++ luôn trả toàn bộ JSON cũ”. Phải phân tích query plan, field predicate, projection và việc fetch.

### 9.1. Phân biệt query plan cache với result cache

Việc Couchbase Query Service có thể dùng **prepared statement/plan caching** không có nghĩa nó mặc định trả lại **rows dữ liệu cũ** từ một result cache. Prepared plan tái sử dụng cách thực thi, không đồng nghĩa tái sử dụng tập kết quả cũ. Cũng không mặc định Java SDK/Repository tự cache mọi kết quả SQL++.

Khi nói “cache stale”, phải chỉ ra **cache nào thực sự được cấu hình và đang phục vụ kết quả**, không suy từ việc truy vấn dùng prepared statement.

## 10. Mức SQL++ consistency chỉ điều khiển đường query thực sự chạy

Couchbase SQL++ thường cung cấp:

| Chế độ | Mục tiêu | Giới hạn |
| --- | --- | --- |
| `NOT_BOUNDED` | Không yêu cầu index đợi mutation mới trước scan | Có thể dùng index chưa theo kịp |
| `REQUEST_PLUS` | Đợi index liên quan bắt kịp mốc request trước scan | Có thể tăng latency; không sửa cache |
| `AT_PLUS` / `consistentWith(state)` | Đợi index phản ánh các mutation token cụ thể | Cần token/state phù hợp; không sửa cache |

Điều không đổi với cả ba:

- Query chưa được gọi vì cache hit thì **không có scan consistency nào được thực thi**.
- Cache nằm **sau** query có thể lưu kết quả vừa đọc rồi tiếp tục trả lại sau khi index đã thay đổi.
- Một row bị loại bởi `WHERE`/`LIMIT` không tự xuất hiện nhờ consistency cao.
- Chế độ scan consistency không bảo vệ CAS, transaction hoặc uniqueness.

### 10.1. Tại sao REQUEST_PLUS có thể đúng nhưng người dùng vẫn thấy cũ?

Ví dụ service:

~~~java
@Cacheable(cacheNames = "order-history", key = "#customerId")
public List<OrderDocument> history(String customerId) {
    // Repository method được gắn REQUEST_PLUS.
    return orderRepository.findFreshByCustomerId(customerId);
}
~~~

Khi key `customerId` đã có entry, Spring Cache trả kết quả trước khi chạy method body, nên `findFreshByCustomerId` **không được gọi**. Đây là lý do một annotation về consistency ở Repository không thể thay chính sách cache.

## 11. Spring Data Repository: tạo đường đọc không cache để kiểm chứng

Entity tối giản:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;

    @Field
    private String customerId;

    @Field
    private String status;

    @Field
    private String createdAt;

    @Version
    private Long version;

    public OrderDocument() { }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getCustomerId() { return customerId; }
    public void setCustomerId(String v) { this.customerId = v; }
    public String getStatus() { return status; }
    public void setStatus(String v) { this.status = v; }
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String v) { this.createdAt = v; }
    public Long getVersion() { return version; }
    public void setVersion(Long v) { this.version = v; }
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;
import com.couchbase.client.java.query.QueryScanConsistency;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    // Query theo field; mặc định thường không đòi index bắt kịp.
    List<OrderDocument> findByCustomerId(String customerId);

    // Query riêng có yêu cầu freshness cao.
    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    List<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

- `findById(id)` thường đi KV, không cần secondary index.
- Hai derived query theo field thường chạy SQL++/index.
- `@ScanConsistency` có tác dụng **khi method query thực sự được gọi**, không xử lý bộ nhớ đệm trước method.
- `@Version` dùng CAS cho optimistic locking, không phải index freshness hoặc cơ chế invalidation cache.

Để production tránh query trả dữ liệu không giới hạn, nên thêm `Pageable`/`Slice`/`Page` hoặc một truy vấn có `LIMIT` phù hợp. Mã trên giúp làm rõ đường đi và annotation, chưa phải thiết kế pagination cuối cùng.

## 12. SQL++ và index: chẩn đoán đúng query trước khi đổ lỗi cho cache

Truy vấn ví dụ:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Index khởi đầu:

~~~sql
CREATE INDEX ix_orders_customer_status_date
ON `shop`.`sales`.`orders`(customerId, status, createdAt DESC);
~~~

Cần xác minh:

1. Index tồn tại và online trên keyspace đúng.
2. Generated SQL++ từ Spring Data có thể thêm type discriminator; query SDK thô có thể khác.
3. `EXPLAIN` cho thấy index plan hợp lý; điều kiện lọc/sort/projection phục vụ use case.
4. Parameter binding được sử dụng, không nối input tùy ý vào SQL++.
5. Tenant/authorization filter không vô ý loại Order.
6. `LIMIT 20` không loại document mong đợi vì 20 Order khác mới hơn.

Một query trực tiếp với `REQUEST_PLUS` thành công có kết quả đúng là **bằng chứng mạnh để chuyển hướng kiểm tra cache** khi service vẫn trả nội dung cũ. Nó không tự chứng minh mọi request HTTP đều đi đúng đường code.

## 13. Kiểm tra trực tiếp bằng Java SDK mà không đi qua Spring Cache

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

public class DirectCouchbaseDiagnostics {
    private final Cluster cluster;
    private final Collection orders;

    public DirectCouchbaseDiagnostics(Cluster cluster) {
        this.cluster = cluster;
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    public JsonObject getById(String id) {
        return orders.get(id).contentAsObject();
    }

    public QueryResult listPaidByCustomer(String customerId) {
        String sql = """
            SELECT META(o).id AS documentId,
                   o.customerId, o.status
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
              AND o.status = "PAID"
            """;

        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS);

        return cluster.query(sql, options);
    }
}
~~~

Ở đây **không có annotation Spring Cache**, nên hai method thực sự gọi Couchbase khi được thực thi. Truy vấn SQL++ sử dụng index phù hợp và chịu semantics REQUEST_PLUS; KV get không dùng secondary index. Để tránh rò rỉ thông tin, chỉ vận hành diagnostic này trong môi trường được cấp quyền và không log toàn bộ body hoặc credential.

Lưu ý: SDK direct query **không tự dùng** converter và type discriminator của Spring Data. Nếu JSON/schema khác nhau, kết quả Repository và SDK có thể khác do mapping, không chỉ do consistency.

## 14. Cache ở ứng dụng Spring: cơ chế cache-aside

Trong Spring Boot, một cách phổ biến là bật Spring Cache:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
}
~~~

Một service đọc chi tiết:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class OrderDetailReadService {
    private final OrderRepository repository;

    public OrderDetailReadService(OrderRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "order-by-id", key = "#documentId")
    public OrderDocument detail(String documentId) {
        return repository.findById(documentId)
                .orElseThrow();
    }
}
~~~

Luồng:

- Cache miss → chạy Repository KV get → cache kết quả theo key.
- Cache hit → trả entry đã lưu → **không thực thi Repository**.
- Nếu một thao tác ghi khác đổi Order mà không eviction/update cache, entry vẫn chứa trạng thái cũ.

`@EnableCaching`/`@Cacheable` không tự tạo cơ chế coherency phân tán với Couchbase KV. Provider cache có thể là cache trong JVM, Redis hoặc một cấu hình khác. Hãy xác định provider thực sự và policy TTL/eviction.

### 14.1. Cache key phải biểu diễn đủ ngữ cảnh

Không chỉ tránh collision giữa hai Order ID. Với ứng dụng multi-tenant hoặc dữ liệu có quyền truy cập riêng, cache key còn phải đảm bảo tách biệt **tenant, quyền/role, locale, filter, sort, page** theo những yếu tố ảnh hưởng kết quả.

Ví dụ ý tưởng:

~~~text
tenantId + customerId + status + pageSize + cursor
~~~

Tuy nhiên, **cache key không thay cho authorization**. Kiểm tra quyền truy cập trước khi trả dữ liệu và thiết kế cache tránh rò rỉ dữ liệu giữa người dùng/tenant.

## 15. Eviction sau ghi: một ví dụ có kiểm soát

Khi cập nhật một Order, có thể cấu hình eviction cho cache chi tiết:

~~~java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;

@Service
public class OrderWriteService {
    private final OrderRepository repository;

    public OrderWriteService(OrderRepository repository) {
        this.repository = repository;
    }

    @CacheEvict(cacheNames = "order-by-id", key = "#documentId")
    public OrderDocument changeStatus(
            String documentId, String newStatus) {

        OrderDocument order = repository.findById(documentId)
                .orElseThrow();

        order.setStatus(newStatus);
        return repository.save(order);
    }
}
~~~

Với annotation Spring Cache thông thường, eviction sau method được gọi khi method hoàn tất thành công; nếu method thất bại trước đó, eviction mặc định không chạy. Điều này phù hợp hơn xóa cache **trước khi** mutation đã được xác nhận.

Nhưng đây chỉ là **mẫu cơ bản**, có những giới hạn:

1. Một lệnh ghi ở code path **khác** (SDK, batch job, dịch vụ khác) không tự gọi method eviction.
2. Cập nhật Order có thể ảnh hưởng **cache danh sách** theo customerId/status, không chỉ cache chi tiết theo Order ID.
3. Cập nhật nhiều document trong transaction đòi xác định eviction **sau commit** phù hợp, không đơn giản chỉ sau khi method Java return.
4. Giữa cache miss và cache evict có thể xảy ra race làm cache bị refill bằng dữ liệu cũ.
5. Nếu eviction thất bại nhưng write đã commit, phải có cơ chế phục hồi/retry/TTL tương ứng.

Không dùng `@CacheEvict` như công cụ thay thế CAS hoặc giao dịch. `@Version`/CAS bảo vệ concurrent update của document; cache eviction phục vụ độ mới cho những lần đọc tiếp theo.

## 16. Cache danh sách khó invalidation hơn cache một document

Giả sử cache lưu kết quả `findByCustomerIdAndStatus("c-1001", "CREATED")`. Khi Order chuyển sang `PAID`, hệ thống phải cân nhắc cả:

- Danh sách `CREATED`: Order không còn thuộc tập kết quả.
- Danh sách `PAID`: Order mới cần xuất hiện.
- Các trang/sort/filter khác của cùng khách.
- Cache tổng hợp/dashboard nếu ứng dụng dùng.
- Các instance khác hoặc cache ngoài JVM.

Một thao tác chỉ evict `order-by-id:order::o-1001` **không đủ** làm mới mọi danh sách.

### 16.1. Cách đơn giản cho bài thực hành

Có thể evict toàn bộ cache danh sách:

~~~java
@CacheEvict(cacheNames = "order-history", allEntries = true)
public OrderDocument saveOrder(OrderDocument order) {
    return repository.save(order);
}
~~~

Cách này dễ hiểu nhưng **có thể gây cache stampede** và giảm hit rate nếu dữ liệu lớn hoặc tốc độ ghi cao. Không xem đây là mặc định phù hợp production.

### 16.2. Cách có chọn lọc

Thiết kế key theo customerId/status/filter/page và lưu một mapping phụ hoặc chiến lược theo nhóm key để evict các kết quả bị ảnh hưởng. Khi Order đổi customerId, cần invalidation **cả nhóm cũ lẫn nhóm mới**.

Một số lựa chọn khác:

- TTL ngắn cho các danh sách chấp nhận lag.
- Cache kết quả tổng hợp theo cửa sổ thời gian, không cache danh sách giao dịch nhạy cảm.
- Versioned cache key hoặc namespace version do ứng dụng duy trì.
- Event-driven invalidation sau commit, với cơ chế xử lý mất/sai thứ tự sự kiện.
- Bỏ cache trên những query mà chi phí invalidation lớn hơn lợi ích cache.

Không đưa ra một quy tắc “evict bằng customerId” nếu cache key thực tế còn chứa tenant, status và cursor: phải giải được chính xác các entry bị ảnh hưởng.

## 17. TTL của cache khác TTL/expiry của Couchbase

Hai thuật ngữ giống nhau nhưng thuộc hai hệ thống độc lập.

| Khái niệm | Vị trí | Ý nghĩa |
| --- | --- | --- |
| **Couchbase document TTL** | Metadata/expiry của document trong Data Service | Document hết hiệu lực theo policy lưu trữ |
| **Cache TTL** | Caffeine/Redis/application cache/HTTP cache | Bản sao kết quả được giữ bao lâu trước khi expire |
| **JSON field `expiresAt`** | Business data trong body | Không tự tạo Couchbase TTL nếu không có cấu hình/API |
| **HTTP `max-age`** | Cache-control policy của response | Client/proxy có thể dùng response cũ trong khoảng cho phép |

Ví dụ:

~~~text
Couchbase Order vẫn hợp lệ 10 năm
Application cache giữ bản Order 60 giây
HTTP cache giữ response 30 giây
~~~

Độ mới người dùng nhìn thấy phụ thuộc mọi tầng đang tham gia. Nếu dữ liệu nguồn đổi ngay sau cache fill, người dùng có thể còn thấy bản cũ tới lúc cache được invalidation/hết hạn. **TTL chỉ giới hạn thời gian sống theo policy**, không bảo đảm mọi lần đọc sau ghi đều mới.

Đặc biệt, TTL cho session/security token phải phối hợp giữa nguồn có thẩm quyền, revoke và cache; đừng để cache tiếp tục công nhận session đã hết hiệu lực chỉ vì entry chưa expire.

## 18. Caffeine/local cache và Redis/distributed cache có đặc tính khác nhau

| Đặc điểm | Local cache trong mỗi JVM | Distributed cache như Redis |
| --- | --- | --- |
| Phạm vi | Mỗi instance có entry riêng | Nhiều instance có thể dùng chung |
| Ưu điểm | Truy cập rất nhanh, không cần network | Chia sẻ trạng thái cache giữa instance |
| Khi một instance update rồi evict | Instance khác có thể còn bản cũ | Evict chung key dễ phối hợp hơn nếu cùng Redis |
| Độ khó invalidation | Cần broadcast hoặc TTL nếu nhiều instance | Cần xử lý race, lỗi mạng, consistency của thao tác cache |
| Khi cache không khả dụng | Có thể fallback tới database tùy thiết kế | Phải có policy degrade/fallback và timeout |

Đừng mặc định Redis **tự bảo đảm** đồng bộ với Couchbase. Redis chỉ là nơi lưu cache; ứng dụng vẫn phải cập nhật/loại bỏ entry đúng thời điểm. Đồng thời, một instance có thể có cả local cache phía trước Redis, tạo thêm một tầng phải invalidation.

### 18.1. Dấu hiệu cache local không đồng bộ

Nếu request tới instance A trả `PAID` còn instance B vẫn trả `CREATED`, cần kiểm tra:

- Cache provider có phải local của từng instance không.
- Có eviction được truyền đến mọi instance không.
- Load balancer có sticky session hoặc routing khác không.
- Các instance có cấu hình cùng keyspace, version và schema không.
- Có deployment rolling gây response khác format không.

Chênh lệch giữa instance là dấu hiệu hữu ích, **không đủ để kết luận duy nhất do cache**.

## 19. Cache ở HTTP, CDN và trình duyệt

Ngay cả khi Spring Service trả đúng Order, HTTP response có thể được cache theo headers:

~~~http
Cache-Control: private, max-age=30
ETag: "order-o-1001-v3"
~~~

Ví dụ chỉ minh họa cú pháp, không phải cấu hình phải dùng. Với dữ liệu đơn hàng cá nhân hoặc nhạy cảm, chính sách cache phải xét quyền truy cập, bảo mật và tuân thủ. Trong nhiều ứng dụng, response nhạy cảm nên dùng chính sách không lưu cache hoặc cache riêng có kiểm soát.

Các cơ chế cần biết:

- **Browser cache:** response có thể được dùng lại trước khi gửi request mới.
- **CDN/reverse proxy:** cache response nếu cấu hình cho phép; phân biệt nội dung public và private.
- **ETag/If-None-Match:** cơ chế kiểm tra điều kiện HTTP; server có thể trả `304 Not Modified` khi representation chưa đổi theo hợp đồng.
- **SPA client query cache:** thư viện/frontend có thể giữ dữ liệu và chưa refetch dù server đã cập nhật.
- **Optimistic UI:** giao diện tự cập nhật trước khi write commit; sau lỗi có thể không rollback đúng.

### 19.1. Cách chẩn đoán

Kiểm tra developer tools Network: có request mới không, status gì, response header nào, response body thực tế có giá trị mới không, response được phục vụ từ memory/disk cache hay network. Phân biệt `304` là một cơ chế revalidation hợp lệ với việc frontend cố tình giữ state cũ.

Một SQL++ `REQUEST_PLUS` **không thể làm trình duyệt bỏ qua cache HTTP**. Phải điều chỉnh Cache-Control, ETag/revalidation hoặc chính sách refetch của frontend.

### 19.2. Không phơi cache bừa bãi với thông tin cá nhân

Cache key có chứa tenant/user/permission có thể cần thiết, nhưng không ghi toàn bộ thông tin nhạy cảm vào URL, log hay cache key public. Cấu hình CDN không được để dữ liệu của người A bị dùng cho người B. Cache invalidation không được làm mất kiểm soát quyền truy cập.

## 20. Race condition khiến cache cũ tái xuất hiện sau eviction

Ngay cả khi code đã evict khi ghi, vẫn có thể xảy ra **stale refill**:

~~~mermaid
sequenceDiagram
    participant R1 as Request đọc A
    participant R2 as Request ghi B
    participant DB as Couchbase
    participant C as Cache
    R1->>C: Cache miss
    R1->>DB: Read Order = CREATED
    DB-->>R1: CREATED
    R2->>DB: Save Order = PAID
    DB-->>R2: ACK
    R2->>C: Evict key
    R1->>C: Put CREATED (hoàn tất muộn)
    Note over C: Cache lại cũ dù đã evict
~~~

Đây không phải index lag. Nó cũng có thể xảy ra khi nguồn dữ liệu của A là KV hoàn toàn nhất quán tại thời điểm đọc.

### 20.1. Các chiến lược giảm rủi ro

- **Versioned cache keys:** key chứa version/epoch do ứng dụng quản lý; reader mới không dùng entry version cũ.
- **So sánh CAS/version tại cache write:** nếu provider/thiết kế hỗ trợ, không cho bản cũ ghi đè entry mới.
- **Invalidate sau commit + event ordering:** xử lý sự kiện ở đúng thứ tự hoặc có khả năng bỏ qua event cũ.
- **Short TTL + fallback:** giới hạn thời gian chịu stale nếu nghiệp vụ cho phép.
- **Không cache dữ liệu quyết định nhạy cảm:** dùng nguồn dữ liệu có thẩm quyền khi yêu cầu tính đúng đắn cao.

Không phải cứ thêm `@CacheEvict` là có **linearizable cache coherence** dưới mọi concurrency. Phải xác định mô hình consistency của cache theo yêu cầu.

## 21. Chọn chính sách từ SLO về độ mới

Một yêu cầu “dữ liệu luôn realtime” không đủ để chọn thiết kế. Nên đặt từng hợp đồng cụ thể:

| Use case | Freshness yêu cầu | Đường đọc và cache gợi ý |
| --- | --- | --- |
| Xác nhận Order vừa tạo | Thấy Order đã ACK | Trả saved representation/KV; tránh cache cũ |
| Chi tiết Order đang thanh toán | Không hiển thị trạng thái sai ảnh hưởng quyết định | KV và kiểm soát cache chặt hoặc không cache |
| Lịch sử Order sau POST | Danh sách phải gồm Order nếu filter/page đúng | SQL++ REQUEST_PLUS hoặc mutation-based + cache invalidate |
| Danh sách lịch sử thông thường | Có thể chấp nhận lag theo SLO | NOT_BOUNDED + cache TTL phù hợp nếu có lợi |
| Dashboard doanh thu | Cập nhật theo chu kỳ cho phép | Tổng hợp/read model và cache có timestamp |
| Email duy nhất khi đăng ký | Không được tạo trùng | Conditional write/transaction, không dựa vào query/cache |
| Session còn hiệu lực | Không công nhận session expired/revoked | KV key + expiry/revocation; tránh cache stale |
| Search sản phẩm | Độ mới theo Search SLO | Search index/cache policy riêng |

**Độ mới có thể mất ở nhiều tầng:** Nếu cho phép GSI trễ một khoảng và cache thêm một khoảng, thời gian nhìn thấy cuối cùng có thể dài hơn mỗi thành phần riêng. Không cộng các TTL thành một bảo đảm toán học đơn giản nếu cơ chế refresh, invalidation và concurrency chưa được xác định.

### 21.1. Tránh vừa cache lâu vừa ép query REQUEST_PLUS

Nếu một cache giữ danh sách 10 phút, nhưng lúc miss query dùng REQUEST_PLUS để đợi index, người dùng vẫn có thể thấy danh sách cũ trong 10 phút sau write. Chỉ đổi consistency của miss path không đáp ứng hợp đồng read-your-writes.

### 21.2. Khi nào bỏ cache?

Không cache có thể là lựa chọn đúng nếu dữ liệu nhỏ, truy cập ít, yêu cầu fresh nghiêm ngặt hoặc invalidation quá phức tạp. Trước khi thêm cache, cần đo query cost, hit rate, memory/network, tần suất mutation và chi phí stale.

## 22. Monitoring: tách chỉ số database và cache

| Nhóm metric | Ví dụ | Giúp chẩn đoán |
| --- | --- | --- |
| KV | Write ACK latency, get latency, CAS conflict | Dữ liệu nguồn/ghi cạnh tranh |
| Query | SQL++ p50/p95/p99, timeout, query count | Query có chạy/chậm không |
| Index | Mutation backlog/lag, index state, scan load | GSI theo kịp nguồn đến đâu |
| Cache application | Hit/miss/eviction/expiry, entry age, load time | Response được phục vụ từ cache cũ không |
| Distributed cache | Redis latency/error, invalidation failures | Cache dùng chung có lỗi đồng bộ không |
| HTTP | Cache HIT/MISS, `Age`, `ETag`, `304`, CDN status | Response có đi tới backend không |
| Frontend | Query invalidation/refetch, client state age | UI có nhận body mới nhưng không render không |
| Business | Thời gian từ order paid tới khi UI thấy paid | Freshness cuối-đầu thực tế |

Khi tracing, thêm correlation ID và các span biểu thị **cache hit/miss**, repository/SDK call và Couchbase query duration. Không log password, bearer token, dữ liệu thanh toán hay PII đầy đủ.

### 22.1. Một trace mẫu

~~~text
requestId = req-123
endpoint = GET /orders/order::o-1001
cache.name = order-by-id
cache.hit = true
db.kv.get.called = false
response.status = CREATED
~~~

Nếu trace này xuất hiện sau một write đã ACK `PAID`, vấn đề nằm ở **cache path**, không cần bắt đầu bằng điều chỉnh Index Service.

Ngược lại:

~~~text
cache.hit = false
db.query.called = true
scanConsistency = NOT_BOUNDED
indexLag = observed/high
resultContainsOrder = false
~~~

thì độ mới index là một giả thuyết cần kiểm chứng bằng REQUEST_PLUS và query plan.

## 23. Test 1: tái hiện cache stale một cách xác định

Khác với index lag, **cache stale có thể tái hiện có chủ đích** bằng cách không invalidation entry khi cập nhật nguồn.

Một test case ở mức hành vi:

~~~text
1. Seed Order(status=CREATED) bằng Repository/SDK.
2. Gọi OrderDetailReadService.detail(id) để điền cache.
3. Mutation trực tiếp vào nguồn Couchbase thành status=PAID,
   cố tình đi qua code path không evict cache.
4. Đọc nguồn KV theo id -> kỳ vọng PAID.
5. Gọi OrderDetailReadService.detail(id) -> có thể vẫn CREATED
   nếu provider lưu snapshot/serialized value riêng.
6. Evict đúng cache key.
7. Gọi OrderDetailReadService.detail(id) -> kỳ vọng PAID.
~~~

Trong thực tế cần lưu ý provider:

- Redis cache thường lưu dạng serialized representation, thuận tiện để tái hiện stale snapshot.
- Một local cache có thể giữ **cùng object Java reference**; nếu test tự sửa object đó in-place, cache cũng “đổi theo” và test mất ý nghĩa. Nên cập nhật nguồn bằng SDK riêng hoặc tạo object độc lập.
- Spring Cache hoạt động qua proxy: lời gọi nội bộ `this.detail(id)` trong cùng bean có thể **không đi qua caching advice** với mô hình proxy mặc định. Test nên gọi method trên Spring-managed bean từ bên ngoài.

### 23.1. Một cách kiểm chứng tối thiểu

~~~java
// Pseudocode test fixture; giả định các bean được inject.
OrderDocument original = cachedRead.detail(id);
assertEquals("CREATED", original.getStatus());

// Cập nhật Couchbase qua code path cố ý không evict cache.
sdkOrders.mutateIn(id, List.of(
        MutateInSpec.replace("status", "PAID")));

assertEquals("PAID",
        sdkOrders.get(id).contentAsObject().getString("status"));

// Nếu cache provider giữ snapshot độc lập:
assertEquals("CREATED", cachedRead.detail(id).getStatus());

cacheManager.getCache("order-by-id").evict(id);
assertEquals("PAID", cachedRead.detail(id).getStatus());
~~~

Đoạn trên minh họa thao tác SDK sub-document; cần import `List`, `MutateInSpec`, chuẩn bị SDK collection, cache provider, dữ liệu thử nghiệm, fixture cleanup và kiểm soát `@Version`/CAS. Không copy trực tiếp vào production. Một cache reference-based có semantics khác serialized cache nên phải kiểm chứng provider trước khi đặt assertion.

## 24. Test 2: xác minh index freshness mà không ép index phải trễ

Với SQL++ index, kiểm thử phải kiểm tra **bảo đảm được yêu cầu**, không bắt index cố tình stale.

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class IndexFreshnessIT {
    @Autowired
    private Cluster cluster;

    @Test
    void requestPlusSeesAcknowledgedInsert() {
        Collection orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");

        String id = "order::it-" + UUID.randomUUID();
        String customerId = "c-it-" + UUID.randomUUID();
        boolean acknowledged = false;

        try {
            orders.insert(id, JsonObject.create()
                    .put("customerId", customerId)
                    .put("status", "PAID"));
            acknowledged = true;

            String sql = """
                SELECT META(o).id AS documentId
                FROM `shop`.`sales`.`orders` AS o
                WHERE o.customerId = $customerId
                  AND o.status = "PAID"
                """;

            QueryResult result = cluster.query(
                    sql,
                    queryOptions()
                            .parameters(JsonObject.create()
                                    .put("customerId", customerId))
                            .scanConsistency(
                                    QueryScanConsistency.REQUEST_PLUS));

            assertTrue(result.rowsAsObject().stream()
                    .anyMatch(row ->
                            id.equals(row.getString("documentId"))));
        } finally {
            if (acknowledged) {
                orders.remove(id);
            }
        }
    }
}
~~~

Điều kiện:

1. Bucket/scope/collection và index phù hợp phải tồn tại/online.
2. Query không được lọc nhầm hoặc có mutation cạnh tranh.
3. Test SDK raw JSON không tự thêm Spring Data type discriminator; test Repository cần fixture mapping đúng.
4. Nếu insert đã được server xử lý nhưng client không nhận ACK, cờ `acknowledged` có thể false; suite thực cần cleanup độc lập cho mutation ambiguous.
5. Không chạy test trên production.

**Test sai:**

~~~text
Insert Order
Query NOT_BOUNDED ngay
assert Order KHÔNG xuất hiện  // Flaky!
~~~

Index có thể cập nhật đủ nhanh. `NOT_BOUNDED` cho phép kết quả chưa mới, không bắt buộc nó stale.

## 25. Test 3: nhiều tầng cache và nhiều instance

Một kịch bản tích hợp cần kiểm tra:

| Tình huống | Bước test | Bằng chứng kỳ vọng |
| --- | --- | --- |
| Local cache mỗi JVM | Điền cache trên A/B, ghi qua A | B có thể còn entry cũ nếu không broadcast |
| Redis shared cache | Điền key chung, ghi và evict | Các instance cùng miss/đọc lại nếu dùng cùng key |
| Cache key thiếu tenant | Hai tenant có cùng customerId | Test phải phát hiện nguy cơ trả nhầm dữ liệu |
| Cache list stale | Cache lịch sử, update status | Cache liên quan phải được invalidate/refresh |
| Stale refill race | Điều phối read chậm và write/evict xen kẽ | Không cho cache bị hồi sinh bằng version cũ nếu SLO cấm |
| HTTP cache | Ghi source rồi gọi endpoint qua proxy | Kiểm tra `Cache-Control`, `Age`, revalidation |
| Frontend state | API body mới nhưng UI còn cũ | Query invalidate/refetch và render đúng |

Các test về cache nên có **provider thật** trong integration environment nếu cần khẳng định semantics serialization/TTL/invalidation. Mock cache có thể kiểm tra method gọi evict, nhưng không thay thế test race và multi-instance.

## 26. Khi cache và index cùng stale: thứ tự xử lý

Giả sử chuỗi sự kiện:

~~~text
1. Save Order(PAID) thành công.
2. Lịch sử SQL++ NOT_BOUNDED chưa bắt kịp status.
3. Application cache ghi lại danh sách thiếu Order.
4. Index bắt kịp.
5. User tiếp tục nhận danh sách thiếu Order từ cache.
~~~

Có hai phần phải sửa:

- **Miss/load path:** Nếu hợp đồng yêu cầu query sau write thấy thay đổi, dùng REQUEST_PLUS/MutationState phù hợp hoặc đọc KV/response đã lưu; không cache một kết quả chưa đáp ứng SLO.
- **Hit/invalidation path:** Evict/update các cache key bị ảnh hưởng sau mutation/commit; thiết kế TTL và xử lý race. Nếu cache vẫn hit, không có query mới để REQUEST_PLUS phát huy tác dụng.

Chỉ làm một trong hai có thể khiến lỗi lặp lại. Đặc biệt, **xóa toàn bộ cache** có thể khắc phục tạm thời nhưng tăng tải Query Service/Index Service đột ngột khi mọi request đều miss.

## 27. Lưu ý về transaction, CAS, durability và quyền truy cập

### 27.1. CAS không tự cập nhật cache

`@Version` trong Spring Data Couchbase dùng CAS metadata để phát hiện cập nhật cạnh tranh. Nếu một request bị optimistic-locking conflict, phải báo lỗi hoặc retry nghiệp vụ có kiểm soát; không evict/update cache như thể mutation đã thành công.

### 27.2. Transaction và thời điểm invalidation

Nếu tạo Order và trừ Inventory trong một transaction, không nên phát hành một cache event tuyên bố “đã cập nhật” **trước khi transaction commit thành công**. Xem semantics transaction manager/SDK version và dùng cơ chế hậu commit, outbox hoặc event đáng tin cậy phù hợp. Evict sau khi method return không tự bảo đảm đúng thứ tự với mọi transaction boundary.

### 27.3. Durability khác cache freshness

Một mutation có mức durability cao hơn không tự khiến Redis/Caffeine/CDN xóa entry. Ngược lại, eviction cache không làm mutation bền hơn. Đây là hai hợp đồng khác nhau.

### 27.4. Bảo mật là giới hạn ưu tiên

Không dùng cache hoặc SQL++ index lag làm nguồn duy nhất quyết định token/session còn hợp lệ hay thanh toán đã được xử lý. Dùng nguồn có thẩm quyền theo key/expiry/revocation và kiểm soát quyền tại thời điểm phù hợp. Một stale cache chứa dữ liệu của tenant khác có thể là **sự cố bảo mật**, không chỉ lỗi UX.

## 28. Chiến lược chọn cache và index policy trong production

| Loại dữ liệu | Khuyến nghị tiếp cận | Đánh đổi |
| --- | --- | --- |
| Chi tiết Order vừa ghi | Saved entity hoặc KV; cân nhắc bỏ cache | Ít phụ thuộc index, thêm KV read nếu không trả saved |
| Danh sách Order có yêu cầu mới cao | SQL++ consistency phù hợp; cache hạn chế và invalidation chặt | Latency/index wait có thể tăng |
| Danh sách khám phá chấp nhận trễ | NOT_BOUNDED, cache TTL/refresh theo SLO | Có độ trễ dữ liệu phải công bố/đo |
| Dashboard | Read model/tổng hợp và cache với timestamp | Không phản ánh từng mutation ngay |
| Customer profile ít thay đổi | Cache-aside + evict sau update, tenant isolation | Lợi ích hit rate; cần xử lý race |
| Session/token | Nguồn có thẩm quyền và expiry/revocation | Không chấp nhận stale positive |
| Payment/unique constraints | CAS, conditional write, transaction/idempotency | Không coi cache/query là ràng buộc ghi |

**Không có một TTL cache chuẩn cho mọi ngành và mọi use case.** Tính TTL từ tần suất thay đổi, SLO độ mới, hậu quả stale data, hit rate, chi phí truy vấn và khả năng invalidation.

## 29. Bài tập tình huống

### Bài A — REQUEST_PLUS nhưng UI vẫn cũ

Repository query đã gắn `@ScanConsistency(REQUEST_PLUS)`. Service bao ngoài gắn `@Cacheable` và cache hit.

**Hỏi:** Vì sao vẫn thấy dữ liệu cũ?

**Đáp án:** Service trả giá trị cache mà không gọi Repository. Cần invalidation/refresh đúng key hoặc thiết kế bypass phù hợp; REQUEST_PLUS chỉ có tác dụng khi SQL++ chạy.

### Bài B — Cache eviction có đủ không?

Service evict entry Order detail khi đổi status, nhưng lịch sử theo customerId/status còn cũ.

**Đáp án:** Chưa. Cần invalidate cache của các danh sách bị ảnh hưởng, kể cả tập trạng thái cũ và mới, phân trang/tenant nếu có.

### Bài C — KV mới nhưng SQL++ cũ

Ứng dụng không dùng Spring Cache. KV get đã thấy Order PAID; SQL++ NOT_BOUNDED theo status=PAID chưa có row.

**Đáp án:** Kiểm tra index, generated SQL++, query plan và consistency. Dùng REQUEST_PLUS cho phép đợi index tới mốc request nếu nghiệp vụ cần.

### Bài D — Hai instance trả khác nhau

Instance A trả PAID, instance B trả CREATED dù cùng cluster.

**Đáp án:** Nghi local cache không được invalidation đồng bộ; đồng thời kiểm tra phiên bản triển khai, keyspace, đường đọc và proxy/cache phía trước.

### Bài E — Cache TTL bằng Couchbase TTL?

Một developer đặt TTL của session document là 30 phút rồi cho rằng local cache session cũng tự hết hạn sau 30 phút.

**Đáp án:** Không. Document TTL và application cache TTL độc lập; phải đồng bộ policy xác thực/revocation phù hợp.

### Bài F — Prepared query plan cache

Developer nói Couchbase Query Service có prepared statement cache nên SQL++ trả row cũ.

**Đáp án:** Plan cache không đồng nghĩa result cache. Cần kiểm tra index freshness và các result cache thật sự tồn tại trong ứng dụng.

### Bài G — Stale refill

Request A bắt đầu đọc CREATED; request B ghi PAID và evict; request A hoàn tất muộn, cache lại CREATED.

**Đáp án:** Đây là cache refill race. Cần chiến lược version/epoch, compare-and-set cache hoặc không cache dữ liệu nhạy cảm, tùy SLO.

### Bài H — Cache key thiếu tenant

Hai tenant có cùng `customerId`, cache lịch sử chỉ dùng customerId làm key.

**Đáp án:** Nguy cơ dữ liệu tenant A bị trả cho B. Phải đảm bảo authorization và tách key theo tenant/ngữ cảnh quyền, không chỉ sửa consistency SQL++.

### Bài I — Test NOT_BOUNDED

Test yêu cầu SQL++ NOT_BOUNDED luôn trả stale row sau insert.

**Đáp án:** Sai. Index có thể cập nhật kịp. Cache stale có thể tái hiện xác định bằng giữ entry cũ, nhưng index lag phải kiểm tra bằng bảo đảm REQUEST_PLUS và quan sát dưới tải.

## 30. Checklist xử lý dữ liệu cũ

- [ ] Write thật sự đã ACK hay kết quả timeout/ambiguous?
- [ ] Đã xác minh đúng document ID, bucket, scope và collection?
- [ ] KV active path phản ánh giá trị mới chưa?
- [ ] SQL++ có thực sự được thực thi hay service trả cache hit?
- [ ] Query SQL++ đúng `WHERE`, `ORDER BY`, `LIMIT`, tenant/type filter?
- [ ] Index online và `EXPLAIN`/scan consistency được xác minh?
- [ ] Dùng REQUEST_PLUS/MutationState đúng khi bắt buộc query mới?
- [ ] Cache provider nào được bật — local Caffeine, Redis, HTTP, CDN, frontend?
- [ ] Cache key có đủ tenant, ID, quyền, filter/page/cursor?
- [ ] Mutation có invalidation đủ cache detail, list và dashboard liên quan?
- [ ] Eviction xảy ra sau ghi/commit thành công chứ không trước?
- [ ] Có khả năng stale refill race hoặc mất event invalidation?
- [ ] Cache TTL, document TTL và HTTP cache policy được tách biệt?
- [ ] Không nhầm prepared plan cache với result cache?
- [ ] Đã đo cache hit/miss, entry age, query count, KV latency, GSI lag?
- [ ] Không trả danh sách rỗng khi Couchbase query timeout?
- [ ] Không dùng cache/index lag cho uniqueness, payment, session validity?
- [ ] Test cache stale có deterministic và test index không ép NOT_BOUNDED stale?
- [ ] Có runbook bypass an toàn, không bật endpoint debug công khai?
- [ ] Có correlation ID/tracing nhưng không lộ bí mật hoặc PII?

## 31. Kết luận

**Kết quả cũ do secondary index và dữ liệu cũ trong bộ nhớ đệm có thể giống nhau ở giao diện nhưng khác nhau hoàn toàn về nguyên nhân.** Index lag xảy ra khi query SQL++ thật sự quét một GSI chưa bắt kịp mutation; cache stale xảy ra khi lớp phía trước database trả lại giá trị đã lưu và có thể không gọi Couchbase.

Trong tầng truy cập **Spring Data Couchbase**, hãy chẩn đoán từ **nguồn KV → SQL++ trực tiếp → Spring Cache/Redis → HTTP/CDN/browser**. Chọn `REQUEST_PLUS` hay `MutationState` khi cần index mới, và xử lý cache bằng **key đúng, invalidation, TTL, versioning và kiểm soát race**. Đừng coi CAS, transaction, document expiry hoặc durability là những cơ chế tự động làm mới mọi cache. Khi tách rõ từng lớp, bạn có thể bảo đảm độ mới cần thiết, giữ latency hợp lý và vận hành hệ thống một cách có thể kiểm chứng.
