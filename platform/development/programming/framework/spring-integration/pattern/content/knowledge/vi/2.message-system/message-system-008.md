# Loại payload và hợp đồng kiểu dữ liệu

## 1. Tại sao kiểu payload là một phần của thiết kế message system?

Trong Spring Integration, một thông điệp (*message*) không đơn thuần là đoạn JSON đi qua hàng đợi. Nó có **payload** chứa dữ liệu được xử lý và **headers** mô tả ngữ cảnh truyền nhận. Các endpoint như **Gateway, Filter, Transformer, Router, Splitter, Aggregator** làm việc với thông điệp theo những cách khác nhau. Để các thành phần ít phụ thuộc vào nhau, mỗi ranh giới cần một hợp đồng rõ ràng: nhận kiểu dữ liệu gì, trường nào bắt buộc, nội dung có ý nghĩa gì và gửi đi kiểu nào.

Ví dụ luồng xử lý đơn hàng có thể có các trạng thái:

1. Gateway nhận payload `OrderPlacedV1`.
2. Filter kiểm tra tính hợp lệ của nội dung.
3. Transformer chuẩn hóa thành payload `ValidatedOrder`.
4. Router xét thuộc tính vùng để chọn một trong hai channel.
5. Splitter tạo payload `OrderLineTask` cho từng dòng hàng.
6. Aggregator gom các kết quả cùng `orderId` thành `OrderSummary`.

Nếu không công bố kiểu và cấu trúc ở các bước trên, một handler có thể mong `OrderPlacedV1` nhưng thực tế nhận `String` hoặc `byte[]`. Lỗi có thể chỉ xuất hiện lúc chạy, thậm chí sau khi message đã qua nhiều channel.

**Mục tiêu học tập:** phân biệt kiểu dữ liệu trong bộ nhớ với biểu diễn trên đường truyền; chọn payload phù hợp; định nghĩa hợp đồng kiểu dữ liệu có version; thực hành kiểm tra kiểu và chuyển đổi an toàn; kiểm thử mọi nhánh và lỗi khi dữ liệu không đúng hợp đồng.

## 2. Cấu tạo Message<T> và vai trò của generic

Spring Messaging định nghĩa đối tượng `Message<T>` có hai phần chính:

- **`getPayload()`:** trả về một giá trị có kiểu `T` theo khai báo Java; payload chứa dữ liệu chính của nghiệp vụ.
- **`getHeaders()`:** trả về `MessageHeaders`, chứa thông tin như `id`, `timestamp` và các header tùy biến.

Ví dụ rút gọn, độc lập, chỉ minh họa một message trong bộ nhớ (mục 5 sẽ mở rộng record này thành hợp đồng đơn hàng có các dòng hàng):

~~~java
record OrderPlacedV1(String eventId, String orderId, String region) {}

OrderPlacedV1 order = new OrderPlacedV1("evt-101", "ord-501", "vn");
Message<OrderPlacedV1> message = MessageBuilder.withPayload(order)
    .setHeader("eventType", "order.placed")
    .setHeader("schemaVersion", 1)
    .setHeader("correlationId", "ord-501")
    .build();

OrderPlacedV1 payload = message.getPayload();
String eventType = (String) message.getHeaders().get("eventType");
~~~

Trong ví dụ, payload là một đối tượng `OrderPlacedV1` thực sự, chưa được chuyển thành JSON. Header `eventType` hay `schemaVersion` cung cấp metadata để các thành phần hiểu thông điệp; chúng **không tự kiểm tra** sự khớp nhau giữa schema và payload.

Đặc biệt, tham số generic `Message<OrderPlacedV1>` giúp trình biên dịch kiểm tra cách sử dụng ở những đoạn mã có thông tin kiểu, nhưng **không làm mọi channel trở thành channel chỉ nhận `OrderPlacedV1`**. Phần lớn luồng Spring Integration trao đổi đối tượng `Message<?>`; khi nhận đầu vào từ adapter, broker hay một producer khác, kiểu payload thực tế cần được xác minh tại runtime.

Một thông điệp thường có payload khác `null`; không nên dùng `null` làm sự kiện nghiệp vụ hoặc tín hiệu kết thúc nhóm. Hãy thiết kế sự kiện/trạng thái tường minh, chẳng hạn `OrderCancelled` hoặc `OrderProcessingFailed`.

## 3. Các dạng payload thường gặp

| Loại payload | Ví dụ | Sử dụng thích hợp | Nguy cơ cần quản lý |
|---|---|---|---|
| POJO, Java record | `OrderPlacedV1` | Luồng nghiệp vụ nội bộ đã biết schema | Thay đổi class có thể phá consumer cũ |
| `String` | JSON dạng text, CSV, dòng log | Nhận dữ liệu văn bản hoặc bước parse ban đầu | Chưa có bảo đảm cấu trúc và charset |
| `byte[]` | Dữ liệu JSON UTF-8, file, binary protocol | Transport, adapter, tệp và nội dung nhị phân | Phải biết encoding/schema; mảng có thể bị sửa |
| `Map<String, Object>` | Payload linh hoạt do parser tạo | Dữ liệu động hoặc khâu tương thích tạm thời | Sai tên khóa/kiểu giá trị chỉ lộ khi chạy |
| `List<OrderLineTask>` | Danh sách công việc | Bước ngay trước Splitter | Phải xác định danh sách rỗng có nghĩa gì |
| Kiểu đối tượng do thư viện tạo | HTTP response, database row | Adapter/tích hợp chuyên biệt | Dễ làm contract phụ thuộc vào thư viện ngoài |

`Message<T>` là **vỏ bao** payload cùng headers, không phải một loại payload nghiệp vụ riêng. Ưu tiên **kiểu nghiệp vụ rõ ràng và ít thay đổi** cho phần lõi xử lý. `String`, `byte[]` hoặc `Map` phù hợp ở ranh giới nhận dữ liệu, nhưng không nên để mọi handler tự đoán định dạng. Một Transformer ở gần cửa vào nên chuyển dữ liệu về kiểu mà các bước phía sau hiểu thống nhất.

**Phân biệt quan trọng:** kiểu của payload trong JVM, ví dụ `OrderPlacedV1`, khác với *wire format* khi gửi qua HTTP, AMQP hoặc Kafka, ví dụ JSON UTF-8. Một payload là Java record không có nghĩa là broker có thể truyền trực tiếp bản ghi đó; cần encoder/serializer và decoder/deserializer tương ứng.

## 4. Hợp đồng kiểu dữ liệu gồm những lớp nào?

Hợp đồng tốt trả lời nhiều câu hỏi hơn tên class. Với một sự kiện `OrderPlacedV1`, hãy viết rõ:

| Lớp hợp đồng | Cần mô tả | Ví dụ của order |
|---|---|---|
| **Identity** | Loại thông điệp, nguồn tạo, mục đích | `eventType=order.placed`, phát sau khi nhận đơn |
| **Shape** | Tên trường, kiểu, trường bắt buộc, khả năng rỗng | `orderId: String` bắt buộc; `lines: List<LineItem>` |
| **Semantics** | Ý nghĩa, đơn vị đo, điều kiện đúng | `quantity > 0`; `region` là mã thị trường |
| **Transformation** | Input/output type của mỗi bước | `OrderPlacedV1 → ValidatedOrder` |
| **Version** | Phiên bản và cách consumer nhận version mới | `schemaVersion=1`; quy tắc hỗ trợ v1/v2 |
| **Wire format** | Encoding, serializer, content type, field naming | JSON UTF-8, `application/json` |
| **Failure contract** | Thiếu field, sai kiểu, lỗi version thì xử lý đâu | Reject/quarantine, có mã lỗi và `eventId` |
| **Operational metadata** | Correlation, idempotency, trace, thời điểm | `eventId` riêng biệt với `orderId` |

Trong một module Spring Integration triển khai Enterprise Integration Patterns, hợp đồng này là điểm nối giữa các endpoint: Filter/Router cần biết **giá trị nào hợp lệ**, Transformer cần biết **kiểu đích**, Splitter/Aggregator cần biết **cách giữ định danh nhóm**, còn Gateway và adapter cần biết **cách chuyển dữ liệu vào/ra**.

## 5. Thiết kế payload nghiệp vụ rõ ràng

Giả sử nhận một sự kiện đặt hàng gồm nhiều mặt hàng. Java record giúp thể hiện cấu trúc bất biến ở mức các tham chiếu field; nhưng collection lồng bên trong vẫn cần sao chép nếu muốn ngăn thay đổi ngoài ý muốn.

~~~java
record LineItem(String sku, int quantity) {}

record OrderPlacedV1(
    String eventId,
    String orderId,
    int schemaVersion,
    String region,
    List<LineItem> lines
) {
    OrderPlacedV1 {
        lines = lines == null ? null : List.copyOf(lines);
    }
}

record ValidatedOrder(
    String eventId,
    String orderId,
    String region,
    List<LineItem> lines
) {
    ValidatedOrder {
        lines = List.copyOf(lines);
    }
}
~~~

`OrderPlacedV1` thể hiện dữ liệu **như đã nhận**. `ValidatedOrder` biểu diễn dữ liệu **sau khi được kiểm tra và chuẩn hóa**. Tách hai kiểu giúp handler phía sau không phải liên tục kiểm tra `region` đã trim hay chưa. `schemaVersion` dùng để xác định hợp đồng phát/nhận, còn `eventId` giúp nhận diện lần phát sự kiện và hỗ trợ chống xử lý trùng.

Nếu ứng dụng thật phải ghi tiền, nên dùng kiểu giá trị như `BigDecimal` cùng quy tắc currency và scale cụ thể; tránh truyền `double` cho số tiền. Với timestamp, nên thống nhất định dạng, timezone và cách biểu diễn, ví dụ `Instant` trong Java và chuỗi ISO 8601 khi ở JSON.

**Quy ước hữu ích:** message dùng để thông báo sự kiện đã xảy ra nên có tên quá khứ như `OrderPlaced`; message yêu cầu hành động có thể dùng tên mệnh lệnh như `ReserveInventory`. Hợp đồng của command và event khác nhau về kỳ vọng phản hồi, retry và quyền sở hữu dữ liệu.

## 6. Kiểu dữ liệu chạy xuyên Gateway, Filter, Transformer và Router

Ví dụ Java DSL bên dưới minh họa một flow trong cùng ứng dụng. Lược bỏ các import Java/Spring/Spring Integration thường gặp; các record trong mục trước dùng lại ở đây.

~~~java
@MessagingGateway(defaultRequestChannel = "orders.in")
interface OrderGateway {
    void submit(OrderPlacedV1 event);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderTypeFlows {
    @Bean
    IntegrationFlow validateTransformRoute() {
        return IntegrationFlow.from("orders.in")
            .filter(OrderPlacedV1.class, this::isValid,
                spec -> spec.discardChannel("orders.rejected"))
            .transform(OrderPlacedV1.class,
                e -> new ValidatedOrder(
                    e.eventId(),
                    e.orderId(),
                    e.region().trim().toUpperCase(Locale.ROOT),
                    e.lines()))
            .route(ValidatedOrder.class, ValidatedOrder::region,
                spec -> spec.channelMapping("VN", "orders.vn")
                    .defaultOutputChannel("orders.other"))
            .get();
    }

    private boolean isValid(OrderPlacedV1 event) {
        return event.schemaVersion() == 1
            && event.eventId() != null && !event.eventId().isBlank()
            && event.orderId() != null && !event.orderId().isBlank()
            && event.region() != null && !event.region().isBlank()
            && event.lines() != null && !event.lines().isEmpty()
            && event.lines().stream().allMatch(line ->
                line != null && line.sku() != null
                    && !line.sku().isBlank() && line.quantity() > 0);
    }

    @Bean
    IntegrationFlow vnOrders() {
        return IntegrationFlow.from("orders.vn")
            .handle(message ->
                System.out.println("VN: " + message.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow otherOrders() {
        return IntegrationFlow.from("orders.other")
            .handle(message ->
                System.out.println("OTHER: " + message.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow rejectedOrders() {
        return IntegrationFlow.from("orders.rejected")
            .handle(message ->
                System.out.println("REJECTED: " + message.getPayload()))
            .get();
    }
}
~~~

Luồng vận hành như sau:

~~~mermaid
flowchart LR
    G["Gateway: OrderPlacedV1"] --> F{"Filter: hợp lệ?"}
    F -->|"Không"| X["orders.rejected: OrderPlacedV1"]
    F -->|"Có"| T["Transformer: ValidatedOrder"]
    T --> R{"Router: region"}
    R -->|"VN"| V["orders.vn: ValidatedOrder"]
    R -->|"Khác"| O["orders.other: ValidatedOrder"]
~~~

Ví dụ đầu vào `region=" vn "` hợp lệ và được chuẩn hóa thành `"VN"`, sau đó định tuyến tới `orders.vn`. Message bị Filter loại gửi sang `orders.rejected` vẫn mang **payload gốc** `OrderPlacedV1`, vì chưa qua Transformer. Hai channel đích sau Router nhận **payload mới** `ValidatedOrder`. Đó là lý do mỗi nhánh cần ghi rõ kiểu mà endpoint cuối cùng có thể nhận.

Đoạn mã minh họa dùng Gateway với phương thức `void`. Khi flow xử lý đồng bộ, lời gọi có thể vẫn chờ các handler hoàn tất; `void` không đồng nghĩa một message đã được lưu bền vững hoặc xử lý bất đồng bộ.

**Giới hạn bảo vệ kiểu:** `.filter(OrderPlacedV1.class, ...)` diễn đạt kiểu mà endpoint mong đợi; nó không tự biến mọi byte/String đầu vào thành `OrderPlacedV1`. Nếu producer đẩy một kiểu khác vào `orders.in`, hệ thống có thể báo lỗi chuyển đổi hoặc gọi handler. Cần kiểm tra kiểu tại ingress, đặt converter rõ ràng, và có quy trình xử lý lỗi phù hợp.

## 7. Transformer là ranh giới thay đổi hợp đồng

Một Transformer không chỉ thay giá trị mà có thể **đổi cả loại payload**:

~~~text
byte[] (JSON) --decode--> OrderPlacedV1
OrderPlacedV1 --validate/normalize--> ValidatedOrder
ValidatedOrder --split--> OrderLineTask
List<LineResult> --aggregate--> OrderSummary
OrderSummary --encode--> byte[] (JSON)
~~~

Mỗi mũi tên cần một hợp đồng đầu vào/đầu ra riêng. Một converter chỉ làm nhiệm vụ **biểu diễn** (ví dụ byte[] ⇄ đối tượng Java); business Transformer làm nhiệm vụ **ngữ nghĩa** (chuẩn hóa mã vùng, tính toán, chuyển đổi mô hình nghiệp vụ). Tách hai nhiệm vụ này giúp kiểm thử rõ ràng và tránh vô tình gắn nghiệp vụ vào transport.

Lỗi thường gặp là giả định biến `String` thành `OrderPlacedV1` bằng ép kiểu:

~~~java
Object incoming = "{\"orderId\":\"ord-501\"}";
// Sai: incoming là String, không phải OrderPlacedV1
// OrderPlacedV1 event = (OrderPlacedV1) incoming; // ClassCastException
~~~

Để có đối tượng Java cần **parse** bằng serializer phù hợp và kiểm tra schema. Chẳng hạn, với Jackson:

~~~java
ObjectMapper mapper = new ObjectMapper();
OrderPlacedV1 event = mapper.readValue(jsonBytes, OrderPlacedV1.class);
// Sau parse vẫn phải kiểm tra các ràng buộc nghiệp vụ.
~~~

Ví dụ trên minh họa thao tác parse, không phải flow đầy đủ. Cần cấu hình mapper, xử lý ngoại lệ, giới hạn kích thước message và các ràng buộc dữ liệu theo hệ thống thực tế. Với adapter của Spring Integration, chọn converter/transformer tương ứng; đừng mặc định thư viện tự suy ra class từ mọi payload.

## 8. Ranh giới wire format: JSON, byte[] và contentType

Giả sử dịch vụ khác phát một event JSON:

~~~json
{
  "eventId": "evt-101",
  "orderId": "ord-501",
  "schemaVersion": 1,
  "region": "vn",
  "lines": [
    { "sku": "SKU-10", "quantity": 2 },
    { "sku": "SKU-22", "quantity": 1 }
  ]
}
~~~

Nếu adapter nhận payload dạng `byte[]`, bước decode phải hiểu encoding UTF-8, định dạng JSON, schema phiên bản 1 và cách ánh xạ sang `OrderPlacedV1`. Nếu adapter đã tự decode thành đối tượng, tránh decode lại lần nữa.

Header `contentType=application/json` mô tả **kiểu biểu diễn trên đường truyền**, không phải bằng chứng runtime rằng payload là `OrderPlacedV1`. Thêm header JSON cho một POJO trong bộ nhớ cũng không tự serialize POJO ấy. Tương tự, tên class Java không phải hợp đồng tương thích giữa các dịch vụ viết bằng nhiều ngôn ngữ.

| Ranh giới | Payload có thể gặp | Việc cần làm |
|---|---|---|
| HTTP inbound | JSON text/bytes hoặc POJO đã decode | Xác định bước decode; validate schema và kích thước |
| AMQP inbound | bytes hoặc POJO tùy converter | Chọn content type, converter, header mapping và retry |
| Kafka inbound | bytes/String/POJO tùy deserializer | Khai báo serializer/deserializer và compatibility |
| JDBC outbound | DTO/command hoặc parameters | Ánh xạ field rõ ràng, kiểm tra transaction/idempotency |
| Message channel nội bộ | POJO/record | Dùng contract Java ổn định giữa endpoint |

Khi truyền qua broker hoặc process khác, không phải mọi header nội bộ đều được giữ nguyên. Hãy cấu hình header mapper hoặc đưa các metadata **thực sự cần thiết** vào hợp đồng truyền nhận: `eventId`, `orderId`, schema version, correlation và trace context. Không dùng tên class Java hay object serialization mặc định làm giao thức tích hợp dài hạn nếu cần tương thích nhiều phiên bản/ngôn ngữ.

## 9. Versioning và thay đổi hợp đồng an toàn

Payload thường thay đổi theo thời gian. Ví dụ phiên bản 2 cần thêm mã loại tiền và phí vận chuyển. Thay field hoặc thay ý nghĩa field có thể khiến consumer cũ xử lý sai dù JSON vẫn parse được.

| Thay đổi | Ảnh hưởng có thể có | Hướng xử lý |
|---|---|---|
| Thêm trường tùy chọn với mặc định rõ | Consumer cũ có thể bỏ qua nếu cấu hình hỗ trợ | Kiểm tra parser phía nhận; ghi rõ giá trị mặc định |
| Đổi tên/xóa trường bắt buộc | Consumer cũ không đọc được hoặc mất dữ liệu | Tạo schema version mới và migration |
| Đổi `quantity` từ số nguyên sang chuỗi | Sai kiểu hoặc sai logic | Đổi version, thêm adapter chuyển đổi |
| Đổi ý nghĩa `region` từ mã quốc gia sang vùng kho | Có thể lỗi ngầm nghiêm trọng | Đổi tên field hoặc sự kiện, có giai đoạn chuyển tiếp |
| Bổ sung enum value | Consumer cũ có thể gặp giá trị chưa biết | Có nhánh unknown/default và cảnh báo |
| Thay cơ chế correlation | Gộp nhầm hoặc không đủ message | Giữ khóa tương thích, kiểm thử xuyên version |

Không có quy tắc rằng **mọi field mới đều tương thích ngược**. Khả năng tương thích phụ thuộc serializer, chế độ xử lý unknown fields, schema registry (nếu dùng), giá trị mặc định và hành vi nghiệp vụ. Nên kiểm thử với ma trận **producer v1/v2 × consumer v1/v2** trước khi triển khai.

Một chiến lược an toàn là **đọc được version cũ trong thời gian chuyển tiếp, phát version mới khi các consumer đã sẵn sàng**, hoặc dùng adapter riêng để chuyển v1 → mô hình nội bộ thống nhất. Hãy quyết định version nằm trong payload hay metadata khi thiết kế hợp đồng; tránh để hai nguồn version mâu thuẫn.

## 10. Splitter và Aggregator cần giữ cả kiểu lẫn định danh nhóm

Khi chuyển `ValidatedOrder` thành nhiều `OrderLineTask`, đầu vào và đầu ra khác kiểu; đồng thời phải giữ mối liên hệ giữa các dòng hàng:

~~~java
record OrderLineTask(
    String orderId,
    String eventId,
    int lineIndex,
    String sku,
    int quantity
) {}

record LineResult(
    String orderId,
    int lineIndex,
    boolean reserved
) {}

record OrderSummary(
    String orderId,
    List<LineResult> results
) {}
~~~

Splitter có thể tạo các header chuỗi như `correlationId`, `sequenceNumber`, `sequenceSize`; Aggregator có thể dùng chúng để nhóm và phát kết quả theo điều kiện release. Khi các message con đi qua broker hoặc Transformer, phải kiểm tra header mapping và cách xác định lại correlation.

Một bài toán thực tế cần định nghĩa: **`orderId` là khóa nghiệp vụ**, **`eventId` là định danh sự kiện**, còn **`correlationId` là khóa gom thông điệp cho một lần xử lý**. Chúng có thể trùng giá trị theo thiết kế nhưng không mặc định đồng nghĩa. Với hai đơn hàng xử lý song song, chọn correlation sai sẽ làm gộp nhầm kết quả.

Payload `LineResult` cho biết dòng hàng nào hoàn tất; header cho biết nhóm hoặc lần thử xử lý nào đang diễn ra. Chỉ dựa vào `sequenceSize` không đủ để giải quyết tình huống message trùng, message muộn hoặc dòng hàng bị lỗi trước khi trả kết quả. Cần chính sách **timeout, release, expired-message handling, message store và deduplication**.

## 11. Sai kiểu, sai schema và sai nghiệp vụ là ba nhóm lỗi khác nhau

Giả sử một adapter nhận chuỗi `"hello"` trong khi flow mong đợi `OrderPlacedV1`. Đây là **lỗi biểu diễn/kiểu đầu vào**, không phải đơn hàng hợp lệ nhưng số lượng âm. Nên nhận diện và ghi thông tin tại ranh giới ingress.

| Tình huống | Phân loại | Hướng xử lý tham khảo |
|---|---|---|
| Payload JSON sai cú pháp | Deserialize/parse error | Reject hoặc quarantine, không retry vô hạn |
| JSON hợp lệ nhưng thiếu `orderId` | Schema/contract violation | Báo mã lỗi, event ID nếu có; không chuyển vào flow chính |
| Message có payload `String` nhưng handler cần record | Type mismatch/conversion error | Kiểm tra converter/adapter, error channel phù hợp |
| Record hợp schema nhưng `quantity=-1` | Business validation | Filter → discard/rejected channel, lưu lý do |
| Region mới chưa có nhánh | Routing contract | Nhánh mặc định tường minh, cảnh báo nếu cần |
| Dữ liệu hợp lệ nhưng kho timeout | Dependency/transient failure | Retry có giới hạn, backoff, idempotency |
| Duplicate `eventId` | Delivery/reprocessing | Kiểm tra idempotency key trước khi thực hiện tác dụng phụ |

Trong Spring Integration, **discard channel của Filter** dùng cho message không vượt điều kiện lọc. Lỗi exception trong handler có đường xử lý riêng: có thể truyền về caller trong flow đồng bộ hoặc đến error channel tùy endpoint, poller và cấu hình adapter bất đồng bộ. Không mặc định mọi lỗi đều được gửi tới cùng một nơi. Cần thiết kế cơ chế xử lý lỗi và điều kiện ack/retry cụ thể cho từng ranh giới.

Với payload không đáng tin cậy từ bên ngoài, hạn chế deserialize thành class tùy ý theo trường tên class do client gửi. Dùng danh sách schema/sự kiện được cho phép, kiểm tra kích thước và độ sâu dữ liệu, đồng thời tránh log toàn bộ nội dung nhạy cảm vào error channel.

## 12. Kiểm thử hợp đồng dữ liệu từ Gateway đến flow phân tán

Kiểm thử có giá trị phải xác nhận **type**, **ý nghĩa**, **rẽ nhánh**, **đường lỗi** và **tính tương thích**, thay vì chỉ gọi method mà không phát sinh exception.

| Test | Dữ liệu đưa vào | Điều phải xác minh |
|---|---|---|
| Happy path | `OrderPlacedV1` có `region=" vn "` | Transformer tạo `ValidatedOrder` với `region="VN"` |
| Filter invalid | Số lượng bằng 0 hoặc `lines` rỗng | Chỉ xuất hiện ở nhánh rejected với payload gốc |
| Sai kiểu runtime | Producer gửi `String` vào channel nhận record | Không lặng lẽ cast; có lỗi và context để chẩn đoán |
| JSON parse | bytes sai cú pháp hoặc thiếu trường bắt buộc | Lỗi parse/schema được phân loại, không vào handler nghiệp vụ |
| Router unknown | Region chưa hỗ trợ | Đến default channel hoặc đường từ chối đã định |
| Split/aggregate | Hai `orderId` có line result đến xen kẽ | Không gộp nhầm, kết quả có đúng kiểu `OrderSummary` |
| Tương thích version | Producer/consumer dùng version khác nhau | Chính sách tương thích thực thi đúng |
| Broker redelivery | Phát cùng `eventId` hai lần | Không tạo tác dụng phụ trùng, correlation vẫn nguyên |

Ví dụ test đơn vị cho bước chuẩn hóa có thể so sánh rõ cấu trúc đầu ra:

~~~java
OrderPlacedV1 input = new OrderPlacedV1(
    "evt-101",
    "ord-501",
    1,
    " vn ",
    List.of(new LineItem("SKU-10", 2))
);

ValidatedOrder actual = new ValidatedOrder(
    input.eventId(),
    input.orderId(),
    input.region().trim().toUpperCase(Locale.ROOT),
    input.lines()
);

assertEquals("VN", actual.region());
assertEquals("ord-501", actual.orderId());
assertEquals(2, actual.lines().get(0).quantity());
~~~

Đoạn trên kiểm tra phép chuẩn hóa theo dữ liệu mẫu; test integration thực sự còn phải khởi chạy flow và quan sát channel/handler đầu ra. Khi dùng Spring Integration Test hoặc Spring Boot Test, có thể thay handler hoặc gắn interceptor để ghi nhận message đến nhánh đích; với broker phải kiểm thử serialization, header mapping và redelivery trong môi trường tích hợp.

Đối với mỗi bài kiểm thử, nên ghi rõ **kiểu đầu vào**, **kiểu đầu ra**, **headers cần giữ**, **nhánh mong đợi** và **hành vi khi lỗi**. Đây cũng là dữ liệu hữu ích để theo dõi metric theo endpoint và truy vết correlation ID xuyên các dịch vụ.

## 13. Bài thực hành: thiết kế hợp đồng cho hệ thống xử lý đơn hàng

Hãy xây một flow gồm Gateway → Filter → Transformer → Router → Splitter → Aggregator, rồi thay đầu vào Gateway bằng adapter nhận JSON từ một tiến trình khác.

**Yêu cầu đầu vào:** sự kiện `OrderPlacedV1` có `eventId`, `orderId`, `schemaVersion`, `region` và danh sách dòng hàng. Mỗi dòng có `sku` và `quantity`. Hãy quy định version được hỗ trợ, độ dài cho các mã, danh sách rỗng, giới hạn kích thước payload và cách xử lý region chưa biết.

**Yêu cầu xử lý:** chỉ message hợp lệ mới được Transformer đổi thành `ValidatedOrder`; Splitter sinh các `OrderLineTask`; mỗi worker tạo `LineResult`; Aggregator tạo `OrderSummary` theo correlation chính xác. Thiết kế riêng luồng xử lý lỗi parse, lỗi nghiệp vụ và lỗi phụ thuộc.

**Yêu cầu triển khai phân tán:** mã hóa thành JSON UTF-8; công bố schema với consumer; giữ `eventId` và `orderId` qua adapter; mô phỏng message được giao lại và worker restart. Kiểm thử consumer cũ nhận sự kiện version mới theo chính sách đã chọn.

**Tiêu chí hoàn thành:**

1. Có bảng hợp đồng cho từng channel, ghi rõ payload type đầu vào/đầu ra và các headers cần giữ.
2. Có test cho dữ liệu hợp lệ, thiếu field, sai type, unknown region và version không tương thích.
3. Có test hai đơn hàng tách/gộp đan xen mà không trộn nhóm.
4. Có mô tả cách parse JSON, cấu hình codec và chuyển lỗi parse ra kênh xử lý phù hợp.
5. Có log/trace hoặc metric cho thấy một `eventId` đã qua các nhánh nào và nhận kết quả gì.
6. Có minh chứng redelivery không tạo thao tác nghiệp vụ lặp ngoài ý muốn.

## 14. Ghi nhớ khi chọn payload và thiết kế contract

**Kiểu Java, schema dữ liệu và wire format là ba lớp riêng:** `Message<T>` hỗ trợ biểu đạt kiểu trong code; schema quy định giá trị nào hợp lệ; serializer chuyển dữ liệu qua ranh giới tiến trình. Chúng phải được thiết kế thống nhất nhưng không tự thay thế nhau.

**Transformer công bố kiểu đích; Router/Filter biết kiểu mà mình xử lý; Splitter/Aggregator giữ khóa tương quan.** Mỗi bước nên có hợp đồng nhỏ, rõ ràng để có thể thay transport hoặc triển khai thành dịch vụ riêng mà vẫn kiểm thử được.

**Hợp đồng không kết thúc ở happy path.** Cần versioning, quy tắc unknown field, mã lỗi, định danh chống trùng, thông tin correlation và cách kiểm tra toàn bộ nhánh xử lý. Đó là nền tảng để xây dựng message flow ít phụ thuộc, mở rộng được và vận hành tin cậy với Spring Integration.
