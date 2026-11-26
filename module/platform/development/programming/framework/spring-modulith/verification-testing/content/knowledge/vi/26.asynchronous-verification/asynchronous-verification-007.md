# Hủy hoặc dọn tác vụ khi test thất bại

> **Chương:** Async verification  
> **Module đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Thiết kế hủy và dọn dẹp có kiểm soát khi kiểm thử bất đồng bộ thất bại; phân biệt tác vụ do test trực tiếp sở hữu với listener Spring Modulith được hệ thống quản lý, kết hợp transaction, database, event registry và CI.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **cancel**, **interrupt**, **shutdown**, **quiescence**, **cleanup**, **rollback** và **compensation**.
2. Xác định tác vụ nào **thuộc quyền sở hữu của test** để yêu cầu hủy, tác vụ nào thuộc event infrastructure nên chờ, quan sát hoặc cô lập.
3. Giải thích vì sao `Awaitility.atMost(...)`, `JUnit @Timeout` và HTTP client timeout **không tự hủy** listener/background job.
4. Sử dụng `ExecutorService`, `Future.cancel(true)`, `CountDownLatch` và `awaitTermination(...)` trong kiểm thử có task do test sở hữu.
5. Hiểu giới hạn khác biệt của `CompletableFuture.cancel(...)`, interruption và transaction đã commit.
6. Viết `@ApplicationModuleTest` kiểm tra event producer và integration test xác minh listener sau commit qua public API consumer.
7. Thiết kế `@AfterEach`/`finally` an toàn khi assertion fail, không làm mất lỗi gốc hoặc xóa dữ liệu khi worker đang chạy.
8. Kiểm chứng failure injection, retry, duplicate delivery, Testcontainers lifecycle và event publication registry.
9. Bảo vệ ranh giới module bằng `ApplicationModules.verify()`, kết hợp quality gate CI để ngăn hồi quy.

**Nguyên tắc:** Khi test fail, không mặc định “dừng tất cả thread và xóa hết dữ liệu”. Trước hết hỏi **ai sở hữu task, side effect nào đã commit, có thể hủy ở đâu, và có bằng chứng worker đã dừng trước cleanup chưa?**

## 2. Tại sao test thất bại chưa chắc tác vụ nền đã dừng?

Giả sử module `orders` tạo order và publish `OrderPlaced`; module `fulfillment` nhận event sau commit để tạo task.

~~~mermaid
sequenceDiagram
    participant T as JUnit test thread
    participant O as orders
    participant E as Spring Event dispatcher
    participant W as fulfillment worker
    participant DB as Database
    participant C as Cleanup

    T->>O: place(customerId)
    O->>E: publish OrderPlaced
    O-->>T: orderId, producer T1 commit
    E-->>W: listener được schedule
    T->>T: Await READY
    W->>DB: Đang xử lý trong T2
    T-->>T: Timeout sau 5 giây
    T->>C: @AfterEach cleanup
    C->>DB: Xóa fixture
    W->>DB: Commit hoặc retry sau cleanup
~~~

Khi Awaitility timeout:

~~~java
UUID id = orders.place("CUS-001");

await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
                assertThat(fulfillment.hasTask(id)).isTrue());
~~~

test **chỉ biết** chưa quan sát được task trong thời hạn năm giây. Nó không chứng minh listener đã ngừng chạy, event đã bị hủy hoặc transaction consumer bị rollback.

Những khả năng thường gặp:

- Worker còn trong executor queue, chưa bắt đầu.
- Worker đang chờ DB connection/lock hoặc làm external API call.
- Worker vừa ném exception; publication vẫn pending để resubmit.
- Consumer đã commit nhưng query test đọc stale snapshot.
- Test cleanup xóa order, worker chạy muộn rồi lỗi hoặc tái tạo dữ liệu.
- Test sau dùng chung context/DB và nhìn thấy side effect của test trước.

**Deadline của phép quan sát không phải tín hiệu cancellation.** Đây là điểm khác biệt quan trọng nhất của bài học.

## 3. Bảng khái niệm: hủy và dọn không đồng nghĩa

| Khái niệm | Ý nghĩa | Không bảo đảm |
| --- | --- | --- |
| Cancellation request | Yêu cầu task ngừng | Worker chấp nhận và ngừng ngay |
| Thread interruption | Đặt interrupt flag, có thể đánh thức blocking operation | Cưỡng bức dừng mọi I/O |
| `ExecutorService.shutdown()` | Không nhận thêm task, để task hiện có xử lý theo cơ chế | Tất cả task đã kết thúc |
| `ExecutorService.shutdownNow()` | Cố gắng interrupt task đang chạy, trả task chưa bắt đầu | Task đã dừng hoàn toàn |
| `Future.cancel(true)` | Cố gắng hủy future và interrupt worker tùy implementation | Transaction/side effect được rollback |
| Quiescence | Không còn công việc liên quan có thể ghi thêm | Có được chỉ vì một event được publish |
| Cleanup | Giải phóng tài nguyên/fixture test | Đảo tác động đã commit ngoài transaction |
| Rollback | Hủy thay đổi của **một** transaction chưa commit | Đảo transaction đã commit trước đó |
| Compensation | Hành động nghiệp vụ để bù một side effect đã commit | Rollback nguyên tử mọi hệ thống |
| Test timeout | Hết thời hạn quan sát | Worker tự bị hủy |

Có ít nhất ba mệnh đề phải chứng minh riêng:

1. **Đã yêu cầu hủy** (`cancel` được gọi).
2. **Đã xác nhận dừng** (worker/pool kết thúc thật).
3. **Đã dọn an toàn** (không xóa nhầm dữ liệu hoặc để late writes).

Một test chỉ assert `future.isCancelled()` không chứng minh đủ mệnh đề 2 và 3.

## 4. Phân loại ownership trước khi đụng vào worker

| Đối tượng | Chủ sở hữu | Chính sách khi test fail |
| --- | --- | --- |
| `ExecutorService` do test khởi tạo | Test | Cancel, shutdown, await termination hữu hạn |
| `Future` của `executor.submit(...)` do test gọi | Test | Cancel khi an toàn, kiểm chứng worker kết thúc |
| `CountDownLatch`/controlled gateway của fixture | Test | Release trong `finally`, không để deadlock |
| `@ApplicationModuleListener` do Spring quản lý | Application infrastructure | Chờ outcome, quan sát failure, cô lập dữ liệu; không shutdown global executor |
| Persistent Event Publication Registry | Application infrastructure | Bảo toàn pending/recovery theo policy |
| Testcontainers riêng cho test | Fixture/suite | Quản lý vòng đời sau quiescence hoặc dispose môi trường cô lập |
| Database/schema dùng chung | Suite/hạ tầng | Tránh `deleteAll()` khi có worker/test khác |
| External sandbox service | Provider/contract bên ngoài | Dùng idempotency và compensation nếu có |
| HTTP request đã được server chấp nhận | Client + server | Client cancel không tự cancel server operation |

### Quy tắc sở hữu

**Chỉ chủ động hủy khi test có handle hợp lệ và cancellation protocol phù hợp.** Nếu một event `OrderPlaced` đã commit là nghiệp vụ hợp lệ, việc test timeout không cho phép “xóa tất cả pending publications” để tránh cleanup.

Với Spring Modulith, thường cần **cô lập tài nguyên** bằng `orderId`/test run ID, **chờ business state**, **quan sát registry/retry**. Với test-owned executor, có thể cancel và chờ termination một cách xác định.

## 5. Mẫu failure protocol cho một test bất đồng bộ

~~~mermaid
flowchart TD
    A["Kích hoạt tác vụ"] --> B["Await completion criterion"]
    B --> C{"Outcome đã biết?"}
    C -- "READY" --> P["Assertion pass"]
    C -- "FAILED terminal" --> F["Assertion fail + reason"]
    C -- "Hết deadline" --> T["Timeout/unknown"]
    P --> D["Cleanup bình thường"]
    F --> R["Failure handling"]
    T --> R
    R --> O{"Test sở hữu cancellation handle?"}
    O -- "Có" --> X["Request cancel và chờ termination"]
    O -- "Không" --> I["Không kill global listener"]
    X --> Q["Xác minh quiescence"]
    I --> Q
    Q --> S{"Cleanup an toàn?"}
    S -- "Có" --> D
    S -- "Không" --> Z["Lưu diagnostic, cô lập môi trường,<br/>không destructive cleanup"]
~~~

Thứ tự thực dụng:

1. Trigger bằng fixture riêng có correlation ID.
2. Chờ outcome bắt buộc với deadline.
3. Nếu fail, **ghi lại trạng thái cuối trước cleanup**.
4. Xác định task nào do test sở hữu và có thể cancel.
5. Với owned task: gửi cancel, chờ worker ngừng với deadline.
6. Với Spring-managed event: không hủy bừa bãi, quan sát pending/retry/terminal state.
7. Chỉ xóa fixture khi không còn late writer hoặc test environment được dispose cô lập.
8. Nếu cleanup fail, **báo failure**, không nuốt exception.

**Không viết vòng lặp cleanup vô hạn**. Một teardown treo sẽ làm CI khó chẩn đoán hơn nhiều so với một lỗi timeout rõ ràng.

## 6. Future.cancel(true) chỉ gửi yêu cầu hủy

Java `Future.cancel(true)` cố gắng interrupt thread thực thi, tùy implementation và trạng thái task:

~~~java
boolean cancellationRequested = future.cancel(true);
~~~

Giá trị `true` không tự chứng minh underlying worker đã dừng hoặc mọi side effect đã rollback. Worker cần có điểm hợp tác:

- Kiểm tra `Thread.currentThread().isInterrupted()` trong vòng lặp tính toán dài.
- Dùng blocking calls hỗ trợ `InterruptedException` khi phù hợp.
- Không nuốt interruption rồi tiếp tục chạy mãi.
- Giải phóng tài nguyên trong `finally`.
- Có tín hiệu worker **exited**, không chỉ future cancelled.
- Giữ transaction/commit boundary an toàn với side effects.

### Phản mẫu nuốt InterruptedException

~~~java
while (true) {
    try {
        Thread.sleep(100);
        processNextItem();
    } catch (InterruptedException ignored) {
        // Sai: worker phớt lờ yêu cầu dừng.
    }
}
~~~

Nếu task bỏ qua interrupt, `shutdownNow()` có thể không làm pool terminate. Test phải báo lỗi cleanup, không gọi `Thread.stop()` hoặc đánh dấu dọn thành công.

### Worker test-owned có finally signal

~~~java
final class BlockingWorker implements Callable<Void> {

    final CountDownLatch entered = new CountDownLatch(1);
    final CountDownLatch exited = new CountDownLatch(1);

    @Override
    public Void call() throws InterruptedException {
        entered.countDown();

        try {
            // Test-only: chờ đến khi bị interrupt.
            new CountDownLatch(1).await();
            return null;
        } finally {
            exited.countDown();
        }
    }
}
~~~

Đây là **fixture thử cancellation**, không phải pattern để production worker chờ một latch không bao giờ mở.

## 7. Test thực hành đầy đủ: cancel owned worker và awaitTermination

**`src/test/java/com/example/shop/testing/OwnedWorkerCleanupTest.java`**

~~~java
package com.example.shop.testing;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class OwnedWorkerCleanupTest {

    private ExecutorService executor;
    private Future<Void> future;
    private BlockingWorker worker;

    @BeforeEach
    void start() {
        executor = Executors.newSingleThreadExecutor();
        worker = new BlockingWorker();
        future = executor.submit(worker);
    }

    @Test
    void owns_a_worker_that_teardown_can_stop()
            throws InterruptedException {

        assertThat(worker.entered.await(2, TimeUnit.SECONDS))
                .isTrue();

        // Nếu một assertion tiếp theo fail,
        // @AfterEach vẫn xử lý resource mà test sở hữu.
    }

    @AfterEach
    void cleanup() throws InterruptedException {
        if (future != null) {
            future.cancel(true); // Yêu cầu hủy.
        }

        if (executor != null) {
            executor.shutdownNow(); // Chỉ owned executor.
            assertThat(executor.awaitTermination(
                    3, TimeUnit.SECONDS))
                    .as("Owned worker must terminate")
                    .isTrue();
        }

        if (worker != null
                && worker.entered.getCount() == 0L) {
            assertThat(worker.exited.getCount())
                    .as("Started worker must leave finally")
                    .isZero();
        }
    }

    static final class BlockingWorker implements Callable<Void> {

        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch exited = new CountDownLatch(1);

        @Override
        public Void call() throws InterruptedException {
            entered.countDown();

            try {
                new CountDownLatch(1).await();
                return null;
            } finally {
                exited.countDown();
            }
        }
    }
}
~~~

### Vì sao thiết kế này an toàn hơn?

- Executor được tạo **cho một test**, không phải bean executor Spring-wide.
- Worker hợp tác với interruption vì `CountDownLatch.await()` ném `InterruptedException`.
- `@AfterEach` có null guards khi setup fail một phần.
- `awaitTermination(3s)` mới là bằng chứng pool thực sự dừng.
- `exited` xác nhận `finally` chạy nếu worker đã bắt đầu.

**Lưu ý:** `future.cancel(true)` có thể được gọi trước khi task bắt đầu; khi ấy `entered` và `exited` chưa chắc mở. Ví dụ chỉ kiểm tra `exited` khi worker từng `entered`. Nếu worker bị block trong I/O không interruptible, `awaitTermination` có thể trả false và bài test phải fail.

**Cấm áp dụng máy móc `shutdownNow()` lên `TaskExecutor` chung của Spring application**: bạn có thể hủy task của nhiều module hoặc test khác.

## 8. CompletableFuture.cancel không đồng nghĩa interrupt task gốc

~~~java
CompletableFuture<Void> future =
        CompletableFuture.runAsync(() -> performWork());

future.cancel(true);
~~~

Với `CompletableFuture`, tham số `mayInterruptIfRunning` **không được dùng để điều khiển interruption như cách `FutureTask` có thể làm**; cancellation chủ yếu là trạng thái completion exception. Underlying computation có thể tiếp tục chạy.

| API | Có thể yêu cầu interrupt worker? | Chứng minh worker đã kết thúc? |
| --- | --- | --- |
| `FutureTask.cancel(true)` | Có thể | Không |
| `CompletableFuture.cancel(true)` | Không nên dựa vào `true` để interrupt | Không |
| `Thread.interrupt()` | Có | Không |
| `ExecutorService.shutdownNow()` | Thử interrupt | Không |
| `ExecutorService.awaitTermination(...)` | Đợi executor kết thúc | Có thể xác minh theo deadline |
| Public business state terminal | Không điều khiển thread | Xác minh nghiệp vụ, không nhất thiết pool idle |

Nếu `CompletableFuture` dùng cho business operation, hãy thiết kế cooperative cancellation token hoặc cancellation API riêng, và tách tín hiệu “completion bị hủy” khỏi bằng chứng **worker thực sự quiescent**.

Ví dụ token:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

final class StopToken {

    private final AtomicBoolean stopRequested =
            new AtomicBoolean();

    void requestStop() {
        stopRequested.set(true);
    }

    boolean shouldStop() {
        return stopRequested.get()
                || Thread.currentThread().isInterrupted();
    }
}
~~~

Token chỉ có ích nếu worker kiểm tra nó **ở điểm an toàn** và không ghi side effect trái contract sau khi chấp nhận hủy.

## 9. Cancellation không rollback side effect đã commit

Giả sử một worker thực hiện:

~~~text
BEGIN T2
  INSERT fulfillment_task
COMMIT T2
POST external shipping API
Wait for provider response...
~~~

Nếu test yêu cầu cancel **sau COMMIT T2**:

- Row task đã commit **không tự biến mất**.
- Provider có thể đã nhận request dù HTTP client bị interrupt.
- Retry sau cancellation có thể tạo side effect trùng nếu không có idempotency.
- Outer `@Transactional` ở test thread không rollback transaction T2 của worker thread.

| Mốc cancel | Điều cần cân nhắc |
| --- | --- |
| Trước khi task được schedule | Có thể hủy task chưa chạy |
| Khi worker đang trong T2 | Cần bảo đảm transaction rollback hoặc trạng thái nhất quán |
| Sau T2 commit | Có thể cần cleanup dữ liệu test hoặc compensation |
| Sau external request | Phải theo dõi receipt/cancellation contract của provider |
| Trong retry wait | Publication có thể pending và được giao lại |

**Cleanup** là quản lý fixture/tài nguyên test. **Compensation** là một hành động nghiệp vụ đảo side effect đã commit (ví dụ hủy nhãn vận chuyển sandbox) và có thể thất bại; nó không phải database rollback.

## 10. Không lạm dụng cancellation lên Spring Modulith listener

Một lệnh tạo order có thể là nghiệp vụ hợp lệ đã commit, kể cả khi integration test hết deadline. `@ApplicationModuleListener` không tự trả một `Future` trực tiếp cho `orders.place(...)`; test không có quyền gọi `cancel(true)` đối với riêng callback ấy nếu application không cung cấp cancellation protocol.

Thay vì shutdown global executor:

1. Chờ consumer outcome hoặc state terminal theo `orderId`.
2. Ghi lại listener error, DB state, publication pending/retry nếu có.
3. Dùng fixture/namespace riêng, không xóa shared tables.
4. Giữ pending publication cho recovery test khi cần.
5. Nếu side effect đã commit, dùng cleanup/compensation theo contract.
6. Nếu cần shutdown behavior, viết **một bài test lifecycle riêng** sở hữu context/executor tương ứng.

**Không tạo “cancel all listeners” chỉ để CI xanh**. Hành động đó có thể làm mất công việc nghiệp vụ hoặc phá bài test khác dùng cùng application context.

## 11. Spring Modulith case study: orders → fulfillment

Cấu trúc ví dụ:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderCommands.java
│   ├── OrderPlaced.java
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/
    ├── FulfillmentQueries.java
    ├── PreparationState.java
    └── internal/
        ├── OrderPlacedListener.java
        ├── FulfillmentQueryService.java
        └── persistence/
            ├── FulfillmentTask.java
            └── FulfillmentTaskRepository.java
~~~

Theo cách nhận diện module mặc định, hai package trực tiếp dưới `com.example.shop` là application modules. Public event `OrderPlaced` nằm trong root package của `orders`; implementation JPA ở `internal` không nên bị module khác truy cập.

**Completion criterion:** Consumer đã tạo fulfillment task cho đúng order, T2 commit và public query trả `READY`. Điều này chưa hứa một external shipping job đã hoàn tất.

## 12. Mã Java của producer và event contract

### Application entry point

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

### Public commands và event

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

### JPA source entity

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

### Service publish event trong T1

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
            throw new IllegalArgumentException("Invalid customerId");
        }

        var saved = orders.save(new OrderEntity(customerId));
        UUID id = saved.getId();
        publisher.publishEvent(new OrderPlaced(id));
        return id;
    }
}
~~~

`publishEvent(...)` xảy ra trong transaction T1. Khi gọi qua Spring transaction proxy mà không có transaction bên ngoài, commit của T1 được xử lý trước khi lời gọi hoàn tất thành công. **Không đồng nghĩa consumer T2 đã commit**.
## 13. Consumer Spring Modulith và side effect ở transaction T2

### Public query API

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

`NOT_OBSERVED` chỉ có nghĩa chưa nhìn thấy task; không tự xác định worker đang xử lý, thất bại terminal hay event đã mất.

### JPA task và repository

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

### Listener xử lý sau commit

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

`@ApplicationModuleListener` thường kết hợp listener hậu commit, async và transaction mới theo Spring Modulith version/config tương thích. Đây là **application-managed listener**, không phải future mà test trực tiếp sở hữu. Việc gọi `tasks.save(...)` chưa chứng minh T2 đã commit; JPA flush/constraint có thể fail sau đó.

**Giới hạn happy path:** `existsById` rồi `save` chưa an toàn tuyệt đối trước duplicate delivery đồng thời. Một invocation có thể vướng unique constraint và để publication pending.

### Query service nhìn state đã commit

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

Query consumer qua public module API giúp test xác nhận dữ liệu đã visible mà không import repository trong `fulfillment.internal`.

## 14. Producer module test không thay thế consumer completion

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
    void publishes_order_event(PublishedEvents events) {
        var id = orders.place("CUS-PUBLISH");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }

    @Test
    void invalid_customer_does_not_publish(PublishedEvents events) {
        assertThatThrownBy(() -> orders.place(" "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderPlaced.class)).isEmpty();
    }
}
~~~

`PublishedEvents` chỉ chứng minh producer đã phát event trong test; **chưa** chứng minh T1 commit ở thời điểm event được quan sát, listener đã chạy, T2 commit hoặc publication sống qua restart. `anySatisfy` chỉ đòi ít nhất một event khớp, không chứng minh exactly one.

Không thêm code tắt listener vào teardown producer-only test: consumer có thể không được bootstrap trong `@ApplicationModuleTest`. Muốn kiểm tra việc consumer xử lý và failure path, hãy dùng integration test thật.

## 15. Cross-module integration: chờ business outcome

**`src/test/java/com/example/shop/OrderFulfillmentIntegrationTest.java`**

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
class OrderFulfillmentIntegrationTest {

    @Autowired
    OrderCommands orders;

    @Autowired
    FulfillmentQueries fulfillment;

    @Test
    void awaits_consumer_commit_before_return() {
        UUID id = orders.place("CUS-" + UUID.randomUUID());

        await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() ->
                        assertThat(fulfillment.statusFor(id))
                                .isEqualTo(PreparationState.READY));
    }
}
~~~

### Khi assertion pass

Test đã quan sát task của đúng `orderId` sau commit. Không cần cancel listener; nghiệp vụ được yêu cầu đã hoàn thành. Tuy nhiên, READY không tự chứng minh không còn retry/duplicate publication hay external job đang chạy.

### Khi assertion timeout

- **Không tự gọi `shutdownNow()` lên Spring global executor.**
- Lưu ID, trạng thái cuối, listener errors và pending publication nếu có.
- Không xóa cả bảng trong database chung vì worker còn có thể chạy.
- Phân biệt chưa đủ thời gian với lỗi logic, transaction rollback hoặc stale read.
- Nếu cần cleanup, dùng fixture isolation hoặc một protocol cho quiescence được ứng dụng hỗ trợ.

### Không bọc test trong outer @Transactional

Nếu method test được `@Transactional` bao ngoài, `orders.place(...)` với propagation `REQUIRED` có thể tham gia transaction test và bị rollback khi test kết thúc. Listener `AFTER_COMMIT` khi ấy không chạy, dẫn tới timeout sai mục tiêu. Để service tự commit T1; dọn dữ liệu bằng chiến lược độc lập.

## 16. @AfterEach có thể xóa fixture trước khi worker hoàn tất

Một anti-pattern:

~~~java
@Test
void bad_test() {
    orders.place("CUS-CLEANUP");
    // Return ngay, listener chưa chắc xong.
}

@AfterEach
void cleanup() {
    fixture.deleteAllOrders();
    // Có thể xóa source khi listener còn đọc.
}
~~~

JUnit chạy `@AfterEach` sau test method, **không đợi mọi task Spring executor đã hoàn tất**.

### Quy tắc failure-aware cleanup

1. Lưu danh sách `orderId` do test tạo, không xóa dữ liệu ngoài scope.
2. Chờ completion criterion **trong test method** khi đó là claim đang kiểm tra.
3. Nếu fail, chụp diagnostics **trước destructive cleanup**.
4. Với test-owned task, cancel + await termination có deadline.
5. Với application event, không kill global listener; giữ isolated fixture/DB.
6. Không xóa publication pending nếu test/recovery còn phụ thuộc.
7. Cleanup idempotent, chạy được khi setup mới thành công một phần.
8. Báo cleanup failure, không ignore exception.
9. Không dùng `Thread.sleep` để đoán đã hết late writers.

### Pseudocode khi có workflow status và worker tracker

~~~java
// Pseudocode: các API workflow/tracker/fixture do dự án
// thiết kế, không có sẵn trong Spring Modulith.
@AfterEach
void cleanupOrders() {
    for (UUID id : testOwnedOrderIds) {
        var state = workflow.status(id);

        if (state.isTerminal() && tracker.isQuiescent(id)) {
            fixture.deleteByOrderId(id);
        } else {
            diagnostics.capture(id, state);
            // Không destructive cleanup khi late write còn có thể.
        }
    }
}
~~~

**Không copy chạy ngay:** `workflow`, `tracker`, `fixture` và `diagnostics` là test hooks. `isQuiescent` cần bằng chứng theo consumer/executor/registry thực, không suy ra từ một sleep cố định.

## 17. Khi cleanup cũng lỗi: đừng che assertion gốc

~~~text
TEST FAILURE:
    Expected READY but saw NOT_OBSERVED after 10 s

CLEANUP FAILURE:
    Owned executor did not terminate after 3 s
~~~

Hai lỗi đều có giá trị. Nếu teardown dùng `catch(Exception ignored)`, resource leak bị che. Nếu `finally` ném lỗi mới và mất stack trace đầu, chẩn đoán cũng khó.

Hướng triển khai:

- Assertion business ở test body.
- Cleanup owned resources ở `@AfterEach`/`finally` phù hợp.
- Khi termination không đạt, ném assertion rõ tên resource/deadline.
- Lưu `orderId`, last state, listener exception và retry status.
- Để JUnit hiển thị cả assertion và lifecycle failures; nếu bắt lỗi thủ công thì giữ root cause (ví dụ `addSuppressed`).
- Không dùng `System.exit`, `Thread.stop` hoặc vô hạn retry trong cleanup.

### Dữ liệu diagnostic gợi ý

~~~text
testName=OrderFulfillmentIntegrationTest
testRunId=...
orderId=...
producerTransaction=COMMITTED
consumerState=NOT_OBSERVED
listenerStarted=UNKNOWN/YES/NO
lastListenerFailure=...
publicationState=PENDING/COMPLETED/UNKNOWN
ownedExecutorTerminated=N/A
cleanupAction=SKIPPED_NOT_QUIESCENT
elapsedWaitMs=...
~~~

Những field này là **mẫu instrumentation**, không phải log Spring Modulith tự sinh nguyên dạng. Không log thông tin nhạy cảm không cần thiết.

## 18. @DirtiesContext và shutdown Spring không phải cancel API

Spring TestContext có thể cache application context. Một test method return không nhất thiết làm context close ngay; nhưng `@DirtiesContext`, kết thúc suite hoặc shutdown explicit có thể bắt đầu đóng executor/bean.

~~~text
Test fails/returns
   -> @DirtiesContext hoặc shutdown
   -> executor/DataSource/EntityManagerFactory đóng
   -> listener vẫn còn chạy
   -> DB connection hoặc bean bị đóng
   -> exception tới sau kết quả test
~~~

`@DirtiesContext` có ích khi context state thực sự không thể tái sử dụng, **không phải nút cancel listener**.

Cần xem:

- Worker còn active/queued khi context close không?
- `ThreadPoolTaskExecutor` có shutdown/wait policy nào theo version?
- Có pending publications sẽ retry khi context mới start không?
- TestContext cache có trỏ tới container đã dừng không?
- Ngưỡng await termination có hữu hạn không?

Tách **business completion test** (đợi READY) khỏi **shutdown semantics test** (sở hữu và đóng context/executor). Không trộn hai mục tiêu rồi tăng timeout khi fixture lifecycle sai.

## 19. Testcontainers: worker không được ghi vào DB đã đóng

~~~mermaid
sequenceDiagram
    participant T as Test
    participant W as Listener
    participant DB as PostgreSQL Testcontainer
    participant TD as Teardown

    T->>W: Trigger event
    T-->>T: Timeout
    T->>TD: End class
    TD->>DB: Stop
    W->>DB: INSERT / COMMIT
    DB-->>W: Connection closed
~~~

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
class FulfillmentPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Inject OrderCommands và FulfillmentQueries.
    // Test await business READY với database production-like.
}
~~~

Đây là khung, chưa có test method; cần Testcontainers Jupiter/PostgreSQL, Spring Boot Testcontainers, JDBC driver và runtime. `@ServiceConnection` hỗ trợ từ Spring Boot 3.1+, cần version tương thích.

**Lưu ý lifecycle:**

- Container startup và business await có budget riêng.
- Spring TestContext cache và Testcontainers lifecycle không tự đồng bộ.
- Nếu context còn cache nhưng container của class trước đã stop, DB connection sẽ fail.
- Recovery test cần persistent storage sống qua restart/resubmit.
- Với DB dùng chung, không stop container khi test khác còn sử dụng.
- Dùng migration thật ở integration test quan trọng nếu production sử dụng Flyway/Liquibase.

Không tăng Awaitility để che container/schema lỗi. Nếu worker không dừng, báo failure và xử lý test environment cô lập đúng policy.

## 20. Event Publication Registry: pending không phải rác để xóa

Khi Spring Modulith Event Publication Registry được cấu hình với adapter lưu trữ, publications có thể được theo dõi theo trạng thái chưa xử lý/đã xử lý.

~~~text
T1 commit OrderPlaced
   -> publication được theo dõi
   -> consumer T2 lỗi
   -> publication có thể pending
   -> test timeout
   -> @AfterEach xóa publication
   -> mất bằng chứng cần phục hồi
~~~

Xóa pending publication để “làm sạch DB” có thể làm reliability test vô nghĩa. Trong production, đó còn có thể là mất công việc nghiệp vụ.

| Quan sát | Điều được biết | Điều chưa được biết |
| --- | --- | --- |
| `PublishedEvents` có event | Producer đã publish | Consumer đã chạy |
| Registry pending | Theo registry, publication chưa hoàn tất | Business chắc đã FAILED terminal |
| Registry completed | Listener xử lý thành công theo semantics registry | External job cuối đã hoàn tất |
| Task READY | Side effect đã được ghi và đọc | Mọi duplicate/retry đã quiescent |
| Test timeout | Outcome chưa được quan sát đúng hạn | Worker đã bị hủy |

Nếu yêu cầu là event sống qua restart, test phải giữ registry/storage, inject lỗi, quan sát pending, resubmit/restart theo adapter và chờ kết quả cuối. **Không mặc định có retry vô hạn hay exactly-once** chỉ vì `@ApplicationModuleListener`.

## 21. Replay/duplicate có thể tạo lại task sau cleanup

~~~text
Attempt A -> INSERT task -> COMMIT
Test thấy READY -> cleanup DELETE task
Attempt B retry -> INSERT task lại
Test tiếp theo thấy dữ liệu "ma"
~~~

Handler mẫu `existsById` rồi `save` có race nếu hai invocation đồng thời đều thấy chưa tồn tại. Primary key có thể ngăn hai row nhưng một invocation vẫn ném unique violation và publication pending.

Để bảo vệ reliability, tách test:

- Giao lại event tuần tự không tạo effect trùng.
- Giao trùng đồng thời không gây retry vô hạn.
- Event cũ không làm state đi lùi nếu có revision.
- Recovery sau failure không nhân đôi side effect.
- Registry/retry state đạt policy phù hợp.

Một test quan sát `READY` **không tự chứng minh** không còn late retry. Cần quiescence tracking hoặc fixture isolation khi muốn xóa dữ liệu.

## 22. HTTP client cancel không làm server tự dừng

~~~text
POST /api/orders -> 202 Accepted + orderId
GET /api/orders/{id}/status -> PROCESSING
Client timeout/cancel
Server vẫn có thể chạy listener và commit T2
~~~

Việc client đóng request không chứng minh server đã cancel operation. Nếu business hỗ trợ cancellation, phải có API và state riêng, ví dụ:

~~~http
POST /api/orders/{id}/cancel
202 Accepted
{"orderId":"...", "state":"CANCELLATION_REQUESTED"}
~~~

~~~http
GET /api/orders/{id}/status
200 OK
{"orderId":"...", "state":"CANCELLED"}
~~~

Đây là API giả định, không phải endpoint Spring Modulith tự có. Server phải thiết kế cancellation, idempotency và compensation cho side effect đã commit; test phải chờ `CANCELLED` terminal thay vì coi `202` là đã hủy.

Không gọi business cancellation chỉ để dọn một test đang chứng minh task READY, vì sẽ làm thay đổi chính nghiệp vụ cần kiểm chứng.
## 23. Failure injection: chứng minh cả đường cleanup khi assertion thất bại

Một test cancellation đáng tin cần **negative control** cho failure path, không chỉ happy path.

### Thí nghiệm A — Test-owned worker

Với `OwnedWorkerCleanupTest` ở mục 7:

1. Cho worker bắt đầu và mở `entered`.
2. Trong nhánh thực hành, thêm một assertion sai có chủ đích trong method test.
3. Xác nhận `@AfterEach` vẫn gọi `future.cancel(true)`.
4. Xác nhận `executor.awaitTermination(...)` thành công.
5. Nếu worker đã bắt đầu, `exited` phải được count down.
6. Hoàn nguyên assertion sai trước khi chạy CI bình thường.

Kết quả quan trọng là **cleanup vẫn chạy khi assertion đỏ**, không phải cố tạo một test luôn thất bại trong nhánh chính.

### Thí nghiệm B — Consumer listener lỗi sau commit

1. Tạo một port test-only trong consumer có thể ném exception ở lần xử lý đầu.
2. Producer `orders.place(...)` vẫn commit T1 và publish event.
3. Consumer có thể rollback T2, không tạo task READY.
4. Integration test phải fail với terminal FAILED hoặc timeout có giới hạn.
5. Chụp listener failure và registry pending nếu có.
6. Nếu test về recovery, gỡ lỗi rồi resubmit theo adapter và chờ task xuất hiện.
7. Không xóa pending publication trước khi quan sát recovery.

**Không mock toàn bộ listener** rồi tuyên bố đã kiểm tra transaction, retry hay cleanup. Cần listener và infrastructure thực cho claim tích hợp.

### Thí nghiệm C — Worker không hợp tác interrupt

Trong một môi trường test cô lập, cố tình cho test-owned worker nuốt interruption. `awaitTermination` sẽ có thể trả false. Test phải báo cleanup failure và có outer time budget để không giữ CI vô hạn.

**Không dùng `Thread.stop()` làm cách xử lý.** Sửa worker để phản hồi interrupt/cancellation token ở các điểm nhất quán.

## 24. try/finally với test-controlled gateway

Nếu test dùng latch để chặn listener trước khi ghi DB, cần release dù assertion thất bại:

~~~java
// Pseudocode: gate là test fixture được wire vào listener
// qua một test-only port.
gate.pauseNextCall();

UUID id = orders.place("CUS-GATED");

try {
    assertThat(gate.awaitEntered(Duration.ofSeconds(5)))
            .isTrue();

    // Handler đã bắt đầu nhưng đang chặn trước DB write.
    assertThat(fulfillment.statusFor(id))
            .isEqualTo(PreparationState.NOT_OBSERVED);
} finally {
    gate.release();
}

await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(fulfillment.statusFor(id))
                        .isEqualTo(PreparationState.READY));
~~~

Ví dụ chỉ minh họa control flow; cần thực thi `gate` và đưa nó vào listener bằng dependency injection. **Barrier `entered` chỉ chứng minh listener đến gateway**, còn Awaitility sau release mới chứng minh task đã commit.

### Tránh tự tạo deadlock

Sai thứ tự:

~~~text
1. Gate chặn consumer trước khi save.
2. Test await READY.
3. Test chỉ release gate sau khi await kết thúc.
4. Await timeout vì consumer đang bị test chặn.
~~~

Đúng thứ tự: chờ `entered` → assert state trung gian → release trong `finally` → chờ business outcome.

Không giữ mutex/lock của test trong khi await nếu worker phải lấy cùng lock để mở latch hoặc commit.

## 25. Negative assertion: không thấy task lúc này chưa chứng minh hủy thành công

Một test yếu:

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> fulfillment.statusFor(id)
                == PreparationState.NOT_OBSERVED);
~~~

Predicate có thể true **ngay lập tức** khi consumer chưa được schedule. Sau đó worker vẫn có thể ghi task, khiến test âm pass giả.

Để xác minh *không có side effect từ transaction producer rollback*:

1. Chứng minh producer T1 thật sự rollback bằng nguồn dữ liệu orders.
2. Kiểm tra listener `AFTER_COMMIT` và fallback policy.
3. Dùng event/worker synchronization khi cần để biết đã qua mốc xử lý.
4. Nếu contract chỉ là “không xảy ra trong X thời gian”, ghi rõ observation window.
5. Không gọi một cửa sổ hữu hạn là “không bao giờ”.

Awaitility có `during(Duration)` ở các version hỗ trợ, ví dụ:

~~~java
await()
        .during(Duration.ofMillis(500))
        .atMost(Duration.ofSeconds(2))
        .until(() -> fulfillment.statusFor(id)
                == PreparationState.NOT_OBSERVED);
~~~

Điều này chỉ bảo vệ **absence trong cửa sổ 500 ms**; nó không chứng minh mọi publication đã được drain hoặc sẽ không có retry sau đó.

### Rollback được điều khiển bằng TransactionTemplate

~~~java
@Autowired
TransactionTemplate transactions;

@Test
void rolls_back_after_publication() {
    UUID id = transactions.execute(status -> {
        UUID created = orders.place("CUS-ROLLBACK");
        status.setRollbackOnly();
        return created;
    });

    assertThat(id).isNotNull();

    // Thêm public source query/test fixture để xác nhận
    // order không commit; phép kiểm tra consumer là bước riêng.
}
~~~

Đây là **trích đoạn trigger rollback**, chưa phải test đầy đủ về absence. Không gắn `@Transactional` outer test vào bài happy-path AFTER_COMMIT rồi chờ READY, vì transaction test thường rollback và ngăn listener hoạt động.

## 26. Parallel tests, fixture isolation và late writes

Khi nhiều test chia sẻ H2, PostgreSQL schema hoặc Spring application context, một cleanup sai có thể ảnh hưởng test khác.

| Tình huống | Rủi ro | Biện pháp |
| --- | --- | --- |
| Nhiều test dùng cùng ID cố định | Không biết task thuộc test nào | Dùng UUID/correlation ID |
| `@AfterEach deleteAll()` | Xóa dữ liệu của test khác | Dọn theo ID/schema riêng |
| Latch singleton dùng chung | Test A release nhầm worker B | Test-scoped gateway, key theo run |
| Global `TaskExecutor.shutdownNow()` | Hủy task ngoài phạm vi test | Chỉ shutdown test-owned executor |
| Cached Spring context và class-scoped container | Context dùng DB container đã dừng | Đồng bộ lifecycle |
| Registry dùng chung | Xóa pending event của test khác | Namespace/isolated adapter |
| Worker retry sau teardown | Row tái xuất hiện trong test tiếp theo | Quiescence + isolation |
| Shared external sandbox account | Side effect leak sang suite khác | Test tenant/idempotency/cleanup policy |

**Isolation không phải excuse để bỏ cleanup**, nhưng khi không thể đảm bảo global worker đã dừng, một môi trường test hoàn toàn cô lập và disposable an toàn hơn phá shared state bằng force cancellation.

### Mẫu chính sách thất bại

- Test có owned executor: cancel và await dừng, không trả PASS nếu không terminate.
- Test Spring event: chờ terminal state nếu có, capture diagnostic; không xóa mutable shared state khi worker còn hoạt động.
- Test registry/recovery: giữ pending publication cho đến khi bài kiểm chứng kết thúc.
- Test external provider: dùng sandbox và cancellation/compensation API hợp đồng.
- CI suite đã bị nhiễm state: đánh dấu gate fail/quarantine môi trường đó, không coi kết quả các test phụ thuộc sau là đáng tin.

## 27. Kiểm chứng ranh giới kiến trúc Spring Modulith

Runtime event có chiều `orders → fulfillment`, nhưng dependency tĩnh Java có thể là `fulfillment → orders` qua public event `OrderPlaced`.

Được phép:

~~~java
import com.example.shop.orders.OrderPlaced;
~~~

Không nên:

~~~java
// Vi phạm ranh giới module mặc định:
import com.example.shop.orders.internal.persistence.OrderEntity;
~~~

Test kiến trúc độc lập:

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

`ApplicationModules.verify()` kiểm tra các quy tắc như dependency cycle, truy cập ngoài module API và allowed dependencies khi được khai báo. Nó **không tự kiểm tra listener commit hoặc cleanup**.

Nếu `fulfillment` chỉ được phụ thuộc `orders`, có thể khai báo:

~~~java
@ApplicationModule(allowedDependencies = "orders")
package com.example.shop.fulfillment;

import org.springframework.modulith.ApplicationModule;
~~~

Không mở allowedDependencies cho tất cả module chỉ để `verify()` xanh. Cần review API và event contract như các ranh giới kiến trúc thật.

## 28. CI quality gate: failure cleanup cũng phải được kiểm chứng

~~~mermaid
flowchart LR
    PR["Pull request"] --> A["Unit + architecture"]
    A --> P["Publisher module tests"]
    P --> C["Consumer after-commit integration"]
    C --> X["Cancellation / failure cleanup"]
    X --> R["Retry / registry / DB"]
    R --> E["Critical HTTP E2E"]
    E --> G{"Đủ bằng chứng, không leak?"}
    G -- "Có" --> OK["Merge / release"]
    G -- "Không" --> FIX["Điều tra và sửa"]
~~~

| Gate | Bằng chứng |
| --- | --- |
| Unit task cancellation | Test-owned worker phản hồi interruption và terminate |
| `ApplicationModules.verify()` | Ranh giới package/dependency đúng |
| `@ApplicationModuleTest` + `PublishedEvents` | Producer publish đúng event |
| Consumer integration | Side effect đúng ID đã commit trước test pass |
| Failure injection | Consumer lỗi được quan sát; cleanup không xóa bằng chứng |
| Retry/idempotency/registry | Replay/recovery không làm trùng side effect |
| PostgreSQL Testcontainers | Constraint/isolation/lifecycle production-like |
| HTTP E2E | Client thấy terminal business outcome, không chỉ 202 |

### Quy tắc chất lượng CI

- Đặt **deadline hữu hạn** cho Awaitility, `Future.get`, `awaitTermination` và HTTP/DB requests.
- Phân biệt test timeout, JUnit method timeout và CI job timeout.
- Giữ last observed state và worker failure trước khi cleanup.
- Không dùng `Thread.sleep` để “bảo đảm đã sạch”.
- Nếu cleanup fail, ghi rõ failure và không che assertion đầu.
- Không shutdown shared executor chỉ để một test pass.
- Không xóa pending event publications khi test chính là recovery.
- Dùng correlation ID/tenant/schema để tránh side effect giữa các test.
- Review parallel test config khi có fixture singleton/DB chung.
- Không tắt architecture test vì integration test xanh.
- Theo dõi timeout rate, leftover tasks và time-to-READY để phát hiện hồi quy.

**Gate phải kiểm tra cả kết quả nghiệp vụ và việc test không để lại tác vụ/tài nguyên do chính test sở hữu.**

## 29. Troubleshooting: khi cleanup sai hoặc không hoàn tất

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Test timeout nhưng task xuất hiện sau đó | Awaitility không cancel worker | Tách observation timeout khỏi lifecycle |
| `Future.isCancelled()` true, worker vẫn log | Worker không ngừng hoặc cancel không interrupt | Await termination, kiểm tra interruption |
| `CompletableFuture.cancel(true)` không dừng action | CompletableFuture cancellation semantics | Cooperative token/termination signal |
| `shutdownNow()` mà pool chưa terminate | Task không phản hồi interrupt | Blocking I/O, loop, leaks |
| `@AfterEach` xóa rồi task tái xuất hiện | Retry/replay sau cleanup | Quiescence/idempotency/registry |
| Test sau thấy row test trước | Shared fixture và late write | ID/schema isolation |
| Listener lỗi khi context đóng | `@DirtiesContext`/shutdown sớm | Context/executor lifecycle |
| After-commit integration luôn timeout | Outer `@Transactional` rollback T1 | Để service commit thật |
| Query không thấy row dù DB có | Snapshot/cache cũ hoặc sai ID | Fresh read transaction, correlation |
| Publication pending biến mất | Teardown xóa registry | Giữ state cho recovery |
| Hủy HTTP GET nhưng server vẫn tạo task | Client cancel không cancel server | Business cancellation API riêng |
| Cleanup failure che lỗi gốc | Exception handling sai | JUnit lifecycle/suppressed |
| Container dừng khi worker đang commit | Testcontainers lifecycle sai | Chờ/giữ container đúng scope |
| Architecture test đỏ dù E2E xanh | Import `internal` sai | Sửa API, giữ `verify()` |

### Trình tự điều tra

1. Tác vụ do **test** hay **application** sở hữu?
2. Trạng thái worker: queued, running, done, retry pending?
3. Side effect nào đã commit?
4. Có cancellation protocol an toàn không?
5. `cancel` đã được gọi hay worker đã thực sự terminate?
6. Fixture có chia sẻ với test khác không?
7. Có pending publication cần phục hồi không?
8. Cleanup nào an toàn, cleanup nào phải skip trong môi trường cô lập?
9. Lỗi gốc, lỗi cleanup và correlation ID có được ghi không?
10. Ranh giới module có đang bị vi phạm không?

Không tăng timeout vô hạn, đóng global executor hoặc xóa toàn bộ DB trước khi biết task đang làm gì.

## 30. Bài thực hành

### Bài A — Owned executor cleanup sau assertion đỏ

Dùng `OwnedWorkerCleanupTest`. Trong nhánh thực hành, tạo một assertion sai có chủ đích, xác nhận `@AfterEach` cancel, executor terminate và worker `finally` chạy. Khôi phục assertion trước khi lưu test lên CI.

### Bài B — Worker bỏ qua interruption

Sửa test fixture để nuốt `InterruptedException` trong vòng lặp. Quan sát `awaitTermination` có thể timeout; sửa worker hợp tác interrupt. Không dùng `Thread.stop()`.

### Bài C — CompletableFuture semantics

Tạo `CompletableFuture.runAsync` trên test-owned executor. Gọi `cancel(true)` rồi kiểm tra trạng thái future và **tín hiệu worker exited** riêng. Giải thích vì sao chúng có thể khác nhau.

### Bài D — Event listener timeout rồi commit muộn

Tạo test-controlled gate chặn consumer. Cho Awaitility timeout, release gate theo `finally` rồi quan sát worker có thể commit sau timeout. Thiết kế isolation để không làm bẩn test kế tiếp.

### Bài E — Failure-aware @AfterEach

Thiết kế cleanup theo correlation ID. Nếu workflow chưa terminal hoặc worker chưa quiescent, chụp diagnostic và bỏ qua destructive cleanup thay vì xóa cả bảng. Báo failure/quarantine môi trường nếu không thể dọn an toàn.

### Bài F — Rollback sau publish

Dùng `TransactionTemplate` tạo T1, publish event rồi rollback. Xác nhận source không commit; giải thích vì sao `until(NOT_OBSERVED)` có thể pass giả và cần listener AFTER_COMMIT/dispatch evidence.

### Bài G — Duplicate/replay và registry

Gửi cùng event hai lần hoặc đồng thời. Kiểm tra DB unique constraints, idempotency và registry pending. Không xóa pending publication trước khi chạy recovery test.

### Bài H — Testcontainers lifecycle

Thử integration trên PostgreSQL Testcontainers với fixture riêng. Đo container startup riêng với consumer wait; đảm bảo context/cache/container scope không làm worker dùng DB đã dừng.

### Bài I — HTTP business cancellation

Giả định có endpoint hủy business operation. Gửi cancel, chờ trạng thái CANCELLED terminal; kiểm tra idempotency và compensation cho side effect đã commit. Giải thích vì sao đóng HTTP client chưa đủ.

### Bài J — Architecture và CI

Chạy `ApplicationModules.verify()`, producer publication test và consumer integration. Cố ý import entity `orders.internal` từ fulfillment, xác nhận architecture test đỏ. Thêm failure cleanup test vào CI gate.

### Câu hỏi tự đánh giá

1. Awaitility timeout có tự hủy `@ApplicationModuleListener` không?
2. `Future.cancel(true)` trả true có chứng minh worker đã terminate?
3. `CompletableFuture.cancel(true)` có chắc interrupt thread gốc?
4. Khi nào được phép dùng `shutdownNow()`?
5. Vì sao không shutdown global Spring executor trong `@AfterEach`?
6. Cleanup khác compensation và transaction rollback thế nào?
7. Vì sao outer `@Transactional` có thể ngăn event AFTER_COMMIT?
8. Khi T2 đã commit, interrupt worker có rollback T2 không?
9. `PublishedEvents` và consumer public state kiểm tra hai việc gì?
10. Vì sao pending registry không nên bị xóa để làm test sạch?
11. Vì sao task có thể tái xuất hiện sau cleanup?
12. Client HTTP timeout có tự cancel server operation?
13. Làm sao bảo vệ failure gốc khi teardown cũng lỗi?
14. Khi nào cô lập test environment tốt hơn force cancellation?
15. Vì sao cần `ApplicationModules.verify()` dù integration xanh?

## 31. Checklist trước khi xác nhận cleanup hoàn tất

- [ ] Đã xác định quyền sở hữu của task/worker.
- [ ] Không cancel/shutdown global application executor ngoài contract.
- [ ] Đã phân biệt cancellation request và verified termination.
- [ ] Test-owned worker có điểm hợp tác interruption.
- [ ] Không coi `CompletableFuture.isCancelled()` là worker quiescent.
- [ ] Cancellation không bị nhầm với rollback mọi commit trước đó.
- [ ] Có chính sách compensation cho external side effect nếu cần.
- [ ] Có deadline hữu hạn cho wait, shutdown và cleanup.
- [ ] Business completion được assert qua public API/terminal state.
- [ ] Dữ liệu fixture có correlation ID riêng.
- [ ] `@AfterEach` không xóa dữ liệu khi late writer còn hoạt động.
- [ ] Gateway/latch test-controlled luôn release trong `finally`.
- [ ] Context/`@DirtiesContext`/executor shutdown được review.
- [ ] Container/DB lifecycle phù hợp worker và recovery.
- [ ] Outer test transaction không vô tình rollback flow AFTER_COMMIT.
- [ ] Listener error và registry pending được quan sát theo policy.
- [ ] Không xóa pending publication để che lỗi retry.
- [ ] Negative assertions không pass giả trước khi async task chạy.
- [ ] Không ignore mọi exception để chuyển bug thành timeout.
- [ ] Duplicate/replay có reliability test riêng.
- [ ] Diagnostic được ghi trước destructive cleanup.
- [ ] Cleanup failure được báo cùng assertion failure gốc.
- [ ] `ApplicationModules.verify()` có trong CI.
- [ ] Negative controls chứng minh failure path thực sự được kiểm thử.

## 32. Ghi nhớ

**Hủy hoặc dọn tác vụ khi test thất bại** bắt đầu từ **ownership, transaction và completion evidence**. Awaitility/JUnit timeout chỉ nói test chưa quan sát được kết quả đúng hạn; chúng **không hủy Spring Modulith listener**, rollback transaction consumer đã commit hay đảo side effect ngoài hệ thống. `Future.cancel(true)` và `shutdownNow()` chỉ là yêu cầu dừng; chỉ dùng với tài nguyên test sở hữu, rồi xác nhận quiescence bằng `awaitTermination` hoặc completion signal thích hợp. `CompletableFuture.cancel` còn có semantics khác.

Với event-driven `@ApplicationModuleListener` sau commit, ưu tiên chờ business outcome, giữ registry/retry policy và cô lập fixture. Với test-controlled workers, dùng cancellation hợp tác, `try/finally` và `@AfterEach` có deadline. Kết hợp `@ApplicationModuleTest` + `PublishedEvents`, consumer integration/reliability tests và `ApplicationModules.verify()` trong quality gate CI để ngăn **xanh giả, resource leak, dữ liệu nhiễm bẩn và phụ thuộc module sai**.




