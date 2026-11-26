# Đánh đổi giữa độ mới, độ trễ và tải trên dịch vụ chỉ mục

## 1. Bài toán: ba mục tiêu không thể tối ưu riêng lẻ

Trong **Spring Data Couchbase**, người dùng vừa tạo đơn hàng và nhận HTTP `201 Created`. Khi mở trang chi tiết theo Order ID, đơn đã xuất hiện; khi mở lịch sử đơn theo customer ID, danh sách có thể chưa cập nhật. Lập trình viên có thể bật SQL++ `REQUEST_PLUS` để query đợi chỉ mục bắt kịp, nhưng sau đó latency p95/p99 có thể tăng khi Index Service đang bận.

Đây là đánh đổi giữa ba yếu tố:

1. **Độ mới của dữ liệu (freshness):** một query nhìn thấy các mutation được xác nhận gần đây đến mức nào?
2. **Độ trễ (latency):** mất bao lâu để trả kết quả theo đúng hợp đồng của API?
3. **Tải trên dịch vụ chỉ mục:** Index Service cần duy trì bao nhiêu index, xử lý bao nhiêu mutation, còn bao nhiêu backlog và phải phối hợp với bao nhiêu query có yêu cầu consistency cao?

Bài học thuộc chương **Tính nhất quán** của module **SPRING_DATA_COUCHBASE** — xây dựng tầng truy cập Couchbase bằng document mapping, `CouchbaseRepository`, `CouchbaseTemplate`, SQL++, Java SDK và reactive API. Nội dung liên kết với thiết kế bucket/scope/collection, chỉ mục, CAS, TTL, durability, giao dịch và khả năng vận hành.

**Mục tiêu học tập:** Sau bài này, bạn có thể diễn tả SLO độ mới cho từng API, chọn chính sách SQL++ `NOT_BOUNDED`, `REQUEST_PLUS` hoặc consistency theo mutation token, tối ưu index/query plan, đo p95/p99 cùng index backlog, phát hiện retry storm và bảo vệ các thao tác nghiệp vụ quan trọng mà không lạm dụng index freshness.

> Cách tối ưu tốt không phải luôn chọn dữ liệu mới nhất bằng mọi giá, mà là **đáp ứng đúng yêu cầu về độ mới với chi phí đo được và chấp nhận được**.

## 2. Tình huống xuyên suốt: hệ thống quản lý đơn hàng

Giả sử cluster có bucket `shop`, scope `sales`, collection `orders`. Một Order:

~~~text
Keyspace: shop.sales.orders
Metadata document ID: order::o-1001
~~~

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "currency": "VND",
  "totalVnd": 420000
}
~~~

Ứng dụng có bốn đường truy cập:

| Chức năng | API ví dụ | Đường truy cập | Kỳ vọng về dữ liệu |
| --- | --- | --- | --- |
| Xem Order vừa tạo | `GET /orders/o-1001` | KV theo document key | Thấy thao tác vừa được xác nhận |
| Lịch sử Order | `GET /customers/c-1001/orders` | SQL++ theo `customerId` | Tùy lúc có thể bắt buộc thấy Order mới |
| Dashboard doanh thu | `GET /reports/orders` | SQL++ aggregate / read model | Chấp nhận cập nhật theo chu kỳ nếu sản phẩm cho phép |
| Xác nhận đơn | `POST /orders/o-1001/confirm` | KV mutation + CAS | Không mất cập nhật hoặc xác nhận sai trạng thái |

Cùng đọc một loại document không có nghĩa mọi API cần cùng scan consistency. Trang xác nhận đã có Order ID, còn dashboard thường không cần đợi index bắt kịp từng mutation mới trong vài mili giây.

## 3. Vì sao write ACK và index visibility khác nhau?

Couchbase cung cấp đường **Key–Value** qua Data Service để đọc/ghi document theo metadata ID. Truy vấn **SQL++** lọc nhiều document theo field JSON thường được phục vụ bởi Query Service với **Global Secondary Index (GSI)** do Index Service duy trì.

~~~mermaid
flowchart LR
    APP["Spring Service"] --> WR["Repository/Template/SDK write"]
    WR --> DATA[("Data Service")]
    DATA --> KV["KV get theo key"]
    DATA --> STREAM["Mutation update stream"]
    STREAM --> IDX[("Index Service: GSI")]
    IDX --> SQL["Query Service: SQL++"]
    KV --> DETAIL["Chi tiết một Order"]
    SQL --> LIST["Danh sách theo customerId"]
~~~

Khi thao tác KV đã được ACK, index có thể chưa phản ánh mutation mới. Vì vậy:

~~~text
T0: KV insert Order A thành công
T1: findById(A) theo active KV đọc được A
T2: Index theo customerId vẫn đang bắt kịp
T3: SQL++ WHERE customerId = ... ở mode không đợi
    -> có thể chưa trả A
T4: Index đã phản ánh mutation của A
T5: SQL++ với filter hợp lệ có thể trả A
~~~

Đây là timeline **minh họa**, không phải cam kết index luôn đến sau với một khoảng trễ cố định. Trên cluster ít tải, GSI có thể đã cập nhật trước lúc query đầu tiên chạy.

### 3.1. Khi query không có row chưa chắc do độ trễ index

Kiểm tra thêm `WHERE`, `ORDER BY`, `LIMIT`, scope/collection, type discriminator của Spring Data, tenant filter, quyền, query plan, cache và các mutation đồng thời. Nếu query đã timeout thì đó là lỗi thực thi, **không phải** bằng chứng document không tồn tại.

## 4. Ba thước đo cần định nghĩa trước khi tuning

### 4.1. Độ trễ nhìn thấy mutation

Với mutation `m`, gọi `t_ack(m)` là thời điểm client nhận xác nhận và `t_seen(m)` là thời điểm sớm nhất một kiểu truy vấn/index path nhất định có thể nhìn thấy tác động của nó.

Độ trễ nhìn thấy được mô tả khái niệm:

\[
L_{\mathrm{visible}}(m)=t_{\mathrm{seen}}(m)-t_{\mathrm{ack}}(m)
\]

Không nên coi đây là một chỉ số có sẵn với đúng cách đo trong mọi phiên bản Couchbase. Nếu application polling mỗi 50 ms để tìm row, thời gian lần đầu phát hiện chỉ là **mẫu quan sát**, không chứng minh chính xác mốc server cập nhật index.

### 4.2. Độ trễ cuối-đầu của query

Một cách phân tích:

\[
T_{\mathrm{query}}\approx T_{\mathrm{network}}+
T_{\mathrm{plan}}+T_{\mathrm{wait-index}}+
T_{\mathrm{scan/fetch/sort}}+T_{\mathrm{transfer/map}}
\]

Các thành phần có thể chồng lấn; đây là **mô hình suy luận**, không phải phương trình nội bộ chính xác của Query Service. Scan consistency cao có thể tăng `T_wait-index`; index/query plan kém có thể khiến `T_scan/fetch/sort` lớn dù index đã đủ mới.

### 4.3. Tải của Index Service

Không chỉ xem CPU. Cần theo dõi:

- Mutation rate và backlog/lag của quá trình cập nhật GSI.
- Số index, kích thước, số partition, memory và disk I/O.
- Index build/rebalance/recovery đang diễn ra.
- Số query cần index scan và các truy vấn chờ consistency.
- Tỷ lệ timeout/retry có khả năng khuếch đại tải.
- Sự cạnh tranh tài nguyên giữa Index, Query và Data Service theo topology.

**Một phân biệt quan trọng:** REQUEST_PLUS không mặc nhiên làm mỗi mutation bị index hóa thêm lần nữa. GSI vốn phải được duy trì từ những thay đổi nguồn. Consistency cao chủ yếu tạo ràng buộc **query phải đợi index đạt một mốc**, kéo theo chi phí thời gian chờ, concurrency và áp lực tài nguyên; mức tăng tải thực tế cần đo chứ không suy từ tên option.

## 5. So sánh NOT_BOUNDED, REQUEST_PLUS và AT_PLUS

| Mode | Mốc index yêu cầu | Cần mutation token? | Đánh đổi |
| --- | --- | --- | --- |
| `NOT_BOUNDED` | Không yêu cầu đợi index bắt kịp mốc ghi mới trước scan | Không | Có thể stale; thường tránh thêm thời gian đợi consistency |
| `REQUEST_PLUS` | Đợi index liên quan đạt mốc của query theo semantics server | Không | Có thể tăng latency/timeout khi index backlog |
| `AT_PLUS` / `consistentWith(state)` | Đợi index phản ánh những mutation token được cung cấp | Có | Có thể tập trung vào các ghi cụ thể; quản lý token và fallback |

### 5.1. NOT_BOUNDED không đồng nghĩa stale bắt buộc

`NOT_BOUNDED` cho phép Query Service quét index hiện tại mà không yêu cầu đợi một mốc cập nhật mới nhất. Nếu Index Service đã kịp cập nhật, query vẫn có thể trả dữ liệu mới. Vì vậy không bao giờ viết integration test khẳng định **mọi NOT_BOUNDED query phải thiếu Order vừa insert**.

### 5.2. REQUEST_PLUS không tạo snapshot cố định

`REQUEST_PLUS` đợi index tiến tới mốc consistency của request trước khi scan. Nó không chặn mutation diễn ra sau khi query bắt đầu; không giữ một snapshot lịch sử đúng lúc vừa save. Một Order có thể bị cập nhật hoặc xóa tiếp và kết quả query có thể phản ánh trạng thái mới hơn.

### 5.3. AT_PLUS không luôn nhanh hơn REQUEST_PLUS

`MutationState` có thể giúp đợi đúng những mutation application đã quan sát thay vì mốc request rộng hơn. Nhưng nếu partition chứa mutation token đang có lag lớn, query vẫn chậm. Ngoài ra, thời gian scan/sort/fetch không biến mất. **Cần đo trên workload thực tế** trước khi khẳng định lợi ích latency.

## 6. Một timeline giả định cho thấy đánh đổi

Các mốc sau là **ví dụ mô phỏng**, không phải benchmark hay quy luật thời gian của Couchbase:

| Sự kiện | Mốc minh họa | Diễn giải |
| --- | --- | --- |
| KV write được ACK | 10:00:00.000 | Đã nhận kết quả ghi |
| KV get theo Order ID | 10:00:00.010 | Thấy Order |
| NOT_BOUNDED bắt đầu | 10:00:00.015 | Không đợi mốc consistency mới |
| NOT_BOUNDED trả | 10:00:00.029 | Có thể chưa chứa Order |
| REQUEST_PLUS bắt đầu | 10:00:00.030 | Yêu cầu index đạt mốc |
| GSI xử lý mutation | 10:00:00.105 | Index đủ mới với Order |
| REQUEST_PLUS trả | 10:00:00.125 | Có thể chứa Order nếu query hợp lệ |

Khi backlog thấp, hai query có thể nhanh tương đương. Khi backlog cao, REQUEST_PLUS có thể chậm rõ rệt hoặc chạm timeout. Bật REQUEST_PLUS không biến `WHERE` sai thành đúng hay `LIMIT 20` thành truy vấn không giới hạn.

## 7. Index lag ảnh hưởng latency như thế nào?

~~~mermaid
flowchart TD
    W["Mutation rate tăng"] --> B["Backlog cập nhật index"]
    I["Quá nhiều index / tài nguyên chưa đủ"] --> B
    B --> WAIT["Query REQUEST_PLUS / AT_PLUS chờ lâu"]
    WAIT --> CON["Nhiều HTTP request còn tồn tại"]
    CON --> TMO["Timeout / retry"]
    TMO --> LOAD["Tải query và concurrency tăng"]
    LOAD --> WAIT
    Q["SQL++ scan/sort tốn tài nguyên"] --> LOAD
~~~

Đây là một vòng khuếch đại **có thể xảy ra**, không phải cơ chế bắt buộc của mọi triển khai.

Với một hệ thống ổn định, Little's Law cho cách nhìn trực giác:

\[
N\approx\lambda W
\]

Trong đó `N` là số request trung bình đang trong hệ thống, `\lambda` là throughput và `W` là thời gian request ở lại. Nếu chờ index làm `W` tăng mà lượng request đến không giảm, số request đồng thời có thể tăng, kéo theo áp lực bộ nhớ/kết nối và rủi ro timeout.

**Không kết luận Index Service là nút thắt khi chưa đo.** Một query có thể chậm vì network, query plan tệ, sort nhiều row hoặc ứng dụng blocking I/O, dù index đã được cập nhật kịp.

## 8. Phân biệt tải cập nhật index và tải truy vấn

Index Service phải duy trì các cấu trúc GSI liên quan mỗi khi document thay đổi. Số lượng index, trường index, kích thước dữ liệu và tốc độ ghi ảnh hưởng tổng chi phí maintenance.

Một Query Service dùng GSI để quét và lấy row có thể tốn thời gian CPU/memory/network đáng kể; SQL++ cần sort/fetch nhiều cũng ảnh hưởng throughput. Tuy nhiên:

- Tạo **một index nữa** có thể làm tăng khối lượng maintenance lâu dài.
- Bật **REQUEST_PLUS trên một query** không mặc định tạo thêm một bản index mới hay viết lại mọi mutation; nó yêu cầu query đợi một mốc.
- Nhiều query đợi đồng thời có thể gia tăng pressure lên hệ thống khi kết hợp timeout và retry.
- Một covering index có thể giảm fetch body nhưng làm index lớn hơn và tốn công cập nhật.
- Đường KV theo key bỏ qua bước secondary-index scan cho một document.

Khi tuning, xem cả **chỉ số index update** lẫn **query plan**, đừng chỉ đổi enum consistency rồi so latency.

## 9. Bước đầu tối ưu: đã biết key thì dùng KV

Nếu controller vừa lưu Order:

~~~java
OrderDocument saved = repository.save(newOrder);

// Có thể dùng saved representation trả cho trang xác nhận.
return saved;
~~~

Khi muốn kiểm tra lại chính document ấy:

~~~java
OrderDocument detail = repository.findById(saved.getId())
        .orElseThrow();
~~~

Không cần SQL++ `WHERE customerId = ...` chỉ để xác định một Order đã có ID.

SDK KV minh họa:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

public class OrderKvGateway {
    private final Collection orders;

    public OrderKvGateway(Cluster cluster) {
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    public JsonObject getById(String documentId) {
        return orders.get(documentId).contentAsObject();
    }
}
~~~

Lưu ý: `documentId` phải là metadata key đầy đủ, ví dụ `order::o-1001`. Đọc từ replica, cluster khác hoặc cache không nhất thiết có cùng độ mới như active KV path. Một write timeout không có nghĩa chắc chắn chưa ghi — cần idempotency và xác minh kết quả theo key.

## 10. Thiết kế secondary index theo access pattern

Giả sử SQL++ liệt kê 20 đơn mới nhất của khách:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt, o.totalVnd
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Index khởi đầu:

~~~sql
CREATE INDEX ix_orders_customer_date
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Đây là **một lựa chọn minh họa**. Index production cần đánh giá bằng `EXPLAIN`, data distribution, projection và generated SQL++ của Spring Data (có thể thêm type discriminator).

| Phương án index | Lợi ích tiềm năng | Chi phí |
| --- | --- | --- |
| Một key `customerId` | Tương đối gọn | Có thể cần sort nhiều |
| Composite `(customerId, createdAt DESC)` | Có thể hỗ trợ filter và sort | Chi phí duy trì trên mutation |
| Covering index chứa thêm field phục vụ SELECT | Có thể tránh fetch document | Index lớn hơn, thêm RAM/disk/update cost |
| Nhiều index gần như trùng nhau | Có thể phục vụ nhiều query cụ thể | Tổng chi phí maintenance và quản trị tăng |

Không có quy tắc “càng nhiều index càng nhanh”. Với write-heavy workload, index thừa có thể làm GSI backlog xấu hơn và khiến các query REQUEST_PLUS phải chờ lâu hơn.

### 10.1. Query plan vẫn là bắt buộc

Kiểm tra:

~~~sql
EXPLAIN
SELECT META(o).id AS documentId,
       o.customerId, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = "c-1001"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Tìm index scan phù hợp, chi phí sort/fetch và projected rows. `REQUEST_PLUS` không tự tạo index thiếu hoặc sửa câu SQL++ không hiệu quả.

### 10.2. Phân trang giúp giảm scan và traffic

Không đọc toàn bộ lịch sử rồi `subList(0, 20)` trong Java. Cần `LIMIT`/pagination phía database với thứ tự ổn định. Offset pagination sâu có thể đắt và lặp/bỏ sót khi dữ liệu biến động; cân nhắc keyset/cursor phù hợp.

## 11. Chọn mức scan consistency từ Java SDK theo từng query

Ví dụ dùng Couchbase Java SDK 3.x và bean `Cluster` được quản lý vòng đời bởi ứng dụng.

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

public class OrderHistoryGateway {
    private static final String SQL = """
        SELECT META(o).id AS documentId,
               o.customerId, o.status, o.createdAt
        FROM `shop`.`sales`.`orders` AS o
        WHERE o.customerId = $customerId
        ORDER BY o.createdAt DESC
        LIMIT 20
        """;

    private final Cluster cluster;

    public OrderHistoryGateway(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult history(
            String customerId, QueryScanConsistency consistency) {

        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .scanConsistency(consistency)
                .timeout(Duration.ofSeconds(5));

        return cluster.query(SQL, options);
    }
}
~~~

Service có thể gọi:

~~~java
import static com.couchbase.client.java.query.QueryScanConsistency.NOT_BOUNDED;
import static com.couchbase.client.java.query.QueryScanConsistency.REQUEST_PLUS;

QueryResult dashboard = gateway.history("c-1001", NOT_BOUNDED);
QueryResult afterCreate = gateway.history("c-1001", REQUEST_PLUS);
~~~

Thời gian timeout `5s` chỉ là placeholder để minh họa option, **không phải con số chuẩn**. Phải chọn từ SLO/HTTP budget và kiểm tra behavior cụ thể của SDK/Server version.

SDK query trả kết quả rows/raw JSON; nó **không tự áp dụng tất cả converter và mapping entity của Spring Data**. Dùng named parameter thay vì nối user input trực tiếp vào SQL++ để kiểm soát injection.

## 12. Spring Data Repository: consistency ở method có nhu cầu

~~~java
import java.util.List;

import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerId(String customerId);

    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    List<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

`findById` thông thường đi KV; `findByCustomerId`/`findByCustomerIdAndStatus` thường sinh SQL++ theo field. Với query có `REQUEST_PLUS`, Index Service có thể phải bắt kịp mutation mốc request.

### 12.1. Entity mapping

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Field;

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

    public OrderDocument() {}

    // Bổ sung constructor/getters/setters cho ứng dụng thực.
}
~~~

`@Id` là metadata document key, không phải JSON field luôn hiện diện. `@Version` hỗ trợ CAS/optimistic locking, **không** đồng nghĩa một mutation token để query chờ index. Các annotation scope/collection và cách sinh SQL++ cần được xác minh trên bộ phiên bản Spring Data Couchbase của dự án.

### 12.2. Không gắn policy rộng khi chỉ một use case cần mới

Nếu dashboard không cần REQUEST_PLUS mà màn hình lịch sử sau POST cần, hãy giữ method/query riêng hoặc custom DAO riêng. Đặt REQUEST_PLUS trên cả repository type có thể khiến những query thông thường cũng phải chờ index ngoài ý muốn.

## 13. CouchbaseTemplate: cấu hình ở đúng thao tác

~~~java
import static org.springframework.data.couchbase.core.query.Query.query;
import static org.springframework.data.couchbase.core.query.QueryCriteria.where;

import java.util.List;

import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.data.couchbase.core.query.Query;
import org.springframework.data.domain.Sort;

public class OrderQueryDao {
    private final CouchbaseTemplate template;

    public OrderQueryDao(CouchbaseTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> recentForCustomer(
            String customerId, QueryScanConsistency mode) {

        Query q = query(where("customerId").is(customerId))
                .with(Sort.by(Sort.Direction.DESC, "createdAt"))
                .limit(20);

        return template.findByQuery(OrderDocument.class)
                .withConsistency(mode)
                .matching(q)
                .all();
    }
}
~~~

Ở phiên bản Spring Data hỗ trợ, có thể chọn đặt trên `Query`:

~~~java
Query q = query(where("customerId").is(customerId))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
        .limit(20);

return template.findByQuery(OrderDocument.class)
        .matching(q)
        .all();
~~~

Hai snippet thể hiện **hai nơi để đặt cùng loại policy**. Không tạo một query chứa NOT_BOUNDED rồi override REQUEST_PLUS tại fluent call nếu nhóm chưa kiểm chứng precedence. Query object có thể mutable: tạo mới theo mỗi request, tránh dùng chung instance rồi sửa `scanConsistency` giữa các thread.

## 14. Nhất quán theo MutationState khi có token

Với Java SDK, `MutationResult` có thể cung cấp token. Ứng dụng có thể gom các token liên quan thành `MutationState` rồi dùng SQL++ `consistentWith(state)`.

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.query.QueryResult;

public class OrderConsistentGateway {
    private final Cluster cluster;
    private final Collection orders;

    public OrderConsistentGateway(Cluster cluster) {
        this.cluster = cluster;
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    public QueryResult createAndQuery(String id, String customerId) {
        MutationResult write = orders.insert(id, JsonObject.create()
                .put("customerId", customerId)
                .put("status", "CREATED"));

        // Kiểm tra mutationToken() availability và định nghĩa
        // fallback rõ ràng trong code production.
        MutationState state = MutationState.from(write);

        String sql = """
            SELECT META(o).id AS documentId
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            """;

        return cluster.query(
                sql,
                queryOptions()
                        .parameters(JsonObject.create()
                                .put("customerId", customerId))
                        .consistentWith(state));
    }
}
~~~

Chữ ký API và token availability cần được xác minh theo Java SDK/Server version. Nếu không có token, không tự chế từ CAS, ID hoặc timestamp client. Với SLO bắt buộc query thấy các ghi trước request, `REQUEST_PLUS` có thể là fallback phù hợp. Với một Order đã có ID, KV get có thể tốt hơn.

Một state chỉ có token của Order A **không mặc nhiên bảo đảm** query cũng đã thấy Order B nếu cần hai mutation ở các partition khác nhau. Dùng API tổng hợp state đúng, rồi kiểm thử ở keyspace thực.

## 15. Reactive: giảm blocking thread, không triệt tiêu index wait

Trong WebFlux, dùng Reactive Repository hoặc `ReactiveCouchbaseTemplate` để tránh chặn event loop trong khi chờ I/O. Tuy nhiên, **REQUEST_PLUS vẫn có thể đợi Index Service**, do đó response latency, timeout và tải phía server không tự giảm.

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    Flux<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

Ví dụ nối thao tác ghi rồi query:

~~~java
import reactor.core.publisher.Flux;

public Flux<OrderDocument> saveThenList(OrderDocument order) {
    return reactiveOrders.save(order)
            .flatMapMany(saved ->
                    reactiveOrders.findByCustomerIdAndStatus(
                            saved.getCustomerId(), "CREATED"));
}
~~~

`flatMapMany` bảo đảm query nằm sau tín hiệu save thành công trong pipeline. Nó không tạo transaction. Nếu business chỉ cần trả Order mới, nên trả kết quả save mà không query danh sách.

Các sai lầm phổ biến:

~~~java
// Không non-blocking vì lời gọi sync xảy ra ngay lập tức:
Mono.just(syncRepository.findById(id));

// Không block event loop WebFlux:
reactiveRepository.findById(id).block();

// Không fire-and-forget mutation rồi lập tức query khác:
reactiveRepository.save(order).subscribe();
~~~

Backpressure và giới hạn concurrency ở ứng dụng giúp giảm quá tải pipeline, nhưng không thay index plan và không làm GSI cập nhật tức thì.

## 16. Đặt SLO riêng theo mức độ quan trọng

Một yêu cầu “dữ liệu phải realtime” quá mơ hồ. Nên chuyển thành hợp đồng:

| Use case | Freshness contract | Chiến lược |
| --- | --- | --- |
| Trang xác nhận sau POST | Hiển thị thao tác vừa ACK | Saved entity/KV |
| Lịch sử ngay sau POST | Query phải gồm Order mới nếu vẫn match filter/page | REQUEST_PLUS hoặc mutation state khi hỗ trợ |
| Lịch sử xem thông thường | Có thể lag theo SLO sản phẩm | NOT_BOUNDED nếu chấp nhận |
| Dashboard tổng hợp | Dữ liệu cập nhật theo chu kỳ cụ thể | NOT_BOUNDED/read model |
| Xác nhận trạng thái Order | Không bị lost update | KV + CAS/conditional write |
| Tạo Order và trừ Inventory | Nhiều mutation phải cùng thành công | Transaction/compensation |
| Session authentication | Không chấp nhận token hết hạn/revoked | KV key + expiry/revocation |

Giá trị latency cụ thể (ví dụ p95 dưới bao nhiêu ms, dữ liệu được trễ bao lâu) phải được **đo và thống nhất với sản phẩm**. Không lấy một con số giả định làm bảo đảm chung cho mọi cluster.

### 16.1. Chiến lược degrade

Nếu Index Service lag, các endpoint báo cáo có thể được phép hiển thị dữ liệu trễ kèm nhãn thời điểm cập nhật; còn một nghiệp vụ không cho phép stale data nên trả lỗi/timeout có ý nghĩa hoặc chuyển sang đọc nguồn có thẩm quyền. **Không tự hạ mọi query REQUEST_PLUS xuống NOT_BOUNDED** chỉ để che latency nếu như vậy vi phạm tính đúng đắn.

## 17. Giảm áp lực Index Service bằng thay đổi kiến trúc

Các biện pháp thường hiệu quả hơn việc đổi enum:

1. **Trả kết quả đã lưu:** Tránh query lại một Order bằng field khi đã có key.
2. **Dùng KV cho detail:** Phân biệt API detail và API list.
3. **Dọn index thừa:** Rà soát index ít dùng, trùng lặp hoặc sai access pattern.
4. **Composite index đúng filter/sort:** Giảm scan/sort/fetch không cần thiết.
5. **Projection và pagination:** Chỉ lấy field/row cần thiết.
6. **Tách dashboard nặng:** Cân nhắc read model hoặc tổng hợp định kỳ nếu độ mới cho phép.
7. **Giới hạn concurrency:** Rate limit/load shedding cho các truy vấn đắt.
8. **Timeout và retry có kiểm soát:** Tránh request storm khi index lag.
9. **Capacity theo topology:** Đo CPU, memory, disk và partition/index placement trước khi thay đổi.
10. **Kiểm thử dưới write-heavy và read-heavy load:** Không tối ưu từ một lần gọi dev.

Lưu ý: Tối ưu một trục có thể làm tăng chi phí trục khác. Ví dụ covering index giúp giảm fetch nhưng tăng kích thước/chi phí duy trì index.

## 18. Benchmark phải đo cả freshness, latency và throughput

### 18.1. Chuẩn bị

- Cluster/test environment tách biệt production.
- Bucket/scope/collection và index đã online.
- Dữ liệu đủ lớn và phân phối field đại diện.
- Ghi rõ Java, Spring Boot, Spring Data Couchbase, Java SDK, Server version.
- Workload mutation: tỷ lệ insert/update/delete, kích thước body, index count.
- Workload query: KV read, SQL++ list, dashboard, tỷ lệ từng consistency mode.
- Cấu hình concurrency, timeout, retry và network rõ.

### 18.2. Ma trận đợt thử

| Đợt | Tải ghi | Tải query | Mục đích |
| --- | --- | --- | --- |
| Baseline | Thấp | NOT_BOUNDED | Chi phí query không phải chờ mốc cao |
| Fresh baseline | Thấp | REQUEST_PLUS | Overhead khi index đã gần bắt kịp |
| Write-heavy | Tăng dần | Cả hai mode | Quan sát index backlog và tail latency |
| Read-heavy | Vừa phải | Concurrency tăng | Đo scan/fetch và Query Service |
| Recovery | Hạ tải sau đợt ghi cao | Query tiếp tục | Đo backlog trở lại bình thường |
| Token-targeted | Có token hợp lệ | consistentWith | Đo so với REQUEST_PLUS cho cùng use case |

### 18.3. Kết quả cần lưu

| Mức đo | Vì sao cần? |
| --- | --- |
| p50/p95/p99 query latency | Thấy cả trường hợp đuôi xấu, không chỉ trung bình |
| Throughput thành công | Khả năng phục vụ traffic |
| Timeout, error, retry rate | Tác động của backlog và retry storm |
| KV write ACK latency | Phân biệt write bottleneck với index/query bottleneck |
| Index update backlog/lag | Chứng cứ về tiến độ GSI |
| Query plan và scan/fetch/sort metrics | Phát hiện query kém không do consistency |
| Index/Query/Data CPU, memory, disk I/O | Vị trí nút thắt |
| Tỷ lệ từng consistency mode | Bật REQUEST_PLUS có quá rộng không? |

Không invent số liệu benchmark. Một template ghi kết quả:

| Workload | Consistency | p95 (ms) | p99 (ms) | Timeout | Index lag |
| --- | --- | --- | --- | --- | --- |
| Baseline | NOT_BOUNDED | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| Baseline | REQUEST_PLUS | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| Write-heavy | NOT_BOUNDED | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| Write-heavy | REQUEST_PLUS | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |

### 18.4. Không suy ra index lag chính xác từ polling client

Nếu lần query đầu tiên thấy Order ở mốc 40 ms sau ACK, không có nghĩa index cập nhật **đúng 40 ms**. Nó có thể cập nhật sớm hơn, giữa hai lần polling. Cần mô tả cách đo và sai số trước khi công bố SLO freshness.

## 19. Integration test: kiểm chứng correctness tách khỏi benchmark

Mock Repository không kiểm chứng được GSI freshness. Sử dụng Couchbase thực/tương đương với index online và namespace test riêng.

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
class OrderIndexFreshnessIT {
    @Autowired
    private Cluster cluster;

    @Test
    void requestPlusSeesAcknowledgedOrder() {
        Collection orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");

        String id = "order::it-" + UUID.randomUUID();
        String customerId = "it-customer-" + UUID.randomUUID();
        boolean acknowledged = false;

        try {
            orders.insert(id, JsonObject.create()
                    .put("customerId", customerId)
                    .put("status", "CREATED"));
            acknowledged = true;

            String sql = """
                SELECT META(o).id AS documentId
                FROM `shop`.`sales`.`orders` AS o
                WHERE o.customerId = $customerId
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

Đây là **mẫu test cần fixture**, không chạy độc lập nếu chưa cấu hình Cluster, collection, quyền và index. Nếu insert đã thực thi nhưng client không nhận ACK, biến `acknowledged` có thể vẫn false; bộ test production-grade cần cơ chế cleanup độc lập để dọn dữ liệu có thể đã ghi. Không chạy trên production.

**Một test sai:**

~~~text
Insert Order
Ngay lập tức query NOT_BOUNDED
assert không có Order   // Flaky: index có thể đã cập nhật kịp.
~~~

NOT_BOUNDED cho phép kết quả chưa mới, không bắt buộc nó stale. Đo hiệu năng qua load test riêng thay vì assert latency cứng trong CI biến động.

## 20. Runbook khi p99 tăng hoặc người dùng báo đơn chưa xuất hiện

~~~mermaid
flowchart TD
    A["p99 tăng hoặc lịch sử chưa thấy Order"] --> B{"KV theo ID có thấy document?"}
    B -->|Không| C["Kiểm tra ACK, keyspace, replica/cache, timeout"]
    B -->|Có| D["Kiểm tra generated SQL++ và EXPLAIN"]
    D --> E{"Query/index/filter đúng?"}
    E -->|Không| F["Sửa index, query, mapping, LIMIT, tenant"]
    E -->|Có| G["Đo index backlog và scan consistency"]
    G --> H{"Có nhiều request chờ REQUEST_PLUS?"}
    H -->|Có| I["Giới hạn tải, giảm query thừa, capacity planning"]
    H -->|Không| J["Đo scan/fetch/sort, network, Query Service"]
    I --> K["Đối chiếu freshness và latency SLO"]
    J --> K
~~~

Trình tự xử lý:

1. Xác định endpoint, query và thời điểm bắt đầu lỗi.
2. Đọc source document theo key để tách write/keyspace khỏi index query.
3. Kiểm tra `EXPLAIN`, index online, filter, type discriminator và kết quả.
4. Xác định mode consistency thật sự được gửi xuống SDK.
5. Đo index mutation backlog, Query Service latency và timeout.
6. Giới hạn retry/concurrency trước khi khuếch đại sự cố.
7. Chọn thay đổi phù hợp: policy, query/index, workflow hoặc capacity.
8. Đo lại SLO; không chỉ thấy CPU giảm mà kết luận dữ liệu đã đủ mới.

**Không hạ độ mới một cách âm thầm:** Nếu endpoint giao dịch bắt buộc dữ liệu vừa ghi phải xuất hiện, đổi REQUEST_PLUS thành NOT_BOUNDED có thể giảm latency nhưng phá hợp đồng nghiệp vụ.

## 21. CAS, TTL, durability và transaction không thay thế scan consistency

| Cơ chế | Vấn đề giải quyết | Không nên suy ra |
| --- | --- | --- |
| CAS / `@Version` | Ngăn lost update trên document khi ghi có điều kiện | GSI tự cập nhật tức thì |
| Durability | Mức xác nhận ghi bền/nhân bản | SQL++ mặc định thấy ngay |
| TTL/expiry | Document đến hạn hết hiệu lực | Field JSON `expiresAt` tự biến thành metadata TTL |
| Transaction đa document | Nhiều mutation cùng commit/rollback theo API phù hợp | Mọi Search/GSI index mới ngay không cần policy |
| Query scan consistency | Mốc index trước SQL++ scan | Atomicity, khóa, uniqueness hoặc authorization |
| Mutation token/state | Query thấy các mutation đã chỉ định | CAS, transaction ID hoặc snapshot lịch sử |
| Search index consistency | Độ mới của tìm kiếm toàn văn | QueryScanConsistency.REQUEST_PLUS tự áp dụng cho Search |

Một nghiệp vụ “kiểm tra email bằng SQL++ rồi insert Customer” vẫn có race dù bật REQUEST_PLUS; phải bảo vệ uniqueness ở **đường ghi** bằng key/conditional insert hoặc transaction thích hợp.

Một nghiệp vụ tạo Order và trừ Inventory cần transaction hoặc workflow bù trừ. Scan consistency không làm hai lần `save` nguyên tử. Với session hết hạn, quyết định đăng nhập nên dựa trên nguồn session key/expiry/revocation, không dựa vào một query GSI lag.

## 22. Reactive và retry dưới tải cao

Nếu dùng WebFlux, Reactive Repository/Template giúp tránh chặn thread khi đang chờ I/O; nó **không** làm thời gian chờ index biến mất. Khi nhiều Publisher query REQUEST_PLUS hoạt động đồng thời, vẫn cần:

- Giới hạn mức đồng thời của `flatMap` hoặc ở API gateway.
- Đặt timeout hợp lý theo query/HTTP budget.
- Tránh tự `subscribe()` rồi bỏ qua lỗi.
- Không gọi `block()` trong event loop.
- Không lấy hàng chục nghìn row rồi `take(20)` thay cho SQL++ LIMIT.
- Chỉ retry query khi lỗi có thể phục hồi và không khuếch đại backlog.
- Với mutation bị timeout, giữ idempotency key; không tạo ID mới rồi retry mù.

Một query `REQUEST_PLUS` thất bại vì timeout **không** chứng minh lệnh tạo Order đã thất bại. Tách kết quả ghi và kết quả truy vấn đọc để tránh nhân đôi thao tác nghiệp vụ.

## 23. Bài tập vận dụng

### Bài A — Trang xác nhận

Sau POST, backend có Order ID và saved representation. Developer định dùng SQL++ REQUEST_PLUS theo `customerId` chỉ để lấy đúng Order vừa lưu.

**Đáp án định hướng:** Không cần. Trả saved entity hoặc KV theo ID, tiết kiệm query/index wait.

### Bài B — Dashboard chậm

Dashboard cho phép số liệu chậm theo chu kỳ làm mới nhưng mọi query đang bật REQUEST_PLUS. Sau đợt ghi lớn, p99 tăng.

**Đáp án định hướng:** Đo index lag, query plan và SLO. Nếu sản phẩm cho phép, dùng NOT_BOUNDED hoặc read model riêng cho dashboard. Không tự hạ policy của endpoint thực sự cần read-after-write.

### Bài C — Query đủ mới nhưng thiếu Order

SQL++ REQUEST_PLUS hoàn tất nhưng Order không có trong kết quả `LIMIT 20`.

**Đáp án định hướng:** Kiểm tra `WHERE`, `ORDER BY`, trang hiện tại, customerId, tenant, type discriminator, keyspace và mutation mới hơn. Không quy tất cả về index lag.

### Bài D — Tạo thêm nhiều index

Nhóm tạo năm index gần giống nhau để tăng tốc list Order; dưới tải ghi, index backlog tăng.

**Đáp án định hướng:** Rà soát access pattern và `EXPLAIN`, bỏ/ghép index trùng hoặc không dùng, đo chi phí maintenance và query sau thay đổi.

### Bài E — REQUEST_PLUS timeout sau POST

Save thành công, query lịch sử timeout. Service tạo Order với UUID mới và retry.

**Đáp án định hướng:** Sai. Timeout query không nói write trước đó thất bại; có nguy cơ tạo trùng. Dùng idempotency key và xác minh trạng thái theo nguồn có thẩm quyền.

### Bài F — AT_PLUS luôn nhanh hơn?

Một developer tuyên bố consistent-with MutationState luôn nhanh hơn REQUEST_PLUS.

**Đáp án định hướng:** Không. Dấu mốc hẹp hơn có thể giảm chờ, nhưng index trên partition đó vẫn có thể lag; phần scan/sort/fetch cũng quan trọng.

### Bài G — Chỉ dùng reactive

Chuyển Spring MVC sang WebFlux nhưng giữ cùng SQL++ REQUEST_PLUS và cùng index.

**Đáp án định hướng:** Thread utilization có thể tốt hơn, nhưng server index wait và p99 của query không tự mất. Cần tối ưu đường dữ liệu, index và concurrency.

### Bài H — NOT_BOUNDED test

Test viết assertion rằng query NOT_BOUNDED ngay sau insert phải không thấy Order.

**Đáp án định hướng:** Flaky. Index có thể kịp cập nhật. NOT_BOUNDED cho phép lag, không ép kết quả stale.

## 24. Checklist lựa chọn cho production

- [ ] Có biết chính xác document ID để dùng KV không?
- [ ] Đã định nghĩa SLO độ mới riêng cho từng endpoint?
- [ ] Đã có mục tiêu latency p95/p99 và ngân sách timeout/error?
- [ ] Query SQL++ có index online và `EXPLAIN` phù hợp?
- [ ] `WHERE`, `ORDER BY`, `LIMIT`, projection và tenant filter chính xác?
- [ ] NOT_BOUNDED chỉ dùng nơi cho phép lag?
- [ ] REQUEST_PLUS chỉ gắn nơi cần index bắt kịp mốc request?
- [ ] Nếu dùng mutation state, có token hợp lệ và fallback rõ?
- [ ] Index count/size/update backlog được giám sát?
- [ ] Đã tách chi phí chờ index khỏi scan/fetch/sort/network latency?
- [ ] Query error/timeout không bị chuyển thành danh sách rỗng?
- [ ] Retry/concurrency có giới hạn, không khuếch đại Index Service lag?
- [ ] Có thể trả saved entity/KV thay vì query lại sau POST?
- [ ] CAS, transaction, TTL, durability, Search freshness và idempotency được xử lý độc lập?
- [ ] Reactive path không blocking, không tự subscribe sai vị trí?
- [ ] Integration test kiểm chứng behavior, không ép NOT_BOUNDED stale?
- [ ] Benchmark có read/write mix, p95/p99, timeout và freshness metric thực tế?
- [ ] Runbook có thứ tự kiểm tra KV, SQL++, index plan, mode và capacity?
- [ ] Logging/tracing đủ correlation ID nhưng không lộ secret/session token?

## 25. Kết luận

Đánh đổi giữa **độ mới dữ liệu, độ trễ và tải trên dịch vụ chỉ mục** bắt đầu từ việc chọn đúng **đường đọc**. Biết document ID thì ưu tiên saved representation hoặc KV. Cần truy vấn tập document theo field thì dùng SQL++ và GSI, với `NOT_BOUNDED` khi SLO cho phép index lag, `REQUEST_PLUS` khi phải đợi mốc index của request, hoặc `MutationState/consistentWith` khi cần những mutation cụ thể và SDK hỗ trợ.

Đừng dùng một enum như phương án tối ưu duy nhất. Thiết kế index đúng access pattern, hạn chế kết quả, đo tail latency và backlog, giữ timeout/retry/concurrency có kiểm soát, đồng thời bảo vệ bất biến bằng CAS/transaction/idempotency ở đường ghi. Một lựa chọn tốt là lựa chọn **đạt đúng hợp đồng độ mới với độ trễ và chi phí vận hành thấp nhất có thể kiểm chứng** trên workload thực tế.
