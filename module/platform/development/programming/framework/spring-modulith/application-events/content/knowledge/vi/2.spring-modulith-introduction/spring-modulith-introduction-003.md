# Event trong modular monolith

## 1. Vì sao một modular monolith cần event?

**Modular monolith** là một ứng dụng được triển khai thành một khối chạy thống nhất, nhưng mã nguồn và quy tắc nghiệp vụ được chia thành các **module có ranh giới rõ ràng**. Chẳng hạn hệ thống bán hàng có thể gồm `orders` (đơn hàng), `inventory` (tồn kho), `payments` (thanh toán) và `notifications` (thông báo). Các module dùng chung tiến trình JVM, song mỗi module phải quản lý dữ liệu và hành vi thuộc trách nhiệm của mình.

Giả sử khi đơn hàng được xác nhận, hệ thống cần cập nhật một báo cáo và gửi email. Cách gọi trực tiếp dễ viết ban đầu:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    orderRepository.confirm(orderId);
    notificationService.sendConfirmation(orderId);
    reportingService.recordConfirmedOrder(orderId);
}
~~~

Nếu `notificationService` và `reportingService` nằm ở module khác, `orders` phải biết và phụ thuộc vào từng dịch vụ đó. Khi thêm chức năng mới (tích điểm, phân tích hành vi), mã `orders` lại phải sửa. Việc gọi trực tiếp còn khiến luồng xử lý dài hơn, khó tách module để kiểm thử riêng và dễ phát sinh vòng phụ thuộc.

**Application event** giải quyết nhu cầu thông báo rằng **một sự kiện nghiệp vụ đã xảy ra**. Module phát sự kiện không cần liệt kê module nhận; module quan tâm tự đăng ký listener:

~~~mermaid
flowchart LR
    C["Yêu cầu xác nhận đơn"] --> O["orders<br/>Xác nhận và lưu đơn"]
    O --> E(["OrderConfirmed"])
    E --> N["notifications<br/>Gửi xác nhận"]
    E --> R["reporting<br/>Cập nhật báo cáo"]
    E --> L["loyalty<br/>Cộng điểm"]
~~~

Ở đây, `orders` chỉ phát biểu một sự thật nghiệp vụ: "Đơn hàng đã được xác nhận". Cách gửi email, cập nhật báo cáo hay cộng điểm thuộc về module tiêu thụ sự kiện. Spring Modulith tổ chức cách giao tiếp này trên nền **Spring Application Events** và bổ sung khả năng giao sự kiện đáng tin cậy.

Sau bài này, bạn cần có khả năng:

- Nhận diện lúc nào giao tiếp giữa module nên dùng event và lúc nào cần lời gọi trực tiếp.
- Thiết kế một event công khai, ổn định và không làm lộ chi tiết bên trong module nguồn.
- Phân biệt thời điểm xử lý của `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener`.
- Hiểu vì sao xử lý bất đồng bộ cần thêm cơ chế lưu vết, thử lại và chống xử lý trùng.

## 2. Event không đồng nghĩa với lời gọi hàm bất đồng bộ

Một **command** diễn đạt ý định yêu cầu bên nhận làm việc gì (ví dụ `ReserveStock`); một **event** mô tả sự thật đã xảy ra (ví dụ `OrderConfirmed`). Hai khái niệm khác nhau ở hợp đồng giao tiếp:

| Khía cạnh | Gọi service trực tiếp | Phát application event |
| --- | --- | --- |
| Ý nghĩa | Yêu cầu một hành vi cụ thể | Thông báo một sự kiện đã xảy ra |
| Bên nhận | Bên gọi biết rõ API của bên nhận | Bên phát không cần biết có bao nhiêu listener |
| Kết quả trả về | Có thể nhận kết quả hoặc lỗi ngay | Không dùng làm API trả kết quả đồng bộ |
| Phụ thuộc | Thường phụ thuộc trực tiếp vào service/module đích | Phụ thuộc vào kiểu event công khai và cơ chế giao nhận |
| Tính nhất quán | Có thể cùng một lời gọi/transaction | Phụ thuộc kiểu listener, có thể nhất quán sau |

Event **không tự động** đồng nghĩa với bất đồng bộ: `ApplicationEventPublisher.publishEvent(...)` của Spring thông thường sẽ chuyển sự kiện đến các `@EventListener` đồng bộ ngay trong luồng hiện tại. Event cũng không tự động là message trên Kafka/RabbitMQ; khi chỉ dùng Spring application event, các listener chạy **trong cùng ứng dụng**, không phải một dịch vụ từ xa.

**Nên gọi trực tiếp** khi chức năng nguồn bắt buộc cần kết quả tức thời để quyết định có hoàn thành nghiệp vụ hay không, ví dụ phải xác nhận đủ hạn mức thanh toán trước khi chấp nhận đơn. **Nên cân nhắc event** khi bên khác phản ứng với một kết quả nghiệp vụ đã hoàn tất, như phát hành thông báo, cập nhật bảng đọc hoặc ghi nhận chỉ số.

Đừng biến mọi lời gọi giữa module thành event: một chuỗi event nhiều bước để thay thế thao tác cần trả kết quả ngay sẽ khiến luồng lỗi khó hiểu và khó bảo đảm tính nhất quán.

## 3. Thiết kế event thành hợp đồng giữa các module

Một event tốt cần:

1. **Đặt tên ở thì đã xảy ra:** `OrderConfirmed`, `PaymentCaptured`, `StockReserved`. Tránh kiểu tên ra lệnh như `SendConfirmationEmail` nếu đây thực sự là event nghiệp vụ.
2. **Dữ liệu tối thiểu và bất biến:** truyền ID cùng những giá trị mà listener thực sự cần; không truyền entity JPA đang được quản lý, repository hay Spring bean.
3. **Thuộc API công khai của module phát:** module khác chỉ import kiểu event được phép sử dụng. Với Spring Modulith, kiểu nằm ở package API/module root hoặc một *named interface* được công khai rõ ràng, tránh import vào package nội bộ.
4. **Có ý nghĩa ổn định:** đổi tên trường, xóa trường hay thay đổi ngữ nghĩa của event sẽ ảnh hưởng tất cả consumer; cân nhắc version khi hợp đồng được lưu bền hoặc phát ra hệ thống ngoài.

Ví dụ dùng Java `record` (Java 17 trở lên):

~~~java
// com.example.shop.orders.OrderConfirmed
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID orderId,
        Instant occurredAt
) {}
~~~

`OrderConfirmed` mang dữ liệu đơn giản, không chứa `OrderEntity`. Nhờ vậy module khác không bị lệ thuộc vào mapping ORM và vòng đời persistence của `orders`. Trong ứng dụng đòi hỏi audit, tracing hoặc idempotency chi tiết, có thể bổ sung `eventId`/`correlationId`; chỉ thêm khi có mục đích rõ ràng và duy trì hợp đồng ổn định.

## 4. Ví dụ: module orders phát sự kiện, notifications lắng nghe

Giả sử mỗi thư mục package cấp một tương ứng một application module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderConfirmed.java       # Event thuộc API module
│   ├── OrderService.java         # Nghiệp vụ xác nhận đơn
│   └── internal/                # Repository/entity không công khai
└── notifications/
    ├── ConfirmationListener.java
    └── internal/                # Nghiệp vụ lưu/gửi thông báo
~~~

Module nguồn thay đổi trạng thái đơn hàng và phát event trong transaction:

~~~java
package com.example.shop.orders;

import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher events,
                        Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.confirm(); // Kiểm tra quy tắc và chuyển trạng thái nghiệp vụ
        events.publishEvent(new OrderConfirmed(
                order.getId(), Instant.now(clock)));
    }
}
~~~

`OrderRepository` và `Order` đại diện cho các kiểu thuộc nội bộ `orders`; mã minh họa giả định các bean/repository và `Clock` đã được cấu hình. Với JPA, thay đổi của entity được theo dõi và flush/commit bởi transaction hiện tại. **Lời gọi `publishEvent` không có nghĩa database đã commit**: tùy kiểu listener, việc tiêu thụ có thể diễn ra ngay hoặc đợi commit.

Module `notifications` chỉ cần biết kiểu `OrderConfirmed`:

~~~java
package com.example.shop.notifications;

import com.example.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class ConfirmationListener {
    private final NotificationService notifications;

    public ConfirmationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        notifications.sendConfirmationOnce(event.orderId());
    }
}
~~~

Phương thức `sendConfirmationOnce` ở đây là **hợp đồng nghiệp vụ minh họa**, phải được hiện thực bằng cơ chế chống trùng phù hợp; Spring Modulith không tự chống việc gửi email hai lần. Các kiểu nội bộ của `notifications` không cần công khai cho `orders`.

Kết quả quan trọng về cấu trúc: `notifications` có thể phụ thuộc vào **API event của `orders`**, nhưng `orders` không cần phụ thuộc ngược vào `notifications`. Không nên đặt event vào package nội bộ chỉ để hai module dùng được bằng cách mở rộng quyền truy cập tùy tiện.

## 5. Event chạy ở thời điểm nào so với transaction?

Thời điểm listener thực thi quyết định một yêu cầu thất bại có làm rollback đơn hàng hay không:

| Cách nhận | Thời điểm và luồng thực thi điển hình | Transaction và tác động khi lỗi |
| --- | --- | --- |
| `@EventListener` | Ngay lúc publish, đồng bộ theo mặc định | Nếu chạy trong transaction nguồn, exception có thể lan ra và làm rollback transaction nguồn. |
| `@TransactionalEventListener` | Mặc định `AFTER_COMMIT`, sau khi transaction nguồn commit thành công | Không tham gia transaction nguồn đã commit; không tự tạo transaction mới cho listener. |
| `@ApplicationModuleListener` | Listener transaction sau commit, bất đồng bộ (`@Async`) | Chạy với transaction mới (`REQUIRES_NEW`); thất bại không thể rollback transaction nguồn đã commit. |

Ví dụ khi chỉ cần xử lý sau commit:

~~~java
@Component
class AuditListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        // Đọc trạng thái đơn đã commit, hoặc kích hoạt tác vụ phụ
    }
}
~~~

Điểm dễ nhầm:

- `@TransactionalEventListener` mặc định **không xử lý** event được publish ngoài transaction đang hoạt động (trừ khi cấu hình `fallbackExecution = true`).
- `AFTER_COMMIT` không có nghĩa "tự động có transaction ghi mới". Khi listener cần cập nhật database, hãy dùng transaction độc lập phù hợp; đây là một lý do sử dụng `@ApplicationModuleListener`.
- `@ApplicationModuleListener` là annotation do **Spring Modulith** cung cấp, kết hợp `@Async`, `@TransactionalEventListener` và `@Transactional(propagation = REQUIRES_NEW)`. Để thực thi bất đồng bộ theo mong muốn, cần bật/cấu hình hỗ trợ async (`@EnableAsync` nếu cấu hình ứng dụng chưa bật) và executor phù hợp.
- Khi xử lý bất đồng bộ, thứ tự hoàn tất của nhiều listener không được bảo đảm. Code consumer không được giả định listener khác đã chạy xong.

Sơ đồ thời gian với `@ApplicationModuleListener`:

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders
    participant DB as Database
    participant Events as Spring Events
    participant Notifications as notifications
    Client->>Orders: confirm(orderId)
    Orders->>DB: Thay đổi đơn trong transaction A
    Orders->>Events: publish(OrderConfirmed)
    Orders->>DB: COMMIT A
    DB-->>Events: Commit thành công
    Events-->>Notifications: Chuyển event sau commit
    Notifications->>DB: Transaction B (REQUIRES_NEW)
    Notifications->>DB: COMMIT B
~~~

Nếu transaction A rollback, listener `AFTER_COMMIT` không chạy. Nếu transaction B hoặc việc gửi thông báo thất bại, đơn đã xác nhận vẫn được giữ nguyên; cần cơ chế phục hồi bên nhận.

## 6. Độ tin cậy: xử lý sau commit vẫn có thể mất event

Chỉ ghép `@Async` và `@TransactionalEventListener` chưa bảo đảm giao sự kiện thành công. Ví dụ database đã commit, nhưng JVM dừng đột ngột trước khi tác vụ listener được thực thi. Hoặc listener bị lỗi mạng khi gửi email. Event ở bộ nhớ không tự trở thành hàng đợi bền vững.

**Event Publication Registry** của Spring Modulith giúp ghi lại việc công bố event dành cho các transactional listener được theo dõi:

1. Khi `orders` publish event trong transaction, registry ghi **một bản ghi publication cho mỗi listener phù hợp**, cùng transaction nguồn.
2. Nếu transaction nguồn rollback, cả thay đổi đơn và các publication tương ứng rollback.
3. Sau commit, listener xử lý event. Registry ghi nhận hoàn tất khi việc xử lý thành công theo cơ chế của phiên bản/cấu hình đang dùng.
4. Nếu xử lý lỗi hoặc tiến trình dừng, publication chưa hoàn tất/đã lỗi được giữ để hệ thống theo dõi và **chủ động khôi phục hoặc resubmit**.

Để lưu bền, ứng dụng cần cấu hình một implementation registry thích hợp (ví dụ starter JDBC/JPA) cùng cơ sở dữ liệu/transaction hỗ trợ. Spring Modulith không tự tạo kho lưu trữ bền vững chỉ vì project có `@ApplicationModuleListener`. Cơ chế resubmit cần được cấu hình, kích hoạt hoặc vận hành theo phiên bản đang dùng; **đừng mặc định rằng lỗi sẽ được retry vô hạn và tự động**.

Registry giảm nguy cơ mất publication nhưng **không tạo bảo đảm exactly-once cho tác động bên ngoài**. Một email có thể đã gửi thành công trước khi ứng dụng kịp ghi nhận listener hoàn tất; khi phục hồi, listener có thể được gọi lại. Bởi vậy:

- **Idempotency:** với tác động lưu database, đặt khóa duy nhất như `(order_id, notification_type)` hoặc lưu `eventId` đã xử lý, kiểm tra và cập nhật trong transaction phù hợp.
- **Tác động bên ngoài:** đặt khóa idempotency tại dịch vụ downstream nếu họ hỗ trợ, hoặc quản lý trạng thái gửi (outbox/dispatch record) cùng retry có kiểm soát.
- **Quan sát:** theo dõi publication chưa xử lý, số lần thất bại, thời gian trễ và nguyên nhân lỗi; có quy trình khôi phục sau sự cố.
- **Tách lỗi nghiệp vụ:** phân biệt lỗi tạm thời có thể retry (mạng, timeout) và lỗi dữ liệu không thể phục hồi bằng retry.

Nếu cần trao đổi với **dịch vụ ở tiến trình khác**, phải bổ sung tích hợp message broker hay externalization thích hợp. Application event trong modular monolith trước hết phục vụ ranh giới **module nội bộ**.

## 7. Những lỗi thiết kế thường gặp

**Đưa entity JPA vào event.** Listener vô tình truy cập lazy relationship sau transaction hoặc phụ thuộc cấu trúc private của module phát. Hãy phát ID/value object độc lập và tự nạp dữ liệu cần thiết qua API hợp lệ.

**Phát event để hỏi kết quả bắt buộc.** Ví dụ `orders` phải đợi xem có đủ hàng để xác nhận, nhưng lại phát `CheckStock` rồi mong nhận đáp án tức thì. Đây là command/query cần hợp đồng đồng bộ hoặc một quy trình trạng thái dài hạn được thiết kế riêng.

**Cho rằng publish đồng nghĩa commit.** Listener đồng bộ có thể chạy trong transaction còn mở, nhìn dữ liệu chưa commit, ném exception khiến transaction nguồn rollback.

**Cho rằng listener after-commit không bao giờ bị mất.** Nếu không có publication registry bền vững hay cơ chế tương đương, sự cố giữa commit và xử lý vẫn có thể làm mất tác vụ.

**Thiết kế listener không idempotent.** Retry, khởi động lại hoặc xử lý trùng có thể gây gửi email, trừ tiền hoặc cộng điểm nhiều lần.

**Giấu dependency bằng tên event chung chung.** Các tên `SomethingChanged`, `ProcessThisEvent` không phản ánh sự thật nghiệp vụ; sau này consumer phải đoán ý nghĩa từ payload.

## 8. Cách kiểm thử giao tiếp giữa module

Kiểm thử nên chia thành ba mức, vì mỗi mức trả lời một câu hỏi khác nhau:

| Mức | Cần xác minh | Ví dụ |
| --- | --- | --- |
| Unit test của publisher | Khi xác nhận đơn hợp lệ, phát đúng `OrderConfirmed` với ID tương ứng | Dùng mock `ApplicationEventPublisher` và assert event |
| Kiểm thử tích hợp module | Listener nhận event sau commit, cập nhật dữ liệu module nhận, không xử lý khi rollback | Tạo đơn trong DB kiểm thử, chờ kết quả async có giới hạn thời gian |
| Kiểm thử lỗi và phục hồi | Publication được lưu bền; listener lỗi vẫn có thể resubmit; tác động không bị nhân đôi | Gây lỗi tạm thời rồi chạy đường phục hồi và kiểm tra khóa idempotency |

Spring Modulith có công cụ kiểm tra cấu trúc module:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {
    @Test
    void modulesRespectTheirBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` giúp phát hiện các phụ thuộc module bất hợp lệ (như vòng phụ thuộc hoặc truy cập package nội bộ theo quy tắc Modulith). Nó **không thay thế** kiểm thử event, transaction, retry hay idempotency. Với listener bất đồng bộ, tránh assert ngay sau khi publish: kiểm tra kết quả theo cơ chế chờ có timeout, và bố trí transaction của bài test để commit thực sự xảy ra trước khi đợi listener `AFTER_COMMIT`.

## 9. Bài thực hành: thêm module loyalty mà không sửa orders

Tạo module `loyalty` với listener nhận `OrderConfirmed`. Mỗi đơn xác nhận hợp lệ được cộng 10 điểm **đúng một lần**, kể cả khi cùng event được gửi hai lần.

1. Giữ `OrderConfirmed` trong API của `orders` và không inject `LoyaltyService` vào `OrderService`.
2. Dùng `@ApplicationModuleListener` để cập nhật điểm trong transaction của `loyalty`.
3. Thiết kế bảng/log có ràng buộc unique trên `orderId` cho nghiệp vụ cộng điểm; thực hiện kiểm tra và ghi điểm theo transaction an toàn trước xử lý đồng thời.
4. Thử xác nhận đơn thành công, rollback đơn trước commit, gửi lại event và gây lỗi listener một lần rồi phục hồi.
5. Chạy kiểm thử ranh giới module và giải thích vì sao `orders` không cần biết `loyalty` tồn tại.

**Tự kiểm tra:** Nếu email gửi lỗi sau khi đơn đã commit, có nên rollback đơn không? Điều gì xảy ra nếu event được xử lý hai lần? Với bài toán thông báo phụ, giao tiếp sau commit và idempotency thường phù hợp hơn việc buộc đơn hàng phụ thuộc vào email.

## 10. Ghi nhớ để áp dụng

Trong Spring Modulith, event là **hợp đồng diễn tả sự kiện nghiệp vụ giữa các module**, giúp module nguồn tập trung vào trách nhiệm của mình và cho phép các module khác phản ứng độc lập. Spring Application Events là cơ chế phát/nhận; `@ApplicationModuleListener` cung cấp mẫu xử lý bất đồng bộ sau commit trong transaction riêng; Event Publication Registry hỗ trợ lưu dấu và phục hồi việc giao event. Chất lượng thiết kế vẫn phụ thuộc vào ranh giới module, ý nghĩa event, chiến lược nhất quán và khả năng xử lý trùng của từng consumer.

**Đọc thêm (tài liệu chính thức):**

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Framework — Task Execution and Scheduling (`@Async`)](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
