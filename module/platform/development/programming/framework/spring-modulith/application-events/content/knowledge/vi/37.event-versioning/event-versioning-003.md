# Version trong payload

Event thường tồn tại lâu hơn một lần triển khai ứng dụng. Một producer có thể phát event hôm nay, trong khi consumer đọc lại event đó sau vài tuần hoặc nhiều tháng. Trong thời gian đó, cấu trúc payload có thể thay đổi: thêm trường, đổi tên thuộc tính, thay kiểu dữ liệu hoặc thay ý nghĩa nghiệp vụ. Nếu producer và consumer không thống nhất cách nhận diện phiên bản, một thay đổi tưởng như nhỏ có thể làm hỏng listener đang chạy hoặc khiến dữ liệu lịch sử không thể replay.

Version trong payload cho consumer biết cấu trúc và quy ước dữ liệu của event đang nhận. Trong ứng dụng Spring Modulith, điều này quan trọng cả với application event giữa các module lẫn integration event được externalize sang broker. Event type cho biết sự kiện nào đã xảy ra; schema version cho biết payload phải được diễn giải theo hợp đồng nào.

Bài này trình bày cách thiết kế version trong payload, quy tắc thay đổi tương thích, cách xử lý nhiều phiên bản trong consumer, upcasting dữ liệu cũ, triển khai producer/consumer theo từng giai đoạn và kiểm thử contract để event có thể được đọc an toàn qua nhiều lần nâng cấp.

## 1. Vì sao payload cần version?

Giả sử module Order phát event OrderPlaced với dữ liệu ban đầu:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderPlaced",
  "orderId": "order-42",
  "total": 125.00
}
~~~

Sau một lần nâng cấp, producer cần gửi thêm currency và thời điểm tạo:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "orderId": "order-42",
  "total": 125.00,
  "currency": "VND",
  "occurredAt": "2026-11-25T10:00:00Z"
}
~~~

Consumer cũ có thể bỏ qua trường mới nếu serializer được cấu hình theo hướng tolerant. Nhưng consumer mới có thể không đọc được event cũ nếu nó bắt buộc phải có currency hoặc occurredAt. Vấn đề nghiêm trọng hơn khi trường total đổi từ số thập phân sang chuỗi, hoặc ý nghĩa của total chuyển từ tổng trước thuế sang tổng sau thuế.

Version giúp consumer chọn đúng quy tắc diễn giải, xác định có thể xử lý payload hay cần chuyển đổi, quarantine hoặc từ chối. Nó cũng giúp đội vận hành biết event lịch sử được tạo theo hợp đồng nào.

Không nên suy ra version từ ngày deploy, tên class Java hoặc phiên bản ứng dụng producer. Một producer có thể phát nhiều loại event và nhiều schema version trong giai đoạn rolling deployment. Version cần gắn với chính payload hoặc envelope của event.

## 2. Phân biệt event type, schema version và aggregate version

Ba khái niệm này thường bị nhầm lẫn:

| Trường | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| eventType | Sự kiện nghiệp vụ nào đã xảy ra? | OrderPlaced |
| schemaVersion | Payload tuân theo hợp đồng cấu trúc nào? | 1, 2 |
| aggregateVersion | Aggregate đã ở phiên bản trạng thái thứ mấy khi phát event? | 17 |

schemaVersion thay đổi khi hợp đồng payload thay đổi theo chính sách versioning. aggregateVersion tăng theo mỗi thay đổi trạng thái của aggregate và thường được dùng để phát hiện event đến sai thứ tự hoặc bị thiếu. Hai giá trị không thay thế nhau.

Một envelope có thể chứa:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "occurredAt": "2026-11-25T10:00:00Z",
  "aggregateId": "order-42",
  "aggregateVersion": 17,
  "correlationId": "corr-8f31",
  "causationId": "cmd-778",
  "payload": {
    "orderId": "order-42",
    "total": "125.00",
    "currency": "VND"
  }
}
~~~

Envelope giữ metadata dùng chung như event ID, correlation ID và version; payload chứa dữ liệu riêng của loại event. Tổ chức envelope cần được quy định thống nhất cho tất cả producer và consumer.

Nếu event type đã được mã hóa trong tên topic, routing key hoặc header, vẫn nên có một quy ước xác định event type duy nhất. Đừng để consumer phải đoán event type từ nhiều nguồn không nhất quán.

## 3. Đặt version ở đâu trong payload?

Có một số cách thường gặp:

**Version trong envelope:** schemaVersion nằm ở cấp cao nhất, bên cạnh eventType và eventId. Đây là cách dễ đọc và thuận tiện cho router/upcaster vì có thể xác định version trước khi parse payload chi tiết.

**Version trong payload riêng:** mỗi DTO chứa trường version. Cách này có thể phù hợp khi payload được lưu và trao đổi độc lập, nhưng dễ lặp lại metadata giữa nhiều event.

**Version trong message header:** broker message có header như schema-version. Cách này hữu ích cho routing hoặc filtering, nhưng header có thể bị mất khi payload được lưu, export hoặc replay qua hệ thống khác. Nếu version chỉ tồn tại trong header, dữ liệu payload độc lập có thể không còn tự mô tả.

Một lựa chọn thực tế là đặt version trong envelope và có thể lặp lại trong transport header để phục vụ broker tooling. Nếu lặp lại, phải quy định hai giá trị luôn giống nhau và consumer xử lý rõ khi chúng mâu thuẫn.

Ví dụ Java:

~~~java
public record EventEnvelope<T>(
        UUID eventId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String correlationId,
        String causationId,
        T payload
) {}
~~~

Không dùng @Version của JPA để làm schema version. @Version thường phục vụ optimistic locking cho entity; schema version là phiên bản hợp đồng event.

## 4. Chọn chiến lược versioning

Có nhiều cách đặt version. Điều quan trọng là chọn một quy ước rõ và áp dụng nhất quán.

| Chiến lược | Ví dụ | Phù hợp khi |
|---|---|---|
| Số nguyên trong envelope | schemaVersion: 2 | Hệ thống muốn một chuỗi phiên bản đơn giản cho từng event type |
| Semantic version | 2.1.0 | Cần phân biệt thay đổi lớn, bổ sung tương thích và sửa metadata |
| Tên event có version | OrderPlacedV2 | Các phiên bản có cấu trúc/semantics rất khác và cần route riêng |
| Schema ID/registry | ID tham chiếu tới schema đã đăng ký | Nhiều producer/consumer cần quản lý schema tập trung |

Với payload JSON trong ứng dụng Spring, một số nguyên schemaVersion theo từng eventType thường dễ vận hành. Nếu dùng semantic version, phải định nghĩa rõ consumer so sánh phiên bản như thế nào và thay đổi nào làm tăng major/minor/patch.

Không dùng một số version toàn cục cho toàn bộ hệ thống nếu mỗi loại event tiến hóa độc lập. OrderPlaced có thể ở version 3 trong khi PaymentCaptured vẫn ở version 1. Version là thuộc tính của hợp đồng event type cụ thể.

Cũng không tăng version chỉ vì phiên bản ứng dụng thay đổi. Chỉ tăng khi payload contract hoặc semantics cần consumer diễn giải theo quy tắc khác.

## 5. Quy tắc thay đổi tương thích

Tương thích có hai chiều:

- **Backward compatibility:** consumer mới có thể đọc payload cũ.
- **Forward compatibility:** consumer cũ có thể đọc payload mới.

Một thay đổi có thể tương thích theo một chiều nhưng không theo chiều còn lại. Khi triển khai rolling deployment, cả hai chiều đều cần được cân nhắc vì producer và consumer có thể chạy các phiên bản khác nhau cùng lúc.

### 5.1. Thay đổi thường có thể tương thích

Các thay đổi sau thường an toàn hơn nếu consumer được thiết kế tolerant:

- Thêm trường tùy chọn.
- Thêm metadata không làm thay đổi ý nghĩa trường cũ.
- Thêm giá trị enum mới nếu consumer có nhánh xử lý unknown value.
- Thêm một trường có default rõ ràng cho consumer cũ.

Tuy nhiên, thêm trường không tự động tương thích. Một consumer strict có thể từ chối unknown property; một consumer mới có thể yêu cầu trường mới dù event lịch sử chưa có. Hãy kiểm tra serializer/deserializer và quy tắc nghiệp vụ thực tế.

### 5.2. Thay đổi thường gây breaking change

Các thay đổi sau thường cần version mới hoặc migration có kiểm soát:

- Xóa trường đang được consumer sử dụng.
- Đổi tên trường mà không giữ alias hoặc mapping cũ.
- Đổi kiểu dữ liệu, ví dụ number thành string.
- Thay đổi đơn vị, scale hoặc currency semantics.
- Đổi ý nghĩa nghiệp vụ của một trường dù tên và kiểu không đổi.
- Biến trường tùy chọn thành bắt buộc.
- Thay đổi cách biểu diễn null, missing và empty.
- Chuyển timestamp từ local time sang UTC nhưng không đổi contract/documentation.

Một payload vẫn parse được không có nghĩa là tương thích nghiệp vụ. Ví dụ trường amount vẫn là decimal nhưng chuyển từ số tiền trước thuế sang số tiền sau thuế có thể làm consumer tính toán sai mà không ném exception.

## 6. Thiết kế payload có khả năng tiến hóa

Một event contract tốt cần mô tả kiểu dữ liệu, ý nghĩa, tính bắt buộc và quy tắc default cho từng trường.

Ví dụ DTO version 1:

~~~java
public record OrderPlacedV1(
        UUID orderId,
        BigDecimal total
) {}
~~~

Version 2 bổ sung currency và occurredAt:

~~~java
public record OrderPlacedV2(
        UUID orderId,
        BigDecimal total,
        String currency,
        Instant occurredAt
) {}
~~~

Nếu consumer mới phải đọc event V1, nó cần quy tắc chuyển đổi rõ ràng. Không nên tự gán currency mặc định tùy tiện nếu không có bảo đảm từ dữ liệu lịch sử. Nếu không thể suy ra giá trị đúng, consumer cần từ chối có kiểm soát hoặc dùng một nguồn dữ liệu bổ sung đáng tin cậy.

Các nguyên tắc thiết kế:

- Dùng tên trường mô tả rõ ý nghĩa nghiệp vụ.
- Chọn kiểu dữ liệu ổn định và không phụ thuộc class nội bộ.
- Quy định currency, timezone, precision và đơn vị đo.
- Phân biệt trường thiếu, null và chuỗi rỗng.
- Chỉ đánh dấu required khi producer cũ và dữ liệu lịch sử có thể đáp ứng.
- Có quy tắc cho enum/union value chưa biết.
- Tránh nhúng entity hoặc object graph của persistence vào payload.
- Duy trì fixture mẫu cho từng version được hỗ trợ.

Với tiền tệ, nên gửi amount và currency riêng, đồng thời thống nhất precision/rounding. Với thời gian, ưu tiên timestamp có timezone rõ ràng như ISO-8601 UTC. Với số lượng, ghi rõ đơn vị.

## 7. Ví dụ envelope và payload JSON

Một event version 1:

~~~json
{
  "eventId": "a9c3a2c4-50c0-4b80-a3e0-2f0b0a9c1010",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-25T10:00:00Z",
  "aggregateId": "order-42",
  "aggregateVersion": 1,
  "correlationId": "corr-8f31",
  "payload": {
    "orderId": "order-42",
    "total": 125000
  }
}
~~~

Một event version 2:

~~~json
{
  "eventId": "b7d1d5b4-8e62-4db7-b4c2-5e7a3d0b1002",
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "occurredAt": "2026-11-25T10:00:00Z",
  "aggregateId": "order-42",
  "aggregateVersion": 1,
  "correlationId": "corr-8f31",
  "payload": {
    "orderId": "order-42",
    "total": "1250.00",
    "currency": "VND",
    "pricingBasis": "TAX_INCLUDED"
  }
}
~~~

Ví dụ trên cố ý minh họa thay đổi kiểu của total và thêm currency/pricingBasis. Đây là breaking change nên schemaVersion tăng. Việc chuyển 125000 thành chuỗi 1250.00 chỉ đúng nếu hợp đồng cũ quy định total là đơn vị đồng nguyên và hợp đồng mới quy định decimal string theo cùng currency; trong thực tế phải ghi rõ quy tắc chuyển đổi và không suy diễn từ ví dụ.

Một consumer có thể chọn decoder theo cặp eventType và schemaVersion:

~~~java
public OrderPlacedEvent decode(EventEnvelope<JsonNode> envelope) {
    return switch (envelope.schemaVersion()) {
        case 1 -> decodeV1(envelope.payload());
        case 2 -> decodeV2(envelope.payload());
        default -> throw new UnsupportedEventVersionException(
                envelope.eventType(),
                envelope.schemaVersion()
        );
    };
}
~~~

Trong production, kiểm tra cả eventType trước khi dispatch và phân loại lỗi unsupported version để đưa message vào quarantine/DLQ. Không retry vô hạn một payload có version mà consumer không hỗ trợ.

## 8. Backward compatibility và tolerant reader

Consumer thường nên chịu được thay đổi bổ sung không ảnh hưởng đến logic của nó. Với JSON/Jackson, có thể cấu hình bỏ qua unknown property cho một DTO nếu chính sách contract cho phép:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderPlacedPayload(
        UUID orderId,
        BigDecimal total
) {}
~~~

Cấu hình tolerant reader giúp consumer cũ đọc payload có thêm trường. Nhưng nó không giải quyết trường bắt buộc bị thiếu, thay đổi kiểu dữ liệu hoặc thay đổi semantics.

Không nên bật bỏ qua mọi lỗi deserialize. Nếu payload thiếu orderId hoặc total mà consumer cần để xử lý, message phải bị từ chối có kiểm soát. Phân biệt unknown field (có thể bỏ qua) với missing required field (cần lỗi contract).

Với enum, có thể định nghĩa UNKNOWN/OTHER hoặc một nhánh fallback. Tuy nhiên, fallback chỉ an toàn nếu consumer biết cách xử lý giá trị mới mà không làm sai nghiệp vụ. Nếu unknown payment status không thể xử lý an toàn, hãy quarantine thay vì map thành trạng thái mặc định có vẻ hợp lệ.

## 9. Forward compatibility và producer/consumer rollout

Forward compatibility giúp consumer cũ tiếp tục đọc payload mới. Điều này hữu ích trong rolling deployment khi producer được nâng cấp trước một số consumer.

Để tăng khả năng tương thích:

- Consumer bỏ qua trường không biết khi trường đó không ảnh hưởng logic của nó.
- Producer không xóa trường cũ ngay khi đã phát trường mới.
- Consumer không giả định enum chỉ có các giá trị đã biết nếu contract cho phép mở rộng.
- Trường mới chỉ được dùng cho logic bắt buộc sau khi mọi consumer liên quan đã hỗ trợ nó.
- Kiểm thử consumer cũ với payload mới trước khi rollout.

Với thay đổi breaking, dùng triển khai nhiều giai đoạn:

1. Phát hành consumer có khả năng đọc cả version cũ và mới.
2. Xác minh consumer mới chạy ổn định trên payload version cũ.
3. Triển khai producer bắt đầu phát version mới.
4. Theo dõi tỷ lệ decode, lỗi contract và DLQ.
5. Chờ hết retention/replay window hoặc xử lý xong event version cũ.
6. Chỉ loại bỏ decoder cũ khi đã có bằng chứng không còn dữ liệu cần đọc.

Nếu producer và consumer không thể được nâng cấp đồng thời, cần giữ compatibility window đủ dài cho deployment, backlog và replay.

## 10. Upcasting: chuyển payload cũ sang mô hình nội bộ mới

Upcasting là quá trình chuyển một event ở schema version cũ sang biểu diễn mới mà consumer hiện tại sử dụng. Thay vì để mọi business handler xử lý nhiều cấu trúc payload, adapter có thể decode version cũ rồi chuyển về một mô hình chuẩn nội bộ.

~~~text
Payload V1 ----> Decoder V1 ----+
                               +----> Current OrderPlaced model ----> Handler
Payload V2 ----> Decoder V2 ----+
~~~

Ví dụ:

~~~java
OrderPlacedEvent upcastV1(OrderPlacedV1 oldEvent) {
    return new OrderPlacedEvent(
            oldEvent.orderId(),
            oldEvent.total(),
            currencyForLegacyOrder(oldEvent.orderId()),
            oldEvent.occurredAt()
    );
}
~~~

Ví dụ chỉ hợp lệ nếu currency và occurredAt có thể được xác định đáng tin cậy. Nếu không có dữ liệu đó, không nên bịa default để làm event parse thành công.

Upcaster nên:

- Có tính xác định: cùng payload/version tạo cùng kết quả.
- Không ghi đè dữ liệu gốc.
- Có test fixture cho từng version cũ.
- Có thể chạy lại an toàn khi replay.
- Tách chuyển đổi cấu trúc khỏi quyết định nghiệp vụ.
- Báo lỗi rõ khi không thể chuyển đổi an toàn.

Với nhiều version liên tiếp, có thể chuyển V1 sang V2 rồi V3 hoặc chuyển trực tiếp từng version cũ về current model. Chọn cách giúp kiểm soát độ phức tạp và test coverage. Không để chuỗi upcaster tăng vô hạn mà không có chính sách ngừng hỗ trợ version cũ.

## 11. Versioning trong Spring Modulith

Spring Modulith dùng application events để giao tiếp giữa các module trong cùng ứng dụng. Khi các module được build và deploy cùng nhau, thay đổi class event có thể được cập nhật đồng thời, nhưng điều đó không loại bỏ nhu cầu quản lý hợp đồng.

Một số nguyên tắc:

- Đặt event trong package API mà module nhận được phép phụ thuộc.
- Không dùng JPA entity hoặc class implementation làm payload.
- Nếu event được lưu, replay hoặc externalize, cần hợp đồng có khả năng diễn giải độc lập với phiên bản code hiện tại.
- Nếu có nhiều module hoặc consumer triển khai độc lập, version payload cần được quản lý rõ.
- Event Publication Registry theo dõi publication tới listener; nó không tự động là schema registry hoặc event store dài hạn.

Ví dụ module Order công bố event nội bộ và adapter ánh xạ sang integration envelope:

~~~java
public record OrderPlaced(
        UUID orderId,
        BigDecimal total,
        long aggregateVersion
) {}

@Component
class OrderIntegrationMapper {

    EventEnvelope<OrderPlacedPayloadV2> toIntegrationEvent(
            OrderPlaced event,
            UUID eventId,
            String correlationId
    ) {
        return new EventEnvelope<>(
                eventId,
                "OrderPlaced",
                2,
                Instant.now(),
                correlationId,
                null,
                new OrderPlacedPayloadV2(
                        event.orderId(),
                        event.total().toPlainString(),
                        "VND"
                )
        );
    }
}
~~~

Đây là ví dụ về ranh giới adapter; không nhất thiết phải thêm schemaVersion vào mọi application event nội bộ nếu các module luôn được nâng cấp đồng bộ và không lưu payload theo hợp đồng lâu dài. Tuy nhiên, integration event qua broker cần version rõ ràng vì producer và consumer có vòng đời triển khai độc lập.

Nếu dùng Spring Modulith externalization, xác minh API mapping và serialization của đúng phiên bản thư viện. Không giả định framework tự nâng cấp payload hoặc tự tương thích mọi schema version.

## 12. Event versioning và replay lịch sử

Replay có thể đọc event đã lưu từ trước khi schema mới được triển khai. Consumer cần biết version gốc và chuyển đổi theo cùng quy tắc đã dùng trong live processing.

Các điểm cần kiểm tra:

- Nguồn lưu trữ có giữ schemaVersion cùng payload không?
- Event ID gốc có được giữ nguyên khi replay không?
- Upcaster có thể đọc mọi version còn trong retention window không?
- Consumer có idempotency để tránh áp dụng lại side effect không?
- Replay có tạo một recoveryRunId riêng để quan sát không?
- Nếu event không thể upcast, có quy trình quarantine/manual repair không?

Không sửa payload lịch sử tại chỗ chỉ để phù hợp code mới. Giữ bản gốc giúp audit và có thể chạy lại bằng decoder khác. Upcasting nên diễn ra khi đọc hoặc trong một migration được quản lý riêng.

Publication Registry của Spring Modulith phục vụ trạng thái giao event tới listener và không mặc nhiên lưu toàn bộ lịch sử event đã hoàn tất. Nếu cần replay dài hạn, dùng event store, outbox archive hoặc nguồn lưu trữ có retention phù hợp.

## 13. Schema registry và schema contract

Trong hệ thống có nhiều producer/consumer, schema registry có thể quản lý schema đã đăng ký, ID/version, compatibility policy và lịch sử thay đổi. Các định dạng như Avro, Protobuf hoặc JSON Schema có thể được dùng tùy hệ sinh thái.

Schema registry giúp:

- Kiểm tra producer không phát payload trái schema.
- Kiểm tra compatibility trước khi publish schema mới.
- Consumer tra schema theo ID/version.
- Lưu lịch sử schema và hỗ trợ nhiều consumer.
- Giảm việc copy DTO hoặc schema thủ công giữa repository.

Tuy nhiên, schema registry không thay thế kiểm thử nghiệp vụ. Hai payload có thể cùng schema nhưng khác semantics. Cần review ý nghĩa trường, đơn vị, invariants và cách consumer xử lý unknown value.

Nếu hệ thống chưa cần registry tập trung, có thể bắt đầu bằng schema file được version hóa trong source control, fixture payload và contract test. Điều quan trọng là schema phải có chủ sở hữu, quy trình thay đổi và chính sách compatibility rõ ràng.

## 14. Kiểm thử version trong payload

Mỗi version được hỗ trợ cần có fixture và test riêng. Một bộ kiểm thử nên bao gồm:

| Kịch bản | Điều cần xác minh |
|---|---|
| Consumer đọc version hiện tại | Decode đúng payload và tạo mô hình nội bộ |
| Consumer đọc version cũ | Upcast thành current model đúng quy tắc |
| Payload có trường mới không biết | Tolerant reader bỏ qua nếu contract cho phép |
| Payload thiếu trường bắt buộc | Từ chối rõ và đưa vào xử lý lỗi phù hợp |
| Enum có giá trị mới | Fallback an toàn hoặc quarantine |
| schemaVersion không hỗ trợ | Không retry vô hạn; ghi rõ event type/version |
| Trường đổi kiểu | Decoder version cũ/mới không nhầm lẫn |
| Trường đổi semantics | Version mới và logic chuyển đổi được kiểm thử |
| Replay event cũ | Giữ eventId và dedupe đúng |
| Producer/consumer rolling deploy | Các tổ hợp version được hỗ trợ cùng hoạt động |
| Envelope header khác payload version | Phát hiện mismatch và xử lý rõ |
| Upcaster chạy nhiều lần | Kết quả xác định, không sửa dữ liệu gốc |

Ví dụ kiểm thử decoder:

~~~java
@Test
void decodesVersionOnePayload() {
    EventEnvelope<JsonNode> envelope =
            fixtureReader.read("order-placed-v1.json");

    OrderPlacedEvent event = decoder.decode(envelope);

    assertThat(event.orderId()).isEqualTo(UUID.fromString(
            "8c1f7b1b-5b70-4f6a-a5d4-6fca2f5c8d77"
    ));
}
~~~

Ngoài unit test decoder, cần integration test qua message converter hoặc application adapter để chứng minh header, envelope và serializer thực tế giữ đúng version.

Không chỉ test payload do producer hiện tại tạo ra. Consumer phải được test với fixture của các version cũ còn được hỗ trợ, vì đó là dữ liệu sẽ xuất hiện trong backlog hoặc replay.

## 15. Quan sát và vận hành theo version

Khi có nhiều schema version, metric và log cần cho biết version nào đang được phát và version nào đang bị consumer từ chối.

Nên ghi các field:

- eventType.
- schemaVersion.
- eventId.
- aggregateId và aggregateVersion.
- correlationId và causationId.
- producer/service name.
- consumer/listener name.
- decode/upcast outcome.
- error category và retry attempt.

Metric có thể theo dõi số event theo eventType/schemaVersion, tỷ lệ decode lỗi, số lần upcast, số event vào DLQ và tuổi backlog theo consumer. Không dùng eventId hoặc correlationId làm label metric vì cardinality rất cao; các ID chi tiết nên nằm trong log và trace.

Khi phát hành version mới, theo dõi tỷ lệ consumer đã hỗ trợ version đó và số message version cũ còn tồn đọng. Chỉ bỏ decoder cũ khi backlog, retention và replay policy chứng minh không còn cần.

## 16. Lỗi thường gặp khi version payload

**Dùng phiên bản ứng dụng làm schema version.** Một ứng dụng có thể phát nhiều event type và mỗi loại tiến hóa riêng. Version phải thuộc hợp đồng event type.

**Nhầm schemaVersion với aggregateVersion.** Schema version mô tả cấu trúc payload; aggregate version mô tả thứ tự thay đổi của một aggregate.

**Đặt version chỉ trong message header.** Khi payload được archive hoặc replay, header có thể mất. Giữ version trong envelope hoặc nguồn dữ liệu bền vững.

**Thêm trường bắt buộc mà không có default/migration.** Consumer mới có thể không đọc được event cũ. Cung cấp upcaster hoặc chiến lược compatibility.

**Đổi ý nghĩa trường nhưng giữ nguyên version.** Payload vẫn parse nhưng consumer tính sai. Thay đổi semantics cần được quản lý như contract change.

**Bỏ qua unknown enum một cách tùy tiện.** Giá trị mới có thể mang ý nghĩa nghiệp vụ quan trọng. Dùng fallback có chủ đích hoặc quarantine.

**Chỉ test version mới nhất.** Replay và backlog vẫn chứa payload cũ. Giữ fixture và test cho mọi version còn hỗ trợ.

**Sửa payload lịch sử tại chỗ.** Mất khả năng audit và tái hiện. Giữ payload gốc, upcast khi đọc hoặc dùng migration có kiểm soát.

**Retry vô hạn version không hỗ trợ.** Lỗi contract cố định không tự hết. Đưa vào quarantine/DLQ và cảnh báo.

**Cho rằng Spring Modulith tự quản lý schema evolution.** Application event publication và schema registry là các trách nhiệm khác nhau. Thiết kế version ở hợp đồng event và adapter.

## 17. Quy trình phát hành một payload version mới

Khi cần thay đổi event contract, thực hiện theo trình tự:

1. Xác định event type, consumer và các version đang được hỗ trợ.
2. Phân loại thay đổi là additive hay breaking, cả về cấu trúc lẫn semantics.
3. Cập nhật schema/fixture và tài liệu hợp đồng.
4. Viết decoder/upcaster cho version cũ nếu consumer mới cần đọc dữ liệu lịch sử.
5. Triển khai consumer có khả năng đọc version cũ và mới.
6. Xác minh consumer mới xử lý fixture cũ và payload mới.
7. Triển khai producer phát version mới theo rollout plan.
8. Theo dõi decode errors, upcast rate, DLQ và backlog.
9. Chỉ ngừng hỗ trợ version cũ sau khi hết retention/replay window và có bằng chứng không còn producer/consumer phụ thuộc.
10. Lưu lại compatibility decision và thời điểm ngừng hỗ trợ.

Version trong payload là một phần của event contract và cần được quản lý như API giữa các module hoặc service. Với Spring Modulith, application events giúp module giao tiếp qua ranh giới rõ ràng; adapter integration chịu trách nhiệm đóng gói schema version khi event đi ra ngoài tiến trình. Khi version, compatibility, upcasting, replay và contract test được thiết kế cùng nhau, producer và consumer có thể nâng cấp độc lập mà vẫn đọc được event lịch sử một cách có kiểm soát.
