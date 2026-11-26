# Chọn mức nhất quán cho từng truy vấn Template trong Spring Data Couchbase

## 1. Mục tiêu và câu hỏi cần trả lời

Trong **Spring Data Couchbase**, `CouchbaseTemplate` là API làm việc với document và truy vấn trực tiếp ở mức linh hoạt hơn Repository. Khi viết một phương thức dùng `findByQuery(...)`, lập trình viên có thể quyết định **scan consistency cho riêng truy vấn đó**, thay vì buộc mọi truy vấn của ứng dụng dùng cùng một mức độ mới dữ liệu.

Câu hỏi trọng tâm của chương **Tính nhất quán**:

> Khi một truy vấn SQL++ qua secondary index cần thấy các mutation vừa được xác nhận, làm thế nào yêu cầu Index Service bắt kịp dữ liệu mà không bắt các truy vấn khác phải chờ không cần thiết?

Spring Data Couchbase cung cấp hai cách quan trọng trong các dòng phiên bản hiện đại:

~~~java
// Cách 1: option trên fluent query operation.
template.findByQuery(OrderDocument.class)
        .withConsistency(QueryScanConsistency.REQUEST_PLUS)
        .matching(query)
        .all();

// Cách 2: option nằm trong Query object.
Query query = Query.query(QueryCriteria.where("customerId").is(customerId))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS);
~~~

Cả hai cách đều nhắm tới **scan consistency của truy vấn SQL++**. Không nên thiết lập hai mức mâu thuẫn trên cùng một query rồi trông chờ framework tự đoán ý định; trong bài này, từng ví dụ sẽ chọn **một** nơi khai báo nhất quán.

Sau bài học, bạn có thể:

1. Phân biệt `NOT_BOUNDED` và `REQUEST_PLUS` đối với query được thực thi qua index.
2. Viết một DAO dùng `CouchbaseTemplate.findByQuery(...).withConsistency(...).matching(...).all()`.
3. Đặt `Query.scanConsistency(...)` cho một Query riêng khi phù hợp API.
4. Sử dụng `ReactiveCouchbaseTemplate` mà không vô tình block WebFlux.
5. Thiết kế policy độ mới theo use case, SLO, pagination và ngân sách timeout.
6. Phân biệt scan consistency với KV, CAS, TTL, durability và transaction.
7. Viết integration test và quan sát để xác minh hành vi cũng như lựa chọn cấu hình.

Phạm vi module **SPRING_DATA_COUCHBASE** rộng hơn riêng query: xây dựng tầng dữ liệu bằng document mapping, Repository, Template và SQL++, cùng thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch, API reactive, hiệu năng và vận hành. Bài này tập trung vào **đặt mức nhất quán tại từng lần gọi Template**.

## 2. Một tình huống thực tế: vừa tạo đơn, vừa tải lịch sử

Hệ thống bán hàng có collection `shop.sales.orders`. Một đơn hàng có metadata key `order::o-1001` và JSON body:

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 259000
}
~~~

Người dùng đặt hàng và ứng dụng lưu document thành công. Sau đó ứng dụng có hai nhu cầu:

- **Xem đúng đơn vừa lưu:** đã có ID `order::o-1001`, có thể dùng KV theo key.
- **Xem danh sách 20 đơn mới nhất của khách:** lọc theo `customerId`, sắp theo `createdAt`, phải dùng truy vấn theo field và index phù hợp.

Hai nhu cầu này không nhất thiết cần cùng một chính sách đọc.

~~~mermaid
flowchart TD
    A["Ứng dụng save Order thành công"] --> D[("Couchbase Data Service")]
    D --> E["KV get theo document ID"]
    D --> M["Luồng mutation cập nhật index"]
    M --> I[("Index Service")]
    I --> Q["SQL++ query qua Template"]
    E --> K["Chi tiết một Order"]
    Q --> L{"Danh sách cần mới tới mức nào?"}
    L -->|Cho phép trễ ngắn| N["NOT_BOUNDED"]
    L -->|Cần index bắt kịp mốc request| R["REQUEST_PLUS"]
~~~

Sau khi ghi, đường KV thường đọc được document qua active data path theo key đã biết, trong khi secondary index có thể cập nhật chậm hơn. `NOT_BOUNDED` không đợi index đủ mới trước khi scan; `REQUEST_PLUS` yêu cầu đợi mốc index thích hợp tại thời điểm query. Cả hai vẫn là truy vấn **trên dữ liệu thực**, không phải cách tạo một transaction mới.

## 3. Đặt đúng khái niệm: Query consistency không phải consistency của mọi thao tác

| Cơ chế | Trả lời câu hỏi | Có phải điều khiển bằng `withConsistency(REQUEST_PLUS)`? |
| --- | --- | --- |
| KV read theo ID | Document hiện tại theo key là gì? | Không, đây không phải index scan SQL++ |
| Secondary index scan | Index dùng cho query đã bắt kịp mutation tới đâu? | **Có**, nếu query đi qua cơ chế tương ứng |
| CAS / optimistic locking | Document có bị sửa từ lúc tôi đọc không? | Không |
| Durability | Ghi đã đạt mức xác nhận bền nào? | Không |
| TTL/expiry | Document hết hạn khi nào? | Không |
| Multi-document transaction | Nhiều mutation có cùng ranh giới commit không? | Không |
| Replica hoặc cross-cluster read | Bản sao đã bắt kịp nguồn tới đâu? | Không |
| Search/FTS freshness | Search index đã phản ánh thay đổi gì? | Không; Search có API consistency riêng |

Giả sử bạn cập nhật `status` từ `CREATED` sang `CONFIRMED` và lưu thành công. Một SQL++ query `WHERE status = "CREATED"` dùng index chưa cập nhật có thể vẫn bị ảnh hưởng bởi trạng thái index cũ. Query `REQUEST_PLUS` có thể cần chờ index phản ánh mutation tới mốc được yêu cầu.

Tuy nhiên, `REQUEST_PLUS` **không tạo snapshot cố định** tại thời điểm cập nhật đó; một request khác có thể tiếp tục đổi đơn thành `CANCELLED`. Query thấy giá trị mới hơn không phải lỗi consistency.

## 4. Hai chế độ chọn theo từng truy vấn

### 4.1. NOT_BOUNDED

`QueryScanConsistency.NOT_BOUNDED` biểu thị: query **không bắt buộc đợi** index cập nhật tới mốc tất cả mutation mới trước khi scan.

Đặc điểm:

- Có thể trả kết quả nhanh hơn khi index còn đang bắt kịp dữ liệu.
- Có thể tạm thời thiếu document mới, còn thông tin liên quan document đã sửa/xóa, tùy query plan.
- **Không** có nghĩa “bắt buộc trả dữ liệu cũ”: index có thể đã đủ mới.
- Phù hợp danh sách hoặc báo cáo chấp nhận độ trễ quan sát được.

### 4.2. REQUEST_PLUS

`QueryScanConsistency.REQUEST_PLUS` yêu cầu index liên quan **đạt mốc consistency của query** trước khi scan. Đây là lựa chọn khi ứng dụng yêu cầu query theo field phải bao gồm những thay đổi đã được xác nhận trước mốc query, với điều kiện dữ liệu vẫn khớp `WHERE` và không bị loại bởi `ORDER BY/LIMIT`.

Đặc điểm:

- Giúp thực hiện read-after-write qua SQL++ query theo field, không cần giữ mutation token.
- Có thể làm query **đợi Index Service**, tăng latency hoặc timeout nếu index lag.
- Không tự tạo index, sửa sai query, bảo đảm uniqueness hay đồng bộ tất cả dịch vụ.
- Mutation **sau mốc query** vẫn có thể xảy ra; không nên suy rằng mọi row phản ánh đúng một thời điểm không thay đổi.

### 4.3. Bảng quyết định

| Nhu cầu | Policy gợi ý | Lý do |
| --- | --- | --- |
| Báo cáo cập nhật định kỳ, chấp nhận trễ | `NOT_BOUNDED` | Không cần chi phí chờ index mới |
| Lịch sử đơn bắt buộc phản ánh ghi vừa hoàn tất | `REQUEST_PLUS` | Query đợi index đạt mốc phù hợp |
| Đọc một Order vừa ghi và đã có ID | KV `findById` | Không cần secondary index |
| Kiểm tra email có duy nhất dưới nhiều request đồng thời | Ghi có điều kiện/giao dịch phù hợp | Scan consistency **không** biến check-then-insert thành atomic |
| Xác nhận Order chỉ khi status hợp lệ | KV + CAS/conditional write | Giải quyết xung đột ở đường ghi |
| Search văn bản tự nhiên | Search API + Search index | Không dùng SQL++ scan consistency thay Search |
| Query cần thấy chính các mutation đã biết qua token | Mutation-state-based consistency nếu stack hỗ trợ | Cơ chế khác, thường cần token và API phù hợp |

Tư duy đúng là **SLO độ mới của từng use case**, thay vì “mức cao hơn luôn tốt hơn”.

## 5. Chuẩn bị entity, keyspace và chỉ mục

Giả sử ứng dụng có bucket `shop`, scope `sales` và collection `orders` đã được tạo sẵn. Entity minh họa:

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

    @Field
    private long totalVnd;

    @Version
    private Long version;

    public OrderDocument() { }

    public OrderDocument(
            String id, String customerId,
            String status, String createdAt, long totalVnd) {
        this.id = id;
        this.customerId = customerId;
        this.status = status;
        this.createdAt = createdAt;
        this.totalVnd = totalVnd;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
    public long getTotalVnd() { return totalVnd; }
    public void setTotalVnd(long totalVnd) {
        this.totalVnd = totalVnd;
    }
    public Long getVersion() { return version; }
    public void setVersion(Long version) {
        this.version = version;
    }
}
~~~

- `@Id` ánh xạ metadata document key, không phải một field JSON luôn tồn tại.
- `@Version` gắn với CAS để hỗ trợ optimistic locking khi ghi, **khác** với index freshness.
- `@Scope` và `@Collection` chỉ định keyspace theo khả năng của phiên bản Spring Data. Chỉ cấu hình bucket không tự làm entity chuyển sang collection mong muốn.
- `createdAt` trong ví dụ là chuỗi ISO-8601 UTC có quy tắc thống nhất. Nếu sử dụng `Instant`, cần kiểm tra converter và kiểu dữ liệu thực tế trong index.

Cấu hình Spring Boot khởi đầu:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: YOUR_COUCHBASE_USERNAME
    password: YOUR_COUCHBASE_PASSWORD
  data:
    couchbase:
      bucket-name: shop
~~~

Credential thực phải đến từ secret/environment; không đưa mật khẩu thật vào source control. Cluster và tài khoản phải có quyền Data/Query phù hợp. Với `findByQuery` cần một secondary index cho điều kiện lọc và sắp xếp.

SQL++ minh họa:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Ví dụ câu truy vấn phục vụ trang lịch sử:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt, o.totalVnd
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Đây là query minh họa, không nhất thiết giống nguyên văn SQL++ do Spring Data tạo. Generated SQL++ có thể thêm điều kiện type discriminator và metadata để tái tạo entity. Cần kiểm tra `EXPLAIN`, index được dùng, quyền query và số row thật.

## 6. Cách ưu tiên: chọn mức consistency ngay trên fluent Template operation

Cách dễ đọc với một DAO là gọi **`withConsistency(...)`** trên kết quả của `findByQuery(Entity.class)`. Phương thức này nhận enum `QueryScanConsistency` của Java SDK và áp dụng cho **lần thực thi query đó**.

~~~java
import static org.springframework.data.couchbase.core.query.Query.query;
import static org.springframework.data.couchbase.core.query.QueryCriteria.where;

import java.util.List;

import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.data.couchbase.core.query.Query;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Repository;

@Repository
public class OrderQueryDao {

    private final CouchbaseTemplate template;

    public OrderQueryDao(CouchbaseTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> listByCustomer(
            String customerId, QueryScanConsistency consistency) {

        Query query = query(where("customerId").is(customerId))
                .with(Sort.by(Sort.Direction.DESC, "createdAt"))
                .limit(20);

        return template.findByQuery(OrderDocument.class)
                .withConsistency(consistency)
                .matching(query)
                .all();
    }
}
~~~

Lưu ý về tên `query`: phương thức static `Query.query(...)` và biến cục bộ `Query query` cùng xuất hiện hợp lệ khi khai báo; sau khi xây dựng biến, lời gọi trên fluent Template nhận đúng object.

Cách dùng từ application service:

~~~java
import static com.couchbase.client.java.query.QueryScanConsistency.NOT_BOUNDED;
import static com.couchbase.client.java.query.QueryScanConsistency.REQUEST_PLUS;

List<OrderDocument> ordinary =
        dao.listByCustomer("c-1001", NOT_BOUNDED);

List<OrderDocument> mustIncludeAcknowledgedWrites =
        dao.listByCustomer("c-1001", REQUEST_PLUS);
~~~

Đây là **hai lần gọi cùng DAO** nhưng yêu cầu consistency khác nhau. Không cần tạo hai bean Template, không đổi cấu hình toàn cục và không gắn `@ScanConsistency` lên toàn bộ Repository.

### 6.1. Vì sao dùng QueryCriteria thay ghép SQL++ thủ công?

`QueryCriteria.where("customerId").is(customerId)` biểu diễn điều kiện một cách có cấu trúc để Spring Data chuyển thành truy vấn và binding tương ứng. Không nối chuỗi input người dùng vào SQL++ theo mẫu:

~~~java
// Tránh: dữ liệu người dùng trở thành một phần cú pháp SQL++.
String sql = "SELECT * FROM orders WHERE customerId = '"
        + customerId + "'";
~~~

Với query phức tạp, cách mapping và binding có thể cần bổ sung hoặc dùng SDK QueryOptions có parameters. Dù chọn API nào cũng phải kiểm soát injection, quyền tenant và data projection.

### 6.2. Tại sao giới hạn 20 row?

`REQUEST_PLUS` không giúp một query thiếu `LIMIT` tránh trả hàng trăm nghìn document. Với lịch sử đơn, cần giới hạn tại server và thiết kế phân trang. Khi dùng `Sort`, bảo đảm field `createdAt` có kiểu/định dạng nhất quán và index phục vụ filter/sort phù hợp.

### 6.3. Khi nào nên dùng `one()` thay `all()`?

`all()` trả tập kết quả của query. Nếu domain invariant bảo đảm có tối đa một document theo điều kiện và API dùng `one()`, phải hiểu trường hợp không có hoặc có nhiều kết quả. Với email khách hàng, nếu uniqueness chưa được bảo vệ ở đường ghi, đừng giả định `one()` tự áp đặt tính duy nhất. Khi đã có metadata ID của document, ưu tiên KV `findById(...).one(id)`.

## 7. Cách thứ hai: gắn consistency vào Query object

Lớp `org.springframework.data.couchbase.core.query.Query` hỗ trợ `scanConsistency(QueryScanConsistency)`. Có thể tạo một Query object **mới cho mỗi lời gọi**, gắn mức tương ứng, rồi truyền vào `matching(query)`.

~~~java
import static org.springframework.data.couchbase.core.query.Query.query;
import static org.springframework.data.couchbase.core.query.QueryCriteria.where;

import java.util.List;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.data.couchbase.core.query.Query;

public class OrderQueryObjectDao {
    private final CouchbaseTemplate template;

    public OrderQueryObjectDao(CouchbaseTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> byStatus(
            String status, QueryScanConsistency consistency) {

        Query criteriaQuery = query(where("status").is(status))
                .scanConsistency(consistency)
                .limit(50);

        return template.findByQuery(OrderDocument.class)
                .matching(criteriaQuery)
                .all();
    }
}
~~~

Trong phương pháp này, **Query object mang consistency**, còn fluent operation không gọi `withConsistency(...)` riêng. Hai lựa chọn đều là một phần của API Spring Data Couchbase hiện đại; hãy xác minh hành vi tương ứng trong phiên bản được quản lý bởi Spring Boot của dự án.

### 7.1. Không giữ một Query mutable làm biến dùng chung

Mẫu nguy hiểm:

~~~java
// KHÔNG nên chia sẻ một Query rồi thay đổi policy giữa các request.
private static final Query SHARED =
        query(where("status").is("CREATED"));

// Request A: SHARED.scanConsistency(REQUEST_PLUS)
// Request B: SHARED.scanConsistency(NOT_BOUNDED)
~~~

`Query.scanConsistency(...)` là thao tác cấu hình instance. Nếu cùng object bị tái sử dụng và sửa đồng thời, hai request có thể ảnh hưởng lựa chọn của nhau. **Tái sử dụng bean CouchbaseTemplate**, nhưng xây Query mới trong từng method/request hoặc dùng cấu trúc bất biến do ứng dụng tự quản lý.

### 7.2. Không tạo hai nguồn cấu hình mâu thuẫn

Tránh:

~~~java
Query query = query(where("status").is("CREATED"))
        .scanConsistency(QueryScanConsistency.NOT_BOUNDED);

template.findByQuery(OrderDocument.class)
        .withConsistency(QueryScanConsistency.REQUEST_PLUS)
        .matching(query)
        .all();
~~~

Ngay cả khi phiên bản xác định rõ mức ưu tiên, đoạn code buộc người đọc đoán ý định. Quy ước tốt là **một query chỉ chọn policy ở một nơi**; nếu tổ chức cần override theo layer, phải có hợp đồng và test precedence rõ ràng.

## 8. Chọn policy dựa vào SLO của từng use case

Đừng nhận trực tiếp giá trị `REQUEST_PLUS` từ query parameter công khai mà không có giới hạn vì client có thể khiến hệ thống tốn chi phí chờ index. Một giải pháp là định nghĩa chính sách nghiệp vụ riêng:

~~~java
public enum OrderReadFreshness {
    ALLOW_INDEX_LAG,
    REQUIRE_CURRENT_INDEX
}
~~~

Ánh xạ policy sang SDK enum ở persistence boundary:

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;

public final class QueryFreshnessPolicy {
    private QueryFreshnessPolicy() { }

    public static QueryScanConsistency forOrderList(
            OrderReadFreshness freshness) {

        return switch (freshness) {
            case ALLOW_INDEX_LAG ->
                    QueryScanConsistency.NOT_BOUNDED;
            case REQUIRE_CURRENT_INDEX ->
                    QueryScanConsistency.REQUEST_PLUS;
        };
    }
}
~~~

Service:

~~~java
public List<OrderDocument> recentOrdersForCustomer(
        String customerId, boolean justPlacedOrder) {

    OrderReadFreshness freshness = justPlacedOrder
            ? OrderReadFreshness.REQUIRE_CURRENT_INDEX
            : OrderReadFreshness.ALLOW_INDEX_LAG;

    return orderQueryDao.listByCustomer(
            customerId,
            QueryFreshnessPolicy.forOrderList(freshness));
}
~~~

Đoạn trên biểu đạt **chính sách đơn giản cho ví dụ**, không phải một tín hiệu bảo mật. Trong thực tế, service cần biết luồng ghi trước đó có hoàn tất và có cùng keyspace không, giới hạn tải, và có thể chọn cách **trả Order vừa lưu** thay vì chạy lại query lịch sử.

### 8.1. Lợi ích khi tách policy khỏi API của SDK

- Service nói bằng ngôn ngữ nghiệp vụ: “danh sách vừa đặt hàng phải mới”.
- Persistence layer chịu trách nhiệm chuyển thành consistency option.
- Test policy không cần nối tới Couchbase; test **tính đúng đắn query** vẫn cần database thật.
- Có thể thay chiến lược khi xuất hiện khả năng mutation token, cache hay read model riêng mà không sửa mọi controller.

### 8.2. Khi nào nên khai báo luôn enum ở DAO?

Nếu DAO chỉ dành cho application code nội bộ, nhận trực tiếp `QueryScanConsistency` cũng hợp lý. Nhiều lớp trừu tượng không có giá trị sẽ làm code khó đọc. Hãy chọn cách đơn giản nhất vẫn bảo vệ được ý định và SLO.

## 9. Phạm vi cài đặt: một query khác với mặc định toàn Template

`CouchbaseTemplate` có thể có default scan consistency được cấu hình qua bean/configuration theo phiên bản. Entity `@Document` hoặc Repository cũng có thể mang metadata consistency. Nhưng yêu cầu của bài là **chọn từng truy vấn**.

| Nơi chọn consistency | Phạm vi tác động dự kiến | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| `withConsistency(...)` trên fluent operation | Một lần gọi query | Rõ, cục bộ, dễ kiểm thử | Lặp code nếu nhiều query chung policy |
| `Query.scanConsistency(...)` | Query instance được truyền tới Template | Đi cùng filter/sort/limit | Query mutable nếu tái sử dụng |
| Metadata entity/repository | Nhiều thao tác liên quan type | Ít lặp cấu hình | Có thể chờ index ngoài ý muốn |
| Template default | Nhiều query qua cùng bean | Chính sách mặc định nhất quán | Khó phân biệt endpoint cần nhanh |
| SDK `QueryOptions.scanConsistency(...)` | Một SQL++ SDK query | Điều khiển trực tiếp | Bỏ qua một số mapping/converter Spring Data |

**Khuyến nghị cho lớp Query DAO:** bắt đầu bằng `withConsistency(...)` hoặc `Query.scanConsistency(...)` mỗi lần gọi. Chỉ đưa thành default rộng hơn nếu **mọi** query liên quan có cùng SLO và đã đo tác động.

### 9.1. @ScanConsistency của Repository không thay Query của Template

`@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)` thuộc `org.springframework.data.couchbase.repository` và thường cấu hình **repository queries**. Nó không phải chú thích bắt buộc cho DAO dùng Template và không nên xem như cách đổi mọi SQL++ query trong ứng dụng.

Ví dụ:

~~~java
@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
List<OrderDocument> findByCustomerId(String customerId);
~~~

Đây là cách khai báo cho method Repository. Với Template custom query, ta có thể dùng chính `withConsistency(...)` ngay lúc thực thi, phù hợp khi mỗi yêu cầu nghiệp vụ cần độ mới khác nhau. Cần chú ý precedence giữa các cấu hình nếu dự án kết hợp nhiều tầng; xác nhận bằng integration test trên bộ phiên bản cụ thể.

## 10. Phân biệt findById và findByQuery trong Template

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public class OrderDetailDao {
    private final CouchbaseTemplate template;

    public OrderDetailDao(CouchbaseTemplate template) {
        this.template = template;
    }

    public OrderDocument load(String documentId) {
        return template.findById(OrderDocument.class)
                .one(documentId);
    }
}
~~~

Ở đây `documentId` phải có dạng đầy đủ mà ứng dụng dùng, ví dụ `order::o-1001`. Thao tác `findById` là đường **KV**, không phải SQL++ secondary-index scan. Đặt `REQUEST_PLUS` cho query danh sách sẽ không tác động tới lệnh KV này.

Sơ đồ phân loại:

~~~mermaid
flowchart TD
    A{"Có biết document ID?"}
    A -->|Có| K["template.findById(...).one(id)"]
    A -->|Không, cần lọc theo field| Q["template.findByQuery(Entity.class)"]
    K --> G["KV, không cần secondary index"]
    Q --> P{"Cần query phản ánh mutation mới tới mốc request?"}
    P -->|Có| R["withConsistency(REQUEST_PLUS)"]
    P -->|Không| N["withConsistency(NOT_BOUNDED)"]
    R --> IDX["SQL++ / Index Service"]
    N --> IDX
~~~

Điều này có thể giảm độ trễ đáng kể ở luồng **vừa ghi xong, biết key của document**: trả ngay kết quả `save/upsert` hoặc KV đọc lại thay vì ép query theo field phải chờ index.

## 11. ReactiveCouchbaseTemplate: consistency riêng cho từng Flux/Mono

Một ứng dụng Spring WebFlux có thể dùng `ReactiveCouchbaseTemplate`. Giao diện fluent query reactive cũng hỗ trợ `withConsistency(QueryScanConsistency)` trong các phiên bản tương thích.

~~~java
import static org.springframework.data.couchbase.core.query.Query.query;
import static org.springframework.data.couchbase.core.query.QueryCriteria.where;

import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.core.ReactiveCouchbaseTemplate;
import org.springframework.data.couchbase.core.query.Query;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Flux;

public class ReactiveOrderQueryDao {

    private final ReactiveCouchbaseTemplate template;

    public ReactiveOrderQueryDao(
            ReactiveCouchbaseTemplate template) {
        this.template = template;
    }

    public Flux<OrderDocument> recentForCustomer(
            String customerId, QueryScanConsistency consistency) {

        Query query = query(where("customerId").is(customerId))
                .with(Sort.by(Sort.Direction.DESC, "createdAt"))
                .limit(20);

        return template.findByQuery(OrderDocument.class)
                .withConsistency(consistency)
                .matching(query)
                .all();
    }
}
~~~

`Flux<OrderDocument>` là luồng 0..n kết quả. Nó **không tự làm SQL++ query nhanh hơn**, không biến index thành nhất quán tức thì và cũng không làm mất chi phí đợi khi dùng `REQUEST_PLUS`.

### 11.1. Ghép ghi trước rồi query sau

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import com.couchbase.client.java.query.QueryScanConsistency;

public Flux<OrderDocument> saveThenLoadRecent(
        Mono<OrderDocument> savePublisher,
        String customerId) {

    return savePublisher.thenMany(
            reactiveOrderQueryDao.recentForCustomer(
                    customerId,
                    QueryScanConsistency.REQUEST_PLUS));
}
~~~

Ví dụ giả định `savePublisher` chứa thao tác ghi thực và `reactiveOrderQueryDao` đã được inject. `thenMany` đảm bảo publisher query được subscribe **sau khi** publisher save hoàn tất thành công, nhưng không tự tạo transaction. Nếu write lỗi, query không tiếp tục theo luồng thành công bình thường.

**Không dùng:**

~~~java
// Sai trong WebFlux event-loop:
List<OrderDocument> rows = blockingTemplate
        .findByQuery(OrderDocument.class)
        .all();
return Mono.just(rows);
~~~

Đoạn trên gọi I/O blocking trước khi tạo `Mono`. Dùng Reactive Template thực sự khi cần pipeline non-blocking. Nếu phải tích hợp client blocking tạm thời, cô lập nó bằng scheduler dành cho blocking với giới hạn phù hợp, nhưng đó không biến truy cập bản chất thành non-blocking.

### 11.2. Backpressure không bỏ qua chỉ mục hoặc số hàng truy vấn

Reactive `Flux` có thể giúp phối hợp kết quả, nhưng đừng truy vấn toàn bộ lịch sử rồi áp dụng `take(20)` tại Java để thay thế `LIMIT 20` ở server. Cần phân trang từ Query object và kiểm soát concurrency downstream; độ mới của index là một mối quan tâm khác với backpressure.

## 12. Phân trang, sort, projection và độ mới dữ liệu

Một query `REQUEST_PLUS` đã đợi index bắt kịp vẫn có thể **không trả document bạn muốn** vì logic query:

- `WHERE` không khớp.
- Tham số customerId/tenantId sai.
- `ORDER BY` và `LIMIT` loại document khỏi trang.
- Document thay đổi sau mốc consistency.
- Generated query có type discriminator không khớp.
- Entity map tới nhầm scope/collection.
- Query plan không dùng index dự kiến.
- Lỗi timeout/thiếu quyền bị tầng ứng dụng che giấu thành danh sách rỗng.

Vì thế, hãy tách:

1. **Query semantics:** điều kiện lọc, sắp xếp, projection, tenant và page.
2. **Query index freshness:** mốc mutation index phải bắt kịp.
3. **Domain consistency:** có cần CAS/transaction bảo vệ bất biến không?

### 12.1. Query object có limit và sort

~~~java
Query query = Query.query(
        QueryCriteria.where("customerId").is("c-1001"))
        .with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")))
        .limit(20);
~~~

Đoạn trên minh họa ý định **sắp xếp ổn định**. Lưu ý: trường `id` của Java entity thường ánh xạ document ID metadata, **không nhất thiết là JSON body field**. Việc `Sort.by("id")` được chuyển thành biểu thức SQL++ nào phụ thuộc mapping; đừng sử dụng đoạn minh họa này như cam kết tie-breaker `META().id` ở mọi phiên bản. Nếu cần phân trang với tie-breaker theo metadata ID, hãy xem generated SQL++ và chọn query/projection hoặc SDK query rõ ràng.

### 12.2. Không hiểu LIMIT là bảo đảm read-your-writes

Một Order vừa tạo không xuất hiện trong 20 đơn mới nhất có thể là do có nhiều Order khác mới hơn theo sắp xếp; index hoàn toàn có thể đã mới. Trước khi tăng consistency, hãy xác nhận ID, điều kiện, thứ tự, pagination và document nguồn.

### 12.3. Count và các thao tác Template khác

Template có các thao tác như `count(Query, Class<?>)`, `exists` hoặc `removeByQuery` theo khả năng phiên bản. Với query tổng hợp/count dựa vào index, cần đặt policy trên **đúng Query/operation**; không mặc định một cấu hình trên `findByQuery` sẽ áp dụng cho các phương thức khác trong ứng dụng. Với thao tác xóa theo điều kiện SQL++, còn phải cân nhắc concurrency, tính nguyên tử và an toàn nghiệp vụ; không chọn consistency như một cách thay thế transaction.

## 13. Khi cần mức nhất quán theo mutation token

Bên cạnh `NOT_BOUNDED` và `REQUEST_PLUS`, Couchbase Java SDK hỗ trợ mô hình yêu cầu query đợi index phản ánh **những mutation cụ thể đã quan sát** bằng mutation token/state, thường được gọi là `at_plus` hoặc consistent-with.

Ý tưởng:

~~~text
SDK KV upsert Order A  -> mutation token A
SDK KV upsert Order B  -> mutation token B
                           |
                           v
                    MutationState(A,B)
                           |
                           v
          Query yêu cầu consistent-with(state)
                           |
                           v
             Index bắt kịp các mốc đã chỉ ra
~~~

### 13.1. Khác REQUEST_PLUS thế nào?

- `REQUEST_PLUS` đợi index đến mốc dữ liệu phù hợp của request mới.
- Mutation-state-based consistency đợi những mutation cụ thể đã được nêu trong state, khi API hỗ trợ.
- Token/state **không** đại diện cho snapshot lịch sử cố định hoặc transaction ID.

### 13.2. Dùng với Template ra sao?

Các fluent interfaces của Template có thể có các phương thức `consistentWith(...)` ở một số phiên bản, nhưng cần phân biệt overload/phương thức bị deprecated với `withConsistency(QueryScanConsistency)`. Khi cần truyền `MutationState`, hãy tra Java API đúng phiên bản và xác minh signature; đừng truyền một token tự chế hoặc timestamp của máy client.

Nếu Spring Data layer không trả token trong kết quả `save` cần thiết cho luồng cụ thể, một **SDK gateway** có thể là nơi giữ kết quả mutation và chuyển mutation state sang truy vấn SDK. Khi làm vậy, phải giữ đúng keyspace, quyền, JSON mapping và logic CAS của các code path khác.

**Khuyến nghị:** Chỉ đưa mutation token vào ứng dụng khi cần phân biệt các ghi của chính request với mutation khác. Với phần lớn query Template thông thường, quyết định rõ giữa `NOT_BOUNDED` và `REQUEST_PLUS` trước.

## 14. Khi nào rơi xuống Couchbase Java SDK?

Nếu Template không phơi bày một option đặc thù ở phiên bản đang dùng, có thể gọi Java SDK Query API trực tiếp với `QueryOptions`.

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

public class RawOrderQueryGateway {
    private final Cluster cluster;

    public RawOrderQueryGateway(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult listForCustomer(
            String customerId, boolean fresh) {

        String sql = """
            SELECT META(o).id AS documentId,
                   o.customerId, o.createdAt, o.status
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            ORDER BY o.createdAt DESC
            LIMIT 20
            """;

        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .scanConsistency(fresh
                        ? QueryScanConsistency.REQUEST_PLUS
                        : QueryScanConsistency.NOT_BOUNDED);

        return cluster.query(sql, options);
    }
}
~~~

SDK trả `QueryResult`/raw rows; nó **không tự áp dụng tất cả annotation và converter của Spring Data**. Một SQL++ query SDK có thể không tự thêm điều kiện `_class` và metadata mapping như Template. Chỉ cần khác JSON shape, discriminator hoặc projection là kết quả của hai lớp API có thể khác nhau, dù consistency giống hệt.

SDK thích hợp với những thao tác chuyên biệt như sub-document, KV mutation options hoặc token-based consistency nếu phiên bản Template không đáp ứng, nhưng đừng lạm dụng nó chỉ vì không rõ cách gọi `withConsistency(...)`.

## 15. CAS, TTL, transaction và durability: ranh giới không được trộn

### 15.1. CAS: ngăn mất cập nhật trên một document

~~~text
A đọc Order, CAS = C1
B đọc Order, CAS = C1
A sửa status, ghi thành công -> CAS = C2
B cố ghi object cũ với CAS = C1 -> conflict
~~~

`@Version` ở Spring Data Couchbase có thể bảo vệ optimistic locking qua CAS. Bật `REQUEST_PLUS` trên query Template **không** ngăn B ghi đè A nếu đường ghi không có kiểm tra CAS/điều kiện thích hợp.

### 15.2. TTL: document tự hết hạn theo metadata

Một session có TTL 30 phút phải được thiết lập expiry metadata qua API hỗ trợ, không chỉ thêm JSON field `expiresAt`. Search/query theo index có thể có độ trễ phản ánh expiry. Vì thế, không xác thực một session chỉ bằng một query Template theo field với mức consistency mặc định; nên kiểm tra bằng session key và quy tắc revoke/expiry.

### 15.3. Transaction: nhiều document phải cùng thành công

Nếu tạo Order đồng thời trừ Inventory ở hai document, cần transaction Couchbase phù hợp hoặc workflow bù trừ/idempotency. `REQUEST_PLUS` không làm `order.save` và `inventory.save` trở thành một transaction và không thay thế xử lý commit ambiguous.

### 15.4. Durability: bảo đảm ghi bền khác bảo đảm index mới

Durability kiểm soát mức xác nhận mutation theo yêu cầu. SQL++ consistency kiểm soát mốc index trước khi scan. Một write có durability cao **không** tự làm query `NOT_BOUNDED` thấy ngay, và một query `REQUEST_PLUS` cũng không thay durability của write.

### 15.5. Cần ưu tiên nguồn có thẩm quyền

Đừng dùng một query Template theo field với index có thể trễ để quyết định duy nhất email, tồn kho hoặc trạng thái thanh toán. Với bất biến nghiệp vụ, thiết kế ID/conditional write/CAS/transaction/idempotency trên **đường ghi**.

## 16. Phân tích hiệu năng và ngân sách timeout

Khi query chạy với `REQUEST_PLUS`, tổng latency có thể gồm:

~~~text
Request -> Query Service
   + lập kế hoạch query
   + chờ Index Service đạt mốc consistency
   + scan/fetch/filter/sort/project
   + chuyển row về ứng dụng
   + chuyển thành Java entity
~~~

Với `NOT_BOUNDED`, query không cần đợi index tới mốc như `REQUEST_PLUS`, nhưng chi phí scan/fetch/sort vẫn có thể lớn nếu index/SQL++ thiết kế chưa tốt.

| Tín hiệu | Điều cần đo | Gợi ý xử lý |
| --- | --- | --- |
| p95/p99 tăng chỉ khi REQUEST_PLUS | Chờ index và mutation backlog | Sizing Index Service hoặc chọn policy có chọn lọc |
| Cả hai mode đều chậm | Query plan, sort/fetch, mạng | `EXPLAIN`, index, projection, pagination |
| REQUEST_PLUS timeout khi ghi hàng loạt | Index đang bắt kịp | Tăng query timeout hợp lý, giảm tải, xem SLO |
| Nhiều request chờ cùng lúc | Concurrency, scheduler/thread pool | Giới hạn tải và quan sát hàng đợi |
| Kết quả thiếu dù REQUEST_PLUS thành công | Filter/limit/tenant/type metadata | Debug query thay vì tăng consistency |
| Query WebFlux chặn event loop | Dùng blocking Template trong reactive handler | Chuyển Reactive Template hoặc cô lập blocking |

### 16.1. Mức consistency có thể là chi phí chung của endpoint

Nếu một service gọi ba query `REQUEST_PLUS` tuần tự, tổng độ trễ có thể cộng nhiều khoảng chờ. Với request có thời hạn, cần tối ưu **workflow** chứ không chỉ từng query. Nếu đã có Order ID, một KV get có thể tránh query SQL++ và index wait.

### 16.2. Không tự động retry tất cả lỗi timeout

Timeout khi query không nhất thiết là lỗi dữ liệu; cần phân biệt query/cluster lỗi, index lag, quyền và ngân sách request. Với thao tác ghi, timeout có thể khiến kết quả commit không rõ; phải có idempotency và kiểm tra trạng thái trước khi retry. Với query đọc, retry có giới hạn/backoff có thể hợp lý, nhưng retry liên tục trên Index Service đang quá tải có thể khuếch đại sự cố.

## 17. Integration test: chứng minh chính sách từng query hoạt động

Mock `CouchbaseTemplate` có thể kiểm tra DAO **chọn enum đúng**, nhưng không xác minh Index Service đã bắt kịp mutation. Cần cả **unit test cho policy** và **integration test với Couchbase thật**.

### 17.1. Thiết kế test không flaky

1. Chuẩn bị bucket/scope/collection riêng cho test và secondary index thích hợp.
2. Sinh Order ID và customerId ngẫu nhiên để tránh đụng dữ liệu khác.
3. Ghi Order bằng Template/Repository, xác nhận kết quả.
4. Đọc `findById` theo key để xác minh document nguồn.
5. Gọi query `NOT_BOUNDED` và ghi nhận kết quả; **không assert nó bắt buộc thiếu Order**.
6. Gọi query `REQUEST_PLUS` khi không có mutation cạnh tranh/xóa document; xác nhận Order xuất hiện khi `WHERE` và `LIMIT` cho phép.
7. Dọn fixture và đo thời gian p95/p99 dưới background write load phù hợp.
8. Xác minh Query Service nhận đúng consistency policy bằng trace/query request diagnostics nếu muốn kiểm tra cấu hình, vì một kết quả có row tự nó chưa chứng minh REQUEST_PLUS đã được dùng.

### 17.2. Ví dụ Spring Boot integration test

Ví dụ này giả định `OrderDocument` từ mục 5, một bean `CouchbaseTemplate` và index `customerId` đang online:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.data.couchbase.core.query.Query.query;
import static org.springframework.data.couchbase.core.query.QueryCriteria.where;

import java.time.Instant;
import java.util.UUID;

import com.couchbase.client.java.query.QueryScanConsistency;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.data.couchbase.core.query.Query;

@SpringBootTest
class TemplateConsistencyIT {

    @Autowired
    private CouchbaseTemplate template;

    @Test
    void requestPlusFindsPreviouslyInsertedOrder() {
        String id = "order::test-" + UUID.randomUUID();
        String customerId = "customer-test-" + UUID.randomUUID();

        OrderDocument order = new OrderDocument(
                id, customerId, "CREATED",
                Instant.now().toString(), 250000L);

        boolean saved = false;
        try {
            template.insertById(OrderDocument.class).one(order);
            saved = true;

            Query requestQuery = query(
                    where("customerId").is(customerId))
                    .limit(50);

            boolean found = template.findByQuery(OrderDocument.class)
                    .withConsistency(QueryScanConsistency.REQUEST_PLUS)
                    .matching(requestQuery)
                    .all()
                    .stream()
                    .anyMatch(o -> id.equals(o.getId()));

            assertTrue(found);
        } finally {
            if (saved) {
                template.removeById(OrderDocument.class).one(id);
            }
        }
    }
}
~~~

Đây là **ví dụ kiểm thử phụ thuộc fixture**: phải chuẩn bị cluster test và index, cấu hình quyền, test isolation, cleanup và xử lý tình huống timeout/ambiguous mutation. Nếu insert thực sự đã ghi nhưng client không nhận ACK, cờ `saved` chưa chắc bật; suite thực cần cơ chế dọn dữ liệu theo tiền tố test để tránh tích lũy rác. Tuyệt đối không chạy test xóa dữ liệu trên môi trường production.

### 17.3. Không viết test ép NOT_BOUNDED phải stale

~~~text
Insert Order
Query NOT_BOUNDED
assert result KHÔNG chứa Order   // Sai: index có thể bắt kịp rất nhanh.
~~~

`NOT_BOUNDED` chỉ không **đòi hỏi** index phải mới tới mốc request; nó không bắt buộc engine bỏ qua mutation đã có. Một test ổn định cần kiểm tra điều đã được hứa, không kiểm tra khả năng delay ngẫu nhiên.

### 17.4. Kiểm chứng precedence của hai cách đặt

Nếu dự án hỗ trợ cả `Query.scanConsistency(...)` và `withConsistency(...)`, nên có một test cho quy ước nội bộ: **không truyền hai chính sách mâu thuẫn trong cùng query**. Việc test chỉ dựa trên dữ liệu có thể tình cờ cho kết quả giống nhau; nếu cần xác nhận policy thực sự gửi xuống SDK, phải dùng metric/trace hoặc log cấu hình query ở môi trường test.

## 18. Xử lý lỗi và troubleshooting

| Hiện tượng | Khả năng nguyên nhân | Cách tiếp cận |
| --- | --- | --- |
| `findById` thấy Order, `findByQuery` chưa thấy | Index lag với NOT_BOUNDED | Chọn REQUEST_PLUS ở use case cần, hoặc trả saved Order |
| REQUEST_PLUS làm API chậm | Index backlog, đợi mốc query | Đo Index Service, timeout và mức tải |
| Query với REQUEST_PLUS trả thiếu row | `WHERE`, `LIMIT`, mapping, tenant filter, mutation sau query | Kiểm tra nguồn KV và generated SQL++ |
| Query lỗi vì thiếu index | Chưa tạo index hoặc index không online | Chuẩn bị index; chạy `EXPLAIN` |
| Query theo field trả sai collection | Scope/collection mapping sai | Kiểm tra `@Scope`/`@Collection` và configuration |
| Java không nhận `withConsistency` | Thư viện/version sai hoặc gọi khác fluent interface | Đối chiếu Java API cùng phiên bản Spring Data |
| Mã cũ dùng `consistentWith(QueryScanConsistency)` | API cũ hoặc chữ ký đã thay đổi | Ưu tiên `withConsistency` nếu version hỗ trợ; kiểm tra overload |
| Dùng Query object được chia sẻ, policy thay đổi | Mutable query state | Xây Query mới theo request |
| WebFlux bị block | Gọi `CouchbaseTemplate` thay Reactive Template | Chọn reactive API end-to-end |
| Vừa xóa session nhưng query còn thấy ID | Index lag, TTL/cache | Xác thực session theo key, trạng thái bảo mật |
| CAS conflict nhiều | Hot document/concurrent writes | Xử lý optimistic locking, xem lại aggregate |
| Tạo Order trùng sau timeout | Thiếu idempotency | Kiểm tra theo key và bảo vệ đường ghi |

**Không nuốt mọi exception thành danh sách rỗng.** Trả empty cho timeout/index error có thể làm domain nghĩ “không có đơn” hoặc “email chưa ai đăng ký”, gây quyết định sai. Cần phân biệt không có kết quả thật với lỗi kết nối/query.

## 19. Bài tập thực hành

### Bài tập A — Chính sách riêng cho hai endpoint

Hệ thống có:

- `GET /orders/report`: báo cáo cập nhật định kỳ, cho phép chậm vài giây.
- `GET /customers/{id}/orders` ngay sau `POST /orders`: bắt buộc có đơn vừa tạo nếu thuộc 20 đơn gần nhất.

**Yêu cầu:** Viết hai method gọi cùng `OrderQueryDao` với chính sách khác nhau.

*Hướng giải:* `NOT_BOUNDED` cho báo cáo; `REQUEST_PLUS` cho danh sách cần đủ mới. Đảm bảo query, index, sort và limit chính xác.

### Bài tập B — Query object

Một DAO tạo Query với `status = "CONFIRMED"`, limit 50.

**Yêu cầu:** Đặt `REQUEST_PLUS` tại **Query instance** chứ không phải trên fluent operation.

~~~java
Query q = Query.query(QueryCriteria.where("status").is("CONFIRMED"))
        .limit(50)
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS);

return template.findByQuery(OrderDocument.class)
        .matching(q)
        .all();
~~~

Giả định code nằm trong method có kiểu trả thích hợp và bean `template` đã inject.

### Bài tập C — Một Order đã có key

Service vừa lưu đơn, có `saved.getId()`. Nó dùng `findByQuery` theo `customerId` với REQUEST_PLUS chỉ để lấy lại đúng đơn.

**Hỏi:** Đường nào phù hợp hơn?

*Hướng giải:* Trả saved entity hoặc `template.findById(OrderDocument.class).one(saved.getId())`. Không cần chờ index để xem một document có key rõ.

### Bài tập D — Lost update

A và B cùng đọc Order ở trạng thái CREATED. A xác nhận, B cố cập nhật bản cũ. B bật REQUEST_PLUS ở một query Template.

**Hỏi:** REQUEST_PLUS có bảo vệ ghi đè không?

*Hướng giải:* Không. Dùng `@Version`/CAS hoặc conditional mutation ở đường ghi và xử lý conflict.

### Bài tập E — Reactive

Chuyển `listByCustomer(...)` sang WebFlux; một developer viết `Mono.just(blockingTemplate.findByQuery(...).all())`.

**Hỏi:** Có non-blocking chưa?

*Hướng giải:* Chưa, vì truy vấn blocking chạy trước khi Mono được tạo. Dùng `ReactiveCouchbaseTemplate` và trả `Flux` theo pipeline.

### Bài tập F — Kiểm thử độ mới

Nhóm viết test yêu cầu truy vấn NOT_BOUNDED phải thiếu Order mới trong ít nhất một lần.

**Hỏi:** Test đúng không?

*Hướng giải:* Không. Độ trễ index không deterministic. Kiểm chứng REQUEST_PLUS qua hành vi được hứa; đo index lag bằng metric riêng.

## 20. Câu hỏi tự kiểm tra

1. **`withConsistency(REQUEST_PLUS)` điều khiển điều gì?** Mốc freshness cần thiết cho scan index của một SQL++ query.
2. **Nó có giúp `findById` nhanh/mới hơn không?** Không phải cơ chế đó; `findById` là KV theo key.
3. **Khác biệt chính của NOT_BOUNDED?** Không chủ động đợi index đạt mốc mutation của request; có thể trả dữ liệu chưa mới.
4. **REQUEST_PLUS có thể làm tăng latency không?** Có, nếu phải đợi index.
5. **Cách khai báo trên Query object?** `query.scanConsistency(QueryScanConsistency.REQUEST_PLUS)`.
6. **Tại sao không chia sẻ Query mutable?** Các request có thể can thiệp lẫn nhau khi đổi sort/limit/consistency.
7. **`@ScanConsistency` của Repository có phải lựa chọn bắt buộc cho Template?** Không; fluent Template có thể chọn policy ngay trên lần query.
8. **Nếu REQUEST_PLUS không thấy Order, nên xem gì?** Keyspace, field/filter, type discriminator, sort/limit, index state, lỗi và mutation cạnh tranh.
9. **CAS khác scan consistency thế nào?** CAS kiểm tra concurrency của mutation; scan consistency yêu cầu độ mới của index cho query.
10. **Muốn consistency theo mutation token có phải dùng timestamp máy client?** Không; cần token/state do database/SDK cung cấp.
11. **Reactive Template có làm index cập nhật tức thì không?** Không; nó thay mô hình điều phối I/O.
12. **Một request vừa ghi xong có cần query lại qua index để hiển thị Order đã lưu?** Thường không; saved entity hoặc KV theo ID đủ cho mục đích đó.

## 21. Checklist triển khai

- [ ] Đã xác định use case nào cần **một document theo key**, use case nào thực sự cần SQL++?
- [ ] SQL++ index/filter/sort/projection đã được kiểm tra bằng `EXPLAIN`?
- [ ] Policy độ mới được chọn ở đúng **mỗi Query/operation**, không làm mọi endpoint chờ index ngoài ý muốn?
- [ ] Dùng `withConsistency(...)` **hoặc** `Query.scanConsistency(...)` rõ ràng, không tạo chính sách mâu thuẫn?
- [ ] Query instance được tạo mới theo request, Template bean được tái sử dụng?
- [ ] Đã phân biệt `NOT_BOUNDED`/`REQUEST_PLUS` và chấp nhận đánh đổi latency?
- [ ] `ORDER BY`, `LIMIT`/pagination và tenant filter đã đúng?
- [ ] Khai báo scope/collection khớp cluster và account được cấp quyền cần thiết?
- [ ] Có SLA về độ mới; đã đo p50/p95/p99 query dưới background mutation load?
- [ ] Đã kiểm soát timeout/retry, không coi lỗi query là danh sách rỗng?
- [ ] CAS, TTL, transaction, durability và idempotency được thiết kế riêng?
- [ ] Reactive path dùng Reactive Template nếu WebFlux cần non-blocking?
- [ ] Có integration test read-after-write, xác minh cấu hình qua trace khi cần?
- [ ] Không viết test đòi hỏi NOT_BOUNDED bắt buộc trả stale data?
- [ ] Có logging/tracing không lộ bí mật và metric Index/Query Service để điều tra khi hệ thống chậm?

## 22. Tài liệu kỹ thuật để đối chiếu phiên bản

Những API liên quan có thể được kiểm tra trong tài liệu chính thức Spring Data Couchbase; nên xem đúng dòng phiên bản dự án dùng:

- [Spring Data Couchbase — Template & direct operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html).
- [Couchbase `Query` API: `scanConsistency(QueryScanConsistency)`](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/query/Query.html).
- [Couchbase `QueryCriteria`: `where`, `is` và các điều kiện](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/query/QueryCriteria.html).
- [Fluent find-by-query `withConsistency(QueryScanConsistency)`](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/ExecutableFindByQueryOperation.FindByQueryWithConsistency.html).
- [Reactive find-by-query `withConsistency(QueryScanConsistency)`](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/ReactiveFindByQueryOperation.FindByQueryWithConsistency.html).

Tài liệu tham khảo là để kiểm tra **chữ ký API và cách sử dụng**, không thay thế kiểm thử trên bộ phiên bản Java, Spring Boot, Spring Data Couchbase, Couchbase Java SDK và Couchbase Server thực tế.

## 23. Kết luận

**CouchbaseTemplate cho phép chọn mức nhất quán tại từng truy vấn SQL++**: dùng `findByQuery(Entity.class).withConsistency(QueryScanConsistency.REQUEST_PLUS).matching(query).all()` khi query cần đợi index đạt mốc request; dùng `NOT_BOUNDED` khi SLO cho phép index lag và cần tránh chờ không cần thiết. Một cách tương đương ở lớp Query là `Query.scanConsistency(...)`; nên chọn một vị trí cấu hình rõ ràng cho mỗi lần gọi.

Trong tầng truy cập **Spring Data Couchbase**, lựa chọn đúng không chỉ nằm ở enum. Cần biết query đi KV hay index, đúng bucket/scope/collection, có secondary index phù hợp, query được giới hạn và bảo vệ quyền truy cập; đồng thời tách riêng CAS, TTL, transaction, durability, token-based consistency và reactive. Khi đặt policy theo use case và đo bằng integration test cùng metric thực tế, hệ thống có thể cân bằng **độ mới dữ liệu, độ trễ và khả năng vận hành**.
