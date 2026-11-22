# Rollback, exception và thời điểm commit

> **Chương:** Session và giao dịch  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Hiểu chính xác thời điểm transaction bắt đầu, khi nào MongoDB commit/abort, exception nào khiến Spring rollback, vì sao `catch`/self-invocation gây commit ngoài ý muốn, cách dùng `rollbackFor`/`setRollbackOnly` và `TransactionTemplate`; xử lý lỗi commit không xác định, retry an toàn, side effect ngoài database và kiểm thử bằng MongoDB replica set.

## 1. Vấn đề: method chạy xong chưa có nghĩa đã commit

Giả sử ứng dụng cần thực hiện hai ghi khi duyệt một đơn hàng:

1. Đổi trạng thái order từ `PENDING` sang `APPROVED`.
2. Ghi một outbox event `OrderApproved` để hệ thống khác xử lý sau.

Nếu cả hai thao tác phải **cùng thành công hoặc cùng không có hiệu lực**, transaction là một công cụ phù hợp. Nhưng lập trình viên thường hiểu sai:

~~~java
@Transactional
public void approveOrder(String orderId) {
    updateOrder(orderId);
    insertOutboxEvent(orderId);
    // Chạy hết tới đây có nghĩa đã commit? CHƯA CHẮC.
}
~~~

Khi method được gọi **qua Spring transactional proxy**, tiến trình thường là:

~~~mermaid
flowchart TD
    A["Caller gọi proxy @Transactional"] --> B["Spring mở session và bắt đầu transaction"]
    B --> C["Chạy method nghiệp vụ"]
    C --> D{"Method hoàn tất thế nào?"}
    D -->|"Return bình thường"| E["Spring yêu cầu commit"]
    D -->|"Exception phù hợp rollback rule"| F["Spring yêu cầu rollback/abort"]
    D -->|"Checked exception mặc định không rollback"| E
    E --> G{"commitTransaction thành công?"}
    G -->|"Có"| H["Proxy trả thành công cho caller"]
    G -->|"Không / kết quả không rõ"| I["Proxy phát lỗi hoặc trạng thái không xác định"]
    F --> J["Proxy ném lỗi gốc hoặc lỗi rollback"]
~~~

**Điểm chốt:** Code cuối thân method chạy xong **trước khi transaction interceptor thực hiện commit**. Nếu commit lỗi, exception có thể xuất hiện **sau khi thân method đã return**, nhưng caller vẫn chưa nhận được một lời gọi thành công qua proxy.

### 1.1. Tách ba khái niệm

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Application method returned** | Phần code nghiệp vụ đi tới `return`, chưa chắc transaction commit xong |
| **Commit acknowledged** | MongoDB đã xác nhận `commitTransaction` theo write concern/transaction options hiệu lực |
| **Business workflow complete** | Ngoài MongoDB, còn có thể phải phát sự kiện, gọi cổng thanh toán, đối soát hoặc gửi thông báo |

Không lấy log `"method finished"` làm bằng chứng transaction đã commit, cũng không suy rằng MongoDB transaction tự rollback được email, HTTP request hoặc message đã gửi ra ngoài.

## 2. Rollback nghĩa là gì trong MongoDB?

Khi dùng multi-document transaction, MongoDB gom nhiều thao tác đọc/ghi vào **một session transaction**.

- **Commit:** các ghi trong transaction được công nhận như một đơn vị nguyên tử.
- **Abort:** các thay đổi chưa commit của transaction không trở thành kết quả đã commit.
- **Rollback do failover của replica set:** một tình huống replication khác với abort transaction do ứng dụng; mức write concern commit ảnh hưởng độ bền kết quả.

### 2.1. Atomicity khác durability

Một transaction có thể **commit nguyên tử** đối với nhiều document, nhưng mức bền vững khi primary hỏng phụ thuộc write concern tại commit. Nếu commit chỉ được xác nhận theo `w:1`, transaction đã được ACK vẫn có thể gặp rủi ro rollback trong failover khi commit chưa đạt majority.

**Vì vậy cần hai câu hỏi:**

- Các thao tác có cùng commit/abort hay không? → **Transaction atomicity**.
- Sau ACK, dữ liệu có mức bảo vệ nào trước failover/crash? → **Commit write concern**.

### 2.2. Transaction không cần cho mọi trường hợp

MongoDB hỗ trợ tính nguyên tử đối với **một document**. Nếu nghiệp vụ chỉ chuyển trạng thái một order:

~~~javascript
db.orders.updateOne(
  { _id: "o701", state: "PENDING" },
  { $set: { state: "APPROVED" } }
);
~~~

thao tác single-document có predicate trạng thái thường đơn giản hơn multi-document transaction. Khi phải cập nhật order **và** tạo outbox ở hai collection cùng lúc, transaction giúp biểu diễn một ranh giới nhất quán.

### 2.3. Không đồng nhất abort với “xóa lại từng bản ghi”

Khi transaction bị abort, ứng dụng **không cần tự đảo ngược** các insert/update của transaction bằng một danh sách câu lệnh `delete`/`update` thủ công. Tự tạo compensation trong cùng database khi transaction đã có atomicity dễ gây xóa nhầm dữ liệu người khác hoặc ghi đè thay đổi đồng thời.

Compensation/saga chỉ cần thiết cho **nhiều hệ thống độc lập** hoặc business workflow không thể bao trọn trong một transaction MongoDB.

## 3. Điều kiện để dùng transaction

Các ví dụ tiếp theo yêu cầu MongoDB ở topology hỗ trợ transaction, phổ biến là:

- **Replica set** có primary hoạt động; hoặc
- **Sharded cluster** đáp ứng yêu cầu transaction của phiên bản đang dùng.

Một MongoDB **standalone** đơn lẻ không hỗ trợ multi-document transaction theo cơ chế replica set transaction. Trong phát triển/test, có thể chạy **single-node replica set** để kiểm các nguyên tắc commit/abort; để thử failover thật cần nhiều node.

### 3.1. Kiểm tra topology trong `mongosh`

Trên một database test:

~~~javascript
db.adminCommand({ hello: 1 });
// Replica set thường có trường setName và trạng thái isWritablePrimary.
~~~

Lệnh chỉ giúp nhận diện deployment. Đừng dùng quyền admin hoặc chạy `rs.stepDown()` trên cluster chung chỉ để thử rollback.

### 3.2. Session của transaction

Một MongoDB transaction được gắn với **ClientSession**. Các operation phải chạy trên cùng session/transaction và kết nối phù hợp với database factory mà Spring Data đang dùng.

~~~text
ClientSession S1
    +-- startTransaction
    +-- update orders
    +-- insert outbox
    +-- commitTransaction / abortTransaction

ClientSession S2
    +-- thao tác bên ngoài transaction S1
~~~

Nếu `update orders` dùng một `MongoTemplate` gắn session S1 nhưng `insert outbox` lại dùng driver/client không tham gia session ấy, bạn **không** có một transaction bao trọn cả hai.

### 3.3. Read preference và transaction

Các thao tác đọc trong multi-document transaction cần tuân theo yêu cầu **đọc primary** của MongoDB. Đừng gắn `secondaryPreferred` vào một transaction rồi cho rằng có thể đọc mọi secondary một cách tùy ý. Một read concern như `SNAPSHOT` có ngữ nghĩa riêng bên trong transaction.

## 4. Fixture học tập: hai collection và một trạng thái nghiệp vụ

Chạy trên database **test riêng**, không dùng production:

~~~javascript
use spring_data_mongodb_lab

db.orders_tx_demo_007.insertMany([
  {
    _id: "o701",
    tenant_id: "t01",
    state: "PENDING",
    amount_vnd: NumberLong(450000)
  },
  {
    _id: "o702",
    tenant_id: "t01",
    state: "PENDING",
    amount_vnd: NumberLong(700000)
  },
  {
    _id: "o703",
    tenant_id: "t02",
    state: "PENDING",
    amount_vnd: NumberLong(900000)
  }
]);

// Tạo outbox collection tường minh trước transaction.
db.createCollection("outbox_tx_demo_007");

db.orders_tx_demo_007.createIndex({ tenant_id: 1, state: 1 });
~~~

Các ID cố định chỉ dùng cho lần chạy fixture đầu trên collection test sạch. Không thực hiện `dropDatabase()`/`drop()` trong môi trường dùng chung. Khi chạy test tự động, sử dụng IDs riêng và cleanup đúng dữ liệu của test.

### 4.1. Kết quả mong đợi

| Kịch bản | Order sau thao tác | Outbox sau thao tác |
| --- | --- | --- |
| Approve o701, commit thành công | `o701.state=APPROVED` | Có `OrderApproved(o701)` |
| Approve o702 rồi ném unchecked exception | `o702.state=PENDING` | Không có outbox tương ứng |
| Cố approve o703 bằng tenant t01 | `o703.state=PENDING` | Không có outbox |
| Checked exception không cấu hình rollback | Có thể vẫn `APPROVED` | Có thể vẫn có outbox |

Kịch bản cuối là cảnh báo về **Spring rollback rules**, không phải yêu cầu nghiệp vụ. Nếu checked exception báo hủy thao tác nhưng transaction vẫn commit, đó thường là lỗi thiết kế chính sách exception.

## 5. Entity Spring Data MongoDB

### 5.1. Order document

~~~java
// OrderDocument.java
package com.example.transactions;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_tx_demo_007")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String state;

    @Field("amount_vnd")
    private long amountVnd;

    protected OrderDocument() { }

    public OrderDocument(
            String id, String tenantId,
            String state, long amountVnd) {
        this.id = id;
        this.tenantId = tenantId;
        this.state = state;
        this.amountVnd = amountVnd;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
    public long getAmountVnd() { return amountVnd; }
}
~~~

### 5.2. Outbox event

~~~java
// OutboxEvent.java
package com.example.transactions;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "outbox_tx_demo_007")
public class OutboxEvent {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("order_id")
    private String orderId;

    private String eventType;
    private Instant occurredAt;

    protected OutboxEvent() { }

    public OutboxEvent(
            String id, String tenantId,
            String orderId, String eventType,
            Instant occurredAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.eventType = eventType;
        this.occurredAt = occurredAt;
    }

    public String getId() { return id; }
    public String getOrderId() { return orderId; }
    public String getTenantId() { return tenantId; }
    public String getEventType() { return eventType; }
}
~~~

`@MongoId(FieldType.STRING)` giúp `_id` của fixture giữ BSON string, không mặc nhiên chuyển một giá trị giống ObjectId sang `ObjectId`. Các field `tenant_id`/`order_id` được ánh xạ từ property Java khi dùng `MongoOperations` với entity metadata.

### 5.3. Vì sao cần ID outbox ổn định?

Đặt outbox ID như `order-approved:o701` hoặc UUID/idempotency key dựa trên **event nghiệp vụ duy nhất**. Nếu request/transaction được thử lại, ID ổn định giúp phát hiện trùng thay vì tạo event giống nhau nhưng mang ID hoàn toàn mới.

Tuy nhiên, ID ổn định **không tự bảo đảm delivery exactly-once** tới hệ thống bên ngoài. Outbox publisher và consumer vẫn cần cơ chế idempotency, checkpoint và phân loại lỗi.

## 6. Cấu hình `MongoTransactionManager` và commit options

### 6.1. Transaction manager cơ bản

~~~java
// MongoTxConfig.java
package com.example.transactions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTxConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

`MongoTransactionManager` là thành phần Spring quản lý session, start/commit/abort và gắn transaction vào ngữ cảnh của thread cho **synchronous MongoTemplate/repository**.

Spring Data MongoDB không tự bật transaction cho mọi method `@Transactional` nếu chưa có transaction manager tương ứng. Hãy dùng tên manager rõ ràng nếu ứng dụng còn JPA/JDBC/Kafka transaction manager.

### 6.2. Cấu hình rõ majority commit và snapshot

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Bean
MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory factory) {

    TransactionOptions options = TransactionOptions.builder()
        .readConcern(ReadConcern.SNAPSHOT)
        .readPreference(ReadPreference.primary())
        .writeConcern(WriteConcern.MAJORITY.withJournal(true))
        .build();

    return new MongoTransactionManager(factory, options);
}
~~~

Đây là **phương án thay thế** bean ở mục 6.1, **không khai báo đồng thời hai bean cùng tên**. Tùy phiên bản MongoDB/driver và policy vận hành, có thể điều chỉnh transaction options. Commit write concern là nơi xác định mức xác nhận **commitTransaction**; không cố đặt write concern riêng cho mỗi `insert`/`update` bên trong transaction.

### 6.3. Quy tắc cùng database factory

Một transaction manager sử dụng `MongoDatabaseFactory A`, nhưng `MongoTemplate` trong service dùng factory B, sẽ không mặc nhiên tham gia cùng transaction. Với nhiều data source hoặc nhiều MongoClient:

- Xác định factory/session thuộc từng template.
- Bảo đảm thao tác cần nguyên tử đi qua cùng hạ tầng transaction được quản lý.
- Có integration test chứng minh cả hai collection cùng rollback.
- Đừng chỉ nhìn annotation mà kết luận có transaction thật.

## 7. Service: update order và ghi outbox trong một transaction

### 7.1. Custom exception để báo conflict

~~~java
// OrderStateConflictException.java
package com.example.transactions;

public class OrderStateConflictException
        extends RuntimeException {
    public OrderStateConflictException(String message) {
        super(message);
    }
}
~~~

Đây là **unchecked exception**, nên theo rollback rules mặc định của Spring nó sẽ khiến transactional interceptor **đánh dấu rollback**, với điều kiện exception thực sự thoát khỏi method qua proxy.

### 7.2. Một service đủ điều kiện chạy qua proxy

~~~java
// OrderApprovalService.java
package com.example.transactions;

import java.time.Instant;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApprovalService {
    private final MongoOperations operations;

    public OrderApprovalService(MongoOperations operations) {
        this.operations = operations;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void approve(String tenantId, String orderId) {
        applyApproval(tenantId, orderId);
    }

    private void applyApproval(String tenantId, String orderId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        Query pending = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );

        var result = operations.updateFirst(
            pending,
            new Update().set("state", "APPROVED"),
            OrderDocument.class
        );

        if (result.getMatchedCount() != 1) {
            throw new OrderStateConflictException(
                "Order missing, wrong tenant or not PENDING"
            );
        }

        operations.insert(
            new OutboxEvent(
                "order-approved:" + orderId,
                tenantId,
                orderId,
                "OrderApproved",
                Instant.now()
            )
        );
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void approveThenFail(
            String tenantId, String orderId) {
        applyApproval(tenantId, orderId);
        throw new IllegalStateException(
            "Simulated failure before commit"
        );
    }
}
~~~

**Điều kiện chạy đúng:** Caller inject `OrderApprovalService` và gọi `approve(...)`/`approveThenFail(...)` từ **bean khác** thông qua Spring proxy. `applyApproval(...)` là private helper được gọi **bên trong** một method transaction đã được mở.

### 7.3. Vì sao dùng `updateFirst` có điều kiện?

Predicate yêu cầu đồng thời:

~~~text
_id == orderId
tenant_id == authenticatedTenant
state == PENDING
~~~

Nó giúp chỉ một workflow chuyển order đang `PENDING` sang `APPROVED`, đồng thời không cho tenant t01 sửa order của t02. `matchedCount == 0` có thể là ID không tồn tại, sai tenant hoặc state đã đổi; cần contract API quyết định thông điệp/HTTP status.

Đừng gọi `findById` rồi `save` nếu yêu cầu cạnh tranh là “chỉ transition khi state vẫn PENDING” mà không có guard/optimistic lock. Transaction không thay thế predicate nghiệp vụ.

### 7.4. Khi không có exception

~~~text
Proxy mở tx T1
  -> update order (trong T1)
  -> insert outbox (trong T1)
  -> method approve() return
  -> Spring commitTransaction(T1)
  -> commit ACK thành công
Proxy trả về caller
~~~

**Kết quả:** Order `APPROVED` và outbox được commit cùng nhau. Nếu API caller nhận lời gọi từ proxied service **thành công sau commit**, có cơ sở khẳng định transaction đã đạt mức acknowledgment cấu hình, nhưng chưa đồng nghĩa message đã được consumer xử lý.

### 7.5. Khi method ném unchecked exception

~~~text
Proxy mở tx T2
  -> update order (trong T2)
  -> insert outbox (trong T2)
  -> throw IllegalStateException
  -> Spring abortTransaction(T2)
Proxy chuyển exception tới caller
~~~

**Kết quả:** Cả update order và outbox insert trong T2 **không được commit**. Không tự chạy câu lệnh xóa outbox sau khi bắt exception ở controller.

## 8. Quy tắc rollback mặc định của Spring

Theo rollback rules mặc định quen thuộc của Spring:

- `RuntimeException` (unchecked) → **rollback**.
- `Error` → **rollback**.
- Checked exception (`Exception` không kế thừa `RuntimeException`) → **không tự rollback**, transaction có thể **commit** khi method ném exception đó.

Một số phiên bản/cấu hình Spring mới cho phép thay đổi **default rollback policy ở cấp ứng dụng**; vì vậy bảng sau áp dụng khi dự án **chưa tùy chỉnh rollback rules**.

| Kết thúc method `@Transactional` | Mặc định với Spring proxy | Kết quả kỳ vọng |
| --- | --- | --- |
| Return bình thường | Commit | Các write được commit nếu commit thành công |
| Ném `IllegalStateException` | Rollback | Các write thuộc transaction bị abort |
| Ném `DuplicateKeyException` | Rollback | Spring Data exception là unchecked |
| Ném `DataAccessException` | Rollback | Unchecked exception |
| Ném `Error` | Rollback | Transaction interceptor yêu cầu rollback |
| Ném custom checked `BusinessRuleException extends Exception` | **Commit theo mặc định** | Có thể commit dù caller nhận exception |
| Bắt unchecked exception và return bình thường | Thường commit nếu transaction còn hợp lệ | Lỗi có thể bị che; server error đôi khi đã làm transaction không thể commit |
| Gọi `setRollbackOnly()` rồi return | Rollback | Không commit dù method trả bình thường |

### 8.1. Checked exception dễ tạo sai lệch nghiệp vụ

~~~java
// BusinessRuleException.java
package com.example.transactions;

public class BusinessRuleException extends Exception {
    public BusinessRuleException(String message) {
        super(message);
    }
}
~~~

Giả sử service:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager"
)
public void approveThenThrowChecked(
        String tenantId, String orderId)
        throws BusinessRuleException {

    applyApproval(tenantId, orderId);
    throw new BusinessRuleException(
        "Example checked error"
    );
}
~~~

**Bất ngờ:** Nếu không cấu hình rollback cho checked exception và transaction không bị lỗi ở database, Spring có thể **commit** cả order lẫn outbox, sau đó exception vẫn được ném ra caller.

Điều này không có nghĩa MongoDB “bỏ qua rollback”; là vì **transaction interceptor đã chọn commit theo rollback rule**.

### 8.2. Exception type, không phải tên class, quyết định mặc định

Hai class tên giống nghiệp vụ:

~~~java
class OrderRejectedRuntime extends RuntimeException { }
class OrderRejectedChecked extends Exception { }
~~~

có hành vi rollback mặc định **khác nhau**. Khi thiết kế API error, đặt phân loại exception có chủ đích và kiểm thử actual transaction behavior; đừng dựa vào tên `...Failed` hoặc `...Business`.

## 9. `rollbackFor`, `noRollbackFor` và rule rõ ràng

### 9.1. Rollback cho checked exception

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    rollbackFor = BusinessRuleException.class
)
public void approveThenRollbackChecked(
        String tenantId, String orderId)
        throws BusinessRuleException {

    applyApproval(tenantId, orderId);
    throw new BusinessRuleException(
        "Must abort transaction"
    );
}
~~~

Lúc này exception checked thoát khỏi transactional proxy sẽ khiến Spring **abort** theo rule cụ thể.

Có thể dùng `rollbackFor = Exception.class` cho chính sách rộng hơn, nhưng phải review tác động: không phải mọi checked exception đều đại diện cho thất bại cần rollback. Ví dụ một exception dùng để báo kết quả nghiệp vụ “đã xử lý nhưng có cảnh báo” có thể cần một contract khác.

### 9.2. `noRollbackFor` cho trường hợp có chủ đích

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    noRollbackFor = NonFatalNotificationException.class
)
public void approveAndReportWarning(
        String tenantId, String orderId) {

    applyApproval(tenantId, orderId);
    throw new NonFatalNotificationException(
        "Notification scheduling was skipped"
    );
}
~~~

Trong đó `NonFatalNotificationException extends RuntimeException` là class do dự án định nghĩa. Khi dùng `noRollbackFor`, Spring có thể **vẫn commit** dù caller nhận unchecked exception.

**Chỉ dùng khi thực sự muốn dữ liệu được commit** và caller hiểu khác biệt “write đã hoàn thành nhưng nghiệp vụ có cảnh báo”. Nếu operation đã đánh dấu transaction **rollback-only** hoặc MongoDB transaction bị server abort, `noRollbackFor` không thể “cứu” một transaction không còn commit được.

### 9.3. Rule cụ thể và độ ưu tiên

Khi có nhiều rollback/no-rollback rules, Spring chọn rule **phù hợp cụ thể nhất** với exception type theo cơ chế của transaction attribute. Đừng cấu hình một chồng class/pattern quy tắc trùng nhau mà không có test.

Ưu tiên khai báo theo **class**:

~~~java
rollbackFor = BusinessRuleException.class
~~~

hơn pattern string chung chung như `rollbackForClassName = "Exception"`, vì pattern có thể vô tình khớp nhiều class không liên quan.

## 10. Bẫy `try/catch`: bắt exception rồi transaction vẫn commit

### 10.1. Mẫu sai: nuốt lỗi và trả thành công

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager"
)
public boolean approveIgnoringFailure(
        String tenantId, String orderId) {
    try {
        applyApproval(tenantId, orderId);
        throw new IllegalStateException(
            "Simulated business failure"
        );
    } catch (IllegalStateException ignored) {
        return false; // Method return bình thường qua transaction interceptor.
    }
}
~~~

Vì exception **không đi ra khỏi method**, interceptor thường nhìn thấy **normal return** và thực hiện commit. Đối với lỗi thuần Java như ví dụ, transaction có thể vẫn hợp lệ, nghĩa là order và outbox **được commit** dù method trả `false`.

### 10.2. Không nhầm với lỗi MongoDB đã làm transaction vô hiệu

Nếu exception đến từ server (write conflict, duplicate, transaction aborted), session có thể đã rơi vào trạng thái không thể commit. `catch` và trả bình thường **không bảo đảm commit được**; lệnh commit có thể thất bại hoặc transaction đã abort.

Vì vậy không nên viết quy tắc đơn giản “catch thì luôn commit”. Quy tắc đúng là:

> Catch khiến Spring **không còn biết exception thoát ra**, nhưng transaction chỉ commit nếu trạng thái transaction và server còn cho phép.

### 10.3. Các hướng xử lý đúng

Nếu lỗi phải hủy cả transaction:

~~~java
try {
    applyApproval(tenantId, orderId);
} catch (OrderStateConflictException ex) {
    logBusinessConflict(ex); // log an toàn
    throw ex;                // Cho interceptor thấy lỗi.
}
~~~

Hoặc nếu cần chuyển đổi exception:

~~~java
try {
    applyApproval(tenantId, orderId);
} catch (OrderStateConflictException ex) {
    throw new ApprovalFailedException("Cannot approve", ex);
}
~~~

`ApprovalFailedException` nên là một unchecked exception hoặc được khai báo trong `rollbackFor`. Đừng chuyển unchecked exception thành checked exception rồi vô tình thay đổi rollback rule.

### 10.4. Nên bắt lỗi ở ranh giới nào?

- **Trong service transaction:** bắt khi cần enrich context rồi ném lại, hoặc chọn rollback-only có chủ đích.
- **Ở application/controller boundary:** nhận exception sau khi proxy đã commit/rollback (hoặc fail commit), chuyển thành API response.
- **Ở retry/orchestration layer:** phân loại transient vs unknown outcome, quyết định retry an toàn.

Không cần bắt mọi `Exception` ngay trong transactional method nếu không có lý do nghiệp vụ.

## 11. Đánh dấu rollback-only khi không muốn ném exception

Đôi khi service cần ghi nhận một kết quả business nhưng vẫn muốn **abort** transaction. Spring cho phép đánh dấu trạng thái hiện tại rollback-only.

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional(
    transactionManager = "mongoTransactionManager"
)
public boolean approveOrReturnFalse(
        String tenantId, String orderId) {
    try {
        applyApproval(tenantId, orderId);
        if (requiresCancellation(orderId)) {
            TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
            return false;
        }
        return true;
    } catch (OrderStateConflictException ex) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return false;
    }
}
~~~

`requiresCancellation(orderId)` là một hàm kiểm nghiệp vụ minh họa, chưa có implementation trong ví dụ. Khi áp dụng, phải tránh các side effect không rollback được và kiểm status của transaction.

### 11.1. Giới hạn của rollback-only

`setRollbackOnly()` chỉ có ý nghĩa khi code đang chạy trong **Spring transaction context**. Gọi ngoài context có thể ném `NoTransactionException` hoặc báo không có transaction status thích hợp.

Nếu method chạy qua proxy với một transaction **mới do nó sở hữu**, Spring có thể abort khi xử lý return. **Nhưng trong transaction tham gia bên ngoài**, việc một inner scope đánh dấu rollback-only có thể khiến outer scope cố commit và gặp `UnexpectedRollbackException`.

### 11.2. Đừng xem `false` là bằng chứng đã rollback

Một API trả `false` có thể có rất nhiều nghĩa:

- Business predicate không khớp, transaction đã rollback.
- Business predicate không khớp, không hề có write.
- Method nuốt lỗi và vô tình commit.
- Transaction commit thất bại sau khi method return.

Đặt contract rõ ràng và test **trạng thái database sau khi proxy trả về** thay vì chỉ assert boolean.

## 12. `UnexpectedRollbackException` khi nhiều method cùng transaction

Một tình huống phổ biến: method bên ngoài **bắt lỗi** của method bên trong, nghĩ rằng mọi thứ vẫn ổn, nhưng transaction đã bị đánh dấu rollback-only.

### 12.1. Hai service bean khác nhau

~~~java
@Service
public class InnerApprovalService {
    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void validateAndApprove(String orderId) {
        // Các thao tác MongoDB trong transaction hiện tại...
        throw new OrderStateConflictException("Conflict");
    }
}

@Service
public class OuterCheckoutService {
    private final InnerApprovalService inner;

    public OuterCheckoutService(InnerApprovalService inner) {
        this.inner = inner;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void checkout(String orderId) {
        try {
            inner.validateAndApprove(orderId);
        } catch (OrderStateConflictException ignored) {
            // Không rethrow; nhưng inner transaction scope
            // đã đánh dấu transaction chung rollback-only.
        }

        // Có thể còn thao tác trong cùng transaction...
    }
}
~~~

Với **propagation `REQUIRED` mặc định**:

~~~text
OuterCheckoutService.checkout()
    -> T1 bắt đầu
    -> InnerApprovalService.validateAndApprove()
           -> tham gia T1, KHÔNG mở T2 mới
           -> ném RuntimeException
           -> inner interceptor đánh dấu T1 rollback-only
    -> outer catch exception, tiếp tục
    -> outer method return bình thường
    -> outer interceptor cố commit T1
    -> T1 rollback, có thể ném UnexpectedRollbackException
~~~

Spring dùng `UnexpectedRollbackException` để tránh để caller tin commit thành công khi transaction đã bị đánh dấu rollback-only ở một scope khác.

### 12.2. `UnexpectedRollbackException` xuất hiện khi nào?

Nó thường xuất hiện **ở ranh giới commit của outer transaction**, sau khi thân method ngoài đã return. Lúc này:

- Ngoại lệ được inner service ném ra có thể đã bị catch.
- Dữ liệu trong transaction chung không được commit.
- Caller ngoài cùng lại nhận một exception mới, thường là `UnexpectedRollbackException`.

Không cố chặn `UnexpectedRollbackException` bằng cách hạ rollback rules tùy tiện; hãy sửa thiết kế quyền sở hữu transaction và xử lý lỗi.

### 12.3. Ba cách làm rõ hợp đồng

**Cách A — lỗi có nghĩa phải hủy workflow:** outer **ném lại** exception để rollback trở nên rõ ràng.

~~~java
try {
    inner.validateAndApprove(orderId);
} catch (OrderStateConflictException ex) {
    throw ex;
}
~~~

**Cách B — lỗi inner có thể bỏ qua:** inner method không nên đánh dấu transaction chung rollback-only nếu thật sự muốn outer commit; hãy trả result nghiệp vụ **trước khi thực hiện ghi có thể hỏng**, hoặc tách transaction scope phù hợp.

**Cách C — thao tác inner độc lập:** cân nhắc `REQUIRES_NEW` với chi phí và giới hạn độc lập của nó. Không dùng nó để “chữa” mọi lỗi khi logic thực sự yêu cầu all-or-nothing.

## 13. Propagation `REQUIRED`, `REQUIRES_NEW` và `NESTED`

Spring định nghĩa **propagation behavior** cho các method transactional. Cần phân biệt propagation của Spring với primitive transaction của MongoDB.

| Propagation | Khi có outer transaction | Hệ quả cần lưu ý |
| --- | --- | --- |
| `REQUIRED` | Tham gia transaction hiện tại | Một rollback-only có thể ảnh hưởng toàn transaction |
| `REQUIRES_NEW` | Tạm dừng outer, mở transaction mới nếu hạ tầng cho phép | Inner commit độc lập với outer; cần thêm session/connection resource |
| `SUPPORTS` | Tham gia nếu có, không thì không tạo | Ghi ngoài transaction có thể không atomic với outer |
| `MANDATORY` | Yêu cầu transaction đã tồn tại | Thiếu outer transaction sẽ lỗi |
| `NOT_SUPPORTED` | Tạm dừng transaction để chạy không transaction | Write ở đây không rollback cùng outer |
| `NEVER` | Không được có transaction đang chạy | Có transaction sẽ lỗi |
| `NESTED` | Nested savepoint theo hạ tầng hỗ trợ | **Không giả định MongoDB có savepoint/nested transaction** |

### 13.1. `REQUIRES_NEW` không phải savepoint MongoDB

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    propagation = Propagation.REQUIRES_NEW
)
public void writeIndependentAudit(...) {
    // Transaction mới, commit độc lập nếu bắt đầu được.
}
~~~

Trong đó cần import `org.springframework.transaction.annotation.Propagation`. Spring có thể suspend outer transaction và mở một session transaction khác cho inner.

**Cảnh báo:** MongoDB transaction mới có thể cần tài nguyên/session/kết nối khác, làm tăng contention, đặc biệt dưới load. Nếu inner commit rồi outer rollback, **audit inner vẫn có thể tồn tại**. Đây là tính năng chỉ đúng nếu nghiệp vụ **muốn kết quả độc lập**.

### 13.2. `NESTED` không phải “transaction nhỏ rollback riêng”

MongoDB không cung cấp savepoint theo cách JDBC hỗ trợ. `MongoTransactionManager` không hỗ trợ `NESTED` thông qua JDBC savepoint mặc định. Nếu yêu cầu:

~~~text
T1: ghi A
  T_nested: ghi B
  rollback chỉ B
T1: vẫn commit A
~~~

thì không nên kỳ vọng annotation `Propagation.NESTED` biến MongoDB thành hệ có savepoint. Cần tái thiết kế aggregate, tách transaction độc lập, hoặc dùng saga/compensation có kiểm soát.

### 13.3. Không dùng `REQUIRES_NEW` trong cùng method rồi tin annotation có hiệu lực

Spring AOP proxy-based transaction chỉ intercept lời gọi **qua proxy**. Nếu một method gọi `this.inner()` trong **cùng object**, annotation trên `inner()` có thể bị bỏ qua; xem mục tiếp theo.

## 14. Self-invocation: annotation có nhưng transaction không mở

### 14.1. Mẫu sai

~~~java
@Service
public class OrderFacade {
    public void handle(String tenantId, String orderId) {
        approveInTransaction(tenantId, orderId);
        // Lời gọi nội bộ this.approveInTransaction(...)
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void approveInTransaction(
            String tenantId, String orderId) {
        // Nếu gọi qua this từ handle(), proxy không intercept.
    }
}
~~~

Nếu `handle()` được gọi qua proxy, nó không có annotation transaction; lời gọi vào `approveInTransaction()` xảy ra trực tiếp trong object, bỏ qua proxy. Hai write bên dưới có thể thực hiện **ngoài transaction**, cho dù nhìn code có `@Transactional`.

### 14.2. Cách sửa dễ bảo trì

Đưa method transactional sang **một Spring bean khác** và inject:

~~~java
@Service
public class OrderFacade {
    private final OrderApprovalService approvalService;

    public OrderFacade(OrderApprovalService approvalService) {
        this.approvalService = approvalService;
    }

    public void handle(String tenantId, String orderId) {
        approvalService.approve(tenantId, orderId);
    }
}
~~~

Hoặc đặt `@Transactional` trên **entry-point public** thật sự nhận lời gọi qua proxy. Các giải pháp như tự inject proxy của chính mình hoặc dùng AspectJ weaving có chi phí/cấu hình khác; không nên làm mặc định nếu có thể tách bean đúng responsibility.

### 14.3. Cảnh báo khác về proxy

- Method private/final hoặc class/method không được proxy đúng cách có thể không được intercept; hành vi phụ thuộc JDK proxy/CGLIB/Spring version.
- Tự tạo object bằng `new OrderApprovalService(...)` thay vì lấy từ Spring context bỏ qua transaction proxy.
- `@Transactional` trên method chạy trong **thread khác** không tự truyền thread-bound transaction context; đừng tự tạo `CompletableFuture.runAsync(...)` rồi cho rằng các write ở thread mới thuộc T1.
- Một số interceptor khác (@Async, retry, security) có thứ tự AOP riêng; nên kiểm transaction boundary thực tế bằng integration test.

**Không dùng một unit test gọi trực tiếp method trên object `new` để chứng minh annotation transaction hoạt động.**

## 15. `TransactionTemplate`: lựa chọn lập trình tường minh

Khi muốn bao một đoạn code trong transaction mà không phụ thuộc self-invocation hoặc cần điều khiển explicit status, dùng `TransactionTemplate` trong mô hình imperative.

### 15.1. Tạo template từ manager

~~~java
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ProgrammaticOrderService {
    private final TransactionTemplate tx;
    private final MongoOperations operations;

    public ProgrammaticOrderService(
            MongoTransactionManager transactionManager,
            MongoOperations operations) {
        this.tx = new TransactionTemplate(transactionManager);
        this.operations = operations;
    }

    public boolean approve(String tenantId, String orderId) {
        Boolean result = tx.execute(status -> {
            // Gọi MongoOperations trên cùng MongoDatabaseFactory.
            Query query = Query.query(
                Criteria.where("id").is(orderId)
                    .and("tenantId").is(tenantId)
                    .and("state").is("PENDING")
            );

            var update = operations.updateFirst(
                query,
                new Update().set("state", "APPROVED"),
                OrderDocument.class
            );

            if (update.getMatchedCount() != 1) {
                status.setRollbackOnly();
                return false;
            }

            operations.insert(new OutboxEvent(
                "order-approved:" + orderId,
                tenantId, orderId,
                "OrderApproved",
                Instant.now()
            ));
            return true;
        });

        // commit/rollback xảy ra trong tx.execute(...)
        // TRƯỚC khi method này trả về.
        return Boolean.TRUE.equals(result);
    }
}
~~~

Để chạy, import `java.time.Instant`, `MongoOperations`, `Criteria`, `Query`, `Update` tương tự mục 7. `TransactionTemplate.execute(...)` tự quản lý start/commit/rollback quanh callback theo policy được cấu hình.

### 15.2. Thời điểm commit của `TransactionTemplate`

~~~text
ProgrammaticOrderService.approve()
   -> tx.execute(callback)
       -> start tx
       -> callback return true
       -> commitTransaction
   -> tx.execute(...) trả true
   -> method approve() trả true
~~~

Nếu commit lỗi, `tx.execute` **không** có nghĩa đã trả true cho caller; exception có thể xuất hiện ở bước commit trước khi `execute` kết thúc.

### 15.3. Khi nào chọn declarative vs programmatic?

| Tiêu chí | `@Transactional` | `TransactionTemplate` |
| --- | --- | --- |
| Ranh giới transaction | Method chạy qua proxy | Callback `execute` |
| Khả năng nhìn thấy điểm bắt đầu/kết thúc | Ít tường minh hơn | Rõ ngay tại dòng gọi `execute` |
| Tách business logic | Ít boilerplate | Nhiều boilerplate hơn |
| Self-invocation | Dễ mắc bẫy proxy | Không phụ thuộc method AOP cho callback |
| Rollback-only | `TransactionAspectSupport...` | `status.setRollbackOnly()` |

Cả hai vẫn dựa trên **cùng transaction manager/Mongo session**. Chọn phương án dễ review, dễ test và phù hợp kiến trúc, không phải vì một cách “tự động an toàn hơn” cách kia.

## 16. Thời điểm commit và ranh giới HTTP/API

### 16.1. Khi controller gọi service qua proxy

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderApprovalService service;

    public OrderController(OrderApprovalService service) {
        this.service = service;
    }

    @PostMapping("/{id}/approve")
    ResponseEntity<Void> approve(
            @PathVariable String id,
            Authentication authentication) {

        String tenantId = tenantFrom(authentication);
        service.approve(tenantId, id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Trong đó `tenantFrom(authentication)` là hàm chuyển security principal thành tenant được xác thực, phải do dự án triển khai. Bỏ qua phần xác thực chỉ để minh họa boundary transaction.

Đường đi:

~~~text
Controller -> transactional proxy -> method body -> commit
                                               |
                                        commit thành công?
                                               |
                                   Proxy trả về controller
                                               |
                                     HTTP 204 được xây dựng
~~~

Với transaction annotation trên **service**, controller thường chỉ tạo response thành công **sau khi proxy đã hoàn thành commit**. Nếu commit lỗi, call service ném exception, controller không nên phát 204.

### 16.2. Khi `@Transactional` nằm trực tiếp trên controller?

Về mặt kỹ thuật có thể cấu hình, nhưng nên ưu tiên transaction ở **application service** thay vì để controller chứa transaction. Lý do:

- Controller còn làm serialization, HTTP mapping và tham chiếu request.
- Ranh giới commit khó review và có thể trộn xử lý exception/response.
- Những hoạt động chậm như HTTP call bên ngoài kéo dài transaction không cần thiết.

Không dùng `ResponseEntity.ok(...)` tạo **trong thân transactional method** làm bằng chứng response đã được gửi: transaction interceptor có thể commit sau khi method tạo object nhưng trước khi trả nó cho bên ngoài.

### 16.3. Log `"approved"` trước commit có thể đánh lừa

~~~java
@Transactional
public void approve(...) {
    applyApproval(...);
    logger.info("Order approved");
}
~~~

Log trên xuất hiện **trước commit**. Nếu commit thất bại, log vẫn nói “approved”. Dùng thông điệp rõ:

~~~text
Approval changes prepared in transaction
~~~

và log/metric `committed` tại ranh giới sau successful proxy return hoặc transaction synchronization `afterCommit`.

## 17. Side effect ngoài MongoDB không rollback theo transaction

### 17.1. Mẫu sai: gửi HTTP hoặc email trong transaction

~~~java
@Transactional
public void approveAndNotify(...) {
    applyApproval(...);
    emailSender.sendApprovalEmail(...);
    // Sau đó MongoDB commit mới xảy ra.
}
~~~

Nếu email đã được gửi nhưng MongoDB abort/commit lỗi, người nhận sẽ thấy thông báo “đã duyệt” trong khi database không lưu trạng thái ấy.

MongoDB **không thể rollback một email đã gửi hoặc request đã được remote API xử lý**.

### 17.2. Outbox pattern

Thay vì gửi event trực tiếp trong transaction:

~~~text
Transaction T1:
   update orders.state = APPROVED
   insert outbox(OrderApproved)
   commit

Outbox publisher (process riêng):
   đọc outbox đã commit
   gửi event
   đánh dấu delivered / checkpoint

Consumer:
   xử lý idempotent theo eventId
~~~

Order và outbox record cùng commit/abort. Publisher chỉ thấy event sau commit, nhưng **gửi event** có thể thực hiện nhiều lần khi publisher crash giữa send và checkpoint; consumer phải xử lý trùng.

### 17.3. `@TransactionalEventListener(AFTER_COMMIT)`

Spring hỗ trợ hook chạy khi transaction commit thành công:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCommitListener {
    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterCommit(OrderApprovedSignal signal) {
        // Chỉ chạy khi transaction commit thành công theo Spring.
        // Không là một phần của atomic transaction MongoDB.
        notifyLocally(signal);
    }
}
~~~

`OrderApprovedSignal` và `notifyLocally(...)` là kiểu/hàm minh họa. Nếu phát event trong transactional service qua `ApplicationEventPublisher`, listener `AFTER_COMMIT` được gọi theo transaction synchronization.

**Không nhầm hook với outbox bảo đảm bền vững:** Process có thể crash **sau commit nhưng trước khi listener gửi thành công**; listener có thể lỗi hoặc chạy lại khi workflow khác retry. Với event quan trọng, outbox persisted vẫn phù hợp hơn.

### 17.4. Ghi MongoDB trong `AFTER_COMMIT` cần transaction mới

Spring lưu ý: sau commit/rollback, tài nguyên transaction có thể vẫn còn gắn tạm với thread trong callback completion; **không giả định ghi dữ liệu trong AFTER_COMMIT tự mở transaction mới và sẽ commit**.

Nếu listener thực sự cần ghi một transaction độc lập, dùng service khác có `REQUIRES_NEW`/`TransactionTemplate` với hạ tầng phù hợp, và test kỹ. Với outbox, cách tốt nhất thường là để publisher/worker xử lý sau commit, không nhồi thêm write vào completion callback.

## 18. Commit lỗi: trạng thái transaction có thể *không xác định*

Đây là điểm khác biệt quan trọng giữa:

- **Lỗi rõ ràng trước commit** khiến ứng dụng biết transaction được yêu cầu abort.
- **Lỗi trong lúc commit** khi client chưa biết server đã commit thành công hay chưa.

### 18.1. Ví dụ mạng đứt đúng lúc commit

~~~text
Service method:
   update order  -> ok trong tx
   insert outbox -> ok trong tx
   return khỏi thân method

Spring/driver:
   gửi commitTransaction
   MongoDB commit thành công
   MẤT KẾT NỐI trước khi ACK tới client

Caller:
   nhận exception / timeout
   nhưng transaction CÓ THỂ ĐÃ COMMIT.
~~~

**Không có thông tin nào trong exception network đơn thuần chứng minh transaction đã abort.** Nếu ứng dụng tự chạy lại toàn bộ business method như request mới, nó có thể tạo side effect trùng hoặc gặp conflict.

### 18.2. Error label `UnknownTransactionCommitResult`

MongoDB Driver dùng error labels, nổi bật:

- `UnknownTransactionCommitResult`: kết quả commit chưa chắc chắn; hướng xử lý chính là **retry commit** theo quy tắc driver/API, không tự động chạy lại mọi write trong transaction.
- `TransientTransactionError`: một số lỗi tạm thời xảy ra trong transaction cho phép **retry toàn transaction body** từ đầu với một transaction mới khi an toàn.

Hai nhãn này **không tương đương**. Một nhãn khuyến nghị retry **commit**, một nhãn có thể khuyến nghị retry **body**, và cả hai cần tuân theo điều kiện/giới hạn của driver.

### 18.3. Driver có logic retry nhưng application vẫn cần thiết kế

MongoDB Java Driver có các API transaction thuận tiện và logic retry theo trường hợp, còn khi dùng manual transaction/Spring transaction manager, không nên giả định mọi phiên bản tự retry vô hạn.

Nên:

1. Dùng MongoDB Java Driver/Spring Data phiên bản phù hợp.
2. Hiểu commit retry theo phiên bản driver/server.
3. Phân loại lỗi ở application boundary, không `catch Exception; retry 3` mù.
4. Dùng business idempotency keys cho request.
5. Đối soát state persisted khi kết quả commit chưa xác định.
6. Áp deadline/số lần retry hữu hạn và metric để tránh khuếch đại lỗi cluster.

### 18.4. Thực hành nhận diện error label

~~~java
import com.mongodb.MongoException;

public static boolean containsMongoLabel(
        Throwable error, String label) {
    for (Throwable cause = error; cause != null;
            cause = cause.getCause()) {
        if (cause instanceof MongoException mongo
                && mongo.hasErrorLabel(label)) {
            return true;
        }
    }
    return false;
}
~~~

Khi Spring Data translate exception thành `DataAccessException` hoặc wrapper khác, nhãn lỗi MongoDB có thể nằm ở **cause**. Hàm trên dùng để **phân loại**; nó không tự quyết định retry có an toàn hay không.

Ví dụ:

~~~java
if (containsMongoLabel(error,
        "UnknownTransactionCommitResult")) {
    // Không coi là rollback chắc chắn.
    // Dùng cơ chế retry commit của driver nếu còn session/context,
    // hoặc chuyển sang trạng thái cần đối soát idempotency key.
}
~~~

Không đơn giản gọi lại `service.approve(...)` từ đầu chỉ dựa vào label này, nhất là khi workflow còn gửi request tới hệ thống ngoài.

## 19. Retry toàn transaction và các giới hạn

### 19.1. Khi nào nên retry body?

Ví dụ hai transaction cạnh tranh cập nhật cùng order có thể gặp `WriteConflict` hoặc một lỗi có `TransientTransactionError`. MongoDB có thể abort một transaction để bảo vệ tính nhất quán; ứng dụng có thể **tạo transaction mới** và thử lại logic nếu:

- Thao tác là **idempotent** hoặc có khóa bảo vệ đủ mạnh.
- Transaction body **không phát side effect ngoài database**.
- Có deadline, backoff và giới hạn số lần retry.
- Lần retry luôn đọc/kiểm lại trạng thái nghiệp vụ mới nhất.

### 19.2. Không retry body ở mọi `DuplicateKeyException`

Một outbox `_id` cố định bị duplicate có thể nghĩa là request đã xử lý thành công. Retry liên tục cùng insert sẽ vẫn duplicate; cần đọc bản ghi cũ và đối chiếu payload.

Với payment/ledger, không “đổi `_id` ngẫu nhiên cho hết duplicate” vì như vậy phá cơ chế idempotency.

### 19.3. Không xem `@Retryable` tự hiểu MongoDB transaction

Nếu dùng Spring Retry hoặc custom retry interceptor:

- Xem **thứ tự AOP advice**: retry bao quanh transaction hay transaction bao quanh retry?
- Mỗi retry attempt có tạo transaction/session mới không?
- Có retry commit uncertainty bằng cách gọi lại body sai không?
- Có side effect ngoài database nằm trong body không?

Ví dụ nếu retry nằm **bên trong** một transaction đã bị MongoDB đánh dấu aborted, retry thao tác đơn lẻ **trên cùng transaction** thường không khôi phục được. Thiết kế retry phải bao quanh **đúng đơn vị transaction**.

### 19.4. Quy tắc phân loại ngắn

| Tình huống | Hành động thường phù hợp |
| --- | --- |
| Business conflict rõ ràng | Trả conflict, không retry tự động |
| Duplicate business ID | Đối chiếu request cũ, không tạo ID mới tùy tiện |
| `TransientTransactionError` | Cân nhắc retry **transaction body** mới, bounded |
| `UnknownTransactionCommitResult` | Retry **commit** theo driver/session khi có thể; nếu không, đối soát |
| Socket timeout không có nhãn | Xử lý outcome unknown, không suy aborted |
| Connection/server selection fail trước khi bắt đầu | Retry có điều kiện sau khi phân loại và kiểm deadline |

Đây là khung quyết định nghiệp vụ. Luôn xem **API driver cụ thể và phiên bản server** trước khi viết retry handler.

## 20. Session thủ công bằng Java Driver: commit/abort tường minh

Để hiểu cơ chế Spring quản lý ở bên dưới, hãy xem một ví dụ dùng MongoDB Java Sync Driver trực tiếp. Không trộn ví dụ này với bean transaction của Spring trừ khi có thiết kế rõ session ownership.

### 20.1. Đoạn code minh họa

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import java.util.concurrent.TimeUnit;
import org.bson.Document;

public void approveManually(
        MongoClient client,
        String tenantId,
        String orderId) {

    TransactionOptions options = TransactionOptions.builder()
        .readPreference(ReadPreference.primary())
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(
            WriteConcern.MAJORITY.withJournal(true)
                .withWTimeout(5, TimeUnit.SECONDS))
        .build();

    try (ClientSession session = client.startSession()) {
        session.startTransaction(options);

        try {
            var database = client.getDatabase("spring_data_mongodb_lab");
            MongoCollection<Document> orders =
                database.getCollection("orders_tx_demo_007");
            MongoCollection<Document> outbox =
                database.getCollection("outbox_tx_demo_007");

            var result = orders.updateOne(
                session,
                new Document("_id", orderId)
                    .append("tenant_id", tenantId)
                    .append("state", "PENDING"),
                new Document("$set",
                    new Document("state", "APPROVED"))
            );

            if (result.getMatchedCount() != 1) {
                throw new IllegalStateException(
                    "Order is not in PENDING state");
            }

            outbox.insertOne(
                session,
                new Document("_id",
                    "order-approved:" + orderId)
                    .append("tenant_id", tenantId)
                    .append("order_id", orderId)
                    .append("eventType", "OrderApproved")
            );

            session.commitTransaction();
        } catch (RuntimeException error) {
            if (session.hasActiveTransaction()) {
                try {
                    session.abortTransaction();
                } catch (RuntimeException abortError) {
                    error.addSuppressed(abortError);
                }
            }
            throw error;
        }
    }
}
~~~

Đoạn trên chỉ minh họa **manual transaction cơ bản**:

- Mọi lệnh `updateOne`/`insertOne` nhận **cùng ClientSession**.
- `commitTransaction()` được gọi **chỉ sau khi** hai thao tác nghiệp vụ hoàn tất.
- Nếu lỗi trước commit, cố gắng `abortTransaction()` khi transaction còn active.
- `ClientSession` được đóng bằng `try-with-resources`.

**Quan trọng:** `catch RuntimeException; abort` không phải là thuật toán xử lý `UnknownTransactionCommitResult` hoàn chỉnh. Nếu mạng đứt đúng lúc commit, transaction có thể đã commit dù phía client nhận exception; không tự coi lệnh abort trong `catch` là bằng chứng commit đã được hoàn tác.

### 20.2. Không tự retry commit bằng cách bắt đầu session mới

Commit retry hợp lệ gắn với **session và transaction identity hiện có**. Khi kết quả commit chưa xác định, mở session mới rồi chạy lại toàn bộ thao tác là một request nghiệp vụ mới, không phải “retry commit cũ”.

Nếu sử dụng manual transaction trong production, dùng driver convenient transaction API hoặc triển khai transaction retry loop **theo đúng MongoDB Driver specification**, bao gồm các error labels và deadline.

### 20.3. Session không an toàn cho thao tác song song tùy tiện

Một `ClientSession`/MongoDB transaction không được chia sẻ để thực hiện nhiều operation song song trên các thread/phân nhánh reactive độc lập theo cách không được driver hỗ trợ.

**Không làm:**

~~~java
// Không chạy hai operation cùng session bằng parallelStream():
// List.of(task1, task2).parallelStream()
//     .forEach(task -> collection.insertOne(session, task));
~~~

Thao tác trong transaction cần được điều phối tuần tự hoặc theo các khả năng chính thức của driver; Spring Data không tự làm một session trở thành thread-safe.

## 21. Reactive transaction: commit sau khi publisher hoàn tất

Trong Spring Data MongoDB reactive, session/transaction context được gắn theo **Reactor Context**, không dựa vào một thread-local imperative giống `MongoTransactionManager`.

### 21.1. Transaction manager reactive

~~~java
// ReactiveMongoTxConfig.java
package com.example.transactions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTxConfig {
    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

Không dùng `MongoTransactionManager` sync để quản lý một chuỗi `ReactiveMongoTemplate`. Chọn đúng loại manager và dùng các component cùng reactive factory/session.

### 21.2. Transactional service trả `Mono<Void>`

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderApprovalService {
    private final ReactiveMongoTemplate mongo;

    public ReactiveOrderApprovalService(
            ReactiveMongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(
        transactionManager = "reactiveMongoTransactionManager"
    )
    public Mono<Void> approve(String tenantId, String orderId) {
        Query pending = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );

        return mongo.updateFirst(
                pending,
                new Update().set("state", "APPROVED"),
                OrderDocument.class
            )
            .flatMap(result -> {
                if (result.getMatchedCount() != 1) {
                    return Mono.error(
                        new OrderStateConflictException(
                            "Order not PENDING"));
                }
                return mongo.insert(new OutboxEvent(
                    "order-approved:" + orderId,
                    tenantId, orderId,
                    "OrderApproved",
                    Instant.now()
                ));
            })
            .then();
    }
}
~~~

**Điểm quan trọng:** Code trong method **tạo publisher**, không phải hoàn tất toàn bộ transaction ngay lúc `approve(...)` trả về một `Mono`. Reactive transaction interceptor quản lý lifecycle khi publisher được **subscribe** và kết thúc.

~~~text
Caller subscribe
   -> reactive transaction được mở
   -> updateFirst phát result
   -> insert outbox
   -> publisher body complete
   -> commitTransaction
   -> downstream thấy terminal completion sau transaction
~~~

Nếu `Mono.error(...)` được phát trong chuỗi transactional, interceptor thường abort transaction theo rule reactive. Nếu dùng `onErrorResume(...)` để nuốt lỗi và hoàn tất bình thường **bên trong cùng transaction flow**, bạn có thể khiến transaction đi tới commit giống bẫy `try/catch` imperative.

### 21.3. `TransactionalOperator`

Một cách lập trình tường minh:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public Mono<Void> approveWithOperator(
        String tenantId,
        String orderId,
        TransactionalOperator operator) {

    Mono<Void> operations = createApprovalPipeline(
        tenantId, orderId
    );

    return operations.as(operator::transactional);
}
~~~

`createApprovalPipeline(...)` là helper trả `Mono<Void>` gồm cả update và insert; phải dùng **cùng reactive database factory** với operator. Toán tử `transactional` quản lý transaction trong subscription scope, không biến mọi nguồn reactive nằm ngoài pipeline thành participant của transaction.

### 21.4. Không dùng `block()` trong event loop

~~~java
// Không dùng trong WebFlux event loop:
// reactiveService.approve(tenant, order).block();
~~~

Việc block có thể gây thread starvation, đánh mất lợi ích reactive và tạo các lỗi tương tác transaction context. Thiết kế controller trả `Mono<ResponseEntity<...>>` và ghép pipeline đúng lifecycle.

### 21.5. Cẩn trọng với cancellation và nhiều subscription

- Mỗi **subscription** có thể tạo một lần thực thi mới; nếu publisher không idempotent, subscribe hai lần có thể ghi hai lần.
- Cancellation có thể xảy ra trước khi transaction hoàn tất; **đừng coi client ngắt kết nối HTTP là bằng chứng MongoDB đã rollback** nếu commit đã bắt đầu hoặc kết quả chưa rõ.
- Không chạy `parallel()` hay mở nhiều nhánh chia sẻ transaction session khi driver không hỗ trợ transaction operations song song.
- Test bằng `StepVerifier` và kiểm database persisted state; không chỉ test `Mono.empty()`.

## 22. MongoDB transaction có những giới hạn vận hành nào?

### 22.1. Transaction không nên kéo dài

Multi-document transaction giữ snapshot và tài nguyên cần thiết. MongoDB có thời gian sống transaction mặc định và server parameter `transactionLifetimeLimitSeconds`; transaction quá dài có thể bị abort theo cấu hình.

**Không**:

~~~java
@Transactional
public void approveAndWaitForExternalResponse(...) {
    updateOrder(...);
    httpClient.callSlowPaymentGateway(...); // chờ network bên ngoài
    insertOutbox(...);
}
~~~

Nên làm transaction MongoDB **ngắn**, chỉ chứa thao tác DB cần nguyên tử. Các workflow ngoài database dùng state machine/outbox/saga, không giữ transaction mở chờ mạng.

### 22.2. Lock contention, write conflict và transaction abort

Hai transaction cùng cập nhật một document có thể xảy ra write conflict. Một transaction bị abort có thể cần retry toàn body, nhưng retry phải đánh giá lại predicate nghiệp vụ với dữ liệu mới.

`@Transactional` **không bảo đảm** mọi transaction đồng thời sẽ hoàn tất; nó tạo cơ chế atomicity/isolation trong giới hạn MongoDB, còn contention/retry vẫn phải xử lý.

### 22.3. Collection/index DDL và transaction

MongoDB hỗ trợ một số thao tác tạo collection/index trong transaction với điều kiện/phụ thuộc phiên bản, topology và ràng buộc. Tuy nhiên code production không nên tự tạo collection/index **ngay trong workflow giao dịch mỗi request**.

**Thực hành tốt:** tạo collection, index và validator qua migration/deployment trước khi nhận traffic; integration test cũng nên tạo fixture collection bên ngoài transaction để tránh lỗi không liên quan rollback.

### 22.4. Sharded transactions và write concern

Trên sharded cluster, transaction phối hợp nhiều shard có thêm chi phí điều phối commit và phụ thuộc topology. `WriteConcern.MAJORITY` của commit ảnh hưởng durability, còn atomicity của transaction do cơ chế commit phân tán quản lý.

Không giả định latency/giới hạn giống hệt single replica set, và không dùng một test đơn node để khẳng định đã kiểm đúng distributed commit.

### 22.5. Không đặt write concern cho từng operation trong transaction

Theo MongoDB, write concern cần được đặt **ở transaction level**, đặc biệt cho `commitTransaction`. Một số API driver sẽ từ chối hoặc không áp write concern riêng trên operation chạy trong transaction.

Không làm:

~~~javascript
// Không thiết kế transactional operation kiểu:
// session.startTransaction(...);
// db.collection.updateOne(..., { writeConcern: { w: 1 } });
// db.collection.insertOne(..., { writeConcern: { w: "majority" } });
// session.commitTransaction();
~~~

Thay vào đó, xác định durability policy của **toàn transaction** và dùng transaction options.

### 22.6. Transaction và index uniqueness

Unique index vẫn được cưỡng chế trong transaction. Một transaction insert hai document có cùng unique key hoặc xung đột với document ngoài có thể thất bại. Đừng trông chờ transaction cho phép “vi phạm tạm thời rồi xử lý trước commit” trong mọi tình huống như một số constraint deferred của relational database.

## 23. Integration test: kiểm commit, rollback và checked exception

Đây là phần bắt buộc nếu muốn chứng minh `@Transactional` thật sự hoạt động trong Spring Data MongoDB.

### 23.1. Điều kiện test

- MongoDB test instance đã cấu hình **replica set**, không phải standalone.
- Transaction manager bean `mongoTransactionManager` được tạo trong application context.
- Service là **Spring bean/proxy**, không tự `new`.
- `MongoTemplate` và transaction manager dùng **cùng MongoDatabaseFactory**.
- Các collection đã có hoặc được tạo **trước transaction**.
- **Không đặt `@Transactional` trên method test** rồi dùng chính rollback của test thay cho kiểm business service: cần quan sát kết quả sau khi **service proxy** commit/abort.
- Dùng fixture ID riêng và cleanup chính xác; không dùng collection/DB dùng chung.

### 23.2. Bổ sung method checked để test

Thêm vào `OrderApprovalService` của mục 7:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager"
)
public void checkedDefault(String tenantId, String orderId)
        throws BusinessRuleException {
    applyApproval(tenantId, orderId);
    throw new BusinessRuleException("Checked exception");
}

@Transactional(
    transactionManager = "mongoTransactionManager",
    rollbackFor = BusinessRuleException.class
)
public void checkedRollback(String tenantId, String orderId)
        throws BusinessRuleException {
    applyApproval(tenantId, orderId);
    throw new BusinessRuleException("Checked exception");
}

@Transactional(
    transactionManager = "mongoTransactionManager"
)
public void swallowUnchecked(String tenantId, String orderId) {
    applyApproval(tenantId, orderId);
    try {
        throw new IllegalStateException("Non-database error");
    } catch (IllegalStateException ignored) {
        // Intentionally swallowed to demonstrate unexpected commit.
    }
}
~~~

Các method ví dụ này được gọi từ **bean khác qua proxy**. Trong test, nên dùng **mỗi order ID cho một case** để không ảnh hưởng nhau.

### 23.3. Integration test với Spring Boot test slice

~~~java
package com.example.transactions;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import({MongoTxConfig.class, OrderApprovalService.class})
class OrderApprovalTransactionTest {
    @Autowired MongoTemplate template;
    @Autowired OrderApprovalService service;

    private static final String TENANT = "test-tenant-tx007";
    private static final String COMMIT_ID = "tx007-commit";
    private static final String ROLLBACK_ID = "tx007-rollback";
    private static final String CHECKED_ID = "tx007-checked";
    private static final String CHECKED_RB_ID = "tx007-checked-rb";
    private static final String SWALLOW_ID = "tx007-swallow";

    @BeforeEach
    void prepare() {
        // Cleanup an toàn chỉ trên MongoDB test database.
        cleanup();

        for (String id : new String[] {
                COMMIT_ID, ROLLBACK_ID,
                CHECKED_ID, CHECKED_RB_ID, SWALLOW_ID }) {

            template.insert(new OrderDocument(
                id, TENANT, "PENDING", 100000L
            ));
        }
    }

    @AfterEach
    void cleanup() {
        for (String id : new String[] {
                COMMIT_ID, ROLLBACK_ID,
                CHECKED_ID, CHECKED_RB_ID, SWALLOW_ID }) {

            template.remove(
                org.springframework.data.mongodb.core.query.Query.query(
                    org.springframework.data.mongodb.core.query.Criteria
                        .where("id").is(id)
                ),
                OrderDocument.class
            );

            template.remove(
                org.springframework.data.mongodb.core.query.Query.query(
                    org.springframework.data.mongodb.core.query.Criteria
                        .where("id").is("order-approved:" + id)
                ),
                OutboxEvent.class
            );
        }
    }

    @Test
    void commitsOrderAndOutboxTogether() {
        service.approve(TENANT, COMMIT_ID);

        assertThat(template.findById(
            COMMIT_ID, OrderDocument.class
        ).getState()).isEqualTo("APPROVED");

        assertThat(template.findById(
            "order-approved:" + COMMIT_ID, OutboxEvent.class
        )).isNotNull();
    }

    @Test
    void uncheckedExceptionAbortsBothChanges() {
        assertThatThrownBy(() ->
            service.approveThenFail(TENANT, ROLLBACK_ID)
        ).isInstanceOf(IllegalStateException.class);

        assertPendingWithoutOutbox(ROLLBACK_ID);
    }

    @Test
    void checkedExceptionCommitsByDefault() {
        assertThatThrownBy(() ->
            service.checkedDefault(TENANT, CHECKED_ID)
        ).isInstanceOf(BusinessRuleException.class);

        assertThat(template.findById(
            CHECKED_ID, OrderDocument.class
        ).getState()).isEqualTo("APPROVED");
        assertThat(template.findById(
            "order-approved:" + CHECKED_ID,
            OutboxEvent.class
        )).isNotNull();
    }

    @Test
    void rollbackForCheckedAbortsBothChanges() {
        assertThatThrownBy(() ->
            service.checkedRollback(TENANT, CHECKED_RB_ID)
        ).isInstanceOf(BusinessRuleException.class);

        assertPendingWithoutOutbox(CHECKED_RB_ID);
    }

    @Test
    void swallowedJavaExceptionStillCommits() {
        service.swallowUnchecked(TENANT, SWALLOW_ID);

        assertThat(template.findById(
            SWALLOW_ID, OrderDocument.class
        ).getState()).isEqualTo("APPROVED");
        assertThat(template.findById(
            "order-approved:" + SWALLOW_ID,
            OutboxEvent.class
        )).isNotNull();
    }

    private void assertPendingWithoutOutbox(String orderId) {
        assertThat(template.findById(
            orderId, OrderDocument.class
        ).getState()).isEqualTo("PENDING");

        assertThat(template.findById(
            "order-approved:" + orderId,
            OutboxEvent.class
        )).isNull();
    }
}
~~~

**Điểm cần cấu hình khi chạy thật:** Ví dụ dùng `@DataMongoTest` theo Spring Boot 3.x. Với Spring Boot 4 hoặc cấu trúc project khác, package của test slice có thể đổi; hãy dùng annotation tương ứng. Cần replica set test đã chạy sẵn/Testcontainers có cấu hình, và test không tự thay các file/build của project.

### 23.4. Giải thích kết quả test

| Test | Outcome thật sau service proxy |
| --- | --- |
| `commitsOrderAndOutboxTogether` | Cả order và outbox tồn tại |
| `uncheckedExceptionAbortsBothChanges` | Order vẫn PENDING, không outbox |
| `checkedExceptionCommitsByDefault` | Exception được ném ra nhưng dữ liệu **đã commit** |
| `rollbackForCheckedAbortsBothChanges` | Checked exception có cấu hình → rollback |
| `swallowedJavaExceptionStillCommits` | Lỗi Java bị catch → normal return → commit |

Các test khẳng định **hành vi đã persisted** bằng query sau lời gọi service, thay vì assert duy nhất exception class.

### 23.5. Test self-invocation và transaction thật

Tạo thêm hai service:

~~~java
@Service
public class BrokenFacade {
    public void run(String tenantId, String orderId) {
        this.inner(tenantId, orderId); // bypass proxy
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void inner(String tenantId, String orderId) {
        // update + insert + throw
    }
}
~~~

Với `BrokenFacade.run(...)`, nếu thân `inner` không nhận transaction của outer context, các write có thể **đã commit riêng lẻ** trước khi throw. Để test, chỉ dùng data fixture riêng, kiểm trạng thái collection và so sánh với phiên bản gọi **qua bean transactional khác**.

### 23.6. Test lỗi commit là bài test khác

Test ném `IllegalStateException` trong body kiểm **rollback rule**, nhưng không giả lập đúng `UnknownTransactionCommitResult`. Muốn test commit ambiguity thực:

- Dùng môi trường chaos riêng có khả năng kiểm soát mạng/primary stepdown.
- Inject lỗi vào ranh giới commit hoặc dùng driver/test harness phù hợp.
- Ghi nhận server state bằng idempotency key và read policy đã định.
- Không giả định body exception tương đương commit exception.

## 24. Reactive integration test với `StepVerifier`

Với bean reactive đã cấu hình manager tương ứng, có thể kiểm:

~~~java
import reactor.test.StepVerifier;

@Test
void reactiveApprovalCommitsAfterComplete() {
    StepVerifier.create(
        reactiveService.approve(
            "test-tenant-tx007", "rx007-commit"
        )
    ).verifyComplete();

    StepVerifier.create(
        reactiveTemplate.findById(
            "rx007-commit", OrderDocument.class
        )
    )
      .assertNext(order ->
          assertThat(order.getState())
              .isEqualTo("APPROVED")
      )
      .verifyComplete();
}
~~~

Trước test cần insert `rx007-commit` ở trạng thái `PENDING` bằng **reactive test template** và tạo collection trước transaction. Tương tự, test lỗi reactive:

~~~java
StepVerifier.create(
    reactiveService.approve(
        "wrong-tenant", "rx007-rollback"
    )
)
  .expectError(OrderStateConflictException.class)
  .verify();
~~~

Sau đó kiểm order vẫn PENDING và không có outbox. Đừng chỉ assert `expectError`; lỗi có thể được phát **sau một write ngoài transaction** nếu cấu hình proxy/transaction manager sai.

**Lưu ý:** reactive publisher phải được subscribe. Nếu test chỉ tạo:

~~~java
Mono<Void> pipeline = reactiveService.approve(...);
~~~

rồi không subscribe, các lệnh ghi thường **chưa chạy**; test đó không chứng minh commit hay rollback.

## 25. Chẩn đoán những sai lầm phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách điều tra/sửa |
| --- | --- | --- |
| Method ném RuntimeException nhưng order vẫn đổi | Chưa có transaction manager, self-invocation, template khác factory hoặc write ngoài transaction | Xem proxy/factory/session và integration test |
| Checked exception nhưng DB đã commit | Spring mặc định không rollback checked exception | `rollbackFor` theo contract hoặc đổi exception type |
| Method catch lỗi và return false, DB vẫn commit | Exception không thoát proxy | Rethrow/mark rollback-only nếu đúng nghiệp vụ |
| Outer catch inner RuntimeException rồi nhận `UnexpectedRollbackException` | Inner đã đánh dấu transaction chung rollback-only | Thiết kế propagation và error handling rõ |
| `@Transactional` trên private method không hoạt động | Spring proxy không intercept internal/private call | Đưa transaction lên entry-point qua proxy |
| Dùng `REQUIRES_NEW` nhưng outer rollback vẫn còn audit inner | Inner commit độc lập | Chỉ dùng khi yêu cầu tách transaction thật sự |
| `NESTED` thất bại | MongoDB không hỗ trợ savepoint như JDBC | Không giả định nested rollback; thiết kế lại |
| Service return bình thường nhưng caller nhận exception | Commit lỗi sau thân method | Phân loại commit error/unknown outcome |
| Client timeout rồi retry, tạo hai side effect | Không có idempotency | Khóa nghiệp vụ ổn định, đối soát, retry bounded |
| Bắt MongoDB write error nhưng commit vẫn lỗi | Transaction server đã abort/doomed | Không tiếp tục dùng transaction đã hỏng |
| Gửi email trước commit, DB rollback | Side effect ngoài MongoDB không được abort | Outbox/afterCommit và idempotency |
| Listener `AFTER_COMMIT` bỏ lỡ sự kiện khi process crash | In-memory callback không bền vững | Durable outbox |
| Ghi trong `AFTER_COMMIT` không thấy persisted | Dùng tài nguyên completion mà không tạo tx mới | Tách worker hoặc `REQUIRES_NEW` đúng |
| `MongoTemplate` không tham gia transaction | Khác `MongoDatabaseFactory` hoặc dùng driver không gắn session | Đồng nhất manager/factory, test cả hai collection |
| Transaction trên standalone báo lỗi | Topology không hỗ trợ | Dùng test replica set |
| Reactive `Mono` tạo rồi không ghi | Chưa subscribe | Dùng WebFlux chain/StepVerifier |
| Reactive error bị `onErrorResume` nuốt, DB commit | Chuỗi kết thúc bình thường trước interceptor | Đặt error handling ngoài transaction hoặc rollback rule rõ |
| Transaction quá lâu, bị abort | Snapshot/lock/resource timeout | Giữ transaction ngắn, đưa HTTP call ra ngoài |
| Test `@Transactional` rollback sau test làm che kết quả | Test transaction chưa commit | Test business service không nằm trong test rollback scope |
| Test một node PASS nhưng failover thực vẫn lỗi | Chưa test nhiều thành viên/chaos | Test topology đúng và failure injection riêng |

## 26. Checklist review một workflow MongoDB transaction

1. **Xác định đúng atomic boundary:** những write nào bắt buộc cùng commit/abort?
2. **Dùng transaction khi cần nhiều document/collection**, không thay atomic single-document operation bằng transaction vô ích.
3. **Kiểm replica set/sharded topology** và tạo collection/index trước transaction.
4. **Cấu hình `MongoTransactionManager` hoặc reactive manager** đúng hạ tầng.
5. **Bảo đảm cùng factory/session**, không trộn driver khác client vào cùng kỳ vọng atomicity.
6. **Đặt transaction ở public service boundary đi qua proxy**, không dựa vào self-invocation.
7. **Đặt điều kiện nghiệp vụ trong write predicate** (tenant, state, version), không nghĩ transaction thay thế optimistic locking.
8. **Kiểm rollback rules:** unchecked, checked, `rollbackFor`, `noRollbackFor`.
9. **Không nuốt exception**; nếu đã catch, xác định có cần rethrow/rollback-only không.
10. **Review propagation**, nhất là `REQUIRES_NEW` và `UnexpectedRollbackException`.
11. **Không giả định MongoDB có savepoint/nested rollback**.
12. **Hiểu commit xảy ra sau method body**, caller chỉ thấy thành công qua proxy khi commit đã hoàn tất.
13. **Chọn commit write concern** dựa trên độ bền dữ liệu và failover policy.
14. **Phân biệt body error với commit error**; quản lý `UnknownTransactionCommitResult` và `TransientTransactionError`.
15. **Retry có giới hạn và idempotent**, không retry lệnh tăng/giảm tiền như một request mới.
16. **Đưa side effect ngoài DB sang outbox** hoặc thiết kế AFTER_COMMIT có giới hạn rõ.
17. **Không giữ transaction mở chờ HTTP**, email hay xử lý CPU dài.
18. **Dùng reactive manager + Reactor Context** cho reactive operation, tránh blocking/parallel session.
19. **Test với MongoDB replica set thật**, không chỉ mock repository.
20. **Assert persisted state sau proxy call**, cả hai collection, với fixture riêng và không bọc test trong rollback scope.
21. **Theo dõi metric lỗi commit/rollback, write conflict và latency**, kết hợp quy trình phục hồi.

## 27. Bài thực hành có đáp án

### Bài 1 — Điểm commit

Một method có `@Transactional` đã đi tới dòng `return;`. Có thể khẳng định MongoDB commit xong chưa?

**Đáp án:** Chưa. Khi lời gọi đi qua Spring proxy, transaction interceptor thường commit **sau khi thân method return**, trước khi caller nhận kết quả thành công từ proxy.

### Bài 2 — Unchecked exception

Trong service transactional, đã update order và insert outbox rồi ném `IllegalStateException`. Dữ liệu sẽ ra sao nếu manager/session đúng và rollback thành công?

**Đáp án:** Transaction được abort; order trở về trạng thái chưa được commit và outbox không được tạo.

### Bài 3 — Checked exception

Sau hai write, method ném `BusinessRuleException extends Exception` nhưng không có `rollbackFor`. Mặc định Spring làm gì?

**Đáp án:** Mặc định commit nếu transaction còn hợp lệ, dù exception checked được ném ra caller. Cần khai báo `rollbackFor` nếu lỗi ấy phải hủy workflow.

### Bài 4 — `rollbackFor`

Viết annotation để rollback khi method ném `BusinessRuleException`.

**Đáp án:**

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    rollbackFor = BusinessRuleException.class
)
~~~

### Bài 5 — `noRollbackFor`

Một method ném unchecked `NonFatalNotificationException` nhưng nghiệp vụ vẫn muốn commit dữ liệu. Có thể dùng gì?

**Đáp án:** Cân nhắc `noRollbackFor = NonFatalNotificationException.class` có chủ đích. Nhưng nếu server/transaction đã abort hoặc marked rollback-only, rule không làm transaction bất khả thi trở nên commit được.

### Bài 6 — Bắt lỗi

Method bắt `IllegalStateException` do code tự tạo rồi `return false`. Spring proxy có tự biết phải rollback không?

**Đáp án:** Không; exception không thoát qua proxy. Transaction có thể commit nếu vẫn hợp lệ, dù service trả false.

### Bài 7 — Rollback-only

Khi cần return một business result nhưng muốn abort, dùng API nào trong imperative `@Transactional`?

**Đáp án:** `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` trong transaction context đang hoạt động; hoặc dùng `TransactionTemplate` và `status.setRollbackOnly()`.

### Bài 8 — Inner transaction và outer catch

Outer `@Transactional(REQUIRED)` gọi inner `@Transactional(REQUIRED)` qua bean khác. Inner ném RuntimeException, outer catch rồi return bình thường. Vì sao caller có thể nhận `UnexpectedRollbackException`?

**Đáp án:** Inner interceptor đã đánh dấu **transaction chung** rollback-only. Outer cố commit một transaction không thể commit và Spring báo rollback ngoài dự kiến.

### Bài 9 — `REQUIRES_NEW`

Inner dùng `REQUIRES_NEW` để ghi audit, commit; outer sau đó rollback. Audit có được giữ không?

**Đáp án:** Có thể vẫn giữ vì inner dùng transaction độc lập. Chỉ dùng khi đó là mục đích nghiệp vụ, không phải cách chữa bừa mọi rollback.

### Bài 10 — `NESTED`

MongoDB có cho rollback một nested savepoint bên trong cùng session transaction như JDBC không?

**Đáp án:** Không có savepoint/nested transaction tương đương để tùy ý rollback một phần. `Propagation.NESTED` không nên được giả định hỗ trợ trong `MongoTransactionManager`.

### Bài 11 — Self-invocation

`this.approveInTransaction()` có gọi qua proxy transaction không?

**Đáp án:** Trong mô hình Spring AOP proxy thông thường, không. Chuyển lời gọi qua một Spring bean khác hoặc đặt `@Transactional` trên entry-point public được gọi từ ngoài.

### Bài 12 — MongoTemplate khác factory

Order update dùng template A trong transaction S1, outbox insert dùng driver MongoClient B. Cả hai có cùng rollback không?

**Đáp án:** Không mặc nhiên. Thao tác B không tự tham gia session S1; cần dùng cùng factory/session mechanism hoặc thiết kế transaction coordination đúng.

### Bài 13 — Side effect ngoài database

Ứng dụng gửi email trước khi Spring commit. Sau đó MongoDB commit thất bại. Email có tự được thu hồi không?

**Đáp án:** Không. Dùng outbox hoặc sau-commit workflow và chấp nhận/giải quyết failure mode của external delivery.

### Bài 14 — AFTER_COMMIT

`@TransactionalEventListener(phase=AFTER_COMMIT)` có thay thế durable outbox không?

**Đáp án:** Không. Callback chạy sau commit thành công nhưng có thể bị mất khi process crash hoặc gửi thất bại. Outbox persisted giúp retry và đối soát.

### Bài 15 — Commit uncertainty

Server có thể đã commit, nhưng phản hồi `commitTransaction` bị mất do mạng. Có nên bắt đầu transaction mới rồi lặp lại toàn bộ workflow không?

**Đáp án:** Không tự động. Đây là unknown commit outcome; retry **commit hiện có** theo driver/session khi phù hợp hoặc đối soát idempotency key. Retry body như request mới có thể tạo duplicate.

### Bài 16 — Error labels

Khác biệt giữa `TransientTransactionError` và `UnknownTransactionCommitResult`?

**Đáp án:** Transient transaction error có thể dẫn tới retry **toàn transaction body mới**; unknown commit result chủ yếu yêu cầu xử lý/retry **commit**, không giả định transaction đã abort.

### Bài 17 — Reactive

Một `Mono<Void>` được tạo từ method reactive transactional nhưng chưa subscribe. Transaction đã chạy chưa?

**Đáp án:** Thông thường chưa; publisher reactive thường lazy. Cần subscriber/StepVerifier hoặc WebFlux pipeline để thực thi và quan sát commit/rollback.

### Bài 18 — Reactive error swallowing

`Mono.error(...)` bị `onErrorResume(e -> Mono.empty())` xử lý bên trong transaction pipeline. Có rủi ro gì?

**Đáp án:** Pipeline có thể complete bình thường và interceptor đi tới commit nếu transaction/server chưa bị abort. Đặt error recovery đúng ranh giới và test database state.

### Bài 19 — Test đáng tin

Test ném unchecked exception và assert exception type, nhưng không kiểm DB. Đã chứng minh rollback chưa?

**Đáp án:** Chưa. Exception có thể xuất hiện sau một số write ngoài transaction. Phải đọc lại order/outbox sau khi lời gọi proxy kết thúc, trong MongoDB replica set test.

### Bài 20 — Test chạy trên standalone

MongoDB standalone trả lỗi khi bắt đầu multi-document transaction. Có nên sửa bài bằng cách tắt transaction trong test không?

**Đáp án:** Không. Dùng replica set test (single-node replica set đủ cho behavior commit/abort cơ bản); test failover thì dùng nhiều node.

### Bài 21 — Write concern tại commit

Đặt `WriteConcern.MAJORITY` vào mỗi insert/update trong MongoDB transaction có đúng contract không?

**Đáp án:** Không; MongoDB transaction đặt write concern ở **transaction/commit level**. Cấu hình qua `TransactionOptions`/transaction manager.

### Bài 22 — Thời gian transaction

Một transaction giữ mở 60 giây để chờ cổng thanh toán HTTP. Rủi ro?

**Đáp án:** Giữ snapshot/lock/resource, tăng write conflicts và có thể bị lifetime limit abort. Tách external workflow, dùng outbox/saga/state machine.

### Bài 23 — Dữ liệu nào được hủy?

Transaction cập nhật order và outbox rồi abort. Nhưng service đã ghi log và gửi HTTP request trước đó. Những side effect nào được MongoDB hủy?

**Đáp án:** Những thay đổi **trong cùng MongoDB transaction** bị abort; log đã ghi và HTTP request bên ngoài **không** được tự động thu hồi.

### Bài 24 — Commit `w:1`

Transaction đã commit với `w:1`. Có thể khẳng định transaction đã được majority-journaled và không rollback sau election không?

**Đáp án:** Không. Atomic commit và durability là hai thuộc tính riêng; cân nhắc commit write concern majority/journal theo yêu cầu.

## Tài liệu tham khảo

- [Spring Data MongoDB — Client Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, `ReactiveMongoTransactionManager`, `@Transactional`, programmatic transactions, session binding và transaction options.
- [Spring Data MongoDB — `MongoTransactionManager` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/MongoTransactionManager.html): transaction lifecycle, configuration và các giới hạn.
- [Spring Data MongoDB — `ReactiveMongoTransactionManager` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/ReactiveMongoTransactionManager.html): reactive transaction/session management.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): RuntimeException/Error, checked exception, `rollbackFor`, `noRollbackFor`, rollback-only và proxy boundary.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED` và `UnexpectedRollbackException`.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` và trạng thái rollback-only.
- [Spring Framework — `@TransactionalEventListener`](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): AFTER_COMMIT, AFTER_ROLLBACK và giao tiếp với tài nguyên transaction.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): atomicity, session, topology, isolation và giới hạn vận hành.
- [MongoDB Manual — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/): contention, lifetime limits, DDL và resource management.
- [MongoDB Manual — Commit Transaction Command](https://www.mongodb.com/docs/manual/reference/command/commitTransaction/): commit write concern, acknowledgment và hành vi timeout/commit.
- [MongoDB Manual — Abort Transaction Command](https://www.mongodb.com/docs/manual/reference/command/abortTransaction/): abort semantics.
- [MongoDB Manual — Retry Transactions](https://www.mongodb.com/docs/manual/core/transactions-in-applications/): `TransientTransactionError`, `UnknownTransactionCommitResult` và retry loops.
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/): manual sessions, transaction API và retry guidelines.
- [MongoDB Java Reactive Streams Driver — Transactions](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/write/transactions/): reactive transaction publisher lifecycle.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): commit durability, majority, journal và rollback risk.
