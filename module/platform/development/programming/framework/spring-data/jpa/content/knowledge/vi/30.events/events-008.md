# Giới hạn giao nhận sự kiện trong bộ nhớ

Spring Data JPA hỗ trợ phát hành domain event từ aggregate root khi các thao tác repository phù hợp được gọi. Cách này rất tiện để thông báo cho các thành phần khác trong cùng ứng dụng rằng một thay đổi nghiệp vụ đã xảy ra. Tuy nhiên, cơ chế phát hành sự kiện mặc định dựa trên bộ nhớ của ứng dụng và Spring application event mechanism. Nó không phải một hàng đợi bền vững hay một hệ thống messaging phân tán.

Hiểu rõ giới hạn này giúp chọn đúng cách xử lý: dùng event trong bộ nhớ cho phối hợp nội bộ nhẹ, dùng transaction-bound listener khi cần đợi transaction commit, và dùng transactional outbox hoặc message broker khi không được phép mất sự kiện.

## 1. Domain event trong Spring Data là gì?

Domain event là một thông điệp biểu diễn điều gì đó có ý nghĩa trong nghiệp vụ đã xảy ra, chẳng hạn:

- Đơn hàng đã được xác nhận.
- Thanh toán đã hoàn tất.
- Tài khoản đã bị khóa.
- Hồ sơ đã được phê duyệt.

Event thường mô tả sự kiện đã xảy ra bằng tên ở thì quá khứ, ví dụ `OrderConfirmed`, thay vì mô tả một lệnh như `ConfirmOrder`. Lệnh thể hiện ý định yêu cầu thay đổi; event thể hiện kết quả nghiệp vụ đã xảy ra.

Trong Spring Data, aggregate root có thể công bố event bằng `@DomainEvents` và dọn các event đã công bố bằng `@AfterDomainEventPublication`. Lớp tiện ích `AbstractAggregateRoot` đã triển khai cơ chế lưu event trong một collection nội bộ, cung cấp `registerEvent(...)` để aggregate đăng ký event và tự xóa các event sau khi phát hành.

Repository proxy của Spring Data phát hành các domain event đã đăng ký khi gọi những thao tác repository được hỗ trợ, ví dụ `save`, `saveAll`, `delete(entity)` và `deleteAll(entities)`. Điều này không có nghĩa mọi lệnh thay đổi database đều tự động phát event.

## 2. Đăng ký event từ aggregate root

Ví dụ một đơn hàng chỉ được hoàn tất khi đã thanh toán:

```java
package com.example.order;

public record OrderCompleted(Long orderId) {
}
```

Aggregate root đăng ký event khi chuyển trạng thái hợp lệ:

```java
package com.example.order;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;

import org.springframework.data.domain.AbstractAggregateRoot;

@Entity
public class PurchaseOrder
        extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public void complete() {
        if (status != OrderStatus.PAID) {
            throw new IllegalStateException(
                    "Only paid orders can be completed");
        }

        status = OrderStatus.COMPLETED;
        registerEvent(new OrderCompleted(id));
    }
}
```

`registerEvent` lưu event vào bộ nhớ của aggregate root. Nó chưa ghi event vào một bảng hay gửi event tới một message broker. Khi repository lưu aggregate, Spring Data lấy các event đã đăng ký và phát hành chúng qua Spring application event mechanism.

Ví dụ trên giả định đơn hàng đã được lưu và có ID trước khi gọi `complete()`. Nếu ID chỉ được database sinh ra khi INSERT, đừng tạo payload event chứa ID còn null trước khi persist; hãy thiết kế thời điểm đăng ký hoặc dữ liệu event sao cho ID đã sẵn sàng.

Repository:

```java
package com.example.order;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

Service thay đổi aggregate rồi gọi repository:

```java
package com.example.order;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void complete(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow();

        order.complete();
        repository.save(order);
    }
}
```

Khi `save(order)` được gọi, Spring Data phát hành event đã đăng ký trên aggregate. Phương thức service có transaction bao quanh cả thay đổi entity và thao tác repository. Thời điểm event được phát hành và thời điểm transaction commit là hai mốc khác nhau; phần tiếp theo giải thích cách ràng buộc listener với transaction.

## 3. Nhận event trong cùng ứng dụng

Có thể dùng `@EventListener` để nhận Spring application event:

```java
package com.example.notification;

import com.example.order.OrderCompleted;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderNotificationListener {

    @EventListener
    public void handle(OrderCompleted event) {
        System.out.println(
                "Order completed: " + event.orderId());
    }
}
```

Với cấu hình mặc định, Spring application event listener chạy đồng bộ trên thread phát hành event. Điều này có nghĩa lời gọi repository có thể phải đợi listener hoàn tất. Nếu listener ném exception, exception có thể truyền ngược về phía publisher và ảnh hưởng đến luồng xử lý hiện tại.

Đây là lựa chọn phù hợp cho phản ứng nội bộ nhẹ, nhanh và có thể chạy trong cùng tiến trình. Ví dụ: cập nhật một thành phần trong bộ nhớ, ghi log ứng dụng hoặc kích hoạt một bước xử lý nội bộ không cần độ bền giao nhận độc lập.

Không nên dùng listener đồng bộ để thực hiện một tác vụ mạng chậm nếu việc đó làm kéo dài transaction hoặc request. Cũng không nên giả định event đã được gửi ra ngoài thành công chỉ vì phương thức publish không báo lỗi.

## 4. Phân biệt thời điểm publish và thời điểm commit

Một điểm dễ nhầm là repository publish domain event sau khi phương thức repository được gọi, nhưng transaction bên ngoài có thể vẫn chưa commit. Ví dụ, service ở trên có `@Transactional`; khi `repository.save(order)` phát event, transaction của `complete()` vẫn đang chạy.

Nếu listener dùng `@EventListener`, nó có thể chạy trước khi database commit. Khi listener gửi email hoặc gọi API bên ngoài rồi transaction sau đó rollback, hệ thống bên ngoài đã nhận một thông báo cho thay đổi không được lưu.

Khi cần xử lý chỉ sau khi transaction commit, dùng `@TransactionalEventListener`:

```java
package com.example.notification;

import com.example.order.OrderCompleted;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCompletedListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void handle(OrderCompleted event) {
        // Xử lý sau khi transaction phát hành event đã commit.
    }
}
```

Các phase chính gồm:

- `BEFORE_COMMIT`: chạy trước khi transaction commit.
- `AFTER_COMMIT`: chạy sau khi commit thành công; đây là phase mặc định.
- `AFTER_ROLLBACK`: chạy sau khi transaction rollback.
- `AFTER_COMPLETION`: chạy sau khi transaction hoàn tất, dù commit hay rollback.

Nếu không có transaction đang hoạt động, transactional event listener mặc định không được gọi. Có thể bật `fallbackExecution = true` nếu nghiệp vụ thực sự muốn xử lý cả khi không có transaction, nhưng cần cân nhắc vì khi đó listener không còn được bảo đảm gắn với một lần commit.

`@TransactionalEventListener` giải quyết vấn đề thời điểm xử lý tương đối với transaction. Nó không biến event trong bộ nhớ thành dữ liệu bền vững.

## 5. Vì sao event trong bộ nhớ có thể bị mất?

Cơ chế domain event của aggregate root giữ các event trong một collection trong bộ nhớ. Spring application event publisher chuyển event tới listener trong cùng application context. Cơ chế này không tự lưu một bản ghi event độc lập trong database hoặc broker.

Các giới hạn quan trọng:

1. **Ứng dụng dừng hoặc crash:** event đang nằm trong bộ nhớ chưa được xử lý sẽ mất khi tiến trình kết thúc.
2. **Không có hàng đợi bền vững:** mặc định không có bảng lưu event chờ gửi, trạng thái retry hay cơ chế phát lại event sau khi khởi động.
3. **Không tự phân phối giữa các instance:** event được publish trong application context của một tiến trình không tự xuất hiện trong context của instance khác.
4. **Không có bảo đảm giao nhận độc lập:** Spring application event không tự cung cấp acknowledgment, retry bền vững hay exactly-once delivery.
5. **Listener có thể thất bại:** listener đồng bộ có thể ném exception; listener chạy sau commit có thể thất bại khi dữ liệu đã commit và không thể rollback transaction gốc.
6. **Event queue của aggregate cũng ở trong bộ nhớ:** `AbstractAggregateRoot` xóa event sau khi phát hành. Việc xóa này diễn ra trong quy trình publish, trước khi transaction bao ngoài nhất thiết đã commit. Nếu transaction rollback sau đó, listener phase `AFTER_COMMIT` không chạy, trong khi event trong aggregate đã được dọn.

Vì vậy, event nội bộ là cơ chế thông báo trong tiến trình, không phải một nhật ký sự kiện có thể phục hồi. Nếu cần chắc chắn rằng thay đổi database và thông điệp cần gửi được ghi nhận cùng nhau, cần một thiết kế có lưu trữ bền vững.

## 6. Các thao tác không tự động phát domain event

Spring Data phát hành domain event thông qua repository infrastructure khi gọi các phương thức được hỗ trợ trên aggregate root. Không nên suy rộng cơ chế này thành mọi thao tác ghi dữ liệu.

Các trường hợp thường không tự kích hoạt quy trình domain event của aggregate root:

- JPQL bulk `UPDATE` hoặc `DELETE` khai báo bằng `@Modifying`.
- Native SQL chạy trực tiếp.
- Cập nhật bằng `EntityManager` hoặc JDBC mà không đi qua repository proxy hỗ trợ publish event.
- Một phương thức repository tùy chỉnh không được event publishing infrastructure xử lý.
- Thao tác xóa chỉ truyền ID, khi không có aggregate instance để đọc các event đã đăng ký.

Bulk operation tác động trực tiếp lên database và bỏ qua việc tải, gọi phương thức nghiệp vụ và xử lý lifecycle của từng aggregate. Nếu cần event cho thao tác này, ứng dụng phải chủ động tạo và phát event phù hợp hoặc ghi nhận nó trong một cơ chế bền vững.

## 7. Khi nào dùng Transactional Outbox?

Nếu một thay đổi nghiệp vụ phải kéo theo thông điệp gửi tới hệ thống khác, ví dụ gửi thông tin đơn hàng tới dịch vụ vận chuyển hoặc phát thông báo thanh toán sang message broker, chỉ dùng event trong bộ nhớ có thể để lại khoảng trống giữa database và hệ thống nhận.

Transactional outbox giải quyết khoảng trống này bằng cách ghi thay đổi nghiệp vụ và một bản ghi event vào cùng database transaction:

1. Cập nhật aggregate trong transaction.
2. Chèn một hàng vào bảng `outbox_event` với event ID, loại event, aggregate ID, payload và thời điểm tạo.
3. Commit transaction. Nếu transaction rollback, cả thay đổi nghiệp vụ và hàng outbox đều rollback.
4. Một publisher riêng đọc các hàng chưa gửi và chuyển chúng tới broker.
5. Khi gửi thành công, publisher đánh dấu hàng đã gửi hoặc lưu trạng thái xử lý. Nếu gửi thất bại, có thể retry theo chính sách.

Ví dụ cấu trúc dữ liệu khái niệm:

| Cột | Mục đích |
|---|---|
| `event_id` | ID duy nhất để nhận diện và chống xử lý trùng |
| `aggregate_id` | ID của aggregate phát sinh event |
| `event_type` | Loại event |
| `payload` | Dữ liệu event được serialize |
| `created_at` | Thời điểm tạo event |
| `published_at` | Thời điểm publisher xác nhận đã gửi, có thể null khi còn chờ |

Outbox bảo đảm thay đổi nghiệp vụ và ý định gửi event được lưu nguyên tử trong cùng database transaction. Nó không tự bảo đảm broker chỉ nhận đúng một lần: publisher có thể gửi thành công nhưng gặp lỗi trước khi đánh dấu hàng đã gửi, dẫn đến gửi lại. Vì vậy consumer cần idempotent, chẳng hạn lưu `event_id` đã xử lý và bỏ qua event trùng.

Transactional outbox phù hợp khi mất event là không chấp nhận được, cần retry sau sự cố hoặc cần giao tiếp giữa nhiều service. Với nhu cầu nội bộ đơn giản trong một tiến trình, Spring application event thường gọn hơn.

## 8. Chọn cơ chế theo yêu cầu

| Nhu cầu | Cách tiếp cận |
|---|---|
| Phản ứng nhanh trong cùng ứng dụng, không cần lưu event | `@EventListener` |
| Chỉ chạy listener khi transaction commit thành công | `@TransactionalEventListener(AFTER_COMMIT)` |
| Chạy logic khi transaction rollback | `@TransactionalEventListener(AFTER_ROLLBACK)` |
| Cần gửi thông điệp bền vững tới broker hoặc service khác | Transactional outbox kết hợp message broker |
| Cần xử lý lại, chống trùng và theo dõi trạng thái giao nhận | Outbox/inbox, event ID và consumer idempotent |

Không nên chọn outbox chỉ vì ứng dụng có domain event. Hãy chọn dựa trên hậu quả nghiệp vụ nếu event bị mất, bị gửi trùng hoặc bị xử lý trễ.

## 9. Lỗi thường gặp và cách kiểm tra

- **Cho rằng `registerEvent` đã lưu event vào database:** phương thức này chỉ đăng ký event trong aggregate root. Muốn bền vững, phải lưu event vào bảng hoặc broker theo một quy trình có kiểm soát.
- **Dùng `@EventListener` cho side effect bên ngoài trước commit:** listener có thể chạy rồi transaction rollback. Dùng `@TransactionalEventListener(AFTER_COMMIT)` khi cần đợi commit.
- **Cho rằng AFTER_COMMIT có retry bền vững:** listener thất bại sau commit không làm transaction gốc rollback và không tự tạo hàng đợi retry. Dùng outbox nếu phải giao nhận đáng tin cậy.
- **Không thấy event khi gọi bulk update:** bulk query bỏ qua aggregate lifecycle và event publishing của repository. Tạo event tường minh hoặc ghi outbox.
- **Event bị phát lại nhiều lần:** thiết kế consumer idempotent bằng event ID và ràng buộc duy nhất cho dấu vết xử lý.
- **Listener làm request chậm:** listener mặc định đồng bộ. Nếu dùng async, hãy cấu hình executor và xử lý rõ lỗi, context bảo mật, transaction cùng retry; async vẫn không tạo độ bền.
- **Không có transaction nhưng dùng `@TransactionalEventListener`:** listener mặc định không chạy. Kiểm tra transaction boundary hoặc cân nhắc `fallbackExecution` khi thực sự phù hợp.

Khi kiểm thử, hãy xác minh ít nhất bốn trường hợp: transaction commit thì AFTER_COMMIT listener được gọi; transaction rollback thì listener AFTER_COMMIT không chạy; event trong aggregate được publish khi repository method phù hợp được gọi; và bulk update không được giả định sẽ tự phát domain event. Với outbox, kiểm thử tình huống publisher gửi thành công nhưng lỗi trước khi đánh dấu đã gửi để xác nhận consumer xử lý event trùng an toàn.

## 10. Ghi nhớ

Spring Data domain events là cách thuận tiện để aggregate root thông báo thay đổi nghiệp vụ trong cùng ứng dụng. Event được giữ và phát hành qua bộ nhớ, nên không có độ bền, retry hoặc phân phối liên tiến trình mặc định. Dùng `@TransactionalEventListener` để gắn thời điểm xử lý với commit/rollback; dùng transactional outbox và consumer idempotent khi hệ thống cần giao nhận event bền vững giữa các thành phần hoặc service.