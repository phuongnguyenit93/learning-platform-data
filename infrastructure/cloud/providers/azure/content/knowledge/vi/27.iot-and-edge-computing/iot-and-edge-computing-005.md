# Định tuyến telemetry từ IoT Hub đến dịch vụ xử lý

Một nhà máy triển khai hàng nghìn cảm biến đo nhiệt độ, độ rung và điện năng. Mỗi thiết bị gửi dữ liệu vài giây một lần về **Azure IoT Hub**. Đội vận hành muốn cảnh báo tức thời khi nhiệt độ vượt ngưỡng; đội phân tích muốn lưu telemetry gốc để điều tra và huấn luyện mô hình; một hệ thống báo cáo cần tổng hợp trung bình theo phút. Nếu mọi thông điệp đều phải đi qua một ứng dụng Java tự viết rồi mới phân phối cho các hệ thống, ứng dụng đó có thể trở thành nút nghẽn và phải xử lý rất nhiều tình huống retry, kết nối và mở rộng.

**Message routing của Azure IoT Hub** cho phép đưa thông điệp **device-to-cloud (D2C)** đến các endpoints được hỗ trợ dựa trên **nguồn thông điệp và điều kiện lọc**. Một telemetry message có thể được chuyển tới endpoint streaming cho xử lý thời gian thực, sang Azure Storage để lưu trữ, hoặc tới hàng đợi/topic cho các tác vụ nghiệp vụ. Tuy nhiên, route chỉ chọn **đích**, không tự thay thế ETL, kiểm tra schema, quản lý sự kiện trùng, authorization của downstream processor hay hệ thống phân tích.

Bài thuộc chương **IoT và xử lý tại biên** của module **CLOUD_PROVIDERS_AZURE**. Module tìm hiểu hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID tới mạng ảo, compute, lưu trữ và dữ liệu; đồng thời học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng. Bài này nối **thiết bị → IoT Hub → routing → dịch vụ xử lý → lưu trữ/cảnh báo/analytics**, với ví dụ Java và các nguyên tắc vận hành khi triển khai thực tế.

**Phạm vi kỹ thuật:** tập trung **Azure IoT Hub device telemetry message routing**, không nhầm với cloud-to-device commands, device twins, IoT Edge routing nội bộ hoặc Azure Event Grid subscriptions. Những API, kiểu endpoint, tính năng identity, tên lệnh Azure CLI và quota có thể khác theo IoT Hub tier/region/phiên bản; trước khi chạy trong subscription thực, kiểm tra tài liệu chính thức và tính năng được bật. Các tên tài nguyên trong bài là **giả định dành cho lab**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **D2C telemetry**, **cloud-to-device message**, **device twin**, **direct method** và **routing**.
- Giải thích **IoT Hub route**, **message source**, **routing query/condition**, **custom endpoint**, **built-in endpoint** và **fallback route**.
- Thiết kế các route tới **Event Hubs, Service Bus queues/topics, Azure Storage và Azure Cosmos DB** khi loại endpoint được IoT Hub hỗ trợ.
- Chọn **Azure Functions, Stream Analytics, Java worker** hoặc dịch vụ analytics làm consumer phù hợp.
- Gửi JSON telemetry với **contentType** và **contentEncoding** đúng để lọc theo nội dung message.
- Viết routing queries dựa trên **application properties, system properties và JSON body**.
- Hiểu **nhiều route cùng khớp**, default/fallback behavior và cách tránh vô tình mất luồng dữ liệu mong đợi.
- Thiết kế đường streaming, cảnh báo, dữ liệu lịch sử và dead-letter/replay thích hợp.
- Kiểm soát device identity, endpoint authorization, managed identity, Key Vault và private networking.
- Viết skeleton Java để gửi dữ liệu từ thiết bị và xử lý thông điệp từ một endpoint streaming.
- Đo delivery failures, throttling, latency, backlog, chi phí và kiểm thử negative scenarios.
- Triển khai thay đổi route có version, kiểm tra và rollback mà không ảnh hưởng production.

## 2. Vị trí của IoT Hub trong kiến trúc

**Azure IoT Hub** là dịch vụ cloud có khả năng tiếp nhận và quản lý giao tiếp với nhiều thiết bị IoT, hỗ trợ xác thực thiết bị, device-to-cloud telemetry và các mẫu giao tiếp quản lý thiết bị.

~~~mermaid
flowchart LR
    D1[Sensor A] -->|MQTT / AMQP / HTTPS D2C| H[Azure IoT Hub]
    D2[Sensor B] -->|D2C telemetry| H
    H -->|Rule: alert| E[Service Bus queue]
    H -->|Rule: all telemetry| V[Event Hubs]
    H -->|Rule: archive| S[Azure Blob Storage]
    H -->|Rule: selected JSON| C[Azure Cosmos DB]
    E --> F[Azure Functions / Java alert worker]
    V --> A[Stream Analytics / Java streaming consumer]
    S --> L[Data lake / offline processing]
    C --> Q[Operational query API]
~~~

Sơ đồ là **kiến trúc lựa chọn**: không có nghĩa một IoT Hub/account/tier luôn dùng mọi endpoint cùng lúc, hoặc mọi loại message route tương thích mọi đích. Chọn theo tính năng, quyền, network và chi phí thực tế.

### D2C khác C2D

| Luồng | Hướng đi | Dùng cho |
|---|---|---|
| **Device-to-cloud telemetry** | Thiết bị → IoT Hub → xử lý | Nhiệt độ, độ rung, vị trí, chất lượng mạng |
| **Cloud-to-device messages** | Dịch vụ → IoT Hub → thiết bị | Thông báo/cấu hình đơn giản theo khả năng |
| **Direct methods** | Backend gọi method thiết bị, yêu cầu kết quả | Khởi động lại, thực thi lệnh có kiểm soát |
| **Device twins** | Desired/reported properties và metadata trạng thái | Cấu hình thiết bị, trạng thái được báo cáo |
| **IoT Hub message routing** | IoT Hub → endpoint xử lý/lưu trữ | Phân luồng dữ liệu dựa nguồn/query |

**Routing telemetry không tự gửi lại một lệnh tới thiết bị.** Nếu muốn từ cảnh báo kích hoạt điều khiển thiết bị, backend phải thực hiện luồng điều khiển riêng với authorization, safety checks và device capability.

## 3. Mô hình dữ liệu của một telemetry message

Ví dụ một cảm biến gửi payload:

~~~json
{
  "schemaVersion": 1,
  "messageId": "sensor-a-0000182",
  "temperatureC": 81.4,
  "vibrationMmS": 12.3,
  "humidityPct": 57.2,
  "recordedAtUtc": "2026-11-20T08:15:30Z",
  "locationId": "factory-hcm-line-2"
}
~~~

**IoT Hub message** còn có metadata bên ngoài body:

~~~text
System properties:
  connectionDeviceId = sensor-a
  messageId          = sensor-a-0000182
  contentType        = application/json
  contentEncoding    = utf-8
  enqueuedTime       = do IoT Hub đặt theo định dạng dịch vụ

Application properties do thiết bị/app gán:
  messageType = telemetry
  site = factory-hcm
  severity = normal

Body:
  {"schemaVersion":1,"temperatureC":81.4,...}
~~~

Đây là **minh họa lớp dữ liệu**, không phải raw protocol frame chính xác. Một số thuộc tính hệ thống được IoT Hub đặt hoặc SDK ánh xạ theo tên khác nhau; **không tin giá trị device-supplied application property như bằng chứng security identity**.

### Vì sao nên có schemaVersion và messageId?

- **schemaVersion** giúp consumer nhận biết định dạng payload và migrate.
- **messageId** hoặc một event ID ổn định hỗ trợ deduplication/idempotency.
- **recordedAtUtc** biểu thị thời điểm đo tại thiết bị, khác **IoT Hub enqueued time**.
- **locationId** là dữ liệu nghiệp vụ, cần kiểm tra quyền/nguồn đáng tin.
- Các trường đo nên dùng **kiểu số** và đơn vị rõ, tránh chuỗi chứa đơn vị gây khó filter/tính toán.

Thiết bị offline có thể gửi lại dữ liệu cũ; consumer phải phân biệt **event time**, **ingestion time** và **processing time**, không giả định mọi message đến đúng thứ tự thời gian đo.

## 4. Device identity không phải application property

IoT Hub có cơ chế danh tính thiết bị bằng device identity registry cùng phương thức như SAS/token hoặc X.509 theo thiết kế. Khi thiết bị kết nối và gửi message, Hub biết danh tính kết nối ở lớp giao thức.

Đừng đánh giá quyền của một telemetry message chỉ dựa vào body:

~~~json
{"deviceId": "admin-sensor", "temperatureC": 90}
~~~

Trường **deviceId** trong JSON body có thể do thiết bị tự điền sai. Consumer nên dùng **device connection identity từ trusted IoT Hub metadata**, kết hợp registry/twin/asset mapping nếu nghiệp vụ cần. Nếu chuyển tiếp qua endpoint làm mất/đổi metadata, hãy chủ động thiết kế preservation/normalization và kiểm chứng.

### Các lớp danh tính

| Lớp | Ai được xác thực? | Ví dụ |
|---|---|---|
| **Device → IoT Hub** | Thiết bị cụ thể | Device SAS/X.509 credential |
| **IoT Hub → custom endpoint** | Dịch vụ Hub theo cấu hình SAS/managed identity | Quyền Event Hubs/Service Bus/Storage |
| **Consumer → endpoint** | Azure Function/Java worker | Managed identity hoặc consumer credential |
| **Processor → database/action** | Worker/backend workload | SQL/Cosmos data-plane permission |
| **Operator → control plane** | Người/quy trình quản lý routes | Azure RBAC ở resource phù hợp |

Một quyền **IoT Hub Contributor** ở management plane không tự cấp mọi quyền đọc dữ liệu từ custom Event Hubs/Storage hoặc cập nhật thiết bị.

## 5. Một route gồm những thành phần nào?

Với message routing, đội vận hành xác định:

1. **Name** — tên route độc lập, dễ kiểm toán.
2. **Data source** — ví dụ **Device Telemetry Messages**.
3. **Condition/query** — biểu thức lọc message theo properties/body.
4. **Endpoint** — built-in hoặc custom endpoint đã được cấu hình.
5. **Enabled** — route có đang hoạt động.

~~~text
Route: route-high-temperature
  Source: Device Telemetry Messages
  Condition: $body.temperatureC > 80
  Endpoint: servicebus-alerts
  Enabled: true

Route: route-all-telemetry
  Source: Device Telemetry Messages
  Condition: true
  Endpoint: eventhub-telemetry
  Enabled: true
~~~

Đây là **mô tả cấu hình**, không phải YAML có thể apply trực tiếp. Cú pháp routing query/body và các loại endpoint phải kiểm tra trong phần **Message routing query syntax** của IoT Hub, kể cả yêu cầu contentType/contentEncoding.

### Source quan trọng

Nếu muốn định tuyến dữ liệu cảm biến, chọn nguồn **device telemetry messages**. Một route dùng nguồn **device lifecycle events** không tự nhận telemetry; các nguồn event và tính năng hỗ trợ phải được đối chiếu với Hub tier/cấu hình.

## 6. Built-in endpoint và custom endpoint

IoT Hub cung cấp một **built-in endpoint** có khả năng tương thích với Azure Event Hubs để consumer đọc thông điệp vào Hub theo mô hình streaming.

Các loại endpoint custom được hỗ trợ cho routing có thể bao gồm:

- **Azure Event Hubs** — luồng message cho streaming consumers/analytics.
- **Azure Service Bus queue** — xử lý công việc độc lập với retries/dead-letter ở downstream.
- **Azure Service Bus topic** — phân phối event cho subscriptions có bộ lọc khác nhau.
- **Azure Storage container** — lưu batch thông điệp để phân tích/lưu trữ.
- **Azure Cosmos DB** — đưa dữ liệu phù hợp vào NoSQL operational store khi routing endpoint hỗ trợ.

| Đích | Mẫu xử lý | Không phải |
|---|---|---|
| **Built-in events endpoint** | Event Hubs-compatible consumer | Custom Event Hubs namespace bạn tự quản |
| **Custom Event Hubs** | Stream Analytics, Java processor, nhiều consumer groups | Database query hoặc hàng đợi công việc |
| **Service Bus queue** | Java/Function xử lý từng việc, retry/DLQ | Dòng thời gian phân tích throughput cực lớn |
| **Service Bus topic** | Nhiều subscribers theo nghiệp vụ | Tự quản WebSocket client connections |
| **Azure Storage** | Archive, replay, data lake | Hệ thống cảnh báo realtime |
| **Cosmos DB** | Dữ liệu JSON phục vụ query/trạng thái | Message broker durable cho nhiều consumers |

**Consumer không mặc định nhận từ một route chỉ vì endpoint tồn tại**. Bạn cần cấu hình producer/route, endpoint connectivity, consumer group/subscription/trigger, identity và quyền cụ thể.

## 7. Built-in Event Hubs-compatible endpoint

Built-in endpoint thường được tham chiếu ở IoT Hub dưới vai trò **messages/events** và có **Event Hubs-compatible name/endpoint**, partition count và chính sách retention theo IoT Hub.

~~~text
Device
  |
  v
IoT Hub
  |
  +-- Built-in events endpoint
  |       |
  |       +-- Consumer group: analytics
  |       +-- Consumer group: diagnostics
  |       +-- Java/Event Hubs SDK processor
  |
  +-- Custom routes -> other endpoints
~~~

### Những điều cần nhớ

- Đây là endpoint **tương thích giao thức Event Hubs** do IoT Hub cung cấp, không đồng nghĩa bạn sở hữu một Event Hubs namespace độc lập.
- Có thể dùng client SDK/consumer tương thích, nhưng phải lấy đúng **Event Hubs-compatible endpoint/name** từ Hub.
- Các consumers nên dùng **consumer groups riêng** nếu cần đọc độc lập.
- Lưu dữ liệu chỉ trong **retention window**, không xem đó là kho lịch sử vô hạn.
- Đọc một event không xóa nó khỏi luồng cho tất cả consumer groups; consumer tự quản offsets/checkpoints.

### Default/fallback route

Hành vi gửi tự động tới built-in endpoint **có thể thay đổi khi bạn tạo routes/custom routing**. Hãy kiểm tra **fallback route** và routes hiện có thay vì giả định mọi telemetry luôn được nhân bản tới built-in endpoint.

**Cách an toàn:** Nếu yêu cầu nghiệp vụ là "mọi telemetry phải vào analytics", định nghĩa **route rõ ràng** đến built-in hoặc custom Event Hubs endpoint với điều kiện phù hợp, rồi kiểm thử đường đến. Đừng chỉ trông chờ mặc định khi đã cấu hình nhiều custom routes.

## 8. Nhiều routes có thể cùng khớp một message

Routing queries **không nhất thiết hoạt động như chuỗi if/else chỉ chọn một route đầu tiên**. Nếu nhiều routes cùng khớp, message có thể được định tuyến tới nhiều endpoints theo cấu hình dịch vụ và giới hạn.

~~~text
Input: temperatureC = 85.4

Route A: true                         -> Event Hubs
Route B: $body.temperatureC > 80      -> Service Bus alerts
Route C: messageType = 'telemetry'    -> Storage archive

Result kỳ vọng:
  A + B + C cùng khớp, các endpoint nhận theo rules
~~~

Điều này hữu ích để **fan-out**: vừa cảnh báo, vừa lưu raw telemetry, vừa tính analytics. Nhưng có thể phát sinh:

- Ghi/nhận trùng nghiệp vụ nếu hai routes đổ vào cùng pipeline.
- Chi phí tăng do nhân nhiều đường dữ liệu.
- Quyền/network/health ở từng endpoint độc lập.
- Thứ tự xử lý giữa endpoints không được bảo đảm chung.

Không xây logic như "nếu route cảnh báo khớp thì route lưu trữ sẽ không chạy" khi chưa có điều kiện loại trừ rõ.

## 9. Fallback route: xử lý message không khớp

**Fallback route** giúp đưa message **không khớp custom routes** tới built-in endpoint theo cấu hình IoT Hub. Nó là cơ chế hữu ích để phát hiện telemetry chưa được phân loại, nhưng không phải một **dead-letter queue** tổng quát cho mọi lỗi downstream.

Ví dụ:

~~~text
Message = {"temperatureC": 22}

route-high-temperature:  condition temperatureC > 80
  -> không khớp

route-raw-type-alarm:     condition messageType = 'alarm'
  -> không khớp

fallback route enabled:
  -> built-in events endpoint theo cấu hình
~~~

### Phân biệt fallback và delivery failure

| Tình huống | Kết quả cần hiểu |
|---|---|
| Không có route nào khớp | Fallback có thể nhận nếu bật/theo cấu hình |
| Route A và B đều khớp | Các endpoints tương ứng có thể được gửi |
| Route khớp nhưng endpoint outage | Là vấn đề **delivery/retry/expiration**, không phải auto-fallback vì "không khớp" |
| Consumer nhận rồi xử lý lỗi | Cần retry/DLQ/replay ở consumer/broker, không phải fallback IoT Hub |

**Đừng gọi fallback route là cơ chế đảm bảo 100% telemetry không mất.** Hãy giám sát route deliveries, endpoint health và có đường archive/replay phù hợp.

## 10. Routing query lọc bằng application properties

Application properties là metadata do client gán bên ngoài JSON body:

~~~text
messageType = telemetry
severity = critical
site = factory-hcm
~~~

Các điều kiện ví dụ theo cú pháp routing query của IoT Hub:

~~~sql
messageType = 'telemetry'
~~~

~~~sql
severity = 'critical' AND site = 'factory-hcm'
~~~

Điểm cần chú ý:

- Property names và values phải khớp quy ước đặt tên/kiểu dữ liệu.
- Application properties do **thiết bị tạo** có thể không đáng tin với quyết định authorization.
- Routing query không biến property thành claim được Azure Entra ID ký.
- Với thông điệp thiếu property, query có thể không khớp; xây test cho field undefined/null.
- Nếu client SDK ánh xạ property khác, dùng device simulator để đọc lại message thực tế.

**Định tuyến bằng application properties** thường dễ dự đoán hơn parse body khi message payload có schema thay đổi, nhưng vẫn cần kiểm soát nguồn gửi và validation downstream.

## 11. Routing query lọc theo JSON body

Khi routing theo content, IoT Hub cần biết message body là **JSON UTF-8** qua các thuộc tính phù hợp.

Ví dụ message:

~~~json
{
  "temperatureC": 82.7,
  "vibrationMmS": 15.8,
  "recordedAtUtc": "2026-11-20T08:15:30Z"
}
~~~

System properties từ device SDK cần chỉ rõ:

~~~text
contentType = application/json
contentEncoding = utf-8
~~~

Một routing query minh họa:

~~~sql
$body.temperatureC > 80
~~~

~~~sql
$body.temperatureC > 80 AND $body.vibrationMmS > 10
~~~

### Vì sao route không khớp dù dữ liệu đúng?

- Thiếu **contentType** hoặc **contentEncoding** nên IoT Hub không đánh giá body dưới dạng JSON theo điều kiện.
- **temperatureC** là chuỗi thay vì số.
- Device gửi **TemperatureC** khác **temperatureC**.
- JSON bị lỗi syntax/encoding.
- Message có nested schema nhưng query dùng sai path.
- Route chọn sai message source hoặc bị disabled.

**IoT Hub routing query không phải một trình xử lý ETL tổng quát**. Nếu cần chuyển đổi Fahrenheit → Celsius, validate JSON Schema phức tạp hoặc join asset metadata, dùng Stream Analytics, Azure Functions hoặc Java processor sau endpoint.

## 12. System properties và device connection identity

IoT Hub có system metadata liên quan đến **connection device ID**, enqueue time, message type và các thông tin được dịch vụ định nghĩa. Một routing query có thể tham chiếu system properties theo cú pháp có tiền tố **$** khi tính năng hỗ trợ:

~~~sql
$connectionDeviceId = 'sensor-a'
~~~

Tuy nhiên, thuộc tính system có thể khác theo message source, ngữ cảnh và API; đối chiếu **routing query syntax** cho source và loại property thực tế.

### Dùng device ID làm filter có đủ không?

Phù hợp nếu định tuyến một vài thiết bị thử nghiệm. Không nên tạo hàng nghìn routes **mỗi thiết bị một route** nếu có thể gom theo **site, device twin metadata, message type** hoặc downstream logic. Cần cân nhắc giới hạn routes/endpoints và vận hành IaC.

### System time vs device time

- **recordedAtUtc** trong body do thiết bị gửi; có thể sai do đồng hồ lệch.
- **IoT Hub enqueued time** được Hub gán khi tiếp nhận.
- **processedAtUtc** do worker gán khi xử lý.

Trong Stream Analytics, windowing và xử lý late/out-of-order cần biết đang dùng **event time** hay **arrival time**. Không giả định event cũ sẽ tự bị loại nếu bạn chưa khai báo watermark/late arrival policy.

## 13. Bảng chọn endpoint theo mục tiêu nghiệp vụ

Giả sử hệ thống có ba yêu cầu: **cảnh báo ngay**, **tính số liệu theo cửa sổ thời gian** và **lưu raw data 12 tháng**. Không nhất thiết phải chọn một endpoint cho cả ba.

| Nhu cầu | Endpoint/pipeline nên đánh giá | Vì sao | Điều cần bổ sung |
|---|---|---|---|
| Cảnh báo nhiệt độ cao | Service Bus queue → Java worker/Function | Điều phối công việc, retry và DLQ ở downstream | Kiểm tra ngưỡng, dedup, chống spam cảnh báo |
| Dashboard gần thời gian thực | Event Hubs → Stream Analytics/Java consumer | Streaming nhiều events với consumer groups | Windows, late arrivals, sink dữ liệu |
| Audit/replay | Azure Storage container | Lưu trữ dữ liệu gốc theo batch/format | Retention, immutable policies nếu cần, partition theo ngày |
| Tra vấn JSON thiết bị | Cosmos DB | Query, TTL, phân vùng và truy cập ứng dụng | Partition key, RU, indexing, schema migration |
| Nhiều microservices nhận alert | Service Bus topic | Mỗi subscription độc lập xử lý | Subscription filters, DLQ và quyền |
| Realtime web notifications | Alert worker → Web PubSub | Push tới browser | Authentication/authorization, reconnect |

**Endpoint routing và downstream processor là hai trách nhiệm khác nhau.** Route tới Event Hubs không tự tạo báo cáo; route tới Service Bus không tự chạy Java logic; route tới Storage không tự tạo index truy vấn.

### Khi nào dùng nhiều endpoint?

Một kiến trúc thực tế có thể:

~~~text
IoT Hub -- all telemetry --> Event Hubs --> Stream Analytics
       |
       +-- all telemetry --> Storage archive
       |
       +-- hot readings --> Service Bus queue --> Java alerts
~~~

Thiết kế này tăng độ độc lập giữa pipelines nhưng kéo theo **chi phí mỗi đích, IAM, vận hành và khả năng dữ liệu khác thời điểm giữa hệ thống**.

## 14. Custom Event Hubs endpoint: dành cho streaming

**Azure Event Hubs** là nền tảng thu nhận sự kiện throughput cao theo partitioned log. Dùng endpoint Event Hubs riêng khi:

- Cần consumer groups/retention/throughput quản trị độc lập IoT Hub.
- Nhiều ứng dụng Java/Stream Analytics/analytics jobs cùng đọc.
- Muốn tách lifecycle stream và IoT Hub, hoặc quản lý network/IAM cụ thể.
- Cần scale partition/throughput theo tải và SKU Event Hubs đã chọn.

~~~text
IoT Hub route "all-telemetry"
              |
              v
Custom Event Hubs endpoint: eh-telemetry
       |
       +-- consumer group: stream-analytics
       |
       +-- consumer group: java-aggregator
       |
       +-- consumer group: diagnostics
~~~

### Consumer groups và checkpoints

Mỗi consumer group biểu diễn một góc nhìn đọc độc lập lên stream. Trong cùng consumer group, các instances processor thường phối hợp phân phối partitions. Khi consumer restart, **checkpoint/offset** giúp xác định vị trí đọc lại.

**Event Hubs retention không phải permanent archive**. Nếu processor ngừng lâu hơn khoảng retention, không thể chắc chắn replay dữ liệu cũ từ Event Hubs; vì vậy archive ra Storage có thể là một nhu cầu độc lập.

### Partition key và ordering

Mỗi event có thể được phân phối vào một partition theo cơ chế dịch vụ. Event ordering thường chỉ nên được kỳ vọng **trong phạm vi một partition và chuỗi sự kiện có cùng điều kiện routing**, không có global ordering giữa nhiều partitions/regions/routes. Mọi nghiệp vụ cần ordering theo device nên thiết kế **device sequence number + checkpoint + dedup**.

### Built-in hay custom Event Hubs?

Built-in endpoint thuận tiện khi mới học hoặc pipeline nhỏ, còn custom endpoint cho phép **quản trị Event Hubs độc lập**. Đừng chuyển sang custom chỉ vì tên có chữ "Event Hubs": việc chọn còn liên quan quota, cost, security, operations và downtime khi migrate consumers.

## 15. Service Bus queue: xử lý từng cảnh báo

Khi cảm biến gửi thông điệp nhiệt độ cao, một **route theo điều kiện** đưa tới Service Bus queue. Java worker lấy message và thực hiện nghiệp vụ.

~~~text
Sensor: temperatureC=85
       |
       v
IoT Hub route hot-reading
       |
       v
Service Bus queue: telemetry-alerts
       |
       v
Java AlertProcessor
  +-- Validate telemetry schema
  +-- Lookup trusted asset/device mapping
  +-- Deduplicate event
  +-- Check alert state / cooldown
  +-- Persist alarm + notify operator
~~~

### Tại sao không gửi SMS/email ngay trong IoT Hub route?

Routing không chạy arbitrary Java handler. Đưa vào queue rồi xử lý giúp:

- Backpressure và tách tải telemetry khỏi dịch vụ email/SMS.
- Retry khi downstream tạm lỗi.
- Dead-letter khi một event không thể xử lý theo chính sách.
- Truy vết message ID, worker attempt và trạng thái nghiệp vụ.

### Service Bus không thay IoT Hub

IoT Hub quản lý **device connectivity/identity**, còn Service Bus queue quản lý **enterprise messaging** giữa cloud services. Không nên yêu cầu mọi thiết bị gửi trực tiếp vào Service Bus thay IoT Hub nếu hệ thống cần provisioning/twin/device security và protocol support.

### Dead-letter queue (DLQ)

Service Bus có cơ chế DLQ. Một message không xử lý được do schema sai, quyền asset sai hoặc retry vượt giới hạn có thể cần xử lý thủ công. **Không auto-complete rồi xóa event khi business transaction thực sự thất bại**; nhưng cũng không retry vô tận một invalid schema không thể tự sửa.

## 16. Service Bus topic: một sự kiện cho nhiều nghiệp vụ

Khi cùng cảnh báo cần được xử lý độc lập bởi hệ thống bảo trì, an toàn và báo cáo, topic/subscriptions có thể phù hợp hơn queue:

~~~text
IoT Hub route severe-events
          |
          v
Service Bus topic: factory-events
          |
          +-- subscription maintenance
          |        -> Java CMMS integration
          |
          +-- subscription safety
          |        -> Incident processing
          |
          +-- subscription reporting
                   -> Analytics projection
~~~

**IoT Hub routing query** quyết định messages nào đi tới **topic endpoint**. **Service Bus subscription rules/filters** có thể phân chia tiếp cho từng subscriber theo properties do broker nhận; đó là hai lớp cấu hình khác nhau.

### Fan-out và duplicate

Một event có thể được xử lý bởi nhiều subscriptions, điều này là chủ đích. Nhưng cùng một subscription khi retry vẫn có thể xử lý lặp, vì vậy business actions cần **idempotency** theo eventId và đối tượng nghiệp vụ.

### Khi không dùng topic?

Nếu chỉ có một worker và không cần publish-subscribe, queue đơn giản hơn. Topic còn đi kèm chi phí/giới hạn, lifecycle của subscriptions và quản lý quyền phức tạp hơn.

## 17. Azure Storage endpoint: archive telemetry

Một route tới **Azure Storage container** có thể giúp lưu raw telemetry theo định dạng/partitioning mà IoT Hub hỗ trợ.

~~~text
IoT Hub -- route archive --> Blob Storage container
                                    |
                                    +-- time-partitioned blobs
                                    +-- batch/format configured by route
                                    +-- lifecycle retention rules
                                    |
                                    v
                          Data lake / Spark / SQL analytics
~~~

### Những quyết định cần đưa ra

| Quyết định | Ví dụ/ý nghĩa |
|---|---|
| **Storage account region** | Cùng vùng hoặc vùng đáp ứng residency |
| **Container name** | telemetry-raw |
| **Encoding/format** | JSON hoặc AVRO theo endpoint hỗ trợ |
| **Blob naming/partitioning** | Tổ chức theo ngày/giờ/IoT Hub metadata |
| **Batch/aggregation time** | Trade-off file size và độ trễ xuất hiện |
| **Retention/lifecycle** | Hot → Cool/Archive → xóa theo policy |
| **Network/IAM** | Managed identity hoặc khóa/SAS theo cơ chế endpoint |
| **Integrity/replay** | Tính số events, dedup và kiểm chứng |

### Không nhầm Storage route là realtime alert

IoT Hub có thể **gộp thông điệp thành blobs**, vì vậy event không nhất thiết thành một blob riêng ngay sau khi thiết bị gửi. Những hệ thống cần báo động trong vài giây nên dùng luồng streaming/queue riêng, không chờ archive batch.

### File format và schema

Nếu chọn AVRO, consumer phải dùng decoder/schema phù hợp. Nếu chọn JSON, kiểm tra cách IoT Hub đóng gói **metadata, messages và body** trong file, thay vì giả định file chứa một đối tượng JSON sensor thuần túy. Có thể cần downstream ETL để normalize.

**Azure Storage lifecycle rules không phải cơ chế lưu vô hạn**. Định kỳ kiểm tra retention và pháp lý dữ liệu; việc xóa archive có thể làm mất khả năng replay nếu Event Hubs cũng hết retention.

## 18. Azure Cosmos DB endpoint: lưu telemetry có thể truy vấn

Một số mô hình IoT dùng **Azure Cosmos DB for NoSQL** làm đích để truy vấn dữ liệu theo thiết bị, thời gian, địa điểm hoặc trạng thái. Với IoT Hub routing hỗ trợ Cosmos DB endpoint theo cấu hình, cần lập kế hoạch:

- JSON schema và kiểu thuộc tính.
- **Partition key** phân bố đủ tốt theo workload.
- TTL/retention và RU/s hoặc autoscale.
- Index policy theo query patterns (không index mọi payload lớn nếu không cần).
- Data-plane role và quản lý network.
- Duplicate/late messages và item identity.

### Ví dụ read model

~~~json
{
  "id": "sensor-a-0000182",
  "deviceId": "sensor-a",
  "siteId": "factory-hcm",
  "temperatureC": 81.4,
  "recordedAtUtc": "2026-11-20T08:15:30Z",
  "ingestedAtUtc": "2026-11-20T08:15:31Z"
}
~~~

Đây là **dạng dữ liệu mong muốn** để query, không cam kết IoT Hub tự tạo đủ các fields hoặc ánh xạ JSON body chính xác như hình. Nếu cần bổ sung **deviceId đáng tin, ingestedAtUtc, chuẩn hóa schema hoặc deterministic item id**, đặt **Azure Function/Java transformation processor** giữa IoT Hub route và Cosmos DB.

### Khi nào nên có một processor trước Cosmos DB?

- Payload không hợp lệ hoặc thiết bị nhiều schema versions.
- Cần map device ID sang tenant/asset đã kiểm tra.
- Cần idempotent upsert.
- Cần encryption/redaction/normalization.
- Cần custom partition key/id transformation.
- Cần thống kê trước khi ghi để giảm RU.

**Cosmos DB không phải một hàng đợi dùng để bảo đảm mọi consumer đọc message đúng một lần**. Nếu nguồn dữ liệu cần replay và nhiều consumer độc lập, Event Hubs hoặc Service Bus cùng archive/processor có thể phù hợp hơn.

## 19. Azure Functions nhận telemetry qua endpoint

**Azure Functions** có thể được kích hoạt bởi:

- **Event Hubs trigger** đọc custom/built-in Event Hubs-compatible endpoint khi cấu hình được hỗ trợ.
- **Service Bus trigger** đọc queue/subscription của đường cảnh báo.
- **Blob trigger** hoặc pipeline thích hợp khi data đã archive.

### Ví dụ Java Event Hubs trigger

~~~java
package com.example.iot;

import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.EventHubTrigger;
import com.microsoft.azure.functions.annotation.FunctionName;

public class TelemetryFunctions {

    @FunctionName("processTelemetry")
    public void processTelemetry(
        @EventHubTrigger(
            name = "telemetryEvent",
            eventHubName = "%EVENT_HUB_NAME%",
            connection = "EVENT_HUB_CONNECTION",
            consumerGroup = "%EVENT_HUB_CONSUMER_GROUP%"
        ) String message,
        ExecutionContext context) {

        // Message có thể là envelope/body theo binding configuration.
        // Parse, validate, kiểm tra metadata/identity và idempotency.
        context.getLogger().info("Telemetry event received");
        // Không log raw payload nếu có dữ liệu nhạy cảm.
    }
}
~~~

**Code này là function skeleton**: cần Maven **azure-functions-java-library**, cấu hình Function host và bindings tương thích, local.settings.json/app settings và quyền đọc Event Hubs. Tên **EVENT_HUB_CONNECTION** là tên cấu hình binding, không phải URL/secret ghi thẳng trong code. Kiểm tra cách biểu diễn Event Hubs-compatible endpoint của IoT Hub nếu dùng built-in route, vì endpoint/name khác Event Hubs namespace tự quản.

### Thực thi Functions không đảm bảo chỉ một lần

Trigger có thể chạy lại sau failure/rebalance/timeout. Cần dùng messageId/deviceId/sequence number để dedup, lưu checkpoint theo processor và bảo vệ database writes idempotently.

### Khi có lưu lượng rất cao

Hệ thống serverless có scale limits, concurrency, cold start và downstream constraints. Đừng chỉ tăng Functions instances nếu Azure SQL/Cosmos DB/notification API là bottleneck; cần throttle/backpressure và budget.

## 20. Java worker xử lý Service Bus queue

Để nhận cảnh báo từ IoT Hub route tới Service Bus queue, Java service có thể dùng **Azure Service Bus SDK** với một processor client.

~~~java
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusProcessorClient;
import com.azure.messaging.servicebus.models.ServiceBusErrorContext;
import com.azure.messaging.servicebus.models.ServiceBusReceivedMessageContext;

public class AlertWorker {
    public static void main(String[] args) throws Exception {
        String connection = System.getenv("SERVICE_BUS_CONNECTION_STRING");
        if (connection == null || connection.isBlank()) {
            throw new IllegalStateException("Missing Service Bus credential");
        }

        ServiceBusProcessorClient processor =
            new ServiceBusClientBuilder()
                .connectionString(connection)
                .processor()
                .queueName("telemetry-alerts")
                .processMessage(AlertWorker::handle)
                .processError(AlertWorker::onError)
                .buildProcessorClient();

        processor.start();
        // Worker host giữ process sống và quản lý shutdown.
        // Ở ứng dụng thật: đóng processor khi host kết thúc.
    }

    private static void handle(ServiceBusReceivedMessageContext ctx) {
        String payload = ctx.getMessage().getBody().toString();
        // Parse JSON, validate, kiểm tra idempotency và business commit.
        // Không log payload nhạy cảm hoặc xử lý alert trực tiếp ở đây.
    }

    private static void onError(ServiceBusErrorContext ctx) {
        // Ghi operation/entity/error code đã redaction.
        System.err.println("Service Bus processing error");
    }
}
~~~

Đây là **mẫu kiến trúc**, không phải worker vận hành hoàn chỉnh: phải pin dependency **com.azure:azure-messaging-servicebus**, xử lý concurrency, lock renewal, settlement mode, dead-letter, graceful shutdown và monitoring. **Không đặt namespace connection string thật trong code hoặc Git**; với production, ưu tiên credential/token identity được hỗ trợ.

### Auto-complete và lỗi nghiệp vụ

Với SDK processor có auto-complete theo mặc định/configuration, việc callback kết thúc thành công thường dẫn tới complete. Nếu callback bỏ qua validation hoặc bắt exception rồi trả bình thường, hệ thống có thể **đánh dấu hoàn tất dù chưa ghi cảnh báo**. Chọn settlement mode, retry và DLQ phù hợp để tránh silent data loss.

### Java consumer phải hiểu route source

Service Bus message sau IoT Hub routing có thể có **body và metadata** theo cách endpoint đóng gói. Phải kiểm tra metadata thực tế (device ID, message ID, content type) ở môi trường lab và normalize; không giả định message luôn có body JSON thuần nếu SDK/binding hiển thị envelope khác.

## 21. Stream Analytics làm sạch và tổng hợp telemetry

**Azure Stream Analytics** có thể nhận stream từ IoT Hub hoặc Event Hubs theo input configuration hỗ trợ, xử lý cửa sổ thời gian và đưa dữ liệu tới sink.

Một query khái niệm cho nhiệt độ trung bình theo cửa sổ 1 phút:

~~~sql
SELECT
    deviceId,
    System.Timestamp() AS windowEnd,
    AVG(CAST(temperatureC AS float)) AS avgTemperatureC,
    COUNT(*) AS sampleCount
INTO
    [temperature-averages]
FROM
    [telemetry-input] TIMESTAMP BY recordedAtUtc
GROUP BY
    deviceId,
    TumblingWindow(minute, 1)
~~~

**Đây là mô hình query dành cho Stream Analytics**, không phải routing query của IoT Hub hoặc T-SQL Azure SQL. Cần cấu hình input/output aliases, event time mapping, kiểu dữ liệu, late arrival/out-of-order policy và partitioning; cú pháp CAST/types và named fields phải kiểm tra theo schema thực.

### Chức năng phân chia

- **IoT Hub routing query:** lọc và chuyển message đến endpoint.
- **Stream Analytics SQL:** biến đổi, aggregate/window, join stream/reference data theo điều kiện.
- **Java downstream service:** nghiệp vụ tùy biến, enrichment, persistence và notification.

Nếu cần average theo phút, IoT Hub không tự tạo AVG/COUNT chỉ vì route có điều kiện temperature > 80.

## 22. Azure Event Grid và các sự kiện IoT

**Azure Event Grid** thường được dùng cho sự kiện có subscription/filter/handler theo mô hình event-driven. IoT Hub có tích hợp các **event types** như thay đổi vòng đời thiết bị và những tính năng telemetry-related được hỗ trợ theo tài liệu.

### Không gộp ba khái niệm

| Thành phần | Chức năng |
|---|---|
| **IoT Hub message routing** | Tuyến D2C messages theo rules tới endpoints được hỗ trợ |
| **Event Grid event subscription** | Phân phối các event types từ publisher tới handlers theo schema của Event Grid |
| **Stream Analytics/Event Hubs** | Phân tích/tiêu thụ stream liên tục |

Nếu mục tiêu là **đưa mọi telemetry với throughput cao vào pipeline streaming**, Event Hubs-compatible endpoint hoặc custom Event Hubs thường là tuyến tự nhiên. Nếu mục tiêu là **phản ứng với device lifecycle event**, Event Grid có thể phù hợp.

**Không coi route tới Event Grid là một custom endpoint trong danh sách Event Hubs/Service Bus/Storage** nếu IoT Hub Portal thực tế không cung cấp loại endpoint đó. Thiết kế kết nối Event Grid bằng đúng event subscription/feature được hỗ trợ.

## 23. IoT Edge: xử lý tại biên trước khi định tuyến cloud

Ở nhà máy mạng không ổn định, có thể xử lý ở gateway/thiết bị biên:

~~~text
Sensors -> Edge gateway / local processor
           |
           +-- Local validation / aggregation / anomaly flag
           +-- Store-and-forward khi mất mạng theo khả năng edge
           |
           v
        IoT Hub
           |
           +-- Routes -> cloud processors
~~~

IoT Edge runtime/hệ sinh thái modules có cơ chế route và store-and-forward **riêng ở edge**, không đồng nhất với **IoT Hub cloud message routing**. Một event đã được edge gửi tới IoT Hub có thể bị xử lý theo IoT Hub routes; nhưng một message còn nằm trong edge local queue chưa phải message IoT Hub đã tiếp nhận.

### Khi nào edge processing có lợi?

- Băng thông WAN hạn chế: gửi **aggregates** thay vì dữ liệu raw liên tục.
- Cần cảnh báo local ngay cả khi mất Internet.
- Có dữ liệu camera/audio lớn cần suy luận gần thiết bị.
- Muốn lọc những mẫu bất thường trước khi gửi cloud.

### Trade-off

- Dữ liệu thô có thể không lên cloud nếu chỉ gửi aggregate.
- Phải quản lý version, identity, disk buffer và tình huống mất điện edge.
- Dữ liệu đến cloud muộn cần xử lý event time.
- Security/patching của edge devices vẫn là trách nhiệm vận hành.

## 24. Java device simulator gửi D2C telemetry

Trong bài lab, một **Java simulator** đóng vai thiết bị thử nghiệm có danh tính riêng trong IoT Hub. Nó sử dụng **Azure IoT device SDK for Java** với một device-level credential; **không sử dụng iothubowner/service-wide key** trên thiết bị.

### Luồng gửi

~~~text
Java simulator
  |
  +-- Read device identity credential securely
  +-- Construct JSON telemetry
  +-- Set contentType=application/json
  +-- Set contentEncoding=utf-8
  +-- Add application property messageType=telemetry
  +-- Send D2C event asynchronously
  |
  v
Azure IoT Hub (authenticated device)
  |
  v
Routing engine evaluates message source/query
~~~

Ví dụ skeleton Java theo mẫu SDK thiết bị truyền thống:

~~~java
import com.microsoft.azure.sdk.iot.device.DeviceClient;
import com.microsoft.azure.sdk.iot.device.IotHubClientProtocol;
import com.microsoft.azure.sdk.iot.device.Message;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class TelemetryDeviceSimulator {
    public static void main(String[] args) throws Exception {
        String deviceConnectionString =
            System.getenv("IOTHUB_DEVICE_CONNECTION_STRING");
        if (deviceConnectionString == null ||
                deviceConnectionString.isBlank()) {
            throw new IllegalStateException(
                "Missing device-scoped credential");
        }

        DeviceClient client = new DeviceClient(
            deviceConnectionString, IotHubClientProtocol.MQTT);

        client.open();
        try {
            String json = """
                {
                  "schemaVersion": 1,
                  "messageId": "sensor-lab-001",
                  "temperatureC": 85.0,
                  "vibrationMmS": 11.0,
                  "recordedAtUtc": "2026-11-20T08:15:30Z"
                }
                """;
            Message message = new Message(
                json.getBytes(StandardCharsets.UTF_8));
            message.setContentType("application/json");
            message.setContentEncoding("utf-8");
            message.setProperty("messageType", "telemetry");
            message.setProperty("site", "factory-lab");

            CountDownLatch completed = new CountDownLatch(1);
            AtomicReference<String> status = new AtomicReference<>("pending");
            client.sendEventAsync(message, (result, context) -> {
                status.set(String.valueOf(result));
                completed.countDown();
            }, null);

            if (!completed.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Send acknowledgement timed out");
            }
            System.out.println("IoT Hub send status: " + status.get());
            // Ứng dụng thật phải kiểm tra enum result và retry policy.
        } finally {
            // Ví dụ đã chờ callback hoặc timeout; cần xử lý timeout/
            // pending sends và graceful shutdown trong ứng dụng thật.
            client.closeNow();
        }
    }
}
~~~

**Đoạn code là ví dụ khái niệm của Azure IoT Java device SDK.** Phải pin dependency **com.microsoft.azure.sdk.iot:iot-device-client** ở phiên bản hỗ trợ, kiểm tra signatures **Message.setContentType/setContentEncoding/sendEventAsync/closeNow**, semantics callback và credential trong dự án thực. Mẫu đã chờ callback tối đa 30 giây nhưng **in status không đồng nghĩa chắc chắn gửi thành công**: cần kiểm tra enum kết quả, lỗi callback, số lần thử và trường hợp timeout/pending send theo SDK đã pin. Trong ứng dụng lâu dài, tái sử dụng DeviceClient thay vì mở/đóng cho từng event.

### Mẫu gửi bằng SDK có điều kiện thực tế

1. Kết nối bằng **device-scoped authentication** và TLS.
2. Tạo **messageId mới** cho mỗi sample thực tế; ví dụ ID cố định ở trên chỉ để minh họa.
3. Đặt **JSON UTF-8 headers** đúng, tránh filter body không khớp.
4. Gửi và chờ acknowledgment của **IoT Hub ingress**, ghi status an toàn.
5. Khi mất mạng, dùng offline queue/store-and-forward nếu yêu cầu.
6. Đóng tài nguyên/clean up theo lifecycle của SDK.

**IoT Hub ingress acknowledgment chỉ chứng minh Hub đã chấp nhận theo giao thức, không chứng minh mọi downstream routes/consumers đã xử lý thành công.**

## 25. Message enrichments và asset metadata

**Message enrichments** cho phép IoT Hub bổ sung một số thông tin vào messages khi định tuyến tới endpoints được cấu hình, tùy loại metadata/tier và hỗ trợ của dịch vụ.

Ví dụ mong muốn:

~~~text
Original device message:
  body: {"temperatureC": 82}
  app property: messageType=telemetry

Trusted metadata configured in IoT Hub:
  assetSite = factory-hcm
  assetClass = refrigeration

Routed message:
  body: same JSON telemetry
  properties: additional enrichment information
~~~

### Vì sao enrich trước khi route?

- Đội phân tích muốn biết Hub/tenant/site nguồn mà không phải join mọi message.
- Nhiều consumer cần cùng một tag hoặc nguồn đáng tin hơn property do thiết bị tự gửi.
- Giảm duplication của bước gắn metadata ở nhiều downstream services.

### Những giới hạn cần nhớ

- Nguồn enrichment có thể là **constant value, IoT Hub name, device twin data** hoặc lựa chọn khác theo service capability.
- Chỉ những paths/properties được hỗ trợ mới có thể được bổ sung; không tự biến enrichment thành ETL tổng quát.
- Device twin tags/properties có thể thiếu hoặc thay đổi, cần thiết kế default/validation.
- Enrichment không thay thế authorization khi một consumer phục vụ nhiều tenants.
- Nếu route query dựa vào enrichment, cần xác minh **thời điểm đánh giá routing query so với enrichment** theo dịch vụ. Không suy luận điều kiện lọc chắc chắn nhìn thấy một property chỉ được thêm ở giai đoạn gửi endpoint.

**Không đồng nhất enrichment metadata với device-reported body**. Hãy phân biệt nguồn và mức tin cậy của từng trường.

## 26. Schema evolution, versioning và type safety

Thiết bị trong nhà máy có thể cập nhật firmware theo từng đợt. Trong cùng một ngày, consumer nhận cả schema version 1 và 2.

~~~json
{
  "schemaVersion": 2,
  "deviceMessageId": "sensor-a-0000183",
  "measurements": {
    "temperatureC": 84.1,
    "vibrationMmS": 12.5
  },
  "recordedAtUtc": "2026-11-20T08:15:40Z"
}
~~~

Giữa v1 và v2, đường dẫn nhiệt độ đổi từ **$body.temperatureC** thành **$body.measurements.temperatureC**. Route lọc version 1 sẽ không tự hiểu version 2.

### Ba phương án migration

1. **Giữ tương thích ngược:** v2 vẫn gửi trường cũ trong giai đoạn chuyển đổi nếu ngân sách/format cho phép.
2. **Mở rộng route condition:** hỗ trợ v1/v2 với điều kiện OR và kiểm tra kiểu dữ liệu, không tự suy luận missing fields.
3. **Normalize downstream:** route rộng theo messageType, dùng Function/Java processor chuyển v1/v2 về canonical schema rồi quyết định alert.

Ví dụ pseudo-condition (phải xác minh cú pháp route engine và kiểu property):

~~~text
version 1: $body.temperatureC > 80
version 2: $body.measurements.temperatureC > 80

Desired: (v1_condition) OR (v2_condition)
~~~

**Không xóa route v1 ngay khi deploy firmware v2**. Thiết bị offline có thể tiếp tục gửi v1 trong thời gian dài; cần xem inventory rollout và message data thực tế.

### Dùng schema registry?

Có thể xây schema registry/contract management ở processor hoặc pipeline analytics tùy công nghệ. IoT Hub routing không tự xác minh toàn bộ JSON Schema cho mọi device event. Backend phải tiếp tục validate schema và giới hạn kích thước payload.

## 27. Delivery semantics: ingress, routing và downstream

Phân biệt ba thời điểm:

~~~text
(1) Device -> IoT Hub ingress accepted
                |
                v
(2) IoT Hub routing -> endpoint accepted
                |
                v
(3) Consumer processed -> DB/business effect committed
~~~

### Một acknowledgment không thay cho tất cả

| Mức | Bằng chứng | Điều chưa chứng minh |
|---|---|---|
| **Device send acknowledged** | Hub nhận message | Endpoint đã lưu hoặc xử lý |
| **Route delivery succeeded** | Endpoint nhận theo service semantics | Java consumer đã commit nghiệp vụ |
| **Broker message completed/checkpointed** | Consumer xác nhận vị trí/xử lý | Alert SMS/email đã tới người dùng |
| **Business effect recorded** | DB transaction/audit | Người dùng đã xem cảnh báo |

Trong kiến trúc message-driven, hãy thiết kế **at-least-once-compatible processing** và deduplication. Không mặc định message chỉ một lần hoặc globally ordered.

### Message ID và device sequence

Thiết bị nên gửi **eventId ổn định** cho một phép đo khi retry; nếu tạo ID mới mỗi lần retry, backend không phát hiện được trùng. Một thiết kế có thể dùng:

~~~text
idempotencyKey = hubId + deviceId + deviceSequence
~~~

Trong đó **deviceSequence** tăng theo thiết bị/phiên đo và cần mô tả hành vi reset/reboot. Nếu không đảm bảo uniqueness, kết hợp timestamp và ID phát sinh hoặc dùng idempotency contract khác. **Không dùng timestamp một mình làm ID duy nhất** nếu nhiều readings có thể cùng timestamp.

### Khi endpoint bị lỗi

IoT Hub có cơ chế retry/expiration cho route deliveries theo dịch vụ và timeout/retention được cấu hình. **Không cam kết retries vô hạn hoặc tự chuyển sang fallback route nếu endpoint không phản hồi**. Dùng metrics, alerting, endpoint health và archive/replay design để xử lý mất dữ liệu ngoài retention window.

## 28. Phân phối trùng và thứ tự sự kiện

Ví dụ thiết bị gửi:

~~~text
seq=101 temperature=78 C
seq=102 temperature=85 C
seq=103 temperature=83 C
~~~

Một Java worker có thể nhận **102 hai lần** sau retry hoặc xử lý **103 trước 102** khi nhiều partitions/instances tham gia. Nếu business logic gửi một email mới cho mỗi message có nhiệt độ >80, hệ thống có thể spam người vận hành.

### Cách xử lý

- Dùng **eventId/deviceSequence** làm deduplication key.
- Chỉ tạo một active alert theo **deviceId + alertType** trong một khoảng cooldown.
- Dùng compare-and-set/version hoặc transaction để cập nhật last processed sequence.
- Ghi event vào database với unique constraint/upsert phù hợp.
- Áp event-time window và policy late arrivals khi tính aggregates.
- Lưu raw stream/archive nếu cần forensic reconciliation.

### Tình huống thiết bị gửi sai đồng hồ

Nếu recordedAtUtc ở quá khứ/tương lai, có thể phải dùng IoT Hub enqueued time để xác định ingestion delay và áp chính sách giới hạn clock skew. Không sửa timestamp thiết bị rồi mất original time nếu cần trace.

## 29. Backpressure, throttling và poison messages

IoT Hub có giới hạn units, message ingress/egress, routing endpoints và throughput theo tier. Endpoint downstream cũng có giới hạn riêng.

### Đường tắc nghẽn điển hình

~~~text
10.000 devices -> IoT Hub ingress
                       |
                       v
               Service Bus queue
                       |
                       v
                Java workers
                       |
                       v
                   Azure SQL

Khi DB ghi chậm:
  queue backlog tăng
  message age tăng
  lock timeout/retry có thể tăng
~~~

### Những biện pháp cơ bản

1. Đo message rate/size và peak theo site/device.
2. Xác định bottleneck ở **ingress**, **route**, **endpoint** hay **consumer**.
3. Giới hạn concurrency ở Java workers theo database capacity.
4. Retry transient errors có backoff/jitter và max attempts.
5. Quarantine/dead-letter invalid schema ("poison messages") theo broker capability.
6. Không auto-complete message khi business transaction chưa thành công.
7. Scale endpoint/consumer khi đã đo được resource limits và chi phí.

**Không tăng IoT Hub units để sửa mọi lỗi**. Nếu Service Bus permission sai, Azure SQL indexes thiếu hoặc Java parser crash, scale Hub không cải thiện nguyên nhân.

## 30. Managed identity cho IoT Hub routing endpoints

Trong các cấu hình được hỗ trợ, **IoT Hub có thể sử dụng managed identity** để kết nối với custom endpoints thay cho một số connection strings/keys. Đây là kết nối **IoT Hub → dịch vụ đích**, khác danh tính thiết bị và khác danh tính Java consumer.

~~~text
IoT Hub managed identity
       |
       | Data-plane role on destination
       v
Custom Event Hubs / Service Bus / Storage / Cosmos DB
       |
       | Different identity and permission
       v
Java consumer / Azure Function
~~~

### Vai trò theo đích

| Destination | Quyền cần đánh giá |
|---|---|
| Event Hubs | Quyền gửi events trên Event Hub cụ thể |
| Service Bus queue/topic | Quyền gửi vào entity tương ứng |
| Azure Storage | Quyền ghi blob vào container/account theo cấu hình |
| Cosmos DB | Data-plane permission ghi trong database/container theo API |

Ví dụ các RBAC roles built-in trong Azure có thể có tên **Azure Event Hubs Data Sender**, **Azure Service Bus Data Sender**, **Storage Blob Data Contributor** hoặc role Cosmos DB data-plane phù hợp. **Không có một role tên "Contributor" dùng cho mọi destination/data-plane.** Kiểm tra cách IoT Hub endpoint hỗ trợ managed identity và role definition cụ thể.

### Mối quan hệ management/data plane

- Operator có quyền tạo route trong IoT Hub chưa chắc được xem keys của storage.
- IoT Hub managed identity có quyền **send** vào queue không đồng nghĩa Java worker có quyền **receive**.
- Java worker có quyền đọc event stream không đồng nghĩa được ghi SQL hoặc gọi device method.

Thiết kế theo **least privilege** ở từng chặng và kiểm thử bằng identity thật, không dùng Owner/admin để làm mọi thứ.

## 31. Network: firewall, private endpoints và đường đi của Hub

Một custom endpoint có thể dùng firewall/private network restrictions. IoT Hub routing phải được cấp **đường truy cập dịch vụ phù hợp** theo tính năng network/managed identity được hỗ trợ.

~~~text
IoT devices
    |
    | TLS to IoT Hub public/private ingress as configured
    v
Azure IoT Hub
    |
    | Service-to-service routing
    v
Azure Event Hubs / Service Bus / Storage endpoint
    |
    | Private endpoint/VNet integration for Java consumer
    v
Azure Function / AKS / App Service
~~~

### Hai kết nối không giống nhau

1. **Device → IoT Hub**: MQTT/AMQP/HTTPS, DNS, TLS, device auth, IoT Hub network restrictions.
2. **IoT Hub → custom endpoint**: service-managed routing path và endpoint network policy.
3. **Consumer → endpoint**: Java process/Function VNet, DNS, firewall, SDK identity.

Việc AKS worker có Private Endpoint tới Service Bus **không chứng minh IoT Hub routing có thể gửi vào Service Bus**; đường IoT Hub → Service Bus là một hop riêng. Một Private Endpoint chỉ dành cho consumer cũng không mở đường routing nếu đích cấm truy cập từ Hub.

### Chuyển sang private networking an toàn

- Kiểm tra resource SKU/network support, managed identity và policies.
- Cấu hình destination để chấp nhận IoT Hub routing theo cơ chế Azure cung cấp.
- Thử message delivery từ thiết bị lab thực.
- Kiểm tra private DNS/network của consumers.
- Chỉ vô hiệu public access sau khi từng hop hoạt động.
- Chuẩn bị đường admin/emergency và rollback configuration.

Không bật "allow all trusted Microsoft services" một cách mù quáng: tính năng này có phạm vi và điều kiện cụ thể, cần security review.

## 32. Bảo vệ thiết bị và dữ liệu telemetry

Các thiết bị có thể bị chiếm quyền, gửi dữ liệu giả hoặc ngắt kết nối. Bảo mật ở cloud cần bắt đầu từ device:

1. Dùng **device-level identity**; cấp quyền tối thiểu cho từng thiết bị.
2. Ưu tiên **DPS (Device Provisioning Service)** nếu cần đăng ký hàng loạt theo quy trình.
3. Bảo vệ khóa/certificate bằng TPM/HSM hoặc cơ chế an toàn tương ứng khi có.
4. Rotate/revoke credentials khi thiết bị bị thay thế/compromised.
5. Dùng TLS và hạn chế inbound control từ cloud theo chính sách.
6. Kiểm tra device-to-asset mapping ở backend.
7. Áp schema validation, bounds checks và anomaly detection.
8. Đặt retention/PII policy cho location/serial number/user-related telemetry.
9. Không lưu IoT Hub owner/shared access policy key trên firmware.
10. Có firmware update, signed packages và inventory monitoring theo giải pháp thiết bị.

### Data integrity và trust

Một cảm biến bị tấn công có thể gửi **temperatureC=999** dù đã được xác thực bằng device key hợp lệ. Authentication chứng minh credential, không chứng minh dữ liệu vật lý chính xác. Các action nguy hiểm như tắt máy phải qua safety policy và xác nhận theo kiến trúc OT/industrial controls.

### Không đưa bí mật vào logs

IoT device connection strings, SAS tokens, X.509 private keys, Event Hubs/Service Bus credentials và Blob SAS đều không nên xuất hiện trong Java console logs, dead-letter diagnostics hoặc tickets.

## 33. Retention, replay và đối soát dữ liệu

Một pipeline chỉ gồm IoT Hub → Function → dashboard dễ mất khả năng phân tích lại dữ liệu sau sự cố. Nếu retention quan trọng, thiết kế **archive path** độc lập.

~~~text
IoT Hub
   |
   +-- Event Hubs --> Stream Analytics --> Dashboard
   |
   +-- Storage archive --> Offline replay/reprocess
                                |
                                v
                         Java batch processor
~~~

### Replay có giới hạn

- Event Hubs chỉ giữ dữ liệu trong **retention window**.
- Service Bus queue khi message completed thì không phải bản sao historical để replay; DLQ chỉ chứa một số events lỗi.
- Azure Storage archive có thể giữ dài hơn nhưng cần xác định file naming, schema, dedup và sự toàn vẹn.
- Cosmos DB có TTL/retention và không mặc định giữ raw telemetry mãi mãi.

**Không đồng nghĩa "đã gửi vào hai endpoints" là có hai bản sao dữ liệu chính xác 100%**. Hai routes có thể có retry, lag, endpoint failures khác nhau; đối soát theo messageId/time-window để đánh giá mất/trùng.

### Một quy trình đối soát

1. Đếm số readings theo device/site trong khoảng 10 phút ở ingress khi có metric phù hợp.
2. Đếm messages delivered từng endpoint từ Hub metrics/diagnostics.
3. Đếm messages processed/checkpointed ở consumer.
4. Đếm rows/items persisted ở sink.
5. Dùng eventId để phát hiện duplicate và gaps.
6. Khi lệch, kiểm tra retry, dead-letter, schema errors, retention và network.

**Số counts không luôn trùng** nếu routes có filters/fan-out, Storage batching hoặc hợp lệ hóa loại bỏ events; cần ghi kỳ vọng theo từng route trước khi so sánh.

## 34. Cấu hình route trên Azure Portal

Với một **IoT Hub sandbox** đã được cấp quyền và ngân sách, quy trình tổng quát:

1. Vào [Azure Portal](https://portal.azure.com), mở đúng subscription và **IoT Hub**.
2. Chọn phần **Message routing/Routing** theo giao diện hiện hành.
3. Xem các routes, endpoints và trạng thái **fallback route** hiện có.
4. Tạo **custom endpoint** trước nếu đích không phải built-in endpoint.
5. Chọn nguồn **Device Telemetry Messages**.
6. Đặt route name có ý nghĩa, ví dụ **route-hot-temperature-lab**.
7. Nhập query **$body.temperatureC > 80** hoặc điều kiện phù hợp.
8. Chọn đích **Service Bus queue** đã kiểm tra network/permissions.
9. Bật route; dùng khả năng **Test route** nếu Portal/API có hỗ trợ.
10. Gửi các telemetry messages giả lập từ device test, quan sát endpoint và metrics.

### Điều cần kiểm tra trước khi bấm Save

- Đúng **hub/subscription/resource group**, không phải production.
- Route source có phù hợp device telemetry.
- Condition syntax đúng và trường JSON có type mong đợi.
- Custom endpoint được tạo và có **authorization/network**.
- Đã biết fallback behavior nếu message không khớp.
- Đã xác nhận route khác có thể cùng khớp, tránh double processing.
- Có phương án rollback nếu route gây lỗi/cost tăng.

**Không cấu hình trực tiếp trên Hub production** khi chưa có change approval. Một route condition sai hoặc thay fallback có thể làm mất luồng dữ liệu mong đợi từ hàng nghìn thiết bị.

### Test route khác kiểm thử delivery

Khả năng kiểm tra query trên một sample có thể xác minh **route condition matching**, nhưng không chứng minh endpoint thực sự nhận message và consumer commit thành công. Sau test condition, vẫn cần gửi telemetry thật từ device test/simulator và kiểm tra đầu cuối.

## 35. Azure CLI: inspect hub, routes và endpoints

Các lệnh minh họa chạy bằng **Azure CLI trong Bash/Azure Cloud Shell**; nếu dùng IoT extension, bảo đảm phiên bản CLI/extension hỗ trợ subcommands đang dùng.

~~~bash
az login
az account list --output table
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<IOT_HUB_RESOURCE_GROUP>"
HUB="<LAB_IOT_HUB_NAME>"

az iot hub show \
  --resource-group "$RG" \
  --name "$HUB" \
  --query "{name:name,location:location,sku:sku.name}" \
  --output json

az iot hub route list \
  --hub-name "$HUB" \
  --output json

az iot hub routing-endpoint list \
  --hub-name "$HUB" \
  --output json
~~~

**Lưu ý:** các lệnh **route/routing-endpoint** phụ thuộc Azure CLI/azure-iot extension và có thể yêu cầu flags hoặc có tên khác theo phiên bản. Kiểm tra:

~~~bash
az extension list --output table
az iot hub route --help
az iot hub routing-endpoint --help
~~~

Các lệnh trên chỉ đọc metadata; CLI không tự có quyền data-plane của Service Bus/Storage hoặc credentials thiết bị. **Không chạy các lệnh liệt kê hub keys/policies vào terminal được log công khai**.

### Không tạo/sửa route chỉ để test cú pháp trên production

Lệnh **az iot hub route create/update/delete** (nếu extension cung cấp) có thể thay đổi đường dữ liệu đang hoạt động. Hãy:

1. Xem hiện trạng và lưu cấu hình từ management API.
2. Soạn route spec trong IaC đã review.
3. Dùng môi trường lab hoặc tính năng test query được hỗ trợ.
4. Có owner xác nhận và monitoring trước khi apply.

## 36. Infrastructure as Code và versioned routing

**Routing configuration là một phần của kiến trúc**, nên được quản lý tương tự code:

~~~yaml
# Manifest KHÁI NIỆM - không phải ARM/Bicep/Terraform deployable.
iotHub: iothub-factory-prod
messageRouting:
  endpoints:
    - name: eh-telemetry
      type: eventHubs
      target: <APPROVED_EVENT_HUB_RESOURCE>
    - name: sb-alerts
      type: serviceBusQueue
      target: <APPROVED_QUEUE_RESOURCE>
    - name: blob-archive
      type: storageContainer
      target: <APPROVED_STORAGE_CONTAINER>
  routes:
    - name: all-telemetry
      source: DeviceMessages
      condition: "true"
      endpoint: eh-telemetry
      enabled: true
    - name: hot-reading
      source: DeviceMessages
      condition: "$body.temperatureC > 80"
      endpoint: sb-alerts
      enabled: true
    - name: raw-archive
      source: DeviceMessages
      condition: "true"
      endpoint: blob-archive
      enabled: true
  fallback:
    enabled: true
~~~

**Không chạy YAML trên như lệnh Azure**. Đối chiếu Bicep/ARM resource schema (Microsoft.Devices/IotHubs routing routes/endpoints) hoặc Terraform AzureRM provider phù hợp để viết thực thi đúng schema/version, managed identity và endpoint-specific properties.

### Workflow triển khai

~~~mermaid
flowchart TD
    A[Commit route spec + tests] --> B[Static validation + approval]
    B --> C[Deploy lab hub/endpoints]
    C --> D[Send synthetic telemetry]
    D --> E[Test matching + nonmatching]
    E --> F[Test destination + Java consumer]
    F --> G[Check metrics and cost]
    G --> H{Production approval?}
    H -- No --> I[Stop / fix]
    H -- Yes --> J[Apply approved change]
    J --> K[Monitor routing deliveries]
    K --> L{Errors or regressions?}
    L -- Yes --> M[Rollback previous route spec]
    L -- No --> N[Record change evidence]
~~~

### Drift và conflicts

Nếu một admin chỉnh route trên Portal rồi pipeline áp IaC cũ, thay đổi thủ công có thể bị ghi đè. Quy định rõ **source of truth**, review IAM và quy trình emergency changes; trước rollout cần kiểm tra route diff, điều kiện và tác động.

## 37. Giám sát IoT Hub routing và downstream health

Một dashboard hiệu quả phải liên kết ít nhất ba lớp:

| Lớp | Tín hiệu | Câu hỏi |
|---|---|---|
| **Device → IoT Hub** | D2C ingress, errors, connections, authentication failures | Thiết bị có gửi được không? |
| **Routing** | Matched/unmatched messages, routing deliveries, endpoint delivery errors | Route có chọn đúng và gửi đi không? |
| **Endpoint** | Event Hubs incoming/throughput, Service Bus active/DLQ, Storage blobs, Cosmos RU | Đích có nhận được không? |
| **Processor** | Java Function invocation, retries, failures, checkpoint lag | Consumer có xử lý được không? |
| **Business sink** | Stored rows, alerts, dashboard latency | Kết quả nghiệp vụ đã xảy ra chưa? |
| **Capacity** | Throttled requests, peak/sustained rates, queue depth | Nút nghẽn nằm ở đâu? |
| **Cost** | IoT Hub units, downstream charges, storage/lifecycle, logs | Luồng có vượt ngân sách không? |

Azure Monitor **Metrics, Diagnostic settings, Log Analytics, Application Insights** có thể cung cấp các nguồn quan sát theo resource/tier/tính năng. **Tên metric chính xác thay đổi theo sản phẩm**, cần kiểm tra danh sách metric definitions hiện tại thay vì giả định mọi tên ở bảng đã được xuất tự động.

### Correlation ID

Một event có thể được truy qua:

~~~text
Device identity / eventId
      |
      +-- IoT Hub enqueued time / diagnostic ID
      |
      +-- Route name / destination
      |
      +-- Event Hubs partition+offset OR Service Bus message ID
      |
      +-- Java Function/worker invocation ID
      |
      +-- DB row / alert ID
~~~

Không ghi device connection strings, SAS tokens, raw confidential payload hoặc tất cả vị trí người dùng vào logs. Với số lượng thiết bị lớn, dùng **sampling/counters**, giữ correlation metadata cần thiết và có retention policy.

### Cảnh báo có hành động

- D2C ingress giảm bất thường theo site so với baseline.
- Route delivery failures tăng hoặc endpoint unhealthy.
- Service Bus queue backlog/oldest message age vượt SLO.
- Event Hubs consumer lag tăng qua nhiều intervals.
- Consumer exception rate hoặc DLQ tăng.
- Storage archive không có blob trong thời gian expected.
- IoT Hub throttling tăng khi peak fleet hoạt động.

**Một metric 0 delivery có thể đúng** nếu filter của route không khớp message nào. Alert logic cần biết expected traffic, không coi mọi route im lặng là outage.

## 38. Capacity planning: telemetry, ingress và fan-out

Giả định **8.000 thiết bị**, mỗi thiết bị gửi **1 message/10 giây**, kích thước payload 700 bytes:

~~~text
Incoming message rate:
  8.000 / 10 = 800 messages/giây

Trong 1 giờ:
  800 × 3.600 = 2.880.000 messages

Payload bytes/giây (chưa tính protocol overhead):
  800 × 700 = 560.000 bytes/giây
~~~

Đây là **toán minh họa**, không phải số IoT Hub có thể phục vụ miễn phí. IoT Hub message accounting có thể phụ thuộc **message size chunks, tier/units, operations và quotas**; các downstream endpoints có billing rules riêng.

### Fan-out làm tăng lưu lượng downstream

Nếu tất cả telemetry khớp:

~~~text
Route A -> Event Hubs:         800 events/giây
Route B -> Storage archive:    800 events/giây (có thể batch)

5% messages vượt ngưỡng:
Route C -> Service Bus alerts: 40 messages/giây
~~~

Số events/rate này chỉ là giả định độc lập, không tính duplicate/retry/system overhead. Với 1.000 nhà máy, thiết kế phải xem limits ở **IoT Hub ingress, routing endpoints, Event Hubs throughput/partitions, Storage writes, Service Bus queue, Functions/Java consumers và database**.

### Peak và downtime

- Thiết bị mất mạng 30 phút có thể đồng loạt replay backlog khi kết nối lại.
- Thêm firmware version có thể tăng message size 3 lần.
- Sự cố endpoint làm queue lag; khi phục hồi có replay/burst.
- Một firmware bug gửi mỗi 100 ms thay vì 10 giây có thể phá dự toán.

Đặt **rate limiting/device policy** và có capacity headroom. Không định cỡ chỉ dựa trên traffic trung bình của một ngày yên tĩnh.

## 39. Cost Management cho tuyến IoT

| Thành phần | Các yếu tố chi phí |
|---|---|
| **Azure IoT Hub** | Tier, units, số message/operations theo quy tắc service |
| **Custom Event Hubs** | Throughput/capacity, retention, partitions, capture nếu dùng |
| **Service Bus** | Tier, messaging operations, topics/subscriptions |
| **Storage** | Blob capacity, transactions, redundancy, lifecycle, egress |
| **Cosmos DB** | RU/s hoặc serverless usage, data/index storage |
| **Functions/AKS/App Service** | Execution count, CPU/memory, nodes/plans |
| **Stream Analytics** | Streaming units/compute theo cấu hình |
| **Network** | Inter-region egress, Private Link, VNet resolver, NAT |
| **Monitoring** | Log ingestion, retention, alerts, traces |
| **Security** | Key Vault operations, identity/credential management |

### Cách ước tính hợp lý

1. Xác định số device, send frequency, peak, payload-size distribution.
2. Tính số messages/operations có tính phí theo **IoT Hub SKU** thực tế.
3. Phân tích route matching rate tới từng endpoint.
4. Cộng mức ghi/đọc, retention và số consumers của endpoints.
5. Cộng compute Java/Functions, database writes, storage và network.
6. Tính chi phí observability/logs, đặc biệt nếu log mọi telemetry body.
7. Thêm headroom cho peak/backlog, rồi đối chiếu Azure Pricing Calculator.

**Bật route mới tới Storage hoặc Cosmos DB có thể phát sinh chi phí ngay**; budget alert không tự ngừng mọi tài nguyên. Gắn tags owner/environment/costCenter và có kế hoạch cleanup sandbox sau lab.

## 40. Bảng chẩn đoán routing và telemetry

| Triệu chứng | Nguyên nhân khả dĩ | Cần kiểm tra |
|---|---|---|
| Device send thất bại | Credential hết hạn/sai, device disabled, network/TLS | Device identity, callback status, IoT Hub ingress, firewall |
| Hub nhận message nhưng route không khớp | Query sai, route disabled, sai source | Routing rules, điều kiện trên sample thực |
| Route theo body không khớp | Thiếu contentType/contentEncoding, JSON sai, type mismatch | Body và system headers trong device SDK |
| Route theo application property không khớp | Property name/case/value sai | Metadata thực gửi, không chỉ JSON body |
| Built-in endpoint không nhận dữ liệu như trước | Thay routes/fallback/default behavior | Built-in route và fallback status |
| Storage archive xuất hiện trễ | Batch/file publishing behavior | Endpoint batch config, storage metrics và blobs |
| Event Hubs có messages nhưng Java không đọc | Sai hub name/namespace/consumer group/permission | Event Hubs-compatible metadata, consumer offset/checkpoint |
| Service Bus queue backlog tăng | Worker chậm, DB lỗi, max concurrency không đủ | Oldest message age, DLQ, worker failures |
| Alerts gửi trùng | At-least-once retries/duplicate device messages | eventId, sequence, dedup/cooldown |
| Sensor khác tenant bị ghi sai vào DB | Trust device-supplied tenant/site | System device identity, asset registry mapping |
| Route delivery lỗi 401/403 | Hub managed identity/SAS thiếu quyền | Data-plane RBAC và credential rotation |
| Route delivery timeout/forbidden | Destination firewall/private network không phù hợp | Hub → endpoint network path, endpoint diagnostic |
| Java processor báo JSON parse error | Schema version/type thay đổi, envelope khác | Payload sample, contentType, decoder |
| 429 từ Hub hoặc endpoint | Ingress/quota/throughput hoặc consumer overload | SKU limits, per-resource metrics, peak rate |
| Message quá cũ | Offline replay, event-time drift, backlog | recordedAtUtc, enqueued time, processedAtUtc |
| Cosmos DB RU tăng | Partition hot, index, writes nhiều | RU/partition key, SDK query metrics |
| Stream Analytics window không đúng | Event-time/late arrival policy sai | TIMESTAMP BY, watermark, data types |
| Failover endpoint làm mất event | Retention/route delivery expiration | Archive path, retries, outage duration |

### Phương pháp phân tích theo từng chặng

**Không đổi nhiều thành phần cùng lúc.** Bắt đầu từ:

1. **Ingress:** device gửi được và IoT Hub chấp nhận?
2. **Match:** route condition được kiểm tra trên sample đúng source?
3. **Delivery:** IoT Hub gửi được tới endpoint không?
4. **Consumption:** consumer có quyền, đúng consumer group/subscription và đọc được không?
5. **Commit:** xử lý nghiệp vụ/database thành công không?
6. **Observation:** metrics/alerts phản ánh đúng thời điểm và dữ liệu không?

Nếu alert worker không gửi SMS, việc thử tạo thêm route trong IoT Hub có thể làm trùng dữ liệu mà không sửa được lỗi Service Bus consumer hoặc provider gửi SMS.

## 41. Tình huống A: message JSON có 85°C nhưng route không khớp

**Bối cảnh:** Sensor-A gửi:

~~~json
{"temperatureC": 85, "recordedAtUtc": "2026-11-20T08:20:00Z"}
~~~

Hub có route:

~~~sql
$body.temperatureC > 80
~~~

Thiết bị nhận send acknowledgment nhưng Service Bus queue vẫn không có alerts.

### Nguyên nhân có thể

- Thiết bị không đặt **contentType=application/json** và **contentEncoding=utf-8**.
- Body thực tế là chuỗi JSON bị double-encoded, không phải object.
- Message có thuộc tính **TemperatureC** hoặc **temperatureC** là string.
- Route đang disabled hoặc chọn sai source.
- Route khớp nhưng **Service Bus endpoint delivery thất bại**.
- Consumer đã lấy/complete message trước khi người vận hành nhìn queue count.

### Runbook

1. Dùng device simulator có credential lab, gửi một event mới có eventId riêng.
2. Xác minh device SDK set content properties và body bytes UTF-8.
3. Kiểm thử query matching với JSON/sample trong route testing.
4. Xem endpoint status và routing delivery/error metrics.
5. Kiểm tra Service Bus queue active/dead-letter counts và consumer logs.
6. Nếu route match nhưng queue không nhận, kiểm tra **IoT Hub → Service Bus** RBAC/network.
7. Sửa đúng nguyên nhân, gửi event mới và đối chiếu eventId đầu cuối.

**Không tự động tăng ngưỡng hoặc tạo catch-all route** để làm số message xuất hiện, vì có thể khiến hệ thống cảnh báo sai.

## 42. Tình huống B: thêm route Storage khiến analytics mất telemetry

**Bối cảnh:** Trước đó Java analytics đọc built-in Event Hubs-compatible endpoint. Nhóm triển khai thêm custom route tới Storage, sau đó dashboard không còn cập nhật trong khi blobs vẫn xuất hiện.

### Giả thuyết

Khi cấu hình message routing thay đổi, **default/built-in/fallback behavior** không còn giống trước. Một message khớp Storage route có thể **không được fallback gửi tới built-in endpoint**, khiến Java consumer tiếp tục đọc nhưng không thấy messages mới.

### Hướng điều tra

1. Lưu trạng thái routes/endpoints/fallback hiện tại, kiểm tra Git/IaC diff.
2. Kiểm tra route explicit tới built-in endpoint có còn enabled không.
3. Gửi một telemetry event giả có messageId xác định.
4. Xác minh event tới Storage và built-in endpoint riêng biệt.
5. Nếu yêu cầu là fan-out cả hai, thêm/đảm bảo route tương ứng tới built-in với condition cần thiết.
6. Kiểm tra consumer group/offset/retention để không nhầm "không có route" với "consumer đọc sai offset".
7. Chạy smoke test analytics và ghi lại behavior vào change request.

### Bài học

**Fallback chỉ dành cho message không khớp routes** theo cấu hình, không phải cơ chế tự nhân bản mọi message. Khi thêm một route, cần regression test các consumers hiện có, đặc biệt đường built-in events.

## 43. Tình huống C: endpoint Service Bus từ chối sau khi bật private access

**Bối cảnh:** Route alert từng hoạt động. Đội bảo mật đổi Service Bus namespace sang network restricted và gán managed identity cho IoT Hub. Sau thay đổi, IoT Hub có routing delivery failures, queue không có messages mới.

### Vì sao?

- IoT Hub managed identity chưa được cấp quyền **sender** đúng scope.
- Role assignment mới chưa propagation xong.
- Service Bus network rules không cho phép đường routing theo cơ chế được hỗ trợ.
- Endpoint configuration vẫn dùng credential cũ/connection string sau rotation.
- Hub hoặc endpoint SKU/region không hỗ trợ một cấu hình mong muốn.

### Runbook

1. Xem route endpoint identity mode và authorization configuration.
2. Xác minh managed identity của **đúng IoT Hub** đang active.
3. Kiểm tra data-plane RBAC trên đúng Service Bus entity/namespace.
4. Xác minh network support và firewall trusted-services/private endpoint design.
5. Kiểm thử một event trên sandbox với cấu hình tương tự.
6. Phục hồi cấu hình mạng cũ theo change plan nếu production outage.
7. Kiểm tra retries/retention trong khoảng endpoint lỗi; xác định event nào cần replay từ archive.

**Không cấp Owner/RootManageSharedAccessKey rộng chỉ để xóa lỗi 403.** Xác định quyền send tối thiểu và đường mạng hợp lệ.

## 44. Tình huống D: cảnh báo trùng sau khi Java worker restart

**Bối cảnh:** Java worker lấy từ Service Bus queue, gửi một incident vào hệ thống quản lý bảo trì rồi restart trước khi message được complete. Broker giao lại event và tạo incident thứ hai.

### Nguyên nhân

Service Bus và consumer hoạt động theo cơ chế có thể **redeliver** khi settlement chưa hoàn tất. Routing ở IoT Hub cũng không đảm bảo downstream side effect exactly-once.

### Cách sửa

- Định nghĩa idempotency key từ **Hub/deviceId/eventId** hoặc business event identity đáng tin.
- Lưu unique constraint/upsert cho incident trong database.
- Chỉ complete broker message sau khi business commit đã được xác minh.
- Retry transient errors có giới hạn; invalid schema vào DLQ.
- Nếu worker crash sau DB commit nhưng trước complete, lần chạy lại phải phát hiện incident đã tồn tại.

~~~text
Service Bus eventId=evt-42
    |
    v
Java worker
    |
    +-- INSERT Incident with UNIQUE(eventId)
    +-- If duplicate: treat as already handled
    +-- Commit business transaction
    +-- Complete broker message
~~~

**Chỉ đếm số queue messages không phát hiện được incident nghiệp vụ bị tạo trùng**. Theo dõi cả idempotency conflicts và business records.

## 45. Tình huống E: telemetry đến muộn làm sai dashboard theo phút

**Bối cảnh:** Sensor offline 20 phút, khi mạng phục hồi nó gửi hàng nghìn samples cũ. Dashboard Stream Analytics lấy window theo event time; một số kết quả xuất hiện muộn hoặc bị bỏ tùy late-arrival policy.

### Điều cần làm

1. Xác định **device recordedAtUtc**, **IoT Hub enqueued time** và **processor arrival time**.
2. Xem clock skew của firmware và source time quality.
3. Kiểm tra **TIMESTAMP BY** và late/out-of-order policy của Stream Analytics.
4. Quyết định chấp nhận event muộn bao lâu theo business SLO.
5. Với dữ liệu quá hạn, đưa vào archive/backfill pipeline để đối soát.
6. Gắn dashboard watermark/lastUpdatedAt thay vì giả định số liệu luôn hoàn chỉnh.
7. Tách real-time anomaly alert với historical data correction.

### Bài học

Một route hoạt động đúng vẫn có thể đưa message tới processor **sau thời điểm đo**. **Routing success không bảo đảm event-time window chính xác** nếu thiết bị offline hoặc đồng hồ sai.

## 46. Bài thực hành: định tuyến telemetry trong một IoT Hub sandbox

### Yêu cầu

Thiết kế mô hình **Factory Monitoring** gồm:

- Một **IoT Hub lab** và hai thiết bị giả **sensor-lab-a**, **sensor-lab-b**.
- Event JSON có **schemaVersion, messageId, temperatureC, vibrationMmS, recordedAtUtc**.
- Một custom **Event Hubs endpoint** hoặc built-in endpoint cho analytics.
- Một **Service Bus queue** cho telemetry nhiệt độ >80°C.
- Một **Storage container** cho dữ liệu raw khi có budget/permission.
- Một **Java consumer/Azure Function** đọc stream hoặc queue và xác minh dữ liệu.
- Có test **message khớp, không khớp, sai type, thiếu headers và mất quyền endpoint**.

Không cần tạo đủ mọi dịch vụ nếu sandbox không có ngân sách; bạn vẫn có thể hoàn thành **thiết kế, route matrix, test cases và runbook**. Tuyệt đối không dùng Hub/queue production để gây lỗi thử.

### Phần A: thiết kế ma trận route

| Route | Source | Condition | Destination | Mục đích |
|---|---|---|---|---|
| **all-telemetry** | Device telemetry | true | Event Hubs/built-in | Stream analytics |
| **hot-temperature** | Device telemetry | $body.temperatureC > 80 | Service Bus queue | Alert worker |
| **raw-archive** | Device telemetry | true | Storage | Replay/retention |
| **fallback** | Không khớp custom route | Theo cấu hình Hub | Built-in endpoint | Bảo vệ event không phân loại |

Vì có **all-telemetry** điều kiện true, fallback có thể **không còn nhận device telemetry chưa khớp kiểu khác** do đã khớp ít nhất một route. Đây là điều học viên cần giải thích rõ; fallback không phải bản sao thứ tư cho mọi event.

### Phần B: gửi messages giả lập

Tạo dữ liệu theo bốn case:

~~~json
{"messageId":"lab-001","temperatureC":25,"vibrationMmS":3,"recordedAtUtc":"2026-11-20T10:00:00Z"}
~~~

~~~json
{"messageId":"lab-002","temperatureC":85,"vibrationMmS":12,"recordedAtUtc":"2026-11-20T10:00:10Z"}
~~~

~~~json
{"messageId":"lab-003","temperatureC":"85","vibrationMmS":12,"recordedAtUtc":"2026-11-20T10:00:20Z"}
~~~

~~~json
{"messageId":"lab-004","measurements":{"temperatureC":85},"recordedAtUtc":"2026-11-20T10:00:30Z"}
~~~

Mọi message có thể thêm **messageType=telemetry** ở application properties. Để query body hoạt động, đặt **contentType=application/json**, **contentEncoding=utf-8** theo SDK.

### Phần C: test routing

1. Với **lab-001**, kiểm tra **analytics + archive**, không vào queue nhiệt độ cao.
2. Với **lab-002**, kiểm tra **analytics + archive + alert queue**.
3. Với **lab-003**, kiểm tra kiểu chuỗi không được đánh giá như số theo giả định; ghi kết quả thực của routing query engine, không coi type coercion là contract.
4. Với **lab-004**, query cũ dùng path temperatureC ở root sẽ không thấy nested value; cần schema versioning.
5. Gửi bản giống **lab-002** nhưng thiếu JSON content headers để thấy nguy cơ body condition không được đánh giá.
6. Thử role/permission endpoint bị thiếu **chỉ trong sandbox**; xác nhận metrics/error handling.
7. Kiểm tra Java consumer hoặc Function thực sự xử lý và persist event.
8. Chạy duplicate **lab-002** để test idempotency, không tạo incident hai lần.

### Phần D: đo end-to-end

| Chỉ số | Cách ghi nhận |
|---|---|
| Device send acknowledgment | Callback status và timestamp |
| IoT Hub ingress | Metric/thời gian nhận phù hợp |
| Route matched | Route test hoặc routing metrics/log |
| Endpoint delivery | Message count/ID, errors |
| Processor execution | Invocation ID, retry count |
| Business result | Incident ID hoặc aggregate record |
| End-to-end latency | Processed time trừ ingested/event time theo định nghĩa |
| Duplicate count | Number of idempotency conflicts |
| Cost estimate | Message rate, Hub/endpoint/compute/storage |

Không coi timestamp thiết bị đáng tin tuyệt đối khi tính end-to-end latency; có thể dùng IoT Hub enqueued time cho một phép đo bổ sung.

### Phần E: thử nghiệm fault injection an toàn

Chỉ trong **lab được phép**:

- Tắt Java consumer trong vài phút rồi bật lại; quan sát backlog/retention.
- Cho parser nhận JSON thiếu schemaVersion; kỳ vọng error handling/DLQ.
- Gửi 2 events có cùng eventId; kỳ vọng không có business effect trùng.
- Tạm dùng một endpoint test có IAM cố tình thiếu; xác minh route delivery errors.
- Giả lập thiết bị gửi timestamp trễ; xem Stream Analytics xử lý.

Không tắt firewall, thu hồi role hoặc xóa endpoint production để tạo tình huống lỗi. Nếu một thao tác có thể tác động nhóm khác trong resource dùng chung, thay bằng mock/tabletop exercise.

### Phần F: bằng chứng cần nộp

~~~text
Hub (sandbox): ...
Subscription/resource group/region: ...
Device IDs (không có credential): ...
Route names/source/query/endpoint: ...
Fallback status: ...
JSON schema + message headers: ...
Matching and nonmatching test IDs: ...
Consumer app/SDK version: ...
Message ingress/delivery/process counts: ...
Retry/idempotency result: ...
Monitoring dashboard and alert rules: ...
Cost estimate and cleanup: ...
Secrets in report: NONE
~~~

### Phần G: cleanup

- Chỉ xóa test devices, routes, endpoints hoặc resources **do lab tạo riêng** và được sở hữu.
- Không xóa IoT Hub/resource group dùng chung hoặc route production.
- Thu hồi/rotate lab credentials theo quy trình.
- Dọn blobs/queue messages/test data theo retention được phê duyệt.
- Xác minh tài nguyên vẫn phát sinh phí (Hub, Event Hubs, Storage, Service Bus, Stream Analytics, logs) đã được đóng/dọn khi phù hợp.
- Xác minh tài nguyên vẫn phát sinh phí (Hub, Event Hubs, Storage, Service Bus, Stream Analytics, logs) đã được đóng/dọn khi phù hợp.

## 47. Checklist thiết kế và vận hành production

- [ ] Đã xác định rõ **message source** là D2C telemetry, không nhầm C2D/twin/Edge events.
- [ ] Có route matrix từ use cases: alert, realtime analytics, historical archive.
- [ ] Đã quyết định **built-in vs custom Event Hubs** và consumer group/retention.
- [ ] Đã chọn **Service Bus queue hay topic** theo số consumers và retry/DLQ policy.
- [ ] Storage archive có encoding, file partitioning, retention và khả năng replay rõ.
- [ ] Cosmos DB endpoint/processor có partition key, index, TTL và RU budget nếu dùng.
- [ ] Device SDK đặt contentType=application/json và contentEncoding=utf-8 khi route đọc JSON body.
- [ ] Routing queries đã test cả **matching, nonmatching, missing, null, wrong type**.
- [ ] Route conditions được kiểm tra với schemaVersion và firmware versions thực tế.
- [ ] Route khác cùng khớp không gây double alerts ngoài thiết kế.
- [ ] Fallback route và đường built-in events được regression test sau mỗi thay đổi.
- [ ] Không dùng **device-supplied tenantId/site** làm bằng chứng authorization.
- [ ] Device-level identity/certificate/SAS được bảo vệ, không dùng owner key trên firmware.
- [ ] Hub → custom endpoint có managed identity/credential và data-plane RBAC tối thiểu.
- [ ] Java consumer có identity/permission riêng, không dùng quyền gửi của IoT Hub.
- [ ] Network và private connectivity được kiểm chứng riêng từng hop.
- [ ] Có eventId/sequence, deduplication và business idempotency.
- [ ] Java Functions/worker xử lý retry, checkpoint/settlement, DLQ và graceful shutdown.
- [ ] Đã quy định event time vs enqueue time và late/out-of-order policy.
- [ ] Có monitoring từ device ingress tới routing delivery và business sink.
- [ ] Alert rules có owner, runbook và tránh false positives khi route ít traffic.
- [ ] Có archive/replay và kiểm thử khôi phục trong thời hạn retention.
- [ ] Có IaC/source-of-truth, change review, rollback và môi trường staging.
- [ ] Capacity plan tính peak/offline replay và message size, không chỉ average.
- [ ] Có tags/budget, ước lượng toàn pipeline và kế hoạch dọn resources lab.
- [ ] Không có credentials, raw PII hay private payloads trong Git hoặc logs.

## 48. Câu hỏi tự kiểm tra

1. IoT Hub D2C telemetry khác cloud-to-device và device twins ở điểm nào?
2. Một IoT Hub route gồm những trường thông tin cơ bản nào?
3. Vì sao IoT Hub routing không thể tự tính AVG theo phút?
4. Khi nào dùng built-in Event Hubs-compatible endpoint thay custom Event Hubs?
5. Nếu hai routes cùng khớp một telemetry message, điều gì có thể xảy ra?
6. Fallback route dùng khi nào? Có phải dead-letter queue không?
7. Vì sao thêm route tới Storage có thể ảnh hưởng consumer built-in endpoint?
8. Điều kiện lọc theo application property và JSON body khác nhau ra sao?
9. Muốn dùng $body.temperatureC, thiết bị cần đặt contentType và contentEncoding thế nào?
10. Nếu temperatureC là chuỗi nhưng query so sánh số, cần kiểm tra điều gì?
11. Có thể tin tenantId do thiết bị tự ghi trong body để phân quyền không?
12. IoT Hub system property về device connection identity có ích gì?
13. Khi nào chọn Service Bus queue thay vì Event Hubs?
14. Service Bus topic phù hợp với bài toán nhiều subscribers ra sao?
15. Vì sao message trong Event Hubs không tự biến mất khi consumer đọc?
16. Consumer group và checkpoint giải quyết điều gì?
17. Vì sao Storage route không phù hợp alert cần phản hồi vài giây?
18. Nếu muốn lưu telemetry vào Cosmos DB, những quyết định phân vùng/index nào quan trọng?
19. Tại sao cần Function/Java processor trước Cosmos DB trong một số use cases?
20. Event Grid subscriptions và IoT Hub custom routing endpoints có phải một danh sách giống nhau không?
21. IoT Edge xử lý offline khác IoT Hub cloud routing ở điểm nào?
22. Tại sao send acknowledgment không chứng minh dữ liệu đã được ghi vào database?
23. Trường nào có thể dùng để dedup một reading khi worker retry?
24. Khi processor crash sau DB commit nhưng trước broker complete, tránh incident trùng bằng cách nào?
25. Event time, enqueued time và processing time khác nhau thế nào?
26. Nếu route delivery 403, cần kiểm tra role và network của ai?
27. IoT Hub managed identity và Java consumer managed identity có cần là cùng principal không?
28. Private Endpoint của consumer có tự mở đường IoT Hub gửi vào Service Bus không?
29. Vì sao 429 vẫn xảy ra dù Hub được cấp thêm units nếu database đang là bottleneck?
30. Poison/invalid message nên vào DLQ khi nào, và ai chịu trách nhiệm?
31. Archive giúp gì khi Event Hubs retention đã hết?
32. Những điểm nào cần kiểm thử trước khi đổi từ JSON v1 sang v2?
33. Vì sao route điều kiện true và fallback có tương tác đặc biệt?
34. Có thể dùng IoT Hub message routing để gửi lệnh tắt máy trực tiếp theo temperature threshold không?
35. Những chỉ số nào chứng minh một telemetry đã đi từ sensor tới cảnh báo nghiệp vụ?
36. Một nhà máy có hàng nghìn thiết bị đồng loạt replay backlog sẽ ảnh hưởng capacity ra sao?
37. Một deployment IaC đổi route condition cần có các bước review/rollback nào?
38. Tại sao không nên log device connection strings hoặc toàn bộ dữ liệu vị trí?
39. Khi nào cần tạo alert theo event time và khi nào theo enqueue time?
40. Với ba yêu cầu alert, analytics và lưu trữ, bạn chọn những endpoints nào và vì sao?

## 49. Tài liệu tham khảo

- [Azure IoT Hub documentation](https://learn.microsoft.com/azure/iot-hub/) — tổng quan IoT Hub, device management, messages và routing.
- [IoT Hub device-to-cloud communication guidance](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-messages-d2c) — D2C messages và luồng cloud.
- [IoT Hub message routing](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-messages-d2c#message-routing) — messages đến endpoints, routing/fallback concepts.
- [IoT Hub message routing query syntax](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-routing-query-syntax) — source, body/properties và query conditions.
- [IoT Hub message enrichments](https://learn.microsoft.com/azure/iot-hub/iot-hub-message-enrichments-overview) — gắn metadata vào routed messages.
- [IoT Hub quotas and throttling](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-quotas-throttling) — service limits và capacity.
- [Monitor Azure IoT Hub](https://learn.microsoft.com/azure/iot-hub/monitor-iot-hub) — Azure Monitor metrics/diagnostics.
- [Azure Event Hubs overview](https://learn.microsoft.com/azure/event-hubs/event-hubs-about) — partitioned streaming/event ingestion.
- [Azure Service Bus overview](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview) — queues/topics và durable messaging.
- [Azure Storage Blob overview](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-overview) — archive/retention/data lake.
- [Azure Cosmos DB for NoSQL overview](https://learn.microsoft.com/azure/cosmos-db/nosql/overview) — NoSQL destination, partitions, RU.
- [Azure Functions Event Hubs trigger](https://learn.microsoft.com/azure/azure-functions/functions-bindings-event-hubs-trigger) — functions xử lý events.
- [Azure Functions Service Bus trigger](https://learn.microsoft.com/azure/azure-functions/functions-bindings-service-bus-trigger) — message processor với queue/topic.
- [Azure Stream Analytics overview](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-introduction) — event-time windows, transformations và sinks.
- [Azure Event Grid overview](https://learn.microsoft.com/azure/event-grid/overview) — mô hình event subscription.
- [Azure IoT Edge documentation](https://learn.microsoft.com/azure/iot-edge/) — xử lý ở edge và kết nối cloud.
- [Azure IoT SDKs](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-sdks) — device và service SDK, phiên bản.
- [Azure CLI IoT Hub reference](https://learn.microsoft.com/cli/azure/iot/hub) — xem Hub metadata, route commands/extension.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — ước lượng IoT Hub và downstream services.

**Kết luận:** Định tuyến telemetry từ Azure IoT Hub là một bước thiết kế hạ tầng dữ liệu IoT, không chỉ là điền một điều kiện lọc. Hãy xác định rõ **nguồn message, metadata và schema, route condition, built-in/custom endpoints, fallback behavior và consumer ownership**. Dùng **Event Hubs** cho streaming, **Service Bus** cho công việc và alerts cần retry/DLQ, **Storage** để archive/replay và **Cosmos DB** cho truy vấn trạng thái khi phù hợp. Đảm bảo **identity và quyền từng chặng, JSON headers, idempotency, xử lý dữ liệu muộn, monitoring, kiểm thử và chi phí** trước khi đưa production. Một pipeline đáng tin là pipeline mà bạn có thể giải thích **message đã được tiếp nhận, được định tuyến, được xử lý và được ghi nhận ở đâu**, kể cả khi một endpoint gặp sự cố.
