# Chọn timeout theo môi trường kiểm thử

> **Chương:** Async verification  
> **Chương trình:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Phạm vi:** Chọn timeout cho kiểm chứng bất đồng bộ giữa các application module Spring Modulith; thực hành `@ApplicationModuleTest`, kiểm tra sự kiện sau commit, database, tích hợp, kiến trúc và quality gate CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **timeout chờ điều kiện**, **timeout HTTP**, **timeout transaction/database**, **timeout JUnit**, **timeout Testcontainers** và **timeout CI job**.
2. Xác định mốc bắt đầu và mốc kết thúc khi đo: từ lúc gửi yêu cầu, từ khi transaction producer commit hay từ khi bắt đầu Awaitility.
3. Chọn timeout có căn cứ theo **rủi ro**, **môi trường**, **độ trễ đã đo** và **retry policy**, thay vì sao chép một con số cho mọi test.
4. Dùng `await().atMost(...).pollInterval(...).untilAsserted(...)` để chờ side effect của listener sau commit.
5. Tách thời gian **khởi động Spring context/container** khỏi thời gian **xử lý sự kiện**.
6. Phân biệt **timeout quan sát** với **FAILED terminal** và xử lý đúng trường hợp kiểm tra không xảy ra hành vi.
7. Thiết kế quality gate CI giữ đúng bằng chứng về module, event, JPA, HTTP và tính tin cậy mà không kéo dài thời gian chạy vô cớ.

**Nguyên tắc:** Timeout không có một “giá trị tốt nhất” cho mọi hệ thống. Timeout quá ngắn sinh flaky test; timeout quá dài trì hoãn phát hiện lỗi và có thể che hồi quy hiệu năng. Con số chỉ hữu ích khi gắn với **hợp đồng đang kiểm chứng và thời gian thực sự được đo**.

## 2. Timeout là ngân sách quan sát, không phải bảo đảm của nghiệp vụ

Ví dụ ứng dụng `orders` tạo order, publish `OrderPlaced`; module `fulfillment` tạo task sau commit.

~~~java
UUID orderId = orders.place("CUS-101");

await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
                assertThat(fulfillment.hasTask(orderId)).isTrue());
~~~

Bài test này chỉ chứng minh:

> “Sau khi `orders.place(...)` trả về, task của đúng order được quan sát trong tối đa 10 giây **ở môi trường test cụ thể**.”

Nó **chưa chứng minh** production đáp ứng SLO “99,9% tác vụ hoàn thành dưới 10 giây”, cũng chưa kiểm tra event vẫn tồn tại qua restart, đúng một lần delivery hoặc hãng vận chuyển bên ngoài đã hoàn tất công việc.

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Completion criterion** | Cần điều gì đúng để gọi là xong? | Task đã commit, query trả READY |
| **Test deadline** | Chờ điều kiện đó tối đa bao lâu? | Awaitility atMost 10 giây |
| **Business SLA/SLO** | Tốc độ phải đạt thế nào dưới tải/cấu hình đã định nghĩa? | p99 dưới một ngưỡng sản phẩm |
| **Timeout failure** | Test không thấy điều kiện đúng trước deadline | Assertion timeout |
| **Business terminal failure** | Server quyết định workflow không tiếp tục được | State FAILED |

**Timeout không đồng nghĩa FAILED.** Workflow có thể hoàn thành ngay sau khi test hết deadline. Ngược lại, nếu server đã trả FAILED terminal, test nên dừng sớm, không phải chờ hết 10 giây để phát hiện điều đã biết.

## 3. Đo chính xác phần thời gian nào?

Một integration test bao gồm nhiều giai đoạn:

~~~mermaid
flowchart LR
    A["Gradle / JUnit"] --> B["Spring TestContext"]
    B --> C["DB / container / migration"]
    C --> D["Gọi producer T1"]
    D --> E["Publish + commit"]
    E --> F["Executor / listener T2"]
    F --> G["Consumer commit"]
    G --> H["Query / assertion"]
~~~

Các khoảng thời gian có ý nghĩa khác nhau.

| Bắt đầu đo từ | Kết thúc khi | Số liệu đang đo |
| --- | --- | --- |
| Chạy `./gradlew test` | Build kết thúc | Tổng wall-clock Gradle/JVM/test |
| Khởi tạo test context | Context sẵn sàng | Spring bootstrap và hạ tầng liên quan |
| Bắt đầu `orders.place(...)` | Consumer READY | Toàn luồng từ lệnh Java tới kết quả |
| Sau `orders.place(...)` trả về | Consumer READY | Thời gian chờ downstream sau producer |
| Sau event được registry ghi nhận | Publication completed | Latency cơ chế phân phối theo registry |
| Listener vừa bắt đầu | Side effect commit | Thời gian xử lý consumer |
| Trước POST HTTP | Endpoint status READY | Toàn hành trình HTTP do client trải nghiệm |

**Lỗi dễ gặp:** Đặt `await().atMost(10s)` **sau** `orders.place(...)` không giới hạn thời gian thực hiện producer. Producer mất 8 giây và polling mất thêm 9 giây vẫn có thể làm test xanh mặc dù toàn luồng mất 17 giây.

Do đó phải ghi rõ **mốc bắt đầu** trong tên test, tài liệu hoặc báo cáo đo trước khi tranh luận “timeout 10 giây có đủ không”.

## 4. Bản đồ các loại timeout

| Tầng | Phạm vi | Công cụ minh họa | Khi chỉnh sai |
| --- | --- | --- | --- |
| Awaitility | Tổng thời gian chờ oracle đạt | `atMost(Duration)` | Flaky hoặc báo lỗi quá muộn |
| Poll interval | Khoảng giữa hai lần query | `pollInterval(Duration)` | Poll quá dày hoặc phản hồi chậm |
| HTTP connect | Thời gian mở kết nối một request | HTTP client config | Request thất bại vì network chậm |
| HTTP read | Thời gian chờ response từng request | HTTP client config | Một lần poll treo hoặc timeout |
| Database query | Thời gian chờ/làm SQL | JDBC, JPA, driver | Không đọc được state dù consumer đã ghi |
| Transaction | Giới hạn xử lý một transaction | Spring transaction manager | Consumer rollback trước khi commit |
| Container readiness | Thời gian DB/broker khởi động | Testcontainers wait strategy | Test context không start |
| JUnit method | Giới hạn chạy phần body test | `@Timeout` | Có thể ngắt trước Awaitility |
| CI job | Giới hạn toàn job/suite | CI platform | Mất toàn bộ báo cáo nếu job bị hủy |

**Tăng Awaitility timeout không làm container khởi động nhanh hơn**, không sửa lỗi DB schema và không giải quyết việc HTTP request bị block vô hạn. Luôn tìm đúng tầng đang gây ra timeout.

### Các tầng ngân sách thường nên có trật tự

~~~text
Timeout của một HTTP GET hoặc DB query
        < Deadline chung của Awaitility
        < Outer timeout của JUnit method
        < CI job limit đủ cho toàn suite và setup
~~~

Đây là **nguyên tắc thiết kế**, không phải bất đẳng thức bắt buộc cho mọi tình huống. Nếu mỗi query đơn lẻ cần 8 giây còn Awaitility chỉ có 10 giây, còn rất ít ngân sách để thử lại; cần xem lại mục tiêu kiểm chứng và cấu hình query.

## 5. Chọn thời hạn theo môi trường: bảng tham khảo có điều kiện

Những khoảng sau là **điểm bắt đầu minh họa để chạy đo**, không phải mặc định của Spring Modulith hay một cam kết về hiệu năng.

| Test type / môi trường | Hạ tầng cần thật | Deadline khởi điểm để thử | Poll interval để thử | Chú ý |
| --- | --- | --- | --- | --- |
| Unit Java đồng bộ | Không Spring | Không cần Awaitility | Không áp dụng | Assert return/exception ngay |
| Unit task async có controlled executor | Thread/future nội bộ | 1–5 giây | 20–100 ms | Prefer latch/future khi có mốc chính xác |
| Producer `@ApplicationModuleTest` + `PublishedEvents` | Module producer | Thường không cần chờ consumer | Không áp dụng | Event publish khác consumer completion |
| Cross-module integration H2 | Spring, T1/T2, H2 | 5–10 giây | 50–200 ms | Theo correlation ID |
| Cross-module PostgreSQL Testcontainers | DB production-like | 5–15 giây **sau startup** | 100–250 ms | Readiness có budget riêng |
| HTTP E2E local server | `RANDOM_PORT`, HTTP | 10–20 giây | 100–500 ms | Từng HTTP call có timeout riêng |
| Registry retry/resubmit | Persistent storage, policy | Theo lịch backoff đã cấu hình | Theo cadence retry | Không đoán retry mặc định |
| Sandbox bên ngoài | Network/provider | Theo hợp đồng provider | Có backoff/rate limit | Phân loại lỗi tạm thời và terminal |

Không áp dụng máy móc **“CI phải chờ gấp đôi local”**. Một CI runner nhiều CPU có thể nhanh hơn máy laptop; một local máy yếu có thể chậm hơn CI. Timeout phải bám vào số liệu *của môi trường và workflow cụ thể*.

### Điều gì làm môi trường khác nhau?

- CPU/RAM, số JVM forks, test parallelism, thread pool của listener.
- Spring TestContext cache hit/miss, số application modules/bean và auto-configuration.
- JPA metadata, Flyway/Liquibase migration và connection pool.
- Container image đã có sẵn hay phải pull, Docker network, disk I/O.
- Database isolation, locking, native SQL và replica lag.
- Broker, registry, retry backoff, sự cố mạng và rate limit provider.

Nếu một test timeout trên CI, việc đầu tiên là **xác định nguyên nhân**, không phải tăng thời gian chờ.

## 6. Local, CI, Testcontainers và staging khác nhau thế nào?

### Local developer

Local có thể có JVM và database warm sau vài lần chạy, nhưng chịu ảnh hưởng IDE, Docker và các ứng dụng cùng máy. Hãy tách **cold run** khỏi **warm run**; không so một cold start với một warm cache hit rồi gán chênh lệch cho Awaitility.

### CI pull request

CI chịu ảnh hưởng bởi runner scheduling, memory limit, số job chạy đồng thời, Docker service và filesystem. Khi có flaky test, hãy xem executor queue và logs của consumer trước khi kết luận timeout chưa đủ.

### Testcontainers

Pull image, start PostgreSQL/Kafka, chờ readiness và chạy migration có thể tốn nhiều thời gian hơn chính consumer event. Đây thường là **setup cost**, phải quản lý bằng startup/container/job budget, không nhét toàn bộ vào `await().atMost(...)` đo business task.

### Staging/provider sandbox

Khi bài test gọi dịch vụ ngoài, còn có DNS/TLS, rate limit, maintenance và API trả `202 Accepted` cho công việc chưa hoàn tất. Retry/backoff phải theo hợp đồng, không poll quá nhanh hoặc ignore mọi HTTP error.

### Môi trường performance/load

Ở đây ngưỡng có thể là một **SLO được sản phẩm phê duyệt**. Một functional test cho phép tối đa 15 giây không thể chứng minh p99 production dưới 1 giây. Đó là hai phép kiểm chứng khác nhau.

## 7. Chọn timeout dựa trên phân phối thời gian thực

Quy trình thực hành:

1. **Xác định claim.** Ví dụ “sau khi T1 commit, task có thể đọc được”.
2. **Xác định clock start.** Sau `orders.place(...)` trả về hay trước khi gọi service?
3. **Đo lặp lại** trong môi trường đại diện, đủ số mẫu để thấy tail latency.
4. **Tách startup và phương thức test.** Đừng lấy thời gian Gradle task làm latency của event.
5. **Ghi p50, p95, p99 khi cỡ mẫu đủ**, cùng max, failures, timeout rate và điều kiện CI.
6. **Điều tra outlier.** Nó đến từ executor queue, DB pool, GC, retry, network hay bug?
7. **Chọn headroom có lý do**, nhưng không vượt chuẩn SLO nếu test chính là performance gate.
8. **Theo dõi sau thay đổi** để phát hiện hồi quy bị deadline rộng che giấu.

### Ví dụ số liệu giả định

Giả sử đo 300 lượt chạy trên CI có cấu hình tương đối ổn định:

| Chỉ số | Giá trị minh họa |
| --- | --- |
| Số mẫu | 300 |
| p50 | 180 ms |
| p95 | 550 ms |
| p99 | 1.250 ms |
| Lượt chậm nhất quan sát | 1.700 ms |
| Timeout hiện dùng | 2 giây |

Có thể cân nhắc 3–5 giây cho **functional test** nếu muốn thêm headroom theo dữ liệu này. Nhưng nếu business yêu cầu 99% dưới 1 giây, việc nới test thành 5 giây **không làm hệ thống đáp ứng yêu cầu ấy**.

**Không lấy p99 từ năm mẫu.** Các percentile ở đuôi phân phối rất nhạy với cỡ mẫu; phải báo số mẫu, bối cảnh và biến thiên của kết quả. Công thức “p99 cộng 20%” có thể là heuristic, không phải một tiêu chuẩn mặc định.

## 8. Sự kiện Spring Modulith: nguồn latency chính

Với `@ApplicationModuleListener`, một listener thường được kích hoạt **sau commit**, xử lý **bất đồng bộ** và dùng transaction riêng theo cấu hình Spring Modulith tương thích.

~~~mermaid
sequenceDiagram
    participant T as Test
    participant O as orders
    participant D1 as Orders DB
    participant E as Events
    participant L as fulfillment listener
    participant D2 as Fulfillment DB

    T->>O: place(customerId)
    O->>D1: INSERT trong T1
    O->>E: publish OrderPlaced
    O->>D1: COMMIT T1
    O-->>T: orderId
    Note over T,L: Awaitility bắt đầu khi gọi ở đây
    E-->>L: Dispatch AFTER_COMMIT
    L->>D2: INSERT task trong T2
    L->>D2: COMMIT T2
    T->>D2: Query task theo orderId
    D2-->>T: READY
~~~

Thời gian chờ từ producer trả về đến task visible bao gồm:

- Thời gian dispatch vào thread pool.
- Hàng đợi executor nếu worker đang bận.
- Transaction T2 và truy cập database.
- Query/visibility sau commit.
- Retry/backoff nếu test cố ý kích hoạt lỗi.

**Không dùng `PublishedEvents` để đo consumer completion.** Collection này quan sát publisher, không khẳng định consumer đã commit.

### Một mốc khác, một ý nghĩa khác

~~~text
A: trước orders.place()
B: orders.place() trả về sau T1
C: task READY có thể đọc

A ---- producer/commit ---- B ---- consumer/wait ---- C
          A -> C: total workflow elapsed
                                B -> C: post-producer wait
~~~

Nếu mục tiêu của test là tổng thời gian từ khi client bắt đầu yêu cầu, đừng tính riêng `B → C`.

## 9. Ví dụ code: hai application module

Cấu trúc minh họa:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderCommands.java              # Public API
│   ├── OrderPlaced.java                # Public event
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/
    ├── FulfillmentQueries.java         # Public API
    ├── PreparationState.java
    └── internal/
        ├── OrderPlacedListener.java
        ├── FulfillmentQueryService.java
        └── persistence/
            ├── FulfillmentTask.java
            └── FulfillmentTaskRepository.java
~~~

Theo mô hình mặc định của Spring Modulith, `orders` và `fulfillment` là application modules. `OrderPlaced` trong package root của `orders` là API mặc định, còn các class dưới `internal` không nên được module khác import.

**Completion criterion của ví dụ:** Công đoạn chuẩn bị task hoàn thành khi `fulfillment` đã commit task và `FulfillmentQueries.statusFor(orderId)` trả `READY`. Đây không phải khẳng định bưu kiện đã giao cho khách.

## 10. Producer: tạo đơn và publish event trong transaction

### 10.1. Application entry point

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

`@EnableAsync` cho phép Spring sử dụng async executor theo cấu hình. Trong production phải xem queue capacity, rejected execution và exception handling; annotation này không tự cung cấp durable queue hay retry guarantee.

### 10.2. API và event

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

Dùng record bất biến, mang ID cần thiết; không đưa JPA entity hoặc repository nội bộ vào event công khai.

### 10.3. JPA entity và repository

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

Code minh họa dùng Java 17+ và JPA hỗ trợ `GenerationType.UUID`. Với engine/phiên bản khác, thay ID strategy phù hợp.

### 10.4. Application service phát sự kiện

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

        var entity = orders.save(new OrderEntity(customerId));
        UUID id = entity.getId();

        publisher.publishEvent(new OrderPlaced(id));
        return id;
    }
}
~~~

`publishEvent` diễn ra **trong T1**. Khi gọi service qua Spring transaction proxy và không có outer transaction, `place(...)` hoàn tất sau xử lý commit của T1. Listener consumer vẫn có thể chưa bắt đầu.

## 11. Consumer: oracle thuộc module sở hữu dữ liệu

### 11.1. Query API công khai

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

`NOT_OBSERVED` cố ý chỉ mang nghĩa “chưa thấy task”; nó không đủ để phân biệt pending, failed, event mất hoặc order ID không tồn tại.

### 11.2. Entity và repository của fulfillment

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

### 11.3. Listener sau commit

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

Handler trên chỉ nhằm minh họa happy path. Hai sự kiện trùng xử lý đồng thời có thể cùng vượt qua `existsById` rồi gây unique constraint violation. Đây là rủi ro idempotency cần test riêng; tăng timeout không sửa được.

### 11.4. Query service quan sát sau commit

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

Test đọc qua `FulfillmentQueries`, không import repository `fulfillment.internal` của module khác. Mỗi lần poll qua Spring bean có transaction đọc phù hợp sẽ có cơ hội thấy task đã commit.

## 12. Producer test không cần chờ consumer

Mệnh đề **“producer phát event đúng”** nên được kiểm tra độc lập, nhanh và đúng phạm vi:

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
    void publishes_order_id(PublishedEvents events) {
        var id = orders.place("CUS-PUB");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }

    @Test
    void rejects_invalid_input_without_event(
            PublishedEvents events) {

        assertThatThrownBy(() -> orders.place(" "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderPlaced.class)).isEmpty();
    }
}
~~~

`PublishedEvents` quan sát sự kiện đã **publish**, không chứng minh consumer đã chạy. `anySatisfy` chỉ chứng minh **ít nhất một event phù hợp**, không phải chính xác một. Vì vậy **không thêm Awaitility chờ task** vào test chỉ cần producer contract.

Khi cần bảo vệ cardinality, bổ sung assertion số lượng event bằng API phù hợp phiên bản Spring Modulith đang dùng.

## 13. Integration test với deadline được cấu hình theo kịch bản

Bài test consumer cần cả hai module, database và transaction thật. Để điều chỉnh budget test mà không phải thay production service, ví dụ đọc JVM system property:

~~~java
private static Duration awaitBudget() {
    long milliseconds =
            Long.getLong("verification.await.ms", 10_000L);

    if (milliseconds <= 0) {
        throw new IllegalArgumentException(
                "verification.await.ms must be positive");
    }

    return Duration.ofMillis(milliseconds);
}
~~~

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
        "spring.datasource.url=jdbc:h2:mem:fulfillment-async;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderFulfillmentIntegrationTest {

    @Autowired
    OrderCommands orders;

    @Autowired
    FulfillmentQueries fulfillment;

    private static Duration awaitBudget() {
        long millis = Long.getLong("verification.await.ms", 10_000L);
        return Duration.ofMillis(millis);
    }

    @Test
    void task_appears_after_consumer_commit() {
        UUID orderId = orders.place(
                "CUS-" + UUID.randomUUID());

        await()
                .atMost(awaitBudget())
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() ->
                        assertThat(fulfillment.statusFor(orderId))
                                .isEqualTo(PreparationState.READY));
    }
}
~~~

Cách `Long.getLong` trên đọc **JVM system property**, không đọc environment variable. Nếu dùng giá trị từ CI, truyền property vào JVM test qua build tool. Nên validate budget dương như helper đầu mục này trong code thực tế.

### Điều đã chứng minh

- Producer được gọi qua Spring bean và transaction được xử lý thật.
- Listener consumer được bootstrap và có cơ hội chạy sau T1 commit.
- Task cho đúng `orderId` có thể đọc sau T2 commit.
- Timeout chỉ giới hạn **phần polling sau `place(...)`**.

### Điều chưa chứng minh

- Tổng thời gian từ lúc `place(...)` bắt đầu đến READY dưới budget.
- Độ bền event qua restart hoặc broker ngoài.
- Exactly-once delivery.
- SLO production dưới tải.

### Vì sao không đặt @Transactional trên test?

Nếu test được bọc trong outer transaction do Spring Test quản lý, `place(...)` có thể tham gia transaction đó, và cuối test framework rollback. Listener `AFTER_COMMIT` có thể không chạy. Để test consumer hậu commit, **service producer phải commit thật**, đồng thời fixture/cleanup phải được thiết kế riêng.

## 14. Chọn cách cấu hình theo môi trường mà không làm phân mảnh context

### 14.1. JVM property chỉ dùng cho phép chờ

Gradle Kotlin DSL minh họa:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    val awaitMs = providers.gradleProperty("asyncAwaitMs")
            .orElse("10000")

    systemProperty("verification.await.ms", awaitMs.get())
}
~~~

Có thể gọi:

~~~bash
./gradlew test -PasyncAwaitMs=12000
~~~

Chỉ dùng con số khác khi có căn cứ về thời gian CI; không tự đặt “CI = 2 × local”.

**Ưu điểm:** Thay budget của bài test mà không nhất thiết đổi cấu hình bean Spring.  
**Lưu ý:** `System.setProperty` trong từng test method không an toàn khi nhiều test chạy đồng thời. Thiết lập tại launcher/build, ghi giá trị vào report, tránh các test tự sửa global property.

### 14.2. Spring test properties/profiles

Có thể đặt riêng:

~~~yaml
# application-test.yml, ví dụ cấu hình
verification:
  await:
    timeout: PT10S
    interval: PT0.1S
~~~

~~~yaml
# application-ci.yml, giá trị chỉ mang tính minh họa
verification:
  await:
    timeout: PT15S
    interval: PT0.2S
~~~

Nếu test dùng Spring-bound Duration, cần binder/conversion phù hợp; tách rõ property dùng cho **test** với cấu hình timeout của **production business logic**.

**Cẩn trọng:** `@ActiveProfiles` và `@TestPropertySource` khác nhau có thể tạo **Spring TestContext cache key** khác nhau, dẫn tới nhiều context cold startup. Không tạo một profile riêng cho mỗi test chỉ để đổi 100 ms của polling.

| Cách cấu hình | Khi phù hợp | Rủi ro cần chú ý |
| --- | --- | --- |
| Constant trong test | Suite nhỏ, môi trường ổn định | Khó tùy biến |
| JVM system property | Test-only await budget | Global mutable state nếu sửa trong test |
| Spring test profile | Budget gắn với một suite context | Context fragmentation nếu cấu hình khác |
| Explicit per-test | Reliability scenario có retry/backoff khác | Nhiều magic numbers |
| CI runner configuration | Phân biệt nhóm job/hạ tầng | Không được che hồi quy bằng ngưỡng quá rộng |

## 15. Đo toàn workflow: trừ thời gian producer đã dùng

Để khẳng định **“từ lúc gọi place đến READY trong tối đa 12 giây”**, bắt đầu clock **trước** khi gọi producer.

~~~java
@Test
void finishes_within_total_workflow_budget() {
    Duration totalBudget = Duration.ofSeconds(12);

    long startedNanos = System.nanoTime();
    UUID orderId = orders.place(
            "CUS-TOTAL-" + UUID.randomUUID());

    Duration alreadySpent = Duration.ofNanos(
            System.nanoTime() - startedNanos);

    Duration remaining = totalBudget.minus(alreadySpent);

    assertThat(remaining)
            .as("Producer exhausted total workflow budget")
            .isGreaterThan(Duration.ZERO);

    await()
            .atMost(remaining)
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() ->
                    assertThat(fulfillment.statusFor(orderId))
                            .isEqualTo(PreparationState.READY));
}
~~~

`System.nanoTime()` thích hợp để đo elapsed time (không phụ thuộc người dùng chỉnh đồng hồ hệ điều hành). Nếu producer đã dùng hết budget, test fail trước khi poll; **không cấp lại toàn bộ 12 giây** cho consumer.

Bài này vẫn là functional integration test, không tự tạo benchmark production p99. Nếu muốn đo latency HTTP, bắt đầu clock trước HTTP POST.

## 16. Retry/backoff: deadline phải chứa một đường phục hồi hợp lệ

Giả sử test cố ý gây lỗi tạm thời:

~~~text
T0:       attempt 1 -> thất bại
T0 + 1s:  attempt 2 -> thất bại
T0 + 4s:  attempt 3 -> thành công và commit
~~~

Đặt `atMost(2s)` sẽ fail **trước** một lần retry hợp lệ theo policy. Test phải biết lịch retry nếu mục tiêu là chứng minh recovery.

### Lập ngân sách theo cơ chế thực tế

~~~text
Retry observation budget
  ≈ tổng backoff có thể xảy ra trong kịch bản
    + thời gian của các attempt
    + database/network/visibility margin
~~~

Đây chỉ là mô hình phân rã; số liệu thật tùy jitter, parallelism, retry cap và hạ tầng.

| Claim | Cách chọn timeout |
| --- | --- |
| Happy path không lỗi | Độ trễ bình thường đã đo + margin |
| Retry một lần rồi thành công | Đủ thời gian cho lần lỗi + backoff + lần thành công |
| Retry tối đa rồi terminal FAILED | Đủ cho chính sách kết thúc, nhưng fail sớm khi có FAILED |
| Publication sống qua restart | Tách startup/recovery và time-to-READY |
| SLO latency dưới tải | Theo ngưỡng sản phẩm, không nới để che regression |

Spring Modulith có Event Publication Registry và các adapter; **không giả định** mọi `@ApplicationModuleListener` tự retry vô hạn. Test phải dựa vào dependency, adapter, version và resubmission policy đang cấu hình.

## 17. Terminal failure phải dừng sớm, timeout là UNKNOWN

Một workflow hoàn chỉnh thường có các trạng thái rõ ràng:

~~~java
public enum WorkflowState {
    ACCEPTED,
    PROCESSING,
    RETRY_WAIT,
    READY,
    FAILED
}
~~~

Đây là **mô hình mở rộng minh họa**, không có sẵn trong code `PreparationState` phía trên. Nếu server đã ghi `FAILED` terminal, test nên dừng và ghi nguyên nhân thay vì đợi hết deadline.

~~~text
state = query(workflowId)

READY                 -> success
FAILED                -> fail ngay, hiển thị reason
ACCEPTED/PROCESSING/
RETRY_WAIT            -> poll tiếp trong deadline
Chưa terminal hết hạn -> timeout/unknown
~~~

Với Awaitility có thể dùng fail-fast/exception handling được hỗ trợ ở phiên bản hiện tại. **Không ignore mọi exception từ HTTP/database**, vì HTTP 401, schema mismatch hoặc lỗi chuyển đổi JSON thường không phải trạng thái chờ bình thường.

| Tín hiệu | Diễn giải |
| --- | --- |
| READY | Completion criterion đạt |
| FAILED | Business failure terminal |
| PROCESSING | Có thể poll tiếp |
| HTTP 429/503 theo policy | Có thể backoff và retry |
| HTTP 401/403 | Lỗi truy cập, dừng chẩn đoán |
| HTTP 404 với ID không tồn tại | Không được poll vô hạn |
| Awaitility timeout | Chưa quan sát được terminal state đúng hạn |

## 18. Negative assertion không thể dùng cùng quy tắc chờ thành công

Nếu mong đợi **không có task** sau producer rollback, test sau là yếu:

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> fulfillment.statusFor(orderId)
                == PreparationState.NOT_OBSERVED);
~~~

Điều kiện có thể đúng ngay ở lần poll đầu tiên khi listener chưa chạy, rồi test pass dù tác vụ bất đồng bộ sai xuất hiện sau đó.

### Chiến lược kiểm tra âm tốt hơn

1. Xác nhận T1 rollback bằng trạng thái database producer.
2. Xác nhận listener dùng pha `AFTER_COMMIT`, không có fallback ngoài transaction.
3. Nếu cần, điều khiển executor/transaction synchronization để biết các tác vụ liên quan đã qua mốc quyết định.
4. Nếu contract là “không xuất hiện trong X thời gian”, quan sát điều kiện **duy trì trong cửa sổ hữu hạn** và diễn đạt giới hạn.
5. Không kết luận “không bao giờ” chỉ vì đã chờ một khoảng tùy ý.

Awaitility hiện đại có `during(Duration)` cho yêu cầu một điều kiện phải giữ đúng liên tục trong một cửa sổ:

~~~java
await()
        .during(Duration.ofMillis(500))
        .atMost(Duration.ofSeconds(2))
        .until(() -> fulfillment.statusFor(orderId)
                == PreparationState.NOT_OBSERVED);
~~~

Bài test này **chỉ chứng minh sự vắng mặt trong cửa sổ quan sát**, không chứng minh mọi listener đã hoàn tất hay event sẽ không bao giờ được xử lý.

### Dùng CountDownLatch khi cần điều khiển mốc

Với race/ordering, một test fixture có thể dùng `CountDownLatch` ghi nhận listener đã vào gateway rồi chặn trước khi ghi database. Test xác nhận listener đã bắt đầu nhưng state chưa READY; sau khi release, Awaitility mới chờ READY. Luôn release trong `finally` để không treo executor.

Đây là cách có bằng chứng mạnh hơn việc đoán `Thread.sleep(300)` khiến listener “chắc đã vào”.

## 19. PostgreSQL Testcontainers: timeout setup khác timeout xử lý

Khi cần xác minh PostgreSQL transaction/constraint thay vì H2, có thể dùng:

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
    // dùng cùng oracle READY, với budget đo sau startup.
}
~~~

Đây là khung cấu hình, chưa có test method. Cần Spring Boot Testcontainers, Testcontainers Jupiter/PostgreSQL, JDBC driver và container runtime. `@ServiceConnection` có từ Spring Boot 3.1+, dùng phiên bản tương thích.

### Những chi phí cần đo riêng

- Pull image, start container, readiness.
- Spring context và datasource bootstrap.
- Migration Flyway/Liquibase nếu production có.
- Producer T1, listener T2 và read visibility.
- Cleanup, container shutdown.

**Không tăng `atMost` để che container không start hoặc schema migration lỗi**. Những lỗi này thuộc setup và phải báo riêng.

### Context cache khác container lifecycle

Spring TestContext cache tái sử dụng application context theo cấu hình trong cùng JVM test. Testcontainers quản lý vòng đời container theo annotation/pattern. Chúng **không tự bảo đảm cùng vòng đời**.

Nếu context được cache nhưng container của test class trước đã dừng, datasource có thể trỏ đến container chết. Tăng timeout không sửa được; phải thiết kế container reuse/lifecycle nhất quán.

## 20. Polling database phải nhìn được dữ liệu đã commit

Một test có thể timeout dù task đã có nếu phép đọc luôn dùng snapshot cũ.

**Không nên** bọc toàn bộ integration test after-commit trong transaction rollback mặc định:

~~~java
@Transactional
@Test
void wrong_test_transaction_boundary() {
    UUID id = orders.place("CUS-TX");
    // Producer có thể tham gia transaction test;
    // listener AFTER_COMMIT không được kích hoạt vì rollback.
}
~~~

Một số vấn đề khác:

- Isolation level giữ snapshot cũ giữa các lần poll.
- JPA persistence context cache entity không được refresh.
- Query đi tới read replica bị lag.
- Connection pool thiếu slot khi test chạy song song.
- Query đọc sai UUID hoặc DB instance.

**Polling chỉ lặp lại phép quan sát.** Nếu phép quan sát luôn nhìn cùng một snapshot cũ, tăng deadline 5 lên 50 giây không làm nó đúng. Hãy dùng transaction đọc ngắn, public query API, dữ liệu test riêng và kiểm tra isolation.

## 21. HTTP polling: giới hạn mỗi request và toàn workflow

Với HTTP E2E, có ít nhất hai timeout:

- Deadline toàn bộ từ request tạo order tới trạng thái `READY`.
- Timeout kết nối/đọc của mỗi HTTP GET status.

Nếu mỗi GET có thể treo 30 giây mà Awaitility budget chỉ 10 giây, việc expect Awaitility luôn ngắt network call đúng giây thứ 10 là không an toàn. Cần cấu hình **HTTP client timeout riêng**, cũng như chính sách phân loại status.

### Ví dụ skeleton E2E

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
    void client_observes_ready() {
        var accepted = http.postForEntity(
                "/api/orders",
                Map.of("customerId", "CUS-" + UUID.randomUUID()),
                JsonNode.class);

        assertThat(accepted.getStatusCode())
                .isEqualTo(HttpStatus.ACCEPTED);
        assertThat(accepted.getBody()).isNotNull();

        String id = accepted.getBody().path("orderId").asText();

        await()
                .atMost(Duration.ofSeconds(15))
                .pollInterval(Duration.ofMillis(200))
                .untilAsserted(() -> {
                    var state = http.getForEntity(
                            "/api/fulfillments/{id}/preparation",
                            JsonNode.class, id);

                    assertThat(state.getStatusCode())
                            .isEqualTo(HttpStatus.OK);
                    assertThat(state.getBody()).isNotNull();
                    assertThat(state.getBody()
                            .path("state").asText())
                            .isEqualTo("READY");
                });
    }
}
~~~

Đoạn này giả định ứng dụng **đã có REST controllers** tương ứng, JSON contract và datasource test; source mẫu `orders`/`fulfillment` phía trên chưa tự tạo hai endpoint ấy. Cần cấu hình HTTP client connect/read timeout khi triển khai integration thật.

Đừng ignore HTTP 500 hoặc 401 như một trạng thái “vẫn đang chờ” nếu contract không cho phép. Nếu API có `Retry-After`, xét áp dụng theo policy thay vì poll dày liên tục.

## 22. JUnit method và CI job timeout: outer guard

Một test có thể có ngân sách:

~~~text
Container startup:      theo Testcontainers
Spring context:         setup context / startup
Producer + Awaitility:  tối đa 12 giây theo claim
JUnit method timeout:   ví dụ 25 giây
CI job limit:           đủ cho toàn suite và setup
~~~

Ví dụ JUnit 5:

~~~java
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Test
@Timeout(value = 25, unit = TimeUnit.SECONDS)
void verifies_completion() {
    // Thân test có Awaitility atMost thấp hơn 25 giây.
}
~~~

**Không đặt `@Timeout(5s)` cho một test dùng `await().atMost(12s)`** rồi mong Awaitility đủ thời gian báo lỗi. Outer guard có thể ngắt trước.

`@Timeout` bảo vệ phạm vi test method theo cấu hình JUnit, không thay thế quản lý context startup hoặc toàn CI job. Việc ngắt thread không bảo đảm mọi network/DB blocking call đều hủy tức khắc; vì vậy vẫn cần timeouts ở các tầng bên dưới.

## 23. Timeout trong CI: cần cả functional gate và latency signal

Nếu trước một thay đổi task thường READY sau 300–600 ms, sau thay đổi nó mất 6–8 giây, bài test `atMost(10s)` vẫn xanh. Nhưng đó có thể là một **hồi quy hiệu năng nghiêm trọng**.

Theo dõi đồng thời:

| Chỉ số | Phát hiện vấn đề |
| --- | --- |
| time-to-READY p50/p95/p99 | Consumer latency và tail |
| Timeout rate theo environment | Flakiness và lỗi thực |
| Executor queue depth | Listener bị xếp hàng |
| Connection-pool wait time | Database contention |
| Container readiness time | Hạ tầng startup |
| Retry attempts/pending publications | Độ tin cậy event |
| Spring TestContext cache hit/miss | Khởi tạo context trùng |
| Full CI wall-clock | Chi phí phản hồi pull request |

Có thể tách hai gate:

**Functional correctness gate:** Side effect cuối cùng đúng trong deadline đủ chặt để phát hiện lỗi.

**Latency regression/SLO gate:** Phân phối độ trễ trong môi trường và workload chuẩn hóa đạt ngưỡng đã phê duyệt.

Không biến functional test thành benchmark p99 chỉ bằng cách tăng sample count vài lần trong một JVM. Cần môi trường/tải phù hợp và cỡ mẫu đủ.

## 24. Troubleshooting timeout theo tầng

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `PublishedEvents` có event, Awaitility timeout | Listener không được đăng ký hoặc lỗi | Check context, listener và log |
| Test `@Transactional` luôn đợi hết deadline | T1 bị rollback, không có AFTER_COMMIT | Cho producer commit thật |
| Test fail trước khi chạy body | Container/context/migration | Đo startup, không chỉnh Awaitility |
| Task đã commit nhưng query không thấy | Snapshot cũ, sai UUID, read replica lag | Kiểm tra read transaction/DB |
| CI chậm hơn local | CPU/memory/executor contention | Đo latency distribution và queue |
| Test pass nhưng tốn cố định nhiều giây | Dùng `Thread.sleep` hoặc poll delay dài | Chờ điều kiện, có deadline |
| Deadline ngắn hơn backoff retry | Policy mâu thuẫn | Tính retry schedule thực |
| FAILED terminal mà vẫn timeout | Thiếu fail-fast | Đọc state và dừng sớm |
| HTTP GET treo hơn total budget | Thiếu per-request timeout | Cấu hình HTTP client |
| Negative test pass ngay | `until(!condition)` | Sửa chiến lược assertion âm |
| Unique key gây retry liên tục | Handler chưa idempotent | Concurrency/replay test |
| Nới timeout nhưng vẫn fail | Lỗi logic, DB schema, wrong event | Chẩn đoán không kéo dài chờ |
| E2E xanh nhưng module architecture đỏ | Import implementation nội bộ | Giữ `ApplicationModules.verify()` |

**Quy trình điều tra:** Xác định mốc timeout → xác nhận producer commit → event publish → listener bắt đầu → T2 commit → query đúng ID → retry/registry → tài nguyên môi trường. Chỉ sau đó mới quyết định có cần điều chỉnh deadline không.

## 25. Giữ kiến trúc Spring Modulith trong quality gate

Module `fulfillment` được phép dùng event công khai:

~~~java
import com.example.shop.orders.OrderPlaced;
~~~

Nhưng không được tự ý import repository/entity nội bộ của `orders`:

~~~java
import com.example.shop.orders.internal.persistence.OrderEntity;
~~~

Một architectural test độc lập:

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void module_boundaries_remain_valid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm tra ranh giới API module, vòng dependency và các giới hạn phụ thuộc được khai báo. Nó **không** chờ event; consumer integration test cũng **không** thay thế được architecture verification.

~~~mermaid
flowchart LR
    PR["Pull request"] --> UNIT["Unit + slice"]
    UNIT --> ARCH["ApplicationModules.verify()"]
    ARCH --> PUB["Publisher module tests"]
    PUB --> CONS["Consumer after-commit"]
    CONS --> REL["Retry / registry / DB"]
    REL --> E2E["Critical HTTP E2E"]
    E2E --> G{"Gate bắt buộc xanh?"}
    G -- "Có" --> M["Merge / release"]
    G -- "Không" --> F["Sửa lỗi"]
~~~

Không xóa Testcontainers khi claim cần PostgreSQL isolation; không thay consumer integration bằng mock event publisher chỉ vì nhanh hơn. **Chọn timeout tốt để bảo vệ bằng chứng, không để loại bỏ bằng chứng.**

### Mẫu review một quyết định timeout

~~~text
Test: OrderFulfillmentIntegrationTest
Claim: Task fulfillment READY sau producer commit
Start clock: Sau khi orders.place(...) trả về
Oracle: statusFor(orderId) == READY
Environment: CI runner, PostgreSQL Testcontainers
Measured samples: [...]
p50 / p95 / p99: [...]
Chosen timeout: [...] và lý do
Poll interval: [...]
Retry/backoff assumptions: [...]
Outer JUnit timeout: [...]
CI job limit: [...]
Negative control: Bỏ listener => test đỏ
Not proven: Durable restart, production SLO
~~~

Việc ghi rõ giả định giúp review phát hiện trường hợp một PR tăng timeout từ 5 lên 60 giây chỉ để làm test xanh, mà không có dữ liệu hoặc lý do kiến trúc.

## 26. Bài tập thực hành

### Bài A — Phân tích hai môi trường

Giả sử local có p50 = 150 ms, p95 = 430 ms, p99 = 950 ms; CI có p50 = 250 ms, p95 = 800 ms, p99 = 1.900 ms sau 500 lượt đo. Chọn timeout khởi điểm có margin cho mỗi môi trường và giải thích tại sao không lấy p99 làm deadline tuyệt đối, cũng không chọn 60 giây khi không có lý do.

### Bài B — Tách startup khỏi completion

Đo container startup, Spring context startup, producer T1 và time-to-READY riêng. Lập bảng so sánh H2 với PostgreSQL Testcontainers. Không gộp image pull vào deadline Awaitility nếu điều muốn chứng minh là độ trễ consumer.

### Bài C — Hai ngân sách khác nhau

Viết test 1 có `atMost(10s)` sau lời gọi `place(...)`; test 2 có total budget 10 giây từ **trước** `place(...)`. Tạo tình huống producer chậm và giải thích vì sao test 1 có thể xanh còn test 2 đỏ.

### Bài D — Retry backoff

Giả định policy riêng của bài tập: retry sau 1 và 3 giây, mỗi attempt có thể mất 500 ms. Thiết kế timeout phù hợp và thêm ca FAILED terminal dừng sớm. Không khẳng định đây là lịch retry mặc định của Spring Modulith.

### Bài E — Kiểm thử lỗi publisher và listener

Tạm bỏ `publishEvent` và xác nhận `OrderPublicationTest` đỏ. Khôi phục, rồi bỏ `@ApplicationModuleListener` và xác nhận producer test vẫn có thể xanh nhưng consumer integration timeout. Nhận diện lỗi bằng log, không chỉ tăng budget.

### Bài F — Negative test sau rollback

Dùng `TransactionTemplate` tạo T1, publish rồi rollback. Chứng minh dữ liệu producer không commit và thiết kế kiểm tra listener hậu commit không gây side effect sai. Trình bày lý do `await().until(!hasTask(id))` có thể pass giả.

### Bài G — HTTP timeout theo tầng

Tạo HTTP polling toàn luồng 15 giây, một GET có read timeout 2 giây và poll interval phù hợp. Thiết kế chính sách riêng cho 401/403, 404, 429, 500 và READY. Tránh ignore mọi lỗi rồi đợi chung một timeout.

### Bài H — CI quality gate

Chuyển bài consumer integration sang PostgreSQL Testcontainers, giữ `ApplicationModules.verify()` và bổ sung một reliability test duplicate delivery. Đo xem loại test nào chiếm startup và loại nào chậm do consumer; chỉ điều chỉnh đúng tầng timeout tương ứng.

### Câu hỏi tự đánh giá

1. Vì sao `atMost(10s)` sau `place(...)` không giới hạn thời gian của `place(...)`?
2. Timeout container và timeout chờ task READY khác nhau như thế nào?
3. Vì sao chỉ vài lần chạy không đủ để chọn p99 đáng tin?
4. Khi nào functional test và latency/SLO test cần ngưỡng khác nhau?
5. Tại sao không nên dùng `@Timeout(5s)` bên ngoài Awaitility 12 giây?
6. Vì sao HTTP read timeout phải được định nghĩa riêng?
7. Trạng thái FAILED terminal có nên chờ hết deadline không?
8. `until(!hasTask(id))` có chứng minh “không bao giờ có task” không?
9. Khi nào retry backoff phải được đưa vào budget?
10. Vì sao architecture test vẫn cần dù integration test event đã xanh?

## 27. Checklist trước khi chốt timeout

- [ ] Mệnh đề và completion criterion được xác định rõ.
- [ ] Mốc bắt đầu/kết thúc đo được ghi lại.
- [ ] Phân biệt startup JVM/context/container với consumer latency.
- [ ] Có số liệu latency hoặc retry policy làm căn cứ.
- [ ] Timeout phù hợp môi trường đã đo, không chỉ dựa trên nhãn “CI”.
- [ ] Poll interval không gây tải dư hoặc kéo dài test vô lý.
- [ ] Assertion kiểm tra đúng `orderId` và state nghiệp vụ thật.
- [ ] Timeout Awaitility, HTTP/DB, transaction, JUnit và job được quản lý đúng tầng.
- [ ] FAILED terminal được xử lý sớm, timeout không bị gọi là FAILED nghiệp vụ.
- [ ] Negative assertion không pass ngay do điều kiện phủ định.
- [ ] Test after-commit không bị outer transaction test rollback.
- [ ] Có kiểm tra duplicate/retry/recovery khi đó là hợp đồng.
- [ ] Database production-like được dùng khi isolation/constraint là rủi ro.
- [ ] TestContext cache và Testcontainers lifecycle được kiểm soát.
- [ ] Có negative control làm producer/consumer test đỏ khi bỏ hành vi cần kiểm chứng.
- [ ] `ApplicationModules.verify()` bảo vệ dependency/package trong CI.
- [ ] Điều chỉnh timeout không che hồi quy latency hoặc bỏ coverage.

## 28. Ghi nhớ

**Chọn timeout theo môi trường kiểm thử** là xác định **độ trễ của hành vi nào**, trong **môi trường nào**, dựa trên **bằng chứng và dữ liệu nào**. Timeout của Awaitility là ngân sách chờ một điều kiện, không thay thế timeout HTTP, transaction, container startup, JUnit hay CI job. Thời gian chờ từ producer trả về đến task READY khác với tổng thời gian từ lúc client bắt đầu yêu cầu.

Trong Spring Modulith, dùng `@ApplicationModuleTest` + `PublishedEvents` cho producer contract; integration test + `@ApplicationModuleListener` + Awaitility cho side effect sau commit; bổ sung reliability tests khi cần retry/duplicate/restart. Giữ `ApplicationModules.verify()` trong quality gate để ngăn phụ thuộc sai. **Timeout đúng giúp phát hiện hồi quy kịp thời mà không đánh đổi ranh giới và bằng chứng của luồng bất đồng bộ.**
