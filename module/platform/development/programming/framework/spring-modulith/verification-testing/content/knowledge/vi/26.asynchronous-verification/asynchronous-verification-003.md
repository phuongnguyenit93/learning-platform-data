# Chờ điều kiện thay vì chờ một khoảng thời gian cố định

> **Chương:** Async verification  
> **Module đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Kiểm thử những tác vụ bất đồng bộ giữa các application module Spring Modulith bằng điều kiện quan sát được, thay vì đoán độ trễ với `Thread.sleep(...)`. Bài học kết hợp `@ApplicationModuleTest`, sự kiện sau commit, database, integration test, kiểm chứng ranh giới kiến trúc và quality gate CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `Thread.sleep(...)` thường làm test bất đồng bộ **chậm, dễ flaky và thiếu bằng chứng**.
2. Viết điều kiện chờ dựa vào **kết quả nghiệp vụ thật**, có correlation ID, giới hạn thời gian và khoảng thăm dò hợp lý.
3. Sử dụng Awaitility với `await().atMost(...).pollInterval(...).untilAsserted(...)` và `until(...)`.
4. Phân biệt mốc **event được publish**, **transaction producer commit**, **listener chạy**, **side effect commit** và **workflow hoàn tất**.
5. Kiểm thử luồng `orders → fulfillment` dùng `@ApplicationModuleListener` với Spring Boot, JPA và database; tránh bọc sai transaction test.
6. Thiết kế assertion về **không xảy ra hành vi**, timeout, failure, retry, idempotency mà không tạo false positive.
7. Kết hợp module test, architectural test `ApplicationModules.verify()` và integration/E2E tests trong quality gate CI.

**Thông điệp chính:** Đừng hỏi “ngủ bao nhiêu mili giây thì đủ?”. Hãy hỏi **“điều gì phải đúng để kết luận công việc đã xong, và tôi có thể quan sát điều đó ở đâu?”**

## 2. Vấn đề của Thread.sleep trong kiểm thử bất đồng bộ

Giả sử module `orders` vừa tạo một order, phát event `OrderPlaced`; module `fulfillment` xử lý event trên executor và lưu một task.

Một test dễ viết nhưng yếu:

~~~java
@Test
void creates_task_eventually() throws Exception {
    UUID orderId = orders.place("CUS-001");

    Thread.sleep(2_000);

    assertThat(fulfillment.hasTask(orderId)).isTrue();
}
~~~

Bài test này đưa ra giả định ngầm: “Dù máy tính, thread pool, database và CI bận thế nào, consumer cũng hoàn tất trong hai giây.” Giả định không được chứng minh và có thể không ổn định.

### Hai cách thất bại

| Tình huống | `Thread.sleep(2_000)` | Hệ quả |
| --- | --- | --- |
| Consumer hoàn tất sau 40 ms | Vẫn ngủ đủ 2.000 ms | Lãng phí gần như toàn bộ thời gian |
| Consumer hoàn tất sau 2.300 ms | Test assert tại 2.000 ms | Fail dù hệ thống có thể vẫn đúng với contract |
| Consumer không bao giờ được gọi | Ngủ 2.000 ms rồi fail | Lỗi được phát hiện nhưng không có thông tin nguyên nhân |
| Consumer đã fail terminal | Vẫn đợi hết 2.000 ms | Phản hồi muộn |
| Nhiều test chạy song song | Delay biến động | Test lúc xanh lúc đỏ tùy tải |
| Consumer ghi sai order ID | Ngủ lâu không sửa được oracle | Assertion yếu vẫn có thể bỏ sót nếu không theo ID |

**Tăng `sleep` từ 2 giây lên 20 giây không sửa nguyên nhân**: test có thể ít fail do chậm hơn nhưng sẽ luôn lãng phí 20 giây trên nhánh thành công. Nếu hệ thống treo thật, test lại phải đợi lâu hơn mới biết.

### Thất bại kinh điển: “nó chạy trên máy tôi”

~~~text
Developer laptop:  task visible after 60 ms
CI không tải:     task visible after 180 ms
CI tải cao:       task visible after 1.400 ms
CI đôi lúc:       task visible after 2.700 ms

Test: sleep(2.000 ms) rồi assert.
=> Chỉ fail khi CI tải cao, khó tái hiện.
~~~

Các mốc trên chỉ để minh họa biến động, **không phải benchmark Spring Modulith**. Hãy đo độ trễ thực của repository/CI trước khi chọn timeout hoặc SLA.

## 3. Nguyên tắc chờ theo điều kiện (condition-based waiting)

Thay vì đợi “đủ lâu”, test nên liên tục kiểm tra một **predicate** hoặc **assertion** cho tới khi thành công, có thể giới hạn thời gian.

~~~mermaid
flowchart TD
    A["Kích hoạt công việc bất đồng bộ"] --> B["Kiểm tra điều kiện kết thúc"]
    B --> C{"Điều kiện đã đúng?"}
    C -- "Có" --> D["Test pass ngay"]
    C -- "Chưa" --> E{"Đã hết deadline?"}
    E -- "Có" --> F["Test fail với trạng thái cuối"]
    E -- "Chưa" --> G["Chờ poll interval"]
    G --> B
~~~

Bộ ba cơ bản:

- **Điều kiện hoàn thành (oracle):** Ví dụ `fulfillment.hasTask(orderId) == true`. Nó phải bám vào kết quả **thật** của consumer.
- **Deadline:** Ví dụ tối đa 10 giây. Đây là ngân sách của test, không tự động là SLA nghiệp vụ.
- **Nhịp kiểm tra:** Ví dụ mỗi 100 ms. Tránh đọc database quá dày, đồng thời không chờ quá thưa.

Nếu công việc hoàn tất sau 40 ms, test có thể pass ở lần poll đầu hoặc gần nhất, **không đợi hết 10 giây**. Nếu lỗi khiến điều kiện không bao giờ đạt, deadline tạo giới hạn chờ rõ ràng.

### Một ví dụ Awaitility ngắn

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

UUID orderId = orders.place("CUS-001");

await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
                assertThat(fulfillment.hasTask(orderId)).isTrue());
~~~

Kết luận của test: **task cho order cụ thể có thể quan sát được trong vòng 10 giây trong môi trường test**.

Không kết luận từ đó rằng:

- Event chỉ được giao đúng một lần.
- Không có retry hay lỗi trung gian.
- Event publication có thể hồi phục sau restart.
- Hãng vận chuyển bên ngoài đã nhận hàng.
- Mọi workflow ở production đều hoàn tất trước 10 giây.

## 4. Từ lời hứa nghiệp vụ tới điều kiện quan sát được

Một điều kiện chờ tốt bắt đầu bằng câu hỏi “xong *cái gì*?”.

Ví dụ luồng đặt hàng:

~~~text
Client đặt đơn
  -> orders lưu OrderEntity
  -> orders publish OrderPlaced
  -> fulfillment listener xử lý
  -> fulfillment lưu FulfillmentTask
  -> shipping provider cấp nhãn
  -> hãng giao hàng nhận kiện
~~~

Tùy hợp đồng, completion point thay đổi:

| Mục tiêu kiểm thử | Điều kiện hợp lý | Điều kiện chưa đủ |
| --- | --- | --- |
| Producer phát event đúng | `PublishedEvents` chứa `OrderPlaced` đúng ID | Mock publisher được stub |
| Order đã commit | Order đọc được từ transaction mới | Service mới gọi `save(...)` |
| Fulfillment tạo task | `FulfillmentQueries.hasTask(id) == true` sau commit | Event được publish hoặc callback bắt đầu |
| Nhãn vận chuyển được tạo | State `LABEL_READY` và external receipt theo hợp đồng | HTTP provider trả 202 Accepted |
| Tất cả các nhánh workflow hoàn tất | State terminal của orchestrator được lưu sau các nhánh bắt buộc | Một consumer đơn lẻ đã xử lý |
| Event xử lý lại an toàn | Không có side effect trùng, failure handling hợp lệ | Chỉ kiểm tra task tồn tại |

**Đừng đợi một tín hiệu yếu rồi tuyên bố một hợp đồng mạnh.** Thấy event trong `PublishedEvents` chỉ nói producer đã publish, không chứng minh listener async đã commit.

### Thành phần của một oracle đủ tốt

Một oracle thực dụng gồm:

1. **Entity/correlation:** Query chính xác `orderId` vừa tạo.
2. **Outcome:** Trạng thái hoặc dữ liệu mà nghiệp vụ yêu cầu.
3. **Visibility:** Dữ liệu đã có thể đọc qua API/repository phù hợp sau commit.
4. **Terminal semantics:** Có phân biệt đang xử lý với thất bại không?
5. **Time budget:** Nếu chưa đạt, test fail trong thời hạn hữu hạn.
6. **Diagnostic:** Khi fail, báo ID và trạng thái cuối/exception nếu có thể.

## 5. Tìm hiểu Awaitility: until và untilAsserted

Awaitility là thư viện giúp đợi điều kiện bất đồng bộ với timeout và polling. Trong Spring Boot test projects, Awaitility có thể được kéo vào gián tiếp qua starter test tùy phiên bản; nếu không có thì thêm `org.awaitility:awaitility` vào dependency test với version tương thích.

### 5.1. until: predicate trả về boolean

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .until(() -> fulfillment.hasTask(orderId));
~~~

Dạng này phù hợp khi predicate chỉ cần trả true/false.

Hoặc chỉ rõ nhịp poll:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .until(() -> fulfillment.hasTask(orderId));
~~~

### 5.2. untilAsserted: assertion giàu ngữ nghĩa

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            var state = fulfillment.statusFor(orderId);
            assertThat(state).isEqualTo(PreparationState.READY);
        });
~~~

`untilAsserted` thử lại assertion cho tới khi nó không ném `AssertionError` hoặc hết hạn. Nó giúp test diễn tả kết quả kỳ vọng rõ và thường cung cấp thông tin assertion có ích khi timeout.

### 5.3. Điều kiện có nhiều thuộc tính

Khi kết quả nghiệp vụ cần nhiều trường, chờ **một trạng thái nhất quán**:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            var snapshot = fulfillment.findTask(orderId);

            assertThat(snapshot).isPresent();
            assertThat(snapshot.orElseThrow().orderId())
                    .isEqualTo(orderId);
            assertThat(snapshot.orElseThrow().status())
                    .isEqualTo(PreparationState.READY);
        });
~~~

Đây là trích đoạn **giả định có API `findTask(UUID)` trả `Optional<TaskSnapshot>`**. Nó không thuộc bộ source hoàn chỉnh ở mục 8–10; khi triển khai hãy thêm API tương ứng hoặc dùng `statusFor(...)` được xây dựng trong ví dụ.

**Tránh split các assertion thành nhiều lần đọc không đồng nhất** nếu state có thể đổi giữa các lần đọc. Đọc một snapshot và assert nhiều thuộc tính trên cùng snapshot giúp suy luận chính xác hơn.

### 5.4. Khi nào nên dùng predicate, khi nào dùng assertion?

| Tình huống | Ưu tiên | Lý do |
| --- | --- | --- |
| Kiểm tra task đã tồn tại | `until(() -> hasTask(id))` | Gọn và dễ đọc |
| Kiểm tra nhiều trường của DTO | `untilAsserted(...)` | Hiển thị kỳ vọng rõ |
| Kiểm tra state terminal cụ thể | `untilAsserted(...)` | Message khi fail hữu ích |
| Cần dừng sớm nếu FAILED | Tách logic phát hiện terminal failure | Tránh poll đến deadline khi không thể thành công |
| Kiểm tra không bao giờ xảy ra hành vi | Không chỉ dùng `until(!condition)` | Có thể pass ngay, xem mục 15 |

## 6. Thiết lập thời hạn và nhịp poll có cơ sở

Không nên chọn `atMost` và `pollInterval` bằng cảm tính. Chúng phục vụ hai mục tiêu khác nhau.

- **Timeout:** Giới hạn tổng thời gian chờ. Chọn dựa vào yêu cầu kiểm thử, tải CI, độ trễ database và event scheduling.
- **Poll interval:** Tần suất kiểm tra. Khoảng quá nhỏ tạo tải lên DB/HTTP; khoảng quá lớn tăng latency của test.
- **Poll delay:** Thời gian đợi trước lần poll đầu nếu có cấu hình; không lạm dụng một delay lớn khiến test mất lợi thế “pass ngay khi điều kiện đúng”.

Một bảng minh họa, không phải chuẩn mặc định:

| Loại test | Timeout thử nghiệm ban đầu | Poll interval thử nghiệm | Lưu ý |
| --- | --- | --- | --- |
| Task local với executor | 2–5 giây | 20–100 ms | Chọn theo CI thực tế |
| Module event + database | 5–10 giây | 50–200 ms | Có commit và JPA |
| HTTP API polling | 10–20 giây | 100–500 ms | Tránh gọi endpoint quá dày |
| Retry qua broker hoặc registry | Tùy policy thực tế | Phù hợp backoff | Không đặt deadline ngắn hơn chu kỳ retry |
| External provider sandbox | Theo hợp đồng provider | Có rate limit | Không suy ra SLA production |

Các con số trên chỉ là **điểm bắt đầu để đo**. Nếu hệ thống phải bảo đảm 99% workflow dưới 2 giây, một integration test timeout 20 giây **không tự kiểm tra SLA đó**. SLA cần đo riêng bằng thống kê latency, tải và percentiles.

### Dùng một cấu hình chung khi có lý do

~~~java
private static final Duration ASYNC_TIMEOUT =
        Duration.ofSeconds(10);

private static final Duration POLL_INTERVAL =
        Duration.ofMillis(100);
~~~

Dùng constants giúp nhiều test giữ chính sách nhất quán. Nhưng test cần broker retry 30 giây không nên buộc dùng cùng timeout với một task local 100 ms chỉ để “đồng bộ style”.

## 7. Vì sao correlation ID là điều kiện tiên quyết?

Nếu test viết:

~~~java
await().atMost(Duration.ofSeconds(10))
        .until(() -> fulfillment.countTasks() > 0);
~~~

Nó có thể pass nhờ task từ test trước. **Có task bất kỳ** khác với **task của yêu cầu vừa tạo**.

Cần viết:

~~~java
UUID orderId = orders.place("CUS-UNIQUE");
await().atMost(Duration.ofSeconds(10))
        .until(() -> fulfillment.hasTask(orderId));
~~~

Hãy phân biệt:

- **Correlation ID:** Liên hệ event, request, log và side effect của cùng một workflow.
- **Aggregate ID:** Ví dụ `orderId`; đủ làm correlation khi mỗi order tương ứng một workflow theo thiết kế.
- **Idempotency key:** Giúp server nhận biết hai HTTP request retry là cùng một thao tác logic; không tự động trùng với correlation ID.
- **Event ID:** Phân biệt từng lần publication để deduplicate/replay khi cần.

Với test chạy song song, dùng dữ liệu riêng cho từng ca, không dựa vào ID tuần tự luôn bằng 1 hoặc database hoàn toàn rỗng. Nếu shared database không thể cô lập, phải có chiến lược fixture/schema/transaction cụ thể.

## 8. Ví dụ Spring Modulith: cấu trúc module

Ta dùng ứng dụng có hai application module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderCommands.java                   # Public API
│   ├── OrderPlaced.java                    # Event công khai
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/
    ├── FulfillmentQueries.java             # Public API
    ├── PreparationState.java              # Trạng thái công khai
    └── internal/
        ├── OrderPreparationListener.java
        ├── FulfillmentQueryService.java
        └── persistence/
            ├── FulfillmentTask.java
            └── FulfillmentTaskRepository.java
~~~

Theo chiến lược phát hiện module mặc định, `orders` và `fulfillment` là module trực tiếp dưới package ứng dụng `com.example.shop`. API công khai mặc định thuộc package root, còn `internal` là implementation riêng.

**Hợp đồng minh họa:**

1. Tạo order hợp lệ trả `orderId`.
2. `orders` publish `OrderPlaced(orderId)` bên trong transaction.
3. `fulfillment` nhận event sau commit và tạo một task.
4. `FulfillmentQueries.statusFor(orderId)` trả `READY` khi task đã commit.
5. `NOT_OBSERVED` chỉ nghĩa là chưa quan sát thấy task; **không** chứng minh đang xử lý hay đã thất bại.

## 9. Producer: phát OrderPlaced trong transaction

### 9.1. Spring Boot entry point

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

`@EnableAsync` cho phép các listener async chạy theo executor của Spring. Bật annotation không tự cung cấp durable queue/retry policy hoặc xác nhận business completion.

### 9.2. Public API và event

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

Typed event ở public API không nên chứa JPA entity, lazy proxy hoặc repository nội bộ của producer.

### 9.3. JPA persistence của orders

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

Ví dụ sử dụng Jakarta Persistence tương thích Java 17+ và JPA có `GenerationType.UUID`. Với dự án dùng sequence hoặc identity khác, thay chiến lược ID theo database.

### 9.4. Application service phát event

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

`publishEvent` được gọi **bên trong transaction T1**. Consumer sau commit có thể bắt đầu sau khi method trả về, và transaction T2 của consumer cần hoàn tất trước khi task được đọc thấy. Test không nên gắn ý nghĩa “fulfillment đã sẵn sàng” cho việc method `place(...)` trả ID.

## 10. Consumer: side effect có thể quan sát

### 10.1. Public query API

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

`NOT_OBSERVED` có nghĩa rất hẹp: chưa nhìn thấy task. Nó không đủ phân biệt đang xử lý, thất bại terminal hay order ID không tồn tại. Production có thể dùng trạng thái đầy đủ hơn, như `ACCEPTED`, `PROCESSING`, `READY` và `FAILED`.

### 10.2. Persistence

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

### 10.3. Listener hậu commit

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

`@ApplicationModuleListener` thường xử lý event **bất đồng bộ, sau commit và trong transaction riêng** theo cơ chế Spring Modulith tương ứng. Vì vậy gọi `orders.place(...)` xong không đảm bảo task đã được ghi.

**Lưu ý quan trọng về idempotency:** `existsById` rồi `save` không an toàn tuyệt đối khi hai invocation xử lý event trùng đồng thời. Primary key ngăn hai row trùng, nhưng invocation thứ hai có thể ném unique-constraint exception. Phần 18 đề xuất test tương ứng.

### 10.4. Query API đọc state của consumer

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

Test quan sát qua **public API của module consumer**, không import repository JPA nội bộ. Khi mỗi poll thực hiện một lời gọi với transaction đọc riêng phù hợp, nó có thể thấy row đã commit của listener.

## 11. Module test: PublishedEvents là oracle của producer

Trước khi test consumer, hãy xác minh producer thật sự phát event.

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
    void publishes_order_placed_for_created_order(
            PublishedEvents events) {

        UUID id = orders.place("CUS-PUBLISH");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }

    @Test
    void invalid_request_publishes_nothing(
            PublishedEvents events) {

        assertThatThrownBy(() -> orders.place(" "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderPlaced.class)).isEmpty();
    }
}
~~~

**Bằng chứng từ test trên:** Producer phát event có đúng kiểu/ID; input rỗng được từ chối trước khi publish.

**Không phải bằng chứng:** Listener đã chạy, database consumer commit hay publication còn sống sau restart. `PublishedEvents` quan sát event được phát; publisher có thể phát bên trong T1 trước khi transaction commit, và listener ở module khác có thể không được nạp trong context `@ApplicationModuleTest`.

`anySatisfy` chỉ chứng minh **ít nhất một event khớp**, không phải chính xác một. Nếu hợp đồng đòi cardinality, cần assertion đếm event bằng API phù hợp version thư viện.

## 12. Integration test: Awaitility thay cho Thread.sleep

Đây là điểm trọng tâm của bài. Test phải có **cả module producer và consumer**, transaction manager, listener thực và database.

**`src/test/java/com/example/shop/OrderFulfillmentAsyncTest.java`**

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
        "spring.datasource.url=jdbc:h2:mem:orders-fulfillment;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderFulfillmentAsyncTest {

    @Autowired
    OrderCommands orders;

    @Autowired
    FulfillmentQueries fulfillment;

    @Test
    void eventually_creates_task_after_order_commit() {
        String customerId = "CUS-" + UUID.randomUUID();

        UUID orderId = orders.place(customerId);
        assertThat(orderId).isNotNull();

        await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() ->
                        assertThat(fulfillment.statusFor(orderId))
                                .isEqualTo(PreparationState.READY));
    }
}
~~~

### Vì sao test này tốt hơn ngủ cố định?

- Test có thể pass ngay khi task `READY` xuất hiện, không đợi hết timeout.
- Kết quả dựa trên **state nghiệp vụ có thể đọc**, không dựa vào thời gian ước đoán.
- Assertion gắn đúng `orderId` của lần chạy.
- Timeout hữu hạn, giúp CI không treo vô tận.
- Nếu listener bỏ annotation, transaction rollback hoặc ghi sai ID, điều kiện không đạt và test thất bại.

### Vì sao dùng @SpringBootTest(NONE)?

Bằng chứng cần là giao tiếp Java/event giữa các module và database, **không phải HTTP server**. `WebEnvironment.NONE` không mở embedded server, giảm phạm vi thừa. Khi muốn kiểm tra HTTP request và endpoint trạng thái, dùng test `RANDOM_PORT` riêng.

### Vì sao không đặt @Transactional trên test?

Nếu test method được gắn `@Transactional`, lệnh `orders.place(...)` có thể tham gia transaction do test mở. Test framework thường rollback transaction này khi kết thúc; listener `AFTER_COMMIT` có thể không chạy do không có commit thật.

Trong test trên, transaction của service producer tự commit qua Spring proxy, cho phép listener hậu commit hoạt động theo cấu hình. Cần dọn dữ liệu test bằng fixture/cô lập riêng, không dùng outer rollback để “tiện cleanup” nếu điều được kiểm chứng chính là after-commit.

## 13. Chờ điều kiện qua HTTP polling

Một client bên ngoài có thể nhận `202 Accepted` khi tạo order, sau đó poll endpoint trạng thái.

~~~mermaid
sequenceDiagram
    participant C as Client/test
    participant API as Orders API
    participant F as Fulfillment status API

    C->>API: POST /api/orders
    API-->>C: 202 + orderId
    loop Cho đến READY hoặc deadline
        C->>F: GET /api/fulfillments/{id}/preparation
        F-->>C: PROCESSING hoặc READY
    end
    Note over C,F: READY là kết quả cần, 202 ban đầu không phải completion
~~~

### Contract minh họa

- `POST /api/orders` trả `202` cùng `orderId`.
- `GET /api/fulfillments/{id}/preparation` trả JSON trạng thái.
- Trạng thái `READY` nghĩa là task đã được commit theo hợp đồng.
- `FAILED` nghĩa là nghiệp vụ thất bại terminal, không tiếp tục poll.
- `UNKNOWN` hoặc HTTP 404 phải được xử lý riêng, không coi là mãi mãi pending.

HTTP status thực tế tùy thiết kế. Một status resource có thể luôn trả HTTP 200 cùng field `state`; không bắt buộc phải trả HTTP 202 ở mọi lần poll.

### Test HTTP với RANDOM_PORT

Ví dụ dưới đây là **khung test** giả định các endpoint và JSON contract đã được triển khai:

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
class OrderHttpPollingTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void client_waits_for_ready_outcome() {
        var accepted = http.postForEntity(
                "/api/orders",
                Map.of("customerId", "CUS-" + UUID.randomUUID()),
                JsonNode.class);

        assertThat(accepted.getStatusCode())
                .isEqualTo(HttpStatus.ACCEPTED);
        assertThat(accepted.getBody()).isNotNull();

        String orderId = accepted.getBody()
                .path("orderId").asText();

        assertThat(orderId).isNotBlank();

        await()
                .atMost(Duration.ofSeconds(15))
                .pollInterval(Duration.ofMillis(200))
                .untilAsserted(() -> {
                    var status = http.getForEntity(
                            "/api/fulfillments/{id}/preparation",
                            JsonNode.class,
                            orderId);

                    assertThat(status.getStatusCode())
                            .isEqualTo(HttpStatus.OK);
                    assertThat(status.getBody()).isNotNull();
                    assertThat(status.getBody()
                            .path("orderId").asText())
                            .isEqualTo(orderId);
                    assertThat(status.getBody()
                            .path("state").asText())
                            .isEqualTo("READY");
                });
    }
}
~~~

**Giới hạn:** Test này giả định khi chưa READY endpoint không trả HTTP 200/READY, và khi READY trả `200` cùng body. Nếu endpoint trả 404 tạm thời, `getForEntity`/error handler có thể sinh response hoặc exception theo client/config; điều kiện chờ và chính sách retry phải tương thích với contract. Không mặc định bỏ qua mọi HTTP 500 — đó có thể là lỗi terminal hoặc lỗi mà test cần hiển thị.

Trong production, việc kiểm tra trạng thái qua mạng còn liên quan authentication, rate limit, consistency và timeouts của HTTP client, nên chọn poll interval phù hợp.

## 14. Trạng thái thất bại terminal: đừng đợi đến deadline vô ích

Giả sử workflow công bố trạng thái:

~~~java
public enum WorkflowState {
    ACCEPTED,
    PROCESSING,
    RETRY_WAIT,
    READY,
    FAILED
}
~~~

Nếu consumer đã ghi `FAILED`, việc chờ tới 10 giây trong khi liên tục assert phải `READY` sẽ chỉ làm test chậm và khó chẩn đoán.

### Mô hình logic của điều kiện chờ

~~~text
while (time < deadline):
    state = query(workflowId)

    if state == READY:
        return success

    if state == FAILED:
        fail("Workflow failed: " + reason)

    if state in [ACCEPTED, PROCESSING, RETRY_WAIT]:
        wait(pollInterval)

fail("Timed out; last state=" + state)
~~~

Đây là **pseudocode diễn tả chính sách**. Không được dùng `Thread.sleep` cố định thay cho cả cơ chế; nếu dùng thư viện polling, tận dụng điều kiện dừng sớm và fail-fast dựa vào terminal state theo API tương thích version.

### Với Awaitility

Một lựa chọn là định nghĩa điều kiện nhận diện lỗi terminal và ném một exception có ý nghĩa, đồng thời cấu hình Awaitility **không bỏ qua exception ấy** theo API/version đang dùng. Không nên viết một `untilAsserted` mà mọi exception từ HTTP/DB đều bị ignore, vì lỗi không thể phục hồi sẽ bị biến thành timeout khó hiểu.

**Ranh giới khái niệm:**

| Kết quả quan sát | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `READY` | Thành công nghiệp vụ theo contract | Pass |
| `FAILED` | Thất bại terminal đã được server ghi nhận | Dừng sớm, fail rõ |
| `ACCEPTED/PROCESSING/RETRY_WAIT` | Chưa terminal | Poll tiếp trong deadline |
| Chưa thấy state trước deadline | Chưa quan sát được completion | Timeout, không tự gán business FAILED |

**Timeout của test không bằng `FAILED` của nghiệp vụ.** Workflow có thể hoàn tất ngay sau khi test deadline hết, nhưng test vẫn phải fail để báo chưa đạt tiêu chí thời gian/khả năng quan sát trong môi trường đó.

## 15. Assertion về “không xảy ra”: bẫy của until(!condition)

Đây là khác biệt quan trọng giữa **chờ một điều xuất hiện** và **khẳng định một điều không xảy ra**.

Một test sai:

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> !fulfillment.hasTask(orderId));
~~~

Nếu chưa có task ngay sau lệnh tạo order, predicate sẽ **true ngay** và test pass, dù listener sai có thể tạo task vài mili giây sau. Test ấy không chứng minh event không bao giờ được xử lý.

### Khi cần chứng minh event bị chặn bởi rollback

Ví dụ producer publish rồi transaction rollback. Một chiến lược mạnh hơn gồm:

1. Xác nhận transaction T1 thực sự rollback bằng dữ liệu orders.
2. Xác nhận listener đang dùng pha `AFTER_COMMIT`, không cấu hình fallback ngoài transaction.
3. Quan sát cơ chế giao sự kiện/transaction synchronization hoặc event publication state phù hợp.
4. Nếu cần, dùng test hook/controlled executor có thể drain các tác vụ liên quan trước assertion.
5. Định nghĩa observation window có cơ sở khi contract yêu cầu “không phát sinh trong X giây”, không gọi đó là “không bao giờ”.

### Awaitility during: chỉ khi yêu cầu là một khoảng ổn định

Awaitility có các khả năng diễn tả điều kiện phải duy trì trong một khoảng nhất định, ví dụ `during(Duration)` tùy version:

~~~java
await()
        .during(Duration.ofMillis(500))
        .atMost(Duration.ofSeconds(2))
        .until(() -> !fulfillment.hasTask(orderId));
~~~

**Quan trọng:** Ví dụ này chỉ giúp kiểm tra sự vắng mặt **trong một cửa sổ thời gian 500 ms**, không chứng minh mọi tác vụ async trong hệ thống đã kết thúc, không chứng minh trạng thái vắng mặt vĩnh viễn. Với rollback và eventual scheduling, cần kết hợp kiểm soát transaction/dispatch để có bằng chứng mạnh.

### Cách làm tốt hơn cho negative test

Nếu hợp đồng là “không publish event khi validation thất bại”, producer module test có thể assert `PublishedEvents.ofType(...).isEmpty()` sau khi lời gọi validation ném exception **trước khi publish**. Đó là một điều kiện đồng bộ có cơ sở.

Nếu hợp đồng là “không tạo task từ order rollback”, test cần thêm kiến thức về transaction phase và execution lifecycle; không đủ chỉ kiểm tra consumer query ngay lập tức.

## 16. Chờ bằng CountDownLatch khi cần điều khiển trình tự

Polling là phù hợp khi quan sát state cuối cùng. Tuy nhiên, để kiểm thử race condition, ordering hoặc “listener đã bắt đầu nhưng chưa ghi”, có thể dùng các primitive đồng bộ hóa trong test fixture.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

CountDownLatch entered = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

// Trong controlled test port/gateway:
entered.countDown();

if (!release.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Test gate not released");
}

// Tiếp tục delegate vào implementation thực.
~~~

**Đây là trích đoạn trong test gateway**, không phải implementation production. Trong test:

1. Cấu hình gateway chặn bước tạo task.
2. Kích hoạt order/event.
3. Dùng `entered.await(5, TimeUnit.SECONDS)` xác nhận listener đi vào gateway.
4. Trước `release`, assert task chưa tồn tại.
5. `release.countDown()`, rồi chờ task xuất hiện bằng Awaitility.
6. Luôn release trong `finally` để không treo executor nếu assertion thất bại.

Mẫu này chứng minh **listener invocation** khác **consumer completion** bằng trình tự được kiểm soát, không phụ thuộc vào `Thread.sleep`.

### So sánh polling và latch

| Kỹ thuật | Mục tiêu tốt nhất | Không nên dùng để |
| --- | --- | --- |
| Awaitility trên public query API | Chờ kết quả nghiệp vụ cuối | Thay thế contract của kết quả cần quan sát |
| `CountDownLatch` trong test fixture | Đồng bộ một mốc thực thi xác định | Suy ra transaction đã commit nếu latch đặt trước commit |
| `CompletableFuture`/promise từ test-controlled dependency | Điều phối kết quả của task đang kiểm thử | Tuyên bố hệ thống ngoài đã xử lý nếu future chỉ là enqueue |
| `Thread.sleep` | Rất ít: mô phỏng delay trong fake có kiểm soát | Chứng minh async flow đã hoàn thành |

**Đừng biến latch “listener entered” thành oracle “task persisted”.** Chúng là hai mốc khác nhau.

## 17. Rollback và transaction trong Spring Modulith

Giả sử producer:

~~~text
BEGIN T1
    INSERT order
    publish OrderPlaced(orderId)
    xảy ra lỗi
ROLLBACK T1
~~~

`PublishedEvents` có thể đã quan sát event dù T1 rollback. Với `@ApplicationModuleListener` xử lý sau commit, consumer không nên tạo task cho transaction rollback.

### Tạo rollback có chủ đích

Ví dụ trích đoạn trong integration test có `OrderCommands` và `TransactionTemplate` được inject:

~~~java
@Autowired
TransactionTemplate transactions;

@Test
void rolls_back_an_order_after_publication() {
    UUID orderId = transactions.execute(status -> {
        UUID created = orders.place("CUS-ROLLBACK");
        status.setRollbackOnly();
        return created;
    });

    assertThat(orderId).isNotNull();

    // Cần một public query API hoặc test fixture riêng để
    // xác nhận row order không commit; không suy ra từ UUID.
}
~~~

Ví dụ này **chưa phải test hoàn chỉnh về không có side effect**. Nếu chỉ gọi `fulfillment.statusFor(orderId)` ngay sau transaction rồi thấy `NOT_OBSERVED`, side effect sai có thể xuất hiện sau một khoảng delay.

Test đầy đủ phải kiểm tra rollback dữ liệu, pha listener, chính sách fallback và cơ chế quan sát đủ mạnh đối với tác vụ async. Không gắn `@Transactional` lên test consumer after-commit nếu test sẽ rollback toàn bộ transaction và ngăn listener chạy như production.

## 18. Retry, duplicate delivery và idempotency: đợi đúng điều kiện sau lỗi

Đối với những workflow có retry, consumer có thể nhận event nhiều lần, hoặc event được gửi lại sau khi lỗi.

~~~text
OrderPlaced(42) -> consumer attempt #1 -> lỗi tạm thời
                 -> consumer attempt #2 -> ghi task
                 -> consumer attempt #3 do replay -> ?
~~~

**Bằng chứng cần thu không chỉ là “cuối cùng có task”.** Cần thêm:

- Task thuộc đúng order ID.
- Số side effect phù hợp với hợp đồng (ví dụ chỉ một task).
- Handler không mắc kẹt ở lỗi duplicate/unique constraint.
- Failure được ghi nhận theo policy; retry/resubmission không nhân đôi tác động.
- Nếu có durable publication registry, publication được xử lý/hoàn tất theo adapter.

### Race condition của ví dụ

Handler:

~~~java
if (!tasks.existsById(event.orderId())) {
    tasks.save(new FulfillmentTask(event.orderId()));
}
~~~

Hai invocation đồng thời có thể đều thấy “chưa tồn tại” và cùng insert. Primary key ngăn hai row nhưng một invocation có thể bị unique violation. Thiết kế production nên có idempotent upsert hoặc duplicate-key handling đúng transaction, cùng test concurrency.

### Chờ thành công cuối cùng không bảo vệ mọi lỗi

~~~java
await().atMost(Duration.ofSeconds(10))
        .until(() -> fulfillment.statusFor(orderId)
                == PreparationState.READY);
~~~

Đoạn này chứng minh READY đã xuất hiện, **không chứng minh không có retry lỗi**. Khi idempotency/reliability là cam kết, bổ sung integration test quan sát publication state, duplicate attempts, unique constraints và recovery.

**Không giả định Spring Modulith luôn tự retry vô hạn.** Khả năng theo dõi publication chưa hoàn tất và resubmit phụ thuộc Event Publication Registry adapter, dependency, version và cấu hình cụ thể.

## 19. Database production-like: Polling cần đọc state thật

H2 giúp ví dụ gọn và nhanh, nhưng transaction isolation, locking, native SQL và unique constraints có thể khác PostgreSQL/MySQL production. Khi test claim liên quan đến các tính chất đó, dùng Testcontainers với database tương thích.

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
class OrderFulfillmentPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Inject OrderCommands và FulfillmentQueries,
    // chạy cùng oracle await status == READY như mục 12.
}
~~~

Đây là **khung cấu hình**, chưa phải method test hoàn chỉnh. Cần dependency `spring-boot-testcontainers`, Testcontainers Jupiter/PostgreSQL, driver và container runtime. `@ServiceConnection` thuộc Spring Boot 3.1+, phải dùng version tương thích.

### Cạm bẫy transaction khi poll

Nếu test hoặc query giữ transaction snapshot cũ, nhiều lần đọc có thể vẫn không thấy row vừa commit từ listener khác. Cần:

- Không bọc toàn bộ polling trong transaction rollback của test.
- Khi cần, mở transaction đọc ngắn qua public query API mỗi lần poll.
- Chú ý isolation level của database, cache/JPA persistence context và replica lag.
- Không đọc cùng một managed entity cũ mãi mà kỳ vọng nó tự refresh.
- Với eventually consistent read model, kiểm tra version hoặc state cuối từ điểm quan sát mà contract đã chọn.

**Polling không sửa được stale-read design.** Nó chỉ thử lại; nếu mỗi lần thử đều nhìn snapshot cũ, tăng timeout không giúp ích.

## 20. Event publication registry: chờ registry hay chờ kết quả nghiệp vụ?

Spring Modulith có cơ chế Event Publication Registry để theo dõi event publications với adapter phù hợp. Nhưng ba mốc thường bị nhầm:

| Tín hiệu | Được dùng để chứng minh | Không đủ để chứng minh |
| --- | --- | --- |
| `PublishedEvents` chứa event | Producer đã publish | Consumer đã xử lý |
| Registry đánh dấu publication completed | Listener xử lý xong theo semantics registry | External workflow đã hoàn thành |
| `FulfillmentQueries.statusFor(id) == READY` | Task fulfillment đã xuất hiện theo API | Event có thể phục hồi qua restart |
| Receipt từ shipping provider | Bước ngoài đạt trạng thái được provider xác nhận | Mọi module nội bộ đều đúng kiến trúc |

Ví dụ listener chỉ gọi external API và nhận HTTP 202 để enqueue tạo nhãn. Listener có thể trả về thành công, registry có thể hoàn tất publication, **nhưng nhãn vẫn chưa được tạo**. Nếu contract cần “label ready”, phải đợi callback/polling receipt của provider hoặc workflow state do module sở hữu ghi sau khi nhận kết quả cuối.

### Recovery tests

Khi yêu cầu là event không mất qua restart:

1. Dùng publication registry adapter persistent thật.
2. Cố ý làm consumer thất bại.
3. Xác nhận publication được ghi nhận đang pending theo cơ chế adapter.
4. Gỡ lỗi và thử resubmit/restart theo chính sách hỗ trợ.
5. Chờ side effect nghiệp vụ với deadline hợp lý.
6. Xác nhận idempotency và trạng thái publication theo contract.

Không hard-code tên bảng hay API resubmit cho mọi phiên bản; test với dependency/cấu hình thực tế của dự án.

## 21. Kiểm chứng ranh giới kiến trúc khi dùng event

Trong ví dụ, `fulfillment` import public event:

~~~java
import com.example.shop.orders.OrderPlaced;
~~~

Điều đó phù hợp API mặc định của module `orders`. Nó không nên import:

~~~java
// Vi phạm ranh giới package mặc định của Modulith:
import com.example.shop.orders.internal.persistence.OrderEntity;
~~~

Một integration test có thể vẫn xanh dù consumer truy cập JPA entity nội bộ của producer. Vì vậy cần architectural test riêng:

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

`ApplicationModules.verify()` kiểm tra dependency graph, vòng phụ thuộc và khả năng truy cập public API theo mô hình Spring Modulith, cùng allowed dependency nếu cấu hình. Nó **không** chứng minh event consumer đã commit, nên không thay `OrderFulfillmentAsyncTest`.

Nếu `fulfillment` chỉ được phụ thuộc `orders`, có thể khai báo:

~~~java
@ApplicationModule(allowedDependencies = "orders")
package com.example.shop.fulfillment;

import org.springframework.modulith.ApplicationModule;
~~~

Whitelist cần phản ánh thiết kế thật; không thêm mọi module để test xanh. Khi dùng `@NamedInterface` cho event package, cập nhật whitelist theo named interface phù hợp.

## 22. Troubleshooting: điều kiện không bao giờ đúng

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `PublishedEvents` xanh, Awaitility timeout | Consumer listener không được bootstrap | Kiểm tra context và annotation |
| Event được publish, consumer không chạy | T1 rollback hoặc listener sau commit không có transaction phù hợp | Kiểm tra transaction phase |
| Test có `@Transactional` và luôn timeout | Test rollback, không có AFTER_COMMIT | Cho producer commit qua service proxy |
| Listener có log “started”, task không xuất hiện | T2 lỗi/rollback hoặc chưa xong | Kiểm tra exception và DB state |
| Task có thật nhưng query không thấy | Snapshot cũ, cache hoặc sai ID | Kiểm tra transaction/isolation, correlation |
| Test flaky ở CI | Executor/DB delay biến động | Dùng Awaitility và đo latency |
| Test pass nhanh dù rollback sai | `until(!condition)` trả true ngay | Thiết kế negative test theo phase/synchronization |
| Polling gây tải quá cao | Interval quá nhỏ | Điều chỉnh interval/backoff |
| API trả 404/500 rồi test chỉ timeout | Bỏ qua exception quá rộng | Phân loại lỗi tạm thời/terminal |
| Retry xảy ra nhưng task trùng/handler lỗi | Idempotency chưa vững | Test duplicate/concurrency |
| Testcontainers chạy chậm | Pull image, startup hoặc migration | Tách thời gian hạ tầng và test logic |
| HTTP status 202 nhưng client tưởng xong | Nhầm acceptance với completion | Công bố endpoint/status terminal rõ |
| Integration xanh nhưng architecture đỏ | Consumer import `internal` | Sửa public API/dependency, giữ `verify()` |

### Các bước điều tra hiệu quả

1. Log `orderId`/`workflowId` từ bước tạo yêu cầu.
2. Kiểm tra transaction producer đã commit chưa.
3. Xác minh producer publish event đúng payload.
4. Xác minh listener consumer được đăng ký và nhận event.
5. Xem exception và transaction commit/rollback của consumer.
6. Truy vấn state cùng ID, tránh stale-read.
7. Nếu có registry, xem publication state và retry policy.
8. Chỉ sau đó mới đánh giá timeout/CI capacity có quá ngắn hay không.

Tăng timeout vô hạn chỉ che lỗi thiết kế. Điều kiện quan sát được và diagnostic mới giúp tìm nguyên nhân.

## 23. Quality gate CI cho kiểm thử bất đồng bộ

~~~mermaid
flowchart LR
    PR["Pull request"] --> U["Unit + adapter tests"]
    U --> A["ApplicationModules.verify()"]
    A --> P["Publisher module tests"]
    P --> I["Consumer Awaitility integration"]
    I --> R["Retry / idempotency / recovery"]
    R --> E["Critical HTTP E2E"]
    E --> G{"Các gate bắt buộc đạt?"}
    G -- "Có" --> M["Cho phép merge/release"]
    G -- "Không" --> F["Chẩn đoán và sửa"]
~~~

| Gate | Bằng chứng | Cách bảo vệ |
| --- | --- | --- |
| Unit/slice | Validation và adapter contract | Chạy mọi PR |
| Architectural verification | Không vượt API/dependency module | `ApplicationModules.verify()` trên mọi PR |
| Producer module | Đúng type/payload event | `@ApplicationModuleTest` + `PublishedEvents` |
| Consumer integration | Side effect sau commit | Awaitility trên public query API |
| Database integration | Transaction/constraint thật | Testcontainers khi cần engine production-like |
| Reliability/recovery | Duplicate, retry và registry | Failure injection và restart khi đã cam kết |
| API E2E | Client thấy terminal outcome | HTTP polling đúng ID |

### Nguyên tắc quản lý thời gian CI

- Chạy unit và architecture sớm để phản hồi nhanh.
- Các test async quan trọng phải có deadline, không treo mãi.
- Đo độ trễ p50/p95 và timeout rate của job integration để chọn `atMost` có cơ sở.
- Không dùng `Thread.sleep` hàng loạt làm tổng suite chậm.
- Tách job hạ tầng khi cần nhưng đừng vô tình skip quality gate bắt buộc.
- Khi test timeout, đính kèm log tương quan của producer/consumer và trạng thái cuối.
- Test data phải cô lập; không phụ thuộc vào thứ tự chạy.
- CI ngăn cả **phụ thuộc sai** và **hồi quy hành vi**; một loại test không thể thay tất cả loại còn lại.

Một lời hứa SLA production cần đo trong môi trường tải phù hợp, không thể suy ra chỉ từ một integration test `await().atMost(10s)` xanh.

## 24. Bài thực hành

### Bài A — Sửa test dùng Thread.sleep

Bắt đầu từ:

~~~java
UUID id = orders.place("CUS-A");
Thread.sleep(3_000);
assertThat(fulfillment.statusFor(id))
        .isEqualTo(PreparationState.READY);
~~~

Hãy chuyển sang Awaitility với `atMost` và `pollInterval` phù hợp. Giải thích vì sao test mới pass sớm khi công việc hoàn tất nhanh và fail có giới hạn khi lỗi thật xảy ra.

### Bài B — Bắt lỗi quên listener

Viết `OrderPublicationTest` và `OrderFulfillmentAsyncTest`. Trong nhánh thực hành, tạm bỏ `@ApplicationModuleListener` khỏi consumer. Giải thích vì sao publisher test vẫn có thể xanh nhưng consumer integration timeout. Khôi phục annotation.

### Bài C — Tạo một race condition có kiểm soát

Dùng `CountDownLatch` hoặc fake test port để tạm chặn listener ngay trước bước ghi DB. Xác nhận listener đã bắt đầu nhưng task chưa xuất hiện. Sau khi release, Awaitility phải thấy task READY. Không dùng sleep cố định để tạo thứ tự.

### Bài D — Negative assertion

Một developer viết `await().until(() -> !hasTask(id))` để kiểm tra transaction rollback không tạo task. Hãy giải thích false positive, rồi thiết kế bằng chứng gồm rollback dữ liệu producer, pha AFTER_COMMIT, kiểm soát dispatch và observation window có cơ sở.

### Bài E — Trạng thái terminal

Mở rộng `PreparationState` thành `ACCEPTED, PROCESSING, RETRY_WAIT, READY, FAILED`. Thiết kế polling dừng thành công tại READY, fail sớm tại FAILED và timeout khi trạng thái vẫn chưa terminal. Phân biệt timeout test với lỗi nghiệp vụ.

### Bài F — Độ bền và retry

Nếu dự án dùng Event Publication Registry persistent, giả lập consumer failure, khởi động lại hoặc resubmit theo cơ chế được cấu hình. Chờ side effect cuối cùng, rồi xác minh publication completion và idempotency. Giải thích vì sao test trong cùng JVM không đủ chứng minh sống qua restart.

### Bài G — Database production-like

Chạy cùng consumer integration trên PostgreSQL Testcontainers và migration thật nếu production dùng Flyway/Liquibase. Kiểm tra stale read, isolation và unique constraint dưới concurrent duplicate delivery.

### Bài H — Kiểm chứng kiến trúc

Thử import `orders.internal.persistence.OrderEntity` từ module `fulfillment`. Chạy `ApplicationModules.verify()` và xác nhận test đỏ; sửa thành chỉ import public event `OrderPlaced`.

### Câu hỏi tự đánh giá

1. Vì sao `Thread.sleep(2_000)` có thể vừa chậm vừa flaky?
2. Awaitility khác sleep ở điều kiện dừng nào?
3. `PublishedEvents` chứng minh điều gì và không chứng minh điều gì?
4. Tại sao `@ApplicationModuleListener` hậu commit không chạy khi test transaction rollback?
5. Vì sao `await().until(() -> !hasTask(id))` thường không đủ làm negative test?
6. `during(Duration)` có chứng minh một hành vi không bao giờ xảy ra không?
7. Khi nào dùng `CountDownLatch` thay vì chỉ polling?
8. Vì sao timeout không đồng nghĩa business `FAILED`?
9. Vì sao một task tồn tại không chứng minh exactly-once business effect?
10. Vì sao integration test xanh vẫn cần architecture verification?

## 25. Checklist kiểm thử chờ điều kiện

- [ ] Mệnh đề cần chứng minh và công đoạn nghiệp vụ đã được định nghĩa rõ.
- [ ] Điều kiện chờ đọc output/state thật, không chỉ kiểm tra mock invocation.
- [ ] Assertion dùng đúng `orderId`/correlation ID của test.
- [ ] Timeout hữu hạn và phù hợp loại test; không xem là SLA tự động.
- [ ] Poll interval đủ nhẹ cho DB/HTTP, không quá thưa.
- [ ] Có thể pass ngay khi điều kiện đạt, không sleep đủ thời gian cố định.
- [ ] Nếu có state `FAILED`, test biết dừng sớm và báo nguyên nhân.
- [ ] Nếu có lỗi HTTP/DB, không ignore mọi exception một cách mù quáng.
- [ ] Test consumer có listener thật, transaction producer commit và query đọc mới.
- [ ] Test không mở transaction rollback bao ngoài rồi vô tình ngăn `AFTER_COMMIT`.
- [ ] Negative test không dùng `until(!condition)` để chứng minh “không bao giờ”.
- [ ] Khi cần, dùng latch/gateway để điều khiển trình tự một cách quyết định.
- [ ] Database fixture và container lifecycle được cô lập.
- [ ] Duplicate/retry/restart có test riêng nếu contract yêu cầu.
- [ ] `ApplicationModules.verify()` có trong quality gate CI cùng event integration tests.

## 26. Ghi nhớ

**Chờ theo điều kiện** giúp kiểm thử bất đồng bộ nhanh khi công việc hoàn tất sớm, có giới hạn khi công việc thất bại và rõ ràng về **bằng chứng thực sự được quan sát**. `Thread.sleep(...)` chỉ đoán một khoảng trễ, không xác nhận workflow hoàn thành. Với Spring Modulith, hãy dùng `@ApplicationModuleTest` + `PublishedEvents` để kiểm tra producer, dùng Awaitility và integration test sau commit để quan sát side effect của consumer, và thêm test reliability khi cần retry, duplicate hoặc durability.

Đừng quên **negative assertions**, transaction boundary, correlation ID và trạng thái terminal. Kết hợp những phép kiểm chứng này với `ApplicationModules.verify()` và quality gate CI để vừa giữ ranh giới application module, vừa ngăn hồi quy khi giao tiếp bất đồng bộ.
