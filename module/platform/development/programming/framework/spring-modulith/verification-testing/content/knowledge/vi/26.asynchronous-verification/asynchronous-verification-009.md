# Kiểm tra race giữa event và transaction commit

> **Chương:** Async verification  
> **Module:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Tái hiện và kiểm chứng **cửa sổ thời gian từ lúc publish event đến lúc transaction producer commit/rollback**. Bằng chứng cần thu không chỉ là “event được phát” hoặc “test cuối cùng xanh”, mà là **consumer không đọc dữ liệu chưa commit, không tạo side effect cho giao dịch rollback và vẫn xử lý được event sau commit**.

## 1. Câu hỏi kiểm chứng chính xác

Giả sử module `orders` lưu order và phát `OrderPlaced`; module `fulfillment` đọc dữ liệu order hoặc tạo projection theo event. Code trông hợp lý:

~~~java
@Transactional
public void placeOrder(UUID id) {
    orders.save(new OrderEntity(id));
    events.publishEvent(new OrderPlaced(id));
}
~~~

Nếu handler dùng `@Async @EventListener`, thread consumer **có thể chạy ngay khi `publishEvent(...)` được gọi**, trong lúc transaction T1 của producer chưa commit. Consumer ở transaction/kết nối khác sẽ không nhìn thấy row của T1 theo isolation `READ_COMMITTED`. Một lần chạy có thể thành công vì T1 commit trước khi worker kịp đọc; lần khác thất bại vì worker chạy nhanh hơn commit.

Bài này tập trung chứng minh các mệnh đề:

1. **P1 — Chưa commit thì chưa có dữ liệu committed visible:** Sau `saveAndFlush` và `publishEvent` nhưng trước T1 commit, một transaction đọc độc lập ở `READ_COMMITTED` không được thấy order.
2. **P2 — Consumer cần dữ liệu đã commit không được xử lý nghiệp vụ trước commit:** Listener transactional hậu commit không khởi phát side effect cho T1 đang mở.
3. **P3 — Khi commit thành công:** Event liên quan được nhận và side effect consumer cuối cùng có thể đọc được.
4. **P4 — Khi rollback:** Listener `AFTER_COMMIT` không được kích hoạt cho transaction bị hủy.
5. **P5 — Không có xanh giả:** Test không đồng nhất `PublishedEvents`, `listener invoked` hoặc `Thread.sleep` với commit và không dừng trước khi consumer outcome được kiểm tra.

**Điểm học thuật quan trọng:** Một assertion âm tức thời như `assertThat(taskExists(id)).isFalse()` khi T1 đang mở chỉ là **một snapshot**. Nó không chứng minh mọi lịch scheduling đều đúng; cần kết hợp **controlled commit gate**, event phase probe, test rollback và điều kiện sau commit.

## 2. Race nằm ở đâu trên timeline?

~~~mermaid
sequenceDiagram
    participant C as Test/Caller
    participant T1 as orders T1
    participant DB as PostgreSQL
    participant EV as Event infrastructure
    participant T2 as fulfillment T2

    C->>T1: place(id)
    T1->>DB: INSERT + FLUSH (uncommitted)
    T1->>EV: publish OrderPlaced(id)
    Note over T1,EV: Cửa sổ nguy hiểm: event đã phát, T1 chưa commit
    opt @Async @EventListener không gắn commit phase
        EV-->>T2: Có thể schedule ngay
        T2->>DB: SELECT order(id) trên connection khác
        DB-->>T2: Empty ở READ_COMMITTED
    end
    T1->>DB: COMMIT
    opt @ApplicationModuleListener hậu commit
        EV-->>T2: Dispatch sau COMMIT
        T2->>DB: INSERT fulfillment_task
        T2->>DB: COMMIT T2
    end
    T1-->>C: place hoàn tất
    C->>DB: Query fulfillment(id) tới READY
~~~

Có ít nhất **hai quyết định timing khác nhau**:

- **Event publication timing:** Khi producer gọi `publishEvent` trong T1.
- **Listener execution timing:** Khi handler được phép chạy theo transaction phase và async executor.

`@ApplicationModuleListener` của Spring Modulith, trong các phiên bản hỗ trợ, là dạng kết hợp cho **transactional listener pha `AFTER_COMMIT`, asynchronous dispatch và transaction mới**. Điều đó khác `@Async @EventListener` thông thường. Cần kiểm tra dependency/configuration/version dự án; không dùng tên annotation như bằng chứng duy nhất mà bỏ qua integration test.

### Bảng trạng thái có thể quan sát

| Thời điểm | Order trong T1 | Order đọc từ T2 độc lập | Fulfillment task | Điều hợp lệ |
| --- | --- | --- | --- | --- |
| Trước khi save | Chưa có | Chưa có | Chưa có | Bình thường |
| Sau `saveAndFlush`, trước commit | Đã flush nhưng chưa commit | Chưa thấy với `READ_COMMITTED` | Chưa có với listener hậu commit | Bình thường |
| Sau `publishEvent`, T1 còn mở | Vẫn chưa commit | Chưa thấy | **Chưa được tạo bởi handler AFTER_COMMIT** | Cửa sổ cần thử |
| Sau T1 commit, trước T2 | Đã commit | Thấy | Có thể chưa có | Eventual lag hợp lệ |
| Sau T2 commit | Đã commit | Thấy | Đúng ID, trạng thái | Success |
| T1 rollback | Không có row commit | Không có | Không được tạo bởi AFTER_COMMIT event của T1 | Phải bảo vệ |

**`flush ≠ commit`.** `saveAndFlush` buộc JPA gửi SQL, nhờ đó bài test thực sự khảo sát row đã được ghi vào transaction nhưng chưa visible cho giao dịch khác. Chỉ gọi `save` có thể trì hoãn SQL đến commit và làm phép thử quá yếu.

## 3. Phản mẫu dễ tạo race: @Async @EventListener

~~~java
@Component
class UnsafeOrderListener {

    private final OrderQueries orders;

    UnsafeOrderListener(OrderQueries orders) {
        this.orders = orders;
    }

    @Async
    @EventListener
    void on(OrderPlaced event) {
        // Thread khác không thừa kế transaction T1.
        if (!orders.exists(event.orderId())) {
            throw new IllegalStateException(
                    "Order not visible yet: " + event.orderId());
        }
    }
}
~~~

Khi producer phát event trong T1:

- `@EventListener` thường được kích hoạt tại thời điểm publish.
- `@Async` đưa xử lý sang executor; **thread mới không tự được gắn vào transaction T1**.
- Nếu consumer query trước commit, nguồn authoritative có thể trả empty.
- Nếu executor bận và chạy muộn sau commit, test “tình cờ” xanh.

### Phản mẫu không cần async cũng có thể sai

~~~java
@EventListener
@Transactional(propagation = Propagation.REQUIRES_NEW)
void on(OrderPlaced event) {
    // T1 tạm bị suspend; T2 dùng transaction riêng.
    // T2 có thể không thấy insert chưa commit ở T1.
    assertOrderCommitted(event.orderId());
}
~~~

Với `REQUIRES_NEW` trước T1 commit, read query độc lập có thể không thấy row; trên PostgreSQL `READ_COMMITTED`, đây là hành vi dự kiến. Ngược lại, synchronous `@EventListener` chạy ngay trong T1 có thể đọc chính write chưa commit của T1 và tạo **xanh giả** về commit.

**Không sửa bằng `Thread.sleep(500)` trong handler.** Delay chỉ thay đổi xác suất race; cần chọn semantics xử lý **sau commit** và test đúng cửa sổ thời gian.

## 4. Hợp đồng cần bảo vệ bằng test

Trước khi viết Java, định nghĩa rõ contract:

~~~text
Given:
  - orderId duy nhất do test tạo
  - orders lưu row trong T1
  - publish OrderPlaced trong T1

When:
  - T1 bị giữ mở sau publish
Then:
  - independent READ_COMMITTED reader không thấy order
  - after-commit phase probe chưa được gọi
  - fulfillment side effect chưa được thấy

When:
  - Cho T1 commit
Then:
  - orders row visible
  - AFTER_COMMIT probe đã được gọi
  - fulfillment task cuối cùng visible qua public API

When:
  - Một T1 khác rollback sau publish
Then:
  - orders row không visible
  - AFTER_COMMIT probe không được gọi
  - AFTER_ROLLBACK probe ghi nhận rollback
  - không có fulfillment task của rollback ID
~~~

Không biến “consumer invocation không xảy ra trong 200 ms” thành bằng chứng tuyệt đối. Sự vắng mặt được quan sát có giới hạn; **transaction phase và test-controlled timeline** mới là nền tảng chính.

### Chọn ID và điểm quan sát

Để test độc lập và dễ correlation, ví dụ dùng `UUID` do caller cấp như **idempotency/order request ID**:

~~~java
UUID id = UUID.randomUUID();
orders.place(id, "CUS-" + id);
~~~

Production có thể generate ID bên trong service; khi đó dùng một test hook an toàn để lấy ID trước commit. Việc caller cấp UUID ở đây chỉ nhằm giúp test biết rõ entity nào đang nằm trong T1 khi bị chặn.

## 5. Cấu trúc module cho bài thử race

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderCommands.java             # Public write API
│   ├── OrderQueries.java              # Public committed-read API
│   ├── OrderPlaced.java               # Public event
│   └── internal/
│       ├── OrderApplicationService.java
│       ├── OrderQueryService.java
│       ├── CommitWindow.java           # Internal test seam
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/
    ├── FulfillmentQueries.java        # Public API cho oracle
    └── internal/
        ├── OrderPlacedListener.java
        ├── FulfillmentQueryService.java
        └── persistence/
            ├── FulfillmentTask.java
            └── FulfillmentTaskRepository.java
~~~

**Ranh giới:** `fulfillment` chỉ import public `orders.OrderPlaced`; không chọc vào `orders.internal.persistence.OrderRepository`. Test race nằm trong `com.example.shop.orders.internal` để có thể tiêm **test-only gate** ở internal seam của producer, trong khi assert kết quả qua API `orders.OrderQueries` và `fulfillment.FulfillmentQueries`.

### Test seam không phải production delay

`CommitWindow.afterEventPublished(id)` là một port nội bộ có implementation production **no-op**. Trong integration test, override bằng gate có latch để giữ T1 mở ngay sau publish. Cách này deterministic hơn thay source production bằng `Thread.sleep` hoặc sửa delay global.

**Không bật gate trong production.** Không dùng nó để thay đổi contract event; nó chỉ cho phép test điều khiển lịch tại đúng ranh giới cần kiểm chứng.

## 6. Mã nguồn: public API và entity producer

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

**`src/main/java/com/example/shop/orders/OrderCommands.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public interface OrderCommands {
    void place(UUID orderId, String customerId);
}
~~~

**`src/main/java/com/example/shop/orders/OrderQueries.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public interface OrderQueries {
    boolean exists(UUID orderId);
}
~~~

**`src/main/java/com/example/shop/orders/OrderPlaced.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

**`src/main/java/com/example/shop/orders/internal/persistence/OrderEntity.java`**

~~~java
package com.example.shop.orders.internal.persistence;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_orders")
public class OrderEntity {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String customerId;

    protected OrderEntity() {}

    public OrderEntity(UUID id, String customerId) {
        this.id = id;
        this.customerId = customerId;
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

### Vì sao tự cấp ID?

ID do caller cấp giúp test biết chính xác `orderId` **trước** khi T1 commit và không phải đọc thông qua JPA entity chưa visible. Cần unique constraint/primary key chống tạo trùng. Nếu ứng dụng đã có server-generated ID, giữ design đó và điều chỉnh test gate để capture ID; không ép đổi business API chỉ vì thử race.

## 7. Đặt test gate chính xác trong T1

**`src/main/java/com/example/shop/orders/internal/CommitWindow.java`**

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.stereotype.Component;

interface CommitWindow {
    void afterEventPublished(UUID orderId);
}

@Component
class NoOpCommitWindow implements CommitWindow {

    @Override
    public void afterEventPublished(UUID orderId) {
        // Production: intentionally no-op.
    }
}
~~~

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

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;
    private final CommitWindow window;

    OrderApplicationService(
            OrderRepository repository,
            ApplicationEventPublisher publisher,
            CommitWindow window) {
        this.repository = repository;
        this.publisher = publisher;
        this.window = window;
    }

    @Override
    @Transactional
    public void place(UUID id, String customerId) {
        if (id == null || customerId == null
                || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId/customerId required");
        }

        repository.saveAndFlush(new OrderEntity(id, customerId));
        publisher.publishEvent(new OrderPlaced(id));

        // Quan trọng: còn đang ở trong @Transactional method.
        // Transaction T1 chưa commit tại đây.
        window.afterEventPublished(id);
    }
}
~~~

**Điểm cần giữ đúng:** Spring transaction interceptor chỉ có thể hoàn tất commit sau khi body `place(...)` trả về thành công. Trong lúc `window.afterEventPublished(id)` đang chặn, T1 còn mở; `saveAndFlush` đã gửi SQL nhưng chưa commit.

Nếu di chuyển gate **ra ngoài method `@Transactional`** hoặc chặn sau khi proxy trả về, bài test không còn kiểm tra cửa sổ trước commit. Nếu test có outer `@Transactional`, proxy có thể không tự commit T1 khi return: tránh outer test transaction trong bài này.

### Public query tạo transaction đọc riêng

**`src/main/java/com/example/shop/orders/internal/OrderQueryService.java`**

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.orders.OrderQueries;
import com.example.shop.orders.internal.persistence.OrderRepository;

@Service
class OrderQueryService implements OrderQueries {

    private final OrderRepository repository;

    OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional(readOnly = true)
    public boolean exists(UUID orderId) {
        return repository.existsById(orderId);
    }
}
~~~

Khi test thread gọi `OrderQueries.exists(id)`, nó dùng transaction/kết nối **khác** thread producer. Với PostgreSQL `READ_COMMITTED`, nó không đọc row đã flush nhưng chưa commit ở T1. Đây là một assertion có ngữ nghĩa khác với query chạy ngay trong T1.

## 8. Consumer minh họa: chỉ cần public outcome

**`src/main/java/com/example/shop/fulfillment/FulfillmentQueries.java`**

~~~java
package com.example.shop.fulfillment;

import java.util.UUID;

public interface FulfillmentQueries {
    boolean taskExists(UUID orderId);
}
~~~

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
    public boolean taskExists(UUID orderId) {
        return tasks.existsById(orderId);
    }
}
~~~

`@ApplicationModuleListener` là listener hậu commit nên không cần workaround bằng `Thread.sleep`. `FulfillmentQueries.taskExists` là oracle sau T2 commit. Một event duplicate đồng thời có thể làm check-then-insert race; đó là **reliability issue riêng**, cần unique constraint/idempotent insert và test concurrency.

### Phạm vi của phép kiểm

Consumer này chỉ ghi projection, không đọc authoritative order; nhờ vậy test kiểm tra rõ **side effect sau commit**. Nếu consumer phải đọc order từ `OrderQueries`, lỗi trước commit càng dễ thấy vì T2 không nhìn thấy row T1. Bài sẽ chỉ ra cách cố tình tái hiện lỗi này ở mục phản ví dụ.

## 9. Ma trận kịch bản cần thực thi

| Case | Điều khiển timeline | Oracle chính | Bug sẽ bắt |
| --- | --- | --- | --- |
| **R1 — Commit đang bị giữ** | Publish + flush; gate trước return | Source invisible ở reader độc lập; probe AFTER_COMMIT chưa chạy | Hiểu nhầm flush=commit / callback phase sai |
| **R2 — Release để commit** | Mở gate | Source visible; AFTER_COMMIT probe, consumer task cuối cùng visible | Listener không đăng ký, task rollback/mất |
| **R3 — Rollback sau publish** | T1 rollback có chủ đích | Source absent; AFTER_ROLLBACK probe; AFTER_COMMIT probe absent | Event tiêu thụ dù transaction rollback |
| **R4 — Sai @Async @EventListener** | Ép worker đọc trong cửa sổ T1 mở | Consumer thấy source absent, test phải phát hiện | Early dispatch race |
| **R5 — Failure commit/constraint** | Gây rollback/commit failure | Không tạo task từ event T1 chưa commit | Ghost side effect |
| **R6 — Retry sau T1 commit** | Consumer fail rồi recover | Task xuất hiện đúng ID, idempotent | Lost event/duplicate effect |
| **R7 — Test có outer @Transactional** | Test rollback mặc định | Chỉ là negative control của test setup | False timeout do không có commit |

**Không gộp toàn bộ case vào một phép AssertJ `isPresent()` sau lệnh place.** Mỗi case thử một quyết định timing có thể hỏng độc lập.

## 10. Phân biệt mức độ bằng chứng trong cửa sổ trước commit

Một phép thử đáng tin cần biết **đang chặn ở mốc nào**:

~~~text
T1 [saveAndFlush] -- [publishEvent] -- [gate waits] -- [method return] -- [commit]
                                           ^
                                      test thread
                                  query nguồn/consumer
~~~

- `CountDownLatch.entered` của gate chứng minh producer đã **đi qua `publishEvent` và chưa return khỏi method transactional**.
- `OrderQueries.exists(id) == false` chứng minh **giao dịch đọc độc lập chưa thấy row** tại mốc đó.
- `FulfillmentQueries.taskExists(id) == false` là bằng chứng **chưa thấy side effect tại thời điểm đọc**.
- `AFTER_COMMIT probe chưa chạy` là bằng chứng Spring transaction phase callback chưa xảy ra tới mốc đó; probe được gọi đồng bộ theo transaction synchronization khi commit.
- Sau release, `Future.get` chứng minh call producer đã return/transaction proxy hoàn tất; Awaitility cuối chứng minh consumer T2 commit/visible.

**Lưu ý giới hạn:** Một consumer sai dùng `@Async @EventListener` có thể chưa được scheduler chạy tại đúng khoảnh khắc test check absence, nên absence tức thời **không đủ chứng minh race đã được loại bỏ**. Muốn bắt consumer sai một cách chắc chắn, cần test-controlled scheduling/latch ở chính faulty listener (mục sau).

## 11. Test gate và transaction-phase probe

Ta dùng **hai quan sát độc lập** để hạn chế xanh giả:

1. **Producer gate** giữ transaction T1 mở sau `publishEvent` nhưng trước return/commit.
2. **PhaseRecorder** dùng `@TransactionalEventListener(AFTER_COMMIT/AFTER_ROLLBACK)`, lưu event ID vào set thread-safe.

Probe chỉ chứng minh **pha của callback**. Consumer thật vẫn phải được kiểm tra bằng read API của `fulfillment` sau transaction T2.

~~~mermaid
flowchart TD
    A["T1 saveAndFlush(id)"] --> B["publish OrderPlaced(id)"]
    B --> G["CommitWindow giữ T1"]
    G --> Q["Test query nguồn từ transaction độc lập"]
    Q --> R["Test kiểm tra AFTER_COMMIT chưa được ghi"]
    R --> UNLOCK["Thả gate"]
    UNLOCK --> OUT{"Kết cục T1"}
    OUT -- "COMMIT" --> C["AFTER_COMMIT phase probe"]
    C --> L["@ApplicationModuleListener sau commit"]
    L --> V["Task visible sau T2 COMMIT"]
    OUT -- "ROLLBACK" --> X["AFTER_ROLLBACK phase probe"]
    X --> N["Không dispatch AFTER_COMMIT"]
~~~

**Cấm tự tạo deadlock:** Không chờ consumer hậu commit chạy khi gate còn giữ T1. Trong một setup đúng, listener không thể bắt đầu theo pha `AFTER_COMMIT` cho đến khi thả gate.

## 12. Integration test PostgreSQL kiểm chứng thứ tự commit/rollback

Đây là bài test trung tâm, đặt trong `com.example.shop.orders.internal` để có thể implement `CommitWindow` là internal test seam. Các source ở mục 6–8 là dependencies thực.

**`src/test/java/com/example/shop/orders/internal/CommitRaceIntegrationTest.java`**

~~~java
package com.example.shop.orders.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import com.example.shop.orders.OrderCommands;
import com.example.shop.orders.OrderPlaced;
import com.example.shop.orders.OrderQueries;
import com.example.shop.orders.internal.persistence.OrderEntity;
import com.example.shop.orders.internal.persistence.OrderRepository;
import com.example.shop.fulfillment.FulfillmentQueries;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
            "spring.jpa.hibernate.ddl-auto=create-drop",
            "spring.datasource.hikari.maximum-pool-size=5"
        })
@Import(CommitRaceIntegrationTest.RaceSupport.class)
class CommitRaceIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderCommands commands;
    @Autowired OrderQueries orders;
    @Autowired FulfillmentQueries fulfillment;
    @Autowired PausingCommitWindow gate;
    @Autowired PhaseRecorder phases;

    @Autowired TransactionTemplate transactions;
    @Autowired OrderRepository repository;
    @Autowired ApplicationEventPublisher events;

    @Test
    @Timeout(value = 30, unit = TimeUnit.SECONDS)
    void cannot_observe_uncommitted_order_then_processes_commit()
            throws Exception {

        UUID id = UUID.randomUUID();
        ExecutorService producerThread =
                Executors.newSingleThreadExecutor();

        try {
            Future<?> command = producerThread.submit(
                    () -> commands.place(id, "CUS-" + id));

            // Body @Transactional đã publish, nhưng T1 còn mở.
            assertThat(gate.published.await(
                    5, TimeUnit.SECONDS)).isTrue();

            // Từ test thread, đây là transaction/kết nối khác.
            assertThat(orders.exists(id)).isFalse();

            // Snapshot consumer trong cửa sổ trước commit.
            assertThat(fulfillment.taskExists(id)).isFalse();

            // Probe AFTER_COMMIT chưa chạy.
            assertThat(phases.committed.contains(id)).isFalse();

            // Transaction proxy chưa thể return xong.
            assertThat(command.isDone()).isFalse();

            // Cho method return và Spring commit T1.
            gate.release.countDown();
            command.get(8, TimeUnit.SECONDS);

            assertThat(orders.exists(id)).isTrue();

            // Phase probe đồng bộ chạy khi commit hoàn tất.
            assertThat(phases.committed.contains(id)).isTrue();

            // Listener Spring Modulith chạy async trong T2.
            await()
                    .atMost(Duration.ofSeconds(10))
                    .pollInterval(Duration.ofMillis(100))
                    .untilAsserted(() ->
                            assertThat(fulfillment.taskExists(id))
                                    .isTrue());

        } finally {
            // Bất kể assertion fail, không để T1 kẹt mãi.
            gate.release.countDown();

            // Chỉ đóng executor do test tự tạo để gọi producer.
            producerThread.shutdown();
            if (!producerThread.awaitTermination(
                    10, TimeUnit.SECONDS)) {
                producerThread.shutdownNow();
                assertThat(producerThread.awaitTermination(
                        2, TimeUnit.SECONDS)).isTrue();
            }
        }
    }

    @Test
    void rollback_after_publish_does_not_dispatch_after_commit() {
        UUID id = UUID.randomUUID();

        transactions.executeWithoutResult(status -> {
            repository.saveAndFlush(
                    new OrderEntity(id, "CUS-ROLLBACK"));

            events.publishEvent(new OrderPlaced(id));

            // Rollback T1 sau publish nhưng trước commit.
            status.setRollbackOnly();
        });

        assertThat(orders.exists(id)).isFalse();

        // PhaseRecorder chạy đồng bộ theo transaction sync.
        assertThat(phases.rolledBack.contains(id)).isTrue();
        assertThat(phases.committed.contains(id)).isFalse();

        // Kiểm tra âm trong CỬA SỔ quan sát, không phải
        // khẳng định "không bao giờ" dựa trên một snapshot.
        await()
                .during(Duration.ofMillis(300))
                .atMost(Duration.ofSeconds(2))
                .untilAsserted(() ->
                        assertThat(fulfillment.taskExists(id))
                                .isFalse());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class RaceSupport {

        @Bean
        @Primary
        PausingCommitWindow pausingCommitWindow() {
            return new PausingCommitWindow();
        }

        @Bean
        PhaseRecorder phaseRecorder() {
            return new PhaseRecorder();
        }
    }

    static final class PausingCommitWindow
            implements CommitWindow {

        final CountDownLatch published = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);

        @Override
        public void afterEventPublished(UUID orderId) {
            published.countDown();

            try {
                if (!release.await(12, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Commit gate expired for " + orderId);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Producer interrupted before commit", e);
            }
        }
    }

    static final class PhaseRecorder {

        final Set<UUID> committed =
                ConcurrentHashMap.newKeySet();

        final Set<UUID> rolledBack =
                ConcurrentHashMap.newKeySet();

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            committed.add(event.orderId());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderPlaced event) {
            rolledBack.add(event.orderId());
        }
    }
}
~~~

### Tiền điều kiện để test này có ý nghĩa

- Java 17+, JUnit 5, Spring Boot 3.1+ cho `@ServiceConnection`, Spring Modulith tương thích, JPA và Testcontainers PostgreSQL.
- PostgreSQL dùng isolation mặc định `READ_COMMITTED`. Nếu dự án tùy chỉnh isolation, phải khai báo rõ điều kiện mong đợi.
- `hibernate.ddl-auto=create-drop` chỉ làm bài học tự chứa; production dùng Flyway/Liquibase thì test quan trọng nên chạy migration thật.
- Hikari pool size đủ cho producer **giữ một connection** và test thread **đọc bằng connection khác**.
- `@Primary PausingCommitWindow` thay bean no-op cùng interface, nhưng chỉ trong context test.
- Có **một test** gọi `commands.place(...)` qua gate. Nếu muốn nhiều test gọi đồng thời, phải thiết kế gate theo `orderId`, không dùng một latch singleton toàn context.
- Không đặt `@Transactional` lên test method; producer bắt đầu T1 trong worker thread qua Spring proxy.

### Vì sao không chỉ dùng H2?

`saveAndFlush` trước commit cần kiểm tra visibility đúng với database production. H2 có thể khác PostgreSQL về isolation, locks và transaction behavior. Sử dụng database engine phù hợp là một phần của **oracle**, không phải trang trí test.

### Vì sao PhaseRecorder không @Async?

`@TransactionalEventListener(AFTER_COMMIT)` không async chạy trong synchronization callback của transaction producer. `command.get(...)` đợi producer method/transaction proxy hoàn tất nên test có thể kiểm tra `phases.committed` mà không phải đoán lịch worker.

Nhưng recorder **chỉ xác minh callback phase của recorder**, không tự chứng minh listener fulfillment đã commit. Awaitility trên `FulfillmentQueries` vẫn bắt buộc.

## 13. Cách đọc bằng chứng theo từng mốc

~~~text
A — Commit gate đang chặn:
  T1: SQL INSERT đã flush
  T1: publishEvent đã gọi
  T1: chưa commit
  orders.exists(id) từ test thread    = false
  fulfillment.taskExists(id)           = false (snapshot)
  phases.committed.contains(id)        = false
  producer Future.isDone()             = false

B — Release gate:
  T1: method return
  Transaction interceptor commit
  AFTER_COMMIT probe ghi nhận id
  producer Future.get() thành công
  orders.exists(id)                    = true

C — Consumer:
  @ApplicationModuleListener được schedule sau commit
  Transaction T2 ghi fulfillment_task và commit
  Awaitility thấy taskExists(id)       = true

Rollback:
  T1 publish rồi rollback
  AFTER_ROLLBACK probe ghi nhận id
  AFTER_COMMIT probe không ghi nhận id
  orders row không commit
~~~

### Đừng buộc consumer phải “chậm” sau commit

Listener async có thể hoàn tất **trước khi test thread tiếp tục sau `Future.get`**. Hoàn toàn hợp lệ. Test chỉ cần sự kiện **không được dispatch nghiệp vụ trước commit** và **cuối cùng đạt outcome**; không yêu cầu có một khoảng task absent sau commit.

### Vì sao snapshot âm chưa đủ?

Một listener lỗi sử dụng `@Async @EventListener` có thể chưa được executor chạy **ở đúng lúc test query task**. Vì thế việc không thấy task là bằng chứng tại thời điểm đó, không phải chứng minh vĩnh viễn. Cần transaction-phase semantics cùng negative control điều khiển lịch xử lý, không thay bằng sleep.

## 14. PublishedEvents chứng minh điều gì trước transaction commit?

Producer module test có thể dùng:

~~~java
@ApplicationModuleTest
class OrderPublisherTest {

    @Autowired OrderCommands orders;

    @Test
    void publishes_order_placed(PublishedEvents events) {
        UUID id = UUID.randomUUID();
        orders.place(id, "CUS-" + id);

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }
}
~~~

Cần imports Spring Modulith `@ApplicationModuleTest`, `PublishedEvents`, JUnit `@Test`, `@Autowired`, `UUID` và AssertJ. Producer module test có thể cần datasource test tùy JPA setup.

**Đã chứng minh:** Event type/payload ID được publish bởi service.

**Chưa chứng minh:** T2 của consumer commit, registry durable, exactly-once event delivery hay callback AFTER_COMMIT chạy ngay lúc capture. Khi producer publish rồi rollback, publication đã được phát trong phạm vi process, nhưng transactional listener `AFTER_COMMIT` **không xử lý**. Hai kết quả không mâu thuẫn.

Không dùng producer-only `@ApplicationModuleTest` để kết luận consumer đúng nếu `fulfillment` không được bootstrap. Case race liên module ở mục 12 dùng context có producer, consumer, JPA và database thật.

### Rollback cần được kiểm tra có chủ đích

- Transaction T1 thực sự rollback, không chỉ có exception ở test thread.
- Assert row authoritative không visible.
- Kiểm chứng `AFTER_ROLLBACK`/`AFTER_COMMIT` đúng pha.
- Bổ sung quan sát negative side effect nếu hợp đồng yêu cầu.
- Nếu có external broker hoặc durable registry, phải kiểm tra rollback effect ở chính adapter ấy.

Một lần gọi `taskExists(id) == false` ngay sau rollback **chưa** chứng minh một listener cấu hình sai sẽ không chạy muộn. Bằng chứng chính đến từ transaction phase và integration test có scheduling điều khiển.

## 15. Negative control: ép listener sai đọc trước commit

Để chắc rằng test có khả năng **phơi bày** race, tạo riêng một biến thể `@Async @EventListener` không gắn pha commit. **Không đưa nó vào production hoặc cùng context test bình thường.**

~~~java
// Test-only faulty listener được @Import trong
// một context/nhánh thí nghiệm riêng.
@Component
class UnsafeEarlyReadListener {

    private final OrderQueries orders;
    private final EarlyReadProbe probe;

    UnsafeEarlyReadListener(
            OrderQueries orders,
            EarlyReadProbe probe) {
        this.orders = orders;
        this.probe = probe;
    }

    @Async
    @EventListener
    void on(OrderPlaced event) {
        probe.entered.countDown();

        try {
            probe.visible.set(orders.exists(event.orderId()));
        } finally {
            probe.observed.countDown();
        }
    }
}
~~~

~~~java
final class EarlyReadProbe {
    final CountDownLatch entered = new CountDownLatch(1);
    final CountDownLatch observed = new CountDownLatch(1);
    final AtomicBoolean visible = new AtomicBoolean(true);
}
~~~

Đây là **code khung**; khi chạy thực tế phải inject `EarlyReadProbe` và imports `Component`, `Async`, `EventListener`, `AtomicBoolean`, `CountDownLatch`. Consumer faulty sử dụng public `OrderQueries` để có transaction đọc độc lập.

### Lịch thử trên biến thể sai

1. Producer `saveAndFlush`, publish rồi đứng tại `CommitWindow`.
2. Test đợi `gate.published`, bảo đảm T1 vẫn chưa commit.
3. Vì `@Async @EventListener` được schedule lúc publish, test chờ `probe.observed.await(timeout)` **trong lúc gate còn giữ T1**.
4. `probe.visible == false` chứng minh consumer sai có thể đọc source quá sớm.
5. Release gate trong `finally`; không để producer kẹt.
6. Thay handler bằng hậu commit; khi đó **không được chờ probe được gọi trước release**, vì đúng semantics là nó chưa chạy.

**Nếu worker không start do executor đang nghẽn**, `probe.observed` sẽ timeout — đây là vấn đề setup, không phải bằng chứng listener đúng. Dùng executor đủ capacity và báo rõ phần nào timeout.

### Tại sao thí nghiệm này mạnh hơn sleep?

Không đoán “worker sẽ chạy trong 200 ms”; nó **đợi tín hiệu worker đã hoàn thành phép đọc** trước khi cho T1 commit. Kết quả query empty vì thời điểm được khóa bằng latch, không phụ thuộc may rủi CPU/CI.

### Một anti-pattern đồng bộ khác

~~~java
@EventListener
@Transactional(propagation = Propagation.REQUIRES_NEW)
void on(OrderPlaced event) {
    // T1 bị suspend, T2 riêng sẽ không thấy uncommitted row.
    if (!orders.exists(event.orderId())) {
        throw new IllegalStateException("Missing order");
    }
}
~~~

Code này không nhất thiết có thread race, nhưng vẫn **sai phase**: gọi ngay trong `publishEvent` trước T1 commit; transaction mới không thấy source. Đừng sửa bằng cách bỏ `REQUIRES_NEW` để handler đọc chính dirty state của T1 rồi tưởng đã kiểm chứng commit.

## 16. Phân biệt annotation theo thời điểm dispatch

| Cơ chế | Thời điểm gọi/schedule | Context transaction | Race trước commit? |
| --- | --- | --- | --- |
| `@EventListener` | Tại `publishEvent` theo multicaster đồng bộ thông thường | Có thể cùng T1 | Có nếu side effect phụ thuộc commit/external |
| `@Async @EventListener` | Schedule lúc publish, execute tùy executor | Thread khác không tự kế thừa T1 | **Có** |
| `@TransactionalEventListener(AFTER_COMMIT)` | Callback theo phase sau T1 commit | Sau commit; ghi DB mới cần transaction mới đúng | Tránh early dispatch |
| `@Async @TransactionalEventListener(AFTER_COMMIT)` | Schedule sau commit | Thread async, transaction riêng cần cấu hình | Tránh early dispatch; vẫn eventual |
| `@ApplicationModuleListener` | Spring Modulith composed transactional listener | Thường async hậu commit và T2 độc lập | Tránh early dispatch theo contract |
| Gửi broker trực tiếp trong T1 | Broker nhận ngay nếu không có outbox/coordination | DB và broker không atomic | Ghost event khi rollback |

### Chi tiết AFTER_COMMIT ghi database

Một callback `AFTER_COMMIT` đồng bộ có thể còn thấy transaction resources bind với thread tại pha completion. Không nên gắn `@Transactional(REQUIRED)` rồi giả định nó sẽ có một commit thứ hai cho công việc mới. Dùng transaction mới có chủ đích (ví dụ `REQUIRES_NEW`) hoặc cơ chế listener của Spring Modulith phù hợp.

### Publish ngoài transaction

`@TransactionalEventListener` mặc định không chạy khi **không có transaction active** và `fallbackExecution=false`. Self-invocation qua method `@Transactional` không đi qua proxy, hoặc một publisher được gọi từ nontransactional path, có thể tạo **event không có callback như dự đoán**. Bài test phải chứng minh T1 thực sự active, thay vì chỉ nhìn thấy annotation.
## 17. Kiểm tra T1 thực sự active tại điểm publish

`@Transactional` trên source code không bảo đảm transaction active: proxy có thể bị bypass hoặc transaction đang do outer caller sở hữu.

Trong implementation **test-only** của `CommitWindow.afterEventPublished`, có thể bổ sung:

~~~java
@Override
public void afterEventPublished(UUID id) {
    if (!TransactionSynchronizationManager
            .isActualTransactionActive()) {
        throw new AssertionError(
                "No active T1 at publication: " + id);
    }

    published.countDown();
    awaitReleaseWithDeadline();
}
~~~

Cần import `org.springframework.transaction.support.TransactionSynchronizationManager`; `awaitReleaseWithDeadline()` là helper test-only dùng latch như mục 12. Assertion này buộc test **thực sự chạy transaction** tại đúng thời điểm event được phát.

### Self-invocation và proxy

~~~java
@Service
class UnsafeOrderService {

    void outer(UUID id) {
        this.place(id); // Bypass transaction proxy.
    }

    @Transactional
    public void place(UUID id) {
        // save + publish...
    }
}
~~~

Nếu `outer` không có outer transaction, lời gọi `this.place` không kích hoạt interceptor `@Transactional` trong mô hình Spring proxy thông thường. `@TransactionalEventListener` với `fallbackExecution=false` có thể không nhận callback. Một module test chỉ assert event được publish có thể vẫn xanh.

Nếu caller đã mở T0 và `orders.place` tham gia T0 theo `REQUIRED`, **method place return không phải commit point**. Listener sẽ đợi commit của T0. Hãy xác định transaction owner trước khi thiết kế gate.

## 18. Chọn primitive đồng bộ theo đúng mệnh đề

| Cơ chế | Chứng minh/điều khiển | Rủi ro |
| --- | --- | --- |
| `CountDownLatch` tại producer sau publish | T1 còn mở trong một cửa sổ | Quên release gây deadlock |
| `Phaser` / barrier | Các thread đã gặp mốc test | Sai participants |
| Controlled `TaskExecutor` | Task đã schedule/started | Chạm global executor |
| `TransactionTemplate` | Commit/rollback chủ động | Đặt transaction sai thread |
| `TransactionalEventListener` phase probe | Phase callback Spring | Không phải business completion |
| Awaitility | Consumer cuối cùng visible | Chờ khi producer còn khóa T1 |
| `Thread.sleep` | Chỉ tăng delay | Không đảm bảo event ordering |

**Self-deadlock điển hình:** Test giữ T1 tại gate, rồi Awaitility chờ listener `AFTER_COMMIT` trước khi release. Listener đúng thiết kế **không thể chạy**; test sẽ timeout do chính mình gây ra.

Đúng thứ tự: *đợi gate → kiểm tra uncommitted visibility → release gate → đợi T1 commit → đợi T2 visible*.

Chỉ với **negative-control listener sai `@Async @EventListener`**, test mới cố ý đợi worker đọc **trước** release để chứng minh early read.

## 19. Rollback sau publish khác lỗi xảy ra trước publish

~~~text
A: saveAndFlush -> publish -> setRollbackOnly -> ROLLBACK
B: saveAndFlush -> publish -> COMMIT attempt -> DB failure
~~~

Hai trường hợp đều có event phát ra trước khi T1 hoàn tất. Nếu listener/broker xử lý sớm, có thể sinh side effect cho order không bao giờ được commit.

### Failure injection đúng mốc

- `TransactionTemplate` publish rồi `setRollbackOnly`: rõ ràng và deterministic cho rollback.
- Constraint **deferred tới commit** trên database hỗ trợ: tạo lỗi tại mốc commit sau publication.
- Ném exception **sau publish** trong transactional method để rollback.
- **Không đủ:** Cho `saveAndFlush` lỗi trước publish và kết luận đã thử race event–commit.

| Oracle | Kỳ vọng khi T1 fail |
| --- | --- |
| Committed authoritative row | Không có |
| AFTER_COMMIT phase probe | Không ghi ID |
| AFTER_ROLLBACK phase probe | Ghi ID khi phase tương ứng chạy |
| Fulfillment task của event T1 | Không được tạo bởi listener AFTER_COMMIT |
| Broker/registry/outbox state | Theo adapter và transactional coupling |
| Caller | Nhận error hoặc rollback, không giả success |

Phải xác định T1 đã commit hay rollback **trước** khi coi lỗi ở consumer là nguyên nhân.

## 20. Dual-write race khi publish ra broker bên ngoài

### Publish broker trước T1 commit

~~~text
T1 INSERT order (chưa commit)
Broker nhận OrderPlaced
External consumer xử lý
T1 ROLLBACK
=> Ghost event
~~~

### Publish broker sau commit không có outbox

~~~text
T1 COMMIT order
Process crash trước broker publish
=> Order tồn tại nhưng event có thể mất
~~~

Một transactional outbox có thể ghi **event intent cùng T1**, sau đó dispatcher giao lại theo chính sách. Spring Modulith Event Publication Registry và các persistence adapters có thể tham gia tracking khi cấu hình đúng; **atomicity/recovery/delivery semantics phụ thuộc adapter/version**. Không mặc định exactly-once.

| Điều cần chứng minh | Test |
| --- | --- |
| Rollback không để durable publication | Rollback rồi đọc outbox/registry storage |
| Commit tạo publication durable | Commit rồi query storage |
| Dispatcher fail không mất event | Failure injection + resubmit/restart |
| Không có ghost broker event | Broker integration test |
| Replay không nhân đôi side effect | Idempotency/concurrency test |
| Crash window được xử lý | Recovery test thật |

`@ApplicationModuleListener` giải quyết early dispatch **trong process**, nhưng không tự bảo đảm atomic cross-system delivery.

## 21. Isolation, flush và snapshot

Trong integration test:

1. T1 được mở ở producer thread.
2. `saveAndFlush` đã gửi SQL nhưng chưa commit.
3. Test thread gọi public `OrderQueries.exists(id)` bằng transaction/kết nối độc lập.
4. PostgreSQL `READ_COMMITTED` không cho thấy row uncommitted.
5. Sau release và commit, test query lại bằng transaction mới.

### Các nguồn gây kết luận sai

| Setup | Vấn đề |
| --- | --- |
| Mock repository | Không mô phỏng DB visibility |
| H2 thay engine production | Có thể khác locking/isolation |
| Connection pool size 1 | Reader chờ connection do T1 giữ |
| Outer test `@Transactional` | Commit boundary khác với giả định |
| Reader transaction `REPEATABLE_READ` dài | Giữ snapshot cũ sau commit |
| JPA persistence context cached | Entity/snapshot không refresh |
| Read replica/cache | Lag sau commit, khác race trước commit |

**Không tăng timeout để che sai isolation hoặc stale snapshot.**

Sai:

~~~java
boolean snapshot = fulfillment.taskExists(id);
await().until(() -> snapshot);
~~~

Đúng:

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> fulfillment.taskExists(id));
~~~

Mỗi lần poll phải thực sự đọc trạng thái hiện tại qua API.

## 22. Commit T1 và commit T2 có oracle riêng

~~~text
T1 COMMIT orders
  -> AFTER_COMMIT handoff
  -> async executor schedule
  -> T2 BEGIN, INSERT fulfillment_task
  -> T2 COMMIT
~~~

| Phép kiểm | Bằng chứng |
| --- | --- |
| `Future.get` của producer thành công | Service/transaction proxy hoàn tất |
| `PhaseRecorder.committed` có ID | Test probe của AFTER_COMMIT đã chạy |
| `PublishedEvents` có event | Producer publish |
| `FulfillmentQueries.taskExists(id)` true | Consumer side effect visible |
| Registry completed | Xử lý theo registry semantics |
| External receipt terminal | External job xong theo hợp đồng |

Không assert task tức thời sau `Future.get`; consumer có thể vẫn đang chạy. Cũng không kết luận callback AFTER_COMMIT là toàn bộ workflow completion.

## 23. Ordering race sau commit là rủi ro kế tiếp

~~~text
T1: OrderPlaced(id, version=1) -> COMMIT
T3: OrderPaid(id, version=2) -> COMMIT
~~~

Async scheduler/retry có thể hoàn thành version 2 trước version 1. Đây là **race ordering sau commit**, tách khỏi bài thử T1 commit.

Nếu event là snapshot đầy đủ, có thể dùng PostgreSQL conditional upsert:

~~~sql
INSERT INTO order_views
    (order_id, source_version, state)
VALUES
    (:id, :version, :state)
ON CONFLICT (order_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    state = EXCLUDED.state
WHERE order_views.source_version < EXCLUDED.source_version;
~~~

Với delta events, cần ordering/continuity hoặc rebuild thay vì chỉ bỏ qua version cũ. Kiểm thử duplicate, concurrency và out-of-order riêng để commit gate test vẫn deterministic và dễ chẩn đoán.
## 24. Quản lý timeout và tài nguyên khi test giữ T1

Test có gate mở một transaction rồi giữ nó chờ. Nếu assertion sai hoặc test thread bị ngắt, transaction producer có thể kẹt và giữ connection. Do đó **cleanup là một phần của độ tin cậy bài thử race**, không phải công việc phụ.

~~~java
ExecutorService worker = Executors.newSingleThreadExecutor();

try {
    Future<?> call = worker.submit(
            () -> orders.place(id, "CUS-" + id));

    assertThat(gate.published.await(
            5, TimeUnit.SECONDS)).isTrue();

    // Probe khi producer còn bị chặn...
    assertThat(reads.exists(id)).isFalse();

    gate.release.countDown();

    // Bây giờ mới chờ T1 hoàn tất.
    call.get(8, TimeUnit.SECONDS);
} finally {
    gate.release.countDown();

    worker.shutdown();
    if (!worker.awaitTermination(10, TimeUnit.SECONDS)) {
        worker.shutdownNow();

        assertThat(worker.awaitTermination(
                2, TimeUnit.SECONDS)).isTrue();
    }
}
~~~

Đây là **khung nhắc lại barrier order**, bản integration test đầy đủ nằm ở mục 12.

### Các deadline khác nhau

| Deadline | Mục tiêu |
| --- | --- |
| Gate `await(12s)` | Không giữ T1 mãi khi test quên release |
| `gate.published.await(5s)` | Producer phải đi tới điểm publish |
| Producer `Future.get(8s)` | Transaction proxy/commit hoàn tất |
| Awaitility `atMost(10s)` | Consumer T2 eventually visible |
| JUnit `@Timeout(30s)` | Guard toàn method |
| JDBC query timeout/connection timeout | Mỗi call DB blocking |
| Container readiness timeout | DB sẵn sàng trước test |

Các con số là ví dụ; điều chỉnh theo môi trường và đảm bảo tổng time budget nhất quán. Không giải quyết quên release gate bằng cách tăng Awaitility vô hạn.

### Test timeout không cancel consumer

Nếu Awaitility hết hạn, `@ApplicationModuleListener` vẫn có thể đang chạy trên executor Spring. **Không shutdown shared Spring executor từ `@AfterEach`**. Dùng correlation ID riêng, lưu diagnostics, giữ DB/test fixture đủ lâu hoặc cô lập môi trường test để không làm nhiễm test khác.

### Báo lỗi đúng nơi

- Timeout trước `gate.published`: producer chưa tới mốc publish, bean/test gate chưa wire hoặc T1 đang tắc.
- Query source trước commit bị block: pool exhaustion/locking/connection issue.
- Producer `Future.get` lỗi: T1 rollback/commit failure hoặc gate error.
- Phase probe không có ID sau commit: transaction/probe registration/synchronization.
- Awaitility consumer timeout: listener/T2/registry/executor.
- Cleanup `awaitTermination` fail: worker producer do test tạo chưa dừng.

Không gộp cả sáu thành một thông báo “async test flaky”.

## 25. Thiết kế quality gate CI chống hồi quy race

~~~mermaid
flowchart LR
    PR["Pull request"] --> ARCH["ApplicationModules.verify()"]
    ARCH --> PUB["Producer event contract"]
    PUB --> GATE["Pre-commit gate IT"]
    GATE --> RB["Rollback phase IT"]
    RB --> CON["After-commit consumer IT"]
    CON --> REL["Registry/outbox recovery"]
    REL --> GO{"Gates bắt buộc đạt?"}
    GO -- "Có" --> MERGE["Merge/release"]
    GO -- "Không" --> FIX["Sửa timing, transaction, delivery"]
~~~

| Gate | Rủi ro được bảo vệ | Bằng chứng |
| --- | --- | --- |
| `ApplicationModules.verify()` | Dependency cycle, import `internal` sai | Architecture pass |
| `@ApplicationModuleTest` + `PublishedEvents` | Producer không phát event/ID sai | Event type/payload |
| **Commit gate IT** | Consumer đọc trước T1 commit; hiểu nhầm flush | Source invisible + after-commit probe |
| **Rollback IT** | Ghost event cho T1 rollback | AFTER_ROLLBACK vs AFTER_COMMIT |
| Cross-module consumer IT | Sau commit listener không chạy/T2 rollback | Public task state |
| Postgres Testcontainers | Isolation/locking/constraint khác H2 | DB behavior production-like |
| Event publication registry/outbox | Durable recovery/dual-write loss | Pending/completed/restart |
| Reliability/concurrency | Duplicate, ordering, retry | Idempotent business effect |

### Negative controls nên khiến test đỏ

Trong nhánh kiểm thử có chủ đích:

1. Thay `@ApplicationModuleListener` bằng `@Async @EventListener` và dùng faulty listener probe để phát hiện early read.
2. Bỏ `@Transactional` ở producer: test seam assertion active transaction phải fail.
3. Di chuyển `publishEvent` ra ngoài T1: rollback/phase tests phải cho thấy semantics khác.
4. Bỏ `publishEvent`: producer event-contract test phải fail.
5. Bỏ listener: producer test vẫn có thể xanh, consumer IT phải fail.
6. Thêm import `orders.internal.persistence` từ `fulfillment`: architecture test phải fail.
7. Giữ reader trong snapshot cũ: consumer oracle phải cho thấy cần transaction đọc mới.

Không lưu cố ý các lỗi negative control vào branch merge. Mục tiêu là chứng minh **gate bắt đúng loại lỗi**, sau đó hoàn nguyên.

### Giữ test deterministic trong CI

- Sử dụng latch/barrier, không phụ thuộc CPU speed hoặc `Thread.sleep`.
- Ghi correlation `orderId` và T1 phase vào failure report.
- Không dùng fixed ID trùng giữa jobs.
- Kiểm soát parallelism nếu gate bean hoặc DB fixture có mutable state.
- Không dùng Testcontainers class-scoped DB với cached Spring context trỏ container đã stop.
- Tách container startup, T1 phase wait và T2 eventual wait trong metrics.
- Không tắt race test chỉ vì đôi khi timeout; xác định deadlock/setup hay product bug.

## 26. Kiểm chứng kiến trúc song song với transaction timing

`fulfillment` có thể phụ thuộc event public API của `orders`:

~~~java
import com.example.shop.orders.OrderPlaced;
~~~

Nhưng không nên truy cập JPA implementation nội bộ:

~~~java
// Vi phạm public API module mặc định:
import com.example.shop.orders.internal.persistence.OrderRepository;
~~~

Bài test kiến trúc:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifies_public_module_boundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm tra những ràng buộc Spring Modulith như phụ thuộc vòng, truy cập ngoài public module API và allowed dependencies nếu cấu hình. Nó **không** kiểm tra isolation hay thứ tự event commit, nên phải chạy song song với integration test của bài này.

Khi `fulfillment` chỉ được phụ thuộc `orders`:

~~~java
@ApplicationModule(allowedDependencies = "orders")
package com.example.shop.fulfillment;

import org.springframework.modulith.ApplicationModule;
~~~

Public `OrderQueries` có thể được dùng nếu consumer thật cần authoritative data, nhưng **public API không thay đổi visibility trước commit**. Một query đúng ranh giới module vẫn đọc empty nếu consumer chạy sai phase.

## 27. Troubleshooting các race event/commit

| Triệu chứng | Nguyên nhân có thể | Kiểm chứng ưu tiên |
| --- | --- | --- |
| Consumer thỉnh thoảng không thấy order | `@Async @EventListener` chạy sớm | Controlled gate + early-read probe |
| Debug bằng sleep thì pass | Delay che race | Bỏ sleep, kiểm tra transaction phase |
| `PublishedEvents` xanh, task thiếu | Publication không phải consumer completion | Await T2 qua public API |
| AFTER_COMMIT probe không chạy | Không active transaction, rollback, thiếu listener bean | Test active T1/proxy registration |
| Gate chưa nhận published | Service không vào test hook hoặc tắc T1 | Wiring `@Primary`, thread stack |
| Query trước commit block lâu | DB connection pool nhỏ/lock contention | Pool size, SQL, isolation |
| Test chờ READY khi gate chưa release | Self-deadlock | Release trước Awaitility |
| T1 rollback nhưng consumer tạo task | Early dispatch hoặc external ghost event | AFTER_COMMIT phase, broker/outbox |
| T1 commit nhưng T2 không thấy row | Async executor/transaction consumer lỗi | Listener exception, retry/registry |
| T2 commit rồi test vẫn empty | Stale JPA context/cache/replica | Fresh transaction, routing |
| Source query trong same T1 trả row | Đọc được own uncommitted write | Test transaction **độc lập** |
| Snapshot âm rồi task xuất hiện muộn | Assertion absence quá yếu | Phase test và controlled scheduler |
| Task xuất hiện trùng | Duplicate/replay thiếu idempotency | Reliability test |
| Test chỉ fail trên CI | Timing hoặc shared fixture | Latch, ID isolation, parallelism |
| Spring architecture test đỏ | Consumer import `orders.internal` | Sửa module API |

### Quy trình 10 câu hỏi

1. `publishEvent` có thật nằm trong transaction T1 đang active?
2. Dữ liệu đã `flush` hay `commit`?
3. Transaction nào thực sự sở hữu commit — method hiện tại hay outer T0?
4. Listener là `@EventListener`, `@Async @EventListener` hay hậu commit?
5. Handler chạy thread nào, transaction nào?
6. Reader có dùng independent connection/isolation thích hợp?
7. Producer gate có nằm **trong** transactional method?
8. Test có release gate trước khi chờ outcome hậu commit?
9. Rollback có làm mất durable publication theo adapter được sử dụng?
10. T2 side effect và architecture verification có được assert riêng?

## 28. Bài thực hành theo bằng chứng

### Bài A — Chứng minh flush khác commit

Tạo T1, `saveAndFlush` rồi giữ gate. Test gọi `OrderQueries.exists(id)` từ thread/transaction khác trên PostgreSQL, kỳ vọng false. Cho T1 commit, query lại kỳ vọng true. Giải thích vì sao dùng repository mock không có giá trị cho oracle này.

### Bài B — Phân biệt phase callbacks

Dùng `PhaseRecorder` của mục 12. Sau publish + commit, assert `AFTER_COMMIT` ghi ID. Sau publish + rollback, assert `AFTER_ROLLBACK` ghi ID còn `AFTER_COMMIT` không. Không nhầm probe với listener đã xử lý T2.

### Bài C — Negative control @Async @EventListener

Tạo test-only faulty listener đọc `OrderQueries` bằng transaction độc lập. Giữ T1, chờ `probe.observed` trước commit và chứng minh nguồn không visible. Sửa thành hậu commit, thay test điều khiển để release trước khi chờ callback.

### Bài D — Bỏ @Transactional làm mất transaction

Tạo một path self-invocation và đo `TransactionSynchronizationManager.isActualTransactionActive()` tại test seam. Sửa qua Spring proxy và bảo đảm callback phase hoạt động.

### Bài E — Rollback sau publish

Trong `TransactionTemplate`, insert/flush, publish event, rồi `setRollbackOnly`. Kiểm tra source rollback và phase probe. Nêu giới hạn của assertion `taskExists == false` tức thời.

### Bài F — T1 đã commit nhưng T2 chưa commit

Chèn test-controlled gate trong consumer trước `tasks.save`, khác gate producer. Cho producer commit, chờ consumer entered rồi assert task chưa visible; release consumer gate, Awaitility chờ task. Không giữ cả hai gates theo thứ tự gây deadlock.

### Bài G — External broker ghost event

Dùng fake broker không tham gia T1, publish message trước commit rồi rollback. Kiểm tra fake broker có event “ma”. Thiết kế outbox lưu trong T1 và kiểm tra rollback không để committed intent.

### Bài H — DB pool starvation

Giảm Hikari pool size xuống 1 trong một test isolated, giữ T1 và query từ thread khác. Quan sát connection wait timeout, phân biệt với việc row chưa visible. Trả pool size phù hợp cho suite.

### Bài I — Consumer idempotency sau commit

Phát lại event hoặc chạy nhiều consumer cho cùng ID. Assert chỉ một business effect và registry/retry state phù hợp. Đây là test riêng, không đổi phase của producer.

### Bài J — Ranh giới module và CI

Cố tình import `orders.internal.persistence.OrderRepository` từ `fulfillment` và chạy `ApplicationModules.verify()`; xác nhận đỏ. Thiết lập CI chạy architecture, producer, commit gate, rollback và consumer IT.

### Câu hỏi tự đánh giá

1. `publishEvent` trong T1 có nghĩa T1 đã commit không?
2. `saveAndFlush` khác `commit` về visibility như thế nào?
3. Vì sao `@Async @EventListener` tạo race trước commit?
4. Vì sao synchronous listener đọc được own write cũng chưa chứng minh commit?
5. Khi nào `@ApplicationModuleListener` được dispatch?
6. Vì sao gate phải nằm trong body method `@Transactional`?
7. Vì sao không await listener hậu commit khi gate còn khóa?
8. Probe AFTER_COMMIT chứng minh gì, chưa chứng minh gì?
9. `PublishedEvents` có thể quan sát event của T1 rollback không?
10. Vì sao snapshot âm không chứng minh không có race?
11. Khi nào phải dùng faulty-listener probe với latch?
12. Self-invocation làm callback `@TransactionalEventListener` sai thế nào?
13. Broker publish trước commit và sau commit có những rủi ro gì?
14. Vì sao pool size 1 có thể làm test fail sai nguyên nhân?
15. Vì sao `ApplicationModules.verify()` không thay integration test?

## 29. Checklist trước khi merge kiểm chứng commit race

- [ ] Event được publish trong một transaction active, không chỉ có annotation.
- [ ] Correlation ID duy nhất cho từng test.
- [ ] Gate nằm sau `saveAndFlush`/publish nhưng trước commit.
- [ ] Gate có deadline và luôn được release trong `finally`.
- [ ] Test không có outer `@Transactional` phá timing T1.
- [ ] Source query đọc bằng transaction/kết nối độc lập.
- [ ] DB isolation đã được xác định; production-like engine khi cần.
- [ ] Connection pool đủ cho T1 giữ connection và reader độc lập.
- [ ] Không coi flush là commit.
- [ ] Phân biệt publish event và dispatch hậu commit.
- [ ] Có phase probe hoặc transaction synchronization evidence.
- [ ] Không suy diễn “không bao giờ” từ snapshot âm.
- [ ] Negative control kiểm tra listener sai pha nếu thuộc rủi ro.
- [ ] Sau release gate, chờ T1 hoàn tất và T2 outcome riêng.
- [ ] Consumer được assert qua public API với đúng order ID.
- [ ] Rollback **sau publish** được test rõ ràng.
- [ ] Không dùng sleep đoán scheduling order.
- [ ] Phân biệt producer commit failure và consumer T2 failure.
- [ ] Broker/outbox/registry được kiểm chứng riêng khi có external delivery.
- [ ] Không tự tuyên bố exactly-once từ happy path.
- [ ] Owned worker/gate trong test được cleanup bounded.
- [ ] Không shutdown executor của Spring từ per-method test cleanup.
- [ ] `ApplicationModules.verify()` được đưa vào CI.
- [ ] CI lưu correlation, phase, last observed state để chẩn đoán.

## 30. Ghi nhớ

**Race giữa event và transaction commit** là lỗi **thứ tự xử lý**: producer có thể phát event khi row mới chỉ `flush`, chưa `commit`; consumer trong transaction khác có thể đọc quá sớm. `@Async @EventListener` không ràng buộc execution với commit, trong khi `@TransactionalEventListener(AFTER_COMMIT)` hoặc `@ApplicationModuleListener` giải quyết thời điểm dispatch phù hợp với luồng cần nguồn đã commit.

Một bài test đáng tin phải **giữ T1 mở có chủ đích sau publish**, đọc authoritative data bằng transaction độc lập, quan sát callback phase, release gate rồi chờ **T1 commit và T2 side effect** bằng hai oracle riêng. Kiểm chứng rollback sau publish, faulty-listener negative control, DB isolation và registry/outbox giúp tránh xanh giả. Kết hợp commit race integration với `@ApplicationModuleTest`, `ApplicationModules.verify()` và quality gate CI để ngăn **early dispatch, ghost event, mất publication và phụ thuộc module sai**.






