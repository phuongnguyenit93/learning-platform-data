# Tương thích schema, trường tùy chọn và nâng phiên bản hợp đồng dữ liệu

## Bối cảnh: payload cần sống lâu hơn một lần triển khai

Trong hệ thống RSocket, client và server trao đổi payload qua TCP hoặc WebSocket. Một payload có thể chứa dữ liệu nghiệp vụ như trạng thái thiết bị, lệnh điều khiển, sự kiện telemetry hoặc kết quả xử lý. Hai phía phải hiểu cùng một cấu trúc dữ liệu thì mới giải mã và xử lý chính xác.

Trong môi trường thực tế, client và server hiếm khi được nâng cấp cùng một thời điểm. Một số thiết bị có thể chạy firmware cũ nhiều tháng; một dịch vụ có thể được triển khai theo từng instance; ứng dụng di động có thể vẫn dùng phiên bản đã phát hành trước đó. Vì vậy, hợp đồng dữ liệu cần chịu được tình huống producer và consumer đang chạy các phiên bản schema khác nhau.

**Schema evolution** là quá trình thay đổi cấu trúc dữ liệu theo thời gian mà vẫn duy trì khả năng trao đổi giữa các phiên bản cần hỗ trợ. Việc thêm một trường mới có thể đơn giản, nhưng đổi tên, đổi kiểu, thay đổi ý nghĩa hoặc biến một trường tùy chọn thành bắt buộc có thể làm hỏng giao tiếp.

RSocket định nghĩa cách đóng gói và truyền payload, interaction model, metadata và flow control. Giao thức không tự quyết định schema JSON, Protobuf hay quy tắc tương thích của DTO nghiệp vụ. Ứng dụng phải thiết kế hợp đồng dữ liệu, định dạng serialization và chính sách nâng phiên bản phù hợp.

## 1. Phân biệt RSocket protocol, serialization và schema

Có ba lớp cần phân biệt:

| Lớp | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| RSocket protocol | Payload được gửi trên stream nào và theo interaction model nào? | request-response, request-stream, request-channel |
| Serialization / media type | Byte trong payload được mã hóa theo định dạng nào? | JSON, Protobuf, CBOR |
| Schema / data contract | Dữ liệu có trường nào, kiểu gì và ý nghĩa ra sao? | sensorId, temperatureC, batteryPercent |

Hai ứng dụng có thể cùng dùng RSocket và JSON nhưng vẫn không tương thích nếu một bên gửi trường temperatureC còn bên kia chờ temperatureF. Ngược lại, hai ứng dụng có thể dùng cùng schema nhưng không trao đổi được nếu serialization hoặc MIME type không khớp.

Trong RSocket SETUP, hai peer khai báo data MIME type và metadata MIME type dùng trên kết nối. Những MIME type này cho biết cách diễn giải phần data và metadata. Chúng không tự xác minh rằng schema nghiệp vụ của hai phía tương thích, cũng không tự thực hiện migration DTO.

Ví dụ:

- application/json cho biết phần data được mã hóa dạng JSON.
- application/x-protobuf có thể được dùng cho payload Protobuf theo cấu hình ứng dụng.
- Composite metadata có thể chứa các entry như routing, authentication hoặc metadata do ứng dụng định nghĩa.

Nếu cần nhận biết phiên bản hợp đồng, hãy quy định rõ cách mang schema version trong envelope hoặc metadata ứng dụng. Không nên xem việc hai phía cùng khai báo application/json là bằng chứng rằng chúng dùng cùng một schema.

## 2. Ba mức tương thích khi thay đổi schema

Khi đánh giá một thay đổi, cần xác định phía nào được nâng cấp trước.

- **Backward compatibility:** consumer mới đọc được dữ liệu do producer cũ tạo ra.
- **Forward compatibility:** consumer cũ vẫn đọc được dữ liệu do producer mới tạo ra.
- **Full compatibility:** cả hai chiều đều tương thích trong phạm vi phiên bản được hỗ trợ.

Giả sử phiên bản 1 có payload:

~~~json
{
  "sensorId": "sensor-01",
  "temperatureC": 28.4
}
~~~

Phiên bản 2 bổ sung batteryPercent:

~~~json
{
  "sensorId": "sensor-01",
  "temperatureC": 28.4,
  "batteryPercent": 87
}
~~~

Nếu consumer phiên bản 2 chấp nhận payload cũ và xem batteryPercent là chưa có, thay đổi có backward compatibility. Nếu consumer phiên bản 1 bỏ qua trường chưa biết, nó vẫn đọc được payload mới và thay đổi có forward compatibility.

| Producer | Consumer | Điều kiện để trao đổi an toàn |
|---|---|---|
| Cũ | Mới | Consumer mới chấp nhận trường bị thiếu và áp dụng mặc định hợp lý |
| Mới | Cũ | Consumer cũ bỏ qua trường mới hoặc có cơ chế xử lý trường chưa biết |
| Cũ | Cũ | Hai phía dùng hợp đồng đã biết |
| Mới | Mới | Hai phía hiểu cùng phiên bản và cùng ngữ nghĩa |

Khả năng tương thích không chỉ phụ thuộc schema trên giấy. Nó còn phụ thuộc cấu hình serializer, validation, logic nghiệp vụ và cách triển khai thực tế của từng client.

### Trường hợp nào thường phá vỡ tương thích?

| Thay đổi | Rủi ro | Hướng xử lý |
|---|---|---|
| Thêm trường tùy chọn | Thấp nếu reader cũ bỏ qua trường lạ và reader mới xử lý trường thiếu | Ưu tiên thay đổi cộng thêm |
| Thêm trường bắt buộc | Cao với producer cũ chưa gửi trường đó | Có mặc định hoặc triển khai theo giai đoạn |
| Xóa trường đang được sử dụng | Consumer cũ có thể không đọc được | Ngừng sử dụng trước, rồi mới xóa |
| Đổi tên trường | Reader cũ và producer mới không còn khớp tên | Hỗ trợ tên cũ trong giai đoạn chuyển đổi |
| Đổi kiểu dữ liệu | Có thể lỗi giải mã hoặc thay đổi cách hiểu | Thêm trường mới và chuyển đổi dần |
| Đổi đơn vị hoặc ý nghĩa | Có thể giải mã thành công nhưng kết quả sai | Định nghĩa hợp đồng mới hoặc trường mới |
| Thay đổi enum | Consumer cũ có thể gặp giá trị chưa biết | Có nhánh xử lý giá trị chưa biết |
| Đổi cấu trúc lồng nhau | Có thể làm reader cũ không tìm thấy dữ liệu | Thay đổi cộng thêm và kiểm thử phiên bản |

Một thay đổi có thể tương thích về cú pháp nhưng không tương thích về nghiệp vụ. Ví dụ, giữ nguyên trường temperature nhưng chuyển đơn vị từ Celsius sang Fahrenheit sẽ khiến consumer tính toán sai dù JSON vẫn parse thành công.

## 3. Thiết kế trường tùy chọn và giá trị mặc định

Trường tùy chọn cho phép producer cũ chưa gửi dữ liệu đó và consumer mới vẫn có thể xử lý payload. Khi thêm trường, hãy trả lời ba câu hỏi:

1. Nếu trường không xuất hiện thì có nghĩa là gì?
2. Nếu trường xuất hiện với giá trị null thì có nghĩa là gì?
3. Nếu trường có giá trị mặc định thì consumer có thể tiếp tục nghiệp vụ an toàn không?

Không nên mặc định rằng thiếu trường và null luôn đồng nghĩa. Trong một số hợp đồng, thiếu trường nghĩa là client chưa biết thông tin; null nghĩa là đã biết nhưng không có giá trị. Nếu nghiệp vụ cần phân biệt hai trường hợp này, DTO đơn giản có thể chưa đủ và cần mô hình biểu diễn sự hiện diện của trường.

### Ví dụ với JSON

Giả sử payload đọc cảm biến ban đầu chỉ có sensorId và temperatureC. Phiên bản mới bổ sung batteryPercent và firmwareVersion:

~~~json
{
  "sensorId": "sensor-01",
  "temperatureC": 28.4,
  "batteryPercent": 87,
  "firmwareVersion": "3.2.1"
}
~~~

Consumer mới cần đọc được payload cũ không có hai trường mới:

~~~json
{
  "sensorId": "sensor-01",
  "temperatureC": 28.4
}
~~~

Một DTO Java có thể biểu diễn các trường mới bằng kiểu nullable:

~~~java
public record SensorReading(
    String sensorId,
    Double temperatureC,
    Integer batteryPercent,
    String firmwareVersion
) {}
~~~

Với cấu hình Jackson phù hợp, trường không có trong JSON có thể được ánh xạ thành null cho các thành phần reference. Cần kiểm tra hành vi thực tế của codec và ObjectMapper mà ứng dụng RSocket sử dụng; validation hoặc constructor tùy chỉnh có thể thay đổi cách xử lý.

Ở tầng nghiệp vụ, hãy chuyển dữ liệu tùy chọn thành trạng thái rõ ràng:

~~~java
public DeviceSnapshot toSnapshot(SensorReading reading) {
    Integer battery = reading.batteryPercent();

    BatteryState batteryState = battery == null
        ? BatteryState.UNKNOWN
        : BatteryState.fromPercent(battery);

    return new DeviceSnapshot(
        reading.sensorId(),
        reading.temperatureC(),
        batteryState,
        reading.firmwareVersion()
    );
}
~~~

Ví dụ này xem trường bị thiếu là UNKNOWN. Không nên tự gán 0% pin nếu 0 có nghĩa thiết bị đã cạn pin; giá trị mặc định sai có thể tạo cảnh báo hoặc hành động điều khiển không đúng.

### Không ép mọi trường tùy chọn thành một giá trị giả

Các giá trị như 0, chuỗi rỗng, false hoặc ngày 1970 có thể là dữ liệu hợp lệ. Nếu dùng chúng để thay cho “không có dữ liệu”, consumer không còn phân biệt được giá trị thật với giá trị mặc định.

Hãy dùng null, kiểu wrapper, enum trạng thái hoặc một cấu trúc có presence rõ ràng tùy định dạng serialization và ngữ nghĩa nghiệp vụ.

Nếu cần phân biệt absent với explicit null trong JSON, hãy kiểm tra token JSON hoặc dùng một kiểu wrapper có biểu diễn trạng thái presence. Chỉ dùng Optional trong DTO khi codec và module Jackson tương ứng đã được cấu hình và kiểm thử; Optional không tự giải quyết mọi khác biệt giữa absent, null và value.

### Xử lý trường chưa biết

Consumer có thể nhận một trường mới do producer được triển khai trước. Với JSON, ứng dụng nên quy định rõ serializer có bỏ qua thuộc tính chưa biết hay từ chối payload.

Có thể cấu hình ở DTO:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record SensorReading(
    String sensorId,
    Double temperatureC
) {}
~~~

Hoặc cấu hình ở ObjectMapper/codec dùng chung. Hãy kiểm thử cấu hình thực tế trong Spring RSocket; không nên giả định mọi ObjectMapper trong mọi ứng dụng đều có cùng hành vi.

Bỏ qua trường chưa biết giúp forward compatibility, nhưng không nên bỏ qua mọi lỗi. Trường bắt buộc, kiểu dữ liệu sai, giá trị ngoài miền cho phép hoặc payload sai định dạng vẫn cần được kiểm tra và từ chối phù hợp.

## 4. Quy tắc tiến hóa schema JSON

JSON linh hoạt và dễ quan sát, nhưng các quy tắc tương thích cần được thống nhất giữa producer và consumer.

### Ưu tiên thêm trường tùy chọn

Đây thường là cách mở rộng ít rủi ro nhất:

~~~json
{
  "sensorId": "sensor-01",
  "temperatureC": 28.4,
  "batteryPercent": 87
}
~~~

Reader mới cần xử lý payload cũ không có batteryPercent. Reader cũ cần bỏ qua batteryPercent nếu nó chưa biết trường này.

### Không đổi tên trường trực tiếp

Giả sử trường cũ là temperature và muốn đổi thành temperatureC. Nếu producer chuyển ngay sang tên mới, consumer cũ có thể không tìm thấy trường temperature.

Một lộ trình an toàn hơn:

1. Consumer mới đọc được cả temperature và temperatureC.
2. Producer bắt đầu gửi trường temperatureC; trong giai đoạn chuyển đổi có thể tiếp tục gửi trường cũ.
3. Theo dõi số client còn dùng trường cũ.
4. Chỉ ngừng gửi temperature khi toàn bộ consumer được hỗ trợ đã chuyển đổi.

Jackson có thể dùng @JsonAlias để chấp nhận tên cũ khi đọc:

~~~java
public record SensorReading(
    String sensorId,
    @JsonAlias("temperature")
    Double temperatureC
) {}
~~~

@JsonAlias hỗ trợ tên thay thế trong quá trình deserialize; khi serialize, tên thuộc tính chính vẫn được sử dụng. Nếu cần phát đồng thời cả hai tên trong giai đoạn chuyển đổi, hãy tạo DTO hoặc lớp ánh xạ tương thích có chủ đích và kiểm thử payload đầu ra.

### Không đổi kiểu dữ liệu tại chỗ

Ví dụ đổi batteryPercent từ integer sang string:

~~~json
{
  "batteryPercent": "87%"
}
~~~

Consumer cũ có thể đang thực hiện phép so sánh số hoặc lưu vào cột integer. Hãy tạo trường mới như batteryLevelText, chuyển đổi dần và giữ trường cũ trong giai đoạn tương thích.

Tương tự, tránh đổi:

- Số nguyên thành số thực nếu consumer phụ thuộc độ chính xác hoặc kiểu parse.
- Một giá trị đơn thành mảng nếu reader cũ chỉ xử lý scalar.
- Chuỗi thời gian không có múi giờ thành timestamp có quy ước khác.
- Đơn vị Celsius thành Fahrenheit mà không đổi tên hoặc version contract.

### Enum cần có nhánh cho giá trị chưa biết

Một consumer cũ có thể nhận enum mới do producer mới gửi. Ví dụ firmwareState bổ sung giá trị CALIBRATING. Nếu code consumer giả định chỉ có ONLINE và OFFLINE, nó có thể lỗi hoặc rẽ nhánh sai.

Hãy có trạng thái UNKNOWN/UNRECOGNIZED ở tầng ứng dụng và quy định cách xử lý giá trị enum chưa biết. Không nên mặc định một trạng thái chưa biết tương đương OFFLINE hoặc một trạng thái an toàn khác nếu nghiệp vụ chưa xác định.

## 5. Tiến hóa schema Protobuf

Protobuf phù hợp khi cần payload gọn, hiệu quả và có schema định nghĩa rõ. Tuy nhiên, tính tương thích phụ thuộc vào field number, wire type, presence và quy tắc tiến hóa của schema.

Ví dụ schema ban đầu:

~~~protobuf
syntax = "proto3";

message SensorReading {
  string sensor_id = 1;
  double temperature_c = 2;
}
~~~

Phiên bản mới bổ sung thông tin pin và firmware:

~~~protobuf
syntax = "proto3";

message SensorReading {
  string sensor_id = 1;
  double temperature_c = 2;
  optional int32 battery_percent = 3;
  string firmware_version = 4;
}
~~~

Các field number 1 và 2 được giữ nguyên. Trường mới dùng field number chưa từng sử dụng. Consumer cũ có thể bỏ qua field không biết theo cơ chế của Protobuf; consumer mới có thể đọc payload cũ và nhận trạng thái mặc định hoặc trạng thái không hiện diện tùy kiểu field.

### Các quy tắc cần giữ

- Không thay đổi field number đã phát hành.
- Không tái sử dụng field number của trường đã xóa.
- Dùng reserved để đánh dấu field number và tên không được dùng lại.
- Tránh thay đổi kiểu làm đổi wire type hoặc thay đổi ngữ nghĩa dữ liệu.
- Thêm trường mới với field number mới và thiết kế presence/default rõ ràng.
- Kiểm tra cách consumer xử lý enum value chưa biết.
- Không đổi ý nghĩa hoặc đơn vị của field hiện có dù kiểu Protobuf vẫn giống nhau.

Khi xóa field, hãy giữ số và tên của nó trong reserved:

~~~protobuf
message SensorReading {
  reserved 3;
  reserved "legacy_voltage";

  string sensor_id = 1;
  double temperature_c = 2;
  optional int32 battery_percent = 4;
}
~~~

Số 3 và tên legacy_voltage sẽ không bị vô tình cấp lại cho một trường mới. Việc giữ reserved giúp tránh trường hợp dữ liệu cũ được giải mã nhầm thành một ý nghĩa khác.

### Presence trong proto3

Với scalar thông thường trong proto3, giá trị mặc định như 0, false hoặc chuỗi rỗng có thể không phân biệt được với trường không xuất hiện. Nếu nghiệp vụ cần biết trường có được gửi hay không, dùng optional scalar hoặc một cấu trúc có presence phù hợp.

Ví dụ battery_percent có thể chưa được thiết bị hỗ trợ. Với optional int32, code được sinh có thể cung cấp API kiểm tra presence, chẳng hạn hasBatteryPercent() tùy ngôn ngữ và generator. Consumer có thể phân biệt trường chưa xuất hiện với giá trị 0.

Đối với message field, Protobuf có presence theo ngữ nghĩa message. Với oneof, cần xem xét tác động khi thêm hoặc thay đổi các nhánh vì consumer cũ có thể không hiểu nhánh mới.

### Enum trong Protobuf

Khi thêm enum value, consumer cũ có thể nhận một số enum chưa được định nghĩa trong phiên bản schema của nó. Code Java được sinh từ Protobuf thường có trạng thái UNRECOGNIZED cho trường hợp này. Hãy xử lý trạng thái đó tường minh, ghi nhận telemetry và chọn hành vi nghiệp vụ phù hợp.

Không đổi số enum value đã phát hành và không tái sử dụng số đã xóa. Có thể dùng reserved để bảo vệ số và tên cũ.

## 6. Mang phiên bản hợp đồng trong RSocket

RSocket có metadata và MIME type để mô tả cách diễn giải payload. Ứng dụng có thể dùng chúng để xác định contract, nhưng cần phân biệt định dạng serialization với phiên bản schema.

Có một số cách thường gặp:

| Cách | Ví dụ | Phù hợp khi |
|---|---|---|
| Schema version trong envelope | schemaVersion: 2 | Cần kiểm soát phiên bản theo từng payload |
| Version trong MIME type | application/vnd.example.sensor-reading.v2+json | Muốn nhận biết loại payload và contract qua content type |
| Metadata ứng dụng | contract-version = 2 | Muốn gắn thông tin phiên bản vào metadata của tương tác |
| Route có phiên bản | sensor.readings.v2 | Có thay đổi breaking và cần endpoint song song |

### Envelope chứa schemaVersion

Ví dụ payload JSON:

~~~json
{
  "schemaVersion": 2,
  "eventId": "evt-1042",
  "occurredAt": "2026-11-22T10:15:30Z",
  "data": {
    "sensorId": "sensor-01",
    "temperatureC": 28.4,
    "batteryPercent": 87
  }
}
~~~

Envelope giúp consumer biết phiên bản của cấu trúc data trước khi xử lý. Tuy nhiên, schemaVersion chỉ có tác dụng khi consumer kiểm tra và định nghĩa hành vi cho từng phiên bản. Đưa trường này vào JSON mà không có chính sách tương thích không tự làm payload an toàn hơn.

Nếu chỉ thêm một trường tùy chọn tương thích, không nhất thiết phải tăng major version cho mọi payload. Version nên phản ánh thay đổi hợp đồng có ý nghĩa, không phải số build của ứng dụng.

### Dùng metadata ứng dụng

RSocket payload có thể mang metadata riêng. Với composite metadata, ứng dụng có thể định nghĩa một entry chứa contract version, correlation ID hoặc thông tin phục vụ định tuyến theo quy ước của hệ thống.

Cần quy định:

- MIME type của entry metadata.
- Cấu trúc và giới hạn kích thước.
- Phiên bản được hỗ trợ và hành vi khi không có metadata.
- Cách xử lý version chưa biết.
- Quy tắc xác thực metadata nếu nó ảnh hưởng tới route, tenant hoặc quyền truy cập.

Không đặt dữ liệu nghiệp vụ lớn vào metadata chỉ vì metadata có sẵn. Data nên mang payload nghiệp vụ; metadata nên chứa thông tin điều khiển hoặc ngữ cảnh nhỏ, có cấu trúc rõ ràng.

### Khi nào cần route hoặc MIME type versioned?

Nếu thay đổi làm consumer cũ không thể hiểu dữ liệu mới, hãy cung cấp một hợp đồng mới song song:

- sensor.readings.v1 tiếp tục phục vụ client cũ.
- sensor.readings.v2 phục vụ client đã nâng cấp.

Một MIME type versioned cũng có thể dùng để nhận biết schema. Dù chọn route hay MIME type, cần có chính sách thời gian hỗ trợ và thời điểm ngừng phiên bản cũ. Không nên để nhiều phiên bản tồn tại vô thời hạn mà không biết client nào còn sử dụng.

## 7. Quy trình rollout thay đổi schema an toàn

Vì producer và consumer có thể được triển khai độc lập, việc nâng cấp nên theo hướng mở rộng trước, chuyển đổi sau, thu hẹp cuối cùng.

Giả sử cần thêm batteryPercent vào stream sensor.readings.

~~~mermaid
flowchart TD
    A["1. Mở rộng consumer: chấp nhận payload cũ và mới"] --> B["2. Triển khai consumer mới"]
    B --> C["3. Producer bắt đầu gửi trường mới"]
    C --> D["4. Theo dõi client, lỗi parse và dữ liệu thiếu"]
    D --> E["5. Ngừng trường cũ khi hết consumer cần nó"]
    E --> F["6. Xóa hỗ trợ cũ trong lần phát hành hợp đồng phù hợp"]
~~~

### Bước 1: mở rộng consumer trước

Consumer mới phải xử lý được cả payload cũ không có batteryPercent và payload mới có trường này. Đặt mặc định nghiệp vụ rõ ràng, kiểm tra validation và bổ sung metric để biết trường có xuất hiện hay không.

### Bước 2: triển khai consumer mới

Triển khai consumer có khả năng đọc cả hai dạng dữ liệu. Nếu hệ thống có nhiều instance, cần bảo đảm tất cả instance phục vụ stream đều đã tương thích trước khi producer bắt đầu gửi trường mới.

### Bước 3: mở rộng producer

Producer bắt đầu gửi batteryPercent. Trong giai đoạn chuyển đổi, producer có thể tiếp tục gửi các trường cũ để hỗ trợ consumer chưa được nâng cấp. Nếu dữ liệu được phát từ thiết bị lâu đời, gateway có thể cần ánh xạ payload cũ sang contract mới.

### Bước 4: quan sát thực tế

Theo dõi:

- Số client hoặc phiên bản client còn sử dụng contract cũ.
- Tỷ lệ payload thiếu trường mới.
- Lỗi deserialize, validation và lỗi xử lý nghiệp vụ.
- Số request/stream đang chạy theo từng phiên bản.
- Tỷ lệ reconnect và client lỗi sau khi nâng cấp.

Không dựa vào việc một lần deploy thành công để kết luận mọi consumer đã chuyển đổi.

### Bước 5: ngừng hỗ trợ cũ có kiểm soát

Chỉ ngừng gửi hoặc đọc trường cũ sau khi đã xác nhận không còn consumer cần nó trong phạm vi hỗ trợ. Với stream dài, cần tính đến phiên đang mở từ trước thời điểm triển khai. Có thể chờ các stream cũ kết thúc, đặt thời hạn tối đa cho phiên hoặc tiếp tục hỗ trợ contract cũ trong một khoảng thời gian đã công bố.

### Bước 6: loại bỏ code tương thích cũ

Sau khi hết thời gian chuyển đổi, xóa alias, mapper hoặc route cũ trong một thay đổi có version rõ ràng. Cập nhật schema registry hoặc tài liệu hợp đồng nếu hệ thống sử dụng chúng.

## 8. Ví dụ Spring RSocket với DTO tương thích

Spring RSocket có thể nhận và trả về DTO thông qua các method được ánh xạ bằng @MessageMapping. Codec và cấu hình serialization quyết định cách byte payload trở thành object Java.

Ví dụ server nhận SensorReading:

~~~java
@Controller
class SensorController {

    private final SensorService sensorService;

    SensorController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @MessageMapping("sensor.reading")
    Mono<ReadingAccepted> accept(SensorReading reading) {
        if (reading.sensorId() == null || reading.sensorId().isBlank()) {
            return Mono.error(new InvalidReadingException("sensorId is required"));
        }

        return sensorService.accept(reading)
            .map(result -> new ReadingAccepted(
                result.eventId(),
                reading.batteryPercent() == null
                    ? "UNKNOWN"
                    : "AVAILABLE"
            ));
    }
}
~~~

DTO có thể tiến hóa theo hướng thêm trường tùy chọn:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record SensorReading(
    String sensorId,
    Double temperatureC,
    Integer batteryPercent,
    String firmwareVersion
) {}
~~~

Client cũ gửi:

~~~json
{
  "sensorId": "sensor-01",
  "temperatureC": 28.4
}
~~~

Client mới gửi:

~~~json
{
  "sensorId": "sensor-01",
  "temperatureC": 28.4,
  "batteryPercent": 87,
  "firmwareVersion": "3.2.1"
}
~~~

Consumer mới xử lý được cả hai payload. Consumer cũ chỉ xử lý payload mới nếu codec của nó được cấu hình bỏ qua thuộc tính chưa biết và logic nghiệp vụ không phụ thuộc trường mới.

Khi dùng Protobuf, Spring cần codec tương ứng và cả hai phía phải thống nhất message type/schema. Việc đổi DTO Java không tự cập nhật schema Protobuf hoặc bảo đảm field number tương thích.

## 9. Kiểm thử tương thích hợp đồng dữ liệu

Unit test cho DTO mới là chưa đủ. Cần kiểm tra các tổ hợp producer/consumer có thể gặp khi rollout.

Một ma trận kiểm thử hữu ích:

| Payload đầu vào | Consumer cũ | Consumer mới |
|---|---|---|
| Payload phiên bản cũ | Phải đọc được | Phải đọc được, áp dụng mặc định |
| Payload thêm trường tùy chọn | Bỏ qua trường lạ hoặc xử lý theo cấu hình | Đọc và xử lý trường mới |
| Payload thiếu trường bắt buộc | Từ chối với lỗi rõ ràng | Từ chối với lỗi rõ ràng |
| Enum value chưa biết | Có hành vi fallback đã định nghĩa | Có hành vi fallback đã định nghĩa |
| Kiểu dữ liệu sai | Từ chối hoặc chuyển lỗi có kiểm soát | Từ chối hoặc chuyển lỗi có kiểm soát |

### Kiểm thử bằng JSON fixture

Lưu payload mẫu của các phiên bản đã phát hành làm fixture. Mỗi lần thay DTO hoặc codec, chạy lại toàn bộ fixture để xác nhận consumer hiện tại vẫn đọc được dữ liệu cũ.

~~~java
@Test
void readsLegacyPayloadWithoutOptionalFields() throws Exception {
    String json = """
        {
          "sensorId": "sensor-01",
          "temperatureC": 28.4
        }
        """;

    SensorReading reading =
        objectMapper.readValue(json, SensorReading.class);

    assertEquals("sensor-01", reading.sensorId());
    assertNull(reading.batteryPercent());
}
~~~

Cần có test ngược lại nếu hệ thống yêu cầu consumer cũ đọc payload mới. Có thể dùng ObjectMapper hoặc codec được cấu hình giống ứng dụng thực tế để kiểm tra unknown fields.

### Contract test giữa producer và consumer

Contract test xác nhận producer tạo payload mà consumer có thể đọc và consumer không giả định các trường tùy chọn luôn xuất hiện. Nếu có nhiều client độc lập, lưu contract fixture và chạy trong pipeline CI của cả producer lẫn consumer.

Với RSocket, integration test nên bao gồm:

- Kết nối bằng đúng data MIME type và metadata MIME type.
- Gọi route thực tế với payload cũ và mới.
- Kiểm tra trường tùy chọn bị thiếu, null và có giá trị.
- Kiểm tra lỗi khi schema không hợp lệ.
- Kiểm tra stream dài khi producer/consumer ở phiên bản khác nhau.
- Kiểm tra metadata version và hành vi khi version chưa được hỗ trợ.

### Kiểm thử Protobuf

Với Protobuf, kiểm tra schema diff trước khi phát hành. Xác nhận field number không bị tái sử dụng, wire type không thay đổi ngoài quy tắc tương thích cho phép, enum value cũ được giữ nguyên và reserved được cập nhật khi xóa trường. Nên giữ binary fixture được tạo từ schema cũ để kiểm thử reader mới.

## 10. Những nguyên tắc nên thống nhất trong nhóm

- Ưu tiên thay đổi cộng thêm: thêm trường tùy chọn trước khi xóa hoặc đổi trường cũ.
- Định nghĩa rõ absent, null và default; không để mỗi service tự hiểu một cách.
- Không đổi đơn vị, timezone hoặc ý nghĩa nghiệp vụ tại chỗ.
- Quy định cách xử lý unknown fields và unknown enum values.
- Với Protobuf, không tái sử dụng field number hoặc enum number đã phát hành.
- Dùng versioned route hoặc contract riêng khi có thay đổi breaking.
- Giữ fixture payload của các phiên bản đã phát hành.
- Theo dõi client và stream còn dùng contract cũ trước khi ngừng hỗ trợ.
- Không dùng schema version thay cho xác thực, phân quyền hoặc kiểm tra dữ liệu đầu vào.

Một hợp đồng dữ liệu tốt cần được quản lý như API công khai: có chủ sở hữu, quy tắc thay đổi, thời gian hỗ trợ phiên bản và kiểm thử tương thích. Điều này đặc biệt quan trọng với RSocket vì stream có thể tồn tại lâu và client có thể kết nối lại từ nhiều phiên bản ứng dụng khác nhau.

## Kết luận

Tương thích schema giúp producer và consumer trao đổi payload an toàn trong khi hai phía được nâng cấp ở các thời điểm khác nhau. Hãy ưu tiên thêm trường tùy chọn, xác định ý nghĩa của trường bị thiếu hoặc null, cho phép xử lý trường chưa biết và tránh đổi kiểu hoặc ý nghĩa của trường đã phát hành.

RSocket cung cấp transport, stream, payload và metadata; ứng dụng chịu trách nhiệm quản lý serialization và schema version. Với JSON, hãy quy định unknown fields, default và quy trình chuyển tên trường. Với Protobuf, giữ field number, dùng reserved và quản lý presence. Khi có thay đổi breaking, triển khai hợp đồng mới song song, kiểm thử payload của các phiên bản cũ và chỉ loại bỏ hỗ trợ cũ sau khi đã xác nhận các consumer cần thiết đều chuyển đổi.
