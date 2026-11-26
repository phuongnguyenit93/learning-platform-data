# Kiểm tra event được publish đúng một lần

## 1. “Đúng một lần” đang nói đến điều gì?

Trong ứng dụng Spring Modulith, một yêu cầu phổ biến là **mỗi chuyển trạng thái nghiệp vụ hợp lệ chỉ phát đúng một sự kiện tương ứng**. Ví dụ: khi đơn hàng chuyển từ `CREATED` sang `COMPLETED`, module `orders` cần phát một `OrderCompleted`. Nếu người dùng gửi lại request hoặc service bị gọi lặp, hệ thống không nên phát thêm `OrderCompleted` cho cùng lần hoàn tất.

Tuy nhiên, câu “event được publish đúng một lần” có thể được hiểu theo ba tầng khác nhau:

| Tầng | Câu hỏi kiểm chứng | Kỹ thuật phù hợp |
| --- | --- | --- |
| **Publication tại nguồn** | Use case có gọi phát đúng **một** `OrderCompleted` cho chuyển trạng thái này không? | `@ApplicationModuleTest` + `PublishedEvents`, test unit với mock publisher. |
| **Ghi nhận/giao tới listener** | Khi có nhiều transactional listener, từng publication có được ghi nhận và theo dõi đúng không? | Integration test với Event Publication Registry và database. |
| **Tác động nghiệp vụ ở consumer** | Dù nhận lại event hoặc retry, listener có cập nhật dữ liệu/gửi yêu cầu ra ngoài đúng số lần cho phép không? | Integration test, khóa duy nhất, idempotency key, kiểm tra dữ liệu cuối cùng. |

Ba tầng **không tương đương**. Một event được phát đúng một lần nhưng được giao lại cho listener sau lỗi vẫn có thể làm consumer chạy nhiều lần. Ngược lại, một listener idempotent có thể chỉ ghi một bản ghi dù producer đã phát trùng hai event. Vì thế bài kiểm thử phải nói rõ mình đang bảo vệ tầng nào.

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, mục tiêu là rèn kỹ năng kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, kiểm thử hành vi module bằng `@ApplicationModuleTest`, kiểm thử sự kiện/database và tích hợp các kiểm tra vào quality gate trong CI. Bài này tập trung vào **số lần phát event tại nguồn**, sau đó mở rộng để tránh hiểu nhầm với exactly-once delivery.

### Sau bài học, bạn có thể

1. Viết assertion đếm chính xác event theo **kiểu sự kiện và khóa nghiệp vụ** bằng `PublishedEvents`.
2. Kiểm tra trường hợp gọi một lần, gọi lặp, điều kiện không hợp lệ và nhiều đơn hàng khác nhau.
3. Bảo vệ việc phát một event cho một chuyển trạng thái bằng guard nghiệp vụ, transaction và chiến lược xử lý đồng thời.
4. Phân biệt “đã được publish” với “transaction đã commit” và “listener đã xử lý thành công”.
5. Kiểm tra idempotency của listener khi publication được xử lý lại.
6. Đưa test kiến trúc, test module phát và integration test vào quality gate CI.

## 2. Mô hình ví dụ: một sự kiện cho một lần hoàn tất đơn hàng

Giả sử ứng dụng có package gốc `com.example.shop`. Theo cách phát hiện module mặc định của Spring Modulith, các package con trực tiếp `orders` và `notifications` là application module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   ├── events
│   │   ├── OrderCompleted.java
│   │   └── package-info.java
│   └── internal
│       ├── OrderEntity.java
│       └── OrderJpaRepository.java
└── notifications
    ├── OrderCompletedListener.java
    └── package-info.java
~~~

Yêu cầu nghiệp vụ:

- Đơn hàng mới có trạng thái chưa hoàn tất.
- Lần gọi `complete(orderId)` đầu tiên chuyển trạng thái sang hoàn tất và phát **một** event.
- Lần gọi tiếp theo với cùng `orderId`, nếu đơn hàng đã hoàn tất, không tạo chuyển trạng thái mới và **không phát event mới**.
- Với `orderId` không tồn tại, use case báo lỗi và không phát `OrderCompleted`.
- Hai đơn hàng khác nhau hoàn tất hợp lệ thì **mỗi đơn có một event**, tổng cộng hai event.

~~~mermaid
flowchart TD
    A["orders.complete(orderId)"] --> B{"Đơn hàng tồn tại?"}
    B -->|"Không"| E["Báo lỗi; không publish"]
    B -->|"Có"| C{"Đã COMPLETED?"}
    C -->|"Có"| F["Trả về; không publish thêm"]
    C -->|"Chưa"| D["Chuyển trạng thái"]
    D --> G["publishEvent(OrderCompleted)"]
    G --> H["Transaction commit"]
~~~

Sơ đồ mô tả đường nghiệp vụ đơn giản. Nếu transaction thất bại sau khi `publishEvent` đã được gọi, một test đếm event vẫn có thể thấy lời gọi phát đó; điều này **không có nghĩa trạng thái đơn hàng đã commit**.

### 2.1. Event payload nên đủ để nhận diện sự kiện

File `orders/events/OrderCompleted.java`:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderCompleted(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {
    public OrderCompleted {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

Ba trường có ý nghĩa khác nhau:

- `orderId`: khóa nghiệp vụ cho phép lọc các event liên quan đến **một đơn hàng**.
- `eventId`: định danh một **lần phát event nghiệp vụ**; nếu consumer nhận lại cùng event, giá trị này phải được giữ nguyên.
- `occurredAt`: thời điểm nguồn tạo event; không phải bằng chứng listener đã xử lý.

Không dùng `eventId` mới được sinh trong **mỗi lần nhận lại** ở listener. Một thông điệp được retry phải giữ danh tính sự kiện để consumer phát hiện đã xử lý.

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Named interface công bố kiểu event như API của module `orders`. Việc phát event giúp `orders` không cần gọi trực tiếp service nội bộ của `notifications`, nhưng module nhận vẫn phụ thuộc vào kiểu `OrderCompleted` được công bố.

## 3. Chặn phát trùng từ chính nghiệp vụ

Đếm một event trong test chỉ xác minh hành vi hiện tại. Muốn **ngăn phát trùng khi service được gọi lặp**, cần quy tắc nghiệp vụ rõ ràng.

### 3.1. Entity quản lý chuyển trạng thái

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
    private boolean completed;

    protected OrderEntity() {} // Constructor cho JPA.

    public OrderEntity(UUID id) {
        this.id = Objects.requireNonNull(id);
    }

    public boolean completeIfNeeded() {
        if (completed) {
            return false;
        }
        completed = true;
        return true;
    }
}
~~~

`completeIfNeeded()` trả về `true` **chỉ khi có chuyển trạng thái**. Không nên để service phát event vô điều kiện rồi kỳ vọng listener tự xử lý trùng cho mọi tình huống.

### 3.2. Repository đọc có khóa khi cần chống gọi đồng thời

File `orders/internal/OrderJpaRepository.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.UUID;

public interface OrderJpaRepository
        extends JpaRepository<OrderEntity, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select o from OrderEntity o where o.id = :id")
    Optional<OrderEntity> findByIdForUpdate(@Param("id") UUID id);
}
~~~

`PESSIMISTIC_WRITE` yêu cầu database khóa hàng đang xử lý khi transaction hoạt động. Hai yêu cầu hoàn tất **cùng đơn hàng** sẽ không được đồng thời đọc một trạng thái chưa hoàn tất rồi cùng phát event, miễn là mọi đường đi nghiệp vụ liên quan tuân thủ cùng cơ chế khóa, transaction hoạt động và database thực sự hỗ trợ lock. Với hệ thống khác có thể dùng optimistic locking cùng retry hợp lệ, cập nhật có điều kiện hoặc cơ chế idempotency key.

Lưu ý rằng lớp `OrderJpaRepository` là `public` ở mức Java để service import được, nhưng vẫn nằm trong package **nội bộ của module `orders`**; module khác không nên import nó.

### 3.3. Service chỉ phát event khi state chuyển thành công

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderCompleted;
import com.example.shop.orders.internal.OrderJpaRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.NoSuchElementException;
import java.util.UUID;

@Service
public class OrderService {

    private final OrderJpaRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(OrderJpaRepository orders,
                        ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void complete(UUID orderId) {
        var order = orders.findByIdForUpdate(orderId)
                .orElseThrow(() ->
                        new NoSuchElementException("Order not found"));

        if (!order.completeIfNeeded()) {
            return; // Đã hoàn tất: không tạo event mới.
        }

        // JPA dirty checking lưu thay đổi của entity khi commit.
        events.publishEvent(new OrderCompleted(
                UUID.randomUUID(), orderId, Instant.now()));
    }
}
~~~

Mã trên dựa trên **JPA managed entity** và transaction thật. `@Transactional` hoạt động khi lời gọi đi qua Spring proxy. Trong test cần có datasource, transaction manager, schema JPA và các Spring Modulith test dependency tương ứng.

**Tại sao không đưa `publishEvent` ra ngoài `if`?** Vì mỗi lần API bị gọi lặp đều sẽ tạo thêm event dù không có sự thật nghiệp vụ mới. **Tại sao lock quan trọng?** Vì guard `if (completed)` một mình không bảo vệ khi hai transaction cùng đọc dữ liệu cũ; race condition có thể làm cả hai quyết định phát.

Khi dùng database phân tán, retry sau lỗi, optimistic locking hoặc lệnh `UPDATE ... WHERE completed=false`, thiết kế bảo vệ concurrency có thể khác; hãy kiểm chứng đúng transaction semantics của hệ thống.

## 4. Kiểm tra publish đúng một lần bằng @ApplicationModuleTest

Spring Modulith cung cấp `PublishedEvents` để quan sát các event được phát trong một module test. Đặt test ở package `com.example.shop.orders` để `@ApplicationModuleTest` bootstrap module `orders`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderCompleted;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderJpaRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ApplicationModuleTest
class OrderPublicationTests {

    @Autowired OrderService orders;
    @Autowired OrderJpaRepository repository;

    @Test
    void publishesOneOrderCompletedForFirstTransition(
            PublishedEvents events) {
        UUID id = UUID.randomUUID();
        repository.saveAndFlush(new OrderEntity(id));

        orders.complete(id);

        assertThat(events.ofType(OrderCompleted.class)
                .matching(OrderCompleted::orderId, id))
                .hasSize(1);
    }

    @Test
    void repeatedCallDoesNotPublishAnotherEvent(
            PublishedEvents events) {
        UUID id = UUID.randomUUID();
        repository.saveAndFlush(new OrderEntity(id));

        orders.complete(id);
        orders.complete(id);

        assertThat(events.ofType(OrderCompleted.class)
                .matching(OrderCompleted::orderId, id))
                .hasSize(1);
    }

    @Test
    void unknownOrderDoesNotPublishCompletedEvent(
            PublishedEvents events) {
        UUID id = UUID.randomUUID();

        assertThatThrownBy(() -> orders.complete(id))
                .isInstanceOf(java.util.NoSuchElementException.class);

        assertThat(events.ofType(OrderCompleted.class)
                .matching(OrderCompleted::orderId, id))
                .isEmpty();
    }

    @Test
    void countsOneEventPerOrderWhenTwoOrdersComplete(
            PublishedEvents events) {
        UUID first = UUID.randomUUID();
        UUID second = UUID.randomUUID();
        repository.saveAndFlush(new OrderEntity(first));
        repository.saveAndFlush(new OrderEntity(second));

        orders.complete(first);
        orders.complete(second);

        assertThat(events.ofType(OrderCompleted.class)
                .matching(OrderCompleted::orderId, first))
                .hasSize(1);
        assertThat(events.ofType(OrderCompleted.class)
                .matching(OrderCompleted::orderId, second))
                .hasSize(1);
        assertThat(events.ofType(OrderCompleted.class))
                .hasSize(2);
    }
}
~~~

### 4.1. Assertion nào thực sự chứng minh “một lần”?

Trọng tâm là:

~~~java
assertThat(events.ofType(OrderCompleted.class)
        .matching(OrderCompleted::orderId, id))
        .hasSize(1);
~~~

- `events.ofType(OrderCompleted.class)` chỉ lấy những sự kiện đúng kiểu.
- `matching(OrderCompleted::orderId, id)` lọc đúng **đơn hàng đang test**, tránh đếm nhầm event của đơn khác.
- `hasSize(1)` thất bại nếu không có event hoặc có từ **hai event phù hợp trở lên**.

Không chỉ viết `isNotEmpty()`: cả một và nhiều sự kiện đều qua được assertion này. Cũng không chỉ dùng `ofType(...).hasSize(1)` trong một test xử lý nhiều đơn hàng, vì event của đơn khác không thuộc đối tượng cần xác minh.

### 4.2. Vì sao phải test gọi lặp?

Test “gọi một lần rồi thấy một event” sẽ **không bắt được** lỗi:

~~~java
@Transactional
public void complete(UUID id) {
    var order = orders.findByIdForUpdate(id).orElseThrow();
    order.completeIfNeeded();

    // Lỗi: bất kể order đã completed hay chưa, vẫn phát event.
    events.publishEvent(new OrderCompleted(
            UUID.randomUUID(), id, Instant.now()));
}
~~~

Lần gọi đầu tiên vẫn tạo đúng một event nên test happy path vẫn pass. Test gọi `complete(id)` **hai lần** rồi đếm tổng một event sẽ bắt được hồi quy này.

Nếu nghiệp vụ cho phép nhiều lần hoàn tất sau khi **mở lại đơn hàng**, yêu cầu cần đổi từ “một event cho mỗi order ID mãi mãi” thành **một event cho mỗi chuyển trạng thái hợp lệ**. Khi đó payload nên có `transitionId`, version hoặc correlation key khác để test đúng vòng đời, tránh khóa cứng sai quy tắc nghiệp vụ.

### 4.3. Kiểm tra field event thay vì chỉ đếm

Đếm đúng một event chưa bảo đảm payload đúng. Có thể thêm assertion với AssertJ:

~~~java
assertThat(events.ofType(OrderCompleted.class)
        .matching(OrderCompleted::orderId, id))
        .singleElement()
        .satisfies(event -> {
            assertThat(event.eventId()).isNotNull();
            assertThat(event.occurredAt()).isNotNull();
        });
~~~

`singleElement()` vừa xác nhận chỉ có một phần tử phù hợp, vừa cho phép kiểm tra payload. Với các nghiệp vụ có số phiên bản/trạng thái, nên assert thêm những field ấy.

## 5. Test đếm publication không đồng nghĩa transaction đã commit

Giả sử code phát event **bên trong transaction** rồi transaction rollback:

~~~java
transactions.executeWithoutResult(status -> {
    publisher.publishEvent(new OrderCompleted(
            UUID.randomUUID(), orderId, Instant.now()));
    status.setRollbackOnly();
});
~~~

Lời gọi `publishEvent` **đã xảy ra** nên một bộ quan sát event ở thời điểm phát có thể vẫn đếm được event. Nhưng dữ liệu thay đổi trong transaction nguồn đã rollback, và một `@TransactionalEventListener(AFTER_COMMIT)` sẽ **không được gọi**.

Vì vậy cần xác định ý nghĩa của assertion:

| Assertion | Chứng minh được | Chưa chứng minh được |
| --- | --- | --- |
| `PublishedEvents` có đúng một event | Use case có **một lần publish phù hợp** trong test. | Transaction nguồn đã commit; listener xử lý thành công. |
| Kiểm tra trạng thái đơn hàng trong database sau service call trả về | Kết quả lưu dữ liệu sau transaction của lời gọi hiện tại. | Event có được ghi nhận bền vững cho listener hay không. |
| Event Publication Registry có publication cho target | Có bản ghi theo dõi giao event cho listener. | Side effect ngoài hệ thống đã thực hiện đúng một lần. |
| Listener có bản ghi xử lý với unique key | Consumer đã lưu dấu công việc trong database. | Email/API bên ngoài chưa bao giờ nhận trùng khi có lỗi giữa chừng. |

Không nên gắn `@Transactional` lên **toàn bộ test class** ở mục 4 nếu mục tiêu là để mỗi lần gọi `orders.complete(id)` tạo transaction rồi commit độc lập. Spring Test có thể mở một transaction bao ngoài test và rollback khi kết thúc; khi đó transaction của service thường tham gia transaction test và không có commit thật giữa hai lời gọi.

Nếu cần chủ động kiểm tra commit và rollback, viết một test riêng **không có transaction bao ngoài**, dùng `TransactionTemplate` hoặc `TestTransaction` với commit được điều khiển rõ ràng.

### 5.1. Dùng TransactionTemplate để minh họa hai pha khác nhau

Đoạn sau đặt trong một test đã được cấu hình `PlatformTransactionManager`, `ApplicationEventPublisher` và `PublishedEvents`. Nó xác nhận **một lần phát được quan sát ngay cả khi rollback**:

~~~java
@Test
void publishingBeforeRollbackIsStillAnAttempt(
        PublishedEvents events) {

    UUID orderId = UUID.randomUUID();
    var transaction = new TransactionTemplate(transactionManager);

    transaction.executeWithoutResult(status -> {
        publisher.publishEvent(new OrderCompleted(
                UUID.randomUUID(), orderId, Instant.now()));
        status.setRollbackOnly();
    });

    assertThat(events.ofType(OrderCompleted.class)
            .matching(OrderCompleted::orderId, orderId))
            .hasSize(1);
}
~~~

Đây là **ví dụ bổ sung**, không phải test class hoàn chỉnh: các bean và import cần được khai báo. Kết quả này không phải lỗi framework. Bộ quan sát `PublishedEvents` đang trả lời câu hỏi “đã publish bao nhiêu lần trong test”, còn rollback/commit là một phép đo khác.

Đối với yêu cầu publication bền vững sau commit, hãy dùng integration test với registry/persistence và listener thật; chỉ dựa vào `PublishedEvents` là chưa đủ.

## 6. Gọi đồng thời: test tuần tự chưa bảo vệ race condition

Đây là lỗi có thể xảy ra khi chỉ có guard kiểm tra trạng thái mà **không có khóa hoặc cơ chế kiểm soát cập nhật đồng thời**:

~~~text
Transaction A                  Transaction B
Đọc completed=false           Đọc completed=false
Kiểm tra: cần hoàn tất        Kiểm tra: cần hoàn tất
Đổi completed=true            Đổi completed=true
publish OrderCompleted        publish OrderCompleted
COMMIT                         COMMIT
=> Có thể phát hai event cho một chuyển trạng thái logic.
~~~

Test gọi `orders.complete(id)` hai lần **tuần tự** có thể vẫn pass, vì lời gọi thứ hai thấy dữ liệu đã completed. Để phát hiện lỗi đồng thời, cần integration test cho hai lời gọi chạy song song thật.

**Cách xây dựng test cạnh tranh có ý nghĩa:**

1. Tạo một order trong database test thật, trạng thái `completed=false`.
2. Khởi động hai luồng qua một cổng đồng bộ như `CountDownLatch` để chúng đồng thời gọi `orders.complete(sameId)`.
3. Để mỗi lời gọi đi qua Spring service proxy và có transaction **riêng**; không chạy cả hai trong transaction test bao ngoài.
4. Chờ cả hai luồng kết thúc bằng `Future.get`/timeout, kiểm tra exception theo chính sách đã định.
5. Assert database có một đơn hàng đã completed và số sự kiện được ghi nhận cho **cùng lần chuyển trạng thái** không vượt một. Dùng một listener ghi dấu bền vững, outbox/registry hoặc counter đồng bộ có kiểm soát; không mặc định `PublishedEvents` thu mọi event phát từ các thread khác theo cùng phạm vi test.
6. Chạy test với engine database hỗ trợ đúng kiểu lock/isolation dự kiến của production; H2 hoặc mock repository có thể không phản ánh lock behavior của PostgreSQL/MySQL.

Với ví dụ ở mục 3, `PESSIMISTIC_WRITE` khiến hai transaction truy cập cùng hàng theo thứ tự. Transaction thứ hai đọc trạng thái sau khi transaction thứ nhất đã commit, sau đó trả về mà không publish thêm.

Nếu dùng optimistic locking, một lời gọi có thể thất bại do conflict. Cần định nghĩa nó sẽ retry như thế nào; retry không được phát thêm một event mới cho cùng chuyển trạng thái đã thành công. Lưu ý test đếm publish **trước commit** có thể quan sát cả attempt bị rollback; để khẳng định một **event bền vững sau commit**, hãy kết hợp kiểm tra registry/outbox và trạng thái nghiệp vụ.

## 7. Một event, nhiều target: không nhầm số publication trong registry

Giả sử `orders` phát **một** `OrderCompleted`, còn hai listener:

~~~java
// Module inventory
@ApplicationModuleListener
void on(OrderCompleted event) {
    // Cập nhật tồn kho.
}

// Module notifications
@ApplicationModuleListener
void on(OrderCompleted event) {
    // Gửi thông báo.
}
~~~

Nếu Event Publication Registry được cấu hình với persistence và cả hai listener có mặt trong application context, có thể có **hai target publication** cho cùng một business event. Đây là hành vi đúng:

~~~mermaid
flowchart LR
    S["orders.complete(id)"] --> E["1 OrderCompleted"]
    E --> R["Event Publication Registry"]
    R --> P1["Publication #1: inventory"]
    R --> P2["Publication #2: notifications"]
    P1 --> C1["COMPLETED"]
    P2 --> C2["Chưa hoàn tất / cần xử lý lại"]
~~~

**Không dùng số dòng registry để khẳng định số lần service gọi publish.** Một event có nhiều target có thể tạo nhiều publication. Và khi target không nằm trong context test, registry có thể không tạo publication nào cho target đó dù service đã phát event.

Test đúng nên tách:

- Ở **module nguồn**, `@ApplicationModuleTest` + `PublishedEvents` khẳng định số event được phát cho một khóa nghiệp vụ.
- Ở **integration test** có listener và registry thật, xác nhận publication theo từng target, trạng thái completed/incomplete và khả năng đọc lại event sau commit.
- Ở **module nhận**, test tác động nghiệp vụ của từng listener, bao gồm việc xử lý lặp.

Registry hỗ trợ theo dõi publication và có cơ chế recovery khi được cấu hình; nó **không cam kết “exactly once” ở mọi tầng**. Listener có thể bị gọi lại sau lỗi hay restart; số lần callback chạy có thể lớn hơn số lần event ban đầu được phát.

## 8. Consumer phải idempotent nếu event có thể được xử lý lại

Xem một `OrderCompleted(eventId, orderId, ...)`. Nếu listener xử lý thành công nhưng tiến trình dừng trước khi registry đánh dấu completed, hệ thống có thể resubmit publication và listener nhận **lại cùng event**.

Một chiến lược phổ biến là ghi dấu `eventId` cùng transaction với thay đổi database của module nhận.

### 8.1. Ví dụ lưu dấu xử lý

File `notifications/ProcessedEvent.java`:

~~~java
package com.example.shop.notifications;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

import java.util.UUID;

@Entity
class ProcessedEvent {

    @Id
    private UUID eventId;

    protected ProcessedEvent() {}

    ProcessedEvent(UUID eventId) {
        this.eventId = eventId;
    }
}
~~~

File `notifications/ProcessedEventRepository.java`:

~~~java
package com.example.shop.notifications;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.UUID;

interface ProcessedEventRepository
        extends JpaRepository<ProcessedEvent, UUID> {}
~~~

File `notifications/OrderCompletionHandler.java`:

~~~java
package com.example.shop.notifications;

import com.example.shop.orders.events.OrderCompleted;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderCompletionHandler {

    private final ProcessedEventRepository processed;
    private final NotificationLogRepository logs;

    OrderCompletionHandler(ProcessedEventRepository processed,
                           NotificationLogRepository logs) {
        this.processed = processed;
        this.logs = logs;
    }

    @Transactional
    public void handle(OrderCompleted event) {
        if (processed.existsById(event.eventId())) {
            return;
        }

        // Ghi kết quả nghiệp vụ và dấu xử lý trong cùng transaction.
        logs.save(new NotificationLog(event.orderId()));
        processed.save(new ProcessedEvent(event.eventId()));
    }
}
~~~

`NotificationLogRepository` và `NotificationLog` là các thành phần mẫu của module `notifications` cần triển khai với database thật. Ví dụ minh họa đường **xử lý tuần tự**: sau lần đầu thành công, xử lý lại cùng `eventId` sẽ không ghi thêm log.

**Giới hạn cạnh tranh:** Hai transaction đồng thời đều có thể thấy `existsById=false` trước khi ghi dấu. Phải dùng unique constraint (khóa chính `eventId`), transaction bao quanh cả cập nhật nghiệp vụ lẫn marker, và xử lý đúng lỗi constraint/rollback theo database để không commit side effect trùng. Nếu gửi email hoặc gọi API ngoài, giao dịch database **không tự rollback** side effect ấy; dùng idempotency key ở phía provider hoặc một cơ chế outbox/dispatch phù hợp.

### 8.2. Listener theo transaction trong Spring Modulith

~~~java
package com.example.shop.notifications;

import com.example.shop.orders.events.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderCompletedListener {

    private final OrderCompletionHandler handler;

    OrderCompletedListener(OrderCompletionHandler handler) {
        this.handler = handler;
    }

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        handler.handle(event);
    }
}
~~~

`@ApplicationModuleListener` có ngữ nghĩa transactional listener, xử lý bất đồng bộ và transaction riêng trong Spring Modulith. Việc gọi thêm một service `@Transactional` với propagation mặc định `REQUIRED` thường tham gia transaction đang có; cần đối chiếu cấu hình transaction thực tế. Module `notifications` chỉ nên import event type thuộc API công khai của `orders`, không import repository nội bộ từ module nguồn.

File `notifications/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.example.shop.notifications;
~~~

### 8.3. Kiểm thử xử lý trùng ở consumer

Trong integration/module test có `OrderCompletionHandler` và database:

~~~java
@Test
void processingSameEventTwiceCreatesOneLog() {
    UUID id = UUID.randomUUID();
    var event = new OrderCompleted(
            UUID.randomUUID(), id, Instant.now());

    handler.handle(event);
    handler.handle(event); // Retry của chính eventId.

    assertThat(logs.countByOrderId(id)).isEqualTo(1);
    assertThat(processed.existsById(event.eventId())).isTrue();
}
~~~

Đây là **đoạn test minh họa**: cần test fixture, inject `handler`, `logs`, `processed`, các import JUnit/AssertJ/Java và repository `countByOrderId`. Kiểm tra số bản ghi nghiệp vụ **kết hợp** marker idempotency; một assertion về marker đơn lẻ chưa chứng minh side effect không trùng.

Đoạn test xử lý lặp không thay thế test của module phát. Một producer có thể phát trùng hai event với **hai `eventId` khác nhau** nhưng cùng `orderId`; consumer chặn trùng theo event ID riêng lẻ sẽ coi chúng là hai sự kiện hợp lệ. Bởi vậy, cần cả **guard nghiệp vụ ở producer** và **idempotency ở consumer**.

## 9. Kiểm chứng ranh giới module với ApplicationModules

Trong Spring Modulith, việc dùng event không có nghĩa mọi loại phụ thuộc bị xóa. `notifications` import `OrderCompleted` từ `orders.events`, vì vậy package `events` phải là API được công bố, và `allowedDependencies` của module nhận phải cho phép quan hệ này.

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` phát hiện các vi phạm phụ thuộc kiến trúc được Spring Modulith kiểm tra, ví dụ import một implementation class trong `orders.internal` từ `notifications` hoặc chu trình module không hợp lệ.

**Đừng suy ra rằng test kiến trúc pass tức là event được phát đúng một lần.** `verify()` kiểm tra cấu trúc phụ thuộc, không thực thi `OrderService.complete`. Ngược lại, test `PublishedEvents` pass cũng không tự chứng minh module listener chỉ dùng public API. Hai nhóm test bổ sung cho nhau.

## 10. Các anti-pattern làm phép đếm event sai hoặc thiếu giá trị

### 10.1. Chỉ kiểm tra có ít nhất một event

~~~java
// Quá yếu: hai hoặc ba event vẫn pass.
assertThat(events.ofType(OrderCompleted.class)).isNotEmpty();
~~~

Nếu yêu cầu là **chính xác một** event cho đơn hàng hiện tại, phải lọc `orderId` rồi `hasSize(1)`.

### 10.2. Chỉ kiểm tra một lần gọi đầu tiên

~~~java
orders.complete(id);
assertThat(events.ofType(OrderCompleted.class)
        .matching(OrderCompleted::orderId, id)).hasSize(1);
~~~

Test này hữu ích nhưng chưa chứng minh idempotency. Thêm test **gọi lặp** để bắt lỗi phát lại khi entity đã `completed`.

### 10.3. Đếm tất cả event cùng kiểu của cả test suite

Nếu các test share context, dữ liệu hoặc listener test không được cô lập, đếm mọi `OrderCompleted` mà không lọc theo ID có thể gây lỗi ngẫu nhiên. Tạo `UUID` mới cho mỗi test, lọc chính xác trường nghiệp vụ và làm sạch fixture database khi cần.

`PublishedEvents` của Spring Modulith được dùng để quan sát event thuộc ngữ cảnh một test; không tự thay thế cho cơ chế lưu trữ bền vững hoặc bộ đếm cross-thread trong test concurrency.

### 10.4. Dựa vào số dòng của registry để đếm lời gọi publish

Một event có nhiều transactional listener có thể tạo nhiều publication, mỗi publication theo target riêng. Số dòng không phải số lần gọi `publishEvent`.

### 10.5. Assert callback async hoàn tất ngay

~~~java
orders.complete(id);
assertThat(notificationLogs.countByOrderId(id)).isEqualTo(1);
~~~

Với `@ApplicationModuleListener`, callback có thể chạy sau trên executor khác. Assertion ngay lập tức có thể flaky. Hãy chờ theo điều kiện bằng API `Scenario` của Spring Modulith hoặc Awaitility nếu dự án có dependency:

~~~java
await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(notificationLogs.countByOrderId(id))
                        .isEqualTo(1));
~~~

Đây là đoạn assertion của integration test. Trong bài toán chống trùng, còn cần gửi lại event/trigger retry rồi kiểm tra side effect vẫn không tăng.

### 10.6. Chặn trùng chỉ bằng biến trong bộ nhớ

~~~java
private final Set<UUID> processed = ConcurrentHashMap.newKeySet();
~~~

Bộ nhớ trong một instance không giải quyết trường hợp restart hoặc nhiều replica. Một bộ nhớ đệm có thể hữu ích cho tối ưu, nhưng quyết định chống trùng nghiệp vụ cần cơ chế nhất quán và bền vững phù hợp.

### 10.7. Nuốt lỗi listener rồi coi hoàn tất

~~~java
@ApplicationModuleListener
void on(OrderCompleted event) {
    try {
        externalService.call(event);
    } catch (Exception ignored) {
        // Sai nếu muốn registry tiếp tục xem đây là thất bại để retry.
    }
}
~~~

Nếu listener trả về bình thường, hạ tầng có thể đánh dấu publication hoàn tất dù side effect đã thất bại. Thay vì bỏ qua exception, hãy xử lý lỗi theo chính sách, phân loại lỗi có thể retry và bảo đảm registry/monitoring phản ánh đúng kết quả.

## 11. Đề xuất ma trận test trong CI

| Test | Tình huống | Assertion chính |
| --- | --- | --- |
| **Module publication test** | Hoàn tất một order mới. | `PublishedEvents` có đúng một `OrderCompleted` theo `orderId`. |
| **Idempotent command test** | Gọi `complete(id)` hai lần tuần tự. | Tổng event theo ID vẫn bằng một. |
| **Negative-path test** | Order không tồn tại hoặc quy tắc nghiệp vụ từ chối. | Không có `OrderCompleted` phù hợp. |
| **Multiple-aggregate test** | Hoàn tất hai order riêng biệt. | Mỗi order có một event, tổng hai event. |
| **Concurrent-transition test** | Hai transaction cùng hoàn tất một order. | Chỉ một chuyển trạng thái được xác nhận; số event bền vững phù hợp chính sách. |
| **Commit/rollback test** | Publish trong transaction rồi rollback. | Tách việc gọi publish khỏi publication bền vững và side effect `AFTER_COMMIT`. |
| **Consumer idempotency test** | Cùng `eventId` được xử lý hai lần. | Một kết quả dữ liệu nghiệp vụ cuối cùng. |
| **Registry integration test** | Một event có hai target. | Publication theo từng target, completion độc lập, retry đúng target. |
| **Architecture test** | Thay đổi dependency module. | `ApplicationModules.verify()` phát hiện truy cập nội bộ trái quy tắc. |

Chạy các test liên quan trong quality gate CI của dự án. Ví dụ dùng tác vụ `test` của Gradle/Maven cùng cơ chế tích hợp database riêng khi cần. Test dùng lock/concurrency nên chạy trên database có transaction semantics tương đương production; không phải mọi mock hoặc database nhúng đều mô phỏng được tình huống race condition thực tế.

**Không đặt mục tiêu “exactly once delivery” chỉ bằng một assertion `hasSize(1)`.** Kết quả đó có ý nghĩa hẹp và hữu ích: đúng một sự kiện phù hợp được publish trong use case/test. Exactly-once effect ở consumer đòi hỏi các ràng buộc bổ sung.

## 12. Bài tập tình huống

Module `payment` có API:

~~~java
@Transactional
public void capture(UUID paymentId) {
    Payment payment = repository.findById(paymentId).orElseThrow();
    payment.markCaptured();
    publisher.publishEvent(new PaymentCaptured(
            UUID.randomUUID(), paymentId));
}
~~~

Một UI gọi `capture(paymentId)` hai lần vì request đầu tiên timeout. Có hai transactional listener: `ledger` ghi sổ và `receipt` gửi hóa đơn.

**Câu hỏi:**

1. Test chỉ gọi `capture` một lần rồi assert `PublishedEvents.hasSize(1)` có phát hiện lỗi phát trùng khi retry không?
2. Có cần guard trạng thái hoặc khóa giao dịch trên `Payment` không?
3. Nếu producer thực sự phát một event nhưng có hai listener, số publication trong registry có thể là bao nhiêu?
4. Nếu `receipt` đã gửi email nhưng registry chưa đánh dấu completed, email có thể bị gửi lại không?
5. Nên dùng test nào để chứng minh **publish đúng một lần**, test nào để chứng minh **ghi sổ đúng một lần**?
6. `ApplicationModules.verify()` đóng vai trò gì trong tình huống này?

**Đáp án tham khảo:**

1. Không. Test happy path một lời gọi chưa bao phủ hành vi retry. Cần gọi `capture(paymentId)` lặp rồi kiểm tra tổng event phù hợp chỉ bằng một.
2. Có. Kiểm tra trạng thái `CAPTURED` và xử lý cạnh tranh giúp tránh hai transaction cùng phát event cho một chuyển trạng thái nghiệp vụ.
3. Có thể là **hai publication**, mỗi transactional listener một bản ghi, dù chỉ một event nghiệp vụ được phát.
4. Có. Một lần giao lại có thể chạy listener lần nữa; cần idempotency key/ghi dấu bền vững hoặc cơ chế phòng trùng từ bên gửi thư.
5. `@ApplicationModuleTest` + `PublishedEvents` ở `payment` xác nhận publication tại nguồn. Integration test ở `ledger` với một `eventId` được xử lý lại xác nhận hiệu ứng ghi sổ không trùng.
6. `verify()` kiểm tra `ledger` và `receipt` chỉ phụ thuộc vào API event đã công bố của `payment`, không import repository/service nội bộ của module nguồn.

## 13. Checklist khi kiểm chứng event chỉ phát một lần

- [ ] Xác định rõ “một lần” là **mỗi request**, **mỗi order ID**, **mỗi chuyển trạng thái**, hay **mỗi event ID**.
- [ ] Use case có guard chống phát trùng nếu trạng thái nghiệp vụ đã được xác nhận.
- [ ] Có chiến lược cho hai lời gọi đồng thời: pessimistic/optimistic lock, cập nhật có điều kiện hoặc khóa idempotency.
- [ ] `@ApplicationModuleTest` gọi use case thật; `PublishedEvents` lọc **đúng kiểu và khóa nghiệp vụ**.
- [ ] Dùng `hasSize(1)` hoặc `singleElement()` thay cho chỉ `isNotEmpty()`.
- [ ] Có test gọi lặp, trường hợp từ chối và nhiều aggregate.
- [ ] Phân biệt việc `publishEvent` được gọi với transaction đã commit thành công.
- [ ] Nếu dùng Event Publication Registry, hiểu một event có nhiều publication theo các listener target.
- [ ] Consumer xử lý lại cùng event bằng idempotency; test cả marker lẫn side effect.
- [ ] Test async chờ theo điều kiện; test concurrent dùng transaction/database thực.
- [ ] Event type thuộc API công khai và các phụ thuộc module được `ApplicationModules.verify()` kiểm tra.
- [ ] Tích hợp module test, integration test và architecture test trong CI.

**Kết luận:** Để chứng minh **một chuyển trạng thái chỉ publish đúng một event**, hãy kích hoạt nghiệp vụ và dùng `PublishedEvents` lọc theo kiểu event cùng định danh nghiệp vụ, rồi assert **chính xác một**. Bổ sung test gọi lặp, transaction và cạnh tranh để ngăn phát trùng tại nguồn. Nếu yêu cầu là **xử lý nghiệp vụ đúng một lần ở listener**, cần kiểm tra idempotency và trạng thái dữ liệu riêng, bởi cơ chế retry không tự mang lại exactly-once effect.
