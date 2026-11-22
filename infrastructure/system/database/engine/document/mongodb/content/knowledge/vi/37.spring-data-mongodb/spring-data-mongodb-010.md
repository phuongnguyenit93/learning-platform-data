# MongoTransactionManager, @Transactional và phạm vi session trong Spring Data MongoDB

## 1. Bài toán: một nghiệp vụ cần thay đổi nhiều document cùng lúc

Giả sử ứng dụng Spring Boot xử lý đơn hàng. Khi người dùng xác nhận đơn, hệ thống phải thực hiện hai việc trên MongoDB:

1. Chuyển trạng thái document `orders` từ `PENDING` sang `CONFIRMED`.
2. Tạo một document `outbox` để worker phát sự kiện xác nhận đơn.

Nếu bước đầu thành công nhưng bước thứ hai thất bại, hệ thống có thể có đơn hàng đã xác nhận nhưng không có sự kiện để thông báo cho các dịch vụ khác. Một **multi-document transaction** giúp hai thay đổi MongoDB cùng **commit** hoặc cùng **abort**, miễn là mọi thao tác tham gia **đúng cùng transaction/session**.

~~~text
Client request
      |
      v
CheckoutService.confirmOrder()
      |
      +---- Update orders -------------------+
      |                                      |
      +---- Insert outbox event -------------+--- MongoDB Transaction
                                             |
                                +------------+------------+
                                |                         |
                                v                         v
                            Commit OK                Abort/Rollback
                                |                         |
                                v                         v
                        Cả hai cùng lưu          Không lưu thay đổi nào
~~~

Trong Spring Data MongoDB, ba khái niệm thường bị nhầm là:

- `MongoTransactionManager`: transaction manager đồng bộ của Spring.
- `@Transactional`: khai báo ranh giới và chính sách transaction trên một method.
- `ClientSession`: đối tượng driver gắn các operations với cùng session; MongoDB transactions được tạo **trên session**.

Bài thuộc module **Database Engine Document MongoDB**, chương **Spring Data MongoDB**, với đề bài **MongoTransactionManager, @Transactional và phạm vi session**.

### 1.1. Sau bài học, bạn sẽ làm được gì?

1. Giải thích vì sao transaction gắn với `ClientSession` và khi nào cần multi-document atomicity.
2. Kiểm tra điều kiện replica set, sharded cluster, server version và driver.
3. Khai báo `MongoTransactionManager` trong Spring Boot.
4. Viết service `@Transactional` dùng `MongoRepository` và `MongoTemplate`.
5. Phân biệt method boundary với session boundary, commit, abort, rollback.
6. Hiểu các cạm bẫy Spring proxy, self-invocation, checked exceptions và catch-and-swallow.
7. Chọn `TransactionTemplate` hoặc session callback khi cần điều khiển tường minh.
8. Giải thích vì sao raw driver, thread khác hoặc reactive flow có thể không tham gia cùng transaction.
9. Dùng `ReactiveMongoTransactionManager` và `TransactionalOperator` cho WebFlux/Reactor.
10. Định cấu hình readConcern, writeConcern, readPreference và transaction options.
11. Phân biệt retry toàn transaction với retry commit khi kết quả commit không rõ.
12. Kiểm tra rollback thật trên integration test chạy replica set.
13. Phân tích các hạn chế vận hành và tránh transaction dài.
14. Thiết kế outbox, idempotency, monitoring và runbook khi có write conflict hoặc failover.

**Điểm mấu chốt:** Có chú thích `@Transactional` trên method không tự biến mọi hành động của Java code thành một atomic transaction toàn hệ thống. Nó chỉ quản lý những tài nguyên/operations mà transaction manager thực sự điều khiển.

## 2. Khi nào thực sự cần transaction?

MongoDB đảm bảo **atomicity ở cấp một document**, kể cả khi cập nhật nhiều fields trong document đó. Trong nhiều trường hợp, schema embedding giúp không cần multi-document transaction.

Ví dụ một giỏ hàng có mảng items:

~~~javascript
db.carts.updateOne(
  { _id: "cart-001" },
  {
    $set: {
      "items.0.quantity": 3,
      updatedAt: new Date()
    }
  }
);
~~~

Đây là một thao tác trên một document nên được MongoDB áp dụng atomically theo cơ chế update một document. Không cần mở transaction chỉ vì thay hai fields.

### 2.1. Khi nào nên đánh giá transaction?

- Di chuyển giá trị giữa hai tài khoản ở hai documents.
- Cập nhật đơn hàng và ghi outbox event ở hai collections.
- Đặt chỗ và giảm tồn kho với ràng buộc liên documents.
- Ghi nhiều documents phải all-or-nothing.
- Thực thi invariant không thể biểu diễn thành một update atomically trong một document.

### 2.2. Khi nào không nên lạm dụng?

- Một `updateOne` với filter đủ chặt đã bảo đảm điều kiện nghiệp vụ.
- Một document đã chứa toàn bộ aggregate dữ liệu cần đồng bộ.
- Nhiều reads không đòi snapshot isolation.
- Một công việc ETL lớn hoặc batch có thể chia thành các bước idempotent.
- Một workflow trải nhiều dịch vụ, HTTP/Kafka/payment gateway mà MongoDB không kiểm soát.

Transactions xuyên nhiều shards còn có overhead cao hơn transactions giới hạn trong một shard/replica set.

### 2.3. ACID trong phạm vi MongoDB

| Thuộc tính | Ý nghĩa thực hành |
|---|---|
| Atomicity | Các writes trong transaction cùng commit hoặc cùng abort |
| Consistency | Tính nhất quán theo những constraints và logic mà ứng dụng/enforced indexes kiểm soát |
| Isolation | Các thay đổi chưa commit không nhìn thấy từ bên ngoài; mức snapshot phụ thuộc options |
| Durability | Mức bền vững phụ thuộc write concern và cấu hình deployment |

Không tuyên bố transaction tự tạo mọi business constraint nếu schema thiếu unique index hoặc logic chống duplicate.

## 3. Điều kiện bắt buộc trước khi thử

MongoDB multi-document transactions cần topology hỗ trợ:

| Deployment | Multi-document transaction |
|---|---|
| Standalone `mongod` | Không |
| Replica set | Có, từ MongoDB 4.0 với FCV phù hợp |
| Sharded cluster | Có, từ MongoDB 4.2 với FCV phù hợp |
| MongoDB Atlas | Có trên các deployment/tier hỗ trợ transactions |
| Embedded/simulator MongoDB giả lập | Không mặc định tương đương replica set thật |

### 3.1. Dùng replica set trong môi trường lab

Một MongoDB container chạy **standalone** có thể cho phép insert/find nhưng khi bắt đầu transaction sẽ lỗi:

~~~text
Transaction numbers are only allowed on a replica set member or mongos
~~~

Lỗi này không được sửa chỉ bằng thêm `@Transactional`.

### 3.2. Kiểm tra bằng mongosh

Trên một node self-managed có quyền phù hợp:

~~~javascript
db.hello();
~~~

Trên replica set, output thường có `setName`, `isWritablePrimary` hoặc `secondary`. Trên `mongos` thường thấy `msg:"isdbgrid"`.

Kiểm tra FCV khi cần và được cấp quyền:

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

### 3.3. Driver/server phiên bản tương thích

Dùng phiên bản MongoDB Java Driver và Spring Data được Spring Boot BOM hỗ trợ. Nâng MongoDB major version cần kiểm tra compatibility matrix, không chỉ xem `pom.xml` có starter.

### 3.4. Kết nối topology đúng

Ví dụ URI self-managed replica set:

~~~text
mongodb://db1.example.test:27017,db2.example.test:27017,db3.example.test:27017/orders?replicaSet=rs0&authSource=admin&tls=true
~~~

Ví dụ Atlas SRV:

~~~text
mongodb+srv://<user>:<encoded-password>@cluster0.example.mongodb.net/orders?authSource=admin&retryWrites=true&w=majority
~~~

Đây là placeholders; không đặt password thật vào bài học hoặc Git. Chọn `replicaSet` phù hợp khi dùng seed list self-managed; `mongodb+srv` có cơ chế khám phá riêng.

## 4. Session và transaction: quan hệ một-nhiều có giới hạn

Một `ClientSession` đại diện ngữ cảnh client để server nhận diện các operations có liên quan. Session hỗ trợ causal consistency và là nền tảng của transaction.

~~~text
MongoClient
   |
   +---- ClientSession A
   |        |
   |        +---- Transaction 1: start -> operations -> commit
   |        |
   |        +---- Transaction 2: start -> operations -> abort
   |
   +---- ClientSession B
            |
            +---- Transaction 3: start -> operations -> commit
~~~

Một session có thể tham gia nhiều transactions **nối tiếp**, nhưng tại một thời điểm chỉ có tối đa **một transaction đang mở trên session đó**.

### 4.1. Session không có nghĩa luôn có transaction

Có thể dùng `ClientSession` để thực hiện causally consistent reads/writes mà không gọi `startTransaction()`. Các operations trong session **không tự trở thành một atomic unit** khi chưa mở transaction.

### 4.2. Transaction cần mọi operation dùng cùng session

Trong Java Driver, các operations raw có overload nhận `ClientSession`:

~~~java
collection.insertOne(session, document);
collection.updateOne(session, filter, update);
~~~

Nếu quên tham số `session` và gọi overload không có session, thao tác đó có thể chạy **ngoài** transaction đang mong đợi.

### 4.3. Close session khi xong

Manual session cần được đóng bằng `close()`, thường dùng `try-with-resources`. Spring transaction manager sẽ quản lý lifecycle session khi dùng declarative transaction đúng cách.

### 4.4. Lazy loading sau khi session đóng

Một số phép tải dữ liệu lười (ví dụ DBRef lazy loading) có thể cần session đang còn hiệu lực. Nếu entity vượt ra khỏi session rồi mới dereference dữ liệu lazy, thao tác có thể lỗi. Thiết kế mapping/lifecycle phù hợp, không kéo dài session vô hạn chỉ để che lazy-loading.

## 5. Spring quản lý transaction ở đâu?

Trong Spring Data MongoDB đồng bộ:

~~~text
Caller -> Spring AOP transactional proxy
                    |
                    v
            MongoTransactionManager
                    |
            start ClientSession
            start MongoDB transaction
                    |
           bind session to current thread
                    |
                    v
             Service method body
                  /      \
                 v        v
         MongoRepository MongoTemplate
                 \        /
                  \      /
             MongoDatabaseFactory
                    |
             same bound session
                    |
                    v
             commit / abort
                    |
          unbind / close session
~~~

`MongoTransactionManager` triển khai Spring `PlatformTransactionManager`, mở transaction, gắn `ClientSession` với **thread hiện tại**, và hoàn tất/cleanup sau method.

`MongoTemplate` lấy session gắn với cùng `MongoDatabaseFactory` để các operations tham gia transaction. Repositories thường dùng infrastructure tương ứng nên có thể tham gia nếu cấu hình đồng bộ.

### 5.1. @Transactional không trực tiếp mở socket

Annotation được Spring transaction interceptor/AOP xử lý. Nó yêu cầu transaction manager cung cấp tài nguyên, nhưng bản thân annotation không thay driver, replica set hoặc MongoDB sessions.

### 5.2. Không có transaction manager thì sao?

Theo Spring Data MongoDB reference, transactional support cần `MongoTransactionManager` (hoặc reactive equivalent) được đăng ký. Không giả định chỉ thêm starter đã tạo manager có khả năng transactions theo đúng nhu cầu.

### 5.3. Same MongoDatabaseFactory rất quan trọng

Hai `MongoTemplate` dùng hai `MongoDatabaseFactory`/`MongoClient` khác nhau không tự tham gia một transaction, dù cùng trỏ tới hostname/database và cùng Java thread.

Không trộn repositories từ hai contexts/factories rồi gọi chúng “cùng transaction” chỉ vì method có `@Transactional`.

## 6. Khai báo MongoTransactionManager trong Spring Boot

Với Spring Data MongoDB và MongoDB Java Driver được BOM quản lý:

~~~java
package example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfig {

    @Bean("mongoTransactionManager")
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory mongoDatabaseFactory) {
        return new MongoTransactionManager(mongoDatabaseFactory);
    }
}
~~~

Đây là cấu hình tối thiểu thường dùng. Spring Boot có thể auto-configure `MongoClient`, `MongoDatabaseFactory` và `MongoTemplate`; thêm bean manager để kích hoạt MongoDB transaction support theo hướng dẫn Spring Data.

### 6.1. Vì sao tên bean rõ ràng tốt?

Khi ứng dụng còn có JDBC/JPA hoặc messaging, nhiều `PlatformTransactionManager` có thể cùng tồn tại. Khai báo:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
~~~

giúp chọn **đúng** manager, không phụ thuộc bean mặc định/`@Primary` của môi trường.

### 6.2. Không tạo MongoClient riêng trong cấu hình manager

Tránh cấu hình sau nếu ứng dụng đã có auto-configured client:

~~~java
// Anti-pattern: tạo một MongoClient mới riêng chỉ để làm transaction manager.
// Có thể dẫn tới khác MongoDatabaseFactory hoặc connection pool ngoài dự kiến.
~~~

Manager phải dùng đúng factory mà repositories và `MongoTemplate` transactional sử dụng.

### 6.3. Spring Boot 3.x so với 4.x: URI property

Với Boot 3.5:

~~~yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI}"
~~~

Với Boot 4.x:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
~~~

Sự khác biệt là **prefix cấu hình kết nối**. Class `MongoTransactionManager` ở package Spring Data `org.springframework.data.mongodb` trong các ví dụ hiện đại. Xác minh theo Boot/Spring Data version thực tế.

### 6.4. Dependency sync

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Không thêm starter reactive nếu chỉ có code synchronous. Dùng Spring Boot BOM để quản versions.

## 7. Thiết kế document cho ví dụ order và outbox

Tạo hai collections từ trước:

~~~javascript
use orders_lab

db.createCollection("orders");
db.createCollection("outbox");

db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
);

db.outbox.createIndex(
  { aggregateId: 1, type: 1 },
  { name: "idx_aggregate_type" }
);
~~~

Tạo collections/indexes trước làm giảm rủi ro collection creation/index DDL xảy ra lần đầu ngay trong transaction và giúp kiểm soát schema trên môi trường production.

### 7.1. Order entity

~~~java
package example.orders.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class Order {
    @Id
    private String id;
    private String tenantId;
    private String status;

    protected Order() {
    }

    public Order(String id, String tenantId, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
}
~~~

### 7.2. OutboxEvent entity

~~~java
package example.orders.domain;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("outbox")
public class OutboxEvent {
    @Id
    private String id;
    private String aggregateId;
    private String type;
    private Instant occurredAt;

    protected OutboxEvent() {
    }

    public OutboxEvent(String id, String aggregateId, String type,
                       Instant occurredAt) {
        this.id = id;
        this.aggregateId = aggregateId;
        this.type = type;
        this.occurredAt = occurredAt;
    }

    public String getId() { return id; }
    public String getAggregateId() { return aggregateId; }
    public String getType() { return type; }
    public Instant getOccurredAt() { return occurredAt; }
}
~~~

### 7.3. Repositories

~~~java
package example.orders.repo;

import example.orders.domain.Order;
import example.orders.domain.OutboxEvent;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
}

public interface OutboxEventRepository
        extends MongoRepository<OutboxEvent, String> {
}
~~~

Ở dự án Java thực tế, để mỗi public top-level interface trong file Java cùng tên. Ví dụ trên được ghép để trình bày.

## 8. @Transactional trên service: ví dụ có thể quan sát

~~~java
package example.orders.service;

import example.orders.domain.Order;
import example.orders.domain.OutboxEvent;
import example.orders.repo.OrderRepository;
import example.orders.repo.OutboxEventRepository;

import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final OutboxEventRepository outbox;

    public CheckoutService(OrderRepository orders,
                           OutboxEventRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void confirm(String orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId));

        if (!"PENDING".equals(order.getStatus())) {
            throw new IllegalStateException(
                "Order is not pending: " + orderId);
        }

        order.setStatus("CONFIRMED");
        orders.save(order);

        OutboxEvent event = new OutboxEvent(
            "order-confirmed:" + orderId,
            orderId,
            "OrderConfirmed",
            Instant.now()
        );
        outbox.save(event);
    }
}
~~~

Nếu `orders.save` thành công nhưng `outbox.save` ném runtime exception, Spring transaction interceptor rollback transaction, nên trạng thái order không commit.

### 8.1. Vì sao transaction boundary đặt ở service?

Transaction bao quanh một **use case nghiệp vụ**. Đặt `@Transactional` ở từng repository method riêng lẻ không tự gộp nhiều repository calls thành một transaction. Service method biết các operations nào cần all-or-nothing.

### 8.2. Giới hạn ví dụ đối với concurrency

Code trên minh họa atomicity, chưa phải toàn bộ giải pháp đồng thời:

- Hai request cùng xác nhận một order có thể cạnh tranh.
- MongoDB có thể tạo write conflict khiến một transaction abort.
- Unique event ID giúp chống duplicate ở outbox nhưng không thay retry/idempotency policy.
- Production nên có conditional state transition, versioning hoặc deduplication phù hợp.

### 8.3. Transaction không tự gửi Kafka event

Outbox document được commit trong MongoDB; **việc publish** nên thực hiện bởi worker/consumer sau commit, có idempotency và retry riêng. Không gửi HTTP/Kafka trong transaction rồi tuyên bố MongoDB rollback được tác động ngoài database.

## 9. Lifecycle của @Transactional

Trong trường hợp method được gọi **qua Spring-managed proxy**:

~~~text
1. Caller gọi CheckoutService proxy
2. Spring chọn mongoTransactionManager
3. Manager tạo/gắn ClientSession
4. Manager bắt đầu MongoDB transaction
5. Service gọi repositories/MongoTemplate
6. Các calls dùng cùng bound ClientSession
7. Method trả về bình thường -> commitTransaction
8. Method ném lỗi cần rollback -> abortTransaction
9. Cleanup, unbind, close session
~~~

### 9.1. Commit ở cuối method, không phải sau từng save()

Khi `orders.save` trả về thành công bên trong transaction, dữ liệu chưa nhất thiết được quan sát bởi clients ngoài transaction. Commit thành công mới xác lập atomic outcome.

### 9.2. Method return thành công nhưng commit vẫn có thể fail

Transaction commit xảy ra khi interceptor kết thúc method. Có thể xuất hiện lỗi commit (network, failover, writeConcern, UnknownTransactionCommitResult). Service code đã chạy đến `return` không có nghĩa caller chắc nhận thành công.

### 9.3. Transaction bắt đầu là tài nguyên tốn kém

Giữ transaction qua sleep, remote HTTP, file upload hoặc chờ người dùng làm cache/resource pressure tăng, kéo dài locks và rủi ro abort.

## 10. @Transactional proxy và self-invocation

Spring transaction annotation thường hoạt động thông qua AOP proxy. **Gọi nội bộ trên cùng object** có thể không đi qua proxy.

~~~java
@Service
public class BadCheckoutService {

    public void submit(String orderId) {
        // Gọi trên this, bỏ qua transactional proxy:
        confirmInternal(orderId);
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void confirmInternal(String orderId) {
        // Nhiều MongoDB operations...
    }
}
~~~

Nếu method `submit()` được gọi từ bên ngoài mà không có transaction bao quanh, self-call tới `confirmInternal()` sẽ không kích hoạt advice như mong đợi.

### 10.1. Cách tốt: tách service

~~~text
OrderController
      |
      v
OrderApplicationService
      |
      v
TransactionalCheckoutService proxy
      |
      v
@Transactional confirm()
~~~

~~~java
@Service
public class OrderApplicationService {
    private final CheckoutService checkout;

    public OrderApplicationService(CheckoutService checkout) {
        this.checkout = checkout;
    }

    public void submit(String orderId) {
        checkout.confirm(orderId);
    }
}
~~~

CheckoutService là bean Spring riêng được inject nên public method invocation đi qua proxy trong cấu hình thông thường.

### 10.2. Private/final methods và proxy

Không đặt transaction boundary vào private helper rồi kỳ vọng Spring proxy chặn được. Final methods/classes và JDK/class-based proxies có hạn chế khác nhau. Dùng public service methods và gọi qua bean proxy là mô hình dễ hiểu/kiểm thử.

### 10.3. Constructor và @PostConstruct

Gọi transactional method trong constructor hoặc quá sớm trước khi proxy sẵn sàng không bảo đảm advice được áp. Khởi tạo dữ liệu nên qua cơ chế lifecycle/runner phù hợp, có bean proxy và kiểm tra transaction.

## 11. Rollback rules: RuntimeException, checked exception và Error

Mặc định Spring thường rollback với `RuntimeException` và `Error`, **không tự rollback với mọi checked exception**.

### 11.1. Runtime exception

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void doWork() {
    // Write A
    throw new IllegalStateException("simulate failure");
    // Write B không chạy
}
~~~

Khi có lỗi unchecked thoát ra khỏi proxy, transaction bị abort.

### 11.2. Checked exception

~~~java
public class BusinessRuleException extends Exception {
    public BusinessRuleException(String message) {
        super(message);
    }
}
~~~

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    rollbackFor = BusinessRuleException.class
)
public void confirmWithRule(String id) throws BusinessRuleException {
    // Write A
    throw new BusinessRuleException("rule failed");
}
~~~

Nếu bỏ `rollbackFor`, checked exception có thể **không** kích hoạt rollback theo cấu hình mặc định Spring. Hãy chủ động định nghĩa rollback policy.

### 11.3. Không dùng checked exception chỉ để ra hiệu rollback

Cân nhắc phân biệt business validation xảy ra **trước write**, với system failure xảy ra **sau write**. Nếu kiểm tra được trước khi mở transaction, làm vậy giúp giảm tài nguyên và lỗi xử lý.

## 12. Catch-and-swallow có thể vô tình commit

Sai lầm phổ biến:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void unsafeAction() {
    try {
        // Write A
        // Write B -> lỗi
    } catch (Exception e) {
        // Chỉ log, không throw -> interceptor có thể commit!
    }
}
~~~

Nếu exception được nuốt, method kết thúc bình thường và Spring có thể thử commit. Với một số MongoDB operation errors, transaction server có thể đã ở trạng thái abort-only; nhưng không được dựa vào điều đó như cơ chế rollback business.

### 12.1. Cách ưu tiên: để exception thoát

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void saferAction() {
    // Write A
    // Write B: nếu fail, cho RuntimeException thoát.
}
~~~

### 12.2. Khi buộc phải xử lý lỗi trong method

Có thể đặt rollback-only:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

try {
    // ... actions
} catch (KnownBusinessException e) {
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    // Chỉ trả response phù hợp sau khi đảm bảo không coi đã commit.
}
~~~

Đây là cách phụ thuộc transaction context và tạo coupling với Spring transaction infrastructure. Ưu tiên tách validation và exception flow rõ ràng hơn.

### 12.3. UnexpectedRollbackException

Nếu inner method đánh dấu shared transaction rollback-only nhưng outer method vẫn kết thúc bình thường, outer caller có thể nhận `UnexpectedRollbackException` lúc commit. Đừng giải quyết bằng cách tắt exception; cần xác định propagation, error handling và mong muốn nghiệp vụ.

## 13. Transaction propagation: REQUIRED và những giới hạn

Các giá trị propagation là khái niệm **Spring transaction manager**, không phải “nested MongoDB transaction” tương ứng 1:1.

| Propagation | Ý nghĩa Spring-level | Lưu ý với MongoDB |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện có hoặc tạo mới | Thường là mặc định phù hợp |
| `SUPPORTS` | Tham gia nếu đang có | Không bảo đảm có transaction nếu gọi độc lập |
| `MANDATORY` | Yêu cầu đã có transaction | Dùng để enforce boundary |
| `NEVER` | Không được nằm trong transaction | Có thể fail khi caller đang transactional |
| `NOT_SUPPORTED` | Chạy ngoài transaction nếu manager hỗ trợ suspend | Kiểm tra manager/resource behavior |
| `REQUIRES_NEW` | Đòi transaction độc lập, có suspend/resume | Không giả định Mongo manager hỗ trợ mọi trường hợp |
| `NESTED` | Savepoint-style nested transaction | MongoDB không cung cấp nested transaction/savepoint tương đương |

### 13.1. REQUIRED không tạo transaction con

Nếu `ServiceA.operation()` đang mở transaction rồi gọi `ServiceB.save()` có `REQUIRED`, thông thường cả hai dùng **cùng** MongoDB transaction/session.

~~~text
A @Transactional(REQUIRED)
    |
    +--> B @Transactional(REQUIRED)
            |
         Same ClientSession
         Same transaction
~~~

### 13.2. Không mặc định dùng REQUIRES_NEW cho audit

Không dùng `REQUIRES_NEW` với kỳ vọng chắc chắn ghi audit dù transaction ngoài abort; với MongoDB transaction manager, suspension/restart có thể không được hỗ trợ theo ngữ cảnh. Nếu cần audit độc lập, dùng infrastructure riêng được kiểm chứng và hiểu rằng nó **không** thuộc cùng atomic unit.

### 13.3. NESTED không đồng nghĩa transaction trong transaction

MongoDB chỉ có một active transaction trên mỗi session, không có JDBC-style savepoint cho MongoDB transactions. Đừng dùng `Propagation.NESTED` với kỳ vọng rollback một phần các writes nhưng vẫn commit phần còn lại.

### 13.4. Tên transaction manager

Trong service có MongoDB và JDBC:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
~~~

Chú thích không bao gồm SQL writes của `JpaTransactionManager` hay HTTP calls. Hai transaction managers độc lập **không** tự tạo distributed two-phase commit.

## 14. @Transactional(readOnly = true) không có nghĩa “không có session”

Với Spring Data MongoDB, `@Transactional(readOnly = true)` vẫn có thể mở transaction và gắn `ClientSession` cho operations. Nó không phải lựa chọn tối ưu mặc định cho mọi API read-only.

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    readOnly = true
)
public Order findOrder(String id) {
    return orders.findById(id).orElseThrow();
}
~~~

### 14.1. Không coi readOnly là kiểm soát quyền ghi

`readOnly=true` là transaction hint/cấu hình ở Spring-level; không dùng nó thay MongoDB database roles hoặc ACL. Muốn chặn writes, cấp user role read-only ở MongoDB.

### 14.2. Read preference trong transaction

Transactions có reads phải dùng `primary` theo MongoDB docs. Không kỳ vọng `@Transactional(readOnly=true)` sẽ tự chuyển tất cả queries sang secondary.

### 14.3. Đọc chỉ một document có cần transaction?

Thường không, trừ khi có consistency requirements rõ. Một transaction read-only có overhead snapshot/session và nên được quyết định theo use case.

## 15. Transaction options: read concern, write concern, read preference

MongoDB transaction isolation/durability phụ thuộc options:

- `ReadConcern.SNAPSHOT`: dùng snapshot consistency theo requirements hỗ trợ.
- `WriteConcern.MAJORITY`: commit được majority acknowledge, là lựa chọn phổ biến cho durability.
- `ReadPreference.primary()`: cần cho transactions có read operations.
- `maxCommitTime`: giới hạn thời gian commit operation theo cấu hình driver.

### 15.1. Cấu hình defaults trong MongoTransactionManager

~~~java
package example.orders.config;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfig {

    @Bean("mongoTransactionManager")
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY)
            .readPreference(ReadPreference.primary())
            .build();

        return new MongoTransactionManager(factory, options);
    }
}
~~~

Đây là **phương án có chủ đích** cho một loại nghiệp vụ; không tuyên bố mọi application bắt buộc dùng đúng bộ options này.

### 15.2. Phân biệt writeConcern trong transaction

Write concern của transaction áp dụng ở commit theo semantics của MongoDB; không giả định một write concern riêng trên từng collection operation sẽ override commit guarantee.

### 15.3. Snapshot trong sharded clusters

Với transaction nhiều shards, `snapshot` read concern được dùng khi cần consistent snapshot xuyên shards. Các mức khác không bảo đảm cùng một snapshot giữa shards.

### 15.4. Đừng dùng read preference secondary trong read transaction

MongoDB docs yêu cầu các transactions chứa reads dùng primary, dù Spring Data transaction labels có thể nhận những enum values rộng hơn ở config layer. “Parser chấp nhận” không có nghĩa server hỗ trợ ngữ nghĩa trong giao dịch đang chạy.

## 16. @Transactional labels cho Mongo-specific options

Spring Data MongoDB các phiên bản hỗ trợ có thể đọc transaction labels để xác định options tại transaction boundary.

Ví dụ:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    label = {
        "mongo:readConcern=SNAPSHOT",
        "mongo:writeConcern=MAJORITY",
        "mongo:readPreference=PRIMARY",
        "mongo:maxCommitTime=PT1S"
    }
)
public void confirmWithOptions(String orderId) {
    // MongoDB operations trong cùng factory/session
}
~~~

### 16.1. Kiểm tra Spring Data version

Transaction labels và `MongoTransactionOptionsResolver` có điều kiện theo Spring Data release. Không copy annotations từ tài liệu hiện đại sang version cũ rồi coi là đã support.

### 16.2. Options của outer transaction quyết định

Một inner method `REQUIRED` tham gia transaction đã mở, labels của inner method **không tự thay đổi** options của transaction đang chạy. Đặt consistency/durability ở boundary thực sự mở transaction.

### 16.3. Timeout annotation không thay server lifetime limit

`@Transactional(timeout = 10)` là một Spring transaction setting và không nhất thiết kiểm soát toàn bộ MongoDB server transaction lifetime theo kỳ vọng. Server có `transactionLifetimeLimitSeconds` (mặc định thường 60 giây) và commit có `maxCommitTime` riêng. Phải kiểm tra driver, manager và server semantics.

## 17. TransactionTemplate: ranh giới chương trình thay vì annotation

Nếu muốn boundary tường minh, dùng `TransactionTemplate`.

~~~java
package example.orders.service;

import example.orders.domain.Order;
import example.orders.repo.OrderRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class OrderProgrammaticService {
    private final OrderRepository orders;
    private final TransactionTemplate tx;

    public OrderProgrammaticService(
            OrderRepository orders,
            @Qualifier("mongoTransactionManager")
            PlatformTransactionManager manager) {
        this.orders = orders;
        this.tx = new TransactionTemplate(manager);
    }

    public void markConfirmed(String id) {
        tx.executeWithoutResult(status -> {
            Order order = orders.findById(id).orElseThrow();
            order.setStatus("CONFIRMED");
            orders.save(order);
        });
    }
}
~~~

### 17.1. Khi nào thích hợp?

- Một method có vài nhánh khác nhau, chỉ một đoạn cần transaction.
- Muốn viết retry wrapper ngoài một callback.
- Muốn đặt rollback-only có chủ đích.
- Muốn tránh self-invocation proxy pitfalls trong phạm vi code hợp lý.

### 17.2. Có thể đặt rollback-only

~~~java
tx.executeWithoutResult(status -> {
    if (businessRuleFails()) {
        status.setRollbackOnly();
        return;
    }
    // Mongo operations...
});
~~~

Giả định `businessRuleFails()` là hàm nghiệp vụ của ứng dụng. Kiểm tra có trả kết quả phản ánh rollback cho caller, không báo đã hoàn tất đơn hàng khi transaction thực ra không commit.

### 17.3. TransactionTemplate dùng cùng manager/factory

Nếu `TransactionTemplate` dùng JDBC manager, MongoTemplate không tự được bao bọc bởi MongoDB transaction. Chọn và inject đúng manager.

## 18. Manual ClientSession: khi nào cần kiểm soát trực tiếp?

Spring Data `MongoTemplate.withSession(...)` cho phép scope một chuỗi operations với một session cụ thể.

Ví dụ giản lược:

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class SessionReader {

    private final MongoClient client;
    private final MongoTemplate template;

    public SessionReader(MongoClient client, MongoTemplate template) {
        this.client = client;
        this.template = template;
    }

    public void readWithSession(String id) {
        try (ClientSession session = client.startSession()) {
            template.withSession(session).execute(ops -> {
                Query query = Query.query(Criteria.where("_id").is(id));
                ops.findOne(query, Order.class);
                return null;
            });
        }
    }
}
~~~

Đoạn trên **dùng session nhưng chưa gọi startTransaction**, vì vậy nó không tạo multi-document atomic transaction.

### 18.1. Manual transaction với driver

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public void writeAtomically(MongoClient client) {
    MongoCollection<Document> left =
        client.getDatabase("orders_lab").getCollection("left");
    MongoCollection<Document> right =
        client.getDatabase("orders_lab").getCollection("right");

    try (ClientSession session = client.startSession()) {
        session.startTransaction();

        try {
            left.insertOne(session,
                new Document("_id", "left-001").append("value", 1));
            right.insertOne(session,
                new Document("_id", "right-001").append("value", 2));

            session.commitTransaction();
        } catch (RuntimeException ex) {
            if (session.hasActiveTransaction()) {
                session.abortTransaction();
            }
            throw ex;
        }
    }
}
~~~

Đây là ví dụ ý tưởng có nguy cơ duplicate IDs khi chạy lại. Production nên dùng driver transaction retry APIs/withTransaction phù hợp và idempotent business keys, không xem code demo là chiến lược recovery hoàn chỉnh.

### 18.2. Không mix thủ công với @Transactional mà không kiểm soát

Một method đã có `@Transactional` rồi tự gọi `client.startSession()` có thể tạo **session thứ hai độc lập**. Các raw operations trên session mới không mặc nhiên tham gia Spring-bound transaction.

### 18.3. getCollection() là native driver gateway

`MongoTemplate.getCollection()` trả native `MongoCollection`, và theo Spring Data docs, các thao tác trực tiếp trên gateway này có thể không được session proxy tự truyền. Khi cần transaction, dùng `MongoTemplate` operations hoặc explicitly pass `ClientSession` vào driver overloads phù hợp.

## 19. Phạm vi session trong Spring đồng bộ: ThreadLocal

`MongoTransactionManager` gắn session với **current thread** thông qua Spring transaction synchronization/resource binding.

~~~text
HTTP worker thread A
  |
  +-- @Transactional service A
         |
         +-- Repository.insert    -> session S1
         +-- MongoTemplate.update -> session S1
         +-- Repository.find      -> session S1
  |
  +-- return / commit / unbind

Executor thread B
  |
  +-- Mongo operation            -> KHÔNG tự có session S1
~~~

### 19.1. @Async không tự kế thừa transaction

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void confirm(String id) {
    orders.save(...);

    asyncWorker.sendNotification(id); // @Async qua thread khác
}
~~~

Lời gọi asynchronous có thể chạy trước commit hoặc sau rollback và **không dùng cùng thread/session**. Tránh gửi side effect từ transaction; dùng outbox hoặc event handler after-commit có semantics phù hợp.

### 19.2. CompletableFuture/new Thread/ExecutorService

Tạo thread mới trong method transactional không tự lan truyền ThreadLocal session:

~~~java
CompletableFuture.runAsync(() -> repository.save(...));
~~~

Thao tác async có thể nằm ngoài transaction và diễn ra không đúng thứ tự. Không dùng “ThreadLocal copy” tự viết để chia sẻ ClientSession giữa threads; MongoDB Java Driver không cho phép chạy operations song song trên cùng transaction/session như ý muốn.

### 19.3. Servlet request scope khác transaction scope

Một HTTP request có thể gọi nhiều services. Transaction boundary chỉ bao phủ method/call stack được manager xử lý, **không** tự bằng toàn bộ request hay cả response stream.

### 19.4. Session không an toàn để dùng đồng thời tùy tiện

MongoDB không hỗ trợ parallel operations trong cùng transaction. Không chạy `parallelStream` hoặc nhiều futures đồng thời cùng session để “tối ưu” multi-document transaction.

## 20. Reactive: không dùng MongoTransactionManager của luồng blocking

Trong WebFlux/Reactor, Spring Data MongoDB cung cấp `ReactiveMongoTransactionManager`.

~~~text
Reactive request publisher
          |
          v
TransactionalOperator / @Transactional
          |
          v
Reactor Context chứa transactional resources
          |
          v
ReactiveMongoTemplate / Reactive repository
          |
          v
Reactive MongoDB driver + session
~~~

**Khác biệt quan trọng:**

| Luồng | Transaction manager | Session binding |
|---|---|---|
| Synchronous/blocking | `MongoTransactionManager` | Thread-bound |
| Reactive | `ReactiveMongoTransactionManager` | Reactor Context |

### 20.1. Khai báo manager reactive

~~~java
package example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ReactiveMongoTxConfig {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

### 20.2. @Transactional trên reactive method

~~~java
@Service
public class ReactiveCheckoutService {
    private final ReactiveOrderRepository orders;
    private final ReactiveOutboxRepository outbox;

    public ReactiveCheckoutService(
            ReactiveOrderRepository orders,
            ReactiveOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional(transactionManager = "reactiveMongoTransactionManager")
    public Mono<Void> confirm(String orderId) {
        return orders.findById(orderId)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Order not found")))
            .flatMap(order -> {
                order.setStatus("CONFIRMED");

                return orders.save(order)
                    .then(outbox.save(new OutboxEvent(
                        "order-confirmed:" + orderId,
                        orderId,
                        "OrderConfirmed",
                        java.time.Instant.now()
                    )));
            })
            .then();
    }
}
~~~

Ở đây `ReactiveOrderRepository` và `ReactiveOutboxRepository` là các interfaces do bạn khai báo extends `ReactiveMongoRepository<...,String>`, và `Mono` là `reactor.core.publisher.Mono`. Cần đủ imports/beans/dependencies reactive để biên dịch.

### 20.3. Không gọi block() để tạo “transaction sync”

~~~java
// Anti-pattern trong reactive flow:
reactiveRepository.save(order).block();
~~~

Chuyển qua blocking có thể làm mất reactor context và gây deadlock/thread starvation trong WebFlux. Transaction reactive cần giữ publisher chain và subscribe trong đúng framework.

### 20.4. Laziness của Reactor

Method trả `Mono` chưa thực hiện I/O ngay khi được gọi; operations diễn ra khi subscribed. Transactional interceptor reactive quản lý scope qua publisher lifecycle, không thể suy luận thời gian mở/commit từ dòng Java tạo `Mono`.

### 20.5. Synchronous repository và reactive manager không thay thế nhau

Không mix blocking `MongoRepository` với `ReactiveMongoTransactionManager` rồi kỳ vọng cùng session. Chọn transaction model theo driver/template/repository stack.

## 21. TransactionalOperator cho Reactor

Trong reactive flow, `TransactionalOperator` giúp xác định scope mà không cần proxy method.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReactiveAtomicService {
    private final ReactiveMongoTemplate mongoTemplate;
    private final TransactionalOperator operator;

    public ReactiveAtomicService(
            ReactiveMongoTemplate mongoTemplate,
            @Qualifier("reactiveMongoTransactionManager")
            ReactiveTransactionManager manager) {
        this.mongoTemplate = mongoTemplate;
        this.operator = TransactionalOperator.create(manager);
    }

    public Mono<Void> writeTwoDocuments() {
        return mongoTemplate.insert(
                new Document("_id", "a1"), "a")
            .then(mongoTemplate.insert(
                new Document("_id", "b1"), "b"))
            .then()
            .as(operator::transactional);
    }
}
~~~

Đoạn rút gọn dùng `org.bson.Document` và `org.springframework.data.mongodb.core.ReactiveMongoTemplate`; cần dependencies reactive và collections được chuẩn bị trước.

### 21.1. Transaction scope phụ thuộc publisher được bao

`.as(operator::transactional)` chỉ bao các operations upstream trong publisher được cung cấp. Một `Mono`/`Flux` độc lập được subscribe ngoài chain có thể không nằm trong transaction.

### 21.2. Không subscribe thủ công giữa service

~~~java
// Anti-pattern: subscribe tách luồng bên trong service.
repository.save(order).subscribe();
return Mono.empty();
~~~

Trong cách viết này save chạy độc lập, khó biết khi nào lỗi/commit. Trả về publisher và compose với `then`/`flatMap` để manager kiểm soát.

### 21.3. Manual ClientSession reactive khác reactive transaction manager

Spring Data reference phân biệt session callbacks trên `ReactiveMongoTemplate` và managed reactive transactions. Không cố mang `ThreadLocal` session của imperative manager sang Reactor Context.

## 22. MongoTemplate và SessionSynchronization

`MongoTemplate` có thuộc tính `SessionSynchronization`:

| Giá trị | Ý nghĩa |
|---|---|
| `ON_ACTUAL_TRANSACTION` | Tham gia native MongoDB transaction do MongoTransactionManager mở |
| `ALWAYS` | Tham gia cả transaction Spring khác và có thể khởi tạo MongoDB transaction theo infrastructure |
| `NEVER` | Không đồng bộ với transactional session |

Ở các Spring Data MongoDB versions hiện đại, default là `ON_ACTUAL_TRANSACTION`.

### 22.1. Có cần set ALWAYS khi dùng MongoTransactionManager?

Thông thường **không** khi đã dùng `MongoTransactionManager` đúng factory và default `ON_ACTUAL_TRANSACTION`. `ALWAYS` dùng cho mục đích khác, ví dụ tham gia một transaction Spring không native MongoDB theo hướng dẫn.

### 22.2. Không thay settings runtime

~~~java
// Tránh đổi liên tục trong khi nhiều threads đang hoạt động:
template.setSessionSynchronization(SessionSynchronization.ALWAYS);
~~~

Spring Data cảnh báo thay trạng thái `MongoTemplate` trong runtime có thể gây threading/visibility issues. Cấu hình một lần trước khi bean phục vụ traffic.

### 22.3. ALWAYS không tạo distributed XA

Việc MongoTemplate tham gia transaction Spring khác không biến MongoDB và JDBC/Kafka thành một global transaction commit đồng thời. Khi cần cross-system consistency, sử dụng outbox/saga hoặc giải pháp phù hợp với semantics và failure modes.

## 23. Phạm vi session khi có nhiều MongoClient/factories

Giả sử ứng dụng có:

~~~text
MongoClient A -> MongoDatabaseFactory A -> MongoTemplate A
MongoClient B -> MongoDatabaseFactory B -> MongoTemplate B
~~~

Nếu `MongoTransactionManager` được tạo từ factory A, các operations trên Template B không tự nằm trong transaction A.

### 23.1. Cùng URI không có nghĩa cùng transaction

Ngay cả khi A và B trỏ tới cùng deployment, driver sessions là đối tượng riêng và Spring resource binding dựa vào factory. Đừng “đoán” rằng cùng hostname đã đủ.

### 23.2. Multi-tenant database routing

Một custom `MongoDatabaseFactory` chọn database theo tenant có thể làm session/bound transaction phức tạp. Đảm bảo tenant context không đổi giữa transaction và mọi calls dùng cùng session/factory. Không chuyển tenant giữa chừng trên transaction đã mở.

### 23.3. Nhiều PlatformTransactionManager

Nếu có Mongo, JDBC, Redis, messaging:

- Đặt tên beans rõ.
- Dùng `@Transactional(transactionManager="...")`.
- Không để `@Primary` ngẫu nhiên quyết định boundary.
- Không giả định cross-store atomicity.
- Test tình huống một nguồn commit thành công nhưng nguồn khác fail.

## 24. Những thao tác nằm ngoài transaction dù trong method

Ví dụ:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void process(String id) {
    orders.save(...);          // MongoDB - có thể tham gia tx
    paymentGateway.charge(...); // HTTP - KHÔNG thuộc MongoDB tx
    kafkaTemplate.send(...);    // Kafka - KHÔNG thuộc MongoDB tx
    auditJdbcRepository.save(...); // JDBC - manager khác
}
~~~

MongoDB có thể abort `orders.save` nhưng không đảo được thanh toán đã thực hiện hoặc message đã được broker xác nhận.

### 24.1. Transaction đồng bộ với external side effects là nguy hiểm

Giữ transaction mở trong khi gọi payment gateway nhiều giây tăng risk timeout/cache/lock pressure. Nếu commit MongoDB thất bại sau khi gateway đã charge, hệ thống cần compensation/deduplication.

### 24.2. Outbox pattern

Thay vì gửi message trực tiếp:

~~~text
@Transactional:
  - cập nhật order
  - insert outbox event

Commit MongoDB

Outbox worker:
  - lấy event
  - publish broker
  - đánh dấu delivered/retry idempotently
~~~

Outbox giúp lưu dữ liệu và ý định phát sự kiện atomically trong MongoDB; delivery vẫn thường có **at-least-once** semantics nên consumer cần idempotency.

### 24.3. After-commit callback không tạo atomic delivery

Spring có `@TransactionalEventListener(phase = AFTER_COMMIT)` và transaction synchronizations. Chúng giúp chỉ chạy callback sau commit nhưng **nếu process chết sau commit trước khi gửi message**, event có thể bị mất. Outbox bền vững hơn cho delivery quan trọng.

## 25. Transaction retries: không phải mọi lỗi đều retry được

MongoDB dùng error labels để giúp driver/application phân biệt transient transaction failure và không rõ kết quả commit.

Hai labels quan trọng:

- `TransientTransactionError`: có thể cần retry **toàn bộ transaction** từ đầu.
- `UnknownTransactionCommitResult`: commit đã được gửi nhưng client không biết chắc đã thành công hay chưa; thường cần retry **commit** theo đúng algorithm, không tự chạy lại nghiệp vụ ngay.

### 25.1. TransientTransactionError

Ví dụ transaction gặp write conflict hoặc failover trước commit. Cách xử lý có thể là:

~~~text
Attempt 1:
 start tx -> writes -> transient error -> abort
Attempt 2:
 start NEW tx -> re-read state -> writes -> commit
~~~

Retry phải có giới hạn attempt/time, jitter/backoff và kiểm tra business invariants, không infinite loop.

### 25.2. UnknownTransactionCommitResult

~~~text
Client gửi commitTransaction
        |
        v
Network timeout
        |
        v
Không rõ server đã commit chưa
~~~

Không mặc định “timeout nghĩa là rollback”. Chạy lại cả nghiệp vụ có thể phát thêm outbox events/charges nếu transaction trước đã commit; cần retry commit theo driver/manual guidance hoặc reconcile idempotent business key.

### 25.3. @Transactional không tự retry mọi lỗi MongoDB

Spring transaction interceptor xử lý commit/rollback theo outcomes. Nó không phải một generic MongoDB retry engine cho mọi transaction body và commit ambiguity.

### 25.4. Retry wrapper phải nằm ngoài transaction boundary

Một kiến trúc:

~~~text
Retry orchestrator (ngoài)
         |
         v
@Transactional service proxy (mỗi attempt = tx mới)
         |
         v
MongoDB operations
~~~

Nếu dùng Spring Retry annotations, kiểm tra advice order và behavior bằng integration test. Cách rõ ràng là một bean retry bên ngoài gọi bean service transactional riêng, không self-invocation.

### 25.5. Idempotency là lớp bảo vệ nghiệp vụ

Ví dụ request xác nhận order có ID đã được xác nhận. Nếu retry sau uncertain commit, hệ thống nên tìm trạng thái cuối và event key duy nhất thay vì tạo những side effects trùng.

## 26. Transaction lifetime và performance

MongoDB mặc định có giới hạn lifetime của transaction thường **60 giây**, qua `transactionLifetimeLimitSeconds` trên `mongod` (thay đổi theo admin policy/tier). Transactions quá lâu có thể bị abort định kỳ.

### 26.1. Đừng làm I/O ngoài database trong transaction

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void badFlow() {
    // MongoDB write A
    // Upload file 30 giây
    // Gọi HTTP 20 giây
    // MongoDB write B
}
~~~

Nhiều giây chờ I/O làm transaction giữ snapshot/resources lâu, tăng cache pressure và risk aborted transaction.

### 26.2. Large transactions

Ghi quá nhiều documents trong một transaction có thể tạo storage-cache pressure và lỗi như:

- `WriteConflict`.
- `TransactionTooLargeForCache`.
- Transaction lifetime exceeded.
- Lock acquisition timeout.
- Commit network/writeConcern timeout.

### 26.3. Sharded transaction có cost bổ sung

Transaction chạm nhiều shards có coordination overhead hơn single-shard transaction. Nếu schema/shard key cho phép giữ một business aggregate trên một shard, thường dễ tối ưu hơn.

### 26.4. Thiết kế transaction ngắn

- Validate input trước.
- Precompute deterministic values.
- Chỉ thực hiện những MongoDB operations cần all-or-nothing.
- Không gọi remote services trong transaction.
- Không dùng sleep hoặc locks ứng dụng dài.
- Có timeout/budget và metrics.
- Có retry/backoff đúng semantics.

## 27. Collection/index DDL trong transaction: tránh ngầm tạo collection

Spring Data documentation khuyến nghị chuẩn bị collections/indexes trước khi thực hiện transaction, vì việc tạo collection “on first use” có thể không tương thích với transaction workflow.

### 27.1. Nuance theo MongoDB server version

MongoDB server hiện đại hỗ trợ một số thao tác tạo collection/index trong transactions theo điều kiện, ví dụ:

- Không phải cross-shard write transaction.
- Index creation bị giới hạn trên new/empty collections.
- Explicit DDL trong transaction yêu cầu read concern phù hợp (thường `local`).

**Nhưng** Spring Data application không nên mặc định dựa vào dynamic DDL trong transaction. Pre-create collections/indexes giúp giảm rủi ro, ngăn metadata locks bất ngờ và tránh lỗi phân biệt phiên bản/topology.

### 27.2. Đừng bật auto-index creation tuỳ tiện trên production startup

Nếu ứng dụng vừa start vừa build indexes lớn, có thể tác động throughput/transaction behavior. Quản lý schema/index migrations thành change riêng, kiểm tra data/dup keys trước khi tạo unique index.

### 27.3. DB admin operations không nằm trong transaction thông thường

Không chạy user creation, replica config, backup/restore hoặc `explain` trong transaction nghiệp vụ. Một số thao tác không được server hỗ trợ trong transaction, một số có global effects không thể rollback kiểu document write.

## 28. Count, geo queries và transactional semantics

Một số helpers có behavior khác trong transaction.

### 28.1. count vs countDocuments

MongoDB `count` command dùng collection metadata và không phù hợp với transaction; Spring Data `MongoTemplate.count` chuyển sang aggregation `$match + $count` khi phát hiện active transaction theo tài liệu Spring Data.

Ví dụ:

~~~java
Query query = Query.query(Criteria.where("status").is("OPEN"));
long total = mongoTemplate.count(query, Order.class);
~~~

Trong transaction, cần hiểu query được triển khai khác so với estimated count/metadata count.

### 28.2. Geo near limitations

Các toán tử như `$near` / `$nearSphere` trong một số aggregation count paths bị hạn chế. Spring Data docs đề xuất thay bằng những biểu thức `$geoWithin`/`$center` hoặc `$centerSphere` khi phù hợp.

### 28.3. Không dựa vào count toàn database để chứng minh atomicity

Một test rollback tốt phải kiểm tra **cả hai collections liên quan** và một failure được chèn đúng điểm, không chỉ nhìn overall document count.

## 29. Transaction và Spring tests: vì sao test dễ đánh lừa?

### 29.1. Standalone container không đủ

Một integration test chỉ dùng standalone MongoDB có thể chạy repository CRUD nhưng transaction fail lúc mở. Testcontainers cho MongoDB nên chạy replica set (chẳng hạn URL từ `MongoDBContainer.getReplicaSetUrl()` ở version tương ứng).

### 29.2. Property name theo Boot version

Spring Boot 3.5:

~~~text
spring.data.mongodb.uri
~~~

Spring Boot 4.x:

~~~text
spring.mongodb.uri
~~~

Nếu `@DynamicPropertySource` inject sai key, test có thể kết nối localhost/default database ngoài ý muốn.

### 29.3. @DataMongoTest không quét mọi service/config

`@DataMongoTest` tập trung vào MongoTemplate, @Document, repositories. Configuration/Service ngoài slice có thể không được quét. Khi test transaction service, dùng `@SpringBootTest` hoặc `@Import` đúng beans và manager.

### 29.4. @Transactional trên test method có thể che dấu thiếu commit

Nếu test method được Spring tự rollback ở cuối, việc kiểm tra dữ liệu **trong cùng transaction** có thể cho thấy reads đã nhìn thấy writes, dù commit chưa từng được thử. Cần có test commit thật và đọc lại bằng session/transaction khác.

## 30. Integration test kiểm tra rollback giữa hai collections

Một workflow test:

~~~text
1. Chuẩn bị order PENDING
2. Gọi service qua Spring proxy
3. Trong service: write order, write outbox, inject exception
4. Transaction abort
5. Đọc từ session mới:
   - order vẫn PENDING
   - outbox event không tồn tại
~~~

### 30.1. Ví dụ thêm phương thức thử lỗi vào service lab

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void confirmThenFailForTest(String orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.setStatus("CONFIRMED");
    orders.save(order);

    outbox.save(new OutboxEvent(
        "test-order-confirmed:" + orderId,
        orderId,
        "OrderConfirmed",
        java.time.Instant.now()
    ));

    throw new IllegalStateException("injected failure");
}
~~~

Đặt method này trong `CheckoutService` của **test profile/lab**, không expose như production endpoint.

### 30.2. Test JUnit minh họa

~~~java
@SpringBootTest
class CheckoutTransactionIT {

    @Autowired CheckoutService checkout;
    @Autowired OrderRepository orders;
    @Autowired OutboxEventRepository outbox;

    @Test
    void rollbacksBothCollections() {
        String id = "order-test-rollback-001";

        orders.save(new Order(id, "tenant-test", "PENDING"));

        assertThrows(IllegalStateException.class,
            () -> checkout.confirmThenFailForTest(id));

        Order after = orders.findById(id).orElseThrow();
        assertEquals("PENDING", after.getStatus());

        assertFalse(outbox.existsById("test-order-confirmed:" + id));
    }
}
~~~

Trong class test thực tế cần imports JUnit/Spring Test, setup replica-set Testcontainers, property injection, fixtures cleanup và test isolation. **Không** thêm `@Transactional` lên test method trong ví dụ nếu mục tiêu là quan sát rollback qua một transaction khác.

### 30.3. Test commit thành công

Chạy `checkout.confirm(id)` trên order PENDING, rồi đọc lại order `CONFIRMED` và outbox ID đúng. Tiếp tục test concurrent confirmations, duplicated requests và transient failures.

### 30.4. Test khi operation thứ hai thất bại

Ví dụ pre-seed outbox với ID trùng; `outbox.save` có thể thay vì insert nếu dùng cùng ID, nên muốn kiểm tra duplicate key cần dùng `insert` hoặc custom uniqueness constraints rõ. Không giả định `save` luôn ném duplicate-key exception.

## 31. Testcontainers replica set: phác thảo cấu hình

Với Testcontainers/Spring Boot version phù hợp:

~~~java
// Pseudocode cấu trúc: imports và MongoDBContainer package
// phụ thuộc Testcontainers 1.x/2.x được dùng trong build.

@Testcontainers
@SpringBootTest
class MongoTransactionIntegrationTests {

    @Container
    static MongoDBContainer mongodb =
        new MongoDBContainer("mongo:8.0");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongodb::getReplicaSetUrl
        );
    }
}
~~~

Đoạn trên đặt property **Spring Boot 3.5**. Với Boot 4.x thay thành `spring.mongodb.uri`. Thêm dependencies `spring-boot-starter-test`, Testcontainers MongoDB/JUnit và MongoDB image/version được phê duyệt.

### 31.1. Vì sao dùng replica set URL?

Testcontainers MongoDB module có thể bật replica set cho container được tạo theo setup hỗ trợ. Transaction manager cần server hỗ trợ sessions/transactions, không chỉ port 27017.

### 31.2. Nếu Testcontainers 2.x đổi import/package?

Đọc javadocs và modules theo major version. Không copy import cũ rồi suy luận behavior tương đương.

### 31.3. Kiểm tra end-to-end, không chỉ context load

Một test “Spring context starts” chỉ chứng minh bean có thể tạo. Phải chạy một transaction có commit, một transaction rollback và kiểm tra dữ liệu ngoài transaction.

## 32. Quan sát transaction đang chạy

Sự cố transaction có thể thể hiện qua:

- Transaction aborts tăng.
- Commit duration p95/p99 tăng.
- Write conflicts.
- Long-running transactions.
- WiredTiger cache pressure.
- Driver retries và pool wait.
- Lock acquisition timeouts.
- Primary elections và network.
- Sharded transaction coordination costs.

### 32.1. serverStatus

Trên self-managed/Atlas environment có quyền phù hợp:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  transactions: s.transactions,
  connections: s.connections
});
~~~

Tên fields/metrics phụ thuộc MongoDB server version/tier. Các counters như commits/aborts tích lũy cần tính rates và xử lý process reset.

### 32.2. Current operations

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: true
    }
  },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      secs_running: 1,
      waitingForLock: 1
    }
  },
  { $limit: 20 }
]);
~~~

`$currentOp` cần privileges, không tự động expose full commands/PII. Không gọi `killOp` tùy tiện khi thấy transaction chậm.

### 32.3. Metrics ứng dụng

Nên thu:

~~~text
mongo_transaction_attempts_total
mongo_transaction_commits_total
mongo_transaction_aborts_total
mongo_transaction_commit_duration_seconds
mongo_transaction_retry_attempts_total
mongo_transaction_unknown_commit_results_total
~~~

Đây là **metric names minh họa do hệ thống tự instrument**, không phải fields mặc định Spring/MongoDB.

### 32.4. Dùng query shape thay full command

Không log dữ liệu khách hàng hoặc credentials để debug transaction. Ghi logical operation name, attempt, duration, error labels, incident ID và trace ID được bảo vệ.

## 33. Troubleshooting: phân loại lỗi đúng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Transaction numbers not allowed | Standalone mongod | `db.hello`, replica set |
| @Transactional không rollback | Thiếu manager hoặc sai manager | Spring beans, logs |
| Một repository rollback, repository khác không | Khác factory/client/session | Bean wiring |
| Self-invocation bỏ qua tx | Call trên `this` | Tách service proxy |
| @Async write vẫn commit riêng | ThreadLocal session không truyền | Tracing/thread |
| Raw driver write nằm ngoài tx | Không truyền session vào overload | Code path |
| Exception nhưng data vẫn commit | Checked exception/catch swallow | Rollback rules |
| UnexpectedRollbackException | Inner marked rollback-only | Propagation/error handling |
| TransactionTooLargeForCache | Transaction quá lớn/cache pressure | Server metrics |
| WriteConflict | Concurrent writes/long transaction | Trace, retry policy |
| UnknownTransactionCommitResult | Network/commit ambiguity | Error label, reconcile |
| Count command error | Native count không phù hợp tx | `countDocuments`/aggregation |
| Collection creation fail | Auto-create trong tx/topology | Pre-create collections |
| readPreference secondary fail | Transactions có reads cần primary | Transaction options |
| @Transactional(readOnly) vẫn tạo tx | Session binding theo manager | Đánh giá có cần tx |
| Transaction timeout | Server lifetime/commit/locks | Parameters, duration |
| Reactive writes ngoài tx | `subscribe` riêng hoặc `block` | Reactor chain/context |
| Multiple transaction managers | Annotation chọn nhầm manager | Name/Qualifier |
| Test pass nhưng production rollback lỗi | Test không dùng replica set/commit thật | Integration test |
| HTTP side effect không rollback | Ngoài MongoDB tx | Outbox/saga |

## 34. Phần rất dễ nhầm: cùng request không có nghĩa cùng session

Ví dụ controller:

~~~java
@PostMapping("/orders/{id}/confirm")
public ResponseEntity<Void> confirm(@PathVariable String id) {
    checkoutService.confirm(id);
    asyncPublisher.publish(id);
    return ResponseEntity.noContent().build();
}
~~~

`checkoutService.confirm` có transaction MongoDB riêng theo method boundary. `asyncPublisher.publish` diễn ra sau lời gọi, không cùng MongoDB session và có failure semantics độc lập.

### 34.1. Session gắn với manager, không gắn với URL

Một HTTP request có thể có hai transactional service calls:

~~~text
Controller
  |
  +--> serviceA.tx()  -> session S1, commit
  |
  +--> serviceB.tx()  -> session S2, commit
~~~

Không có automatic “request-wide transaction” kéo dài qua hai calls độc lập. Nếu muốn chung atomic boundary, cần một outer transactional service **đúng proxy/factory** bọc cả hai.

### 34.2. Session và connection pool

Session không đồng nghĩa một TCP connection tồn tại suốt vòng đời ứng dụng, nhưng transaction có các yêu cầu về connection/server routing. Đừng tự pin/đóng driver connections hoặc quản session trong layer Controller khi dùng Spring transaction manager.

### 34.3. API response trước commit?

Với Spring proxy, commit xảy ra trước khi lời gọi transactional method trở lại caller, nhưng nếu bạn tự spawn async job hoặc return reactive publisher thì thời gian thực thi/commit khác. Đừng trả HTTP 200 “đã xác nhận” trước khi atomic outcome thực sự được xác định.

## 35. So sánh các cách quản lý transaction

| Cách | Quản session | Ưu điểm | Rủi ro/cần chú ý |
|---|---|---|---|
| `@Transactional` + `MongoTransactionManager` | Spring thread-bound | Dễ đọc, gọn cho service | Proxy/self-invocation, exception rules |
| `TransactionTemplate` | Spring thread-bound | Ranh giới tường minh | Cần chọn manager đúng |
| `MongoTemplate.withSession` | Developer cung cấp | Kiểm soát session callback | Phải đóng session; transaction manual |
| Java Driver `withTransaction`/manual | Driver | Kiểm soát chi tiết và retry APIs | Phải truyền session trên mọi operation |
| `@Transactional` + Reactive manager | Reactor Context | Tích hợp WebFlux/Reactor | Publisher chain, subscribe semantics |
| `TransactionalOperator` | Reactor Context | Scope reactive rõ | Operations tách chain dễ thoát scope |

### 35.1. Lựa chọn mặc định

Ứng dụng Spring MVC dùng MongoRepository và cần một atomic business operation ngắn thường nên bắt đầu với `MongoTransactionManager` + public service `@Transactional` và test rollback thật.

Reactive WebFlux chọn reactive transaction manager/operator; không đưa blocking manager vào publisher chain.

### 35.2. Khi nào manual session phù hợp?

Khi cần causal consistency hoặc session-bound operations đặc biệt không được Spring manager biểu diễn trực tiếp. Nếu cần all-or-nothing nhiều repositories, declarative transaction thường rõ hơn.

## 36. Runbook cho sự cố transaction trong production

### Tình huống: checkout errors tăng sau failover

**Bước 1 — Ảnh hưởng:** đo tỷ lệ orders failed, p95, user impact, duplicate events và thời điểm bắt đầu.

**Bước 2 — Phân loại error:** `TransientTransactionError`, `UnknownTransactionCommitResult`, auth/TLS, writeConflict hoặc timeout.

**Bước 3 — Kiểm tra topology:** Atlas events/`rs.status`, primary availability, secondary lag và elections.

**Bước 4 — Kiểm tra runtime:** Transaction duration, retries, WiredTiger/cache/locks, pool waits, server selection.

**Bước 5 — Mitigate:** giảm concurrency, tạm dừng batch gây xung đột, bảo toàn idempotency keys. Không đổi writeConcern bừa bãi.

**Bước 6 — Verify:** commit success ratio về baseline, orders/outbox invariants đúng, không duplicate side effects.

**Bước 7 — RCA:** root cause có evidence, cải thiện retry policy/timeout/test failover và update runbook.

### 36.1. Nếu UnknownTransactionCommitResult tăng?

Không tự chạy lại mọi nghiệp vụ vô hạn. Cần implement commit retry/reconciliation theo driver guidelines và idempotent keys để phân biệt transaction đã commit nhưng response bị mất.

### 36.2. Khi primary không có majority

Transactions cần MongoDB deployment khỏe với majority/write concern phù hợp. Không hạ writeConcern để ép ghi khi không hiểu durability. Ưu tiên khôi phục topology và trạng thái ứng dụng an toàn.

## 37. Các nguyên tắc thiết kế cho hệ thống lớn

1. **Modeling trước transactions:** Nếu aggregate có thể embedded an toàn, một document atomic update có thể đơn giản hơn.
2. **Boundary theo use case:** Một service method ngắn bọc đúng các MongoDB writes.
3. **Đúng session/factory:** Tránh MongoClient tùy ý ngoài Spring.
4. **Idempotency:** Mỗi business request cần key để retry không nhân đôi side effects.
5. **Outbox:** Atomic intent to publish, asynchronous delivery.
6. **Không giữ transaction qua remote I/O.**
7. **Quyền tối thiểu:** DB user không cần `root` để giao dịch.
8. **Read/write concerns:** Chọn theo consistency/durability thực tế.
9. **Tách blocking và reactive semantics.**
10. **Test replica set thật và rollback ngoài transaction.**
11. **Monitor và alert:** Writes conflicts, abort rate, commit latency, unknown commit results.
12. **Có runbook:** Failover, DDL conflict, timeout, stale reads, duplicate requests.

## 38. Checklist triển khai production

### Topology và cấu hình

- [ ] MongoDB deployment hỗ trợ transactions.
- [ ] Replica set/sharded topology và FCV phù hợp.
- [ ] Java Driver/Spring Data/Spring Boot tương thích.
- [ ] MongoClient URI có TLS/replica set discovery đúng.
- [ ] Database users có quyền CRUD tối thiểu.
- [ ] Collections/indexes đã được tạo trước cho workflow.
- [ ] Có baseline transaction duration và throughput.

### Spring transaction wiring

- [ ] Khai báo `MongoTransactionManager`.
- [ ] Manager dùng cùng `MongoDatabaseFactory` với repositories/template.
- [ ] Chọn đúng manager khi có JDBC/JPA.
- [ ] `@Transactional` trên public service method.
- [ ] Invocation đi qua proxy.
- [ ] Không có self-invocation bỏ qua transaction.
- [ ] Exception/rollbackFor rõ ràng.
- [ ] Không catch-and-swallow.
- [ ] Kiểm thử annotation labels/options theo version.
- [ ] Không kỳ vọng `NESTED`/`REQUIRES_NEW` mặc nhiên hoạt động như JDBC savepoints.

### Session và reactive scope

- [ ] Không tự khởi tạo session thứ hai trong Spring tx.
- [ ] Không gọi raw driver methods thiếu ClientSession.
- [ ] Không chạy parallel operations trên cùng session/transaction.
- [ ] `@Async`/Executor không giả vờ chia sẻ ThreadLocal transaction.
- [ ] Reactive flow có `ReactiveMongoTransactionManager`.
- [ ] Không `block()`/`subscribe()` giữa transactional publisher.
- [ ] Manual sessions được close.
- [ ] Không lazy-load session-bound data sau khi close.

### Performance và reliability

- [ ] Transaction đủ ngắn, không remote HTTP/Kafka calls.
- [ ] Read concern/write concern/read preference được chọn chủ đích.
- [ ] Có bounded retries với backoff.
- [ ] Phân biệt transient error và uncertain commit.
- [ ] Có idempotency key/business reconciliation.
- [ ] Có outbox cho external event delivery quan trọng.
- [ ] Theo dõi commit/abort/write conflict/latency.
- [ ] Không log PII/credentials trong transaction diagnostics.

### Tests

- [ ] Integration tests dùng replica set.
- [ ] Test commit thành công trên hai collections.
- [ ] Test rollback sau lỗi thao tác thứ hai.
- [ ] Test đọc lại ngoài transaction.
- [ ] Test concurrent requests và conflict/retry.
- [ ] Test duplicate business request.
- [ ] Test failover/commit ambiguity khi có môi trường phù hợp.
- [ ] CI sử dụng database cô lập.
- [ ] Test @DataMongoTest/@SpringBootTest load đúng transaction bean.

## 39. Bài tập thực hành

Các bài thay đổi dữ liệu dùng **MongoDB lab replica set**. Không chạy kịch bản abort/killOp/failover trực tiếp trên production chỉ để thử.

### Bài 1 — Atomicity một document

Vì sao `updateOne` cập nhật nhiều fields của một document không nhất thiết cần transaction?

### Bài 2 — Multi-document invariant

Thiết kế một workflow cập nhật `orders` và `outbox` cần all-or-nothing. Điều gì xảy ra nếu không có transaction?

### Bài 3 — Session vs transaction

Một `ClientSession` được mở, ba operations được gọi nhưng không `startTransaction`. Chúng có tự trở thành một atomic unit không?

### Bài 4 — Replica set

Một standalone MongoDB chạy repository save bình thường nhưng transaction lỗi. Giải thích và cách tạo lab đúng.

### Bài 5 — MongoTransactionManager

Viết `@Bean MongoTransactionManager` inject `MongoDatabaseFactory`.

### Bài 6 — Same factory

Hai `MongoTemplate` có hai factories khác nhau nhưng cùng URI. Có chắc chúng nằm trong một transaction không?

### Bài 7 — Service @Transactional

Thêm `@Transactional(transactionManager="mongoTransactionManager")` vào service confirm order và xác định boundary.

### Bài 8 — Rollback runtime

Chèn `IllegalStateException` sau `orders.save` và trước commit. Kiểm tra kết quả bên ngoài transaction.

### Bài 9 — Checked exception

Một checked `BusinessRuleException` được ném trong service. Khi nào cần `rollbackFor`?

### Bài 10 — Swallowed exception

Catch `RuntimeException` rồi chỉ log. Vì sao có thể commit dữ liệu không mong muốn?

### Bài 11 — Proxy

`submit()` gọi `this.confirm()` trong cùng bean. Vì sao annotation ở confirm có thể không hoạt động?

### Bài 12 — Public method

Vì sao private/final transactional methods có thể không được proxy intercept?

### Bài 13 — REQUIRED

Service A đang có transaction và gọi service B `REQUIRED`. Có bao nhiêu transaction nếu cả hai dùng cùng manager/factory?

### Bài 14 — NESTED

Có thể rollback một phần transaction bằng MongoDB JDBC-style savepoint không?

### Bài 15 — Multiple managers

Một ứng dụng có JPA và MongoDB. Làm sao đảm bảo `@Transactional` chọn đúng manager?

### Bài 16 — Read-only

`@Transactional(readOnly=true)` có thể vẫn mở MongoDB session/transaction không? Nó có chặn writes ở server không?

### Bài 17 — Read preference

Vì sao không đặt `secondary` cho transaction có reads?

### Bài 18 — Consistency

So `ReadConcern.SNAPSHOT` và `WriteConcern.MAJORITY` về mục đích.

### Bài 19 — Transaction labels

Viết annotation có `mongo:readConcern=SNAPSHOT` và `mongo:maxCommitTime=PT1S` cho Spring Data version hỗ trợ.

### Bài 20 — Programmatic control

Viết `TransactionTemplate.executeWithoutResult` để cập nhật hai documents.

### Bài 21 — Manual session

Dùng `try(ClientSession session = ...)` và `withSession`; tại sao phải close session?

### Bài 22 — Raw driver

Một thao tác `collection.updateOne(filter, update)` nằm trong method dùng manual session. Vì sao nó có thể chạy ngoài transaction?

### Bài 23 — ThreadLocal

`@Async` gửi MongoDB write trên executor. Nó có mặc nhiên tham gia transaction của caller không?

### Bài 24 — Reactor Context

Vì sao reactive transaction dùng `ReactiveMongoTransactionManager` và không dùng ThreadLocal như imperative?

### Bài 25 — Reactive subscribe

Một service gọi `repository.save(doc).subscribe()` rồi trả `Mono.empty()`. Vì sao transaction có thể không bao operation?

### Bài 26 — TransactionalOperator

Dùng `.as(operator::transactional)` bao hai reactive writes trong cùng chain.

### Bài 27 — SessionSynchronization

Phân biệt `ON_ACTUAL_TRANSACTION`, `ALWAYS` và `NEVER`.

### Bài 28 — External side effects

MongoDB transaction abort sau khi HTTP payment gateway đã charge. Có tự refund không? Thiết kế compensation/outbox.

### Bài 29 — Commit ambiguity

Khi client nhận `UnknownTransactionCommitResult`, có nên luôn chạy lại toàn business method không?

### Bài 30 — Transient error

Phác thảo bounded retry cho `TransientTransactionError`, gồm idempotency và mỗi attempt mở transaction mới.

### Bài 31 — Transaction timeout

Transaction kéo dài 90 giây; server lifetime mặc định thường 60 giây. Những lỗi và resources cần theo dõi?

### Bài 32 — DDL trong transaction

Vì sao nên pre-create collections/indexes dù MongoDB server versions mới hỗ trợ một số DDL có điều kiện?

### Bài 33 — Count

Vì sao native `count` command khác `MongoTemplate.count` được chuyển sang aggregation trong transaction?

### Bài 34 — Integration test

Thiết kế JUnit test xác nhận order + outbox cùng rollback khi có lỗi thứ hai. Vì sao test phải đọc lại ngoài transaction?

### Bài 35 — Testcontainers

Một test container standalone có đủ để test `MongoTransactionManager` không? Cần replica set URL thế nào?

### Bài 36 — Observability

Chọn metrics commit success, abort, retry, write conflicts, pool waits và duration.

### Bài 37 — Concurrent confirmation

Hai requests xác nhận cùng một order. Dùng unique key, conditional update, optimistic lock và retries thế nào để tránh double effects?

### Bài 38 — Tổng hợp

Thiết kế API Spring Boot + MongoDB Atlas xác nhận order có outbox event, trong đó:

- MongoTransactionManager cùng factory.
- Transaction scope public service.
- MongoRepository + MongoTemplate.
- Majority write concern và snapshot read concern khi phù hợp.
- External publisher chạy sau commit.
- Retry xử lý transient và unknown commit.
- Idempotency key.
- Testcontainers replica set integration test.
- Observability và incident runbook.

## 40. Tổng kết

Một giao dịch MongoDB trong Spring Data chỉ đáng tin khi có **đúng transaction manager, đúng session, đúng phạm vi và đúng thao tác**:

- **MongoTransactionManager** tạo transaction và gắn `ClientSession` với thread trong luồng synchronous. `ReactiveMongoTransactionManager` dùng Reactor Context cho luồng reactive.
- **@Transactional** xác định boundary ở Spring proxy, không tự đảm bảo calls qua `this`, threads mới, raw clients khác hoặc external services tham gia.
- **MongoTemplate và repositories** cần cùng `MongoDatabaseFactory`/session. Raw driver calls phải nhận session tường minh khi thao tác ngoài sự quản lý của Spring Template.
- **Rollback** dựa trên exception propagation và rollback rules; checked exceptions/catch-swallow/self-invocation dễ gây hiểu nhầm.
- **Read/write concerns** và transaction options quyết định consistency/durability, và transactions có reads phải ưu tiên primary theo MongoDB server rules.
- **Timeout/retry:** giữ transaction ngắn; phân biệt transient failures và uncertain commit results, có idempotency và bounded retries.
- **External systems:** MongoDB không rollback HTTP, payment gateway hoặc Kafka; dùng outbox/saga và reconciliation.
- **Kiểm thử:** dùng replica set thật, xác minh commit lẫn rollback qua session khác; monitoring phải theo dõi abort, retry, conflicts và resource pressure.

Quy tắc thực hành đáng nhớ: **Transaction scope không phải HTTP request scope, session scope không phải toàn ứng dụng, và `@Transactional` không phải phép màu bao trùm mọi loại I/O.**

## Tài liệu tham khảo chính thức

- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Spring Data MongoDB — MongoTransactionManager API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/MongoTransactionManager.html)
- [Spring Data MongoDB — ReactiveMongoTransactionManager API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/ReactiveMongoTransactionManager.html)
- [Spring Data MongoDB — MongoTemplate API](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html)
- [Spring Data MongoDB — Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Boot — Data and MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Transactions on Sharded Clusters](https://www.mongodb.com/docs/manual/core/transactions-sharded-clusters/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Reactive Streams Driver — Transactions](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/write/transactions/)
