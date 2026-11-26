# Xử lý eventual consistency trong assertion

> **Chương:** Async verification  
> **Chương trình:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Viết assertion đúng khi một module Spring Modulith đã commit dữ liệu nhưng module khác, read model hoặc hệ thống tích hợp **chưa kịp phản ánh thay đổi**. Bài học kết hợp `ApplicationModules`, `@ApplicationModuleTest`, event sau commit, JPA, integration test và quality gate CI.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **eventual consistency** và phân biệt nó với lỗi mất dữ liệu, transaction chưa commit, hoặc cache đọc sai.
2. Xác định **điểm quan sát** và **điều kiện hoàn thành** đúng cho một assertion bất đồng bộ, bao gồm entity ID, trạng thái và phiên bản.
3. Viết `Awaitility.untilAsserted(...)` cho read model cuối cùng sẽ nhất quán, không dùng `Thread.sleep(...)` đoán thời gian.
4. Phân biệt việc producer **publish event**, commit transaction và consumer **commit projection**.
5. Thiết kế integration test cho luồng `orders → orderviews` bằng `@ApplicationModuleListener`, JPA và public query API.
6. Phát hiện false positive do dữ liệu cũ, đọc nhầm ID, phiên bản thấp, assertion quá yếu, hoặc một transaction giữ snapshot cũ.
7. Kiểm thử lỗi terminal, retry, duplicate và event đến sai thứ tự; nhận biết giới hạn của việc assert dữ liệu **không tồn tại**.
8. Chọn phạm vi `@ApplicationModuleTest`, full integration, Testcontainers và HTTP E2E theo mệnh đề cần chứng minh.
9. Đưa kiểm chứng eventual consistency và ranh giới dependency vào quality gate CI.

**Câu hỏi trọng tâm:** API đặt hàng trả về một `orderId` hợp lệ nhưng endpoint đọc đơn từ một read model khác module trả “chưa có dữ liệu” trong vài trăm mili giây. **Test nên báo lỗi ngay, đợi cố định, hay chờ một điều kiện có giới hạn?**

Câu trả lời phụ thuộc vào **hợp đồng nhất quán** của hệ thống. Nếu read model được thiết kế cập nhật cuối cùng (*eventually*), test phải cho phép độ trễ được chấp nhận nhưng không được chấp nhận kết quả sai vô thời hạn.

## 2. Eventual consistency là gì trong một modular monolith?

Trong Spring Modulith, các application module chạy trong cùng ứng dụng nhưng có thể có **transaction boundary và thời điểm xử lý khác nhau**. Dù không có Kafka, việc xử lý event bất đồng bộ sau commit đã đủ tạo khoảng thời gian dữ liệu giữa các module chưa đồng nhất.

Ví dụ:

- `orders` là **nguồn sự thật** của đơn đặt hàng.
- `orderviews` sở hữu **read model** phục vụ truy vấn nhanh.
- `orders` publish `OrderPlaced` trong transaction tạo đơn.
- `orderviews` dùng `@ApplicationModuleListener` xử lý sau commit và tạo projection trong transaction riêng.
- Một lời gọi GET ngay sau POST có thể chưa tìm thấy projection dù order ở `orders` đã tồn tại.

~~~mermaid
sequenceDiagram
    participant C as Test/Client
    participant O as orders
    participant DB1 as Orders DB
    participant EV as Spring Events
    participant V as orderviews
    participant DB2 as Projection DB

    C->>O: place(customerId)
    O->>DB1: INSERT order trong T1
    O->>EV: publish OrderPlaced
    O->>DB1: COMMIT T1
    O-->>C: orderId
    C->>V: find(orderId) lần 1
    V-->>C: Optional.empty
    Note over C,V: Đây có thể là độ trễ hợp lệ
    EV-->>V: @ApplicationModuleListener sau commit
    V->>DB2: UPSERT projection trong T2
    V->>DB2: COMMIT T2
    C->>V: find(orderId) lần 2
    V-->>C: OrderView(sourceVersion=1, PLACED)
~~~

**Điểm cốt lõi:** `Optional.empty()` ở lần đọc đầu **chưa chắc là lỗi** nếu contract tuyên bố read model cập nhật bất đồng bộ. Nhưng nếu hệ thống yêu cầu *read-your-writes* ngay lập tức, hành vi trên có thể là lỗi thiết kế hoặc bug.

### Hai loại nhất quán không nên trộn

| Yêu cầu | Phép quan sát mong muốn | Test phù hợp |
| --- | --- | --- |
| **Strong/transactional consistency** | Sau khi API đồng bộ trả thành công, đọc ngay từ nguồn authoritative phải thấy dữ liệu | Assert tức thời trong boundary đã cam kết |
| **Eventual consistency** | Projection sẽ bắt kịp trạng thái nguồn trong một thời hạn hợp lý | Await điều kiện trên read model, có deadline |
| **Session read-your-writes** | Một client cụ thể đọc được thay đổi của chính mình | Test session/token/routing theo contract |
| **Monotonic reads** | Client không thấy version cũ hơn version đã thấy | Kiểm tra version/routing/cache |
| **Causal ordering** | Projection không áp dụng event cũ đè event mới | Test version/out-of-order |
| **Durable recovery** | Sau lỗi/restart, projection cuối cùng hội tụ | Persistent publication + recovery integration |

*Eventual consistency* không có nghĩa “mọi thứ rồi sẽ đúng” một cách vô điều kiện. Hệ thống cần event delivery phù hợp, consumer có khả năng hồi phục, logic idempotent và quan sát được trạng thái khi quá trình hội tụ thất bại.

## 3. Phân biệt ba sự thật: source committed, event published, projection visible

Với một lệnh tạo order, có ít nhất ba assertion khác nhau:

~~~text
P — Published:
    OrderPlaced(orderId, sourceVersion=1) đã được publish.

S — Source committed:
    OrderEntity(orderId) đã commit trong orders.

V — View visible:
    OrderView(orderId, sourceVersion=1, state=PLACED)
    đã commit trong orderviews và đọc được.
~~~

| Mốc | Bằng chứng | Không được suy diễn |
| --- | --- | --- |
| `publishEvent(...)` được gọi | Producer đã công bố event trong cơ chế hiện tại | Transaction T1 chắc chắn commit |
| `PublishedEvents` chứa event | Test quan sát event producer phát | Listener consumer chạy thành công |
| Order đọc được sau T1 | Dữ liệu nguồn đã commit | Projection đã đồng bộ |
| Listener được gọi | Consumer bắt đầu xử lý | Transaction T2 đã commit |
| Read model trả đúng ID, version, state | Projection có kết quả mong muốn | Event registry bền qua restart |
| Registry publication completed | Listener xử lý xong theo semantics của registry | Mọi bước nghiệp vụ bên ngoài đã xong |

Một test chỉ kiểm tra **P** có thể xanh trong khi **V** thất bại. Điều đó không mâu thuẫn: chúng là **hai mệnh đề khác nhau**.

### Khi nào assertion được coi là thành công?

Trong ví dụ, completion criterion là:

> “Với `orderId` vừa tạo, public query API của `orderviews` trả một projection có **cùng ID**, **cùng customerId**, **sourceVersion = 1** và **state = PLACED** trong ngân sách chờ đã thỏa thuận.”

Nó mạnh hơn “`findAll()` có ít nhất một row” hoặc “listener log thành công”, vì chứng minh đúng **request**, đúng **dữ liệu** và đúng **phiên bản**.

## 4. Bẫy của assertion tức thời

Sai lầm thường gặp:

~~~java
UUID orderId = orders.place("CUS-01");

// Có thể chạy trước khi consumer T2 commit.
assertThat(orderViews.find(orderId)).isPresent();
~~~

Nếu `orderviews` cập nhật bất đồng bộ, kết quả có thể:

~~~text
Run 1: projection đã commit trước khi assert -> PASS
Run 2: listener chưa được schedule       -> FAIL
Run 3: DB pool đang bận                  -> FAIL
Run 4: context warm, thread pool rảnh    -> PASS
~~~

**Đó là flaky test do assertion không phù hợp consistency contract.** Không nhất thiết business logic sai.

### Sai lầm khác: thêm Thread.sleep

~~~java
UUID orderId = orders.place("CUS-01");
Thread.sleep(2_000);
assertThat(orderViews.find(orderId)).isPresent();
~~~

- Consumer xử lý trong 20 ms → test vẫn lãng phí 2 giây.
- Consumer xử lý trong 2.100 ms → test fail dù hợp đồng cho phép.
- Consumer không bao giờ xử lý → test chỉ báo absence, ít diagnostic.
- Consumer cập nhật **sai version** → assertion `isPresent()` vẫn xanh.

**Giải pháp:** Chờ **kết quả phù hợp hợp đồng**, không chờ một khoảng thời gian cố định.

## 5. Mẫu assertion cơ bản với Awaitility

Awaitility thử lại một predicate hoặc assertion đến khi đạt điều kiện, hoặc đến hết deadline.

### 5.1. Chờ sự tồn tại đúng ID

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
                assertThat(orderViews.find(orderId)).isPresent());
~~~

Điều kiện này tốt hơn `Thread.sleep` và chờ đúng `orderId`. Nhưng nó **chỉ chứng minh tồn tại**; nếu dữ liệu projection có thể stale hoặc sai, cần assertion mạnh hơn.

### 5.2. Chờ snapshot đầy đủ

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            var snapshot = orderViews.find(orderId);
            assertThat(snapshot).isPresent();

            var view = snapshot.orElseThrow();
            assertThat(view.orderId()).isEqualTo(orderId);
            assertThat(view.customerId()).isEqualTo(customerId);
            assertThat(view.sourceVersion()).isEqualTo(1L);
            assertThat(view.state()).isEqualTo(OrderViewState.PLACED);
        });
~~~

**Điểm mạnh:** Mỗi lần poll lấy một snapshot rồi kiểm tra **ID + payload + version + state trên cùng snapshot**. Không vô tình assert hai trạng thái lấy từ hai lần query khác nhau.

### 5.3. Dạng predicate với until

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .until(() -> orderViews.find(orderId)
                .filter(view -> view.sourceVersion() == 1L)
                .filter(view -> view.state() == OrderViewState.PLACED)
                .isPresent());
~~~

`until` gọn khi predicate là boolean. `untilAsserted` thường cho failure message giàu ngữ nghĩa khi cần kiểm tra nhiều trường. Chọn **một** phong cách đủ rõ cho mục tiêu.

### 5.4. Không tự ý ignore mọi exception

Nếu database tạm thời unavailable, ứng dụng có thể quyết định thử lại theo một policy. Nhưng nếu query bị `SQLGrammarException` vì thiếu bảng, hoặc HTTP trả 401 do auth sai, việc ignore mọi exception có thể biến lỗi rõ ràng thành một timeout mơ hồ.

Hãy phân loại:

- **Trạng thái tạm thời hợp lệ:** `Optional.empty()` hoặc `PROCESSING` theo contract → poll tiếp.
- **Lỗi transient có policy:** 429/503, kết nối bị ngắt theo kịch bản resilience → retry giới hạn và có log.
- **Lỗi terminal/bug:** Schema mismatch, sai quyền truy cập, payload không giải mã được → fail rõ, không nuốt lỗi.

Không thêm `ignoreExceptions()` một cách mù quáng chỉ để test “ổn định”.

## 6. Tổ chức module mẫu: orders → orderviews

Cấu trúc dự án minh họa:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/                               # Application module nguồn
│   ├── OrderCommands.java                 # Public API
│   ├── OrderPlaced.java                   # Public event
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── orderviews/                            # Application module read model
    ├── OrderViews.java                   # Public query API
    ├── OrderView.java                    # Public snapshot
    ├── OrderViewState.java               # Public enum
    └── internal/
        ├── OrderPlacedProjectionListener.java
        ├── OrderViewQueryService.java
        └── persistence/
            ├── OrderViewEntity.java
            └── OrderViewRepository.java
~~~

Spring Modulith thường phát hiện các package trực tiếp dưới application root là application modules. Package root là API mặc định; `internal` giữ implementation riêng.

### Quy ước ownership

- `orders` sở hữu **dữ liệu nghiệp vụ authoritative** cho order.
- `orderviews` sở hữu projection phục vụ truy vấn; không sửa trực tiếp source-of-truth order.
- Consumer được import `orders.OrderPlaced` nhưng **không** import `orders.internal.persistence.OrderRepository`.
- Projection có thể tạm thời **đi sau** source. Điều đó phải được mô tả trong contract API.

Với hệ thống cần read-your-writes ngay, có thể truy vấn trực tiếp authoritative module hoặc thiết kế response trả snapshot đã commit từ producer. Không dùng eventual read model như một câu trả lời tức thời chỉ vì tiện.

## 7. Mã nguồn producer: nguồn sự thật và public event

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

`@EnableAsync` cho phép Spring dùng executor cho listener async theo cấu hình. Nó **không tự bật** durable event registry, retry vô hạn hay exactly-once delivery.

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

public record OrderPlaced(
        UUID orderId,
        String customerId,
        long sourceVersion) {}
~~~

Event record thuộc public API và có revision rõ ràng để consumer biết projection đang phản ánh phiên bản nguồn nào.

### 7.3. Persistence nguồn

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

    @Column(nullable = false)
    private long sourceVersion = 1L;

    protected OrderEntity() {}

    public OrderEntity(String customerId) {
        this.customerId = customerId;
    }

    public UUID getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public long getSourceVersion() {
        return sourceVersion;
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

Ví dụ dùng Java 17+, Jakarta Persistence và JPA provider hỗ trợ `GenerationType.UUID`. Với ID kiểu khác, thay theo database mà không ảnh hưởng lập luận về eventual consistency.

### 7.4. Service tạo order, publish trong T1

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

        OrderEntity entity = orders.save(
                new OrderEntity(customerId));

        publisher.publishEvent(new OrderPlaced(
                entity.getId(),
                entity.getCustomerId(),
                entity.getSourceVersion()));

        return entity.getId();
    }
}
~~~

`publishEvent(...)` được gọi **trước thời điểm commit T1** trong body của service. Khi service được gọi qua transaction proxy và không có transaction bao ngoài, T1 thường được commit khi lệnh hoàn tất thành công. Nhưng read model `orderviews` vẫn cần transaction T2 riêng để cập nhật.

## 8. Mã nguồn consumer: read model có thể lag sau nguồn

### 8.1. Public snapshot và query API

**`src/main/java/com/example/shop/orderviews/OrderViewState.java`**

~~~java
package com.example.shop.orderviews;

public enum OrderViewState {
    PLACED
}
~~~

**`src/main/java/com/example/shop/orderviews/OrderView.java`**

~~~java
package com.example.shop.orderviews;

import java.util.UUID;

public record OrderView(
        UUID orderId,
        String customerId,
        long sourceVersion,
        OrderViewState state) {}
~~~

**`src/main/java/com/example/shop/orderviews/OrderViews.java`**

~~~java
package com.example.shop.orderviews;

import java.util.Optional;
import java.util.UUID;

public interface OrderViews {
    Optional<OrderView> find(UUID orderId);
}
~~~

`Optional.empty()` chỉ có nghĩa **projection chưa được quan sát tại thời điểm đọc**. Nó không thể tự phân biệt order ID không tồn tại, consumer đang chạy, consumer lỗi hoặc event đã mất. Khi đưa read model lên API công khai, cần một chiến lược diễn đạt UNKNOWN/PENDING/FAILED phù hợp.

### 8.2. Entity và repository của projection

**`src/main/java/com/example/shop/orderviews/internal/persistence/OrderViewEntity.java`**

~~~java
package com.example.shop.orderviews.internal.persistence;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import com.example.shop.orderviews.OrderView;
import com.example.shop.orderviews.OrderViewState;

@Entity
@Table(name = "order_views")
public class OrderViewEntity {

    @Id
    private UUID orderId;

    @Column(nullable = false)
    private String customerId;

    @Column(nullable = false)
    private long sourceVersion;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderViewState state;

    protected OrderViewEntity() {}

    public OrderViewEntity(
            UUID orderId,
            String customerId,
            long sourceVersion,
            OrderViewState state) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.sourceVersion = sourceVersion;
        this.state = state;
    }

    public OrderView snapshot() {
        return new OrderView(
                orderId,
                customerId,
                sourceVersion,
                state);
    }
}
~~~

**`src/main/java/com/example/shop/orderviews/internal/persistence/OrderViewRepository.java`**

~~~java
package com.example.shop.orderviews.internal.persistence;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderViewRepository
        extends JpaRepository<OrderViewEntity, UUID> {}
~~~

### 8.3. Listener cập nhật projection sau commit

**`src/main/java/com/example/shop/orderviews/internal/OrderPlacedProjectionListener.java`**

~~~java
package com.example.shop.orderviews.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;
import com.example.shop.orderviews.OrderViewState;
import com.example.shop.orderviews.internal.persistence.OrderViewEntity;
import com.example.shop.orderviews.internal.persistence.OrderViewRepository;

@Component
class OrderPlacedProjectionListener {

    private final OrderViewRepository views;

    OrderPlacedProjectionListener(OrderViewRepository views) {
        this.views = views;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        if (!views.existsById(event.orderId())) {
            views.save(new OrderViewEntity(
                    event.orderId(),
                    event.customerId(),
                    event.sourceVersion(),
                    OrderViewState.PLACED));
        }
    }
}
~~~

Listener này được dùng theo mô hình Spring Modulith phổ biến: **sau commit**, **bất đồng bộ**, **trong transaction riêng**. Do đó query `order_views` ngay sau `orders.place(...)` có thể tạm thời trả rỗng.

**Giới hạn quan trọng của code mẫu:** `existsById` rồi `save` là implementation minh họa cho **một event tạo mới**, chưa phải upsert production an toàn với duplicate/concurrent delivery hoặc event version cao hơn. Khi cần idempotency, update version có điều kiện và database constraint, xem mục 15–16.

### 8.4. Service đọc projection qua API

**`src/main/java/com/example/shop/orderviews/internal/OrderViewQueryService.java`**

~~~java
package com.example.shop.orderviews.internal;

import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.orderviews.OrderView;
import com.example.shop.orderviews.OrderViews;
import com.example.shop.orderviews.internal.persistence.OrderViewRepository;

@Service
class OrderViewQueryService implements OrderViews {

    private final OrderViewRepository views;

    OrderViewQueryService(OrderViewRepository views) {
        this.views = views;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<OrderView> find(UUID orderId) {
        return views.findById(orderId)
                .map(view -> view.snapshot());
    }
}
~~~

Một lần gọi `OrderViews.find(...)` trả snapshot immutable, không để test giữ entity JPA managed và mong entity ấy tự refresh. Khi test không mở outer transaction dài, mỗi lần poll có thể mở transaction đọc phù hợp để nhìn thấy dữ liệu mới commit.

## 9. Producer module test: xác minh event, chưa chờ read model

Đặt test trong package `com.example.shop.orders`:

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
        "spring.datasource.url=jdbc:h2:mem:orders-publication;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderPublicationTest {

    @Autowired
    OrderCommands orders;

    @Test
    void publishes_order_placed_with_version(
            PublishedEvents events) {

        var orderId = orders.place("CUS-PUBLISH");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event -> {
                    assertThat(event.orderId()).isEqualTo(orderId);
                    assertThat(event.customerId())
                            .isEqualTo("CUS-PUBLISH");
                    assertThat(event.sourceVersion()).isEqualTo(1L);
                });
    }

    @Test
    void invalid_customer_cannot_publish(
            PublishedEvents events) {

        assertThatThrownBy(() -> orders.place(" "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderPlaced.class)).isEmpty();
    }
}
~~~

**Đã chứng minh:** Producer publish một event `OrderPlaced` phù hợp type, customerId, orderId và revision.

**Chưa chứng minh:** Listener `orderviews` được nạp, projection đã commit, event bền vững qua restart hoặc đúng một event duy nhất được publish. `anySatisfy(...)` chỉ đòi **ít nhất một** event khớp. Nếu yêu cầu cardinality, thêm assertion đếm event theo API phiên bản sử dụng.

**Tại sao không thêm Awaitility vào đây?** Claim của bài test nằm ở producer publication; một module test giới hạn phạm vi có thể không bootstrap `orderviews`. Chờ projection ở test này vừa không đúng boundary vừa làm test chậm/khó chẩn đoán.

## 10. Consumer integration test: chờ dữ liệu hội tụ

Để kiểm tra `orders → event → orderviews`, dùng context có cả hai module, transaction manager và database thật.

**`src/test/java/com/example/shop/OrderProjectionIntegrationTest.java`**

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
import com.example.shop.orderviews.OrderViews;
import com.example.shop.orderviews.OrderViewState;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:orders-projection;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderProjectionIntegrationTest {

    @Autowired
    OrderCommands orders;

    @Autowired
    OrderViews orderViews;

    @Test
    void view_eventually_matches_committed_order() {
        String customerId = "CUS-" + UUID.randomUUID();
        UUID orderId = orders.place(customerId);

        await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() -> {
                    var found = orderViews.find(orderId);

                    assertThat(found).isPresent();

                    var view = found.orElseThrow();
                    assertThat(view.orderId()).isEqualTo(orderId);
                    assertThat(view.customerId())
                            .isEqualTo(customerId);
                    assertThat(view.sourceVersion())
                            .isEqualTo(1L);
                    assertThat(view.state())
                            .isEqualTo(OrderViewState.PLACED);
                });
    }
}
~~~

### Tại sao đây là assertion eventual consistency?

- **Nguồn tạo mới:** `orders.place(...)` commit transaction do service quản lý.
- **Điểm quan sát:** API `OrderViews.find(orderId)` của module read model.
- **Thời gian:** Awaitility cho phép khoảng lag có giới hạn.
- **Correlation:** ID và customer ID lấy từ chính lệnh vừa thực hiện.
- **Version:** `sourceVersion=1` xác minh projection đại diện đúng revision của nguồn.
- **State:** `PLACED` là kết quả nghiệp vụ được định nghĩa.
- **Lỗi rõ ràng:** Nếu listener mất, query sai, version sai hoặc transaction T2 rollback, điều kiện không đạt và test thất bại.

### Vì sao không dùng @Transactional trên test?

Nếu method test có `@Transactional`, lời gọi `orders.place(...)` có thể tham gia outer transaction của test rồi bị Spring Test rollback sau cùng. Listener `AFTER_COMMIT` khi ấy không có commit để kích hoạt. Hơn nữa, một transaction đọc kéo dài có thể giữ snapshot cũ, khiến polling không thấy projection dù consumer đã commit.

Bài test trên **không gắn `@Transactional`** để service producer tự commit và mỗi query được thực hiện qua Spring bean public API.

### Ngân sách 10 giây có nghĩa gì?

`atMost(10s)` chỉ giới hạn thời gian polling **sau khi `place(...)` trả về**. Nếu yêu cầu là “từ lúc HTTP request bắt đầu tới projection sẵn sàng dưới 10 giây”, phải bắt đồng hồ từ trước request. Giá trị 10 giây trong bài là minh họa; production SLO cần đo phân phối độ trễ và tải phù hợp.

## 11. Bảng phản mẫu assertion và cách sửa

| Assertion hoặc thói quen | Vì sao sai/yếu | Sửa thế nào |
| --- | --- | --- |
| `assertThat(find(id)).isPresent()` ngay sau producer | Projection có thể chưa kịp cập nhật | Await trạng thái với deadline |
| `Thread.sleep(2000)` rồi assert | Dễ flaky, luôn đợi đủ và không giúp chẩn đoán | Await điều kiện có ý nghĩa |
| `await().until(() -> countAll() > 0)` | Có thể thấy dữ liệu từ test cũ | Query theo correlation ID |
| `await().until(() -> find(id).isPresent())` | Có thể chỉ thấy phiên bản stale | Assert version + state + payload |
| `await().until(() -> view.version() >= 2)` | Version 3 có thể là trạng thái khác; chưa chắc đúng kỳ vọng | Gắn version với state/correlation contract |
| Đọc entity một lần rồi chờ field thay đổi | Entity/snapshot không tự refresh | Query snapshot mới trong mỗi poll |
| Giữ transaction test xuyên các lần poll | Snapshot cũ hoặc ngăn commit source | Transaction đọc ngắn, không bao T1 |
| `ignoreExceptions()` cho mọi loại lỗi | Che lỗi schema/auth/serialization | Chỉ retry lỗi transient đã định nghĩa |
| `await().until(() -> !find(id).isPresent())` | Có thể true ngay trước khi consumer chạy | Test âm có kiểm soát, xem mục 19 |
| Chỉ kiểm tra `PublishedEvents` | Chưa có bằng chứng read model cập nhật | Cross-module integration test |
| Kết luận timeout = event mất | Timeout chỉ là “chưa thấy trong deadline” | Quan sát transaction, listener và registry |
| Bỏ `ApplicationModules.verify()` vì integration xanh | Vẫn có thể import package `internal` sai | Giữ architecture gate riêng |

Một assertion tốt phải có khả năng **bị bác bỏ** bởi lỗi quan trọng của use case. Nếu đổi event payload thành sai `customerId` mà test vẫn xanh, assertion chưa đủ mạnh.

## 12. Mỗi lần poll phải tạo một phép đọc mới có ý nghĩa

Có một lỗi tưởng khó hiểu: task/projection đã commit trong database, nhưng test vẫn đọc trạng thái cũ cho tới timeout.

### 12.1. Không giữ snapshot lấy trước Awaitility

Sai:

~~~java
var snapshot = orderViews.find(orderId);

await()
        .atMost(Duration.ofSeconds(10))
        .until(() -> snapshot.isPresent());
~~~

`snapshot` là một `Optional` đã được tính trước khi chờ. Lặp lại predicate **không gọi lại query**, nên kết quả không bao giờ thay đổi.

Đúng:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .until(() -> orderViews.find(orderId).isPresent());
~~~

### 12.2. Không giữ JPA entity managed cũ

Trong persistence context, JPA có first-level cache. Nếu test giữ một entity/projection cũ và gọi getter liên tục, nó có thể không phản ánh thay đổi đã commit từ transaction khác.

**Giải pháp:** Query lại qua một public read API trả snapshot immutable; tùy setup có thể cần `EntityManager.clear()`, refresh hoặc transaction ngắn riêng, nhưng không ép module khác lộ EntityManager/repository nội bộ chỉ để assertion dễ viết.

### 12.3. Chú ý transaction isolation

| Isolation/điểm đọc | Rủi ro với polling | Điều cần kiểm tra |
| --- | --- | --- |
| Read committed, transaction ngắn | Mỗi query thường nhìn dữ liệu đã commit mới | Vẫn cần kiểm tra cache và replica |
| Repeatable read với transaction dài | Có thể giữ snapshot cũ | Không poll trong một outer transaction kéo dài |
| Query qua read replica | Có thể có replication lag | Chọn observation point đúng contract |
| Cache ứng dụng TTL dài | Query luôn trả dữ liệu stale cho đến khi hết TTL | Invalidation, version/token, TTL |
| Test database in-memory | Không đại diện hoàn toàn DB production | Dùng Testcontainers nếu isolation/locking quan trọng |

**Đợi lâu không sửa được một vòng polling chỉ đọc snapshot cũ.** Lỗi nằm ở **cách quan sát**, không phải con số timeout.

## 13. Nhất quán cuối cùng phải có giới hạn và khả năng chẩn đoán

Một test đúng không chờ mãi:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
                assertThat(orderViews.find(orderId)).isPresent());
~~~

### Vai trò của atMost và pollInterval

- `atMost` là ngân sách tối đa cho phép test quan sát dữ liệu hội tụ.
- `pollInterval` quyết định tần suất query; quá ngắn gây tải, quá dài làm test phản hồi chậm.
- Condition có thể thành công sớm, không đợi hết timeout.
- Timeout của một HTTP GET/DB query riêng cần có giới hạn phù hợp; Awaitility không tự là thay thế hoàn hảo cho network read timeout.

### Gợi ý lựa chọn theo loại test, không phải chuẩn mặc định

| Môi trường | Timeout ban đầu có thể thử | Poll interval ban đầu có thể thử |
| --- | --- | --- |
| In-process consumer + H2 | 5–10 giây | 50–200 ms |
| PostgreSQL Testcontainers đã sẵn sàng | 5–15 giây | 100–250 ms |
| HTTP `RANDOM_PORT` + local DB | 10–20 giây | 100–500 ms |
| Broker/registry có retry | Theo tổng backoff hợp lệ | Theo retry schedule |
| External provider sandbox | Theo hợp đồng và latency đo thực tế | Rate limit/backoff phù hợp |

Những giá trị là điểm bắt đầu cho phép **đo**. Không tự đặt “CI gấp đôi local”; hãy dùng các số liệu như p95/p99 với cỡ mẫu đủ, tải đại diện và baseline. Functional test eventual success và performance SLO test không nhất thiết có cùng ngưỡng.

### Khi timeout, cần báo gì?

Một diagnostic có ích:

~~~text
workflowId=...
orderId=...
expectedSourceVersion=1
expectedState=PLACED
lastObservedVersion=<none>
lastObservedState=<none>
publisherCommit=COMMITTED
consumerAttempt=...
publicationPending=...
elapsedWaitMs=...
~~~

Các trường trên là **mẫu instrumentation do ứng dụng/test bổ sung**, không phải log tự động có sẵn nguyên dạng của Spring Modulith. Không đưa dữ liệu nhạy cảm vào log không cần thiết.

## 14. Assertion cho read model có revision lớn hơn 1

Một projection thường được cập nhật nhiều lần:

~~~text
OrderPlaced(orderId, revision=1, state=PLACED)
OrderPaid  (orderId, revision=2, state=PAID)
OrderShipped(orderId, revision=3, state=SHIPPED)
~~~

Nếu test cần xác minh read model đã bắt kịp **revision 2**, chỉ assert `find(id).isPresent()` là quá yếu: projection revision 1 đã tồn tại từ trước.

### Chờ version cụ thể

Một dạng condition:

~~~java
long expectedRevision = 2L;

await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            OrderView snapshot = orderViews.find(orderId)
                    .orElseThrow();

            assertThat(snapshot.sourceVersion())
                    .isEqualTo(expectedRevision);
            assertThat(snapshot.state())
                    .isEqualTo(OrderViewState.PAID);
        });
~~~

**Đoạn trên là ví dụ cho mô hình mở rộng**, cần bổ sung `PAID` trong `OrderViewState` và các event/handler tương ứng. Không copy nguyên vào source tạo order revision 1 ở mục 7–8 rồi kỳ vọng chạy.

### Dùng >= hay ==?

- `version == expected` phù hợp khi test muốn quan sát **snapshot chính xác** ở một mốc, và không có update mới hợp lệ chạy đồng thời.
- `version >= expected` phù hợp khi contract là “read model đã bắt kịp **ít nhất** revision đó”, nhưng **không tự bảo đảm state của revision mong đợi** còn hiện diện sau một update mới.
- Nếu nhiều cập nhật cạnh tranh, thiết kế assertion theo **bất biến nghiệp vụ của trạng thái mới nhất**, không ép state trung gian phải xuất hiện.

Ví dụ nếu projection đã lên revision 3 `SHIPPED` thì assertion “đến revision 2 và state=PAID” không nên fail nếu **yêu cầu thực** chỉ là “đã xử lý tối thiểu revision 2”. Khi ấy chọn điều kiện `sourceVersion >= 2` **và một trạng thái hợp lệ theo business progression**, không assert `PAID` đúng lúc có thể bị bỏ qua.

### Khi nào cần revision từ API?

Có thể để lệnh update trả `expectedRevision` hoặc một read token. Client/test dùng token đó để chờ view bắt kịp, không đoán bằng thời gian hay thứ tự tác vụ.

~~~text
POST command -> 202 Accepted
response: { orderId, expectedVersion: 2 }

GET projection:
{ orderId, sourceVersion: 1, state: "PLACED" }   # stale
GET projection:
{ orderId, sourceVersion: 2, state: "PAID" }     # caught up
~~~

Đây là **hợp đồng JSON minh họa**, không phải API Spring Modulith tạo sẵn. Ứng dụng phải định nghĩa token/version và quyết định việc client được poll hay không.

## 15. Event đến trùng hoặc sai thứ tự: hội tụ không tự xảy ra

Trong hệ thống bất đồng bộ, event có thể được giao lại và có thể đến khác thứ tự, đặc biệt khi có retry hoặc nhiều consumer/executor. Nếu handler luôn ghi đè projection mà không kiểm tra revision, một event cũ có thể **làm read model đi lùi**.

~~~text
Event revision 2 -> projection state PAID, version 2
Event revision 1 đến muộn -> projection state PLACED, version 1
=> Read model thụt lùi dù cả hai handler "thành công".
~~~

### Bất biến cần bảo vệ

1. **Không ghi đè bằng version cũ:** Khi đã áp dụng revision 2, event revision 1 không làm state lùi.
2. **Replay idempotent:** Event revision 2 được xử lý lại không nhân đôi side effect.
3. **Phát hiện gap:** Khi nhận revision 4 trong khi projection mới revision 2, policy phải rõ: áp dụng snapshot đầy đủ, đợi revision 3, hay rebuild từ source.
4. **Atomicity:** Điều kiện kiểm tra version và ghi phải an toàn dưới concurrency.
5. **Correlation:** Không lấy revision của order A để suy luận trạng thái order B.

### Ví dụ SQL upsert có điều kiện cho PostgreSQL

Giả sử event mang **snapshot đầy đủ** tương ứng một revision và bảng có unique/primary key `order_id`:

~~~sql
INSERT INTO order_views
    (order_id, customer_id, source_version, state)
VALUES
    (:id, :customer_id, :version, :state)
ON CONFLICT (order_id)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    source_version = EXCLUDED.source_version,
    state = EXCLUDED.state
WHERE order_views.source_version < EXCLUDED.source_version;
~~~

**Tác dụng:** Một update mới hơn có thể thắng; event trùng revision hoặc cũ hơn không ghi đè state mới. Nhưng đây là **chiến lược chỉ phù hợp nếu mỗi event là snapshot đủ dữ liệu**. Nếu event là *delta* cần áp dụng theo thứ tự, bỏ qua event cũ/gap có thể làm sai projection; khi đó cần ordering, version continuity, outbox hoặc rebuild policy khác.

### Không dùng “check-then-save” để bảo đảm concurrency

~~~java
if (incomingVersion > currentVersion) {
    repository.save(updatedEntity);
}
~~~

Nếu hai transaction cùng đọc current version 1, rồi ghi version 2 và 3 không có khóa/optimistic locking, kết quả cuối có thể bị ghi lùi về 2. Cần **atomic compare-and-set**, database conditional update, khóa phù hợp hoặc optimistic locking được xử lý đúng.

### Test out-of-order

| Kịch bản | Oracle đáng tin |
| --- | --- |
| Apply revision 1 rồi 2 | Projection cuối version 2, state mới |
| Apply revision 2 rồi 1 | Projection không đi lùi về 1 |
| Apply revision 2 hai lần | Một business effect và không lỗi replay không xử lý |
| Hai event revision khác nhau đồng thời | Final state đúng policy, không lost update |
| Thiếu revision trung gian | State/quy trình gap xử lý đúng hợp đồng |

**Không thể kết luận idempotency chỉ vì assertion Awaitility cuối cùng thấy version 2.** Có thể handler đã ném lỗi nhiều lần rồi trạng thái may mắn đúng. Reliability test phải quan sát exception, retry và publication state theo policy.

## 16. Consumer terminal failure và retry phải có assertion riêng

Một projection chậm chưa chắc hỏng; nhưng consumer cũng có thể gặp lỗi **không thể phục hồi**.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING
    PROCESSING --> APPLIED: Projection commit
    PROCESSING --> RETRY_WAIT: Lỗi tạm thời
    RETRY_WAIT --> PROCESSING: Retry
    PROCESSING --> FAILED: Lỗi terminal
    RETRY_WAIT --> FAILED: Hết retry policy
    APPLIED --> [*]
    FAILED --> [*]
~~~

Đây là mô hình trạng thái giám sát **minh họa**, không phải enum được Spring Modulith tự sinh. Một ứng dụng không có workflow state table có thể chỉ thấy projection vắng mặt; khi đó test cần thêm log, failure injection hoặc publication registry để phân biệt **lag bình thường** với **error**.

### Nếu có public workflow state

~~~text
PENDING / PROCESSING / RETRY_WAIT -> tiếp tục poll
APPLIED và sourceVersion phù hợp -> thành công
FAILED terminal                  -> fail sớm, hiển thị reason
Hết deadline chưa terminal       -> timeout/unknown
~~~

Không nên dùng `untilAsserted` chỉ kiểm tra `APPLIED` mà quên trạng thái `FAILED` đã rõ; test sẽ đợi vô ích.

### Khi nào ignore exception?

- Transient database/network exception được chấp nhận trong kịch bản resilience đã định nghĩa: có thể retry có giới hạn.
- Schema validation error, missing bean, serialization bug, HTTP 401/403: thường phải fail rõ.
- Mọi exception được ignore: dễ biến bug xác định thành một timeout mơ hồ.

Khi API/framework hỗ trợ fail-fast, dùng đúng semantics và version; nếu không, triển khai phân loại trạng thái/lỗi ngoài vòng polling một cách rõ ràng.

## 17. HTTP API E2E: không đòi read-after-write tức thời khi contract là eventual

Một API có thể tạo order rồi trả:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"orderId":"...", "expectedVersion":1}
~~~

Client sau đó poll một **read model status resource**:

~~~text
GET /api/order-views/{id}

Lần đầu: 202/PENDING hoặc 404 theo contract
Lần sau: 200 + {id, sourceVersion:1, state:"PLACED"}
~~~

Một số API luôn trả HTTP 200 cho status resource kèm `state=PENDING`; một số dùng HTTP 404 cho projection chưa tồn tại. **Không có một quy ước bắt buộc chung**. Test phải phản ánh hợp đồng đã công bố và không coi mọi 404 là transient nếu nó có thể nghĩa ID không tồn tại.

### Khung E2E kiểm tra eventual consistency qua HTTP

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
class OrderReadModelHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void projection_eventually_reflects_created_order() {
        String customerId = "CUS-" + UUID.randomUUID();

        var response = http.postForEntity(
                "/api/orders",
                Map.of("customerId", customerId),
                JsonNode.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.ACCEPTED);
        assertThat(response.getBody()).isNotNull();

        String id = response.getBody()
                .path("orderId").asText();
        long expectedVersion = response.getBody()
                .path("expectedVersion").asLong();

        await()
                .atMost(Duration.ofSeconds(15))
                .pollInterval(Duration.ofMillis(200))
                .untilAsserted(() -> {
                    var view = http.getForEntity(
                            "/api/order-views/{id}",
                            JsonNode.class,
                            id);

                    assertThat(view.getStatusCode())
                            .isEqualTo(HttpStatus.OK);
                    assertThat(view.getBody()).isNotNull();
                    assertThat(view.getBody()
                            .path("orderId").asText())
                            .isEqualTo(id);
                    assertThat(view.getBody()
                            .path("customerId").asText())
                            .isEqualTo(customerId);
                    assertThat(view.getBody()
                            .path("sourceVersion").asLong())
                            .isEqualTo(expectedVersion);
                    assertThat(view.getBody()
                            .path("state").asText())
                            .isEqualTo("PLACED");
                });
    }
}
~~~

**Đây là test skeleton theo REST contract giả định**: các source ở mục 7–8 chỉ gồm Java API và JPA, **chưa triển khai controllers**. Khi dùng thực tế phải tạo HTTP endpoints, security, JSON schema và datasource phù hợp. Nếu GET trong trạng thái pending trả HTTP 404 hoặc 202, Awaitility sẽ thử lại assertion; cần quyết định status nào được phép chờ và status nào phải fail-fast.

**Cẩn trọng:** HTTP connect/read timeout của từng GET phải được cấu hình riêng; `atMost(15s)` không tự bảo đảm một network call đang block bị hủy chính xác lúc deadline.

## 18. Kiểm thử rollback: absence không chứng minh tất cả

Tình huống:

~~~text
BEGIN T1
    INSERT order
    publish OrderPlaced
    một bước sau đó ném exception
ROLLBACK T1
~~~

Với listener `AFTER_COMMIT`, projection không nên được tạo cho transaction rollback. Tuy nhiên, một test thấy `PublishedEvents` chứa `OrderPlaced` **không** mâu thuẫn với rollback: event đã được publish trước khi T1 bị hủy.

### Tạo rollback bằng transaction thật

Trích đoạn trong integration test đã inject `OrderCommands` và `TransactionTemplate`:

~~~java
@Autowired
TransactionTemplate transactions;

@Test
void rolls_back_order_after_event_publication() {
    UUID id = transactions.execute(status -> {
        UUID created = orders.place("CUS-ROLLBACK");
        status.setRollbackOnly();
        return created;
    });

    assertThat(id).isNotNull();

    // Bổ sung public query của orders hoặc fixture database
    // để xác nhận row đã rollback.
}
~~~

Đây chỉ là **trích đoạn kích hoạt rollback**, chưa đủ là test hoàn chỉnh bảo đảm consumer không tạo projection. Để có bằng chứng phù hợp:

1. Xác nhận transaction nguồn **thật sự rollback**.
2. Xác nhận listener dùng `AFTER_COMMIT` và fallback policy như mong đợi.
3. Kiểm soát/quan sát dispatch lifecycle hoặc publication state theo thiết kế.
4. Không khẳng định “sẽ không có row về sau” chỉ dựa trên một lần đọc âm tức thời.

### Bẫy until(!condition)

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> orderViews.find(id).isEmpty());
~~~

Phép thử này có thể pass **ngay lập tức** trước khi consumer kịp làm gì, kể cả khi một listener bị cấu hình sai sẽ ghi projection sau đó.

Nếu contract chỉ cần chứng minh “projection không xuất hiện trong một cửa sổ”, Awaitility có thể dùng `during(Duration)` theo version hỗ trợ, nhưng một cửa sổ hữu hạn **không tương đương** chứng minh “không bao giờ”. Với rollback, kết hợp transaction semantics/controlled executor/registry mới có bằng chứng mạnh.

## 19. Event publication registry, retry và độ bền cuối cùng

Spring Modulith hỗ trợ **event publication registry** và adapter lưu trữ tương ứng. Với cấu hình phù hợp, publications có thể được theo dõi và phục hồi. Nhưng cần phân biệt:

| Tín hiệu | Nó chứng minh | Nó không chứng minh |
| --- | --- | --- |
| `PublishedEvents` ghi nhận event | Producer đã publish | Consumer đã commit projection |
| Publication pending | Có publication chưa được đánh dấu xử lý xong theo registry | Business chắc chắn đã thất bại |
| Publication completed | Listener xử lý xong theo semantics registry | Projection đúng payload/version nếu listener có bug |
| Projection đạt revision mong muốn | Read model đã hội tụ cho snapshot được kiểm tra | Publication sống qua restart |
| External provider receipt | Bước ngoài được xác nhận theo contract | Mọi internal projection đều đúng |

### Test phục hồi khi đó là cam kết

1. Dùng adapter registry persistent và database/hạ tầng thích hợp.
2. Cố ý làm consumer fail sau producer commit.
3. Xác nhận publication pending theo API của adapter.
4. Gỡ lỗi, resubmit/restart theo **cơ chế được hỗ trợ của phiên bản dự án**.
5. Await projection đạt revision/state mong muốn.
6. Xác minh handler idempotent và publication hoàn tất theo policy.

Không giả định `@ApplicationModuleListener` tự retry vô hạn, không giả định tất cả adapter dùng một bảng/tên API và không suy ra exactly-once delivery từ việc projection cuối cùng đúng.

## 20. Testcontainers khi visibility/isolation thuộc rủi ro

H2 giúp thử nhanh ví dụ. Tuy nhiên PostgreSQL/MySQL có khác biệt về isolation, unique constraint, SQL dialect và locking. Nếu eventual consistency assertion fail vì transaction visibility hoặc out-of-order updates, cần test với database production-like.

Khung dùng PostgreSQL Testcontainers:

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
class OrderProjectionPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Inject OrderCommands và OrderViews.
    // Dùng cùng oracle id + sourceVersion + state như mục 10.
}
~~~

**Đây là khung cấu hình**, chưa có test method. Cần Testcontainers Jupiter/PostgreSQL, Spring Boot Testcontainers, JDBC driver và Docker/container runtime. `@ServiceConnection` được Spring Boot hỗ trợ từ 3.1, phải dùng version tương thích.

Nếu production dùng Flyway/Liquibase, integration test quan trọng nên chạy migration thật thay vì chỉ `hibernate.ddl-auto=create-drop`. Test event replay/out-of-order phải chạy concurrent transaction với database thật khi atomicity là mệnh đề.

### Không trộn container startup với thời gian hội tụ

- **Container readiness:** DB đã start và sẵn sàng nhận kết nối.
- **Context bootstrap:** Spring tạo entity manager, repositories, listeners.
- **Projection convergence:** Từ lệnh/commit đến khi projection đạt version mong đợi.

Ba khoảng này khác nhau. Tăng `Awaitility.atMost` để che Docker image pull, migration lỗi hoặc container lifecycle không hợp lệ là sửa sai tầng.

### TestContext cache và container lifecycle

Spring TestContext cache có thể giữ application context giữa các test class; Testcontainers có vòng đời container riêng. Nếu context còn được cache nhưng container cũ đã dừng, query sẽ fail. Đừng xem đó là “eventual consistency chậm”; cần thiết kế lifecycle theo mô hình tương thích.

## 21. Khi nào dùng @ApplicationModuleTest và khi nào dùng full integration?

| Bằng chứng | Test type thích hợp | Quan sát cần có |
| --- | --- | --- |
| Domain logic của orders | Unit test | Giá trị/exception đồng bộ |
| Producer phát event đúng | `@ApplicationModuleTest` + `PublishedEvents` | Type, payload, version |
| Read model query mapping đúng | Repository/slice test | `OrderViewEntity → OrderView` |
| Consumer tiếp nhận event và cập nhật projection | Cross-module integration | Snapshot sau commit |
| Projection xử lý out-of-order/replay | Consumer reliability integration | Version không lùi, no duplicate effect |
| PostgreSQL upsert/locking | Testcontainers integration | Atomicity ở DB production-like |
| HTTP client đọc eventual projection | `@SpringBootTest(RANDOM_PORT)` | API contract, polling theo ID/version |
| Module không import implementation nội bộ | `ApplicationModules.verify()` | Dependency graph hợp lệ |
| Publication hồi phục qua restart | Registry/recovery integration | Pending được phục hồi đúng policy |

### Một lưu ý về bootstrap mode

`@ApplicationModuleTest` mặc định chỉ bootstrap phạm vi module liên quan; có các mode như `STANDALONE`, `DIRECT_DEPENDENCIES`, `ALL_DEPENDENCIES`. **Không mặc định nghĩ module consumer được nạp** khi đặt test trong producer: chiều dependency tĩnh của event listener thường là `orderviews → orders`, không phải `orders → orderviews`.

Nếu mục đích là kiểm tra cả producer và projection từ entry point ứng dụng, `@SpringBootTest(webEnvironment = NONE)` là lựa chọn rõ ràng. Một module test trong `orderviews` có thể dùng dependency mode phù hợp nếu muốn kiểm tra consumer với producer, nhưng phải xác minh module graph thực tế.

## 22. Architectural verification: giữ public event API

Consumer `orderviews` được phép import event công khai:

~~~java
import com.example.shop.orders.OrderPlaced;
~~~

Nhưng không nên import JPA implementation của producer:

~~~java
// Vi phạm ranh giới module mặc định:
import com.example.shop.orders.internal.persistence.OrderEntity;
~~~

Bài kiểm thử kiến trúc:

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void application_modules_respect_dependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm tra các quy tắc kiến trúc Spring Modulith, như vòng phụ thuộc và truy cập ngoài public API. Nó **không** kiểm tra eventual consistency hay listener commit. Cần chạy song song **architecture test** và **event integration test**.

Nếu `orderviews` chỉ được phụ thuộc `orders`, có thể khai báo:

~~~java
@ApplicationModule(allowedDependencies = "orders")
package com.example.shop.orderviews;

import org.springframework.modulith.ApplicationModule;
~~~

Whitelist phản ánh kiến trúc được review; không mở rộng bừa để test xanh. Nếu event nằm trong một named interface `orders::events`, whitelist phải theo tên interface đã khai báo thực tế.

## 23. CI quality gate cho read model eventually consistent

~~~mermaid
flowchart LR
    PR["Pull request"] --> A["Unit + architecture"]
    A --> P["Publisher module test"]
    P --> C["Projection consumer integration"]
    C --> R["Replay / ordering / retry tests"]
    R --> DB["Production-like DB tests"]
    DB --> E["Critical HTTP E2E"]
    E --> G{"Mọi gate bắt buộc đạt?"}
    G -- "Có" --> OK["Merge/release"]
    G -- "Không" --> FIX["Sửa lỗi hoặc hồi quy"]
~~~

| Gate | Rủi ro bảo vệ | Tần suất gợi ý |
| --- | --- | --- |
| `ApplicationModules.verify()` | Phụ thuộc API/package sai | Mọi PR, bắt buộc |
| Producer module + `PublishedEvents` | Event thiếu/sai ID, payload, version | Mọi PR liên quan orders |
| Projection integration | Listener không chạy, T2 rollback, mapping sai | Mọi PR liên quan read model |
| Contract/version test | Version/snapshot semantics đổi | Mọi PR ảnh hưởng event contract |
| Reliability | Duplicate, out-of-order, retry, recovery | Theo rủi ro, đặc biệt trước release |
| PostgreSQL Testcontainers | Atomic upsert/isolation/constraint | Khi DB semantics quan trọng |
| HTTP E2E | POST rồi GET read model cuối | Một số hành trình công khai |

### Kỷ luật về timeout

- Đặt deadline hữu hạn theo **độ trễ đã đo** và hợp đồng, không theo một con số sao chép.
- Poll theo ID/version để tránh false positive.
- Tách container/context startup khỏi thời gian hội tụ.
- Theo dõi timeout rate và time-to-version p50/p95/p99 nếu đủ dữ liệu.
- Điều tra lỗi schema, missed event, retry hay stale snapshot **trước khi** tăng timeout.
- Không dùng `Thread.sleep` hàng loạt khiến suite chậm.
- Không tắt test flaky vô thời hạn; xác định đó là bug race hay hạ tầng chậm.
- Không coi một test eventual success là đủ để chứng minh durable recovery.

### Negative controls có giá trị

Trong một nhánh thực hành:

1. Bỏ dòng publish `OrderPlaced` → producer test phải đỏ.
2. Bỏ `@ApplicationModuleListener` → producer test có thể vẫn xanh, projection integration phải đỏ.
3. Đổi `sourceVersion` trong event thành sai số → assertion version phải đỏ.
4. Đổi `customerId` projection thành giá trị khác → assertion payload phải đỏ.
5. Thêm import từ `orderviews` tới `orders.internal` → architecture test phải đỏ.

Các thí nghiệm này cho thấy từng test bảo vệ một **mệnh đề độc lập**, không chỉ “test suite có nhiều class”.

## 24. Troubleshooting eventual consistency assertion

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `PublishedEvents` xanh, projection mãi rỗng | Listener không đăng ký hoặc transaction T2 lỗi | Context, annotation, log listener và DB |
| Projection hiện sau lần 2 nhưng test fail lần 1 | Assert tức thời dù contract eventual | Await đúng condition |
| Awaitility mãi đọc empty dù DB đã có | Snapshot lấy trước polling, transaction/cache cũ | Query lại mỗi lần, transaction đọc ngắn |
| Test pass nhờ dữ liệu cũ | Query `countAll() > 0` hoặc ID fixture cố định | Correlation ID duy nhất |
| Projection tồn tại nhưng revision thấp | Consumer chưa bắt kịp hoặc lost event | Assert version, xem publication state |
| Revision cao nhưng state bất hợp lệ | Out-of-order hoặc mapping bug | Version conditional update + business assertion |
| Listener đã gọi nhưng read model chưa thấy | T2 chưa commit hoặc rollback | Query/transaction/exception |
| Timeout chỉ trên CI | Executor/DB contention, stale read hoặc flaky fixture | Logs, p95/p99, pool metrics |
| Mọi HTTP 500 bị biến thành timeout | Retry exceptions quá rộng | Phân loại terminal/transient |
| Event trùng gây unique violation | Check-then-insert race | DB constraint + upsert/idempotency |
| Event cũ ghi đè state mới | Không kiểm tra revision atomically | CAS/versioned upsert |
| Transaction test có `@Transactional` | Không có producer commit/AFTER_COMMIT | Loại outer rollback khỏi consumer test |
| Registry completed nhưng projection sai payload | Listener thành công về kỹ thuật nhưng logic sai | Assert snapshot đầy đủ |
| PostgreSQL khác H2 | Locking/isolation/SQL khác | Testcontainers production-like |
| Integration xanh nhưng architecture đỏ | Consumer import `orders.internal` | Sửa ranh giới API |

**Hướng chẩn đoán theo thứ tự:** Producer commit → event publish → listener được nạp/chạy → consumer transaction commit → query đúng ID → sourceVersion/state → cache/isolation/replica → registry/retry → môi trường và deadline.

Đừng kết luận “eventual consistency nghĩa là cứ đợi lâu hơn” khi có bằng chứng query sai, event mất hoặc trạng thái đã FAILED terminal.

## 25. Bài thực hành

### Bài A — Chuyển assertion tức thời thành eventual assertion

Cho:

~~~java
UUID id = orders.place("CUS-A");
assertThat(orderViews.find(id)).isPresent();
~~~

Hãy chuyển sang Awaitility với `untilAsserted`, `atMost` và `pollInterval`. Bổ sung assertion về `orderId`, `sourceVersion=1` và `state=PLACED`.

**Tiêu chí đạt:** Test phải đỏ nếu listener bị bỏ annotation, version sai hoặc customerId sai; không chỉ chờ một row bất kỳ.

### Bài B — Bắt false positive do dữ liệu test cũ

Tạo hai đơn có `orderId` khác nhau. Viết một test sai dùng `countAll() > 0` và một test đúng dùng `find(secondOrderId)`. Giải thích vì sao test sai có thể pass trước khi projection của đơn thứ hai xuất hiện.

### Bài C — Chứng minh việc poll một snapshot cũ là sai

Gọi `OrderViews.find(id)` đúng một lần trước Awaitility rồi giữ `Optional` trong biến. Cho consumer cập nhật projection ở một thread khác; kiểm tra predicate trên biến cũ không bao giờ đổi. Sửa bằng việc gọi `find(id)` bên trong mỗi lần poll.

### Bài D — Bắt phiên bản read model bị trễ

Thiết kế một event cập nhật revision 2 và public API trả `sourceVersion`. Cho revision 1 đã tồn tại, tạm chặn listener revision 2 bằng controlled port/latch. Kiểm tra assertion chỉ `isPresent()` sẽ xanh sai, còn assertion `version>=2` chưa xanh. Release listener rồi xác nhận điều kiện đạt.

### Bài E — Event đến sai thứ tự

Tạo event snapshot revision 2 rồi phát lại revision 1. Kiểm tra projection không lùi version/state. Viết database conditional update hoặc optimistic-locking policy và test concurrent delivery.

### Bài F — Negative assertion sau rollback

Dùng `TransactionTemplate` để tạo order, publish event rồi rollback. Giải thích vì sao `await().until(find(id).isEmpty())` có thể pass giả; bổ sung kiểm tra rollback nguồn và phase `AFTER_COMMIT`, điều khiển dispatch khi cần.

### Bài G — Xử lý consumer failure

Cho listener lỗi một lần. Nếu dự án cấu hình durable event publication registry, quan sát pending, resubmit và cuối cùng projection đúng version sau khi lỗi được gỡ. Tách business `FAILED` với timeout của test.

### Bài H — HTTP polling contract

Thiết kế `POST /orders` trả `orderId` và `expectedVersion`, `GET /order-views/{id}` trả trạng thái. Viết E2E theo ID/version, xử lý trạng thái pending và lỗi 401/403/404/429 rõ ràng. Không ignore mọi response rồi chờ một deadline chung.

### Bài I — Bảo vệ ranh giới module

Chạy `ApplicationModules.verify()`. Thử để consumer import `orders.internal.persistence.OrderEntity`; xác nhận architecture test đỏ. Sửa bằng public event `OrderPlaced` và public query API của `orderviews`.

### Câu hỏi tự đánh giá

1. Vì sao một read model `Optional.empty()` ngay sau POST chưa chắc là bug?
2. `PublishedEvents` khác assertion projection đã commit như thế nào?
3. Tại sao `Thread.sleep(...)` làm test chậm và flaky?
4. Vì sao `findAll().size() > 0` có thể tạo false positive?
5. Khi nào cần assert cả ID, version, state và payload?
6. `sourceVersion >= 2` có đủ chứng minh state chính xác của revision 2 không?
7. Vì sao transaction dài hoặc cache cũ làm polling không thấy cập nhật?
8. Vì sao `until(find(id).isEmpty())` chưa phải kiểm tra âm đáng tin?
9. Upsert chỉ dựa vào version phù hợp khi event là snapshot hay delta?
10. Khi nào cần test persistent registry và Testcontainers?
11. Vì sao hết timeout không đồng nghĩa workflow `FAILED`?
12. Tại sao integration test xanh vẫn phải có `ApplicationModules.verify()`?

## 26. Checklist trước khi phê duyệt assertion eventual consistency

- [ ] Đã xác định nguồn dữ liệu authoritative và read model nào có thể lag.
- [ ] Contract nói rõ đọc tức thời hay eventual, không lẫn hai kiểu consistency.
- [ ] Completion criterion là kết quả nghiệp vụ quan sát được, không chỉ listener invoked.
- [ ] Assertion dùng đúng correlation ID của request hiện tại.
- [ ] Có kiểm tra source version/revision khi read model có thể đã tồn tại từ trước.
- [ ] Có kiểm tra state và payload đủ mạnh để bắt sai mapping/ngữ nghĩa.
- [ ] Mỗi lần poll thực sự query một snapshot mới.
- [ ] Test không giữ outer transaction/snapshot cũ không cần thiết.
- [ ] Deadline hữu hạn, poll interval hợp lý, không dùng `Thread.sleep` đoán.
- [ ] Không ignore mọi exception HTTP/database một cách mù quáng.
- [ ] Có phân biệt trạng thái terminal FAILED với timeout/unknown.
- [ ] Negative assertion không pass ngay trước khi consumer bắt đầu.
- [ ] Event duplicate/out-of-order có idempotency/version policy nếu cần.
- [ ] Database constraint và atomicity được test trên engine phù hợp với production.
- [ ] `@ApplicationModuleTest` + `PublishedEvents` chỉ được dùng làm bằng chứng producer.
- [ ] Consumer integration test có listener thật và transaction commit thật.
- [ ] Durable/recovery chỉ kết luận khi persistent registry và restart đã được kiểm thử.
- [ ] Public API/dependency được kiểm tra bằng `ApplicationModules.verify()`.
- [ ] Quality gate CI thực sự chạy các bài test quan trọng và giữ log chẩn đoán.
- [ ] Có negative control khiến test đỏ khi publisher, listener hoặc version bị phá.

## 27. Ghi nhớ

**Eventual consistency trong assertion** không phải chờ “thật lâu” cho tới khi kết quả xuất hiện. Cần biết **dữ liệu nào có thể trễ**, **phiên bản nào được mong đợi**, **kết quả nào được coi là hoàn thành**, và **điểm quan sát có thực sự đọc dữ liệu mới hay không**. Awaitility giúp chờ một điều kiện với deadline hữu hạn; nó không sửa được event mất, stale snapshot, version ghi lùi hoặc lỗi transaction.

Trong Spring Modulith, `@ApplicationModuleTest` và `PublishedEvents` kiểm tra producer phát event; integration test với `@ApplicationModuleListener` và database kiểm tra projection hội tụ sau commit; reliability test kiểm tra duplicate, out-of-order, retry và restart. Kết hợp `ApplicationModules.verify()` và quality gate CI để ngăn phụ thuộc sai lẫn hồi quy của read model bất đồng bộ.
