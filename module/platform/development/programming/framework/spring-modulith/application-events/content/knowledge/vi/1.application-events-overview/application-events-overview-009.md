# Lợi ích của event trong Spring Modulith

## 1. Event giải quyết vấn đề gì?

Một ứng dụng Spring Boot được tổ chức theo Spring Modulith thường có nhiều module nghiệp vụ: **Đơn hàng**, **Thanh toán**, **Kho hàng**, **Thông báo**, **Điểm thưởng**. Các module cùng chạy trong một ứng dụng nhưng cần có ranh giới rõ ràng để dễ phát triển, kiểm thử và bảo trì.

Giả sử khách hàng đặt hàng thành công. Hệ thống cần lưu đơn hàng, gửi email xác nhận, ghi lịch sử hoạt động và cộng điểm thưởng. Nếu module Đơn hàng gọi trực tiếp từng module còn lại, số phụ thuộc tăng lên theo mỗi yêu cầu mới:

~~~text
OrderService.placeOrder()
  -> orderRepository.save(...)
  -> notificationService.sendConfirmation(...)
  -> loyaltyService.addPoints(...)
  -> auditService.record(...)
~~~

Đoạn xử lý đơn hàng phải biết những công việc sau khi đặt hàng là gì và phải gọi API của các module tương ứng. Khi thêm một hành vi mới, lập trình viên thường phải quay lại sửa mã của Đơn hàng.

Với **application event**, module Đơn hàng chỉ công bố sự kiện nghiệp vụ **OrderPlaced** (đơn hàng đã được tạo). Các module quan tâm tự đăng ký listener:

~~~mermaid
flowchart LR
    O["Module Đơn hàng"] -->|"publish OrderPlaced"| E(("Application event"))
    E --> N["Module Thông báo"]
    E --> L["Module Điểm thưởng"]
    E --> A["Module Kiểm toán"]
~~~

**Event là thông báo về một sự thật đã xảy ra trong nghiệp vụ**, chẳng hạn OrderPlaced, PaymentReceived hoặc ShipmentDispatched. Nó khác với command (yêu cầu thực hiện hành động), chẳng hạn SendConfirmationEmail. Sự kiện cho biết *điều gì đã xảy ra*; bên nhận tự quyết định *phản ứng thế nào*.

Trong phạm vi này, event của Spring Modulith là **Spring application event được công bố và nhận bên trong cùng tiến trình ứng dụng**. Việc dùng event không mặc nhiên tạo message broker, hệ thống phân tán hay bảo đảm giao sự kiện bền vững. Những khả năng đó cần cơ chế và cấu hình tương ứng.

## 2. Các lợi ích chính

### 2.1. Giảm phụ thuộc giữa các module

Không dùng event, module Đơn hàng có thể phải phụ thuộc trực tiếp vào các interface của Thông báo, Điểm thưởng và Kiểm toán. Càng nhiều lời gọi, module càng hiểu sâu về cách các module khác hoạt động.

Khi dùng event:

- **Publisher** chỉ biết hợp đồng sự kiện OrderPlaced và cách công bố nó qua ApplicationEventPublisher.
- **Listener** chỉ cần hiểu dữ liệu được công khai trong hợp đồng sự kiện.
- Publisher không cần import hoặc gọi lớp service cụ thể của các listener.
- Module mới có thể đăng ký nhận OrderPlaced mà không phải chỉnh sửa logic tạo đơn.

Điều này giúp bảo vệ ranh giới module: **Đơn hàng sở hữu quyết định khi nào một đơn hàng được tạo thành công; các module khác sở hữu cách xử lý hệ quả của sự kiện đó**.

Giảm phụ thuộc không có nghĩa loại bỏ mọi phụ thuộc. Các module tiêu thụ vẫn phụ thuộc vào **hợp đồng event** của module phát hành. Vì thế hợp đồng event cần ổn định, có ý nghĩa nghiệp vụ và tránh lộ cấu trúc nội bộ.

### 2.2. Dễ mở rộng hành vi mà không sửa luồng nghiệp vụ gốc

Sau khi triển khai OrderPlaced, hệ thống có thể bổ sung listener để ghi nhật ký, phát thông báo đẩy hoặc cập nhật báo cáo. Mỗi tính năng nằm trong module chịu trách nhiệm về nó.

Ví dụ, khi thêm chương trình khách hàng thân thiết:

1. Module Đơn hàng tiếp tục công bố OrderPlaced như trước.
2. Module Điểm thưởng thêm listener cho OrderPlaced.
3. Listener của Điểm thưởng tính và ghi điểm theo quy tắc riêng.
4. Kiểm thử module Đơn hàng không cần chứa logic tính điểm thưởng.

Cách mở rộng này đặc biệt hữu ích với **hành vi phụ trợ phát sinh sau một sự kiện nghiệp vụ**, chẳng hạn thông báo, audit, thống kê, chỉ mục tìm kiếm và projection phục vụ đọc dữ liệu.

### 2.3. Đặt logic đúng nơi chịu trách nhiệm

Event cho phép mô tả luồng xử lý bằng ngôn ngữ nghiệp vụ:

- OrderPlaced: đơn hàng đã được tạo.
- PaymentCompleted: thanh toán đã thành công.
- ShipmentHandedOver: kiện hàng đã được bàn giao.

Module phát hành chịu trách nhiệm xác định sự thật nghiệp vụ, còn module nghe sự kiện xử lý chính sách của mình. Nhờ đó không phải tập trung tất cả quyết định của nhiều module trong một service điều phối khổng lồ.

Đây cũng là lợi ích khi bảo trì: muốn thay đổi cách gửi email thì tìm trong module Thông báo; muốn thay đổi chính sách cộng điểm thì tìm trong module Điểm thưởng.

### 2.4. Phân tách xử lý chính với tác vụ sau commit

Một lỗi thường gặp là gửi email hoặc gọi hệ thống ngoài ngay trong transaction tạo đơn. Giả sử email đã gửi nhưng transaction lưu đơn bị rollback: khách hàng nhận xác nhận cho một đơn không tồn tại.

Spring hỗ trợ **transactional event listener** để chỉ bắt đầu xử lý sau khi transaction phát hành đã commit. Spring Modulith cung cấp annotation **@ApplicationModuleListener** cho mô hình listener bất đồng bộ, được kích hoạt sau commit và có transaction riêng cho quá trình xử lý của listener.

Lợi ích của cách này là:

- Tác vụ phụ trợ chỉ được kích hoạt sau khi nghiệp vụ chính commit thành công.
- Listener có thể chạy tách khỏi luồng xử lý request ban đầu.
- Lỗi ở listener sau commit không làm rollback transaction tạo đơn đã commit.

**Lưu ý:** xử lý sau commit không có nghĩa hai thao tác trở thành một transaction nguyên tử. Chẳng hạn, đơn hàng có thể đã lưu thành công trong khi gửi email thất bại. Ứng dụng phải quy định rõ cách theo dõi và xử lý trạng thái này.

### 2.5. Có điểm tựa cho việc giao sự kiện đáng tin cậy

Spring Modulith có **Event Publication Registry** để theo dõi việc giao sự kiện tới các transactional event listener. Khi được cấu hình với cơ chế lưu trữ phù hợp, registry ghi nhận publication đang chờ hoàn tất và đánh dấu hoàn tất khi listener xử lý thành công.

Nếu listener lỗi, publication có thể vẫn ở trạng thái chưa hoàn tất để ứng dụng kiểm tra hoặc thực hiện phát lại theo cơ chế khôi phục/retry được cấu hình. Đây là lợi ích quan trọng so với việc chỉ công bố event trong bộ nhớ rồi bỏ qua kết quả xử lý.

Tuy nhiên cần phân biệt:

| Cơ chế | Khả năng |
| --- | --- |
| ApplicationEventPublisher đơn thuần | Công bố event trong tiến trình Spring; tự nó không lưu event bền vững để khôi phục sau sự cố. |
| Transactional listener sau commit | Tránh chạy tác vụ phụ trợ khi transaction phát hành rollback. |
| Event Publication Registry có persistent store | Theo dõi publication chưa hoàn tất và hỗ trợ phát lại/khôi phục theo cấu hình. |
| Idempotency trong listener | Ngăn việc áp dụng tác dụng phụ trùng lặp khi một sự kiện được xử lý nhiều lần. |

**Registry không mang lại bảo đảm exactly-once cho tác dụng phụ bên ngoài.** Ví dụ, listener đã gửi email thành công nhưng ứng dụng dừng trước khi ghi nhận publication hoàn tất; lần phát lại có thể gửi email lần nữa. Do đó các thao tác có tác dụng phụ quan trọng cần dùng khóa idempotency hoặc cơ chế chống trùng phù hợp.

### 2.6. Kiểm thử và quan sát hành vi theo module

Với sự kiện là một hợp đồng rõ ràng, kiểm thử có thể tách thành hai phần:

- **Publisher:** sau thao tác nghiệp vụ, event đúng loại được công bố với đúng mã định danh và dữ liệu.
- **Listener:** khi nhận event hợp lệ, module tiêu thụ thực hiện hành vi mong đợi, xử lý lỗi và chống trùng theo chính sách.

Spring Modulith hỗ trợ kiểm thử module qua **@ApplicationModuleTest** và kiểm tra event đã công bố bằng **PublishedEvents**. Cách kiểm thử này giảm nhu cầu kéo mọi module tiêu thụ vào một bài test của publisher.

Event cũng tạo một điểm quan sát tự nhiên: có thể ghi log event type, orderId, listener và kết quả xử lý, theo dõi các publication chưa hoàn tất, thời gian xử lý và số lần thử lại. Các chỉ số/trace cụ thể phụ thuộc cấu hình observability của ứng dụng; chỉ định nghĩa event không tự tạo sẵn dashboard.

## 3. Ví dụ: tạo đơn hàng và gửi xác nhận

Giả sử cấu trúc module:

~~~text
com.example.shop
├── orders
│   ├── OrderPlaced.java                 # Hợp đồng công khai của module
│   └── internal
│       └── OrderService.java
└── notifications
    └── internal
        └── OrderPlacedListener.java
~~~

### Bước 1. Khai báo event bất biến

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {
}
~~~

Record thể hiện sự kiện đã xảy ra với dữ liệu tối thiểu: **orderId** để xác định đơn hàng và **occurredAt** để ghi nhận thời điểm. Trong module Spring Modulith, đặt hợp đồng event tại API công khai phù hợp giúp module khác tham chiếu tới event mà không cần truy cập package nội bộ.

Không nên truyền nguyên đối tượng JPA entity vào event vì entity có thể chứa trạng thái mutable, quan hệ lazy loading và cấu trúc triển khai nội bộ.

### Bước 2. Publisher phát sự kiện từ nghiệp vụ gốc

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.OrderPlaced;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public UUID placeOrder(NewOrder request) {
        Order saved = orders.save(Order.create(request));
        UUID orderId = saved.getId();

        events.publishEvent(new OrderPlaced(orderId, Instant.now()));
        return orderId;
    }
}
~~~

**Order**, **OrderRepository** và **NewOrder** là các kiểu nghiệp vụ minh họa, cần được định nghĩa trong ứng dụng thực tế. Điểm cần quan sát là OrderService không gọi NotificationService. Nó chỉ lưu đơn hàng và công bố OrderPlaced.

Lệnh publishEvent ở đây chạy trong transaction tạo đơn; việc listener thực sự xử lý lúc nào phụ thuộc annotation và cấu hình listener. Không nên mặc định mọi listener đều bất đồng bộ hoặc sau commit: **@EventListener** thông thường có ngữ nghĩa khác **@TransactionalEventListener** và **@ApplicationModuleListener**.

### Bước 3. Listener xử lý sau khi transaction commit

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    private final NotificationService notifications;

    OrderPlacedListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        notifications.sendOrderConfirmation(event.orderId());
    }
}
~~~

Ở đây, module Thông báo biết OrderPlaced, nhưng module Đơn hàng không biết OrderPlacedListener hoặc NotificationService.

Với @ApplicationModuleListener, xử lý của listener diễn ra sau commit và bất đồng bộ theo cơ chế của Spring Modulith. Nếu gửi thông báo có lỗi, cần log nguyên nhân, theo dõi publication thất bại và xác định chính sách retry; không được xem việc publishEvent trả về là bằng chứng email đã được gửi.

### Bước 4. Thêm hành vi mới

Để cộng điểm sau khi tạo đơn, module Điểm thưởng có thể tạo listener khác cho cùng OrderPlaced:

~~~java
@Component
class AwardPointsOnOrderPlaced {

    private final LoyaltyService loyalty;

    AwardPointsOnOrderPlaced(LoyaltyService loyalty) {
        this.loyalty = loyalty;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        loyalty.awardForOrder(event.orderId());
    }
}
~~~

Đoạn mã là ví dụ về một listener đặt trong module Điểm thưởng (các import/package được lược bớt). Không cần thêm lời gọi LoyaltyService vào OrderService. Trong vận hành thực tế, awardForOrder phải xử lý idempotency, chẳng hạn ràng buộc duy nhất giữa orderId và loại nghiệp vụ cộng điểm, để tránh cộng hai lần.

## 4. Luồng xử lý khi có commit, lỗi và phát lại

~~~mermaid
sequenceDiagram
    participant Client as Khách hàng/API
    participant Orders as Module Đơn hàng
    participant DB as Cơ sở dữ liệu
    participant Registry as Publication Registry
    participant Listener as Module Thông báo

    Client->>Orders: placeOrder()
    Orders->>DB: Lưu đơn trong transaction
    Orders->>Registry: Ghi nhận publication (nếu cấu hình)
    Orders->>DB: COMMIT
    Orders-->>Client: Trả về orderId
    DB-->>Listener: Kích hoạt listener sau commit
    Listener->>Listener: Gửi xác nhận / xử lý nghiệp vụ
    alt Xử lý thành công
        Listener->>Registry: Đánh dấu hoàn tất
    else Xử lý thất bại
        Note over Registry: Publication chưa hoàn tất
        Registry-->>Listener: Phát lại theo cơ chế recovery/retry
    end
~~~

*Sơ đồ mô tả luồng logic, không phải thứ tự các lời gọi nội bộ cố định của mọi phiên bản Spring Modulith. Khả năng lưu publication và phát lại chỉ có khi Event Publication Registry cùng persistence/recovery tương ứng được cấu hình.*

Ba trường hợp nên kiểm tra:

1. **Lưu đơn thất bại và rollback:** listener sau commit không được thực thi cho transaction thất bại đó.
2. **Lưu đơn thành công nhưng listener lỗi:** đơn hàng đã tồn tại; ứng dụng cần quan sát publication chưa hoàn tất và khôi phục việc xử lý.
3. **Listener thực hiện tác dụng phụ nhưng chưa xác nhận hoàn tất:** sự kiện có thể được giao lại; logic nhận event phải chống xử lý trùng.

## 5. So sánh gọi trực tiếp và phát event

| Khía cạnh | Gọi service trực tiếp | Phát application event |
| --- | --- | --- |
| Phụ thuộc | Bên gọi biết API của module được gọi. | Bên phát chỉ cần biết hợp đồng event; bên nhận phụ thuộc vào event. |
| Mở rộng hành vi | Thường phải thay đổi luồng gọi hiện tại. | Có thể thêm listener độc lập cho cùng sự kiện. |
| Thời điểm xử lý | Thường diễn ra ngay trong lời gọi; có thể dùng cùng transaction nếu thiết kế cho phép. | Có thể đồng bộ hoặc sau commit/bất đồng bộ tùy loại listener. |
| Xử lý lỗi | Lỗi có thể truyền trực tiếp lên bên gọi. | Listener sau commit cần cơ chế ghi nhận, retry và xử lý thất bại riêng. |
| Quan sát | Dễ theo dõi theo call stack thông thường. | Cần liên kết log/trace theo event ID, business ID và listener. |
| Tính nhất quán | Phù hợp khi cần kết quả ngay và ràng buộc nguyên tử. | Phù hợp với tác vụ có thể xử lý sau và chấp nhận độ trễ nhất định. |
| Độ phức tạp | Dễ hiểu với luồng ngắn, quan hệ rõ. | Cần quản lý hợp đồng event, listener, idempotency và vận hành. |

**Ví dụ chọn cách phù hợp:**

- **Gửi email sau khi đơn hàng được lưu:** event sau commit thường phù hợp vì có thể thử lại nếu gửi thất bại.
- **Cập nhật chỉ mục tìm kiếm hoặc báo cáo:** event phù hợp nếu chấp nhận dữ liệu hiển thị trễ một khoảng ngắn.
- **Kiểm tra tồn kho bắt buộc trước khi xác nhận bán:** thường cần tương tác đồng bộ hoặc một quy trình giữ chỗ được thiết kế rõ; phát event sau commit rồi mặc định đơn hàng thành công có thể làm sai ràng buộc nghiệp vụ.
- **Lấy ngay tỷ giá để báo giá cho người dùng:** lời gọi trực tiếp thường phù hợp hơn vì phía gọi cần kết quả tức thì.

Như vậy, event giúp giảm ghép nối khi truyền đạt **sự kiện đã xảy ra** và phản ứng theo module, nhưng không thay thế mọi lời gọi đồng bộ.

## 6. Những giới hạn cần nhận biết

### Event không tự bảo đảm giao thành công

ApplicationEventPublisher vốn là cơ chế phát event trong bộ nhớ ứng dụng. Nếu thiếu persistence publication registry, một sự cố tiến trình có thể khiến việc xử lý chưa hoàn tất khó được khôi phục. Ngay cả khi đã có registry, cần cấu hình lưu trữ, chính sách phát lại và cách xử lý publication liên tục thất bại.

### Listener sau commit tạo ra tính nhất quán cuối cùng

Ví dụ, màn hình Đơn hàng có thể hiển thị “Đã tạo” trước khi module Điểm thưởng ghi điểm. Đây là hệ quả bình thường của xử lý bất đồng bộ. API và UI nên biểu diễn trạng thái phù hợp, tránh hứa rằng tất cả tác vụ phụ trợ đã hoàn tất ngay khi request tạo đơn trả về.

### Phát lại có thể gây tác dụng phụ trùng

Một event có thể được xử lý nhiều lần nếu có retry hoặc lỗi giữa lúc thực hiện tác dụng phụ và lúc đánh dấu publication hoàn tất. Các thao tác như cộng điểm, trừ tiền hoặc tạo phiếu phải có khóa nghiệp vụ và kiểm soát idempotency. Đặc biệt, **không coi exactly-once là thuộc tính mặc định của event hay registry**.

### Luồng nghiệp vụ trở nên phân tán qua nhiều listener

Publisher ít phụ thuộc hơn, nhưng để hiểu toàn bộ phản ứng với OrderPlaced, lập trình viên phải tìm các listener đăng ký event đó. Cần tài liệu sự kiện, tên rõ nghĩa, kiểm thử tích hợp và log/trace xuyên module để tránh “luồng xử lý vô hình”.

### Event contract cần được quản trị

Đổi tên hoặc cấu trúc OrderPlaced có thể ảnh hưởng tất cả listener. Nên dùng payload nhỏ, bất biến, có ý nghĩa ổn định; khi cần thay đổi schema, đánh giá mức tương thích và khả năng đọc lại những event đã lưu trong publication registry.

## 7. Cách khai thác lợi ích trong một dự án thật

| Việc thực hiện | Mục đích |
| --- | --- |
| Đặt tên event theo sự thật nghiệp vụ ở thì đã xảy ra. | Giúp publisher và listener giao tiếp bằng ngôn ngữ chung. |
| Công bố event từ module sở hữu nghiệp vụ. | Rõ trách nhiệm xác định khi nào sự kiện hợp lệ. |
| Đặt hợp đồng event trong API công khai thích hợp; giữ service nội bộ trong package internal. | Bảo vệ ranh giới Spring Modulith. |
| Truyền định danh và dữ liệu tối thiểu, tránh truyền JPA entity. | Giảm phụ thuộc vào cấu trúc dữ liệu và trạng thái persistence. |
| Dùng listener sau commit cho tác vụ cần phản ứng với transaction đã thành công. | Tránh tác dụng phụ từ giao dịch rollback. |
| Cấu hình Event Publication Registry bằng cơ chế lưu trữ phù hợp nếu cần recovery. | Theo dõi và xử lý publication chưa hoàn tất sau lỗi. |
| Thiết kế idempotency và chính sách retry ngay tại listener. | Hạn chế trùng tác dụng phụ và kiểm soát lỗi lặp. |
| Kiểm thử publisher, listener và các kịch bản rollback/lỗi/phát lại. | Xác nhận điều kiện thành công và độ tin cậy của luồng sự kiện. |
| Theo dõi publication chưa hoàn tất, thời gian xử lý, mã nghiệp vụ và lỗi listener. | Phát hiện sự kiện bị kẹt, điều tra và khôi phục vận hành. |

Có thể bắt đầu bằng một use case nhỏ: **sau khi đặt hàng thành công, gửi email xác nhận**. Tách listener khỏi OrderService, kiểm tra event chỉ được tiêu thụ sau commit, cố tình gây lỗi ở dịch vụ email rồi quan sát publication chưa hoàn tất (nếu đã bật registry), thực hiện recovery và xác minh email không bị gửi trùng.

## 8. Câu hỏi tự kiểm tra

1. Vì sao việc thêm một listener cho OrderPlaced giúp module Đơn hàng ít phải thay đổi hơn so với gọi trực tiếp nhiều service?
2. Khác biệt thực tế giữa listener đồng bộ thông thường và @ApplicationModuleListener sau commit là gì?
3. Nếu transaction tạo đơn rollback, email xác nhận có nên được gửi không? Cần chọn loại listener thế nào?
4. Nếu email đã gửi nhưng publication chưa được đánh dấu hoàn tất, lần retry có thể gây vấn đề gì và giải quyết ra sao?
5. Khi nào gọi trực tiếp một module khác lại phù hợp hơn dùng event?

**Điểm ghi nhớ:** Event có giá trị lớn nhất khi cần thông báo một **sự thật nghiệp vụ** cho nhiều module tự phản ứng: giảm phụ thuộc, mở rộng hành vi và tách tác vụ sau commit. Để lợi ích đó an toàn trong vận hành, cần kết hợp hợp đồng event ổn định, transactional listener phù hợp, publication registry khi cần recovery, idempotency, kiểm thử và khả năng quan sát.
