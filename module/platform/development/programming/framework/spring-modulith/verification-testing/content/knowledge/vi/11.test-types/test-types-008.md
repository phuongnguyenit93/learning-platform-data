# Event-driven test cho giao tiếp bất đồng bộ

> **Chương:** Test types  
> **Module đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Kiểm thử publisher, consumer, ranh giới transaction và kết quả cuối cùng của giao tiếp bất đồng bộ giữa các application module Spring Modulith.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **sự kiện đã được publish**, **listener đã nhận sự kiện** và **side effect đã được commit**; xác định phép kiểm tra cho từng giai đoạn.
2. Viết `@ApplicationModuleTest` với `PublishedEvents` để kiểm tra kiểu, payload và điều kiện phát sự kiện của module producer.
3. Kiểm thử `@ApplicationModuleListener` chạy sau commit bằng một integration test có database và điều kiện chờ hữu hạn.
4. Giải thích vì sao `@Transactional` trên test, rollback, `@Async` và thời điểm commit có thể gây false positive hoặc false negative.
5. Phân tích các trường hợp sự kiện trùng, xử lý lại, lỗi tạm thời, thứ tự và idempotency; thiết kế test phù hợp với cơ chế giao nhận được cấu hình.
6. Giữ ranh giới module bằng event API công khai và kiểm chứng dependency với `ApplicationModules.verify()`.
7. Kết hợp unit test, module test, integration test và kiểm tra độ bền sự kiện vào quality gate CI.

Một application module có thể xuất bản một sự kiện để module khác tự phản ứng mà không gọi trực tiếp implementation của module đó. Đây là cách giảm ghép nối trong Spring Modulith, nhưng nó mang đến thách thức kiểm thử: **khi phương thức producer trả về, consumer có thể chưa làm xong việc**. Bộ test phải biết chính xác nó đang kiểm chứng thời điểm và hành vi nào.

## 2. Mô hình giao tiếp sự kiện trong Spring Modulith

Ví dụ, module `orders` nhận yêu cầu đặt đơn và module `shipping` tạo công việc giao hàng khi có sự kiện `OrderPlaced`.

~~~mermaid
sequenceDiagram
    participant Client as Test/client
    participant Orders as orders service
    participant DB as Database
    participant Publisher as Event publisher
    participant Listener as shipping listener

    Client->>Orders: place(customerId)
    Orders->>DB: INSERT order trong transaction
    Orders->>Publisher: publish OrderPlaced(orderId)
    Note over Orders,DB: Commit transaction của orders
    Orders-->>Client: orderId
    Publisher-->>Listener: xử lý sau commit
    Listener->>DB: INSERT shipping task trong transaction riêng
    Note over Client,Listener: Listener có thể còn chạy sau khi producer trả về
~~~

Mẫu sử dụng `@ApplicationModuleListener` của Spring Modulith hỗ trợ một listener transactional, thường chạy **bất đồng bộ và sau khi transaction xuất bản sự kiện commit**, với transaction xử lý riêng tùy phiên bản/cấu hình thư viện. Vì vậy cần phân biệt các mốc:

| Mốc | Điều có thể quan sát | Chưa thể kết luận |
| --- | --- | --- |
| Producer gọi `publishEvent` | Có event đúng kiểu/payload được công bố | Transaction đã commit |
| Transaction producer commit | Dữ liệu của producer được lưu thành công | Listener đã chạy xong |
| Listener được kích hoạt | Consumer bắt đầu xử lý event | Side effect đã commit |
| Transaction consumer commit | Side effect có thể được đọc ở database | Retry/replay/restart luôn đáng tin |
| Bản ghi event publication được hoàn tất | Registry xác nhận tiến độ theo adapter đang dùng | Hệ thống ngoài luôn nhận đúng một lần |

**Không nhầm event in-process với broker ngoài.** Những ví dụ chính của bài dùng Spring Application Events giữa module trong cùng JVM. Nếu ứng dụng chuyển event sang Kafka/RabbitMQ, còn phải kiểm tra serialization, routing, broker acknowledgement, consumer group và việc xử lý lại theo hợp đồng giao thức đó.

### Hướng phụ thuộc giữa các module

~~~mermaid
flowchart LR
    O["orders<br/>publish OrderPlaced"] --> E["Event infrastructure"]
    E --> S["shipping<br/>@ApplicationModuleListener"]
    S --> D[("shipping tasks")]
    S -. "tham chiếu kiểu OrderPlaced<br/>ở API module orders" .-> O
~~~

Luồng runtime bắt đầu từ `orders`, nhưng **dependency tĩnh trong mã Java** thường là `shipping → orders`, vì listener import kiểu event `orders.OrderPlaced`. Module `orders` không phải import `shipping.internal.ShippingListener`. Việc consumer dùng kiểu event công khai là hợp lệ khi không vi phạm các giới hạn phụ thuộc đã cấu hình.

## 3. Ma trận kiểm thử cho hệ thống event-driven

Trước khi viết test, chọn rõ câu hỏi và loại bằng chứng.

| Câu hỏi | Test phù hợp | Assertion điển hình |
| --- | --- | --- |
| Có publish `OrderPlaced` đúng payload? | `@ApplicationModuleTest` + `PublishedEvents` | Event chứa đúng `orderId` |
| Đầu vào sai có bị từ chối trước khi phát event? | Unit/module test | Exception và không có event tương ứng |
| Consumer có tạo shipping task sau commit? | Integration test có cả hai module | Cuối cùng `shipping.hasTask(id) == true` |
| Consumer có nhận event khi producer rollback? | Test transaction/after-commit chuyên biệt | Không có side effect; đối chiếu transaction và cơ chế giao sự kiện |
| Event bị giao lại có tạo task trùng không? | Consumer integration/idempotency test | Chỉ một task theo `orderId`, không phát sinh lỗi không xử lý |
| Lỗi consumer có thể retry/replay? | Integration test với publication registry bền vững | Publication còn pending rồi được xử lý khi lỗi được gỡ |
| Đổi schema event có làm hỏng consumer? | Contract/serialization test | Payload vẫn tương thích với consumer |
| Module có tham chiếu package `internal` trái phép? | `ApplicationModules.verify()` | Test kiến trúc báo vi phạm |

**Nguyên tắc:** Một test chỉ chứng minh phần nó quan sát được. `PublishedEvents` báo rằng event đã được publish; nó không thay thế assertion về side effect của listener hay cơ chế lưu bền publication.

## 4. Ví dụ ứng dụng: orders phát sự kiện, shipping xử lý

Ví dụ tự chứa dưới đây dùng Java 17+, Spring Boot 3.x, Spring Data JPA, JUnit 5 và phiên bản Spring Modulith tương thích. Quy tắc minh họa: khi tạo đơn hợp lệ, `orders` lưu đơn và phát `OrderPlaced`; sau khi đơn được commit, `shipping` tạo một task giao hàng.

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderCommands.java                     # API module
│   ├── OrderPlaced.java                       # sự kiện công khai
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── shipping/
    ├── ShippingQueries.java                   # API module
    └── internal/
        ├── ShippingEventListener.java
        ├── ShippingQueryService.java
        └── persistence/
            ├── ShippingTask.java
            └── ShippingTaskRepository.java
~~~

### 4.1. Spring Boot application

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

`@EnableAsync` cho phép xử lý asynchronous theo cấu hình của ứng dụng. Các tính chất như executor, concurrency và cách thu thập exception cần được kiểm soát trong môi trường thực tế. Không suy ra event delivery đáng tin cậy chỉ từ việc bật async.

### 4.2. API và event thuộc sở hữu orders

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

Event là dữ liệu bất biến và có payload tối thiểu. Một event công khai nên mô tả **sự kiện nghiệp vụ đã xảy ra**, không mang JPA entity, repository hay object có liên kết lazy-loading của module producer. Khi cần thêm nhiều trường, cần đánh giá tác động tới consumer và serialization nếu sự kiện đi qua giao thức bên ngoài.

### 4.3. Persistence thuộc orders

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
@Table(name = "sales_orders")
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

public interface OrderRepository extends JpaRepository<OrderEntity, Long> {}
~~~

Dù entity/repository được khai báo Java `public` để thuận tiện cho việc sử dụng trong module và framework, chúng nằm trong package `internal`, không phải public API mà module khác được phép import.

### 4.4. Service publish trong transaction

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
    public long place(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "customerId must not be blank");
        }

        var entity = repository.save(
                new OrderEntity(customerId));

        long id = entity.getId();
        publisher.publishEvent(new OrderPlaced(id));
        return id;
    }
}
~~~

Spring gọi `place(...)` qua transaction proxy, nên khi phương thức kết thúc thành công transaction sẽ được commit theo cấu hình transaction manager. Trường `id` dùng `GenerationType.IDENTITY`; JPA thường cần thực hiện insert để lấy ID, nhưng điều đó **không thay thế commit**.

Trong ví dụ này việc publish diễn ra **bên trong transaction tạo đơn**. Listener sau commit không nên xử lý một đơn mà transaction của producer cuối cùng đã rollback. Đây là tính chất cần kiểm chứng khi giao tiếp bất đồng bộ mang side effect.

### 4.5. API đọc kết quả của shipping

**`src/main/java/com/example/shop/shipping/ShippingQueries.java`**

~~~java
package com.example.shop.shipping;

public interface ShippingQueries {
    boolean hasTask(long orderId);
}
~~~

E2E/integration test sẽ dùng API này để quan sát kết quả cuối luồng, thay vì cần biết repository nội bộ của `shipping`.

### 4.6. Entity và repository thuộc shipping

**`src/main/java/com/example/shop/shipping/internal/persistence/ShippingTask.java`**

~~~java
package com.example.shop.shipping.internal.persistence;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "shipping_tasks")
public class ShippingTask {

    @Id
    private Long orderId;

    protected ShippingTask() {}

    public ShippingTask(long orderId) {
        this.orderId = orderId;
    }

    public Long getOrderId() {
        return orderId;
    }
}
~~~

**`src/main/java/com/example/shop/shipping/internal/persistence/ShippingTaskRepository.java`**

~~~java
package com.example.shop.shipping.internal.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ShippingTaskRepository
        extends JpaRepository<ShippingTask, Long> {
}
~~~

Dùng `orderId` làm primary key thể hiện bất biến “một task cho một đơn” trong ví dụ. Cơ chế này ngăn database lưu hai row cho cùng một đơn, nhưng **không tự khiến listener xử lý trùng an toàn** khi hai lần xử lý cùng diễn ra đồng thời. Phần kiểm thử idempotency sẽ phân tích rủi ro đó.

### 4.7. Listener và query service của shipping

**`src/main/java/com/example/shop/shipping/internal/ShippingEventListener.java`**

~~~java
package com.example.shop.shipping.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;
import com.example.shop.shipping.internal.persistence.ShippingTask;
import com.example.shop.shipping.internal.persistence.ShippingTaskRepository;

@Component
class ShippingEventListener {

    private final ShippingTaskRepository repository;

    ShippingEventListener(ShippingTaskRepository repository) {
        this.repository = repository;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        if (!repository.existsById(event.orderId())) {
            repository.save(new ShippingTask(event.orderId()));
        }
    }
}
~~~

**`src/main/java/com/example/shop/shipping/internal/ShippingQueryService.java`**

~~~java
package com.example.shop.shipping.internal;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.shipping.ShippingQueries;
import com.example.shop.shipping.internal.persistence.ShippingTaskRepository;

@Service
class ShippingQueryService implements ShippingQueries {

    private final ShippingTaskRepository repository;

    ShippingQueryService(ShippingTaskRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional(readOnly = true)
    public boolean hasTask(long orderId) {
        return repository.existsById(orderId);
    }
}
~~~

**Cảnh báo về idempotency:** `existsById(...)` rồi `save(...)` chỉ đủ minh họa một luồng đơn giản. Nếu hai listener cùng xử lý một event, cả hai có thể đọc “chưa tồn tại” trước khi một transaction commit, khiến một lần insert vi phạm primary key. Production cần chính sách xử lý duplicate theo database (upsert, unique violation recovery), xử lý lại event và transaction phù hợp. Test “task tồn tại” không đủ chứng minh listener an toàn trước duplicate delivery.

## 5. Viết test producer bằng @ApplicationModuleTest và PublishedEvents

Trước tiên kiểm tra *producer contract*: gọi API `OrderCommands.place(...)` phải publish đúng một event có `orderId` tương ứng với bản ghi được tạo. Test này đặt trong package `orders` và sử dụng các bean thực của module.

**`src/test/java/com/example/shop/orders/OrderEventsContractTest.java`**

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
        "spring.datasource.url=jdbc:h2:mem:orders-event-test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderEventsContractTest {

    @Autowired
    OrderCommands orders;

    @Test
    void publishes_order_placed_for_created_order(
            PublishedEvents events) {

        long id = orders.place("CUS-101");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }

    @Test
    void does_not_publish_when_input_is_rejected(
            PublishedEvents events) {

        assertThatThrownBy(() -> orders.place(" "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderPlaced.class)).isEmpty();
    }
}
~~~

### Test đã chứng minh điều gì?

- `@ApplicationModuleTest` khởi tạo Spring context phù hợp với module chứa test; ở mode mặc định nó tập trung vào module đó.
- `orders` được inject qua interface công khai; không mock service producer.
- `PublishedEvents` là tiện ích kiểm thử của Spring Modulith để quan sát event đã được publish trong test.
- Assertion xác minh event đúng kiểu và payload `orderId` sinh từ lời gọi thật.
- Input không hợp lệ bị từ chối **trước khi publish** nên tập event quan sát được rỗng trong test thứ hai.

**Giới hạn quan trọng:** Test đầu tiên xác nhận event được publish; nó không chứng minh listener `shipping` đã tồn tại, đã được gọi, hoặc transaction phía consumer đã commit. Test thứ hai chỉ kiểm tra trường hợp validation xảy ra trước thao tác ghi, chưa phải kiểm tra rollback sau khi publish.

Nếu hợp đồng yêu cầu **chính xác một event** cho mỗi lệnh, cần có assertion về số lượng event phù hợp với API `PublishedEvents` ở phiên bản đang dùng. Không suy ra “đúng một” chỉ từ `anySatisfy(...)`, vì assertion ấy vẫn xanh khi có hai event và một event khớp.

### Vì sao không dùng @SpringBootTest cho mọi phép thử?

Để kiểm tra đơn thuần kiểu và payload event của producer, module test có phạm vi hẹp hơn nên nhanh và dễ xác định lỗi hơn. Chỉ mở rộng context khi câu hỏi là **cách consumer xử lý event** hoặc khi cần database/broker/transaction ngoài phạm vi module.

## 6. Integration test consumer xử lý bất đồng bộ sau commit

Để xác nhận `shipping` nhận event, ta cần **cả hai module trong Spring context**, database và transaction thực của service. Bài test sau đặt ở package ứng dụng gốc, dùng `@SpringBootTest` và quan sát thông qua `ShippingQueries`.

**`src/test/java/com/example/shop/OrderShippingIntegrationTest.java`**

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import com.example.shop.orders.OrderCommands;
import com.example.shop.shipping.ShippingQueries;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:shipping-event-test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderShippingIntegrationTest {

    @Autowired
    OrderCommands orders;

    @Autowired
    ShippingQueries shipping;

    @Test
    void creates_shipping_task_after_order_commit() {
        long orderId = orders.place("CUS-202");

        await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() ->
                        assertThat(shipping.hasTask(orderId)).isTrue());
    }
}
~~~

### Tại sao dùng Awaitility?

`@ApplicationModuleListener` có thể xử lý event trên thread khác sau khi transaction producer commit. Việc gọi `shipping.hasTask(orderId)` **ngay sau** `orders.place(...)` có thể trả `false` khi consumer chưa ghi xong. Một assertion tức thời vì thế dễ bị phụ thuộc vào tốc độ CPU, transaction, scheduler và database.

`await().untilAsserted(...)` lặp lại một assertion đến khi đạt hoặc hết thời hạn. Nếu side effect không xuất hiện trong 10 giây, test thất bại. Giá trị 10 giây là ví dụ; CI nên chọn timeout dựa trên thời gian chạy thực tế, không tăng vô hạn để che lỗi.

**Không dùng `Thread.sleep(1000)` thay cho điều kiện quan sát được.** Một khoảng nghỉ cố định có thể quá dài ở máy nhanh và quá ngắn khi CI chịu tải.

### Tại sao không gắn @Transactional lên test?

Test `OrderShippingIntegrationTest` không có `@Transactional`. `orders.place(...)` mở transaction qua proxy, service trả về sau khi transaction manager xử lý commit. Điều đó tạo điều kiện cho listener `AFTER_COMMIT` chạy.

Nếu test gọi service trực tiếp và tự mở transaction bao ngoài bằng `@Transactional`, service có thể tham gia transaction của test; Spring Test thường rollback transaction đó khi test kết thúc. Listener sau commit khi ấy có thể **không được chạy**, khiến test sai về mặt ngữ cảnh.

Với test gửi HTTP đến server thật, transaction của client test và transaction xử lý request ở server là những transaction khác nhau. Không kỳ vọng `@Transactional` trên HTTP client test tự rollback dữ liệu server.

### Phạm vi của test này

Test đã kiểm tra luồng producer → event infrastructure → listener → database consumer → query API. Nó **không** chứng minh một broker ngoài JVM, một email provider hay event publication registry bền vững hoạt động đúng; muốn kiểm tra các thành phần đó phải đưa chúng vào test.

## 7. Kiểm thử transaction rollback và AFTER_COMMIT

Một quy tắc thường gặp là: **không xử lý event tạo đơn khi transaction tạo đơn rollback**. Để chứng minh điều này, cần kích hoạt một transaction thực sự đã cố ghi hoặc publish event rồi rollback.

Một cách kiểm tra có kiểm soát là dùng `TransactionTemplate` bên ngoài lời gọi service. Khi `place(...)` dùng propagation mặc định `REQUIRED`, nó tham gia transaction hiện có; rollback outer transaction làm bản ghi đơn chưa được commit.

Ví dụ sau là trích đoạn **đặt trong integration test** đã inject `OrderCommands`, và có thêm `TransactionTemplate`. Nó minh họa rollback dữ liệu, đồng thời không tuyên bố chứng minh hoàn toàn absence của một side effect bất đồng bộ.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.support.TransactionTemplate;

// Đặt trong một integration test có bean Orders và database test.
@Autowired
TransactionTemplate transactions;

@Test
void outer_transaction_can_rollback_order_creation() {
    long id = transactions.execute(status -> {
        long createdId = orders.place("CUS-ROLLBACK");
        status.setRollbackOnly();
        return createdId;
    });

    assertThat(id).isPositive();

    // Để xác nhận row orders đã rollback, cần một API truy vấn
    // hoặc repository fixture riêng của test. Không suy diễn từ ID.
}
~~~

**Điều cần tránh:** Sau transaction rollback, gọi ngay `shipping.hasTask(id)` rồi assert `false` không phải bằng chứng mạnh rằng listener sẽ *không bao giờ* chạy. Nếu dispatch bất đồng bộ bị chậm, test có thể xanh trước khi listener thực hiện side effect sai.

Một test về rollback và event delivery cần kết hợp:

1. Xác minh transaction producer đã rollback bằng trạng thái persistence quan sát được.
2. Xác nhận listener được đăng ký ở chế độ xử lý sau commit (không dùng fallback execution ngoài transaction trừ khi hợp đồng yêu cầu).
3. Dùng cơ chế kiểm thử event/transaction phù hợp để quan sát có hay không invocation/side effect ở pha commit, thay vì một assertion âm tức thời.
4. Nếu hệ thống có registry, kiểm tra publication state theo semantics thực tế của adapter đang dùng.

Với event thuộc loại **bắt buộc không có khi rollback**, một cách thiết kế thêm là test thành phần publisher với `PublishedEvents` và kiểm tra quy tắc service, sau đó integration test riêng xác nhận side effect chỉ xuất hiện khi commit thật. Cần nhớ `PublishedEvents` có thể ghi nhận event được **publish trước rollback**; nó không đồng nghĩa event đã được consumer xử lý.

## 8. Kiểm thử duplicate delivery và idempotency

Event-driven system phải xác định khả năng một event được xử lý nhiều lần do retry, redelivery hoặc concurrency. **Exactly-once side effect** là một thuộc tính cần thiết kế và xác minh ở cấp dữ liệu/đích nhận, không được tự suy ra từ API `publishEvent`.

Trong ví dụ:

~~~text
Event OrderPlaced(42) lần 1 → shipping_tasks(order_id=42)
Event OrderPlaced(42) lần 2 → ?
~~~

Hợp đồng muốn đạt: sau một hoặc nhiều lần giao cùng event, chỉ có **một** shipping task cho đơn 42.

### Ca test nên có

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Xử lý event mới | Tạo đúng một task |
| Giao lại event sau khi đã xử lý thành công | Không thêm task mới và xử lý theo policy retry |
| Hai listener xử lý cùng event gần như đồng thời | Không tạo hai row; ngoại lệ duplicate được xử lý phù hợp |
| Consumer thất bại giữa chừng rồi nhận lại | Tác động phụ không bị nhân đôi |
| Event cùng `orderId` nhưng dữ liệu khác nhau | Có quy tắc xử lý xung đột/version rõ ràng |

Với xử lý **tuần tự**, có thể đưa một event `OrderPlaced` vào consumer sau khi task tồn tại để xác nhận trạng thái không đổi. Với listener `@ApplicationModuleListener`, việc publish thủ công từ test cần diễn ra **trong transaction được commit**, ví dụ qua `TransactionTemplate`; phát event ngoài transaction có thể không kích hoạt listener transactional theo mặc định.

**Tình huống cạnh tranh:**

~~~text
Listener A: existsById(42) -> false
Listener B: existsById(42) -> false
Listener A: INSERT(42) -> commit
Listener B: INSERT(42) -> unique constraint violation
~~~

Ràng buộc primary key bảo vệ dữ liệu khỏi hai bản ghi trùng, nhưng một invocation có thể vẫn thất bại và gây retry không cần thiết. Trong production, nên triển khai idempotent insert/upsert hoặc xử lý duplicate exception đúng cấp transaction, kèm cơ chế xác định trạng thái đã xử lý. Test phải xác nhận **hành vi phục hồi** chứ không chỉ đếm bản ghi ở database.

### Không gọi method listener trực tiếp để giả lập mọi tính chất bất đồng bộ

Có thể unit test logic xử lý event bằng cách tạo một instance handler Java. Tuy nhiên, gọi thẳng `listener.on(event)` không đi qua Spring event infrastructure, không kích hoạt proxy/transaction semantics của annotation và không kiểm tra asynchronous dispatch. Hãy phân biệt rõ **unit test logic consumer** với **integration test event delivery**.

## 9. Kiểm thử failure, retry và event publication registry

Khi consumer bị lỗi tạm thời, hệ thống cần quyết định có retry không, retry khi nào, tối đa bao nhiêu lần, và làm sao tránh side effect trùng. Spring Modulith có cơ chế **Event Publication Registry** và các adapter để ghi nhận publication đang chờ/đã hoàn tất; khả năng lưu bền, resubmit hoặc retry thực tế phụ thuộc vào module/adapter registry và cấu hình phiên bản đang sử dụng.

### Tình huống failure minh họa

~~~mermaid
flowchart TD
    A["orders publish OrderPlaced"] --> C["orders transaction commit"]
    C --> D["shipping listener"]
    D --> E{"Consumer thành công?"}
    E -- "Có" --> F["Ghi task và hoàn tất xử lý"]
    E -- "Không" --> G["Ghi nhận lỗi / publication chưa hoàn tất"]
    G --> H["Retry hoặc resubmit<br/>theo cấu hình hệ thống"]
    H --> D
~~~

Bản đồ trên mô tả **mục tiêu của một hệ thống có registry/retry được cấu hình**, không khẳng định Spring tự động retry vô hạn ở mọi ứng dụng. Nếu không có durable registry hoặc cơ chế resubmission phù hợp, một lỗi consumer có thể cần xử lý thủ công hoặc dẫn tới event bị bỏ lỡ.

### Test có giá trị cho độ tin cậy

1. Cấu hình **cùng loại publication registry adapter** sẽ dùng trong production nếu muốn chứng minh tính lưu bền.
2. Tạo một failure có thể kiểm soát ở dependency của consumer, ví dụ fake outbound port trả lỗi một lần.
3. Publish event từ transaction producer và cho transaction commit thật.
4. Quan sát publication state khi listener thất bại, theo API/schema và semantics của adapter đã chọn.
5. Gỡ failure hoặc kích hoạt resubmission bằng cơ chế được hỗ trợ.
6. Xác nhận consumer thực hiện đúng side effect một lần và publication được đánh dấu hoàn tất theo hợp đồng.
7. Nếu yêu cầu chịu restart, kiểm tra việc khởi động lại với **cùng storage bền vững**, thay vì chỉ giữ event trong bộ nhớ của một JVM.

Ở mức bài học, không hard-code tên bảng hoặc API điều khiển registry cho mọi phiên bản. Khi triển khai, phải kiểm tra module dependency và cấu hình cụ thể của Spring Modulith được dự án sử dụng.

### Phân biệt các khái niệm

| Khái niệm | Câu hỏi kiểm thử |
| --- | --- |
| At-most-once | Có tránh xử lý trùng khi một event không được retry? Điều gì xảy ra khi mất event? |
| At-least-once | Khi thất bại, event có thể được gửi lại và consumer có chịu được trùng? |
| Exactly-once side effect | Dữ liệu nghiệp vụ có đúng một tác động dù event bị xử lý lại? |
| Durable publication | Publication có tồn tại sau restart/đứt kết nối không? |
| Event ordering | Có được bảo đảm thứ tự cần thiết theo aggregate/key không? |
| Replay/backfill | Khi chạy lại event lịch sử, consumer xử lý/phiên bản hóa thế nào? |

Trong thực tế, thiết kế **at-least-once + idempotent consumer** thường là mục tiêu khả thi hơn việc giả định mọi bước trong hệ thống phân tán có exactly-once delivery.

## 10. Kiểm thử event ordering và payload compatibility

Khi nhiều event liên quan cùng aggregate, thứ tự xử lý có thể quan trọng. Ví dụ:

~~~text
OrderPlaced(42)
OrderCancelled(42)
~~~

Nếu consumer xử lý `OrderCancelled` trước khi `OrderPlaced` do song song hoặc broker partitioning, side effect có thể sai khi code giả định mọi event luôn đến đúng thứ tự.

### Hợp đồng cần xác định

- Consumer phải chịu được event đến sai thứ tự hay hạ tầng bảo đảm thứ tự theo `orderId`?
- Có sequence number hoặc version của aggregate để phát hiện event cũ?
- Khi phát hiện event cũ/trùng, consumer bỏ qua, trì hoãn hay bù trừ?
- Event record đổi trường sẽ ảnh hưởng client Java/serializer như thế nào?

Một event có version có thể được biểu diễn:

~~~java
package com.example.shop.orders;

public record OrderStatusChanged(
        long orderId,
        long aggregateVersion,
        String status
) {}
~~~

Đây là một **ví dụ hợp đồng mở rộng**, không thay thế `OrderPlaced` ở phần code trước. Test phải kiểm tra chính sách mà ứng dụng đã lựa chọn: chẳng hạn version nhỏ hơn version đã áp dụng thì không ghi đè trạng thái mới; event schema không tương thích phải có cơ chế chuyển đổi/khước từ rõ ràng.

Nếu sự kiện chỉ đi trong cùng JVM qua Java object, test compilation và Java contract bảo vệ nhiều thay đổi kiểu. Nếu serialize sang JSON/Avro/Protobuf hoặc broker ngoài, cần bổ sung schema compatibility test và consumer contract test; một module test với `PublishedEvents` không kiểm tra wire format.

## 11. Tổ chức test với database thực tế và Testcontainers

Các test trước sử dụng H2 để giảm thời gian thiết lập. Tuy nhiên, khi xử lý event gắn với transaction, unique constraint, locking, isolation hoặc native SQL, H2 có thể khác PostgreSQL/MySQL/Oracle production.

Có thể bổ sung integration test dùng PostgreSQL Testcontainers (với Spring Boot hỗ trợ `@ServiceConnection`):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrderShippingPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void processes_event_with_postgres_transactions() {
        // Inject OrderCommands và ShippingQueries,
        // gọi orders.place(...), rồi await shipping.hasTask(id).
    }
}
~~~

Để dùng đoạn khung này, cần dependency `spring-boot-testcontainers`, Testcontainers Jupiter/PostgreSQL, JDBC driver và môi trường container runtime. Nó chỉ minh họa **cấu hình container**; assertion event end-to-end thực tế phải được viết giống mục 6.

### Lưu ý schema và migration

- Nếu production dùng Flyway/Liquibase, các integration test quan trọng nên sử dụng migration tương ứng.
- Không giữ URL H2 cứng trong test Testcontainers; nếu không, datasource có thể kết nối sai nơi.
- Mỗi test phải tự tạo dữ liệu, dùng ID đã sinh trong test; không dựa vào “bản ghi đầu tiên có ID 1”.
- Với xử lý async, test không nên dùng dữ liệu mutable toàn cục hoặc phụ thuộc thứ tự test.
- Chạy đồng thời nhiều test dùng chung database cần chiến lược cô lập để tránh nhiễu và lock không mong muốn.

**Độ trung thực của test** tăng lên khi database cùng loại production, nhưng một test trong cùng JVM vẫn chưa bao phủ restart, mạng, broker hoặc nhà cung cấp email/thanh toán bên ngoài nếu các thành phần đó không có trong môi trường.

## 12. Giữ ranh giới kiến trúc của event-driven modules

Chọn event-driven communication không miễn trừ quy tắc phụ thuộc của Spring Modulith. Listener `shipping.internal.ShippingEventListener` được phép import `orders.OrderPlaced` thuộc public API, nhưng không được import `orders.internal.persistence.OrderEntity`.

Ví dụ sai:

~~~java
// Trong module shipping: import implementation của orders.
import com.example.shop.orders.internal.persistence.OrderEntity;
~~~

Ngay cả khi `OrderEntity` có modifier Java `public`, class vẫn nằm ngoài API mặc định của module `orders`. Architecture verification nên phát hiện vi phạm này.

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void module_dependencies_respect_boundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` xác minh mô hình module cùng các quy tắc như vòng phụ thuộc, truy cập API module và whitelist dependency nếu được khai báo. Nó **không** chứng minh sự kiện có được giao hoặc listener xử lý xong. Vì thế luôn cần cả architectural test và behavioral event test.

### Cách suy nghĩ về allowedDependencies

Nếu `shipping` chỉ được sử dụng API của `orders`, có thể quy định chính sách bằng `@ApplicationModule(allowedDependencies = "orders")` tại `shipping/package-info.java`:

~~~java
@ApplicationModule(allowedDependencies = "orders")
package com.example.shop.shipping;

import org.springframework.modulith.ApplicationModule;
~~~

Chỉ khai báo whitelist này khi phù hợp với kiến trúc thực tế. Nó không tự tạo listener, không tăng độ tin cậy event và không thay cho việc kiểm tra hậu commit.

## 13. Lỗi và anti-pattern khi test giao tiếp bất đồng bộ

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Producer test xanh nhưng shipping không có task | `PublishedEvents` chỉ quan sát publish; consumer có thể chưa được bootstrap | Chạy integration test gồm consumer và quan sát side effect |
| Test fail ngẫu nhiên khi assert ngay | Listener async chưa xử lý xong | Dùng Awaitility/điều kiện chờ hữu hạn |
| Không có listener invocation trong test rollback | `@Transactional` test rollback, listener chờ AFTER_COMMIT | Đảm bảo test cần commit được commit thật |
| `@TransactionalEventListener` không chạy khi publish ngoài transaction | Theo mặc định không có transaction commit để kích hoạt | Publish trong transaction hoặc cấu hình hợp đồng khác có chủ đích |
| Test dùng `Thread.sleep` lâu vẫn không ổn định | Đồng bộ theo thời gian đoán | Chờ điều kiện quan sát được, giới hạn timeout |
| Task bị ghi trùng khi replay | Consumer chưa idempotent | Unique key, upsert/duplicate handling và test replay |
| Task không trùng nhưng listener báo lỗi liên tục | Concurrent duplicate insert vi phạm constraint và không được xử lý | Xử lý unique violation phù hợp, test concurrency |
| Retry không xảy ra dù event đã publish | Chưa có registry/resubmission phù hợp | Xác minh adapter và chính sách retry thực |
| Event gửi broker lỗi nhưng module test xanh | Test chỉ dùng in-process event | Thêm contract/integration test broker |
| Module event chạy đúng nhưng `verify()` đỏ | Consumer phụ thuộc vào implementation nội bộ | Sửa import theo public API và dependency rule |

Không áp dụng cùng một cách khắc phục cho mọi lỗi. Khi timeout, cần xem log publisher, transaction commit, exception của listener, trạng thái database và event publication registry (nếu đã cấu hình). Một assertion timeout chỉ là **dấu hiệu cuối luồng**, không chỉ ra chính xác nguyên nhân gốc.

## 14. Đưa event-driven test vào quality gate CI

Ứng dụng Spring Modulith cần nhiều lớp test để ngăn cả lỗi logic, lỗi tích hợp và ranh giới kiến trúc bị phá:

~~~mermaid
flowchart LR
    PR["Pull request"] --> U["Unit & slice tests"]
    U --> A["ApplicationModules.verify()"]
    A --> P["Publisher module tests"]
    P --> C["Consumer integration tests"]
    C --> R["Retry/idempotency tests"]
    R --> G{"Gate bắt buộc xanh?"}
    G -- "Có" --> Merge["Merge"]
    G -- "Không" --> Fix["Sửa lỗi"]
~~~

| Nhóm test | Phạm vi | Nên chạy khi nào? |
| --- | --- | --- |
| Unit test logic event/consumer | Java thuần, fake dependency | Mọi PR |
| Producer module test với `PublishedEvents` | Module producer, payload và validation | Mọi PR |
| Architecture verification | Dependency và package boundary | Mọi PR, bắt buộc |
| Consumer integration test | Producer + consumer + transaction/DB | Mọi PR cho luồng trọng yếu |
| Schema/contract test | Payload công khai và wire format nếu có | Khi thay event contract, có thể mọi PR |
| Duplicate/rollback/retry test | Độ tin cậy event và adapter registry/broker | CI có hạ tầng; trước merge hoặc theo mức rủi ro |
| E2E qua HTTP entry point | Request → event → kết quả quan sát được | Luồng nghiệp vụ quan trọng |

### Cấu hình kiểm thử và dependency

Với Gradle Kotlin DSL trong dự án đã quản lý phiên bản tương thích:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.modulith:spring-modulith-starter-core")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
    testRuntimeOnly("com.h2database:h2")

    // Nếu starter-test của phiên bản dự án không kéo Awaitility:
    // testImplementation("org.awaitility:awaitility")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đây là ví dụ dependency tối thiểu cho test với H2; nó **không** tự bật một publication registry lưu bền. Nếu dự án cần retry/resubmit theo registry, phải bổ sung adapter registry và schema/configuration tương ứng. Với Testcontainers, thêm dependency theo mục 11.

Khi CI tách unit/module/integration tests thành nhiều suite, phải cấu hình việc phát hiện và chạy test chính xác, tránh skip nhóm event hoặc architecture test. Giữ log đủ để lần theo `orderId` và thread/transaction của consumer khi lỗi, đồng thời dùng dữ liệu riêng cho mỗi test để kết quả có thể tái lập.

## 15. Bài thực hành

### Bài A — Kiểm tra publisher contract

Hoàn thiện `OrderEventsContractTest`:

1. Tạo đơn hợp lệ, kiểm tra có `OrderPlaced` đúng `orderId`.
2. Tạo đơn với `customerId` rỗng, kiểm tra ngoại lệ và không có event.
3. Bổ sung chính sách **đúng một event** cho mỗi đơn; viết assertion đếm event phù hợp với API phiên bản dùng.
4. Thử xóa lệnh `publisher.publishEvent(...)` và xác nhận test đỏ.

**Điều kiện đạt:** Test thất bại khi producer quên publish hoặc payload ID sai.

### Bài B — Kiểm tra consumer bất đồng bộ

Dùng `OrderShippingIntegrationTest` với H2 hoặc PostgreSQL Testcontainers. Tạo đơn, sau đó chờ `shipping.hasTask(orderId)`. Tạm bỏ `@ApplicationModuleListener` để thấy test timeout, rồi khôi phục annotation. Giải thích vì sao assertion ngay sau `place(...)` không đáng tin.

### Bài C — Rollback trước commit

Tạo outer transaction bằng `TransactionTemplate`, gọi lệnh tạo đơn và rollback. Xác minh bản ghi producer không được commit, rồi thiết kế chiến lược kiểm tra listener hậu commit không tạo side effect sai. Giải thích tại sao `PublishedEvents` có thể ghi nhận event trước rollback và vì sao `hasTask(id) == false` ngay lập tức là bằng chứng chưa đủ.

### Bài D — Idempotency và replay

Dùng cùng `orderId` để kích hoạt consumer hai lần trong những transaction đã commit. Kiểm tra chỉ một shipping task cuối cùng và không có lỗi không được xử lý. Thêm tình huống hai invocation đồng thời; điều chỉnh code để xử lý unique constraint/idempotent upsert một cách đáng tin.

### Bài E — Retry và registry

Giả lập dependency của consumer thất bại lần đầu. Nếu ứng dụng đã cấu hình event publication registry bền vững, kiểm tra trạng thái publication pending, rồi gỡ lỗi và dùng cơ chế resubmission theo phiên bản. Xác minh side effect cuối cùng đúng một lần. Nếu chưa có registry, giải thích những đảm bảo nào vẫn chưa được kiểm thử.

### Bài F — Ranh giới kiến trúc

Chạy `ApplicationModules.of(ShopApplication.class).verify()`. Thử thêm import từ `shipping` sang `orders.internal.persistence.OrderEntity` trong nhánh thực hành, xác nhận test kiến trúc đỏ; sửa bằng public event `OrderPlaced`.

### Câu hỏi tự kiểm tra

1. Sự khác nhau giữa **publish thành công**, **consumer được gọi** và **side effect commit** là gì?
2. Vì sao test `@Transactional` rollback có thể khiến listener hậu commit không chạy?
3. `PublishedEvents` có chứng minh consumer đã hoàn thành xử lý không?
4. Vì sao primary key theo `orderId` chưa đủ để chứng minh handler an toàn khi duplicate delivery đồng thời?
5. `@ApplicationModuleListener` có tự bảo đảm durable event replay sau restart trong mọi cấu hình không?
6. Khi nào nên dùng H2 và khi nào cần database/broker giống production?
7. Tại sao event integration test xanh vẫn cần `ApplicationModules.verify()`?

## 16. Ghi nhớ

**Event-driven test cho giao tiếp bất đồng bộ** phải kiểm tra từng chặng có ý nghĩa: producer phát đúng event, transaction commit, consumer nhận và xử lý, rồi side effect cuối cùng có thể quan sát được. Trong Spring Modulith, `@ApplicationModuleTest` cùng `PublishedEvents` phù hợp cho **contract của producer**; integration test với cả hai module, database và điều kiện chờ hữu hạn phù hợp cho **consumer sau commit**.

Khi yêu cầu độ tin cậy cao, bổ sung test rollback, duplicate delivery, idempotency, retry và durable publication registry với hạ tầng thực tế. Giữ event trong public API của module và chạy `ApplicationModules.verify()` để bảo vệ ranh giới dependency. Kết hợp các lớp test này trong **quality gate CI** nhằm ngăn phụ thuộc sai, phát hiện hồi quy và giảm rủi ro của xử lý bất đồng bộ.
