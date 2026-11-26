# Vì sao event cần version

Event là hợp đồng dữ liệu giữa module phát và các listener nhận sự kiện. Khi ứng dụng phát triển, payload thường thay đổi: thêm trường, đổi kiểu dữ liệu, đổi ý nghĩa nghiệp vụ hoặc tách một event thành nhiều event chuyên biệt. Nếu producer và consumer không triển khai cùng một thời điểm, hai phía có thể đọc và ghi những cấu trúc khác nhau. Version giúp nhận diện phiên bản hợp đồng, lựa chọn cách diễn giải payload và tiến hóa event có kiểm soát.

Trong Spring Modulith, application events giúp các module giao tiếp qua hợp đồng rõ ràng, còn `@ApplicationModuleListener` và Event Publication Registry hỗ trợ giao nhận sau commit. Khi event được lưu trong publication registry, externalize qua broker, retry hoặc replay, payload cũ có thể còn tồn tại sau khi code producer đã thay đổi. Vì vậy, versioning cần được thiết kế từ lúc công bố event, không đợi đến khi consumer lỗi khi deserialize.

## 1. Vì sao event cần version?

Một event có thể sống lâu hơn phiên bản code đã tạo ra nó. Consumer có thể được deploy muộn hơn producer; publication có thể nằm trong registry chờ retry; broker có thể giữ message theo retention; DLQ có thể được replay nhiều ngày sau. Nếu schema thay đổi mà không có chiến lược tương thích, các tình huống sau dễ xảy ra:

- Consumer mới không đọc được payload cũ vì trường bắt buộc hoặc kiểu dữ liệu đã đổi.
- Consumer cũ không hiểu trường mới hoặc giá trị enum mới.
- Một trường giữ nguyên tên nhưng đổi ý nghĩa, khiến consumer vẫn deserialize được nhưng xử lý sai nghiệp vụ.
- Retry một publication cũ sau deploy làm lỗi deserialize trước khi listener được gọi.
- Replay message lịch sử tạo kết quả khác vì code mới diễn giải payload theo giả định mới.
- Hai producer version cùng phát một event nhưng không thống nhất format hoặc semantics.

Version giúp consumer biết payload thuộc hợp đồng nào và chọn cách đọc phù hợp. Nó cũng giúp đội phát triển đặt quy tắc cho thay đổi tương thích, chuyển đổi dữ liệu và loại bỏ phiên bản cũ.

Version không tự làm cho event tương thích. Một trường `version: 2` không giải quyết được việc consumer không có code đọc version 2. Giá trị của version nằm ở quy trình tiến hóa schema, kiểm thử tương thích và kế hoạch rollout đi kèm.

Không phải mọi application event nội bộ đều cần một trường version tường minh. Nếu toàn bộ module luôn được build và deploy cùng nhau, event chỉ tồn tại trong bộ nhớ và không có consumer độc lập, việc version hóa từng payload có thể tạo thêm chi phí không cần thiết. Version trở nên quan trọng khi contract được dùng bởi consumer triển khai độc lập, payload được lưu bền vững, event được externalize hoặc message có thể được retry/replay qua nhiều phiên bản ứng dụng.

## 2. Phân biệt các loại định danh và version

Không nên dùng một trường `version` cho nhiều mục đích. Event ID, aggregate version và schema version biểu diễn những khái niệm khác nhau.

| Trường | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| `eventId` | Đây là lần phát sinh sự kiện nào? | UUID duy nhất, giữ nguyên qua retry/redelivery. |
| `eventType` | Sự kiện thuộc loại nghiệp vụ nào? | `OrderConfirmed`. |
| `schemaVersion` | Payload tuân theo cấu trúc hợp đồng nào? | `1`, `2`. |
| `aggregateVersion` | Aggregate nguồn ở phiên bản trạng thái nào khi phát event? | `17`, `18`. |
| `occurredAt` | Sự kiện xảy ra lúc nào? | Timestamp UTC. |
| `correlationId` | Sự kiện thuộc luồng xử lý nào? | ID của request/workflow. |
| `causationId` | Sự kiện được tạo ra bởi command/event nào? | ID của message gây ra sự kiện. |

`schemaVersion` thay đổi khi cấu trúc hoặc cách diễn giải hợp đồng thay đổi. `aggregateVersion` thay đổi theo trạng thái aggregate và thường tăng khi aggregate được cập nhật. Một aggregate có thể phát nhiều event cùng schema version nhưng aggregate version khác nhau. Ngược lại, schema version có thể tăng dù aggregate chưa thay đổi.

`eventId` phải ổn định qua retry và redelivery. Không tạo event ID mới chỉ vì chuyển payload sang schema mới trong lúc replay; nếu tạo một event nghiệp vụ mới, hãy cấp ID mới và liên kết `causationId` với event gốc.

## 3. Đặt version trong event contract

Một event có thể mang version ngay trong payload:

```java
public record OrderConfirmedV1(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        BigDecimal totalAmount,
        Instant occurredAt
) {
    public int schemaVersion() {
        return 1;
    }
}
```

Hoặc version có thể nằm trong envelope bao quanh payload:

```java
public record EventEnvelope<T>(
        UUID eventId,
        String eventType,
        int schemaVersion,
        long aggregateVersion,
        Instant occurredAt,
        String correlationId,
        String causationId,
        T payload
) {}
```

Envelope tạo một vị trí thống nhất cho metadata dùng chung, trong khi payload chỉ chứa dữ liệu riêng của event type. Với broker, một số metadata có thể được đặt trong message header; cần thống nhất rõ version nằm ở header hay payload và bảo đảm serializer, adapter, consumer cùng đọc một quy ước.

Không nên lặp version ở nhiều vị trí mà không định nghĩa trường nào là nguồn có thẩm quyền. Nếu header ghi version 2 nhưng payload ghi version 1, consumer phải xử lý thế nào? Quy tắc nên được xác định ở contract và có test phát hiện mismatch.

## 4. Khi nào cần tăng schema version?

Không phải mọi thay đổi code đều cần tăng version. Version biểu diễn thay đổi hợp đồng, không phải phiên bản ứng dụng hoặc số lần build.

| Thay đổi | Thường tương thích? | Hướng xử lý |
| --- | --- | --- |
| Thêm trường optional có default hợp lý | Thường tương thích với consumer cũ nếu serializer/consumer bỏ qua trường lạ. | Có thể giữ version nếu contract quy định rõ. |
| Thêm trường bắt buộc không có default | Có thể phá consumer cũ hoặc dữ liệu cũ. | Tăng version hoặc triển khai giai đoạn chuyển tiếp có default. |
| Xóa trường đang được consumer dùng | Breaking change. | Tăng version, migrate consumer rồi mới bỏ trường. |
| Đổi tên trường | Thường breaking với consumer dựa trên tên cũ. | Thêm trường mới, hỗ trợ song song rồi loại bỏ trường cũ. |
| Đổi kiểu dữ liệu | Có thể phá deserialize và semantics. | Dùng version mới hoặc biểu diễn tương thích rõ ràng. |
| Thêm giá trị enum | Có thể phá consumer dùng enum strict. | Consumer phải có chính sách unknown value hoặc version mới. |
| Đổi ý nghĩa nghiệp vụ nhưng giữ cấu trúc | Breaking về semantics dù deserialize thành công. | Tạo event type/version mới và mô tả khác biệt. |
| Đổi tên class Java nhưng payload wire không đổi | Có thể không ảnh hưởng nếu event type wire độc lập với class name. | Kiểm tra serializer/type mapping trước khi đổi. |

Quyết định tăng version cần dựa trên contract được công bố cho consumer. Đừng tăng version chỉ vì thêm một field nội bộ không xuất hiện trong payload; cũng đừng giữ version khi ý nghĩa nghiệp vụ đã thay đổi đáng kể.

## 5. Backward compatibility và forward compatibility

Tương thích cần được xem xét theo hướng deploy và replay:

- **Backward compatibility:** consumer mới đọc được payload do producer cũ phát.
- **Forward compatibility:** consumer cũ có thể tiếp tục đọc payload do producer mới phát, thường bằng cách bỏ qua field chưa biết hoặc có quy tắc xử lý giá trị mới.
- **Full compatibility:** cả consumer cũ với producer mới và consumer mới với producer cũ đều hoạt động trong phạm vi contract đã định.

Ví dụ thêm trường `deliveryNote` optional:

```json
{
  "eventId": "e2d7f91d-5e5d-4b7c-8a30-45a7a12c10ef",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "payload": {
    "orderId": "7f7f2d8b-b0cc-4b22-a9bb-23d75e38f09a",
    "totalAmount": 125.00,
    "deliveryNote": null
  }
}
```

Nếu consumer cũ bỏ qua field không biết và consumer mới chấp nhận field bị thiếu, thay đổi có thể tương thích hai chiều. Nhưng điều đó phụ thuộc serializer, schema format và chính sách validation; không được giả định mọi consumer đều tolerant.

Đối với enum, consumer nên có chiến lược xử lý giá trị chưa biết. Ví dụ, không nên để một giá trị mới làm toàn bộ listener crash nếu có thể đưa message vào trạng thái `UNSUPPORTED_VALUE` và cảnh báo. Tuy nhiên, không được tự ánh xạ giá trị lạ sang một trạng thái nghiệp vụ sai.

## 6. Version cấu trúc và version semantics

Một payload có thể giữ nguyên JSON shape nhưng thay đổi ý nghĩa. Ví dụ, `totalAmount` trước đây là tổng sau giảm giá, sau đó được đổi thành tổng trước giảm giá. Consumer vẫn đọc được số decimal nhưng tính toán sai.

Thay đổi semantics cần được xem như thay đổi contract. Có thể:

- tạo event type mới như `OrderConfirmedV2`;
- tăng `schemaVersion` và mô tả rõ cách diễn giải mới;
- thêm field mới có tên thể hiện ý nghĩa mới, giữ field cũ trong giai đoạn chuyển tiếp;
- chuyển đổi sang một canonical internal model trước khi consumer xử lý.

Không đổi ý nghĩa của field đang tồn tại mà không đổi version hoặc công bố migration. Một contract tốt mô tả không chỉ kiểu dữ liệu mà cả đơn vị, timezone, currency, nullability, semantics và quy tắc nghiệp vụ.

## 7. Chiến lược đặt tên version

Có hai chiến lược phổ biến:

| Chiến lược | Ví dụ | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Version trong metadata | `eventType=OrderConfirmed`, `schemaVersion=2` | Giữ event type ổn định, version là metadata rõ ràng. | Consumer cần dispatch theo type và version. |
| Version trong event type | `OrderConfirmedV2` | Dễ phân biệt contract breaking ở code và routing. | Tạo nhiều type; cần quản lý vòng đời và mapping. |

Có thể kết hợp hai cách, nhưng phải tránh version mâu thuẫn. Với application event nội bộ, record/class Java có thể được version hóa bằng type riêng. Với externalized message, nên có wire event type và schema version độc lập với tên class Java để refactor package/class không làm thay đổi contract ngoài ý muốn.

Tên event nên mô tả sự kiện nghiệp vụ đã xảy ra. Hậu tố version là thông tin contract; không thay thế tên nghiệp vụ hoặc biến event thành command.

## 8. Consumer dispatch theo version

Consumer cần chọn cách deserialize và xử lý dựa trên event type/schema version. Không nên deserialize mọi payload vào class mới nhất rồi giả định các trường cũ luôn có đầy đủ.

Ví dụ dispatcher đơn giản:

```java
public OrderConfirmed toCanonical(EventEnvelope<JsonNode> envelope) {
    return switch (envelope.schemaVersion()) {
        case 1 -> v1Mapper.toCanonical(envelope.payload());
        case 2 -> v2Mapper.toCanonical(envelope.payload());
        default -> throw new UnsupportedEventVersionException(
                envelope.eventType(), envelope.schemaVersion()
        );
    };
}
```

`OrderConfirmed` ở đây là canonical model nội bộ mà business handler sử dụng. Mapper chuyển từng schema wire sang cùng một mô hình để phần nghiệp vụ không phải chứa điều kiện version ở mọi nơi.

Nếu gặp version không hỗ trợ, consumer cần quyết định rõ: từ chối và đưa vào DLQ/quarantine, chờ deploy consumer mới, hoặc dùng một compatibility adapter đã được kiểm chứng. Không âm thầm bỏ event quan trọng hoặc diễn giải payload theo version gần nhất.

## 9. Upcasting và chuyển đổi event cũ

Upcasting là chuyển payload phiên bản cũ sang mô hình mới hơn khi đọc, thường qua một chuỗi hàm chuyển đổi có thể kiểm thử. Ví dụ, V1 lưu `customerName`, còn V2 dùng `customerReference`:

```java
public OrderConfirmedV2 upcast(OrderConfirmedV1 oldEvent) {
    return new OrderConfirmedV2(
            oldEvent.eventId(),
            oldEvent.orderId(),
            customerLookup.referenceForLegacyName(oldEvent.customerName()),
            oldEvent.totalAmount(),
            oldEvent.occurredAt(),
            2
    );
}
```

Đây là ví dụ minh họa; việc ánh xạ tên sang customer reference chỉ hợp lệ nếu có nguồn dữ liệu xác định duy nhất. Không suy đoán ID từ dữ liệu không đủ căn cứ.

Upcaster cần có các đặc tính:

- Có đầu vào và đầu ra version rõ ràng.
- Không sửa message gốc nếu hệ thống cần giữ bằng chứng lịch sử.
- Có thể chạy lặp cho cùng payload và cho cùng kết quả.
- Có test cho dữ liệu cũ, dữ liệu thiếu field và giá trị biên.
- Có chính sách khi không thể chuyển đổi, ví dụ quarantine và yêu cầu can thiệp.
- Có thể xâu chuỗi `V1 -> V2 -> V3` hoặc chuyển trực tiếp sang canonical model.

Không phải mọi ứng dụng đều cần event store hay upcaster framework. Nếu publication registry chỉ lưu trạng thái giao event ngắn hạn, có thể chỉ cần serializer tương thích trong khoảng retry window. Nếu broker giữ message lâu hoặc hệ thống hỗ trợ replay lịch sử, chiến lược đọc schema cũ trở nên quan trọng hơn.

## 10. Rollout producer và consumer không đồng thời

Producer và consumer thường được deploy độc lập. Một rollout an toàn cần bảo đảm consumer có thể đọc cả payload cũ và mới trong khoảng chuyển tiếp.

Một trình tự triển khai thường dùng:

1. **Mở rộng consumer trước:** triển khai consumer đọc được cả V1 và V2, nhưng vẫn xử lý V1 như hiện tại.
2. **Mở rộng contract:** thêm field hoặc schema V2 theo cách tương thích, chưa loại bỏ field cũ.
3. **Chuyển producer:** bắt đầu phát V2 hoặc phát song song theo migration plan đã xác định.
4. **Quan sát:** đo tỷ lệ V1/V2, lỗi deserialize, DLQ và kết quả xử lý.
5. **Chuyển consumer hoàn toàn:** xác nhận mọi consumer cần thiết đã đọc V2.
6. **Thu hẹp contract:** ngừng phát V1 sau khi retry/replay window và consumer cũ đã được xử lý.
7. **Loại bỏ code cũ:** chỉ xóa V1 mapper/schema khi không còn message V1 cần đọc và đã có kế hoạch rollback.

Đây thường được gọi là expand-and-contract. Trong giai đoạn expand, producer và consumer chấp nhận cả cấu trúc cũ/mới. Trong giai đoạn contract, phiên bản cũ được loại bỏ sau khi đã xác minh không còn phụ thuộc.

Không dual-publish hai event type cho cùng một hành động nếu consumer không có idempotency hoặc quy tắc dedup rõ ràng; điều đó có thể tạo side effect hai lần. Nếu cần phát cả V1 và V2, phải xác định chúng là hai biểu diễn của cùng một event, giữ chung event ID/correlation và bảo đảm consumer không xử lý cả hai như hai sự kiện nghiệp vụ độc lập.

## 11. Versioning với Spring Modulith

Spring Modulith tổ chức application events giữa các module trong cùng ứng dụng. Event contract nên nằm ở API package được công bố cho consumer; module nhận không nên phụ thuộc vào package nội bộ của module nguồn.

Với event nội bộ, có thể dùng record riêng cho từng schema version hoặc một envelope có version. Ví dụ:

```java
public record OrderConfirmedV2(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        UUID customerReference,
        BigDecimal totalAmount,
        String currency,
        Instant occurredAt
) {}
```

Nếu dùng class Java làm contract nội bộ, thay đổi tên package/class có thể ảnh hưởng serializer hoặc persistence adapter nếu chúng lưu type metadata. Cần kiểm tra cách event được serialize trong cấu hình thực tế và giữ khả năng đọc publication cũ trong thời gian chúng còn có thể được retry.

`@ApplicationModuleListener` nhận event theo type mà Spring đăng ký. Nếu chuyển từ `OrderConfirmedV1` sang `OrderConfirmedV2`, có thể cần listener cho cả hai type trong giai đoạn chuyển tiếp hoặc một adapter chuyển V1 sang canonical model. Đừng giả định listener nhận class mới sẽ tự động nhận record cũ có cấu trúc khác.

Event Publication Registry theo dõi publication đến transactional listener và có thể giữ dữ liệu event qua persistence adapter. Registry không phải event store lâu dài, nhưng publication incomplete có thể sống qua một lần deploy. Vì vậy, code mới cần đọc được event cũ còn tồn tại trong retry window hoặc có quy trình xử lý/quarantine an toàn trước khi xóa class/serializer cũ.

## 12. Versioning khi externalize qua broker

Khi event được externalize, wire format trở thành hợp đồng giữa các process hoặc tổ chức khác nhau. Không nên để tên class Java, package hoặc chi tiết persistence nội bộ quyết định schema bên ngoài.

Một message envelope có thể gồm:

```json
{
  "eventId": "f4c2a9f4-0d4f-47b1-8a0f-7d3f0d0a1234",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "aggregateVersion": 18,
  "occurredAt": "2026-11-25T08:30:00Z",
  "correlationId": "workflow-9a2",
  "payload": {
    "orderId": "2a7a3d42-17d4-4f52-93b8-0a4a0a0f1234",
    "customerReference": "cust-ref-91",
    "totalAmount": 125.00,
    "currency": "VND"
  }
}
```

Consumer ngoài cần biết schema registry hoặc contract repository nào là nguồn chuẩn, quy tắc tương thích được chọn, cách xử lý version chưa hỗ trợ và thời gian lưu schema cũ. Nếu dùng Avro, Protobuf hoặc JSON Schema, áp dụng compatibility mode tương ứng của công cụ; không suy ra tương thích chỉ từ việc field mới có vẻ optional.

Với Kafka hoặc RabbitMQ, broker thường lưu message bytes và metadata; nó không tự chuyển đổi schema cho consumer. Serializer/deserializer, schema registry và consumer adapter chịu trách nhiệm đọc đúng version. Externalization adapter của Spring Modulith cần được kiểm thử cùng wire contract thực tế.

## 13. Retention, retry và replay

Version cũ cần được hỗ trợ ít nhất trong khoảng thời gian message có thể quay lại hệ thống:

- Publication incomplete trong Event Publication Registry.
- Retry queue hoặc delayed retry.
- Broker topic retention.
- Dead-letter queue.
- Backup/export hoặc kho lưu message.
- Quy trình replay thủ công hoặc rebuild projection.

Trước khi xóa mapper V1, hãy xác định không còn message V1 trong các nơi trên hoặc có cách chuyển đổi đã được kiểm thử. Nếu DLQ giữ message 30 ngày, consumer có thể nhận lại V1 sau 30 ngày dù producer đã chỉ phát V2 từ lâu.

Khi replay, giữ nguyên `eventId` và `schemaVersion` của payload gốc nếu đang phát lại cùng sự kiện. Nếu chuyển payload sang canonical representation, ghi rõ version nguồn và version đích trong log/trace; không sửa lịch sử message gốc một cách âm thầm.

Event Publication Registry không nên được dùng làm nguồn lịch sử đầy đủ để replay mọi event. Nó theo dõi trạng thái publication; khả năng replay phải dựa vào broker retention, event store hoặc nguồn snapshot/history được thiết kế riêng.

## 14. Schema registry và contract test

Với nhiều producer/consumer, schema registry hoặc contract repository giúp công bố schema có version và kiểm tra compatibility trước deploy. Quy trình có thể gồm:

1. Producer đề xuất schema mới.
2. Công cụ kiểm tra schema mới với các version đã đăng ký theo compatibility mode.
3. Consumer contract test xác nhận có thể deserialize và diễn giải payload.
4. Producer test xác nhận payload thực tế khớp schema đã công bố.
5. CI từ chối thay đổi breaking nếu chưa có migration/version mới.

Contract test nên kiểm tra cả cấu trúc lẫn semantics. Ví dụ, `totalAmount` cần xác định currency, scale, rounding và có bao gồm thuế/giảm giá hay không. Một schema hợp lệ về kiểu `number` vẫn có thể sai nghiệp vụ nếu producer và consumer hiểu đơn vị khác nhau.

## 15. Kiểm thử tiến hóa event

Một bộ test versioning nên bao gồm:

1. Consumer mới đọc được payload V1 còn tồn tại.
2. Consumer mới đọc được payload V2.
3. Consumer cũ xử lý payload mới theo chính sách forward compatibility nếu hệ thống cam kết điều đó.
4. Field optional bị thiếu được gán default đúng.
5. Giá trị enum chưa biết được xử lý có chủ đích, không làm sai trạng thái nghiệp vụ.
6. Version không hỗ trợ được quarantine/DLQ và cảnh báo.
7. Upcaster V1 sang canonical model tạo kết quả ổn định.
8. Cùng event ID qua retry/replay không tạo side effect trùng.
9. Producer V1 và V2 cùng hoạt động trong giai đoạn rollout mà không làm consumer xử lý hai lần.
10. Publication cũ trong registry vẫn được deserialize hoặc được xử lý theo quy trình phục hồi đã định.
11. Serializer và externalization adapter tạo wire payload đúng schema version.
12. Contract test phát hiện thay đổi semantics dù JSON shape không đổi.

Lưu payload mẫu đại diện cho từng version trong test fixture hoặc contract test resources của dự án. Fixture nên là dữ liệu đã được phê duyệt, không chứa thông tin cá nhân hoặc bí mật thật.

## 16. Quan sát version trong production

Metric và log giúp phát hiện consumer đang nhận version nào và version cũ còn tồn tại bao lâu.

Metric có cardinality thấp có thể dùng:

- số message theo `event_type` và `schema_version`;
- số lỗi deserialize theo version;
- số event bị quarantine do unsupported version;
- độ trễ xử lý theo version;
- số publication incomplete có event type/version tương ứng nếu registry/API cung cấp đủ metadata.

Không đưa `event_id`, aggregate ID hoặc customer ID làm metric label. Các định danh này phù hợp với log/trace có kiểm soát để điều tra một message cụ thể.

Log nên ghi event type, schema version, event ID, aggregate version, consumer name và correlation ID. Khi chuyển đổi V1 sang canonical model, ghi cả source version và target model version. Không log toàn bộ payload nếu chứa dữ liệu nhạy cảm.

Một dashboard hữu ích cho thấy tỷ lệ V1/V2 theo thời gian, consumer nào còn nhận V1, lỗi deserialize và số message V1 còn trong retry/DLQ. Dữ liệu này giúp xác định thời điểm an toàn để loại bỏ code cũ.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Dùng app version làm event schema version | Consumer không biết payload thực sự theo cấu trúc nào. | Version hóa contract độc lập với release/build. |
| Gộp schema version và aggregate version | Consumer nhầm thay đổi dữ liệu với thay đổi cấu trúc. | Dùng hai trường riêng và định nghĩa rõ. |
| Đổi ý nghĩa field mà không tăng version | Deserialize thành công nhưng logic sai. | Xem semantics là một phần của contract. |
| Xóa field ngay sau khi producer ngừng phát | Consumer cũ hoặc message replay không đọc được. | Expand-and-contract và chờ hết retention/retry window. |
| Giả định consumer bỏ qua field lạ | Consumer strict có thể lỗi deserialize. | Contract test trên serializer/consumer thực tế. |
| Không xử lý enum mới | Listener crash khi gặp giá trị chưa biết. | Có chính sách unknown value rõ ràng. |
| Tạo event ID mới khi retry | Inbox/idempotency không nhận ra cùng event. | Giữ event ID qua retry/redelivery. |
| Dùng registry làm event store | Không thể replay lịch sử đầy đủ và đúng semantics. | Dùng nguồn history/event store được thiết kế riêng. |
| Refactor class Java làm thay đổi wire type | Consumer hoặc publication cũ không deserialize được. | Tách wire contract khỏi tên class và kiểm thử serialization. |

## 18. Checklist trước khi thay đổi event schema

- [ ] Đã xác định thay đổi cấu trúc hay thay đổi semantics.
- [ ] `schemaVersion` được phân biệt với `eventId` và `aggregateVersion`.
- [ ] Contract mô tả field, kiểu, nullability, đơn vị và ý nghĩa nghiệp vụ.
- [ ] Đã đánh giá backward/forward compatibility với mọi consumer liên quan.
- [ ] Có quy tắc cho field mới, field bị xóa và enum chưa biết.
- [ ] Consumer có thể dispatch version hoặc upcast về canonical model.
- [ ] Rollout producer/consumer theo expand-and-contract.
- [ ] Không dual-publish gây side effect trùng.
- [ ] Retry, registry, broker retention và DLQ còn đọc được version cũ.
- [ ] Externalized wire format không phụ thuộc ngoài ý muốn vào class/package Java.
- [ ] Có contract test và payload fixture cho từng version.
- [ ] Có metric/log để biết version nào còn được sử dụng trước khi loại bỏ.

Event cần version vì hợp đồng dữ liệu tồn tại qua nhiều lần deploy, retry và replay, trong khi producer và consumer không nhất thiết thay đổi cùng lúc. Trong Spring Modulith, version rõ ràng giúp module giữ hợp đồng event ổn định khi listener và publication được xử lý bất đồng bộ; với externalization, nó còn là cam kết giữa các process độc lập. Khi phân biệt schema version với event ID và aggregate version, áp dụng compatibility có chủ đích, triển khai expand-and-contract và giữ khả năng đọc message cũ trong retry/retention window, event có thể tiến hóa mà không làm gián đoạn giao tiếp giữa các module.
