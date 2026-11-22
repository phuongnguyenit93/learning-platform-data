# Sự kiện nghiệp vụ sau commit và xử lý tác động phụ an toàn

> **Chương:** Vòng đời và callback  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Phân biệt callback vòng đời entity và sự kiện nghiệp vụ sau commit; hiểu `@TransactionalEventListener` với các phase, bẫy không có transaction và xử lý lỗi; dùng transaction MongoDB đúng cách; thiết kế transactional outbox, idempotency, retry/claim/lease cho tác động phụ quan trọng; viết integration test quan sát trạng thái DB và hành vi sau commit/rollback.

## 1. Vấn đề nghiệp vụ: lưu đơn hàng rồi gửi thông báo

Giả sử khách hàng duyệt một đơn hàng. Hệ thống phải:

1. Chuyển order từ `PENDING` sang `APPROVED` trong MongoDB.
2. Phát sự kiện `OrderApproved` để gửi email, gọi API kho hoặc cập nhật hệ thống khác.

Một cách triển khai trông hợp lý:

~~~java
public void approve(String orderId) {
    repository.save(approvedOrder);
    emailClient.sendApprovedNotice(orderId);
}
~~~

Nhưng code đó có những khả năng lỗi:

- Database ghi thất bại **sau khi** email đã gửi.
- Email client timeout nhưng phía nhận **đã gửi email**; retry gây gửi hai lần.
- Trong transaction, `save(...)` hoàn thành nhưng transaction **chưa commit**. Email gửi ngay trong method có thể thông báo một sự kiện không bao giờ được commit.
- Transaction đã commit nhưng ứng dụng **crash trước khi phát email**.
- Cùng một request được client gửi lại, tạo sự kiện/thông báo trùng.

Không có một callback đơn giản nào tự loại bỏ tất cả các rủi ro này.

### 1.1. Hai mức yêu cầu thường gặp

| Yêu cầu | Thiết kế thường phù hợp |
| --- | --- |
| “Nếu đã commit thì *cố gắng* thông báo ngay; đôi khi bỏ lỡ được” | Spring `@TransactionalEventListener(AFTER_COMMIT)` |
| “Mọi order đã commit phải có bản ghi công việc để gửi/đối soát về sau” | **Transactional outbox** được ghi cùng MongoDB transaction |
| “Gửi được email thì rollback được nếu MongoDB lỗi” | **Không** thể rollback email bằng MongoDB transaction |
| “Không bao giờ nhận hai message ở hệ thống ngoài” | Không thể suy từ `AFTER_COMMIT`; cần idempotency/đảm bảo delivery phía consumer |

### 1.2. Sơ đồ khái niệm

~~~mermaid
flowchart TD
    A["Client yêu cầu duyệt đơn"] --> B["Transaction: update order"]
    B --> C{"Chọn chiến lược sự kiện"}
    C -->|"Best effort"| D["Publish domain event trong transaction"]
    D --> E["Commit MongoDB"]
    E -->|"Thành công"| F["AFTER_COMMIT listener"]
    F --> G["Gọi email / API ngoài"]
    C -->|"Durable"| H["Insert outbox trong cùng transaction"]
    H --> I["Commit order + outbox cùng nhau"]
    I --> J["Worker đọc outbox đã commit"]
    J --> K["Gửi external event với eventId"]
    K --> L["Ghi nhận delivered / retry"]
~~~

**Phân biệt:** best-effort listener gắn với **tiến trình ứng dụng đang chạy**, còn outbox gắn với một **bản ghi được persist** trong cùng transaction. Không gọi chúng là hai cách tương đương về mức bảo đảm.

## 2. Từ khóa: entity callback, application event, transaction synchronization, outbox

| Khái niệm | Kích hoạt | Mục đích | Có phải sau commit? |
| --- | --- | --- | --- |
| `BeforeConvertCallback<T>` | Trước chuyển entity sang BSON | Chuẩn hóa field, sinh giá trị kỹ thuật | **Không** |
| `BeforeSaveCallback<T>` | Sau convert, trước save | Điều chỉnh entity/BSON theo contract callback | **Không** |
| `AfterSaveCallback<T>` | Sau thao tác save trong mapping pipeline | Xử lý lifecycle của entity | **Không bảo đảm** |
| `AfterSaveEvent<T>` / `AbstractMongoEventListener` | Mapping event do Spring Data phát | Quan sát mapping lifecycle | **Không bảo đảm** |
| `ApplicationEventPublisher.publishEvent(...)` | Khi code gọi publisher | Phát event trong process | **Không tự đợi commit** |
| `@EventListener` | Application event được phát | Xử lý event không gắn phase commit | **Không** |
| `@TransactionalEventListener(AFTER_COMMIT)` | Transaction synchronization ở phase commit thành công | Side effect *sau* commit | **Có**, nếu event gắn với transaction |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Transaction hoàn tất bằng rollback | Telemetry/cleanup phù hợp | **Sau rollback** |
| Transactional outbox | Bản ghi outbox được ghi trong cùng transaction | Giao việc bền vững cho worker | Gửi **sau** khi record đã commit |
| Change stream | MongoDB công bố thay đổi đã được quan sát qua stream | CDC/consumer event | Phụ thuộc resume token, pipeline và durability; không thay outbox tùy tiện |

### 2.1. “After save” không đồng nghĩa “after commit”

Với `MongoTemplate.save` hay repository save:

~~~text
MongoDB transaction T1 started
    |
    +-- BeforeConvert
    +-- BeforeSave
    +-- MongoDB write trong T1
    +-- AfterSave
    |
    +-- service method tiếp tục
    +-- Có thể NÉM exception
    +-- transaction T1 ABORT
~~~

`AfterSaveCallback` vẫn đã chạy dù không có bản ghi được commit. Nếu callback lập tức gửi email/HTTP, bên ngoài đã nhận side effect nhưng database không lưu kết quả.

Trong một thao tác không có multi-document transaction, save được xác nhận theo write concern áp dụng; vẫn không nên suy ra lifecycle callback bảo đảm độ bền qua failover hoặc delivery external.

### 2.2. Callback phù hợp với thao tác “gần entity”

Ví dụ `BeforeConvertCallback`:

~~~java
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderNormalizationCallback
        implements BeforeConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument order,
            String collection) {
        // Ví dụ chỉ nên thực hiện biến đổi đồng bộ/deterministic
        // như điền field kỹ thuật hoặc validate.
        return order;
    }
}
~~~

Không dùng callback này gọi email service, publish event ra message broker hoặc bắt đầu transaction phụ cho mọi lần save.

### 2.3. Bulk/template operations có thể không đi qua lifecycle như `save`

`updateFirst`, `updateMulti`, aggregation update, bulk operations và raw driver không đồng nhất với pipeline `repository.save` về callback/event. **Không đặt logic nghiệp vụ thiết yếu chỉ trong `AfterSaveCallback`** nếu hệ thống cũng cập nhật dữ liệu bằng những API khác.

Ví dụ chuyển trạng thái:

~~~java
template.updateFirst(query, update, OrderDocument.class);
~~~

có thể cập nhật một document mà **không phát `AfterSaveCallback<OrderDocument>`** vì không có thao tác convert/save entity theo đường như `save`. Điểm phát domain event nên nằm ở **application service** sau khi biết write thực sự có ý nghĩa, không đoán từ một callback không chạy trên mọi đường ghi.

## 3. MongoDB transaction là nền tảng cho “sau commit”

Muốn `AFTER_COMMIT` có ý nghĩa cho **nhiều write MongoDB**, cần một transaction thực sự.

### 3.1. Topology và hạ tầng

- Dùng MongoDB **replica set** hoặc sharded deployment hỗ trợ transactions; standalone không đáp ứng multi-document transaction.
- Tạo collections/indexes trước khi mở transaction trong luồng request quan trọng.
- `MongoTemplate` và `MongoTransactionManager` phải sử dụng database factory/session phù hợp.
- Service phải được gọi **qua Spring transactional proxy**; tự gọi method transactional bằng `this...` có thể bỏ qua proxy.
- Chọn commit write concern phù hợp. **Atomic commit không tự đồng nghĩa durable majority** nếu policy chỉ `w:1`.

### 3.2. Manager đồng bộ

~~~java
// MongoTransactionConfig.java
package com.example.mongoevents;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .readPreference(ReadPreference.primary())
            .writeConcern(
                WriteConcern.MAJORITY.withJournal(true))
            .build();

        return new MongoTransactionManager(factory, options);
    }
}
~~~

`MongoTransactionManager` tạo và quản lý `ClientSession` theo ngữ cảnh transaction của Spring. Transaction options đặt `writeConcern` ở cấp **commit**, không nhồi mỗi insert/update trong transaction một concern khác.

**Lưu ý vận hành:** Single-node replica set đủ cho integration test cơ bản, nhưng `majority` trên một node **không chứng minh** khả năng chịu failover đa node. Production cần topology nhiều data-bearing members nếu mục tiêu là replication durability.

### 3.3. Read concern và khái niệm “đã commit”

Commit thành công theo transaction write concern **không tự làm mọi secondary thấy dữ liệu tức thì**. Khi consumer đọc secondary, phải tính replication lag, read concern và session/causal consistency. Với outbox, worker nên dùng query/read preference nhất quán, không suy “sau commit” đồng nghĩa “mọi node đều ngay lập tức đã apply”.

## 4. Fixture nghiệp vụ và entity

Ví dụ dùng hai collections:

~~~text
orders_events_011
  _id: "order-011-01"
  tenant_id: "t01"
  state: "PENDING"

outbox_events_011
  _id: "order-approved:order-011-01"
  tenant_id: "t01"
  aggregate_id: "order-011-01"
  kind: "OrderApproved"
  status: "PENDING"
~~~

### 4.1. Khởi tạo môi trường test

Chỉ chạy trong database **test riêng**:

~~~javascript
use spring_data_mongodb_lab

db.createCollection("orders_events_011");
db.createCollection("outbox_events_011");

db.orders_events_011.insertOne({
  _id: "order-011-01",
  tenant_id: "t01",
  state: "PENDING",
  amount_vnd: NumberLong(250000)
});

db.outbox_events_011.createIndex(
  { status: 1, next_attempt_at: 1, _id: 1 },
  { name: "ix_outbox_due" }
);

db.outbox_events_011.createIndex(
  { tenant_id: 1, aggregate_id: 1, kind: 1 },
  { name: "ix_outbox_aggregate" }
);
~~~

Collection `_id` luôn có unique index. Index truy vấn outbox là ví dụ khởi điểm; cấu trúc index phải đánh giá theo filter, sort, throughput và kích thước collection thực.

### 4.2. `OrderDocument`

~~~java
// OrderDocument.java
package com.example.mongoevents;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_events_011")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String state;

    @Field("amount_vnd")
    private long amountVnd;

    protected OrderDocument() {}

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
}
~~~

### 4.3. Event domain không phụ thuộc cơ chế gửi

~~~java
// OrderApproved.java
package com.example.mongoevents;

public record OrderApproved(
    String eventId,
    String tenantId,
    String orderId
) {}
~~~

`OrderApproved` là **sự kiện nghiệp vụ trong process**. Nó chưa tự được lưu vào MongoDB, không mặc nhiên là Kafka message và không mang bảo đảm giao tận nơi. Tên `eventId` được tạo từ business identity để hỗ trợ đối soát/idempotency.

### 4.4. `OutboxEvent`

~~~java
// OutboxEvent.java
package com.example.mongoevents;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "outbox_events_011")
public class OutboxEvent {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("aggregate_id")
    private String aggregateId;

    private String kind;
    private String status;
    private int attempts;

    @Field("created_at")
    private Instant createdAt;

    @Field("next_attempt_at")
    private Instant nextAttemptAt;

    @Field("lease_until")
    private Instant leaseUntil;

    @Field("lease_token")
    private String leaseToken;

    protected OutboxEvent() {}

    public OutboxEvent(
            String id, String tenantId,
            String aggregateId, String kind,
            Instant now) {
        this.id = id;
        this.tenantId = tenantId;
        this.aggregateId = aggregateId;
        this.kind = kind;
        this.status = "PENDING";
        this.attempts = 0;
        this.createdAt = now;
        this.nextAttemptAt = now;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getAggregateId() { return aggregateId; }
    public String getKind() { return kind; }
    public String getStatus() { return status; }
    public int getAttempts() { return attempts; }
    public Instant getLeaseUntil() { return leaseUntil; }
    public String getLeaseToken() { return leaseToken; }
}
~~~

Đây là model ví dụ có trạng thái `PENDING`/`SENDING`/`DELIVERED`. Production thường cần thêm `leaseOwner`, `leaseToken`, `lastErrorCode`, `schemaVersion`, `traceId`, `deliveredAt` và deadline/idempotency policy; đừng lưu token, payload nhạy cảm hoặc thông tin cá nhân vào log tùy tiện.

## 5. Event chỉ nên phát sau khi business write đã hợp lệ

Khi chuyển trạng thái order, cần biết **thật sự có một transition**. Không phát `OrderApproved` nếu query không khớp, sai tenant hoặc order đã duyệt từ trước.

~~~java
Query pending = Query.query(
    Criteria.where("id").is(orderId)
        .and("tenantId").is(authorizedTenantId)
        .and("state").is("PENDING")
);

Update approve = new Update().set("state", "APPROVED");

UpdateResult result = mongo.updateFirst(
    pending, approve, OrderDocument.class
);

if (result.getMatchedCount() != 1) {
    throw new OrderStateConflictException(
        "Order not found or not PENDING"
    );
}
~~~

`UpdateResult` ở đây là `com.mongodb.client.result.UpdateResult`, `Query`/`Criteria`/`Update` thuộc `org.springframework.data.mongodb.core.query`. Class `OrderStateConflictException` được khai báo tiếp dưới đây.

### 5.1. Exception miền

~~~java
// OrderStateConflictException.java
package com.example.mongoevents;

public class OrderStateConflictException
        extends RuntimeException {
    public OrderStateConflictException(String message) {
        super(message);
    }
}
~~~

Mặc định Spring rollback với `RuntimeException`/`Error` khi exception thoát khỏi transactional proxy. Checked exception có quy tắc khác nếu không đặt `rollbackFor`.

### 5.2. Một event có ID ổn định

~~~java
String eventId = "order-approved:" + orderId;
OrderApproved event = new OrderApproved(
    eventId, authorizedTenantId, orderId
);
~~~

Chọn `eventId` dựa trên **định danh nghiệp vụ** và semantics. Nếu một order có thể approve nhiều lần sau reopen, chỉ `orderId` có thể không đủ; lúc đó cần `orderId + transitionVersion` hoặc ID lệnh nghiệp vụ riêng. Không tạo UUID mới cho cùng một event mỗi lần retry nếu downstream cần deduplication.

## 6. Phương án A: `@TransactionalEventListener(AFTER_COMMIT)` cho thông báo best effort

Nếu thông báo là một tính năng phụ có thể mất khi process crash và có cơ chế xử lý thủ công, có thể dùng Spring application event kết hợp transaction phase.

### 6.1. Service phát event **bên trong** transaction

~~~java
// BestEffortOrderService.java
package com.example.mongoevents;

import com.mongodb.client.result.UpdateResult;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BestEffortOrderService {
    private final MongoTemplate mongo;
    private final ApplicationEventPublisher events;

    public BestEffortOrderService(
            MongoTemplate mongo,
            ApplicationEventPublisher events) {
        this.mongo = mongo;
        this.events = events;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void approve(String tenantId, String orderId) {
        Query eligible = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );

        UpdateResult result = mongo.updateFirst(
            eligible,
            new Update().set("state", "APPROVED"),
            OrderDocument.class
        );

        if (result.getMatchedCount() != 1) {
            throw new OrderStateConflictException(
                "Order not PENDING or wrong tenant"
            );
        }

        events.publishEvent(new OrderApproved(
            "order-approved:" + orderId,
            tenantId,
            orderId
        ));
        // Event được PUBLISH tại đây, nhưng listener AFTER_COMMIT
        // chưa chạy vì transaction chưa commit.
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void approveThenFail(
            String tenantId, String orderId) {
        approveInternalAndPublish(tenantId, orderId);
        throw new IllegalStateException(
            "Simulated failure before commit");
    }

    private void approveInternalAndPublish(
            String tenantId, String orderId) {
        Query eligible = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );
        UpdateResult result = mongo.updateFirst(
            eligible, new Update().set("state", "APPROVED"),
            OrderDocument.class
        );
        if (result.getMatchedCount() != 1) {
            throw new OrderStateConflictException(
                "Order not PENDING");
        }
        events.publishEvent(new OrderApproved(
            "order-approved:" + orderId,
            tenantId, orderId
        ));
    }
}
~~~

Trong ví dụ, `approveThenFail` gọi private helper thay vì gọi `this.approve(...)` nhằm không ngộ nhận rằng lời gọi nội bộ tạo transaction thứ hai. Hai entry points có `@Transactional` **phải được gọi từ bean khác qua Spring proxy** để transaction thực sự tồn tại.

Ở production nên tách logic `update + publish` thành helper chung để tránh trùng code; ví dụ giữ hai đường riêng giúp dễ theo dõi kịch bản thành công và rollback.

### 6.2. Listener chạy khi commit thành công

~~~java
// NotificationGateway.java
package com.example.mongoevents;

public interface NotificationGateway {
    void notifyOrderApproved(OrderApproved event);
}
~~~

~~~java
// OrderNotificationListener.java
package com.example.mongoevents;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {
    private final NotificationGateway notifications;

    public OrderNotificationListener(
            NotificationGateway notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterCommit(OrderApproved event) {
        notifications.notifyOrderApproved(event);
    }
}
~~~

`NotificationGateway` phải có implementation ở môi trường chạy (email/HTTP adapter, mock/recording port trong test). Listener chỉ **thử gọi external adapter sau commit**; adapter thất bại không biến order đã commit trở lại PENDING.

**Lưu ý:** phase mặc định của `@TransactionalEventListener` vốn là `AFTER_COMMIT`, nhưng khai báo tường minh giúp người đọc không nhầm với `@EventListener` thông thường.

### 6.3. Dòng thời gian thành công

~~~text
Caller --> Spring proxy
  -> mở MongoDB transaction T1
  -> update orders (T1)
  -> events.publishEvent(OrderApproved)
       -> listener được REGISTER cho AFTER_COMMIT
  -> method body return
  -> Spring commitTransaction(T1)
  -> T1 commit ACK thành công
  -> listener AFTER_COMMIT được thực thi
       -> NotificationGateway gửi thông báo
~~~

Đừng đọc dòng `events.publishEvent(...)` như “email đã được gửi”. Spring application event được công bố ở đó, nhưng listener có transaction phase sẽ đợi transaction completion.

### 6.4. Dòng thời gian rollback

~~~text
Caller --> Spring proxy
  -> transaction T2
  -> update orders (T2)
  -> events.publishEvent(OrderApproved)
       -> listener AFTER_COMMIT chờ
  -> throw IllegalStateException
  -> Spring abortTransaction(T2)
  -> listener AFTER_COMMIT KHÔNG chạy
  -> order không commit
~~~

Nếu service ném checked exception nhưng **không** có `rollbackFor`, Spring có thể vẫn commit theo default rollback rules. Khi đó listener AFTER_COMMIT **vẫn có thể chạy** dù caller nhận checked exception. Phase phụ thuộc **kết quả transaction**, không phụ thuộc trực tiếp việc controller có nhận exception hay không.

## 7. Khi không có transaction, listener làm gì?

Đây là lỗi cấu hình phổ biến:

~~~java
events.publishEvent(
    new OrderApproved("evt-011", "t01", "order-011-01")
);
~~~

Nếu code trên chạy **ngoài transaction** và `@TransactionalEventListener` không có `fallbackExecution`:

> Spring mặc định **không gọi listener** vì không có transaction synchronization để gắn phase.

### 7.1. `fallbackExecution = true`

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void onEvent(OrderApproved event) {
    notificationGateway.notifyOrderApproved(event);
}
~~~

Khi có transaction hợp lệ, listener chờ phase. Khi **không có transaction**, Spring có thể xử lý ngay theo fallback, tức **không có commit nào để đợi**.

**Không bật fallback một cách vô điều kiện** chỉ để “sửa lỗi listener không chạy”. Nếu yêu cầu là **chỉ thông báo sau commit**, fallback true có thể phá hợp đồng đó.

### 7.2. Vì sao mất transaction mà không biết?

Các nguyên nhân thường gặp:

- Chưa khai báo `MongoTransactionManager`.
- `@Transactional` nằm trên method được gọi nội bộ `this.method()`, bỏ qua proxy.
- Tạo service bằng `new` thay vì lấy Spring bean từ container.
- Chạy task trong thread khác bằng `CompletableFuture`/`@Async` mà không có transaction scope phù hợp.
- Sử dụng sai transaction manager (JPA/JDBC thay vì MongoDB) hoặc template khác `MongoDatabaseFactory`.
- Publish event sau khi transactional service đã trả về và transaction kết thúc.
- Trong reactive code, đánh mất `Reactor Context` hoặc dùng publisher không tham gia transaction.

### 7.3. Kiểm transaction ở chế độ imperative

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
boolean synchronizationActive =
    TransactionSynchronizationManager.isSynchronizationActive();
~~~

Hai flag có ý nghĩa khác nhau: transaction đang active và transaction synchronization được bật **không phải khái niệm giống nhau trong mọi cấu hình**. Dùng để chẩn đoán, không làm một transaction manager sai trở nên đúng.

**Không dùng** hai API thread-local này như cách chứng minh reactive transaction đang hoạt động. Reactive transaction dựa trên `Reactor Context`/reactive manager.

## 8. Bốn phase của `@TransactionalEventListener`

`TransactionPhase` có bốn lựa chọn phổ biến:

| Phase | Khi chạy | Use case phù hợp | Cảnh báo |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit transaction | Kiểm tra cuối, chuẩn bị dữ liệu | Exception có thể làm commit thất bại/rollback |
| `AFTER_COMMIT` | Sau commit thành công | Best-effort notification, invalidation | Crash window; lỗi listener **không undo commit** |
| `AFTER_ROLLBACK` | Sau khi rollback | Telemetry, cleanup ngoài DB cẩn trọng | Không dùng để “xóa lại” document đã abort |
| `AFTER_COMPLETION` | Sau commit **hoặc** rollback | Dọn tài nguyên/metric chung | Không suy đó là success |

### 8.1. `BEFORE_COMMIT` không thích hợp cho email

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.BEFORE_COMMIT
)
public void beforeCommit(OrderApproved event) {
    // Phù hợp kiểm tra bất biến, KHÔNG gửi email ở đây.
}
~~~

Nếu callback gửi email trước khi transaction commit rồi commit thất bại, external recipient đã nhận thông báo sai.

`BEFORE_COMMIT` cũng không có nghĩa commit chắc sẽ thành công; có thể còn write conflict, lỗi network, majority write concern hoặc failure lúc commit.

### 8.2. `AFTER_ROLLBACK` không có nghĩa “có thể bù mọi thứ”

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_ROLLBACK
)
public void afterRollback(OrderApproved event) {
    // Ví dụ: ghi metrics từ chối một workflow hoặc dọn tài nguyên
    // không nằm trong database transaction.
}
~~~

Đây chỉ được kích hoạt nếu event đã được publish trong transaction và transaction sau đó rollback. Nếu exception xảy ra **trước câu publishEvent**, listener này không biết gì để xử lý. Nếu cần audit **mọi failed attempt** phải có đường ghi/audit riêng, không chỉ trông chờ event từ một câu lệnh chưa chạy.

### 8.3. `AFTER_COMPLETION` có thể chạy cả hai outcome

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMPLETION
)
public void afterCompletion(OrderApproved event) {
    // Đây không phải nơi mặc định gửi "Approved" notification.
}
~~~

Nếu muốn biết cụ thể commit hay rollback, dùng hai listeners riêng hoặc transaction synchronization có status phù hợp; đừng suy từ tên event `OrderApproved` rằng phase này chỉ chạy sau success.

### 8.4. Event nhiều lần trong cùng transaction

~~~java
events.publishEvent(new OrderApproved("e1", tenantId, id1));
events.publishEvent(new OrderApproved("e2", tenantId, id2));
~~~

Mỗi lần phát có thể đăng ký một lần callback với transaction synchronization. Spring không tự gom nhiều event business giống nhau thành một event, không tự deduplicate và không chuyển chúng thành persistent queue.

Nếu muốn “chỉ một event cho mỗi transition”, cần thiết kế event ID, điều kiện update, transaction/outbox uniqueness.

## 9. Sau commit, tài nguyên transaction có thể vẫn đang bound

Spring Framework lưu ý: tại những callback `AFTER_COMMIT`/`AFTER_COMPLETION`, tài nguyên transaction đôi khi vẫn còn **gắn vào ngữ cảnh hiện tại** trong khi quá trình cleanup chưa hoàn tất.

### 9.1. Bẫy ghi DB trong listener sau commit

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void afterCommit(OrderApproved event) {
    // Không nên giả định thao tác sau sẽ chắc chắn được commit
    // dưới một transaction mới:
    mongoTemplate.save(new DeliveryAudit(...));
}
~~~

`DeliveryAudit` trong snippet là class minh họa, không phải Spring Data type. Với synchronization/transaction resource còn bound, thao tác DB có thể **tham gia tài nguyên cũ** dù phần commit đã kết thúc, nhưng không còn commit tiếp theo dành cho những thay đổi mới. **Không xem `afterCommit` là nơi tự động mở transaction mới.**

### 9.2. Nếu bắt buộc ghi DB mới: dùng service riêng `REQUIRES_NEW`

~~~java
// DeliveryAuditWriter.java
package com.example.mongoevents;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.mongodb.core.MongoTemplate;

@Service
public class DeliveryAuditWriter {
    private final MongoTemplate mongo;

    public DeliveryAuditWriter(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager",
        propagation = Propagation.REQUIRES_NEW
    )
    public void writeAudit(DeliveryAudit audit) {
        mongo.insert(audit);
    }
}
~~~

`DeliveryAudit` là entity dự án cần định nghĩa đầy đủ; code minh họa yêu cầu một **transaction mới** ở một **bean khác**, được gọi qua proxy. Nếu gọi `this.writeAudit(...)` từ cùng class, `REQUIRES_NEW` có thể không được intercept.

**Cân nhắc thiết kế:** Nếu audit/event này cực kỳ quan trọng, ghi **outbox/audit trong transaction gốc** an toàn hơn là chờ commit xong rồi mở transaction thứ hai. `REQUIRES_NEW` sau commit vẫn có crash window giữa hai transactions.

### 9.3. Phân biệt exception của listener và kết quả DB

Một listener `AFTER_COMMIT` có thể ném exception:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void send(OrderApproved event) {
    throw new IllegalStateException("Notification service unavailable");
}
~~~

**Order đã commit không tự rollback.** Việc exception được log, truyền tới caller hay xử lý bởi error handler phụ thuộc cơ chế listener/transaction synchronization, multicaster, async configuration và Spring version. Đừng mặc định “caller nhận lỗi ⇒ database chưa commit” hoặc “exception listener luôn được swallow”.

Hệ thống cần tách rõ trạng thái **database committed** và **notification delivered**, đo chúng qua metrics/event IDs riêng.

## 10. Đồng bộ, bất đồng bộ và độ bền của listener

### 10.1. “Sau commit” không đồng nghĩa “được chạy trong background”

`@TransactionalEventListener(AFTER_COMMIT)` mặc định tham gia cơ chế transaction synchronization. Trong cấu hình thông thường, callback có thể chạy trên luồng xử lý transaction completion. Nó **không tự tạo durable queue** hoặc retry job.

Nếu side effect như gửi HTTP mất 10 giây, request vẫn có thể chịu tác động latency tùy execution model. Phải cân nhắc deadline và isolation của external dependency.

### 10.2. `@Async` thay đổi nơi thực thi nhưng không thêm durability

Việc dùng async executor hoặc event multicaster bất đồng bộ có các lưu ý:

- Transaction context từ thread ban đầu **không tự đi theo** thread mới.
- Không để việc đăng ký listener transaction xảy ra ở một executor không có transaction context.
- Exception trong background thường cần error handler/metrics riêng.
- Nếu process crash sau commit nhưng trước/sau khi enqueue task vào executor, task trong memory có thể mất.
- Security context, tenant context, tracing context phải truyền đúng cách và không ghi lộ dữ liệu nhạy cảm.

Không xem một annotation `@Async` là giải pháp delivery tin cậy. Khi cần bền vững, dùng outbox/queue có persist và hợp đồng retry.

### 10.3. Ba crash window quan trọng

~~~text
W1. Before MongoDB commit
    -> transaction abort được; listener AFTER_COMMIT chưa được gọi.

W2. MongoDB commit thành công, process crash
    -> có thể MẤT event chỉ tồn tại trong memory.

W3. External API đã xử lý, process crash trước khi ghi nhận kết quả
    -> retry có thể GỬI TRÙNG.
~~~

`AFTER_COMMIT` xử lý đúng tình huống W1, **không tự giải quyết W2/W3**. Transactional outbox giải quyết đáng kể W2 bằng cách lưu việc cần gửi trong cùng commit, còn W3 vẫn cần idempotent consumer/đối soát.

## 11. Sự kiện nghiệp vụ không phải đồng nghĩa với Spring Data entity events

### 11.1. Sự kiện nên mô tả điều nghiệp vụ *đã xảy ra*

Nên đặt tên:

~~~text
OrderApproved
PaymentConfirmed
StockReservationCreated
CustomerEmailVerified
~~~

Thay vì chỉ:

~~~text
OrderSaved
DocumentUpdated
MongoEntityChanged
~~~

`OrderApproved` chứa ý nghĩa và invariant: tenant, order, transition ID, trạng thái mới. `AfterSaveEvent<OrderDocument>` chỉ nói một API mapping save chạy; nó có thể phát khi cập nhật field không liên quan approval.

### 11.2. Domain event cần xuất hiện từ tầng service

~~~java
UpdateResult result = mongo.updateFirst(
    pendingQuery, approveUpdate, OrderDocument.class
);

if (result.getMatchedCount() == 1) {
    events.publishEvent(
        new OrderApproved(eventId, tenantId, orderId)
    );
}
~~~

Nguồn phát event nằm ở **transition command được xác thực**. Nếu update không match, không phát success event. Điều kiện `tenantId`/trạng thái vẫn phải được enforced trên database; thông báo từ listener không thể sửa một write unauthorized.

### 11.3. Domain events của Spring Data repositories

Spring Data Commons cung cấp các khái niệm như `@DomainEvents`/`@AfterDomainEventPublication` trên aggregate root, hỗ trợ công bố sự kiện trong một số repository method. Đây là một **cơ chế publication ở tầng repository**, không thay thế transaction synchronization hoặc durable outbox.

Các lưu ý:

- Publication có thể xảy ra trước khi transaction commit.
- Một số đường ghi như `MongoTemplate.updateMulti` hoặc raw driver không đi qua cơ chế aggregate domain events.
- Việc delete theo ID/mass delete có thể không instantiate aggregate để thu thập events.
- Sự kiện in-memory có thể mất khi process crash.

Nếu muốn phản ứng **sau commit**, phải kết nối publication với transaction phase. Nếu yêu cầu không được mất event sau commit, phải **persist** event/outbox cùng transaction.

## 12. Phương án B: transactional outbox cho side effect phải được giao tin cậy

Một **transactional outbox** là collection chứa các event/message dự định gửi sau commit. Với MongoDB:

~~~text
Trong transaction T1:
   update orders_events_011
   insert outbox_events_011
   commit T1

Ngoài transaction T1:
   OutboxDispatcher đọc PENDING
   claim event và gửi external system
   đánh dấu DELIVERED hoặc lịch retry
~~~

Nếu transaction T1 abort, **không có** order approval và **không có** outbox event tương ứng. Nếu T1 commit thành công, outbox record vẫn còn sau process crash, để worker tìm lại.

### 12.1. Service ghi order và outbox atomically

~~~java
// ReliableOrderService.java
package com.example.mongoevents;

import com.mongodb.client.result.UpdateResult;
import java.time.Clock;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReliableOrderService {
    private final MongoTemplate mongo;
    private final Clock clock;

    public ReliableOrderService(
            MongoTemplate mongo, Clock clock) {
        this.mongo = mongo;
        this.clock = clock;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void approve(String tenantId, String orderId) {
        Query eligible = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );

        UpdateResult updated = mongo.updateFirst(
            eligible,
            new Update().set("state", "APPROVED"),
            OrderDocument.class
        );

        if (updated.getMatchedCount() != 1) {
            throw new OrderStateConflictException(
                "No eligible order");
        }

        String eventId = "order-approved:" + orderId;

        mongo.insert(new OutboxEvent(
            eventId,
            tenantId,
            orderId,
            "OrderApproved",
            clock.instant()
        ));
        // Commit của CẢ HAI write xảy ra sau khi method return,
        // tại transactional proxy.
    }
}
~~~

`Clock` là dependency để test thời gian ổn định; cần cung cấp bean:

~~~java
@Bean
java.time.Clock clock() {
    return java.time.Clock.systemUTC();
}
~~~

Đây là một đoạn bean method đặt trong class `@Configuration`; phần config có thể đặt cạnh `MongoTransactionConfig`. Không tạo bean mới trong mỗi request.

### 12.2. Một tình huống lỗi trước commit

Giả sử thao tác update thành công trong transaction nhưng `mongo.insert(outbox)` bị `DuplicateKeyException` vì trùng `_id`. Với transaction được cấu hình đúng:

~~~text
update order -> thành công trong transaction
insert outbox -> E11000
Spring rollback/abort transaction
order APPROVED chưa commit -> không có
outbox mới -> không có
~~~

Outbox record **đã tồn tại trước đó** không bị xóa bởi abort của transaction mới. Đây là lý do không viết compensation `deleteById(outboxId)` bừa bãi khi transaction rollback.

### 12.3. Idempotency key ở outbox

`_id = "order-approved:" + orderId` bảo đảm không tạo hai outbox record cùng key. Nếu nghiệp vụ cho phép reapprove cùng order sau reopen, cần thay `eventId` bằng khóa gồm **orderId + transitionVersion** hoặc **business command ID**.

Mục tiêu là xác định **một sự kiện logic** chứ không phải “một HTTP request”. Nếu retry sau timeout với một eventId khác, bạn có thể ghi hai event logic giống nhau.

### 12.4. Cần bao nhiêu index?

Ngoài unique `_id` tự có, worker có thể dùng index kiểu:

~~~javascript
db.outbox_events_011.createIndex(
  { status: 1, next_attempt_at: 1, _id: 1 },
  { name: "ix_outbox_due" }
);

db.outbox_events_011.createIndex(
  { status: 1, lease_until: 1 },
  { name: "ix_outbox_expired_lease" }
);
~~~

Index trên giúp query event **PENDING tới hạn** và **SENDING có lease quá hạn**. Tối ưu thực tế phụ thuộc số event, selectivity, sort, shard key, write amplification và `explain("executionStats")`. Không tạo quá nhiều index mà không đo chi phí.

## 13. Worker outbox: claim atomically, gửi, rồi ghi nhận

Để nhiều instances cùng xử lý outbox, mỗi event cần được **claim** trước khi gửi. Không viết:

~~~java
// SAI khi nhiều worker chạy:
OutboxEvent event = mongo.findOne(pendingQuery, OutboxEvent.class);
gateway.send(event);
mongo.updateFirst(markDelivered, ...);
~~~

Hai worker có thể đọc cùng một event PENDING và cùng gửi. Trạng thái “đã đọc” không phải lock.

### 13.1. State machine đề xuất

~~~mermaid
flowchart LR
    P["PENDING"] -->|"claim"| S["SENDING"]
    S -->|"external ACK + mark"| D["DELIVERED"]
    S -->|"transient failure"| R["PENDING / retry later"]
    S -->|"lease hết hạn"| S2["SENDING / worker khác claim"]
    S -->|"permanent failure hoặc quá retries"| X["DEAD_LETTER"]
    R -->|"claim lại"| S
    S2 -->|"retry claim"| S
~~~

State `DEAD_LETTER` là lựa chọn nghiệp vụ, không phải MongoDB built-in. Một deployment thực tế còn có worker owner/token, retry count, next attempt, exponential backoff và cảnh báo vận hành.

### 13.2. Claim bằng `findAndModify`

~~~java
// OutboxClaimService.java
package com.example.mongoevents;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OutboxClaimService {
    private final MongoTemplate mongo;
    private final Clock clock;

    public OutboxClaimService(MongoTemplate mongo, Clock clock) {
        this.mongo = mongo;
        this.clock = clock;
    }

    public OutboxEvent claimNext() {
        Instant now = clock.instant();
        String claimToken = UUID.randomUUID().toString();

        Criteria duePending = Criteria.where("status").is("PENDING")
            .and("nextAttemptAt").lte(now);

        Criteria expiredLease = Criteria.where("status").is("SENDING")
            .and("leaseUntil").lt(now);

        Query eligible = Query.query(
            new Criteria().orOperator(duePending, expiredLease)
        ).with(Sort.by(
            Sort.Order.asc("nextAttemptAt"),
            Sort.Order.asc("id")
        ));

        Update claim = new Update()
            .set("status", "SENDING")
            .set("leaseUntil", now.plus(Duration.ofSeconds(30)))
            .set("leaseToken", claimToken)
            .inc("attempts", 1);

        return mongo.findAndModify(
            eligible,
            claim,
            FindAndModifyOptions.options().returnNew(true),
            OutboxEvent.class
        );
    }
}
~~~

`findAndModify` là một **atomic single-document operation**: mỗi call chỉ claim một document đang thỏa filter tại thời điểm áp write. Hai worker đồng thời không cùng claim một record ở trạng thái PENDING, vì một worker chuyển nó sang SENDING.

**Giới hạn quan trọng:** Sau 30 giây, lease của worker A có thể hết hạn **dù A đang gửi chậm**. Worker B có thể claim lại event. Vì thế hệ thống vẫn phải chấp nhận khả năng **gửi trùng** và dùng eventId/idempotency phía receiver; lease không biến outbox thành exactly-once delivery.

### 13.3. Fencing token giúp worker cũ không ghi đè trạng thái

Giả sử A claim event token `A1`, lease hết hạn, B claim lại với token `B2`. A không được phép “đánh dấu DELIVERED” dựa trên token đã hết hiệu lực.

~~~java
public boolean markDelivered(
        String eventId, String claimToken) {

    Query mine = Query.query(
        Criteria.where("id").is(eventId)
            .and("status").is("SENDING")
            .and("leaseToken").is(claimToken)
    );

    Update done = new Update()
        .set("status", "DELIVERED")
        .unset("leaseUntil")
        .unset("leaseToken");

    var result = mongo.updateFirst(
        mine, done, OutboxEvent.class
    );
    return result.getMatchedCount() == 1;
}
~~~

Đây là method có thể đặt trong `OutboxClaimService` (đã có `mongo`) hoặc một state writer riêng. Nó bảo vệ **cập nhật state trong MongoDB**, nhưng không thể ngăn external API bị gọi hai lần nếu worker A/B cùng gửi.

### 13.4. Retry có kiểm soát

Với lỗi có thể retry, chỉ writer đang giữ token mới được chuyển lại trạng thái PENDING và hẹn `nextAttemptAt`:

~~~java
public boolean scheduleRetry(
        String eventId,
        String claimToken,
        Instant nextAttemptAt) {

    Query mine = Query.query(
        Criteria.where("id").is(eventId)
            .and("status").is("SENDING")
            .and("leaseToken").is(claimToken)
    );

    Update retry = new Update()
        .set("status", "PENDING")
        .set("nextAttemptAt", nextAttemptAt)
        .unset("leaseUntil")
        .unset("leaseToken");

    return mongo.updateFirst(
        mine, retry, OutboxEvent.class
    ).getMatchedCount() == 1;
}
~~~

Không retry tất cả lỗi như nhau. Ví dụ external API trả validation error vì payload không hợp lệ thì việc chờ rồi gửi lại vô hạn không có lợi; có thể chuyển `DEAD_LETTER` và báo vận hành. Với HTTP 429/503, cân nhắc `Retry-After`, exponential backoff, jitter và giới hạn attempt.

### 13.5. Không giữ MongoDB transaction mở khi gọi external API

**Không làm:**

~~~java
@Transactional
public void claimSendAndMark(...) {
    claimEventInMongo();
    emailClient.send(...); // mạng ngoài, có thể 30 giây
    markDeliveredInMongo();
}
~~~

Không thể rollback email trong transaction MongoDB; giữ transaction mở qua HTTP làm tăng contention, chi phí snapshot và timeout. Tách thành:

~~~text
DB atomic claim (transaction đơn document ngắn)
    -> external send ngoài MongoDB transaction
    -> DB atomic mark/lease-token guard
~~~

### 13.6. Dispatcher một lần xử lý

~~~java
public void dispatchOne() {
    OutboxEvent event = claims.claimNext();
    if (event == null) {
        return;
    }

    try {
        gateway.send(
            event.getId(),          // Idempotency-Key bên ngoài
            event.getKind(),
            event.getAggregateId()
        );

        boolean committed = claims.markDelivered(
            event.getId(), event.getLeaseToken()
        );
        if (!committed) {
            metrics.recordLostLease(event.getId());
        }
    } catch (RetryableDeliveryException ex) {
        claims.scheduleRetry(
            event.getId(),
            event.getLeaseToken(),
            nextRetryTime(event.getAttempts())
        );
    }
}
~~~

Ở đây `gateway`/`claims` là dependency của worker service, `metrics` là telemetry adapter, `RetryableDeliveryException` là custom exception, `nextRetryTime(...)` là hàm exponential backoff có giới hạn. Đây là **pseudocode Java cho orchestration**, chưa định nghĩa các adapter; không copy vào production thiếu xử lý permanent failure và monitoring.

Dispatcher phải kiểm:

- Phân loại exception có thể retry vs permanent.
- Nếu worker crash sau external ACK nhưng trước `markDelivered`, retry có thể gửi lại.
- Nếu hết lease, worker cũ có thể đã gửi xong nhưng không mark được; metric và idempotency là cần thiết.
- Tránh hàng nghìn workers `claimNext()` spin liên tục khi queue rỗng; dùng scheduling/backoff hoặc consumer event.
- Bảo vệ tenant, credentials và thông tin nhạy cảm của event.

## 14. Vì sao outbox thường mang ngữ nghĩa at-least-once?

Xét dòng thời gian:

~~~text
t0  T1 commit order + outbox.
t1  Worker A claim event e1.
t2  Worker A gọi external API; remote nhận và xử lý e1.
t3  Worker A crash TRƯỚC khi mark DELIVERED.
t4  Lease e1 hết hạn.
t5  Worker B claim lại e1 và gửi cùng eventId.
~~~

Receiver có thể nhận **hai lần**, mặc dù MongoDB có đúng một outbox record. Đây là **at-least-once attempt**, không phải exactly-once external effect.

### 14.1. Hợp đồng idempotency phía receiver

Receiver có thể lưu một bảng/collection:

~~~text
processed_events
  _id = eventId
  processed_at = ...
~~~

Khi nhận event:

1. Kiểm eventId/fingerprint hợp lệ và tenant có quyền.
2. Đảm bảo **chỉ một lần áp business effect** cho eventId bằng unique key và thao tác nguyên tử/transaction phù hợp.
3. Nếu nhận lại cùng eventId với cùng payload, trả kết quả đã xử lý.
4. Nếu cùng eventId nhưng payload khác, coi là **conflict/security anomaly**, không im lặng bỏ qua.

Nếu receiver dùng MongoDB, có thể tạo `_id` unique trong collection `processed_events` và thực hiện insert marker **cùng transaction** với business update của receiver. Chỉ ghi marker trước rồi thực hiện side effect ngoài transaction có thể khiến marker ghi thành công nhưng business effect chưa xảy ra.

### 14.2. Email provider không hỗ trợ idempotency?

Nếu email provider không có idempotency key API, application có thể kiểm marker gửi, nhưng không thể loại bỏ hoàn toàn crash window:

~~~text
Send email thành công -> crash trước marker
Retry -> email có thể gửi thêm lần nữa
~~~

Để có bảo đảm gần “một lần”, cần hỗ trợ idempotency từ **điểm thực hiện effect cuối cùng**, hoặc chấp nhận khả năng duplicate và thiết kế UX phù hợp. Không tuyên bố “outbox bảo đảm gửi email exactly once” chỉ vì outbox `_id` unique.

### 14.3. Thứ tự sự kiện

Nếu một aggregate có:

~~~text
OrderApproved(version=5)
OrderShipped(version=6)
~~~

Outbox worker chạy đồng thời có thể gửi version 6 trước version 5 nếu không có quy tắc. Nếu downstream cần ordering:

- Lưu `aggregateId` và `aggregateVersion` vào event.
- Phân vùng theo aggregate key.
- Consumer xử lý version có điều kiện hoặc đợi gap.
- Đặt idempotency/version guard khi cập nhật trạng thái.

Sort bằng `createdAt` chỉ giúp **ưu tiên**, không tự bảo đảm thứ tự **ACK external** khi nhiều worker/concurrent network.

### 14.4. Delivery acknowledgement khác commit của business

Có ba mốc:

~~~text
Business MongoDB transaction committed
          ↓
Outbox event claimed and sent
          ↓
External consumer acknowledged / processed
~~~

API có thể trả `200/204` ở mốc đầu nếu contract chỉ yêu cầu order được duyệt và notification sẽ diễn ra sau. Nếu cần external confirmation đồng bộ, phải định nghĩa trạng thái riêng `PENDING_EXTERNAL_CONFIRMATION`; không kéo dài MongoDB transaction để chờ kết quả remote.

## 15. Polling, scheduling và change streams

### 15.1. Polling là baseline đơn giản

Một worker có thể gọi `claimNext` theo lịch (ví dụ mỗi vài trăm mili giây đến vài giây, tùy SLO). Với Spring:

~~~java
@Scheduled(fixedDelayString = "${app.outbox.poll-delay-ms:1000}")
public void poll() {
    dispatcher.dispatchOne();
}
~~~

Yêu cầu `@EnableScheduling` trong configuration. `fixedDelay` tính từ sau lần chạy kết thúc; mỗi lần poll xử lý một event trong ví dụ. Với số lượng lớn cần batch loops có giới hạn thời gian, concurrency và cơ chế tránh worker starvation.

**Lưu ý:** Cấu hình `app.outbox.poll-delay-ms` là property **tự định nghĩa**, không phải built-in Spring Data MongoDB.

### 15.2. MongoDB change streams để giảm độ trễ

Change stream có thể quan sát outbox inserts/updates khi MongoDB chạy replica set hoặc sharded cluster phù hợp. Khi có event mới, worker được đánh thức sớm hơn so với polling.

Nhưng change streams có:

- Resume token cần persist và quản lý sau reconnect.
- Oplog history hữu hạn; token có thể không còn khả dụng sau outage dài.
- Các event có thể bị xử lý lại khi reconnect/crash giữa delivery và checkpoint.
- Consumer lag, bộ lọc pipeline và quyền truy cập cần kiểm soát.

**Thiết kế robust:** coi collection outbox persist là **nguồn sự thật**; change stream chỉ giúp **đánh thức xử lý**, còn polling/reconciliation scan vẫn cần để phục hồi khi bỏ lỡ notification hoặc mất resume token.

### 15.3. Change stream của collection nghiệp vụ không mặc định là outbox

Nghe `orders` change stream rồi suy luận `OrderApproved` dựa trên update BSON có thể:

- Nhầm một update metadata với transition nghiệp vụ.
- Bỏ sót ngữ cảnh tenant/commandId/actor/event version.
- Khó xác định payload canonical cho consumer.
- Phụ thuộc change stream options (fullDocument/lookup/updateDescription).

Outbox record mô tả **ngữ nghĩa domain event** rõ hơn; có thể dùng change stream **trên outbox** để kích hoạt delivery.

## 16. Hạn chế của “eventual consistency”

Khi order đã commit nhưng email/cập nhật kho chưa xong, hệ thống có hai trạng thái đúng thời điểm:

~~~text
Order service: APPROVED
Inventory service: chưa áp reservation
~~~

Đó là **eventual consistency**, không phải lỗi tự động nếu contract cho phép. API/UX nên phản ánh:

- `APPROVED_PENDING_FULFILLMENT` nếu còn bước external quan trọng.
- Retry/timeout cho từng bước, không retry mù toàn approve command.
- Khả năng đối soát dựa trên `eventId` và `orderId`.
- Alert khi outbox pending quá SLA.
- Compensation/saga nếu external effect cuối cùng không thể hoàn tất.

Nếu một nghiệp vụ **không thể chấp nhận** window tạm bất nhất giữa các hệ thống, phải xem lại ranh giới aggregate/architecture và yêu cầu consistency; MongoDB transaction chỉ bao trùm tài nguyên MongoDB tham gia cùng transaction, không mở rộng sang SMTP/Kafka/HTTP service bằng một annotation.

## 17. Reactive application: transaction context khác imperative

Trong Spring Data MongoDB reactive, transaction manager là `ReactiveMongoTransactionManager` và transaction context được truyền qua **Reactor Context**, không chỉ thread-local.

### 17.1. Bean reactive transaction manager

~~~java
// ReactiveMongoTransactionConfig.java
package com.example.mongoevents;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class ReactiveMongoTransactionConfig {

    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveMongoTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
~~~

Đây là config cho application reactive; không dùng `MongoTransactionManager` imperative để mong nó quản lý một chuỗi `ReactiveMongoTemplate`.

### 17.2. Ghi order và outbox tuần tự trong reactive transaction

~~~java
// ReactiveReliableOrderService.java
package com.example.mongoevents;

import java.time.Clock;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReactiveReliableOrderService {
    private final ReactiveMongoTemplate mongo;
    private final TransactionalOperator operator;
    private final Clock clock;

    public ReactiveReliableOrderService(
            ReactiveMongoTemplate mongo,
            TransactionalOperator operator,
            Clock clock) {
        this.mongo = mongo;
        this.operator = operator;
        this.clock = clock;
    }

    public Mono<Void> approve(
            String tenantId, String orderId) {

        Query eligible = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );

        Mono<Void> work = mongo.updateFirst(
                eligible,
                new Update().set("state", "APPROVED"),
                OrderDocument.class
            )
            .flatMap(result -> {
                if (result.getMatchedCount() != 1) {
                    return Mono.error(
                        new OrderStateConflictException(
                            "No eligible order"));
                }

                OutboxEvent outbox = new OutboxEvent(
                    "order-approved:" + orderId,
                    tenantId, orderId,
                    "OrderApproved", clock.instant()
                );

                return mongo.insert(outbox).then();
            });

        return work.as(operator::transactional);
    }
}
~~~

`updateFirst` được subscribe trước `insert(outbox)` vì chúng được ghép bằng `flatMap`, và **cả hai ở cùng reactive transaction** do `TransactionalOperator` quản lý.

**Không viết**:

~~~java
// Sai: parallel operations trong cùng MongoDB transaction
// return Mono.when(
//     mongo.updateFirst(...),
//     mongo.insert(outbox)
// ).as(operator::transactional);
~~~

MongoDB Java Reactive Streams Driver không hỗ trợ các operation **song song trong cùng transaction**; hơn nữa outbox phụ thuộc vào việc update order thật sự match. Hãy ghép tuần tự như trên.

### 17.3. Reactive `@TransactionalEventListener` cần transaction context trong event

Từ Spring Framework **6.1**, transactional event listeners có hỗ trợ cả reactive transaction. Tuy nhiên reactive transaction state nằm trong **Reactor Context**, không phải thread-local.

Vì thế khi publish reactive transactional event:

- Phải bảo đảm event **mang transaction context trong source** theo hợp đồng Spring.
- `org.springframework.transaction.reactive.TransactionalEventPublisher` là utility được Spring cung cấp để publish event gắn đúng transaction context.
- Việc gọi một `ApplicationEventPublisher.publishEvent(...)` đơn thuần ngoài reactive context **không tự bảo đảm** listener AFTER_COMMIT được kích hoạt đúng.
- Publisher publish phải được **compose trong reactive chain**, không tự `subscribe()` tách rời.
- Nếu không có transaction, `fallbackExecution` vẫn có cùng bẫy: listener có thể chạy ngay, không hề có commit cần chờ.

Khi sự kiện **cực kỳ quan trọng**, ví dụ reactive `approve` như mục 17.2 ghi outbox **trong transaction** sẽ đơn giản hơn về độ bền và khả năng đối soát so với chỉ publish event trong Reactor Context.

### 17.4. Cancellation không chứng minh transaction đã rollback

Client WebFlux ngắt kết nối khi server đang commit:

~~~text
Publisher bị cancel / HTTP request timeout
              ≠
MongoDB chắc chắn đã abort
~~~

Commit có thể đã tới server và thành công trong khi client không nhận được acknowledgment. Dùng `eventId`/`orderId` ổn định và đọc đối soát theo read concern/consistency policy phù hợp.

Không retry một sự kiện nghiệp vụ bằng cách tạo ID mới chỉ vì client mất kết nối.

## 18. Kiểm thử tích hợp: after commit chạy, rollback không chạy

Mock trực tiếp `MongoTemplate` không chứng minh transaction synchronization hoạt động. Dùng MongoDB **replica set test** và Spring context thực.

### 18.1. Ma trận kiểm thử cần có

| Tình huống | DB sau khi service proxy kết thúc | Listener AFTER_COMMIT |
| --- | --- | --- |
| Transaction commit thành công | Order APPROVED | Gọi một lần cho event đã publish |
| RuntimeException trước commit | Order còn PENDING | **Không gọi** |
| Checked exception mặc định không rollback | Transaction có thể commit | Có thể gọi nếu commit thành công |
| Checked exception với `rollbackFor` | Order còn PENDING | Không gọi |
| Publish event ngoài transaction, fallback false | Không xét | Không gọi |
| Publish event ngoài transaction, fallback true | Không có transaction | Có thể gọi ngay |
| Transaction commit, process crash trước listener | DB đã commit | **Có thể mất notification** |
| Listener gửi external rồi lỗi | DB vẫn commit | Có thể gửi trùng nếu retry |
| Outbox transaction commit | Order APPROVED + outbox tồn tại | Không phụ thuộc listener |
| Outbox insert duplicate trong transaction | Order rollback | Outbox mới không được ghi |
| Worker crash sau external ACK trước `markDelivered` | Outbox vẫn chưa DELIVERED | Có thể retry và gửi trùng |

Hai dòng crash cần **fault-injection/chaos test** riêng; chúng không được chứng minh chỉ bằng một unit test bình thường.

### 18.2. Recording gateway trong test

~~~java
// RecordingNotifications.java (test source)
package com.example.mongoevents;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public final class RecordingNotifications
        implements NotificationGateway {

    private final CopyOnWriteArrayList<OrderApproved> received =
        new CopyOnWriteArrayList<>();

    @Override
    public void notifyOrderApproved(OrderApproved event) {
        received.add(event);
    }

    public List<OrderApproved> snapshot() {
        return List.copyOf(received);
    }

    public void reset() {
        received.clear();
    }
}
~~~

Recording gateway không gửi email thật, chỉ quan sát listener invocation. Nó không mô phỏng network/remote response.

### 18.3. Bean test để inject gateway và clock

~~~java
// MongoEventsTestBeans.java (test source)
package com.example.mongoevents;

import java.time.Clock;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration
public class MongoEventsTestBeans {

    @Bean
    RecordingNotifications recordingNotifications() {
        return new RecordingNotifications();
    }

    @Bean
    NotificationGateway notificationGateway(
            RecordingNotifications recording) {
        return recording;
    }

    @Bean
    Clock testClock() {
        return Clock.systemUTC();
    }
}
~~~

Trong application thật, thay recording adapter bằng gateway cung cấp external notification. Với test phải đảm bảo không có bean `NotificationGateway` khác xung đột hoặc cần `@Qualifier`.

### 18.4. Test commit/rollback và outbox cùng transaction

~~~java
// MongoBusinessEventsTest.java (test source)
package com.example.mongoevents;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import({
    MongoTransactionConfig.class,
    BestEffortOrderService.class,
    ReliableOrderService.class,
    OrderNotificationListener.class,
    MongoEventsTestBeans.class
})
class MongoBusinessEventsTest {

    private static final String TENANT = "it-mongo-evt-011";
    private static final String OK = "it-evt-011-ok";
    private static final String ABORT = "it-evt-011-abort";
    private static final String OUTBOX = "it-evt-011-outbox";
    private static final String CONFLICT = "it-evt-011-conflict";

    @Autowired MongoTemplate mongo;
    @Autowired BestEffortOrderService bestEffort;
    @Autowired ReliableOrderService reliable;
    @Autowired RecordingNotifications notifications;

    @BeforeEach
    void setUp() {
        // Tạo collection ngoài transaction trong test DB biệt lập.
        if (!mongo.collectionExists(OrderDocument.class)) {
            mongo.createCollection(OrderDocument.class);
        }
        if (!mongo.collectionExists(OutboxEvent.class)) {
            mongo.createCollection(OutboxEvent.class);
        }

        clearFixtures();
        notifications.reset();

        for (String id : new String[] {
                OK, ABORT, OUTBOX, CONFLICT }) {
            mongo.insert(new OrderDocument(
                id, TENANT, "PENDING", 250000L
            ));
        }
    }

    @AfterEach
    void tearDown() {
        clearFixtures();
        notifications.reset();
    }

    private void clearFixtures() {
        for (String id : new String[] {
                OK, ABORT, OUTBOX, CONFLICT }) {
            mongo.remove(
                Query.query(Criteria.where("id").is(id)),
                OrderDocument.class
            );
            mongo.remove(
                Query.query(Criteria.where("id").is(
                    "order-approved:" + id)),
                OutboxEvent.class
            );
        }
    }

    @Test
    void afterCommitNotifiesAfterDatabaseCommit() {
        bestEffort.approve(TENANT, OK);

        assertThat(mongo.findById(
            OK, OrderDocument.class
        ).getState()).isEqualTo("APPROVED");

        assertThat(notifications.snapshot())
            .extracting(OrderApproved::orderId)
            .containsExactly(OK);
    }

    @Test
    void afterCommitDoesNotRunAfterRollback() {
        assertThatThrownBy(() ->
            bestEffort.approveThenFail(TENANT, ABORT)
        ).isInstanceOf(IllegalStateException.class);

        assertThat(mongo.findById(
            ABORT, OrderDocument.class
        ).getState()).isEqualTo("PENDING");
        assertThat(notifications.snapshot()).isEmpty();
    }

    @Test
    void orderAndOutboxCommitTogether() {
        reliable.approve(TENANT, OUTBOX);

        assertThat(mongo.findById(
            OUTBOX, OrderDocument.class
        ).getState()).isEqualTo("APPROVED");
        assertThat(mongo.findById(
            "order-approved:" + OUTBOX,
            OutboxEvent.class
        )).isNotNull();
    }

    @Test
    void duplicateOutboxAbortsOrderUpdate() {
        String eventId = "order-approved:" + CONFLICT;

        mongo.insert(new OutboxEvent(
            eventId, TENANT, CONFLICT,
            "OrderApproved", java.time.Instant.now()
        ));

        assertThatThrownBy(() ->
            reliable.approve(TENANT, CONFLICT)
        ).isInstanceOf(DuplicateKeyException.class);

        assertThat(mongo.findById(
            CONFLICT, OrderDocument.class
        ).getState()).isEqualTo("PENDING");

        // Bản ghi outbox cũ không biến mất vì rollback
        // của transaction mới.
        assertThat(mongo.findById(
            eventId, OutboxEvent.class
        )).isNotNull();
    }
}
~~~

**Giới hạn test:** Dùng Spring Boot test slice tương ứng phiên bản (đoạn import minh họa Spring Boot 3.x), MongoDB replica set test đã chạy và application context có transaction manager. Test **không** được mang `@Transactional` ở method test hoặc class test vì sẽ thay đổi scope commit/rollback đang cần quan sát.

Spring Boot 4 có thay đổi một số package/test starter; khi đưa vào dự án cần chọn phiên bản đúng. Bài này không yêu cầu người học chạy ngay trên project bất kỳ mà không kiểm dependencies/config.

### 18.5. Kiểm thêm behavior ngoài transaction

Gọi:

~~~java
// Thực thi ở một method test KHÔNG @Transactional:
events.publishEvent(
    new OrderApproved("outside-evt", TENANT, "outside-order")
);
~~~

Với `@TransactionalEventListener(AFTER_COMMIT)` và `fallbackExecution=false`, recording gateway **không** nhận event này.

Nếu đổi annotation sang `fallbackExecution=true` thì gateway có thể nhận ngay dù không có transaction. Đây là điều phải kiểm bằng test riêng trước khi bật fallback.

### 18.6. Test khác: listener lỗi sau commit

Một `NotificationGateway` test có thể cố ý ném exception khi nhận event. Điều cần kiểm:

- Order đã commit vẫn ở APPROVED.
- Handler/metric ghi nhận notification failure.
- Exception propagation được kỳ vọng theo cơ chế Spring listener đang cấu hình.
- Có job/outbox để retry hay không.

Đừng viết test chỉ có `assertThrows(...)` rồi suy rằng DB đã rollback; phải truy vấn **database state sau lời gọi proxy**.

## 19. Reactive integration test cho outbox

Với reactive service ở mục 17, cần MongoDB **replica set**, `ReactiveMongoTransactionManager` và test publisher bằng `StepVerifier`.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import reactor.test.StepVerifier;

// Test setup đã tạo order "rx-evt-011" trạng thái PENDING
// và hai collection trước transaction.
StepVerifier.create(
    reactiveReliableOrderService.approve(
        "test-tenant-rx-011", "rx-evt-011"
    )
).verifyComplete();

StepVerifier.create(
    reactiveMongoTemplate.findById(
        "rx-evt-011", OrderDocument.class
    )
)
  .assertNext(order ->
      assertThat(order.getState()).isEqualTo("APPROVED")
  )
  .verifyComplete();

StepVerifier.create(
    reactiveMongoTemplate.findById(
        "order-approved:rx-evt-011", OutboxEvent.class
    )
)
  .expectNextCount(1)
  .verifyComplete();
~~~

Đây là đoạn trong method test đã inject `reactiveReliableOrderService` và `reactiveMongoTemplate`, không phải class test tự chứa hoàn toàn. Ngoài happy path, test thêm kịch bản trùng outbox `_id` trước approval: publisher phải phát error và order vẫn PENDING.

Không dùng `block()` trong WebFlux runtime; trong integration test có thể dùng StepVerifier để subscribe và kiểm terminal signal. Nếu chỉ tạo `Mono<Void>` mà không subscribe, transaction/reactive write thường **chưa chạy**.

## 20. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/sửa |
| --- | --- | --- |
| `AfterSaveCallback` gửi email cho order đã rollback | Callback lưu entity chạy trước transaction commit | Đưa side effect sang AFTER_COMMIT hoặc outbox |
| `@TransactionalEventListener` không nhận event | Publish ngoài transaction, fallback false | Kiểm proxy/manager/synchronization |
| Listener chạy dù không có transaction | Bật `fallbackExecution=true` | Tắt fallback nếu cần strict after-commit |
| `@EventListener` gửi email trước khi DB commit | `@EventListener` không gắn phase transaction | Dùng transactional listener hoặc outbox |
| Listener chạy sau checked exception | Spring mặc định có thể commit checked exception | Cấu hình `rollbackFor` theo contract |
| `@Transactional` có nhưng DB vẫn ghi từng lệnh | Self-invocation hoặc manager/template khác factory | Gọi qua proxy, dùng cùng MongoDatabaseFactory |
| Service trả về rồi listener vẫn chạy sai thời điểm | Hiểu nhầm body return với proxy commit | Quan sát lifecycle sau transaction completion |
| Listener AFTER_COMMIT lỗi, order vẫn APPROVED | Commit đã xảy ra | Tách trạng thái business và delivery; retry qua outbox |
| Ghi MongoDB trong AFTER_COMMIT không persisted | Tài nguyên transaction cũ còn bound, không có commit mới | Tách service REQUIRES_NEW hoặc ghi outbox trước commit |
| Dùng `REQUIRES_NEW` mà không thấy tác dụng | Gọi `this.method()` hoặc sai manager | Bean khác qua proxy, kiểm transaction |
| App crash sau commit, không gửi thông báo | In-memory listener không durable | Transactional outbox |
| Outbox có hai worker cùng gửi một record | Poll `findOne` rồi gửi, không claim | `findAndModify` atomic + token/lease |
| Outbox gửi trùng dù `_id` unique | Crash sau external ACK, trước mark DELIVERED | Receiver idempotency theo eventId |
| Worker kẹt SENDING vĩnh viễn | Không có lease expiry/recovery | Lease timeout, fencing token, monitor |
| Worker A mark đè worker B | Không kiểm token khi update status | Conditional update với claimToken |
| Event mới commit nhưng worker chưa thấy | Poll interval/read preference/replication lag | Monitor lag, read consistency, retry scan |
| Change stream reconnect rồi bỏ mất event | Mất resume token hoặc oplog window | Persist checkpoint và polling reconciliation |
| Consumer nhận version 6 trước version 5 | Song song delivery không có ordering | Partition theo aggregate, version guard |
| Một event được publish hai lần từ business code | Thiếu idempotency/điều kiện transition | Guard state + unique eventId/fingerprint |
| Reactive listener không thấy transaction | Event thiếu reactive transaction context | Dùng TransactionalEventPublisher/context đúng |
| Reactive outbox bị commit một phần | Không gắn cả hai write trong cùng operator | Sequence update/insert và dùng reactive transaction |
| Test không thấy rollback trên standalone | MongoDB standalone không hỗ trợ multi-document transactions | Dùng replica set test |
| Test mock pass nhưng production email sai | Mock không kiểm commit/failure windows | Integration test + fault injection |
| Callback order/transaction khác kỳ vọng | Driver/bulk/update paths không qua lifecycle entity save | Đặt phát event trong application service |

## 21. Vận hành: giữ outbox chạy được lâu dài

Một outbox chỉ thực sự hữu ích khi worker và quy trình khôi phục được vận hành.

### 21.1. Metric/alert tối thiểu

| Metric | Ý nghĩa |
| --- | --- |
| `outbox.pending.count` | Số event chưa được gửi |
| `outbox.oldest_pending_age_seconds` | Tuổi event cũ nhất chưa delivery |
| `outbox.sending_expired_lease.count` | Worker crash/hang hoặc thiếu gia hạn lease |
| `outbox.delivery_latency` | Thời gian từ business commit tới external ACK |
| `outbox.delivery_attempts` | Retry storm và vấn đề dependency |
| `outbox.dead_letter.count` | Event cần manual remediation |
| `outbox.claim_conflicts` | Tranh chấp giữa workers |
| `outbox.mark_lost_lease` | Worker cũ cố mark sau khi token đổi |
| `external.idempotency_conflicts` | Cùng eventId nhưng payload khác |
| `transaction.commit_failures` | MongoDB tx/availability/durability |

Không tag metrics theo từng `orderId`/`eventId` trên hệ thống lớn vì cardinality tăng không giới hạn. Dùng trace/log có hạn chế PII để điều tra sự kiện cụ thể.

### 21.2. Retention và cleanup

Sau delivery:

- Có thể giữ `DELIVERED` trong thời gian audit/replay xác định.
- Có thể lưu vào archive riêng trước khi xóa.
- Có thể dùng TTL index theo timestamp **chỉ khi đã xác định đúng chính sách giữ lại**, không xóa PENDING/SENDING nhầm.
- Nếu dùng sharding, chú ý shard key, phân phối tải và transaction constraints.

**Không dùng `deleteMany({status: "PENDING"})` để “làm sạch queue chậm”.** Đó là mất công việc chưa hoàn tất.

### 21.3. Reconciliation job

Nên có job định kỳ đối chiếu:

~~~text
Orders APPROVED
    ↕
Outbox OrderApproved tương ứng
    ↕
External delivery acknowledgement
~~~

Trong thiết kế outbox đúng, việc thiếu outbox của một order APPROVED thường chỉ ra:

- Dữ liệu từ trước migration.
- Có code path cập nhật trực tiếp order mà không ghi outbox.
- Có sai phạm transaction/session.
- Có cleanup lỗi hoặc thao tác vận hành không an toàn.

Đối soát phải dựa trên version/transition ID, không kết luận mọi order APPROVED hiện tại đều cần một event mới nếu lịch sử đã được xử lý hoặc transition thuộc phiên bản khác.

### 21.4. Cân nhắc công bằng giữa tenants

Một tenant tạo nhiều event có thể chiếm toàn bộ worker capacity. Với hệ multi-tenant:

- Đặt rate limits/quota phù hợp.
- Không để batch chỉ chọn event của tenant lớn mãi.
- Dùng phân vùng/chia workers/round-robin có chủ đích nếu cần.
- Giữ isolation tenant trong payload và external destination.

Không truyền thẳng một `tenantId` không xác thực từ request HTTP tới external delivery endpoint có quyền lớn hơn.

## 22. Checklist trước khi phát hành

1. **Phân loại side effect:** best-effort hay bắt buộc được persist/retry?
2. **Phân biệt rõ** entity lifecycle callback với transaction completion.
3. **Không dùng `AfterSaveCallback` gửi email/HTTP** nếu DB write có thể abort.
4. **Dùng `@TransactionalEventListener(AFTER_COMMIT)`** cho notification best-effort có chấp nhận crash window.
5. **Kiểm fallbackExecution**: ngoài transaction phải bỏ qua hay được chạy ngay?
6. **Kiểm transaction manager, topology, proxy và MongoDatabaseFactory**.
7. **Đặt rollback rules** đúng cho checked/unchecked exceptions.
8. **Nhớ commit sau method body**, đừng gửi side effect bên ngoài quá sớm.
9. **Không ghi DB trong after-commit với assumption auto-new transaction**.
10. **Dùng outbox persist cùng transaction** nếu việc gửi không được mất khi process crash.
11. **Outbox eventId ổn định** và có unique constraint đúng semantics.
12. **State transition cần guard** tenant, state, version/idempotency.
13. **Claim outbox atomically** bằng `findAndModify` hoặc cơ chế tương đương.
14. **Dùng lease + fencing token**, có recovery khi worker crash.
15. **Không giữ MongoDB transaction qua external network call**.
16. **Receiver xử lý idempotent**; không tuyên bố exactly-once chỉ nhờ outbox.
17. **Thiết kế retry/backoff/dead-letter** theo loại lỗi và SLO.
18. **Xác định event ordering** nếu consumer phụ thuộc phiên bản aggregate.
19. **Giữ polling reconciliation** kể cả dùng change streams để đánh thức.
20. **Dùng reactive transaction manager/context đúng loại** với WebFlux.
21. **Kiểm commit/rollback qua trạng thái DB thật**, không chỉ kiểm callback invoked.
22. **Test crash window/timeout** trong môi trường chaos được phép và có cách khôi phục.
23. **Bảo vệ dữ liệu cá nhân**, event payload, logs và outbox retention.
24. **Có dashboards/alerts** cho pending age, retry, expired lease và dead-letter.

## 23. Bài thực hành có đáp án

### Bài 1 — `AfterSaveCallback`

Một `AfterSaveCallback` gửi email “Order approved”. Sau callback, service ném `IllegalStateException` và transaction rollback. Email có bị thu hồi không?

**Đáp án:** Không. Callback đã gọi external side effect trước commit. Cần dời email sang after-commit best effort hoặc durable outbox.

### Bài 2 — `@EventListener`

Chỉ dùng `@EventListener` trên event phát bên trong transactional service có chắc listener chạy sau commit không?

**Đáp án:** Không. `@EventListener` không gắn transaction phase; phải dùng `@TransactionalEventListener(AFTER_COMMIT)` hoặc cơ chế khác có transaction synchronization.

### Bài 3 — Event phát nhưng transaction rollback

Trong transaction T1, code publish `OrderApproved` rồi ném RuntimeException. Listener AFTER_COMMIT có gửi notification không?

**Đáp án:** Không, nếu transaction thực sự rollback và listener gắn đúng T1.

### Bài 4 — Checked exception

Service publish event rồi ném checked exception mặc định; Spring có thể commit không?

**Đáp án:** Có. Spring mặc định rollback RuntimeException/Error, không tự rollback checked exception nếu chưa cấu hình `rollbackFor`; nếu commit thì AFTER_COMMIT listener có thể chạy.

### Bài 5 — Không có transaction

Một `@TransactionalEventListener(AFTER_COMMIT)` được publish ngoài transaction với `fallbackExecution=false`. Điều gì xảy ra?

**Đáp án:** Listener bị bỏ qua vì không có transaction để gắn callback.

### Bài 6 — Fallback

Đặt `fallbackExecution=true` có nghĩa “đợi commit nếu không có transaction” không?

**Đáp án:** Không. Ngoài transaction, listener có thể thực thi ngay; không có commit nào để đợi.

### Bài 7 — Self-invocation

`this.approve()` gọi method `@Transactional` trên chính service. Vì sao AFTER_COMMIT listener có thể không chạy?

**Đáp án:** Lời gọi nội bộ bỏ qua proxy; transaction có thể chưa được mở, nên không có synchronization phase. Dùng entry point qua bean/proxy thực.

### Bài 8 — Ghi DB sau commit

Trong listener AFTER_COMMIT, bạn gọi `mongoTemplate.insert(audit)` và tin sẽ tự commit trong transaction mới. Nhận định đúng không?

**Đáp án:** Không. Tài nguyên transaction cũ có thể còn bound, không có commit mới. Nếu cần DB write độc lập, dùng service riêng `REQUIRES_NEW`; với dữ liệu cực kỳ quan trọng, ghi outbox/audit cùng transaction gốc.

### Bài 9 — Crash window

MongoDB commit thành công, application crash trước khi AFTER_COMMIT listener gọi email. Email có chắc được gửi sau restart không?

**Đáp án:** Không. In-memory listener không phải durable queue. Dùng transactional outbox để persist công việc trong cùng commit.

### Bài 10 — Transactional outbox

Transaction update order và insert outbox cùng nhau. Nếu outbox insert lỗi duplicate và transaction abort, order có còn APPROVED?

**Đáp án:** Không. Update trong transaction không được commit; outbox mới không được tạo. Outbox record cũ trước transaction vẫn tồn tại.

### Bài 11 — EventId

Retry request dùng eventId mới dù đó là cùng transition nghiệp vụ. Rủi ro?

**Đáp án:** Có thể tạo hai event logic giống nhau. Dùng ID ổn định dựa trên business transition, version hoặc command id.

### Bài 12 — Hai worker

Hai worker chạy `findOne({status:"PENDING"})` cùng lúc, rồi đều gửi event. Làm sao giảm tranh chấp?

**Đáp án:** Claim atomically bằng `findAndModify` và cập nhật PENDING → SENDING trong cùng operation.

### Bài 13 — Lease hết hạn

Worker A claim token A1; mất mạng lâu khiến lease hết hạn. Worker B claim token B2. A có được phép mark DELIVERED bằng token A1 không?

**Đáp án:** Không. Dùng conditional update trên `eventId + status + leaseToken`; token cũ không match.

### Bài 14 — Exactly-once

Outbox `_id` unique và worker chỉ chọn một event tại mỗi lần claim. Có bảo đảm external HTTP không bao giờ nhận hai request không?

**Đáp án:** Không. Worker có thể crash sau external ACK trước DB mark; retry gửi lại. Receiver nên hỗ trợ idempotency theo eventId.

### Bài 15 — External side effect trong transaction

Vì sao không giữ MongoDB transaction mở khi gọi SMTP/HTTP?

**Đáp án:** MongoDB không rollback external effect, giữ transaction lâu tăng resource contention/timeout, và lỗi remote làm nghiệp vụ khó đối soát. Tách outbox worker.

### Bài 16 — AFTER_ROLLBACK

Một lỗi xảy ra **trước** câu `events.publishEvent(...)`. Listener AFTER_ROLLBACK của event đó có được gọi không?

**Đáp án:** Không, vì event chưa được publish để đăng ký synchronization.

### Bài 17 — Reactive transaction

Có thể dùng `Mono.when(updateOrder, insertOutbox)` trong một `TransactionalOperator` không?

**Đáp án:** Không. Các operation trong cùng MongoDB transaction không được chạy song song, và outbox còn phụ thuộc update hợp lệ. Dùng `update.flatMap(...insert...).as(tx::transactional)`.

### Bài 18 — Reactive event context

Trong reactive code, dùng `ApplicationEventPublisher.publishEvent(event)` thông thường có tự động đảm bảo AFTER_COMMIT transaction listener nhìn thấy Reactor Context không?

**Đáp án:** Không. Spring Framework 6.1+ yêu cầu cung cấp transaction context qua event source; `TransactionalEventPublisher` hỗ trợ điều này. Với delivery quan trọng, ưu tiên reactive outbox.

### Bài 19 — Change stream

Nếu worker bỏ lỡ change stream notification vì resume token hết hạn, outbox record có mất không?

**Đáp án:** Nếu outbox được persist và chưa bị cleanup sai, record vẫn ở MongoDB. Worker có thể scan/reconciliation và claim lại; change stream chỉ là cơ chế wake-up.

### Bài 20 — Group ordering

Hai event `OrderApproved(v5)` và `OrderShipped(v6)` được gửi qua hai worker đồng thời. Có chắc receiver nhận v5 trước v6 không?

**Đáp án:** Không. Nếu ordering quan trọng, dùng aggregate partition/version guard, không chỉ sort theo createdAt ở query.

### Bài 21 — Kiểm thử

Test chỉ assert `NotificationGateway.notify...` được gọi một lần sau service call. Đã chứng minh business transaction commit chưa?

**Đáp án:** Chưa đủ. Phải đọc database state (order/outbox) sau transactional proxy call và kiểm rollback case, bằng MongoDB replica set test thật.

### Bài 22 — Retention

Có thể dùng `deleteMany({status:"PENDING"})` để giảm outbox size khi queue chậm không?

**Đáp án:** Không. Đó là xóa công việc chưa xử lý. Chọn cleanup/TTL chỉ cho dữ liệu đã delivered/đủ điều kiện theo retention policy.

### Bài 23 — Lỗi listener

Listener AFTER_COMMIT ném exception khi gửi email. MongoDB transaction có tự trở về PENDING không?

**Đáp án:** Không. Commit đã hoàn tất; lỗi listener không undo dữ liệu. Ghi nhận delivery failure và retry bằng outbox hoặc quy trình khác.

### Bài 24 — Khi nào không cần outbox?

Một metric theo dõi nội bộ “Order approved” đôi khi mất được, không ảnh hưởng nghiệp vụ. Có nhất thiết dùng transactional outbox không?

**Đáp án:** Không. Có thể dùng best-effort AFTER_COMMIT; chi phí outbox chỉ xứng đáng khi cần durability, retry và đối soát.

## Tài liệu tham khảo

- [Spring Data MongoDB — Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): `AbstractMongoEventListener`, mapping events, callback ordering và giới hạn.
- [Spring Data MongoDB — Entity Callbacks](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): `BeforeConvertCallback`, `BeforeSaveCallback`, `AfterSaveCallback` và reactive variants.
- [Spring Data MongoDB — Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, `ReactiveMongoTransactionManager`, transaction options và session binding.
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `save`, `updateFirst`, `findAndModify` và bulk behavior.
- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html): `@DomainEvents` và `@AfterDomainEventPublication`.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, phase, fallback, reactive transaction context.
- [Spring Framework — `TransactionalEventListener` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): phase, fallbackExecution và resource/commit caveats.
- [Spring Framework — `TransactionalEventPublisher` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html): publish event với reactive transaction context.
- [Spring Framework — `TransactionSynchronization` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): `afterCommit`, `afterCompletion` và tài nguyên bound.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRES_NEW`, rollback scope và proxy semantics.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): multi-document transaction atomicity và operational constraints.
- [MongoDB Manual — `findAndModify`](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/): atomic claim một document và kết quả trước/sau update.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): watching changes, resume token và giới hạn reconnect.
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): bảo đảm eventId/idempotency key duy nhất.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): majority, journal, acknowledgment và rollback risk.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): retry dưới lỗi tạm thời và điều kiện topology.
