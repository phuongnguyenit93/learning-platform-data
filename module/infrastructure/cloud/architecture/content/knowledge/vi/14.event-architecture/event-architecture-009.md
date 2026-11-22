# Dead-letter queue và quy trình xử lý sự kiện lỗi

Trong kiến trúc hướng sự kiện, producer thường gửi message vào queue hoặc event bus để consumer xử lý bất đồng bộ. Cách làm này giúp tách vòng đời các dịch vụ, hấp thụ tải đột biến và cho phép retry khi phụ thuộc tạm thời gặp sự cố. Tuy vậy, không phải message nào cũng xử lý thành công. Message có thể sai schema, thiếu dữ liệu, chứa tham chiếu không còn tồn tại, gây lỗi nghiệp vụ hoặc liên tục gặp timeout. Nếu chỉ retry vô hạn, một message lỗi có thể chiếm tài nguyên, làm nghẽn queue và khiến các message hợp lệ bị chậm.

**Dead-letter queue (DLQ)** là cơ chế giữ riêng những message không thể được xử lý thành công theo chính sách giao nhận/retry đã định. DLQ tạo nơi quan sát và điều tra lỗi, cho phép sửa nguyên nhân rồi phát lại message có kiểm soát. DLQ không tự sửa message, không tự bảo đảm dữ liệu nghiệp vụ đúng và cũng không nên được xem là kho lưu trữ vô thời hạn.

Trong module **CLOUD_ARCHITECTURE**, thiết kế DLQ là một phần của kiến trúc sự kiện và độ tin cậy. Bài học này trình bày cách phân loại lỗi, chọn retry, thiết kế consumer idempotent, cấu hình DLQ, điều tra và redrive, đồng thời cân nhắc bảo mật, chi phí, vận hành và khả năng phục hồi theo tư duy Well-Architected.

## 1. Vì sao cần dead-letter queue?

Giả sử Booking API phát sự kiện BookingConfirmed vào queue. Notification Worker nhận sự kiện để gửi email xác nhận. Một số message có thể thất bại vì:
- Email Provider tạm thời không phản hồi.
- Worker mất kết nối database hoặc secret manager.
- Message sai schema do producer phát hành phiên bản mới không tương thích.
- Email address không hợp lệ hoặc dữ liệu bắt buộc bị thiếu.
- Một booking đã bị xóa hoặc trạng thái đã thay đổi nên thao tác không còn hợp lệ.
- Code consumer có bug khiến một loại payload cụ thể luôn làm tiến trình crash.

Không phân loại lỗi, consumer có thể retry mọi trường hợp. Điều đó có thể tạo ra vòng lặp:

~~~text
Queue -> Consumer -> Error -> Retry -> Consumer -> Error -> Retry ...
~~~

Khi message lỗi được giao liên tục, nó tiêu tốn concurrency và CPU, làm các message hợp lệ phải chờ, che mất sự cố mới trong log, tăng tải lên hệ thống phụ thuộc và không tạo được điểm tập trung để đội vận hành quan sát.

DLQ tách message đã vượt ngưỡng xử lý khỏi luồng chính:

~~~mermaid
flowchart LR
    P["Producer"] --> Q[("Main queue")]
    Q --> C["Consumer / worker"]
    C -->|"Thành công: ack/delete"| DONE["Completed"]
    C -->|"Lỗi: retry theo policy"| Q
    Q -->|"Vượt ngưỡng giao lại"| DLQ[("Dead-letter queue")]
    DLQ --> TRIAGE["Điều tra / phân loại"]
    TRIAGE --> FIX["Sửa dữ liệu hoặc nguyên nhân"]
    FIX --> REDRIVE["Redrive có kiểm soát"]
    REDRIVE --> Q
~~~

DLQ giúp giữ lại message thất bại để điều tra thay vì bỏ mất hoặc tiếp tục đưa chúng vào cùng luồng xử lý bình thường. Tuy nhiên, chính sách đưa message vào DLQ khác nhau theo dịch vụ: có dịch vụ dùng số lần giao tối đa, có dịch vụ dùng thời gian khóa/visibility, có dịch vụ yêu cầu cấu hình dead-letter policy ở subscription. Cần đọc semantics cụ thể của queue đang dùng.

## 2. Phân biệt queue chính, retry queue và DLQ

Ba loại queue có thể xuất hiện trong cùng một thiết kế nhưng vai trò khác nhau:

| Thành phần | Mục đích | Vòng đời message |
|---|---|---|
| **Main queue** | Giữ message chờ consumer xử lý lần đầu hoặc bình thường | Được giao theo semantics của queue và consumer |
| **Retry queue / delayed retry** | Trì hoãn lần thử tiếp theo sau lỗi có khả năng phục hồi | Chờ một khoảng thời gian rồi quay lại luồng xử lý |
| **Dead-letter queue** | Cô lập message đã hết cơ hội retry tự động hoặc không thể xử lý theo policy | Chờ điều tra, sửa nguyên nhân và redrive hoặc loại bỏ theo quy trình |

Không phải hệ thống nào cũng cần retry queue riêng. Một số broker hỗ trợ visibility timeout, delayed delivery, scheduled enqueue hoặc retry policy tích hợp. Dù triển khai kiểu nào, phải phân biệt **thử lại trong cùng luồng** và **đưa message sang vùng cách ly để con người hoặc quy trình chuyên biệt xử lý**.

DLQ cũng không giống queue lưu mọi message đã hoàn thành. Message xử lý thành công phải được ack/delete hoặc hoàn tất theo giao thức tương ứng. Nếu message đã xử lý thành công vẫn xuất hiện trong DLQ, thường đó là dấu hiệu lỗi ack, timeout, consumer hoặc cấu hình redelivery.

## 3. Phân loại lỗi trước khi quyết định retry

Không phải lỗi nào cũng nên retry. Một chính sách tốt bắt đầu bằng phân loại:

| Nhóm lỗi | Ví dụ | Có nên retry? | Hướng xử lý |
|---|---|---|---|
| **Lỗi tạm thời (transient)** | Timeout mạng, HTTP 503, database failover ngắn | Có, với giới hạn và backoff | Retry có delay, theo dõi phụ thuộc |
| **Throttling / quota** | HTTP 429, queue hoặc API vượt quota | Có, tôn trọng Retry-After nếu có | Backoff, giảm concurrency, điều tiết tải |
| **Lỗi xác thực/cấu hình** | Credential hết hạn, permission bị thu hồi, endpoint sai | Không retry liên tục nếu chưa sửa nguyên nhân | Cảnh báo, khôi phục identity/config, sau đó retry |
| **Lỗi dữ liệu/schema** | Thiếu field bắt buộc, enum lạ không được hỗ trợ | Thường không retry cùng payload | Cách ly, kiểm tra producer/schema, chuyển đổi dữ liệu nếu được phép |
| **Lỗi nghiệp vụ vĩnh viễn** | Booking đã hủy, tài nguyên không tồn tại, giao dịch bị từ chối | Không retry vô hạn | Ghi trạng thái thất bại hoặc xử lý nghiệp vụ thay thế |
| **Bug consumer** | Null pointer với một payload, logic lỗi ở một nhánh | Retry sau khi sửa code nếu dữ liệu còn hợp lệ | DLQ, sửa code, test rồi redrive |
| **Lỗi không xác định** | Worker crash, connection reset, process bị kill | Có thể retry có giới hạn | Ghi đủ context và đặt ngưỡng an toàn |

### 3.1. Retry chỉ có ý nghĩa khi lỗi có khả năng thay đổi

Nếu message sai schema thì retry sau 1 giây, 1 phút hay 1 giờ vẫn thất bại cho tới khi producer hoặc dữ liệu được sửa. Retry lỗi vĩnh viễn chỉ tăng chi phí. Ngược lại, bỏ ngay message khi database đang failover có thể tạo thất bại không cần thiết.

Consumer nên ánh xạ lỗi kỹ thuật và lỗi nghiệp vụ sang loại retry rõ ràng. Tránh một khối catch-all chỉ ghi log rồi ném lại mọi exception.

### 3.2. Có giới hạn tổng thời gian và số lần thử

Đừng chỉ định retry count mà quên tổng thời gian. Ví dụ retry 8 lần, mỗi lần chờ tăng dần có thể kéo dài nhiều phút. Với tác vụ thông báo, độ trễ đó có thể chấp nhận được; với xác nhận thanh toán, cần trạng thái nghiệp vụ và timeout khác.

Xác định số lần giao/thử tối đa, backoff và thời gian delay tối đa, tổng tuổi message tối đa, thời gian xử lý tối đa mỗi lần, thời điểm chuyển DLQ và thời điểm hết hạn hoặc cần xử lý thủ công. Ngưỡng là quyết định theo nghiệp vụ, không có một giá trị mặc định phù hợp mọi queue.

## 4. Exponential backoff, jitter và kiểm soát tải

Retry ngay lập tức có thể tạo một đợt tải mới đúng lúc hệ thống phụ thuộc đang suy yếu. **Exponential backoff** tăng khoảng chờ giữa các lần thử, còn **jitter** thêm độ ngẫu nhiên để các worker không cùng retry tại một thời điểm.

Một công thức minh họa:

\[
d_n = \min(d_{\max}, d_0 \times 2^n)
\]

Trong đó d0 là khoảng chờ cơ sở, n là số lần retry bắt đầu từ 0, và dmax là giới hạn delay.

Có thể thêm full jitter:

\[
d_{\text{actual}} \sim U(0, d_n)
\]

Ví dụ với d0 = 1 giây, giới hạn 30 giây, các cửa sổ chờ lần lượt là 1, 2, 4, 8, 16, 30 giây; full jitter chọn thời gian ngẫu nhiên trong cửa sổ tương ứng. Các con số chỉ để minh họa.

~~~text
Lần retry       Cửa sổ backoff       Delay thực tế với full jitter
1               1 giây               ngẫu nhiên 0–1 giây
2               2 giây               ngẫu nhiên 0–2 giây
3               4 giây               ngẫu nhiên 0–4 giây
4               8 giây               ngẫu nhiên 0–8 giây
5               16 giây              ngẫu nhiên 0–16 giây
6+              30 giây              ngẫu nhiên 0–30 giây
~~~

Khi dịch vụ trả HTTP 429 hoặc 503 có header Retry-After, cần tôn trọng thông tin đó trong giới hạn policy. Retry policy phải tránh retry storm, thundering herd, retry amplification và queue starvation.

Nên có concurrency limit, circuit breaker hoặc cơ chế pause consumer khi phụ thuộc đang lỗi, và backpressure để kiểm soát lượng message được lấy vào xử lý.

## 5. Ack, visibility timeout, lock và số lần giao

Semantics giao nhận ảnh hưởng trực tiếp tới cách DLQ hoạt động.

### 5.1. At-least-once delivery

Nhiều queue managed cung cấp semantics giao nhận ít nhất một lần trong các chế độ phổ biến. Điều đó có nghĩa consumer có thể nhận cùng message nhiều lần, ví dụ khi worker xử lý xong nhưng chết trước khi ack/delete, ack bị timeout hoặc mất trên đường truyền, visibility/lock hết hạn trong khi xử lý vẫn đang chạy, hoặc broker không nhận được xác nhận hoàn tất.

Vì vậy, **at-least-once không đồng nghĩa mỗi message chỉ xử lý một lần**. Consumer phải an toàn khi nhận lại message.

### 5.2. Visibility timeout và lock duration

Với queue kiểu visibility timeout, khi consumer nhận message, message tạm thời không được giao cho consumer khác trong khoảng thời gian cấu hình. Nếu consumer không xóa/ack trước khi hết hạn, message có thể xuất hiện lại.

Với broker dùng message lock, message được khóa trong một khoảng thời gian; consumer cần complete/ack đúng hạn hoặc renew lock nếu xử lý lâu. Chi tiết và tên gọi khác nhau theo dịch vụ.

Nếu timeout/lock quá ngắn, worker còn đang xử lý thì message đã được giao lại; hai worker có thể thực hiện cùng một tác vụ; số delivery count tăng nhanh và message có thể vào DLQ dù tác vụ cuối cùng vẫn thành công.

Nếu timeout quá dài, worker chết thì message phải chờ lâu mới được giao lại; khôi phục queue chậm hơn và message bị treo chiếm khả năng xử lý.

Nên đặt thời gian dựa trên phân bố processing time, có margin hợp lý, và dùng renewal/heartbeat cho tác vụ dài nếu queue hỗ trợ. Không kéo dài lock vô hạn để che lỗi consumer.

### 5.3. Delivery count khác retry count ở ứng dụng

Một consumer có thể tự retry API bên ngoài ba lần trong một lần giao message. Broker lại đếm một delivery cho lần giao message. Nếu worker fail trước ack và broker giao lại, tổng số lần gọi API có thể nhiều hơn delivery count.

Cần phân biệt:
- **Delivery count:** Broker đã giao message bao nhiêu lần, theo định nghĩa dịch vụ.
- **Application retry count:** Ứng dụng đã thử tác vụ hoặc gọi dependency bao nhiêu lần.
- **Business attempt count:** Số lần nghiệp vụ thực sự được thực hiện, nếu được ghi nhận riêng.

## 6. Poison message là gì?

**Poison message** là message liên tục làm consumer thất bại do nội dung hoặc điều kiện xử lý đặc biệt. Ví dụ JSON không parse được, schema version không được hỗ trợ, một giá trị gây exception ở một nhánh code, payload quá lớn hoặc dữ liệu hợp lệ về cú pháp nhưng vi phạm invariant nghiệp vụ.

Một poison message có thể làm nhiều message khác chậm lại. Với FIFO queue hoặc consumer xử lý tuần tự, ảnh hưởng có thể tập trung vào một nhóm hoặc partition. DLQ giúp cô lập nhưng phải cân nhắc semantics thứ tự: đưa message ra DLQ có thể cho phép message sau tiếp tục, làm luồng nghiệp vụ thay đổi thứ tự quan sát.

Không nên ném mọi lỗi vào DLQ ngay lập tức:
- Lỗi schema/data vĩnh viễn: có thể đưa vào DLQ ngay hoặc sau validation.
- Lỗi dependency transient: retry theo policy trước.
- Lỗi security/config: cảnh báo và dừng có kiểm soát; tránh retry dồn dập.
- Lỗi nghiệp vụ hợp lệ: có thể ghi kết quả rejected/failed trong hệ thống nghiệp vụ thay vì coi là poison message.
- Bug mới phát hành: DLQ có thể lưu message cho tới khi rollback/fix và redrive.

Phải ghi rõ vì sao message bị dead-letter, không chỉ dựa trên việc đã giao nhiều lần.

## 7. Idempotent consumer: nền tảng để retry an toàn

Một consumer **idempotent** đảm bảo việc xử lý lại cùng một message không tạo side effect nghiệp vụ lặp ngoài ý muốn. Đây là điều kiện quan trọng vì retry và redelivery là tình huống bình thường trong hệ thống phân tán.

Ví dụ, Notification Worker nhận BookingConfirmed nhiều lần. Nó cần tránh gửi email xác nhận lặp nếu quy tắc nghiệp vụ yêu cầu chỉ gửi một lần cho cùng event.

Một cách tiếp cận là lưu event ID đã xử lý trong cùng transaction với side effect nội bộ:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Pseudo flow:

~~~text
BEGIN TRANSACTION
  Nếu event_id đã có trong processed_events:
      trả kết quả "đã xử lý", không lặp side effect
  Ngược lại:
      ghi thay đổi nghiệp vụ cần thiết
      ghi event_id vào processed_events
COMMIT
ACK message
~~~

Khóa duy nhất trên event_id cần được thực thi ở database để hai worker xử lý đồng thời không cùng vượt qua bước kiểm tra. Nếu side effect nằm ở dịch vụ ngoài (gửi email, charge payment), transaction database không thể bao trùm thao tác đó; cần idempotency key phía dịch vụ ngoài, outbox/inbox pattern hoặc trạng thái workflow riêng.

Các quy tắc:
- Mỗi event có ID duy nhất, ổn định qua các lần retry/redrive.
- Không sinh event ID mới mỗi khi phát lại cùng sự kiện.
- Consumer ghi nhận kết quả xử lý và khóa chống trùng một cách nguyên tử khi có thể.
- Xác định scope của idempotency key: theo tenant, loại thao tác hay event.
- Quy định thời hạn lưu deduplication record đủ dài so với thời gian redrive/replay.
- Không coi message trùng là luôn vô hại nếu side effect chưa có cơ chế chống trùng.

**Redrive có thể lặp message đã từng xử lý thành công nhưng chưa ack**, vì vậy idempotency vẫn cần thiết cả khi đội vận hành phát lại thủ công.

## 8. Thiết kế DLQ trong hệ thống sự kiện

Một thiết kế cơ bản cho Booking System:

~~~mermaid
flowchart TB
    OUT["Booking API / Outbox publisher"] --> MAIN[("booking-events")]
    MAIN --> WORKER["Notification Worker"]
    WORKER -->|"Success + ack"| OK["Notification state updated"]
    WORKER -->|"Transient error"| RETRY["Backoff / delayed retry"]
    RETRY --> MAIN
    WORKER -->|"Delivery limit exceeded"| DLQ[("booking-events-dlq")]
    DLQ --> METRIC["DLQ depth / oldest age / alert"]
    DLQ --> OPS["Triage workflow"]
    OPS --> PATCH["Fix consumer or transform approved data"]
    PATCH --> REPLAY["Controlled redrive"]
    REPLAY --> MAIN
~~~

Các thành phần cần thiết:
1. **Main queue:** Giữ message chưa xử lý.
2. **Consumer:** Xác thực schema, kiểm tra quyền, xử lý nghiệp vụ và ack đúng thời điểm.
3. **Retry policy:** Quy định lỗi nào được retry, thời gian chờ và ngưỡng chuyển DLQ.
4. **DLQ:** Lưu message lỗi cùng metadata giao nhận và lý do nếu broker hỗ trợ.
5. **Alert/observability:** Theo dõi DLQ depth, oldest message age, arrival rate, retry và nguyên nhân.
6. **Triage/redrive process:** Quy trình được phân quyền để điều tra, sửa nguyên nhân và phát lại hoặc loại bỏ theo chính sách.

DLQ cần owner và cấu hình riêng: retention, encryption, IAM/RBAC, message format, metadata, alerting, quyền đọc/purge/redrive và quy trình tránh redrive loop.

Không dùng cùng một DLQ cho mọi loại event chỉ vì tiện. Có thể chia theo bounded context, mức độ nhạy cảm, owner, SLA hoặc kiểu consumer để điều tra và phân quyền đúng. Cũng không nên tạo quá nhiều DLQ nhỏ khiến khó quản lý và không ai nhận trách nhiệm.

## 9. DLQ trên các nền tảng cloud phổ biến

Các cloud có cách thể hiện DLQ khác nhau. Hãy hiểu semantics thay vì chỉ tìm nút có chữ dead letter.

| Nền tảng/dịch vụ | Cơ chế DLQ phổ biến | Điều cần chú ý |
|---|---|---|
| **Amazon SQS** | Redrive policy liên kết source queue với dead-letter queue và maxReceiveCount | Delivery/receive count, visibility timeout, retention; FIFO có giới hạn và semantics riêng; redrive task có tốc độ và quyền riêng |
| **Azure Service Bus** | Subqueue dead-letter thuộc entity queue/subscription; consumer có thể dead-letter message với reason/description hoặc broker tự dead-letter theo điều kiện | Dead-letter reason/error description; TTL, max delivery count, lock duration; muốn xử lý cần nhận message từ dead-letter subqueue và chuyển/complete có chủ đích |
| **Google Cloud Pub/Sub** | Dead-letter topic được cấu hình trên subscription cùng maxDeliveryAttempts và quyền publish/subscribe thích hợp | Delivery attempt mang tính xấp xỉ trong một số điều kiện; dead-letter topic là topic riêng; cấu hình IAM và subscription của topic đích; retry/backoff theo policy |

### 9.1. Amazon SQS

Trong SQS, queue nguồn có thể cấu hình redrive policy trỏ tới DLQ và ngưỡng maxReceiveCount. Khi một message được nhận vượt ngưỡng theo semantics dịch vụ, nó được chuyển sang DLQ.

Điều cần kiểm tra:
- Queue nguồn và DLQ có loại tương thích theo yêu cầu dịch vụ không (standard/FIFO).
- Visibility timeout đủ cho thời gian xử lý.
- Retention của DLQ không ngắn hơn mức vận hành cần thiết.
- Redrive permission và quyền gửi/nhận phù hợp.
- Redrive task có kiểm soát tốc độ để không làm quá tải consumer hoặc dependency.

SQS hỗ trợ redrive từ DLQ về source queue hoặc queue đích theo tính năng dịch vụ. Redrive không thay thế idempotency và kiểm tra message trước khi đưa lại luồng.

### 9.2. Azure Service Bus

Service Bus có dead-letter subqueue gắn với queue hoặc subscription. Message có thể được dead-letter bởi broker, ví dụ khi vượt max delivery count hoặc TTL tùy cấu hình, hoặc bởi application khi phát hiện lỗi không thể xử lý.

Cần phân biệt:
- Dead-letter subqueue không phải một entity queue độc lập mà tạo thêm một vùng nhận message cho entity.
- Lock duration/renewal ảnh hưởng delivery và dead-letter.
- Một số lỗi cấu hình hoặc filter của topic subscription cũng có thể tạo dead-letter; không phải tất cả đều đến từ exception của consumer.
- Việc chuyển message trở lại queue chính cần xử lý duplicate, sequence và ordering phù hợp.

### 9.3. Google Cloud Pub/Sub

Pub/Sub hỗ trợ dead-letter topic trên subscription. Khi cấu hình, cần thiết lập dead-letter topic, số lần giao tối đa và quyền cần thiết để Pub/Sub publish message sang topic đó. Một subscription khác có thể đọc dead-letter topic để điều tra.

Delivery attempt có thể được tính gần đúng trong một số trường hợp tùy cấu hình và behavior của dịch vụ. Không thiết kế logic nghiệp vụ phụ thuộc vào việc con số attempt luôn chính xác tuyệt đối. Cần xem retry policy, acknowledgment deadline, subscription type và quyền IAM thực tế.

Tên gọi và cấu hình có thể thay đổi theo sản phẩm. Khi triển khai thực tế, xác minh quota, giới hạn retention, quyền, semantics redrive và chi phí trong tài liệu dịch vụ/Region đang sử dụng.

## 10. Message envelope và metadata phục vụ điều tra

Một message nên có đủ metadata để consumer và đội vận hành hiểu nguồn gốc cũng như phạm vi xử lý, nhưng không chứa secret hoặc dữ liệu nhạy cảm không cần thiết.

Ví dụ envelope:

~~~json
{
  "eventId": "evt-01J8ABCDEF",
  "eventType": "BookingConfirmed",
  "schemaVersion": 2,
  "occurredAt": "2026-12-01T08:00:00Z",
  "producer": "booking-api",
  "correlationId": "corr-81ab",
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "data": {
    "bookingId": "BK-9081",
    "customerReference": "cust-302"
  }
}
~~~

Các trường hữu ích:
- eventId: định danh ổn định để deduplicate.
- eventType: loại event.
- schemaVersion: phiên bản schema.
- occurredAt: thời điểm nghiệp vụ xảy ra.
- producer: hệ thống phát event.
- correlationId: liên kết các bước của một nghiệp vụ.
- traceparent: context truy vết phân tán nếu dùng W3C Trace Context.
- data: payload nghiệp vụ tối thiểu cần cho consumer.

Broker có thể bổ sung metadata riêng như delivery count, enqueue time, dead-letter reason, sequence number hoặc lock token. Không giả định mọi nền tảng lưu các trường giống nhau; khi chuyển qua adapter hoặc redrive, phải bảo toàn event ID/correlation ID và ghi nhận metadata broker phù hợp.

**Không nhúng password, bearer token, private key hoặc thông tin thẻ thanh toán vào event.** DLQ có thể được giữ lâu và cấp cho đội vận hành rộng hơn consumer thường. Nếu payload chứa dữ liệu cá nhân, tối thiểu hóa nội dung, mã hóa, phân quyền đọc, retention và quy trình xóa cần được thiết kế từ đầu.

## 11. Quy trình triage: điều tra message trong DLQ

Khi DLQ nhận message, mục tiêu đầu tiên là **xác định mức độ ảnh hưởng và nguyên nhân**, không vội redrive toàn bộ.

### Bước 1 — Xác định nguồn và phạm vi
- DLQ thuộc main queue/subscription nào?
- Consumer và team owner là ai?
- Event type/schema version nào?
- Có bao nhiêu message và message mới nhất/cũ nhất vào lúc nào?
- Có phải một producer hoặc release cụ thể gây lỗi không?

### Bước 2 — Kiểm tra metadata và nguyên nhân
- Dead-letter reason hoặc exception code có sẵn?
- Delivery count/application retry count?
- Enqueue time, occurredAt, correlationId?
- Consumer version, image tag, deployment revision?
- Có thay đổi schema, quyền IAM, secret hoặc endpoint gần thời điểm đó không?

### Bước 3 — Đánh giá tác động nghiệp vụ

Không phải mọi DLQ message đều có cùng mức quan trọng. Phân loại:
- Đơn thuần thất lạc email thông báo.
- Booking đã commit nhưng notification chưa gửi.
- Payment state chưa được đồng bộ.
- Báo cáo chậm nhưng dữ liệu chuẩn còn nguyên.
- Lệnh nghiệp vụ có side effect chưa rõ đã thực hiện hay chưa.

Cần xác định **source of truth**. Trước redrive, có thể phải truy vấn database/workflow để biết nghiệp vụ đã thành công một phần hay chưa.

### Bước 4 — Quyết định cách xử lý

| Tình huống | Hướng xử lý |
|---|---|
| Dependency đã phục hồi, message hợp lệ | Redrive có kiểm soát, có thể theo batch nhỏ |
| Consumer bug đã được sửa | Triển khai bản sửa, test message đại diện rồi redrive |
| Schema từ producer không tương thích | Sửa producer/consumer hoặc dùng transformer có kiểm soát, giữ event ID và audit |
| Dữ liệu sai hoặc thiếu không thể suy ra | Yêu cầu owner nghiệp vụ sửa nguồn dữ liệu hoặc quyết định bỏ theo policy |
| Event đã được thực hiện trước đó | Deduplicate/idempotency; không lặp side effect |
| Message hết hạn hoặc không còn ý nghĩa nghiệp vụ | Loại bỏ theo retention/approval policy, lưu dấu quyết định |
| Có dấu hiệu tấn công hoặc payload độc hại | Cách ly, hạn chế truy cập, chuyển quy trình security incident |

### Bước 5 — Ghi nhận quyết định

Mỗi batch xử lý nên ghi incident/ticket ID, người phê duyệt và người thực hiện, DLQ/source queue, event ID hoặc số lượng message, nguyên nhân/code fix, kết quả test trước redrive, thời điểm/tốc độ redrive, số thành công/lỗi lại/duplicate/bị bỏ và kết quả đối soát nghiệp vụ.

Không copy payload nhạy cảm vào ticket hoặc chat công khai. Dùng ID tham chiếu và nơi lưu có phân quyền.

## 12. Redrive an toàn: phát lại mà không làm hỏng dữ liệu

**Redrive** là chuyển message từ DLQ trở lại queue/topic hoặc consumer path để xử lý lại. Đây là thao tác có side effect và cần quy trình kiểm soát.

### 12.1. Không redrive toàn bộ ngay lập tức

Trước tiên:
1. Xác nhận nguyên nhân gốc đã được xử lý.
2. Xác nhận consumer version mới đọc được schema/payload.
3. Kiểm thử một message đại diện trong môi trường an toàn nếu có thể.
4. Kiểm tra event đã tạo side effect trước đó hay chưa.
5. Chọn batch nhỏ và tốc độ phù hợp.
6. Theo dõi queue depth, error rate, dependency saturation và số message vào DLQ lại.
7. Tạm dừng nếu lỗi tái diễn hoặc downstream quá tải.

### 12.2. Giữ nguyên event ID

Khi redrive, không tạo event ID mới cho cùng event nghiệp vụ chỉ để né deduplication. Điều đó có thể làm consumer coi message phát lại là hành động mới và gửi email/charge payment lần hai.

Nếu thực sự tạo **một nghiệp vụ mới** dựa trên event cũ, phải tạo event ID mới và quan hệ causation/parent event rõ ràng. Redrive đơn thuần nên giữ identity của event gốc.

### 12.3. Tránh vòng lặp DLQ

Một redrive thiếu kiểm soát có thể tạo chu kỳ:

~~~text
DLQ -> Main queue -> Consumer lỗi -> DLQ -> Redrive -> ...
~~~

Nên có số lần redrive hoặc vòng sửa lỗi được ghi nhận, cơ chế dừng tự động nếu message quay lại DLQ, cấu hình source queue/DLQ không tạo chu trình chuyển tiếp sai, batch riêng cho message có rủi ro và owner có quyền phê duyệt redrive/purge.

### 12.4. Khi nào cần replay có biến đổi?

Có thể cần chuyển đổi message cũ sang schema mới nếu producer đã ngừng phát schema cũ, consumer mới không còn hỗ trợ schema cũ hoặc một trường có thể được ánh xạ an toàn theo quy tắc đã xác nhận.

Transformer phải có phiên bản và kiểm thử, lưu bản gốc hoặc tham chiếu tới bản gốc theo retention policy, không tự suy đoán dữ liệu nghiệp vụ thiếu, giữ event ID và metadata lineage, ghi rõ các trường đã chuyển đổi và kết quả. Không dùng transformer để che một incompatibility chưa được giải quyết.

## 13. DLQ, ordering và partition

Queue có bảo đảm ordering khác nhau. Với message ordering hoặc partition key, đưa một message vào DLQ có thể khiến các message tiếp theo được xử lý trước message lỗi. Điều này có thể chấp nhận với thông báo, nhưng nguy hiểm với trạng thái nghiệp vụ cần thứ tự.

Ví dụ Booking:
- BookingCreated
- PaymentAuthorized
- BookingConfirmed
- BookingCancelled

Nếu PaymentAuthorized bị dead-letter nhưng BookingConfirmed vẫn được xử lý, trạng thái downstream có thể sai.

Cần quyết định:
- Ordering có bắt buộc theo toàn queue, partition, aggregate ID hay không?
- Khi một message lỗi, có được xử lý message sau cùng key không?
- Có cần tạm dừng partition/aggregate đó, nhưng vẫn xử lý key khác?
- Redrive message cũ có cần sắp xếp lại với event phát sinh sau không?
- Có thể rebuild trạng thái từ event log hoặc nguồn dữ liệu chuẩn không?

Với FIFO/ordered systems, cân nhắc mức độ cô lập: dừng cả luồng giảm throughput; tiếp tục xử lý có thể phá thứ tự. Một số dịch vụ có semantics DLQ ảnh hưởng ordering theo cách riêng. Phải kiểm tra đúng dịch vụ và mô hình partition.

## 14. Observability: theo dõi DLQ trước khi nghiệp vụ bị ảnh hưởng

Chỉ nhìn DLQ depth là chưa đủ. Một DLQ có vài message có thể chứa sự cố nghiêm trọng; một DLQ có nhiều message có thể chỉ là sự kiện hết hạn đã được chấp nhận theo nghiệp vụ.

| Metric | Ý nghĩa | Cảnh báo khi |
|---|---|---|
| dlq_messages_visible | Số message sẵn sàng đọc trong DLQ | Tăng bất thường hoặc vượt ngưỡng |
| dlq_oldest_message_age | Tuổi của message cũ nhất | Vượt SLA xử lý/retention |
| dlq_arrival_rate | Tốc độ message mới vào DLQ | Đột biến sau deploy hoặc dependency failure |
| main_queue_age | Tuổi message lâu nhất trong queue chính | Consumer không theo kịp tải |
| delivery_attempts | Số lần giao/thử theo semantics broker | Phân bố tăng bất thường |
| consumer_error_rate | Tỷ lệ lỗi xử lý | Tăng theo event type hoặc version |
| redrive_success_rate | Tỷ lệ message redrive xử lý thành công | Giảm hoặc quay lại DLQ |
| duplicate_suppression_count | Số lần idempotency chặn xử lý trùng | Tăng đột biến sau redrive |
| downstream_latency/throttle | Tình trạng dependency | 429, 5xx hoặc latency cao gây retry |

Alert cần có owner và hành động:
- DLQ non-zero: cảnh báo tới owner nếu nghiệp vụ yêu cầu xử lý mọi event.
- Arrival rate tăng mạnh: phát incident, xem release và dependency.
- Oldest age gần retention limit: ưu tiên triage trước khi message hết hạn.
- Main queue age tăng cùng consumer errors: cân nhắc giảm concurrency hoặc pause retry.
- Redrive thất bại liên tục: tự dừng batch và yêu cầu điều tra.

Không đặt threshold chỉ bằng một số lượng tuyệt đối. Kết hợp volume, tuổi message, loại event và SLA. Với event không quan trọng có thể chấp nhận bỏ theo policy; với payment state, ngay cả một message cũng có thể cần cảnh báo mức cao.

## 15. Bảo mật và quản trị dữ liệu trong DLQ

DLQ thường chứa message lỗi lâu hơn queue chính và có thể được nhiều người truy cập để điều tra. Vì vậy, nó có thể trở thành nơi tập trung dữ liệu nhạy cảm.

Các nguyên tắc:
- Chỉ lưu payload tối thiểu cần thiết; dùng reference ID tới dữ liệu chuẩn nếu phù hợp.
- Mã hóa khi lưu và truyền bằng cơ chế nền tảng, quản lý key và quyền giải mã.
- IAM/RBAC tách biệt quyền xem, redrive, purge và thay đổi policy.
- Redrive/purge cần audit, approval theo mức độ ảnh hưởng.
- Không log full message chứa PII, payment data, token hoặc secret.
- Đặt retention theo nghĩa vụ nghiệp vụ/pháp lý và nhu cầu điều tra.
- Xóa an toàn hoặc hết hạn message theo policy; không giữ vô thời hạn.
- Phân tách DLQ theo domain hoặc mức nhạy cảm để giảm quyền đọc quá rộng.
- Bảo vệ quy trình export/download payload; file điều tra cũng là dữ liệu nhạy cảm.

Một message bị dead-letter không tự nhiên trở nên ít nhạy cảm. Quyền đọc DLQ cần được đánh giá ít nhất nghiêm túc như quyền đọc queue chính, đôi khi chặt hơn vì payload có thể chứa dữ liệu lỗi chưa được làm sạch.

## 16. Kiểm thử DLQ và tình huống lỗi

Không nên chỉ kiểm tra bằng cách gửi message sai rồi xem nó xuất hiện trong DLQ. Cần kiểm thử cả vòng đời:

| Test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Transient failure | Dependency trả 503 vài lần rồi phục hồi | Retry có delay, message cuối cùng xử lý thành công |
| Permanent invalid payload | Thiếu field bắt buộc | Message vào DLQ theo policy, có reason/context |
| Poison message | Một payload liên tục làm consumer crash | Không tạo vòng lặp vô hạn; DLQ và alert hoạt động |
| Worker crash trước ack | Side effect hoàn tất rồi worker chết trước ack | Message có thể giao lại nhưng idempotency ngăn side effect lặp |
| Visibility/lock hết hạn | Xử lý lâu hơn lock | Renewal hoặc redelivery được xử lý an toàn |
| DLQ permission | Consumer/ops thiếu quyền đọc/redrive | Bị từ chối và audit được ghi |
| DLQ retention | Message gần hết hạn | Cảnh báo trước khi mất dữ liệu theo policy |
| Controlled redrive | Sửa consumer rồi redrive batch nhỏ | Message được xử lý, event ID được giữ và không duplicate |
| Redrive regression | Bản sửa chưa khắc phục poison message | Tự dừng hoặc cảnh báo khi quay lại DLQ |
| Downstream overload | Redrive lượng lớn khi dependency yếu | Rate control/backpressure giữ hệ thống ổn định |
| Ordering | Message giữa chuỗi event bị dead-letter | Giữ invariant hoặc cô lập aggregate bị ảnh hưởng |
| Data privacy | Payload DLQ chứa PII | Quyền đọc, retention, encryption và log redaction đúng policy |

Kiểm thử staging cần gần giống semantics queue production; mock đơn giản có thể không mô phỏng chính xác visibility, delivery count, ordering hoặc DLQ behavior của broker thật. Với dịch vụ managed, nên có integration test trên tài nguyên thực được cô lập và có cleanup.

## 17. Runbook xử lý DLQ

Một runbook ngắn cần cung cấp hành động rõ ràng khi cảnh báo xảy ra.

~~~text
1. Nhận alert
   - Xác định DLQ, source queue, owner và mức độ ảnh hưởng.
   - Ghi incident/ticket ID.

2. Khoanh vùng
   - Xem volume, oldest age, arrival rate, event type/schema version.
   - Tìm release, dependency hoặc policy change gần thời điểm phát sinh.

3. Đảm bảo an toàn
   - Không redrive ngay.
   - Hạn chế export payload; dùng quyền đọc phù hợp.
   - Pause consumer/redrive nếu có dấu hiệu tạo side effect sai hoặc quá tải.

4. Điều tra
   - Kiểm tra dead-letter reason, delivery count, correlation ID.
   - Đối chiếu source of truth và trạng thái nghiệp vụ.
   - Phân loại transient, data, schema, business hay security.

5. Khắc phục
   - Rollback/fix consumer, phục hồi dependency, sửa config hoặc data qua quy trình được phê duyệt.
   - Kiểm thử message đại diện.

6. Redrive
   - Chọn batch nhỏ, giữ event ID và giới hạn rate.
   - Theo dõi main queue, consumer, dependency và DLQ quay lại.
   - Dừng nếu lỗi tái diễn.

7. Đối soát và đóng incident
   - Đối chiếu side effect và trạng thái nghiệp vụ.
   - Ghi số thành công, duplicate, bỏ và còn tồn.
   - Cập nhật nguyên nhân gốc, hành động phòng ngừa và alert threshold.
~~~

Các quyết định cần owner phê duyệt:
- Redrive message thanh toán, hoàn tiền hoặc thay đổi trạng thái booking.
- Chỉnh sửa payload nghiệp vụ gốc.
- Purge/xóa message trước thời hạn retention.
- Tắt DLQ hoặc tăng giới hạn giao để xử lý một sự cố.
- Replay lượng lớn message hoặc event có side effect ngoài hệ thống.

Không biến quyền đọc DLQ thành quyền tùy ý sửa payload và phát lại vào production.

## 18. Đánh đổi theo Well-Architected

| Khía cạnh | Lợi ích khi có DLQ | Rủi ro/chi phí cần kiểm soát | Bằng chứng |
|---|---|---|---|
| **Độ tin cậy** | Cô lập message lỗi, tránh retry vô hạn, cho phép phục hồi sau khi sửa | Message có thể hết retention, redrive gây duplicate hoặc sai ordering | Failure injection, idempotency test, recovery drill |
| **Bảo mật** | Giữ lại dữ liệu và metadata để điều tra có kiểm soát | DLQ tập trung PII/secret, quyền đọc/purge quá rộng | IAM review, encryption, audit, retention |
| **Hiệu quả hiệu năng** | Poison message không chiếm worker mãi | Retry/redrive có thể tạo load spike và làm chậm luồng chính | Queue age, throughput, backoff, concurrency tests |
| **Tối ưu chi phí** | Giảm retry lãng phí và incident kéo dài | Storage retention, request, logging và vận hành redrive tạo chi phí | DLQ storage/age, cost per event, lifecycle |
| **Vận hành xuất sắc** | Có nơi điều tra, owner, runbook và số liệu lỗi | DLQ không ai theo dõi sẽ trở thành nghĩa địa message | Alert routing, triage SLA, ownership, incident review |
| **Bền vững** | Retry có kiểm soát giảm xử lý lặp và tài nguyên dư thừa | Giữ message quá lâu, redrive nhiều lần tiêu hao compute/storage | Retention policy, retry budget, batch replay |

Các câu hỏi review quan trọng:
- Có message nào được phép mất hoặc hết hạn không? Owner nào phê duyệt?
- Khi consumer dừng, message giữ lại đủ lâu để phục hồi không?
- Retry có thể làm tăng tải vào dependency đang lỗi không?
- Có biết message ở DLQ thuộc consumer/schema version nào không?
- Ai chịu trách nhiệm xử lý DLQ ngoài giờ làm việc?
- Redrive có thể charge payment, gửi email hoặc phát sự kiện trùng không?
- Data privacy và retention của DLQ đã được review chưa?
- Có diễn tập từ lỗi tới triage, fix, redrive và reconciliation không?

## 19. Bài tập thực hành: xử lý notification event bị lỗi

Một hệ thống đặt chỗ phát BookingConfirmed vào queue. Notification Worker nhận message và gửi email. Sau lần deploy mới, một số message có schemaVersion = 3 nhưng worker chỉ hỗ trợ version 2. Các message đó bị giao lại nhiều lần rồi chuyển vào DLQ. Đồng thời Email Provider có lúc trả 503, khiến một số message khác retry. Đội vận hành thấy DLQ tăng nhưng chưa biết có email nào đã gửi trước khi worker crash hay chưa.

**Yêu cầu:**
1. Phân loại lỗi schema version 3 và HTTP 503.
2. Đề xuất retry policy riêng cho từng loại.
3. Xác định thông tin cần kiểm tra trong DLQ trước redrive.
4. Thiết kế idempotency để tránh gửi cùng email nhiều lần.
5. Viết kế hoạch triển khai worker hỗ trợ version 2 và 3.
6. Đề xuất redrive batch và các chỉ số cần theo dõi.
7. Nêu quyền và quy trình phê duyệt khi đọc, redrive hoặc purge DLQ.

### Hướng giải quyết

- Schema version 3 không được worker v2 hỗ trợ là lỗi compatibility, không nên retry vô hạn. Xác định thay đổi schema, nâng worker hoặc chuyển đổi bằng transformer đã được kiểm thử.
- HTTP 503 là lỗi tạm thời; retry theo exponential backoff, jitter, tôn trọng Retry-After và giới hạn tổng attempts/age.
- Dùng eventId ổn định cùng trạng thái notification trong database hoặc provider idempotency key nếu provider hỗ trợ. Nếu email gửi thành công nhưng worker crash trước ack, lần giao lại phải tra trạng thái hoặc dùng idempotency để tránh gửi lại.
- Triển khai worker tương thích v2/v3, kiểm thử contract và rollout; không chuyển toàn bộ producer sang v3 trước khi consumer cần thiết đã sẵn sàng.
- Đối chiếu Booking state, provider request ID, event ID và log trước khi redrive. Không suy đoán rằng message trong DLQ chưa từng gửi email.
- Redrive một nhóm nhỏ, giới hạn tốc độ, theo dõi DLQ arrival rate, main queue age, consumer errors, duplicate suppression và email provider 429/503.
- Quyền read/inspect tách khỏi quyền redrive/purge; ghi ticket, người duyệt, số lượng và kết quả batch.

### Câu hỏi tự kiểm tra

1. Vì sao retry không giải quyết được một message sai schema?
2. Delivery count có luôn bằng số lần gọi dependency bên ngoài không?
3. Vì sao consumer cần idempotent dù queue có DLQ?
4. Visibility timeout/lock duration quá ngắn gây vấn đề gì?
5. Vì sao redrive giữ nguyên event ID?
6. Khi một message giữa chuỗi event bị dead-letter, ordering có thể bị ảnh hưởng như thế nào?
7. DLQ depth bằng 1 có thể nghiêm trọng hơn depth bằng 100 trong trường hợp nào?
8. Vì sao không nên purge message trước khi đối soát source of truth?
9. Khác biệt chính giữa SQS DLQ, Service Bus dead-letter subqueue và Pub/Sub dead-letter topic là gì?
10. Cần bằng chứng nào để đóng incident DLQ sau khi redrive thành công?

Một kiến trúc sự kiện đáng tin cậy không chỉ định nghĩa cách xử lý message thành công. Nó phải xác định **lỗi nào được retry, lỗi nào cần cách ly, ai điều tra, cách sửa và cách phát lại mà không tạo side effect trùng**. DLQ chỉ phát huy giá trị khi đi cùng idempotent consumer, quan sát đầy đủ, quyền truy cập chặt, retention phù hợp và runbook có người chịu trách nhiệm.
