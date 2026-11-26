# Test event contract

Application event là một hợp đồng giao tiếp giữa module phát và module nhận. Hợp đồng này mô tả sự kiện nghiệp vụ nào đã xảy ra, dữ liệu nào được công bố, ý nghĩa của từng trường và cách consumer phải diễn giải dữ liệu đó. Nếu producer đổi tên field, thay đổi ý nghĩa event hoặc xóa enum value mà không kiểm tra consumer, các module có thể vẫn biên dịch nhưng lỗi khi chạy hoặc xử lý sai nghiệp vụ.

**Test event contract** là nhóm kiểm thử xác minh hợp đồng event được giữ ổn định qua producer, consumer, serialization và các phiên bản ứng dụng. Trong Spring Modulith, kiểm thử cần bảo vệ cả ý nghĩa event, ranh giới module và cách event được công bố tới listener. Khi event được externalize, contract còn bao gồm wire format mà broker và consumer bên ngoài sử dụng.

## 1. Event contract bao gồm những gì?

Một event contract không chỉ là chữ ký Java của một class. Nó bao gồm:

- **Event semantics:** event mô tả sự kiện đã xảy ra, không phải yêu cầu chưa được thực hiện.
- **Identity:** event ID hoặc định danh tương đương để liên kết retry, replay và audit.
- **Payload schema:** field, kiểu dữ liệu, nullability, format và ý nghĩa nghiệp vụ.
- **Time semantics:** thời điểm xảy ra, timezone và độ chính xác timestamp.
- **Versioning:** cách consumer nhận biết và đọc các phiên bản schema.
- **Compatibility:** producer và consumer khác phiên bản có thể trao đổi dữ liệu như thế nào.
- **Delivery expectations:** thời điểm phát, khả năng giao lại, ordering và idempotency.
- **Security boundary:** dữ liệu nào được phép công bố và ai được quyền nhận.

Ví dụ, `OrderPlaced` nên có nghĩa đơn hàng đã được tạo và transaction nguồn đã commit theo quy ước của hệ thống. `PlaceOrder` lại là command yêu cầu tạo đơn. Đặt tên event như thể kết quả đã xảy ra giúp consumer hiểu đúng trạng thái mà event cam kết.

| Thành phần | Câu hỏi kiểm thử |
|---|---|
| Tên và semantics | Event có mô tả đúng một sự kiện nghiệp vụ đã xảy ra không? |
| Field bắt buộc | Consumer có nhận đủ dữ liệu cần thiết không? |
| Field tùy chọn | Giá trị thiếu/null/default có ý nghĩa rõ không? |
| Identity | Retry có giữ nguyên event ID không? |
| Version | Consumer có nhận diện và xử lý version không hỗ trợ không? |
| Serialization | Payload serialize/deserialize có bảo toàn dữ liệu không? |
| Module API | Consumer chỉ phụ thuộc contract được công bố không? |
| Delivery | Event được phát đúng transaction phase và có thể phục hồi không? |

## 2. Phân biệt contract nội bộ và wire contract

Trong Spring Modulith, một application event có thể chỉ được truyền giữa các module trong cùng JVM. Khi đó, listener nhận object Java và không nhất thiết có serialization. Nếu event được lưu trong Event Publication Registry hoặc externalize sang Kafka/RabbitMQ, một hoặc nhiều serialization boundary xuất hiện.

Nên phân biệt ba lớp:

1. **Java event API:** class/record mà module phát và listener nội bộ sử dụng.
2. **Persistence representation:** định dạng serializer dùng để lưu và khôi phục publication nếu persistence implementation cần lưu payload.
3. **Wire contract:** bytes, JSON hoặc schema-based message mà broker và consumer bên ngoài trao đổi.

Ba lớp có thể dùng chung DTO, nhưng không mặc định phải giống nhau. Một thay đổi package Java có thể không ảnh hưởng wire contract nếu adapter map sang envelope ổn định; ngược lại, đổi JSON field có thể phá consumer dù class Java vẫn tương thích source.

Kiểm thử phải xác định boundary đang bảo vệ. Unit test class Java không chứng minh JSON schema không đổi; round-trip serialization không chứng minh event được publish sau commit; test broker không chứng minh module consumer không truy cập package nội bộ.

## 3. Thiết kế event contract ổn định

Event nên là dữ liệu bất biến, nhỏ và độc lập với entity/persistence model. Ví dụ:

```java
public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    String orderNumber,
    Instant occurredAt,
    List<OrderLineData> lines
) {}

public record OrderLineData(
    UUID productId,
    int quantity,
    BigDecimal unitPrice
) {}
```

Các trường có ý nghĩa rõ ràng:

- `eventId` định danh một lần phát sinh event và giữ nguyên qua retry/replay.
- `orderId` liên kết event với aggregate nghiệp vụ.
- `occurredAt` là thời điểm sự kiện xảy ra, không phải thời điểm consumer nhận.
- `lines` là snapshot dữ liệu cần cho consumer, không phải JPA entity đang sống.

Nếu event được trao đổi qua nhiều module hoặc service, có thể bổ sung `schemaVersion`, `correlationId`, `causationId` hoặc `tenantId` khi các trường này có semantics và nguồn tin cậy rõ ràng. Không thêm metadata chỉ để làm payload dài hơn hoặc phụ thuộc vào object runtime.

Tránh đưa các kiểu sau vào event contract:

- JPA entity, Hibernate proxy hoặc lazy collection.
- `HttpServletRequest`, `Authentication`, `SecurityContext` hoặc `ThreadLocal`.
- Repository, service, `EntityManager`, stream hoặc file handle.
- Credential, access token, password hoặc dữ liệu cá nhân không cần thiết.
- Exception object hoặc class metadata tùy ý.

## 4. Kiểm thử semantics và field bắt buộc

Kiểm thử producer cần xác minh event được tạo từ trạng thái nghiệp vụ đúng. Ví dụ, sau khi đơn hàng được commit, event phải chứa đúng order ID, tổng tiền/dòng hàng theo contract và thời điểm xảy ra.

```java
@Test
void createsOrderPlacedWithContractFields() {
    var event = orderEventFactory.from(placedOrder);

    assertThat(event.eventId()).isNotNull();
    assertThat(event.orderId()).isEqualTo(placedOrder.id());
    assertThat(event.orderNumber()).isEqualTo(placedOrder.number());
    assertThat(event.occurredAt()).isNotNull();
    assertThat(event.lines()).hasSize(placedOrder.lines().size());
}
```

Đây là unit test cho factory/producer mapping. Trong ứng dụng thực, cần kiểm tra thêm quy tắc làm tròn tiền, currency, timezone, enum, nullability và các field nhạy cảm. Không chỉ kiểm tra field có giá trị; hãy kiểm tra giá trị có đúng ý nghĩa nghiệp vụ.

Một số assertion quan trọng:

- Event type và tên field theo contract đã công bố.
- Field bắt buộc không null hoặc rỗng ngoài quy tắc.
- Collection có giới hạn và không chứa phần tử sai.
- Decimal không bị chuyển qua floating point gây sai số.
- Timestamp giữ đúng instant và timezone semantics.
- Event không chứa entity hoặc thông tin không được phép công bố.

## 5. Kiểm thử serialization round-trip

Round-trip test xác minh object sau khi serialize rồi deserialize vẫn giữ nguyên dữ liệu contract. Với Jackson, có thể dùng mapper được cấu hình giống ứng dụng:

```java
@SpringBootTest
class OrderPlacedSerializationTests {

    @Autowired
    ObjectMapper eventObjectMapper;

    @Test
    void preservesContractWhenSerializedAndReadBack() throws Exception {
        var original = TestEvents.orderPlaced();

        byte[] payload = eventObjectMapper.writeValueAsBytes(original);
        var restored = eventObjectMapper.readValue(payload, OrderPlaced.class);

        assertThat(restored).isEqualTo(original);
    }
}
```

Ví dụ giả định event là Java record và mapper có module phù hợp cho các kiểu dữ liệu như `Instant`. Nếu ứng dụng có serializer riêng cho Event Publication Registry hoặc transport adapter, hãy kiểm thử chính serializer đó; inject một `ObjectMapper` khác không chứng minh integration thực sự dùng cùng cấu hình.

Round-trip test nên bao phủ:

- UUID, decimal, enum, date/time và Unicode.
- Field optional có giá trị và không có giá trị.
- Collection rỗng, một phần tử và kích thước gần giới hạn.
- Giá trị biên như số lượng bằng 0 hoặc giới hạn nghiệp vụ hợp lệ.
- Encoding UTF-8 và content type.
- Không vô tình serialize field nội bộ hoặc dữ liệu nhạy cảm.

Round-trip cùng một version chưa đủ để kiểm tra schema evolution. Cần thêm fixture từ các phiên bản đã phát hành.

## 6. Kiểm thử schema bằng JSON fixture

Với wire contract JSON, có thể lưu payload mẫu trong test source hoặc khai báo inline để kiểm tra consumer đọc được schema đã công bố. Ví dụ payload version 1:

```json
{
  "eventId": "f34b3a4a-9b1f-4c7f-9c8e-7e31a2b7b4e1",
  "eventType": "order.placed",
  "schemaVersion": 1,
  "orderId": "d48a8e64-bad8-4a87-9e7c-5e4b70d0a40f",
  "occurredAt": "2026-11-25T10:15:30Z",
  "currency": "VND",
  "total": "125000.00"
}
```

Consumer contract test có thể xác minh fixture được map về DTO hoặc model nội bộ chính xác. Dùng `JsonNode` hoặc schema validator để kiểm tra field name, kiểu dữ liệu và field bắt buộc mà không phụ thuộc vào thứ tự property trong JSON.

Không so sánh JSON bằng chuỗi tuyệt đối nếu thứ tự field và whitespace không phải một phần của contract. So sánh cấu trúc JSON hoặc deserialize rồi assert semantics. Nếu định dạng canonical JSON hoặc chữ ký số yêu cầu byte representation cụ thể, khi đó mới kiểm tra bytes chính xác.

## 7. Schema evolution và compatibility

Event có thể tồn tại lâu trong publication registry, outbox, broker hoặc dead-letter queue. Consumer phiên bản mới có thể phải đọc event được tạo bởi producer cũ; consumer cũ cũng có thể tiếp tục chạy trong giai đoạn rolling deployment.

Hai khái niệm cần phân biệt:

- **Backward compatibility:** reader/consumer mới có thể đọc dữ liệu được writer/producer cũ tạo ra.
- **Forward compatibility:** reader/consumer cũ có thể đọc dữ liệu do writer/producer mới tạo ra.

Khả năng tương thích thực tế phụ thuộc schema format và cấu hình reader. Ví dụ, thêm field optional có default có thể backward compatible; nhưng consumer Jackson cũ bật strict unknown-property handling có thể từ chối field mới. Do đó, không thể chỉ dựa vào việc field mới có optional hay không.

| Thay đổi | Rủi ro | Kiểm thử cần có |
|---|---|---|
| Thêm field optional | Reader cũ có thể từ chối field lạ | Consumer cũ đọc payload mới |
| Thêm field bắt buộc | Consumer cũ không có giá trị | Compatibility test và migration plan |
| Xóa field | Consumer cũ có thể còn phụ thuộc | Consumer cũ với payload mới |
| Đổi kiểu field | Parse hoặc mapping sai | Fixture cũ/mới và test conversion |
| Đổi ý nghĩa field | Không lỗi parse nhưng sai nghiệp vụ | Semantic contract test |
| Xóa enum value | Payload cũ có thể không deserialize | Fixture chứa enum value cũ |
| Đổi tên event/type | Routing hoặc type resolution hỏng | Test event type và adapter mapping |
| Đổi package class | Type metadata cũ có thể không resolve | Test đọc publication cũ hoặc mapping ổn định |

Nên có `schemaVersion` hoặc versioning mechanism tương đương khi consumer cần chọn mapper khác nhau. Không đổi ý nghĩa field mà vẫn giữ nguyên version. Nếu version không được hỗ trợ, consumer nên từ chối rõ ràng và đưa message vào quy trình lỗi thay vì diễn giải theo schema gần giống.

## 8. Kiểm thử fixture từ các phiên bản cũ

Một bộ fixture tương thích nên giữ các payload đại diện cho những schema version còn được hỗ trợ. Mỗi lần sửa DTO, serializer hoặc dependency, test consumer mới đọc lại toàn bộ fixture.

```java
@Test
void readsPreviouslyPublishedV1Payload() throws Exception {
    String payload = """
        {
          "eventId": "f34b3a4a-9b1f-4c7f-9c8e-7e31a2b7b4e1",
          "eventType": "order.placed",
          "schemaVersion": 1,
          "orderId": "d48a8e64-bad8-4a87-9e7c-5e4b70d0a40f",
          "total": "125000.00"
        }
        """;

    var envelope = eventObjectMapper.readValue(payload, EventEnvelope.class);
    var command = eventDecoder.decode(envelope);

    assertThat(command.total()).isEqualByComparingTo("125000.00");
}
```

`EventEnvelope`, `eventDecoder` và `command` là kiểu/adapter do ứng dụng định nghĩa. Ví dụ minh họa kiểm tra payload cũ qua compatibility mapping; không phải class envelope chuẩn của Spring Modulith.

Fixture nên được quản lý như một phần của contract đã phát hành. Không sửa fixture cũ chỉ để làm test pass khi thay đổi mới làm mất tương thích; nếu phải loại bỏ version cũ, cần có bằng chứng rằng không còn publication/message cần đọc và có migration policy rõ ràng.

## 9. Kiểm thử consumer expectations

Producer có thể phát payload hợp lệ về mặt schema nhưng consumer vẫn diễn giải sai semantics. Vì vậy, consumer test cần kiểm tra điều mà consumer kỳ vọng từ event:

- Event type nào được xử lý.
- Field nào là bắt buộc đối với use case.
- Field optional thiếu được xử lý như thế nào.
- Enum hoặc reason code không nhận biết được phản ứng ra sao.
- Event version mới hơn consumer được hỗ trợ có bị từ chối rõ không.
- Event duplicate hoặc đến sai thứ tự có ảnh hưởng tới state không.
- Consumer không đọc dữ liệu nội bộ ngoài contract của module phát.

Không yêu cầu consumer phụ thuộc mọi field của producer. Contract nên nhỏ và mỗi consumer chỉ dựa vào phần cần thiết. Nếu producer thêm field không liên quan, consumer không nên thất bại khi policy cho phép bỏ qua field mở rộng.

## 10. Kiểm thử event được publish đúng lúc

Event contract còn bao gồm semantics về thời điểm. Với event mô tả thay đổi đã commit, cần kiểm tra event không được xử lý như thành công nếu transaction nguồn rollback.

Một test service có thể gọi phương thức transactional thật và xác minh event được phát sau commit. Với `@TransactionalEventListener`, có thể kiểm tra nhánh commit và rollback riêng. Nếu test method tự mở transaction rồi rollback mặc định, listener `AFTER_COMMIT` có thể không chạy; hãy thiết kế test để commit transaction một cách chủ động khi cần kiểm tra nhánh thành công.

Các tình huống cần kiểm tra:

1. Transaction commit: event được công bố theo contract.
2. Transaction rollback: không có event biểu thị thay đổi đã commit.
3. Listener lỗi sau commit: transaction nguồn vẫn đã commit và publication failure được quan sát riêng.
4. Event được giao lại: consumer không lặp tác động nghiệp vụ.
5. Event có nhiều listener: mỗi listener nhận đúng event theo contract và có trạng thái publication phù hợp.

Không gộp kiểm thử event payload với kiểm thử Event Publication Registry. Một test xác minh payload đúng không chứng minh registry phục hồi publication; một test registry không chứng minh field trong payload mang ý nghĩa đúng.

## 11. Kiểm thử với Spring Modulith `Scenario`

Spring Modulith cung cấp test support để kiểm thử tương tác event giữa các module. `@ApplicationModuleTest` dựng test context theo module được chọn; `Scenario` giúp kích hoạt hành động và chờ event mong đợi mà không cần `Thread.sleep`.

Ví dụ:

```java
@ApplicationModuleTest
class OrdersModuleEventTests {

    @Autowired
    Scenario scenario;

    @Autowired
    OrderManagement orders;

    @Test
    void publishesOrderPlacedWithExpectedIdentity() {
        UUID orderId = UUID.randomUUID();

        scenario.stimulate(() -> orders.placeOrder(orderId))
            .andWaitForEventOfType(OrderPlaced.class)
            .matching(event -> event.orderId().equals(orderId))
            .toArrive();
    }
}
```

Đây là ví dụ theo Scenario API của Spring Modulith; kiểu service, cách tạo đơn và assertion cần khớp với module thực tế. Test xác minh event được công bố và có dữ liệu liên quan đúng. Nếu cần kiểm tra toàn bộ field, hãy lấy event trong assertion hoặc kiểm thử event factory/consumer riêng.

`Scenario` đặc biệt hữu ích cho listener bất đồng bộ vì nó chờ điều kiện event trong thời hạn cấu hình thay vì đoán thời gian bằng sleep. Nó không thay thế kiểm thử serialization hoặc schema fixture.

## 12. Ghi nhận application events trong test

Với test cần quan sát event được phát trong Spring test context, có thể dùng `@RecordApplicationEvents` và `ApplicationEvents` của Spring Test:

```java
@SpringBootTest
@RecordApplicationEvents
class OrderEventPublicationTests {

    @Autowired
    ApplicationEvents applicationEvents;

    @Autowired
    OrderManagement orders;

    @Test
    void publishesOneOrderPlacedEvent() {
        orders.placeOrder(UUID.randomUUID());

        assertThat(applicationEvents.stream(OrderPlaced.class))
            .hasSize(1);
    }
}
```

Ví dụ này minh họa quan sát application event trong test context. Cần bảo đảm event được phát trong phạm vi recording và transaction đã đạt phase mong đợi. Với event async, dùng Scenario hoặc cơ chế chờ có điều kiện phù hợp; không đọc collection ngay lập tức rồi kết luận event không được phát.

## 13. Kiểm thử ranh giới module của event contract

Event contract nên nằm ở package được module công bố. Consumer chỉ nên import API công khai, không truy cập package nội bộ hoặc entity của producer.

Spring Modulith có thể kiểm tra cấu trúc module:

```java
class ModularityTests {

    @Test
    void moduleStructureIsValid() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

Test này kiểm tra quy tắc phụ thuộc module theo cấu trúc Spring Modulith được nhận diện. Nó không tự xác minh event schema hoặc semantics. Nên kết hợp với test contract để phát hiện cả phụ thuộc sai ranh giới lẫn thay đổi payload không tương thích.

Nếu dùng named interface để công bố package contract, hãy xác minh consumer chỉ truy cập package được phép. Không chuyển DTO event vào package implementation chỉ vì tiện tái sử dụng class nội bộ.

## 14. Kiểm thử Event Publication Registry

Event Publication Registry theo dõi publication của application event tới listener được quản lý. Với persistence implementation phù hợp, registry có thể lưu publication và trạng thái hoàn tất để nhận biết publication chưa xử lý xong.

Contract test và registry test có mục tiêu khác nhau:

| Kiểm thử | Điều cần chứng minh |
|---|---|
| Event contract | Tên, field, type, semantics và version đúng |
| Serialization | Payload có thể ghi/đọc theo format đã công bố |
| Publication lifecycle | Publication được ghi nhận và hoàn tất theo listener lifecycle |
| Recovery | Publication incomplete có thể được phục hồi theo API được hỗ trợ |
| Consumer idempotency | Giao lại event không lặp business effect |

Các integration test nên xác minh listener thành công làm publication hoàn tất, listener thất bại không bị đánh dấu hoàn tất nhầm và publication có thể được phục hồi sau restart theo cấu hình. Chi tiết API và persistence behavior phụ thuộc phiên bản Spring Modulith; dùng API công khai tương ứng, không sửa trực tiếp bảng registry.

Registry không phải schema registry và không tự quản lý compatibility giữa version của event. Nó theo dõi publication; contract versioning vẫn là trách nhiệm của ứng dụng hoặc hệ thống schema được tích hợp.

## 15. Kiểm thử externalization và broker contract

Nếu event được gửi ra Kafka hoặc RabbitMQ, cần kiểm tra wire contract tại adapter:

- Destination/topic/exchange và routing key đúng.
- Message type, content type và schema version đúng.
- Key/partition key giữ semantics ordering đã chọn.
- Headers chứa event ID, correlation ID và metadata theo contract.
- Payload bytes giải mã được bởi consumer tương thích.
- Publisher confirm/return hoặc send result được xử lý theo policy.
- Consumer nhận event và áp dụng đúng mapping.

Unit test có thể capture message để kiểm tra mapping; integration test với broker test hoặc Testcontainers xác minh serializer, routing và consumer behavior thực tế. Mock `KafkaTemplate` hoặc `RabbitTemplate` không chứng minh broker đã nhận và route message đúng.

Không dùng một test broker để thay thế mọi contract test. Broker integration kiểm tra transport semantics; fixture schema kiểm tra compatibility; module test kiểm tra ranh giới và event dispatch nội bộ.

## 16. Kiểm thử security và dữ liệu nhạy cảm trong contract

Event thường được lưu trong registry, broker, log hoặc DLQ lâu hơn request ban đầu. Vì vậy, contract test nên ngăn dữ liệu không được phép xuất hiện:

- Không có password, access token, refresh token hoặc session cookie.
- Không serialize `SecurityContext` hoặc authentication object.
- Không phát toàn bộ entity/customer profile nếu consumer chỉ cần ID.
- Tenant ID phải lấy từ nguồn đã xác thực và có semantics rõ.
- Field nhạy cảm được mask/tokenize hoặc loại bỏ theo policy.
- Unknown type metadata không được phép deserialize tùy ý.

Có thể serialize event thành JSON trong test rồi kiểm tra không có các field cấm hoặc giá trị nhạy cảm đã biết. Tuy nhiên, test blacklist field không thay thế thiết kế DTO allowlist: contract nhỏ và chỉ chứa field cần thiết là biện pháp chính.

## 17. Contract test cho enum, thời gian và số tiền

Một số kiểu dữ liệu có rủi ro tương thích cao:

| Kiểu dữ liệu | Rủi ro | Quy tắc nên kiểm tra |
|---|---|---|
| Enum | Đổi/xóa tên làm payload cũ không đọc được | Giữ giá trị đã phát hành hoặc có mapping cũ |
| `Instant` | Mất timezone/precision khi chuyển text | Dùng UTC/ISO-8601 và test round-trip |
| `LocalDate` | Bị hiểu nhầm thành timestamp | Giữ semantics ngày lịch, không tự gắn timezone |
| `BigDecimal` | Sai số nếu chuyển qua `double` | Dùng decimal string/number theo contract đã thống nhất |
| UUID | Khác format giữa producer/consumer | Kiểm tra canonical representation |
| Null/optional | Consumer nhầm thiếu field với giá trị rỗng | Định nghĩa rõ missing, null và default |
| Collection | Payload quá lớn hoặc thứ tự không xác định | Quy định size limit và ordering nếu có ý nghĩa |

Không dựa vào thứ tự field trong JSON hoặc thứ tự collection nếu contract không bảo đảm. Nếu thứ tự có ý nghĩa nghiệp vụ, producer phải công bố và test điều đó.

## 18. Ma trận kiểm thử event contract

Một ma trận tổng hợp giúp tránh chỉ kiểm tra happy path:

| Nhóm | Tình huống | Kết quả mong đợi |
|---|---|---|
| Semantics | Producer phát event sau hành động thành công | Event mô tả đúng sự kiện đã xảy ra |
| Required fields | Thiếu event ID/order ID | Validation/test thất bại rõ ràng |
| Optional fields | Field tùy chọn không có | Consumer dùng default đúng contract |
| Round-trip | Serialize rồi deserialize cùng version | Dữ liệu có ý nghĩa được bảo toàn |
| Backward compatibility | Consumer mới đọc fixture cũ | Mapping thành công hoặc chuyển đổi rõ ràng |
| Forward compatibility | Consumer cũ nhận payload mới | Bỏ qua field mở rộng hoặc từ chối theo policy đã định |
| Breaking change | Field đổi kiểu/ý nghĩa | Compatibility test phát hiện |
| Enum evolution | Payload chứa enum cũ/không biết | Mapping hoặc từ chối có kiểm soát |
| Transaction | Nguồn rollback | Không phát event mô tả commit thành công |
| Async dispatch | Listener chạy bất đồng bộ | Test chờ event bằng cơ chế đồng bộ phù hợp |
| Registry | Listener thất bại | Publication không bị hoàn tất nhầm |
| Module boundary | Consumer import implementation package | Architecture verification phát hiện |
| Externalization | Broker message được tạo | Destination, headers và payload đúng |
| Security | Event có field/secret không được phép | Contract test phát hiện rò rỉ |

## 19. Tổ chức bộ test theo tầng

Không cần một integration test lớn cho mọi assertion. Có thể phân chia:

1. **Unit test:** event factory, mapping, validation, enum/reason code và semantics.
2. **Serialization test:** round-trip và schema fixture cũ/mới.
3. **Module integration test:** event publication, listener interaction và module boundary.
4. **Persistence/recovery test:** Event Publication Registry, outbox và listener failure.
5. **Broker integration test:** externalization, serializer, routing, confirm và consumer.
6. **Architecture test:** dependency chỉ đi qua API package được công bố.

Test tầng thấp chạy nhanh và chỉ ra lỗi cụ thể. Test tích hợp xác minh wiring, transaction và persistence thực. Chọn tầng dựa trên rủi ro; không thay test database concurrency hoặc broker routing bằng mock nếu semantics đó là điều cần chứng minh.

## 20. Tránh test bất ổn

Event bất đồng bộ dễ tạo test flaky nếu test giả định listener hoàn tất ngay sau khi publish. Tránh dùng `Thread.sleep()` với thời gian cố định. Dùng `Scenario`, Awaitility hoặc một cơ chế chờ điều kiện có timeout rõ ràng.

Các nguyên tắc khác:

- Dùng event ID và test data xác định để tái lập lỗi.
- Tách transaction test khi cần xác minh commit/rollback thật.
- Dọn database/Inbox/outbox giữa test hoặc dùng namespace riêng.
- Không chia sẻ mutable event fixture giữa nhiều test chạy song song.
- Chờ listener hoàn tất trước khi assert trạng thái bất đồng bộ.
- Kiểm tra cả timeout để test không treo vô hạn.
- Không phụ thuộc vào thứ tự test execution.

## 21. Checklist trước khi phát hành event contract

- [ ] Event có tên và semantics mô tả sự kiện đã xảy ra.
- [ ] Contract là DTO/record bất biến, không phải entity hoặc object runtime.
- [ ] Required/optional/null/default được định nghĩa rõ.
- [ ] Event ID, aggregate ID, timestamp và correlation metadata có semantics ổn định.
- [ ] Decimal, date/time, enum và collection có quy ước rõ.
- [ ] Serialization round-trip được kiểm tra bằng mapper/serializer thực tế.
- [ ] Fixture của schema version cũ vẫn đọc được.
- [ ] Breaking change có version/migration plan.
- [ ] Consumer chỉ phụ thuộc package/API công khai của module phát.
- [ ] Event được phát đúng transaction phase.
- [ ] Listener async được kiểm thử bằng cơ chế chờ có timeout.
- [ ] Publication Registry/recovery được kiểm thử riêng với contract schema.
- [ ] Externalization adapter kiểm tra destination, headers và payload.
- [ ] Không có secret hoặc dữ liệu nhạy cảm không cần thiết trong event.
- [ ] Có kiểm thử module boundary, duplicate delivery và consumer expectations.

Test event contract bảo vệ ý nghĩa và hình dạng dữ liệu mà các module dùng để giao tiếp. Trong Spring Modulith, cần kết hợp kiểm thử producer, consumer, serialization fixture, module integration, publication lifecycle và externalization theo đúng từng boundary. Giữ event contract nhỏ, bất biến, có version và tương thích với payload còn tồn tại giúp các module phát triển độc lập mà không làm hỏng luồng application events khi deploy hoặc phục hồi sau sự cố.
