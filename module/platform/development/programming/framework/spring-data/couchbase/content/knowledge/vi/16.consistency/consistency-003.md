# Cấu hình @ScanConsistency cho repository trong Spring Data Couchbase

## 1. Mục tiêu bài học

Trong **Spring Data Couchbase**, một Repository có thể cung cấp cả thao tác **đọc theo document ID** và các phương thức **truy vấn SQL++ theo field JSON**. Hai đường truy cập này không sử dụng cùng cơ chế tìm dữ liệu: đọc theo ID thường đi qua dịch vụ **Key–Value (KV)**, còn query theo field thường dựa trên **secondary index**. Vì index được cập nhật từ những thay đổi dữ liệu, một truy vấn mặc định có thể chưa nhìn thấy mutation vừa hoàn tất.

Annotation **`@ScanConsistency`** cho phép cấu hình độ mới cần thiết cho **query do Repository thực thi**. Cách viết quan trọng là:

~~~java
@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
~~~

Ở đây, `ScanConsistency` thuộc Spring Data Couchbase Repository, còn `QueryScanConsistency` là enum thuộc Couchbase Java SDK. Chỉ cần đặt annotation là chưa đủ để có hệ thống nhất quán đúng: người học còn phải biết thao tác nào thực sự đi SQL++, chỉ mục nào được quét và chi phí đợi index.

Bài học thuộc chương **Tính nhất quán** của module **SPRING_DATA_COUCHBASE**. Sau khi học, bạn có thể:

- Import đúng annotation `@ScanConsistency` và sử dụng thuộc tính `query`.
- Chọn `NOT_BOUNDED` hoặc `REQUEST_PLUS` cho **từng repository query** dựa trên yêu cầu nghiệp vụ.
- Giải thích vì sao đặt annotation trên `findById` không biến KV thành SQL++.
- Biết trường hợp có thể cấu hình trên method, repository type hoặc entity `@Document(queryScanConsistency = ...)` và đánh đổi của phạm vi rộng.
- Kết hợp cấu hình với index SQL++, bucket/scope/collection, `@Query`, Repository đồng bộ và Reactive Repository.
- Xây integration test **không giả định index luôn trễ**, quan sát độ trễ và xử lý các nguyên nhân khác khiến query không trả row.
- Phân biệt scan consistency với CAS, TTL, durability, transaction và consistency của Search/Analytics.

## 2. Bài toán mở đầu: đã lưu đơn nhưng repository tìm chưa ra

Giả sử ứng dụng đặt hàng ghi document vào:

~~~text
Bucket: shop
Scope: sales
Collection: orders
Document ID: order::o-1001
~~~

JSON body minh họa:

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 350000
}
~~~

Service gọi hai method sau ngay sau khi tạo đơn:

~~~java
OrderDocument saved = orders.save(order);

Optional<OrderDocument> detail =
        orders.findById(saved.getId());

List<OrderDocument> history =
        orders.findByCustomerId("c-1001");
~~~

- `findById` biết **metadata key** và thông thường sử dụng KV; không cần secondary index theo `customerId`.
- `findByCustomerId` tìm **tập document qua field JSON**, thường sinh SQL++ và dùng secondary index.
- Nếu query SQL++ chạy với scan consistency mặc định `NOT_BOUNDED`, index có thể chưa cập nhật xong mutation của `save`, nên `history` có thể chưa chứa Order mới.

~~~mermaid
flowchart TB
    SAVE["repository.save(order)"] --> DATA[("Data Service: document đã ghi")]
    DATA --> KV["findById: KV theo ID"]
    DATA --> STREAM["Mutation được chuyển tới Index Service"]
    STREAM --> INDEX[("Secondary index")]
    INDEX --> SQL["findByCustomerId: SQL++"]
    KV --> NEW["Có thể đọc document vừa ghi"]
    SQL --> STALE["Có thể chưa thấy mutation nếu index còn trễ"]
~~~

**Không có quy tắc rằng NOT_BOUNDED luôn trả stale data.** Trên một cluster nhàn, index có thể bắt kịp ngay trước lần query đầu. Vấn đề là ứng dụng **không yêu cầu** Query Service đợi index đủ mới.

## 3. Hai chế độ scan consistency cần nắm

| Thuộc tính | `NOT_BOUNDED` | `REQUEST_PLUS` |
| --- | --- | --- |
| Nguyên tắc | Không chủ động đợi index đạt mốc mutation mới của request trước scan | Đợi index liên quan theo kịp mốc consistency khi query bắt đầu |
| Kết quả ngay sau insert | Có thể thiếu document vừa insert | Có cơ sở để nhìn thấy mutation đã hoàn tất trước mốc request nếu query hợp lệ và index hoạt động |
| Kết quả ngay sau update/xóa | Có thể bị ảnh hưởng bởi index chưa bắt kịp | Index phải bắt kịp mốc yêu cầu trước khi scan |
| Thời gian chờ index | Thường thấp hơn | Có thể tăng khi Index Service đang trễ |
| Tình huống phù hợp | Danh sách/báo cáo chấp nhận trễ ngắn | Query theo field bắt buộc phản ánh các ghi đã xác nhận trước request |
| Có tạo index thiếu? | Không | Không |
| Có bảo vệ lost update? | Không | Không |
| Có tạo transaction? | Không | Không |

**`REQUEST_PLUS` không phải “đọc mọi thứ dưới khóa toàn cục”**. Nó đặt ràng buộc lên **độ tiến của index cho query**, không chặn các mutation mới sau khi query bắt đầu và không tạo snapshot lịch sử cố định.

Mặt khác, `NOT_BOUNDED` không hề yêu cầu trả dữ liệu cũ; nó chỉ **không bảo đảm index phải chờ**. Vì thế kiểm thử không nên assert một truy vấn NOT_BOUNDED bắt buộc thiếu document.

### 3.1. Timeline minh họa

~~~text
T0: Save Order mới -> KV write được xác nhận
T1: KV get(key) -> thấy Order
T2: Index theo customerId còn chưa phản ánh mutation
T3: Query NOT_BOUNDED -> có thể thiếu Order
T4: Query REQUEST_PLUS -> đợi index đạt mốc query
T5: Index bắt kịp mutation
T6: Query REQUEST_PLUS -> kết quả theo điều kiện truy vấn
~~~

Nếu sau T0 document đã bị thay đổi hoặc xóa, query ở T6 có thể phản ánh phiên bản sau cùng; `REQUEST_PLUS` không buộc trả một trạng thái `CREATED` cố định tại T0.

## 4. @ScanConsistency: gói import, thuộc tính và phạm vi annotation

Đây là phần khác biệt giữa **annotation Spring Data** và **option SDK**:

~~~java
import org.springframework.data.couchbase.repository.ScanConsistency;
import com.couchbase.client.java.query.QueryScanConsistency;
~~~

Spring Data Couchbase công bố annotation trong gói:

~~~text
org.springframework.data.couchbase.repository.ScanConsistency
~~~

Annotation có thể gắn ở **method**, **annotation type** hoặc **type** theo API, với các thuộc tính:

| Thuộc tính | Kiểu | Mặc định | Mục đích |
| --- | --- | --- | --- |
| `query` | `QueryScanConsistency` | `NOT_BOUNDED` | Mức scan consistency cho **SQL++/Query Service** |
| `analytics` | `AnalyticsScanConsistency` | `NOT_BOUNDED` | Mức consistency cho **Analytics** API, không phải SQL++ thông thường |

Để cấu hình **repository SQL++**, phải dùng `query`:

~~~java
@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
~~~

Không nhầm với một annotation không tồn tại ở package JPA hoặc cú pháp tự đặt như:

~~~java
// SAI: Không phải cú pháp @ScanConsistency được minh họa.
@ScanConsistency(value = "REQUEST_PLUS")
~~~

Không cần cấu hình `analytics` nếu nghiệp vụ chỉ truy vấn SQL++ qua Repository. **Search/FTS** dùng Search index riêng và có cơ chế consistency riêng; không tự chịu ảnh hưởng từ `query` của annotation này.

### 4.1. Tại sao dùng enum của Java SDK?

Spring Data Couchbase hoạt động dựa trên Couchbase Java SDK. Trên đường SQL++, framework chuyển yêu cầu truy vấn và các option phù hợp xuống client SDK. Sử dụng enum `com.couchbase.client.java.query.QueryScanConsistency` giúp tránh tự quy ước string policy không khớp tên API.

### 4.2. Đối chiếu phiên bản

Các ví dụ trong bài sử dụng hình thức API của các dòng Spring Data Couchbase hiện đại với Java SDK 3.x. Khi triển khai, hãy xác minh bộ phiên bản **Java – Spring Boot – Spring Data Couchbase – Couchbase Java SDK – Couchbase Server** thực sự hỗ trợ các annotation, operation và mapping đang dùng. Không tự thêm version SDK khác BOM của Spring Boot chỉ để sửa lỗi import mà chưa kiểm tra compatibility.

## 5. Chuẩn bị entity và kết nối để minh họa

Ví dụ Gradle trong Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
}
~~~

Cấu hình kết nối minh họa:

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

Thay placeholder bằng credential qua secret/environment; không commit username/password thật vào repository code. Bucket/scope/collection và tài khoản có quyền phù hợp phải được tạo từ trước. Cấu hình bucket **không tự chọn `sales.orders`**; cần ánh xạ scope và collection cho entity theo đúng phiên bản.

Entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

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
    public void setVersion(Long version) { this.version = version; }
}
~~~

Giải thích:

- `@Id` biểu diễn document key metadata, ví dụ `order::o-1001`.
- `@Field` ánh xạ thuộc tính Java vào JSON.
- `@Version` hỗ trợ optimistic locking theo CAS; **không liên quan trực tiếp đến scan consistency**.
- `createdAt` được lưu trong JSON theo định dạng UTC ISO 8601 trong ví dụ; muốn sắp xếp đáng tin cậy phải thống nhất cách lưu trên mọi document.
- Spring Data có thể lưu type discriminator như `_class` tùy mapping; query generated và index nên được kiểm tra dựa trên JSON thật.

## 6. Gắn @ScanConsistency trên một derived query

Đây là cách nên bắt đầu: **đánh dấu chỉ những query cần thấy index đủ mới**, không bật rộng cho mọi use case.

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;
import com.couchbase.client.java.query.QueryScanConsistency;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    // Query theo field; nếu không override, thường NOT_BOUNDED.
    List<OrderDocument> findByCustomerId(String customerId);

    // Dành cho màn hình bắt buộc thấy ghi đã xác nhận.
    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    List<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

Ở ví dụ này:

- `findByCustomerId` dùng derived query theo `customerId` và thông thường nhận consistency mặc định.
- `findByCustomerIdAndStatus` yêu cầu `REQUEST_PLUS` khi được thực thi như query SQL++; nó vẫn cần index đáp ứng điều kiện.
- `findById` từ `CouchbaseRepository` vẫn là thao tác theo key trong trường hợp bình thường, không phải query SQL++.
- Annotation không tạo transaction, không sửa JSON và không điều chỉnh durability của một lệnh `save`.

### 6.1. Chọn method theo ý nghĩa nghiệp vụ

Đặt tên method không chỉ phản ánh field mà còn phản ánh mục đích:

~~~java
@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
List<OrderDocument> findByCustomerIdAndStatus(
        String customerId, String status);
~~~

Nếu chỉ một endpoint bắt buộc query có consistency mạnh hơn, có thể tách interface hoặc custom repository để không làm mọi query cùng `customerId` đều phải chờ index. Tránh thêm nhiều method gần giống nhau nhưng không ghi rõ lý do khác biệt consistency; đây là một quyết định nghiệp vụ và SLO cần được tài liệu hóa.

### 6.2. Có nên gắn @ScanConsistency trên findById?

Không nên coi đó là cách “làm cho findById mới hơn”. Với Repository, `findById` thường đi **KV**, nên scan consistency của **SQL++ index** không phải cơ chế quyết định độ mới của lời gọi đó. Annotation không tự biến KV get thành query index.

Thay vì:

~~~java
// Không có ích cho mục tiêu làm mới một KV get thông thường:
@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
Optional<OrderDocument> findById(String id);
~~~

hãy xác định đúng **đường đọc**. Nếu biết document ID vừa ghi, đọc KV theo key hoặc sử dụng entity kết quả của `save` thường đơn giản hơn. Trong môi trường có replica read, cache hay cross-cluster replication, cần nghiên cứu freshness của từng đường đó riêng.

## 7. Gắn annotation trên method findAll được kế thừa

Một điểm dễ bỏ qua: không chỉ custom derived query mới có thể sinh SQL++. Một thao tác như `findAll()` có thể cần query toàn bộ tập document theo type và index.

Tài liệu Spring Data Couchbase mô tả cách **override method được kế thừa** để thêm annotation. Ví dụ dạng repository dựa trên `CrudRepository`:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;
import com.couchbase.client.java.query.QueryScanConsistency;

public interface OrderFindAllRepository
        extends CrudRepository<OrderDocument, String> {

    @Override
    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    Iterable<OrderDocument> findAll();
}
~~~

Đây là ví dụ **phương pháp** thêm annotation vào inherited repository query, không phải khuyến nghị đưa `findAll()` không giới hạn lên endpoint production.

**Cảnh báo:** Trả toàn bộ Order có thể gây quét và truyền dữ liệu rất lớn; consistency cao **không** thay thế `WHERE`, `LIMIT`, phân trang hoặc chỉ mục được thiết kế đúng. Nếu dự án đang sử dụng một base repository cung cấp return type khác (ví dụ `List<T>` thay `Iterable<T>`), phải override bằng chữ ký/return type tương thích với đúng phiên bản.

## 8. Cấu hình trên repository type và @Document

Annotation có `@Target(TYPE)` nên về mặt API có thể gắn trên kiểu repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;
import com.couchbase.client.java.query.QueryScanConsistency;

@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
public interface FreshOrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerId(String customerId);
}
~~~

Nhưng hãy cân nhắc **phạm vi rộng**:

- Các SQL++ query thuộc Repository có thể phải đợi index dù không phải mọi endpoint đều cần độ mới đó.
- Phương thức KV theo ID không biến thành query chỉ vì annotation gắn trên type.
- Khi dùng inheritance, meta-annotations hoặc cấu hình entity khác nhau, cần xác minh cách resolve annotation và mức ưu tiên trong phiên bản đang chạy bằng integration test.

Spring Data Couchbase cũng có thuộc tính của entity `@Document` để cấu hình mặc định ở mức kiểu dữ liệu:

~~~java
import org.springframework.data.couchbase.core.mapping.Document;
import com.couchbase.client.java.query.QueryScanConsistency;

@Document(queryScanConsistency =
        QueryScanConsistency.REQUEST_PLUS)
public class InventoryDocument {
    // Mapping entity và các field...
}
~~~

Ở các phiên bản hỗ trợ, `queryScanConsistency` là **alias** của thuộc tính `query` trong `@ScanConsistency`. Đây là lựa chọn có phạm vi rộng: query cho entity có thể dùng mức consistency được khai báo, tùy Spring Data operation và metadata hiện hành.

**Nguyên tắc quản lý:** ưu tiên khai báo **trên method** khi yêu cầu chỉ thuộc một use case; dùng entity/repository-wide policy khi mọi query liên quan thật sự có cùng SLO độ mới. Đừng giả định chính xác thứ tự ưu tiên giữa method, repository type, entity annotation và tùy chọn runtime mà chưa đối chiếu phiên bản và test tình huống xung đột.

## 9. @ScanConsistency cùng @Query viết SQL++ thủ công

Repository có thể sử dụng `@Query` để định nghĩa SQL++ thay vì chỉ derived query. Khi đó, nếu method chạy qua Query Service và được Spring Data hỗ trợ như một repository query, có thể cấu hình scan consistency tương tự.

Ví dụ minh họa cấu trúc:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.couchbase.repository.ScanConsistency;
import com.couchbase.client.java.query.QueryScanConsistency;

public interface OrderQueryRepository
        extends CouchbaseRepository<OrderDocument, String> {

    @Query("#{#n1ql.selectEntity} WHERE " +
           "#{#n1ql.filter} AND customerId = $1")
    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    List<OrderDocument> findOrdersForCustomer(String customerId);
}
~~~

`#{#n1ql.selectEntity}` và `#{#n1ql.filter}` giúp Spring Data xây câu query có đủ metadata cần thiết cho entity mapping/type filter theo cấu hình. Tham số `$1` trong minh họa là một cách binding positional parameter của câu SQL++ được Spring Data hỗ trợ theo version; xác minh generated SQL++ và kết quả với đúng bộ thư viện đang dùng.

**Không tự viết**:

~~~java
// Không an toàn: ghép input người dùng thành SQL++.
String sql = "SELECT * FROM orders WHERE customerId = '"
        + customerId + "'";
~~~

Query parameter binding tránh injection và giúp tách giá trị khỏi cấu trúc câu lệnh. `@ScanConsistency` chỉ điều khiển index freshness; nó không làm phép query string concatenation trở nên an toàn.

### 9.1. Khi nào không nên dùng @Query?

Nếu `findByCustomerIdAndStatus` đã diễn đạt rõ điều kiện, derived query thường dễ bảo trì hơn. `@Query` hữu ích khi cần truy vấn/phép chiếu cụ thể; không nhất thiết dùng nó chỉ để gắn `@ScanConsistency`.

## 10. Cần tạo secondary index trước khi kiểm chứng consistency

Trong ví dụ Order, giả sử query cần lọc theo `customerId` và `status`, rồi sắp xếp theo ngày:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Một index khởi đầu:

~~~sql
CREATE INDEX ix_orders_customer_status_date
ON `shop`.`sales`.`orders`(customerId, status, createdAt DESC);
~~~

Cần chú ý:

1. Index này là **ví dụ thiết kế ban đầu**. Query generated từ Repository có thể thêm điều kiện về discriminator `_class` và projection cần CAS/metadata; kiểm tra kế hoạch thật.
2. `@ScanConsistency(query = REQUEST_PLUS)` **không tạo index**. Query thiếu index có thể lỗi hoặc chậm tùy kế hoạch.
3. `ORDER BY`, `LIMIT` và projection ảnh hưởng chi phí query. Yêu cầu index đủ mới không tự sửa một query quét quá nhiều row.
4. Nếu dữ liệu ngày giờ được lưu bằng chuỗi, cần chuẩn hóa UTC/ISO 8601 để so sánh/sắp xếp có ý nghĩa.
5. Tài khoản runtime cần quyền đọc/Query phù hợp; thao tác quản trị index nên được tách khỏi quyền ứng dụng khi có thể.

Dùng `EXPLAIN` để phân tích query:

~~~sql
EXPLAIN
SELECT META(o).id AS documentId, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = "c-1001"
  AND o.status = "CREATED"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Nếu query không dùng đúng index hoặc phải sort/fetch diện rộng, cải thiện query plan trước khi quy lỗi performance cho `REQUEST_PLUS`.

## 11. Lựa chọn theo use case: giữ consistency là quyết định sản phẩm

| Tình huống | Có sẵn document ID? | Đường truy cập | Policy thường phù hợp |
| --- | --- | --- | --- |
| Hiển thị Order vừa tạo trên trang xác nhận | Có | Entity đã `save` hoặc KV `findById` | Không cần `@ScanConsistency` chỉ để đọc một ID |
| Lịch sử đơn phải chứa đơn vừa lưu ngay | Không biết toàn bộ ID danh sách | SQL++ theo `customerId` | Cân nhắc `REQUEST_PLUS` cho method query đó |
| Báo cáo tổng hợp cập nhật định kỳ | Không | SQL++/aggregate | `NOT_BOUNDED` nếu SLO cho phép |
| Tìm đơn theo status sau thao tác xác nhận | Query theo field | SQL++ | `REQUEST_PLUS` nếu bắt buộc nhìn thấy thay đổi trước mốc query |
| Thử xác nhận một Order khi hai người cùng sửa | Có Order ID | KV read + CAS/conditional write | CAS, không dùng scan consistency thay thế |
| Kiểm tra email có duy nhất trước khi tạo | Theo email | Query hỗ trợ UX, ghi cần bảo vệ riêng | Query mới hơn vẫn chưa đủ bảo đảm uniqueness |
| Liệt kê session để quản trị | Query theo field | SQL++ | Policy tùy SLO |
| Quyết định session còn hợp lệ để xác thực | Có session token/key | KV + expiry/revocation | Không dùng query index trễ làm nguồn duy nhất |

Nếu người dùng vừa tạo đơn, **trả ngay biểu diễn đã lưu và Order ID** thường tránh một query phụ tốn kém. Chỉ yêu cầu `REQUEST_PLUS` cho danh sách khi trải nghiệm hoặc nghiệp vụ thực sự cần.

### 11.1. Phân biệt “đã ghi” với “phải xuất hiện trong LIMIT”

Ngay cả khi index đã đủ mới, một Order có thể không nằm trong kết quả `LIMIT 20` vì có nhiều Order mới hơn, do filter tenant/status, hoặc vì `ORDER BY` khác kỳ vọng. Đừng coi một row thiếu là bằng chứng `@ScanConsistency` không hoạt động khi chưa kiểm tra query semantics.

## 12. Service đồng bộ: read-your-write theo cách đúng

Giả sử Repository có method đã gắn annotation:

~~~java
@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
List<OrderDocument> findByCustomerIdAndStatus(
        String customerId, String status);
~~~

Service:

~~~java
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {

    private final OrderRepository orders;

    public OrderReadService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderDocument createOrder(OrderDocument newOrder) {
        return orders.save(newOrder);
    }

    public OrderDocument getByKey(String orderId) {
        return orders.findById(orderId)
                .orElseThrow();
    }

    public List<OrderDocument> latestCreatedForCustomer(
            String customerId) {
        return orders.findByCustomerIdAndStatus(
                customerId, "CREATED");
    }
}
~~~

Ở đây `createOrder` chỉ lưu một document. Để xử lý response HTTP, service nên trả ID/entity đã lưu; không buộc query danh sách để kiểm tra thao tác ghi có thành công. Nếu giao diện yêu cầu danh sách mới hơn, `latestCreatedForCustomer` gọi method có consistency rõ ràng.

**Quan trọng:** `@ScanConsistency` không làm ứng dụng tự bảo đảm mọi lần đọc sau ghi ở cả cluster khác, replica hoặc cache. Nó đặt policy trên SQL++ query tương ứng; các tầng replication/cache phải được xem riêng.

## 13. Reactive Repository cũng có thể dùng @ScanConsistency

Trong Spring Data Couchbase reactive, Repository trả `Mono` hoặc `Flux`, nhưng Query Service và secondary index vẫn có những semantics freshness giống truy vấn SQL++ đồng bộ.

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

Service:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveOrderReadService {
    private final ReactiveOrderRepository orders;

    public ReactiveOrderReadService(ReactiveOrderRepository orders) {
        this.orders = orders;
    }

    public Mono<OrderDocument> get(String orderId) {
        return orders.findById(orderId);
    }

    public Flux<OrderDocument> createdForCustomer(
            String customerId) {
        return orders.findByCustomerIdAndStatus(
                customerId, "CREATED");
    }
}
~~~

- `Flux<OrderDocument>` là luồng 0..n kết quả; vẫn cần pagination/giới hạn khi lịch sử nhiều document.
- `@ScanConsistency` không làm query nhanh hơn vì được trả bằng `Flux`.
- `REQUEST_PLUS` có thể làm Publisher chờ index dài hơn trước khi có row; cần timeout và giám sát phù hợp.
- Không gọi `block()` trong WebFlux event loop và không tự `subscribe()` trong service rồi bỏ qua lỗi.
- Một pipeline tạo Order rồi query danh sách cần dùng `flatMap`/`thenMany` để bảo đảm thứ tự subscription/thao tác; không tạo hai Publisher độc lập rồi kỳ vọng câu query luôn chạy sau mutation.

Ví dụ:

~~~java
public Flux<OrderDocument> saveThenQuery(
        OrderDocument order) {

    return orders.save(order)
            .thenMany(orders.findByCustomerIdAndStatus(
                    order.getCustomerId(), "CREATED"));
}
~~~

Method `findByCustomerIdAndStatus` đã gắn `REQUEST_PLUS`; `thenMany` nối query sau khi save hoàn tất. Đây là minh họa luồng đọc, **không** thay thế transaction hay idempotency cho thao tác tạo đơn.

## 14. Nếu dùng CouchbaseTemplate hoặc SDK thay vì Repository?

### 14.1. CouchbaseTemplate

`CouchbaseTemplate` cung cấp API query ở mức Spring Data. Ở các phiên bản có `Query.scanConsistency(...)`, có thể đặt policy trên query object:

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.core.query.Query;

// Pseudocode phần dựng query:
// Query query = Query.query(criteria...)
//         .scanConsistency(QueryScanConsistency.REQUEST_PLUS);
// template.findByQuery(OrderDocument.class).matching(query).all();
~~~

Đây là **mẫu gợi ý**, không phải đoạn Java độc lập biên dịch: cần chọn criteria, mapping type/keyspace và method phù hợp với phiên bản Spring Data. Với operation dạng fluent, một số API còn có `withConsistency(...)`. Không suy rằng tất cả Template methods cùng có cùng chữ ký.

### 14.2. Couchbase Java SDK

Truy vấn SDK có thể đặt option trực tiếp:

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

    public QueryResult listFresh(String customerId) {
        String sql = """
                SELECT META(o).id AS documentId,
                       o.customerId, o.status
                FROM `shop`.`sales`.`orders` AS o
                WHERE o.customerId = $customerId
                """;

        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS);

        return cluster.query(sql, options);
    }
}
~~~

SDK thích hợp khi cần những option chưa được lớp Repository/Template phơi bày thuận tiện. Nhưng SDK trả raw rows/`JsonObject` và **không tự dùng toàn bộ entity converter của Spring Data**. Nếu hệ thống cần mapping đầy đủ với `@Version`, field discriminator hoặc custom converter, phải thiết kế cơ chế tương thích.

**Đừng tạo `Cluster.connect` cho mỗi request**; để Spring quản lý và tái sử dụng client kết nối.

### 14.3. Không nhầm mutation-based consistency với @ScanConsistency

Java SDK còn có thể hỗ trợ độ mới theo **mutation state/token** (`consistentWith` / cơ chế `at_plus`), để query đợi đúng những mutation đã quan sát. `@ScanConsistency(query = REQUEST_PLUS)` là policy **theo mốc request**, không nhận một mutation token động làm giá trị annotation. Nếu cần consistency theo token cho luồng đặc thù, hãy kiểm tra API Template/SDK ở phiên bản tương ứng và thiết kế cách truyền token/state.

## 15. @ScanConsistency không giải quyết CAS, transaction hoặc durability

Một bảng phân biệt ngắn:

| Yêu cầu | Cơ chế phù hợp | Vai trò của @ScanConsistency |
| --- | --- | --- |
| Vừa lưu Order, query theo `customerId` phải thấy dữ liệu đến mốc query | `REQUEST_PLUS` cho SQL++ query | Có tác dụng trực tiếp |
| Đọc chính Order theo ID vừa lưu | KV theo ID | Thường không cần |
| Hai nhân viên cùng đổi trạng thái Order | `@Version` / CAS | Không tránh lost update |
| Tạo Order và trừ tồn kho phải atomic | Transaction Couchbase phù hợp hoặc workflow bù trừ | Không tạo transaction |
| Ghi Order phải đạt mức bền mong muốn | Durability option | Không thay đổi xác nhận ghi |
| Session tự hết hạn | TTL/expiry metadata | Không đặt TTL |
| Đọc từ replica hoặc cluster khác | Replica/replication semantics | Không điều khiển freshness của mọi đường đọc |
| Tìm toàn văn với ranking | Search index/API riêng | Không tự chỉnh Search consistency |

### 15.1. CAS

`@Version` ở Spring Data Couchbase có thể dùng CAS metadata để phát hiện mutation cạnh tranh:

~~~text
A đọc Order, CAS=C1
B đọc Order, CAS=C1
A save -> thành công, CAS=C2
B save với C1 -> optimistic locking conflict
~~~

Bật `REQUEST_PLUS` cho một method tìm theo status **không** khiến B ghi an toàn hơn. Cần phát hiện/giải quyết xung đột trên chính đường ghi.

### 15.2. Transaction

Nếu Order và Inventory là hai document cần cùng thành công/thất bại, gọi hai lần `save` không tự bảo đảm atomicity. Một transaction phải được thực thi qua API/transaction manager phù hợp với phiên bản và ranh giới của mọi thao tác. Annotation `@ScanConsistency` chỉ nói về độ mới query index, không định nghĩa ranh giới commit hay rollback.

### 15.3. TTL

Session có TTL nhưng JSON field `expiresAt` không tự động làm Couchbase hết hạn. Expiry là metadata/cấu hình; query theo index có thể có độ trễ phản ánh mutation/expiry. Không dùng một query có thể stale làm nguồn duy nhất quyết định còn đăng nhập.

### 15.4. Durability

Durability yêu cầu mức ghi bền/nhân bản được xác nhận khi mutation thành công; `REQUEST_PLUS` yêu cầu index bắt kịp mutation để phục vụ query. Có thể cần cả hai trong một hệ thống nhưng chúng không thay thế nhau.

## 16. Tác động hiệu năng: đánh đổi khi gắn annotation quá rộng

Giả sử 100% API list Order của ứng dụng được chú thích `REQUEST_PLUS`, trong khi chỉ 10% request yêu cầu thấy mutation vừa ghi. Khi Index Service có backlog, **cả các request không cần độ mới cao** cũng có thể phải chờ index, làm tăng p95/p99 latency và timeout.

~~~text
Tổng thời gian SQL++ có thể gồm:
  - HTTP/SDK request và network
  - Chờ index đạt consistency yêu cầu
  - Index scan
  - Fetch, filter, sort, projection
  - Chuyển rows về application
~~~

Các yếu tố cần quan sát:

| Thước đo | Ý nghĩa |
| --- | --- |
| Query p50/p95/p99 | Người dùng bị ảnh hưởng bao nhiêu dưới tải? |
| Query timeout và cancellation | Chờ index có vượt ngân sách request? |
| Index mutation backlog/lag | Index Service đang theo kịp Data Service ở mức nào? |
| Query plan/scan/fetch/sort | Có nút thắt ngoài consistency không? |
| KV latency | Vấn đề có nằm ở đường đọc theo key không? |
| JVM thread/heap, SDK metrics | Pipeline đồng bộ/reactive có nghẽn tài nguyên? |
| Tỷ lệ REQUEST_PLUS theo endpoint | Đã áp dụng đúng nơi cần hay quá rộng? |

### 16.1. Đặt timeout đúng ranh giới

Nếu một query `REQUEST_PLUS` phải chờ index bắt kịp nhưng request HTTP chỉ có ngân sách 200 ms, query có thể thường xuyên timeout khi tải tăng. Phải phối hợp SDK query timeout, HTTP timeout, chính sách retry và quy mô cluster. Không retry mù quáng một endpoint list nếu mỗi lần lại tạo thêm đợt chờ index mà backend đang quá tải.

### 16.2. Cách tối ưu theo thứ tự

1. Xác nhận query đúng keyspace và semantics.
2. Chuẩn bị secondary index có hiệu quả; chạy `EXPLAIN`.
3. Đặt phân trang/giới hạn kết quả.
4. Chọn `@ScanConsistency` chỉ nơi cần SLA độ mới.
5. Đo lại dưới tải ghi, đối chiếu độ mới/latency/error rate.
6. Đánh giá thay đổi UX: trang xác nhận có thể trả saved Order thay vì query danh sách.

## 17. Kiểm thử @ScanConsistency bằng integration test

**Không thể kiểm chứng độ mới index chỉ bằng mock Repository.** Cần một Couchbase Server hoặc môi trường test tương đương, bucket/scope/collection chính xác, secondary index đã online và dependency Spring Boot Test.

### 17.1. Một phương pháp kiểm chứng không flaky

1. Tạo một Order thử nghiệm với ID và customerId ngẫu nhiên.
2. Ghi Order bằng Repository hoặc SDK, xác nhận thao tác `save` thành công.
3. Đọc `findById` theo key để kiểm tra nguồn dữ liệu đã tồn tại.
4. Gọi derived query `NOT_BOUNDED` và ghi nhận kết quả, **không yêu cầu nó phải thiếu row**.
5. Gọi derived query có `@ScanConsistency(query = REQUEST_PLUS)` với các field khớp và xác nhận Order xuất hiện nếu không có mutation cạnh tranh và không bị `LIMIT` loại.
6. Xóa dữ liệu test, kiểm tra đường xử lý lỗi và lặp lại dưới tải có background writes.
7. Đo p95/p99 và timeouts của hai chính sách trên workload đại diện.

Đừng viết test dạng:

~~~text
save(Order)
assert !repositoryNotBoundedQuery.contains(Order)  // Sai tư duy!
~~~

Index có thể bắt kịp rất nhanh. `NOT_BOUNDED` **cho phép** trả trạng thái index chưa mới, không bắt buộc nó cũ.

### 17.2. Test Spring Boot repository với annotation

Giả sử trong ứng dụng đã có `OrderRepository` ở phần 6 và được inject thành công:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderScanConsistencyIT {

    @Autowired
    private OrderRepository orders;

    @Test
    void annotatedMethodSeesPreviouslySavedOrder() {
        String id = "order::it-" + UUID.randomUUID();
        String customerId = "customer-it-" + UUID.randomUUID();

        OrderDocument order = new OrderDocument(
                id, customerId, "CREATED",
                Instant.now().toString(), 150000L);

        boolean saved = false;
        try {
            OrderDocument inserted = orders.save(order);
            saved = true;

            assertEquals(id,
                    orders.findById(inserted.getId())
                            .orElseThrow().getId());

            assertTrue(
                    orders.findByCustomerIdAndStatus(
                            customerId, "CREATED")
                            .stream()
                            .anyMatch(row -> id.equals(row.getId()))
            );
        } finally {
            if (saved) {
                orders.deleteById(id);
            }
        }
    }
}
~~~

Phần này là **mẫu kiểm thử tích hợp**, không phải hứa hẹn chạy độc lập nếu chưa cấu hình môi trường:

- Collection `shop.sales.orders` phải tồn tại và entity mapping đúng.
- Index theo `customerId`/`status` phải hoạt động, bao gồm các điều kiện type/discriminator nếu query generated cần.
- `OrderDocument` cần constructor/getters như phần 5.
- Nếu `save` timeout với kết quả không rõ, cleanup dựa trên cờ `saved` chưa đủ để đảm bảo dọn hết fixture; suite thật cần phương án dọn độc lập an toàn.
- Khi test dùng dữ liệu random và không có mutation đồng thời khác, việc assert ORDER tồn tại là một kiểm tra tốt cho `REQUEST_PLUS`.
- Để xác nhận **annotation thực sự đã được apply**, ngoài kết quả test còn nên quan sát cấu hình query/SDK tracing. Kết quả xuất hiện ngay có thể do index bắt kịp tự nhiên, kể cả không có annotation.

**Không chạy test này trên production**. Đặt nó ở một môi trường riêng, tránh xóa hoặc làm lộ dữ liệu thật.

### 17.3. Phân biệt kiểm chứng hành vi và kiểm chứng cấu hình

Việc query sau ghi trả đúng row **không chứng minh riêng** rằng `@ScanConsistency` được truyền tới SQL++ QueryOptions: index có thể đã đủ mới ngay cả với NOT_BOUNDED. Để kiểm chứng cấu hình, cần kiểm tra trace/query request metadata bằng khả năng quan sát của SDK/Query Service hoặc một integration test chuyên biệt cho annotation resolution trên phiên bản đang dùng.

Vì vậy nên có **hai loại bằng chứng**:

- **Hành vi:** Query có thể nhìn thấy mutation trước mốc request khi yêu cầu và không có thay đổi cạnh tranh.
- **Cấu hình:** Method được gắn annotation đã thực sự điều khiển scan consistency tương ứng.

## 18. Những lỗi cấu hình hay gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Không import được `@ScanConsistency` | Nhầm package, sai Spring Data version | Dùng `org.springframework.data.couchbase.repository.ScanConsistency` và kiểm tra BOM |
| Enum không tìm thấy | Import nhầm hoặc SDK version lệch | Dùng `com.couchbase.client.java.query.QueryScanConsistency` |
| Gắn annotation trên `findById` mà không thấy khác biệt | Lời gọi đi KV, không quét index | Không dùng scan consistency để điều chỉnh KV |
| Annotated query vẫn chưa trả row | Filter, `LIMIT`, sai keyspace, concurrent update hoặc annotation chưa được áp dụng | Xem generated query, dữ liệu nguồn, tracing |
| Query `REQUEST_PLUS` timeout | Index backlog, index chưa online hoặc timeout quá thấp | Kiểm tra Index Service, timeout và query plan |
| Chỉ mục đã tạo nhưng query chậm | Index không phù hợp, sort/fetch lớn | `EXPLAIN`, projection, pagination |
| Annotation trên type làm nhiều query chậm | Phạm vi policy quá rộng | Chuyển xuống method cần consistency cao |
| Dùng `@ScanConsistency(value=...)` | Sai thuộc tính annotation | Sử dụng `query = QueryScanConsistency.REQUEST_PLUS` |
| Nghĩ annotation bảo vệ ghi cùng một document | Nhầm scan consistency với CAS | Dùng `@Version`/CAS, xử lý conflict |
| Nghĩ Search index cũng theo REQUEST_PLUS | Search có API consistency khác | Kiểm tra Search Service riêng |
| Test mặc định bắt buộc phải thấy stale row | Race timing không xác định | Không assert bắt buộc stale; quan sát/index lag |
| Bị duplicate Order sau retry | Check-then-insert, thiếu idempotency | Bảo vệ ở đường ghi; không coi query index là uniqueness constraint |

### 18.1. Quy trình debug khi đã gắn annotation nhưng vẫn thấy sai

~~~mermaid
flowchart TD
    A["Query thiếu Order sau khi ghi"] --> B{"Đã biết Order ID?"}
    B -->|Có| C["Đọc KV theo key xác nhận nguồn"]
    B -->|Không| D["Kiểm tra keyspace / filter"]
    C --> D
    D --> E{"Index online và EXPLAIN đúng?"}
    E -->|Không| F["Sửa index/query plan"]
    E -->|Có| G{"Method có chạy SQL++ qua annotation?"}
    G -->|Không chắc| H["Xem trace/version/annotation resolution"]
    G -->|Có| I["Kiểm tra REQUEST_PLUS, timeout và mutation cạnh tranh"]
    I --> J["Đo p95/p99 và xác nhận hợp đồng nghiệp vụ"]
~~~

Không nên chỉ thêm `REQUEST_PLUS` rồi coi vấn đề đã được giải quyết. Một row có thể bị loại vì `WHERE` không khớp, tenant filter hoặc sort/limit, dù index đã rất mới.

## 19. Câu hỏi tự kiểm tra

**1. Import nào đúng cho annotation cấu hình repository?**

`org.springframework.data.couchbase.repository.ScanConsistency`; giá trị enum SQL++ từ `com.couchbase.client.java.query.QueryScanConsistency`.

**2. Làm thế nào bật REQUEST_PLUS cho một derived method?**

~~~java
@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
List<OrderDocument> findByCustomerId(String customerId);
~~~

**3. Tại sao findById thường không cần annotation?**

Vì đọc bằng ID biết trước thường sử dụng KV; scan consistency là chính sách chờ **index của query SQL++**.

**4. Có phải NOT_BOUNDED luôn trả document cũ?**

Không. Nó chỉ không yêu cầu chờ index bắt kịp mốc mới của request; index có thể đã theo kịp.

**5. REQUEST_PLUS có ngăn hai người cùng ghi đè Order không?**

Không. Cần optimistic locking qua CAS/`@Version` hoặc điều kiện ghi phù hợp.

**6. Đặt annotation ở repository type có ưu điểm và nguy cơ gì?**

Ít lặp cấu hình khi mọi query cần cùng policy, nhưng có thể khiến các query không cần mới cũng chờ index; nên áp dụng theo SLO và test.

**7. Khi nào dùng `@Document(queryScanConsistency = ...)`?**

Khi muốn chính sách mặc định theo entity ở phiên bản hỗ trợ, đồng thời hiểu đây là phạm vi rộng và phải kiểm tra mức ưu tiên với annotation/tùy chọn khác.

**8. Vì sao test “NOT_BOUNDED phải không thấy row vừa lưu” là sai?**

Vì index có thể cập nhật rất nhanh, nên giả định bắt buộc có lag là flaky.

**9. REQUEST_PLUS có làm query tự có index không?**

Không. Cần secondary index và query plan phù hợp.

**10. Tại sao reactive không thay đổi lựa chọn consistency?**

Reactive thay cách điều phối I/O và kết quả `Flux`/`Mono`; Query Service và Index Service vẫn cần chính sách dữ liệu tương ứng.

## 20. Checklist trước khi sử dụng trong dự án

- [ ] Đã xác định method thực sự đi SQL++ thay vì KV?
- [ ] Đã import đúng `ScanConsistency` và `QueryScanConsistency`?
- [ ] Mỗi method có SLO về độ mới, không bật REQUEST_PLUS theo thói quen?
- [ ] Phạm vi annotation (method/type/entity) phù hợp và không vô tình ảnh hưởng query khác?
- [ ] Document mapping chỉ đúng bucket/scope/collection; ID là metadata?
- [ ] Secondary index đúng, online và được kiểm tra bằng `EXPLAIN`?
- [ ] Query generated/`@Query` có filter, projection và binding đúng?
- [ ] Query có `LIMIT`/pagination nếu kết quả nhiều; không tải không giới hạn?
- [ ] Timeout tính cả thời gian chờ index? Đã đo p95/p99 và error rate?
- [ ] Không dựa vào query index để bảo đảm uniqueness hay tranh chấp ghi?
- [ ] CAS, TTL, durability và transaction được thiết kế riêng?
- [ ] Reactive pipeline không blocking và không subscribe thủ công sai chỗ?
- [ ] Integration test kiểm tra read-after-write nhưng không bắt NOT_BOUNDED luôn stale?
- [ ] Đã xác nhận annotation được apply trong đúng bộ phiên bản qua log/trace/test?
- [ ] Có metric/index lag để chẩn đoán sự cố thực tế?

## 21. Tài liệu chính thức để đối chiếu API

Các nguồn dưới đây giúp kiểm tra chữ ký và khả năng của phiên bản đang sử dụng; nên ưu tiên trang đúng phiên bản thay vì sao chép mã từ nhiều thế hệ SDK:

- [Spring Data Couchbase — Repositories, mục Querying with consistency](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html)
- [`@ScanConsistency` — Java API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/repository/ScanConsistency.html)
- [`@Document` — Java API, thuộc tính queryScanConsistency](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/mapping/Document.html)
- [Spring Data Couchbase Query — API scanConsistency](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/query/Query.html)

## 22. Kết luận

**`@ScanConsistency` là cách khai báo scan consistency cho các truy vấn repository trong Spring Data Couchbase**, thường dùng để chuyển một SQL++ query có yêu cầu độ mới cao từ `NOT_BOUNDED` sang `REQUEST_PLUS`. Cú pháp quan trọng là `@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)`, với đúng package Spring Data và enum Couchbase SDK.

Hãy ưu tiên **cấu hình theo method** khi chỉ một vài endpoint cần đọc các mutation vừa ghi, xác định rõ query có dùng secondary index hay không, chuẩn bị index tốt và đo chi phí chờ index. Với document đã có key, đọc KV thường đơn giản hơn; với transaction, CAS, TTL hay durability, phải dùng cơ chế riêng. Khi kết hợp đúng annotation, query plan, kiểm thử và quan sát, tầng truy cập Couchbase sẽ vừa đáp ứng SLO về độ mới dữ liệu vừa tránh độ trễ không cần thiết.
