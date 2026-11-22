# Bổ sung version, auditing và giao dịch nhiều document

Trong một ứng dụng dùng **Spring Data MongoDB**, lưu một document đơn lẻ tương đối đơn giản: **MongoRepository.save(...)** hoặc **MongoTemplate.save(...)** đủ cho nhiều tình huống. Bài toán khó hơn xuất hiện khi một thao tác nghiệp vụ phải **đọc rồi cập nhật tồn kho**, **tạo đơn hàng**, **ghi sự kiện**, đồng thời cần biết **ai thực hiện, khi nào** và phải xử lý khi hai request cùng sửa một document.

Bài thực hành tổng hợp này bổ sung ba khả năng vào luồng đặt hàng:

1. **Optimistic locking với @Version** để phát hiện cập nhật dựa trên phiên bản cũ.
2. **Auditing với @CreatedDate, @LastModifiedDate, @CreatedBy, @LastModifiedBy** để tự động ghi metadata thay đổi.
3. **Transaction nhiều document với MongoTransactionManager và @Transactional** để các thay đổi trong MongoDB được commit hoặc rollback cùng nhau.

Đây là bài học thực hành của module **SPRING_DATA_MONGODB**: sử dụng **MongoRepository**, liên hệ với **MongoTemplate**, hiểu yêu cầu về replica set và kiểm thử cả nhánh thành công lẫn nhánh thất bại. Những ví dụ mã nguồn dùng **Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, MongoDB 7.0** và Testcontainers 1.x làm một bộ minh họa nhất quán; khi dùng bộ phiên bản khác, hãy điều chỉnh dependency, import và cấu hình theo compatibility matrix tương ứng.

> **Mục tiêu thực hành:** một đơn hàng chỉ được tạo khi đủ tồn kho; thao tác giữ tồn kho, tạo đơn và ghi sự kiện phải cùng một transaction; mỗi document quan trọng có version và metadata audit; ghi đồng thời không được âm thầm làm mất update.

## 1. Đầu ra mong đợi và tiêu chí nghiệm thu

Sau khi hoàn thành, người học cần chứng minh được:

| Yêu cầu | Bằng chứng chấp nhận |
| --- | --- |
| Tạo mới mặt hàng tồn kho | Document được lưu trong collection **inventory** với version và thời điểm tạo |
| Đặt hàng thành công | Tăng số lượng **reserved**, tạo **orders**, tạo **order_events** trong một transaction |
| Đặt hàng thất bại giữa chừng | Không có cập nhật tồn kho bị commit dở; không phát sinh đơn/sự kiện ngoài dự kiến |
| Cập nhật document bằng bản sao cũ | Có lỗi optimistic locking hoặc write conflict được xử lý theo chính sách |
| Ghi nhận metadata | **createdAt**, **updatedAt**, **createdBy**, **updatedBy** có giá trị hợp lệ ở nơi được cấu hình auditing |
| Chạy trong môi trường phù hợp | Sử dụng MongoDB **replica set** hoặc **sharded cluster** hỗ trợ transaction |
| Kiểm thử không phụ thuộc mock DB | Test thực sự kiểm tra trạng thái MongoDB sau khi transaction kết thúc |
| Retry an toàn | Phân biệt lỗi được phép thử lại, lỗi nghiệp vụ và request đã xử lý |

Không dùng **@Transactional** như một dấu bảo đảm mọi tài nguyên bên ngoài đều atomic: transaction của MongoDB bao gồm các thao tác MongoDB cùng session, **không** tự bao gồm HTTP call, gửi email, Kafka hoặc các hệ thống khác.

## 2. Mô hình nghiệp vụ và bất biến dữ liệu

Giả sử một cửa hàng có ba collection:

| Collection | Dữ liệu chính | Mục đích |
| --- | --- | --- |
| **inventory** | **sku**, **onHand**, **reserved**, version, audit fields | Số lượng tồn và số đã giữ chỗ |
| **orders** | **orderId**, **sku**, **quantity**, **status**, version, audit fields | Đơn hàng đã đặt |
| **order_events** | **eventId**, **orderId**, **type**, createdAt | Bằng chứng sự kiện nội bộ trong cùng DB |

Trong ví dụ:

- **onHand** là số đơn vị có trong kho.
- **reserved** là số đơn vị đã giữ cho các đơn hàng chưa hoàn tất.
- **available = onHand − reserved**.
- Mỗi request chỉ đặt **một SKU** để tập trung vào việc học transaction, không xử lý giỏ hàng nhiều mặt hàng.
- **orderId** do caller cung cấp, dùng làm khóa định danh duy nhất; cần chính sách idempotency khi mở rộng sản phẩm.

Các bất biến cần giữ:

\[
0 \leq \text{reserved} \leq \text{onHand}
\]

\[
\text{available} = \text{onHand} - \text{reserved}
\]

Một transaction đặt hàng thành công phải thỏa:

1. Tồn kho được tăng **reserved** đúng bằng quantity.
2. Có **một** document đơn hàng tương ứng orderId.
3. Có **một** sự kiện loại **ORDER_PLACED** cho đơn đó.
4. Nếu một bước ghi trong transaction thất bại, **không bước nào** được commit.

~~~mermaid
sequenceDiagram
    participant API as "API / Command"
    participant SVC as "OrderPlacementService"
    participant INV as "inventory"
    participant ORD as "orders"
    participant EVT as "order_events"
    API->>SVC: "place(orderId, sku, quantity)"
    Note over SVC: "Mở MongoDB transaction"
    SVC->>INV: "findById(sku)"
    SVC->>SVC: "Kiểm tra available và cập nhật reserved"
    SVC->>INV: "save(inventory) với @Version"
    SVC->>ORD: "insert(order)"
    SVC->>EVT: "insert(ORDER_PLACED event)"
    alt "Cả ba ghi thành công"
        SVC->>SVC: "Commit transaction"
        SVC-->>API: "Trả order"
    else "Một bước lỗi"
        SVC->>SVC: "Abort / rollback transaction"
        SVC-->>API: "Trả lỗi phù hợp"
    end
~~~

**Ranh giới quan trọng:** MongoDB đảm bảo atomic ở mức **một document** ngay cả không có transaction. Chúng ta cần transaction vì phải cập nhật **nhiều document/collection** với cùng kết quả commit. **@Version** giải quyết một vấn đề khác: ngăn ghi đè dựa trên snapshot document đã cũ. Hai cơ chế bổ sung nhau, không thay thế cho nhau.

## 3. Khai báo dependency và môi trường

Đối với Gradle Groovy DSL, ứng dụng dùng Spring Boot BOM phù hợp cần tối thiểu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:mongodb'
}

test {
    useJUnitPlatform()
}
~~~

Ví dụ giả định phiên bản được Spring Boot/dependency management quản lý. Không ghép tùy ý **MongoDB Java Driver**, **Spring Data MongoDB** và **Testcontainers** khác major. Để chạy integration test cần container runtime tương thích, còn môi trường production cần cluster MongoDB có topology và cấu hình transaction phù hợp.

Cấu hình kết nối local ví dụ:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/capstone
      auto-index-creation: false
~~~

Đây là cú pháp ví dụ cho **Spring Boot 3.x**. Ở **Spring Boot 4.x**, một số property kết nối chuyển sang namespace **spring.mongodb**; không sao chép cấu hình giữa major version khi chưa kiểm tra migration guide. Bài học không phụ thuộc vào việc bật auto index: khóa **_id** đã có unique index mặc định, còn index nghiệp vụ phải được quản lý riêng khi cần.

### 3.1. Vì sao transaction cần replica set?

MongoDB multi-document transaction yêu cầu **replica set** hoặc **sharded cluster**. Một MongoDB standalone có thể lưu và đọc đơn hàng bình thường, nhưng bắt đầu transaction nhiều document sẽ không hoạt động như mong đợi. Nếu gặp thông báo liên quan đến **Transaction numbers are only allowed on a replica set member or mongos**, hãy kiểm tra topology trước khi đổ lỗi cho annotation Java.

Các điểm phải xác nhận:

- Kết nối đến replica set (qua replica set connection string) hoặc **mongos** của sharded cluster.
- **MongoTransactionManager** sử dụng đúng **MongoDatabaseFactory** của client mà repository/MongoTemplate truy cập.
- Write concern, read concern, timeout và giới hạn transaction phù hợp hệ thống thực tế.
- Những collection/index cần thiết được tạo **trước transaction** theo chính sách môi trường; không thiết kế transaction nghiệp vụ phụ thuộc vào tạo mới schema/index ở thời điểm chạy.

## 4. Bổ sung @Version vào entity tồn kho

**Optimistic locking** được thiết kế cho trường hợp nhiều tác nhân đọc cùng document rồi cố ghi dựa trên trạng thái cũ. Khi mapping có **@Version**, Spring Data MongoDB dùng giá trị version hiện tại làm một phần điều kiện cập nhật và tăng version khi ghi thành công.

Ví dụ hai thread đọc cùng bản:

~~~text
T0: inventory = { sku: "SKU-1", onHand: 3, reserved: 0, version: 0 }

Thread A đọc version 0.
Thread B đọc version 0.

A giữ 2 đơn vị và save -> ghi version 0 thành version 1.
B giữ 2 đơn vị dựa trên version 0 -> không cập nhật được
  hoặc gặp xung đột khi transaction; không được âm thầm ghi đè A.
~~~

Nếu không có version hoặc điều kiện ghi nguyên tử tương đương, cách **read → calculate → save** có nguy cơ mất update (lost update).

### 4.1. Entity InventoryItem

~~~java
package example.capstone;

import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inventory")
public class InventoryItem {
    @Id
    private String sku;

    private long onHand;
    private long reserved;

    @Version
    private Long version;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    protected InventoryItem() {
        // Spring Data mapping.
    }

    public InventoryItem(String sku, long onHand) {
        if (sku == null || sku.isBlank() || onHand < 0) {
            throw new IllegalArgumentException("Invalid inventory");
        }
        this.sku = sku;
        this.onHand = onHand;
        this.reserved = 0;
    }

    public void reserve(long quantity) {
        if (quantity <= 0 || quantity > onHand - reserved) {
            throw new IllegalStateException("Insufficient inventory");
        }
        reserved = Math.addExact(reserved, quantity);
    }

    public String getSku() { return sku; }
    public long getOnHand() { return onHand; }
    public long getReserved() { return reserved; }
    public long getAvailable() { return onHand - reserved; }
    public Long getVersion() { return version; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public String getCreatedBy() { return createdBy; }
    public String getUpdatedBy() { return updatedBy; }
}
~~~

**Các chú ý về @Version:**

- Chọn **Long** để biểu diễn version nullable khi entity mới tạo; Spring Data gán giá trị khởi tạo thích hợp và tăng khi cập nhật. Không tự tăng version trong code nghiệp vụ.
- Với **@Version**, lần save đối tượng đang tồn tại dùng cơ chế so sánh version; khi không còn document khớp version cũ, Spring Data thường ném **OptimisticLockingFailureException**.
- Cơ chế phát hiện cập nhật không khớp cần **acknowledged write concern** để driver nhận được kết quả ghi. Tránh dùng **UNACKNOWLEDGED** cho luồng này.
- **@Version** trên entity không tự ngăn mọi cách ghi. Lệnh update raw bằng driver hoặc **MongoTemplate.updateFirst(...)** không theo luồng save entity có thể không tuân thủ contract optimistic locking mà bạn kỳ vọng; cần kiểm tra API cụ thể và điều kiện update.
- Version là một số dành cho **concurrency control**, không phải lịch sử thay đổi. Muốn lưu lịch sử sự kiện/ai đã làm gì, cần auditing hoặc audit log riêng.

## 5. Bổ sung auditing vào đơn hàng

Auditing điền metadata khi entity được tạo hoặc sửa qua luồng Spring Data phù hợp:

| Annotation | Khi sử dụng | Ý nghĩa |
| --- | --- | --- |
| **@CreatedDate** | Khi tạo document mới | Thời điểm tạo |
| **@LastModifiedDate** | Khi tạo và cập nhật theo chính sách auditing | Thời điểm sửa gần nhất |
| **@CreatedBy** | Khi tạo document mới | Người/tác nhân tạo |
| **@LastModifiedBy** | Khi cập nhật theo chính sách auditing | Người/tác nhân sửa |
| **@Version** | Khi lưu/cập nhật entity versioned | Phát hiện stale write và tăng version |

**Auditing không thay thế audit trail bất biến**: nếu cần danh sách đầy đủ các thay đổi theo thời gian, chỉ có **updatedBy/updatedAt** sẽ không đủ; phải thiết kế sự kiện lịch sử, change log hoặc event store với chính sách riêng.

### 5.1. Entity PurchaseOrder

~~~java
package example.capstone;

import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class PurchaseOrder {
    public enum Status { PLACED, CANCELLED }

    @Id
    private String id;

    private String sku;
    private long quantity;
    private Status status;

    @Version
    private Long version;

    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;
    @CreatedBy
    private String createdBy;
    @LastModifiedBy
    private String updatedBy;

    protected PurchaseOrder() {}

    public PurchaseOrder(String id, String sku, long quantity) {
        if (id == null || id.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
        this.id = id;
        this.sku = sku;
        this.quantity = quantity;
        this.status = Status.PLACED;
    }

    public void cancel() {
        if (status != Status.PLACED) {
            throw new IllegalStateException("Not cancellable");
        }
        status = Status.CANCELLED;
    }

    public String getId() { return id; }
    public String getSku() { return sku; }
    public long getQuantity() { return quantity; }
    public Status getStatus() { return status; }
    public Long getVersion() { return version; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public String getCreatedBy() { return createdBy; }
    public String getUpdatedBy() { return updatedBy; }
}
~~~

### 5.2. Sự kiện nội bộ thuộc cùng transaction

~~~java
package example.capstone;

import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "order_events")
public class OrderEvent {
    @Id
    private String id;

    private String orderId;
    private String type;

    @CreatedDate
    private Instant createdAt;

    protected OrderEvent() {}

    public OrderEvent(String orderId, String type) {
        this.id = "order-placed:" + orderId;
        this.orderId = orderId;
        this.type = type;
    }

    public String getId() { return id; }
    public String getOrderId() { return orderId; }
    public String getType() { return type; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

Khóa sự kiện được xác định theo orderId và loại nghiệp vụ đơn giản trong bài. Một hệ thống thực tế có nhiều event cho cùng order cần một khóa khác, ví dụ **orderId + event type + sequence** hoặc event UUID, và chính sách chống trùng rõ ràng.

### 5.3. Bật auditing và cung cấp AuditorAware

~~~java
package example.capstone;

import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
@EnableMongoAuditing(auditorAwareRef = "capstoneAuditor")
public class MongoInfrastructureConfiguration {

    @Bean
    public AuditorAware<String> capstoneAuditor() {
        // Demo có actor cố định để test có tính lặp lại.
        return () -> Optional.of("capstone-operator");
    }

    @Bean(name = "mongoTransactionManager")
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory mongoDatabaseFactory) {
        return new MongoTransactionManager(mongoDatabaseFactory);
    }
}
~~~

**Tại production:** thay actor cố định bằng một **AuditorAware** lấy định danh từ bối cảnh xác thực hiện tại (chẳng hạn Spring Security), hoặc từ **system/job identity** của batch. Cần xác định hành vi khi người dùng không xác thực: dùng actor hệ thống có chủ đích, hoặc từ chối theo chính sách; không ghi một ID giả như thể đó là người dùng thật.

Thời gian auditing được tạo ở ứng dụng; **Instant** phù hợp cho thời điểm tuyệt đối và được ánh xạ sang BSON Date (độ chính xác mili giây). Nếu test cần so sánh chính xác với clock, cấu hình **DateTimeProvider** có kiểm soát thay vì dựa vào **Instant.now()** và khoảng chờ ngẫu nhiên.

**Không mặc định mọi đường cập nhật đều kích hoạt auditing**. Với các thao tác update pipeline hoặc raw MongoDB driver, callback trên entity không nhất thiết được chạy. Cần xác minh từng API sử dụng; nếu cập nhật trực tiếp qua **MongoTemplate.updateFirst(...)**, ứng dụng phải thiết kế rõ việc cập nhật **updatedAt/updatedBy** và version.

## 6. Repository và transaction service

### 6.1. Khai báo repository

~~~java
package example.capstone;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface InventoryRepository
        extends MongoRepository<InventoryItem, String> {
}

public interface PurchaseOrderRepository
        extends MongoRepository<PurchaseOrder, String> {
}

public interface OrderEventRepository
        extends MongoRepository<OrderEvent, String> {
}
~~~

Để chạy như dự án Java thật, đặt **mỗi interface public trong một file** có tên tương ứng; chúng được nhóm chung ở đây để tiết kiệm không gian. Các repository dùng cùng database factory và MongoClient được cấu hình bởi Spring Boot.

### 6.2. Service đặt hàng với một transaction

~~~java
package example.capstone;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPlacementService {
    private final InventoryRepository inventoryRepository;
    private final PurchaseOrderRepository orderRepository;
    private final OrderEventRepository eventRepository;

    public OrderPlacementService(
            InventoryRepository inventoryRepository,
            PurchaseOrderRepository orderRepository,
            OrderEventRepository eventRepository) {
        this.inventoryRepository = inventoryRepository;
        this.orderRepository = orderRepository;
        this.eventRepository = eventRepository;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public PurchaseOrder place(
            String orderId, String sku, long quantity) {
        if (orderId == null || orderId.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid place request");
        }

        InventoryItem inventory = inventoryRepository.findById(sku)
            .orElseThrow(() ->
                new IllegalArgumentException("Unknown SKU"));

        inventory.reserve(quantity);
        inventoryRepository.save(inventory);

        PurchaseOrder order = orderRepository.insert(
            new PurchaseOrder(orderId, sku, quantity)
        );

        eventRepository.insert(
            new OrderEvent(orderId, "ORDER_PLACED")
        );
        return order;
    }
}
~~~

**Giải thích thứ tự:**

1. Đọc inventory trong transaction.
2. Kiểm tra số có thể giữ chỗ, sau đó save entity **@Version**.
3. **insert** đơn hàng thay vì **save** để một **orderId** trùng không bị hiểu là cập nhật đơn cũ.
4. Ghi event cùng transaction.
5. Nếu một thao tác phát sinh runtime exception và transaction manager quản lý đúng session, Spring đánh dấu rollback theo quy tắc mặc định.

**Không bắt exception bên trong place rồi trả kết quả thành công**: việc nuốt lỗi có thể khiến transaction commit các thay đổi trước đó. Nếu phải chuyển loại lỗi, ném một exception phù hợp và xác định rollback rule khi dùng checked exception.

**Quan trọng về @Transactional:** với mô hình proxy của Spring, phải gọi **place(...) qua Spring-managed bean**, không gọi từ một phương thức khác cùng object qua **this.place(...)** rồi kỳ vọng annotation tự mở transaction. Phương thức được bao quanh bởi proxy phải thực sự được gọi từ bên ngoài proxy. Kiểm tra logging/monitoring transaction và đọc lại dữ liệu sau khi phương thức trả về.

## 7. @Version hoạt động như thế nào với transaction?

**Optimistic locking** và **multi-document transaction** giải quyết hai chiều khác nhau:

| Cơ chế | Bảo vệ chính | Trường hợp điển hình |
| --- | --- | --- |
| **@Version** | Tránh ghi đè bản document đã bị thay đổi từ lúc đọc | Hai người cùng cập nhật tồn kho, số dư hoặc trạng thái |
| **MongoDB transaction** | Commit/rollback nhất quán nhiều document | Giữ kho + tạo đơn + ghi event |
| **Unique _id / unique index** | Chặn dữ liệu trùng theo business key | orderId hoặc payment request ID |
| **Idempotency** | Xử lý retry request mà không thực thi nghiệp vụ hai lần | Timeout sau commit nhưng caller chưa nhận response |

Trong transaction, hai yêu cầu đồng thời có thể gặp **write conflict** hoặc transaction bị hủy bởi MongoDB, không nhất thiết luôn hiện ra dưới dạng **OptimisticLockingFailureException**. Không nên viết handler chỉ nhận một exception rồi cho rằng đã bao phủ toàn bộ xung đột.

~~~mermaid
flowchart TD
    A["Hai request giữ cùng một SKU"] --> B["Cả hai đọc inventory"]
    B --> C["Cả hai kiểm tra available"]
    C --> D["Yêu cầu thứ nhất cập nhật và commit"]
    D --> E["Yêu cầu còn lại gặp version/write conflict"]
    E --> F["Abort transaction hiện tại"]
    F --> G{"Có thể thử lại không?"}
    G -- "Có, lỗi transient và request còn hợp lệ" --> H["Bắt đầu transaction mới, đọc trạng thái mới"]
    G -- "Không" --> I["Trả lỗi có phân loại"]
    H --> J["Kiểm tra lại available, orderId và tính idempotent"]
~~~

Sau xung đột, không thử save lại **cùng entity cũ với version cũ** trong một transaction đã abort. Nếu được phép retry, hãy bắt đầu **transaction mới**, đọc lại inventory và kiểm tra lại toàn bộ bất biến. Khi tài nguyên đã bị giữ bởi request khác, lần thử lại có thể chuyển thành lỗi **Insufficient inventory**, và đó là kết quả nghiệp vụ hợp lệ.

## 8. Kiểm thử tích hợp với MongoDB replica set

Các bài unit test mock repository có thể kiểm tra nhánh **reserve(...)** nhưng **không** chứng minh transaction commit/rollback, BSON mapping, auditing callback hoặc conflict trên server. Để nghiệm thu, dùng **@SpringBootTest + Testcontainers** với replica set.

Trong ví dụ Spring Boot 3.x/Testcontainers 1.x, **MongoDBContainer.getReplicaSetUrl()** cung cấp URL replica set thử nghiệm. Việc container khởi chạy cần Docker hoặc runtime hỗ trợ. Phiên bản MongoDB nên tương thích môi trường production; **mongo:7.0** chỉ là một hình mẫu.

### 8.1. Bài test end-to-end tại tầng service

~~~java
package example.capstone;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class OrderPlacementIntegrationTest {

    @Container
    static final MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongodbProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }

    @Autowired OrderPlacementService service;
    @Autowired InventoryRepository inventoryRepository;
    @Autowired PurchaseOrderRepository orderRepository;
    @Autowired OrderEventRepository eventRepository;
    @Autowired MongoTemplate template;

    @BeforeEach
    void prepareFixture() {
        // Chuẩn bị collection ngoài transaction nghiệp vụ.
        if (!template.collectionExists(InventoryItem.class)) {
            template.createCollection(InventoryItem.class);
        }
        if (!template.collectionExists(PurchaseOrder.class)) {
            template.createCollection(PurchaseOrder.class);
        }
        if (!template.collectionExists(OrderEvent.class)) {
            template.createCollection(OrderEvent.class);
        }

        eventRepository.deleteAll();
        orderRepository.deleteAll();
        inventoryRepository.deleteAll();
        inventoryRepository.save(new InventoryItem("SKU-1", 3));
    }

    @Test
    void shouldCommitInventoryOrderAndEventTogether() {
        PurchaseOrder order = service.place("O-101", "SKU-1", 2);

        InventoryItem stock = inventoryRepository
            .findById("SKU-1").orElseThrow();
        PurchaseOrder persisted = orderRepository
            .findById("O-101").orElseThrow();
        OrderEvent event = eventRepository
            .findById("order-placed:O-101").orElseThrow();

        assertEquals(2, stock.getReserved());
        assertEquals(1, stock.getAvailable());
        assertEquals("O-101", order.getId());
        assertEquals(PurchaseOrder.Status.PLACED,
            persisted.getStatus());
        assertEquals("ORDER_PLACED", event.getType());

        assertNotNull(stock.getVersion());
        assertNotNull(persisted.getVersion());
        assertNotNull(stock.getCreatedAt());
        assertNotNull(stock.getUpdatedAt());
        assertNotNull(persisted.getCreatedAt());
        assertNotNull(persisted.getUpdatedAt());
        assertNotNull(event.getCreatedAt());
        assertEquals("capstone-operator", persisted.getCreatedBy());
    }

    @Test
    void shouldRollBackInventoryWhenOrderIdIsDuplicate() {
        orderRepository.insert(
            new PurchaseOrder("O-DUP", "SKU-1", 1)
        );

        assertThrows(DuplicateKeyException.class,
            () -> service.place("O-DUP", "SKU-1", 2));

        InventoryItem stock = inventoryRepository
            .findById("SKU-1").orElseThrow();

        assertEquals(0, stock.getReserved());
        assertEquals(1, orderRepository.count());
        assertFalse(eventRepository.existsById("order-placed:O-DUP"));
    }

    @Test
    void shouldRejectInsufficientStockWithoutPartialWrites() {
        assertThrows(IllegalStateException.class,
            () -> service.place("O-LOW", "SKU-1", 4));

        assertEquals(0, inventoryRepository
            .findById("SKU-1").orElseThrow().getReserved());
        assertFalse(orderRepository.existsById("O-LOW"));
        assertFalse(eventRepository.existsById("order-placed:O-LOW"));
    }

    @Test
    void staleInventoryVersionMustFail() {
        InventoryItem first = inventoryRepository
            .findById("SKU-1").orElseThrow();
        InventoryItem stale = inventoryRepository
            .findById("SKU-1").orElseThrow();

        first.reserve(1);
        inventoryRepository.save(first);

        stale.reserve(1);
        assertThrows(OptimisticLockingFailureException.class,
            () -> inventoryRepository.save(stale));

        assertEquals(1, inventoryRepository
            .findById("SKU-1").orElseThrow().getReserved());
    }
}
~~~

Điều kiện để chạy mẫu: cần class **@SpringBootApplication** trong package cha phù hợp và component scan thấy **OrderPlacementService**, các repository cùng **MongoInfrastructureConfiguration**. Nếu dự án có bean hệ thống khác yêu cầu Kafka, HTTP hoặc cloud credential, phải cung cấp test double/test environment phù hợp; lỗi do dependency ngoài không chứng minh transaction MongoDB sai.

**Không đánh dấu @Transactional trên chính lớp test** nếu mục tiêu là xem service commit/rollback thực tế. Test nên gọi service qua Spring proxy, để method kết thúc, rồi **đọc lại dữ liệu ngoài transaction đó**. Đặc biệt đừng chỉ assert giá trị trả về hoặc dữ liệu nằm trong persistence context của lời gọi.

### 8.2. Kiểm thử optimistic locking bằng hai bản đọc

Phương thức **staleInventoryVersionMustFail** đã nằm trong **OrderPlacementIntegrationTest** ở mục 8.1, vì vậy nó chạy với cùng MongoDB Testcontainer, fixture **SKU-1** và cấu hình auditing. Test cố ý:

1. Lấy hai bản copy từ database với **cùng version**.
2. Giữ hàng và save bản thứ nhất, làm version tăng.
3. Thử save bản thứ hai đã stale, chờ **OptimisticLockingFailureException**.
4. Đọc lại inventory từ MongoDB để xác nhận reserved vẫn là **1**, không bị ghi đè.

Không cần thêm một transaction bao quanh cả test: mục đích là quan sát version check ở mỗi lần save thực sự.

### 8.3. Kiểm tra optimistic locking sau transaction

Nếu có cơ chế cập nhật đơn hàng, thêm kịch bản:

1. Đọc order hai lần thành hai entity khác nhau với cùng version.
2. Save order thứ nhất và xác nhận version tăng.
3. Save order thứ hai dựa trên version cũ, kỳ vọng lỗi optimistic locking.
4. Đọc lại MongoDB và kiểm tra trạng thái cuối không bị ghi đè.
5. Đảm bảo audit **updatedAt/updatedBy** chỉ phản ánh thao tác đã commit; audit field trên object ở bộ nhớ chưa phải bằng chứng database đã commit.

## 9. Auditing: kiểm thử trường nào, ở thời điểm nào?

Auditing tự động có ích, nhưng cần xác định rõ những assertion có thể chấp nhận:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Insert inventory mới | createdAt/updatedAt được ghi theo cấu hình auditing, version được khởi tạo |
| Save inventory đang tồn tại | version tăng, updatedAt và updatedBy theo auditing policy |
| Insert order | createdAt, updatedAt, createdBy, updatedBy theo chính sách; status PLACED |
| Insert event | createdAt được điền khi event được insert qua Spring Data |
| Transaction rollback | Thay đổi audit trên DB không được commit; object Java cũ có thể vẫn giữ thay đổi trong bộ nhớ |
| Update raw không qua mapping callback | Không giả định audit tự động kích hoạt; cần kiểm thử và tự quản lý metadata |

Một ví dụ assertion cho bản ghi sau update:

~~~java
InventoryItem before = inventoryRepository
    .findById("SKU-1").orElseThrow();
Long oldVersion = before.getVersion();

before.reserve(1);
inventoryRepository.save(before);

InventoryItem after = inventoryRepository
    .findById("SKU-1").orElseThrow();
assertNotNull(after.getVersion());
assertTrue(after.getVersion() > oldVersion);
assertEquals("capstone-operator", after.getUpdatedBy());
assertNotNull(after.getUpdatedAt());
~~~

Đoạn trên là phần thân test dùng fixture đã có **SKU-1**. Không cần assert **updatedAt > createdAt** đến từng mili giây: hai thao tác đủ gần nhau có thể có cùng timestamp ở độ chính xác BSON Date. Hãy kiểm tra tính hiện diện, thứ tự hợp lệ hoặc dùng **DateTimeProvider** cố định nếu cần xác minh thời điểm chính xác.

**Auditing không tự động xác nhận an toàn bảo mật.** AuditorAware đọc một username từ request vẫn có thể bị giả mạo nếu ứng dụng lấy trực tiếp từ header không đáng tin. Trong production, lấy actor từ context xác thực đã được kiểm tra, và dùng system actor tách biệt cho batch/maintenance.

## 10. Xử lý lỗi, retry và idempotency

### 10.1. Phân loại lỗi thay vì retry tất cả

| Lỗi | Ví dụ | Hành động phù hợp |
| --- | --- | --- |
| **Không đủ tồn kho** | quantity > available | Trả lỗi nghiệp vụ; không retry mù |
| **Unknown SKU** | Không có inventory document | Trả lỗi dữ liệu đầu vào hoặc domain |
| **DuplicateKeyException** | orderId đã tồn tại | Kiểm tra idempotency: request có cùng nội dung với đơn đã lưu không? |
| **OptimisticLockingFailureException** | Save dựa trên version cũ | Đọc lại entity trong transaction mới nếu chính sách cho phép |
| **Transient transaction/write conflict** | Nhiều transaction tranh cùng document | Có thể retry có giới hạn, backoff và jitter |
| **Unknown transaction commit result** | Timeout trong lúc commit | Không tự kết luận transaction đã rollback; xác minh orderId |
| **Không có replica set** | Transaction fail ở standalone | Sửa topology/cấu hình; không retry vô hạn |

**Một ngoại lệ quan trọng:** timeout sau lúc client gửi commit không chứng minh server chưa commit. Nếu caller nhận lỗi và lặp lại **orderId khác**, việc giữ hàng có thể xảy ra hai lần. Cần **idempotency key** ổn định cho mỗi yêu cầu, lưu request fingerprint và kết quả; một lần retry phải xác định nó là **cùng yêu cầu** hay yêu cầu mới.

Ví dụ chính sách idempotency ở cấp thiết kế:

~~~text
requestKey = "checkout-request-123"
payload   = { sku: "SKU-1", quantity: 2 }

Lần đầu:
  transaction commit -> tạo order, giữ tồn kho và lưu requestKey.

Retry sau timeout:
  tìm requestKey đã commit;
  nếu payload giống nhau, trả lại kết quả cũ;
  nếu payload khác nhau, báo xung đột;
  không tạo order khác hoặc giữ tồn kho lần hai.
~~~

Ví dụ code dịch vụ đang dùng **orderId** như một business key duy nhất, đủ để thử tình huống duplicate. Nó **chưa** là một cơ chế idempotency production hoàn chỉnh: cần xử lý concurrent retry, matching payload, phản hồi khi transaction commit không rõ và retention của request key.

### 10.2. Retry bên ngoài transaction

Với **@Transactional**, một lời gọi bị abort không thể dùng tiếp session/transaction cũ. Nếu muốn retry, lớp orchestration ở **ngoài transaction** phải tạo một lời gọi mới qua proxy, nạp lại document và kiểm tra lại bất biến. Cần retry có giới hạn, **exponential backoff với jitter**, metric, timeout và cơ chế phân loại lỗi theo error label/driver.

Không đặt một vòng **for retry** bên trong **place(...)** rồi tiếp tục sử dụng repository/entity cũ sau exception, vì transaction đã thất bại. Nếu sử dụng thư viện retry/transaction template, kiểm tra **thứ tự interceptor** để mỗi lần retry được thực thi trong transaction mới.

### 10.3. MongoDB transaction không bao gồm Kafka và email

Nếu yêu cầu tiếp theo là “gửi email xác nhận khi đặt hàng thành công”, **không** gọi trực tiếp email API bên trong MongoDB transaction rồi xem đó là atomic. Email có thể đã được gửi nhưng transaction bị rollback.

Một mô hình mở rộng là **transactional outbox**:

1. Cùng transaction MongoDB: giữ tồn kho, ghi order và ghi **outbox event**.
2. Sau commit: một worker đọc outbox rồi gửi email/Kafka.
3. Worker có retry/idempotency riêng; đánh dấu event đã gửi hoặc duy trì trạng thái xử lý.

Collection **order_events** trong bài có thể làm điểm khởi đầu về mặt dữ liệu, nhưng để trở thành outbox production cần thêm trạng thái gửi, claim/lease, retry, idempotent consumer, xử lý duplicate, giám sát lag và retention. Transaction chỉ đảm bảo ghi event **cùng database**, không đảm bảo broker ngoài nhận thông điệp một lần duy nhất.

## 11. Quan sát và chẩn đoán khi triển khai

Khi xảy ra lỗi, log và metric phải đủ để phân biệt:

- Không tìm thấy SKU hoặc thiếu stock.
- Trùng orderId.
- Optimistic version conflict.
- MongoDB write conflict/transaction abort.
- Timeout/unknown commit result.
- Lỗi không kết nối được replica set hoặc thiếu quyền.

Ghi **correlation ID, orderId, SKU, loại lỗi, transaction retry count, latency và phiên bản ứng dụng**. Tránh log secret, thông tin thanh toán nhạy cảm, raw credentials hoặc toàn bộ payload người dùng.

Ví dụ lệnh **mongosh** dùng để xác minh trạng thái sau một bài kiểm thử:

~~~javascript
db.inventory.findOne({ _id: "SKU-1" });

db.orders.findOne({ _id: "O-101" });

db.order_events.findOne({ _id: "order-placed:O-101" });
~~~

Kiểm tra server/topology khi transaction không khởi động:

~~~javascript
db.adminCommand({ hello: 1 });
db.adminCommand({ buildInfo: 1 });

// Cần quyền phù hợp, một số dịch vụ managed giới hạn.
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

**Chú ý về rollback:** sau transaction thất bại, object Java trong bộ nhớ có thể đã bị sửa **reserved**, audit fields hoặc version trước khi driver trả lỗi. Chỉ coi **document đọc lại từ MongoDB sau khi rollback** là bằng chứng trạng thái đã commit. Không trả object chưa commit như phản hồi “thành công”.

## 12. Hiệu năng và giới hạn của transaction nhiều document

Transactions có chi phí tài nguyên, snapshot, lock/conflict và thời gian commit. Với một đơn hàng có nhiều SKU hoặc hàng nghìn document, một transaction dài dễ tăng conflict, áp lực bộ nhớ và độ trễ.

| Vấn đề | Thiết kế khuyến nghị |
| --- | --- |
| Transaction kéo dài | Chỉ giữ lệnh MongoDB thật sự cần atomic; không chờ HTTP/email bên trong |
| Nhiều request tranh một SKU | Theo dõi write conflict; cân nhắc thao tác **atomic conditional update** trên một document |
| Nhiều update đọc–sửa–ghi | Dùng **@Version** và transaction/retry phù hợp; hoặc cập nhật nguyên tử theo điều kiện |
| Sự kiện phát sinh liên tục | Ghi outbox event cùng DB và xử lý gửi bên ngoài |
| Hàng nghìn đơn hàng một lô | Chia workload, tránh transaction cực lớn; xác định lại đơn vị atomic của nghiệp vụ |
| Write concern không acknowledged | Không bảo đảm cơ chế optimistic locking phát hiện xung đột đúng như kỳ vọng |

**Phương án nâng cao cho tồn kho nóng:** nếu chỉ cần giữ chỗ trong **một document**, có thể dùng **MongoTemplate.findAndModify** hoặc **updateFirst** với điều kiện available đủ, sao cho kiểm tra và tăng reserved là **một thao tác nguyên tử trên document**. Ví dụ có thể lưu trực tiếp **available** rồi dùng điều kiện **available ≥ quantity** và **$inc** tương ứng; khi đó cần xác định rõ bất biến dữ liệu và version/audit update. Trong capstone hiện tại, sử dụng **read + @Version + transaction** để minh họa rõ optimistic locking và atomic nhiều document, không khẳng định đây luôn là kiến trúc tối ưu cho SKU cực nóng.

## 13. Các lỗi triển khai thường gặp

| Biểu hiện | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| Có @Transactional nhưng inventory vẫn cập nhật khi tạo order lỗi | Method không đi qua Spring proxy; dùng sai DB factory hoặc transaction manager | Xác minh bean/proxy, transaction manager, cùng MongoClient/session; test rollback thực |
| Transaction báo lỗi replica set | Kết nối tới standalone | Chạy replica set/sharded cluster hỗ trợ transaction |
| Audit fields rỗng | Thiếu **@EnableMongoAuditing**, thiếu AuditorAware cho trường actor, entity không qua callback | Kiểm tra cấu hình audit và đường ghi entity |
| Version không tăng | Cập nhật trực tiếp không qua save versioned entity hoặc version mapping sai | Kiểm tra **@Version** và command update thực |
| Hai request cùng thành công dù chỉ còn đủ một đơn | Thiếu kiểm soát concurrency/bất biến hoặc bỏ qua write conflict | Thử song song, kiểm tra version/conditional update và trạng thái cuối |
| Có lỗi version nhưng retry mãi | Không đọc lại state, retry trong transaction cũ | Retry bên ngoài transaction, giới hạn số lần, backoff |
| Sau timeout đặt hàng hai lần | Chưa có idempotency key/cơ chế xác minh commit | Dùng orderId/request key duy nhất, đối chiếu payload |
| Sau rollback test vẫn thấy reserved tăng trong object Java | Object trong bộ nhớ đã thay đổi nhưng DB không commit | Đọc lại từ repository ngoài transaction để assert |
| Spring Boot/Spring Data khác major | Import/config Testcontainers hoặc Mongo property không khớp | Đối chiếu BOM và migration guide, không ghép thư viện tùy ý |

## 14. Bài tập mở rộng

### Bài A — Hủy đơn hàng

Bổ sung **OrderCancellationService** trong một MongoDB transaction:

1. Đọc order có status **PLACED**.
2. Kiểm tra version hiện tại, chuyển sang **CANCELLED**.
3. Giảm **reserved** của inventory tương ứng, không để reserved âm.
4. Lưu order, inventory và thêm sự kiện **ORDER_CANCELLED** cùng transaction.
5. Kiểm thử hủy thành công, hủy lần hai, không có order, xung đột version và rollback khi lưu event lỗi.

**Lưu ý:** event id ví dụ **"order-placed:" + orderId** phải được mở rộng thành định danh mới cho sự kiện **ORDER_CANCELLED**, không tái sử dụng khóa của event đặt hàng.

### Bài B — Kiểm thử hai request đồng thời

Dùng **CountDownLatch** hoặc executor có điều phối để hai request cùng cố giữ **2** đơn vị của SKU chỉ còn **3** đơn vị. Yêu cầu:

- Chỉ có một request được commit thành công với số lượng 2 nếu không có bổ sung stock.
- Request còn lại nhận lỗi conflict hoặc lỗi thiếu tồn kho sau retry.
- **reserved** cuối cùng không vượt **onHand**.
- Số lượng order/event khớp số transaction đã commit.

Đừng viết bài test chỉ gọi hai request tuần tự hoặc mock MongoRepository: nó không chứng minh race condition. Đồng thời, test concurrency không nên phụ thuộc vào thứ tự thread thắng; hãy assert **bất biến cuối cùng**.

### Bài C — Tích hợp bảo mật audit

Thay **capstone-operator** bằng một **AuditorAware<String>** lấy user ID từ security context được xác thực. Bổ sung xử lý cho request không có đăng nhập và batch job với system identity; kiểm thử việc user A sửa document do user B tạo:

- **createdBy** giữ nguyên B.
- **updatedBy** chuyển sang A.
- **createdAt** không bị thay thế bởi **updatedAt**.
- Version tăng khi cập nhật thật sự qua save entity.

### Bài D — Xử lý event ngoài transaction

Thiết kế outbox worker gửi sự kiện sang broker hoặc dịch vụ email; mô tả retry, idempotency, trạng thái xử lý, khả năng chạy trùng và cách khôi phục sau crash. Không được khẳng định MongoDB transaction giúp “exactly once delivery” tới hệ thống bên ngoài.

## 15. Checklist nghiệm thu capstone

- [ ] Inventory dùng **@Version** và giữ bất biến **0 ≤ reserved ≤ onHand**.
- [ ] Order dùng **@Version**; thao tác ghi mới dùng định danh duy nhất và không ghi đè order trùng.
- [ ] Các entity cần audit có **@CreatedDate / @LastModifiedDate** và actor metadata phù hợp.
- [ ] Có **@EnableMongoAuditing**, **AuditorAware** đúng ngữ cảnh và đã kiểm tra callback thực.
- [ ] Có **MongoTransactionManager** và service chạy **@Transactional** qua Spring proxy.
- [ ] MongoDB test là replica set/sharded cluster hỗ trợ transaction.
- [ ] Bài test thành công đọc lại đủ inventory/order/event sau commit.
- [ ] Bài test lỗi ở bước insert order chứng minh inventory **không** bị commit dở.
- [ ] Bài test stale version chứng minh không bị mất update.
- [ ] Có kịch bản concurrency để assert bất biến cuối cùng.
- [ ] Có chính sách xử lý xung đột, transient retry và unknown commit result.
- [ ] Có kế hoạch idempotency cho request lặp lại và outbox khi tích hợp hệ thống ngoài.
- [ ] Không đặt mạng ngoài, email hoặc broker call bên trong MongoDB transaction với kỳ vọng atomic.
- [ ] Log và metric giúp chẩn đoán lỗi mà không lộ dữ liệu nhạy cảm.

## 16. Tài liệu tham khảo

1. [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking): annotation **@Version**, cách phát hiện stale update và write concern.
2. [Spring Data MongoDB — Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html): **@EnableMongoAuditing**, **AuditorAware**, metadata người tạo/người sửa và thời điểm.
3. [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): **MongoTransactionManager**, session, transaction và giới hạn của việc thực thi.
4. [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): proxy, **@Transactional**, rollback rules và transaction propagation.
5. [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): topology, atomic nhiều document, lỗi và các giới hạn.
6. [MongoDB Manual — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/): lock, timeout, concurrency, resource và các đặc điểm vận hành.
7. [MongoDB Manual — Retryable Writes and Transaction Errors](https://www.mongodb.com/docs/manual/core/retryable-writes/): phân biệt retryable writes và lỗi transaction, xem tài liệu driver tương ứng.
8. [Testcontainers — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): tạo môi trường MongoDB thử nghiệm, bao gồm replica set URL.

**Kết luận:** **@Version** bảo vệ thao tác cập nhật khỏi sử dụng dữ liệu đã cũ; **auditing** cho biết ai và khi nào thay đổi; **MongoDB transaction** giữ nhất quán việc lưu nhiều document cùng lúc. Một capstone đạt yêu cầu không chỉ có annotation đúng: nó phải **chứng minh bằng dữ liệu MongoDB thật** rằng thành công được commit trọn vẹn, thất bại rollback, xung đột không làm mất update và metadata audit phản ánh các thay đổi đã được lưu.
