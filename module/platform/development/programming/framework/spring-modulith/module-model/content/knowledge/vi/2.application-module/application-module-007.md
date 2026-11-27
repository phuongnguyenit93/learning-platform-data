# Application event được module phát ra

Một application module thường cần thông báo cho các phần khác của ứng dụng khi một việc nghiệp vụ đã xảy ra. Ví dụ, sau khi mô-đun `order` tạo đơn hàng thành công, mô-đun `shipping` cần chuẩn bị giao hàng và mô-đun `notification` cần gửi email xác nhận. Nếu `order` gọi trực tiếp từng mô-đun, nó phải biết nhiều chi tiết triển khai và dễ bị ràng buộc vào các bên nhận.

Spring Modulith hỗ trợ các mô-đun trao đổi qua application event của Spring. Mô-đun phát sự kiện công bố một sự thật nghiệp vụ; những mô-đun quan tâm đăng ký listener để phản ứng. Mô-đun phát không cần biết có bao nhiêu bên nhận. Khi thiết kế đúng, event trở thành một phần API công khai của mô-đun và được kiểm soát như các hợp đồng package khác.

## 1. Application event là thông báo về một sự thật nghiệp vụ

Application event là một đối tượng mô tả điều gì đó đã xảy ra trong ứng dụng. Trong Spring, mô-đun có thể phát đối tượng đó bằng `ApplicationEventPublisher`.

Ví dụ:

- `OrderPlaced`: một đơn hàng đã được tạo.
- `PaymentReceived`: hệ thống đã nhận được thanh toán.
- `StockReserved`: số lượng hàng đã được giữ cho một đơn hàng.

Tên event thường dùng thì quá khứ vì nó mô tả một sự kiện đã xảy ra. Nội dung event nên thể hiện một sự thật ổn định, chẳng hạn mã đơn hàng, tổng tiền và thời điểm tạo đơn.

Event khác với command. `PlaceOrder` là yêu cầu tạo đơn hàng; `OrderPlaced` là thông báo rằng đơn hàng đã được tạo. Bên nhận event không được hiểu thông báo đó như một yêu cầu có thể tùy ý thực hiện hoặc từ chối. Nếu nghiệp vụ chưa xảy ra, mô-đun sở hữu nghiệp vụ không nên phát event khẳng định rằng nó đã xảy ra.

Một event tốt thường có các đặc điểm sau:

- **Bất biến:** dữ liệu không thay đổi sau khi phát. Java `record` là lựa chọn phù hợp cho payload đơn giản.
- **Có ý nghĩa nghiệp vụ:** tên và trường dữ liệu mô tả điều đã xảy ra, không phơi bày cấu trúc bảng hoặc chi tiết ORM.
- **Đủ thông tin cho bên nhận:** listener có thể hiểu và xử lý event mà không phải truy cập trực tiếp repository nội bộ của mô-đun phát.
- **Ổn định như một hợp đồng:** thay đổi tên, kiểu dữ liệu hoặc ý nghĩa của event có thể ảnh hưởng đến mọi mô-đun đang tiêu thụ nó.

Tránh gửi toàn bộ JPA entity hoặc aggregate đang được quản lý làm payload. Đối tượng đó có thể chứa proxy, quan hệ lazy hoặc trạng thái có thể thay đổi. Một event nhỏ với các giá trị cần thiết giúp hợp đồng rõ ràng và ít phụ thuộc vào mô hình lưu trữ hơn.

## 2. Mô-đun phát event sở hữu hợp đồng sự kiện

Giả sử ứng dụng có package gốc `com.acme.shop` và mô-đun `order` chịu trách nhiệm tạo đơn hàng. Mô-đun này công bố event trong package riêng:

```text
com.acme.shop
├── order
│   ├── OrderManagement.java
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── internal
│       └── PlaceOrderService.java
└── shipping
    └── ShippingOnOrderPlaced.java
```

Định nghĩa payload event:

```java
package com.acme.shop.order.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID orderId,
        BigDecimal total,
        Instant occurredAt
) {}
```

`OrderPlaced` được đặt trong package `order.events`. Vì package con của một application module mặc định là nội bộ, mô-đun `order` cần công bố rõ package này nếu muốn các mô-đun khác sử dụng event.

Trong `package-info.java`, khai báo một Named Interface:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
```

Sau khai báo này, `order.events` trở thành giao diện công khai có tên `events` của mô-đun `order`. Những mô-đun khác có thể phụ thuộc vào hợp đồng event được công bố mà không phải truy cập các package triển khai như `order.internal`.

Mô-đun phát chịu trách nhiệm về ý nghĩa và khả năng tương thích của event. Nếu đổi `OrderPlaced` thành một cấu trúc khác, cần xem xét các listener đang sử dụng hợp đồng này. Không nên đổi payload chỉ vì một thay đổi nội bộ trong cách lưu đơn hàng.

## 3. Phát event trong quy trình nghiệp vụ

Mô-đun phát sử dụng `ApplicationEventPublisher` để công bố event. Trong ví dụ dưới đây, dịch vụ tạo đơn lưu đơn hàng rồi phát `OrderPlaced` trong cùng transaction:

```java
package com.acme.shop.order.internal;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;

@Service
class PlaceOrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    PlaceOrderService(
            OrderRepository orders,
            ApplicationEventPublisher events
    ) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    OrderId place(PlaceOrder command) {
        Order order = Order.create(command);
        orders.save(order);

        events.publishEvent(new OrderPlaced(
                order.id().value(),
                order.total(),
                Instant.now()
        ));

        return order.id();
    }
}
```

Đoạn code minh họa thứ tự trách nhiệm: mô-đun `order` tạo và lưu đơn, sau đó thông báo sự kiện `OrderPlaced`. Các kiểu `Order`, `OrderRepository`, `PlaceOrder` và `OrderId` là những thành phần nội bộ minh họa của mô-đun; listener bên ngoài chỉ cần hợp đồng `OrderPlaced`.

`publishEvent()` gửi event vào Spring application context. Lệnh gọi này tự nó không có nghĩa event đã được ghi vào message broker hoặc chuyển sang một tiến trình khác. Cách listener nhận và xử lý event phụ thuộc vào loại listener được khai báo.

Khi event được phát bên trong transaction như ví dụ, cần chọn thời điểm xử lý phù hợp. Một listener thông thường với `@EventListener` được gọi đồng bộ theo cơ chế mặc định của Spring, trên luồng phát event. Nếu muốn chỉ xử lý sau khi transaction nghiệp vụ commit, có thể dùng `@TransactionalEventListener` hoặc annotation tích hợp của Spring Modulith.

## 4. Mô-đun khác tiêu thụ event

Mô-đun `shipping` có thể đăng ký listener để nhận `OrderPlaced`. Với Spring Modulith, `@ApplicationModuleListener` là cách khai báo listener thường dùng cho giao tiếp giữa các application module:

```java
package com.acme.shop.shipping;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ShippingOnOrderPlaced {

    private final ShippingService shipping;

    ShippingOnOrderPlaced(ShippingService shipping) {
        this.shipping = shipping;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        shipping.prepareShipment(event.orderId());
    }
}
```

Listener chỉ biết event contract và dịch vụ nội bộ của `shipping`. Nó không cần import `OrderRepository`, gọi `OrderManagement` hoặc biết cách `order` lưu dữ liệu.

`@ApplicationModuleListener` kết hợp cơ chế xử lý event sau commit của Spring với xử lý bất đồng bộ và transaction riêng cho listener. Nhờ đó, công việc chuẩn bị giao hàng có thể chạy sau khi transaction tạo đơn đã commit, trong một transaction độc lập. Để xử lý bất đồng bộ bằng `@Async`, ứng dụng cần bật hỗ trợ async của Spring, chẳng hạn bằng `@EnableAsync` trong cấu hình phù hợp.

Nếu không muốn xử lý bất đồng bộ, có thể dùng `@TransactionalEventListener`:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderPlaced event) {
    shipping.prepareShipment(event.orderId());
}
```

Với cấu hình mặc định, `@TransactionalEventListener` chỉ chạy khi có transaction phù hợp và mặc định xử lý ở giai đoạn `AFTER_COMMIT`. Nếu event được phát ngoài transaction, listener sẽ không được gọi trừ khi bật `fallbackExecution`. Listener thông thường dùng `@EventListener` không có quy tắc chờ commit như vậy.

## 5. Khai báo phụ thuộc vào Named Interface

Event là hợp đồng công khai của `order`, vì vậy phụ thuộc của `shipping` cần được giới hạn vào đúng Named Interface đó. Có thể khai báo trên package của mô-đun `shipping`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: events"
)
package com.acme.shop.shipping;
```

Khai báo này thể hiện `shipping` được phép phụ thuộc vào giao diện `events` của mô-đun `order`. Nó không mở quyền truy cập vào `order.internal` hoặc mọi package khác của `order`.

Khi chạy kiểm tra kiến trúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Spring Modulith có thể phát hiện `shipping` truy cập package không được công bố hoặc vi phạm `allowedDependencies`. Nhờ đó, việc dùng event vẫn tuân thủ ranh giới mô-đun thay vì trở thành một con đường vòng để truy cập triển khai nội bộ.

## 6. Thời điểm phát và xử lý event gắn với transaction

Khi phát event từ một phương thức `@Transactional`, cần phân biệt ba thời điểm:

1. **Trong transaction:** nghiệp vụ đang được xử lý; dữ liệu chưa chắc đã commit.
2. **Sau commit:** dữ liệu nghiệp vụ đã được commit thành công; listener có thể bắt đầu công việc phụ thuộc vào dữ liệu đó.
3. **Sau rollback:** transaction thất bại; event mô tả một sự thật đã xảy ra không nên được xử lý như thể nghiệp vụ đã thành công.

Spring cung cấp `@TransactionalEventListener` để gắn listener với các giai đoạn transaction:

| Phase | Thời điểm listener chạy |
| --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction commit |
| `AFTER_COMMIT` | Sau khi transaction commit thành công; đây là mặc định |
| `AFTER_ROLLBACK` | Sau khi transaction rollback |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất, dù commit hay rollback |

Với thông báo như `OrderPlaced`, `AFTER_COMMIT` thường phù hợp vì đơn hàng phải được lưu thành công trước khi mô-đun khác chuẩn bị giao hàng. Nếu listener chạy trước commit, nó có thể thực hiện tác động phụ trong khi transaction tạo đơn cuối cùng lại rollback.

Một điểm cần hiểu rõ: `AFTER_COMMIT` chỉ xác định thời điểm gọi listener. Nó không tự biến event thành một thông điệp bền vững trong broker và không bảo đảm một listener bất đồng bộ sẽ luôn hoàn thành nếu tiến trình dừng đột ngột.

## 7. Event Publication Registry và khả năng phục hồi

Đối với listener giao dịch, Spring Modulith cung cấp Event Publication Registry để theo dõi việc giao event đến từng listener. Khi được cấu hình với một cơ chế lưu trữ bền vững phù hợp, registry ghi nhận publication trong transaction phát event. Mỗi publication được đánh dấu hoàn tất khi listener xử lý thành công.

Điều này giải quyết một tình huống thực tế: transaction tạo đơn đã commit, nhưng listener xử lý chưa hoàn thành vì lỗi hoặc tiến trình bị gián đoạn. Publication chưa hoàn tất có thể được quan sát và gửi xử lý lại theo cơ chế phục hồi của Spring Modulith. Nhóm vận hành có thể dựa vào trạng thái publication để điều tra listener nào đang lỗi.

Có thể hình dung vòng đời publication như sau:

```text
Trong transaction tạo đơn, event được phát
          |
          v
Registry ghi nhận publication cho listener
          |
          v
Transaction nghiệp vụ commit
          |
          v
Listener nhận và xử lý event
          |
      +---+---+
      |       |
   Thành công  Thất bại/gián đoạn
      |       |
      v       v
  Hoàn tất   Còn publication chưa hoàn tất
                  |
                  v
             Có thể phục hồi

Nếu transaction nghiệp vụ rollback, event và publication đã ghi trong transaction
cũng rollback; listener sau commit không được gọi.
```

Registry giúp theo dõi và phục hồi publication cho transactional listener. Nó không thay thế thiết kế xử lý lỗi của ứng dụng, cũng không bảo đảm mọi tác động bên ngoài được thực hiện đúng một lần. Nếu listener gọi dịch vụ bên ngoài rồi gặp lỗi trước khi publication được đánh dấu hoàn tất, lần xử lý lại có thể lặp tác động đó. Vì vậy, listener nên được thiết kế idempotent khi có thể: nhận cùng một event nhiều lần vẫn không tạo ra kết quả nghiệp vụ sai hoặc trùng lặp.

Khả năng lưu trữ và phục hồi phụ thuộc vào implementation persistence mà ứng dụng cấu hình, chẳng hạn tích hợp JDBC hoặc JPA tương ứng. Chỉ gọi `ApplicationEventPublisher.publishEvent()` không đồng nghĩa đã bật một registry bền vững.

## 8. Khi nào nên dùng event thay cho gọi API trực tiếp?

Không phải mọi lời gọi giữa các mô-đun đều nên chuyển thành event. Hãy chọn cách giao tiếp dựa trên ý nghĩa nghiệp vụ và mức độ phụ thuộc mong muốn.

| Nhu cầu | Cách giao tiếp phù hợp |
| --- | --- |
| Mô-đun gọi một nghiệp vụ và cần kết quả ngay | Gọi API công khai của mô-đun đó |
| Một sự thật đã xảy ra và nhiều mô-đun có thể quan tâm | Phát application event |
| Bên gọi cần biết thao tác có thành công hay không trước khi tiếp tục | Gọi API đồng bộ hoặc dùng một quy trình có phản hồi rõ ràng |
| Công việc phụ có thể thực hiện sau khi nghiệp vụ chính commit | Dùng transactional event listener phù hợp |

Event đặc biệt hữu ích khi mô-đun phát không cần biết danh sách bên nhận. Hôm nay `OrderPlaced` có thể chỉ được `shipping` xử lý; sau này `notification` hoặc `analytics` có thể đăng ký thêm listener mà không cần sửa quy trình tạo đơn trong `order`.

Đổi lại, giao tiếp qua event thường làm cho kết quả ở các mô-đun khác xuất hiện sau đó. Đây là tính nhất quán cuối cùng: sau khi đơn hàng commit, việc chuẩn bị giao hàng hoặc gửi thông báo có thể chưa hoàn tất ngay tại thời điểm API tạo đơn trả về. Giao diện và quy trình nghiệp vụ cần phản ánh đúng điều này.

Không nên dùng event để che giấu một lời gọi đồng bộ cần kết quả ngay. Nếu `order` phải biết ngay kho còn đủ hàng hay không trước khi xác nhận đơn, nó cần một hợp đồng truy vấn hoặc kiểm tra đồng bộ thích hợp. Phát `OrderPlaced` rồi chờ một listener khác trả lời sẽ làm luồng điều khiển khó hiểu và không phù hợp với ý nghĩa thông báo sự kiện.

## 9. Những lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Đặt event trong package `internal` rồi import từ mô-đun khác | Bên nhận đang truy cập phần triển khai nội bộ | Công bố event qua package gốc hoặc Named Interface có chủ đích |
| Phát event trước khi nghiệp vụ thành công | Bên nhận có thể phản ứng với một sự thật chưa được commit | Phát trong transaction và dùng listener ở phase phù hợp |
| Dùng event như một command | Bên nhận không rõ đang được thông báo hay bị yêu cầu thực hiện việc gì | Dùng tên quá khứ cho sự thật đã xảy ra; dùng API/command cho yêu cầu |
| Gửi entity hoặc đối tượng ORM làm payload | Hợp đồng phụ thuộc vào cấu trúc lưu trữ và trạng thái mutable | Tạo event payload nhỏ, bất biến và có ý nghĩa nghiệp vụ |
| Cho rằng `publishEvent()` tự gửi sang Kafka hoặc RabbitMQ | Spring application event mặc định chỉ hoạt động trong application context | Cấu hình tích hợp externalization/message broker riêng khi cần giao tiếp liên tiến trình |
| Cho rằng listener bất đồng bộ luôn hoàn tất đúng một lần | Lỗi và phục hồi có thể dẫn đến xử lý lại | Theo dõi publication, xử lý lỗi và thiết kế listener idempotent |
| Công bố quá nhiều package event | API công khai trở nên rộng và khó duy trì | Chỉ công bố những event thực sự là hợp đồng tích hợp giữa các mô-đun |

## 10. Quy trình thiết kế event giữa các module

Khi thêm một event mới, có thể thực hiện theo trình tự sau:

1. Xác định sự thật nghiệp vụ đã xảy ra và mô-đun sở hữu sự thật đó.
2. Đặt tên event ở thì quá khứ, chọn các trường dữ liệu ổn định và bất biến.
3. Đặt event trong package API của mô-đun phát hoặc một Named Interface chuyên biệt như `events`.
4. Phát event từ luồng nghiệp vụ tại thời điểm phù hợp với transaction.
5. Đăng ký listener trong mô-đun tiêu thụ và khai báo phụ thuộc đến đúng Named Interface.
6. Chọn xử lý đồng bộ, sau commit hoặc bất đồng bộ theo yêu cầu nghiệp vụ; xác định cách xử lý lỗi và phục hồi.
7. Kiểm tra kiến trúc bằng `ApplicationModules.verify()` và kiểm thử hành vi phát/tiêu thụ event.

Một event tốt tạo ra hợp đồng rõ ràng giữa các mô-đun. Mô-đun phát công bố sự thật nghiệp vụ mà nó sở hữu; mô-đun tiêu thụ quyết định cách phản ứng trong phạm vi trách nhiệm của mình. Spring Modulith giúp mô hình hóa hợp đồng đó bằng package, Named Interface, listener và Event Publication Registry, đồng thời cung cấp công cụ để kiểm tra và vận hành giao tiếp nội bộ.

## Tài liệu tham khảo

- [Spring Modulith Reference — Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
