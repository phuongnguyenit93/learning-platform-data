# Công bố sự kiện từ aggregate bằng @DomainEvents

Trong Domain-Driven Design (DDD), aggregate root là điểm vào để thay đổi trạng thái của một aggregate. Khi một thay đổi nghiệp vụ có ý nghĩa xảy ra, aggregate có thể ghi nhận một domain event, chẳng hạn `OrderConfirmed` hoặc `PaymentReceived`. Spring Data cung cấp `@DomainEvents` để tự động công bố các event đã ghi nhận khi ứng dụng gọi những phương thức repository được hỗ trợ.

Cơ chế này giúp aggregate mô tả sự kiện nghiệp vụ mà không phải tự tìm và gọi từng listener. Spring Data đưa event vào cơ chế application event của Spring; các bean khác có thể nhận event bằng `@EventListener` hoặc `@TransactionalEventListener`.

## 1. Domain event và aggregate root

Domain event là một sự kiện đã xảy ra trong miền nghiệp vụ. Tên event thường diễn đạt ở thì quá khứ:

- `OrderPlaced`: đơn hàng đã được tạo.
- `OrderConfirmed`: đơn hàng đã được xác nhận.
- `PaymentReceived`: khoản thanh toán đã được ghi nhận.
- `InventoryReserved`: tồn kho đã được giữ.

Domain event khác command. Command yêu cầu hệ thống thực hiện điều gì đó, ví dụ `ConfirmOrder`; domain event thông báo rằng việc xác nhận đã xảy ra, ví dụ `OrderConfirmed`.

Một aggregate root có trách nhiệm bảo vệ invariant và thay đổi trạng thái của aggregate. Khi phương thức nghiệp vụ hoàn thành một chuyển đổi hợp lệ, aggregate ghi nhận event tương ứng. Repository là điểm tích hợp để Spring Data thu thập và công bố những event đó.

Event nên chứa dữ liệu cần thiết cho consumer, thường là ID aggregate, thời điểm xảy ra và các giá trị nghiệp vụ bất biến. Tránh truyền nguyên entity JPA hoặc proxy lazy vào event vì listener có thể chạy sau khi persistence context đã đóng hoặc transaction đã hoàn tất.

## 2. Hai annotation chính

### @DomainEvents

`@DomainEvents` đánh dấu một phương thức trên aggregate root để Spring Data lấy các event cần công bố.

Phương thức được đánh dấu:

- Không nhận tham số.
- Có thể trả về một event đơn lẻ hoặc một collection các event.
- Được Spring Data gọi khi một phương thức repository hỗ trợ được thực thi với aggregate root tương ứng.

Ví dụ:

```java
@DomainEvents
public Collection<Object> domainEvents() {
    return events;
}
```

### @AfterDomainEventPublication

`@AfterDomainEventPublication` đánh dấu callback được gọi sau khi Spring Data đã công bố tất cả event lấy từ aggregate. Callback thường dùng để xóa các event đã công bố khỏi danh sách nội bộ.

```java
@AfterDomainEventPublication
public void clearDomainEvents() {
    events.clear();
}
```

Callback này gắn với việc công bố event vào Spring application event mechanism. Nó không có nghĩa database transaction đã commit. Nếu cần xử lý listener theo kết quả commit/rollback, hãy dùng `@TransactionalEventListener`.

## 3. Dùng AbstractAggregateRoot để quản lý event

Spring Data cung cấp lớp tiện ích `AbstractAggregateRoot` trong package `org.springframework.data.domain`. Aggregate có thể kế thừa lớp này để đăng ký event mà không phải tự viết danh sách, phương thức `@DomainEvents` và callback xóa event.

Các phương thức hữu ích:

- `registerEvent(event)`: thêm event vào danh sách chờ công bố và trả lại chính event đó.
- `andEvent(event)`: thêm event và trả lại aggregate để hỗ trợ method chaining.
- `andEventsFrom(aggregate)`: thêm các event từ aggregate khác.
- `domainEvents()`: phương thức được đánh dấu `@DomainEvents`, cung cấp danh sách event.
- `clearDomainEvents()`: callback được đánh dấu `@AfterDomainEventPublication`, xóa danh sách sau khi công bố.

Ví dụ dưới đây dùng Java 17 record để biểu diễn event bất biến:

```java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID orderId,
    Instant occurredAt
) {}
```

Aggregate root:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;

import java.util.UUID;

import org.springframework.data.domain.AbstractAggregateRoot;

@Entity
public class PurchaseOrder extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public static PurchaseOrder create() {
        PurchaseOrder order = new PurchaseOrder();
        order.id = UUID.randomUUID();
        order.status = OrderStatus.DRAFT;
        return order;
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft order can be confirmed"
            );
        }

        status = OrderStatus.CONFIRMED;
        registerEvent(new OrderConfirmed(id, java.time.Instant.now()));
    }

    public UUID getId() {
        return id;
    }
}
```

`OrderStatus` là enum của miền nghiệp vụ, ví dụ có các giá trị `DRAFT` và `CONFIRMED`. Phần code trên là đoạn minh họa aggregate; trong dự án thật cần bổ sung các thuộc tính, constructor và mapping phù hợp với schema.

Điểm quan trọng là event chỉ được đăng ký sau khi quy tắc nghiệp vụ cho phép chuyển trạng thái. Nếu `confirm()` thất bại vì trạng thái không hợp lệ, aggregate không phát ra `OrderConfirmed`.

## 4. Repository là điểm kích hoạt công bố event

Repository quản lý aggregate root:

```java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {
}
```

Khi gọi một phương thức repository được Spring Data hỗ trợ, cơ chế event publishing tìm các aggregate root được truyền vào, gọi phương thức `@DomainEvents`, công bố event và gọi callback `@AfterDomainEventPublication` sau khi công bố xong.

Các phương thức repository được tài liệu Spring Data liệt kê gồm:

- `save(aggregate)` và `saveAll(aggregates)`.
- `delete(aggregate)` và `deleteAll(aggregates)`.
- `deleteAllInBatch(aggregates)` và `deleteInBatch(aggregates)` đối với các overload nhận các aggregate instance.

Việc truyền aggregate instance là điều kiện quan trọng. `deleteById(id)` không nằm trong danh sách vì repository có thể xóa bằng query mà không tải aggregate root lên. Các phương thức bulk query tùy chỉnh như `@Query("update ...")` hoặc `@Modifying` cũng không tự tìm aggregate để phát event. Những thao tác không nhận aggregate instance không thể dựa vào cơ chế này để thu thập domain event.

Ví dụ service thay đổi aggregate rồi lưu bằng repository:

```java
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public UUID confirm(UUID orderId) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId
            ));

        order.confirm();

        // Lời gọi save cung cấp aggregate cho cơ chế DomainEvents.
        orders.save(order);

        return order.getId();
    }
}
```

Trong ví dụ này:

1. Service tải aggregate root.
2. Phương thức nghiệp vụ `confirm()` kiểm tra invariant, đổi trạng thái và đăng ký `OrderConfirmed`.
3. `orders.save(order)` kích hoạt cơ chế công bố event của Spring Data.
4. Spring Data lấy event từ aggregate và đưa event vào Spring application event mechanism.
5. Callback của aggregate xóa event đã công bố theo cơ chế `AbstractAggregateRoot`.

Đối với entity đang được quản lý trong transaction JPA, thay đổi field có thể đã được dirty checking ghi nhận mà không cần gọi `save()` về mặt JPA. Tuy nhiên, nếu muốn kích hoạt cơ chế công bố domain event của Spring Data, hãy gọi phương thức repository phù hợp với aggregate instance. Đừng giả định rằng chỉ cần Hibernate flush là event sẽ được công bố.

## 5. Nhận event bằng Spring listener

Event được Spring Data công bố như application event. Một bean có thể nhận event bằng `@EventListener`:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventLogger {

    @EventListener
    public void onOrderConfirmed(OrderConfirmed event) {
        System.out.println(
            "Order confirmed: " + event.orderId()
        );
    }
}
```

Với cấu hình Spring mặc định, application event listener được gọi đồng bộ trên thread công bố. Do đó listener có thể chạy ngay trong lời gọi repository, trước khi transaction bên ngoài kết thúc. Nếu listener ném exception, exception có thể truyền ngược qua luồng công bố và làm transaction rollback tùy rollback rule.

Có thể dùng `@Async` để xử lý bất đồng bộ khi đã cấu hình async processing. Khi đó listener chạy ở thread khác, không tự động chia sẻ transaction hoặc persistence context của thread công bố. Không dùng async nếu listener cần đọc trạng thái chưa commit hoặc cần tham gia cùng transaction của service.

## 6. Chọn thời điểm xử lý bằng @TransactionalEventListener

Trong nghiệp vụ có transaction, thời điểm listener chạy có thể quan trọng. Spring Framework cung cấp `@TransactionalEventListener` để gắn việc xử lý event với một phase của transaction.

Ví dụ gửi thông báo sau khi đơn hàng đã commit:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void sendConfirmation(OrderConfirmed event) {
        // Gửi email hoặc gọi một dịch vụ thông báo.
    }
}
```

Các phase thường dùng:

| Phase | Thời điểm | Mục đích |
|---|---|---|
| `BEFORE_COMMIT` | Ngay trước khi transaction commit | Kiểm tra hoặc thực hiện công việc cần hoàn tất trước commit |
| `AFTER_COMMIT` | Sau khi commit thành công; đây là mặc định | Gửi thông báo hoặc thực hiện side effect chỉ khi dữ liệu đã commit |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Ghi nhận hoặc xử lý tình huống rollback |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất, bất kể commit hay rollback | Dọn dẹp hoặc xử lý chung sau khi transaction kết thúc |

Nếu không có transaction đang hoạt động, `@TransactionalEventListener` mặc định không được gọi. Thuộc tính `fallbackExecution = true` cho phép listener chạy cả khi không có transaction, nhưng chỉ nên bật khi nghiệp vụ thực sự chấp nhận trường hợp đó.

### Phân biệt @EventListener và @TransactionalEventListener

- `@EventListener` xử lý event khi Spring công bố event. Với multicaster mặc định, listener chạy đồng bộ ngay tại thời điểm đó.
- `@TransactionalEventListener` chờ phase được chỉ định. Mặc định là `AFTER_COMMIT`, vì vậy listener chỉ xử lý event nếu transaction commit thành công.

Chọn `@EventListener` khi muốn thực hiện xử lý đồng bộ ngay trong luồng nghiệp vụ và chấp nhận listener cùng ảnh hưởng kết quả lời gọi. Chọn `@TransactionalEventListener(AFTER_COMMIT)` khi side effect chỉ được xảy ra sau khi dữ liệu đã commit, chẳng hạn gửi email, webhook hoặc cập nhật hệ thống tìm kiếm.

Lưu ý với listener chạy sau commit: transaction gốc đã hoàn tất. Tài nguyên giao dịch có thể vẫn còn được truy cập trong callback, nhưng thay đổi database được thực hiện tại thời điểm đó không được commit theo transaction đã kết thúc. Nếu listener cần ghi database, hãy gọi một service mở transaction mới, thường bằng `Propagation.REQUIRES_NEW`.

## 7. Vòng đời event và giới hạn bảo đảm

### Callback xóa event không phải là xác nhận commit

`@AfterDomainEventPublication` được gọi sau khi event đã được đưa vào cơ chế công bố của Spring. Nếu dùng `AbstractAggregateRoot`, danh sách event được xóa tại callback này. Thời điểm đó có thể vẫn nằm trước commit của transaction bên ngoài.

Do đó, không nên hiểu callback là "event đã được xử lý thành công sau khi dữ liệu commit". Ví dụ, một `@TransactionalEventListener(AFTER_COMMIT)` có thể còn chưa chạy khi callback xóa danh sách event được gọi.

### Spring application event không phải hàng đợi bền vững

Domain event được giữ trong bộ nhớ của aggregate và công bố trong process hiện tại. Cơ chế này không tự cung cấp:

- Lưu trữ event bền vững trong database.
- Retry tự động khi listener hoặc hệ thống bên ngoài thất bại.
- Bảo đảm giao nhận đúng một lần giữa nhiều hệ thống.
- Khôi phục event đã mất khi ứng dụng dừng đột ngột.

Nếu transaction rollback sau khi event đã được công bố và aggregate đã xóa danh sách event, event không tự xuất hiện lại khi ứng dụng khởi động. Listener `AFTER_COMMIT` sẽ không chạy cho transaction rollback, nhưng danh sách event trong object đang giữ có thể đã được xóa.

Với tích hợp quan trọng cần bảo đảm không mất thông điệp, hãy cân nhắc Transactional Outbox: lưu thay đổi aggregate và bản ghi outbox trong cùng transaction database; một publisher riêng đọc outbox và gửi message đến broker, sau đó đánh dấu đã xử lý. Consumer nên idempotent vì hệ thống phân tán thường cần chịu được việc gửi lại.

## 8. Tổ chức event trong aggregate

Một số nguyên tắc giúp event dễ bảo trì:

- **Đặt tên theo sự kiện đã xảy ra:** dùng `OrderConfirmed`, không dùng tên command như `ConfirmOrder`.
- **Chỉ phát sau chuyển đổi hợp lệ:** đăng ký event sau khi aggregate đã kiểm tra điều kiện và thay đổi trạng thái thành công.
- **Dùng payload bất biến:** Java record phù hợp với event nhỏ; chỉ đưa vào dữ liệu consumer thực sự cần.
- **Ưu tiên ID và snapshot nghiệp vụ:** tránh truyền entity JPA có quan hệ lazy hoặc trạng thái mutable.
- **Giữ event thuộc aggregate tạo ra nó:** một aggregate không nên phát thay các sự kiện nội bộ của aggregate khác.
- **Làm listener idempotent khi cần:** cùng một event có thể được xử lý lại do retry của tầng ứng dụng hoặc hệ thống tích hợp.

Không nên để listener thay đổi ngược aggregate vừa phát event theo một vòng lặp khó kiểm soát. Nếu cần một chuyển đổi nghiệp vụ mới, hãy thể hiện bằng một use case rõ ràng và event tương ứng.

## 9. Cách tự triển khai bằng hai annotation

Nếu không muốn aggregate kế thừa `AbstractAggregateRoot`, có thể tự quản lý danh sách event và đánh dấu hai phương thức:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

public class CustomAggregate {

    private final transient List<Object> events = new ArrayList<>();

    protected void register(Object event) {
        events.add(event);
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return Collections.unmodifiableList(events);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        events.clear();
    }
}
```

Danh sách event là trạng thái tạm trong bộ nhớ; từ khóa Java `transient` giúp nó không bị serialize theo cơ chế Java serialization và không được JPA coi là persistent field. Cách triển khai thực tế vẫn cần bảo đảm collection không bị sửa từ bên ngoài, event chỉ được đăng ký qua phương thức nghiệp vụ và callback xóa đúng các event đã công bố.

Chọn một cách quản lý: kế thừa `AbstractAggregateRoot` hoặc tự dùng hai annotation. Không cần triển khai cả hai cơ chế cho cùng một danh sách event.

## 10. Kiểm thử công bố domain event

Có thể kiểm thử hai lớp hành vi riêng:

1. **Aggregate đăng ký event đúng:** gọi phương thức nghiệp vụ hợp lệ và xác nhận aggregate cung cấp event mong đợi; gọi phương thức không hợp lệ và xác nhận không tạo event sai.
2. **Repository kích hoạt công bố:** gọi `save(aggregate)` trong Spring context, đăng ký listener hoặc dùng `ApplicationEvents` trong test để xác nhận event đã được công bố.
3. **Callback dọn danh sách:** sau khi repository công bố event, lưu lại aggregate và xác nhận event không bị phát lại nếu callback đã xóa danh sách.
4. **Transaction phase:** dùng integration test để xác nhận listener `AFTER_COMMIT` chỉ chạy khi transaction commit và không chạy khi rollback.
5. **Không nhầm save với flush:** sửa một entity rồi chỉ flush persistence context không phải là lời gọi repository kích hoạt cơ chế `@DomainEvents`.

Ví dụ kiểm tra aggregate ở mức unit test (giả sử `PurchaseOrder` là lớp aggregate ở trên):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PurchaseOrderTest {

    @Test
    void confirmRegistersDomainEvent() {
        PurchaseOrder order = PurchaseOrder.create();

        order.confirm();

        assertEquals(1, order.domainEvents().size());
        assertEquals(
            order.getId(),
            ((OrderConfirmed) order.domainEvents().iterator().next()).orderId()
        );
    }

    @Test
    void cannotConfirmTwice() {
        PurchaseOrder order = PurchaseOrder.create();
        order.confirm();

        assertThrows(IllegalStateException.class, order::confirm);
        assertEquals(1, order.domainEvents().size());
    }
}
```

Lưu ý `domainEvents()` trong `AbstractAggregateRoot` có thể được khai báo protected. Nếu test cần truy cập, hãy cung cấp một phương thức package-private/protected trong aggregate phục vụ kiểm thử, hoặc kiểm tra event qua listener trong Spring integration test. Đoạn test trên cần điều chỉnh quyền truy cập theo cách tổ chức package của dự án; không nên mở API domain chỉ để test nếu không cần thiết.

## 11. Lỗi thường gặp

- **Chỉ đăng ký event nhưng không gọi repository:** event vẫn nằm trong aggregate; Spring Data chưa có lần gọi repository hỗ trợ để thu thập và công bố event.
- **Dùng `deleteById()` rồi mong event của aggregate được phát:** phương thức chỉ nhận ID, không cung cấp aggregate instance cho cơ chế event publishing.
- **Dùng bulk JPQL update/delete và mong tự phát event:** bulk query làm việc trực tiếp với database, không đi qua aggregate root; hãy tự công bố event hoặc thiết kế thao tác qua aggregate.
- **Quên xóa danh sách event:** cùng event có thể bị công bố lại ở lần save/delete tiếp theo. Dùng `@AfterDomainEventPublication` hoặc `AbstractAggregateRoot`.
- **Nghĩ callback chạy sau commit:** callback chạy sau khi Spring Data công bố event, không phải callback transaction. Dùng `@TransactionalEventListener` để ràng buộc theo transaction phase.
- **Gửi email ngay trong listener đồng bộ:** email có thể đã gửi dù transaction sau đó rollback. Dùng `AFTER_COMMIT` cho side effect chỉ được chạy khi commit thành công.
- **Cho rằng event trong bộ nhớ là durable:** event có thể mất khi process dừng hoặc transaction rollback. Dùng outbox nếu cần giao nhận bền vững.
- **Truyền nguyên entity vào event:** listener có thể gặp lazy loading, detached entity hoặc đọc trạng thái thay đổi về sau. Ưu tiên ID và snapshot bất biến.

## 12. Quy trình áp dụng

1. Xác định aggregate root và các chuyển đổi trạng thái có ý nghĩa nghiệp vụ.
2. Tạo event bất biến, mang tên một sự kiện đã xảy ra và chứa dữ liệu cần cho consumer.
3. Trong phương thức nghiệp vụ, kiểm tra invariant, cập nhật trạng thái và đăng ký event.
4. Kế thừa `AbstractAggregateRoot` hoặc tự triển khai `@DomainEvents` cùng `@AfterDomainEventPublication`.
5. Gọi `save(aggregate)` hoặc phương thức repository được hỗ trợ có truyền aggregate instance.
6. Viết listener phù hợp: `@EventListener` cho xử lý ngay; `@TransactionalEventListener` cho xử lý theo phase transaction.
7. Nếu listener cần ghi database sau commit, mở transaction mới. Nếu cần tích hợp bền vững với broker hoặc hệ thống bên ngoài, cân nhắc transactional outbox.
8. Kiểm thử event được đăng ký, được công bố đúng lần, callback dọn danh sách và listener chạy đúng transaction phase.

## Tài liệu tham khảo

- [Spring Data Commons – Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html)
- [Spring Data Commons – AbstractAggregateRoot API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AbstractAggregateRoot.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)

