# Static dependency khác choreography runtime

Bài này thuộc chương **Model và events** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith mô hình hóa các application module trong ứng dụng Spring Boot để làm rõ ranh giới nghiệp vụ, API công khai và quan hệ phụ thuộc giữa package. Khi một module phát application event và module khác lắng nghe event đó, cần phân biệt hai góc nhìn: **dependency tĩnh trong mã nguồn** và **luồng phối hợp tại runtime**.

Hai góc nhìn này có thể có hướng khác nhau. Module phát event không cần biết lớp listener của module nhận, nhưng listener vẫn cần tham chiếu kiểu event để xử lý dữ liệu. Vì vậy, event giúp giảm coupling trực tiếp giữa producer và consumer, chứ không có nghĩa hai module hoàn toàn không có quan hệ phụ thuộc.

## 1. Hai đồ thị mô tả hai câu hỏi khác nhau

Giả sử module order phát sự kiện `OrderConfirmed`; module shipping và payment đăng ký listener để xử lý sự kiện đó.

~~~text
Module order
  └── publishes OrderConfirmed

Module shipping
  └── listens to OrderConfirmed

Module payment
  └── listens to OrderConfirmed
~~~

Ở góc nhìn mã nguồn, shipping và payment cần biết kiểu `OrderConfirmed` do order sở hữu. Order không import các listener:

~~~text
STATIC DEPENDENCY (compile-time)

shipping ───────> order
payment  ───────> order


RUNTIME EVENT FLOW

order ──────────> shipping
      └─────────> payment
~~~

Hai đồ thị trả lời hai câu hỏi:

- **Dependency tĩnh:** module nào cần tham chiếu kiểu hoặc hợp đồng thuộc module nào để biên dịch?
- **Choreography runtime:** khi một sự kiện được phát, module nào nhận và phản ứng với sự kiện đó?

Không nên đọc mũi tên trong đồ thị tĩnh như thể đó là thứ tự gọi hàm ở runtime. Với event, hướng tham chiếu trong mã nguồn có thể ngược với hướng truyền thông điệp khi ứng dụng chạy.

## 2. Dependency tĩnh hình thành từ event contract

Module order sở hữu sự kiện nghiệp vụ:

~~~java
package com.acme.shop.order;

import java.time.Instant;

public record OrderConfirmed(
        String orderId,
        Instant confirmedAt
) {
}
~~~

Khi order xác nhận đơn, nó phát event bằng Spring's `ApplicationEventPublisher`:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.order.OrderConfirmed;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

import java.time.Instant;

@Component
class OrderConfirmationService {

    private final ApplicationEventPublisher events;

    OrderConfirmationService(ApplicationEventPublisher events) {
        this.events = events;
    }

    void confirm(String orderId) {
        // Thực hiện các quy tắc xác nhận đơn hàng.
        events.publishEvent(new OrderConfirmed(orderId, Instant.now()));
    }
}
~~~

Module order tham chiếu kiểu event do chính nó sở hữu và API publish event của Spring. Nó không cần import `ShippingOrderConfirmedListener` hay `PaymentOrderConfirmedListener`.

Vì vậy, trong mã nguồn của producer không có dependency trực tiếp tới các module nhận event. Producer chỉ công bố một sự kiện có ý nghĩa nghiệp vụ.

## 3. Listener tạo dependency tĩnh về module sở hữu event

Module shipping cần tham chiếu kiểu `OrderConfirmed` để khai báo listener:

~~~java
package com.acme.shop.shipping.internal;

import com.acme.shop.order.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ShippingOrderConfirmedListener {

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        // Tạo yêu cầu giao hàng từ thông tin đơn đã xác nhận.
    }
}
~~~

Do listener import và nhận `OrderConfirmed`, mã nguồn của shipping có tham chiếu tới kiểu thuộc order. Ở cấp application module, đây là dependency tĩnh:

~~~text
shipping ───────> order
        OrderConfirmed
~~~

Module payment có listener tương tự cũng tạo dependency tĩnh payment → order.

Điều này có ý nghĩa kiến trúc: event contract là một phần API mà producer công khai. Consumer phụ thuộc vào schema/kiểu sự kiện đó, dù producer không biết consumer nào đang lắng nghe.

## 4. Choreography runtime đi theo hướng publish đến listener

Khi order phát `OrderConfirmed`, Spring application event infrastructure phân phối sự kiện tới các listener phù hợp. Ở góc nhìn nghiệp vụ, luồng phối hợp là:

~~~text
Order được xác nhận
        |
        v
publish OrderConfirmed
        |
        +--------------------+
        |                    |
        v                    v
Shipping listener      Payment listener
        |                    |
        v                    v
Tạo yêu cầu giao hàng   Khởi tạo xử lý thanh toán
~~~

Đây là runtime choreography: producer phát thông báo về điều đã xảy ra, các consumer tự quyết định hành động tiếp theo.

Order không cần gọi trực tiếp service của shipping hoặc payment. Khi thêm một consumer mới, producer thường không cần thay đổi mã nguồn chỉ để biết thêm listener đó.

Tuy nhiên, event flow còn phụ thuộc vào cách listener được cấu hình: listener đồng bộ hay bất đồng bộ, transactional event listener hay cơ chế xử lý khác. Hãy phân biệt hướng nghiệp vụ của event với chi tiết thực thi và thời điểm listener được gọi.

## 5. Spring Modulith phân loại event listener dependency

Spring Modulith không chỉ nhìn mọi dependency là quan hệ gọi component thông thường. Mô hình module có thể phân loại quan hệ listener tới event của module khác bằng `DependencyType.EVENT_LISTENER`.

Ví dụ:

- Shipping lắng nghe `OrderConfirmed` do order công bố: dependency tĩnh shipping → order, được nhận diện là event listener dependency.
- Payment lắng nghe `OrderConfirmed`: dependency tĩnh payment → order, cũng là event listener dependency.
- Order gọi trực tiếp một bean của inventory: dependency thông thường từ order → inventory, thường được phân loại `DEFAULT` hoặc loại tương ứng với component được dùng.

Việc phân loại giúp mô hình diễn đạt bản chất dependency. Nó không đổi hướng tham chiếu tĩnh thành hướng runtime và cũng không xóa dependency tới event contract.

## 6. Event giảm coupling trực tiếp, nhưng không xóa hợp đồng

So sánh hai cách phối hợp.

Gọi trực tiếp:

~~~java
class OrderConfirmationService {

    private final ShippingService shipping;

    OrderConfirmationService(ShippingService shipping) {
        this.shipping = shipping;
    }

    void confirm(String orderId) {
        // Xác nhận đơn.
        shipping.prepareShipment(orderId);
    }
}
~~~

Producer phải biết kiểu service của shipping. Mã nguồn order phụ thuộc shipping; luồng runtime cũng gọi trực tiếp shipping.

Phát event:

~~~java
class OrderConfirmationService {

    private final ApplicationEventPublisher events;

    OrderConfirmationService(ApplicationEventPublisher events) {
        this.events = events;
    }

    void confirm(String orderId) {
        // Xác nhận đơn.
        events.publishEvent(new OrderConfirmed(orderId, Instant.now()));
    }
}
~~~

Producer không biết các listener cụ thể. Consumer phụ thuộc event contract của order và tự xử lý khi nhận sự kiện.

Event loại bỏ dependency trực tiếp từ producer tới consumer, nhưng consumer vẫn phụ thuộc vào event type và ý nghĩa dữ liệu trong event. Nếu producer thay đổi tên package, tên class hoặc schema event, consumer có thể cần cập nhật.

## 7. Công khai event contract qua API module

Event được consumer tham chiếu nên thuộc bề mặt API công khai của module producer. Nếu event đặt trong package con, có thể công khai package đó bằng named interface.

Ví dụ:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
~~~

Event contract:

~~~java
package com.acme.shop.order.events;

import java.time.Instant;

public record OrderConfirmed(
        String orderId,
        Instant confirmedAt
) {
}
~~~

Listener của shipping import event từ named interface:

~~~java
package com.acme.shop.shipping.internal;

import com.acme.shop.order.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ShippingOrderConfirmedListener {

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        // Xử lý giao hàng.
    }
}
~~~

Module shipping có thể khai báo dependency được phép:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order::events"
)
package com.acme.shop.shipping;
~~~

Như vậy, module order công khai nhóm event contract qua `events`; shipping chỉ cần phụ thuộc vào named interface này. Những package nội bộ khác của order vẫn được giữ kín.

Named interface quản lý bề mặt API; nó không biến event thành một giao tiếp không có dependency. Listener vẫn có static dependency tới module sở hữu event.

## 8. @ApplicationModuleListener và cách listener được thực thi

Spring Modulith cung cấp `@ApplicationModuleListener` để khai báo listener ở ranh giới application module. Annotation này là một composed annotation kết hợp cơ chế xử lý event của Spring với các semantics phù hợp cho module listener.

Ví dụ:

~~~java
@Component
class ShippingOrderConfirmedListener {

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        // Xử lý nghiệp vụ của shipping.
    }
}
~~~

Trong cấu hình Spring Modulith thông thường, `@ApplicationModuleListener` được thiết kế cho xử lý event theo module, bao gồm execution bất đồng bộ và transaction riêng cho listener. Hãy kiểm tra cấu hình transaction, executor và event publication của ứng dụng để hiểu chính xác hành vi trong môi trường đang chạy.

Nếu dùng `@EventListener` hoặc `@TransactionalEventListener` trực tiếp, semantics đồng bộ, transaction phase và cách xử lý lỗi có thể khác. Đừng suy ra listener bất đồng bộ chỉ từ việc phương thức có annotation event listener bất kỳ.

## 9. Event không phải lời gọi request-response

Event thường mô tả một điều đã xảy ra, ví dụ `OrderConfirmed`, `StockReserved` hoặc `PaymentCaptured`. Consumer nhận thông báo và tự quyết định phản ứng.

Nếu order cần câu trả lời ngay lập tức để quyết định có xác nhận đơn hay không, event một chiều có thể không phù hợp. Một API đồng bộ hoặc port có thể phù hợp hơn:

| Nhu cầu | Cách phối hợp thường phù hợp |
|---|---|
| Cần kết quả ngay để tiếp tục hoặc từ chối use case. | Gọi API/port đồng bộ. |
| Thông báo một sự kiện nghiệp vụ đã xảy ra. | Publish application event. |
| Nhiều module độc lập cần phản ứng với cùng một sự kiện. | Event với nhiều listener. |
| Cần trạng thái xử lý và khả năng retry sau commit. | Cân nhắc event publication registry và chính sách retry phù hợp. |
| Cần hỏi dữ liệu hiện tại của module khác. | Dùng query API/port có hợp đồng rõ ràng. |

Không nên dùng event chỉ để thay thế mọi lời gọi method. Event làm thay đổi semantics từ “yêu cầu bên kia làm việc” sang “thông báo một sự kiện để bên kia tự phản ứng”.

## 10. Transaction và độ tin cậy của event flow

Khi event được phát trong một transaction nghiệp vụ, nhóm cần quyết định listener nên xử lý ở thời điểm nào và điều gì xảy ra nếu listener thất bại.

Các câu hỏi quan trọng:

- Listener có cần chạy sau khi transaction của producer commit không?
- Nếu ứng dụng dừng giữa lúc commit và xử lý listener, sự kiện có cần được ghi nhận để xử lý lại không?
- Listener có thể được gọi lại không, và thao tác có idempotent không?
- Lỗi của một listener có ảnh hưởng tới các listener khác không?
- Có cần retry, dead-letter hoặc quan sát trạng thái xử lý không?

Spring Modulith Event Publication Registry có thể ghi nhận publication tới listener trong cùng transaction để hỗ trợ theo dõi và xử lý lại publication chưa hoàn tất, khi được cấu hình phù hợp. Registry và chính sách retry là vấn đề runtime reliability; chúng không làm biến mất static dependency tới event contract.

Hãy thiết kế consumer chịu được việc xử lý lặp nếu cơ chế retry hoặc phục hồi có thể gọi lại listener. Đối với side effect bên ngoài như gửi email hoặc gọi payment provider, cần có idempotency key hoặc cơ chế bảo vệ tương ứng.

## 11. Kiểm tra mô hình dependency và event

Có thể tạo mô hình module và xác minh ranh giới:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Verification giúp kiểm tra dependency giữa các module, bao gồm việc consumer truy cập event contract qua API được công khai hay package nội bộ.

Để xem quan hệ được phân loại, có thể duyệt dependency trực tiếp:

~~~java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule shipping = modules.getModuleByName("shipping")
        .orElseThrow();

shipping.getDirectDependencies(modules).forEach(dependency ->
        System.out.printf(
                "%s -> %s [%s]%n",
                dependency.getSourceType().getName(),
                dependency.getTargetType().getName(),
                dependency.getDependencyType()
        )
);
~~~

Khi có listener tới event của order, dependency model có thể hiển thị loại `EVENT_LISTENER`. Điều đó giúp nhóm phân biệt event contract dependency với dependency sử dụng component thông thường.

Verification không chứng minh event flow runtime đã thành công. Cần test listener, transaction, publication registry và lỗi xử lý riêng theo yêu cầu của hệ thống.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Dùng event nghĩa là không còn dependency giữa module. | Listener vẫn tham chiếu event contract của producer. |
| Mũi tên dependency tĩnh chính là hướng event được truyền lúc chạy. | Static graph và runtime choreography có thể ngược hướng. |
| Producer biết tất cả listener. | Producer chỉ publish event; consumer tự đăng ký listener. |
| Named interface loại bỏ cycle tự động. | Named interface giới hạn API; cần thiết kế lại dependency nếu còn cycle. |
| Mọi event listener đều chạy bất đồng bộ. | Semantics phụ thuộc annotation và cấu hình; `@ApplicationModuleListener` có semantics riêng. |
| Event bảo đảm listener luôn xử lý thành công đúng một lần. | Cần cấu hình reliability, retry và idempotency phù hợp. |
| `verify()` kiểm tra được runtime delivery. | `verify()` kiểm tra mô hình kiến trúc tĩnh, không thay thế integration test runtime. |

## 13. Quy trình thiết kế event giữa các module

1. **Xác định sự kiện nghiệp vụ.** Chọn một sự kiện mô tả điều đã xảy ra, không biến event thành lệnh gọi method trá hình.
2. **Chọn module sở hữu event.** Module phát sự kiện chịu trách nhiệm về ý nghĩa và schema của contract.
3. **Đặt event trong API công khai.** Dùng package gốc hoặc named interface phù hợp.
4. **Thiết kế payload ổn định.** Chỉ chứa dữ liệu consumer cần; tránh đưa entity hoặc object nội bộ vào event.
5. **Đăng ký listener tại consumer.** Consumer tham chiếu event contract và thực hiện hành vi của chính nó.
6. **Kiểm tra static dependency.** Xác nhận consumer → event owner là dependency có chủ đích và được phép.
7. **Kiểm tra runtime choreography.** Xác minh producer publish, listener nhận và xử lý đúng.
8. **Xác định transaction/retry.** Chọn semantics phù hợp và bảo đảm consumer có thể xử lý lỗi hoặc lặp nếu cần.
9. **Đưa vào kiểm tra tự động.** Dùng `ApplicationModules.verify()` cho cấu trúc module và integration test cho event flow.

## Ghi nhớ

Static dependency mô tả module nào tham chiếu kiểu hoặc hợp đồng của module nào. Runtime choreography mô tả event được publish và listener phản ứng ra sao. Với application event, listener thường có static dependency tới module sở hữu event contract, trong khi luồng runtime đi từ producer tới listener.

Event giúp producer không cần biết các consumer cụ thể, nhưng event contract vẫn là API cần quản lý. Hãy công khai event qua package API hoặc named interface, kiểm tra dependency bằng Spring Modulith, đồng thời test transaction, delivery và xử lý lỗi ở runtime.
