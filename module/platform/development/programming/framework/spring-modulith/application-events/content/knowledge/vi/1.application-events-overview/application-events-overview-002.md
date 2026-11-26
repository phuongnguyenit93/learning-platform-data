# Bài toán mà event giải quyết

Trong một ứng dụng **Spring Modulith**, các module cùng chạy trong một tiến trình Spring Boot nhưng vẫn cần giữ ranh giới nghiệp vụ rõ ràng. Vấn đề xuất hiện khi một thao tác ở module này kéo theo nhiều việc ở các module khác: hoàn tất đơn hàng có thể cần gửi thông báo, cộng điểm thưởng, cập nhật báo cáo hoặc ghi nhật ký. Nếu module đặt hàng gọi trực tiếp từng module, số phụ thuộc và rủi ro lan truyền lỗi sẽ tăng theo mỗi tính năng mới.

**Application event** giúp diễn đạt một sự thật nghiệp vụ đã xảy ra, để những module quan tâm tự phản ứng. Mục tiêu là giảm sự phụ thuộc của module phát sự kiện vào các module xử lý, đồng thời làm rõ thời điểm xử lý, cách khôi phục khi thất bại và mức độ nhất quán mà nghiệp vụ chấp nhận.

Sau bài học, bạn cần giải thích được *vì sao* dùng event, khi nào **không nên** dùng event, sự khác nhau giữa publish và xử lý sau commit, và vì sao event chỉ đáng tin cậy khi có chiến lược lưu vết, retry, chống xử lý trùng, kiểm thử và quan sát.

## 1. Từ một yêu cầu nhỏ đến chuỗi phụ thuộc

Giả sử hệ thống bán hàng có bốn module:

| Module | Trách nhiệm chính |
| --- | --- |
| `orders` | Tiếp nhận và lưu đơn hàng, quản lý trạng thái đơn |
| `notifications` | Chuẩn bị và gửi thông báo |
| `loyalty` | Ghi nhận điểm thưởng của khách hàng |
| `reporting` | Cập nhật dữ liệu phục vụ báo cáo |

Yêu cầu ban đầu chỉ là “đặt hàng thành công”. Sau đó sản phẩm bổ sung email xác nhận, điểm thưởng và báo cáo. Cách làm trực tiếp dễ xuất hiện trong một phương thức:

~~~java
@Transactional
public UUID placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(Order.from(command));

    notificationService.sendConfirmation(order); // Có thể gọi dịch vụ ngoài
    loyaltyService.addPoints(order);               // Phụ thuộc module khác
    reportingService.updateSales(order);           // Phụ thuộc module khác

    return order.getId();
}
~~~

*Đây là ví dụ minh họa một thiết kế có vấn đề, không phải mẫu triển khai nên sao chép.* `orders` giờ phải biết cả ba dịch vụ và thứ tự gọi của chúng. Thêm một tính năng mới đồng nghĩa sửa code của `orders`, dù quy tắc tạo đơn không đổi.

Nguy hiểm hơn, `@Transactional` trên `placeOrder()` **không thể tự biến các hiệu ứng ngoài cơ sở dữ liệu thành một giao dịch nguyên tử**. Nếu email đã gửi rồi nhưng giao dịch lưu đơn bị rollback, khách hàng nhận thông báo cho đơn chưa tồn tại. Nếu dịch vụ gửi mail bị lỗi và exception truyền ngược, thao tác đặt hàng có thể thất bại chỉ vì một chức năng phụ trợ. Nếu các module cùng tham gia giao dịch database, thời gian giữ lock và phạm vi lỗi cũng có thể phình to.

### Những loại phụ thuộc cần tách bạch

| Vấn đề | Khi gọi trực tiếp | Event giúp gì? |
| --- | --- | --- |
| **Phụ thuộc mã nguồn** | `orders` import service của `notifications`, `loyalty`, `reporting` | `orders` công bố một loại sự kiện thuộc API công khai của mình; các module khác chủ động đăng ký xử lý |
| **Phụ thuộc luồng điều khiển** | `orders` quyết định ai chạy, chạy theo thứ tự nào | Mỗi listener chịu trách nhiệm cho phản ứng của module mình |
| **Phụ thuộc thời gian chạy** | Một dịch vụ phụ trợ chậm hoặc hỏng có thể kéo chậm luồng đặt hàng | Listener chạy sau commit/bất đồng bộ giúp tách luồng, nếu cấu hình đúng |
| **Phụ thuộc giao dịch** | Tác vụ phụ dễ bị trộn vào transaction chính | Có thể xử lý sau khi dữ liệu nguồn được commit, trong transaction riêng |
| **Mở rộng tính năng** | Thêm một phản ứng mới phải sửa module phát | Thêm listener ở module nhận mà không cần sửa logic đặt hàng |

Event không xóa hết mọi phụ thuộc. Các module nhận vẫn phụ thuộc vào **hợp đồng sự kiện** và ý nghĩa nghiệp vụ của nó. Đổi tên, xóa field hoặc đổi ý nghĩa `OrderPlaced` vẫn có thể làm hỏng listener. Khác biệt là module phát không phải phụ thuộc ngược vào từng module nhận.

## 2. Event mô tả điều đã xảy ra

Một domain/application event thường được đặt tên ở **thì quá khứ**, ví dụ `OrderPlaced`, `PaymentAuthorized`, `OrderCancelled`. Nó phát biểu một sự kiện nghiệp vụ đã xảy ra hoặc đã được ghi nhận trong một bước nghiệp vụ rõ ràng.

- **Command** như `SendConfirmationEmail` yêu cầu một bên cụ thể thực hiện công việc.
- **Event** như `OrderPlaced` thông báo rằng đơn đã được ghi nhận; bên nhận tự quyết định có cần gửi email, cộng điểm hay cập nhật báo cáo.
- **State** là dữ liệu hiện tại, chẳng hạn `Order.status = CONFIRMED`. Event thể hiện sự chuyển biến có ý nghĩa trong quá trình đạt đến trạng thái đó.

Sự khác nhau này ảnh hưởng kiến trúc. Nếu `orders` phát `SendConfirmationEmail` rồi chờ kết quả để tiếp tục, nó vẫn đang điều phối trách nhiệm của `notifications`, chỉ thay lời gọi phương thức bằng một thông điệp. Với `OrderPlaced`, `orders` chỉ chịu trách nhiệm phát biểu sự thật thuộc sở hữu của mình.

~~~mermaid
flowchart LR
    U["Yêu cầu đặt hàng"] --> O["orders: lưu đơn"]
    O --> E(("OrderPlaced"))
    E --> N["notifications: thông báo"]
    E --> L["loyalty: tích điểm"]
    E --> R["reporting: thống kê"]
~~~

Mũi tên từ `OrderPlaced` biểu diễn các bên đăng ký quan tâm. Nó **không** mặc định có nghĩa là các nhánh đều bất đồng bộ, đã commit hoặc sẽ được chạy lại sau lỗi; những đặc tính đó phụ thuộc loại listener và cấu hình hạ tầng.

### Thiết kế hợp đồng sự kiện

Sự kiện nên nhỏ gọn, bất biến, dễ đọc và có ý nghĩa ổn định. Với Java hiện đại, `record` là lựa chọn phù hợp:

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

// Đặt ở API công khai của module orders để module khác được phép tham chiếu.
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        Instant occurredAt
) {}
~~~

`eventId` dùng để theo dõi và nhận biết một **lần xảy ra nghiệp vụ** khi cần chống xử lý trùng; `orderId` định danh aggregate; `customerId` là dữ liệu tối thiểu để bên nhận tự tìm thông tin mình quản lý; `occurredAt` biểu thị thời điểm sự kiện được tạo. Không nên nhét entity JPA đang được quản lý, transaction/session, đối tượng service hoặc toàn bộ cấu trúc nội bộ của `orders` vào payload. Làm như vậy dễ rò rỉ ranh giới và tạo phụ thuộc vào persistence model.

Với hệ thống có nhiều cách tạo đơn, phải thống nhất ý nghĩa của `OrderPlaced`: “đơn đã được ghi nhận” hay “đơn đã được xác nhận sau thanh toán”. Nếu tính điểm chỉ được phép xảy ra sau thanh toán, có thể cần sự kiện khác như `OrderConfirmed`. **Tên sự kiện phải phản ánh đúng mốc nghiệp vụ**, vì listener dựa vào mốc đó để hành động.

## 3. Publisher và listener trong Spring Modulith

Spring Modulith tận dụng cơ chế application events của Spring để liên kết module qua một hợp đồng sự kiện. Module nguồn dùng `ApplicationEventPublisher`; module nhận cung cấp listener của chính mình. Ví dụ sau giả định đã có `Order`, `OrderRepository` và `PlaceOrderCommand` trong module `orders`:

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(OrderRepository orders, ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        Order order = orders.save(Order.from(command));

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                Instant.now()
        ));

        return order.getId();
    }
}
~~~

Module `orders` chỉ import API của Spring và event do mình sở hữu. Nó không cần tham chiếu service thuộc `loyalty` hoặc `notifications`.

Một listener thuộc module `loyalty` có thể như sau:

~~~java
package com.example.shop.loyalty;

import com.example.shop.orders.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class LoyaltyOnOrderPlaced {

    private final LoyaltyLedger ledger;

    LoyaltyOnOrderPlaced(LoyaltyLedger ledger) {
        this.ledger = ledger;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        ledger.grantPointsIfAbsent(
                event.eventId(),
                event.customerId(),
                10
        );
    }
}
~~~

`grantPointsIfAbsent(...)` là **phương thức nghiệp vụ minh họa**, không phải API của Spring Modulith. Khi hiện thực, bảng cộng điểm cần ràng buộc duy nhất cho cặp `(event_id, handler)` hoặc khóa tương đương, để hai lần nhận cùng event không cộng điểm hai lần. Kiểm tra `exists` rồi `insert` riêng rẽ mà không có unique constraint vẫn có thể bị race condition.

`@ApplicationModuleListener` là annotation tiện ích của Spring Modulith, kết hợp xử lý sự kiện theo transaction sau commit với xử lý bất đồng bộ và transaction riêng cho listener (về mặt ý tưởng tương đương `@TransactionalEventListener`, `@Async` và `@Transactional(REQUIRES_NEW)`). Nhờ vậy, `orders` không phải đợi thao tác cộng điểm hoàn thành trong transaction đặt hàng.

Điểm cần ghi nhớ: **gọi `publishEvent(...)` tự nó không bảo đảm sau commit, bất đồng bộ hoặc bền vững**. Đó là API phát sự kiện; thời điểm, cách thực thi và mức bảo đảm phụ thuộc vào listener cùng event publication registry.

## 4. Vấn đề transaction: xử lý trước hay sau commit?

Giả sử `orders` vừa lưu đơn và phát `OrderPlaced`, nhưng database báo lỗi ở lúc commit. Những phản ứng như gửi email “đơn đã thành công” phải được ngăn lại. Vì vậy lựa chọn loại listener là một quyết định nghiệp vụ.

| Cơ chế | Thời điểm thường gặp | Hệ quả chính |
| --- | --- | --- |
| `@EventListener` | Đồng bộ trong luồng publish theo cấu hình mặc định | Listener có thể chạy **trước commit**; exception có thể ảnh hưởng luồng giao dịch đang chạy |
| `@TransactionalEventListener(phase = AFTER_COMMIT)` | Sau khi transaction phát sự kiện commit thành công | Tránh phản ứng cho transaction đã rollback; bản thân annotation này không mặc định chạy bất đồng bộ hoặc mở transaction mới |
| `@ApplicationModuleListener` | Sau commit, bất đồng bộ, trong transaction riêng | Phù hợp cho phản ứng độc lập giữa các module; kết quả của listener thường xuất hiện muộn hơn response đặt hàng |

Với `@TransactionalEventListener`, mặc định sự kiện phát ngoài một transaction sẽ không kích hoạt listener giao dịch; chỉ dùng `fallbackExecution` khi đã hiểu rõ hệ quả. Nếu listener cần ghi database sau commit, cần bảo đảm nó chạy trong transaction phù hợp, như cách `@ApplicationModuleListener` hỗ trợ.

### Dòng thời gian có publication registry

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as orders
    participant DB as Database
    participant P as Event Publisher / Registry
    participant L as loyalty listener

    C->>O: placeOrder(command)
    O->>DB: Lưu Order (transaction T1)
    O->>P: publishEvent(OrderPlaced)
    P->>DB: Ghi publication chưa hoàn tất (trong T1)
    O->>DB: COMMIT T1
    O-->>C: Trả orderId
    P-->>L: Giao OrderPlaced sau commit
    L->>DB: Cộng điểm (transaction T2)
    L-->>P: Xử lý thành công
    P->>DB: Đánh dấu publication hoàn tất
~~~

Sơ đồ mô tả **luồng logic** khi đã cấu hình registry bền vững. Nó không ngụ ý response HTTP luôn đến trước khi listener bắt đầu; hai việc có thể diễn ra gần như đồng thời. Registry ghi nhận ý định giao sự kiện trong transaction phát, còn cơ chế event listener thực hiện lời gọi đến bên nhận sau commit.

Với xử lý bất đồng bộ, ngay khi API trả thành công, `loyalty` hoặc `reporting` có thể **chưa cập nhật**. Đây là *eventual consistency* (nhất quán cuối cùng), phù hợp nếu hệ thống chấp nhận độ trễ có kiểm soát. Giao diện người dùng có thể hiển thị “đang cập nhật điểm” thay vì hứa hẹn điểm đã có ngay lập tức.

## 5. Bài toán lỗi sau commit: publication registry giải quyết điều gì?

Chạy sau commit giúp tránh tác động từ transaction rollback, nhưng mở ra một khoảng rủi ro khác: **database đã commit, JVM có thể dừng trước khi listener hoàn tất**. Nếu chỉ dùng event trong bộ nhớ, event đang chờ có thể mất khỏi tiến trình. Bất đồng bộ cũng không đồng nghĩa với có hàng đợi bền vững.

Spring Modulith có **Event Publication Registry** để theo dõi publication cho các transactional listener được hỗ trợ:

1. Khi event được publish trong transaction, registry tạo bản ghi publication cần chuyển cho từng listener quan tâm, trên lưu trữ đã cấu hình.
2. Nếu transaction nguồn rollback, bản ghi publication cùng transaction không được commit.
3. Khi listener xử lý thành công, publication tương ứng được đánh dấu hoàn tất.
4. Khi listener ném exception hoặc chưa hoàn thành, bản ghi vẫn thể hiện trạng thái cần xử lý; ứng dụng có thể truy vấn và **kích hoạt cơ chế gửi lại/resubmit** theo chiến lược vận hành.

Có thể chọn kho lưu trữ phù hợp hệ thống, chẳng hạn JDBC hoặc JPA theo các module tích hợp và phiên bản Spring Modulith đang dùng. Phải thực sự cấu hình repository publication bền vững và quy trình khôi phục. **Chỉ thêm `@ApplicationModuleListener` không tự bảo đảm rằng mọi sự kiện sẽ được lưu bền hoặc được retry vô hạn.**

Điểm mạnh của registry khi dùng chung database và transaction là *ý định gửi event* được ghi cùng thao tác nghiệp vụ. Tuy nhiên, registry không tạo một transaction nguyên tử xuyên qua các dịch vụ bên ngoài như email, thanh toán hoặc HTTP API.

### Từng kịch bản lỗi và hành vi cần có

| Kịch bản | Điều cần xảy ra | Cách thiết kế |
| --- | --- | --- |
| T1 rollback trước commit | Không xử lý phản ứng hậu commit | Transactional listener; publication gắn với T1 |
| T1 commit, tiến trình dừng trước khi listener chạy | Vẫn biết có publication chưa hoàn tất | Registry trên storage bền vững; chính sách khôi phục/resubmit |
| Listener ném exception | Không đánh dấu hoàn tất giả | Ghi nhận lỗi, retry có giới hạn/backoff, cảnh báo |
| Listener hoàn thành hiệu ứng nhưng crash trước khi đánh dấu hoàn tất | Event có thể đến lần nữa | Idempotency và unique constraint; với dịch vụ ngoài dùng idempotency key hoặc giao thức tương đương |
| Dịch vụ nhận lỗi kéo dài | Không nghẽn vô hạn, không quên việc tồn đọng | Retry có kiểm soát, hàng chờ xử lý vận hành, cảnh báo publication quá hạn |
| Hợp đồng event thay đổi không tương thích | Listener cũ có thể thất bại | Quản lý phiên bản payload và chiến lược tương thích |

**“Giao ít nhất một lần” (at-least-once) là mô hình thực tế nên chuẩn bị cho xử lý có retry.** Nó cho phép nhận trùng; không hứa hẹn hiệu ứng nghiệp vụ xảy ra đúng một lần trên mọi hệ thống ngoài. Mục tiêu của listener là *idempotent*: nhận lại cùng một sự kiện không làm thay đổi kết quả nghiệp vụ quá một lần.

Ví dụ: cộng điểm có thể dùng unique key theo `eventId`. Gửi email khó hơn: nếu nhà cung cấp đã chấp nhận email nhưng ứng dụng crash trước khi ghi nhận thành công, retry có thể gửi trùng. Nên có bảng yêu cầu gửi, trạng thái giao hàng và khả năng idempotency từ bên gửi nếu được hỗ trợ; khi không có bảo đảm của nhà cung cấp, phải thừa nhận giới hạn đó.

## 6. Những gì event không tự giải quyết

### 6.1. Bất biến nghiệp vụ cần quyết định ngay

Giả sử quy tắc là **“không tạo đơn thành công nếu chưa giữ được tồn kho”**. Đưa bước giữ kho sang listener bất đồng bộ rồi trả `CONFIRMED` ngay có thể tạo đơn vượt kho. Có hai phương án hợp lý:

- **Nhất quán ngay:** Kiểm tra/giữ tồn kho đồng bộ trong ranh giới giao dịch hoặc bằng giao thức đồng bộ có kiểm soát, rồi chỉ phát `OrderConfirmed` khi điều kiện đã đạt.
- **Nhất quán cuối cùng:** Tạo đơn ở trạng thái `PENDING`, phát event yêu cầu các bước độc lập, sau đó chuyển sang `CONFIRMED` hoặc `REJECTED` dựa trên kết quả và xử lý bù khi cần. Phải thể hiện rõ trạng thái chờ cho người dùng.

Event là công cụ phân tách trách nhiệm, không thay thế được quyết định về bất biến nghiệp vụ, transaction, idempotency và cách xử lý bù.

### 6.2. Cần câu trả lời ngay từ bên được gọi

Nếu người dùng cần kết quả tính phí vận chuyển **trong response hiện tại**, lời gọi đồng bộ hoặc một query API rõ ràng thường thích hợp hơn. Gửi `ShippingCostRequested` rồi chờ listener trả lời bằng một event khác trong cùng request có thể chỉ làm phức tạp request/response.

### 6.3. Ranh giới quy trình và hạ tầng

**Spring application events chủ yếu hoạt động trong cùng tiến trình ứng dụng.** Chúng hữu ích cho module của modular monolith, nhưng không phải tự động là message broker liên tiến trình. Khi cần phân phối sang service khác, phải thiết kế integration events, outbox hoặc cơ chế xuất bản ra broker (Kafka, AMQP, ...) cùng xử lý lỗi mạng và hợp đồng phiên bản. Event nội bộ và integration event có thể liên quan nhau, nhưng không bắt buộc có cùng payload.

Sử dụng event cũng không đồng nghĩa với **event sourcing**. Event sourcing lưu các event như nguồn sự thật để tái dựng trạng thái; application event thông thường chỉ dùng để thông báo và điều phối các phản ứng.

## 7. Nguyên tắc thiết kế cho module nhận

**Mỗi listener nên giữ một trách nhiệm rõ ràng** và thuộc module sở hữu phản ứng đó. Ví dụ `loyalty` sở hữu quy tắc cộng điểm và dữ liệu ledger; `notifications` sở hữu lựa chọn kênh thông báo. Không để `orders` import repository, entity nội bộ hoặc service implementation của các module này.

Để việc vận hành an toàn:

1. **Đặt hợp đồng event trong API công khai có chủ ý.** Trong Spring Modulith, tránh cho listener import package nội bộ của module phát; khi cần, khai báo named interface thích hợp và kiểm tra ranh giới module.
2. **Giữ payload đủ dùng và ổn định.** Chứa các ID, giá trị snapshot cần thiết tại thời điểm xảy ra sự kiện; tránh truyền live JPA entity. Cân nhắc dữ liệu nhạy cảm và tương thích khi thêm hoặc thay đổi field.
3. **Dùng định danh sự kiện độc lập.** Phân biệt `eventId` của một lần xảy ra với `orderId` của thực thể: cùng đơn hàng có thể có nhiều event khác nhau.
4. **Thiết kế idempotency ở nơi ghi dữ liệu.** Dựa vào unique constraint hoặc khóa tự nhiên phù hợp; không chỉ dựa vào một biến boolean trong JVM.
5. **Quyết định thứ tự xử lý nếu nghiệp vụ cần.** Không mặc định các listener chạy tuần tự hoặc có thứ tự xác định. Nếu phản ứng B bắt buộc sau A, hãy mô hình hóa sự kiện/trạng thái tiếp theo hoặc một workflow sở hữu thứ tự.
6. **Không nuốt lỗi rồi trả thành công giả.** Nếu lỗi khiến publication cần xử lý lại, cho phép hệ thống ghi nhận thất bại; đồng thời phân biệt lỗi tạm thời và lỗi dữ liệu vĩnh viễn để tránh retry vô hạn vô ích.

Một listener viết dữ liệu trong database riêng của module thường dễ làm idempotent hơn listener thực hiện side effect ngoài hệ thống. Với HTTP, email hoặc payment gateway, hãy định nghĩa rõ điều kiện “xử lý xong”, cách xác nhận và thao tác bù khi không thể hoàn tác.

## 8. Kiểm thử điều gì để tin được luồng event?

Kiểm thử chỉ xác nhận rằng `publishEvent()` đã được gọi là chưa đủ. Lỗi thường nằm ở transaction, retry, ranh giới module và tác dụng phụ sau khi giao lại event. Spring Modulith cung cấp các tiện ích như `@ApplicationModuleTest`, `PublishedEvents`, `Scenario` và khả năng kiểm tra cấu trúc module để hỗ trợ kiểm thử nhiều lớp.

| Lớp kiểm thử | Tình huống nên kiểm | Kết quả mong muốn |
| --- | --- | --- |
| Publisher | Đặt đơn hợp lệ | Đơn được lưu; đúng một `OrderPlaced` có `eventId`, `orderId`, `customerId` phù hợp |
| Transaction | Cố ý rollback transaction đặt đơn | Không có phản ứng `AFTER_COMMIT`; publication liên quan không được commit |
| Listener | Nhận một `OrderPlaced` hợp lệ | Ghi điểm đúng quy tắc và đúng module sở hữu |
| Idempotency | Gửi lại **cùng `eventId`** hai lần, kể cả cạnh tranh | Chỉ có một ledger entry hoặc một hiệu ứng hợp lệ |
| Khôi phục | Sau commit làm listener ném exception, rồi bật lại | Publication được nhận diện là chưa hoàn tất và được xử lý lại sau khi nguyên nhân lỗi được sửa |
| Ranh giới module | Chạy kiểm tra cấu trúc Spring Modulith | Không có phụ thuộc ngược hoặc import vào package nội bộ không được công bố |
| Luồng cuối đến cuối | Đặt đơn rồi đợi phản ứng bất đồng bộ | Trạng thái hội tụ trong thời hạn chấp nhận được; không dựa vào `Thread.sleep` cố định |

**Cẩn thận với `@Transactional` trên phương thức test.** Nhiều test tự rollback transaction sau khi kết thúc, vì vậy listener `AFTER_COMMIT` sẽ không chạy như mong đợi. Muốn chứng minh hành vi sau commit, cần để transaction thực sự commit trong kịch bản test và dùng cách chờ có điều kiện cho xử lý bất đồng bộ (ví dụ `Scenario`).

Nếu sử dụng registry, nên có một kiểm thử tích hợp với storage thật hoặc tương đương để xác nhận rollback, trạng thái publication chưa hoàn tất, khả năng resubmit và completion. Mock `ApplicationEventPublisher` không chứng minh được những thuộc tính này.

## 9. Quan sát và vận hành: biết event đang mắc ở đâu

Một luồng event chạy tốt lúc demo vẫn có thể thất bại âm thầm trong production. Nên quan sát tối thiểu:

| Tín hiệu | Câu hỏi mà nó trả lời |
| --- | --- |
| Số publication chưa hoàn tất | Có bao nhiêu tác vụ hậu commit đang tồn đọng? |
| Tuổi của publication cũ nhất | Có tác vụ nào bị kẹt vượt thời hạn nghiệp vụ chấp nhận? |
| Số lần retry và lỗi theo loại listener | Module nào thường xuyên gặp sự cố? |
| Độ trễ từ `occurredAt` đến khi xử lý xong | Hệ thống có đáp ứng kỳ vọng nhất quán cuối cùng? |
| Số lần nhận trùng hoặc từ chối do idempotency | Retry có tạo áp lực hay chỉ ra lỗi bất thường? |

Log và trace nên gắn `eventId`, `orderId`, tên event, tên listener, thời điểm xử lý và mã lỗi phân loại; liên kết với correlation/trace ID của request gốc khi phù hợp. Không log tràn lan payload chứa thông tin cá nhân.

Cần có quy trình vận hành được kiểm chứng: tìm publication chưa hoàn tất, xem nguyên nhân lỗi, sửa dữ liệu/cấu hình nếu cần, kích hoạt resubmit có kiểm soát và xác nhận tác dụng phụ thực tế. **Không đánh dấu hoàn tất thủ công chỉ để xóa cảnh báo** khi chưa biết nghiệp vụ đã được thực hiện hay chưa.

## 10. Cách chọn giữa gọi trực tiếp và event

| Câu hỏi thiết kế | Thường nghiêng về |
| --- | --- |
| Bên gọi phải biết kết quả ngay để quyết định commit/response? | Lời gọi đồng bộ hoặc một bước điều phối rõ ràng |
| Đây là phản ứng độc lập sau khi nghiệp vụ nguồn đã hoàn tất? | Application event sau commit |
| Bên nhận có thể chậm và kết quả cập nhật sau vài giây? | Event bất đồng bộ và eventual consistency |
| Side effect có thể cần thực hiện lại sau restart? | Event + durable publication registry + retry + idempotency |
| Cần giao sự kiện sang ứng dụng/process khác? | Integration event + outbox/broker và cơ chế giao nhận phù hợp |
| Thứ tự nhiều bước là một quy trình nghiệp vụ bắt buộc? | Workflow/process manager rõ ràng; có thể dùng event giữa các bước |

Quy tắc thực dụng: chỉ phát event khi **module nguồn đã xác định được một sự thật nghiệp vụ đáng tin**, bên nhận có thể sở hữu phản ứng của mình, và nhóm phát triển đã chỉ rõ tình trạng dữ liệu khi listener chưa chạy hoặc chạy thất bại. Nếu chưa trả lời được ba câu hỏi này, việc đổi service call thành event có thể chỉ che giấu phụ thuộc.

## 11. Tình huống luyện tập

Một ứng dụng bán vé có module `booking`, `payment`, `notifications` và `analytics`. Khi khách giữ chỗ, hệ thống phải bảo đảm mỗi ghế không bị giữ bởi hai người; sau khi thanh toán thành công sẽ gửi vé điện tử và cập nhật báo cáo.

Hãy tự thiết kế theo các bước:

1. Xác định bất biến **không giữ trùng ghế** cần được bảo vệ đồng bộ bằng ràng buộc dữ liệu/giao dịch hoặc cơ chế đặt giữ phù hợp.
2. Đề xuất những mốc có ý nghĩa như `SeatReserved`, `PaymentCompleted`, `TicketIssued`; phân biệt việc giữ chỗ với thanh toán và phát hành vé.
3. Chọn những phản ứng có thể chạy sau commit, ví dụ gửi email, thống kê; quyết định khi nào được hiển thị vé “đã phát hành”.
4. Với mỗi listener, xác định khóa chống xử lý trùng, trạng thái hoàn thành, lỗi có thể retry và thông tin cần quan sát.
5. Viết các test rollback, nhận trùng, listener thất bại sau commit và khôi phục sau restart.

**Tự kiểm tra:** Nếu thanh toán đã thành công nhưng email gửi vé bị lỗi, khách vẫn phải có một trạng thái đặt vé đúng và một cách nhận lại vé. Một lời gọi gửi email thất bại không được làm “biến mất” kết quả thanh toán; đồng thời hệ thống phải biết việc gửi thông báo đang chờ xử lý.

### Ghi nhớ

Application events trong Spring Modulith giải bài toán **giảm phụ thuộc giữa các module đối với những phản ứng xuất phát từ một sự thật nghiệp vụ**. Publisher công bố sự kiện thuộc ranh giới của mình; listener ở module khác tự chịu trách nhiệm xử lý. `@ApplicationModuleListener` hỗ trợ xử lý sau commit và bất đồng bộ; event publication registry hỗ trợ lưu vết và khôi phục publication chưa hoàn tất. Độ tin cậy thực tế vẫn phải được hoàn thiện bằng **idempotency, retry có kiểm soát, kiểm thử transaction và khả năng quan sát**.
