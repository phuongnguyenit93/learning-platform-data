# Thiết kế đối tượng dữ liệu truyền đi độc lập với thực thể lưu trữ

Trong ứng dụng Spring, dữ liệu thường tồn tại dưới nhiều hình thức. Database lưu dữ liệu theo mô hình persistence; domain model biểu diễn quy tắc nghiệp vụ; message truyền dữ liệu giữa các thành phần hoặc hệ thống; API DTO phục vụ giao tiếp với client. Những mô hình này có thể chứa một số thông tin giống nhau, nhưng chúng có mục đích và vòng đời khác nhau.

Khi gửi trực tiếp một persistence entity làm payload của message, cấu trúc message vô tình bị gắn với cách ứng dụng lưu dữ liệu. Một thay đổi quan hệ JPA, tên cột hoặc cách tổ chức bảng có thể làm consumer bị ảnh hưởng dù hợp đồng nghiệp vụ không thay đổi. Thiết kế một message DTO riêng giúp kiểm soát chính xác dữ liệu được công bố, giữ hợp đồng giao tiếp ổn định và bảo vệ ranh giới giữa persistence với messaging.

## 1. Phân biệt các loại mô hình dữ liệu

### Persistence entity

Persistence entity là object được ORM như JPA/Hibernate ánh xạ với dữ liệu lưu trữ. Nó thường mang các chi tiết phục vụ database:

- Annotation như **@Entity**, **@Table**, **@Id**, **@Column**, **@OneToMany** hoặc **@ManyToOne**.
- Quan hệ giữa các entity và collection có thể được tải lazy.
- Trạng thái phục vụ persistence như version, khóa ngoại, audit field hoặc cờ xóa mềm.
- Phương thức và quy tắc phục vụ vòng đời lưu trữ.

Entity có thể có proxy do ORM tạo, quan hệ hai chiều và tham chiếu vòng. Những chi tiết này phù hợp với persistence context nhưng thường không phải hợp đồng dữ liệu mà một consumer bên ngoài cần biết.

### Domain model

Domain model biểu diễn khái niệm và quy tắc nghiệp vụ. Nó có thể là entity nghiệp vụ, aggregate, value object hoặc service. Domain model tập trung bảo vệ invariant và hành vi nghiệp vụ; nó không bắt buộc phải trùng với cấu trúc bảng database hoặc payload message.

### Data Transfer Object (DTO)

DTO là object mang dữ liệu qua một ranh giới giao tiếp. DTO thường chỉ chứa những trường mà bên nhận cần. DTO có thể được dùng cho REST API, message, RPC hoặc một tầng ứng dụng khác. Mỗi ranh giới có thể cần một DTO riêng vì người nhận, mục đích và chính sách tương thích khác nhau.

### Message contract

Message contract là hợp đồng dữ liệu mà producer công bố và consumer dựa vào. Nó bao gồm payload, ý nghĩa các trường, kiểu dữ liệu, quy tắc nullability, định dạng thời gian, phiên bản và metadata liên quan. Message DTO là một cách cụ thể để biểu diễn payload theo hợp đồng đó.

Không phải mọi DTO đều là message contract và không phải mọi message đều phải được biểu diễn bằng một Java DTO. Điều quan trọng là payload có cấu trúc rõ ràng, độc lập với chi tiết lưu trữ và được các bên hiểu thống nhất.

## 2. Vì sao không nên gửi trực tiếp persistence entity?

Giả sử bảng đơn hàng được ánh xạ thành một entity có thông tin khách hàng, danh sách dòng hàng, ghi chú nội bộ và trạng thái lưu trữ. Consumer nhận event đơn hàng chỉ cần mã đơn hàng, mã khách hàng, tổng tiền và thời điểm phát sinh. Nếu producer gửi toàn bộ entity, có thể phát sinh nhiều vấn đề.

### 2.1. Lộ chi tiết database ra ngoài

Tên field trong entity có thể phản ánh cách lưu trữ như **customerForeignKey**, **deletedFlag**, **rowVersion** hoặc tên cột cũ. Consumer không nên phải thay đổi chỉ vì producer đổi cách tổ chức database.

Khi payload là DTO riêng, producer có thể đổi bảng, đổi ORM hoặc tách một entity thành nhiều bảng mà không làm thay đổi message contract, miễn là ý nghĩa dữ liệu được công bố vẫn giữ nguyên.

### 2.2. Lazy loading và truy vấn ngoài ý muốn

Hibernate có thể dùng proxy và collection lazy để chỉ tải quan hệ khi được truy cập. Khi serializer duyệt object graph để tạo JSON, nó có thể kích hoạt truy vấn database ngoài dự kiến. Nếu persistence context đã đóng, việc truy cập có thể gây lỗi như **LazyInitializationException**.

Gửi DTO đã được ánh xạ trong ranh giới giao dịch giúp payload có dữ liệu cụ thể và không phụ thuộc vào trạng thái của persistence context. Việc mapping cần được thực hiện khi các dữ liệu cần thiết còn truy cập được, hoặc bằng một truy vấn projection được thiết kế rõ ràng.

### 2.3. Quan hệ hai chiều và vòng tham chiếu

Một entity **Order** có thể tham chiếu **Customer**, trong khi **Customer** lại có danh sách **Order**. Serializer đi theo quan hệ này có thể lặp vô hạn, tạo payload quá lớn hoặc cần annotation đặc thù của serializer để cắt vòng tham chiếu.

DTO chỉ chứa các trường đã chọn, ví dụ **orderId** và **customerId**, nên tránh mang toàn bộ object graph của ORM vào message.

### 2.4. Rò rỉ dữ liệu và tăng kích thước payload

Entity có thể chứa email, địa chỉ, ghi chú nội bộ, thông tin thanh toán, token hoặc trường chỉ phục vụ nhân viên. Gửi nguyên entity dễ công bố nhiều dữ liệu hơn mức consumer cần.

Payload càng lớn càng tốn băng thông, bộ nhớ broker, chi phí serialization và thời gian xử lý. Chỉ nên đưa dữ liệu cần thiết vào message. Với tệp hoặc nội dung lớn, hãy lưu nội dung ở object storage và gửi một tham chiếu có quyền truy cập được kiểm soát.

### 2.5. Ghép chặt producer và consumer

Nếu consumer phụ thuộc trực tiếp vào class entity của producer, hai bên bị ghép chặt vào package, phiên bản class và thư viện persistence. Consumer có thể buộc phải thêm dependency JPA dù nó chỉ cần đọc một thông điệp.

Một message contract độc lập cho phép producer và consumer phát triển riêng, miễn là thay đổi vẫn tương thích với hợp đồng đã công bố.

## 3. Thiết kế một message DTO tốt

Một DTO truyền đi nên thể hiện sự kiện hoặc yêu cầu nghiệp vụ rõ ràng. Hãy chọn các trường dựa trên câu hỏi: consumer cần biết điều gì để thực hiện trách nhiệm của nó?

### 3.1. Chỉ đưa dữ liệu cần thiết

Ví dụ event **OrderPlaced** có thể chứa:

- **eventId:** định danh duy nhất của sự kiện.
- **orderId:** định danh đơn hàng trong nghiệp vụ.
- **customerId:** định danh khách hàng nếu consumer cần tra cứu hoặc liên kết.
- **totalAmount:** tổng tiền tại thời điểm đặt hàng.
- **currency:** mã tiền tệ.
- **occurredAt:** thời điểm sự kiện xảy ra.

Không đưa các trường chỉ phục vụ persistence như khóa ngoại nội bộ, trạng thái lazy proxy, tên bảng, thông tin audit nội bộ hoặc ghi chú bí mật. Nếu consumer cần thông tin bổ sung, hãy cân nhắc đưa một snapshot tối thiểu vào event hay để consumer truy vấn qua một API được kiểm soát.

### 3.2. Dùng kiểu dữ liệu rõ nghĩa

Chọn kiểu dữ liệu theo ý nghĩa nghiệp vụ:

- ID nên có kiểu và định dạng ổn định. Có thể dùng String trong contract JSON hoặc một kiểu định danh được quy ước rõ.
- Tiền nên dùng **BigDecimal** hoặc biểu diễn bằng đơn vị nhỏ nhất dưới dạng số nguyên, kèm mã tiền tệ. Không dùng floating point để biểu diễn tiền cần độ chính xác.
- Thời điểm tuyệt đối nên dùng **Instant** hoặc chuỗi ISO-8601 có múi giờ, ví dụ UTC với hậu tố Z.
- Trạng thái nên có giá trị được quy ước ổn định; tránh phụ thuộc vào ordinal của Java enum vì thứ tự enum có thể thay đổi.
- Collection cần quy định rõ ý nghĩa của danh sách rỗng, trường bị thiếu và giá trị null.

Một contract cần xác định rõ cách serialize kiểu dữ liệu. Ví dụ BigDecimal có thể được biểu diễn thành chuỗi thập phân để tránh sai số khi qua hệ thống dùng kiểu số khác. Instant thường được serialize theo ISO-8601. Không nên để mỗi consumer tự suy đoán định dạng.

### 3.3. Ưu tiên payload bất biến

Message biểu diễn một sự kiện đã xảy ra nên dữ liệu cần phản ánh snapshot tại thời điểm phát hành. Java record là lựa chọn phù hợp cho DTO bất biến đơn giản:

~~~java
public record OrderPlacedV1(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        String currency,
        Instant occurredAt
) {}
~~~

Record giúp khai báo dữ liệu ngắn gọn và các component là final. Tuy nhiên, bất biến ở cấp record không tự làm mọi object được tham chiếu trở nên bất biến. Với collection, nên tạo bản sao bất biến; với kiểu mutable, cần cân nhắc defensive copy.

### 3.4. Tách dữ liệu payload khỏi metadata vận chuyển

Payload chứa nội dung nghiệp vụ. Message headers chứa metadata phục vụ vận chuyển hoặc quan sát, ví dụ correlation ID, content type, trace context hoặc thông tin định tuyến.

Không nên đưa cùng một thông tin vào cả payload và headers nếu không có lý do rõ ràng. Những thông tin consumer cần để hiểu sự kiện nên thuộc message contract; metadata phục vụ delivery/tracing có thể đặt trong headers theo quy ước của hệ thống.

## 4. Mapping từ entity sang message DTO

Mapping là bước chuyển dữ liệu từ mô hình nội bộ sang hợp đồng công bố. Nên đặt mapping ở application layer hoặc một mapper riêng, nơi có thể nhìn rõ những trường được phép đưa ra ngoài.

Ví dụ entity lưu trữ có thể có nhiều field hơn payload:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private String id;

    private String customerId;

    private BigDecimal totalAmount;

    private String currency;

    private String internalNote;

    @Version
    private long version;

    // Constructor, getter và setter được lược bỏ.
}
~~~

Đây là đoạn minh họa persistence entity dùng JPA; nó cần dependency JPA và không phải chương trình độc lập. Các field **internalNote** và **version** phục vụ nội bộ, không cần xuất hiện trong event.

Message DTO được định nghĩa riêng:

~~~java
public record OrderPlacedV1(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        String currency,
        Instant occurredAt
) {}
~~~

Mapper chọn đúng dữ liệu công bố:

~~~java
public final class OrderEventMapper {

    private OrderEventMapper() {}

    public static OrderPlacedV1 toOrderPlaced(
            OrderEntity order,
            String eventId,
            Instant occurredAt) {

        return new OrderPlacedV1(
                eventId,
                order.getId(),
                order.getCustomerId(),
                order.getTotalAmount(),
                order.getCurrency(),
                occurredAt
        );
    }
}
~~~

Mapping thủ công phù hợp với contract nhỏ và giúp nhìn thấy chính xác từng field. Với nhiều DTO, có thể dùng MapStruct để sinh code mapping lúc biên dịch. Dù dùng công cụ nào, vẫn phải review quy tắc mapping và kiểm tra rằng không có field nội bộ bị xuất ra ngoài.

Một số quy tắc mapping cần quyết định rõ:

- Giá trị null ở entity được chuyển thành null, trường bị bỏ qua hay một giá trị mặc định?
- Collection có cần sắp xếp để payload ổn định không?
- Quan hệ entity chỉ được chuyển thành ID hay cần snapshot một số thuộc tính?
- Giá trị tiền và thời gian có được chuẩn hóa không?
- Event thể hiện trạng thái trước hay sau khi cập nhật database?
- Khi một field nội bộ đổi tên hoặc đổi kiểu, message contract có cần thay đổi không?

Không nên để DTO tự truy cập repository hoặc gọi lazy relation. DTO chỉ nên mô tả dữ liệu; việc lấy dữ liệu và ánh xạ thuộc về application/service hoặc mapper.

## 5. Gửi DTO qua Spring Messaging

Spring Messaging biểu diễn một thông điệp bằng **Message<T>**, trong đó payload có kiểu T và headers chứa metadata. **MessageBuilder** hỗ trợ tạo message. **MessageChannel** là abstraction để gửi message.

Khi đã tạo DTO, producer có thể đóng gói DTO làm payload:

~~~java
OrderPlacedV1 event = mapper.toOrderPlaced(order, eventId, occurredAt);

Message<OrderPlacedV1> message = MessageBuilder
        .withPayload(event)
        .setHeader("eventType", "OrderPlaced")
        .setHeader("schemaVersion", 1)
        .build();

boolean accepted = outputChannel.send(message);
~~~

Đây là đoạn minh họa sử dụng Spring Messaging, cần các bean và import tương ứng. Nó cho thấy payload là **OrderPlacedV1**, không phải **OrderEntity**. Việc gửi qua channel không tự quyết định cách serialize hoặc broker sẽ lưu message; điều đó phụ thuộc channel, adapter, message converter và transport được cấu hình.

Consumer nhận payload theo contract:

~~~java
@Service
public class OrderProjectionHandler {

    public void handle(Message<OrderPlacedV1> message) {
        OrderPlacedV1 event = message.getPayload();

        // Cập nhật read model bằng dữ liệu trong event.
        updateOrderProjection(
                event.orderId(),
                event.customerId(),
                event.totalAmount(),
                event.currency()
        );
    }

    private void updateOrderProjection(
            String orderId,
            String customerId,
            BigDecimal totalAmount,
            String currency) {
        // Logic cập nhật read model được triển khai tại đây.
    }
}
~~~

Trong ứng dụng thực tế, consumer có thể nhận message thông qua **@ServiceActivator**, **@RabbitListener**, **@KafkaListener** hoặc adapter tương ứng với công nghệ tích hợp. Cần bảo đảm message converter của producer và consumer thống nhất về định dạng payload, kiểu dữ liệu và schema.

## 6. Phiên bản hóa và tiến hóa message contract

Message có thể được giữ trong broker, retry hoặc được consumer xử lý sau khi producer đã triển khai phiên bản mới. Vì vậy, contract cần tương thích qua thời gian.

### 6.1. Thay đổi tương thích

Các thay đổi thường dễ tương thích hơn gồm:

- Thêm một field tùy chọn mà consumer cũ có thể bỏ qua.
- Bổ sung metadata mà consumer không bắt buộc phải hiểu.
- Mở rộng tài liệu và mô tả ý nghĩa field mà không đổi semantics hiện tại.

Các thay đổi có nguy cơ phá vỡ tương thích gồm:

- Xóa hoặc đổi tên field đang được consumer sử dụng.
- Đổi kiểu dữ liệu, đơn vị đo hoặc ý nghĩa của field.
- Đổi enum value mà consumer cũ không biết.
- Biến field tùy chọn thành bắt buộc mà không có chiến lược chuyển đổi.

Không phải mọi định dạng serialization đều xử lý field lạ hoặc field thiếu giống nhau. Với JSON, consumer cần được thiết kế để xử lý field bổ sung và giá trị thiếu theo quy tắc rõ ràng. Với Avro hoặc Protobuf, cần tuân theo quy tắc schema evolution của định dạng đó.

### 6.2. Đặt phiên bản trong tên contract hoặc metadata

Có thể dùng tên kiểu như **OrderPlacedV1**, **OrderPlacedV2**, hoặc giữ tên event ổn định và công bố schema version trong metadata. Chọn một quy ước nhất quán để consumer biết cách diễn giải payload.

Phiên bản trong tên class Java không tự động bảo đảm compatibility. Điều quan trọng là schema được công bố, serializer, deserializer và chính sách triển khai giữa producer và consumer.

### 6.3. Duy trì consumer tương thích

Một chiến lược phổ biến là triển khai consumer có thể đọc cả phiên bản cũ và mới, sau đó mới chuyển producer sang phiên bản mới. Khi không thể duy trì compatibility, có thể dùng topic/queue mới, event type mới hoặc quy trình migration có kiểm soát.

Không sửa nghĩa của một event đã phát hành. Ví dụ, nếu **totalAmount** từng có nghĩa là tổng tiền sau giảm giá và thuế, không nên đổi sang tổng tiền trước giảm giá chỉ vì tên field vẫn giống nhau.

## 7. Chọn DTO snapshot hay chỉ gửi ID?

Có hai cách thiết kế phổ biến, mỗi cách phù hợp với nhu cầu khác nhau.

### Gửi snapshot dữ liệu cần thiết

Event chứa các giá trị consumer cần tại thời điểm sự kiện xảy ra, ví dụ mã đơn hàng, tổng tiền, currency và tên hiển thị của sản phẩm. Consumer có thể xử lý mà không phải gọi ngược producer.

Cách này hữu ích khi:

- Consumer cần biết trạng thái tại đúng thời điểm event xảy ra.
- Producer và consumer cần giảm phụ thuộc vào API truy vấn lẫn nhau.
- Dữ liệu cần thiết nhỏ, có ý nghĩa rõ và không chứa thông tin nhạy cảm không cần thiết.

Snapshot có thể trở nên lỗi thời sau này, nhưng đó chính là đặc điểm của sự kiện lịch sử: nó ghi lại điều đã xảy ra tại một thời điểm.

### Chỉ gửi định danh và tham chiếu

Event chỉ chứa ID hoặc một tham chiếu để consumer truy vấn dữ liệu hiện tại qua API hoặc read model. Cách này làm payload nhỏ hơn và giảm trùng lặp dữ liệu, nhưng consumer phụ thuộc vào khả năng truy vấn và quyền truy cập của hệ thống sở hữu dữ liệu.

Nếu consumer truy vấn entity sau khi event được phát, nó có thể đọc trạng thái mới hơn chứ không phải snapshot tại thời điểm event xảy ra. Hãy chọn cách này khi nghiệp vụ cần dữ liệu mới nhất và chấp nhận phụ thuộc truy vấn.

Có thể kết hợp hai cách: gửi các field cần thiết để xử lý phổ biến, kèm ID để truy vấn thêm khi cần. Không nên gửi toàn bộ entity chỉ để tránh phải thiết kế payload.

## 8. Giao dịch lưu trữ và phát message

Một vấn đề quan trọng là đồng bộ giữa thay đổi database và việc phát event. Nếu ứng dụng commit đơn hàng nhưng gửi message thất bại, consumer không biết đơn hàng đã được tạo. Nếu gửi message trước rồi transaction database rollback, consumer lại nhận một sự kiện cho dữ liệu chưa được lưu.

Một giải pháp phổ biến là **Transactional Outbox**:

1. Trong cùng database transaction, lưu thay đổi nghiệp vụ và một bản ghi outbox chứa event DTO hoặc dữ liệu đủ để dựng event.
2. Sau khi transaction commit, một publisher riêng đọc các bản ghi outbox chưa gửi.
3. Publisher gửi event tới broker rồi đánh dấu bản ghi đã phát theo quy trình có khả năng phục hồi.
4. Consumer xử lý idempotent vì publisher có thể gửi lại nếu trạng thái gửi chưa được ghi nhận.

Outbox giúp tránh khoảng trống giữa commit dữ liệu và ghi nhận ý định phát event. Nó không tự bảo đảm exactly-once end-to-end; producer và consumer vẫn cần xử lý duplicate, retry và quan sát lỗi.

## 9. Ví dụ Java 17: chuyển entity sang DTO độc lập

Ví dụ sau dùng các record để mô phỏng dữ liệu lưu trữ và message DTO. Class **OrderEntity** đóng vai trò persistence model đơn giản; trong ứng dụng thật, entity JPA có thể có annotation, quan hệ và trạng thái ORM. DTO chỉ giữ dữ liệu công bố.

Tạo file **MessageDtoDemo.java**:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

public class MessageDtoDemo {

    record OrderEntity(
            String id,
            String customerId,
            BigDecimal totalAmount,
            String currency,
            String internalNote,
            long persistenceVersion
    ) {}

    record OrderPlacedV1(
            String eventId,
            String orderId,
            String customerId,
            BigDecimal totalAmount,
            String currency,
            Instant occurredAt
    ) {
        OrderPlacedV1 {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(orderId);
            Objects.requireNonNull(customerId);
            Objects.requireNonNull(totalAmount);
            Objects.requireNonNull(currency);
            Objects.requireNonNull(occurredAt);
        }
    }

    static OrderPlacedV1 toMessageDto(
            OrderEntity entity,
            String eventId,
            Instant occurredAt
    ) {
        return new OrderPlacedV1(
                eventId,
                entity.id(),
                entity.customerId(),
                entity.totalAmount(),
                entity.currency(),
                occurredAt
        );
    }

    public static void main(String[] args) {
        OrderEntity storedOrder = new OrderEntity(
                "ORD-42",
                "CUS-7",
                new BigDecimal("129900.00"),
                "VND",
                "INTERNAL: manual review",
                3L
        );

        OrderPlacedV1 event = toMessageDto(
                storedOrder,
                "evt-001",
                Instant.parse("2026-11-07T03:00:00Z")
        );

        System.out.println("Message event: " + event.eventId());
        System.out.println("Order: " + event.orderId());
        System.out.println("Customer: " + event.customerId());
        System.out.println("Total: " + event.totalAmount()
                + " " + event.currency());
        System.out.println("Occurred at: " + event.occurredAt());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac MessageDtoDemo.java
java MessageDtoDemo
~~~

Kết quả:

~~~text
Message event: evt-001
Order: ORD-42
Customer: CUS-7
Total: 129900.00 VND
Occurred at: 2026-11-07T03:00:00Z
~~~

Hàm **toMessageDto** chỉ chọn các field thuộc hợp đồng event. **internalNote** và **persistenceVersion** vẫn thuộc entity nhưng không xuất hiện trong DTO. Nhờ vậy, consumer không phụ thuộc vào field nội bộ của mô hình lưu trữ.

Ví dụ chỉ minh họa mapping và payload Java. Khi gửi qua broker, ứng dụng vẫn cần serializer/message converter phù hợp và cấu hình transport tương ứng.

## 10. Kiểm thử message DTO và contract

Không nên chỉ kiểm tra rằng mapper không ném exception. Cần kiểm tra chính xác payload được công bố:

- **Mapping test:** xác nhận từng field được map đúng, field nội bộ không xuất hiện và giá trị null được xử lý theo quy ước.
- **Serialization test:** serialize DTO rồi deserialize lại, xác nhận giá trị và định dạng được bảo toàn.
- **Contract test:** producer và consumer cùng dùng schema hoặc fixture đã công bố; kiểm tra consumer đọc được message mẫu của phiên bản hiện hành.
- **Compatibility test:** khi thêm hoặc thay đổi field, chạy test với payload phiên bản cũ và mới.
- **Privacy test:** xác nhận password, token, ghi chú nội bộ và dữ liệu không cần thiết không có trong payload.
- **Failure test:** kiểm tra message thiếu field, enum không nhận diện hoặc timestamp sai định dạng được xử lý theo chính sách.

Nếu dùng JSON, nên lưu một số payload mẫu đã phát hành trong source control hoặc schema registry để phát hiện thay đổi không tương thích. Không nên chỉ dựa vào việc hai class Java cùng biên dịch, vì producer và consumer có thể chạy ở hai phiên bản khác nhau.

## 11. Lỗi thiết kế thường gặp

- **Gửi nguyên entity JPA:** khiến message contract phụ thuộc schema database, lazy loading và quan hệ ORM.
- **Dùng chung một DTO cho mọi API và event:** mỗi ranh giới có nhu cầu khác nhau; thay đổi một API có thể vô tình phá vỡ consumer message.
- **Đưa quá nhiều dữ liệu vào payload:** làm tăng chi phí vận chuyển và nguy cơ lộ thông tin.
- **Chỉ gửi ID khi consumer cần snapshot:** consumer có thể truy vấn ra trạng thái mới và xử lý sai thời điểm nghiệp vụ.
- **Đổi field hoặc ý nghĩa mà không version:** message cũ có thể được retry hoặc đọc bởi consumer mới, gây lỗi khó truy vết.
- **Dùng enum ordinal hoặc kiểu số không phù hợp:** thay đổi thứ tự enum hoặc biểu diễn floating point có thể làm dữ liệu bị diễn giải sai.
- **Để DTO chứa logic truy cập database:** làm ranh giới dữ liệu phụ thuộc persistence và khó kiểm thử.
- **Không kiểm thử serialization thực tế:** object Java có thể đúng nhưng JSON hoặc schema khi truyền đi lại không tương thích.

## 12. Quy trình thiết kế message DTO

Khi chuẩn bị phát một message mới, hãy đi theo quy trình sau:

1. Xác định message là command hay event và consumer nào cần nhận.
2. Viết hợp đồng nghiệp vụ: tên, ý nghĩa, kiểu dữ liệu, nullability, đơn vị và thời điểm của từng field.
3. Chọn dữ liệu tối thiểu mà consumer cần; phân biệt snapshot với tham chiếu ID.
4. Tạo DTO riêng, ưu tiên kiểu bất biến và không gắn annotation persistence.
5. Viết mapper từ domain/persistence model sang DTO ở ranh giới application.
6. Xác định serializer, content type, schema version và message headers.
7. Kiểm thử mapping, serialization, compatibility và dữ liệu nhạy cảm.
8. Xác định chính sách giao dịch, retry, duplicate, ordering và outbox nếu cần.

Thiết kế DTO độc lập giúp producer tự do thay đổi cách lưu trữ mà vẫn duy trì hợp đồng messaging có ý nghĩa. Message chỉ nên công bố dữ liệu cần thiết, ổn định và được định nghĩa rõ. Khi kết hợp mapping tường minh, schema evolution, kiểm thử contract và xử lý duplicate an toàn, các thành phần có thể trao đổi thông tin mà không bị ràng buộc vào cấu trúc entity hoặc vòng đời của ORM.