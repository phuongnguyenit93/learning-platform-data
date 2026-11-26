# Listener theo package trong Spring Modulith

Trong Spring Boot, một phương thức có `@EventListener` hoặc `@ApplicationModuleListener` có thể nhận application event mà không cần module phát gọi trực tiếp phương thức đó. Nhưng **đặt class listener ở package nào** lại ảnh hưởng tới kiến trúc: ai sở hữu hành vi, module nào được phép phụ thuộc vào module nào, class nào thuộc API công khai, và Spring có phát hiện bean listener lúc khởi động hay không.

Ví dụ, module `ordering` phát `OrderPlaced`. Module `notification` cần gửi email và module `analytics` cần cập nhật báo cáo. Đưa tất cả listener vào package `ordering` chỉ vì chúng nhận `OrderPlaced` sẽ làm mờ ranh giới trách nhiệm. Cách tổ chức phù hợp là **đặt listener ở module tiêu thụ, trong package triển khai của chính module đó**, rồi cho nó chỉ phụ thuộc vào hợp đồng sự kiện được `ordering` công bố.

Bài **“Listener theo package”** thuộc chương **Listener và subscriber** của `SPRING_MODULITH_APPLICATION_EVENTS`. Trọng tâm là bố trí, phát hiện và kiểm tra listener trong modular monolith, kết hợp nguyên tắc giảm phụ thuộc, listener sau commit, event publication registry, retry và khả năng quan sát quá trình xử lý.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **Java package**, **application module**, **API công khai của module** và **package nội bộ**.
- Giải thích vì sao package chứa listener nên phản ánh **module sở hữu phản ứng**, không chỉ tên event mà nó nhận.
- Bố trí publisher, event contract và listener ở các package khác nhau nhưng tuân thủ ranh giới Spring Modulith.
- Hiểu vai trò của `@Component`, component scanning và annotation listener trong việc Spring đăng ký handler.
- Viết listener theo `@EventListener`, `@TransactionalEventListener` hoặc `@ApplicationModuleListener` đúng ngữ nghĩa transaction.
- Giới hạn phụ thuộc bằng `@NamedInterface` và `@ApplicationModule(allowedDependencies = ...)`.
- Kiểm tra cấu trúc bằng `ApplicationModules.verify()` và kiểm thử các tình huống publish, commit, rollback, lỗi và xử lý lặp.

## 2. “Theo package” nghĩa là tổ chức listener theo quyền sở hữu

Một Java package tập hợp các kiểu có liên quan. Trong Spring Modulith, với cách phát hiện module theo quy ước mặc định, các package con trực tiếp dưới package ứng dụng là **application modules**.

Giả sử class khởi động nằm ở `com.example.shop.ShopApplication`. Các package `com.example.shop.ordering`, `com.example.shop.notification` và `com.example.shop.analytics` tương ứng với ba application module. Các package con như `notification.internal` vẫn thuộc `notification`.

**Quy tắc cốt lõi:**

> Listener xử lý trách nhiệm nghiệp vụ của module nào thì được đặt trong package của module đó. Module nhận chỉ cần biết contract event mà module nguồn đã công bố.

Điều này dẫn đến ba vị trí khác nhau:

| Thành phần | Package ví dụ | Lý do |
| --- | --- | --- |
| Hợp đồng event `OrderPlaced` | `ordering.events`, được công bố thành named interface | Module `ordering` sở hữu sự thật “đơn hàng đã được đặt” |
| Publisher `OrderingService` | `ordering.internal` | Module `ordering` quyết định khi nào sự thật được phát |
| Listener gửi thông báo | `notification.internal.listener` | `notification` sở hữu việc gửi email và trạng thái thông báo |
| Listener cập nhật chỉ số | `analytics.internal.listener` | `analytics` sở hữu thuật toán tính chỉ số và dữ liệu thống kê |

Đặt tên package `listener` hoặc `subscribers` chỉ để phân loại code là lựa chọn tổ chức; **tên package không tự đăng ký một phương thức nhận event**. Việc nhận sự kiện vẫn cần bean được Spring quản lý và listener annotation hoặc cơ chế đăng ký tương đương.

## 3. Cấu trúc package mẫu

~~~text
com.example.shop
├── ShopApplication.java
├── ordering/                              # Module sở hữu nghiệp vụ đặt hàng
│   ├── OrderFacade.java                   # API công khai mặc định
│   ├── events/
│   │   ├── package-info.java              # @NamedInterface("events")
│   │   └── OrderPlaced.java               # Event contract
│   └── internal/
│       ├── OrderingService.java           # Publisher
│       ├── OrderRepository.java
│       └── OrderEntity.java
├── notification/                          # Module sở hữu thông báo
│   ├── package-info.java                  # allowedDependencies
│   └── internal/
│       ├── listener/
│       │   └── OrderNotificationListener.java
│       ├── ConfirmationSender.java
│       └── NotificationRepository.java
└── analytics/                             # Module sở hữu thống kê
    └── internal/
        ├── listener/
        │   └── OrderAnalyticsListener.java
        └── SalesMetrics.java
~~~

Ở cách bố trí này, mỗi listener nằm trong module xử lý phản ứng. Nếu sau này thay email bằng push notification, sửa đổi chủ yếu nằm trong `notification`; nếu thay công thức báo cáo, sửa trong `analytics`. `ordering` không phải import bất cứ implementation nào của hai module kia.

~~~mermaid
flowchart LR
    subgraph O["ordering"]
        P["internal/OrderingService"]
        E["events/OrderPlaced<br/>Hợp đồng công khai"]
        P -->|"publish"| E
    end
    subgraph N["notification"]
        NL["internal/listener/<br/>OrderNotificationListener"]
        NS["internal/<br/>ConfirmationSender"]
        NL --> NS
    end
    subgraph A["analytics"]
        AL["internal/listener/<br/>OrderAnalyticsListener"]
        AM["internal/<br/>SalesMetrics"]
        AL --> AM
    end
    NL -->|"import event contract"| E
    AL -->|"import event contract"| E
~~~

Sơ đồ thể hiện cả **phụ thuộc mã nguồn** và vị trí xử lý: `notification` và `analytics` import `OrderPlaced`; `ordering` không import listener. Tại runtime, Spring event infrastructure chuyển sự kiện từ publisher đến các listener tương ứng. Luồng publish không hàm ý consumer đã xử lý thành công.

## 4. API công khai và package nội bộ quyết định phụ thuộc nào hợp lệ

Trong mô hình application module mặc định của Spring Modulith:

- Các kiểu phù hợp nằm trực tiếp trong **root package của module** thuộc bề mặt API mặc định.
- Các **subpackage** là chi tiết nội bộ trừ khi được công bố có chủ đích, chẳng hạn qua `@NamedInterface`.
- Kiểu Java `public` trong subpackage nội bộ không đương nhiên trở thành API được phép cho module khác import.

Vì event được dùng ở module khác, cần đặt contract trong API được công bố. Có hai cách thường gặp:

1. Đặt `OrderPlaced` ngay trong `com.example.shop.ordering`.
2. Đặt `OrderPlaced` trong `com.example.shop.ordering.events` và công bố package đó thành named interface.

Ví dụ cách thứ hai:

~~~java
// com/example/shop/ordering/events/OrderPlaced.java
package com.example.shop.ordering.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

~~~java
// com/example/shop/ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
~~~

`OrderPlaced` là một Java record thông thường; Spring có thể publish nó làm application event mà không yêu cầu kế thừa `ApplicationEvent`. Ba trường nhận diện sự kiện, đơn hàng và thời điểm xảy ra sự kiện theo nghiệp vụ. Trong thực tế nên xác nhận dữ liệu bắt buộc không null và định nghĩa rõ khi nào `OrderPlaced` được phát.

Module `notification` chỉ cần contract này có thể khai báo:

~~~java
// com/example/shop/notification/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "ordering::events"
)
package com.example.shop.notification;
~~~

Chuỗi `ordering::events` mô tả named interface mà `notification` được phép phụ thuộc. Vì vậy, import `com.example.shop.ordering.events.OrderPlaced` là một phụ thuộc có chủ đích, còn import `com.example.shop.ordering.internal.OrderRepository` là vi phạm ranh giới theo quy tắc mặc định.

`@NamedInterface` và `allowedDependencies` tạo ra **quy tắc kiến trúc**, không tạo sandbox bảo mật ở JVM. Java compiler có thể vẫn cho phép import class `public` từ package nội bộ; kiểm tra kiến trúc sẽ phát hiện vi phạm khi được chạy.

## 5. Publisher ở package nguồn, listener ở package đích

### 5.1. Module đặt hàng công bố sự kiện

~~~java
// com/example/shop/ordering/internal/OrderingService.java
package com.example.shop.ordering.internal;

import com.example.shop.ordering.events.OrderPlaced;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderingService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderingService(
            OrderRepository repository,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.repository = repository;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(OrderDraft draft) {
        // Repository và draft là kiểu nghiệp vụ giả định của ordering.
        UUID id = repository.create(draft);

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                id,
                clock.instant()
        ));
        return id;
    }
}
~~~

Đoạn mã minh họa vị trí phát sự kiện. `OrderRepository`, `OrderDraft` và bean `Clock` phải được định nghĩa trong dự án thực. Event được tạo sau thao tác lưu đơn nhưng **bên trong transaction hiện tại**; nó chưa chứng minh transaction đã commit.

### 5.2. Module thông báo nhận event tại package của nó

~~~java
// com/example/shop/notification/internal/listener/OrderNotificationListener.java
package com.example.shop.notification.internal.listener;

import com.example.shop.notification.internal.ConfirmationSender;
import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    private final ConfirmationSender confirmations;

    OrderNotificationListener(ConfirmationSender confirmations) {
        this.confirmations = confirmations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        confirmations.sendConfirmation(
                event.eventId(),
                event.orderId()
        );
    }
}
~~~

`ConfirmationSender` là interface/service của module `notification`; method `sendConfirmation(eventId, orderId)` do ứng dụng định nghĩa, **không phải method có sẵn của Spring Modulith**. Trong cấu trúc ví dụ, kiểu `ConfirmationSender` cần được khai báo `public` nếu listener ở subpackage `internal.listener` import nó từ `internal`. Việc `public` bên trong cùng một module không đồng nghĩa nó phải được công bố làm API cho module khác.

Đặt `OrderNotificationListener` là class **package-private** giúp hạn chế khả năng code Java ngoài package phụ thuộc trực tiếp vào class listener. Spring vẫn có thể phát hiện bean được gắn `@Component` nếu package nằm trong phạm vi component scanning, dù cần bảo đảm yêu cầu reflection/proxy của môi trường triển khai. Nếu muốn đơn giản hóa quyền truy cập nội bộ, có thể đặt listener và `ConfirmationSender` trong cùng package `notification.internal`.

### 5.3. Module thống kê đăng ký subscriber độc lập

~~~java
// com/example/shop/analytics/internal/listener/OrderAnalyticsListener.java
package com.example.shop.analytics.internal.listener;

import com.example.shop.analytics.internal.SalesMetrics;
import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderAnalyticsListener {

    private final SalesMetrics metrics;

    OrderAnalyticsListener(SalesMetrics metrics) {
        this.metrics = metrics;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        metrics.recordAcceptedOrder(event.eventId(), event.orderId());
    }
}
~~~

`SalesMetrics` là service thuộc `analytics`, cần có mức truy cập Java phù hợp với package chứa listener. Thêm listener này không đòi hỏi `OrderingService` biết nó tồn tại. Mỗi module sở hữu logic và trạng thái xử lý sự kiện riêng.

## 6. Điều kiện để Spring thực sự đăng ký listener

**Đặt file đúng package không đủ để Spring gọi listener.** Cần phân biệt ba điều:

1. **Class nằm trên classpath và trong phạm vi component scanning:** Spring phát hiện bean ứng với `@Component` hoặc một cách khai báo bean tương đương.
2. **Method được nhận diện là listener:** đặt `@EventListener`, `@TransactionalEventListener` hoặc `@ApplicationModuleListener` đúng vào handler.
3. **Event được publish đúng kiểu và đúng điều kiện:** listener nhận event theo kiểu tham số và quy tắc của annotation; listener transaction còn phụ thuộc trạng thái transaction.

Ví dụ class khởi động:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Với `ShopApplication` ở `com.example.shop`, component scanning mặc định bao phủ các package con như `ordering.internal`, `notification.internal.listener` và `analytics.internal.listener`. Do vậy một `@Component` listener ở những package này có thể được đăng ký trong ApplicationContext.

### Khi listener không được phát hiện

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy bean listener trong context | Package nằm ngoài phạm vi scan, thiếu `@Component`, cấu hình profile/conditional loại trừ bean | Kiểm tra base package, cấu hình bean, profile |
| Bean có nhưng method không chạy | Thiếu listener annotation hoặc event type không phù hợp | Kiểm tra chữ ký handler và event được publish |
| `@TransactionalEventListener` không chạy | Publish không có transaction, hoặc transaction rollback | Kiểm tra transaction boundary và phase |
| Listener chạy đồng bộ dù mong muốn async | Hạ tầng `@Async` chưa được kích hoạt/cấu hình như dự kiến | Kiểm tra `@EnableAsync`, executor và annotation đang dùng |
| Listener chạy nhưng không ghi được dữ liệu | Transaction sau commit không có transaction ghi mới phù hợp, hoặc quyền dữ liệu sai | Xác định transaction của listener, ví dụ `REQUIRES_NEW` |

Đừng sửa lỗi “không nhận event” bằng cách chuyển listener sang package của publisher một cách tùy tiện. Trước tiên hãy xác minh scanning, registration, event type, transaction và cấu hình runtime.

## 7. Package và annotation là hai trục độc lập

**Package** trả lời câu hỏi: *Ai sở hữu mã nguồn và các phụ thuộc của listener?* **Annotation** trả lời câu hỏi: *Listener được kích hoạt theo cơ chế nào?*

| Annotation | Thời điểm điển hình | Đặc điểm cần hiểu |
| --- | --- | --- |
| `@EventListener` | Theo mặc định chạy đồng bộ khi `publishEvent(...)` được gọi | Có thể chạy trước commit; exception của listener đồng bộ thường lan về publisher |
| `@TransactionalEventListener` | Mặc định ở pha `AFTER_COMMIT` khi event phát trong transaction | Không tự tạo transaction mới để ghi dữ liệu; nếu không có transaction thì mặc định bỏ qua |
| `@ApplicationModuleListener` | Kết hợp listener sau commit, `@Async` và transaction mới theo semantics Spring Modulith | Phù hợp phản ứng độc lập giữa module; cần quản lý hạ tầng async, registry và lỗi |

Ba lựa chọn này đều có thể được đặt trong `notification.internal.listener`. Không có quy định rằng `@EventListener` phải ở root package hay `@ApplicationModuleListener` phải ở package `events`. Cách đặt package phục vụ ownership và giới hạn phụ thuộc, không thay thế ngữ nghĩa listener.

### 7.1. Dùng `@EventListener` khi cần phản ứng trong luồng publish

~~~java
@EventListener
void on(OrderPlaced event) {
    // Có thể chạy đồng bộ ngay khi publisher phát event.
}
~~~

Đây có thể là lựa chọn chủ đích cho một số phản ứng trong tiến trình. Nhưng nếu handler gửi email ngay, event được publish trong transaction và transaction sau đó rollback, hệ thống có thể gửi xác nhận cho đơn không được lưu.

### 7.2. Dùng `@TransactionalEventListener` để phản ứng sau commit

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderPlaced event) {
    // Chỉ xử lý khi transaction phát event commit thành công.
}
~~~

`@TransactionalEventListener` mặc định cần có transaction đang hoạt động tại thời điểm publish. Khi không có transaction, listener không chạy trừ khi sử dụng `fallbackExecution = true`. Vì callback `AFTER_COMMIT` chạy sau khi transaction nguồn đã hoàn thành, việc ghi thêm dữ liệu cần transaction mới thích hợp.

### 7.3. Dùng `@ApplicationModuleListener` cho phản ứng module độc lập

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    // Xử lý sau commit trong ngữ cảnh listener phù hợp.
}
~~~

Spring Modulith cung cấp annotation này để kết hợp cơ chế listener giao dịch ở pha sau commit, thực thi bất đồng bộ và transaction độc lập (`REQUIRES_NEW`). **Cần kiểm tra phiên bản và cấu hình thực tế của ứng dụng**, bao gồm việc kích hoạt xử lý async và executor thích hợp. Không suy ra rằng annotation tự đảm bảo lưu bền sự kiện, retry vô hạn hoặc xử lý đúng một lần.

## 8. Một package có thể chứa nhiều listener, một event có thể có nhiều subscriber

Không cần tạo một package riêng cho mỗi event. Các cách tổ chức đều có thể hợp lệ nếu ownership rõ:

~~~text
notification/internal/listener/
    OrderPlacedListener.java
    PaymentCapturedListener.java
    ShipmentDeliveredListener.java
~~~

Hoặc gom các handler liên quan theo một use case:

~~~text
notification/internal/orderconfirmation/
    OrderConfirmationListener.java
    ConfirmationSender.java
    ConfirmationRepository.java
~~~

Tiêu chí chọn package nên là **khả năng hiểu và thay đổi cùng nhau**. Khi cùng nghiệp vụ xác nhận đơn có cả listener và service xử lý, đặt cùng package giảm độ phức tạp truy cập Java. Khi số lượng subscriber tăng, chia theo nhóm use case có thể rõ ràng hơn chia theo công nghệ vận chuyển.

### Tránh chia package theo nơi phát khi làm mất ownership

Đặt các class sau trong `ordering.listeners` là thiết kế cần xem lại:

~~~text
ordering/listeners/
    SendEmailListener.java
    UpdateAnalyticsListener.java
    AwardLoyaltyPointsListener.java
~~~

Nếu ba handler thực hiện nghiệp vụ và phụ thuộc vào dữ liệu của `notification`, `analytics` và `loyalty`, việc đặt tại `ordering` khiến module đặt hàng phụ thuộc ngược vào các implementation này. Nó còn làm cho ranh giới module trở nên vô nghĩa dù dùng event thay vì lời gọi trực tiếp.

**Sửa:** di chuyển từng handler về module sở hữu side effect. Hợp đồng `OrderPlaced` vẫn do `ordering` công bố. Khi listener ở module tiêu thụ, phụ thuộc mã nguồn đi từ consumer tới contract, không từ publisher tới consumer.

## 9. Package-private, `public` và khả năng kiểm thử

Spring event listener là bean được framework gọi; các module khác thường không cần gọi thẳng method `on(...)`. Vì vậy một cách bố trí tốt là **class listener package-private**, constructor/method có phạm vi vừa đủ, còn contract event là `public` trong API được công bố.

Ví dụ tối giản khi listener và service nằm cùng package:

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
        sender.sendConfirmation(event.eventId(), event.orderId());
    }
}
~~~

Nếu `ConfirmationSender` cũng là package-private trong `notification.internal`, không cần mở rộng quyền truy cập class đó chỉ để handler ở subpackage khác import nó. Spring có hỗ trợ method listener không public trong những cấu hình thông thường, nhưng với proxy/JDK interface, native image và các chế độ runtime đặc biệt cần kiểm chứng thực tế.

**Không dùng modifier Java như lớp kiểm soát kiến trúc duy nhất.** Một service `public` trong `notification.internal` vẫn là chi tiết nội bộ Spring Modulith. Test module boundary bảo vệ quy tắc ở cấp module.

## 10. Kiểm tra phụ thuộc bằng `ApplicationModules.verify()`

Một test kiến trúc giữ ranh giới ổn định dù số listener tăng:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleBoundaryTest {

    @Test
    void keepsListenerDependenciesInsidePublicModuleApis() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Theo mô hình module và cấu hình hiện hành, `verify()` có thể phát hiện:

- `notification.internal.listener` import `ordering.internal.OrderRepository`.
- `analytics` dùng API không nằm trong `allowedDependencies`.
- Đồ thị module tạo vòng phụ thuộc khi một listener gọi ngược implementation của module khác.

Ví dụ lỗi:

~~~java
// Vi phạm ranh giới trong module notification:
import com.example.shop.ordering.internal.OrderEntity;
~~~

Nếu `OrderEntity` là `public`, Java compiler có thể chấp nhận import, nhưng Spring Modulith có thể bác bỏ khi xác minh ranh giới. Thay bằng `OrderPlaced` hoặc API truy vấn được công bố có chủ đích.

Kiểm tra kiến trúc **không chứng minh runtime có bean listener**, event được publish đúng, transaction commit hay email đã gửi. Đó là lý do cần thêm test hành vi.

## 11. Kiểm thử listener ở đúng package

### 11.1. Unit test logic của handler

Đặt test trong cùng Java package với listener package-private giúp gọi trực tiếp method mà không cần làm class `public`:

~~~java
package com.example.shop.notification.internal;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.example.shop.ordering.events.OrderPlaced;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderNotificationListenerTest {

    @Test
    void delegatesEventToNotificationService() {
        ConfirmationSender sender = mock(ConfirmationSender.class);
        OrderNotificationListener listener = new OrderNotificationListener(sender);
        OrderPlaced event = new OrderPlaced(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.parse("2026-11-25T08:00:00Z")
        );

        listener.on(event);

        verify(sender).sendConfirmation(event.eventId(), event.orderId());
    }
}
~~~

Test này sử dụng **phiên bản listener nằm tại `notification.internal` ở mục 9**. Nếu dùng cấu trúc `notification.internal.listener` của mục 5, đặt test cùng package đó và sử dụng implementation tương ứng. Hai class cùng tên ở hai mục là **hai phương án bố trí**, không nên tạo đồng thời trong một dự án.

Unit test trên chứng minh logic chuyển giao dữ liệu cho service nội bộ, **không chứng minh** annotation được Spring phát hiện, listener chạy sau commit hoặc xử lý bất đồng bộ.

### 11.2. Kiểm tra publisher qua `PublishedEvents`

Spring Modulith có công cụ `PublishedEvents` để thu thập sự kiện trong module test:

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
class OrderingEventTest {

    @Autowired
    OrderFacade orders;

    @Test
    void publishesOrderPlaced(PublishedEvents events) {
        UUID expectedId = orders.placeOrder(validRequest());

        assertThat(events.ofType(OrderPlaced.class))
                .extracting(OrderPlaced::orderId)
                .contains(expectedId);
    }

    private PlaceOrderRequest validRequest() {
        // Viết test fixture đúng với domain và repository của dự án.
        throw new UnsupportedOperationException("Provide valid fixture");
    }
}
~~~

`OrderFacade`, `PlaceOrderRequest` và `validRequest()` là các thành phần minh họa cần có implementation/fixture thực trước khi chạy. Test cho thấy cách kiểm tra event được phát, chưa chứng minh subscriber xử lý xong.

### 11.3. Integration test cần chứng minh listener thật sự hoạt động

Với `@ApplicationModuleTest` hoặc integration test Spring phù hợp, kiểm tra bean, ngữ nghĩa transaction và side effect của listener. Cần đặc biệt chú ý:

1. **Commit:** tạo đơn bằng service có transaction thật; xác nhận listener `AFTER_COMMIT` thực hiện side effect phù hợp.
2. **Rollback:** làm transaction của publisher rollback sau khi publish; listener sau commit không được thực hiện side effect.
3. **Async:** chờ một điều kiện có thể kiểm chứng thay vì mặc định side effect hoàn tất ngay lúc method publisher trả về.
4. **Lỗi:** mô phỏng sender thất bại; xác định publication và trạng thái lỗi theo hạ tầng được cấu hình.
5. **Retry:** gửi lại cùng event ID; kiểm tra không tạo side effect trùng.

Một bẫy phổ biến là gắn `@Transactional` lên chính method test rồi để Spring Test rollback khi kết thúc. Khi không có commit thật, listener `AFTER_COMMIT` không chạy, dù cấu hình ứng dụng đúng. Hãy tạo ranh giới transaction có commit rõ, ví dụ service được quản lý bởi Spring hoặc `TransactionTemplate` và cơ chế chờ async thích hợp.

## 12. Hướng phụ thuộc giữa listener và service nội bộ

Listener nên là **adapter mỏng**: nhận event, kiểm tra đầu vào hợp đồng cần thiết, gọi service nghiệp vụ trong cùng module và ghi nhận kết quả. Đặt toàn bộ xử lý SQL, email, HTTP và retry trong method `on(...)` sẽ khiến việc kiểm thử và kiểm soát transaction khó khăn.

Ví dụ:

~~~text
notification/internal/
    OrderNotificationListener.java
    ConfirmationService.java
    NotificationRepository.java
    EmailGateway.java
~~~

~~~java
@Component
class OrderNotificationListener {

    private final ConfirmationService confirmations;

    OrderNotificationListener(ConfirmationService confirmations) {
        this.confirmations = confirmations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        confirmations.handleOrderPlaced(
                event.eventId(),
                event.orderId()
        );
    }
}
~~~

`ConfirmationService` có thể chịu trách nhiệm kiểm tra trùng, truy vấn dữ liệu qua API hợp lệ, tạo notification record và gọi gateway gửi phù hợp. Cách này giúp listener gắn với package của module nhận, trong khi phần logic có thể được dùng lại và kiểm thử độc lập.

**Không tạo package `common.listeners` ở cấp ứng dụng chỉ để chứa tất cả event handlers.** Package “chung” thường làm khó xác định module nào sở hữu dữ liệu và luồng phản ứng, đồng thời dễ dẫn tới phụ thuộc vòng hoặc import implementation chéo.

## 13. Transaction và registry gắn với listener thực tế

Vì `@ApplicationModuleListener` là một cơ chế nhận sự kiện có điều kiện transaction, vị trí package chỉ là một phần thiết kế. Cần hiểu cách sự kiện được xử lý:

~~~mermaid
sequenceDiagram
    participant O as ordering
    participant DB as Database
    participant E as Spring events
    participant N as notification listener
    O->>DB: Lưu đơn trong transaction
    O->>E: publish OrderPlaced
    alt Commit thành công
        O->>DB: Commit
        E-->>N: Kích hoạt AFTER_COMMIT
        N->>N: Xử lý thông báo
    else Rollback
        O->>DB: Rollback
        Note over E,N: AFTER_COMMIT không được gọi
    end
~~~

Sơ đồ mô tả điều kiện kích hoạt listener sau commit. Trong thực tế listener bất đồng bộ có thể bắt đầu ở thời điểm khác với việc trả phản hồi của service phát.

### 13.1. Sau commit không phải là giao nhận chắc chắn

Nếu process dừng giữa lúc publisher commit và listener hoàn thành, handler có thể chưa xử lý xong. Nếu handler gửi email thành công rồi crash trước khi ghi nhận hoàn tất, lần khôi phục có thể gửi email lại.

Spring Modulith có **Event Publication Registry** để theo dõi publication của các listener được hỗ trợ khi cấu hình persistence tương ứng. Nó giúp nhận diện publication chưa hoàn tất và phục vụ chiến lược khôi phục/chạy lại. Tuy nhiên, **annotation listener và cách đặt package không tự cung cấp bảo đảm exactly-once hoặc retry vô hạn**.

### 13.2. Mỗi module chịu trách nhiệm idempotency của side effect

`notification` có thể dùng `eventId` để tránh gửi thông báo trùng; `analytics` có thể ghi nhận `eventId` trong cùng transaction cập nhật số liệu. Vì cùng một event có thể được nhận bởi nhiều listener, trạng thái xử lý nên được xét theo **consumer/listener và event**, tránh coi xử lý thành công ở module này là hoàn tất ở module khác.

Một mô hình đơn giản:

~~~text
OrderPlaced(eventId=E100, orderId=O200)
   |
   +--> notification: đã xử lý E100? => gửi hoặc bỏ qua
   |
   +--> analytics: đã xử lý E100?    => cộng chỉ số hoặc bỏ qua
~~~

Ghi dấu đã xử lý cùng transaction với cập nhật dữ liệu nội bộ nếu có thể. Với API ngoài như email, cần đánh giá idempotency key hoặc chính sách chống trùng vì transaction database local không bao phủ side effect bên ngoài.

## 14. Khi có nhiều listener cùng nghe một loại event

Việc listener ở nhiều package khác nhau có nghĩa **mỗi bean đủ điều kiện có thể được kích hoạt**, không có nghĩa chúng tạo thành một nhóm consumer có cơ chế chia tải giống queue trên broker.

| Mô hình | Cách hoạt động | Điều cần lưu ý |
| --- | --- | --- |
| Hai `@EventListener` cùng nhận `OrderPlaced` | Hai handler đủ điều kiện đều được gọi theo cơ chế dispatcher | Không mặc định tách công việc để chỉ một handler nhận |
| Hai `@ApplicationModuleListener` nhận `OrderPlaced` | Mỗi listener là một phản ứng sau commit theo cấu hình | Có thể có hai publication/trạng thái xử lý riêng khi registry hỗ trợ |
| Nhiều consumer của cùng một queue broker | Phân phối tùy mô hình broker/consumer group | Không được suy ra semantics của broker từ Spring event |
| Một listener có nhiều phiên bản cùng active | Có thể xử lý cùng event hai lần nếu vô tình đăng ký hai bean | Kiểm tra bean registration và mục đích mỗi subscriber |

Đừng dùng `@Order` hoặc tên package như cách đảm bảo thứ tự nghiệp vụ giữa các module xử lý bất đồng bộ. Nếu bước B bắt buộc chờ bước A, hãy mô hình hóa dependency/workflow đó rõ ràng qua kết quả nghiệp vụ, trạng thái hoặc event tiếp theo. Đơn thuần có nhiều listener của một event không tạo guarantee thứ tự hoặc tính nguyên tử xuyên module.

## 15. Một số sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đặt listener gửi email trong `ordering` vì event phát từ `ordering` | Module phát phụ thuộc implementation thông báo | Đưa listener về `notification.internal` |
| Đặt `OrderPlaced` trong `ordering.internal` | Consumer phải import internal package | Công bố event tại API hoặc named interface của `ordering` |
| Chuyển listener ra root package để Spring nhìn thấy | Tình cờ biến class triển khai thành API mặc định | Giữ ở subpackage nội bộ, sửa component scan/bean registration |
| Chỉ tạo package `listeners` mà không khai báo bean | Spring không đăng ký handler | Dùng `@Component` hoặc khai báo bean phù hợp |
| Nhầm `public` Java với API công khai module | Phụ thuộc nội bộ khó kiểm soát | Chạy `ApplicationModules.verify()` |
| Sử dụng `@EventListener` để gửi email trước commit | Có thể phát side effect cho đơn rollback | Dùng listener sau commit khi nghiệp vụ yêu cầu |
| Dùng `@Async` và mặc định sự kiện đã bền vững | Mất việc chưa xử lý khi process dừng | Cấu hình registry/persistence và recovery khi cần |
| Để listener trực tiếp gọi repository module khác | Rò rỉ quyền sở hữu dữ liệu | Dùng event payload hoặc public query API |
| Tạo nhiều handler trùng chức năng do scan hai lần | Xử lý side effect hai lần | Kiểm tra bean definitions và trách nhiệm mỗi listener |
| Test chỉ gọi thẳng `on(event)` | Không phát hiện lỗi scan/transaction | Thêm integration test với Spring context và commit thật |

## 16. Quy trình thiết kế listener theo package

Một quy trình thực tế để thêm phản ứng mới vào modular monolith:

1. **Xác định nghiệp vụ sở hữu phản ứng.** Ví dụ gửi xác nhận thuộc `notification`, không thuộc `ordering`.
2. **Chọn hợp đồng nguồn.** Kiểm tra sự kiện thực sự diễn đạt điều cần phản ứng; `OrderPlaced` không đồng nghĩa `PaymentCaptured`.
3. **Kiểm tra API được công bố.** Đặt event trong root API hoặc named interface; khai báo giới hạn dependency nếu cần.
4. **Tạo listener trong package nội bộ của consumer.** Thêm `@Component` và annotation phù hợp; giữ handler mỏng.
5. **Xác định transaction.** Phản ứng chỉ sau commit hay cần chạy đồng bộ trong transaction nguồn?
6. **Thiết kế xử lý lỗi.** Listener lỗi có cần retry? Có registry/persistence chưa? Idempotency key là gì?
7. **Kiểm tra Spring registration và ranh giới.** Chạy test kiến trúc, test module và integration test khi có side effect.
8. **Bổ sung quan sát.** Log/metric theo `eventId`, listener, trạng thái xử lý và số lần thử; không log dữ liệu nhạy cảm không cần thiết.

## 17. Bài thực hành

**Bối cảnh:** Ứng dụng có `ordering`, `notification` và `analytics`. Module đặt hàng phát `OrderPlaced` khi nhận đơn hàng thành công; hai module còn lại cần phản ứng sau khi dữ liệu được commit.

### Phần A — Tổ chức package

Tạo `ordering.events.OrderPlaced` và `ordering.events.package-info.java` khai báo `@NamedInterface("events")`. Trong `notification`, tạo listener ở `notification.internal` (hoặc `notification.internal.listener` nếu service nội bộ có mức truy cập phù hợp). Trong `analytics`, tạo listener tương ứng ở package nội bộ của module.

Kiểm tra xem `ordering.internal.OrderingService` có import class từ `notification` hoặc `analytics` hay không. Mục tiêu là **không có phụ thuộc mã nguồn từ publisher đến consumer**.

### Phần B — Kiểm chứng đăng ký listener

Thử lần lượt các tình huống:

1. Bỏ `@Component` khỏi một listener không được khai báo bean ở nơi khác; kiểm tra nó không được Spring đăng ký.
2. Đưa listener ra ngoài phạm vi component scan; xác định vì sao nó không nhận event.
3. Khôi phục vị trí dưới `com.example.shop` và annotation thích hợp; xác minh bean được đăng ký.
4. Thêm một listener analytics vào module riêng; chứng minh publisher không phải thay đổi.

### Phần C — Kiểm thử transaction và lỗi

Viết test đảm bảo event được publish khi tạo đơn thành công. Sau đó cố tình rollback transaction nguồn và xác minh listener `AFTER_COMMIT` không gửi email. Giả lập email lỗi sau commit, theo dõi publication theo registry đã cấu hình và thử xử lý lại cùng `eventId` để chứng minh cơ chế chống gửi trùng.

### Phần D — Checklist nghiệm thu

| Tiêu chí | Bằng chứng |
| --- | --- |
| Listener nằm trong đúng module sở hữu side effect | Cấu trúc package và review kiến trúc |
| Event contract thuộc API công khai | `@NamedInterface` hoặc root API; `verify()` PASS |
| Spring phát hiện handler | Spring context chứa bean và listener được kích hoạt theo tình huống |
| Publisher không biết consumer | Không import implementation consumer vào module phát |
| Rollback không kích hoạt side effect sau commit | Integration test transaction PASS |
| Retry không tạo tác vụ trùng | Test idempotency theo event ID |
| Có thể điều tra lỗi | Metrics/log/registry xác định event và listener liên quan |

## 18. Tự kiểm tra kiến thức

**Câu 1. Nếu `OrderPlaced` được phát từ `ordering`, listener gửi email nên nằm ở đâu?**

Ở `notification`, tốt nhất trong một package triển khai nội bộ như `notification.internal`. Hợp đồng `OrderPlaced` vẫn thuộc API được công bố của `ordering`.

**Câu 2. Chỉ cần tạo package `notification.listener` thì Spring tự nhận event không?**

Không. Class phải được Spring quản lý làm bean và method phải được đăng ký theo cơ chế listener. Package chỉ tổ chức mã nguồn và ảnh hưởng tới phạm vi scan.

**Câu 3. Vì sao nên giữ listener triển khai trong subpackage nội bộ của module?**

Vì listener không phải hợp đồng mà module khác cần gọi trực tiếp. Đặt nó ở nội bộ giúp giữ bề mặt API nhỏ và dễ thay đổi triển khai.

**Câu 4. `ApplicationModules.verify()` có chứng minh listener đã gửi email thành công không?**

Không. Nó kiểm tra phụ thuộc kiến trúc; cần integration test hoặc test tác dụng phụ để chứng minh hành vi runtime.

**Câu 5. Có hai listener nhận cùng một event thì chỉ một listener được chạy như consumer group trên queue không?**

Không. Spring application event thông thường có thể phát tới tất cả handler đủ điều kiện. Consumer group là khái niệm của hạ tầng messaging, có cơ chế phân phối khác.

**Câu 6. Dùng `@ApplicationModuleListener` thì có chắc chắn mỗi event được xử lý đúng một lần không?**

Không. Cần thiết kế registry, recovery và idempotency theo yêu cầu; hệ thống có thể xử lý lại một publication sau lỗi.

## 19. Kết luận

**“Listener theo package” là đặt phản ứng sự kiện vào module thực sự sở hữu hành vi đó.** Trong Spring Modulith, publisher và event contract thuộc module phát; mỗi consumer cài đặt listener trong package nội bộ của mình và chỉ import API sự kiện đã được công bố. Cách tổ chức này giảm phụ thuộc trực tiếp, giữ ranh giới module dễ kiểm tra và giúp từng phản ứng phát triển độc lập.

Package chỉ xác định ownership và góp phần vào component scanning. Khả năng tiếp nhận event còn phụ thuộc bean registration, listener annotation và transaction boundary. Để các listener đáng tin cậy trong thực tế, hãy kết hợp **xử lý sau commit**, **Event Publication Registry khi được cấu hình**, **retry/idempotency**, kiểm thử kiến trúc cùng kiểm thử runtime và quan sát theo từng consumer.
