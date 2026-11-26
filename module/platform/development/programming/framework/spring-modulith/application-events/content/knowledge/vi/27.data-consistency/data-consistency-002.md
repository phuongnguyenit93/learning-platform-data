# Eventual consistency

Trong một ứng dụng Spring Modulith, các module có thể giao tiếp qua application events thay vì gọi trực tiếp implementation của nhau. Khi module phát một event và listener xử lý bất đồng bộ sau khi transaction nguồn đã commit, dữ liệu ở module nhận sẽ được cập nhật sau một khoảng thời gian. Trong khoảng đó, hai module có thể nhìn thấy trạng thái khác nhau. Đây là eventual consistency, hay tính nhất quán cuối cùng.

Eventual consistency giúp giảm phụ thuộc thời gian chạy và cho phép từng phần của ứng dụng xử lý công việc theo nhịp riêng. Đổi lại, thiết kế phải tính đến độ trễ, dữ liệu đọc có thể cũ, xử lý trùng, thứ tự event và khả năng phục hồi khi listener lỗi.

## 1. Eventual consistency là gì?

Eventual consistency là mô hình trong đó các bản sao hoặc read model được cập nhật bất đồng bộ. Nếu không có thêm thay đổi mới và các event đang chờ được xử lý thành công, các mô hình dữ liệu liên quan sẽ hội tụ về trạng thái phản ánh cùng một sự thật nghiệp vụ.

Ví dụ, module Orders xác nhận đơn hàng trong database của nó rồi phát `OrderConfirmed`. Module Inventory nhận event và cập nhật số lượng cần giữ. Ngay sau khi Orders commit, đơn hàng đã ở trạng thái CONFIRMED nhưng Inventory có thể chưa cập nhật. Một lát sau listener hoàn tất và hai phần dữ liệu đạt trạng thái phù hợp.

~~~mermaid
sequenceDiagram
    participant O as Orders
    participant DB as Orders DB
    participant E as Application event
    participant I as Inventory listener
    participant IDB as Inventory DB
    O->>DB: Lưu trạng thái CONFIRMED
    DB-->>O: Commit
    O->>E: Publish OrderConfirmed
    E-->>I: Giao event bất đồng bộ
    I->>IDB: Cập nhật tồn kho
    IDB-->>I: Commit
~~~

Điểm quan trọng là lệnh xác nhận đơn hàng không phải chờ Inventory hoàn thành mới commit. Vì vậy, eventual consistency không hứa rằng mọi module nhìn thấy dữ liệu mới ngay lập tức hoặc trong một thời hạn cố định. Độ trễ phụ thuộc tải, lịch xử lý, lỗi listener, kết nối database và khả năng phục hồi.

## 2. Vì sao chọn eventual consistency?

Eventual consistency phù hợp khi một thay đổi nghiệp vụ cần thông báo cho nhiều phần khác của hệ thống, nhưng không cần tất cả cùng cập nhật trong một transaction đồng bộ.

- Giảm phụ thuộc trực tiếp: module phát event không cần biết listener nào đang tồn tại hoặc cách listener lưu dữ liệu.
- Giảm thời gian phản hồi: use case chính có thể hoàn tất sau khi transaction của nó commit.
- Tăng khả năng mở rộng: listener có thể xử lý bất đồng bộ và mở rộng tài nguyên riêng.
- Cô lập lỗi: lỗi ở một listener không nhất thiết làm rollback transaction nghiệp vụ đã commit.
- Hỗ trợ nhiều read model: các listener khác nhau có thể xây dựng projection theo nhu cầu truy vấn riêng.

Đổi lại, hệ thống phải chấp nhận và quản lý khoảng thời gian dữ liệu chưa hội tụ. Nếu một quyết định cần dữ liệu mới nhất ngay trong cùng use case, hãy đặt invariant đó trong module sở hữu dữ liệu và kiểm tra đồng bộ tại ranh giới nghiệp vụ phù hợp.

## 3. Luồng event trong Spring Modulith

Spring Modulith cung cấp cách tổ chức application events giữa các module. Module sở hữu nghiệp vụ phát event mô tả điều đã xảy ra. Module tiêu thụ đăng ký listener và xử lý event theo trách nhiệm của mình.

Ví dụ, Orders phát event khi đơn hàng được xác nhận:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        Instant occurredAt) {
}
~~~

Use case cập nhật trạng thái đơn hàng và publish event trong cùng transaction:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findRequired(orderId);
        order.confirm();

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                order.id(),
                order.version(),
                Instant.now()));
    }
}
~~~

Module Inventory xử lý event bằng `@ApplicationModuleListener`:

~~~java
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOnOrderConfirmed {

    private final InventoryProjectionService projections;

    InventoryOnOrderConfirmed(InventoryProjectionService projections) {
        this.projections = projections;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        projections.apply(event);
    }
}
~~~

`@ApplicationModuleListener` được thiết kế cho việc xử lý application event bất đồng bộ sau khi transaction phát event commit và cung cấp transaction riêng cho listener theo cấu hình của Spring Modulith. Vì transaction Orders đã commit trước khi listener xử lý, lỗi ở Inventory không thể rollback việc xác nhận đơn hàng. Listener phải có chiến lược retry và phục hồi riêng.

Đặt event contract ở ranh giới module phù hợp và chỉ công bố dữ liệu mà consumer cần. Module phát event không nên phụ thuộc vào class repository hoặc entity nội bộ của module nhận.

## 4. Khoảng trễ và dữ liệu đọc cũ

Giữa thời điểm event được publish và thời điểm listener commit có một khoảng trễ. Trong thời gian đó, read model của module nhận có thể chưa phản ánh thay đổi mới nhất.

Ví dụ: API xác nhận đơn hàng trả về trạng thái CONFIRMED, nhưng màn hình tồn kho vẫn hiển thị số lượng trước khi listener xử lý `OrderConfirmed`. Đây không nhất thiết là lỗi nếu hợp đồng của màn hình cho phép dữ liệu trễ.

Ứng dụng cần xác định độ trễ chấp nhận được theo từng luồng. Một màn hình tổng hợp có thể chấp nhận vài giây; một quyết định giữ chỗ tồn kho có thể cần kiểm tra đồng bộ trong module Inventory trước khi xác nhận kết quả cho khách hàng.

Các khái niệm thường gặp:

| Khái niệm | Ý nghĩa | Cách xử lý thường dùng |
| --- | --- | --- |
| Eventual consistency | Dữ liệu sẽ hội tụ khi các cập nhật đang chờ được xử lý | Theo dõi độ trễ và backlog |
| Stale read | Người đọc thấy dữ liệu cũ hơn trạng thái nguồn | Hiển thị thời điểm cập nhật hoặc trạng thái đang đồng bộ |
| Read-your-writes | Người dùng nhìn thấy thay đổi do chính thao tác vừa thực hiện | Trả kết quả từ nguồn ghi hoặc chờ projection đạt version yêu cầu |
| Monotonic read | Các lần đọc liên tiếp không quay lùi về phiên bản cũ hơn | Gắn version và định tuyến đọc nhất quán |

Không nên hứa một thời gian hội tụ tuyệt đối nếu hệ thống không có SLA và cơ chế đo lường tương ứng. Hãy định nghĩa mục tiêu như độ trễ p95/p99, thời gian backlog tối đa và cách ứng dụng phản hồi khi vượt ngưỡng.

## 5. Thiết kế trải nghiệm khi dữ liệu chưa đồng bộ

API và giao diện cần thể hiện rõ sự khác nhau giữa trạng thái nghiệp vụ đã commit và trạng thái của projection.

Ví dụ, sau khi xác nhận đơn hàng, API có thể trả về:

~~~json
{
  "orderId": "...",
  "status": "CONFIRMED",
  "projectionStatus": "PENDING"
}
~~~

`projectionStatus` là ví dụ về trạng thái đồng bộ mà ứng dụng có thể cung cấp nếu nghiệp vụ cần. Không phải mọi API đều cần trường này; chỉ đưa vào hợp đồng khi client cần biết dữ liệu phụ thuộc đang chờ cập nhật.

Một số cách hỗ trợ read-your-writes:

- Trả trực tiếp trạng thái vừa commit từ module sở hữu dữ liệu thay vì đọc ngay projection bất đồng bộ.
- Cung cấp endpoint truy vấn trạng thái xử lý hoặc thời điểm projection được cập nhật gần nhất.
- Đưa aggregate version vào response và projection; client có thể chờ projection đạt version tối thiểu.
- Dùng polling, server-sent events hoặc WebSocket để thông báo khi projection đã bắt kịp.
- Với truy vấn quan trọng, đọc từ nguồn có thẩm quyền thay vì từ read model có độ trễ.

Không nên bắt request đồng bộ chờ vô hạn một listener bất đồng bộ. Nếu client cần chờ, đặt timeout rõ ràng và có phản hồi phù hợp khi projection chưa sẵn sàng.

## 6. Đặt invariant ở đúng ranh giới

Eventual consistency không phù hợp để kiểm tra mọi quy tắc nghiệp vụ. Hãy phân biệt invariant cần đúng ngay với dữ liệu dẫn xuất có thể cập nhật sau.

| Yêu cầu | Nơi nên bảo đảm |
| --- | --- |
| Một đơn hàng không được xác nhận nếu thanh toán chưa hợp lệ | Use case/module sở hữu quy tắc xác nhận, kiểm tra trong transaction phù hợp |
| Số liệu dashboard cập nhật sau khi đơn hàng thay đổi | Projection listener, chấp nhận độ trễ có giới hạn |
| Một mã coupon không được sử dụng vượt số lượt cho phép | Module sở hữu coupon và cơ chế đồng bộ/atomic phù hợp |
| Báo cáo tổng hợp doanh thu cập nhật sau khi giao dịch commit | Read model hoặc pipeline tổng hợp bất đồng bộ |

Nếu hai module cùng cần quyết định trên một invariant, hãy xác định module nào sở hữu quyết định và cung cấp một API hoặc quy trình nghiệp vụ rõ ràng. Không dựa vào projection có thể cũ để cho phép hai transaction đồng thời tiêu thụ cùng một tài nguyên.

## 7. Idempotency và xử lý event trùng

Listener bất đồng bộ có thể được gọi lại khi ứng dụng phục hồi publication chưa hoàn tất hoặc khi có cơ chế retry. Vì vậy, không được giả định một event chỉ được xử lý đúng một lần.

Payload nên có `eventId` ổn định. Listener có thể lưu ID đã xử lý cùng transaction với cập nhật projection:

~~~java
@Transactional
public void apply(OrderConfirmed event) {
    if (processedEvents.existsById(event.eventId())) {
        return;
    }

    projectionRepository.updateFrom(event);
    processedEvents.save(new ProcessedEvent(event.eventId()));
}
~~~

Đây là ví dụ khái niệm. Kiểm tra trùng, cập nhật projection và ghi dấu event cần có tính nguyên tử. Một unique constraint trên `eventId` giúp xử lý trường hợp hai lần giao đồng thời. Nếu listener gọi hệ thống ngoài, transaction database không thể rollback side effect từ xa; cần idempotency key ở hệ thống đích hoặc một quy trình outbox phù hợp.

Nếu event có version của aggregate, projection có thể bỏ qua event cũ hoặc phát hiện khoảng trống version. Tuy nhiên, chỉ bỏ qua event có version nhỏ hơn chưa đủ nếu event hiện tại phụ thuộc vào một version bị thiếu. Với event dạng delta, cần xử lý gap theo thứ tự; với event chứa snapshot đầy đủ, có thể áp dụng snapshot mới nhất theo version.

## 8. Event Publication Registry và khả năng phục hồi

Spring Modulith Event Publication Registry theo dõi publication của event tới các listener. Khi publication được đăng ký, registry lưu trạng thái xử lý; listener hoàn tất thì publication được đánh dấu hoàn tất. Nếu listener lỗi, publication có thể còn ở trạng thái chưa hoàn tất để hệ thống phát hiện và phục hồi theo cấu hình.

Để tăng độ tin cậy khi ứng dụng dừng hoặc khởi động lại, cần cấu hình registry có persistence bền vững phù hợp với môi trường. Việc lưu registry cùng transaction phát event giúp tránh tình huống nghiệp vụ commit nhưng publication không được ghi nhận, trong phạm vi cấu hình và transaction manager được hỗ trợ.

Registry không phải event store tổng quát. Nó theo dõi trạng thái giao event tới listener; publication hoàn tất có thể được dọn theo retention. Nếu cần lịch sử nghiệp vụ dài hạn hoặc replay toàn bộ event, hãy thiết kế event store, audit log hoặc outbox/archive riêng.

Retry cần phân biệt lỗi tạm thời với lỗi dữ liệu hoặc lỗi logic cố định. Có thể thử lại sau backoff cho lỗi hạ tầng; với event không hợp lệ hoặc listener bug, cần cảnh báo và quy trình điều tra. Theo dõi publication chưa hoàn tất và tuổi của publication lâu nhất để tránh lỗi bị che khuất.

## 9. Thứ tự event và cập nhật đồng thời

Eventual consistency không tự bảo đảm các event được xử lý đúng thứ tự ở mọi listener. Nếu `OrderConfirmed` và `OrderCancelled` được xử lý đồng thời, listener có thể hoàn tất theo thứ tự khác với thứ tự phát.

Với projection phụ thuộc thứ tự, hãy:

- Gắn aggregate ID và version/sequence vào event.
- Cập nhật projection có điều kiện theo version đã áp dụng.
- Phát hiện version bị thiếu và chờ, retry hoặc lấy snapshot mới từ nguồn có thẩm quyền.
- Phân vùng xử lý theo aggregate key nếu hạ tầng hỗ trợ và cần giữ thứ tự trong phạm vi aggregate.
- Tránh giả định có thứ tự toàn cục giữa các module hoặc các partition.

Nếu listener xử lý song song, hãy bảo đảm các cập nhật cùng aggregate không ghi đè dữ liệu mới hơn bằng dữ liệu cũ. Optimistic locking, câu lệnh update có điều kiện hoặc hàng đợi tuần tự theo key có thể được dùng tùy mô hình dữ liệu.

## 10. Eventual consistency giữa các service

Trong cùng ứng dụng, application events có thể cập nhật module khác qua listener. Khi sự kiện vượt ra ngoài tiến trình tới service khác, cần thêm integration event và transport như Kafka hoặc RabbitMQ.

Luồng externalization thường gồm:

1. Module nghiệp vụ thay đổi dữ liệu và publish event trong transaction.
2. Spring Modulith theo dõi publication của listener externalization.
3. Adapter chuyển event thành message và gửi tới broker.
4. Consumer của service nhận message và cập nhật database/read model riêng.

Ở ranh giới broker, cần xét thêm publisher confirms hoặc send result, retry, consumer offset/acknowledgement, schema compatibility và idempotency. Registry của ứng dụng phát theo dõi listener externalization; nó không chứng minh consumer ở service khác đã hoàn thành nghiệp vụ. Nếu cần xác nhận đầu cuối, hãy thiết kế acknowledgement event hoặc trạng thái quy trình riêng.

Không giả định transaction database của service phát và transaction database của service nhận là một transaction nguyên tử. Với quy trình nhiều bước cần bù trừ, có thể dùng Saga/process manager; với việc ghi database và message cần nhất quán, dùng outbox hoặc cơ chế publication bền vững phù hợp.

## 11. Kiểm thử eventual consistency

Kiểm thử cần xác minh cả trạng thái nguồn và trạng thái sau khi listener hoàn tất:

1. Gọi use case và xác nhận transaction nguồn đã commit.
2. Xác minh event được publish với đúng dữ liệu và version.
3. Chờ listener xử lý bằng điều kiện có timeout thay vì sleep cố định.
4. Đọc projection và xác minh nó hội tụ về kết quả mong đợi.
5. Giao cùng event nhiều lần và xác minh side effect không bị nhân đôi.
6. Làm listener thất bại, xác minh publication còn được theo dõi và có thể phục hồi.
7. Gửi event sai thứ tự hoặc version bị thiếu để xác minh quy tắc ordering.
8. Kiểm tra read path trả dữ liệu cũ hoặc trạng thái PENDING theo đúng hợp đồng trong khoảng chờ.

Với Spring Modulith, kiểm thử module nên xác minh event được công bố và listener của module nhận xử lý đúng. Dùng cơ chế đồng bộ hóa trong test hoặc Awaitility để chờ điều kiện cụ thể. Tránh kiểm thử bất đồng bộ bằng cách chờ một khoảng thời gian cố định vì thời gian chạy có thể thay đổi theo máy và tải.

## 12. Quan sát và vận hành

Eventual consistency chỉ vận hành tốt khi độ trễ và backlog được nhìn thấy. Theo dõi các chỉ số:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Event processing lag | Khoảng thời gian từ lúc event phát sinh tới lúc listener hoàn tất |
| Pending publications | Số publication chưa hoàn tất trong registry |
| Oldest pending age | Tuổi của publication tồn đọng lâu nhất |
| Listener success/failure | Tỷ lệ thành công và lỗi theo listener |
| Retry count | Số lần retry theo loại lỗi |
| Projection version lag | Chênh lệch version giữa nguồn và read model |
| Rebuild/catch-up progress | Tiến độ khi projection được dựng lại hoặc bắt kịp live event |

Log nên có event ID, event type, aggregate ID, aggregate version, correlation ID, listener và thời điểm phát sinh/xử lý. Tránh ghi toàn bộ payload nếu chứa dữ liệu nhạy cảm.

Đặt cảnh báo theo SLA của từng luồng. Ví dụ, dashboard có thể chấp nhận projection trễ vài giây, nhưng một quy trình thanh toán có thể yêu cầu cảnh báo sớm hơn nhiều. Khi backlog tăng, xác định listener chậm, dependency lỗi, worker thiếu tài nguyên hay event poison; không chỉ tăng concurrency mà không xem xét thứ tự và giới hạn database.

## 13. Những sai lầm cần tránh

- Giả định listener bất đồng bộ đã chạy xong ngay khi publisher trả về.
- Dùng read model có thể cũ để quyết định invariant cần đúng ngay.
- Coi Event Publication Registry là event store giữ toàn bộ lịch sử.
- Không thiết kế idempotency và xử lý event trùng.
- Không theo dõi tuổi publication pending hoặc độ trễ projection.
- Cho phép nhiều listener cùng cập nhật một dữ liệu mà không xác định quyền sở hữu.
- Retry vô hạn một lỗi dữ liệu hoặc lỗi logic cố định.
- Giả định event được xử lý theo đúng thứ tự publish khi listener chạy song song.
- Coi listener hoàn tất là bằng chứng consumer bên ngoài đã hoàn thành nghiệp vụ.

## Kết luận

Eventual consistency cho phép các module Spring Modulith cập nhật dữ liệu bất đồng bộ qua application events và giảm phụ thuộc trực tiếp. Để mô hình này đáng tin cậy, cần đặt invariant ở đúng module, chấp nhận và đo lường độ trễ, thiết kế read-your-writes, xử lý event trùng và thứ tự bằng version, đồng thời cấu hình Event Publication Registry có persistence và quy trình retry phù hợp. Khi event đi qua broker, phải quan sát riêng việc externalize và việc consumer xử lý. Nhờ vậy, hệ thống có thể hội tụ về trạng thái nhất quán mà vẫn duy trì khả năng phục hồi khi một listener hoặc dependency gặp sự cố.
