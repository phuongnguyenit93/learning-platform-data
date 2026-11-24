# Tiến hóa hợp đồng dữ liệu và xử lý thông điệp không tương thích

> **Chương:** Độ tin cậy  
> **Module:** SPRING_CLOUD_FUNCTION  
> **Trọng tâm:** Thiết kế hợp đồng message có thể tiến hóa khi producer và consumer được triển khai độc lập; hiểu backward/forward/full compatibility, schema registry, writer/reader schema, chuyển đổi dữ liệu, cách ly message không đọc được và khôi phục an toàn trong ứng dụng Spring Cloud Function.  
> **Bối cảnh:** Các ví dụ dùng Java 21 và Spring Cloud Function. Các quy tắc compatibility của Schema Registry được nêu rõ theo cách triển khai của Confluent; không coi chúng là quy tắc chung bắt buộc của mọi registry.

## 1. Vì sao hợp đồng dữ liệu cần được tiến hóa có kiểm soát?

Trong hệ thống hướng sự kiện, producer và consumer thường được build, triển khai và scale độc lập. Producer có thể phát event mới trong khi consumer cũ vẫn đang chạy; queue có thể giữ message qua nhiều lần deploy; một message đã phát tuần trước có thể được replay sau khi schema hiện tại đã thay đổi.

Ví dụ, dịch vụ Order phát message:

~~~json
{
  "orderId": "ORD-42",
  "customerId": "CUS-18",
  "total": 1250000,
  "currency": "VND"
}
~~~

Sau vài tháng, nhóm phát triển muốn bổ sung discountCode, đổi customerId thành buyerId, đồng thời chuyển total từ số nguyên sang decimal. Các thay đổi này có vẻ nhỏ trong code, nhưng có thể ảnh hưởng đến:

- Consumer đang đọc message cũ.
- Consumer cũ vẫn nhận message mới trong giai đoạn rollout.
- Consumer đọc lại message được lưu lâu ngày.
- Consumer khác ngôn ngữ hoặc framework.
- Message được giữ trong DLQ và replay sau khi code đã nâng cấp.
- Hệ thống analytics hoặc audit đọc dữ liệu lịch sử.

**Hợp đồng dữ liệu là thỏa thuận giữa bên ghi và bên đọc.** Việc đổi một DTO Java không tự động nâng cấp mọi producer, consumer, queue hoặc dữ liệu đã lưu.

Spring Cloud Function giúp tách logic nghiệp vụ khỏi giao thức gọi. Để giữ được lợi ích đó, ứng dụng cần một lớp adapter/converter có thể nhận biết phiên bản dữ liệu, chuyển message sang kiểu ứng dụng hiểu được và xử lý rõ ràng khi không thể chuyển đổi.

## 2. Ba lớp version cần phân biệt

Không nên gộp mọi loại version thành một trường version.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Event type/version | Loại sự kiện nghiệp vụ và ý nghĩa của occurrence. | com.acme.order.created.v1 |
| Schema version | Cấu trúc dữ liệu được dùng để serialize/deserialize. | Avro subject order-created, version 3 |
| Application/runtime version | Phiên bản code đang xử lý message. | orders-consumer 2.7.0, Java 21 |

Một event type có thể giữ nguyên trong khi schema có thêm một field tùy chọn. Ngược lại, một thay đổi ý nghĩa nghiệp vụ có thể cần event type mới dù JSON fields trông gần giống.

Nếu dùng CloudEvents, specversion là version của đặc tả envelope; nó không phải version của payload. Schema version nên được nhận diện bằng dataschema, registry schema ID/version hoặc quy ước riêng của ứng dụng.

### 2.1. Event type trả lời “điều gì đã xảy ra?”

Ví dụ:

- com.acme.order.created.v1
- com.acme.order.cancelled.v1
- com.acme.order.refunded.v1

Type không phải tên function bean. Một event order.created có thể được nhiều function xử lý: cập nhật kho, gửi email, ghi audit hoặc tính điểm.

### 2.2. Schema version trả lời “payload có cấu trúc nào?”

Ví dụ schema version 1 có:

~~~json
{
  "orderId": "ORD-42",
  "customerId": "CUS-18",
  "total": 1250000
}
~~~

Schema version 2 thêm field tùy chọn:

~~~json
{
  "orderId": "ORD-42",
  "customerId": "CUS-18",
  "total": 1250000,
  "discountCode": null
}
~~~

Cả hai payload có thể mô tả cùng một occurrence order.created. Việc schema mới có đọc được dữ liệu cũ hay không phụ thuộc format, default, required fields và compatibility policy.

## 3. Writer schema và reader schema

Khi serialize message, producer dùng **writer schema**. Khi deserialize, consumer có **reader schema** mà code hiện tại mong đợi.

Ví dụ:

- Producer phiên bản 1 ghi OrderCreatedV1.
- Consumer phiên bản 2 đọc OrderCreatedV2.
- Schema resolver cần biết schema lúc ghi và schema lúc đọc để quyết định có thể chuyển đổi hay không.

~~~mermaid
flowchart LR
    P["Producer v1"] --> WS["Writer schema v1"]
    WS --> M["Message + schema reference"]
    M --> R["Consumer v2"]
    RS["Reader schema v2"] --> R
    R --> D["Schema resolution"]
    D -->|Tương thích| O["Application object"]
    D -->|Không tương thích| Q["Quarantine / DLQ"]
~~~

Trong Avro, dữ liệu binary không tự chứa tên field và type đầy đủ để consumer đoán schema. Reader cần writer schema để diễn giải bytes. Sau đó Avro thực hiện schema resolution giữa writer và reader schema. https://avro.apache.org/docs/current/specification/

Trong một số serializer khác, metadata schema ID được đặt trong wire format hoặc header. Không nên tự giả định mọi message đều có cùng cách mang schema reference.

### 3.1. Ví dụ thay đổi có thể tương thích

Schema cũ:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "customerId", "type": "string"}
  ]
}
~~~

Schema mới thêm field có default:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "customerId", "type": "string"},
    {
      "name": "discountCode",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
~~~

Khi reader schema mới đọc dữ liệu được ghi bằng schema cũ, field discountCode có thể được điền bằng default null. Đây là một mẫu thay đổi backward-compatible thường dùng với Avro.

### 3.2. Default không tự sửa mọi dữ liệu sai

Default chỉ có ý nghĩa theo quy tắc resolution của format. Nó không thể:

- Biến chuỗi unknown thành một mã khách hàng hợp lệ.
- Đổi đơn vị từ đồng sang nghìn đồng.
- Suy ra currency bị thiếu.
- Khôi phục field đã bị producer ghi sai.
- Giải quyết thay đổi ngữ nghĩa của một field.

Không dùng default giả như 0, chuỗi rỗng hoặc ngày hiện tại chỉ để parser không báo lỗi. Một message parse được nhưng mang ý nghĩa sai có thể gây hậu quả nghiêm trọng hơn message bị từ chối.

## 4. Backward, forward và full compatibility

Các thuật ngữ này mô tả khả năng đọc dữ liệu giữa schema của producer và consumer. Quy ước sau là cách diễn giải phổ biến trong Schema Registry:

| Compatibility | Câu hỏi | Hướng đọc |
| --- | --- | --- |
| Backward | Reader schema mới có đọc được dữ liệu ghi bằng schema cũ không? | New reader ← Old writer |
| Forward | Reader schema cũ có đọc được dữ liệu ghi bằng schema mới không? | Old reader ← New writer |
| Full | Cả hai chiều đều đọc được không? | New reader ↔ Old writer |
| None | Có kiểm tra tương thích trước khi đăng ký schema không? | Không có bảo đảm từ registry |

Trong Confluent Schema Registry, BACKWARD là mặc định và kiểm tra schema mới với phiên bản gần nhất. Cấu hình BACKWARD_TRANSITIVE kiểm tra với tất cả phiên bản trước đó. Các mode FORWARD, FULL và biến thể transitive có ý nghĩa tương ứng. Quy tắc cụ thể thay đổi theo Avro, Protobuf và JSON Schema. https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html

### 4.1. Backward compatibility

Schema mới có thể đọc dữ liệu được ghi bằng schema cũ.

Ví dụ: consumer mới đọc message cũ không có field discountCode; reader schema cung cấp default null.

Backward compatibility hữu ích khi triển khai consumer trước, sau đó mới cho producer phát schema mới. Consumer mới đã sẵn sàng đọc message cũ trước khi producer đổi định dạng.

### 4.2. Forward compatibility

Schema cũ có thể đọc dữ liệu được ghi bằng schema mới.

Ví dụ: producer mới thêm field tùy chọn, nhưng consumer cũ có thể bỏ qua field không biết nếu format/parser cho phép.

Forward compatibility hữu ích khi producer được nâng cấp trước, trong khi consumer cũ vẫn còn hoạt động. Tuy nhiên, không phải mọi parser đều bỏ qua unknown fields; JSON Schema với object đóng có thể từ chối field mới.

### 4.3. Full compatibility

Full yêu cầu cả hai chiều backward và forward đều đạt.

Điều này có ích trong rolling deployment khi phiên bản producer và consumer mới/cũ có thể cùng hoạt động trong một khoảng thời gian. Tuy vậy, full compatibility giữa hai schema liền kề chưa bảo đảm đọc được tất cả message rất cũ.

### 4.4. Transitive compatibility

Giả sử hệ thống có schema v1, v2, v3, v4:

- Non-transitive chỉ kiểm tra v4 với v3.
- Transitive kiểm tra v4 với tất cả phiên bản cũ trong phạm vi policy.

Điều này quan trọng với queue lưu message lâu, event archive, replay hoặc consumer offline nhiều tháng. Một thay đổi có thể tương thích với phiên bản ngay trước đó nhưng không tương thích với v1.

### 4.5. Compatibility không đồng nghĩa semantic correctness

Registry có thể xác nhận hai schema tương thích về cấu trúc, nhưng không biết:

- total trước đây là VND, nay producer gửi USD.
- customerId đổi từ mã CRM sang mã loyalty.
- createdAt trước đây là UTC, nay bị gửi theo giờ địa phương.
- Một giá trị enum mới mang ý nghĩa mà consumer cũ không hiểu.

Schema compatibility là một hàng rào quan trọng, nhưng không thay thế review hợp đồng và kiểm thử nghiệp vụ.

## 5. Phân biệt thay đổi an toàn và thay đổi phá vỡ hợp đồng

### 5.1. Những thay đổi thường dễ tương thích hơn

- Thêm field tùy chọn với default phù hợp.
- Thêm metadata không làm thay đổi ý nghĩa field hiện có.
- Thêm extension mà consumer có thể bỏ qua.
- Mở rộng enum nếu consumer có chiến lược xử lý giá trị chưa biết.
- Bổ sung field mới mà consumer cũ đã được thiết kế để bỏ qua.

Mức độ tương thích vẫn phụ thuộc format và cấu hình parser. Không có quy tắc “thêm field luôn an toàn” áp dụng cho mọi hệ thống.

### 5.2. Những thay đổi có nguy cơ breaking

| Thay đổi | Rủi ro |
| --- | --- |
| Xóa field consumer đang bắt buộc | Consumer không đọc được hoặc mất dữ liệu. |
| Thêm field required không có default | Reader cũ hoặc mới có thể không tạo được object. |
| Đổi tên field | Consumer cũ không tìm thấy field; dữ liệu mới có thể không được ánh xạ. |
| Đổi kiểu dữ liệu | Deserialize thất bại hoặc mất độ chính xác. |
| Đổi ý nghĩa/đơn vị field | Parse thành công nhưng nghiệp vụ sai. |
| Xóa enum value đang được dùng | Consumer hoặc producer có thể không hiểu giá trị lịch sử. |
| Thay đổi nesting/path | JSONPath, mapper hoặc code generated có thể hỏng. |
| Đổi timezone/format timestamp | Sai thời điểm dù giá trị vẫn parse được. |

### 5.3. Ví dụ đổi tên field

Không nên đổi trực tiếp customerId thành buyerId trong một lần deploy nếu consumer chưa đồng bộ.

Một cách chuyển tiếp:

1. Producer phát cả customerId và buyerId trong thời gian migration, nếu semantics hai field thực sự giống nhau.
2. Consumer mới đọc buyerId, đồng thời hỗ trợ customerId cũ.
3. Theo dõi số consumer còn dùng field cũ.
4. Dừng phát field cũ sau khi tất cả consumer đã chuyển.
5. Chỉ xóa field cũ ở schema version sau, khi replay/retention window đã được xem xét.

Nếu hai field không cùng ý nghĩa, không copy giá trị qua lại chỉ để giữ compatibility. Hãy phát event type hoặc schema version mới với mapping nghiệp vụ rõ ràng.

## 6. Quy tắc tiến hóa theo từng schema format

Một compatibility mode không tạo ra cùng kết quả cho mọi serialization format. Cần hiểu các quy tắc quan trọng của format đang dùng.

### 6.1. Avro

Avro có schema resolution dựa trên writer schema và reader schema.

Các lưu ý thực tế:

- Khi thêm field vào record, reader schema nên có default để đọc dữ liệu cũ thiếu field.
- Field nullable thường được mô tả bằng union có null, ví dụ ["null", "string"].
- Default của field phải tuân theo nhánh đầu tiên của union trong Avro.
- Field writer có nhưng reader không cần có thể được bỏ qua theo quy tắc resolution.
- Đổi type chỉ an toàn trong những trường hợp promotion được Avro hỗ trợ; không suy ra mọi phép đổi số đều an toàn.
- Dữ liệu binary cần writer schema để deserialize đúng.

Ví dụ field tùy chọn:

~~~json
{
  "name": "deliveryNote",
  "type": ["null", "string"],
  "default": null
}
~~~

Đừng nhầm nullable với có default. Một field cho phép null nhưng không có default vẫn có thể không giải quyết được trường hợp message cũ hoàn toàn không chứa field đó.

Tài liệu: https://avro.apache.org/docs/current/specification/

### 6.2. Protocol Buffers

Protobuf dùng field number làm định danh trên wire format. Field name có thể đổi trong một số trường hợp mà binary wire vẫn đọc được, nhưng field number không được thay đổi hoặc tái sử dụng.

Ví dụ:

~~~protobuf
syntax = "proto3";

message OrderCreated {
  string order_id = 1;
  string customer_id = 2;
  int64 total_minor_units = 4;

  reserved 3;
  reserved "legacy_customer_code";
}
~~~

Khi xóa field:

- Reserve field number đã xóa.
- Reserve field name nếu cần bảo vệ JSON/TextFormat.
- Không dùng lại số tag cũ cho field mới.
- Không thay đổi type của field đang dùng chỉ vì code Java có thể cast.
- Thêm enum value cần tính đến consumer có thể nhận giá trị chưa biết.

Tái sử dụng field number có thể khiến dữ liệu cũ bị diễn giải thành field hoàn toàn khác. Đây là lỗi nghiêm trọng hơn một exception deserialize thông thường. https://protobuf.dev/programming-guides/proto3/

### 6.3. JSON Schema

JSON Schema mô tả cấu trúc và validation của JSON. Bản thân JSON Schema không quy định một compatibility mode duy nhất cho mọi registry.

Một điểm quan trọng là object có cho phép field chưa khai báo hay không:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {"type": "string"},
    "customerId": {"type": "string"}
  },
  "required": ["orderId", "customerId"],
  "additionalProperties": true
}
~~~

Với additionalProperties: true, object có thể chứa field khác ngoài các field được liệt kê. Nếu đặt false, consumer/schema validator có thể từ chối field mới mà nó chưa biết.

Trong Confluent Schema Registry, compatibility behavior của JSON Schema còn phụ thuộc compatibilityPolicy (LENIENT hoặc STRICT) và schema mở hay đóng (additionalProperties). Vì vậy, phải kiểm tra policy thực tế của registry, không chỉ đọc file JSON Schema. https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html

### 6.4. So sánh format

| Tiêu chí | Avro | Protobuf | JSON Schema |
| --- | --- | --- | --- |
| Cách mô tả schema | Record/union/type trong Avro schema. | Message, field number, enum. | JSON Schema document. |
| Metadata schema | Writer schema phải được tìm thấy để đọc binary. | Descriptor/proto contract và wire tags. | Schema URI/registry reference tùy ứng dụng. |
| Thêm field | Dùng default phù hợp để reader cũ/mới xử lý. | Dùng tag mới chưa từng cấp; field optional phù hợp. | Phụ thuộc required, additionalProperties và registry policy. |
| Xóa field | Reader resolution và default quyết định. | Reserve tag và tên đã xóa. | Xem required, properties và open/closed object. |
| Rủi ro đặc biệt | Thiếu writer schema hoặc default sai. | Tái sử dụng field number gây đọc sai wire data. | Parser/policy đóng từ chối field mới. |
| Công cụ kiểm tra | Avro schema resolution/registry. | Protoc và compatibility checker. | JSON Schema validator/registry compatibility check. |

## 7. Schema Registry giúp gì và không giúp gì?

Schema Registry lưu schema theo subject/version, cung cấp schema reference cho producer/consumer và có thể kiểm tra compatibility khi đăng ký schema mới.

Một quy trình điển hình:

1. Producer lấy hoặc tạo schema từ payload type.
2. Producer đăng ký schema với registry.
3. Registry trả về schema version hoặc ID.
4. Serializer ghi reference/metadata schema vào message.
5. Consumer đọc reference để tìm writer schema.
6. Consumer dùng reader schema của phiên bản ứng dụng để deserialize.
7. Nếu schema không tương thích hoặc không tìm được, xử lý lỗi theo policy.

Schema Registry có thể chặn một schema breaking trước khi deploy nếu compatibility check được bật. Nó không bảo đảm consumer code không có lỗi nghiệp vụ, không tự cập nhật mọi ứng dụng và không giải quyết message đã phát bằng schema không còn tồn tại.

### 7.1. Compatibility mode phải phù hợp rollout

Ví dụ Confluent Schema Registry:

~~~text
BACKWARD
BACKWARD_TRANSITIVE
FORWARD
FORWARD_TRANSITIVE
FULL
FULL_TRANSITIVE
NONE
~~~

NONE bỏ qua compatibility check; không nên chọn chỉ để đăng ký schema nhanh khi hệ thống đang chạy production.

Đối với event replay dài hạn, cân nhắc transitive mode. Nếu chỉ cần consumer mới đọc được message của phiên bản liền trước và lịch sử cũ đã được migrate/retire, non-transitive có thể đủ, nhưng quyết định cần dựa trên retention và replay policy.

### 7.2. Registry không phải message broker

Registry không chịu trách nhiệm:

- Giao message.
- Retry consumer.
- Ack/nack.
- Quản lý thứ tự partition.
- Chuyển message lỗi vào DLQ.
- Bảo đảm schema ID vẫn tồn tại trong suốt thời gian message còn được lưu.

Phải đồng bộ retention của schema với retention của message/archive. Xóa schema còn được tham chiếu có thể khiến consumer không đọc được message lịch sử.

## 8. Triển khai thay đổi theo mô hình Expand–Migrate–Contract

Một quy trình triển khai an toàn nên mở rộng khả năng đọc trước, chuyển producer sau, rồi mới dọn field cũ.

~~~mermaid
flowchart TD
    A["1. Expand schema: thêm field tùy chọn"] --> B["2. Deploy consumer đọc cả cũ và mới"]
    B --> C["3. Xác nhận toàn bộ consumer đã sẵn sàng"]
    C --> D["4. Deploy producer bắt đầu ghi field mới"]
    D --> E["5. Theo dõi message cũ, mới và replay"]
    E --> F["6. Ngừng ghi field cũ"]
    F --> G["7. Chờ retention / replay window"]
    G --> H["8. Contract: xóa field cũ ở schema sau"]
~~~

### 8.1. Expand

- Thêm field mới dưới dạng optional nếu format hỗ trợ.
- Cung cấp default có ý nghĩa.
- Giữ field cũ trong schema.
- Đăng ký schema và chạy compatibility check.
- Kiểm tra consumer có thể parse cả message cũ lẫn mới.

### 8.2. Migrate

- Deploy consumer trước nếu policy là backward compatibility.
- Xác nhận consumer mới đã chạy ở mọi instance/region.
- Bắt đầu phát field mới từ producer.
- Theo dõi metric theo schema version và consumer version.
- Kiểm tra message backlog và DLQ.

### 8.3. Contract

- Ngừng phát field cũ.
- Chờ các message cũ hết retention hoặc bảo đảm reader vẫn hỗ trợ chúng.
- Chỉ xóa field cũ khi mọi consumer, replay job và analytics reader đã được kiểm tra.
- Giữ schema lịch sử nếu còn dữ liệu tham chiếu.

Không xóa field ngay sau khi deploy producer mới. Queue có thể chứa message cũ và DLQ có thể giữ message lâu hơn thời gian triển khai.

### 8.4. Khi nào cần full compatibility?

Trong rolling deployment, producer và consumer có thể nâng cấp lệch nhau. Nếu không thể kiểm soát thứ tự rollout hoặc có nhiều consumer độc lập, full compatibility giúp giảm rủi ro hơn.

Tuy nhiên, full compatibility có thể hạn chế các thay đổi schema. Với thay đổi breaking thật sự, tạo version/type mới và chạy hai đường xử lý song song thường rõ ràng hơn cố ép một schema duy nhất phục vụ mọi thế hệ.

## 9. Versioning message và upcasting dữ liệu cũ

Khi consumer cần một model nội bộ ổn định, có thể dùng adapter/upcaster để chuyển các schema cũ sang canonical model.

Ví dụ:

~~~text
OrderCreatedV1 ----\
                    +--> OrderCreatedCanonical --> processOrder
OrderCreatedV2 ----/
~~~

- OrderCreatedV1 giữ cấu trúc cũ.
- OrderCreatedV2 chứa field mới.
- Upcaster chuyển cả hai thành OrderCreatedCanonical.
- Business function chỉ xử lý canonical model.

Ví dụ Java:

~~~java
public record OrderCreatedV1(
        String orderId,
        String customerId,
        long total) {
}

public record OrderCreatedV2(
        String orderId,
        String customerId,
        long total,
        String discountCode) {
}

public record OrderCreatedCanonical(
        String orderId,
        String customerId,
        long total,
        String discountCode,
        int schemaVersion) {
}

public final class OrderUpcaster {

    public OrderCreatedCanonical fromV1(OrderCreatedV1 oldEvent) {
        return new OrderCreatedCanonical(
                oldEvent.orderId(),
                oldEvent.customerId(),
                oldEvent.total(),
                null,
                1);
    }

    public OrderCreatedCanonical fromV2(OrderCreatedV2 newEvent) {
        return new OrderCreatedCanonical(
                newEvent.orderId(),
                newEvent.customerId(),
                newEvent.total(),
                newEvent.discountCode(),
                2);
    }
}
~~~

Đây là ví dụ mapping đơn giản. Trong production, upcaster phải kiểm tra giá trị bắt buộc, đơn vị đo, currency, timestamp và các invariant nghiệp vụ. Không tự gán null nếu field mới có ý nghĩa bắt buộc; khi đó cần business migration hoặc từ chối message.

### 9.1. Upcasting không sửa message gốc

Nên giữ nguyên message gốc và schema reference để audit/replay. Upcasting tạo representation mới cho consumer hiện tại; không ghi đè dữ liệu lịch sử nếu không có quy trình migration riêng.

### 9.2. Không dùng một model canonical để che mọi khác biệt

Nếu event v1 và v2 mang semantics khác nhau, canonical model phải biểu diễn được khác biệt hoặc tách loại event. Ép hai payload khác nghĩa vào cùng một field có thể khiến hệ thống parse thành công nhưng xử lý sai.

## 10. Xử lý message không tương thích

Một message không đọc được có thể do nhiều nguyên nhân. Phải phân loại trước khi quyết định retry hay quarantine.

| Nguyên nhân | Phân loại thường gặp | Hành động |
| --- | --- | --- |
| Schema ID không tồn tại do registry tạm thời lỗi | Transient | Retry có giới hạn và backoff. |
| Schema ID đã bị xóa vĩnh viễn | Permanent/configuration | Quarantine, phục hồi schema hoặc mapping. |
| Schema version mới hơn consumer hỗ trợ | Incompatible version | Quarantine hoặc route tới consumer mới. |
| Payload JSON sai cú pháp | Poison message | Quarantine; không retry vô hạn. |
| Required field thiếu | Contract violation | Quarantine và điều tra producer. |
| Content-Type sai hoặc thiếu | Integration/configuration | Sửa adapter/producer; giữ raw message để replay. |
| Consumer bug với payload hợp lệ | Application failure | Retry nếu transient; sau đó DLQ. |
| Database tạm thời unavailable | Transient | Retry theo policy. |
| Payload parse được nhưng sai ý nghĩa nghiệp vụ | Semantic incompatibility | Reject/quarantine; cần sửa contract hoặc mapping. |

### 10.1. Schema incompatibility thường là lỗi permanent đối với cùng một consumer build

Nếu consumer không hiểu schema version 5 và không có decoder/upcaster, retry lại chính message đó với cùng binary thường không giúp ích.

Retry lặp vô hạn có thể:

- Giữ partition/queue backlog.
- Tăng chi phí.
- Chặn message hợp lệ phía sau.
- Tạo retry storm.
- Làm message lỗi khó được quan sát.

Hãy quarantine hoặc DLQ message sau khi xác định lỗi không thể tự hồi phục. Nếu schema registry đang tạm thời không truy cập được, đó lại là lỗi transient và có thể retry.

### 10.2. Quarantine và DLQ có vai trò khác nhau

- **Quarantine:** vùng cách ly để giữ message chưa thể xử lý, thường dùng cho payload/schema không hợp lệ hoặc cần điều tra.
- **DLQ:** đích mà broker/binder chuyển message sau khi hết retry hoặc bị reject theo delivery policy.

Một hệ thống có thể dùng DLQ làm quarantine destination, nhưng cần quy định ai phân loại, sửa và replay message. Không nên để message lỗi bị xóa âm thầm.

### 10.3. Dữ liệu cần giữ khi quarantine

Một record lỗi nên có:

- Raw payload hoặc bản lưu an toàn của bytes gốc.
- Message headers và content type.
- Schema ID/version hoặc schema reference.
- Event ID và source/producer.
- Destination/topic/partition/offset hoặc queue metadata nếu có.
- Consumer name, application build/version.
- Error category và error code.
- Thời điểm nhận, số lần thử và correlation/trace ID.
- Trạng thái xử lý, người/quy trình redrive.

Không ghi raw payload nhạy cảm vào log không kiểm soát. Dùng encryption, access policy, retention và audit phù hợp.

## 11. Quy trình redrive message lỗi

Redrive là phát lại message đã bị cách ly. Đây là một thao tác có rủi ro tạo side effect trùng hoặc tiếp tục gây lỗi.

Trước khi replay:

1. Xác định lỗi gốc: producer contract, schema registry, consumer code hay dependency.
2. Sửa nguyên nhân và triển khai decoder/upcaster phù hợp.
3. Xác minh schema gốc vẫn có thể được tìm thấy.
4. Kiểm tra message đã tạo side effect một phần hay chưa.
5. Giữ nguyên event ID/idempotency key.
6. Chạy thử một vài message trong môi trường kiểm soát.
7. Giới hạn tốc độ replay để không gây tải đột biến.
8. Theo dõi success/failure và lưu audit trail.

Không sửa payload trong DLQ bằng thao tác thủ công nếu không có quy trình kiểm soát. Nếu cần transform dữ liệu, lưu cả bản gốc, bản đã chuyển và mapping version.

## 12. Tích hợp với Spring Cloud Function

### 12.1. FunctionCatalog không phải Schema Registry

FunctionCatalog quản lý lookup/wrapper cho functional beans, composition và một số cơ chế conversion. Nó không tự đăng ký schema, không giữ toàn bộ lịch sử writer schema và không tự quyết định compatibility policy.

Khi function nhận Message<?>, Spring Cloud Function dùng MessageConverter và ConversionService để chuyển payload sang kiểu tham số của function. Việc chọn converter dựa trên kiểu đích và contentType header; nếu không có converter phù hợp, framework ném exception. https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html

Vì vậy, cần tách các trách nhiệm:

| Thành phần | Trách nhiệm |
| --- | --- |
| Producer serializer | Serialize payload theo schema đã chọn. |
| Schema Registry | Lưu schema/version và kiểm tra compatibility theo policy. |
| Broker/binder | Giao message, retry, ack/nack, DLQ theo capability. |
| Adapter/message converter | Đọc content type/schema reference, deserialize và tạo Message. |
| FunctionCatalog | Lookup/wrap function và cung cấp function invocation/conversion integration. |
| Business function | Xử lý nghiệp vụ trên model đã được kiểm tra. |
| Quarantine service | Lưu message không thể xử lý để điều tra/redrive. |

### 12.2. Spring Cloud Stream có tích hợp Avro Schema Registry

Spring Cloud Stream có thể dùng SchemaRegistryClient để đăng ký schema Avro khi gửi và lấy writer schema khi nhận. Converter đặt thông tin subject/version trong contentType; khi đọc, nó lấy writer schema, sau đó dùng reader schema để resolve sang model consumer. Thuộc tính spring.cloud.stream.schema.avro.readerSchema cho phép cấu hình reader schema cục bộ. https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html

Đây là chức năng của Spring Cloud Stream và schema registry integration, không phải chỉ riêng FunctionCatalog.

Ví dụ cấu hình minh họa cho binding:

~~~properties
spring.cloud.function.definition=processOrder
spring.cloud.stream.bindings.processOrder-in-0.destination=orders
spring.cloud.stream.bindings.processOrder-in-0.group=orders-v2
spring.cloud.stream.bindings.processOrder-in-0.content-type=application/*+avro
~~~

Tên binding processOrder-in-0 được tạo từ function definition theo quy tắc functional binding. Cấu hình thực tế còn cần binder, broker và SchemaRegistryClient phù hợp.

### 12.3. Consumer function nhận model đã deserialize

~~~java
@Bean
public Consumer<OrderCreatedCanonical> processOrder(
        OrderService orderService) {

    return event -> orderService.createOrder(
            event.orderId(),
            event.customerId(),
            event.total(),
            event.discountCode());
}
~~~

Function nghiệp vụ nhận canonical model. Nó không cần biết message gốc được serialize bằng Avro, JSON hay Protobuf nếu adapter đã chuyển đổi đúng.

### 12.4. Khi nào nên nhận raw bytes?

Nếu muốn chủ động phân loại schema incompatibility trước khi business function chạy, adapter có thể nhận Message<byte[]>:

~~~java
@Bean
public Consumer<Message<byte[]>> ingestOrder(
        OrderDecoder decoder,
        OrderQuarantine quarantine,
        OrderService orderService) {

    return message -> {
        try {
            OrderCreatedCanonical event =
                    decoder.decode(message.getPayload(), message.getHeaders());

            orderService.createOrder(event);
        } catch (UnsupportedSchemaException exception) {
            // Chỉ return bình thường sau khi quarantine đã lưu bền vững.
            quarantine.store(message, "UNSUPPORTED_SCHEMA", exception);
        } catch (TemporaryRegistryException exception) {
            // Để binder/trigger retry theo policy.
            throw new RetryableMessageException(exception);
        }
    };
}
~~~

Đây là code minh họa; OrderDecoder, OrderQuarantine và exception là abstraction của ứng dụng. Để nhận đúng raw bytes, binding/adapter phải giữ payload thô (ví dụ dùng `application/octet-stream` hoặc converter tùy chỉnh); chỉ đổi chữ ký function thành `Message<byte[]>` không bảo đảm mọi binder đều bỏ qua bước deserialize trước đó. Trong production:

- UnsupportedSchemaException chỉ được quarantine sau khi raw message đã được lưu bền vững.
- Nếu lưu quarantine thất bại, phải ném exception để message chưa bị ack.
- Lỗi registry tạm thời nên được retry có giới hạn.
- Không catch mọi Exception rồi return bình thường, vì binder có thể coi message đã thành công.
- Nếu framework deserialize trước khi function được gọi, exception có thể phát sinh ngoài ingestOrder. Dùng raw bytes khi cần kiểm soát bước decode, hoặc cấu hình error handler phù hợp với binder.

## 13. Retry, DLQ và binder-specific behavior

Spring Cloud Function không định nghĩa một DLQ chung cho mọi transport. Khi dùng Spring Cloud Stream, binder và broker quyết định các tính năng có sẵn.

### 13.1. Exception phải đi tới tầng xử lý lỗi

Khi message handler ném exception, Spring Cloud Stream có thể chuyển exception về binder. Binder có thể retry rồi drop, requeue hoặc gửi DLQ tùy cấu hình và khả năng middleware. Không phải binder nào cũng có cùng behavior. https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html

### 13.2. Ví dụ Kafka binder

Kafka binder hỗ trợ DLQ cho consumer có consumer group. Ví dụ cấu hình:

~~~properties
spring.cloud.function.definition=processOrder
spring.cloud.stream.bindings.processOrder-in-0.destination=orders
spring.cloud.stream.bindings.processOrder-in-0.group=orders-v2
spring.cloud.stream.bindings.processOrder-in-0.consumer.max-attempts=3
spring.cloud.stream.kafka.bindings.processOrder-in-0.consumer.enable-dlq=true
~~~

Khi đã bật DLQ, binder có thể gửi record lỗi tới dead-letter topic sau khi retry hết số lần cấu hình. Cấu hình DLQ không bật mặc định; consumer group là yêu cầu quan trọng. Hành vi cụ thể cần xác minh theo version binder đang dùng. https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html

### 13.3. Phân loại exception trước retry

Một chính sách đơn giản:

| Exception category | Hành động |
| --- | --- |
| Temporary network/registry error | Retry có giới hạn. |
| Database unavailable | Retry có backoff. |
| Unsupported schema version | Quarantine/DLQ, chờ consumer mới. |
| Invalid payload | Quarantine/DLQ, không retry vô hạn. |
| Business rule violation | Từ chối theo nghiệp vụ; không retry như lỗi hạ tầng. |
| Unknown application bug | Retry có giới hạn, alert và DLQ nếu hết attempts. |

Không nên coi mọi MessageConversionException là transient. Nếu payload sai schema cố định, retry không thay đổi kết quả. Nếu converter không truy cập được registry do network, retry có thể giúp.

### 13.4. Không để message lỗi chặn partition vô hạn

Với Kafka, record lỗi có thể khiến consumer không commit offset theo policy, làm partition không tiến lên. Cần thiết kế retry topic, DLQ hoặc pause/retry strategy phù hợp. Khi replay, giữ key và ordering semantics nếu nghiệp vụ yêu cầu.

## 14. Idempotency khi chuyển đổi hoặc replay message

Một message có thể được xử lý lại vì retry, redrive, consumer restart hoặc replay lịch sử. Khi schema mới được upcast từ schema cũ, event vẫn là cùng một occurrence.

Dùng khóa ổn định, ví dụ:

~~~text
(source, eventId)
~~~

hoặc khóa business operation đã thống nhất. Không tạo idempotency key mới chỉ vì consumer build hoặc schema version thay đổi.

Nếu upcaster phát sinh event mới thay vì chỉ chuyển representation, cần phân biệt:

- Original event identity.
- Derived event identity.
- Transformation/upcaster version.

Nếu không, một lần replay có thể tạo side effect lặp hoặc khiến trace khó nối.

## 15. Ví dụ tình huống: đổi cấu trúc OrderCreated

Giả sử schema v1:

~~~json
{
  "orderId": "ORD-42",
  "customerId": "CUS-18",
  "total": 1250000,
  "currency": "VND"
}
~~~

Nhóm muốn schema v2:

~~~json
{
  "orderId": "ORD-42",
  "buyer": {
    "id": "CUS-18",
    "segment": "GOLD"
  },
  "total": {
    "amount": "1250000.00",
    "currency": "VND"
  },
  "discountCode": null
}
~~~

Đây là thay đổi lớn: customerId chuyển vào object buyer, total đổi kiểu từ scalar sang object và thêm discountCode.

Không nên deploy producer v2 ngay lập tức. Một kế hoạch có thể là:

1. Xác định canonical model và semantics chính xác của total.
2. Tạo schema v2 và kiểm tra compatibility với v1.
3. Viết adapter/upcaster đọc v1 và v2.
4. Deploy consumer hỗ trợ cả hai schema.
5. Xác nhận tất cả consumer instance và replay worker đã nâng cấp.
6. Bắt đầu phát v2.
7. Theo dõi tỉ lệ message v1/v2 và lỗi decode.
8. Chờ backlog, archive và DLQ cũ được xử lý.
9. Chỉ dừng hỗ trợ v1 khi retention/replay window đã kết thúc hoặc có migration riêng.

Nếu schema registry báo breaking, đó là tín hiệu cần một migration plan hoặc versioned subject/type mới; không nên hạ compatibility policy chỉ để vượt qua kiểm tra.

## 16. Kiểm thử hợp đồng trước khi deploy

Một bộ kiểm thử schema evolution nên bao gồm:

| Test | Câu hỏi cần trả lời |
| --- | --- |
| Old writer → new reader | Consumer mới có đọc message cũ không? |
| New writer → old reader | Consumer cũ có đọc message mới không? |
| Historical writer → latest reader | Có đọc được tất cả schema còn trong retention không? |
| Missing optional field | Default có đúng nghiệp vụ không? |
| Unknown field | Parser có bỏ qua hay từ chối theo policy? |
| Unknown enum | Consumer có xử lý an toàn không? |
| Type mismatch | Có lỗi rõ ràng trước side effect không? |
| Missing schema ID | Retry hay quarantine theo nguyên nhân? |
| Registry unavailable | Retry có giới hạn không? |
| Malformed payload | Raw message có được giữ lại không? |
| DLQ redrive | Message cũ có được decode sau khi sửa consumer không? |
| Duplicate replay | Side effect có được bảo vệ bằng idempotency không? |

### 16.1. Contract test cho writer và reader schema

Lưu fixture đại diện cho từng schema version trong source control hoặc test artifact store. Mỗi lần thay đổi consumer:

1. Đọc fixture cũ bằng decoder mới.
2. Đọc fixture mới bằng decoder cũ nếu rollout yêu cầu forward compatibility.
3. So sánh canonical model sau upcast.
4. Kiểm tra business invariants.
5. Kiểm tra trường hợp không tương thích được quarantine đúng.

Không chỉ test schema JSON bằng parser. Cần test bytes thực tế đã được serializer ghi ra, kèm content type/schema reference.

### 16.2. Kiểm thử integration với binder

- Gửi message hợp lệ và xác nhận function được gọi.
- Gửi message không tương thích và xác nhận raw payload được giữ.
- Làm registry tạm thời không truy cập được và xác nhận retry/backoff.
- Làm quarantine storage thất bại và xác nhận message không bị ack.
- Xác nhận DLQ destination, metadata và redrive.
- Gửi cùng event hai lần và xác nhận idempotency.

## 17. Lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đổi DTO và cho rằng producer/consumer cùng nâng cấp | Consumer cũ nhận payload mới và lỗi. | Dùng compatibility check và rollout theo giai đoạn. |
| Thêm required field không có default | Message lịch sử không deserialize được. | Thêm optional/default hoặc versioned contract. |
| Đổi type mà không migration | Mất độ chính xác hoặc conversion failure. | Tạo schema version mới và adapter rõ ràng. |
| Xóa field ngay khi producer ngừng ghi | DLQ/archive cũ không còn đọc được. | Chờ retention/replay window hoặc giữ upcaster. |
| Chỉ kiểm tra schema liền trước | Message rất cũ có thể không tương thích. | Dùng transitive compatibility khi cần. |
| Dùng NONE để ép đăng ký schema | Breaking change lọt vào production. | Sửa schema hoặc thực hiện migration có kiểm soát. |
| Dùng default giả để parser qua | Dữ liệu nghiệp vụ sai nhưng khó phát hiện. | Chỉ dùng default có ý nghĩa domain. |
| Retry vô hạn schema không hỗ trợ | Backlog và poison message. | Quarantine/DLQ, chờ consumer hỗ trợ. |
| Catch exception rồi return success | Broker có thể ack message lỗi. | Chỉ return sau khi quarantine bền vững; lỗi transient phải throw. |
| Xóa schema registry version còn được message tham chiếu | Không deserialize được message lịch sử. | Giữ schema theo retention của data. |
| Cho FunctionCatalog tự parse schema registry | Sai trách nhiệm framework. | Cấu hình converter/adapter/SchemaRegistryClient phù hợp. |
| Replay mà tạo event ID mới | Side effect bị thực hiện lặp. | Giữ nguyên event identity và idempotency key. |

## 18. Bài tập tình huống

### Bài 1 — Chọn compatibility mode

Producer đang dùng schema v1. Consumer mới sẽ được deploy trước producer mới. Consumer mới phải đọc được message v1 đang nằm trong queue.

1. Nên kiểm tra backward hay forward compatibility?
2. Vì sao default field có thể cần thiết?
3. Nếu message v1 vẫn được replay sau sáu tháng, non-transitive backward có đủ không?

**Gợi ý:** New reader cần đọc old writer, vì vậy cần backward compatibility. Nếu cần đọc mọi phiên bản lịch sử, đánh giá backward-transitive và giữ schema cũ.

### Bài 2 — Field mới trong JSON Schema

Consumer cũ dùng JSON Schema có additionalProperties: false. Producer mới thêm field discountCode.

1. Vì sao parser cũ có thể từ chối payload?
2. Thay đổi schema consumer như thế nào để chấp nhận field mới?
3. Nếu field mới mang ý nghĩa bắt buộc, có thể bỏ qua an toàn không?

### Bài 3 — Protobuf field number

Một developer xóa customer_id = 2 và tạo buyer_id = 2 với ý nghĩa khác.

1. Vì sao thay đổi này nguy hiểm?
2. Phải dùng reserved như thế nào?
3. Nếu chỉ đổi field name nhưng giữ semantics và tag number, còn điều gì cần kiểm tra ở JSON/TextFormat?

### Bài 4 — Schema Registry tạm thời mất kết nối

Consumer không lấy được writer schema do registry timeout.

1. Đây là lỗi permanent hay transient?
2. Retry/backoff nên được giới hạn thế nào?
3. Nếu schema ID thực sự không tồn tại, có nên tiếp tục retry không?
4. Cần lưu những metadata nào khi quarantine?

### Bài 5 — Spring Cloud Function nhận message không tương thích

Một bean Consumer<OrderCreated> không được gọi vì payload không chuyển được sang OrderCreated.

1. Vì sao lỗi có thể xảy ra trước business function?
2. contentType và function target type tham gia conversion ra sao?
3. Khi nào nên dùng Consumer<Message<byte[]>>?
4. Vì sao FunctionCatalog không tự giải quyết schema version?

### Bài 6 — Redrive sau khi nâng cấp consumer

DLQ có 20.000 message schema v1. Consumer hiện tại chỉ xử lý v2.

Thiết kế quy trình:

- Khôi phục schema v1.
- Viết upcaster v1 → canonical model.
- Kiểm tra idempotency.
- Replay theo tốc độ giới hạn.
- Theo dõi message đã xử lý và lỗi còn lại.
- Giữ audit trail cho toàn bộ đợt redrive.

### Bài 7 — Thay đổi ý nghĩa field

total trước đây là số tiền VND, nay producer gửi giá trị USD nhưng vẫn giữ tên và kiểu dữ liệu.

1. Schema Registry có thể phát hiện thay đổi này không?
2. Vì sao đây là breaking semantic change dù schema tương thích?
3. Nên dùng field/currency mới, event type mới hay schema version mới?
4. Consumer cần migration nào để không tính sai giá trị?

## 19. Checklist trước khi phát hành schema mới

| Hạng mục | Cần xác nhận |
| --- | --- |
| Event contract | Event type và semantics có giữ nguyên không? |
| Schema identity | Subject, schema ID/version và retention được quản lý ra sao? |
| Compatibility | Backward, forward, full hay transitive phù hợp rollout nào? |
| Format rules | Avro default, Protobuf reserved tags, JSON Schema open/closed policy. |
| Consumer coverage | Tất cả consumer và replay worker đã hỗ trợ schema mới chưa? |
| Producer rollout | Consumer đã sẵn sàng trước khi producer phát dữ liệu mới chưa? |
| Historical data | Message backlog, archive và DLQ cũ còn được đọc không? |
| Conversion | Content type, writer schema, reader schema và custom converter đã đúng chưa? |
| Failure handling | Unsupported schema, corrupt payload và registry outage được phân loại chưa? |
| Quarantine/DLQ | Raw payload, schema reference, error code và audit metadata được giữ chưa? |
| Idempotency | Retry/redrive có giữ nguyên event identity không? |
| Testing | Old/new writer-reader matrix và binder integration test đã chạy chưa? |
| Rollback | Có thể dừng producer mới hoặc rollback consumer mà không mất message không? |

## 20. Tổng kết và tài liệu chính thức

**Tiến hóa hợp đồng dữ liệu là quá trình phối hợp producer, consumer, schema, adapter và broker.** Một thay đổi schema chỉ an toàn khi các phiên bản đang chạy, message đang lưu và quy trình replay đều được tính đến.

Ghi nhớ:

- Backward: reader mới đọc dữ liệu writer cũ.
- Forward: reader cũ đọc dữ liệu writer mới.
- Full: cả hai chiều; transitive kiểm tra cả lịch sử schema.
- Quy tắc compatibility khác nhau giữa Avro, Protobuf và JSON Schema.
- Dùng default có ý nghĩa, field optional và rollout expand–migrate–contract.
- Giữ writer schema/schema ID theo thời gian tồn tại của message.
- Upcaster chuyển dữ liệu cũ sang canonical model mà vẫn giữ message gốc.
- Schema incompatibility cố định nên quarantine/DLQ; lỗi registry tạm thời có thể retry.
- FunctionCatalog không phải Schema Registry; contentType, function target type và MessageConverter quyết định conversion trong Spring Cloud Function.
- Retry, DLQ và acknowledgement phụ thuộc binder/broker; chỉ xác nhận message sau khi xử lý hoặc quarantine đã bền vững.
- Giữ event identity và idempotency key khi replay.

**Tài liệu tham khảo chính thức:**

1. Confluent Schema Registry — Schema Evolution and Compatibility: https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html
2. Confluent Schema Registry — Compatibility Types and Transitive Modes: https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html
3. Apache Avro — Specification, Schema Resolution: https://avro.apache.org/docs/current/specification/
4. Protocol Buffers — Proto3 Language Guide, deleting fields and reserving numbers: https://protobuf.dev/programming-guides/proto3/
5. Protocol Buffers — Proto3 Language Specification: https://protobuf.dev/reference/protobuf/proto3-spec/
6. JSON Schema — Core and Validation Specifications: https://json-schema.org/specification
7. Spring Cloud Function — Message Conversion and Programming Model: https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html
8. Spring Cloud Stream — Schema Registry and Avro Schema Resolution: https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html
9. Spring Cloud Stream — Error Handling and Retry: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html
10. Spring Cloud Stream — Kafka Binder Dead-Letter Topic Processing: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html
