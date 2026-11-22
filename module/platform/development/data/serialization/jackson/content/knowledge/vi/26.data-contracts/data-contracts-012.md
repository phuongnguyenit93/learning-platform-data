# Thiết kế dữ liệu mẫu và kiểm thử hợp đồng giữa bên gửi và bên nhận

Trong một hệ thống dùng JSON, bên gửi và bên nhận thường được phát triển ở những module, service hoặc thời điểm khác nhau. Bên gửi có thể serialize một DTO thành JSON rồi gửi qua HTTP, message broker hoặc file; bên nhận parse JSON đó thành DTO khác để xử lý. Hai phía chỉ phối hợp đúng khi chúng hiểu cùng một hợp đồng dữ liệu.

Một bài test chỉ serialize object rồi deserialize lại bằng cùng một ObjectMapper chưa đủ để chứng minh hợp đồng tương thích. Serializer và deserializer có thể cùng mắc một giả định sai nhưng vẫn round-trip thành công. Cần có dữ liệu mẫu độc lập, đại diện cho payload thực tế, và test riêng hành vi của bên gửi lẫn bên nhận.

Trong Jackson, có thể dùng ObjectWriter để kiểm tra JSON mà producer phát ra, ObjectReader/ObjectMapper để kiểm tra JSON mà consumer tiếp nhận, và JsonNode để so sánh cấu trúc JSON theo ý nghĩa thay vì phụ thuộc khoảng trắng hoặc thứ tự property.

Mục tiêu là tạo một bộ dữ liệu mẫu có chủ đích, xác định rõ field, kiểu, nullability, format và semantics, rồi dùng bộ dữ liệu đó để kiểm tra hai chiều: **bên gửi phát đúng hợp đồng; bên nhận hiểu đúng hợp đồng; thay đổi ở một phía không âm thầm phá phía còn lại.**

## 1. Hợp đồng dữ liệu giữa sender và receiver là gì?

Hợp đồng dữ liệu (data contract) mô tả cách hai thành phần trao đổi dữ liệu. Với JSON, hợp đồng thường xác định:

- Tên property và cách viết tên.
- Kiểu JSON của từng property: object, array, string, number, boolean hoặc null.
- Field bắt buộc và field tùy chọn.
- Ý nghĩa của field bị thiếu, field explicit null và giá trị rỗng.
- Định dạng ngày giờ, timezone, enum và identifier.
- Miền giá trị, precision và scale của số.
- Cấu trúc subtype/discriminator nếu payload đa hình.
- Chính sách với property không biết hoặc giá trị chưa hỗ trợ.
- Quy tắc versioning và tương thích ngược.

Ví dụ, một service gửi thông tin đơn hàng:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "order-created",
  "occurredAt": "2026-11-12T08:30:00Z",
  "order": {
    "orderId": "ORD-9001",
    "total": 125000.50,
    "currency": "VND",
    "items": [
      {
        "sku": "SKU-01",
        "quantity": 2
      }
    ]
  }
}
~~~

Sender có thể dùng record OrderCreatedEvent để tạo JSON. Receiver có thể dùng một DTO khác, chẳng hạn IncomingOrderEvent, để đọc payload. Hai class không cần giống nhau, nhưng JSON representation và ý nghĩa field phải thống nhất.

~~~text
Producer DTO
     |
     v
ObjectWriter / ObjectMapper
     |
     v
JSON payload  <---- HỢP ĐỒNG ---->
     |
     v
ObjectReader / ObjectMapper
     |
     v
Consumer DTO
     |
     v
Validation và xử lý nghiệp vụ
~~~

Hợp đồng nằm ở payload và semantics trao đổi, không nằm ở việc hai service có dùng chung một class Java hay không.

## 2. Vì sao cần dữ liệu mẫu độc lập?

Dữ liệu mẫu (contract fixture) là payload JSON được lưu hoặc tạo có chủ đích để đại diện cho một trường hợp trao đổi cụ thể. Fixture có thể là file trong test resources hoặc một hằng số JSON trong test.

Ví dụ:

~~~text
src/test/resources/contracts/
    order-created-v1.json
    order-created-without-note-v1.json
    order-created-null-customer-v1.json
    order-cancelled-v1.json
    order-created-unknown-field-v1.json
~~~

Fixture độc lập giúp:

- Producer test được JSON output có đúng shape.
- Consumer test được khả năng đọc payload không phụ thuộc producer implementation.
- Hai service khác ngôn ngữ vẫn dùng chung bộ ví dụ.
- Regression test phát hiện thay đổi schema ngoài ý muốn.
- Review thay đổi hợp đồng dễ dàng qua diff của file JSON.
- Có thể giữ payload đại diện cho phiên bản API/message cũ.

Nếu chỉ tạo payload bằng chính DTO producer trong test rồi đưa ngay vào DTO consumer, test có thể bỏ sót lỗi vì cả hai phía cùng được cập nhật theo một thay đổi. Fixture JSON cố định đóng vai trò ví dụ độc lập của hợp đồng.

### 2.1. Fixture không phải dữ liệu production tùy tiện

Không sao chép payload thật chứa thông tin cá nhân, token, địa chỉ hoặc bí mật vào repository. Hãy tạo dữ liệu tổng hợp (synthetic data) có hình dạng và biên giá trị giống dữ liệu thật nhưng không nhận diện được người dùng thật.

Fixture nên:

- Nhỏ, tập trung vào một hành vi.
- Có tên mô tả trường hợp.
- Có giá trị dễ đọc và dễ hiểu.
- Không chứa dữ liệu nhạy cảm.
- Có version hoặc metadata nếu cần.
- Được cập nhật cùng thay đổi hợp đồng có chủ đích.

Không tạo một file JSON khổng lồ cho mọi tình huống. Nhiều fixture nhỏ giúp biết chính xác test nào đang bảo vệ quy tắc nào.

## 3. Thiết kế bộ dữ liệu mẫu theo trường hợp

Một bộ fixture tốt bao phủ cả trường hợp bình thường, biên và lỗi. Không cần nhân bản mọi tổ hợp field; hãy chọn trường hợp đại diện cho từng quy tắc có ý nghĩa.

| Nhóm | Dữ liệu mẫu | Mục đích |
|---|---|---|
| Happy path | Payload đầy đủ, hợp lệ | Xác nhận luồng cơ bản |
| Optional field | Bỏ field tùy chọn | Kiểm tra default và missing semantics |
| Explicit null | Field có giá trị null | Phân biệt null với missing |
| Empty value | "", [], {} | Kiểm tra giá trị rỗng |
| Boundary | Min/max, số lớn, chuỗi dài hợp lệ | Bảo vệ miền giá trị |
| Format | Timestamp, enum, decimal | Bảo vệ representation |
| Nested data | Object/array nhiều cấp | Kiểm tra binding lồng nhau |
| Polymorphism | Nhiều subtype | Kiểm tra discriminator |
| Unknown field | Property mới chưa biết | Kiểm tra chính sách schema evolution |
| Invalid shape | String thay number, object thay array | Kiểm tra lỗi đầu vào |
| Truncated/malformed | JSON thiếu dấu đóng hoặc sai cú pháp | Kiểm tra parser error |

### 3.1. Mỗi fixture nên có một mục tiêu rõ

Ví dụ:

- order-created-v1.json: payload hợp lệ đầy đủ.
- order-created-no-note-v1.json: note không xuất hiện.
- order-created-null-note-v1.json: note xuất hiện với null.
- order-created-empty-items-v1.json: items là array rỗng.
- order-created-max-total-v1.json: total ở biên nghiệp vụ.
- order-created-unknown-field-v1.json: có field mới để kiểm tra consumer tolerant.
- order-created-invalid-quantity-v1.json: quantity có kiểu hoặc giá trị sai.

Tên file nên diễn đạt tình huống, không chỉ là sample1.json hoặc test-data-final.json.

### 3.2. Không cần mọi fixture đều là happy path

Payload lỗi có giá trị vì chúng xác định ranh giới hợp đồng. Nếu consumer cần từ chối quantity dạng string, hãy có fixture thể hiện trường hợp đó và test xác nhận lỗi. Nếu field optional được phép null, cần một fixture riêng cho explicit null.

Một bộ fixture tốt không chỉ nói "dữ liệu hợp lệ trông như thế nào", mà còn xác định "dữ liệu nào phải bị từ chối hoặc được diễn giải khác".

## 4. Tạo DTO hai phía và giữ ranh giới hợp đồng

Trong ví dụ, producer và consumer có thể dùng các class khác nhau.

DTO phía sender:

~~~java
public record OutgoingOrderCreated(
    String eventId,
    String eventType,
    Instant occurredAt,
    OutgoingOrder order
) {}

public record OutgoingOrder(
    String orderId,
    BigDecimal total,
    String currency,
    List<OutgoingOrderItem> items
) {}

public record OutgoingOrderItem(
    String sku,
    int quantity
) {}
~~~

DTO phía receiver:

~~~java
public record IncomingOrderCreated(
    String eventId,
    String eventType,
    Instant occurredAt,
    IncomingOrder order
) {}

public record IncomingOrder(
    String orderId,
    BigDecimal total,
    String currency,
    List<IncomingOrderItem> items
) {}

public record IncomingOrderItem(
    String sku,
    Integer quantity
) {}
~~~

Khác biệt như int và Integer có thể là quyết định nội bộ. Điều cần bảo đảm là sender không gửi quantity null nếu hợp đồng quy định integer bắt buộc, và receiver không vô tình biến null thành 0.

Nếu cả hai phía dùng chung một DTO library, vẫn cần contract fixture và test JSON. Dùng chung class không bảo đảm mapper configuration, module, naming strategy hoặc version dependency giống nhau.

### 4.1. DTO nội bộ không nhất thiết là schema công khai

Không nên để thay đổi cấu trúc domain model tự động thay đổi JSON contract. Có thể dùng DTO riêng ở ranh giới service:

~~~text
Domain model
     |
     v
Mapper / assembler
     |
     v
Contract DTO
     |
     v
Jackson ObjectWriter
     |
     v
JSON
~~~

Cách này giúp refactor domain mà vẫn giữ payload ổn định. Nó cũng cho phép hai service dùng ngôn ngữ và mô hình nội bộ khác nhau.

## 5. Cấu hình Jackson giống môi trường thật

Contract test phải dùng cấu hình Jackson mà ứng dụng thực sự sử dụng. Nếu production có JavaTimeModule, naming strategy, custom serializer, mix-in hoặc coercion policy, test tạo một ObjectMapper mặc định có thể cho kết quả khác.

Ví dụ cấu hình chung:

~~~java
public final class ContractJackson {

    private ContractJackson() {}

    public static ObjectMapper createMapper() {
        return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
            .build();
    }
}
~~~

Cấu hình trên là ví dụ. Dự án có thể cần thêm module hoặc feature khác. Điều quan trọng là contract test lấy mapper từ cùng cấu hình production, hoặc tái sử dụng factory cấu hình chung được production và test cùng gọi.

Không nên tạo mapper riêng trong từng test với một tập feature tùy ý. Điều đó làm test không còn đại diện cho ứng dụng.

### 5.1. Dùng ObjectWriter và ObjectReader

Sau khi cấu hình mapper, có thể tạo writer/reader theo kiểu contract:

~~~java
ObjectWriter orderWriter =
    mapper.writerFor(OutgoingOrderCreated.class);

ObjectReader orderReader =
    mapper.readerFor(IncomingOrderCreated.class);
~~~

ObjectWriter và ObjectReader là đối tượng cấu hình bất biến phù hợp để tái sử dụng. Chúng giúp test thể hiện rõ kiểu nguồn hoặc đích mà hợp đồng đang kiểm tra.

Nếu production sử dụng writer/reader riêng cho từng message type, hãy dùng đúng những đối tượng đó trong contract test.

## 6. Kiểm thử bên gửi: JSON output phải đúng hợp đồng

Test phía sender cần xác nhận object Java được serialize thành JSON có đúng property, type và semantics đã công bố.

Ví dụ:

~~~java
@Test
void senderProducesOrderCreatedContract() throws Exception {
    OutgoingOrderCreated event = new OutgoingOrderCreated(
        "evt-1001",
        "order-created",
        Instant.parse("2026-11-12T08:30:00Z"),
        new OutgoingOrder(
            "ORD-9001",
            new BigDecimal("125000.50"),
            "VND",
            List.of(new OutgoingOrderItem("SKU-01", 2))
        )
    );

    String json = orderWriter.writeValueAsString(event);
    JsonNode actual = mapper.readTree(json);

    assertEquals("evt-1001", actual.path("event_id").asText());
    assertEquals("order-created", actual.path("event_type").asText());
    assertEquals(
        "2026-11-12T08:30:00Z",
        actual.path("occurred_at").asText()
    );
    assertEquals("ORD-9001", actual.path("order").path("order_id").asText());
    assertEquals(
        new BigDecimal("125000.50"),
        actual.path("order").path("total").decimalValue()
    );
    assertEquals("VND", actual.path("order").path("currency").asText());
    assertEquals(
        2,
        actual.path("order").path("items").get(0).path("quantity").intValue()
    );
}
~~~

Test này xác nhận các tên property sau naming strategy, timestamp format và decimal value. Nếu hợp đồng yêu cầu một field không được xuất hiện, hãy assert nó không có mặt.

### 6.1. So sánh JsonNode thay vì so sánh JSON String nguyên văn

Không nên luôn dùng:

~~~java
assertEquals(expectedJson, actualJson);
~~~

JSON object không phụ thuộc thứ tự property và whitespace. Hai chuỗi có thể khác nhau nhưng cùng cấu trúc và giá trị.

Cách tốt hơn là parse cả expected và actual thành JsonNode:

~~~java
JsonNode expected = mapper.readTree(expectedJson);
JsonNode actual = mapper.readTree(actualJson);

assertEquals(expected, actual);
~~~

JsonNode equality kiểm tra cấu trúc và giá trị theo mô hình Jackson. Với JSON object, thứ tự property không cần giống nhau; với array, thứ tự phần tử vẫn có ý nghĩa.

So sánh chuỗi chỉ phù hợp khi byte-level representation là một phần hợp đồng, ví dụ chữ ký số trên raw JSON, canonical JSON hoặc payload phải khớp chính xác định dạng đã công bố.

### 6.2. Assert các field bắt buộc và field không được phát ra

Ngoài so sánh toàn tree, có thể kiểm tra trực tiếp:

~~~java
assertTrue(actual.has("event_id"));
assertFalse(actual.has("internal_note"));
assertTrue(actual.path("order").path("items").isArray());
~~~

Điều này hữu ích khi test muốn diễn đạt rõ một quy tắc bảo mật hoặc schema. Không nên chỉ assert một vài field rồi bỏ qua toàn bộ cấu trúc nếu payload có nhiều field quan trọng.

## 7. Kiểm thử bên nhận: fixture độc lập phải deserialize đúng

Consumer test nên đọc fixture JSON độc lập, không tạo JSON bằng DTO sender trong cùng test.

Ví dụ file fixture:

~~~json
{
  "event_id": "evt-1001",
  "event_type": "order-created",
  "occurred_at": "2026-11-12T08:30:00Z",
  "order": {
    "order_id": "ORD-9001",
    "total": 125000.50,
    "currency": "VND",
    "items": [
      {
        "sku": "SKU-01",
        "quantity": 2
      }
    ]
  }
}
~~~

Test:

~~~java
@Test
void receiverReadsPublishedOrderCreatedFixture() throws Exception {
    String json = readFixture("contracts/order-created-v1.json");

    IncomingOrderCreated event = orderReader.readValue(json);

    assertEquals("evt-1001", event.eventId());
    assertEquals("order-created", event.eventType());
    assertEquals(
        Instant.parse("2026-11-12T08:30:00Z"),
        event.occurredAt()
    );
    assertEquals("ORD-9001", event.order().orderId());
    assertEquals(new BigDecimal("125000.50"), event.order().total());
    assertEquals(2, event.order().items().get(0).quantity());
}
~~~

Fixture có thể được tạo từ tài liệu hợp đồng hoặc ví dụ producer đã phát hành, sau đó được giữ cố định trong repository consumer. Nhờ vậy, test không phụ thuộc vào class Java hoặc serializer implementation của sender.

### 7.1. Fixture nên phản ánh payload trên wire

Nếu message broker thêm envelope, header hoặc metadata ngoài JSON body, cần quyết định test đang kiểm tra body hay toàn bộ message. Không trộn metadata vận chuyển vào fixture body nếu receiver không nhận các field đó.

Tương tự, nếu HTTP có content type hoặc version header, có thể kiểm tra chúng trong integration/contract test riêng. JSON fixture chỉ xác nhận phần body.

## 8. Round-trip test có ích nhưng không đủ

Round-trip test thường có dạng:

~~~java
OutgoingOrderCreated source = sampleEvent();

String json = mapper.writeValueAsString(source);

IncomingOrderCreated restored =
    mapper.readValue(json, IncomingOrderCreated.class);

assertEquals(expected, restored);
~~~

Test này có thể hữu ích, nhưng có giới hạn:

- Sender và receiver có thể dùng cùng naming strategy sai.
- Serializer và deserializer có thể cùng hiểu nhầm một field.
- Cả hai phía có thể cùng thay đổi theo một schema mới không tương thích với consumer cũ.
- Một field bị bỏ khỏi output và cũng không được kiểm tra ở input.
- JSON thực tế mà service khác gửi có thể khác payload do test tạo.

Vì vậy, hãy dùng ba lớp test:

1. Sender test: DTO sender → JSON → assert hợp đồng.
2. Receiver test: fixture JSON độc lập → DTO receiver → assert semantics.
3. Compatibility test: JSON do phiên bản producer đã phát hành tạo ra → consumer phiên bản hiện tại đọc được.

Round-trip có thể bổ sung để kiểm tra các mapping hai chiều, nhưng không thay thế fixture và test độc lập.

## 9. Thiết kế fixture cho missing, null và empty

Một trong những nguồn lỗi phổ biến là nhầm field không xuất hiện với field có null hoặc giá trị rỗng.

Giả sử payload có field note tùy chọn:

~~~json
{
  "order_id": "ORD-9001",
  "note": null,
  "tags": []
}
~~~

Các trạng thái khác nhau:

| JSON | Ý nghĩa có thể có |
|---|---|
| Không có note | Producer không cung cấp note |
| "note": null | Producer cung cấp explicit null |
| "note": "" | Note là chuỗi rỗng |
| "tags": [] | Có danh sách tags nhưng không có phần tử |
| "metadata": {} | Có object metadata rỗng |

Tùy hợp đồng, missing và null có thể mang semantics khác nhau, đặc biệt với PATCH hoặc event update.

Tạo fixture riêng:

~~~text
order-no-note-v1.json
order-null-note-v1.json
order-empty-note-v1.json
order-empty-tags-v1.json
~~~

Test receiver:

~~~java
@Test
void distinguishesMissingAndExplicitNull() throws Exception {
    JsonNode missing = mapper.readTree(
        readFixture("contracts/order-no-note-v1.json")
    );

    JsonNode explicitNull = mapper.readTree(
        readFixture("contracts/order-null-note-v1.json")
    );

    assertFalse(missing.has("note"));
    assertTrue(explicitNull.has("note"));
    assertTrue(explicitNull.path("note").isNull());
}
~~~

Nếu DTO Java không giữ được sự khác biệt này, hãy dùng JsonNode, presence wrapper hoặc custom deserializer theo yêu cầu. Test cần xác nhận semantics mà service thực sự sử dụng, không chỉ xác nhận deserialize thành công.

## 10. Dữ liệu mẫu cho số và precision

Các field số cần fixture boundary thay vì chỉ dùng số tròn dễ dàng.

Ví dụ amount:

~~~json
{
  "amount": 0.10,
  "quantity": 2147483647
}
~~~

Các trường hợp cần test:

- Số nguyên ở min/max của target type.
- Giá trị ngay ngoài range.
- Decimal có trailing zero như 0.10.
- Decimal vượt scale được phép.
- Exponent notation nếu hợp đồng cho phép.
- Số nguyên lớn hơn 2^53 - 1 nếu client JavaScript tham gia.
- Số âm nếu domain cho phép.
- Zero và negative zero nếu có ý nghĩa với hệ thống.

Dùng BigDecimal trong DTO khi cần giữ decimal chính xác:

~~~java
public record PaymentAmount(BigDecimal amount) {}
~~~

Đừng dùng double cho tiền chỉ vì JSON number có thể đọc vào double. Fixture nên assert decimal value và scale nếu scale là một phần của contract.

Với integer field, test cả JSON number và string chứa số nếu policy phải từ chối string coercion. Một test chỉ có giá trị hợp lệ không chứng minh consumer từ chối payload sai kiểu.

## 11. Dữ liệu mẫu cho ngày giờ và timezone

Ngày giờ thường bị lệch do format và timezone. Hợp đồng phải quy định:

- Field là date hay timestamp.
- Timestamp có offset/timezone hay không.
- Có chuẩn hóa về UTC hay giữ offset gốc.
- Precision đến giây, mili giây hay nano giây.
- Có chấp nhận timestamp dạng number không.
- Có chấp nhận local date-time không có timezone không.

Ví dụ:

~~~json
{
  "created_at": "2026-11-12T08:30:00Z",
  "business_date": "2026-11-12"
}
~~~

Fixture nên có ít nhất:

- UTC timestamp.
- Timestamp có offset khác UTC nếu contract cho phép.
- Ngày ở ranh giới tháng/năm.
- Leap day nếu field là date.
- Giá trị sai format.
- Timestamp thiếu timezone nếu hợp đồng yêu cầu offset.

Test:

~~~java
assertEquals(
    Instant.parse("2026-11-12T08:30:00Z"),
    event.createdAt()
);
~~~

Dùng Instant cho thời điểm tuyệt đối, OffsetDateTime nếu cần giữ offset, LocalDate cho ngày lịch không gắn thời điểm. Không chuyển local date thành Instant nếu hợp đồng chưa định nghĩa timezone.

## 12. Enum và giá trị chưa biết

Enum Java thường có danh sách giá trị hữu hạn:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Fixture hợp lệ:

~~~json
{
  "status": "PAID"
}
~~~

Khi producer thêm trạng thái REFUNDED, consumer cũ có thể không deserialize được nếu enum strict. Hãy chọn chính sách:

- Từ chối enum chưa biết.
- Map về UNKNOWN nếu domain có giá trị fallback.
- Giữ raw string để forward hoặc log có kiểm soát.
- Dùng custom deserializer nếu có alias hoặc mã legacy.

Nếu dùng @JsonValue để enum xuất mã riêng, fixture phải chứa mã JSON thực tế, không nhất thiết là tên constant Java.

Test cần có cả giá trị đã biết và chưa biết:

~~~java
@Test
void rejectsUnknownStatusWhenContractIsStrict() {
    assertThrows(JsonProcessingException.class, () ->
        mapper.readValue(
            "{\"status\":\"REFUNDED\"}",
            OrderStatusRequest.class
        )
    );
}
~~~

Nếu contract cho phép UNKNOWN, test phải xác nhận fallback đúng và service không thực hiện hành động nguy hiểm do một trạng thái chưa hiểu.

## 13. Polymorphism và discriminator trong fixture

Nếu cùng một field có nhiều subtype, fixture phải có một payload cho từng loại.

~~~json
{
  "event_type": "order-created",
  "event_id": "evt-1",
  "order_id": "ORD-1"
}
~~~

~~~json
{
  "event_type": "order-cancelled",
  "event_id": "evt-2",
  "order_id": "ORD-2",
  "reason": "CUSTOMER_REQUEST"
}
~~~

Test receiver:

~~~java
OrderEvent event = mapper.readValue(json, OrderEvent.class);

assertInstanceOf(OrderCreatedEvent.class, event);
~~~

Và test riêng cho từng subtype. Bổ sung fixture cho:

- Discriminator bị thiếu.
- Discriminator null.
- Discriminator không biết.
- Discriminator có kiểu sai.
- Payload thiếu field bắt buộc của subtype.
- Field riêng của subtype có kiểu sai.

Dùng logical type id ổn định như order-created thay vì tên package/class Java. Fixture giúp bảo vệ mã type id như một phần hợp đồng công khai.

## 14. Unknown property và schema evolution

Khi producer thêm field mới, consumer cũ có thể gặp property chưa biết. Chính sách phụ thuộc cấu hình Jackson và yêu cầu tích hợp.

Nếu consumer cần tolerant với field bổ sung, có thể cấu hình:

~~~java
ObjectMapper tolerantMapper = JsonMapper.builder()
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Nếu consumer cần strict để phát hiện producer gửi sai schema, giữ chế độ fail hoặc dùng schema validation riêng.

Không có một chính sách đúng cho mọi service:

| Tình huống | Chính sách có thể phù hợp |
|---|---|
| Event forward-compatible, field mới không ảnh hưởng | Tolerant với unknown field |
| Lệnh tài chính hoặc workflow action | Strict hơn để tránh bỏ sót semantics |
| Consumer lưu và forward payload | Giữ unknown fields bằng JsonNode/extension map |
| DTO nội bộ có schema cố định | Strict để phát hiện drift |
| Public API có version rõ | Tùy version và quy tắc compatibility |

Fixture unknown-field nên xác nhận hành vi mong muốn. Nếu consumer bỏ qua field mới, test cần chứng minh field cũ vẫn đọc đúng. Nếu consumer giữ extension data, test cần assert dữ liệu không bị mất.

Đừng tắt FAIL_ON_UNKNOWN_PROPERTIES toàn cục chỉ để một fixture qua test. Hãy cấu hình theo ranh giới contract và lý do tương thích.

## 15. Kiểm tra cấu trúc bằng JsonNode

JsonNode phù hợp để assert JSON contract mà không phụ thuộc DTO implementation.

Ví dụ helper đọc fixture:

~~~java
static JsonNode readJson(ObjectMapper mapper, String json)
        throws JsonProcessingException {
    return mapper.readTree(json);
}
~~~

So sánh toàn cấu trúc:

~~~java
JsonNode expected = mapper.readTree(expectedJson);
JsonNode actual = mapper.readTree(actualJson);

assertEquals(expected, actual);
~~~

Kiểm tra field:

~~~java
assertTrue(actual.path("order").isObject());
assertTrue(actual.path("order").path("items").isArray());
assertTrue(actual.path("order").path("total").isNumber());
~~~

Kiểm tra field không được phát ra:

~~~java
assertFalse(actual.has("password"));
assertFalse(actual.path("order").has("internal_cost"));
~~~

Kiểm tra missing và null:

~~~java
assertFalse(actual.has("note"));
assertTrue(actual.has("optional_code"));
assertTrue(actual.path("optional_code").isNull());
~~~

JsonNode assertion giúp test tập trung vào JSON contract, còn assertion trên DTO giúp test semantics mà receiver sử dụng. Hai kiểu kiểm tra bổ sung cho nhau.

## 16. Kiểm tra lỗi bằng fixture không hợp lệ

Fixture lỗi giúp xác định payload nào phải bị từ chối. Có thể lưu riêng:

~~~text
contracts/invalid/
    quantity-as-string.json
    amount-overflow.json
    timestamp-without-offset.json
    unknown-event-type.json
    malformed-json.json
~~~

Ví dụ test sai kiểu:

~~~java
@Test
void rejectsStringQuantityWhenIntegerTokenIsRequired() {
    String json = """
        {
          "quantity": "two"
        }
        """;

    assertThrows(JsonProcessingException.class, () ->
        strictMapper.readValue(json, IncomingItem.class)
    );
}
~~~

Test overflow:

~~~java
@Test
void rejectsQuantityOutsideIntegerRange() {
    String json = """
        {
          "quantity": 2147483648
        }
        """;

    assertThrows(JsonProcessingException.class, () ->
        strictMapper.readValue(json, IncomingItem.class)
    );
}
~~~

Test malformed JSON:

~~~java
@Test
void rejectsTruncatedPayload() {
    String json = """
        {
          "event_id": "evt-1",
          "order": {
            "order_id": "ORD-1"
        """;

    assertThrows(JsonProcessingException.class, () ->
        mapper.readValue(json, IncomingOrderCreated.class)
    );
}
~~~

Không cần assert exact message của Jackson nếu message có thể thay đổi theo version. Assert exception category hoặc map lỗi thành application error ổn định.

## 17. Cấu trúc thư mục fixture và test

Một cách tổ chức:

~~~text
src/test/
  java/
    com/example/contracts/
      SenderContractTest.java
      ReceiverContractTest.java
      ContractFixtureSupport.java
      OrderContractTest.java
  resources/
    contracts/
      order/
        v1/
          order-created.json
          order-created-no-note.json
          order-created-null-note.json
          order-created-empty-items.json
          order-cancelled.json
        invalid/
          quantity-as-string.json
          quantity-overflow.json
          unknown-event-type.json
~~~

Trong repository có nhiều producer/consumer, có thể đặt fixture ở một thư mục hợp đồng dùng chung hoặc một module contract artifact. Tuy nhiên, consumer test vẫn nên lấy fixture như một tài liệu độc lập, không generate fixture trong lúc test từ chính DTO producer đang được kiểm tra.

### 17.1. Helper đọc fixture

~~~java
static String readFixture(String resourcePath) throws IOException {
    try (InputStream input =
             ContractFixtureSupport.class.getResourceAsStream(
                 "/" + resourcePath
             )) {

        if (input == null) {
            throw new FileNotFoundException(resourcePath);
        }

        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Với Java version chưa có InputStream.readAllBytes(), dùng ByteArrayOutputStream hoặc thư viện phù hợp. Helper nên báo rõ tên fixture khi không tìm thấy.

### 17.2. Tránh helper che giấu mục tiêu test

Helper có thể giảm boilerplate, nhưng tên test vẫn cần thể hiện contract nào đang được bảo vệ. Không nên tạo một framework test quá phức tạp khiến người đọc không biết fixture nào được deserialize và assertion nào được thực hiện.

## 18. Consumer-driven contract và provider verification

Với hệ thống nhiều service, consumer-driven contract testing có thể bổ sung cho fixture test Jackson.

Ý tưởng:

1. Consumer mô tả request/response hoặc message mà nó cần.
2. Provider xác minh rằng implementation thực tế đáp ứng các expectation đó.
3. Contract được version hóa và chạy trong CI trước khi deploy.

Công cụ như Pact có thể quản lý contract giữa consumer và provider qua HTTP hoặc message interaction. Jackson fixture test vẫn hữu ích để kiểm tra serialization/deserialization ở cấp JSON; contract testing ở cấp service còn xác nhận endpoint, status code, header, routing hoặc message envelope.

Hai lớp không thay thế nhau:

| Loại test | Điều nó xác nhận |
|---|---|
| Jackson serialization test | DTO sender tạo đúng JSON |
| Jackson deserialization test | DTO receiver đọc đúng JSON |
| Fixture compatibility test | Payload phiên bản trước vẫn được hiểu |
| JSON Schema validation | Payload phù hợp schema đã công bố |
| Consumer-driven contract | Provider đáp ứng nhu cầu thực tế của consumer |
| End-to-end integration test | Các thành phần phối hợp qua hạ tầng thật hoặc gần thật |

Không cần đưa Pact vào mọi module. Nếu chỉ có một service và một contract nhỏ, fixture test có thể đủ. Khi nhiều team phát hành độc lập, contract verification giúp phát hiện breaking change sớm hơn.

## 19. JSON Schema và kiểm thử hợp đồng

JSON Schema có thể mô tả cấu trúc JSON độc lập với Java:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "occurred_at", "order"],
  "properties": {
    "event_id": {
      "type": "string"
    },
    "event_type": {
      "const": "order-created"
    },
    "occurred_at": {
      "type": "string",
      "format": "date-time"
    },
    "order": {
      "type": "object",
      "required": ["order_id", "total", "currency", "items"],
      "properties": {
        "order_id": {"type": "string"},
        "total": {"type": "number", "minimum": 0},
        "currency": {"type": "string", "minLength": 3, "maxLength": 3},
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["sku", "quantity"],
            "properties": {
              "sku": {"type": "string"},
              "quantity": {"type": "integer", "minimum": 1}
            }
          }
        }
      }
    }
  }
}
~~~

Schema có thể được dùng để validate cả output sender và input fixture. Tuy nhiên, JSON Schema format/date-time validation phụ thuộc validator và cấu hình; không phải mọi validator đều tự động kiểm tra format nếu chưa bật format assertion.

Schema cũng không thay thế test semantics Java. Ví dụ, schema có thể xác nhận total là number, nhưng không biết service có dùng BigDecimal thay double để giữ chính xác hay không.

Nếu dùng schema:

- Lưu schema theo version.
- Validate fixture và producer output.
- Xác định additionalProperties true/false.
- Quy định required, nullable và default rõ ràng.
- Test các ràng buộc nghiệp vụ mà schema không thể diễn tả.
- Đồng bộ schema với DTO/mapper bằng test thay vì giả định chúng luôn khớp.

## 20. Compatibility matrix giữa phiên bản producer và consumer

Khi service phát hành độc lập, cần biết phiên bản nào phải tương thích với phiên bản nào.

Ví dụ:

| Producer payload | Consumer v1 | Consumer v2 |
|---|---|---|
| Producer v1 | Phải đọc được | Phải đọc được nếu hỗ trợ lịch sử |
| Producer v2 | Tùy chính sách backward compatibility | Phải đọc được |
| Producer v3 | Có thể cần version mới | Theo chính sách hỗ trợ |

Một thay đổi có thể được phân loại:

| Thay đổi JSON | Rủi ro thường gặp |
|---|---|
| Thêm optional field | Thường tương thích nếu consumer bỏ qua unknown field |
| Thêm required field | Có thể phá producer/consumer cũ |
| Đổi tên field | Breaking change nếu không giữ alias |
| Đổi number thành string | Thay đổi JSON type, thường breaking |
| Đổi enum code | Consumer cũ có thể từ chối |
| Đổi timestamp format/timezone semantics | Có thể thay đổi thời điểm được hiểu |
| Xóa field | Consumer đang phụ thuộc field sẽ lỗi |
| Đổi discriminator | Consumer có thể không nhận subtype |
| Thay null bằng missing | Có thể thay đổi PATCH/event semantics |

Không đánh giá compatibility chỉ dựa vào việc DTO compile. Hãy kiểm tra payload fixture của phiên bản cũ với consumer mới và payload producer mới với consumer đang được hỗ trợ.

### 20.1. Giữ fixture cũ như regression contract

Khi v2 được phát hành, không nên xóa fixture v1 nếu consumer vẫn cần đọc message cũ trong queue hoặc archive.

Ví dụ:

~~~text
contracts/
  order/
    v1/
      order-created.json
    v2/
      order-created.json
~~~

Consumer có thể test cả hai fixture. Nếu ngừng hỗ trợ v1, hãy xóa theo quyết định versioning có chủ đích và cập nhật danh sách phiên bản được hỗ trợ.

## 21. Alias tên property và migration

Khi đổi tên property, có thể cần hỗ trợ tên cũ trong giai đoạn chuyển đổi.

Ví dụ receiver:

~~~java
public record IncomingOrder(
    @JsonAlias("orderNumber")
    String orderId
) {}
~~~

JsonAlias cho phép nhận thêm tên cũ khi deserialize; tên serialize vẫn theo property chính, ví dụ orderId hoặc tên sau naming strategy.

Có thể test cả hai fixture:

~~~java
@Test
void acceptsLegacyPropertyName() throws Exception {
    IncomingOrder order = mapper.readValue(
        "{\"orderNumber\":\"ORD-1\"}",
        IncomingOrder.class
    );

    assertEquals("ORD-1", order.orderId());
}
~~~

Alias là công cụ migration. Không nên giữ vô hạn nhiều alias không còn dùng; chúng làm schema khó hiểu và có thể che giấu producer chưa nâng cấp.

Nếu cần gửi cả tên cũ và mới trong một giai đoạn, hãy quy định rõ phía nào phát tên nào và thời điểm loại bỏ alias.

## 22. Test tại ranh giới HTTP hoặc message broker

Jackson unit test xác nhận body mapping. Nhưng khi payload được gửi qua HTTP hoặc broker, còn có metadata vận chuyển:

- Content-Type và charset.
- HTTP status code.
- Header version hoặc correlation ID.
- Message key và partition.
- Content encoding.
- Retry/dead-letter behavior.
- Envelope và routing key.

Ví dụ với Spring MVC, có thể dùng MockMvc để gửi JSON fixture tới endpoint và xác nhận status/body. Với WebClient hoặc message listener, có thể kiểm tra adapter ở mức integration.

Không đưa mọi vấn đề vận chuyển vào Jackson unit test. Giữ test theo từng lớp:

~~~text
Jackson unit test
    - JSON shape
    - type binding
    - null/coercion
          |
          v
Adapter contract test
    - HTTP headers/status
    - message envelope
    - routing
          |
          v
Integration test
    - broker/server
    - retry
    - end-to-end flow
~~~

Nếu receiver dùng @RequestBody, hãy test đúng ObjectMapper/HttpMessageConverter mà Spring cấu hình. Nếu test trực tiếp mapper nhưng production converter dùng cấu hình khác, có thể bỏ sót khác biệt.

## 23. Kiểm thử producer và consumer trong hai repository

Khi producer và consumer nằm ở hai repository khác nhau, có thể chia sẻ contract fixtures qua một trong các cách:

- Một repository contract riêng chứa JSON fixtures và schema.
- Một package/module versioned được publish nội bộ.
- Git submodule hoặc cơ chế đồng bộ có kiểm soát.
- Copy fixture có nguồn/version rõ ràng vào repository consumer.

Không nên để consumer tự generate fixture bằng producer library ở thời điểm chạy test nếu mục tiêu là kiểm tra độc lập. Khi producer library thay đổi, fixture sẽ thay đổi theo và có thể che mất breaking change.

Một quy trình phù hợp:

1. Producer thay đổi DTO/serializer.
2. Sender contract test tạo JSON output và so với fixture/schema.
3. Fixture mới được review như thay đổi hợp đồng.
4. Consumer chạy test với fixture mới và fixture cũ còn được hỗ trợ.
5. CI kiểm tra compatibility trước khi phát hành.
6. Khi deploy, theo dõi lỗi deserialize và version thực tế của payload.

Nếu có nhiều consumer, cần xác định ai chịu trách nhiệm duyệt thay đổi schema và ai xác nhận backward compatibility.

## 24. Đặt tên và quản lý dữ liệu mẫu

Một fixture nên có tên và ngữ cảnh đủ rõ để người khác biết tại sao nó tồn tại.

Ví dụ:

| Tên fixture | Ý nghĩa |
|---|---|
| order-created-v1.json | Payload hợp lệ chuẩn của v1 |
| order-created-no-note-v1.json | Optional note bị thiếu |
| order-created-null-note-v1.json | Note explicit null |
| order-created-empty-items-v1.json | Danh sách items rỗng |
| order-created-large-total-v1.json | Decimal ở biên lớn |
| order-created-unknown-field-v1.json | Consumer nhận field mới |
| order-cancelled-v1.json | Subtype cancelled |
| invalid-quantity-string.json | Sai JSON type |
| invalid-quantity-overflow.json | Vượt miền int |
| invalid-timestamp.json | Sai date-time format |

Có thể thêm file README nhỏ trong thư mục contracts giải thích version, owner và nguồn gốc fixture. Tuy nhiên, fixture JSON nên tự chứa và không phụ thuộc file khác để parse.

Không đặt tên fixture theo implementation như mapper-test-3.json. Tên nên mô tả hành vi hợp đồng.

## 25. Bộ test mẫu tổng hợp

Một lớp test có thể tách rõ sender và receiver:

~~~java
class OrderContractTest {

    private final ObjectMapper mapper = ContractJackson.createMapper();

    @Test
    void senderOutputMatchesPublishedFixture() throws Exception {
        OutgoingOrderCreated event = sampleOutgoingEvent();

        String actualJson = mapper
            .writerFor(OutgoingOrderCreated.class)
            .writeValueAsString(event);

        JsonNode expected = mapper.readTree(
            readFixture("contracts/order/v1/order-created.json")
        );

        JsonNode actual = mapper.readTree(actualJson);

        assertEquals(expected, actual);
    }

    @Test
    void receiverReadsPublishedFixture() throws Exception {
        String json = readFixture(
            "contracts/order/v1/order-created.json"
        );

        IncomingOrderCreated event = mapper.readValue(
            json,
            IncomingOrderCreated.class
        );

        assertEquals("evt-1001", event.eventId());
        assertEquals("ORD-9001", event.order().orderId());
        assertEquals(
            new BigDecimal("125000.50"),
            event.order().total()
        );
    }

    @Test
    void receiverRejectsInvalidQuantityType() {
        String json = """
            {
              "order_id": "ORD-9001",
              "quantity": "two"
            }
            """;

        assertThrows(JsonProcessingException.class, () ->
            mapper.readValue(json, IncomingItem.class)
        );
    }
}
~~~

Trong dự án thực tế, sender và receiver có thể nằm ở hai module riêng nên không cần đặt cả hai test trong cùng class. Ví dụ trên chỉ thể hiện cách tổ chức logic.

### 25.1. Test fixture không bị vô tình ghi đè

Nếu test tạo expected JSON từ cùng object đang serialize, nó không còn là fixture độc lập. Giữ expected payload dưới dạng file hoặc literal được review và chỉ cập nhật khi hợp đồng thay đổi có chủ đích.

Không tự động ghi đè fixture expected khi test fail. Hãy đọc diff, xác định thay đổi có phải breaking change không, rồi mới cập nhật.

## 26. Kiểm thử với cấu hình mapper production

Một lỗi thường gặp là test tạo ObjectMapper mới:

~~~java
ObjectMapper mapper = new ObjectMapper();
~~~

trong khi production dùng mapper đã đăng ký JavaTimeModule, custom serializer, naming strategy hoặc coercion policy.

Khi đó:

- Test có thể fail dù production chạy được.
- Test có thể pass nhưng production fail.
- Timestamp và enum representation có thể khác.
- Unknown property và null handling có thể khác.
- Custom module không được kích hoạt trong test.

Hãy dùng cùng một factory/configuration method hoặc inject ObjectMapper/ObjectReader/ObjectWriter được cấu hình bởi ứng dụng.

Nếu sender và receiver có mapper policy khác nhau, đó là điều bình thường; mỗi phía phải test bằng cấu hình thực tế của chính nó. Không ép hai mapper giống hệt nhau nếu hợp đồng chỉ yêu cầu JSON tương thích.

## 27. Tách schema test khỏi business validation test

Một payload có thể hợp lệ về JSON schema nhưng sai nghiệp vụ.

Ví dụ:

~~~json
{
  "quantity": 2,
  "unit_price": 100,
  "total": 999999
}
~~~

Tất cả field có thể đúng kiểu và nằm trong range, nhưng total không bằng quantity nhân unit_price.

Nên tách:

- Serialization contract: sender phát đúng tên/kiểu/shape.
- Deserialization contract: receiver bind đúng field.
- Structural validation: required, type, format, range.
- Business validation: tổng tiền, trạng thái chuyển tiếp, quyền sở hữu.
- Integration behavior: transaction, retry, persistence.

Nếu gộp tất cả vào một test lớn, lỗi khó xác định đến từ JSON mapping hay nghiệp vụ.

## 28. Những lỗi thường gặp khi thiết kế contract test

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ test round-trip cùng mapper | Serializer/deserializer cùng sai vẫn pass | Test sender và receiver độc lập |
| Generate fixture từ DTO producer trong mỗi test | Fixture thay đổi theo implementation | Giữ JSON fixture cố định và review |
| So sánh JSON String nguyên văn | Fail vì whitespace/property order | Parse thành JsonNode rồi so sánh |
| Chỉ dùng một happy-path fixture | Không phát hiện null, missing, boundary và invalid shape | Tạo fixture theo từng semantics |
| Dùng mapper mặc định trong test | Khác production configuration | Tái sử dụng mapper factory production |
| Chia sẻ DTO Java giữa mọi service | Refactor nội bộ có thể kéo theo contract | Tách contract DTO hoặc kiểm tra wire JSON |
| Bỏ qua unknown property policy | Producer thêm field có thể phá consumer | Test tolerant/strict policy có chủ đích |
| Không giữ fixture cũ | Mất kiểm tra backward compatibility | Giữ payload theo version còn hỗ trợ |
| Assert chỉ vài field | Field nhạy cảm hoặc sai shape lọt qua | So sánh toàn tree và assert field cấm |
| Dùng dữ liệu production trong fixture | Rò rỉ PII hoặc bí mật | Dùng synthetic data |
| Không test kiểu số và ngày giờ | Mất precision hoặc lệch timezone | Fixture boundary và format |
| Không test subtype | Discriminator mới làm consumer lỗi | Một fixture cho mỗi subtype và unknown type |
| Tự cập nhật expected khi test fail | Breaking change bị hợp thức hóa | Review diff và quyết định versioning |
| Chỉ test mapper, không test adapter | Sai header/envelope/routing không được phát hiện | Thêm adapter contract test |

## 29. Quy trình xây dựng và duy trì bộ contract test

1. Xác định producer, consumer, transport và JSON body nào thuộc hợp đồng.
2. Liệt kê field, JSON type, required/optional, nullability, format và range.
3. Tạo DTO contract riêng nếu domain model thay đổi độc lập với wire schema.
4. Tạo fixture synthetic cho happy path, optional/null/empty, boundary, subtype và lỗi.
5. Lưu fixture theo tên mô tả và version.
6. Dùng đúng ObjectMapper/ObjectWriter của sender để test JSON output.
7. So sánh output với fixture/schema bằng JsonNode hoặc validator phù hợp.
8. Dùng fixture độc lập với ObjectReader/mapper của receiver.
9. Assert cả DTO semantics và các field quan trọng trong JSON.
10. Test coercion, unknown property, enum, date/time, number precision và polymorphism.
11. Giữ fixture phiên bản cũ trong khi consumer còn hỗ trợ.
12. Chạy compatibility test trong CI khi DTO, annotation, mapper config hoặc schema thay đổi.
13. Review mọi diff fixture như một thay đổi API/message contract.
14. Bổ sung adapter/integration test cho HTTP header, broker envelope và routing khi cần.
15. Không cập nhật fixture chỉ để làm test xanh; phải xác định thay đổi có được chấp thuận hay không.

## 30. Nguyên tắc nên giữ

- Hợp đồng nằm ở JSON payload và semantics, không nhất thiết ở class Java dùng chung.
- Dữ liệu mẫu phải độc lập với implementation đang được kiểm tra.
- Mỗi fixture nên bảo vệ một tình huống cụ thể.
- Dùng dữ liệu tổng hợp, không đưa PII hoặc secret vào repository.
- Test sender output và receiver input riêng biệt.
- Round-trip chỉ là test bổ sung, không thay thế fixture độc lập.
- So sánh JsonNode để tránh phụ thuộc whitespace và thứ tự object property.
- Dùng mapper configuration giống production ở từng phía.
- Test missing, explicit null, empty, boundary và invalid shape.
- Giữ fixture theo version để bảo vệ backward compatibility.
- Quy định rõ unknown property, enum và subtype mới.
- Phân biệt JSON binding với schema validation và business validation.
- Kiểm tra cả transport metadata khi nó là một phần hợp đồng.
- Review fixture diff như review thay đổi API.
- Không tự động cập nhật expected payload khi test fail.

Thiết kế dữ liệu mẫu và kiểm thử hợp đồng giúp sender và receiver phối hợp ổn định dù chúng có DTO, mapper hoặc ngôn ngữ khác nhau. Fixture JSON độc lập cho biết payload thực sự phải trông như thế nào; sender test xác nhận output; receiver test xác nhận input; compatibility test bảo vệ các phiên bản đang được hỗ trợ. Khi dữ liệu mẫu bao phủ cả happy path, missing/null, boundary, format và lỗi, thay đổi trong Jackson configuration hoặc DTO sẽ được phát hiện trước khi đi vào môi trường tích hợp.

