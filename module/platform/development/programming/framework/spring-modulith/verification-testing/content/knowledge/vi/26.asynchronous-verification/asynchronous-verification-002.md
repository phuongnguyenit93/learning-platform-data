# Event publication và listener execution khác nhau thế nào?

> **Chương:** Async verification  
> **Module đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Mục tiêu:** Phân biệt việc module phát sự kiện với việc module khác thực thi listener, kiểm tra đúng pha transaction, side effect và trạng thái xử lý trong Spring Modulith, rồi đưa các phép kiểm tra cần thiết vào quality gate CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt các mốc: **producer publish**, **event được dispatch**, **producer commit**, **listener bắt đầu**, **consumer commit** và **business completion**.
2. Giải thích ảnh hưởng của `@EventListener`, `@Async`, `@TransactionalEventListener` và `@ApplicationModuleListener` tới thời điểm, thread và transaction thực thi.
3. Viết `@ApplicationModuleTest` với `PublishedEvents` để xác minh hợp đồng phát sự kiện của producer.
4. Viết integration test với Awaitility và database để chứng minh listener sau commit thật sự tạo side effect ở module consumer.
5. Kiểm thử rollback, listener lỗi, retry và duplicate delivery mà không suy diễn quá phạm vi của assertion.
6. Phân biệt Event Publication Registry, event delivery và trạng thái hoàn thành nghiệp vụ; chọn đúng completion oracle.
7. Giữ ranh giới module bằng `ApplicationModules.verify()` và tổ chức các lớp kiểm thử trong quality gate CI.

**Câu hỏi trọng tâm:** `orders` gọi `publishEvent(new OrderPlaced(id))` rồi trả về ID. Điều đó có chứng minh `fulfillment` đã tạo task giao hàng chưa? **Không**, trừ khi hợp đồng dispatch, transaction và trạng thái consumer đã được kiểm chứng bằng những tín hiệu phù hợp.

## 2. Một lời gọi publish, nhiều sự kiện thời gian khác nhau

Mô hình đơn hàng điển hình:

~~~mermaid
sequenceDiagram
    participant T as Test/HTTP client
    participant O as orders
    participant ODB as Orders DB
    participant PUB as Spring Event publisher
    participant L as fulfillment listener
    participant FDB as Fulfillment DB

    T->>O: placeOrder(customerId)
    O->>ODB: INSERT order trong transaction T1
    O->>PUB: publishEvent(OrderPlaced)
    Note over O,PUB: Đã publish nhưng T1 chưa chắc commit
    O->>ODB: Commit T1
    O-->>T: orderId
    PUB-->>L: Listener được kích hoạt theo cấu hình
    L->>FDB: INSERT task trong transaction T2
    L->>FDB: Commit T2
    T->>L: Query trạng thái theo orderId
    L-->>T: Task tồn tại
~~~

Có ít nhất sáu mốc cần phân biệt:

| Mốc | Quan sát | Kết luận có cơ sở | Không được kết luận |
| --- | --- | --- | --- |
| **P — Published** | Producer gọi `publishEvent(...)` | Producer công bố tín hiệu | Transaction đã commit, listener thành công |
| **D — Dispatched** | Event multicaster giao hoặc lên lịch xử lý | Có quá trình dispatch/scheduling | Tác vụ consumer đã xong |
| **C1 — Producer committed** | Row order đọc được sau commit | Dữ liệu producer đã commit | Side effect consumer đã xuất hiện |
| **L — Listener invoked** | Callback bắt đầu | Consumer đã nhận lời gọi xử lý | Transaction consumer đã commit |
| **C2 — Consumer committed** | Task đọc được qua query mới | Side effect cụ thể đã lưu thành công | Những công đoạn bên ngoài task đã xong |
| **B — Business completed** | Terminal state/receipt theo hợp đồng | Công đoạn nghiệp vụ được định nghĩa đã xong | Các bước ngoài hợp đồng |

Đây là **các mệnh đề độc lập**. Test quan sát P không mặc nhiên chứng minh L hoặc C2. Ngược lại, một integration test thấy C2 chứng minh hệ thống đã đạt kết quả cuối mong muốn cho ca đó, nhưng không nhất thiết chứng minh cơ chế lưu bền event qua restart.

### Hoàn thành cái gì?

Giả sử việc giao hàng có ba bước:

~~~text
OrderPlaced
    -> tạo fulfillment task
    -> tạo nhãn vận chuyển
    -> hãng vận chuyển giao đến khách
~~~

“Đã tạo task” có thể hoàn tất tại C2, còn “nhãn đã sẵn sàng” đòi callback hoặc receipt của hãng vận chuyển. Không dùng một từ `COMPLETED` cho cả ba công đoạn khi hợp đồng khác nhau.

## 3. Bản thân ApplicationEventPublisher bảo đảm điều gì?

Spring cung cấp `ApplicationEventPublisher`:

~~~java
publisher.publishEvent(new OrderPlaced(orderId));
~~~

Đây là API **công bố event** tới hạ tầng application events hiện tại. Bản thân lời gọi không khẳng định:

- Event đã được lưu bền vào broker hoặc event publication registry.
- Transaction hiện tại đã commit.
- Mọi listener chạy trên thread khác.
- Mọi listener đã xử lý không lỗi.
- Side effect của consumer có thể đọc từ một transaction khác.
- Event sẽ được giao đúng một lần hoặc retry vô hạn.

Tuy nhiên, cũng **không được khẳng định mọi listener luôn chạy sau khi `publishEvent` trả về**. Với `@EventListener` đồng bộ và multicaster mặc định, listener thường thực thi **ngay trong quá trình publish**, trước khi lời gọi trả về.

**Khác biệt quan trọng:** Publication là hành vi của **producer và event infrastructure**. Listener execution là hành vi của **consumer**; thời điểm của nó phụ thuộc cách khai báo listener, thread, transaction phase và cấu hình runtime.

## 4. @EventListener, @Async và @ApplicationModuleListener khác nhau ra sao?

| Cơ chế | Thời điểm điển hình | Thread | Transaction | Hậu quả khi kiểm thử |
| --- | --- | --- | --- | --- |
| `@EventListener` | Khi multicaster phân phối; thường ngay lúc publish | Thường cùng thread nếu dùng multicaster đồng bộ | Không mặc định đợi commit | Listener có thể chạy trước khi transaction producer commit |
| `@Async @EventListener` | Khi executor nhận tác vụ | Thread executor khi async được bật | `@Async` không tự bảo đảm AFTER_COMMIT | Consumer có thể chạy trước commit và lỗi không tự truyền ngược |
| `@TransactionalEventListener(AFTER_COMMIT)` | Theo pha sau transaction commit | Thường cùng thread commit nếu không async | Có ràng buộc transaction phase | Không đồng nghĩa tự mở transaction mới cho việc ghi DB |
| `@ApplicationModuleListener` | Mẫu listener module sau commit | Thường bất đồng bộ | Thường dùng transaction mới cho listener | Thích hợp tương tác module nhưng vẫn cần kiểm thử side effect |

Bảng trên mô tả mô hình sử dụng phổ biến. `ApplicationEventMulticaster`, executor, transaction manager và phiên bản thư viện có thể được tùy biến; phải kiểm tra cấu hình thật trước khi dựa vào một chi tiết về thread hoặc thời gian.

### 4.1. @EventListener đồng bộ

~~~java
@Component
class AuditListener {

    @EventListener
    void on(OrderPlaced event) {
        // Thường được gọi ngay trong quá trình publishEvent(...)
        // nếu multicaster dùng cơ chế đồng bộ mặc định.
    }
}
~~~

Nếu producer publish bên trong transaction T1, listener này có thể chạy trước commit. Exception từ listener đồng bộ cũng có thể ảnh hưởng đường gọi producer, tùy multicaster và error handler. Test listener được gọi chưa đủ chứng minh T1 đã commit.

### 4.2. @Async @EventListener

~~~java
@Component
class AsyncAuditListener {

    @Async
    @EventListener
    void on(OrderPlaced event) {
        // Chạy bằng executor khi @EnableAsync được bật.
    }
}
~~~

`@Async` quyết định **cách thực thi bất đồng bộ**, không mặc nhiên quyết định **pha transaction**. Một tác vụ có thể được executor chạy trước khi T1 commit. Vì vậy không dùng riêng `@Async @EventListener` để bảo đảm consumer chỉ thấy dữ liệu producer đã commit.

### 4.3. @TransactionalEventListener(AFTER_COMMIT)

~~~java
@Component
class AfterCommitAuditListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) {
        // Chỉ xử lý ở pha sau commit khi có transaction phù hợp.
    }
}
~~~

Đoạn code cần import `org.springframework.transaction.event.TransactionPhase` và `org.springframework.transaction.event.TransactionalEventListener`. Khi không có transaction hoạt động, listener kiểu này thường **không được kích hoạt**, trừ khi thiết lập `fallbackExecution = true`.

**Điểm tinh tế:** Gọi callback ở pha AFTER_COMMIT không tự mở một transaction mới. Tài nguyên transaction cũ có thể vẫn gắn với thread và việc ghi database trong callback không tự được commit như mong muốn. Nếu consumer cần ghi dữ liệu, phải thiết kế transaction mới có chủ đích.

### 4.4. @ApplicationModuleListener

~~~java
@Component
class FulfillmentListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Xử lý event theo mô hình module listener của Spring Modulith.
    }
}
~~~

`@ApplicationModuleListener` là shortcut phổ biến kết hợp hành vi của `@Async`, `@TransactionalEventListener` và `@Transactional(propagation = REQUIRES_NEW)`. Nó giảm công cấu hình cho listener hậu commit độc lập, nhưng **không** tự làm hệ thống có exactly-once delivery, idempotency, retry vô hạn hoặc business workflow completed.

## 5. Transaction producer và consumer là hai ranh giới khác nhau

Mẫu điển hình:

~~~text
T1 — orders:
    INSERT order
    publish OrderPlaced
    COMMIT

Event hand-off:
    dispatch hoặc schedule listener
    (có thể phải chờ thread)

T2 — fulfillment:
    INSERT fulfillment task
    COMMIT
~~~

Nếu T1 rollback sau khi publish, listener `AFTER_COMMIT` không nên được thực thi cho một giao dịch chưa commit. Nếu T1 commit nhưng T2 thất bại, đơn hàng có thể tồn tại trong khi task fulfillment chưa được tạo.

~~~mermaid
flowchart LR
    P["Publish trong T1"] --> C{"T1 commit?"}
    C -- "Không" --> X["Không chạy callback<br/>AFTER_COMMIT"]
    C -- "Có" --> L["Kích hoạt listener"]
    L --> T{"T2 commit?"}
    T -- "Có" --> S["Side effect đã lưu"]
    T -- "Không" --> F["Consumer failure<br/>cần quan sát và phục hồi"]
~~~

Vì thế test cần tách:

1. **Publisher contract test** quan sát event phát ra.
2. **After-commit consumer test** quan sát side effect sau khi T2 commit.
3. **Rollback/failure test** xem điều gì xảy ra khi T1 hoặc T2 không thành công.

Một assertion duy nhất về event trong `PublishedEvents` không thể thay ba phép kiểm tra trên.

## 6. Case study: orders phát event, fulfillment nhận event

Ứng dụng Spring Boot giả định cấu trúc:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderCommands.java                   # Public API
│   ├── OrderPlaced.java                    # Public event
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/
    ├── FulfillmentQueries.java             # Public API
    └── internal/
        ├── OrderPlacedListener.java
        ├── FulfillmentQueryService.java
        └── persistence/
            ├── FulfillmentTask.java
            └── FulfillmentTaskRepository.java
~~~

Theo cơ chế nhận diện module mặc định của Spring Modulith, `orders` và `fulfillment` là application module. Kiểu ở root package là API công khai mặc định; package `internal` thuộc implementation riêng.

Trong ví dụ:

- `OrderCommands.place(customerId)` tạo order và trả `UUID`.
- Producer phát `OrderPlaced(orderId)` bên trong transaction tạo order.
- Consumer nhận event sau commit, lưu một fulfillment task.
- `FulfillmentQueries.hasTask(orderId)` xác nhận task hiện có qua API của consumer.
- **Điểm hoàn thành của công đoạn** là task đã được commit và có thể đọc; chưa có lời hứa giao hàng thực tế.

## 7. Triển khai producer và public event API

### 7.1. Ứng dụng

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

`@EnableAsync` hỗ trợ thực thi async của Spring. Dự án thật cần cấu hình executor, exception handling và capacity; bật async không đồng nghĩa có durable queue.

### 7.2. API và event

**`src/main/java/com/example/shop/orders/OrderCommands.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public interface OrderCommands {
    UUID place(String customerId);
}
~~~

**`src/main/java/com/example/shop/orders/OrderPlaced.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

Event nên mang dữ liệu immutable cần thiết, không đưa JPA entity hoặc repository implementation sang module consumer.

### 7.3. Persistence của orders

**`src/main/java/com/example/shop/orders/internal/persistence/OrderEntity.java`**

~~~java
package com.example.shop.orders.internal.persistence;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "shop_orders")
public class OrderEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private String customerId;

    protected OrderEntity() {}

    public OrderEntity(String customerId) {
        this.customerId = customerId;
    }

    public UUID getId() {
        return id;
    }
}
~~~

**`src/main/java/com/example/shop/orders/internal/persistence/OrderRepository.java`**

~~~java
package com.example.shop.orders.internal.persistence;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {}
~~~

Ví dụ dùng Java 17+ và JPA hỗ trợ `GenerationType.UUID`. Dự án dùng ID kiểu khác có thể thay thế mà không ảnh hưởng ý nghĩa publish–listener.

### 7.4. Service publish trong T1

**`src/main/java/com/example/shop/orders/internal/OrderApplicationService.java`**

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

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
    public UUID place(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "customerId must not be blank");
        }

        var saved = orders.save(new OrderEntity(customerId));
        UUID orderId = saved.getId();

        publisher.publishEvent(new OrderPlaced(orderId));
        return orderId;
    }
}
~~~

**Quan trọng:** `publishEvent(...)` được gọi **trong T1**, trong khi việc commit của transaction do Spring proxy quản lý xảy ra ở ranh giới phương thức. `return orderId` không bảo đảm `fulfillment` đã ghi task.

## 8. Triển khai consumer và điểm quan sát side effect

### 8.1. Public query API

**`src/main/java/com/example/shop/fulfillment/FulfillmentQueries.java`**

~~~java
package com.example.shop.fulfillment;

import java.util.UUID;

public interface FulfillmentQueries {
    boolean hasTask(UUID orderId);
}
~~~

### 8.2. Task entity và repository

**`src/main/java/com/example/shop/fulfillment/internal/persistence/FulfillmentTask.java`**

~~~java
package com.example.shop.fulfillment.internal.persistence;

import java.util.UUID;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "fulfillment_tasks")
public class FulfillmentTask {

    @Id
    private UUID orderId;

    protected FulfillmentTask() {}

    public FulfillmentTask(UUID orderId) {
        this.orderId = orderId;
    }
}
~~~

**`src/main/java/com/example/shop/fulfillment/internal/persistence/FulfillmentTaskRepository.java`**

~~~java
package com.example.shop.fulfillment.internal.persistence;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface FulfillmentTaskRepository
        extends JpaRepository<FulfillmentTask, UUID> {}
~~~

Chọn `orderId` làm primary key ngăn database có hai row cùng ID. Điều đó **không tự bảo đảm** handler xử lý an toàn khi hai event trùng tới đồng thời; mục 15 trình bày rủi ro race.

### 8.3. Listener hậu commit

**`src/main/java/com/example/shop/fulfillment/internal/OrderPlacedListener.java`**

~~~java
package com.example.shop.fulfillment.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTask;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTaskRepository;

@Component
class OrderPlacedListener {

    private final FulfillmentTaskRepository tasks;

    OrderPlacedListener(FulfillmentTaskRepository tasks) {
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

Mốc listener **được gọi** xảy ra khi `on(...)` bắt đầu. Mốc **consumer commit** xảy ra sau khi transaction xử lý hoàn tất. Ngay cả khi `tasks.save(...)` trả về, transaction T2 vẫn có thể fail/rollback sau đó.

### 8.4. Query service của fulfillment

**`src/main/java/com/example/shop/fulfillment/internal/FulfillmentQueryService.java`**

~~~java
package com.example.shop.fulfillment.internal;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTaskRepository;

@Service
class FulfillmentQueryService implements FulfillmentQueries {

    private final FulfillmentTaskRepository tasks;

    FulfillmentQueryService(FulfillmentTaskRepository tasks) {
        this.tasks = tasks;
    }

    @Override
    @Transactional(readOnly = true)
    public boolean hasTask(UUID orderId) {
        return tasks.existsById(orderId);
    }
}
~~~

Các module khác chỉ cần biết `FulfillmentQueries`, không cần import JPA repository dưới `fulfillment.internal`. Test integration cũng nên sử dụng public API khi quan sát kết quả liên module.

## 9. Test publication bằng @ApplicationModuleTest và PublishedEvents

Bài test đặt trong package module `orders`:

**`src/test/java/com/example/shop/orders/OrderPublicationTest.java`**

~~~java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.UUID;

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
class OrderPublicationTest {

    @Autowired
    OrderCommands orders;

    @Test
    void publishes_correct_order_placed_event(
            PublishedEvents events) {
        UUID orderId = orders.place("CUS-PUB");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId())
                                .isEqualTo(orderId));
    }

    @Test
    void invalid_input_does_not_publish(
            PublishedEvents events) {
        assertThatThrownBy(() -> orders.place(" "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderPlaced.class)).isEmpty();
    }
}
~~~

`PublishedEvents` quan sát event producer đã publish trong test. Đây là **producer contract test**.

**Nó chứng minh:**

- Service producer được khởi tạo theo Spring module test.
- Lệnh tạo order hợp lệ publish một `OrderPlaced` có `orderId` tương ứng.
- Đầu vào không hợp lệ bị từ chối trước khi publish theo code ví dụ.

**Nó không chứng minh:**

- `fulfillment` listener đã được bootstrap và chạy.
- Transaction T1 commit ở thời điểm event được quan sát.
- Task consumer đã được lưu.
- Event được giữ bền và replay sau restart.
- Chỉ đúng **một** event được publish.

`anySatisfy(...)` chỉ kiểm tra **ít nhất một event khớp**. Nếu hợp đồng là exactly one event per order, bổ sung assertion cardinality theo API `PublishedEvents` phiên bản đang dùng.

### Negative control cho producer

Trong nhánh thực hành, tạm bỏ dòng `publisher.publishEvent(...)` rồi chạy test trên. Test phải đỏ, sau đó khôi phục. Điều này chứng minh test không chỉ đang kiểm tra kết quả ID do service trả về.

## 10. Test execution bằng integration test và Awaitility

Để chứng minh side effect consumer, cần nạp cả hai module và dùng transaction/database thật.

**`src/test/java/com/example/shop/OrdersFulfillmentIntegrationTest.java`**

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

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:orders-fulfillment;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrdersFulfillmentIntegrationTest {

    @Autowired
    OrderCommands orders;

    @Autowired
    FulfillmentQueries fulfillment;

    @Test
    void creates_task_after_producer_commit() {
        UUID orderId = orders.place("CUS-CONSUMER");

        await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() ->
                        assertThat(fulfillment.hasTask(orderId))
                                .isTrue());
    }
}
~~~

### Vì sao test này có phạm vi bằng chứng lớn hơn?

- Lệnh gọi qua **bean producer thật**.
- Producer T1 tự commit ở ranh giới proxy.
- `@ApplicationModuleListener` thuộc consumer được Spring đăng ký.
- Consumer có repository và transaction riêng.
- Awaitility chờ **state đã có thể đọc** qua API module consumer.
- Assertion dùng đúng `orderId`, không đọc task cũ từ test khác.

Nếu publisher vẫn phát event nhưng listener bị bỏ annotation, test `OrderPublicationTest` có thể xanh; bài test consumer trên sẽ timeout. Đây là ví dụ trực tiếp cho thấy hai loại test chứng minh **hai mệnh đề khác nhau**.

### Tại sao không dùng @Transactional trên test?

Với integration test gọi service trực tiếp, nếu test method có `@Transactional`, `orders.place(...)` với propagation mặc định có thể tham gia transaction của test. Spring Test thường rollback transaction này sau test; listener `AFTER_COMMIT` khi ấy không chạy. Vì vậy test trên **không gắn `@Transactional`** để lời gọi service commit thật.

Nếu test gửi HTTP tới embedded server, transaction của server khác transaction ở client test. Phải hiểu ranh giới trước khi chọn rollback/cleanup.

### Vì sao không dùng Thread.sleep?

`Thread.sleep(1000)` đợi thời gian cố định, không quan sát điều kiện. Nó có thể quá dài ở máy nhanh và quá ngắn ở CI. Awaitility với deadline 10 giây sẽ thành công khi task xuất hiện và thất bại nếu không đạt, cho tín hiệu trực tiếp hơn.

## 11. Kiểm chứng listener đã bắt đầu nhưng chưa hoàn tất

Một test chỉ verify callback invocation có thể xanh trong khi transaction T2 chưa commit. Có thể chứng minh bằng test điều khiển trình tự thực thi.

### Tách port tạo task

Refactor listener để gọi một port nội bộ:

~~~java
// Minh họa refactor riêng; thay thế trực tiếp listener ở mục 8.
interface TaskCreator {
    void createTask(UUID orderId);
}

@Component
class OrderPlacedListener {

    private final TaskCreator creator;

    OrderPlacedListener(TaskCreator creator) {
        this.creator = creator;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        creator.createTask(event.orderId());
    }
}
~~~

Implementation production thực hiện việc ghi database. Test-only wrapper có thể dùng hai `CountDownLatch`:

- `entered`: báo listener đã đi tới port.
- `release`: giữ listener lại trước khi ghi side effect, chỉ mở khi test cho phép.

### Pseudocode của thí nghiệm

~~~java
// Pseudocode: test fixture gate có các method bên dưới;
// không copy trực tiếp nếu chưa cài test port và delegate.
gate.pauseNextCall();

UUID id = orders.place("CUS-CONTROLLED");
gate.awaitEntered();

assertThat(fulfillment.hasTask(id)).isFalse();
// Callback đã bắt đầu, nhưng side effect chưa được commit.

gate.release();

await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(fulfillment.hasTask(id)).isTrue());
~~~

Khi triển khai, **luôn giải phóng latch trong `finally`** để không làm kẹt executor nếu assertion thất bại. Fixture phải chuyển tiếp tới implementation persistence thật sau khi được release.

**Bài học:** “listener invoked” và “task committed” là hai sự thật có thể quan sát ở **hai thời điểm khác nhau**. Nếu business completion đòi task đã tồn tại, assert callback invocation là quá sớm.

## 12. Rollback sau publication: lỗi suy luận phổ biến

Một transaction có thể phát event rồi rollback:

~~~text
BEGIN T1
    INSERT order
    publish OrderPlaced
    xảy ra lỗi
ROLLBACK T1
~~~

Trong trường hợp listener `AFTER_COMMIT`, consumer không nên tạo task cho order chưa commit. Nhưng `PublishedEvents` có thể đã quan sát event trước rollback — hoàn toàn nhất quán với ý nghĩa của collection này.

### Tạo rollback có chủ đích

Ví dụ trích đoạn trong integration test:

~~~java
@Autowired
TransactionTemplate transactions;

@Test
void rollback_after_publication() {
    UUID id = transactions.execute(status -> {
        UUID created = orders.place("CUS-ROLLBACK");
        status.setRollbackOnly();
        return created;
    });

    assertThat(id).isNotNull();

    // Cần bổ sung public query API hoặc fixture thích hợp
    // để chứng minh row orders đã rollback.
}
~~~

Lưu ý: Đây là **trích đoạn tạo rollback**, chưa phải bài test hoàn chỉnh chứng minh absence của listener side effect. Test hoàn chỉnh cần:

1. Xác nhận producer database **không còn row order** sau rollback.
2. Xác minh listener đang dùng `AFTER_COMMIT` và không bật fallback ngoài transaction nếu không chủ định.
3. Quan sát theo cơ chế có đồng bộ hoặc publication state đủ nghĩa.
4. Không kết luận “sẽ không xảy ra về sau” từ một assertion âm tức thời.

### Assertion âm yếu

~~~java
// Không chứng minh listener sẽ không chạy về sau:
assertThat(fulfillment.hasTask(id)).isFalse();
~~~

Một tác vụ bất đồng bộ sai có thể chưa thực thi lúc assertion chạy và chỉ tạo row sau đó. Test âm đáng tin cần thiết kế vòng đời/pha transaction, theo dõi trạng thái hoặc kiểm soát tác vụ để tránh false positive.

## 13. Listener failure: producer đã trả ID nhưng consumer thất bại

Trong event processing bất đồng bộ, exception của consumer có thể xảy ra **sau** response producer. Vì vậy:

- Producer commit thành công không đồng nghĩa T2 thành công.
- Một listener exception không nhất thiết được truyền về request ban đầu.
- Có thể cần logging, alerting, pending publication và cơ chế retry/resubmission.
- Business status phải phản ánh việc consumer vẫn chưa hoàn tất nếu nó là bước bắt buộc.

~~~mermaid
flowchart TD
    A["Producer commit"] --> B["Listener bắt đầu"]
    B --> C{"Consumer thành công?"}
    C -- "Có" --> D["T2 commit"]
    D --> E["Task quan sát được"]
    C -- "Không" --> F["T2 rollback / error"]
    F --> G{"Có recovery mechanism?"}
    G -- "Có" --> H["Pending / retry / resubmit"]
    G -- "Không" --> I["Cần xử lý lỗi riêng"]
~~~

**Quan trọng:** Sơ đồ nói về các hướng xử lý khả dĩ, không cam kết Spring tự retry vô hạn. Hành vi retry phụ thuộc event publication registry, adapter, version, resubmission policy và cách cấu hình lỗi.

### Test failure injection

Một reliability test tốt có thể:

1. Cho dependency của consumer ném exception ở lần gọi đầu.
2. Tạo order và commit T1.
3. Xác nhận order vẫn tồn tại.
4. Xác nhận consumer chưa commit task sai; failure được ghi nhận.
5. Khi có registry hỗ trợ, kiểm tra publication ở trạng thái đang chờ theo semantics adapter.
6. Bỏ lỗi và resubmit theo cơ chế cấu hình; chờ task cuối cùng xuất hiện.
7. Xác minh idempotency và publication completion phù hợp.

**Không mock chính listener rồi verify một lời gọi** để tuyên bố đã kiểm tra rollback, retry hoặc durable delivery. Mock có ích cho logic rất hẹp, nhưng không chạy transaction/event infrastructure thật.

## 14. Event Publication Registry khác business completion

Spring Modulith có cơ chế **Event Publication Registry** và các adapter lưu trữ cho việc theo dõi event publications đối với listener phù hợp. Phải phân biệt:

| Bằng chứng | Thuộc tầng | Điều được chứng minh |
| --- | --- | --- |
| `PublishedEvents` chứa event | Producer test | Producer đã publish event |
| Publication được ghi nhận | Registry, nếu có | Có record theo dõi publication |
| Publication được đánh dấu completed | Registry | Đường xử lý listener hoàn tất theo semantics của registry |
| Task fulfillment tồn tại sau commit | Consumer/database | Bước tạo task được thực hiện thành công |
| External job trả receipt terminal | Dịch vụ ngoài | Bước nghiệp vụ ngoài đã hoàn thành |

### Registry completed nhưng external job chưa xong

~~~text
Listener nhận OrderPlaced
   -> POST create-label tới shipping provider
   -> provider trả 202 Accepted + jobId
   -> listener lưu jobId, kết thúc
   -> registry có thể đánh dấu listener xử lý xong
   -> external job còn chạy
   -> callback label-ready đến sau
   -> nghiệp vụ "label ready" mới hoàn thành
~~~

Nếu completion criterion là **label ready**, test phải quan sát callback/receipt hoặc trạng thái nghiệp vụ cuối, chứ không chỉ registry completed.

**Không được giả định:** Cài `@ApplicationModuleListener` là tự động có storage bền qua restart, resubmission vô hạn, exactly-once delivery hoặc quy tắc retention nhất định. Cần kiểm tra dependency/adapter và chính sách vận hành cụ thể.

## 15. Retry, duplicate delivery và idempotency

Một event có thể được xử lý lại do retry, replay hoặc concurrency. Handler mẫu ở mục 8 sử dụng:

~~~java
if (!tasks.existsById(event.orderId())) {
    tasks.save(new FulfillmentTask(event.orderId()));
}
~~~

Đây là cách minh họa happy path, **không đủ bảo đảm idempotency an toàn khi concurrent delivery**.

~~~text
Listener A: existsById(42) -> false
Listener B: existsById(42) -> false
Listener A: INSERT(42) -> commit
Listener B: INSERT(42) -> unique constraint violation
~~~

Primary key ngăn hai row trùng, nhưng listener B có thể lỗi và tiếp tục bị retry. **“Sau cùng chỉ có một row” chưa chứng minh handler xử lý duplicate sạch lỗi.**

| Rủi ro | Test nên có | Oracle |
| --- | --- | --- |
| Giao lại tuần tự | Consumer integration | Một task; xử lý lại không có lỗi không kiểm soát |
| Giao trùng đồng thời | Concurrency + database thật | Không nhân đôi business effect; retry state hợp lệ |
| Consumer lỗi giữa chừng | Failure/retry integration | Không lặp side effect đã commit |
| Event cũ đến muộn | Ordering/version test | State mới không bị ghi đè sai |
| Restart trước khi xử lý | Persistent registry recovery | Publication pending có thể được phục hồi nếu đã cam kết |
| Client retry thao tác tạo order | API idempotency test | Cùng idempotency key không tạo hai đơn |

Thiết kế có thể dùng unique constraint, upsert, duplicate-key recovery, event ID/version và deduplication table. Lựa chọn phải xét database và hợp đồng. “Exactly-once **business effect**” thường đòi idempotency tại nơi ghi side effect, không suy ra trực tiếp từ event delivery.

## 16. Correlation ID và dấu hiệu hoàn thành đáng tin

Một test yếu có thể chỉ assert rằng **có task bất kỳ**:

~~~java
// Sai: có thể là task từ test trước.
assertThat(fulfillment.countTasks()).isGreaterThan(0);
~~~

Một test đúng mục tiêu:

~~~java
UUID orderId = orders.place("CUS-" + UUID.randomUUID());

await().untilAsserted(() ->
        assertThat(fulfillment.hasTask(orderId)).isTrue());
~~~

Quy tắc cần nhớ:

- Query theo đúng `orderId` vừa được tạo.
- Dùng fixture/test data độc lập cho các lượt chạy.
- Nếu workflow nhiều bước, công bố `workflowId` hoặc `correlationId` để liên kết logs/traces/event.
- Không giả định ID đầu tiên bằng 1 hoặc database luôn rỗng.
- Phân biệt correlation ID (truy vết) và idempotency key (chống xử lý lại lệnh tạo).
- Kiểm soát test song song, datasource và transaction isolation.

Có thể instrument log theo dạng:

~~~text
orderId=...
producerCommitted=true
eventType=OrderPlaced
listenerStarted=true
consumerCommitted=false
publicationState=PENDING
lastFailure=...
elapsedWaitMs=...
~~~

Đây là mẫu **log do ứng dụng tự bổ sung**, không phải những field Spring Modulith tự ghi sẵn nguyên dạng. Không log thông tin nhạy cảm không cần thiết.

## 17. Chọn test type theo bằng chứng muốn thu

| Mệnh đề | Test phù hợp | Assertion | Điều chưa chứng minh |
| --- | --- | --- | --- |
| Producer chọn đúng event theo nghiệp vụ | Unit test | Event factory/decision | Event infrastructure |
| Producer thực publish `OrderPlaced` | `@ApplicationModuleTest` + `PublishedEvents` | Type, payload | Consumer execution |
| Consumer chạy sau commit | Integration với transaction và listener | Side effect sau commit | Durable restart |
| Task thật sự đã lưu | Integration DB + Awaitility | Public query đọc task | External shipping job |
| Event trùng không nhân side effect | Concurrency/reliability | Unique effect và failure handling | Mọi lỗi production |
| Publication được phục hồi qua restart | Durable registry/recovery test | Pending → recovered | Broker ngoài nếu chưa test |
| HTTP client thấy kết quả | `@SpringBootTest(RANDOM_PORT)` | Response + eventual state | Browser hoặc dịch vụ ngoài |
| Module dependency hợp lệ | `ApplicationModules.verify()` | Không có vi phạm API/vòng | Behavior của listener |
| PostgreSQL constraint đúng | Testcontainers với PostgreSQL | Transaction/unique constraint thật | External provider |

Spring Modulith còn có tiện ích `Scenario` hỗ trợ một số kịch bản kiểm thử sự kiện trong module test. Hãy dùng đúng API theo phiên bản đang dùng và **lựa chọn điều kiện chờ tương ứng với mệnh đề**. Chờ thấy một event không tự thay cho chờ side effect của consumer đã commit.

## 18. Ranh giới kiến trúc của typed event giữa các module

Runtime event thường chảy từ `orders` sang `fulfillment`, nhưng dependency tĩnh trong Java là `fulfillment → orders` vì listener import kiểu `OrderPlaced`.

Được phép:

~~~java
import com.example.shop.orders.OrderPlaced;
~~~

Không hợp lệ theo ranh giới mặc định:

~~~java
// Consumer không được import JPA implementation của producer.
import com.example.shop.orders.internal.persistence.OrderEntity;
~~~

Bài architecture verification:

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void application_module_dependencies_are_valid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` giúp phát hiện vòng phụ thuộc, tham chiếu ngoài module API và vi phạm whitelist `allowedDependencies` nếu khai báo. Nó **không** kiểm tra listener đã chạy hoặc DB đã commit.

Nếu `fulfillment` chỉ được phép phụ thuộc `orders`, có thể khai báo:

~~~java
@ApplicationModule(allowedDependencies = "orders")
package com.example.shop.fulfillment;

import org.springframework.modulith.ApplicationModule;
~~~

Cập nhật giới hạn này theo kiến trúc được review, không tự mở whitelist chỉ để test xanh. Nếu dùng `@NamedInterface` cho event package riêng, phải cấu hình tên interface và dependency tương ứng.

## 19. Database và Testcontainers: khi transaction semantics thuộc rủi ro

H2 có thể đủ cho bài module/integration minh họa. Nhưng SQL dialect, locking, isolation và unique constraint của PostgreSQL/MySQL có thể khác H2.

Khung Testcontainers:

~~~java
package com.example.shop;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FulfillmentPostgresIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Inject OrderCommands và FulfillmentQueries;
    // dùng cùng oracle consumer như mục 10.
}
~~~

Đây là **khung cấu hình**, cần test method và dependency Spring Boot Testcontainers, Testcontainers Jupiter/PostgreSQL, JDBC driver, container runtime. `@ServiceConnection` hỗ trợ từ Spring Boot 3.1+, kiểm tra version tương thích.

Nếu production dùng Flyway/Liquibase, test quan trọng nên chạy migration thật. Khi test recovery qua restart, storage persistent phải sống qua giai đoạn tắt/bật application.

### Cấu hình dependency minh họa

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.modulith:spring-modulith-starter-core")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
    testRuntimeOnly("com.h2database:h2")

    // Khi cần:
    // testImplementation("org.awaitility:awaitility")
    // testImplementation("org.springframework.boot:spring-boot-testcontainers")
    // testImplementation("org.testcontainers:junit-jupiter")
    // testImplementation("org.testcontainers:postgresql")
    // runtimeOnly("org.postgresql:postgresql")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đây là đoạn dependencies minh họa, **chưa phải build script đầy đủ**, và không tự bật adapter Event Publication Registry bền vững.

## 20. Troubleshooting: event có nhưng consumer không thành công

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `PublishedEvents` có event, không có task | Consumer không bootstrap/không đăng ký | Kiểm tra context và listener annotation |
| Consumer chạy trước T1 commit | `@Async @EventListener` không có AFTER_COMMIT | Xem transaction phase |
| Test `@Transactional` không kích hoạt listener | Test rollback, không có commit | Để transaction producer commit thật |
| Listener được gọi, task không thấy | T2 rollback, SQL lỗi, query sai ID | Kiểm tra exception, DB và correlation |
| Plain listener làm producer fail | Lỗi được phát sinh qua dispatch đồng bộ | Kiểm tra multicaster/error handling |
| Async listener lỗi nhưng HTTP vẫn trả thành công | Lỗi không truyền lại request producer | Quan sát log/registry/business state |
| Transactional listener không chạy khi publish ngoài T1 | Không có transaction để attach | Xem fallback hoặc tạo transaction |
| Registry completed, external job còn chạy | Listener chỉ enqueue | Theo dõi receipt terminal |
| Event duplicate làm listener lỗi | Unique conflict không được xử lý | Upsert/duplicate recovery |
| Awaitility timeout ngẫu nhiên | Executor, DB hoặc shared fixture | Chờ điều kiện theo đúng ID, log chi tiết |
| H2 xanh, PostgreSQL lỗi | Dialect/isolation/constraint khác | Testcontainers production-like |
| Integration xanh nhưng architecture đỏ | Import vượt package API | Sửa dependency, giữ `verify()` |

Khi test timeout, đừng chỉ tăng `atMost`. Cần xác nhận T1 commit, event đã publish, listener đăng ký/chạy, T2 commit và query đúng ID; nếu có registry thì kiểm tra pending/completed theo semantics của adapter.

## 21. Quality gate CI theo từng ranh giới bằng chứng

~~~mermaid
flowchart LR
    PR["Pull request"] --> A["Unit + architecture"]
    A --> P["Publisher module tests"]
    P --> C["After-commit consumer integration"]
    C --> R["Retry / idempotency / recovery"]
    R --> E["Critical HTTP E2E"]
    E --> G{"Các gate bắt buộc xanh?"}
    G -- "Có" --> M["Merge/release"]
    G -- "Không" --> F["Điều tra và sửa"]
~~~

| Gate | Bằng chứng | Khi nào chạy |
| --- | --- | --- |
| Unit | Quy tắc quyết định publish và validation | Mọi PR |
| `ApplicationModules.verify()` | Dependency/package hợp lệ | Mọi PR, bắt buộc |
| `@ApplicationModuleTest` + `PublishedEvents` | Producer phát đúng event/payload | Mọi PR có ảnh hưởng event |
| Consumer integration | Listener hậu commit tạo side effect thật | Các luồng nghiệp vụ trọng yếu |
| Reliability/registry | Retry, duplicate, durable recovery | Khi hệ thống cam kết tính tin cậy |
| PostgreSQL/Testcontainers | Transaction/constraint như production | Khi database semantics quan trọng |
| HTTP E2E | Client quan sát luồng qua entry point | Chọn hành trình thiết yếu |

Tách job nhanh và job hạ tầng có thể giảm thời gian phản hồi, nhưng test bắt buộc phải thực sự được chạy trước merge/release theo chính sách. Không dùng producer test xanh để bỏ qua consumer integration test.

### Tiêu chí kết luận “đã được kiểm thử”

Một báo cáo CI tốt nêu rõ: **event nào được publish**, **listener nào được kích hoạt**, **side effect nào được quan sát sau commit**, **ID nào được đối chiếu**, **failure mode nào được thử**, và **những điều chưa được chứng minh**. Đừng chỉ báo “async test passed” khi assertion mới kiểm tra một callback.

## 22. Bài thực hành

### Bài A — Phân biệt các mốc

Sắp xếp và mô tả mối liên hệ giữa producer publish, dispatch, T1 commit, listener invocation, T2 commit và business completion. Với từng mốc, cho biết assertion hoặc nguồn dữ liệu quan sát được.

### Bài B — So sánh annotation

Đổi `@ApplicationModuleListener` thành `@EventListener` đồng bộ, rồi `@Async @EventListener` trong nhánh thực hành. Phân tích thứ tự thực thi và khả năng listener chạy trước commit. Khôi phục cơ chế đáp ứng yêu cầu nghiệp vụ.

### Bài C — Negative control cho publisher

Tạm bỏ `publisher.publishEvent(...)` rồi chạy `OrderPublicationTest`. Test phải đỏ. Khôi phục, thử đổi event payload thành sai ID và xác nhận assertion phát hiện.

### Bài D — Negative control cho consumer

Tạm bỏ `@ApplicationModuleListener` hoặc gây lỗi trong listener. Producer test với `PublishedEvents` có thể vẫn xanh, nhưng `OrdersFulfillmentIntegrationTest` phải không quan sát được task thành công. Giải thích vì sao không mâu thuẫn.

### Bài E — Chặn callback có kiểm soát

Dùng hai latch hoặc một controlled port như mục 11. Xác nhận callback đã bắt đầu trong khi side effect chưa commit; release và chờ task xuất hiện. Không dùng `Thread.sleep` đoán trước và luôn release trong `finally`.

### Bài F — Rollback sau publish

Dùng `TransactionTemplate` để tạo T1, phát event và rollback. Xác nhận row producer không commit; sau đó thiết kế bằng chứng listener AFTER_COMMIT không xử lý side effect sai. Giải thích vì sao một assertion âm ngay lập tức chưa đủ.

### Bài G — Giao lại và recovery

Cho cùng `OrderPlaced` được xử lý hai lần tuần tự rồi đồng thời, test không có side effect trùng và handler không retry vô hạn vì unique violation. Nếu có persistent registry, giả lập consumer failure và thử resubmit/restart theo adapter.

### Bài H — Bảo vệ public event API

Chạy `ApplicationModules.verify()`. Cố ý import `orders.internal.persistence.OrderEntity` từ `fulfillment`, xác nhận architecture test đỏ; sửa thành chỉ dùng `orders.OrderPlaced`.

### Câu hỏi tự đánh giá

1. `publishEvent(...)` trả về có luôn nghĩa listener đã hoàn tất không?
2. Vì sao với `@EventListener` đồng bộ, callback có thể chạy trước khi `publishEvent(...)` trả về?
3. `@Async` có bảo đảm listener chờ T1 commit không?
4. `@TransactionalEventListener(AFTER_COMMIT)` có tự tạo transaction ghi DB mới không?
5. `@ApplicationModuleListener` có tự bảo đảm event sống qua restart hoặc exactly-once delivery không?
6. `PublishedEvents` và integration test phía consumer trả lời hai câu hỏi gì?
7. Vì sao listener invoked không phải consumer committed?
8. Vì sao registry completed không nhất thiết là external job completed?
9. Unique constraint có tự làm handler an toàn trước duplicate delivery đồng thời không?
10. Tại sao architecture test vẫn cần dù integration test xanh?

## 23. Checklist trước khi kết luận listener đã xử lý xong

- [ ] Đã xác định mệnh đề là published, invoked, committed hay business completed.
- [ ] Biết rõ loại listener, transaction phase và thread/executor được dùng.
- [ ] Producer publication test chỉ được dùng làm bằng chứng publish.
- [ ] Consumer integration test chạy listener thật và quan sát state sau commit.
- [ ] Assertion dùng đúng correlation ID của lần chạy.
- [ ] Test hậu commit không bị transaction rollback mặc định của test bao ngoài.
- [ ] Test async chờ điều kiện có timeout, không dựa vào `Thread.sleep` cố định.
- [ ] Có negative control cho quên publish và listener bị bỏ đăng ký.
- [ ] Rollback và listener failure được kiểm tra ở đúng pha.
- [ ] Idempotency/retry được kiểm tra nếu event có thể được giao lại.
- [ ] Durable publication chỉ kết luận khi adapter/storage/restart đã được test.
- [ ] Registry completion và business completion không bị đánh đồng.
- [ ] Public event API và allowed dependency được bảo vệ bằng `ApplicationModules.verify()`.
- [ ] Các test quan trọng có trong CI và không bị skip.

## 24. Ghi nhớ

**Event publication** là producer công bố một tín hiệu; **listener execution** là consumer được kích hoạt để xử lý tín hiệu đó. Listener đồng bộ có thể chạy ngay trong lời gọi publish; listener bất đồng bộ thường chạy sau đó; listener hậu commit phụ thuộc trạng thái transaction. **Không tín hiệu publish, scheduling hay callback started nào tự chứng minh side effect consumer đã commit.**

Với Spring Modulith, dùng `@ApplicationModuleTest` + `PublishedEvents` để xác minh producer, integration test với `@ApplicationModuleListener`, Awaitility và database để xác minh consumer, và test reliability khi cần retry, duplicate hoặc phục hồi qua restart. Kết hợp `ApplicationModules.verify()` cùng quality gate CI để bảo vệ **cả hành vi sự kiện lẫn ranh giới kiến trúc module**.
