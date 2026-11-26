# Đọc sau ghi và thời điểm chỉ mục nhìn thấy thay đổi

## 1. Từ tình huống thực tế đến mục tiêu bài học

Một người dùng tạo đơn hàng trong ứng dụng Spring Boot. API trả `201 Created` và một `orderId` hợp lệ. Người dùng chuyển ngay sang trang “Đơn hàng của tôi”, nhưng danh sách chưa có đơn vừa đặt; vài giây hoặc vài lần tải lại sau, đơn xuất hiện. Khi xem trực tiếp bằng ID, backend lại đọc được đơn ngay.

Đây là tình huống điển hình của **read-after-write (đọc sau ghi)** khi hai đường truy cập Couchbase có cơ chế khác nhau:

- **Đọc Key–Value (KV) theo document ID:** thường nhìn thấy mutation đã được xác nhận trên đường active KV mà không phải chờ secondary index.
- **Truy vấn SQL++ theo field JSON:** thường cần **Global Secondary Index (GSI)**, và index có thể chưa phản ánh mutation ở thời điểm query quét.

Bài học thuộc chương **Tính nhất quán** của module **SPRING_DATA_COUCHBASE**. Để xây tầng truy cập Couchbase qua Spring Data, người học cần hiểu document mapping, Repository, `CouchbaseTemplate` và SQL++, đồng thời biết cách lựa chọn query consistency, CAS, TTL, transaction, reactive API và các biện pháp vận hành.

**Sau bài này, bạn sẽ có thể:**

1. Giải thích chính xác “ghi thành công”, “đọc KV thấy dữ liệu” và “index đã nhìn thấy dữ liệu” là ba mốc **khác nhau**.
2. Mô tả đường đi của insert/update/delete từ Data Service tới secondary index và query SQL++.
3. Phân biệt **độ mới của index** với **độ mới của document được fetch**, nhất là khi index có lag.
4. Lựa chọn giữa **trả ngay kết quả ghi**, **đọc lại theo ID**, `NOT_BOUNDED`, `REQUEST_PLUS` và consistency theo mutation token khi hỗ trợ.
5. Viết Repository, Template và SDK query cho một case study cụ thể.
6. Tránh dùng một query có thể trễ để quyết định uniqueness, thanh toán, quyền truy cập hoặc chống lost update.
7. Tạo kiểm thử read-after-write không phụ thuộc may rủi về tốc độ cập nhật index, và đo ảnh hưởng latency.

> **Câu hỏi định hướng:** Khi người dùng hỏi “vừa lưu rồi sao chưa thấy?”, trước hết phải xác định họ đang đọc **document theo key**, **query qua index**, **replica**, **Search index**, hay **cache của ứng dụng**.

## 2. Mô hình hệ thống: đường ghi và hai đường đọc

Giả sử ứng dụng có bucket `shop`, scope `sales`, collection `orders`. Repository làm việc trên `OrderDocument` đã được mapping tới collection này.

~~~mermaid
flowchart LR
    APP["Spring OrderService"] --> WR["Repository / Template / SDK write"]
    WR --> DATA[("Data Service: active document")]
    DATA --> KV["KV get theo ID"]
    KV --> DETAIL["Chi tiết đơn hàng"]

    DATA --> STREAM["Mutation stream / index update"]
    STREAM --> INDEX[("Index Service: secondary index")]
    INDEX --> QUERY["Query Service: SQL++"]
    QUERY --> LIST["Danh sách đơn theo customerId"]
~~~

Sơ đồ mang tính khái niệm, không thể hiện toàn bộ partition, vBucket, replica, networking hoặc mọi đường thực thi của Query Service. Điều quan trọng là **mutation trên dữ liệu nguồn** và **cập nhật cấu trúc tìm kiếm của index** có thể không hoàn tất cùng lúc.

| Công việc | Cơ chế thường dùng | Có cần secondary index? |
| --- | --- | --- |
| Lưu Order theo document ID | KV mutation | Không |
| Lấy Order bằng `findById(id)` | KV get | Không |
| Tìm Order theo `customerId` | SQL++ qua index | Thường có |
| Sắp xếp các Order theo ngày | SQL++ + index/query plan | Thường có |
| Tìm mô tả sản phẩm theo từ khóa | Search Service và Search index | Cơ chế index khác GSI |

Dùng cùng một Java entity hoặc cùng `CouchbaseRepository` **không khiến tất cả các method đi chung một đường đọc**.

## 3. Document ID, JSON body và một đơn hàng mẫu

Một document Couchbase có **địa chỉ logic** gồm bucket, scope, collection và key metadata:

~~~text
Bucket:       shop
Scope:        sales
Collection:   orders
Document ID:  order::o-20261125-1001
~~~

Body JSON:

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "currency": "VND",
  "totalVnd": 350000
}
~~~

Các field `customerId`, `status` và `createdAt` phục vụ query nghiệp vụ. `order::o-20261125-1001` là **key metadata**, không bắt buộc hiện diện dưới tên `id` trong JSON body. Spring Data có thể thêm type discriminator theo converter/mapping của phiên bản đang sử dụng.

Ba câu lệnh sau khác nhau về mục tiêu:

~~~text
KV get key "order::o-20261125-1001"
  -> cần biết key chính xác

SQL++ WHERE customerId = "c-1001"
  -> cần tìm nhiều document theo field

SQL++ WHERE status = "CREATED"
  -> cần tìm nhiều document theo một field khác
~~~

Index phù hợp với query theo customerId và ngày có thể là:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Đây là index khởi đầu để minh họa. Một index thực tế cần được chọn từ query plan, selectivity, sort, projection và type discriminator của dữ liệu.

## 4. Timeline: ba thời điểm không được nhập làm một

Xét một Order mới được ghi qua KV:

~~~text
Thời gian tăng dần
   |
   | T0: Application gửi KV insert/upsert Order
   | T1: Data Service xác nhận mutation theo durability option hiện hành
   | T2: Application nhận kết quả write thành công
   | T3: KV get theo key trên active path thấy Order
   | T4: Index Service nhận/xử lý mutation liên quan
   | T5: Secondary index đã phản ánh Order
   | T6: SQL++ query quét index và có thể chọn Order mới
   v
~~~

**T3, T4, T5, T6 là mốc minh họa**, không phải một thứ tự tổng quát cố định của tất cả request trong thực tế. Trên một cluster nhàn, index có thể theo kịp trước khi application gửi query. Tại một cluster đang ghi nhiều dữ liệu, một request SQL++ có thể bắt đầu trước khi index nhận mutation mới.

Điều có thể xảy ra:

~~~text
T0  Ghi Order thành công
T1  GET /orders/o-20261125-1001       -> có Order
T2  GET /customers/c-1001/orders      -> chưa có Order trong lịch sử
T3  Index nhận đủ mutation
T4  GET /customers/c-1001/orders      -> có Order nếu WHERE/LIMIT phù hợp
~~~

Điều **không nên suy diễn**:

- Không có “độ trễ mặc định luôn là 100 ms” hoặc một con số chung cho mọi cluster.
- `NOT_BOUNDED` không bắt buộc query phải trả dữ liệu cũ.
- Đọc KV thấy Order mới không chứng minh secondary index đã cập nhật.
- Secondary index bắt kịp không chứng minh mọi Search index, cache hoặc bản sao dữ liệu bên ngoài đã cập nhật.
- Một query không trả row chưa đủ chứng minh vấn đề index lag: còn phải xét `WHERE`, `ORDER BY`, `LIMIT`, quyền và mapping.

## 5. Đọc sau ghi theo KV: điều gì được kỳ vọng?

### 5.1. Read-your-writes trên active KV path

Sau khi một KV mutation trả thành công, việc đọc lại theo **cùng document ID, cùng collection trên active KV path** thường phản ánh mutation đã được xác nhận. Đây là lựa chọn tự nhiên nếu service cần xem lại **chính document vừa lưu**.

Ví dụ:

~~~java
OrderDocument saved = orders.save(newOrder);

OrderDocument detail = orders.findById(saved.getId())
        .orElseThrow();
~~~

Lời gọi `findById` có key đầy đủ; không cần secondary index cho query theo `customerId` để tìm chính Order này.

Thậm chí nếu dữ liệu trả từ `save` đã đủ để phản hồi người dùng, một GET lại có thể là **round trip dư thừa**:

~~~java
OrderDocument saved = orders.save(newOrder);
return saved; // Dùng biểu diễn được tầng ghi trả về.
~~~

### 5.2. Phạm vi của kỳ vọng

Không nên mở rộng câu trên thành “mọi cách đọc Couchbase đều luôn mạnh như active KV read”:

- **Replica read:** replica có thể chưa bắt kịp active; semantics của API đọc replica cần kiểm tra riêng.
- **Cross-cluster/region:** replication qua các môi trường có độ trễ riêng.
- **Cache ở application hoặc gateway:** cache có thể còn phiên bản cũ dù KV source đã mới.
- **Write timeout/ambiguous result:** chưa nhận ACK không nhất thiết có nghĩa mutation không xảy ra.
- **Transaction chưa commit:** cần đọc theo đúng context/visibility của transaction, không mặc định một thay đổi chưa commit xuất hiện với mọi reader.
- **TTL/expiry:** document có thể đã đến hạn hết hiệu lực trước khi reader gọi.

Vì thế hãy ghi rõ trong hợp đồng API: **đọc lại một document đã được xác nhận thành công, qua cùng nguồn dữ liệu và đường active KV**, chứ không hứa vô hạn về mọi bản sao.

## 6. Vì sao chỉ mục có thể đến sau document?

Một **Global Secondary Index** có thể lưu thông tin được trích xuất từ các field JSON để phục vụ tìm kiếm, lọc và sắp xếp. Index cần cập nhật khi document thêm mới, đổi giá trị field có index hoặc bị xóa/hết hạn.

Ví dụ SQL++:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt, o.totalVnd
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Thay vì biết ID trước, Query Service cần tìm các Order matching `customerId`. Nó thường dùng index theo `customerId` để tìm các ID ứng viên rồi thực hiện các bước scan/fetch/filter/sort/project theo kế hoạch.

### 6.1. Ghi và cập nhật index là hai dòng công việc

~~~mermaid
sequenceDiagram
    participant API as Spring Service
    participant DATA as Data Service
    participant IDX as Index Service
    participant QUERY as Query Service
    API->>DATA: insert Order id=order::1001
    DATA-->>API: Mutation acknowledged
    API->>QUERY: SELECT ... WHERE customerId=...
    QUERY->>IDX: IndexScan theo customerId
    Note over IDX: Index có thể chưa có mutation
    IDX-->>QUERY: Tập ID ở mốc index hiện tại
    QUERY-->>API: Có thể thiếu Order mới
    DATA-->>IDX: Mutation được phản ánh vào index
~~~

Không nên diễn giải sơ đồ thành một protocol bắt buộc từng bước. Mục tiêu là phân biệt **ACK của write** với **mốc index đủ mới để scan**.

### 6.2. Độ trễ index chịu ảnh hưởng bởi gì?

- Tốc độ insert/update/delete và kích thước dữ liệu.
- Số index cần duy trì, index design và partition.
- Tài nguyên CPU, memory, disk của Index Service.
- Hoạt động index build/rebalance/recovery và mức tải chung.
- Query consistency mode, query timeout và loại truy vấn.
- Đường mạng và tài nguyên của cluster.

Trong production, đo chỉ số index progress/backlog và query latency; không thay thế đo đạc bằng một giả định cứng về số mili giây.

## 7. Ba dạng mutation và tác động tới truy vấn

### 7.1. Insert: document mới chưa xuất hiện

~~~text
T0: INSERT order::1001, customerId=c-1001
T1: KV get(order::1001) -> thành công
T2: GSI chưa có order::1001
T3: Query WHERE customerId=c-1001 -> có thể thiếu order::1001
~~~

Đây là ví dụ trực quan nhất của read-after-write gap.

### 7.2. Update: membership hoặc thứ tự index thay đổi

Giả sử ban đầu:

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z"
}
~~~

Sau cập nhật:

~~~json
{
  "customerId": "c-1001",
  "status": "CONFIRMED",
  "createdAt": "2026-11-25T08:00:00Z"
}
~~~

Một index theo `status` có thể vẫn phản ánh điều kiện cũ trong lúc bắt kịp mutation. Query `WHERE status = "CREATED"` hoặc `WHERE status = "CONFIRMED"` có thể chịu ảnh hưởng của lag. Nếu index dùng để xác định membership còn engine fetch body nguồn tại thời điểm truy vấn, kết quả có thể khác so với trường hợp index đủ cover — vì vậy không khẳng định mọi query sẽ hiển thị nguyên bản JSON cũ.

### 7.3. Delete: index còn key trong một khoảng ngắn

~~~text
T0: DELETE order::1001 đã được xác nhận
T1: Active KV get(order::1001) -> not found
T2: GSI có thể chưa xử lý removal
T3: Query theo field -> có thể bị ảnh hưởng bởi index stale
~~~

Kết quả cuối còn phụ thuộc index scan và việc Query Service có cần fetch document nguồn hay không. Nếu fetch thất bại vì document đã xóa, row có thể không được trả; một covering plan có thể phản ánh dữ liệu index cũ theo cách khác. **Không sử dụng một query index trễ làm phép kiểm tra xóa chắc chắn** cho workflow bảo mật hoặc nghiệp vụ quan trọng.

### 7.4. TTL/expiry cũng ảnh hưởng vòng đời document

Khi document hết hạn, trạng thái hợp lệ trên đường KV và tiến độ phản ánh expiry trong index cần được xét độc lập. Một trường JSON tên `expiresAt` **không phải** Couchbase TTL trừ khi ứng dụng tự thực hiện cơ chế hết hạn; TTL thực sự là metadata/option ở database.

Với session đăng nhập, hãy kiểm tra theo key/expiry/revocation thích hợp thay vì quyết định “còn đăng nhập” bằng một query liệt kê session theo index có thể trễ.

## 8. Đọc mới đến đâu: NOT_BOUNDED, REQUEST_PLUS và mutation state

Để yêu cầu SQL++ đợi index khi cần, client có các mức scan consistency. Chúng chỉ có ý nghĩa trên đường **query/index** phù hợp, không tự làm KV get khác đi.

| Mức | Điều Query Service cần làm | Khi nào cân nhắc? |
| --- | --- | --- |
| `NOT_BOUNDED` | Không buộc index đợi bắt kịp mutation mới nhất ở mốc request trước scan | Dashboard, báo cáo, danh sách chấp nhận lag |
| `REQUEST_PLUS` | Đợi index liên quan tới mốc consistency của request trước scan | SQL++ ngay sau ghi cần dữ liệu đủ mới |
| `AT_PLUS`/mutation-based | Đợi index tới các mutation cụ thể được xác định bởi token/state nếu API hỗ trợ | Read-your-writes cho các ghi cụ thể, cần điều khiển tinh hơn |

### 8.1. NOT_BOUNDED không phải “cố tình làm dữ liệu cũ”

Nếu index đã bắt kịp trước khi query đến, `NOT_BOUNDED` vẫn có thể trả Order mới ngay. Ý nghĩa chỉ là **không bắt index phải đợi** tới một mốc mutation mới được yêu cầu.

Nó thường là chế độ mặc định nếu không yêu cầu scan consistency cao hơn. Kiểm tra default cụ thể của lớp API/phiên bản đang dùng, thay vì áp một giả định cho mọi kết nối và truy vấn khác nhau.

### 8.2. REQUEST_PLUS chờ index tại mốc request

Giả sử một write được ACK, rồi application gửi SQL++ với `REQUEST_PLUS`. Query Service đợi index bắt kịp những mutation thuộc mốc consistency được xác định khi query bắt đầu theo semantics Couchbase, sau đó scan.

Điều nó **không làm**:

- Không ngăn request khác ghi sau khi query bắt đầu.
- Không lấy lại snapshot lịch sử đúng bằng bản JSON tại thời điểm `save`.
- Không thay thế khóa/transaction serializable.
- Không tự tạo index thiếu hoặc sửa `WHERE` sai.
- Không biến hai lời gọi `save` thành một transaction nguyên tử.
- Không làm Query Service bỏ qua `ORDER BY`, `LIMIT` hoặc phân quyền.

Nếu index bị backlog, `REQUEST_PLUS` có thể **chậm hoặc timeout**; nhất quán hơn về index freshness phải trả chi phí thời gian chờ.

### 8.3. Mutation-based consistency tập trung vào những ghi đã biết

Trong luồng dùng Couchbase Java SDK, kết quả mutation có thể cung cấp token; ứng dụng có thể gom token thành `MutationState` để query đợi những mutation đó. Đây là phương án “consistent with các ghi cụ thể” thay vì đợi mốc chung của toàn request.

~~~text
KV upsert(Order A) -> mutation token A
KV upsert(Order B) -> mutation token B
                       |
                       v
                MutationState(A,B)
                       |
                       v
         SQL++ consistentWith(state)
                       |
                       v
           Index đã vượt qua các mốc A,B
~~~

Token không phải timestamp tùy ý của máy client. `@Version`/CAS cũng không phải mutation token dành cho scan consistency. Cần đối chiếu SDK/Server version, keyspace của các token và API thực sự có thể lấy/truyền state, đặc biệt khi thao tác ghi đi qua Spring Data Repository không expose token trực tiếp.

## 9. Read-after-write là bảo đảm của luồng, không phải một option toàn cầu

Cùng một màn hình có thể cần các hợp đồng đọc khác nhau.

| Use case | Yêu cầu nhìn thấy dữ liệu | Giải pháp phù hợp |
| --- | --- | --- |
| Trang xác nhận ngay sau tạo Order | Chính Order vừa tạo | Trả saved representation hoặc KV theo ID |
| Lịch sử Order ngay sau khi tạo | Query theo customerId chứa Order mới nếu match page/filter | SQL++ `REQUEST_PLUS` hoặc mutation-based khi hỗ trợ |
| Lịch sử Order xem bất kỳ lúc nào | Chấp nhận một khoảng trễ ngắn | SQL++ `NOT_BOUNDED` và UX refresh |
| Danh sách báo cáo cuối ngày | Cần độ trễ theo SLO báo cáo | Chọn policy theo SLO, không theo thói quen |
| Xác nhận Order chỉ khi status hợp lệ | Không mất cập nhật và không xác nhận hai lần sai | KV + CAS/conditional write |
| Email phải duy nhất khi đăng ký | Không được tạo hai Customer cùng email | Định danh/conditional insert/transaction phù hợp |
| Xác thực session | Phải xác định session còn hiệu lực tại request | KV theo session key + expiry/revocation |

**Nguyên tắc thực dụng:** Nếu bạn có key chính xác của document vừa ghi, hãy thử giải quyết bằng **kết quả đã lưu hoặc KV** trước khi bật scan consistency cao cho một query theo field.

## 10. Spring Data Couchbase Repository: hai cách đọc cùng entity

Một entity Java minh họa mapping:

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

    public OrderDocument() {}

    public OrderDocument(String id, String customerId,
                         String status, String createdAt,
                         long totalVnd) {
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
    public void setStatus(String status) {
        this.status = status;
    }
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

Ở những phiên bản Spring Data hỗ trợ, `@Scope` và `@Collection` trên entity chọn keyspace. Nếu stack khác version, xác minh cách cấu hình tương ứng. `@Version` lưu CAS metadata phục vụ optimistic locking; nó **không buộc secondary index đủ mới**.

Repository:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;
import com.couchbase.client.java.query.QueryScanConsistency;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    // Query theo JSON field; mặc định thường không buộc đợi index.
    List<OrderDocument> findByCustomerId(String customerId);

    // Chỉ áp dụng consistency mạnh hơn cho query cần thiết.
    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    List<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

Lớp service:

~~~java
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {
    private final OrderRepository orders;

    public OrderReadService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderDocument create(OrderDocument newOrder) {
        return orders.save(newOrder);
    }

    public OrderDocument detail(String fullDocumentId) {
        return orders.findById(fullDocumentId).orElseThrow();
    }

    public List<OrderDocument> createdHistory(String customerId) {
        return orders.findByCustomerIdAndStatus(
                customerId, "CREATED");
    }
}
~~~

Chính sách đọc **không nằm ở kiểu Java trả về**. Method `findById` đi KV theo key; derived query theo các field thường sinh SQL++. `@ScanConsistency` cho method query điều khiển scan consistency khi Spring Data hỗ trợ ở phiên bản đang chạy, không thay đường KV thành SQL++.

### 10.1. Đừng hỏi “tại sao cùng Repository mà khác kết quả?”

Hãy hỏi chính xác:

1. Method nào đã được gọi?
2. Có biết document ID không?
3. Generated SQL++ là gì?
4. Index và query plan nào được dùng?
5. Có đặt `@ScanConsistency`/query options không?
6. Có mutation mới hơn thay đổi field hoặc xóa document không?

Đây là chuỗi chẩn đoán có khả năng giải thích vấn đề hơn là chỉ thêm retry vào controller.

## 11. CouchbaseTemplate: chọn độ mới tại đúng truy vấn

Khi ứng dụng có query động theo nhiều điều kiện, `CouchbaseTemplate` giúp dùng Spring Data mapping nhưng vẫn kiểm soát query ở cấp gọi.

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
public class OrderHistoryDao {
    private final CouchbaseTemplate template;

    public OrderHistoryDao(CouchbaseTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> history(
            String customerId, QueryScanConsistency consistency) {

        Query orderQuery = query(where("customerId").is(customerId))
                .with(Sort.by(Sort.Direction.DESC, "createdAt"))
                .limit(20);

        return template.findByQuery(OrderDocument.class)
                .withConsistency(consistency)
                .matching(orderQuery)
                .all();
    }
}
~~~

Gọi với policy khác nhau:

~~~java
import static com.couchbase.client.java.query.QueryScanConsistency.NOT_BOUNDED;
import static com.couchbase.client.java.query.QueryScanConsistency.REQUEST_PLUS;

List<OrderDocument> ordinaryHistory =
        historyDao.history("c-1001", NOT_BOUNDED);

List<OrderDocument> freshHistory =
        historyDao.history("c-1001", REQUEST_PLUS);
~~~

Cùng một Template và index, nhưng hai **query request** có yêu cầu về thời điểm index bắt kịp khác nhau.

Ở các dòng API Spring Data Couchbase hỗ trợ, có thể đặt trực tiếp trên Query object:

~~~java
Query q = query(where("customerId").is("c-1001"))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
        .limit(20);

List<OrderDocument> rows =
        template.findByQuery(OrderDocument.class)
                .matching(q)
                .all();
~~~

**Không trộn hai policy mâu thuẫn** giữa `withConsistency(...)` và `Query.scanConsistency(...)` mà không có quy ước precedence rõ và integration test. Tạo Query object mới cho mỗi thao tác; đừng chia sẻ một Query mutable giữa request và thay consistency liên tục.

## 12. Java SDK: thể hiện rõ request_plus trong QueryOptions

Đối với SQL++ truy vấn ngoài Repository, SDK Java 3.x có cách cấu hình trực tiếp qua `QueryOptions.scanConsistency`.

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

public class OrderSqlppGateway {
    private final Cluster cluster;

    public OrderSqlppGateway(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult byCustomer(
            String customerId, boolean requireFreshIndex) {

        String sql = """
            SELECT META(o).id AS documentId,
                   o.customerId, o.status, o.createdAt
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            ORDER BY o.createdAt DESC
            LIMIT 20
            """;

        QueryScanConsistency consistency = requireFreshIndex
                ? QueryScanConsistency.REQUEST_PLUS
                : QueryScanConsistency.NOT_BOUNDED;

        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .scanConsistency(consistency);

        return cluster.query(sql, options);
    }
}
~~~

Những điểm cần phân biệt:

- `QueryScanConsistency` chỉ điều khiển **SQL++ query**, không thay thế KV get.
- Named parameter `$customerId` giúp tránh nối user input trực tiếp thành cú pháp SQL++.
- SDK trả kết quả SQL++ thô/rows, không tự dùng toàn bộ Spring Data converter cho entity.
- SDK query cần quyền truy cập đúng bucket/scope/collection và index hoạt động.
- Không tạo `Cluster.connect(...)` cho từng request; để Spring quản lý và tái sử dụng connection/client.

**Nếu query trả row không có Order mới dù REQUEST_PLUS đã hoàn thành**, kiểm tra `WHERE`, `LIMIT`, concurrent mutation, keyspace, type discriminator và quyền trước khi kết luận consistency “không có tác dụng”.

## 13. Khi cần mutation token: lưu đúng dấu mốc thay vì đếm mili giây

Câu hỏi đôi khi không phải “index đã theo kịp tất cả các ghi trước query chưa?” mà là “index đã thấy **ghi A và ghi B do chính request của tôi thực hiện** chưa?”.

Trong SDK, mutation result có thể cung cấp thông tin để tạo `MutationState` theo API/phiên bản. Mẫu bên dưới mô tả ý tưởng, **không phải code Java hoàn chỉnh độc lập**:

~~~java
// Pseudocode: các biến orders, id, body, cluster và sql đã được khai báo.

var result = orders.upsert(id, body);

// MutationState.from(...) biểu thị state từ mutation result
// theo API SDK tương ứng; kiểm tra chữ ký thực tế trước khi dùng.
var state = MutationState.from(result);

var rows = cluster.query(
        sql,
        QueryOptions.queryOptions()
                .consistentWith(state));
~~~

### 13.1. Token và CAS không đồng nghĩa

- **CAS** định danh trạng thái document cho conditional write / optimistic locking.
- **Mutation token/state** dùng để mô tả mốc mutation mà index phải bắt kịp.
- **Request timestamp** từ đồng hồ client không thay thế mutation state.
- **Transaction ID** cũng không tự đồng nghĩa với mutation token.

Nếu ghi qua Spring Data Repository mà không nhận được token từ abstraction, có thể dùng `REQUEST_PLUS` ở query cần freshness hoặc một SDK gateway cho luồng buộc giữ token. Khi dùng SDK trực tiếp, phải bảo đảm keyspace, schema, mapping, CAS và bảo mật phù hợp với các đường Spring Data khác.

### 13.2. Token không đòi trả đúng một phiên bản lịch sử

Nếu Order A đã ghi với status `CREATED` rồi một request khác cập nhật `CONFIRMED`, query consistent-with token A có thể thấy `CONFIRMED`. Nó yêu cầu index **không lùi trước mốc mutation A**, không yêu cầu query trả snapshot cố định của A.

## 14. Một luồng end-to-end có hợp đồng đọc sau ghi rõ ràng

Thay vì một service vừa save rồi luôn query lại lịch sử qua index, có thể thiết kế ranh giới API:

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant C as Spring Controller
    participant S as Order Service
    participant DB as Couchbase KV
    participant Q as SQL++ Query
    U->>C: POST /orders
    C->>S: createOrder(...)
    S->>DB: Save Order
    DB-->>S: ACK + Order metadata
    S-->>C: Saved Order representation
    C-->>U: 201 Created + orderId
    U->>C: GET /orders/{orderId}
    C->>DB: KV get theo ID
    DB-->>C: Order
    C-->>U: 200 Order
    U->>C: GET /customers/{id}/orders
    C->>Q: SQL++ với policy độ mới của danh sách
    Q-->>C: Rows
    C-->>U: Paginated order history
~~~

Tách API detail và API list đem lại hai lợi ích:

1. Trang xác nhận không cần phụ thuộc secondary index.
2. Trang lịch sử có thể tự định nghĩa SLO về độ mới, có policy retry/refresh thích hợp và được đo độc lập.

### 14.1. Nếu cùng một HTTP request ghi rồi truy vấn

Một service đồng bộ có thể làm:

~~~java
OrderDocument saved = orders.save(order);

// Nếu cần trả một document cụ thể:
return orders.findById(saved.getId()).orElseThrow();
~~~

Nếu business thực sự cần danh sách ngay sau ghi:

~~~java
OrderDocument saved = orders.save(order);

return historyDao.history(
        saved.getCustomerId(),
        QueryScanConsistency.REQUEST_PLUS);
~~~

Ở đoạn thứ hai, đợi index là một quyết định có chủ ý. Nó không cần thiết chỉ để xác nhận `save` đã thành công nếu kết quả `saved` đã có đầy đủ dữ liệu.

### 14.2. Nếu qua hai HTTP request

`POST` hoàn tất rồi trình duyệt gọi `GET` query danh sách. Service query không nhất thiết có mutation token của request `POST`. Lựa chọn `REQUEST_PLUS` có ích khi không truyền token xuyên request, nhưng có chi phí chờ index. Nếu ứng dụng quyết định ghép Order vừa tạo vào màn hình bằng response trước đó, cần tránh báo trạng thái “đã thanh toán” nếu payment workflow chưa hoàn tất.

## 15. Khi query vẫn không thấy Order dù index đã đủ mới

“Đọc sau ghi” chỉ có ý nghĩa khi dữ liệu vẫn **thỏa câu truy vấn**. Một query REQUEST_PLUS có thể đúng về consistency mà vẫn không chứa row mong muốn.

| Nguyên nhân | Minh họa |
| --- | --- |
| Sai `WHERE` | Order lưu `customerId = "c-1001"` nhưng query `"customer::c-1001"` |
| Sai keyspace | Ghi `shop.sales.orders`, query `shop._default._default` |
| Field khác kiểu | `createdAt` lưu numeric epoch, query so sánh string |
| `ORDER BY / LIMIT` | Order đúng nhưng nằm ngoài trang 20 kết quả |
| Type discriminator | Document SDK thô không có metadata mapping như Spring Data yêu cầu |
| Concurrent write | Order bị chuyển khách hàng, đổi status hoặc xóa sau lần ghi đầu |
| Tenant/authorization | Filter phân quyền loại document khỏi kết quả |
| Index/query lỗi | Query timeout hoặc index chưa online; đây là lỗi chứ không phải “0 rows” |
| Cache ngoài database | Application/CDN cache trả dữ liệu cũ thay vì query mới |
| Replica/region khác | Reader không truy cập cùng active data path/cluster |

**Quy trình xác minh:** lấy document theo ID trên nguồn có thẩm quyền, đối chiếu body mới nhất, xem generated SQL++ và `EXPLAIN`, kiểm tra index/query consistency, rồi mới điều chỉnh timeout hoặc retry.

## 16. Độ trễ chỉ mục khác với xung đột ghi và tính nguyên tử

### 16.1. CAS giải quyết lost update, không giải quyết index lag

~~~text
A đọc Order, CAS=C1
B đọc Order, CAS=C1
A sửa status và ghi thành công, CAS=C2
B ghi object cũ với CAS=C1 -> conflict nếu optimistic locking đúng
~~~

`@Version` trong entity giúp Spring Data dùng CAS cho optimistic locking. Đổi một query từ `NOT_BOUNDED` sang `REQUEST_PLUS` **không ngăn B ghi đè** nếu write path không kiểm tra CAS.

### 16.2. Transaction giải quyết nhóm thay đổi, không tự thay consistency của mọi index

Một đơn mới cần đồng thời tạo Order và trừ Inventory. Nếu hai document này phải cùng thành công hoặc cùng thất bại, phải xem xét transaction Couchbase phù hợp với SDK/Spring Data version hoặc workflow bù trừ. `REQUEST_PLUS` cho query lịch sử **không** làm hai lệnh `save` thành transaction.

Sau transaction commit, một SQL++ query bên ngoài vẫn cần hiểu Query Service/index semantics tương ứng. Không suy rằng mọi Search index hoặc cache đã cập nhật tức thì chỉ vì transaction đã commit.

### 16.3. Durability và index freshness là hai trục độc lập

Mutation với yêu cầu durability cao hơn có thể cần xác nhận replica/persistence tùy option. Điều đó không có nghĩa GSI cập nhật xong trong cùng ACK. Ngược lại, một query `REQUEST_PLUS` đợi index nhưng không thay đổi mức bền của mutation trước đó.

### 16.4. TTL là vòng đời document

TTL quyết định khi document hết hạn. Nó không phải option query consistency và không thể thay bằng `expiresAt` trong body nếu không có logic thực thi. Với session, luôn xác thực theo nguồn có thẩm quyền và trạng thái bảo mật chứ không lấy query index làm sự thật duy nhất.

## 17. Reactive pipeline: thứ tự subscribe và độ mới index

Trong WebFlux, repository có thể trả `Mono<OrderDocument>` hoặc `Flux<OrderDocument>`; việc dữ liệu được chuyển bằng Publisher **không thay đổi** thời điểm Index Service cập nhật.

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;
import com.couchbase.client.java.query.QueryScanConsistency;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    Flux<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

Ví dụ service muốn **lưu xong rồi mới query**:

~~~java
import reactor.core.publisher.Flux;

public Flux<OrderDocument> saveThenLoadCreated(
        OrderDocument newOrder) {

    return reactiveOrders.save(newOrder)
            .flatMapMany(saved ->
                    reactiveOrders.findByCustomerIdAndStatus(
                            saved.getCustomerId(), "CREATED"));
}
~~~

Ví dụ giả định `reactiveOrders` được inject. `flatMapMany` nối subscription query sau khi save phát ra saved entity thành công. Query được gắn `REQUEST_PLUS` để tăng khả năng nhìn thấy mutation qua SQL++ khi business cần.

Lỗi thường gặp:

~~~java
// Sai: gọi blocking Repository trước khi Mono được tạo.
Mono.just(syncRepository.findById(id));

// Sai: chặn event loop WebFlux để lấy giá trị.
reactiveRepository.findById(id).block();

// Dễ bỏ mất lỗi và vòng đời request:
reactiveRepository.save(order).subscribe();
~~~

Nếu dùng ReactiveCouchbaseTemplate, chọn `withConsistency(...)` trên fluent reactive query theo phiên bản hỗ trợ. `Flux`, backpressure và concurrency operators giúp điều phối I/O, nhưng **không sửa thiếu index**, không tạo transaction và không làm query `REQUEST_PLUS` không còn chi phí chờ.

## 18. Xử lý timeout và kết quả ghi chưa rõ

Một vấn đề khó hơn index lag là **write result ambiguous**. Giả sử client gửi insert rồi mất kết nối trước khi nhận response; database có thể đã ghi thành công, hoặc có thể chưa.

~~~text
T0: Client gửi tạo Order
T1: Data Service có thể đã thực thi mutation
T2: Network timeout trước khi client nhận ACK
T3: Client không biết kết quả cuối
T4: Client tự tạo ID mới và retry -> có nguy cơ tạo hai Order
~~~

Không dùng SQL++ `NOT_BOUNDED` để tìm xem “đã tạo chưa” rồi khẳng định không có record nếu query chưa trả row. Ngay cả `REQUEST_PLUS` cũng không giải quyết hết race condition tạo trùng dưới các request đồng thời.

### 18.1. Thiết kế idempotency

- Mỗi yêu cầu nghiệp vụ có **idempotency key** ổn định qua retry.
- Có mapping từ key đó tới kết quả Order hoặc quy tắc tạo document có điều kiện.
- Nếu response timeout, kiểm tra trạng thái nghiệp vụ theo **key có thẩm quyền**, không dựa trên một danh sách index có thể trễ.
- Khi mutation đã hoàn tất, retry cùng key trả lại kết quả hoặc lỗi theo hợp đồng, không tự động nhân đôi thanh toán/đơn hàng.
- Đặt giới hạn retry, backoff và xử lý các lỗi xung đột rõ ràng.

Nếu timeout xảy ra ở **query `REQUEST_PLUS`**, phải phân biệt query chỉ đọc không hoàn tất với mutation đã xảy ra trước đó; không tự gọi lại lệnh tạo Order chỉ vì query danh sách bị timeout.

## 19. Đo thời điểm index nhìn thấy mutation trong thực tế

Bản thân độ trễ index là một thuộc tính **quan sát được**, không phải một hằng số nên hard-code. Đo trong môi trường test với lượng ghi, số index và phần cứng đại diện.

### 19.1. Một thí nghiệm an toàn

1. Tạo Order với ID ngẫu nhiên, customerId riêng cho test.
2. Gửi mutation bằng KV, ghi lại thời điểm client nhận ACK.
3. Đọc lại theo ID bằng KV để xác minh document đã tồn tại.
4. Gọi SQL++ `NOT_BOUNDED` theo customerId và ghi nhận xem kết quả đã chứa Order chưa. **Không ép kết quả phải thiếu.**
5. Nếu muốn ước lượng thời gian đến lúc query mặc định thấy Order, có thể quan sát bằng các lần query có khoảng nghỉ/giới hạn, nhưng thời điểm phát hiện chỉ là **một mẫu đo** bị ảnh hưởng bởi lịch polling.
6. Gọi SQL++ `REQUEST_PLUS` và xác minh Order xuất hiện khi query thành công, không có mutation cạnh tranh và filter/page cho phép.
7. Ghi latency, error rate, Query Service/Index Service metrics và cleanup fixture.
8. Lặp với nhiều mutation rate, index state và concurrency khác nhau.

### 19.2. Tránh phép đo đánh lừa

Nếu query NOT_BOUNDED đầu tiên đã thấy Order, bạn **không thể suy ra index lag = 0**; chỉ biết index đã đủ mới tại thời điểm quét đó. Nếu query sau thấy Order ở mốc 20 ms, không thể suy ra mutation thực sự được index hóa chính xác ở 20 ms — nó có thể xảy ra sớm hơn.

`REQUEST_PLUS` chờ index và cho phép xác minh **hợp đồng đọc**; không phải đồng hồ đo trực tiếp latency nội bộ của mọi mutation.

### 19.3. Metric nên theo dõi

| Metric | Câu hỏi vận hành |
| --- | --- |
| KV write ACK latency p95/p99 | Mutation được xác nhận nhanh tới đâu? |
| KV get latency | Đọc lại theo key có chậm không? |
| SQL++ query latency p50/p95/p99 | Người dùng đợi bao lâu cho danh sách? |
| Scan consistency mode theo endpoint | Bao nhiêu request đang buộc đợi index? |
| Index mutation backlog / index lag | Index Service có theo kịp tốc độ ghi? |
| Query timeout/error rate | Query có thường xuyên vượt ngân sách? |
| Index/Query/Data Service CPU, memory, disk | Nút thắt nằm ở dịch vụ nào? |
| CAS conflict count | Có nhiều ghi cạnh tranh cùng document? |
| Retry count và idempotency conflicts | Retry có khuếch đại tải/đơn trùng? |

Không log credential, session token hoặc dữ liệu cá nhân đầy đủ. Dùng correlation ID/request ID và che/hàm băm ID theo chính sách bảo vệ thông tin của hệ thống.

## 20. Integration test: xác minh read-after-write mà không flaky

Mock `OrderRepository` không kiểm tra được Index Service. Integration test cần Couchbase thật hoặc môi trường tương đương, collection và index đã online, cùng cấu hình ứng dụng phù hợp.

### 20.1. Test minh họa bằng Spring Boot và SDK

Test này tạo một Order **qua KV**, rồi truy vấn SQL++ `REQUEST_PLUS` để xác minh một ACK insert trước mốc query đã được index phản ánh.

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import static org.junit.jupiter.api.Assertions.assertEquals;
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
class ReadAfterWriteConsistencyIT {
    @Autowired
    private Cluster cluster;

    @Test
    void requestPlusSeesAcknowledgedKvInsert() {
        Collection collection = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");

        String id = "order::it-" + UUID.randomUUID();
        String customerId = "it-customer-" + UUID.randomUUID();

        boolean confirmedInserted = false;
        try {
            collection.insert(id, JsonObject.create()
                    .put("customerId", customerId)
                    .put("status", "CREATED"));
            confirmedInserted = true;

            // KV: đọc theo ID, không cần secondary index.
            assertEquals(customerId,
                    collection.get(id)
                            .contentAsObject()
                            .getString("customerId"));

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
            if (confirmedInserted) {
                collection.remove(id);
            }
        }
    }
}
~~~

Đây là cấu trúc **integration test có phụ thuộc môi trường**:

- Phải chuẩn bị bucket/scope/collection, quyền và index phù hợp trước khi chạy.
- Một test dùng SDK thô **không tự thêm type discriminator** của Spring Data; đó là chủ ý để kiểm tra SQL++ và index. Khi test Repository mapping, cần dùng entity/JSON khớp converter.
- Nếu insert thực sự đã commit nhưng client không nhận ACK, biến `confirmedInserted` sẽ không được bật. Suite thật nên có cleanup fixture riêng để xử lý write ambiguous.
- Nếu cleanup thất bại, test fixture còn lại không được phép làm sai các test sau; dùng customerId ngẫu nhiên giúp giảm va chạm, nhưng không thay cleanup.
- Nếu cluster có thao tác cập nhật khác lên document giữa write và query, hợp đồng expected rows phải được điều chỉnh.
- Không chạy test tạo/xóa dữ liệu như trên trong production.

### 20.2. Test sai cần tránh

~~~text
Insert Order
Immediately query NOT_BOUNDED
assert query KHÔNG chứa Order
~~~

Test này flaky: index có thể đã xử lý mutation. `NOT_BOUNDED` cho phép đọc kết quả trước khi index bắt kịp, **không yêu cầu index cố tình lạc hậu**.

### 20.3. Test đúng phải kiểm chứng điều đã hứa

- `REQUEST_PLUS` query thành công với filter khớp sau insert ACK → phải có đường giải thích rằng index đã bắt kịp mốc query.
- `NOT_BOUNDED` → ghi nhận kết quả/latency, không buộc có lag.
- `findById` → xác minh document theo active KV path khi mutation đã được xác nhận.
- CAS → kiểm tra conflict trên ghi cạnh tranh **trong test độc lập**.
- Transaction → kiểm tra ranh giới commit/rollback độc lập.
- Reactive → kiểm tra subscription, timeout và không blocking riêng.

## 21. Chẩn đoán sự cố “vừa ghi rồi chưa thấy”

~~~mermaid
flowchart TD
    A["Báo lỗi: vừa ghi nhưng chưa thấy"] --> B{"Lệnh ghi đã nhận ACK thành công?"}
    B -->|Không hoặc timeout| C["Kiểm tra ambiguous write / idempotency"]
    B -->|Có| D{"Đang đọc theo exact document ID?"}
    D -->|Có| E["Xác nhận active/replica, cache, đúng keyspace"]
    D -->|Không| F["Kiểm tra generated SQL++ hoặc Search query"]
    F --> G{"Index/query plan và filter có đúng?"}
    G -->|Không| H["Sửa index, WHERE, LIMIT, tenant, mapping"]
    G -->|Có| I["Xem NOT_BOUNDED / REQUEST_PLUS / token policy"]
    I --> J["Đo index lag, query latency và timeout"]
    E --> J
    C --> J
~~~

Bảng triệu chứng:

| Triệu chứng | Chẩn đoán đầu tiên | Giải pháp có thể phù hợp |
| --- | --- | --- |
| KV đọc được Order, SQL++ list chưa thấy | Index freshness, query policy | REQUEST_PLUS nếu cần hoặc dùng saved Order |
| SQL++ REQUEST_PLUS chậm nhiều | Index backlog, Index Service tải cao | Đo, tối ưu index/capacity và chọn policy |
| REQUEST_PLUS cũng không ra Order | WHERE, LIMIT, keyspace, mapping, concurrent mutation | Sửa query/logic, không retry mù |
| SQL++ báo thiếu index | Index online, query plan, quyền | Tạo/sửa index, EXPLAIN |
| Cập nhật status nhưng list theo status lạ | Index membership lag hoặc fetch/covering plan | Kiểm tra source KV, scan consistency |
| KV đọc giá trị cũ ở vùng khác | Replica/cross-cluster path hoặc cache | Xác nhận topology và semantics nguồn đọc |
| Xóa session nhưng Search vẫn thấy hit | Search index lag | Không xác thực session bằng Search |
| Ghi tạo đơn bị timeout rồi có hai đơn | Retry thiếu idempotency | Dùng key ổn định và conditional creation |
| Hai người cùng sửa Order, một ghi đè | Thiếu CAS/optimistic locking | Dùng `@Version`, xử lý conflict |

## 22. Bài tập thực hành

### Bài tập A — Màn hình xác nhận Order

API tạo Order vừa trả `201` và `orderId`. Trang xác nhận chỉ cần thông tin của đúng đơn đó.

**Hỏi:** Có cần gọi SQL++ `REQUEST_PLUS` theo `customerId` không?

**Hướng giải:** Không cần. Dùng saved entity/response hoặc KV theo document ID. Chỉ query index nếu thật sự cần danh sách nhiều Order.

### Bài tập B — Danh sách phải có Order vừa tạo

Product yêu cầu rằng sau `POST /orders`, `GET /customers/{id}/orders` phải có đơn mới nếu nó thuộc filter và 20 đơn mới nhất.

**Hỏi:** Cấu hình nào phù hợp?

**Hướng giải:** SQL++ với `REQUEST_PLUS` hoặc mutation state/token khi API hỗ trợ; kiểm tra `WHERE`, `ORDER BY`, `LIMIT` và ngân sách timeout. Có thể cân nhắc UX hiển thị Order mới ngay từ response trong khi danh sách load riêng.

### Bài tập C — Cập nhật trạng thái

A cập nhật `CREATED → CONFIRMED`. B vẫn giữ một Order object cũ và gọi `save`. B vừa chạy query `REQUEST_PLUS` theo status trước khi ghi.

**Hỏi:** Điều gì ngăn B ghi đè A?

**Hướng giải:** CAS/`@Version` hoặc conditional write; REQUEST_PLUS chỉ yêu cầu index scan đủ mới, không bảo vệ đường ghi.

### Bài tập D — Email duy nhất

Hai request cùng query email, đều chưa thấy kết quả rồi tạo hai Customer khác key.

**Hỏi:** Đổi query từ NOT_BOUNDED sang REQUEST_PLUS có đủ không?

**Hướng giải:** Không. Check-then-insert vẫn có race. Cần cơ chế uniqueness trên đường ghi: key/record ánh xạ, insert có điều kiện và/hoặc transaction phù hợp.

### Bài tập E — Test index lag

Bạn viết test yêu cầu query NOT_BOUNDED phải chưa thấy document mới ít nhất một lần.

**Hỏi:** Test có đáng tin không?

**Hướng giải:** Không; thời điểm index bắt kịp không deterministic. Test REQUEST_PLUS trên mutation đã ACK và quan sát latency/index lag bằng đo đạc khác.

### Bài tập F — WebFlux đọc sau ghi

Một developer gọi `reactiveOrders.save(order).subscribe()` rồi ngay lập tức gọi một query khác ở method trả HTTP response.

**Hỏi:** Có bảo đảm save hoàn tất trước query không?

**Hướng giải:** Không nếu hai pipeline độc lập và tự subscribe không được điều phối. Dùng `flatMap`/`thenMany` để nối thứ tự completion và chọn scan consistency riêng khi query dựa vào index.

## 23. Checklist review thiết kế trước khi triển khai

- [ ] Đã xác định đường read sau write là KV, SQL++, Search, replica hay cache?
- [ ] Document ID, bucket, scope, collection ở write và read có trùng đúng không?
- [ ] Có phân biệt ACK write với secondary index visibility?
- [ ] Query theo field có index phù hợp và query plan được xem bằng `EXPLAIN`?
- [ ] API đã biết ID có tránh query qua index không cần thiết?
- [ ] Với SQL++, SLO độ mới cho từng endpoint được diễn đạt rõ?
- [ ] `NOT_BOUNDED` chỉ dùng khi ứng dụng chấp nhận độ trễ index?
- [ ] `REQUEST_PLUS` chỉ dùng khi cần, với timeout và đo latency phù hợp?
- [ ] Nếu cần thấy các mutation cụ thể, có API token/state phù hợp và cách truyền token an toàn?
- [ ] `WHERE`, `ORDER BY`, `LIMIT`, projection, tenant filter và type discriminator đã được xác minh?
- [ ] Read-after-write qua KV có tránh replica/cache stale không?
- [ ] CAS, transaction, durability, TTL và Search consistency được xem là các vấn đề độc lập?
- [ ] Ghi bị timeout có idempotency và cách xác minh trạng thái, không tạo trùng đơn?
- [ ] Reactive pipeline điều phối save/query đúng thứ tự, không block/subscribe sai?
- [ ] Integration test không ép NOT_BOUNDED luôn stale và có fixture cleanup?
- [ ] Có metric KV latency, index backlog, query latency và timeout theo endpoint?
- [ ] Logging/tracing có đủ correlation ID mà không lộ bí mật?

## 24. Kết luận

**Read-after-write trong Couchbase phải được giải thích theo đường truy cập.** Một KV mutation thành công có thể được đọc lại theo document ID trên active KV path mà **không cần chờ secondary index**. Trong khi đó, SQL++ query theo field thường sử dụng index được cập nhật từ mutation, vì vậy một query `NOT_BOUNDED` có thể chưa nhìn thấy thay đổi mới nhất ở thời điểm quét.

Giải pháp không phải bật `REQUEST_PLUS` cho mọi truy vấn. Hãy **trả saved entity hoặc dùng KV khi đã biết key**, chỉ yêu cầu index bắt kịp ở những SQL++ query có SLO độ mới thực sự, cân nhắc mutation token khi API hỗ trợ và đo chi phí chờ trong production. Đồng thời, giữ ranh giới rõ giữa **index freshness, CAS, TTL, durability, transaction, replica reads, reactive scheduling và idempotency**. Khi đó, tầng truy cập **Spring Data Couchbase** vừa có tính đúng đắn nghiệp vụ, vừa kiểm soát được độ trễ và khả năng vận hành.
