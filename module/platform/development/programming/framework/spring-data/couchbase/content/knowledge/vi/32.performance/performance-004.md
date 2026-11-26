# Giảm số trường trả về và số tài liệu trung gian

## 1. Hai loại lãng phí trong một câu truy vấn

Một API danh sách đơn hàng chỉ hiển thị **mã đơn, thời gian tạo, trạng thái và tổng tiền**, nhưng repository hiện trả toàn bộ `OrderDocument`, gồm địa chỉ giao hàng, lịch sử cập nhật, danh sách hàng hóa và thông tin thanh toán. Ở tầng khác, SQL++ lọc hàng nghìn đơn, sắp xếp rồi mới trả 20 dòng đầu tiên. Hai vấn đề này có thể cùng tồn tại nhưng phải xử lý theo hai hướng khác nhau:

- **Dư trường (wide rows):** đọc, chuyển đổi hoặc truyền nhiều field hơn contract response cần.
- **Dư tài liệu trung gian (high intermediate cardinality):** quét, fetch, join, UNNEST, sort hoặc materialize nhiều document/row hơn cần thiết để tạo kết quả cuối.

Bài **“Giảm số trường trả về và số tài liệu trung gian”** thuộc chương **Hiệu năng** của module **SPRING_DATA_COUCHBASE**. Module xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn API reactive để bảo đảm hiệu năng, nhất quán và khả năng vận hành.

**Mục tiêu:**

1. Phân biệt projection giảm kích thước kết quả với index/filter làm giảm số row phải xử lý.
2. Biết dùng `SELECT` field tường minh, `SELECT RAW`, DTO projection và KV subdocument `lookupIn` đúng tình huống.
3. Xác định khi nào covering index tránh được `Fetch`, và khi nào việc SELECT ít field chưa đủ.
4. Giảm số rows trước `ORDER BY`, `JOIN`, `UNNEST`, `GROUP BY` và phía ứng dụng mà không làm đổi semantics.
5. Dùng `LIMIT`/pagination/keyset đúng để tránh tải hoặc bỏ qua lượng lớn dữ liệu.
6. Kiểm soát materialization trên Spring Data, SDK blocking và reactive API.
7. Đo số entries quét, document fetch, rows returned, bytes, memory, độ trễ và write amplification.
8. Giữ nguyên authorization, consistency, CAS/TTL và schema khi tối ưu.

Ví dụ sử dụng phong cách Java 17, Spring Boot 3.x, Spring Data Couchbase 5.x, Couchbase Java SDK 3.x và SQL++ trên Couchbase Server hỗ trợ collections. Hành vi optimizer, tên operator trong `EXPLAIN` và cú pháp projection repository có thể khác theo phiên bản; khi đưa vào production phải đối chiếu API/plan trên phiên bản thực tế.

## 2. Từ 100.000 document tới 20 row: pipeline thực sự làm gì?

Một truy vấn:

~~~sql
SELECT o.*
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = "PAID"
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Kết quả chỉ có tối đa 20 row, **không đồng nghĩa Query service chỉ phải xử lý 20 document**. Tùy index/plan, nó có thể:

1. Quét nhiều index entries để tìm candidates.
2. Fetch content từ Data service.
3. Thực hiện residual filter.
4. Sort một tập row trung gian.
5. Cắt còn 20 row.
6. Trả JSON lớn vì `o.*`.

~~~mermaid
flowchart LR
    A["Nhiều index entries"] --> B["Filter / index scan"]
    B --> C["Fetch document nếu cần"]
    C --> D["Sort / Join / Aggregate"]
    D --> E["LIMIT 20"]
    E --> F["Serialize + network"]
    G["Index phù hợp"] --> H["Giảm scan/fetch/sort"]
    H --> B
    I["Projection hẹp"] --> J["Giảm bytes và mapping"]
    J --> F
~~~

Một tối ưu tốt xác định **bottleneck nằm ở B/C/D hay F**, rồi thay đổi đúng thành phần. Projection hẹp có thể giảm bytes nhưng chưa chắc giảm số document cần scan; một index tốt có thể giảm scan nhưng không tự biến `SELECT *` thành JSON nhỏ.

## 3. Mô hình dữ liệu xuyên suốt

Giả sử collection:

~~~text
Bucket: commerce
Scope: sales
Collection: orders
Document key: order::O-2026-001
~~~

Document minh họa:

~~~json
{
  "docType": "order",
  "customerId": "u-42",
  "status": "PAID",
  "createdAtEpochMs": 1795582800000,
  "orderSequence": 10051,
  "total": 150000,
  "currency": "VND",
  "shippingAddress": {
    "city": "Ho Chi Minh City",
    "district": "District 1",
    "street": "Example street"
  },
  "items": [
    {"sku": "SKU-1", "quantity": 2, "price": 50000},
    {"sku": "SKU-2", "quantity": 1, "price": 50000}
  ],
  "auditHistory": [
    {"status": "CREATED", "at": "2026-11-25T09:00:00Z"},
    {"status": "PAID", "at": "2026-11-25T09:10:00Z"}
  ]
}
~~~

API danh sách chỉ cần:

~~~json
{
  "id": "order::O-2026-001",
  "status": "PAID",
  "createdAtEpochMs": 1795582800000,
  "total": 150000
}
~~~

Danh sách không cần `shippingAddress`, `items` hay `auditHistory`. Tuy vậy, API chi tiết đơn hàng có thể cần các field đó. **Contract của từng endpoint**, không phải hình dạng entity tổng, quyết định projection.

## 4. Hai số đo không được đánh đồng

| Khái niệm | Đo cái gì? | Thí dụ |
| --- | --- | --- |
| Fields returned | Số field/result shape | 4 field thay vì toàn JSON |
| Logical response bytes | Kích thước serialized result body | 2 KiB thay vì 80 KiB |
| Index entries scanned | Số entries index được duyệt | 100 hay 100.000 |
| Documents fetched | Số document lấy từ Data service để thực hiện query | 0, 20 hoặc 5.000 |
| Intermediate rows | Số row giữa các operator | 20 hay 10.000 |
| Final rows | Số row thật trả client | 20 |
| Application allocations | Bộ nhớ tạo ra để map/entity/list | Tỷ lệ tăng theo rows/bytes |
| Network bytes | Traffic thật gồm framing/compression/retries | Khác logical bytes |

Nếu cả hai query đều trả 20 row, một query vẫn có thể **chậm gấp nhiều lần** vì scanned/fetched rows lớn hơn. Nếu cả hai scan cùng 20 entries, một query vẫn có thể nặng hơn vì mỗi row chứa JSON hàng trăm KiB.

### 4.1. Dựng baseline ở ba trục

Cần đo cùng workload:

- **Latency:** p50/p95/p99 ở HTTP và Query/SDK.
- **Throughput:** completed useful requests/giây cùng tỷ lệ lỗi.
- **Data transfer:** logical JSON bytes, HTTP response bytes và network bytes theo đúng tầng.

Đồng thời xem `EXPLAIN`/profile để giải thích scanned/fetched/intermediate rows. Không kết luận tối ưu chỉ vì response nhỏ hơn trong một lần test.

## 5. Bước đơn giản nhất: bỏ `SELECT *` khi không cần

Query trả toàn bộ document:

~~~sql
SELECT o.*
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Query chỉ trả field cần hiển thị:

~~~sql
SELECT META(o).id AS id,
       o.status,
       o.createdAtEpochMs,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Lợi ích có thể gồm:

1. Ít bytes serialize từ Query service và gửi về client.
2. Ít allocations/deserialization khi xây DTO.
3. Hạn chế lộ field nhạy cảm không cần thiết.
4. Tạo cơ hội dùng **covering index** nếu tất cả predicate/order/projection đều được index đáp ứng.

**Giới hạn:** nếu plan vẫn `Fetch` 10.000 document và sort ngoài index, chỉ thay `SELECT *` chưa chắc giảm phần chi phí lớn nhất. Phải kiểm tra plan.

### 5.1. Projection là một phần của API contract

Đừng loại field để đạt benchmark đẹp nhưng làm sai chức năng. Xác nhận các field được UI, business rules, audit và authorization thực sự sử dụng. Khi thay result shape, DTO/schema test phải được cập nhật có chủ đích.

## 6. Đừng dùng `SELECT o.*` khi chỉ cần một scalar

Có endpoint chỉ cần trạng thái:

~~~sql
SELECT RAW o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = "PAID"
LIMIT 20;
~~~

`SELECT RAW`, còn được gọi theo cách diễn đạt `SELECT VALUE` trong SQL++ phù hợp, trả **giá trị biểu thức trực tiếp** thay vì một object có property chứa giá trị đó. Hình dạng result là phần contract cần test:

~~~text
Projection object:
  {"status":"PAID"}

Projection RAW:
  "PAID"
~~~

Không dùng RAW khi caller cần object với nhiều field. Nếu chỉ cần một con số tổng hợp:

~~~sql
SELECT RAW COUNT(1)
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = "PAID";
~~~

Query count không phải phép KV tồn tại và có thể cần scan nhiều index entries. `RAW` chỉ thu gọn result shape; **không bảo đảm giảm scan count**.

## 7. Projection của nested field

Muốn hiển thị thành phố giao hàng trên một danh sách:

~~~sql
SELECT META(o).id AS id,
       o.status,
       o.shippingAddress.city AS city
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
LIMIT 20;
~~~

Nếu schema có document thiếu `shippingAddress`, projection có thể cho field `MISSING` hoặc thiếu property trong JSON. DTO mapping phải định nghĩa rõ optional/null/required.

Một thay đổi từ `o.shippingAddress` sang `o.shippingAddress.city` giảm output bytes, nhưng server vẫn có thể fetch document để đọc nested path. Nếu cần tránh Fetch, đánh giá index expression/path tương ứng và cost để cover query.

### 7.1. Không tự trả dữ liệu nhạy cảm trong list view

Thông tin địa chỉ, thanh toán, token hoặc audit history không nên nằm trong response chỉ vì entity có field tương ứng. Projection là cả vấn đề **hiệu năng** lẫn **giảm bề mặt dữ liệu**, nhưng phải có authorization riêng chứ không chỉ dựa vào field selection.

## 8. Khi đã biết document key: cân nhắc KV trước SQL++

Nếu caller đã có chính xác `order::O-2026-001` và đúng collection, SDK KV GET không cần secondary index:

~~~java
import com.couchbase.client.java.kv.GetResult;

GetResult read = orders.get("order::O-2026-001");
var json = read.contentAsObject();

String status = json.getString("status");
~~~

Nhưng đoạn này **vẫn lấy toàn bộ document** rồi mới chọn `status` trong JVM. Nếu JSON lớn và chỉ cần một hai path, cân nhắc KV subdocument `lookupIn` thay vì dùng SQL++ chỉ để projection một key.

### 8.1. Không dùng WHERE theo ID thay cho KV chỉ vì muốn ít field

~~~sql
SELECT o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE META(o).id = "order::O-2026-001";
~~~

Query service có thể tối ưu key predicate trong plan, nhưng vẫn có overhead Query request. Với exact key, KV `lookupIn` là một hướng cần benchmark trước.

## 9. SDK `lookupIn` chỉ đọc vài path của một document

~~~java
import java.util.List;
import com.couchbase.client.java.kv.LookupInResult;
import com.couchbase.client.java.kv.LookupInSpec;

LookupInResult result = orders.lookupIn(
        "order::O-2026-001",
        List.of(
                LookupInSpec.get("status"),
                LookupInSpec.get("total")
        )
);

String status = result.contentAs(0, String.class);
Long total = result.contentAs(1, Long.class);
~~~

Đây là operation **KV subdocument**, không dùng Query service/GSI. Nó có thể tránh chuyển cả document lớn qua mạng chỉ để lấy hai giá trị.

Cần lưu ý:

- JSON path phải có thật hoặc được xử lý theo contract.
- Kiểu dữ liệu Java tương thích với JSON.
- Một document nhỏ hoặc cần gần hết fields có thể không lợi khi dùng subdocument.
- Thao tác này không tự thực hiện authorization.
- Nhiều request `lookupIn` riêng biệt trên cùng key có thể tốn round trip hơn một request với nhiều specs.

### 9.1. Đừng nhầm `lookupIn` với `mutateIn`

`lookupIn` đọc các phần document. `mutateIn` là mutation theo path; nó cần chính sách CAS, expiry và xử lý conflict riêng. Không tự dùng mutation chỉ để đọc trạng thái.

### 9.2. Benchmark đúng ba lựa chọn

Trên document 100 KiB, thử:

| Phương án | Phép đo |
| --- | --- |
| `get` toàn JSON | KV latency và body bytes |
| `lookupIn` hai path | KV latency, response bytes, CPU |
| SQL++ projection theo document ID | Query latency, Query/Index load, bytes |

Không tuyên bố `lookupIn` luôn nhanh nhất; đo p95/p99 và throughput cùng network/topology.

## 10. Spring Data repository và chi phí entity mapping

Entity ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    private String customerId;
    private String status;
    private Long createdAtEpochMs;
    private Long orderSequence;
    private Long total;
    private String currency;
    private ShippingAddress shippingAddress;
    private java.util.List<OrderItem> items;

    protected OrderDocument() {
    }

    public String getId() { return id; }
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public Long getCreatedAtEpochMs() { return createdAtEpochMs; }
    public Long getOrderSequence() { return orderSequence; }
    public Long getTotal() { return total; }
    public String getCurrency() { return currency; }
    public ShippingAddress getShippingAddress() { return shippingAddress; }
    public java.util.List<OrderItem> getItems() { return items; }
}
~~~

Đoạn này dùng `ShippingAddress` và `OrderItem` như các type domain minh họa cần được định nghĩa trong dự án.

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

`findById` có thể dùng KV theo document ID và map toàn entity. Nếu endpoint chỉ cần `status` nhưng repository đã tải toàn bộ document, **tạo DTO sau khi gọi `findById` không giảm bytes được đọc từ Couchbase**:

~~~java
// Chỉ thu nhỏ HTTP response, không chắc giảm KV payload.
var entity = repository.findById(id).orElseThrow();
return new OrderStatusResponse(
        entity.getId(), entity.getStatus());
~~~

Đó vẫn có thể là lựa chọn đúng cho document nhỏ hoặc cache entity đã có, nhưng không nên ghi trong benchmark rằng DTO mapping này tối ưu network GET.

## 11. Projection repository không tự bảo đảm Query chỉ đọc vài field

Spring Data có các cơ chế projection khác nhau theo phiên bản, ví dụ interface projection hoặc DTO projection. Một interface minh họa:

~~~java
public interface OrderListView {
    String getId();
    String getStatus();
    Long getCreatedAtEpochMs();
    Long getTotal();
}
~~~

Repository query theo business fields có thể khai báo:

~~~java
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderListRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderListView> findByCustomerIdAndStatus(
            String customerId, String status, Pageable pageable);
}
~~~

**Quan trọng:** loại projection và phương pháp mapper triển khai khác nhau tùy Spring Data release. Một closed projection có thể giúp chọn ít field, nhưng cũng có trường hợp Spring Data vẫn phải materialize entity hoặc thêm metadata/type fields. Vì vậy:

1. Ghi lại SQL++ thực sự được repository tạo.
2. Kiểm tra `SELECT` field có giảm không.
3. Kiểm tra `EXPLAIN`: có `Fetch` không?
4. Đo result bytes và entity/proxy allocations.
5. Đừng chỉ xem DTO có bốn getter rồi suy SDK chỉ đọc bốn field.

Nếu endpoint cần tối ưu mạnh, một SQL++ projection tường minh và DTO mapper được kiểm soát có thể phù hợp hơn; nhưng phải cân nhắc bảo trì và contract.

## 12. SQL++ projection tường minh qua SDK

Ví dụ trả DTO bốn field với named parameters:

~~~java
import java.util.List;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;

public record OrderSummary(
        String id,
        String status,
        long createdAtEpochMs,
        long total) {
}

public final class OrderSummaryQuery {

    private final Cluster cluster;

    public OrderSummaryQuery(Cluster cluster) {
        this.cluster = cluster;
    }

    public List<OrderSummary> find(
            String customerId, String status) {

        String sql = """
                SELECT META(o).id AS id,
                       o.status,
                       o.createdAtEpochMs,
                       o.total
                FROM `commerce`.`sales`.`orders` AS o
                WHERE o.docType = "order"
                  AND o.customerId = $customerId
                  AND o.status = $status
                ORDER BY o.createdAtEpochMs DESC,
                         o.orderSequence DESC
                LIMIT 20
                """;

        var options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId)
                        .put("status", status));

        return cluster.query(sql, options)
                .rowsAsObject()
                .stream()
                .map(row -> new OrderSummary(
                        row.getString("id"),
                        row.getString("status"),
                        row.getLong("createdAtEpochMs"),
                        row.getLong("total")))
                .toList();
    }
}
~~~

Code giả định các field luôn có và đúng JSON type. Production cần validate null/missing/overflow, xử lý query errors và quyền truy cập. `rowsAsObject()` vật hóa danh sách kết quả trên đường blocking; không dùng cách này để tự kéo hàng triệu rows vào heap.

**Không ghép giá trị user vào SQL string**. Named parameters giúp bind values; tên bucket/scope/collection nếu cần động phải được kiểm soát bằng whitelist/identifier quoting phù hợp, không coi chúng như value parameters.

## 13. Muốn tránh Fetch: cần covering index phù hợp

Một index ứng viên:

~~~sql
CREATE INDEX ix_orders_customer_status_list
ON `commerce`.`sales`.`orders` (
    customerId,
    status,
    createdAtEpochMs DESC,
    orderSequence DESC,
    total
)
WHERE docType = "order";
~~~

Query:

~~~sql
SELECT META(o).id AS id,
       o.status,
       o.createdAtEpochMs,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "order"
  AND o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC,
         o.orderSequence DESC
LIMIT 20;
~~~

Index này hướng tới hai lợi ích:

- `customerId` và `status` làm equality prefix, tiếp theo là sort keys để giảm scan/sort nếu plan phù hợp.
- Những field `SELECT` và điều kiện có thể được đáp ứng từ index entries, giúp **cover query** mà không fetch toàn document.

Tuy nhiên **không được khẳng định index sẽ luôn cover hay loại Sort**. Predicate `docType` của partial index, `META().id`, field MISSING, optimizer statistics, version và query form đều ảnh hưởng. Xem `EXPLAIN` để xác minh covers/fetch/order.

### 13.1. Covering index và projection là hai quyết định khác

| Cấu hình | Projection nhỏ? | Có thể tránh Fetch? |
| --- | --- | --- |
| `SELECT o.*`, index ba field | Không | Thường không |
| SELECT bốn field, index chỉ customerId | Có | Chưa chắc |
| SELECT bốn field, index bao phủ cả predicate/sort/projection | Có | Có cơ hội |
| KV `lookupIn` hai path | Có | Không đi qua SQL++ index/fetch |
| SELECT RAW một scalar nhưng predicate không có index | Rất nhỏ | Scan vẫn có thể lớn |

Projection giảm **kích thước output**; covering index có thể giảm **Data service fetch**; predicate/sort index giúp giảm **intermediate rows**. Phải đo cả ba.

## 14. Index rộng hơn cũng có chi phí

Một index thêm `total`, `currency`, `shippingAddress.city` để cover nhiều màn hình sẽ có footprint và maintenance cost.

Khi mutation Couchbase cập nhật các field được index, Index service có thêm công việc. Chỉ thêm field nếu lợi ích tránh Fetch và bytes đủ bù:

- Kích thước index trên disk và memory.
- Thời gian build/rebuild.
- Write/update p95/p99.
- Tài nguyên Index service.
- Chi phí scan index entries lớn hơn.
- Số query thực sự được cover.

Đừng tạo một index cho mọi field của document để cố làm `SELECT *` trở thành covering query.

## 15. Giảm document trung gian bắt đầu từ WHERE có thể dùng index

Query lọc đúng nghiệp vụ:

~~~sql
SELECT META(o).id AS id,
       o.createdAtEpochMs,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "order"
  AND o.customerId = $customerId
  AND o.status = "PAID"
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Nếu index leading keys phù hợp, Query service có thể giới hạn vùng scan ngay từ đầu. Ngược lại, dùng `LOWER(o.customerId)` hoặc ép kiểu trên field khi index chỉ chứa raw value có thể khiến predicate khó tận dụng index.

**Quy tắc:** muốn giảm số row trung gian, hãy ưu tiên predicate chọn lọc và **sargable**, dùng index theo access pattern thật. Không chỉ sửa vị trí dòng WHERE trong SQL text; optimizer mới là thành phần quyết định execution plan.

### 15.1. Không nhầm sargability với phân quyền

Nếu query bắt buộc lọc tenant:

~~~sql
WHERE o.tenantId = $tenantId
  AND o.customerId = $customerId
~~~

Không được xóa `tenantId` để scan nhanh hơn mà làm lộ data cross-tenant. Hãy thiết kế composite index cho cả hai điều kiện theo mức độ chọn lọc và tần suất.

## 16. Thứ tự điều kiện trong SQL text không luôn là thứ tự thực thi

Hai câu:

~~~sql
WHERE o.customerId = $customerId
  AND o.status = "PAID"
~~~

và:

~~~sql
WHERE o.status = "PAID"
  AND o.customerId = $customerId
~~~

thường diễn đạt cùng một predicate logic. Đổi thứ tự các dòng không phải kỹ thuật tối ưu index đáng tin. Đường thực thi phụ thuộc optimizer, index key order và statistics.

Thay vì sắp lại câu SQL theo cảm giác:

1. Xác định equality/range predicates.
2. Thiết kế composite index với leading keys hữu ích.
3. Chạy `EXPLAIN` để xem spans.
4. Đo scanned entries, fetch count và p95/p99.

## 17. Sort và LIMIT: đẩy công việc xuống index khi có thể

Một API lịch sử chỉ cần 20 đơn mới nhất:

~~~sql
SELECT META(o).id AS id,
       o.createdAtEpochMs,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAtEpochMs DESC,
         o.orderSequence DESC
LIMIT 20;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_orders_recent
ON `commerce`.`sales`.`orders` (
    customerId,
    createdAtEpochMs DESC,
    orderSequence DESC,
    total
);
~~~

Nếu scan có thể duyệt entries theo thứ tự cần thiết và query đủ điều kiện, Query service có thể tránh một sort lớn và cắt sớm. Nhưng `LIMIT 20` **không cam kết chỉ 20 index entries được đọc**: residual predicate, nhiều spans, fetch và điều kiện khác có thể khiến nó xử lý nhiều hơn.

### 17.1. Phân biệt số row cuối với số row trước LIMIT

~~~text
Scanned entries:    80.000
Fetched documents:  12.000
Rows after filter:   9.000
Rows after LIMIT:       20
~~~

Các số trên là ví dụ giả lập. Nếu sau thêm index plan mới chỉ scan vài chục entries, cải thiện đến từ **giảm trung gian**; còn chỉ thay SELECT field có thể làm response nhỏ hơn nhưng không thay 80.000 scanned entries.

## 18. OFFSET lớn làm lãng phí row trung gian

~~~sql
SELECT META(o).id AS id, o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAtEpochMs DESC,
         o.orderSequence DESC
LIMIT 20 OFFSET 20000;
~~~

Để tới trang sâu, engine có thể phải xét nhiều entries trước khi bỏ 20.000 dòng. Đây là chi phí dù output chỉ 20 rows.

Với lịch sử theo thứ tự ổn định, cân nhắc **keyset/cursor pagination**:

~~~sql
SELECT META(o).id AS id,
       o.createdAtEpochMs,
       o.orderSequence,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND (
       o.createdAtEpochMs < $lastCreatedAt
       OR (
           o.createdAtEpochMs = $lastCreatedAt
           AND o.orderSequence < $lastSequence
       )
  )
ORDER BY o.createdAtEpochMs DESC,
         o.orderSequence DESC
LIMIT 20;
~~~

Cần có tie-breaker `orderSequence` bảo đảm thứ tự duy nhất trong phạm vi cần phân trang. Query dùng `OR` cần kiểm tra index spans/plan, không tự giả định tối ưu. Cursor phải chứa cùng filter/order context và được bảo vệ chống sửa trái phép nếu phù hợp.

### 18.1. Phân trang không tự tạo snapshot nhất quán

Nếu order mới xuất hiện hoặc trạng thái đổi giữa các trang, kết quả phân trang có thể thay đổi. Cần định nghĩa consistency/snapshot requirement; không coi keyset pagination tự giải quyết mọi race.

## 19. Chỉ lấy đủ N+1 row khi cần biết còn trang sau

Một UI trả 20 items và flag `hasNext` đôi khi chỉ cần lấy 21 kết quả, rồi dùng item thứ 21 làm tín hiệu còn trang sau. Điều này có thể tránh một query `COUNT(*)` tốn tài nguyên trong mỗi request.

~~~text
Requested page size = 20
Query fetch limit   = 21

Nếu có 21 rows:
  hasNext = true
  body trả 20 rows
Nếu có <=20 rows:
  hasNext = false
~~~

Trong Spring Data, return type kiểu `Page` có thể kích hoạt count query tùy cách repository/service thực thi. `Slice` hoặc phương án cursor có thể giảm công việc khi business không cần total count, nhưng API/implementation phải được kiểm tra theo Spring Data version.

**Không thay Page bằng Slice nếu UI bắt buộc hiện chính xác tổng số trang**, trừ khi thay đổi contract được phê duyệt.

## 20. Không đọc toàn bộ dataset vào Java rồi mới filter

Anti-pattern:

~~~java
// Ví dụ phản tác dụng nếu collection rất lớn.
List<OrderDocument> all = repository.findAll();

List<OrderDocument> recent = all.stream()
        .filter(o -> "PAID".equals(o.getStatus()))
        .sorted(java.util.Comparator.comparing(
                OrderDocument::getCreatedAtEpochMs).reversed())
        .limit(20)
        .toList();
~~~

Lỗi thiết kế:

- Đọc/mapping nhiều document chỉ để trả 20.
- Tạo list và sort trong heap.
- Tăng network bytes và GC.
- Không tận dụng index/filter/limit của Query service.
- Có nguy cơ OOM hoặc latency rất cao khi dataset tăng.

Cách đúng là **biểu đạt predicate, sort và LIMIT ở tầng lưu trữ/query**, dùng index phù hợp và trả một result set hữu hạn. Trường hợp phải xử lý một tập lớn để chạy batch là use case khác, cần streaming/paging và backpressure riêng.

## 21. JOIN có thể nhân số row trung gian

Giả sử một order có nhiều shipment events. Query:

~~~sql
SELECT META(o).id AS orderId,
       o.status,
       s.carrier,
       s.eventAt
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`sales`.`shipments` AS s
  ON s.orderId = META(o).id
WHERE o.customerId = $customerId;
~~~

Nếu mỗi order có 10 shipments, join có thể tạo **10 result rows cho một order**. Một danh sách màn hình cần một dòng cho mỗi order sẽ bị phình trung gian nếu join toàn bộ events.

Trước khi dùng JOIN:

1. UI cần một row cho mỗi order hay một row cho mỗi shipment?
2. Có thể lọc order/customer trước theo index không?
3. Có thể tìm **một shipment phù hợp** bằng một truy vấn/aggregation cụ thể không?
4. Có index trên join key phía phải không?
5. Có đang fetch toàn bộ shipment payload khi chỉ cần carrier/time không?
6. Có duplicate rows do quan hệ 1-n hoặc sai join predicate không?

**Không cắt `LIMIT 20` tùy tiện trước hoặc sau JOIN** nếu làm đổi semantics. LIMIT 20 orders khác LIMIT 20 joined rows.

### 21.1. Tránh `SELECT o.*, s.*` trong danh sách

Nếu contract chỉ cần order ID và shipping status, projection nên chỉ chứa các field đó. Giảm field không tự giảm join multiplication; để giảm trung gian cần chọn đúng join semantics, predicate và index.

## 22. Nếu chỉ cần kiểm tra có phần tử: tránh UNNEST toàn bộ mảng

Một order có mảng `items`:

~~~json
{
  "customerId": "u-42",
  "items": [
    {"sku": "SKU-A", "quantity": 2},
    {"sku": "SKU-B", "quantity": 1},
    {"sku": "SKU-C", "quantity": 4}
  ]
}
~~~

Nếu muốn tìm những order **có SKU-A**, một cách dùng `UNNEST`:

~~~sql
SELECT META(o).id AS id
FROM `commerce`.`sales`.`orders` AS o
UNNEST o.items AS item
WHERE o.customerId = $customerId
  AND item.sku = $sku;
~~~

Mỗi phần tử mảng có thể tạo một row trung gian. Nếu chỉ cần predicate tồn tại ít nhất một phần tử, diễn đạt bằng `ANY ... SATISFIES`:

~~~sql
SELECT META(o).id AS id
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND ANY item IN o.items
      SATISFIES item.sku = $sku
      END;
~~~

`ANY` mô tả bài toán “có ít nhất một item thỏa điều kiện” mà không yêu cầu trả từng item làm row. Tuy nhiên performance thực phụ thuộc index. Có thể đánh giá array index:

~~~sql
CREATE INDEX ix_orders_customer_item_sku
ON `commerce`.`sales`.`orders` (
    customerId,
    DISTINCT ARRAY item.sku FOR item IN items END
);
~~~

Cú pháp và khả năng optimizer dùng index cần đối chiếu Couchbase Server version và `EXPLAIN`. Array index có thể có nhiều entries/document và tăng write cost.

### 22.1. Khi nào UNNEST vẫn đúng?

Nếu API thực sự phải trả **từng line item** hoặc tính aggregate trên từng phần tử, UNNEST có thể là lựa chọn hợp lý. Khi đó hãy hạn chế document đầu vào, projection và row count theo business semantics. Không tự thay UNNEST bằng ANY nếu làm mất danh sách items mà caller cần.

## 23. GROUP BY và aggregation: để server tổng hợp nhưng cần index tốt

Anti-pattern trong ứng dụng:

~~~text
Query toàn bộ đơn PAID (hàng trăm nghìn rows)
→ truyền về Java
→ stream().groupingBy(currency)
→ sum(total)
→ trả vài con số
~~~

Với aggregate phù hợp, SQL++ có thể thực hiện phần lớn công việc ở server:

~~~sql
SELECT o.currency,
       COUNT(1) AS orderCount,
       SUM(o.total) AS totalAmount
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "order"
  AND o.status = "PAID"
GROUP BY o.currency;
~~~

Kết quả chỉ gồm một dòng mỗi currency thay vì trả mọi order cho JVM.

**Nhưng** SQL++ vẫn có thể phải scan nhiều index entries và aggregate trung gian; số dòng kết quả ít không có nghĩa công việc rẻ. Cần xem index/aggregate pushdown, memory và Query service metrics.

### 23.1. COUNT không miễn phí

~~~sql
SELECT RAW COUNT(1)
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId;
~~~

Chỉ trả một số nguyên, nhưng engine vẫn phải đánh giá các entries phù hợp. Nếu UI liên tục đếm toàn bộ dataset để phân trang, có thể thay bằng has-next hoặc thiết kế summary được duy trì phù hợp với consistency và tốc độ cập nhật.

## 24. Sort trên tập lớn gây chi phí bộ nhớ

Một câu query có `ORDER BY` nhưng thiếu index theo predicate/sort có thể cần sắp xếp một lượng lớn rows trước khi trả `LIMIT`.

Các chiến lược:

1. Chọn composite index theo equality/range và sort keys.
2. Có `LIMIT` thật sự ở SQL++, không chỉ `stream.limit` sau khi nhận.
3. Giảm field được đưa qua sort nếu plan có thể tránh materialization rộng.
4. Dùng keyset pagination cho trang sâu.
5. Kiểm tra Query/Index resource, memory và spill behavior theo server version.
6. Đo p95/p99 dưới dataset lớn, không chỉ 100 document trong staging.

Đừng tạo một index mới chỉ vì có ORDER BY; phân tích thứ tự key, tần suất query và write amplification.

## 25. Pushdown là đặc tính plan, không phải tên cú pháp

Các tối ưu có thể được gọi là:

- Predicate pushdown: giảm candidates ngay từ index scan.
- Projection pushdown: chỉ yêu cầu field cần thiết tại đúng tầng.
- ORDER/LIMIT pushdown: tránh xử lý toàn bộ tập khi index cho phép.
- Aggregation pushdown: tận dụng index/query plan để giảm intermediate work.

Không được suy rằng thay đổi **thứ tự chữ trong SQL++** sẽ tự biến mọi operator thành pushdown. Optimizer quyết định kế hoạch. Hãy nhìn `EXPLAIN` và runtime metrics.

### 25.1. CTE/subquery không mặc nhiên giúp giảm dữ liệu

Một `WITH` hoặc subquery viết để “lọc trước” có thể được optimizer rewrite/inlined tùy phiên bản và query shape. Nếu cố ép materialization ở giữa có thể còn tệ hơn.

Chọn subquery khi nó diễn đạt đúng semantics hoặc giúp kiểm soát tập kết quả, nhưng xác minh plan. Đừng xem CTE như một hàng rào tối ưu cố định.

## 26. Query plan: phân biệt scan, fetch, sort và result

Ví dụ:

~~~sql
EXPLAIN
SELECT META(o).id AS id,
       o.status,
       o.createdAtEpochMs,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "order"
  AND o.customerId = "u-42"
  AND o.status = "PAID"
ORDER BY o.createdAtEpochMs DESC,
         o.orderSequence DESC
LIMIT 20;
~~~

Trong `EXPLAIN`, tìm các operator/thông tin tương đương theo version:

| Dấu hiệu | Câu hỏi cần trả lời |
| --- | --- |
| IndexScan/IndexScan3 | Index nào? Spans có chọn lọc không? |
| Covers | SELECT và predicate có được phục vụ từ index? |
| Fetch | Có phải đọc document từ Data service? Bao nhiêu? |
| Filter | Điều kiện nào chỉ áp sau scan/fetch? |
| Order | Có sort riêng hay index scan đã hỗ trợ thứ tự? |
| Limit/Offset | Có thể cắt sớm không? |
| NestedLoop/Hash Join | Join có tạo nhiều row trung gian không? |
| Group/Aggregate | Aggregation xử lý ở đâu, bao nhiêu nhóm? |

Không assert một tên operator nhất định tồn tại ở mọi Couchbase Server. Chi tiết plan và metric tùy phiên bản/cost-based optimizer.

## 27. Profile và metrics: đo cả tỷ lệ phóng đại

Một bảng đo giả định:

| Chỉ số | Query A: trước | Query B: sau |
| --- | ---: | ---: |
| Entries scanned | 150.000 | 90 |
| Documents fetched | 20.000 | 0 |
| Rows before LIMIT | 7.500 | Khoảng 20 |
| Final rows | 20 | 20 |
| Logical response | 120 KiB | 6 KiB |
| Query p95 | 230 ms | 35 ms |

Đây chỉ là **ví dụ minh họa**, không phải phép đo thực. Cải thiện B có thể đến từ cả covering index lẫn predicate/order/limit pushdown, không thể tự quy toàn bộ cho projection.

Một chỉ số hữu ích là tỷ lệ:

~~~text
scan amplification  = entries scanned / final rows
fetch amplification = documents fetched / final rows
row width            = logical result bytes / final rows
~~~

Các tỷ số này chỉ có ý nghĩa khi định nghĩa đơn vị, trường hợp final rows bằng 0 và query semantics rõ ràng. Một aggregate trả một dòng đương nhiên có amplification cao nếu cần tổng hợp toàn bộ dữ liệu; không nên coi đó tự động là lỗi.

## 28. Spring Data `@Query` và type discriminator

Spring Data Couchbase có thể phát ra SQL++ với các field/type metadata riêng để map entity. Ví dụ một repository method:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.domain.Pageable;

public interface OrderSearchRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerIdAndStatus(
            String customerId,
            String status,
            Pageable pageable
    );
}
~~~

Dù tên method nghe như một query đơn giản, SQL++ phát sinh có thể bao gồm:

- Type discriminator/filter của mapper.
- `SELECT` entity fields cần thiết.
- ORDER BY từ `Pageable`.
- LIMIT/OFFSET.
- Các field names sau `@Field` conversion.

Index partial hoặc covering phải khớp **statement thật**, không chỉ mẫu SQL++ tự viết. Một index chỉ cover bốn fields danh sách có thể không cover entity projection do repository cần thêm type metadata.

### 28.1. Không bỏ type filter hoặc CAS để đạt kế hoạch đẹp

Xóa type discriminator có thể làm Spring Data đọc nhầm entity. Bỏ CAS khi update có thể làm lost updates. Bỏ TTL hoặc đổi scan consistency có thể thay contract dữ liệu. Tối ưu hiệu năng phải giữ correctness.

## 29. `CouchbaseTemplate` và entity query

`CouchbaseTemplate` có các đường thao tác theo ID và query entity tùy phiên bản. Nếu biết document key, dùng find-by-ID/KV khi phù hợp. Nếu tìm theo predicate, kiểm tra SQL++ generated và projection result thật.

Một service dùng template trả `OrderDocument` đầy đủ dù HTTP chỉ cần `OrderSummary` có thể materialize dữ liệu không cần. Phương án gồm:

- Cấu trúc DTO/projection được framework hỗ trợ và xác minh SQL++.
- SDK SQL++ projection tường minh cho hot read path.
- KV `lookupIn` khi key đã biết.
- Tách entity nội bộ và DTO public contract.

Không mặc định một phương án nhanh hơn mọi phương án khác; đo số field được đọc, mapper cost và bytes.

## 30. Reactive API không tự giảm số result rows

Một endpoint WebFlux dùng:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<OrderSummary> summaries =
        cluster.reactive()
                .query(sql, options)
                .flatMapMany(result -> result.rowsAsObject())
                .map(row -> new OrderSummary(
                        row.getString("id"),
                        row.getString("status"),
                        row.getLong("createdAtEpochMs"),
                        row.getLong("total")
                ));
~~~

Đây là mô hình reactive SQL++ qua SDK 3.x ở các version hỗ trợ; các biến `cluster`, `sql`, `options` và record `OrderSummary` đã được định nghĩa trong service. Cần xác minh API cụ thể với dependency.

Lợi ích:

- Có thể xử lý row dưới dạng reactive signals, giảm nhu cầu tạo một danh sách lớn trong ứng dụng khi pipeline hỗ trợ.
- Có thể kết nối backpressure và response streaming theo kiến trúc.
- Giảm blocking thread khi I/O-bound.

**Không tự giả định** pipeline reactive khiến Query service chỉ quét số row đã consume. Nếu SQL++ không có `LIMIT` hoặc cần sort/aggregate toàn tập, server vẫn có thể làm nhiều công việc trước khi phát rows. Backpressure phía JVM không đồng nghĩa predicate/index pushdown phía server.

### 30.1. `collectList` có thể xóa lợi ích streaming

~~~java
Mono<java.util.List<OrderSummary>> materialized =
        summaries.collectList();
~~~

`collectList` giữ toàn bộ kết quả trong memory tới khi publisher complete. Với result nhỏ có LIMIT, việc này bình thường; với triệu rows có thể OOM.

Dùng paging/bounded result hoặc streaming khi nghiệp vụ cho phép. Đồng thời phải xử lý cancellation, timeout, lỗi giữa stream và semantics HTTP (không thể luôn đổi status sau khi response đã bắt đầu).

## 31. Mở rộng fan-out KV cũng tạo trung gian ở ứng dụng

Giả sử service có 500 order IDs từ một query rồi GET từng document để lấy vài fields. Đây là một dạng fan-out/N+1:

~~~text
SQL++ tìm 500 IDs
→ 500 KV GET document đầy đủ
→ Java filter còn 20
→ HTTP trả 20
~~~

Có thể cân nhắc:

1. Đưa filter/sort/LIMIT vào SQL++ và chỉ lấy 20 IDs.
2. Dùng covering SQL++ projection khi có thể để tránh bước 20 GET.
3. Nếu phải GET thêm fields, chỉ GET cho subset đã chọn.
4. Bounded concurrency với reactive; không phát hàng nghìn KV requests đồng thời.
5. Dùng `lookupIn` trên các key nếu chỉ cần vài path.

Không giảm fan-out bằng cách bỏ kiểm tra quyền hoặc dùng dữ liệu index cũ ngoài consistency contract. Đo cả Query request và KV operations sinh thêm.

## 32. Không tối ưu bytes bằng cách bỏ cơ chế nhất quán

Tình huống có query và KV:

- `NOT_BOUNDED` và `REQUEST_PLUS` có yêu cầu độ mới index khác nhau.
- Query projection chỉ trả field từ index có thể khác timing với KV read sau mutation.
- TTL/xóa document và index cleanup có nhịp riêng.
- CAS/`@Version` bảo vệ optimistic locking của mutation, không phải chỉ là field thừa để bỏ.
- Transaction nhiều document có chi phí khác lookup đơn lẻ.
- Cache hit không phải read Couchbase mới.

Một plan cover nhanh nhưng trả dữ liệu chưa đạt yêu cầu nhất quán không thể tự được gọi là tối ưu thành công. Giữ nguyên contract read-after-write và correctness khi benchmark.

## 33. Metadata expiry, mapping và security khi giảm field

Không phải mọi field đều có thể bỏ qua:

- `META().id` nếu API cần định danh row.
- Type metadata/fields nếu Spring Data mapper cần để khôi phục entity.
- CAS nếu cần optimistic concurrency (thường SDK lấy từ KV result, không phải JSON field thường).
- Expiry metadata nếu nghiệp vụ cần kiểm tra TTL (đọc qua API options phù hợp).
- Tenant/ownership fields nếu authorization cần kiểm tra chúng.
- Sort tie-breaker/cursor fields để paging đúng.
- Audit fields nếu chính use case cần chúng (không mặc định mọi list view cần).

Projection UI không phải authorization. Một query vẫn phải giới hạn tập document theo tenant/permission trước khi trả dữ liệu; không thể chỉ ẩn tên field mà coi đã an toàn.

### 33.1. Project field sau khi đã xác thực có thể khác query theo tenant

Với hot path multi-tenant, hãy bảo đảm predicate authorization được áp ở backend, có index phục vụ và test không có cross-tenant leakage. Không lấy một list gồm document nhiều tenant rồi lọc ở Java chỉ vì DTO cuối không chứa tenant ID.

## 34. Byte count: logical JSON khác network wire

Một `JsonObject` nhỏ hơn có thể giảm logical serialized bytes. Nhưng:

- JSON Unicode có byte UTF-8 khác số ký tự Java.
- Response compression làm wire bytes khác body bytes.
- TLS/protocol framing và retries thêm traffic.
- HTTP DTO có thể nhỏ dù SDK đã tải full entity.
- Query result metadata/row framing có overhead riêng.

Nếu đã có QueryResult rows dưới dạng JsonObject, có thể ước lượng serialized result bytes:

~~~java
import java.nio.charset.StandardCharsets;
import com.couchbase.client.java.json.JsonObject;

long logicalBytes = 0;
for (JsonObject row : result.rowsAsObject()) {
    logicalBytes += row.toString()
            .getBytes(StandardCharsets.UTF_8).length;
}
~~~

Đây là **ước lượng logical JSON**; nó tự serialize lại (có CPU overhead) và không phải số byte trên wire. Không bật đo kiểu này trên mọi request production chỉ để lấy metric.

Với KV, `contentAsBytes().length` có thể đo document body bytes sau decode theo SDK API; nếu ứng dụng đã lấy bytes sẵn thì không cần serialize lại.

## 35. Benchmark trước và sau: hai trục rows và bytes

Mẫu benchmark:

~~~text
Use case: recent paid orders by customer
Input: customerId + status
Output: 20 order summaries, đúng thứ tự

Variant A:
  SELECT o.*
  index không cover
  mapping full entity

Variant B:
  SELECT 4 fields
  index cũ, vẫn Fetch

Variant C:
  SELECT 4 fields
  covering index theo filter/sort

Variant D:
  SELECT 4 fields
  covering index + keyset pagination

Chung:
  dataset, key distribution, concurrency, TLS
  consistency, result correctness, version
  warm-up và load steps
~~~

Thu:

| Metric | A | B | C | D |
| --- | --- | --- | --- | --- |
| p50/p95/p99 Query | Đo | Đo | Đo | Đo |
| p50/p95/p99 HTTP | Đo | Đo | Đo | Đo |
| Goodput + unexpected errors | Đo | Đo | Đo | Đo |
| Index entries scanned | Đo | Đo | Đo | Đo |
| Documents fetched | Đo | Đo | Đo | Đo |
| Rows before LIMIT | Đo theo khả năng profiler | Đo | Đo | Đo |
| Rows returned | Xác minh bằng nhau | Xác minh | Xác minh | Xác minh |
| Logical/HTTP/network bytes | Đo đúng tầng | Đo | Đo | Đo |
| App heap/GC | Đo | Đo | Đo | Đo |
| Index memory/disk | Đo | Đo | Đo | Đo |
| Write p95/p99 | Đo | Đo | Đo | Đo |

Nếu C giảm Query p99 nhưng index build/maintenance làm write p99 vượt SLO, phải tiếp tục cân bằng.

### 35.1. Kết quả giả định để diễn giải

| Chỉ số | Query A | Query C |
| --- | ---: | ---: |
| Rows returned | 20 | 20 |
| Entries scanned | 120.000 | 45 |
| Documents fetched | 8.000 | 0 |
| Logical response | 180 KiB | 6 KiB |
| p95 Query | 220 ms | 34 ms |
| Index footprint tăng thêm | Không | 800 MiB |

**Đây là số liệu minh họa, không phải đo từ Couchbase.** C cải thiện cả scan/fetch và bytes; không thể quy toàn bộ cho câu `SELECT` hẹp hơn. Cần xem write overhead và tài nguyên index.

## 36. Dấu hiệu anti-pattern và hướng sửa

| Dấu hiệu | Tại sao tốn tài nguyên | Cách xử lý |
| --- | --- | --- |
| `SELECT *` cho màn hình list | Chuyển nhiều field không cần | Projection DTO |
| Repo `findById` rồi mới lấy status | KV GET có thể đọc toàn JSON | `lookupIn` khi document lớn |
| Chỉ đổi DTO sau khi đã đọc full entity | HTTP bytes giảm nhưng KV bytes không | Kiểm tra truy vấn thực |
| LIMIT 20 nhưng scan lớn | Residual filter/sort không pushdown | Index theo WHERE/ORDER |
| `OFFSET 20000` | Bỏ qua nhiều rows | Keyset pagination nếu phù hợp |
| `findAll` rồi filter/sort trong Java | Materialize cả dataset | Push filter/order/limit vào SQL++ |
| JOIN 1-n chỉ để biết “có liên quan” | Nhân row trung gian | EXISTS/ANY/semi-join theo use case |
| UNNEST array để kiểm tra có SKU | Row per item | `ANY ... SATISFIES` |
| Fetch 1000 IDs rồi 1000 GET full JSON | N+1/fan-out | Projection cover/giới hạn subset |
| `collectList` trên stream vô hạn/lớn | Tăng heap và GC | LIMIT/paging/bounded streaming |
| COUNT mọi request để biết hasNext | Scan/aggregate dư | N+1 rows/Slice khi hợp đồng cho phép |
| Covering index quá rộng | Index size/write amplification | Chỉ cover hot projections |
| Partial index không được dùng | Query predicate không bao hàm filter | Xem EXPLAIN, chỉnh query/index |
| Không có tenant filter | Rò dữ liệu, dù trả ít fields | Filter authorization trên server |
| Query nhanh hơn nhưng consistency yếu hơn | Benchmark không tương đương | Khóa consistency |
| Chỉ đo response bytes | Bỏ qua scan/fetch | Đo cả intermediate metrics |

## 37. Tình huống thực hành: danh sách đơn hàng và báo cáo

Giả sử service có:

~~~text
commerce.sales.orders
commerce.sales.shipments
commerce.checkout.carts
~~~

Các API:

- `GET /orders/{id}`: một order theo key.
- `GET /orders/{id}/status`: chỉ ID và status.
- `GET /customers/{id}/orders`: 20 order mới nhất.
- `GET /customers/{id}/orders?status=PAID`: lọc status.
- `GET /orders?sku=SKU-A`: order có SKU-A trong items.
- `GET /customers/{id}/shipment-summary`: một dòng summary.
- `GET /reports/revenue-by-currency`: vài dòng aggregate.
- `GET /orders?page=1000`: trang rất sâu.

**Câu hỏi:**

1. Vì sao GET theo ID không nhất thiết cần SQL++ projection?
2. Khi nào `lookupIn` tốt hơn `get` toàn JSON?
3. Vì sao mapping DTO từ entity sau `findById` chưa chắc giảm network bytes?
4. Với màn hình list, hãy viết `SELECT` bốn field thay `SELECT *`.
5. Đề xuất index cho `customerId + status + ORDER BY createdAtEpochMs`.
6. Phân biệt giảm response bytes và giảm `Fetch` trong `EXPLAIN`.
7. Nếu `LIMIT 20` mà scan 50.000 entries, cần điều tra gì?
8. Viết cursor pagination có tie-breaker `orderSequence`.
9. Khi nào `COUNT` tốn nhiều hơn lấy 21 rows để biết hasNext?
10. Với query join shipment, vì sao LIMIT sau join có thể cho 20 shipment rows thay vì 20 orders?
11. Dùng `ANY` thay `UNNEST` khi chỉ cần biết có SKU-A như thế nào?
12. Khi nào nên GROUP BY ở server thay vì tải toàn bộ orders về Java?
13. Vì sao `collectList` có thể gây OOM dù pipeline reactive?
14. Dùng những metrics gì để chứng minh optimizer giảm intermediate documents?
15. Nếu covering index giảm query latency nhưng làm write p99 tăng, tiêu chí chấp nhận là gì?
16. Tại sao không được xóa tenant filter hoặc hạ `REQUEST_PLUS` để benchmark đẹp?

**Định hướng lời giải:** chọn projection theo API contract, KV subdocument cho key đã biết, index theo predicate/order để hạn chế scan/fetch, paging thay OFFSET sâu, hạn chế JOIN/UNNEST/aggregation dư, đo p95/p99, rows/bytes/CPU và giữ đúng tính nhất quán.

## 38. Checklist đưa vào production

- [ ] Đã phân biệt “ít field trả về” và “ít document/row trung gian”.
- [ ] Biết chính xác endpoint cần field nào, không tự dùng `SELECT *`.
- [ ] Tách list DTO với entity domain khi phù hợp.
- [ ] Đã kiểm tra Spring Data generated SQL++ và converter behavior.
- [ ] Không coi DTO tạo sau full GET là giảm KV payload.
- [ ] Với exact document key, đánh giá SDK `lookupIn` nếu chỉ cần vài path.
- [ ] Projection nested fields có xử lý NULL/MISSING đúng.
- [ ] Có index theo equality/range/ORDER BY của hot queries.
- [ ] EXPLAIN cho thấy spans và Fetch/Order/Limit rõ ràng.
- [ ] Covering index giúp tránh Fetch **trên plan thực** chứ không chỉ trong lý thuyết.
- [ ] Đã đánh giá index width/write amplification.
- [ ] LIMIT được thực thi trong SQL++, không chỉ sau Java stream.
- [ ] Tránh OFFSET sâu khi cursor pagination đáp ứng contract.
- [ ] Phân trang có tie-breaker xác định và giới hạn số rows.
- [ ] Không COUNT đầy đủ mỗi request nếu chỉ cần hasNext.
- [ ] Không tải cả collection vào Java để filter/sort.
- [ ] JOIN có cardinality đúng; không nhân row vô ý.
- [ ] UNNEST chỉ dùng khi thật sự cần phần tử; cân nhắc ANY để kiểm tra tồn tại.
- [ ] Aggregate đúng nơi, không truyền mọi document để tính vài số.
- [ ] Reactive pipeline có LIMIT/paging và không collectList vô hạn.
- [ ] N+1 KV fan-out được kiểm soát, không phát không giới hạn.
- [ ] Query/SDK errors, timeout và result shape được test.
- [ ] Tenant, ownership, type filter, CAS và TTL không bị bỏ khi tối ưu.
- [ ] Scan consistency giữ đúng business contract.
- [ ] Đã benchmark latency p50/p95/p99 và throughput hữu ích.
- [ ] Đã đo index scan/fetch/intermediate rows cùng logical/wire bytes.
- [ ] JVM heap/GC, Query/Index/Data CPU và write p99 được kiểm tra.
- [ ] Có run ID, version, dataset, workload và query plan lưu lại.
- [ ] Rollout index/query change có kiểm soát và rollback rõ ràng.

## 39. Tổng kết

Trong **Spring Data Couchbase**, giảm số trường trả về bằng `SELECT` tường minh, `SELECT RAW`, DTO projection hoặc KV `lookupIn` có thể giảm **serialized bytes, network transfer và chi phí mapping**. Nhưng một response nhỏ không chứng minh Query service đã xử lý ít document.

Để giảm số tài liệu trung gian, cần xử lý **predicate và index sớm**, giảm Fetch bằng covering index khi có lợi, tận dụng `ORDER BY/LIMIT`, tránh OFFSET sâu, hạn chế JOIN/UNNEST làm nhân rows và chuyển aggregation thích hợp sang server. Spring Data repository, `CouchbaseTemplate`, SDK blocking/reactive có cách materialize khác nhau; chúng phải được đo theo đường truy cập thật.

Một tối ưu đáng tin cậy phải cải thiện **scan/fetch count, result bytes, latency và throughput**, đồng thời giữ nguyên contract kết quả, authorization, consistency, CAS/TTL và chi phí index/write trong giới hạn chấp nhận. `EXPLAIN` kết hợp benchmark trước/sau là cơ sở đưa ra quyết định, không phải giả định rằng `SELECT` ít field luôn tương đương ít công việc.

