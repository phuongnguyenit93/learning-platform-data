# Mock event publisher và giới hạn bằng chứng

## 1. Một lệnh verify không chứng minh cả luồng sự kiện

Trong một unit test Java, ta thường gặp:

~~~java
verify(publisher).publishEvent(any(OrderPlaced.class));
~~~

Lệnh này có giá trị: nó xác nhận code đang kiểm thử đã gọi `ApplicationEventPublisher.publishEvent(...)` trên **mock** với một đối tượng kiểu `OrderPlaced`. Nhưng nó **không** tự chứng minh:

- Spring đã phân phối sự kiện tới listener.
- Một listener `@EventListener` hoặc `@TransactionalEventListener` đã chạy.
- Transaction nguồn đã **commit** thay vì rollback.
- Listener `AFTER_COMMIT` đã thực thi sau khi dữ liệu bền vững.
- `@ApplicationModuleListener` bất đồng bộ đã hoàn tất.
- Event Publication Registry đã lưu hoặc đánh dấu hoàn tất một publication.
- Kafka/RabbitMQ/HTTP đã nhận integration event.
- Hệ thống bên ngoài đã tạo đúng một side effect, không trùng khi retry.

Đó là **giới hạn bằng chứng** của việc mock event publisher: test chứng minh **ý định phát** ở cấp một lời gọi Java, chứ không chứng minh toàn bộ cơ chế truyền và xử lý sự kiện.

Trong Spring Modulith, sự phân biệt này quan trọng vì một event có thể là hợp đồng giữa các application module; việc phát event thường diễn ra trong transaction, còn module nhận có thể xử lý sau commit, bất đồng bộ và có khả năng được retry. Test mock publisher chỉ quan sát được **một mắt xích**.

Bài thuộc chương **Mock và spy** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**. Học phần hướng đến kiểm chứng ranh giới kiến trúc với `ApplicationModules`, các quy tắc phụ thuộc giữa module, `@ApplicationModuleTest`, database, sự kiện và tích hợp; kết hợp chúng thành quality gate CI để ngăn phụ thuộc sai và hồi quy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu chính xác `verify(publisher).publishEvent(...)` **có và không có** giá trị chứng minh gì.
2. Viết unit test dùng `@Mock ApplicationEventPublisher`, `ArgumentCaptor` và Mockito verification để kiểm tra type/payload/điều kiện phát.
3. Tránh bẫy hai overload `publishEvent(Object)` và `publishEvent(ApplicationEvent)`.
4. Chọn `@ApplicationModuleTest` + `PublishedEvents` thay vì mock publisher khi muốn kiểm tra event được phát **qua Spring infrastructure thật**.
5. Phân biệt event được phát, transaction commit, listener sau commit, publication registry và integration event tới broker.
6. Thiết kế test **commit/rollback** có đối chứng và không khẳng định sai về `PublishedEvents`.
7. Dùng `@MockitoBean` đúng ranh giới module/I/O, không mock publisher để chữa các lỗi wiring/kiến trúc.
8. Xây dựng bộ test cho producer, receiver, contract, persistence, retry/idempotency và CI.

## 2. Thang bằng chứng: mỗi bài test chỉ chứng minh điều nó quan sát

| Mức | Công cụ/thiết lập | Điều có thể khẳng định | Điều chưa được khẳng định |
| --- | --- | --- | --- |
| **1. Method invocation** | Unit test, `@Mock ApplicationEventPublisher`, `verify`. | SUT đã gọi method của mock đúng số lần/đối số. | Spring event dispatch, DB, listener, commit. |
| **2. Event được phát trong Spring context** | `@ApplicationModuleTest` + `PublishedEvents`. | Spring publisher thật đã nhận event phù hợp. | Transaction đã commit, listener ngoài module đã xử lý. |
| **3. Commit/rollback của nguồn** | Spring-managed service + datasource thật, `TransactionTemplate` khi cần. | Dữ liệu nguồn commit/rollback theo kịch bản. | Listener async hoặc broker đã hoàn tất. |
| **4. Listener theo phase** | `@TransactionalEventListener(AFTER_COMMIT)` thật và test có commit. | Listener thuộc context đã nhận sau commit; không nhận khi rollback. | External I/O thành công và durable retry. |
| **5. Publication lifecycle** | Spring Modulith Event Publication Registry với store phù hợp. | Publication theo target được ghi nhận/chuyển trạng thái như mong đợi. | Broker/provider tạo đúng một business effect. |
| **6. Adapter/wire integration** | Broker test, HTTP fake server, Testcontainers, contract assertions. | Payload, routing, serialization/ack trong môi trường thử nghiệm. | Toàn hệ thống phân tán luôn exactly-once. |
| **7. Business outcome** | State bền vững, idempotency key, provider evidence. | Một invariant nghiệp vụ cụ thể được duy trì sau retry/recovery. | Mọi failure mode ngoài phạm vi test đều đã được chứng minh. |

**Không có một annotation nào thay thế tất cả các mức.** Với một bài unit test, kiểm tra lời gọi publisher là hoàn toàn hợp lý, miễn tên test và kết luận không nói quá. Với bài module integration test cần event thật, lại phải chuyển công cụ quan sát.

### 2.1. Một chuỗi xử lý được chia thành nhiều mốc

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders.OrderService
    participant DB as Orders Database
    participant Pub as ApplicationEventPublisher
    participant Rec as PublishedEvents
    participant Tx as Transaction manager
    participant Listener as AFTER_COMMIT listener
    participant GW as External gateway
    Client->>Orders: place(order)
    Orders->>DB: save(order)
    Orders->>Pub: publishEvent(OrderPlaced)
    Pub-->>Rec: Observe published event
    Orders-->>Tx: Method completes
    alt Transaction commits
        Tx->>DB: COMMIT
        Tx-->>Listener: AFTER_COMMIT callback
        Listener->>GW: Send / persist side effect
    else Transaction rolls back
        Tx->>DB: ROLLBACK
        Note over Listener,GW: AFTER_COMMIT callback is skipped
    end
~~~

Sơ đồ đơn giản hóa cơ chế Spring để làm rõ các mốc; listener đồng bộ `@EventListener` có thể chạy **ngay trong lúc `publishEvent` được gọi**. Listener `AFTER_COMMIT` lại chờ commit. Bộ quan sát `PublishedEvents` không được hiểu là chứng nhận mọi bước phía sau.

## 3. Event publisher trong Spring có hai overload

`ApplicationEventPublisher` công bố:

~~~java
void publishEvent(ApplicationEvent event);
void publishEvent(Object event);
~~~

Tùy phiên bản Spring Framework, một overload có thể được cài đặt qua default method hoặc cơ chế tương đương, nhưng ở góc độ Java **đây là hai signature có thể chọn khi gọi**.

Nếu event là record thường:

~~~java
public record OrderPlaced(UUID orderId) {}

publisher.publishEvent(new OrderPlaced(orderId));
~~~

Java chọn overload **`publishEvent(Object)`**, vì `OrderPlaced` không extends `ApplicationEvent`. Nếu event là subclass của `ApplicationEvent`, Java sẽ chọn overload cụ thể hơn.

Với Mockito, tránh assertion quá mơ hồ:

~~~java
// Không nên dùng khi cần biết overload chính xác.
verify(publisher).publishEvent(any());
~~~

`any()` generic có thể khiến Java chọn overload phù hợp nhất theo overload resolution, không phải overload mà production đã gọi; từ đó gây lỗi “Wanted but not invoked” khó hiểu.

Ưu tiên matcher có kiểu cụ thể:

~~~java
verify(publisher).publishEvent(any(OrderPlaced.class));
~~~

Hoặc dùng `ArgumentCaptor<OrderPlaced>` và kiểm tra payload. Với một record `OrderPlaced`, kiểu được truyền vào `publishEvent` rõ ràng là `Object`. **Không dùng `any(ApplicationEvent.class)` để bắt record payload không extends `ApplicationEvent`.**

### 3.1. Publisher là một abstraction của Spring, không phải broker

`ApplicationEventPublisher` chỉ là cổng **phát sự kiện ứng dụng** trong Spring `ApplicationContext`. Lời gọi đó tự nó không tương đương:

- Một Kafka record đã có offset.
- Một HTTP POST tới service ngoài.
- Một row trong outbox đã được commit.
- Một consumer đã acknowledge.

Muốn externalize event, phải có **adapter/event externalization configuration** và một test tích hợp riêng kiểm tra transport thực hoặc test harness.

## 4. Kiến trúc ví dụ: orders phát event, notifications nhận event

Giả sử ứng dụng Spring Boot có root package `com.example.shop`, hai application module `orders` và `notifications`:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   ├── package-info.java
│   ├── events
│   │   ├── OrderPlaced.java
│   │   └── package-info.java
│   └── internal
│       ├── OrderEntity.java
│       └── OrderRepository.java
└── notifications
    ├── package-info.java
    ├── OrderNotificationListener.java
    └── NotificationGateway.java
~~~

Mục tiêu thiết kế:

1. Module `orders` quản lý lệnh đặt hàng, persistence và phát `OrderPlaced`.
2. Module `notifications` phụ thuộc vào **API event được công bố** bởi `orders`, không inject `OrderRepository` hoặc `OrderService` nội bộ.
3. Module `notifications` lắng nghe event sau commit và gửi thông báo qua gateway thuộc trách nhiệm của chính nó.
4. Unit test `OrderService` có thể mock publisher; module test `orders` **không mock publisher**.
5. Test listener ở `notifications` hoặc integration test dùng event infrastructure thật, có thể mock **NotificationGateway** nếu chỉ cần cô lập I/O.

~~~mermaid
flowchart LR
    OT["orders.OrderService"] --> OR["orders.internal.OrderRepository"]
    OT --> PUB["ApplicationEventPublisher"]
    PUB --> EV["orders.events.OrderPlaced"]
    EV --> NL["notifications.OrderNotificationListener"]
    NL --> NG["notifications.NotificationGateway"]
    MT["Unit test orders"] -. "mock publisher" .-> PUB
    IT["@ApplicationModuleTest orders"] --> OT
    IT --> PE["PublishedEvents"]
~~~

## 5. Công bố event như một module API có chủ đích

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        Instant occurredAt
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(customerId);
        Objects.requireNonNull(occurredAt);
    }
}
~~~

Event là một record bất biến, chỉ chứa dữ liệu cần thiết. Không đưa `OrderEntity`, JPA proxy hoặc repository nội bộ vào payload của event chỉ vì unit test dễ verify.

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Trong ứng dụng có package module root `com.example.shop.orders`, named interface `events` công bố package event tới consumer. Nếu consumer chỉ được phụ thuộc sự kiện:

File `notifications/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders :: events")
package com.example.shop.notifications;
~~~

Như vậy `notifications` có thể nhận `OrderPlaced` qua API được công bố, nhưng không được trực tiếp dùng `orders.internal.OrderRepository`.

**Module producer không cần phụ thuộc vào listener:** `orders` chỉ import lớp event do chính nó sở hữu và `ApplicationEventPublisher`. Test producer `STANDALONE` không cần dựng mock listener ở module nhận.

## 6. Entity và repository thật của module orders

File `orders/internal/OrderEntity.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.util.Objects;
import java.util.UUID;

@Entity
public class OrderEntity {

    @Id
    private UUID id;
    private UUID customerId;

    protected OrderEntity() {} // Cho JPA.

    public OrderEntity(UUID id, UUID customerId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
    }

    public UUID getId() { return id; }
    public UUID getCustomerId() { return customerId; }
}
~~~

File `orders/internal/OrderRepository.java`:

~~~java
package com.example.shop.orders.internal;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.UUID;

public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {}
~~~

Đây là persistence của **module `orders`**. Trong unit test thuần, ta có thể mock repository. Trong `@ApplicationModuleTest` cần xác nhận dữ liệu thật, phải dùng repository/datasource thật.

## 7. OrderService thật và hai đường đi commit/rollback

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
import java.util.Objects;
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
    public void place(UUID orderId, UUID customerId) {
        saveAndPublish(orderId, customerId);
    }

    @Transactional
    public void placeAndFail(UUID orderId, UUID customerId) {
        saveAndPublish(orderId, customerId);

        // Lỗi sau save và publish, trước khi outer transaction commit.
        throw new IllegalStateException("Simulated rollback");
    }

    private void saveAndPublish(UUID orderId, UUID customerId) {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerId, "customerId");

        orders.save(new OrderEntity(orderId, customerId));
        publisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(), orderId,
                customerId, Instant.now()));
    }
}
~~~

**Lưu ý:** hai public methods có `@Transactional` và được gọi **qua bean Spring-managed proxy** trong module test. Helper `saveAndPublish` private được gọi khi transaction của public method đã bắt đầu. Nếu unit test dùng `new OrderService(...)`, không có proxy; annotation `@Transactional` không tự mở transaction.

`placeAndFail` là phương thức **chỉ phục vụ ví dụ rollback**. Trong code production, không tạo một public endpoint cố ý ném lỗi chỉ để viết test; hãy dùng tình huống thất bại thật của nghiệp vụ hoặc fixture thích hợp.

## 8. Unit test: mock publisher để xác minh ý định phát

Khi chỉ muốn bảo vệ orchestration của `OrderService`, unit test không cần Spring context:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class OrderPublisherUnitTests {

    @Mock OrderRepository repository;
    @Mock ApplicationEventPublisher publisher;

    @Test
    void asksPublisherToPublishOrderPlacedWithCorrectPayload() {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        var service = new OrderService(repository, publisher);

        service.place(orderId, customerId);

        ArgumentCaptor<OrderPlaced> captor =
                ArgumentCaptor.forClass(OrderPlaced.class);

        // Với OrderPlaced record, overload được chọn là publishEvent(Object).
        verify(publisher).publishEvent(captor.capture());

        OrderPlaced event = captor.getValue();
        assertThat(event.orderId()).isEqualTo(orderId);
        assertThat(event.customerId()).isEqualTo(customerId);
        assertThat(event.eventId()).isNotNull();
        assertThat(event.occurredAt()).isNotNull();
    }
}
~~~

Test này có ý nghĩa: nếu service đổi payload sai `orderId` hoặc không gọi publisher, nó thất bại. Nhưng trong test:

- `OrderRepository` là mock, nên `save` không ghi JPA database.
- `ApplicationEventPublisher` là mock, nên không có Spring event dispatch thực.
- `@Transactional` trên service **không có tác dụng** vì tự khởi tạo bằng `new`.
- Không có listener module ngoài, event registry hoặc broker nào được cấu hình.

**Tên test nên nói “asksPublisherToPublish...” thay vì “deliversEventToNotifications...”** vì đó mới là điều thực sự được kiểm chứng.

### 8.1. Kiểm tra repository cũng được yêu cầu lưu

Nếu unit test muốn chứng minh orchestration có cả lưu và phát:

~~~java
verify(repository).save(any(OrderEntity.class));
verify(publisher).publishEvent(any(OrderPlaced.class));
~~~

Cần import `OrderEntity` và `ArgumentMatchers.any`. Dù hai lời gọi đều xảy ra, test vẫn **không chứng minh dữ liệu đã commit**. Không dùng `InOrder(repository, publisher)` nếu thứ tự method invocation không phải hợp đồng; nếu cần chứng minh **chỉ publish sau commit**, `InOrder` trên hai mocks cũng không đủ.

### 8.2. Đếm invocation theo phạm vi unit test

~~~java
verify(publisher, times(1))
        .publishEvent(any(OrderPlaced.class));
~~~

Với Mockito, `verify(publisher).publishEvent(...)` mặc định tương đương `times(1)` đối với method/argument match. Điều này **không cấm** publisher nhận thêm loại event khác hoặc một `OrderPlaced` cho order khác nếu test không kiểm tra.

Nếu business contract yêu cầu đúng một `OrderPlaced` trong một command, dùng event captor và assertion cụ thể. Đừng suy ra “exactly-once giao message đến tất cả consumer” từ một `times(1)` trong một process.

## 9. Unit test nhánh invalid: không phát event

Vì service kiểm tra `orderId` và `customerId` trước khi lưu/phát, có thể viết:

~~~java
@Test
void invalidOrderIdDoesNotUseRepositoryOrPublisher() {
    var service = new OrderService(repository, publisher);
    UUID customerId = UUID.randomUUID();

    assertThatThrownBy(() -> service.place(null, customerId))
            .isInstanceOf(NullPointerException.class)
            .hasMessage("orderId");

    verifyNoInteractions(repository, publisher);
}
~~~

Đây là snippet thêm vào `OrderPublisherUnitTests`, với static imports:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;
~~~

**Đây là negative contract thực sự:** dữ liệu không hợp lệ phải bị chặn trước mọi side effect. `verifyNoInteractions` chỉ nói không có method invocation lên **hai mock** tại thời điểm assertion; nó không nói gì về HTTP client, DB hoặc listener khác không có trong unit test.

Nếu code thay đổi để kiểm tra dữ liệu sau `repository.save`, test này phát hiện hành vi không mong muốn. Nếu contract yêu cầu validate ở API layer khác, hãy chọn test ở đúng tầng để không bắt service thực thi một trách nhiệm chưa được giao.

## 10. Khi publisher mock ném exception

`publishEvent(...)` là method `void`, nên muốn mô phỏng nó ném exception dùng `doThrow`:

~~~java
@Test
void publisherFailurePropagatesFromService() {
    var service = new OrderService(repository, publisher);
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    doThrow(new IllegalStateException("Simulated publisher failure"))
            .when(publisher)
            .publishEvent(any(OrderPlaced.class));

    assertThatThrownBy(() ->
            service.place(orderId, customerId))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Simulated publisher failure");

    verify(repository).save(any(OrderEntity.class));
}
~~~

Cần static import `Mockito.doThrow`, `Mockito.any`, `assertThatThrownBy` và import `OrderEntity` như trên. **Không thể** dùng `when(publisher.publishEvent(...))` vì method trả về `void`.

Những gì test chứng minh:

1. Service không bắt/nuốt `IllegalStateException` từ mock publisher.
2. Lệnh `save` trên mock repository được gọi trước khi mock publisher ném lỗi.

Những gì **không chứng minh**:

- Database rollback khi event publish thất bại (không có database/transaction thật).
- Một listener thật có thể ném cùng exception trong pha nào.
- Spring đã thử ghi durable publication hoặc sẽ retry như thế nào.

Trong Spring, **listener đồng bộ** `@EventListener` có thể ném exception ngay trong lúc `publishEvent` chạy; listener `AFTER_COMMIT` và `@ApplicationModuleListener` có thời điểm/lifecycle khác. Một mock ném exception ngay tại publish **không mô phỏng trung thực mọi cơ chế này**.

## 11. Anti-pattern: mock publisher trong module integration test

Khi mục tiêu là chứng minh `OrderPlaced` được phát qua Spring thật, đoạn cấu hình sau là lựa chọn không phù hợp:

~~~java
@ApplicationModuleTest
class OrderEventTests {

    @MockitoBean
    ApplicationEventPublisher publisher;

    @Autowired OrderService service;

    @Test
    void looksLikeAnEventTest() {
        service.place(UUID.randomUUID(), UUID.randomUUID());
        verify(publisher).publishEvent(any(OrderPlaced.class));
    }
}
~~~

Đây là **ví dụ anti-pattern**, không phải một module test được khuyến nghị. `@MockitoBean` thay/thêm mock trong Spring context; việc Spring giải quyết `ApplicationEventPublisher` còn liên quan tới dependency đặc biệt của `ApplicationContext`, nên không dựa vào cấu hình này như một phép kiểm chứng chung cho mọi version/context.

Ngay cả nếu `OrderService` inject đúng mock và test pass, nó chỉ chứng minh **bean đã gọi mock**. Event infrastructure có thể bị bypass, `PublishedEvents` không còn quan sát đúng đường phát, listener không chạy và registry không được kiểm chứng.

**Cách sửa:** bỏ mock publisher, chạy `OrderService` thật trong `@ApplicationModuleTest`, dùng `PublishedEvents` cho producer; mock **collaborator ngoài module hoặc cổng I/O** nếu test cần cô lập hành vi khác.

### 11.1. Không cần mock listener ở module ngoài

`orders` chỉ phát `OrderPlaced`. Trong `@ApplicationModuleTest(STANDALONE)` thuộc package `orders`, bean listener ở `notifications` thường không được bootstrap. Do đó không có lý do khai báo `@MockitoBean NotificationListener` để “giữ test độc lập”.

Khi muốn kiểm tra listener, viết **test của module `notifications`** hoặc integration test nạp cả hai module và event infrastructure thật.

## 12. @ApplicationModuleTest + PublishedEvents: bằng chứng mạnh hơn

Module test cho `orders` có thể giữ service, JPA repository và publisher thật:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderPublicationModuleTests {

    @Autowired OrderService service;
    @Autowired OrderRepository repository;

    @Test
    void persistsOrderAndPublishesEvent(PublishedEvents events) {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        service.place(orderId, customerId);

        assertThat(repository.findById(orderId))
                .get()
                .satisfies(order ->
                        assertThat(order.getCustomerId())
                                .isEqualTo(customerId));

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.customerId()).isEqualTo(customerId);
                    assertThat(event.eventId()).isNotNull();
                    assertThat(event.occurredAt()).isNotNull();
                });
    }
}
~~~

Điều kiện cần: dự án đã có Spring Modulith test support, Spring Data JPA, test datasource, transaction manager và schema tương thích. Lớp test đặt trong package `orders` để Spring Modulith xác định scope. Không gắn `@Transactional` ở test class nếu cần service **commit transaction riêng** và kiểm tra thêm listener sau commit.

**Bằng chứng thu được:**

- `OrderService` và `OrderRepository` thật chạy bên trong Spring context hạn chế theo module.
- Dữ liệu order có thể được truy vấn qua JPA sau lời gọi service.
- `PublishedEvents` quan sát event đã được phát qua publisher thật.
- Event đúng loại, đúng `orderId`/`customerId` và có metadata cần thiết.

**Bằng chứng chưa có:** listener `notifications` đã nhận, registry đã completed, broker đã nhận hoặc khách hàng đã nhận thông báo. `STANDALONE` thường cố ý loại các module khác khỏi context.

### 12.1. Tránh assert mọi event của toàn context

Không nên:

~~~java
assertThat(events.ofType(OrderPlaced.class)).hasSize(1);
~~~

nếu test environment có các luồng khác tạo `OrderPlaced` độc lập. Khi kiểm tra một command, lọc theo **order ID riêng**:

~~~java
assertThat(events.ofType(OrderPlaced.class)
        .matching(OrderPlaced::orderId, orderId))
        .hasSize(1);
~~~

Điều này giảm nhiễu từ fixture, các listener test khác hoặc sự kiện phụ trợ. Dù vậy, mỗi test vẫn phải quản lý transaction, context và dữ liệu riêng phù hợp.

## 13. Trường hợp rollback: publishEvent đã gọi nhưng AFTER_COMMIT không chạy

Một ngộ nhận nguy hiểm:

> “Transaction rollback thì event chưa từng được publish, nên `PublishedEvents` phải rỗng.”

Trong service ví dụ:

~~~java
@Transactional
public void placeAndFail(UUID orderId, UUID customerId) {
    saveAndPublish(orderId, customerId);
    throw new IllegalStateException("Simulated rollback");
}
~~~

Lệnh `publisher.publishEvent(new OrderPlaced(...))` đã **được gọi trước khi exception xuất hiện**. Rollback sau đó không thể “xóa” lời gọi Java đã xảy ra. Vì vậy:

- Mockito mock publisher có thể ghi nhận invocation ngay cả khi transaction sẽ rollback.
- `PublishedEvents` có thể đã ghi nhận event phát trong context.
- Lệnh ghi database thuộc transaction nguồn được rollback (nếu không có giao tác độc lập xen vào).
- Listener `@TransactionalEventListener(AFTER_COMMIT)` không được thực thi cho transaction đó.
- Listener đồng bộ `@EventListener` có thể **đã chạy** trong lúc publish; nếu nó gửi HTTP/email ngay, rollback DB không thu hồi side effect ngoài.

### 13.1. Ba mệnh đề cần kiểm tra riêng

| Mệnh đề | Kịch bản rollback sau publish | Công cụ |
| --- | --- | --- |
| `publishEvent` có từng được gọi? | **Có**, theo code ví dụ. | Unit verify hoặc `PublishedEvents` quan sát lời gọi phát. |
| Dữ liệu order có commit không? | **Không** nếu Spring transaction rollback đúng. | Query repository/datasource sau transaction. |
| Listener `AFTER_COMMIT` có chạy không? | **Không** cho giao tác rollback. | Listener probe/integration test với positive control commit. |

Không dùng một assertion `verify(publisher)` để suy luận cả ba mệnh đề. Đặc biệt, **không assert `PublishedEvents.isEmpty()` chỉ vì rollback** nếu code đã phát event trước khi lỗi.

### 13.2. Test rollback với database thật

Thêm vào lớp `OrderPublicationModuleTests`:

~~~java
@Test
void rolledBackOrderDoesNotPersist(
        PublishedEvents publishedEvents) {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    assertThatThrownBy(() ->
            service.placeAndFail(orderId, customerId))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Simulated rollback");

    assertThat(repository.existsById(orderId)).isFalse();

    // ĐỪNG suy ra event chưa từng được phát.
    // publishedEvents có thể vẫn thấy OrderPlaced cho orderId này.
    // Callback AFTER_COMMIT cần được test bằng listener thật.
}
~~~

Thêm static import `assertThatThrownBy`. Biến `publishedEvents` hiện diện để nhắc về việc quan sát event; có thể bỏ khỏi tham số test nếu không cần truy vấn. **Điểm được chứng minh trong test này chỉ là rollback của row order**.

## 14. Kiểm tra listener AFTER_COMMIT bằng test probe thật

Để có bằng chứng listener sau commit **không chạy khi rollback** và **chạy khi commit**, hãy dùng một bean test-only nhận `OrderPlaced` bằng `@TransactionalEventListener`. Đừng mock publisher.

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ApplicationModuleTest
@Import(OrderCommitProbeTests.ProbeConfiguration.class)
class OrderCommitProbeTests {

    @Autowired OrderService service;
    @Autowired OrderRepository repository;
    @Autowired CommitProbe probe;

    @Test
    void committedOrderInvokesAfterCommitListener() {
        UUID orderId = UUID.randomUUID();

        service.place(orderId, UUID.randomUUID());

        assertThat(repository.existsById(orderId)).isTrue();
        assertThat(probe.sawCommit(orderId)).isTrue();
    }

    @Test
    void rolledBackOrderDoesNotInvokeAfterCommitListener() {
        UUID orderId = UUID.randomUUID();

        assertThatThrownBy(() ->
                service.placeAndFail(orderId, UUID.randomUUID()))
                .isInstanceOf(IllegalStateException.class);

        assertThat(repository.existsById(orderId)).isFalse();
        assertThat(probe.sawCommit(orderId)).isFalse();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ProbeConfiguration {
        @Bean CommitProbe commitProbe() {
            return new CommitProbe();
        }
    }

    static class CommitProbe {
        private final Set<UUID> committed =
                ConcurrentHashMap.newKeySet();

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void on(OrderPlaced event) {
            committed.add(event.orderId());
        }

        boolean sawCommit(UUID orderId) {
            return committed.contains(orderId);
        }
    }
}
~~~

**Vì sao probe này có giá trị?** Nó đăng ký một **listener thật** trong test context, chỉ ghi nhận callback `AFTER_COMMIT`. Hai test đối chứng chứng minh cả điều kiện dương (commit thì callback chạy) lẫn điều kiện âm (rollback thì không). Nếu chỉ có test rollback không thấy callback, test có thể xanh vì listener chưa được đăng ký — positive control giúp bắt lỗi đó.

`CommitProbe` dùng `Set` thread-safe và order ID riêng để giảm nhiễu từ Spring context cache. Ví dụ giả định default `@TransactionalEventListener` đồng bộ, **không thêm `@Async`**; khi listener thật bất đồng bộ, cần chờ theo điều kiện.

**Điều kiện rất quan trọng:** không bọc cả lớp test bằng `@Transactional` tự rollback cuối method, vì `OrderService` có thể join transaction test khiến callback `AFTER_COMMIT` không xảy ra giữa các assertions.

### 14.1. @Transactional trên test thay đổi toàn bộ bằng chứng

Nếu dùng:

~~~java
@ApplicationModuleTest
@Transactional
class MisleadingCommitTest {
    // Spring Test có thể rollback transaction test sau method.
}
~~~

thì `service.place(...)` thường tham gia outer transaction, không tự commit lúc method trả về. Một assertion listener chưa được gọi tại thời điểm đó **không chứng minh** phase được cấu hình đúng.

Với test cần điều khiển mốc giao tác có thể dùng `TransactionTemplate`, `TestTransaction` hoặc service `@Transactional` qua Spring proxy mà **không có transaction test bao ngoài**.

## 15. So sánh @EventListener, @TransactionalEventListener và @ApplicationModuleListener

| Loại listener | Thời điểm thường gặp | Khi publish rồi rollback | Test cần gì? |
| --- | --- | --- | --- |
| `@EventListener` đồng bộ | Ngay trong luồng publish với multicaster mặc định đồng bộ. | **Có thể đã chạy**; exception có thể truyền ngược publisher. | Spring event dispatch thật và assertion hành vi. |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Trước commit của transaction. | Có thể chạy nếu transaction đến giai đoạn before-commit; không phải AFTER_COMMIT. | Transaction thật, kiểm tra phase. |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit thành công. | Không chạy. | Commit-vs-rollback positive/negative controls. |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Sau rollback. | Có thể chạy khi rollback. | Transaction điều khiển rõ. |
| `@ApplicationModuleListener` | Meta-annotation của Spring Modulith cho xử lý event theo transaction, thường async và transaction mới. | Thông thường không xử lý sau rollback transaction nguồn. | Nạp receiver, commit thật, chờ callback/side effect. |

Cần tính tới cấu hình custom `ApplicationEventMulticaster`, `@Async`, `fallbackExecution` và phiên bản framework: các yếu tố ấy có thể thay đổi timing/dispatch. **Không dùng Mockito mock publisher để xác nhận các semantics này.**

### 15.1. Receiver mẫu dùng @ApplicationModuleListener

File `notifications/NotificationGateway.java`:

~~~java
package com.example.shop.notifications;

import java.util.UUID;

public interface NotificationGateway {
    void sendOrderConfirmation(UUID orderId, UUID eventId);
}
~~~

File `notifications/OrderNotificationListener.java`:

~~~java
package com.example.shop.notifications;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    private final NotificationGateway gateway;

    OrderNotificationListener(NotificationGateway gateway) {
        this.gateway = gateway;
    }

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        gateway.sendOrderConfirmation(
                event.orderId(), event.eventId());
    }
}
~~~

Trong test của `notifications`, có thể dùng `@MockitoBean NotificationGateway` để **không gửi email thật**, trong khi listener và cơ chế event chạy thật. Như vậy test chứng minh lời gọi của listener tới gateway trong một event flow, nhưng vẫn cần test adapter/provider riêng nếu muốn chứng minh email thực sự được gửi.

Nếu `NotificationGateway` có implementation thực, hãy bảo đảm test cô lập nó đúng theo bean name/qualifier hoặc thay tại port. Trong module test `notifications`, event nguồn có thể được kích hoạt bằng `Scenario` hoặc test fixture phát event trong transaction; **không gọi trực tiếp `listener.on(event)` rồi nói đã test `AFTER_COMMIT`**.

## 16. Scenario/Awaitility: chờ kết quả của listener, không chỉ method call

`@ApplicationModuleListener` thường chạy bất đồng bộ; một test kiểu:

~~~java
publisher.publishEvent(event);
verify(gateway).sendOrderConfirmation(orderId, eventId);
~~~

có thể fail vì listener chưa kịp xử lý, hoặc pass khi gateway đã được gọi nhưng side effect/database completion chưa xong.

Khi test receiver thật, ưu tiên chờ **trạng thái nghiệp vụ**:

~~~java
await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            assertThat(notificationRepository
                    .existsByOrderId(orderId))
                    .isTrue();
        });
~~~

Đây là **snippet integration test**, yêu cầu repository thật, imports Awaitility/`Duration`, dữ liệu test và event đã được phát trong transaction commit. Spring Modulith cũng cung cấp `Scenario` để diễn đạt stimulate-event-and-wait trong module test.

Nếu mục tiêu chỉ là kiểm tra listener gọi gateway đúng payload, có thể dùng Mockito `verify(..., timeout(...))` ở receiver test, nhưng hãy nói chính xác rằng bằng chứng chỉ là **gateway được gọi**:

~~~java
verify(gateway, timeout(2_000))
        .sendOrderConfirmation(orderId, eventId);
~~~

`timeout` có thể trả ngay khi invocation đầu tiên thỏa điều kiện; nó **không** chứng minh không có lời gọi trùng sau đó. Với retry/recovery, cần idempotency và integration assertions.

## 17. Event Publication Registry: không xuất hiện trong publisher mock

Spring Modulith có Event Publication Registry để ghi nhận những publication hướng tới các transactional event listener và theo dõi chúng đã hoàn tất hay chưa. Tùy cấu hình và event publication store đang dùng, registry có thể hỗ trợ khôi phục incomplete publications.

Khi test chỉ dùng:

~~~java
@Mock ApplicationEventPublisher publisher;

verify(publisher).publishEvent(any(OrderPlaced.class));
~~~

không có `ApplicationContext` thực phân phối sự kiện, nên **không có bằng chứng** về:

- Target listener nào được phát hiện.
- Publication record đã được tạo trong cùng transaction nguồn.
- Rollback có xóa/không commit record liên quan hay không.
- Listener đã được gọi và trả về thành công để đánh dấu complete.
- Publication thất bại có còn incomplete và có được retry/recover không.

### 17.1. Các trạng thái cần tách

~~~mermaid
flowchart TD
    A["ApplicationEventPublisher.publishEvent"] --> B{"Transaction outcome"}
    B -->|"Rollback"| R["Không có AFTER_COMMIT delivery"]
    B -->|"Commit"| C["Publication durable theo store/config"]
    C --> D["Target listener receives event"]
    D -->|"Success"| E["Publication marked complete"]
    D -->|"Failure"| F["Publication remains incomplete"]
    F --> G["Recovery / resubmit"]
    G --> D
~~~

Sơ đồ là **mô hình khái niệm**, không khẳng định mọi application luôn có durable store hoặc retry tự động. Tính bền vững phụ thuộc vào starter, registry, transaction manager, loại publication store và cấu hình resubmission của dự án.

### 17.2. Bài test registry cần làm gì?

Một integration test có persistence registry thật nên có ít nhất:

1. **Control commit:** phát event trong transaction commit, target được ghi nhận; listener hoàn tất thì publication được đánh dấu hoàn tất.
2. **Listener failure:** một target listener ném lỗi; publication tương ứng còn incomplete theo contract của store/config.
3. **Rollback nguồn:** phát event rồi transaction rollback; record cùng transaction nguồn không tồn tại bền vững nếu storage transactionally enlisted đúng.
4. **Recovery:** kích hoạt cơ chế resubmission được cấu hình và kiểm tra completion, đồng thời xác minh side effect không nhân đôi.
5. **Multi-target:** một event gửi tới nhiều target, trạng thái của từng target độc lập.

Không giả định “một event = một publication row” khi có nhiều listener. **Publication lifecycle là theo target**, còn event ID nghiệp vụ là khóa liên kết/replay/idempotency khác.

### 17.3. Đừng tạo giả định về registry từ một test unit

Ngay cả khi `verify(publisher, times(1))` pass, registry có thể không có target nào, có nhiều target, chưa ghi vào store, hoặc listener thất bại. Những dữ liệu ấy **không thể được suy ra từ method invocation**.

## 18. Integration event: gửi ra Kafka/HTTP cần test transport riêng

Một application event `OrderPlaced` có thể được chuyển thành **integration event** cho một service khác thông qua adapter/event externalization:

~~~mermaid
flowchart LR
    A["orders.OrderService"] --> B["publishEvent(OrderPlaced)"]
    B --> C["Spring Modulith event handling"]
    C --> D["Outbound externalization adapter"]
    D --> E["OrderPlacedMessageV1 JSON"]
    E --> F["Kafka / AMQP / HTTP"]
    F --> G["External consumer"]
~~~

Test mock `ApplicationEventPublisher` chặn ngay ở đầu chuỗi và **không đi tới outbound adapter**. Test `PublishedEvents` chứng minh event nội bộ có mặt, **chưa** chứng minh mapping/routing/serialization/transport.

Một outbound integration test phải kiểm tra:

| Thành phần | Cần kiểm chứng |
| --- | --- |
| **Selection** | Event nào được externalize, event nào giữ nội bộ. |
| **Mapping** | Chuyển từ `OrderPlaced` nội bộ sang public message DTO đúng version. |
| **Routing** | Topic/exchange/URL đúng, partition key/correlation ID phù hợp. |
| **Serialization** | JSON/Avro/Protobuf schema, timezone/UUID/currency rõ ràng. |
| **Transaction/commit** | Không tạo delivery bên ngoài cho nghiệp vụ rollback theo thiết kế. |
| **Failure/retry** | Lỗi broker/network không làm mất publication cần retry. |
| **Idempotency** | Consumer có thể xử lý duplicate với event ID ổn định. |

**Không đồng nhất** `ApplicationEventPublisher.publishEvent` với việc producer Kafka được gọi. Giữ publisher thật và dùng broker Testcontainers hoặc fake transport phù hợp; khi muốn test riêng mapper/adapter, có thể mock **gateway transport**, không thay event bus của producer.

## 19. “Exactly once” là ba câu hỏi khác nhau

| Câu hỏi | Có thể kiểm tra bằng |
| --- | --- |
| `OrderService` gọi publisher một lần trong unit test? | `verify(publisher, times(1))`. |
| `OrderService` phát một `OrderPlaced` cho order ID trong module test? | `PublishedEvents.ofType(...).matching(...).hasSize(1)`. |
| Consumer chỉ tạo một business effect dù event được giao lại? | Database unique constraint, idempotency marker, provider/reconciliation integration test. |

Ngay cả khi producer chỉ phát **một lần**, hệ thống event-driven có thể thực hiện lại listener do:

- Transaction listener đã xử lý side effect nhưng lỗi trước khi completion được ghi.
- Broker gửi lại message sau consumer restart.
- Network timeout khiến sender không biết request bên ngoài đã thành công chưa.
- Cơ chế replay/recovery của Event Publication Registry.

Một event cần `eventId` ổn định qua retry/replay; consumer lưu marker hoặc sử dụng idempotency key tại provider. **Mockito verification trong một test process không bao phủ vòng đời phân tán**.

### 19.1. Khi nào nên mock gateway ở receiver?

Ở test riêng `notifications`, `@MockitoBean NotificationGateway` là hợp lý nếu mục tiêu là listener nhận đúng `orderId`, `eventId` và xử lý exception/retry. Nhưng nó chỉ khẳng định **ý định gửi** qua gateway Java. Muốn chứng minh gửi email/HTTP thực, phải test adapter bằng fake server hoặc provider test environment.

Sự khác nhau tương tự bài học này: **mock một boundary làm bằng chứng dừng tại boundary ấy**.

## 20. @MockitoBean, @Mock và @MockitoSpyBean trong bài toán event

| Công cụ | Phạm vi | Dùng đúng khi | Cảnh báo |
| --- | --- | --- | --- |
| `@Mock ApplicationEventPublisher` | Unit test thuần, không Spring context. | Chỉ cần verify publish method/payload. | Không có Spring dispatch, DB/transaction. |
| `@MockitoBean ExternalGateway` | Spring Test context. | Cô lập I/O bên ngoài ở producer/receiver test. | Không kiểm chứng implementation gateway. |
| `@MockitoBean ApplicationEventPublisher` | Spring context. | Hiếm khi thật sự cần; không phù hợp với test sự kiện end-to-end trong Spring. | Có thể làm lệch đường phân phối event và khiến kết luận sai. |
| `@MockitoSpyBean Listener` | Spring context có real bean. | Quan sát real listener cụ thể khi thật sự cần. | Real behavior/side effects vẫn chạy; không thay commit/registry assertions. |
| `PublishedEvents` | Spring Modulith module test. | Quan sát event thật được phát. | Không chứng minh listener completion. |
| `Scenario` + DB side effect | Spring Modulith module/integration test. | Chờ phản ứng event và kết quả bền vững. | Cần giao tác/fixture phù hợp. |

### 20.1. Spring Framework version và bean override

`@MockitoBean` và `@MockitoSpyBean` thuộc Spring Framework 6.2+ (ví dụ Spring Boot 3.4+). Các dự án Spring Boot cũ có thể dùng `@MockBean`/`@SpyBean` trong package Boot test; các annotation cũ bị deprecated từ Boot 3.4 để chuyển sang API của Framework.

Trong `@ApplicationModuleTest(STANDALONE)`, mock public API ngoài module có thể được tạo khi implementation không được bootstrap nhờ cơ chế **REPLACE_OR_CREATE** mặc định của `@MockitoBean`. Ngược lại, `@MockitoSpyBean` cần **bean thật đã tồn tại** để wrap, không chữa được việc module ngoài không được nạp.

Đừng viết `@MockitoBean(enforceOverride = true)` khi chính mục tiêu là tạo mock cho bean vắng mặt do `STANDALONE`; tùy chọn này yêu cầu target bean tồn tại để thay.

## 21. Kiểm chứng ranh giới kiến trúc bằng ApplicationModules

Mock publisher không bảo vệ được kiến trúc module. Giả sử `notifications` import `orders.internal.OrderRepository` thay vì chỉ nhận `orders.events.OrderPlaced`: một test Mockito vẫn có thể pass, nhưng module dependency bị vi phạm.

Architecture gate:

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

`ApplicationModules.verify()` kiểm tra cycle, access tới package không được công bố và quy tắc `allowedDependencies` theo mô hình Spring Modulith. Nó **không** kiểm tra event đã publish, listener đã xử lý hoặc Kafka đã nhận. Vì thế architecture test và event behavior/integration tests phải cùng tồn tại.

### 21.1. Không inject trực tiếp listener của module nhận để “dễ verify”

Một producer service kiểu:

~~~java
class OrderService {
    private final NotificationService notifications;
}
~~~

chỉ để producer có thể gọi `notifications.send(...)` rồi Mockito verify sẽ làm coupling trực tiếp tăng. Nếu nghiệp vụ chỉ cần thông báo sự kiện, công bố `OrderPlaced` là cách giảm phụ thuộc. Tránh thay đổi architecture chỉ để có một mock dễ kiểm tra.

## 22. Các lỗi suy luận thường gặp

### 22.1. “verify publishEvent = event đã được delivery”

~~~java
verify(publisher).publishEvent(any(OrderPlaced.class));
~~~

**Sai kết luận:** chỉ chứng minh lời gọi tới mock. Dùng `PublishedEvents`, listener/registry và broker integration test theo mức cần thiết.

### 22.2. “Đã gọi publisher thì chắc chắn commit”

Publisher có thể được gọi **trong transaction chưa commit**. Rollback sau publish không thu hồi lời gọi Java. Assert commit bằng database và test transaction.

### 22.3. “PublishedEvents rỗng nếu transaction rollback”

**Không phải quy tắc chung.** Nếu code đã publish trước rollback, `PublishedEvents` có thể quan sát event. `AFTER_COMMIT` listener không chạy mới là điều cần kiểm tra khi commit bị hủy.

### 22.4. “Producer test chứng minh consumer hoàn tất”

`@ApplicationModuleTest(STANDALONE)` của `orders` thường không nạp `notifications`. Cần test receiver/integration.

### 22.5. “Mock publisher giúp module test đáng tin hơn”

Trong test cần event thật, mock publisher làm giảm phạm vi bằng chứng. Mock public dependency ngoài module nếu cần; giữ infrastructure event thật.

### 22.6. “verifyNoMoreInteractions chứng minh không còn event”

`verifyNoMoreInteractions(publisher)` chỉ kiểm tra interaction chưa verify **tại thời điểm hiện tại** trên mock. Không chứng minh callback async/broker không có event khác sau đó.

### 22.7. “InOrder save → publish chứng minh after-commit”

Thứ tự method calls không bằng transaction commit. Cần listener `AFTER_COMMIT` có test dương/âm và repository thật.

### 22.8. “Một lần publish = một lần side effect”

Consumer có thể retry/replay. Idempotency phải được thiết kế và kiểm tra ở nơi ghi side effect.

### 22.9. “@MockitoSpyBean listener là giải pháp kiểm thử delivery”

Spy listener vẫn chạy real logic và có thể gửi I/O thật; verify invocation không chứng minh completion/registry. Dùng gateway mock ở receiver và test flow/side effect đúng tầng.

### 22.10. “Event record tự động là integration contract”

Event nội bộ chưa chắc phù hợp làm public message. Externalization cần mapping/version/schema/transport tests.

## 23. Ma trận kiểm thử cho quality gate CI

| Gate | Mục tiêu | Công cụ | Lỗi có thể phát hiện |
| --- | --- | --- | --- |
| **Unit producer** | Đúng payload và gọi publisher khi hợp lệ. | `@Mock ApplicationEventPublisher`, captor/verify. | Quên publish, truyền sai ID. |
| **Unit negative** | Input lỗi không save/publish. | `verifyNoInteractions`, exception assertion. | Side effect trước validation. |
| **Module producer** | Lưu order, phát event thật. | `@ApplicationModuleTest`, JPA và `PublishedEvents`. | Sai dữ liệu, thiếu event, duplicate trong phạm vi test. |
| **Transaction rollback** | Không commit order khi lỗi. | Spring proxy và datasource thật. | Rollback không đúng. |
| **AFTER_COMMIT phase** | Callback chạy khi commit, không chạy khi rollback. | Test-only transactional listener có positive control. | Listener phase sai hoặc transaction test không commit. |
| **Receiver module** | Xử lý event và gọi gateway với đúng payload. | `@ApplicationModuleTest`, `Scenario`, `@MockitoBean` gateway. | Mapping sai, không xử lý event. |
| **Publication Registry** | Publication incomplete/completed/recovery đúng. | Store JDBC/JPA thật và integration scenarios. | Lost publication, completion sai, retry lỗi. |
| **Adapter contract** | Public message/routing/headers/schema đúng. | Mapper tests, fake server/broker Testcontainers. | Wire contract không tương thích. |
| **Idempotency** | Replay không nhân đôi effect. | DB constraint/marker, provider sandbox. | Duplicate email/reservation/charge. |
| **Architecture** | Producer không phụ thuộc consumer, receiver chỉ dùng event API. | `ApplicationModules.verify()`. | Import internal, cycle, allowedDependencies sai. |
| **Boot/wiring smoke** | App có beans/registrations thật. | `DIRECT_DEPENDENCIES` hoặc `@SpringBootTest`. | Mock che thiếu bean/config runtime. |

**Chiến lược CI:** Unit và architecture tests chạy nhanh trên pull request; module tests có database test cũng nên chạy thường xuyên nếu chi phí phù hợp. Registry, broker và external adapter tests có thể nằm ở integration stage chuyên biệt, nhưng phải là gate cho thay đổi liên quan contract, transaction và reliability.

### 23.1. Kết quả test âm tính cần có đối chứng

Nếu test nói listener không chạy khi rollback, phải có case **listener thực sự chạy khi commit**. Nếu không, test có thể xanh vì listener chưa được đăng ký, phase chưa cấu hình hoặc context thiếu module. Đây là nguyên tắc “positive control” quan trọng khi kiểm tra **không có side effect**.

### 23.2. Quy tắc chống flaky

- Dùng order ID/event ID riêng trong mỗi test.
- Không đo bằng `Thread.sleep` cố định nếu có callback async.
- Chờ điều kiện observable bằng `Scenario` hoặc Awaitility.
- Quản lý reset mock, dữ liệu database, event store và broker riêng; Mockito reset **không xóa state ngoài mock**.
- Không chạy song song các test chia sẻ cùng context/mock/registry nếu chưa thiết kế isolation.
- Không bọc test cần commit thật trong `@Transactional` rollback tự động.

## 24. Quy trình debug khi “event không tới listener”

Một phương pháp kiểm tra tuần tự:

1. **Producer có chạy đúng nhánh không?** Unit test có thể `verify(publisher)` hoặc capture payload.
2. **Có phát qua Spring context thật không?** Chạy `@ApplicationModuleTest` và kiểm tra `PublishedEvents`; bỏ `@MockitoBean ApplicationEventPublisher`.
3. **Transaction có commit không?** Query database sau lời gọi và xác nhận không bị test transaction rollback.
4. **Listener có được nạp không?** Xác định `STANDALONE`/dependencies hoặc test receiver; kiểm tra bean registration.
5. **Phase nào?** `@EventListener` đồng bộ, `AFTER_COMMIT` hay `@ApplicationModuleListener` bất đồng bộ? Có `fallbackExecution`/custom multicaster không?
6. **Listener có chạy và thất bại không?** Kiểm tra exception, logs/test side effect; chờ async đúng cách.
7. **Registry có target/store không?** Xác minh cấu hình persistence và trạng thái incomplete/completed sau transaction.
8. **External adapter có externalize không?** Kiểm tra event selection, mapping, route và wire-level send.
9. **Consumer có xử lý trùng hoặc lỗi schema không?** Kiểm tra contract version, idempotency và recovery.
10. **Kiến trúc có đúng không?** Chạy `ApplicationModules.verify()`, không sửa bằng mock nội bộ.

Đừng nhảy từ bước 1 tới kết luận “Kafka hỏng” hoặc “Spring Modulith làm mất event”. Mỗi tầng có một phép kiểm chứng riêng.

## 25. Bài tập thực hành

Một hệ thống Spring Modulith có:

- `checkout`: lưu `CheckoutEntity` rồi phát `CheckoutCompleted`.
- `loyalty`: listener sau commit ghi điểm thưởng vào database.
- `notifications`: listener async gửi email qua `EmailGateway`.
- `integration`: externalize `CheckoutCompleted` thành message version `v1` tới broker.

Team đang có test:

~~~java
@ExtendWith(MockitoExtension.class)
class CheckoutTests {
    @Mock CheckoutRepository repository;
    @Mock ApplicationEventPublisher publisher;

    @Test
    void checkoutIsDelivered() {
        var service = new CheckoutService(repository, publisher);
        service.complete(checkoutId);

        verify(publisher).publishEvent(
                any(CheckoutCompleted.class));
    }
}
~~~

### Câu hỏi

1. Test trên thực sự chứng minh điều gì? Tên `checkoutIsDelivered` có phù hợp không?
2. Nếu muốn kiểm tra event payload có `checkoutId`, `amount` và `eventId` đúng, dùng Mockito thế nào?
3. Nếu `CheckoutCompleted` là record thường, nên tránh `any()` không định kiểu vì sao?
4. `verify(publisher, times(1))` có chứng minh loyalty points chỉ được ghi một lần không?
5. Nếu `complete` gọi publisher rồi transaction rollback, `PublishedEvents` có nhất thiết rỗng không?
6. Muốn biết listener `AFTER_COMMIT` không chạy khi rollback, cần test kiểu gì?
7. Muốn biết `notifications` có gọi `EmailGateway` với dữ liệu đúng sau commit, test đặt ở đâu?
8. Khi test module `checkout`, có nên `@MockitoBean ApplicationEventPublisher` không?
9. Muốn chứng minh message `CheckoutCompletedV1` tới broker đúng topic/schema, test gì là phù hợp?
10. Nếu `notifications` import `checkout.internal.CheckoutRepository`, test nào phát hiện vấn đề?

### Đáp án tham khảo

1. Chỉ chứng minh `CheckoutService` **gọi mock publisher** với một `CheckoutCompleted`. Tên đúng hơn là `requestsPublicationOfCheckoutCompleted`.
2. Dùng `ArgumentCaptor<CheckoutCompleted>`, `verify(publisher).publishEvent(captor.capture())`, assert từng field; hoặc verify bằng đối tượng expected nếu immutable/equality rõ.
3. Vì Java chọn overload `publishEvent(Object)` cho record, còn `any()` có thể chọn overload `ApplicationEvent` cụ thể hơn gây mismatch.
4. Không. Loyalty listener có thể retry sau failure; cần idempotency và database test phía receiver.
5. Không. `publishEvent` đã được gọi trước rollback, nên `PublishedEvents` có thể quan sát event dù không có callback sau commit.
6. Test listener thật `@TransactionalEventListener(AFTER_COMMIT)` trong context có transaction, positive control commit và negative control rollback.
7. Ở module `notifications` hoặc integration test nạp listener, commit event nguồn, chờ async và có thể mock **EmailGateway** tại I/O boundary.
8. Không khi mục tiêu là event thực; giữ publisher thật, dùng `PublishedEvents`.
9. Integration test event externalization/adapter với broker test hoặc fake transport, assert message DTO version, topic/route, key, headers và payload.
10. `ApplicationModules.of(...).verify()` bảo vệ named interfaces/`allowedDependencies`; mock không sửa dependency sai.

## 26. Checklist trước khi mock ApplicationEventPublisher

- [ ] Đã viết rõ mục tiêu: **method invocation**, Spring event publication, transaction, listener, registry hay external delivery?
- [ ] Nếu chỉ unit test orchestration, `@Mock ApplicationEventPublisher` là lựa chọn chấp nhận được.
- [ ] Event record được kiểm tra bằng `ArgumentCaptor`/typed matcher, không dùng `any()` gây nhầm overload.
- [ ] Kiểm tra đúng type, `orderId`/`eventId`/payload, số invocation theo phạm vi unit test.
- [ ] Nhánh input lỗi có negative assertion không gọi publisher khi đó là contract.
- [ ] Không dùng mock publisher để suy ra database commit, listener execution hoặc broker delivery.
- [ ] Nếu cần `@ApplicationModuleTest` cho producer, giữ publisher, service và repository thật.
- [ ] Dùng `PublishedEvents` có lọc business ID riêng, không chỉ đếm mọi event của context.
- [ ] Phân biệt **đã gọi publishEvent** với **đã commit transaction**.
- [ ] Không assert `PublishedEvents` rỗng chỉ vì transaction rollback sau lệnh publish.
- [ ] Có test listener `AFTER_COMMIT` với cả commit positive control và rollback negative control khi phase quan trọng.
- [ ] Không bọc test cần commit thật trong `@Transactional` rollback mặc định.
- [ ] Với `@ApplicationModuleListener` async, chờ theo điều kiện qua `Scenario`/Awaitility.
- [ ] Producer `STANDALONE` không cần mock receiver listener ngoài module.
- [ ] Receiver test giữ listener thật, có thể mock/fake **external gateway** để cô lập I/O.
- [ ] Nếu cần reliability, test Event Publication Registry theo target, incomplete/completed/recovery và store phù hợp.
- [ ] Nếu externalize event, test mapping/version/routing/serialization/headers với broker hoặc fake transport.
- [ ] Không kết luận exactly-once business effect chỉ từ `times(1)`.
- [ ] Consumer có idempotency key/unique marker và test replay/retry.
- [ ] Public event API được công bố bằng named interface; không rò JPA entity vào payload.
- [ ] `ApplicationModules.verify()` được đưa vào CI để bảo vệ phụ thuộc module.
- [ ] Có provider/receiver contract và wiring integration tests không bị mocks che khuất.
- [ ] CI quản lý dữ liệu, context cache, registry state và async isolation.

**Kết luận:** Mock `ApplicationEventPublisher` hữu ích khi mục tiêu chỉ là kiểm tra **một lời gọi phát event trong unit test**. Bằng chứng dừng lại ở mock: không có Spring dispatch, không có bảo đảm commit, không có listener completion, durable publication hay external delivery. Trong Spring Modulith, hãy nâng cấp công cụ theo mục tiêu: `@ApplicationModuleTest` + `PublishedEvents` để quan sát producer thật; transaction/listener tests để kiểm chứng `AFTER_COMMIT`; registry/integration tests để bảo vệ reliability và transport; `ApplicationModules.verify()` để giữ ranh giới kiến trúc. Khi từng tầng nói đúng điều nó chứng minh, bộ test vừa nhanh, vừa tránh cảm giác an toàn giả.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `PublishedEvents`, `Scenario` và bootstrap modes.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional module listener, event publication, registry và recovery.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): module API, named interface và dependency rules.
- [Spring Framework — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): overload `publishEvent(ApplicationEvent)` và `publishEvent(Object)`.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): listener phases `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`.
- [Spring Framework — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean override trong Spring Test.
- [Mockito — Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/Mockito.html): `verify`, `ArgumentCaptor`, `any`, `doThrow` và verification modes.

> Ghi chú tương thích: ví dụ giả định Spring Framework 6.2+, Spring Modulith, Spring Data JPA và JUnit 5/Mockito có cấu hình test phù hợp. Repository schema, test datasource, transaction manager, Event Publication Registry store, broker và external gateway cần được thiết lập theo dự án thực tế. Bài thuộc bước biên soạn STEP_4; chưa chạy Gradle hoặc vòng Content QA chuyên môn.
