# Service Bus namespace, queue, topic và subscription

Một ứng dụng bán hàng trên Azure nhận đơn đặt hàng qua HTTP. Nếu API phải đồng thời gọi hệ thống thanh toán, trừ kho, gửi email và ghi báo cáo trước khi trả lời, người dùng có thể phải chờ lâu; khi một dịch vụ phụ lỗi, cả yêu cầu đặt hàng cũng có nguy cơ thất bại. Một cách tách các thành phần là gửi **message** vào **Azure Service Bus** để những worker xử lý **bất đồng bộ**.

Nhưng cấu trúc messaging phải đúng ý nghĩa nghiệp vụ. **Queue** phù hợp khi một công việc cần được xử lý bởi một trong nhiều worker cạnh tranh. **Topic** và các **subscription** phù hợp khi một sự kiện cần được phân phối độc lập đến nhiều nhóm nhận. Cả queue và topic đều nằm trong **Service Bus namespace** — ranh giới tài nguyên, cấu hình, quyền và mạng của dịch vụ.

Bài học thuộc chương **Hàng đợi và thông điệp** của module `CLOUD_PROVIDERS_AZURE`. Module giúp bạn khám phá Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu; sau đó triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Ở đây, trọng tâm là thiết kế các **thành phần cốt lõi của Azure Service Bus** và vận hành chúng như một phần của kiến trúc ứng dụng đáng tin cậy.

> Tên tài nguyên, SKU, hạn mức, tính năng mạng, bộ SDK và cú pháp CLI có thể thay đổi theo phiên bản và khu vực. Ví dụ sử dụng dữ liệu giả lập, không có mật khẩu hay connection string thật. Mọi lệnh tạo tài nguyên hoặc gửi message chỉ nên chạy trong subscription/lab đã được cho phép.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích mục đích của **Service Bus namespace**, **queue**, **topic**, **subscription** và **subscription rule/filter**.
2. Vẽ luồng xử lý **point-to-point** và **publish/subscribe** theo đúng ranh giới nhận message.
3. Chọn queue hay topic cho một tình huống nghiệp vụ, phân biệt **competing consumers** với **nhiều subscriber độc lập**.
4. Mô tả vòng đời một message: **send → enqueue → receive → complete/abandon/dead-letter/defer**.
5. Phân biệt **Peek-Lock** với **Receive-and-Delete**, giải thích delivery lại và nhu cầu idempotency.
6. Xác định vai trò của **TTL, dead-letter queue, duplicate detection, sessions, filters** và các giới hạn hỗ trợ theo tier.
7. Thiết kế danh tính và phân quyền bằng **Microsoft Entra ID/managed identity** thay cho việc nhúng SAS connection string khi khả thi.
8. Tạo namespace, queue, topic và subscriptions trong Azure Portal hoặc bằng Azure CLI có kiểm soát.
9. Dùng SDK để gửi/nhận message và quan sát các thông số vận hành.
10. Điều tra sự cố message tồn đọng, gửi vào sai subscription, worker bị lỗi hoặc message chuyển sang dead-letter.
11. Lập phương án retention, giám sát, bảo mật, DR và kiểm soát chi phí cho hệ thống messaging.

## 2. Tại sao cần nhắn tin bất đồng bộ?

Hãy so sánh hai luồng xử lý đơn hàng.

**Xử lý đồng bộ:**

```text
Khách hàng
    |
    v
Orders API
    ├── gọi Payment API ─────── chờ
    ├── gọi Inventory API ───── chờ
    ├── gọi Email API ───────── chờ
    └── trả phản hồi
```

Nếu một dependency chậm hoặc không khả dụng, request từ khách hàng có thể bị timeout. Mọi thành phần cũng bị buộc hoạt động cùng lúc.

**Xử lý bất đồng bộ qua Service Bus:**

```text
Khách hàng
    |
    v
Orders API
    |
    +-- lưu đơn hàng ở hệ thống nguồn
    |
    +-- publish message/event
    |
    +-- trả trạng thái đã tiếp nhận
               |
               v
          Service Bus
               |
       +-------+--------+
       |       |        |
     Billing  Inventory  Notifications
      worker    worker      worker
```

Ưu điểm có thể có:

- API và worker không cần sẵn sàng cùng một thời điểm.
- Message có thể chờ trong hàng đợi khi worker đang bận.
- Worker có thể mở rộng độc lập theo backlog.
- Producer không phải biết địa chỉ cụ thể của mọi consumer.
- Cơ chế settlement và dead-letter giúp xử lý message thất bại có kiểm soát.

Tuy nhiên, bất đồng bộ **không tự bảo đảm nghiệp vụ đã hoàn thành** ngay khi API trả về. Cần phân biệt trạng thái **đơn hàng được tiếp nhận** với **đã thanh toán, đã trừ kho hoặc đã gửi email**. Thiết kế phải quản lý trạng thái cuối cùng, lỗi, retry và đối soát.

## 3. Sơ đồ phân cấp tài nguyên của Azure Service Bus

Một namespace là ranh giới chứa các messaging entities. Trong đó có các queue và topic; mỗi topic có thể có nhiều subscription, và mỗi subscription có thể có rules để lọc message.

```text
Azure subscription (đơn vị quản lý và thanh toán)
└── Resource group: rg-orders-prod
    └── Service Bus namespace: sb-orders-prod
        ├── Queue: charge-command
        │   └── Dead-letter subqueue (DLQ)
        │
        ├── Queue: refunds-command
        │   └── Dead-letter subqueue (DLQ)
        │
        └── Topic: order-events
            ├── Subscription: billing
            │   ├── Rules / filters
            │   └── Dead-letter subqueue
            ├── Subscription: inventory
            │   ├── Rules / filters
            │   └── Dead-letter subqueue
            └── Subscription: audit
                ├── Rules / filters
                └── Dead-letter subqueue
```

**Hai nghĩa khác nhau của “subscription”:**

- **Azure subscription:** ranh giới tài khoản/tài nguyên, thanh toán, quota và Azure RBAC.
- **Service Bus topic subscription:** thực thể nhận bản message phù hợp từ **một topic**, có backlog và chính sách xử lý riêng.

Một Service Bus subscription **không phải** một Azure subscription và cũng không phải Kubernetes subscription hay Event Grid event subscription.

### Các cấp cấu hình

| Cấp | Bạn quản lý gì? | Ví dụ |
|---|---|---|
| Azure subscription/resource group | Quyền tạo tài nguyên, region, policy, ngân sách. | `rg-orders-prod` |
| **Service Bus namespace** | SKU/tier, endpoint, auth, network, cấu hình namespace-level và thống kê tổng. | `sb-orders-prod.servicebus.windows.net` |
| **Queue** | Nơi nhận message point-to-point, TTL, lock, DLQ và chính sách entity. | `charge-command` |
| **Topic** | Điểm producer publish message cho nhiều luồng nhận. | `order-events` |
| **Topic subscription** | Một “luồng nhận” độc lập có backlog, consumer và DLQ riêng. | `inventory` |
| **Rule/filter** | Xác định message nào được đưa vào một subscription. | `eventType = 'OrderPlaced'` |

## 4. Namespace: ranh giới quản trị và kết nối

**Service Bus namespace** có tên DNS endpoint riêng, được tạo trong một region và chọn một pricing tier. Client thường kết nối tới endpoint dạng:

```text
<NAMESPACE_NAME>.servicebus.windows.net
```

Tại namespace, bạn thường quyết định:

1. **Region và tier:** khả năng tính năng, chi phí, độ ổn định hiệu năng.
2. **Ranh giới ứng dụng/môi trường:** Production và Development có nên tách namespace?
3. **Identity và quyền:** ai gửi, ai nhận, ai quản trị?
4. **Kết nối mạng:** public network, IP restrictions/private endpoint khi tier hỗ trợ, DNS và outbound traffic của ứng dụng.
5. **Giám sát và vận hành:** Azure Monitor, diagnostic logs, alert, retention.
6. **Chính sách DR:** ảnh hưởng khi namespace hoặc region không khả dụng.
7. **Ngân sách:** dung lượng message, throughput, số entities và chi phí theo mô hình giá.

### Namespace không phải queue

Tạo một namespace thành công **chưa có nghĩa có queue/topic để gửi message**. Các messaging entities phải được tạo rõ ràng. Một ứng dụng gửi tới `queue_name="charge-command"` nhưng queue đó chưa tồn tại có thể nhận lỗi entity not found dù kết nối namespace hợp lệ.

### Tách namespace theo môi trường

Ví dụ:

```text
sb-orders-dev   → dùng dữ liệu và quyền Development
sb-orders-test  → kiểm thử tích hợp/hiệu năng theo ngân sách
sb-orders-prod  → đơn hàng thật, quyền và cảnh báo chặt hơn
```

Không bắt buộc một namespace cho mỗi microservice. Tách namespace là quyết định về **blast radius, hạn mức, isolation, mạng, quyền và chi phí**. Nhiều queue/topics có thể dùng chung namespace nếu yêu cầu an toàn và vận hành tương thích; nhưng không nên để một nhóm phát triển có quyền xóa mọi queue của Production.

## 5. Chọn tier: Basic, Standard và Premium

Azure Service Bus có những tier khác nhau về tính năng và mô hình tính phí. Hãy chọn tier **trước khi chốt sơ đồ messaging**.

| Tiêu chí | Basic | Standard | Premium |
|---|---|---|---|
| Queue messaging | Có. | Có. | Có. |
| Topic/subscription | **Không hỗ trợ** mô hình topic/subscription của Service Bus. | Có. | Có. |
| Mô hình tài nguyên | Môi trường dùng chung theo tier. | Môi trường dùng chung theo tier. | Tài nguyên chuyên dụng hơn, mô hình capacity Messaging Units. |
| Dự đoán throughput/latency | Phù hợp yêu cầu đơn giản. | Phù hợp nhiều hệ thống ứng dụng. | Thường phù hợp workload quan trọng, cần isolation/throughput dự đoán tốt hơn. |
| Networking, messaging nâng cao, DR | Kiểm tra giới hạn tính năng. | Có giới hạn khác Premium. | Thường có nhiều khả năng enterprise hơn, tùy tính năng hỗ trợ. |
| Hướng sử dụng | Hàng đợi đơn giản, ít yêu cầu. | Queue + publish/subscribe. | Workload quan trọng, throughput lớn hoặc network isolation chặt. |

**Quy tắc:** nếu bài toán cần **topic và nhiều subscriptions**, đừng chọn Basic chỉ vì giá thấp hơn. Ngược lại, một queue đơn giản không đương nhiên cần Premium. Các tính năng như **sessions, duplicate detection, private endpoint, partitioning, large messages** có ràng buộc theo tier/SKU/phiên bản; không suy ra chúng được hỗ trợ chỉ từ việc namespace đã tồn tại.

### Premium không đồng nghĩa vô hạn

Premium mang lại tài nguyên chuyên dụng hơn nhưng vẫn có **giới hạn throughput, entity size, concurrent connections, quy mô namespace và khả năng cấp phát**. Khi tăng Messaging Units hoặc các cấu hình performance khác, cần benchmark thực tế theo payload size, số client, batch và latency; không suy diễn throughput tăng tuyến tính trong mọi workload.

## 6. Queue: mô hình point-to-point

Queue nhận message từ producer và để một trong các consumer xử lý một lần về mặt nghiệp vụ. Nhiều worker có thể **cạnh tranh lấy các message khác nhau** từ cùng queue để tăng throughput.

```text
Orders API / Producer
        |
        v
Queue: charge-command
        |
        +--> Worker A nhận message M1
        +--> Worker B nhận message M2
        +--> Worker C nhận message M3
        |
        +--> DLQ khi message không xử lý được theo chính sách
```

Nếu ba worker cùng nghe `charge-command`, Service Bus **không cố ý gửi cùng một message riêng biệt cho cả ba worker** như một cơ chế broadcast. Một message được nhận để xử lý bởi **một consumer tại một thời điểm có lock hợp lệ**, nhưng vẫn có thể được giao lại khi lock hết hạn hoặc xử lý không được xác nhận.

### Queue phù hợp khi nào?

- Worker xử lý yêu cầu tính toán ảnh theo job ID.
- Hệ thống thực thi yêu cầu thanh toán có thể retry/idempotency.
- Dịch vụ nhận yêu cầu xuất báo cáo, gửi hóa đơn hoặc đồng bộ dữ liệu.
- Nhiều instance worker cùng chia backlog để tăng throughput.

### Queue không nên dùng để làm fan-out

Giả sử ba đội Billing, Inventory và Audit đều phải nhận **từng sự kiện đơn hàng**. Nếu tất cả nghe **cùng một queue**, một message thường chỉ được một trong các nhóm nhận, không bảo đảm ba nhóm đều nhận. Đó là lý do cần **topic với ba subscriptions**.

## 7. Topic: producer publish một lần, nhiều luồng nhận độc lập

Topic là điểm nhận message từ publisher. Các subscription liên kết với topic có thể nhận **bản message phù hợp** theo bộ lọc của từng subscription.

```text
Orders API
    |
    | publish OrderPlaced
    v
Topic: order-events
    |
    +--- Subscription: billing ------> Billing workers
    |       |                             (cạnh tranh trong nhóm)
    |       +--- DLQ
    |
    +--- Subscription: inventory ----> Inventory workers
    |       +--- DLQ
    |
    +--- Subscription: audit --------> Audit workers
            +--- DLQ
```

Đây là mô hình **publish/subscribe (pub/sub)**:

- Publisher không gửi từng bản riêng đến ba worker.
- Topic định tuyến mỗi message tới các subscription thỏa rule.
- Mỗi subscription có **backlog, consumer, retry/settlement và DLQ riêng**.
- Billing chậm không buộc Inventory phải ngừng xử lý những message đã vào subscription của mình.
- Trong **một subscription**, nhiều worker vẫn có thể cạnh tranh nhận message để tăng throughput.

### Topic không tự có lịch sử vô hạn

Khi một subscription **chưa tồn tại lúc message được publish**, subscriber được tạo sau đó không mặc định nhận lại toàn bộ message cũ. Service Bus không phải hệ thống event log có thể replay từ đầu theo offset như một số nền tảng streaming.

Nếu cần **replay lịch sử nhiều tháng**, nên lưu event ở nơi bền vững riêng theo chính sách (ví dụ lưu event archive, database/outbox hoặc event store). Một subscription mới chỉ tham gia nhận những message phù hợp theo cấu hình và thời điểm tồn tại của nó.

### Những thông tin không nên trộn lẫn

Topic là **publish endpoint**; không có một queue chung cho consumer đọc trực tiếp từ topic. Worker nhận từ **subscription**, không gọi `get_topic_receiver` như cách `get_queue_receiver`.

## 8. Subscription: hàng đợi logic riêng cho từng nhóm nhận

Một **topic subscription** nhận các message thỏa rule từ một topic. Nó có nhiều thuộc tính vận hành giống queue: message count, lock duration, TTL, dead-letter handling và khả năng kết nối nhiều worker.

Ví dụ ba subscriptions:

| Subscription | Nhận loại sự kiện | Consumer | Hệ quả khi bị lỗi |
|---|---|---|---|
| `billing` | `OrderPlaced`, `OrderCancelled` | Hệ thống thanh toán/hóa đơn. | Backlog tăng riêng ở billing, có thể sinh DLQ. |
| `inventory` | `OrderPlaced` | Hệ thống quản lý kho. | Inventory backlog riêng, billing vẫn hoạt động. |
| `audit` | Mọi sự kiện đơn hàng cần lưu dấu vết. | Audit worker/archiver. | Cần giám sát retention và bảo đảm archive thực sự được ghi. |

Subscription **không phải** một tài khoản nhận thông báo qua email. Nó là messaging entity với bộ lọc, trạng thái và dữ liệu cần quản lý.

### Subscription lifecycle

- Tạo subscription trước khi bắt đầu publish nếu không muốn bỏ qua sự kiện đầu tiên.
- Kiểm tra filter/rules ngay sau khi tạo.
- Cấu hình receiver và dead-letter handling của riêng subscription.
- Không xóa subscription để “dọn backlog” nếu chưa xác nhận có thể mất các message chờ xử lý.
- Với cấu hình auto-delete-on-idle, đánh giá nguy cơ subscription ít traffic bị xóa sau thời gian không hoạt động.

## 9. Subscription rules và filters

Service Bus cho phép subscription có những **rule** dùng filter để quyết định message được chuyển vào subscription nào. Những kiểu lọc thường gặp gồm:

- **True filter:** nhận mọi message.
- **SQL filter:** biểu thức điều kiện trên system/application properties theo cú pháp được hỗ trợ.
- **Correlation filter:** so khớp thuộc tính cụ thể để định tuyến hiệu quả cho một số kịch bản.
- **SQL rule action:** một số cấu hình hỗ trợ biến đổi properties của bản message được chọn theo giới hạn dịch vụ.

Ví dụ publisher gửi message với application property:

```json
{
  "messageId": "order-1042-event-1",
  "subject": "OrderPlaced",
  "applicationProperties": {
    "eventType": "OrderPlaced",
    "region": "vn-south"
  },
  "body": {
    "orderId": "1042",
    "amount": 250000
  }
}
```

Đây là **minh họa logic các thành phần message**, không phải JSON wire format mà Service Bus bắt buộc; trong SDK, `messageId`, `subject` và `applicationProperties` thường được đặt thành **metadata của message**, không nhất thiết nằm trong body JSON.

Các SQL filter minh họa:

```sql
-- Inventory nhận đơn mới.
eventType = 'OrderPlaced'

-- Nhóm xử lý miền Nam nhận đơn mới tại vùng tương ứng.
eventType = 'OrderPlaced' AND region = 'vn-south'
```

### Cạm bẫy $Default

Khi tạo một topic subscription mới theo thao tác thông thường, có thể tồn tại rule mặc định **`$Default`** với true filter — nghĩa là nhận **tất cả** message.

Nếu sau đó bạn chỉ **thêm** rule `OnlyOrderPlaced` mà **không loại bỏ rule `$Default`**, subscription vẫn có thể nhận mọi message vì các rules được áp dụng theo logic phù hợp với **bất kỳ** rule nào. Khi muốn subscription thực sự chỉ nhận một tập message, hãy xác nhận toàn bộ rule list và bỏ rule mặc định rộng khi có phê duyệt.

### Filter không áp dụng ngược thời gian

Việc sửa rule hôm nay **không tự lọc lại hoặc di chuyển** những message đã tồn tại trong backlog của subscription từ trước. Với thay đổi routing, xác định khoảng chuyển đổi, cách xử lý message cũ và khả năng song song hai phiên bản consumer.

## 10. Chọn queue hay topic: bảng ra quyết định

| Nhu cầu | Hướng chọn | Lý do |
|---|---|---|
| Một yêu cầu xuất báo cáo phải được một worker xử lý. | **Queue** | Competing consumers chia công việc. |
| Mỗi sự kiện tạo đơn phải tới Billing, Inventory và Audit. | **Topic + 3 subscriptions** | Fan-out, mỗi nhóm có backlog riêng. |
| Một sự kiện chỉ đi tới bộ phận ở một vùng được chọn. | **Topic + subscription filters** | Routing theo metadata. |
| Hàng chục workers giống nhau cùng xử lý tác vụ CPU. | **Một queue + nhiều receivers** | Scale throughput, không broadcast. |
| Cần tách message cho từng đối tác nhưng mỗi đối tác phải nhận đầy đủ. | **Topic + subscription cho từng đối tác**, nếu giới hạn/phân quyền phù hợp. | Isolation và filter riêng. |
| Cần replay toàn bộ sự kiện từ ba năm trước. | **Đánh giá event store/streaming/archiving bổ sung.** | Service Bus subscriptions không phải lịch sử vô hạn. |
| Chỉ cần thông báo trạng thái tài nguyên Azure đến subscriber endpoints. | **Đánh giá Event Grid.** | Phân phối sự kiện theo mô hình khác. |
| Cần telemetry streaming lưu lượng rất cao. | **Đánh giá Event Hubs.** | Kiến trúc stream và consumer groups khác queue/topic. |

Service Bus, Storage Queue, Event Grid và Event Hubs đều có thể xử lý message/event nhưng **không hoán đổi ngữ nghĩa**. Chọn theo nhu cầu delivery, retention, filtering, workflow, ordering và throughput; không chỉ theo tên “queue”.

## 11. Vòng đời một message trong queue/subscription

Service Bus hỗ trợ nhiều receive modes. Trong mô hình đáng tin cậy thường dùng **Peek-Lock** để consumer nhận message, xử lý rồi xác nhận.

```text
Producer
   |
   | Send
   v
Active message trong Queue / Topic Subscription
   |
   | Receive với Peek-Lock
   v
Message bị khóa tạm thời cho receiver
   |
   +--- Xử lý OK ------------> Complete ------> Message rời entity
   |
   +--- Lỗi có thể thử lại ---> Abandon -------> Quay lại trạng thái có thể nhận
   |
   +--- Không thể xử lý ------> DeadLetter ----> DLQ
   |
   +--- Cần xử lý về sau -----> Defer ---------> Deferred, lấy theo sequence number
   |
   +--- Lock hết hạn / client chết -----------> Có thể được giao lại
```

### Các thao tác settlement

| Thao tác | Khi nào dùng | Hệ quả |
|---|---|---|
| **Complete** | Nghiệp vụ đã xử lý thành công, sẵn sàng xác nhận. | Message được loại khỏi hàng đợi/subscription. |
| **Abandon** | Lỗi tạm thời, muốn message có thể nhận lại. | Message trở lại trạng thái sẵn sàng theo cơ chế nhận. |
| **DeadLetter** | Message độc hại, sai schema, không thể xử lý hoặc cần cách ly. | Chuyển vào DLQ của queue/subscription. |
| **Defer** | Cần tạm giữ để xử lý theo logic ứng dụng. | Message không được nhận theo đường bình thường; phải lấy theo **sequence number**. |
| **Peek** | Xem message mà không tiêu thụ/settle. | Hữu ích quan sát, không thay thế luồng nhận xử lý. |

**Đừng dùng Defer làm “retry sau 10 phút” mà không có cơ chế quản lý sequence number và thời điểm xử lý.** Message deferred cần được ứng dụng chủ động nhận lại; nếu không, chúng có thể bị bỏ quên.

## 12. Peek-Lock và Receive-and-Delete

### Peek-Lock

Luồng:

1. Receiver lấy một message và có **lock** trong thời hạn cấu hình.
2. Message tạm không được cấp cho receiver khác theo lock hợp lệ.
3. Worker thực hiện logic nghiệp vụ.
4. Worker gọi `Complete` nếu thành công.
5. Nếu worker crash, mất lock hoặc không complete, message có thể xuất hiện lại để xử lý.

Peek-Lock thường thích hợp cho **workload cần độ tin cậy và retry**. Nhưng có thể nhận lại cùng message, vì thế cần **idempotency**.

### Receive-and-Delete

Với mode này, message được coi là tiêu thụ khi broker gửi tới receiver theo cơ chế delivery của mode, không cần một thao tác Complete sau đó. Nếu consumer crash ngay sau khi nhận nhưng trước khi hoàn thành nghiệp vụ, message có thể **mất khỏi queue mà chưa được xử lý thành công**.

Chỉ cân nhắc Receive-and-Delete khi nghiệp vụ chấp nhận nguy cơ mất message hoặc có phương án bù/khôi phục riêng. Nó không phải mặc định an toàn cho thanh toán, xuất hóa đơn hay cập nhật trạng thái quan trọng.

### Lock duration không phải thời gian bảo đảm xử lý xong

Nếu tác vụ mất lâu hơn lock duration, receiver có thể cần **renew lock** theo API/processor được hỗ trợ. Ngay cả khi có auto-renew, kết nối lỗi hoặc thời hạn tối đa có thể khiến lock mất. Khi đó `Complete` có thể thất bại, và message được giao lại cho worker khác.

**Một message hoàn tất nghiệp vụ nhưng complete thất bại** là ví dụ kinh điển dẫn đến xử lý lặp nếu ứng dụng không idempotent.

## 13. Delivery count, retries, TTL và dead-letter queue

Azure Service Bus giúp kiểm soát xử lý lỗi nhưng ứng dụng vẫn phải phân loại lỗi đúng.

### Delivery count và MaxDeliveryCount

Mỗi khi một message được giao lại theo điều kiện của Service Bus, delivery count có thể tăng. Nếu vượt chính sách **MaxDeliveryCount** của entity, Service Bus có thể chuyển message sang **dead-letter subqueue** thay vì thử lại mãi.

Không dựa vào một con số mặc định mà không đọc cấu hình thật; queue/subscription có thể được thiết lập khác nhau. Một lỗi vĩnh viễn như thiếu trường bắt buộc không nên được retry với cùng payload đến khi hết mọi lần thử nếu có thể xác định sớm và dead-letter có chủ đích.

### TTL (time to live)

Message có thời hạn hiệu lực; TTL có thể được đặt trên message hoặc chịu giới hạn của entity theo cơ chế hỗ trợ. Khi hết hạn, message không còn là một công việc hợp lệ để xử lý bình thường. Tùy cấu hình, message hết hạn có thể được **dead-letter on expiration** hoặc bị xử lý hết hạn theo hành vi dịch vụ.

**TTL không phải SLA thực thi.** Đặt TTL một giờ không có nghĩa worker sẽ hoàn thành trong một giờ; nếu backlog quá lớn, message có thể hết hạn mà chưa được xử lý.

### DLQ ở đâu?

- Mỗi **queue** có một **dead-letter subqueue** gắn với queue đó.
- Mỗi **topic subscription** có một **dead-letter subqueue** gắn với subscription đó.
- **Topic itself** không có một DLQ chung thay thế cho toàn bộ subscriptions.

DLQ giúp cách ly message không được xử lý thành công; nhưng **không tự khắc phục** message, không tự replay và cũng không phải một nơi lưu trữ vô thời hạn để bỏ mặc.

## 14. Thiết kế xử lý DLQ có trách nhiệm

Một runbook DLQ tốt có:

1. **Phát hiện:** cảnh báo dead-letter message count tăng.
2. **Phân loại:** sai schema, thiếu dữ liệu, lỗi quyền, thiếu dependency, poison message, vượt delivery count.
3. **Bảo vệ dữ liệu:** không in payload có PII/secrets ra log hoặc ticket không phù hợp.
4. **Sửa nguyên nhân:** code, config, DB schema, permission hoặc hệ thống đích.
5. **Quyết định:** bỏ message có phê duyệt, sửa/chuẩn hóa rồi gửi lại, hoặc xử lý thủ công.
6. **Replay có kiểm soát:** tránh tạo message trùng và tránh gửi lặp lại vào cùng DLQ.
7. **Đối soát:** xác nhận business state sau khi replay.
8. **Đóng sự cố:** ghi số message, nguyên nhân, quyết định và tác động.

Ví dụ một message thiếu `orderId`:

```json
{
  "schemaVersion": 1,
  "eventType": "OrderPlaced",
  "amount": 250000
}
```

Nếu consumer yêu cầu `orderId` để cập nhật đúng đơn hàng, retry nguyên dữ liệu này 50 lần không tự tạo ra orderId. Cần đưa sang DLQ với lý do rõ ràng, không tạo transaction giả.

### Dấu hiệu cần điều tra theo nguyên nhân

| DLQ reason hoặc triệu chứng | Hướng điều tra |
|---|---|
| `MaxDeliveryCountExceeded` | Worker crash, lock lost, lỗi code/dependency lặp. |
| Message hết hạn hoặc bị dead-letter do expiration | TTL quá ngắn, backlog, downtime hoặc không có receiver. |
| Ứng dụng chủ động dead-letter | Validation/schema/business rule hoặc bảo vệ dữ liệu. |
| Subscription có DLQ nhưng queue không có | Lỗi độc lập của subscriber đó; không phải toàn hệ thống. |
| DLQ tăng khi rollout mới | So schema version, worker image, filter, secret và dependency. |

## 15. Idempotency: điều kiện quan trọng của at-least-once delivery

Trong kiến trúc Service Bus dùng Peek-Lock, **at-least-once** là mô hình ứng dụng nên dự liệu: cùng một message có thể được giao lại sau failure hoặc lock timeout.

Ví dụ:

```text
Worker nhận message M:
  1. Ghi hóa đơn vào DB thành công
  2. Worker crash trước Complete
  3. Lock hết hạn
  4. Service Bus giao lại message M
  5. Worker khác nhận M
```

Nếu bước 5 tạo thêm một hóa đơn, đó là lỗi nghiệp vụ. Phải làm handler **idempotent**: xử lý nhiều lần cùng một yêu cầu nhưng chỉ ghi hiệu ứng nghiệp vụ mong muốn một lần.

### Một chiến lược idempotency

- Mỗi message có **MessageId ổn định** gắn với thao tác nghiệp vụ.
- Bảng lưu các message/business operations đã xử lý (inbox) với **unique constraint**.
- Trong cùng database transaction khi phù hợp: kiểm tra ID, ghi nghiệp vụ, ghi marker đã xử lý.
- Khi nhận lại cùng ID, worker phát hiện đã hoàn tất và chỉ Complete message.
- Nếu phát hành message và cập nhật DB, cân nhắc **transactional outbox** để giảm rủi ro dual write.

**Service Bus duplicate detection không thay thế idempotency của consumer.** Nó có thể giúp loại bỏ các lần gửi trùng với MessageId trong cửa sổ cấu hình khi tier/entity hỗ trợ, nhưng không bảo đảm giao dịch nghiệp vụ đúng một lần trong mọi failure scenario.

## 16. Sessions và thứ tự xử lý

Đôi khi thứ tự message quan trọng: đơn hàng cần xử lý theo các bước `Created → Paid → Shipped`. Azure Service Bus **sessions**, khi được hỗ trợ và cấu hình trên entity, cho phép gom message cùng **SessionId** để xử lý có thứ tự trong một session.

Ví dụ:

```text
SessionId = order-1042
  1. OrderCreated
  2. PaymentCaptured
  3. OrderShipped

SessionId = order-1043
  1. OrderCreated
  2. PaymentFailed
```

Một worker giữ **session lock** và xử lý các message trong session theo logic nhận phù hợp. Các session khác nhau vẫn có thể chạy song song.

### Cần lưu ý

- Queue/subscription phải được tạo với cấu hình session thích hợp; không mặc định bật cho mọi entity.
- Producer phải đặt SessionId nhất quán theo khóa nghiệp vụ, ví dụ `orderId`.
- Receiver phải dùng cơ chế **session receiver**.
- Ordering được kỳ vọng **trong phạm vi session**, không áp dụng toàn namespace hoặc toàn bộ topics.
- Sessions không tự giải quyết duplicate side effects, transaction giữa nhiều services hoặc message đến sai thứ tự từ producer.
- Một session có message xử lý rất chậm có thể cản các message sau trong cùng session; thiết kế partitioning key và khả năng xử lý cần hợp lý.

**Nếu không có yêu cầu thứ tự thực sự, đừng bật sessions chỉ để “tăng độ an toàn”**: chúng tăng độ phức tạp và có thể giảm khả năng parallelism theo key.

## 17. Những khả năng khác cần biết ở cấp entity

| Tính năng | Ý nghĩa | Điểm cần thận trọng |
|---|---|---|
| **Scheduled messages** | Đặt thời điểm message được đưa vào luồng nhận theo API được hỗ trợ. | Không phải timer có deadline tuyệt đối với SLA millisecond. |
| **Duplicate detection** | Phát hiện send trùng theo MessageId trong cửa sổ và điều kiện cấu hình. | Không thay thế inbox/idempotency. |
| **Transactions** | Một số thao tác messaging có thể được nhóm trong transaction theo khả năng SDK/tier. | Không mặc định bao trùm database bên ngoài hoặc HTTP APIs. |
| **Auto-forwarding** | Chuyển message từ queue/subscription tới entity đích theo cấu hình hỗ trợ. | Cần quyền, topology và giới hạn forwarding/dead-letter tương ứng. |
| **Auto-delete on idle** | Tự dọn entity sau khoảng không hoạt động. | Có thể mất backlog/định nghĩa consumer nếu dùng cho Production không cẩn thận. |
| **Partitioning** | Phân tán lưu trữ/xử lý trên mô hình được tier hỗ trợ. | Không bảo đảm thứ tự tổng thể; tính năng thay đổi theo tier/SKU. |
| **Message deferral** | Giữ message chờ xử lý theo sequence number. | Cần tracker nhận lại và quản lý lifecycle. |

Một số tính năng có điều kiện kết hợp. Trước khi chọn tier và tạo entity, hãy xác minh **support matrix**, giới hạn kích thước message, số entities, lock duration, TTL và quota hiện hành trong region của namespace.

## 18. Thiết kế contract của message: body và metadata

Producer và consumer cần một **message contract** có phiên bản rõ ràng. Không nên gửi toàn bộ entity database dưới dạng một object không kiểm soát kích thước hoặc chứa thông tin nhạy cảm.

Ví dụ **event body**:

```json
{
  "schemaVersion": 1,
  "eventType": "OrderPlaced",
  "eventId": "evt-1042-001",
  "occurredAtUtc": "2026-11-20T08:30:00Z",
  "orderId": "1042",
  "customerReference": "cust-ref-81",
  "totalAmount": 250000,
  "currency": "VND"
}
```

**Metadata của Service Bus Message** có thể mang:

```text
message_id       = evt-1042-001
subject          = OrderPlaced
correlation_id   = checkout-req-889
content_type     = application/json
application_properties:
  eventType      = OrderPlaced
  schemaVersion  = 1
  region         = vn-south
```

### Nguyên tắc contract

- Có **schema version** và quy tắc tương thích khi thêm/xóa trường.
- Có **event/business ID** ổn định phục vụ correlation và idempotency.
- Dùng UTC timestamp và mô tả ý nghĩa của time.
- Không đưa password, access token, private keys hay dữ liệu nhạy cảm không cần vào body/log.
- Message phải **tự đủ thông tin cần xử lý** hoặc có tham chiếu rõ ràng tới bản dữ liệu nguồn.
- Nếu payload lớn, cân nhắc **claim-check pattern**: lưu object trong Blob Storage và gửi message chứa URI/ID được phân quyền phù hợp, không gửi SAS vĩnh viễn.
- Có chính sách TTL và xử lý khi event đến sau thời điểm còn giá trị.
- Nếu filter dựa vào `eventType`, producer phải đặt **application property** đúng nơi, không chỉ đặt trường trong body JSON.

## 19. Bảo mật: Entra ID, managed identity và Azure RBAC

Để gửi/nhận message, ứng dụng cần **quyền data plane** trên namespace hoặc entity liên quan. Phương án được ưu tiên khi khả thi là **Microsoft Entra ID và managed identity**, thay vì nhúng SAS key/connection string vào container hoặc source code.

Các role thường dùng:

| Role | Quyền chính | Dùng cho |
|---|---|---|
| **Azure Service Bus Data Sender** | Gửi message. | Orders API/producer. |
| **Azure Service Bus Data Receiver** | Nhận message. | Billing/Inventory/Audit workers. |
| **Azure Service Bus Data Owner** | Quyền data plane rộng hơn để quản lý/use messaging entities. | Tác vụ vận hành đặc biệt có kiểm soát, không cấp mặc định. |

Role được gán đúng **scope** mà tình huống cho phép — namespace, queue hoặc topic/subscription phù hợp với mô hình Azure RBAC và SDK. Với nhiều ứng dụng, nên cấp sender quyền gửi tới đúng entity, receiver quyền nhận đúng entity, tránh cấp Data Owner trên mọi namespace.

### Cấp role minh họa

Nếu một managed identity đã tồn tại và bạn đã xác định đúng principal ID/scope, quyền Sender có thể được gán theo quy trình được phê duyệt:

```bash
az role assignment create \
  --assignee-object-id "<PRINCIPAL_ID>" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure Service Bus Data Sender" \
  --scope "<QUEUE_OR_NAMESPACE_RESOURCE_ID>"
```

**Lệnh này thay đổi Azure RBAC** và không nên chạy nếu thiếu quyền và phê duyệt. Việc role assignment tồn tại cũng cần thời gian propagation; kiểm tra mô hình xác thực thực tế của ứng dụng, không vội cấp thêm quyền rộng khi vừa thay đổi.

### SAS policies và connection strings

Service Bus cũng hỗ trợ **Shared Access Signature (SAS)** theo tính năng/cấu hình namespace/entity. Quyền thường phân theo **Send, Listen, Manage**. Với hệ thống mới:

- Ưu tiên identity-based authentication khi SDK/runtime hỗ trợ.
- Nếu bắt buộc dùng SAS, cấp policy quyền tối thiểu, phạm vi hẹp, xoay khóa.
- Không dùng **RootManageSharedAccessKey** của namespace cho mọi ứng dụng.
- Không để connection string trong Git, Kubernetes ConfigMap plaintext, logs hay ticket.
- Khi migration hoàn tất, đánh giá khả năng vô hiệu hóa local/SAS authentication theo khả năng tier và chính sách tổ chức.

**Azure control-plane Contributor** không tự tương đương Azure Service Bus Data Sender/Receiver: RBAC cho tài nguyên và quyền gửi/nhận message phải được đánh giá riêng.

## 20. Network security và private access

Để kết nối Service Bus, runtime cần **DNS resolution, đường mạng, TLS và quyền Service Bus**. Một identity hợp lệ không giúp được nếu firewall/VNet policy chặn kết nối.

Checklist:

1. Namespace cho phép đường kết nối public hoặc private đã được thiết kế?
2. Nếu dùng **Private Endpoint**, tier/region/tính năng hỗ trợ không? Private DNS zone và VNet links đã đúng?
3. Client ở Azure VM/AKS/Container Apps có route đến endpoint không?
4. NSG, Azure Firewall, NAT, UDR và corporate proxy cho phép outbound?
5. SDK sử dụng **AMQP over TLS** (thường TCP 5671) hay **AMQP over WebSockets** (thường TCP 443) theo cấu hình phù hợp?
6. TLS certificate validation và đồng bộ thời gian hệ thống có hợp lệ không?
7. App có quyền Entra RBAC/SAS thích hợp cho entity đích?
8. Retry/backoff có tránh quá tải khi namespace tạm không sẵn sàng?

### Vì sao TCP 443 không tự giải quyết mọi sự cố?

Một số SDK có thể dùng WebSockets transport qua TCP 443 khi mạng chặn 5671, nhưng **phải cấu hình transport theo SDK**. Việc một firewall cho phép TCP 443 không tự biến connection AMQP/TCP thành WebSockets; hostname/private DNS và Service Bus authorization vẫn phải đúng.

**Private Endpoint không tự tăng messaging throughput hoặc cấp quyền gửi/nhận.** Đây là tính năng kiểm soát đường truy cập mạng.

## 21. Quy trình triển khai qua Azure Portal

Ví dụ cần một queue và một topic với ba subscriptions.

### Giai đoạn A: Tạo namespace

1. Đăng nhập [Azure Portal](https://portal.azure.com/), kiểm tra đúng tenant/subscription.
2. Mở **Service Bus** → **Create**.
3. Chọn resource group, namespace name hợp lệ, region và pricing tier.
4. Chọn **Standard hoặc Premium** nếu cần topic/subscriptions.
5. Xem cấu hình network/auth và chính sách tổ chức trước khi tạo.
6. Chờ resource được provision và mở namespace để kiểm tra endpoint.

### Giai đoạn B: Tạo queue

1. Trong namespace, chọn **Queues** → **Create**.
2. Nhập tên `charge-command`.
3. Cấu hình TTL, lock duration, MaxDeliveryCount và các tùy chọn được hỗ trợ theo nhu cầu.
4. Không bật sessions/duplicate detection nếu ứng dụng chưa thiết kế receiver và MessageId/SessionId tương ứng.
5. Tạo và xem lại thông số entity.

### Giai đoạn C: Tạo topic và subscriptions

1. Chọn **Topics** → **Create**, tên `order-events`.
2. Tạo ba subscriptions: `billing`, `inventory`, `audit`.
3. Kiểm tra các rule hiện tại. Nếu muốn lọc, tạo rule đúng rồi xử lý `$Default` khi cần.
4. Cấu hình DLQ, TTL, MaxDeliveryCount/lock và các khả năng của từng subscription.
5. Tạo receivers riêng; mỗi receiver phải kết nối **topic + subscription** phù hợp.
6. Gửi message lab; xác minh mỗi subscription nhận đúng loại event.

### Giai đoạn D: Bảo mật và vận hành

1. Gán role Sender/Receiver tối thiểu cho managed identities.
2. Cấu hình network endpoint/firewall/private DNS theo thiết kế.
3. Thiết lập Azure Monitor metrics, diagnostic logs, alerts và dashboard.
4. Thử retry/failed message trong lab, xác minh DLQ.
5. Đặt owner, ngân sách và quy trình đổi schema/rules.

## 22. Azure CLI: kiểm tra namespace và entities (read-only)

Các lệnh bên dưới đọc cấu hình Azure Resource Manager, **không tạo/xóa message**. Thay giá trị placeholder bằng tài nguyên của tổ chức.

### Xác minh context

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table
```

### Xem namespace

```bash
az servicebus namespace show \
  --name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --query "{Name:name,Location:location,Sku:sku.name,State:provisioningState}" \
  --output json
```

### Danh sách queues và topics

```bash
az servicebus queue list \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output table

az servicebus topic list \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output table
```

### Liệt kê subscriptions của topic

```bash
az servicebus topic subscription list \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --topic-name "order-events" \
  --output table
```

### Xem chi tiết queue/subscription

```bash
az servicebus queue show \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --name "charge-command" \
  --output json

az servicebus topic subscription show \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --topic-name "order-events" \
  --name "billing" \
  --output json
```

Output có thể bao gồm thuộc tính runtime/metadata tùy API/CLI. Trước khi kết luận backlog hoặc DLQ có bao nhiêu message, hãy kiểm tra thời điểm cập nhật số liệu và metrics ở portal/monitor; một số số đếm có thể có độ trễ.

### Kiểm tra subscription rules

```bash
az servicebus topic subscription rule list \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --topic-name "order-events" \
  --subscription-name "billing" \
  --output json
```

Kiểm tra tên `$Default` hoặc rule true filter khi dự kiến lọc. Các flag và cấu trúc response có thể khác theo phiên bản Azure CLI; dùng `az servicebus topic subscription rule list --help` nếu cần.

## 23. Azure CLI: tạo lab resources có kiểm soát

**Các lệnh trong mục này thay đổi tài nguyên và có thể phát sinh phí**. Chỉ chạy trong một resource group lab đã được phê duyệt. Chúng là trình tự tham khảo; tài khoản thực tế phải có quota, RBAC và SKU phù hợp.

### Namespace Standard

```bash
az servicebus namespace create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --name "<UNIQUE_NAMESPACE_NAME>" \
  --location "southeastasia" \
  --sku Standard
```

Tên namespace phải đáp ứng quy tắc và **duy nhất** theo phạm vi DNS của dịch vụ. Region `southeastasia` chỉ là ví dụ; chọn region phù hợp dữ liệu, latency và policy.

### Queue point-to-point

```bash
az servicebus queue create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --name "charge-command"
```

### Topic và ba subscriptions

```bash
az servicebus topic create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --name "order-events"

az servicebus topic subscription create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --topic-name "order-events" \
  --name "billing"

az servicebus topic subscription create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --topic-name "order-events" \
  --name "inventory"

az servicebus topic subscription create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --topic-name "order-events" \
  --name "audit"
```

Sau khi tạo, liệt kê lại subscriptions và rules. Đừng gửi dữ liệu nhạy cảm để thử. Nếu cần filter, hãy tạo và xác minh rule bằng Portal hoặc SDK/CLI được hỗ trợ, đồng thời kiểm tra rule mặc định.

**Dọn lab:** xóa tài nguyên bằng quy trình của nhóm quản trị chỉ sau khi đã xác minh không còn message/đối tượng cần lưu và không có hệ thống khác sử dụng chung namespace. Không dùng lệnh xóa namespace chỉ vì đã hoàn thành một bài tập nếu namespace được dùng chung.

## 24. SDK Python: producer gửi message vào queue

Ví dụ sau dùng **Azure SDK for Python** với **DefaultAzureCredential**; runtime phải đăng nhập bằng danh tính được cấp **Azure Service Bus Data Sender** trên đúng entity/scope.

Cài thư viện trong virtual environment của lab đã được cho phép:

```bash
python -m pip install azure-servicebus azure-identity
```

Script gửi một yêu cầu giả lập:

```python
import json
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

namespace = os.environ["SERVICEBUS_NAMESPACE"]
queue_name = "charge-command"

payload = {
    "schemaVersion": 1,
    "commandType": "ChargeOrder",
    "orderId": "lab-order-1042",
    "amount": 250000,
    "currency": "VND",
}

credential = DefaultAzureCredential()
with ServiceBusClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    credential=credential,
) as client:
    with client.get_queue_sender(queue_name=queue_name) as sender:
        message = ServiceBusMessage(
            json.dumps(payload, ensure_ascii=False),
            message_id="charge-lab-order-1042-v1",
            subject="ChargeOrder",
            content_type="application/json",
            correlation_id="checkout-lab-1042",
            application_properties={"commandType": "ChargeOrder"},
        )
        sender.send_messages(message)
        print("Đã gửi yêu cầu lab vào queue.")
```

Chạy với biến môi trường chỉ chứa **tên namespace**, không phải SAS secret:

```bash
export SERVICEBUS_NAMESPACE="<UNIQUE_NAMESPACE_NAME>"
python send_queue.py
```

`export` là cú pháp shell Unix. Trên Windows PowerShell, cách đặt biến môi trường khác; thay đổi phù hợp shell thật. Script không tạo queue và không tự cấp quyền Entra. Nếu queue chưa tồn tại hoặc principal thiếu Sender permission, thao tác gửi sẽ lỗi.

### Gửi thành công chưa có nghĩa đã thanh toán

`send_messages` hoàn tất cho biết broker đã chấp nhận message theo thao tác SDK, **không có nghĩa Billing worker đã xử lý nghiệp vụ**. API cần ghi trạng thái `Accepted/Pending` và có cơ chế theo dõi kết quả nghiệp vụ.

## 25. SDK Python: receiver với Peek-Lock và Complete

Một worker thường dùng Peek-Lock, xử lý nghiệp vụ rồi Complete.

```python
import json
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusReceiveMode

namespace = os.environ["SERVICEBUS_NAMESPACE"]

def handle_command(body):
    data = json.loads(body)
    order_id = data["orderId"]
    # THAY bằng nghiệp vụ idempotent trong DB/transaction của ứng dụng.
    print(f"Đã kiểm tra yêu cầu đơn lab {order_id}")
    # Không tạo giao dịch thanh toán thật trong ví dụ.

credential = DefaultAzureCredential()
with ServiceBusClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    credential=credential,
) as client:
    with client.get_queue_receiver(
        queue_name="charge-command",
        receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
        max_wait_time=10,
    ) as receiver:
        messages = receiver.receive_messages(
            max_message_count=5,
            max_wait_time=10,
        )
        for message in messages:
            body = b"".join(message.body).decode("utf-8")
            try:
                handle_command(body)
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                # Dữ liệu không hợp lệ: cần xem chính sách DLQ của hệ thống thật.
                receiver.dead_letter_message(
                    message, reason="InvalidCommand",
                    error_description=type(exc).__name__,
                )
            except Exception:
                # Ví dụ đơn giản: cho message cơ hội xử lý lại.
                receiver.abandon_message(message)
                raise
            else:
                receiver.complete_message(message)
```

**Lưu ý quan trọng về ví dụ:**

- Đây là mẫu **minh họa luồng settlement**, chưa phải production-ready processor.
- `ServiceBusReceivedMessage.body` có thể được hiển thị/đọc khác theo loại message và SDK version; ở môi trường thật, kiểm tra API body type và decoding phù hợp.
- Việc Complete có thể thất bại nếu lock mất; worker phải xử lý `MessageLockLost` và idempotency thay vì cho rằng không có retry.
- Cần phân biệt dữ liệu sai vĩnh viễn với lỗi dependency tạm thời.
- Message có thể chứa thông tin nhạy cảm; chỉ log **message ID, correlation ID, error code đã làm sạch**, không dump body.
- Với workload cần throughput lớn, dùng Service Bus processor/SDK pattern phù hợp, concurrency limit, auto-lock renewal và graceful shutdown.

### Một bản mẫu kiểm tra body an toàn hơn

Nếu ứng dụng chuẩn hóa payload về UTF-8 JSON, hãy bọc decode/parse và kiểm tra schema. Một số thư viện định nghĩa body là iterable data sections; tránh giả định mọi message đều là text UTF-8 nếu hệ thống cũng nhận binary payload.

## 26. SDK Python: publish topic và nhận ở subscription

### Publisher

Trong publisher, chọn **topic sender** thay vì queue sender:

```python
import json
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

namespace = os.environ["SERVICEBUS_NAMESPACE"]
event = {
    "schemaVersion": 1,
    "eventType": "OrderPlaced",
    "eventId": "evt-lab-1042-1",
    "orderId": "lab-order-1042",
}

credential = DefaultAzureCredential()
with ServiceBusClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    credential=credential,
) as client:
    with client.get_topic_sender(topic_name="order-events") as sender:
        sender.send_messages(ServiceBusMessage(
            json.dumps(event),
            message_id=event["eventId"],
            subject=event["eventType"],
            content_type="application/json",
            application_properties={"eventType": event["eventType"]},
        ))
        print("Đã publish OrderPlaced tới topic.")
```

### Subscriber

Một subscription được nhận bằng **topic name + subscription name**:

```python
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient

namespace = os.environ["SERVICEBUS_NAMESPACE"]

credential = DefaultAzureCredential()
with ServiceBusClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    credential=credential,
) as client:
    with client.get_subscription_receiver(
        topic_name="order-events",
        subscription_name="inventory",
        max_wait_time=10,
    ) as receiver:
        for message in receiver:
            print(
                "Nhận sự kiện:",
                message.message_id,
                "từ subscription inventory",
            )
            # Đối với production: xử lý có idempotency trước Complete.
            receiver.complete_message(message)
```

Khi thử, cần khởi tạo cả `billing`, `inventory` và `audit` subscriptions **trước khi publish**. Đọc từng subscription riêng để xác nhận event có xuất hiện tương ứng. Khi nhiều receivers cùng nghe `inventory`, mỗi message trong **inventory subscription** thường do một receiver xử lý, không được nhân bản tới tất cả receivers trong nhóm.

## 27. Quan sát và cảnh báo: biết hệ thống đang bị nghẽn ở đâu

Một queue có 10.000 active messages có thể bình thường trong batch peak, hoặc là dấu hiệu outage nếu API kỳ vọng độ trễ vài giây. Metrics phải gắn với **SLO nghiệp vụ**.

| Metric/tín hiệu | Ý nghĩa | Hướng phản ứng |
|---|---|---|
| **Active messages** | Message chờ nhận/xử lý trong queue/subscription theo trạng thái metric. | So tốc độ producer/consumer; kiểm tra receiver health. |
| **Dead-lettered messages** | Message bị cách ly cần điều tra. | Mở runbook DLQ, xem reason và schema. |
| **Incoming messages** | Lưu lượng publish tới namespace/entity theo khả năng metric. | Dùng để so tải vào và nhu cầu scale. |
| **Outgoing messages** | Lưu lượng nhận/đi ra theo cách metric được tính. | Không đồng nghĩa mọi nghiệp vụ đã hoàn thành. |
| **Server errors / user errors** | Lỗi phía dịch vụ hoặc request/authorization/config. | Phân loại theo mã và tình trạng client. |
| **Throttled requests** | Gặp giới hạn capacity/quota hoặc mô hình tier. | Kiểm tra SKU, workload, retry/backoff và throughput. |
| **CPU/memory/namespace utilization** | Tùy tier và metric được cung cấp. | Xác định capacity, đặc biệt Premium Messaging Units. |
| **Age of oldest message** | Tín hiệu backlog có gây trễ vượt SLO hay không. | Có thể phải đo trong ứng dụng/consumer; không mặc định là built-in metric ở mọi tier. |
| **Receiver exceptions và lock lost** | Worker lỗi hoặc xử lý lâu hơn lock. | Xem handler, dependency, concurrency, lock renewal. |

### Ba loại log không thay thế nhau

1. **Application logs/traces:** producer send, receiver handle, business outcome, MessageId, CorrelationId.
2. **Azure Service Bus diagnostics/metrics:** resource health, errors, operations theo diagnostic categories được hỗ trợ.
3. **Azure Activity Log:** thay đổi control plane của namespace/entities, network, RBAC và cấu hình; **không phải lịch sử đầy đủ body mọi message**.

Bật Azure Monitor diagnostic settings tới Log Analytics/Event Hubs/Storage theo chính sách. Tên bảng/field của Log Analytics có thể khác theo chế độ resource-specific tables hoặc `AzureDiagnostics`; không lấy một KQL mẫu từ workspace khác rồi kết luận không có message.

### Cảnh báo tối thiểu

- DLQ count > 0 hoặc tăng bất thường đối với luồng nghiệp vụ quan trọng.
- Backlog hoặc queue length/processing age vượt ngưỡng thời gian cho phép.
- Throttled requests, server errors hoặc unauthorized tăng.
- Producer/consumer không có activity bất thường trong khung giờ phải hoạt động.
- Worker exception/restarts và database dependency lỗi liên tục.
- Premium capacity utilization cao kéo dài nếu metric hỗ trợ.
- Thay đổi namespace network/RBAC/rules ngoài khung bảo trì.

Một message không có consumer vì subscription filter loại bỏ từ đầu sẽ **không xuất hiện** trong backlog để alert; do đó cần cả **end-to-end business monitoring** và thử nghiệm event routing.

## 28. Throughput, scaling và chi phí

### Các yếu tố ảnh hưởng throughput

- Kích thước payload và số message/giây.
- Số producer/consumer connections, concurrency và batch size.
- Thời gian xử lý nghiệp vụ trong worker.
- Prefetch, receive batching, lock duration và auto-renew.
- Sessions, filters, duplicate detection và đặc tính ordering.
- Quota/hạn mức namespace, entity và tier.
- Network latency, AMQP transport, CPU/connection pooling.
- Database hoặc downstream services — nơi thường là nút thắt thật.

**Thêm consumer không chắc tăng throughput** khi downstream database chỉ xử lý được 100 transactions/giây hoặc một session duy nhất giới hạn xử lý tuần tự.

### Ước lượng backlog đơn giản

Giả sử:

- Producer gửi 500 message/phút.
- Tổng consumer xử lý thành công 400 message/phút.
- Ban đầu backlog bằng 0.

Sau 60 phút:

```text
Tăng backlog/phút = 500 - 400 = 100 messages
Backlog sau 60 phút ≈ 100 × 60 = 6.000 messages
```

Nếu producer ngừng và consumer giữ tốc độ 400 message/phút, cần khoảng:

```text
Thời gian xả backlog ≈ 6.000 / 400 = 15 phút
```

Đây là tính toán minh họa, bỏ qua retry, expired messages, batch efficiency, thay đổi throughput và downtime.

### Ước lượng chi phí theo đặc tính tải

| Hạng mục | Cần đo |
|---|---|
| Namespace tier | Basic/Standard theo operations/model hỗ trợ; Premium theo Messaging Units/capacity. |
| Volume message | Sends/receives, operations và số messages thực tế. |
| Storage footprint | Backlog, TTL, size, DLQ và subscriptions fan-out. |
| Network | Private endpoint/VNet/DNS/NAT/firewall và traffic liên quan. |
| Monitoring | Log Analytics ingestion, retention, alerts, metrics. |
| Workload compute | VM/Functions/AKS/Container Apps workers tiêu thụ backlog. |
| Operations | Công sức on-call, DLQ replay, incident, DR exercises. |

**Một topic có ba subscriptions** có thể tạo ra **ba luồng lưu trữ và xử lý** cho những message matching, nên không chỉ đếm một lần producer publish khi tính nhu cầu capacity/backlog. Dùng **Azure Pricing Calculator** với region/tier và số liệu hiện hành; không suy ra giá thật từ ví dụ.

## 29. Troubleshooting: từng loại lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra theo thứ tự |
|---|---|---|
| `MessagingEntityNotFound` | Sai queue/topic/subscription name, namespace hoặc entity chưa tạo. | Context, namespace, entity list, tên chính xác. |
| `Unauthorized` / `AuthorizationFailed` | Managed identity/SAS thiếu quyền hoặc scope sai. | Entra token, Sender/Receiver role, policy, propagation, endpoint. |
| `ServiceBusException: ServiceTimeout` | Network, dịch vụ, throttling hoặc kết nối quá tải. | Region health, SDK retries, AMQP transport, firewall, metrics. |
| Không gửi được khi dùng Basic | Cố dùng topic/subscription hoặc tính năng tier không hỗ trợ. | Namespace SKU và support matrix. |
| Publish thành công nhưng subscriber không nhận | Subscription không tồn tại lúc publish, filter loại bỏ hoặc receiver sai subscription. | Rules (kể cả `$Default`), timeline, entity metadata. |
| Một subscriber backlog tăng | Worker nhóm đó bị lỗi hoặc processing chậm. | Subscription active count, consumer logs, DLQ. |
| Message nhận lại nhiều lần | Lock timeout, Complete thất bại hoặc Abandon/consumer crash. | Delivery count, lock duration, worker latency, idempotency. |
| DLQ tăng liên tục | Poison message, max delivery, TTL hoặc explicit dead-letter. | DLQ reason, schema, dependency và handler. |
| Message hết hạn trước khi xử lý | TTL nhỏ hơn queue wait/backlog. | TTL, ingestion rate, consumer capacity, SLO. |
| Message không đúng thứ tự | Nhiều producers/receivers, không có session model phù hợp. | SessionId, message timeline, handler architecture. |
| Lỗi khi deploy consumer mới | Contract không tương thích hoặc missing metadata. | Schema version, tolerant reader, rollout strategy. |
| Không kết nối namespace Private Endpoint | DNS, route, NSG/firewall hoặc private feature/tier. | Tên FQDN, private IP resolution, outbound port, TLS. |
| Quá nhiều retries làm DB nghẽn | Retry storm, thundering herd, thiếu backoff/jitter. | Concurrency, downstream metrics, retry policy. |
| Client đọc được nhưng Complete thất bại | Lock lost, link detach, receiver reconnect. | Lock renewal, processing duration, SDK error. |

### Phương pháp khoanh vùng

1. **Tài nguyên đúng?** Azure subscription, resource group, namespace, tier, entity/subscription.
2. **Quyền đúng?** Azure RBAC/SAS và scope.
3. **Đường mạng đúng?** DNS, TCP/TLS, firewall, private endpoint.
4. **Message đã được chấp nhận?** Producer logs/operation result và metrics.
5. **Được định tuyến đúng?** Topic filters, default rule và thời điểm tạo subscription.
6. **Receiver đang hoạt động?** App health, consumer group và dependency.
7. **Settlement đúng?** Complete, retry, lock lost, DLQ.
8. **Business side effect đúng?** DB transaction/idempotency, đối soát.
9. **Có thể khôi phục?** Backlog, DLQ, event archive và replay plan.

Đừng thay đổi đồng thời namespace networking, filters và consumer code khi chưa có bằng chứng; làm vậy khó tìm nguyên nhân và có thể gây mất thêm message.

## 30. Kiến trúc đáng tin cậy: transactional outbox và inbox

Service Bus không tự làm giao dịch atomic với database ứng dụng bên ngoài.

### Vấn đề dual write

Giả sử Orders API:

1. Ghi đơn hàng vào database.
2. Publish `OrderPlaced` vào Service Bus.

Nếu bước 1 thành công nhưng bước 2 lỗi, DB có đơn mới nhưng không có event. Nếu đảo thứ tự, event có thể được publish nhưng DB transaction chưa commit.

### Transactional outbox

```text
Orders API
    |
    +-- Một DB transaction:
    |      - INSERT Order
    |      - INSERT OutboxEvent(OrderPlaced)
    |
    v
Outbox dispatcher
    |
    +-- đọc event chưa gửi
    +-- publish Service Bus
    +-- đánh dấu đã gửi
    |
    v
Topic: order-events
    |
    +--> Billing subscription
    +--> Inventory subscription
```

Outbox giảm rủi ro mất event giữa DB commit và publish. Dispatcher vẫn có thể gửi trùng nếu publish thành công nhưng cập nhật trạng thái outbox thất bại, vì vậy cần **idempotent consumers**.

### Inbox ở consumer

Consumer ghi `ProcessedMessageId` cùng với thay đổi nghiệp vụ trong một transaction khi phù hợp. Nếu nhận lại MessageId đó, bỏ qua side effect rồi Complete.

**Outbox + inbox + retry** là một thiết kế đáng tin cậy hơn việc tuyên bố “broker đảm bảo exactly-once business transactions”. Khả năng transaction của Service Bus trong messaging không mặc định mở rộng atomicity sang mọi cơ sở dữ liệu ngoài dịch vụ.

## 31. Quản lý thay đổi topic/subscription và schema

Mỗi lần thêm subscriber hoặc filter mới có thể ảnh hưởng business behavior.

**Checklist trước khi deploy:**

1. Có cần queue hay topic/subscription mới không?
2. Namespace tier/capacity có đủ cho entity và message throughput không?
3. Subscription có được tạo **trước khi publisher bắt đầu phát event**?
4. Rule/filters có được kiểm tra với cả matching và non-matching examples?
5. Có cần xóa `$Default` để tránh nhận tất cả?
6. Có dữ liệu backlog cũ với schema cũ không?
7. Consumer đọc được schema version trước không?
8. DLQ retention, MaxDeliveryCount và TTL phù hợp chưa?
9. Role Sender/Receiver và private networking đã triển khai?
10. Có dashboard/alert riêng cho subscription mới?
11. Có rollback path nếu filter quá rộng/hẹp?
12. Có business owner xác minh event thực sự được xử lý thành công?

### Schema evolution

Ưu tiên thay đổi **backward compatible** khi có thể, ví dụ thêm trường optional, giữ ý nghĩa trường cũ. Với thay đổi phá vỡ tương thích, cân nhắc:

- Event type hoặc schema version mới.
- Song song hai consumer trong giai đoạn chuyển đổi.
- Contract tests cho producers/consumers.
- Cơ chế xử lý message cũ vẫn đang backlog.
- Không xóa subscription cũ trước khi backlog và xử lý kết thúc.

## 32. Runbook sự cố: Orders event không tới Inventory

**Bối cảnh:** Orders API gửi `OrderPlaced` vào topic `order-events`. Billing xử lý được nhưng Inventory không thấy event.

### Pha A — Xác định phạm vi

1. Lấy `eventId` / MessageId và UTC timestamp từ producer log.
2. Xác nhận namespace và topic đích đúng.
3. Kiểm tra publisher báo send accepted hay chỉ log “sắp gửi”.
4. Kiểm tra Billing xử lý được **đúng eventId**, không phải event khác.

### Pha B — Kiểm tra subscription

1. Subscription `inventory` đã tồn tại khi event được publish?
2. Có rule `eventType = 'OrderPlaced'` không?
3. Có `$Default` hoặc rule khác thay đổi routing không?
4. Producer đặt `eventType` vào **application properties** hay chỉ trong JSON body?
5. Subscription có active messages, dead-lettered messages hoặc TTL expiration?
6. Consumer có thật sự kết nối tới `inventory` subscription của topic này?

### Pha C — Kiểm tra receiver

1. Worker đang chạy, dùng identity Data Receiver đúng scope?
2. Có error khi parse schema, cập nhật DB hoặc Complete?
3. Có delivery count cao hoặc message nằm DLQ?
4. Worker đang nhận lại message nhưng business side effect bị rollback?
5. Nếu có nhiều workers, có một instance lỗi hoặc mismatch version?

### Pha D — Khắc phục

- Nếu rule sai: sửa rule có phê duyệt **cho những publish mới**, không giả định replay event đã bị bỏ lọc.
- Nếu message trong backlog: sửa receiver và tiếp tục nhận.
- Nếu DLQ: theo runbook DLQ, xác minh payload, replay idempotent.
- Nếu event chưa từng vào subscription: lấy lại từ nguồn dữ liệu/outbox/event archive rồi publish lại theo quy trình, tránh tạo effect trùng.
- Nếu identity/network lỗi: sửa quyền/route hẹp nhất, không mở rộng toàn namespace vô điều kiện.

### Pha E — Nghiệm thu

- Event thử mới xuất hiện và được xử lý đúng ở Billing/Inventory/Audit theo rule.
- MessageId/correlation ID tra được end-to-end.
- Không tạo side effect trùng.
- Backlog/DLQ ổn định, latency trong SLO.
- Rule và tài liệu contract được cập nhật.
- Những quyền tạm đã thu hồi.

## 33. Bài thực hành: xây mô hình queue và publish/subscribe

**Bối cảnh:** một cửa hàng trực tuyến muốn tách xử lý thanh toán dạng command và phân phối sự kiện tạo đơn.

Yêu cầu:

| Thành phần | Tên minh họa |
|---|---|
| Resource group | `rg-messaging-lab` |
| Service Bus namespace | `sb-shop-lab-unique` |
| Namespace tier | Standard |
| Queue xử lý công việc | `charge-command` |
| Topic sự kiện | `order-events` |
| Subscription thanh toán | `billing` |
| Subscription kho | `inventory` |
| Subscription kiểm toán | `audit` |
| Event type | `OrderPlaced`, `OrderCancelled` |
| Quyền producer | Azure Service Bus Data Sender |
| Quyền consumer | Azure Service Bus Data Receiver |
| Điều kiện lab | Không dùng dữ liệu thật, không in secret |

### Nhiệm vụ

1. Vẽ sơ đồ namespace, queue, topic, ba subscriptions và DLQs.
2. Giải thích vì sao `charge-command` là queue, còn `order-events` là topic.
3. So sánh ý nghĩa một queue có ba workers với một topic có ba subscriptions.
4. Chọn tier phù hợp và lý do không dùng Basic.
5. Tạo namespace/queue/topic/subscriptions trong lab với Portal hoặc CLI đã được phê duyệt.
6. Kiểm tra rule `$Default` của từng subscription.
7. Thiết kế filter để `inventory` chỉ nhận `OrderPlaced` và `audit` nhận mọi event.
8. Gửi một command giả lập vào queue, dùng hai worker để kiểm tra competing consumers.
9. Publish `OrderPlaced` vào topic, đọc lần lượt từ Billing/Inventory/Audit.
10. Publish `OrderCancelled` và dự đoán subscription nào nên nhận sau khi cấu hình filter.
11. Tạo một message lab sai schema, quan sát failure settlement/DLQ theo policy.
12. Mô tả cách xử lý lại message bị lock timeout mà không tính hai lần phí thanh toán.
13. Thiết lập ít nhất hai alerts cho backlog/DLQ.
14. Ghi lại ba lỗi kiến trúc có thể xảy ra nếu xóa subscription hoặc đổi filter khi Production đang chạy.
15. Xác minh dọn lab theo quyền/retention và ngân sách được phê duyệt.

### Đáp án định hướng

**Queue:** `charge-command` lưu các yêu cầu xử lý một lần về mặt nghiệp vụ, nhiều worker cạnh tranh nhận, phải dùng idempotency theo orderId/MessageId để tránh tạo side effect lặp.

**Topic:** `order-events` phát một event tới nhiều nhóm nghiệp vụ. Mỗi subscription lưu backlog độc lập, nên Billing bị chậm không làm Inventory phải xử lý cùng backlog của Billing.

**Filters:** Inventory nên có rule chỉ nhận `OrderPlaced`; nếu vẫn còn `$Default` true filter thì rule này không có tác dụng hạn chế như kỳ vọng. Audit có thể giữ rule nhận tất cả. Billing có thể nhận hai loại event tùy business contract.

**Lỗi schema:** message thiếu `orderId` phải được cách ly và điều tra; không tự tạo orderId hoặc retry vô hạn.

**Nghiệm thu:** chứng minh một command vào queue có một worker xử lý thành công; một event vào topic tạo bản phù hợp ở mỗi subscription; message sai vào DLQ theo cơ chế đã kiểm thử; consumers có quyền hẹp và logs không lộ dữ liệu nhạy cảm.

## 34. Câu hỏi tự kiểm tra kiến thức

**Câu 1.** Điểm khác nhau cơ bản giữa namespace, queue và topic là gì?

**Đáp án:** Namespace là ranh giới tài nguyên/cấu hình và endpoint; queue lưu công việc point-to-point; topic nhận publish và phân phối tới các subscriptions.

**Câu 2.** Service Bus topic subscription có phải Azure subscription dùng cho billing không?

**Đáp án:** Không. Topic subscription là entity nhận message từ một topic. Azure subscription là ranh giới tài khoản, tài nguyên và thanh toán.

**Câu 3.** Vì sao dùng một queue với ba workers không thay thế được topic với ba subscriptions?

**Đáp án:** Ba workers trên queue là competing consumers; một message thường được một worker xử lý. Topic có thể chuyển bản phù hợp tới mỗi subscription độc lập.

**Câu 4.** Tier Basic có dùng để tạo topic và subscriptions được không?

**Đáp án:** Không. Khi cần Service Bus publish/subscribe theo topic, chọn tier có hỗ trợ như Standard hoặc Premium.

**Câu 5.** Publisher đã gửi message từ hôm trước, hôm nay mới tạo subscription. Subscription có mặc định nhận hết message cũ không?

**Đáp án:** Không. Service Bus không tự replay lịch sử trước khi subscription tồn tại.

**Câu 6.** Khi thêm SQL filter vào subscription nhưng vẫn để `$Default` true filter, có chắc chỉ nhận message khớp SQL filter không?

**Đáp án:** Không. Rule mặc định có thể vẫn khiến subscription nhận mọi message; phải đánh giá toàn bộ rules.

**Câu 7.** Queue nhận message với Peek-Lock rồi worker crash trước Complete. Có thể xảy ra điều gì?

**Đáp án:** Sau khi lock hết hiệu lực, message có thể được giao lại, vì vậy handler cần idempotent.

**Câu 8.** Receive-and-Delete có nguy cơ gì khi worker chết sau khi nhận?

**Đáp án:** Message có thể đã bị coi là tiêu thụ trong khi nghiệp vụ chưa hoàn thành, gây mất công việc.

**Câu 9.** Dead-letter queue là một queue riêng trên topic dùng chung cho tất cả subscriptions đúng không?

**Đáp án:** Không. Queue hoặc từng subscription có dead-letter subqueue riêng.

**Câu 10.** TTL một giờ có bảo đảm message được xử lý thành công trong một giờ không?

**Đáp án:** Không. TTL quy định thời hạn hiệu lực, không phải SLA xử lý. Backlog có thể khiến message hết hạn trước khi receiver thực thi.

**Câu 11.** Duplicate detection có bảo đảm database không ghi hóa đơn hai lần không?

**Đáp án:** Không. Duplicate detection có phạm vi/cửa sổ điều kiện; consumer vẫn cần idempotency và transaction thích hợp.

**Câu 12.** Khi nào nên dùng SessionId?

**Đáp án:** Khi message thuộc cùng khóa nghiệp vụ cần xử lý có thứ tự, ví dụ theo orderId, và sender/receiver/entity đều được thiết kế cho sessions.

**Câu 13.** Sender có role Azure Service Bus Data Sender có tự nhận được message không?

**Đáp án:** Không mặc định. Quyền gửi và nhận được phân biệt, cần role data plane thích hợp.

**Câu 14.** Azure Service Bus Data Receiver có đồng nghĩa được phép tạo/xóa toàn bộ namespace không?

**Đáp án:** Không. Quản lý tài nguyên Azure control plane là một phạm vi quyền khác.

**Câu 15.** Khi dùng Private Endpoint, có thể bỏ Azure RBAC/SAS không?

**Đáp án:** Không. Private Endpoint giới hạn đường mạng; Service Bus vẫn cần xác thực/ủy quyền.

**Câu 16.** Một topic message không xuất hiện ở Inventory nhưng có ở Billing. Nên kiểm tra gì?

**Đáp án:** Subscription Inventory có tồn tại lúc publish, rules/filters, `$Default`, application properties, TTL, DLQ và trạng thái receiver.

**Câu 17.** Vì sao không nên gửi access token hoặc full customer records vào message body nếu không cần?

**Đáp án:** Message có thể tồn tại trong backlog, retries, DLQ và logs; dữ liệu không cần thiết tăng bề mặt rò rỉ và chi phí lưu trữ.

**Câu 18.** `send_messages` trả thành công có phải đơn hàng đã thanh toán xong không?

**Đáp án:** Không. Nó chỉ cho biết broker chấp nhận thao tác gửi; kết quả nghiệp vụ cần được theo dõi riêng.

**Câu 19.** Outbox pattern giảm rủi ro nào?

**Đáp án:** Giảm rủi ro DB commit thành công nhưng publish event thất bại hoặc ngược lại; thường dùng một DB transaction ghi nghiệp vụ và outbox record, dispatcher gửi sau.

**Câu 20.** Backlog tăng đều dù đã thêm workers. Có thể do đâu?

**Đáp án:** Downstream DB nghẽn, consumer xử lý chậm, sessions giới hạn song song, lock failures, quota/throttling hoặc network issues. Cần đo hiệu suất và bottleneck thật.

**Tóm lại:** Azure Service Bus **namespace** là ranh giới quản trị và kết nối; **queue** phân phối công việc cho những consumer cạnh tranh; **topic** phát message tới các **subscriptions** độc lập, mỗi subscription có rule, backlog và DLQ riêng. Hệ thống đáng tin cậy không chỉ gửi message thành công mà phải **định tuyến đúng, phân quyền đúng, xử lý lặp an toàn, giám sát backlog và chứng minh nghiệp vụ cuối cùng hoàn tất**.
