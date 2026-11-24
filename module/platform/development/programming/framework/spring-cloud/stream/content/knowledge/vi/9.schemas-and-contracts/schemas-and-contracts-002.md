# Chọn JSON, Avro hoặc Protobuf theo yêu cầu tương tác

Trong hệ thống hướng sự kiện, producer và consumer có thể được phát triển bằng ngôn ngữ khác nhau, triển khai ở thời điểm khác nhau và do những nhóm khác nhau quản lý. Vì vậy, payload cần một hợp đồng rõ ràng: hai phía phải hiểu cùng ý nghĩa của trường dữ liệu, cách biểu diễn kiểu dữ liệu và quy tắc thay đổi phiên bản. JSON, Avro và Protobuf đều có thể dùng để trao đổi sự kiện, nhưng chúng giải quyết các ưu tiên khác nhau.

JSON thường thuận tiện khi cần khả năng đọc trực tiếp và tích hợp rộng. Avro phù hợp với hệ thống có schema được quản lý, cần dữ liệu nhị phân gọn và cơ chế tương thích giữa phiên bản. Protobuf phù hợp khi muốn hợp đồng kiểu mạnh, mã sinh tự động và payload nhị phân hiệu quả cho nhiều ngôn ngữ. Không có định dạng tốt nhất cho mọi tình huống; lựa chọn nên dựa trên yêu cầu tương tác, tốc độ thay đổi schema, năng lực vận hành và hệ sinh thái công nghệ.

## 1. Hợp đồng message gồm những gì?

Định dạng tuần tự hóa chỉ là một phần của hợp đồng. Trước khi chọn JSON, Avro hay Protobuf, hãy xác định:

- **Tên và ý nghĩa sự kiện:** OrderCreated có nghĩa là đơn hàng đã được tạo thành công, không phải yêu cầu tạo đơn.
- **Payload và kiểu dữ liệu:** trường nào bắt buộc, trường nào có thể vắng mặt, đơn vị đo, quy tắc null và giới hạn giá trị.
- **Định danh và thời điểm:** eventId, orderId, occurredAt và correlationId giúp phát hiện trùng lặp, sắp xếp theo nghiệp vụ và truy vết.
- **Phiên bản schema:** consumer cũ sẽ phản ứng thế nào khi producer thêm trường hoặc thay đổi cấu trúc.
- **Quy tắc tương thích:** có cho phép consumer cũ đọc dữ liệu mới không, producer mới có đọc được dữ liệu cũ không, và ai chịu trách nhiệm phê duyệt thay đổi.
- **Cách tuần tự hóa:** media type, serializer, deserializer hoặc message converter mà hai phía sử dụng.

Một broker chỉ vận chuyển byte và metadata. Broker không tự biết trường total là tiền tệ, orderId là định danh hay eventType có nghĩa gì. Producer và consumer cần thống nhất hợp đồng ngoài việc cùng kết nối đến một destination.

## 2. So sánh JSON, Avro và Protobuf

| Tiêu chí | JSON | Avro | Protobuf |
|---|---|---|---|
| Dạng dữ liệu | Văn bản có cấu trúc | Nhị phân, schema định nghĩa bằng JSON | Nhị phân, schema định nghĩa bằng file .proto |
| Khả năng đọc trực tiếp | Cao | Thấp khi nhìn payload nhị phân | Thấp khi nhìn payload nhị phân |
| Kiểu dữ liệu | Linh hoạt; cần schema hoặc validation để ràng buộc | Kiểu dữ liệu được mô tả trong schema | Kiểu dữ liệu mạnh, có mã sinh từ schema |
| Kích thước và tốc độ | Thường lớn hơn do tên trường và ký tự văn bản | Thường gọn, hiệu quả cho luồng dữ liệu lớn | Thường gọn, hiệu quả cho trao đổi nhị phân |
| Tiến hóa schema | Cần quy ước và validation | Có quy tắc writer schema/reader schema | Dựa trên field number và quy tắc tương thích |
| Công cụ | Rất phổ biến trên web và API | Phổ biến trong hệ sinh thái dữ liệu và streaming | Phổ biến trong hệ thống đa ngôn ngữ và RPC |
| Phù hợp khi | Dễ tích hợp, dễ quan sát, tải vừa phải | Cần schema registry và quản lý phiên bản dữ liệu | Cần hợp đồng kiểu mạnh, mã sinh và payload gọn |

Các nhận xét về kích thước và tốc độ là xu hướng, không phải bảo đảm tuyệt đối. Kết quả phụ thuộc vào cấu trúc dữ liệu, serializer, nén, kích thước batch, ngôn ngữ và cách triển khai. Hãy đo bằng payload thực tế trước khi quyết định dựa trên benchmark chung.

## 3. JSON: dễ tích hợp và dễ quan sát

JSON biểu diễn object bằng các cặp tên trường và giá trị. Con người có thể đọc payload trực tiếp trong log, công cụ dòng lệnh hoặc giao diện quản trị broker:

~~~json
{
  "eventId": "evt-7f31",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "ORD-1001",
  "customerId": "CUS-204",
  "totalMinorUnits": 12550,
  "currency": "VND",
  "occurredAt": "2026-11-24T09:30:00Z"
}
~~~

Ưu điểm của JSON:

- Hầu hết ngôn ngữ và nền tảng đều có thư viện đọc/ghi JSON.
- Dễ kiểm tra khi phát triển, tích hợp với REST API và công cụ quan sát.
- Có thể thêm trường mà nhiều parser vẫn đọc được nếu consumer bỏ qua trường chưa biết.
- Không bắt buộc mọi consumer phải sinh mã từ một schema trước khi đọc payload.

JSON không tự cung cấp kiểm tra hợp đồng. Một payload có thể hợp lệ về cú pháp nhưng sai nghiệp vụ, chẳng hạn totalMinorUnits là chuỗi thay vì số hoặc currency bị thiếu. Dùng JSON Schema, validation trong ứng dụng hoặc contract test để kiểm tra kiểu, trường bắt buộc và giới hạn giá trị.

Ví dụ cấu hình JSON cho binding Spring Cloud Stream:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
          content-type: application/json
~~~

Với content type application/json, Spring Cloud Stream có thể dùng message converter phù hợp để chuyển object Java thành JSON khi phát và chuyển JSON thành kiểu Java khi nhận. Consumer vẫn cần xác thực payload và áp dụng quy tắc tương thích. Đừng hiểu rằng đặt content-type là đã có schema validation.

JSON phù hợp khi các dịch vụ cần tích hợp nhanh, payload không quá lớn, khả năng quan sát quan trọng và nhóm phát triển có thể duy trì quy ước trường cùng contract test. Khi luồng có lưu lượng rất cao hoặc schema thay đổi phức tạp, cần đánh giá thêm chi phí kích thước, parse và quản lý hợp đồng.

## 4. Avro: schema rõ ràng và dữ liệu nhị phân

Avro là định dạng tuần tự hóa có schema. Schema mô tả tên record, trường và kiểu dữ liệu. Dữ liệu được mã hóa nhị phân nên không chứa lặp lại tên trường như JSON. Trong hệ thống streaming, producer và consumer thường dùng schema registry hoặc một cơ chế phân phối schema để tìm đúng schema của message.

Ví dụ schema Avro cho sự kiện OrderCreated:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.orders",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "customerId", "type": "string" },
    { "name": "totalMinorUnits", "type": "long" },
    { "name": "currency", "type": "string", "default": "VND" }
  ]
}
~~~

Avro có hai khái niệm quan trọng:

- **Writer schema:** schema mà producer sử dụng để mã hóa record.
- **Reader schema:** schema mà consumer sử dụng để đọc record.

Khi writer schema và reader schema khác nhau, Avro có thể phân giải khác biệt theo quy tắc schema resolution. Ví dụ, reader có thể cung cấp giá trị mặc định cho trường mới mà writer cũ chưa gửi. Khả năng đọc tương thích phụ thuộc vào thay đổi cụ thể và cách schema được phân phối.

### Schema evolution với Avro

Giả sử phiên bản đầu chỉ có eventId, orderId và totalMinorUnits. Phiên bản tiếp theo thêm currency với default là VND. Consumer mới có thể đọc record cũ và lấy giá trị mặc định nếu schema được thiết kế đúng. Trong Avro, default trong reader schema được dùng khi record do writer cũ tạo ra không có trường đó; nó không tự động buộc producer ghi giá trị mặc định vào mọi record. Khi thêm trường không có default, một reader mới có thể không đọc được dữ liệu cũ vì record cũ không chứa trường đó.

Khi đổi tên trường, cân nhắc aliases để reader schema nhận diện tên cũ. Khi đổi kiểu dữ liệu, kiểm tra quy tắc promotion của Avro và kiểm thử cả chiều đọc dữ liệu cũ lẫn mới. Không xem việc thêm default là cách sửa mọi thay đổi không tương thích; cần xác định chính xác writer schema, reader schema và thứ tự triển khai.

### Schema Registry

Schema registry lưu schema và các phiên bản, đồng thời có thể thực thi chính sách tương thích như backward, forward hoặc full. Serializer thường đăng ký hoặc tra cứu schema, sau đó ghi thông tin nhận diện schema vào payload theo quy ước của hệ sinh thái đang dùng. Consumer sử dụng thông tin đó để lấy schema phù hợp trước khi giải mã.

Registry không phải broker và cũng không thay thế destination. Broker lưu chuyển message; registry quản lý hợp đồng schema. Cách gắn schema ID vào message phụ thuộc serializer và registry được chọn, không phải một định dạng chung bắt buộc của mọi broker.

Avro phù hợp khi nhiều nhóm cùng sản xuất/tiêu thụ sự kiện, cần quản lý phiên bản có kiểm soát, payload lớn hoặc cần tối ưu kích thước và có năng lực vận hành registry.

## 5. Protobuf: hợp đồng kiểu mạnh và mã sinh tự động

Protocol Buffers (Protobuf) định nghĩa message trong file .proto. Công cụ protoc sinh class và mã tuần tự hóa cho ngôn ngữ mục tiêu. Mỗi trường có tên, kiểu và một số thứ tự (field number); dữ liệu nhị phân sử dụng số trường để mã hóa thay vì lặp tên trường.

Ví dụ:

~~~protobuf
syntax = "proto3";

package orders.v1;

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  string customer_id = 3;
  int64 total_minor_units = 4;
  string currency = 5;
  int64 occurred_at_epoch_millis = 6;
}
~~~

Trong ví dụ, total_minor_units lưu số tiền theo đơn vị nhỏ nhất của tiền tệ, tránh dùng số thực nhị phân cho phép tính tiền. Với VND, đơn vị nhỏ nhất có thể là đồng; với loại tiền có phần thập phân, cần xác định rõ scale trong hợp đồng. occurred_at_epoch_millis biểu diễn thời điểm theo epoch milliseconds; hai phía cần thống nhất múi giờ và đơn vị.

### Quy tắc tiến hóa Protobuf

Field number là một phần của wire format. Khi xóa trường, không tái sử dụng số trường hoặc tên cũ. Dùng reserved để đánh dấu:

~~~protobuf
message OrderCreated {
  reserved 7;
  reserved "legacy_note";

  string event_id = 1;
  string order_id = 2;
  string customer_id = 3;
  int64 total_minor_units = 4;
  string currency = 5;
  int64 occurred_at_epoch_millis = 6;
}
~~~

Các nguyên tắc quan trọng:

- Thêm trường mới với field number chưa từng dùng.
- Không đổi field number của trường đã phát hành.
- Không tái sử dụng số hoặc tên trường đã xóa; đánh dấu reserved.
- Tránh đổi kiểu trường nếu wire type hoặc ngữ nghĩa có thể thay đổi.
- Kiểm tra presence khi phân biệt trường không được gửi với trường có giá trị mặc định.
- Duy trì quy tắc tương thích giữa code sinh ra ở các phiên bản.

Protobuf có hỗ trợ trường chưa biết trong quá trình giải mã ở nhiều runtime, giúp consumer cũ có thể bỏ qua trường mới. Tuy vậy, tương thích wire không đồng nghĩa tương thích nghiệp vụ: consumer cũ có thể đọc message nhưng không hiểu ý nghĩa của trường mới. Hãy kiểm tra hành vi của phiên bản protoc và runtime đang dùng.

Protobuf phù hợp khi hợp đồng cần kiểu mạnh, nhiều ngôn ngữ, mã sinh tự động, payload gọn và nhóm phát triển có quy trình quản lý file .proto. Việc quan sát payload đòi hỏi công cụ giải mã và schema tương ứng; log nhị phân thô không thuận tiện như JSON.

## 6. Chọn định dạng theo yêu cầu tương tác

Có thể dùng các câu hỏi sau để ra quyết định:

| Câu hỏi | JSON | Avro | Protobuf |
|---|---|---|---|
| Consumer có cần đọc payload trực tiếp không? | Rất phù hợp | Cần công cụ giải mã | Cần công cụ giải mã |
| Có nhiều nhóm và cần quản lý schema tập trung? | Có thể, với JSON Schema và registry phù hợp | Rất phù hợp | Có thể, với kho schema và quy trình quản lý .proto |
| Cần sinh mã kiểu mạnh? | Tùy công cụ | Có công cụ sinh mã | Là thế mạnh |
| Cần trao đổi với API web và công cụ phổ biến? | Rất thuận tiện | Cần lớp tích hợp | Cần lớp tích hợp |
| Lưu lượng lớn, muốn payload nhị phân gọn? | Có thể cần nén/đo benchmark | Phù hợp | Phù hợp |
| Đội ngũ đã có hệ sinh thái nào? | JSON tooling | Avro/registry | Protobuf/protoc |

Một số tình huống điển hình:

- **Dịch vụ nghiệp vụ và dashboard cần kiểm tra payload dễ dàng:** bắt đầu với JSON, bổ sung JSON Schema hoặc contract test để xác thực.
- **Nền tảng sự kiện Kafka có nhiều producer/consumer và registry:** cân nhắc Avro nếu nhóm đã vận hành schema registry và cần schema resolution.
- **Hệ thống đa ngôn ngữ, hợp đồng API chặt chẽ hoặc dùng Protobuf ở RPC:** dùng Protobuf cho message streaming nếu binder và serializer được tích hợp, kiểm thử tốt.
- **Tích hợp với đối tác bên ngoài:** chọn định dạng mà đối tác hỗ trợ ổn định, sau đó xác định phiên bản schema và quy trình thay đổi trước khi phát hành.

Không nên chọn định dạng chỉ vì payload nhỏ hơn trong một benchmark. Hãy tính cả chi phí quản lý schema, sinh mã, debug, tích hợp, triển khai đồng thời và hỗ trợ consumer cũ.

## 7. Tích hợp serializer và converter trong Spring Cloud Stream

Spring Cloud Stream cho phép hàm nghiệp vụ làm việc với object Java hoặc Message<T>. Việc chuyển object thành byte và ngược lại có thể do message converter của Spring Cloud Stream hoặc serializer/deserializer của binder thực hiện.

### Dùng JSON qua message converter

Với JSON, thường có thể khai báo content type và để message converter chuyển đổi:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validator
          content-type: application/json
        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json
~~~

Hàm có thể nhận OrderCreated và trả về OrderValidated. Kiểu Java cùng converter xác định cách ánh xạ JSON. Hãy kiểm tra trường bắt buộc, kiểu số, ngày giờ và xử lý trường không biết bằng contract test.

### Dùng Avro hoặc Protobuf

Với Avro và Protobuf, ứng dụng cần serializer/deserializer hoặc message converter hiểu định dạng tương ứng. Có hai hướng tích hợp thường gặp:

1. Dùng message converter của Spring để chuyển giữa object và payload theo content type đã cấu hình.
2. Dùng native serialization của binder/client, trong đó Kafka client hoặc thư viện broker chịu trách nhiệm mã hóa và giải mã payload.

Ví dụ khái niệm khi dùng Kafka binder native encoding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
        orders-in-0:
          destination: orders.created
          group: order-consumer
      kafka:
        bindings:
          orders-out-0:
            producer:
              use-native-encoding: true
          orders-in-0:
            consumer:
              use-native-decoding: true
~~~

Khi bật native encoding/decoding, cần cấu hình serializer và deserializer tương ứng cho Kafka client, cùng registry hoặc schema source nếu định dạng yêu cầu. Tên class serializer, thuộc tính registry và namespace cấu hình phụ thuộc thư viện được chọn. Ví dụ Avro có thể dùng serializer tích hợp với schema registry; Protobuf có thể dùng serializer/deserializer tương ứng với message class được protoc sinh ra.

Đặt content-type không tự biến payload Java thành Avro hoặc Protobuf. Content type mô tả định dạng; serializer hoặc converter mới thực hiện mã hóa. Cũng không bật native decoding đồng thời kỳ vọng một converter khác giải mã cùng payload nếu chưa hiểu thứ tự xử lý của binder.

Với RabbitMQ hoặc Pulsar, cách cấu hình serializer và message properties có thể khác Kafka. Hãy dùng tài liệu binder đúng phiên bản, kiểm tra cách truyền content type/schema metadata và xác nhận consumer nhận đúng kiểu dữ liệu. Không sao chép nguyên cấu hình Kafka sang binder khác.

## 8. Tổ chức phiên bản schema và triển khai producer/consumer

Quy tắc tương thích phải gắn với lịch triển khai thực tế. Producer và consumer không được nâng cấp đồng thời trong nhiều hệ thống phân tán. Một quy trình an toàn thường gồm:

1. Đề xuất thay đổi schema và phân loại thay đổi: thêm trường, xóa trường, đổi tên, đổi kiểu hoặc đổi ý nghĩa.
2. Kiểm tra quy tắc tương thích đã chọn và chạy test với schema của phiên bản đang triển khai.
3. Phát hành consumer có khả năng đọc cả dữ liệu cũ và dữ liệu mới nếu cần chuyển đổi theo từng giai đoạn.
4. Phát hành producer mới sau khi các consumer liên quan đã sẵn sàng.
5. Theo dõi lỗi giải mã, validation và tỷ lệ message vào retry/DLQ.
6. Chỉ loại bỏ trường hoặc schema cũ sau khi xác nhận không còn consumer cần chúng và dữ liệu cũ đã hết thời hạn lưu giữ.

Với thay đổi không tương thích, cân nhắc destination mới hoặc event type/version mới, ví dụ orders.created.v2. Không đổi ý nghĩa trường hiện có trong cùng schema version chỉ để tránh tạo phiên bản mới. Một trường total đổi từ đồng sang nghìn đồng là thay đổi ngữ nghĩa dù kiểu dữ liệu vẫn là số.

## 9. Kiểm thử hợp đồng

Kiểm thử hàm đơn lẻ không đủ để xác nhận hai dịch vụ hiểu cùng một schema. Nên kết hợp:

- **Schema validation:** xác nhận payload hoặc schema đúng cú pháp và kiểu dữ liệu.
- **Compatibility test:** kiểm tra schema mới với phiên bản producer/consumer cần hỗ trợ.
- **Serialization round-trip:** mã hóa rồi giải mã payload và so sánh dữ liệu quan trọng.
- **Cross-language test:** khi có nhiều ngôn ngữ, tạo message ở một runtime và giải mã ở runtime khác.
- **Spring Cloud Stream test binder:** kiểm tra binding, payload và header ở cấp ứng dụng.
- **Broker integration test:** kiểm tra serializer, deserializer, registry, native encoding/decoding và hành vi thực tế của binder.

Với Avro, kiểm tra writer schema và reader schema theo chính sách registry. Với Protobuf, kiểm tra field number, reserved và code sinh từ phiên bản .proto. Với JSON, kiểm tra JSON Schema hoặc validation logic và xác nhận consumer bỏ qua hay xử lý trường mới theo hợp đồng.

## 10. Checklist trước khi chốt định dạng

Trước khi phát hành một luồng sự kiện mới, nhóm phát triển nên thống nhất:

- Producer và consumer nào sở hữu hợp đồng?
- Định dạng nào được các ngôn ngữ và nền tảng tham gia hỗ trợ?
- Có cần schema registry, kho schema hoặc mã sinh tự động không?
- Quy tắc backward, forward hoặc full compatibility nào được áp dụng?
- Cách xử lý trường thiếu, trường null, trường không biết và giá trị mặc định ra sao?
- Serializer, deserializer hoặc converter nào được dùng trong từng binder?
- Content type và schema metadata được truyền như thế nào?
- Làm sao kiểm thử dữ liệu cũ, dữ liệu mới và triển khai lệch phiên bản?
- Ai giám sát lỗi giải mã và xử lý message lỗi?

JSON giúp bắt đầu nhanh và dễ quan sát. Avro cung cấp schema cùng cơ chế phân giải writer/reader hữu ích cho nền tảng dữ liệu. Protobuf cung cấp hợp đồng kiểu mạnh và mã sinh đa ngôn ngữ. Khi chọn định dạng, hãy ưu tiên yêu cầu tương tác và khả năng vận hành dài hạn của toàn bộ producer-consumer; sau đó cấu hình serializer hoặc converter đúng với binder trong Spring Cloud Stream và kiểm thử hợp đồng qua các phiên bản.
