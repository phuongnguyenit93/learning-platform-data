# Hợp đồng sự kiện, schema và tương thích khi tiến hóa

## 1. Vì sao event cần một hợp đồng rõ ràng?

Trong kiến trúc hướng sự kiện (event-driven architecture), các dịch vụ trao đổi thông tin bằng những sự kiện như BookingConfirmed, PaymentCaptured hoặc InventoryChanged. Producer có thể được triển khai và phát hành độc lập với consumer; một sự kiện còn có thể được nhiều consumer sử dụng cho thông báo, tìm kiếm, phân tích hoặc tích hợp đối tác. Sự độc lập này chỉ bền vững khi các bên **hiểu cùng một ý nghĩa và cùng một cấu trúc dữ liệu**.

Nếu producer đổi tên field, đổi đơn vị tiền tệ hoặc thay ý nghĩa trạng thái mà không báo trước, consumer cũ có thể đọc sai dữ liệu, bỏ qua sự kiện hoặc ngừng xử lý. Hậu quả không dừng ở lỗi parse: hệ thống có thể gửi thông báo sai, cập nhật tồn kho sai hoặc tính doanh thu không chính xác.

**Hợp đồng sự kiện (event contract)** mô tả điều mà producer cam kết phát và consumer được phép dựa vào: ý nghĩa sự kiện, cấu trúc envelope/payload, kiểu và ràng buộc dữ liệu, quy tắc thời gian, danh tính, thứ tự, phiên bản, quyền truy cập và chính sách tương thích. **Schema** mô tả cấu trúc và một phần quy tắc kiểm tra dữ liệu của hợp đồng; schema hợp lệ về cú pháp chưa chắc đã diễn đạt đúng nghiệp vụ.

Trong module **CLOUD_ARCHITECTURE**, thiết kế event contract liên quan trực tiếp đến lựa chọn mạng, compute, lưu trữ, broker và mô hình triển khai. Cần cân bằng **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và khả năng vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: nền tảng đặt chỗ phát sự kiện xác nhận booking cho notification service, search indexer, analytics và một hệ thống đối tác. Producer và các consumer có lịch phát hành khác nhau; message có thể được lưu, phát lại sau nhiều ngày và consumer mới có thể được đưa vào trong khi consumer cũ vẫn đang chạy.

## 2. Phân biệt event, command, notification và schema

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Event** | Điều gì đã xảy ra? | BookingConfirmed |
| **Command** | Một thành phần được yêu cầu làm gì? | ConfirmBooking |
| **Notification** | Ai cần biết một sự kiện đã xảy ra? | Gửi email khi booking được xác nhận |
| **Event contract** | Producer cam kết ý nghĩa và dữ liệu nào? | BookingConfirmed v1, điều kiện phát và định nghĩa field |
| **Schema** | Message có cấu trúc, kiểu và ràng buộc nào? | bookingId là string không rỗng, occurredAt là timestamp |
| **Schema registry** | Schema nào đã đăng ký, phiên bản nào hợp lệ và tương thích? | Registry lưu schema ID, version và compatibility policy |

Tên event nên mô tả một sự thật nghiệp vụ đã xảy ra, thường dùng quá khứ hoặc trạng thái hoàn tất. BookingConfirmed không đồng nghĩa với yêu cầu xác nhận. Producer chỉ nên phát event sau khi điều kiện nghiệp vụ được đáp ứng theo hợp đồng đã thống nhất.

### 2.1. Event là dữ liệu lịch sử, không phải bản sao tùy tiện của database

Event nên mô tả sự kiện có ý nghĩa đối với consumer. Không nên tự động serialize toàn bộ entity/database row vào message. Cấu trúc nội bộ thường thay đổi nhanh và có thể chứa dữ liệu nhạy cảm không cần thiết.

Ví dụ event BookingConfirmed có thể cung cấp bookingId, customerRef, propertyId, thời điểm xác nhận, currency và tổng tiền đã xác nhận. Nó không nhất thiết phải chứa mật khẩu, token, địa chỉ thanh toán đầy đủ hay toàn bộ lịch sử thao tác của khách.

Hợp đồng tốt giúp consumer biết **được phép dựa vào điều gì**, và đồng thời nêu những điều consumer không nên giả định. Ví dụ, không được suy ra event luôn đến đúng thứ tự thời gian chỉ vì producer tạo chúng theo thứ tự.

## 3. Cấu trúc hợp đồng: envelope và payload

Một message thường được chia thành:

- **Envelope/metadata:** thông tin phục vụ định tuyến, truy vết, quản trị phiên bản và diễn giải message.
- **Payload/data:** nội dung nghiệp vụ mà event muốn truyền tải.

Ví dụ minh họa:

~~~json
{
  "specVersion": "1.0",
  "id": "evt-7f21a9",
  "type": "com.example.booking.confirmed",
  "source": "booking-service",
  "subject": "bookings/booking-42",
  "time": "2026-12-18T08:30:00Z",
  "schemaVersion": 1,
  "correlationId": "req-51bc",
  "dataContentType": "application/json",
  "data": {
    "bookingId": "booking-42",
    "customerRef": "customer-18",
    "propertyId": "property-91",
    "confirmedAt": "2026-12-18T08:29:58Z",
    "currency": "VND",
    "totalAmountMinor": 125000000
  }
}
~~~

Các tên trường trên chỉ là một thiết kế minh họa, không phải schema tiêu chuẩn bắt buộc. Một số hệ thống dùng CloudEvents hoặc format envelope riêng. Nếu dùng chuẩn envelope, cần tuân theo semantics của chuẩn và bổ sung extension một cách có kiểm soát, tránh tạo hai nguồn metadata mâu thuẫn.

### 3.1. Các trường metadata nên cân nhắc

| Trường | Mục đích | Quy tắc cần thống nhất |
| --- | --- | --- |
| id/eventId | Định danh duy nhất của một lần phát event | Phạm vi duy nhất, cách giữ ổn định khi retry, thời gian lưu để deduplicate |
| type/eventType | Tên loại event | Quy ước namespace, tên ổn định, không tái sử dụng tên với ý nghĩa khác |
| source/producer | Hệ thống phát event | Danh tính producer có thể xác minh, không chỉ là chuỗi tự khai |
| subject/aggregateId | Đối tượng nghiệp vụ liên quan | Quy tắc định danh và phân vùng |
| time/occurredAt | Thời điểm sự kiện xảy ra | Múi giờ, độ chính xác, nguồn thời gian |
| schemaVersion | Phiên bản payload contract | Phạm vi version: theo event type hay schema ID |
| correlationId | Liên kết nhiều bước trong một hành trình | Truyền xuyên request, event, consumer và workflow |
| causationId | Chỉ ra message hoặc thao tác gây ra event hiện tại | Hữu ích để truy vết chuỗi nhân quả |
| trace context | Liên kết với distributed tracing | Quy tắc truyền context qua broker, không lộ dữ liệu nhạy cảm |
| tenantId | Định tuyến và cách ly khách hàng trong hệ đa tenant | Xác minh nguồn, quyền truy cập và khả năng phân vùng |

Không phải mọi event đều cần tất cả trường. Mỗi trường cần định nghĩa rõ kiểu, tính bắt buộc, ngữ nghĩa, cách tạo, cách xác minh và chính sách bảo vệ. Nếu có cả time của envelope và timestamp trong payload, phải giải thích chúng khác nhau thế nào, chẳng hạn thời điểm event được phát so với thời điểm giao dịch được xác nhận.

### 3.2. Thiết kế payload theo ngữ nghĩa nghiệp vụ

Field cần mô tả đủ rõ để consumer không tự đoán:

- Số tiền là đơn vị nhỏ nhất hay số thập phân? Currency theo chuẩn nào? Phí và thuế đã nằm trong tổng chưa?
- Timestamp là thời điểm xảy ra, thời điểm ghi vào database hay thời điểm publisher phát?
- Status là trạng thái tại thời điểm event hay trạng thái hiện tại có thể thay đổi sau đó?
- ID là định danh nội bộ, public ID hay định danh được phép chia sẻ cho đối tác?
- Field optional có thể vắng mặt, null hay chuỗi rỗng? Ba trường hợp này có cùng ý nghĩa không?

Ví dụ tên totalAmount không cho biết đơn vị hoặc currency. Một hợp đồng rõ có thể quy định totalAmountMinor là số nguyên tính theo đơn vị nhỏ nhất của currency và currency là mã tiền tệ đã thống nhất. Cần bảo đảm cách biểu diễn đó phù hợp với mọi currency/precision mà sản phẩm hỗ trợ; không nên mặc định mọi loại tiền đều có hai chữ số thập phân.

## 4. Định nghĩa schema và validation

Schema mô tả cấu trúc message dưới dạng máy có thể kiểm tra. Tùy công nghệ, tổ chức có thể dùng JSON Schema, Avro, Protocol Buffers hoặc format khác. Các hệ thống cũng có thể dùng schema registry để quản lý version và ngăn producer phát dữ liệu không tuân thủ policy.

### 4.1. JSON Schema

Ví dụ schema đơn giản cho payload BookingConfirmed:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.invalid/booking-confirmed-v1.json",
  "title": "BookingConfirmed",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "bookingId",
    "confirmedAt",
    "currency",
    "totalAmountMinor"
  ],
  "properties": {
    "bookingId": {
      "type": "string",
      "minLength": 1
    },
    "confirmedAt": {
      "type": "string",
      "format": "date-time"
    },
    "currency": {
      "type": "string",
      "pattern": "^[A-Z]{3}$"
    },
    "totalAmountMinor": {
      "type": "integer",
      "minimum": 0
    },
    "customerRef": {
      "type": "string"
    }
  }
}
~~~

Schema minh họa giúp kiểm tra loại dữ liệu, trường bắt buộc và một số ràng buộc. Trong triển khai thật cần chọn JSON Schema draft phù hợp với validator, xác định cách xử lý format, additionalProperties, nullability và tương thích giữa phiên bản. Pattern ba ký tự không tự chứng minh đó là mã currency được nghiệp vụ hỗ trợ; validation nghiệp vụ vẫn cần thêm.

### 4.2. Avro

Avro biểu diễn schema dưới dạng JSON và thường được dùng trong hệ thống event/streaming. Reader và writer có thể dùng schema ID hoặc cơ chế schema resolution để diễn giải dữ liệu theo quy tắc của Avro. Khi thêm field có default, reader cũ/mới có thể giải quyết khác nhau tùy writer schema và reader schema.

Ví dụ một record đơn giản:

~~~json
{
  "type": "record",
  "name": "BookingConfirmed",
  "namespace": "com.example.booking",
  "fields": [
    {"name": "bookingId", "type": "string"},
    {"name": "confirmedAt", "type": "string"},
    {"name": "currency", "type": "string"},
    {"name": "totalAmountMinor", "type": "long"}
  ]
}
~~~

Với Avro, kiểu số có ý nghĩa về khả năng biểu diễn và schema resolution; không nên thay đổi int/long hoặc union type chỉ để làm code producer thuận tiện mà chưa kiểm tra consumer cũ.

### 4.3. Protocol Buffers

Protocol Buffers dùng message definition và field number ổn định. Ví dụ:

~~~protobuf
syntax = "proto3";

message BookingConfirmed {
  string booking_id = 1;
  string confirmed_at = 2;
  string currency = 3;
  int64 total_amount_minor = 4;
}
~~~

Field number là một phần của wire contract. **Không tái sử dụng field number đã xóa** cho field khác; nên reserve số và tên cũ nếu schema format hỗ trợ. Thay đổi kiểu hoặc cách biểu diễn có thể phá tương thích ngay cả khi tên field không đổi.

### 4.4. So sánh các lựa chọn

| Định dạng | Điểm mạnh | Điều cần cân nhắc |
| --- | --- | --- |
| JSON / JSON Schema | Dễ đọc, dễ tích hợp HTTP và nhiều ngôn ngữ; validation rõ | Payload thường lớn hơn binary; quy tắc null/unknown field và draft validator phải thống nhất |
| Avro | Schema resolution phù hợp cho data pipeline/event; hỗ trợ reader/writer schema | Cần quản lý schema ID, default và tương thích theo đúng semantics Avro |
| Protocol Buffers | Binary gọn, hiệu quả; field number hỗ trợ evolution có quy tắc | Cần quản lý field number, reserved field và generated code; không đọc trực tiếp dễ như JSON |
| XML/XSD | Hữu ích trong một số tích hợp doanh nghiệp và hệ thống legacy | Verbose, phức tạp namespace và tooling; phải quản lý schema/version rõ |

Không có định dạng tốt nhất cho mọi hệ thống. Chọn theo broker, ngôn ngữ, throughput, khả năng kiểm tra, tích hợp đối tác, yêu cầu lưu trữ và năng lực đội ngũ. Quan trọng hơn định dạng là **quy tắc contract và quy trình tiến hóa được thực thi nhất quán**.

## 5. Tương thích schema: backward, forward và full

Tương thích (compatibility) mô tả khả năng các phiên bản producer/consumer khác nhau trao đổi dữ liệu an toàn. Các thuật ngữ có thể được registry định nghĩa theo chiều writer/reader cụ thể; phải đọc đúng semantics của registry và format.

### 5.1. Backward compatibility

Một schema mới tương thích backward khi consumer/reader mới có thể đọc dữ liệu được ghi theo schema cũ trong phạm vi quy tắc được hỗ trợ. Ví dụ thêm một field optional với default phù hợp có thể tương thích backward theo một số format và registry.

### 5.2. Forward compatibility

Một schema mới tương thích forward khi consumer/reader cũ có thể đọc dữ liệu được ghi theo schema mới. Điều này thường đòi hỏi reader cũ bỏ qua field mới hoặc format hỗ trợ cơ chế tương ứng. Nếu reader cũ từ chối mọi field chưa biết, thêm field mới có thể phá forward compatibility.

### 5.3. Full compatibility

Full compatibility kết hợp cả backward và forward trong mô hình kiểm tra của registry: phiên bản mới và cũ có thể được đọc qua lại theo chiều đã quy định. Full compatibility không đồng nghĩa mọi thay đổi nghiệp vụ đều an toàn; một field vẫn giữ string nhưng đổi ý nghĩa từ "số tiền trước thuế" sang "số tiền sau thuế" vẫn có thể khiến consumer tính sai.

### 5.4. Compatibility theo phiên bản liền kề và toàn bộ lịch sử

Một số registry cho phép kiểm tra tương thích với **phiên bản trước gần nhất** (backward/forward/full), hoặc với **mọi phiên bản trước đó** (transitive modes). Kiểm tra transitive chặt hơn trong các luồng có message cũ lưu lâu và consumer có thể replay lịch sử nhiều năm.

| Chế độ khái niệm | Kiểm tra với | Khi nào cần cân nhắc |
| --- | --- | --- |
| Backward | Reader mới với dữ liệu writer cũ | Consumer mới sẽ đọc message đã tồn tại |
| Backward transitive | Reader mới với mọi schema cũ trong phạm vi | Có replay dài hạn hoặc nhiều thế hệ producer |
| Forward | Reader cũ với dữ liệu writer mới | Producer mới được phát hành trước consumer |
| Forward transitive | Reader cũ với tất cả schema mới theo policy | Consumer cũ cần tiếp tục đọc message từ nhiều phiên bản producer |
| Full | Hai chiều giữa schema cũ và mới gần nhất | Producer/consumer được rollout độc lập |
| Full transitive | Hai chiều với toàn lịch sử schema theo policy | Cần khả năng tương thích xuyên nhiều phiên bản lưu trữ |

Đây là mô tả khái niệm. Tên mode và cách thực thi khác nhau giữa registry; một số hệ thống còn có policy khác hoặc kiểm tra tương thích theo format. Không được chọn mode chỉ dựa vào tên gọi mà không xem **ai là writer, ai là reader, message cũ được giữ bao lâu và có replay không**.

## 6. Thay đổi nào thường an toàn, thay đổi nào có nguy cơ?

| Thay đổi schema/contract | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Thêm field optional với default rõ ràng | Có thể an toàn nếu consumer cũ bỏ qua field mới và format hỗ trợ | Kiểm tra compatibility trong registry và test consumer cũ |
| Thêm field bắt buộc không có default | Consumer/reader cũ có thể không hiểu hoặc writer cũ không cung cấp | Thêm optional trước, rollout theo giai đoạn, chỉ bắt buộc sau khi đủ consumer |
| Xóa field đang dùng | Consumer hiện tại hoặc replay lịch sử có thể lỗi | Deprecate, đo usage, migrate consumer, rồi mới ngừng phát |
| Đổi tên field | Reader cũ không tìm thấy field | Thêm field mới song song, dual-read/dual-write có thời hạn, rồi deprecate field cũ |
| Đổi kiểu dữ liệu | Có thể lỗi parse hoặc mất độ chính xác | Dùng field mới và chuyển đổi tường minh; không ép cast ngầm |
| Đổi đơn vị hoặc semantics nhưng giữ tên/kiểu | Nguy cơ dữ liệu hợp lệ về schema nhưng sai nghiệp vụ | Coi là breaking change; version/type mới hoặc field mới với định nghĩa khác |
| Thu hẹp enum | Consumer gặp giá trị mới không được phép | Consumer phải có chiến lược unknown value; thêm giá trị theo compatibility policy |
| Thêm giá trị enum | Consumer dùng exhaustive switch có thể lỗi | Test consumer cũ, có nhánh unknown/other |
| Đổi ý nghĩa null/default | Dữ liệu cũ và mới bị diễn giải khác | Định nghĩa rõ absent/null/default và versioning khi semantics thay đổi |
| Thay đổi partition key | Có thể đổi ordering và phân bố tải | Đánh giá lại ordering, hot partition và chiến lược migration |

### 6.1. Ví dụ: thêm customer tier

Phiên bản cũ chỉ có bookingId và confirmedAt. Phiên bản mới muốn thêm customerTier để consumer analytics phân loại báo cáo:

~~~json
{
  "bookingId": "booking-42",
  "confirmedAt": "2026-12-18T08:29:58Z",
  "customerTier": "gold"
}
~~~

Nếu consumer cũ bỏ qua field không biết và format/schema policy cho phép, đây có thể là thay đổi không phá tương thích với consumer cũ. Nhưng cần xác định giá trị customerTier có thể vắng mặt không, enum có được mở rộng không, dữ liệu phân loại có phải PII hay không và consumer mới xử lý event lịch sử thiếu field này ra sao.

### 6.2. Đừng giả định unknown enum value không bao giờ xuất hiện

Consumer có thể nhận một trạng thái mới do producer triển khai trước. Hãy thiết kế logic theo nguyên tắc:

- Biết rõ nhóm trạng thái có thể xử lý.
- Không silently coi mọi giá trị lạ là trạng thái thành công.
- Ghi metric/log an toàn khi gặp giá trị chưa biết.
- Có cách quarantine hoặc xử lý theo chính sách nghiệp vụ, không làm mất message âm thầm.

## 7. Versioning: thay đổi hợp đồng có kiểm soát

Có nhiều cách versioning; lựa chọn cần nhất quán trong toàn bộ hệ sinh thái:

### 7.1. Version trong tên event

Ví dụ BookingConfirmed.v1 và BookingConfirmed.v2. Cách này làm rõ đây là hai contract khác nhau, thuận tiện để tồn tại song song khi thay đổi không tương thích. Đổi lại, routing, topic, dashboard, consumer và governance phải quản lý nhiều type hơn.

### 7.2. Version trong metadata/schema registry

Tên event vẫn ổn định, schema ID hoặc schemaVersion xác định cách diễn giải payload. Cách này phù hợp khi format/registry hỗ trợ schema resolution và consumer được thiết kế đọc nhiều version. Tuy nhiên, metadata version không tự sửa được thay đổi semantics.

### 7.3. Version trong payload

Một field version trong payload giúp consumer phân biệt cấu trúc nhưng cần quy tắc rõ để không tạo nhiều nhánh logic vô hạn. Tránh vừa version trong event name, vừa schema ID, vừa payload version mà không xác định cái nào là nguồn sự thật.

### 7.4. Không version chỉ vì thêm một field

Nếu thay đổi thực sự tương thích theo contract và policy của hệ thống, có thể không cần phát event type mới. Ngược lại, đổi ngữ nghĩa, đơn vị, nguồn sự thật hoặc mô hình trạng thái là thay đổi có thể phá consumer dù schema cú pháp không đổi. Quyết định version phải dựa vào **ngữ nghĩa và khả năng đọc dữ liệu**, không chỉ số lượng field.

## 8. Schema registry và governance

**Schema registry** lưu trữ schema, nhận dạng phiên bản, kiểm tra policy tương thích và thường cung cấp schema ID/metadata để producer và consumer sử dụng. Nó giúp phát hiện một số thay đổi không an toàn trước khi message tới production.

Một quy trình governance nên có:

1. Định danh event type và domain owner.
2. Định nghĩa contract, schema, ví dụ payload và mục đích từng field.
3. Kiểm tra naming convention, data classification, compatibility và quyền.
4. Review thay đổi bởi producer owner và các consumer/nhóm đại diện.
5. Đăng ký schema và chạy kiểm tra CI/CD.
6. Triển khai consumer tương thích trước hoặc theo thứ tự rollout đã thiết kế.
7. Theo dõi usage, lỗi validation, unknown field/value và thời gian ngừng dùng phiên bản cũ.
8. Deprecate và retire schema sau khi đã xác minh không còn producer/consumer cần dùng.

### 8.1. CI/CD cho contract

Một pipeline có thể kiểm tra:

~~~text
Pull request
  -> Validate schema syntax
  -> Lint naming / required metadata
  -> Check compatibility against registry history
  -> Validate sample payloads
  -> Consumer contract tests
  -> Security and data-classification checks
  -> Publish schema artifact
  -> Deploy producer/consumer according to rollout plan
~~~

Registry không thay thế review nghiệp vụ và test tích hợp. Một schema có thể vượt kiểm tra backward nhưng event vẫn sai vì producer phát BookingConfirmed trước khi transaction thực sự commit.

### 8.2. Quản trị quyền

- Producer chỉ được đăng ký/ghi schema trong domain hoặc namespace được giao.
- Producer chỉ được publish loại event đã phê duyệt vào topic/stream tương ứng.
- Consumer chỉ được consume subscription cần thiết.
- Thao tác sửa compatibility policy, xóa schema hoặc replay lịch sử cần được audit và giới hạn quyền.
- Secret, token, payload nhạy cảm không nên nằm trong schema description, example công khai hoặc log CI.

## 9. Quy trình rollout schema không phá consumer

Với thay đổi tương thích, quy trình vẫn cần được thiết kế. Mô hình thường dùng là **expand → migrate → contract**:

1. **Expand:** bổ sung field/schema theo cách có thể tồn tại song song với phiên bản cũ, thường là optional/default thích hợp.
2. **Migrate consumers:** triển khai consumer mới có thể đọc cả dữ liệu cũ và mới. Consumer cần xử lý trường hợp field vắng mặt.
3. **Migrate producers:** bắt đầu phát field mới sau khi consumer cần thiết đã sẵn sàng hoặc đã có policy cho phép.
4. **Observe:** theo dõi validation, lỗi consumer, tỷ lệ sử dụng field và các giá trị unknown.
5. **Contract:** chỉ sau khi mọi consumer liên quan đã chuyển, mới cân nhắc bỏ field cũ hoặc thay đổi ràng buộc.

### 9.1. Ví dụ đổi tên field

Giả sử field cũ là totalAmount và cần chuyển sang totalAmountMinor cùng currency:

| Giai đoạn | Producer | Consumer |
| --- | --- | --- |
| 0 — hiện tại | Phát totalAmount theo hợp đồng cũ | Đọc totalAmount |
| 1 — mở rộng | Phát cả totalAmount và bộ field mới có quy tắc đối chiếu | Chấp nhận cả hai, ưu tiên bộ mới nếu hợp lệ |
| 2 — chuyển consumer | Tiếp tục phát cả hai | Tất cả consumer cần thiết đọc bộ mới; đo consumer còn dùng field cũ |
| 3 — ngừng field cũ | Ngừng phát totalAmount theo quy trình thông báo | Không còn consumer phụ thuộc field cũ |
| 4 — contract | Chỉ còn field mới hoặc event type mới nếu thay đổi semantics không tương thích | Consumer chỉ dùng hợp đồng mới |

Nếu totalAmount cũ là decimal còn totalAmountMinor là integer, producer phải quy định cách làm tròn/chuyển đổi, currency exponent và xử lý trường hợp cũ thiếu currency. **Không chuyển đổi bằng phép nhân 100 một cách mặc định** cho mọi currency.

## 10. Consumer contract testing và kiểm thử tương thích

Schema validation kiểm tra payload có đúng cấu trúc; **consumer contract test** kiểm tra producer phát đúng những gì consumer thực sự cần, trong khi consumer có thể xử lý dữ liệu theo hợp đồng.

Các lớp kiểm thử:

| Loại kiểm thử | Mục tiêu |
| --- | --- |
| Schema validation | Message đúng cấu trúc, kiểu, required field và constraint |
| Compatibility check | Schema mới phù hợp policy với schema cũ |
| Producer contract test | Producer phát event có ý nghĩa và dữ liệu đúng theo contract |
| Consumer contract test | Consumer xử lý payload hợp lệ, field thiếu/unknown value theo rule |
| Integration test | Broker, serialization, schema ID, authentication và routing hoạt động |
| Replay test | Consumer mới đọc được message lưu từ các version cũ |
| Semantic test | Đơn vị, status transition, timestamp và giá trị tiền tệ được diễn giải đúng |

Một tập test nên bao gồm:

- Message hợp lệ tối thiểu và message với các field optional.
- Field mới xuất hiện mà consumer chưa biết.
- Enum có giá trị mới.
- Field cũ bị absent/null và các default khác nhau.
- Timestamp ở timezone/precision khác nhau theo contract.
- Event trùng, đến sai thứ tự hoặc có version thấp hơn trạng thái consumer hiện tại.
- Schema ID không tồn tại, schema validation fail hoặc producer gửi sai content type.
- Payload có kích thước bất thường hoặc dữ liệu nhạy cảm không được phép.

## 11. Replay, retention và consumer mới

Một ưu điểm của event log là có thể phát lại message để tái dựng projection hoặc sửa lỗi consumer. Tuy nhiên replay làm nổi bật vấn đề tương thích:

- Consumer mới có thể phải đọc event được phát từ nhiều năm trước theo schema cũ.
- Field có thể thiếu, enum có thể chứa giá trị đã ngừng sử dụng, timestamp có thể theo quy ước cũ.
- Một event lịch sử không nên bị sửa lại chỉ để giống schema mới, vì điều đó làm sai tính bất biến của dữ liệu lịch sử.
- Consumer cần có logic đọc nhiều version hoặc một bước upcast/normalization có kiểm soát.

### 11.1. Upcasting và normalization

**Upcaster** chuyển message cũ sang mô hình nội bộ mới trước khi consumer xử lý. Ví dụ schema v1 có totalAmount và currency; mô hình nội bộ v2 dùng amountMinor và currency. Upcaster phải biết quy tắc chuyển đổi chính xác, có test cho mọi trường hợp và không thay đổi message gốc trong event store.

Nếu không thể chuyển đổi an toàn do thiếu thông tin, consumer cần đưa message vào quarantine hoặc quy trình reconciliation. Không tự gán một default nghiệp vụ sai chỉ để tránh lỗi parse.

### 11.2. Retention là một phần của contract

Chính sách giữ message và schema phải liên kết:

| Câu hỏi | Tác động |
| --- | --- |
| Message giữ trong bao lâu? | Consumer/replay cần hỗ trợ schema cũ ít nhất theo phạm vi yêu cầu |
| Có archive dài hạn không? | Cần lưu schema ID/contract và khả năng truy cập registry cũ |
| Có replay qua nhiều phiên bản consumer không? | Cần kiểm thử upcast/normalization và idempotency |
| Ai có quyền replay? | Replay có thể lặp side effect, cần quy trình phê duyệt/audit |
| Có xóa dữ liệu cá nhân theo yêu cầu không? | Event immutable và retention cần thiết kế với yêu cầu privacy, không lưu thừa |

## 12. Bảo mật và quyền riêng tư trong event contract

Message có thể được lưu lâu, nhân bản qua broker, archive, DLQ và nhiều consumer. Vì vậy một field đưa vào event có thể mở rộng phạm vi dữ liệu hơn nhiều so với một API trả trực tiếp cho người dùng.

Nguyên tắc thiết kế:

- **Data minimization:** chỉ phát field consumer cần; ưu tiên reference thay cho bản sao đầy đủ.
- **Classification:** gắn loại dữ liệu (public/internal/confidential hoặc taxonomy tổ chức) vào contract/catalog.
- **Access control:** phân quyền publish/consume theo domain, topic, subscription và tenant khi phù hợp.
- **Encryption:** bảo vệ truyền dẫn và lưu trữ, quản lý khóa theo yêu cầu.
- **Audit:** ghi ai thay đổi schema, publish, truy cập/replay hoặc thay compatibility policy.
- **Retention/deletion:** xác định thời gian giữ và khả năng đáp ứng nghĩa vụ dữ liệu cá nhân.
- **Schema example:** dùng dữ liệu giả, không đưa thông tin khách thật vào tài liệu hoặc repository.

### 12.1. Event immutable và yêu cầu xóa dữ liệu

Event log thường được thiết kế bất biến để giữ lịch sử và khả năng audit. Nhưng nếu payload chứa dữ liệu cá nhân, một yêu cầu xóa hoặc giới hạn xử lý có thể tạo xung đột. Giải pháp phải được xác định theo nghĩa vụ pháp lý và thiết kế dữ liệu cụ thể:

- Tránh đưa dữ liệu cá nhân trực tiếp vào event nếu chỉ cần reference.
- Dùng token/reference có thể thu hồi hoặc dữ liệu tách biệt theo quyền.
- Có chính sách retention và xóa/ẩn danh phù hợp với event store, archive, backup và consumer projection.
- Ghi nhận cách xử lý khi dữ liệu đã được sao chép qua hệ thống downstream.

Không giả định mã hóa tự giải quyết mọi nghĩa vụ xóa hoặc giới hạn truy cập; phải đánh giá bản sao, khóa, log và backup.

## 13. Quản lý catalog, ownership và vòng đời event

Ngoài registry schema, tổ chức nên có **event catalog** để người phát triển tìm được event nào tồn tại, ai sở hữu và có thể dùng như thế nào.

Một catalog record tối thiểu:

| Trường | Mục đích |
| --- | --- |
| Event type/name | Định danh ổn định |
| Domain/business meaning | Ý nghĩa nghiệp vụ và thời điểm phát |
| Producer/owner | Nhóm chịu trách nhiệm |
| Consumer/subscribers | Nhóm sử dụng và mục đích |
| Schema ID/version | Liên kết phiên bản schema |
| Compatibility policy | Quy tắc thay đổi được chấp nhận |
| Data classification | Phân loại dữ liệu và quyền |
| Delivery/ordering semantics | At-least-once, partition key, ordering scope nếu áp dụng |
| Retention/replay policy | Thời gian giữ, archive và quy trình replay |
| Lifecycle status | Draft, active, deprecated, retired |

### 13.1. Deprecation và retirement

Ngừng một event không chỉ là xóa schema. Phải thông báo producer/consumer, xác định ngày ngừng, theo dõi lưu lượng thực tế, kiểm tra backlog và archive, cung cấp giải pháp thay thế và xác định ai chấp thuận xóa topic/schema. Event đã phát trong quá khứ vẫn có thể được replay, vì vậy retirement của producer không tự kết thúc nghĩa vụ tương thích lịch sử.

## 14. Ví dụ thiết kế một event contract hoàn chỉnh

**Event:** BookingConfirmed — được phát khi booking đã chuyển sang trạng thái confirmed theo quy tắc transaction của Booking Service.

### Đặc tả nghiệp vụ

- Producer có thẩm quyền: Booking Service.
- Thời điểm: sau khi transaction xác nhận booking được commit.
- Một event biểu diễn một lần chuyển booking sang confirmed.
- Event không có nghĩa thanh toán đã settled nếu hợp đồng thanh toán chỉ mới authorized.
- ID booking ổn định; event ID duy nhất cho từng lần phát; retry không tạo event nghiệp vụ mới.
- Consumer được phép xử lý lặp; phải dùng event ID hoặc khóa nghiệp vụ để deduplicate.
- Event chứa amount/currency đã xác nhận, nhưng không chứa thông tin thẻ hoặc bí mật thanh toán.

### Payload tham khảo

~~~json
{
  "eventId": "evt-7f21a9",
  "eventType": "com.example.booking.confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-12-18T08:29:58Z",
  "producer": "booking-service",
  "correlationId": "req-51bc",
  "aggregateId": "booking-42",
  "data": {
    "bookingId": "booking-42",
    "customerRef": "customer-18",
    "propertyId": "property-91",
    "currency": "VND",
    "totalAmountMinor": 125000000
  }
}
~~~

### Consumer và quyền

| Consumer | Nhu cầu | Quyền dữ liệu |
| --- | --- | --- |
| Notification service | Gửi email/SMS xác nhận | Đọc booking ID và dữ liệu tối thiểu để tạo thông báo |
| Search indexer | Cập nhật trạng thái/tồn phòng hiển thị | Chỉ nhận field cần thiết, không cần dữ liệu liên hệ khách |
| Analytics | Tính chỉ số đặt chỗ/doanh thu | Dùng reference hoặc dữ liệu đã phân loại, tránh PII không cần |
| Partner integration | Đồng bộ trạng thái được thỏa thuận | Subscription riêng, hợp đồng version và quyền theo đối tác |

### Chính sách tiến hóa

1. Schema v1 được đăng ký, kiểm tra và phát hành.
2. Khi thêm field promotionCode, bắt đầu bằng field optional; kiểm tra backward/forward theo consumer và registry policy.
3. Consumer nào cần field mới được nâng cấp để xử lý trường hợp absent.
4. Producer chỉ phát promotionCode sau khi đã xác nhận quy tắc dữ liệu và consumer phù hợp sẵn sàng.
5. Nếu sau này thay semantics của tổng tiền, không tái sử dụng totalAmountMinor với ý nghĩa mới; tạo field/type/version mới và có migration plan.

## 15. Bài thực hành: tiến hóa hợp đồng sự kiện không làm gián đoạn consumer

**Bối cảnh:** Booking Service phát BookingConfirmed v1. Notification, Search Indexer và Analytics đang dùng schema hiện tại. Nhóm muốn thêm promotionCode, đổi field totalAmount thành cấu trúc amount + currency, đồng thời cần giữ khả năng replay event cũ.

### Nhiệm vụ

1. Viết event contract gồm ý nghĩa nghiệp vụ, điều kiện phát, owner, envelope, payload, data classification, ordering và retention.
2. Chọn JSON Schema, Avro hoặc Protocol Buffers; giải thích lý do theo ngôn ngữ, throughput, tooling và khả năng consumer.
3. Đăng ký v1 và xác định compatibility mode cần dùng cho rollout độc lập producer/consumer.
4. Phân loại từng thay đổi là backward, forward, full hay breaking trong đúng semantics của format/registry đã chọn.
5. Thiết kế lộ trình expand–migrate–contract cho promotionCode và amount/currency; không đổi semantics field cũ âm thầm.
6. Viết test cho consumer cũ khi gặp field mới, consumer mới khi đọc message v1, enum lạ, null/absent và message replay.
7. Mô tả cách upcast dữ liệu lịch sử và xử lý event không thể chuyển đổi an toàn.
8. Xác định quyền producer/consumer, cách che dữ liệu nhạy cảm trong log, quy trình replay và người phê duyệt schema.
9. Viết ADR ngắn nêu đánh đổi về compatibility, chi phí registry, payload size, vận hành và khả năng mở rộng.

### Tiêu chí hoàn thành

- Contract có ý nghĩa nghiệp vụ rõ, không chỉ liệt kê tên field.
- Envelope và payload phân tách được metadata với dữ liệu nghiệp vụ.
- Schema validate được và có ví dụ dữ liệu hợp lệ/không hợp lệ.
- Compatibility policy được giải thích theo chiều writer/reader và lịch sử schema thực tế.
- Thay đổi breaking có version/migration plan; không âm thầm thay semantics.
- Consumer cũ, consumer mới, replay và unknown value đều có test.
- Quyền, dữ liệu nhạy cảm, retention và ownership được ghi nhận.

## 16. Checklist Well-Architected trước khi phát hành event contract

- [ ] Event mô tả một sự thật nghiệp vụ đã xảy ra; producer và thời điểm phát được xác định.
- [ ] Hợp đồng có owner, producer, consumer, mục đích, ví dụ và trạng thái vòng đời.
- [ ] Envelope/payload, ID, timestamp, correlation/causation và schema version có semantics rõ.
- [ ] Field có kiểu, đơn vị, optional/null/default, enum và quy tắc tương thích cụ thể.
- [ ] Đã chọn format/registry theo năng lực đội ngũ và kiểm tra semantics thực tế của tool.
- [ ] Compatibility được kiểm tra với consumer cũ và lịch sử message có thể replay.
- [ ] Thay đổi ngữ nghĩa hoặc đơn vị được xem là breaking; không chỉ giữ kiểu dữ liệu rồi âm thầm đổi nghĩa.
- [ ] Producer/consumer được rollout theo thứ tự tương thích, có quan sát và rollback.
- [ ] Có test schema, producer contract, consumer contract, integration và replay.
- [ ] Event có idempotency/deduplication, ordering/partition và delivery semantics phù hợp nghiệp vụ.
- [ ] Dữ liệu nhạy cảm được tối thiểu hóa, phân loại, phân quyền và kiểm soát retention.
- [ ] Quyền publish/consume/schema change/replay được cấp tối thiểu và audit.
- [ ] Schema, registry, catalog, DLQ và archive có owner, backup/DR và quy trình xử lý lỗi.
- [ ] Chi phí serialization, broker, lưu trữ, truyền dữ liệu, registry và vận hành được đánh giá.
- [ ] ADR ghi rõ đánh đổi về reliability, security, performance, cost và operations.

**Điểm cốt lõi:** schema hợp lệ chỉ cho biết message có đúng cấu trúc; event contract còn phải bảo đảm các bên hiểu đúng **ý nghĩa nghiệp vụ và cách dữ liệu tiến hóa**. Khi producer, consumer, registry, rollout, replay và governance cùng tuân theo một quy trình tương thích có kiểm chứng, event-driven architecture mới có thể mở rộng độc lập mà không biến mỗi lần đổi field thành rủi ro gián đoạn hoặc sai dữ liệu.
