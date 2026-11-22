# Đổi tên hoặc xóa field

Schema của một sự kiện Kafka là hợp đồng dữ liệu giữa producer và consumer. Khi đổi tên hoặc xóa một field, producer mới có thể ghi payload mà consumer cũ không hiểu; ngược lại, consumer mới có thể không đọc được những record được ghi theo schema cũ. Vấn đề còn kéo dài sau khi triển khai vì Kafka giữ record theo retention và consumer có thể replay dữ liệu lịch sử.

Do đó, đổi tên hoặc xóa field cần được triển khai theo nhiều bước tương thích. Trước khi sửa schema, phải xác định format đang dùng (Avro, JSON Schema hay Protobuf), quy tắc tương thích của Schema Registry và phiên bản producer/consumer đang hoạt động.

## 1. Kafka không tự định nghĩa schema cho payload

Kafka lưu key, value và headers dưới dạng byte. Kafka broker không tự hiểu `customerName` là field gì và cũng không kiểm tra một consumer có hiểu payload hay không. Việc kiểm tra schema thường được thực hiện ở producer/consumer thông qua serializer, deserializer và hệ thống quản lý schema như Confluent Schema Registry.

Một record có thể chứa schema ID hoặc metadata định dạng do serializer thêm vào. Consumer dùng deserializer để lấy schema tương ứng và chuyển byte thành object. Khi schema thay đổi, khả năng đọc phụ thuộc vào quy tắc resolution của format và compatibility policy được cấu hình cho subject.

Các câu hỏi cần trả lời trước khi thay đổi:

- Producer nào đang ghi loại sự kiện này? Có producer cũ vẫn chạy trong lúc rollout không?
- Consumer nào đang đọc? Có consumer bên ngoài tổ chức hoặc job replay chạy theo lịch không?
- Record cũ còn nằm trong Kafka, object storage hoặc data lake trong bao lâu?
- Consumer có thể đọc record được ghi bằng nhiều schema version hay không?
- Schema Registry đang dùng compatibility mode nào và kiểm tra với version gần nhất hay toàn bộ lịch sử?

Không nên xem việc code compile thành công là bằng chứng schema đã tương thích. Producer và consumer có thể được triển khai ở thời điểm khác nhau, và dữ liệu cũ vẫn tiếp tục được đọc sau rollout.

## 2. Hiểu backward, forward và full compatibility

Schema Registry thường dùng các khái niệm tương thích sau. Cách diễn giải phổ biến dựa trên hướng reader/writer:

| Chế độ | Ý nghĩa | Câu hỏi kiểm tra |
| --- | --- | --- |
| Backward | Schema mới có thể đọc dữ liệu được ghi bằng schema cũ | Consumer mới có đọc được record cũ không? |
| Forward | Consumer/schema cũ có thể đọc dữ liệu được ghi bằng schema mới | Consumer cũ có chịu được record mới không? |
| Full | Hỗ trợ cả backward và forward | Producer và consumer có thể được nâng cấp theo thứ tự khác nhau không? |
| Transitive | Kiểm tra tương thích với nhiều version lịch sử thay vì chỉ version liền trước | Consumer mới có đọc được toàn bộ dữ liệu còn được phép replay không? |

Tên mode và thuật toán kiểm tra cụ thể phụ thuộc format và phiên bản Schema Registry. Ví dụ, `BACKWARD_TRANSITIVE` kiểm tra schema mới với các version trước đó; `FULL_TRANSITIVE` yêu cầu cả hai hướng với lịch sử schema. Hãy xác nhận policy đang áp dụng cho đúng subject, vì subject naming strategy có thể tạo subject riêng cho topic, record name hoặc key/value.

Một thay đổi có thể tương thích theo một hướng nhưng không tương thích theo hướng còn lại. Trong rollout producer/consumer độc lập, full compatibility thường tạo dư địa triển khai an toàn hơn, nhưng không thay thế việc kiểm tra schema format, semantics và consumer thực tế.

## 3. Đổi tên field thực chất là xóa field cũ và thêm field mới

Giả sử sự kiện ban đầu có field:

```json
{
  "customerId": "C-102",
  "customerName": "An"
}
```

Sau đó nghiệp vụ muốn đổi `customerName` thành `displayName`. Về mặt hợp đồng dữ liệu, đây là hai thao tác:

1. Thêm field `displayName`.
2. Ngừng sử dụng và cuối cùng xóa field `customerName`.

Nếu producer mới chỉ ghi `displayName`, consumer cũ vẫn tìm `customerName` có thể nhận giá trị thiếu hoặc lỗi deserialize/validation. Nếu consumer mới chỉ đọc `displayName`, record cũ chỉ có `customerName` cũng không cung cấp giá trị mà consumer mong đợi.

Trong giai đoạn chuyển tiếp, consumer mới nên đọc cả hai tên và ưu tiên tên mới. Producer mới có thể ghi cả hai field với cùng ý nghĩa trong một khoảng thời gian. Chỉ xóa tên cũ sau khi các consumer cũ và quy trình replay đã được xử lý.

```java
String displayName = event.displayName() != null
        ? event.displayName()
        : event.customerName();
```

Đoạn code minh họa fallback ở consumer. Với DTO thực tế, cần cho phép field cũ và mới cùng tồn tại trong giai đoạn chuyển tiếp, đồng thời xác định rõ cách xử lý nếu cả hai cùng có giá trị nhưng khác nhau.

Không đổi tên field nếu ý nghĩa nghiệp vụ cũng thay đổi. Ví dụ `amount` trước đây là số tiền trước thuế nhưng sau này được dùng làm số tiền sau thuế. Đây là thay đổi semantics; hãy tạo field mới hoặc event version mới, không tái sử dụng cùng tên để biểu thị một ý nghĩa khác.

## 4. Đổi tên field trong Avro

Avro resolution so sánh writer schema (schema dùng khi ghi record) với reader schema (schema consumer dùng để đọc). Reader schema có thể khai báo `aliases` để ánh xạ tên cũ sang tên mới khi đọc dữ liệu đã được ghi bằng schema cũ.

Ví dụ schema cũ:

```json
{
  "type": "record",
  "name": "CustomerUpdated",
  "fields": [
    { "name": "customerId", "type": "string" },
    { "name": "customerName", "type": "string" }
  ]
}
```

Schema mới dùng `displayName` và khai báo alias:

```json
{
  "type": "record",
  "name": "CustomerUpdated",
  "fields": [
    { "name": "customerId", "type": "string" },
    {
      "name": "displayName",
      "type": ["null", "string"],
      "default": null,
      "aliases": ["customerName"]
    }
  ]
}
```

Khi reader dùng schema mới, alias `customerName` cho phép Avro nhận diện field cùng tên trong writer schema cũ và đưa giá trị vào `displayName`. `default: null` cũng cho phép reader đọc writer schema không có field `displayName` trong trường hợp không có field tương ứng để resolution.

Điểm quan trọng: alias được dùng theo hướng reader schema phân giải tên từ writer schema. Consumer cũ vẫn dùng reader schema cũ không tự biết rằng writer schema mới đã đổi tên field sang `displayName`. Vì vậy, alias hỗ trợ consumer mới đọc dữ liệu cũ; nó không tự bảo đảm producer mới chỉ ghi tên mới sẽ tương thích với consumer cũ.

Trong rollout có producer và consumer chạy song song, hãy giữ field cũ hoặc dual-write trong thời gian chuyển tiếp. Chỉ bỏ field cũ khi consumer cũ không còn cần đọc record mới và policy tương thích cho phép.

## 5. Xóa field trong Avro

Khi xóa field khỏi writer schema mới, consumer mới thường có thể đọc record cũ có field thừa vì reader có thể bỏ qua field không cần dùng. Chiều ngược lại cần chú ý: consumer cũ có reader schema yêu cầu field mà writer schema mới đã bỏ có thể không resolve được nếu reader schema không khai báo default.

Ví dụ, schema cũ có `legacyCode` bắt buộc:

```json
{
  "name": "legacyCode",
  "type": "string"
}
```

Trước khi ngừng ghi field này, cần triển khai consumer có reader schema chấp nhận việc thiếu `legacyCode`, ví dụ bằng default phù hợp hoặc một schema mới đã bỏ field. Sau đó mới triển khai producer ngừng ghi field và cuối cùng loại field khỏi schema theo compatibility policy.

Default của Avro là giá trị reader dùng khi writer schema không cung cấp field tương ứng. Nó không tự sửa dữ liệu đã lưu trong Kafka và cũng không thay đổi payload gốc. Chọn default phải có ý nghĩa nghiệp vụ; không dùng chuỗi rỗng hoặc số 0 một cách máy móc nếu các giá trị đó có thể bị hiểu là dữ liệu thật.

## 6. Đổi tên hoặc xóa property trong JSON Schema

Với JSON Schema, field thường là property trong object. Một schema mới có thể khai báo property mới và giữ property cũ trong giai đoạn chuyển tiếp:

```json
{
  "type": "object",
  "properties": {
    "customerId": { "type": "string" },
    "customerName": {
      "type": "string",
      "deprecated": true
    },
    "displayName": { "type": "string" }
  },
  "required": ["customerId"]
}
```

Ở đây `deprecated: true` là annotation giúp công cụ và con người biết property cũ không nên dùng nữa. Nó không tự xóa property, không ép producer ngừng ghi và cũng không chuyển giá trị `customerName` sang `displayName`.

Trong giai đoạn chuyển tiếp, consumer mới nên đọc `displayName` trước rồi fallback sang `customerName`. Producer có thể ghi cả hai. Chỉ thêm `displayName` vào `required` sau khi bảo đảm tất cả producer đã cung cấp property này và dữ liệu cũ được xử lý theo chính sách tương thích.

JSON Schema có thể dùng `additionalProperties: false` để từ chối property không được khai báo. Consumer cũ có cấu hình này có thể từ chối payload mới có thêm `displayName`, dù consumer không cần property đó. Vì vậy, thêm property mới chỉ an toàn nếu schema/validator phía consumer cho phép hoặc consumer được nâng cấp trước.

Thuộc tính `default` trong JSON Schema chỉ là annotation theo chuẩn JSON Schema; validator thông thường không tự chèn giá trị default vào payload. Nếu consumer cần fallback, phải thực hiện trong code hoặc dùng một bước chuẩn hóa dữ liệu rõ ràng.

## 7. Đổi tên hoặc xóa field trong Protobuf

Protobuf mã hóa field theo field number (tag number), không dùng tên field để xác định dữ liệu trên wire. Do đó, đổi tên field nhưng giữ nguyên field number và wire type thường tương thích ở mức binary wire format:

```protobuf
message CustomerUpdated {
  string display_name = 2; // Trước đây là customer_name = 2
  string customer_id = 1;
}
```

Consumer Protobuf cũ vẫn đọc field số 2 theo schema cũ; consumer mới đọc cùng field số 2 theo tên mới. Tuy nhiên, tên field được dùng trong code sinh tự động, descriptor và JSON mapping. Nếu hệ thống có trao đổi Protobuf JSON, đổi tên có thể làm thay đổi property JSON (ví dụ `customerName` thành `displayName`) và phá vỡ API JSON dù wire format nhị phân vẫn tương thích.

Khi xóa field, phải `reserved` cả field number và tên để không vô tình tái sử dụng chúng:

```protobuf
message CustomerUpdated {
  string customer_id = 1;

  reserved 2;
  reserved "customer_name";
}
```

Không bao giờ gán lại tag number đã dùng cho một ý nghĩa khác. Nếu tái sử dụng, consumer cũ có thể diễn giải dữ liệu mới thành field cũ và tạo lỗi khó phát hiện. Với enum, cũng cần reserve numeric value và tên enum đã xóa khi muốn ngăn tái sử dụng.

Schema Registry cho Protobuf còn áp dụng quy tắc tương thích trên descriptor và cấu hình format. Vì vậy, wire compatibility không đồng nghĩa mọi công cụ, JSON representation và compatibility mode đều chấp nhận thay đổi tên. Hãy kiểm tra bằng chính registry và client version đang triển khai.

## 8. Quy trình rollout an toàn khi đổi tên field

Ví dụ đổi `customerName` thành `displayName`, có thể chia rollout thành các giai đoạn:

```text
Giai đoạn 1: EXPAND
  Schema chấp nhận cả customerName và displayName
                 |
                 v
Giai đoạn 2: CONSUMER
  Consumer mới đọc displayName, fallback customerName
                 |
                 v
Giai đoạn 3: DUAL WRITE
  Producer ghi cả hai field với cùng ý nghĩa
                 |
                 v
Giai đoạn 4: MIGRATE
  Xác nhận không còn consumer phụ thuộc customerName
                 |
                 v
Giai đoạn 5: CONTRACT
  Producer ngừng ghi customerName, schema loại field cũ
```

Các bước thực tế:

1. Kiểm kê producer, consumer, connector, job replay và hệ thống ngoài đang dùng field cũ.
2. Đăng ký schema mở rộng sao cho các consumer hiện tại vẫn đọc được payload mới theo policy đã chọn.
3. Triển khai consumer có thể đọc cả tên mới và tên cũ. Với Avro, dùng alias trong reader schema khi phù hợp; với JSON Schema/Protobuf, triển khai fallback hoặc mapping tương ứng.
4. Triển khai producer dual-write hai field. Nếu cả hai cùng có giá trị, quy định rõ giá trị nào là nguồn chuẩn và cách phát hiện chúng bị lệch nhau.
5. Theo dõi metric/log để xác nhận consumer đã chuyển sang field mới và không còn phụ thuộc field cũ.
6. Ngừng producer cũ, sau đó ngừng ghi field cũ ở producer mới.
7. Chỉ xóa field cũ khỏi schema khi các consumer cũ đã kết thúc và chính sách replay/retention không còn yêu cầu chúng.

Nếu không thể dual-write do payload hoặc semantics không cho phép, hãy dùng event version mới hoặc topic/version contract riêng. Không ép một field mới mang ý nghĩa cũ chỉ để giữ tương thích hình thức.

## 9. Quy trình rollout an toàn khi xóa field

Xóa field thường có thể triển khai theo mô hình *deprecate → stop use → stop write → remove*:

1. Đánh dấu field là deprecated trong tài liệu/schema nếu format hỗ trợ.
2. Triển khai consumer ngừng phụ thuộc field đó; kiểm tra code, dashboard, connector và báo cáo.
3. Triển khai producer ngừng ghi field. Nếu consumer cũ vẫn cần field, chưa được thực hiện bước này.
4. Chờ hết thời gian rollout, retry, retention và replay đã cam kết. Xem cả dữ liệu ở kho lưu trữ ngoài Kafka.
5. Xóa field khỏi schema và kiểm tra compatibility với các version lịch sử.
6. Giữ lại metadata cần thiết để giải thích schema cũ và hỗ trợ điều tra dữ liệu lịch sử.

Đừng xóa field chỉ vì không còn thấy nó trong traffic vài phút. Một consumer chạy hàng tuần, batch job cuối tháng hoặc công cụ replay có thể vẫn phụ thuộc field. Thời gian chờ phải dựa trên vòng đời thực tế của tất cả consumer và dữ liệu.

## 10. Compatibility policy không thay thế kiểm thử ứng dụng

Schema Registry có thể xác nhận thay đổi tương thích theo format nhưng không hiểu đầy đủ logic nghiệp vụ. Ví dụ, `customerName` và `displayName` đều là string nên schema checker có thể chấp nhận một thay đổi, nhưng consumer có thể hiểu hai field với semantics khác nhau.

Hãy kiểm tra tối thiểu các cặp producer/consumer:

| Producer ghi | Consumer đọc | Điều cần xác minh |
| --- | --- | --- |
| Schema cũ | Consumer mới | Consumer mới đọc được record lịch sử và fallback đúng |
| Schema mới | Consumer cũ | Consumer cũ không lỗi hoặc đã được loại khỏi rollout trước khi producer mới chạy |
| Producer dual-write | Consumer mới | Consumer ưu tiên field mới và phát hiện hai field mâu thuẫn |
| Producer dual-write | Consumer cũ | Consumer cũ vẫn đọc field cũ trong giai đoạn chuyển tiếp |
| Schema mới sau khi contract | Job replay | Dữ liệu lịch sử còn trong retention vẫn được deserialize và xử lý |

Nên có fixture payload được ghi bằng từng schema version, integration test với Schema Registry hoặc mock registry phù hợp, và kiểm tra deserialize thực tế. Kiểm thử thêm các trường hợp field null, field vắng mặt, field có giá trị mặc định và cả hai tên cùng xuất hiện.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Đổi tên trực tiếp và chỉ triển khai producer mới | Consumer cũ không tìm thấy field cũ | Rollout consumer tương thích trước và dual-write trong giai đoạn chuyển tiếp |
| Nghĩ Avro alias giúp cả producer/consumer cũ và mới tự hiểu nhau | Alias chủ yếu hỗ trợ reader schema mới ánh xạ writer schema cũ | Kiểm tra cả hai hướng reader/writer; giữ field cũ khi cần forward compatibility |
| Xóa field đang được consumer cũ yêu cầu | Deserialize hoặc validation thất bại | Consumer ngừng phụ thuộc trước khi producer ngừng ghi và schema bị contract |
| Cho rằng JSON Schema `default` tự chèn giá trị | Consumer vẫn nhận property vắng mặt | Tự triển khai fallback/normalization trong ứng dụng |
| Xóa Protobuf field nhưng tái sử dụng tag number | Dữ liệu wire bị diễn giải sai | Reserve tag number và tên đã xóa |
| Chỉ kiểm tra schema version liền trước | Job replay có thể gặp schema cũ hơn | Cân nhắc transitive compatibility theo thời hạn replay |
| Xóa field khi chỉ consumer online đã nâng cấp | Batch job hoặc hệ thống ngoài vẫn lỗi | Kiểm kê mọi reader và thời gian lưu dữ liệu |
| Đổi tên đồng thời đổi nghĩa nghiệp vụ | Consumer cũ đọc được nhưng hiểu sai dữ liệu | Tạo field/event version mới cho thay đổi semantics |

## 12. Checklist trước khi đổi tên hoặc xóa field

- [ ] Đã xác định format schema và version của serializer/deserializer.
- [ ] Đã xác định Schema Registry subject và compatibility mode (kể cả transitive).
- [ ] Đã kiểm kê producer, consumer, connector, batch job và quy trình replay.
- [ ] Đã phân biệt đổi tên thuần túy với thay đổi semantics.
- [ ] Nếu đổi tên, consumer mới có thể đọc cả dữ liệu cũ và dữ liệu mới.
- [ ] Producer dual-write hoặc có chiến lược event version riêng trong thời gian chuyển tiếp.
- [ ] Avro alias/default, JSON Schema optional/deprecated hoặc Protobuf tag/reserved được dùng đúng ngữ nghĩa.
- [ ] Không dựa vào JSON Schema `default` như một cơ chế tự chèn dữ liệu.
- [ ] Không tái sử dụng Protobuf field number hoặc enum value đã xóa.
- [ ] Đã kiểm thử old producer/new consumer, new producer/old consumer và replay dữ liệu lịch sử.
- [ ] Chỉ contract field cũ sau khi không còn reader/writer phụ thuộc và thời hạn retention/replay đã được tính đến.
- [ ] Có metric hoặc log để theo dõi mức sử dụng field cũ trong giai đoạn migration.

Đổi tên hoặc xóa field là một quá trình chuyển đổi hợp đồng dữ liệu, không chỉ là sửa tên thuộc tính trong DTO. Hãy mở rộng schema trước, triển khai consumer có khả năng đọc cả hai dạng, chuyển producer theo từng bước và chỉ contract field cũ khi mọi reader cùng dữ liệu lịch sử đã sẵn sàng. Cách làm này giữ cho luồng Kafka hoạt động trong suốt quá trình nâng cấp producer và consumer độc lập.
