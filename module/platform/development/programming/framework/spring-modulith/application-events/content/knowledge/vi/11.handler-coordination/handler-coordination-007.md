# Fan-out event trong Spring Modulith: một sự kiện, nhiều handler độc lập

## 1. Fan-out event là gì?

**Fan-out event** là cách một sự kiện được công bố **một lần** nhưng có thể được **nhiều listener (handler/subscriber)** quan tâm tiếp nhận và xử lý. Trong Spring Modulith, đây là một hình thức giao tiếp giữa các application module: module sở hữu nghiệp vụ phát ra sự thật đã xảy ra, các module khác tự đăng ký phản ứng theo trách nhiệm của mình.

Ví dụ, khi `orders` tạo đơn hàng thành công, một sự kiện `OrderPlaced` có thể kích hoạt:

- `notifications`: gửi xác nhận đặt hàng.
- `loyalty`: xét và cộng điểm thưởng.
- `analytics`: cập nhật chỉ số đơn hàng.
- `audit`: ghi nhật ký nghiệp vụ.

Publisher **không gọi bốn service trên**, không cần biết số lượng handler, và không phải chỉnh sửa khi thêm một consumer mới.

~~~mermaid
flowchart LR
    O["orders<br/>OrderService"] -->|"publish OrderPlaced"| E(("OrderPlaced"))
    E --> N["notifications<br/>SendConfirmation"]
    E --> L["loyalty<br/>AwardPoints"]
    E --> A["analytics<br/>ProjectOrder"]
    E --> U["audit<br/>RecordOrder"]
~~~

Trong chương **Điều phối handler** của `SPRING_MODULITH_APPLICATION_EVENTS`, trọng tâm là thiết kế **phân phối một sự kiện đến nhiều handler mà vẫn giữ ranh giới nghiệp vụ, xử lý được lỗi từng consumer và theo dõi được trạng thái giao sự kiện**.

> Fan-out là **một sự kiện → nhiều phản ứng độc lập**, không có nghĩa nhiều handler chắc chắn hoàn thành cùng lúc hoặc tất cả đều thành công.

### Mục tiêu học tập

Sau bài này, người học có thể giải thích sự khác nhau giữa fan-out và cân bằng công việc, triển khai các listener ở nhiều module, chọn cơ chế xử lý sau commit, thiết kế idempotency riêng cho từng handler, nhận diện hậu quả của partial failure và kiểm thử/quan sát một sự kiện được xử lý bởi nhiều consumer.

## 2. Phân biệt fan-out, gọi trực tiếp và competing consumers

Ba cách phối hợp công việc nhìn bề ngoài khá giống nhưng có ý nghĩa khác nhau.

| Cách phối hợp | Cách vận hành | Hệ quả |
| --- | --- | --- |
| **Gọi service trực tiếp** | `orders` gọi lần lượt `notificationService`, `loyaltyService`, `analyticsService`. | Publisher biết trực tiếp các consumer và phụ thuộc vào chữ ký API, thời gian phản hồi, lỗi của chúng. |
| **Fan-out event** | `orders` công bố `OrderPlaced`; mỗi listener quan tâm có cơ hội xử lý. | Publisher không cần biết consumer. Mỗi module tự quyết định phản ứng. |
| **Competing consumers / work-sharing** | Nhiều worker cạnh tranh lấy các job từ cùng hàng đợi, mỗi job thường do một worker nhận theo cơ chế queue. | Mục đích chính là chia tải công việc, không phải mỗi worker đều thực hiện cùng một event. |

**Spring application events trong cùng một `ApplicationContext` không mặc nhiên là hàng đợi competing consumers**. Khi có ba listener đăng ký cho `OrderPlaced`, ý nghĩa phổ biến là **cả ba listener đều có thể nhận cùng một lần công bố**. Nếu muốn mô hình nhiều worker chỉ một worker thực hiện mỗi job, phải thiết kế cơ chế phân công công việc khác, không suy ra từ fan-out.

Tương tự, fan-out trong Spring Modulith **không đồng nghĩa phát sang Kafka hoặc RabbitMQ**. `ApplicationEventPublisher` vận hành trong cơ chế application event của Spring; việc truyền ra broker là một quyết định tích hợp riêng và có thể sử dụng hợp đồng integration event khác.

## 3. Ví dụ xuyên suốt: một đơn hàng, bốn kết quả

Giả sử khách hàng đặt đơn `O-100` trị giá 550.000 VND. Phần nghiệp vụ của `orders` có trách nhiệm tạo đơn và xác định sự thật `OrderPlaced`. Sau khi commit thành công, hệ thống mong muốn bốn kết quả:

| Consumer | Tác vụ | Có cần kết quả ngay để chấp nhận đơn? |
| --- | --- | --- |
| Notifications | Gửi xác nhận. | Không; có thể hoàn tất sau commit. |
| Loyalty | Cộng điểm nếu đủ điều kiện. | Không, với chính sách minh họa này. |
| Analytics | Ghi vào projection thống kê đơn đã đặt. | Không; chấp nhận cập nhật trễ. |
| Audit | Ghi nhận dấu vết sự kiện. | Tùy yêu cầu tuân thủ; nếu bắt buộc nguyên tử với đặt đơn thì không thể chỉ dựa vào listener bất đồng bộ. |

Ví dụ minh họa sử dụng ba consumer đầu tiên dưới dạng `@ApplicationModuleListener`. Audit có thể có thiết kế khác nếu hệ thống yêu cầu dữ liệu kiểm toán bắt buộc phải commit trong cùng transaction với đơn hàng.

Không phải mọi chức năng “được kích hoạt sau đặt đơn” đều nên fan-out. Chẳng hạn xác thực hạn mức tín dụng *trước khi chấp nhận đơn* cần một kết quả nghiệp vụ rõ ràng; không nên gửi `OrderPlaced` rồi hy vọng một listener bất đồng bộ sẽ kịp từ chối đơn.

## 4. Mỗi module sở hữu một phần việc

Một package layout tham khảo cho cách phát hiện module mặc định của Spring Modulith:

~~~text
com/acme/shop/
├── ShopApplication.java
├── orders/
│   ├── events/
│   │   ├── package-info.java       # @NamedInterface("events")
│   │   └── OrderPlaced.java
│   └── internal/
│       ├── OrderService.java
│       ├── OrderRepository.java
│       └── OrderEntity.java
├── notifications/
│   ├── package-info.java
│   └── internal/
│       ├── SendOrderConfirmation.java
│       └── ConfirmationService.java
├── loyalty/
│   ├── package-info.java
│   └── internal/
│       ├── AwardPointsForOrder.java
│       └── LoyaltyService.java
└── analytics/
    ├── package-info.java
    └── internal/
        ├── ProjectOrderPlaced.java
        └── OrderProjectionRepository.java
~~~

Các quy tắc sở hữu:

1. **Orders sở hữu `OrderPlaced`.** Module này biết khi nào đơn được chấp nhận theo quy tắc nghiệp vụ.
2. **Notifications sở hữu listener gửi xác nhận.** Nó quyết định mẫu email, kênh gửi và chính sách chống trùng.
3. **Loyalty sở hữu listener cộng điểm.** Nó giữ quy tắc điểm và kiểm soát ghi điểm.
4. **Analytics sở hữu listener tạo projection.** Nó quản lý dữ liệu và độ trễ báo cáo.
5. **Không consumer nào import `orders.internal`.** Consumer chỉ thấy hợp đồng event công khai.

Nếu `OrderPlaced` nằm tại package con `orders.events`, có thể công khai package bằng named interface:

~~~java
// File: orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Ví dụ giới hạn phụ thuộc của notifications:

~~~java
// File: notifications/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.acme.shop.notifications;
~~~

Loyalty và analytics cũng có thể khai báo `allowedDependencies = "orders::events"` theo nhu cầu. Annotation này **không phát hoặc đăng ký event**; nó mô tả **phụ thuộc mã nguồn được phép** giữa các module. Đăng ký listener vẫn thông qua Spring bean và annotation listener.

Nếu event đặt trực tiếp ở package gốc `orders`, nó thuộc API mặc định của module; không bắt buộc tạo named interface riêng.

## 5. Thiết kế một hợp đồng dùng chung, không phục vụ riêng một handler

Event nên mô tả **sự thật nghiệp vụ** chứ không đưa chỉ thị của consumer vào payload.

~~~java
package com.acme.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        BigDecimal totalAmount,
        String currencyCode,
        Instant occurredAt
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(totalAmount, "totalAmount");
        Objects.requireNonNull(currencyCode, "currencyCode");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (totalAmount.signum() < 0) {
            throw new IllegalArgumentException("Negative totalAmount");
        }
        if (!currencyCode.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currencyCode");
        }
    }
}
~~~

Ý nghĩa của từng field:

| Field | Vai trò |
| --- | --- |
| `eventId` | ID ổn định của **một lần xảy ra sự kiện**, giúp trace và chống xử lý trùng. |
| `orderId` | Tham chiếu đơn hàng, không thay thế event ID. |
| `customerId` | ID khách hàng để consumer liên hệ đối tượng phù hợp nếu có quyền truy cập. |
| `totalAmount` và `currencyCode` | Giá trị đã chốt và đơn vị tiền tệ của đơn. |
| `occurredAt` | Thời điểm nghiệp vụ được ghi nhận; không phải lúc handler hoàn tất. |

Việc đưa `customerId` và số tiền vào event phải xuất phát từ nhu cầu thật của các consumer. Không nên cho toàn bộ hồ sơ khách hàng, token hay dữ liệu thẻ vào một event mà nhiều module có thể nhận.

**Không nên định nghĩa:**

~~~java
public record OrderPlaced(
        UUID orderId,
        boolean sendEmail,
        boolean awardPoints,
        boolean updateAnalytics
) {}
~~~

Các cờ `sendEmail`, `awardPoints`, `updateAnalytics` khiến publisher phải biết chính sách nội bộ của consumer, làm suy yếu chính mục đích fan-out. Tên `OrderPlaced` nói rằng đơn đã được đặt; mỗi consumer tự quyết định có phản ứng hay không.

## 6. Publisher chỉ cần tạo và công bố một event

Module orders phát event tại nơi xử lý nghiệp vụ:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.events.OrderPlaced;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderService(
            OrderRepository orders,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        OrderEntity order = OrderEntity.create(command);
        OrderEntity saved = orders.save(order);

        var event = new OrderPlaced(
                UUID.randomUUID(),
                saved.getId(),
                saved.getCustomerId(),
                saved.getTotalAmount(),
                saved.getCurrencyCode(),
                clock.instant()
        );

        publisher.publishEvent(event);
        return saved.getId();
    }
}
~~~

`OrderEntity`, `OrderRepository` và `PlaceOrderCommand` là các kiểu nghiệp vụ minh họa cần được triển khai trong dự án thật; `Clock` cũng cần được cấp bean. Ví dụ giả định repository trả về entity với ID và giá trị đã chốt.

Một lệnh `publishEvent(event)` là đủ để Spring giao event tới **mọi listener phù hợp đã được đăng ký**. Không cần:

~~~java
// Không nên: orders biết trực tiếp các consumer.
notificationService.sendConfirmation(orderId);
loyaltyService.awardPoints(orderId);
analyticsService.projectOrder(orderId);
~~~

Điều quan trọng là publisher **chỉ biết sự thật mà nó sở hữu**, không biết số lượng phản ứng đối với sự thật đó.

**Phân biệt:** tạo event Java, gọi `publishEvent`, transaction commit, listener xử lý và trạng thái publication hoàn tất là các bước khác nhau. `publishEvent` trả về **không bảo đảm** mọi handler bất đồng bộ đã thành công.

## 7. Đăng ký ba handler độc lập

### 7.1. Notifications: gửi xác nhận

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class SendOrderConfirmation {

    private final ConfirmationService confirmations;

    SendOrderConfirmation(ConfirmationService confirmations) {
        this.confirmations = confirmations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        confirmations.sendOnce(
                event.eventId(),
                event.orderId(),
                event.customerId()
        );
    }
}
~~~

`sendOnce` chỉ là tên phương thức **do ứng dụng phải tự cài đặt**. Annotation listener không cung cấp sẵn hàm chống trùng hoặc cơ chế gửi email đúng một lần.

### 7.2. Loyalty: cộng điểm thưởng

~~~java
package com.acme.shop.loyalty.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class AwardPointsForOrder {

    private final LoyaltyService loyalty;

    AwardPointsForOrder(LoyaltyService loyalty) {
        this.loyalty = loyalty;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        loyalty.awardOnce(
                event.eventId(),
                event.orderId(),
                event.totalAmount(),
                event.currencyCode()
        );
    }
}
~~~

Chính sách cộng điểm, điều kiện loại tiền tệ, giới hạn điểm và idempotency thuộc về **loyalty**, không nên được quyết định bằng một flag trong event.

### 7.3. Analytics: cập nhật projection

~~~java
package com.acme.shop.analytics.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ProjectOrderPlaced {

    private final OrderAnalytics analytics;

    ProjectOrderPlaced(OrderAnalytics analytics) {
        this.analytics = analytics;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        analytics.recordOnce(
                event.eventId(),
                event.orderId(),
                event.occurredAt(),
                event.totalAmount(),
                event.currencyCode()
        );
    }
}
~~~

`OrderAnalytics` là thành phần nội bộ cần tự triển khai. Event `OrderPlaced` ở đây biểu thị **giá trị đơn đã đặt**; không tự đồng nghĩa **doanh thu đã thu tiền**. Nếu chỉ số yêu cầu thanh toán hoàn tất, nên nghe một sự kiện có ngữ nghĩa như `PaymentCaptured` thay vì dùng nhầm `OrderPlaced`.

Đăng ký listener hoạt động khi các lớp được Spring tạo thành bean (`@Component` trong vùng component scan) và loại tham số handler khớp event được publish. Tạo một object listener bằng `new` bên ngoài `ApplicationContext` **không làm Spring tự đăng ký nó**.

## 8. Cơ chế Spring thực hiện fan-out

Trong Spring Framework, `ApplicationEventPublisher` giao sự kiện cho hệ thống event của `ApplicationContext`, nơi các listener được phát hiện và đăng ký. Với ba phương thức nhận `OrderPlaced`, Spring có ba nơi xử lý phù hợp.

Sơ đồ logic:

~~~mermaid
sequenceDiagram
    autonumber
    participant API as Client
    participant O as orders
    participant DB as Orders DB
    participant S as Spring Event Infrastructure
    participant N as notifications
    participant L as loyalty
    participant A as analytics

    API->>O: placeOrder(command)
    O->>DB: Lưu đơn (transaction)
    O->>S: publishEvent(OrderPlaced)
    O->>DB: Commit
    par Listener sau commit
        S-->>N: OrderPlaced
        N->>N: Gửi xác nhận
    and
        S-->>L: OrderPlaced
        L->>L: Cộng điểm
    and
        S-->>A: OrderPlaced
        A->>A: Ghi projection
    end
    O-->>API: orderId
~~~

Sơ đồ này mô tả ý nghĩa **fan-out sau commit**, không ấn định chính xác thời điểm các task bất đồng bộ khởi chạy so với HTTP response, cũng không cam kết ba task luôn chạy song song vật lý. Sự đồng thời phụ thuộc executor và tài nguyên hệ thống.

### Một event Java có bắt buộc phải kế thừa `ApplicationEvent`?

Không. Java record hoặc POJO có thể được công bố bằng `ApplicationEventPublisher`; Spring hỗ trợ xử lý object thông thường. Nếu cần lưu hoặc gửi event ngoài tiến trình, định dạng serialization là câu chuyện khác với việc tạo và dispatch object trong `ApplicationContext`.

### Listener nào nhận event?

Các listener có method signature/annotation phù hợp với loại event được công bố. Điều kiện `@EventListener(condition = "...")` có thể lọc một số event; khi đó không phải mọi listener đăng ký cùng kiểu đều xử lý tất cả instance. Dispatch cũng có thể xét quan hệ kiểu cha/con, nên không nhất thiết chỉ khớp tên class chính xác.

**Fan-out không phải một bản hợp đồng “đúng N consumer” cố định**. Khi hệ thống thêm hoặc xóa listener, số lượng phản ứng có thể thay đổi mà publisher không phải sửa.

## 9. Ba mô hình thời điểm xử lý và tác động tới fan-out

| Cơ chế | Thời điểm phổ biến | Điều cần chú ý khi có nhiều handler |
| --- | --- | --- |
| `@EventListener` | Đồng bộ ngay khi publish theo cấu hình mặc định. | Một handler ném lỗi có thể khiến publisher thất bại; handler khác có thể đã chạy hoặc chưa chạy. |
| `@TransactionalEventListener` | Gắn với transaction phase; mặc định `AFTER_COMMIT`. | Chỉ được kích hoạt khi transaction đạt phase tương ứng; mặc định không chạy nếu không có transaction. |
| `@ApplicationModuleListener` | Spring Modulith kết hợp xử lý sau commit, bất đồng bộ và transaction riêng. | Phù hợp cho fan-out giữa module có tác vụ hậu xử lý độc lập; cần giám sát và retry an toàn. |

Với `@EventListener` đồng bộ, fan-out có thể tạo kết quả *một handler đã gửi email, handler tiếp theo lỗi và transaction rollback*. Đây là nguyên nhân thường gặp gây side effect sai nếu gửi email trực tiếp trước khi đơn hàng commit.

Với `@ApplicationModuleListener`, các handler xử lý hậu nghiệp vụ sau khi orders commit; một handler thất bại **không thể rollback ngược đơn hàng đã commit**. Tuy nhiên khả năng độc lập về lỗi của từng tác vụ không thay thế chính sách phát lại/idempotency.

### Transaction của publisher có ý nghĩa gì?

`@TransactionalEventListener` mặc định yêu cầu một transaction đang hoạt động ở thời điểm event được publish. Nếu `OrderService` không thực sự chạy dưới transaction, listener transactional mặc định **không được kích hoạt** trừ khi cấu hình fallback phù hợp. Với proxy transaction của Spring, self-invocation hoặc cấu hình bean có thể khiến kỳ vọng về transaction không đúng. Hãy kiểm thử hành vi commit và rollback thực tế.

### Có cần ép handler chạy theo thứ tự?

Không nên dùng `@Order` làm cơ chế điều phối nghiệp vụ khi các handler bất đồng bộ. Thứ tự kích hoạt callback không bảo đảm thứ tự hoàn thành; một handler có thể chậm hơn, retry, hoặc lỗi. Nếu một tác vụ thật sự phụ thuộc kết quả của tác vụ khác, cần mô hình hóa **sự kiện mới, bước điều phối hoặc trạng thái workflow rõ ràng**.

## 10. Fan-out dẫn tới trạng thái hoàn tất riêng của từng consumer

Một `OrderPlaced(eventId=E-101)` được fan-out tới ba handler. Kết quả có thể là:

| Notifications | Loyalty | Analytics | Ý nghĩa |
| --- | --- | --- | --- |
| Thành công | Thành công | Thành công | Các tác vụ phụ đều hoàn tất. |
| Thất bại | Thành công | Thành công | Đơn đã commit; cần khôi phục gửi thông báo, không cộng điểm và ghi projection lại một cách vô điều kiện. |
| Thành công | Thất bại | Thành công | Cần khôi phục xử lý điểm; email không cần gửi lại nếu đã hoàn tất. |
| Thành công | Thành công | Thất bại | Projection có thể cập nhật trễ; không được đánh đồng với đơn chưa tạo. |
| Thất bại | Thất bại | Thất bại | Nhiều tác vụ hậu xử lý tồn đọng; cần giám sát và recovery theo từng consumer. |

**Không nên dùng một cờ `eventProcessed = true/false` chung để mô tả mọi consumer đã hoàn tất.** Một event có thể cần được phát tới nhiều listener, mỗi listener có vòng đời xử lý và lỗi khác nhau.

Điều này cũng cho thấy khác biệt giữa:

- **Tính nhất quán của nghiệp vụ orders:** đơn đã được tạo thành công.
- **Tính nhất quán cuối cùng của các module tiêu thụ:** email, điểm và báo cáo có thể cập nhật sau.

Một trải nghiệm người dùng phù hợp có thể hiển thị `ORDER_CREATED` cùng trạng thái `EMAIL_PENDING` hoặc `POINTS_PENDING` nếu các trạng thái phụ thực sự cần được lộ ra; không nên tuyên bố điểm đã cộng ngay khi `placeOrder` trả về.

## 11. Event Publication Registry theo dõi fan-out

Spring Modulith cung cấp **Event Publication Registry** để theo dõi việc giao event tới **transactional event listener**. Khi được cấu hình với backend persistence phù hợp, registry có thể ghi nhận các **publication gắn với listener** và đánh dấu hoàn tất khi consumer xử lý thành công.

Ở mức tư duy, một event fan-out có thể dẫn đến các mục theo dõi riêng:

~~~text
Event: OrderPlaced(E-101)
├── Publication cho notifications.OnOrderPlaced : COMPLETED
├── Publication cho loyalty.OnOrderPlaced       : INCOMPLETE
└── Publication cho analytics.OnOrderPlaced     : COMPLETED
~~~

Đây là **mô hình logic minh họa**, không phải tên bảng hay định dạng lưu bắt buộc của mọi storage integration. Việc registry hiện diện, cách lưu, định danh listener và thời điểm đánh dấu hoàn tất phụ thuộc cấu hình và phiên bản thực tế.

### Lợi ích của trạng thái theo listener

Giả sử gửi email và projection thành công nhưng loyalty lỗi. Cơ chế theo dõi publication riêng giúp ứng dụng biết **consumer nào cần xử lý tiếp**, thay vì publish lại một cách mù quáng khiến mọi tác dụng phụ có nguy cơ bị lặp.

Tuy nhiên, không suy ra rằng **mọi** ứng dụng có `@ApplicationModuleListener` đã tự có persistent recovery. Muốn có tính bền vững khi ứng dụng dừng, cần cấu hình Event Publication Registry và persistence phù hợp, xác định cách phục hồi publication chưa hoàn tất và kiểm thử đường khôi phục đó.

### Khôi phục khác với tự động retry ngay

Một publication chưa hoàn tất có thể được kiểm tra hoặc xử lý lại theo cơ chế recovery/republication do ứng dụng cấu hình. Không được mặc định rằng hệ thống sẽ tự thử lại vô hạn với backoff, lịch chạy và giới hạn số lần retry như mong muốn chỉ vì một listener ném exception.

Khi triển khai cần làm rõ: ai kích hoạt retry, khi nào retry, có backoff/jitter không, số lần tối đa, lỗi vĩnh viễn được báo ở đâu và cách khôi phục sau deploy.

## 12. Vì sao mỗi handler phải idempotent?

**Fan-out không tự bảo đảm đúng một lần xử lý tác dụng phụ.** Nếu handler đã thực hiện side effect thành công nhưng tiến trình dừng trước khi publication được ghi nhận hoàn tất, cùng event có thể được giao lại.

Ví dụ:

~~~text
OrderPlaced(eventId=E-101) đã commit
  notifications: đã gửi email, chưa kịp xác nhận completion
  loyalty:       đã cộng điểm và hoàn tất
  analytics:     đã cập nhật projection và hoàn tất

Ứng dụng khởi động lại:
  publication notifications còn dang dở -> có thể được replay
  nếu thiếu idempotency -> email trùng
~~~

Mỗi consumer có thể dùng một **khóa riêng**:

- Notifications: `(eventId, "send-confirmation")`.
- Loyalty: `(eventId, "award-loyalty-points")`.
- Analytics: `(eventId, "record-order-projection")`.

Không nên dùng một bản ghi `consumed(eventId)` chung cho cả ba consumer rồi chặn những consumer còn lại; cùng một event **phải được phép xử lý một lần cho từng tác vụ độc lập**.

Ví dụ bảng chống trùng:

~~~sql
CREATE TABLE consumer_processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Với consumer cập nhật dữ liệu trong cùng một database, có thể dùng unique constraint và transaction phù hợp để bảo đảm thao tác ghi dấu và thay đổi nghiệp vụ là nguyên tử. Tránh mẫu kiểm tra `exists` rồi insert không khóa vì hai worker đồng thời có thể cùng qua bước kiểm tra.

Với **email hoặc API bên ngoài**, transaction database không tự tạo atomicity với hệ thống ngoài. Nếu đánh dấu hoàn tất **trước khi gửi email**, lỗi gửi có thể khiến lần retry bị bỏ qua và email mất. Nếu đánh dấu **sau khi gửi**, tiến trình dừng ở giữa có thể tạo email trùng. Phải chọn chiến lược phù hợp: tận dụng idempotency key nếu downstream hỗ trợ, cơ chế outbox/dispatch riêng, đối soát trạng thái hoặc chấp nhận xử lý trùng có kiểm soát.

**Registry hỗ trợ biết publication nào chưa hoàn tất; idempotency bảo vệ side effect khỏi bị nhân đôi. Hai năng lực bổ sung cho nhau.**

## 13. Fan-out có thể gây tăng tải và backlog

Một event được ba listener xử lý có thể tạo ba tác vụ. Khi có thêm consumer hoặc lượng event tăng cao, fan-out làm tăng tổng công việc.

Giả sử trung bình một phút có \(N\) sự kiện và mỗi sự kiện được \(K\) listener tiêu thụ. Số lần kích hoạt handler lý thuyết gần bằng:

\[
H = N \times K
\]

Ví dụ 1.000 đơn/phút với 4 handler tạo ra khoảng 4.000 lượt handler/phút **trước khi tính retry**. Đây không phải khẳng định hệ thống thực thi đồng thời 4.000 luồng; số luồng và lịch xử lý phụ thuộc executor, tài nguyên và cấu hình.

Những điểm cần quản lý:

| Rủi ro | Hậu quả | Biện pháp |
| --- | --- | --- |
| Executor thiếu tài nguyên | Handler bị chậm, quá tải hoặc bị từ chối thực thi. | Cấu hình executor phù hợp, quan sát queue/active tasks/rejections. |
| Nhiều handler cùng truy cập một downstream | Gây quá tải email API, DB hoặc hệ thống báo cáo. | Rate limit, timeout, backoff và phân bổ tài nguyên. |
| Handler lâu hoặc treo | Publication tồn đọng, giảm tốc độ cập nhật. | Timeout, giám sát độ trễ và chính sách xử lý lỗi. |
| Retry quá nhanh | Tăng tải vào hệ thống vốn đang gặp sự cố. | Retry có giới hạn, backoff/jitter và cảnh báo. |
| Payload event quá lớn | Tăng chi phí bộ nhớ/lưu publication. | Snapshot tối thiểu phục vụ hợp đồng, tránh dữ liệu lớn không cần thiết. |
| Thêm consumer không kiểm soát | Tăng độ phức tạp vận hành và bề mặt dữ liệu. | Review hợp đồng, module dependency và ownership của listener. |

**Spring application events không phải bộ đệm hàng đợi bền vững mặc định**. Nếu fan-out cần cân bằng tải phân tán trên nhiều tiến trình và có yêu cầu throughput/retention lớn, cân nhắc tích hợp message broker hoặc kiến trúc phù hợp. Đừng ngầm coi in-process fan-out là hệ thống distributed pub/sub.

## 14. Thứ tự, concurrency và tính đúng đắn

Hai event liên tiếp của cùng một đơn:

~~~text
OrderPlaced(orderId=O-100, eventId=E-1)
OrderCancelled(orderId=O-100, eventId=E-2)
~~~

Không nên giả định một consumer bất đồng bộ luôn hoàn tất `OrderPlaced` trước `OrderCancelled` chỉ vì publisher phát theo thứ tự đó. Thời gian xử lý, lỗi, retry và executor có thể khiến kết quả đến muộn hoặc đảo thứ tự.

Một số chiến lược:

1. **Phân biệt ngữ nghĩa rõ:** `OrderPlaced`, `OrderCancelled` là sự thật khác nhau, không gom thành event `OrderChanged` mơ hồ.
2. **Version theo aggregate nếu cần:** thêm `orderVersion` do orders quản lý để consumer phát hiện update cũ, nhưng version **không tự bảo đảm** hệ thống giao theo thứ tự.
3. **Projection idempotent:** consumer so sánh phiên bản/trạng thái trước khi áp dụng thay đổi; tránh update ngược bởi event đến muộn.
4. **Workflow có điều kiện:** nếu một bước chỉ được chạy sau bước khác hoàn tất, dùng trạng thái điều phối hoặc một event mới thể hiện bước tiền đề đã xảy ra.
5. **Không dựa vào `@Order` để ép thứ tự hoàn thành của các listener bất đồng bộ.**

### Fan-out song song hay tuần tự?

`@ApplicationModuleListener` được thiết kế cho xử lý bất đồng bộ sau commit; việc nhiều handler chạy chồng lấp hay tuần tự phụ thuộc executor và cấu hình thực tế. **Fan-out chỉ nói về số consumer được giao event, không định nghĩa scheduling policy.**

Nếu một dự án muốn giới hạn sự đồng thời giữa các handler, cần thiết kế executor, transaction, lock hoặc consumer workflow riêng; không suy luận rằng mọi listener của Spring Modulith đều chạy trên thread riêng biệt cho mỗi event.

## 15. Khi fan-out không đủ: điều phối và phụ thuộc nghiệp vụ

Giả sử yêu cầu là:

1. Đơn được tạo.
2. Hệ thống phải thu thanh toán thành công.
3. **Chỉ sau khi thanh toán thành công** mới phát lệnh giao hàng.

Nếu cho `PaymentHandler` và `ShippingHandler` cùng nghe `OrderPlaced`, shipping có thể chạy trước khi payment hoàn tất. Đây là **sai mô hình nghiệp vụ** chứ không phải lỗi của Spring.

~~~mermaid
flowchart LR
    A["OrderPlaced"] --> P["payments<br/>Xử lý thanh toán"]
    P --> PC(("PaymentCaptured"))
    PC --> S["shipping<br/>Chuẩn bị giao hàng"]
    PC --> N["notifications<br/>Thông báo đã thanh toán"]
~~~

`PaymentCaptured` được phát bởi module sở hữu sự thật **đã thu tiền**. Fan-out vẫn có thể sử dụng ở bước sau: shipping và notifications cùng phản ứng khi thanh toán thành công. Nếu thanh toán thất bại, quy trình cần trạng thái hoặc sự kiện khác phù hợp.

Phân biệt:

- **Fan-out**: các phản ứng độc lập trước **cùng một sự thật**.
- **Event chaining**: một handler xử lý xong nghiệp vụ, phát thêm **sự thật mới**.
- **Orchestration/workflow**: một thành phần điều phối theo dõi trạng thái, thứ tự, lỗi, timeout và bù trừ.
- **Distributed saga**: phối hợp quy trình phân tán qua nhiều bước với chính sách bù trừ; không tự được cung cấp chỉ bằng việc thêm listener.

Không dùng fan-out thay thế một workflow có điều kiện hoàn thành, cũng không lạm dụng event chaining để tạo vòng lặp sự kiện khó kiểm soát.

## 16. Test fan-out: publish một lần, kiểm tra từng handler

Kiểm thử tốt cần tách rõ các lớp xác minh.

### 16.1. Publisher có phát đúng một sự kiện không?

Spring Modulith cung cấp `@ApplicationModuleTest` và `PublishedEvents` để quan sát những event đã công bố.

~~~java
package com.acme.shop.orders;

import com.acme.shop.orders.events.OrderPlaced;
import com.acme.shop.orders.internal.OrderService;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderEventsTest {

    @Autowired
    OrderService orders;

    @Test
    void publishesExactlyOneOrderPlaced(PublishedEvents published) {
        // Fixture do dự án định nghĩa để tạo yêu cầu hợp lệ.
        var request = TestOrders.validPlaceOrder();
        UUID orderId = orders.placeOrder(request);

        assertThat(published.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .hasSize(1);
    }
}
~~~

`TestOrders` là fixture minh họa cần được triển khai trong mã test. Kiểm thử này chỉ chứng minh **publisher đã công bố một `OrderPlaced` phù hợp**. Nó **không chứng minh** ba listener đã chạy hoặc đã hoàn tất.

### 16.2. Mỗi consumer xử lý đúng dữ liệu

Ở module notifications, tạo test xác nhận `SendOrderConfirmation` gọi gateway đúng `orderId`. Tương tự, loyalty phải áp dụng đúng chính sách điểm; analytics phải ghi projection đúng thời điểm và số tiền. Có thể unit test logic nội bộ bằng mock/fixture, nhưng phải có integration test nếu muốn xác nhận annotation listener thật sự được đăng ký trong Spring context.

Mỗi consumer nên được kiểm thử với **cùng loại event hợp đồng**, không cần biết implementation của consumer khác.

### 16.3. Integration test fan-out sau commit

Một kịch bản đầy đủ:

1. Khởi chạy context có cả publisher và ba listener.
2. Gọi `placeOrder` thực sự tạo transaction và commit.
3. Chờ kết quả của **từng consumer** với điều kiện quan sát được, không dùng một `Thread.sleep` cố định.
4. Xác nhận cả ba phản ứng phù hợp với một `eventId`.
5. Tạo transaction rollback sau publish và xác nhận không có tác dụng phụ từ các listener sau commit.

Lưu ý test gắn `@Transactional` đôi khi bị framework tự rollback cuối test, khiến listener after-commit chưa có điều kiện chạy. Hãy điều khiển commit tường minh hoặc tổ chức test cho phép service nghiệp vụ tự quản lý transaction.

### 16.4. Fault injection một nhánh

Cho listener loyalty ném exception trong khi notifications và analytics hoạt động bình thường. Kiểm tra:

- Đơn hàng đã commit vẫn tồn tại.
- Hai consumer còn lại hoàn tất.
- Nếu registry/persistence đang bật, publication dành cho loyalty chưa hoàn tất được ghi nhận theo cơ chế thực tế.
- Kích hoạt recovery cho nhánh lỗi và xác nhận sau đó hoàn tất.
- Không nhân đôi email hoặc projection khi phát lại cùng event.

Đây là test quan trọng nhất để chứng minh fan-out đang xử lý **partial failure**, không chỉ minh họa happy path.

### 16.5. Kiểm tra ranh giới module

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm tra này giúp phát hiện module tiêu thụ phụ thuộc sai vào implementation của module phát hành. Nó không thay thế test transaction, recovery hoặc sự thành công của các side effect.

## 17. Observability phải chi tiết tới từng handler

Nếu chỉ ghi log:

~~~text
OrderPlaced published: E-101
~~~

thì không thể biết notifications, loyalty hoặc analytics đã hoàn thành chưa. Fan-out cần **truy vết theo cặp `(eventId, consumer)`**.

Một nhóm trường quan sát hữu ích:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `eventType`, `eventId` | Xác định sự kiện chung được fan-out. |
| `orderId` | Liên kết với đối tượng nghiệp vụ. |
| `publisherModule` | Tìm module chủ sở hữu sự thật. |
| `consumerModule`, `listenerName` | Xác định nhánh đang chạy hoặc bị lỗi. |
| `occurredAt`, `startedAt`, `completedAt` | Đo độ trễ từ sự kiện tới từng phản ứng. |
| `attempt`, `errorType` | Tìm các nhánh retry liên tục. |
| `publicationStatus` | Phân biệt completed/incomplete khi dùng registry. |
| Executor queue/rejections | Xác định hiện tượng nghẽn ở tầng bất đồng bộ. |

Ví dụ log do **ứng dụng tự thiết kế**:

~~~text
event=OrderPlaced eventId=E-101 listener=notifications status=COMPLETED attempt=1
event=OrderPlaced eventId=E-101 listener=loyalty       status=FAILED    attempt=1 reason=DB_TIMEOUT
event=OrderPlaced eventId=E-101 listener=analytics     status=COMPLETED attempt=1
event=OrderPlaced eventId=E-101 listener=loyalty       status=COMPLETED attempt=2
~~~

Đây không phải mẫu log mặc định Spring Modulith tự xuất. Cần cấu hình logging, metrics, tracing và giám sát publication theo từng consumer; tránh log toàn bộ payload có dữ liệu nhạy cảm.

Một dashboard vận hành tốt phân biệt **bao nhiêu event được phát**, **bao nhiêu publication đến từng listener**, **bao nhiêu hoàn tất**, **bao nhiêu đang retry** và **publication nào tồn đọng lâu**.

## 18. Sai lầm thường gặp khi thiết kế fan-out

### 18.1. Publisher gọi tất cả service rồi vẫn publish event

~~~java
notificationService.send(orderId);
loyaltyService.award(orderId);
publisher.publishEvent(new OrderPlaced(...));
~~~

Nếu đã có listener xử lý cùng các tác vụ, đoạn này có thể tạo side effect trùng và vẫn làm orders phụ thuộc trực tiếp vào consumer. Chỉ gọi trực tiếp khi có lý do nghiệp vụ cần đồng bộ rõ ràng, không kết hợp bừa với fan-out.

### 18.2. Một “GodListener” làm mọi thứ

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    sendEmail(event);
    awardPoints(event);
    updateAnalytics(event);
}
~~~

Mọi lỗi và phụ thuộc bị gom vào một handler, làm mờ ownership giữa module. Nên tách handler tại module chịu trách nhiệm tác dụng phụ; nếu thật sự có chuỗi bước bắt buộc, tạo workflow có trạng thái.

### 18.3. Tin rằng ba listener đều thành công vì publish thành công

Với listener bất đồng bộ, publisher có thể đã trả lời khi các handler vẫn chạy hoặc lỗi. Phải quan sát kết quả ở consumer và publication registry nếu dùng.

### 18.4. Dùng một khóa dedup chung cho mọi consumer

Nếu notifications ghi `processed(eventId)` vào bảng chung, rồi loyalty thấy event đã xử lý và bỏ qua, fan-out không còn đúng nghĩa. Khóa phải phân biệt **consumer và sự kiện**, hoặc từng consumer có kho dấu vết xử lý riêng.

### 18.5. Dựa vào thứ tự đăng ký để tạo quan hệ phụ thuộc

Không nên dùng `@Order` để yêu cầu loyalty đợi notifications hoàn tất khi các handler chạy async. Mô hình nghiệp vụ phải thể hiện sự phụ thuộc bằng trạng thái hoặc event mới.

### 18.6. Không bảo vệ tác dụng phụ khỏi retry

Một publication có thể được replay khi listener đã gửi email nhưng chưa được ghi nhận hoàn tất. Cần idempotency và chính sách phục hồi, không suy ra exactly-once chỉ từ annotation.

### 18.7. Truyền entity sống giữa các handler

Nếu `OrderPlaced` mang `OrderEntity` mutable, các handler bất đồng bộ có thể gặp lazy loading, dữ liệu thay đổi hoặc phụ thuộc sai package. Dùng record/snapshot bất biến hoặc ID cùng API truy vấn công khai khi phù hợp.

### 18.8. Nhầm application event với broker fan-out

Spring in-process event không mặc nhiên có consumer groups, durable topics, partition ordering hoặc replay từ broker. Những đặc tính đó cần tích hợp và cấu hình riêng.

## 19. Quy trình thiết kế fan-out an toàn

~~~mermaid
flowchart TD
    A["Có một sự thật nghiệp vụ"] --> B["Định nghĩa event contract tại module sở hữu"]
    B --> C["Liệt kê consumer và tác vụ độc lập"]
    C --> D{"Các tác vụ có cần thứ tự bắt buộc?"}
    D -->|"Có"| E["Thiết kế workflow / event tiếp theo"]
    D -->|"Không"| F["Đăng ký listener ở từng module"]
    F --> G{"Tác vụ chỉ hợp lệ sau commit?"}
    G -->|"Có"| H["@ApplicationModuleListener hoặc transactional listener"]
    G -->|"Không"| I["Cân nhắc @EventListener và tác động transaction"]
    H --> J["Thiết kế idempotency riêng từng consumer"]
    I --> J
    J --> K{"Cần khôi phục publication sau lỗi?"}
    K -->|"Có"| L["Cấu hình registry, persistence, recovery"]
    K -->|"Không"| M["Xác định giới hạn mất tác vụ có thể chấp nhận"]
    L --> N["Test rollback, partial failure, retry và metrics"]
    M --> N
    E --> N
~~~

Đây là cách ra quyết định, không phải quy tắc cứ có event là phải có nhiều listener. Nếu chỉ một consumer cần phản ứng thì vẫn có thể dùng event để giảm phụ thuộc; nếu nhiệm vụ cần kết quả đồng bộ tức thì, event fan-out bất đồng bộ có thể không phù hợp.

## 20. Checklist triển khai

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Event có mô tả đúng sự thật nghiệp vụ? | `OrderPlaced` chỉ phát khi orders xác nhận thao tác tạo đơn. |
| Ai sở hữu event? | Publisher module công khai contract qua API/named interface. |
| Ai sở hữu từng handler? | Module tương ứng sở hữu xử lý và dữ liệu của mình. |
| Mỗi handler có là Spring bean? | Bean được scan/`@Bean`, method annotation và kiểu tham số phù hợp. |
| Các tác vụ có thật sự độc lập? | Không dựa vào thứ tự hoàn thành giữa listener bất đồng bộ. |
| Transaction hợp lệ? | Listener sau commit chỉ chạy khi publisher commit, không chạy khi rollback. |
| Event payload có bất biến và tối thiểu? | Không truyền JPA entity/secret hoặc dữ liệu không cần thiết. |
| Có thể có partial failure? | Theo dõi trạng thái từng consumer và khôi phục riêng. |
| Có cần persistent delivery? | Registry/storage/recovery đã được cấu hình và test phù hợp. |
| Idempotency đúng phạm vi? | Khóa theo consumer + event hoặc theo tác vụ nghiệp vụ. |
| Có kiểm soát tải? | Timeout, executor, backoff và observability. |
| Test đầy đủ? | Publisher, từng consumer, commit/rollback, fault injection, replay, module boundaries. |

## 21. Bài thực hành: một event, ba nhánh xử lý

Xây dựng một ứng dụng Spring Modulith mô phỏng bán hàng, gồm `orders`, `notifications`, `loyalty`, `analytics`.

**Yêu cầu nghiệp vụ:** khi tạo đơn trị giá `550000 VND`, orders công bố một `OrderPlaced`. Notifications gửi một xác nhận, loyalty cộng điểm theo quy tắc riêng và analytics ghi giá trị đơn đã đặt.

Thực hiện theo các bước:

1. Tạo record `OrderPlaced(eventId, orderId, customerId, totalAmount, currencyCode, occurredAt)` bất biến tại module `orders`.
2. Dùng `@NamedInterface("events")` công khai contract; giới hạn các consumer phụ thuộc vào `orders::events`.
3. Từ `OrderService.placeOrder`, lưu đơn trong transaction rồi gọi `publishEvent` **một lần**.
4. Viết ba `@ApplicationModuleListener` ở ba module khác nhau, mỗi handler chỉ phụ trách tác vụ của module mình.
5. Kiểm thử publisher tạo đúng một event; test riêng nội dung và dữ liệu mỗi consumer.
6. Xác nhận ba handler sau commit không xử lý nếu transaction tạo đơn rollback.
7. Giả lập loyalty bị lỗi trong khi notifications và analytics thành công; quan sát trạng thái riêng của mỗi consumer.
8. Với Event Publication Registry có persistence/recovery phù hợp, khôi phục publication loyalty chưa hoàn tất.
9. Phát lại cùng `eventId`; xác nhận mỗi consumer vẫn chỉ tạo một tác dụng phụ nghiệp vụ.
10. Theo dõi `eventId`, `listenerName`, thời gian xử lý, số lượt thử và publication còn tồn.

**Bài tập mở rộng:** thay đổi yêu cầu để **chỉ cộng điểm sau khi thanh toán thành công**. Không cho loyalty và payment cùng nghe `OrderPlaced` rồi dùng `@Order`; hãy định nghĩa sự thật `PaymentCaptured` do payments công bố và để loyalty nghe event này. Giải thích vì sao đây là sự thay đổi mô hình nghiệp vụ, không chỉ thay đổi cấu hình thread.

**Tự kiểm tra:** Fan-out khác queue có competing consumers như thế nào? Tại sao một event cần trạng thái xử lý riêng theo listener? Vì sao `@ApplicationModuleListener` không đồng nghĩa exactly-once? Một consumer lỗi có bắt buộc kéo các consumer khác rollback không? Nếu thêm subscriber mới sau khi event đã phát, có tự nhận lịch sử event cũ không?

**Ghi nhớ:** Fan-out event trong Spring Modulith cho phép **một sự thật nghiệp vụ được nhiều module phản ứng độc lập**. Publisher chỉ biết hợp đồng event; mỗi consumer sở hữu handler, transaction và tác dụng phụ của mình. Khi áp dụng xử lý sau commit, hãy quản lý partial failure, Event Publication Registry khi cần lưu publication, retry có kiểm soát, idempotency riêng từng consumer, kiểm thử tình huống lỗi và observability theo từng nhánh. Fan-out giúp giảm phụ thuộc, nhưng không thay thế việc điều phối workflow khi nghiệp vụ cần thứ tự hoặc kết quả bắt buộc.

