# Tích hợp Azure Cosmos DB bằng Spring Data Cosmos

**Azure Cosmos DB for NoSQL** là dịch vụ cơ sở dữ liệu phân tán toàn cầu, lưu dữ liệu dạng item JSON trong container. Khi tích hợp với Spring Boot, thư viện **Azure Spring Data Cosmos** cung cấp mô hình quen thuộc của Spring Data: entity được ánh xạ vào container, repository thực hiện CRUD và truy vấn, còn SDK Azure Cosmos DB Java xử lý giao tiếp với dịch vụ. Lớp repository giúp giảm mã truy cập dữ liệu, nhưng không làm mất các đặc tính quan trọng của Cosmos DB như **partition key, Request Units (RU), consistency, indexing và giới hạn transaction**.

Bài thuộc chương **Dữ liệu Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Trong bài này, ta tập trung vào Azure Cosmos DB for NoSQL và Spring Data Cosmos, từ cấu hình client đến thiết kế partition và vận hành truy vấn.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt account, database, container, item và logical partition trong Cosmos DB.
- Giải thích vai trò của Spring Cloud Azure starter, Spring Data Cosmos, repository/template và Azure Cosmos DB Java SDK.
- Cấu hình endpoint, database và Microsoft Entra ID/Managed Identity cho ứng dụng Spring Boot.
- Ánh xạ Java entity bằng `@Container`, `@Id`, `@PartitionKey` và viết repository sync/reactive.
- Chọn partition key theo truy vấn và tải dự kiến; thực hiện point read có cả item ID và partition key.
- Đọc RU charge, tối ưu indexing/query, sử dụng optimistic locking và transaction trong phạm vi một logical partition.
- Kiểm thử với Cosmos DB Emulator và môi trường Azure thật, chẩn đoán lỗi quyền, partition, throttling và consistency.

## 2. Azure Cosmos DB for NoSQL và vị trí của Spring Data Cosmos

Azure Cosmos DB hỗ trợ nhiều API tương thích như NoSQL, MongoDB, Cassandra, Gremlin và Table. **Spring Data Cosmos trong bài này nhắm tới Azure Cosmos DB for NoSQL** (tên cũ thường gặp là SQL API). Đây là database dạng document/item JSON với ngôn ngữ truy vấn SQL-like riêng của Cosmos DB; nó **không phải** cơ sở dữ liệu quan hệ SQL Server/PostgreSQL và không cung cấp mô hình join/transaction liên bảng như JPA.

Các thành phần chính:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Account** | Ranh giới dịch vụ, endpoint, region, consistency và cấu hình toàn cục | Một Cosmos DB account cho môi trường production |
| **Database** | Nhóm container, có thể chia sẻ throughput tùy cấu hình | `orders-db` |
| **Container** | Ranh giới lưu item, partition key, indexing policy và throughput | `orders` |
| **Item** | Một tài liệu JSON có `id` và partition key | Một order của khách hàng |
| **Logical partition** | Nhóm item có cùng partition key value | Tất cả order có `tenantId = tenant-42` |
| **Physical partition** | Đơn vị hạ tầng mà dịch vụ tự quản lý để phân phối dữ liệu và throughput | Ứng dụng không tự chỉ định vị trí physical partition |

~~~mermaid
flowchart TD
    A[Cosmos DB account] --> D[Database: orders-db]
    D --> C[Container: orders]
    C --> P1[Logical partition tenant-42]
    C --> P2[Logical partition tenant-77]
    C --> P3[Logical partition tenant-91]
    P1 --> I1[Item order-1001]
    P1 --> I2[Item order-1002]
    P2 --> I3[Item order-2001]
    P3 --> I4[Item order-3001]
~~~

Partition key value và item ID cùng xác định một item trong container. Thiết kế partition ảnh hưởng trực tiếp đến khả năng scale, phân phối RU, chi phí truy vấn và phạm vi transaction. Vì vậy, khi dùng Spring Data Cosmos, **chọn partition key là quyết định thiết kế dữ liệu**, không phải chỉ là thêm một annotation để repository chạy được.

## 3. Các lớp tích hợp trong Spring Boot

Đường đi của một thao tác đọc/ghi thường là:

~~~mermaid
flowchart LR
    H[Controller / application service] --> R[CosmosRepository]
    R --> T[CosmosTemplate / ReactiveCosmosTemplate]
    T --> S[Azure Cosmos DB Java SDK]
    S --> N[HTTPS / Direct or Gateway mode]
    N --> C[Azure Cosmos DB for NoSQL]
    A[Spring Cloud Azure auto-configuration] -. tạo client / template .-> T
    I[Managed Identity / TokenCredential] -. xác thực .-> S
~~~

- **Spring Cloud Azure starter** gom dependency và auto-configuration, giúp Spring tạo/cấu hình client và các thành phần tích hợp.
- **Spring Data Cosmos** cung cấp mapping entity, repository, query method, `CosmosTemplate` và `ReactiveCosmosTemplate`.
- **Azure Cosmos DB Java SDK** thực hiện request, quản lý kết nối, retry, token và diagnostics.
- **Cosmos DB service** kiểm tra quyền, partition, indexing, consistency và RU rồi trả kết quả.

Repository là API tiện dụng cho thao tác phổ biến. Khi cần tính năng SDK chuyên biệt như change feed processor, transactional batch nâng cao, stored procedure hoặc diagnostics chi tiết, ứng dụng có thể dùng SDK client được Spring quản lý. Không cần bỏ Spring Data chỉ vì một use case cần thêm một lời gọi SDK.

## 4. Thêm dependency và quản lý phiên bản

### 4.1. Dùng Spring Cloud Azure starter cho Spring Data Cosmos

Với dự án Spring Boot dùng hệ sinh thái Spring Cloud Azure, có thể import BOM tương thích rồi thêm starter dữ liệu Cosmos:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-data-cosmos</artifactId>
    </dependency>
</dependencies>
~~~

Đặt `spring-cloud-azure.version` theo ma trận tương thích giữa **Spring Boot, Spring Cloud Azure và Spring Data Cosmos**. Các nhánh thư viện khác nhau hỗ trợ những dòng Spring Boot khác nhau; không lấy một version mới nhất bất kỳ rồi ghép với dự án cũ. Tài liệu Spring Cloud Azure hiện phân biệt các dòng 5.x, 6.x và 7.x theo dòng Spring Boot; hãy kiểm tra version mapping tại thời điểm nâng cấp.

### 4.2. Dùng trực tiếp thư viện Azure Spring Data Cosmos

Nếu ứng dụng tự cấu hình Cosmos SDK thay vì dùng Spring Cloud Azure starter, dependency chính là:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-spring-data-cosmos</artifactId>
</dependency>
~~~

Trong cấu hình trực tiếp, ứng dụng có thể mở rộng `AbstractCosmosConfiguration`, khai báo `CosmosClientBuilder` và bật `@EnableCosmosRepositories`. Không nên đồng thời tự tạo trùng client/template với auto-configuration của starter. Chọn **một cơ chế sở hữu client rõ ràng**, rồi kiểm tra bean graph và lifecycle khi khởi động.

## 5. Cấu hình endpoint, database và danh tính

Ví dụ cấu hình cho Spring Cloud Azure starter:

~~~yaml
spring:
  cloud:
    azure:
      cosmos:
        endpoint: ${AZURE_COSMOS_ENDPOINT}
        database: orders-db
        credential:
          managed-identity-enabled: true
          # Chỉ khai báo client-id khi dùng user-assigned identity:
          # client-id: ${AZURE_MANAGED_IDENTITY_CLIENT_ID}
~~~

`AZURE_COSMOS_ENDPOINT` là endpoint của account, thường có dạng `https://<account>.documents.azure.com:443/`. `database` là database ứng dụng sử dụng. Khi chạy trên Azure, **Managed Identity** cho phép workload lấy token Microsoft Entra ID mà không lưu account key trong cấu hình. Nếu dùng user-assigned identity, thêm client ID tương ứng; với system-assigned identity thì không cần client ID.

Ở máy phát triển, có thể dùng `DefaultAzureCredential` để lấy danh tính từ Azure CLI, IDE hoặc credential source được Azure Identity SDK hỗ trợ. Trong môi trường production, ưu tiên Managed Identity/workload identity. Nếu buộc phải dùng account key, lưu key trong secret manager và có quy trình rotation; không commit key vào repository hoặc log.

### 5.1. Phân biệt quyền quản lý tài nguyên và quyền dữ liệu

Cosmos DB for NoSQL có **native data-plane RBAC** riêng, tách biệt với Azure Resource Manager control-plane RBAC:

| Role dữ liệu dựng sẵn | Quyền chính |
| --- | --- |
| **Cosmos DB Built-in Data Reader** | Đọc item, chạy query và đọc change feed |
| **Cosmos DB Built-in Data Contributor** | Tạo, đọc, cập nhật và xóa item |

Gán role cho identity của workload ở scope nhỏ nhất phù hợp (account/database/container nếu khả dụng). Quyền **Contributor** thường phù hợp với service cần ghi dữ liệu; service chỉ đọc nên dùng Reader hoặc custom data role hẹp hơn. Việc tạo account, database, container hoặc thay đổi cấu hình quản trị có thể cần **control-plane role** riêng. Có quyền đọc/ghi item không đồng nghĩa có quyền provisioning tài nguyên.

Ví dụ: một API chỉ thao tác container `orders` cần quyền data-plane trên container đó. Không cấp quyền quản trị subscription chỉ để service ghi order. Khi nhận lỗi 403, kiểm tra principal thực tế, role assignment, scope, data action và endpoint/account.

### 5.2. Bật repository scanning

Với cách cấu hình repository tường minh, có thể khai báo:

~~~java
import com.azure.spring.data.cosmos.repository.config.EnableCosmosRepositories;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCosmosRepositories(basePackages = "com.example.orders.persistence")
public class CosmosRepositoryConfiguration {
}
~~~

Nếu starter/phiên bản đang dùng đã bật repository scanning theo cấu hình của ứng dụng, không tạo thêm cấu hình scanning trùng. Đặt package repository rõ ràng để tránh quét nhầm module hoặc tạo hai bean repository cho cùng entity.

## 6. Ánh xạ entity vào container

Giả sử ứng dụng quản lý đơn hàng theo tenant. Mỗi item có `id`, `tenantId`, trạng thái, tổng tiền và thời điểm tạo. Container dùng `/tenantId` làm partition key:

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

Các annotation quan trọng:

- `@Container` gắn entity với tên container và một số cấu hình container như auto-create, TTL, throughput hoặc partition path tùy phiên bản.
- `@Id` ánh xạ field Java thành system property `id` của item. Nếu field đã tên `id`, thư viện có thể ánh xạ theo quy ước; dùng annotation giúp rõ ý định.
- `@PartitionKey` xác định field Java tương ứng với partition key của container.
- `autoCreateContainer = false` phù hợp với production khi container được provisioning bằng IaC/deployment pipeline. Tránh để mỗi lần ứng dụng khởi động tự tạo hoặc thay đổi tài nguyên dữ liệu ngoài ý muốn.

Container thực tế phải được tạo với partition key path khớp entity, ví dụ `/tenantId`. Annotation không tự di chuyển dữ liệu hiện có hoặc đổi partition key của container đang tồn tại.

## 7. Repository: CRUD, derived query và point read

Spring Data Cosmos hỗ trợ repository đồng bộ qua `CosmosRepository` và repository bất đồng bộ qua `ReactiveCosmosRepository`. Ví dụ đồng bộ:

~~~java
import com.azure.spring.data.cosmos.repository.CosmosRepository;
import java.util.List;
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

Repository cung cấp các thao tác quen thuộc như `save`, `findAll`, tìm theo ID, xóa item và query method. `@Query` sử dụng ngôn ngữ truy vấn của Cosmos DB for NoSQL, không phải JPQL của JPA. Cần đọc query plan/RU charge và kiểm tra partition key có xuất hiện trong predicate hay không.

### 7.1. Đọc item theo ID và partition key

Với container partitioned, một point read hiệu quả cần **cả item ID và partition key value**:

~~~java
import com.azure.cosmos.models.PartitionKey;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    public Optional<OrderDocument> findOrder(
            String tenantId, String orderId) {
        return orders.findById(orderId, new PartitionKey(tenantId));
    }
}
~~~

Nếu chỉ có ID mà không có partition key, thư viện có thể phải thực hiện query rộng hơn tùy API và version; không giả định mọi `findById(id)` đều là point read. Khi endpoint đã xác thực tenant, truyền partition value đã được xác minh vào thao tác đọc. Không tin partition key do caller tùy ý cung cấp mà bỏ qua authorization.

### 7.2. Derived query và truy vấn có tham số

Ví dụ `findByTenantIdAndStatus` cho thấy Spring Data có thể suy ra query từ tên method. Với truy vấn phức tạp hơn, dùng `@Query` và `@Param` để viết rõ predicate. Các giá trị tham số phải được bind, không nối chuỗi input vào query. Truy vấn có partition key equality thường có thể được route hiệu quả hơn; truy vấn thiếu partition key có thể trở thành cross-partition query.

Không phải mọi từ khóa của Spring Data JPA đều có cùng semantics hoặc được hỗ trợ trong Spring Data Cosmos. Kiểm tra tài liệu/version và query thực tế trước khi dựa vào derived method phức tạp.

### 7.3. Phân trang

Spring Data Cosmos hỗ trợ các kiểu như `Pageable`, `Slice` và `Sort` tùy query/API. Cosmos DB sử dụng continuation token để tiếp tục query; số item trả về trong một page có thể **ít hơn page size yêu cầu** do RU/điều kiện thực thi. Không tự suy ra tổng số trang cố định hoặc dùng `offset` lớn như một cơ sở dữ liệu quan hệ mà chưa đo chi phí.

Với danh sách lớn, ưu tiên duyệt theo continuation/page tiếp theo và chỉ lấy field cần thiết. Không tải toàn bộ container vào bộ nhớ chỉ để phân trang ở Java.

## 8. Chọn partition key theo access pattern

Partition key quyết định cách item được phân phối và cách query được định tuyến. Một key tốt cần:

- Có cardinality đủ cao để phân phối dữ liệu và RU.
- Xuất hiện trong các truy vấn phổ biến, nhất là point read hoặc filter equality.
- Có giá trị ổn định trong suốt vòng đời item.
- Không tạo một logical partition quá lớn hoặc quá nóng.

Ví dụ `tenantId` phù hợp nếu phần lớn request luôn thao tác dữ liệu của một tenant và tải giữa các tenant tương đối cân bằng. Nếu một tenant lớn tạo phần lớn lưu lượng, `tenantId` có thể trở thành **hot partition**. Có thể cân nhắc hierarchical partition key hoặc synthetic key, nhưng phải phân tích query pattern và yêu cầu transaction trước.

| Lựa chọn | Ưu điểm | Rủi ro |
| --- | --- | --- |
| `/tenantId` | Truy vấn theo tenant thuận tiện, dữ liệu tenant được gom cùng logical partition | Tenant quá lớn/tải cao có thể tạo hot partition và chạm giới hạn dung lượng |
| `/id` | Cardinality cao, point read rất thuận tiện khi luôn có ID | Query theo tenant/status thường phải cross-partition |
| Synthetic key như `tenantId#month` | Phân tán dữ liệu/tải theo tenant và thời gian | Query chỉ theo tenant cần nhiều partition; transaction bị chia nhỏ |
| Hierarchical key như `tenantId/orderGroup` | Hỗ trợ nhiều cấp truy vấn và phân phối | Cần thiết kế thứ tự cấp key và predicate phù hợp |

**Partition key là bất biến sau khi tạo item**. Nếu cần đổi giá trị partition key, phải tạo item ở partition/container đích rồi xóa item cũ; không có thao tác update tại chỗ để di chuyển item giữa logical partition. Thay partition key cho container hiện hữu thường cần migration sang container mới.

Trong API for NoSQL, logical partition còn là phạm vi transaction. Theo tài liệu dịch vụ hiện hành, logical partition có giới hạn dung lượng và throughput riêng; cần xem quota hiện tại trước khi thiết kế cho tenant cực lớn. Đừng chọn key chỉ dựa trên tên field thuận tiện.

## 9. RU, throughput và chi phí truy vấn

Cosmos DB đo chi phí thao tác bằng **Request Units (RU)**. RU là đơn vị chuẩn hóa tài nguyên xử lý, I/O và bộ nhớ; mỗi request đọc, ghi, xóa hoặc query đều tiêu thụ RU. Response/diagnostics có thể cung cấp request charge để nhóm phát triển hiểu thao tác nào tốn tài nguyên.

Các chế độ throughput phổ biến:

| Chế độ | Cách cấp năng lực | Phù hợp |
| --- | --- | --- |
| **Provisioned throughput** | Cấp RU/s cho database hoặc container | Workload ổn định, cần kiểm soát năng lực |
| **Autoscale** | Throughput tự điều chỉnh trong giới hạn cấu hình | Lưu lượng biến động, có đỉnh tải |
| **Serverless** | Tính theo RU tiêu thụ, không cần provision RU/s cố định | Workload không liên tục hoặc lưu lượng thấp/khó dự đoán, trong giới hạn service |

Điểm đọc theo **ID + partition key** thường rẻ hơn query phải quét nhiều partition. RU thực tế còn phụ thuộc kích thước item, số property, indexing policy, predicate, số item trả về, consistency và số region.

### 9.1. Indexing policy

Container mặc định có indexing policy tự động index nhiều property để hỗ trợ truy vấn linh hoạt. Điều này tiện lúc đầu nhưng index nhiều field có thể làm tăng RU của write và dung lượng index. Với workload đã biết query pattern, xem xét include/exclude path, composite index và loại index cần thiết. Thay indexing policy có thể kích hoạt quá trình index transformation; theo dõi trạng thái trước khi phụ thuộc vào index mới.

Spring Data Cosmos có annotation/configuration để tùy chỉnh indexing policy như `@CosmosIndexingPolicy` ở những version hỗ trợ. Hãy quản lý container/index trong IaC hoặc migration có kiểm soát khi production; không thay đổi policy tùy tiện từ nhiều instance ứng dụng.

### 9.2. Query metrics và diagnostics

Spring Data Cosmos hỗ trợ cấu hình query metrics, index metrics và response diagnostics qua `CosmosConfig`/cấu hình tương ứng theo version. Khi query chậm hoặc tốn RU:

1. Ghi nhận RU charge, latency, status/substatus và activity/request ID.
2. Bật query metrics trong môi trường kiểm thử/điều tra.
3. Xem query có filter theo partition key không, có dùng index không và trả quá nhiều field/item không.
4. Kiểm tra indexing policy, kích thước document, pagination và parallelism.
5. Đo lại trên dữ liệu và throughput gần với production.

Không log credential, token hoặc toàn bộ document có PII. Diagnostics có thể chứa metadata nhạy cảm; cấu hình mức log và quyền truy cập log phải phù hợp.

## 10. Consistency và phân phối đa vùng

Cosmos DB for NoSQL cung cấp năm consistency level:

1. **Strong** — đọc thấy phiên bản mới nhất đã commit theo bảo đảm linearizability.
2. **Bounded staleness** — độ trễ dữ liệu được giới hạn theo cấu hình.
3. **Session** — bảo đảm đọc-your-writes và monotonic reads trong session phù hợp.
4. **Consistent prefix** — thứ tự ghi được giữ, nhưng có thể đọc trạng thái cũ hơn.
5. **Eventual** — các bản sao hội tụ theo thời gian, không có bảo đảm thứ tự mạnh.

Consistency level được cấu hình ở account và có thể được điều chỉnh theo client/request trong giới hạn dịch vụ cho phép. Mức mạnh hơn có thể tăng latency/chi phí đọc và ảnh hưởng khả năng phục vụ trong tình huống đa vùng. Không chọn consistency chỉ theo tên “mạnh nhất”; hãy xác định nghiệp vụ có cần đọc-your-writes, thứ tự, stale tolerance hay không.

Khi bật nhiều region, cần hiểu preferred regions, read/write region, failover và conflict resolution nếu có multi-region writes. Một request thành công ở một vùng không có nghĩa mọi replica đã quan sát cùng dữ liệu ngay lập tức ở mọi consistency level. Test đọc sau ghi và failover trên topology thật nếu use case phụ thuộc.

## 11. Transaction, optimistic locking và giới hạn atomicity

### 11.1. Transaction chỉ trong một logical partition

Cosmos DB for NoSQL hỗ trợ ACID transaction với snapshot isolation trong **cùng một logical partition key**. Có thể sử dụng transactional batch để nhóm create/replace/delete/patch point operations cùng partition; nếu một thao tác thất bại, batch được rollback. Stored procedures/triggers cũng có transaction scope theo logical partition.

Không có transaction nguyên tử xuyên nhiều logical partition hoặc nhiều container. Vì vậy, không áp dụng tư duy JPA `@Transactional` rồi kỳ vọng cập nhật item ở các tenant khác nhau cùng commit/rollback.

Ví dụ hai item cùng `tenantId = tenant-42` có thể được đặt trong một transactional batch nếu cùng container và đúng điều kiện API; item thuộc tenant khác không nằm trong cùng batch transaction.

### 11.2. Optimistic locking bằng ETag

Spring Data Cosmos hỗ trợ optimistic locking cho các container/operation được hỗ trợ. Có thể ánh xạ ETag vào field `_etag` với `@Version`:

~~~java
import com.azure.spring.data.cosmos.core.mapping.Container;
import com.azure.spring.data.cosmos.core.mapping.PartitionKey;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;

@Container(containerName = "inventory")
public class InventoryItem {
    @Id
    private String id;

    @PartitionKey
    private String warehouseId;

    private int availableQuantity;

    @Version
    private String _etag;

    public InventoryItem() {}
}
~~~

Khi hai tiến trình cùng đọc một version rồi cập nhật, thao tác từ tiến trình dùng ETag cũ có thể bị từ chối thay vì âm thầm ghi đè dữ liệu mới. Application service cần bắt conflict, đọc lại và áp dụng quy tắc nghiệp vụ (ví dụ tính lại tồn kho). Không retry update mù quáng với payload cũ.

## 12. Change Feed và xử lý thay đổi

Change Feed cho phép ứng dụng đọc các thay đổi item để xây dựng projection, đồng bộ search index/cache, phát sự kiện hoặc chuyển dữ liệu sang hệ thống khác. Đây là API ở tầng SDK/processor; không nên nhầm nó với việc gọi `findAll()` theo lịch.

Một số điểm quan trọng:

- Thứ tự thay đổi được bảo đảm trong phạm vi partition key value; không có thứ tự toàn cục giữa các partition key.
- Latest version mode tập trung vào phiên bản mới nhất của item; các update trung gian có thể không được phát ra nếu item thay đổi nhiều lần nhanh chóng.
- Latest version mode không cung cấp delete event như một log đầy đủ; có thể dùng soft-delete marker nếu consumer cần biết trạng thái xóa.
- All versions and deletes mode có retention gắn với continuous backup của account; không xem đây là event log lưu vô hạn.
- Consumer cần checkpoint, xử lý idempotent, quan sát lag và có chiến lược phục hồi khi restart.

Nếu dùng change feed để phát event ra message broker, không giả định thao tác đọc feed và publish event là một transaction duy nhất. Cần lưu checkpoint đúng thời điểm và xử lý trường hợp publish thành công nhưng checkpoint chưa được ghi (event có thể được phát lại).

## 13. Xử lý lỗi và retry

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| **401/403** | Token/key không hợp lệ, identity sai, thiếu native data-plane role hoặc scope | Xác minh principal, Entra token, role assignment và quyền dữ liệu |
| **404** | Sai endpoint/account/database/container, item không tồn tại hoặc partition key không đúng | Kiểm tra tên resource, database, container, item ID và partition value |
| **409 Conflict** | Item ID/unique key đã tồn tại hoặc conflict theo thao tác | Ánh xạ thành conflict nghiệp vụ; không retry giống lỗi mạng |
| **412 Precondition Failed** | ETag/version/precondition không còn hợp lệ | Đọc lại, xử lý optimistic concurrency và quyết định cập nhật lại |
| **429 Too Many Requests** | Vượt RU/s hoặc partition bị nóng | Tôn trọng retry-after, giảm concurrency, tối ưu partition/query/index và đánh giá throughput |
| Timeout / connection error | Network, endpoint, TLS, DNS hoặc response bị mất | Kiểm tra diagnostics; với write, kết quả có thể chưa rõ nên cần operation ID/idempotency |
| Query chậm, RU cao | Cross-partition, index không phù hợp, payload/query lớn | Xem query metrics, partition predicate, projection và indexing policy |

Cosmos SDK có cơ chế retry cho một số lỗi throttling/transient. Không thêm retry vô hạn ở repository/service bên ngoài; nhiều tầng retry có thể nhân số lần request. Giới hạn tổng deadline, concurrency và số lần thử; tôn trọng `Retry-After` khi SDK cung cấp.

Với thao tác ghi bị timeout, không thể luôn kết luận item chưa được ghi. Dùng ID/operation ID ổn định, đọc đối chiếu theo partition key và thiết kế idempotency trước khi gửi lại. Một `save` có semantics upsert không thay thế quy tắc nghiệp vụ “chỉ tạo một lần”.

## 14. Kiểm thử bằng Emulator và Azure thật

### 14.1. Unit test

Unit test application service nên mock repository/port để kiểm tra quy tắc nghiệp vụ: tenant nào được truy cập, trạng thái nào được chuyển, dữ liệu nào được lưu. Không cần Azure credentials hoặc network.

### 14.2. Cosmos DB Emulator

Azure Cosmos DB Emulator cung cấp môi trường phát triển/kiểm thử cục bộ cho API được hỗ trợ. HTTPS certificate của emulator là **self-signed**; Java runtime cần trust certificate theo hướng dẫn emulator trước khi SDK kết nối. Không tắt xác minh TLS tùy tiện để làm test chạy được.

Integration test nên kiểm tra:

- Entity được serialize/deserialize đúng, field `id` và partition key có giá trị.
- Repository save/read/query theo đúng partition.
- Query cross-partition và pagination hoạt động theo mong đợi.
- Optimistic locking/conflict được ánh xạ đúng.
- Container provisioning và indexing policy không bị thay đổi ngoài ý muốn.

### 14.3. Cloud integration test

Emulator không thay thế kiểm thử identity và role assignment trên Azure thật. Tạo account/database/container test riêng, dùng Managed Identity hoặc principal thử nghiệm, cấp native data-plane role tối thiểu và kiểm tra:

- Token Entra ID được lấy từ đúng workload identity.
- Data-plane role có quyền trên đúng scope.
- Endpoint, preferred region, firewall/private network và DNS đúng.
- RU, throttling, diagnostics và failover phù hợp workload.
- Cleanup không xóa tài nguyên dùng chung hoặc dữ liệu production.

## 15. Ví dụ luồng hoàn chỉnh: tạo và tìm đơn hàng

Một use case đơn giản có thể đi theo đường:

~~~text
POST /tenants/{tenantId}/orders
  -> Controller xác thực request
  -> Application service xác minh tenant/caller
  -> Tạo OrderDocument với id và tenantId
  -> OrderRepository.save(document)
  -> Spring Data Cosmos / CosmosTemplate
  -> Azure Cosmos DB Java SDK
  -> Cosmos DB container orders
  <- Stored item / diagnostics / RU charge
  <- HTTP 201

GET /tenants/{tenantId}/orders/{orderId}
  -> Application service
  -> OrderRepository.findById(orderId, PartitionKey(tenantId))
  -> Point read theo id + partition key
  <- OrderDocument hoặc not found
~~~

Trong luồng này, tenant ID phải đến từ context đã xác thực hoặc được kiểm tra ownership. Không để caller tự chọn partition key rồi đọc item ngoài phạm vi được phép. Nếu service trả dữ liệu nhạy cảm, lọc trường ở application/DTO trước khi gửi response.

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Chọn partition key theo field dễ viết nhưng không theo query | Cross-partition query, RU cao hoặc hot partition | Thiết kế theo access pattern và phân phối tải |
| Dùng `findById(id)` mà không truyền partition key khi đã biết key | Có thể mất lợi ích point read hoặc phải query rộng | Dùng overload có partition key phù hợp |
| Dùng Cosmos DB như SQL Server/JPA | Kỳ vọng join/transaction không được hỗ trợ tương đương | Thiết kế document và denormalize theo truy vấn |
| Tạo container tự động ở mỗi lần startup production | Khó kiểm soát throughput/index/partition policy | Provision bằng IaC; tắt auto-create khi phù hợp |
| Bật index cho mọi field mà không đo | RU write và index storage tăng | Điều chỉnh indexing policy theo query |
| Bỏ qua RU charge và 429 | Throttling lặp lại, latency tăng | Theo dõi RU, retry-after, autoscale/provisioned throughput |
| Dùng account key trong appsettings đã commit | Lộ credential, khó rotation | Managed Identity + native data-plane RBAC |
| Dùng transaction cho item thuộc nhiều partition | Không có atomicity như mong đợi | Đặt dữ liệu cần atomic cùng partition hoặc dùng saga/outbox |
| Coi change feed là event log không mất/không trùng | Bỏ sót intermediate update hoặc xử lý lặp | Chọn mode, checkpoint và idempotent consumer |
| Chỉ test emulator | Không phát hiện thiếu RBAC, private endpoint, quota | Thêm cloud smoke test bằng identity thật |

## 17. Bài tập thực hành

**Bài tập 1 — Chọn partition key.** Một SaaS lưu order của nhiều tenant. Phần lớn truy vấn lấy order theo tenant và trạng thái; một tenant lớn tạo 40% lưu lượng. So sánh `/tenantId`, `/id` và hierarchical partition key. Đề xuất cách tránh hot partition mà vẫn giữ các truy vấn quan trọng hiệu quả.

**Bài tập 2 — Repository và point read.** Viết entity `OrderDocument` với `@Container`, `@Id`, `@PartitionKey`; viết `OrderRepository` với derived query theo tenant/status. Giải thích tại sao tìm item theo ID cần partition key value.

**Bài tập 3 — RU và indexing.** Một query lọc theo tenantId, status và createdAt nhưng tốn nhiều RU. Hãy kiểm tra partition predicate, index policy, số field trả về, page size và query metrics. Đề xuất thay đổi và cách đo trước/sau.

**Bài tập 4 — Optimistic locking.** Hai worker đọc cùng một inventory item rồi cập nhật số lượng. Dùng `@Version` với ETag để tránh ghi đè mất cập nhật. Mô tả cách xử lý 412 và test race condition.

**Bài tập 5 — Transactional batch.** Một order và các order line cần được ghi atomically. Xác định các item phải dùng cùng partition key, thiết kế batch và nêu điều gì xảy ra nếu một operation thất bại. Điều gì thay đổi nếu order line thuộc partition khác?

**Bài tập 6 — Identity.** Chuyển ứng dụng từ account key sang Managed Identity. Nêu sự khác biệt giữa Azure management-plane role và Cosmos DB native data-plane role; xác định quyền tối thiểu cho service chỉ đọc và service có ghi.

**Bài tập 7 — Change Feed.** Một projection cập nhật search index từ change feed. Thiết kế checkpoint, idempotency và xử lý delete; giải thích tại sao thứ tự chỉ được bảo đảm trong partition key value và latest version mode có thể bỏ qua intermediate updates.

**Bài tập 8 — Test strategy.** Thiết kế unit test, emulator integration test và cloud smoke test cho một repository Cosmos DB. Liệt kê điều emulator không thể chứng minh về identity, RBAC, network và quota.

## 18. Ghi nhớ

- **Spring Data Cosmos là lớp Spring Data cho Azure Cosmos DB for NoSQL**, không phải JPA cho một relational database. Repository dùng client/SDK Cosmos ở bên dưới.
- **Partition key chi phối routing, RU, hot partition và phạm vi transaction.** Chọn theo access pattern; giá trị partition key không thể đổi tại chỗ sau khi item được tạo.
- **Point read cần item ID và partition key.** Query không có partition predicate có thể tốn RU và latency hơn; hãy đo query metrics và request charge.
- **RU là đơn vị chi phí xử lý của mỗi thao tác.** Kích thước item, indexing, query shape, consistency và số region đều ảnh hưởng mức tiêu thụ.
- **ACID transaction/transactional batch chỉ nằm trong một logical partition key.** Với cập nhật đồng thời, dùng ETag/`@Version` và xử lý conflict.
- **Managed Identity + Cosmos DB native data-plane RBAC** là lựa chọn ưu tiên cho workload trên Azure; quyền quản trị tài nguyên và quyền đọc/ghi dữ liệu là hai phạm vi khác nhau.
- Emulator hỗ trợ kiểm thử tích hợp nhưng không thay thế cloud test cho identity, RBAC, network, quota và failover.

## 19. Tài liệu tham khảo

- [Azure Cosmos DB Developer Guide for Java](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/how-to-guides-spring-data-cosmosdb)
- [Azure Spring Data Cosmos client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-data-cosmos-readme?view=azure-java-stable)
- [Spring Cloud Azure — modules, starters và BOM](https://github.com/Azure/azure-sdk-for-java/tree/main/sdk/spring)
- [Partitioning and horizontal scaling](https://learn.microsoft.com/en-us/azure/cosmos-db/partitioning)
- [Request Units in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/request-units)
- [Consistency level choices](https://learn.microsoft.com/en-us/azure/cosmos-db/consistency-levels)
- [Transactional batch operations](https://learn.microsoft.com/en-us/azure/cosmos-db/transactional-batch)
- [Connect using role-based access control and Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/how-to-connect-role-based-access-control)
- [Change Feed design patterns](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/change-feed-design-patterns)
