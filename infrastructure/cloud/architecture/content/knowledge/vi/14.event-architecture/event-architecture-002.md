# Hàng đợi, publish–subscribe, event bus và luồng sự kiện

Trong ứng dụng cloud, các thành phần thường cần phối hợp mà không nhất thiết phải gọi nhau trực tiếp trong cùng một request. Khi khách hàng đặt phòng, Booking Service có thể phát thông báo để Payment xử lý, Notification gửi email, Search cập nhật chỉ mục và Analytics ghi nhận hành vi. Nếu Booking phải chờ từng hệ thống hoàn tất, độ trễ và mức độ phụ thuộc sẽ tăng; nếu gửi thông báo nhưng không có cơ chế lưu giữ và giao lại, một sự cố ngắn có thể làm mất công việc.

Các công nghệ **queue**, **publish–subscribe (pub/sub)**, **event bus** và **event stream** giải quyết những phần khác nhau của bài toán trao đổi thông điệp. Chúng giúp tách producer khỏi consumer, hấp thụ biến động tải, phân phối sự kiện và xây dựng luồng xử lý bất đồng bộ. Tuy nhiên, chúng có semantics khác nhau về giao nhận, thứ tự, lưu trữ, phát lại và khả năng mở rộng. Chọn sai mô hình có thể gây mất sự kiện, xử lý trùng, backlog kéo dài, dữ liệu sai lệch hoặc chi phí vận hành không cần thiết.

Bài học thuộc chương **Kiến trúc sự kiện** của module **CLOUD_ARCHITECTURE**. Mục tiêu là lựa chọn cơ chế truyền sự kiện phù hợp với yêu cầu nghiệp vụ, sau đó thiết kế tính đúng đắn, bảo mật, độ tin cậy, hiệu năng, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt message queue, pub/sub, event bus và event streaming theo mô hình giao nhận và lưu giữ dữ liệu.
2. Giải thích vai trò của producer, consumer, broker, topic, subscription, partition, offset và consumer group.
3. Chọn cơ chế giao nhận phù hợp với yêu cầu một consumer, nhiều consumer, fan-out, buffering, replay và xử lý liên tục.
4. Thiết kế consumer idempotent, xử lý duplicate, ordering, retry và dead-letter queue.
5. Phân biệt command với event, định nghĩa event contract và quản lý phiên bản schema.
6. Thiết kế luồng sự kiện có bảo mật, quan sát, giới hạn tải, phục hồi và kiểm soát chi phí.
7. Đánh giá các đánh đổi về độ trễ, throughput, durability, consistency và khả năng vận hành trong kiến trúc cloud.

## 2. Bốn mô hình thường gặp

### 2.1. Message queue: giao công việc cho consumer

Queue là nơi producer gửi thông điệp để một hoặc nhiều consumer xử lý. Trong mô hình competing consumers phổ biến, mỗi message được một consumer trong nhóm nhận để xử lý; broker hoặc giao thức queue quản lý trạng thái giao nhận và có thể làm message sẵn sàng lại nếu consumer không xác nhận theo semantics của dịch vụ.

~~~mermaid
flowchart LR
    P[Producer] --> Q[(Message Queue)]
    Q --> C1[Consumer 1]
    Q --> C2[Consumer 2]
    Q --> C3[Consumer 3]
~~~

Ví dụ: Booking Service gửi yêu cầu tạo hóa đơn vào queue. Một worker nhận message, gọi dịch vụ hóa đơn, lưu kết quả rồi xác nhận message đã xử lý. Những worker khác nhận các message khác khi có năng lực.

Queue phù hợp khi:

- Công việc có thể xử lý bất đồng bộ.
- Cần hấp thụ spike và điều chỉnh tốc độ consumer.
- Mỗi message là một đơn vị công việc cần hoàn tất.
- Producer không cần biết cụ thể worker nào sẽ thực hiện.

Queue không mặc nhiên phát cùng một message tới mọi consumer. Nếu cần nhiều hệ thống cùng nhận một sự kiện, cần mô hình pub/sub hoặc nhiều subscription/queue được cấu hình để mỗi consumer có bản giao riêng.

### 2.2. Publish–subscribe: một sự kiện, nhiều subscriber

Trong pub/sub, publisher gửi sự kiện tới một topic hoặc kênh; broker phân phối bản giao tới những subscriber đã đăng ký. Mỗi subscriber có thể xử lý độc lập, với tốc độ riêng và cơ chế retry riêng theo khả năng của nền tảng.

~~~mermaid
flowchart LR
    P[Publisher] --> T((Topic))
    T --> S1[Subscription A]
    T --> S2[Subscription B]
    T --> S3[Subscription C]
    S1 --> A[Notification]
    S2 --> B[Analytics]
    S3 --> C[Search projection]
~~~

Ví dụ: sau khi một booking được xác nhận, Booking Service phát BookingConfirmed. Notification gửi email, Analytics ghi nhận conversion và Search cập nhật projection. Booking Service không cần gọi từng hệ thống.

Pub/sub phù hợp khi:

- Một sự kiện cần kích hoạt nhiều consumer.
- Consumer cần scale hoặc triển khai độc lập.
- Publisher không cần biết danh sách cụ thể các subscriber.
- Có nhu cầu tách biệt quyền nhận, retry và backlog của từng nhóm consumer.

Pub/sub vẫn cần quy định rõ subscriber mới có nhận được sự kiện cũ hay chỉ sự kiện từ lúc đăng ký; điều này tùy broker, retention và loại subscription.

### 2.3. Event bus: định tuyến sự kiện theo quy tắc

Event bus là một lớp nhận sự kiện và định tuyến đến target theo rule. Rule có thể dựa trên nguồn, loại event, thuộc tính hoặc pattern trong payload. Nó thường được sử dụng để kết nối các dịch vụ và ứng dụng theo event-driven architecture.

~~~mermaid
flowchart LR
    A[Booking Service] --> BUS[(Event Bus)]
    B[Payment Service] --> BUS
    C[Inventory Service] --> BUS
    BUS -->|BookingConfirmed| N[Notification]
    BUS -->|PaymentFailed| R[Reconciliation]
    BUS -->|InventoryChanged| S[Search Indexer]
~~~

Event bus phù hợp khi nhiều nguồn phát các loại event khác nhau và cần routing tới các target theo chính sách. Một bus có thể hỗ trợ nhiều rule và target, nhưng thường không nên được coi là kho lưu trữ sự kiện dài hạn hoặc nền tảng replay tùy ý nếu sản phẩm không cung cấp các khả năng đó.

### 2.4. Event stream: chuỗi sự kiện có thể đọc theo vị trí

Event streaming xử lý sự kiện như một luồng dữ liệu liên tục được ghi vào log/stream có thứ tự trong phạm vi nhất định, thường là partition. Consumer đọc sự kiện theo offset hoặc cursor; nhiều consumer group có thể đọc cùng luồng độc lập. Retention cho phép consumer đọc lại dữ liệu trong khoảng thời gian được cấu hình.

~~~mermaid
flowchart LR
    P[Producers] --> K[(Stream / Topic)]
    K --> PG1[Partition 0]
    K --> PG2[Partition 1]
    K --> PG3[Partition 2]
    PG1 --> CG1[Consumer Group A]
    PG2 --> CG1
    PG3 --> CG1
    PG1 --> CG2[Consumer Group B]
    PG2 --> CG2
    PG3 --> CG2
~~~

Ví dụ: hệ thống ghi event clickstream, thay đổi giá và trạng thái booking vào stream. Consumer phân tích dữ liệu gần thời gian thực; consumer khác xây dựng kho phân tích. Mỗi nhóm tiến triển offset riêng, có thể đọc lại khi cần tái tạo kết quả trong giới hạn retention.

Streaming phù hợp khi:

- Dữ liệu phát sinh liên tục và thông lượng lớn.
- Cần nhiều consumer group đọc cùng dữ liệu độc lập.
- Cần xử lý theo thứ tự trong phạm vi partition.
- Cần replay/reprocess một khoảng dữ liệu.
- Cần tích hợp xử lý luồng, analytics hoặc materialized view.

Stream không tự đảm bảo mọi consumer nhìn thấy thứ tự toàn cục; thứ tự thường chỉ được bảo đảm trong partition hoặc phạm vi do nền tảng định nghĩa.

## 3. So sánh queue, pub/sub, event bus và stream

| Tiêu chí | Queue | Pub/sub | Event bus | Event stream |
|---|---|---|---|---|
| Mục tiêu chính | Phân phối công việc | Phát một sự kiện tới nhiều subscriber | Định tuyến event theo rule | Ghi và đọc chuỗi sự kiện liên tục |
| Mô hình consumer | Competing consumers thường gặp | Nhiều subscription độc lập | Nhiều target theo rule | Nhiều consumer group |
| Lưu giữ | Theo retention/visibility/dead-letter policy | Tùy broker/subscription | Tùy dịch vụ; thường không phải kho replay dài hạn mặc định | Retention theo thời gian hoặc dung lượng |
| Replay | Phụ thuộc dịch vụ và bản sao message | Tùy subscription và retention | Có thể hạn chế; cần xem khả năng archive/replay | Thường hỗ trợ đọc lại theo offset trong retention |
| Ordering | Có thể FIFO hoặc theo nhóm khóa tùy loại queue | Tùy broker và subscription | Không nên giả định thứ tự toàn cục | Thứ tự trong partition |
| Consumer scaling | Nhiều worker cùng lấy message | Mỗi subscription scale độc lập | Target scale theo cơ chế dịch vụ | Consumer group chia partition |
| Use case | Job nền, xử lý tác vụ | Notification, fan-out | Integration giữa service | Clickstream, audit/event pipeline, analytics |

**Tên gọi không hoàn toàn đồng nhất giữa các nhà cung cấp.** Một sản phẩm pub/sub có thể lưu message và cho phép replay; một dịch vụ event bus có thể hỗ trợ archive; một queue có thể hỗ trợ fan-out qua subscription. Hãy so sánh semantics và giới hạn cụ thể, không chỉ dựa vào tên dịch vụ.

## 4. Thành phần trong kiến trúc truyền sự kiện

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Producer / publisher** | Tạo message hoặc event | Booking Service phát BookingConfirmed |
| **Broker** | Nhận, lưu/đệm và phân phối thông điệp | Managed queue, event bus hoặc streaming cluster |
| **Queue / topic / stream** | Đích logic nhận message/event | booking-events, invoice-jobs |
| **Subscription** | Quy định một consumer hoặc nhóm consumer nhận bản giao | Notification subscription |
| **Consumer / subscriber** | Nhận và xử lý message | Email worker |
| **Partition** | Chia luồng để mở rộng và xác định phạm vi ordering | Partition theo bookingId |
| **Offset / cursor** | Vị trí consumer đã đọc hoặc xác nhận trong stream | Offset 1.250 |
| **Consumer group** | Nhóm consumer cùng chia việc đọc partition | Search indexer group |
| **DLQ (dead-letter queue)** | Giữ message không thể xử lý sau policy retry | booking-events-dlq |
| **Schema registry / contract store** | Quản lý schema và phiên bản event | BookingConfirmed v2 |

Một kiến trúc đơn giản:

~~~mermaid
flowchart TB
    APP[Application services] --> PUB[Producer client]
    PUB --> BROKER[(Broker / Topic)]
    BROKER --> SUB[Subscription / Consumer group]
    SUB --> WORKER[Worker / Function]
    WORKER --> STORE[(Consumer data store)]
    WORKER -->|Retryable failure| RETRY[Retry policy / delayed queue]
    RETRY --> BROKER
    WORKER -->|Poison message| DLQ[(Dead-letter queue)]
    DLQ --> OPS[Alert + controlled redrive]
~~~

## 5. Message, command và event

### 5.1. Message là khái niệm bao quát

Message là đơn vị dữ liệu được gửi qua một cơ chế giao tiếp. Nó có thể là command, event, request, response hoặc job. Nội dung message không tự quyết định semantics; producer và consumer phải thống nhất ý nghĩa.

### 5.2. Command yêu cầu hành động

Command mô tả việc một consumer được yêu cầu thực hiện, thường hướng đến một owner cụ thể.

Ví dụ: ReserveAvailability, GenerateInvoice, SendEmail. Consumer có thể chấp nhận hoặc từ chối command sau khi kiểm tra quy tắc.

### 5.3. Event thông báo sự thật đã xảy ra

Event mô tả một sự kiện nghiệp vụ đã xảy ra, thường đặt tên ở thì quá khứ:

- BookingConfirmed
- PaymentAuthorized
- CustomerProfileUpdated
- InventoryReleased

Consumer phản ứng với event nhưng không được hiểu event như một lệnh buộc nó thực hiện thay đổi bất kỳ. BookingConfirmed có nghĩa booking đã được owner xác nhận; BookingConfirmationRequested chỉ là yêu cầu cần xử lý.

### 5.4. Envelope event mẫu

~~~json
{
  "eventId": "evt_01JXY99",
  "eventType": "BookingConfirmed",
  "eventVersion": 1,
  "occurredAt": "2026-12-01T09:16:22Z",
  "producer": "booking-service",
  "tenantId": "tenant_7",
  "correlationId": "req_548",
  "data": {
    "bookingId": "booking_913",
    "listingId": "listing_42",
    "checkIn": "2026-12-10",
    "checkOut": "2026-12-12"
  }
}
~~~

Event contract cần quy định:

- **eventId:** định danh duy nhất cho một event logical, hỗ trợ deduplication.
- **eventType / eventVersion:** xác định loại và schema version.
- **occurredAt:** thời điểm nghiệp vụ xảy ra, có timezone rõ ràng; khác thời điểm publish hoặc consume.
- **producer:** hệ thống phát event.
- **tenantId:** phạm vi dữ liệu; consumer vẫn phải xác thực quyền và nguồn gốc.
- **correlationId:** liên kết các bước cùng một luồng nghiệp vụ.
- **data:** chỉ chứa các trường consumer thực sự cần.

Không nên phát toàn bộ database record lên topic. Payload quá lớn và chứa dữ liệu không cần thiết sẽ làm tăng chi phí, coupling và nguy cơ lộ thông tin.

## 6. Delivery semantics: at-most-once, at-least-once và exactly-once

### 6.1. At-most-once

Thông điệp được giao tối đa một lần theo semantics của cơ chế. Nếu lỗi xảy ra ở thời điểm không thuận lợi, message có thể bị mất hoặc không được xử lý. Mô hình này có thể chấp nhận cho dữ liệu tạm thời, telemetry không trọng yếu hoặc trường hợp mất một số bản tin được phép.

### 6.2. At-least-once

Hệ thống cố gắng giao message ít nhất một lần. Nếu consumer xử lý thành công nhưng acknowledgement bị mất, broker có thể giao lại. Đây là semantics phổ biến ở queue và một số hệ thống event.

Consumer phải chịu được duplicate. Ví dụ, cùng BookingConfirmed được giao hai lần không nên gửi hai hóa đơn hoặc trừ tiền hai lần.

### 6.3. Exactly-once

Một số hệ thống streaming/broker có cơ chế transaction hoặc exactly-once trong phạm vi cụ thể, chẳng hạn giữa thao tác đọc và ghi trong cùng nền tảng. Điều này **không tự động bảo đảm exactly-once end-to-end** khi consumer gọi API thanh toán, ghi database khác hoặc gửi email.

Thiết kế thực tế thường kết hợp:

1. Delivery có thể lặp.
2. Event có định danh ổn định.
3. Consumer lưu dấu đã xử lý.
4. Side effect idempotent.
5. Đối soát trạng thái khi kết quả chưa xác định.

### 6.4. Idempotent consumer

Consumer có thể dùng bảng inbox để ghi nhận event đã xử lý trong cùng transaction với thay đổi dữ liệu:

~~~sql
BEGIN;

INSERT INTO processed_events(event_id, processed_at)
VALUES ('evt_01JXY99', CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;

-- Chỉ thực hiện thay đổi nghiệp vụ nếu bản ghi processed_events
-- được thêm mới trong transaction này.
-- Nếu event đã tồn tại, bỏ qua side effect lặp.

COMMIT;
~~~

Đoạn SQL chỉ minh họa ý tưởng; cú pháp và cách lấy số dòng ảnh hưởng tùy database. Đối với side effect bên ngoài như gửi email hoặc gọi payment, transaction database cục bộ không thể tự bao trùm API đó. Cần idempotency key của provider, outbox/inbox, trạng thái trung gian hoặc quy trình đối soát.

## 7. Acknowledgement, visibility timeout và offset

### 7.1. Acknowledgement trong queue

Một số queue dùng cơ chế consumer nhận message rồi xác nhận xóa/hoàn tất sau khi xử lý. Nếu consumer chết hoặc không xác nhận trước thời hạn, message có thể trở lại trạng thái sẵn sàng để giao cho consumer khác.

**Visibility timeout** là khoảng thời gian message tạm ẩn đối với consumer khác sau khi được nhận, ở những dịch vụ hỗ trợ mô hình này. Nếu xử lý lâu hơn thời hạn mà không gia hạn, message có thể bị giao trùng khi consumer đầu vẫn đang làm việc.

Vì vậy:

- Đặt visibility timeout phù hợp với p95/p99 processing time và deadline.
- Gia hạn khi công việc hợp lệ cần thời gian dài, nếu dịch vụ hỗ trợ.
- Chỉ acknowledge sau khi side effect cần thiết đã commit theo quy tắc.
- Đảm bảo handler idempotent vì duplicate vẫn có thể xảy ra.

### 7.2. Offset trong stream

Trong streaming, consumer group thường theo dõi offset/cursor. Consumer đọc từ vị trí tiếp theo và commit offset theo semantics của client/broker. Commit offset trước khi xử lý xong có thể làm mất khả năng xử lý lại; chỉ commit sau khi xử lý có thể khiến record được đọc lại nếu consumer crash.

Một cách tiếp cận phổ biến là xử lý idempotent rồi commit offset sau khi kết quả đã được ghi bền vững. Khi thao tác đọc và ghi không nằm trong cùng transaction, vẫn có cửa sổ lỗi cần được xử lý.

### 7.3. Thứ tự xử lý

Queue FIFO hoặc stream partition có thể cung cấp ordering trong phạm vi được định nghĩa. Tuy nhiên, nhiều consumer song song, retry và partition khác nhau có thể làm thứ tự hoàn tất khác với thứ tự publish.

Nếu nghiệp vụ cần thứ tự theo bookingId, có thể dùng bookingId làm message group/partition key theo khả năng broker. Khi đó các event cùng key có cơ hội được xử lý theo thứ tự trong một partition/group, nhưng một consumer xử lý chậm có thể giới hạn throughput của key đó.

Không dựa duy nhất vào timestamp để sắp thứ tự nghiệp vụ khi đồng hồ các máy có thể lệch hoặc event đến muộn. Có thể cần aggregate version/sequence do service owner cấp.

## 8. Retry, dead-letter queue và poison message

### 8.1. Retry có kiểm soát

Lỗi tạm thời như network reset, 429 hoặc 503 có thể retry. Lỗi không thể khắc phục bằng chờ như schema không hợp lệ, thiếu quyền hoặc dữ liệu sai nên được xử lý theo nhánh khác.

Một chính sách retry thường cần:

- Phân loại retryable và non-retryable.
- Giới hạn số lần retry hoặc tổng thời gian.
- Exponential backoff và jitter.
- Giới hạn concurrency để không làm downstream quá tải.
- Metric retry count, age và tỷ lệ thành công sau retry.

Retry vô hạn có thể giữ message mãi trong hệ thống, tạo backlog và chi phí lớn.

### 8.2. Poison message

Poison message là message liên tục thất bại do nội dung hoặc điều kiện xử lý không thể tự phục hồi. Ví dụ consumer không parse được event version mới, dữ liệu thiếu trường bắt buộc hoặc một bản ghi gây lỗi logic lặp lại.

Nếu không giới hạn retry, một poison message có thể chiếm worker, chặn FIFO group hoặc làm nghẽn partition.

### 8.3. Dead-letter queue (DLQ)

DLQ giữ các message vượt quá policy giao/thử lại để điều tra và xử lý riêng.

~~~mermaid
flowchart TD
    Q[(Main Queue)] --> C[Consumer]
    C --> OK{Processed?}
    OK -->|Yes| ACK[Acknowledge]
    OK -->|Transient error| RETRY[Retry with backoff]
    RETRY --> Q
    OK -->|Attempts exceeded| DLQ[(Dead-letter Queue)]
    DLQ --> ALERT[Alert / Inspect]
    ALERT --> FIX[Fix code, data or dependency]
    FIX --> REDRIVE[Controlled redrive]
    REDRIVE --> Q
~~~

DLQ không phải nơi để quên message. Phải có:

1. Owner và cảnh báo khi DLQ tăng.
2. Khả năng xem metadata và lỗi mà không lộ dữ liệu nhạy cảm.
3. Quy trình xác định nguyên nhân và sửa code/config/data.
4. Kiểm tra consumer đã idempotent trước redrive.
5. Giới hạn tốc độ redrive để tránh làm downstream quá tải.
6. Audit ai redrive, message nào, lúc nào và kết quả ra sao.

Không redrive hàng loạt khi chưa xác định side effect trước đó đã thành công hay chưa.

## 9. Ordering, partitioning và consumer scaling

### 9.1. Partition key

Trong event stream, partition key quyết định record đi vào partition nào theo thuật toán broker. Chọn key ảnh hưởng ba điều:

- **Ordering:** cùng key thường ở cùng partition và giữ thứ tự trong phạm vi partition.
- **Scalability:** key phân phối đều giúp tận dụng nhiều partition.
- **Hot partition:** một key quá phổ biến có thể dồn tải vào một partition.

Ví dụ, key theo bookingId phù hợp nếu cần thứ tự event của từng booking. Key theo một giá trị cố định sẽ làm mọi event vào cùng partition và phá vỡ khả năng mở rộng ngang.

### 9.2. Số partition và consumer

Một consumer group thường không thể xử lý song song hơn số partition đang được gán trong mô hình phổ biến; tăng consumer vượt quá số partition có thể tạo consumer nhàn rỗi. Ngược lại, quá ít partition làm giới hạn throughput và khả năng song song.

Không nên chỉ tăng partition để tăng tải mà không xem xét:

- Ordering key có thay đổi mapping khi tăng partition không?
- Consumer có đủ năng lực xử lý từng partition không?
- Broker có chịu được replication, storage và network không?
- Rebalance ảnh hưởng latency và xử lý đang dở ra sao?
- Có cần kiểm soát quota và retention không?

### 9.3. Queue và competing consumers

Với queue, tăng số worker có thể tăng throughput nếu công việc độc lập và downstream còn capacity. Nếu mọi message cùng cập nhật một bản ghi hoặc gọi một API có rate limit thấp, thêm worker không giải quyết bottleneck; cần batching, concurrency limit hoặc phân vùng công việc.

## 10. Event schema và khả năng tiến hóa

### 10.1. Versioning

Event schema cần version rõ ràng và policy tương thích. Một số thay đổi có thể tương thích tùy consumer:

- Thêm trường tùy chọn với default/ý nghĩa rõ.
- Thêm event type mới mà consumer cũ được phép bỏ qua.
- Mở rộng enum nếu consumer có nhánh xử lý unknown an toàn.

Những thay đổi thường phá vỡ hợp đồng:

- Xóa hoặc đổi tên trường đang được dùng.
- Đổi kiểu dữ liệu hoặc đơn vị đo/tiền tệ.
- Đổi ý nghĩa của event hoặc trạng thái.
- Biến trường tùy chọn thành bắt buộc.
- Thay đổi partition key hay ordering semantics mà consumer đang dựa vào.

### 10.2. Expand–migrate–contract

1. **Expand:** thêm trường/event version mới và giữ khả năng đọc cũ.
2. **Migrate:** cập nhật consumer từng bước, kiểm thử với cả dữ liệu cũ/mới.
3. **Observe:** kiểm tra consumer cũ còn đọc event cũ hay chưa, theo dõi lỗi parse.
4. **Contract:** sau thời gian hỗ trợ đã thông báo, ngừng phát schema cũ và retire consumer cũ.

Event đã lưu trong retention có thể được replay sau nhiều ngày hoặc nhiều tuần. Consumer cần biết cách đọc phiên bản cũ hoặc có bước chuyển đổi phù hợp; không thể giả định mọi record trong topic đều dùng schema mới nhất.

### 10.3. Schema registry

Schema registry lưu định nghĩa và version của event, hỗ trợ kiểm tra producer/consumer theo compatibility policy. Registry giúp phát hiện lỗi schema sớm nhưng không thể xác minh ý nghĩa nghiệp vụ đã đúng. Consumer vẫn cần kiểm thử contract và behavior.

## 11. Transactional outbox và đảm bảo phát event

### 11.1. Khoảng trống dual-write

Giả sử Booking Service ghi trạng thái CONFIRMED vào database rồi publish BookingConfirmed lên broker. Có hai tình huống lỗi:

- Database commit thành công nhưng service crash trước khi publish: consumer không nhận được event.
- Publish thành công nhưng database transaction rollback: consumer nhận một event mô tả trạng thái chưa từng được commit.

Đây là vấn đề **dual-write** giữa hai hệ thống không nằm trong cùng transaction.

### 11.2. Transactional outbox

Outbox lưu bản ghi nghiệp vụ và bản ghi event cần publish trong cùng transaction của database thuộc service:

~~~sql
BEGIN;

UPDATE bookings
SET status = 'CONFIRMED'
WHERE booking_id = 'booking_913';

INSERT INTO outbox_events(event_id, event_type, payload, created_at)
VALUES (
  'evt_01JXY99',
  'BookingConfirmed',
  '{"bookingId":"booking_913"}',
  CURRENT_TIMESTAMP
);

COMMIT;
~~~

Một publisher riêng hoặc CDC đọc outbox rồi gửi event lên broker. Nếu gửi thành công nhưng publisher crash trước khi đánh dấu đã gửi, event có thể được gửi lại. Vì vậy consumer vẫn cần idempotency/deduplication.

Transactional outbox giúp tránh việc trạng thái nghiệp vụ commit mà event bị bỏ quên trong khoảng dual-write; nó **không tự bảo đảm exactly-once end-to-end**.

### 11.3. Inbox và deduplication

Consumer có thể ghi eventId vào bảng inbox/processed_events cùng transaction với cập nhật dữ liệu cục bộ. Nếu nhận event trùng, consumer bỏ qua side effect đã hoàn tất.

Với side effect ngoài database (email, payment, SMS), cần thêm idempotency API, outbox tiếp theo hoặc đối soát. Một lần gọi ngoài có thể thành công nhưng response thất lạc; chỉ dựa vào transaction database của consumer là chưa đủ.

## 12. Bảo mật và quản trị dữ liệu sự kiện

### 12.1. Xác thực và phân quyền

- Producer chỉ được publish vào topic/queue cần thiết.
- Consumer chỉ được subscribe vào stream phù hợp.
- Tách quyền theo environment, tenant và loại event khi nền tảng hỗ trợ.
- Bảo vệ kết nối broker bằng TLS và credential/workload identity.
- Luân chuyển secret và tránh lưu credential trong payload.
- Audit thay đổi topic, subscription, retention, ACL và consumer configuration.

Không nên cấp quyền đọc mọi topic cho một worker chỉ vì triển khai chung trong một tài khoản cloud.

### 12.2. Tối thiểu hóa payload

Event nên chứa các thuộc tính consumer cần, không phát toàn bộ hồ sơ khách hàng, thông tin thanh toán hoặc giấy tờ định danh. Nếu cần dữ liệu đầy đủ, consumer có thể gọi owner service sau khi xác thực quyền hoặc dùng reference có thời hạn phù hợp.

### 12.3. Retention và chủ quyền dữ liệu

Event stream, queue, DLQ, archive, log và backup đều có thể chứa dữ liệu nghiệp vụ. Cần xác định:

- Region lưu broker/topic và bản sao.
- Thời hạn retention và cơ chế xóa.
- Ai có thể đọc hoặc replay dữ liệu cũ.
- Nội dung nào được mã hóa và ai quản lý khóa.
- Payload nào được phép đi tới consumer hoặc bên thứ ba ở khu vực khác.

Việc database chính nằm ở một region không tự đảm bảo event bus hoặc DLQ cũng nằm trong phạm vi đó. Nếu dữ liệu có ràng buộc địa lý, phải đánh giá toàn bộ đường đi và bản sao sự kiện.

## 13. Backpressure, flow control và xử lý quá tải

### 13.1. Queue depth là tín hiệu quan trọng

Nếu producer tạo 900 message/giây còn consumer xử lý 700 message/giây:

~~~text
Backlog growth = 900 - 700 = 200 messages/second

Sau 10 phút:
Backlog ≈ 200 * 600 = 120.000 messages
~~~

Nếu tải không đổi và không có giới hạn, backlog sẽ tiếp tục tăng. Chỉ scale consumer khi downstream có đủ capacity; nếu không, worker tăng lên có thể làm database hoặc API ngoài quá tải.

### 13.2. Backpressure và rate limiting

Biện pháp thường dùng:

- Giới hạn concurrency/worker count.
- Rate limit producer hoặc API đầu vào.
- Batch message khi semantics nghiệp vụ cho phép.
- Tạm dừng subscription/consumer khi downstream sự cố, nếu cơ chế hỗ trợ.
- Dùng retry có backoff và circuit breaker.
- Ưu tiên message quan trọng, trì hoãn công việc nền ít khẩn cấp.
- Đặt ngưỡng backlog và oldest-message age để cảnh báo.

### 13.3. Queue buffer khác năng lực xử lý dài hạn

Queue giúp hấp thụ spike ngắn, nhưng nếu tốc độ đầu vào trung bình luôn cao hơn tốc độ xử lý, queue chỉ trì hoãn sự cố bằng cách tích lũy backlog. Cần tăng capacity, tối ưu xử lý, giảm event thừa hoặc điều chỉnh yêu cầu nghiệp vụ.

## 14. Quan sát và vận hành event-driven system

### 14.1. Các metric cần theo dõi

| Nhóm | Metric | Mục đích |
|---|---|---|
| Producer | Publish rate, publish error, latency | Phát hiện producer không gửi được event |
| Broker | Queue depth, ingress/egress throughput, throttling | Kiểm tra năng lực và backlog |
| Consumer | Processing rate, error rate, retry count | Đánh giá xử lý và lỗi |
| Lag | Consumer lag, age of oldest message | Biết consumer chậm bao lâu |
| Delivery | Redelivery count, ack timeout, DLQ depth | Phát hiện duplicate và poison message |
| Stream | Offset, partition utilization, rebalance | Theo dõi tiến độ và phân phối tải |
| Data quality | Schema failure, invalid event, duplicate event | Phát hiện sai hợp đồng |
| Cost | Storage, retention, request, throughput, egress | Theo dõi chi phí |
| Security | Unauthorized publish/consume, ACL changes | Phát hiện truy cập bất thường |

### 14.2. Correlation và tracing

Mỗi event nên mang eventId và correlationId. Trace context có thể được truyền theo chuẩn tracing phù hợp để liên kết producer, broker và consumer. Không dùng eventId làm khóa nghiệp vụ nếu một nghiệp vụ phát nhiều event.

Log cần chứa đủ thông tin điều tra nhưng tránh payload nhạy cảm. Metric label nên tránh các giá trị cardinality cao như userId, bookingId hoặc eventId.

### 14.3. Runbook xử lý backlog và DLQ

Runbook nên chỉ ra:

1. Xác định topic/queue, subscription, consumer group và môi trường bị ảnh hưởng.
2. Kiểm tra tốc độ publish, processing rate, lag và tuổi message cũ nhất.
3. Xem error type, schema version, dependency và trạng thái deploy gần nhất.
4. Quyết định scale, giảm input, pause, rollback hoặc xử lý lỗi dependency.
5. Kiểm tra idempotency trước khi redrive DLQ hoặc replay stream.
6. Theo dõi backlog giảm, nghiệp vụ bắt kịp và dữ liệu được đối soát.

Không redrive toàn bộ DLQ khi chưa xác định nguyên nhân hoặc xác nhận side effect trước đó.

## 15. Chọn mô hình theo bài toán

| Nhu cầu | Mô hình khởi đầu thường phù hợp | Lý do |
|---|---|---|
 Gửi email khi booking xác nhận | Queue hoặc subscription riêng | Có thể xử lý bất đồng bộ, retry và scale worker |
 Nhiều hệ thống nhận BookingConfirmed | Pub/sub hoặc event bus | Fan-out tới các consumer độc lập |
 Định tuyến nhiều loại domain event tới nhiều target | Event bus | Rule routing theo type/source/attribute |
 Lưu clickstream để analytics đọc lại | Event stream | Retention, partition, consumer group và replay |
 Xử lý từng job độc lập với worker pool | Queue | Competing consumers và buffering |
 Dựng nhiều projection từ cùng lịch sử event | Event stream hoặc broker có retention phù hợp | Consumer độc lập và khả năng tái xử lý |
 Điều phối chuỗi nghiệp vụ có trạng thái, bù trừ | Workflow service kết hợp queue/event | Workflow giữ tiến trình; broker truyền thông điệp/event |

Không nên ép mọi luồng vào một nền tảng messaging duy nhất chỉ để giảm số dịch vụ. Ngược lại, cũng không nên tạo queue/topic mới cho từng hàm nhỏ nếu chi phí quản trị và observability lớn hơn giá trị.

## 16. Ví dụ kiến trúc: nền tảng đặt chỗ

Giả sử khi booking được xác nhận, hệ thống cần gửi thông báo, cập nhật tìm kiếm, ghi analytics và phát dữ liệu cho hệ thống chăm sóc khách hàng.

~~~mermaid
flowchart TB
    B[Booking Service] --> DB[(Booking DB)]
    DB --> OUT[Transactional Outbox / CDC]
    OUT --> BUS[(Event Bus)]
    BUS -->|BookingConfirmed| NQ[(Notification Queue)]
    BUS -->|BookingConfirmed| SEARCH[Search Projection Consumer]
    BUS -->|BookingConfirmed| ANALYTICS[Analytics Stream]
    BUS -->|BookingConfirmed| CRM[CRM Integration]
    NQ --> NW[Notification Workers]
    NW --> EMAIL[Email provider]
    NW --> SMS[SMS provider]
~~~

### 16.1. Phân chia trách nhiệm

| Thành phần | Trách nhiệm | Cơ chế nên xem xét |
|---|---|---|
| Booking Service | Quyết định trạng thái booking và phát event sau commit | Outbox/CDC, event contract |
| Event Bus | Định tuyến event tới target phù hợp | Rule theo eventType/tenant/attribute |
| Notification Queue | Đệm công việc gửi thông báo | Retry, visibility timeout, DLQ |
| Search consumer | Cập nhật projection | Idempotency, event version, rebuild |
| Analytics stream | Lưu chuỗi sự kiện cho phân tích | Partition, retention, consumer group |
| CRM integration | Chuyển đổi và gửi dữ liệu tới đối tác | Schema mapping, rate limit, audit, data minimization |

### 16.2. Tại sao không để Booking gọi tất cả?

Nếu Booking gọi Notification, Search, Analytics và CRM đồng bộ:

- Request đặt phòng có độ trễ phụ thuộc tất cả hệ thống đó.
- Một hệ thống phụ trợ lỗi có thể làm booking không phản hồi dù đã commit.
- Booking phải quản lý retry và trạng thái cho nhiều dịch vụ không sở hữu.
- Tăng số hệ thống tích hợp làm tăng coupling và khó scale riêng.

Phát event sau khi booking đã được xác nhận giúp tách các tác vụ hậu xử lý. Tuy nhiên, nghiệp vụ cốt lõi như giữ chỗ/thanh toán vẫn cần được điều phối và xác nhận trước khi phát BookingConfirmed. Event không thay thế transaction nghiệp vụ.

### 16.3. Xử lý lỗi mẫu

- **Notification provider lỗi:** queue giữ công việc, worker retry có giới hạn; quá số lần chuyển DLQ và cảnh báo.
- **Search consumer lỗi schema:** dừng hoặc đưa message lỗi vào DLQ theo policy; sửa consumer tương thích rồi redrive có kiểm soát.
- **Analytics consumer chậm:** tăng partition/consumer nếu broker và downstream cho phép; theo dõi lag và retention để tránh record hết hạn trước khi xử lý.
- **Booking commit nhưng publish chậm:** outbox publisher tiếp tục phát; consumer chấp nhận duplicate.
- **CRM hết quota:** giới hạn rate, retry theo Retry-After và giữ backlog; không để CRM làm chậm giao dịch booking.

## 17. Các đánh đổi theo Well-Architected

| Trụ cột | Câu hỏi thiết kế | Đánh đổi cần cân nhắc |
|---|---|---|
| **Operational Excellence** | Ai sở hữu topic, schema, consumer, DLQ và runbook? | Nhiều broker/topic tăng linh hoạt nhưng tăng số tài nguyên phải theo dõi |
| **Security** | Ai được publish/consume, event chứa dữ liệu gì và lưu ở đâu? | Fan-out rộng tăng khả năng tích hợp nhưng mở rộng bề mặt truy cập dữ liệu |
| **Reliability** | Duplicate, ordering, retry, broker outage và replay được xử lý ra sao? | Durability/replication tăng độ tin cậy nhưng có thể tăng latency và chi phí |
| **Performance Efficiency** | Throughput, partition, consumer concurrency và payload có phù hợp? | Batch/fan-out giúp thông lượng nhưng có thể tăng latency hoặc tạo hot partition |
| **Cost Optimization** | Retention, storage, request, egress, DLQ và consumer idle tốn bao nhiêu? | Lưu dài hỗ trợ replay nhưng tăng storage; nhiều subscription tạo thêm delivery |
| **Sustainability** | Có event trùng/thừa, polling và payload không cần thiết không? | Giảm event và retention vô ích giúp tiết kiệm tài nguyên và truyền tải |

Một broker được quản lý có thể giảm công việc quản trị hạ tầng, nhưng khách hàng vẫn phải quản lý schema, quyền, retry, consumer, retention và xử lý lỗi nghiệp vụ.

## 18. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Coi queue và pub/sub giống nhau | Consumer không nhận đủ bản sao sự kiện hoặc công việc bị xử lý sai | Xác định competing consumers hay fan-out subscription |
| Giả định broker không giao trùng | Side effect lặp, gửi email hoặc thanh toán kép | Idempotency và deduplication |
| Commit trạng thái rồi publish event bằng hai thao tác độc lập | Mất event hoặc phát event sai | Transactional outbox/CDC |
| Dùng timestamp để bảo đảm thứ tự | Event tới muộn có thể ghi đè trạng thái mới | Version/sequence và ordering key |
| Retry vô hạn | Poison message gây backlog và chi phí tăng | Retry budget, DLQ và alert |
| Redrive DLQ không kiểm tra | Lặp side effect hoặc gây quá tải | Kiểm tra idempotency, sửa nguyên nhân và redrive có giới hạn |
| Chọn partition key quá lệch | Hot partition và throughput thấp | Đánh giá phân bố key và tải theo tenant/entity |
| Lưu payload nhạy cảm không cần thiết | Rủi ro lộ dữ liệu, tăng retention nghĩa vụ | Data minimization, encryption và access control |
| Không giám sát consumer lag | Dữ liệu cũ hoặc retention hết trước khi xử lý | Alert theo lag/oldest-message age |
| Dùng event stream làm database nghiệp vụ mặc định | Khó cập nhật, truy vấn và quản trị invariant | Phân định system of record và event log |

## 19. Bài tập áp dụng

### Bài tập A — Queue hay pub/sub?

Một booking cần tạo một hóa đơn. Chỉ một worker trong nhóm thực hiện công việc, các worker cùng chia tải.

**Câu hỏi:** Nên bắt đầu với mô hình nào?

**Gợi ý:** Queue với competing consumers phù hợp nếu mỗi công việc chỉ cần một consumer xử lý. Consumer vẫn phải idempotent vì có thể nhận message trùng.

### Bài tập B — Một sự kiện, ba consumer

Khi booking xác nhận, Notification, Search và Analytics đều cần nhận event độc lập.

**Câu hỏi:** Làm thế nào để một consumer chậm không ngăn consumer khác?

**Gợi ý:** Dùng pub/sub/event bus với subscription độc lập hoặc stream với consumer group riêng. Mỗi consumer có backlog, retry và monitoring riêng theo khả năng broker.

### Bài tập C — Duplicate sau timeout

Consumer cập nhật database thành công nhưng mất acknowledgement. Broker giao lại cùng event.

**Câu hỏi:** Consumer cần làm gì?

**Gợi ý:** Lưu eventId vào inbox/processed_events cùng transaction với cập nhật nghiệp vụ; nếu event đã xử lý, không lặp side effect. Với API bên ngoài, dùng idempotency key hoặc đối soát.

### Bài tập D — Thứ tự booking

Một booking phát BookingConfirmed rồi BookingCancelled. Hai event có thể được xử lý song song và consumer nhận Cancelled trước Confirmed.

**Câu hỏi:** Làm sao tránh projection quay về trạng thái cũ?

**Gợi ý:** Dùng partition key theo bookingId, aggregate version/sequence, kiểm tra transition hợp lệ và xử lý event cũ tới muộn. Không dựa chỉ vào thời điểm nhận.

### Bài tập E — Backlog tăng

Producer phát 1.200 message/s, consumer xử lý 900 message/s trong 15 phút.

**Câu hỏi:** Backlog tăng thêm khoảng bao nhiêu message?

**Gợi ý:** Chênh lệch 300 message/s; trong 900 giây backlog tăng khoảng 270.000 message nếu không có thay đổi đầu vào, processing hoặc mất message. Cần xử lý bottleneck và kiểm tra retention.

### Bài tập F — Event không thể parse

Producer phát schema version mới, consumer cũ không hiểu trường bắt buộc và liên tục lỗi.

**Câu hỏi:** Cần quy trình nào trước khi redrive?

**Gợi ý:** Đưa message lỗi vào DLQ theo policy, kiểm tra schema compatibility, triển khai consumer tương thích, test cả version cũ/mới, sau đó redrive với concurrency giới hạn và xác minh idempotency.

## 20. Checklist trước khi triển khai event architecture

- [ ] Đã xác định message là command, event, request hay job và owner phát/nhận.
- [ ] Chọn queue, pub/sub, event bus hoặc stream dựa trên delivery, fan-out, replay, ordering và retention.
- [ ] Event có schema/version, eventId, occurredAt, producer và correlation ID cần thiết.
- [ ] Payload được tối thiểu hóa; không chứa secret hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Producer/consumer có IAM/ACL theo least privilege và kết nối được bảo vệ.
- [ ] Consumer idempotent; duplicate, timeout sau commit và side effect ngoài được đối soát.
- [ ] Retry có giới hạn, backoff/jitter, visibility timeout/ack hoặc offset semantics được hiểu rõ.
- [ ] Ordering key/partition key phù hợp; đã kiểm tra hot partition và consumer scaling.
- [ ] DLQ có owner, alert, quy trình điều tra, sửa lỗi và redrive có kiểm soát.
- [ ] Outbox/CDC được xem xét cho dual-write quan trọng.
- [ ] Có metric publish rate, consumer lag, oldest-message age, retry, DLQ và error rate.
- [ ] Retention, archive, backup, region và chính sách xóa dữ liệu được xác định.
- [ ] Quota, throughput, concurrency, storage, egress và chi phí đã được dự báo.
- [ ] Đã test duplicate, out-of-order, broker outage, poison message, replay và tải đột biến.
- [ ] Có runbook, service owner và chu kỳ review schema/contract.

**Điểm cốt lõi:** queue thường phân phối công việc; pub/sub phát sự kiện tới nhiều subscriber; event bus định tuyến event theo rule; event stream lưu chuỗi sự kiện để nhiều consumer đọc theo tiến độ riêng và có thể replay trong phạm vi retention. Dù chọn mô hình nào, hệ thống vẫn cần hợp đồng rõ ràng, consumer idempotent, xử lý duplicate và lỗi, kiểm soát dữ liệu, quan sát backlog và kiểm thử phục hồi. Đó là nền tảng để kiến trúc sự kiện mở rộng mà vẫn giữ được tính đúng đắn và khả năng vận hành.
