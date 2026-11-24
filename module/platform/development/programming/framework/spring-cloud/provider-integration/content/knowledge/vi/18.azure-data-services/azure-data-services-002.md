# Partition key, ánh xạ tài liệu và repository

Khi dùng Azure Cosmos DB for NoSQL với Spring Data Cosmos, ba quyết định gắn chặt với nhau: **partition key** xác định dữ liệu được phân phối và định tuyến như thế nào; **mapping tài liệu** xác định object Java trở thành item JSON ra sao; **repository** xác định ứng dụng đọc và ghi item theo access pattern nào. Nếu chọn partition key không phù hợp, một repository có method rất ngắn vẫn có thể tạo query fan-out, tiêu tốn nhiều Request Units (RU) hoặc dồn tải vào một logical partition. Nếu mapping sai tên field hoặc partition value, point read và query có thể không tìm thấy item dù dữ liệu vẫn tồn tại.

Bài thuộc chương **Dữ liệu Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này đi sâu vào mô hình dữ liệu Cosmos DB for NoSQL và cách thể hiện mô hình đó bằng entity, repository và truy vấn trong Spring Data Cosmos.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Thiết kế partition key từ access pattern, phân phối tải, cardinality và ranh giới transaction.
- Phân biệt item ID, partition key value, logical partition và physical partition.
- Ánh xạ Java document sang JSON item bằng `@Container`, `@Id`, `@PartitionKey` và các quy tắc mapping.
- Viết repository CRUD, derived query, custom query có tham số và point read có partition key.
- Đánh giá chi phí của cross-partition query, phân trang và truy vấn không dùng index.
- Thiết kế cập nhật đồng thời bằng ETag/optimistic locking và xử lý thay đổi partition key.
- Kiểm thử mapping, repository và partition behavior bằng emulator và Azure environment.

## 2. Item, ID và partition key tạo nên địa chỉ dữ liệu

Trong Cosmos DB for NoSQL, dữ liệu được lưu dưới dạng **item JSON** trong một **container**. Mỗi item có thuộc tính hệ thống `id`; container có partition key path, ví dụ `/tenantId`. Giá trị của field tại path đó là **partition key value**.

Với container có partition key path `/tenantId`, item sau thuộc logical partition `tenant-42`:

~~~json
{
  "id": "order-1001",
  "tenantId": "tenant-42",
  "status": "PAID",
  "total": 125.50,
  "createdAt": "2026-11-24T08:30:00Z"
}
~~~

Ba khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Item ID** | Định danh item trong container; thường được ánh xạ từ field `id` | `order-1001` |
| **Partition key path** | Đường dẫn JSON được khai báo cho container | `/tenantId` |
| **Partition key value** | Giá trị của field tại path đối với item cụ thể | `tenant-42` |

Với API for NoSQL, item được xác định bởi **ID và partition key value** trong phạm vi container. Hai item có thể có cùng `id` nếu chúng nằm ở hai logical partition khác nhau; trong cùng logical partition, tổ hợp đó phải duy nhất. Vì vậy, chỉ giữ ID trong URL có thể chưa đủ để thực hiện một point read hiệu quả.

~~~mermaid
flowchart TD
    A[Container: orders] --> P1[Logical partition tenant-42]
    A --> P2[Logical partition tenant-77]
    P1 --> I1[Item id=order-1001]
    P1 --> I2[Item id=order-1002]
    P2 --> I3[Item id=order-1001]
    K[Point read address] --> V[container + partition key + id]
~~~

**Logical partition** là nhóm item có cùng partition key value. Dịch vụ phân phối các logical partition lên **physical partition** do Cosmos DB quản lý. Ứng dụng chọn partition key path và value; không tự gán item vào một physical partition cụ thể.

## 3. Chọn partition key từ access pattern

Partition key nên được chọn sau khi đã liệt kê những thao tác ứng dụng thực sự cần:

- Đọc một item khi biết ID.
- Lấy danh sách item theo tenant, trạng thái hoặc thời gian.
- Ghi/cập nhật nhiều item trong một use case.
- Phân trang danh sách lớn.
- Chạy báo cáo hoặc truy vấn tổng hợp trên nhiều tenant.
- Xử lý lưu lượng lệch giữa các nhóm dữ liệu.

Một partition key tốt thường có **cardinality đủ cao**, phân phối tải tương đối đều, xuất hiện trong các truy vấn quan trọng và có giá trị ổn định trong vòng đời item. Không có một field mặc định đúng cho mọi ứng dụng.

### 3.1. Ví dụ container đơn hàng

Giả sử phần lớn request thao tác dữ liệu của một tenant: tạo đơn, đọc đơn, tìm đơn theo trạng thái và tải lịch sử. Partition key `/tenantId` có thể phù hợp vì query theo tenant có thể được định tuyến tới một logical partition.

| Partition key | Ưu điểm | Rủi ro |
| --- | --- | --- |
| `/tenantId` | Truy vấn theo tenant thuận tiện; các item của tenant có cùng logical partition | Tenant lớn hoặc quá nóng có thể gây skew và giới hạn khả năng mở rộng |
| `/id` | Cardinality cao; point read thuận tiện nếu luôn biết ID | Query theo tenant/status thường phải fan-out qua nhiều partition |
| `/status` | Query một trạng thái có thể có predicate đơn giản | Ít giá trị trạng thái; một số partition có thể rất nóng và dồn nhiều dữ liệu |
| `/createdMonth` | Hữu ích cho truy vấn theo tháng và lưu trữ theo thời gian | Query theo tenant có thể phải đi qua nhiều partition; transaction giữa các tháng bị chia |
| Synthetic key `tenantId#bucket` | Có thể phân tán tải của tenant lớn | Cần tính bucket ổn định; truy vấn tenant phải tổng hợp nhiều logical partition |

**Cardinality cao không phải tiêu chí duy nhất.** Một key có hàng triệu giá trị nhưng không xuất hiện trong query phổ biến có thể khiến ứng dụng phải fan-out thường xuyên. Một key có ít giá trị nhưng tải phân phối đều vẫn có thể là lựa chọn tốt cho một workload cụ thể; cần đo bằng dữ liệu đại diện.

### 3.2. Hot partition và skew

Một logical partition có thể trở thành **hot partition** nếu nhận lượng request/RU lớn hơn nhiều partition khác. Ví dụ, một tenant chiếm 40% traffic nhưng mọi item của tenant đó dùng chung `tenantId`; một partition có thể chạm giới hạn throughput dù tổng RU/s của container vẫn còn dư ở các partition khác.

Hãy theo dõi:

- RU consumed theo partition key range và tỷ lệ request bị throttling.
- Phân phối item count và kích thước dữ liệu theo key.
- Tần suất đọc/ghi theo tenant, status hoặc time window.
- Query có fan-out và số partition tham gia.
- Kích thước lớn nhất của một logical partition.

Không khắc phục hot partition bằng cách tăng RU/s một cách máy móc. Nếu một key quá nóng, throughput cao hơn có thể trì hoãn sự cố nhưng không thay đổi skew. Cần xem lại key, mô hình dữ liệu hoặc cách chia workload.

### 3.3. Synthetic key và hierarchical partition key

**Synthetic partition key** là giá trị được ứng dụng tạo từ nhiều thuộc tính, ví dụ `tenantId#yyyyMM` hoặc `tenantId#shardNumber`. Cách này có thể phân tán tải, nhưng query cần tìm toàn bộ dữ liệu của tenant có thể phải tính các bucket và đọc nhiều partition. Hàm tạo key phải ổn định, có versioning rõ ràng và không được dựa vào giá trị do caller tùy ý gửi.

**Hierarchical partition key (HPK)** cho phép khai báo nhiều cấp của partition key path trong các khả năng Cosmos DB for NoSQL hỗ trợ. Cấu trúc này có thể giúp phân phối dữ liệu lớn theo các cấp như tenant rồi đến nhóm con, đồng thời hỗ trợ truy vấn có prefix của hierarchy. Tuy nhiên, cần kiểm tra giới hạn, API, SDK và khả năng hỗ trợ của phiên bản Spring Data Cosmos đang dùng; không giả định một annotation `@PartitionKey` đơn trường tự biểu diễn mọi cấu hình HPK.

Chỉ dùng HPK khi access pattern và quy mô thực sự cần. Nó không làm mọi query trở thành point read, không tự bảo đảm cân bằng tải và không biến transaction thành giao dịch xuyên mọi cấp key.

## 4. Partition key gắn với ranh giới transaction

Cosmos DB for NoSQL hỗ trợ ACID transaction trong phạm vi **một logical partition key**. Transactional batch có thể nhóm các thao tác trên item cùng container và cùng partition key value; batch bị rollback nếu một operation thất bại theo contract của API.

Điều đó ảnh hưởng trực tiếp đến mô hình dữ liệu:

~~~text
Order(orderId, tenantId)
OrderLine(lineId, orderId, tenantId)
PaymentRecord(paymentId, orderId, tenantId)
~~~

Nếu order, order line và payment record cần được cập nhật nguyên tử cùng nhau, việc đặt chúng trong cùng container và cùng partition key value có thể cho phép transactional batch. Nếu mỗi loại dữ liệu ở container khác hoặc thuộc partition key value khác, không có transaction nguyên tử xuyên các ranh giới đó.

| Thiết kế | Có thể dùng một transactional batch? | Hệ quả |
| --- | --- | --- |
| Nhiều item cùng container, cùng partition key value | Có, nếu thao tác được API hỗ trợ | Phù hợp cho cập nhật nguyên tử trong logical partition |
| Item cùng container nhưng khác partition key value | Không | Cần workflow nhiều bước/saga hoặc thiết kế lại aggregate |
| Item ở hai container khác nhau | Không bằng transactional batch của một container | Phải điều phối riêng |
| Database Cosmos và Azure Blob Storage | Không | Cần trạng thái, retry, outbox hoặc compensation |

Nếu nghiệp vụ đòi hỏi transaction xuyên nhiều tenant, hãy cân nhắc lại aggregate boundary. Không nên chọn `/tenantId` chỉ vì tiện rồi kỳ vọng một batch có thể cập nhật mọi tenant cùng lúc.

## 5. Ánh xạ Java object thành JSON item

Spring Data Cosmos cung cấp mapping annotation để mô tả container và field:

- `@Container`: gắn entity với container.
- `@Id`: đánh dấu field ánh xạ tới system property `id`.
- `@PartitionKey`: đánh dấu field mang partition key value.
- Các annotation Spring Data/Jackson hoặc converter phù hợp có thể hỗ trợ những trường hợp mapping cụ thể, nhưng cần kiểm tra serializer thực tế của version đang dùng.

Ví dụ entity:

~~~java
import com.azure.spring.data.cosmos.core.mapping.Container;
import com.azure.spring.data.cosmos.core.mapping.PartitionKey;
import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;

@Container(
    containerName = "orders",
    autoCreateContainer = false
)
public class OrderDocument {
    @Id
    private String id;

    @PartitionKey
    private String tenantId;

    private String status;
    private BigDecimal total;
    private Instant createdAt;

    public OrderDocument() {
    }

    public OrderDocument(
            String id,
            String tenantId,
            String status,
            BigDecimal total,
            Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.total = total;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public BigDecimal getTotal() { return total; }
    public Instant getCreatedAt() { return createdAt; }

    public void setId(String id) { this.id = id; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public void setStatus(String status) { this.status = status; }
    public void setTotal(BigDecimal total) { this.total = total; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
~~~

Nếu container được tạo với partition key path `/tenantId`, field `tenantId` của entity phải được serialize đúng thành property `tenantId` ở root JSON. Tên field, annotation, serializer và partition key path phải khớp. Đổi tên field Java mà không cập nhật mapping có thể khiến request gửi thiếu partition key hoặc query lọc sai property.

### 5.1. Container mapping không tự tạo schema quan hệ

`@Container(containerName = "orders")` xác định tên container. Cosmos DB là schema-flexible: các item trong cùng container không bắt buộc phải có toàn bộ property giống nhau. Annotation entity không tự tạo foreign key, join, relational constraint hoặc index như JPA database.

`autoCreateContainer = false` phù hợp khi container được provision bằng IaC/deployment pipeline. Nếu bật auto-create trong môi trường phát triển, cần hiểu rõ thư viện sẽ dùng partition key/throughput nào và có quyền provisioning hay không. Không để nhiều instance production tự ý tạo hoặc sửa container ngoài quy trình quản lý hạ tầng.

### 5.2. Field tùy chọn, null và kiểu dữ liệu

Mapping cần quyết định rõ cách biểu diễn:

- **Field vắng mặt và null:** hai trạng thái có thể khác nhau trong query và update. Không mặc định serializer luôn ghi hoặc bỏ field null giống nhau.
- **Thời gian:** thống nhất UTC và định dạng ISO 8601/Instant; không lưu thời gian địa phương thiếu offset nếu query theo thời gian.
- **Tiền tệ:** dùng `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất, kèm currency; tránh float/double cho giá trị cần chính xác.
- **Enum:** xác định serialize theo tên ổn định hay mã; đổi tên enum Java có thể làm dữ liệu cũ không đọc được nếu mapping theo tên.
- **Nested object/collection:** kiểm soát kích thước item và shape; query trên nested path cần được hỗ trợ bởi indexing policy.
- **Field nhạy cảm:** không serialize credential/token/secret vào item chỉ vì entity có field đó.

Nếu dùng Jackson annotation hoặc custom converter, cần kiểm thử JSON thực tế mà SDK gửi/nhận; đừng suy luận chỉ từ getter/setter của Java class.

### 5.3. Mapping phiên bản dữ liệu

Schema của item có thể phát triển theo thời gian. Khi thêm field mới, đặt default hợp lý trong application model và bảo đảm consumer cũ có thể bỏ qua field không biết. Khi đổi tên hoặc đổi semantics:

1. Thêm field mới hoặc version marker trước.
2. Cho code đọc được cả dữ liệu cũ và mới trong giai đoạn chuyển đổi.
3. Backfill theo batch có giới hạn RU.
4. Chuyển ghi sang format mới.
5. Chỉ xóa field cũ khi đã đối soát và không còn consumer phụ thuộc.

Không dùng việc đổi tên property Java như một migration dữ liệu ngầm. Cosmos DB không tự đổi tên property của item cũ khi ứng dụng deploy code mới.

## 6. Repository interface và các thao tác cơ bản

Spring Data Cosmos cung cấp `CosmosRepository<T, ID>` cho API đồng bộ. Ví dụ:

~~~java
import com.azure.spring.data.cosmos.repository.CosmosRepository;
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.query.Param;
import com.azure.spring.data.cosmos.repository.Query;

public interface OrderRepository
        extends CosmosRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status);

    @Query("SELECT * FROM c WHERE c.tenantId = @tenantId AND c.status = @status")
    List<OrderDocument> findOrders(
        @Param("tenantId") String tenantId,
        @Param("status") String status);
}
~~~

Các method repository thường dùng:

| Method | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `save(entity)` | Tạo hoặc cập nhật item theo semantics của repository/SDK | Không mặc định tương đương create-only; xem upsert và concurrency |
| `findById(id)` | Tìm item theo ID qua repository | Nếu không truyền partition key, có thể không đạt hiệu quả point read |
| `findById(id, partitionKey)` | Tìm theo ID và partition key | Ưu tiên khi biết partition value |
| `findAll()` | Lấy dữ liệu qua repository | Có thể đọc nhiều partition; không dùng như thao tác rẻ mặc định |
| `deleteById(id)` | Xóa item theo ID | Với container partitioned, cần API/overload phù hợp partition key khi có |
| Derived query | Sinh query từ tên method | Chỉ dùng từ khóa được Spring Data Cosmos hỗ trợ |
| `@Query` | Khai báo Cosmos SQL query | Bind tham số; kiểm tra partition predicate và RU |

Không phải mọi method signature của Spring Data JPA đều có cùng semantics hoặc được hỗ trợ trong Spring Data Cosmos. Đọc tài liệu của đúng phiên bản và kiểm thử repository thật, nhất là các method có `Pageable`, `Sort`, `Optional`, projection hoặc update/delete derived.

## 7. Point read: truyền cả ID và partition key

Khi biết item ID và partition key value, point read là đường đọc trực tiếp phù hợp. Với Spring Data Cosmos, có thể dùng overload repository nhận `PartitionKey`:

~~~java
import com.azure.cosmos.models.PartitionKey;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {
    private final OrderRepository orders;

    public OrderReadService(OrderRepository orders) {
        this.orders = orders;
    }

    public Optional<OrderDocument> find(
            String authenticatedTenantId,
            String orderId) {
        return orders.findById(
            orderId,
            new PartitionKey(authenticatedTenantId));
    }
}
~~~

Trong ứng dụng multi-tenant, `authenticatedTenantId` phải đến từ security context đã xác thực hoặc được đối chiếu ownership. Không tin partition key do caller tự gửi để đọc item của tenant khác. Một endpoint chỉ nhận `orderId` có thể cần lookup một bản ghi định tuyến/metadata đáng tin cậy để tìm tenant/partition key trước khi gọi point read.

**Point read** và **query** khác nhau:

- Point read dùng **container + item ID + partition key value**, thường là đường đọc hiệu quả nhất cho một item đã biết.
- Query dùng predicate và có thể trả nhiều item; nếu không giới hạn partition key, dịch vụ có thể phải fan-out qua nhiều partition.
- Derived query có chứa partition key trong method name không tự bảo đảm SDK luôn thực hiện point read; chỉ một item ID + partition key với API point read mới thể hiện rõ đường đọc trực tiếp.

## 8. Derived query và custom Cosmos SQL

### 8.1. Derived query

Ví dụ:

~~~java
List<OrderDocument> findByTenantIdAndStatus(
    String tenantId, String status);

List<OrderDocument> findByTenantIdAndCreatedAtAfter(
    String tenantId, Instant from);
~~~

Spring Data phân tích tên method để tạo query dựa trên property của entity. Các property phải đúng tên Java mapping. Một method như `findByStatus("PAID")` không có tenant predicate có thể trở thành cross-partition query trên container partitioned.

### 8.2. Custom query với tham số

~~~java
@Query("""
    SELECT * FROM c
    WHERE c.tenantId = @tenantId
      AND c.status = @status
    ORDER BY c.createdAt DESC
    """)
List<OrderDocument> findRecentByStatus(
    @Param("tenantId") String tenantId,
    @Param("status") String status);
~~~

Đây là Cosmos DB SQL-like query; `@Param` bind giá trị thay vì nối input thành query string. Tránh ghép chuỗi từ request vào `@Query`, vì dễ tạo query sai và rủi ro injection. Nếu cần tên property/field động, dùng whitelist và API query phù hợp thay vì cho caller truyền đoạn SQL tùy ý.

**Partition predicate** nên được đưa vào query khi access pattern cho phép, ví dụ `c.tenantId = @tenantId`. Điều đó giúp dịch vụ định tuyến tới partition liên quan. Tuy nhiên, predicate có partition key không có nghĩa mọi query chỉ tốn một RU cố định; chi phí vẫn phụ thuộc số item, index, projection, consistency và dữ liệu thực tế.

### 8.3. Projection và chỉ lấy field cần thiết

Nếu màn hình chỉ cần `id`, `status`, `total`, không cần đọc toàn bộ item có payload lớn. Có thể thiết kế projection DTO/query tương ứng theo tính năng Spring Data Cosmos của phiên bản đang dùng. Kiểm tra kiểu kết quả mapping, nullability và trường hệ thống; không trả entity persistence trực tiếp cho public API nếu nó chứa field nội bộ.

## 9. Cross-partition query, pagination và RU

Query thiếu partition key có thể được thực hiện trên nhiều logical/physical partition. Đây là điều hợp lệ cho báo cáo hoặc tìm kiếm toàn cục, nhưng có chi phí:

- Nhiều partition tham gia, nhiều request backend và tổng RU cao hơn.
- Latency phụ thuộc partition chậm nhất và mức song song.
- Kết quả lớn cần continuation token/page; không tải tất cả item về heap.
- Throttling có thể xuất hiện nếu parallelism/query concurrency quá cao.

Ví dụ truy vấn toàn bộ order theo trạng thái:

~~~sql
SELECT * FROM c
WHERE c.status = "PAID"
~~~

Nếu `tenantId` là partition key, query trên không chỉ rõ tenant và có thể phải chạy cross-partition. Đây có thể là yêu cầu hợp lệ cho báo cáo toàn hệ thống; khi đó nên cân nhắc projection/reporting store hoặc change feed thay vì gọi query nặng từ request path.

### 9.1. Pagination và continuation

Cosmos DB sử dụng continuation token để tiếp tục một query. Một page có thể trả ít item hơn page size yêu cầu do RU, execution time hoặc giới hạn response. Không nên giả định `Pageable` trên mọi repository sẽ cung cấp tổng số trang miễn phí như một relational database.

Với API public, có thể bọc continuation token vào cursor opaque. Token phải được bảo vệ khỏi sửa đổi và gắn với query/filter/tenant context ban đầu; không dùng token của tenant A cho tenant B. Nếu framework abstraction không expose token theo cách cần thiết, dùng API template/SDK tương ứng trong adapter và giữ contract pagination ở application boundary.

### 9.2. RU và query diagnostics

RU charge phản ánh chi phí thao tác. Để tối ưu query:

1. Ghi nhận request charge, latency, status/substatus và activity ID.
2. Xác nhận query có predicate theo partition key khi có thể.
3. Kiểm tra indexing policy, sort/order, composite index và projection.
4. Giảm số field/item trả về, dùng pagination và giới hạn concurrency.
5. So sánh trên dữ liệu có phân phối giống production.

Không chỉ đo latency trong một emulator hoặc dataset nhỏ. RU, throttling và hot partition chỉ bộc lộ rõ khi dữ liệu/tải đủ đại diện.

## 10. Cập nhật đồng thời bằng ETag và optimistic locking

Hai worker có thể cùng đọc một item rồi cùng cập nhật. Nếu không có concurrency control, thao tác ghi sau có thể ghi đè thay đổi của thao tác trước. Cosmos DB dùng ETag để hỗ trợ optimistic concurrency.

Với Spring Data Cosmos, có thể ánh xạ ETag vào field `_etag` bằng `@Version` ở các thao tác/phiên bản hỗ trợ:

~~~java
import com.azure.spring.data.cosmos.core.mapping.Container;
import com.azure.spring.data.cosmos.core.mapping.PartitionKey;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;

@Container(containerName = "inventory")
public class InventoryDocument {
    @Id
    private String id;

    @PartitionKey
    private String warehouseId;

    private int availableQuantity;

    @Version
    private String _etag;

    public InventoryDocument() {}
}
~~~

Khi repository cập nhật một entity mang ETag cũ, service có thể trả conflict/precondition failure (thường là HTTP 412 ở API tương ứng). Application service cần quyết định:

- Đọc lại item và tính lại nghiệp vụ (ví dụ trừ tồn kho).
- Trả conflict để caller thử lại với trạng thái mới.
- Từ chối nếu điều kiện nghiệp vụ không còn đúng.

Không retry cùng payload cũ vô hạn, vì điều đó không giải quyết conflict. Cần test hai tiến trình cùng cập nhật một item và xác minh một thao tác bị phát hiện stale version.

## 11. Thay đổi partition key và migration dữ liệu

**Partition key value không thể được cập nhật tại chỗ để di chuyển item sang logical partition khác.** Nếu cần đổi `tenantId` hoặc đổi partition key path, phải tạo item mới ở vị trí đích và xóa item cũ theo quy trình có kiểm soát. Thay partition key path cho container hiện hữu thường yêu cầu container mới và migration.

Quy trình migration có thể gồm:

1. Tạo container đích với partition key path mới và indexing/throughput phù hợp.
2. Backfill dữ liệu cũ theo batch có giới hạn RU và checkpoint.
3. Đồng bộ thay đổi phát sinh trong khi backfill (ví dụ change feed hoặc dual-write có kiểm soát).
4. Đối soát số item, ID, partition value, checksum và business invariant.
5. Chuyển traffic sang container mới theo cutover/rollback plan.
6. Giữ container cũ trong thời gian rollback rồi retire theo retention policy.

Nếu đổi từ `/tenantId` sang `/tenantId/orderGroup`, ứng dụng cũng phải thay mapping và query/repository phù hợp; chỉ sửa annotation trong Java không di chuyển dữ liệu hiện có.

## 12. Repository đồng bộ và reactive

Spring Data Cosmos cung cấp repository đồng bộ và reactive tùy dependency/phiên bản:

~~~java
import com.azure.spring.data.cosmos.repository.ReactiveCosmosRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveCosmosRepository<OrderDocument, String> {

    Flux<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status);

    Mono<OrderDocument> findByTenantIdAndId(
        String tenantId, String id);
}
~~~

Reactive repository phù hợp khi toàn bộ đường xử lý dùng WebFlux/Reactor và driver/client bên dưới hỗ trợ non-blocking. Không bọc repository đồng bộ trong `Mono.just(...)` rồi kết luận đã có reactive I/O; lời gọi blocking vẫn chạy khi tạo giá trị. Nếu cần chuyển một thao tác blocking, phải cô lập nó khỏi event loop bằng scheduler phù hợp, nhưng đó vẫn là I/O blocking.

Với reactive method, xử lý `Mono.empty()`, `onError`, cancellation và retry theo contract. Retry một lệnh ghi có side effect có thể tạo thao tác lặp; cần ID ổn định, ETag/precondition hoặc idempotency. Đừng gọi `subscribe()` bên trong service để tự chạy repository rồi trả response trước khi thao tác hoàn tất.

## 13. Khi nào dùng repository, template hay SDK trực tiếp?

| Nhu cầu | Lựa chọn phù hợp để đánh giá | Vì sao |
| --- | --- | --- |
| CRUD và query phổ biến trên entity | `CosmosRepository` | Giảm boilerplate, tích hợp Spring Data |
| Derived query theo field và custom Cosmos SQL | Repository + `@Query` | Hợp đồng đọc dữ liệu rõ, bind tham số |
| Point read cần chỉ rõ partition key | Repository overload hoặc template/SDK | Kiểm soát đường đọc ID + partition |
| Cần response diagnostics/RU, request options riêng | `CosmosTemplate` hoặc SDK | Truy cập tùy chọn cấp thấp hơn |
| Change Feed Processor, transactional batch hoặc tính năng SDK chuyên biệt | SDK/client phù hợp | Repository không nhất thiết biểu diễn đầy đủ |
| Nhiều thao tác lặp trong một workflow | Application service + repository/port | Giữ business transaction boundary rõ |

Không cần dùng SDK trực tiếp cho mọi method chỉ để “tối ưu”. Hãy đo trước, sau đó chuyển phần thực sự cần capability riêng xuống adapter. Ngược lại, đừng ép một thao tác SDK chuyên biệt vào derived query chỉ vì muốn mọi truy cập dữ liệu đều là repository.

## 14. Kiểm thử mapping, repository và partition

### 14.1. Unit test application service

Mock repository/port để kiểm tra business rule, tenant authorization và cách service tạo entity. Unit test không cần Cosmos endpoint, credential hoặc emulator.

### 14.2. Mapping test

Xác minh JSON thực tế:

- Có field `id` và đúng kiểu.
- Partition property được serialize đúng tên/path và không null.
- Enum, thời gian, decimal, nested object và field optional được biểu diễn đúng.
- Field nhạy cảm không xuất hiện trong document.
- Dữ liệu cũ vẫn deserialize được sau khi schema thay đổi.

Không chỉ kiểm tra getter/setter. Hãy dùng serializer/mapping thực tế của thư viện và đọc lại item từ emulator hoặc test account.

### 14.3. Repository integration test

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Save rồi point read | Cùng ID + partition key đọc được đúng item |
| Cùng ID ở hai partition khác nhau | Không nhầm item giữa tenant |
| Derived query có partition predicate | Kết quả và RU/latency đúng kỳ vọng |
| Query thiếu partition predicate | Hành vi cross-partition và chi phí được nhận diện |
| Pagination | Continuation/page không bỏ hoặc lặp item ngoài contract |
| Optimistic locking | ETag cũ tạo conflict thay vì ghi đè âm thầm |
| Transactional batch | Chỉ nhóm item cùng logical partition được commit atomically |
| Thay đổi schema | Entity cũ và mới được đọc theo migration plan |

Cosmos DB Emulator hỗ trợ kiểm thử cục bộ cho các API được hỗ trợ, nhưng không thay thế cloud test cho Managed Identity, native data-plane RBAC, firewall/private endpoint, RU quota, multi-region failover và workload thực tế. Emulator dùng certificate tự ký; Java runtime cần trust certificate theo hướng dẫn, không tắt TLS verification tùy tiện.

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Chọn `/status` làm partition key vì query hay lọc status | Ít giá trị key, có thể tạo hot partition | Phân tích cardinality, traffic và query theo tenant/ID |
| Dùng `/id` nhưng hầu hết query theo tenant | Nhiều query fan-out | Chọn key theo access pattern hoặc thiết kế projection |
| Chỉ lưu ID mà quên partition key khi đọc | Không thể point read tối ưu | Truyền ID + partition value đã xác minh |
| Đổi tên Java field mà không kiểm tra JSON | Query/mapping lệch property path | Mapping test và migration schema |
| Dùng `findAll()` trong request path | Đọc rộng, RU/latency cao | Query có filter, pagination hoặc read model |
| Dùng JPA join/transaction kỳ vọng trên Cosmos | Sai mô hình dữ liệu và transaction | Denormalize theo access pattern, transaction cùng logical partition |
| Sửa partition key annotation rồi deploy | Item cũ vẫn ở partition path cũ | Tạo container đích và migration dữ liệu |
| Retry update với ETag cũ | Conflict lặp lại hoặc mất thay đổi nghiệp vụ | Đọc lại và tính lại state |
| Test chỉ với mock repository | Không phát hiện partition/mapping/query behavior | Emulator và cloud integration test |

## 16. Bài tập thực hành

**Bài tập 1 — Chọn partition key.** Một hệ thống lưu order theo tenant. 90% request đọc theo `tenantId + orderId`, 8% query theo `tenantId + status`, 2% báo cáo toàn hệ thống. Hãy chọn partition key, giải thích cách xử lý tenant cực lớn và đánh giá query cross-partition cho báo cáo.

**Bài tập 2 — Mapping entity.** Viết `OrderDocument` với `@Container`, `@Id`, `@PartitionKey`; chỉ rõ container partition key path và JSON item mong đợi. Thêm field thời gian, tiền tệ, enum và nested address; xác định format ổn định khi schema tiến hóa.

**Bài tập 3 — Repository.** Viết `OrderRepository` với derived query theo tenant/status, custom `@Query` theo thời gian và method point read nhận `PartitionKey`. Giải thích method nào có thể cross-partition và cách xác minh query/RU.

**Bài tập 4 — Hot partition.** Một tenant tạo 40% tổng RU. Đề xuất synthetic key hoặc hierarchical key; nêu các query phải thay đổi, cách duy trì transaction và chi phí tổng hợp nhiều bucket.

**Bài tập 5 — Transaction.** Một order có nhiều line và cần cập nhật nguyên tử. Thiết kế container/partition để transactional batch thực hiện được. Điều gì xảy ra khi line thuộc partition khác hoặc container khác?

**Bài tập 6 — Optimistic locking.** Hai worker cùng cập nhật inventory. Dùng ETag/`@Version`, mô phỏng 412 và viết quy tắc đọc lại/tính lại số lượng. Vì sao retry payload cũ không an toàn?

**Bài tập 7 — Migration partition.** Hệ thống đang dùng `/tenantId` nhưng cần chuyển sang `/tenantId/orderGroup`. Viết kế hoạch tạo container mới, backfill, đồng bộ thay đổi, đối soát, cutover và rollback.

**Bài tập 8 — Test strategy.** Lập bộ test mapping JSON, repository, partition routing, pagination, RU và RBAC. Phân loại test nào dùng mock, emulator và Azure thật.

## 17. Ghi nhớ

- **Partition key path và value là một phần của địa chỉ item.** Với point read, cần container, item ID và partition key value; chỉ ID chưa đủ để định tuyến trực tiếp.
- Chọn key theo **access pattern, cardinality, phân phối tải và ranh giới transaction**. Key có skew có thể tạo hot partition dù tổng throughput còn dư.
- **Mapping Java phải khớp JSON path** mà container khai báo. `@Container`, `@Id` và `@PartitionKey` không tự migration dữ liệu hoặc đổi partition key của item cũ.
- **CosmosRepository** phù hợp CRUD/query phổ biến; `@Query` dùng Cosmos SQL-like query và cần bind tham số. Cross-partition query, pagination và RU phải được đo.
- **Transactional batch chỉ nguyên tử trong cùng logical partition key**; ETag/`@Version` giúp phát hiện cập nhật stale nhưng application phải xử lý conflict.
- Đổi partition key là **migration dữ liệu**, không chỉ sửa annotation. Cần container đích, backfill, đồng bộ thay đổi, đối soát và cutover có rollback.
- Kiểm thử mapping/repository bằng emulator, sau đó kiểm tra identity, native data-plane RBAC, quota và failover trên Azure thật.
