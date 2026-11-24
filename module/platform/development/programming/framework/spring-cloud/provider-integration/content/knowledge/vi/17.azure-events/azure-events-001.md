# Phân biệt Event Hubs, Event Grid và Service Bus

Azure cung cấp nhiều dịch vụ truyền sự kiện và thông điệp, nhưng chúng giải quyết những bài toán khác nhau. **Event Hubs** phù hợp với luồng dữ liệu sự kiện lớn cần ingest và xử lý liên tục; **Event Grid** phù hợp với định tuyến sự kiện khi một điều gì đó đã xảy ra; **Service Bus** phù hợp với messaging nghiệp vụ cần queue, topic, subscription, xử lý xác nhận và các khả năng điều phối thông điệp. Chọn sai dịch vụ có thể khiến ứng dụng khó bảo đảm thứ tự, khó xử lý message trùng, tăng chi phí hoặc phải tự xây dựng những chức năng nền tảng đã có ở dịch vụ khác.

Bài học thuộc chương **Sự kiện Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mục tiêu là giúp người học tích hợp Spring Boot với dịch vụ managed của Azure qua Azure SDK và các thư viện Spring Cloud Azure phù hợp; biết cấu hình danh tính và quyền, gửi/nhận dữ liệu, bảo vệ secret, xử lý lỗi, kiểm thử tích hợp và so sánh lựa chọn Azure với AWS và Google Cloud.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích khác biệt về mục đích giữa **event streaming**, **event routing** và **enterprise messaging**.
- Chọn Event Hubs, Event Grid hoặc Service Bus dựa trên loại dữ liệu, delivery semantics, thứ tự, replay, routing và nhu cầu transaction.
- Hiểu partition, consumer group, offset, checkpoint, event subscription, queue, topic, subscription và dead-letter queue.
- Thiết kế producer/consumer Spring Boot với Azure SDK, managed identity và RBAC.
- Xử lý duplicate, retry, poison event, backpressure, checkpoint và sự cố từng phần.
- Thiết kế test trên namespace/topic/queue riêng, theo dõi metric, quota và chi phí.
- Nhận diện khi nào cần kết hợp nhiều dịch vụ thành một kiến trúc event-driven.

## 2. Phân biệt event, message và stream

Ba từ này thường được dùng lẫn nhau, nhưng có thể hiểu theo mục đích:

- **Event (sự kiện)** mô tả một điều đã xảy ra: `OrderCreated`, `InvoiceUploaded`, `CustomerAddressChanged`. Event thường bất biến về ý nghĩa: nó ghi nhận một sự thật trong quá khứ.
- **Command (lệnh)** yêu cầu một thành phần thực hiện điều gì đó: `ReserveInventory`, `SendInvoice`, `CancelOrder`. Command thường có một nơi chịu trách nhiệm xử lý và có kết quả nghiệp vụ cần theo dõi.
- **Message (thông điệp)** là đơn vị dữ liệu được truyền giữa các thành phần. Message có thể mang event, command hoặc dữ liệu công việc.
- **Event stream (luồng sự kiện)** là chuỗi sự kiện liên tục, có thể được ghi nhận và đọc bởi nhiều consumer theo vị trí/offset. Consumer có thể cần đọc lại lịch sử để dựng lại trạng thái hoặc chạy một phép tính mới.

Ví dụ trong hệ thống đơn hàng:

| Dữ liệu | Ý nghĩa | Nhu cầu truyền thường gặp |
|---|---|---|
| `OrderCreated` | Đơn hàng vừa được tạo | Phát cho nhiều consumer: kho, hóa đơn, phân tích |
| `ReserveInventory` | Yêu cầu giữ hàng | Một worker xử lý command và báo kết quả |
| Clickstream / telemetry | Dòng sự kiện lớn, liên tục | Ingest throughput cao, nhiều consumer đọc độc lập |
| `BlobCreated` | Một object mới xuất hiện | Định tuyến thông báo đến handler phù hợp |
| `PaymentAuthorized` | Thanh toán được xác nhận | Giao thông điệp nghiệp vụ có retry, DLQ và audit |

Một event có thể được gửi qua nhiều loại dịch vụ tùy nhu cầu. Tên payload không quyết định dịch vụ; **delivery, retention, routing, ordering và cách consumer xử lý** mới là cơ sở chọn.

## 3. Nhìn nhanh: ba dịch vụ giải quyết ba bài toán

| Dịch vụ | Vai trò chính | Hình dung |
|---|---|---|
| **Azure Event Hubs** | Nền tảng ingest và xử lý event stream quy mô lớn | Một luồng sự kiện được chia partition; nhiều consumer group đọc độc lập |
| **Azure Event Grid** | Bộ định tuyến sự kiện theo nguồn, loại và điều kiện | Khi sự kiện xảy ra, gửi thông báo đến endpoint/subscriber phù hợp |
| **Azure Service Bus** | Broker thông điệp nghiệp vụ | Queue hoặc topic giữ message cho consumer xử lý và xác nhận |

| Tiêu chí | Event Hubs | Event Grid | Service Bus |
|---|---|---|---|
| Mục đích | Streaming / telemetry / event ingestion | Event routing / notification | Enterprise messaging / workflow |
| Đơn vị chính | Event trong partition | Event được route tới event subscription | Message trong queue hoặc topic subscription |
| Mô hình tiêu thụ | Consumer đọc theo offset/checkpoint | Push delivery hoặc pull theo khả năng resource/tier | Peek-Lock hoặc Receive-and-Delete |
| Replay | Có thể đọc lại trong retention bằng offset/checkpoint | Không phải event log dài hạn để replay tùy ý; cần nguồn lưu trữ riêng | Không phải stream log; message bị complete/xóa theo lifecycle |
| Thứ tự | Thứ tự trong một partition | Không bảo đảm thứ tự toàn cục; không thiết kế như ordered log | Có thể dùng sessions để xử lý theo nhóm có thứ tự |
| Fan-out | Consumer group độc lập đọc stream | Routing tới nhiều event subscription | Topic fan-out tới nhiều subscription |
| Dead-letter | Ứng dụng xử lý checkpoint/lỗi; không phải broker queue DLQ kiểu Service Bus | Có thể cấu hình dead-letter cho delivery thất bại | DLQ tích hợp cho queue/topic subscription |
| Filter | Consumer tự lọc stream hoặc dùng processor | Event subscription filter theo event type/subject/advanced filters | Subscription filters/rules trên topic |
| Giao dịch nghiệp vụ | Không phải broker command transaction | Không phải workflow transaction broker | Có transactions trong phạm vi được hỗ trợ của Service Bus |
| Phù hợp nhất | Dữ liệu lớn, liên tục, analytics, telemetry | Phản ứng với sự kiện từ nhiều nguồn | Command, task, integration message cần kiểm soát giao nhận |

**Không dịch máy móc:** Event Hubs không phải queue chỉ vì consumer nhận event; Event Grid không phải event store; Service Bus topic không phải stream log có thể đọc lại vô hạn. Mỗi dịch vụ có cách quản lý trạng thái và chi phí riêng.

## 4. Azure Event Hubs: ingest và xử lý event stream

### 4.1. Khi nào dùng Event Hubs?

Event Hubs phù hợp khi hệ thống cần nhận lượng lớn dữ liệu liên tục từ nhiều producer: telemetry thiết bị, log ứng dụng, clickstream, dữ liệu giao dịch phát sinh, event từ hệ thống vận hành hoặc dữ liệu cần chuyển sang pipeline phân tích.

Đặc điểm quan trọng:

- Namespace chứa một hoặc nhiều event hub.
- Mỗi event hub được chia thành **partition** để phân tán dữ liệu và tải xử lý.
- Producer có thể gửi event theo partition key hoặc để dịch vụ phân phối theo cơ chế phù hợp.
- Consumer group cung cấp view đọc độc lập cho một ứng dụng/nhóm consumer.
- Consumer theo dõi **offset** và lưu **checkpoint** để tiếp tục từ vị trí đã xử lý.
- Event có retention theo cấu hình/tier; consumer có thể đọc lại trong khoảng retention còn hiệu lực.
- Event Hubs hỗ trợ Azure Blob Storage/ADLS Capture để ghi stream sang storage cho xử lý batch/analytics theo cấu hình.
- Có endpoint tương thích giao thức Kafka cho nhiều kịch bản, nhưng không phải mọi tính năng Kafka đều tương đương hoàn toàn.

~~~mermaid
flowchart LR
    P1["IoT / application producer"] --> H["Event Hubs namespace"]
    P2["Services / logs"] --> H
    H --> A["Partition 0"]
    H --> B["Partition 1"]
    H --> C["Partition 2"]
    A --> CG1["Consumer group: analytics"]
    B --> CG1
    C --> CG1
    A --> CG2["Consumer group: fraud detection"]
    B --> CG2
    C --> CG2
    H -. "Capture (nếu bật)" .-> ST["Blob Storage / ADLS"]
~~~

Một consumer group không có nghĩa là mỗi instance đều nhận toàn bộ event. Các instance trong cùng consumer group thường phân chia partition ownership; nhiều consumer group khác nhau có thể đọc cùng stream độc lập, mỗi nhóm có offset/checkpoint riêng.

### 4.2. Partition, ordering và partition key

Event Hubs bảo đảm thứ tự theo **partition** trong phạm vi cách ghi và đọc của partition đó; không có thứ tự tổng thể giữa tất cả partition. Nếu các event liên quan cần xử lý theo thứ tự, producer phải dùng partition key ổn định (ví dụ `customerId` hoặc `orderId`) để định tuyến event cùng khóa vào cùng partition. Đổi partition count hoặc thay đổi cách chọn key có thể ảnh hưởng phân phối và thứ tự quan sát; không coi partition key là khóa transaction.

Partition count là quyết định thiết kế quan trọng:
- Quá ít partition có thể hạn chế concurrency và throughput.
- Quá nhiều partition có thể tăng chi phí/độ phức tạp và ảnh hưởng chiến lược consumer.
- Một key có lưu lượng quá lớn có thể tạo **hot partition**, trong khi các partition khác nhàn rỗi.
- Số consumer xử lý song song trong một consumer group bị ràng buộc bởi số partition đang sở hữu và cấu hình processor.

Không chọn partition count chỉ bằng số lượng instance Spring Boot. Hãy dự báo event rate, kích thước event, throughput cần thiết, số consumer group, độ trễ và khả năng mở rộng.

### 4.3. Consumer group, offset và checkpoint

**Offset** xác định vị trí event trong partition. **Checkpoint** là trạng thái tiến độ mà consumer lưu bền vững, thường dùng Blob Storage làm checkpoint store khi sử dụng Event Processor. Checkpoint quá thường xuyên có thể tăng I/O/chi phí; checkpoint quá thưa khiến nhiều event phải đọc và xử lý lại sau sự cố.

Event Processor Client giúp quản lý partition ownership, load balancing và checkpoint store. Khi một instance chết, instance khác có thể nhận partition sau quá trình cân bằng; ứng dụng phải chấp nhận khả năng **xử lý lại một đoạn event kể từ checkpoint gần nhất**. Do đó, consumer nên idempotent và có cơ chế ghi nhận event đã xử lý khi side effect quan trọng.

### 4.4. Event Hubs không thay thế queue nghiệp vụ

Event Hubs giữ event trong thời gian retention và consumer đọc theo offset. Nó không dùng mô hình “một message được lock, xử lý xong rồi complete” như Service Bus Peek-Lock. Nếu cần workflow với DLQ tích hợp, message settlement, sessions hoặc transaction broker, hãy đánh giá Service Bus.

## 5. Azure Event Grid: định tuyến sự kiện khi điều gì đó xảy ra

### 5.1. Khi nào dùng Event Grid?

Event Grid phù hợp để kết nối nguồn phát sinh event với các handler mà không buộc producer phải biết từng consumer. Ví dụ:
- Khi một blob được tạo, gọi function để xử lý ảnh.
- Khi resource cloud thay đổi, gửi event tới automation hoặc webhook.
- Khi hệ thống nghiệp vụ phát `OrderApproved`, route tới các handler cần phản ứng.
- Khi có event từ partner hoặc dịch vụ Azure, phân phối tới endpoint phù hợp.

Các thành phần khái niệm:
- **Event source/topic:** nơi phát hoặc tập hợp event.
- **Event subscription:** đăng ký nhận event, filter và định nghĩa endpoint đích.
- **Handler/destination:** Azure Function, webhook, queue, Event Hubs hoặc endpoint được hỗ trợ.
- **Filter:** lọc theo event type, subject prefix/suffix hoặc điều kiện dữ liệu được hỗ trợ.
- **Delivery policy:** retry, thời gian giữ event và dead-letter khi cấu hình.

~~~mermaid
flowchart LR
    S1["Blob Storage"] --> EG["Event Grid"]
    S2["Azure resource"] --> EG
    S3["Custom topic / app"] --> EG
    EG --> F["Filter: event type / subject"]
    F --> H1["Function: image processor"]
    F --> Q["Service Bus queue"]
    F --> W["Webhook: order handler"]
~~~

Event Grid giảm coupling giữa publisher và subscriber: producer phát event theo contract; subscription quyết định event nào đi tới đâu. Producer vẫn cần quản lý event schema, quyền publish, khả năng retry và lỗi publish.

### 5.2. Push, pull và delivery

Event Grid có nhiều mô hình resource/delivery theo loại topic và tier. **Push delivery** gửi event đến endpoint đã đăng ký; một số loại resource hỗ trợ **pull delivery** để subscriber chủ động nhận/ack theo mô hình dịch vụ. Cần chọn đúng loại Event Grid resource và tính năng được hỗ trợ, không mặc định mọi topic có cùng semantics.

Với push delivery, endpoint cần đáp ứng đúng giao thức, phản hồi thành công và xử lý validation khi đăng ký subscription. Event có thể được giao lại nếu endpoint không xác nhận thành công hoặc timeout; thứ tự toàn cục không được bảo đảm. Vì thế handler cần:
- Xử lý event theo ID ổn định và idempotency.
- Trả response thành công chỉ sau khi đã nhận trách nhiệm xử lý bền vững.
- Đưa tác vụ dài vào queue hoặc outbox/worker thay vì giữ HTTP webhook mở quá lâu.
- Cấu hình dead-letter destination và cảnh báo khi delivery thất bại kéo dài.
- Xác minh subscription validation handshake và authentication theo loại endpoint.

Không nên xử lý một event HTTP rồi trả 2xx trước khi lưu được công việc cần thực hiện, nếu sau đó tiến trình có thể chết và làm mất side effect. Một lựa chọn là ghi event vào database/outbox hoặc queue bền vững rồi trả thành công.

### 5.3. Event schema và CloudEvents

Event Grid có thể làm việc với **Event Grid schema** hoặc **CloudEvents 1.0** tùy resource/tích hợp. Một event thường có các thông tin:
- `id`: định danh event.
- `source`: nguồn phát.
- `type`: loại event.
- `subject`: đối tượng liên quan.
- `time`: thời điểm phát sinh.
- `data`: payload nghiệp vụ hoặc metadata.
- Phiên bản schema/content type theo giao thức.

CloudEvents giúp chuẩn hóa envelope giữa nhiều hệ thống; tuy vậy, payload trong `data` vẫn cần schema version, tương thích ngược và quy tắc xử lý. Không nhét secret, access token hoặc dữ liệu cá nhân không cần thiết vào event vì event có thể được phân phối tới nhiều consumer và lưu ở nhiều nơi.

### 5.4. Retry và dead-letter

Event Grid có chính sách retry/dead-letter phụ thuộc loại resource và cấu hình. Khi endpoint không phản hồi thành công, event có thể được gửi lại theo lịch retry; khi vượt giới hạn delivery hoặc hết TTL, event có thể bị dead-letter nếu destination được cấu hình và hoạt động. Không bật dead-letter đồng nghĩa event thất bại sẽ tự động được lưu vào nơi an toàn.

Dead-letter storage phải có quyền, lifecycle, alert và quy trình replay. Khi replay, giữ event ID gốc hoặc ghi nhận ID replay mới có liên hệ với event gốc để tránh xử lý trùng.

## 6. Azure Service Bus: messaging nghiệp vụ và workflow

### 6.1. Khi nào dùng Service Bus?

Service Bus phù hợp khi một hệ thống cần gửi **command hoặc message nghiệp vụ** cho worker xử lý đáng tin cậy:
- Xử lý đơn hàng, thanh toán, hóa đơn hoặc tác vụ nền.
- Queue để tách producer khỏi consumer và hấp thụ tải đột biến.
- Topic/subscription để fan-out cùng message tới nhiều consumer logic.
- Sessions để nhóm message có thứ tự theo một khóa nghiệp vụ.
- Dead-letter queue để cách ly message không xử lý được.
- Scheduled/deferred messages và transactions trong phạm vi được hỗ trợ.

Service Bus cung cấp semantics giao nhận và settlement phù hợp cho enterprise messaging. Nó không phải event log để nhiều consumer tự do đọc lại toàn bộ lịch sử theo offset như Event Hubs.

### 6.2. Queue và topic/subscription

~~~mermaid
flowchart LR
    P["Spring Boot producer"] --> T["Service Bus topic: order-events"]
    T --> S1["Subscription: billing"]
    T --> S2["Subscription: warehouse"]
    T --> S3["Subscription: notification"]
    S1 --> C1["Billing worker"]
    S2 --> C2["Warehouse worker"]
    S3 --> C3["Notification worker"]
    C1 -. "DLQ riêng" .-> D1["Dead-letter"]
    C2 -. "DLQ riêng" .-> D2["Dead-letter"]
~~~

- **Queue:** một luồng công việc được phân phối tới một consumer trong nhóm nhận; message được settlement để xóa hoặc đưa lại.
- **Topic:** publisher gửi một bản message vào topic; Service Bus phân phối bản sao logic tới các **subscription** phù hợp.
- **Subscription:** có thể đặt filter/rule để chỉ nhận một phần message; mỗi subscription có trạng thái và DLQ riêng.
- **Session:** nhóm message theo SessionId để xử lý theo thứ tự trong session và hỗ trợ trạng thái/lock theo phiên trong phạm vi dịch vụ.

Topic/subscription hữu ích khi nhiều bộ phận cần cùng một sự kiện nhưng vòng đời xử lý độc lập. Nếu chỉ cần một công việc được một worker xử lý, queue thường đơn giản hơn.

### 6.3. Peek-Lock và Receive-and-Delete

**Peek-Lock** là mô hình thường dùng cho xử lý an toàn:
1. Consumer nhận message và khóa tạm thời.
2. Consumer xử lý nghiệp vụ.
3. Nếu thành công, gọi **Complete** để settlement message.
4. Nếu thất bại có thể **Abandon** để giao lại, hoặc để lock hết hạn.
5. Message vượt điều kiện delivery/được dead-letter thủ công có thể vào DLQ.

Nếu consumer commit database xong nhưng Complete bị mất, broker có thể giao lại message. Consumer phải idempotent; broker lock không thay thế transaction với database.

**Receive-and-Delete** xóa message ngay khi broker giao cho consumer. Nó giảm một số round-trip nhưng nếu consumer chết trước khi xử lý, message có thể mất đối với luồng ứng dụng. Chỉ dùng khi chấp nhận semantics đó.

### 6.4. Sessions, duplicate detection và transactions

- **Sessions** hỗ trợ nhóm message cùng SessionId và xử lý tuần tự trong nhóm; không tạo thứ tự toàn cục giữa mọi session.
- **Duplicate detection** loại bỏ message có MessageId trùng trong phạm vi và cửa sổ được cấu hình. Đây không phải bảo đảm exactly-once end-to-end: consumer side effect, database và các hệ thống ngoài vẫn cần idempotency.
- **Transactions** hỗ trợ một số thao tác Service Bus trong phạm vi broker được công bố; không tự tạo distributed transaction atomic với SQL database, S3, HTTP API hoặc provider khác.
- **DLQ** chứa message không xử lý được để điều tra và replay có kiểm soát. DLQ không tự sửa poison message hoặc schema không hợp lệ.

Service Bus có các tier (ví dụ Basic, Standard, Premium) với tính năng và mô hình capacity/pricing khác nhau. Không phải mọi tính năng như topics, sessions, transactions, duplicate detection hay networking đều có ở mọi tier; phải đối chiếu bảng tính năng và SKU hiện tại trước khi thiết kế.

## 7. Chọn dịch vụ theo tình huống

| Yêu cầu | Lựa chọn ưu tiên | Lý do |
|---|---|---|
| Ingest hàng triệu telemetry events liên tục | **Event Hubs** | Partition, throughput và consumer group phục vụ stream processing |
| Nhiều consumer cần đọc lại dữ liệu trong retention | **Event Hubs** | Offset/checkpoint và consumer group độc lập |
| Blob vừa được tạo thì gọi image processor | **Event Grid** | Event routing từ resource tới handler |
| Resource Azure thay đổi thì kích hoạt automation | **Event Grid** | Event subscription và filter theo nguồn/loại |
| Gửi command xử lý hóa đơn, cần Complete/Abandon/DLQ | **Service Bus** | Queue và settlement semantics |
| Phân phối command tới nhiều nhóm consumer độc lập | **Service Bus topic/subscription** | Fan-out, filter và DLQ riêng theo subscription |
| Cần thứ tự message theo order ID | **Service Bus sessions** hoặc partition key Event Hubs tùy bài toán | Sessions cho workflow message; partition cho stream |
| Cần đọc lại toàn bộ luồng để tính analytics | **Event Hubs** | Retention và consumer offsets |
| Chỉ cần thông báo khi điều gì đó xảy ra, không cần lưu message nghiệp vụ lâu dài | **Event Grid** | Event routing, handler xử lý sự kiện |
| Cần transaction broker hoặc scheduled/deferred command | **Service Bus** | Tính năng messaging nghiệp vụ |

### 7.1. Cây quyết định

~~~mermaid
flowchart TD
    A["Bạn đang truyền loại dữ liệu nào?"] --> B{"Luồng liên tục, throughput lớn, cần replay theo offset?"}
    B -->|Có| EH["Event Hubs"]
    B -->|Không| C{"Một sự kiện xảy ra và cần route tới handler?"}
    C -->|Có| EG["Event Grid"]
    C -->|Không| D{"Cần queue/command, settlement, DLQ, sessions hoặc transaction?"}
    D -->|Có| SB["Service Bus"]
    D -->|Không| X["Xác định lại contract, delivery và retention"]
~~~

Nếu câu trả lời là “cần cả ba”, không nhất thiết phải chọn một. Ví dụ Event Hubs ingest telemetry, Event Grid thông báo blob đã được tạo, Service Bus điều phối command tạo báo cáo. Mỗi dịch vụ cần event contract, quyền, monitoring và failure handling riêng.

## 8. Thiết kế event contract dùng chung cho Spring Boot

Một event tốt nên mô tả **điều đã xảy ra**, không phụ thuộc cấu trúc database nội bộ:
- `eventId`: ID duy nhất và ổn định cho một event nghiệp vụ.
- `eventType`: loại event có version, ví dụ `com.example.orders.created.v1`.
- `source`: service/producer.
- `subject`: entity liên quan, ví dụ `orders/12345`.
- `occurredAt`: thời điểm nghiệp vụ xảy ra, không nhất thiết là lúc broker nhận.
- `correlationId` và `traceparent`: nối các bước trong một luồng phân tán.
- `schemaVersion`: phiên bản payload.
- `data`: các trường cần thiết cho consumer, tránh payload dư thừa.

Ví dụ payload:

~~~json
{
  "eventId": "evt-7f3a8e",
  "eventType": "com.example.orders.created.v1",
  "source": "orders-service",
  "subject": "orders/12345",
  "occurredAt": "2026-11-24T09:30:00Z",
  "correlationId": "req-91ac",
  "schemaVersion": 1,
  "data": {
    "orderId": "12345",
    "customerRef": "cust-204",
    "currency": "VND",
    "total": 450000
  }
}
~~~

Dữ liệu trên là ví dụ giả lập. Không đưa password, access token, connection string hoặc thông tin thẻ thanh toán vào message. Nếu consumer cần dữ liệu lớn, cân nhắc lưu object ở storage và gửi reference có quyền truy cập giới hạn; không dùng event như nơi chứa file lớn vượt giới hạn broker.

### 8.1. Schema evolution

Khi payload thay đổi:
- Thêm field optional có default hoặc quy tắc fallback để consumer cũ tiếp tục hoạt động.
- Không đổi nghĩa của field hiện có mà không tăng version.
- Không xóa field khi vẫn có consumer cũ.
- Kiểm tra producer/consumer tương thích ngược và xuôi theo chiến lược rollout.
- Quản lý schema registry hoặc contract tests nếu nhiều team cùng phát triển.
- Có kế hoạch cho message cũ còn nằm trong retention/queue sau khi ứng dụng đã nâng cấp.

Event Hubs stream retention có thể chứa event từ phiên bản trước; Service Bus queue/topic cũng có message chờ xử lý; Event Grid có thể retry event cũ. Consumer cần biết cách xử lý payload theo version trong cả ba trường hợp.

## 9. Tích hợp Spring Boot với Azure SDK

### 9.1. Chọn thư viện và phiên bản

Có thể dùng:
- **Azure SDK for Java** trực tiếp khi cần kiểm soát producer/consumer, checkpoint, processor, retry hoặc cấu hình nâng cao.
- **Spring Cloud Azure** để tận dụng Spring Boot auto-configuration, credential integration, Spring Messaging và listener abstraction khi phiên bản hỗ trợ dịch vụ cần dùng.
- **Spring Cloud Stream** với binder tương ứng khi kiến trúc muốn dùng abstraction binder và cần hiểu rõ semantics mà binder hỗ trợ.

Chọn **BOM Spring Cloud Azure tương thích với phiên bản Spring Boot**. Tên artifact, package, property và annotation thay đổi giữa các thế hệ thư viện. Không copy cấu hình từ một phiên bản major khác mà chưa kiểm tra compatibility matrix. Với tính năng quan trọng như sessions, manual settlement, checkpoint hoặc processor ownership, xác minh abstraction có expose đúng API cần thiết hay nên dùng SDK gốc.

### 9.2. Danh tính và cấu hình

Trên Azure, ưu tiên **Microsoft Entra ID** và workload identity:
- Local development có thể dùng credential developer đã đăng nhập và được kiểm soát.
- App Service/Functions/VM có thể dùng Managed Identity.
- AKS có thể dùng Workload Identity.
- CI/CD có thể dùng workload identity federation/service connection phù hợp.

Không hardcode SAS key hoặc connection string vào repository. Nếu dùng SAS, giới hạn resource, quyền và thời hạn; lưu trong secret manager, rotate và audit. Với Entra ID, cấp role đúng:
- Event Hubs: **Azure Event Hubs Data Sender** hoặc **Azure Event Hubs Data Receiver** theo producer/consumer.
- Service Bus: **Azure Service Bus Data Sender** hoặc **Azure Service Bus Data Receiver**.
- Event Grid: role publish tương ứng, ví dụ **EventGrid Data Sender** cho publisher ở scope phù hợp; handler cần cơ chế xác thực/authorization riêng theo endpoint.

Role quản lý namespace/resource không mặc nhiên cấp quyền data-plane. Cần xác minh principal runtime và scope được gán.

Ví dụ cấu hình không chứa secret:

~~~yaml
app:
  azure:
    event-hubs:
      namespace: orders-dev.servicebus.windows.net
      name: order-telemetry
    service-bus:
      namespace: orders-dev-messaging.servicebus.windows.net
      queue: orders-dev
    event-grid:
      endpoint: https://orders-dev-events.example.region-1.eventgrid.azure.net/api/events
~~~

Các khóa `app.azure.*` là cấu hình tự định nghĩa của ứng dụng, không phải property mặc định chung cho Spring Cloud Azure. Endpoint là giá trị minh họa; phải lấy endpoint thật từ resource đã triển khai. Không đưa key/token vào file YAML.

## 10. Ví dụ Event Hubs producer bằng Azure SDK

Ví dụ dưới đây gửi một event vào Event Hubs bằng **DefaultAzureCredential**. Runtime identity phải có role **Azure Event Hubs Data Sender** trên namespace hoặc scope phù hợp.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubProducerClient;

public class TelemetryPublisher {
    public void publish(
            String fullyQualifiedNamespace,
            String eventHubName,
            String jsonPayload) {

        EventHubProducerClient producer = new EventHubClientBuilder()
                .credential(
                        fullyQualifiedNamespace,
                        eventHubName,
                        new DefaultAzureCredentialBuilder().build())
                .buildProducerClient();

        try {
            EventDataBatch batch = producer.createBatch();
            if (!batch.tryAdd(new EventData(jsonPayload))) {
                throw new IllegalArgumentException(
                        "Event exceeds the available batch size");
            }
            producer.send(batch);
        } finally {
            producer.close();
        }
    }
}
~~~

Mã minh họa cần dependency Azure Identity và Azure Messaging Event Hubs tương thích. Trong ứng dụng production, nên tạo producer client như **Spring bean dùng lại**, thay vì tạo và đóng client trên từng request; thêm timeout, retry policy, telemetry và xử lý lỗi. Nếu batch không đủ chỗ cho event, có thể chia batch hoặc từ chối payload theo chính sách; không tăng vô hạn kích thước.

### 10.1. Consumer và checkpoint

Với stream processing, dùng **EventProcessorClient** để quản lý partition ownership và checkpoint qua checkpoint store phù hợp (thường là Blob Storage). Consumer group nên có tên riêng theo ứng dụng logic; các replica của cùng consumer group chia partition, còn analytics và fraud detection dùng consumer group riêng.

Luồng xử lý:
1. Nhận event cùng partition context.
2. Validate schema và event ID.
3. Thực hiện side effect idempotent hoặc lưu kết quả bền vững.
4. Checkpoint sau khi đã xử lý an toàn theo batch/interval đã chọn.
5. Nếu instance chết trước checkpoint, event từ checkpoint gần nhất có thể được xử lý lại.

Không checkpoint trước khi side effect bền vững, nếu không có thể mất xử lý. Checkpoint quá thường xuyên tăng chi phí và I/O; checkpoint quá thưa tăng số event cần replay. Nếu có side effect sang database, dùng deduplication/outbox phù hợp.

## 11. Ví dụ gửi message Service Bus bằng Azure SDK

Service Bus phù hợp cho command hoặc công việc cần settlement. Ví dụ producer dùng managed identity:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;

public class OrderCommandPublisher {
    public void send(
            String namespace,
            String queueName,
            String eventId,
            String payload) {

        ServiceBusSenderClient sender = new ServiceBusClientBuilder()
                .credential(
                        namespace,
                        new DefaultAzureCredentialBuilder().build())
                .sender()
                .queueName(queueName)
                .buildClient();

        try {
            ServiceBusMessage message = new ServiceBusMessage(payload)
                    .setMessageId(eventId)
                    .setContentType("application/json")
                    .setSubject("ReserveInventory");
            sender.sendMessage(message);
        } finally {
            sender.close();
        }
    }
}
~~~

Trong ứng dụng Spring Boot, tạo sender client dùng lại theo lifecycle bean, không khởi tạo mỗi lần gọi. `MessageId` ổn định hỗ trợ duplicate detection nếu namespace/queue được cấu hình tính năng tương ứng; consumer vẫn phải idempotent vì dedup có phạm vi/thời hạn và không bao trùm side effect ngoài broker.

### 11.1. Consumer và settlement

Có thể dùng **ServiceBusProcessorClient** để nhận message bất đồng bộ. Handler chỉ Complete sau khi xử lý nghiệp vụ và commit database thành công; khi gặp lỗi tạm thời, có thể abandon để broker giao lại theo policy. Với lỗi dữ liệu không thể phục hồi, dead-letter kèm reason/description đã loại bỏ dữ liệu nhạy cảm.

~~~java
import com.azure.messaging.servicebus.ServiceBusReceivedMessageContext;

void handleMessage(ServiceBusReceivedMessageContext context) {
    String body = context.getMessage().getBody().toString();

    // Validate và xử lý idempotent trong transaction database.
    processOrderCommand(body);

    // Chỉ settlement complete sau khi transaction đã commit.
    context.complete();
}
~~~

Đoạn code là **phác thảo handler**, cần được gọi từ callback của processor client và cấu hình processor ở chế độ Peek-Lock/manual settlement phù hợp phiên bản SDK. Nếu framework listener tự động complete sau callback, không gọi settlement thủ công trùng lặp. Không bắt exception rồi nuốt lỗi; nếu transaction thất bại, để policy xử lý retry/abandon hoặc dead-letter.

## 12. Event Grid và Spring Boot webhook

Event Grid thường đẩy event tới endpoint HTTP. Handler cần:
- Hoàn tất subscription validation handshake theo loại event/schema.
- Xác minh endpoint authentication; không coi URL khó đoán là cơ chế bảo mật.
- Parse đúng Event Grid schema hoặc CloudEvents 1.0 đã cấu hình.
- Dùng event ID để chống duplicate.
- Ghi công việc bền vững hoặc publish vào queue trước khi trả thành công nếu xử lý lâu.
- Giới hạn request body, validate schema và không tin dữ liệu từ event như dữ liệu đã được authorization.

Một endpoint Spring MVC minh họa cho **CloudEvents JSON** (DTO cần điều chỉnh theo schema và Jackson configuration thực tế):

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record CloudEventRequest(
        String specversion,
        String id,
        String source,
        String type,
        Instant time,
        String subject,
        Object data) {}

@RestController
@RequestMapping("/events")
class OrderEventController {

    @PostMapping
    ResponseEntity<Void> receive(
            @RequestBody List<CloudEventRequest> events) {

        for (CloudEventRequest event : events) {
            if (event.id() == null || event.type() == null) {
                return ResponseEntity.badRequest().build();
            }
            // Persist to inbox/queue with unique event ID.
            acceptForAsyncProcessing(event);
        }
        return ResponseEntity.ok().build();
    }

    private void acceptForAsyncProcessing(CloudEventRequest event) {
        // Store durably and deduplicate before acknowledging delivery.
    }
}
~~~

Đây là skeleton minh họa, không phải webhook production hoàn chỉnh. Cần triển khai subscription validation theo giao thức đã chọn; xác thực nguồn/endpoint, giới hạn schema, xử lý duplicate, transaction khi lưu inbox và trả response theo đúng delivery contract. Nếu handler không lưu bền vững được, nên trả lỗi phù hợp để Event Grid có thể retry theo policy.

## 13. Kết hợp ba dịch vụ trong một kiến trúc

Một hệ thống thương mại điện tử có thể dùng cả ba:
- **Event Grid** nhận thông báo `BlobCreated` và route tới function kiểm tra file hoặc đưa reference vào Service Bus.
- **Service Bus** nhận command `GenerateInvoice`, worker xử lý có lock/complete, retry và DLQ.
- **Event Hubs** nhận telemetry từ ứng dụng, gateway và worker để phân tích throughput, latency, hành vi người dùng.

~~~mermaid
flowchart TD
    B["Blob Storage: invoice uploaded"] --> EG["Event Grid"]
    EG --> Q["Service Bus queue: validate invoice"]
    Q --> W["Spring Boot invoice worker"]
    W --> DB["Managed database"]
    APP["Spring Boot services"] --> EH["Event Hubs: telemetry stream"]
    W --> EH
    EH --> AN["Stream analytics / data platform"]
    Q -. "Poison messages" .-> DLQ["Service Bus DLQ"]
~~~

Không nên gửi mọi event nghiệp vụ vào cả ba dịch vụ theo kiểu nhân bản tùy tiện. Mỗi luồng cần chủ sở hữu, mục tiêu, retention, schema, quyền, cost center và quy trình xử lý lỗi. Nếu Event Grid route vào Service Bus, producer/handler phải xác định rõ event nào được gửi và cách tránh gửi trùng.

## 14. Bảo mật, network và phân quyền

### 14.1. RBAC và danh tính

Dùng Managed Identity hoặc Workload Identity khi có thể:
- Producer Event Hubs: **Azure Event Hubs Data Sender**.
- Consumer Event Hubs: **Azure Event Hubs Data Receiver**.
- Producer Service Bus: **Azure Service Bus Data Sender**.
- Consumer Service Bus: **Azure Service Bus Data Receiver**.
- Publisher Event Grid: **EventGrid Data Sender** hoặc role data tương ứng theo resource.
- Webhook/handler: xác thực riêng bằng cơ chế được hỗ trợ, ví dụ Microsoft Entra/managed identity cho destination tương thích, hoặc endpoint authentication phù hợp.

Role gán ở namespace có thể bao phủ nhiều entity; gán ở scope nhỏ hơn nếu dịch vụ và role hỗ trợ. Không cấp Contributor/Owner chỉ để gửi hoặc nhận message. Quyền quản lý resource khác quyền data-plane; xác minh đúng principal runtime thay vì credential local.

### 14.2. SAS, connection string và secret

SAS/connection string có thể cần cho một số kịch bản, nhưng phải:
- Giới hạn namespace/entity, quyền Send/Listen/Manage và thời hạn.
- Không dùng quyền **Manage** cho workload chỉ cần Send hoặc Listen.
- Lưu trong Azure Key Vault hoặc secret manager phù hợp; rotate và thu hồi khi nghi ngờ lộ.
- Không log connection string, SAS token hoặc raw message payload nhạy cảm.
- Ưu tiên Entra ID khi SDK, service và môi trường triển khai hỗ trợ.

### 14.3. Network

Event Hubs, Service Bus và Event Grid có khả năng network controls tùy resource/tier, như firewall, private endpoint/private link hoặc kết nối mạng được hỗ trợ. Cần kiểm tra DNS, route, TLS, ingress/egress và khả năng endpoint từ runtime. Private endpoint không tự cấp quyền; RBAC và authentication vẫn phải đúng.

## 15. Reliability: retry, duplicate, ordering và dead-letter

| Khía cạnh | Event Hubs | Event Grid | Service Bus |
|---|---|---|---|
| Retry | Consumer tự quản lý retry/checkpoint; producer SDK có retry policy | Delivery retry theo policy của resource | Redelivery khi abandon/lock expiry; retry trong consumer |
| Duplicate | Consumer có thể đọc lại từ checkpoint gần nhất | Có thể giao event nhiều lần | Message có thể giao lại; duplicate detection là tùy chọn |
| Ordering | Trong một partition theo semantics của stream | Không bảo đảm thứ tự toàn cục | Sessions hỗ trợ thứ tự trong một session |
| Replay | Đọc lại theo offset trong retention | Cần nguồn lưu trữ riêng nếu muốn replay lịch sử dài hạn | Không phải log replay; message lifecycle qua settlement |
| Poison event | Log/quarantine/checkpoint policy của ứng dụng | Dead-letter nếu cấu hình | DLQ tích hợp |
| Backpressure | Consumer throughput, partition ownership, checkpoint | Endpoint response, delivery retry, pull model nếu hỗ trợ | Prefetch, max concurrent calls, lock duration, queue depth |

Các nguyên tắc:
- Tạo **eventId/messageId** ổn định từ nghiệp vụ, không chỉ dựa vào delivery ID.
- Consumer idempotent bằng inbox/processed-event table hoặc conditional update.
- Chỉ checkpoint Event Hubs sau side effect bền vững theo chiến lược xử lý.
- Chỉ Complete Service Bus sau transaction nghiệp vụ.
- Event Grid webhook nên lưu bền vững trước khi trả 2xx cho tác vụ cần xử lý sau.
- Retry có giới hạn, backoff/jitter, deadline và phân loại lỗi; không retry 401/403/schema error vô hạn.
- Theo dõi DLQ/dead-letter storage và quy trình replay có phê duyệt.

## 16. Quan sát và chi phí

### 16.1. Metrics cần theo dõi

**Event Hubs**
- Incoming messages/bytes và outgoing messages/bytes.
- Throttled requests, server errors, active connections.
- Consumer lag/độ trễ xử lý theo offset và thời gian event.
- Checkpoint failures, partition ownership rebalance, Capture backlog/storage.
- Số partition và mức sử dụng throughput/capacity theo tier.

**Event Grid**
- Delivery success/failure, delivery attempts, unmatched events.
- Dead-lettered events và dung lượng destination.
- Publish errors, latency và endpoint availability.
- Số event theo topic/subscription, filter match và retry.

**Service Bus**
- Active messages, dead-lettered messages, scheduled messages.
- Incoming/outgoing requests, server errors, throttled requests.
- Queue/topic/subscription size, oldest message age.
- Lock lost/abandoned/expired, delivery count và DLQ growth.
- Messaging Units/CPU/memory với tier tương ứng.

Đặt cảnh báo theo **độ trễ và tuổi backlog**, không chỉ số lượng message. Một queue có 100 message nhưng message cũ nhất đã chờ một giờ có thể nghiêm trọng hơn queue 10.000 message mới phát sinh trong vài giây.

### 16.2. Chi phí và capacity

- **Event Hubs:** pricing phụ thuộc tier/capacity model, throughput/capacity units, ingress/processing và retention hoặc tính năng Capture theo lựa chọn.
- **Event Grid:** tính phí theo operations/events/delivery hoặc mô hình resource/tier cụ thể; retry và fan-out có thể làm tăng lượng delivery.
- **Service Bus:** phụ thuộc tier, messaging operations, capacity/messaging units và tính năng networking/geo-disaster recovery theo SKU.

Không có một con số giá cố định áp dụng mọi Region và thời điểm. Đọc bảng giá chính thức theo **SKU, Region, volume, kích thước payload, retention, network và số subscription/consumer**. Tính cả chi phí Blob Storage dùng checkpoint hoặc Capture, log/monitoring, private endpoint và data transfer.

## 17. Kiểm thử tích hợp

Một bộ test có thể chia thành các lớp:

1. **Contract/unit test:** kiểm tra schema event, version, validation, partition key, message properties và business idempotency bằng fixture.
2. **Component test:** kiểm tra adapter/serialization/retry logic bằng mock hoặc test double; không giả định mock chứng minh semantics của Azure.
3. **Cloud integration test:** dùng namespace, topic, queue, subscription và storage riêng cho test; kiểm tra credential, RBAC, endpoint và delivery thật.
4. **Failure test:** mất kết nối, endpoint timeout, duplicate, consumer crash trước ACK/checkpoint, poison message, lock expiry, quota/throttling.
5. **Recovery test:** kiểm tra DLQ, replay, checkpoint resume, consumer rebalance và cleanup.
6. **Security test:** xác minh identity dev không thể publish/consume vào resource production; secret không xuất hiện trong log.

### 17.1. Ma trận test theo dịch vụ

| Kịch bản | Event Hubs | Event Grid | Service Bus |
|---|---|---|---|
| Gửi event thành công | Producer send và consumer nhận | Publish và endpoint nhận | Send và receiver nhận |
| Consumer/endpoint lỗi | Checkpoint không tiến sai; resume có thể replay | Retry và dead-letter theo cấu hình | Abandon/lock expiry và redelivery |
| Event trùng | Dedup theo eventId ở consumer | Handler idempotent | MessageId/dedup tùy cấu hình và DB dedup |
| Scale ngang | Partition ownership và rebalance | Nhiều endpoint/worker theo delivery model | Nhiều receiver và lock contention |
| Thứ tự | Cùng partition key | Không giả định global order | SessionId và session receiver |
| Quá tải | Throughput, throttling, lag | Delivery failure/endpoint backpressure | Queue depth, lock, throttling, tier |
| Replay | Offset/retention/checkpoint | Nguồn lưu event riêng hoặc replay do ứng dụng | Replay qua DLQ/resubmit có kiểm soát |

Không dùng namespace production để thử message lỗi, xóa topic hoặc kiểm tra quota bằng cách cố tình gây tải. Tạo resource test có TTL/lifecycle và chi phí được giới hạn.

## 18. Các ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| Event Hubs là queue, mỗi event chỉ tới một consumer | Nhiều consumer group có thể đọc độc lập; các instance cùng group chia partition |
| Event Grid lưu event để replay như event store | Event Grid chủ yếu route và deliver; muốn lưu/replay dài hạn cần storage/stream riêng |
| Service Bus topic là một stream log | Topic phân phối message tới subscription có lifecycle/settlement riêng |
| Event Grid bảo đảm thứ tự event | Không thiết kế dựa trên thứ tự toàn cục; handler cần version/state transition |
| SQS/SB/PubSub hoặc Event Grid giao đúng một lần | Duplicate/redelivery vẫn có thể xảy ra tùy semantics; business idempotency cần thiết |
| Event Hubs checkpoint trước khi xử lý giúp nhanh hơn | Có thể bỏ qua event nếu xử lý thất bại sau checkpoint |
| Service Bus Complete rồi mới commit DB là an toàn | Có thể mất message nếu DB commit thất bại sau Complete |
| Duplicate detection thay thế idempotency | Dedup broker có phạm vi/thời hạn; side effect ngoài broker vẫn cần chống trùng |
| Dùng Managed Identity là không cần RBAC | Identity phải được gán role data-plane phù hợp |
| Private endpoint bảo đảm mọi request hợp lệ | Network riêng không thay authentication, authorization hoặc schema validation |
| Một producer chỉ có thể gửi một kiểu event | Có thể gửi nhiều event type nhưng cần contract, routing và quyền rõ ràng |
| Cả ba dịch vụ đều tính phí theo số message giống nhau | Mỗi dịch vụ có meter, tier, throughput và delivery model riêng |

## 19. Checklist chọn và triển khai

Trước khi quyết định dịch vụ, trả lời:

- **Mục tiêu:** stream liên tục, event routing hay command/work queue?
- **Volume:** event/giây, payload size, burst, retention và throughput cần thiết?
- **Consumer:** một nhóm worker hay nhiều consumer độc lập? Có cần fan-out/filter?
- **Delivery:** at-least-once, replay, checkpoint, ACK/Complete hay pull/push?
- **Ordering:** thứ tự toàn cục, theo partition key hay theo session?
- **Failure:** duplicate, retry, poison event, DLQ, checkpoint, replay và idempotency được xử lý thế nào?
- **Security:** workload identity, RBAC data role, SAS/secret, private networking và cross-environment isolation?
- **Operations:** metrics, alert, backlog, DLQ, consumer lag, quota và runbook?
- **Cost:** tier, capacity, operation/delivery, retention, Capture/storage, network và monitoring?
- **Spring compatibility:** BOM, starter/SDK, auto-configuration, lifecycle client và settlement semantics đúng version?

## 20. Tổng kết

**Event Hubs** là lựa chọn cho event streaming throughput cao, partition, consumer group và replay theo offset trong retention. **Event Grid** là lựa chọn cho event routing, filter và thông báo khi một sự kiện xảy ra. **Service Bus** là lựa chọn cho enterprise messaging, queue/topic, settlement, sessions, retry và dead-letter. Ba dịch vụ có thể phối hợp nhưng không thay thế lẫn nhau.

Khi tích hợp Spring Boot, hãy chọn dịch vụ từ **contract và cách consumer phải xử lý**, sau đó mới chọn starter/SDK. Bảo vệ từng luồng bằng managed identity và RBAC, thiết kế schema/event ID, idempotency, checkpoint hoặc ACK đúng thời điểm, theo dõi lag/backlog/DLQ và kiểm thử lỗi trên resource riêng. Cách tiếp cận này giúp ứng dụng tận dụng đúng khả năng của Azure và giữ được tính đúng đắn khi hệ thống mở rộng hoặc một thành phần gặp sự cố.

