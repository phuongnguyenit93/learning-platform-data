# Event giữa các module

Trong ứng dụng **Spring Modulith**, các module nghiệp vụ có thể cùng chạy trong một tiến trình Spring Boot nhưng vẫn cần một cách giao tiếp không khiến module này phụ thuộc trực tiếp vào toàn bộ dịch vụ, repository và mô hình dữ liệu của module khác. **Application event giữa các module** là một cơ chế phù hợp khi module nguồn đã xác lập một sự thật nghiệp vụ và nhiều module khác cần phản ứng độc lập với sự thật đó.

Bài này thuộc chương **Event nội bộ và tích hợp** của mô-đun học **SPRING_MODULITH_APPLICATION_EVENTS**. Trọng tâm là cách dùng `ApplicationEventPublisher`, listener của Spring Modulith, xử lý sau commit và Event Publication Registry để tổ chức giao tiếp nội bộ đáng tin cậy; đồng thời chỉ rõ ranh giới giữa **event nội bộ ứng dụng** và **integration event** phải đi qua ranh giới tiến trình, broker hoặc mạng. Bài học cũng đề cập retry, idempotency, kiểm thử và quan sát quá trình giao sự kiện.

Mục tiêu sau khi học: bạn có thể tự thiết kế một luồng event từ module `orders` sang `loyalty`, `notifications`, `reporting`; giải thích ai sở hữu contract, điều gì xảy ra khi một listener lỗi sau commit, và khi nào cần thêm cơ chế tích hợp bên ngoài thay vì chỉ dùng Spring application events.

## 1. Tại sao cần event giữa các module?

Giả sử module `orders` thực hiện nghiệp vụ thanh toán. Sau khi trạng thái một đơn chuyển thành `PAID`, hệ thống muốn cộng điểm thưởng, gửi thông báo và cập nhật báo cáo. Một cách triển khai thường gặp là gọi tuần tự các service:

~~~java
// Ví dụ minh họa sự phụ thuộc trực tiếp, không phải thiết kế khuyến nghị.
@Transactional
public void confirmPayment(UUID orderId) {
    Order order = orderRepository.markPaid(orderId);

    loyaltyService.addPoints(order);
    notificationService.sendPaymentEmail(order);
    reportingService.recordRevenue(order);
}
~~~

Đoạn mã có những điểm bất lợi:

1. **Module nguồn biết các module nhận**: `orders` phải import `loyalty`, `notifications`, `reporting` và nắm thứ tự gọi của từng service.
2. **Phạm vi thay đổi mở rộng**: thêm một phản ứng mới như chống gian lận có thể buộc sửa `orders`, dù nghiệp vụ xác nhận thanh toán không đổi.
3. **Rủi ro side effect trong transaction**: email đã gửi không thể rollback nếu transaction database của `orders` thất bại.
4. **Lỗi lan truyền**: dịch vụ thông báo chậm hoặc ném exception có thể làm đường xử lý thanh toán chậm/hỏng theo.
5. **Ranh giới dữ liệu bị xói mòn**: để gọi tiện, các module có thể bắt đầu dùng entity hoặc repository nội bộ của nhau.

Nếu việc gửi email, cộng điểm và cập nhật báo cáo chỉ là **những phản ứng xảy ra sau khi thanh toán đã được xác lập**, `orders` có thể công bố một sự kiện có ý nghĩa: `OrderPaid`. Mỗi module nhận tự đăng ký listener và xử lý trách nhiệm của mình.

~~~mermaid
flowchart LR
    Client["Yêu cầu xác nhận thanh toán"] --> Orders["orders<br/>Nghiệp vụ thanh toán"]
    Orders --> Event(("OrderPaid"))
    Event --> Loyalty["loyalty<br/>Cộng điểm"]
    Event --> Notifications["notifications<br/>Tạo thông báo"]
    Event --> Reporting["reporting<br/>Cập nhật báo cáo"]
~~~

Trong sơ đồ này, **`orders` không điều phối từng consumer**. Nó chỉ sở hữu và công bố sự thật `OrderPaid`. `loyalty`, `notifications`, `reporting` đăng ký phản ứng theo nhu cầu nghiệp vụ và quản lý lỗi của chính mình.

Event không xóa hết mọi phụ thuộc. Các consumer vẫn phụ thuộc vào **hợp đồng `OrderPaid`**, bao gồm tên, field và ý nghĩa. Mục tiêu là làm phụ thuộc có hướng, có phạm vi, và giảm số chỗ phải sửa khi thêm hoặc bỏ một phản ứng.

## 2. Khái niệm: event nội bộ, integration event và message

Để không chọn sai hạ tầng, trước hết cần phân biệt **ranh giới giao tiếp**.

| Thuộc tính | Application event giữa các module | Integration event giữa các hệ thống |
| --- | --- | --- |
| **Phạm vi chủ yếu** | Các module trong cùng ứng dụng Spring Boot | Các ứng dụng, service, tiến trình hoặc tổ chức khác nhau |
| **Hợp đồng** | Kiểu Java được công bố trong API module, ví dụ `OrderPaid` | Schema giao tiếp ổn định qua mạng, ví dụ JSON/Avro/Protobuf |
| **Đường truyền** | Spring application event multicaster và listener | Broker, event bus, HTTP/webhook hoặc kênh tích hợp khác |
| **Ranh giới transaction** | Producer và registry có thể dùng cùng transaction database; listener hậu commit có transaction riêng | Không thể dùng một local database transaction để bảo đảm cả broker và mọi hệ thống ngoài đều commit |
| **Giao nhận lại** | Registry được cấu hình và resubmit publication chưa hoàn tất | Retry, acknowledgement, offset, outbox/inbox, dead-letter handling tùy công nghệ |
| **Biến đổi payload** | Có thể dùng các kiểu Java giàu ngữ nghĩa vừa đủ trong cùng ứng dụng | Cần chú trọng phiên bản schema, tương thích và không rò rỉ nội bộ |
| **Chi phí vận hành** | Thường ít hạ tầng hơn, nhưng vẫn cần theo dõi lỗi listener | Thêm broker/network, schema governance, bảo mật, retry liên tiến trình |

**“Event” diễn tả sự thật; “message” diễn tả một đơn vị được vận chuyển.** Một sự thật `OrderPaid` có thể tạo application event nội bộ và sau đó một integration message khác được gửi ra broker. Hai biểu diễn không nhất thiết cùng cấu trúc hoặc vòng đời.

Application events của Spring Modulith chủ yếu phục vụ liên lạc **bên trong một ứng dụng**. Việc dùng chúng không tự triển khai một topic Kafka, một queue RabbitMQ hay kênh liên tiến trình. Ngược lại, không phải mọi phản ứng nội bộ đều cần broker; thêm broker chỉ để hai module trong cùng JVM nói chuyện thường tăng chi phí vận hành không cần thiết.

### Event khác command

**Event** như `OrderPaid` có nghĩa “đơn đã được xác nhận thanh toán”. **Command** như `SendPaymentEmail` có nghĩa “hãy gửi email cho đơn này”. Sự khác nhau quan trọng khi thiết kế module:

- Producer của `OrderPaid` không quyết định module nào phải gửi email, cộng điểm hay ghi báo cáo.
- Consumer tự diễn giải `OrderPaid` và quyết định phản ứng của mình.
- Khi producer gửi một “event” có nội dung chỉ đạo module `loyalty` gọi một phương thức cụ thể, giao tiếp vẫn mang tính điều phối trực tiếp, chỉ khác phương tiện.

Không có quy tắc mọi command đều xấu. Nếu một bước đồng bộ bắt buộc có kết quả ngay để quyết định nghiệp vụ, gọi API/command rõ ràng có thể phù hợp hơn event hậu commit.

## 3. Tình huống mẫu và quyền sở hữu giữa các module

Xây dựng ứng dụng bán hàng minh họa với bốn module:

| Module | Sở hữu dữ liệu gì? | Vai trò trong luồng `OrderPaid` |
| --- | --- | --- |
| `orders` | Aggregate đơn hàng, trạng thái thanh toán, quy tắc transition | **Producer**, quyết định khi nào `OrderPaid` hợp lệ |
| `loyalty` | Ledger điểm thưởng và chính sách tích điểm | **Consumer**, cộng điểm khi thanh toán được chấp nhận |
| `notifications` | Yêu cầu gửi thông báo, template, trạng thái gửi | **Consumer**, chuẩn bị/gửi thông báo |
| `reporting` | Projection và số liệu doanh thu | **Consumer**, cập nhật thống kê |

Một cấu trúc package theo quy ước Spring Modulith có thể là:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderPaid.java
│   └── internal
│       ├── OrderPaymentService.java
│       └── OrderRepository.java
├── loyalty
│   └── internal
│       ├── LoyaltyOnOrderPaid.java
│       └── LoyaltyLedger.java
├── notifications
│   └── internal
│       ├── NotifyOnOrderPaid.java
│       └── NotificationRequests.java
└── reporting
    └── internal
        └── RevenueOnOrderPaid.java
~~~

`orders` sở hữu **contract** vì nó sở hữu sự thật nghiệp vụ. Các consumer được phép dùng contract công khai, nhưng không nên import `orders.internal.OrderRepository`, entity JPA hoặc service implementation của `orders`.

Với cơ chế phát hiện module mặc định, các subpackage thường là nội bộ trừ khi được công bố. Nếu muốn các consumer import `orders.events.OrderPaid`, hãy khai báo **named interface** ở `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Sau đó, `loyalty` có thể khai báo phụ thuộc được cho phép trong `loyalty/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.example.shop.loyalty;
~~~

Những tên này giả định module có định danh mặc định là `orders`. Nếu tên module được tùy biến, cú pháp phụ thuộc phải sử dụng đúng tên thực tế mà Spring Modulith nhận diện. **`@NamedInterface` và `allowedDependencies` là cơ chế kiểm soát phụ thuộc mã nguồn, không quyết định cách phân phối hay lưu trữ event**.

## 4. Thiết kế hợp đồng `OrderPaid` cho giao tiếp nội bộ

Event nên thể hiện một **mốc đã xảy ra**, có payload nhỏ, ý nghĩa rõ và đủ thông tin cho các consumer. Chọn các field theo trách nhiệm consumer, đồng thời giữ module nguồn có quyền thay đổi mô hình nội bộ.

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

/**
 * Đơn đã được orders chấp nhận chuyển trạng thái sang PAID.
 * Phản ứng hậu commit chỉ thực hiện khi transaction nguồn thành công.
 */
public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID paymentId,
        Instant occurredAt
) {}
~~~

Các field có vai trò khác nhau:

| Field | Ý nghĩa | Khi nào hữu ích? |
| --- | --- | --- |
| `eventId` | ID của một lần xảy ra event | Correlation, log, idempotency khi event được giao lại |
| `orderId` | ID aggregate đơn hàng | Liên kết báo cáo/thông báo với đơn |
| `customerId` | ID khách hàng | Định vị người nhận hoặc sổ điểm thưởng |
| `paymentId` | ID giao dịch thanh toán đã được xác thực | Ngăn producer tạo nhiều transition cho cùng payment; đối chiếu nghiệp vụ |
| `occurredAt` | Thời điểm producer ghi nhận transition và tạo event theo contract | Đo độ trễ, phân tích lịch sử |

`occurredAt` **không mặc nhiên là thời điểm database commit** và càng không phải thời điểm consumer đã xử lý. Cần tránh dùng `LocalDateTime.now()` ở nhiều máy với timezone không rõ ràng; dùng `Instant` cho timestamp tuyệt đối và `Clock` inject được để kiểm thử.

Những điều không nên đưa vào event:

- Entity JPA có lazy relation, persistence context hoặc object graph nội bộ;
- Spring bean, repository, service, kết nối database;
- Thông tin thanh toán nhạy cảm hoặc dữ liệu khách hàng vượt nhu cầu của consumer;
- Tập field “để dự phòng” khiến contract trở thành bản sao toàn bộ aggregate.

Nếu `reporting` cần giá trị doanh thu tại thời điểm thanh toán, có thể thêm một snapshot `paidAmount` và `currency` với định nghĩa rõ ràng, thay vì để reporting query trực tiếp entity nội bộ của `orders`. Nếu consumer cần dữ liệu hiện tại, hãy cân nhắc một public query API được công bố hoặc projection thuộc consumer.

### Contract thuộc producer, phản ứng thuộc consumer

`orders` quyết định `OrderPaid` chỉ được phát khi đơn **thật sự** chuyển sang PAID. Consumer `loyalty` quyết định cách tính điểm và cách chống cộng trùng. Consumer `notifications` quyết định có cần gửi email, chọn template và lưu trạng thái thông báo.

Đổi ý nghĩa `OrderPaid` thành “đã gửi yêu cầu thanh toán” dù tên và field không đổi sẽ làm hỏng contract. Cần tạo event đúng ngữ nghĩa như `PaymentRequested` hoặc `PaymentAuthorized` khi nghiệp vụ yêu cầu phân biệt các mốc khác nhau.

## 5. Producer phát event bằng `ApplicationEventPublisher`

Producer thường phát event sau khi đã xác định transition hợp lệ **trong transaction nghiệp vụ**. Cơ chế Spring phụ trách phân phối đến các listener; producer không cần import service của bất kỳ consumer nào.

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderPaid;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderPaymentService(
            OrderRepository orders,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void recordVerifiedPayment(UUID orderId, UUID paymentId) {
        Order order = orders.findById(orderId).orElseThrow();

        // Domain method minh họa: false nếu payment đã ghi nhận.
        boolean transitioned = order.markPaidIfNew(paymentId);
        if (!transitioned) {
            return;
        }

        orders.save(order);
        publisher.publishEvent(new OrderPaid(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                paymentId,
                clock.instant()
        ));
    }
}
~~~

`Order`, `OrderRepository` và `markPaidIfNew` là các kiểu/phương thức nghiệp vụ minh họa do dự án tự triển khai. `recordVerifiedPayment` giả định giao dịch thanh toán đã được xác minh qua nguồn đáng tin trước khi gọi; một `paymentId` do client tự nhập không đủ chứng minh đã trả tiền.

**Thứ tự logic** gồm kiểm tra điều kiện, thay đổi trạng thái và phát event trong cùng transaction. Tuy nhiên, **gọi `publishEvent` không tự cam kết database đã commit**, cũng không xác nhận consumer đã xử lý. Nếu transaction rollback, dữ liệu nguồn sẽ không bền vững; hành vi listener phụ thuộc vào loại listener được đăng ký.

Để producer không phát nhiều `OrderPaid` cho cùng một thanh toán, cần idempotency ở đầu vào và transition, có thể dựa vào một unique constraint theo payment reference. Nếu producer vô tình tạo hai **eventId khác nhau** cho cùng thanh toán, một consumer chống trùng chỉ bằng `eventId` có thể vẫn xử lý hai tác động riêng biệt.

## 6. Consumer đăng ký phản ứng trong module của mình

Một consumer dùng API event của producer nhưng không cần biết logic tạo đơn. Ví dụ `loyalty`:

~~~java
package com.example.shop.loyalty.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class LoyaltyOnOrderPaid {

    private final LoyaltyLedger ledger;

    LoyaltyOnOrderPaid(LoyaltyLedger ledger) {
        this.ledger = ledger;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        ledger.grantPointsOnce(
                event.eventId(),
                event.orderId(),
                event.customerId()
        );
    }
}
~~~

`grantPointsOnce` là phương thức minh họa của `LoyaltyLedger`, **không phải API Spring Modulith**. Nó cần được triển khai sao cho cùng event được giao lại không tạo thêm một khoản điểm. Sử dụng khóa duy nhất ở database, thao tác ghi ledger và cập nhật tổng điểm trong cùng transaction là một cách tiếp cận.

Consumer `notifications` có thể chỉ ghi yêu cầu gửi thông báo:

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class NotifyOnOrderPaid {

    private final NotificationRequests requests;

    NotifyOnOrderPaid(NotificationRequests requests) {
        this.requests = requests;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        requests.enqueueOnce(
                event.eventId(),
                event.customerId(),
                event.orderId()
        );
    }
}
~~~

`enqueueOnce` là phương thức nghiệp vụ minh họa. Consumer có thể lưu yêu cầu gửi trong transaction riêng, rồi một tác vụ khác gửi email và ghi trạng thái. Cách này giúp tách phần **đã tiếp nhận yêu cầu** khỏi phần **nhà cung cấp email đã thực sự chấp nhận**, vốn là tác dụng phụ ngoài database không thể rollback.

Ba listener quan tâm cùng loại event đều có thể nhận một `OrderPaid`; đây là kiểu **fan-out**, không phải queue cạnh tranh nơi chỉ một listener giành được message. Mỗi consumer có trách nhiệm và trạng thái hoàn thành độc lập, nên một consumer lỗi không có nghĩa tất cả phản ứng đều phải làm lại.

## 7. Chọn thời điểm nhận: đồng bộ hay sau commit?

Đây là điểm kỹ thuật quyết định event giữa các module có an toàn khi nghiệp vụ nguồn rollback hay không.

| Listener | Thời điểm thường gặp | Tác động quan trọng |
| --- | --- | --- |
| `@EventListener` | Mặc định đồng bộ ngay trong lời gọi `publishEvent` với multicaster chuẩn | Có thể chạy trước commit, lỗi có thể truyền về producer |
| `@TransactionalEventListener(phase = AFTER_COMMIT)` | Khi transaction phát event đã commit thành công | Không tự bất đồng bộ hoặc mở transaction mới |
| `@ApplicationModuleListener` | Tiện ích Spring Modulith cho xử lý sau commit, bất đồng bộ và transaction riêng | Phù hợp phản ứng độc lập, kết quả có thể đến muộn hơn transaction nguồn |

`@ApplicationModuleListener` về mặt ý tưởng kết hợp transactional event listener hậu commit, `@Async` và transaction mới (`REQUIRES_NEW`). Khi consumer cần ghi dữ liệu sau commit, transaction riêng giúp tránh nhầm việc ghi trong resource cũ đã hoàn tất.

Sơ đồ dưới đây mô tả listener hậu commit trong ứng dụng đã cấu hình cơ chế phù hợp:

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders / Producer
    participant DB as Database
    participant Events as Application events
    participant Loyalty as loyalty
    participant Notify as notifications

    Client->>Orders: recordVerifiedPayment(...)
    Orders->>DB: Lưu trạng thái PAID trong T1
    Orders->>Events: publishEvent(OrderPaid)
    Note over Orders,Events: Event được phát khi T1 còn hoạt động
    Orders->>DB: Commit T1
    par Consumer phản ứng độc lập
        Events-->>Loyalty: OrderPaid sau commit
        Loyalty->>DB: Ghi ledger trong T2
    and
        Events-->>Notify: OrderPaid sau commit
        Notify->>DB: Tạo yêu cầu gửi trong T3
    end
~~~

Sơ đồ chỉ mô tả **quan hệ logic giữa các bước**; trong thực tế listener có thể bắt đầu ngay sau commit và chạy đồng thời với luồng chuẩn bị trả response HTTP. Không nên dựa vào việc HTTP response đến trước hay sau callback của listener.

### Điều gì xảy ra khi rollback?

Giả sử producer chuyển `PAID`, phát `OrderPaid`, rồi vi phạm constraint khi commit. Khi đó:

- Dữ liệu `PAID` không được commit.
- `@EventListener` đồng bộ có thể **đã chạy trước khi rollback**.
- Listener `AFTER_COMMIT` không nên được kích hoạt cho transaction đã rollback.
- Nếu đã cấu hình ghi publication trong cùng transaction nguồn, các publication chưa commit cũng bị rollback.

Vì vậy email, cộng điểm hoặc side effect không thể hoàn tác thường nên thực hiện sau khi transaction nguồn commit. Nếu một phản ứng **phải** quyết định tính hợp lệ của transaction nguồn, nó có thể cần một lời gọi đồng bộ hoặc một quy trình trạng thái rõ ràng; không chuyển sang async chỉ vì muốn giảm coupling.

## 8. Độ bền của event: Registry và khoảng trống sau commit

`@ApplicationModuleListener` hỗ trợ cách chạy sau commit nhưng **bất đồng bộ trong cùng JVM không mặc nhiên bền vững**. Hãy xét chuỗi:

1. `orders` commit thành công, `OrderPaid` hợp lệ.
2. Tiến trình bị dừng trước khi `loyalty` nhận event hoặc đánh dấu xử lý hoàn tất.
3. Sau restart, hệ thống phải biết còn một phản ứng cần thực hiện.

Spring Modulith cung cấp **Event Publication Registry** để theo dõi việc publication cho các transactional listener được hỗ trợ. Khi cấu hình kho lưu trữ publication bền vững, và khi publisher phát event bên trong transaction nguồn phù hợp, bản ghi publication có thể cùng commit với dữ liệu nguồn. Sau khi listener thành công, publication tương ứng được ghi nhận hoàn tất.

~~~mermaid
flowchart TD
    A["orders cập nhật trạng thái trong T1"] --> B["Publish OrderPaid trong T1"]
    B --> C["Registry ghi publication theo listener"]
    C --> D{"T1 có commit?"}
    D -->|"Không"| E["Rollback dữ liệu nguồn và publication"]
    D -->|"Có"| F["Dữ liệu nguồn và publication tồn tại"]
    F --> G["Consumer nhận event sau commit"]
    G --> H{"Consumer hoàn tất?"}
    H -->|"Có"| I["Publication được đánh dấu hoàn tất"]
    H -->|"Không hoặc crash"| J["Publication chưa hoàn tất"]
    J --> K["Kiểm tra lỗi, resubmit có kiểm soát"]
    K --> G
~~~

Một số điểm phải kiểm tra theo **phiên bản Spring Modulith thực tế**:

- Đã thêm và cấu hình integration lưu publication tương ứng, chẳng hạn JDBC hoặc JPA, cùng schema/database cần thiết hay chưa?
- Khi publisher phát trong transaction, publication có tham gia **cùng transaction** với thay đổi nguồn hay không?
- Listener nào được registry theo dõi, trạng thái “chưa hoàn tất” được đọc ở đâu?
- Cơ chế khôi phục/resubmit được kích hoạt như thế nào và lịch retry có phù hợp nghiệp vụ hay không?
- Hệ thống xử lý publication lỗi vĩnh viễn, trùng lặp và tồn đọng quá lâu ra sao?

Chỉ có annotation `@ApplicationModuleListener` chưa đủ để kết luận “event sẽ không mất” hoặc “tự động retry vô hạn”. Registry cũng không tạo transaction nguyên tử xuyên qua database của các service ngoài, email provider và broker.

### Mỗi consumer có một rủi ro riêng

| Trạng thái | `orders` | `loyalty` | `notifications` |
| --- | --- | --- | --- |
| Transaction nguồn rollback | Không có `PAID` đã commit | Không xử lý hậu commit | Không xử lý hậu commit |
| Nguồn commit, cả hai thành công | `PAID` | Đã ghi điểm | Đã tạo yêu cầu gửi |
| Nguồn commit, loyalty lỗi | `PAID` | Publication còn chờ hoặc lỗi | Có thể đã hoàn tất |
| Loyalty ghi điểm rồi crash trước completion | `PAID` | Có thể nhận cùng event lần nữa | Không cần tự động làm lại phần đã hoàn tất |

Nhờ phân chia theo listener, có thể khôi phục nhánh `loyalty` còn dang dở mà không cần yêu cầu `orders` “thanh toán lại” hoặc phát một sự thật nghiệp vụ mới.

## 9. Idempotency: nhận lại event nhưng không làm lại tác động

Nếu registry hoặc cơ chế retry gửi lại cùng `OrderPaid`, consumer có thể được gọi nhiều lần. Đây là tình huống phải dự kiến khi làm việc với xử lý **at-least-once**.

Ví dụ sai:

~~~java
void on(OrderPaid event) {
    customerBalance.addPoints(10); // Giao lại event => cộng thêm 10.
}
~~~

Một ledger có khóa duy nhất cho event là cách mạnh hơn:

~~~sql
CREATE TABLE loyalty_awards (
    id BIGINT PRIMARY KEY,
    source_event_id VARCHAR(36) NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    points INTEGER NOT NULL,
    CONSTRAINT uq_loyalty_awards_event UNIQUE (source_event_id)
);
~~~

Trong transaction consumer, thực hiện nghiệp vụ ghi ledger và cập nhật điểm sao cho **chỉ một lần ghi cho `source_event_id` được phép thành công**. Unique constraint bảo vệ cả trường hợp hai lần giao nhận trùng được xử lý song song. Kiểm tra `SELECT exists` rồi `INSERT` mà không có ràng buộc database vẫn có thể race.

Nếu một consumer thực hiện nhiều loại tác động cho cùng event, khóa thích hợp có thể là cặp `(consumer_name, event_id)` hoặc một khóa nghiệp vụ cụ thể. Phân biệt:

- **Trùng event**: cùng `eventId` được giao lại sau retry.
- **Trùng nghiệp vụ**: producer tạo hai `eventId` cho cùng một payment reference do xử lý webhook chưa idempotent.

Consumer cần bảo vệ trùng event; producer cũng phải chống trùng nghiệp vụ. Với email hoặc API ngoài, transaction database không thể tự rollback một side effect đã xảy ra. Cần idempotency key ở provider nếu có, bảng yêu cầu gửi và cách xử lý trạng thái chưa chắc chắn.

Đừng nuốt exception rồi trả thành công khi tác dụng quan trọng chưa hoàn tất: registry có thể coi publication đã được xử lý, làm mất cơ hội retry đúng lúc.

## 10. Khi nào event nội bộ trở thành integration event?

Một ngày, hệ thống có thêm ứng dụng `fulfillment-service` chạy độc lập, cần biết đơn đã thanh toán để chuẩn bị đóng gói. `fulfillment-service` không còn là module trong cùng JVM, nên **Spring ApplicationEventPublisher tự nó không truyền `OrderPaid` đến service đó**.

Một thiết kế rõ ràng thường gồm:

1. `orders` vẫn công bố **`OrderPaid` nội bộ** theo contract module.
2. Một adapter/integration component trong ứng dụng chuyển đổi `OrderPaid` thành **hợp đồng xuất bản ra ngoài** như `OrderPaymentConfirmedV1`.
3. Cơ chế externalization/outbox hoặc integration phù hợp đưa integration message tới broker/kênh ngoài.
4. `fulfillment-service` đọc message, xác thực schema, nhận diện trùng và xử lý theo transaction riêng của nó.

~~~mermaid
flowchart LR
    Orders["orders"] --> DomainEvent(("OrderPaid<br/>Internal event"))
    DomainEvent --> Loyalty["loyalty<br/>Listener nội bộ"]
    DomainEvent --> Adapter["Integration adapter<br/>Mapping + externalization"]
    Adapter --> Outbox["Outbox/publication<br/>Cấu hình bền vững"]
    Outbox --> Broker["Broker hoặc kênh mạng"]
    Broker --> Fulfillment["fulfillment-service<br/>Consumer ngoài tiến trình"]
~~~

Spring Modulith có các khả năng hỗ trợ externalization cho các hạ tầng tích hợp nhất định, nhưng dependency, annotation, routing và semantics xác nhận gửi phụ thuộc **phiên bản cùng adapter cụ thể**. Không nên giả định chỉ cần đánh dấu một Java event là đã bảo đảm giao nhận liên tiến trình đúng một lần. Nếu dùng outbox, phải xác minh ranh giới transaction giữa dữ liệu nguồn và bản ghi cần xuất, tiến trình gửi, xác nhận từ broker và xử lý lại khi crash.

### Vì sao tách hai hợp đồng?

| Internal event `OrderPaid` | Integration event `OrderPaymentConfirmedV1` |
| --- | --- |
| Sử dụng giữa các module trong cùng ứng dụng | Được đối tác/service khác nhận qua kênh ngoài |
| Có thể dùng Java record đơn giản và biên dịch cùng codebase | Cần schema, encoding, tiêu chuẩn tương thích theo phiên bản |
| Thay đổi cùng tiến trình build/deploy ứng dụng | Người nhận có thể triển khai độc lập và dùng phiên bản cũ |
| Chỉ cần payload đủ cho consumer nội bộ | Tránh rò rỉ dữ liệu, có thể cần mapping hoặc giảm field |
| Lỗi listener được quản lý trong ranh giới Modulith/registry | Lỗi broker/network/consumer ngoài cần cơ chế xác nhận, DLQ, retry riêng |

Một event nội bộ **không bắt buộc** phải được externalize; ngược lại một integration event có thể được tạo từ một mốc nghiệp vụ duy nhất với schema riêng. Phải xác định ai sở hữu contract ngoài, chính sách phiên bản và trách nhiệm khi người nhận chưa xử lý.

### Transaction và outbox qua ranh giới tiến trình

Một lỗi thiết kế là:

~~~java
@Transactional
void confirmPayment(...) {
    orderRepository.save(order);
    brokerClient.send(message); // Có thể gửi thành công dù DB rollback.
}
~~~

Transaction database cục bộ **không tự khiến việc gửi mạng nằm trong cùng transaction**. Nếu broker đã nhận message nhưng DB rollback, service khác có thể xử lý một trạng thái chưa tồn tại. Ngược lại, nếu DB commit rồi broker lỗi, message có thể thất lạc nếu không có cơ chế ghi lại ý định xuất bản.

Outbox hoặc cơ chế externalization bền vững phù hợp ghi **ý định gửi** cùng transaction dữ liệu nguồn, sau đó một thành phần khác truyền ra kênh ngoài và retry. Việc broker nhận message vẫn cần xác nhận và xử lý trùng ở phía nhận. Cách này khác với giả định “publisher nội bộ xong là integration event đã đến mọi service”.

## 11. Những trường hợp không nên dùng event bất đồng bộ

Event giữa các module hiệu quả cho phản ứng có thể hoàn thành sau nghiệp vụ nguồn. Nhưng một số bất biến phải được bảo vệ **trước khi hệ thống thông báo thành công**.

| Nhu cầu | Giải pháp nên cân nhắc | Lý do |
| --- | --- | --- |
| Đặt hàng chỉ hợp lệ nếu giữ kho thành công | Gọi đồng bộ/transaction phù hợp hoặc quy trình trạng thái `PENDING` được điều phối | Không thể trả `CONFIRMED` rồi hy vọng listener giữ kho thành công sau |
| Tính phí vận chuyển để hiển thị ngay trong response | Query hoặc service API đồng bộ có contract rõ | Người gọi cần kết quả tức thời |
| Gửi email xác nhận sau khi đơn đã thanh toán | Event hậu commit, consumer notifications | Email không cần quyết định commit thanh toán |
| Ghi điểm thưởng có thể chậm vài giây | Event hậu commit + idempotency | Cho phép eventual consistency |
| Bắt buộc nhiều bước chạy theo thứ tự | Workflow/process manager hoặc event theo từng mốc trạng thái | Listener bất đồng bộ không tự bảo đảm thứ tự |
| Xuất dữ liệu sang service ngoài | Integration event, broker/outbox và contract riêng | Ranh giới tiến trình cần cơ chế phân phối ngoài JVM |

Đừng lấy việc giảm coupling làm lý do che giấu một quy tắc quan trọng. Nếu `OrderPaid` chỉ hợp lệ khi kho còn hàng, phải xác định chính xác mốc khi nào đơn trở thành `PAID`, `CONFIRMED` và khi nào cần hoàn tác/đền bù; event là công cụ biểu đạt các mốc đó, không tự giải bài toán transaction phân tán.

## 12. Kiểm thử giao tiếp giữa các module

Một bài test chỉ xác nhận `publishEvent` được gọi không chứng minh event giao đúng sau commit hay được khôi phục sau lỗi. Cần phân lớp kiểm thử.

### Kiểm tra cấu trúc module

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTests {

    @Test
    void dependenciesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đoạn mã giả định `ShopApplication` nằm tại package gốc và dự án có dependency Spring Modulith cần thiết. `verify()` kiểm tra ranh giới phụ thuộc, không tự kiểm tra nội dung ledger hay độ bền của publication.

### Ma trận tình huống cần thử

| Tình huống | Kỳ vọng |
| --- | --- |
| `orders` thanh toán hợp lệ lần đầu | Phát một `OrderPaid` đúng contract |
| Webhook thanh toán trùng `paymentId` | Không phát một transition nghiệp vụ mới |
| Transaction `orders` rollback sau publish | Listener hậu commit không tạo hiệu ứng |
| Transaction `orders` commit | `loyalty` và `notifications` xử lý độc lập |
| Một listener thất bại, listener khác thành công | Nghiệp vụ nguồn vẫn commit; thấy nhánh còn dang dở |
| Registry bền vững có publication chưa hoàn tất | Có thể tìm và resubmit sau khi xử lý nguyên nhân |
| Retry cùng `eventId` | Không tạo thêm điểm thưởng hoặc thông báo không hợp lệ |
| Consumer đồng thời xử lý trùng | Unique constraint bảo vệ hiệu ứng duy nhất |
| Import kiểu từ `orders.internal` | Kiểm tra module boundary phát hiện vi phạm |
| Đưa integration event ra broker nhưng broker lỗi | Ý định gửi còn tồn tại theo cơ chế outbox/externalization đã chọn |

Spring Modulith cung cấp các tiện ích kiểm thử module như `@ApplicationModuleTest`, `PublishedEvents` và `Scenario`; chọn cách dùng theo phiên bản và dependency test trong dự án. Với listener hậu commit, test phải để transaction nguồn **thực sự commit**. Một test dùng `@Transactional` và rollback ở cuối có thể khiến callback `AFTER_COMMIT` không chạy. Với async, dùng cách chờ theo điều kiện và giới hạn thời gian, tránh `Thread.sleep` cố định.

Đối với registry, cần ít nhất một kiểm thử tích hợp có storage thực hoặc tương đương để chứng minh publication bị rollback đúng lúc, publication lỗi còn dấu vết, và resubmit không nhân đôi tác dụng nghiệp vụ.

## 13. Quan sát: một event, nhiều consumer

Khi người dùng báo “đã thanh toán nhưng chưa được cộng điểm”, hệ thống cần trả lời được **producer đã commit chưa, listener nào nhận event, listener nào hoàn tất, publication nào còn tồn đọng**. Log mỗi lần publish là chưa đủ.

| Tín hiệu | Giá trị thực tế |
| --- | --- |
| `eventId`, `eventType`, `orderId`, `paymentId` | Tra theo một lần xảy ra và liên kết với nghiệp vụ |
| `module`, `listenerName` | Phân biệt phản ứng của từng consumer |
| `occurredAt`, `receivedAt`, `completedAt` | Đo độ trễ và nhận diện nơi bị kẹt |
| Số publication chưa hoàn tất | Xác định công việc hậu commit đang tồn đọng |
| Tuổi publication lớn nhất | Phát hiện sự kiện lỗi hoặc bị bỏ quên lâu ngày |
| Retry count / exception category | Phân loại lỗi tạm thời, lỗi dữ liệu, lỗi tích hợp |
| Duplicate suppressed | Biết idempotency đã chặn bao nhiêu lần giao lại |
| Broker acknowledgement / outbox backlog (nếu externalize) | Phân biệt hỏng nội bộ với hỏng kênh tích hợp ngoài |

Có thể dùng structured logs và tracing với correlation ID để theo luồng producer → registry → từng consumer. Không log toàn bộ payload nếu chứa dữ liệu cá nhân, token thanh toán hoặc thông tin nhạy cảm.

Quy trình xử lý production nên gồm: tra `eventId`, xác nhận trạng thái nguồn, xem publication của listener, xác định lỗi, kiểm tra tác động đã xảy ra chưa, sửa nguyên nhân, resubmit có kiểm soát và xác nhận side effect đúng một lần. **Không đánh dấu publication hoàn tất thủ công chỉ vì muốn xóa cảnh báo**, khi chưa xác định điều gì đã xảy ra tại consumer.

## 14. Bài tập thực hành tổng hợp

### Đề bài

Thiết kế ứng dụng quản lý đặt vé có bốn module trong cùng Spring Boot:

- `payments`: ghi nhận thanh toán thành công;
- `tickets`: phát hành vé sau thanh toán;
- `notifications`: thông báo cho khách;
- `analytics`: cập nhật thống kê.

Ngoài ra có `partner-fulfillment` là một **service riêng chạy độc lập**, cần biết vé đã phát hành để chuẩn bị dịch vụ đi kèm.

Yêu cầu hệ thống: không phát hành trùng vé dù nhận `PaymentCompleted` nhiều lần; không gửi thông báo cho transaction thanh toán rollback; khi consumer hỏng sau commit phải có cách tìm việc chưa hoàn tất và xử lý lại.

### Các bước cần thực hiện

1. Tạo **`PaymentCompleted` nội bộ** thuộc public API của `payments` với `eventId`, `paymentId`, `reservationId`, `occurredAt`.
2. Tạo named interface `payments::events` và chỉ cho các module nhận phụ thuộc vào contract cần thiết.
3. Viết producer dùng `ApplicationEventPublisher`, phát sau transition thanh toán hợp lệ trong transaction.
4. Viết listener `@ApplicationModuleListener` trong `tickets` và `analytics`. Listener `tickets` lưu `paymentId` hoặc khóa nghiệp vụ tương đương với unique constraint.
5. Thiết kế `TicketIssued` do module `tickets` sở hữu và cho `notifications` phản ứng khi vé thực sự được phát hành, nếu đó là mốc đúng nghiệp vụ.
6. Cấu hình Event Publication Registry và tình huống làm `tickets` lỗi sau commit; kiểm tra publication chưa hoàn tất rồi phục hồi.
7. Thiết kế **integration event riêng**, ví dụ `TicketIssuedV1`, cho `partner-fulfillment`; mô tả mapping, schema, outbox/broker và cơ chế chống trùng phía nhận.
8. Viết test cho rollback, một consumer lỗi, trùng event, quyền phụ thuộc module và khoảng thời gian sau commit.
9. Thêm log và metric để người vận hành tra một `eventId` và biết đã xử lý tới đâu.

### Câu hỏi đánh giá

**1. Vì sao `tickets` nên nghe `PaymentCompleted` thay vì `payments` gọi trực tiếp `TicketService.issue(...)`?**

Nếu việc phát hành vé là phản ứng độc lập sau thanh toán, consumer có thể sở hữu quy tắc phát hành, idempotency và retry. `payments` không phải phụ thuộc vào implementation của `tickets`. Nếu nghiệp vụ yêu cầu phát hành vé hoàn tất ngay trước khi xác nhận thanh toán cho khách, cần định nghĩa workflow/trạng thái và điều kiện thành công tương ứng, không giả định async là đủ.

**2. Event nội bộ có tự đến `partner-fulfillment` không?**

Không. Service ở tiến trình khác cần một đường phân phối như broker/webhook và hợp đồng integration event; Spring application event mặc định không chạy qua mạng.

**3. Nếu `tickets` đã tạo vé nhưng crash trước khi registry ghi completion, có được tạo vé thứ hai khi retry?**

Không được. Consumer cần ghi dấu xử lý dựa trên event hoặc khóa nghiệp vụ và ràng buộc duy nhất trong transaction. Registry có thể giao lại event, vì vậy không được dựa vào giả định listener chỉ chạy một lần.

**4. `notifications` và `analytics` có phải hoàn thành cùng lúc không?**

Không. Mỗi listener có trạng thái và độ trễ riêng. Chỉ những bước bị buộc chung bởi một bất biến nghiệp vụ mới cần điều phối chặt hơn; phản ứng độc lập có thể nhất quán cuối cùng.

**5. Tại sao không gửi thẳng Java entity JPA của `tickets` cho service bên ngoài?**

Vì đó là mô hình nội bộ, khó tương thích và có nguy cơ lộ dữ liệu. Integration event cần schema ổn định, các ID/snapshot cần thiết và chính sách phiên bản rõ ràng.

## 15. Checklist khi thiết kế event giữa các module

- [ ] Xác định một **sự thật nghiệp vụ** đủ rõ để đặt tên event ở thì quá khứ.
- [ ] Producer sở hữu contract và phát event đúng khi transition được chấp nhận.
- [ ] Contract được công bố qua API module, consumer không import package nội bộ.
- [ ] Không truyền entity JPA, bean Spring hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Một event có thể được nhiều listener nhận; mỗi listener có trách nhiệm riêng.
- [ ] Chọn đồng bộ/hậu commit theo bất biến nghiệp vụ và rủi ro rollback.
- [ ] Publish trong transaction nguồn khi cần liên kết atomic publication với dữ liệu nguồn.
- [ ] Đã cấu hình persistence, recovery và theo dõi Event Publication Registry nếu cần giao bền vững.
- [ ] Có idempotency ở producer đối với input trùng và ở consumer đối với event giao lại.
- [ ] Xử lý lỗi tạm thời/lỗi vĩnh viễn bằng retry có kiểm soát và cảnh báo.
- [ ] Không cho rằng listener async luôn hoàn tất theo thứ tự hoặc ngay lúc response.
- [ ] Phân biệt application event nội bộ với integration event xuất sang tiến trình khác.
- [ ] Nếu externalize, có schema, outbox/broker, acknowledgement và xử lý nhận trùng phù hợp.
- [ ] Kiểm thử rollback, commit, lỗi sau commit, restart, idempotency và module boundary.
- [ ] Quan sát trạng thái publication và độ trễ theo từng listener/eventId.

## Ghi nhớ

**Event giữa các module** trong Spring Modulith giúp một module công bố sự thật nghiệp vụ qua `ApplicationEventPublisher` và để các module khác xử lý bằng listener mà không phải phụ thuộc trực tiếp vào implementation của nhau. Bảo vệ ranh giới module bằng public event contract và named interface; bảo vệ ý nghĩa nghiệp vụ bằng việc chọn đúng thời điểm phát và xử lý sau commit khi cần.

Khi một consumer có thể lỗi sau commit, **Event Publication Registry** với storage và chính sách recovery phù hợp giúp theo dõi publication chưa hoàn tất; **retry và idempotency** giúp xử lý việc giao lại. Các cơ chế này áp dụng cho giao tiếp nội bộ trong ứng dụng. Khi sự kiện cần đến một service độc lập, hãy thiết kế thêm **integration event, schema, cơ chế gửi bền vững và xác nhận nhận** tương ứng. Sự phân biệt đó giúp tận dụng Spring Modulith để giảm phụ thuộc giữa module, đồng thời giữ được tính đúng đắn và khả năng quan sát của luồng sự kiện.

