# Giao tiếp qua event trong kiến trúc Spring Modulith

## 1. Vì sao các module cần giao tiếp qua event?

Một ứng dụng theo kiến trúc module thường có nhiều năng lực nghiệp vụ liên quan nhưng khác trách nhiệm. Ví dụ, trong hệ thống bán hàng:

- Module **Orders** quản lý đơn hàng và quyết định khi nào một đơn được xác nhận.
- Module **Fulfillment** lập yêu cầu đóng gói, giao hàng.
- Module **Notifications** gửi thông báo cho khách hàng.
- Module **Reporting** cập nhật dữ liệu phục vụ báo cáo.

Sau khi Orders xác nhận đơn hàng, ba module còn lại có thể cần thực hiện các công việc tiếp theo. Cách dễ nghĩ đến là Orders gọi trực tiếp lần lượt `FulfillmentService`, `NotificationService` và `ReportService`. Khi đó Orders dần phải biết mỗi module nhận có API gì, gọi theo thứ tự nào và lỗi ở một module ảnh hưởng đến toàn bộ thao tác ra sao.

**Giao tiếp qua event** thay đổi điểm kết nối: Orders chỉ công bố một sự thật nghiệp vụ đã xảy ra, chẳng hạn `OrderConfirmed`. Các module quan tâm tự đăng ký listener và tự xử lý công việc thuộc quyền sở hữu của mình.

Trong **SPRING_MODULITH_APPLICATION_EVENTS**, cơ chế này được triển khai bằng Spring application events kết hợp các tiện ích của Spring Modulith. Mục tiêu là giảm phụ thuộc trực tiếp, bảo vệ ranh giới module và hỗ trợ giao sự kiện có thể theo dõi, xử lý lại khi cần.

~~~mermaid
flowchart TB
    subgraph Direct["Liên kết bằng lời gọi trực tiếp"]
      O1["Orders"] --> F1["Fulfillment"]
      O1 --> N1["Notifications"]
      O1 --> R1["Reporting"]
    end
    subgraph Events["Liên kết bằng event"]
      O2["Orders"] -->|"publish OrderConfirmed"| Bus(("Application event"))
      Bus -->|"subscribe"| F2["Fulfillment"]
      Bus -->|"subscribe"| N2["Notifications"]
      Bus -->|"subscribe"| R2["Reporting"]
    end
~~~

Sơ đồ event bus ở đây là mô hình logic của cơ chế publish/subscribe trong ứng dụng. `ApplicationEventPublisher` mặc định hoạt động **bên trong cùng tiến trình Spring**; nó không tự tạo một hàng đợi bền vững hoặc message broker bên ngoài.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chọn giao tiếp trực tiếp hoặc event dựa trên nhu cầu nghiệp vụ và transaction.
2. Đặt event contract đúng phần API công khai của module Spring Modulith.
3. Tạo publisher và listener, phân biệt listener đồng bộ với listener sau commit.
4. Thiết kế tính idempotent, theo dõi publication và cách xử lý event bị lỗi.
5. Kiểm thử ranh giới module và luồng sự kiện giữa nhiều module.

## 2. So sánh lời gọi trực tiếp và giao tiếp qua event

Sự khác biệt cốt lõi là quan hệ phụ thuộc. Khi gọi trực tiếp, module gửi yêu cầu biết rõ module nào phải trả lời. Với event, module phát chỉ biết **điều đã xảy ra**; quyết định hành động nằm ở module nhận.

| Tiêu chí | Gọi qua public API trực tiếp | Publish/subscribe qua event |
| --- | --- | --- |
| Mục đích | Yêu cầu một thao tác hoặc lấy kết quả ngay | Thông báo sự thật nghiệp vụ cho các bên quan tâm |
| Phụ thuộc giữa module | Caller biết interface/service được gọi | Publisher chỉ biết event contract; subscriber phụ thuộc contract công khai |
| Phản hồi | Có return value/exception theo lời gọi | Thường không có kết quả đồng bộ từ consumer |
| Transaction | Có thể cùng transaction nếu gọi đồng bộ trong cùng ứng dụng | Phụ thuộc loại listener; listener sau commit có transaction riêng |
| Số bên nhận | Caller tự điều phối từng lời gọi | Nhiều listener độc lập đăng ký cùng một event |
| Xử lý lỗi | Có thể truyền lỗi trực tiếp về caller | Cần chiến lược retry, theo dõi và bảo vệ idempotency |
| Độ trễ cập nhật | Thường thấy kết quả ngay khi gọi xong | Có thể chậm hoặc hoàn thành vào các thời điểm khác nhau |
| Tình huống phù hợp | Kiểm tra điều kiện bắt buộc, lấy giá trị phục vụ quyết định hiện tại | Gửi thông báo, khởi tạo quy trình sau commit, cập nhật read model |

**Event không phải lựa chọn mặc định cho mọi giao tiếp.** Khi Orders phải biết kết quả kiểm tra hạn mức tín dụng **trước khi chấp nhận đơn hàng**, một lời gọi đồng bộ qua public API của module Credit có thể rõ ràng và phù hợp hơn. Khi đơn đã được xác nhận và cần gửi thông báo, event là một lựa chọn tốt vì công việc thông báo có thể diễn ra độc lập.

Có thể tự hỏi:

- *Tôi cần câu trả lời ngay để quyết định thao tác đang thực hiện?* Ưu tiên API đồng bộ.
- *Tôi chỉ muốn cho các phần khác biết một sự thật vừa xảy ra?* Cân nhắc event.
- *Nếu listener lỗi, giao dịch chính có phải bị hủy?* Nếu có, không được tự động chuyển toàn bộ trách nhiệm đó sang listener `AFTER_COMMIT`.
- *Công việc có thể xử lý trễ và thử lại?* Event sau commit thường phù hợp.

## 3. Các vai trò trong một luồng event

Một luồng giao tiếp sự kiện giữa module có bốn thành phần:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Publisher** | Thực hiện nghiệp vụ trong module mình; công bố sự kiện khi một kết quả được xác nhận | `OrderApplicationService` |
| **Event contract** | Mô tả sự thật nghiệp vụ dưới dạng dữ liệu ổn định mà module khác được phép biết | `OrderConfirmed` |
| **Spring event infrastructure** | Chuyển sự kiện đến listener đã đăng ký theo cách xử lý được cấu hình | `ApplicationEventPublisher` |
| **Subscriber/listener** | Diễn giải sự kiện và thay đổi state hoặc gây side effect trong module của mình | `OrderConfirmedListener` |

Publisher không cần biết có bao nhiêu listener. Điều này giúp thêm module Reporting sau này mà không sửa luồng xác nhận đơn trong Orders, miễn contract vẫn đáp ứng nhu cầu.

Tuy vậy, module nhận **vẫn phụ thuộc vào contract sự kiện**. Vì vậy, event không xóa hết sự phụ thuộc; nó chuyển sự phụ thuộc sang một hợp đồng hẹp, công khai và có ý nghĩa nghiệp vụ.

## 4. Bảo vệ ranh giới module khi công bố event

Trong cấu trúc mặc định của Spring Modulith, các package trực tiếp dưới package gốc ứng dụng thường tương ứng với các application module. Các type ở package gốc của một module thuộc API được phơi bày theo quy ước; các package con nội bộ mặc định không được truy cập tùy tiện từ module khác.

Ví dụ cấu trúc đơn giản:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderConfirmed.java          <-- public event contract
│   └── internal
│       ├── OrderApplicationService.java
│       ├── Order.java
│       └── OrderRepository.java
├── fulfillment
│   └── internal
│       ├── OrderConfirmedListener.java
│       └── FulfillmentRequestRepository.java
└── notifications
    └── internal
        └── OrderNotificationListener.java
~~~

Với cách tổ chức này:

- Fulfillment có thể import `com.acme.shop.orders.OrderConfirmed` từ API công khai của Orders.
- Fulfillment **không** nên import `com.acme.shop.orders.internal.OrderRepository` hoặc sửa entity của Orders.
- Orders không cần import listener, entity hay repository của Fulfillment và Notifications.
- Các chi tiết lưu trữ và quy tắc xử lý vẫn nằm ở module sở hữu.

Một lựa chọn khác là đặt event contract trong package con như `orders.events`. Khi đó, nếu muốn module khác sử dụng package con, cần công bố nó thành **named interface** bằng `@NamedInterface` theo cấu hình Spring Modulith. Chỉ tạo một package con không tự làm toàn bộ type bên trong trở thành API công khai.

Ví dụ file `com/acme/shop/orders/events/package-info.java` khi dùng named interface:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Điều này cho phép xây dựng API rõ ràng mà không phải phơi bày entity nội bộ. Chỉ cần chọn **một** cấu trúc hợp lý cho project: ví dụ xuyên suốt dưới đây đặt `OrderConfirmed` ngay trong module root để dễ theo dõi.

### Event contract khác entity như thế nào?

Không nên dùng chính entity JPA `Order` làm payload của event:

~~~java
// Không khuyến nghị: rò rỉ mô hình persistence sang module khác.
events.publishEvent(order);
~~~

Entity có thể chứa quan hệ lazy loading, các setter và trạng thái đang thay đổi trong transaction. Khi consumer phụ thuộc entity, một thay đổi nội bộ ở Orders có thể phá vỡ nhiều module còn lại.

Thay vào đó, contract chỉ nên có thông tin cần thiết về sự kiện:

~~~java
package com.acme.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

`record` là lựa chọn phù hợp cho event payload mang dữ liệu bất biến. Nếu consumer cần số tiền hoặc mã khách hàng **tại thời điểm xác nhận**, có thể bổ sung những dữ liệu thực sự cần thiết và được phép công bố, thay vì bắt consumer truy cập entity nội bộ. Tránh đưa bí mật, dữ liệu cá nhân không cần thiết hoặc object có thể bị thay đổi vào payload.

## 5. Ví dụ: publisher phát event khi hoàn thành nghiệp vụ

Giả sử có một application service trong module Orders. Nó xác nhận đơn hàng, lưu trạng thái và thông báo sự kiện:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        if (order.isConfirmed()) {
            return; // Tránh phát lại event cho thao tác lặp không đổi state.
        }

        order.confirm(); // Bảo vệ quy tắc chuyển trạng thái trong domain.
        orders.save(order);

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                order.getId(),
                Instant.now(clock)
        ));
    }
}
~~~

Ví dụ giả định đã có `Order`, `OrderRepository` và bean `Clock`. Phần tạo entity, quản lý transaction và kiểm tra điều kiện thuộc Orders, không nằm trong event bus.

Ba ý quan trọng:

1. **Sự kiện được phát vì có sự thật nghiệp vụ:** `OrderConfirmed` chỉ có ý nghĩa nếu thao tác xác nhận hợp lệ.
2. **Publisher không chọn consumer:** không hề có phụ thuộc mã nguồn từ Orders sang Fulfillment hay Notifications.
3. **`publishEvent(...)` không đồng nghĩa commit thành công:** lệnh này được gọi trong transaction. Listener đồng bộ có thể được chạy ngay, còn listener sau commit chỉ được kích hoạt khi transaction đã commit.

Ví dụ kiểm tra `order.isConfirmed()` mới giải quyết callback lặp trong luồng đơn giản. Trong môi trường có nhiều request đồng thời, Orders vẫn phải áp dụng optimistic/pessimistic locking hoặc unique constraint phù hợp để tránh hai request cùng phát hiện trạng thái chưa xác nhận rồi cùng phát sự kiện.

## 6. Listener: mỗi module tự quyết định phản ứng

Fulfillment nhận event và tạo yêu cầu xử lý giao hàng:

~~~java
package com.acme.shop.fulfillment.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmedListener {

    private final FulfillmentService fulfillment;

    OrderConfirmedListener(FulfillmentService fulfillment) {
        this.fulfillment = fulfillment;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        fulfillment.openRequestIfAbsent(
                event.orderId(),
                event.eventId()
        );
    }
}
~~~

Notifications cũng có thể lắng nghe cùng contract:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    private final NotificationService notifications;

    OrderNotificationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        notifications.scheduleOrderConfirmationIfAbsent(
                event.orderId(),
                event.eventId()
        );
    }
}
~~~

Hai service `openRequestIfAbsent` và `scheduleOrderConfirmationIfAbsent` là API nội bộ minh họa, cần được triển khai với transaction và ràng buộc dữ liệu của từng module.

**Fulfillment không phụ thuộc Notifications**: một bên mở yêu cầu giao hàng, bên còn lại lên lịch thông báo. Khi thêm một subscriber mới, Orders không cần biết. Mỗi subscriber có quy tắc nghiệp vụ và cách xử lý lỗi riêng.

### Vì sao cần idempotency?

Một event có thể được giao lại trong quá trình khôi phục hoặc retry. Nếu Fulfillment tạo record mới mỗi lần nghe cùng `OrderConfirmed`, một đơn có thể sinh nhiều yêu cầu giao hàng.

Giải pháp thường là thiết kế thao tác **idempotent**:

- Lưu `eventId` đã xử lý trong bảng riêng hoặc dùng business key như `orderId` nếu quy tắc là mỗi đơn chỉ có một yêu cầu xử lý thuộc loại đó.
- Tạo unique constraint ở database theo khóa phù hợp, vì kiểm tra “chưa tồn tại” trong Java chưa đủ khi có xử lý song song.
- Đặt việc ghi dấu event đã xử lý và cập nhật state của Fulfillment trong **cùng transaction**.
- Với side effect ngoài database (gửi email, gọi API), sử dụng idempotency key hoặc một cơ chế lưu yêu cầu gửi bền vững trước khi thực hiện.

Event ID là định danh cho một lần phát sinh sự kiện: khi xử lý lại **chính sự kiện đó**, giữ nguyên ID. Nếu phát một sự kiện mới có cùng `orderId` nhưng đại diện cho một lần thay đổi nghiệp vụ khác, ID phải khác và consumer cần phân biệt theo quy tắc miền nghiệp vụ.

## 7. Chọn cơ chế listener phù hợp với transaction

Spring Framework và Spring Modulith hỗ trợ nhiều kiểu xử lý event. Chúng khác nhau ở thời điểm callback chạy, tính đồng bộ và transaction.

| Cơ chế | Đặc điểm | Tác động |
| --- | --- | --- |
| `@EventListener` | Với cấu hình mặc định, gọi đồng bộ khi publisher phát event | Consumer có thể chạy khi transaction publisher chưa commit; lỗi listener có thể ảnh hưởng lời gọi publisher |
| `@TransactionalEventListener` | Mặc định chờ phase `AFTER_COMMIT` | Chỉ phản ứng sau transaction commit; bản thân annotation không tạo luồng bất đồng bộ hay transaction ghi mới |
| `@Async` + `@TransactionalEventListener` | Callback được lập lịch bất đồng bộ khi có async execution phù hợp | Publisher không chờ consumer xử lý xong; cần quan tâm executor và xử lý exception |
| `@ApplicationModuleListener` | Annotation tiện ích của Spring Modulith: listener sau commit, bất đồng bộ, chạy trong transaction mới | Phù hợp cho những tác vụ liên module có thể hoàn tất độc lập sau commit |

`@ApplicationModuleListener` được thiết kế cho giao tiếp giữa các application module và kết hợp các đặc tính của `@Async`, `@TransactionalEventListener` và `@Transactional(propagation = REQUIRES_NEW)`. Cần cấu hình cơ chế xử lý bất đồng bộ phù hợp khi sử dụng, đồng thời hiểu rằng transaction của listener không giống transaction nghiệp vụ đã commit của publisher.

### Luồng thời gian sau commit

~~~mermaid
sequenceDiagram
    autonumber
    actor Client
    participant O as Orders
    participant DB as Orders DB
    participant E as Event infrastructure
    participant F as Fulfillment
    participant N as Notifications
    Client->>O: confirm(orderId)
    O->>DB: Cập nhật Order (transaction Orders)
    O->>E: publishEvent(OrderConfirmed)
    O->>DB: COMMIT
    E-->>F: @ApplicationModuleListener
    E-->>N: @ApplicationModuleListener
    F->>F: Tạo request (transaction riêng)
    N->>N: Lên lịch thông báo (transaction riêng)
~~~

Sơ đồ mô tả trách nhiệm, không bảo đảm Fulfillment luôn chạy trước Notifications. Khi listener bất đồng bộ, thứ tự thực tế phụ thuộc executor, tải hệ thống và thời gian xử lý.

**Khi Orders rollback**, các listener sau commit không được kích hoạt cho một giao dịch đã bị hủy. **Khi Orders commit nhưng Fulfillment lỗi**, commit của Orders không bị đảo ngược. Đây là đặc tính phải được chấp nhận và được thiết kế rõ trong luồng nghiệp vụ.

Một `@TransactionalEventListener` mặc định thường cần event được phát bên trong transaction; nếu phát ngoài transaction thì listener không được gọi, trừ khi bật `fallbackExecution` và chấp nhận khác biệt ngữ nghĩa.

### Trường hợp không nên tách bằng listener sau commit

Nếu thao tác tạo đơn hàng chỉ được coi là thành công khi **đã giữ được tồn kho ngay lập tức**, yêu cầu giữ hàng có thể cần diễn ra đồng bộ trước khi commit hoặc theo quy trình reserve/confirm chuyên biệt. Chuyển một ràng buộc bắt buộc thành listener bất đồng bộ có thể khiến API trả thành công trong khi điều kiện nghiệp vụ chưa được thỏa mãn.

Vì vậy, thiết kế event phải bắt đầu bằng câu hỏi về **ràng buộc tính nhất quán**, không chỉ mong muốn giảm số lời gọi service.

## 8. Eventual consistency và state của từng module

Giao tiếp event sau commit thường tạo ra một khoảng thời gian mà state của các module **chưa hội tụ**:

~~~text
12:00:00.000  Orders:       CONFIRMED
12:00:00.010  Fulfillment:  Chưa có yêu cầu giao hàng
12:00:00.020  Notifications: Chưa có thông báo
12:00:00.500  Fulfillment:  REQUESTED
12:00:01.200  Notifications: SCHEDULED
~~~

Đây có thể là hành vi bình thường nếu nghiệp vụ cho phép xử lý bất đồng bộ. Module sở hữu state mới là nơi quyết định trạng thái thực sự của mình; không nên cho rằng một event đã phát đồng nghĩa tất cả consumer đã xử lý xong.

Ví dụ màn hình quản lý đơn hàng có thể hiển thị “Đã xác nhận, đang chuẩn bị xử lý” trong lúc yêu cầu giao hàng chưa được tạo. Nếu giao diện yêu cầu trạng thái tổng hợp chính xác, hãy xác định rõ nguồn dữ liệu, cách đồng bộ và giới hạn thời gian trễ chấp nhận được.

Các vấn đề cần cân nhắc:

| Tình huống | Hướng xử lý |
| --- | --- |
| Listener xử lý muộn vài giây | Hiển thị trạng thái trung gian; theo dõi thời gian xử lý để đáp ứng SLA |
| Event giao lại | Thực hiện thao tác idempotent với khóa nghiệp vụ hoặc event ID |
| Hai event của cùng aggregate xử lý khác thứ tự | Dùng version, state-machine guard hoặc truy vấn trạng thái hiện tại theo contract thích hợp |
| Consumer phải biết trạng thái đang hiện hành | Cung cấp API truy vấn công khai hoặc một read model có cơ chế đồng bộ rõ ràng |
| Một bước phải hoàn thành trước khi API trả thành công | Dùng API đồng bộ hoặc thiết kế lại workflow; không giả định listener sau commit chạy ngay |

**Đừng gọi event là “lệnh cập nhật state của module khác”.** Publisher công bố sự thật; consumer nhận thông tin và áp dụng quy tắc để quyết định mình có nên chuyển state hay không. Cách tổ chức đó giữ quyền sở hữu dữ liệu ở từng module.

## 9. Độ tin cậy: event publication registry, retry và quan sát

Spring application events cơ bản có phạm vi tiến trình. Nếu ứng dụng dừng sau khi commit Orders nhưng trước khi Fulfillment xử lý, cần một cơ chế bền vững để biết publication nào còn thiếu.

**Event Publication Registry** của Spring Modulith hỗ trợ theo dõi việc phát event đến các transactional listener khi đã có cấu hình lưu trữ publication thích hợp. Tùy phiên bản và cấu hình, publication được ghi nhận trong cơ sở dữ liệu, đánh dấu hoàn thành sau khi listener chạy thành công và có thể được xử lý lại khi chưa hoàn tất.

~~~mermaid
flowchart TD
    A["Orders publish OrderConfirmed"] --> B["Transaction commit"]
    B --> C["Publication chờ listener"]
    C --> D{"Listener thành công?"}
    D -->|Có| E["Đánh dấu completed"]
    D -->|Lỗi| F["Publication chưa completed"]
    F --> G["Theo dõi / khôi phục / retry"]
    G --> D
~~~

Registry giải quyết bài toán **theo dõi và khôi phục publication**, nhưng không đảm bảo rằng mọi side effect của consumer chỉ xảy ra một lần. Ví dụ Fulfillment đã commit request, sau đó tiến trình dừng trước khi hệ thống ghi nhận publication hoàn thành. Khi xử lý lại, listener có thể được gọi thêm lần nữa. Vì thế, cần kết hợp registry với idempotency.

Những điểm cần chuẩn bị khi triển khai thực tế:

1. **Lưu trữ publication:** chọn tích hợp lưu trữ (JDBC/JPA hoặc phương án được phiên bản Spring Modulith hỗ trợ) phù hợp cơ sở dữ liệu và khởi tạo schema/migration.
2. **Khôi phục publication chưa hoàn thành:** xác định cơ chế resubmission/republication và lịch chạy thích hợp theo phiên bản đang dùng; không giả định framework tự retry vô hạn theo cấu hình mặc định.
3. **Tái thử có kiểm soát:** phân biệt lỗi tạm thời (timeout) với lỗi nghiệp vụ không thể tự sửa; dùng backoff/giới hạn lần thử nếu môi trường triển khai yêu cầu.
4. **Tính idempotent:** bảo vệ DB và side effect theo event ID hoặc business key; transaction của consumer phải rõ ràng.
5. **Quan sát:** theo dõi số publication còn pending, tuổi của publication, số lần lỗi, độ trễ từ commit đến xử lý, và tỷ lệ thành công theo listener.
6. **Chẩn đoán:** ghi `eventId`, `orderId`, loại event và tên listener trong log/trace một cách nhất quán, không log dữ liệu nhạy cảm.

Ví dụ thông tin log hữu ích:

~~~text
eventType=OrderConfirmed eventId=... orderId=... listener=Fulfillment status=COMPLETED
eventType=OrderConfirmed eventId=... orderId=... listener=Notifications status=FAILED reason=SMTP_TIMEOUT
~~~

Khi sự kiện cần vượt ra ngoài tiến trình ứng dụng đến microservice hoặc broker, cần thêm cơ chế externalization/outbox/messaging thích hợp. Chỉ dùng `ApplicationEventPublisher` và đăng ký `@ApplicationModuleListener` **không** tự tạo tích hợp Kafka hay RabbitMQ.

## 10. Thiết kế contract để nhiều module có thể dùng lâu dài

Một event contract tốt cần nhỏ, rõ ràng và có ý nghĩa nghiệp vụ ổn định.

### Đặt tên theo sự thật đã xảy ra

Ưu tiên:

- `OrderConfirmed`: đơn hàng đã được xác nhận.
- `PaymentCaptured`: tiền đã được thu thành công.
- `ShipmentDispatched`: lô hàng đã được bàn giao cho đơn vị vận chuyển.

Tránh dùng một event với tên mệnh lệnh như `SendOrderEmailNow` khi mục đích là công bố việc xác nhận đơn; event mệnh lệnh kéo trách nhiệm quyết định về publisher.

### Chọn payload

Các nhóm dữ liệu thường được cân nhắc gồm:

- **Identity:** `eventId`, `orderId` và ID của thực thể liên quan.
- **Business snapshot:** dữ liệu đã chốt tại thời điểm phát event, nếu consumer thật sự cần.
- **Metadata:** `occurredAt` hoặc `aggregateVersion` khi cần kiểm soát thứ tự và đối soát.
- **Schema evolution:** quy ước cho field thêm mới, đổi tên hoặc đổi ngữ nghĩa khi consumer đã phụ thuộc vào contract.

Không nên đưa các đối tượng ORM, connection, service bean hoặc cấu trúc chi tiết của database vào event.

### Thay đổi schema

Giả sử ban đầu chỉ có `OrderConfirmed(eventId, orderId, occurredAt)`. Sau này Notifications cần ngôn ngữ của khách hàng. Có ba lựa chọn điển hình: thêm dữ liệu snapshot ổn định vào event, dùng public query API của một module sở hữu dữ liệu phù hợp, hoặc xây read model của Notifications. Mỗi cách có trade-off về coupling, hiệu năng và khả năng dùng lại event lịch sử.

Cần lưu ý các publication đang chờ có thể chứa payload theo schema cũ. Khi triển khai thay đổi lớn, định nghĩa chiến lược tương thích hoặc chuyển đổi serialization tương ứng với cơ chế lưu trữ đang dùng.

### Kiểm soát chuỗi event

Listener có thể phát một event mới khi *nghiệp vụ của chính module đó* hoàn tất, ví dụ Fulfillment nhận `OrderConfirmed` rồi tạo `FulfillmentRequested`. Điều này có thể tạo workflow nhiều bước, nhưng dễ gặp vòng lặp:

~~~text
OrderConfirmed
    -> FulfillmentRequested
        -> OrderStatusChanged
            -> OrderConfirmed (vòng lặp ngoài ý muốn)
~~~

Nên vẽ rõ ai sở hữu state, điều kiện chuyển trạng thái và event nào phát sinh một lần. Bảo vệ các trạng thái terminal, tránh việc một event đến lặp khiến nghiệp vụ quay lại trạng thái cũ.

## 11. Kiểm thử giao tiếp và ranh giới module

Một bài test có giá trị cần xác minh rằng event biểu thị đúng sự thật, contract có thể truy cập hợp lệ, listener phản ứng đúng và cơ chế khôi phục không tạo side effect trùng.

### 11.1. Kiểm tra dependency giữa các module

Spring Modulith có thể phân tích mô hình module và kiểm tra các quy tắc dependency. Ví dụ trong bài kiểm thử kiến trúc:

~~~java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void modulesRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm tra này hữu ích để phát hiện việc một module tham chiếu type không thuộc API công khai của module khác hoặc một số loại vi phạm ranh giới được Spring Modulith hỗ trợ. Nó không tự chứng minh business flow hay idempotency đúng.

### 11.2. Kiểm tra publisher

Trong test module Orders, xác minh:

- Xác nhận thành công làm cập nhật state và phát đúng event có ID, aggregate ID, dữ liệu cần thiết.
- Xác nhận bị từ chối không phát event “đã xác nhận”.
- Callback lặp không tạo thêm một chuyển trạng thái nghiệp vụ.
- Nếu transaction rollback, không có kết quả sau commit được consumer coi là thành công.

Có thể dùng `@ApplicationModuleTest` và hỗ trợ `PublishedEvents` của Spring Modulith để quan sát các event đã phát trong test context. Các assertion chính xác tùy phiên bản API; hãy kiểm tra cách cấu hình module test trong project thực tế.

### 11.3. Kiểm tra listener và trạng thái cuối

Với Fulfillment, test nên bao gồm:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Nhận `OrderConfirmed` hợp lệ | Tạo đúng một fulfillment request và lưu state của Fulfillment |
| Nhận lặp cùng event | Không phát sinh request thứ hai |
| Consumer lỗi tạm thời | Publication còn chưa hoàn tất theo cơ chế registry được cấu hình |
| Xử lý lại thành công | Publication hoàn tất, state không bị nhân đôi |
| Nhận event cũ sau thay đổi nghiệp vụ mới | Quy tắc state ngăn chuyển ngược hoặc xử lý sai |
| Notifications thất bại | Kết quả commit của Orders không bị đảo ngược; Fulfillment vẫn xử lý độc lập |

Với listener sau commit và bất đồng bộ, kiểm thử nên **đợi điều kiện cuối cùng với timeout hữu hạn**, không dùng sleep cố định hoặc giả định gọi `publishEvent` xong là consumer đã hoàn tất. Test bọc trong transaction mặc định rollback cũng có thể khiến listener `AFTER_COMMIT` không chạy như khi deploy thực tế.

### 11.4. Phân biệt hai cấp kiểm thử

- **Architecture test:** xác minh dependency hợp lệ giữa module; event contract đặt đúng API.
- **Integration test:** xác minh event được phát/nhận và state hoặc side effect được lưu đúng qua các transaction.

Cả hai cần thiết vì code có thể tuân thủ dependency nhưng sai nghiệp vụ; ngược lại, tích hợp có thể chạy được dù một module đang import repository nội bộ của module khác.

## 12. Bài thực hành: tách một luồng gọi trực tiếp

Ban đầu có mã kiểu:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    orders.confirm(orderId);
    fulfillment.createRequest(orderId);
    notifications.sendOrderConfirmed(orderId);
}
~~~

Đoạn minh họa chứa các trách nhiệm khác nhau trong một use case và giả định kết quả của cả Fulfillment/Notifications là một phần của luồng xác nhận đồng bộ. Trước khi refactor, cần xác định các phụ thuộc nào là invariant bắt buộc ngay lập tức.

Với phần công việc được phép xử lý sau commit, thực hiện theo các bước:

1. Xác định sự thật trong Orders cần công bố: `OrderConfirmed`; đặt contract trong API công khai của module.
2. Cho Orders xử lý transaction, xác nhận state rồi `publishEvent`.
3. Đưa công việc của Fulfillment và Notifications sang các `@ApplicationModuleListener` độc lập.
4. Bảo vệ các listener bằng unique constraint/idempotency và transaction riêng.
5. Cấu hình publication registry cùng cơ chế quan sát/khôi phục nếu yêu cầu độ tin cậy khi ứng dụng restart.
6. Thêm architecture test và integration test cho lỗi listener, rollback, duplicate event.
7. Xác định trạng thái trung gian trên API/UI và cam kết độ trễ xử lý chấp nhận được.

**Câu hỏi tự đánh giá:**

- Nếu Fulfillment lỗi sau khi Orders commit, API xác nhận đơn có phải trả lỗi và đảo trạng thái Orders không? Vì sao?
- Nếu thêm module Loyalty thưởng điểm cho đơn đã xác nhận, cần thay đổi code tại Orders không?
- Vì sao event contract trong `orders.internal` có thể vi phạm ranh giới module?
- Vì sao event publication registry vẫn phải đi kèm listener idempotent?
- Nếu việc trừ tồn kho là điều kiện bắt buộc của thao tác xác nhận, có nên chuyển hẳn sang listener sau commit không?

## 13. Tổng kết kiến thức

Giao tiếp qua event giúp các application module trong Spring Modulith mở rộng hành vi theo sự kiện nghiệp vụ mà giảm lời gọi trực tiếp và giảm số module publisher cần biết. Muốn đạt được điều đó, event contract phải thuộc một API công khai rõ ràng; publisher công bố sự thật, consumer tự sở hữu state và quy tắc xử lý.

Khi chọn listener sau commit, cần chấp nhận khả năng state của các module hội tụ theo thời gian. Event publication registry, khôi phục publication, retry có kiểm soát, idempotency, kiểm thử module và quan sát độ trễ tạo nên cơ sở thực hành giao sự kiện đáng tin cậy. Việc chọn giữa đồng bộ và bất đồng bộ vẫn phải dựa trên bất biến nghiệp vụ, khả năng chịu lỗi và yêu cầu nhất quán của từng use case.
