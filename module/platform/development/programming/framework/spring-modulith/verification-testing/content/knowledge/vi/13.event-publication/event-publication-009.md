# Lỗi khi publication listener thất bại

## 1. Một event đã phát nhưng listener gặp lỗi: điều gì thực sự thất bại?

Trong ứng dụng Spring Modulith, module `orders` có thể lưu đơn hàng và phát `OrderPlaced` trong một transaction. Module `inventory` nhận sự kiện để giữ tồn kho; module `notifications` nhận cùng sự kiện để gửi thông báo. Giả sử transaction của `orders` đã commit, nhưng listener giữ tồn kho ném exception do database tạm thời không truy cập được.

Kết quả đúng không phải là “mọi thứ đều rollback”:

- **Dữ liệu nguồn đã commit**: đơn hàng có thể đã tồn tại bền vững.
- **Lời gọi `publishEvent` đã xảy ra**: một test `PublishedEvents` có thể quan sát được event.
- **Một listener đích bị lỗi**: thao tác giữ tồn kho chưa chắc thành công.
- **Listener khác có thể thành công**: mỗi transactional listener là một target publication riêng khi dùng Event Publication Registry.
- **Publication lỗi cần được theo dõi/khôi phục** nếu hệ thống yêu cầu giao sự kiện đáng tin cậy.

Đây là ranh giới quan trọng giữa **transaction của module phát** và **transaction/tác động của module nhận**. Một listener thất bại *sau commit* không thể đơn giản buộc transaction nguồn đã commit quay lại trạng thái trước đó.

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, bài này gắn việc kiểm chứng phụ thuộc module bằng `ApplicationModules` với kiểm thử `@ApplicationModuleTest`, transaction, database, Event Publication Registry và quality gate CI để ngăn hồi quy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt lỗi trong `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener`.
2. Xác định lỗi xảy ra **trước commit** hay **sau commit** và tác động đến transaction nguồn.
3. Giải thích publication đang chờ, hoàn tất, thất bại và được xử lý lại theo từng target.
4. Viết test mô phỏng listener ném exception để kiểm tra database nguồn cùng publication chưa hoàn tất.
5. Xây dựng hướng xử lý retry, idempotency, timeout và lỗi không thể tự phục hồi.
6. Đưa test lỗi listener, test ranh giới module và test khôi phục vào CI.

## 2. Phân loại lỗi theo thời điểm xử lý

`ApplicationEventPublisher.publishEvent(...)` công bố một object Java tới cơ chế sự kiện của Spring. Nó không tự mở transaction và không tự bảo đảm việc các listener luôn hoàn tất.

| Listener | Khi nào chạy trong cấu hình mặc định? | Nếu ném exception thì sao? |
| --- | --- | --- |
| `@EventListener` đồng bộ | Ngay khi event được phân phối. | Exception thường truyền về bên phát; nếu đang trong transaction và là exception kích hoạt rollback, transaction nguồn có thể rollback. |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Trước commit. | Exception có thể làm quá trình commit thất bại, dẫn tới rollback transaction nguồn. |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit thành công. | Transaction nguồn **đã commit**; lỗi không hoàn tác dữ liệu nguồn. Với listener đồng bộ, exception có thể lan ra caller hoặc được xử lý bởi hạ tầng, tùy cấu hình. |
| `@ApplicationModuleListener` | Tiện ích Spring Modulith cho transactional event listener bất đồng bộ, có transaction mới. | Lỗi xảy ra trong quá trình xử lý async; không giả định caller của `publishEvent` nhận exception. Publication có thể còn cần xử lý lại. |

Không dùng cách gọi chung “listener lỗi nên rollback” nếu chưa xác định **transaction nào**. Với listener sau commit, việc ghi database ở module nhận thường diễn ra trong transaction mới hoặc transaction riêng do annotation/cấu hình tạo ra.

### Sơ đồ đường thành công và lỗi

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as orders.OrderService
    participant DB as Database
    participant Pub as Event Publisher/Registry
    participant Stock as inventory.Listener
    participant Mail as notifications.Listener

    Client->>Order: place(orderId)
    Note over Order,DB: Transaction nguồn
    Order->>DB: Lưu đơn hàng
    Order->>Pub: publishEvent(OrderPlaced)
    Pub->>DB: Ghi publication theo listener target
    Order->>DB: COMMIT nguồn
    par Target inventory
        Pub-->>Stock: Giao event
        Stock->>Stock: Xử lý trong transaction riêng
        Stock-->>Pub: Ném exception
        Note over Pub,Stock: Publication chưa completed
    and Target notifications
        Pub-->>Mail: Giao event
        Mail-->>Pub: Xử lý thành công
        Note over Pub,Mail: Publication completed
    end
    Note over Order,DB: Đơn hàng vẫn đã commit
~~~

Sơ đồ là mô hình khái niệm; listener có thể thực thi tuần tự hoặc bất đồng bộ tùy annotation và cấu hình executor. Event Publication Registry hỗ trợ ghi nhận publication và completion; nó không phải broker và không mặc nhiên xử lý toàn bộ retry nếu chưa có chính sách recovery.

## 3. Lỗi trước commit và lỗi sau commit khác nhau thế nào?

### 3.1. Listener thông thường có thể làm transaction nguồn rollback

~~~java
@Component
class ValidationListener {

    @EventListener
    void on(OrderPlaced event) {
        throw new IllegalStateException("Synchronous listener failed");
    }
}
~~~

Nếu `OrderService.place(...)` gọi `publishEvent` trong transaction, multicaster mặc định phân phối `@EventListener` đồng bộ. Exception unchecked từ listener có thể truyền ra `place` và khiến transaction nguồn rollback theo quy tắc `@Transactional` mặc định.

**Không nên** dùng `@EventListener` đồng bộ để thực hiện công việc chỉ có ý nghĩa sau commit nếu side effect không thể rollback (gửi email, gọi HTTP, ghi file). Một side effect ngoài database có thể đã xảy ra rồi transaction nguồn mới thất bại.

### 3.2. Transactional listener sau commit không rollback transaction đã hoàn tất

~~~java
@Component
class StockListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) {
        throw new IllegalStateException("Inventory database unavailable");
    }
}
~~~

Với sự kiện được phát trong transaction nguồn và commit thành công, `AFTER_COMMIT` listener chạy **sau khi commit**. Exception của listener có thể làm hàm caller quan sát một lỗi kỹ thuật, nhưng **không phải bằng chứng transaction nguồn chưa commit**.

Một hệ thống không được tự động gọi lại use case đặt hàng chỉ vì client thấy exception nếu không có cơ chế idempotency: có thể tạo đơn hàng hoặc side effect lặp. Test phải kiểm tra **trạng thái database thực tế**, không chỉ dựa vào exception hay HTTP status.

### 3.3. @ApplicationModuleListener và lỗi bất đồng bộ

~~~java
@Component
class StockListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        reservationService.reserve(event.orderId());
    }
}
~~~

`@ApplicationModuleListener` kết hợp xử lý theo transaction, bất đồng bộ và transaction mới theo cơ chế Spring Modulith. Nếu `reservationService.reserve(...)` ném exception, exception thuộc công việc xử lý event; caller của `orders.place` không nhất thiết nhận lỗi đó do tác vụ chạy trên thread khác.

Vì xử lý bất đồng bộ, **không assert ngay lập tức** rằng publication đã failed hoặc một bản ghi tồn kho đã được tạo. Cần chờ bằng điều kiện phù hợp hoặc hỗ trợ `Scenario` của Spring Modulith và giới hạn timeout trong test.

### 3.4. Listener lỗi nhưng tự nuốt exception

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    try {
        reservationService.reserve(event.orderId());
    } catch (Exception ex) {
        log.warn("Reservation failed", ex);
        // Trả về bình thường -> hạ tầng có thể coi là xử lý thành công.
    }
}
~~~

Đây là **anti-pattern nếu yêu cầu registry ghi nhận thất bại để xử lý lại**. Listener trả về bình thường có thể bị coi là completed dù nghiệp vụ downstream chưa thành công.

Có thể phân loại lỗi không thể retry và đưa vào hàng đợi vận hành, nhưng đó phải là **chính sách nghiệp vụ rõ ràng**, không phải một khối `catch` âm thầm biến lỗi thành thành công.

## 4. Event Publication Registry theo dõi target bị lỗi

Spring Modulith Event Publication Registry ghi nhận một publication cho **mỗi transactional listener target** phù hợp event khi persistence được cấu hình đúng. Vì vậy một event có thể dẫn đến:

~~~text
OrderPlaced(eventId = E-17)
├── Publication P-1 -> inventory.StockListener     : chưa completed / failed
└── Publication P-2 -> notifications.EmailListener : completed
~~~

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **Event ID nghiệp vụ** | Định danh sự kiện, hữu ích cho idempotency; cần tự định nghĩa trong payload nếu muốn dùng. |
| **Publication ID** | ID bản ghi giao event đến target, do registry quản lý. |
| **Target identifier** | Danh tính listener đích, không mặc nhiên là tên module. |
| **Completion** | Xác nhận listener đích kết thúc thành công, độc lập với target khác. |
| **Incomplete / failed** | Publication cần quan sát, đánh giá và có thể xử lý lại tùy phiên bản/chính sách. |

Nếu một listener thành công, registry chỉ đánh dấu hoàn tất **publication của target đó**, không tự hoàn tất publication tới listener khác. Trạng thái của một bản ghi phải được hiểu ở mức **event + target**, không chỉ theo event type.

### 4.1. Khái niệm incomplete và trạng thái FAILED

`EventPublicationRegistry.findIncompletePublications()` trả về publication chưa completed. Trong đó có thể có publication đang chờ hoặc đang xử lý bình thường; **incomplete không đồng nghĩa tất cả đều lỗi**.

Các phiên bản Spring Modulith có lifecycle trạng thái chi tiết (2.0+) còn cung cấp trạng thái như:

| Trạng thái | Cách diễn giải |
| --- | --- |
| `PUBLISHED` | Publication đã được ghi, đang chờ xử lý. |
| `PROCESSING` | Target đã bắt đầu xử lý. |
| `COMPLETED` | Listener đã được xác nhận hoàn tất thành công. |
| `FAILED` | Xử lý thất bại hoặc publication được đánh dấu stale theo cơ chế hỗ trợ. |
| `RESUBMITTED` | Publication đã được đưa vào luồng thử lại. |
| `ABANDONED` (phiên bản hỗ trợ) | Publication bị từ bỏ theo chính sách xử lý lỗi; **không phải** thành công. |

Với phiên bản 1.x, việc quan sát chủ yếu dựa vào **incomplete/completed** và các API tương ứng; không áp dụng nguyên xi một API trạng thái 2.x vào ứng dụng cũ. Khi cần quyết định retry, kết hợp trạng thái, **tuổi publication**, loại lỗi và tình trạng instance đang xử lý.

### 4.2. Completion mode ảnh hưởng cách đọc kết quả

Property `spring.modulith.events.completion-mode` cho phép các chiến lược lưu publication đã hoàn tất:

| Mode | Sau khi target hoàn tất | Điều cần lưu ý khi test |
| --- | --- | --- |
| `UPDATE` | Giữ bản ghi và cập nhật thông tin completion. | Có thể kiểm tra lịch sử completed. |
| `DELETE` | Xóa bản ghi đã hoàn tất. | Không tìm thấy bản ghi **không tự chứng minh** listener đã thành công. |
| `ARCHIVE` | Đưa bản ghi completed sang vùng archive theo hỗ trợ của storage. | Test phải truy vấn đúng vùng dữ liệu/API. |

Một test thất bại listener thường kiểm tra publication **còn incomplete**. Nếu test thành công listener cần kiểm tra completed record, phải biết completion mode của môi trường chạy. Với `DELETE`, hãy xác nhận **side effect đã thực hiện** và publication không còn incomplete thay vì kỳ vọng tìm thấy bản ghi completed.

### 4.3. Transaction của registry

Khi event được phát trong transaction nguồn và registry dùng bộ lưu trữ phù hợp:

1. Publication được ghi trong transaction nguồn.
2. Nếu transaction nguồn rollback, publication đó cũng rollback.
3. Nếu nguồn commit, publication tồn tại để theo dõi việc xử lý của listener.
4. Listener lỗi sau commit khiến publication **chưa được xác nhận completed**, nhưng nguồn đã commit.

Đây không phải một distributed transaction xuyên tất cả module. Một module nhận có thể có transaction riêng và rollback khi listener gặp lỗi; điều đó không đảo ngược một transaction nguồn đã commit.

## 5. Ví dụ thiết kế module orders và inventory

Giả sử lớp `ShopApplication` nằm ở `com.example.shop`, và Spring Modulith dùng cách phát hiện module mặc định:

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
    ├── StockReservationService.java
    └── package-info.java
~~~

### 5.1. Event công khai

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {
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

`eventId` là định danh duy nhất của **sự kiện nghiệp vụ**, không phải publication ID. Một event có thể tạo nhiều publication đến nhiều target; khi retry cùng event, `eventId` phải được giữ nguyên. Payload không nên chứa entity/repository hoặc service nội bộ.

### 5.2. Module nguồn lưu đơn hàng và phát event

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
    private final ApplicationEventPublisher publisher;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public void place(UUID orderId) {
        orders.save(new OrderEntity(orderId));
        publisher.publishEvent(
                new OrderPlaced(UUID.randomUUID(), orderId, Instant.now()));
    }
}
~~~

`OrderEntity` là entity JPA có `UUID` làm khóa, còn `OrderRepository` là `JpaRepository<OrderEntity, UUID>` của module nguồn. Định nghĩa chi tiết được lược bỏ vì trọng tâm là lỗi listener. Ví dụ giả định Spring Boot có JPA, datasource, schema và transaction manager hoạt động.

Lời gọi `publisher.publishEvent` nằm trong transaction của `place`. Nếu `place` commit, listener `AFTER_COMMIT` mới được phép chạy. Nếu listener lỗi **sau commit**, bản ghi đơn hàng không tự biến mất.

### 5.3. Module nhận có listener riêng

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

`StockReservationService` cần tự triển khai trong module `inventory` với transaction và chính sách idempotency. Giả sử nó gọi repository lưu bản ghi giữ hàng. Nếu database tạm lỗi, exception nên phản ánh ra khỏi listener để registry có thể theo dõi publication chưa hoàn tất.

File `inventory/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.example.shop.inventory;
~~~

`inventory` chỉ được import event API công khai, không truy cập `orders.internal.OrderRepository`. Một lỗi runtime ở listener **khác bản chất** với một vi phạm boundary tĩnh.

## 6. Kiểm thử module phát: đã publish gì?

Trong `@ApplicationModuleTest` đặt tại `com.example.shop.orders`, `PublishedEvents` giúp xác nhận use case nguồn phát đúng payload:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import java.util.UUID;
import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderPublicationTests {

    @Autowired OrderService orders;

    @Test
    void publishesOrderPlaced(PublishedEvents events) {
        UUID orderId = UUID.randomUUID();

        orders.place(orderId);

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.eventId()).isNotNull();
                    assertThat(event.occurredAt()).isNotNull();
                });
    }
}
~~~

Đoạn test này có giá trị nhưng **không chứng minh listener `inventory` đã xử lý hoặc publication đã completed**. Với module test mặc định `STANDALONE`, module listener khác có thể không được bootstrap trong context. Kể cả khi event đã phát, còn cần integration test có đúng listener và persistence registry để kiểm chứng lỗi downstream.

## 7. Integration test: nguồn commit, listener ném lỗi, publication còn lại

Để kiểm thử đường lỗi mà không phụ thuộc network hoặc tác vụ gửi mail thật, hãy đăng ký **transactional listener chỉ dùng trong test**. Nó cố tình ném exception **sau commit** cho một `ProbeEvent`, giúp xác nhận registry thực sự lưu publication chưa hoàn tất.

### Điều kiện chạy

- Spring Boot + Spring Modulith, có persistence starter của Event Publication Registry (ví dụ JDBC/JPA).
- Datasource, transaction manager, schema registry và serializer hoạt động.
- Test có ứng dụng Spring Boot hợp lệ (`ShopApplication`) để `@SpringBootTest` bootstrap.
- Test **không được bao bằng `@Transactional` tự rollback**.
- Đoạn ví dụ dùng `@TransactionalEventListener` **đồng bộ** thay vì `@ApplicationModuleListener` async để việc quan sát sau `TransactionTemplate` dễ xác định.

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
@Import(ListenerFailureRegistryTests.TestListeners.class)
class ListenerFailureRegistryTests {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired EventPublicationRegistry registry;
    @Autowired PlatformTransactionManager transactionManager;

    public record ProbeEvent(UUID eventId) {}

    @Test
    void failedAfterCommitListenerLeavesPublicationIncomplete() {
        UUID eventId = UUID.randomUUID();
        var tx = new TransactionTemplate(transactionManager);

        try {
            tx.executeWithoutResult(status ->
                    publisher.publishEvent(new ProbeEvent(eventId)));
        } catch (IllegalStateException expected) {
            // Listener test cố tình ném lỗi AFTER_COMMIT.
            // Việc exception lan tới caller tùy hạ tầng.
        }

        assertThat(registry.findIncompletePublications())
                .anyMatch(publication ->
                        publication.getEvent() instanceof ProbeEvent event
                                && event.eventId().equals(eventId));
    }

    @Test
    void rollbackDoesNotLeaveDurablePublication() {
        UUID eventId = UUID.randomUUID();
        var tx = new TransactionTemplate(transactionManager);

        tx.executeWithoutResult(status -> {
            publisher.publishEvent(new ProbeEvent(eventId));
            status.setRollbackOnly();
        });

        assertThat(registry.findIncompletePublications())
                .noneMatch(publication ->
                        publication.getEvent() instanceof ProbeEvent event
                                && event.eventId().equals(eventId));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestListeners {
        @Bean
        FailingListener failingListener() {
            return new FailingListener();
        }
    }

    static class FailingListener {
        @TransactionalEventListener
        public void on(ProbeEvent event) {
            throw new IllegalStateException(
                    "Simulated failure in listener");
        }
    }
}
~~~

### Đọc kết quả đúng cách

**Test 1 — commit nhưng listener lỗi:** transaction nguồn commit trước khi callback `AFTER_COMMIT` thất bại. Registry còn publication chưa hoàn tất của event test.

**Test 2 — rollback nguồn:** transaction chứa `publishEvent` rollback, vì vậy publication được ghi trong cùng transaction không tồn tại bền vững. Listener `AFTER_COMMIT` cũng không chạy.

Hai test bổ sung cho nhau. Nếu chỉ test rollback, một ứng dụng không cấu hình registry hoặc không đăng ký listener có thể “pass” vì không có publication nào được tạo ngay từ đầu. Test commit với listener lỗi xác nhận hạ tầng thực sự đang theo dõi publication.

**Giới hạn:** ví dụ phụ thuộc phiên bản Spring Modulith, cách serialize record và cấu hình đồng bộ/async. Nếu exception được bọc trong kiểu khác, test cần điều chỉnh xử lý exception dựa trên cấu hình thực tế; assertion quan trọng là publication vẫn được lưu sau commit. Không chạy test với database chỉ giả lập bằng mock nếu mục tiêu là xác nhận durability.

### 7.1. Chứng minh dữ liệu nguồn vẫn commit

Test ở trên tập trung vào publication. Khi kiểm chứng nghiệp vụ thật, nên tạo một order trong cùng transaction nguồn:

~~~java
tx.executeWithoutResult(status -> {
    orderRepository.save(new OrderEntity(orderId));
    publisher.publishEvent(new ProbeEvent(eventId));
});
~~~

Sau khi listener `AFTER_COMMIT` ném lỗi (và test xử lý exception test-only nếu lan ra), kiểm tra:

~~~java
assertThat(orderRepository.existsById(orderId)).isTrue();
assertThat(registry.findIncompletePublications())
        .anyMatch(publication ->
                publication.getEvent() instanceof ProbeEvent event
                        && event.eventId().equals(eventId));
~~~

Đây là **các đoạn bổ sung** cho integration test có `orderRepository`/`OrderEntity` và transaction manager. Điều cần chứng minh là: **commit nguồn thành công** và **listener vẫn lỗi** có thể xảy ra đồng thời. Không viết `assertThatThrownBy(service::place)` rồi tự suy ra DB đã rollback.

## 8. Khi có nhiều listener: lỗi của một target không nhất thiết làm tất cả lỗi

Giả sử event `OrderPlaced` có hai listener sau commit:

- `inventory`: giữ tồn kho, gặp lỗi timeout.
- `notifications`: ghi thông báo, xử lý thành công.

Về mặt registry, mỗi listener có **publication riêng**. Trong xử lý bất đồng bộ, chúng có thể tiến triển độc lập:

| Publication | Target | Kết quả | Điều cần quan sát |
| --- | --- | --- | --- |
| `P1` | `inventory.StockReservationListener` | Chưa completed / failed | Lỗi, tuổi publication, khả năng xử lý lại. |
| `P2` | `notifications.OrderNotificationListener` | Completed | Side effect đã lưu, thời điểm hoàn tất. |

**Chú ý:** Với các listener **đồng bộ** trong cùng chuỗi callback, exception từ một callback có thể ảnh hưởng thứ tự hoặc khả năng các callback kế tiếp được gọi. Không suy ra “listener B chắc chắn thành công” chỉ vì đã đăng ký cả hai. Muốn test hai target xử lý độc lập, hãy dùng cấu hình listener phù hợp và kiểm tra từng target bằng kết quả thực tế.

Trong integration test nhiều listener, cần:

1. Phát cùng một event trong transaction commit thật.
2. Cho listener A thành công và listener B thất bại có kiểm soát.
3. Chờ nếu xử lý async; không dùng `Thread.sleep` cố định.
4. Kiểm tra side effect của A tồn tại trong database.
5. Kiểm tra publication tới B chưa completed (hoặc `FAILED` ở phiên bản hỗ trợ).
6. Xử lý lại B, kiểm tra không làm A bị thực thi lặp ngoài ý muốn.

Khi dùng `completion-mode=DELETE`, bản ghi hoàn tất của A có thể đã biến mất; cần kết hợp **side effect thực tế** với trạng thái publication còn tồn. Không thể chỉ nhìn “không có publication A” mà kết luận A đã chạy.

## 9. Xử lý lại publication lỗi có kiểm soát

Registry giúp lưu bằng chứng publication chưa completed, nhưng **không nên retry mù tất cả incomplete ngay lập tức**. Một publication có thể đang xử lý bình thường ở một thread hoặc một instance khác.

### 9.1. Truy vấn và đánh giá trước khi retry

~~~java
@Service
class PublicationInspector {

    private final EventPublicationRegistry registry;

    PublicationInspector(EventPublicationRegistry registry) {
        this.registry = registry;
    }

    void reportStuckPublications() {
        registry.findIncompletePublicationsOlderThan(
                Duration.ofMinutes(15))
            .forEach(publication -> {
                var target = publication.getTargetIdentifier();
                var id = publication.getIdentifier();
                // Gửi metric/log có phân quyền; tránh log toàn bộ payload.
                System.out.printf("%s target=%s%n", id, target);
            });
    }
}
~~~

Đây là đoạn Java **rút gọn**, cần import `@Service`, `EventPublicationRegistry`, `Duration` và cấu hình bean. Truy vấn theo tuổi giúp ưu tiên điều tra; **tuổi lớn không tự chứng minh exception**.

### 9.2. API resubmit

Spring Modulith có `IncompleteEventPublications` để xử lý lại các publication chưa hoàn tất, ví dụ:

~~~java
@Service
class PublicationRecoveryJob {

    private final IncompleteEventPublications incomplete;

    PublicationRecoveryJob(IncompleteEventPublications incomplete) {
        this.incomplete = incomplete;
    }

    void retryOldPublications() {
        incomplete.resubmitIncompletePublicationsOlderThan(
                Duration.ofMinutes(15));
    }
}
~~~

Đây là **mẫu cho job vận hành** đã được kiểm soát, không nên gắn trực tiếp vào mỗi request nghiệp vụ. Cần kiểm tra phiên bản API, điều kiện lọc, topology triển khai, batching, thời gian xử lý và khả năng trùng. Ở các phiên bản có `FailedEventPublications`, có thể chọn riêng publication failed và cấu hình resubmission theo tùy chọn hỗ trợ, thay vì tự xử lý mọi incomplete.

Property có thể dùng để xem xét phát lại publication còn tồn khi restart:

~~~properties
spring.modulith.events.republish-outstanding-events-on-restart=true
~~~

Không bật vô điều kiện nếu nhiều instance cùng chạy hoặc listener chưa idempotent. Một lần restart không nên gây “bão retry” lên dependency vẫn lỗi.

### 9.3. Phân loại lỗi trước khi resubmit

| Loại lỗi | Ví dụ | Chính sách thường phù hợp |
| --- | --- | --- |
| **Tạm thời** | Database không sẵn sàng, timeout mạng, HTTP 503. | Retry có giới hạn và backoff; theo dõi số lần thử. |
| **Payload không hợp lệ** | Thiếu trường bắt buộc hoặc không deserialize được sau nâng cấp. | Sửa hợp đồng/migration; không retry vô hạn cùng dữ liệu lỗi. |
| **Lỗi nghiệp vụ vĩnh viễn** | Mã SKU không tồn tại, trạng thái không được phép. | Quy trình xử lý riêng/đánh dấu không thể phục hồi; cần quyết định rõ về publication. |
| **Phụ thuộc bên ngoài có side effect không rõ kết quả** | Timeout sau khi đã gửi email hoặc charge. | Kiểm tra trạng thái/idempotency key trước khi gọi lại. |
| **Lỗi do cấu hình listener** | Thay tên method/target, thiếu bean, sai transaction manager. | Sửa deploy/cấu hình rồi mới recovery; rà soát publication tồn từ phiên bản cũ. |

Trong Spring Modulith 2.x, tính năng theo dõi trạng thái và staleness giúp quản lý publication bị kẹt; các hành vi cụ thể phụ thuộc phiên bản và cấu hình. Một publication bị đánh dấu `ABANDONED` trong phiên bản hỗ trợ **không** có nghĩa tác vụ nghiệp vụ đã thành công.

## 10. Idempotency: retry được phép gọi listener nhiều lần

Giả sử listener gửi email:

1. Listener gọi email provider, email được gửi.
2. Ứng dụng dừng ngay sau đó **trước khi** registry đánh dấu publication completed.
3. Khi retry, listener được gọi thêm lần nữa.
4. Nếu không có cơ chế chống trùng, khách hàng nhận hai email.

Do đó, Event Publication Registry **không tự tạo bảo đảm exactly-once effect** cho dịch vụ ngoài. Nó hỗ trợ theo dõi và khôi phục; consumer cần thiết kế thao tác lặp an toàn.

### 10.1. Khóa idempotency ổn định

Sử dụng `eventId` do module nguồn sinh **một lần**:

~~~java
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Khi cùng sự kiện được resubmit, `eventId` không đổi. Với thay đổi database ở module `inventory`, có thể lưu một bản ghi `ProcessedEvent(eventId)` trong **cùng transaction** với thao tác giữ tồn kho:

~~~java
@Transactional
public void reserveOnce(OrderPlaced event) {
    if (processedEvents.existsById(event.eventId())) {
        return;
    }

    // Cập nhật tồn kho và lưu dấu trong cùng transaction.
    reservations.reserve(event.orderId());
    processedEvents.save(new ProcessedEvent(event.eventId()));
}
~~~

Đây là **đoạn minh họa**: cần có entity/repository, unique constraint và chính sách xử lý concurrency phù hợp. Chỉ kiểm tra `existsById` rồi `save` không tránh hết race: hai transaction đồng thời có thể cùng thấy chưa xử lý. Cần DB unique key, transaction và xử lý lỗi constraint đúng cách. Nếu side effect ngoài hệ thống, hãy dùng idempotency key do provider hỗ trợ hoặc một cơ chế dispatch/outbox phù hợp.

### 10.2. Không tự đánh dấu completed khi side effect chưa xong

API của registry có thể cho phép thao tác hoàn tất publication ở mức hạ tầng. Mã nghiệp vụ thông thường **không nên** tự gọi `markCompleted` để che một lỗi chưa được khắc phục. Một publication bị đánh dấu completed khi inventory chưa thực sự giữ hàng sẽ không còn xuất hiện trong nhóm cần retry.

Hãy gắn điều kiện thành công với **kết quả nghiệp vụ**: số lượng tồn kho thực tế, record đã ghi, hoặc xác nhận được định nghĩa rõ từ dịch vụ ngoài. Sau đó mới để hạ tầng hoàn tất lifecycle publication.

## 11. Kiểm thử listener bất đồng bộ và database

Với `@ApplicationModuleListener`, callback có thể chạy trên executor khác sau commit. Test kiểu:

~~~java
orders.place(id);
assertThat(reservations.existsByOrderId(id)).isTrue();
~~~

có thể thất bại ngẫu nhiên dù code đúng, vì test đọc database trước khi listener kịp hoàn tất.

Nếu dự án có Awaitility, thay bằng chờ theo điều kiện:

~~~java
orders.place(id);

await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(reservations.existsByOrderId(id))
                        .isTrue());
~~~

Đây là đoạn assertion trong integration test đã có `orders`, `reservations`, `id` và các import tương ứng. Có thể dùng `Scenario` của Spring Modulith để kiểm chứng event và state change khi phù hợp.

### 11.1. Test một lần lỗi rồi thành công

Một kịch bản đủ sâu cho listener:

1. Đưa listener vào chế độ **fail** qua một dependency test có thể điều khiển (ví dụ fake external service).
2. Phát event trong transaction commit; chờ listener báo lỗi hoặc registry ghi nhận publication còn incomplete.
3. Assert **không có side effect bền vững** ở module nhận nếu transaction xử lý của listener đã rollback.
4. Bật lại dependency test, gọi resubmit theo đúng API/cấu hình.
5. Chờ publication được xác nhận hoàn tất và kiểm tra **side effect đúng một lần**.
6. Resubmit/cố tình giao lại cùng `eventId` để xác nhận idempotency.

Nếu đoạn retry được kiểm thử bằng fake service, cần thêm integration test với database thật để kiểm tra transaction rollback, unique constraint và các ranh giới commit. Không thay thế toàn bộ test bằng mock publisher.

### 11.2. Test nhiều target

Với hai listener `inventory` và `notifications`, mỗi target có publication độc lập. Khi một target lỗi:

- Assertion về **publication chưa completed** phải lọc đúng event ID và target.
- Assertion về **side effect** phải kiểm tra dữ liệu thuộc module nhận tương ứng.
- Assertion “mọi publication của event đã completed” chỉ đúng khi **tất cả target** đã hoàn tất hoặc có chính sách xử lý khác được ghi nhận rõ ràng.

Số bản ghi publication **không** bằng số lần `publishEvent` trong mọi trường hợp: một event có thể có nhiều target.

### 11.3. Không nhầm rollback nguồn với rollback listener

| Trường hợp | Đơn hàng ở module nguồn | Dữ liệu module nhận | Publication |
| --- | --- | --- | --- |
| Nguồn rollback trước commit | Không được commit. | Listener `AFTER_COMMIT` không chạy. | Ghi cùng transaction nguồn bị rollback. |
| Nguồn commit, listener thành công | Đã commit. | Side effect được xác nhận. | Completed theo mode lưu trữ. |
| Nguồn commit, listener rollback | **Vẫn commit.** | Tác vụ trong transaction listener bị rollback. | Chưa completed hoặc trạng thái failed theo phiên bản. |
| Listener hoàn tất side effect ngoài rồi chết trước completion | Đã commit. | Side effect có thể đã xảy ra. | Có thể còn incomplete và được retry. |

Bảng này là căn cứ để thiết kế assertion, báo lỗi và chính sách recovery đúng.

## 12. Kiểm chứng ranh giới kiến trúc khi listener gặp lỗi

Một listener gặp exception **không phải** bằng chứng module boundary sai. Ngược lại, kiến trúc không có phụ thuộc vòng **không** bảo đảm listener sẽ thành công trong runtime. Cần cả hai:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` giúp phát hiện phụ thuộc vòng và truy cập vào kiểu không được module khác công bố, hoặc vi phạm `allowedDependencies`. Trong ví dụ, `inventory` chỉ được dùng `orders.events.OrderPlaced` qua named interface, không import `orders.internal.OrderRepository`.

**Giới hạn:** test kiến trúc không gọi `OrderService.place`, không giả lập database timeout, không làm publication failed và không kiểm tra idempotency. Nó bảo vệ ranh giới tĩnh, bổ sung cho module test và integration test.

## 13. Quality gate CI và giám sát sau triển khai

Một nhóm kiểm tra hữu ích cho học phần `SPRING_MODULITH_VERIFICATION_TESTING`:

| Quality gate | Mục tiêu | Phép kiểm tra tiêu biểu |
| --- | --- | --- |
| **Architecture test** | Ngăn phụ thuộc sai và vòng module. | `ApplicationModules.of(...).verify()` |
| **Publisher module test** | Phát đúng loại event và payload. | `@ApplicationModuleTest` + `PublishedEvents` |
| **Commit/rollback test** | Phân biệt lỗi nguồn trước commit với lỗi listener sau commit. | `TransactionTemplate`, DB assertion, listener probe |
| **Registry integration test** | Publication chưa completed được lưu sau listener lỗi. | `@SpringBootTest`, persistence starter, `findIncompletePublications()` |
| **Per-target test** | Listener thành công không bị ảnh hưởng sai bởi target lỗi. | Kiểm tra publication và side effect từng target |
| **Recovery/idempotency test** | Retry đạt trạng thái cuối, không nhân đôi nghiệp vụ. | Fail-once fake, resubmit, unique key, DB |
| **Serialization/upgrade test** | Publication lưu lâu vẫn đọc lại được. | Round-trip serializer/schema tương ứng |

Chạy các nhóm test trong CI bằng task test của Gradle/Maven theo cấu hình dự án. Với test database, cần schema và transaction manager tương tự production; với test async, chờ theo điều kiện có timeout thay vì `Thread.sleep` cố định.

### Những chỉ số đáng theo dõi ở production

- Số publication chưa hoàn tất **theo target**.
- Tuổi của publication lâu nhất và độ trễ hoàn tất.
- Số `FAILED`, số lần retry và publication `ABANDONED` ở phiên bản hỗ trợ.
- Tỷ lệ lỗi/timeout theo loại exception và dependency.
- Tốc độ hoàn tất của từng listener sau deploy.
- Tỷ lệ xử lý trùng bị chặn bởi idempotency.

Không log toàn bộ payload nếu có dữ liệu nhạy cảm. Đặt cảnh báo theo SLA nghiệp vụ; ví dụ “publication giữ tồn kho quá lâu chưa hoàn tất” quan trọng hơn chỉ số tổng số event phát.

## 14. Những hiểu nhầm thường gặp

1. **“Listener lỗi nên transaction nguồn rollback.”** Chỉ có thể đúng với lỗi trước commit hoặc đồng bộ trong transaction; **không đúng** khi lỗi xảy ra sau khi nguồn đã commit.
2. **“Publisher không trả exception nghĩa là listener đã thành công.”** Không đúng cho listener async và nhiều đường xử lý lỗi.
3. **“PublishedEvents có event nghĩa là registry đã completed.”** Sai. Nó quan sát sự kiện được phát, không phải completion của listener.
4. **“Incomplete chắc chắn là FAILED.”** Sai. Publication có thể mới tạo hoặc đang xử lý; cần tuổi, trạng thái và chính sách.
5. **“Một event chỉ có một publication.”** Sai khi có nhiều transactional listener target.
6. **“Retry sẽ bảo đảm side effect chính xác một lần.”** Sai nếu consumer chưa idempotent.
7. **“Bắt mọi exception rồi log là đủ.”** Sai nếu listener trả về bình thường và registry hiểu nhầm completed.
8. **“Test after commit có thể chạy trong test @Transactional mặc định rollback.”** Không thể suy ra callback sẽ được gọi; cần commit thật.
9. **“Không thấy completed row nghĩa là thất bại.”** Sai nếu dùng completion mode `DELETE`.
10. **“Mọi exception đều nên retry vô hạn.”** Sai với payload hỏng, lỗi nghiệp vụ vĩnh viễn hoặc listener/target không còn tương thích.

## 15. Bài tập tình huống

Ứng dụng có ba module:

- `payment` lưu giao dịch thanh toán và phát `PaymentCaptured` trong transaction.
- `ledger` ghi sổ qua `@ApplicationModuleListener`.
- `receipt` gửi hóa đơn qua một `@ApplicationModuleListener` khác.

Sau khi transaction `payment` commit, `ledger` hoàn tất; `receipt` gọi nhà cung cấp email và timeout.

**Câu hỏi:**

1. Có nên rollback bản ghi thanh toán đã commit chỉ vì listener `receipt` timeout không?
2. Registry cần theo dõi trạng thái theo event hay theo từng listener target?
3. Nếu email provider có thể đã gửi email trước khi timeout, retry có nguy cơ gì?
4. Test chỉ kiểm tra `PublishedEvents` ở module `payment` có phát hiện lỗi receipt không?
5. Một listener bắt exception rồi return bình thường có thể gây lỗi quản lý publication ra sao?
6. Vì sao test registry phải có nhánh commit khi kiểm thử lỗi listener, thay vì chỉ assert rollback không để lại publication?

**Đáp án tham khảo:**

1. Transaction nguồn đã commit; listener sau commit lỗi không tự hoàn tác dữ liệu nguồn. Cần recovery/bù trừ theo nghiệp vụ nếu thật sự cần.
2. Theo **từng target**: publication của `ledger` có thể completed còn của `receipt` chưa completed.
3. Có thể gửi hóa đơn hai lần; cần idempotency key hoặc cơ chế chống trùng tương ứng.
4. Không. `PublishedEvents` chỉ xác nhận module nguồn đã phát event và payload phù hợp.
5. Registry có thể đánh dấu completed dù side effect chưa thành công, làm mất cơ hội retry từ trạng thái incomplete.
6. Chỉ rollback test có thể pass giả khi registry chưa được cấu hình hoặc không có listener. Nhánh commit với listener lỗi xác nhận publication thực sự được ghi nhận.

## 16. Checklist xử lý lỗi listener

- [ ] Xác định listener là đồng bộ, `BEFORE_COMMIT`, `AFTER_COMMIT` hay `@ApplicationModuleListener`.
- [ ] Phân biệt transaction nguồn đã commit với transaction riêng của listener.
- [ ] Event được phát trong transaction phù hợp và payload có khả năng serialize khi registry cần lưu bền vững.
- [ ] Registry có persistence starter, schema và transaction manager hoạt động.
- [ ] Listener không nuốt exception khiến một failure bị đánh dấu completed giả.
- [ ] Có test commit nguồn + listener lỗi; không chỉ có test rollback.
- [ ] Có assertion publication chưa completed theo đúng event/target và assertion database thực tế.
- [ ] Có test listener sửa lỗi rồi xử lý lại thành công, không gây side effect trùng.
- [ ] Retry có ngưỡng, backoff và phân loại lỗi; không retry vô hạn mọi incomplete.
- [ ] Với nhiều instance hoặc listener async, test và chính sách recovery xét đến đồng thời và thời gian xử lý.
- [ ] Event API/allowed dependencies được kiểm tra bằng `ApplicationModules.verify()`.
- [ ] `@ApplicationModuleTest`, integration test, serialization test và quality gate CI bao phủ đường lỗi.

**Kết luận:** Khi một publication listener thất bại, câu hỏi không chỉ là “có exception không”, mà là **exception xảy ra trước hay sau commit, target nào thất bại, publication có còn incomplete và side effect nào đã thực hiện**. Spring Modulith Event Publication Registry cung cấp cơ sở theo dõi và phục hồi theo target; thiết kế retry, idempotency, kiểm thử database và boundary test mới giúp luồng sự kiện đáng tin cậy trong thực tế.

### Tài liệu tham khảo

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listener, publication registry, completion và recovery.
- [EventPublicationRegistry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html): tra cứu và quản lý publication.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): pha xử lý của `@TransactionalEventListener`.

> Ghi chú: Những API trạng thái chi tiết hoặc resubmission phụ thuộc phiên bản Spring Modulith. Đối chiếu phiên bản ứng dụng trước khi dùng enum trạng thái, cách đánh dấu lỗi và các tùy chọn retry.
