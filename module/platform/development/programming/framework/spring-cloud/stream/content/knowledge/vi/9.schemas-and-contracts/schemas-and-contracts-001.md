# Thiết kế hợp đồng sự kiện độc lập với mô hình lưu trữ nội bộ

Trong hệ thống hướng sự kiện, producer và consumer thường do các nhóm khác nhau phát triển, triển khai và mở rộng ở những thời điểm khác nhau. Nếu producer gửi thẳng entity JPA hoặc cấu trúc bảng cơ sở dữ liệu ra broker, thay đổi lưu trữ nội bộ có thể làm hỏng các consumer dù ý nghĩa nghiệp vụ không thay đổi.

Hợp đồng sự kiện cần mô tả sự thật nghiệp vụ mà các service cùng quan tâm. Nó phải ổn định theo ngôn ngữ nghiệp vụ, có phiên bản và được chuyển đổi từ mô hình nội bộ bằng một lớp ánh xạ rõ ràng. Spring Cloud Stream cung cấp binding và binder để vận chuyển hợp đồng đó qua Kafka, RabbitMQ hoặc Pulsar; framework không tự tách hợp đồng khỏi entity nếu ứng dụng gửi trực tiếp entity làm payload.

## 1. Vì sao không gửi trực tiếp entity lưu trữ?

Entity lưu trữ được thiết kế để phục vụ thao tác đọc/ghi trong một service. Nó thường chứa các chi tiết không thuộc hợp đồng liên dịch vụ:

- Khóa chính, khóa ngoại và cấu trúc quan hệ của cơ sở dữ liệu.
- Trường phục vụ optimistic locking, audit nội bộ, soft delete hoặc lazy loading.
- Tên cột và cách biểu diễn dữ liệu phụ thuộc ORM.
- Trạng thái tạm thời, cache, proxy hoặc quan hệ vòng.
- Dữ liệu nhạy cảm hoặc thuộc quyền sở hữu riêng của service.

Ví dụ entity đơn giản:

~~~java
import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    @Column(name = "customer_fk")
    private Long customerDatabaseId;

    private String status;
    private BigDecimal subtotal;
    private BigDecimal discountAmount;
    private BigDecimal totalAmount;
    private String internalRiskFlag;
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    // getters, setters và các hành vi persistence
}
~~~

Nếu producer serialize entity này, consumer có thể vô tình phụ thuộc vào tên cột, ID nội bộ, quan hệ ORM hoặc trường riêng tư. Khi service đổi từ JPA sang document database, chuẩn hóa bảng hoặc thay cách tính chiết khấu, hợp đồng bên ngoài cũng bị thay đổi theo.

Một entity còn có thể kéo theo truy vấn lazy loading, vòng tham chiếu hoặc dữ liệu không cần thiết. Serialize entity trong thời điểm transaction đóng cũng có thể gây lỗi do proxy chưa được tải. Đây là các vấn đề của mô hình lưu trữ bị đưa qua ranh giới giao tiếp.

Hãy xem entity là mô hình nội bộ của producer. Payload phát ra broker là một kiểu dữ liệu công khai được thiết kế riêng cho người nhận.

## 2. Phân biệt mô hình domain, entity và event contract

Ba mô hình có mục đích khác nhau:

| Mô hình | Mục đích | Câu hỏi chính |
|---|---|---|
| Domain model | Thể hiện quy tắc và hành vi nghiệp vụ trong service | Nghiệp vụ cho phép điều gì xảy ra? |
| Persistence model / entity | Lưu và truy vấn trạng thái nội bộ | Dữ liệu được lưu như thế nào? |
| Event contract | Công bố sự kiện và dữ liệu cần thiết cho consumer | Sự thật nghiệp vụ nào đã xảy ra? |

Một service có thể có domain aggregate Order, entity OrderEntity và event OrderPlacedV1. Ba kiểu này có thể chia sẻ một vài giá trị như orderId, nhưng không cần có cùng cấu trúc.

~~~text
                Service Orders
+---------------------------------------------+
| Domain aggregate                            |
|      |                                      |
|      +----> Persistence mapper ----> Entity |
|      |                             Database |
|      |                                      |
|      +----> Event mapper ------> Event DTO  |
+---------------------------------------------+
                                      |
                                      v
                              Outbox / Publisher
                                      |
                                      v
                               Broker destination
                                      |
                                      v
                           Consumer-owned contract
                                      |
                                      v
                             Consumer read model
~~~

Producer sở hữu mô hình lưu trữ và chịu trách nhiệm chuyển đổi sang event contract. Consumer đọc contract rồi ánh xạ sang mô hình riêng của nó. Consumer không cần biết producer đang dùng bảng, entity hay aggregate nào.

## 3. Thiết kế event theo sự thật nghiệp vụ

Một event mô tả điều đã xảy ra, thường dùng tên ở thì quá khứ như OrderPlaced, PaymentAuthorized hoặc ShipmentDispatched. Event không phải lệnh yêu cầu service khác thực hiện hành động. Ví dụ:

- OrderPlaced nói rằng đơn hàng đã được đặt thành công.
- PlaceOrder là command yêu cầu hệ thống đặt đơn.
- OrderPlacementRejected mô tả kết quả từ chối, nếu đó là một sự kiện cần công bố.

Một hợp đồng tốt nên có các đặc điểm:

1. **Ý nghĩa nghiệp vụ rõ ràng:** tên event và trường dữ liệu phản ánh ngôn ngữ mà producer và consumer cùng hiểu.
2. **Độc lập với lưu trữ:** không đưa tên bảng, khóa ngoại nội bộ, tên cột hoặc annotation ORM vào contract.
3. **Bất biến theo thời gian:** event ghi lại sự thật tại thời điểm xảy ra, không thay đổi khi trạng thái hiện tại của aggregate thay đổi.
4. **Đủ dữ liệu cho mục đích tiêu thụ:** consumer có thể xử lý mà không phải truy vấn ngược producer chỉ để hiểu event.
5. **Không công bố dữ liệu thừa:** chỉ chứa trường cần cho nghiệp vụ và các consumer được phép nhận.
6. **Có thể tiến hóa:** bổ sung trường và thay đổi schema theo quy tắc tương thích đã thống nhất.

Ví dụ event OrderPlaced có thể chứa mã đơn hàng công khai, mã khách hàng dùng trong tích hợp, tổng tiền, đơn vị tiền tệ và thời điểm đặt đơn. Nó không cần chứa ID row của bảng orders, tên cột customer_fk hay cờ rủi ro nội bộ.

### Chọn giữa snapshot và tham chiếu

Khi consumer cần dữ liệu tại đúng thời điểm event xảy ra, hãy cân nhắc đưa snapshot cần thiết vào event. Ví dụ OrderPlaced nên chứa tổng tiền và currency tại thời điểm đặt hàng. Nếu chỉ gửi orderId rồi yêu cầu consumer gọi API producer để lấy tổng tiền hiện tại, dữ liệu trả về có thể đã thay đổi sau khi event được phát.

Ngược lại, không nên sao chép toàn bộ aggregate vào mọi event. Chỉ đưa những thuộc tính cần thiết cho mục đích event và các consumer dự kiến. Với dữ liệu lớn, nhạy cảm hoặc thay đổi thường xuyên, có thể gửi tham chiếu ổn định cùng cơ chế truy cập được kiểm soát, nhưng phải chấp nhận rằng consumer phụ thuộc vào dịch vụ tra cứu đó.

Cần phân biệt dữ liệu snapshot với trạng thái hiện tại. Event OrderPlaced ghi nhận giá và tổng tiền khi đặt hàng; event OrderCancelled sau đó không làm thay đổi nội dung event OrderPlaced cũ.

## 4. Xây dựng DTO sự kiện riêng

Tạo record hoặc class dành riêng cho event contract. Ví dụ:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderPlacedV1(
    String orderId,
    String customerId,
    BigDecimal total,
    String currency,
    Instant placedAt
) {}
~~~

Kiểu dữ liệu trên chỉ chứa các trường thuộc hợp đồng OrderPlaced. Nó không có annotation JPA, quan hệ ORM, khóa chính cơ sở dữ liệu hay trạng thái nội bộ.

Có thể định nghĩa envelope bao quanh payload:

~~~java
import java.time.Instant;

public record EventEnvelope<T>(
    String eventId,
    String source,
    String eventType,
    int schemaVersion,
    Instant occurredAt,
    String correlationId,
    String causationId,
    T data
) {}
~~~

Envelope chứa metadata dùng chung; data chứa nội dung của loại event cụ thể. Đây là một quy ước ứng dụng. Nếu hệ thống đã dùng CloudEvents, hãy cân nhắc sử dụng envelope và thuộc tính chuẩn của CloudEvents thay vì tạo một định dạng cạnh tranh.

Ví dụ JSON được công bố:

~~~json
{
  "eventId": "evt-7d0b",
  "source": "orders-service",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T10:15:30Z",
  "correlationId": "corr-checkout-9001",
  "causationId": "cmd-place-order-9001",
  "data": {
    "orderId": "ord-9001",
    "customerId": "cus-2001",
    "total": 125000.00,
    "currency": "VND",
    "placedAt": "2026-11-24T10:15:29Z"
  }
}
~~~

Trong hợp đồng này, eventId định danh lần phát sự kiện; source định danh producer; eventType xác định loại sự kiện; schemaVersion xác định phiên bản contract; occurredAt là thời điểm sự kiện được ghi nhận; correlationId liên kết quy trình; causationId tham chiếu command hoặc event gây ra nó. Trường data là payload nghiệp vụ.

Có thể dùng tên trường camelCase hoặc snake_case. Điều quan trọng là thống nhất một quy ước và giữ tên/ý nghĩa ổn định giữa các phiên bản. Không dùng một trường chung chung như value hoặc data1 nếu consumer không thể hiểu ý nghĩa nghiệp vụ.

## 5. Ánh xạ từ mô hình nội bộ sang event contract

Tạo mapper riêng để chuyển từ domain/entity sang event DTO. Mapper là ranh giới chống lan truyền chi tiết lưu trữ:

~~~java
import java.time.Instant;

public class OrderEventMapper {

    public OrderPlacedV1 toOrderPlaced(Order order, Instant occurredAt) {
        return new OrderPlacedV1(
            order.getPublicOrderId(),
            order.getCustomerReference(),
            order.getFinalTotal(),
            order.getCurrencyCode(),
            occurredAt
        );
    }
}
~~~

Order là domain object của producer. OrderPlacedV1 là contract công khai. Mapper quyết định giá trị nào được công bố và cách biểu diễn chúng. Khi entity thay đổi từ customerDatabaseId sang customerReference, chỉ mapper và domain logic cần được điều chỉnh nếu contract vẫn giữ customerId như cũ.

Có thể dùng MapStruct để sinh code ánh xạ cho các trường đơn giản. Tuy nhiên, không nên dựa vào mapping tự động để quyết định ngữ nghĩa event. Những quyết định như snapshot giá, cách biểu diễn currency, xử lý dữ liệu thiếu hoặc loại bỏ thông tin nội bộ cần được viết và kiểm thử rõ ràng.

Một số nguyên tắc khi ánh xạ:

- Dùng ID nghiệp vụ ổn định thay cho khóa row chỉ có ý nghĩa trong database.
- Chuyển enum nội bộ sang giá trị contract được công bố và có quy tắc tiến hóa.
- Chuẩn hóa thời gian theo UTC và định nghĩa rõ đó là thời điểm nghiệp vụ hay thời điểm publish.
- Dùng kiểu số chính xác cho tiền, kèm currency; không dùng floating point cho số tiền.
- Không serialize proxy, quan hệ entity hoặc object có vòng tham chiếu.
- Xử lý null và trường tùy chọn theo schema; không để consumer phải đoán ý nghĩa của giá trị rỗng.
- Không công bố password, token, dữ liệu định danh nhạy cảm hoặc trường nội bộ không có mục đích tiêu thụ.

## 6. Công bố event qua Spring Cloud Stream

Sau khi có DTO, có thể tạo envelope và lưu nó vào outbox. Ví dụ factory:

~~~java
import java.time.Instant;
import java.util.UUID;

public class OrderEventFactory {

    private final OrderEventMapper mapper;

    public OrderEventFactory(OrderEventMapper mapper) {
        this.mapper = mapper;
    }

    public EventEnvelope<OrderPlacedV1> create(
            Order order,
            String correlationId,
            String causationId,
            Instant occurredAt) {

        OrderPlacedV1 data = mapper.toOrderPlaced(order, occurredAt);

        return new EventEnvelope<>(
            UUID.randomUUID().toString(),
            "orders-service",
            "OrderPlaced",
            1,
            occurredAt,
            correlationId,
            causationId,
            data
        );
    }
}
~~~

Trong ứng dụng thực tế, event ID và nội dung envelope phải được tạo một lần cho một sự kiện nghiệp vụ. Nếu gửi lại do timeout hoặc relay restart, hãy phát lại cùng event ID và cùng payload. Không gọi factory để sinh event ID mới cho mỗi lần retry của cùng một bản ghi outbox.

Có thể khai báo output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPlaced-out-0:
          destination: orders.placed
          content-type: application/json
~~~

Tên binding là ví dụ cho output được gửi bằng StreamBridge. Khi dùng StreamBridge, có thể gửi envelope đã tạo tới binding có tên orderPlaced-out-0:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;

public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(EventEnvelope<OrderPlacedV1> event) {
        return streamBridge.send("orderPlaced-out-0", event);
    }
}
~~~

Đoạn code trên minh họa việc gửi DTO đã được tạo. Với nghiệp vụ cần đảm bảo cập nhật database và phát event nhất quán, không nên coi lời gọi send nằm cùng transaction cơ sở dữ liệu là một transaction phân tán. Hãy lưu envelope đã serialize trong outbox cùng transaction nghiệp vụ, sau đó relay gửi bản ghi outbox. Nếu relay gửi thành công nhưng chưa đánh dấu bản ghi, event có thể được gửi lại; consumer cần idempotency dựa trên event ID.

Binder Kafka, RabbitMQ hoặc Pulsar vận chuyển message theo cấu hình tương ứng. Contract DTO không nên chứa logic phụ thuộc vào loại broker. Nếu thay binder, mục tiêu là giữ nguyên ý nghĩa payload và chỉ thay đổi cấu hình kết nối/semantics vận chuyển đã được kiểm thử.

## 7. Consumer cũng có mô hình riêng

Consumer nhận contract và ánh xạ sang mô hình đọc hoặc mô hình domain của chính nó. Ví dụ một service phân tích có thể chỉ cần orderId, total, currency và placedAt:

~~~java
import java.time.Instant;

public record SalesOrderProjection(
    String orderReference,
    long totalInMinorUnit,
    String currencyCode,
    Instant orderTime
) {}
~~~

Mapper phía consumer chuyển OrderPlacedV1 sang projection riêng. Consumer không cần tái sử dụng OrderEntity của producer, và producer không cần biết cấu trúc bảng báo cáo của consumer.

~~~java
public class SalesProjectionMapper {

    public SalesOrderProjection toProjection(OrderPlacedV1 event) {
        long totalInMinorUnit = event.total()
            .movePointRight(2)
            .longValueExact();

        return new SalesOrderProjection(
            event.orderId(),
            totalInMinorUnit,
            event.currency(),
            event.placedAt()
        );
    }
}
~~~

Ví dụ trên giả định currency có hai chữ số thập phân. Với hệ thống nhiều currency, quy tắc số chữ số thập phân phải được xác định theo currency hoặc dùng một biểu diễn tiền tệ đã chuẩn hóa trong contract. Không áp dụng cố định movePointRight(2) cho mọi loại tiền.

Consumer có thể lưu projection vào database riêng, dùng document model, cập nhật cache hoặc phát một event mới. Thay đổi cấu trúc lưu trữ ở consumer không làm thay đổi event contract nếu mục đích nghiệp vụ vẫn giữ nguyên.

## 8. Chọn dữ liệu ổn định và tránh rò rỉ chi tiết nội bộ

Trước khi thêm một trường vào contract, hãy hỏi:

- Consumer cần trường này để thực hiện nghiệp vụ nào?
- Giá trị này có ý nghĩa ổn định ngoài service phát không?
- Đây là ID nghiệp vụ hay ID kỹ thuật chỉ tồn tại trong database?
- Giá trị cần phản ánh trạng thái tại thời điểm event hay trạng thái hiện tại?
- Có thể công bố trường này cho tất cả consumer có quyền đọc destination không?
- Nếu producer thay đổi cách lưu trữ, trường này có còn giữ nguyên ý nghĩa không?

Ví dụ một số trường nên tránh công bố:

| Trường nội bộ | Vấn đề | Thay thế phù hợp |
|---|---|---|
| databaseRowId | Khóa phụ thuộc database và cách import dữ liệu | orderId nghiệp vụ ổn định |
| customer_fk | Tên cột và quan hệ lưu trữ | customerId hoặc customerReference |
| hibernateVersion | Phục vụ optimistic locking nội bộ | Bỏ khỏi event nếu consumer không cần |
| internalRiskFlag | Quy tắc và dữ liệu nội bộ có thể nhạy cảm | Event riêng được phân quyền nếu có nhu cầu nghiệp vụ hợp lệ |
| entityStatusCode = 7 | Mã số không mang ý nghĩa contract | Giá trị enum công khai như PLACED |
| lazy-loaded customer object | Proxy/quan hệ ORM, có thể kéo theo dữ liệu không cần thiết | Snapshot trường cần dùng hoặc reference đã định nghĩa |

Không phải mọi trường kỹ thuật đều bị cấm. Event ID, source, schema version và thời điểm phát là metadata kỹ thuật có ích cho hợp đồng. Điểm cần tránh là làm contract phụ thuộc vào cách producer tổ chức bảng hoặc framework lưu trữ.

## 9. Tiến hóa hợp đồng mà không phá consumer

Producer và consumer không được triển khai đồng thời. Một phiên bản producer mới có thể phát event trước khi tất cả consumer được nâng cấp. Vì vậy, thay đổi schema phải theo quy tắc tương thích.

Các thay đổi thường an toàn hơn:

- Thêm trường tùy chọn mà consumer cũ có thể bỏ qua.
- Đặt giá trị mặc định hợp lý cho trường mới khi dùng schema format hỗ trợ default.
- Thêm giá trị enum mới nếu consumer được thiết kế để xử lý giá trị chưa biết.
- Bổ sung metadata mà không đổi ý nghĩa trường hiện có.

Các thay đổi có rủi ro phá vỡ:

- Xóa trường mà consumer đang sử dụng.
- Đổi tên trường hoặc đổi kiểu dữ liệu.
- Tái sử dụng trường cũ với ý nghĩa nghiệp vụ khác.
- Đổi đơn vị tiền tệ hoặc đơn vị đo nhưng giữ nguyên tên trường.
- Đổi quy tắc null/default khiến consumer diễn giải dữ liệu khác.
- Thêm giá trị enum mà consumer cũ coi mọi giá trị ngoài danh sách là lỗi không phục hồi.

Nếu thay đổi không tương thích, có thể tạo event type hoặc phiên bản contract mới, ví dụ OrderPlacedV2, hoặc dùng destination/versioning strategy phù hợp. Lộ trình chuyển đổi thường gồm công bố contract mới, cập nhật consumer, chạy song song trong thời gian chuyển tiếp, quan sát tỷ lệ tiêu thụ và ngừng contract cũ sau khi các consumer đã chuyển đổi.

Không nên tăng schemaVersion chỉ vì producer có bản phát hành mới nếu contract không đổi. Phiên bản ứng dụng và phiên bản hợp đồng sự kiện là hai thứ khác nhau.

## 10. Schema format và Schema Registry

JSON dễ đọc và phù hợp khi cần tích hợp nhanh. Tuy nhiên, nếu nhiều team và nhiều ngôn ngữ cùng phát triển producer/consumer, nên quản lý schema bằng định dạng và công cụ có quy tắc tương thích rõ ràng.

| Định dạng | Đặc điểm | Khi phù hợp |
|---|---|---|
| JSON Schema | Dễ đọc, mô tả kiểu, required, enum và ràng buộc | API/event JSON và tích hợp đa ngôn ngữ |
| Avro | Schema tách khỏi payload, hỗ trợ schema resolution | Luồng Kafka và hệ thống cần tiến hóa schema |
| Protocol Buffers | Schema IDL, payload nhị phân gọn, sinh code đa ngôn ngữ | Hệ thống cần contract chặt và hiệu quả truyền tải |

Schema Registry lưu schema, quản lý phiên bản và có thể kiểm tra compatibility trước khi producer phát dữ liệu. Registry không thay thế việc thiết kế ý nghĩa nghiệp vụ. Một schema có thể hợp lệ về cấu trúc nhưng vẫn gây hiểu sai nếu producer đổi đơn vị hoặc đổi ý nghĩa trường.

Cần xác định compatibility policy phù hợp với cách triển khai:

- Backward compatibility: consumer dùng schema mới có thể đọc dữ liệu được ghi bằng schema cũ, theo quy tắc của định dạng.
- Forward compatibility: consumer dùng schema cũ có thể đọc dữ liệu được ghi bằng schema mới.
- Full compatibility: hỗ trợ cả hai hướng.
- Transitive compatibility: kiểm tra tương thích với nhiều phiên bản trước đó, không chỉ phiên bản gần nhất.

Tên chính xác và chi tiết của các policy phụ thuộc Registry và schema format. Kiểm tra tài liệu của công cụ đang dùng trước khi chọn policy.

## 11. Kiểm thử hợp đồng ở producer và consumer

Không nên chỉ kiểm tra rằng JSON serialize thành công. Cần kiểm tra cả nội dung, ngữ nghĩa và tương thích.

**Producer tests** nên xác nhận:

- Mapper không đưa trường persistence hoặc dữ liệu nội bộ vào payload.
- Event type, schema version và tên trường đúng contract.
- Giá trị snapshot phản ánh thời điểm nghiệp vụ xảy ra.
- Retry cùng một outbox record giữ nguyên event ID và payload.
- Trường bắt buộc, currency, thời gian và đơn vị có giá trị hợp lệ.

**Consumer tests** nên xác nhận:

- Consumer đọc được payload theo contract hiện tại.
- Consumer bỏ qua trường bổ sung mà nó không cần, nếu schema format cho phép.
- Giá trị enum chưa biết hoặc trường tùy chọn được xử lý theo chính sách.
- Mapping sang read model riêng không phụ thuộc entity producer.
- Duplicate event không gây lặp side effect.

**Contract/integration tests** nên xác nhận:

- Producer phát schema đã đăng ký và được chấp nhận bởi compatibility policy.
- Consumer đọc message thực tế qua binder và broker.
- Header và payload được chuyển đổi đúng.
- Phiên bản consumer hiện tại đọc được event của producer mới trong giai đoạn rollout.
- DLQ và replay vẫn giữ nguyên event contract gốc.

Có thể lưu các payload mẫu đã được kiểm duyệt trong repository contract để làm fixture. Khi thay đổi contract, cập nhật fixture và kiểm thử tương thích trước khi triển khai producer.

## 12. Checklist thiết kế trước khi công bố một event

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Tên và ý nghĩa | Event mô tả sự thật nghiệp vụ đã xảy ra chưa? |
| Chủ sở hữu | Service nào chịu trách nhiệm định nghĩa và phát contract? |
| Payload | Có chỉ chứa dữ liệu cần thiết cho consumer không? |
| Độc lập lưu trữ | Có trường nào chỉ phản ánh bảng, entity hoặc ORM không? |
| Snapshot | Giá trị có phản ánh đúng thời điểm event xảy ra không? |
| Định danh | Event ID và các ID nghiệp vụ có ổn định không? |
| Kiểu dữ liệu | Tiền, thời gian, enum, null và đơn vị đã rõ chưa? |
| Bảo mật | Có trường nhạy cảm hoặc dữ liệu nội bộ bị công bố không? |
| Tiến hóa | Thay đổi mới có tương thích với consumer cũ không? |
| Kiểm thử | Có mapper test, contract test và broker integration test không? |
| Vận hành | Có outbox, idempotency, DLQ và quy trình replay phù hợp không? |

## 13. Trình tự thực hành và tiêu chí hoàn thành

Thực hiện một bài tập với nghiệp vụ đặt hàng:

1. Tạo OrderEntity có các trường persistence như database ID, version, quan hệ customer và trạng thái nội bộ.
2. Định nghĩa OrderPlacedV1 chỉ chứa orderId, customerId, total, currency và placedAt.
3. Viết mapper chuyển domain Order sang OrderPlacedV1.
4. Tạo envelope chứa eventId, source, eventType, schemaVersion, occurredAt, correlationId, causationId và data.
5. Lưu event vào outbox trong cùng transaction với thay đổi trạng thái đơn hàng.
6. Dùng relay phát envelope qua output binding Spring Cloud Stream.
7. Viết consumer nhận OrderPlacedV1 và chuyển thành projection có cấu trúc riêng.
8. Thêm một trường nội bộ mới vào entity và chứng minh contract không đổi.
9. Thêm một trường tùy chọn vào contract, kiểm tra consumer cũ vẫn đọc được.
10. Thử một thay đổi phá vỡ như đổi kiểu total hoặc xóa orderId; xác định chiến lược versioning cần dùng.

Hoàn thành bài khi có thể giải thích vì sao entity không phải event contract, viết được DTO sự kiện độc lập, ánh xạ từ mô hình nội bộ, công bố bằng Spring Cloud Stream và kiểm tra được thay đổi contract mà không làm consumer cũ hỏng.

## 14. Tài liệu tham khảo chính thức

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — mô hình function, binding và binder.
- [Spring Cloud Stream — Programming model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html) — tích hợp event DTO với Supplier, Function và Consumer.
- [Spring Cloud Stream — Schema Registry](https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html) — schema registry client và quản lý schema.
- [Apache Avro Specification](https://avro.apache.org/docs/) — schema, writer/reader resolution và định dạng Avro.
- [Protocol Buffers Documentation](https://protobuf.dev/overview/) — thiết kế message schema và tiến hóa field.
- [JSON Schema](https://json-schema.org/learn) — mô tả và xác thực cấu trúc JSON.
- [CloudEvents Specification](https://github.com/cloudevents/spec) — envelope và thuộc tính metadata sự kiện.

