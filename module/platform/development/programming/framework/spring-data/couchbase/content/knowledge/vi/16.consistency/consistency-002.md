# NOT_BOUNDED và REQUEST_PLUS trong truy vấn SQL++ của Spring Data Couchbase

## 1. Vấn đề cần giải quyết

Trong một ứng dụng **Spring Data Couchbase**, sau khi ghi thành công một document, hai lời gọi đọc có thể cho trải nghiệm khác nhau:

~~~java
// Đọc theo document ID đã biết.
orders.findById("order::o-1001");

// Tìm các order theo một field trong JSON.
orders.findByCustomerId("customer-42");
~~~

Lời gọi thứ nhất thường sử dụng **Key–Value (KV)** theo ID. Lời gọi thứ hai thường tạo truy vấn **SQL++** và sử dụng secondary index. Vì index được cập nhật từ các mutation của dữ liệu, nó có thể chậm hơn nội dung document nguồn. Vậy ứng dụng phải quyết định: **có chấp nhận truy vấn theo index chưa theo kịp những thay đổi mới không, hay phải đợi index cập nhật?**

Hai mức scan consistency quan trọng giải quyết lựa chọn này:

- **`NOT_BOUNDED`:** không buộc query đợi index cập nhật tới mốc mutation mới nhất trước khi scan.
- **`REQUEST_PLUS`:** buộc query đợi các index liên quan bắt kịp một mốc của các mutation đã xảy ra trước lúc query bắt đầu theo semantics của Couchbase, rồi mới scan.

Bài học thuộc chương **Tính nhất quán** trong module **SPRING_DATA_COUCHBASE**. Trọng tâm là hiểu đúng **cơ chế, đánh đổi và cách chọn hai mức này** khi dùng SQL++, Repository, CouchbaseTemplate hoặc Java SDK.

### Kết quả học tập

Sau bài, bạn có thể:

1. Diễn tả được vì sao một query `NOT_BOUNDED` có thể tạm thời không thấy document vừa ghi.
2. Nêu chính xác `REQUEST_PLUS` bảo đảm về **độ mới của index**, và điều nó **không** bảo đảm.
3. Viết query SQL++ có tham số và gọi Couchbase Java SDK với `QueryScanConsistency.NOT_BOUNDED` hoặc `REQUEST_PLUS`.
4. Lựa chọn consistency cho màn hình xác nhận, lịch sử đơn, báo cáo và các thao tác kiểm tra trạng thái nhạy cảm.
5. Thiết kế integration test không flaky và đo được chi phí chờ index.
6. Phân biệt scan consistency với CAS, TTL, durability, transaction và reactive API.

## 2. Tình huống xuyên suốt: đơn hàng biến mất khỏi danh sách ngay sau khi tạo

Giả sử chúng ta lưu Order trong:

~~~text
Bucket:      shop
Scope:       sales
Collection:  orders
Document ID: order::o-1001
~~~

Body JSON:

~~~json
{
  "customerId": "customer-42",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 259000
}
~~~

Ứng dụng thực hiện:

1. `OrderRepository.save(order)` trả về thành công.
2. Controller điều hướng người dùng đến trang **Lịch sử đơn hàng**.
3. Trang gọi `findByCustomerId("customer-42")`.
4. Trong một khoảng thời gian ngắn, danh sách có thể chưa chứa `order::o-1001`.
5. Vài thời điểm sau, query cùng điều kiện lại nhìn thấy Order.

Đây có thể là **độ trễ cập nhật secondary index**, không nhất thiết là thao tác `save` bị mất. Điều cần kiểm tra là **đường đọc** và **scan consistency** của query.

~~~mermaid
sequenceDiagram
    participant A as Spring API
    participant D as Data Service
    participant I as Index Service
    participant Q as Query Service
    A->>D: Lưu order::o-1001
    D-->>A: Ghi thành công
    A->>D: KV get(order::o-1001)
    D-->>A: Order đã tồn tại
    Note over D,I: Index có thể đang bắt kịp mutation
    A->>Q: SQL++ WHERE customerId = ...
    Q->>I: Quét secondary index
    I-->>Q: Kết quả theo index tại lúc scan
    Q-->>A: Có thể thiếu Order vừa tạo
    D-->>I: Mutation được phản ánh vào index
~~~

Sơ đồ trên thể hiện một **khả năng**. Trên cluster nhàn, index có thể cập nhật đủ nhanh để query mặc định cũng thấy Order ngay; không có quy tắc rằng query `NOT_BOUNDED` *phải* trả kết quả cũ.

## 3. Hiểu ba lớp dữ liệu trước khi chọn consistency

### 3.1. Document nguồn

Document được nhận diện bằng **bucket + scope + collection + metadata ID**. KV `get` đọc theo key xác định, không cần secondary index để tìm đúng document ấy.

### 3.2. Secondary index

SQL++ có thể lọc `customerId`, `status` hoặc `createdAt` dù không biết document ID trước. Một secondary index giúp Query Service tìm các key/document phù hợp mà không phải quét rộng không cần thiết. Index có trạng thái cập nhật riêng so với thao tác ghi document nguồn.

### 3.3. Query Service

Query Service lập kế hoạch và thực thi SQL++. Khi có yêu cầu scan consistency, nó cần xem xét mức tiến của index liên quan trước khi scan. Không phải bản thân Java Repository quyết định document mới đã nằm trong index hay chưa.

| Đường truy cập | Biết gì từ đầu? | Cần secondary index? | Câu hỏi consistency chính |
| --- | --- | --- | --- |
| KV `get(id)` | Document ID chính xác | Không | Đang đọc bản dữ liệu từ đường KV nào? |
| SQL++ `WHERE customerId = ...` | Giá trị field JSON | Thông thường có index phù hợp | Index đã phản ánh các mutation tới mốc nào? |
| SQL++ `WHERE status = ...` | Trạng thái nghiệp vụ | Thường cần secondary index | Filter có bị ảnh hưởng bởi trạng thái index cũ không? |
| Search/FTS | Từ khóa và query tìm kiếm | Search index riêng | Search index có cơ chế consistency riêng |

**Phạm vi bài này là SQL++ sử dụng index**, không phải mọi kiểu đọc trên Couchbase. Một số kế hoạch SQL++ có thể dùng cơ chế truy cập khác; hãy xem `EXPLAIN` để biết đường thực thi thật.

## 4. NOT_BOUNDED: query không đợi chỉ mục bắt kịp các ghi mới nhất

`NOT_BOUNDED` là một chế độ scan consistency thường gặp của SQL++ khi không đặt yêu cầu chờ index mới hơn. Cách hiểu đúng:

> Query có thể sử dụng trạng thái index hiện có mà không cần đợi index xử lý hết các mutation mới xảy ra trước lúc query bắt đầu.

Nó **không phải**:

- Yêu cầu “chỉ trả dữ liệu cũ”.
- Cam kết “kết quả sẽ luôn stale”.
- Lệnh vô hiệu hóa mọi bảo đảm nhất quán khác trong Couchbase.
- Cách buộc database bỏ qua những thay đổi đã nằm trong index.

### 4.1. Ưu điểm

- Tránh phần thời gian chờ index phải theo kịp mốc mới tại đầu query.
- Phù hợp với workload chấp nhận một mức trễ quan sát được.
- Có thể giảm độ trễ đầu-cuối khi Index Service đang bận xử lý mutation.

### 4.2. Giới hạn

- Một Order vừa insert có thể **chưa xuất hiện** trong query theo `customerId`.
- Một Order vừa đổi `status` có thể vẫn bị xem theo điều kiện index cũ hoặc chưa khớp điều kiện mới.
- Một document đã xóa có thể vẫn để lại dấu vết trong index trong một khoảng thời gian; kết quả cuối cùng còn phụ thuộc engine có phải fetch document nguồn hay không.

Nếu query sử dụng covering index hay fetch document hiện hành, biểu hiện cụ thể có thể khác. Vì vậy không nên tuyên bố mọi `NOT_BOUNDED` sẽ trả nguyên body JSON cũ; điều đáng chú ý là **tập ID/row và điều kiện lọc phụ thuộc độ mới của index**.

### 4.3. Ví dụ phù hợp

- Báo cáo hoặc dashboard không cần phản ánh mutation vừa xảy ra từng mili giây.
- Danh sách gợi ý hoặc thống kê được làm mới định kỳ.
- Trang lịch sử đơn chấp nhận refresh, trong khi trang xác nhận hiển thị Order đã lưu bằng ID.
- Query phục vụ trải nghiệm khám phá, không dùng kết quả làm cơ sở duy nhất cho quyết định ghi có tính cạnh tranh.

## 5. REQUEST_PLUS: đợi chỉ mục đạt mốc dữ liệu phù hợp trước khi scan

`REQUEST_PLUS` yêu cầu Query Service đợi index liên quan bắt kịp các mutation tới mốc xác định khi query bắt đầu, rồi mới quét. Nhờ đó query có thể nhìn thấy những mutation **đã được ghi nhận trước mốc consistency của request** trong phạm vi mà Couchbase bảo đảm.

~~~mermaid
sequenceDiagram
    participant A as Spring API
    participant D as Data Service
    participant I as Index Service
    participant Q as Query Service
    A->>D: Ghi Order mới
    D-->>A: Mutation được xác nhận
    A->>Q: SQL++ với REQUEST_PLUS
    Q->>I: Chờ index bắt kịp mốc request
    Note over Q,I: Có thể phải chờ nếu index lag
    D-->>I: Cập nhật từ mutation
    I-->>Q: Đã đạt mốc cần thiết
    Q-->>A: SQL++ query result
~~~

### 5.1. Ưu điểm

- Đơn giản để yêu cầu query có độ mới cao hơn mặc định, ngay cả khi ứng dụng không giữ mutation token.
- Hữu ích cho các luồng “vừa ghi xong phải tìm theo field” nếu yêu cầu sản phẩm không thể chấp nhận kết quả tạm thiếu.
- Áp dụng ngay tại query có yêu cầu cụ thể, không nhất thiết phải thay toàn bộ hệ thống sang một policy chung.

### 5.2. Đánh đổi

- Query có thể **chờ Index Service**, tăng thời gian phản hồi.
- Nếu index đang tải cao, đang catch up, bị lỗi hoặc chưa sẵn sàng, query có thể chậm hoặc **timeout**.
- Bật cho mọi request có thể tạo thêm áp lực chờ index không cần thiết.
- Không thay thế query plan tốt, secondary index phù hợp và capacity planning.

### 5.3. Điều REQUEST_PLUS không hứa hẹn

- Không khóa database hay ngăn mutation khác xảy ra đồng thời.
- Không tạo snapshot bất biến tại chính thời điểm ghi Order.
- Không làm một chuỗi `save` thành **transaction đa document**.
- Không bảo vệ khỏi **lost update** khi hai request đọc cùng một trạng thái rồi ghi đè — đó là bài toán CAS/conditional write.
- Không tự tạo index bị thiếu.
- Không biến query SQL++ thành truy vấn Search/FTS với consistency giống hệt.
- Không bảo đảm người dùng có quyền xem document; authorization vẫn phải do hệ thống kiểm soát.

## 6. Bảng so sánh trực tiếp

| Câu hỏi | NOT_BOUNDED | REQUEST_PLUS |
| --- | --- | --- |
| Có chủ động đợi index theo kịp mutation mới trước scan? | Không | Có, đến mốc request phù hợp |
| Có thể bỏ sót insert vừa được xác nhận? | Có thể | Với mutation thuộc mốc bảo đảm và query hợp lệ, index phải bắt kịp trước khi scan |
| Có thể trả trạng thái của mutation **sau** thời điểm query bắt đầu? | Có thể | Cũng có thể; không tạo snapshot đúng một thời điểm duy nhất |
| Có giảm khả năng gặp index lag trong kết quả? | Không phải mục tiêu | Có, bằng cách đợi index |
| Phần chi phí chờ index | Thường ít hơn | Có thể tăng đáng kể |
| Khi index backlog lớn | Có thể trả nhanh hơn nhưng kết quả chưa đủ mới | Có thể chờ lâu hoặc timeout |
| Thích hợp báo cáo chấp nhận trễ | Thường có | Chỉ cần khi SLA độ mới cao |
| Thích hợp query danh sách ngay sau ghi bắt buộc thấy ghi đó | Có rủi ro | Thường là một lựa chọn phù hợp |
| Giải quyết lỗi ghi đè đồng thời? | Không | Không |
| Thay thế transaction/durability? | Không | Không |

### 6.1. Một timeline minh họa hai lựa chọn

~~~text
T0  Order mới được ghi thành công qua KV
T1  Active KV đã có Order
T2  Secondary index vẫn chưa có mục cho Order
T3  Query A: NOT_BOUNDED -> có thể trả danh sách thiếu Order
T4  Query B: REQUEST_PLUS -> đợi index đủ mới
T5  Index xử lý mutation Order
T6  Query B scan -> có thể trả Order trong danh sách phù hợp
~~~

T3/T4/T5/T6 là **minh họa thứ tự**, không phải giới hạn độ trễ thực tế. Nếu mutation tiếp theo đổi `customerId` hoặc xóa Order, query sau khi index bắt kịp có thể phản ánh trạng thái mới hơn thay vì một snapshot lịch sử ở T0.

## 7. Cấu trúc dữ liệu và secondary index cho ví dụ

Giả sử ta lưu nhiều Order ở collection `shop.sales.orders`; mỗi body có:

~~~json
{
  "customerId": "customer-42",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 259000
}
~~~

Một truy vấn danh sách gần nhất:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt, o.totalVnd
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Một secondary index khởi đầu:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Truy vấn dùng **named parameter** `$customerId` để tránh nối trực tiếp input vào câu SQL++.

**Lưu ý quan trọng:**

1. Cần có collection, quyền Query/Index và index thật sự sẵn sàng trước khi kiểm thử.
2. Index trong ví dụ là một lựa chọn ban đầu; generated SQL++ từ Spring Data có thể bổ sung type/discriminator và projection khác.
3. Hãy dùng `EXPLAIN` để xem query plan. Không suy rằng index sẽ được sử dụng chỉ vì nó tồn tại.
4. `createdAt` trong ví dụ là field do ứng dụng ghi theo chuẩn thống nhất (chẳng hạn UTC ISO 8601), không tự có trong mọi JSON.
5. `REQUEST_PLUS` chỉ xử lý mốc cập nhật index; nó không sửa query sai logic hoặc thiết kế index không hiệu quả.

### 7.1. Kiểm tra kế hoạch

~~~sql
EXPLAIN
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = "customer-42"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Khi phân tích, xem index scan có đúng đường dự kiến, có fetch dữ liệu không cần thiết, có sort nặng hay không, và có thao tác quét rộng. Consistency mode không thay thế tối ưu `WHERE`/`ORDER BY`.

## 8. Cách đặt scan consistency bằng Couchbase Java SDK

Trong Java SDK 3.x, có thể cấu hình cho từng query bằng `QueryOptions.scanConsistency(...)` với `QueryScanConsistency`.

Ví dụ sau giả định `Cluster` đã được cấu hình và quản lý vòng đời trong Spring Boot; không tạo một `Cluster.connect(...)` cho từng request.

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

public class OrderQueryGateway {
    private static final String SQL = """
        SELECT META(o).id AS documentId,
               o.customerId, o.status, o.createdAt
        FROM `shop`.`sales`.`orders` AS o
        WHERE o.customerId = $customerId
        ORDER BY o.createdAt DESC
        LIMIT 20
        """;

    private final Cluster cluster;

    public OrderQueryGateway(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult listNotBounded(String customerId) {
        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .scanConsistency(
                        QueryScanConsistency.NOT_BOUNDED);

        return cluster.query(SQL, options);
    }

    public QueryResult listRequestPlus(String customerId) {
        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .scanConsistency(
                        QueryScanConsistency.REQUEST_PLUS);

        return cluster.query(SQL, options);
    }
}
~~~

Điểm quan trọng:

- Hai phương thức thực hiện **cùng câu SQL++**, chỉ khác scan consistency.
- `NOT_BOUNDED` có thể dùng để diễn đạt lựa chọn mặc định rõ ràng; trong nhiều trường hợp, không cấu hình scan consistency cũng tương ứng mức mặc định này.
- `REQUEST_PLUS` chỉ thay yêu cầu độ mới của index; không thay đổi `WHERE`, `LIMIT`, quyền truy cập hay transaction.
- SDK trả `QueryResult` và có thể đọc rows qua `rowsAsObject()`. Nó không tự áp dụng toàn bộ Spring Data entity converter.
- Java text block yêu cầu JDK có hỗ trợ. Hãy kiểm tra tính tương thích phiên bản Spring Boot, Spring Data, Java SDK và Couchbase Server khi áp dụng mã.

### 8.1. Thay đổi chính sách theo use case

Không nên có một setting toàn cục “mọi query đều REQUEST_PLUS” nếu chưa hiểu workload. Lớp persistence có thể nêu rõ ý định qua tên phương thức hoặc tham số policy nội bộ:

~~~java
public enum OrderListFreshness {
    ACCEPT_INDEX_LAG,
    WAIT_FOR_REQUEST_BOUNDARY
}
~~~

Một service có thể chọn policy từ **yêu cầu nghiệp vụ**, không từ input tùy ý của người dùng:

~~~java
public QueryResult listOrders(
        String customerId, OrderListFreshness freshness) {

    if (freshness == OrderListFreshness.WAIT_FOR_REQUEST_BOUNDARY) {
        return gateway.listRequestPlus(customerId);
    }
    return gateway.listNotBounded(customerId);
}
~~~

Mã trên minh họa logic service; giả định `gateway` đã được inject và luôn kiểm soát phân quyền trước khi trả dữ liệu. Không cho client bất kỳ tự bật chính sách tốn tài nguyên mà không qua kiểm soát tải.

## 9. Spring Data Repository và CouchbaseTemplate có liên quan gì?

Ở mức Spring Data Couchbase, một Repository có thể định nghĩa:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerId(String customerId);
}
~~~

- `findById("order::o-1001")` thường đi KV.
- `findByCustomerId("customer-42")` thường sinh SQL++ theo field và cần index.
- `save(order)` thực hiện mutation dựa trên mapping/entity state và các tùy chọn được hỗ trợ.

**Cùng một Repository không có nghĩa mọi phương thức có cùng tính nhất quán.** Đường KV và query theo index khác nhau ngay ở tầng Couchbase.

`CouchbaseTemplate` hỗ trợ thao tác entity/query linh hoạt nhưng vẫn dựa trên Couchbase SDK và Query Service khi cần SQL++. API cấu hình scan consistency ở tầng Spring Data **có thể khác theo phiên bản**; cần kiểm tra đúng tài liệu thay vì giả định có một annotation hoặc tên method giống SDK.

Một lựa chọn triển khai rõ ràng khi cần `REQUEST_PLUS` cho đúng một chức năng là:

1. Dùng Repository cho CRUD và các derived query thông dụng.
2. Thêm một **query gateway** dùng SDK như ví dụ ở mục 8, phục vụ use case bắt buộc index mới hơn.
3. Dùng DTO/projection phù hợp; nếu cần entity đầy đủ, áp dụng mapping nhất quán với Spring Data hoặc đọc theo ID.
4. Viết integration test cùng Couchbase thực để xác nhận query trả dữ liệu và mapping đúng.

Nếu stack đang dùng cho phép đặt query scan consistency trong Template hoặc Repository configuration, có thể dùng trực tiếp, nhưng phải **xác minh phiên bản và phạm vi áp dụng**. Đừng tuyên bố một option SDK chắc chắn tồn tại nguyên tên trong mọi API Spring Data.

## 10. Độ mới của index không giống read-after-write qua KV

Một luồng đơn giản:

~~~java
OrderDocument saved = orders.save(newOrder);

// Cần hiện thông tin đúng một đơn: đã có document ID.
OrderDocument confirmed = orders.findById(saved.getId())
        .orElseThrow();

// Cần lịch sử của nhiều đơn theo customerId:
List<OrderDocument> history =
        orders.findByCustomerId(saved.getCustomerId());
~~~

Trường hợp thứ nhất có thể dùng **entity đã lưu** hoặc KV đọc theo ID; không cần chuyển qua query theo secondary index để “xác nhận” sự tồn tại của một document cụ thể.

Trường hợp thứ hai cần query theo field và phải đặt câu hỏi: “Danh sách có bắt buộc chứa mọi mutation vừa được xác nhận không?” Nếu có, cân nhắc `REQUEST_PLUS` hoặc cơ chế mutation-based consistency tương thích; nếu không, `NOT_BOUNDED` có thể hợp lý.

### 10.1. Một thiết kế UX tránh chờ index không cần thiết

~~~mermaid
flowchart TD
    A["POST /orders"] --> B["Save Order qua KV"]
    B --> C["Trả order ID + saved representation"]
    C --> D["Trang xác nhận hiển thị ngay Order"]
    D --> E["Lịch sử đơn load riêng qua SQL++"]
    E --> F{"Lịch sử phải đồng bộ tức thời?"}
    F -->|Có| G["REQUEST_PLUS / policy phù hợp"]
    F -->|Không| H["NOT_BOUNDED + refresh/UX rõ ràng"]
~~~

Chỉ dùng index consistency cao khi nó thực sự bảo đảm một điều kiện sản phẩm. Việc trả ngay saved representation còn tránh round trip đọc lại một document mà service vừa ghi, nếu dữ liệu được trả đã đủ và có thẩm quyền.

## 11. Chi phí hiệu năng của REQUEST_PLUS đến từ đâu?

Thời gian phản hồi SQL++ có thể xem như tổng của nhiều thành phần:

~~~text
Thời gian query
   = thời gian kết nối và truyền request
   + thời gian chờ index đạt consistency yêu cầu
   + thời gian scan/fetch/sort/project kết quả
   + thời gian truyền kết quả về client
~~~

**`REQUEST_PLUS` có thể tăng phần chờ index**. Nếu mutation rate cao, Index Service đang xây dựng/recover index hoặc máy thiếu CPU/RAM, phần chờ này có thể dài và chạm timeout. Một query với `NOT_BOUNDED` có thể hoàn tất trước nhưng phải chấp nhận rủi ro dữ liệu chưa đủ mới.

### 11.1. Những yếu tố làm tăng độ trễ

| Yếu tố | Tác động có thể xảy ra | Cách quan sát |
| --- | --- | --- |
| Mutation rate lớn | Index có backlog | Theo dõi index mutation backlog/lag |
| Nhiều index trên cùng collection | Chi phí cập nhật index tăng | Rà soát index thừa, tài nguyên Index Service |
| Query plan không tốt | Scan/sort/fetch nhiều dù consistency đã đạt | `EXPLAIN`, query metrics |
| Document lớn, projection rộng | Truyền và giải mã dữ liệu tăng | Row size, network, ứng dụng |
| Index chưa ready hoặc gặp lỗi | Query đợi/lỗi/timeout | Index state và logs |
| Timeout/query budget thấp | REQUEST_PLUS dễ thất bại khi phải chờ | P95/P99, timeout/error rate |
| Dồn mọi request vào REQUEST_PLUS | Hệ thống phải trả chi phí consistency không cần thiết | Phân loại traffic theo endpoint |

Đừng chỉ so sánh một lần gọi dev. Cần đo **p50/p95/p99**, throughput và error rate khi có background writes đại diện.

### 11.2. REQUEST_PLUS không phải cách tối ưu một query chậm do thiếu index

Nếu `WHERE customerId = ...` không có index hợp lý, hoặc query phải sort hàng triệu row, bật `REQUEST_PLUS` không giải quyết nút thắt. Thứ tự tối ưu hợp lý:

1. Xác minh keyspace/query/result đúng nghiệp vụ.
2. Kiểm tra index, `EXPLAIN` và projection/pagination.
3. Đo latency không có/ít contention.
4. Chọn consistency theo SLA độ mới.
5. Đo lại dưới tải có mutation và đánh giá timeout.

## 12. Chi tiết ranh giới thời gian: REQUEST_PLUS không khóa các ghi sau đó

Giả sử các thay đổi xảy ra:

~~~text
T0: Ghi Order A (status = CREATED) thành công
T1: Query Q bắt đầu với REQUEST_PLUS
T2: Một request khác sửa Order A thành CONFIRMED
T3: Query Q hoàn tất
~~~

`REQUEST_PLUS` yêu cầu index đủ mới tới **mốc của request Q** theo semantics Couchbase. Nó không chặn thao tác ở T2 và không bắt buộc query phải trả trạng thái đúng bằng T0 hoặc T1. Kết quả có thể phản ánh những mutation mới hơn, tùy thời điểm index scan và query plan.

Đừng nhầm ba khái niệm:

- **Index freshness:** index đã theo kịp mốc nào?
- **Snapshot/transaction isolation:** một nhóm thao tác đọc nhìn thấy tập trạng thái nào trong một giao dịch?
- **Optimistic concurrency:** thao tác ghi của tôi có bị thay đổi đồng thời làm xung đột không?

`REQUEST_PLUS` giải quyết vấn đề thứ nhất; không tự giải quyết hai vấn đề còn lại.

## 13. REQUEST_PLUS vẫn có thể không trả row mà bạn mong muốn

Một query có `REQUEST_PLUS` không đồng nghĩa “row mà business mong muốn chắc chắn xuất hiện”. Kiểm tra các nguyên nhân sau:

1. **Điều kiện `WHERE` sai:** Order thực tế đã đổi `customerId` hoặc `status` nên không còn match.
2. **Sai keyspace:** repository trỏ `shop.sales.orders` nhưng SQL++ query tới `shop._default._default`.
3. **Sai định dạng field:** dữ liệu lưu `createdAt` khác kiểu/cú pháp so sánh.
4. **`LIMIT`/`ORDER BY`:** document đúng tồn tại nhưng nằm ngoài 20 row mới nhất.
5. **Type discriminator:** query qua Spring Data có điều kiện phân biệt kiểu entity mà document SDK thô không có.
6. **Authorization/tenant filter:** request không được xem document hoặc filter chủ ý loại nó.
7. **Index không sẵn sàng/timeout:** query chưa thực thi thành công; không thể diễn giải lỗi thành danh sách rỗng.
8. **Mutation sau mốc query:** document đã bị xóa hoặc đổi trạng thái trước khi query trả kết quả.
9. **Kết quả từ cache ở tầng ứng dụng:** cache trả dữ liệu cũ dù query thực có consistency khác.

Một thao tác debug đúng không dừng ở “thử REQUEST_PLUS rồi vẫn thiếu”. Hãy log correlation ID, document key (nếu chính sách cho phép), keyspace, query plan, consistency mode, row count và lỗi để xác định nguyên nhân.

## 14. NOT_BOUNDED không giải quyết được uniqueness dưới cạnh tranh

Một ví dụ nguy hiểm:

~~~text
Request A: SQL++ WHERE email = "user@example.com" -> không có row
Request B: SQL++ WHERE email = "user@example.com" -> không có row
Request A: insert Customer với ID customer::A
Request B: insert Customer với ID customer::B
~~~

Nếu email phải duy nhất, ngay cả khi hai query được thực hiện với `REQUEST_PLUS` và rất mới tại thời điểm mỗi query, **hai request vẫn có thể cạnh tranh giữa bước check và bước insert**. Scan consistency không biến “kiểm tra rồi ghi” thành một thao tác nguyên tử.

Giải pháp cần thiết kế ở **đường ghi**:

- Dùng một key định danh/ánh xạ email chuẩn hóa có tính duy nhất và thao tác insert có điều kiện.
- Hoặc transaction/logic ghi có ranh giới phù hợp nếu cần thay đổi nhiều document.
- Đặt policy idempotency và xử lý conflict rõ ràng.
- Không dùng query index lag làm nguồn duy nhất quyết định “chưa có bản ghi”.

**Cùng lý do, không dùng `REQUEST_PLUS` thay CAS** khi cập nhật trạng thái Order hay trừ tồn kho.

## 15. Mối liên hệ với CAS, durability, TTL và transaction

| Cơ chế | Câu hỏi nó giải quyết | Quan hệ với NOT_BOUNDED / REQUEST_PLUS |
| --- | --- | --- |
| **CAS / `@Version`** | Có ai sửa document từ lúc tôi đọc không? | Độc lập với độ mới secondary index |
| **Durability** | Mutation được xác nhận bền ở mức nào? | Ghi bền không tự buộc query mặc định thấy ngay |
| **TTL / expiry** | Document được coi hết hạn theo vòng đời nào? | Query index có độ trễ phản ánh expiry; xác thực session nên dựa vào nguồn chính |
| **Transaction** | Nhiều thao tác dữ liệu commit/rollback theo ranh giới nào? | Commit không mặc định biến mọi query/index thành đồng bộ tức thời |
| **Replica reads** | Đọc từ bản sao nào và bản sao mới tới đâu? | Khác với scan consistency của SQL++ index |
| **Search/FTS** | Search index trả hits theo độ mới nào? | Có API/semantics consistency riêng; không áp dụng nguyên xi REQUEST_PLUS của SQL++ |

### 15.1. CAS không cải thiện index freshness

Nếu hai request cùng đọc Order ở CAS `C1`, một request ghi thành công đổi CAS thành `C2`, request còn lại có thể bị từ chối khi ghi với CAS `C1`. Cơ chế đó bảo vệ không mất cập nhật; **không** thay thế việc index theo `status` bắt kịp mutation đã ghi.

### 15.2. Durability không thay scan consistency

Tăng durability có thể yêu cầu xác nhận ghi bền hoặc replication theo chính sách. Nó **không** có nghĩa secondary index đã quét được mutation ở chính thời điểm mutation được ACK. Nếu business cần query ngay sau ghi, vẫn phải xét read pattern và consistency.

### 15.3. TTL và session

Một session document có expiry metadata. Đến khi hết hạn, KV read theo key phải tuân thủ semantics expiry; không xác thực session chỉ bằng SQL++ query theo field khi index có thể trễ. Field JSON `expiresAt` do ứng dụng tự thêm **không tự kích hoạt** Couchbase TTL.

### 15.4. Transaction nhiều document

Giả sử tạo Order và trừ Inventory cần cùng thành công. Việc bật `REQUEST_PLUS` cho query danh sách không biến hai thao tác ghi thành một transaction. Cần transaction Couchbase phù hợp với stack hoặc workflow bù trừ được thiết kế riêng. Cần hiểu transaction boundary, retry và hành vi khi kết quả commit không rõ.

## 16. Khi nào cân nhắc consistency theo mutation token?

Bên cạnh `NOT_BOUNDED` và `REQUEST_PLUS`, SDK có thể hỗ trợ yêu cầu query đợi **các mutation cụ thể** được biểu đạt qua token/state, thường tương ứng cơ chế `at_plus`.

Ví dụ ý tưởng:

~~~text
KV upsert(Order A) -> token A
KV upsert(Order B) -> token B
           |
           v
      MutationState(A, B)
           |
           v
SQL++ query consistentWith(state)
           |
           v
Đợi index tới ít nhất các mutation đã biết
~~~

Khác biệt tư duy:

- **`REQUEST_PLUS`:** đợi index bắt kịp mốc chung của request (không nhất thiết phải giữ token trong application).
- **Mutation-based consistency:** yêu cầu index đã bao gồm **những mutation cụ thể** mà ứng dụng biết.

Nếu viết bằng Java SDK, cần đối chiếu cách tạo `MutationState`, lấy token từ mutation result và gọi `consistentWith(...)` ở đúng phiên bản. Khi chỉ sử dụng `repository.save(...)`, abstraction có thể không trả trực tiếp token cần thiết cho use case này. Không nên bịa API ở tầng Spring Data nếu chưa kiểm tra.

Bài này tập trung hai lựa chọn `NOT_BOUNDED` và `REQUEST_PLUS`; mutation-based consistency là một phương án liên quan khi yêu cầu chỉ cần thấy các ghi đã biết mà không muốn đợi mọi mutation khác.

## 17. Kiểm thử tích hợp hai consistency mode

Một test có giá trị phải chạy qua **Couchbase thực hoặc môi trường tương đương** với secondary index sẵn sàng. Mock Repository không kiểm chứng được độ mới của index.

### 17.1. Thiết kế test không flaky

Các bước:

1. Tạo một document Order mới bằng KV với customerId ngẫu nhiên.
2. Đọc lại theo ID bằng KV, xác nhận mutation đã ghi thành công.
3. Query theo customerId với `NOT_BOUNDED`; **ghi nhận kết quả**, nhưng không assert nó bắt buộc thiếu Order.
4. Query cùng điều kiện với `REQUEST_PLUS`; xác nhận Order vừa tạo xuất hiện khi query thành công và không có mutation khác loại bỏ nó.
5. Đo thời gian hai query, lặp trên nhiều lần chạy và dưới tải ghi có kiểm soát.
6. Dọn dữ liệu test trong `finally` hoặc teardown.
7. Xác nhận index/query plan đã chuẩn bị đúng.

Vì Index Service có thể xử lý mutation rất nhanh, test dưới đây là **sai tư duy**:

~~~text
Ghi Order
Query NOT_BOUNDED
assert Order KHÔNG xuất hiện  // Flaky: index có thể đã kịp
~~~

`NOT_BOUNDED` **cho phép** index chưa mới; nó không **bắt buộc** kết quả stale.

### 17.2. Ví dụ integration test với Spring Boot và SDK

Giả sử Spring Test đã cấu hình bean `Cluster`, collection `shop.sales.orders` và secondary index đáp ứng điều kiện customerId:

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
class OrderConsistencyIT {
    @Autowired
    private Cluster cluster;

    @Test
    void requestPlusSeesAcknowledgedInsert() {
        Collection orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");

        String id = "order::it-" + UUID.randomUUID();
        String customerId = "customer-it-" + UUID.randomUUID();

        String sql = """
            SELECT META(o).id AS documentId
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            """;

        boolean inserted = false;
        try {
            orders.insert(id, JsonObject.create()
                    .put("customerId", customerId)
                    .put("status", "CREATED"));
            inserted = true;

            // Đường KV: không cần chờ secondary index.
            orders.get(id);

            // Đường SQL++: yêu cầu index bắt kịp mốc của query.
            QueryResult result = cluster.query(
                    sql,
                    queryOptions()
                            .parameters(JsonObject.create()
                                    .put("customerId", customerId))
                            .scanConsistency(
                                    QueryScanConsistency.REQUEST_PLUS)
            );

            assertTrue(result.rowsAsObject().stream()
                    .anyMatch(row ->
                            id.equals(row.getString("documentId"))));
        } finally {
            if (inserted) {
                orders.remove(id);
            }
        }
    }
}
~~~

Đây là **mẫu cấu trúc** để mở rộng thành test hoàn chỉnh; trước khi copy chạy, cần chuẩn bị fixtures, index, quyền Query, xử lý cả trường hợp kết quả insert/xóa không rõ do timeout và dependency JUnit/Spring Test. Đoạn `finally` chỉ xóa khi ứng dụng đã nhận xác nhận insert; một test suite thực nên có cơ chế dọn fixture độc lập để xử lý những tài liệu có thể đã ghi nhưng client không nhận được ACK. Với production, test phải chạy trên môi trường tách biệt.

### 17.3. Đo độ trễ đúng

Có thể đo thời gian ngay quanh mỗi `cluster.query(...)` trên SDK, kèm:

- Consistency mode.
- Query ID/correlation ID theo tracing.
- Query plan/index được sử dụng.
- Thời gian tổng, query metrics khi có, và trạng thái Index Service.
- Mutation rate trong thời gian đo.
- Số lần timeout, retry và row count.

Chỉ từ một lần đo ngắn không thể suy ra “REQUEST_PLUS luôn chậm hơn X mili giây”; index lag phụ thuộc tải và hoàn cảnh.

## 18. Troubleshooting: đọc theo ID thấy, SQL++ chưa thấy

| Hiện tượng | Kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| `findById` thấy Order mới, `findByCustomerId` chưa thấy | Query mode, keyspace, index freshness | Chọn REQUEST_PLUS khi cần, hoặc hiển thị saved Order |
| REQUEST_PLUS chậm | Mutation backlog, Index Service, timeout | Đo wait time, tăng capacity/điều chỉnh policy |
| REQUEST_PLUS trả lỗi thiếu index | Query plan, index build/state, quyền | Tạo/kiểm tra index đúng collection |
| REQUEST_PLUS thành công nhưng thiếu Order | `WHERE`, `LIMIT`, `ORDER BY`, discriminator, concurrent mutation | Kiểm tra body/ID, query logic và trạng thái nguồn |
| Xóa Order rồi query còn trả hit | Index chưa phản ánh xóa, query plan | Không dùng query index cũ cho quyết định ghi/ủy quyền |
| Session đã logout nhưng tìm theo field còn thấy | Đường truy cập session không phù hợp | Xác thực theo key/expiry và revoke state |
| Tạo trùng Order sau retry | Timeout ambiguous, thiếu idempotency | Tạo idempotency key, kiểm tra theo key trước khi xử lý lại |
| SQL++ chậm cả khi NOT_BOUNDED | Thiếu index, sort lớn, network | `EXPLAIN`, projection/pagination, capacity |
| WebFlux dùng REQUEST_PLUS bị block thread | Dùng API sync hoặc gọi `block()` trên event loop | Dùng API reactive hoặc cô lập blocking có kiểm soát |

**Không biến mọi lỗi query thành danh sách rỗng.** Trả empty cho timeout hoặc thiếu index sẽ khiến nghiệp vụ nhầm lỗi hệ thống thành “không tồn tại dữ liệu”, đặc biệt nguy hiểm nếu dùng để quyết định tạo một resource duy nhất.

## 19. Bài tập và câu hỏi tự kiểm tra

### Bài tập A — Xác nhận đơn ngay sau POST

Sau khi `POST /orders` thành công, response đã có Order ID. Trang tiếp theo chỉ cần hiển thị trạng thái và tổng tiền của **đúng Order đó**.

**Hỏi:** Nên query SQL++ với `REQUEST_PLUS` hay đọc KV theo ID?

**Gợi ý:** Dùng saved representation hoặc KV theo ID. Không cần secondary index để xác nhận một document có key đã biết.

### Bài tập B — Lịch sử cần thấy đơn mới ngay

Trang `GET /customers/{id}/orders` phải hiển thị đơn vừa tạo trong kết quả SQL++ nếu nó thuộc 20 đơn gần nhất theo thứ tự chính xác.

**Hỏi:** `NOT_BOUNDED` hay `REQUEST_PLUS` phù hợp hơn?

**Gợi ý:** `REQUEST_PLUS` là lựa chọn phù hợp hơn nếu bắt buộc index bắt kịp mutation tại mốc query, nhưng vẫn phải xem `WHERE`, `ORDER BY`, `LIMIT` và các mutation xảy ra đồng thời. Một phương án UX khác là ghép Order vừa tạo vào màn hình xác nhận và tải lịch sử riêng.

### Bài tập C — Báo cáo tổng hợp

Báo cáo cuối ngày được refresh mỗi 30 giây, không yêu cầu ghi vừa xảy ra phải xuất hiện trong lần refresh đầu tiên.

**Hỏi:** Có nhất thiết bật `REQUEST_PLUS` cho tất cả truy vấn không?

**Gợi ý:** Không. `NOT_BOUNDED` có thể phù hợp với SLA chấp nhận độ trễ; vẫn cần đo freshness thực tế.

### Bài tập D — Trùng email

Hai request đồng thời query xem email chưa tồn tại, rồi cùng insert hai Customer có hai ID khác nhau.

**Hỏi:** Đổi cả hai query sang `REQUEST_PLUS` có đủ bảo đảm email duy nhất không?

**Gợi ý:** Không. Đó là race condition của “check rồi insert”; cần một ràng buộc ở đường ghi như key/record ánh xạ tạo có điều kiện hoặc transaction.

### Bài tập E — Phân biệt CAS và scan consistency

Hai nhân viên cùng cập nhật trạng thái một đơn. Người thứ hai bật `REQUEST_PLUS` cho query theo status.

**Hỏi:** Có chặn được lost update không?

**Gợi ý:** Không. Sử dụng `@Version`/CAS hoặc thao tác ghi có điều kiện, rồi xử lý conflict.

### Câu hỏi nhanh

1. **NOT_BOUNDED có luôn trả dữ liệu cũ?** Không; chỉ không yêu cầu đợi index mới hơn.
2. **REQUEST_PLUS cần index có sẵn không?** Có, truy vấn phải có kế hoạch truy cập hợp lệ; consistency không tự tạo index.
3. **REQUEST_PLUS có thể timeout không?** Có, nếu chờ index/hoàn tất query vượt timeout.
4. **Có bắt buộc dùng REQUEST_PLUS khi chỉ có Order ID?** Không; KV theo key thường thích hợp hơn.
5. **REQUEST_PLUS có bảo đảm snapshot đúng lúc insert không?** Không; mutation mới hơn vẫn có thể được phản ánh.
6. **NOT_BOUNDED có liên quan durability của mutation không?** Không phải cùng một vấn đề.
7. **Khi query mặc định thấy Order ngay, test có sai không?** Không; index có thể cập nhật kịp.
8. **Reactive Repository có tự thay đổi scan consistency thành REQUEST_PLUS?** Không nên giả định; phải cấu hình theo API và phiên bản.

## 20. Checklist chọn consistency cho production

- [ ] Đã xác định API cần **một document theo ID** hay **danh sách theo field**?
- [ ] Query SQL++ có index phù hợp và query plan đã được kiểm tra bằng `EXPLAIN`?
- [ ] Với mỗi endpoint, đã xác định SLA về **độ mới** (chấp nhận trễ hay phải thấy mutation đã ghi)?
- [ ] Đã phân biệt rõ `NOT_BOUNDED` và `REQUEST_PLUS` trong code/configuration?
- [ ] REQUEST_PLUS được bật có chọn lọc, không phải mặc định vì “an toàn hơn”?
- [ ] Timeout đã tính chi phí đợi index; có chỉ số latency p95/p99 và query timeout?
- [ ] Không dùng query có thể trễ để làm ràng buộc duy nhất email, ID hay trạng thái giao dịch?
- [ ] Đã xác định cách xử lý CAS conflict, idempotency, transaction và durability độc lập với scan consistency?
- [ ] Những route WebFlux có dùng API non-blocking hoặc cô lập blocking đúng cách?
- [ ] Test có xác nhận REQUEST_PLUS thấy mutation trước mốc query, mà không assert NOT_BOUNDED bắt buộc stale?
- [ ] Đã xử lý đúng lỗi query thiếu index, timeout, quyền và trạng thái index thay vì trả empty?
- [ ] Có giám sát Index Service, mutation backlog, Query Service latency và retry load?

## 21. Kết luận

**`NOT_BOUNDED` và `REQUEST_PLUS` là hai lựa chọn về *độ mới của secondary index* khi thực thi SQL++.** `NOT_BOUNDED` tránh chờ index bắt kịp các mutation mới trước khi scan, phù hợp những workload chấp nhận độ trễ dữ liệu. `REQUEST_PLUS` đợi index tiến tới mốc của request, phù hợp khi query theo field bắt buộc phải nhìn thấy các mutation đã được xác nhận trước mốc ấy, đổi lại có thể tăng latency và rủi ro timeout.

Trong **Spring Data Couchbase**, hãy luôn phân biệt **KV theo document ID** với **SQL++ qua index**. Với một document vừa ghi và đã có ID, thường nên trả saved entity hoặc đọc KV. Với danh sách lọc theo field, chọn scan consistency theo SLA độ mới, dùng index/query plan hiệu quả và đo dưới tải thực tế. Đừng trộn scan consistency với **CAS, TTL, durability, transaction, replica reads hay Search freshness**: mỗi khái niệm giải quyết một phần riêng của tính đúng đắn và khả năng vận hành.
