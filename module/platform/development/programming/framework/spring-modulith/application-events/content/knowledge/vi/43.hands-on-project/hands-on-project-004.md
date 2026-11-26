# Tạo producer

Trong Spring Modulith, producer là thành phần phát application event khi một sự kiện nghiệp vụ đã được xác lập. Producer cần công bố một contract rõ ràng, phát event đúng thời điểm trong transaction và chỉ chứa dữ liệu mà các module nhận cần để phản ứng. Khi producer được thiết kế đúng, module sở hữu nghiệp vụ không phải gọi trực tiếp từng listener và có thể bổ sung subscriber mà không thay đổi luồng phát event.

Bài thực hành này xây dựng producer cho module **SPRING_MODULITH_APPLICATION_EVENTS**. Ví dụ dùng module Orders: khi đơn hàng được xác nhận, use case lưu trạng thái đơn và phát event `OrderConfirmed`. Các module khác có thể đăng ký listener để cập nhật projection hoặc khởi tạo công việc tiếp theo.

## 1. Xác định contract trước khi viết producer

Trước khi tạo class, xác định sự thật nghiệp vụ cần công bố. Trong ví dụ này, `OrderConfirmed` có nghĩa đơn hàng đã chuyển sang trạng thái CONFIRMED và thay đổi đó được lưu trong transaction nghiệp vụ.

Event cần trả lời được:

- Sự kiện nào đã xảy ra?
- Đối tượng nghiệp vụ nào bị ảnh hưởng?
- Sự kiện xảy ra vào thời điểm nào?
- Subscriber cần những dữ liệu nào để xử lý?
- Có cần event ID để deduplicate và aggregate version để phát hiện event cũ không?

Tên event nên mô tả sự thật đã xảy ra, thường dùng thì quá khứ như `OrderConfirmed`, `PaymentCaptured` hoặc `StockReserved`. Tên như `ConfirmOrder` hoặc `SendNotification` mô tả yêu cầu hành động và phù hợp với command hơn.

Một event không phải bản sao toàn bộ aggregate. Chỉ đưa vào payload những trường thuộc contract và cần thiết cho subscriber. Không đưa JPA entity, repository, service, lazy proxy hoặc object phụ thuộc persistence context vào event.

## 2. Xác định vị trí producer trong module

Producer thuộc module sở hữu sự thật nghiệp vụ. Nếu Orders quyết định đơn hàng đã được xác nhận, Orders chịu trách nhiệm định nghĩa và phát `OrderConfirmed`.

Một cấu trúc package minh họa:

~~~text
com.example.orders
├── api
│   └── events
│       └── OrderConfirmed.java
├── application
│   └── ConfirmOrderUseCase.java
├── domain
│   ├── Order.java
│   └── OrderRepository.java
└── infrastructure
    └── persistence
        └── JpaOrderRepository.java
~~~

Event contract được đặt trong package API được module công bố. Use case nằm trong application layer và phụ thuộc vào domain repository cùng Spring event publisher. Listener của module nhận nằm trong module của chính nó; producer không import implementation listener.

Nếu dự án dùng named interface của Spring Modulith, package chứa event có thể được công bố như một interface có tên. Quy tắc cụ thể cần nhất quán với cấu trúc module hiện có. Không đưa event vào package `common` chỉ để mọi module tiện import nếu không có module sở hữu contract rõ ràng.

## 3. Tạo immutable event record

Dùng Java record để biểu diễn event bất biến:

~~~java
package com.example.orders.api.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    BigDecimal totalAmount,
    String currency
) {}
~~~

Các trường trong ví dụ có ý nghĩa:

| Trường | Mục đích |
|---|---|
| `eventId` | Định danh duy nhất của lần phát event, hỗ trợ deduplication và điều tra |
| `orderId` | Định danh đơn hàng đã được xác nhận |
| `occurredAt` | Thời điểm nghiệp vụ xác nhận đơn |
| `totalAmount` | Số tiền tại thời điểm xác nhận |
| `currency` | Mã tiền tệ theo contract, ví dụ ISO 4217 |

`BigDecimal` phù hợp với dữ liệu tiền tệ hơn floating-point. Currency được biểu diễn bằng mã có ý nghĩa rõ ràng; consumer không nên tự đoán đơn vị hoặc số chữ số thập phân.

Nếu subscriber cần phát hiện event đến sai thứ tự, có thể bổ sung `aggregateVersion` hoặc sequence do aggregate sở hữu. Chỉ thêm trường này khi nguồn có quy tắc tăng version đáng tin cậy. Timestamp không thay thế sequence vì đồng hồ có thể lệch và nhiều event có thể cùng thời điểm.

Event ID phải được tạo một lần cho event và giữ nguyên khi publication được retry hoặc resubmit. Không tạo ID mới mỗi lần listener xử lý lại cùng publication.

## 4. Tạo use case phát event

Producer thường nằm trong application service hoặc use case điều phối thay đổi nghiệp vụ. Use case tải aggregate, gọi hành vi domain, lưu thay đổi và phát event.

~~~java
package com.example.orders.application;

import com.example.orders.api.events.OrderConfirmed;
import com.example.orders.domain.Order;
import com.example.orders.domain.OrderRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConfirmOrderUseCase {

    private final OrderRepository orders;
    private final ApplicationEventPublisher eventPublisher;
    private final Clock clock;

    public ConfirmOrderUseCase(
            OrderRepository orders,
            ApplicationEventPublisher eventPublisher,
            Clock clock) {
        this.orders = orders;
        this.eventPublisher = eventPublisher;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        Instant confirmedAt = clock.instant();
        order.confirm(confirmedAt);
        orders.save(order);

        OrderConfirmed event = new OrderConfirmed(
            UUID.randomUUID(),
            order.getId(),
            confirmedAt,
            order.getTotalAmount(),
            order.getCurrencyCode()
        );

        eventPublisher.publishEvent(event);
    }
}
~~~

Đây là ví dụ minh họa; tên repository, exception và domain method cần khớp với mô hình của ứng dụng. `Order.confirm()` chịu trách nhiệm kiểm tra chuyển trạng thái hợp lệ. Use case điều phối transaction và công bố event sau khi đã thực hiện thay đổi domain.

Việc gọi `publishEvent()` nằm trong transaction. Điều đó giúp event publication tham gia đúng luồng nghiệp vụ, nhưng cách listener phản ứng phụ thuộc loại listener. Một listener `@EventListener` thông thường có thể chạy ngay trong luồng publish. Với phản ứng cần xảy ra sau commit, hãy dùng semantics after-commit phù hợp, chẳng hạn `@ApplicationModuleListener` của Spring Modulith.

## 5. Cấu hình Clock để kiểm soát thời gian

Không gọi trực tiếp `Instant.now()` ở nhiều nơi nếu cần test thời gian xác định. Đưa `Clock` vào constructor để production dùng UTC và test có thể cung cấp clock cố định.

~~~java
package com.example.orders.infrastructure;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Trong test, có thể dùng `Clock.fixed(...)` để xác minh `occurredAt` đúng thời điểm mong đợi. Điều này làm test ổn định và tránh phụ thuộc vào thời gian chạy thực tế.

Nếu ứng dụng đã có bean Clock dùng chung, hãy tái sử dụng bean đó thay vì khai báo thêm một bean trùng lặp.

## 6. Đặt thời điểm publish đúng với transaction

Một nguyên tắc quan trọng là event mô tả sự thật đã commit. Với use case ở trên, thay đổi đơn hàng và publication được tạo trong cùng transaction. Listener được cấu hình after-commit chỉ thực hiện phản ứng sau khi transaction commit thành công.

Luồng xử lý:

~~~text
ConfirmOrderUseCase
        |
        v
Begin transaction
        |
        v
Load and validate Order
        |
        v
Change Order state
        |
        v
Save Order
        |
        v
publishEvent(OrderConfirmed)
        |
        v
Commit transaction
        |
        v
After-commit listener runs
~~~

Nếu transaction rollback, listener after-commit không được thực hiện như thể đơn hàng đã xác nhận. Cần phân biệt việc event được phát vào Spring application context với việc một listener thực sự được gọi sau commit.

Không tự chuyển mọi listener sang async chỉ để producer trả về nhanh. Việc đó thay đổi thời điểm quan sát dữ liệu, cách lỗi được truyền và yêu cầu phục hồi. Chọn đồng bộ hay bất đồng bộ theo contract nghiệp vụ.

## 7. Tạo listener thử nghiệm ở module nhận

Để thấy producer hoạt động, có thể tạo một listener trong module khác. Listener chỉ phụ thuộc vào event contract công khai:

~~~java
package com.example.notifications;

import com.example.orders.api.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmedNotificationListener {

    private final NotificationJobRepository jobs;

    OrderConfirmedNotificationListener(
            NotificationJobRepository jobs) {
        this.jobs = jobs;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        jobs.createConfirmationJob(
            event.eventId(),
            event.orderId(),
            event.occurredAt()
        );
    }
}
~~~

Listener này chỉ minh họa cách subscriber sử dụng event. Producer không cần biết class listener hoặc module Notifications tồn tại. Trong ứng dụng thực tế, job gửi email nên được lưu bền vững rồi worker gửi riêng; không giữ transaction listener mở trong khi gọi dịch vụ email qua mạng.

Nếu chưa có module nhận, vẫn có thể xây dựng và kiểm thử producer độc lập bằng cách xác minh event được publish. Contract nên được thiết kế theo nhu cầu subscriber đã xác định, nhưng không cần tạo một listener giả chỉ để producer compile.

## 8. Event Publication Registry làm gì?

Spring Modulith Event Publication Registry theo dõi publication của application event tới các listener được quản lý. Với listener transactional phù hợp, registry lưu trạng thái publication để biết listener đã hoàn tất hay còn incomplete.

Registry giúp xử lý các tình huống như listener thất bại hoặc ứng dụng dừng trước khi publication hoàn tất. Tuy nhiên, registry không tự bảo đảm mọi side effect bên ngoài được thực hiện đúng một lần và không thay thế idempotency của listener.

Khi dùng registry:

- Giữ cấu hình persistence phù hợp nếu cần phục hồi qua restart.
- Để exception thoát khỏi listener khi publication cần được đánh dấu thất bại.
- Không bắt exception rồi chỉ ghi log và kết thúc bình thường.
- Thiết kế listener idempotent vì publication có thể được resubmit.
- Theo dõi publication incomplete và tuổi của publication.
- Kiểm tra API phục hồi theo đúng phiên bản Spring Modulith đang dùng.

Producer chỉ cần phát event qua application event publisher. Việc theo dõi publication phụ thuộc vào listener và cấu hình Spring Modulith; không tự ghi một trạng thái “đã giao” chỉ vì `publishEvent()` đã trả về.

## 9. Phân biệt event nội bộ và event externalized

Bài thực hành này tạo application event dùng trong phạm vi ứng dụng Modulith. Nếu sau này cần gửi sự kiện ra Kafka hoặc hệ thống khác, hãy xem đó là một hợp đồng tích hợp có chủ đích.

Có thể dùng cơ chế externalization của Spring Modulith, ví dụ metadata `@Externalized`, khi integration tương ứng đã được cấu hình. Logical target cần được ánh xạ tới destination thực tế; annotation không tự tạo topic, serializer, ACL hoặc broker.

Trước khi externalize, xác định:

- Consumer ngoài và owner của từng consumer.
- Schema, version và compatibility policy.
- Event ID, correlation metadata và key.
- Serialization, headers và data classification.
- Retry, dead-letter và replay.
- Ai chịu trách nhiệm khi broker không sẵn sàng.

Không externalize mọi event nội bộ. Giữ contract bên ngoài tách khỏi entity và implementation nội bộ để module có thể thay đổi mà không vô tình phá vỡ consumer độc lập.

## 10. Kiểm thử producer phát đúng event

Có thể dùng Spring Test `@RecordApplicationEvents` để ghi nhận application event được publish trong test:

~~~java
@SpringBootTest
@RecordApplicationEvents
class ConfirmOrderUseCaseTests {

    @Autowired
    ConfirmOrderUseCase confirmOrder;

    @Autowired
    ApplicationEvents applicationEvents;

    @Test
    void publishesOrderConfirmed() {
        UUID orderId = createDraftOrder();

        confirmOrder.confirm(orderId);

        List<OrderConfirmed> events =
            applicationEvents.stream(OrderConfirmed.class).toList();

        assertThat(events).hasSize(1);
        assertThat(events.get(0).orderId()).isEqualTo(orderId);
        assertThat(events.get(0).eventId()).isNotNull();
    }
}
~~~

Ví dụ dùng Spring Test và AssertJ; `createDraftOrder()` là fixture do test cung cấp. Test method không nên tự mở transaction nếu muốn use case commit độc lập theo transaction của nó. Nếu test được bọc trong transaction của test framework, cần kiểm soát rõ thời điểm commit.

Test này chứng minh use case đã publish event với dữ liệu mong đợi. Nó không tự chứng minh listener after-commit đã hoàn tất hoặc Event Publication Registry đã đánh dấu publication hoàn tất. Hai hành vi đó cần integration test riêng với listener và persistence registry thực tế.

Các trường hợp bổ sung nên kiểm tra:

1. Đơn hàng hợp lệ phát đúng một event.
2. Đơn hàng không tồn tại không phát event.
3. Chuyển trạng thái không hợp lệ không phát event.
4. Payload chứa đúng order ID, amount, currency và occurredAt.
5. Event ID khác nhau giữa hai sự kiện nghiệp vụ độc lập.
6. Transaction rollback không kích hoạt listener after-commit.
7. Listener nhận event không truy cập package nội bộ của producer.

## 11. Tránh các lỗi thường gặp khi tạo producer

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Phát event trước khi kiểm tra nghiệp vụ | Subscriber phản ứng với sự kiện không hợp lệ | Xác thực và thay đổi aggregate trước khi publish |
| Publish ngoài transaction cần thiết | Event có thể tách khỏi trạng thái dữ liệu | Đặt publication trong transaction nghiệp vụ |
| Dùng listener đồng bộ nhưng nghĩ là after-commit | Listener có thể chạy trước commit | Dùng listener transactional/after-commit phù hợp |
| Đưa entity vào payload | Rò rỉ persistence model và lỗi lazy loading | Dùng immutable event DTO |
| Producer gọi trực tiếp từng listener | Phụ thuộc chặt vào subscriber | Publish contract và để module nhận đăng ký |
| Tạo event ID mới khi retry | Deduplication không nhận ra cùng event | Giữ event ID của publication gốc |
| Nuốt exception ở listener | Registry có thể coi publication hoàn tất | Truyền lỗi hoặc ghi nhận quarantine có chủ đích |
| Externalize không có contract | Consumer ngoài phụ thuộc vào model nội bộ | Tạo integration contract và version policy |

## 12. Checklist hoàn thành producer

Trước khi xem producer đã sẵn sàng, xác nhận:

- Event diễn tả một sự thật nghiệp vụ đã xảy ra.
- Module phát sở hữu contract và công bố package phù hợp.
- Payload bất biến, không chứa entity hoặc service.
- Event ID ổn định qua retry và replay.
- Timestamp được tạo từ Clock có thể kiểm soát trong test.
- Use case thực hiện validation và thay đổi domain trong transaction.
- Event được publish trong đúng transaction nghiệp vụ.
- Listener cần after-commit được cấu hình theo semantics phù hợp.
- Producer không phụ thuộc implementation listener.
- Event Publication Registry được cấu hình và persistence phù hợp nếu cần phục hồi.
- Listener có idempotency và xử lý exception đúng policy.
- Unit/integration test xác minh event payload và nhánh lỗi.
- Externalization chỉ được bật khi có contract và consumer rõ ràng.

Tạo producer trong Spring Modulith là việc xác định đúng sự thật nghiệp vụ, công bố contract có owner và phát event trong transaction phù hợp. Khi producer giữ payload ổn định, không phụ thuộc listener và được kiểm thử ở ranh giới transaction, các module khác có thể phản ứng độc lập mà vẫn bảo vệ được tính nhất quán của nghiệp vụ.

