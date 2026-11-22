# Điều kiện hỗ trợ giao dịch và transaction manager

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot kết nối các hệ thống qua HTTP client, cơ sở dữ liệu, cache, message broker và adapter Spring Integration. Một nghiệp vụ có thể vừa cập nhật MongoDB, vừa đánh dấu sự kiện đã xử lý, tạo thông điệp outbox hoặc gọi HTTP downstream. Để đảm bảo tính đúng đắn của luồng tích hợp, cần phân biệt **thao tác MongoDB nào commit/rollback cùng nhau** và **tác động nào nằm ngoài transaction**.

Chương **MongoDB** giới thiệu một vấn đề quan trọng: **Điều kiện hỗ trợ giao dịch và transaction manager**. Không phải cứ thêm starter Spring Data MongoDB và gắn **@Transactional** là có giao dịch nhiều document.

Sau bài học, người học có thể:

1. Phân biệt atomic update trên một document và giao dịch nhiều document/collection.
2. Xác định yêu cầu về replica set, sharded cluster, phiên bản, featureCompatibilityVersion và ClientSession.
3. Cấu hình **MongoTransactionManager** cho imperative và **ReactiveMongoTransactionManager** cho reactive.
4. Viết service **@Transactional**, TransactionTemplate và TransactionalOperator đúng ranh giới session.
5. Thiết kế retry, idempotency, outbox, rollback và đối soát khi commit chưa chắc chắn.
6. Kiểm thử giao dịch với replica set thật, thay vì chỉ test CRUD trên standalone.

## 2. Một document đã có tính nguyên tử: khi nào không cần transaction?

MongoDB đảm bảo **một thao tác ghi trên một document là atomic**. Nhiều nghiệp vụ có thể được mô hình hóa thành một aggregate document, giảm nhu cầu transaction trên nhiều collection.

Ví dụ document đơn hàng:

~~~json
{
  "_id": "O-204",
  "status": "CREATED",
  "paymentVersion": 6,
  "paidAt": null
}
~~~

Một phép update có điều kiện kiểm tra version và ghi trạng thái trong một operation:

~~~java
Query onlyNewer = Query.query(
        Criteria.where("_id").is("O-204")
                .and("paymentVersion").lt(7L));

Update update = new Update()
        .set("status", "PAID")
        .set("paymentVersion", 7L)
        .set("paidAt", Instant.now());

UpdateResult result = mongoTemplate.updateFirst(
        onlyNewer, update, "orders");

boolean applied = result.getModifiedCount() == 1;
~~~

**MongoTemplate** thuộc Spring Data MongoDB. Các import đã được lược bỏ để tập trung vào thao tác. Filter và update thực hiện trên cùng document nên tránh được việc hai thread đọc, tính toán rồi cùng ghi theo giá trị cũ một cách thiếu kiểm soát.

| Nhu cầu | Hướng triển khai |
| --- | --- |
| Thay đổi các trường trong một order | Một lệnh update có điều kiện |
| Tăng/giảm counter trên một document | Toán tử **$inc**, có ràng buộc điều kiện nếu cần |
| Đồng thời cập nhật hai document hoặc collection | Cân nhắc multi-document transaction |
| Cập nhật order và ghi outbox cùng MongoDB | Có thể dùng MongoDB transaction |
| Ghi MongoDB rồi publish Kafka/HTTP | Transaction MongoDB **không bao phủ** broker hoặc HTTP |
| Xử lý hàng triệu bản ghi có checkpoint | Batch nhỏ, idempotency và bù trừ, không phải một transaction dài |

**Thiết kế aggregate và unique key trước khi thêm transaction.** Transaction hữu ích để giữ invariant nhiều document nhưng làm tăng chi phí điều phối, khóa/snapshot và xử lý lỗi.

## 3. Điều kiện MongoDB hỗ trợ transaction nhiều document

### 3.1. Topology và phiên bản

| MongoDB deployment | Hỗ trợ transaction? | Điều kiện |
| --- | --- | --- |
| **Standalone mongod** | **Không** | CRUD thành công không chứng minh transaction hoạt động |
| **Replica set** | **Có** | MongoDB 4.0+, FCV tối thiểu 4.0 |
| **Sharded cluster** | **Có** | MongoDB 4.2+, FCV tối thiểu 4.2 |
| **Managed MongoDB** | Tùy topology/tier | Xác nhận deployment thực tế, quyền và driver tương thích |

FCV là **featureCompatibilityVersion**, không phải chỉ số version trong tên Docker image. Một replica set đơn nút đã được **rs.initiate()** có thể phục vụ test giao dịch cục bộ, nhưng không mang tính chịu lỗi của replica set production nhiều nút.

MongoDB transaction được xây dựng trên **ClientSession**. Mọi operation trong một transaction phải được thực thi với đúng session đó; Spring Data sử dụng transaction manager để ràng buộc session với các operation phù hợp.

Ví dụ các lệnh kiểm tra ở công cụ quản trị:

~~~javascript
rs.status()

db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
})
~~~

**rs.status()** áp dụng tại thành viên replica set. Với sharded cluster/managed service, dùng công cụ topology tương ứng. Không cấp quyền admin cho tài khoản ứng dụng chỉ để chạy các kiểm tra vận hành này.

### 3.2. Kết nối và định tuyến đến primary

Ví dụ MongoDB URI dành cho replica set:

~~~text
mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/shop?replicaSet=rs-shop&readPreference=primary
~~~

Thêm **replicaSet** chính xác giúp driver nhận biết topology và chọn node thích hợp, đặc biệt khi transaction cần tới primary. Không nhúng credential production trong URI được commit hoặc trong log; nếu có username/password trong URI runtime, bảo vệ toàn bộ URI như một secret. Cấu hình TLS/hostname verification phải đúng môi trường.

Ngoài topology cần:

- **ClientSession** được driver hỗ trợ và kết nối tới server phiên bản tương thích.
- User có quyền đọc/ghi đúng collection, không cần quyền admin tùy tiện.
- Read concern, write concern và read preference phù hợp chính sách consistency.
- Thời gian transaction được giữ ngắn để tránh giữ snapshot/tài nguyên quá lâu.
- Collections và indexes được **chuẩn bị trước khi nhận traffic**, tránh phụ thuộc vào on-the-fly DDL trong transaction.

### 3.3. Những giới hạn không nên bỏ qua

- Transaction có thể gặp **write conflict** do nhiều request cạnh tranh trên cùng document.
- Transaction có thể bị server abort nếu quá thời gian hoặc thiếu tài nguyên.
- Operation bên trong cùng ClientSession phải được phối hợp theo thứ tự phù hợp, không tùy ý chạy đồng thời trên nhiều thread.
- Transaction trên sharded cluster có thể tốn thêm chi phí điều phối giữa các shard.
- Read concern **snapshot** không làm biến mất mọi write conflict hoặc tình huống dữ liệu cập nhật cạnh tranh.

## 4. Spring Boot tự cấu hình MongoDB nhưng chưa chắc có transaction manager

Với Maven có dependency management của Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Hoặc Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
}
~~~

Khi cấu hình kết nối hợp lệ, Boot có thể tạo **MongoClient**, **MongoDatabaseFactory**, **MongoTemplate**, cùng repository Spring Data. Tuy nhiên, theo Spring Data MongoDB, **nếu không có MongoTransactionManager trong application context thì không thể mặc định sử dụng transaction management cho các operation Mongo**. Tương tự, API reactive cần **ReactiveMongoTransactionManager**.

### 4.1. Phân biệt cấu hình Spring Boot 3.x và 4.x

Với **Spring Boot 3.x**, ví dụ:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Với **Spring Boot 4.x**, nhiều thuộc tính connection chuyển sang prefix **spring.mongodb**:

~~~yaml
spring:
  mongodb:
    uri: ${MONGODB_URI}
~~~

Đây là **hai cấu hình cho hai thế hệ phiên bản**, không nên đặt cả hai để mong framework tự chọn. **MONGODB_URI** được cấp qua environment hoặc secret manager; có thể chứa **replicaSet**, TLS và authentication phù hợp. Không log raw URI nếu có credential.

### 4.2. Luồng quản lý session của Spring

~~~mermaid
flowchart TD
    A["@Transactional / TransactionTemplate"] --> B["TransactionInterceptor"]
    B --> C["MongoTransactionManager"]
    C --> D["MongoDatabaseFactory"]
    D --> E["ClientSession gắn với thread"]
    F["MongoTemplate / MongoRepository"] --> E
    E --> G["MongoDB replica set hoặc sharded cluster"]
    H["Reactive @Transactional / TransactionalOperator"] --> I["ReactiveMongoTransactionManager"]
    I --> J["ClientSession trong Reactor Context"]
    K["ReactiveMongoTemplate"] --> J
    J --> G
~~~

**MongoTransactionManager** sử dụng cơ chế transaction context gắn với thread cho code đồng bộ. **ReactiveMongoTransactionManager** dùng Reactor Context; không thay thế qua lại hai manager này. Một **MongoTemplate** tự tạo với factory khác hoặc một driver client tự mở session ngoài Spring có thể không tham gia transaction của manager đã đăng ký.

## 5. Khai báo MongoTransactionManager cho imperative API

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement
public class MongoTransactionsConfiguration {

    @Bean("mongoTransactionManager")
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Với cấu hình này:

1. **MongoDatabaseFactory** phải là cùng factory mà MongoTemplate/repositories sử dụng.
2. **@EnableTransactionManagement** đảm bảo annotation transaction được xử lý trong cấu hình mẫu; Spring Boot có thể cung cấp hạ tầng advice tự động theo dependency/manager, nhưng cấu hình tường minh giúp dễ kiểm chứng.
3. Đặt tên bean **mongoTransactionManager** để service chỉ rõ manager cần sử dụng.
4. Nếu hệ thống dùng JDBC/JPA hoặc JMS cùng lúc, một **@Transactional** không chọn manager rõ ràng có thể chọn sai manager hoặc tạo cấu hình mơ hồ.

Ví dụ một service:

~~~java
@Service
public class MongoOrderService {
    private final MongoTemplate mongo;

    public MongoOrderService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void updateBothDocuments(...) {
        // Nhiều thao tác MongoDB được thực thi trong cùng session.
    }
}
~~~

Đoạn này là skeleton minh họa cách khai báo transaction boundary; phần tiếp theo sẽ triển khai một nghiệp vụ cụ thể.

### 5.1. Nhiều transaction managers không đồng nghĩa distributed transaction

| Transaction manager | Tài nguyên được quản lý |
| --- | --- |
| **MongoTransactionManager** | MongoDB session và những operation Mongo cùng factory |
| **ReactiveMongoTransactionManager** | Reactive MongoDB session trong Reactor Context |
| **JdbcTransactionManager** | JDBC DataSource tương ứng |
| **JmsTransactionManager** | JMS resource theo cấu hình ConnectionFactory |
| **KafkaTransactionManager** | Transaction producer/consumer Kafka theo hợp đồng cụ thể |

Một transaction Mongo không tự rollback được một update PostgreSQL hay một HTTP call. Dù service gọi một method **@Transactional** khác, điều đó cũng **không tự tạo XA hoặc two-phase commit** giữa các hệ thống.

## 6. Ví dụ: ghi dấu event và cập nhật order trong cùng transaction

Giả sử consumer nhận sự kiện **PaymentCaptured** và cần:

1. Ghi receipt **processed_payment_events** cho eventId để chống trùng.
2. Cập nhật document **orders** thành đã thanh toán.
3. Hoàn tác cả hai nếu một thao tác thất bại.

### 6.1. Chuẩn bị collections

~~~javascript
// Chạy ở migration/setup, không chạy bên trong transaction nghiệp vụ.
db.createCollection("orders")
db.createCollection("processed_payment_events")

// Mỗi _id có unique index mặc định.
~~~

Ứng dụng phải có collection và index trước khi mở transaction. Việc tự tạo collection lần đầu khi insert có những giới hạn trong transaction, tùy MongoDB và Spring Data version; không nên dựa vào nó tại production.

DTO và receipt:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

public record PaymentCaptured(
        String eventId, String orderId, long paymentVersion,
        Instant capturedAt) {
}

@Document("processed_payment_events")
public record ProcessedPaymentEvent(
        @Id String id, String orderId, Instant processedAt) {
}
~~~

Document trong **orders** có **_id = orderId** và các trường **status**, **paymentVersion**, **paidAt**. Mã sau dùng MongoTemplate trực tiếp để ngắn gọn:

~~~java
@Service
public class MongoPaymentProjector {
    private final MongoTemplate mongo;

    public MongoPaymentProjector(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void apply(PaymentCaptured event) {
        if (event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("Invalid event identity");
        }

        boolean processed = mongo.exists(
                Query.query(Criteria.where("_id").is(event.eventId())),
                ProcessedPaymentEvent.class);
        if (processed) {
            return; // Đã commit receipt của event này.
        }

        mongo.insert(new ProcessedPaymentEvent(
                event.eventId(), event.orderId(), Instant.now()));

        UpdateResult result = mongo.updateFirst(
                Query.query(Criteria.where("_id").is(event.orderId())),
                new Update()
                        .set("status", "PAID")
                        .set("paymentVersion", event.paymentVersion())
                        .set("paidAt", event.capturedAt()),
                "orders");

        if (result.getMatchedCount() != 1) {
            throw new IllegalStateException("Order not found");
        }
    }
}
~~~

Các import cho MongoTemplate, Query, Criteria, Update, UpdateResult, @Service và @Transactional được lược bỏ. **capturedAt** trong production phải được validate không null và đúng schema; eventId phải ổn định qua retry/redelivery. **RuntimeException** thoát khỏi service giúp Spring rollback cả receipt vừa insert và update nếu transaction thật sự hoạt động.

### 6.2. Race condition và unique key

Hai consumer có thể cùng thấy **processed=false**. Check rồi insert **không phải** phép khóa nguyên tử. Unique index trên **_id** mới đảm bảo hai receipt cùng eventId không thể cùng commit. Một transaction có thể bị **DuplicateKeyException** hoặc write conflict; khi đó cần rollback transaction lỗi và retry/đối soát từ **ngoài** boundary.

**Không catch DuplicateKeyException giữa transaction rồi return** để đánh dấu “duplicate đã xử lý”: transaction server có thể đã bị abort, và exception có thể biểu thị vấn đề khác. Khi caller redeliver sau một receipt đã commit, lần chạy mới sẽ thấy receipt và có thể no-op; với race chưa commit thì dùng retry có giới hạn.

### 6.3. Event đến đảo thứ tự

Nếu **hai eventId khác nhau** cùng cập nhật một order, receipt chống trùng không tự bảo vệ trước event version cũ. Cần dùng điều kiện version ở chính lệnh update, ví dụ:

~~~java
Query onlyNewer = Query.query(
        Criteria.where("_id").is(event.orderId())
                .and("paymentVersion").lt(event.paymentVersion()));

UpdateResult result = mongo.updateFirst(
        onlyNewer,
        new Update().set("paymentVersion", event.paymentVersion())
                .set("status", "PAID"),
        "orders");
~~~

Khi **matchedCount=0**, phải phân biệt order không tồn tại, event đến muộn hoặc dữ liệu đã ở version mới hơn. Nếu xem tất cả là lỗi retryable, broker có thể giao lại message cũ mãi mãi. Nếu những document cũ chưa có paymentVersion, cần migration hoặc quy tắc riêng.

### 6.4. Commit, ACK và redelivery

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant L as Listener
    participant TM as MongoTransactionManager
    participant M as MongoDB
    B->>L: PaymentCaptured evt-901
    L->>TM: begin transaction
    TM->>M: ClientSession
    L->>M: insert processed_payment_events
    L->>M: update orders
    alt Mongo commit thành công
        TM->>M: commitTransaction
        M-->>TM: success
        L-->>B: ACK theo adapter
    else Exception xảy ra
        TM->>M: abortTransaction
        L-->>B: failure / redelivery theo policy
    end
~~~

Nếu Mongo commit thành công nhưng tiến trình chết **trước khi broker ACK**, broker có thể gửi lại. Receipt theo eventId ngăn side effect Mongo lặp. **Broker ACK không nằm trong Mongo transaction**, nên vẫn cần chiến lược idempotency ở consumer, retry giới hạn và dead-letter cho event lỗi vĩnh viễn.

## 7. TransactionTemplate và quyền sở hữu session

Nếu muốn xác định ranh giới giao dịch ngay tại một đoạn lệnh, có thể dùng **TransactionTemplate** của Spring:

~~~java
@Configuration
public class MongoTemplateTransactionsConfiguration {
    @Bean("mongoTxTemplate")
    TransactionTemplate mongoTxTemplate(
            @Qualifier("mongoTransactionManager")
            PlatformTransactionManager manager) {
        return new TransactionTemplate(manager);
    }
}
~~~

~~~java
@Service
public class ProjectionBatchService {
    private final MongoTemplate mongo;
    private final TransactionTemplate tx;

    public ProjectionBatchService(
            MongoTemplate mongo,
            @Qualifier("mongoTxTemplate") TransactionTemplate tx) {
        this.mongo = mongo;
        this.tx = tx;
    }

    public void storeRelatedDocuments(
            Document first, Document second) {
        tx.executeWithoutResult(status -> {
            mongo.insert(first, "projection_a");
            mongo.insert(second, "projection_b");
        });
    }
}
~~~

**Document** ở đây là **org.bson.Document** và dùng để minh họa; production nên có DTO/entity và schema rõ ràng. Collections đã được tạo trước khi transaction chạy. Nếu một insert ném lỗi khiến transaction rollback, cả hai insert không được commit.

**TransactionTemplate phải dùng MongoTransactionManager**, không được vô tình inject manager JDBC. Khi dùng MongoTemplate và transaction manager cùng factory, Spring quản lý ClientSession cho các operation trong callback.

Spring Data MongoDB cũng cho phép **MongoTemplate.withSession(...)** để tự quản lý session với Java driver, nhưng nếu đã có Spring transaction abstraction, không nên tự gọi **session.startTransaction/commitTransaction** chồng lên @Transactional. Việc mở, đóng session thủ công và exception handling sẽ phức tạp hơn mà không tạo thêm tính nguyên tử cho hệ thống bên ngoài MongoDB.

### 7.1. Proxy và self-invocation

Ví dụ sau dễ gây hiểu nhầm:

~~~java
@Service
class BrokenExample {

    void handle(PaymentCaptured event) {
        apply(event); // Self-invocation, có thể bỏ qua proxy transaction.
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void apply(PaymentCaptured event) {
        // ...
    }
}
~~~

Trong cấu hình giao dịch dựa trên Spring proxy, lời gọi **cùng đối tượng** có thể không đi qua TransactionInterceptor. Đặt method transaction trong bean riêng và gọi qua Spring-managed proxy, hoặc sử dụng TransactionTemplate. Không chỉ dựa vào annotation hiện diện trong source code để suy ra transaction đã chạy.

## 8. ReactiveMongoTransactionManager và Reactor Context

Nếu ứng dụng sử dụng WebFlux/reactive MongoDB, cần dùng starter và transaction manager reactive phù hợp:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
~~~

Đăng ký manager:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ReactiveMongoTransactionsConfiguration {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

**ReactiveMongoTransactionManager** dùng **Reactor Context** để truyền ClientSession. Nó không dùng ThreadLocal theo cách của imperative MongoTransactionManager; không thay manager đồng bộ vào reactive pipeline rồi nghĩ các operation sẽ tự tham gia.

### 8.1. @Transactional trên phương thức trả Mono

~~~java
@Service
public class ReactiveMongoPaymentProjector {
    private final ReactiveMongoTemplate mongo;

    public ReactiveMongoPaymentProjector(ReactiveMongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(
            transactionManager = "reactiveMongoTransactionManager")
    public Mono<Void> apply(PaymentCaptured event) {
        Query receiptQuery = Query.query(
                Criteria.where("_id").is(event.eventId()));

        return mongo.exists(
                    receiptQuery, ProcessedPaymentEvent.class)
                .flatMap(processed -> {
                    if (processed) {
                        return Mono.<Void>empty();
                    }

                    return mongo.insert(new ProcessedPaymentEvent(
                                    event.eventId(),
                                    event.orderId(),
                                    Instant.now()))
                            .then(mongo.updateFirst(
                                    Query.query(Criteria.where("_id")
                                            .is(event.orderId())),
                                    new Update().set("status", "PAID")
                                            .set("paymentVersion",
                                                    event.paymentVersion()),
                                    "orders"))
                            .flatMap(result ->
                                    result.getMatchedCount() == 1
                                    ? Mono.<Void>empty()
                                    : Mono.error(
                                            new IllegalStateException(
                                                    "Order not found")));
                });
    }
}
~~~

Đoạn này giả định DTO, collections và factory đã nêu ở phần trước. Thực tế cần validate dữ liệu và xử lý version cũ. Một **Mono** là mô tả thực thi: transaction và các lệnh mạng chỉ chạy khi có subscription. Nếu một test gọi method rồi bỏ publisher, không có bằng chứng transaction đã chạy.

**Không dùng subscribe() thủ công bên trong method transaction rồi return sớm.** Subscription tách rời có thể chạy ngoài Reactor Context của transaction; method return có thể hoàn tất khi side effect còn đang chạy.

### 8.2. TransactionalOperator

Khi cần khai báo phạm vi bằng code:

~~~java
@Bean("mongoOperator")
TransactionalOperator mongoOperator(
        @Qualifier("reactiveMongoTransactionManager")
        ReactiveTransactionManager manager) {
    return TransactionalOperator.create(manager);
}
~~~

~~~java
Mono<Void> work = reactiveMongoTemplate
        .insert(new ProcessedPaymentEvent(
                "evt-901", "O-204", Instant.now()))
        .then(reactiveMongoTemplate.updateFirst(
                Query.query(Criteria.where("_id").is("O-204")),
                new Update().set("status", "PAID"),
                "orders"))
        .then()
        .as(mongoOperator::transactional);
~~~

Với **.as(mongoOperator::transactional)**, những publisher upstream nằm trong phạm vi transactional operator. Publisher tạo ra ở một subscription khác hoặc được gọi sau operator sẽ không tự gia nhập transaction đó.

### 8.3. Không chạy đồng thời nhiều operation trên một session

MongoDB driver yêu cầu operation trong transaction được thực thi theo thứ tự thích hợp. Đừng dùng **flatMap** với concurrency lớn để ghi đồng thời trên **cùng một ClientSession**:

~~~java
// Không nên dùng khi cùng một transaction có nhiều write song song:
Flux.fromIterable(events)
        .flatMap(event -> reactiveMongoTemplate.insert(event));

// Nếu số lượng nhỏ và phải tuần tự trong một transaction:
Flux.fromIterable(events)
        .concatMap(event -> reactiveMongoTemplate.insert(event));
~~~

Các biểu thức chỉ minh họa thứ tự thực thi, không phải một ví dụ đầy đủ về cấu hình transaction. Với lượng dữ liệu lớn, chia thành **nhiều transaction nhỏ** có checkpoint và idempotency thay vì giữ một session cho toàn bộ stream.

**Không gọi block() trên WebFlux event loop** và không cho rằng MongoTemplate đồng bộ sẽ tự dùng ClientSession của ReactiveMongoTransactionManager.

## 9. Read concern, write concern và transaction options

MongoDB transaction có những lựa chọn ảnh hưởng tới dữ liệu quan sát và thời điểm commit:

| Tùy chọn | Vai trò | Cân nhắc |
| --- | --- | --- |
| **readConcern** | Mức nhất quán của dữ liệu được đọc | **snapshot** phù hợp nhiều bài toán đọc trong transaction |
| **writeConcern** | Yêu cầu acknowledgement của write/commit | **majority** tăng mức đảm bảo durability so với chỉ một replica |
| **readPreference** | Cách driver chọn node đọc | Transaction có quy tắc định tuyến đến primary phù hợp |
| **maxCommitTime** | Giới hạn thời gian thao tác commit | Hết hạn không luôn chứng minh commit đã thất bại |
| **transaction lifetime** | Thời gian sống transaction trên server | Transaction quá dài có thể bị abort |

Spring Data MongoDB hỗ trợ transaction labels trong những phiên bản có **MongoTransactionOptionsResolver**:

~~~java
@Transactional(
        transactionManager = "mongoTransactionManager",
        label = {
                "mongo:readConcern=SNAPSHOT",
                "mongo:writeConcern=MAJORITY",
                "mongo:maxCommitTime=PT2S"
        })
public void processPayment(PaymentCaptured event) {
    // Các operation Mongo tham gia cùng transaction.
}
~~~

Nếu Spring Data version không hỗ trợ option labels này, cấu hình **TransactionOptions** qua MongoTransactionManager và API tương ứng. Không dùng label tùy ý rồi mặc định nó được chuyển thành setting của MongoDB.

**readConcern snapshot không loại bỏ write conflict.** Một transaction có thể đọc snapshot hợp lệ nhưng bị abort khi ghi trùng với transaction khác. Bảo vệ bằng unique index, version predicate và retry có giới hạn.

**@Transactional(readOnly=true)** có thể vẫn mở ClientSession/transaction theo manager, không nên bọc mọi query đọc đơn giản vào transaction chỉ vì lo thiếu consistency.

## 10. Giới hạn vận hành của transaction MongoDB

### 10.1. Giữ transaction ngắn

MongoDB có tham số **transactionLifetimeLimitSeconds**. Mặc định phổ biến trong nhiều triển khai là **60 giây**, nhưng giá trị thực tế tùy cấu hình server hoặc managed service. Transaction quá hạn có thể bị abort; trong thời gian chạy nó giữ snapshot/tài nguyên và tăng khả năng write conflict.

Không giữ Mongo transaction trong lúc:

- Gọi HTTP downstream chậm hoặc chờ Retry-After dài.
- Chờ broker xác nhận, chờ người dùng phê duyệt hoặc chờ một job async nhiều phút.
- Quét hàng triệu document hoặc giữ cursor lâu không kiểm soát.
- Backoff retry nhiều lần mà vẫn giữ cùng transaction mở.

Nên chuẩn bị dữ liệu/validate trước khi mở transaction; thực hiện những thao tác Mongo atomic nhanh; gửi notification hoặc publish broker sau commit bằng cơ chế outbox/recovery.

### 10.2. Collections và indexes phải được chuẩn bị

Đừng dựa vào việc Spring Data tự tạo collection trong lần insert đầu tiên **bên trong transaction**. Khả năng DDL trong transaction phụ thuộc MongoDB version/topology và integration cụ thể; đảm bảo collections/indexes đã được tạo từ migration hoặc bootstrap có kiểm soát.

~~~javascript
// Khâu chuẩn bị ngoài transaction:
db.createCollection("orders")
db.createCollection("processed_payment_events")
db.createCollection("outbox_events")
db.outbox_events.createIndex({ status: 1, createdAt: 1 })
~~~

Thực tế migration phải kiểm tra tồn tại để chạy lặp an toàn; các lệnh trên minh họa mục tiêu, không phải script production idempotent hoàn chỉnh.

### 10.3. Không dùng transaction làm cơ chế batch throughput

Multi-document transaction có chi phí điều phối và ghi oplog, đặc biệt khi đi qua nhiều shard. Nó không tự tăng hiệu suất ghi hàng loạt. Mỗi BSON document vẫn phải tuân theo giới hạn kích thước document; transaction cũng có giới hạn runtime/tài nguyên tùy server.

Với ingest lớn, dùng batch nhỏ, atomic upsert, checkpoint, retry có giới hạn và đối soát; nếu nghiệp vụ cần invariant xuyên batch, cân nhắc thiết kế dữ liệu hoặc workflow có trạng thái thay vì một transaction mở hàng phút.

## 11. Lỗi, retry và kết quả commit không chắc chắn

Transaction có thể lỗi khi bắt đầu session, đọc, ghi, hoặc commit:

~~~mermaid
flowchart TD
    A["Bắt đầu transaction"] --> B["Ghi document A"]
    B --> C["Ghi document B"]
    C --> D["commitTransaction"]
    B -->|"Exception"| E["abort/rollback"]
    C -->|"Write conflict/duplicate"| E
    D -->|"Commit xác nhận"| F["Bước tiếp theo/ACK"]
    D -->|"Kết quả không chắc chắn"| G["Kiểm tra error labels / đối soát"]
    G --> H{"Phục hồi"}
    H -->|"Retry commit theo driver protocol"| I["Xác minh commit outcome"]
    H -->|"Retry toàn transaction nếu an toàn"| A
~~~

### 11.1. Phân loại lỗi

| Nhóm | Ý nghĩa | Chính sách |
| --- | --- | --- |
| Standalone không hỗ trợ transaction | Topology không đáp ứng | Sửa deployment; không retry business |
| **TransientTransactionError** | Lỗi giao dịch có thể tạm thời | Retry **cả transaction** khi operation idempotent |
| **UnknownTransactionCommitResult** | Chưa biết commit có thành công hay chưa | Theo protocol retry commit/đối soát; không tạo side effect khác ngay |
| DuplicateKeyException | Vi phạm unique receipt/index | Phân biệt duplicate nghiệp vụ và race/conflict |
| Write conflict | Cạnh tranh cập nhật | Backoff/retry giới hạn, giảm thời gian transaction |
| Validation/mapping error | DTO/schema không hợp lệ | Sửa dữ liệu/code; không retry vô hạn |
| Network/timeout | Kết quả operation có thể chưa xác định | Đánh giá phase, error labels và trạng thái nguồn sự thật |

Driver có thể gắn **error labels** cho exception; Spring Data chuyển đổi một số lỗi sang **DataAccessException**. Khi phân loại retry, cần xem root cause/driver labels và kiểm thử với phiên bản thực tế. **@Transactional không tự cung cấp retry policy đúng cho mọi lỗi**.

### 11.2. Retry đúng ranh giới

Nếu ghi B trong transaction lỗi transient, retry mỗi lệnh B bên ngoài transaction cũ có thể làm sai invariant. Thông thường cần rollback transaction cũ rồi retry lại **toàn bộ hàm nghiệp vụ** trong transaction mới. Nếu **commit chưa rõ kết quả**, việc chạy lại toàn bộ nghiệp vụ ngay có thể tạo duplicate: phải dùng receipt có unique index, kiểm tra trạng thái hoặc retry commit theo hướng dẫn driver.

**Không bắt mọi RuntimeException rồi return bình thường bên trong @Transactional.** Nếu transaction còn hợp lệ, Spring có thể commit những thay đổi trước lỗi; nếu server đã abort, commit sau đó lại lỗi khó hiểu. Cho exception thoát ra ranh giới để rollback hoặc đánh dấu rollback-only có chủ đích.

### 11.3. Checked exception và rollback rule

Theo cấu hình Spring thường dùng, runtime exception/Error gây rollback theo mặc định; checked exception cần được xác định riêng nếu muốn rollback:

~~~java
@Transactional(
        transactionManager = "mongoTransactionManager",
        rollbackFor = ExternalContractException.class)
public void process(...) throws ExternalContractException {
    // Đoạn này là skeleton minh họa rollback rule.
}
~~~

**ExternalContractException** là kiểu exception do ứng dụng định nghĩa. Chính sách rollback có thể được điều chỉnh ở cấp framework/ứng dụng; cần kiểm thử hành vi thật.

## 12. MongoDB transaction và tích hợp qua broker/HTTP

Một transaction Mongo **không bao phủ** Kafka, RabbitMQ, JMS, HTTP, Redis hoặc JDBC khác chỉ vì code nằm trong một method @Transactional.

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void saveAndPublish(...) {
    mongoTemplate.insert(...);
    kafkaTemplate.send(...); // Không thuộc transaction MongoDB.
    // Một lời gọi HTTP cũng không tự rollback khi Mongo rollback.
}
~~~

Đây là **pseudocode ranh giới**, không phải code production hoàn chỉnh. Nếu event được broker nhận nhưng Mongo commit thất bại, downstream thấy một sự kiện không có dữ liệu nguồn tương ứng. Nếu Mongo commit xong rồi process chết trước publish, event có thể bị mất.

### 12.1. Transactional outbox trong MongoDB

Phương án thường dùng là **cập nhật business document và chèn outbox document trong cùng transaction Mongo**, rồi relay riêng chuyển outbox sang broker:

~~~mermaid
flowchart TD
    A["Business command"] --> B["Mongo transaction"]
    B --> C["Update order"]
    B --> D["Insert outbox event"]
    C --> E{"Mongo commit"}
    D --> E
    E -->|"Đã commit"| F["Outbox relay"]
    F --> G["Kafka/RabbitMQ/JMS"]
    F -->|"Publish lỗi"| H["Retry, backoff, checkpoint"]
    H --> F
    G --> I["Consumer có idempotency"]
~~~

Outbox document:

~~~java
@Document("outbox_events")
public record OutboxEvent(
        @Id String eventId,
        String eventType,
        String aggregateId,
        Instant createdAt,
        String status) {
}
~~~

Code service chỉ minh họa thao tác trong transaction:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void markPaidAndQueueEvent(PaymentCaptured event) {
    UpdateResult result = mongo.updateFirst(
            Query.query(Criteria.where("_id").is(event.orderId())),
            new Update().set("status", "PAID"),
            "orders");

    if (result.getMatchedCount() != 1) {
        throw new IllegalStateException("Order not found");
    }

    mongo.insert(new OutboxEvent(
            event.eventId(),
            "OrderPaid",
            event.orderId(),
            Instant.now(),
            "PENDING"));
}
~~~

Ví dụ dùng **eventId làm _id outbox** để dễ bảo vệ tính duy nhất, nhưng ở ứng dụng thật cần thêm quy tắc version/out-of-order và idempotency. Relay phải xử lý tình huống **publish thành công nhưng cập nhật trạng thái SENT thất bại**, có thể dẫn đến publish lặp; consumer cần chống trùng theo eventId.

MongoDB **change streams** có thể hỗ trợ relay phát hiện outbox document mới trên replica set/sharded cluster, nhưng resume token, mất kết nối, replay và duplicate cần được xử lý; change stream không tự tạo broker publish exactly-once.

### 12.2. Nếu còn PostgreSQL hoặc Redis

MongoTransactionManager chỉ quản lý session Mongo tương ứng. JDBC transaction manager chỉ quản lý DataSource của nó. Khi workflow đi qua nhiều loại backend, dùng **outbox/inbox, saga, idempotency, retry, checkpoint và reconciliation** thay vì giả định một @Transactional tạo XA phân tán.

## 13. Kiểm thử giao dịch trên replica set thật

Mock MongoTemplate hoặc một MongoDB standalone không xác minh được rollback nhiều document. Với Spring Boot, test tích hợp nên dùng MongoDB replica set thật, chẳng hạn **Testcontainers MongoDB module**.

Ví dụ cho Spring Boot **3.x**, với Testcontainers + JUnit 5:

~~~java
@Testcontainers
@SpringBootTest
class MongoPaymentTransactionIT {

    @Container
    static MongoDBContainer mongo =
            new MongoDBContainer("mongo:7.0");

    @DynamicPropertySource
    static void mongoUri(DynamicPropertyRegistry properties) {
        properties.add(
                "spring.data.mongodb.uri",
                () -> mongo.getReplicaSetUrl("shop"));
    }

    @Autowired
    MongoTemplate template;

    @Autowired
    MongoPaymentProjector projector;

    @BeforeEach
    void prepare() {
        if (!template.collectionExists("orders")) {
            template.createCollection("orders");
        }
        if (!template.collectionExists("processed_payment_events")) {
            template.createCollection("processed_payment_events");
        }
        template.getCollection("orders").deleteMany(new Document());
        template.getCollection("processed_payment_events")
                .deleteMany(new Document());
    }

    @Test
    void receiptIsRolledBackWhenOrderIsMissing() {
        PaymentCaptured event = new PaymentCaptured(
                "evt-001", "missing-order", 1L, Instant.now());

        assertThrows(IllegalStateException.class,
                () -> projector.apply(event));
        assertFalse(template.exists(
                Query.query(Criteria.where("_id").is("evt-001")),
                ProcessedPaymentEvent.class));
    }
}
~~~

Các import JUnit, Testcontainers, Spring Test, BSON, Mongo và Instant được lược bỏ. Cần khai báo dependency Testcontainers/JUnit phù hợp, Docker chạy được trong CI; image **mongo:7.0** là ví dụ, nên quản lý version và cập nhật định kỳ. **MongoDBContainer** được thiết kế để cung cấp URI replica set dùng được cho transaction; xác minh API **getReplicaSetUrl(...)** theo version Testcontainers.

Với **Spring Boot 4.x**, property test phải đổi sang **spring.mongodb.uri**. Test slice **@DataMongoTest** tập trung vào template/repository và có thể không scan service hoặc transaction config tùy biến; dùng **@SpringBootTest** hoặc **@Import** phù hợp khi cần xác minh một service @Transactional thật.

### 13.1. Ma trận kiểm thử

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Replica set + manager chính xác | Hai write cùng commit hoặc rollback |
| MongoDB standalone | Không thể coi transaction nhiều document là thành công |
| Order không tồn tại | Receipt insert bị rollback |
| Event lặp cùng eventId | Receipt unique chặn side effect lặp |
| Hai consumer đồng thời | Race được xử lý bằng unique key và retry/đối soát |
| Version cũ đến sau version mới | Không làm order giảm version |
| Runtime/checked exception | Rollback theo chính sách đã chọn |
| Write conflict | Retry có giới hạn, không nhân đôi side effect |
| Commit result unknown | Không phán đoán thất bại; có recovery theo receipt |
| Reactive publisher phát lỗi | Transaction rollback và không có write còn sót |
| Broker redelivery sau Mongo commit | Business state vẫn idempotent |
| Outbox relay crash sau publish | Consumer vẫn chống trùng |
| Mongo failover/network outage | Không swallow lỗi và không báo ACK sớm |

Với reactive, phải **subscribe** để kiểm tra effect:

~~~java
StepVerifier.create(reactiveProjector.apply(event))
        .verifyComplete();
~~~

Chỉ tạo Mono rồi bỏ qua không chứng minh transaction đã bắt đầu. Với test lỗi, dùng **expectError(...)** và đọc lại collection để chứng minh rollback thay vì chỉ assert exception.

## 14. Quan sát và vận hành MongoDB transaction

| Metric/tín hiệu | Ý nghĩa |
| --- | --- |
| **transaction started/committed/aborted** | Tỷ lệ commit và rollback |
| **transaction duration p95/p99** | Transaction chậm, nguy cơ hết lifetime |
| **write conflict / duplicate key** | Cạnh tranh và idempotency |
| **unknown commit result** | Cần đối soát, không coi luôn là rollback |
| **connection pool pending / timeout** | Pool bị giữ lâu hoặc quá tải |
| **Mongo command latency** | Query/update thiếu index hoặc primary chậm |
| **outbox pending / oldest age** | Relay bị kẹt sau commit Mongo |
| **broker redelivery / duplicate event** | Đánh giá tác động của ACK/at-least-once |

Các tên trên là **định nghĩa metric đề xuất**, không phải tất cả đều có sẵn trong Spring Boot. Spring Boot Actuator, Micrometer, MongoDB driver/server exporter và Spring Integration tracing cho những tín hiệu khác nhau. Không dùng **eventId, orderId, tenantId, MongoDB URI chứa password** làm metric tag có cardinality cao.

Một trace có ích:

~~~text
Message delivery evt-901
  → Mongo transaction begin
     → insert processed_payment_events
     → update orders
  → Mongo commit success
  → broker ACK
~~~

Phân biệt **Mongo commit** với **ACK broker** trong log/trace. Nếu broker redelivery vì mất ACK, metric duplicate tăng nhưng Mongo transaction có thể đã commit trước đó.

Trong production, theo dõi transaction dài, index, currentOp, khả năng primary failover, pool pressure và log Mongo với quyền đọc phù hợp. Không bật full payload/credential logging chỉ để debug.

## 15. Sai lầm thường gặp

**“MongoDB luôn cần @Transactional để ghi an toàn.”** Một thao tác trên một document đã atomic; nhiều trường hợp dùng conditional update là đủ.

**“Có spring-boot-starter-data-mongodb là tự động có Mongo transaction.”** Không đủ. Phải có manager Mongo được cấu hình và topology hỗ trợ transaction.

**“Standalone chạy CRUD là đủ để test transaction.”** Sai. Test giao dịch nhiều document cần replica set hoặc sharded cluster.

**“@Transactional tự chọn Mongo dù ứng dụng có JDBC manager.”** Không bảo đảm; cần chọn manager đúng và test thực tế.

**“MongoTransactionManager rollback được HTTP hoặc Kafka.”** Sai. Nó chỉ quản lý những Mongo operation thuộc session tương ứng.

**“exists rồi insert là chống trùng an toàn dưới concurrency.”** Cần unique key thực sự và xử lý race.

**“Catch DuplicateKeyException trong transaction rồi return luôn an toàn.”** Transaction có thể đã abort; xử lý conflict ở ngoài boundary hoặc theo protocol rõ.

**“Snapshot read loại bỏ write conflict.”** Không; transaction có thể abort khi hai write cạnh tranh.

**“Reactive transaction dùng ThreadLocal như imperative.”** Sai. Reactive session đi theo Reactor Context và subscription.

**“Retry toàn nghiệp vụ khi commit timeout luôn an toàn.”** Có thể commit trước khi timeout; phải phân biệt unknown commit và idempotency.

**“Transaction dài giúp batch hàng triệu document hiệu quả hơn.”** Thường làm tăng rủi ro lock/snapshot, abort và pool exhaustion.

**“Tạo collection trong transaction lúc xử lý đầu tiên là mặc định ổn.”** Phụ thuộc version/topology; chuẩn bị schema trước.

**“Đã commit Mongo thì broker cũng nhận event.”** Chỉ đúng nếu có một giao thức tích hợp phù hợp; thông thường cần outbox/recovery.

## 16. Checklist trước khi triển khai

1. Xác định invariant nào phải được giữ qua **nhiều document**; ưu tiên atomic single-document update khi đủ.
2. Xác nhận MongoDB topology, phiên bản/FCV, quyền, read/write concern và TLS.
3. Không dùng standalone để kiểm chứng transaction production.
4. Chọn đúng property MongoDB theo Spring Boot 3.x hoặc 4.x và cấu hình replicaSet rõ.
5. Đăng ký **MongoTransactionManager** hoặc **ReactiveMongoTransactionManager** với đúng factory.
6. Chỉ rõ tên transaction manager nếu service có cả Mongo/JDBC/JMS.
7. Đặt boundary tại service qua Spring proxy/TransactionTemplate/TransactionalOperator; tránh self-invocation.
8. Pre-create collections và indexes, đặc biệt receipt/outbox unique keys.
9. Giữ transaction ngắn; không chờ HTTP, broker hoặc backoff bên trong.
10. Với reactive, không tự subscribe, không block và không chạy nhiều operation song song cùng session.
11. Retry theo error labels và ngân sách; phân biệt transient error với unknown commit.
12. Bảo vệ side effect bằng eventId, version, idempotency và outbox/inbox.
13. Test rollback bằng replica set thật, thêm test concurrency, redelivery và crash sau commit.
14. Theo dõi transaction latency, abort, write conflict, pool và outbox backlog, không lộ bí mật.

**Kết luận:** multi-document transaction MongoDB bảo vệ một nhóm thao tác trong **cùng MongoDB session** khi server hỗ trợ và Spring quản lý đúng manager. Nó là một công cụ quan trọng, nhưng không thay thế cho **mô hình dữ liệu tốt, idempotency, outbox, retry có điều kiện, kiểm thử và observability** của toàn bộ luồng tích hợp.

## Tài liệu tham khảo

- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): hỗ trợ giao dịch, topology, FCV và atomicity.
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/): runtime limit và lưu ý về tài nguyên.
- [MongoDB Manual — startTransaction](https://www.mongodb.com/docs/manual/reference/method/session.starttransaction/): ClientSession, retry và commit.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): MongoTransactionManager, ReactiveMongoTransactionManager, TransactionTemplate, TransactionalOperator và option labels.
- [Spring Boot — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/reference/data/nosql.html): MongoDB client, properties và auto-configuration.
- [Spring Boot 4 Migration Guide — MongoDB properties](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): thay đổi prefix spring.mongodb.
- [Spring Boot 3.5 — Auto-configured Data MongoDB Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): phạm vi test slice @DataMongoTest.
- [Testcontainers — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): MongoDBContainer và replica set trong integration test.
