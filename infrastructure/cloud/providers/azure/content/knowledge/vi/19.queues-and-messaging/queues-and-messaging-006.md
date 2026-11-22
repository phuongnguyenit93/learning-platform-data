# Dead-letter queue và quy trình xử lý message lỗi

## 1. Vì sao hàng đợi cần nơi lưu thông điệp không thể xử lý?

Một hệ thống xử lý đơn hàng trên Microsoft Azure có thể hoạt động theo luồng sau: API nhận đơn hàng, gửi thông điệp vào hàng đợi, một worker lấy thông điệp, kiểm tra dữ liệu rồi ghi vào database và gọi dịch vụ thanh toán. Nếu database tạm thời không phản hồi, worker có thể thử lại. Nhưng nếu thông điệp chứa mã sản phẩm không hợp lệ hoặc được tạo theo một schema đã lỗi thời, việc thử lại hàng trăm lần sẽ không giúp nó thành công.

Nếu ứng dụng liên tục lấy cùng một thông điệp lỗi, hệ thống có thể xuất hiện hiện tượng **poison message**: một thông điệp làm tốn tài nguyên, chặn tiến độ xử lý và tạo retry storm. Nếu bỏ thông điệp không dấu vết, doanh nghiệp mất khả năng điều tra và khôi phục giao dịch.

**Dead-letter queue (DLQ)** là nơi cách ly các thông điệp không thể xử lý thành công theo những điều kiện được xác định. Từ đó, nhóm vận hành có thể điều tra nguyên nhân, sửa lỗi, quyết định phát lại hoặc kết thúc xử lý theo quy trình có kiểm soát.

Bài học thuộc chương **Hàng đợi và thông điệp** trong lộ trình khám phá hệ sinh thái Microsoft Azure. Chúng ta sẽ tập trung vào **Azure Service Bus dead-letter subqueue** và **poison queue của Azure Functions Queue Storage trigger**, đồng thời liên hệ đến Functions, App Service/AKS workers, Microsoft Entra ID, dữ liệu, bảo mật, giám sát và chi phí.

**Điểm cần nhớ ngay:** Azure Service Bus có cơ chế DLQ tích hợp cho queue và subscription; Azure Queue Storage **không có DLQ broker-native tương đương**. Khi dùng Azure Functions Queue trigger, Functions runtime có thể chuyển thông điệp xử lý thất bại nhiều lần sang một **poison queue** được đặt tên theo quy ước. Hai cơ chế này có cách hoạt động và công cụ vận hành khác nhau.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt lỗi tạm thời, lỗi vĩnh viễn và poison message.
2. Giải thích lifecycle của một message từ enqueue, receive, retry đến complete hoặc dead-letter.
3. So sánh Azure Service Bus DLQ với Azure Functions poison queue trên Azure Queue Storage.
4. Hiểu **Peek-Lock**, **Complete**, **Abandon**, **DeadLetter**, **delivery count**, TTL và **MaxDeliveryCount** trong Service Bus.
5. Phân biệt DLQ của queue/subscription với **transfer dead-letter subqueue** khi có forwarding.
6. Thiết kế retries có giới hạn, exponential backoff, jitter và idempotency.
7. Xây dựng runbook **phát hiện → phân loại → sửa nguyên nhân → replay/quarantine → xác minh → audit**.
8. Tránh replay gây xử lý trùng, sai thứ tự, lặp vô hạn hoặc quá tải downstream.
9. Sử dụng Azure CLI/Portal và Java SDK để cấu hình và đọc metadata DLQ trong môi trường được phép.
10. Thiết lập giám sát, cảnh báo, RBAC, bảo vệ dữ liệu và quản lý chi phí cho quy trình xử lý message lỗi.

## 3. Thông điệp bình thường đi qua hệ thống như thế nào?

Một kiến trúc thông dụng:

~~~mermaid
flowchart LR
    API[API Java] --> SB[(Azure Service Bus Queue)]
    SB --> WORKER[Azure Function / AKS Worker]
    WORKER --> VALID{Xử lý thành công?}
    VALID -->|Có| DB[(Database / Storage)]
    DB --> ACK[Complete message]
    VALID -->|Lỗi tạm thời| RETRY[Abandon / retry theo chính sách]
    RETRY --> SB
    VALID -->|Lỗi không thể xử lý| DLQ[(Dead-letter queue)]
    DLQ --> OPS[Điều tra và khắc phục]
~~~

Quy trình lý tưởng:

1. Producer tạo message theo contract đã thống nhất, có **messageId**, loại event, phiên bản schema và correlation ID.
2. Broker lưu message để consumer xử lý bất đồng bộ.
3. Consumer nhận message theo mô hình settlement phù hợp.
4. Khi xử lý thành công và đã ghi kết quả bền vững, consumer xác nhận hoàn thành.
5. Khi lỗi tạm thời, consumer retry trong giới hạn an toàn.
6. Khi không thể xử lý sau chính sách retries hoặc phát hiện lỗi vĩnh viễn, message được cách ly.
7. Nhóm hỗ trợ có dữ liệu và công cụ để khắc phục mà không làm tắc main queue.

DLQ là một **công cụ giữ bằng chứng và phục hồi**, không phải nơi để quên mọi message lỗi.

## 4. Cần phân biệt Service Bus, Queue Storage và các dịch vụ sự kiện

| Dịch vụ/cách sử dụng | Cơ chế xử lý message lỗi | Điều quan trọng |
|---|---|---|
| **Azure Service Bus queue** | Có **dead-letter subqueue** tích hợp | MaxDeliveryCount, TTL và explicit dead-letter |
| **Azure Service Bus topic subscription** | Mỗi subscription có DLQ riêng | Fan-out: subscriber lỗi không nhất thiết ảnh hưởng subscriber khác |
| **Azure Queue Storage** sử dụng SDK trực tiếp | Không có broker-native DLQ như Service Bus | Ứng dụng tự thiết kế queue lỗi/quarantine nếu cần |
| **Azure Queue Storage** qua **Azure Functions Queue trigger** | Functions runtime có thể đưa message vào **<queue-name>-poison** sau giới hạn dequeue | Đây là chức năng Functions extension, không phải DLQ gốc của Storage |
| **Azure Event Grid** | Có cơ chế dead-lettering đến destination được hỗ trợ, thường là Blob Storage, nếu cấu hình | Không mặc định là Service Bus DLQ |
| **Azure Event Hubs** | Không có dead-letter subqueue built-in tương đương Service Bus | Consumer tự xử lý quarantine/checkpoint/replay theo kiến trúc streaming |

**Đừng dùng một câu “Azure Queue tự có DLQ” cho mọi dịch vụ.** Trước khi lập runbook, hãy ghi rõ tên broker, loại entity, trigger extension, cơ chế retry và địa chỉ thực sự chứa message lỗi.

## 5. Azure Service Bus DLQ là gì?

Azure Service Bus hỗ trợ **dead-letter subqueue** gắn với queue và topic subscription. Nó không phải một Azure resource queue độc lập do bạn tạo thủ công. Message được chuyển từ luồng xử lý chính sang subqueue khi broker hoặc ứng dụng xác định điều kiện dead-letter.

Ví dụ queue:

~~~text
Service Bus namespace
└── queue: orders
    ├── Active messages
    └── Dead-letter subqueue
~~~

Ví dụ topic:

~~~text
Service Bus namespace
└── topic: order-events
    ├── subscription: accounting
    │   ├── Active messages
    │   └── Dead-letter subqueue
    └── subscription: notifications
        ├── Active messages
        └── Dead-letter subqueue
~~~

Cấu trúc này giúp mỗi consumer group thông qua subscription có lịch sử lỗi riêng. Một message có thể được xử lý thành công trong subscription **notifications** nhưng bị dead-letter ở **accounting** do rule nghiệp vụ khác.

### 5.1. Những điều Service Bus DLQ không tự làm

- Không tự hiểu thông điệp sai nghiệp vụ.
- Không tự sửa dữ liệu hay đổi schema.
- Không tự retry message từ DLQ sang active queue sau một khoảng thời gian.
- Không tự tạo dashboard phân loại nguyên nhân.
- Không tự đảm bảo một lần replay sẽ không sinh giao dịch trùng.
- Không tự đảm bảo thông điệp lỗi được xóa sau một ngày nhất định.

Vì vậy, nếu chỉ bật DLQ nhưng không có runbook và cảnh báo, hệ thống vẫn có thể tích lũy hàng nghìn giao dịch chưa hoàn tất.

## 6. Khi nào message đi vào Service Bus DLQ?

Những nguyên nhân thường gặp:

| Nguyên nhân | Cơ chế | Hướng điều tra |
|---|---|---|
| **MaxDeliveryCountExceeded** | Số lần delivery vượt giới hạn của entity theo cơ chế broker | Consumer lỗi, abandon hoặc lock hết hạn liên tục |
| **TTLExpiredException** hoặc expiration reason tương ứng | Message hết TTL khi entity bật dead-letter on expiration | Quá tải, backlog, TTL quá ngắn |
| **Explicit dead-letter** | Ứng dụng gọi API dead-letter khi phát hiện điều kiện không thể xử lý | Payload sai, vi phạm hợp đồng, dữ liệu thiếu |
| **Filter evaluation error** (một số subscription settings) | Broker gặp lỗi khi đánh giá filter theo tính năng cấu hình | Rule của topic subscription |
| **Forwarding/transfer failure** | Một số lỗi khi auto-forward có thể dẫn đến transfer DLQ | Đích forward, quota, cấu hình liên kết |

Không phải mọi exception của consumer đều lập tức đưa message vào DLQ. Với **Peek-Lock**, nếu consumer bỏ lock hoặc lock hết hạn, message có thể được giao lại. Việc dead-letter tự động chỉ xảy ra sau khi đạt điều kiện broker đã quy định.

### 6.1. MaxDeliveryCount

Một Service Bus queue/subscription có thể được cấu hình **MaxDeliveryCount**, giới hạn số lần broker cho phép message được delivery lại trước khi dead-letter theo chính sách. Ví dụ lab chọn **5** để dễ quan sát.

Điều này không có nghĩa một message chắc chắn được gọi handler đúng 5 lần: crashes, lock renewals, prefetch, client behavior và thời điểm settlement đều ảnh hưởng dấu vết thực tế.

### 6.2. Hết TTL

**Time-to-live (TTL)** biểu diễn thời hạn message còn hợp lệ theo broker. Với entity bật tùy chọn dead-letter on expiration, message hết hạn có thể xuất hiện trong DLQ. Nếu không bật, thông điệp hết hạn có thể bị loại bỏ mà không có bản trong DLQ theo cơ chế entity.

Không đặt TTL quá ngắn nếu có thể xuất hiện backlog hợp lệ; đồng thời không giữ message giao dịch vô hạn mà không có chính sách dữ liệu rõ ràng.

### 6.3. Explicit dead-letter

Ứng dụng chủ động gọi dead-letter khi dữ liệu hoặc điều kiện là **không thể xử lý bằng retry thông thường**, ví dụ schema không được hỗ trợ hoặc tham chiếu tenant không hợp lệ đã được xác minh.

Cần đặt **dead-letter reason** rõ ràng, **description** ngắn và không lộ dữ liệu nhạy cảm.

## 7. Peek-Lock, Complete, Abandon và DeadLetter

Service Bus hỗ trợ các mô hình receive như **Peek-Lock** và **Receive-and-Delete**.

### 7.1. Peek-Lock

Khi nhận message ở chế độ Peek-Lock:

1. Consumer lấy được message với một lock có thời hạn.
2. Broker không xóa message ngay.
3. Consumer xử lý và thực hiện settlement.
4. Nếu xử lý thành công, **Complete** loại message khỏi luồng nhận.
5. Nếu consumer **Abandon** hoặc lock hết hạn, message có thể được nhận lại.
6. Nếu consumer gọi **DeadLetter**, message được đưa sang DLQ.
7. Nếu message bị delivery lại quá số lần theo MaxDeliveryCount, broker có thể tự dead-letter.

~~~mermaid
flowchart TD
    READY[Active message] --> RECEIVE[Receive với Peek-Lock]
    RECEIVE --> WORK{Xử lý}
    WORK -->|Thành công| COMPLETE[Complete]
    WORK -->|Lỗi có thể retry| ABANDON[Abandon / lock expires]
    ABANDON --> READY
    WORK -->|Lỗi vĩnh viễn| DEAD[Explicit DeadLetter]
    READY --> CHECK{Delivery count vượt giới hạn?}
    CHECK -->|Có| DLQ[Dead-letter subqueue]
    DEAD --> DLQ
~~~

### 7.2. Receive-and-Delete

Với Receive-and-Delete, broker loại message khi giao cho consumer, không chờ ứng dụng Complete. Nếu consumer chết ngay sau khi nhận, dữ liệu có thể mất. Cơ chế này không phù hợp khi nghiệp vụ cần khả năng retry/dead-letter sau xử lý thất bại.

**Với thanh toán, đơn hàng, xuất hóa đơn hoặc công việc quan trọng, ưu tiên một mô hình settlement có thể phục hồi**, và thiết kế idempotency để xử lý trường hợp nhận trùng.

### 7.3. Lock duration và gia hạn

Xử lý lâu có thể khiến lock hết hạn trước khi Complete; message có thể được giao cho worker khác. Service Bus SDK có cơ chế auto-renew lock trong những điều kiện/cấu hình được hỗ trợ.

Đừng coi gia hạn lock là vô hạn. Nếu job dài hoặc chạy nhiều bước, cân nhắc chia công việc, checkpoint hoặc dùng cơ chế workflow thích hợp.

## 8. Dead-letter subqueue và transfer DLQ không giống nhau

Trong Service Bus:

- **Dead-letter subqueue thông thường** chứa những message lỗi của queue/subscription: max delivery, TTL hoặc dead-letter do ứng dụng.
- **Transfer dead-letter subqueue** liên quan một số tình huống lỗi chuyển tiếp khi dùng auto-forwarding hoặc transfer, không nên gộp với lỗi nghiệp vụ consumer.

Trong một namespace có auto-forwarding, runbook nên phân loại:

~~~text
Message không xử lý được do business validation
  -> DLQ của entity nhận

Message không forward được tới đích
  -> Điều tra transfer DLQ / forwarding path
~~~

Nếu nhìn thấy transfer DLQ tăng, sửa handler nghiệp vụ ở đích chưa chắc giải quyết nguyên nhân. Hãy kiểm tra đích forward, quyền, cấu hình forwarding, giới hạn hop/size/quota và trạng thái entity.

## 9. Azure Queue Storage có poison queue khi nào?

**Azure Queue Storage bản thân không cung cấp dead-letter subqueue tương tự Service Bus**. Nó lưu message, hỗ trợ nhận, visibility timeout, dequeue count và xóa message khi hoàn thành. Ứng dụng dùng SDK trực tiếp phải tự xây dựng logic quarantine nếu muốn có nơi lưu message lỗi riêng.

Khi xử lý Azure Queue Storage thông qua **Azure Functions Queue trigger**, Functions runtime theo extension hỗ trợ cơ chế:

1. Đọc message từ queue đầu vào.
2. Gọi function.
3. Khi function thất bại, message có thể được thử lại theo cấu hình.
4. Khi vượt giới hạn **maxDequeueCount**, runtime đưa message vào một queue có tên theo quy ước **<original-queue-name>-poison**.

Ví dụ:

~~~text
Azure Storage account
├── queue: orders
└── queue: orders-poison
~~~

**orders-poison** không phải Service Bus DLQ. Nó là một queue Azure Storage thông thường được Functions runtime sử dụng theo quy ước. Phần mềm của bạn vẫn cần theo dõi, đọc, phân loại và quyết định xử lý tiếp.

### 9.1. Ví dụ host.json cho Queue trigger

~~~json
{
  "version": "2.0",
  "extensions": {
    "queues": {
      "batchSize": 4,
      "newBatchThreshold": 2,
      "visibilityTimeout": "00:00:30",
      "maxDequeueCount": 5
    }
  }
}
~~~

Ở một Functions Queue extension tương thích:

- **maxDequeueCount** giới hạn số lần thử nhận/xử lý trước khi chuyển sang poison queue.
- **visibilityTimeout** ảnh hưởng khoảng trì hoãn message xuất hiện lại sau lỗi theo cơ chế runtime.
- **batchSize/newBatchThreshold** liên quan mức lấy và xử lý song song, không phải trực tiếp số lần retry.

Khi runtime bật **dynamic concurrency** hoặc dùng extension version khác, các thuộc tính concurrency có thể có hiệu lực khác. Cần đối chiếu tài liệu extension đang chạy.

### 9.2. Khác biệt quan trọng khi vận hành

Không thể dùng Service Bus SDK **SubQueue.DEAD_LETTER_QUEUE** để đọc **orders-poison** của Azure Storage. Với poison queue này, dùng Azure Queue Storage APIs/SDK hoặc Azure Portal/Storage Explorer và quyền Storage tương ứng.

## 10. Vì sao message lỗi lặp lại được gọi là poison message?

Poison message là message khiến consumer liên tục thất bại hoặc không thể tiến bộ trong điều kiện xử lý hiện tại.

Một số ví dụ:

- JSON không thể parse.
- Schema cũ thiếu trường bắt buộc.
- ID tham chiếu không tồn tại và không bao giờ xuất hiện.
- Một chuỗi bất hợp lệ làm parser throw exception.
- Payload vượt giới hạn xử lý của ứng dụng.
- Message yêu cầu quyền mà người dùng/tenant không có.
- Handler chứa bug khiến một loại sự kiện luôn crash.
- Tài nguyên dependency không bao giờ sẵn sàng theo chính sách đã quyết định.

**Không phải message thất bại lần đầu đều là poison.** Database timeout hoặc lỗi mạng ngắn hạn có thể thành công khi thử lại. Phải phân loại nguyên nhân trước khi kết luận.

### 10.1. Poison message làm tắc hệ thống bằng cách nào?

Nếu một consumer luôn lấy message A, xử lý lỗi, nhận lại ngay rồi lặp vô hạn, nó có thể chiếm CPU/requests, tạo chi phí và làm message tốt ở phía sau bị trì hoãn.

DLQ giúp tách A khỏi luồng chính để các messages còn lại tiếp tục chạy, nhưng phải có runbook để A không bị lãng quên.

## 11. Phân loại lỗi: transient, permanent và unknown

| Loại lỗi | Ví dụ | Chính sách hợp lý |
|---|---|---|
| **Transient** | Timeout ngắn, HTTP 503, database failover, giới hạn rate tạm thời | Retry có giới hạn và backoff/jitter |
| **Permanent/data** | JSON không hợp lệ, schema không hỗ trợ, dữ liệu vi phạm quy tắc | Dead-letter hoặc quarantine để điều tra |
| **Permanent/authorization** | Không có quyền nghiệp vụ do dữ liệu/tenant thật sự không hợp lệ | Không retry vô hạn; xác minh quyền và quyết định |
| **Infrastructure/config** | Key Vault permission bị thiếu, DNS sai, sai connection setting | Cảnh báo và sửa cấu hình; retry có kiểm soát |
| **Unknown** | Exception chưa được phân loại | Retry budget nhỏ, đo đạc, cách ly nếu không khắc phục |
| **Processing conflict** | Đơn hàng đã xử lý, duplicate key, tranh chấp dữ liệu | Kiểm tra idempotency; có thể Complete thay vì coi là lỗi |

Không nên dùng một quy tắc cứng “mọi lỗi 4xx thì dead-letter, mọi 5xx thì retry” vì từng API có contract riêng. Ví dụ HTTP 409 có thể đại diện dữ liệu đã được xử lý thành công theo idempotency hoặc một xung đột cần retry với version mới.

### 11.1. Chú ý lỗi do message và lỗi do hệ thống

Nếu một Function App mất quyền truy cập database, **mọi message** có thể thất bại. Dead-letter hàng loạt lúc này làm phức tạp khôi phục mà không sửa được root cause. Cần alert, giảm tốc xử lý, circuit breaker hoặc tạm dừng consumer theo quy trình.

### 11.2. Chú ý dữ liệu độc hại

Một message có thể được cố ý tạo để khai thác parser, gây tràn bộ nhớ hoặc injection. Không tự phát lại payload chưa được kiểm tra từ nguồn không tin cậy; xử lý trong vùng phân tích an toàn và giới hạn kích thước.

## 12. Chính sách retry tốt phải có giới hạn

Với lỗi tạm thời, retry hữu ích nếu lỗi có khả năng tự hồi phục. Nhưng retry không giới hạn làm tăng tải và chi phí.

Một mô hình backoff:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Trong đó \(d_0\) là thời gian chờ ban đầu, \(d_{\max}\) là giới hạn cao nhất, \(n\) là lần retry. Nên thêm **jitter** để nhiều consumers không retry đồng thời.

Ví dụ kế hoạch:

| Lần thử | Chờ trước khi thử lại (ví dụ) |
|---|---:|
| 1 | 0 giây |
| 2 | ~2 giây |
| 3 | ~4 giây |
| 4 | ~8 giây |
| 5 | ~16 giây |

Đây chỉ là mô hình minh họa. Với Service Bus Peek-Lock, **Abandon** có thể làm message sẵn sàng lại sớm theo cơ chế broker, chứ không nhất thiết chờ theo dãy backoff bạn tính. Muốn trì hoãn giữa các lần xử lý phải thiết kế scheduler/delayed retries hoặc một giải pháp ứng dụng phù hợp; không nên dùng Thread.sleep trong handler để giả lập retry dài.

### 12.1. Retry ở nhiều tầng gây nhân số lần thử

Nếu SDK retry 3 lần, handler retry 4 lần và broker redeliver 5 lần, hệ thống có thể tạo rất nhiều lời gọi downstream.

Cần có **retry budget tổng**, xác định tầng chịu trách nhiệm retry và số lần tối đa ở mỗi tầng.

### 12.2. Retry không nên kéo dài hơn giá trị nghiệp vụ

Một lệnh đặt hàng hết hiệu lực sau 5 phút có thể không còn ý nghĩa để retry sau 2 giờ. TTL và retry windows phải phản ánh yêu cầu nghiệp vụ.

## 13. Bộ trạng thái nghiệp vụ cho message lỗi

Không chỉ dựa vào trạng thái broker. Một workflow nghiệp vụ có thể cần trạng thái riêng:

~~~text
RECEIVED
  -> PROCESSING
  -> COMPLETED

PROCESSING
  -> RETRY_SCHEDULED
  -> FAILED_PERMANENT
  -> QUARANTINED
  -> UNDER_INVESTIGATION
  -> READY_TO_REPLAY
  -> REPLAYED
  -> VERIFIED
  -> CLOSED
~~~

Các trạng thái này có thể được lưu trong một bảng audit/operations hoặc hệ thống ticketing, không nhất thiết có sẵn trong broker.

Một message đã **REPLAYED** không có nghĩa nghiệp vụ đã **COMPLETED**. Phải theo dõi execution mới cho tới khi xác nhận kết quả thật.

### 13.1. Tách technical state và business outcome

Ví dụ:

- Service Bus DLQ message count giảm từ 10 xuống 9.
- Message được gửi lại active queue.
- Worker mới vẫn lỗi và đưa message vào DLQ lần nữa.

Nếu dashboard chỉ nhìn DLQ count, có thể tưởng hệ thống đã giải quyết được lỗi. Cần đối chiếu business status, correlation ID và lịch sử replay.

## 14. Thiết kế message envelope để điều tra dễ hơn

Thông điệp nên có metadata phục vụ trace:

~~~json
{
  "eventType": "OrderSubmitted",
  "schemaVersion": 2,
  "eventId": "evt-demo-001",
  "correlationId": "corr-demo-001",
  "occurredAt": "2026-11-20T08:30:00Z",
  "tenantId": "tenant-demo",
  "data": {
    "orderId": "ORD-1001",
    "customerId": "C-50",
    "amount": 125000
  }
}
~~~

Đây là ví dụ với dữ liệu giả. Trong Azure Service Bus, một số metadata như **MessageId**, **CorrelationId**, **Subject**, **ApplicationProperties** được lưu ở message metadata riêng, không nhất thiết đều phải lặp trong JSON body.

### 14.1. Những trường nên giữ

- **MessageId/eventId**: định danh message/business event.
- **CorrelationId/traceId**: liên kết luồng từ API đến consumers.
- **SchemaVersion/eventType**: giúp hiểu parser và contract.
- **Enqueued time**: xác định backlog hoặc độ trễ.
- **Delivery count**: biết số lần broker đã delivery theo cơ chế tương ứng.
- **DeadLetterReason**: lý do phân loại ngắn, có chuẩn.
- **DeadLetterErrorDescription**: mô tả đã lọc thông tin nhạy cảm.
- **Source entity/subscription**: message đến từ đâu.
- **Producer version/consumer version** nếu có và được duy trì nhất quán.

### 14.2. Dữ liệu không nên đưa vào reason/description

Không lưu access token, connection string, mật khẩu, số thẻ, email đầy đủ hoặc nội dung người dùng nhạy cảm trong trường lỗi. Những trường này có thể được hiển thị trong công cụ vận hành, log hoặc support ticket.

### 14.3. Schema version và compatibility

Một nguyên nhân DLQ phổ biến là producer phát schema mới nhưng consumer chưa cập nhật. Thiết kế versioning và backward/forward compatibility giúp tránh lỗi không thể parse trên diện rộng.

## 15. DeadLetterReason và DeadLetterErrorDescription trong Service Bus

Khi dead-letter thủ công, nên dùng một tập **reason code có kiểm soát**.

Ví dụ:

| Reason code | Khi dùng | Đội phụ trách |
|---|---|---|
| **InvalidSchema** | JSON/schema sai hoặc version không được hỗ trợ | Producer/consumer team |
| **BusinessRuleRejected** | Dữ liệu vi phạm điều kiện nghiệp vụ đã xác minh | Business/consumer team |
| **UnknownEntity** | Không tìm thấy mã tham chiếu cần thiết | Data owner |
| **DependencyUnavailable** | Hết retry budget do downstream không sẵn sàng | Platform/dependency owner |
| **UnauthorizedTenant** | Tenant không được phép thực hiện hành động | Security/business |
| **UnclassifiedFailure** | Chưa xác định được nguyên nhân | On-call team |

Đừng đặt reason thành toàn bộ stack trace. Stack trace có thể dài, chứa nội dung nhạy cảm và thay đổi theo build version, khiến thống kê nguyên nhân khó hơn.

Một ví dụ thông tin nên lưu:

~~~text
DeadLetterReason: InvalidSchema
DeadLetterErrorDescription:
  EventType=OrderSubmitted; SchemaVersion=9 không được hỗ trợ;
  ContractVersionSupported=1..2; IncidentRef=INC-1042
~~~

Nếu reason được broker tạo tự động, cần bảo toàn metadata gốc để hiểu lỗi. Không tự ghi đè rằng mọi message dead-letter đều do ứng dụng không hợp lệ.

## 16. Cấu hình Service Bus queue trong Azure CLI

Ví dụ sau chỉ dành cho môi trường lab được phép, cần Azure subscription, quyền tạo resource group/Service Bus và tên namespace duy nhất.

~~~bash
az login
az account set --subscription "<subscription-id>"

az group create \
  --name rg-messaging-lab \
  --location southeastasia

az servicebus namespace create \
  --resource-group rg-messaging-lab \
  --name sb-messaging-lab-unique \
  --location southeastasia \
  --sku Standard
~~~

Tạo queue với MaxDeliveryCount thấp để kiểm thử:

~~~bash
az servicebus queue create \
  --resource-group rg-messaging-lab \
  --namespace-name sb-messaging-lab-unique \
  --name orders \
  --max-delivery-count 5 \
  --enable-dead-lettering-on-message-expiration true
~~~

**Lưu ý:**

- **sb-messaging-lab-unique** chỉ là placeholder; tên namespace phải hợp lệ và khả dụng.
- Các cờ CLI và tính năng cần kiểm tra với phiên bản Azure CLI/extension thực tế. Nếu lệnh không hỗ trợ một cờ, đối chiếu help/tài liệu của chính môi trường; không tự đổi loại queue hoặc bypass chính sách.
- Giá trị **MaxDeliveryCount=5** nhằm làm bài lab dễ quan sát, không nhất thiết phù hợp production.
- Bật dead-letter on expiration giúp đưa thông điệp hết hạn vào DLQ theo cơ chế broker, nhưng không đồng nghĩa mọi expired message sẽ được xử lý ngay tức thời như một sự kiện business.

Xem queue:

~~~bash
az servicebus queue show \
  --resource-group rg-messaging-lab \
  --namespace-name sb-messaging-lab-unique \
  --name orders \
  --output json
~~~

Đối chiếu các thuộc tính như **maxDeliveryCount**, **deadLetteringOnMessageExpiration**, **countDetails** và các trường có sẵn trong output.

## 17. Kiểm tra DLQ bằng Azure Portal

Một quy trình quan sát không phá hủy:

1. Mở **Azure Portal → Service Bus namespaces**.
2. Chọn namespace thử nghiệm.
3. Mở danh sách **Queues** hoặc **Topics → Subscriptions**.
4. Chọn entity đang điều tra.
5. Xem số lượng **Active messages**, **Dead-lettered messages** và những thông tin monitor được hiển thị.
6. Mở công cụ **Service Bus Explorer** trong Portal nếu chức năng và quyền hỗ trợ.
7. Chọn **dead-letter subqueue** đúng của queue hoặc subscription.
8. Dùng **Peek** để xem metadata và nội dung cần thiết theo quyền/kiểm soát dữ liệu.
9. Ghi messageId, reason, deliveryCount, enqueue time và correlation ID.
10. **Không bấm Complete/Delete/Resubmit** chỉ vì thấy message cũ; cần phê duyệt và đánh giá trước.

Tên menu và khả năng của Service Bus Explorer có thể thay đổi. Nếu tài khoản chỉ có quyền đọc metadata và không có quyền data-plane để đọc message, phải yêu cầu đúng quyền theo quy trình, không sử dụng khóa kết nối có đặc quyền cao để làm đường tắt.

### 17.1. Peek khác Receive

**Peek** đọc để kiểm tra mà không lấy lock và không làm message bị settlement, phù hợp giai đoạn điều tra. **Receive** ở Peek-Lock lấy message để consumer xử lý/settle, nên có khả năng thay đổi delivery/lock behavior.

Với DLQ production, nên ưu tiên **Peek** khi mục tiêu chỉ là quan sát.

## 18. Java SDK: đọc metadata DLQ không phá hủy

Ví dụ dùng Azure SDK for Java và **DefaultAzureCredential** để đọc message metadata từ DLQ của queue **orders**. Cần có các dependency **azure-messaging-servicebus** và **azure-identity** phiên bản phù hợp trong dự án của bạn.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusReceiverClient;
import com.azure.messaging.servicebus.models.ServiceBusReceiveMode;
import com.azure.messaging.servicebus.models.SubQueue;
import com.azure.messaging.servicebus.models.ServiceBusReceivedMessage;

public class InspectDeadLetters {
    public static void main(String[] args) {
        String namespace = "sb-messaging-lab-unique.servicebus.windows.net";

        try (ServiceBusReceiverClient receiver =
                 new ServiceBusClientBuilder()
                     .credential(
                         namespace,
                         new DefaultAzureCredentialBuilder().build())
                     .receiver()
                     .queueName("orders")
                     .subQueue(SubQueue.DEAD_LETTER_QUEUE)
                     .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
                     .buildClient()) {

            for (ServiceBusReceivedMessage message :
                    receiver.peekMessages(10)) {
                System.out.println("MessageId: " + message.getMessageId());
                System.out.println("Reason: " + message.getDeadLetterReason());
                System.out.println("Description: "
                        + message.getDeadLetterErrorDescription());
                System.out.println("DeliveryCount: "
                        + message.getDeliveryCount());
            }
        }
    }
}
~~~

Giải thích:

- **credential(namespace, credential)** dùng Microsoft Entra identity theo cơ chế SDK.
- **SubQueue.DEAD_LETTER_QUEUE** chỉ rõ nguồn là Service Bus dead-letter subqueue.
- **peekMessages(10)** chỉ xem messages, không Complete và không xóa.
- Message metadata được in để minh họa, không in raw body hoặc secret.
- Tài khoản chạy phải có **quyền data-plane nhận/đọc** phù hợp trên entity. Azure ARM Reader không mặc nhiên cho phép đọc nội dung messages.

**Lưu ý phiên bản:** tên API và enum phải được đối chiếu theo dependency version thực tế. Đây là ví dụ cho SDK Azure Service Bus Java hiện đại, không phải SDK legacy.

### 18.1. Vì sao không dùng connection string trong ví dụ chính?

SAS connection strings chứa credential nhạy cảm và dễ bị ghi vào log/source. Trong Azure, nên ưu tiên managed identity và role assignments phù hợp; trên máy dev có thể sử dụng Azure CLI sign-in qua DefaultAzureCredential theo cấu hình.

Nếu buộc phải dùng SAS trong môi trường test, lưu trong secret store và không đưa vào Git hoặc chat.

## 19. Java SDK: explicit dead-letter khi dữ liệu sai

Một consumer dùng Peek-Lock có thể chủ động chuyển message lỗi không thể phục hồi sang DLQ.

Ví dụ minh họa **chỉ phần settlement sau khi đã nhận message**:

~~~java
import com.azure.messaging.servicebus.ServiceBusReceiverClient;
import com.azure.messaging.servicebus.models.DeadLetterOptions;
import com.azure.messaging.servicebus.models.ServiceBusReceivedMessage;

public final class MessageSettlement {
    private MessageSettlement() {}

    public static void rejectInvalidPayload(
            ServiceBusReceiverClient receiver,
            ServiceBusReceivedMessage message) {
        DeadLetterOptions options = new DeadLetterOptions()
            .setDeadLetterReason("InvalidSchema")
            .setDeadLetterErrorDescription(
                "Message body khong dung schema version duoc ho tro");

        receiver.deadLetter(message, options);
    }
}
~~~

Những điều kiện phải có:

- Receiver đã nhận message ở **Peek-Lock** và vẫn giữ lock hợp lệ.
- Ứng dụng đã xác minh lỗi là vĩnh viễn hoặc chính sách yêu cầu cách ly.
- Không Complete message sau khi đã dead-letter thành công.
- Nếu dead-letter API thất bại do lock mất hoặc broker lỗi, ghi log và xử lý exception đúng; không giả định message đã nằm trong DLQ.
- Không đưa toàn bộ message body vào error description.

Nếu consumer được Azure Functions Service Bus trigger quản lý settlement tự động, **đừng ghép ví dụ trên một cách máy móc**. Phải xem trigger/binding và khả năng manual message settlement của phiên bản Functions SDK trước khi gọi complete/dead-letter.

## 20. Azure Functions Service Bus trigger và DLQ

Azure Functions có thể dùng **Service Bus trigger** để nhận message. Khi một invocation thất bại, hành vi abandon/retry/lock renewal được quyết định bởi runtime, extension và cấu hình handler. Sau khi delivery count vượt giới hạn entity, Service Bus có thể đưa message vào DLQ.

Một ví dụ Java Functions trigger dạng tối giản:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.ServiceBusQueueTrigger;

public class OrdersConsumer {
    @FunctionName("processOrder")
    public void run(
        @ServiceBusQueueTrigger(
            name = "message",
            queueName = "orders",
            connection = "ServiceBusConnection")
        String message,
        ExecutionContext context) {

        context.getLogger().info("Received order message");
        // Validate va xu ly nghiep vu.
        // Khi throw exception, settlement/retry phu thuoc extension.
    }
}
~~~

**ServiceBusConnection** chỉ là tên cấu hình connection. Với các phiên bản Azure Functions/extension có hỗ trợ identity-based connection, cấu hình có thể dùng prefix app settings tương ứng thay vì một SAS connection string; cần xác nhận runtime/extension/SDK hỗ trợ.

### 20.1. Throw exception có luôn tự dead-letter không?

Không. Function thất bại có thể làm message được abandon hoặc lock hết hạn, và broker có thể delivery lại. Chỉ khi đạt điều kiện như **MaxDeliveryCountExceeded** hoặc ứng dụng chủ động dead-letter bằng API được hỗ trợ, message mới nằm trong DLQ.

### 20.2. Manual settlement

Một số binding/runtime/extension hỗ trợ nhận đối tượng message cùng **message actions** để Complete/Abandon/DeadLetter thủ công. Khả năng này tùy ngôn ngữ và phiên bản. Khi dùng manual settlement, phải tắt hoặc điều chỉnh auto-complete đúng cách theo tài liệu phù hợp để tránh double settlement.

### 20.3. Không retry cùng lúc ở ba tầng mà không tính toán

Azure SDK, Functions runtime và Service Bus broker đều có thể liên quan đến retry. Việc trộn retry trong code, host.json và broker redelivery không được kiểm soát có thể tạo quá nhiều attempts.

## 21. Azure Functions Queue trigger và poison messages

Với Azure Queue Storage trigger trong Functions, sau số lần dequeue không thành công theo **maxDequeueCount**, runtime có thể chuyển message sang **<queue-name>-poison**.

Một handler Java mẫu:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.QueueTrigger;

public class QueueOrderConsumer {
    @FunctionName("processStorageOrder")
    public void run(
        @QueueTrigger(
            name = "message",
            queueName = "orders",
            connection = "AzureWebJobsStorage")
        String message,
        ExecutionContext context) {

        context.getLogger().info("Queue message received");
        // Khi xu ly khong thanh cong, throw exception theo contract.
    }
}
~~~

Lưu ý:

- Đây là **Azure Storage Queue** trigger, không phải Service Bus trigger.
- Queue **orders-poison** là queue thực sự trong Storage account theo quy ước runtime, không phải Service Bus subqueue.
- Message được runtime đưa vào poison queue theo hành vi của extension; việc bảo toàn metadata nguyên gốc có thể khác với Service Bus DLQ.
- Nếu sử dụng SDK để dequeue/xử lý Queue Storage **không thông qua Functions trigger**, bạn phải tự xây cơ chế poison/quarantine.
- Không dùng cùng một quy trình xóa và quyền truy cập cho Service Bus và Storage Queue vì chúng là hai dịch vụ khác nhau.

### 21.1. Poison queue vẫn có lifecycle riêng

Poison queue có thể tiếp tục tăng nếu không có người xử lý. Nó cũng chịu quy tắc message TTL, quyền và giới hạn của Azure Storage Queues. Đừng coi việc message đã vào poison queue đồng nghĩa đã được lưu mãi mãi hoặc đã được backup.

## 22. Quy trình xử lý message lỗi: tám bước

Một runbook đáng tin cậy nên thực hiện theo thứ tự:

~~~mermaid
flowchart TD
    ALERT[1. Phát hiện DLQ tăng] --> FREEZE[2. Đánh giá phạm vi / ngăn lan rộng]
    FREEZE --> PEEK[3. Peek, thu metadata an toàn]
    PEEK --> CLASS[4. Phân loại lỗi]
    CLASS --> FIX[5. Sửa root cause / dữ liệu / code]
    FIX --> APPROVE[6. Phê duyệt phương án]
    APPROVE --> ACTION{Quyết định}
    ACTION -->|Replay| REPLAY[7a. Phát lại có giới hạn]
    ACTION -->|Quarantine| HOLD[7b. Giữ và điều tra thêm]
    ACTION -->|Close| CLOSE[7c. Kết thúc theo chính sách]
    REPLAY --> VERIFY[8. Xác minh outcome và audit]
    HOLD --> VERIFY
    CLOSE --> VERIFY
~~~

### Bước 1 — Phát hiện

Tạo alert khi DLQ count tăng bất thường, age tăng hoặc số business operations chưa hoàn tất vượt SLO. Không chỉ nhìn con số tuyệt đối.

### Bước 2 — Đánh giá phạm vi

Xác định lỗi chỉ xảy ra với một message, một partition/subscription, một phiên bản producer hay toàn hệ thống. Nếu đang có một đợt lỗi diện rộng, cân nhắc ngăn tiếp tục tạo poison messages bằng cách sửa producer/consumer hoặc điều chỉnh tiếp nhận theo runbook, thay vì xóa dữ liệu.

### Bước 3 — Đọc metadata không phá hủy

Ưu tiên Peek; ghi correlation ID, reason, eventType, schema version, nguồn và thời gian. Không copy dữ liệu khách hàng vào ticket công khai.

### Bước 4 — Phân loại

Đánh giá lỗi transient, permanent, config, data, duplicate hoặc unknown. Phân biệt lỗi bên gửi và lỗi bên nhận.

### Bước 5 — Sửa gốc

Sửa bug handler, schema compatibility, quyền, DNS, cấu hình hoặc dữ liệu tham chiếu. Replay khi chưa sửa nguyên nhân chỉ đẩy message vòng lại DLQ.

### Bước 6 — Phê duyệt

Quyết định rõ message nào được replay, có cần chỉnh payload không, người phê duyệt là ai, xử lý side effects như thanh toán/hóa đơn ra sao.

### Bước 7 — Replay/quarantine/close

Thực hiện theo nhóm nhỏ và rate limit; có khả năng dừng ngay khi errors tăng. Với lỗi không thể khắc phục, lưu audit và kết thúc theo chính sách retention/compliance.

### Bước 8 — Xác minh

Đối chiếu outcome nghiệp vụ, không chỉ DLQ count. Lưu thời điểm, người thao tác, source message ID, target message ID và kết quả.

## 23. Cần kiểm tra những gì trước khi replay?

Danh sách tối thiểu:

- Message thuộc entity và môi trường nào: dev/staging/prod?
- Message còn giá trị nghiệp vụ không hay đã hết hiệu lực?
- Đã có consumer khác xử lý thành công chưa?
- Có payment, email, inventory hoặc workflow side effect nào đã xảy ra?
- Source schema còn được phiên bản consumer hiện tại hỗ trợ không?
- Message có phụ thuộc vào thứ tự xử lý hoặc Service Bus session không?
- Các reference IDs trong database còn tồn tại và đúng tenant?
- Lỗi gốc đã được xác nhận khắc phục chưa?
- Target queue/topic/subscription đúng không?
- Replay có cần giữ MessageId/CorrelationId hoặc tạo một MessageId mới?
- Duplicate detection của Service Bus có thể làm broker bỏ bản gửi mới không?
- Có ngân sách, rate limit, cảnh báo và kế hoạch rollback/recovery không?
- Ai duyệt, ai chạy và ai xác minh?

**Không replay hàng nghìn messages chỉ dựa trên việc một message mẫu chạy thành công.** Phân loại theo reason, schema version, thời điểm, tenant và độ rủi ro; thử một batch nhỏ trước.

## 24. Replay an toàn: vì sao send trước, Complete sau?

Một thuật toán replay phổ biến cho Service Bus DLQ:

1. Receive message từ DLQ bằng Peek-Lock.
2. Kiểm tra metadata và quyết định đủ điều kiện replay.
3. Tạo **message mới** cho queue/topic đích với body và application properties hợp lệ.
4. Ghi trace metadata như originalMessageId và replayAttempt.
5. Send message mới và chờ broker xác nhận thành công.
6. **Chỉ sau đó Complete** message nguồn đang khóa trong DLQ.
7. Ghi audit và theo dõi message mới tới outcome nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant O as Replay worker
    participant DL as Service Bus DLQ
    participant Q as Active Queue
    participant A as Audit Store
    O->>DL: Receive message (Peek-Lock)
    DL-->>O: Original message + metadata
    O->>O: Validate policy, idempotency, target
    O->>Q: Send new message
    Q-->>O: Send acknowledged
    O->>DL: Complete original DLQ message
    O->>A: Record replay result
~~~

**Không xóa/Complete message gốc trước khi send thành công.** Nếu send lỗi mà message gốc đã bị Complete, bạn mất bản phục hồi.

### 24.1. Nhưng send trước, Complete sau vẫn không exactly-once

Một cửa sổ lỗi quan trọng:

~~~text
Send tới active queue thành công
   -> Process chết trước Complete DLQ
   -> Original vẫn nằm ở DLQ
   -> Replay lại có thể gửi bản thứ hai
~~~

Do đó, phải có idempotency ở tầng consumer hoặc hệ thống audit/coordination bền vững. Không được tuyên bố một script replay đơn giản tự đảm bảo exactly-once end-to-end.

### 24.2. Không copy mọi system properties máy móc

Khi tạo message mới, cần chọn lại các thuộc tính hợp lệ: MessageId, CorrelationId, Subject, application properties và TTL/session theo contract. Những metadata như DeliveryCount, LockToken, EnqueuedTime hay DeadLetterReason thuộc bản nhận hiện tại, không phải tất cả đều có thể gán trực tiếp lên message gửi mới.

### 24.3. Duplicate detection ảnh hưởng replay

Nếu entity đích bật duplicate detection, gửi lại cùng MessageId trong deduplication window có thể không tạo bản mới theo ý định. Nhưng đổi MessageId tùy tiện lại làm consumer không còn nhận ra nghiệp vụ đã xử lý.

Cần quyết định rõ:

- **business idempotency key** ổn định qua các lần replay;
- **transport message ID** theo chính sách broker/deduplication;
- **replay attempt ID** để audit.

## 25. Replay tool nên có dry-run và giới hạn tốc độ

Một công cụ replay production nên có:

| Chức năng | Mục đích |
|---|---|
| **List/Peek** | Chỉ xem message và metadata |
| **Filter** | Chọn theo reason, event type, thời gian, tenant |
| **Dry-run** | In kế hoạch, không send/complete |
| **Approve** | Ghi người chấp thuận và ticket |
| **Batch size** | Giới hạn số message mỗi đợt |
| **Rate limit** | Không làm quá tải consumer/downstream |
| **Idempotency** | Không nhân bản giao dịch |
| **Audit** | Lưu source/target IDs và kết quả |
| **Pause/Stop** | Dừng nếu error/latency tăng |
| **Resume checkpoint** | Tiếp tục xử lý khi replay tool dừng |
| **Verification** | Đối chiếu business outcome |

Ví dụ pseudocode **không phải lệnh chạy trực tiếp**:

~~~text
for each selected DLQ message:
    if !policyAllows(message):
        quarantine(message)
        continue

    if businessAlreadyCompleted(message.businessKey):
        closeAccordingToPolicy(message)
        continue

    newMessage = reconstructSafely(message)
    newMessage.replayAttempt = message.replayAttempt + 1
    newMessage.correlationId = message.correlationId

    sendAndAwaitAcknowledgement(targetEntity, newMessage)
    completeOriginalDlqMessage(message)
    writeAuditRecord(message, newMessage)
~~~

Mẫu trên chưa giải quyết trọn vẹn atomicity giữa broker và audit database. Trong hệ thống nghiêm ngặt, cần thiết kế thêm transactional outbox/inbox, trạng thái idempotent hoặc cơ chế transaction của broker trong phạm vi các hạn chế được hỗ trợ.

**Dry-run không được gửi message hoặc Complete nguồn.** Một nút “Preview” mà vẫn ack message là lỗi thiết kế nghiêm trọng.

## 26. Idempotency: điều kiện quan trọng hơn số lần retry

Trong hệ thống message-driven, có thể xảy ra:

1. Worker ghi đơn hàng vào database thành công.
2. Worker chết trước khi Complete message.
3. Broker giao lại message.
4. Worker xử lý lần nữa, nếu không kiểm tra có thể tạo đơn hàng hoặc trừ tiền lần hai.

**Idempotency** là khả năng xử lý cùng một sự kiện nhiều lần mà không làm kết quả nghiệp vụ sai.

### 26.1. Dùng business key

Ví dụ với nghiệp vụ đơn hàng:

~~~text
BusinessOperationId = "CreateInvoice:ORD-1001"
~~~

Trong database, có unique constraint hoặc bảng inbox theo BusinessOperationId. Khi nhận message trùng:

- Nếu operation đã hoàn tất, consumer xác nhận message mà không tạo hóa đơn lần nữa.
- Nếu operation đang chạy, dùng locking/transaction thích hợp để ngăn race.
- Nếu operation chưa xử lý, thực hiện trong transaction phù hợp rồi ghi trạng thái hoàn thành.

### 26.2. Không chỉ dựa vào Service Bus duplicate detection

Broker duplicate detection liên quan đến việc **nhận message gửi vào entity** trong một khoảng thời gian được cấu hình; nó không thay thế khả năng consumer xử lý message được delivery lại hoặc replay qua nhiều ngày.

### 26.3. Side effects cần đặc biệt chú ý

Payment charge, gửi email và cập nhật inventory là các side effects có thể không hoàn nguyên đơn giản. Cần idempotency token ở API ngoài hoặc cơ chế đối soát trước replay. Đôi khi quyết định đúng là **đóng message lỗi sau khi xác minh nghiệp vụ đã hoàn tất**, không gửi lại.

## 27. Thứ tự message, sessions và replay

Service Bus hỗ trợ **sessions** cho các kịch bản cần nhóm và thứ tự xử lý theo session. Nhưng khi một message lỗi được đưa vào DLQ, các message khác có thể tiếp tục được xử lý tùy cách consumer và session logic được xây dựng.

### 27.1. Rủi ro replay sai thứ tự

Giả sử các events:

~~~text
OrderCreated -> OrderPaid -> OrderCancelled
~~~

Nếu OrderPaid bị DLQ nhưng OrderCancelled đã được xử lý, replay OrderPaid sau đó có thể đưa state về trạng thái sai nếu handler không kiểm tra business version/state transitions.

### 27.2. Quy trình cho session/ordering

1. Phân nhóm DLQ theo SessionId hoặc business aggregate key.
2. Xác định các events đã hoàn thành và state hiện tại.
3. Quyết định có cần replay theo một thứ tự cụ thể hay cần một compensating action.
4. Khi tạo message mới, bảo toàn SessionId nếu contract yêu cầu và entity đích hỗ trợ.
5. Kiểm tra consumer có chịu được out-of-order events không.

**Replay không tự đặt message về đúng vị trí lịch sử trong hàng đợi.** Đây là hành động gửi mới vào thời điểm hiện tại; cần business state machine để xử lý thứ tự.

## 28. Topic subscriptions: một event, nhiều DLQ

Khi dùng Service Bus topic:

~~~mermaid
flowchart TB
    PUB[OrderSubmitted producer] --> TOPIC[(Topic: order-events)]
    TOPIC --> S1[Subscription: accounting]
    TOPIC --> S2[Subscription: email]
    TOPIC --> S3[Subscription: analytics]
    S1 --> C1[Accounting consumer]
    S2 --> C2[Email consumer]
    S3 --> C3[Analytics consumer]
    C1 --> DLQ1[(Accounting DLQ)]
    C3 --> DLQ3[(Analytics DLQ)]
~~~

Một event có thể thành công ở subscription email nhưng lỗi ở accounting. DLQ phải được giám sát **theo subscription**, không chỉ theo namespace tổng.

### 28.1. Replay đúng đích

Khi phát lại một message từ **accounting DLQ**, gửi lại nguyên event vào topic có thể khiến **email và analytics nhận event lần thứ hai**, dù họ đã xử lý thành công.

Các lựa chọn cần đánh giá:

- Replay vào đường nhận chỉ dành cho consumer bị lỗi, nếu kiến trúc hỗ trợ.
- Dùng một topic/replay route với filtering rõ ràng.
- Consumer idempotency ở tất cả subscriptions.
- Thực hiện compensating action có kiểm soát thay vì broadcast lại.

**Không mặc định có thể “send trở lại subscription” trực tiếp**, vì subscription trong Service Bus là nơi nhận từ topic, không phải endpoint gửi message kiểu queue. Cần thiết kế luồng replay hợp lệ theo broker.

## 29. Message TTL, retention và pháp lý dữ liệu

Một điểm dễ nhầm: **message nằm trong Service Bus DLQ thường không chịu cơ chế tự hết hạn TTL giống active queue**; thông điệp dead-letter thường tồn tại cho tới khi được đọc và Complete hoặc xóa theo thao tác phù hợp. Vì thế DLQ cần được quản lý dung lượng và retention ở tầng vận hành.

### 29.1. DLQ không phải kho lưu trữ lâu dài

- Message có thể chứa thông tin khách hàng nhạy cảm.
- DLQ tăng có thể góp phần làm entity đạt giới hạn lưu trữ.
- Mất kiểm soát DLQ gây tăng chi phí và rủi ro lưu trữ quá hạn.
- DLQ không thay thế Azure Backup, cơ sở dữ liệu hoặc archival store.

### 29.2. Khi nào archive trước khi xóa?

Nếu tổ chức cần lưu bằng chứng điều tra nhưng không muốn giữ mãi trong broker, có thể xuất metadata và payload phù hợp sang Storage/database có chính sách access, encryption, retention và audit riêng. Xác minh dữ liệu đã lưu thành công trước khi Complete/delete nguồn.

### 29.3. Không tự xóa theo tuổi nếu nghiệp vụ chưa xử lý

Một message 30 ngày chưa được giải quyết có thể đại diện hóa đơn quan trọng. Chính sách retention phải tính đến SLA, pháp lý, bảo mật và business owner, không chỉ mức dung lượng.

## 30. Giám sát DLQ và poison queue bằng Azure Monitor

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa | Hành động |
|---|---|---|
| **DLQ message count** | Số message đang chờ giải quyết | Cảnh báo theo mức tăng/tồn đọng |
| **DLQ arrival rate** | Số message mới vào DLQ theo thời gian | Phát hiện sự cố mới |
| **Oldest DLQ message age** | Message chưa giải quyết lâu nhất | Theo dõi SLA xử lý |
| **Active backlog** | Message còn ở hàng đợi chính | Phát hiện consumer không theo kịp |
| **Delivery count distribution** | Số lần xử lý/retry trước DLQ | Đánh giá cấu hình MaxDeliveryCount |
| **Reason distribution** | Tỷ lệ lỗi schema, timeout, quyền... | Ưu tiên root cause |
| **Replay success rate** | Messages replay và hoàn tất nghiệp vụ | Đánh giá chất lượng xử lý |
| **Repeated DLQ / replay loops** | Một business event quay lại DLQ nhiều lần | Dừng replay và điều tra |
| **Dependency error rate** | Lỗi DB/API/Storage ngoài broker | Tránh dead-letter hàng loạt |
| **Queue/consumer throughput** | Số message hoàn tất theo thời gian | Đánh giá chất lượng phục hồi |

Azure Monitor hỗ trợ metrics và diagnostic logs cho Service Bus/Storage theo tài nguyên và cấu hình. Không phải mọi giá trị như **reason distribution** hoặc **oldest DLQ message age** đều có sẵn trực tiếp thành metric nền tảng; có thể cần một **DLQ inspector** hoặc pipeline telemetry bổ sung để thu thập.

### 30.1. Đếm tổng không đủ

Ví dụ DLQ luôn có 100 messages, nhưng mỗi ngày 100 messages mới được thêm và 100 messages cũ bị xóa. Tổng không đổi không có nghĩa hệ thống ổn định. Cần arrival rate, age, resolution rate và business impact.

### 30.2. Dùng Azure Monitor alerts

Thiết lập cảnh báo dựa trên metric thực có sẵn, hoặc custom metrics từ DLQ processor:

- DLQ count tăng liên tục.
- Message mới vào DLQ từ một producer version.
- Oldest age vượt SLA.
- Replay thất bại vượt ngưỡng.
- Queue active backlog tăng cùng DLQ.
- Entity gần giới hạn capacity.
- Consumer exceptions/lock-lost spikes.

Cần có **owner** và action khi alert, không chỉ gửi email rồi để đó.

## 31. Log và correlation phục vụ điều tra

Một structured log tối thiểu:

~~~json
{
  "level": "ERROR",
  "event": "MessageProcessingFailed",
  "entity": "orders",
  "messageId": "evt-demo-001",
  "correlationId": "corr-demo-001",
  "schemaVersion": 2,
  "errorCategory": "InvalidSchema",
  "retryable": false,
  "consumerVersion": "orders-worker-1.4.2",
  "attempt": 3
}
~~~

Không ghi toàn bộ payload hoặc raw exception nếu chứa secrets/PII. Khi cần forensic, sử dụng một kho riêng có quyền chặt, retention và masking.

### 31.1. Tracing qua nhiều dịch vụ

Liên kết:

~~~text
HTTP request
  -> Producer send
  -> Service Bus message
  -> Consumer invocation
  -> Database operation
  -> Dead-letter event hoặc Complete
  -> Replay operation
  -> Final business state
~~~

Application Insights/OpenTelemetry có thể hỗ trợ trace correlation nếu được instrument. Phải bảo toàn correlation ID khi replay, đồng thời gắn **replayAttemptId** riêng để biết sự kiện xử lý nào thuộc lần phát lại.

### 31.2. Lỗi cần dữ liệu để tái hiện

Khi không thể lưu payload vì privacy, vẫn nên giữ schemaVersion, event type, safe validation error codes và một reference ID tới dữ liệu nguồn đã được kiểm soát. Việc này giúp debug mà không phát tán bản sao dữ liệu nhạy cảm.

## 32. Bảo mật và phân quyền xử lý DLQ

DLQ thường chứa dữ liệu không hợp lệ, nhưng vẫn có thể chứa dữ liệu sản xuất nhạy cảm. Cần áp dụng:

- **Microsoft Entra ID/managed identity** cho công cụ đọc và xử lý khi SDK/broker hỗ trợ.
- Azure RBAC data-plane với quyền tối thiểu: người xem message khác người có quyền Complete/replay.
- Quy trình phê duyệt riêng cho replay/xóa hàng loạt.
- Kiểm soát truy cập Azure Portal, Service Bus Explorer, Storage Explorer và CI runners.
- TLS, private endpoints/VNet/firewall theo thiết kế hệ thống.
- Masking/redaction payload và error descriptions.
- Lưu audit của thao tác peek, nhận, xóa, replay nếu công cụ/tổ chức hỗ trợ.
- Tránh đưa SAS connection strings vào source hoặc ticket.
- Xác minh tenant boundary và target environment trước khi phát lại.

### 32.1. Quyền đọc metadata không đồng nghĩa quyền đọc body

Một user có Azure Resource Manager Reader có thể xem cấu hình resource nhưng không mặc nhiên được đọc nội dung message. Cần cấp đúng data-plane role như Service Bus Data Receiver hoặc vai trò tương ứng theo mô hình quyền của hệ thống.

### 32.2. Quyền gửi lại message

Một replay service có thể cần quyền **receive/settle** ở DLQ nguồn và **send** tới queue/topic đích. Đây là quyền nhạy cảm, nên giới hạn scope và chỉ vận hành trong môi trường được phê duyệt.

### 32.3. Không phát lại dữ liệu không tin cậy một cách mù quáng

Nếu message có nội dung độc hại, replay có thể gây lỗi lặp lại hoặc kích hoạt logic không an toàn. Kiểm tra schema, size, loại event và nguồn trước khi xử lý.

## 33. Chi phí, hiệu năng và dung lượng DLQ

DLQ giúp giữ message lỗi nhưng vẫn tạo chi phí gián tiếp:

| Nguồn chi phí | Giải thích |
|---|---|
| Broker resources | Lưu message, kích thước entity, operations và tier |
| Consumer invocations | Retry nhiều lần tốn compute |
| Queue polling | Kiểm tra liên tục có thể tăng requests |
| Replay process | Compute, send/receive operations và downstream calls |
| Logging/monitoring | Log ingestion, metrics, alerting, retention |
| Archive storage | Lưu bản sao lỗi đã kiểm soát |
| Operational labor | Điều tra và phê duyệt thủ công |

Một DLQ tăng vô hạn có thể ảnh hưởng sức chứa hoặc quota của Service Bus entity. Ngay cả khi số messages ít, một payload lớn hoặc nhiều copies do retry/replay cũng có thể tạo vấn đề.

### 33.1. Không tối ưu bằng cách xóa mọi DLQ ngay lập tức

Xóa DLQ có thể giảm số message và storage usage nhưng làm mất cơ hội phục hồi giao dịch. Quyết định cleanup phải xuất phát từ business owner, trạng thái xử lý và policy.

### 33.2. Đặt ngưỡng theo tác động

Với giao dịch thanh toán, 1 message dead-letter cũng có thể cần cảnh báo ưu tiên cao. Với batch không quan trọng, ngưỡng theo tỷ lệ lỗi hoặc thời gian xử lý có thể phù hợp hơn.

## 34. Kịch bản 1: JSON sai schema

**Bối cảnh:** producer version 2 gửi:

~~~json
{
  "eventType": "OrderSubmitted",
  "schemaVersion": 9,
  "data": {
    "orderId": "ORD-1001"
  }
}
~~~

Consumer chỉ hỗ trợ schemaVersion 1 và 2.

Quy trình:

1. Consumer parse envelope và phát hiện schemaVersion không được hỗ trợ.
2. Phân loại **permanent schema incompatibility**.
3. Explicit dead-letter với reason **InvalidSchema**.
4. Alert phát hiện nhiều messages cùng schemaVersion=9.
5. Đội phát triển quyết định: nâng consumer hỗ trợ schema 9, sửa producer, hoặc dùng converter có kiểm thử.
6. Sau khi có bản fix, thử replay một số message giả trong staging.
7. Đánh giá version compatibility cho production.
8. Replay batch nhỏ, kiểm tra nghiệp vụ đã ghi thành công.
9. Audit và đóng incident.

**Không sửa payload đang nằm trong DLQ bằng một script không có version/approval.** Nếu cần transform, tạo message mới và ghi rõ source, transformation version và kết quả.

## 35. Kịch bản 2: Database tạm thời không phản hồi

**Bối cảnh:** worker xử lý OrderSubmitted nhưng Azure SQL báo timeout trong vài phút.

Cách xử lý:

1. Phân loại lỗi **transient infrastructure/dependency**.
2. Retry với backoff và giới hạn để tránh retry storm.
3. Kiểm tra CPU/DTU/vCore, connection pool, locks và tình trạng database.
4. Nếu lỗi lan rộng, giảm concurrency hoặc tạm ngừng nhận job theo runbook.
5. Nếu messages bị MaxDeliveryCountExceeded và rơi vào DLQ, không mặc định chúng bị sai dữ liệu.
6. Sau khi database phục hồi, chọn nhóm DLQ lỗi timeout để replay dần.
7. Kiểm tra những nghiệp vụ đã commit trước khi lỗi settlement để tránh ghi trùng.

**Bài học:** DLQ vì MaxDeliveryCountExceeded không đủ để kết luận payload sai. Phải kiểm tra logs và downstream state.

## 36. Kịch bản 3: Gửi email trùng khi replay topic event

Một event **OrderSubmitted** được publish vào topic cho ba consumers: accounting, email và analytics.

- Subscription email đã gửi mail thành công.
- Subscription accounting bị DLQ do lỗi cấu hình.
- Nhóm vận hành re-publish nguyên event vào topic.
- Email consumer nhận lại và có nguy cơ gửi mail lần thứ hai.

Thiết kế an toàn:

1. Không tự động broadcast message DLQ trở lại topic.
2. Kiểm tra sự kiện đã được xử lý ở những subscriptions nào.
3. Dùng idempotency key ở email consumer.
4. Chỉ replay theo đường đã được kiến trúc cho phép, có filtering đúng.
5. Ghi audit rằng accounting mới là nhánh cần phục hồi.
6. Sau replay, đối chiếu cả accounting outcome và số email đã gửi.

**DLQ của một subscription không đồng nghĩa mọi subscriber của topic đều thất bại.**

## 37. Kịch bản 4: Poison queue của Azure Functions Queue Storage

Giả sử Function **processInvoices** lấy message từ Azure Queue Storage queue **invoices**. Message sai dữ liệu làm function throw exception đến giới hạn cấu hình.

Kết quả mong đợi của cơ chế Functions Queue trigger:

~~~text
invoices
    |
    | xử lý lỗi nhiều lần
    v
invoices-poison
~~~

Runbook:

1. Kiểm tra App Insights/Functions logs để biết nguyên nhân và số lần xử lý.
2. Mở Storage Explorer/Portal và xác nhận queue **invoices-poison** đã có message.
3. Đọc message có kiểm soát; nhớ rằng body/metadata không tương đương Service Bus DeadLetterReason.
4. Đối chiếu invoice đã được tạo trước đó hay chưa.
5. Sửa handler hoặc dữ liệu cần thiết.
6. Nếu replay, gửi message mới vào **invoices** theo chính sách idempotency.
7. Chỉ xóa message từ **invoices-poison** sau khi gửi/kiểm chứng phù hợp; chấp nhận rủi ro duplicate và bảo vệ bằng idempotency.
8. Theo dõi poison queue tiếp tục tăng hay không.

Không dùng Service Bus Explorer hoặc Service Bus-specific SDK để quản lý invoices-poison, vì nó là Azure Storage Queue.

## 38. Bài thực hành: Service Bus DLQ từ tạo lỗi đến replay

**Mục tiêu:** trong subscription lab, tạo một Service Bus queue, gửi một vài messages giả, cố tình xử lý lỗi để quan sát DLQ, sau đó lập phương án phục hồi có kiểm soát.

### Phần A — Chuẩn bị

1. Xác nhận có quyền tạo Service Bus namespace/queue và ngân sách lab.
2. Tạo resource group riêng, namespace và queue **orders**.
3. Đặt MaxDeliveryCount=5 và xem cấu hình dead-letter on expiration.
4. Chọn identity phù hợp và chỉ cấp data-plane role cần thiết.
5. Không dùng dữ liệu thật của khách hàng.

### Phần B — Tạo message thử nghiệm

Gửi ba messages bằng một ứng dụng SDK hoặc công cụ được phép:

| Message | Nội dung | Kỳ vọng |
|---|---|---|
| **M1** | OrderSubmitted schema hợp lệ | Được Complete |
| **M2** | JSON/schema không hợp lệ | Explicit dead-letter |
| **M3** | Message hợp lệ nhưng mô phỏng dependency lỗi | Retry rồi dead-letter khi vượt giới hạn |

Gắn MessageId, CorrelationId và schemaVersion rõ ràng.

### Phần C — Xử lý

1. Chạy consumer lab ở Peek-Lock.
2. Với M1, ghi kết quả giả rồi Complete.
3. Với M2, đặt DeadLetterReason=InvalidSchema và DeadLetter.
4. Với M3, mô phỏng lỗi có giới hạn để quan sát redelivery và MaxDeliveryCount.
5. Không giữ script trong vòng lặp vô hạn.
6. Kiểm tra Active/DLQ counts trong Portal.

### Phần D — Điều tra

1. Dùng **Peek** vào DLQ.
2. Ghi message IDs, reasons, delivery counts, enqueue time, producer version.
3. Phân biệt lý do explicit với broker-generated MaxDeliveryCount.
4. Tạo một incident record và ghi root cause.
5. Không in message body chứa dữ liệu nhạy cảm vào terminal ghi log công khai.

### Phần E — Thử replay

1. Sửa mô phỏng dependency lỗi.
2. Chọn chỉ M3 để replay; không replay M2 khi schema vẫn sai.
3. Chạy dry-run hiển thị source/target IDs và policy.
4. Được người phụ trách chấp thuận.
5. Gửi message mới tới active queue.
6. Chỉ Complete bản DLQ sau khi send đã được broker xác nhận.
7. Kiểm tra outcome ở consumer và audit.
8. Thử tình huống process ngắt giữa send và Complete để hiểu rủi ro duplicate.

### Phần F — Dọn dẹp

1. Kiểm tra không còn nghiệp vụ lab cần phục hồi.
2. Xem queue/DLQ, log và script chạy nền đã dừng.
3. Xóa các messages/tài nguyên lab theo phê duyệt.
4. Không xóa namespace hoặc resource group có tài nguyên dùng chung.
5. Kiểm tra chi phí phát sinh trong Azure Cost Management.

**Tiêu chí hoàn thành:** có thể giải thích vì sao M2/M3 đi vào DLQ theo hai cơ chế khác nhau, phân biệt xem và nhận message, đồng thời chứng minh quy trình replay không Complete nguồn trước khi send.

## 39. Bài thực hành bổ sung: poison queue với Azure Functions

Nếu môi trường có Azure Function App và Azure Storage account thử nghiệm:

1. Tạo queue **demo-jobs**.
2. Cấu hình Queue trigger với maxDequeueCount có giới hạn nhỏ theo môi trường học.
3. Gửi message hợp lệ và message sai schema.
4. Quan sát invocation retries và Functions logs.
5. Kiểm tra queue **demo-jobs-poison** sau khi vượt giới hạn.
6. So sánh metadata poison queue với Service Bus DLQ của bài thực hành trước.
7. Viết một chức năng chỉ **Peek/read** và thống kê nội dung cần thiết mà không tự xóa.
8. Thiết kế cách resend có idempotency.
9. Dọn tài nguyên và secrets lab.

**Không giả lập poison queue bằng cách cố tình làm lỗi trên ứng dụng production.** Trong môi trường dùng chung, cần bảo vệ quota, chi phí và dữ liệu.

## 40. Checklist thiết kế DLQ cho production

- [ ] Đã xác định rõ dịch vụ queue/broker và cơ chế DLQ/poison tương ứng.
- [ ] Service Bus queue/subscription có MaxDeliveryCount phù hợp.
- [ ] TTL và dead-letter on expiration được cấu hình theo yêu cầu nghiệp vụ.
- [ ] Consumer phân biệt transient/permanent/unknown errors.
- [ ] Retry có giới hạn, backoff/jitter và retry budget tổng.
- [ ] Lỗi diện rộng của dependency có cơ chế giảm tải hoặc tạm dừng an toàn.
- [ ] Message có MessageId, CorrelationId, schemaVersion và business key.
- [ ] DeadLetterReason theo chuẩn, description không chứa secrets/PII.
- [ ] Không dùng Receive-and-Delete cho nghiệp vụ cần retry an toàn.
- [ ] Consumer idempotent khi broker giao trùng hoặc replay.
- [ ] Có dashboard DLQ count, arrival rate, age và reason distribution.
- [ ] Có alert owner và SLA xử lý messages lỗi.
- [ ] Runbook gồm peek, phân loại, sửa gốc, approve, replay, verify, audit.
- [ ] Replay tool có dry-run, batch size, rate limit, pause và checkpoint.
- [ ] Không Complete DLQ trước khi send bản mới thành công.
- [ ] Đã xử lý cửa sổ send-success/complete-failure có thể sinh duplicate.
- [ ] Dữ liệu và thứ tự Service Bus sessions được xem xét trước replay.
- [ ] Topic subscription replay không gây broadcast trùng ngoài ý muốn.
- [ ] Có chính sách retention/archival phù hợp dữ liệu và luật áp dụng.
- [ ] RBAC tách quyền quan sát với quyền replay/xóa.
- [ ] Secrets/keys không nằm trong code, log hoặc error description.
- [ ] Đã diễn tập outage của database và replay một batch nhỏ.
- [ ] Có audit trail của incident, operator và business outcomes.
- [ ] Có ngân sách cho broker operations, retries, logs và archive.
- [ ] Đã kiểm tra khả năng phục hồi khi chính replay worker bị crash.

## 41. Câu hỏi tự kiểm tra

1. Dead-letter queue giải quyết vấn đề gì trong một hệ thống event-driven?
2. Service Bus DLQ khác Azure Queue Storage poison queue của Functions ở điểm nào?
3. Nếu dùng Azure Queue Storage SDK trực tiếp, broker có tự tạo queue -poison không?
4. Các hành động Complete, Abandon và DeadLetter khác nhau như thế nào?
5. Vì sao Peek-Lock phù hợp cho giao dịch quan trọng hơn Receive-and-Delete?
6. MaxDeliveryCountExceeded có luôn chứng minh payload sai không?
7. TTL expiration có tự đưa mọi message vào Service Bus DLQ không?
8. DLQ của topic subscription ảnh hưởng đến các subscriptions khác như thế nào?
9. Transfer DLQ có những nguyên nhân khác DLQ nghiệp vụ nào?
10. Tại sao cần phân loại transient và permanent errors trước retry?
11. Vì sao retry không giới hạn có thể làm hệ thống lỗi nghiêm trọng hơn?
12. Tại sao không nên dùng Thread.sleep hàng phút để trì hoãn retries trong Function?
13. Những metadata nào cần giữ để điều tra message bị dead-letter?
14. Reason và ErrorDescription có nên chứa toàn bộ payload/stack trace không?
15. Vì sao replay một message sau khi gửi email hoặc charge tiền có thể nguy hiểm?
16. Idempotency key ở tầng nghiệp vụ khác duplicate detection của Service Bus thế nào?
17. Vì sao send trước rồi Complete sau vẫn chưa bảo đảm exactly-once end-to-end?
18. Nếu business event thuộc một Service Bus session, replay có thể làm mất thứ tự như thế nào?
19. Vì sao gửi lại nguyên event vào topic có thể gây duplicate side effects?
20. Một dashboard chỉ theo dõi DLQ count còn thiếu những chỉ số nào?
21. Người chỉ có ARM Reader có mặc nhiên xem được message body không?
22. Khi nào nên archive DLQ messages trước khi xóa?
23. Nếu một queue có hàng nghìn messages DeadLetterReason=DependencyUnavailable, nên làm gì trước replay?
24. Khi dùng Azure Functions Queue trigger, host.json maxDequeueCount liên quan poison queue thế nào?
25. Một bài thực hành thành công cần chứng minh điều gì ngoài việc DLQ count giảm?

## 42. Tổng kết

**Dead-letter queue** là thành phần quan trọng để giữ lại và điều tra những thông điệp không thể xử lý bình thường. Với **Azure Service Bus**, queue và topic subscription có dead-letter subqueue tích hợp, chịu tác động từ **MaxDeliveryCount**, TTL policy và explicit dead-letter. Với **Azure Queue Storage**, không có broker-native DLQ tương đương; **Azure Functions Queue trigger** có thể sử dụng **<queue-name>-poison** theo cơ chế retry của runtime.

Một thiết kế đúng không kết thúc ở việc tạo DLQ. Bạn cần **phân loại lỗi, retry có giới hạn, idempotency, metadata an toàn, giám sát và quy trình replay có phê duyệt**. Replay phải tránh mất dữ liệu, sinh giao dịch trùng, sai thứ tự và lặp lại lỗi cũ. Hãy kiểm tra nguyên nhân gốc trước, gửi message mới thành công rồi mới Complete nguồn, và xác minh kết quả nghiệp vụ sau cùng.

Kết hợp **Service Bus/Queue Storage**, **Azure Functions hoặc AKS workers**, **Microsoft Entra ID/managed identity**, **Azure Monitor/Application Insights**, **database** và **Cost Management** để xây dựng luồng xử lý thông điệp an toàn, có thể phục hồi và kiểm soát chi phí. **Một message ra khỏi DLQ chưa chắc đã được giải quyết**; mục tiêu cuối cùng là nghiệp vụ thành công hoặc được kết thúc minh bạch, có dấu vết và được chấp thuận.
