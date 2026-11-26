# Thay đổi tùy chọn

## Thay đổi tùy chọn trong event contract là gì?

Event contract là cấu trúc dữ liệu mà producer công bố và consumer sử dụng để hiểu một sự kiện. Theo thời gian, nghiệp vụ có thể cần thêm thông tin, chẳng hạn OrderConfirmed ban đầu chỉ có orderId và totalAmount, sau đó cần thêm deliveryNote hoặc promotionCode.

Một cách tiến hóa thường gặp là thêm field tùy chọn. Event cũ vẫn hợp lệ khi field mới chưa xuất hiện; event mới có thể mang giá trị bổ sung khi producer đã có dữ liệu. Nếu được thiết kế đúng, consumer cũ tiếp tục xử lý event mới và consumer mới vẫn đọc được event cũ.

Tính tương thích không đến từ việc field có chữ “optional” trong tên hoặc annotation. Nó phụ thuộc vào schema format, serializer/deserializer, validation rule và cách consumer xử lý trường hợp thiếu dữ liệu.

~~~mermaid
flowchart TD
    E1[Event schema v1] -->|Add optional field| E2[Event schema v2]
    P1[Old producer] -->|No new field| C2[New consumer]
    P2[New producer] -->|Field may be present| C1[Old consumer]
    P2 -->|Field present or absent| C2
    E2 --> V[Compatibility checks]
    V --> R[Safe rollout]
~~~

Ví dụ, schema mới bổ sung deliveryNote:

~~~json
{
  "eventId": "evt-100",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "orderId": "order-42",
  "totalAmount": "125000.00",
  "deliveryNote": "Giao tại quầy lễ tân"
}
~~~

Event v1 không có deliveryNote vẫn phải được consumer v2 xử lý. Event v2 có field mới cũng cần được consumer v1 đọc an toàn theo quy tắc unknown-field của serializer và schema validation.

## Phân biệt field tùy chọn, field nullable và field có default

Ba khái niệm này không đồng nghĩa:

| Khái niệm | Ý nghĩa |
|---|---|
| Optional / absent | Field có thể không xuất hiện trong payload |
| Nullable | Field có thể xuất hiện với giá trị null |
| Default | Consumer hoặc schema có quy tắc thay thế khi field không được cung cấp |

Một field có thể optional nhưng không nullable: nếu xuất hiện thì phải có giá trị hợp lệ. Một field có thể required nhưng nullable: key phải xuất hiện, giá trị có thể là null. Một default có thể được consumer áp dụng khi field vắng mặt, nhưng không nhất thiết được áp dụng khi field hiện diện với null.

Ví dụ:

~~~json
{
  "orderId": "order-42"
}
~~~

Field deliveryNote vắng mặt.

~~~json
{
  "orderId": "order-42",
  "deliveryNote": null
}
~~~

Field deliveryNote hiện diện nhưng có giá trị null.

~~~json
{
  "orderId": "order-42",
  "deliveryNote": "Giao tại quầy lễ tân"
}
~~~

Field hiện diện với một giá trị cụ thể.

Trước khi thêm field, producer và consumer cần thống nhất ý nghĩa của từng trường hợp. Ví dụ, thiếu deliveryNote có thể có nghĩa khách hàng không cung cấp ghi chú; null có thể biểu thị dữ liệu chưa được xác định. Nếu hai trạng thái không khác nhau về nghiệp vụ, nên chuẩn hóa chúng thành một quy tắc đơn giản.

Không dùng null để biểu thị nhiều ý nghĩa không liên quan như “không biết”, “không áp dụng”, “đã xóa” và “chưa được tải”. Nếu cần phân biệt, hãy dùng enum trạng thái hoặc cấu trúc dữ liệu rõ ràng.

## Khi nào thêm field tùy chọn là thay đổi tương thích?

Thêm field thường là additive change, nhưng chỉ tương thích khi cả producer và consumer xử lý được schema mới.

Điều kiện cần xem xét:

- Consumer cũ bỏ qua field chưa biết thay vì từ chối payload.
- Schema validator của consumer cũ cho phép additional properties hoặc đã được cập nhật tương ứng.
- Consumer mới chấp nhận event cũ không có field.
- Field mới không được dùng để thay đổi ý nghĩa của field hiện có.
- Giá trị mặc định khi thiếu field có ý nghĩa nghiệp vụ an toàn.
- Serializer giữ đúng kiểu dữ liệu và không tự biến đổi giá trị.
- Schema registry hoặc contract validation cho phép mức tương thích dự kiến.

Ví dụ thêm deliveryNote chỉ để hiển thị ghi chú giao hàng có thể tương thích. Nhưng nếu consumer mới dùng field đó để quyết định có cho phép xác nhận đơn hàng hay không, event cũ thiếu field có thể không còn đủ thông tin. Khi đó, thay đổi có thể làm thay đổi hành vi nghiệp vụ dù schema chỉ thêm một field.

Một thay đổi được xem là tương thích về cấu trúc chưa chắc tương thích về ngữ nghĩa. Luôn kiểm tra cả cách consumer sử dụng dữ liệu.

## Quy tắc thiết kế field tùy chọn

Field mới nên có mục đích rõ ràng và không làm thay đổi ý nghĩa dữ liệu đã công bố.

Nên:

- Chọn tên mô tả đúng ý nghĩa nghiệp vụ.
- Dùng kiểu dữ liệu ổn định, phù hợp với schema hiện tại.
- Định nghĩa rõ field có thể vắng mặt, null hay cả hai.
- Quy định cách consumer xử lý khi thiếu field.
- Không làm thay đổi ý nghĩa của field cũ.
- Không dùng field mới để âm thầm thay thế một field cũ.
- Cân nhắc độ nhạy cảm và quyền truy cập nếu field chứa dữ liệu mới.
- Ghi rõ thời điểm field được thêm và schema version áp dụng.

Tránh:

- Thêm field bắt buộc nhưng triển khai producer trước khi mọi consumer sẵn sàng.
- Dùng default khác nhau giữa các consumer.
- Dùng giá trị rỗng như chuỗi "" để thay cho absent mà không có quy tắc.
- Thay kiểu dữ liệu của field hiện tại trong cùng một thay đổi.
- Tái sử dụng tên field đã bị xóa cho một ý nghĩa mới.
- Đưa dữ liệu chỉ phục vụ một consumer vào event chung nếu nó làm lộ thông tin không cần thiết cho consumer khác.

## Định nghĩa schema JSON cho field tùy chọn

Trong JSON Schema, một property không nằm trong danh sách required là tùy chọn. Nếu muốn cho phép null, khai báo kiểu tương ứng.

Ví dụ deliveryNote tùy chọn nhưng nếu có thì phải là string:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "orderId": {
      "type": "string"
    },
    "deliveryNote": {
      "type": "string",
      "maxLength": 500
    }
  },
  "required": ["orderId"],
  "additionalProperties": true
}
~~~

Nếu field có thể là string hoặc null:

~~~json
{
  "type": ["string", "null"],
  "maxLength": 500
}
~~~

Trong JSON Schema hiện đại, default là annotation mô tả giá trị mặc định; validator không nhất thiết tự chèn giá trị đó vào payload. Consumer cần tự áp dụng default nếu hợp đồng yêu cầu.

Không nhầm việc additionalProperties true với việc consumer hiểu được field mới. Nó chỉ cho phép field không được liệt kê xuất hiện trong object. Consumer vẫn cần quyết định có đọc, lưu hoặc bỏ qua field đó.

Nếu schema dùng additionalProperties false, thêm field mới có thể khiến validator cũ từ chối event mới. Cần kiểm tra chính sách unknown field trước khi rollout producer.

## Biểu diễn field tùy chọn trong Java

Với Java record, có thể biểu diễn một field không bắt buộc bằng kiểu tham chiếu có thể null, kết hợp quy ước rõ ràng trong contract:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    BigDecimal totalAmount,
    String deliveryNote
) {}
~~~

Khi deserialize event cũ không có deliveryNote, serializer cần có cấu hình phù hợp để tạo giá trị null hoặc default đã quy định. Hãy kiểm tra chính xác hành vi của Jackson, JSON-B hoặc serializer đang dùng.

Không mặc định rằng Optional<String> là lựa chọn tốt nhất cho mọi event DTO. Hỗ trợ serialize/deserialize Optional phụ thuộc thư viện và module cấu hình; Optional trong payload cũng có thể tạo biểu diễn JSON không mong muốn. Nếu dùng Optional, hãy xác nhận contract JSON và test round-trip.

Nếu cần phân biệt absent với explicit null, kiểu nullable đơn giản không đủ. Có thể dùng wrapper presence, JsonNode/JsonNullable hoặc một cấu trúc có trạng thái rõ ràng. Chọn cách biểu diễn nhất quán cho toàn bộ producer và consumer.

Ví dụ một accessor áp dụng default ở lớp consumer:

~~~java
public String effectiveDeliveryNote(OrderConfirmed event) {
    return event.deliveryNote() == null
        ? "Không có ghi chú giao hàng"
        : event.deliveryNote();
}
~~~

Default trong ví dụ là quy tắc hiển thị của consumer. Không tự ghi ngược chuỗi mặc định vào event gốc vì điều đó làm thay đổi dữ liệu được producer công bố.

## Default phải được định nghĩa ở đâu?

Một default có thể được áp dụng ở nhiều lớp:

| Vị trí | Trách nhiệm |
|---|---|
| Producer | Phát giá trị đã chuẩn hóa khi nghiệp vụ có default thực sự |
| Schema | Mô tả default hoặc quy tắc đọc tùy schema format |
| Deserializer | Chuyển dữ liệu thiếu thành giá trị theo cấu hình |
| Consumer | Áp dụng fallback cho use case cụ thể |
| Domain model | Quyết định giá trị nghiệp vụ theo quy tắc của module sở hữu |

Tránh để mỗi consumer tự chọn một default nghiệp vụ khác nhau. Nếu default ảnh hưởng đến trạng thái nghiệp vụ, nên thuộc module sở hữu dữ liệu hoặc được quy định trong event contract.

Ví dụ, thiếu deliveryNote có thể chỉ là “không có ghi chú” và consumer hiển thị chuỗi thân thiện. Nhưng thiếu currency trong event PaymentCaptured không nên tự động mặc định VND nếu producer có thể phát nhiều loại tiền. Default sai có thể gây sai số tài chính.

Nếu default thay đổi theo thời gian, hãy xác định default được áp dụng tại thời điểm producer tạo event hay tại thời điểm consumer đọc event. Với event lịch sử, consumer áp dụng default mới có thể làm thay đổi cách diễn giải dữ liệu cũ.

## Schema evolution với Avro, Protobuf và JSON

Mỗi schema format có quy tắc tương thích riêng. Không thể lấy quy tắc của JSON áp dụng nguyên trạng cho Avro hoặc Protobuf.

| Định dạng | Lưu ý khi thêm field tùy chọn |
|---|---|
| JSON / JSON Schema | Property không required có thể vắng mặt; unknown-field policy của consumer quyết định có chấp nhận field mới không |
| Avro | Khi reader schema mới đọc dữ liệu writer schema cũ, field mới cần default để reader tạo giá trị cho field chưa có trong dữ liệu cũ |
| Protocol Buffers | Thêm field mới với field number chưa dùng; giữ nguyên field number/type của field cũ và không tái sử dụng số đã xóa |
| CloudEvents envelope | Extension attribute cần tuân thủ quy tắc tên và cách consumer bỏ qua thuộc tính chưa biết theo profile đã chọn |

Với Avro, default có ý nghĩa trong quá trình schema resolution. Nó không đồng nghĩa producer tự động ghi field đó vào mọi record mới.

Với Protobuf, field mới thường có thể được thêm tương thích nếu dùng field number mới và tuân thủ quy tắc wire compatibility. Khi xóa field, nên reserve field number và tên để tránh tái sử dụng gây diễn giải sai dữ liệu cũ.

Với JSON, một consumer dùng strict schema có thể từ chối property mới. Cần test serializer/deserializer thực tế, không chỉ đọc file schema.

## Consumer mới phải đọc được event cũ

Consumer mới thường được triển khai sau khi event đã tồn tại trong broker, retry queue hoặc archive. Vì vậy, nó có thể nhận event được tạo từ schema cũ trong nhiều ngày hoặc nhiều tháng.

Khi thêm field tùy chọn, consumer mới cần:
- Xử lý event thiếu field.
- Áp dụng fallback đã được quy định.
- Không giả định schemaVersion mới luôn xuất hiện.
- Giữ khả năng deserialize event từ retry/DLQ.
- Xử lý null và absent đúng semantics.
- Không làm hỏng dữ liệu khi lưu lại projection hoặc archive.

Ví dụ consumer:

~~~java
public void on(OrderConfirmed event) {
    String note = event.deliveryNote();

    if (note == null) {
        note = "Không có ghi chú giao hàng";
    }

    shipmentService.prepare(
        event.orderId(),
        note
    );
}
~~~

Đây chỉ là fallback minh họa. Nếu thiếu deliveryNote có ý nghĩa khác với “không có ghi chú”, hãy dùng trạng thái tường minh thay vì gộp chúng.

## Producer mới phải tương thích với consumer cũ

Producer mới có thể bắt đầu gửi field tùy chọn trong khi một số consumer cũ chưa được nâng cấp. Có hai chiến lược:

1. Consumer cũ bỏ qua unknown field và tiếp tục xử lý.
2. Triển khai consumer hỗ trợ schema mới trước, sau đó mới cho producer phát field.

Chiến lược thứ nhất chỉ an toàn nếu serializer/deserializer và validation của consumer cũ thật sự cho phép unknown field. Không suy luận điều này chỉ từ việc consumer dùng JSON.

Với strict schema hoặc generated model, cần nâng cấp consumer trước. Trong giai đoạn chuyển tiếp, producer có thể chỉ phát field khi đã xác nhận consumer đã sẵn sàng, hoặc dùng versioned topic/contract nếu không thể triển khai đồng thời.

Không để producer gửi field mới làm thay đổi logic bắt buộc của consumer cũ. Nếu consumer cũ cần field để xử lý đúng, thay đổi đó không còn là optional additive change đối với consumer ấy.

## Trình tự rollout an toàn

Một trình tự triển khai thường dùng:

~~~mermaid
flowchart TD
    A[Publish schema v2 as compatible] --> B[Deploy consumers tolerant of absent field]
    B --> C[Verify old and new events are accepted]
    C --> D[Deploy producer capable of emitting optional field]
    D --> E[Enable field emission gradually]
    E --> F[Observe deserialize and business errors]
    F --> G[Retain old-field fallback for replay window]
~~~

Các bước cụ thể:

1. Cập nhật event contract và schema registry theo compatibility mode đã chọn.
2. Nâng cấp consumer để chấp nhận event cũ và hiểu field mới nếu có.
3. Kiểm thử với cả payload v1 và v2.
4. Triển khai consumer trước nếu consumer cũ không chấp nhận unknown field.
5. Triển khai producer có khả năng phát field nhưng ban đầu có thể chưa bật.
6. Bật phát field theo cấu hình hoặc rollout có kiểm soát.
7. Theo dõi lỗi deserialize, validation, retry và business behavior.
8. Giữ fallback đủ lâu để xử lý backlog, retry và replay event cũ.

Không xóa ngay code xử lý event cũ sau khi producer mới đã rollout. Broker retention, DLQ, archive và quy trình replay có thể khiến event cũ quay lại sau thời gian dài.

## Thay đổi tùy chọn nhưng không làm thay đổi ngữ nghĩa

Một field mới có thể làm consumer hiểu event theo cách khác dù cấu trúc vẫn tương thích.

Ví dụ, priority được thêm để tối ưu thứ tự xử lý. Nếu consumer cũ bỏ qua field và xử lý FIFO, consumer mới ưu tiên HIGH trước, hệ thống có thể có hành vi khác giữa hai nhóm consumer trong thời gian rollout.

Hãy xác định:
- Field mới chỉ cung cấp thông tin bổ sung hay thay đổi quyết định nghiệp vụ?
- Consumer không hiểu field có thể tiếp tục an toàn không?
- Default khi thiếu field có tạo ra kết quả tương đương với hành vi cũ không?
- Hai phiên bản consumer chạy song song có thể tạo kết quả khác nhau không?
- Field có ảnh hưởng tới authorization, tài chính hoặc trạng thái không thể đảo ngược không?

Nếu field mới thay đổi quy tắc nghiệp vụ, có thể cần event type mới hoặc một workflow migration rõ ràng thay vì chỉ thêm optional field.

## Khi nào nên dùng event version mới?

Không phải mọi thay đổi đều cần tăng event type version. Additive optional field có thể giữ cùng event type nếu contract và schema registry hỗ trợ compatibility.

Cân nhắc version mới khi:
- Thay đổi ý nghĩa của field hiện có.
- Thay kiểu dữ liệu không tương thích.
- Đổi đơn vị đo hoặc currency semantics.
- Tách/gộp field khiến consumer cũ không thể diễn giải đúng.
- Thay đổi required/optional làm payload cũ không hợp lệ.
- Thay đổi hành vi nghiệp vụ mà consumer cần phân biệt.

Có thể dùng schemaVersion trong envelope để xác định phiên bản schema. Tuy nhiên, schemaVersion không thay thế schema registry hoặc contract documentation. Consumer vẫn cần biết quy tắc chuyển đổi và compatibility.

Tránh tạo version mới cho mọi field bổ sung nhỏ nếu schema format hỗ trợ tiến hóa tương thích. Quá nhiều event type/version làm tăng chi phí vận hành và số nhánh consumer cần duy trì.

## Không xóa hoặc tái sử dụng field tùy tiện

Xóa field có thể phá consumer cũ còn đang đọc nó. Tái sử dụng tên field cho một ý nghĩa mới nguy hiểm hơn vì consumer cũ vẫn parse được nhưng diễn giải sai.

Khi field không còn cần thiết:
1. Ngừng producer phát giá trị mới nhưng tiếp tục giữ field trong schema.
2. Chuyển consumer sang không phụ thuộc field.
3. Theo dõi usage và xác nhận không còn consumer cần field.
4. Chờ hết thời gian retention/replay hoặc xử lý event lịch sử theo policy.
5. Chỉ xóa field trong một thay đổi có version/compatibility plan phù hợp.
6. Với Protobuf, reserve field number và tên đã xóa.

Không dùng lại tên deliveryNote cho deliveryInstructionsCode nếu ý nghĩa và kiểu dữ liệu đã thay đổi. Hãy tạo field mới hoặc version contract mới.

## Validation và bảo vệ dữ liệu tùy chọn

Field tùy chọn vẫn cần validation khi xuất hiện:

- Giới hạn độ dài chuỗi.
- Kiểm tra định dạng và miền giá trị.
- Kiểm tra enum nằm trong tập được hỗ trợ.
- Kiểm tra tenant/ownership nếu field tham chiếu dữ liệu khác.
- Giới hạn kích thước payload tổng thể.
- Xử lý ký tự Unicode và normalization theo hợp đồng.
- Không tin field chỉ vì producer nội bộ đã phát nó.

Consumer cần quyết định xử lý giá trị không hợp lệ như thế nào: reject, quarantine, dead-letter hay bỏ qua field nếu contract cho phép. Không silently coerce giá trị sai thành default nếu điều đó che giấu lỗi producer.

Nếu field mới chứa thông tin cá nhân hoặc bí mật, đánh giá lại quyền truy cập của mọi consumer đang nhận event. Thêm field vào event chung có thể làm mở rộng phạm vi dữ liệu được chia sẻ.

## Kiểm thử compatibility cho thay đổi tùy chọn

Mỗi thay đổi schema nên có test ở cả hai chiều tương thích:

| Producer | Consumer | Điều cần xác nhận |
|---|---|---|
| v1, không có field | v2 | Consumer mới dùng fallback đúng |
| v2, field vắng mặt | v2 | Không phát sinh lỗi validation |
| v2, field null | v2 | Xử lý theo semantics null đã công bố |
| v2, field có giá trị | v2 | Giá trị được deserialize và dùng đúng |
| v2, field có giá trị | v1 | Consumer cũ bỏ qua unknown field hoặc được nâng cấp trước |
| v1 event từ archive/DLQ | consumer hiện tại | Replay vẫn xử lý được |
| v2 payload sai kiểu | consumer hiện tại | Validation từ chối rõ ràng |
| v2 field quá dài | consumer hiện tại | Giới hạn được thực thi |
| schema registry compatibility | producer mới | Đăng ký schema được chấp nhận theo policy |

Test nên dùng payload mẫu thực tế được lưu cùng contract, không chỉ tạo object Java rồi serialize ngược bằng cùng một phiên bản model. Payload v1 cố định giúp phát hiện consumer mới không còn đọc được dữ liệu cũ.

Có thể bổ sung contract test giữa producer và consumer, schema compatibility test trong pipeline và integration test với serializer thực tế. Nếu dùng Avro/Protobuf, kiểm tra writer schema cũ với reader schema mới theo đúng thư viện.

## Quan sát sau khi rollout

Sau khi bật field mới, theo dõi:

- Tỷ lệ event có field mới và không có field.
- Lỗi deserialize/validation theo schema version.
- Tỷ lệ consumer fallback do field vắng mặt.
- Retry và dead-letter tăng bất thường.
- Khác biệt kết quả nghiệp vụ giữa consumer version.
- Số event cũ còn trong backlog hoặc archive.
- Consumer nào vẫn dùng contract cũ nếu có telemetry.

Không đưa event ID hoặc order ID làm metric label. Dùng schema version, event type, producer version và consumer version làm nhóm metric có cardinality giới hạn; event ID phù hợp với log/trace.

Nếu field mới được bật theo feature flag, log trạng thái rollout và thời điểm thay đổi để liên kết với lỗi phát sinh.

## Tích hợp với Spring Modulith

Spring Modulith tổ chức event contract giữa các module thông qua application event và cơ chế externalization. Khi thay đổi event class, hãy xem xét cả listener nội bộ lẫn adapter gửi event ra broker.

Một event record có thể được mở rộng:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    BigDecimal totalAmount,
    String deliveryNote
) {}
~~~

Khi thêm component vào record, code tạo event, constructor call, test fixture, serializer và listener đều có thể cần cập nhật. Nếu event được lưu trong Event Publication Registry hoặc outbox, cần xác nhận cách serializer đọc các payload cũ còn tồn tại.

Các điểm cần kiểm tra:
- Listener nội bộ có chấp nhận giá trị thiếu không.
- @ApplicationModuleListener có xử lý đúng event được deserialize từ persistence hay không.
- Externalization adapter có giữ schemaVersion và field tùy chọn theo contract không.
- Event Publication Registry chỉ theo dõi publication; nó không tự giải quyết schema evolution.
- Retry/resubmission có thể xử lý event được tạo từ phiên bản ứng dụng cũ.
- Module API không bị thay đổi ngoài ý muốn khi event class là kiểu dùng chung.

Nếu event class được chia sẻ trực tiếp giữa module, giữ ranh giới bằng contract được công bố và tránh để consumer phụ thuộc vào chi tiết nội bộ của producer.

## Quy trình thêm một field tùy chọn

Khi cần thêm field vào event, thực hiện theo thứ tự:

1. Xác định ý nghĩa nghiệp vụ của absent, null và giá trị cụ thể.
2. Chọn kiểu dữ liệu và quy tắc validation.
3. Kiểm tra schema format và unknown-field policy của consumer cũ.
4. Định nghĩa default tại đúng lớp chịu trách nhiệm.
5. Cập nhật schema/contract và kiểm tra compatibility.
6. Nâng cấp consumer để đọc cả event cũ lẫn event mới.
7. Kiểm thử payload cũ, field vắng mặt, null và field có giá trị.
8. Triển khai producer có khả năng phát field mới.
9. Bật field theo rollout có kiểm soát.
10. Theo dõi fallback, deserialize error, retry và DLQ.
11. Giữ khả năng đọc event cũ trong suốt thời gian retention/replay.
12. Chỉ xóa hoặc thay field cũ sau một kế hoạch migration riêng.

Thay đổi tùy chọn giúp event contract phát triển theo hướng additive mà không buộc mọi producer và consumer nâng cấp cùng lúc. Khi semantics của absent/null/default được định nghĩa rõ, consumer mới đọc được event cũ, consumer cũ chấp nhận field mới và rollout được kiểm thử hai chiều, hệ thống có thể tiến hóa schema an toàn hơn.

## Tài liệu tham khảo

- Spring Modulith Reference — Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- Apache Avro Specification — Schema Resolution: https://avro.apache.org/docs/current/specification/
- Protocol Buffers — Updating a Message Type: https://protobuf.dev/programming-guides/proto3/#updating
- JSON Schema — Annotations and Properties: https://json-schema.org/understanding-json-schema/reference/annotations
- RFC 8785 — JSON Canonicalization Scheme: https://www.rfc-editor.org/rfc/rfc8785
