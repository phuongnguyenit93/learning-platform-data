# Lựa chọn Azure Queue Storage và Azure Service Bus

Khi một API phải xử lý đồng thời nhiều yêu cầu đặt hàng, gửi email, tạo thumbnail hoặc tính toán báo cáo, việc thực hiện mọi tác vụ trong chính HTTP request dễ gây timeout và làm hệ thống khó mở rộng. **Hàng đợi thông điệp (message queue)** giúp tách bên gửi khỏi bên xử lý: API gửi một thông điệp ngắn, worker lấy thông điệp và xử lý bất đồng bộ. Khi worker chậm hoặc tạm thời không hoạt động, thông điệp có thể tiếp tục nằm trong hàng đợi theo các giới hạn và chính sách lưu giữ được cấu hình.

Microsoft Azure có hai lựa chọn phổ biến là **Azure Queue Storage** và **Azure Service Bus**. Cả hai đều giúp kết nối các thành phần không đồng bộ, nhưng khác nhau về tính năng nghiệp vụ, cơ chế giao nhận, định tuyến, độ phức tạp vận hành và cách tính chi phí. Chọn dịch vụ đúng không chỉ dựa trên số thông điệp mỗi giây, mà còn dựa trên câu hỏi: **Có cần thứ tự trong một nhóm nghiệp vụ, publish/subscribe, dead-letter queue tích hợp, transaction, duplicate detection hoặc workflow tin cậy không?**

Bài học thuộc chương **Hàng đợi và thông điệp** trong module **CLOUD_PROVIDERS_AZURE**. Nội dung kết nối Azure Storage, Microsoft Entra ID, Azure Functions, ứng dụng Java, mạng ảo, giám sát, bảo mật và tối ưu chi phí một kiến trúc ứng dụng Azure.

> **Phạm vi:** các giới hạn kích thước thông điệp, quota, tính năng theo tier và đơn giá có thể thay đổi theo region, phiên bản dịch vụ và thời điểm triển khai. Các ví dụ cung cấp mô hình quyết định và cách tích hợp; khi vận hành thật, cần đối chiếu giới hạn hiện hành của **đúng SKU, namespace/storage account và SDK version**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích mô hình **producer → queue → consumer**, sự khác biệt giữa lưu dữ liệu và gửi thông điệp.
2. So sánh Azure Queue Storage với Azure Service Bus về chức năng, scale, thứ tự, retry, dead-letter và bảo mật.
3. Chọn **Service Bus Queue**, **Service Bus Topic/Subscription** hoặc **Queue Storage** cho các tình huống thực tế.
4. Phân biệt **visibility timeout + pop receipt** của Queue Storage với **Peek-Lock + settlement** của Service Bus.
5. Thiết kế message payload, idempotency key, retry, backoff, poison-message handling và trạng thái xử lý.
6. Gửi/nhận/xác nhận thông điệp bằng Azure SDK for Java theo identity-based authentication.
7. Nhận biết khi nào cần **sessions, duplicate detection, dead-lettering, scheduling và transactions**.
8. Thiết kế quyền truy cập, private networking, monitoring, alert, chi phí và khả năng phục hồi.
9. Lập checklist để đánh giá, kiểm thử và chuyển đổi messaging backend khi yêu cầu thay đổi.

## 2. Bản chất của một hàng đợi

Một hàng đợi đơn giản có ba vai trò:

- **Producer:** ứng dụng, API hoặc sự kiện gửi thông điệp.
- **Queue/Broker:** tiếp nhận và giữ thông điệp trong giới hạn retention, điều phối cho consumer.
- **Consumer:** worker lấy thông điệp, xử lý và xác nhận kết quả.

~~~mermaid
flowchart LR
  U["HTTP client"] --> A["Order API (producer)"]
  A --> Q["Message queue"]
  Q --> W1["Worker 1"]
  Q --> W2["Worker 2"]
  W1 --> DB["Database / Blob Storage"]
  W2 --> DB
  A --> RESP["202 Accepted + jobId"]
~~~

Trong kiến trúc này, API có thể phản hồi nhanh sau khi **đã gửi message thành công**; công việc thực tế diễn ra sau đó. Nếu worker cần bảo trì, queue giúp giảm phụ thuộc thời gian giữa producer và consumer. Tuy nhiên, queue không thay thế việc đảm bảo API đã kiểm tra dữ liệu, backend có đủ công suất, trạng thái công việc được cập nhật và người dùng có thể tra cứu kết quả.

### Message không phải toàn bộ dữ liệu nghiệp vụ

Thông điệp nên chứa thông tin cần thiết để tìm hoặc xử lý một tác vụ, ví dụ:

~~~json
{
  "schemaVersion": 1,
  "messageId": "order-1024-created",
  "jobId": "job-7f23",
  "orderId": "order-1024",
  "occurredAt": "2026-11-20T08:15:00Z",
  "blobRef": "orders/input/order-1024.json"
}
~~~

Nếu payload là tệp video 500 MiB, không nên nhét trực tiếp toàn bộ tệp vào message. Hãy lưu vào **Blob Storage**, gửi **tham chiếu, ID, checksum hoặc URI không chứa credential**, và để worker tải dữ liệu qua quyền được cấp.

Lưu ý **message body** không tự được mã hóa ở cấp nghiệp vụ ngoài các biện pháp của nền tảng; không đưa mật khẩu, token, dữ liệu thẻ hoặc thông tin nhạy cảm vượt chính sách vào nội dung message/log.

## 3. Azure Queue Storage là gì?

**Azure Queue Storage** là dịch vụ queue trong Azure Storage account. Nó cung cấp cơ chế bền vững, tương đối đơn giản cho một hoặc nhiều consumer xử lý thông điệp bất đồng bộ.

Các khái niệm chính:

- **Storage account:** tài nguyên cha chứa queue, cùng hệ sinh thái giám sát/bảo mật Azure Storage.
- **Queue:** vùng lưu thông điệp theo tên, ví dụ `image-jobs`.
- **Message:** payload được gửi vào hàng đợi, có metadata do dịch vụ quản lý.
- **Visibility timeout:** khoảng thời gian message đã được consumer lấy về tạm thời không hiển thị với consumer khác.
- **Pop receipt:** giá trị do dịch vụ cung cấp để xác nhận quyền thao tác trên một lần nhận message; cần khi xóa hoặc cập nhật message theo API tương ứng.
- **Time-to-live (TTL):** thời gian message được lưu trước khi hết hạn theo cấu hình và giới hạn dịch vụ.
- **Dequeue count:** số lần message được đưa ra xử lý theo cơ chế nhận; hữu ích để phát hiện message lỗi liên tục.

### Luồng xử lý điển hình

1. Producer gửi message vào queue.
2. Consumer nhận message và một **pop receipt**.
3. Message trở nên ẩn trong visibility timeout.
4. Worker xử lý và ghi kết quả vào nơi bền vững.
5. Nếu thành công, worker gọi **delete message** bằng message ID và pop receipt hiện hành.
6. Nếu worker chết hoặc không xóa message, sau khi hết visibility timeout, message có thể xuất hiện trở lại để xử lý tiếp.

~~~mermaid
flowchart TD
  P["Producer gửi message"] --> Q["Azure Queue Storage"]
  Q --> R["Receive + pop receipt"]
  R --> V["Message tạm ẩn trong visibility timeout"]
  V --> O{"Worker thành công?"}
  O -->|Có| D["Delete bằng messageId + popReceipt"]
  O -->|Không / worker mất| X["Hết timeout, message có thể được nhận lại"]
  X --> R
~~~

**Đây là at-least-once processing ở góc độ thiết kế ứng dụng:** cùng một message có thể được nhận lại. Không được giả định đúng một lần xử lý chỉ vì client đã nhận nó thành công.

### Đặc trưng phù hợp

Queue Storage hấp dẫn khi cần **queue đơn giản, dễ tích hợp với Azure Storage, không cần broker features phức tạp**, hoặc khi pipeline chỉ có một luồng tác vụ để nhóm consumer cạnh tranh xử lý.

Một số tính năng thường cần ở hệ thống nghiệp vụ như broker-level topics/subscriptions, message sessions hoặc dead-letter subqueue **không phải tính năng tích hợp tương đương trong Queue Storage**; muốn có chúng phải tự xây logic hoặc chọn Service Bus.

## 4. Azure Service Bus là gì?

**Azure Service Bus** là dịch vụ **enterprise message broker** được quản lý. Ngoài queue điểm-điểm, nó cung cấp mô hình **Topic/Subscription** để phân phối một sự kiện tới nhiều nhóm consumer, cùng các cơ chế xử lý message chuyên sâu tùy tier.

Các khái niệm:

- **Namespace:** phạm vi quản lý queues, topics, subscriptions, policy, network và quyền.
- **Queue:** một message được đưa vào một hàng đợi để một consumer trong nhóm cạnh tranh xử lý.
- **Topic:** điểm publish message cho nhiều nhóm nhận.
- **Subscription:** hàng đợi logic của một topic; mỗi subscription nhận các thông điệp theo rules/filters được hỗ trợ.
- **Peek-Lock:** consumer nhận message dưới trạng thái locked mà broker chưa xóa; sau đó **complete/abandon/dead-letter/defer** theo API phù hợp.
- **Dead-letter queue (DLQ):** vùng phụ được dịch vụ quản lý để lưu message không thể xử lý theo quy tắc nhất định.
- **Session:** gom các message có cùng session ID để hỗ trợ xử lý có thứ tự và độc quyền ở phạm vi session theo cơ chế hỗ trợ.
- **Duplicate detection:** tính năng tùy chọn giúp broker phát hiện message trùng theo MessageId trong cửa sổ được cấu hình khi tier/entity hỗ trợ.

~~~mermaid
flowchart LR
  API["Order API"] --> TOP["Topic: order-events"]
  TOP --> SUB1["Subscription: billing"]
  TOP --> SUB2["Subscription: notifications"]
  TOP --> SUB3["Subscription: analytics"]
  SUB1 --> B["Billing worker"]
  SUB2 --> N["Notification worker"]
  SUB3 --> A["Analytics worker"]
~~~

**Topic không giống Queue:** với queue, những consumer cạnh tranh lấy công việc từ cùng hàng đợi; với topic, mỗi subscription phù hợp có một bản giao nhận logic riêng để nhóm consumer đó xử lý. Một consumer của subscription `billing` không khiến message biến mất khỏi `notifications`.

## 5. Bảng so sánh nhanh

| Tiêu chí | Azure Queue Storage | Azure Service Bus |
|---|---|---|
| Mục tiêu chính | Task queue đơn giản | Enterprise messaging, workflow và event fan-out |
| Tài nguyên cha | Storage account | Service Bus namespace |
| Điểm-điểm, competing consumers | Có | Có, qua queue hoặc trong cùng subscription |
| Topic/Subscription pub-sub | Không có broker topics tích hợp | Có trên tier được hỗ trợ |
| Nhận và giữ message | Visibility timeout + pop receipt | Peek-Lock + lock token/settlement |
| Xác nhận thành công | Xóa message | Complete message trong Peek-Lock |
| Xử lý lại | Message hiện lại sau visibility timeout | Abandon, lock expiry, retry/settlement |
| DLQ tích hợp | Không có DLQ riêng của Queue Storage | Có dead-letter subqueue |
| FIFO theo nhóm nghiệp vụ | Không bảo đảm strict FIFO khi có parallelism/retry | Sessions có thể hỗ trợ thứ tự trong session |
| Duplicate detection broker | Không phải tính năng tương đương tích hợp | Có khi bật và tier hỗ trợ |
| Schedule message | Cần ứng dụng tự tổ chức lịch | Hỗ trợ scheduled messages |
| Transactions broker | Không có cơ chế Service Bus tương đương | Hỗ trợ một số transaction operations trong phạm vi quy định |
| Filtering/rules | Do ứng dụng tự triển khai | Subscription filters/rules |
| Authorization | Entra ID/RBAC hoặc Storage authorization | Entra ID/RBAC hoặc SAS theo cấu hình |
| Network | Firewall/private endpoints của Storage | Network controls/private access theo tier/features |
| Mô hình chi phí | Storage + operations/transactions + traffic | Messaging tier/operations/capacity + traffic |
| Độ phức tạp | Thấp hơn cho bài toán đơn giản | Cao hơn nhưng thêm nhiều tính năng |

**Không có dịch vụ nào luôn tốt hơn.** Queue Storage có thể là giải pháp đúng cho hàng triệu job đơn giản; Service Bus có thể cần thiết ngay cả khi traffic thấp nếu nghiệp vụ đòi hỏi sessions, dead-letter, pub-sub hoặc các quy trình xử lý tin cậy.

## 6. Chọn Queue Storage hay Service Bus theo yêu cầu

### Nên bắt đầu bằng Azure Queue Storage khi

1. Có một kiểu job tương đối độc lập, mỗi message cần một worker xử lý.
2. Không cần topic/subscription hay message filters ở broker.
3. Không bắt buộc duy trì thứ tự nghiêm ngặt khi retry và xử lý song song.
4. Có thể tự xử lý poison messages, idempotency và tracking job.
5. Hạ tầng ứng dụng đã dùng Azure Storage và muốn giảm độ phức tạp.
6. Đã đánh giá đúng message size, queue size, request rate, SLA và chi phí.

**Ví dụ:** dịch vụ nhận ảnh, gửi message `resize-image`, nhiều worker lấy ảnh từ Blob Storage, tạo thumbnail rồi xóa message khi thành công. Nếu một ảnh lỗi, app có thể đưa vào queue lỗi riêng hoặc chuyển trạng thái ở database.

### Nên đánh giá Azure Service Bus khi

1. Một sự kiện cần **nhiều hệ thống** nhận độc lập qua topic/subscription.
2. Cần **DLQ tích hợp** để phân tích thông điệp không xử lý được.
3. Cần **sessions** để xử lý tuần tự theo `orderId` hoặc `accountId`.
4. Cần duplicate detection, scheduled messages hoặc các khả năng transaction của broker.
5. Muốn điều khiển hoàn tất/thử lại/defer/dead-letter rõ ràng qua settlement.
6. Hệ thống cần mô hình messaging enterprise với subscription filters và chính sách retention/retry.

**Ví dụ:** khi đơn hàng được tạo, hệ thống billing, kho và email phải nhận sự kiện riêng. Service Bus Topic cho phép tách ba subscription, mỗi đội triển khai và scale consumer độc lập, đồng thời có thể theo dõi DLQ từng subscription.

### Decision tree

~~~mermaid
flowchart TD
  A["Cần gửi công việc/sự kiện bất đồng bộ"] --> B{"Một sự kiện cần nhiều nhóm nhận độc lập?"}
  B -->|Có| T["Service Bus Topic + Subscriptions"]
  B -->|Không| C{"Cần sessions, broker DLQ, duplicate detection, scheduling hoặc transactions?"}
  C -->|Có| S["Service Bus Queue"]
  C -->|Không| D{"Task đơn giản, retry/idempotency do app quản lý?"}
  D -->|Có| Q["Azure Queue Storage"]
  D -->|Không rõ| E["Làm PoC: kiểm tra tính năng, quota, chi phí, latency, bảo mật"]
~~~

Sơ đồ là hướng dẫn lựa chọn ban đầu. Với yêu cầu đặc thù về event routing, streaming, telemetry hoặc hàng triệu subscriber, cũng nên so sánh các dịch vụ khác như **Event Grid** hoặc **Event Hubs**; chúng không mặc nhiên thay thế một task queue.

## 7. Queue, Topic và Subscription: đừng nhầm kiểu phân phối

### Queue: một nhóm consumer chia nhau công việc

~~~text
                +--> Worker A
Producer -> Q --+
                +--> Worker B
                +--> Worker C
~~~

Một message thường được một consumer xử lý tại một thời điểm theo cơ chế khóa/ẩn message. Nếu consumer không hoàn thành, message có thể được xử lý lại. **Không phải broadcast** cho cả A, B, C.

### Topic: nhiều nhóm consumer nhận độc lập

~~~text
Producer -> Topic -> Subscription billing -> Billing worker pool
                  -> Subscription email   -> Email worker pool
                  -> Subscription audit   -> Audit worker pool
~~~

Các **rule/filter** tại subscription cho phép nhận những message phù hợp với điều kiện được hỗ trợ. Filter sai có thể làm sự kiện không đến subscription dự kiến; cần kiểm thử với loại sự kiện thực.

### Fan-out thủ công trên Queue Storage

Có thể tự triển khai producer gửi bản sao vào ba queue khác nhau, nhưng producer lúc này phải đảm bảo cả ba lần gửi, retry từng đích và tránh trường hợp chỉ một phần thành công. Khi số consumer tăng hoặc tổ chức cần subscription filters, Service Bus Topic thường dễ quản trị tính nhất quán của hành vi messaging hơn.

## 8. Delivery semantics: không có exactly-once end-to-end miễn phí

Ba khái niệm thường bị hiểu sai:

- **At-most-once:** thông điệp có thể mất nếu xử lý lỗi trong cơ chế nhận/xóa không an toàn.
- **At-least-once:** thông điệp được thử giao lại khi chưa xác nhận; có thể xử lý trùng.
- **Exactly-once business effect:** một đơn hàng/hóa đơn chỉ được tạo một lần dù xử lý lại; cần thiết kế idempotency/transaction ở nghiệp vụ.

Azure Queue Storage với visibility timeout và Service Bus với Peek-Lock đều cần **consumer idempotent**. Ngay cả khi Service Bus bật duplicate detection, broker chỉ giúp loại một số lần gửi trùng theo **MessageId trong cửa sổ phát hiện**; nó không thay thế transaction của database hay chống trùng ở hệ thống bên ngoài.

### Cửa sổ lỗi kinh điển

1. Consumer nhận `order-1024`.
2. Consumer ghi hóa đơn thành công.
3. Process bị kill **trước** khi xóa/complete message.
4. Message được giao lại.
5. Nếu handler cứ tạo hóa đơn mới, sẽ có hóa đơn trùng.

Giải pháp: dùng một khóa nghiệp vụ ổn định và unique constraint/conditional write/transaction khi ghi hóa đơn. Sau đó, message được giao lại chỉ xác nhận rằng công việc đã hoàn tất.

## 9. Queue Storage: visibility timeout và pop receipt

Ví dụ một Queue Storage consumer:

~~~text
10:00:00  Receive message M, popReceipt R1, invisible 60s
10:00:20  Worker xử lý
10:00:45  Ghi kết quả thành công
10:00:46  Delete message M với R1

Nếu worker mất lúc 10:00:30:
10:01:00  Message M có thể hiển thị lại
10:01:01  Worker khác receive -> popReceipt R2
~~~

**Pop receipt** cần gắn với bản nhận/cập nhật hợp lệ hiện tại. Nếu một worker giữ receipt cũ và cố xóa message sau khi message đã được nhận lại hoặc receipt đã thay đổi, thao tác có thể không thành công. Vì thế không viết mã cố xóa với receipt đã hết hiệu lực.

### Visibility timeout cần đủ nhưng không quá dài

- Quá ngắn: job vẫn chạy, message xuất hiện lại và worker khác cùng xử lý.
- Quá dài: worker chết nhưng job phải chờ lâu mới được retry.
- Job dài: cần chia thành bước nhỏ hoặc cập nhật message visibility theo API/SDK phù hợp, lưu lại pop receipt mới nếu có.
- Thao tác update visibility cũng có thể thất bại khi hết thời gian hoặc mất kết nối; ứng dụng cần retry/khôi phục an toàn.

Không dùng visibility timeout như một **distributed lock vĩnh viễn**. Đối với thao tác có side effect, vẫn cần concurrency control ở database hoặc data store.

### Thứ tự thông điệp

Queue Storage có thể cho phép message được xử lý theo thứ tự khác với thứ tự gửi khi có nhiều consumer, retry, timeout hoặc thay đổi trạng thái hiển thị. **Không thiết kế logic nghiệp vụ dựa vào FIFO nghiêm ngặt** từ queue đơn giản.

## 10. Service Bus: Peek-Lock, settlement và lock renewal

Với **Peek-Lock**, Service Bus chuyển message tới receiver nhưng chưa xóa khỏi queue. Receiver quyết định:

| Settlement | Ý nghĩa |
|---|---|
| `complete` | Đánh dấu xử lý thành công, xóa message khỏi luồng giao nhận thông thường |
| `abandon` | Từ bỏ lần xử lý này; message có thể được giao lại |
| `deadLetter` | Đưa message sang DLQ để điều tra/xử lý riêng |
| `defer` | Trì hoãn message theo cơ chế deferred messages; cần cách truy xuất lại thích hợp |

### Lock timeout

Khi message đang locked, receiver phải hoàn thành công việc trước khi lock hết hạn hoặc **renew lock** theo SDK/tính năng hỗ trợ. Nếu lock hết hạn trước khi complete, receiver có thể gặp lỗi settlement và message có thể được giao lại.

Ví dụ:

~~~text
T0      Receive M với lock
T0+10s  Xử lý và ghi output
T0+20s  Complete M thành công

Nếu worker bị dừng hoặc lock hết hạn:
        M có thể được nhận lại sau đó
~~~

**Lock renewal không phải vô hạn.** Đặt deadline và dùng checkpoint nếu xử lý lâu. Khi dùng Service Bus processor SDK, có cơ chế auto lock renewal cấu hình được, nhưng phải hiểu giới hạn và trạng thái lỗi.

### Receive-and-Delete

Service Bus cũng có chế độ **Receive-and-Delete**, trong đó broker coi message đã được nhận/xóa mà không chờ complete. Chế độ này có thể phù hợp với telemetry ít quan trọng chấp nhận mất, nhưng **không nên dùng cho đơn hàng, thanh toán hoặc job cần retry** vì consumer chết sau khi nhận có thể làm mất message.

### Delivery count và max delivery

Service Bus có cơ chế đếm lần giao và **max delivery count** theo entity settings. Khi vượt ngưỡng/điều kiện liên quan, message có thể được dead-letter tự động theo cơ chế hỗ trợ. Đừng coi giá trị mặc định của tier/SDK luôn phù hợp: xác định chính sách retry/dead-letter cho workload và xác minh bằng thử nghiệm.

## 11. Poison message và dead-letter: khác biệt lớn

**Poison message** là message không thể xử lý thành công sau các lần thử hợp lý, ví dụ payload JSON thiếu trường, phiên bản schema không còn hỗ trợ hoặc bản ghi tham chiếu đã bị xóa.

### Trong Queue Storage

Storage Queue **không có dead-letter subqueue tích hợp như Service Bus**. Một worker tự viết có thể:

1. Đọc `dequeueCount`.
2. Nếu quá ngưỡng, ghi bản ghi lỗi hoặc chuyển message sang queue riêng, ví dụ `image-jobs-failed`.
3. Ghi nguyên nhân đã được làm sạch dữ liệu nhạy cảm và correlation ID.
4. Chỉ sau khi xử lý chuyển queue thành công mới xóa message ban đầu.
5. Có quy trình vận hành để sửa và replay các job lỗi.

**Azure Functions Queue trigger** có quy ước poison queue như `<queue-name>-poison` khi vượt `maxDequeueCount` theo extension; đây là hành vi của **Functions trigger extension**, không phải DLQ mặc định của Azure Queue Storage REST API.

### Trong Service Bus

Service Bus có **DLQ tích hợp** cho queue hoặc từng topic subscription. Message có thể vào DLQ do policy hoặc do consumer gọi dead-letter. Operator đọc DLQ qua SDK/công cụ phù hợp, tìm root cause và quyết định replay hoặc hủy theo retention/chính sách.

**DLQ không tự sửa message lỗi.** Nếu lấy một message schema sai từ DLQ và gửi ngay lại queue chính, nó sẽ tiếp tục thất bại. Cần validation, fix code/schema/dependency và giới hạn tốc độ replay.

### Checklist cho hàng đợi lỗi

- Phân biệt lỗi tạm thời (timeout, 503) với lỗi vĩnh viễn (payload không hợp lệ).
- Có **giới hạn số lần thử** và backoff phù hợp.
- Ghi error reason, messageId, operation ID, attempt count và thời gian.
- Không log PII/secret vượt chính sách.
- Có owner và SLA xử lý DLQ/poison queue.
- Có cách retry/replay chọn lọc, idempotent, không phát tán lỗi hàng loạt.
- Có alert khi DLQ depth/oldest age tăng.

## 12. Service Bus Sessions: thứ tự trong một nhóm nghiệp vụ

Một hệ thống ngân hàng có thể muốn các thao tác của **cùng một tài khoản** được xử lý lần lượt, nhưng hai tài khoản khác nhau vẫn xử lý song song. Đây là bài toán phù hợp để **đánh giá Service Bus Sessions**.

Producer gắn cùng `SessionId` cho các message thuộc một nhóm:

~~~text
Account A: A-1 -> A-2 -> A-3   (SessionId="account-A")
Account B: B-1 -> B-2          (SessionId="account-B")
~~~

Service Bus session receiver sử dụng session lock để phối hợp một consumer xử lý các message trong session theo thứ tự khả dụng, trong giới hạn cơ chế và cách consumer xử lý. Các session khác nhau có thể được xử lý song song.

**Không hiểu sessions là sự bảo đảm toàn cục rằng toàn bộ queue là FIFO.** Thứ tự cần được xét **trong từng session**, cùng các điều kiện gửi, retry, settlement, deferred message, transaction và concurrency của ứng dụng.

### Điều kiện áp dụng

- Entity phải bật session support khi được tạo và theo tier/tính năng hỗ trợ.
- Sender đặt `SessionId` thích hợp.
- Receiver dùng **session-enabled receiver/processor**, không nhận như queue thông thường.
- Cần tính partitioning, số sessions và độ lệch workload; một session quá nóng có thể giảm mức song song.
- Không dùng session ID từ dữ liệu người dùng mà chưa xác thực/quy định độ dài và format.

### Khi nào không cần sessions?

Nếu các tác vụ hoàn toàn độc lập và đã idempotent, thêm sessions có thể làm tăng độ phức tạp và giảm throughput không cần thiết. Đừng dùng sessions chỉ vì “muốn queue chuyên nghiệp hơn”.

## 13. Duplicate detection, scheduled delivery và transactions

### Duplicate detection

Khi được bật ở Service Bus entity hỗ trợ, broker lưu dấu **MessageId** trong một khoảng thời gian được cấu hình. Nếu producer gửi lại message với cùng ID trong cửa sổ, broker có thể nhận request gửi nhưng loại bỏ bản trùng theo cơ chế dịch vụ.

Hạn chế quan trọng:

- Cần MessageId ổn định do producer quản lý.
- Chỉ áp dụng trong **cửa sổ duplicate detection**, không phải mãi mãi.
- Không bảo vệ side effect từ các lần consumer xử lý lại nếu quy trình giao nhận cho phép retry.
- Tương tác với partition key/session/transaction cần đúng quy định của tier và entity.

Đối với nghiệp vụ thanh toán hoặc kế toán, vẫn cần **idempotency ở database** với unique key/transaction.

### Scheduled messages

Service Bus có khả năng hẹn thời điểm message trở nên sẵn sàng giao trong tương lai theo API hỗ trợ. Phù hợp cho tác vụ nhắc hẹn, delay retry hoặc workflow đơn giản; không tự thay thế một scheduler tổng quát có logic nhiều bước.

Với Queue Storage, có thể dùng initial visibility delay theo khả năng API hoặc ứng dụng tự quản lý lịch, nhưng không mặc định hai dịch vụ có scheduling semantics tương đương.

### Transactions

Service Bus có khả năng kết hợp một số thao tác messaging trong **transaction phạm vi Service Bus** theo tier/API và điều kiện hỗ trợ. Ví dụ, một receiver có thể cần hoàn thành message đầu vào đồng thời gửi message tiếp theo qua broker trong một đơn vị công việc có atomicity do dịch vụ hỗ trợ.

**Transaction broker không bao gồm tự động giao dịch cơ sở dữ liệu SQL, Blob Storage hoặc API đối tác.** Để phối hợp database và phát event, cân nhắc mô hình **transactional outbox**.

## 14. Transactional outbox: tránh mất sự kiện sau khi ghi database

Một lỗi kiến trúc phổ biến:

1. API cập nhật đơn hàng trong database thành công.
2. API định gửi message `OrderCreated`.
3. Process chết giữa hai bước.
4. Database đã có đơn hàng, nhưng queue/topic chưa nhận event.

Nếu đảo thứ tự (gửi message trước, ghi DB sau), consumer có thể nhận event cho một đơn hàng chưa commit hoặc sẽ bị rollback.

### Giải pháp khái niệm

~~~mermaid
flowchart LR
  API["Order API"] --> TX["Database transaction"]
  TX --> ORDER["Orders table"]
  TX --> OUT["Outbox table"]
  OUT --> P["Outbox publisher"]
  P --> BUS["Queue Storage / Service Bus"]
  BUS --> C["Idempotent consumer"]
~~~

Cùng một database transaction ghi **business state** và **outbox event**. Một publisher định kỳ đọc outbox chưa gửi, gửi message rồi đánh dấu trạng thái. Nếu publisher chết sau khi gửi nhưng trước khi đánh dấu, message có thể được gửi lại; consumer vẫn phải idempotent.

Outbox là **pattern ứng dụng**, không phải tính năng tự có khi bật Queue Storage hoặc Service Bus. Nó đặc biệt cần cân nhắc khi thông điệp đại diện cho sự kiện nghiệp vụ quan trọng.

## 15. Thiết kế payload và versioning

Thông điệp nên nhỏ, có mục đích rõ và an toàn khi xử lý lại.

### Đề xuất envelope

~~~json
{
  "schemaVersion": 2,
  "messageId": "evt-order-1024-created-v2",
  "eventType": "OrderCreated",
  "correlationId": "request-8b91",
  "subjectId": "order-1024",
  "occurredAt": "2026-11-20T08:15:00Z",
  "payloadRef": "orders/events/order-1024.json"
}
~~~

Các trường nên có:

- **messageId:** định danh ổn định của message/event, dùng cho dedup/telemetry.
- **correlationId:** liên hệ các bước qua API, producer và consumer.
- **schemaVersion:** cho phép triển khai producer/consumer lệch phiên bản.
- **eventType/jobType:** cho consumer biết loại tác vụ.
- **subjectId/jobId:** khóa nghiệp vụ cho idempotency.
- **occurredAt:** thời gian sự kiện; không dùng như đồng hồ đồng bộ tuyệt đối.
- **payloadRef:** đường dẫn dữ liệu lớn trong store bền vững, không kèm SAS/secret nếu tránh được.

### Giới hạn message size

Cả hai dịch vụ đều có giới hạn về payload và quota; **con số khác nhau theo REST/API, tier và cấu hình**. Đặc biệt Service Bus Standard và Premium có khả năng/giới hạn khác nhau. Khi payload lớn, ưu tiên **claim-check pattern**: dữ liệu trong Blob Storage, message chỉ chứa pointer và checksum; xác định ai có quyền đọc pointer và thời gian lưu dữ liệu.

### Schema evolution

Producer không nên đột ngột xóa field mà consumer cũ yêu cầu. Có thể thêm field tùy chọn, version schema, hoặc triển khai consumer hỗ trợ cả hai định dạng trong giai đoạn chuyển đổi. Message có thể nằm trong queue nhiều giờ/ngày và được xử lý bởi phiên bản code mới.

## 16. Java SDK: kết nối bằng Microsoft Entra ID

Hai Azure SDK for Java thường dùng:

| Tài nguyên | Artifact Maven | Client |
|---|---|---|
| Queue Storage | `com.azure:azure-storage-queue` | `QueueClient`, `QueueServiceClient` |
| Service Bus | `com.azure:azure-messaging-servicebus` | `ServiceBusSenderClient`, `ServiceBusReceiverClient`, processor |
| Credential | `com.azure:azure-identity` | `DefaultAzureCredential` |

Thêm các dependency với phiên bản **tương thích được tổ chức quản lý**. Ví dụ phần `dependencies` trong Maven (properties phải được khai báo ở POM cha hoặc dự án):

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-queue</artifactId>
    <version>${azure.storage.queue.version}</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-messaging-servicebus</artifactId>
    <version>${azure.messaging.servicebus.version}</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>${azure.identity.version}</version>
  </dependency>
</dependencies>
~~~

Đây là đoạn hướng dẫn; không phải POM hoàn chỉnh. Dùng Azure SDK BOM hoặc khóa versions theo dependency policy để tránh xung đột. `DefaultAzureCredential` có thể dùng Azure CLI identity ở local và managed identity ở Azure; **luôn xác minh credential nào được dùng thật** để tránh nhầm quyền môi trường.

### RBAC data-plane tối thiểu

- Queue Storage producer: role như **Storage Queue Data Message Sender** tại scope cần thiết.
- Queue Storage consumer: role như **Storage Queue Data Message Processor** theo quyền thao tác cần dùng.
- Service Bus producer: **Azure Service Bus Data Sender**.
- Service Bus consumer: **Azure Service Bus Data Receiver**.
- Khi tạo queue hoặc namespace, cần **quyền management plane** khác với quyền gửi/nhận message.

Role tùy chỉnh và tài nguyên có thể cần quyền rộng/hẹp khác nhau. Quyền `Contributor` trên resource group không tự có nghĩa client được gửi/nhận message qua Entra data-plane nếu role data-plane chưa được cấp.

## 17. Java: gửi và nhận với Azure Queue Storage

Ví dụ dưới đây giả định queue `image-jobs` **đã tồn tại**, Java project có các SDK phù hợp, và danh tính runtime có quyền send/receive/delete. Địa chỉ storage là placeholder.

### Tạo QueueClient

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueClientBuilder;

public final class StorageQueueClients {
    private StorageQueueClients() {}

    public static QueueClient connect(String account, String queue) {
        String endpoint = "https://" + account
            + ".queue.core.windows.net/" + queue;

        return new QueueClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }
}
~~~

Dùng `DefaultAzureCredential` giúp tránh nhúng account key trong mã. Đối với production, xác minh RBAC và connectivity qua firewall/private endpoint. Không log credential hoặc connection string.

### Producer gửi message

~~~java
QueueClient queue = StorageQueueClients.connect(
    "<STORAGE_ACCOUNT>", "image-jobs");

String body = "{\"jobId\":\"job-1024\","
    + "\"blobRef\":\"incoming/image-1024.jpg\"}";

queue.sendMessage(body);
System.out.println("Message submitted");
~~~

Producer ở trên chưa có retries/timeout/metrics theo quy định production. Nếu gửi lỗi hoặc timeout, **không thể suy luận chắc message chưa được lưu**: broker có thể đã nhận nhưng response về client bị mất. Dùng job ID ổn định và xử lý duplicate.

### Consumer receive, xử lý, delete

~~~java
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.models.QueueMessageItem;

QueueClient queue = StorageQueueClients.connect(
    "<STORAGE_ACCOUNT>", "image-jobs");

for (QueueMessageItem msg : queue.receiveMessages(1)) {
    String jobId = extractAndValidateJobId(
        msg.getBody().toString());

    // Idempotent: chỉ ghi kết quả nếu jobId chưa hoàn tất.
    processSafely(jobId);

    // Chỉ xóa sau khi business result đã lưu bền vững.
    queue.deleteMessage(msg.getMessageId(), msg.getPopReceipt());
}
~~~

**Hai phương thức `extractAndValidateJobId` và `processSafely` là logic ứng dụng cần triển khai**; ví dụ không phải một class chạy độc lập. Nếu bất kỳ bước nào thất bại, không xóa message. Worker cần xử lý exception, timeout, concurrency, backoff và poison queue theo policy; không gọi `deleteMessage` trong `finally` vô điều kiện.

Nếu SDK/cơ chế mã hóa message dùng Base64, consumer cần giải mã đúng theo quy ước producer và SDK. Không giả định mọi công cụ gửi message đều dùng cùng một chế độ encoding.

## 18. Java: gửi/nhận với Azure Service Bus

Service Bus SDK dùng fully qualified namespace, ví dụ `orders-bus.servicebus.windows.net`, và có các sender/receiver clients.

### Producer gửi vào queue

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;

public class OrderSender {
    public static void main(String[] args) {
        String namespace = "<NAMESPACE>.servicebus.windows.net";

        try (ServiceBusSenderClient sender =
                new ServiceBusClientBuilder()
                    .credential(namespace,
                        new DefaultAzureCredentialBuilder().build())
                    .sender()
                    .queueName("order-jobs")
                    .buildClient()) {

            ServiceBusMessage message =
                new ServiceBusMessage(
                    "{\"orderId\":\"order-1024\",\"version\":1}");

            message.setMessageId("order-1024-process");
            message.setCorrelationId("request-8b91");
            sender.sendMessage(message);
        }
    }
}
~~~

**Lưu ý:** `MessageId` ở đây là khóa ổn định của công việc, hữu ích cho idempotency. Nếu producer muốn phát nhiều lần những sự kiện khác nhau trên cùng một order, nó cần tạo MessageId theo **event ID**, không dùng cùng ID làm mất các sự kiện hợp lệ khi bật duplicate detection.

### Consumer dùng Peek-Lock và complete

~~~java
import java.time.Duration;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusReceiveMode;
import com.azure.messaging.servicebus.ServiceBusReceivedMessage;
import com.azure.messaging.servicebus.ServiceBusReceiverClient;

public class OrderReceiver {
    public static void main(String[] args) {
        String namespace = "<NAMESPACE>.servicebus.windows.net";

        try (ServiceBusReceiverClient receiver =
                new ServiceBusClientBuilder()
                    .credential(namespace,
                        new DefaultAzureCredentialBuilder().build())
                    .receiver()
                    .queueName("order-jobs")
                    .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
                    .buildClient()) {

            for (ServiceBusReceivedMessage msg :
                    receiver.receiveMessages(5, Duration.ofSeconds(10))) {
                try {
                    // TODO: deserialize, validate, use stable idempotency key.
                    processOrderSafely(
                        msg.getBody().toString());
                    receiver.complete(msg);
                } catch (Exception ex) {
                    // TODO: classify permanent vs transient errors.
                    receiver.abandon(msg);
                }
            }
        }
    }
}
~~~

`processOrderSafely` là logic nghiệp vụ phải tự viết. Ví dụ minh họa settlement, **không phải retry policy đầy đủ**. Nếu lỗi không thể phục hồi (schema sai, dữ liệu không hợp lệ), cân nhắc `deadLetter` theo API/SDK phù hợp; nếu gặp lỗi tạm thời có thể `abandon` hoặc để lock hết hạn. Không xử lý message dài hơn lock duration mà không renew hoặc checkpoint.

### Tác vụ dài và lock renewal

Với Service Bus processor API, ứng dụng có thể cấu hình giới hạn concurrent calls, auto-complete, auto-lock-renewal và error handlers theo phiên bản SDK. Nếu dùng synchronous receiver như ví dụ, phải chủ động lập kế hoạch thời gian xử lý/renew lock. **Không tăng concurrency vô hạn** chỉ để bù backlog; backend database hoặc API downstream có thể bị throttling.

## 19. Azure CLI: tạo tài nguyên lab

Các ví dụ dùng **Azure Cloud Shell (Bash)** hoặc CLI đã đăng nhập. Tạo tài nguyên và gửi message có thể phát sinh chi phí. Chỉ chạy trong subscription/resource group thử nghiệm được cho phép; **không** dùng tên, region hoặc credential production.

### Xác nhận subscription

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  -o table
~~~

Khai báo biến:

~~~bash
RG="rg-messaging-lab"
LOC="southeastasia"
STORAGE="<UNIQUE_STORAGE_ACCOUNT>"
SBNS="<UNIQUE_SERVICEBUS_NAMESPACE>"
~~~

Giả sử resource group đã có sẵn. Với tên Storage và namespace, dùng tên **thực tế, hợp lệ và khả dụng toàn cục**.

### Tạo Storage account và queue

~~~bash
az storage account create \
  --name "$STORAGE" \
  --resource-group "$RG" \
  --location "$LOC" \
  --sku Standard_LRS \
  --kind StorageV2
~~~

Nếu identity có role data-plane phù hợp:

~~~bash
az storage queue create \
  --name "image-jobs" \
  --account-name "$STORAGE" \
  --auth-mode login
~~~

Việc tạo queue có thể cần role/quyền khác với chỉ gửi message. Nếu CLI trong môi trường không hỗ trợ `--auth-mode login` cho lệnh tương ứng, xác nhận `az storage queue create --help` và phương pháp xác thực được phép. Không chuyển sang in storage account key chỉ để khắc phục vấn đề RBAC.

### Tạo Service Bus namespace và queue

~~~bash
az servicebus namespace create \
  --resource-group "$RG" \
  --name "$SBNS" \
  --location "$LOC" \
  --sku Standard

az servicebus queue create \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --name "order-jobs"
~~~

Namespace Standard ở đây được dùng để minh họa queue và topic; khi cần Premium, kiểm tra mô hình capacity, chi phí và điều kiện hỗ trợ riêng. Sau khi tạo, hãy cấu hình quyền data-plane để Java sender/receiver hoạt động.

### Tạo topic và subscription

~~~bash
az servicebus topic create \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --name "order-events"

az servicebus topic subscription create \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "order-events" \
  --name "billing"

az servicebus topic subscription create \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "order-events" \
  --name "notifications"
~~~

**Không đồng nhất CLI resource creation với runtime delivery.** Phải cấu hình sender identity/receiver identity, permissions, connection, event filters và các chính sách retention/retry trước khi hệ thống production sử dụng.

### Kiểm tra tài nguyên

~~~bash
az storage queue list \
  --account-name "$STORAGE" \
  --auth-mode login \
  -o table

az servicebus queue show \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --name "order-jobs" \
  -o json
~~~

Các lệnh trên chỉ kiểm tra resource/properties, không phải bằng chứng message được xử lý thành công. Cần gửi message thử và quan sát worker/telemetry.

## 20. Tích hợp Azure Functions, Container Apps và AKS

Queue có thể được tiêu thụ bởi nhiều loại compute:

| Compute | Mô hình phù hợp | Điều cần kiểm tra |
|---|---|---|
| **Azure Functions Queue trigger** | Tự kích hoạt từ Azure Queue Storage | Queue extension, connection, poison queue, concurrency |
| **Azure Functions Service Bus trigger** | Broker message handlers | Lock/retry, DLQ, session support, identity-based settings |
| **Azure Container Apps worker** | Consumer container scale theo queue backlog thông qua scale rules phù hợp | Identity, trigger/scaler, max replicas, graceful shutdown |
| **AKS/VMSS workers** | Cần kiểm soát runtime, batching, networking sâu hơn | Autoscaling theo backlog, SDK reconnect, concurrency, probes |
| **Batch jobs** | Tác vụ nặng có deadline/lịch | Checkpoint, partitioning, retry, lifecycle tài nguyên |

Azure Functions có binding riêng cho Queue Storage và Service Bus. **Các binding này không có cùng config/retry/poison semantics** chỉ vì cùng dùng tên `@QueueTrigger` hoặc có chung pattern “trigger từ queue”.

### Ví dụ pipeline

~~~text
HTTP API -> Queue Storage -> Azure Functions resize worker -> Blob Storage
~~~

Phù hợp khi mỗi ảnh là công việc độc lập, có thể thử lại, không cần thứ tự hoặc fan-out.

~~~text
HTTP API -> Service Bus Topic -> Billing subscription -> Billing worker
                             -> Email subscription   -> Notification worker
                             -> Audit subscription   -> Audit worker
~~~

Phù hợp khi một sự kiện cần nhiều consumer nghiệp vụ, mỗi consumer có DLQ/retry và owner riêng.

### Scaling không phải chỉ tăng consumer

Nếu producer gửi nhanh hơn consumer xử lý, backlog tăng. Tăng replica quá nhanh cũng có thể làm Storage/Database bên dưới bị nghẽn. Cần xác định:

- Throughput worker thực tế và chi phí mỗi job.
- Giới hạn concurrency, prefetch/batching, lock duration hoặc visibility timeout.
- Rate limit của downstream APIs.
- Số message đang chờ và tuổi message cũ nhất.
- Deadline/SLO của công việc.
- Khả năng scale và giới hạn quota của hosting plan/namespace/storage account.

## 21. Bảo mật: identity, RBAC và network

### Prefer Microsoft Entra ID

Sử dụng **managed identity** trong Azure Functions, Container Apps, AKS workload identity hoặc VM/VMSS khi được hỗ trợ. Cấp quyền đúng vai trò send/receive và scope:

- Producer không cần quyền receive/delete nếu chỉ gửi.
- Consumer không cần quyền tạo/xóa queue hoặc thay đổi namespace.
- Administrator có thể cần quyền quản trị, nhưng không có nghĩa ứng dụng cũng cần.
- Dùng scope ở queue hoặc namespace/storage account theo mô hình role thực tế.

**Shared Access Signature (SAS)** vẫn có những tình huống sử dụng phù hợp và giới hạn theo dịch vụ, nhưng phải quản lý vòng đời, xoay khóa/authorization rules, thời hạn và không ghi token vào logs. Với thiết kế mới trong Azure, identity-based auth thường giảm nhu cầu phân phối secret dài hạn.

### Private connectivity

- Queue Storage tuân thủ mạng/storage firewall và private endpoint của Storage account khi tính năng được sử dụng.
- Service Bus có các tùy chọn firewall, private connectivity hoặc network restrictions **phụ thuộc tier và loại triển khai**.
- Cần kiểm tra DNS trả đúng địa chỉ private/public mong muốn, route, NSG/firewall, outbound port và service endpoints liên quan.
- Nếu producer/consumer chạy ở mạng on-premises, đánh giá VPN/ExpressRoute và private DNS resolvers.
- Không giả định bật Private Endpoint tự động tắt mọi public access; phải kiểm tra cấu hình và chính sách cụ thể.

Một lỗi `403 Unauthorized` có thể do RBAC/SAS hoặc network firewall tùy mã lỗi và dịch vụ; lỗi timeout có thể là DNS/route/proxy. Luôn lấy **request ID, error code và context** thay vì đoán.

### Payload security

- Không cho consumer deserialize type tùy ý từ nguồn không tin cậy.
- Kiểm tra schema, kích thước, giới hạn field, loại sự kiện và quyền truy cập dữ liệu tham chiếu.
- Mã hóa dữ liệu nhạy cảm khi chính sách yêu cầu, ngoài mã hóa lưu trữ/đường truyền của nền tảng.
- Tránh ghi toàn bộ message body chứa PII vào Application Insights hoặc DLQ troubleshooting logs.
- Đặt TTL/retention và xóa dữ liệu theo yêu cầu tuân thủ.

## 22. Monitoring và alert cho hàng đợi

Một hệ thống queue khỏe không chỉ là “queue tồn tại”. Cần chứng minh message **được xử lý thành công trong thời hạn** và không tích tụ lỗi.

### Bộ metric tối thiểu

| Nhóm | Dữ liệu cần quan sát | Ý nghĩa |
|---|---|---|
| Queue depth | Số message đang chờ/đang hoạt động theo scope metric | Backlog có tăng không? |
| Oldest message age | Tuổi message chưa xử lý lâu nhất (nếu có telemetry phù hợp) | Có vi phạm deadline? |
| Enqueue/dequeue rate | Số message vào/ra theo thời gian | Producer có nhanh hơn consumer? |
| Success rate | Số **business jobs hoàn thành** | Broker operations không thay thế nghiệp vụ |
| Retry/dequeue/delivery count | Message bị thử lại bao nhiêu lần | Lỗi tạm thời hay poison? |
| DLQ/poison depth | Message bị cách ly | Cần xử lý thủ công hay sửa code? |
| Processing latency | Thời gian từ enqueue đến hoàn tất | SLO end-to-end |
| Exceptions/throttling | Error code, timeout, 429/503, lock lost | Giới hạn dịch vụ hoặc network |
| Cost | Broker/storage, operations, transfer, logs, compute | Chi phí trên một job thành công |

Các tên metric hiện thực trong Azure Monitor khác nhau giữa **Storage Queue** và **Service Bus Namespace/Queue/Topic/Subscription**. Hãy kiểm tra metric definitions ở đúng resource; không tạo alert dựa trên tên metric chưa được dịch vụ công bố.

### Phối hợp với application telemetry

Broker biết message được gửi/nhận/complete ở một mức độ nhất định, nhưng không biết rõ **hóa đơn đã tạo đúng hay chưa**, ảnh đã xử lý có checksum chính xác không hoặc người dùng đã nhận thông báo chưa. Vì thế consumer nên log:

- Stable `messageId` và `jobId`.
- Correlation ID từ request ban đầu.
- Kết quả xử lý và mã lỗi được chuẩn hóa.
- Attempt count, processing duration, external dependency status.
- Checkpoint/version nếu job dài.
- Không log secrets hoặc payload nhạy cảm.

### Alert gắn với hành động

1. Queue backlog tăng liên tục trên ngưỡng và thời gian xác định.
2. Tuổi job cũ nhất vượt SLO.
3. DLQ/poison queue có message mới hoặc tăng nhanh.
4. Consumer không xử lý message trong thời gian dự kiến.
5. Retry/lock lost/visibility timeout nhiều bất thường.
6. Producer gặp nhiều lỗi gửi hoặc unauthorized.
7. Chi phí operations/compute tăng không tương xứng số job hoàn tất.

## 23. Chi phí và giới hạn phải kiểm chứng

### Queue Storage

Chi phí có thể gồm:

- Dung lượng lưu trữ queue data theo mô hình Storage.
- Các thao tác đọc/ghi/list/delete và request/transaction liên quan.
- Data transfer, kết nối private/network và giám sát theo cấu hình.
- Compute consumer/producer: Azure Functions, Container Apps, VM hoặc AKS.

Hàng đợi đơn giản có thể kinh tế, nhưng **polling quá thường xuyên khi queue rỗng** vẫn làm tăng operations và tài nguyên. Cần chọn khoảng polling/backoff và tận dụng trigger/SDK hợp lý.

### Service Bus

Chi phí thay đổi theo tier, số lượng operations/messages, mức tài nguyên/công suất được cấp, features và region. Premium có mô hình năng lực tài nguyên khác Standard, phục vụ những yêu cầu hiệu năng, isolation hoặc networking theo thiết kế dịch vụ.

**Không nhân đơn giản “số messages × một đơn giá cố định”** nếu workload dùng topics nhiều subscriptions, filters, transactions, forwarding hoặc Premium capacity. Một message gửi tới topic có thể tạo nhiều bản giao nhận logic và operations khi nhiều subscriptions cần nhận.

### Những quota cần xem trước production

- Kích thước message và batch theo API, SKU/tier.
- Số queues, topics, subscriptions, connection/receiver và sessions được hỗ trợ.
- Maximum retention/TTL, size của queue/entity/namespace.
- Throughput/request rate và giới hạn mạng.
- Duplicate detection history window.
- Lock duration/renewal, delivery count và DLQ.
- Capacity và khả năng scale của producer/consumer hosting.
- Availability và hỗ trợ private endpoint cho đúng tier.

### Chi phí trên kết quả thành công

~~~text
Tổng chi phí pipeline
  = broker/storage + producer/consumer compute
  + network + monitoring + retries/rework
  + chi phí vận hành bổ sung

Chi phí trên job hoàn tất hợp lệ
  = Tổng chi phí pipeline / số job hoàn tất hợp lệ
~~~

So sánh các dịch vụ theo **kịch bản tải thực tế**: tần suất polling, số subscriptions, tỷ lệ retry, payload size và deadline, không chỉ giá message niêm yết.

## 24. Tình huống A: xử lý ảnh theo lô

Một website tải lên ảnh vào Blob Storage, cần tạo thumbnail ở ba kích thước. Công việc độc lập, có thể xử lý lại, kết quả có tên file theo `imageId` và biến thể kích thước.

**Thiết kế gợi ý:**

~~~text
Client -> Upload API -> Blob Storage
                    -> Queue Storage: image-jobs
Queue Storage -> Functions/Container Apps workers
Workers -> thumbnails container
Workers -> job-status store
~~~

Lý do chọn Queue Storage:

- Không cần topics/filters broker.
- Mỗi ảnh là công việc có thể chia nhỏ.
- Output có thể idempotent theo `imageId` và size.
- Worker có thể retry sau visibility timeout.
- Poisons có thể được chuyển sang queue lỗi riêng hoặc Functions poison queue.

**Các bẫy:** gửi message trước khi upload blob hoàn tất, queue message chứa SAS dài hạn, worker làm xong nhưng không xóa message, visibility timeout quá ngắn, lặp lại file output, không có alert backlog.

Nếu về sau cần thông báo cho nhiều hệ thống độc lập khi ảnh hoàn tất, có thể bổ sung event flow phù hợp hoặc đánh giá Service Bus Topic cho bước sự kiện nghiệp vụ. Không nhất thiết phải thay Queue Storage xử lý thumbnail ban đầu.

## 25. Tình huống B: phát sự kiện đơn hàng cho nhiều dịch vụ

Một hệ thống thương mại điện tử phát `OrderPlaced`. Ba hệ thống xử lý riêng:

- **Billing:** tạo hóa đơn; yêu cầu idempotency và DLQ.
- **Fulfillment:** tạo công việc kho; cần đảm bảo thứ tự theo đơn trong một số workflow.
- **Notifications:** gửi email; lỗi tạm thời có thể retry riêng.

**Thiết kế gợi ý:**

~~~mermaid
flowchart LR
  APP["Order API + transactional outbox"] --> PUB["Outbox publisher"]
  PUB --> TOPIC["Service Bus Topic: order-events"]
  TOPIC --> BILL["Subscription: billing"]
  TOPIC --> FUL["Subscription: fulfillment"]
  TOPIC --> NOTI["Subscription: notifications"]
  BILL --> BW["Billing processor"]
  FUL --> FW["Fulfillment processor"]
  NOTI --> NW["Notification processor"]
  BILL --> DLQ["Billing DLQ khi lỗi cần xử lý"]
~~~

Lý do chọn Service Bus:

- Topic/subscriptions giảm coupling giữa producer và các nhóm nghiệp vụ.
- Mỗi subscription có thể thiết lập xử lý lỗi/retention riêng theo khả năng dịch vụ.
- DLQ hỗ trợ quy trình điều tra.
- Sessions có thể được cân nhắc cho một số nhóm thông điệp cần thứ tự.
- Duplicate detection có thể hỗ trợ giảm một số bản gửi trùng, **nhưng không thay thế idempotency** của Billing.

**Các bẫy:** cho rằng một message hoàn tất ở billing sẽ biến mất khỏi notifications, đặt cùng một session cho mọi đơn khiến giảm throughput, dùng MessageId không ổn định, bỏ qua outbox khi cập nhật DB, gửi lại DLQ hàng loạt mà chưa sửa lỗi.

## 26. Bảng chẩn đoán sự cố

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Producer gửi không thành công | RBAC, SAS, DNS/firewall, quota hoặc payload quá lớn | Kiểm tra response code, identity, mạng, size |
| Queue Storage message được xử lý hai lần | Visibility timeout hết, worker crash, delete lỗi | Idempotency, timeout/renewal, pop receipt mới |
| Queue Storage message không biến mất | Worker không delete, pop receipt cũ | Đọc logs và thao tác delete với receipt hợp lệ |
| Queue Storage backlog tăng | Worker ít, polling chậm, downstream nghẽn | Quan sát enqueue/dequeue rate, tăng xử lý có kiểm soát |
| Service Bus `MessageLockLost` | Xử lý quá lâu, lock hết hạn, mất connection | Renew lock, giảm thời gian xử lý, checkpoint |
| Service Bus message vào DLQ | Max delivery count, TTL/rules hoặc dead-letter chủ động | Đọc reason và sửa nguyên nhân, replay chọn lọc |
| Service Bus consumer không nhận message | Queue/topic/subscription sai, filter, sessions hoặc quyền | Kiểm tra entity, rule, receiver type và RBAC |
| Message cùng order bị sai thứ tự | Nhiều consumer, retry, không có session | Thiết kế session key và receiver có hỗ trợ |
| Duplicate detection không loại bản trùng | MessageId đổi, hết cửa sổ hoặc chưa bật feature | Kiểm tra entity settings, MessageId, thời gian |
| Queue có message nhưng Functions không chạy | Connection setting, extension, managed identity hoặc trigger lỗi | Host logs, extension, bindings, role và queue name |
| HTTP API đã tạo order nhưng thiếu event | DB commit rồi publish thất bại | Transactional outbox, publisher retry |
| Processing latency tăng dù queue rỗng | Downstream chậm, SDK retries hoặc consumer startup | App traces, dependency metrics, concurrency |
| Private Endpoint không hoạt động | Private DNS/route/NSG/firewall hoặc tier không hỗ trợ | DNS, network path, policy, resource settings |
| Bill tăng mạnh | Polling rỗng, nhiều subscriptions, retries/logs | Cost Management và operations breakdown |

## 27. Bài thực hành tổng hợp: hai kiến trúc cho một nhu cầu

### Đề bài

Một ứng dụng nhận file PDF, trích xuất nội dung và gửi thông báo sau xử lý. Ban đầu có một nhóm consumer; sáu tháng sau cần thêm hai nhóm độc lập: analytics và compliance.

**Yêu cầu chức năng:**

- API trả về nhanh sau khi nhận yêu cầu.
- PDF nằm ở Blob Storage.
- Mỗi tác vụ có `jobId` ổn định, trạng thái và correlation ID.
- Worker có thể mất kết nối hoặc restart.
- Lỗi schema phải được phân loại khác timeout.
- Người dùng phải tra được kết quả xử lý.
- Hệ thống có kiểm soát bảo mật, log và chi phí.

### Phần A — Thiết kế ban đầu bằng Queue Storage

1. Vẽ producer, Storage Queue, consumer và Blob Storage.
2. Xác định message schema nhỏ, chỉ chứa job ID và tham chiếu PDF.
3. Chọn visibility timeout dựa trên thời gian xử lý **một bước**, không phải tổng thời gian job lớn.
4. Xây idempotency: một `jobId` không tạo hai kết quả nghiệp vụ khác nhau.
5. Viết quy trình khi worker chết trước khi delete message.
6. Chọn cách xử lý poison message khi `dequeueCount` vượt ngưỡng.
7. Định nghĩa metric queue depth, oldest job age, successful completions và retries.
8. Dự kiến những quyền Entra ID cần cho producer, consumer và operator.

### Phần B — Thiết kế khi cần fan-out bằng Service Bus

1. Xác định sự kiện `DocumentProcessed` khác lệnh `ProcessDocument` ở điểm nào.
2. Chọn Queue cho command processing và Topic cho sự kiện gửi tới nhiều bộ phận nếu phù hợp.
3. Vẽ Topic `document-events` với subscriptions `analytics`, `compliance` và `notifications`.
4. Xác định nơi dùng DLQ và người chịu trách nhiệm xử lý.
5. Chọn MessageId, correlationId, schemaVersion và retention phù hợp.
6. Đánh giá có thực sự cần sessions/duplicate detection không.
7. Mô tả outbox nếu cập nhật document status trong database đồng thời publish event.
8. Thiết kế quyền send/receive theo subscription, không chia sẻ connection string toàn quyền.
9. So sánh chi phí, độ phức tạp và lợi ích so với ba Queue Storage queues.
10. Mô tả rollback khi Service Bus consumer mới hoạt động sai.

### Phần C — Lab Java/Azure CLI

Trên subscription/resource group thử nghiệm, với các SDK và quyền đã được cài/cấp:

1. Tạo Storage account/queue `image-jobs` hoặc tên phù hợp lab.
2. Tạo Service Bus namespace Standard/queue `order-jobs`.
3. Tạo topic và hai subscriptions để kiểm tra fan-out.
4. Dùng Java SDK gửi một message vào Queue Storage.
5. Nhận message bằng pop receipt, xử lý giả lập và delete khi thành công.
6. Thử dừng consumer **trước khi delete** trong lab; quan sát message được giao lại.
7. Dùng Service Bus Java SDK gửi và nhận một message ở Peek-Lock mode.
8. Xử lý thành công bằng `complete`, mô phỏng transient error bằng `abandon`.
9. Tạo một message lỗi hợp lệ cho lab và thực hành quy trình DLQ theo policy.
10. Quan sát logs/metrics và tính tỷ lệ job thành công.
11. Thu hồi secrets test nếu có, kiểm tra tài nguyên phí phát sinh và dọn tài nguyên lab theo phê duyệt.

**Lưu ý:** không dùng queue hoặc topic production để kiểm thử retry/dead-letter, không gửi PII/secret trong message thực hành và không xóa resource group chứa tài nguyên dùng chung.

### Câu hỏi tự kiểm tra

**Câu 1.** Khác biệt cốt lõi giữa Azure Queue Storage và Azure Service Bus là gì khi workload chỉ có một nhóm consumer?

**Câu 2.** Một message Queue Storage có được xóa ngay sau khi receive không? Khi nào cần pop receipt?

**Câu 3.** Khi visibility timeout hết trong lúc worker còn xử lý, điều gì có thể xảy ra?

**Câu 4.** Service Bus `complete`, `abandon`, `deadLetter` và `defer` khác nhau thế nào?

**Câu 5.** Vì sao Service Bus Topic cần Subscriptions để nhiều hệ thống nhận cùng một sự kiện?

**Câu 6.** Với một đơn hàng, vì sao sessions có thể hữu ích nhưng không cần cho toàn bộ message queue?

**Câu 7.** Broker duplicate detection có thay thế unique constraint và idempotency ở database không?

**Câu 8.** Queue Storage có built-in DLQ giống Service Bus không? Azure Functions Queue trigger poison queue là tính năng của lớp nào?

**Câu 9.** Nếu DB commit thành công rồi producer chết trước khi gửi event, pattern nào nên được đánh giá?

**Câu 10.** Vì sao cần đo oldest message age và business completion thay vì chỉ queue depth?

**Câu 11.** Managed identity được cấp quyền pull/read Blob có tự cho phép gửi message Service Bus hay Queue Storage không?

**Câu 12.** Một message kích thước lớn nên được thiết kế thế nào và vì sao không nên nhét toàn bộ file vào body?

**Câu 13.** Lợi ích và chi phí khi chuyển từ một Queue Storage queue sang Service Bus Topic với nhiều subscriptions?

**Câu 14.** Với workload thanh toán, nên chọn Receive-and-Delete hay Peek-Lock? Vì sao?

**Tiêu chí hoàn thành:** người học giải thích được bản chất messaging, chọn Queue Storage/Service Bus theo tính năng và ràng buộc, thiết kế idempotency/poison/DLQ, thực hiện send/receive an toàn bằng Java, và đánh giá bảo mật, vận hành và chi phí của hai phương án.

## Kết luận

**Azure Queue Storage** là lựa chọn phù hợp cho những **task queue đơn giản**, nhiều worker có thể xử lý công việc độc lập, dễ tích hợp Azure Storage và tự quản lý idempotency/poison processing. **Azure Service Bus** đáng cân nhắc khi ứng dụng cần **message broker nâng cao**: topics/subscriptions, dead-lettering tích hợp, sessions, duplicate detection, scheduling, lock/settlement hoặc transaction operations theo phạm vi hỗ trợ.

Dù chọn dịch vụ nào, thông điệp có thể được thử lại, consumer có thể chết ngay sau khi ghi kết quả, payload có thể lỗi và backlog có thể tăng khi downstream chậm. Thiết kế bền vững cần **message IDs ổn định, payload có schema, xử lý idempotent, retry/backoff hữu hạn, dead-letter/poison runbook, Entra ID/RBAC, bảo mật mạng, telemetry theo job và kiểm soát chi phí**. Khi đánh giá hai dịch vụ bằng các tiêu chí đó thay vì chỉ bằng tên sản phẩm, bạn sẽ xây dựng hệ thống Azure dễ mở rộng và vận hành đáng tin cậy hơn.

