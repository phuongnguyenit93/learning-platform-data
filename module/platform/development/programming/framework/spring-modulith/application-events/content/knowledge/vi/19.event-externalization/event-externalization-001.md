# Event externalization là gì

Trong module SPRING_MODULITH_APPLICATION_EVENTS, application events giúp các module Spring Modulith giao tiếp với nhau mà không cần phụ thuộc trực tiếp vào implementation của nhau. Event externalization mở rộng cách giao tiếp đó ra ngoài ứng dụng: một sự kiện được phát sinh bên trong ứng dụng có thể được chuyển thành thông điệp để hệ thống khác nhận và xử lý.

Ví dụ, module Orders xác nhận đơn hàng. Các module nội bộ có thể nhận `OrderConfirmed` để cập nhật quy trình trong cùng ứng dụng; đồng thời hệ thống kho, vận chuyển hoặc phân tích dữ liệu có thể nhận một integration event tương ứng qua message broker. Bên phát chỉ công bố sự kiện mô tả điều đã xảy ra, còn bên nhận tự quyết định cách phản ứng.

## 1. Event externalization là gì?

Event externalization là quá trình đưa một application event vượt qua ranh giới của ứng dụng để một hệ thống hoặc dịch vụ khác có thể tiêu thụ. Thay vì gọi API của từng hệ thống đích, ứng dụng phát một thông điệp tới hạ tầng tích hợp như message broker. Các consumer độc lập đăng ký nhận thông điệp và xử lý theo nhu cầu.

Trong Spring Modulith, có thể đánh dấu loại event cần externalize bằng annotation `@Externalized` và cấu hình cơ chế externalization cùng integration phù hợp. Ví dụ:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.modulith.events.Externalized;

@Externalized("orders")
public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        int schemaVersion) {
}
~~~

Trong ví dụ, `orders` là target logic của sự kiện. Cấu hình externalization và integration adapter quyết định target đó được chuyển tới destination nào trong hạ tầng messaging. Tên target không nhất thiết phải trùng với tên topic hoặc queue; cách ánh xạ phụ thuộc vào integration đang sử dụng.

Annotation mô tả ý định externalize một event. Để thông điệp thực sự được gửi, ứng dụng vẫn cần cấu hình cơ chế externalization, destination, kết nối và serializer phù hợp. Chỉ thêm annotation không tự tạo broker, topic hay subscription.

## 2. Vì sao cần externalize event?

Externalization hữu ích khi một sự kiện nghiệp vụ cần thông báo cho nhiều hệ thống độc lập. Ví dụ:

- Khi đơn hàng được xác nhận, hệ thống kho tạo yêu cầu giữ hàng.
- Khi thanh toán hoàn tất, hệ thống vận chuyển bắt đầu chuẩn bị giao hàng.
- Khi khách hàng thay đổi thông tin, hệ thống phân tích cập nhật dữ liệu phục vụ báo cáo.
- Khi tài khoản được tạo, hệ thống thông báo gửi email chào mừng.

Cách tiếp cận này giảm phụ thuộc thời gian chạy giữa các hệ thống. Module Orders không cần biết hệ thống kho đang dùng công nghệ gì, địa chỉ endpoint nào hoặc có đang trực tuyến hay không. Nó công bố sự kiện theo một hợp đồng đã thống nhất; hạ tầng messaging đảm nhiệm việc chuyển thông điệp tới consumer.

Externalization cũng giúp bên nhận mở rộng độc lập. Có thể bổ sung một consumer mới để tạo báo cáo mà không cần sửa luồng xác nhận đơn hàng, miễn là hợp đồng sự kiện vẫn đáp ứng nhu cầu của consumer đó.

## 3. Phân biệt application event, integration event và event sourcing

Ba khái niệm này có liên quan nhưng phục vụ những mục đích khác nhau:

| Khái niệm | Phạm vi và mục đích |
| --- | --- |
| Application event | Thông báo một điều đã xảy ra trong ứng dụng; thường phục vụ giao tiếp giữa các module trong cùng tiến trình |
| Integration event | Hợp đồng thông điệp được công bố qua ranh giới ứng dụng để hệ thống khác có thể hiểu và xử lý |
| Event sourcing | Cách lưu trạng thái bằng chuỗi sự kiện làm nguồn dữ liệu chính để dựng lại trạng thái |

Externalization là cách chuyển một event ra ngoài ứng dụng; bản thân nó không biến hệ thống thành event-sourced. Một ứng dụng CRUD thông thường vẫn có thể externalize integration events mà không lưu toàn bộ lịch sử thay đổi làm nguồn dữ liệu chính.

Application event nội bộ có thể chứa kiểu dữ liệu hoặc chi tiết implementation phù hợp với module trong ứng dụng. Integration event cần ổn định hơn vì consumer có vòng đời triển khai độc lập. Do đó, thường nên ánh xạ domain/application event sang một integration event có hợp đồng rõ ràng thay vì đưa mọi object nội bộ ra broker.

## 4. Luồng externalization trong ứng dụng

Một luồng phổ biến có thể diễn ra như sau:

~~~mermaid
flowchart LR
    A[Module nghiệp vụ] --> B[Publish application event]
    B --> C[Event publication tracking]
    C --> D[Externalization listener]
    D --> E[Message broker]
    E --> F[Consumer hệ thống khác]
~~~

1. Module nghiệp vụ thay đổi trạng thái và phát application event trong ngữ cảnh xử lý nghiệp vụ.
2. Cơ chế event publication theo dõi publication tới listener cần xử lý, bao gồm listener thực hiện externalization khi được cấu hình.
3. Externalization listener chuyển event thành thông điệp theo target, mapping và serialization đã cấu hình.
4. Integration adapter gửi thông điệp tới broker hoặc hệ thống đích.
5. Consumer nhận thông điệp, kiểm tra hợp đồng và xử lý nghiệp vụ của chính nó.

Ranh giới transaction cần được thiết kế cẩn thận. Nếu thông điệp được gửi trước khi transaction nghiệp vụ commit, consumer có thể nhìn thấy một thay đổi chưa được lưu thành công. Với luồng cần nhất quán, hãy cấu hình publication để externalization chỉ diễn ra sau commit và dùng cơ chế lưu publication bền vững phù hợp. Spring Modulith Event Publication Registry có thể theo dõi trạng thái xử lý publication; cấu hình persistence và transaction quyết định khả năng phục hồi khi ứng dụng dừng đột ngột.

Việc listener externalization hoàn tất thường chỉ cho biết thao tác gửi của listener đã hoàn tất theo adapter. Điều đó không đồng nghĩa consumer cuối cùng đã xử lý thành công nghiệp vụ. Trạng thái xác nhận ở broker và trạng thái xử lý ở consumer là hai chặng khác nhau; nếu cần xác nhận nghiệp vụ đầu cuối, phải thiết kế acknowledgement hoặc event phản hồi riêng.

## 5. Thiết kế hợp đồng integration event

Consumer bên ngoài có thể được viết bằng ngôn ngữ và công nghệ khác. Vì vậy, payload nên thể hiện hợp đồng dữ liệu ổn định, không phụ thuộc vào class nội bộ của ứng dụng phát.

Một integration event nên cân nhắc các trường sau:

| Trường | Ý nghĩa |
| --- | --- |
| `eventId` | Định danh duy nhất để consumer nhận biết thông điệp trùng lặp |
| `eventType` | Tên loại sự kiện theo hợp đồng công bố |
| `schemaVersion` | Phiên bản cấu trúc payload |
| `occurredAt` | Thời điểm sự kiện nghiệp vụ xảy ra |
| `aggregateId` | Định danh đối tượng nghiệp vụ liên quan, ví dụ `orderId` |
| `correlationId` | Liên kết các thao tác thuộc cùng một luồng nghiệp vụ |
| `payload` | Dữ liệu tối thiểu consumer cần để xử lý |

Không phải mọi event đều cần đúng các trường trên; hãy chọn theo hợp đồng thực tế. Điểm quan trọng là định danh, ý nghĩa và cách diễn giải payload phải được thống nhất giữa bên phát và bên nhận.

Ưu tiên sự kiện mô tả một sự thật nghiệp vụ đã xảy ra, thường dùng tên ở thì quá khứ như `OrderConfirmed` hoặc `PaymentCaptured`. Tránh biến event thành command yêu cầu consumer thực hiện một hành động cụ thể. Event nói rằng một việc đã xảy ra; consumer tự quyết định có cần phản ứng hay không.

Payload nên nhỏ và chứa đủ dữ liệu cho consumer. Nếu chỉ gửi ID rồi yêu cầu consumer gọi ngược API của bên phát để lấy mọi thông tin, sự phụ thuộc thời gian chạy có thể quay trở lại. Ngược lại, gửi toàn bộ entity nội bộ sẽ làm lộ implementation và khiến việc thay đổi model trở nên khó khăn.

## 6. Ví dụ phát một event cần externalize

Ví dụ sau minh họa module nghiệp vụ phát một application event khi xác nhận đơn hàng. Event type đã được đánh dấu bằng `@Externalized`; phần cấu hình externalization và adapter sẽ ánh xạ target `orders` tới hạ tầng messaging của môi trường:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderApplicationService {

    private final ApplicationEventPublisher events;
    private final OrderRepository orders;

    OrderApplicationService(
            ApplicationEventPublisher events,
            OrderRepository orders) {
        this.events = events;
        this.orders = orders;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.getRequired(orderId);
        order.confirm();

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                orderId,
                Instant.now(),
                1));
    }
}
~~~

Đoạn mã tập trung vào việc công bố sự kiện. Repository, model và cấu hình externalization là thành phần của ứng dụng thực tế. Khi chạy production, cần bảo đảm event publication được phối hợp đúng với transaction và được lưu bền vững nếu yêu cầu nghiệp vụ không cho phép mất thông điệp khi tiến trình dừng.

## 7. Độ tin cậy, retry và xử lý trùng

Không nên giả định thông điệp chỉ được giao đúng một lần. Khi gửi thành công nhưng ứng dụng chưa kịp ghi nhận publication hoàn tất, một lần retry có thể gửi lại cùng event. Consumer cũng có thể nhận lại thông điệp do cơ chế retry của broker hoặc do sự cố mạng.

Vì vậy, consumer nên idempotent: xử lý cùng một `eventId` nhiều lần không làm nghiệp vụ bị áp dụng lặp. Một cách thường dùng là lưu event ID đã xử lý trong cùng transaction với thay đổi nghiệp vụ của consumer. Nếu ID đã tồn tại, consumer có thể bỏ qua lần giao lặp.

Event Publication Registry giúp theo dõi publication tới listener và hỗ trợ xử lý các publication chưa hoàn tất khi ứng dụng được cấu hình persistence phù hợp. Retry cần có giới hạn, khoảng chờ và cơ chế xử lý lỗi cuối cùng. Thông điệp lỗi kéo dài nên được quan sát và chuyển tới quy trình điều tra hoặc dead-letter phù hợp với broker.

Externalization không tự bảo đảm thứ tự toàn cục. Nếu thứ tự theo từng đơn hàng quan trọng, hãy chọn partition key hoặc routing key ổn định dựa trên aggregate ID, đồng thời bảo đảm consumer xử lý tuần tự trong phạm vi cần thiết. Nếu hai event có thể đến sai thứ tự, consumer nên kiểm tra version hoặc sequence của aggregate trước khi áp dụng.

## 8. Bảo mật và tiến hóa schema

Integration event là dữ liệu rời khỏi ranh giới ứng dụng. Trước khi công bố, hãy xem xét:

- Không đưa mật khẩu, token, bí mật hệ thống hoặc dữ liệu cá nhân không cần thiết vào payload.
- Dùng TLS và cơ chế xác thực phù hợp cho kết nối broker; giới hạn quyền publish và subscribe theo destination.
- Xác định retention, quyền truy cập và quy trình xóa dữ liệu ở broker cũng như các hệ thống tiêu thụ.
- Có chiến lược tương thích schema: ưu tiên thay đổi bổ sung có khả năng tương thích, quản lý phiên bản và thông báo khi có thay đổi phá vỡ hợp đồng.
- Tránh tái sử dụng tên event cho một ý nghĩa nghiệp vụ khác sau khi consumer đã phụ thuộc vào nó.

Khi thay đổi payload, cần xem xét cả consumer đang chạy phiên bản cũ. Có thể triển khai theo hướng consumer chấp nhận cả schema cũ và mới, sau đó mới nâng cấp publisher; với thay đổi không tương thích, hãy công bố event type hoặc version mới và có kế hoạch chuyển đổi rõ ràng.

## 9. Kiểm thử và quan sát

Kiểm thử externalization nên bao gồm nhiều lớp:

1. Kiểm thử mapping: event nghiệp vụ được chuyển thành target và payload đúng hợp đồng.
2. Kiểm thử transaction: xác minh thông điệp chỉ được externalize ở thời điểm phù hợp với commit của nghiệp vụ.
3. Kiểm thử adapter: xác minh serializer, destination và header được cấu hình đúng.
4. Kiểm thử lỗi: mô phỏng broker không sẵn sàng, timeout và retry; kiểm tra publication còn có thể được phục hồi.
5. Kiểm thử consumer: gửi lặp cùng event ID và xác minh nghiệp vụ không bị áp dụng hai lần.

Theo dõi số publication đang chờ, tuổi publication lâu nhất, số lần retry, lỗi gửi, thời gian gửi và số thông điệp bị chuyển sang dead-letter. Dùng event ID và correlation ID để lần theo một luồng qua publisher, broker và consumer. Log không nên chứa toàn bộ payload nếu payload có dữ liệu nhạy cảm.

## 10. Khi nào nên externalize?

Nên externalize khi một sự kiện nghiệp vụ cần được nhiều hệ thống độc lập tiêu thụ, khi muốn giảm kết nối đồng bộ giữa các hệ thống, hoặc khi consumer có thể xử lý bất đồng bộ theo nhịp riêng.

Không cần externalize mọi application event. Event chỉ phục vụ một listener nội bộ, chứa chi tiết implementation hoặc thay đổi thường xuyên có thể nên giữ trong ranh giới ứng dụng. Mỗi integration event tạo ra một hợp đồng mà publisher phải duy trì và consumer phải hiểu; chỉ công bố những sự kiện có ý nghĩa ngoài ranh giới đó.

## Kết luận

Event externalization đưa sự kiện từ bên trong ứng dụng ra hệ thống bên ngoài thông qua một hợp đồng integration event và hạ tầng messaging. Spring Modulith cung cấp cách đánh dấu và tổ chức externalization, còn adapter và cấu hình môi trường đảm nhiệm việc gửi tới destination cụ thể. Muốn giao sự kiện đáng tin cậy, cần phối hợp transaction, publication tracking, retry, idempotency, versioning, bảo mật và quan sát từ đầu đến cuối.
