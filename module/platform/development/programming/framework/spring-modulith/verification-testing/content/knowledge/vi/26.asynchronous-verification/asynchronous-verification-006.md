# Không để test kết thúc trước tác vụ nền

> **Chương:** Async verification  
> **Module học:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Kiểm chứng ứng dụng Spring Modulith có ranh giới module đúng, xử lý event sau commit đúng và **không để JUnit báo PASS trước khi tác vụ nền bắt buộc hoàn tất**. Thực hành `@ApplicationModuleTest`, `PublishedEvents`, `@ApplicationModuleListener`, JPA, Awaitility, Testcontainers và quality gate CI.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **test method trả về**, **producer publish event**, **transaction producer commit**, **listener bắt đầu**, **consumer commit** và **workflow hoàn tất**.
2. Giải thích vì sao `@Test` kết thúc mà không đợi worker có thể tạo **xanh giả (false positive)**.
3. Chọn **completion barrier** phù hợp: Awaitility trên business state, `Future` thực sự đại diện kết quả, hoặc primitive đồng bộ có kiểm soát.
4. Viết integration test chạy `@ApplicationModuleListener` thật và chỉ pass khi side effect có thể đọc được sau commit.
5. Không nhầm `PublishedEvents`, mock verification, log `listener started` hoặc `Thread.sleep(...)` với bằng chứng listener thành công.
6. Xử lý lifecycle `@AfterEach`, `@DirtiesContext`, async executor, transaction test và Testcontainers để không phá công việc đang chạy.
7. Phân biệt timeout quan sát, lỗi terminal, retry, duplicate delivery và nhiều nhánh nền phải cùng hoàn thành.
8. Kết hợp architectural verification `ApplicationModules.verify()` cùng các test chức năng trong quality gate CI.

**Câu hỏi trọng tâm:** Khi `orders.place(...)` trả về `orderId` nhưng listener `fulfillment` chạy nền, test được phép return ngay không?

**Không**, nếu điều test tuyên bố kiểm tra là *fulfillment task đã được tạo*. Nó chỉ được return sau khi có bằng chứng **task của đúng order đã commit và có thể quan sát** hoặc một outcome terminal khác được hợp đồng công nhận.

## 2. Vì sao test có thể xanh trước khi worker hoàn thành?

Một bài test sai mục tiêu:

~~~java
@Test
void creates_order_and_fulfillment() {
    UUID orderId = orders.place("CUS-001");

    assertThat(orderId).isNotNull();
    // JUnit kết thúc, dù background listener có thể chưa chạy.
}
~~~

Producer có thể publish event trong transaction T1. Spring Modulith `@ApplicationModuleListener` trong cấu hình thông dụng xử lý **sau commit**, **bất đồng bộ** và với **transaction mới**. Nó không nhất thiết chạy xong trước khi test nhận `orderId`.

~~~mermaid
sequenceDiagram
    participant T as JUnit test thread
    participant O as orders
    participant D1 as Orders DB
    participant E as Event delivery
    participant L as fulfillment listener
    participant D2 as Fulfillment DB

    T->>O: place(customerId)
    O->>D1: INSERT order trong T1
    O->>E: publish OrderPlaced
    O->>D1: COMMIT T1
    O-->>T: orderId
    T-->>T: Assert orderId, return, PASS
    Note over T,L: Worker vẫn có thể đang chờ executor
    E-->>L: Listener bắt đầu
    L->>D2: Ghi task trong T2
    L->>D2: COMMIT hoặc ROLLBACK T2
~~~

Test đầu có thể xanh dù:

- Listener bị bỏ annotation nên không đăng ký.
- Executor chưa chạy, bị tắc queue hoặc task bị reject.
- Listener ném exception sau khi test method return.
- Repository `save` được gọi nhưng T2 rollback.
- Task được ghi sai `orderId`.
- Test teardown xóa dữ liệu trước khi listener xử lý.
- Listener xử lý trùng và gây lỗi retry sau khi task đầu tiên đã có.

**Ý nghĩa chính xác:** JUnit chỉ kiểm tra exception và assertion thuộc đường thực thi nó quan sát. Không có cơ chế nào mặc định biến mọi tác vụ bất đồng bộ liên quan thành một phần của pass/fail.

## 3. Đừng nhầm các mốc hoàn thành

| Mốc | Tín hiệu thường quan sát | Có thể kết luận | Chưa được kết luận |
| --- | --- | --- | --- |
| **A — Producer returned** | `orders.place(...)` trả ID | Producer trả kết quả đồng bộ | Consumer đã chạy |
| **B — Event published** | `PublishedEvents` chứa `OrderPlaced` | Producer công bố tín hiệu | T1 đã commit, T2 đã xong |
| **C — Listener invoked** | Callback/log/latch tại đầu handler | Consumer bắt đầu xử lý | Side effect đã commit |
| **D — Consumer commit** | Query mới đọc thấy row/task | T2 có kết quả lưu theo oracle | External job đã xong |
| **E — Business terminal** | State `READY`, `FAILED` hoặc receipt theo contract | Công đoạn nghiệp vụ đã kết thúc | Các bước ngoài công đoạn |

**Điều kiện pass phải tương ứng mốc muốn chứng minh.** Test publisher chỉ kiểm tra B; test tạo task phải quan sát D; test giao kiện ngoài có thể phải đợi E.

### Một event có thể kích hoạt nhiều tác vụ

~~~text
OrderPlaced(orderId)
  ├── fulfillment: tạo picking task
  ├── billing: tạo payment reservation
  └── notifications: gửi email
~~~

Nếu contract là “task fulfillment có sẵn”, không nhất thiết chờ billing hay email. Nếu contract là “order ready to ship” và đòi cả picking task lẫn payment reservation, **chỉ một nhánh READY không đủ**.

## 4. Completion barrier: điểm ngăn test return quá sớm

Một **completion barrier** là điều kiện hoặc synchronization point mà sau đó test có đủ bằng chứng để kết luận tác vụ cần kiểm chứng đã hoàn thành.

| Barrier | Phù hợp khi | Giới hạn |
| --- | --- | --- |
| Awaitility trên public query API | Event-driven consumer có side effect truy vấn được | Phải chọn predicate đúng nghiệp vụ |
| `Future.get(timeout)` hoặc `CompletionStage` | Test sở hữu future của **toàn bộ** operation | Future chỉ đại diện enqueue thì quá yếu |
| `CountDownLatch.await` | Test fixture điều khiển mốc code | Latch ở đầu listener chỉ chứng minh started |
| Spring Modulith `Scenario` | Module test cần chờ event/state theo API phiên bản | Chờ event không mặc định chứng minh side effect |
| Poll HTTP status/receipt | Kiểm tra hành trình client | Phải phân biệt `202 Accepted` và terminal state |
| Event Publication Registry | Kiểm tra publication tracking/recovery | Registry completed chưa chắc external job DONE |
| `Thread.sleep(...)` | Tạo delay có chủ đích trong fake | Không phải completion barrier đáng tin |

**Nguyên tắc:** Chỉ gọi là “complete” khi barrier được đặt **sau side effect bắt buộc** hoặc quan sát trạng thái cuối từ nguồn đáng tin. Gọi `latch.countDown()` ngay khi method listener bắt đầu không đủ.

## 5. Những phản mẫu khiến test kết thúc sai

### 5.1. Chỉ chờ một khoảng cố định

~~~java
UUID orderId = orders.place("CUS-SLEEP");
Thread.sleep(2_000);
assertThat(fulfillment.hasTask(orderId)).isTrue();
~~~

Nếu consumer chạy xong sau 40 ms, test vẫn mất hai giây. Nếu CI có độ trễ 2.300 ms, test fail dù workflow có thể hợp lệ. Nếu consumer lỗi, test chỉ báo row chưa xuất hiện, khó phân biệt nguyên nhân.

### 5.2. Verify listener được gọi

~~~java
// Ví dụ mock/spy; chỉ kiểm tra callback invocation.
verify(listener, timeout(2_000)).on(any(OrderPlaced.class));
~~~

Assertion có thể đạt **trước khi transaction T2 commit**. Handler ném exception ở cuối hoặc JPA flush thất bại thì test vẫn có thể xanh. Dùng spy cho chẩn đoán control flow, không làm business oracle.

### 5.3. Chỉ kiểm tra event được publish

~~~java
assertThat(events.ofType(OrderPlaced.class))
        .anySatisfy(event ->
                assertThat(event.orderId()).isEqualTo(orderId));
~~~

`PublishedEvents` kiểm tra producer phát event, không chứng minh consumer tồn tại hoặc đã commit.

### 5.4. Chỉ chờ một row bất kỳ

~~~java
// Có thể lấy row từ test chạy trước.
await().until(() -> fulfillment.countAllTasks() > 0);
~~~

Phải chờ kết quả **đúng `orderId`** của lần thử, không dựa vào database rỗng hay ID cố định.

## 6. Case study: orders → fulfillment trong Spring Modulith

Ví dụ tự chứa có hai application module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/                                  # Application module producer
│   ├── OrderCommands.java                   # Public API
│   ├── OrderPlaced.java                     # Public event
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/                             # Application module consumer
    ├── FulfillmentQueries.java              # Public query API
    ├── PreparationState.java                # Public trạng thái
    └── internal/
        ├── OrderPlacedListener.java
        ├── FulfillmentQueryService.java
        └── persistence/
            ├── FulfillmentTask.java
            └── FulfillmentTaskRepository.java
~~~

Theo quy tắc phát hiện module mặc định, `orders` và `fulfillment` là application module trực tiếp dưới `com.example.shop`. Public API mặc định nằm ở package root; `internal` thuộc implementation riêng.

**Completion criterion của ví dụ:** Tạo order được chấp nhận khi service trả ID và T1 commit; **chuẩn bị fulfillment hoàn thành** khi module `fulfillment` tạo một task có `orderId` tương ứng, T2 commit và public API trả `READY`.

`NOT_OBSERVED` chỉ có nghĩa chưa đọc thấy task tại thời điểm truy vấn. Nó không đủ phân biệt đang xử lý, lỗi hoặc order ID không tồn tại; production nên có workflow state phong phú hơn khi cần.

## 7. Code producer: event được phát trong transaction

### 7.1. Spring Boot application

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

`@EnableAsync` cho phép async processing thông qua executor. Nó không tự cung cấp durable queue, retry policy hoặc exactly-once effect.

### 7.2. Public API orders

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

Event record chứa ID bất biến; không chuyển JPA entity hoặc repository implementation sang module consumer.

### 7.3. Orders persistence

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
@Table(name = "customer_orders")
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

Ví dụ sử dụng Java 17+, Spring Boot 3.x và JPA hỗ trợ `GenerationType.UUID`. Dự án có thể thay ID strategy phù hợp database thực.

### 7.4. Transactional service và publisher

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
        UUID id = saved.getId();

        publisher.publishEvent(new OrderPlaced(id));
        return id;
    }
}
~~~

`publishEvent` được gọi **bên trong T1**, trong khi transaction proxy xử lý commit ở ranh giới phương thức khi không có transaction bao ngoài. Lời gọi `place(...)` hoàn tất **không bảo đảm** listener consumer đã được schedule hoặc T2 đã commit.

## 8. Code consumer: oracle đọc dữ liệu đã commit

### 8.1. Public query API

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

import java.util.UUID;

public interface FulfillmentQueries {
    PreparationState statusFor(UUID orderId);
}
~~~

### 8.2. JPA persistence

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

### 8.3. Consumer listener

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

`@ApplicationModuleListener` thường kết hợp processing **AFTER_COMMIT**, async và transaction mới theo Spring Modulith version/config phù hợp. Khi listener `on(...)` được gọi, nó mới bắt đầu công việc. `save(...)` trả về cũng không phải bằng chứng final commit: T2 có thể rollback lúc flush/commit.

Code `existsById` rồi `save` minh họa happy path; cần xử lý duplicate concurrent an toàn trong production (xem mục 19).

### 8.4. Query API thuộc consumer

**`src/main/java/com/example/shop/fulfillment/internal/FulfillmentQueryService.java`**

~~~java
package com.example.shop.fulfillment.internal;

import java.util.UUID;
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
    public PreparationState statusFor(UUID orderId) {
        return tasks.existsById(orderId)
                ? PreparationState.READY
                : PreparationState.NOT_OBSERVED;
    }
}
~~~

Mỗi lần test gọi `FulfillmentQueries.statusFor(...)` qua Spring bean, nó thực hiện phép đọc mới theo transaction/isolation phù hợp. Test không phải import JPA repository thuộc `fulfillment.internal`.

## 9. @ApplicationModuleTest: bảo vệ producer publication

Test thuộc package `com.example.shop.orders`:

**`src/test/java/com/example/shop/orders/OrderPublicationTest.java`**

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
        "spring.datasource.url=jdbc:h2:mem:orders-pub;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderPublicationTest {

    @Autowired
    OrderCommands orders;

    @Test
    void publishes_event_with_correct_order_id(
            PublishedEvents events) {
        var orderId = orders.place("CUS-PUBLISH");

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

**Đã chứng minh:** Producer publish event đúng type và order ID; validation rỗng không publish.

**Chưa chứng minh:** Consumer module được bootstrap, listener xử lý thành công, T2 commit, event sống qua restart hay exactly one publication. `anySatisfy` chỉ đòi có **ít nhất một** event phù hợp.

Vì vậy producer-only test **không thay thế** consumer integration test. Không yêu cầu `@ApplicationModuleTest` của `orders` chờ consumer nếu context của test không bootstrap consumer.

## 10. Consumer integration test: bắt buộc chờ side effect

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
        "spring.datasource.url=jdbc:h2:mem:fulfillment-it;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderFulfillmentCompletionTest {

    @Autowired
    OrderCommands orders;

    @Autowired
    FulfillmentQueries fulfillment;

    @Test
    void waits_until_background_listener_commits() {
        var orderId = orders.place(
                "CUS-" + UUID.randomUUID());

        await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() ->
                        assertThat(fulfillment.statusFor(orderId))
                                .isEqualTo(PreparationState.READY));
    }
}
~~~

### Vì sao barrier này phù hợp?

1. Chạy **cả producer và consumer thật** trong Spring context.
2. Producer T1 được service transaction proxy commit khi test không tạo outer transaction.
3. Listener `@ApplicationModuleListener` có thể chạy sau commit theo lịch executor.
4. Assertion quan sát **task của chính order vừa tạo**, không phải task cũ.
5. Public query của consumer nhìn được dữ liệu sau T2 commit.
6. Test có **deadline hữu hạn**, không sleep cố định và có thể pass khi task xuất hiện.

Nếu listener bị bỏ annotation, ghi sai ID, ném exception hoặc rollback, điều kiện không đạt và test sẽ đỏ. Nếu worker hoàn tất nhanh, test không phải đợi hết 10 giây.

### Giới hạn kết luận

Test này chứng minh **một task READY đã được quan sát**, không chứng minh event xử lý đúng một lần, không có publication pending, hoặc nhãn vận chuyển bên ngoài đã hoàn tất.

**Timeout** chỉ nói “chưa quan sát thấy READY trong 10 giây”, không tự nói nguyên nhân là lost event. Cần log/registry/transaction diagnostic để điều tra.

## 11. Không bọc test after-commit trong outer @Transactional

Một lỗi phổ biến:

~~~java
@Transactional
@Test
void incorrectly_waits_for_listener() {
    UUID id = orders.place("CUS-TEST-TX");

    await().atMost(Duration.ofSeconds(5))
            .untilAsserted(() ->
                    assertThat(fulfillment.statusFor(id))
                            .isEqualTo(PreparationState.READY));
}
~~~

Spring Test thường mở transaction cho test rồi rollback khi test kết thúc. Service `orders.place(...)` với propagation `REQUIRED` có thể tham gia transaction đó; event listener pha `AFTER_COMMIT` không có commit để kích hoạt. Test timeout không phải vì worker “quá chậm”, mà vì test không cho T1 commit.

**Cách sửa:** Với consumer after-commit integration test, tránh outer `@Transactional` trên method test, hoặc điều khiển transaction commit có chủ đích nếu thật sự cần. Dọn dữ liệu qua fixture/namespace riêng thay vì dựa vào rollback của test.

### Rollback là một claim test khác

Khi muốn kiểm tra transaction rollback **không kích hoạt side effect**, dùng `TransactionTemplate` tạo rollback có chủ đích và một phép xác minh âm đủ mạnh; không nhầm với happy-path integration test đòi READY.

## 12. Wait theo điều kiện, không theo thời gian ước đoán

Một completion barrier dạng Awaitility cần năm yếu tố:

- **Oracle:** `statusFor(id) == READY`.
- **Correlation:** `id` do chính lần thử tạo.
- **Deadline:** `atMost(10s)`.
- **Poll interval:** Ví dụ `100ms`.
- **Observation boundary:** Query mới có thể đọc state đã commit.

~~~mermaid
flowchart TD
    A["Trigger background work"] --> B["Query state by orderId"]
    B --> C{"READY?"}
    C -- "Có" --> PASS["Test pass"]
    C -- "Chưa" --> D{"Hết deadline?"}
    D -- "Có" --> FAIL["Test fail: chưa thấy READY"]
    D -- "Chưa" --> WAIT["Đợi poll interval"]
    WAIT --> B
~~~

`Thread.sleep(5_000)` không đảm bảo worker sẽ hoàn tất trước đúng giây thứ năm, nhưng **luôn làm test chậm năm giây** nếu task đã xong từ sớm. Awaitility tránh lãng phí đó.

### Không biến wait thành vòng lặp vô hạn

~~~java
// Không dùng:
while (fulfillment.statusFor(orderId)
        != PreparationState.READY) {
    // Không có deadline, có thể treo cả CI.
}
~~~

Mọi phép chờ test phải có **giới hạn**, failure message và một chính sách đối với state terminal lỗi nếu ứng dụng công bố.

## 13. CountDownLatch: listener entered khác listener committed

`CountDownLatch` hữu ích khi cần điều khiển trình tự trong test, nhưng **vị trí đặt latch quyết định ý nghĩa**.

Test-only gateway:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

final class ControlledPreparationGate {

    final CountDownLatch entered = new CountDownLatch(1);
    final CountDownLatch release = new CountDownLatch(1);

    void beforeSave() {
        entered.countDown();

        try {
            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Test did not release worker");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted waiting for gate", e);
        }
    }
}
~~~

Đây là **test fixture**, chưa tự được wire vào listener của mục 8. Để áp dụng, refactor listener gọi một port trước `tasks.save`, rồi cung cấp production implementation no-op và test implementation `ControlledPreparationGate` có ưu tiên injection phù hợp.

### Kiểm chứng hai mốc khác nhau

~~~java
// Pseudocode: cần listener gọi gate.beforeSave()
// và test đã inject đúng gate vào listener.
UUID id = orders.place("CUS-CONTROLLED");

try {
    assertThat(gate.entered.await(5, TimeUnit.SECONDS))
            .isTrue();

    // Worker đã tới gateway nhưng chưa ghi side effect.
    assertThat(fulfillment.statusFor(id))
            .isEqualTo(PreparationState.NOT_OBSERVED);
} finally {
    gate.release.countDown();
}

await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(fulfillment.statusFor(id))
                        .isEqualTo(PreparationState.READY));
~~~

**Chú ý:** `entered` chứng minh callback đã bắt đầu, còn **Awaitility sau release** mới chứng minh task đã commit. Nếu handler sau gateway ném exception, latch vẫn có thể xanh nhưng business oracle không đạt.

**Luôn release trong `finally`** để test failure không khiến worker kẹt, executor không được giải phóng và suite treo.

## 14. Khi test có quyền sở hữu CompletableFuture

Nếu một API được thiết kế trả `CompletionStage`/`CompletableFuture` **đại diện cho công việc đến cuối**, test có thể chờ future có deadline:

~~~java
CompletableFuture<PreparationResult> future =
        preparationService.prepareAsync(orderId);

PreparationResult result =
        future.get(10, TimeUnit.SECONDS);

assertThat(result.status())
        .isEqualTo(PreparationState.READY);
~~~

Code này minh họa **API khác** có future đại diện completion, không phải chữ ký `void @ApplicationModuleListener` ở mục 8.

### Future có thể complete quá sớm

~~~java
CompletableFuture<UUID> accepted =
        CompletableFuture.completedFuture(orderId);

// Future này chỉ hoàn tất vì đã có ID,
// không chứng minh side effect của worker đã commit.
~~~

Để `future.get` làm barrier hợp lệ, future phải chỉ hoàn tất **sau công việc bắt buộc**. Nếu future đại diện enqueue/request accepted, test vẫn return quá sớm.

### Nhiều futures

~~~java
CompletableFuture<Void> both = CompletableFuture.allOf(
        fulfillmentFuture,
        billingFuture
);

both.get(15, TimeUnit.SECONDS);
~~~

Dùng khi test thực sự sở hữu các futures và cần cả hai. Không tạo dependency trực tiếp giữa module chỉ để expose future của listener; với event-driven module, public business state thường phù hợp hơn.

## 15. Chờ tất cả nhánh bắt buộc, không chỉ nhánh nhanh nhất

Giả sử một order cần cả task fulfillment **và** payment reservation để được gọi là ready-to-ship.

~~~java
await()
        .atMost(Duration.ofSeconds(15))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            assertThat(fulfillment.statusFor(orderId))
                    .isEqualTo(PreparationState.READY);

            assertThat(billing.hasReservation(orderId))
                    .isTrue();
        });
~~~

`billing.hasReservation(...)` là **public API minh họa** của module thứ ba, chưa có trong source mẫu. Điều kiện pass yêu cầu **cả hai** thay vì chỉ một.

Nếu các state có thể đảo chiều hoặc thay đổi cạnh tranh, đọc hai API rời rạc không đảm bảo một snapshot nguyên tử. Khi business contract cần kết luận terminal thống nhất, nên có một **workflow status resource do module điều phối sở hữu**, cập nhật sau các bước bắt buộc, rồi assert trên status đó.

**Không dùng event của nhánh không liên quan** làm completion marker. Email queued hoặc analytics projection có thể hoàn tất sớm hơn fulfillment.

## 16. @AfterEach có thể phá tác vụ nền chưa xong

JUnit gọi `@AfterEach` sau khi method test return, không phải sau khi mọi executor tasks trong Spring ApplicationContext hoàn thành.

~~~java
@Test
void bad_test() {
    orders.place("CUS-CLEANUP");
    // Return ngay.
}

@AfterEach
void cleanup() {
    fixture.deleteAllOrders();
    // Worker vẫn có thể cần dữ liệu vừa bị xóa.
}
~~~

Một chuỗi lỗi khó chẩn đoán:

1. Producer commit và publish.
2. Test return, JUnit bắt đầu cleanup.
3. Cleanup xóa source data.
4. Listener chạy muộn và cần đọc dữ liệu source.
5. Listener lỗi trên thread khác; test gốc vẫn xanh.
6. Test tiếp theo bị ảnh hưởng bởi pending publication hoặc dữ liệu không nhất quán.

### Cách làm đúng

- Assert outcome cần thiết **ngay trong test method** trước khi return.
- Với worker do test kiểm soát trực tiếp, quản lý quiescence/cancel/cleanup có deadline.
- Dùng correlation ID và fixture riêng, không xóa cả bảng trong môi trường test song song.
- Không coi teardown exception như business assertion; lỗi nên được gắn với chính test use case.
- Với test cố ý giữ publication pending để kiểm tra recovery, phải thiết kế storage/lifecycle riêng thay vì cleanup bất chấp.

### Tránh chỉ await ở @AfterEach

Nếu mọi test đều đợi trong teardown, lỗi nghiệp vụ có thể hiện thành “cleanup failure” khó hiểu. Nên chờ kết quả trong **test body**, còn teardown chịu trách nhiệm giải phóng tài nguyên an toàn.

## 17. Spring TestContext, @DirtiesContext và shutdown

Spring TestContext thường cache application context để tái sử dụng giữa test classes có cấu hình trùng. Không có quy luật “mỗi `@Test` return là Spring context sẽ đóng ngay”. Tuy nhiên, `@DirtiesContext`, kết thúc suite hoặc shutdown khác có thể đóng context/executor khi worker chưa xong.

~~~text
Test returns
    → @DirtiesContext hoặc cuối suite
    → executor/DataSource/EntityManagerFactory shutdown
    → listener vẫn đang chạy
    → DB connection hoặc bean không còn hợp lệ
    → lỗi có thể xuất hiện sau khi test báo PASS
~~~

**Không dùng `@DirtiesContext` thay completion barrier**. Reset context có thể che một worker bị bỏ dở thay vì kiểm chứng nó.

### Kiểm tra tài nguyên

- Context có bị đánh dấu dirty không?
- Async executor có active tasks hoặc queue pending không?
- DataSource còn sống tới khi worker commit không?
- Testcontainers có dừng sau class trong khi context vẫn được cache không?
- H2 in-memory database có vòng đời tương ứng context không?
- Fixture cleanup có cạnh tranh với listener không?
- Có outer test transaction rollback làm listener AFTER_COMMIT không chạy không?

Giải quyết đúng lifecycle trước khi tăng Awaitility timeout.

## 18. Exception trên worker thread và trạng thái FAILED

Async exception có thể xảy ra **sau** khi producer/test thread đã trả về. Với `void @Async`, lỗi có thể đi vào handler/logging theo cấu hình và không tự ném về caller.

~~~text
Test thread:
  orders.place -> orderId
  assert orderId != null -> PASS
  return

Worker thread:
  on(OrderPlaced) -> SQL exception
  T2 rollback
  error logged / publication state updated (nếu có)
~~~

Để test bảo vệ nghiệp vụ, cần quan sát:

- **Business outcome:** READY hoặc FAILED theo hợp đồng.
- **Listener errors:** Log/metrics/exception recording.
- **Publication state:** Pending, completed, retry khi adapter registry có hỗ trợ.
- **Correlation ID:** `orderId` của đúng lần thử.

### Terminal state và timeout là hai chuyện

| Quan sát | Ý nghĩa | Hành động test |
| --- | --- | --- |
| `READY` | Công đoạn đã hoàn thành | Pass |
| `PROCESSING` | Vẫn đang xử lý | Poll tiếp |
| `RETRY_WAIT` | Retry có thể xảy ra | Chờ đúng policy |
| `FAILED` terminal | Thất bại nghiệp vụ đã được xác nhận | Fail sớm |
| `NOT_OBSERVED` | Chưa có bằng chứng READY | Không suy ra nguyên nhân |
| Awaitility timeout | Không thấy condition đúng trước deadline | Fail, ghi trạng thái cuối |

Nếu hệ thống chỉ có `NOT_OBSERVED` như ví dụ, test không phân biệt worker chưa start với worker đã lỗi. Production thường nên có workflow state/diagnostic phù hợp khi cần vận hành và fail-fast.

**Không ignore tất cả exception của Awaitility** để biến schema mismatch, security error hoặc JPA failure thành “worker chậm”.

## 19. Retry, duplicate và idempotency: chờ task thôi chưa đủ

Handler ví dụ dùng:

~~~java
if (!tasks.existsById(event.orderId())) {
    tasks.save(new FulfillmentTask(event.orderId()));
}
~~~

Hai event trùng xử lý đồng thời có thể:

~~~text
Listener A: existsById(id) = false
Listener B: existsById(id) = false
Listener A: INSERT(id) -> commit
Listener B: INSERT(id) -> unique-constraint violation
~~~

Primary key ngăn hai row, nhưng B có thể fail và tiếp tục bị retry. Test Awaitility thấy task tồn tại từ A có thể xanh trong khi vẫn còn lỗi chưa được xử lý.

### Hai loại mệnh đề cần test riêng

**Completion:** Task cho order đã commit và đọc được.

**Reliability:** Replay/duplicate/failure không nhân đôi side effect, không retry vô hạn, registry state đạt policy.

| Kịch bản | Test phù hợp |
| --- | --- |
| Event một lần | Integration + Awaitility trên task |
| Event trùng tuần tự | Consumer idempotency test |
| Event trùng đồng thời | Concurrency + DB constraint/upsert |
| Consumer fail lần đầu | Failure injection + retry/recovery |
| Event sai thứ tự | Event revision/version test |
| Restart sau failure | Persistent registry/recovery test |

Không gọi việc có một task là “exactly once delivery”. Để có **exactly-once business effect**, cần idempotent design và assertion cho side effect.

## 20. Event Publication Registry: listener done khác business done

Spring Modulith có Event Publication Registry và persistence adapters cho việc theo dõi publications. Khi sử dụng đúng dependency/configuration, một publication có thể được ghi nhận và đánh dấu đã xử lý theo semantics registry.

Nhưng có ít nhất ba loại outcome:

| Outcome | Nó xác nhận |
| --- | --- |
| `PublishedEvents` chứa event | Producer phát event |
| Registry publication completed | Listener xử lý thành công theo cơ chế registry |
| Business state terminal | Công đoạn nghiệp vụ được định nghĩa hoàn tất |

Ví dụ listener gọi external shipping provider:

~~~text
Listener nhận OrderPlaced
   -> POST create-label
   -> provider trả 202 Accepted + jobId
   -> listener lưu jobId và return
   -> registry có thể đánh dấu publication completed
   -> external job vẫn đang chạy
   -> callback LABEL_READY tới sau
   -> business completion mới đạt
~~~

Nếu test cần **nhãn vận chuyển đã tạo xong**, đợi listener return hoặc registry completed vẫn là quá sớm. Phải đợi terminal receipt/state.

Không tự giả định registry có retry vô hạn, adapter lưu trữ bền hay event sống qua restart chỉ vì có `@ApplicationModuleListener`. Đó là **những contract khác** cần test phù hợp.

## 21. Không dùng outer @Transactional khi muốn test AFTER_COMMIT

Tình huống sai:

~~~text
Spring Test mở outer T1
   orders.place -> tham gia T1
   publish OrderPlaced
   test chờ fulfillment READY
   nhưng T1 chưa commit
   listener AFTER_COMMIT chưa chạy
   test timeout
   Spring Test rollback T1
~~~

Nếu cần kiểm tra listener sau commit, cho service transaction commit thực; `OrderFulfillmentCompletionTest` ở mục 10 **không** đặt `@Transactional` trên test.

### Test rollback cố ý là một bài khác

~~~java
@Autowired
TransactionTemplate transactions;

@Test
void producer_can_rollback_after_publication() {
    UUID id = transactions.execute(status -> {
        UUID created = orders.place("CUS-ROLLBACK");
        status.setRollbackOnly();
        return created;
    });

    assertThat(id).isNotNull();

    // Bổ sung phép đọc dữ liệu orders xác nhận rollback.
}
~~~

Đây là **trích đoạn tạo rollback**, không đủ để chứng minh consumer sẽ không bao giờ tạo side effect. Assert `NOT_OBSERVED` một lần ngay sau rollback có thể pass trước một listener cấu hình sai chạy.

Negative test mạnh hơn cần kiểm tra **transaction phase**, absence có giới hạn quan sát và/hoặc controlled event dispatch. Không viết `await().until(() -> !hasTask(id))` để tuyên bố bất khả xảy ra, vì predicate có thể true ngay lập tức.

## 22. HTTP E2E: accepted không phải completed

HTTP có thể trả `202 Accepted` trong khi các worker vẫn chạy. Nếu mục tiêu E2E là client nhìn thấy task đã chuẩn bị, phải poll status resource theo ID.

~~~mermaid
sequenceDiagram
    participant C as Test client
    participant A as Orders API
    participant F as Fulfillment API

    C->>A: POST /api/orders
    A-->>C: 202 + orderId
    loop Cho đến READY hoặc deadline
        C->>F: GET /api/fulfillments/{id}/preparation
        F-->>C: PROCESSING hoặc READY
    end
    Note over C,F: Chỉ READY mới chứng minh completion point
~~~

Khung E2E sau **giả định REST controllers đã được triển khai** (source ở mục 7–8 mới có Java APIs, chưa có controllers):

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

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FulfillmentHttpCompletionTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void waits_for_terminal_business_state() {
        var accepted = http.postForEntity(
                "/api/orders",
                Map.of("customerId", "CUS-" + UUID.randomUUID()),
                JsonNode.class);

        assertThat(accepted.getStatusCode())
                .isEqualTo(HttpStatus.ACCEPTED);
        assertThat(accepted.getBody()).isNotNull();

        String id = accepted.getBody()
                .path("orderId").asText();

        await()
                .atMost(Duration.ofSeconds(15))
                .pollInterval(Duration.ofMillis(200))
                .untilAsserted(() -> {
                    var response = http.getForEntity(
                            "/api/fulfillments/{id}/preparation",
                            JsonNode.class, id);

                    assertThat(response.getStatusCode())
                            .isEqualTo(HttpStatus.OK);
                    assertThat(response.getBody()).isNotNull();
                    assertThat(response.getBody()
                            .path("orderId").asText())
                            .isEqualTo(id);
                    assertThat(response.getBody()
                            .path("state").asText())
                            .isEqualTo("READY");
                });
    }
}
~~~

**Lưu ý:** Contract HTTP có thể dùng 200/202/404 khác nhau khi pending; production cần phân biệt order không tồn tại với chưa xử lý. Cấu hình HTTP connect/read timeout cho mỗi poll riêng, vì Awaitility không bảo đảm hủy tức thì một network request bị block.

## 23. Testcontainers: đừng dừng database trước worker

H2 dùng trong ví dụ giúp tập trung vào mechanics. Với PostgreSQL production-like và các rủi ro constraint/isolation:

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
class FulfillmentPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Inject OrderCommands + FulfillmentQueries;
    // test chờ state READY như mục 10.
}
~~~

Đây là **khung cấu hình**, chưa phải test method. Cần Testcontainers Jupiter/PostgreSQL, Spring Boot Testcontainers, JDBC driver và container runtime. `@ServiceConnection` hỗ trợ từ Spring Boot 3.1+, nên kiểm tra version tương thích.

### Vòng đời quan trọng

- Container phải sẵn sàng trước khi app/test dùng connection.
- Worker cần hoàn tất công việc bắt buộc trước teardown container.
- Spring TestContext cache và Testcontainers lifecycle **không tự bảo đảm cùng vòng đời**.
- Test recovery qua restart cần storage persistent sống qua các lần context restart.
- Flyway/Liquibase production nên được chạy trong những integration tests quan trọng.

**Không tăng Awaitility timeout để sửa container bị đóng, schema sai hoặc datasource trỏ DB đã dừng.** Đó là lỗi setup/lifecycle, không phải độ trễ eventual consistency hợp lệ.

## 24. Deadline, JUnit @Timeout và hậu quả khi test fail

Có thể tổ chức nhiều tầng ngân sách:

~~~text
Awaitility atMost:     10 giây chờ READY
JUnit @Timeout:        20 giây giới hạn test method
HTTP/DB call timeout:  ngắn hơn hoặc phù hợp tổng budget
CI job timeout:        đủ cho toàn suite và startup
~~~

Ví dụ:

~~~java
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Test
@Timeout(value = 20, unit = TimeUnit.SECONDS)
void verifies_async_completion() {
    // Trigger và Awaitility với atMost thấp hơn 20 giây.
}
~~~

Không đặt `@Timeout(5s)` bên ngoài `Awaitility.atMost(10s)` rồi kỳ vọng Awaitility luôn có thời gian đưa diagnostic.

**Deadline test không tự hủy background workflow.** Khi Awaitility timeout, worker có thể vẫn đang chạy và tiếp tục ghi database. Trên failure path cần giữ fixture isolation, quản lý controlled tasks và không vô tình xóa dữ liệu khi worker chưa an toàn để dừng.

Timeout cũng không phải SLO production: `atMost(10s)` ở integration test chỉ chứng minh outcome quan sát được trong môi trường test cụ thể. Latency p95/p99 phải đo riêng dưới tải và môi trường có chủ đích.

## 25. Architectural verification: event đúng nhưng dependency vẫn có thể sai

Module `fulfillment` có thể import public event của `orders`:

~~~java
import com.example.shop.orders.OrderPlaced;
~~~

Không nên import entity ở package nội bộ:

~~~java
// Vi phạm ranh giới module mặc định.
import com.example.shop.orders.internal.persistence.OrderEntity;
~~~

Kiểm tra kiến trúc:

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void module_boundaries_are_valid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm tra các quy tắc Spring Modulith như dependency cycle, truy cập ngoài API module và allowed dependencies nếu cấu hình. Nó **không** chạy business listener hoặc chờ task commit. Vì thế cần cả **architecture test và consumer integration test**.

Nếu `fulfillment` chỉ được phụ thuộc `orders`, khai báo có chủ đích trong `fulfillment/package-info.java`:

~~~java
@ApplicationModule(allowedDependencies = "orders")
package com.example.shop.fulfillment;

import org.springframework.modulith.ApplicationModule;
~~~

Không thêm mọi module vào whitelist chỉ để `verify()` xanh. Chiều event nghiệp vụ `orders → fulfillment` khác với chiều import Java của event type `fulfillment → orders`.

## 26. CI quality gate: báo PASS chỉ khi điều kiện thực sự đạt

~~~mermaid
flowchart LR
    PR["Pull request"] --> U["Unit + slice"]
    U --> A["ApplicationModules.verify()"]
    A --> P["Producer PublishedEvents"]
    P --> C["Consumer completion tests"]
    C --> R["Retry / idempotency / registry"]
    R --> E["Critical HTTP E2E"]
    E --> G{"Các gate bắt buộc xanh?"}
    G -- "Có" --> M["Merge / release"]
    G -- "Không" --> F["Điều tra và sửa"]
~~~

| Gate | Bằng chứng |
| --- | --- |
| Unit/slice | Validation, adapter mapping |
| `ApplicationModules.verify()` | Ranh giới package/dependency |
| `@ApplicationModuleTest` + `PublishedEvents` | Producer phát event đúng |
| Consumer integration + Awaitility | Side effect sau commit được quan sát |
| Concurrency/recovery | Duplicate, retry, restart, registry state |
| Testcontainers DB | Constraint/isolation production-like |
| HTTP E2E | Client thấy terminal outcome theo ID |

### Điều kiện triển khai CI ổn định

- Mỗi test dùng correlation ID riêng, tránh phụ thuộc vào ID cố định.
- Không để `@AfterEach` cleanup khi worker quan trọng còn chạy.
- Giới hạn parallelism nếu fixture/database/executor chia sẻ trạng thái.
- Bắt timeout hữu hạn, ghi last known state và exception.
- Không ignore mọi exception để biến bug thành timeout.
- Không loại bỏ consumer integration chỉ vì producer test xanh và nhanh.
- Không loại bỏ architecture test vì E2E đã đạt READY.
- Theo dõi time-to-READY, timeout rate và executor queue để phát hiện hồi quy performance.

**Một test chỉ “không ném lỗi tới khi return” không đủ làm quality gate cho luồng async**. CI phải chặn những thay đổi khiến listener quan trọng không hoàn tất.

## 27. Troubleshooting khi test xanh nhưng worker thất bại

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Test xanh rồi mới thấy listener exception | Method return trước worker | Await business state |
| `PublishedEvents` xanh, consumer không có task | Chỉ kiểm tra producer | Thêm cross-module integration |
| Spy listener được gọi, DB rỗng | T2 rollback sau invocation | Query state sau commit |
| `@AfterEach` làm listener fail | Cleanup trước worker | Await trước teardown, cô lập fixture |
| `@DirtiesContext` gây DataSource closed | Context đóng khi worker chạy | Review lifecycle và wait |
| Latch `entered` xanh, task vẫn thiếu | Latch đặt ở đầu handler | Await final side effect |
| `@Transactional` test timeout | Test rollback, không có AFTER_COMMIT | Cho producer commit thật |
| Query không thấy task dù DB có | Snapshot/cache cũ hoặc sai ID | Query mới, đúng transaction/UUID |
| Timeout rồi test sau nhiễm dữ liệu | Worker tiếp tục chạy sau deadline | Quản lý failure cleanup, cô lập |
| Task tồn tại nhưng registry pending | Duplicate/retry lỗi | Test registry và idempotency |
| HTTP 202 bị hiểu là completed | Chỉ assert accepted | Poll terminal READY |
| Testcontainers đóng trước listener | Resource lifecycle sai | Wait và giữ container đúng scope |
| Integration xanh nhưng architecture đỏ | Import `internal` sai | Giữ `verify()` trong CI |

### Trình tự điều tra

1. Producer T1 có commit không?
2. Event được publish đúng `orderId` không?
3. Listener đã được bootstrap và đăng ký chưa?
4. Executor có chạy task không?
5. Handler có exception hoặc T2 rollback không?
6. Public query API đọc đúng order/database không?
7. Test return hoặc cleanup có quá sớm không?
8. Registry có pending/retry không?
9. Có **nhiều tác vụ** bắt buộc cần chờ không?
10. Deadline/test env có phù hợp không?

Tăng `Thread.sleep` hay deadline vô hạn không sửa lỗi sai ranh giới hoặc worker không thể hoàn tất.

## 28. Bài thực hành

### Bài A — Tạo xanh giả có kiểm soát

Viết test chỉ gọi `orders.place(...)`, assert ID và return. Trong nhánh thực hành, tạm bỏ `@ApplicationModuleListener`. Xác nhận test vẫn có thể xanh. Sau đó chạy `OrderFulfillmentCompletionTest`; test này phải đỏ vì task không thể xuất hiện.

### Bài B — Thay Thread.sleep bằng Awaitility

Đổi một test `Thread.sleep(2_000)` rồi assert task thành Awaitility `atMost` + `pollInterval`. Chạy khi listener nhanh và chậm, so sánh thời gian chờ và tính ổn định.

### Bài C — Callback started khác committed

Dùng controlled gate/latch trước khi `tasks.save`. Assert listener đã vào gateway, task chưa có; giải phóng gateway rồi Awaitility chờ task. Gây exception sau gateway và xem entered latch vẫn có thể xanh trong khi outcome đỏ.

### Bài D — Race giữa @AfterEach và worker

Dựng fixture cleanup xóa source order. Tạo test sai return sớm khiến listener đọc order sau cleanup, sau đó sửa bằng completion barrier và dữ liệu test riêng. Không phá hạ tầng dùng chung ngoài môi trường test kiểm soát.

### Bài E — Nhiều consumer

Giả định thêm billing module có `BillingQueries.hasReservation(id)`. Viết test cần **cả fulfillment READY và billing reservation**; bỏ billing listener để chứng minh một nhánh thành công không đủ.

### Bài F — CompletableFuture hoàn tất quá sớm

So sánh một future completed khi enqueue với một future chỉ completed sau output đã commit. Giải thích khi nào `Future.get` là barrier hợp lệ.

### Bài G — Transaction rollback

Dùng `TransactionTemplate` publish event rồi rollback T1. Kiểm chứng dữ liệu producer không commit; giải thích vì sao `await().until(!hasTask(id))` là negative assertion yếu.

### Bài H — Duplicate/replay

Phát cùng event hai lần, thử đồng thời và kiểm tra handler an toàn trước unique constraint. Nếu dùng persistent registry, inject consumer failure rồi resubmit/restart để kiểm tra completion/recovery.

### Bài I — Testcontainers và teardown

Chuyển consumer integration sang PostgreSQL Testcontainers. Phân biệt container startup với business wait, giữ DB sống cho tới khi test hoàn tất hoặc recovery scenario được dọn đúng.

### Bài J — Kiểm chứng kiến trúc và CI

Chạy `ApplicationModules.verify()`; cố ý import `orders.internal.persistence.OrderEntity` từ fulfillment và xác nhận architecture test đỏ. Đưa cả producer publication test và consumer completion test vào quality gate.

### Câu hỏi tự đánh giá

1. `@Test` return có bảo đảm `@ApplicationModuleListener` đã chạy xong không?
2. `PublishedEvents` chứng minh điều gì?
3. Vì sao `verify(listener, timeout(...))` chưa chứng minh T2 commit?
4. `CountDownLatch` đặt ở đầu handler đo mốc gì?
5. Khi nào dùng `Future.get` thay vì Awaitility?
6. Vì sao `@AfterEach` có thể làm listener lỗi?
7. Vì sao test after-commit thường không nên gắn outer `@Transactional`?
8. Một task READY có chứng minh duplicate/retry đều an toàn không?
9. HTTP `202 Accepted` có nghĩa workflow hoàn tất không?
10. Timeout Awaitility có hủy worker không?
11. Tại sao phải có cả architecture verification và consumer integration?
12. Khi có hai side effect bắt buộc, chờ một nhánh có đủ không?

## 29. Checklist trước khi cho test kết thúc

- [ ] Đã định nghĩa rõ công việc nền/bước nghiệp vụ cần hoàn tất.
- [ ] Completion barrier quan sát **final business state**, không chỉ callback started.
- [ ] Assertion có đúng `orderId`/correlation ID của lần thử.
- [ ] Consumer test chạy context có listener và transaction thật.
- [ ] Producer T1 commit thật, không bị outer test transaction rollback ngoài ý muốn.
- [ ] Đã dùng timeout hữu hạn với poll interval phù hợp.
- [ ] Không dùng `Thread.sleep` để đoán thời gian hoàn tất.
- [ ] `PublishedEvents` chỉ được xem là bằng chứng publication.
- [ ] Mock/spy invocation không bị nhầm với transaction commit.
- [ ] Nếu contract có nhiều nhánh bắt buộc, test chờ đủ các nhánh.
- [ ] `@AfterEach` và fixture cleanup không chạy trước worker cần thiết.
- [ ] `@DirtiesContext`, executor shutdown và container lifecycle được kiểm soát.
- [ ] Exception trên worker có đường quan sát qua state/log/registry.
- [ ] Test phân biệt business FAILED và observation timeout.
- [ ] CountDownLatch/future test-controlled có cleanup trong `finally` khi cần.
- [ ] Duplicate, replay và recovery có test riêng nếu là cam kết.
- [ ] HTTP `202` không bị coi là business completed.
- [ ] `ApplicationModules.verify()` được chạy trong CI.
- [ ] Negative control khiến test consumer đỏ nếu bỏ listener.
- [ ] Quality gate thật sự thực thi test và lưu diagnostic phù hợp.

## 30. Ghi nhớ

**Không để test kết thúc trước tác vụ nền** là đảm bảo JUnit chỉ tuyên bố pass sau khi đã quan sát được **completion criterion** của công việc bắt buộc. Một event được publish, callback được gọi, future enqueue hoàn tất hoặc một khoảng `Thread.sleep` trôi qua đều có thể **đến trước** transaction consumer commit. Với Spring Modulith, `@ApplicationModuleListener` thường chạy bất đồng bộ sau commit; cách đáng tin là chờ dữ liệu/state phía consumer qua public API bằng Awaitility, theo đúng correlation ID.

Đồng thời phải giữ an toàn lifecycle của `@AfterEach`, context/executor shutdown, Testcontainers và failure path. Dùng `@ApplicationModuleTest` + `PublishedEvents` cho producer contract, integration/reliability tests cho consumer outcome, và `ApplicationModules.verify()` cho ranh giới kiến trúc. Kết hợp chúng trong quality gate CI để ngăn **xanh giả** và hồi quy bất đồng bộ.
