# @Transactional ở tầng dịch vụ với nhiều repository/template

## 1. Khi một thao tác nghiệp vụ cần nhiều lần ghi MongoDB

Một khách mua hai sản phẩm trong ứng dụng thương mại điện tử. Để ghi nhận việc đặt hàng, hệ thống có thể phải:

1. Trừ hoặc giữ số lượng tồn kho.
2. Tạo đơn hàng.
3. Ghi nhật ký thay đổi tồn kho.
4. Ghi một sự kiện để hệ thống khác xử lý sau khi đơn được xác nhận.

Nếu chương trình thực hiện từng thao tác riêng:

~~~text
MongoTemplate.updateFirst(inventory)  -> thành công
OrderRepository.insert(order)          -> thành công
MovementRepository.insert(movement)    -> lỗi

Kết quả: tồn kho đã giảm, đơn hàng đã có, nhưng nhật ký bị thiếu.
~~~

Một **atomic update trên một document** không tự biến ba lần ghi vào ba document hoặc collection khác nhau thành một đơn vị **all-or-nothing**. Khi nghiệp vụ yêu cầu những ghi MongoDB này **cùng commit hoặc cùng rollback**, chúng ta cần **MongoDB multi-document transaction**.

Spring Data MongoDB cung cấp **MongoTransactionManager** và tích hợp với **@Transactional** của Spring. Đặt annotation ở **tầng service** giúp gom các lời gọi repository và MongoTemplate nằm trong cùng transaction, thay vì đặt transaction rời rạc trên từng repository method.

Bài **@Transactional ở tầng dịch vụ với nhiều repository/template** thuộc chương **Session và giao dịch** trong module **SPRING_DATA_MONGODB**. Module học kết nối và ánh xạ document, thao tác MongoDB bằng repository hoặc MongoTemplate, thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

Sau bài học, bạn có thể:

- Cấu hình MongoTransactionManager với MongoDatabaseFactory thích hợp.
- Hiểu **ClientSession**, transaction và cơ chế truyền session trong Spring.
- Dùng **@Transactional** tại service khi gọi nhiều MongoRepository và MongoTemplate.
- Xác nhận commit/rollback thực, thay vì chỉ thấy annotation trong mã.
- Giải thích các lỗi **self-invocation**, bắt nuốt exception, nhiều transaction managers và vượt ranh giới thread.
- Xử lý **write conflict**, retry, commit chưa rõ kết quả và idempotency.
- Phân biệt transaction MongoDB với lời gọi HTTP/payment bên ngoài.
- Xây dựng biến thể **ReactiveMongoTransactionManager** và kiểm thử trên replica set.

## 2. Phân biệt tính nguyên tử một document và một transaction

MongoDB bảo đảm atomicity cho **một thao tác ghi trên một document**. Ví dụ:

~~~javascript
db.inventories.updateOne(
  {
    _id: productId,
    tenantId: "shop-a",
    available: { $gte: 2 }
  },
  {
    $inc: { available: -2, reserved: 2 }
  }
);
~~~

Đây là **một lệnh update một document**, nên hai phép thay đổi available và reserved đi cùng nhau. Không cần multi-document transaction chỉ để cập nhật đồng thời hai field của **cùng document**.

Nhưng nếu sau đó cần ghi order:

~~~javascript
db.orders.insertOne({
  tenantId: "shop-a",
  requestId: "checkout-123",
  status: "RESERVED"
});
~~~

thì lệnh update và insert **không tự cùng commit/rollback** khi thực hiện độc lập. Một lỗi giữa hai lệnh có thể khiến inventory thay đổi mà order không tồn tại.

| Trường hợp | Cơ chế cần cân nhắc |
| --- | --- |
| Chỉ giảm số lượng trên một inventory document | Điều kiện available >= qty + $inc nguyên tử |
| Giảm available và tăng reserved trong cùng inventory document | Một update với hai toán tử $inc |
| Giảm inventory và tạo order trong hai collection | Transaction MongoDB nếu phải cùng commit/rollback |
| Tạo order, movement và outbox event trong MongoDB | Một transaction cho các ghi liên quan |
| Trừ inventory và thu tiền qua cổng thanh toán ngoài MongoDB | Saga, trạng thái nghiệp vụ, idempotency/outbox |
| Chỉ đọc vài document cho báo cáo | Không mặc nhiên cần transaction dài |

**Transaction không thay thế điều kiện nghiệp vụ trong update.** Khi trừ kho, vẫn phải kiểm tra available >= quantity; một transaction không tự biết “không được bán quá tồn”.

## 3. ClientSession là nền tảng của MongoDB transaction

MongoDB transaction được gắn với một **ClientSession**. Các thao tác muốn cùng thuộc một transaction phải được thực thi trên session thích hợp, trong phạm vi transaction đó.

~~~mermaid
flowchart TB
    A["HTTP request / job"] --> B["CheckoutService.placeOrder"]
    B --> C["@Transactional + MongoTransactionManager"]
    C --> D["ClientSession / MongoDB transaction"]
    D --> E["MongoTemplate: update inventory"]
    D --> F["OrderRepository: insert order"]
    D --> G["MovementRepository: insert movement"]
    E --> H{"Commit hay rollback?"}
    F --> H
    G --> H
    H -->|Không có lỗi| I["Commit cả ba thao tác"]
    H -->|Rollback| J["Bỏ các thay đổi của transaction"]
~~~

Trong stack Spring Data MongoDB **đồng bộ**:

1. Spring transaction interceptor gọi transaction manager khi phương thức @Transactional được đi qua đúng proxy.
2. MongoTransactionManager tạo/tham gia transaction và gắn session vào **thread** hiện hành thông qua cơ chế resource synchronization của Spring.
3. MongoTemplate và repository dùng cùng cấu hình MongoDatabaseFactory có thể phát hiện session đang được gắn và tham gia transaction.
4. Khi service hoàn tất, Spring commit; khi gặp lỗi cần rollback, Spring abort transaction.

**Không phải mọi lời gọi đến MongoDB trong JVM đều tự tham gia**. Nếu tự tạo một MongoClient mới, tự mở session độc lập hoặc chạy MongoDB operation trên thread khác mà không giữ context đúng, thao tác đó có thể nằm ngoài transaction.

### 3.1. Session không đồng nghĩa transaction

ClientSession còn có thể phục vụ các khả năng khác như causal consistency. **Có session** chưa có nghĩa **đã start một transaction**. Cần phân biệt:

- Lời gọi thường, không có session được quản lý.
- Lời gọi trong session nhưng không có active transaction.
- Lời gọi nằm trong một transaction đã bắt đầu với session.

Với bài này, **@Transactional + MongoTransactionManager** phụ trách tạo ranh giới transaction đồng bộ.

### 3.2. Session gắn với transaction không dành để chia sẻ tùy tiện

Không giữ ClientSession trong singleton bean hoặc truyền nó qua nhiều request song song. Với imperative transaction, Spring quản lý session theo phạm vi thực thi phù hợp; để MongoTemplate/repository tham gia qua integration chính thức, thay vì giữ session ở field toàn cục.

## 4. Điều kiện môi trường để chạy transaction

MongoDB multi-document transactions cần một **deployment tương thích**, ví dụ replica set hoặc sharded cluster được hỗ trợ ở phiên bản MongoDB Server thích hợp.

Một **standalone mongod** không phải môi trường đủ để kiểm thử đúng transaction nhiều document. Lệnh chạy có thể báo lỗi tương tự:

~~~text
Transaction numbers are only allowed on a replica set member or mongos
~~~

Vì vậy, một integration test chỉ dùng mongod standalone có thể kiểm thử CRUD bình thường nhưng thất bại khi bật @Transactional.

### 4.1. Những điều kiện cần kiểm tra

- MongoDB Server hỗ trợ transaction trên topology đang sử dụng.
- Driver MongoDB và Spring Data MongoDB thuộc các thế hệ tương thích.
- Các repository và MongoTemplate được cấu hình tới **cùng MongoDB deployment** và tham gia transaction qua factory/session phù hợp.
- MongoTransactionManager được khai báo và transaction management được kích hoạt.
- Database user có quyền đọc/ghi các collection trong transaction.
- Các collection/index cần thiết đã được tạo/migrate phù hợp trước khi mở transaction nghiệp vụ.
- Write concern, read concern, read preference và thời hạn transaction đáp ứng yêu cầu vận hành.

Các ràng buộc về transaction trên sharded cluster, các thao tác DDL và thời gian cho phép có thể phụ thuộc phiên bản server. **Không suy rằng một đoạn mã @Transactional có thể chạy mọi nơi chỉ vì MongoTemplate đã kết nối thành công.**

### 4.2. Không dùng production để thử rollback

Không cố ý xóa đơn hàng hoặc làm lỗi transaction trên database production để kiểm chứng cơ chế. Dùng replica set riêng cho integration tests, ví dụ Testcontainers hoặc môi trường test tương đương.

## 5. Ba collection trong ví dụ checkout

Chúng ta sử dụng ba collection:

| Collection | Vai trò | Điều kiện quan trọng |
| --- | --- | --- |
| inventories | Available và reserved theo mặt hàng | available >= requested quantity |
| orders | Ghi nhận checkout theo requestId | Unique tenantId + requestId |
| inventory_movements | Nhật ký giữ hàng | Liên kết requestId, inventoryId và số lượng |

Inventory document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  sku: "BOOK-101",
  available: NumberLong("8"),
  reserved: NumberLong("0")
}
~~~

Order document sau khi reserve thành công:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  requestId: "checkout-123",
  inventoryId: ObjectId("507f1f77bcf86cd799439011"),
  quantity: NumberLong("2"),
  status: "RESERVED",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Movement document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439013"),
  tenantId: "shop-a",
  requestId: "checkout-123",
  inventoryId: ObjectId("507f1f77bcf86cd799439011"),
  quantity: NumberLong("2"),
  kind: "RESERVE",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

**Định nghĩa bất biến:** một yêu cầu giữ 2 món sẽ trừ available đi 2 và cộng reserved thêm 2, đồng thời tạo order và movement tương ứng. Không ghi một order “RESERVED” nếu tồn kho không được giữ thành công.

### 5.1. Model Java

~~~java
package com.example.checkout;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inventories")
public record InventoryDocument(
    @Id ObjectId id,
    String tenantId,
    String sku,
    long available,
    long reserved
) {}

@Document(collection = "orders")
@CompoundIndex(
    name = "uk_orders_tenant_request",
    def = "{ 'tenantId': 1, 'requestId': 1 }",
    unique = true
)
public record OrderDocument(
    @Id ObjectId id,
    String tenantId,
    String requestId,
    ObjectId inventoryId,
    long quantity,
    String status,
    Instant createdAt
) {}

@Document(collection = "inventory_movements")
public record InventoryMovementDocument(
    @Id ObjectId id,
    String tenantId,
    String requestId,
    ObjectId inventoryId,
    long quantity,
    String kind,
    Instant createdAt
) {}
~~~

Các record trên được trình bày chung một khối cho dễ theo dõi; khi triển khai Java thật, đặt mỗi **public record** trong file riêng theo quy tắc Java.

### 5.2. Repository interfaces

~~~java
package com.example.checkout;

import java.util.Optional;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {

    Optional<OrderDocument> findByTenantIdAndRequestId(
        String tenantId, String requestId
    );
}

public interface InventoryMovementRepository
        extends MongoRepository<InventoryMovementDocument, ObjectId> {
}
~~~

Tương tự, mỗi **public interface** nằm trong một source file riêng. Spring Data tạo implementation cho repository và sử dụng MongoDB mapping được quản lý.

### 5.3. Unique index phải tồn tại thực

Annotation @CompoundIndex là metadata; việc tạo index phụ thuộc auto-index-creation hoặc migration.

~~~javascript
db.orders.createIndex(
  { tenantId: 1, requestId: 1 },
  {
    unique: true,
    name: "uk_orders_tenant_request"
  }
);
~~~

Một transaction không tự ngăn cùng requestId được xử lý hai lần nếu code thiếu cơ chế chống trùng. **Unique index** giúp ràng buộc dữ liệu; **business workflow** còn phải kiểm tra payload và xử lý lần gửi lại.

## 6. Đăng ký MongoTransactionManager

Trong một ứng dụng Spring Data MongoDB đồng bộ, khai báo một transaction manager sử dụng chính **MongoDatabaseFactory** mà MongoTemplate/repository đang dùng.

~~~java
package com.example.checkout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class MongoTransactionConfiguration {

    @Bean("mongoTransactionManager")
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

**@EnableTransactionManagement** cho phép Spring áp dụng transaction interceptor theo cơ chế cấu hình proxy phù hợp. Với Spring Boot, transaction management có thể đã được kích hoạt qua auto-configuration; ví dụ khai báo tường minh để bài học dễ kiểm chứng.

**Tên bean mongoTransactionManager** giúp chỉ rõ transaction manager dùng khi ứng dụng có cả MongoDB và một database khác.

### 6.1. Không dùng nhầm DataSourceTransactionManager

Nếu ứng dụng có JDBC/JPA cùng MongoDB:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public OrderDocument placeOrder(...) {
    // Các thao tác MongoDB.
}
~~~

Ở đây transactionManager chọn **MongoTransactionManager**. Nếu không chỉ định và có nhiều PlatformTransactionManager, việc tìm bean mặc định có thể mơ hồ hoặc chọn manager không mong muốn.

**DataSourceTransactionManager hoặc JpaTransactionManager không tự quản lý MongoDB ClientSession.**

### 6.2. Không tạo MongoClient/MongoTemplate mới tùy ý

Ví dụ sai:

~~~java
// Không nên tạo client riêng bên trong service đang @Transactional.
MongoClient customClient = MongoClients.create(otherConnectionUri);
MongoDatabase rawDb = customClient.getDatabase("catalog");
rawDb.getCollection("orders").insertOne(document);
~~~

Lời gọi trên không tự tham gia session được MongoTransactionManager gắn với các Spring Data operations. Hãy dùng các repository/MongoTemplate cùng factory, hoặc quản lý transaction/session thủ công nếu chủ ý dùng raw driver.

### 6.3. DatabaseFactory và tên database

Một transaction có thể làm việc với các collection được MongoDB hỗ trợ trên cùng deployment, nhưng việc ứng dụng có **hai MongoDatabaseFactory**, hai MongoClient hoặc hai MongoTransactionManager không tự khiến chúng trở thành một transaction toàn cục.

Nếu giao dịch phải đi qua nhiều datasource/cluster, cần đánh giá chiến lược riêng; **một @Transactional trên MongoTransactionManager không phải distributed transaction coordinator**.

## 7. Dịch vụ checkout dùng MongoTemplate và hai repository

Tầng service là nơi đặt ranh giới nghiệp vụ. Ví dụ:

~~~java
package com.example.checkout;

import java.time.Instant;
import java.util.Optional;
import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public record CheckoutCommand(
    ObjectId inventoryId,
    String requestId,
    long quantity
) {}

@Service
public class CheckoutService {

    private final MongoTemplate mongoTemplate;
    private final OrderRepository orderRepository;
    private final InventoryMovementRepository movementRepository;

    public CheckoutService(
            MongoTemplate mongoTemplate,
            OrderRepository orderRepository,
            InventoryMovementRepository movementRepository) {
        this.mongoTemplate = mongoTemplate;
        this.orderRepository = orderRepository;
        this.movementRepository = movementRepository;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public OrderDocument reserve(
            String authenticatedTenantId,
            CheckoutCommand command) {

        validate(authenticatedTenantId, command);

        Optional<OrderDocument> existing =
            orderRepository.findByTenantIdAndRequestId(
                authenticatedTenantId, command.requestId());

        if (existing.isPresent()) {
            assertSameRequest(existing.get(), command);
            return existing.get();
        }

        Query filter = Query.query(
            Criteria.where("_id").is(command.inventoryId())
                .and("tenantId").is(authenticatedTenantId)
                .and("available").gte(command.quantity())
        );

        Update change = new Update()
            .inc("available", -command.quantity())
            .inc("reserved", command.quantity());

        var result = mongoTemplate.updateFirst(
            filter, change, InventoryDocument.class);

        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                "Inventory write not acknowledged");
        }
        if (result.getModifiedCount() != 1) {
            throw new OutOfStockException();
        }

        Instant now = Instant.now();
        OrderDocument order = orderRepository.insert(
            new OrderDocument(
                new ObjectId(),
                authenticatedTenantId,
                command.requestId(),
                command.inventoryId(),
                command.quantity(),
                "RESERVED",
                now
            )
        );

        movementRepository.insert(
            new InventoryMovementDocument(
                new ObjectId(),
                authenticatedTenantId,
                command.requestId(),
                command.inventoryId(),
                command.quantity(),
                "RESERVE",
                now
            )
        );

        return order;
    }

    private static void validate(
            String tenantId, CheckoutCommand command) {
        if (tenantId == null || tenantId.isBlank()
                || command == null
                || command.inventoryId() == null
                || command.requestId() == null
                || command.requestId().isBlank()
                || command.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid checkout command");
        }
    }

    private static void assertSameRequest(
            OrderDocument existing, CheckoutCommand command) {
        if (!existing.inventoryId().equals(command.inventoryId())
                || existing.quantity() != command.quantity()) {
            throw new IllegalArgumentException(
                "Idempotency key reused with different payload");
        }
    }
}

public class OutOfStockException extends RuntimeException {
    public OutOfStockException() {
        super("Inventory unavailable");
    }
}
~~~

**Lưu ý về cách tổ chức code:** CheckoutCommand, CheckoutService và OutOfStockException là các public type riêng, cần đặt thành những file Java riêng trong dự án thực. Ví dụ đã rút gọn phần HTTP/authentication để tập trung vào transaction.

**authenticatedTenantId** phải do lớp xác thực/ủy quyền của server xác định, không được lấy nguyên xi từ request parameter của người dùng chưa được kiểm tra.

### 7.1. Ba thao tác MongoDB trong một ranh giới

~~~text
@Transactional CheckoutService.reserve(...)
    |
    +-- MongoTemplate.updateFirst(inventories)
    |       condition: available >= quantity
    |       update: inc(available,-quantity), inc(reserved,+quantity)
    |
    +-- OrderRepository.insert(orders)
    |
    +-- InventoryMovementRepository.insert(inventory_movements)
    |
    +-- Spring transaction interceptor: commit / rollback
~~~

Tất cả tham gia cùng transaction khi bean wiring, transaction manager và session binding đúng.

### 7.2. Đừng bỏ điều kiện available >= quantity

**@Transactional không ngăn bán vượt tồn một cách tự động.** Nếu các request chỉ gọi:

~~~java
new Update().inc("available", -quantity);
~~~

mà thiếu predicate available>=quantity, mỗi transaction có thể giảm hàng ngoài giới hạn. Giữ bất biến trực tiếp trong filter và kiểm tra UpdateResult.

### 7.3. Vì sao không bắt OutOfStockException ngay trong service?

Phương thức reserve ném một RuntimeException khi không thể giữ hàng. Mặc định Spring sẽ đánh dấu transaction rollback với exception loại này.

Nếu bắt exception trong service rồi trả một DTO lỗi bình thường mà **không đánh dấu rollback**, transaction interceptor có thể coi method đã thành công và commit những ghi trước đó.

### 7.4. Lưu ý về tính duy nhất của requestId

Đọc existing order trước khi tạo **không đủ chống race**:

~~~text
Transaction A: không thấy requestId
Transaction B: không thấy requestId
Transaction A: insert order
Transaction B: insert order
~~~

Unique index trên tenantId+requestId là lớp bảo vệ bắt buộc. Khi gặp duplicate/write conflict, ứng dụng cần xử lý ở **ngoài transaction đã thất bại**, đọc lại trạng thái theo requestId và xác minh payload. Không nuốt exception bên trong transaction rồi tiếp tục ghi.

## 8. Commit và rollback được quyết định khi nào?

Với một service method được Spring transaction interceptor quản lý:

~~~text
Proxy bắt đầu transaction
    -> service gọi nhiều repository/template
    -> method trả về bình thường
    -> transaction manager commit
    -> proxy trả kết quả cho caller
~~~

Nếu method ném exception đáp ứng quy tắc rollback:

~~~text
Proxy bắt đầu transaction
    -> update inventory
    -> insert order
    -> insert movement lỗi
    -> exception thoát ra khỏi service
    -> transaction manager abort/rollback
    -> caller nhận exception
~~~

**Các thao tác MongoDB đã được thực hiện bên trong transaction không trở thành dữ liệu commit riêng lẻ**. Nếu transaction abort đúng cách, inventory update và order insert trước đó cũng bị rollback.

### 8.1. Quy tắc rollback mặc định của Spring

Mặc định, Spring declarative transaction đánh dấu rollback khi gặp:

- **RuntimeException** và các lớp con.
- **Error**.

Còn checked exception (ví dụ IOException) **không mặc định luôn gây rollback** theo quy tắc chung của @Transactional.

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    rollbackFor = Exception.class
)
public void placeAndExport(...) throws IOException {
    // Khi cần cả checked exception làm transaction rollback.
}
~~~

Chỉ cấu hình **rollbackFor** khi thật sự phù hợp hợp đồng nghiệp vụ. Không nên mở transaction trong suốt quá trình export file/HTTP lâu chỉ để mong checked IOException tự rollback; có thể cần tách bước commit dữ liệu và bước xuất file.

### 8.2. Bắt rồi nuốt exception có thể khiến transaction commit

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public boolean unsafeReserve(CheckoutCommand command) {
    mongoTemplate.updateFirst(...);
    try {
        orderRepository.insert(...);
    } catch (RuntimeException ex) {
        log.warn("Order insert failed", ex);
        return false;
    }
    return true;
}
~~~

Đây là **phản ví dụ**. Nếu exception bị nuốt và không có cơ chế đánh dấu rollback, transaction interceptor có thể nhìn thấy lời gọi hoàn thành bình thường, rồi commit inventory update.

Một cách đúng hơn:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public OrderDocument reserve(...) {
    mongoTemplate.updateFirst(...);
    return orderRepository.insert(...); // Cho exception thoát ra.
}
~~~

Nếu muốn chuyển exception sang một business exception, hãy ném exception mới **thuộc RuntimeException** hoặc khai báo rollbackFor phù hợp:

~~~java
try {
    movementRepository.insert(movement);
} catch (org.springframework.dao.DataAccessException ex) {
    throw new InventoryWorkflowException(
        "Could not persist movement", ex);
}
~~~

Ở đây InventoryWorkflowException cần là **RuntimeException** do ứng dụng định nghĩa. Không bắt rồi trả thông báo lỗi bình thường ngay trong cùng transaction.

### 8.3. Đánh dấu rollback-only khi cần trả kết quả đặc biệt

Spring có API để đánh dấu transaction hiện tại **rollback-only** trong những trường hợp nâng cao:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

TransactionAspectSupport.currentTransactionStatus()
    .setRollbackOnly();
~~~

Tuy nhiên, cách này làm service phụ thuộc trực tiếp vào cơ chế transaction. Với lỗi nghiệp vụ cần hủy toàn bộ thao tác, **ném exception rõ ràng** thường dễ đọc và dễ kiểm thử hơn. Nếu tham gia transaction được mở ở nơi khác, rollback-only cũng có thể khiến caller gặp exception khi cố commit; phải thống nhất hợp đồng.

### 8.4. Commit cũng có thể lỗi

Method service đã tính xong và return object nội bộ **không đồng nghĩa caller chắc chắn nhận thành công**: transaction interceptor còn phải gọi commit.

Nếu commit gặp lỗi mạng hoặc failover, trạng thái kết quả có thể chưa rõ ràng. Không được mặc định mọi lỗi commit nghĩa là chắc chắn rollback; cần phân biệt **transaction thất bại chắc chắn** với **unknown commit result**.

## 9. Vì sao đặt @Transactional ở service, không tản mát ở repository?

Các repository method như insert/save có thể được transaction management bảo vệ theo cách riêng, nhưng khi service gọi nhiều lần:

~~~java
inventoryRepository.save(inventory);
orderRepository.insert(order);
movementRepository.insert(movement);
~~~

**Không được mặc định chúng tự cùng một transaction nhiều document** chỉ vì từng method có tính nguyên tử hoặc có annotation liên quan.

Đặt ranh giới ở service:

~~~java
@Service
public class CheckoutService {

    @Transactional(transactionManager = "mongoTransactionManager")
    public void placeOrder(...) {
        // Nhiều repository + MongoTemplate nằm trong cùng transaction.
    }
}
~~~

Nó tương ứng với **một đơn vị nghiệp vụ**: “giữ hàng và tạo order”.

### 9.1. Không đặt transaction quá rộng

Một service method không nên giữ transaction mở trong toàn bộ:

~~~text
Đọc giỏ hàng
-> gọi API giảm giá bên ngoài (2 giây)
-> chờ thanh toán ngân hàng (30 giây)
-> cập nhật MongoDB
-> gửi email (3 giây)
~~~

Transaction dài làm tăng thời gian giữ snapshot/session, có thể tăng contention và dễ chạm giới hạn transaction runtime.

Thay vào đó, chia thành các phase nghiệp vụ:

1. Xác thực và chuẩn bị dữ liệu ngoài transaction.
2. Mở transaction **ngắn** để reserve và ghi order/movement/outbox.
3. Commit.
4. Worker/outbox thực hiện gọi hệ thống ngoài.
5. Dùng transaction khác để đổi trạng thái dựa trên kết quả.

### 9.2. Không @Transactional cho mỗi controller method vì tiện

Controller có thể làm serialization, HTTP streaming và I/O lâu. Tầng service là nơi thích hợp hơn để giữ ranh giới nghiệp vụ ngắn, có thể tái sử dụng từ cả API, scheduler và message consumer.

## 10. Lỗi self-invocation và Spring proxy

Với cơ chế @Transactional dựa trên proxy, annotation chỉ phát huy tác dụng khi method được gọi **qua Spring-managed proxy**.

~~~java
@Service
public class CheckoutService {

    public void checkout(...) {
        reserveInTransaction(...); // Gọi nội bộ qua this.
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void reserveInTransaction(...) {
        // Có thể KHÔNG nhận transaction khi gọi từ checkout() cùng bean.
    }
}
~~~

Lời gọi từ **checkout → reserveInTransaction** trong cùng object thường không đi qua proxy transaction, nên annotation trên reserveInTransaction **không được áp dụng** ở lời gọi đó.

### 10.1. Tách service được proxy quản lý

~~~java
@Service
public class CheckoutFacade {

    private final ReservationService reservationService;

    public CheckoutFacade(ReservationService reservationService) {
        this.reservationService = reservationService;
    }

    public void checkout(...) {
        reservationService.reserve(...); // Đi qua bean khác.
    }
}

@Service
public class ReservationService {

    @Transactional(transactionManager = "mongoTransactionManager")
    public void reserve(...) {
        // Mongo operations trong transaction.
    }
}
~~~

Trong code thật, dùng các tham số/implementation cụ thể theo mô hình ứng dụng. Điểm chính là method có @Transactional phải được gọi qua proxy thích hợp.

### 10.2. Các tình huống proxy thường gặp

| Cách gọi | Rủi ro |
| --- | --- |
| new CheckoutService(...) trực tiếp | Object không qua Spring AOP proxy |
| this.reserve(...) cùng bean | Self-invocation bỏ qua interceptor |
| Method private | Không phù hợp cho proxy interception |
| Final class/method với class-based proxy | Có thể không được advice |
| Method static | Không phải đối tượng method call theo Spring proxy |
| Gọi MongoTemplate trên thread mới | Thread-bound session không tự truyền |
| Method @Transactional được gọi qua Spring bean/proxy | Hướng phù hợp khi cấu hình manager đúng |

Các chi tiết về visibility có thể khác theo cách proxy và phiên bản Spring. Để dễ kiểm soát, **ưu tiên public service method không final và được gọi qua một Spring bean khác**.

### 10.3. Không mở thread trong một transaction đồng bộ

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void unsafeWork() {
    orderRepository.insert(order);

    CompletableFuture.runAsync(() -> {
        movementRepository.insert(movement);
    });
}
~~~

**ClientSession của transaction đồng bộ được quản lý theo thread context**; tác vụ chạy trên executor khác không mặc nhiên tham gia session đó. Ngoài ra, transaction có thể commit trước khi CompletableFuture hoàn tất.

Nếu cần bất đồng bộ, hãy chuyển việc cần làm thành event/outbox sau commit hoặc thiết kế transaction reactive đúng cách, không tự chia transaction imperative sang nhiều thread.

## 11. Propagation: REQUIRED, REQUIRES_NEW và NESTED

Spring cho phép chỉ định propagation của declarative transaction. **Mặc định là REQUIRED**:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    propagation = Propagation.REQUIRED
)
public void reserve(...) {}
~~~

Với REQUIRED:

- Nếu caller chưa có transaction phù hợp, Spring mở một transaction mới.
- Nếu caller đang có transaction tương thích, method tham gia transaction hiện tại.

Điều này phù hợp khi muốn các method phụ của một business operation dùng chung transaction.

### 11.1. REQUIRES_NEW có thể làm sai ý định all-or-nothing

**REQUIRES_NEW** diễn đạt mong muốn có một transaction độc lập với transaction hiện tại. Ngay cả khi infrastructure hỗ trợ cách tạm dừng transaction hiện hành, việc commit transaction độc lập sẽ **phá vỡ giả định tất cả ghi cùng rollback**.

Ví dụ:

~~~text
Checkout transaction A:
  -> gọi audit method transaction B độc lập, B commit
  -> Checkout A thất bại và rollback

Kết quả: audit B có thể tồn tại dù Checkout A không commit
~~~

Mức hỗ trợ suspension/REQUIRES_NEW phụ thuộc transaction manager và tài nguyên. **Không mặc định mọi propagation mode của JDBC hoạt động giống hệt trên MongoTransactionManager.** Nếu dùng, phải xác minh phiên bản Spring, session binding và semantics thực tế.

### 11.2. NESTED không phải savepoint MongoDB

Đừng giả định MongoDB transaction hỗ trợ nested transactions với savepoint như một số database quan hệ.

~~~java
@Transactional(propagation = Propagation.NESTED)
public void nestedOperation() {
    // Không thể mặc nhiên rollback riêng đến một MongoDB savepoint.
}
~~~

Với MongoDB, cần kiểm tra giới hạn MongoTransactionManager và thiết kế lại luồng nghiệp vụ nếu phải hủy một phần. **Không dựa vào @Transactional(NESTED) để thực hiện giao dịch con độc lập trong một session**.

### 11.3. Mỗi method không cần một transaction riêng

Nếu một service @Transactional gọi ba repository, Spring không cần mở ba transaction. Trong mô hình chuẩn, các thao tác cùng tham gia ranh giới do service mở, giúp commit/rollback thống nhất.

## 12. Read-only, read concern, write concern và read preference

Transaction xác định **một đơn vị commit**, nhưng mức nhất quán/độ bền còn phụ thuộc **transaction options** và cấu hình MongoDB.

| Khái niệm | Vai trò |
| --- | --- |
| readConcern | Mức nhất quán dữ liệu được đọc trong transaction |
| writeConcern | Mức xác nhận và độ bền của commit |
| readPreference | Chọn nơi đọc theo hạn chế của transaction |
| maxCommitTime | Giới hạn liên quan đến quá trình commit nếu được cấu hình |
| transactionLifetimeLimitSeconds | Giới hạn thời gian sống transaction ở server |

Một thiết kế yêu cầu snapshot/majority durability cần chọn chính sách phù hợp với topology và tài liệu MongoDB Server. **Không mặc định chỉ vì có @Transactional thì mọi đọc ngoài transaction ngay lập tức thấy dữ liệu ở tất cả replica hoặc đã có majority durability.**

### 12.1. readOnly không biến MongoDB thành cache

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    readOnly = true
)
public Report readReport(...) {
    // Những truy vấn MongoDB đồng bộ.
}
~~~

**readOnly=true** là metadata/ý định của transaction Spring và có thể ảnh hưởng việc bắt đầu hoặc tham gia session/transaction theo integration cụ thể. Không suy rằng nó luôn chỉ là một hint vô hại hoặc mặc định cho phép đọc trên secondary trong một MongoDB transaction.

Tránh giữ read-only transaction mở trong một report streaming dài nếu không cần snapshot. Cân nhắc read concern và giới hạn report phù hợp.

### 12.2. Đừng tự tin rằng write concern mặc định đủ cho mọi use case

Nếu ứng dụng cần độ bền quan trọng, hãy thiết kế write concern theo chính sách deployment, kiểm tra failover và cách xác định kết quả commit. Spring Data cho phép cấu hình transaction options phù hợp; cần đồng bộ lựa chọn với MongoDB Server và yêu cầu nghiệp vụ.

### 12.3. Đọc bên ngoài transaction không là một phần của snapshot

Nếu một bước đọc từ raw MongoClient khác session rồi dựa trên dữ liệu đó để ghi ở transaction hiện tại, dữ liệu đọc có thể không nằm trong cùng snapshot. Tương tự, gọi Redis hoặc service HTTP không tham gia MongoDB session.

## 13. Cạnh tranh đồng thời vẫn có thể gây write conflict

Hai transaction cùng cố cập nhật một inventory document:

~~~text
Transaction A: đọc/sửa inventory X
Transaction B: đọc/sửa inventory X
Transaction A: commit
Transaction B: có thể nhận write conflict hoặc transient transaction error
~~~

Transaction không có nghĩa mọi concurrent request sẽ tự chờ, rồi luôn thành công. MongoDB có thể yêu cầu abort/retry khi phát hiện xung đột.

### 13.1. Có cần điều kiện available >= quantity trong transaction không?

**Có.** Điều kiện:

~~~java
Criteria.where("_id").is(inventoryId)
    .and("tenantId").is(tenantId)
    .and("available").gte(quantity);
~~~

và cập nhật:

~~~java
new Update()
    .inc("available", -quantity)
    .inc("reserved", quantity);
~~~

vẫn là cách trực tiếp giữ bất biến tồn kho. Khi transaction bị hủy do conflict, các ghi trong transaction không commit; một lần thử lại phải tính toán và kiểm tra điều kiện mới.

### 13.2. Không tự chuyển write conflict thành “hết hàng”

Một write conflict khác với **modifiedCount=0** do không đủ hàng:

- **modifiedCount=0:** không có document khớp điều kiện tại thời điểm thao tác trong transaction.
- **write conflict / transient transaction error:** transaction không thể hoàn tất theo trạng thái hiện tại, có thể thử lại phù hợp.

Nếu business API cần chính xác, không bắt mọi DataAccessException rồi trả một lỗi “out of stock”. Phải phân biệt lỗi nghiệp vụ và lỗi điều phối transaction.

### 13.3. Retry phải bắt đầu ngoài transaction bị hỏng

Một transaction đã abort hoặc bị đánh dấu rollback-only không thể được “sửa” chỉ bằng việc gọi lại update bên trong cùng context rồi cố commit. Với transient transaction error, cần **bắt đầu một transaction mới**, lặp lại những bước cần thiết và đánh giá lại dữ liệu.

Không đặt vòng while retry vô hạn trong service @Transactional:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void unsafeRetryInsideTransaction() {
    for (;;) {
        try {
            updateInventory();
            return;
        } catch (RuntimeException error) {
            // Vẫn ở transaction đã gặp lỗi; nguy cơ vòng lặp vô hạn.
        }
    }
}
~~~

Retry phải có **giới hạn số lần, backoff, phân loại lỗi, định danh request và telemetry**. Với giao dịch chịu tải cao, nên đo contention thay vì chỉ tăng số lần retry.

## 14. UnknownTransactionCommitResult và idempotency

Có tình huống server đã commit nhưng response commit bị mất do mạng/failover. Khi đó caller có thể gặp trạng thái **không chắc chắn kết quả commit**.

MongoDB driver/server có các nhãn lỗi transaction như:

- **TransientTransactionError**: một lỗi có thể khiến toàn bộ transaction phải thử lại.
- **UnknownTransactionCommitResult**: kết quả của thao tác commit chưa được xác định chắc chắn từ phía caller.

Nhãn lỗi, retry behavior và exception được Spring chuyển đổi tùy phiên bản driver/Spring Data; không so sánh mọi exception chỉ bằng thông báo string.

### 14.1. Không đồng nhất hai loại retry

| Tình huống | Hướng xử lý |
| --- | --- |
| Transaction chắc chắn abort do conflict | Có thể retry **toàn bộ transaction** từ đầu |
| Commit result chưa rõ | Theo cơ chế driver/API, có thể retry **commit** phù hợp hoặc đối soát theo business key |
| Quantity không đủ | Không retry vô hạn như lỗi hạ tầng |
| requestId trùng, payload giống | Trả kết quả đã ghi nhận, không trừ lại |
| requestId trùng, payload khác | Báo conflict, không lặng lẽ dùng lại |

Spring Data có đường mở rộng MongoTransactionManager khi cần tùy biến commit/retry; các cơ chế nâng cao phải dựa trên transaction labels và tài liệu chính thức của MongoDB driver.

### 14.2. Business idempotency không được bỏ qua

Ngay cả khi driver tự xử lý retry kỹ thuật, **HTTP request được client gửi lại** vẫn có thể là một transaction mới. Sử dụng **unique (tenantId, requestId)** và lưu payload định danh để truy xuất kết quả sau khi commit.

**Đừng chỉ bắt DuplicateKeyException rồi coi mặc định là thành công**: cần tra cứu order hiện có, so sánh inventoryId/quantity/tenant và trạng thái.

### 14.3. Đọc lại sau lỗi commit cần session mới/phù hợp

Sau khi transaction thất bại hoặc commit chưa rõ, tránh tái sử dụng một context đã rollback-only để truy vấn xác nhận. Nên thoát ranh giới transaction lỗi và thực hiện reconciliation/idempotency lookup trong giao dịch hoặc lần đọc độc lập phù hợp.

## 15. TransactionTemplate: ranh giới tường minh khi cần

Không phải mọi workflow đều dễ trình bày bằng annotation. Spring cung cấp **TransactionTemplate** với PlatformTransactionManager:

~~~java
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public OrderDocument reserveWithTemplate(
        MongoTransactionManager mongoTransactionManager,
        CheckoutCommand command) {

    TransactionTemplate tx =
        new TransactionTemplate(mongoTransactionManager);

    return tx.execute(status -> {
        // Ví dụ: update inventory, insert order, insert movement
        // thông qua các bean Spring Data cùng MongoDatabaseFactory.
        return doReserveSteps(command);
    });
}
~~~

**doReserveSteps** là hàm nghiệp vụ minh họa cần được triển khai, không phải API dựng sẵn của Spring. TransactionTemplate mở/đóng ranh giới đồng bộ quanh callback, giúp nhìn thấy điểm bắt đầu/kết thúc ngay trong mã.

### 15.1. Khi nào nên dùng?

- Một job cần transaction boundary tường minh.
- Một lớp điều phối retry muốn mở **transaction mới cho mỗi attempt**.
- Tách bước MongoDB ngắn khỏi thao tác I/O dài.
- Kiểm thử rollback độc lập.

Không dùng TransactionTemplate bên trong @Transactional chỉ vì “thêm một lớp an toàn” nếu chưa hiểu propagation: mặc định callback có thể tham gia transaction đã có, không tạo một transaction hoàn toàn khác.

### 15.2. Không bao transaction quanh API gọi ra ngoài

~~~java
// Không nên giữ Mongo transaction mở trong lúc gọi payment gateway.
tx.execute(status -> {
    reserveInventory();
    paymentGateway.charge(...); // External HTTP, không thuộc Mongo transaction.
    return saveOrder();
});
~~~

Nếu payment gateway đã thu tiền rồi MongoDB rollback, transaction MongoDB **không hoàn tiền tự động**. Tách các pha bằng reservation/outbox/saga và có khả năng xử lý phát lại, trạng thái chưa rõ, compensation.

## 16. Outbox: gửi sự kiện sau commit mà không mất dấu

Giả sử checkout cần thông báo cho hệ thống fulfillment khi order được giữ thành công. Không nên gọi message broker trực tiếp rồi hy vọng việc đó được rollback cùng MongoDB:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void unsafeCheckout(...) {
    reserveInventory();
    orderRepository.insert(order);
    messageBroker.send("order-reserved", payload);
    movementRepository.insert(movement);
}
~~~

Nếu messageBroker.send đã thành công nhưng movement insert lỗi, **MongoDB rollback**, còn message bên ngoài có thể đã tới consumer. Consumer sẽ nhận thông báo của một order không được commit.

### 16.1. Transactional outbox trong MongoDB

Thay vì gửi ngay, thêm một document vào **outbox_events** trong cùng MongoDB transaction:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439014"),
  tenantId: "shop-a",
  eventId: "event-checkout-123",
  eventType: "OrderReserved",
  aggregateId: "checkout-123",
  status: "PENDING",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Giao dịch gồm:

~~~text
MongoDB transaction:
    update inventory
    insert order
    insert movement
    insert outbox event
commit tất cả
~~~

Sau commit, một worker đọc outbox và gửi tới broker. Nếu process crash trước khi gửi, outbox vẫn còn để retry.

### 16.2. Outbox không tự đem lại exactly-once ở broker

Worker có thể gửi event thành công nhưng crash trước khi đánh dấu outbox SENT. Lần sau có thể gửi lại.

Vì vậy, consumer cần **idempotency theo eventId**; hệ thống không được coi “outbox” có nghĩa mọi downstream side effect chắc chắn xảy ra đúng một lần.

### 16.3. @TransactionalEventListener AFTER_COMMIT có đủ không?

Spring có cơ chế listener sau commit phù hợp cho một số side effect đơn giản. Tuy nhiên, nếu tiến trình chết **sau commit trước lúc listener gửi message**, sự kiện có thể mất nếu chưa được lưu bền vững.

Với workflow quan trọng cần không mất sự kiện, **outbox lưu cùng transaction** mạnh hơn việc chỉ chạy callback sau commit.

## 17. Lưu ý khi gọi nhiều repository cùng transaction

Spring Data repositories cùng MongoDatabaseFactory được cấu hình đúng có thể tham gia transaction do MongoTransactionManager quản lý. Nhưng cần tránh một số giả định:

### 17.1. Repository interface khác nhau vẫn cùng transaction

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void process(...) {
    orderRepository.insert(order);
    movementRepository.insert(movement);
    mongoTemplate.updateFirst(
        inventoryFilter, inventoryUpdate, InventoryDocument.class
    );
}
~~~

Không cần ba transaction riêng theo số repository. Điều quan trọng là chúng dùng cùng session/transaction context và không có thành phần nào tự tạo kết nối khác.

### 17.2. Repository method có @Transactional riêng thì sao?

Nếu một repository method được gọi từ service transaction với **REQUIRED**, nó có thể tham gia transaction đang tồn tại. Nhưng nếu cấu hình repository dùng transaction manager khác, propagation khác hoặc một MongoClient khác, kết quả có thể không như mong muốn.

Tránh “thử theo cảm giác”. Kiểm tra Spring bean wiring và có integration test chứng minh tất cả collection cùng rollback.

### 17.3. Raw driver trực tiếp

~~~java
mongoTemplate.getCollection("orders")
    .insertOne(rawDocument);
~~~

Truy cập raw collection qua MongoTemplate không đồng nghĩa mọi thao tác driver bạn thực hiện sẽ luôn mang session đã được Spring binding. Với raw MongoDB driver, các overload nhận **ClientSession** có thể cần được sử dụng tường minh; nên ưu tiên API MongoTemplate/repository được Spring tích hợp khi muốn transaction declarative.

Nếu bắt buộc dùng raw driver, hãy kiểm chứng cách lấy/reuse session từ Spring Data hoặc thiết kế session programmatic đúng tài liệu, thay vì tin rằng mọi lệnh raw insert tự đi cùng transaction.

### 17.4. Repository.save và read-modify-write

Transaction không loại bỏ nhu cầu kiểm tra business invariant. Hai transaction concurrent cùng đọc snapshot và save entity có thể phát sinh conflict; ứng dụng vẫn cần xử lý retry hoặc optimistic locking khi phù hợp.

Với inventory, dùng **conditional $inc** thay vì đọc stock cũ rồi save là cách diễn đạt bất biến rõ ràng ngay tại MongoDB.

## 18. Transaction và các lệnh aggregation, count, index

Không phải mọi MongoDB command hoặc aggregation stage được phép chạy trong transaction với mọi phiên bản server.

### 18.1. Aggregation trong transaction

Có thể thực hiện một số aggregation read trong transaction khi MongoDB cho phép, nhưng cần chú ý:

- Read preference và read concern của transaction.
- Các stage bị hạn chế trong transaction.
- Thời gian chạy dài giữ transaction/session lâu.
- Các stage ghi kết quả như **$out** hoặc **$merge** có giới hạn khi dùng trong transaction.

Với báo cáo lớn cần aggregation nặng, không mặc định đặt @Transactional quanh toàn bộ report; cân nhắc snapshot/cutoff hoặc xử lý ngoài transaction phù hợp.

### 18.2. Count trong transaction

MongoDB có những giới hạn với lệnh count truyền thống trong transaction. Spring Data MongoDB sử dụng các cách phù hợp hơn (như aggregation có $match/$count trong các trường hợp tương ứng) ở những phiên bản hỗ trợ.

**Không tự gọi raw count command bên trong transaction rồi suy rằng mọi server version đều chấp nhận.** Dùng API Spring Data đang có và viết integration test trong môi trường triển khai.

### 18.3. Tạo collection/index trước khi checkout

Tạo index là hoạt động quản trị schema, không phải một bước thường trực của mỗi checkout.

~~~java
// Không nên ở giữa phương thức đặt hàng:
mongoTemplate.indexOps(OrderDocument.class)
    .ensureIndex(...);
~~~

Việc tạo collection/index trong transaction có các hạn chế theo MongoDB Server, topology và version. **Hãy provision collection và unique index qua migration trước khi nhận traffic checkout**. Đây cũng là điều kiện để cơ chế idempotency có hiệu lực đúng thời điểm.

### 18.4. Không giữ transaction khi đang stream lâu

Nếu method @Transactional trả một Java Stream để caller duyệt **sau khi method kết thúc**, transaction có thể đã commit/rollback và session có thể không còn hợp lệ.

Không trả một resource gắn cursor ra khỏi transaction scope mà không quản lý lifecycle. Với những export dài, nên thiết kế riêng, thường không giữ một transaction nghiệp vụ mở trong suốt quá trình xuất file.

## 19. Reactive: transaction dùng Reactor Context, không phải ThreadLocal

Trong stack ReactiveMongoRepository/ReactiveMongoTemplate, Spring Data cung cấp **ReactiveMongoTransactionManager**. Nó dùng cơ chế transaction context reactive thay vì phụ thuộc hoàn toàn vào ThreadLocal của imperative stack.

### 19.1. Cấu hình manager reactive

~~~java
package com.example.checkout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class ReactiveMongoTransactionConfiguration {

    @Bean("reactiveMongoTransactionManager")
    public ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory databaseFactory) {
        return new ReactiveMongoTransactionManager(databaseFactory);
    }
}
~~~

Đây là **cấu hình thay thế cho reactive stack**; nếu ứng dụng có cả imperative và reactive, hãy kiểm soát manager được chọn ở từng phương thức. Không giả định một MongoTransactionManager đồng bộ tự điều phối ReactiveMongoTemplate.

### 19.2. Reactive repositories

~~~java
package com.example.checkout;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {

    Mono<OrderDocument> findByTenantIdAndRequestId(
        String tenantId, String requestId
    );
}

public interface ReactiveMovementRepository
        extends ReactiveMongoRepository<InventoryMovementDocument, ObjectId> {
}
~~~

### 19.3. Reactive service: compose, không tự subscribe

~~~java
package com.example.checkout;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCheckoutService {

    private final ReactiveMongoTemplate template;
    private final ReactiveOrderRepository orders;
    private final ReactiveMovementRepository movements;

    public ReactiveCheckoutService(
            ReactiveMongoTemplate template,
            ReactiveOrderRepository orders,
            ReactiveMovementRepository movements) {
        this.template = template;
        this.orders = orders;
        this.movements = movements;
    }

    @Transactional(
        transactionManager = "reactiveMongoTransactionManager"
    )
    public Mono<OrderDocument> reserve(
            String authenticatedTenantId,
            CheckoutCommand command) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || command == null
                || command.inventoryId() == null
                || command.requestId() == null
                || command.requestId().isBlank()
                || command.quantity() <= 0) {
            return Mono.error(
                new IllegalArgumentException("Invalid request"));
        }

        Query filter = Query.query(
            Criteria.where("_id").is(command.inventoryId())
                .and("tenantId").is(authenticatedTenantId)
                .and("available").gte(command.quantity())
        );

        Update change = new Update()
            .inc("available", -command.quantity())
            .inc("reserved", command.quantity());

        return template.updateFirst(
            filter, change, InventoryDocument.class
        ).flatMap(result -> {

            if (!result.wasAcknowledged()) {
                return Mono.error(
                    new IllegalStateException(
                        "Inventory write not acknowledged"));
            }
            if (result.getModifiedCount() != 1) {
                return Mono.error(new OutOfStockException());
            }

            Instant now = Instant.now();
            OrderDocument order = new OrderDocument(
                new ObjectId(), authenticatedTenantId,
                command.requestId(), command.inventoryId(),
                command.quantity(), "RESERVED", now);

            InventoryMovementDocument movement =
                new InventoryMovementDocument(
                    new ObjectId(), authenticatedTenantId,
                    command.requestId(), command.inventoryId(),
                    command.quantity(), "RESERVE", now);

            return orders.insert(order)
                .flatMap(saved ->
                    movements.insert(movement)
                        .thenReturn(saved)
                );
        });
    }
}
~~~

Tương tự các ví dụ trước, đặt mỗi public type vào file riêng. Biến thể reactive minh họa thành công/rollback khi có lỗi, **chưa xử lý idempotency retry hoàn chỉnh** như logic lookup existing ở service đồng bộ. Cần bổ sung trong hệ thống thật khi request có thể gửi lại.

### 19.4. Vì sao phải trả Mono?

Reactive transaction interceptor gắn transaction context với publisher được trả về. Khi có subscription, các thao tác được compose trong chain có thể tham gia cùng reactive transaction.

**Không tự subscribe bên trong service**:

~~~java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager"
)
public Mono<OrderDocument> unsafeReserve(...) {
    template.updateFirst(filter, update, InventoryDocument.class)
        .subscribe(); // Tự tách subscription, có thể nằm ngoài context mong muốn.

    return orders.insert(order);
}
~~~

Thao tác cập nhật trên subscription tự tạo có thể không nằm trong cùng reactive transaction với Mono được trả ra. Hơn nữa, lời gọi có thể chạy đua với việc insert và commit.

### 19.5. Không block hoặc trộn stack tùy tiện

~~~java
// Không nên trong reactive service/controller:
reactiveCheckoutService.reserve(tenant, command).block();
~~~

Blocking trên event loop là sai về mô hình reactive. Ngoài ra, **MongoTemplate đồng bộ không tự tham gia reactive transaction của ReactiveMongoTransactionManager**.

Nếu ứng dụng cần cả imperative và reactive, nên xác định rõ ranh giới và sử dụng đúng transaction manager thay vì hy vọng hai context được tự động hợp nhất.

## 20. TransactionalOperator trong reactive stack

Ngoài annotation, Spring có **TransactionalOperator** để thiết lập transaction trên publisher:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import reactor.core.publisher.Mono;

TransactionalOperator operator =
    TransactionalOperator.create(reactiveMongoTransactionManager);

Mono<OrderDocument> result = reservePipeline(command)
    .as(operator::transactional);
~~~

**reservePipeline** là hàm ví dụ trả Mono gồm những thao tác reactive đã compose, và reactiveMongoTransactionManager phải được inject từ cấu hình. Không coi đây là hàm dựng sẵn của Spring.

### 20.1. Dùng khi nào?

- Cần ranh giới transaction cho một đoạn pipeline thay vì toàn bộ method.
- Muốn chủ động compose các operation với Reactor.
- Có một service reactive mà annotation dễ bị self-invocation hoặc không rõ boundary.

### 20.2. Không kéo dài transaction qua Flux vô hạn

Nếu áp transaction cho một Flux vô hạn hoặc kéo dài hàng giờ, transaction có thể không đạt đến tín hiệu hoàn tất để commit và có thể vượt giới hạn server.

Giữ transaction **ngắn và hữu hạn**, phù hợp một đơn vị nghiệp vụ; không áp transaction lên change stream hoặc HTTP streaming output vô hạn.

### 20.3. Cancellation là một tình huống cần kiểm thử

Publisher có thể bị hủy bởi client. Cơ chế transaction reactive xử lý cancel theo ngữ nghĩa của Spring/Reactor/version hiện hành; **đừng thiết kế checkout dựa trên việc client giữ subscription đến cuối mà không có idempotency và truy xuất trạng thái bền vững**.

Một request có thể đã gửi thao tác tới server trước khi kết nối bị hủy. Phải có requestId để đối soát trạng thái.

## 21. Kiểm thử transaction bằng replica set và Testcontainers

**Chỉ nhìn thấy @Transactional trong source code không chứng minh transaction hoạt động.** Cần một integration test dùng MongoDB topology hỗ trợ transaction.

Một lựa chọn là **Testcontainers MongoDBContainer** với replica set được thiết lập cho test.

### 21.1. Khởi tạo MongoDB test

~~~java
package com.example.checkout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class CheckoutTransactionIntegrationTest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
    }

    @Autowired CheckoutService checkout;
    @Autowired MongoTemplate template;
    @Autowired OrderRepository orders;
    @Autowired InventoryMovementRepository movements;

    // Các test và index setup ở phần tiếp theo.
}
~~~

Ví dụ giả định dự án đã có **Spring Boot application**, dependency spring-boot-starter-data-mongodb, testcontainers-mongodb, testcontainers-junit-jupiter, JUnit 5 và môi trường Docker dành cho test. Các import MongoTemplate, Repository và phần code tiếp theo được thêm vào cùng class.

**MongoDBContainer** cung cấp replica set theo cơ chế được Testcontainers hỗ trợ; kiểm tra API với phiên bản Testcontainers thực tế, vì cách cấu hình container có thể thay đổi giữa các phiên bản.

### 21.2. Tạo collection/index trước transaction

Trong môi trường test, nên tạo các unique index cần thiết trước khi service bắt đầu checkout:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

@BeforeEach
void ensureIndexes() {
    template.indexOps(OrderDocument.class).ensureIndex(
        new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("requestId", Sort.Direction.ASC)
            .unique()
            .named("uk_orders_tenant_request")
    );

    template.indexOps(InventoryMovementDocument.class).ensureIndex(
        new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("requestId", Sort.Direction.ASC)
            .unique()
            .named("uk_movements_tenant_request")
    );
}
~~~

Nếu MongoDB Server/index metadata đã tồn tại với option khác, ensureIndex có thể báo conflict. Trong test instance cô lập, tạo index theo schema mong muốn và không thay đổi định nghĩa giữa các test.

**Không đặt @Transactional trên từng test method chỉ vì service có annotation.** Test-managed transaction bao quanh method kiểm thử có thể che đi việc transaction service thật sự commit/rollback và thay đổi ngữ nghĩa kiểm chứng.

## 22. Integration test: commit đồng bộ ba collection

Thêm test sau vào CheckoutTransactionIntegrationTest. Khi dùng trong một source file thật, bổ sung các import tương ứng.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@Test
void commitsInventoryOrderAndMovementTogether() {
    String tenant = "TEST-" + UUID.randomUUID();
    String requestId = "checkout-" + UUID.randomUUID();
    ObjectId inventoryId = new ObjectId();

    template.insert(new InventoryDocument(
        inventoryId, tenant, "BOOK-101", 5L, 0L
    ));

    try {
        OrderDocument saved = checkout.reserve(
            tenant,
            new CheckoutCommand(inventoryId, requestId, 2L)
        );

        InventoryDocument after = template.findById(
            inventoryId, InventoryDocument.class
        );

        assertThat(after).isNotNull();
        assertThat(after.available()).isEqualTo(3L);
        assertThat(after.reserved()).isEqualTo(2L);

        assertThat(saved.status()).isEqualTo("RESERVED");
        assertThat(
            orders.findByTenantIdAndRequestId(tenant, requestId)
        ).isPresent();

        long movementCount = template.count(
            Query.query(
                Criteria.where("tenantId").is(tenant)
                    .and("requestId").is(requestId)
            ),
            InventoryMovementDocument.class
        );

        assertThat(movementCount).isEqualTo(1L);
    } finally {
        cleanupTenantAndInventory(tenant, inventoryId);
    }
}
~~~

Phương thức dọn test:

~~~java
private void cleanupTenantAndInventory(
        String tenant, ObjectId inventoryId) {

    template.remove(
        Query.query(Criteria.where("tenantId").is(tenant)),
        OrderDocument.class
    );
    template.remove(
        Query.query(Criteria.where("tenantId").is(tenant)),
        InventoryMovementDocument.class
    );
    template.remove(
        Query.query(Criteria.where("_id").is(inventoryId)),
        InventoryDocument.class
    );
}
~~~

Lệnh cleanup chạy **ngoài service transaction** và chỉ dùng tenant test được tạo ngẫu nhiên. Chỉ chạy trên database test dành riêng, không áp dụng logic xóa theo tenant tùy ý lên production.

### 22.1. Test chứng minh điều gì?

Với inventory ban đầu available=5, reserved=0, khi checkout reserve quantity=2 thành công:

~~~text
inventories: available=3, reserved=2
orders: một order có requestId tương ứng
inventory_movements: một movement RESERVE
~~~

Nhưng test thành công **chưa đủ để chứng minh rollback**. Ba lần ghi độc lập cũng có thể đều thành công. Cần kiểm thử một lỗi phát sinh **sau khi ít nhất hai lần ghi trước đã diễn ra**.

## 23. Integration test: lỗi ghi cuối cùng phải rollback bước đầu

Để tạo lỗi có thể dự đoán tại bước **insert movement**, test seed một movement có cùng unique key tenantId+requestId. Khi service thử tạo movement thứ hai, MongoDB sẽ từ chối do unique index.

Phương thức service ở phần 7 chạy thứ tự:

~~~text
1. update inventory
2. insert order
3. insert movement -> duplicate key error
4. transaction abort
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@Test
void rollsBackAllWritesWhenLastRepositoryInsertFails() {
    String tenant = "TEST-" + UUID.randomUUID();
    String requestId = "checkout-" + UUID.randomUUID();
    ObjectId inventoryId = new ObjectId();

    template.insert(new InventoryDocument(
        inventoryId, tenant, "BOOK-101", 5L, 0L
    ));

    // Ghi fixture bên ngoài checkout transaction.
    movements.insert(new InventoryMovementDocument(
        new ObjectId(), tenant, requestId, inventoryId,
        2L, "RESERVE", Instant.now()
    ));

    try {
        assertThatThrownBy(() -> checkout.reserve(
            tenant,
            new CheckoutCommand(inventoryId, requestId, 2L)
        )).isInstanceOf(RuntimeException.class);

        InventoryDocument after = template.findById(
            inventoryId, InventoryDocument.class
        );

        assertThat(after).isNotNull();
        assertThat(after.available()).isEqualTo(5L);
        assertThat(after.reserved()).isEqualTo(0L);

        assertThat(
            orders.findByTenantIdAndRequestId(tenant, requestId)
        ).isEmpty();

        long movementCount = template.count(
            Query.query(
                Criteria.where("tenantId").is(tenant)
                    .and("requestId").is(requestId)
            ),
            InventoryMovementDocument.class
        );
        assertThat(movementCount).isEqualTo(1L);
    } finally {
        cleanupTenantAndInventory(tenant, inventoryId);
    }
}
~~~

**Điểm kiểm chứng:** movement được seed trước test vẫn tồn tại (count=1), nhưng inventory update và order insert của transaction lỗi **không** commit. Nếu sau lỗi stock còn 3 hoặc order vẫn tồn tại, cần nghi ngờ transaction chưa được áp dụng hoặc có thao tác ghi chạy ngoài session.

### 23.1. Vì sao test phải có unique index trước?

Nếu không có unique index trên **(tenantId, requestId)** của inventory_movements, insert thứ hai có thể thành công, và transaction không có lỗi nào để rollback. Khi đó test vô tình trở thành success test.

### 23.2. Assertion exception

Ví dụ dùng RuntimeException làm assertion rộng để tập trung vào kiểm tra rollback. Trong dự án thật, nên assert exception được Spring chuyển đổi (như DuplicateKeyException hoặc dạng DataAccessException phù hợp) khi thư viện/driver đã cố định.

Không dựa vào message lỗi text, vì thông báo có thể thay đổi giữa phiên bản MongoDB Server và driver.

### 23.3. Test không có @Transactional trên method test

Nếu method test tự mở transaction, service reserve có thể chỉ **tham gia transaction của test**, làm cho kết quả được kiểm tra trước commit hoặc rollback không phản ánh đúng điều kiện sản xuất.

Test ở đây chủ động gọi service qua Spring bean, để annotation của service quyết định ranh giới.

### 23.4. Kiểm thử thêm không đủ hàng

Chèn inventory available=1 và gọi reserve quantity=2:

~~~java
assertThatThrownBy(() -> checkout.reserve(
    tenant, new CheckoutCommand(inventoryId, requestId, 2L)
)).isInstanceOf(OutOfStockException.class);
~~~

Sau exception, inventory phải còn available=1, reserved=0 và không có order/movement mới. Điều này chứng minh business guard vẫn có hiệu lực trong transaction.

## 24. Kiểm thử khi hai checkout cùng tranh tồn kho

Transaction giúp rollback tập nhiều ghi, nhưng **không đảm bảo mọi concurrent transaction đều thành công**.

Với inventory available=1 và hai request khác nhau cùng quantity=1:

| Kết quả khả thi | Diễn giải |
| --- | --- |
| Một transaction commit, một transaction không còn hàng | Guard available>=1 từ chối request sau |
| Một transaction commit, một transaction gặp write conflict | Conflict cần được phân loại và có thể thử transaction mới |
| Transaction thất bại do lỗi hạ tầng | Cần retry/reconciliation theo chính sách |

Trong test concurrency:

1. Tạo inventory available=1.
2. Dùng hai thread gọi hai requestId khác nhau qua Spring proxy.
3. Chờ cả hai kết thúc, phân loại result/exception.
4. Assert **số order RESERVED được commit không vượt quá 1**.
5. Assert inventory available không âm.
6. Nếu có order RESERVED, kiểm tra movement tương ứng và reserved counter.

**Không assert cứng mọi thất bại đều là OutOfStockException** khi hai MongoDB transactions chạy đồng thời; MongoDB có thể báo write conflict cần retry.

### 24.1. Retry có thể thay đổi kết quả

Nếu ứng dụng retry toàn bộ transaction sau transient conflict, request chưa có kết quả có thể thấy available mới bằng 0 và trở thành business out-of-stock.

Điều này đúng hơn là coi conflict là “đã hết hàng” ngay từ lần đầu. Nhưng retry cần giới hạn thời gian/lần thử và không tạo side effects ngoài MongoDB không idempotent.

### 24.2. Không đo hiệu năng bằng test chạy tuần tự

Một test chỉ gọi service hai lần liên tiếp không tạo contention. Dùng CountDownLatch/ExecutorService và transaction service thực, đồng thời đo behavior của MongoDB test instance.

## 25. Bảng chẩn đoán: @Transactional có mà dữ liệu vẫn ghi dở

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Lỗi cuối nhưng inventory vẫn giảm | Transaction chưa bật, self-invocation, thao tác ngoài session | Kiểm tra proxy/manager/factory và rollback test |
| Transaction báo không hỗ trợ topology | MongoDB standalone | Dùng replica set/sharded deployment hỗ trợ |
| Có hai manager và chọn nhầm | JDBC/JPA manager được chọn thay Mongo | Chỉ định transactionManager chính xác |
| Method có annotation nhưng không rollback | Gọi bằng this hoặc new thay vì Spring proxy | Tách service hoặc gọi qua bean proxy |
| Lỗi được log rồi service return bình thường | Exception bị nuốt | Ném exception hoặc đánh dấu rollback-only |
| IOException vẫn commit | Checked exception không thuộc rollback rule | rollbackFor phù hợp |
| Repository A rollback, raw driver B không rollback | Session/connection không được chia sẻ | Dùng Spring Data APIs cùng factory/session |
| CompletableFuture insert vẫn tồn tại sau rollback | Thread mới không tham gia transaction đồng bộ | Không tách operation ra async thread |
| Có order nhưng thiếu movement | Một method dùng manager khác hoặc operation ở ngoài transaction | Kiểm tra wiring + integration test |
| Client timeout rồi retry có hai order | Không có idempotency hoặc unique request ID | Unique key, payload check, reconcile |
| Commit response bị mất | Unknown commit result | Đối soát requestId, retry commit theo contract |
| Transaction bị write conflict | Nhiều writer tranh document | Retry toàn bộ txn có giới hạn |
| Transaction chạy quá lâu | HTTP ngoài, aggregation nặng, export dài | Giảm phạm vi transaction |
| Transaction tự tạo index lỗi | DDL/index trong workflow | Provision schema trước |
| @Transactional trong WebFlux không như mong muốn | Dùng imperative manager hoặc block/subscribe riêng | ReactiveMongoTransactionManager + publisher chain |
| @Transactional(readOnly=true) vẫn tạo session/tx | Hiểu sai readOnly | Kiểm tra semantics integration và use case |
| Test “pass” mà không chứng minh rollback | Chỉ test commit hoặc test method cũng có transaction | Tạo failure injection sau hai ghi và assert DB state |

### 25.1. Quy trình điều tra nhanh

1. Xác minh bean service được Spring tạo và method @Transactional được gọi qua proxy.
2. Xác nhận transactionManager được chọn là MongoTransactionManager.
3. Kiểm tra topology MongoDB hỗ trợ transaction.
4. Xác minh MongoTemplate và repositories dùng cùng MongoDatabaseFactory/session context.
5. Kiểm tra có catch nuốt exception hoặc rollback rule không phù hợp không.
6. Kiểm tra có CompletableFuture, @Async, raw driver hoặc HTTP call nằm giữa transaction không.
7. Tái hiện rollback trong test replica set bằng lỗi ở lần ghi thứ ba.
8. Kiểm tra unique indexes cần thiết đã tạo trước checkout.
9. Phân loại write conflict và commit result chưa rõ, không retry vô hạn.
10. Sau khi đúng về mặt dữ liệu mới tối ưu hiệu năng và mức chịu tải.

## 26. Hiệu năng, contention và phạm vi transaction

Transaction nhiều document là công cụ tính đúng đắn, **không miễn phí**:

- Cần quản lý session và snapshot/transaction state.
- Có thể tăng contention hoặc write conflict.
- Transaction dài tăng chi phí tài nguyên và nguy cơ vượt giới hạn.
- Ghi trên nhiều collection vẫn có chi phí index, network và disk.
- Commit và durability policy có thể làm thay đổi độ trễ.

### 26.1. Giữ transaction ngắn

~~~text
Không nên:
@Transactional
  -> gọi external API
  -> sleep/retry ở client
  -> query aggregation toàn lịch sử
  -> update inventory
  -> ghi order

Nên:
Chuẩn bị input/authorization trước
@Transactional
  -> conditional update inventory
  -> insert order
  -> insert movement/outbox
commit
Worker xử lý external API sau
~~~

Một transaction nghiệp vụ ngắn dễ quan sát, dễ retry và giảm thời gian giữ tài nguyên hơn transaction bọc toàn bộ checkout HTTP.

### 26.2. Index phục vụ lookup

Trong ví dụ, inventory được tìm theo **_id** nên có index mặc định. Các điều kiện tenantId/available được kiểm tra sau khi xác định document.

Order lookup theo tenantId+requestId cần unique compound index để bảo vệ idempotency và giúp đọc kết quả đã có. Không tạo index trên available theo thói quen nếu chưa có workload cần nó, vì counter được cập nhật thường xuyên.

### 26.3. Chọn isolation/consistency theo yêu cầu

Một transaction không tự đồng nghĩa mọi báo cáo ngoài transaction nhìn thấy snapshot như nhau. Định nghĩa rõ read concern/write concern và thời điểm được phép hiển thị trạng thái order cho client.

### 26.4. Theo dõi metrics

Các chỉ số hữu ích:

- Transaction commit/abort count.
- Transaction duration và p95/p99.
- Write conflict / transient transaction error rate.
- Số lần retry và backoff.
- Unknown commit result/reconciliation count.
- Số lần out-of-stock có điều kiện.
- Số lần requestId duplicate hoặc payload conflict.
- Số outbox events chưa được phát.

Không log thông tin nhạy cảm, raw payment tokens hoặc toàn bộ session internals chỉ để debug transaction.

## 27. Bảo mật và phân tách tenant

Transaction cung cấp all-or-nothing cho các ghi được bao phủ; **không tự cung cấp authorization**.

Trong ví dụ service, filter update phải chứa:

~~~java
Criteria.where("_id").is(command.inventoryId())
    .and("tenantId").is(authenticatedTenantId)
    .and("available").gte(command.quantity());
~~~

Nếu chỉ dùng _id mà caller truyền được ID của tenant khác, transaction có thể commit một thao tác trừ kho xuyên tenant một cách rất nhất quán — nhưng **sai về bảo mật**.

### 27.1. Tenant từ nguồn đáng tin cậy

Không xem trường tenantId do client tự gửi là bằng chứng được phép tác động. Tenant phải được xác định từ principal, session hoặc policy server sau authentication/authorization.

### 27.2. Unique key cũng cần tenant

Nếu requestId chỉ unique trong phạm vi tenant, dùng index **{tenantId:1,requestId:1} unique**. Nếu requestId được thiết kế global unique, index đơn toàn cục cũng có thể phù hợp nhưng phải có hợp đồng rõ.

### 27.3. Lỗi phải tránh rò dữ liệu

Một exception “inventory not found” có thể đại diện cho ID không tồn tại hoặc ID thuộc tenant khác. Public API không nên tiết lộ stock/currency/order metadata của tenant khác qua thông báo lỗi quá chi tiết.

## 28. Các anti-pattern cần tránh

### 28.1. Dùng @Transactional như phép màu

~~~java
@Transactional
public void checkout(...) {
    updateInventory();
    orderRepository.insert(order);
}
~~~

Chưa đủ để chứng minh đúng nếu **không có MongoTransactionManager, MongoDB topology hỗ trợ, cùng session và lời gọi qua proxy**.

### 28.2. Bắt mọi exception rồi trả false

~~~java
try {
    reserveOrder();
} catch (Exception e) {
    return false;
}
~~~

Nếu đoạn code trên nằm trong transaction và nuốt exception, caller có thể không biết kết quả commit. Bên ngoài transaction, bắt tất cả rồi trả false cũng khiến business error bị trộn với network/commit uncertainty.

### 28.3. Tự tạo một MongoClient trong từng repository/service

Nó phá vỡ cách Spring Data đồng bộ quản lý session/resource và có thể gây nhiều connection pools dư. Dùng các bean đã cấu hình và quản lý lifecycle qua Spring.

### 28.4. Mở transaction qua một lời gọi thanh toán

External HTTP không thuộc MongoDB transaction. Giữ transaction trong khi đợi payment vừa tốn tài nguyên vừa không đem lại rollback toàn hệ thống.

### 28.5. Chạy transaction lâu để chờ event

Không dùng MongoDB transaction như một hàng đợi “đợi tới khi consumer phản hồi”. Dùng outbox/message broker và trạng thái nghiệp vụ.

### 28.6. Đưa toàn bộ Flux vào một transaction rồi subscribe riêng từng nhánh

Reactive transaction context không tự chảy qua hai lần subscription độc lập. Compose tất cả thao tác trong **một publisher chain** hoặc dùng TransactionalOperator phù hợp.

### 28.7. Coi transaction thay unique index

Hai transaction cùng đọc “requestId chưa tồn tại” có thể cạnh tranh. Unique index và cơ chế idempotency vẫn là điều kiện cốt lõi.

## 29. Bài tập thực hành

### Bài tập 1: một document có cần transaction?

Một inventory document có available=10, reserved=0. Service chạy:

~~~javascript
db.inventories.updateOne(
  {
    _id: productId,
    available: { $gte: 3 }
  },
  {
    $inc: { available: -3, reserved: 3 }
  }
);
~~~

**Câu hỏi:** Có bắt buộc mở multi-document transaction chỉ để hai field này cùng thay đổi?

**Đáp án:** Không. Một update trên một document được MongoDB áp dụng nguyên tử. Nếu còn cần tạo order/movement ở document khác và cùng commit/rollback, lúc đó mới xem xét multi-document transaction.

### Bài tập 2: transaction manager

Một Spring Boot app có MongoTemplate và OrderRepository nhưng chưa khai báo manager. Cấu hình cần thêm?

~~~java
@Bean("mongoTransactionManager")
MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory factory) {
    return new MongoTransactionManager(factory);
}
~~~

**Lưu ý:** cần bật transaction management đúng cấu hình và có MongoDB topology hỗ trợ. Không chỉ thêm bean mà bỏ qua hạ tầng.

### Bài tập 3: service có ba lần ghi

Service cần cập nhật inventory, insert order và insert movement cùng rollback. Đặt @Transactional ở đâu?

**Đáp án:** Trên public service method đại diện cho nghiệp vụ checkout/reserve, được gọi qua Spring proxy, dùng MongoTransactionManager phù hợp. Repository/template cùng tham gia ranh giới này nếu session/factory đúng.

### Bài tập 4: self-invocation

~~~java
public void checkout() {
    reserve();
}

@Transactional(transactionManager = "mongoTransactionManager")
public void reserve() {}
~~~

**Câu hỏi:** Annotation có chắc được áp dụng khi checkout gọi reserve trong cùng bean?

**Đáp án:** Không trong cơ chế Spring proxy thông thường. Lời gọi nội bộ qua this có thể bỏ qua interceptor. Tách ReservationService thành bean khác và gọi qua bean proxy hoặc thiết kế ranh giới phù hợp.

### Bài tập 5: bắt ngoại lệ

Sau khi update inventory, service insert movement thất bại. Code bắt RuntimeException rồi return false. Vì sao nguy hiểm?

**Đáp án:** Exception không thoát tới transaction interceptor, nên transaction có thể commit phần inventory đã sửa. Hãy ném RuntimeException hoặc dùng rollback-only đúng cách, với một API contract rõ.

### Bài tập 6: checked exception

Một service @Transactional ném IOException sau khi đã insert order. Mặc định Spring luôn rollback không?

**Đáp án:** Không theo quy tắc mặc định cho checked exception. Nếu nghiệp vụ cần rollback, cấu hình rollbackFor=IOException.class hoặc Exception.class thích hợp. Tránh giữ transaction lâu chỉ để bao cả I/O bên ngoài.

### Bài tập 7: nhiều datasource

Ứng dụng có JpaTransactionManager và MongoTransactionManager. Một @Transactional không ghi rõ manager có chắc điều phối MongoDB không?

**Đáp án:** Không. Phải xác định transaction manager được chọn, ví dụ transactionManager="mongoTransactionManager". Một manager MongoDB không tự tạo transaction phân tán với database SQL.

### Bài tập 8: thread khác

Trong @Transactional synchronous method, code tạo CompletableFuture chạy movementRepository.insert trên thread pool. Movement có chắc cùng transaction không?

**Đáp án:** Không. Imperative transaction session gắn theo thread context, không tự truyền qua tác vụ async. Không tách các ghi thuộc cùng transaction sang thread khác.

### Bài tập 9: hàng không đủ

Inventory available=1, checkout quantity=2. Vì sao vẫn cần filter available>=quantity dù đã có @Transactional?

**Đáp án:** Transaction chỉ quản lý commit/rollback của các thao tác; nó không tự đưa điều kiện nghiệp vụ vào update. Filter phải nêu rõ quy tắc tránh stock âm và service cần kiểm tra modifiedCount.

### Bài tập 10: rollback thật

Trong test, update inventory và insert order thành công, insert movement cố ý tạo duplicate key. Trạng thái kỳ vọng sau transaction abort?

**Đáp án:** Inventory giữ giá trị trước transaction, order không được commit, movement fixture đã tồn tại trước test vẫn còn. Nếu inventory/order vẫn được ghi, cần kiểm tra proxy, manager và session.

### Bài tập 11: retry transaction

Một MongoDB transaction nhận TransientTransactionError giữa lúc ghi inventory. Có thể tiếp tục sử dụng cùng transaction và gọi lại insert order không?

**Đáp án:** Không nên. Lỗi loại này có thể yêu cầu thử lại **toàn bộ transaction mới**, gồm đọc/validate lại, với giới hạn retry và backoff. Phải phân biệt với business out-of-stock.

### Bài tập 12: commit outcome chưa chắc chắn

Client nhận timeout sau khi service thực hiện commit. Có nên lập tức tạo một checkout mới với requestId khác?

**Đáp án:** Không. Commit có thể đã thành công. Cần tra cứu kết quả theo requestId cũ, xác minh payload và áp dụng chiến lược xử lý UnknownTransactionCommitResult phù hợp.

### Bài tập 13: unique requestId

Hai transaction cùng thấy requestId không tồn tại trước khi insert. Làm sao bảo vệ không tạo hai order?

**Đáp án:** Unique index trên (tenantId, requestId). Ngoài ra phải xử lý duplicate/write conflict và không giả định pre-check là đủ. Khi retry, đọc kết quả đã commit.

### Bài tập 14: gọi payment gateway

Service mở MongoDB transaction, giảm inventory, gọi thanh toán qua HTTP và ghi order. Nếu MongoDB rollback sau khi gateway đã thu tiền, gateway có tự hoàn tiền không?

**Đáp án:** Không. HTTP/payment gateway không thuộc MongoDB transaction; dùng reservation, saga/compensation và outbox với idempotency.

### Bài tập 15: outbox

Vì sao nên insert outbox event trong cùng transaction thay vì chỉ gọi message broker sau update inventory?

**Đáp án:** Outbox được commit cùng inventory/order, giúp tránh mất dấu sự kiện nếu process crash sau commit. Worker gửi về sau và consumer phải xử lý eventId trùng lặp.

### Bài tập 16: reactive

ReactiveMongoTemplate và ReactiveMongoRepository cần transaction manager nào?

~~~java
@Bean("reactiveMongoTransactionManager")
ReactiveMongoTransactionManager reactiveMongoTransactionManager(
        ReactiveMongoDatabaseFactory factory) {
    return new ReactiveMongoTransactionManager(factory);
}
~~~

**Đáp án:** ReactiveMongoTransactionManager hoặc TransactionalOperator dựa trên reactive manager. Các thao tác phải nằm trong publisher chain được quản lý; không block hay subscribe riêng.

### Bài tập 17: readOnly

Một report read-only dùng @Transactional(readOnly=true). Có chắc MongoDB sẽ luôn đọc secondary mà không mở session/transaction không?

**Đáp án:** Không. readOnly là metadata Spring và cách tích hợp MongoDB có semantics riêng. Cần kiểm tra read preference/concern, topology và test trên phiên bản đang dùng.

### Bài tập 18: index được tạo khi nào?

Một checkout service muốn ensureIndex ngay giữa transaction để chắc unique requestId có hiệu lực. Có nên làm vậy?

**Đáp án:** Không. Schema/index phải được chuẩn bị qua migration trước traffic. Index creation trong transaction có giới hạn và không phù hợp hoạt động checkout.

### Bài tập 19: NESTED

Bạn muốn reserve một phần line item rồi rollback riêng line đó bằng @Transactional(NESTED). Có thể mặc định MongoDB tạo savepoint như SQL không?

**Đáp án:** Không. MongoDB transactions không cung cấp nested savepoints giống cơ chế mong đợi ở một số hệ RDBMS. Thiết kế business boundary/compensation riêng.

### Bài tập 20: kiểm thử nhiều transaction

Hai khách cùng mua món cuối. Một transaction thành công, transaction khác gặp write conflict. Có nên assert transaction thất bại thứ hai luôn phải trả OutOfStockException?

**Đáp án:** Không. Write conflict khác với điều kiện tồn kho không khớp. Có thể retry transaction mới có giới hạn, sau đó lần retry mới quan sát stock=0 và trả lỗi nghiệp vụ thích hợp.

## 30. Checklist trước khi triển khai production

- **Nghiệp vụ:** các thao tác MongoDB nào bắt buộc phải cùng commit/rollback?
- **Phạm vi:** một update document đã đủ chưa, hay thật sự cần multi-document transaction?
- **Topology:** MongoDB có là replica set/sharded deployment tương thích không?
- **Driver:** Spring Data MongoDB, driver và MongoDB Server tương thích không?
- **Manager:** MongoTransactionManager có được đăng ký và chọn đúng tên bean không?
- **Proxy:** @Transactional có nằm trên public service method được gọi qua Spring proxy không?
- **Factory:** các MongoTemplate/repositories có dùng cùng MongoDatabaseFactory/session không?
- **Raw driver:** có operation nào dùng MongoClient/session riêng ngoài transaction không?
- **Async:** có thread/CompletableFuture bất ngờ tách operation ra khỏi context không?
- **Rollback:** có exception nào bị bắt nuốt khiến transaction commit không?
- **Checked error:** rollbackFor đã phù hợp với chính sách xử lý exception chưa?
- **Propagation:** các method phụ có tham gia REQUIRED thay vì vô tình tạo transaction độc lập không?
- **Nested:** không giả định MongoDB hỗ trợ savepoint như RDBMS chưa?
- **Business guard:** update inventory vẫn có available >= quantity chưa?
- **Unique:** tenantId+requestId đã có unique index được tạo thật chưa?
- **Idempotency:** cùng requestId/payload có được trả kết quả cũ, không trừ lại không?
- **Commit unknown:** có cơ chế reconciliation khi mất response commit không?
- **Retry:** có phân biệt transient error, unknown commit result và business failure không?
- **Retry scope:** mỗi lần thử dùng transaction mới phù hợp và giới hạn retry/backoff chưa?
- **Outbox:** sự kiện tới hệ thống ngoài đã được ghi nhận bền vững chưa?
- **External I/O:** không gọi payment gateway trong transaction dài chưa?
- **Options:** readConcern/writeConcern/readPreference phù hợp yêu cầu chưa?
- **Lifetime:** transaction đủ ngắn, không vượt hạn server/chờ client lâu chưa?
- **Schema:** collection/index được migration trước checkout chưa?
- **Reactive:** dùng ReactiveMongoTransactionManager và một publisher chain, không block/subscribe rời chưa?
- **Testing:** đã có replica set integration test cho commit, rollback, business guard, idempotency và concurrency chưa?
- **Metrics:** có log/đo commit, abort, write conflict, retry và p95/p99 không?
- **Security:** tenant lấy từ authentication context, không tin requestId/tenant client tự ý chưa?

## 31. Tổng kết

1. **@Transactional ở tầng service** phù hợp khi một nghiệp vụ cần nhiều MongoRepository/MongoTemplate operations **cùng commit hoặc cùng rollback**.
2. **MongoTransactionManager** quản lý MongoDB ClientSession/transaction trong stack đồng bộ; các thao tác phải tham gia qua session/factory đúng.
3. **MongoDB replica set hoặc sharded deployment tương thích** là điều kiện hạ tầng; standalone mongod không phù hợp cho multi-document transaction.
4. **Transaction một document** không thay thế business guard. Với tồn kho, vẫn cần điều kiện **available >= quantity** và $inc nguyên tử.
5. **MongoTemplate + nhiều MongoRepository** có thể cùng transaction khi được Spring quản lý đúng, không cần transaction độc lập cho từng repository.
6. **Spring proxy** quyết định việc @Transactional được intercept; self-invocation, new bean thủ công và final/private method có thể khiến annotation không hoạt động.
7. **RuntimeException mặc định gây rollback**, còn checked exception cần xem rollbackFor. Bắt nuốt exception có thể khiến service commit sai.
8. **Transaction không tự làm các thread mới, raw MongoClient khác, HTTP call hoặc payment gateway cùng atomic**.
9. **REQUIRED** là propagation thường phù hợp; không mặc định REQUIRES_NEW/NESTED có semantics hay mức hỗ trợ giống JDBC.
10. **Write conflict và UnknownTransactionCommitResult** là những trạng thái khác nhau; retry cần phân loại lỗi, giới hạn và idempotency.
11. **Unique requestId + outbox + state machine** giúp giải quyết phát lại request và side effect ngoài MongoDB, nhưng không loại bỏ nhu cầu đối soát.
12. **ReactiveMongoTransactionManager** dùng Reactor Context; phải compose publisher, không tự subscribe hay block tùy tiện.
13. **Transaction càng ngắn càng dễ vận hành**; tạo index trước, tránh chờ HTTP/aggregation/export dài trong transaction.
14. **Integration test trên replica set** cần chứng minh rollback của tất cả collection khi một thao tác cuối thất bại.
15. **Tính đúng đắn cuối cùng** đòi hỏi cả transaction boundary, điều kiện nghiệp vụ, authorization, unique constraints, consistency options và chiến lược retry phù hợp.

Nắm vững **@Transactional ở tầng dịch vụ với nhiều repository/template** giúp ứng dụng **SPRING_DATA_MONGODB** tổ chức nghiệp vụ nhiều document một cách có kiểm soát, đảm bảo các cập nhật MongoDB cần thiết được commit/rollback cùng nhau và tránh nhầm lẫn giữa transaction trong database với tính nhất quán của toàn bộ quy trình kinh doanh.

### Tài liệu tham khảo

- [Spring Data MongoDB — Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — MongoTransactionManager, ClientSession, imperative/reactive transaction.
- [Spring Data MongoDB — Transactions API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/MongoTransactionManager.html) — contract và transaction lifecycle đồng bộ.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) — @Transactional, proxy, rollback rules và propagation.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — server support, session, transaction limits và best practices.
- [MongoDB Manual — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — resource, topology và giới hạn vận hành.
- [Testcontainers — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/) — MongoDBContainer và replica set test.
