# Header nghiệp vụ và thông tin phiên bản sự kiện

Trong hệ thống xử lý sự kiện, payload mô tả dữ liệu của sự kiện, còn header cung cấp metadata để định danh, định tuyến, theo dõi và diễn giải message. Một số metadata thuộc hạ tầng như ID message hoặc content type; một số khác mang ngữ cảnh ứng dụng như tenant, mã tương quan hoặc mức ưu tiên. Khi nhiều dịch vụ cùng trao đổi sự kiện, cần thống nhất ý nghĩa và kiểu dữ liệu của các header, đồng thời xác định rõ phiên bản hợp đồng sự kiện.

Spring Cloud Stream cho phép function nhận toàn bộ `Message<T>` để đọc payload và `MessageHeaders`, rồi tạo message đầu ra bằng `MessageBuilder`. Binder chuyển message qua Kafka, RabbitMQ, Pulsar hoặc broker khác. Vì cách ánh xạ header phụ thuộc transport và binder, hợp đồng sự kiện cần được thiết kế có chủ đích để consumer vẫn hiểu đúng dữ liệu khi message đi qua nhiều dịch vụ.

## 1. Phân biệt payload và header

Payload chứa sự kiện nghiệp vụ: điều gì đã xảy ra, đối tượng nào bị ảnh hưởng và các dữ kiện cần thiết để consumer xử lý. Ví dụ, `OrderPlaced` có thể chứa mã đơn hàng, khách hàng, tổng tiền và thời điểm đặt hàng.

Header là metadata đi kèm message. Nó có thể giúp consumer xác định loại sự kiện, theo dõi một luồng xử lý, áp dụng quy tắc định tuyến hoặc chọn cách giải mã payload.

Ví dụ:

```java
public record OrderPlaced(
    String orderId,
    String customerId,
    BigDecimal total,
    Instant placedAt,
    String eventId
) {}
```

Payload trên mô tả sự kiện đơn hàng đã được đặt. Một message có thể mang thêm các header như:

| Header | Ý nghĩa | Nhóm |
|---|---|---|
| `eventType` | Tên hợp đồng sự kiện, ví dụ `com.example.orders.OrderPlaced` | Hợp đồng ứng dụng |
| `eventVersion` | Phiên bản schema hoặc hợp đồng của sự kiện | Hợp đồng ứng dụng |
| `eventId` | ID duy nhất của sự kiện, dùng cho audit hoặc chống xử lý trùng | Hợp đồng ứng dụng |
| `correlationId` | Liên kết các message trong cùng một luồng nghiệp vụ | Theo dõi |
| `causationId` | ID sự kiện hoặc message trực tiếp gây ra sự kiện hiện tại | Theo dõi |
| `tenantId` | Ngữ cảnh tenant khi hệ thống đa tenant | Ngữ cảnh nghiệp vụ |
| `contentType` | Định dạng payload để chuyển đổi, ví dụ JSON | Chuyển đổi |
| `id`, `timestamp` | Metadata chuẩn do Spring Messaging quản lý | Framework |

Không phải mọi header đều là “header nghiệp vụ”. Cần phân loại metadata theo mục đích để tránh nhầm lẫn giữa thông tin nghiệp vụ, metadata theo dõi và thông tin riêng của broker.

Một nguyên tắc hữu ích là dữ kiện cốt lõi trả lời “điều gì đã xảy ra?” nên nằm trong payload của sự kiện. Header nên chứa ngữ cảnh giúp vận chuyển, định tuyến hoặc quan sát message. Ví dụ, tổng tiền của đơn hàng là dữ kiện nghiệp vụ và thuộc payload; `correlationId` là metadata theo dõi và thường thuộc header.

## 2. Thiết kế header nghiệp vụ có hợp đồng

Header tùy chỉnh là một phần của hợp đồng tích hợp nếu consumer dựa vào chúng để xử lý. Vì vậy, cần quy định rõ:

- Tên header ổn định, thống nhất cách viết và không thay đổi tùy tiện.
- Kiểu dữ liệu được xác định rõ, ví dụ `tenantId` là chuỗi, `eventVersion` là số nguyên.
- Ý nghĩa, nguồn tạo và phạm vi áp dụng của từng header.
- Header nào bắt buộc, header nào tùy chọn và giá trị mặc định nếu thiếu.
- Header nào được phép truyền qua broker và header nào chỉ tồn tại nội bộ ứng dụng.
- Chính sách kiểm tra, chuẩn hóa và loại bỏ header không hợp lệ.

Ví dụ, `tenantId` cần được lấy từ ngữ cảnh xác thực đáng tin cậy hoặc từ producer đã được xác thực. Consumer không nên coi giá trị tenant do một message tùy ý gửi tới là bằng chứng phân quyền. Tương tự, header `priority` chỉ có tác dụng nếu producer, binder và broker cùng có quy tắc xử lý rõ ràng.

Không nên đưa mật khẩu, access token, thông tin định danh cá nhân nhạy cảm hoặc dữ liệu bí mật vào header. Header thường được ghi log, hiển thị trong công cụ quản trị broker hoặc chuyển qua nhiều thành phần trung gian. Chỉ truyền dữ liệu tối thiểu cần thiết.

### Tạo message với header tùy chỉnh

Spring Messaging cung cấp `MessageBuilder` để tạo message:

```java
OrderPlaced event = new OrderPlaced(
    "order-1007",
    "customer-42",
    new BigDecimal("1250000"),
    Instant.now(),
    UUID.randomUUID().toString()
);

Message<OrderPlaced> message = MessageBuilder
    .withPayload(event)
    .setHeader("eventType", "com.example.orders.OrderPlaced")
    .setHeader("eventVersion", 1)
    .setHeader("eventId", event.eventId())
    .setHeader("correlationId", "checkout-9001")
    .setHeader("tenantId", "retail-vn")
    .build();
```

Ví dụ minh họa việc tạo message ở cấp Spring Messaging. Khi gửi qua Spring Cloud Stream, function có thể trả về message này để binder phát nó tới binding đầu ra. Trong hệ thống thực tế, ID sự kiện và correlation ID nên được lấy từ ngữ cảnh tạo sự kiện thay vì dùng giá trị cố định.
Nếu `eventId` cũng xuất hiện trong payload/envelope, giá trị ở header phải được sao chép từ cùng một ID, không tạo một ID khác.

### Đọc header trong function

Khi consumer cần cả payload và metadata, khai báo kiểu đầu vào là `Message<T>`:

```java
@Bean
Consumer<Message<OrderPlaced>> processOrder(
        OrderApplicationService service) {

    return message -> {
        OrderPlaced event = message.getPayload();

        String eventId = (String) message.getHeaders().get("eventId");
        String tenantId = (String) message.getHeaders().get("tenantId");

        if (eventId == null || tenantId == null) {
            throw new InvalidEventMetadataException(
                "eventId and tenantId are required"
            );
        }

        service.process(event, eventId, tenantId);
    };
}
```

Function kiểm tra metadata cần thiết rồi truyền những giá trị có ý nghĩa cho use case. Service không cần phụ thuộc vào `MessageHeaders` hoặc binder. Nếu chỉ cần payload, có thể khai báo `Consumer<OrderPlaced>` để đơn giản hóa adapter.

Header đến từ broker có thể được chuyển đổi kiểu tùy serializer và binder. Nếu một header được nhận dưới dạng chuỗi trong môi trường này nhưng là số nguyên trong môi trường khác, hãy chuẩn hóa kiểu ở adapter và kiểm tra giá trị trước khi gọi service. Không nên ép kiểu trực tiếp mà không xét dữ liệu thực tế.

## 3. Phân biệt header nghiệp vụ với metadata của broker

Một số thông tin quan trọng có thể tồn tại ở nhiều lớp nhưng không có cùng ngữ nghĩa:

- `eventId` là định danh sự kiện do ứng dụng quản lý; Kafka offset hoặc RabbitMQ delivery tag là metadata giao nhận do broker quản lý.
- `aggregateId` định danh thực thể nghiệp vụ; Kafka record key có thể dùng để chọn partition và giữ thứ tự theo key. Chỉ đặt `aggregateId` vào header không có nghĩa binder tự dùng nó làm partition key.
- `correlationId` liên kết các bước của một luồng nghiệp vụ; trace ID thuộc hệ thống tracing. Hai giá trị có thể được liên kết nhưng không nhất thiết giống nhau.
- `eventVersion` mô tả phiên bản hợp đồng sự kiện; phiên bản giao thức của broker hoặc phiên bản CloudEvents có mục đích khác.

Với Kafka, key của record và partition metadata có vai trò riêng. Với RabbitMQ, routing key là thành phần định tuyến AMQP, còn header exchange có thể dùng các thuộc tính header theo cấu hình. Với Pulsar, message key, properties và schema có quy tắc riêng. Binder có thể ánh xạ một số header ứng dụng sang thuộc tính transport, nhưng không được giả định mọi header đều được giữ nguyên trên tất cả broker.

Nếu header là điều kiện bắt buộc để consumer xử lý đúng, cần xác minh binder hỗ trợ header đó, cấu hình mapping/allow-list nếu cần và viết integration test với broker thật. Tránh dựa vào một header tùy chỉnh chỉ hoạt động trong Test Binder.

## 4. Vì sao sự kiện cần thông tin phiên bản?

Sự kiện thường được lưu giữ lâu hơn vòng đời của một phiên bản ứng dụng. Một producer có thể phát sự kiện theo schema cũ trong khi consumer mới đã triển khai; consumer mới cũng có thể phải đọc lại dữ liệu lịch sử. Nếu cấu trúc payload thay đổi mà không có quy ước phiên bản, consumer có thể giải mã sai, bỏ sót dữ kiện hoặc diễn giải khác ý nghĩa nghiệp vụ.

Phiên bản sự kiện giúp consumer và hệ thống quản lý schema xác định cách đọc payload. Nó đặc biệt quan trọng khi:

- Thêm, đổi hoặc loại bỏ trường trong payload.
- Thay đổi kiểu dữ liệu hoặc quy tắc diễn giải trường.
- Consumer cần hỗ trợ nhiều phiên bản producer trong giai đoạn triển khai chuyển tiếp.
- Phát lại sự kiện lịch sử sau khi hệ thống đã nâng cấp.
- Nhiều dịch vụ được triển khai độc lập và không thể nâng cấp đồng thời.

Không nên tăng phiên bản chỉ vì thay đổi nội bộ của class Java. Phiên bản phải phản ánh thay đổi của hợp đồng dữ liệu hoặc ý nghĩa sự kiện mà consumer nhìn thấy.

## 5. Đặt phiên bản ở đâu?

Có một số cách biểu diễn phiên bản. Hãy chọn một nguồn có thẩm quyền để consumer xác định schema:

| Cách biểu diễn | Ví dụ | Khi phù hợp |
|---|---|---|
| Trường trong event envelope | `eventVersion: 2` | Hợp đồng ứng dụng cần đọc phiên bản độc lập với transport |
| Header message | `eventVersion: 2` | Binder và broker giữ header, consumer cần định tuyến hoặc chọn decoder |
| Schema registry | Schema ID/version được gắn với record | Dùng định dạng có schema và registry quản lý vòng đời |
| CloudEvents attribute | `dataschema` hoặc extension `eventversion` | Cần envelope sự kiện theo chuẩn CloudEvents |

Nếu cùng một phiên bản được lặp lại trong payload, header và schema registry, cần quy định nguồn nào là chuẩn và cách phát hiện khi các giá trị không khớp. Nếu không, producer có thể phát payload phiên bản 2 nhưng header vẫn ghi phiên bản 1, khiến consumer chọn sai decoder.

Một lựa chọn dễ di chuyển giữa broker là đưa phiên bản hợp đồng vào envelope hoặc gắn với schema ID được quản lý. Có thể đồng thời đưa phiên bản vào header để hỗ trợ routing hoặc quan sát, nhưng phải kiểm tra mapping và bảo đảm hai giá trị không mâu thuẫn.

### Phiên bản hợp đồng không phải phiên bản class

Không nên dùng tên class Java làm định danh hợp đồng công khai, ví dụ `com.example.OrderPlacedV2`, nếu tên class chỉ phản ánh chi tiết triển khai. Có thể giữ event type ổn định là `com.example.orders.OrderPlaced` và quản lý schema version riêng. Nếu thay đổi tạo ra một sự kiện có ý nghĩa nghiệp vụ khác, hãy đặt event type mới để thể hiện rõ sự khác biệt.

## 6. Tiến hóa schema mà không làm hỏng consumer

Khi thay đổi schema sự kiện, cần xem xét cả producer cũ, producer mới, consumer cũ, consumer mới và dữ liệu đã lưu trong broker. Các thay đổi phổ biến:

| Thay đổi | Rủi ro | Cách xử lý |
|---|---|---|
| Thêm trường tùy chọn có giá trị mặc định | Consumer cũ có thể bỏ qua; consumer mới phải xử lý dữ liệu cũ thiếu trường | Thường có thể tương thích nếu định dạng và quy tắc schema hỗ trợ |
| Thêm trường bắt buộc không có mặc định | Consumer hoặc dữ liệu cũ có thể không cung cấp giá trị | Cần kế hoạch chuyển đổi hoặc phát hành phiên bản mới |
| Đổi tên hoặc xóa trường | Consumer cũ có thể không đọc được; ý nghĩa dữ liệu lịch sử bị ảnh hưởng | Duy trì trường cũ trong giai đoạn chuyển tiếp hoặc tạo schema/event version mới |
| Đổi kiểu dữ liệu | Có thể không tương thích serializer và consumer | Đánh giá quy tắc chuyển đổi; thường cần phiên bản mới |
| Thay đổi ý nghĩa nghiệp vụ của trường | Dữ liệu vẫn giải mã được nhưng consumer có thể xử lý sai | Tạo hợp đồng hoặc event type mới nếu ngữ nghĩa thay đổi |

Một số chế độ tương thích thường gặp trong schema registry:

- **Backward compatibility**: schema mới có thể đọc dữ liệu được ghi bằng schema trước đó, theo quy tắc của registry/định dạng.
- **Forward compatibility**: schema trước có thể đọc dữ liệu được ghi bằng schema mới.
- **Full compatibility**: đáp ứng cả hai chiều tương thích.
- **Transitive compatibility**: kiểm tra tương thích với nhiều phiên bản trước đó thay vì chỉ phiên bản liền kề, tùy registry.

Tên chế độ giống nhau không đảm bảo mọi schema registry có cách kiểm tra hoàn toàn giống nhau. Cần đọc quy tắc của định dạng và registry đang sử dụng, đặc biệt về trường mặc định, nullable, union type, enum và alias.

Một chiến lược an toàn thường là thêm trường theo cách tương thích, triển khai consumer có khả năng đọc cả dữ liệu cũ và mới, sau đó mới phát producer dùng trường mới. Khi cần thay đổi phá vỡ tương thích, tạo schema hoặc event version mới và triển khai lộ trình chuyển đổi rõ ràng.

## 7. Consumer hỗ trợ nhiều phiên bản

Nếu một consumer phải nhận nhiều phiên bản trong giai đoạn chuyển tiếp, có thể định tuyến theo `eventVersion` rồi chuyển từng phiên bản sang một mô hình nội bộ ổn định:

```java
public record OrderPlacedV1(
    String orderId,
    BigDecimal total
) {}

public record OrderPlacedV2(
    String orderId,
    BigDecimal total,
    String currency
) {}

public record OrderCommand(
    String orderId,
    BigDecimal total,
    String currency
) {}
```

Adapter có thể chuyển đổi phiên bản cũ sang mô hình nội bộ:

```java
@Component
public class OrderEventMapper {

    public OrderCommand fromV1(OrderPlacedV1 event) {
        return new OrderCommand(
            event.orderId(),
            event.total(),
            "VND"
        );
    }

    public OrderCommand fromV2(OrderPlacedV2 event) {
        return new OrderCommand(
            event.orderId(),
            event.total(),
            event.currency()
        );
    }
}
```

Ví dụ dùng `VND` làm mặc định chỉ đúng nếu hợp đồng phiên bản 1 quy định rõ đơn vị tiền tệ đó. Không được tự suy diễn giá trị mặc định từ môi trường hoặc cấu hình hiện tại vì dữ liệu lịch sử có thể bị diễn giải sai.

Với payload JSON, adapter có thể đọc envelope hoặc metadata schema để chọn DTO tương ứng rồi ánh xạ sang `OrderCommand`. Với Avro hoặc Protobuf, serializer/deserializer và schema registry có thể hỗ trợ quá trình đọc schema cũ; vẫn cần kiểm thử cách các phiên bản thực tế được giải mã.

Không nên để mọi service nghiệp vụ nhận nhiều DTO phiên bản khác nhau. Hãy cô lập logic tương thích ở lớp biên, chuyển thành mô hình nội bộ thống nhất rồi mới gọi use case.

## 8. CloudEvents và metadata sự kiện chuẩn hóa

CloudEvents là một đặc tả envelope sự kiện nhằm chuẩn hóa các thuộc tính như:

- `specversion`: phiên bản đặc tả CloudEvents.
- `id`: định danh sự kiện.
- `source`: nguồn tạo sự kiện.
- `type`: loại sự kiện.
- `subject`: đối tượng mà sự kiện nói tới.
- `time`: thời điểm xảy ra.
- `datacontenttype`: kiểu nội dung của phần data.
- `dataschema`: định danh schema của phần data nếu có.

Các thuộc tính mở rộng có thể mang ngữ cảnh bổ sung theo quy ước, ví dụ tenant hoặc correlation ID. CloudEvents giúp các hệ thống khác nhau hiểu envelope thống nhất, nhưng không tự định nghĩa toàn bộ schema nghiệp vụ hay chính sách tương thích của từng event type.

Cần phân biệt `specversion` với phiên bản schema sự kiện. `specversion: 1.0` chỉ ra phiên bản của đặc tả CloudEvents; nó không có nghĩa payload `OrderPlaced` là phiên bản 1. Nếu cần quản lý phiên bản schema, dùng `dataschema`, extension attribute theo hợp đồng hoặc schema registry thích hợp.

Có thể biểu diễn cùng sự kiện theo dạng CloudEvents JSON:

```json
{
  "specversion": "1.0",
  "id": "evt-1007",
  "source": "/services/order-service",
  "type": "com.example.orders.OrderPlaced",
  "subject": "orders/order-1007",
  "time": "2026-11-24T10:15:30Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.example.com/orders/order-placed/2",
  "data": {
    "orderId": "order-1007",
    "customerId": "customer-42",
    "total": 1250000,
    "currency": "VND"
  }
}
```

Trong ví dụ, `dataschema` định danh schema cụ thể; `specversion` vẫn là phiên bản CloudEvents. Khi dùng CloudEvents qua Spring Cloud Stream, cần xác định binder và converter hỗ trợ cách biểu diễn nào: envelope trong payload hay ánh xạ thuộc tính sang transport headers. Không giả định binder tự động chuyển mọi thuộc tính CloudEvents thành header của broker.

## 9. Cấu hình và kiểm thử header trong Spring Cloud Stream

Một binding có thể khai báo content type và destination:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.placed
          content-type: application/json
```

Function tạo message với header đã thống nhất:

```java
@Configuration
public class OrderFunctions {

@Bean
Function<PlaceOrder, Message<OrderPlaced>> publishOrder(
        OrderApplicationService service) {

    return command -> {
        OrderPlaced event = service.place(command);

        return MessageBuilder
            .withPayload(event)
            .setHeader("eventType", "com.example.orders.OrderPlaced")
            .setHeader("eventVersion", 2)
            .setHeader("eventId", event.eventId())
            .setHeader("correlationId", command.correlationId())
            .build();
    };
}
}
```

Đoạn code giả định kiểu `OrderPlaced` có phương thức `eventId()` và command có `correlationId()`. Trong ứng dụng thực tế, hãy bảo đảm event ID được tạo một lần cho sự kiện và được giữ nguyên khi phát lại, thay vì tạo ID mới mỗi lần retry ở tầng producer.

Có thể kiểm thử việc tạo header bằng unit test trực tiếp:

```java
@Test
void publishesOrderWithContractMetadata() {
    OrderApplicationService service = mock(OrderApplicationService.class);
    OrderFunctions functions = new OrderFunctions();

    PlaceOrder command = new PlaceOrder("order-1007", "checkout-9001");
    OrderPlaced event = sampleOrderPlaced();

    when(service.place(command)).thenReturn(event);

    Message<OrderPlaced> message =
        functions.publishOrder(service).apply(command);

    assertThat(message.getHeaders().get("eventType"))
        .isEqualTo("com.example.orders.OrderPlaced");
    assertThat(message.getHeaders().get("eventVersion")).isEqualTo(2);
    assertThat(message.getHeaders().get("correlationId"))
        .isEqualTo("checkout-9001");
}
```

Đây là ví dụ minh họa; constructor và cách tổ chức bean trong dự án có thể khác. Unit test xác minh adapter tạo metadata theo hợp đồng. Spring Cloud Stream Test Binder có thể kiểm tra message qua binding trong bộ nhớ. Integration test với broker thật mới xác minh được header mapping, kiểu dữ liệu header, serializer, partition/routing và khả năng đọc lại message.

Một bộ kiểm thử nên bao gồm:

1. Header bắt buộc bị thiếu hoặc sai kiểu.
2. Event type không được consumer hỗ trợ.
3. Event version cũ và mới đều được xử lý theo chính sách.
4. Schema không tương thích bị từ chối có kiểm soát.
5. Correlation ID và event ID được giữ qua các bước cần thiết.
6. Binder thực tế chuyển được header cần thiết qua broker.
7. Message lỗi được xử lý theo retry hoặc DLQ đã cấu hình.

## 10. Checklist quản lý header và phiên bản

- Payload chứa dữ kiện cốt lõi mô tả điều đã xảy ra; header chứa metadata cần cho vận chuyển, định tuyến hoặc quan sát.
- Mỗi header tùy chỉnh có tên, kiểu, ý nghĩa, nguồn tạo và quy tắc bắt buộc/tùy chọn rõ ràng.
- Chọn một nguồn có thẩm quyền cho event type và event schema version.
- Không nhầm phiên bản schema sự kiện với phiên bản CloudEvents hoặc phiên bản broker.
- Đánh giá tương thích khi thêm, đổi, xóa trường và khi phát lại dữ liệu lịch sử.
- Dùng event ID ổn định để hỗ trợ audit và idempotency; dùng correlation ID để theo dõi luồng.
- Không coi header tenant hoặc role là bằng chứng phân quyền nếu chưa xác thực nguồn gửi.
- Không đưa secret hoặc dữ liệu nhạy cảm vào header.
- Kiểm tra giới hạn và mapping header của binder/broker thực tế.
- Kiểm thử cả payload, header, schema compatibility và quá trình chuyển đổi phiên bản.

Header nghiệp vụ và thông tin phiên bản giúp các dịch vụ diễn giải sự kiện nhất quán qua thời gian. Khi payload, metadata ứng dụng, metadata transport và schema version có ranh giới rõ ràng, producer có thể tiến hóa hợp đồng có kiểm soát, còn consumer có thể tiếp tục xử lý dữ liệu cũ và mới mà không phụ thuộc vào chi tiết triển khai của một broker duy nhất.

