# Event phụ thuộc entity

Trong Spring Modulith, application event là hợp đồng thông báo giữa các module. Một anti-pattern thường gặp là publish trực tiếp JPA entity làm event, hoặc để event chứa tham chiếu tới entity và các quan hệ của nó. Cách làm này khiến listener phụ thuộc vào persistence model, có thể kích hoạt lazy loading ngoài transaction, làm lộ cấu trúc nội bộ của module và tạo payload khó serialize.

Event nên mô tả một sự kiện nghiệp vụ đã xảy ra bằng dữ liệu bất biến, có ý nghĩa rõ ràng với consumer. Thông thường, hãy tạo một event DTO riêng chứa định danh, version và những giá trị cần thiết; không dùng entity đang được Hibernate quản lý làm hợp đồng giao tiếp.

## 1. Anti-pattern: publish trực tiếp JPA entity

Ví dụ module Orders tải một đơn hàng, thay đổi trạng thái rồi publish chính entity đó:

~~~java
@Transactional
public void confirm(UUID orderId) {
    Order order = orders.findRequired(orderId);
    order.confirm();

    events.publishEvent(order);
}
~~~

Listener nhận entity và đọc các quan hệ của nó:

~~~java
@ApplicationModuleListener
void on(Order order) {
    String customerEmail = order.getCustomer().getEmail();
    var lines = order.getLines();
    // Cập nhật projection hoặc gọi dịch vụ khác.
}
~~~

Đoạn code có vẻ ngắn, nhưng biến entity `Order` thành hợp đồng giữa publisher và listener. Listener biết class persistence, tên association, cách Hibernate tải quan hệ và cấu trúc bảng của module Orders. Khi entity đổi vì yêu cầu lưu trữ, consumer cũng có thể phải đổi dù nghiệp vụ không thay đổi.

## 2. Vì sao event phụ thuộc entity nguy hiểm?

### 2.1. Lazy loading và persistence context

JPA thường tải association theo chiến lược lazy. Khi listener chạy bất đồng bộ sau khi transaction phát event commit, persistence context ban đầu có thể đã đóng. Truy cập `order.getCustomer()` hoặc `order.getLines()` khi đó có thể gây `LazyInitializationException`.

Ngay cả khi listener chạy trong transaction riêng, entity được truyền qua event vẫn có thể là detached object hoặc proxy gắn với persistence context cũ. Việc truy cập association có thể thất bại hoặc kích hoạt truy vấn ngoài dự kiến.

### 2.2. Truy vấn ẩn và N+1

Một listener xử lý danh sách event có thể chạm vào từng association lazy. Một lần xử lý ban đầu tưởng chỉ có một truy vấn lại phát sinh thêm nhiều truy vấn cho customer, lines, product hoặc address. Khi dữ liệu tăng, listener chậm, giữ connection lâu và tạo backlog.

### 2.3. Chu kỳ tham chiếu và payload khó serialize

Entity thường có quan hệ hai chiều, ví dụ `Order` tham chiếu `Customer`, còn `Customer` có danh sách `Order`. Serializer có thể gặp vòng lặp tham chiếu, tạo payload quá lớn hoặc cần cấu hình Jackson đặc biệt. Hibernate proxy và persistent collection cũng có thể không serialize theo định dạng mà consumer mong đợi.

### 2.4. Entity là mutable state

Entity có thể tiếp tục thay đổi trong transaction hoặc được listener sửa ngoài dự kiến. Event cần biểu diễn sự thật đã xảy ra tại một thời điểm; nếu payload giữ tham chiếu tới mutable object, ý nghĩa của event không còn rõ ràng và khó tái hiện khi retry.

### 2.5. Rò rỉ ranh giới module

Entity phản ánh mô hình lưu trữ và quy tắc nội bộ của module sở hữu nó. Consumer không nên phụ thuộc vào entity class, association hay repository nội bộ của module khác. Nếu entity thay đổi, các module tiêu thụ bị kéo theo, làm mất lợi ích giảm coupling của application events.

### 2.6. Rủi ro dữ liệu và bảo mật

Entity có thể chứa trường không dành cho consumer như thông tin cá nhân, dữ liệu thanh toán, ghi chú nội bộ hoặc thuộc tính phục vụ persistence. Publish nguyên entity dễ vô tình đưa dữ liệu thừa vào log, broker, retry topic hoặc hệ thống ngoài.

## 3. Event DTO mô tả sự kiện nghiệp vụ

Hãy định nghĩa một kiểu riêng cho event. Ví dụ, `OrderConfirmed` mô tả đơn hàng đã được xác nhận, không mô tả cách entity `Order` được lưu:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        Instant occurredAt,
        UUID customerId,
        BigDecimal totalAmount,
        String currency) {
}
~~~

Record giúp thể hiện dữ liệu bất biến ở mức tham chiếu: các component không thể được gán lại sau khi tạo. Hãy dùng kiểu giá trị bất biến như `UUID`, `Instant`, `String`, `BigDecimal` và value object bất biến. Với collection, tạo bản sao bất biến, ví dụ `List.copyOf(lines)`; không đưa `PersistentCollection` của Hibernate vào event.

Event nên chứa đủ dữ liệu để consumer thực hiện trách nhiệm của mình, nhưng không nên mang toàn bộ aggregate graph. Chỉ đưa field cần thiết, có ý nghĩa và được phép chia sẻ qua ranh giới module.

## 4. Tạo event từ aggregate trong transaction

Publisher có thể lấy các giá trị cần thiết từ aggregate khi persistence context còn hợp lệ, sau đó tạo event DTO:

~~~java
import java.time.Clock;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findRequired(orderId);
        order.confirm();

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                order.id(),
                order.version(),
                clock.instant(),
                order.customerId(),
                order.totalAmount(),
                order.currency()));
    }
}
~~~

Event được tạo từ trạng thái nghiệp vụ trong transaction, nhưng không giữ tham chiếu tới entity. Với Spring Modulith, listener dùng `@ApplicationModuleListener` có thể xử lý bất đồng bộ sau khi transaction nguồn commit theo cơ chế của framework. Listener nhận một payload độc lập với persistence context của publisher.

## 5. Listener xử lý DTO thay vì entity

Consumer chỉ phụ thuộc vào event contract:

~~~java
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    private final OrderProjectionService projection;

    OrderProjectionListener(OrderProjectionService projection) {
        this.projection = projection;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        projection.apply(
                event.eventId(),
                event.orderId(),
                event.aggregateVersion(),
                event.occurredAt(),
                event.customerId(),
                event.totalAmount(),
                event.currency());
    }
}
~~~

Listener không cần biết `Order` là entity, được lưu bằng bảng nào hoặc `Customer` được ánh xạ ra sao. Khi module Orders thay đổi quan hệ JPA nhưng vẫn giữ event contract, consumer không cần thay đổi.

## 6. Khi nào nên gửi ID, khi nào nên gửi snapshot?

Không có quy tắc rằng mọi event chỉ nên chứa ID. Chọn payload theo ý nghĩa nghiệp vụ và nhu cầu consumer:

| Kiểu dữ liệu | Dùng khi | Lưu ý |
| --- | --- | --- |
| Chỉ aggregate ID | Consumer cần tra cứu trạng thái hiện tại qua API/module sở hữu dữ liệu | Dữ liệu đọc được có thể đã thay đổi so với thời điểm event phát sinh |
| ID và snapshot các field cần thiết | Consumer cần biết chính xác giá trị tại thời điểm sự kiện xảy ra | Chỉ đưa field có ý nghĩa và được phép chia sẻ |
| Value object nhỏ, bất biến | Giá trị là một phần của sự thật nghiệp vụ, ví dụ tiền tệ hoặc địa chỉ giao hàng tại lúc đặt hàng | Đảm bảo kiểu dữ liệu ổn định và serialize được |
| Toàn bộ entity/aggregate graph | Không nên dùng làm event contract | Gây coupling, lazy loading, payload lớn và lộ mô hình lưu trữ |

Ví dụ, `OrderConfirmed` cần lưu `totalAmount` tại thời điểm xác nhận nếu consumer xây dựng báo cáo lịch sử. Nếu consumer chỉ cần trạng thái đơn hàng hiện tại, có thể gửi `orderId` rồi gọi API được công bố bởi module Orders để đọc dữ liệu mới nhất.

Đừng gửi ID rồi mặc định consumer sẽ nhận được trạng thái đúng với thời điểm event. Khi listener chạy trễ, aggregate có thể đã chuyển từ CONFIRMED sang CANCELLED. Nếu consumer cần dữ liệu lịch sử, payload phải mang snapshot hoặc tham chiếu tới một phiên bản bất biến có thể truy xuất.

## 7. Không truy cập repository nội bộ của module khác

Event DTO giải quyết coupling với entity, nhưng consumer vẫn có thể vi phạm ranh giới module nếu inject trực tiếp repository nội bộ của module phát.

Ví dụ không nên:

~~~java
@Component
class ShippingListener {

    private final OrderJpaRepository orderJpaRepository;

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        Order order = orderJpaRepository.findById(event.orderId())
                .orElseThrow();
        // Dùng entity nội bộ của Orders.
    }
}
~~~

Nếu cần trạng thái mới nhất, hãy dùng một application service hoặc query API được module sở hữu công bố rõ ràng. Consumer phụ thuộc vào contract công khai, không phụ thuộc vào repository hay entity implementation.

~~~java
import java.util.Optional;
import java.util.UUID;

public interface OrderQuery {
    Optional<OrderDetails> findDetails(UUID orderId);
}
~~~

`OrderDetails` ở đây là read model/DTO công khai do module Orders định nghĩa. Consumer có thể dùng API đó để lấy dữ liệu hiện tại. Nếu cần snapshot lịch sử, hãy lấy thông tin từ event thay vì query trạng thái hiện tại.

## 8. Event nội bộ và integration event

Không phải event nội bộ nào cũng cần trở thành hợp đồng bên ngoài. Có thể tách domain/application event dùng trong nội bộ module khỏi integration event được công bố cho module khác hoặc hệ thống khác.

- **Event nội bộ:** phục vụ điều phối trong module; có thể chứa kiểu nội bộ nếu không vượt ranh giới và không bị lưu/serialize theo cách làm lộ implementation.
- **Integration event:** contract công khai, dùng DTO độc lập, có version, schema và chính sách tương thích.

Với event được externalize bằng Spring Modulith, hãy xem payload như một message contract có thể được lưu, serialize, retry và tiêu thụ bởi phiên bản ứng dụng khác. Tránh đưa JPA entity vào event được đánh dấu `@Externalized`.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.modulith.events.Externalized;

@Externalized("orders")
public record OrderConfirmedIntegrationEvent(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        Instant occurredAt,
        BigDecimal totalAmount,
        String currency) {
}
~~~

Đây là ví dụ contract integration riêng. Có thể ánh xạ từ domain event sang integration event tại ranh giới module để tránh lộ chi tiết nội bộ. `@Externalized` đánh dấu event cần externalize; adapter và cấu hình tích hợp vẫn quyết định cách serialize, định tuyến và gửi message.

## 9. Tránh event mang collection entity

Một biến thể của anti-pattern là gửi danh sách entity hoặc association:

~~~java
import java.util.List;

public record OrderBatchConfirmed(
        List<Order> orders) {
}
~~~

Payload này có thể chứa hàng trăm entity, quan hệ hai chiều, proxy lazy và collection do Hibernate quản lý. Nó làm message lớn, khó retry, khó versioning và khiến consumer phụ thuộc vào toàn bộ mô hình Orders.

Nếu nghiệp vụ thực sự xác nhận nhiều đơn hàng, hãy xác định contract rõ:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record OrderBatchConfirmed(
        UUID batchId,
        Instant occurredAt,
        List<ConfirmedOrderSummary> orders) {

    public OrderBatchConfirmed {
        orders = List.copyOf(orders);
    }
}

public record ConfirmedOrderSummary(
        UUID orderId,
        long aggregateVersion,
        BigDecimal totalAmount,
        String currency) {
}
~~~

Chỉ đưa những giá trị cần thiết vào summary. Với batch lớn, cân nhắc phát event theo từng aggregate hoặc phát một event báo batch đã sẵn sàng kèm `batchId` để consumer lấy dữ liệu qua API được công bố.

## 10. Entity thay đổi không nên làm event contract thay đổi

Giả sử entity `Order` được tái cấu trúc:

- Đổi tên field `customer` thành `buyer`.
- Tách `totalAmount` thành value object `Money`.
- Chuyển quan hệ `lines` sang bảng riêng.
- Thêm `@OneToMany`, `@ManyToOne` hoặc đổi fetch strategy.

Nếu event đang chứa entity, những thay đổi persistence này có thể làm consumer compile lỗi hoặc deserialize lỗi. Với event DTO độc lập, module có thể thay đổi mapping JPA mà vẫn giữ contract cũ.

Chỉ thay event DTO khi hợp đồng nghiệp vụ thực sự thay đổi. Khi đó, áp dụng versioning và migration có kế hoạch; không để thay đổi schema database tự động quyết định version event.

## 11. Idempotency và event snapshot

Event DTO nên có `eventId` ổn định, aggregate ID và version nếu consumer cần phát hiện trùng hoặc sai thứ tự. Listener có thể ghi dấu event đã xử lý cùng transaction với cập nhật projection:

~~~java
@Transactional
public void apply(OrderConfirmed event) {
    if (processedEvents.existsById(event.eventId())) {
        return;
    }

    projectionRepository.upsert(OrderSummary.from(event));
    processedEvents.save(new ProcessedEvent(event.eventId()));
}
~~~

Ví dụ này giả định kiểm tra trùng, cập nhật projection và ghi processed event nằm trong cùng transaction; unique constraint trên `eventId` cần bảo vệ các lần xử lý đồng thời. Nếu listener gọi API ngoài, transaction database không thể rollback side effect từ xa; cần idempotency key ở hệ thống đích.

Snapshot trong event cũng cần có semantics rõ. `totalAmount` là số tiền tại thời điểm xác nhận, không phải số tiền hiện tại nếu đơn hàng sau đó được điều chỉnh. Tên field và tài liệu event nên chỉ rõ thời điểm, đơn vị, currency và ý nghĩa.

## 12. Kiểm thử để ngăn event phụ thuộc entity

Kiểm thử nên chứng minh event contract độc lập với entity:

1. Publish event và xác minh listener nhận DTO với đúng dữ liệu.
2. Đóng persistence context hoặc xử lý listener bất đồng bộ để xác minh payload không cần lazy loading.
3. Serialize và deserialize event DTO để xác minh contract có thể lưu hoặc externalize.
4. Thay đổi fetch strategy hoặc mapping entity trong test fixture và xác minh event contract không đổi.
5. Kiểm tra event không chứa entity, Hibernate proxy hoặc persistent collection.
6. Xác minh consumer chỉ dùng API/DTO công khai, không inject repository nội bộ của module phát.
7. Giao cùng event nhiều lần và xác minh idempotency.
8. Kiểm tra payload không chứa field nhạy cảm hoặc dữ liệu ngoài nhu cầu consumer.

Test serialize nên dùng đúng serializer/converter của integration path khi event được externalize. Test một record Java bằng ObjectMapper mặc định chưa đủ chứng minh adapter production tạo đúng wire contract.

## 13. Checklist thiết kế event an toàn

Trước khi publish event, hãy kiểm tra:

- Event mô tả một sự thật nghiệp vụ đã xảy ra, không phải entity persistence.
- Payload dùng DTO/record và các giá trị bất biến.
- Không chứa JPA entity, Hibernate proxy hoặc persistent collection.
- Không phụ thuộc vào lazy loading hay persistence context của publisher.
- Chỉ chứa field consumer thực sự cần và được phép nhận.
- Có event ID, aggregate ID/version và timestamp khi nghiệp vụ cần.
- Snapshot và ID-reference có semantics rõ ràng.
- Consumer không truy cập repository nội bộ của module phát.
- Integration event có contract/version ổn định.
- Retry, replay và serialization không phụ thuộc trạng thái Hibernate.

## 14. Những sai lầm cần tránh

- Publish trực tiếp entity bằng `events.publishEvent(order)`.
- Để listener đọc association lazy sau khi transaction nguồn đã kết thúc.
- Dùng `EAGER` cho mọi quan hệ chỉ để listener đọc được entity.
- Serialize entity graph với annotation Jackson để che vòng lặp thay vì thiết kế event contract.
- Đưa collection entity lớn vào một event.
- Dùng entity class của module khác trong signature listener.
- Chỉ gửi ID dù consumer cần snapshot lịch sử tại thời điểm event phát sinh.
- Gửi quá nhiều field nhạy cảm vì entity đã có sẵn chúng.
- Coi thay đổi mapping JPA là thay đổi event contract.

## Kết luận

Event phụ thuộc entity là anti-pattern vì nó gắn hợp đồng giao tiếp với persistence model, tạo rủi ro lazy loading, serialization, mutable state và vi phạm ranh giới module. Trong Spring Modulith, hãy tạo event DTO bất biến từ dữ liệu nghiệp vụ cần thiết trong transaction, để listener xử lý payload độc lập với JPA. Chọn ID hay snapshot theo ý nghĩa event, dùng API công khai khi cần trạng thái hiện tại và giữ integration event ổn định qua versioning. Nhờ vậy, entity có thể thay đổi bên trong module mà consumer vẫn hoạt động theo contract rõ ràng.
