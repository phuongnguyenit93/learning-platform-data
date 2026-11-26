# Mô tả payload

## Payload là gì trong event contract?

Payload là phần dữ liệu nghiệp vụ của một event. Nó mô tả điều gì đã xảy ra và cung cấp những thông tin mà consumer cần để phản ứng. Ví dụ, OrderConfirmed có thể chứa orderId, tổng tiền đã chốt, thời điểm xác nhận và thông tin giao hàng được phép chia sẻ.

Một payload được mô tả tốt giúp producer và consumer hiểu cùng một ý nghĩa mà không cần đọc mã nguồn của nhau. Tài liệu cần trả lời được: field biểu diễn điều gì, kiểu dữ liệu và định dạng nào được chấp nhận, field có thể vắng mặt hay null không, giá trị được tính theo quy tắc nào, đơn vị là gì và consumer nên xử lý ra sao.

Tài liệu payload là một phần của event contract. Nó đi cùng event type, schema version, quy tắc tương thích, metadata và chính sách bảo mật. Một JSON mẫu đẹp nhưng thiếu ý nghĩa field, đơn vị hoặc điều kiện bắt buộc vẫn chưa phải tài liệu contract đầy đủ.

~~~mermaid
flowchart TD
    E[Event contract] --> H[Envelope metadata]
    E --> P[Business payload]
    P --> F[Field definitions]
    P --> X[Examples]
    P --> V[Validation rules]
    P --> C[Compatibility rules]
    P --> S[Security and privacy]
~~~

## Phân biệt envelope, metadata và payload

Một message event thường có thể được chia thành ba phần logic:

| Phần | Vai trò | Ví dụ |
|---|---|---|
| Envelope | Đóng gói event và thông tin định tuyến/phiên bản | eventId, eventType, schemaVersion |
| Metadata | Thông tin phục vụ truy vết, nguồn phát và ngữ cảnh | producerId, correlationId, causationId |
| Payload | Dữ liệu nghiệp vụ mà event công bố | orderId, totalAmount, currency |

Tùy transport và tiêu chuẩn, metadata có thể nằm trong envelope, message header hoặc CloudEvents context attributes. Điều quan trọng là tài liệu phải chỉ ra field thuộc lớp nào và nguồn chuẩn của field đó.

Ví dụ envelope minh họa:

~~~json
{
  "eventId": "8e5e9c66-44df-4c2b-9a6b-2f4b8f2f4a10",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "producer": "orders",
  "occurredAt": "2026-11-25T10:15:30Z",
  "correlationId": "checkout-781",
  "payload": {
    "orderId": "ORD-2026-0042",
    "totalAmount": "125000.00",
    "currency": "VND",
    "confirmedAt": "2026-11-25T10:15:29Z"
  }
}
~~~

Ví dụ chỉ minh họa một cấu trúc do ứng dụng thiết kế, không phải envelope mặc định của Spring Modulith. Khi dùng CloudEvents hoặc một envelope chuẩn khác, hãy tuân thủ cấu trúc và tên attribute của chuẩn đó thay vì tạo một cấu trúc gần giống nhưng khác nghĩa.

Không lặp cùng một field ở cả metadata và payload nếu chưa có quy tắc rõ ràng. Nếu eventId xuất hiện ở hai nơi, cần xác định nguồn nào là chuẩn và kiểm tra hai giá trị luôn khớp nhau.

## Mô tả từng field như một hợp đồng

Mỗi field nên có mô tả đủ rõ để một nhóm khác triển khai consumer mà không phải suy đoán. Một bảng field definition thường gồm:

| Thuộc tính | Nội dung cần ghi |
|---|---|
| Name | Tên chính xác trong payload |
| Type | Kiểu dữ liệu trên wire |
| Required | Field bắt buộc hay có thể vắng mặt |
| Nullable | Field có chấp nhận null không |
| Meaning | Ý nghĩa nghiệp vụ cụ thể |
| Format | Định dạng chuỗi, timestamp, ID hoặc số |
| Unit | Đơn vị đo và currency nếu có |
| Constraints | Miền giá trị, độ dài, precision, pattern |
| Default | Quy tắc khi field vắng mặt, nếu có |
| Example | Giá trị mẫu hợp lệ |
| Source | Module hoặc quy tắc nghiệp vụ sở hữu giá trị |
| Privacy | Phân loại dữ liệu và quyền truy cập |

Ví dụ bảng mô tả payload OrderConfirmed:

| Field | Type | Required | Nullable | Mô tả |
|---|---|---:|---:|---|
| orderId | string | Có | Không | ID duy nhất của đơn hàng trong hệ thống Orders |
| totalAmount | string decimal | Có | Không | Tổng tiền đã chốt của đơn hàng, biểu diễn decimal theo scale được công bố |
| currency | string | Có | Không | Mã tiền tệ ISO 4217 viết hoa |
| confirmedAt | string date-time | Có | Không | Thời điểm đơn hàng chuyển sang trạng thái CONFIRMED |
| deliveryNote | string | Không | Không | Ghi chú giao hàng do khách hàng cung cấp, tối đa 500 ký tự |

Mô tả “tổng tiền đơn hàng” còn quá mơ hồ nếu không nói rõ có bao gồm thuế, phí vận chuyển, chiết khấu hoặc khoản hoàn tiền hay không. Hãy ghi rõ quy tắc tính và thời điểm chốt.

## Required, optional, nullable và default

Các trạng thái này phải được mô tả riêng:

- **Required:** field phải xuất hiện trong payload.
- **Optional:** field có thể không xuất hiện.
- **Nullable:** field có thể xuất hiện với giá trị null.
- **Default:** giá trị hoặc hành vi thay thế khi field không được cung cấp.

Optional không tự động có nghĩa nullable. Một field có thể vắng mặt nhưng nếu xuất hiện phải chứa giá trị hợp lệ. Một field required có thể nullable nếu contract cho phép key luôn xuất hiện nhưng đôi khi mang null.

Ví dụ field optional và không nullable:

~~~json
{
  "orderId": "ORD-42"
}
~~~

Ví dụ field optional và nullable:

~~~json
{
  "orderId": "ORD-42",
  "deliveryNote": null
}
~~~

Ví dụ field có giá trị:

~~~json
{
  "orderId": "ORD-42",
  "deliveryNote": "Giao tại cửa sau"
}
~~~

Nếu absent và null có ý nghĩa nghiệp vụ khác nhau, phải giữ được sự khác biệt khi deserialize. Một Java field kiểu String có thể nhận null cho cả hai trường hợp nếu cấu hình deserializer không lưu presence information. Khi cần phân biệt, dùng cấu trúc có trạng thái hoặc biểu diễn phù hợp với serializer.

Default cần nói rõ được áp dụng ở đâu. JSON Schema có thể mô tả default như annotation nhưng validator không nhất thiết tự chèn giá trị. Consumer hoặc domain model phải thực hiện fallback theo contract.

Không để mỗi consumer tự suy ra default nghiệp vụ khác nhau. Nếu default ảnh hưởng tới trạng thái hoặc quyết định nghiệp vụ, module sở hữu dữ liệu cần công bố quy tắc chuẩn.

## Quy định kiểu dữ liệu và định dạng trên wire

Tài liệu nên mô tả kiểu dữ liệu thực sự được truyền, không chỉ kiểu Java nội bộ.

| Dữ liệu | Định dạng nên công bố |
|---|---|
| Identifier | String với format/namespace rõ ràng, ví dụ UUID hoặc mã domain |
| Money | Decimal string hoặc cấu trúc amount + currency |
| Timestamp | RFC 3339/ISO 8601 có timezone, thường chuẩn hóa UTC |
| Date nghiệp vụ | ISO 8601 date, không gắn giờ nếu không có ý nghĩa thời điểm |
| Boolean | true hoặc false, tránh các chuỗi tự do như yes/no |
| Enum | Danh sách giá trị wire ổn định và quy tắc unknown value |
| Collection | Kiểu phần tử, thứ tự có ý nghĩa hay không, giới hạn số lượng |
| Object lồng nhau | Schema, required field và quy tắc tương thích riêng |

Không dùng tên kiểu Java như BigDecimal, Instant hoặc UUID làm mô tả duy nhất nếu consumer có thể viết bằng ngôn ngữ khác. Hãy ghi wire type và format tương ứng.

Ví dụ BigDecimal có thể được serialize thành JSON number hoặc string tùy cấu hình. Nếu precision tiền tệ quan trọng, công bố chính xác biểu diễn được gửi và quy tắc scale. Không giả định consumer tự biết serializer đang dùng.

## Mô tả tiền tệ và số đo

Các giá trị số cần có đơn vị. Một field tên amount không đủ rõ nếu không biết đơn vị là đồng, nghìn đồng, cent hay đơn vị nội bộ.

Với tiền:

- Ghi currency theo ISO 4217.
- Nêu amount là trước thuế hay sau thuế.
- Nêu có bao gồm phí vận chuyển, chiết khấu hoặc khoản điều chỉnh không.
- Nêu scale và quy tắc làm tròn.
- Chọn decimal representation ổn định.
- Không dùng floating point binary cho giá trị tiền cần độ chính xác.

Ví dụ:

~~~json
{
  "amount": "125000.00",
  "currency": "VND"
}
~~~

Với đại lượng đo lường, ghi đơn vị và hệ đo. Ví dụ weightKg là kilogram, distanceMeters là mét, durationMillis là mili giây. Nếu có khả năng thay đổi đơn vị, dùng object gồm value và unit hoặc tên field chứa đơn vị.

Không đổi đơn vị của field đã công bố mà vẫn giữ nguyên tên và schema version. Nếu cần đổi, tạo field mới hoặc version contract với kế hoạch chuyển đổi rõ ràng.

## Timestamp và múi giờ

Một timestamp cần trả lời đó là thời điểm nào:

- Thời điểm nghiệp vụ xảy ra.
- Thời điểm trạng thái được commit.
- Thời điểm producer tạo event.
- Thời điểm message được publish.
- Thời điểm consumer xử lý.

Không dùng một field createdAt chung cho nhiều ý nghĩa. Tên như occurredAt, confirmedAt, publishedAt và processedAt giúp tránh nhầm lẫn.

Nên công bố timestamp theo ISO 8601/RFC 3339 có offset hoặc UTC, ví dụ:

~~~json
{
  "confirmedAt": "2026-11-25T10:15:29Z"
}
~~~

Date-only như ngày giao dự kiến không nên được diễn giải thành midnight UTC nếu nghiệp vụ chỉ quan tâm ngày theo lịch. Hãy phân biệt date, local date-time và instant.

Tài liệu cũng cần nêu độ chính xác timestamp nếu consumer phụ thuộc vào mili giây hoặc micro giây. Không giả định mọi database, serializer và ngôn ngữ đều giữ cùng độ chính xác.

## Enum và giá trị chưa biết

Với enum, liệt kê giá trị wire và ý nghĩa từng giá trị. Ví dụ:

| Value | Ý nghĩa |
|---|---|
| STANDARD | Giao hàng tiêu chuẩn |
| EXPRESS | Giao hàng nhanh |
| PICKUP | Khách tự nhận |

Không công bố tên enum Java rồi để consumer phụ thuộc trực tiếp vào tên class hoặc thứ tự khai báo. Giá trị wire nên ổn định và không phụ thuộc ordinal.

Consumer cần có chính sách khi nhận enum mới:
- Bỏ qua field nếu nó chỉ mang tính thông tin và không ảnh hưởng xử lý.
- Ánh xạ về UNKNOWN nếu contract cho phép.
- Từ chối hoặc quarantine nếu giá trị không biết làm thay đổi quyết định nghiệp vụ quan trọng.

Không tự chuyển enum không biết thành một giá trị mặc định có thể gây hành vi sai. Tài liệu cần nói rõ producer có thể bổ sung giá trị mới hay không và consumer phải chuẩn bị thế nào.

## Collection, nested object và thứ tự phần tử

Với array/list, mô tả:
- Kiểu của mỗi phần tử.
- Số phần tử tối thiểu/tối đa.
- Có cho phép phần tử trùng không.
- Thứ tự có ý nghĩa nghiệp vụ hay chỉ là thứ tự truyền.
- Có thể rỗng hay null không.

Ví dụ:

~~~json
{
  "items": [
    {
      "productId": "SKU-100",
      "quantity": 2,
      "unitPrice": "45000.00"
    },
    {
      "productId": "SKU-200",
      "quantity": 1,
      "unitPrice": "35000.00"
    }
  ]
}
~~~

Nếu thứ tự items không có ý nghĩa, consumer không nên dựa vào vị trí phần tử. Nếu thứ tự có ý nghĩa, ghi rõ quy tắc như thứ tự thêm vào đơn hàng hoặc thứ tự ưu tiên.

Nested object nên có bảng field definition riêng. Tránh mô tả một object lớn bằng một câu chung vì consumer khó biết field con nào bắt buộc, có thể null hoặc có giới hạn.

## Ví dụ payload đầy đủ và ví dụ tối thiểu

Tài liệu nên có ít nhất một payload hợp lệ đầy đủ và một payload thể hiện trường hợp tối thiểu khi field optional vắng mặt.

Ví dụ đầy đủ:

~~~json
{
  "orderId": "ORD-2026-0042",
  "totalAmount": "125000.00",
  "currency": "VND",
  "confirmedAt": "2026-11-25T10:15:29Z",
  "deliveryNote": "Giao tại quầy lễ tân",
  "items": [
    {
      "productId": "SKU-100",
      "quantity": 2,
      "unitPrice": "45000.00"
    },
    {
      "productId": "SKU-200",
      "quantity": 1,
      "unitPrice": "35000.00"
    }
  ]
}
~~~

Ví dụ tối thiểu:

~~~json
{
  "orderId": "ORD-2026-0042",
  "totalAmount": "125000.00",
  "currency": "VND",
  "confirmedAt": "2026-11-25T10:15:29Z",
  "items": []
}
~~~

Ví dụ cần nhất quán với field table và schema. Không đưa field không được mô tả vào payload mẫu. Nếu payload mẫu là dữ liệu giả, dùng identifier và thông tin không đại diện cho khách hàng thật.

## Ví dụ payload không hợp lệ

Một ví dụ sai giúp consumer hiểu validation rule và cách producer phải tránh vi phạm contract.

~~~json
{
  "orderId": "",
  "totalAmount": "-125000.00",
  "currency": "vnd",
  "confirmedAt": "25-11-2026 10:15",
  "deliveryNote": "..."
}
~~~

Các vấn đề có thể gồm:
- orderId rỗng, không phải identifier hợp lệ.
- totalAmount âm nếu event này chỉ công bố đơn hàng đã xác nhận và nghiệp vụ không cho phép tổng âm.
- currency không theo quy ước mã viết hoa.
- confirmedAt không theo định dạng timestamp được công bố.
- deliveryNote có thể vượt giới hạn độ dài.

Không phải mọi event đều cấm amount âm; credit note hoặc adjustment có thể cho phép. Validation phải theo semantics của event, không sao chép một quy tắc chung cho mọi payload.

Tài liệu nên chỉ rõ lỗi nào khiến producer không được phát event, lỗi nào consumer có thể quarantine và lỗi nào có thể bỏ qua an toàn.

## Source of truth và nguồn hình thành field

Mỗi field cần có nguồn sở hữu hoặc quy tắc hình thành rõ ràng. Ví dụ:

| Field | Nguồn có thẩm quyền | Quy tắc |
|---|---|---|
| orderId | Orders | ID do Orders cấp |
| totalAmount | Orders | Snapshot tổng tiền tại thời điểm xác nhận |
| currency | Orders | Currency của đơn hàng đã chốt |
| confirmedAt | Orders | Thời điểm chuyển trạng thái CONFIRMED |
| deliveryNote | Orders/Checkout | Giá trị đã được xác nhận trong đơn hàng |

Consumer không nên tự tính lại totalAmount từ danh sách items nếu contract nói đây là snapshot đã chốt. Cách tính có thể thay đổi theo thuế, chiết khấu hoặc chính sách giá.

Nếu field được tổng hợp từ nhiều nguồn, ghi rõ quy tắc ưu tiên và thời điểm snapshot. Không công bố một giá trị tổng hợp mà không nói nó nhất quán tại thời điểm nào.

## Phân loại dữ liệu và quyền riêng tư

Payload có thể chứa dữ liệu cá nhân, tài chính hoặc thông tin nội bộ. Tài liệu cần nêu phân loại và mục đích sử dụng:

- Public/internal/confidential/restricted theo policy tổ chức.
- Consumer nào được phép nhận field.
- Field có được ghi log hoặc đưa vào trace không.
- Thời gian lưu trữ và yêu cầu xóa.
- Có cần masking, tokenization hoặc mã hóa không.
- Có nên đưa field vào event chung hay chỉ gửi qua một event chuyên biệt.

Không đưa số thẻ, credential, access token hoặc dữ liệu bí mật không cần thiết vào event. Không dùng payload làm nơi truyền dữ liệu lớn hoặc dữ liệu có vòng đời riêng mà consumer không cần.

Nếu event được broadcast tới nhiều consumer, quyền truy cập phải được đánh giá theo consumer có quyền thấp nhất. Một field nhạy cảm có thể khiến toàn bộ event không phù hợp để chia sẻ rộng.

## Payload và schema version

Mỗi payload cần gắn với một schema version hoặc một quy tắc xác định version. Tài liệu phải cho biết:
- Version được đặt trong envelope, schema registry hay metadata.
- Consumer xử lý version cũ và mới thế nào.
- Field mới có optional hay required.
- Field bị deprecated còn được gửi trong bao lâu.
- Khi nào một thay đổi cần event type/version mới.
- Cách xử lý event cũ trong retry queue, DLQ hoặc archive.

Không dùng phiên bản ứng dụng producer thay cho schema version nếu hai khái niệm có vòng đời khác nhau. Một producer version có thể phát nhiều schema version; một schema version có thể được nhiều phiên bản producer sử dụng.

Khi thêm field tùy chọn, định nghĩa absent, null và default. Khi đổi ý nghĩa hoặc kiểu dữ liệu, đánh giá compatibility và lập kế hoạch migration.

## Payload với CloudEvents

Nếu ứng dụng dùng CloudEvents, cần phân biệt context attributes chuẩn và data payload. Các thuộc tính như id, source, type, subject, time và datacontenttype mô tả context của event; data chứa dữ liệu nghiệp vụ.

Ví dụ CloudEvents JSON:

~~~json
{
  "specversion": "1.0",
  "id": "evt-8e5e9c66",
  "source": "/orders",
  "type": "com.example.orders.order-confirmed",
  "subject": "ORD-2026-0042",
  "time": "2026-11-25T10:15:30Z",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "ORD-2026-0042",
    "totalAmount": "125000.00",
    "currency": "VND"
  }
}
~~~

Không sao chép context attribute vào data nếu không có lý do contract rõ ràng. Nếu consumer cần orderId để xử lý nghiệp vụ, nó thuộc data; subject có thể cũng tham chiếu order nhưng có vai trò context.

Nếu dùng CloudEvents extension attributes, tài liệu cần ghi tên, kiểu và ý nghĩa theo quy tắc extension. Không đặt tên trùng với attribute chuẩn hoặc dùng extension để thay thế semantics của field chuẩn.

## Tích hợp payload với Spring Modulith

Spring Modulith tổ chức application event giữa các module. Event class thường là Java record hoặc class được công bố như một phần contract. Khi event được externalize, serializer chuyển object thành payload gửi qua adapter và broker.

Một event có thể được định nghĩa:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    BigDecimal totalAmount,
    String currency,
    Instant confirmedAt,
    String deliveryNote
) {}
~~~

Tài liệu nên giải thích event này biểu diễn snapshot nào, field nào bắt buộc, currency có format nào, deliveryNote có thể vắng mặt không và consumer có thể dựa vào totalAmount ở thời điểm nào.

Không coi cấu trúc Java là tài liệu wire contract hoàn chỉnh. Jackson naming strategy, custom serializer, module Java Time, enum serializer và cấu hình inclusion có thể làm JSON khác với tên field hoặc kiểu Java.

Cần xác nhận payload sau serialize thực tế. Nếu dùng @Externalized hoặc integration adapter, ghi rõ target, serializer, header và schema version được truyền. Event Publication Registry theo dõi publication; nó không tự mô tả payload hoặc bảo đảm schema compatibility.

## Tạo tài liệu từ schema nhưng vẫn giải thích ngữ nghĩa

Có thể sinh bảng kiểu, required field và ví dụ cơ bản từ JSON Schema, Avro hoặc Protobuf descriptor. Tuy nhiên, schema thường không diễn đạt đầy đủ ý nghĩa nghiệp vụ, nguồn có thẩm quyền, đơn vị, thời điểm snapshot và privacy classification.

Một tài liệu payload tốt kết hợp:
- Schema machine-readable để validate và generate model.
- Field table để giải thích semantics.
- Ví dụ thực tế đã được làm sạch dữ liệu.
- Quy tắc compatibility và versioning.
- Hướng dẫn consumer xử lý absent/null/unknown values.
- Quyền truy cập và retention.

Không duy trì hai bản schema độc lập bằng tay nếu có thể sinh tài liệu từ một nguồn chuẩn. Nếu schema và Markdown cùng được sửa thủ công, chúng có thể lệch nhau. Nên đặt schema là source of truth cho cấu trúc và kiểm tra tài liệu bằng contract test hoặc generation trong pipeline.

## Kiểm thử tài liệu payload

Tài liệu nên được kiểm chứng bằng dữ liệu và serializer thực tế:

| Kiểm tra | Điều cần xác nhận |
|---|---|
| Schema validation | Payload mẫu hợp lệ qua schema |
| Required field | Thiếu field bắt buộc bị từ chối |
| Optional field | Payload thiếu field tùy chọn vẫn hợp lệ |
| Nullable field | Null được chấp nhận đúng nơi |
| Type/format | Sai kiểu, timestamp hoặc enum bị phát hiện |
| Range/length | Giới hạn số, chuỗi và collection được thực thi |
| Serialization | Event class tạo ra payload đúng tên field và kiểu wire |
| Deserialization | Consumer đọc được payload mẫu cũ và mới |
| Compatibility | Producer/consumer version hỗ trợ đúng ma trận |
| Privacy | Payload/log không chứa dữ liệu cấm hoặc bí mật |

Giữ các payload mẫu như contract fixture có version. Nếu tài liệu nói field optional, test cần có payload thực sự không chứa field đó; chỉ tạo Java object với null rồi serialize chưa chắc tạo ra field vắng mặt vì serializer có thể ghi null.

Nếu schema registry có compatibility mode, kiểm tra việc đăng ký schema mới bằng chính policy đó. Một tài liệu nói “tương thích” nhưng chưa được kiểm tra với serializer và consumer thực tế có thể tạo kỳ vọng sai.

## Checklist viết mô tả payload

Trước khi công bố event contract, hãy xác nhận:

1. Event type, schema version và envelope đã được xác định.
2. Mọi field payload đều có tên, wire type và ý nghĩa.
3. Required, optional, nullable và default được phân biệt.
4. Timestamp, currency, đơn vị và precision được ghi rõ.
5. Enum, collection và nested object có quy tắc cụ thể.
6. Nguồn có thẩm quyền và thời điểm snapshot được mô tả.
7. Có payload hợp lệ đầy đủ, tối thiểu và trường hợp lỗi.
8. Field nhạy cảm có privacy classification và consumer scope.
9. Quy tắc tương thích, deprecated field và replay được nêu.
10. Schema và ví dụ được validate bằng serializer thực tế.
11. Consumer có hướng dẫn xử lý unknown field và unknown enum.
12. Tài liệu được cập nhật cùng thay đổi schema trong cùng quy trình review.

Mô tả payload biến cấu trúc event thành một hợp đồng có thể hiểu và kiểm chứng. Khi field được giải thích bằng wire type, semantics, đơn vị, presence rule, nguồn dữ liệu và ví dụ; đồng thời schema, privacy và compatibility được duy trì cùng nhau, producer và consumer có thể tích hợp mà ít phải suy đoán.

## Tài liệu tham khảo

- Spring Modulith Reference — Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- CloudEvents Specification 1.0: https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md
- JSON Schema — Understanding JSON Schema: https://json-schema.org/understanding-json-schema/
- Apache Avro Specification: https://avro.apache.org/docs/current/specification/
- Protocol Buffers — Language Guide: https://protobuf.dev/programming-guides/proto3/
- RFC 3339 — Date and Time on the Internet: https://www.rfc-editor.org/rfc/rfc3339
