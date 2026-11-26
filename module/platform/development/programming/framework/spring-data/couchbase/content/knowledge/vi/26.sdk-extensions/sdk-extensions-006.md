# Analytics: phân tích dữ liệu và phân biệt với truy vấn phục vụ giao dịch

Trong một ứng dụng **Spring Data Couchbase**, Repository và `CouchbaseTemplate` thường phục vụ những thao tác gần giao dịch: đọc document theo key, ghi entity, cập nhật bằng CAS, truy vấn SQL++ theo điều kiện nghiệp vụ và trả kết quả đủ nhanh cho màn hình hoặc API. Khi bài toán chuyển thành **phân tích hàng triệu đơn hàng, JOIN nhiều tập dữ liệu, nhóm theo thời gian, so sánh doanh thu giữa các phân khúc** hoặc chạy báo cáo ad hoc, tải xử lý có thể rất khác.

**Couchbase Analytics Service (CBAS)** là tầng phân tích được thiết kế cho các workload truy vấn lớn như vậy. Nó có bộ máy xử lý song song, có thể giữ **bản dữ liệu phân tích được đồng bộ** từ Data Service, rồi thực thi **SQL++ for Analytics** qua API riêng như `Cluster.analyticsQuery(...)` trong Couchbase Java SDK.

Sự khác biệt quan trọng nhất không phải tên method:

> **Analytics tối ưu cho đọc, nhóm, JOIN và tổng hợp dữ liệu quy mô lớn; đường KV/Query phục vụ giao dịch cần độ trễ và mức nhất quán phù hợp với thao tác hiện hành. Bản phân tích được đồng bộ gần thời gian thực, không mặc nhiên mới tuyệt đối ở từng thời điểm.**

Bài thuộc chương **Mở rộng bằng SDK** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase qua document mapping, Repository, `CouchbaseTemplate` và SQL++; hiểu bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để đạt hiệu năng, tính nhất quán và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **OLTP** (xử lý nghiệp vụ/giao dịch) và **OLAP** (phân tích dữ liệu).
2. Giải thích vai trò của Data Service, Query Service/GSI và Analytics Service.
3. Hiểu cách Analytics tạo/mapping **Analytics collections (datasets/shadow copies)** từ Data Service và duy trì thông qua ingestion.
4. Dùng SQL++ for Analytics cho `JOIN`, `GROUP BY`, `HAVING`, tổng hợp và kết quả không phải entity.
5. Gọi `Cluster.analyticsQuery(...)` hoặc `Scope.analyticsQuery(...)` bằng Java SDK, ánh xạ `AnalyticsResult` thành DTO.
6. Cấu hình named parameters, `readonly`, client context ID và `AnalyticsScanConsistency`.
7. Phân biệt `AnalyticsScanConsistency.NOT_BOUNDED` với `REQUEST_PLUS`; không suy ra có snapshot xuyên nhiều truy vấn.
8. Dùng `cluster.reactive().analyticsQuery(...)` để stream row, nhưng không cho rằng reactive biến một query nặng thành rẻ.
9. Chọn đúng công cụ cho dashboard, báo cáo xuất file, kiểm tra quota, tồn kho, thanh toán và API có SLA thấp.
10. Kiểm thử ingestion lag, dữ liệu thay đổi, quyền tenant, hiệu năng, lỗi và môi trường không có Analytics Service.

## 2. Ví dụ xuyên suốt: báo cáo doanh thu bán hàng

Giả sử dữ liệu vận hành nằm ở Couchbase:

~~~text
Bucket: shop
  |
  +-- Scope: sales
  |     +-- Collection: orders
  |     +-- Collection: refunds
  |
  +-- Scope: crm
        +-- Collection: customers
~~~

Document `orders`:

~~~json
{
  "tenantId": "tenant-01",
  "orderId": "ORD-1001",
  "customerId": "customer::42",
  "channel": "WEB",
  "status": "PAID",
  "totalCents": 245000,
  "createdAt": "2026-11-24T09:15:00.000Z"
}
~~~

Document `customers`:

~~~json
{
  "tenantId": "tenant-01",
  "segment": "LOYAL",
  "country": "VN",
  "registeredAt": "2025-02-10T10:00:00.000Z"
}
~~~

Khách hàng có hai loại màn hình:

- **Màn hình thanh toán:** cần xem đơn hiện tại có `PAID` chưa, sau đó kiểm tra điều kiện và cập nhật theo CAS/transaction nếu cần.
- **Bảng phân tích:** cần tính doanh thu theo ngày, kênh và nhóm khách hàng của 12 tháng, so sánh quý và xuất hàng trăm nghìn dòng.

Hai màn hình có thể đọc từ **cùng nguồn nghiệp vụ**, nhưng cần **đường thực thi khác nhau**. Không chuyển toàn bộ thao tác sang Analytics chỉ vì có câu `SELECT` hoặc `COUNT`.

## 3. OLTP và OLAP không chỉ khác số lượng row

| Tiêu chí | OLTP: nghiệp vụ/giao dịch | OLAP: phân tích |
| --- | --- | --- |
| Mục tiêu | Đọc, ghi, xác minh trạng thái, xử lý đơn | Tổng hợp xu hướng, số liệu, phân khúc |
| Đơn vị | Thường một/vài document, hoặc kết quả lọc nhỏ | Có thể hàng triệu document/nhóm |
| Tần suất | Nhiều request nhỏ, lặp thường xuyên | Ít query hơn nhưng mỗi query nặng hơn |
| Độ trễ | Thường cần thấp, ổn định | Có thể chấp nhận lâu hơn theo SLA báo cáo |
| Độ mới | Quan trọng với quyết định ghi/quyền/tiền | Có thể chấp nhận lag có công bố `asOf` |
| Chỉ mục | KV theo key; GSI cho predicate/ORDER BY | Analytics datasets/indexes riêng cho workload |
| Phép toán | CRUD, lookup, filtering, limited aggregation | Join/set/group/window/ad hoc analysis |
| Kết quả | Entity, projection hoặc DTO nhỏ | Aggregate DTO, số, bảng thống kê, stream lớn |
| Lỗi cần xử lý | CAS conflict, timeout, durability, transaction | Query dài, ingestion lag, memory/disk, timeout |
| Mô hình đồng thời | Nhiều request nhanh | Cần kiểm soát concurrency của query nặng |

**Không có ngưỡng thần kỳ** “trên 100.000 document thì phải dùng Analytics”. Query Service vẫn thực hiện aggregation/join trong một số tình huống tốt; Analytics phù hợp hơn khi **mức độ xử lý lớn, phức tạp hoặc tranh chấp tài nguyên với OLTP** có bằng chứng.

## 4. Ba đường đọc không được đánh đồng

~~~text
                  Application service
                         |
        +----------------+------------------+
        |                |                  |
   Repository/KV   Cluster.query(...)   Cluster.analyticsQuery(...)
        |                |                  |
   Data Service      Query Service       Analytics Service
        |                |                  |
  Active document    GSI / Index        Analytics collection
       state         Service            (shadowed dataset)
        |                |                  ^
        +----------------+                  |
             Source operational data  -- ingestion -->
~~~

Đường vận hành:

- `collection.get(id)`: KV theo document key trên Data Service, không cần secondary index.
- `cluster.query(sql)`: **SQL++ Query Service**, thường dựa trên GSI/Index Service cho predicate, sort, JOIN, aggregate.
- `cluster.analyticsQuery(sql)`: **SQL++ for Analytics**, sử dụng Analytics collections/datasets trên Analytics Service.

Tên `SQL++` xuất hiện ở cả Query và Analytics không làm hai ngữ pháp, kế hoạch hay chính sách consistency trở thành giống hệt nhau. Đừng chỉ đổi `query(...)` thành `analyticsQuery(...)` rồi coi toàn bộ SQL++ cũ tương thích.

## 5. Couchbase Analytics Service là gì?

Analytics Service là một bộ máy **massively parallel processing (MPP)** phục vụ phân tích dữ liệu, hỗ trợ đọc nhiều bản ghi, aggregation, JOIN và truy vấn ad hoc. Với Couchbase Server truyền thống, Analytics Service tạo các **shadow copies** của dữ liệu được lựa chọn để phân tích.

Điểm đáng chú ý:

1. Ứng dụng vẫn ghi document vận hành qua Data Service/Repository/KV.
2. Analytics collection được ánh xạ tới nguồn dữ liệu, và một **ingestion link** kết nối luồng dữ liệu.
3. Dữ liệu mới/sửa/xóa dần xuất hiện trong Analytics theo cơ chế ingestion.
4. Analytics chạy truy vấn trên dữ liệu phân tích đã tiếp nhận, nhằm tách tải đọc nặng khỏi đường vận hành.
5. Shadow copy **không nhất thiết phản ánh tức thời mọi mutation**.
6. Analytics nodes nên được triển khai và cấp tài nguyên phù hợp với workload riêng; không dùng chung một giả định về RAM/CPU như API KV nhỏ.

Cụm “near real-time” nghĩa là **độ trễ cập nhật thấp theo thiết kế**, không phải một cam kết mọi query thấy ngay mutation cuối cùng trong mọi điều kiện.

### Analytics Service khác Capella Analytics/Enterprise Analytics mới

Trong hệ sinh thái Couchbase, tên sản phẩm thay đổi theo thế hệ:

- **Couchbase Analytics Service (CBAS)** trong self-managed Couchbase Server/Capella Operational: được truy vấn bằng **operational Java SDK** thông qua `Cluster.analyticsQuery(...)`.
- **Capella Analytics** (trước đây gắn tên **Columnar**) và các sản phẩm Analytics độc lập/thế hệ mới: có **SDK/cách kết nối riêng** theo tài liệu sản phẩm.

Bài này **chủ yếu nói về CBAS của operational cluster**. Không tự áp dụng `cluster.analyticsQuery(...)` cho một endpoint Capella Analytics độc lập nếu sản phẩm đó yêu cầu Analytics SDK khác. Phải xác nhận edition, deployment và phiên bản trước khi chọn API. 

## 6. Analytics collection không phải KV Collection handle

Có thể có tên giống nhau:

~~~text
Data Service source:
  shop.sales.orders

Analytics shadow collection:
  shop.sales.orders  (trong cách mapping cùng tên)
~~~

Nhưng đây là **hai vai trò lưu trữ khác nhau**:

| Khái niệm | Tầng nào sở hữu? | Mục đích |
| --- | --- | --- |
| `com.couchbase.client.java.Collection` | Java SDK Data/KV | `get`, `insert`, `replace`, `mutateIn` theo key |
| Spring Data `@Collection("orders")` | Entity mapping | Chọn KV/SQL++ collection vận hành |
| Analytics collection/dataset | Analytics Service | Tập dữ liệu cho truy vấn phân tích |
| Analytics ingestion link | Analytics Service | Liên kết dữ liệu nguồn và tiến độ sao chép |
| SQL++ GSI index | Index Service | Phục vụ Query Service |
| Analytics index/structure | Analytics Service | Phục vụ query analytical theo khả năng phiên bản |

Gắn `@Collection("orders")` trên entity Spring Data **không tự bật Analytics ingestion**. Ngược lại, việc tạo Analytics collection không khiến `repository.save(...)` ghi trực tiếp vào bản shadow analytical.

## 7. Chuẩn bị Analytics Service và liên kết dữ liệu

Trước khi chạy ví dụ:

1. Kiểm tra deployment **có Analytics Service** và edition hỗ trợ.
2. Data collection `shop.sales.orders` đã tồn tại, có dữ liệu mẫu.
3. Tạo hoặc ánh xạ **Analytics collection** tương ứng.
4. Kết nối ingestion link từ Analytics tới Data Service.
5. Đợi initial ingestion đạt trạng thái chấp nhận được.
6. Cấp RBAC thích hợp cho user chạy Analytics query.
7. Xác minh query đơn giản có thể thấy các row mẫu.

Trong các phiên bản Couchbase Server hỗ trợ mapping theo cùng keyspace, một lệnh theo tài liệu là:

~~~sql
-- Chạy bằng Analytics Workbench/Analytics DDL,
-- không phải câu SQL++ dùng để cập nhật entity trong Repository.
ALTER COLLECTION `shop`.sales.orders ENABLE ANALYTICS;
~~~

Tương đương về mặt ý tưởng với việc tạo Analytics scope/collection từ nguồn tương ứng. Tùy phiên bản, cách quản trị có thể dùng **Map From Data Service**, `CREATE ANALYTICS COLLECTION`/`CREATE DATASET` và thao tác **CONNECT** link.

Không phải mọi hệ thống đều có thể chạy `ALTER COLLECTION ... ENABLE ANALYTICS` nếu metadata/link/edition chưa được chuẩn bị. Với ứng dụng production, quản lý DDL qua migration/operations riêng, không để controller tự tạo Analytics datasets khi HTTP request đầu tiên tới.

### DDL thay đổi theo phiên bản

Các tài liệu cũ có thể dùng thuật ngữ **Dataverse/Dataset**, trong khi tài liệu mới dùng **Analytics Scope/Collection**; tên `CREATE DATAVERSE`, `CREATE DATASET` có thể xuất hiện như cú pháp cũ/tương đương tùy Server.

Điều cần kiểm chứng là **dataset nào đang được query** và nó shadow **Data collection nào**, chứ không phải cố áp đặt một tên cú pháp cho mọi cluster.

## 8. Mô hình ingestion và độ mới dữ liệu

~~~text
T0  Data Service có 10.000 Order PAID.
T1  Analytics collection đã ingest 10.000 Order.
T2  Order mới chuyển sang PAID; KV mutation thành công.
T3  Analytics ingestion chưa bắt kịp.
T4  Analytics COUNT(PAID) có thể vẫn là 10.000.
T5  Ingestion bắt kịp.
T6  Analytics COUNT(PAID) trở thành 10.001.
~~~

Đây là mô hình khái niệm, không dự đoán độ trễ theo mili-giây.

Có nhiều nguyên nhân khiến báo cáo không “tức thời”:

- Ingestion backlog do mutation rate tăng.
- Rebalance/failover hoặc Analytics nodes quá tải.
- Link bị ngắt hoặc lỗi truy cập nguồn.
- Initial ingestion chưa hoàn tất.
- Query chạy trước khi dữ liệu liên quan được ingest.
- Filter/mapping của dataset cố ý loại một số document.
- Writer vừa sửa document khi query đang xử lý.

Không kết luận `COUNT` thấp hơn source là bug converter của Spring Data khi chưa kiểm tra ingestion status và dataset filter.

## 9. Query đầu tiên bằng `Cluster.analyticsQuery(...)`

Couchbase Java SDK 3.x hỗ trợ API:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.analytics.AnalyticsResult;
import com.couchbase.client.java.json.JsonObject;

public void runAnalyticsHello(Cluster cluster) {
    AnalyticsResult result = cluster.analyticsQuery(
            "SELECT 'hello analytics' AS greeting");

    for (JsonObject row : result.rowsAsObject()) {
        System.out.println(row.getString("greeting"));
    }

    System.out.println(
            result.metaData().metrics().executionTime());
}
~~~

Ví dụ không phụ thuộc dataset nên phù hợp để kiểm tra SDK và Analytics Service đã hoạt động.

`AnalyticsResult` gồm **rows và metadata**; nó không phải một `QueryResult` của SQL++ Query Service. Code không dùng `repository.findAll()` rồi tổng hợp trong JVM để “giả” Analytics.

**Đừng khởi tạo `Cluster.connect(...)` mỗi lần chạy báo cáo.** Tận dụng Spring-managed `Cluster` mà Repository/Template đã sử dụng, với environment/TLS/credentials và lifecycle thống nhất.

## 10. SQL++ for Analytics: truy vấn tổng hợp

Giả sử Analytics collection `shop.sales.orders` được mapping và đã connected. Báo cáo số lượng/doanh thu theo kênh:

~~~sql
SELECT o.channel AS channel,
       COUNT(*) AS orderCount,
       SUM(o.totalCents) AS revenueCents
FROM `shop`.sales.orders AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID"
GROUP BY o.channel
ORDER BY revenueCents DESC, channel ASC;
~~~

Kết quả ví dụ:

~~~json
[
  {
    "channel": "WEB",
    "orderCount": 8421,
    "revenueCents": 1925440000
  },
  {
    "channel": "APP",
    "orderCount": 6150,
    "revenueCents": 1099000000
  }
]
~~~

Các con số chỉ minh họa.

**Một row của Analytics GROUP BY đại diện một nhóm**. Nó không phải entity `Order` của Spring Data, không có một document ID/CAS chung cho mọi Order đóng góp vào nhóm.

Nên ánh xạ sang DTO/read model:

~~~java
public record ChannelRevenue(
        String channel,
        long orderCount,
        long revenueCents) {}
~~~

Không gọi `repository.save(new ChannelRevenue(...))`. Nếu muốn ghi thống kê vật hóa, phải thiết kế **document báo cáo riêng** và write pipeline có nguồn sự thật/độ nhất quán rõ.

## 11. Java SDK Analytics với named parameters

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.analytics.AnalyticsResult;
import com.couchbase.client.java.json.JsonObject;
import java.util.List;

import static com.couchbase.client.java.analytics.AnalyticsOptions.analyticsOptions;

public List<ChannelRevenue> revenueByChannel(
        Cluster cluster,
        String tenantId) {

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("tenantId required");
    }

    String sql = """
        SELECT o.channel AS channel,
               COUNT(*) AS orderCount,
               SUM(o.totalCents) AS revenueCents
        FROM `shop`.sales.orders AS o
        WHERE o.tenantId = $tenantId
          AND o.status = "PAID"
        GROUP BY o.channel
        ORDER BY revenueCents DESC, channel ASC
        """;

    JsonObject parameters = JsonObject.create()
            .put("tenantId", tenantId);

    AnalyticsResult result = cluster.analyticsQuery(
            sql,
            analyticsOptions()
                    .parameters(parameters)
                    .readonly(true));

    return result.rowsAsObject().stream()
            .map(row -> new ChannelRevenue(
                    row.getString("channel"),
                    row.getLong("orderCount"),
                    row.getLong("revenueCents")))
            .toList();
}
~~~

Điểm cần hiểu:

1. `analyticsOptions()` đến từ package `com.couchbase.client.java.analytics`.
2. `$tenantId` là **named parameter cho giá trị**; không nối input vào SQL++ thô.
3. `readonly(true)` làm rõ rằng đây là query đọc, giúp SDK/Server xử lý theo policy read-only.
4. `rowsAsObject()` hợp lý vì `SELECT ... AS ...` trả JSON object mỗi row.
5. Alias SQL++ và tên field DTO phải khớp.
6. `getLong(...)` giả định `COUNT/SUM` trả số trong miền Java `long` theo schema; tiền tệ/phép tính phân số cần kiểm tra kiểu và overflow.
7. Tên keyspace `shop.sales.orders` trong query là **Analytics collection**, đã map sẵn từ Data source.
8. Query có thể xử lý rất nhiều row nguồn dù chỉ trả hai nhóm kết quả.

**Hạn chế minh họa:** Service này chưa có giới hạn thời gian riêng, RBAC, metrics, kiểm tra warnings và memory-budget cho số nhóm lớn. Với production, cần bổ sung theo hợp đồng ứng dụng.

## 12. SQL++ for Analytics và SQL++ for Query không giống hệt

Hai ngôn ngữ có nền tảng SQL++ và nhiều cấu trúc chung: `SELECT`, `FROM`, `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, `JOIN` và subqueries.

Tuy nhiên, có khác biệt về:

- Tên và phạm vi dataset/collection.
- Cách diễn đạt một số phép JOIN, `META()`/key functions và tập functions.
- Quản lý data source/link và Analytics DDL.
- Indexes, optimizer, runtime và query plan.
- Request options, consistency, kết quả/metadata.
- Các khả năng mở rộng theo phiên bản.

Ví dụ `USE KEYS` của SQL++ Query có thể cần viết lại thành predicate trên document metadata trong Analytics theo bảng tương thích của Couchbase. **Không copy/paste một statement sản xuất từ `Cluster.query` sang `analyticsQuery` và coi là được bảo đảm chạy**.

### So sánh ví dụ

Query Service:

~~~java
cluster.query(
        "SELECT COUNT(1) AS n FROM `shop`.sales.orders");
~~~

Analytics Service:

~~~java
cluster.analyticsQuery(
        "SELECT COUNT(*) AS n FROM `shop`.sales.orders");
~~~

Hai đoạn có thể trông gần giống nhau, nhưng:

- Đường thứ nhất đọc qua Query/Index Service trên operational collection.
- Đường thứ hai đọc Analytics collection đã shadow.
- Data freshness, optimizer và SLA khác nhau.
- Không nên so hai kết quả bằng nhau tuyệt đối ngay sau mutation rồi kết luận một bên hỏng.

## 13. JOIN lớn là một lý do cân nhắc Analytics

Bài toán: doanh thu theo phân khúc khách hàng.

Ở Data Service, `orders.customerId` lưu document key của Customer, còn `customers` có field `segment`. Sau khi **cả hai source collections đã được mapping sang Analytics**, có thể thực hiện:

~~~sql
SELECT c.segment AS segment,
       COUNT(*) AS orderCount,
       SUM(o.totalCents) AS revenueCents
FROM `shop`.sales.orders AS o
JOIN `shop`.crm.customers AS c
  ON o.customerId = META(c).id
WHERE o.tenantId = $tenantId
  AND c.tenantId = $tenantId
  AND o.status = "PAID"
GROUP BY c.segment
ORDER BY revenueCents DESC, segment ASC;
~~~

Đây là **ví dụ minh họa ngôn ngữ Analytics**: cách tham chiếu metadata document ID và khả năng JOIN cần được kiểm tra trên phiên bản Server/dataset mapping thực tế. Trong một số dataset, bạn có thể chủ đích lưu `customerId` trong body JSON của cả hai phía để JOIN trên field bình thường thay vì dựa vào metadata key.

Với bài toán lớn, Analytics có kiến trúc phù hợp để xử lý JOIN/aggregation theo kiểu song song. Nhưng SQL++ Query Service cũng có JOIN và aggregate; trước khi chuyển, phải đo:

- Quy mô dữ liệu nguồn và độ chọn lọc predicate.
- Tổng số document phải scan.
- Cardinality của join key và nguy cơ nổ row.
- RAM, CPU và spill/temp disk.
- Latency/tài nguyên Query Service trong giờ cao điểm.
- SLA của báo cáo và độ trễ ingestion được phép.

### Cẩn thận với nhân bản hàng

Nếu một Order có nhiều line items và query `UNNEST o.items`, `COUNT(*)` sau UNNEST sẽ đếm **số dòng item**, không còn đếm đơn hàng. Tương tự, `SUM(o.totalCents)` sau UNNEST có thể cộng lại cùng giá trị đơn nhiều lần.

Analytics giúp xử lý dữ liệu nhiều, **không tự sửa sai đơn vị thống kê**.

## 14. `WHERE`, `GROUP BY`, `HAVING` trên dữ liệu phân tích

Ví dụ chỉ giữ các channel có ít nhất 100 đơn PAID:

~~~sql
SELECT o.channel AS channel,
       COUNT(*) AS orders,
       SUM(o.totalCents) AS revenueCents
FROM `shop`.sales.orders AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID"
GROUP BY o.channel
HAVING COUNT(*) >= 100
ORDER BY revenueCents DESC, channel ASC;
~~~

- `WHERE` lọc record **trước tổng hợp**.
- `GROUP BY` hình thành nhóm.
- `HAVING` lọc **nhóm đã tổng hợp**.
- `ORDER BY` sắp các row nhóm.
- `LIMIT/OFFSET` nếu có chỉ cắt **result rows**; không khiến server chỉ quét vài document nguồn.

Báo cáo tổng hợp có thể tốn CPU/RAM dù response JSON nhỏ. Vì vậy áp dụng `LIMIT 20` ở cuối không có nghĩa Analytics chỉ phải xử lý 20 orders.

## 15. `NULL`, `MISSING` và schema không đồng nhất

Couchbase lưu JSON nên `totalCents` hoặc `channel` có thể:

- Bị thiếu (`MISSING`).
- Có mặt với `null`.
- Có kiểu khác, ví dụ chuỗi `"145000"` thay vì number.
- Có định dạng tiền tệ khác.
- Được ghi theo một schema cũ.

Cần xác định trước:

- `COUNT(*)` đếm những row nào?
- `COUNT(o.totalCents)` bỏ qua những giá trị thiếu/null ra sao?
- `SUM` trên field sai kiểu nên coi là lỗi dữ liệu hay bị bỏ qua?
- `AVG` có mẫu số là số bản ghi hay số giá trị hợp lệ?
- Có gộp missing channel vào nhóm `UNKNOWN` không?
- Có phân biệt đơn khác currency hay chưa?

Ví dụ chỉ chấp nhận document có tổng tiền hợp lệ theo schema đã chuẩn hóa:

~~~sql
SELECT o.channel AS channel,
       COUNT(*) AS countOrders,
       SUM(o.totalCents) AS revenueCents
FROM `shop`.sales.orders AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID"
  AND IS_NUMBER(o.totalCents)
GROUP BY o.channel;
~~~

Ví dụ này **loại** những document có `totalCents` sai kiểu. Nếu sản phẩm cần thống kê “bao nhiêu đơn có dữ liệu lỗi”, viết báo cáo riêng cho ngoại lệ, không im lặng bỏ row rồi coi doanh thu đầy đủ.

Tiền tệ nên dùng đơn vị nhỏ nhất (cents/đồng theo chuẩn hệ thống), với kiểm tra phạm vi số và currency. Không trộn các loại tiền rồi `SUM` như thể cùng đơn vị.

## 16. AnalyticsScanConsistency: độ mới là một lựa chọn

Couchbase Java SDK cung cấp lựa chọn:

~~~java
import com.couchbase.client.java.analytics.AnalyticsScanConsistency;
import static com.couchbase.client.java.analytics.AnalyticsOptions.analyticsOptions;

var fastOptions = analyticsOptions()
        .scanConsistency(AnalyticsScanConsistency.NOT_BOUNDED);

var fresherOptions = analyticsOptions()
        .scanConsistency(AnalyticsScanConsistency.REQUEST_PLUS);
~~~

Theo tài liệu:

- `NOT_BOUNDED` (thường là mặc định): chạy trên trạng thái Analytics đang sẵn có, không chờ ingestion bắt kịp tất cả mutation mới.
- `REQUEST_PLUS`: yêu cầu Analytics cập nhật các dataset cần thiết với dữ liệu khả dụng từ Data Service tới mốc request theo semantics của dịch vụ trước khi query; có thể chờ và tăng latency.

**Không suy ra** `REQUEST_PLUS` là cơ chế “mọi báo cáo trong phiên làm việc có một snapshot chung”. Nó ràng buộc freshness cho **một query**, không biến hai query chạy cách nhau vài giây thành một transaction.

### Ví dụ yêu cầu kết quả mới hơn

~~~java
AnalyticsResult result = cluster.analyticsQuery(
        """
        SELECT COUNT(*) AS countOrders
        FROM `shop`.sales.orders AS o
        WHERE o.tenantId = $tenantId
          AND o.status = "PAID"
        """,
        analyticsOptions()
                .parameters(JsonObject.create()
                        .put("tenantId", tenantId))
                .scanConsistency(
                        AnalyticsScanConsistency.REQUEST_PLUS)
                .readonly(true));
~~~

Có thể chấp nhận latency cao hơn ở trang “Báo cáo vừa kết sổ”; trong khi dashboard tổng quan 5 phút một lần có thể chọn `NOT_BOUNDED` và hiển thị thời điểm tính.

## 17. Đừng nhầm Analytics consistency với Query consistency

Tên enum khác nhau:

~~~java
// SQL++ Query Service:
QueryScanConsistency.REQUEST_PLUS

// Analytics Service:
AnalyticsScanConsistency.REQUEST_PLUS
~~~

Và đường gọi khác nhau:

~~~java
// Truy vấn operational:
cluster.query(sql, queryOptions()
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS));

// Truy vấn analytical:
cluster.analyticsQuery(sql, analyticsOptions()
        .scanConsistency(AnalyticsScanConsistency.REQUEST_PLUS));
~~~

Mỗi option thuộc **một query engine/index pipeline khác**. Đặt `REQUEST_PLUS` cho SQL++ Query Service không làm Analytics ingestion tự bắt kịp; đặt `REQUEST_PLUS` cho Analytics cũng không đổi hành vi của Repository `findById(...)` hoặc KV get.

Không đánh đồng với:

- CAS/`@Version`: kiểm soát cạnh tranh trên một document.
- Durability: xác nhận mutation theo chính sách ghi.
- TTL: vòng đời của document nguồn.
- Search consistency: dữ liệu của Search index/FTS.
- Snapshot xuyên nhiều request: cần thiết kế phiên bản báo cáo hoặc xuất snapshot riêng.

## 18. Hai lần đọc Analytics không mặc nhiên là cùng snapshot

Giả sử dashboard gọi:

1. Query A tính tổng đơn `PAID` theo ngày.
2. Query B tính top khách hàng theo doanh thu.
3. Query C tính tổng số kênh bán.

Trong lúc đó, nhiều orders được tạo, cancel, refund hoặc TTL. Ba query có thể phản ánh các trạng thái khác nhau vì ingestion và thời điểm đọc.

Ngay cả khi cả ba dùng `REQUEST_PLUS`, **không có bảo đảm mặc định** các query cùng thấy dataset ở một mốc chung.

Nếu sản phẩm yêu cầu:

> Doanh thu tháng 10 sau khi đóng sổ phải không thay đổi, và mọi bảng trong báo cáo phải đối soát cùng một dataset.

thì cần thiết kế:

- Chốt kỳ và nguồn dữ liệu.
- Materialized report/snapshot với ID/version xác định.
- Lưu `asOf`, trạng thái job, provenance và checksum/đối soát.
- API đọc cùng một `reportVersion` cho mọi trang/tất cả bảng.
- Chính sách điều chỉnh số liệu sau chốt kỳ (restate) có lịch sử.

Analytics là công cụ xử lý query; nó không thay thế định nghĩa **độ đúng số liệu theo thời điểm**.

## 19. Kết quả Analytics thường là DTO, không phải entity

Một row:

~~~json
{
  "channel": "WEB",
  "orderCount": 8421,
  "revenueCents": 1925440000
}
~~~

không đại diện một `Order`. Nó không có:

- Một document ID nguồn duy nhất.
- CAS duy nhất cho tất cả documents đóng góp.
- Đầy đủ fields của entity.
- Ý nghĩa `save(...)` để sửa hàng nghìn Order.

Do đó, `ChannelRevenue` là **read model**. Đừng gắn `@Document`/`@Id` vào nó chỉ để phù hợp một API Repository.

Nếu cần lưu bảng tổng hợp cho truy vấn tiếp theo, thiết kế **report aggregate document** riêng với key theo tenant/kỳ/version và cơ chế writer nhất quán. Document tổng hợp vật hóa khác một row trả tạm thời từ SQL++ Analytics.

## 20. `AnalyticsResult` và metadata phục vụ quan sát

SDK cho phép:

~~~java
AnalyticsResult result =
        cluster.analyticsQuery(statement, analyticsOptions()
                .readonly(true));

for (JsonObject row : result.rowsAsObject()) {
    // Ánh xạ DTO hoặc xử lý stream/batch có kiểm soát.
    System.out.println(row);
}

var metadata = result.metaData();

System.out.println("requestId=" + metadata.requestId());
System.out.println("clientContextId=" + metadata.clientContextId());
System.out.println("status=" + metadata.status());
System.out.println("executionTime=" +
        metadata.metrics().executionTime());
System.out.println("warnings=" + metadata.warnings());
~~~

`AnalyticsMetaData` có thể chứa `requestId`, `clientContextId`, `status`, metrics, signature và warnings. Không chỉ kiểm tra “Java không ném exception” rồi bỏ qua mọi cảnh báo nếu báo cáo cần dữ liệu đầy đủ.

Khi ghi log:

- Ghi query class/name, clientContextId và elapsed/execution time.
- Không log PII/tenant secret/SQL++ parameters nhạy cảm tùy tiện.
- Thêm correlation ID chung với HTTP request/job.
- Có giới hạn kích thước log kết quả; không in cả triệu rows.
- Gửi metrics đến dashboard cho latency, errors, lag và resource.

## 21. Named parameters và query security

SDK hỗ trợ:

~~~java
AnalyticsResult result = cluster.analyticsQuery(
        """
        SELECT o.channel AS channel, COUNT(*) AS n
        FROM `shop`.sales.orders AS o
        WHERE o.tenantId = $tenantId
          AND o.createdAt >= $fromDate
        GROUP BY o.channel
        """,
        analyticsOptions()
                .parameters(JsonObject.create()
                        .put("tenantId", authenticatedTenant)
                        .put("fromDate", fromDateIso)));
~~~

Giả định `authenticatedTenant` được lấy từ **security context** đã xác thực; `fromDateIso` là chuỗi ngày định dạng nhất quán và đã validate.

Named parameters dùng cho **giá trị**, không phải cách hợp lệ để truyền tên collection, field sort hay một đoạn SQL++ tùy ý.

Không làm:

~~~java
String sql = "SELECT * FROM " + userSuppliedDataset;
~~~

trừ khi dataset được chọn từ allowlist nội bộ chặt chẽ và câu SQL++ được xây có kiểm soát.

Các report SQL++ đa tenant phải có predicate quyền ở **mọi nguồn** (đặc biệt hai phía JOIN), không chỉ dựa vào việc user SDK có quyền đọc dataset chung.

## 22. Định tuyến scope và dataset qua SDK

Nếu Analytics collection map cùng convention với Data Service:

~~~text
shop.sales.orders
~~~

có thể query từ cấp `Cluster`:

~~~java
AnalyticsResult result = cluster.analyticsQuery(
        "SELECT COUNT(*) AS n FROM `shop`.sales.orders");
~~~

Hoặc từ `Scope` có query context phù hợp:

~~~java
import com.couchbase.client.java.Scope;

Scope analyticsScope = cluster.bucket("shop").scope("sales");

AnalyticsResult result = analyticsScope.analyticsQuery(
        "SELECT COUNT(*) AS n FROM `orders`");
~~~

**Điều kiện:** Analytics dataset/scope phải được map/đặt tên tương ứng và đã được kết nối. `Scope.analyticsQuery` không tự tạo Analytics collection từ `shop.sales.orders`.

Khi tổ chức một Analytics dataset có tên khác với source, cần sử dụng **đúng tên Analytics dataset**, không lấy annotation Spring Data `@Collection` làm nguồn mặc định.

## 23. Reactive Analytics cho báo cáo có nhiều row

SDK có đường reactive:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.analytics.ReactiveAnalyticsResult;
import com.couchbase.client.java.json.JsonObject;
import reactor.core.publisher.Flux;

import static com.couchbase.client.java.analytics.AnalyticsOptions.analyticsOptions;

public Flux<ChannelRevenue> streamRevenue(
        Cluster cluster,
        String tenantId) {

    String statement = """
        SELECT o.channel AS channel,
               COUNT(*) AS orderCount,
               SUM(o.totalCents) AS revenueCents
        FROM `shop`.sales.orders AS o
        WHERE o.tenantId = $tenantId
          AND o.status = "PAID"
        GROUP BY o.channel
        ORDER BY revenueCents DESC, channel ASC
        """;

    return cluster.reactive().analyticsQuery(
            statement,
            analyticsOptions()
                    .parameters(JsonObject.create()
                            .put("tenantId", tenantId))
                    .readonly(true))
        .flatMapMany(ReactiveAnalyticsResult::rowsAsObject)
        .map(row -> new ChannelRevenue(
                row.getString("channel"),
                row.getLong("orderCount"),
                row.getLong("revenueCents")));
}
~~~

Đây là ví dụ trong **custom SDK adapter**. `Cluster` được Spring inject, không tạo lại kết nối cho mỗi báo cáo.

Reactive giúp:

- Trả `Flux<ChannelRevenue>` theo các row nhận được.
- Đưa backpressure từ downstream tới đường streaming kết quả theo semantics SDK/Reactor.
- Kết hợp cancellation, timeout và error handling trong pipeline.
- Không cần giữ toàn bộ hàng kết quả trong một `List` nếu consumer có thể xử lý từng row.

**Reactive không làm phép JOIN/aggregation server rẻ hơn**. Một query nặng vẫn phải xử lý dữ liệu lớn ở Analytics Service. Không để người dùng mở hàng nghìn subscriptions phân tích không giới hạn chỉ vì ứng dụng dùng WebFlux.

### Không dùng blocking trong event-loop

~~~java
// Sai hướng trong WebFlux:
AnalyticsResult blocking = cluster.analyticsQuery(statement);
return Mono.just(blocking);
~~~

Lời gọi `cluster.analyticsQuery` đã block trước khi `Mono.just` được tạo. Dùng `cluster.reactive().analyticsQuery(...)` hoặc đường async phù hợp.

## 24. Cẩn thận với `collectList()` và result lớn

Một API nhỏ có thể gom dữ liệu:

~~~java
Mono<List<ChannelRevenue>> smallReport =
        streamRevenue(cluster, tenantId)
                .take(100)
                .collectList();
~~~

Nhưng `take(100)` ở Reactor **không bảo đảm** Analytics Service chỉ xử lý 100 nhóm/row nguồn. Nếu giới hạn kết quả là chính sách endpoint, nên thêm `LIMIT 100` vào SQL++ Analytics query và tối ưu dataset/query plan.

Một báo cáo xuất 10 triệu rows không nên `collectList()` rồi chuyển toàn bộ sang JSON response. Các hướng:

1. Trả stream có phân trang/batch và giới hạn concurrent requests.
2. Xuất ra file/job artifact ngoài đường HTTP đồng bộ nếu cần.
3. Ghi checkpoint/progress và dùng idempotent job semantics.
4. Quản lý cancellation và timeout phù hợp.
5. Không giữ quá nhiều row/đối tượng trong heap.
6. Phân biệt số rows output với lượng dữ liệu nguồn Analytics phải xử lý.

Chỉ dùng `collectList()` sau khi bạn biết row stream **đã được giới hạn tại query hoặc theo một batch có kiểm soát**.

## 25. Phân trang báo cáo Analytics

Đối với bảng top doanh thu theo kênh, có thể phân trang **row nhóm**:

~~~sql
SELECT o.channel AS channel,
       COUNT(*) AS orderCount,
       SUM(o.totalCents) AS revenueCents
FROM `shop`.sales.orders AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID"
GROUP BY o.channel
ORDER BY revenueCents DESC, channel ASC
LIMIT $limit OFFSET $offset;
~~~

Cần nhớ:

- `LIMIT 20` trả tối đa 20 **nhóm** chứ không chỉ tổng hợp 20 Order.
- `OFFSET` trang sâu vẫn có thể tốn công.
- `ORDER BY` phải có khóa phụ đủ phân xử nếu cần thứ tự xác định trong một dataset tĩnh.
- `revenueCents` thay đổi khi dữ liệu mới được ingest, khiến vị trí nhóm đổi giữa request.
- Tổng nhóm để dựng `Page` phải đếm **số nhóm** sau `GROUP BY/HAVING`, không đếm số orders nguồn.
- Data query và group-count query riêng không tự có snapshot chung.

Nếu UI chỉ cần “Tải thêm”, query `LIMIT size+1` và tính `hasNext` từ row dư, nhưng **không tăng `PageRequest` size vô tội vạ khiến OFFSET đổi**.

Với xuất báo cáo cần kết quả cố định, chọn `reportVersion`/snapshot materialization thay vì trông chờ offset/keyset qua một dataset đang ingestion liên tục.

## 26. Analytics không dùng để xác nhận thanh toán

Đặt một tình huống:

~~~text
T0    Order chưa PAID.
T1    Payment callback xác nhận thanh toán, Order chuyển PAID.
T2    Analytics ingestion chưa nhận mutation mới.
T3    Checkout service dùng analyticsQuery để kiểm tra Order.
T4    Analytics báo chưa PAID -> dịch vụ quyết định sai.
~~~

Không dùng Analytics như nguồn duy nhất cho:

- Kiểm tra trạng thái thanh toán vừa cập nhật.
- Phê duyệt hạn mức, trừ tồn kho, xác minh quota.
- Kiểm tra thu hồi quyền, khóa tài khoản hoặc xóa token.
- Đọc để thực hiện compare-and-swap.
- Ghi transaction trên operational entities.
- Cấp ID/sequence cần nguyên tử theo key.
- Xử lý command yêu cầu read-your-writes mạnh và latency thấp.

Các luồng này thường cần **KV active read, Repository/Template, CAS, hoặc transaction** với invariants rõ.

Analytics có thể phục vụ **báo cáo lịch sử thanh toán**, xu hướng theo nhóm, phát hiện bất thường ở mức dashboard sau khi data pipeline hội tụ—không thay cơ chế thanh toán hay sổ cái.

## 27. Ingestion lag: một chỉ số phải đo, không đoán

Một báo cáo có thể chậm vì:

- Analytics input chưa tiếp nhận hết mutation.
- Query server xử lý nhóm/join lớn.
- Network hoặc payload của result rows.
- Concurrency của nhiều báo cáo.
- Không đủ CPU/RAM/disk hoặc temporary space.
- Link disconnected, lỗi RBAC hoặc tiến trình ingest bị gián đoạn.

Để tìm nguyên nhân, theo dõi riêng:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Ingestion backlog/pending mutations | Analytics shadow còn chậm so với nguồn bao nhiêu |
| Lag quan sát qua sample revision/timestamp | Bản phân tích có mới đến mức nào |
| Analytics query p50/p95/p99 | Độ trễ truy vấn ở client |
| Execution time của `AnalyticsMetaData` | Thời gian server xử lý do Analytics báo |
| Query errors/warnings/timeouts | Độ tin cậy của kết quả |
| Processed objects/rows output | Query có quét quá nhiều không |
| CPU, memory, disk temp | Nút thắt resource |
| Active request count/concurrency | Có quá nhiều query nặng chạy song song không |
| Tenant query volume | Có user/report gây tải bất thường không |
| Data freshness SLA breaches | Bao nhiêu report vượt mức lag cho phép |

Couchbase Server có API/trang giám sát ingestion status. Khi deploy Analytics Service, cần quan sát cả ingestion và query runtime chứ không chỉ latency HTTP.

## 28. Timeout và giới hạn concurrency

Vì Analytics query có thể chạy lâu, đặt ngân sách tài nguyên rõ:

1. Giới hạn số báo cáo được chạy song song theo tenant/user.
2. Cấu hình timeout SDK/server phù hợp loại query.
3. Không sử dụng một timeout duy nhất cho KV get nhỏ và phân tích nhiều triệu documents.
4. Khi query dài, ưu tiên **job bất đồng bộ** hơn giữ HTTP connection vô hạn.
5. Tránh retry vô hạn nếu Analytics node đang quá tải.
6. Dùng `clientContextId` để truy dấu/đối chiếu query.
7. Không chạy DDL hoặc thay đổi Analytics links từ request nghiệp vụ.
8. Thiết lập RBAC tách quyền query và quyền quản trị.
9. Có cơ chế cancellation/cleanup khi người dùng hủy report.
10. Với trường hợp kết quả lớn, stream hoặc batch thay vì gom toàn bộ heap.

### Một ví dụ đặt client context ID

~~~java
import java.util.UUID;

AnalyticsResult result = cluster.analyticsQuery(
        statement,
        analyticsOptions()
                .readonly(true)
                .clientContextId("channel-report-" + UUID.randomUUID()));
~~~

Đừng đưa số tài khoản, mật khẩu hoặc PII vào ID giám sát; dùng mã định danh ngẫu nhiên/correlation ID đã được chuẩn hóa.

## 29. Priority và readonly không phải giải pháp thần kỳ

SDK có lựa chọn:

~~~java
var options = analyticsOptions()
        .readonly(true)
        .priority(false);
~~~

- `readonly(true)` cho phép đánh dấu câu query không thay đổi dữ liệu; phù hợp báo cáo đọc và giúp retry policy của SDK an toàn hơn trong một số trường hợp.
- `priority(true)` có thể yêu cầu ưu tiên dispatch của Analytics Service; không tự tăng CPU/RAM của cluster.
- Đặt mọi query là high priority có thể làm mất ý nghĩa ưu tiên và tăng tranh chấp.
- Không dùng `readonly(true)` để thay thế **RBAC** và kiểm tra câu query; vẫn cần quyền phù hợp và code review.
- Tùy chọn `raw(...)` là escape hatch của SDK; chỉ dùng khi biết tham số Server hỗ trợ và đã kiểm thử phiên bản.

Một query đọc dài cần throttling/admission control chứ không chỉ set priority.

## 30. Tại sao không dùng Analytics cho tất cả report?

SQL++ Query Service vẫn có thể phù hợp khi:

- Dữ liệu ít, query chọn lọc cao nhờ GSI.
- API cần đồng bộ gần hơn với một mutation vừa hoàn tất.
- Số lượng row thấp và SLA nghiêm ngặt.
- Report chỉ đọc vài document theo key/predicate đơn giản.
- Cluster chưa triển khai Analytics Service hoặc chi phí vận hành chưa xứng đáng.
- Query ít dùng và chi phí duy trì Analytics dataset/index cao hơn lợi ích.

Ngược lại, Analytics phù hợp hơn khi có:

- JOIN lớn và nhiều nguồn.
- Tổng hợp lịch sử nhiều tháng/năm.
- Ad hoc phân tích, bảng quản trị với nhiều chiều/nhóm.
- Dữ liệu operational không muốn bị cạnh tranh Query Service trong giờ cao điểm.
- Khả năng chấp nhận gần thời gian thực thay vì quyết định tức thời.
- Đội vận hành có thể cấp tài nguyên Analytics và theo dõi ingestion riêng.

**Tăng số lượng document chưa đủ để kết luận.** Phải so hiệu năng, index, chi phí vận hành, correctness và freshness trên workload đại diện.

## 31. Chiến lược kiến trúc: tách command, query và analytics

~~~text
Client command (thanh toán / đặt hàng)
         |
    Application service
         |
 Repository / Template / KV + CAS / Transaction
         |
    Data Service (source of truth)
         |
        ingestion
         |
    Analytics Service
         |
 AnalyticsReportPort / SDK adapter
         |
    Dashboard / Export job
~~~

Ví dụ domain ports:

~~~java
public interface OrderCommandPort {
    void markPaid(String orderId, String paymentId);
}

public interface SalesAnalyticsPort {
    List<ChannelRevenue> revenueByChannel(
            String tenantId,
            String fromIso,
            String toIso);
}
~~~

SDK adapter chỉ triển khai phần phân tích. Controller/command service không trực tiếp gọi `analyticsQuery(...)` để kiểm tra điều kiện thay đổi entity.

Ưu điểm:

- Hợp đồng consistency rõ cho từng use case.
- Tách timeout và giới hạn concurrency.
- Có thể chuyển đổi Analytics backend độc lập với entity CRUD.
- Dễ mock `SalesAnalyticsPort` trong unit test.
- Integration tests tập trung vào Analytics ingestion/query.
- Không truyền raw `Cluster`/`AnalyticsResult` khắp domain.

## 32. Spring-managed Cluster và vòng đời

Một adapter Spring dùng chung `Cluster`:

~~~java
import com.couchbase.client.java.Cluster;
import org.springframework.stereotype.Component;

@Component
public final class CouchbaseSalesAnalyticsAdapter {

    private final Cluster cluster;

    public CouchbaseSalesAnalyticsAdapter(Cluster cluster) {
        this.cluster = cluster;
    }

    // Có thể gọi cluster.analyticsQuery(...) tại đây.
}
~~~

Quy tắc:

- `Cluster` do Spring Boot/Spring Data hoặc custom configuration tập trung quản lý.
- Không `Cluster.connect(...)` cho từng report.
- Không gọi `cluster.disconnect()` trong adapter; Spring sở hữu lifecycle.
- Spring-managed Cluster có thể phục vụ KV, SQL++ và Analytics qua các API tương ứng nếu deployment hỗ trợ.
- Cùng Cluster không đồng nghĩa mọi thao tác cùng consistency hay cùng snapshot.
- Nếu có nhiều clusters, định tuyến qua bean `@Qualifier` và hợp đồng dữ liệu rõ.
- Không tự giả định Analytics có trên mọi edition/môi trường chỉ vì KV/Repository kết nối thành công.

## 33. Multi-tenancy, RBAC và dữ liệu nhạy cảm

Analytics datasets có thể tập trung dữ liệu của nhiều tenant và nhiều năm lịch sử. Một câu query aggregation có thể **làm lộ số liệu** ngay cả khi không trả từng document.

Các nguyên tắc:

1. Tenant lấy từ principal/context đã xác thực.
2. Lọc `tenantId` trong mọi dataset tham gia JOIN.
3. Không cho user tự chọn dataset/link/schema/field ngoài allowlist.
4. Giới hạn những metric và dimensions được công khai.
5. Query theo đúng RBAC Analytics service và dataset; tách quyền **query** khỏi quyền **quản trị DDL/links**.
6. Giảm thiểu PII được sao chép vào Analytics nếu không cần thiết.
7. Quản lý lifecycle/xóa dữ liệu đáp ứng chính sách retention và quyền yêu cầu xóa.
8. Không tin tên report “total” đồng nghĩa được phép trả tổng toàn hệ thống.
9. Bảo vệ tài liệu export chứa dữ liệu nhạy cảm, có TTL và quyền download.
10. Không đưa SQL++ params hoặc toàn bộ result rows vào logs/traces.

**Quan trọng:** SQL++ named parameters giảm rủi ro query injection cho **giá trị**, nhưng **không thay thế authorization**.

## 34. Schema evolution, TTL và dữ liệu thiếu

Dữ liệu Analytics là bản phản chiếu được duy trì từ nguồn, nhưng:

- Một field có thể đổi tên do migration Spring Data `@Field`.
- JSON docs cũ có thể thiếu `channel` hoặc `totalCents`.
- TTL/xóa document nguồn được phản ánh theo ingestion, có thể chậm.
- Dataset filter có thể chỉ ingest một tập con nguồn.
- Link disconnected có thể khiến dữ liệu phân tích không mới.
- DDL/index/reindex có thể làm báo cáo tạm thời gián đoạn.
- Một version của report có thể dùng schema khác version sau.

Ví dụ nếu entity dùng `@Field("total_cents")`, Analytics query phải tham chiếu **field JSON thực tế** `o.total_cents` chứ không tự áp dụng converter của Spring Data cho property `totalCents`.

Không dùng DTO kết quả Analytics để `repository.save(...)` làm partial entity. Nếu cần cập nhật entity, đọc đường KV/Repository hiện hành và giữ CAS/`@Version` đúng.

## 35. Kiểm thử tích hợp: mapping và ingestion

Test cần chạy trên môi trường có **Analytics Service thật**, không chỉ mock `Cluster`.

### A. Setup

1. Tạo bucket/scope/collection nguồn test ở môi trường cô lập.
2. Seed 10 orders với tenant/status/channel khác nhau.
3. Map hoặc enable Analytics collection cho source.
4. Connect ingestion link.
5. Chờ initial ingestion đủ để test.
6. Chạy `analyticsQuery("SELECT COUNT(*) ...")` và xác minh các row.
7. Đừng test bằng cách ngủ cố định 100 ms rồi khẳng định ingestion hoàn tất; dùng polling có deadline hoặc consistency phù hợp.

### B. Freshness

~~~text
Given Analytics đã ingest 10 orders
When  KV insert order thứ 11
And   gọi Analytics NOT_BOUNDED
Then  kết quả có thể chưa phản ánh order mới

When  Analytics REQUEST_PLUS được thực hiện thành công
Then  kết quả query được đánh giá theo semantics consistency
      tại mốc request (không phải snapshot vĩnh viễn)
~~~

Không assert `NOT_BOUNDED` **luôn** stale; ingestion có thể rất nhanh. Test nên quan sát khả năng stale và kiểm tra hợp đồng, không ép timing xác suất.

### C. Delete/TTL và schema

- Xóa một order; kiểm tra kết quả phân tích cuối cùng phản ánh việc xóa sau ingestion.
- Nếu TTL được bật, theo dõi thay đổi của count sau khi source hết hạn.
- Ghi order thiếu `channel`, `totalCents` hoặc sai kiểu; xác minh query không lặng lẽ đếm sai.
- Thử dữ liệu nhiều currency và các format createdAt khác nhau.
- Thử dataset filter để biết số row Analytics không nhất thiết bằng toàn source.

## 36. Kiểm thử đúng số liệu và tính nhất quán

Ví dụ dữ liệu đứng yên:

| Channel | Số Order PAID | Tổng cents |
| --- | ---: | ---: |
| WEB | 5 | 5000 |
| APP | 3 | 3600 |
| STORE | 1 | 700 |

Kỳ vọng Analytics `GROUP BY channel` trả 3 nhóm, `COUNT(*)` toàn bộ PAID là **9**, `SUM(totalCents)` là **9300**.

Test:

1. `GROUP BY` trả đúng 3 groups.
2. `WHERE tenantId` không tính tenant khác.
3. `HAVING COUNT(*) >= 3` chỉ giữ WEB/APP.
4. `COUNT(*)` sau UNNEST không được nhầm với số Order.
5. Tổng tiền không trộn currency/sai kiểu.
6. Query `totalGroups` phải đếm nhóm, không count source documents.
7. Thứ tự kết quả có `ORDER BY` và khóa phụ phù hợp.
8. Query khác nhau trong lúc mutation có thể trả số khác; không gắn nhãn “snapshot” sai.
9. Một report version đã chốt phải giữ nhất quán qua mọi trang/bảng bằng cơ chế ngoài Analytics query.

## 37. Kiểm thử tải, lỗi và vận hành

Các ca cần có:

- Analytics Service không được deploy → SDK query lỗi rõ, API báo dependency unavailable hoặc cơ chế fallback **đã thiết kế**, không tự chạy query nặng trên Query Service.
- Ingestion link disconnected → report báo trạng thái dữ liệu cũ/lag; không coi giá trị cũ là chính xác tức thời.
- Analytics query timeout → map lỗi, không trả report rỗng hợp lệ.
- Thiếu RBAC Analytics → từ chối; không tự fallback sang credential quyền cao.
- Query có JOIN lớn / nhiều group → đo CPU/RAM/temp disk.
- Truy vấn `NOT_BOUNDED` vs `REQUEST_PLUS` → đo latency và mức dữ liệu hội tụ.
- Reactive streaming triệu row → kiểm tra memory, backpressure và cancellation.
- Giới hạn số query đồng thời theo user/tenant.
- Query với tên field/data source sai → parsing/planning error rõ.
- Cleanup test data không xóa nhầm production.

### Benchmark tối thiểu

So cùng workload với `Cluster.query(...)` (Query Service) và `Cluster.analyticsQuery(...)` sau khi Analytics đã ingest:

| Tiêu chí | Cần đo |
| --- | --- |
| p50/p95 latency | Trải nghiệm thực tế |
| Total execution time | Metadata engine |
| Số documents/rows xử lý | Khối lượng công việc |
| CPU/RAM/temp disk | Chi phí máy chủ |
| Index/ingestion cost | Công việc duy trì dữ liệu |
| Freshness lag | Sai lệch so với nguồn khi mutation |
| Data correctness | Nhóm/tổng/kiểu số đúng |
| Concurrency | Ảnh hưởng lên OLTP |
| Network/payload | Tải client và kết quả |
| Operational effort | Cấu hình link, RBAC, backup/restore và deploy |

Không kết luận Analytics “nhanh hơn Query” cho mọi câu SQL++: một truy vấn chọn lọc 10 documents có GSI tốt có thể rất nhanh ở Query Service.

## 38. Những hiểu nhầm cần tránh

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Analytics chỉ là `Cluster.query` với tên mới” | Là engine, dataset và SDK API khác |
| “Có @Document là tự có Analytics dataset” | Phải map/create/connect Analytics collection |
| “Analytics luôn thấy mutation mới nhất” | Ingestion có thể lag |
| “`REQUEST_PLUS` làm mọi request cùng snapshot” | Giới hạn cho một query theo semantics Server |
| “Dùng Analytics để xác minh thanh toán” | Không phù hợp nếu nghiệp vụ đòi trạng thái hiện hành |
| “SQL++ Query statement nào cũng chạy nguyên trong Analytics” | Có khác biệt cú pháp/khả năng và metadata |
| “Analytics GROUP BY 20 nhóm chỉ đọc 20 documents” | Phải xử lý nguồn phù hợp để tính group |
| “Kết quả Analytics là entity Order” | Thường là row tổng hợp/DTO |
| “Dùng `getLong` luôn an toàn cho SUM tiền” | Cần kiểm tra schema, range, currency |
| “Reactive sẽ giảm chi phí query server” | Chỉ thay mô hình client/streaming |
| “Cùng Cluster = cùng transaction” | Transaction context và phạm vi riêng |
| “Đã có report total, không cần bảo mật tenant” | Aggregate có thể rò rỉ số liệu |
| “DDL dataset có thể chạy mỗi request” | Phải quản trị qua deployment/migration |
| “Bật REQUEST_PLUS không thêm latency” | Có thể chờ ingestion, timeout |
| “Báo cáo cuối tháng tự bất biến” | Cần report snapshot/version và chính sách restatement |

## 39. Ma trận lựa chọn cho ứng dụng Spring Data Couchbase

| Nhu cầu | Đường truy cập ưu tiên | Lý do |
| --- | --- | --- |
| Đọc một Customer bằng ID | Repository/Template/KV | Tìm theo key, dữ liệu hiện hành |
| Cập nhật Order theo CAS | Repository `@Version` hoặc SDK conditional KV | Cần optimistic locking |
| Kiểm tra quota/tồn kho | CAS/transaction/conditional model | Invariant không phụ thuộc stale analysis |
| Lấy 20 Order mới nhất của tenant | SQL++ Query/GSI | Query chọn lọc, giới hạn thấp |
| Search tên sản phẩm tiếng Việt | Search Service/FTS | Analyzer, relevance, highlight |
| Báo cáo doanh thu 12 tháng | Analytics ứng viên tốt | Aggregation lớn, tách tải OLTP |
| JOIN Order + Customer hàng triệu row | Analytics ứng viên tốt | MPP/analytical JOIN |
| Dashboard tổng hợp mỗi 5 phút | Analytics/materialized aggregate | Chấp nhận lag có `asOf` |
| Đếm số đơn PAID chính xác tức thì trước quyết định | Nguồn vận hành/Query/KV theo invariant | Không dựa vào ingest lag |
| Xuất báo cáo đóng sổ | Analytics + snapshot/version workflow | Giữ một phiên bản báo cáo cố định |
| Analytics Service không có trong môi trường | Query Service hoặc pipeline khác sau benchmark | Không tự giả định có CBAS |
| Báo cáo realtime nhiều nguồn bên ngoài | Kiểm tra Capella Analytics/giải pháp khác | Có thể cần SDK và kiến trúc riêng |

## 40. Bài tập thực hành

**A. Dựng nguồn và Analytics dataset**

1. Tạo `shop.sales.orders` trong môi trường phát triển.
2. Seed ít nhất 30 Order với các tenant/channel/status.
3. Bật Analytics Service trên deployment phù hợp.
4. Map Analytics collection từ Data Service và connect link.
5. Dùng Analytics Workbench chạy `SELECT COUNT(*)` trên dataset.
6. Ghi lại thời gian initial ingest và thông tin status.

**B. Viết Spring SDK adapter**

1. Inject Spring-managed `Cluster`.
2. Dùng `cluster.analyticsQuery(...)` với named parameters.
3. Trả `List<ChannelRevenue>` hoặc `Flux<ChannelRevenue>`.
4. Đặt `readonly(true)` và clientContextId phù hợp.
5. Chỉ trả dữ liệu tenant từ context xác thực.
6. Đọc metadata execution time và warnings.
7. Không đóng Cluster trong method.
8. Không map row GROUP BY thành entity `Order`.

**C. So sánh với Query Service**

1. Viết query tương đương bằng `Cluster.query(...)` với index GSI phù hợp.
2. Đo latency, CPU và result correctness.
3. Chèn thêm Order PAID rồi gọi cả hai query ngay.
4. Thử `NOT_BOUNDED`/`REQUEST_PLUS` ở đúng API từng service.
5. Ghi nhận ingestion lag khác gì GSI index lag.
6. Phân tích khi nào Query Service phù hợp hơn Analytics.

**D. Mở rộng**

1. Map `shop.crm.customers` vào Analytics.
2. JOIN Order với Customer, nhóm theo `segment`.
3. Thử schema thiếu field, nhiều currency và UNNEST item lines.
4. Chạy query analytical nhiều row bằng Reactive SDK và stream có kiểm soát.
5. Mô phỏng link disconnected, timeout và RBAC error.
6. Đề xuất `reportVersion`/`asOf` và chiến lược snapshot cho báo cáo đã đóng sổ.

### Câu hỏi tự kiểm tra

1. OLTP và OLAP khác nhau ở mục tiêu, độ trễ và độ mới thế nào?
2. `Cluster.query` và `Cluster.analyticsQuery` đi qua dịch vụ nào?
3. Analytics collection/shadow copy có phải cùng document KV active không?
4. Có `@Collection` của Spring Data thì Analytics tự ingest không?
5. Vì sao “near real-time” chưa phải “latest state”?
6. `AnalyticsScanConsistency.REQUEST_PLUS` giúp gì, và giới hạn của nó là gì?
7. Vì sao data query và count query Analytics không tự cùng snapshot?
8. `rowsAsObject()` ánh xạ alias SQL++ vào DTO thế nào?
9. `GROUP BY` trả một row cho mỗi document hay mỗi nhóm?
10. Vì sao một `JOIN`/`UNNEST` có thể làm tổng doanh thu sai?
11. Reactive `Flux` thay đổi điều gì ở client, có làm query MPP ít công việc hơn không?
12. Khi nào dùng Query Service với GSI lại tốt hơn Analytics?
13. Một báo cáo theo tenant có thể rò rỉ gì dù chỉ trả tổng?
14. Vì sao không dùng Analytics để quyết định trừ tồn kho?
15. Nếu môi trường dùng Capella Analytics độc lập, vì sao cần xem lại SDK?
16. Làm thế nào kiểm chứng ingestion link đang bắt kịp?
17. Cần thiết kế gì để báo cáo tháng đã đóng sổ không thay đổi giữa các lần đọc?
18. Khi nào nên dùng Analytics như một SDK adapter riêng sau domain port?

## 41. Tài liệu chính thức và lưu ý theo phiên bản

- [Couchbase Java SDK — Analytics](https://docs.couchbase.com/java-sdk/current/howtos/analytics-using-sdk.html): `Cluster.analyticsQuery`, named parameters, `AnalyticsResult`/metadata, consistency, reactive và scoped queries.
- [Couchbase Server — Analytics Service](https://docs.couchbase.com/server/current/learn/services-and-indexes/services/analytics-service.html): MPP architecture, shadow copies và workload analytical.
- [Couchbase Server — Managing Analytics Collections](https://docs.couchbase.com/server/current/analytics/manage-datasets.html): mapping collections, local/remote links và ingestion.
- [Couchbase Server — Analytics DDL](https://docs.couchbase.com/server/current/analytics/5_ddl.html): CREATE/ALTER, Analytics scopes/collections, links.
- [Couchbase Server — SQL++ for Analytics Queries](https://docs.couchbase.com/server/current/analytics/3_query.html): SELECT, GROUP BY, JOIN và cấu trúc SQL++.
- [Couchbase Server — SQL++ Analytics vs Query](https://docs.couchbase.com/server/current/analytics/6_n1ql.html): bảng khác biệt cú pháp/capabilities.
- [Couchbase Server — Analytics Query Parameters](https://docs.couchbase.com/server/current/analytics/query-params.html): `scan_consistency`, request settings và query context.
- [Couchbase Server — Analytics Query Responses](https://docs.couchbase.com/server/current/analytics/query-responses.html): metrics/status/warnings và kết quả.
- [Couchbase Server — Analytics REST API](https://docs.couchbase.com/server/current/analytics-rest-service/index.html): query, quản trị và monitoring.
- [Couchbase Server — Query Data with SQL++](https://docs.couchbase.com/server/current/n1ql/query.html): vai trò của Query Service và Index Service.
- [Couchbase Java SDK — SQL++ Query](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): `Cluster.query`, GSI và `QueryScanConsistency`.
- [Couchbase — Analytics SDK Overview](https://docs.couchbase.com/home/analytics-sdk.html): phân biệt operational CBAS và các sản phẩm Analytics/Columnar khác.
- [Spring Data Couchbase — Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html) và [Repository](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): mapping entity/CRUD/SQL++ phục vụ ứng dụng.

**Đối chiếu phiên bản và triển khai:** API Java SDK, quyền Analytics, DDL collection/dataset, đường scoped query, sản phẩm Capella Analytics/Enterprise Analytics và cú pháp SQL++ for Analytics thay đổi theo **Couchbase Server/edition, Capella và SDK versions**. Phải xác minh trên deployment thực tế; không suy rằng chỉ vì Repository chạy được thì Analytics Service đã tồn tại. Phần viết này tập trung vào kiến trúc và ví dụ, không thay thế Content QA hoặc integration tests ở bước sau.

> **Ghi nhớ:** **Analytics là đường đọc phân tích gần thời gian thực, không phải đường ghi giao dịch.** Chọn Repository/KV/Query Service khi cần trạng thái hiện hành và invariants; chọn Analytics Service khi cần JOIN/aggregation lớn, chấp nhận ingestion lag có kiểm soát và có tài nguyên vận hành tương ứng. Sử dụng `analyticsQuery`/`AnalyticsResult` đúng API, ánh xạ DTO, chọn `AnalyticsScanConsistency` theo độ mới yêu cầu, và vật hóa phiên bản báo cáo khi cần snapshot bất biến.
