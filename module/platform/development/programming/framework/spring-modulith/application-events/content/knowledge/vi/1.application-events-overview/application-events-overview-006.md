# Event và message trong Spring Modulith

Khi chia một ứng dụng Spring Boot thành các **application module** bằng Spring Modulith, mỗi module nên sở hữu một phạm vi nghiệp vụ rõ ràng. Một thay đổi trong module này đôi khi cần kích hoạt công việc ở module khác: đơn hàng đã được tạo thì gửi email xác nhận, cập nhật chỉ số bán hàng hoặc bắt đầu quy trình giao hàng. Nếu module đặt hàng gọi trực tiếp mọi service còn lại, số lượng phụ thuộc sẽ tăng và việc thay đổi từng module trở nên khó khăn.

**Event** và **message** giúp biểu diễn sự giao tiếp đó theo hai góc nhìn khác nhau: *điều gì đã xảy ra trong nghiệp vụ* và *thông tin ấy được chuyển đi như thế nào*. Trong Spring Modulith, sự phân biệt này đặc biệt quan trọng vì các module có thể giao tiếp bằng application events ngay **trong cùng một tiến trình Java**, sau đó mới cần cân nhắc việc chuyển sự kiện ra message broker.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **domain event**, **application event**, **integration event**, **message** và **command**.
- Giải thích vì sao Spring Modulith thường dùng event để giảm phụ thuộc trực tiếp giữa các module.
- Tạo một event bất biến, publish bằng `ApplicationEventPublisher` và nhận bằng listener thuộc module khác.
- Phân biệt lúc phát sự kiện với lúc listener chạy, đặc biệt khi có transaction.
- Nhận diện ranh giới giữa gửi event nội bộ, phát message ra broker và bảo đảm giao sự kiện đáng tin cậy.
- Chọn cách giao tiếp thích hợp với nhu cầu nhất quán, xử lý lỗi và độ trễ của nghiệp vụ.

## 2. Event: một sự thật đã xảy ra

**Event (sự kiện)** mô tả một sự việc đã xảy ra và có ý nghĩa với hệ thống. Event thường được đặt tên bằng động từ ở dạng quá khứ: `OrderPlaced` (đơn hàng đã được đặt), `PaymentCaptured` (đã thu tiền), `InventoryReserved` (đã giữ hàng).

Ví dụ, sau khi module `ordering` ghi nhận một đơn hàng hợp lệ, nó có thể công bố:

~~~java
package com.example.shop.ordering;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID orderId,
        Instant occurredAt
) {}
~~~

`OrderPlaced` là **một Java record thông thường**, không bắt buộc kế thừa `ApplicationEvent` hoặc triển khai interface riêng của Spring. Hai trường `orderId` và `occurredAt` truyền đạt *đơn hàng nào* và *thời điểm nghiệp vụ ghi nhận sự kiện*. Cách dùng record giúp dữ liệu sự kiện bất biến ở mức cấu trúc và biểu diễn rõ hợp đồng giữa các module.

Một event tốt có các đặc điểm:

1. **Mô tả kết quả đã xảy ra**, thay vì ra lệnh cho bên nhận phải thực hiện một hành động.
2. **Có ý nghĩa nghiệp vụ**: bên nhận hiểu sự kiện mà không cần biết luồng xử lý nội bộ của bên phát.
3. **Có hợp đồng dữ liệu rõ ràng**: tên, kiểu dữ liệu, ý nghĩa trường và các thay đổi phiên bản được kiểm soát.
4. **Không mang thực thể JPA đang được quản lý** hoặc phụ thuộc vào session/lazy loading của module phát; ưu tiên ID và dữ liệu đơn giản cần thiết.

Chú ý: một event *được tạo trong mã nguồn* chưa đồng nghĩa với việc transaction nghiệp vụ *đã commit thành công*. Listener chạy lúc nào còn phụ thuộc vào cơ chế đăng ký lắng nghe, được giải thích ở phần sau.

### Domain event và application event

Hai tên gọi này trả lời những câu hỏi khác nhau:

| Khái niệm | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **Domain event** | Sự kiện có nghĩa trong mô hình nghiệp vụ; phản ánh thay đổi trạng thái nghiệp vụ | `OrderPlaced`, `PaymentFailed` |
| **Application event** | Cơ chế phát/nhận sự kiện trong ứng dụng Spring | Gọi `ApplicationEventPublisher.publishEvent(orderPlaced)` |
| **Integration event** | Hợp đồng sự kiện dành cho hệ thống hoặc dịch vụ bên ngoài, có yêu cầu tương thích/phiên bản độc lập | `commerce.order-placed.v1` gửi tới hệ thống vận chuyển |

Một đối tượng như `OrderPlaced` có thể **vừa là domain event về mặt ý nghĩa, vừa là payload được Spring dùng làm application event**. Khi cần tích hợp bên ngoài, cùng một sự thật nghiệp vụ có thể được ánh xạ sang integration event với định dạng và chính sách công bố riêng. Không cần coi ba tên gọi này là ba kiểu class bắt buộc.

## 3. Message: đơn vị thông tin được chuyển qua một kênh

**Message (thông điệp)** là đơn vị dữ liệu được truyền giữa các thành phần hoặc hệ thống. Message thường bao gồm:

- **Payload**: dữ liệu chính, chẳng hạn nội dung `OrderPlaced`.
- **Metadata/headers**: mã định danh, loại sự kiện, phiên bản, correlation ID, thời gian tạo, thông tin định tuyến hoặc tracing tùy hạ tầng.
- **Ngữ cảnh vận chuyển**: channel, queue, topic, protocol hoặc cơ chế nhận/xác nhận thông điệp.

Ví dụ một thông điệp JSON *minh họa* được gửi sang hệ thống bên ngoài:

~~~json
{
  "eventId": "98f7bc42-9f77-49bd-8a73-b5f05f45f6a8",
  "eventType": "order.placed.v1",
  "occurredAt": "2026-11-25T08:00:00Z",
  "correlationId": "checkout-42",
  "payload": {
    "orderId": "e01d1a86-9a4b-4745-b03d-13d22def0df6"
  }
}
~~~

Đây là **envelope minh họa do ứng dụng tự thiết kế**, không phải cấu trúc JSON mặc định mà Spring Modulith tự động tạo. Trường `eventId` nên giữ ổn định cho cùng một sự kiện khi phát lại để bên nhận có thể khử trùng lặp.

Trong hệ sinh thái Spring, `org.springframework.messaging.Message<T>` là một abstraction gồm payload và headers. Tuy nhiên, **không phải mọi Spring application event đều là `Message<T>`**, và gọi `ApplicationEventPublisher.publishEvent(...)` **không tự động gửi message tới Kafka, RabbitMQ hay hệ thống bên ngoài**. Việc chuyển sang broker cần một cơ chế externalization hoặc adapter/producer được cấu hình riêng.

### Event, message và command khác nhau thế nào?

| Tiêu chí | Event | Message | Command |
| --- | --- | --- | --- |
| Câu hỏi chính | Điều gì đã xảy ra? | Dữ liệu được truyền đi dưới dạng nào? | Cần thực hiện hành động gì? |
| Ví dụ | `OrderPlaced` | Một message mang `OrderPlaced` và headers | `ReserveInventory` |
| Ý nghĩa | Công bố sự thật trong quá khứ | Đóng gói/chuyển tải dữ liệu | Yêu cầu một bên xử lý |
| Bên nhận | Thường có thể có nhiều bên quan tâm | Tùy kênh và mô hình định tuyến | Thường có bên chịu trách nhiệm cụ thể |
| Kết quả mong đợi | Bên phát không cần chỉ định từng phản ứng | Phụ thuộc payload và protocol | Thành công, thất bại hoặc kết quả của yêu cầu |

**Event có thể là payload của message; message có thể mang event, command hoặc loại dữ liệu khác.** Vì vậy, hai khái niệm không đồng nghĩa. Chẳng hạn `OrderPlaced` là một event, còn thông điệp được publish lên topic `orders.events` là cách vận chuyển event ấy.

## 4. Vì sao Spring Modulith dùng application events giữa các module?

Giả sử một ứng dụng có các module `ordering` (đặt hàng), `notification` (thông báo) và `analytics` (phân tích). Nếu service đặt hàng gọi trực tiếp cả `NotificationService` và `AnalyticsService`, module `ordering` phải biết và phụ thuộc vào hai module còn lại.

Với event, `ordering` chỉ cần công bố sự kiện theo hợp đồng chung. Mỗi module tiêu thụ tự quyết định có xử lý sự kiện đó hay không.

~~~mermaid
flowchart LR
    O["ordering<br/>Lưu đơn hàng"] --> P["ApplicationEventPublisher<br/>OrderPlaced"]
    P --> N["notification<br/>Gửi email"]
    P --> A["analytics<br/>Cập nhật thống kê"]
    P --> F["fulfillment<br/>Khởi tạo giao hàng"]
~~~

Các mũi tên thể hiện **luồng thông tin theo sự kiện**, không hàm ý ba listener chạy đồng thời hay giao sự kiện đã được lưu bền vững. Cách chạy phụ thuộc loại listener và cấu hình runtime.

Lợi ích chính:

- **Giảm phụ thuộc ở phía publisher**: thêm một module nghe `OrderPlaced` mà không phải sửa logic đặt hàng.
- **Giữ ranh giới trách nhiệm**: module `ordering` không cần biết chi tiết gửi email, tổng hợp báo cáo hay giao hàng.
- **Hỗ trợ mở rộng hành vi theo phản ứng**: nhiều listener độc lập có thể quan tâm cùng một sự kiện.
- **Phù hợp ứng dụng modular monolith**: các module tách biệt về kiến trúc nhưng vẫn hoạt động trong một ứng dụng Spring Boot.

Tuy nhiên, event **không xóa toàn bộ phụ thuộc**. Module tiêu thụ vẫn phụ thuộc vào **hợp đồng event** do module phát công bố. Nếu thay tên hoặc ý nghĩa của trường một cách tùy tiện, các listener vẫn có thể bị ảnh hưởng. Event cũng không mặc nhiên tạo ra khả năng chịu lỗi hoặc tách tiến trình như message broker.

## 5. Ví dụ: publish và consume sự kiện trong cùng ứng dụng

Giả sử tổ chức mã nguồn như sau:

~~~text
com.example.shop
├── ordering/
│   ├── OrderPlaced.java             # Hợp đồng event công khai
│   └── internal/
│       ├── OrderingService.java
│       └── OrderRepository.java
├── notification/
│   └── OrderNotificationListener.java
└── analytics/
    └── OrderAnalyticsListener.java
~~~

Trong cách bố trí module mặc định của Spring Modulith, **package gốc của một module là phần API được các module khác nhìn thấy**, còn `internal` dành cho hiện thực nội bộ. Việc công bố `OrderPlaced` ở `ordering` giúp module `notification` chỉ cần phụ thuộc vào hợp đồng event, không phải import `OrderingService` hay repository nội bộ.

### Bước 1: Module nguồn công bố event

~~~java
package com.example.shop.ordering.internal;

import com.example.shop.ordering.OrderPlaced;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderingService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderingService(
            OrderRepository orders,
            ApplicationEventPublisher events
    ) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public UUID placeOrder(OrderDraft draft) {
        // Ví dụ giả định repository trả về ID đơn hàng vừa lưu.
        UUID orderId = orders.save(draft);

        events.publishEvent(new OrderPlaced(orderId, Instant.now()));

        return orderId;
    }
}
~~~

`OrderDraft` và `OrderRepository` là các kiểu nghiệp vụ giả định của module `ordering`; đoạn mã tập trung vào giao tiếp sự kiện. `ApplicationEventPublisher` nhận một object thường, không yêu cầu record `OrderPlaced` kế thừa class của Spring.

Điểm cần hiểu: lệnh `publishEvent(...)` được gọi **trong transaction** của `placeOrder`. Với listener đồng bộ thông thường, phản ứng có thể bắt đầu *ngay khi publish*, trước khi transaction kết thúc. Vì vậy không thể suy từ tên `OrderPlaced` rằng mọi bên nhận đã quan sát một đơn hàng được commit.

### Bước 2: Module khác lắng nghe sau commit

~~~java
package com.example.shop.notification;

import com.example.shop.ordering.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    private final ConfirmationSender sender;

    OrderNotificationListener(ConfirmationSender sender) {
        this.sender = sender;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        sender.sendConfirmation(event.orderId());
    }
}
~~~

`ConfirmationSender` là cổng gửi thông báo do module `notification` quản lý. Listener không gọi ngược vào `ordering.internal`.

Trong Spring Modulith, `@ApplicationModuleListener` là annotation tiện ích kết hợp ngữ nghĩa **transactional event listener sau commit**, **xử lý bất đồng bộ** (khi hạ tầng `@Async` được kích hoạt) và **transaction mới với `REQUIRES_NEW`** cho phần xử lý listener. Vì thế nó phù hợp với tác vụ phản ứng sau khi trạng thái nghiệp vụ gốc đã được xác nhận, chẳng hạn ghi trạng thái gửi email hoặc tạo bản ghi nghiệp vụ ở module khác.

Nếu dùng `@Async`, ứng dụng cần có cấu hình thực thi bất đồng bộ thích hợp (ví dụ `@EnableAsync` và executor phù hợp). Không nên dựa vào annotation để suy ra thứ tự, thời điểm hoàn thành hoặc khả năng retry mà chưa xác minh cấu hình thực tế.

### Bước 3: Thêm một subscriber mà không sửa publisher

~~~java
package com.example.shop.analytics;

import com.example.shop.ordering.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderAnalyticsListener {

    private final OrderMetrics metrics;

    OrderAnalyticsListener(OrderMetrics metrics) {
        this.metrics = metrics;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        metrics.recordOrder(event.orderId());
    }
}
~~~

`notification` và `analytics` đều tiêu thụ `OrderPlaced`. Module `ordering` không cần biết có bao nhiêu consumer, họ gửi email hay ghi thống kê, và họ triển khai bằng class/service nào.

## 6. Thời điểm listener chạy quyết định ý nghĩa thực tế của event

**Phát sự kiện** và **hoàn thành xử lý sự kiện** là hai thao tác khác nhau. Cùng một đối tượng `OrderPlaced` có thể được xử lý theo các cơ chế sau:

| Cơ chế | Khi nào thường chạy? | Tác động quan trọng |
| --- | --- | --- |
| `@EventListener` thông thường | Đồng bộ ngay lúc publish, trên luồng của publisher theo cấu hình mặc định | Listener có thể chạy trước commit; exception có thể lan về publisher và làm transaction thất bại |
| `@TransactionalEventListener` với `AFTER_COMMIT` | Sau khi transaction phát event commit thành công | Tránh phản ứng đối với dữ liệu đã rollback; mặc định không tự tạo transaction ghi dữ liệu mới |
| `@ApplicationModuleListener` | Listener giao dịch sau commit; có hỗ trợ bất đồng bộ và transaction độc lập theo annotation tổng hợp | Giảm phụ thuộc vào luồng giao dịch của publisher; cần quản lý lỗi và việc xử lý lặp |
| Message broker / externalization | Khi adapter đã chuyển event sang kênh bên ngoài và consumer nhận được | Phụ thuộc cấu hình, cơ chế xác nhận, độ bền và retry của hệ thống tích hợp |

Đối với `@TransactionalEventListener`, phase mặc định là `AFTER_COMMIT`. Có thể ghi rõ để thể hiện chủ ý:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    // Chỉ chạy sau khi transaction công bố event commit.
}
~~~

Theo mặc định, `@TransactionalEventListener` cần có một transaction đang hoạt động lúc publish; khi không có transaction, listener sẽ không được gọi, trừ khi cấu hình `fallbackExecution = true`. Nếu handler cần ghi dữ liệu sau commit, hãy dùng transaction mới phù hợp, ví dụ `REQUIRES_NEW` hoặc `@ApplicationModuleListener`, thay vì mặc định cho rằng transaction đã commit vẫn có thể ghi thêm.

Xét một luồng xảy ra lỗi:

1. `placeOrder` ghi đơn hàng và publish `OrderPlaced`.
2. Sau đó có lỗi làm transaction `ordering` rollback.
3. Listener `@EventListener` đồng bộ **có thể đã gửi email** trước rollback, tạo dữ liệu không nhất quán.
4. Listener `@TransactionalEventListener(AFTER_COMMIT)` **không chạy** trong trường hợp transaction rollback.

Vì vậy, các tác vụ có tác dụng phụ bên ngoài như gửi email, gọi API vận chuyển hoặc đẩy sự kiện đi thường cần cân nhắc ranh giới commit. Đối với nghiệp vụ bắt buộc thành công đồng thời và phải trả kết quả tức thì, đôi khi một lời gọi service rõ ràng với transaction thích hợp sẽ dễ kiểm soát hơn việc phát event.

## 7. Event nội bộ chưa phải message gửi ra ngoài

Trong **modular monolith**, `ApplicationEventPublisher` cùng các listener có thể hoạt động hoàn toàn trong một JVM. Không có yêu cầu phải cài Kafka hoặc RabbitMQ chỉ để `notification` nhận `OrderPlaced` từ `ordering`.

Khi một hệ thống khác cần nhận thông tin, kiến trúc có thêm một ranh giới:

~~~mermaid
flowchart LR
    A["ordering<br/>OrderPlaced"] --> B["Application events<br/>nội bộ JVM"]
    B --> C["Adapter/externalization<br/>Ánh xạ hợp đồng"]
    C --> D[("Broker / topic / queue")]
    D --> E["Consumer<br/>hệ thống khác"]
~~~

**Externalization** là việc chọn và chuyển các application events thích hợp ra hạ tầng messaging, thường qua phần hỗ trợ tích hợp của Spring Modulith hoặc adapter do ứng dụng xây dựng. Bước này có thể cần ánh xạ tên event, payload, định tuyến, serialization và bảo mật. Việc có class `OrderPlaced` hoặc gọi `publishEvent` **chưa đủ** để mặc định bảo đảm có message bên ngoài.

Một số khác biệt cần nhớ:

| Khía cạnh | Application event giữa các module | Message qua broker |
| --- | --- | --- |
| Không gian thực thi | Thường trong một ứng dụng/JVM | Có thể qua nhiều tiến trình/máy |
| Kết nối | Spring event infrastructure và listener | Producer, broker/channel, consumer |
| Dạng payload | Có thể là object Java trong bộ nhớ | Phải có dạng truyền tải/serialization phù hợp |
| Độ trễ | Thường thấp, tùy listener đồng bộ/bất đồng bộ | Bao gồm mạng, broker và consumer |
| Retry và lưu bền | Cần cơ chế và cấu hình riêng | Tùy chính sách broker, producer/consumer và ứng dụng |
| Mức độ tương thích | Phụ thuộc hợp đồng Java giữa các module | Phải quản lý tương thích hợp đồng dữ liệu qua phiên bản triển khai |

Đừng đồng nhất **async** với **durable messaging**: `@Async` chỉ chuyển công việc sang executor, không biến sự kiện thành message được lưu bền trên broker.

## 8. Điều gì xảy ra nếu listener thất bại?

Giả sử đơn hàng đã commit nhưng việc gửi email thất bại vì dịch vụ email tạm ngừng. Có ba vấn đề riêng:

1. **Tính nhất quán**: đơn hàng được lưu thành công có nên bị hủy vì email lỗi không? Thông thường là không; email là phản ứng sau commit.
2. **Khả năng khôi phục**: nếu listener lỗi hoặc tiến trình ứng dụng dừng, có nơi nào ghi nhận sự kiện chưa xử lý để chạy lại không?
3. **Tính idempotent**: nếu cùng một sự kiện được chạy lại, hệ thống có gửi trùng email hoặc ghi trùng thống kê không?

Spring Modulith cung cấp **Event Publication Registry** để theo dõi việc công bố và hoàn thành xử lý sự kiện cho các listener được hỗ trợ, khi ứng dụng đã cấu hình thành phần persistence thích hợp. Registry có thể giúp phát hiện các publication chưa hoàn tất và tạo cơ sở cho chiến lược chạy lại. Đây là tính năng cần **bật và cấu hình** theo phiên bản/dependency sử dụng; không nên coi việc gọi `publishEvent` là đủ để có durable retry.

Khi thiết kế listener, giả định thực tế an toàn là **một event có thể được xử lý lại**:

~~~text
OrderPlaced(eventId=E-123, orderId=O-456)
                  |
                  v
     Kiểm tra eventId đã xử lý chưa?
             /             \
           Có              Chưa
           |                |
      Bỏ qua an toàn    Thực hiện tác vụ
                            |
                   Lưu dấu đã xử lý
~~~

Mẫu trên là nguyên tắc idempotency; triển khai thực tế cần transaction, unique constraint hoặc cơ chế ghi nhận thích hợp để tránh trường hợp hai worker xử lý cùng lúc. Với các thao tác bên ngoài như gửi email, tính idempotent đầu-cuối còn phụ thuộc API/đối tác nhận có hỗ trợ khóa chống trùng hay không.

**Registry không thay thế toàn bộ thiết kế delivery.** Chẳng hạn, khi event được externalize, cần xem xét thêm retry của adapter, lỗi broker, tình huống đã gửi thành công nhưng chưa ghi nhận thành công và khả năng consumer nhận trùng. Các nhu cầu chính xác về “ít nhất một lần”, thứ tự, atomicity hoặc outbox phụ thuộc cách triển khai.

## 9. Thiết kế hợp đồng event để các module dễ phát triển độc lập

**Đặt tên theo sự kiện đã xảy ra.** `OrderPlaced` nói về trạng thái nghiệp vụ; `SendConfirmationEmail` là command ngầm quyết định hành động của module khác. Nếu một event chỉ tồn tại để ra lệnh cho đúng một consumer, hãy cân nhắc đó thực chất là command hay lời gọi trực tiếp.

**Công bố hợp đồng ở bề mặt API module.** Đặt event public trong package API được phép truy cập, giữ service/repository nội bộ trong `internal`. Spring Modulith có cơ chế xác minh ranh giới module; đặt class trong package đúng cách vẫn cần bảo đảm listener không truy cập implementation của module nguồn.

**Truyền đúng dữ liệu cần thiết.** ID cho phép consumer truy vấn dữ liệu khi thực sự cần, nhưng truy vấn xuyên module có thể tạo phụ thuộc ngầm hoặc race condition. Hãy chọn payload vừa đủ cho ngữ nghĩa sự kiện: ví dụ `orderId`, `occurredAt` và một số thuộc tính đã xác nhận; tránh chuyển nguyên entity, graph JPA, bí mật hoặc thông tin cá nhân không cần thiết.

**Phân biệt thời điểm phát với thời điểm hiệu lực.** Event phát trước commit không chứng minh trạng thái đã được lưu bền. Chọn listener sau commit khi bên nhận chỉ nên phản ứng với dữ liệu đã được xác nhận.

**Thiết kế cho lặp, lỗi và thứ tự.** Đừng mặc định tất cả event đến đúng một lần hay đúng thứ tự. Nếu thứ tự có ý nghĩa, cân nhắc thêm `aggregateId`, số phiên bản theo aggregate, event ID, điều kiện chuyển trạng thái và cơ chế xử lý phù hợp.

**Quản lý thay đổi phiên bản.** Khi event trở thành hợp đồng nhiều consumer cùng dùng, đổi tên trường hoặc thay đổi ý nghĩa có thể phá vỡ listener. Đặc biệt với integration events, cân nhắc chiến lược thêm trường tương thích, version rõ ràng và triển khai chuyển tiếp.

**Quan sát được vòng đời xử lý.** Log theo `eventId` và `correlationId`, theo dõi thời gian từ lúc publish đến lúc xử lý xong, số lần retry và các publication chưa hoàn tất. Đây là cơ sở để phát hiện lỗi giao sự kiện trong môi trường thật.

## 10. Chọn event hay lời gọi trực tiếp?

Xét bốn nhu cầu trong luồng mua hàng:

| Tình huống | Hướng tiếp cận thường phù hợp | Lý do |
| --- | --- | --- |
| Tính tổng tiền ngay để xác định có chấp nhận đơn hàng hay không | Gọi service/query theo hợp đồng rõ ràng | Kết quả cần ngay để quyết định transaction hiện tại |
| Sau khi đơn hàng commit, gửi email xác nhận | Application event + listener sau commit | Phản ứng phụ thuộc vào sự kiện đã xảy ra, có thể xử lý riêng |
| Sau khi đơn hàng commit, cập nhật báo cáo bán hàng | Application event + listener | Nhiều consumer độc lập và có thể chấp nhận độ trễ |
| Thông báo đơn hàng tới một dịch vụ giao vận chạy ở hệ thống khác | Integration event/message qua broker hoặc API tích hợp | Có ranh giới tiến trình và hợp đồng truyền tải độc lập |

Một quy tắc thực dụng: **chọn event khi điều quan trọng là thông báo một sự thật và các module khác tự quyết định phản ứng; chọn lời gọi trực tiếp hoặc command khi nghiệp vụ yêu cầu một hành động/giá trị cụ thể trước khi tiếp tục**. Nếu toàn bộ quy trình phải hoàn thành tức thì trong cùng transaction, dùng event thiếu chủ đích có thể che khuất phụ thuộc và làm việc xử lý lỗi khó hiểu hơn.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Event là message.” | Event là sự thật nghiệp vụ; message là đơn vị truyền tải có thể chứa event. |
| “Đã gọi `publishEvent` nghĩa là mọi module đã nhận và xử lý xong.” | Publish và completion là những bước riêng, phụ thuộc listener/transaction/runtime. |
| “Spring Modulith phải có Kafka để giao tiếp giữa module.” | Application events có thể chạy hoàn toàn trong ứng dụng Spring Boot. |
| “`@EventListener` luôn chạy sau commit.” | Listener thông thường thường chạy ngay khi publish; muốn sau commit dùng transactional listener phù hợp. |
| “`@Async` bảo đảm event sẽ không bao giờ mất.” | Async chỉ đổi cơ chế thực thi; durability cần cơ chế lưu và khôi phục riêng. |
| “Đã có registry thì listener không cần idempotent.” | Các kịch bản retry, crash và acknowledgment vẫn có thể dẫn đến xử lý lặp. |
| “Module dùng event là hoàn toàn độc lập.” | Consumer vẫn phụ thuộc vào event contract và các chính sách xử lý chung. |

## 12. Bài thực hành tự kiểm tra

Giả sử module `ordering` vừa lưu thành công một đơn hàng; `notification` phải gửi email và `analytics` phải ghi nhận doanh số.

1. Tạo record `OrderPlaced` gồm `eventId`, `orderId`, `occurredAt`. Giải thích trường nào dùng định danh sự kiện, trường nào dùng định danh đơn hàng.
2. Trong service đặt hàng có `@Transactional`, publish event sau khi lưu đơn hàng.
3. Tạo hai `@ApplicationModuleListener` ở hai module khác nhau. Mỗi listener chỉ dùng hợp đồng event và API thuộc module của mình.
4. Thử mô phỏng lỗi khiến transaction đặt hàng rollback: giải thích vì sao listener sau commit không được chạy.
5. Mô phỏng listener gửi email lỗi sau commit: xác định đơn hàng có còn được lưu không, và cần gì để retry an toàn.
6. Giả sử hệ thống giao vận là service độc lập: phác thảo adapter chuyển `OrderPlaced` sang integration message với event ID và phiên bản.

Bạn đạt mục tiêu khi giải thích được **event là thông tin nghiệp vụ nào được công bố, listener được kích hoạt ở thời điểm nào, message được chuyển qua ranh giới nào và ai chịu trách nhiệm xử lý lỗi**. Đây là nền tảng để đi sâu vào publisher/listener, xử lý sau commit, event publication registry, retry, kiểm thử và quan sát application events trong Spring Modulith.
