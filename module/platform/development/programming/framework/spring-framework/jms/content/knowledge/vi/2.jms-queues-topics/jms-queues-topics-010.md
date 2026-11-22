# Chọn Queue hay Topic theo hợp đồng giao tiếp

## Mục tiêu của bài học

Khi thiết kế giao tiếp bất đồng bộ bằng **JMS / Jakarta Messaging trong Spring**, quyết định “Queue hay Topic?” phải xuất phát từ **hợp đồng giữa bên phát thông điệp và những bên có trách nhiệm xử lý**. Tên công nghệ, số lượng instance đang chạy hoặc việc hệ thống “có nhiều service” tự chúng không quyết định kiểu destination.

Sau bài này, bạn cần xác định được:

1. Một thông điệp là **yêu cầu giao việc** cho một nhóm worker hay **sự kiện/thông báo** mà nhiều nhóm xử lý độc lập cần biết.
2. Ai có quyền nhận, mỗi nhóm phải nhận bao nhiêu bản, khi consumer ngắt kết nối có được bỏ lỡ hay không.
3. Queue, Topic, **subscription**, consumer cạnh tranh, durable/shared subscription tác động như thế nào tới kết quả.
4. Bảo đảm giao nhận, khả năng nhận lại (redelivery), idempotency, thứ tự và giới hạn replay phải ghi trong hợp đồng ra sao.
5. Cách áp dụng và kiểm tra quyết định bằng `JmsTemplate`, `@JmsListener` và cấu hình Spring JMS.

**Quy tắc định hướng:** Nếu *một đơn vị công việc* nên được xử lý bởi **một thành viên bất kỳ trong cùng nhóm**, thường chọn **Queue**. Nếu *một sự kiện* phải được nhiều **nhóm nhận độc lập** xử lý, thường chọn **Topic với subscription tương ứng cho từng nhóm**. Có ngoại lệ; hãy đối chiếu toàn bộ hợp đồng ở phần sau.

## 1. Mô hình giao nhận thật sự

### 1.1. Queue: nhiều consumer tranh nhận trên cùng một hàng đợi

Trong mô hình point-to-point của Jakarta Messaging:

- Producer gửi message vào một **queue**.
- Nhiều consumer cùng nghe queue tạo thành các **competing consumers**.
- Với một lần phân phối bình thường, mỗi message được giao cho **một consumer** trong số những consumer đủ điều kiện; consumer khác trên cùng queue không tự có một bản sao.
- Message chưa được xử lý có thể nằm chờ trên queue dù tạm thời chưa có consumer, trong giới hạn TTL, lưu trữ, chính sách broker và khả năng khôi phục.
- Chuẩn **không quy định** thuật toán chia tải giữa các consumer; không nên cam kết “luân phiên 50/50”.

~~~text
                          +---> Worker A
Producer ---> [orders.work QUEUE] ---> Worker B
                          +---> Worker C

Mỗi lần giao một message: chỉ một worker trong nhóm nhận nó.
Nếu worker gặp lỗi trước khi xác nhận, message có thể được giao lại.
~~~

Ví dụ: `GenerateInvoice(invoiceId=17)` là yêu cầu thực hiện một công việc. Nếu có ba bản sao của dịch vụ Invoice Worker để tăng thông lượng, cả ba cùng subscribe một queue; một message cần có **một lần hoàn tất nghiệp vụ**, dù nhiều lần thử có thể xảy ra.

**Điểm dễ hiểu sai:** “Một consumer nhận” là ngữ nghĩa **phân phối**, không phải cam kết **exactly-once business processing**. Consumer có thể xử lý rồi chết trước khi commit/ack, làm cùng công việc chạy lại. Hợp đồng phải yêu cầu idempotency hoặc cơ chế chống trùng.

### 1.2. Topic: nhiều subscription cùng nhận một sự kiện

Trong mô hình publish/subscribe của Jakarta Messaging:

- Producer publish message vào một **topic**.
- Mỗi **subscription** đủ điều kiện sẽ có phần việc riêng cho message đó.
- Một topic có thể có nhiều subscription, ví dụ Billing, Analytics, Notification.
- **Xác nhận/rollback của một subscription độc lập với subscription khác** ở mức message được phân phối cho từng subscription.
- Topic **không mặc định phát mỗi message cho mọi process đang tồn tại**. Cần xem process đang thuộc subscription nào và subscription đó có tồn tại lúc publish hay không.

~~~text
                               +---> [Billing subscription] ---> Billing worker(s)
Producer ---> [orders.events TOPIC]
                               +---> [Email subscription] -----> Email worker(s)
                               +---> [Audit subscription] -----> Audit worker(s)

Một sự kiện -> mỗi subscription độc lập có phần thông điệp của mình.
Nhiều worker cùng chia sẻ một subscription -> cùng tranh xử lý bản của subscription đó.
~~~

Ví dụ: `OrderPlaced(orderId=17)` đã xảy ra. Billing lập hóa đơn, Stock giữ hàng, Analytics thống kê: mỗi **nhóm nghiệp vụ** cần phản ứng riêng. Nếu cho cả ba service đọc cùng **một queue**, chỉ một service nhận mỗi message và hai service còn lại bỏ lỡ.

### 1.3. “Consumer”, “subscription” và “service” khác nhau

Đây là chìa khóa để chọn đúng:

| Thuật ngữ | Ý nghĩa trong quyết định |
| --- | --- |
| **Producer** | Bên phát thông điệp; phát hành command hay event theo hợp đồng |
| **Queue** | Một nơi tích lũy công việc; các consumer đọc cùng queue cạnh tranh nhau |
| **Topic** | Điểm publish; broker phân phối bản message cho từng subscription phù hợp |
| **Subscription** | Sự đăng ký của một nhóm nhận topic; có danh tính, bộ lọc, tùy chọn durability/shared |
| **Consumer** | Đối tượng/client thực sự gọi receive hoặc nhận callback; một service có thể có nhiều consumer |
| **Service group** | Nhóm business capability cần xử lý một loại thông điệp; có thể chạy nhiều replica |
| **Replica/instance** | Một tiến trình/Pod triển khai của service; số replica không nhất thiết bằng số subscription |

Hai instance của **cùng một dịch vụ** thường *chia tải trong một nhóm*. Hai **dịch vụ khác mục đích** thường cần *mỗi nhóm một bản độc lập*. Tăng từ 1 lên 10 replica không nên làm thay đổi số **lần hoàn tất logic** mà hợp đồng yêu cầu.

## 2. Ma trận lựa chọn theo điều khoản của hợp đồng

| Điều khoản cần xác định | Hướng Queue | Hướng Topic |
| --- | --- | --- |
| **Ai phải xử lý?** | Một worker bất kỳ trong một nhóm | Nhiều nhóm đăng ký độc lập |
| **Tăng replica** | Các consumer cạnh tranh trên cùng queue | Các replica trong *một* nhóm dùng shared subscription nếu cần chia tải |
| **Nhóm nhận khác mục đích** | Phải tạo queue riêng và cơ chế fan-out bên ngoài | Mỗi nhóm có subscription riêng trên topic |
| **Tạm thời không có consumer** | Queue thường giữ message chờ consumer theo chính sách broker | Chỉ subscription **durable đã được tạo** mới giữ khi không có consumer; non-durable có thể mất |
| **Trạng thái đăng ký** | Không có khái niệm durable topic subscription | Có non-durable/durable và shared/unshared |
| **Tăng thêm nhóm nhận** | Thường phải thêm bước route/copy thông điệp | Nhóm mới có thể đăng ký topic, nhưng không tự có lịch sử trước khi đăng ký |
| **Xử lý thất bại** | Retry/redelivery gắn message trong queue | Mỗi subscription theo dõi việc xử lý bản riêng, với chính sách retry/DLQ tùy broker |
| **Replay lịch sử tùy mốc** | Không mặc nhiên có | Cũng không mặc nhiên có; durable subscription không thay event log |
| **Số message nghiệp vụ mong đợi** | Khoảng một lần xử lý hoàn tất cho mỗi command (thiết kế idempotent) | Một lần xử lý hoàn tất **cho từng nhóm** đủ điều kiện (thiết kế idempotent từng nhóm) |

Cần phân biệt **durable subscription của topic** với **persistent delivery mode của message**. Persistent liên quan khả năng broker bảo toàn message theo chính sách; durable subscription liên quan việc subscriber **không online** vẫn giữ lại message. Gửi persistent lên topic **không tự tạo** durable subscription cho consumer đăng ký sau.

## 3. Quy trình quyết định 6 câu hỏi

### Câu 1 — Thông điệp mô tả hành động cần làm, hay điều đã xảy ra?

- **Command** (mệnh lệnh/yêu cầu công việc): `SendReceipt`, `RebuildIndex`, `ReserveSeat`. Thường một capability chịu trách nhiệm chính, nên Queue phù hợp. Tên và nội dung mô tả một nhiệm vụ.
- **Event** (sự kiện): `PaymentCaptured`, `UserRegistered`, `ProductPriceChanged`. Nhiều capability có thể phản ứng độc lập; Topic thường phù hợp. Tên mô tả điều đã xảy ra.
- **Notification** (thông báo): có thể là event nhiều nhóm cần nhận hoặc yêu cầu gửi một email duy nhất. Hãy nhìn vào **số trách nhiệm xử lý**, không chỉ tên gọi.

“Command = Queue, Event = Topic” là một **heuristic**, không phải quy luật tuyệt đối. Một event có thể được chuyển qua queue riêng của một service; một command fan-out có thể có hợp đồng riêng. Nhưng cần ghi rõ ai sở hữu message và ai cần nhận bản sao.

### Câu 2 — Có bao nhiêu **nhóm nghiệp vụ độc lập** phải nhận?

- **Chỉ một nhóm xử lý** → Queue là mặc định đơn giản.
- **Nhiều nhóm, tất cả đều phải xử lý** → Topic; mỗi nhóm subscription riêng.
- **Chỉ một nhóm hiện tại nhưng muốn thêm listener cho metrics** → không đặt metrics reader tranh nhận vào queue nghiệp vụ; cân nhắc publish event riêng sau khi trạng thái đã thành công.
- **Một phần nhóm phải nhận theo điều kiện** → Topic cộng message selector/routing phù hợp; selector có ràng buộc cú pháp và schema, có thể tạo tải lớn tùy broker.

Đừng đếm số container/Kubernetes Pod. Đếm **số cam kết nghiệp vụ độc lập** cần hoàn tất.

### Câu 3 — Consumer offline có được bỏ lỡ message không?

Đối với Queue, message thường chờ khi nhóm worker offline theo TTL, quota và cấu hình broker.

Đối với Topic, cần chọn loại subscription:

| Subscription | Khi không có consumer | Khi có nhiều consumer cùng nhóm |
| --- | --- | --- |
| **Non-durable, unshared** | Không giữ backlog sau khi subscription kết thúc | Chỉ một consumer trên subscription |
| **Non-durable, shared** | Không còn subscription nếu consumer cuối đóng; có thể bỏ lỡ khi cả nhóm offline | Nhiều consumer chia bản của cùng subscription |
| **Durable, unshared** | Giữ các message đủ điều kiện phát **sau khi subscription đã tạo** (trừ hết hạn/chính sách) | Một consumer hoạt động tại một thời điểm |
| **Durable, shared** | Cũng giữ backlog theo danh tính subscription | Nhiều consumer chia tải trên cùng durable subscription |

Trong Jakarta Messaging 3.x, **shared durable subscription** có thể không yêu cầu `clientID`, trong khi **unshared durable** cần `clientID` và tên subscription ổn định. Đừng cấp cùng một `clientID` không phù hợp cho nhiều instance rồi mong có thể chạy song song.

Ví dụ chính sách: Marketing dashboards chấp nhận bỏ lỡ telemetry nếu tắt, có thể dùng non-durable. Accounting phải xử lý mọi `PaymentCaptured` kể cả khi deploy/restart, thường cần durable subscription **được tạo trước thời điểm publish**.

### Câu 4 — Một nhóm cần chạy nhiều instance để chia tải không?

- Với **Queue**: thêm consumer cho cùng queue; mỗi message được phân phối cho một consumer đủ điều kiện.
- Với **Topic**: muốn hai replica cùng thực thi *những message khác nhau của cùng nhóm*, dùng **shared subscription** (thường shared durable cho tác vụ nghiệp vụ quan trọng). Nếu tạo hai subscription độc lập, mỗi replica có thể xử lý **mọi event**, gây xử lý trùng theo thiết kế.
- Với **unshared durable topic subscription**: không bật nhiều consumer đồng thời trên cùng subscription; sẽ xung đột theo quy tắc API/provider.

Một topic với ba subscription nghiệp vụ, mỗi subscription có hai worker, thường tạo **ba bản logic cho mỗi event** (một bản cho mỗi nhóm), sau đó mỗi bản được một trong hai worker của nhóm tương ứng xử lý. Không phải sáu bản logic.

### Câu 5 — Cần thứ tự, retry và ghi nhận giao dịch như thế nào?

Chọn Queue/Topic **không tự giải quyết** thứ tự hay giao dịch:

- **Thứ tự:** nhiều producer, competing consumers, concurrent handler, redelivery và message selector có thể khiến thứ tự business processing khác thứ tự publish. Nếu bắt buộc tuần tự theo `orderId`, mô tả invariant theo khóa, đồng thời cân nhắc giới hạn concurrency/partition/message grouping mà provider thực sự hỗ trợ.
- **Redelivery:** khi consumer lỗi, không ack hoặc rollback, broker có thể giao lại message; một consumer khác có thể nhận bản giao lại.
- **Idempotency:** dùng `messageId`/`eventId` hoặc business key riêng để chống lặp trong database. Không dùng mỗi số lần nhận làm bằng chứng message chỉ được xử lý một lần.
- **Commit:** JMS session transaction không tự gom việc ghi DB vào cùng một atomic transaction. Phải thiết kế giao tiếp giữa DB và broker: transaction boundaries, idempotent inbox, outbox, hoặc XA/JTA theo nhu cầu.
- **Poison message:** đặt ngưỡng retry, backoff, DLQ và quy trình sửa/replay theo từng queue/subscription.
- **Expiration / TTL:** dữ liệu hết hạn có thể mất dù destination là queue hay durable topic subscription.

### Câu 6 — Có cần replay lịch sử, fan-out quy mô lớn hoặc dữ liệu kéo dài vô hạn không?

Queue và Topic trong Jakarta Messaging tối ưu cho giao tiếp messaging theo broker và subscription. **Durable subscription không phải event-store hỗ trợ replay tùy ý từ một timestamp cũ**; subscriber mới thường không tự đọc được những event publish trước khi subscription tồn tại. Nếu yêu cầu bắt buộc “đọc lại toàn bộ lịch sử từ 6 tháng trước”, hãy đánh giá event log (chẳng hạn Kafka), lưu trữ domain event riêng hoặc tính năng lưu trữ/replay cụ thể của broker. Dù chọn công nghệ nào, vẫn cần chính sách retention, schema versioning và quyền truy cập dữ liệu.

### Cây quyết định rút gọn

~~~text
Một message phát ra, ai PHẢI hoàn thành xử lý?
|
+-- Chỉ một nhóm chịu trách nhiệm
|     |
|     +-- Nhiều replica? --> Cùng tranh nhận một QUEUE
|     +-- Cần thêm service khác độc lập? --> Xem xét publish EVENT ra TOPIC riêng
|
+-- Nhiều nhóm nhận độc lập
      |
      +-- TOPIC, mỗi nhóm một SUBSCRIPTION riêng
            |
            +-- Chấp nhận lỡ khi offline? --> NON-DURABLE
            +-- Không được lỡ khi offline? --> DURABLE, đăng ký trước khi publish
            |
            +-- Nhiều replica chia tải trong nhóm? --> SHARED subscription
            +-- Một consumer duy nhất? -----------> UNSHARED cũng có thể phù hợp

Sau đó vẫn xác định retry, idempotency, ordering, TTL, DLQ, auth, monitoring.
~~~

## 4. Các tình huống thực tế và quyết định đúng

### Tình huống A — Giao một job cho một trong các worker

Một service nhận yêu cầu tạo PDF; có 5 worker cùng năng lực. Một job chỉ cần tạo một file cuối cùng.

**Hợp đồng:** `RenderPdf(jobId)`, queue `pdf.render.commands`, nhóm `renderer`; mỗi job có một business outcome. Chọn **Queue**; 5 replica cạnh tranh nhận. Dùng `jobId` chống ghi/tạo file trùng khi redelivery. Nếu worker hỏng sau khi ghi file mà trước khi ack, worker khác có thể nhận lại; cần kiểm tra trạng thái job thay vì tạo thêm sản phẩm.

### Tình huống B — Một event, ba hành động độc lập

Order Service đã ghi nhận đơn thành công, phát `OrderPlaced`. Fulfillment chuẩn bị hàng, Customer Care gửi email, Analytics cập nhật báo cáo. Cả ba phải xử lý riêng.

**Hợp đồng:** topic `orders.lifecycle.events` với ba **durable subscription**: `fulfillment-v1`, `customer-care-v1`, `analytics-v1`. Mỗi nhóm scale qua **shared durable subscription** nếu broker/client tương thích. Event chứa `eventId`, `orderId`, `occurredAt` và `schemaVersion`.

**Không được** cho ba service cùng nghe `orders.lifecycle.queue` nếu mong cả ba đều nhận. Một queue chỉ giao mỗi message cho một consumer, có thể khiến Analytics “ăn mất” message của Fulfillment.

### Tình huống C — Hai bản sao của một dịch vụ không phải hai người nhận độc lập

Có 2 Pod Billing. Mỗi `PaymentConfirmed` chỉ được cập nhật hóa đơn **một lần theo nghiệp vụ**. Trên Topic, cả hai Pod cùng tạo **hai non-shared subscription khác nhau** thì cả hai đều nhận event: không đúng ý định load-balancing.

**Hợp đồng đúng:** cả hai Pod thuộc cùng subscription tên `billing-v1`, cấu hình **shared durable**. Chúng cùng chia việc và vẫn phải chống duplicate khi redelivery. Cần một subscription **khác** như `audit-v1` nếu Audit cũng cần bản riêng.

### Tình huống D — Live dashboard được phép bỏ lỡ

Một dashboard chỉ cần số liệu khi đang online, không có nghĩa vụ bắt kịp mọi điểm đo cũ. Topic `live.telemetry` với **non-durable** subscriptions có thể đơn giản và tiết kiệm backlog; dashboard mất kết nối thì những message trong khoảng offline có thể bị bỏ lỡ. Nếu sau đó cần số liệu lịch sử để vẽ lại đồ thị, hãy đọc từ nguồn lưu trữ metrics, không biến non-durable Topic thành kho dữ liệu.

### Tình huống E — Request/reply không tự bắt buộc là Topic

Một service gửi `CheckFraud(requestId)` tới nhóm Fraud Worker và chờ một kết quả. Queue request hợp lý vì một worker thực thi một request; reply có thể đi qua temporary queue/queue hồi đáp với `JMSReplyTo` và `JMSCorrelationID`. Đặt timeout, correlation và handling duplicate reply. Topic chỉ hữu ích nếu **mỗi nhóm** độc lập cần nhận bản request; đó là hợp đồng khác.

### Tình huống F — “Mỗi service một queue” cũng có thể tạo fan-out

Một integration service đọc event đầu vào và **sao chép** đúng một message vào từng queue đích của Billing, Audit, Notification: mỗi queue có competing consumers riêng. Cấu trúc này đạt fan-out nhờ **router/application** đảm nhiệm nhân bản, không phải nhờ bản chất một queue. Khi dùng Topic, broker/subscription thực hiện phần phân phối theo từng nhóm. Chọn theo hạ tầng, vận hành, quyền sở hữu route và yêu cầu quan sát; đừng nói queue *tự* broadcast.

## 5. Viết hợp đồng giao tiếp trước khi code

Nên chốt và version hóa ít nhất các trường sau:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| `messageType` + `schemaVersion` | Đây là command hay event? Payload có schema/version như thế nào? |
| `destination` + `domain` | Destination tên gì, là Queue hay Topic? Ai được quyền publish/consume? |
| **Producer ownership** | Ai chịu trách nhiệm publish? Publish vào thời điểm nào so với commit dữ liệu nguồn? |
| **Consumer group(s)** | Chính xác nhóm nào phải xử lý? Mỗi nhóm có bao nhiêu subscription? |
| **Offline policy** | Khi tất cả consumer trong nhóm dừng, message cần được giữ bao lâu? Durable subscription đã tạo chưa? |
| **Delivery/ack** | Khi nào ack/commit? Retry/redelivery tối đa? TTL/expiration? |
| **Idempotency key** | Dùng `commandId`/`eventId` hay khóa nghiệp vụ nào để bỏ trùng? Lưu ở đâu? |
| **Ordering requirement** | Có cần thứ tự theo `accountId`/`orderId` không? Với concurrency bao nhiêu? |
| **Poison-message policy** | DLQ, retry delay, alert và quy trình xử lý lại là gì? |
| **Observability** | Số message chờ/tuổi message/lần giao lại/DLQ/độ trễ xử lý đo thế nào? |
| **Contract evolution** | Có bao nhiêu phiên bản consumer còn hoạt động? Ai bảo đảm backward compatibility? |

### Hai hợp đồng mẫu

**Mẫu 1: Command xử lý một công việc**

~~~yaml
name: GenerateInvoice
kind: command
destination: invoices.generate.queue
jmsDomain: queue
producer: Checkout
responsibleGroup: InvoiceWorkers
replicas: 3 # competing consumers của cùng queue
idempotencyKey: invoiceRequestId
delivery: retryable, at-least-once business design
ack: after successful handling (transacted listener)
failure: bounded retries -> DLQ, operator review
ordering: no global ordering requirement
schemaVersion: 1
~~~

**Mẫu 2: Event với nhiều nghĩa vụ độc lập**

~~~yaml
name: OrderPaid
kind: event
destination: orders.paid.topic
jmsDomain: topic
producer: PaymentService (sau khi trạng thái thanh toán được commit)
groups:
  - name: fulfillment-v1
    subscription: shared-durable
    replicas: 3
  - name: receipt-v1
    subscription: shared-durable
    replicas: 2
  - name: analytics-v1
    subscription: shared-durable
    replicas: 2
idempotencyKey: eventId (mỗi nhóm tự theo dõi)
offline: no-loss-after-subscription-created, subject to broker retention/TTL
failure: independent retries/DLQ for each subscription
schemaVersion: 1
~~~

Các YAML trên là **hợp đồng mô tả để thảo luận/ghi tài liệu**, không phải cấu hình Spring Boot có thể copy vào `application.yml` và tự hoạt động. “At-least-once business design” mô tả cách ứng dụng chấp nhận giao lại; không thể suy ra mọi điều kiện giao nhận chỉ bằng một YAML.

### Ví dụ envelope cho event

~~~json
{
  "eventId": "evt-2026-10-30-001",
  "type": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-10-30T01:00:00Z",
  "orderId": "order-42",
  "paymentId": "payment-77",
  "amountMinor": 155000,
  "currency": "VND"
}
~~~

`eventId` nhận diện event để chống trùng; `orderId` là khóa đối tượng nghiệp vụ; `schemaVersion` giúp consumer phát hiện payload cần nâng cấp. Đây là JSON payload độc lập với lựa chọn Queue/Topic: JMS có thể mang một `TextMessage` chứa JSON, nhưng cần converter/schema ở hai đầu. Đừng đặt dữ liệu bí mật trực tiếp trong message nếu không có bảo vệ phù hợp.

## 6. Triển khai Queue và Topic trong Spring JMS

Spring JMS hoạt động trên Jakarta Messaging; phương thức `@JmsListener` dùng **listener container** do Spring tạo, còn `JmsTemplate` gửi message. Với **destination name dạng String**, cần phối hợp cấu hình domain ở **cả producer và consumer**:

- `JmsTemplate.setPubSubDomain(false)`: hiểu tên destination là **Queue**.
- `JmsTemplate.setPubSubDomain(true)`: hiểu tên destination là **Topic**.
- `DefaultJmsListenerContainerFactory.setPubSubDomain(...)`: quyết định container lắng nghe queue hay topic.
- `@JmsListener(destination = "...", containerFactory = "...")`: dùng đúng factory của domain.
- `setSubscriptionDurable(true)` và `setSubscriptionShared(true)` dành cho các loại topic subscription tương ứng; đặt tên subscription nhất quán cho mỗi nhóm.

Spring Boot mặc định thường cấu hình JMS hướng **Queue**; có thể bật `spring.jms.pub-sub-domain=true` cho cấu hình mặc định, nhưng cách đó ảnh hưởng cả producer/listener mặc định, **không thích hợp khi cùng ứng dụng cần đồng thời queue và topic**. Lúc này dùng **hai template/factory có tên rõ ràng**.

### 6.1. Lab Java 17+ với ActiveMQ Artemis nhúng: một Queue và một Topic

Mục tiêu: cùng một ứng dụng tạo hai worker tranh nhận **một** message Queue, và hai listener topic độc lập mỗi bên nhận **một bản** của event. Ví dụ dùng **Spring Boot 3.x/4.x tương thích Java 17+**, Spring Framework 6+/7+, package `jakarta.jms`. Broker embedded chỉ phục vụ lab; sản xuất thường sử dụng broker ngoài.

Tạo project Maven `com.example:queue-topic-demo` bằng Spring Initializr (https://start.spring.io/) với dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`). Thêm vào `pom.xml` trong `<dependencies>` hiện có:

~~~xml
<dependency>
  <groupId>org.apache.activemq</groupId>
  <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Nếu dự án dùng Spring Boot parent/BOM, để Spring Boot quản lý version Artemis. Đừng lấy client Artemis `javax.jms` đời cũ để trộn với stack `jakarta.jms`.

Nội dung `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=jobs.demo
spring.artemis.embedded.topics=events.demo
spring.artemis.embedded.persistent=false
~~~

File `src/main/java/com/example/queuetopicdemo/QueueTopicDemoApplication.java` (chọn package project tương ứng):

~~~java
package com.example.queuetopicdemo;

import jakarta.jms.ConnectionFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class QueueTopicDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(QueueTopicDemoApplication.class, args);
    }

    // Hai publisher cùng dùng một ConnectionFactory nhưng khác domain.
    @Bean("queuePublisher")
    JmsTemplate queuePublisher(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        return template;
    }

    @Bean("topicPublisher")
    JmsTemplate topicPublisher(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);
        return template;
    }

    @Bean("queueFactory")
    DefaultJmsListenerContainerFactory queueFactory(ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }

    @Bean("topicFactory")
    DefaultJmsListenerContainerFactory topicFactory(ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(true);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }

    @Bean
    ApplicationRunner publish(
            @Qualifier("queuePublisher") JmsTemplate queue,
            @Qualifier("topicPublisher") JmsTemplate topic) {
        return args -> {
            queue.convertAndSend("jobs.demo", "job-1001");
            topic.convertAndSend("events.demo", "order-paid-2001");
        };
    }

    @Component
    public static class WorkerA {
        @JmsListener(destination = "jobs.demo", containerFactory = "queueFactory")
        public void handle(String jobId) {
            System.out.println("QUEUE WorkerA: " + jobId);
        }
    }

    @Component
    public static class WorkerB {
        @JmsListener(destination = "jobs.demo", containerFactory = "queueFactory")
        public void handle(String jobId) {
            System.out.println("QUEUE WorkerB: " + jobId);
        }
    }

    @Component
    public static class AuditSubscriber {
        @JmsListener(destination = "events.demo", containerFactory = "topicFactory")
        public void onEvent(String eventId) {
            System.out.println("TOPIC Audit: " + eventId);
        }
    }

    @Component
    public static class EmailSubscriber {
        @JmsListener(destination = "events.demo", containerFactory = "topicFactory")
        public void onEvent(String eventId) {
            System.out.println("TOPIC Email: " + eventId);
        }
    }
}
~~~

Chạy từ thư mục gốc dự án có Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Sau khi ứng dụng khởi động và listener đã hoạt động, hãy tìm các dòng **kiểu** sau trong log (bên cạnh log Spring/Artemis):

~~~text
QUEUE WorkerA: job-1001
TOPIC Audit: order-paid-2001
TOPIC Email: order-paid-2001
~~~

**Kết quả hợp lệ khác:** thay dòng `QUEUE WorkerA` bằng `QUEUE WorkerB`. Trong lần chạy ổn định, dự kiến **chỉ một** trong hai worker nhận `job-1001`, còn **cả Audit và Email** nhận `order-paid-2001` do mỗi listener topic thuộc subscription non-durable riêng. **Không cam kết thứ tự ba dòng** vì listener chạy bất đồng bộ; lỗi vận hành hoặc redelivery có thể làm phát sinh log khác. Không dùng ví dụ này để chứng minh “exactly once” trong môi trường có lỗi.

**Vì sao thí nghiệm phân biệt đúng hai hợp đồng?** `jobs.demo` chỉ có một queue nhưng có hai competing consumers. `events.demo` có hai subscription non-durable độc lập (mỗi listener là một subscriber), nên một event phát khi cả hai đang nghe được fan-out thành hai bản.

**Giới hạn của lab:** Topic non-durable không phải cấu hình production nếu Audit/Email không được bỏ lỡ event trong lúc downtime. Broker nhúng `spring.artemis.embedded.persistent=false` không được dùng để chứng minh độ bền khi ứng dụng/broker mất điện. Quyền tạo destination, cấu hình persistent store, địa chỉ broker và policy trong production phụ thuộc hệ thống thực tế.

### 6.2. Đổi subscriber nghiệp vụ sang shared durable

Đối với một nhóm phải xử lý cả khi offline, nên dùng factory riêng (ví dụ `sharedDurableTopicFactory`) và subscription có **tên cố định**. Đoạn dưới là **mảnh cấu hình thay thế/bổ sung**, đặt trong `@Configuration` hoặc class `@SpringBootApplication` đã có; import các class tương ứng:

~~~java
@Bean("sharedDurableTopicFactory")
DefaultJmsListenerContainerFactory sharedDurableTopicFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setSubscriptionShared(true);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-4");
    return factory;
}
~~~

Và ví dụ listener **của một nhóm**:

~~~java
@JmsListener(
    destination = "orders.lifecycle.events",
    subscription = "billing-v1",
    containerFactory = "sharedDurableTopicFactory")
public void onOrderPaid(String payload) {
    // Parse/validate schema, kiểm tra eventId đã xử lý, cập nhật nghiệp vụ,
    // trả thành công sau khi xử lý an toàn.
}
~~~

Đây là **mảnh phương thức** đặt trong Spring-managed bean; không phải class Java độc lập. Mọi replica của Billing dùng **cùng tên subscription** `billing-v1` để chia tải. Nhóm Fulfillment cần tên `fulfillment-v1` riêng; **không chia sẻ** `billing-v1` với Fulfillment. Nếu dùng shared durable trong Jakarta Messaging hiện đại, không tùy tiện cấp mỗi replica một `clientId` khác nhau vì danh tính subscription có thể bị tách nhóm; kiểm tra cách provider định danh và hỗ trợ shared subscription. Một durable subscription chỉ thu thập các sự kiện đủ điều kiện từ khi **được tạo**, không cấp lại event lịch sử trước đó.

Khi đã tùy chỉnh bean listener factory trong ứng dụng Spring Boot, cần bảo đảm các cài đặt mặc định hữu ích của Boot (converter, error handler, transaction manager, destination resolver...) được mang sang nếu cần. Với Boot, có thể dùng `DefaultJmsListenerContainerFactoryConfigurer` tương thích phiên bản dự án để khởi tạo cấu hình mặc định trước khi ghi đè các thuộc tính domain/subscription.

### 6.3. Đừng lẫn queue/topic khi tên destination giống nhau

Cùng chuỗi tên `orders.events` không có nghĩa là một Queue và một Topic có cùng ý nghĩa. JMS phân biệt đối tượng đích là `jakarta.jms.Queue` hay `jakarta.jms.Topic`. Broker có thể ánh xạ tên vào address/routing nội bộ theo cách riêng; ghi rõ **type + name + quyền sở hữu** trong hợp đồng. Khi gửi bằng `JmsTemplate.convertAndSend("orders.events", ...)`, cấu hình `pubSubDomain` quyết định cách tên được resolve; người nhận cũng phải dùng đúng domain.

## 7. Tính đúng đắn và độ tin cậy không đến từ tên Queue/Topic

### 7.1. Semantics phân phối và business outcome

Giả sử producer phát một message. Có các bước tách biệt:

~~~text
Producer phát -> Broker chấp nhận -> Consumer nhận -> Xử lý nghiệp vụ
      -> DB/side-effect hoàn tất -> ack/commit message
~~~

Queue bảo đảm một consumer được chọn cho lần phân phối (không phải một lần chạy nghiệp vụ vĩnh viễn). Topic bảo đảm mỗi subscription đủ điều kiện có bản riêng (không phải mọi process đều nhận). Khi một consumer chết ở bất kỳ điểm nào, việc xử lý lại có thể xảy ra hoặc mất message nếu cấu hình không phù hợp. Cần kiểm thử theo fault scenario chứ không suy luận chỉ từ Queue/Topic.

### 7.2. Idempotency mỗi nhóm

- **Command Queue:** lưu `commandId`/business key, trạng thái của job; nếu cùng command được giao lại, worker không tạo tác dụng phụ lần hai.
- **Event Topic:** mỗi nhóm giữ bảng processed-event theo `(consumerGroup, eventId)` hoặc có store tách riêng. Billing xử lý xong không có nghĩa Audit cũng xử lý xong.
- **External side effect:** gửi email, thanh toán, gọi API ngoài có thể không nằm trong cùng transaction với ack; dùng idempotency key của bên nhận, outbox hoặc cách bù trừ.
- **At-most-once / at-least-once / exactly-once:** đây là mục tiêu delivery/processing cần nêu đầy đủ ngữ cảnh. Chữ “exactly-once” ở giao thức không đủ để chứng minh hiệu ứng nghiệp vụ chỉ xảy ra một lần.

### 7.3. Thứ tự xử lý

Nếu yêu cầu “mọi thay đổi của cùng `accountId` theo thứ tự”, hãy mô tả thứ tự thuộc cấp nào: toàn topic, từng queue, một consumer, hay từng business key. Concurrency, delivery retry, message selectors, priority và TTL có thể ảnh hưởng thứ tự quan sát được. Có thể dùng kỹ thuật giữ message theo khóa (ví dụ broker-specific message groups) hoặc kiến trúc phân vùng, nhưng phải kiểm tra khả năng hỗ trợ, tính năng động và hành vi failover của provider. Đừng quảng cáo “Topic mất thứ tự còn Queue luôn FIFO tuyệt đối”.

### 7.4. Lỗi và DLQ độc lập

Trong một Topic có nhiều subscription, Billing có thể thành công trong khi Email thất bại và bị retry. Chính sách redelivery, dead-letter address/queue và số lần retry thường do broker điều khiển, không được Jakarta Messaging chuẩn hóa toàn bộ. Cần giám sát **từng subscription**, đặt giới hạn backlog và alert. Với một Queue, nhóm worker cùng tiêu thụ backlog; một poison message có thể chiếm tài nguyên nếu retry không giới hạn.

### 7.5. Mở rộng nhiều service

Topic làm producer ít cần biết danh sách subscriber, nhưng **vẫn có hợp đồng**: schema, semantics, bảo đảm giao nhận, backward compatibility, ACL và ownership. Thêm một subscriber mới không có nghĩa mọi phiên bản payload cũ sẽ tự tương thích. Khi thêm nghĩa vụ nghiệp vụ mới, xác định **từ thời điểm nào** subscriber phải bắt đầu nhận; nếu phải bắt kịp quá khứ, cần backfill từ nguồn dữ liệu khác hoặc chức năng replay của hạ tầng đã được xác nhận.

## 8. Bài kiểm thử hợp đồng trước khi đưa vào production

| Kiểm thử | Kỳ vọng nếu thiết kế đúng |
| --- | --- |
| Gửi 10 command vào queue với 3 worker | Tổng lượt **hoàn tất logic** là 10 nếu không có lỗi; phân bố cho từng worker không cố định |
| Gửi 10 event vào topic có 3 subscription độc lập đã online | Mỗi subscription nhận 10 bản đủ điều kiện; tổng 30 lần xử lý theo 3 nhóm |
| Tăng Billing từ 1 lên 3 replica dùng **shared durable** | Cả nhóm Billing vẫn có 10 bản logic cho 10 event, không tự nhân thành 30 |
| Đóng toàn bộ consumer non-durable rồi publish | Khi không có subscription tồn tại, message không được tích lũy để nhận lại |
| Tạo durable subscription, đóng consumer, rồi publish và kết nối lại | Subscription có thể nhận backlog hợp lệ, miễn TTL/retention/capacity và cấu hình broker cho phép |
| Publish trước khi tạo durable subscription | Subscriber mới **không tự nhận toàn bộ quá khứ** |
| Consumer chết sau side effect nhưng trước ack | Message có thể được redeliver; idempotency bảo vệ trạng thái nghiệp vụ |
| Một subscription topic bị lỗi, subscription khác ổn định | Bản ở nhóm lỗi có thể retry/DLQ độc lập; nhóm khác vẫn có thể xử lý bản riêng |
| Bật concurrency và kiểm tra cùng business key | Đánh giá thứ tự thực tế, không kết luận FIFO global từ tên destination |
| Message hết TTL, backlog đầy, broker restart | Kiểm tra expiration/retention/persistence theo cấu hình thay vì kỳ vọng vô điều kiện |

Khi kiểm thử, ghi rõ **số message publish**, số lần **delivery attempt**, số **business outcome thành công**, số bản trong **DLQ**, và backlog. Ba số đầu khác nhau khi có retry/redelivery; đừng chỉ đếm số dòng log để kết luận nghiệp vụ đã đúng.

## 9. Các lỗi chọn Queue/Topic thường gặp

1. **Ba nhóm độc lập cùng nghe một Queue:** chỉ một nhóm nhận mỗi message; thay bằng Topic + subscription riêng hoặc fan-out router có hợp đồng.
2. **Mỗi replica một subscription Topic độc lập:** mỗi replica xử lý toàn bộ event; dùng shared subscription cho cùng nhóm nếu muốn chia tải.
3. **Dùng Topic non-durable cho nghiệp vụ không được mất event lúc offline:** tạo durable subscription trước khi publish; kiểm tra retention và cách vận hành.
4. **Cho rằng durable subscriber mới tự nhận được lịch sử:** durable chỉ giữ từ lúc subscription tồn tại, không thay event log.
5. **Đổi `spring.jms.pub-sub-domain` mà quên factory bên nhận:** producer gửi Topic trong khi listener vẫn nghe Queue hoặc ngược lại. Cấu hình tường minh cả hai.
6. **Dùng cùng subscription name giữa hai nhóm nghiệp vụ:** chúng tranh phần của cùng một subscription thay vì nhận hai bản độc lập.
7. **Tin “một message giao một consumer” = exactly-once:** redelivery xảy ra; phải idempotent và kiểm soát transaction boundary.
8. **Tăng concurrency rồi yêu cầu xử lý đúng thứ tự toàn cục:** phải xác định rõ ordering constraint và cơ chế bảo đảm.
9. **Không đặt TTL/retry/DLQ/monitoring:** một poison message hoặc offline subscription có thể làm backlog tăng vô hạn.
10. **Thay đổi schema không thông báo:** subscriber độc lập có lịch triển khai riêng; cần contract versioning và kiểm thử tương thích.
11. **Mở nhiều durable subscription không còn owner:** backlog/quota tích lũy khi service ngừng vĩnh viễn; cần lifecycle tạo/xóa subscription và runbook.
12. **Xem JMS như API tự có broker:** Queue/Topic là abstraction của provider; cần `ConnectionFactory`, client tương thích, destination và broker hoạt động.

## 10. Checklist quyết định để ghi vào review kiến trúc

Trước khi chốt thiết kế, reviewer nên yêu cầu câu trả lời rõ ràng cho tất cả câu sau:

- **Ý nghĩa:** Message là command, event hay thông báo? Điều gì khiến nó được publish?
- **Trách nhiệm:** Có mấy nhóm nghiệp vụ phải hoàn tất xử lý? Số bản **cho từng nhóm** là bao nhiêu?
- **Scale:** Replica là competing consumers trên Queue hay thành viên shared Topic subscription?
- **Downtime:** Có được bỏ lỡ khi tất cả consumer offline? Durable subscription tạo và quản lý bởi ai?
- **Dữ liệu:** Schema version, event/command ID, business key và dữ liệu riêng tư được xử lý thế nào?
- **Độ tin cậy:** Ack/transaction, idempotency, redelivery/retry/DLQ, timeout/expiration cụ thể?
- **Thứ tự:** Có yêu cầu thứ tự theo khóa không? Broker và cấu hình hiện tại hỗ trợ ra sao?
- **Vận hành:** Backlog, tuổi message, consumer health, error rate và subscription cleanup được giám sát không?
- **Lịch sử:** Có cần backfill/replay event đã publish trước khi nhóm đăng ký? Nguồn dữ liệu lịch sử là gì?

Nếu câu trả lời là “một trách nhiệm, nhiều worker thay nhau làm”, lựa chọn Queue thường đúng. Nếu câu trả lời là “nhiều trách nhiệm độc lập đều cần biết cùng sự kiện”, lựa chọn Topic với subscription riêng theo nhóm thường đúng. Hãy hoàn thiện điều kiện durability, shared subscription, idempotency và failure policy **trước** khi coi đó là hợp đồng sẵn sàng triển khai.

## 11. Bài tập tự kiểm tra

1. Một event `OrderCancelled` cần Warehouse và RefundService xử lý, trong đó RefundService chạy 4 replica. Hãy vẽ sơ đồ Topic với **hai subscription** và xác định loại subscription cho RefundService.
2. Một Queue `email.send` có 5 worker. Gửi 100 message, một worker crash sau khi đã gửi email nhưng trước khi ack. Hãy giải thích vì sao tổng số email có thể vượt 100, và nêu giải pháp idempotency.
3. Một dashboard ngừng 30 phút, sau đó cần xem lại mọi telemetry. Hãy giải thích vì sao non-durable topic không đáp ứng, và vì sao chỉ mới bật durable **sau 30 phút** cũng không tự khôi phục quá khứ.
4. Với đoạn Java ở phần 6, hãy thêm một message Queue và một message Topic. Dự đoán **tập** consumer nhận; không dự đoán thứ tự log.
5. Đề xuất hợp đồng cho `PaymentCaptured` gồm danh tính subscription, yêu cầu offline, `eventId`, retention, xử lý trùng, retry và DLQ. Chỉ ra phần nào do code Spring quản lý và phần nào phải cấu hình ở broker.

## Tài liệu tham khảo để tra cứu

- Jakarta Messaging 3.1, **Messaging domains**, queue semantics, topic subscription, durable/shared: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework, **JMS integration**: https://docs.spring.io/spring-framework/reference/integration/jms.html
- Spring Framework, **Annotation-driven listener endpoints**: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework, **JMS namespace/destination types**: https://docs.spring.io/spring-framework/reference/integration/jms/namespace.html
- Spring Boot, **JMS and Artemis auto-configuration**: https://docs.spring.io/spring-boot/reference/messaging/jms.html
- Spring guide, **Messaging with JMS**: https://spring.io/guides/gs/messaging-jms/
