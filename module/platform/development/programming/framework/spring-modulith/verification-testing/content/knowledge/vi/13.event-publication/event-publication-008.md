# Kiểm tra event không được publish khi transaction rollback

## 1. Làm rõ điều cần chứng minh

Trong ứng dụng Spring Modulith, yêu cầu “event không được publish khi transaction rollback” thường có nghĩa nghiệp vụ sau:

> Nếu transaction tạo đơn hàng thất bại, các module downstream không được xem đơn hàng đó là đã tạo thành công và không được thực hiện side effect dành riêng cho đơn hàng đã commit.

Để kiểm thử chính xác, phải phân biệt **ba sự kiện kỹ thuật**:

1. Mã nghiệp vụ **gọi** `ApplicationEventPublisher.publishEvent(event)`.
2. Một `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc `@ApplicationModuleListener` **được phép xử lý sau commit**.
3. **Event Publication Registry** lưu publication bền vững để theo dõi việc giao event tới từng transactional listener.

**Điểm quan trọng:** `publishEvent(...)` được gọi **ngay khi code chạy**, kể cả ở giữa transaction. Spring không thu hồi một lời gọi Java đã diễn ra khi transaction rollback. Vì thế một test với `PublishedEvents` vẫn có thể quan sát event đã phát dù transaction nguồn thất bại. Điều Spring có thể bảo đảm theo cơ chế transactional listener là: listener `AFTER_COMMIT` **không chạy** nếu transaction nguồn rollback. Với registry lưu publication trong cùng transaction nguồn, bản ghi publication tương ứng cũng **không được commit**.

| Câu hỏi kiểm thử | Kết quả khi publish trong transaction rồi rollback |
| --- | --- |
| Có lời gọi `publishEvent` không? | **Có**, nếu code đã đi qua lời gọi ấy. |
| `PublishedEvents` có thể ghi nhận event không? | **Có**; nó quan sát việc phát, không phải kết quả commit. |
| `@EventListener` đồng bộ mặc định có thể chạy không? | **Có**, ngay khi event được phân phối. |
| `@TransactionalEventListener(AFTER_COMMIT)` có chạy không? | **Không** khi transaction rollback. |
| `@TransactionalEventListener(AFTER_ROLLBACK)` có chạy không? | **Có**, nếu event được phát trong transaction và listener hợp lệ. |
| Dữ liệu JPA ghi trong transaction nguồn còn không? | **Không**, nếu rollback thành công và không có transaction riêng. |
| Publication được registry ghi cùng transaction nguồn còn bền vững không? | **Không** sau rollback, với cấu hình persistence/transaction đúng. |

Bài thuộc chương **Event publication** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**. Các test dưới đây giúp kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, hành vi `@ApplicationModuleTest`, transaction, cơ sở dữ liệu và tích hợp quality gate CI nhằm ngăn phụ thuộc sai và hồi quy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Diễn đạt yêu cầu rollback dưới dạng **assertion có thể kiểm chứng**, tránh nhầm giữa phát event và xử lý event.
- Viết test rollback thực sự xảy ra với `TransactionTemplate` hoặc service `@Transactional`.
- Xác nhận listener `AFTER_COMMIT` không xử lý, còn listener `AFTER_ROLLBACK` được gọi.
- Dùng `PublishedEvents` đúng ngữ nghĩa và tránh assertion “không có event” sai.
- Kết hợp trạng thái database và Event Publication Registry để kiểm tra side effect bền vững.
- Phân biệt test module nguồn, test module nhận, test kiến trúc và integration test.

## 2. Các kiểu listener phản ứng thế nào với rollback?

`ApplicationEventPublisher` là cơ chế event của Spring Framework. Một `record` hoặc POJO có thể được phát mà không cần kế thừa `ApplicationEvent`. Transaction gắn với service và `PlatformTransactionManager`; lời gọi `publishEvent` **không tự tạo hoặc kết thúc transaction**.

| Listener | Thời điểm trong cấu hình mặc định | Khi transaction nguồn rollback |
| --- | --- | --- |
| `@EventListener` | Đồng bộ tại lúc phát. | Đã được gọi; side effect ngoài transaction có thể đã xảy ra. |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Trước khi commit. | Không được gọi khi transaction được quyết định rollback trước pha commit; nhưng nếu đã chạy rồi commit thất bại về sau, side effect ngoài hệ thống có thể vẫn xảy ra. |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit thành công. | Không được gọi. |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Sau rollback. | Được gọi. |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Sau khi kết thúc transaction. | Được gọi, kể cả rollback. |
| `@ApplicationModuleListener` | Spring Modulith kết hợp transactional event handling, async và transaction mới. | Không được kích hoạt qua đường `AFTER_COMMIT` nếu nguồn rollback. |

`@TransactionalEventListener` mặc định có `phase = AFTER_COMMIT` và `fallbackExecution = false`. Nếu phát event ngoài transaction, listener mặc định **không được kích hoạt**, dù lần giao có xảy ra trước hay sau một transaction khác. Bật `fallbackExecution = true` làm listener chạy khi không có transaction; đây là quyết định nghiệp vụ, không phải mẹo để sửa test rollback.

### Minh họa chuỗi thời gian

~~~mermaid
sequenceDiagram
    participant API as Client
    participant Order as orders.OrderService
    participant DB as Database
    participant Pub as ApplicationEventPublisher
    participant Regular as @EventListener
    participant Commit as AFTER_COMMIT
    participant Rollback as AFTER_ROLLBACK

    API->>Order: placeAndFail(orderId)
    Note over Order,DB: Bắt đầu transaction nguồn
    Order->>DB: INSERT order
    Order->>Pub: publishEvent(OrderPlaced)
    Pub->>Regular: Xử lý đồng bộ
    Note over Pub,Commit: Đăng ký callback theo pha transaction
    Order-->>API: Ném RuntimeException
    API->>DB: Transaction ROLLBACK
    DB-->>Rollback: Callback AFTER_ROLLBACK
    Note over Commit: Không gọi AFTER_COMMIT
    Note over DB: Order INSERT không được commit
~~~

Sơ đồ giản lược proxy/transaction manager. Lời gọi `publishEvent` đã xảy ra, nhưng listener chỉ dành cho dữ liệu commit thành công không được chạy.

## 3. Ví dụ module orders và inventory

Giả sử ứng dụng Spring Boot có lớp `ShopApplication` ở `com.example.shop`. Với cách phát hiện package mặc định, `orders` và `inventory` là hai application module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   ├── events
│   │   ├── OrderPlaced.java
│   │   └── package-info.java
│   └── internal
│       ├── OrderEntity.java
│       └── OrderRepository.java
└── inventory
    ├── StockReservationListener.java
    └── package-info.java
~~~

### 3.1. Event là hợp đồng công khai

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(UUID eventId, UUID orderId, Instant occurredAt) {
    public OrderPlaced {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(occurredAt);
    }
}
~~~

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

`eventId` xác định sự kiện nghiệp vụ để consumer xử lý lặp an toàn; `orderId` định danh đơn hàng. Payload không chứa `OrderEntity` hay repository nội bộ của module nguồn.

### 3.2. Entity và repository mẫu

File `orders/internal/OrderEntity.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.util.UUID;

@Entity
public class OrderEntity {

    @Id
    private UUID id;

    protected OrderEntity() {}

    public OrderEntity(UUID id) {
        this.id = id;
    }
}
~~~

File `orders/internal/OrderRepository.java`:

~~~java
package com.example.shop.orders.internal;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.UUID;

public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {}
~~~

Hai kiểu này thuộc **chi tiết triển khai của module orders**, dù được khai báo `public` ở cấp Java để code trong package khác của cùng module sử dụng. Không được để `inventory` import trực tiếp các kiểu persistence này.

### 3.3. Service phát event trước khi gặp lỗi

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(OrderRepository orders, ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void place(UUID orderId) {
        persistAndPublish(orderId);
    }

    @Transactional
    public void placeAndFail(UUID orderId) {
        persistAndPublish(orderId);
        throw new IllegalStateException("Simulated business failure");
    }

    private void persistAndPublish(UUID orderId) {
        orders.save(new OrderEntity(orderId));
        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(), orderId, Instant.now()));
    }
}
~~~

Ví dụ này chủ động ném `IllegalStateException` **sau** lời gọi `publishEvent`; vì đây là unchecked exception, quy tắc rollback mặc định của `@Transactional` sẽ rollback transaction. Hai phương thức public được gọi qua Spring-managed bean để transaction proxy có hiệu lực.

Trong hệ thống thật, code cần xử lý validation, unique constraint, idempotency và trạng thái đơn hàng. Đoạn code dùng lỗi giả lập để minh họa chính xác tình huống **đã publish nhưng chưa commit**.

### 3.4. Listener nhận event sau commit

File `inventory/StockReservationListener.java`:

~~~java
package com.example.shop.inventory;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class StockReservationListener {

    private final StockReservationService reservations;

    StockReservationListener(StockReservationService reservations) {
        this.reservations = reservations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        reservations.reserveFor(event.orderId(), event.eventId());
    }
}
~~~

`StockReservationService` là bean nội bộ của `inventory` cần triển khai trong ứng dụng thực. `@ApplicationModuleListener` có ngữ nghĩa xử lý sau commit, bất đồng bộ và transaction riêng. Khi `placeAndFail` rollback, listener này **không được kích hoạt** qua luồng `AFTER_COMMIT`.

File `inventory/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.example.shop.inventory;
~~~

Module `inventory` chỉ cần kiểu event công khai. Điều này cho phép kiểm chứng ranh giới bằng `ApplicationModules` độc lập với kết quả transaction.

## 4. Module test: rollback không gọi AFTER_COMMIT

Để kiểm tra chính xác hành vi transaction trong phạm vi module, tạo một **test-only probe** với listener thường, listener sau commit và listener sau rollback. Probe này chạy đồng bộ theo mặc định để test có assertion quyết định, không dựa vào timeout.

Đặt lớp test ở package `com.example.shop.orders`, nơi Spring Modulith nhận diện module cần test. Ví dụ giả định có Spring Data JPA, test datasource, transaction manager và dependency `spring-modulith-starter-test`.

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ApplicationModuleTest
@Import(OrderRollbackModuleTests.ProbeConfig.class)
class OrderRollbackModuleTests {

    @Autowired OrderService orders;
    @Autowired OrderRepository repository;
    @Autowired ListenerProbe probe;

    @BeforeEach
    void reset() {
        probe.reset();
    }

    @Test
    void rollbackDoesNotDeliverToAfterCommitListener(
            PublishedEvents events) {

        UUID orderId = UUID.randomUUID();

        assertThatThrownBy(() -> orders.placeAndFail(orderId))
                .isInstanceOf(IllegalStateException.class);

        // Dữ liệu INSERT trong transaction nguồn đã rollback.
        assertThat(repository.existsById(orderId)).isFalse();

        // Listener đồng bộ đã nhận event khi publishEvent được gọi.
        assertThat(probe.immediate.get()).isEqualTo(1);

        // AFTER_COMMIT không được thực thi.
        assertThat(probe.afterCommit.get()).isZero();

        // Rollback callback thực sự được gọi.
        assertThat(probe.afterRollback.get()).isEqualTo(1);

        // Đây là kết quả ĐÚNG: publishEvent đã được gọi trước rollback.
        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .hasSize(1);
    }

    @Test
    void successfulCommitDeliversToAfterCommitListener(
            PublishedEvents events) {

        UUID orderId = UUID.randomUUID();
        orders.place(orderId);

        assertThat(repository.existsById(orderId)).isTrue();
        assertThat(probe.immediate.get()).isEqualTo(1);
        assertThat(probe.afterCommit.get()).isEqualTo(1);
        assertThat(probe.afterRollback.get()).isZero();
        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .hasSize(1);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ProbeConfig {
        @Bean
        ListenerProbe listenerProbe() {
            return new ListenerProbe();
        }
    }

    static class ListenerProbe {
        final AtomicInteger immediate = new AtomicInteger();
        final AtomicInteger afterCommit = new AtomicInteger();
        final AtomicInteger afterRollback = new AtomicInteger();

        void reset() {
            immediate.set(0);
            afterCommit.set(0);
            afterRollback.set(0);
        }

        @EventListener
        public void onEvent(OrderPlaced event) {
            immediate.incrementAndGet();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void committed(OrderPlaced event) {
            afterCommit.incrementAndGet();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderPlaced event) {
            afterRollback.incrementAndGet();
        }
    }
}
~~~

### Vì sao test này có giá trị?

- **Nhánh rollback:** Test chứng minh `placeAndFail` có thực sự phát event trước khi transaction thất bại, nhưng không tạo dữ liệu đơn hàng đã commit và không kích hoạt `AFTER_COMMIT`.
- **Nhánh commit:** Test đối chứng xác nhận probe `AFTER_COMMIT` **có thể chạy** khi nguồn commit. Nếu chỉ kiểm tra `afterCommit == 0` ở nhánh rollback, một listener không được đăng ký cũng cho kết quả zero, khiến test dương tính giả.
- **Listener đồng bộ:** Số đếm `immediate == 1` chứng minh `@EventListener` không mặc nhiên được bảo vệ bởi transaction rollback.
- **PublishedEvents:** Assertion `hasSize(1)` ở nhánh rollback là có chủ đích. Nó phân biệt **đã gọi publish** với **đã giao sau commit**.

Không gắn `@Transactional` lên lớp test này. Nếu Spring Test mở một transaction bao ngoài rồi rollback ở cuối test, service có thể tham gia transaction test thay vì commit độc lập; assertion sau khi service trả về sẽ không phản ánh các pha thực tế như mong đợi.

Vì probe được đăng ký trong test context, các test nên tránh chia sẻ probe giữa các test chạy song song. Fixture dùng `UUID.randomUUID()` để các truy vấn database không đụng dữ liệu test khác. Trong dự án thật cần cấu hình JPA schema/test database và cô lập fixture theo chiến lược test chung.

## 5. Kiểm tra trực tiếp bằng TransactionTemplate

Nếu chỉ muốn học cơ chế rollback mà không xây cả `OrderService`, có thể chủ động điều khiển transaction từ test:

~~~java
@ApplicationModuleTest
class TransactionPhaseTests {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired PlatformTransactionManager txManager;
    @Autowired ListenerProbe probe;

    @Test
    void afterCommitDoesNotRunWhenRollingBack(
            PublishedEvents publishedEvents) {
        UUID id = UUID.randomUUID();
        var tx = new TransactionTemplate(txManager);

        tx.executeWithoutResult(status -> {
            publisher.publishEvent(
                    new OrderPlaced(UUID.randomUUID(), id, Instant.now()));
            status.setRollbackOnly();
        });

        assertThat(probe.afterCommit.get()).isZero();
        assertThat(probe.afterRollback.get()).isEqualTo(1);
        assertThat(publishedEvents.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, id))
                .hasSize(1);
    }
}
~~~

Đây là **khung test minh họa**, cần import bean `ListenerProbe` như phần trước và các import Java/Spring/AssertJ tương ứng. `TransactionTemplate` được gọi trong test **không có transaction bao ngoài**, vì propagation mặc định là `REQUIRED`. Nếu đã có transaction test, `TransactionTemplate` có thể tham gia transaction ấy và không tạo một pha rollback độc lập.

`TransactionTemplate` phù hợp khi cần test cả commit và rollback có kiểm soát:

~~~java
var tx = new TransactionTemplate(txManager);

tx.executeWithoutResult(status -> {
    publisher.publishEvent(event);
    status.setRollbackOnly();  // Rollback có chủ đích.
});

// Callback AFTER_ROLLBACK (đồng bộ) đã hoàn tất.
// Callback AFTER_COMMIT không chạy.
~~~

Trong test thực tế, hãy có **nhánh đối chứng commit** để xác nhận listener được đăng ký và có thể xử lý khi transaction thành công.

### 5.1. Bẫy rollback do Spring Test

~~~java
@ApplicationModuleTest
@Transactional
class MisleadingTests {
    // Mỗi test có thể bị rollback sau khi test hoàn tất.
}
~~~

Khi Spring Test quản lý transaction của test, các callback `AFTER_COMMIT` có thể không bao giờ chạy do test tự rollback lúc kết thúc. Nếu mục tiêu là kiểm tra commit thật, dùng một test không `@Transactional` bao ngoài; hoặc sử dụng `TestTransaction.flagForCommit()` và `TestTransaction.end()` trong test được Spring quản lý transaction.

## 6. Đừng viết assertion “không có PublishedEvents” cho rollback muộn

Đây là một anti-pattern:

~~~java
assertThatThrownBy(() -> orders.placeAndFail(orderId))
        .isInstanceOf(IllegalStateException.class);

// Sai với code đã gọi publishEvent trước khi ném lỗi:
assertThat(events.ofType(OrderPlaced.class)
        .matching(OrderPlaced::orderId, orderId))
        .isEmpty();
~~~

Assertion rỗng chỉ đúng nếu **mã nguồn chưa từng gọi publish**. Ví dụ validation từ chối request **trước** lệnh phát:

~~~java
@Transactional
public void place(UUID id, boolean valid) {
    if (!valid) {
        throw new IllegalArgumentException("Invalid order");
    }

    repository.save(new OrderEntity(id));
    events.publishEvent(
            new OrderPlaced(UUID.randomUUID(), id, Instant.now()));
}
~~~

Với `valid=false`, `PublishedEvents` rỗng là đúng vì chương trình không đi đến call site. Nhưng khi một transaction có thể rollback **sau** lệnh phát, yêu cầu “không từng gọi publish” phải được giải quyết bằng thiết kế khác; nó không tự được bảo đảm bởi `@Transactional`.

Nếu nghiệp vụ yêu cầu “chỉ phân phối sự kiện sau commit”, hãy dùng `@TransactionalEventListener(AFTER_COMMIT)`, `@ApplicationModuleListener` hoặc hạ tầng outbox/registry phù hợp. Những cơ chế này giúp kiểm soát **việc phân phối/xử lý**, không viết lại lịch sử thực thi của lời gọi `publishEvent`.

## 7. Registry: không còn publication bền vững sau rollback

Spring Modulith Event Publication Registry theo dõi lần công bố tới **từng transactional listener** khi có cấu hình persistence tương ứng. Với một event và hai transactional listener hợp lệ, có thể có **hai publication**, mỗi publication cho một target. Khi event được phát trong transaction nguồn:

1. Registry ghi các publication tương ứng trong transaction đó.
2. Nếu transaction **commit**, các bản ghi publication có thể tồn tại bền vững để theo dõi processing/completion.
3. Nếu transaction **rollback**, những bản ghi ghi **cùng transaction** sẽ rollback; không còn publication bền vững của event đó.

Một test `PublishedEvents` pass không chứng minh registry đã lưu gì. Để kiểm tra tính bền vững, cần **integration test** có starter registry, datasource/transaction manager, schema phù hợp và listener thật trong application context.

### 7.1. Điều kiện tích hợp

Ví dụ dùng JDBC persistence cho registry:

~~~groovy
dependencies {
    implementation 'org.springframework.modulith:spring-modulith-starter-jdbc'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}
~~~

Đoạn Gradle minh họa, giả định đã có Spring Boot/JPA hoặc JDBC, database driver, quản lý phiên bản Spring Modulith, schema registry và transaction manager. Starter chỉ hỗ trợ hạ tầng; không tự tạo đủ mọi cấu hình database của ứng dụng.

### 7.2. Integration test rollback và commit đối chứng

Mẫu dưới đây dùng **test-only event** và một transactional listener cố tình ném exception **sau commit**. Nhờ listener thất bại, publication của nhánh commit còn ở trạng thái chưa hoàn tất để dễ quan sát. Phần rollback phải không để lại publication tương ứng.

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.events.core.EventPublicationRegistry;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(RegistryRollbackTests.FailingListenerConfig.class)
class RegistryRollbackTests {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired PlatformTransactionManager txManager;
    @Autowired EventPublicationRegistry registry;

    public record ProbeEvent(UUID eventId) {}

    @Test
    void rollbackLeavesNoDurablePublication() {
        UUID eventId = UUID.randomUUID();
        var tx = new TransactionTemplate(txManager);

        tx.executeWithoutResult(status -> {
            publisher.publishEvent(new ProbeEvent(eventId));
            status.setRollbackOnly();
        });

        assertThat(registry.findIncompletePublications())
                .noneMatch(publication ->
                        publication.getEvent() instanceof ProbeEvent event
                                && event.eventId().equals(eventId));
    }

    @Test
    void commitLeavesPublicationWhenListenerFails() {
        UUID eventId = UUID.randomUUID();
        var tx = new TransactionTemplate(txManager);

        try {
            tx.executeWithoutResult(status ->
                    publisher.publishEvent(new ProbeEvent(eventId)));
        } catch (IllegalStateException expected) {
            // Test listener cố tình ném lỗi sau commit.
            // Cách exception lan ra ngoài tùy transaction manager.
        }

        assertThat(registry.findIncompletePublications())
                .anyMatch(publication ->
                        publication.getEvent() instanceof ProbeEvent event
                                && event.eventId().equals(eventId));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FailingListenerConfig {
        @Bean
        FailingListener failingListener() {
            return new FailingListener();
        }
    }

    static class FailingListener {
        @TransactionalEventListener
        public void on(ProbeEvent event) {
            throw new IllegalStateException("Simulated downstream failure");
        }
    }
}
~~~

Đây là mẫu test tích hợp cần điều chỉnh theo phiên bản Spring Modulith và cấu hình persistence/serializer thực tế. Test đăng ký listener đồng bộ theo pha `AFTER_COMMIT`, không dùng `@ApplicationModuleListener` bất đồng bộ, để tránh race ở assertion. Với event được serialize trong registry, cần bảo đảm test record có thể round-trip bằng serializer đang cấu hình.

**Vì sao cần test đối chứng commit?** Nếu cấu hình registry bị thiếu hoặc listener không được đăng ký, test “rollback không còn publication” vẫn có thể pass vì chưa bao giờ có bản ghi nào. Nhánh commit có listener lỗi chứng minh registry thực sự nhìn thấy event và lưu publication tương ứng.

Nếu ứng dụng dùng completion mode `DELETE`, publication **đã hoàn tất** có thể bị xóa. Trong ví dụ, listener cố tình lỗi để nhánh commit vẫn có publication chưa hoàn tất; không dùng việc “không tìm thấy” làm bằng chứng thành công chung chung.

### 7.3. Nếu test có listener bất đồng bộ

`@ApplicationModuleListener` xử lý bất đồng bộ, nên một assertion lập tức sau `publishEvent` hoặc sau commit có thể chạy **trước khi listener bắt đầu/kết thúc**. Với trường hợp kiểm tra **không có side effect sau rollback**, một khoảng chờ hữu hạn chỉ là bằng chứng trong cửa sổ quan sát, không chứng minh vĩnh viễn listener sẽ không chạy. Kết hợp kiểm tra publication bền vững, callback đồng bộ trong test và dữ liệu downstream để có tín hiệu đáng tin cậy.

Nếu cần chờ kết quả thành công, dùng `Scenario` của Spring Modulith hoặc Awaitility với timeout hợp lý:

~~~java
await().atMost(Duration.ofSeconds(10))
       .untilAsserted(() ->
               assertThat(reservations.existsByOrderId(orderId))
                       .isTrue());
~~~

Đây chỉ là **đoạn assertion** khi đã khai báo Awaitility và bean/repository test tương ứng.

## 8. Điều gì xảy ra với @EventListener thông thường?

Giả sử một listener đồng bộ gửi yêu cầu HTTP:

~~~java
@EventListener
void on(OrderPlaced event) {
    shippingGateway.requestShipment(event.orderId());
}
~~~

Nếu `publishEvent` chạy giữa transaction rồi transaction rollback, request HTTP đã phát đi **không được hoàn nguyên** bởi rollback database. Ngay cả listener đồng bộ ghi database qua `REQUIRES_NEW` cũng có thể commit kết quả riêng trước khi transaction nguồn rollback.

Với side effect chỉ có ý nghĩa sau khi đơn hàng đã commit, hãy chọn cơ chế sau commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderPlaced event) {
    shippingGateway.requestShipment(event.orderId());
}
~~~

Điều này giảm nguy cơ tạo công việc downstream từ transaction thất bại. Nhưng nếu đã commit nguồn rồi listener lỗi hoặc tiến trình dừng, không thể đơn giản rollback dữ liệu nguồn trở lại. Cần xét registry/outbox, recovery và idempotency.

### Ghi dữ liệu sau commit cần transaction mới

Ở pha `AFTER_COMMIT`, tài nguyên transaction nguồn có thể còn gắn với thread dù commit đã hoàn tất. Nếu listener cần **ghi database mới**, thường nên gọi một bean khác có transaction riêng:

~~~java
@Service
class ReservationWriter {
    private final ReservationRepository reservations;

    ReservationWriter(ReservationRepository reservations) {
        this.reservations = reservations;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void reserve(UUID orderId) {
        reservations.save(new Reservation(orderId));
    }
}
~~~

Đây là đoạn minh họa: các import và định nghĩa `ReservationRepository`/`Reservation` được lược bỏ. Cần gọi phương thức `reserve` **qua Spring proxy**; tự gọi `this.reserve(...)` trong cùng bean có thể không áp dụng `@Transactional` như kỳ vọng.

## 9. Rollback không đồng nghĩa với xử lý đúng một lần

Khi transaction nguồn rollback, listener `AFTER_COMMIT` không được gọi. Khi transaction **commit**, listener vẫn có thể lỗi hoặc được gọi lại do cơ chế recovery. Event Publication Registry giúp theo dõi publication chưa hoàn tất, nhưng không cam kết delivery “exactly once” cho mọi side effect.

Ví dụ email đã gửi rồi tiến trình dừng trước khi registry ghi completed. Sau restart, publication được retry, và email có thể được gửi lại. Vì vậy:

- Sinh `eventId` ổn định tại module nguồn, giữ nguyên khi resubmit.
- Dùng idempotency key ở hệ thống ngoài nếu được hỗ trợ.
- Với cập nhật database, lưu dấu `processed_event` và side effect trong cùng transaction, có unique constraint phù hợp.
- Không bắt rồi nuốt exception của listener nếu muốn registry ghi nhận lỗi để retry.
- Kiểm tra cả **trạng thái database** lẫn **registry publication**; đừng chỉ assert listener method đã được gọi.

Một hệ thống nhiều module có thể có một event nhưng nhiều **publication theo target listener**. Khi đếm publication, cần lọc theo event/target; không dùng số dòng registry làm số lần code gọi `publishEvent`.

## 10. Kiểm chứng kiến trúc bằng ApplicationModules

Test rollback chứng minh hành vi thời gian chạy. Cần thêm quality gate kiến trúc để ngăn module `inventory` phụ thuộc trực tiếp vào entity/repository nội bộ của module `orders`:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` kiểm tra những quy tắc phụ thuộc module mà Spring Modulith áp dụng, như phụ thuộc vòng, truy cập vào kiểu không được công bố và `allowedDependencies`. Trong ví dụ, `inventory` dùng `orders.events.OrderPlaced` qua named interface hợp lệ; truy cập trực tiếp `orders.internal.OrderRepository` phải bị phát hiện.

**Giới hạn:** `verify()` không mở transaction, không chạy service, không phát event và không kiểm tra listener đã xử lý sau commit. Nó bổ sung cho module test và integration test, không thay thế chúng.

## 11. Các tình huống biên cần đưa vào test

| Tình huống | Kỳ vọng và bài kiểm tra |
| --- | --- |
| Validation thất bại **trước khi phát** | `PublishedEvents` không có event; không có dữ liệu commit. |
| Exception sau khi `publishEvent` đã chạy | `PublishedEvents` có thể có event; `AFTER_COMMIT` không chạy; DB rollback. |
| Transaction chỉ đánh dấu `rollbackOnly` | Kiểm tra như rollback dù code không ném lỗi ở cuối callback. |
| Lỗi ở listener `BEFORE_COMMIT` làm transaction rollback | Listener `AFTER_COMMIT` không chạy; listener trước commit có thể đã tạo side effect ngoài transaction. |
| Transaction commit thành công | Listener `AFTER_COMMIT` chạy, DB nguồn giữ dữ liệu; side effect downstream được kiểm chứng riêng. |
| Test có `@Transactional` bao ngoài | Không kết luận đã commit nếu Spring Test rollback cuối test; dùng `TransactionTemplate` hoặc `TestTransaction` đúng cách. |
| Registry starter không được cấu hình | Test “không có publication sau rollback” dễ pass giả; cần nhánh commit đối chứng. |
| Listener chạy async | Cần đồng bộ điều kiện/quan sát trạng thái phù hợp; không assert ngay hoặc dùng sleep cố định. |
| Event phát **ngoài** transaction | `@TransactionalEventListener` mặc định không chạy; không xem đó là minh chứng rollback. |
| Nhiều listener đích | Kiểm tra publication riêng theo target, không coi một target hoàn tất là tất cả hoàn tất. |

### Test lỗi không do exception

Rollback có thể xảy ra vì code chủ động đánh dấu transaction:

~~~java
tx.executeWithoutResult(status -> {
    publisher.publishEvent(event);
    status.setRollbackOnly();
});
~~~

Nhánh này giúp phân biệt rollback do exception và rollback được yêu cầu trực tiếp. Cả hai đều phải làm listener `AFTER_COMMIT` không chạy.

## 12. Quality gate CI cho yêu cầu rollback

Một pipeline hiệu quả của học phần nên bao phủ các lớp bảo vệ sau:

| Quality gate | Điều bảo vệ | Assertion tiêu biểu |
| --- | --- | --- |
| **Module architecture test** | Ranh giới module và quy tắc phụ thuộc. | `ApplicationModules.of(...).verify()` pass. |
| **Module publication test** | Use case phát đúng event và payload. | `PublishedEvents.ofType(...).matching(...)` đúng số lượng. |
| **Rollback listener test** | `AFTER_COMMIT` không chạy khi rollback. | Probe `afterCommit == 0`, `afterRollback == 1`. |
| **Commit đối chứng** | Listener được đăng ký và hoạt động đúng khi nguồn commit. | Probe `afterCommit == 1`, dữ liệu nguồn tồn tại. |
| **Database test** | Thay đổi dữ liệu trong transaction nguồn bị rollback. | `repository.existsById(id) == false`. |
| **Registry integration test** | Publication bền vững không tồn tại sau rollback, tồn tại ở nhánh commit có listener lỗi. | Lọc `findIncompletePublications()` theo event ID. |
| **Async/recovery/idempotency test** | Không mất publication và không tạo side effect trùng khi retry. | Kiểm tra completed/incomplete, dữ liệu downstream, marker xử lý. |

Tích hợp những test này vào tác vụ test chuẩn của dự án trong CI, chẳng hạn `./gradlew test` hoặc `./mvnw test` nếu dự án dùng wrapper tương ứng. Các test database cần cấu hình schema và transaction manager tương đương môi trường thực; với test async, phải có timeout và fixture độc lập.

Không dùng một assertion `PublishedEvents.isEmpty()` để suy ra rollback đã ngăn phát event: kết luận đó **không đúng** nếu mã đã gọi publisher trước rollback. Ngược lại, một test chỉ thấy `afterCommit == 0` cũng chưa đủ nếu listener chưa từng được đăng ký; cần test commit đối chứng.

## 13. Bài tập thực hành

Module `payments` thực hiện:

~~~java
@Transactional
public void capture(UUID paymentId) {
    payments.markCaptured(paymentId);
    events.publishEvent(new PaymentCaptured(paymentId));
    fraudService.verifyOrThrow(paymentId);
}
~~~

Module `accounting` có `@TransactionalEventListener` mặc định để ghi sổ; module `audit` có `@EventListener` thông thường để gửi log qua HTTP.

Giả sử `fraudService.verifyOrThrow` ném một unchecked exception khiến transaction rollback.

**Câu hỏi:**

1. `PublishedEvents` có thể quan sát `PaymentCaptured` không?
2. Listener `accounting` có chạy không? Vì sao?
3. Listener `audit` có thể đã gửi HTTP log không?
4. Bản ghi `PaymentCaptured` trong Event Publication Registry có được commit cùng transaction thất bại không?
5. Nếu test chỉ assert số `AFTER_COMMIT` callback bằng zero, cần test đối chứng nào?
6. Nếu muốn chắc chắn không có một lời gọi `publishEvent` nào trong nhánh fraud bị từ chối, nên thay đổi thứ tự hay thiết kế thế nào?

**Gợi ý đáp án:**

1. Có. Lời gọi `publishEvent` đã xảy ra trước khi fraud check ném lỗi.
2. Không. Listener mặc định là `AFTER_COMMIT`, trong khi transaction nguồn rollback.
3. Có. `@EventListener` mặc định chạy ngay; side effect HTTP không được hoàn tác khi database rollback.
4. Không, nếu registry persistence tham gia cùng transaction nguồn, publication được ghi trong transaction đó cũng rollback.
5. Chạy một use case commit thành công để xác nhận `AFTER_COMMIT` listener có thực sự được đăng ký và thực thi.
6. Thực hiện kiểm tra fraud **trước** lời gọi `publishEvent` nếu có thể và phù hợp transaction. Với những lỗi có thể xảy ra sau đó (như lỗi commit), nếu yêu cầu là chỉ phân phối sau commit, dùng transactional listener/registry/outbox theo thiết kế; chỉ đổi thứ tự code không bảo đảm loại bỏ mọi rollback muộn.

## 14. Checklist khi đánh giá kết quả

- [ ] Mô tả rõ “không được publish” là **không gọi publisher**, **không xử lý listener sau commit**, hay **không có publication bền vững**.
- [ ] Có test rollback thật, không chỉ mock một exception mà không có transaction.
- [ ] Test rollback kiểm tra dữ liệu nguồn đã bị rollback.
- [ ] Test `AFTER_COMMIT` không chạy khi rollback và **có chạy** khi commit thành công.
- [ ] Nếu theo dõi `AFTER_ROLLBACK`, test xác nhận callback được gọi.
- [ ] Không yêu cầu `PublishedEvents` rỗng nếu code đã phát event trước rollback.
- [ ] Nếu nghiệp vụ muốn không bao giờ gọi publisher ở nhánh validation thất bại, đặt guard trước lời gọi và viết test riêng.
- [ ] Kiểm tra cấu hình `@Transactional` thực sự đi qua Spring proxy.
- [ ] Không để transaction test bao ngoài làm sai thời điểm commit/rollback.
- [ ] Nếu dùng Event Publication Registry, test rollback **và** nhánh commit đối chứng có listener thật.
- [ ] Với side effect ngoài hệ thống, có cơ chế after-commit, recovery và idempotency phù hợp.
- [ ] Event thuộc public API module; test `ApplicationModules.verify()` cùng module/integration test chạy trong CI.

**Kết luận:** Khi một transaction rollback **sau lời gọi `publishEvent`**, lời gọi phát event đã diễn ra và `PublishedEvents` vẫn có thể quan sát nó. Điều cần bảo đảm và kiểm chứng là **transactional listener `AFTER_COMMIT` không chạy, dữ liệu nguồn không commit và publication bền vững cùng transaction không còn**. Kết hợp test rollback với nhánh commit đối chứng giúp tránh những bài test “xanh” giả và bảo vệ hành vi Spring Modulith qua các lần thay đổi.
