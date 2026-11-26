# Xác định điểm hoàn thành của luồng bất đồng bộ

> **Chương:** Async verification  
> **Module học:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Định nghĩa khi nào một workflow bất đồng bộ giữa các application module thực sự hoàn tất; quan sát kết quả sau transaction commit, kiểm thử producer/consumer và bảo vệ kiến trúc với quality gate CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **request được tiếp nhận**, **event đã publish**, **producer commit**, **listener bắt đầu**, **consumer commit** và **workflow hoàn tất**.
2. Diễn đạt một **completion criterion** theo hành vi nghiệp vụ, dữ liệu quan sát được, ID tương quan và thời hạn.
3. Dùng `@ApplicationModuleTest` cùng `PublishedEvents` để kiểm tra producer, nhưng không nhầm bằng chứng publish với bằng chứng consumer hoàn tất.
4. Viết integration test cho `@ApplicationModuleListener` sau commit, dùng Awaitility chờ kết quả trong database qua API công khai của module consumer.
5. Phân biệt timeout của test với trạng thái nghiệp vụ `FAILED`, cũng như kiểm tra rollback, retry, duplicate và idempotency.
6. Thiết kế HTTP status/polling hoặc completion callback rõ nghĩa khi client không chờ được toàn bộ workflow.
7. Kết hợp `ApplicationModules.verify()`, test module, database và E2E trong quality gate CI để chống phụ thuộc sai và hồi quy bất đồng bộ.

**Câu hỏi trung tâm:** Nếu `POST /api/orders` đã trả thành công, `OrderPlaced` đã được phát và listener bắt đầu chạy, tại thời điểm nào chúng ta được phép khẳng định **“bước chuẩn bị giao hàng đã hoàn tất”**?

Câu trả lời phải dựa trên **hợp đồng nghiệp vụ và một điểm quan sát đáng tin**, không dựa vào tên annotation hay một dòng log.

## 2. Hoàn thành là một hợp đồng nghiệp vụ, không phải một lời gọi hàm

Xét ứng dụng Spring Modulith gồm `orders` và `fulfillment`. Sau khi đơn được đặt, module `fulfillment` tạo một task chuẩn bị giao hàng.

~~~mermaid
sequenceDiagram
    participant C as Client / Test
    participant O as orders
    participant DB1 as Orders DB
    participant EV as Spring Events
    participant F as fulfillment
    participant DB2 as Fulfillment DB

    C->>O: placeOrder(customerId)
    O->>DB1: INSERT order trong transaction
    O->>EV: publish OrderPlaced(orderId)
    Note over O,EV: Publish không đồng nghĩa đã commit
    O->>DB1: Commit order
    O-->>C: orderId / HTTP 202
    EV-->>F: Listener chạy sau commit
    F->>DB2: INSERT fulfillment task
    F->>DB2: Commit transaction consumer
    C->>F: Kiểm tra preparation status
    F-->>C: READY
~~~

Mỗi mốc cho một loại bằng chứng khác nhau:

| Mốc | Tín hiệu | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- | --- |
| A — Accepted | Server trả ID hoặc HTTP `202 Accepted` | Yêu cầu đã được tiếp nhận theo contract | Tác vụ downstream đã xong |
| B — Published | `publishEvent(...)` được gọi | Producer đã yêu cầu phát event | Transaction producer đã commit |
| C — Producer committed | Row của order đọc được sau commit | Dữ liệu producer tồn tại trong DB | Consumer xử lý thành công |
| D — Listener invoked | Callback/log trong consumer | Consumer đã bắt đầu xử lý | Side effect đã commit |
| E — Consumer committed | Task đọc được qua query ở transaction khác | Side effect cụ thể đã tồn tại | Bưu kiện đã giao thực tế |
| F — Business terminal state | State `READY`/`DELIVERED` theo hợp đồng | Công đoạn nghiệp vụ được định nghĩa đã hoàn tất | Những bước nằm ngoài công đoạn |

**Đặc biệt:** Producer có thể gọi `publishEvent(...)` *trước* khi transaction commit. Trong cấu hình listener sau commit, callback consumer không nên đồng nghĩa với event được phát trong một transaction cuối cùng rollback.

### Định nghĩa completion criterion tốt

Mỗi criterion cần trả lời năm câu hỏi:

1. **Đối tượng:** Workflow nào, nhận diện bằng `orderId` hay `workflowId` nào?
2. **Công đoạn:** Tạo task, cấp nhãn, gửi hãng vận chuyển hay giao hàng tận tay?
3. **Điều kiện thành công:** Trạng thái/side effect chính xác nào phải đúng?
4. **Nguồn quan sát:** API công khai, row đã commit, callback xác nhận hay receipt từ hệ thống ngoài?
5. **Thời hạn và lỗi:** Có được phép chờ vô hạn không? Nếu timeout/failed/retry thì xử lý thế nào?

Ví dụ:

> “Bước **chuẩn bị task fulfillment** cho `orderId=42` hoàn thành khi module `fulfillment` đã commit một task của order 42, và phép đọc mới qua public query API trả `READY`.”

Định nghĩa này **không** khẳng định bưu kiện đã được hãng vận chuyển nhận hoặc giao cho khách. Đó là những completion criterion khác.

## 3. Chọn mốc kết thúc theo đúng workflow

Một event có thể dẫn tới nhiều nhánh:

~~~text
OrderPlaced
  ├── fulfillment: tạo task chuẩn bị giao hàng
  ├── notifications: gửi email xác nhận
  ├── billing: khởi tạo yêu cầu thanh toán
  └── analytics: cập nhật chỉ số
~~~

Không phải lúc nào cũng chờ cả bốn nhánh. Nếu API chỉ cam kết **“order được tiếp nhận”**, commit đơn là đủ. Nếu báo cáo trạng thái **“sẵn sàng giao hàng”**, các bước tạo task/label tương ứng phải xong. Nếu cam kết **“email đã được giao”**, việc HTTP client của email provider trả 202 chỉ có thể chứng minh email được tiếp nhận, chưa chắc đến hộp thư.

| Workflow | Completion point có ý nghĩa | Điểm yếu dễ nhầm |
| --- | --- | --- |
| Tạo order | Order đã commit | Controller vừa vào method |
| Chuẩn bị fulfillment | Task `READY` đã commit | Event `OrderPlaced` được publish |
| Gửi email qua API | Provider xác nhận đã nhận yêu cầu, nếu contract chỉ cam kết enqueue | Hàm send được gọi |
| Email giao thành công | Delivery receipt theo bảo đảm provider | HTTP 2xx từ enqueue |
| Đồng bộ read model | Projection đạt version aggregate mong đợi | Listener bắt đầu |
| Thanh toán | Payment ở terminal state theo gateway contract | Đã tạo payment intent |
| Xuất báo cáo | File/manifest hoàn tất và có thể tải | Job được scheduler kích hoạt |

**Tên trạng thái phải có ngữ nghĩa rõ.** `COMPLETED`, `READY`, `SUCCEEDED` đều có thể phù hợp, nhưng cần chỉ rõ “completed *việc gì*”.

### Mô hình trạng thái mẫu

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED
    ACCEPTED --> PROCESSING
    PROCESSING --> READY: Side effect đã commit
    PROCESSING --> RETRY_WAIT: Lỗi tạm thời
    RETRY_WAIT --> PROCESSING: Retry
    PROCESSING --> FAILED: Lỗi terminal
    RETRY_WAIT --> FAILED: Hết điều kiện retry
    READY --> [*]
    FAILED --> [*]
~~~

Đây là **thiết kế trạng thái nghiệp vụ gợi ý**, không phải enum do Spring Modulith tự tạo. Một ứng dụng có thể dùng trạng thái hoặc tên khác; các test phải bám hợp đồng thật.

## 4. @ApplicationModuleListener làm gì và không làm gì?

`@ApplicationModuleListener` của Spring Modulith được dùng cho các listener module, theo mô hình điển hình là **xử lý sau commit**, **bất đồng bộ** và **trong transaction riêng**, với hạ tầng async/transaction và phiên bản tương thích.

Điều này có nghĩa:

- Phương thức producer có thể trả về trước khi consumer hoàn tất.
- Listener chỉ nên làm side effect cho event của transaction producer đã commit khi dùng cơ chế hậu commit.
- Consumer có thể ghi dữ liệu trong transaction riêng.
- Exception listener không nhất thiết được ném lại cho HTTP request producer.
- Việc callback được schedule hoặc bắt đầu không nói nó đã commit thành công.

~~~text
Transaction T1: orders
    INSERT order
    publish OrderPlaced
    COMMIT

Event hand-off / async executor
    (consumer có thể chưa được chạy)

Transaction T2: fulfillment
    INSERT fulfillment_task
    COMMIT
~~~

**Chú ý về độ bền:** Spring Modulith có cơ chế event publication registry và các adapter lưu trữ. Nhưng không tự suy ra retry vô hạn, giao đúng một lần hoặc event sống qua restart trong mọi ứng dụng. Cần xác nhận dependency, adapter và cấu hình resubmission/retry cụ thể.

### Điều kiện hoàn thành được test

Với công đoạn “tạo task fulfillment”, **đọc được task sau commit T2** là completion signal có ý nghĩa hơn lời gọi `publishEvent` trong T1.

Nếu listener chỉ gọi API ngoài để enqueue một job, việc T2 commit không nhất thiết chứng minh job ngoài đã kết thúc. Khi đó phải chọn một terminal signal khác, ví dụ callback hoặc receipt của provider.

## 5. Ví dụ dự án: orders phát event, fulfillment tạo task

Cấu trúc minh họa:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderCommands.java                 # Public API
│   ├── OrderPlaced.java                   # Public event
│   └── internal/
│       ├── OrderApplicationService.java
│       ├── web/OrderController.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/
    ├── FulfillmentQueries.java            # Public API
    ├── PreparationState.java              # Public enum
    └── internal/
        ├── OrderPreparationListener.java
        ├── FulfillmentQueryService.java
        ├── web/PreparationController.java
        └── persistence/
            ├── FulfillmentTask.java
            └── FulfillmentTaskRepository.java
~~~

Theo cơ chế phát hiện module mặc định, `orders` và `fulfillment` là application module. Kiểu ở package root của mỗi module là public API mặc định, còn `internal` là implementation nội bộ.

**Hợp đồng ví dụ:**

1. `OrderCommands.place(customerId)` tạo đơn trong transaction và trả ID.
2. Producer phát `OrderPlaced(orderId)`.
3. Consumer nhận event sau commit và lưu `FulfillmentTask`.
4. `FulfillmentQueries.statusFor(orderId)` trả `READY` khi task đã được commit; nếu chưa thấy task, trả `NOT_OBSERVED`.
5. `READY` ở đây chỉ nghĩa là **tạo task chuẩn bị giao hàng đã xong**, chưa phải hoàn tất vận chuyển.

`NOT_OBSERVED` được đặt tên cố ý: nếu chưa thấy task, ta **chưa biết** là đang chờ, xử lý thất bại, event bị mất hay order ID không tồn tại. Production cần trạng thái đầy đủ hơn khi business yêu cầu.

## 6. Mã Java của producer

### 6.1. Spring Boot entry point

**`src/main/java/com/example/shop/ShopApplication.java`**

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@EnableAsync` cho phép các phương thức async được thực thi theo executor của Spring. Production cần xác định pool size, rejection policy và exception handling, nhất là khi hệ thống chịu tải.

### 6.2. Public API của orders

**`src/main/java/com/example/shop/orders/OrderCommands.java`**

~~~java
package com.example.shop.orders;

public interface OrderCommands {
    long place(String customerId);
}
~~~

**`src/main/java/com/example/shop/orders/OrderPlaced.java`**

~~~java
package com.example.shop.orders;

public record OrderPlaced(long orderId) {}
~~~

Event record công khai chỉ mang dữ liệu cần thiết. Không nên gửi thẳng JPA entity hoặc lazy-loaded object nội bộ sang module consumer.

### 6.3. Orders persistence

**`src/main/java/com/example/shop/orders/internal/persistence/OrderEntity.java`**

~~~java
package com.example.shop.orders.internal.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_orders")
public class OrderEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String customerId;

    protected OrderEntity() {}

    public OrderEntity(String customerId) {
        this.customerId = customerId;
    }

    public Long getId() {
        return id;
    }
}
~~~

**`src/main/java/com/example/shop/orders/internal/persistence/OrderRepository.java`**

~~~java
package com.example.shop.orders.internal.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {}
~~~

### 6.4. Transaction và event publication

**`src/main/java/com/example/shop/orders/internal/OrderApplicationService.java`**

~~~java
package com.example.shop.orders.internal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.orders.OrderCommands;
import com.example.shop.orders.OrderPlaced;
import com.example.shop.orders.internal.persistence.OrderEntity;
import com.example.shop.orders.internal.persistence.OrderRepository;

@Service
class OrderApplicationService implements OrderCommands {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Override
    @Transactional
    public long place(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "customerId must not be blank");
        }

        var saved = orders.save(new OrderEntity(customerId));
        long id = saved.getId();

        publisher.publishEvent(new OrderPlaced(id));
        return id;
    }
}
~~~

Method `place(...)` được gọi qua Spring transaction proxy, nên transaction của service được commit theo semantics Spring khi method kết thúc thành công. Nhưng **trả về `orderId` không có nghĩa task fulfillment đã sẵn sàng**. Event được publish bên trong transaction producer, còn listener hậu commit có lịch thực thi riêng.

## 7. Mã Java của consumer và điểm hoàn thành READY

### 7.1. Public query API

**`src/main/java/com/example/shop/fulfillment/PreparationState.java`**

~~~java
package com.example.shop.fulfillment;

public enum PreparationState {
    NOT_OBSERVED,
    READY
}
~~~

**`src/main/java/com/example/shop/fulfillment/FulfillmentQueries.java`**

~~~java
package com.example.shop.fulfillment;

public interface FulfillmentQueries {
    PreparationState statusFor(long orderId);
}
~~~

### 7.2. Task lưu trong module fulfillment

**`src/main/java/com/example/shop/fulfillment/internal/persistence/FulfillmentTask.java`**

~~~java
package com.example.shop.fulfillment.internal.persistence;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "fulfillment_tasks")
public class FulfillmentTask {

    @Id
    private Long orderId;

    protected FulfillmentTask() {}

    public FulfillmentTask(long orderId) {
        this.orderId = orderId;
    }

    public Long getOrderId() {
        return orderId;
    }
}
~~~

**`src/main/java/com/example/shop/fulfillment/internal/persistence/FulfillmentTaskRepository.java`**

~~~java
package com.example.shop.fulfillment.internal.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface FulfillmentTaskRepository
        extends JpaRepository<FulfillmentTask, Long> {}
~~~

Primary key `orderId` bảo vệ bất biến không lưu hai task cho cùng ID. Nó **chưa đủ** để xử lý duplicate event đồng thời mà không phát sinh unique-constraint exception; phần 15 phân tích kỹ hơn.

### 7.3. Listener của consumer

**`src/main/java/com/example/shop/fulfillment/internal/OrderPreparationListener.java`**

~~~java
package com.example.shop.fulfillment.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTask;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTaskRepository;

@Component
class OrderPreparationListener {

    private final FulfillmentTaskRepository tasks;

    OrderPreparationListener(FulfillmentTaskRepository tasks) {
        this.tasks = tasks;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        if (!tasks.existsById(event.orderId())) {
            tasks.save(new FulfillmentTask(event.orderId()));
        }
    }
}
~~~

Trong ví dụ, công việc được định nghĩa là **tạo task**. Khi transaction listener commit thành công, phép đọc mới có thể thấy task. Nếu có nhiều bước như sinh nhãn vận chuyển hoặc gửi sang hãng giao hàng, không được coi việc insert task là điểm hoàn thành cho những bước ngoài này.

### 7.4. Query service đọc dữ liệu đã lưu

**`src/main/java/com/example/shop/fulfillment/internal/FulfillmentQueryService.java`**

~~~java
package com.example.shop.fulfillment.internal;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.PreparationState;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTaskRepository;

@Service
class FulfillmentQueryService implements FulfillmentQueries {

    private final FulfillmentTaskRepository tasks;

    FulfillmentQueryService(FulfillmentTaskRepository tasks) {
        this.tasks = tasks;
    }

    @Override
    @Transactional(readOnly = true)
    public PreparationState statusFor(long orderId) {
        return tasks.existsById(orderId)
                ? PreparationState.READY
                : PreparationState.NOT_OBSERVED;
    }
}
~~~

**Chủ sở hữu dữ liệu:** Module `fulfillment` cung cấp một query interface công khai, nhưng không xuất `FulfillmentTaskRepository` ra cho module khác. Đây là cách vừa có **điểm quan sát testable**, vừa bảo vệ ranh giới Spring Modulith.

## 8. Xác định oracle có ý nghĩa

Một *oracle* là điều kiện cho phép kết luận test đạt hay không đạt.

### Những assertion chưa đủ cho completion

~~~java
long orderId = orders.place("CUS-001");
assertThat(orderId).isPositive();
~~~

Đây chỉ là bằng chứng lệnh trả ID.

~~~java
assertThat(events.ofType(OrderPlaced.class))
        .anySatisfy(event ->
                assertThat(event.orderId()).isEqualTo(orderId));
~~~

Đây là bằng chứng publisher phát ít nhất một event có ID đúng, không phải consumer đã xử lý.

~~~java
verify(listener).on(any(OrderPlaced.class));
~~~

Đây là bằng chứng một lời gọi mock/spy được thực hiện, không chứng minh transaction consumer đã commit hoặc output có thể đọc.

### Oracle phù hợp với contract của ví dụ

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
                assertThat(fulfillment.statusFor(orderId))
                        .isEqualTo(PreparationState.READY));
~~~

Điều kiện này quan sát **state thuộc sở hữu consumer**, đúng `orderId` từ lần thử và chỉ thành công khi task đã nhìn thấy được qua query.

**Cảnh báo:** Nếu implementation của query luôn trả `READY` dù không có task, oracle vẫn có thể xanh. Đó là lý do cần test repository/query service độc lập và negative control cố ý bỏ listener để đảm bảo test thật sự phát hiện mất side effect.

### “Ít nhất một” khác “chính xác một”

`PublishedEvents.ofType(...).anySatisfy(...)` xanh nếu ít nhất một event khớp. Nếu business contract yêu cầu **mỗi order chỉ publish đúng một event**, cần thêm assertion cardinality theo API `PublishedEvents` của phiên bản đang dùng. Đừng diễn giải `anySatisfy` thành exactly-once.

## 9. @ApplicationModuleTest: chứng minh producer đã publish

Kiểm thử module producer trước giúp phát hiện lỗi gần nơi phát sinh.

**`src/test/java/com/example/shop/orders/OrderPublishedEventTest.java`**

~~~java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.TestPropertySource;

@ApplicationModuleTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:orders-publish;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderPublishedEventTest {

    @Autowired
    OrderCommands orders;

    @Test
    void publishes_order_placed_with_generated_id(
            PublishedEvents events) {

        long id = orders.place("CUS-PUBLISH");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }

    @Test
    void does_not_publish_invalid_request(
            PublishedEvents events) {

        assertThatThrownBy(() -> orders.place(" "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderPlaced.class)).isEmpty();
    }
}
~~~

**Đã chứng minh:** Một use case producer thực sự publish đúng kiểu/payload; validation đầu vào có thể ngăn việc publish.

**Chưa chứng minh:** Transaction producer đã commit khi sự kiện được ghi nhận, listener consumer đã chạy, event đã được lưu bền hoặc side effect đã hoàn thành. Những phép kiểm tra đó cần context/hạ tầng khác.

**Lưu ý test data:** Các test nên dùng fixture riêng hoặc isolation phù hợp. Bài trên dùng H2 và Hibernate schema chỉ cho môi trường học tập; production nên dùng migration theo dự án.

## 10. Integration test: quan sát READY sau commit

Để chứng minh producer → event → consumer → database, cần Spring context có **cả hai module**, transaction manager và listener thật. Nếu mục đích không bao gồm HTTP, không cần khởi động server.

**`src/test/java/com/example/shop/OrderFulfillmentCompletionTest.java`**

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import com.example.shop.orders.OrderCommands;
import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.PreparationState;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:fulfillment-flow;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderFulfillmentCompletionTest {

    @Autowired
    OrderCommands orders;

    @Autowired
    FulfillmentQueries fulfillment;

    @Test
    void finishes_when_fulfillment_task_is_committed() {
        String customerId = "CUS-" + UUID.randomUUID();
        long orderId = orders.place(customerId);

        assertThat(orderId).isPositive();

        await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() ->
                        assertThat(fulfillment.statusFor(orderId))
                                .isEqualTo(PreparationState.READY));
    }
}
~~~

### Bằng chứng cụ thể thu được

- **Stimulus thật:** Gọi `orders.place(...)` qua Spring bean của producer.
- **Commit thật:** Test không mở một outer transaction rollback mặc định; service tự quản lý transaction.
- **Consumer thật:** Listener `@ApplicationModuleListener` của fulfillment được nạp trong toàn application context.
- **Kết quả thật:** Public query API đọc trạng thái từ repository consumer.
- **Correlation:** Assert đúng task theo `orderId` vừa tạo.
- **Điều kiện chờ hữu hạn:** Nếu READY không xuất hiện, test thất bại trong ngân sách chờ.

### Vì sao không gắn @Transactional lên test class?

Khi test trực tiếp gọi Spring service và có `@Transactional`, service với propagation mặc định có thể **tham gia transaction của test**. Framework thường rollback transaction test sau khi kết thúc; listener `AFTER_COMMIT` có thể vì thế không được kích hoạt.

Ở ví dụ trên, method test **không** gắn `@Transactional` để service tự commit. Với HTTP E2E qua embedded server, transaction của request phía server và transaction của HTTP client test là hai boundary khác nhau; cần phân biệt khi tổ chức test.

### Timeout báo lỗi gì?

Nếu `await().atMost(10s)` hết hạn, chỉ có thể nói **“chưa quan sát được READY trong 10 giây”**. Nguyên nhân có thể là listener chưa đăng ký, thread pool hết tài nguyên, event fail, database rollback, query sai ID hoặc đơn giản là môi trường CI quá chậm. Không tự kết luận event đã bị mất.

## 11. HTTP API: accepted và ready phải khác nhau

Trong ứng dụng hướng tới client ngoài, server thường không giữ request mở cho đến khi mọi consumer xong. Cần cung cấp **cửa vào** và **cửa ra trạng thái**.

### 11.1. Endpoint tạo order

**`src/main/java/com/example/shop/orders/internal/web/OrderController.java`**

~~~java
package com.example.shop.orders.internal.web;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.shop.orders.OrderCommands;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderCommands orders;

    OrderController(OrderCommands orders) {
        this.orders = orders;
    }

    @PostMapping
    ResponseEntity<AcceptedOrder> place(
            @Valid @RequestBody PlaceOrderRequest request) {

        long id = orders.place(request.customerId());
        return ResponseEntity.accepted()
                .body(new AcceptedOrder(id));
    }

    public record PlaceOrderRequest(
            @NotBlank String customerId) {}

    public record AcceptedOrder(long orderId) {}
}
~~~

HTTP `202 Accepted` ở đây có nghĩa **request đã được chấp nhận để xử lý**, còn bước fulfillment có thể tiếp tục sau response. Một API khác có thể chọn `201 Created` cho order resource và thể hiện fulfillment riêng. Không có một mã HTTP bắt buộc cho mọi workflow.

### 11.2. Endpoint quan sát completion

**`src/main/java/com/example/shop/fulfillment/internal/web/PreparationController.java`**

~~~java
package com.example.shop.fulfillment.internal.web;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.PreparationState;

@RestController
@RequestMapping("/api/fulfillments")
class PreparationController {

    private final FulfillmentQueries queries;

    PreparationController(FulfillmentQueries queries) {
        this.queries = queries;
    }

    @GetMapping("/{orderId}/preparation")
    ResponseEntity<PreparationResponse> status(
            @PathVariable long orderId) {

        var state = queries.statusFor(orderId);
        var response = new PreparationResponse(orderId, state);

        if (state == PreparationState.READY) {
            return ResponseEntity.ok(response);
        }

        return ResponseEntity.accepted().body(response);
    }

    public record PreparationResponse(
            long orderId, PreparationState state) {}
}
~~~

Đây là **hợp đồng polling minh họa**, không phải khuyến nghị rằng GET status resource luôn phải dùng HTTP `202` khi còn chờ. Production thường trả `200 OK` kèm trạng thái `ACCEPTED/PROCESSING/READY/FAILED`, hoặc một thiết kế REST nhất quán khác.

**Giới hạn cần sửa khi triển khai thật:** Endpoint tối giản chưa kiểm tra order ID có tồn tại. ID không tồn tại cũng trả `202` mãi. Production cần phân biệt `404 UNKNOWN` với `PENDING` và `FAILED` bằng trạng thái workflow có chủ sở hữu rõ ràng, đồng thời có kiểm tra quyền truy cập khi phù hợp.

### 11.3. API E2E test chờ tới READY

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:fulfillment-http;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class FulfillmentHttpCompletionTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void client_observes_ready_state() {
        var created = http.postForEntity(
                "/api/orders",
                Map.of("customerId", "CUS-" + UUID.randomUUID()),
                JsonNode.class);

        assertThat(created.getStatusCode())
                .isEqualTo(HttpStatus.ACCEPTED);
        assertThat(created.getBody()).isNotNull();

        long orderId = created.getBody()
                .path("orderId").asLong();

        assertThat(orderId).isPositive();

        await()
                .atMost(Duration.ofSeconds(15))
                .pollInterval(Duration.ofMillis(150))
                .untilAsserted(() -> {
                    var state = http.getForEntity(
                            "/api/fulfillments/{id}/preparation",
                            JsonNode.class,
                            orderId);

                    assertThat(state.getStatusCode())
                            .isEqualTo(HttpStatus.OK);
                    assertThat(state.getBody()).isNotNull();
                    assertThat(state.getBody()
                            .path("orderId").asLong())
                            .isEqualTo(orderId);
                    assertThat(state.getBody()
                            .path("state").asText())
                            .isEqualTo("READY");
                });
    }
}
~~~

**Bằng chứng:** HTTP request đi qua controller, service, transaction, event, consumer persistence và HTTP observation point, đến trạng thái READY của đúng ID.

**Chưa chứng minh:** Browser/UI, dịch vụ ngoài bị mock, khả năng phục hồi qua restart và mọi trường hợp duplicate/retry. Phải bổ sung test khác khi các bảo đảm ấy là yêu cầu.

## 12. Timeout, terminal failure và trạng thái chưa xác định

Một phép kiểm tra completion cần phân biệt ba loại kết quả:

| Tình huống | Ý nghĩa | Cách ứng xử |
| --- | --- | --- |
| **READY** | Điều kiện nghiệp vụ cuối cùng đã được quan sát | Thành công và xác nhận output |
| **FAILED** | Server đã ghi nhận thất bại terminal theo policy | Dừng, báo nguyên nhân có ý nghĩa |
| **TIMEOUT/UNKNOWN** | Chưa thấy terminal state trong ngân sách | Không tự gán business FAILED; tra cứu tiếp/log hoặc fail test |

**Timeout của Awaitility không phải business state.** Một request có thể xử lý xong ngay sau khi client timeout; nếu client gửi lại thao tác tạo mới mà không có idempotency key, có thể tạo trùng dữ liệu.

### State model mở rộng

Đối với hệ thống production, có thể thiết kế:

~~~java
package com.example.shop.fulfillment;

public enum WorkflowState {
    ACCEPTED,
    PROCESSING,
    RETRY_WAIT,
    READY,
    FAILED
}
~~~

Đây là **một thiết kế mở rộng**, không thay `PreparationState` trong toàn bộ code ở trên nếu chưa cập nhật implementation. Khi có state rõ ràng, client có thể:

- Tiếp tục chờ với `ACCEPTED`, `PROCESSING`, `RETRY_WAIT`.
- Kết luận thành công khi thấy `READY` cùng kết quả yêu cầu.
- Dừng báo lỗi khi server đã ghi nhận `FAILED`.
- Trả “chưa xác định” khi hết deadline mà server chưa có terminal state.

Nếu test có thể nhìn thấy trạng thái terminal `FAILED`, nên fail sớm thay vì polling cho đến timeout như thể đó là một trạng thái pending.

### Chọn timeout hợp lý

`atMost(Duration.ofSeconds(10))` hoặc 15 giây trong ví dụ chỉ là **ngân sách chờ test minh họa**. Nó không phải SLA production. SLA cần xét percentiles, tải, tài nguyên và môi trường đo thích hợp.

Chọn `pollInterval` hợp lý, tránh gọi database/API quá dày hoặc chờ thưa quá mức. **Không dùng `Thread.sleep(...)` cố định** để thay điều kiện quan sát được.

## 13. Rollback: event đã publish nhưng producer chưa commit

Một transaction có thể publish event rồi rollback. Kiểm thử điều này phải kích hoạt **transaction thật và rollback thật**.

Ví dụ với `TransactionTemplate` trong integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.support.TransactionTemplate;

@Autowired
TransactionTemplate transactions;

@Test
void can_rollback_order_creation() {
    Long id = transactions.execute(status -> {
        long created = orders.place("CUS-ROLLBACK");
        status.setRollbackOnly();
        return created;
    });

    assertThat(id).isPositive();

    // Bổ sung một API truy vấn hoặc fixture database riêng
    // để xác nhận row orders thực sự không được commit.
}
~~~

Đây là **trích đoạn tạo rollback**, không phải một bài test hoàn chỉnh của “không có side effect”. Nếu muốn chứng minh rollback không kích hoạt listener sau commit:

1. Xác nhận dữ liệu producer đã rollback bằng query phù hợp.
2. Xác nhận listener được cấu hình hậu commit, không có fallback execution ngoài transaction nếu không chủ định.
3. Quan sát kết quả qua cơ chế đồng bộ/transaction hoặc publication state có ý nghĩa.
4. Không dùng một assertion âm tức thời để suy ra sẽ không bao giờ có side effect.

~~~java
// Bằng chứng yếu: NOT_OBSERVED ở một thời điểm
// không đủ chứng minh consumer sẽ không làm gì về sau.
assertThat(fulfillment.statusFor(id))
        .isEqualTo(PreparationState.NOT_OBSERVED);
~~~

`PublishedEvents` có thể ghi nhận **event được publish** trong transaction mà sau đó rollback. Điều đó không đồng nghĩa listener hậu commit đã xử lý event.

## 14. Completion signal từ workflow ngoài ứng dụng

Không phải mọi luồng async đều kết thúc trong một transaction JPA. Ví dụ `fulfillment` gọi API hãng vận chuyển để tạo nhãn.

~~~mermaid
sequenceDiagram
    participant L as Fulfillment listener
    participant EXT as Shipping provider
    participant DB as Workflow DB

    L->>EXT: POST create-label
    EXT-->>L: 202 Accepted + jobId
    L->>DB: Lưu jobId / PROCESSING
    Note over L,DB: Listener kết thúc không phải label đã tạo
    EXT-->>L: Callback label-ready
    L->>DB: Lưu receipt + READY
    Note over DB: Bây giờ mới đạt completion criterion "label ready"
~~~

Nếu listener thành công sau khi **enqueue** job ngoài, publication registry có thể coi listener đã xử lý xong. Nhưng trạng thái nghiệp vụ `READY` cho **label** vẫn chưa đạt; phải đợi callback, polling trạng thái provider hoặc một receipt phù hợp.

### Câu hỏi để chọn tín hiệu cuối

- External API trả “đã nhận” hay “đã hoàn tất”?
- Callback có được xác thực, chống giả mạo và xử lý trùng?
- Receipt có một ID liên kết với workflow gốc không?
- Có phân biệt thất bại terminal và đang retry?
- Nếu callback đến trước hoặc sau event khác, trạng thái xử lý thế nào?
- Khi ứng dụng restart, trạng thái ngoài và publication có khôi phục được không?

**Đừng đánh đồng kết thúc callback của listener với business completion**, trừ khi contract khẳng định mọi công đoạn bắt buộc đã xong ngay trong callback.

## 15. Duplicate delivery và idempotency

Một event có thể được xử lý lại do retry, replay hoặc gửi trùng. Một completion criterion mạnh cần kết hợp với bất biến về side effect.

~~~text
OrderPlaced(42) lần 1 -> task(42)
OrderPlaced(42) lần 2 -> ?
~~~

Bất biến mong muốn: **mỗi `orderId` có tối đa một task hợp lệ**, và xử lý event trùng theo policy không gây lỗi lặp không kiểm soát.

### Race condition

~~~text
Listener A: existsById(42) -> false
Listener B: existsById(42) -> false
Listener A: INSERT(42) -> commit
Listener B: INSERT(42) -> unique-constraint violation
~~~

Primary key bảo vệ số row nhưng một listener có thể vẫn lỗi và khiến publication bị retry mãi. Mô hình `existsById` rồi `save` chỉ đủ minh họa happy path, **không phải implementation idempotency production hoàn chỉnh**.

Các lựa chọn tùy loại database và hợp đồng gồm upsert, xử lý duplicate key theo transaction phù hợp, event ID/version, deduplication table và bảo đảm idempotency ở external provider.

| Rủi ro | Test cần có | Bằng chứng |
| --- | --- | --- |
| Event trùng tuần tự | Consumer integration | Một task, handler chấp nhận replay hợp lệ |
| Event trùng đồng thời | Concurrency + DB transaction | Không nhân đôi, không lỗi retry vô hạn |
| Consumer failure tạm thời | Failure injection + retry | Cuối cùng READY theo policy |
| Event cũ đến sau event mới | Ordering/version test | Không ghi đè state mới bằng state cũ |
| Client retry POST | API idempotency test | Cùng idempotency key không tạo hai order |

**“Có một task READY” chưa chứng minh quá trình tạo task chỉ chạy đúng một lần.** Completion test và reliability test giải quyết các mệnh đề khác nhau.

## 16. Event publication registry và độ bền completion

Spring Modulith cung cấp cơ chế quản lý event publications. Khi dùng adapter bền vững thích hợp, registry có thể ghi nhận publication chưa hoàn tất và trạng thái xử lý theo semantics của phiên bản/cấu hình.

Cần tách:

- **Producer published:** Event đã được phát từ module producer.
- **Registry publication completed:** Registry xác nhận handler/đường xử lý theo hợp đồng registry đã xong.
- **Business READY:** Kết quả nghiệp vụ cuối cùng đã xuất hiện theo contract.
- **External DONE:** Nhà cung cấp ngoài đã cấp receipt cuối cùng nếu công đoạn yêu cầu.

Nếu handler chỉ enqueue job cho hệ thống ngoài, registry completed **không tự động chứng minh job ngoài đã chạy xong**.

### Test recovery khi thật sự cần

1. Cấu hình adapter registry persistent tương ứng với hệ thống dùng.
2. Tạo consumer failure có thể điều khiển được.
3. Commit producer và xác nhận publication chưa hoàn tất theo API/semantics adapter.
4. Khởi động lại hoặc resubmit theo cơ chế được hỗ trợ.
5. Xác nhận side effect consumer cuối cùng đạt READY, không bị nhân đôi.
6. Kiểm tra publication hoàn tất theo registry và retention policy.

Không nên hard-code tên bảng, API resubmit hoặc khẳng định có retry vô hạn cho mọi phiên bản. Nếu durable delivery không nằm trong yêu cầu, test cùng JVM có thể đủ cho luồng tích hợp cơ bản; nếu **sống qua restart** là lời hứa nghiệp vụ, phải test storage và restart thực tế.

## 17. Correlation ID và tránh kết quả xanh giả

Một test chỉ kiểm tra “có task nào READY hay không” có thể vô tình đọc task từ test trước.

**Quy tắc:**

- Sinh customer/request ID riêng cho từng lần chạy.
- Ghi lại đúng `orderId` do producer trả về.
- Query consumer theo đúng `orderId` đó.
- Nếu workflow nhiều hệ thống, truyền `workflowId`/`correlationId` qua event, log, trace và status.
- Không giả định order đầu tiên luôn mang ID 1.
- Cô lập database/test fixture khi chạy song song.
- Phân biệt **correlation ID** dùng truy vết với **idempotency key** dùng ngăn tạo request trùng.

Ví dụ log do ứng dụng tự instrument:

~~~text
workflowId=...
orderId=...
producerCommitted=true
eventType=OrderPlaced
consumer=OrderPreparationListener
attempt=...
lastObservedState=NOT_OBSERVED
elapsedWait=...
lastFailure=...
~~~

Những field này **không tự được Spring Modulith ghi đầy đủ theo đúng tên**; developer cần bổ sung logging/tracing và lấy dữ liệu từ hạ tầng tương ứng.

Khi Awaitility timeout, log tối thiểu nên giúp trả lời: producer đã commit chưa, listener có chạy không, exception nào xuất hiện, task row có tồn tại không, query đọc ID nào và registry có pending publication hay không.

## 18. Chọn test type phù hợp với mốc cần chứng minh

| Bằng chứng cần thu | Test type ưu tiên | Lý do |
| --- | --- | --- |
| Logic/validation của producer | Unit test | Không cần Spring context |
| MVC trả `202` và đúng JSON | `@WebMvcTest` | HTTP adapter contract |
| Producer phát `OrderPlaced` | `@ApplicationModuleTest` + `PublishedEvents` | Kiểm tra public event contract |
| Orders JPA mapping/commit | JPA/module integration | Dữ liệu và transaction thật |
| Consumer sau commit tạo task | Cross-module integration + Awaitility | Quan sát side effect ở consumer |
| Native SQL/locking/constraint | Testcontainers với DB production-like | Giữ semantics DB |
| HTTP client thấy READY | `@SpringBootTest(RANDOM_PORT)` | Đi qua entry point thật |
| Event sống qua restart | Registry/recovery integration | Cần persistent adapter và restart |
| External label đã sẵn sàng | External contract/callback integration | Cần receipt cuối từ provider |
| Module không import nội bộ module khác | `ApplicationModules.verify()` | Kiểm tra dependency graph |

Một Spring Modulith có thể chạy đúng event nhưng vẫn import sai `internal`. Một architecture verification xanh cũng không bảo đảm consumer đã commit. Hai loại bằng chứng phải được thu riêng.

### Bài kiểm tra kiến trúc

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void modules_respect_public_api_boundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Module `fulfillment` có thể import kiểu công khai `orders.OrderPlaced`, nhưng không được import `orders.internal.persistence.OrderEntity` theo ranh giới module mặc định. `verify()` phát hiện quan hệ sai và vòng phụ thuộc theo rule áp dụng; nó **không** xác minh event listener chạy xong.

## 19. Database production-like và Testcontainers

Các test trước dùng H2 để tập trung vào completion signal. Nếu production dùng PostgreSQL/MySQL với isolation, locking, unique constraint hoặc SQL riêng, H2 không đại diện đầy đủ.

Khung Testcontainers với PostgreSQL:

~~~java
package com.example.shop;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.TestPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class FulfillmentPostgresIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Inject OrderCommands và FulfillmentQueries;
    // dùng cùng oracle READY ở mục 10.
}
~~~

Đây là **khung cấu hình**, không phải test method hoàn chỉnh. Dự án cần Spring Boot Testcontainers, Testcontainers Jupiter/PostgreSQL, driver và runtime container. `@ServiceConnection` có trong Spring Boot 3.1+; phải dùng version tương thích.

Với Flyway/Liquibase production, những test tích hợp quan trọng nên chạy migration thật. Khi test khả năng restart/recovery, storage cần sống đủ lâu cho toàn bộ vòng kiểm thử; đừng tắt container trước khi context đọc trạng thái còn pending.

### Dependency minh họa trong Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.modulith:spring-modulith-starter-core")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
    testRuntimeOnly("com.h2database:h2")

    // Nếu starter-test version hiện tại chưa cung cấp Awaitility:
    // testImplementation("org.awaitility:awaitility")

    // Thêm khi dùng PostgreSQL Testcontainers:
    // testImplementation("org.springframework.boot:spring-boot-testcontainers")
    // testImplementation("org.testcontainers:junit-jupiter")
    // testImplementation("org.testcontainers:postgresql")
    // runtimeOnly("org.postgresql:postgresql")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đây là đoạn dependencies minh họa, chưa phải build script đầy đủ và **chưa tự bật durable publication registry**.

## 20. Troubleshooting khi không thấy completion

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra |
| --- | --- | --- |
| Event test xanh, integration test timeout | Consumer không được nạp hoặc không được đăng ký | Bean listener/context và annotation |
| Listener được gọi, READY không xuất hiện | Exception/JPA rollback hoặc query sai ID | Log transaction, repository, correlation |
| Test fail ngẫu nhiên khi đọc ngay | Async chưa chạy xong | Await condition có timeout |
| Test `@Transactional` không gọi listener | Transaction test rollback; không có AFTER_COMMIT | Cho service transaction commit thật |
| Đã có READY nhưng external label chưa có | READY được đặt quá sớm | Thiết kế lại business completion point |
| API trả 202 mãi cho ID không tồn tại | Không có status model phân biệt UNKNOWN | Tách 404/unknown khỏi pending |
| Timeout bị báo như FAILED | Trộn test deadline với business state | Giữ trạng thái chưa xác định, quan sát server |
| Retry khiến task lỗi unique liên tục | Handler chưa idempotent an toàn | Upsert/duplicate handling và concurrency test |
| Registry completed nhưng business chưa xong | Handler chỉ enqueue công việc ngoài | Theo dõi receipt/terminal state bên ngoài |
| PostgreSQL production khác H2 | Dialect/isolation/migration khác | Test DB production-like |
| E2E xanh nhưng `verify()` đỏ | Import vượt ranh giới module | Sửa API/dependency, giữ architecture gate |

Khi test không đạt, đừng chỉ tăng thời hạn chờ. Hãy xác định lỗi ở **mốc nào của luồng** bằng cách kiểm tra lần lượt producer commit, event, listener, consumer transaction và observation API.

## 21. Quality gate CI cho completion semantics

~~~mermaid
flowchart LR
    PR["Pull request"] --> U["Unit + adapter tests"]
    U --> A["ApplicationModules.verify()"]
    A --> P["Publisher module tests"]
    P --> I["Consumer after-commit tests"]
    I --> R["Retry / idempotency / registry"]
    R --> E["Critical HTTP E2E"]
    E --> G{"Các gate bắt buộc xanh?"}
    G -- "Có" --> OK["Cho phép merge/release"]
    G -- "Không" --> FIX["Điều tra và sửa"]
~~~

| Gate | Bằng chứng | Khi nào quan trọng |
| --- | --- | --- |
| Unit/slice | Validation và mapping | Mọi PR |
| Architectural test | Dependency/package đúng | Mọi PR, bắt buộc |
| Module + `PublishedEvents` | Producer phát đúng event | Mọi PR liên quan workflow |
| Consumer integration | Side effect sau commit quan sát được | Luồng bất đồng bộ trọng yếu |
| Testcontainers integration | DB constraint/transaction đúng | Khi rủi ro database cao |
| Reliability/recovery | Duplicate, retry, registry và restart | Theo cam kết độ tin cậy |
| HTTP E2E | Client thấy terminal READY từ API | Hành trình công khai quan trọng |

Bên cạnh pass/fail, có thể theo dõi: thời gian từ producer commit đến READY, tỷ lệ workflow quá deadline, publication pending, retry attempts, duplicate deliveries và timeout/flakiness CI. Ngưỡng phải dựa trên baseline và SLA của dự án, không lấy 10–15 giây ví dụ làm quy chuẩn chung.

Nếu chia test thành nhiều CI job, cần đảm bảo các job bắt buộc thực sự được chạy trước merge/release. Không bỏ qua integration test consumer chỉ vì publisher test nhanh hơn.

## 22. Bài thực hành

### Bài A — Định nghĩa ba completion point khác nhau

Với workflow `OrderPlaced → fulfillment → email → analytics`, hãy định nghĩa:

1. **Order created:** Order được commit và có ID.
2. **Fulfillment prepared:** Task `READY` đã commit.
3. **Email delivered:** Có receipt cuối theo hợp đồng provider (nếu hỗ trợ).

Cho mỗi criterion, nêu ID tương quan, nguồn quan sát, thời hạn và những điều chưa được chứng minh.

### Bài B — Bắt lỗi báo READY quá sớm

Tách một preparation port giả lập bước xử lý tốn thời gian. Dùng fake có thể chặn tiến trình để kiểm tra: trước khi bước bắt buộc hoàn thành, trạng thái không được READY; sau khi bước đó thành công và transaction commit, mới được READY.

**Điều kiện đạt:** Test đỏ nếu ứng dụng đánh dấu READY ngay khi listener vừa bắt đầu.

### Bài C — Producer test và consumer test

Viết test `PublishedEvents` rồi trong nhánh thực hành tạm bỏ `@ApplicationModuleListener` khỏi consumer. Producer test vẫn có thể xanh; integration test chờ READY phải timeout. Khôi phục listener và chạy lại.

### Bài D — Rollback sau publish

Dùng `TransactionTemplate`, gọi `orders.place(...)` rồi rollback. Xác minh row order không commit và thiết kế test về việc listener hậu commit không tạo side effect sai. Giải thích vì sao một assertion `NOT_OBSERVED` tức thời chưa đủ.

### Bài E — Phân biệt timeout và terminal failure

Mở rộng state model với `ACCEPTED`, `PROCESSING`, `RETRY_WAIT`, `READY`, `FAILED`. Thiết kế polling: tiếp tục ở trạng thái đang xử lý, thành công ở READY, fail sớm ở FAILED và dừng chưa xác định khi hết deadline. Xử lý ID không tồn tại rõ ràng.

### Bài F — Duplicate và retry

Phát lại `OrderPlaced` cùng `orderId` hai lần tuần tự rồi đồng thời. Kiểm tra task không nhân đôi và handler không gây retry vô hạn do unique violation. Đề xuất chiến lược idempotency ở database.

### Bài G — Kiểm tra DB production-like

Đổi H2 thành PostgreSQL Testcontainers, chạy migration production nếu dùng Flyway/Liquibase. Quan sát transaction và unique constraint khi event consumer cạnh tranh.

### Bài H — Bảo vệ dependency module

Chạy `ApplicationModules.of(ShopApplication.class).verify()`. Thử thêm import từ `fulfillment` sang `orders.internal.persistence.OrderEntity`, xác minh architecture test đỏ rồi sửa để chỉ phụ thuộc vào public event.

### Câu hỏi tự kiểm tra

1. Vì sao `202 Accepted` không chứng minh fulfillment READY?
2. `PublishedEvents` có chứng minh transaction consumer đã commit không?
3. Khi nào listener return vẫn chưa nghĩa là external workflow hoàn tất?
4. Timeout của test và business `FAILED` khác nhau thế nào?
5. Vì sao “chưa có task” không đủ để kết luận order đang pending?
6. Unique constraint có tự khiến handler idempotent trong mọi tình huống không?
7. Khi nào cần test publication registry và restart?
8. Vì sao integration/E2E xanh vẫn cần `ApplicationModules.verify()`?

## 23. Checklist xác định điểm hoàn thành

- [ ] Đã định nghĩa rõ công đoạn nghiệp vụ được gọi là hoàn thành.
- [ ] Có `orderId`/`workflowId` để liên kết đúng request và kết quả.
- [ ] Phân biệt accepted, published, committed, invoked và terminal outcome.
- [ ] Oracle quan sát được state sau commit, không chỉ callback invocation.
- [ ] External side effect phân biệt enqueue/ack với terminal receipt.
- [ ] UNKNOWN/PENDING/FAILED không bị nhập nhằng khi nghiệp vụ cần phân biệt.
- [ ] Timeout được hiểu là deadline quan sát, không tự đổi thành business FAILED.
- [ ] Test async dùng điều kiện chờ với timeout; không dùng `Thread.sleep` cố định.
- [ ] Transaction test không vô tình rollback trước khi listener hậu commit chạy.
- [ ] Test data độc lập và assertion dùng đúng ID của lần chạy.
- [ ] Đã thiết kế duplicate/retry/idempotency theo rủi ro nghiệp vụ.
- [ ] Durable publication và restart được test nếu là cam kết.
- [ ] `ApplicationModules.verify()` bảo vệ quan hệ dependency giữa module.
- [ ] CI thực thi các test bắt buộc, có log/trace hỗ trợ chẩn đoán.
- [ ] Có negative control để phát hiện READY quá sớm hoặc listener bị bỏ.

## 24. Ghi nhớ

**Xác định điểm hoàn thành của luồng bất đồng bộ** là chọn một **sự thật nghiệp vụ có thể quan sát**, không nhầm request được nhận, event được publish hay listener bắt đầu với việc nghiệp vụ đã hoàn tất. Trong Spring Modulith, `@ApplicationModuleTest` và `PublishedEvents` xác minh contract phát event của producer; integration test với `@ApplicationModuleListener`, database và Awaitility xác minh side effect sau commit của consumer.

Khi workflow phụ thuộc broker, publication registry hoặc dịch vụ ngoài, phải làm rõ durable delivery, retry, terminal state và receipt cuối theo hợp đồng thực tế. Kết hợp kiểm thử completion với `ApplicationModules.verify()` và quality gate CI để đồng thời bảo vệ **giao tiếp bất đồng bộ** và **ranh giới kiến trúc application module**.
