# Kiểm thử graph khi thêm subscriber

Trong Spring Modulith, một module có thể giao tiếp với module khác bằng application event. Module phát sự kiện công bố kiểu event như một phần hợp đồng; module đăng ký lắng nghe sự kiện phụ thuộc vào hợp đồng đó. Vì vậy, thêm một subscriber có thể làm thay đổi dependency graph của ứng dụng dù không thêm lời gọi service trực tiếp.

Khi thêm subscriber, cần kiểm tra graph để biết dependency mới có hợp lệ hay tạo thành vòng phụ thuộc. `ApplicationModules.verify()` là kiểm tra kiến trúc phù hợp để chạy sau thay đổi này. Nó phân tích các dependency giữa module, bao gồm dependency được suy ra từ event listener, rồi báo lỗi nếu cấu trúc vi phạm quy tắc.

## 1. Event flow và dependency graph là hai hướng nhìn

Giả sử module `order` phát `OrderCompleted`. Module `shipping` lắng nghe sự kiện đó để tạo yêu cầu giao hàng.

Luồng sự kiện đi từ publisher đến subscriber:

~~~text
order
  |
  | publish OrderCompleted
  v
OrderCompleted
  |
  | delivered to listener
  v
shipping
~~~

Nhưng trong dependency graph, chiều phụ thuộc được nhìn từ module tiêu thụ hợp đồng đến module sở hữu hợp đồng:

~~~text
shipping ─────depends on─────> order
             OrderCompleted
~~~

`shipping` cần biết kiểu `OrderCompleted` để khai báo listener. Kiểu event thuộc API của `order`, do đó `shipping` phụ thuộc vào `order`.

Phân biệt hai hướng này giúp đọc graph chính xác. Mũi tên của event flow biểu diễn nơi sự kiện được gửi đến; mũi tên dependency biểu diễn module nào cần hợp đồng do module nào sở hữu.

## 2. Đặt event trong API của module phát

Event được module khác tiêu thụ cần thuộc phần API được công bố của module phát. Ví dụ, module `order` khai báo record:

~~~java
package com.acme.shop.order;

public record OrderCompleted(
        String orderId,
        String customerId
) {
}
~~~

Đặt event trong base package `com.acme.shop.order` giúp nó thuộc API mặc định của module. Nếu dự án tổ chức event trong package con, hãy công bố package đó bằng named interface và cho phép subscriber phụ thuộc vào giao diện tương ứng.

Không nên để subscriber import một event class trong package `order.internal`. Package nội bộ là chi tiết triển khai; module phát cần công bố hợp đồng event mà subscriber được phép sử dụng.

## 3. Publisher phát event

Module `order` phát event sau khi nghiệp vụ hoàn tất:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.order.OrderCompleted;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
class CompleteOrderService {

    private final ApplicationEventPublisher events;

    CompleteOrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    void complete(String orderId, String customerId) {
        // Lưu trạng thái đơn hàng hoàn tất.
        events.publishEvent(new OrderCompleted(orderId, customerId));
    }
}
~~~

`ApplicationEventPublisher` là API của Spring để công bố application event. Publisher không cần biết module nào sẽ lắng nghe sự kiện. Các subscriber có thể được thêm độc lập, miễn là hợp đồng event và dependency kiến trúc vẫn hợp lệ.

Trong ứng dụng thực tế, chỉ phát event sau khi trạng thái nghiệp vụ được cập nhật thành công. Nếu listener cần xử lý sau khi transaction commit, chọn listener annotation phù hợp với semantics giao dịch của ứng dụng.

## 4. Thêm subscriber tạo dependency mới

Giả sử module `shipping` đăng ký listener:

~~~java
package com.acme.shop.shipping.internal;

import com.acme.shop.order.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderCompletedListener {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Tạo yêu cầu giao hàng từ thông tin đơn đã hoàn tất.
    }
}
~~~

`@ApplicationModuleListener` là listener dành cho tích hợp giữa application module của Spring Modulith. Listener khai báo rõ kiểu event mà module nhận. Việc tham chiếu `OrderCompleted` tạo dependency từ `shipping` đến module `order`.

Sau khi thêm subscriber, graph có thêm cạnh:

~~~text
shipping ─────> order
          event contract
~~~

Đây là thay đổi kiến trúc dù không có dòng code nào gọi trực tiếp `CompleteOrderService` từ `shipping`.

## 5. Vì sao cần kiểm tra graph sau khi thêm subscriber?

Thêm subscriber có thể gây ra một số thay đổi:

- Tạo dependency mới đến module sở hữu event.
- Làm một dependency trước đây không tồn tại trở thành dependency cần được cho phép.
- Tạo vòng phụ thuộc nếu module phát đã phụ thuộc vào subscriber theo một hướng khác.
- Làm lộ việc event type đang nằm trong package nội bộ thay vì API được công bố.
- Làm thay đổi các giả định về thứ tự và thời điểm xử lý event ở runtime.

Ví dụ, ban đầu `order` gọi API của `shipping` để yêu cầu giao hàng:

~~~text
order ─────> shipping
       direct API call
~~~

Sau đó, `shipping` được thêm listener cho `OrderCompleted` của `order`:

~~~text
order ─────> shipping
  ^              |
  |              |
  └──────────────┘
    event dependency
~~~

Dependency graph hiện có chu trình `order` và `shipping`. Dù một chiều dùng lời gọi trực tiếp và chiều còn lại dùng event, cả hai vẫn là dependency giữa application module. Event giúp giảm coupling ở runtime, nhưng không làm biến mất dependency kiến trúc.

## 6. Kiểm tra graph bằng ApplicationModules.verify()

Tạo một architecture test để kiểm tra mô hình module:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleDependencyGraph() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.of(ShopApplication.class)` xây dựng mô hình từ package và metadata của ứng dụng. `verify()` kiểm tra các quy tắc kiến trúc, trong đó có dependency cycle và truy cập không hợp lệ vào package nội bộ.

Khi thêm subscriber, hãy chạy test này trong cùng thay đổi. Nếu subscriber tạo cạnh mới khiến graph có chu trình hoặc vi phạm quy tắc dependency, kiểm tra sẽ thất bại và cung cấp thông tin để xác định module liên quan.

Đặt test trong source set test thông thường và giữ nó trong CI. Như vậy, mọi thay đổi listener hoặc event contract đều được kiểm tra cùng các dependency khác của ứng dụng.

## 7. Kiểm tra tập vi phạm để có báo cáo chi tiết

Nếu muốn thu thập thông điệp trước khi làm test thất bại, dùng `detectViolations()`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;

class ModuleGraphReportTest {

    @Test
    void reportsViolationsAfterSubscriberChanges() {
        Violations violations =
                ApplicationModules.of(ShopApplication.class)
                        .detectViolations();

        if (violations.hasViolations()) {
            violations.getMessages().forEach(System.err::println);
        }

        violations.throwIfPresent();
    }
}
~~~

`detectViolations()` trả về `Violations` để chương trình có thể đọc danh sách lỗi. `throwIfPresent()` ném kết quả nếu có vi phạm, khiến test thất bại sau khi thông điệp đã được ghi ra log.

Nếu chỉ cần kiểm tra thành công/thất bại, `verify()` thường ngắn gọn hơn. Nếu cần báo cáo, lọc hoặc xử lý kết quả, `detectViolations()` linh hoạt hơn.

## 8. allowedDependencies cũng cần phản ánh event dependency

Nếu module tiêu thụ giới hạn dependency bằng `allowedDependencies`, event dependency cần tuân thủ allowlist đó.

Ví dụ, module `shipping` chỉ được phép phụ thuộc vào module `order`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order"
)
package com.acme.shop.shipping;
~~~

Nếu event được công bố trong named interface `events`, module có thể giới hạn dependency vào giao diện đó:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order::events"
)
package com.acme.shop.shipping;
~~~

Package event của module `order` cần được đánh dấu:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
~~~

Khi đó, subscriber import event từ `com.acme.shop.order.events`. Tên trong `allowedDependencies` phải khớp module identifier và named interface identifier thực tế.

Không nên mở toàn bộ dependency của module chỉ để một listener mới vượt qua verification. Hãy công bố đúng hợp đồng event mà subscriber cần.

## 9. Thêm subscriber mới mà không tạo cycle

Giả sử `order` phát `OrderCompleted` và hai module `shipping` cùng `analytics` lắng nghe:

~~~text
              ┌──────────────> shipping
              |
order ──event─┤
              |
              └──────────────> analytics
~~~

Dependency graph:

~~~text
shipping ─────> order
analytics ────> order
~~~

Hai module tiêu thụ cùng phụ thuộc vào hợp đồng event của `order`. Nếu `order` không phụ thuộc ngược lại vào `shipping` hoặc `analytics`, graph vẫn không có chu trình chỉ vì có thêm subscriber.

Đây là cách mở rộng thường phù hợp: publisher công bố một event contract ổn định, nhiều subscriber xử lý các phản ứng riêng trong module của mình. Publisher không cần biết danh sách subscriber.

Tuy vậy, cần kiểm tra các dependency khác trong graph. Một cạnh event mới có thể khép lại chu trình đã hình thành từ các lời gọi API hoặc event khác.

## 10. Khi graph có cycle, nên xử lý thế nào?

Khi verification báo cycle, hãy lần theo từng cạnh và xác định hợp đồng tạo ra dependency:

1. Xác định module publisher và event type mà subscriber đang tham chiếu.
2. Tìm dependency ngược từ publisher đến subscriber, có thể đến từ constructor injection, API call hoặc một listener khác.
3. Xác định hai module có thực sự cần phụ thuộc hai chiều hay đang chia sẻ trách nhiệm chưa rõ.
4. Xem xét chuyển event contract đến một module sở hữu hợp đồng phù hợp, hoặc tách một năng lực chung thành module riêng nếu có lý do nghiệp vụ.
5. Xem xét thay lời gọi ngược bằng event nếu nghiệp vụ phù hợp và semantics nhất quán.
6. Chạy lại `ApplicationModules.verify()` sau khi điều chỉnh.

Ví dụ, nếu `order` cần biết kết quả vận chuyển và `shipping` cần biết đơn hàng hoàn tất, có thể cần một hợp đồng event rõ ràng cho mỗi chiều. Tuy nhiên, hai chiều event vẫn tạo hai dependency trong graph. Chỉ đổi cách truyền thông điệp không tự loại bỏ cycle; cần xem lại quyền sở hữu dữ liệu và trách nhiệm module.

Một lựa chọn khác là đưa một event contract dùng chung vào module riêng, nhưng module đó phải có trách nhiệm và API hợp lý. Không tạo module `common` chỉ để né kiểm tra cycle.

## 11. Graph verification không thay thế kiểm thử event delivery

`ApplicationModules.verify()` kiểm tra cấu trúc dependency của ứng dụng. Nó không khởi chạy toàn bộ nghiệp vụ để chứng minh listener thực sự nhận và xử lý event thành công.

Hai nhóm kiểm thử có mục tiêu khác nhau:

| Kiểm thử | Câu hỏi được trả lời |
| --- | --- |
| Application module verification | Subscriber có tạo dependency hợp lệ không? Graph có cycle hoặc truy cập package nội bộ không? |
| Spring context test | Listener và publisher có được đăng ký trong application context không? |
| Event integration test | Khi publisher phát event, subscriber có nhận và thực hiện phản ứng mong đợi không? |
| Transaction test | Listener được kích hoạt ở thời điểm transaction phù hợp không? |

Với `@ApplicationModuleListener`, cần chú ý listener có thể được thực thi bất đồng bộ và gắn với transaction semantics của Spring Modulith. Integration test phải chờ hoặc đồng bộ theo cơ chế phù hợp, tránh giả định rằng xử lý listener hoàn tất ngay khi `publishEvent()` trả về.

Hãy kiểm thử graph như một architecture test riêng. Sau đó, viết integration test cho hành vi event quan trọng, bao gồm dữ liệu đầu vào, kết quả subscriber và lỗi xử lý nếu nghiệp vụ yêu cầu.

## 12. Quy trình kiểm thử khi thêm subscriber

Thực hiện theo trình tự:

1. Xác định event contract và module sở hữu event.
2. Đặt event trong base package hoặc named interface được công bố.
3. Thêm subscriber trong package của module tiêu thụ.
4. Xác nhận module tiêu thụ được phép phụ thuộc vào publisher qua `allowedDependencies` nếu có allowlist.
5. Chạy `ApplicationModules.verify()` để kiểm tra graph mới.
6. Nếu verification thất bại, đọc cycle hoặc dependency violation và xác định cạnh mới.
7. Điều chỉnh ranh giới hoặc hợp đồng nếu cần rồi chạy lại verification.
8. Chạy Spring context/integration test để xác nhận listener được đăng ký và event được xử lý.
9. Giữ architecture test trong CI để lần thêm subscriber tiếp theo cũng được kiểm tra.

Ví dụ graph trước và sau:

~~~text
Trước:
order ─────> inventory

Thêm listener:
shipping ───> order

Graph sau:
shipping ───> order ───> inventory
~~~

Nếu không có cạnh quay lại `shipping`, graph này vẫn không có cycle. Nếu `inventory` hoặc `order` có dependency ngược đến `shipping`, verification sẽ phát hiện chu trình tương ứng.

## 13. Những nhầm lẫn thường gặp

**Cho rằng subscriber không tạo dependency vì publisher không gọi subscriber.** Subscriber cần kiểu event của publisher, do đó vẫn có dependency kiến trúc từ subscriber đến module sở hữu event.

**Đọc chiều event flow như chiều dependency.** Event chạy từ publisher đến subscriber; dependency hướng từ subscriber đến module cung cấp event contract.

**Cho rằng event-based dependency không thể tạo cycle.** Event giảm coupling trực tiếp ở runtime nhưng vẫn tạo cạnh trong graph module. Nhiều cạnh event có thể tạo chu trình.

**Đặt event trong package internal.** Subscriber không nên phụ thuộc vào chi tiết triển khai. Hãy công bố event ở base package hoặc named interface.

**Cho rằng component scan quyết định dependency được phép.** Scan đăng ký listener bean. Spring Modulith kiểm tra dependency và ranh giới module.

**Cho rằng verify() chứng minh listener chạy đúng.** Verification kiểm tra graph kiến trúc; integration test mới xác nhận event được giao và xử lý đúng.

**Mở allowlist quá rộng để bỏ qua lỗi.** Hãy khai báo dependency đến đúng module hoặc named interface cần dùng.

## 14. Checklist trước khi merge thay đổi subscriber

- [ ] Event type thuộc API được công bố của module phát.
- [ ] Subscriber nằm trong package của module tiêu thụ.
- [ ] Dependency graph được hiểu theo chiều subscriber phụ thuộc publisher.
- [ ] `allowedDependencies` cho phép đúng module hoặc named interface cần thiết.
- [ ] `ApplicationModules.verify()` chạy thành công sau khi thêm listener.
- [ ] Không xuất hiện dependency cycle mới.
- [ ] Không có import từ package internal của module khác.
- [ ] Listener được đăng ký trong Spring context.
- [ ] Integration test xác nhận event được xử lý và xét đến async/transaction semantics.
- [ ] Architecture test được giữ trong CI.

## 15. Kết luận

Thêm subscriber là thay đổi dependency graph của Spring Modulith. Subscriber phụ thuộc vào module sở hữu event contract, vì nó cần kiểu event để đăng ký lắng nghe. Cạnh mới có thể làm graph xuất hiện dependency không được cho phép hoặc tạo cycle với các cạnh trực tiếp và event-based đã có.

Hãy công bố event trong API của module phát, thêm listener trong module tiêu thụ và chạy `ApplicationModules.verify()` sau thay đổi. Dùng `detectViolations()` nếu cần thu thập báo cáo trước khi làm test thất bại. Cuối cùng, kết hợp architecture test với integration test để kiểm tra cả tính hợp lệ của graph lẫn hành vi xử lý event ở runtime.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — `ApplicationModuleListener` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html)
