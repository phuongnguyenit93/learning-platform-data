# Ánh xạ dữ liệu và truy vấn với Spring Data Spanner

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot tích hợp dịch vụ managed của AWS, Azure và Google Cloud để truy cập dữ liệu, storage, messaging và danh tính. Trên Google Cloud, **Cloud Spanner** là cơ sở dữ liệu quan hệ phân tán theo chiều ngang, hỗ trợ SQL, giao dịch ACID và tính nhất quán mạnh. Spring Data Spanner cung cấp cách ánh xạ Java POJO thành hàng trong bảng, tạo repository và chạy truy vấn theo phong cách Spring Data.

Bài học dùng miền nghiệp vụ đơn hàng để thực hành:

1. Cấu hình Spring Boot Starter và ADC để kết nối Spanner.
2. Thiết kế bảng, khóa chính đơn/ghép và quan hệ parent-child.
3. Ánh xạ entity bằng `@Table`, `@Column`, `@PrimaryKey`, `@Interleaved` và `@NotMapped`.
4. Xây dựng `SpannerRepository` với CRUD và query methods.
5. Viết SQL có tham số bằng `@Query` và `SpannerTemplate`.
6. Chọn giữa repository, template, DML và read/write transaction.
7. Thiết kế index, schema evolution và kiểm thử bằng Spanner Emulator.
8. Phân biệt Spanner session pool với HikariCP của JDBC.

> **Phạm vi quan trọng:** Spring Data Spanner dùng GoogleSQL interface của Cloud Spanner. PostgreSQL interface của Spanner không hỗ trợ Spring Data Spanner; nếu ứng dụng dùng PostgreSQL interface, hãy chọn Spring Data JPA và cấu hình dialect/driver tương ứng. Không xem Spring Data Spanner như JPA/Hibernate với toàn bộ semantics và tính năng giống nhau.

## 1. Cloud Spanner và Spring Data Spanner

### 1.1. Cloud Spanner lưu dữ liệu như thế nào?

Cloud Spanner tổ chức dữ liệu thành database, table, row và column. Mỗi table có primary key xác định duy nhất một row. Primary key cũng quyết định thứ tự logic và cách Spanner phân phối các key range giữa các server.

Spanner phù hợp với hệ thống cần dữ liệu quan hệ, giao dịch nhất quán và khả năng mở rộng ngang. Tuy nhiên, thiết kế key và index ảnh hưởng trực tiếp đến phân phối ghi/đọc. Một schema phù hợp với database đơn máy có thể tạo hotspot khi chạy trên hệ thống phân tán.

### 1.2. Spring Data Spanner nằm ở đâu?

~~~mermaid
flowchart TD
    API["Spring Boot service"] --> REPO["SpannerRepository"]
    API --> TEMPLATE["SpannerTemplate / SpannerOperations"]
    REPO --> MAP["Mapping context + converters"]
    TEMPLATE --> MAP
    MAP --> CLIENT["Cloud Spanner Java client"]
    CLIENT --> SESSIONS["gRPC session pool"]
    SESSIONS --> DB["Cloud Spanner database"]
~~~

| Thành phần | Vai trò |
| --- | --- |
| Entity POJO | Mô tả một row trong bảng Spanner |
| Mapping annotations | Ánh xạ Java property, column, primary key và interleaved rows |
| `SpannerRepository` | CRUD và query methods được Spring Data tạo implementation |
| `SpannerTemplate` | API đọc, ghi, truy vấn SQL, DML và transaction |
| `SpannerDatabaseAdminTemplate` | Hỗ trợ thao tác quản trị database/schema |
| Cloud Spanner Java client | Giao tiếp API/gRPC với Spanner |
| Session pool | Tái sử dụng Spanner sessions cho các thao tác database |

Starter tự cấu hình các bean thông dụng như `SpannerTemplate`, `SpannerDatabaseAdminTemplate` và repository được phát hiện trong package. Khi cần thao tác chuyên sâu, có thể dùng `DatabaseClient` của Google Cloud Java client.

### 1.3. Phân biệt GoogleSQL và PostgreSQL interface

Cloud Spanner hỗ trợ GoogleSQL dialect và PostgreSQL interface. Hai giao diện có cú pháp SQL, kiểu dữ liệu và hệ sinh thái driver khác nhau.

- Spring Data Spanner sử dụng mapping và API riêng cho GoogleSQL interface.
- PostgreSQL interface không tương thích với Spring Data Spanner.
- Nếu yêu cầu PostgreSQL protocol, hãy đánh giá Spring Data JPA hoặc JDBC driver tương ứng.
- Không trộn annotation Spring Data Spanner với entity JPA rồi kỳ vọng cùng một repository tự chọn dialect.

Bài này dùng GoogleSQL.

## 2. Thêm dependency và cấu hình Spring Boot

### 2.1. Maven dependency

Dùng Spring Cloud GCP BOM để quản lý phiên bản các module tương thích. Không tự chọn phiên bản starter độc lập với Spring Boot và BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-data-spanner</artifactId>
    </dependency>
</dependencies>
~~~

`${spring-cloud-gcp.version}` là phiên bản BOM do dự án chọn. Kiểm tra compatibility matrix giữa Spring Boot, Spring Framework on Google Cloud và Java version trước khi chốt BOM. Starter kéo theo Cloud Spanner Java client; thường không cần khai báo client library riêng.

### 2.2. Cấu hình project, instance và database

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-platform-dev
      spanner:
        project-id: rental-platform-dev
        instance-id: orders-spanner
        database: orders
~~~

Các property quan trọng:

| Property | Ý nghĩa |
| --- | --- |
| `spring.cloud.gcp.spanner.project-id` | Project chứa Spanner; có thể ghi đè project ID chung |
| `spring.cloud.gcp.spanner.instance-id` | ID của Spanner instance |
| `spring.cloud.gcp.spanner.database` | Database mặc định |
| `spring.cloud.gcp.spanner.enabled` | Bật/tắt autoconfiguration của Spanner |
| `spring.cloud.gcp.spanner.emulator.enabled` | Dùng Spanner Emulator trong môi trường phát triển/test |
| `spring.cloud.gcp.spanner.emulator-host` | Host/port emulator, mặc định thường là `localhost:9010` |

Project ID, instance ID và database name phải khớp tài nguyên thật. Instance ID khác project ID và khác database name.

### 2.3. ADC và service account

Spring Data Spanner sử dụng Google Cloud credentials từ Application Default Credentials (ADC). Với local development, có thể dùng credentials được Google Cloud CLI tạo. Với production, ưu tiên service account gắn trực tiếp với Cloud Run, GKE Workload Identity Federation hoặc Compute Engine.

Các IAM role thường gặp:

- `roles/spanner.databaseUser`: đọc/ghi dữ liệu, chạy SQL và các thao tác database được role cho phép.
- `roles/spanner.databaseReader`: chỉ đọc dữ liệu và chạy truy vấn đọc.
- `roles/spanner.databaseAdmin`: dành cho tác vụ quản trị database/schema.

`roles/spanner.databaseUser` có thể bao gồm quyền cập nhật schema; nếu runtime cần phạm vi hẹp hơn, cân nhắc fine-grained access control hoặc custom role. Tách service account runtime khỏi principal chạy schema migration. Không gán `roles/spanner.admin` toàn project chỉ để ứng dụng đọc/ghi dữ liệu.

### 2.4. Quyền IAM khác quyền ở tầng ứng dụng

IAM quyết định workload được phép truy cập tài nguyên Spanner. Spring Security hoặc business authorization trong ứng dụng quyết định người dùng cuối được phép xem/sửa đơn hàng nào.

Ví dụ, service account có thể được phép đọc toàn bộ database, nhưng API vẫn phải kiểm tra `customerId` của người đang đăng nhập trước khi trả về đơn hàng. Không dùng IAM database role thay thế authorization theo tenant hoặc user.

## 3. Thiết kế schema trước khi tạo entity

### 3.1. Ví dụ mô hình đơn hàng

Một đơn hàng có nhiều dòng hàng. Ta dùng hai bảng:

~~~sql
CREATE TABLE Orders (
    OrderId STRING(36) NOT NULL,
    CustomerId STRING(36) NOT NULL,
    Status STRING(20) NOT NULL,
    CreatedAt TIMESTAMP NOT NULL
) PRIMARY KEY (OrderId);

CREATE TABLE OrderItems (
    OrderId STRING(36) NOT NULL,
    ItemId STRING(36) NOT NULL,
    ProductId STRING(36) NOT NULL,
    Quantity INT64 NOT NULL,
    UnitPrice NUMERIC NOT NULL
) PRIMARY KEY (OrderId, ItemId),
  INTERLEAVE IN PARENT Orders ON DELETE CASCADE;

CREATE INDEX OrdersByCustomerCreatedAt
ON Orders(CustomerId, CreatedAt DESC);
~~~

Trong thiết kế này:

- `Orders` là bảng cha.
- `OrderItems` là bảng con interleaved trong `Orders`.
- Primary key của `OrderItems` bắt đầu bằng toàn bộ key của bảng cha theo đúng thứ tự, sau đó là key riêng `ItemId`.
- Index `OrdersByCustomerCreatedAt` hỗ trợ truy vấn theo khách hàng và thời gian tạo.

Interleaving đặt row con gần row cha trong cách lưu trữ của Spanner. Đây là lựa chọn phù hợp khi vòng đời và truy vấn của child gắn chặt với parent. Nếu quan hệ chỉ là tham chiếu lỏng hoặc cần truy cập child độc lập rộng rãi, hãy cân nhắc foreign key hay mô hình bảng độc lập.

### 3.2. Chọn primary key để tránh hotspot

Spanner phân phối dữ liệu theo key range. Nếu workload liên tục ghi key tăng tuần tự, chẳng hạn timestamp hoặc số tự tăng làm key đầu tiên, các lần ghi mới có thể dồn về một range và tạo hotspot.

Các hướng thiết kế:

- UUID v4 ngẫu nhiên cho khóa độc lập, phân tán tốt khi ghi.
- Dùng natural key ổn định nếu nó phù hợp với truy cập và không tạo phân bố lệch.
- Đảo thứ tự cột trong composite key để tránh monotonic value ở vị trí đầu.
- Dùng bit-reversed sequence hoặc shard prefix khi cần khóa số.
- Chọn thứ tự key theo pattern đọc/ghi, không chỉ theo tính tiện lợi của entity.

Không mặc định dùng `AUTO_INCREMENT` hoặc timestamp làm cột đầu primary key cho bảng ghi lớn. UUID v1 chứa thành phần thời gian ở bit cao không có đặc tính phân tán như UUID v4.

### 3.3. Composite primary key

Composite key có thứ tự. Ví dụ:

~~~sql
PRIMARY KEY (OrderId, ItemId)
~~~

Khác với hai cột độc lập, thứ tự key quyết định thứ tự sắp xếp và phạm vi key. Khi khai báo entity, `keyOrder = 1` phải ứng với `OrderId`, còn `keyOrder = 2` ứng với `ItemId`.

Với interleaved child, các cột primary key của parent phải đứng trước theo cùng thứ tự. Không thể tùy ý đổi thứ tự annotation mà không thay đổi schema tương ứng.

### 3.4. Index theo query pattern

Spanner không tự tạo mọi secondary index chỉ vì entity có property. Hãy liệt kê các truy vấn chính trước khi tạo index:

| Query pattern | Thiết kế gợi ý |
| --- | --- |
| Lấy đơn theo ID | Primary key `OrderId` |
| Lấy đơn của khách hàng, mới nhất trước | Index `CustomerId, CreatedAt DESC` |
| Lấy item trong một đơn | Composite key `OrderId, ItemId` |
| Lấy đơn theo trạng thái và thời gian | Cân nhắc index bắt đầu bằng `Status` rồi `CreatedAt` nếu workload thực sự cần |

Mỗi index làm tăng chi phí ghi và lưu trữ. Tránh tạo index cho mọi cột. Xác minh query plan và metric trước khi thêm index vào production.

## 4. Ánh xạ entity bằng annotation

### 4.1. Entity cho bảng cha

Spring Data Spanner ánh xạ POJO sang table. Các annotation thuộc package `com.google.cloud.spring.data.spanner.core.mapping`:

~~~java
import com.google.cloud.Timestamp;
import com.google.cloud.spring.data.spanner.core.mapping.Column;
import com.google.cloud.spring.data.spanner.core.mapping.Interleaved;
import com.google.cloud.spring.data.spanner.core.mapping.NotMapped;
import com.google.cloud.spring.data.spanner.core.mapping.PrimaryKey;
import com.google.cloud.spring.data.spanner.core.mapping.Table;

import java.util.ArrayList;
import java.util.List;

@Table(name = "Orders")
public class Order {

    @PrimaryKey
    @Column(name = "OrderId")
    private String orderId;

    @Column(name = "CustomerId")
    private String customerId;

    @Column(name = "Status")
    private String status;

    @Column(name = "CreatedAt")
    private Timestamp createdAt;

    @Interleaved
    private List<OrderItem> items = new ArrayList<>();

    @NotMapped
    private String displayLabel;

    public Order() {
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Timestamp getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Timestamp createdAt) {
        this.createdAt = createdAt;
    }

    public List<OrderItem> getItems() {
        return items;
    }

    public void setItems(List<OrderItem> items) {
        this.items = items;
    }
}
~~~

`@Table` chỉ định tên bảng. `@PrimaryKey` bắt buộc ngay cả khi bảng chỉ có một cột khóa. `@Column` ánh xạ property vào tên cột cụ thể. `@Interleaved` khai báo collection row con interleaved. `@NotMapped` đánh dấu property chỉ dùng trong ứng dụng và không lưu trong Spanner.

### 4.2. Entity cho bảng con

~~~java
import com.google.cloud.spring.data.spanner.core.mapping.Column;
import com.google.cloud.spring.data.spanner.core.mapping.PrimaryKey;
import com.google.cloud.spring.data.spanner.core.mapping.Table;

import java.math.BigDecimal;

@Table(name = "OrderItems")
public class OrderItem {

    @PrimaryKey(keyOrder = 1)
    @Column(name = "OrderId")
    private String orderId;

    @PrimaryKey(keyOrder = 2)
    @Column(name = "ItemId")
    private String itemId;

    @Column(name = "ProductId")
    private String productId;

    @Column(name = "Quantity")
    private long quantity;

    @Column(name = "UnitPrice")
    private BigDecimal unitPrice;

    public OrderItem() {
    }

    // Constructors, getters and setters omitted for brevity.
}
~~~

Hai property `orderId` và `itemId` tạo thành composite primary key. Chúng phải trùng thứ tự với DDL. `BigDecimal` phù hợp khi cần kiểu số thập phân chính xác; tránh dùng `double` cho giá tiền.

### 4.3. Naming strategy

Theo naming strategy mặc định, property Java dạng camelCase có thể được ánh xạ sang PascalCase. Ví dụ `customerId` có thể thành `CustomerId`. Nếu schema đã dùng tên cột khác, hãy khai báo `@Column(name = "...")` rõ ràng.

Không dựa vào quy tắc ngầm khi schema có snake_case, tên legacy hoặc cột có cách viết đặc biệt. Mapping tường minh giúp giảm lỗi khi đổi tên property Java.

### 4.4. Primary key và constructor

Spring Data Spanner hỗ trợ POJO có constructor. Tham số constructor phải khớp tên và kiểu với persistent property mà constructor gán. Với entity phức tạp, constructor không nên âm thầm bỏ qua field bắt buộc.

Primary key nên được coi là bất biến sau khi tạo row. Thay giá trị key trên một object rồi gọi update không đổi khóa cũ tại chỗ; thao tác có thể được thực hiện trên row mang key mới. Nếu cần chuyển định danh, hãy thiết kế quy trình tạo row mới, chuyển tham chiếu và xóa row cũ có kiểm soát.

### 4.5. Embedded và custom converters

`@Embedded` cho phép các property của object con được lưu thành các cột trong cùng row; hữu ích khi tái sử dụng nhóm field như địa chỉ hoặc thông tin liên hệ. Nếu field embedded tham gia primary key, phải đánh dấu các thành phần key tương ứng bằng `@PrimaryKey`.

Khi kiểu Java không có conversion mặc định phù hợp, có thể đăng ký custom read/write converters. Converter phải đối xứng và ổn định: giá trị ghi xuống Spanner cần được đọc ngược về đúng kiểu, kể cả null, precision và timezone.

## 5. Repository với Spring Data Spanner

### 5.1. Khai báo repository

~~~java
import com.google.cloud.spring.data.spanner.repository.SpannerRepository;
import com.google.cloud.spanner.Key;

import java.util.List;
import java.util.Optional;

public interface OrderRepository extends SpannerRepository<Order, String> {

    List<Order> findByCustomerId(String customerId);

    List<Order> findTop20ByCustomerIdOrderByCreatedAtDesc(String customerId);

    List<Order> findByCustomerIdAndStatusOrderByCreatedAtDesc(
            String customerId, String status);

    Optional<Order> findByCustomerIdAndOrderId(
            String customerId, String orderId);
}

public interface OrderItemRepository extends SpannerRepository<OrderItem, Key> {
}
~~~

Tham số generic đầu tiên là entity type, tham số thứ hai là kiểu ID. Với entity có một primary-key column dạng String, dùng `String`. Với composite key, repository ID có thể dùng `Key` hoặc kiểu array/Iterable phù hợp với các thành phần key; kiểm tra yêu cầu của phiên bản Spring Data Spanner đang dùng.

Spring Boot starter tự bật repository scanning theo cấu hình mặc định. Nếu cần chỉ định package hoặc tùy chỉnh, có thể dùng `@EnableSpannerRepositories`.

### 5.2. CRUD và semantics của save

Repository kế thừa CRUD methods:

~~~java
orderRepository.save(order);
orderRepository.findById(orderId);
orderRepository.findAll();
orderRepository.deleteById(orderId);
~~~

Trong Spring Data Spanner, `save` và `saveAll` có semantics update-or-insert (upsert). Nếu nghiệp vụ yêu cầu row phải chưa tồn tại, dùng thao tác insert rõ ràng ở tầng template hoặc kiểm soát unique key/điều kiện phù hợp. Đừng giả định `save` tương đương INSERT thuần.

Collection result thường trả về collection rỗng khi không có row. Với một kết quả có thể vắng mặt, dùng `Optional<T>` để biểu đạt rõ trường hợp không tìm thấy.

### 5.3. Query methods theo tên

Spring Data tạo implementation dựa trên tên method:

~~~java
List<Order> findByCustomerIdAndStatus(String customerId, String status);

int countByCustomerId(String customerId);

List<Order> findTop10ByStatusOrderByCreatedAtDesc(String status);

int deleteByCustomerIdAndStatus(String customerId, String status);
~~~

Các predicate thường dùng gồm equality, greater/less than, null/not null, boolean, like, contains và in/not in. Không phải mọi keyword của Spring Data JPA đều được hỗ trợ y hệt. Kiểm tra reference khi dùng toán tử phức tạp hoặc biểu thức property đặc biệt.

Method name dài là dấu hiệu nên cân nhắc custom SQL. Hãy ưu tiên method name cho truy vấn đơn giản, dễ đọc; dùng `@Query` khi cần kiểm soát SQL, projection hoặc điều kiện rõ ràng.

### 5.4. Custom SQL với @Query và @Param

~~~java
import com.google.cloud.spring.data.spanner.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends SpannerRepository<Order, String> {

    @Query(
        "SELECT * FROM Orders " +
        "WHERE CustomerId = @customerId AND Status = @status " +
        "ORDER BY CreatedAt DESC LIMIT 50")
    List<Order> findRecentOrders(
            @Param("customerId") String customerId,
            @Param("status") String status);
}
~~~

Spanner SQL dùng named parameter có dạng `@customerId`, `@status`. Tên trong SQL phải khớp tên ở `@Param`. Luôn bind giá trị qua parameter, không nối chuỗi input người dùng vào SQL để tránh injection và lỗi escape.

### 5.5. DML qua query method

Có thể dùng `@Query` với `dmlStatement = true` cho câu lệnh INSERT/UPDATE/DELETE phù hợp:

~~~java
@Query(
    value = "UPDATE Orders SET Status = @newStatus WHERE OrderId = @orderId",
    dmlStatement = true)
long updateStatus(
        @Param("orderId") String orderId,
        @Param("newStatus") String newStatus);
~~~

Giá trị trả về là số row bị ảnh hưởng. Đánh dấu `dmlStatement = true` để Spring Data biết câu query là DML. DML và mutation API là hai cách ghi khác nhau; chọn theo thao tác và semantics mong muốn.

### 5.6. Projection và chỉ lấy cột cần thiết

Repository có thể trả về projection interface thay vì toàn bộ entity:

~~~java
import com.google.cloud.Timestamp;

public interface OrderSummary {
    String getOrderId();
    String getStatus();
    Timestamp getCreatedAt();
}
~~~

Một query projection giúp giảm dữ liệu đọc khi màn hình chỉ cần vài field. Với custom SQL, chọn đúng cột thay vì `SELECT *`. Nếu trả projection từ SQL, alias và tên property phải khớp mapping mà Spring Data cần.

### 5.7. Phân trang và thứ tự kết quả

Có thể dùng `Pageable` và `Sort` với repository. Khi phân trang, luôn có thứ tự xác định, tốt nhất thêm primary key làm tie-breaker. Nếu chỉ sort theo timestamp trùng nhau, các row có thể đổi vị trí giữa các trang.

Các lần gọi page riêng biệt không mặc nhiên nằm trong cùng một snapshot transaction. Nếu dữ liệu thay đổi giữa lúc người dùng lấy trang 1 và trang 2, kết quả có thể khác. Với báo cáo cần snapshot nhất quán, dùng read-only transaction phù hợp hoặc thiết kế cursor/keyset pagination theo query pattern.

## 6. Truy vấn và ghi với SpannerTemplate

### 6.1. Khi nào dùng Template?

`SpannerTemplate` phù hợp khi cần:

- SQL tùy chỉnh hoặc truy vấn động có tham số.
- Read theo key/key set.
- Đọc/ghi một phần property.
- DML statement và transaction.
- Truy cập tính năng Spanner chưa biểu đạt gọn qua repository.

Spring Boot starter tự cấu hình bean `SpannerTemplate`, có thể inject vào service.

### 6.2. Query với Statement và named parameters

~~~java
import com.google.cloud.spanner.Statement;
import com.google.cloud.spring.data.spanner.core.SpannerTemplate;

import java.util.List;

@Service
public class OrderQueryService {

    private final SpannerTemplate spannerTemplate;

    public OrderQueryService(SpannerTemplate spannerTemplate) {
        this.spannerTemplate = spannerTemplate;
    }

    public List<Order> findByCustomerAndStatus(
            String customerId, String status) {

        Statement statement = Statement.newBuilder(
                "SELECT * FROM Orders " +
                "WHERE CustomerId = @customerId AND Status = @status " +
                "ORDER BY CreatedAt DESC")
            .bind("customerId").to(customerId)
            .bind("status").to(status)
            .build();

        return spannerTemplate.query(Order.class, statement);
    }
}
~~~

`Statement.Builder.bind` giữ giá trị riêng khỏi câu SQL. Cách này giúp query an toàn và tái sử dụng. Với query lớn, hãy kiểm tra execution plan, index và số row đọc.

### 6.3. Đọc theo primary key và KeySet

Nếu đã biết key, dùng read API thay vì query SQL tổng quát:

~~~java
import com.google.cloud.spanner.Key;

Order order = spannerTemplate.read(Order.class, Key.of(orderId));
~~~

Với composite key, dùng `com.google.cloud.spanner.Key` tạo từ các thành phần theo đúng thứ tự schema. `KeySet` cho phép đọc một tập key hoặc range key; phù hợp khi đã biết phạm vi cần đọc. Read API có thể biểu đạt pattern key-based rõ hơn so với một câu SELECT tổng quát.

### 6.4. Insert, update và upsert

~~~java
spannerTemplate.insert(order);  // Chèn row mới.
spannerTemplate.update(order);  // Cập nhật row đã tồn tại.
spannerTemplate.upsert(order);  // Cập nhật hoặc chèn.
~~~

Chọn method theo invariant nghiệp vụ. `insert` phù hợp khi row phải mới; `update` khi row đã tồn tại; `upsert` khi cho phép cả hai trường hợp.

Update mặc định ghi các property của entity. Khi chỉ muốn ghi một số cột, có thể dùng overload nhận danh sách tên property/cột được hỗ trợ bởi phiên bản thư viện. Cần hiểu rõ partial update để không ghi đè field ngoài ý muốn.

### 6.5. DML và Partitioned DML

`SpannerTemplate` hỗ trợ chạy DML statement. Partitioned DML phù hợp với một số thao tác cập nhật/xóa hàng loạt trên nhiều row, nhưng có giới hạn và không chạy bên trong transaction thông thường.

Không dùng Partitioned DML thay thế read-write transaction cho nghiệp vụ cần atomicity nhiều bước. Hãy kiểm tra giới hạn câu lệnh được hỗ trợ, số row bị ảnh hưởng và tính idempotent trước khi chạy batch lớn.

## 7. Transaction với Spring Data Spanner

### 7.1. @Transactional

Spring Data Spanner hỗ trợ `@Transactional` thông qua Spanner transaction manager do starter cung cấp:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class OrderWriteService {

    private final OrderRepository orderRepository;
    private final OrderItemRepository itemRepository;

    public OrderWriteService(
            OrderRepository orderRepository,
            OrderItemRepository itemRepository) {
        this.orderRepository = orderRepository;
        this.itemRepository = itemRepository;
    }

    @Transactional(transactionManager = "spannerTransactionManager")
    public void createOrder(Order order, List<OrderItem> items) {
        orderRepository.save(order);
        itemRepository.saveAll(items);
    }
}
~~~

Tên transaction manager được nêu tường minh để tránh nhầm khi ứng dụng có thêm transaction manager cho Cloud SQL, JPA hoặc datastore khác. Trong một số cấu hình đơn giản chỉ có Spanner, có thể để Spring chọn manager duy nhất.

### 7.2. Không tạo nested transaction

Spanner không hỗ trợ transaction lồng nhau. Không gọi `performReadWriteTransaction` hoặc `performReadOnlyTransaction` từ bên trong một method `@Transactional` đang chạy cùng Spanner transaction. Hãy chọn một cơ chế transaction cho một unit of work.

Read-write transaction phù hợp khi cần đọc rồi ghi dữ liệu có liên hệ trong cùng một đơn vị atomic. Read-only transaction phù hợp khi cần nhiều lần đọc trên cùng một snapshot nhất quán.

### 7.3. Transaction có thể được retry

Cloud Spanner có thể abort read-write transaction do contention hoặc transient condition. Client library có retry logic để chạy lại transaction callback. Vì vậy, code bên trong callback phải có thể chạy nhiều lần.

Không gửi email, gọi payment gateway, publish message hoặc ghi sang hệ thống ngoài trực tiếp trong transaction callback. Side effect bên ngoài có thể xảy ra nhiều lần dù database transaction chỉ commit một lần. Dùng outbox pattern hoặc ghi event trong cùng transaction rồi xử lý sau commit.

### 7.4. Giữ transaction ngắn

Giữ transaction ngắn để giảm lock duration và contention:

- Chỉ đọc những row cần thiết.
- Tránh gọi HTTP service bên trong transaction.
- Không chờ người dùng hoặc thao tác I/O chậm trong transaction.
- Tránh transaction cập nhật phạm vi row quá lớn khi có thể chia batch.
- Thiết kế key để các thao tác atomic thường chạm cùng vùng dữ liệu hợp lý.

### 7.5. Strong read và stale read

Read/query mặc định là strong read: kết quả phản ánh các thay đổi đã commit trước thời điểm bắt đầu lần đọc. Spanner cũng hỗ trợ stale read ở một timestamp trong quá khứ để đổi độ mới dữ liệu lấy lợi ích về latency/throughput trong một số trường hợp.

Dùng stale read cho màn hình thống kê hoặc dữ liệu chấp nhận trễ nếu nghiệp vụ cho phép. Không dùng stale read cho bước kiểm tra tồn kho hoặc quyết định thanh toán cần dữ liệu mới nhất mà không đánh giá semantics.

## 8. Interleaved tables và quan hệ parent-child

### 8.1. Khi nào nên dùng @Interleaved?

`@Interleaved` biểu diễn row con được interleave trong bảng cha. Ví dụ `OrderItems` thuộc một `Order`, thường được đọc cùng đơn hàng và có vòng đời phụ thuộc đơn hàng.

~~~java
@Table(name = "Orders")
public class Order {
    @PrimaryKey
    private String orderId;

    @Interleaved
    private List<OrderItem> items;
}
~~~

Entity child cần chứa đầy đủ primary key của parent theo cùng thứ tự, sau đó là key riêng của child.

### 8.2. Eager và lazy loading

Mặc định, interleaved rows được nạp cùng entity parent. Nếu collection lớn hoặc chỉ đôi lúc cần dùng, có thể chọn:

~~~java
@Interleaved(lazy = true)
private List<OrderItem> items;
~~~

Lazy loading giảm việc đọc child khi không cần, nhưng truy cập property có thể phát sinh thao tác đọc bổ sung. Tránh vòng lặp truy cập từng collection gây nhiều lượt gọi. Hãy đo số query/read và chọn eager/lazy theo pattern sử dụng.

### 8.3. Interleaving không phải quan hệ ORM tổng quát

Interleaving là quyết định vật lý về locality của dữ liệu trong Spanner, không đơn thuần là annotation để tạo collection giống JPA. Nó phù hợp quan hệ parent-child có key hierarchy rõ ràng. Với quan hệ nhiều-nhiều, tham chiếu độc lập hoặc entity có vòng đời riêng, có thể dùng bảng liên kết và foreign key phù hợp.

Không interleave mọi quan hệ chỉ để tránh viết query join. Chọn dựa trên truy cập, lifecycle, phân phối ghi và yêu cầu mở rộng.

## 9. Index, query performance và schema evolution

### 9.1. Index là một phần của thiết kế dữ liệu

Spanner cần index cho các query pattern không dựa trực tiếp trên primary key. Index có thể sắp xếp theo nhiều cột và chiều ASC/DESC. Index giúp đọc nhanh hơn nhưng tạo thêm công việc ghi và storage.

Ví dụ:

~~~sql
CREATE INDEX OrdersByCustomerCreatedAt
ON Orders(CustomerId, CreatedAt DESC);
~~~

Index phù hợp với query lọc `CustomerId` và lấy đơn mới nhất. Nếu query lọc thêm `Status`, hãy benchmark và xem xét index gồm các cột phù hợp. Không thêm index theo cảm tính.

### 9.2. Tránh SELECT *

Nếu màn hình chỉ cần order ID, status và timestamp, hãy chọn đúng cột hoặc dùng projection. Đọc ít dữ liệu hơn giúp giảm network transfer và lượng dữ liệu cần map.

~~~sql
SELECT OrderId, Status, CreatedAt
FROM Orders
WHERE CustomerId = @customerId
ORDER BY CreatedAt DESC
LIMIT 50;
~~~

### 9.3. Schema evolution

Entity annotation mô tả mapping, nhưng không tự động làm schema production luôn khớp với class mới. Thay đổi DDL cần quy trình migration có kiểm soát:

1. Tạo migration DDL phiên bản mới.
2. Xác minh tương thích ngược với phiên bản ứng dụng đang chạy.
3. Áp dụng DDL qua pipeline hoặc công cụ quản trị.
4. Triển khai ứng dụng sử dụng field mới.
5. Backfill dữ liệu nếu cần.
6. Chỉ xóa cột cũ sau khi mọi consumer đã chuyển đổi.

Primary key của table Spanner không thể tùy ý thay đổi như đổi một annotation. Thay đổi key thường cần thiết kế lại hoặc tạo table mới và migrate dữ liệu.

### 9.4. Schema utility

Starter cung cấp `SpannerSchemaUtils` và `SpannerDatabaseAdminTemplate` để tạo DDL từ entity hierarchy và thực hiện DDL. Điều này hữu ích trong thử nghiệm hoặc bootstrap môi trường.

Với production, nên version hóa DDL và chạy migration có review trong deployment pipeline. Tránh để mỗi replica tự tạo hoặc sửa schema lúc khởi động vì có thể gây race, quyền runtime quá rộng và khó audit.

## 10. Session pool của Spanner và HikariCP

### 10.1. Spanner dùng session pool gRPC

Spring Data Spanner sử dụng Cloud Spanner Java client. Client quản lý gRPC channels và **session pool** để tái sử dụng Spanner sessions. Đây không phải JDBC DataSource và không phải HikariCP.

| Cloud SQL JDBC | Cloud Spanner |
| --- | --- |
| JDBC driver | Cloud Spanner Java client/gRPC |
| HikariCP connection pool | Spanner session pool |
| JDBC connection | Spanner session |
| JDBC URL | Project/instance/database config |
| JDBC transaction manager | Spanner transaction manager |

Không cấu hình `spring.datasource.hikari` để điều chỉnh Spring Data Spanner. Thay vào đó, dùng các property `spring.cloud.gcp.spanner.*` phù hợp với phiên bản Spring Framework on Google Cloud.

### 10.2. Các property session pool

Một số cấu hình có thể có trong Spring Cloud GCP:

| Property | Ý nghĩa |
| --- | --- |
| `spring.cloud.gcp.spanner.minSessions` | Số session tối thiểu được duy trì |
| `spring.cloud.gcp.spanner.maxSessions` | Số session tối đa trong pool |
| `spring.cloud.gcp.spanner.maxIdleSessions` | Số session nhàn rỗi tối đa |
| `spring.cloud.gcp.spanner.failIfPoolExhausted` | Báo lỗi ngay khi hết session thay vì chờ session |
| `spring.cloud.gcp.spanner.keepAliveIntervalMinutes` | Khoảng thời gian keepalive session |
| `spring.cloud.gcp.spanner.numRpcChannels` | Số gRPC channel |

Tên property và default phụ thuộc phiên bản. Kiểm tra reference documentation của BOM đang dùng trước khi thay đổi. Tăng `maxSessions` không tự làm query nhanh hơn và có thể tăng tài nguyên/concurrency mà workload sử dụng.

### 10.3. Đặt giới hạn theo workload

Session pool cần được cân nhắc theo số replica, mức đồng thời và pattern transaction. Nếu ứng dụng chạy nhiều replica, tổng session có thể tăng theo số process. Quan sát pool exhaustion, session usage, RPC latency và transaction abort trước khi điều chỉnh.

## 11. IAM, audit và bảo vệ dữ liệu

### 11.1. Workload identity

Gắn service account riêng cho service Spring Boot và để ADC lấy credentials từ runtime. Không lưu service account key JSON trong source, image hoặc file cấu hình commit vào Git.

Phân tách principal theo trách nhiệm:

- Runtime đọc/ghi dữ liệu.
- Migration cập nhật schema.
- Read-only reporting.
- Operator quản trị instance/database.

### 11.2. Least privilege

`roles/spanner.databaseUser` cho phép đọc/ghi và một số thao tác schema. Nếu runtime không cần cập nhật schema, hãy đánh giá fine-grained access control, database roles hoặc custom IAM role để thu hẹp quyền.

`roles/spanner.databaseReader` phù hợp với service chỉ đọc. Không cấp quyền quản trị instance cho service chỉ cần truy vấn đơn hàng.

### 11.3. Audit và application authorization

Bật audit logging theo chính sách tổ chức và ghi nhận request/correlation ID ở tầng ứng dụng. Không log toàn bộ payload nhạy cảm hoặc dữ liệu khách hàng khi không cần.

Spanner IAM không thay thế kiểm tra quyền theo tenant. Mọi query có dữ liệu tenant nên ràng buộc tenant ID từ identity đã xác thực, không tin giá trị tenant tùy ý từ request body.

## 12. Kiểm thử với Cloud Spanner Emulator

### 12.1. Khởi động emulator

Spanner Emulator cung cấp môi trường local trong bộ nhớ, phù hợp phát triển và integration test. Dữ liệu không được lưu qua lần chạy và emulator không phải môi trường production.

Có thể khởi động bằng Google Cloud CLI:

~~~bash
gcloud emulators spanner start
~~~

Sau đó cấu hình Spring:

~~~yaml
spring:
  cloud:
    gcp:
      spanner:
        project-id: local-project
        instance-id: test-instance
        database: test-db
        emulator:
          enabled: true
        emulator-host: localhost:9010
~~~

Tạo instance/database test trong emulator và áp dụng DDL trước khi chạy repository test. Nếu dùng host/port khác, cấu hình `emulator-host` theo property của phiên bản starter.

### 12.2. Integration test

Có thể dùng Testcontainers module gcloud với `SpannerEmulatorContainer` để test tự động trong CI. Test nên bao gồm:

- Mapping field và composite key.
- Insert, update, upsert và delete.
- Query methods theo tên.
- `@Query` với named parameter.
- Interleaved parent-child.
- Transaction commit và rollback.
- DML update và số row bị ảnh hưởng.
- Schema migration.
- Trường hợp không tìm thấy entity.

### 12.3. Giới hạn emulator

Emulator hữu ích để kiểm tra logic và mapping, nhưng không đại diện hoàn toàn cho production về hiệu năng, phân phối dữ liệu, contention, quota, IAM và một số tính năng/behavior. Trước khi phát hành, chạy một tập integration test trên project sandbox có IAM/network tương tự production và đo query latency thực tế.

## 13. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không tạo được Spanner client | Project ID, ADC hoặc API chưa đúng | Kiểm credentials, project, API và service account |
| Permission denied | Thiếu Spanner IAM role | Kiểm `roles/spanner.databaseUser` hoặc role read-only phù hợp |
| Database/instance not found | Sai instance ID hoặc database name | Đối chiếu property với tài nguyên Cloud |
| Entity không map được table | Sai `@Table` hoặc tên bảng | Kiểm DDL và mapping annotation |
| Column not found | Sai `@Column` hoặc naming strategy | So sánh property với schema thực tế |
| Primary key mapping error | Thiếu `@PrimaryKey` hoặc sai keyOrder | Kiểm số cột và thứ tự primary key trong DDL |
| Child rows không load | Sai composite key/interleave mapping | Kiểm parent key có mặt và cùng thứ tự |
| Query parameter missing | Tên `@Param` không khớp placeholder SQL | So sánh tên parameter ở hai vị trí |
| Query chậm | Thiếu index hoặc scan quá nhiều row | Xem query plan, index và số row đọc |
| Transaction aborted | Contention hoặc transaction quá dài | Rút ngắn transaction, giảm vùng ghi xung đột và để client retry |
| Session pool exhausted | Concurrency vượt pool/session budget | Theo dõi session usage và điều chỉnh pool/replica |
| Test local pass nhưng cloud fail | Emulator không phản ánh IAM/quota/network/production load | Test trên sandbox thật với runtime identity |

Không khắc phục lỗi mapping bằng cách đổi tùy tiện DDL production hoặc cấp quyền Spanner Admin cho runtime. Xác định đúng lớp lỗi và tái hiện bằng một test nhỏ.

## 14. So sánh Spring Data Spanner với các lựa chọn dữ liệu khác

| Khía cạnh | Spring Data Spanner | Spring Data JPA + Cloud SQL | AWS/Azure managed relational DB |
| --- | --- | --- | --- |
| Database model | Quan hệ phân tán, scale ngang | PostgreSQL/MySQL/SQL Server managed | RDS/Aurora hoặc Azure Database theo engine |
| Client | Google Cloud Spanner Java client/gRPC | JDBC driver | JDBC driver |
| Pool | Spanner session pool | HikariCP phổ biến | HikariCP hoặc proxy/pooler |
| Mapping | Annotation riêng của Spanner | JPA entity/ORM | JPA/JDBC tùy framework |
| Query | GoogleSQL qua repository/template | JPQL/SQL theo dialect | SQL theo engine |
| Transaction | Spanner transaction semantics | Database engine transaction | Database engine transaction |

Spring Data repository giúp giảm boilerplate, nhưng không biến Spanner thành database có semantics giống Hibernate. Những quyết định về primary key, index, interleaving, transaction retry và session pool vẫn cần kiến thức riêng về Spanner.

## 15. Bài tập thực hành

### Bài A — Tạo schema và ánh xạ entity

Tạo database `orders` trên Spanner sandbox. Áp dụng DDL cho `Orders` và `OrderItems`, tạo entity Java với `@Table`, `@Column`, `@PrimaryKey` và `@Interleaved`. Xác minh mapping với một parent có hai child rows.

### Bài B — Xây dựng repository

Tạo `OrderRepository` kế thừa `SpannerRepository<Order, String>`. Viết query methods tìm đơn theo customer, status và thời gian. Viết một custom `@Query` có `@Param` để tìm 50 đơn mới nhất.

### Bài C — Dùng SpannerTemplate

Viết service dùng `SpannerTemplate` và `Statement.Builder.bind` để query theo customer ID. Thực hiện insert/upsert và so sánh semantics với repository `save`.

### Bài D — Thiết kế key và index

Tạo bảng log có tải ghi cao. So sánh primary key timestamp tăng dần với UUID v4 hoặc shard prefix. Thiết kế index theo query pattern và giải thích chi phí ghi tăng thêm.

### Bài E — Transaction và retry

Viết transaction tạo đơn và item. Giả lập contention trong môi trường test; xác minh retry không gửi email hoặc publish message lặp. Đề xuất outbox pattern cho side effect ngoài database.

### Bài F — Emulator và cloud integration

Chạy repository tests với Spanner Emulator trong CI. Sau đó triển khai một test trên sandbox thật để xác minh ADC/IAM, DDL, query và behavior khi tải đồng thời.

### Câu hỏi tự kiểm tra

1. Cloud Spanner khác Cloud SQL ở kiến trúc client và cách phân phối dữ liệu như thế nào?
2. Vì sao Spring Data Spanner không phải JPA/Hibernate?
3. PostgreSQL interface của Spanner có dùng được Spring Data Spanner không?
4. `@PrimaryKey` có cần thiết khi bảng chỉ có một cột khóa không?
5. `keyOrder` phải khớp với phần nào của DDL?
6. Vì sao khóa tăng tuần tự có thể gây hotspot?
7. UUID v4 có lợi thế gì khi làm primary key?
8. Khi nào nên dùng `@Interleaved`?
9. `@NotMapped` và `@Embedded` có ý nghĩa gì?
10. Khi nào nên dùng repository, khi nào dùng `SpannerTemplate`?
11. Named parameter trong Spanner SQL có cú pháp như thế nào?
12. Vì sao query nên bind parameter thay vì nối chuỗi?
13. `save` của SpannerRepository có semantics gì?
14. Vì sao không được lồng transaction Spanner?
15. Transaction callback có thể chạy nhiều lần vì lý do gì?
16. Vì sao không nên gửi email hoặc gọi payment gateway bên trong transaction callback?
17. Session pool của Spanner khác HikariCP ra sao?
18. Emulator không thể thay thế loại kiểm thử production nào?

**Kết quả mong đợi:** người học thiết kế được schema Cloud Spanner với primary key và index phù hợp, ánh xạ entity Java bằng Spring Data Spanner, xây dựng repository/query có tham số, dùng SpannerTemplate và transaction đúng semantics, kiểm thử bằng emulator và triển khai được quyền truy cập theo workload identity.

## Tài liệu tham khảo

- [Integrate Spanner with Spring Data](https://docs.cloud.google.com/spanner/docs/adding-spring)
- [Spring Framework on Google Cloud — Spring Data Cloud Spanner reference](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/)
- [Spanner schema design best practices](https://docs.cloud.google.com/spanner/docs/schema-design)
- [Spanner transactions](https://docs.cloud.google.com/spanner/docs/transactions)
- [Cloud Spanner IAM roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/spanner)

