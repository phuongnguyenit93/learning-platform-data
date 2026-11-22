# Phân biệt event routing và event streaming trên Azure

Khi một khách hàng tải ảnh sản phẩm lên Azure Blob Storage, hệ thống cần biết **một tệp mới đã xuất hiện** để tạo thumbnail. Khi hàng chục nghìn thiết bị liên tục gửi nhiệt độ và trạng thái hoạt động, hệ thống lại cần **thu nhận, lưu giữ và phân tích một chuỗi dữ liệu khổng lồ theo thời gian**. Cả hai đều có thể được gọi là “xử lý sự kiện”, nhưng mục tiêu, mô hình tiêu thụ dữ liệu và dịch vụ Azure phù hợp rất khác nhau.

**Event routing** tập trung phát hiện sự kiện đã xảy ra và **định tuyến thông báo** đến các bên quan tâm. **Event streaming** tập trung **thu nhận và giữ một luồng bản ghi có thứ tự theo partition** để nhiều consumer đọc, phân tích và có thể đọc lại trong thời hạn lưu giữ. Trên Microsoft Azure, hai dịch vụ tiêu biểu cho hai mô hình này là **Azure Event Grid** và **Azure Event Hubs**. Ngoài ra còn có **Azure Service Bus**, thích hợp cho hàng đợi công việc và giao tiếp nghiệp vụ đáng tin cậy.

Bài học thuộc chương **Sự kiện và dữ liệu streaming** của mô-đun **CLOUD_PROVIDERS_AZURE**: khám phá Azure từ subscription, resource group, Microsoft Entra ID và mạng ảo tới tính toán, lưu trữ, dữ liệu; biết cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng.

> **Mục tiêu quan trọng:** Chọn dịch vụ theo hợp đồng nghiệp vụ: cần **thông báo và kích hoạt** một hành động, cần **đọc luồng sự kiện theo thời gian và phát lại**, hay cần **giao việc có xác nhận hoàn thành**. Tên gọi “event” trong một payload không tự quyết định phải dùng Event Grid hay Event Hubs.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích event, event notification, event stream và command/message bằng ví dụ cụ thể.
2. Phân biệt **event routing**, **event streaming** và **enterprise messaging** theo hướng phát/nhận, lưu giữ, replay, ordering và xử lý lỗi.
3. Trình bày cấu trúc cơ bản của **Event Grid topic, event subscription, filter, event handler**.
4. Trình bày **Event Hubs namespace, event hub, partition, partition key, consumer group, offset và checkpoint**.
5. Nhận biết khi nào chọn **Azure Service Bus Queue/Topic**, Azure Queue Storage hoặc Azure Functions làm thành phần bổ trợ.
6. Thiết kế pipeline Blob Storage → Event Grid → xử lý theo sự kiện và telemetry → Event Hubs → stream processor → lưu trữ/phân tích.
7. Giải thích at-least-once, duplicate, thứ tự theo partition, retention, retry, dead-letter và khả năng phát lại.
8. Thiết kế xác thực, RBAC, private networking, quan sát hệ thống và dự toán chi phí cho từng mô hình.

## 1. Event là gì và “event-driven” không đồng nghĩa “streaming”

Một **event** biểu diễn một điều đã xảy ra, thường được diễn đạt ở thì quá khứ:

- **BlobCreated**: một blob mới đã được tạo.
- **OrderPlaced**: đơn hàng đã được đặt.
- **PaymentSucceeded**: thanh toán đã hoàn tất.
- **DeviceTemperatureObserved**: thiết bị vừa ghi nhận nhiệt độ.

Event có thể mang metadata như **event ID**, **event type**, **source**, **time**, **subject/resource reference** và dữ liệu bổ sung. Producer công bố sự kiện mà không nhất thiết biết chính xác consumer sẽ làm gì với nó.

### Phân biệt event notification và event record

**Event notification** thường là tín hiệu ngắn: “đối tượng X thay đổi, hãy xem xét”. Nó có thể chứa URI blob, loại thay đổi và một số metadata. Nội dung của tệp hoặc trạng thái đầy đủ thường vẫn nằm ở hệ thống nguồn.

**Event record trong stream** là một phần của chuỗi dữ liệu mà consumer cần phân tích qua thời gian. Ví dụ cứ mỗi giây một thiết bị ghi nhiệt độ, độ ẩm và trạng thái pin. Consumer muốn tính trung bình theo cửa sổ, phát hiện bất thường và đọc lại dữ liệu lịch sử trong thời hạn lưu giữ.

### Event và command khác nhau

| Loại | Ví dụ | Ý nghĩa |
|---|---|---|
| **Event** | OrderPlaced | Một sự kiện nghiệp vụ đã xảy ra |
| **Notification** | BlobCreated | Có thay đổi cần thông báo cho người quan tâm |
| **Command/job** | GenerateInvoice | Yêu cầu một worker thực hiện công việc |
| **Stream record** | SensorReading at 14:05:01 | Một mẫu dữ liệu thuộc luồng theo thời gian |

Một hệ thống có thể biến notification thành command: **BlobCreated** được Event Grid chuyển tới một function, function xác thực rồi gửi **GenerateThumbnail** vào Service Bus Queue. Đây không phải hai tên gọi cho cùng một cơ chế.

## 2. So sánh nhanh ba mô hình

| Câu hỏi | Event routing | Event streaming | Enterprise messaging |
|---|---|---|---|
| Mục tiêu | Thông báo và định tuyến sự kiện đến handlers | Thu nhận và phân phối luồng bản ghi liên tục | Chuyển giao công việc/thông điệp có trạng thái xử lý |
| Dịch vụ Azure tiêu biểu | **Azure Event Grid** | **Azure Event Hubs** | **Azure Service Bus** |
| Phía nhận thường làm gì? | Chạy handler khi có notification | Chủ động đọc từ partition và lưu checkpoint | Receive message rồi Complete/Abandon/Dead-letter |
| Hướng giao | Thường push tới destination; Event Grid Namespaces có thêm mô hình pull phù hợp | Consumer pull/receive stream từ broker | Receiver chủ động receive từ queue/subscription |
| Lưu giữ/replay | Retry/dead-letter theo cấu hình; không coi push notification là event log phát lại tùy ý | Retention theo tier/cấu hình; consumer có thể đọc lại trong cửa sổ còn giữ | Message chờ tới khi settlement/expiry theo cơ chế entity |
| Ordering | Không nên giả định toàn bộ notification tới đúng thứ tự | Thứ tự trong **một partition**, không bảo đảm thứ tự toàn event hub | Có các cơ chế như sessions khi cần tổ chức nhóm và thứ tự |
| Nhiều consumer độc lập | Nhiều event subscriptions/handlers | Nhiều consumer groups với vị trí đọc riêng | Topic có nhiều subscriptions, queue cho competing consumers |
| Đơn vị quan sát tải | Số event được publish/matched/delivered/failed | Throughput, partitions, offset/checkpoint/consumer lag | Active messages, locks, dead-letter, delivery count |
| Dùng tốt cho | Blob-created, resource change, webhook trigger | Telemetry, clickstream, log, IoT stream, phân tích thời gian thực | Thanh toán, công việc nền, workflow, giao việc cần settlement |

**Đây là so sánh định hướng, không phải tuyên bố mọi phiên bản của dịch vụ đều có cùng một chế độ.** Event Grid có cả các khả năng Namespaces, MQTT và pull delivery theo tính năng được hỗ trợ. Event Hubs có tích hợp Kafka, Capture và nhiều loại capacity/tier. Cần kiểm tra yêu cầu hiện hành trước khi quyết định.

## 3. Event routing: “Điều gì đã xảy ra, ai cần được báo?”

Giả sử người dùng vừa upload một ảnh vào Blob Storage. Hệ thống cần kích hoạt tạo thumbnail, kiểm tra an toàn và ghi audit.

~~~text
Azure Blob Storage
    |
    | BlobCreated event
    v
Azure Event Grid
    |
    +-- Event subscription A -> Azure Function tạo thumbnail
    |
    +-- Event subscription B -> Handler kiểm tra nội dung
    |
    +-- Event subscription C -> Endpoint audit
~~~

Điểm đáng chú ý:

1. **Nguồn sự kiện** phát thông tin rằng một hành động đã xảy ra.
2. **Event Grid** tiếp nhận sự kiện và áp quy tắc định tuyến/lọc.
3. **Event subscription** định nghĩa nhóm sự kiện cần nhận và đích xử lý.
4. **Handler** thực hiện logic, có thể truy vấn dữ liệu gốc theo reference.
5. Nếu handler không phản hồi đúng hoặc delivery gặp lỗi, Event Grid có cơ chế retry/dead-letter theo loại đích và chính sách áp dụng.

Không có bước nào trong sơ đồ yêu cầu Event Grid tự tải toàn bộ ảnh hoặc thực hiện OCR. Nó chỉ **chuyển tín hiệu đến đúng nơi**.

### Đặc điểm của routing

- Các event subscription giúp **fan-out** một sự kiện đến nhiều handler.
- Filtering giúp giảm event không liên quan.
- Thông báo thường nhỏ hơn dữ liệu nguồn, giúp giảm coupling giữa producer và consumer.
- Đích nhận phải có cơ chế **idempotency** vì delivery có thể lặp.
- Không giả định thứ tự delivery giữa những notification.
- Không coi routing có retry là kho lưu lịch sử sự kiện vô hạn.

## 4. Những khái niệm chính của Azure Event Grid

| Khái niệm | Giải thích |
|---|---|
| **Event source** | Tài nguyên hoặc ứng dụng phát event, ví dụ Blob Storage |
| **System topic** | Đại diện cho luồng sự kiện từ dịch vụ Azure được hỗ trợ |
| **Custom topic** | Nơi ứng dụng riêng xuất bản sự kiện tùy chỉnh |
| **Event Grid Namespace** | Mô hình tài nguyên có các tính năng như namespace topics, push/pull delivery hoặc MQTT theo hỗ trợ |
| **Event subscription** | Bộ lọc, chính sách giao và handler/destination cho một nguồn |
| **Event handler** | Azure Functions, webhook, Event Hubs, Service Bus hoặc đích khác được hỗ trợ |
| **Filtering** | Lọc event type, subject và những thuộc tính khác theo khả năng |
| **Retry policy** | Cách dịch vụ thử giao lại trong giới hạn cấu hình |
| **Dead-letter destination** | Đích lưu thông báo không giao thành công sau các điều kiện retry nếu được cấu hình |

### System topic và custom topic

**System topic** phù hợp khi nguồn là một dịch vụ Azure phát sự kiện, chẳng hạn Blob Storage. Một ứng dụng tự phát sự kiện nghiệp vụ có thể dùng **custom topic** hoặc mô hình namespace topic được hỗ trợ.

Ví dụ **OrderPlaced** là sự kiện do domain của ứng dụng tạo; không nhất thiết là event type hệ thống của Azure. Ngược lại, **BlobCreated** là sự kiện thuộc hệ sinh thái Storage với schema và điều kiện phát theo dịch vụ.

### Event Grid push và pull

Trong mô hình Event Grid push truyền thống, Event Grid chủ động gửi event tới handler. Đích như HTTP webhook cần xử lý yêu cầu, xác thực và phản hồi phù hợp.

**Event Grid Namespaces** còn cung cấp những khả năng pull delivery/queue-like cho consumer theo cấu hình hỗ trợ. Do đó câu “Event Grid luôn push” là quá tuyệt đối. Khi so sánh trong bài này, **event routing** tập trung vào cách định tuyến notification, còn **streaming** tập trung vào log phân vùng và vị trí đọc độc lập của consumer.

## 5. Event Grid schema và CloudEvents

Event Grid hỗ trợ các schema sự kiện theo loại nguồn/đích, trong đó có **CloudEvents**. Một CloudEvent có thể mang:

- **specversion**: phiên bản đặc tả CloudEvents.
- **id**: định danh event do nguồn cung cấp.
- **source**: nguồn phát.
- **type**: loại sự kiện.
- **subject**: đối tượng liên quan, khi có.
- **time**: thời gian sự kiện.
- **datacontenttype**: định dạng nội dung.
- **data**: dữ liệu nghiệp vụ/metadata.

Ví dụ **CloudEvents JSON tùy chỉnh** cho một ứng dụng quản lý đơn hàng:

~~~json
{
  "specversion": "1.0",
  "id": "evt-order-00042",
  "source": "/sales/orders",
  "type": "com.example.sales.order.placed.v1",
  "subject": "/orders/ORD-00042",
  "time": "2026-11-20T08:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "ORD-00042",
    "tenantId": "tenant-demo",
    "schemaVersion": 1
  }
}
~~~

Đây là **sự kiện mẫu do ứng dụng giả định phát**, không phải schema chính thức của Azure Storage hay một event đã tồn tại. Payload cố ý không chứa mật khẩu, access token hay thông tin thanh toán nhạy cảm.

### Event Grid schema có thể khác CloudEvents

Một sự kiện sử dụng Event Grid schema có các trường như **id**, **eventType**, **subject**, **eventTime**, **data**, **dataVersion** và **topic** theo loại event. Không thể thay tùy ý **eventType** bằng **type** trong cùng một payload rồi cho rằng cả hai schema tương đương.

Chọn schema phù hợp với nguồn và handler. Producer/consumer phải thống nhất hợp đồng, version, content type và những trường bắt buộc.

### Chỉ truyền tham chiếu khi dữ liệu lớn

Khi upload video 200 MB, event nên mang **Blob URI hoặc định danh tài nguyên** cùng metadata cần thiết, không nhúng bytes video trong thông báo. Handler dùng danh tính và quyền phù hợp để tải dữ liệu từ Blob Storage.

Để tránh race khi tên blob bị overwrite, cân nhắc ETag hoặc versionId được nguồn cung cấp theo loại sự kiện, rồi kiểm tra bản dữ liệu thực sự cần xử lý. Event không mặc định bảo đảm đối tượng còn nguyên nếu dữ liệu nguồn thay đổi sau lúc phát event.

## 6. Event Grid filtering: chỉ gửi event cần thiết

Một sự kiện có thể không liên quan tới mọi handler. Ví dụ container có file ảnh, log và PDF nhưng thumbnail worker chỉ xử lý ảnh.

Event Grid có những cách lọc như:

- **Event type filter**: chỉ chọn loại như BlobCreated.
- **Subject begins with/ends with**: lọc đường dẫn hoặc phần mở rộng theo chủ đề sự kiện.
- **Advanced filtering**: lọc một số thuộc tính event theo operator được hỗ trợ.

~~~text
BlobCreated events:
  images/product-01.jpg
  images/product-02.png
  reports/report.pdf

Event subscription tạo thumbnail:
  event type = BlobCreated
  subject prefix = .../images/
  subject suffix = .jpg hoặc rule phù hợp cho .png
~~~

Một filter chỉ chọn **.jpg** sẽ không tự bao gồm **.png**; có thể cần nhiều điều kiện/subscription tùy biểu thức filter hỗ trợ. Không giả định glob pattern hoặc logic AND/OR là giống nhau giữa mọi cấp lọc.

### Filter không thay thế xác thực và kiểm tra nội dung

Tên file **photo.jpg** vẫn có thể chứa dữ liệu không phải JPEG. Handler cần xác minh magic bytes, kích thước, content type đáng tin cậy và quyền truy cập. Filter giúp định tuyến, không là lớp kiểm tra malware hoặc kiểm soát ủy quyền.

## 7. Retry, dead-letter và ordering trong routing

Trong Event Grid, delivery có thể gặp lỗi khi handler timeout, không đáp ứng hoặc trả mã lỗi. Tùy loại endpoint, error code và delivery policy, dịch vụ có thể **retry trong giới hạn** hoặc xử lý theo logic kết thúc giao. Có thể cấu hình **dead-letter destination** trong những trường hợp được hỗ trợ để giữ lại event không giao thành công.

~~~text
BlobCreated
    |
    v
Event Grid subscription
    |
    +--> Giao lần đầu --> HTTP endpoint lỗi
    |
    +--> Retry theo policy (nếu lỗi được retry)
    |
    +--> Không giao được trong điều kiện cuối
                  |
                  +--> Dead-letter destination đã cấu hình
                  +--> Nếu chưa có, nguy cơ mất notification cần xử lý
~~~

**Điều cần nhớ:** Retry không đồng nghĩa exactly-once. Handler có thể đã ghi kết quả nhưng response đến Event Grid bị mất; Event Grid có thể giao lại cùng event.

Ví dụ:

~~~text
Event Grid gửi evt-123 -> Function
Function tạo thumbnail thành công
Function response timeout
Event Grid giao lại evt-123

Nếu Function không idempotent:
  tạo kết quả trùng hoặc ghi đè không mong muốn.
~~~

### Không giả định thứ tự global

BlobCreated A rồi BlobDeleted A không bảo đảm consumer luôn nhìn thấy đúng thứ tự khi dùng event routing. Handler phải chấp nhận notification đến muộn, bị trùng, sai thứ tự hoặc dữ liệu nguồn không còn tồn tại.

**Event Grid push retry không thay thế event log có thể seek lại tùy ý.** Nếu cần phát lại lịch sử dài ngày hoặc tính tổng hợp nhiều giờ, cần kiến trúc lưu sự kiện chuyên biệt như Event Hubs kết hợp Capture, storage hay event store khác.

## 8. Event streaming: “Cả chuỗi dữ liệu biến đổi ra sao?”

Trong streaming, producer gửi **một luồng bản ghi liên tục**, consumer đọc và xử lý theo vị trí của mình. Ví dụ:

~~~text
10.000 thiết bị / ứng dụng
   |       |       |
   +-------+-------+
           |
           v
       Azure Event Hubs
    +----------------------+
    | Partition 0: events  |
    | Partition 1: events  |
    | Partition 2: events  |
    | Partition N: events  |
    +----------------------+
       |              |
       v              v
 Consumer Group A   Consumer Group B
 Realtime alerts    Analytics & ETL
       |              |
       v              v
 Azure Functions/    Stream Analytics/
 custom processor    Spark/Fabric etc.
       |              |
       v              v
  Incident API       Lake/warehouse
~~~

**Event Hubs** là dịch vụ tiếp nhận sự kiện/thông điệp với thông lượng lớn, cho phép consumer đọc dữ liệu theo partition và lưu tiến độ. Khác với Service Bus Queue, một event trong Event Hubs **không bị xóa chỉ vì một consumer đã xử lý xong**.

### Các đặc trưng của streaming

- Dữ liệu được **append** vào những partitions.
- Consumer **đọc theo offset/vị trí** và tiến độ riêng.
- Nhiều consumer groups có thể phân tích cùng dữ liệu độc lập.
- Có thể **replay** trong giới hạn retention còn hiệu lực.
- Thứ tự có ý nghĩa **trong mỗi partition**, không mặc định có thứ tự toàn hub.
- Có thể tích hợp với Kafka clients và hệ thống stream processing trong phạm vi hỗ trợ.

## 9. Những khái niệm chính của Azure Event Hubs

| Khái niệm | Vai trò |
|---|---|
| **Event Hubs namespace** | Ranh giới quản lý các event hubs, network/authorization và capacity |
| **Event hub** | Stream log có partitions và retention |
| **Partition** | Đơn vị phân chia dữ liệu để tăng thông lượng và đọc song song |
| **Partition key** | Giá trị dùng để hướng event liên quan vào cùng partition theo cơ chế phân phối |
| **Offset** | Vị trí bản ghi trong một partition |
| **Sequence number** | Thứ tự tăng trong phạm vi partition theo broker |
| **Consumer group** | Góc nhìn tiêu thụ độc lập trên cùng event hub |
| **Event processor** | Consumer phối hợp đọc partitions, xử lý và theo dõi tiến độ |
| **Checkpoint** | Điểm đã xử lý bền vững, giúp tiếp tục sau restart |
| **Retention** | Khoảng thời gian dữ liệu còn được giữ để consumer đọc/replay |
| **Capture** | Tính năng ghi dữ liệu từ Event Hubs sang Storage/Data Lake theo hỗ trợ |

### Event hub khác với Queue

Trong queue, consumer nhận message rồi **Complete** để broker biết công việc đã được xử lý. Trong Event Hubs, consumer đọc bản ghi và **lưu checkpoint** theo cơ chế client/processor; event vẫn có thể tồn tại cho tới khi hết retention, nên một consumer group khác vẫn có thể đọc.

Không gọi **CompleteMessage** trên Event Hubs như với Service Bus Peek-Lock. Cũng không dùng Event Hubs như hàng đợi đảm bảo “một đơn hàng được giao cho một worker đúng một lần” mà không thiết kế idempotency/consumer state.

## 10. Partitions, parallelism và ordering

Giả sử Event Hubs có bốn partitions:

~~~text
Partition 0: A1 -> A2 -> A3 -> A4
Partition 1: B1 -> B2 -> B3
Partition 2: C1 -> C2
Partition 3: D1 -> D2 -> D3 -> D4
~~~

Trong **một partition**, broker duy trì thứ tự bản ghi để consumer đọc theo vị trí. Giữa Partition 0 và Partition 1 **không có thứ tự toàn cục** được đảm bảo.

### Partition key

Với telemetry, có thể dùng **deviceId** làm partition key để các bản ghi của một thiết bị được gửi vào cùng partition theo thuật toán phân phối của producer/broker.

~~~json
{
  "deviceId": "sensor-23",
  "temperature": 31.7,
  "recordedAt": "2026-11-20T08:01:20Z"
}
~~~

Những bản ghi gửi tuần tự cho **sensor-23** có thể được nhóm vào cùng partition, hỗ trợ xử lý theo thứ tự **trong partition**. Nhưng producer gửi đồng thời không được đồng bộ có thể làm logic nghiệp vụ phức tạp; cần sequence/timestamp ở tầng ứng dụng nếu phải phát hiện mẫu thiếu, trùng hoặc đến muộn.

### Partition count ảnh hưởng gì?

Số partition ảnh hưởng mức độ chia song song. Tuy nhiên:

- Không phải tăng số partition sẽ tăng throughput vô hạn; còn giới hạn capacity units, CPU/network và backend.
- Quá ít partitions có thể hạn chế parallelism.
- Quá nhiều partitions làm tăng state/checkpoint và chi phí quản trị ở consumer.
- Việc thay đổi partition count có khả năng bị giới hạn theo tier/tính năng; **khi tăng partitions, mapping partition key có thể thay đổi**, ảnh hưởng giả định về thứ tự dài hạn theo key.

Chọn partition count theo peak volume, số consumer đồng thời, tốc độ xử lý và khả năng thay đổi trong tương lai.

## 11. Consumer groups và checkpoint

**Consumer group** là một tập consumer chia sẻ góc nhìn tiến độ đọc trên một event hub. Ví dụ:

~~~text
Event Hub: device-telemetry
              |
     +--------+---------+
     |                  |
     v                  v
Consumer Group       Consumer Group
realtime-alerts      offline-analytics
     |                  |
     v                  v
P0-P3 processors     P0-P3 processors
     |                  |
     v                  v
Alerting             Data Lake/warehouse
~~~

Hai consumer groups có thể đọc cùng các event mà không cần producer gửi hai lần.

### Checkpoint là tiến độ xử lý

Consumer lưu checkpoint sau khi xử lý an toàn phần dữ liệu tương ứng. Trong một số SDK, checkpoint thường được lưu qua Azure Blob Storage hoặc một checkpoint store được hỗ trợ.

~~~text
Partition 0:
  offset 100 -> xử lý xong
  offset 101 -> xử lý xong
  offset 102 -> xử lý xong
  offset 103 -> đang xử lý

Checkpoint = 102

Consumer restart:
  tiếp tục theo checkpoint, có thể đọc lại một số event
~~~

**Checkpoint không xóa event khỏi Event Hubs.** Nếu consumer ghi checkpoint **trước khi dữ liệu được commit bền vững**, restart có thể bỏ qua công việc chưa hoàn thành. Nếu commit kết quả xong nhưng checkpoint chưa kịp lưu, event có thể được đọc lại.

Do đó thiết kế streaming đáng tin cậy thường cần **idempotent sink**, xử lý lỗi và checkpoint sau khi kết quả đã được ghi bền vững.

### Các consumer cùng một group

Các processor cùng consumer group có thể **phối hợp sở hữu partitions** nhằm chia tải. Một partition thường chỉ có một processor owner trong cơ chế cân bằng được thiết kế, nhưng khi failover/rebalance vẫn cần xử lý duplicate và bảo đảm an toàn dữ liệu.

Consumer group không phải “subscription push” như Event Grid event subscription. Consumer chủ động đọc và quản lý tiến độ.

## 12. Retention và replay trong Event Hubs

Event Hubs giữ các event đã nhận trong một **retention window** được cấu hình theo tier và giới hạn tính năng. Sau khi hết retention, bản ghi không còn khả dụng để đọc lại từ event hub dù consumer chưa checkpoint.

~~~text
Ngày 1: producer gửi events
Ngày 2: consumer realtime xử lý
Ngày 3: pipeline phân tích bị lỗi
Ngày 4: pipeline hoạt động lại

Nếu ngày 1 vẫn nằm trong retention:
  consumer có thể đọc lại từ offset phù hợp.

Nếu dữ liệu đã hết retention:
  không thể dựa vào Event Hubs để replay phần đã bị loại.
~~~

### Event Hubs Capture

**Capture** (khi được hỗ trợ và cấu hình) cho phép ghi dữ liệu stream vào **Azure Blob Storage hoặc Azure Data Lake Storage** theo chu kỳ/kích thước và định dạng được hỗ trợ. Điều này tạo một nguồn lưu dài hạn để phân tích hoặc tái xử lý.

~~~text
Event Hubs partitions
      |
      +--> realtime consumer -> alerts
      |
      +--> analytics consumer -> dashboards
      |
      +--> Capture -> Blob/ADLS -> offline batch/reprocess
~~~

Capture và retention của event hub là **hai lớp khác nhau**. Capture không tự bảo đảm dữ liệu đã được làm sạch, có schema phù hợp hoặc đáp ứng chính sách bất biến; cần kiểm tra đường lưu, quyền, lifecycle, chi phí và khả năng tái xử lý.

### Replay không phải xóa và gửi lại

Một consumer có thể đọc từ vị trí cũ trong thời gian retention. Việc replay có thể làm sink ghi dữ liệu trùng; phải phân biệt mục tiêu:

- **Recompute** một bảng thống kê từ sự kiện lịch sử.
- **Rebuild** materialized view hoặc search index.
- **Debug** consumer bằng dữ liệu mẫu.
- **Recovery** khi checkpoint đã bị cập nhật sai.

Khi replay, hãy cô lập output mới hoặc dùng cơ chế upsert/idempotency trước khi chạy trên dữ liệu production.

## 13. Event Hubs khác Service Bus Queue như thế nào?

Hai dịch vụ đều có tên “message/event” nhưng mô hình lưu giữ khác nhau.

| Nhu cầu | Event Hubs | Service Bus |
|---|---|---|
| Thu nhận telemetry rất lớn liên tục | Phù hợp | Không phải mục tiêu chính |
| Một bản ghi cần nhiều consumer độc lập đọc lại | Consumer groups và retention | Topic subscriptions có bản sao logic cho subscribers nhưng không là partition log replay tùy ý |
| Worker nhận job rồi ACK hoàn thành | Không có settlement Complete tương đương | Peek-Lock, Complete, Abandon, Dead-letter |
| Thứ tự theo key với stream processor | Partition key và partition ordering | Sessions theo tính năng phù hợp |
| Phát lại dữ liệu trong retention | Có, bằng vị trí offset/sequence | Không đọc lại message đã Complete như log |
| Lưu checkpoint theo consumer | Có | Dùng trạng thái message/settlement ở broker |
| Trì hoãn công việc/schedule message | Không phải cơ chế queue job chủ đạo | Có khả năng scheduled messages |
| Xử lý poison message riêng mỗi job | Consumer tự thiết kế quarantine/retry | Dead-letter subqueue theo entity |

**Service Bus Topic/Subscription** cũng hỗ trợ publish-subscribe, nhưng đó không phải bản sao đơn giản của Event Grid. Nếu mục tiêu là **giao thông điệp nghiệp vụ bền vững cho subscriber và settlement**, Service Bus phù hợp. Nếu mục tiêu là **đẩy notification khi Azure resource thay đổi tới handlers**, Event Grid thường là điểm xuất phát.

## 14. Khi nào chọn Azure Queue Storage?

**Azure Queue Storage** là lựa chọn hàng đợi công việc đơn giản, tích hợp với Storage Account và các dịch vụ như Azure Functions. Nó dùng mô hình nhận message/visibility timeout và xóa message khi công việc hoàn tất theo client, khác với Peek-Lock settlement của Service Bus.

| Dịch vụ | Dùng khi |
|---|---|
| Event Grid | Cần báo sự kiện và định tuyến đến handler |
| Event Hubs | Cần thu dòng dữ liệu lớn, partition, consumer groups và replay |
| Service Bus | Cần broker công việc với settlement, DLQ, sessions/transactions tùy tier |
| Storage Queue | Cần queue job tương đối đơn giản với visibility timeout |

Không dùng Queue Storage chỉ vì dữ liệu phát sinh “theo sự kiện”. Quyết định phải dựa vào yêu cầu lock, retry, throughput, kích thước, SLA, fan-out và các tính năng nâng cao.

## 15. Sơ đồ chọn dịch vụ theo mục tiêu

~~~text
Yêu cầu có nguồn event/message
              |
              v
Cần giữ stream để nhiều consumer đọc theo offset,
phân tích theo thời gian và có khả năng replay?
       | Có                     | Không
       v                        v
   Event Hubs             Cần thông báo sự kiện
                          nguồn đã xảy ra và route
                          tới handler?
                              | Có       | Không
                              v          v
                          Event Grid  Cần giao job,
                                      ACK, retry, DLQ
                                      theo nghiệp vụ?
                                         | Có
                                         v
                                    Service Bus
                                    hoặc Storage Queue
~~~

Đây là **quy tắc chọn ban đầu**, không phải mệnh lệnh phải dùng đúng một dịch vụ. Nhiều kiến trúc production kết hợp Event Grid, Event Hubs và Service Bus để mỗi thành phần làm đúng việc.

### Bảng quyết định theo tình huống

| Tình huống | Chọn khởi đầu | Lý do |
|---|---|---|
| Blob mới xuất hiện, cần gọi Function | **Event Grid** | Routing notification |
| Hàng triệu sensor readings, phân tích theo cửa sổ | **Event Hubs** | Streaming throughput/partition/consumer groups |
| Đơn hàng cần worker xử lý đúng quy trình với settlement | **Service Bus Queue** | Hàng đợi công việc và retry/DLQ |
| Nhiều hệ thống nhận cùng sự kiện thay đổi Azure resource | **Event Grid subscriptions** | Fan-out theo event type/filter |
| Một luồng clickstream cần realtime dashboard và kho lịch sử | **Event Hubs + Capture** | Nhiều consumer và lưu dài hạn |
| Producer yêu cầu tạo thumbnail từ BlobCreated rồi cần retry job | **Event Grid → Function → Service Bus** | Routing notification tách khỏi thực thi job |
| Thiết bị dùng MQTT để giao tiếp qua tính năng hỗ trợ | **Event Grid Namespaces MQTT hoặc IoT Hub theo yêu cầu** | Xem protocol/device management, không áp mặc định Event Grid topic push |
| Cần alert theo sự kiện nhưng cũng lưu toàn bộ telemetry | **Event Hubs + stream processor + notification** | Phân tích stream rồi phát cảnh báo |

## 16. Kiến trúc kết hợp: upload tệp và xử lý bất đồng bộ

Một kiến trúc hoàn chỉnh có thể gồm:

~~~text
Client upload image
         |
         v
Azure Blob Storage /incoming
         |
         | BlobCreated event
         v
      Event Grid
         |
         v
Azure Function (ingest)
  - validate event
  - deduplicate by eventId/blob version
  - check Blob URI/ETag
         |
         v
Service Bus Queue: thumbnail-jobs
         |
         v
Container Apps / AKS worker
  - idempotent job ledger
  - fetch correct Blob version
  - generate thumbnail
  - Complete/Dead-letter message
         |
         v
Blob Storage /processed
         |
         v
Monitoring + audit
~~~

### Vì sao không chạy công việc nặng trực tiếp trong webhook?

Một tác vụ xử lý ảnh có thể kéo dài vài phút hoặc cần nhiều lần retry. Nếu handler giữ request Event Grid quá lâu, delivery timeout/retry có thể làm cùng notification xuất hiện nhiều lần và gây áp lực lên nguồn.

Thiết kế thường tốt hơn:

1. **Ingest handler** kiểm tra notification.
2. Ghi một **job bền vững** vào queue hoặc store.
3. Trả kết quả delivery thành công **chỉ sau khi đã ghi job thành công**.
4. Worker thực hiện tác vụ dài với retry, DLQ và idempotency.

Ngay cả khi đã đưa vào queue, Event Grid có thể giao lại; handler phải chống gửi job trùng hoặc producer tạo MessageId/idempotency key ổn định.

### Dùng ETag hoặc versionId để tránh xử lý sai phiên bản

Nếu một blob liên tục bị overwrite, notification BlobCreated cũ có thể đến sau khi nội dung đã thay đổi. Worker cần chọn đúng bản dữ liệu hoặc xác minh ETag; nếu không, tạo thumbnail cho phiên bản mới nhưng ghi nhận như đã xử lý phiên bản cũ.

## 17. Kiến trúc kết hợp: telemetry streaming và phát cảnh báo

Với nhiều thiết bị, Event Hubs có thể thu telemetry để nhiều consumer phân tích:

~~~text
100.000 sensors
      |
      v
Ingestion gateway / producer
      |
      v
Azure Event Hubs (partitions)
      |
      +--> Consumer group: realtime
      |       |
      |       v
      |    Stream Analytics / custom processor
      |       |
      |       +--> Alert API / Service Bus -> Incident worker
      |       |
      |       +--> Time-series dashboard
      |
      +--> Consumer group: analytics
      |       |
      |       v
      |    Spark / Fabric / Data Explorer / data pipeline
      |
      +--> Capture -> Blob/ADLS (nếu được bật)
~~~

Event Hubs giữ dữ liệu đầu vào trong retention window; mỗi consumer group có tiến độ độc lập. Nếu consumer analytics bị lỗi hai giờ nhưng dữ liệu vẫn nằm trong retention, có thể đọc lại từ checkpoint. Nếu cần giữ lâu hơn, Capture hoặc lưu trữ dữ liệu khác có trách nhiệm riêng.

### Alert không phải mọi sensor reading

Một stream processor có thể phát hiện nhiệt độ quá cao trong năm phút và gửi **TemperatureAnomalyDetected** tới một queue hoặc hệ thống cảnh báo. Không cần chuyển hàng triệu sensor readings qua Event Grid chỉ để thực hiện phép trung bình liên tục; chính phép phân tích chuỗi là nhiệm vụ của stream processing.

## 18. Event Hubs và xử lý theo cửa sổ thời gian

Streaming không chỉ là “đọc từng event rồi gửi đi”. Một số nghiệp vụ cần:

- **Tumbling window**: chia thời gian thành các khoảng cố định không chồng lấn, ví dụ trung bình mỗi phút.
- **Hopping window**: các khoảng có thể chồng lấn, ví dụ trung bình 5 phút cập nhật mỗi 1 phút.
- **Sliding window**: xem các khoảng thay đổi liên tục khi event mới tới.
- **Session window**: nhóm sự kiện theo khoảng hoạt động/ngắt quãng theo engine hỗ trợ.

~~~text
Sensor readings (theo event time)
08:00:10  31°C
08:00:30  32°C
08:00:50  33°C
08:01:20  30°C

Tumbling window 08:00:00–08:01:00:
  AVG = (31 + 32 + 33) / 3 = 32°C

Window 08:01:00–08:02:00:
  có một reading 30°C trong ví dụ.
~~~

### Event time và processing time

- **Event time**: thời gian được ghi nhận bởi nguồn trong nội dung event.
- **Enqueue time**: thời gian broker nhận event theo metadata.
- **Processing time**: thời điểm consumer xử lý.

Một thiết bị mất kết nối có thể gửi dữ liệu cũ sau 10 phút. Nếu tính theo processing time, mẫu này thuộc cửa sổ muộn hơn; nếu tính theo event time, nó thuộc cửa sổ gốc nhưng cần xử lý **late arrival/watermark** theo công cụ stream processing.

Event Hubs không tự giải quyết logic watermark, aggregate hay reconciliation cho ứng dụng. Những hành vi đó thuộc engine như Azure Stream Analytics, Spark hoặc consumer tự viết.

## 19. Event streaming và Kafka compatibility

Azure Event Hubs có khả năng làm endpoint tương thích với **Apache Kafka protocol** trong những cấu hình/tier được hỗ trợ, giúp một số Kafka producers/consumers kết nối mà không cần vận hành Kafka brokers.

Điểm cần phân biệt:

- **Event Hubs** vẫn là dịch vụ Azure; không có nghĩa mọi API, tính năng broker, config topic hoặc extension Kafka đều tương đương một Kafka cluster tự quản.
- **Partitions**, consumer groups và offset là những khái niệm gần gũi với Kafka, nhưng quota, retention, security và giới hạn có thể khác.
- Khi migrate ứng dụng, cần thử protocol/client version, SASL/TLS, topic mapping, batching, ordering và error semantics.
- Không sử dụng tài liệu Kafka của môi trường tự quản để khẳng định một config sẽ có hiệu lực trên Event Hubs.

Nếu dự án đã dùng Kafka clients, tích hợp này có thể làm giảm thay đổi client; nếu chỉ muốn nhận event từ Blob thì không cần đưa Kafka vào kiến trúc.

## 20. Độ tin cậy: at-least-once, duplicate và thứ tự

Một trong những sai lầm phổ biến là nghĩ cả Event Grid và Event Hubs “gửi đúng một lần, theo đúng thứ tự”.

### Event Grid

- Delivery có thể lặp; handler cần **idempotency**.
- Không dựa vào thứ tự event đến.
- Delivery retry/dead-letter theo chính sách và kiểu destination.
- Không có mô hình checkpoint tùy ý như consumer của Event Hubs trong luồng push thông thường.

### Event Hubs

- Consumer đọc theo vị trí trong partition.
- **Checkpoint** có thể được ghi sau khi output bền vững.
- Nếu crash sau khi ghi output nhưng trước checkpoint, event có thể được đọc lại.
- Khi consumer tụt quá retention, một phần sự kiện cũ không còn trên hub để replay.
- Không có thứ tự toàn cục giữa các partition.

### Service Bus

- Peek-Lock và settlement cho phép nhận lại sau lock timeout.
- Complete thành công loại message khỏi queue/subscription tương ứng.
- Message được giao lại vẫn cần idempotency.
- Dead-letter giữ thông điệp lỗi trong subqueue.

| Tình huống lỗi | Cách xử lý |
|---|---|
| Event Grid giao trùng BlobCreated | Deduplicate theo event ID kết hợp blob version/operation ID |
| Event Grid đến muộn sau BlobDeleted | Kiểm tra trạng thái/phiên bản blob trước khi xử lý |
| Event Hubs consumer crash sau DB commit | Đọc lại và idempotent upsert theo event key |
| Event Hubs checkpoint trước DB commit | Tránh: chỉ checkpoint khi output đã bền vững |
| Service Bus Complete thất bại sau ghi DB | Consumer mới kiểm tra ledger và Complete mà không tạo trùng |
| Worker nhận dữ liệu sai schema | Quarantine/DLQ hoặc bảng lỗi tùy kiến trúc, không retry vô hạn |

## 21. Replay và reprocessing: thiết kế từ đầu

“Có thể replay” không có nghĩa bạn có thể bất kỳ lúc nào bấm một nút để toàn hệ thống trở về trạng thái cũ.

### Replay trong Event Hubs

Consumer có thể chọn **starting position** hoặc checkpoint cũ trong phạm vi event còn retention. Một nhóm phân tích mới có thể đọc từ đầu cửa sổ hiện còn để tính lại dashboard.

~~~text
Event Hub retention: một khoảng thời gian đã cấu hình

Consumer Group realtime:
  checkpoint mới nhất, tiếp tục xử lý live

Consumer Group investigation:
  đọc từ offset/time cũ còn khả dụng

Không ảnh hưởng tới vị trí đọc của realtime group.
~~~

### Replay từ Capture/Storage

Nếu dữ liệu đã hết retention của Event Hubs nhưng được Capture vào Blob/ADLS, một pipeline offline có thể đọc bản lưu và **tái xử lý**. Việc này không tự chuyển những file Capture thành event trong Event Hubs; muốn đưa lại vào stream phải thiết kế producer/replay pipeline riêng và kiểm soát duplicate.

### Event Grid và lịch sử notification

Event Grid push có retry/dead-letter theo điều kiện; nó **không** nhằm cung cấp lịch sử event lâu dài để mọi consumer tùy ý seek từ tuần trước. Khi cần audit/replay, hãy chủ động lưu event vào event store, Storage, Service Bus hoặc Event Hubs theo nhu cầu.

### Replay phải kiểm soát tác động

Khi tái đọc **PaymentSucceeded**, không được tự động gửi thêm một thanh toán. Consumer cần phân biệt:

- **Dựng lại projection/read model**: có thể tính lại từ event, dùng upsert.
- **Thực hiện side effect mới**: phải qua kiểm tra idempotency và quy trình phê duyệt.
- **Bổ sung event bị thiếu**: cần xác minh nguồn và thời điểm, tránh tạo hai bản sự kiện giả.

## 22. Thiết kế schema và idempotency key

Một hợp đồng event tốt cần nêu rõ:

| Trường | Ý nghĩa |
|---|---|
| **eventId** | Định danh một lần công bố event |
| **eventType** | Loại sự kiện và version tương ứng |
| **source** | Nguồn phát đáng tin cậy |
| **subject/entityId** | Đối tượng nghiệp vụ |
| **occurredAt** | Thời điểm nghiệp vụ xảy ra |
| **schemaVersion** | Phiên bản payload |
| **correlationId** | Liên kết các bước xử lý cùng một yêu cầu |
| **causationId** | Sự kiện/lệnh trước đó gây ra event này, nếu có |
| **partitionKey** | Khóa chọn partition nếu xử lý streaming yêu cầu |
| **data** | Payload đã giới hạn và được phân loại bảo mật |

**EventId** hữu ích để deduplicate một lần giao notification; **business operation ID** có thể cần để ngăn hai event khác ID nhưng đại diện cho cùng thao tác nghiệp vụ.

### Ví dụ một hợp đồng thay đổi đơn hàng

~~~json
{
  "eventId": "evt-00078",
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "entityId": "ORD-00078",
  "occurredAt": "2026-11-20T08:12:00Z",
  "correlationId": "checkout-8f4c",
  "data": {
    "orderStatus": "PLACED"
  }
}
~~~

Không tự coi payload này là đúng CloudEvents schema; nó là **contract ứng dụng**. Nếu gửi qua Event Grid CloudEvents, đặt các trường vào cấu trúc CloudEvents tương ứng, không trộn hai schema trong cùng một root JSON.

### Schema evolution

Consumer cũ có thể vẫn hoạt động khi producer thêm một trường tùy chọn, nhưng sẽ lỗi nếu producer đổi kiểu hoặc xóa trường bắt buộc. Có thể:

1. Giữ tương thích ngược trong giai đoạn chuyển đổi.
2. Dùng schema version rõ ràng.
3. Dùng schema registry/contract testing theo stack.
4. Định nghĩa chính sách reject/quarantine với event không hỗ trợ.
5. Thử lại từ event lịch sử khi cập nhật consumer.

## 23. Bảo mật: authentication khác với network access

Các dịch vụ event/messaging nằm trong kiến trúc Azure với Microsoft Entra ID, RBAC, mạng và bí mật. Không nhúng account key/connection string vào image hoặc source code.

### Các quyền cần đánh giá

| Thành phần | Quyền/kiểm soát thường cần |
|---|---|
| Ứng dụng xuất bản custom Event Grid event | Role/credential publish được hỗ trợ tại topic/namespace thích hợp |
| Event Grid subscription management | Azure RBAC để tạo/sửa routing/filter và endpoint |
| Event handler | Quyền truy cập resource được event tham chiếu, như Blob |
| Event Hubs producer | **Azure Event Hubs Data Sender** theo scope |
| Event Hubs consumer | **Azure Event Hubs Data Receiver** theo scope |
| Service Bus producer | **Azure Service Bus Data Sender** |
| Service Bus worker | **Azure Service Bus Data Receiver** |
| Analytics sink | Data-plane permissions riêng của Storage/DB/warehouse |

**Quyền nhận event không tự cấp quyền đọc blob.** Một Function được Event Grid kích hoạt vẫn cần identity và RBAC phù hợp để tải tệp từ Storage.

### Managed identity

Azure Functions, Container Apps, AKS Workload Identity và VM có thể dùng **managed identity**/Microsoft Entra ID để kết nối các dịch vụ hỗ trợ, tránh connection strings dài hạn. Cần kiểm tra scope/role, tenant, thời gian hiệu lực RBAC và SDK hỗ trợ.

### Webhook endpoint validation

Khi Event Grid push tới webhook, handler cần đáp ứng cơ chế **subscription validation/handshake** theo schema và endpoint tương ứng, hoặc sử dụng một destination tích hợp như Azure Functions theo mô hình được hỗ trợ.

Ngoài handshake, phải xác thực yêu cầu giao event theo phương thức được hỗ trợ (ví dụ Entra authentication hoặc cơ chế ký/định danh tương ứng). **Không coi một HTTP POST mang JSON trông giống CloudEvents là nguồn đáng tin nếu không kiểm tra nguồn và quyền.**

### Private networking

- Event Hubs, Service Bus và Storage có thể có lựa chọn Private Endpoint/firewall theo tier/tính năng.
- Event Grid có các khả năng network khác nhau theo loại topic, namespace và endpoint; **không mặc định mọi push webhook nằm trong VNet đều được Event Grid truy cập qua Private Endpoint**.
- Worker/producer cần DNS, routing, NSG/UDR và outbound cho endpoint phù hợp.
- Dữ liệu được truyền qua TLS; quyền data plane vẫn cần thiết dù kết nối mạng riêng đã hoạt động.

Đừng khắc phục một lỗi 403 bằng cách mở public network access toàn bộ hoặc cấp Owner trên subscription. Phải tách lỗi **auth/RBAC** khỏi **DNS/route/firewall/TLS**.

## 24. Ví dụ Python: Event Hubs producer bằng Microsoft Entra ID

Ví dụ dưới đây **sẽ gửi dữ liệu thật tới một event hub** nếu được chạy. Chỉ thực hiện trong namespace/event hub **lab** được cấp quyền, với ngân sách và quota đã được xác nhận. Không tự dùng môi trường production.

### Chuẩn bị

- Event Hubs namespace và event hub đã tồn tại.
- Danh tính local hoặc managed identity có **Azure Event Hubs Data Sender** phù hợp.
- Network tới namespace cho phép kết nối.
- Python cài các package:

~~~bash
python -m pip install azure-eventhub azure-identity
~~~

Đặt biến môi trường tại terminal phù hợp:

~~~bash
export EVENTHUB_FQDN="eh-demo.servicebus.windows.net"
export EVENTHUB_NAME="device-telemetry"
~~~

**FQDN là tên namespace Event Hubs** và event hub name là entity chứa stream; không nhầm với Service Bus Queue dù đều có hostname dạng servicebus.windows.net.

### Producer mẫu

~~~python
import json
import os
from datetime import datetime, timezone

from azure.eventhub import EventData, EventHubProducerClient
from azure.identity import DefaultAzureCredential

fqdn = os.environ["EVENTHUB_FQDN"]
hub_name = os.environ["EVENTHUB_NAME"]
credential = DefaultAzureCredential()

try:
    with EventHubProducerClient(
        fully_qualified_namespace=fqdn,
        eventhub_name=hub_name,
        credential=credential,
    ) as producer:
        sample = {
            "deviceId": "sensor-lab-23",
            "temperature": 31.7,
            "recordedAt": datetime.now(timezone.utc).isoformat(),
        }

        # Dùng cùng partition key cho nhóm bản ghi của một device
        # theo điều kiện ordering/producer phù hợp.
        batch = producer.create_batch(partition_key=sample["deviceId"])
        batch.add(EventData(json.dumps(sample)))
        producer.send_batch(batch)
        print("Sent one lab telemetry event")
finally:
    credential.close()
~~~

Code tạo một **batch** với partition key rồi gửi một event; không cung cấp checkpoint hay consumer. Khi dữ liệu lớn, cần kiểm tra batch size, retry và giới hạn throughput/tier; không đặt vòng lặp gửi vô hạn chỉ để kiểm tra kiến trúc.

### Producer không phải stream processor

Producer chỉ gửi dữ liệu. Muốn tính trung bình nhiệt độ theo cửa sổ, phải có **consumer hoặc stream engine** đọc từ Event Hubs, xử lý theo event time/window và lưu output.

## 25. Ví dụ consumer và checkpoint trong Event Hubs

Một consumer đơn giản đọc stream nhưng chưa có checkpoint store:

~~~python
import os

from azure.eventhub import EventHubConsumerClient
from azure.identity import DefaultAzureCredential

fqdn = os.environ["EVENTHUB_FQDN"]
hub_name = os.environ["EVENTHUB_NAME"]
credential = DefaultAzureCredential()


def on_event(partition_context, event):
    if event is None:
        return

    print(
        "partition=", partition_context.partition_id,
        "sequence=", event.sequence_number,
        "body=", event.body_as_str(),
    )
    # Ví dụ chỉ hiển thị dữ liệu; không gọi checkpoint vì
    # chưa có durable sink và checkpoint store.


try:
    with EventHubConsumerClient(
        fully_qualified_namespace=fqdn,
        eventhub_name=hub_name,
        consumer_group="$Default",
        credential=credential,
    ) as consumer:
        # Bắt đầu từ event còn được retention ở vị trí sớm nhất.
        # receive là vòng lặp dài hạn; dừng bằng Ctrl+C khi thử nghiệm.
        consumer.receive(
            on_event=on_event,
            starting_position="-1",
            max_wait_time=10,
        )
finally:
    credential.close()
~~~

**Giới hạn:** Đây là **lab consumer chỉ đọc và in**; chưa cân bằng partitions trên nhiều process bằng một checkpoint store chia sẻ, chưa ghi kết quả bền vững, chưa kiểm soát chi phí logging và có thể in payload nhạy cảm nếu dùng dữ liệu thật. Không chạy trên stream production có PII.

### Pseudocode checkpoint an toàn cho production

~~~text
on_event(partition, event):
    validate event schema
    businessKey = event deviceId + sequence/operation identifier
    calculate result / transform data

    write output idempotently into durable store
    if durable write succeeded:
        persist checkpoint at this event position
    else:
        do not advance checkpoint
        retry/quarantine according to policy
~~~

Trong ứng dụng nhiều partitions/consumers, sử dụng **event processor/checkpoint store** tương thích để phối hợp ownership và tiến độ. SDK có các thành phần tích hợp Azure Blob Storage cho checkpoint theo khả năng tương ứng; cần tạo container và quyền Blob Data phù hợp.

**Checkpoint thường phản ánh vị trí tiêu thụ, không phải một transaction nguyên tử với database đích.** Bởi vậy sink phải có idempotency hoặc chiến lược transactional processing.

## 26. Kiểm tra read-only với Azure CLI

Các lệnh dưới đây **chỉ đọc cấu hình** và không tạo hay xuất bản event. Tên subscription/resource group/namespace là ví dụ; thay bằng tài nguyên đã được cấp quyền.

### Event Grid: xem custom topic

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az eventgrid topic show \
  --resource-group "rg-events-lab" \
  --name "topic-order-events" \
  --output json
~~~

### Event Grid: xem event subscriptions theo resource

~~~bash
az eventgrid event-subscription list \
  --source-resource-id "<FULL_AZURE_RESOURCE_ID>" \
  --output json
~~~

Chỉ định **full resource ID** của system topic, Storage Account hoặc topic tương ứng theo cấu hình. Tên lệnh/tham số cần đối chiếu với phiên bản Azure CLI/extension khi chạy.

### Event Hubs: xem event hub

~~~bash
az eventhubs eventhub show \
  --resource-group "rg-events-lab" \
  --namespace-name "eh-demo" \
  --name "device-telemetry" \
  --output json
~~~

Quan sát **partitionCount**, **messageRetentionInDays** hoặc các trường retention tùy API/tier, trạng thái và cấu hình Capture nếu có. Không suy ra pipeline đang xử lý tốt chỉ vì entity tồn tại.

### Event Hubs: consumer groups

~~~bash
az eventhubs eventhub consumer-group list \
  --resource-group "rg-events-lab" \
  --namespace-name "eh-demo" \
  --eventhub-name "device-telemetry" \
  --output table
~~~

Liệt kê consumer groups không cho biết **checkpoint của từng partition** nếu checkpoint nằm trong một storage riêng. Muốn biết consumer lag, cần quan sát offset/sequence hiện tại, checkpoint của consumer và metric/telemetry từ pipeline.

### Service Bus: thông số queue nếu kiến trúc kết hợp

~~~bash
az servicebus queue show \
  --resource-group "rg-events-lab" \
  --namespace-name "sb-jobs-lab" \
  --name "thumbnail-jobs" \
  --output json
~~~

Trong production, quan sát cấu hình và logs trước khi chỉnh queue retention, lock duration hoặc rule; thay đổi các thông số này có thể ảnh hưởng message đang chạy.

## 27. Lab kiến trúc A: BlobCreated → Event Grid → handler

**Mục tiêu:** hiểu routing thông báo. Lab dùng dữ liệu giả và nguồn Storage được phép, không xử lý tài liệu nhạy cảm.

### Chuẩn bị

1. Tạo hoặc chọn một Storage Account lab hỗ trợ Blob events và container **images-lab**.
2. Chọn handler đã được triển khai và có thể xác thực, chẳng hạn Azure Function phù hợp với Event Grid trigger.
3. Bật logging và có cách xem eventId, event type, subject và kết quả xử lý.
4. Chuẩn bị một file PNG thử nghiệm không chứa PII.
5. Xác nhận người thực hiện có quyền tạo event subscription và truy cập Storage theo nhu cầu.

### Các bước

1. Trong Azure portal, mở trang sự kiện của Storage Account.
2. Tạo **event subscription** cho loại **BlobCreated** với subject filter chỉ chọn container lab nếu khả năng giao diện cho phép.
3. Chọn destination là Function/handler đã chuẩn bị; xác minh các yêu cầu authentication/validation.
4. Upload file thử nghiệm vào **images-lab**.
5. Kiểm tra handler nhận event, phân tích URI và event ID.
6. Cho handler ghi job/marker idempotent và chỉ ghi trạng thái đã xử lý sau khi hoàn thành.
7. Upload file khác và kiểm tra filter; thử file không phù hợp để xác minh không bị định tuyến ngoài dự định.

### Nghiệm thu

| Kiểm tra | Điều mong đợi |
|---|---|
| BlobCreated tới handler | Handler được kích hoạt với event hợp lệ |
| Event ID/subject | Có trong log an toàn |
| File ngoài filter | Không kích hoạt handler mục tiêu |
| Event trùng | Không tạo output nghiệp vụ trùng |
| Handler tạm lỗi | Có retry/dead-letter theo cấu hình được hỗ trợ |
| RBAC Storage | Handler chỉ đọc đúng container cần thiết |

**Không cố ý xóa/sửa tài nguyên production để tạo event thử.** Nếu cần thử delivery failure, sử dụng handler/queue lab, với retry policy/retention đủ để không gây áp lực bất thường.

## 28. Lab kiến trúc B: telemetry → Event Hubs → hai consumer groups

**Mục tiêu:** quan sát cùng event stream được hai consumer đọc độc lập.

### Chuẩn bị

1. Tạo hoặc dùng Event Hubs namespace lab với event hub **device-telemetry**.
2. Kiểm tra số partitions, retention và quota/tier.
3. Tạo consumer groups **realtime-lab** và **analytics-lab** (nếu được cấp quyền).
4. Gán quyền Data Sender cho producer và Data Receiver cho consumers.
5. Chuẩn bị storage checkpoint riêng nếu muốn thử nhận dữ liệu bền vững qua restart.

### Thực hành

1. Dùng producer mẫu ở mục 24 gửi vài chục readings có deviceId và recordedAt.
2. Chạy consumer thuộc **realtime-lab** để xem các bản ghi đến theo partition.
3. Chạy consumer khác thuộc **analytics-lab**; xác minh nó có thể đọc cùng dữ liệu còn retention.
4. Dừng một consumer, gửi thêm readings rồi khởi động lại từ checkpoint/starting position đã chọn.
5. Thử đọc lại dữ liệu cũ còn retention và ghi kết quả vào kho test độc lập.
6. Gửi readings tới nhiều deviceId để quan sát phân phối partitions.
7. Nếu có Capture, kiểm tra file được lưu tại đích và quy trình tái xử lý.

### Câu hỏi nghiệm thu

- Vì sao hai groups cùng nhận một event mà producer chỉ gửi một lần?
- Nếu consumer không checkpoint, khởi động lại có thể đọc trùng thế nào?
- Vì sao sequence number chỉ có ý nghĩa thứ tự trong partition?
- Nếu backlog quá lớn và vượt retention, mất khả năng replay ra sao?
- Vì sao Capture không đồng nghĩa một consumer group đã xử lý thành công?

Không dùng một consumer vừa phát replay vào cùng event hub vừa nhận từ đó mà không có bảo vệ vòng lặp, vì có thể tạo **event amplification** và tăng chi phí.

## 29. Thiết kế chịu lỗi trong pipeline kết hợp

Khi kết hợp Event Grid, Service Bus và Event Hubs, cần xác định ranh giới **acknowledgement/checkpoint** ở từng hop.

~~~text
Nguồn tạo event
      |
      v
Event Grid --> delivery success với ingest handler
      |
      v
Ingest handler ghi job vào Service Bus
      |
      v
Service Bus worker nhận Peek-Lock
      |
      +--> commit output/ledger
      |
      +--> Complete message
      |
      v
Kết quả nghiệp vụ đã hoàn thành
~~~

**Event Grid delivery thành công** chỉ chứng minh message đã được handler chấp nhận theo hợp đồng giao hàng, **không chứng minh OCR hoặc hóa đơn đã tạo xong**. **Service Bus Complete** phản ánh việc worker đã xác nhận xử lý theo code; vẫn cần kiểm tra kết quả/ledger.

Đối với streaming:

~~~text
Producer gửi event thành công
      |
      v
Event Hubs ghi event vào partition
      |
      v
Consumer nhận event
      |
      +--> ghi output bền vững
      |
      +--> cập nhật checkpoint
      |
      v
Tiến độ xử lý đã được lưu riêng
~~~

**Producer send success** không đồng nghĩa mọi consumer đã xử lý. Đây là điểm khác căn bản khi thiết kế SLO, kiểm thử và báo cáo.

### RPO/RTO và retention

Nếu doanh nghiệp yêu cầu không mất telemetry trong một thời gian downtime dài, cần retention/backup/capture đủ và kiểm tra capacity. Nếu Event Grid push thất bại kéo dài, cần dead-letter phù hợp hoặc cơ chế truy vấn lại nguồn sự kiện. Đừng chỉ bật retry mà coi như đã đáp ứng DR.

## 30. Quan sát và giám sát theo đúng mô hình

| Tín hiệu | Event Grid | Event Hubs | Service Bus |
|---|---|---|---|
| Ingress | Published events | Incoming messages/bytes | Incoming messages |
| Delivery/processing | Matched/delivered/failed/dead-letter theo khả năng | Outgoing events/bytes, consumer lag tự tính | Active/locked/completed/dead-letter |
| Failure | Endpoint errors, retry/dead-letter | Throttling, failed requests, consumer errors | Lock lost, MaxDeliveryCount, DLQ |
| Progress | Handler job ledger | Offset/checkpoint từng partition/group | Settlement status và job ledger |
| Latency | Publish tới handler accepted | Enqueue tới processed event time | Enqueue tới Complete |
| Backlog | Undelivered/retry theo delivery policy | Lag và checkpoint age theo pipeline | Active message count/oldest age |
| Capacity | Publish/delivery operations | Units/partitions/throughput | Broker tier/requests/message size |

Không phải mọi hàng trong bảng là tên **metric Azure Monitor mặc định**. Ví dụ consumer lag của Event Hubs thường cần kết hợp checkpoint với vị trí cuối partition và dữ liệu ứng dụng. Kết quả thumbnail hoặc latency nghiệp vụ cũng cần tự ghi telemetry.

### Correlation ID

Ví dụ log tối thiểu:

~~~json
{
  "eventId": "evt-00042",
  "source": "/sales/orders",
  "correlationId": "checkout-demo-42",
  "stage": "thumbnail-ingest",
  "outcome": "JOB_ENQUEUED",
  "durationMs": 125
}
~~~

Không log secrets, SAS token, private keys, toàn bộ dữ liệu cá nhân hay payload thanh toán. Event Hubs consumer demo in body phải chỉ chạy trên dữ liệu lab an toàn.

### Những cảnh báo hữu ích

- Event Grid failed deliveries hoặc dead-letter tăng đột biến.
- Một destination có tỉ lệ timeout/429/5xx cao.
- Event Hubs throttled requests, consumer lag hoặc checkpoint age vượt SLA.
- Consumer crash/rebalance liên tục.
- Service Bus Queue backlog/DLQ/MessageLockLost tăng.
- Output không khớp số event đã nhận dù producer metrics bình thường.
- Chi phí ingestion, capture, log hoặc compute vượt ngân sách.

## 31. Chi phí và sizing

Event Grid, Event Hubs và Service Bus có **mô hình tính phí và capacity riêng**. Đừng tính cả ba chỉ bằng số event.

### Event Grid

Quan tâm tới loại tier/namespace/topic, lượng publish/delivery/operations, retry, dead-letter destination, handler compute và traffic/network tùy chức năng. Một event fan-out tới ba đích có thể phát sinh khối lượng delivery lớn hơn so với một đích.

### Event Hubs

Quan tâm tới tier, throughput/capacity units, partitions, ingress/egress, retention, Capture, storage đích, networking và consumer processing. Số partitions không là phép đo duy nhất của năng lực; thông lượng và giới hạn của tier cần được tính riêng.

### Service Bus

Quan tâm tới tier, operations, messaging units hoặc capacity theo cấu hình, queue/topic-subscriptions, traffic, DLQ, retries và worker compute. Mỗi message retry nhiều lần có thể làm tăng hoạt động dù số nghiệp vụ không thay đổi.

### Ví dụ sizing telemetry

Giả sử một hệ thống gửi:

~~~text
100.000 thiết bị
Mỗi thiết bị gửi 1 reading/phút

Tổng ngày:
  100.000 x 60 x 24 = 144.000.000 readings/ngày

Trung bình:
  100.000 / 60 ≈ 1.667 readings/giây

Peak gấp 4 lần:
  khoảng 6.667 readings/giây
~~~

Đây là phép tính lưu lượng cơ bản, **chưa tính kích thước bytes mỗi event, batching, headers, retention, partition skew, throttling hay số consumer**. Khi sizing Event Hubs phải tính **bytes/second và events/second**, tier/capacity phù hợp, partition count và throughput của downstream.

Không đưa mức giá USD cố định vì giá phụ thuộc vùng Azure, tier, thời điểm và cấu hình. Dùng Azure Pricing Calculator/Cost Management để dự toán và theo dõi chi phí thực.

## 32. Lỗi chọn dịch vụ phổ biến

| Triệu chứng/thiết kế | Vấn đề | Cách cải thiện |
|---|---|---|
| Dùng Event Grid như nơi giữ telemetry nhiều ngày | Không có semantics partition log/replay tùy ý trong routing push | Dùng Event Hubs + retention/Capture |
| Dùng Event Hubs làm queue task có Complete/Abandon | Không có settlement theo từng event giống Service Bus | Dùng Service Bus/Storage Queue cho worker job |
| Dùng Service Bus để phát hàng triệu sensor readings rồi phân tích window | Không tối ưu cho mục tiêu streaming throughput/partition consumption | Đánh giá Event Hubs |
| Đặt toàn bộ PDF trong Event Grid event | Notification quá lớn và coupling với payload | Gửi Blob reference + ETag/version |
| Không lưu idempotency key cho webhook | Event Grid retry tạo kết quả trùng | Ledger theo eventId/business operation |
| Consumer checkpoint trước khi ghi DB | Có thể bỏ qua dữ liệu chưa xử lý sau restart | Durable commit rồi checkpoint |
| Streaming không tính event-time lateness | Aggregate sai khi dữ liệu đến muộn | Watermark/reconciliation theo engine |
| Chỉ dùng một consumer group cho dashboard và ETL, chia load ngoài ý muốn | Các processors chia partitions, không phải hai luồng độc lập | Consumer groups riêng cho mục tiêu độc lập |
| Coi Event Grid delivery success là business success | Handler có thể chỉ enqueue job | Theo dõi job lifecycle riêng |
| Mở public network để chữa lỗi 403 | Có thể do identity/RBAC, không phải network | Phân loại auth vs route/DNS/firewall |
| Không cấu hình dead-letter/quarantine | Event lỗi khó kiểm tra sau retry | Thiết kế DLQ/event store theo dịch vụ |
| Bật fan-out rộng không filter | Lượng delivery và chi phí tăng | Filter theo type/subject/metadata |

## 33. Quy trình chẩn đoán theo lớp

Khi “event không tới nơi”, đừng bắt đầu bằng việc đổi tất cả timeout hoặc nới quyền.

### Bước 1: xác định nguồn

- Producer đã phát đúng event chưa?
- Event type/schema và source/subject có đúng không?
- Blob đã được tạo/commit ở thời điểm dự kiến chưa?
- Producer Event Hubs có nhận lỗi 401/403/quota/throttle không?

### Bước 2: xác định dịch vụ trung gian

- **Event Grid:** subscription tồn tại, filter có match, destination hợp lệ, delivery success/failure/retry?
- **Event Hubs:** event hub/partition có ghi event, consumer group đang đọc offset nào, retention còn không?
- **Service Bus:** message đang Active, Locked, Deferred, Scheduled hay DLQ?

### Bước 3: xác định consumer

- Handler có nhận request và xác thực đúng không?
- Consumer có đang chạy, crash hoặc gặp schema không tương thích?
- Có commit output hay chỉ ghi log “received”?
- Có checkpoint/settlement trước khi lưu kết quả không?

### Bước 4: xác định data/identity/network

- RBAC của Function/Container App/AKS đã được cấp đúng scope chưa?
- DNS, Private Endpoint, NSG/UDR/Azure Firewall có cho phép đường kết nối không?
- Blob version/ETag có còn khớp reference trong event không?

### Bước 5: xác nhận end-to-end

Thử một **event giả với correlationId** duy nhất. Ghi lại thời gian mỗi bước, so sánh messageId/eventId/checkpoint hoặc job ledger. Chỉ đánh dấu PASS khi kết quả nghiệp vụ ở đích tồn tại và đúng, không chỉ khi event đã được publish.

## 34. Case study: chọn kiến trúc cho nền tảng bán lẻ

Một doanh nghiệp bán lẻ có bốn nhu cầu:

1. Người dùng upload ảnh sản phẩm; hệ thống tạo thumbnail.
2. Website thu thập khoảng **5 triệu click events/ngày** để phân tích hành vi.
3. Mỗi đơn hàng mới phải được một worker tạo hóa đơn và có DLQ khi thất bại.
4. Đội phân tích muốn đọc lại clickstream bảy ngày trước khi thử thuật toán mới.

### Nhiệm vụ

1. Chọn dịch vụ thích hợp cho từng yêu cầu và giải thích.
2. Thiết kế hệ thống nhận BlobCreated với filter theo container.
3. Giải thích tại sao nên tách thumbnail job sang queue nếu xử lý kéo dài.
4. Đề xuất partition key cho clickstream khi cần phân tích hành vi theo người dùng/phiên mà không lưu PII dư thừa.
5. Xây dựng consumer groups riêng cho realtime dashboard và analytics.
6. Giải thích điều gì xảy ra nếu consumer analytics ngừng hai ngày, vẫn còn hoặc đã hết retention.
7. Chọn cách bảo vệ replay bảy ngày trước và cách dùng Capture nếu retention không đủ.
8. Nêu thiết kế idempotency/settlement cho worker hóa đơn.
9. Thiết kế RBAC/managed identity, private networking và log an toàn.
10. Lập bộ metrics/alerts chứng minh từng mục tiêu đáp ứng.
11. Nêu ít nhất hai cách failover/restore khi consumer checkpoint bị mất.
12. So sánh chi phí fan-out Event Grid với throughput/retention Event Hubs.

### Gợi ý lời giải

~~~text
Ảnh sản phẩm:
Blob Storage -> Event Grid -> Function -> Service Bus -> thumbnail worker

Clickstream:
Web producer -> Event Hubs
                   +-> Consumer group realtime -> dashboard
                   +-> Consumer group analytics -> data lake
                   +-> Capture -> ADLS nếu cần lưu dài hạn

Đơn hàng:
Order service -> Service Bus Queue -> invoice worker -> DB/Blob
~~~

Event Grid hỗ trợ routing khi file xuất hiện. Event Hubs phù hợp để thu clickstream liên tục và đọc lại trong retention; nếu muốn nghiên cứu dữ liệu sau thời hạn retention phải có kho dữ liệu riêng như Capture/ADLS. Service Bus giải quyết việc giao nhiệm vụ hóa đơn với settlement/DLQ.

## 35. Checklist trước khi đưa vào production

| Hạng mục | Điều cần xác nhận |
|---|---|
| Mục tiêu | Routing notification, streaming analytics hay queue job được phân loại rõ |
| Schema | Event type, source, version, correlationId và dữ liệu nhạy cảm được xác định |
| Event Grid | Topic/subscription, filter, destination, retry/dead-letter phù hợp |
| Event Hubs | Namespace, partitions, retention, producer/consumer groups, checkpoints |
| Service Bus | Queue/subscriptions, lock, settlement, DLQ, idempotency nếu dùng |
| Ordering | Không giả định global ordering; chọn partition key/sessions khi cần |
| Replay | Retention và lưu dài hạn/Capture phù hợp RPO và nhu cầu phân tích |
| Idempotency | Consumer chịu được duplicate và side effect không chạy hai lần |
| Auth | Entra ID, managed identity/RBAC hoặc secrets có vòng đời rõ |
| Networking | DNS, firewall, Private Endpoint/ingress theo tính năng được hỗ trợ |
| Payload | Có giới hạn kích thước, tham chiếu nguồn thay vì gửi dữ liệu lớn |
| Consumer | Có retry, backoff, quarantine, checkpoint/settlement đúng thời điểm |
| Revisions | Schema migration, consumer version compatibility, rollback |
| Observability | Publish/delivery, consumer lag, business outcome, failed events, DLQ |
| Cost | Dự toán fan-out/ingress/egress/retention/capture/compute/log |
| Recovery | Có restore/replay drill và kiểm tra tính đúng đắn sau lỗi |

## 36. Câu hỏi tự kiểm tra

1. Sự khác biệt cốt lõi giữa event routing và event streaming là gì?
2. Vì sao BlobCreated notification không nên chứa toàn bộ nội dung video?
3. Event Grid **system topic** và **custom topic** phục vụ những nguồn nào?
4. Event subscription khác consumer group ở đâu?
5. Tại sao không nên khẳng định mọi Event Grid delivery đều là push?
6. Những trường cơ bản của CloudEvents là gì?
7. Event Grid schema và CloudEvents có cùng tên field không?
8. Filter theo subject giải quyết vấn đề gì? Nó có kiểm tra tính an toàn file không?
9. Vì sao handler Event Grid phải idempotent?
10. Event Grid có bảo đảm thứ tự notification như producer phát không?
11. Tại sao Event Grid push không tương đương event log replay tùy ý?
12. Partition của Event Hubs có tác dụng gì?
13. Khi nào nên sử dụng partition key là deviceId?
14. Event Hubs có thứ tự toàn cục giữa mọi partition không?
15. Consumer group khác Service Bus subscription thế nào?
16. Offset/checkpoint có làm broker xóa event khỏi Event Hubs không?
17. Tại sao commit DB trước checkpoint thường an toàn hơn chiều ngược lại?
18. Điều gì xảy ra nếu consumer chậm hơn retention window?
19. Capture giải quyết vấn đề gì? Capture có tự đảm bảo consumer đã xử lý đúng không?
20. Khi nào dùng Azure Service Bus thay Event Hubs?
21. Receive/Complete trong Service Bus khác Event Hubs checkpoint ra sao?
22. Vì sao một stream processor cần quan tâm event time và processing time?
23. Phát lại PaymentSucceeded có rủi ro gì nếu consumer không idempotent?
24. Producer được cấp quyền gửi Event Hubs có tự có quyền đọc Blob output không?
25. Có thể phân biệt lỗi auth với lỗi private DNS/network bằng những dấu hiệu nào?
26. Khi tăng partitions, giả định về mapping partition key cần đánh giá gì?
27. Những chỉ số nào giúp biết realtime consumer đang tụt lại so với producer?
28. Làm sao kết hợp Event Grid và Service Bus để không chạy OCR lâu trong webhook?
29. Vì sao số event đã publish không phải số nghiệp vụ đã hoàn thành?
30. Nêu các thành phần chi phí chính của Event Grid, Event Hubs và Service Bus.

## Tài liệu tham khảo

- Microsoft Learn — *What is Azure Event Grid?*: https://learn.microsoft.com/azure/event-grid/overview
- Microsoft Learn — *Event Grid event schema*: https://learn.microsoft.com/azure/event-grid/event-schema
- Microsoft Learn — *CloudEvents schema*: https://learn.microsoft.com/azure/event-grid/cloud-event-schema
- Microsoft Learn — *Event filtering*: https://learn.microsoft.com/azure/event-grid/event-filtering
- Microsoft Learn — *Event Grid delivery and retry*: https://learn.microsoft.com/azure/event-grid/delivery-and-retry
- Microsoft Learn — *Event Grid Namespaces overview*: https://learn.microsoft.com/azure/event-grid/namespace-overview
- Microsoft Learn — *What is Azure Event Hubs?*: https://learn.microsoft.com/azure/event-hubs/event-hubs-about
- Microsoft Learn — *Event Hubs features and concepts*: https://learn.microsoft.com/azure/event-hubs/event-hubs-features
- Microsoft Learn — *Event Hubs scalability*: https://learn.microsoft.com/azure/event-hubs/event-hubs-scalability
- Microsoft Learn — *Event Hubs Capture*: https://learn.microsoft.com/azure/event-hubs/event-hubs-capture-overview
- Microsoft Learn — *Event Hubs consumer/processor concepts*: https://learn.microsoft.com/azure/event-hubs/event-hubs-event-processor-host
- Microsoft Learn — *Azure Service Bus messaging*: https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview
- Microsoft Learn — *Event Hubs Python SDK*: https://learn.microsoft.com/python/api/overview/azure/eventhub-readme
- CloudEvents specification: https://github.com/cloudevents/spec
