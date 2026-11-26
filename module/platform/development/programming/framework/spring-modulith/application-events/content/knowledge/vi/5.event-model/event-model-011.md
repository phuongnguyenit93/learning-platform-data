# Mục tiêu của event trong Spring Modulith

Trong ứng dụng có nhiều module, một hành động nghiệp vụ thường tạo ra nhiều phản ứng. Khi khách hàng đặt đơn thành công, hệ thống có thể cần gửi email, cập nhật thống kê, ghi nhận điểm thưởng hoặc khởi tạo giao hàng. Nếu module `ordering` trực tiếp gọi service của tất cả các module kia, mỗi chức năng mới lại kéo theo một phụ thuộc mới trong luồng đặt hàng.

**Mục tiêu cốt lõi của event là công bố một sự thật có ý nghĩa nghiệp vụ để những thành phần quan tâm tự quyết định cách phản ứng, trong khi bên phát không phải biết danh sách hay cách triển khai của các bên nhận.** Với Spring Modulith, cơ chế application events giúp đạt mục tiêu này ngay trong một modular monolith, nơi các module chạy trong cùng ứng dụng Spring Boot nhưng có ranh giới nghiệp vụ riêng.

Bài học thuộc chương **Mô hình sự kiện**, trong module `SPRING_MODULITH_APPLICATION_EVENTS`: tổ chức giao tiếp giữa các module bằng application events nhằm giảm phụ thuộc và bảo vệ ranh giới nghiệp vụ. Từ mục tiêu này, chúng ta sẽ xác định khi nào nên dùng event, khi nào không, cách chọn thời điểm xử lý sau commit, và điều kiện cần có để giao sự kiện đáng tin cậy thông qua registry, retry, kiểm thử và quan sát.

## 1. Học xong bài này, bạn cần làm được gì?

- Giải thích được *tại sao* một nghiệp vụ nên phát event, thay vì chỉ biết cách gọi `publishEvent(...)`.
- Nhận diện các mục tiêu cụ thể: giảm phụ thuộc mã nguồn, phân chia trách nhiệm, bổ sung nhiều phản ứng độc lập và kiểm soát ranh giới transaction.
- Phân biệt **mục tiêu kiến trúc** với **bảo đảm runtime**: publish không đồng nghĩa đã commit, listener đã chạy xong hay message đã giao bền vững.
- Chọn giữa event, lời gọi trực tiếp, command và message tích hợp dựa trên kết quả mà nghiệp vụ cần.
- Thiết kế một hợp đồng event giúp consumer hiểu sự thật đã xảy ra mà không truy cập implementation của publisher.
- Đề xuất tiêu chí kiểm thử và quan sát để đánh giá event có thực sự đem lại lợi ích hay không.

## 2. Event phải trả lời câu hỏi: “Chuyện gì đã xảy ra?”

**Event (sự kiện)** đại diện cho một sự việc đã xảy ra trong phạm vi nghiệp vụ. Ví dụ:

| Event | Ý nghĩa đã xảy ra | Những bên có thể quan tâm |
| --- | --- | --- |
| `OrderPlaced` | Hệ thống đã tiếp nhận đơn hàng theo quy tắc nghiệp vụ | Thông báo, thống kê, chuẩn bị giao hàng |
| `PaymentCaptured` | Giao dịch thu tiền đã được xác nhận | Đặt hàng, hóa đơn, kế toán |
| `InventoryReserved` | Lượng hàng được giữ cho yêu cầu cụ thể | Đặt hàng, vận chuyển |
| `CustomerRegistered` | Khách hàng đã được đăng ký thành công | Chào mừng, quản lý ưu đãi, phân tích |

Tên event thường thể hiện **kết quả trong quá khứ**, không thể hiện yêu cầu hành động. `OrderPlaced` mô tả một sự thật; `SendOrderEmail` yêu cầu một bên thực hiện công việc, nên về ý nghĩa gần với **command** hơn.

Một event hữu ích cần trả lời được ba câu hỏi: **điều gì xảy ra**, **xảy ra cho đối tượng nghiệp vụ nào**, và **vì sao các module khác cần biết**. Event không cần liệt kê những hành động mà mỗi listener phải làm.

Ví dụ, record sau là hợp đồng sự kiện đơn giản:

~~~java
package com.example.shop.ordering.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

`OrderPlaced` là Java record và có thể được Spring publish trực tiếp như một application event; không bắt buộc extends `ApplicationEvent`. `eventId` nhận diện sự kiện, `orderId` nhận diện đơn hàng và `occurredAt` biểu diễn thời điểm nghiệp vụ ghi nhận sự kiện. Nếu cùng một sự kiện được xử lý lại, `eventId` cần được giữ ổn định.

Quan trọng: tên `OrderPlaced` phải có ý nghĩa thống nhất trong mô hình nghiệp vụ. Nếu “placed” nghĩa là *đã tiếp nhận yêu cầu*, event không được diễn giải thành *đã thanh toán* hay *đã giao hàng*. Đặt tên rõ giúp consumer không dựa vào những giả định ngầm.

## 3. Mục tiêu thứ nhất: giảm phụ thuộc của module phát

### 3.1. Vấn đề khi gọi trực tiếp nhiều module

Giả sử luồng đặt hàng lúc đầu chỉ có gửi email:

~~~java
public void placeOrder(PlaceOrderRequest request) {
    UUID orderId = orderService.save(request);
    notificationService.sendConfirmation(orderId);
}
~~~

Sau đó thêm thống kê và điểm thưởng:

~~~java
public void placeOrder(PlaceOrderRequest request) {
    UUID orderId = orderService.save(request);
    notificationService.sendConfirmation(orderId);
    analyticsService.recordOrder(orderId);
    loyaltyService.awardPoints(orderId);
}
~~~

Đây là **mã minh họa cho cách tổ chức chưa phù hợp**, không phải service hoàn chỉnh. Mỗi consumer mới buộc module đặt hàng biết thêm một service và thêm logic điều phối. Lỗi của một consumer cũng có thể ảnh hưởng ngay tới luồng đặt hàng nếu không phân tách rõ thời điểm giao dịch và chính sách xử lý lỗi.

### 3.2. Giải pháp bằng một sự kiện công khai

Với application events, module đặt hàng chỉ công bố sự thật:

~~~java
events.publishEvent(new OrderPlaced(
        UUID.randomUUID(),
        orderId,
        clock.instant()
));
~~~

`notification`, `analytics` và `loyalty` tự đăng ký listener cho `OrderPlaced`. Khi bổ sung consumer thứ tư, thường chỉ cần triển khai module nhận sự kiện, không phải sửa danh sách lời gọi trong service phát.

~~~mermaid
flowchart LR
    O["ordering<br/>Lưu đơn hàng"] --> P["ApplicationEventPublisher<br/>OrderPlaced"]
    P --> N["notification<br/>Gửi xác nhận"]
    P --> A["analytics<br/>Ghi nhận thống kê"]
    P --> L["loyalty<br/>Tính điểm thưởng"]
~~~

Sơ đồ thể hiện **luồng thông tin**, không khẳng định các listener chạy đồng thời hay được hoàn tất đúng một lần.

**Đích kiến trúc:** thêm hoặc thay đổi một phản ứng độc lập mà module `ordering` không cần import implementation của consumer. Lợi ích này có thể kiểm tra bằng cách xem hướng phụ thuộc giữa các module.

### 3.3. Giảm phụ thuộc không có nghĩa là không còn phụ thuộc

Consumer vẫn cần hiểu kiểu và ý nghĩa của `OrderPlaced`. Đây là **phụ thuộc vào hợp đồng** có chủ đích. Nếu publisher đổi `orderId` sang một cấu trúc không tương thích, consumer có thể bị ảnh hưởng.

Vì thế, mục tiêu không phải loại bỏ mọi phụ thuộc mà là **đưa phụ thuộc về hợp đồng công khai ổn định**, tránh truy cập class nội bộ như `OrderingService`, `OrderRepository` hoặc `OrderEntity`.

## 4. Mục tiêu thứ hai: bảo vệ ranh giới và trách nhiệm nghiệp vụ

Mỗi module nên chịu trách nhiệm cho những quyết định và dữ liệu của mình:

| Module | Sở hữu quyết định | Không nên biết |
| --- | --- | --- |
| `ordering` | Khi nào đơn hàng được chấp nhận và sự kiện `OrderPlaced` có ý nghĩa | Cách gửi email, cách tính dashboard |
| `notification` | Gửi nội dung gì và qua kênh nào | Entity/repository nội bộ của `ordering` |
| `analytics` | Cách tổng hợp chỉ số, xử lý cập nhật báo cáo | Cách `ordering` mở transaction hoặc lưu JPA |
| `loyalty` | Điều kiện tính điểm và chống cộng điểm trùng | Cách publisher gọi các listener khác |

Một hợp đồng sự kiện nên nằm ở API được module nguồn công bố. Với quy ước module mặc định của Spring Modulith, có thể để record ở root package của `ordering` hoặc công bố package con `ordering.events` qua named interface:

~~~java
// com/example/shop/ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
~~~

Module `notification` có thể giới hạn phụ thuộc vào nhóm event này:

~~~java
// com/example/shop/notification/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "ordering::events"
)
package com.example.shop.notification;
~~~

`ordering::events` diễn đạt rằng `notification` chỉ được phụ thuộc vào named interface `events` của module `ordering` theo ràng buộc được khai báo. Java compiler không tự thực thi mọi quy tắc Spring Modulith; test kiến trúc bằng `ApplicationModules.verify()` giúp phát hiện truy cập trái phép vào phần nội bộ hoặc phụ thuộc không được phép.

**Mục tiêu đạt được khi:** mỗi consumer chỉ hiểu contract được công bố, sở hữu side effect của mình và không đòi hỏi publisher cung cấp toàn bộ object graph hay repository nội bộ.

## 5. Mục tiêu thứ ba: cho phép nhiều phản ứng phát triển độc lập

Một event có thể có **không, một hoặc nhiều listener**. Module `ordering` chỉ phát `OrderPlaced`; mỗi listener quan tâm đến một mục tiêu riêng:

~~~text
OrderPlaced
  ├── notification: gửi thông tin xác nhận
  ├── analytics: cộng số đơn được chấp nhận
  ├── loyalty: ghi nhận điểm sau khi đạt điều kiện
  └── audit: bổ sung thông tin truy vết
~~~

Đặc tính này đặc biệt có ích khi:

1. Có nhiều bên cần phản ứng với cùng một sự thật.
2. Các phản ứng có tốc độ phát triển và chính sách xử lý lỗi khác nhau.
3. Publisher không cần chờ tất cả phản ứng hoàn thành để trả kết quả nghiệp vụ ban đầu.
4. Có khả năng thêm consumer trong tương lai.

Tuy nhiên, **nhiều consumer** cũng làm hệ thống khó quan sát hơn: cùng một event có thể được xử lý thành công ở `analytics` nhưng thất bại ở `notification`. Cần theo dõi kết quả theo từng listener, không đánh đồng “event đã được publish” với “toàn bộ hậu xử lý đã xong”.

Trường hợp một hành động chỉ có đúng một bên chịu trách nhiệm, phải hoàn tất trước khi trả kết quả và bên gọi cần biết thành công hay thất bại, **lời gọi facade hoặc command có phản hồi** có thể diễn đạt nhu cầu tốt hơn. Việc dùng event không phải mục tiêu tự thân.

## 6. Mục tiêu thứ tư: tách phần quyết định chính khỏi phản ứng sau commit

Một đơn hàng chỉ hợp lệ khi các điều kiện bắt buộc đã được kiểm tra và dữ liệu chính được lưu thành công. Gửi email hoặc cập nhật thống kê thường là **hành động phụ sau khi nghiệp vụ chính thành công**. Vì vậy, một mục tiêu của event là cho phép chúng có ranh giới transaction riêng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as ordering
    participant DB as Database
    participant E as Spring events
    participant N as notification
    C->>O: placeOrder()
    O->>DB: Lưu đơn trong transaction
    O->>E: publish OrderPlaced
    O->>DB: Commit transaction
    DB-->>O: Commit thành công
    O-->>C: Trả orderId
    E-->>N: Listener AFTER_COMMIT
    N->>N: Gửi thông báo
~~~

Sơ đồ minh họa một phương án **listener xử lý sau commit**. Thứ tự chính xác giữa việc trả phản hồi và thời điểm listener bất đồng bộ bắt đầu có thể khác nhau tùy cấu hình executor/runtime; phần chắc chắn là listener `AFTER_COMMIT` chỉ phản ứng sau khi transaction nguồn commit thành công.

### 6.1. Publish không có nghĩa transaction đã commit

Trong một service có `@Transactional`, lệnh `publishEvent(...)` có thể được gọi **trước commit**. Với `@EventListener` đồng bộ mặc định, listener thường được gọi ngay khi publish và có thể thực hiện side effect trước khi transaction kết thúc. Nếu sau đó transaction rollback, side effect bên ngoài đã xảy ra.

Với tác vụ chỉ được chạy sau khi đơn hàng đã commit, có thể dùng `@TransactionalEventListener`:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    // Chỉ phản ứng sau commit thành công.
}
~~~

`@TransactionalEventListener` mặc định cũng có phase `AFTER_COMMIT`; viết rõ phase giúp người đọc hiểu ý định. Nếu publish không nằm trong transaction hoạt động, listener loại này mặc định không chạy, trừ khi bật `fallbackExecution`.

### 6.2. Spring Modulith hỗ trợ listener theo ranh giới module

Spring Modulith cung cấp `@ApplicationModuleListener`, một annotation kết hợp mô hình listener sau commit, xử lý bất đồng bộ và transaction mới (`REQUIRES_NEW`), khi hạ tầng thực thi tương ứng được bật/cấu hình phù hợp:

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlaced;
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

`ConfirmationSender` là abstraction do `notification` sở hữu trong ví dụ này. Module `ordering` không biết lớp listener hoặc cách gửi xác nhận.

Khi dùng listener sau commit, **đơn hàng đã commit không bị rollback ngược** chỉ vì thao tác gửi email sau đó thất bại. Nhưng lỗi gửi email vẫn phải có chiến lược phát hiện, retry, bù trừ hoặc xử lý thủ công tùy mức độ quan trọng.

### 6.3. Không nên dời mọi thứ sang event

Nếu nghiệp vụ yêu cầu giữ hàng thành công **trước khi chấp nhận đơn hàng**, không thể mặc nhiên phát `OrderPlaced` rồi coi việc giữ hàng là một phản ứng tùy chọn sau commit. Có thể cần lời gọi đồng bộ/transaction thích hợp, một workflow có trạng thái riêng hoặc saga với bước bù trừ. Tách transaction phù hợp giúp hệ thống linh hoạt, nhưng không được làm mất các bất biến nghiệp vụ.

## 7. Ví dụ đầy đủ: từ nghiệp vụ chính đến phản ứng sự kiện

Giả sử `ordering` sở hữu nghiệp vụ tạo đơn. Bên ngoài chỉ cần một public facade; phần implementation không trực tiếp phụ thuộc consumer.

~~~java
// com/example/shop/ordering/OrderFacade.java
package com.example.shop.ordering;

import java.util.UUID;

public interface OrderFacade {
    UUID placeOrder(PlaceOrderRequest request);
}
~~~

~~~java
// com/example/shop/ordering/internal/OrderingService.java
package com.example.shop.ordering.internal;

import com.example.shop.ordering.OrderFacade;
import com.example.shop.ordering.PlaceOrderRequest;
import com.example.shop.ordering.events.OrderPlaced;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderingService implements OrderFacade {

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    OrderingService(
            OrderRepository repository,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.repository = repository;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Override
    @Transactional
    public UUID placeOrder(PlaceOrderRequest request) {
        UUID orderId = repository.createOrder(request);

        publisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                clock.instant()
        ));

        return orderId;
    }
}
~~~

`OrderRepository` và `PlaceOrderRequest` là những kiểu của ứng dụng ví dụ: repository phải triển khai lưu dữ liệu, request phải được kiểm tra theo nghiệp vụ, và bean `Clock` cần được cấu hình. Đoạn mã thể hiện **vị trí phát event** sau thao tác ghi đơn hàng. Lệnh publish vẫn diễn ra trong transaction; listener sau commit có trách nhiệm chọn đúng thời điểm phản ứng.

Thêm `analytics` mà không sửa `OrderingService`:

~~~java
package com.example.shop.analytics.internal;

import com.example.shop.ordering.events.OrderPlaced;
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
        metrics.recordAcceptedOrder(event.eventId(), event.orderId());
    }
}
~~~

`OrderMetrics` là dịch vụ thuộc module `analytics`. Một implementation tốt có thể dùng `eventId` làm idempotency key để tránh ghi trùng chỉ số khi listener được xử lý lại.

Mẫu này đạt mục tiêu nếu `ordering` không chứa import hoặc phụ thuộc bean `notification`/`analytics`, trong khi các consumer chỉ biết hợp đồng `OrderPlaced` đã được công bố.

## 8. Mục tiêu thứ năm: làm rõ sự kiện để hệ thống dễ mở rộng và tích hợp

Khi nhiều module dùng chung một event, hợp đồng event trở thành **ngôn ngữ chung có chủ đích**. Ví dụ, `PaymentCaptured` nói lên sự kiện đã thu tiền, không yêu cầu listener phải biết cổng thanh toán nào, transaction SQL nào hoặc cách provider ghi nhận trạng thái ra sao.

Trong cùng modular monolith, có thể truyền Java object qua `ApplicationEventPublisher`. Nếu cần thông báo tới một dịch vụ bên ngoài, có thể **ánh xạ** event nội bộ sang integration event hoặc message:

~~~mermaid
flowchart LR
    A["payment<br/>PaymentCaptured"] --> B["Application event<br/>Spring context"]
    B --> C["Externalization / adapter"]
    C --> D[("Message broker")]
    D --> E["Dịch vụ kế toán"]
~~~

Đây là **một lộ trình mở rộng**, không phải hành vi mặc định. `publishEvent(...)` không tự tạo Kafka topic, tự serialize JSON hay bảo đảm message đã đến broker. Externalization cần chọn/cấu hình hạ tầng, định tuyến, hợp đồng payload và chiến lược xử lý lỗi riêng.

Ví dụ một message tích hợp có thể có envelope:

~~~json
{
  "eventId": "69e343b4-9373-40c7-a4f6-1ea4af7dff96",
  "eventType": "order.placed.v1",
  "occurredAt": "2026-11-25T08:15:00Z",
  "payload": {
    "orderId": "38841130-a2ec-42a2-89d5-c4fe72c5f165"
  }
}
~~~

Envelope JSON trên là **thiết kế minh họa**, không phải cấu trúc tự động do Spring Modulith áp đặt. Điểm quan trọng là **event diễn đạt sự thật nghiệp vụ**; message là **đơn vị thông tin được gửi qua một kênh** và có thể cần metadata hoặc version độc lập.

## 9. Mục tiêu kiến trúc khác với bảo đảm giao sự kiện

Một hiểu nhầm phổ biến là: “Dùng event thì hệ thống tự bất đồng bộ, bền vững, retry được và chắc chắn xử lý đúng một lần.” Thực tế, **event là một mô hình giao tiếp**; những thuộc tính runtime cần được thiết kế và cấu hình.

| Mong muốn | Event hỗ trợ điều gì? | Còn phải làm gì? |
| --- | --- | --- |
| Giảm phụ thuộc | Publisher phát một hợp đồng thay vì gọi từng consumer | Giữ API nhỏ và kiểm tra phụ thuộc module |
| Không gửi email cho đơn hàng rollback | Cho phép listener phản ứng theo transaction phase | Chọn listener `AFTER_COMMIT` và có transaction nguồn phù hợp |
| Publisher không phải chờ email hoàn tất | Listener có thể xử lý bất đồng bộ | Cấu hình async/executor, đo tải và kiểm soát lỗi |
| Không bỏ sót phản ứng khi listener lỗi | Có cơ chế ghi nhận publication trong Spring Modulith | Cấu hình registry/persistence, recovery/resubmission |
| Không cộng điểm trùng | Event có định danh ổn định | Thiết kế idempotency và ràng buộc dữ liệu ở consumer |
| Gửi thông điệp ra hệ thống khác | Có thể dùng event làm nguồn cho integration | Externalization/broker, serialization, retry, schema version |
| Theo dõi sự kiện chậm hoặc lỗi | Event tạo mốc nghiệp vụ quan sát được | Trace, log, metrics và cảnh báo theo listener |

### 9.1. Event Publication Registry dùng để làm gì?

Spring Modulith cung cấp **Event Publication Registry** để theo dõi các publication của listener phù hợp khi có cấu hình persistence cần thiết. Registry có thể ghi nhận publication đang chờ, hoàn tất hoặc còn dang dở, hỗ trợ chiến lược tìm và xử lý lại các publication chưa hoàn thành.

Mục tiêu nghiệp vụ ở đây là **không để một lỗi tạm thời của listener trở thành công việc bị bỏ quên**. Nhưng registry không tự biến mọi side effect thành “exactly once”: nếu listener đã gửi email thành công rồi tiến trình dừng trước khi ghi nhận completion, xử lý lại có thể gửi email lần nữa.

Vì vậy, cần tách ba câu hỏi:

1. **Publication được ghi nhận bền vững chưa?** Phụ thuộc cấu hình registry và transaction/persistence.
2. **Listener có thể được chạy lại chưa?** Phụ thuộc cơ chế recovery, retry và cấu hình vận hành.
3. **Chạy lại có an toàn chưa?** Phụ thuộc idempotency của nghiệp vụ và dịch vụ bên ngoài.

### 9.2. Không đánh đồng async với lưu bền

`@Async` giúp chuyển công việc sang executor khi được bật và cấu hình đúng. Nó không tự bảo đảm executor queue được lưu trên đĩa, không bảo đảm retry sau crash và không thay thế message broker. Một thiết kế “đáng tin cậy” phải có bằng chứng cho từng ranh giới có thể thất bại.

## 10. Thiết kế event theo đúng mục tiêu

### 10.1. Tên phản ánh sự kiện đã xảy ra

| Nên dùng | Cần xem lại | Lý do |
| --- | --- | --- |
| `OrderPlaced` | `SendConfirmationEmail` | Tên đầu diễn đạt sự thật; tên sau ra lệnh thực hiện công việc |
| `PaymentCaptured` | `UpdatePaymentTable` | Tên đầu là kết quả nghiệp vụ; tên sau rò rỉ chi tiết persistence |
| `InventoryReserved` | `NotifyOrderingAndShipping` | Tên đầu không buộc sự kiện phải có các consumer cụ thể |

Không phải tên mang ý nghĩa command đều sai; command hợp lệ nếu thật sự cần một bên thực hiện hành động. Điều cần tránh là gọi một command là “event” rồi hy vọng giảm phụ thuộc.

### 10.2. Payload đủ để phản ứng mà không lộ implementation

Một event nên ưu tiên value object, enum, ID và snapshot cần thiết; tránh gửi nguyên JPA entity hoặc kiểu hạ tầng:

~~~java
// Nên tránh:
public record OrderPlaced(OrderEntity entity) {}

// Ưu tiên hợp đồng nghiệp vụ rõ:
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Tuy nhiên, **chỉ gửi ID không phải nguyên tắc tuyệt đối**. Nếu consumer cần trạng thái tại *thời điểm* sự kiện xảy ra và query sau đó có thể trả về giá trị mới, có thể cần thêm snapshot phù hợp vào payload. Chọn dữ liệu theo nhu cầu nghiệp vụ, bảo mật và mức chấp nhận coupling.

### 10.3. Thời điểm có ý nghĩa

`occurredAt` là thời điểm sự thật được ghi nhận, không đồng nghĩa với `processedAt` của mỗi listener hoặc thời điểm message đến broker. Những thời điểm này khác nhau khi có transaction, async và retry. Dùng timestamp nhất quán, ví dụ `Instant`, và phân biệt event time với processing time khi thiết kế metrics.

### 10.4. Versioning và tương thích

Một record Java có thể được nhiều module trong cùng bản build sử dụng. Khi đổi field hoặc semantics, các consumer phải được cập nhật. Nếu event được externalize cho hệ thống triển khai độc lập, nên quản lý schema/version và lộ trình chuyển đổi chặt chẽ hơn. Một thay đổi phá vỡ hợp đồng cũ có thể làm consumer cũ đọc sai message dù publisher đã chạy thành công.

### 10.5. Idempotency từ đầu

Nếu cùng `OrderPlaced(eventId=E1, orderId=O1)` bị retry, consumer cần biết đây vẫn là **sự kiện E1**. Với tác vụ cập nhật số liệu, có thể dùng bảng `processed_events` và unique constraint cho `(consumer_name, event_id)` cùng transaction cập nhật dữ liệu. Với API bên ngoài như email, cần xem API có hỗ trợ idempotency key hoặc có phương án hạn chế trùng phù hợp không.

## 11. Khi nào dùng event, khi nào không?

Lựa chọn giao tiếp nên xuất phát từ **kết quả mà nghiệp vụ cần ngay lúc đó**.

| Yêu cầu | Phương án thường phù hợp | Lý do |
| --- | --- | --- |
| Tính tổng tiền và kiểm tra hạn mức trước khi xác nhận đơn | Service/query hoặc facade đồng bộ | Quyết định hiện tại cần kết quả ngay |
| Sau khi đơn đã commit, gửi email xác nhận | Event + listener sau commit | Là phản ứng với sự thật đã xảy ra |
| Sau khi đơn đã commit, cập nhật dashboard | Event + listener | Nhiều consumer, có thể xử lý trễ |
| Yêu cầu dịch vụ kho phải giữ hàng trước khi xác nhận đơn | Command/giao tiếp đồng bộ hoặc workflow có trạng thái | Cần biết kết quả để giữ bất biến |
| Hệ thống kế toán chạy bên ngoài cần biết đã thu tiền | Integration event qua adapter/broker hoặc API tích hợp | Có ranh giới tiến trình và hợp đồng truyền tải |
| Thực hiện một chuỗi bước bắt buộc với bù trừ khi lỗi | Orchestration/saga theo yêu cầu nghiệp vụ | Event có thể tham gia nhưng không tự thay thế việc điều phối |

### Bộ câu hỏi ra quyết định

Trước khi tạo một event mới, hãy trả lời:

1. **Sự thật nào đã xảy ra?** Có thể đặt tên event ở dạng quá khứ và được nghiệp vụ đồng thuận không?
2. **Ai sở hữu sự thật đó?** Publisher có phải module chịu trách nhiệm quyết định trạng thái không?
3. **Consumer có cần trả kết quả tức thì không?** Nếu có, cơ chế fire-and-forget có thể không phù hợp.
4. **Điều kiện nào phải đúng khi event có hiệu lực?** Phân biệt đã publish trong transaction với đã commit.
5. **Nếu consumer thất bại thì sao?** Đơn hàng có được giữ nguyên không? Có cần retry/bù trừ?
6. **Có thể xử lý lại không?** Event và consumer có định danh/cơ chế idempotency không?

Nếu chưa trả lời được các câu hỏi trên, chưa nên coi thêm `ApplicationEventPublisher` là cách cải thiện kiến trúc.

## 12. Chứng minh event thực sự đạt mục tiêu

Mục tiêu kiến trúc cần được diễn đạt bằng **điều kiện kiểm chứng được**. Một kế hoạch kiểm thử có thể kết hợp:

| Mục tiêu | Cách kiểm chứng |
| --- | --- |
| Publisher không phụ thuộc listener | Kiểm tra package/import và chạy `ApplicationModules.verify()` |
| Event là hợp đồng API được phép | Kiểm tra named interface, `allowedDependencies` và test kiến trúc |
| Phát event đúng khi đơn thành công | `@ApplicationModuleTest` cùng `PublishedEvents` kiểm tra kiểu và payload |
| Không phản ứng với đơn rollback | Test tạo transaction thật rồi rollback; xác nhận side effect listener `AFTER_COMMIT` không xảy ra |
| Một listener thất bại không làm rollback đơn đã commit | Test failure sau commit với các transaction rõ ràng |
| Có thể phát lại an toàn | Test gửi lại cùng `eventId` và xác nhận không nhân đôi kết quả nghiệp vụ |
| Có thể theo dõi publication lỗi/chậm | Test và giám sát trạng thái registry, log/tracing/metrics theo cấu hình |

Ví dụ kiến trúc:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTest {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Ví dụ phát hiện event bằng Spring Modulith test support (giả sử test đã có fixture hợp lệ):

~~~java
package com.example.shop.ordering;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.ordering.events.OrderPlaced;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderEventTest {

    @Autowired
    OrderFacade orders;

    @Test
    void publishesOrderPlaced(PublishedEvents events) {
        PlaceOrderRequest request = validOrderRequest();
        UUID orderId = orders.placeOrder(request);

        assertThat(events.ofType(OrderPlaced.class))
                .extracting(OrderPlaced::orderId)
                .contains(orderId);
    }

    private PlaceOrderRequest validOrderRequest() {
        // Cần thay bằng fixture hợp lệ của ứng dụng cụ thể.
        throw new UnsupportedOperationException("Create project fixture");
    }
}
~~~

Đoạn test thứ hai minh họa **cách dùng API kiểm thử**; `validOrderRequest()` cố ý chừa điểm triển khai theo model thực, nên chưa phải test chạy được độc lập. `PublishedEvents` xác nhận event đã được phát trong ngữ cảnh test, **không chứng minh** đã commit, mọi listener hoàn thành hay delivery “exactly once”.

Khi kiểm thử `AFTER_COMMIT`, chú ý rằng test tự bọc bằng `@Transactional` và rollback cuối test có thể không kích hoạt listener sau commit. Hãy thiết lập transaction boundary với commit rõ ràng, ví dụ thông qua service được Spring quản lý hoặc `TransactionTemplate`. Với listener async, sử dụng cơ chế chờ kết quả hoặc assertion phù hợp thay vì mặc định cho rằng side effect xảy ra ngay sau khi method trả về.

## 13. Những ngộ nhận khiến mục tiêu event bị lệch

| Ngộ nhận | Cách hiểu cần có |
| --- | --- |
| “Tạo event là hệ thống đã loose coupling hoàn toàn.” | Consumer vẫn phụ thuộc vào hợp đồng; phải giữ API và ownership đúng ranh giới. |
| “Có event thì gọi service trực tiếp là kiến trúc xấu.” | Lời gọi trực tiếp phù hợp khi cần kết quả tức thì và ràng buộc rõ. |
| “`publishEvent` thành công nghĩa là đơn hàng đã commit.” | Publish có thể xảy ra trước commit hoặc bị rollback sau đó. |
| “Event là message trên Kafka.” | Application event có thể được xử lý hoàn toàn nội bộ JVM; externalization là bước riêng. |
| “`@Async` đảm bảo event không mất.” | Async không mặc nhiên cung cấp persistence/retry. |
| “Có Event Publication Registry là đã có exactly-once.” | Registry giúp theo dõi publication; side effect lặp vẫn cần idempotency. |
| “Event càng chứa nhiều entity càng tiện cho consumer.” | Truyền entity có thể lộ implementation, làm tăng coupling và gây lỗi lazy loading. |
| “Listener lỗi thì nên rollback đơn hàng đã commit.” | Transaction sau commit đã hoàn thành; cần policy retry, bù trừ hoặc xử lý lỗi phù hợp. |
| “Chỉ cần test publisher là đủ.” | Cần thêm kiểm tra transaction, listener, reliability và ranh giới module. |

## 14. Bài thực hành: xác định mục tiêu trước khi viết code

**Bối cảnh:** Ứng dụng bán hàng có module `ordering`, `notification`, `analytics` và `loyalty`. Sau khi đơn được chấp nhận, ba module sau có thể cần thực hiện công việc của mình; tuy nhiên email có thể lỗi tạm thời, analytics có thể xử lý chậm và điểm thưởng không được cộng trùng.

### Bài 1 — Đề xuất các mục tiêu kiến trúc

Viết ra ít nhất bốn mục tiêu có thể kiểm chứng:

1. `ordering` không import implementation của `notification`/`analytics`/`loyalty`.
2. Một event `OrderPlaced` diễn đạt đúng thời điểm nghiệp vụ “đơn hàng đã được chấp nhận”.
3. Các phản ứng chỉ chạy sau commit thành công khi nghiệp vụ yêu cầu.
4. Retry cùng `eventId` không tạo side effect trùng ở consumer.

Giải thích vì sao **“dùng nhiều event nhất có thể”** không phải mục tiêu tốt.

### Bài 2 — Tách lời gọi trực tiếp và sự kiện

Phân loại các bước sau thành **cần kết quả đồng bộ**, **phản ứng sự kiện** hoặc **workflow có điều phối**:

- Kiểm tra sản phẩm còn được bán trước khi xác nhận đơn.
- Tính tổng tiền trong transaction tạo đơn.
- Gửi email khi đơn hàng đã commit.
- Ghi nhận doanh số theo ngày.
- Bảo đảm giữ hàng thành công trước khi cam kết giao hàng.
- Đồng bộ thông tin thanh toán sang hệ thống kế toán độc lập.

Biện minh lựa chọn theo yêu cầu về bất biến, transaction, độ trễ, retry và độ tin cậy.

### Bài 3 — Viết hợp đồng và consumer

Tạo `OrderPlaced(UUID eventId, UUID orderId, Instant occurredAt)` trong package `ordering.events` và công bố named interface `events`. Publish event trong service tạo đơn; viết một listener `notification` chỉ phụ thuộc vào event contract.

Kiểm tra:

- Thêm `analytics` listener có làm thay đổi mã nguồn `OrderingService` không?
- Có import `ordering.internal` trong consumer không?
- `ApplicationModules.verify()` có đạt không?
- Listener có gửi thông báo khi transaction tạo đơn rollback không?

### Bài 4 — Mô phỏng lỗi và phát lại

Sau khi đơn hàng commit, giả lập listener email ném exception. Ghi nhận publication lỗi theo cấu hình hệ thống; thực hiện lại cùng event; kiểm tra chính sách chống gửi trùng. Nếu tích hợp email không hỗ trợ idempotency key, hãy mô tả giới hạn về khả năng tránh gửi lặp trong trường hợp crash ở thời điểm khó kiểm soát.

### Bài 5 — Xác định dữ liệu quan sát

Lập bảng cho mỗi event với `eventId`, `orderId`, loại event, thời điểm phát, tên listener, trạng thái hoàn tất, số lần thử và thời gian xử lý. Chỉ ra metric nào giúp phát hiện backlog sự kiện và metric nào giúp biết riêng consumer `notification` đang thất bại.

## 15. Tự đánh giá

**Câu 1. Mục tiêu quan trọng nhất khi module `ordering` phát `OrderPlaced` là gì?**

Để thông báo một sự thật nghiệp vụ cho các module quan tâm, giảm việc `ordering` phải biết hoặc gọi trực tiếp từng implementation consumer.

**Câu 2. Nếu chỉ có một thao tác cần kết quả ngay trước khi tạo đơn, có bắt buộc dùng event không?**

Không. Một facade hoặc command đồng bộ với hợp đồng rõ ràng có thể phù hợp hơn. Event được chọn theo nhu cầu nghiệp vụ, không phải vì muốn dùng một kỹ thuật cụ thể.

**Câu 3. Vì sao `OrderPlaced` nên được công bố trong API module?**

Vì consumer cần một hợp đồng ổn định để biết sự kiện gì đã xảy ra. Chúng không nên import service, repository hoặc entity nội bộ của publisher.

**Câu 4. `@ApplicationModuleListener` có làm việc gửi email chắc chắn thành công không?**

Không. Annotation hỗ trợ mô hình xử lý sau commit và bất đồng bộ/transaction riêng khi cấu hình phù hợp; lỗi mạng, crash, retry và xử lý lặp vẫn cần được thiết kế.

**Câu 5. Một event được publish và nhận lại hai lần có luôn là lỗi không?**

Không nhất thiết. Việc retry và một số mô hình giao nhận có thể khiến cùng event được xử lý lại. Nghiệp vụ cần xác định và kiểm soát idempotency; không được mặc định mọi side effect đều “exactly once”.

## 16. Kết luận

Mục tiêu của event trong Spring Modulith là **diễn đạt một sự thật nghiệp vụ thông qua hợp đồng công khai để các module khác phản ứng theo trách nhiệm của mình**. Cách giao tiếp này làm giảm phụ thuộc của publisher, giữ ranh giới module rõ ràng và cho phép nhiều hành vi bổ sung được phát triển độc lập. Khi listener được thiết kế sau commit, event còn giúp tách những phản ứng phụ khỏi transaction quyết định nghiệp vụ chính.

Giảm phụ thuộc không đồng nghĩa với việc mọi sự kiện đã được giao đáng tin cậy. Một hệ thống thực tế phải kết hợp **hợp đồng event rõ nghĩa**, **điều kiện transaction chính xác**, **Event Publication Registry và cơ chế khôi phục khi cần**, **retry an toàn nhờ idempotency**, cùng **kiểm thử và quan sát đầy đủ**. Hãy bắt đầu từ mục tiêu nghiệp vụ và kiểm chứng được lợi ích đó, rồi mới quyết định cách publish và xử lý sự kiện.
