# Phân biệt lỗi test flaky với lỗi production thật

> **Chương:** Async verification  
> **Module:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Bài toán trọng tâm:** Một integration test Spring Modulith có lúc xanh, lúc đỏ vì không thấy side effect của `@ApplicationModuleListener`. Làm thế nào xác định đó là **lỗi phép thử**, **sự cố hạ tầng**, hay **một race/vi phạm hợp đồng có thể xảy ra trong production** — bằng bằng chứng, không chỉ bằng cách chạy lại?

## 1. Định nghĩa lại “flaky”: triệu chứng không phải lời bào chữa cho sản phẩm

Một test là *flaky* khi kết quả pass/fail không ổn định dù input và phiên bản code về cơ bản không đổi. Đặc tính này mô tả **test result**; nó **không tự xác định nguyên nhân**.

Trong Spring Modulith, nhiều lỗi nghiệp vụ thực có tính cạnh tranh và chỉ xuất hiện với một số lịch scheduling. Ví dụ module `orders` lưu order trong transaction T1 rồi publish `OrderPlaced`. Module `fulfillment` tạo projection/fulfillment task khi nhận sự kiện. Test thỉnh thoảng không thấy task trong hạn 3 giây:

~~~java
UUID id = orders.place("CUS-21");

await()
        .atMost(Duration.ofSeconds(3))
        .untilAsserted(() ->
                assertThat(fulfillment.statusFor(id))
                        .isEqualTo(PreparationState.READY));
~~~

Có hai cách giải thích đối lập:

- **Test/harness flaw:** Dữ liệu đã commit đúng, nhưng test đọc qua một transaction/snapshot cũ, dùng sai module slice, fixture bị teardown sớm hoặc thời hạn chờ không phù hợp với hợp đồng.
- **Production defect:** Listener bị dispatch trước T1 commit, side effect bị duplicate, transaction T2 rollback, event không được recover hoặc hệ thống phá một bất biến nghiệp vụ trong một lịch chạy hợp lệ.

Và còn nhóm thứ ba: **hạ tầng/môi trường không ổn định** (DB/container/external sandbox không sẵn sàng, worker bị thiếu tài nguyên). Một lỗi chỉ xảy ra trên CI **không tự động** thuộc nhóm này; load và concurrency cao ở CI cũng có thể giúp phơi bày race thật.

### Phân loại theo bất biến, không theo màu test

| Tình huống quan sát | Nhãn tạm dùng | Cần chứng minh thêm |
| --- | --- | --- |
| Chạy lại thành công | `NON_DETERMINISTIC_OUTCOME` | Chưa đủ dữ liệu để gán nguyên nhân |
| Consumer commit READY rồi test vẫn thấy NOT_FOUND | `SUSPECT_TEST_OBSERVATION` | Kiểm tra query context/cache/replica |
| Consumer chạy trước producer commit và đọc row chưa visible | `CONFIRMED_PRODUCT_RACE` khi violation đã tái hiện | Timeline/connection độc lập |
| Test context thiếu listener do `@ApplicationModuleTest` sai phạm vi | `CONFIRMED_TEST_SETUP_DEFECT` | So sánh bootstrap và bean registration |
| Hai event trùng tạo hai side effects | `CONFIRMED_BUSINESS_INVARIANT_BREACH` | Unique constraint, provider receipt, replay |
| DB container ngừng khi worker còn ghi | `LIFECYCLE_FAILURE` | Ai đóng container/context và khi nào |
| Chỉ biết Awaitility hết hạn | `UNCLASSIFIED_TIMEOUT` | Last state, event ID, listener outcome, registry |

**Không nên hỏi “flaky hay production?” ngay từ đầu**. Hỏi: *đã vi phạm bất biến nào, tại ranh giới nào, và bằng chứng nào phản bác giải thích khác?*

### Bất biến trong ví dụ

Với một event `OrderPlaced(id)` đã commit:

1. Consumer không được dựa vào dữ liệu producer **chưa commit**.
2. Nếu hệ thống hứa durable eventual processing, event không được mất khi listener fail/restart theo policy cụ thể.
3. Fulfillment side effect phải đúng `orderId`, không bị nhân đôi khi replay.
4. Trạng thái `READY` chỉ được báo sau khi side effect cần thiết đã commit; nếu là external workflow nhiều bước, phải xác định `READY` chỉ đại diện bước nào.
5. Một test báo pass phải kiểm chứng **observable business state**, không chỉ listener method được gọi.

Khi chưa biết contract SLA/retry, test không được tự bịa rằng “mọi order phải READY trong 300 ms”. Nếu sản phẩm có deadline chính thức, kiểm tra nó bằng một test SLA riêng và nguồn số liệu phù hợp.

## 2. Lập bản đồ bằng chứng từ T1 tới T2 để định vị lỗi

Dưới đây là timeline tiêu biểu của một luồng event-driven modular:

~~~mermaid
sequenceDiagram
    participant J as JUnit
    participant O as orders T1
    participant EV as Spring events
    participant EX as Async executor
    participant F as fulfillment T2
    participant DB as Database

    J->>O: place(customerId)
    O->>DB: Save order (chưa commit)
    O->>EV: publish OrderPlaced(orderId)
    O->>DB: COMMIT T1
    O-->>J: orderId
    EV-->>EX: Schedule AFTER_COMMIT listener
    EX->>F: Listener entered
    F->>DB: Insert fulfillment_task
    F->>DB: COMMIT T2
    J->>DB: Fresh read fulfillment.statusFor(id)
    DB-->>J: READY
~~~

**Bẫy then chốt:** Các mốc `PUBLISHED`, `LISTENER_ENTERED`, `LISTENER_RETURNED`, `T2_COMMITTED` không thể dùng thay nhau.

| Mốc | Cách thu bằng chứng | Điều **chưa** được chứng minh |
| --- | --- | --- |
| `PUBLISHED` | `PublishedEvents` trong producer module test | T1/T2 đã commit |
| `T1_COMMITTED` | Lời gọi service qua transaction proxy đã hoàn tất khi không có outer transaction; read committed độc lập | Listener đã xử lý |
| `LISTENER_ENTERED` | Event/correlation log hoặc test-only probe | Handler thành công |
| `LISTENER_RETURNED` | Probe ở cuối method body | Transaction T2 đã commit |
| `T2_COMMITTED` | Fresh public read `FulfillmentQueries.statusFor(id) == READY` | External step khác cũng đã DONE |
| `PUBLICATION_PENDING` | Adapter registry nếu được cấu hình | Event chắc chắn mất |
| `PUBLICATION_COMPLETED` | Registry đánh dấu hoàn tất theo target/adapter | Toàn bộ downstream workflow đã hoàn tất |
| `RETRY_WAIT` | Persisted work item, `attempt`, `nextAttemptAt` | Đây là terminal failure |

`@ApplicationModuleListener` ở các bản Spring Modulith tương thích thường áp dụng listener hậu commit, xử lý bất đồng bộ và transaction mới. Nhưng ghi log `LISTENER_RETURNED` **trong body** không chắc commit transaction T2 đã xong: SQL flush/constraint/commit có thể fail sau đó. Hãy hỏi DB state và registry riêng.

### Evidence record tối thiểu khi test đỏ

~~~text
testCase=OrderFulfillmentIT.should_create_task
runId=ci-...
orderId=...
expected=READY
budgetMs=5000
elapsedMs=...
producerOutcome=COMMITTED|ROLLED_BACK|UNKNOWN
publicationCaptured=YES|NO|UNKNOWN
listenerStage=NOT_OBSERVED|ENTERED|RETURNED|FAILED|UNKNOWN
listenerFailureClass=...
lastCommittedView=NOT_FOUND|PENDING|READY|FAILED|QUERY_ERROR
registryState=PENDING|COMPLETED|UNKNOWN
readPath=PRIMARY|REPLICA|CACHE|UNKNOWN
classification=UNCLASSIFIED_TIMEOUT
~~~

Đây là **mẫu instrument của đội dự án**, không phải cấu trúc log Spring Modulith luôn tạo. Điền `UNKNOWN` khi thiếu dữ liệu. Đừng biến `listenerStage=NOT_OBSERVED` thành `listenerNeverRan=true`: có thể probe không được cấu hình, async queue còn đợi hoặc dữ liệu bị cleanup.

## 3. Quy trình tái hiện có đối chứng: biến “đỏ ngẫu nhiên” thành giả thuyết có thể bác bỏ

Tái chạy nhiều lần có ích để **thu mẫu**, không đủ để kết luận nguyên nhân. Dùng các thí nghiệm nhỏ, mỗi lần thay đổi **một điều kiện**.

### Ma trận thí nghiệm

| Thí nghiệm | Giữ nguyên | Chỉ thay đổi | Kết quả giúp phân biệt |
| --- | --- | --- | --- |
| Chạy một test độc lập | Same code, DB/schema, event ID policy | Không chạy tests khác | Shared fixture/context contamination? |
| Chạy toàn suite | Same versions | Thêm concurrent tests | Data race, shared executor, parallel interference? |
| Fresh context vs cached context | Same business commands | Context lifecycle | Singleton mutable state/`@DirtiesContext`? |
| PostgreSQL Testcontainers vs H2 | Same scenario | Database engine | Isolation/locking/constraint behavior? |
| Bỏ outer test `@Transactional` | Same producer/consumer | Commit boundary | `AFTER_COMMIT` có bị test transaction trì hoãn? |
| Controlled gate vs natural scheduling | Same handler | Cố định thứ tự thread | Bug ordering trước commit hoặc cleanup race? |
| Fake clock/controlled gateway vs remote real | Same policy | Loại network jitter | Logic retry hay provider/sandbox? |
| Unique IDs vs fixed shared ID | Same assertions | Isolation dữ liệu | Cross-test leakage/duplicate fixture? |
| Query primary DB vs read replica/cache | Same `orderId` | Read path | Stale read hay T2 chưa commit? |
| Disable automatic replay trong test-controlled environment | Same event/handler | Recovery scheduling | Replay gây duplicate hoặc ảnh hưởng test sau? |

**Không kết luận** rằng “pass 20 lần liên tục = không có bug”. Với race hiếm, một kết quả âm không chứng minh an toàn. Ngược lại, một lỗi được tái hiện với invariant breach và causal timeline **đủ đáng để giữ CI đỏ** dù xác suất thấp.

### Quy trình triage ngắn

1. **Giữ bằng chứng lần fail đầu.** Chụp seed/config/build, `orderId`, exception, start/commit timestamps, context ID, DB URL/schema, thread name, worker attempt.
2. **Đặt invariant rõ.** Ví dụ “mỗi committed OrderPlaced phải có đúng một fulfillment task” khác với “listener phải chạy trong 100 ms”.
3. **Kiểm tra control flow.** T1 commit chưa? Event publish chưa? Listener được scan chưa? T2 error gì? Query có fresh transaction không?
4. **Tạo hai giả thuyết cạnh tranh.** Ví dụ stale read vs T2 rollback; tìm một thí nghiệm phân biệt chúng.
5. **Thu bằng chứng phản chứng.** Nếu primary DB đã có task và test vẫn trả empty, kiểm tra reader/cache. Nếu primary DB cũng không có, tập trung listener/T2/registry.
6. **Cố định scheduling khi cần.** Latch/test port, `TransactionTemplate`, controlled scheduler; không tăng `Thread.sleep`.
7. **Sửa nguyên nhân, giữ regression test.** Nếu product race, test phải fail khi khôi phục code lỗi. Nếu test flaw, phép thử mới phải chờ đúng outcome và không che lỗi sản phẩm.
8. **Xác định gate CI.** Không tự động thay đổi thành “retry test đến khi xanh”.

### Vì sao thống kê chạy lặp không thay causal proof?

Một test có thể fail 1/100 lần vì **business race thật**, hoặc 50/100 lần vì fixture sai. Tần suất chỉ cho biết symptom dưới một tập điều kiện; không chỉ ra root cause. Đặc biệt, tự động test rerun có thể **mất log và DB state của lần đầu**. Nếu pipeline cho phép rerun để chẩn đoán, lưu artifact lần fail gốc và báo cáo cả lượt 1 lẫn lượt rerun.

### Điều nên ổn định trong thí nghiệm

- Dùng `UUID`/`testRunId` riêng; không dùng một `customerId` cố định với side effect ngoài phạm vi.
- Ghi JDK/Spring Boot/Spring Modulith versions và profile, nhưng không sửa versions đồng thời với test scheduling.
- Tách container startup timeout, producer transaction timeout, Awaitility budget, HTTP timeout và CI job timeout.
- Không dùng `@DirtiesContext` để “làm sạch” vô điều kiện: context teardown có thể gây chính race cần điều tra.
- Không đặt query stale `Optional`/`boolean` ngoài predicate rồi poll biến đó mãi.

## 4. Ví dụ tự chứa: hai module và outcome có thể đọc lại

Tập trung vào **một bất biến**: một lệnh `orders.place(...)` đã commit phải khiến `fulfillment` tạo task cho đúng `orderId`. Phần code dưới dùng Java 17+, Spring Boot 3.x/JPA và Spring Modulith version tương thích. Nó minh họa các class cốt lõi; test cần datasource/schema và dependencies tương ứng.

### Cấu trúc module

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderCommands.java              # API public
│   ├── OrderPlaced.java                # Event public
│   └── internal/
│       ├── OrderApplicationService.java
│       ├── OrderEntity.java
│       └── OrderRepository.java
└── fulfillment/
    ├── FulfillmentQueries.java         # API public
    ├── PreparationState.java
    └── internal/
        ├── OrderPlacedListener.java
        ├── FulfillmentQueryService.java
        ├── FulfillmentTask.java
        └── FulfillmentTaskRepository.java
~~~

**`ShopApplication.java`**

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

**Public API của producer:**

~~~java
// com/example/shop/orders/OrderCommands.java
package com.example.shop.orders;

import java.util.UUID;

public interface OrderCommands {
    UUID place(String customerId);
}
~~~

~~~java
// com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

**Entity/repository nội bộ của producer:**

~~~java
// com/example/shop/orders/internal/OrderEntity.java
package com.example.shop.orders.internal;

import java.util.UUID;
import jakarta.persistence.*;

@Entity
@Table(name = "customer_orders")
class OrderEntity {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String customerId;

    protected OrderEntity() {}

    OrderEntity(UUID id, String customerId) {
        this.id = id;
        this.customerId = customerId;
    }
}
~~~

~~~java
// com/example/shop/orders/internal/OrderRepository.java
package com.example.shop.orders.internal;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {}
~~~

**Service transaction T1:**

~~~java
// com/example/shop/orders/internal/OrderApplicationService.java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.orders.OrderCommands;
import com.example.shop.orders.OrderPlaced;

@Service
class OrderApplicationService implements OrderCommands {

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    OrderApplicationService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Override
    @Transactional
    public UUID place(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid customerId");
        }

        UUID id = UUID.randomUUID();
        repository.save(new OrderEntity(id, customerId));
        publisher.publishEvent(new OrderPlaced(id));

        return id;
    }
}
~~~

Không gắn outer `@Transactional` lên integration test nếu test cần listener pha `AFTER_COMMIT` chạy: service có thể tham gia transaction của test và bị rollback trước khi commit.

**Public API của consumer:**

~~~java
// com/example/shop/fulfillment/PreparationState.java
package com.example.shop.fulfillment;

public enum PreparationState {
    NOT_OBSERVED,
    READY
}
~~~

~~~java
// com/example/shop/fulfillment/FulfillmentQueries.java
package com.example.shop.fulfillment;

import java.util.UUID;

public interface FulfillmentQueries {
    PreparationState statusFor(UUID orderId);
}
~~~

**Entity/repository và listener consumer:**

~~~java
// com/example/shop/fulfillment/internal/FulfillmentTask.java
package com.example.shop.fulfillment.internal;

import java.util.UUID;
import jakarta.persistence.*;

@Entity
@Table(name = "fulfillment_tasks")
class FulfillmentTask {

    @Id
    private UUID orderId;

    protected FulfillmentTask() {}

    FulfillmentTask(UUID orderId) {
        this.orderId = orderId;
    }
}
~~~

~~~java
// com/example/shop/fulfillment/internal/FulfillmentTaskRepository.java
package com.example.shop.fulfillment.internal;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface FulfillmentTaskRepository
        extends JpaRepository<FulfillmentTask, UUID> {}
~~~

~~~java
// com/example/shop/fulfillment/internal/OrderPlacedListener.java
package com.example.shop.fulfillment.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;

@Component
class OrderPlacedListener {

    private final FulfillmentTaskRepository tasks;

    OrderPlacedListener(FulfillmentTaskRepository tasks) {
        this.tasks = tasks;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        tasks.save(new FulfillmentTask(event.orderId()));
    }
}
~~~

~~~java
// com/example/shop/fulfillment/internal/FulfillmentQueryService.java
package com.example.shop.fulfillment.internal;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.PreparationState;

@Service
class FulfillmentQueryService implements FulfillmentQueries {

    private final FulfillmentTaskRepository tasks;

    FulfillmentQueryService(FulfillmentTaskRepository tasks) {
        this.tasks = tasks;
    }

    @Override
    @Transactional(readOnly = true)
    public PreparationState statusFor(UUID id) {
        return tasks.existsById(id)
                ? PreparationState.READY
                : PreparationState.NOT_OBSERVED;
    }
}
~~~

**Caveat phải giữ:** Handler trên minh họa happy path, **chưa chứng minh idempotency dưới duplicate delivery đồng thời**. `JpaRepository.save` với assigned ID không thay thế một chiến lược unique constraint/concurrency/replay toàn diện. Cần test riêng nếu event registry có thể redeliver. Sử dụng public `FulfillmentQueries` để quan sát outcome thay vì cho `orders` import `fulfillment.internal`.

### Phân biệt hai phép thử về cùng luồng

- `orders` module test có thể kiểm tra `OrderPlaced` được publish, không cần chờ listener.
- Cross-module integration test kiểm tra task đã commit qua query của `fulfillment`, không dùng `PublishedEvents` làm oracle completion.

Khi hai test báo kết quả khác nhau, đó là **bằng chứng phân vùng lỗi**, không phải lý do để bỏ một test.
## 5. Tách phép thử producer và consumer để xác định lỗi nằm ở đâu

### Producer module test: event có được phát đúng không?

**`src/test/java/com/example/shop/orders/OrderPublicationTest.java`**

~~~java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderPublicationTest {

    @Autowired
    OrderCommands orders;

    @Test
    void publishes_order_placed_with_correct_id(
            PublishedEvents publishedEvents) {

        UUID id = orders.place("CUS-EVENT");

        assertThat(publishedEvents.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }
}
~~~

**Bằng chứng đúng:** Producer publish ít nhất một `OrderPlaced` mang ID vừa tạo. `anySatisfy` **không** chứng minh chỉ có đúng một event, T2 commit hoặc event bền qua restart.

**Giới hạn phạm vi:** `@ApplicationModuleTest` thường chỉ bootstrap module `orders` và các dependency phù hợp; `fulfillment` consumer có thể không có trong context. Một producer test xanh và consumer integration đỏ là **tín hiệu phân lớp**, không phải hai kết quả mâu thuẫn.

Nếu kết quả producer-only test lúc đỏ lúc xanh, kiểm tra shared fixture/DB/transaction của `orders` trước. Nếu producer test luôn xanh nhưng integration thỉnh thoảng đỏ, ưu tiên quan sát AFTER_COMMIT event dispatch, executor, consumer transaction, retry và read path. Vẫn không nên kết luận nguyên nhân chỉ từ sự tương quan.

### Cross-module integration: chờ dữ liệu đã commit

**`src/test/java/com/example/shop/OrderFulfillmentIT.java`**

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import org.awaitility.core.ConditionTimeoutException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import com.example.shop.orders.OrderCommands;
import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.PreparationState;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrderFulfillmentIT {

    @Autowired
    OrderCommands orders;

    @Autowired
    FulfillmentQueries fulfillment;

    @Test
    void committed_order_eventually_has_task() {
        UUID id = orders.place("CUS-" + UUID.randomUUID());

        var last = new AtomicReference<>(
                PreparationState.NOT_OBSERVED);

        long started = System.nanoTime();

        try {
            await()
                    .alias("fulfillment READY for " + id)
                    .atMost(Duration.ofSeconds(8))
                    .pollInterval(Duration.ofMillis(100))
                    .untilAsserted(() -> {
                        PreparationState state =
                                fulfillment.statusFor(id);

                        last.set(state);

                        assertThat(state)
                                .isEqualTo(PreparationState.READY);
                    });
        } catch (ConditionTimeoutException timeout) {
            long elapsedMs = Duration.ofNanos(
                    System.nanoTime() - started).toMillis();

            throw new AssertionError(
                    "Outcome not observed: orderId=" + id
                    + ", expected=READY"
                    + ", lastState=" + last.get()
                    + ", elapsedMs=" + elapsedMs
                    + ", next=inspect T1, listener, T2, registry, read path",
                    timeout);
        }
    }
}
~~~

Ứng dụng test phải có datasource/JPA schema phù hợp. Ví dụ này **không cung cấp SQL migration**, nên cần cấu hình database test, schema/migration và dependency Spring Modulith/JUnit/Awaitility của dự án; với Oracle liên quan PostgreSQL locking/constraint, sử dụng Testcontainers ở mục 6 thay vì H2 giả định.

### Điểm chẩn đoán được mà một phép wait bình thường không có

- `orderId` riêng cho mỗi test cho phép nối log producer/consumer.
- `lastState` được cập nhật **bên trong polling predicate**; không giữ snapshot cũ ngoài vòng await.
- `ConditionTimeoutException` được giữ làm `cause`, không mất stack trace.
- `elapsedMs` tính bằng `System.nanoTime()`, không phụ thuộc wall clock của máy.
- Không `Thread.sleep` một khoảng cố định và không bỏ qua exception từ repository chỉ để tránh fail.
- Trong trường hợp `READY` chỉ là bước đầu của workflow, test cần dùng trạng thái cuối **đúng theo hợp đồng** thay vì đặt tên READY quá rộng.

**Giới hạn quan trọng:** Nếu `lastState=NOT_OBSERVED` sau 8 giây, report **vẫn chưa biết nguyên nhân**. Có thể T1 chưa commit, listener chưa schedule, T2 rollback hoặc reader stale. Bước tiếp theo là thêm instrumentation đúng nhánh, không tăng timeout mù quáng.

### Kiểm thử một trạng thái lỗi terminal

Nếu consumer có public `FAILED` terminal, đừng chờ đủ 8 giây khi đã thấy `FAILED`. Thiết kế contract giàu hơn:

~~~java
// Pseudocode khi public enum có FAILED terminal:
await()
        .atMost(Duration.ofSeconds(8))
        .untilAsserted(() -> {
            var snapshot = queries.snapshotFor(id);

            if (snapshot.status() == FAILED) {
                throw new TerminalFulfillmentFailure(
                        snapshot.failureCode());
            }

            assertThat(snapshot.status()).isEqualTo(READY);
        });
~~~

`TerminalFulfillmentFailure` phải là exception **không được cấu hình ignored** trong Awaitility. `queries.snapshotFor` và các trạng thái ở đây là API cần thêm nếu ứng dụng có workflow terminal failure; không áp chúng lên `PreparationState` chỉ có `NOT_OBSERVED/READY` của ví dụ.

**Không dùng `Awaitility.ignoreExceptions()` vô điều kiện.** Nó có thể biến lỗi DB/handler cần fail-fast thành timeout chung chung.

## 6. Race sản phẩm thật: cố định cửa sổ trước commit bằng latch

Một *production race* thường bị gán nhầm thành test flaky: `orders` gọi `publishEvent` trong T1; consumer sai dùng `@Async @EventListener`, thực thi sớm trước T1 commit rồi đọc source `orders` qua transaction khác. Có lúc T1 commit trước khi consumer đọc nên xanh; có lúc consumer đọc trước commit nên không thấy row.

### Negative control: listener chạy quá sớm

~~~java
// TEST-ONLY variant nhằm tái hiện một implementation sai.
// Không chạy cùng một production listener trong suite bình thường.
@Component
class UnsafeEarlyOrderListener {

    private final OrderQueries source;
    private final EarlyReadWitness witness;

    UnsafeEarlyOrderListener(
            OrderQueries source,
            EarlyReadWitness witness) {
        this.source = source;
        this.witness = witness;
    }

    @Async
    @EventListener
    void on(OrderPlaced event) {
        boolean committedVisible =
                source.exists(event.orderId());

        witness.record(event.orderId(), committedVisible);
    }
}
~~~

Test-only witness tương ứng (đặt cùng package với negative-control listener và đăng ký bean trong test context):

~~~java
final class EarlyReadWitness {

    final CountDownLatch observed = new CountDownLatch(1);

    final ConcurrentMap<UUID, Boolean> visibilityByOrder =
            new ConcurrentHashMap<>();

    void record(UUID orderId, boolean visible) {
        visibilityByOrder.put(orderId, visible);
        observed.countDown();
    }
}
~~~

Cần imports `UUID`, `CountDownLatch`, `ConcurrentMap`, `ConcurrentHashMap`, `@Component`, `@Async`, `@EventListener` và các public event/query types tương ứng. Witness dùng một latch cho **một** kịch bản; nếu chạy nhiều event song song thì dùng barrier keyed by ID. Trong negative-control test, sau khi producer đã tới commit gate, đợi `observed.await(timeout)` **trước khi thả gate**, rồi assert `visibilityByOrder.get(id) == false`.

Vì `@Async @EventListener` có thể schedule ngay khi producer publish, không gắn callback với commit T1, phép đọc độc lập ở PostgreSQL `READ_COMMITTED` có thể thấy `false`. **Việc thread chạy nhanh hơn producer không phải lỗi test**: nếu handler production cần committed data mà dispatch sớm, chính product contract sai.

### Thêm test seam chỉ để điều khiển lịch

Trong `com.example.shop.orders.internal`:

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

interface CommitWindow {
    void afterPublication(UUID id);
}
~~~

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;
import org.springframework.stereotype.Component;

@Component
class NoOpCommitWindow implements CommitWindow {

    @Override
    public void afterPublication(UUID id) {
        // Production: không block.
    }
}
~~~

**Thay** implementation producer `OrderApplicationService` ở mục 4 bằng biến thể inject `CommitWindow`, và sửa phần transaction method:

~~~java
@Service
class OrderApplicationService implements OrderCommands {

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;
    private final CommitWindow commitWindow;

    OrderApplicationService(
            OrderRepository repository,
            ApplicationEventPublisher publisher,
            CommitWindow commitWindow) {
        this.repository = repository;
        this.publisher = publisher;
        this.commitWindow = commitWindow;
    }

    @Override
    @Transactional
    public UUID place(String customerId) {
        UUID id = UUID.randomUUID();

        repository.saveAndFlush(
                new OrderEntity(id, customerId));

        publisher.publishEvent(new OrderPlaced(id));

        // Còn bên trong @Transactional method:
        // T1 chưa commit, dù SQL đã được flush.
        commitWindow.afterPublication(id);

        return id;
    }
}
~~~

Đoạn trên thuộc cùng package `orders.internal` và cần imports Spring/JPA/API như mục 4. Đây là **biến thể thay thế**, không thêm một bean service trùng vào production. `saveAndFlush` chỉ đẩy SQL vào T1, **không làm transaction khác thấy row chưa commit**.

### Public source query làm oracle độc lập

Để chứng minh sự khác biệt trước/sau commit, thêm public API ở module `orders`:

~~~java
// com/example/shop/orders/OrderQueries.java
package com.example.shop.orders;

import java.util.UUID;

public interface OrderQueries {
    boolean exists(UUID orderId);
}
~~~

~~~java
// com/example/shop/orders/internal/OrderQueryService.java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.orders.OrderQueries;

@Service
class OrderQueryService implements OrderQueries {

    private final OrderRepository repository;

    OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional(readOnly = true)
    public boolean exists(UUID id) {
        return repository.existsById(id);
    }
}
~~~

Test sẽ gọi `ordersQuery.exists(id)` trên **test thread**, không trên producer worker thread. Trong PostgreSQL `READ_COMMITTED` nó sẽ đọc transaction độc lập thay vì dirty state trong T1.

### Test giữ producer trước commit rồi thả

**`src/test/java/com/example/shop/orders/internal/CommitWindowIT.java`**

~~~java
package com.example.shop.orders.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import com.example.shop.orders.OrderCommands;
import com.example.shop.orders.OrderQueries;
import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.PreparationState;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
            "spring.jpa.hibernate.ddl-auto=create-drop",
            "spring.datasource.hikari.maximum-pool-size=5"
        })
@Import(CommitWindowIT.GateConfig.class)
class CommitWindowIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderCommands commands;
    @Autowired OrderQueries ordersQuery;
    @Autowired FulfillmentQueries fulfillment;
    @Autowired PausingCommitWindow gate;

    @Test
    void distinguishes_precommit_from_aftercommit_visibility()
            throws Exception {

        ExecutorService caller = Executors.newSingleThreadExecutor();

        try {
            Future<UUID> created = caller.submit(
                    () -> commands.place("CUS-" + UUID.randomUUID()));

            assertThat(gate.entered.await(4, TimeUnit.SECONDS))
                    .as("Producer must reach post-publication gate")
                    .isTrue();

            UUID id = gate.orderId.get();
            assertThat(id).isNotNull();

            // Independent reader: T1 still open.
            assertThat(ordersQuery.exists(id)).isFalse();

            // Snapshot only: absent now is NOT proof that
            // a faulty async listener can never run early.
            assertThat(fulfillment.statusFor(id))
                    .isEqualTo(PreparationState.NOT_OBSERVED);

            gate.release.countDown();
            assertThat(created.get(8, TimeUnit.SECONDS))
                    .isEqualTo(id);

            assertThat(ordersQuery.exists(id)).isTrue();

            await()
                    .atMost(Duration.ofSeconds(10))
                    .untilAsserted(() ->
                            assertThat(fulfillment.statusFor(id))
                                    .isEqualTo(PreparationState.READY));

        } finally {
            gate.release.countDown();

            caller.shutdown();

            if (!caller.awaitTermination(
                    8, TimeUnit.SECONDS)) {
                caller.shutdownNow();

                assertThat(caller.awaitTermination(
                        2, TimeUnit.SECONDS))
                        .as("Test-owned caller must terminate")
                        .isTrue();
            }
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class GateConfig {

        @Bean
        @Primary
        PausingCommitWindow commitWindowForTest() {
            return new PausingCommitWindow();
        }
    }

    static final class PausingCommitWindow
            implements CommitWindow {

        final AtomicReference<UUID> orderId =
                new AtomicReference<>();

        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);

        @Override
        public void afterPublication(UUID id) {
            orderId.set(id);
            entered.countDown();

            try {
                if (!release.await(12, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Commit gate timeout for " + id);
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();

                throw new IllegalStateException(
                        "Producer interrupted before commit",
                        interrupted);
            }
        }
    }
}
~~~

**Phạm vi tiền điều kiện:** Spring Boot 3.1+ cho `@ServiceConnection`, Spring Modulith cùng JPA/transactions, Testcontainers Jupiter/PostgreSQL, PostgreSQL driver và container runtime; sử dụng schema test/migrations tương thích. `hibernate.ddl-auto=create-drop` chỉ là lựa chọn minh họa để bài tự chứa. Connection pool cần đủ connections cho T1 đang giữ kết nối và reader T2/test thread. Nếu dự án dùng Flyway/Liquibase, test nên kiểm chứng migrations thực.

**Đừng chạy nhiều test dùng chung `PausingCommitWindow` một lần với singleton latch**: tạo gate per correlation ID hoặc context test riêng cho scenario, tránh test A release T1 của test B. Latch luôn được giải phóng trong `finally`; `ExecutorService` trong test do test sở hữu, **không shutdown Spring-managed event executor**.

### Điều test này xác minh và chưa xác minh

- **Có:** Producer đã publish/flush nhưng chưa commit tại gate; reader transaction độc lập không thấy row; sau release T1 commit và consumer outcome cuối được quan sát.
- **Chưa:** Một listener sai `@Async @EventListener` chắc chắn đã chạy *trước release*. Snapshot `NOT_OBSERVED` không chứng minh absence mãi mãi.
- **Muốn chứng minh lỗi sai:** Wire `UnsafeEarlyOrderListener` vào **một context negative-control riêng**, thêm `EarlyReadWitness` có latch `observed`, giữ T1 tại gate và **chờ witness đọc xong trước khi release**. Assert witness thấy `false` trong khi T1 chưa commit. Với listener hậu commit đúng, **không được chờ nó chạy trước release** — nếu làm vậy test tự deadlock.

Khi lịch đọc sớm có thể được ép như trên, ta có một **causal reproduction của production race**, không còn chỉ là “CI thỉnh thoảng đỏ”.

## 7. Những lỗi tạo flakiness chỉ trong phép thử và cách bác bỏ

Một số phản mẫu khiến test đỏ dù logic product theo contract đang đúng. Không sửa bằng cách thêm `Thread.sleep` hoặc tăng timeout trước khi xác định nguyên nhân.

| Lỗi harness | Symptom | Phép thử đối chứng | Sửa đúng |
| --- | --- | --- | --- |
| Outer `@Transactional` test rollback | Listener `AFTER_COMMIT` không chạy | Bỏ outer transaction/commit rõ; producer outcome có khác? | Cho T1 commit thật khi test after-commit |
| Assertion đồng bộ ngay sau producer return | Task chưa xuất hiện mặc dù worker sẽ commit | Poll fresh state rồi thấy READY | Awaitility bounded theo business contract |
| Cố định một boolean snapshot rồi poll | Test timeout bất kể DB đã đổi | Re-query trong predicate | Gọi public API mỗi poll |
| Chạy producer `@ApplicationModuleTest` nhưng assert consumer | Listener không được bootstrap | Full context/slice có consumer | Tách test producer và integration |
| `@DirtiesContext`/container stop khi callback còn chạy | Late connection-closed exception | Xem context/container lifecycle | Align context, worker, DB teardown |
| `@AfterEach deleteAll()` khi worker còn retry | Dữ liệu biến mất/tái xuất hiện ở test sau | Tạm bỏ destructive cleanup, dùng ID riêng | Isolation và quiescence |
| Static latch/fake counter dùng chung | Chỉ fail khi parallel | Chạy isolated, per-ID probe | Test-scoped state |
| Test đọc replica/cache lag | Primary DB có row READY nhưng query absent | Query authoritative primary/read transaction mới | Chỉnh read consistency/hợp đồng eventual |
| Test dùng H2 khác production engine | Lock/constraint test thất bại khác nhau | PostgreSQL Testcontainers | Kiểm thử đúng DB engine cho rủi ro tương ứng |
| Chỉ dùng `Mockito.verify(..., timeout(...))` | Method được gọi nhưng T2 rollback | Query committed business effect | Invocation chỉ là evidence phụ |
| `@MockBean`/bean override không đúng scope | Real listener/gateway khác mong đợi | Xem bean resolution/test context config | Fake đúng port và test profile |
| Awaitility ignore-all exceptions | DB lỗi bị biến thành timeout | Tắt ignore-all, xem cause gốc | Chỉ ignore exception transient có chủ đích |

### Ví dụ outer transaction tự tạo false timeout

~~~java
@SpringBootTest
class WrongTransactionIT {

    @Autowired OrderCommands orders;
    @Autowired FulfillmentQueries fulfillment;

    @Transactional
    @Test
    void this_test_cannot_verify_after_commit_yet() {
        UUID id = orders.place("CUS-ROLLBACK");

        await().atMost(Duration.ofSeconds(3))
                .untilAsserted(() ->
                        assertThat(fulfillment.statusFor(id))
                                .isEqualTo(PreparationState.READY));
    }
}
~~~

Nếu producer `OrderApplicationService.place` có propagation `REQUIRED`, nó có thể tham gia outer transaction do Spring Test mở; transaction test thường rollback lúc method kết thúc. `@ApplicationModuleListener` hậu commit không được dispatch như production. Đây là lỗi **test transaction boundary**, không phải bằng chứng sản phẩm mất event. Bỏ `@Transactional` outer và cho service commit qua proxy trước khi await; với test rollback riêng, dùng `TransactionTemplate`/Spring Test transaction controls phù hợp.

### Ví dụ snapshot stale làm test “flaky” hoặc luôn đỏ

~~~java
// Sai: giá trị chỉ được lấy một lần.
PreparationState cached = fulfillment.statusFor(id);

await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> cached == PreparationState.READY);
~~~

~~~java
// Đúng: truy vấn mới mỗi lần poll.
await()
        .atMost(Duration.ofSeconds(5))
        .until(() ->
                fulfillment.statusFor(id) == PreparationState.READY);
~~~

Nếu transaction đọc đã tồn tại với snapshot isolation hoặc Hibernate session cache cũ, **chỉ gọi lại method** cũng có thể không đủ: cần đảm bảo mỗi lần poll dùng transaction đọc mới/consistent read path theo mục tiêu.

### Lỗi product và lỗi harness có thể đồng thời tồn tại

Chẳng hạn test giữ snapshot cũ **đồng thời** consumer thiếu idempotency khi replay. Sửa reader khiến test xanh không loại bỏ race sản phẩm. Cần giữ một test **duplicate/replay** riêng với invariant đúng một business effect. Tránh kết luận “đã sửa flaky” khi chỉ thay thời hạn await và chưa chứng minh downstream state đúng.
## 8. Khi nào phải xác nhận lỗi production: replay, transaction và business invariant

Một test “có lúc đỏ” phải được coi là **điều tra sản phẩm** khi có bằng chứng một lịch thực thi hợp lệ có thể phá bất biến. Đặc biệt, event-driven systems không hứa listener được chạy đúng một lần trong mọi failure/recovery scenario.

### Ba loại vi phạm phải được kiểm chứng riêng

| Invariant | Lỗi thật có thể gặp | Bằng chứng đúng |
| --- | --- | --- |
| Consumer không đọc dữ liệu chưa commit | `@Async @EventListener` chạy trước T1 commit | Latch giữ T1 + độc lập READ_COMMITTED reader |
| Sau T1 commit, event được xử lý theo reliability contract | Listener T2 fail và publication bị bỏ quên | Registry pending/recovery, committed business state |
| Cùng event ID không nhân đôi business effect | Duplicate/replay hoặc timeout mơ hồ tạo hai tác động ngoài | Idempotency key, provider effect ledger, DB constraint |

Nhóm thứ hai và thứ ba **có thể bị che bởi một test chỉ assert task READY**. Task có thể đã được tạo trong attempt A, nhưng attempt B đang retry và cuối cùng tạo thêm external shipment. Cần phân biệt **đã có outcome** với **không có duplicate**.

### Event Publication Registry: đọc đúng semantics

Spring Modulith có Event Publication Registry và những persistence adapters tương thích. Khi listener thất bại, một publication có thể còn ở trạng thái chưa hoàn tất, và có thể được resubmit qua API/policy của adapter/version.

~~~text
T1_COMMITTED OrderPlaced(id)
    -> publication cho fulfillment listener được theo dõi
    -> invocation #1: T2 fail
    -> publication có thể PENDING
    -> retry/resubmit invocation #2
    -> T2 success + committed task
    -> registry completed theo contract
~~~

Không mặc định có retry vô hạn, exactly-once hay một bảng lưu attempt count giống nhau ở mọi adapter. Với Spring Modulith, **một event fan-out tới nhiều listeners** có thể có publication records riêng cho từng target. Khi chẩn đoán, nối **event ID + listener target + publication ID**, không chỉ đếm một row theo order ID.

| Evidence | Kết luận được | Chưa kết luận |
| --- | --- | --- |
| `PublishedEvents` có OrderPlaced | Producer đã publish | T1 commit và consumer xong |
| Probe listener `ENTERED` | Handler bắt đầu | T2 commit |
| Probe listener `RETURNED` | Handler body chạy hết | Flush/commit T2 thành công |
| Public `READY` | Business effect visible | Replay không còn pending |
| Registry `COMPLETED` | Handler xử lý theo registry semantics | External job nhiều bước đã DONE |
| Registry `PENDING` | Chưa marked completed theo adapter | Event chắc chắn bị mất |
| Provider thấy hai request | Hai lần gọi ra ngoài | Hai business effects nếu có idempotency |
| Provider thấy hai shipment IDs | Có dấu hiệu duplicate effect | Cần đối chiếu với idempotency/compensation |

**Bằng chứng nên được giữ trước cleanup.** Không xóa pending publication và không `deleteAll()` dữ liệu test khi còn listener có thể retry; điều đó có thể biến một lỗi thật thành “không thể tái hiện”.

### Kiểm tra khác nhau giữa *request attempts* và *side effects*

Một gateway fake có thể nhận nhiều lời gọi nhưng vẫn trả **cùng một** resource cho cùng idempotency key:

~~~java
package com.example.shop.fulfillment.internal;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

final class RecordingShippingProvider {

    private final ConcurrentMap<String, String> createdByKey =
            new ConcurrentHashMap<>();

    private final AtomicInteger requests =
            new AtomicInteger();

    String createShippingLabel(String idempotencyKey) {
        requests.incrementAndGet();

        // Cùng key -> cùng kết quả; chỉ tạo effect mới
        // khi key chưa có.
        return createdByKey.computeIfAbsent(
                idempotencyKey,
                key -> "LABEL-" + key);
    }

    int requestCount() {
        return requests.get();
    }

    int distinctEffects() {
        return createdByKey.size();
    }
}
~~~

Một unit test của fake chỉ chứng minh **fake có idempotency semantics**, không chứng minh consumer production sử dụng đúng key. Để kiểm tra business invariant, inject fake qua **port thật** của consumer trong integration test, cho duplicate/replay với cùng `orderId` và assert:

~~~java
// Pseudocode integration assertions:
assertThat(provider.requestCount())
        .as("Replay may produce multiple requests")
        .isGreaterThanOrEqualTo(2);

assertThat(provider.distinctEffects())
        .as("One business effect per idempotency key")
        .isEqualTo(1);

assertThat(fulfillment.statusFor(id))
        .isEqualTo(PreparationState.READY);

// Nếu dùng persistent registry, kiểm tra publication
// target của đúng event đã đạt trạng thái theo policy.
~~~

Lệnh assert `requestCount >= 2` **chỉ hợp lệ** sau khi test đã kích hoạt và **xác nhận** ít nhất hai invocations (bằng controlled gateway/barrier hoặc recovery receipt). Không được chỉ gửi duplicate event rồi đọc count ngay; async handler có thể chưa bắt đầu. Khi cần retry/concurrency, dùng latch, công cụ adapter hoặc wait criterion cho invocation count với deadline. Cần đặc biệt tránh việc mock cắt bỏ transaction/registry khi định tuyên bố integration reliability.

### Failure injection phân biệt sản phẩm với test artifact

1. **Producer rollback sau publish:** Dùng `TransactionTemplate` để rollback T1 sau khi phát event; listener hậu commit không được tạo business task từ event đó. Nếu callback sai pha vẫn gây effect, là defect.
2. **Consumer T2 commit failure:** Cho database constraint/transaction failure sau handler body. Test phải quan sát committed state và pending publication nếu có; listener body “RETURNED” chưa đủ.
3. **Duplicate delivery:** Publish cùng event ID lần nữa trong transaction hợp lệ, chờ handler/recovery evidence, đo số external **effects** và trạng thái DB, không chỉ số callbacks.
4. **Provider timeout sau khi đã xử lý:** Fake trả timeout ở attempt 1 sau khi đã tạo label; attempt 2 phải dùng cùng idempotency key, không tạo label thứ hai.
5. **Restart/resubmit:** Giữ registry storage và work item qua lifecycle restart; chỉ gọi recovery API mà adapter hỗ trợ, không bịa tên API hoặc ngủ tới production maintenance interval.

**Nếu tái hiện được một lịch hợp lệ làm mất/nhân đôi business effect, đó là lỗi sản phẩm** ngay cả khi test run khác pass. Nếu thí nghiệm chỉ làm test instrumentation hỏng mà invariant production vẫn giữ, đó là test-harness defect — nhưng cần chứng minh bằng read/receipt độc lập.

## 9. CI triage: giữ fail gốc, phân tầng quality gate và quarantine có trách nhiệm

### Quy trình ra quyết định

~~~mermaid
flowchart TD
    A["CI test đỏ không ổn định"] --> B["Lưu first-failure artifact"]
    B --> C{"Có invariant breach được quan sát?"}
    C -- "Có" --> P["Product defect / release risk"]
    C -- "Chưa" --> D{"Test precondition/oracle có sai?"}
    D -- "Có bằng chứng" --> T["Fix test harness + regression"]
    D -- "Chưa" --> E{"External infra có failure cụ thể?"}
    E -- "Có" --> I["Infrastructure incident"]
    E -- "Không đủ" --> U["UNCLASSIFIED, điều tra tiếp"]
    P --> G["Giữ gate phù hợp + fix causal bug"]
    T --> G
    I --> G
    U --> G
~~~

**“Rerun pass” không phải nhánh kết thúc của cây quyết định**. Nó chỉ cung cấp thêm một điểm dữ liệu và phải giữ artifact của lần fail đầu.

### Bộ thông tin cho một ticket flake có thể hành động

~~~text
classification=UNCLASSIFIED_TIMEOUT
buildCommit=...
testCase=OrderFulfillmentIT.committed_order_eventually_has_task
runId=...
orderId=...
producerOutcome=COMMITTED|UNKNOWN
publishedEvents=YES|NO|UNKNOWN
listenerStage=ENTERED|RETURNED|FAILED|UNKNOWN
consumerT2Outcome=COMMITTED|ROLLED_BACK|UNKNOWN
lastReadState=NOT_OBSERVED
lastReadSource=PRIMARY|REPLICA|UNKNOWN
publicationRegistry=PENDING|COMPLETED|UNKNOWN
firstFailureStack=artifact://...
reRunOutcome=PASS|FAIL|NOT_RUN
hypotheses=[stale_read, listener_rollback]
discriminatingExperiment=primary_fresh_read_vs_test_query
owner=...
nextAction=...
~~~

Đây là **mẫu ticket**, không phải telemetry có sẵn của mọi ứng dụng. Chỉ ghi `producerOutcome=COMMITTED` khi có evidence; không suy ra chỉ vì method return nếu một outer transaction còn mở.

### Quarantine không đồng nghĩa vô hiệu hóa lỗi thật

Quarantine có thể hợp lý cho một test **đã xác nhận lỗi fixture/hạ tầng**, có owner, ticket, hạn xử lý, artifact và một gate khác vẫn bảo vệ business invariant. Ngược lại:

- Nếu bằng chứng cho thấy mất event, duplicate shipment, dữ liệu sai hoặc transaction race, đừng tự đổi nhãn thành “test flaky” để bỏ gate release.
- Nếu chưa phân loại được, `UNCLASSIFIED` không phải bằng chứng an toàn.
- Nếu chỉ rerun để chẩn đoán, **không tự thay đổi thất bại lượt đầu thành xanh** ở quality gate.
- Giữ một deterministic regression test sau sửa bug; không để lỗi chỉ được quan sát qua 100 lượt random chạy.
- Với test phụ thuộc external sandbox bị rate-limited, phân biệt provider incident khỏi retry/idempotency contract; không xóa toàn bộ kiểm chứng.

### Phân tầng CI theo loại bằng chứng

| Gate | Rủi ro | Kiểm chứng |
| --- | --- | --- |
| Unit logic | Quy tắc và state transitions | Mock/fake deterministic, không ngủ |
| `ApplicationModules.verify()` | Cycle, sai module API/dependency | Architecture validation |
| `@ApplicationModuleTest` + `PublishedEvents` | Producer không publish/cấu trúc event sai | Event contract |
| Cross-module integration | T1 commit → listener T2 commit | Public business state, Awaitility bounded |
| Commit race Testcontainers | Consumer đọc trước commit hoặc lock/isolation | Controlled gate, READ_COMMITTED |
| Retry/replay reliability | Event pending/mất/duplicate | Persistent registry, idempotency, recovery |
| Critical E2E | Entry point và terminal outcome | HTTP/API contract, một số paths trọng yếu |

### Architecture gate không thay behavior test

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void module_dependencies_are_valid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` kiểm tra các quy tắc Spring Modulith về vòng phụ thuộc, truy cập nội bộ không qua public API và allowed dependencies khi khai báo. Nó **không** đảm bảo listener dispatch sau commit hoặc side effect đã được ghi. Giữ cả architecture và async integration gates.

Ví dụ: `fulfillment` được import public `orders.OrderPlaced`, không import `orders.internal.OrderRepository`. Một test module boundary có thể đỏ dù integration tình cờ xanh; sửa dependency sai thay vì tắt `verify()`.

### Những negative controls làm gate có ý nghĩa

- **Bỏ `publishEvent`:** Producer module test phải đỏ; consumer integration cũng không thấy task.
- **Bỏ `@ApplicationModuleListener`:** Producer test có thể xanh; cross-module test phải đỏ.
- **Thêm outer `@Transactional` sai vào integration test:** T1 chưa commit, nhận diện harness flaw thay vì tăng wait.
- **Dùng `@Async @EventListener` để đọc source trước commit:** Controlled gate phải chứng minh early visibility bug.
- **Bỏ unique/idempotency policy:** Duplicate/replay test phải phát hiện multiple effects hoặc registry error.
- **Cho query giữ stale snapshot:** Integration test phải chỉ ra read path không còn đáp ứng oracle.
- **Import `orders.internal` từ `fulfillment`:** Architecture test phải đỏ.

Các mutations trên chỉ dùng trong **nhánh thí nghiệm có chủ đích**, không để test cố tình đỏ trong pipeline chính.

## 10. Thực hành phân loại, câu hỏi kiểm tra và checklist

### Bài thực hành A — Test xanh sau rerun nhưng mất event thật

Cho listener ném exception sau T1 commit, event registry adapter giữ pending publication. Chạy test một lần thấy `NOT_OBSERVED`; bật recovery rồi rerun pass. Phải phân biệt **lượt test ban đầu thiếu completion** với **recovery policy**; xác nhận có/không có việc publication vẫn pending, và deadline nghiệp vụ có được đáp ứng không. Không kết luận “không có lỗi vì rerun xanh”.

### Bài thực hành B — Lỗi test transaction

Đặt `@Transactional` ở integration test rồi chờ `AFTER_COMMIT`. Giải thích vì sao publisher service có thể tham gia outer transaction và callback không chạy. Sửa bằng cách cho producer commit thật rồi query consumer ở transaction riêng.

### Bài thực hành C — Race trước commit có causal proof

Áp dụng `CommitWindowIT`: giữ T1 sau `saveAndFlush`/publish, đọc bằng public `OrderQueries` qua PostgreSQL READ_COMMITTED. Với listener sai `@Async @EventListener` trong test context khác, cho worker đọc khi T1 chưa commit và chụp `false`. Sửa listener phase; test sau commit chờ READY.

### Bài thực hành D — Test đọc stale state

Tạo task đã commit, nhưng dùng transaction đọc dài hoặc cache cũ khiến `statusFor` trả absent. So sánh với fresh query primary DB. Chứng minh product business state đúng mà oracle test sai; không chỉ tăng Awaitility budget.

### Bài thực hành E — Duplicate/replay

Gửi lại `OrderPlaced(id)` có kiểm soát, giữ cùng idempotency key khi gọi provider. Assert một committed task và một **distinct external effect**, quan sát event registry target/retry state. Không gọi producer-only `PublishedEvents` là bằng chứng idempotency.

### Bài thực hành F — Testcontainers/context lifecycle

Chạy full suite với context cache và container class scope. Tìm trường hợp Spring context còn cache nhưng container đã stop, hoặc test teardown `@DirtiesContext` khi listener chưa xong. Sửa scope/lifecycle; so sánh với test cô lập để định danh harness/infrastructure issue.

### Bài thực hành G — CI first-failure artifact

Cố ý tạo failure ở listener T2, thu `orderId`, producer commit, stage FAILED, exception type, registry status và last state. Rerun một lượt phục vụ chẩn đoán nhưng **giữ nguyên bằng chứng failure ban đầu** trong báo cáo.

### Bài thực hành H — Architecture cùng async

Cho consumer import `orders.internal.OrderRepository` rồi chạy `ApplicationModules.verify()`; xác nhận đỏ dù integration có thể vẫn xanh. Sửa bằng public event/query API, đồng thời giữ test race riêng.

### Câu hỏi tự đánh giá

1. “Rerun pass” có chứng minh lỗi chỉ nằm trong test không? Vì sao?
2. `PublishedEvents`, `LISTENER_ENTERED`, `LISTENER_RETURNED` và `READY` đại diện các mốc nào?
3. Vì sao `@ApplicationModuleTest` producer không tự đảm bảo consumer đã được bootstrap?
4. Outer `@Transactional` trên JUnit method có thể gây timeout giả thế nào?
5. Khi nào test đọc `NOT_OBSERVED` nhưng DB đã commit `READY`?
6. Vì sao `Thread.sleep` có thể khiến product race trở nên khó tái hiện hơn?
7. Điều kiện nào biến early read ở `@Async @EventListener` thành defect sản phẩm?
8. Vì sao `shutdownNow()` trên executor Spring từ `@AfterEach` là cách “sửa flake” nguy hiểm?
9. Vì sao listener body return không chắc transaction T2 commit?
10. Một provider nhận hai requests có nhất thiết tạo hai side effects không?
11. Khi registry pending mà `READY` đã visible, cần điều tra gì?
12. Khi nào nên dùng PostgreSQL Testcontainers thay vì repository mock?
13. `ApplicationModules.verify()` bắt nhóm lỗi nào mà Awaitility không phát hiện?
14. Quarantine có thể chấp nhận trong điều kiện nào?
15. Tại sao một test có xác suất fail thấp vẫn có thể bảo vệ critical production invariant?

### Checklist trước khi đóng ticket “flaky test”

- [ ] Đã lưu **first-failure artifact**, không chỉ kết quả rerun.
- [ ] Test có business invariant rõ và correlation `orderId` riêng.
- [ ] Đã phân biệt tình huống test oracle sai với product invariant bị phá.
- [ ] Biết T1 thật sự commit/rollback hay vẫn `UNKNOWN`.
- [ ] Producer event publication được kiểm tra độc lập với consumer.
- [ ] Biết listener được bootstrap/entered/failed hay thiếu evidence.
- [ ] Không coi listener returned là T2 committed.
- [ ] Last observed state được đọc mới trong mỗi poll.
- [ ] Không có snapshot/cache/replica làm oracle sai ngoài ý muốn.
- [ ] Không dùng `Thread.sleep` cố định để thay completion criterion.
- [ ] Không dùng `ignoreExceptions` vô điều kiện che transaction/DB error.
- [ ] Không đánh đồng timeout với worker cancellation.
- [ ] Test-owned executor/latch được cleanup theo deadline; không shutdown shared Spring executor.
- [ ] Dữ liệu/fixture `UUID` được cô lập khi suite chạy parallel.
- [ ] Spring TestContext cache và Testcontainers lifecycle không lệch.
- [ ] Các thí nghiệm có đối chứng chỉ thay một biến tại một thời điểm.
- [ ] Nếu nghi production race, có scheduling/transaction gate tái hiện causal order.
- [ ] Duplicate/replay đã được kiểm tra bằng **business effect**, không chỉ callback count.
- [ ] Registry status được đọc đúng adapter/version, không bịa retry semantics.
- [ ] Không xóa pending publication hay dữ liệu trước khi thu chẩn đoán.
- [ ] Phân loại `TEST_DEFECT`, `PRODUCT_DEFECT`, `INFRASTRUCTURE` hoặc `UNCLASSIFIED` theo bằng chứng.
- [ ] CI gate không chuyển lỗi critical thành pass chỉ nhờ rerun.
- [ ] Nếu quarantine, có owner, ticket, thời hạn và gate thay thế.
- [ ] Sau sửa lỗi có deterministic regression test và negative control.
- [ ] `ApplicationModules.verify()` và async integration vẫn nằm trong quality gate.

**Ghi nhớ:** *Flaky* mô tả kết quả test thiếu ổn định, không chứng minh lỗi “chỉ ở test”. Hãy phân biệt bằng **bất biến nghiệp vụ và bằng chứng nhân quả**: producer T1 commit, event publication, listener invocation, consumer T2 commit, public read model và registry/retry. Sửa phép thử khi oracle/fixture sai; sửa sản phẩm khi một lịch thực thi hợp lệ phá invariant. Giữ bằng chứng lần fail đầu, dùng deterministic scheduling để tái hiện, và để CI tiếp tục bảo vệ cả ranh giới Spring Modulith lẫn hành vi bất đồng bộ.





