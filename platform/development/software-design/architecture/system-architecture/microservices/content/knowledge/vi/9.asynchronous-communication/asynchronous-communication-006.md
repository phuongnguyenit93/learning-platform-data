# Xác nhận, gửi lại và quản lý vị trí đọc

## 1. Mục tiêu của cơ chế xác nhận và vị trí đọc trong giao tiếp bất đồng bộ

Trong kiến trúc Microservices, các dịch vụ có thể trao đổi thông điệp qua message broker hoặc event log thay vì gọi HTTP đồng bộ. Ví dụ, Order Service phát **OrderPlaced**, Inventory Service xử lý giữ hàng, Payment Service nhận **PaymentRequested**, rồi các hệ thống khác tạo bản chiếu để đọc hoặc gửi thông báo. Cơ chế này giảm sự phụ thuộc về thời điểm hoạt động giữa producer và consumer, nhưng làm xuất hiện câu hỏi quan trọng:

**Khi consumer nhận được một thông điệp, làm sao biết thông điệp đã được xử lý an toàn và ở đâu phải tiếp tục đọc sau một lần lỗi?**

Ba khái niệm phải được phân biệt:

- **Xác nhận (acknowledgment, ACK):** tín hiệu consumer đã hoàn thành nghĩa vụ được quy định đối với một lần nhận thông điệp, để broker hoặc hệ thống điều phối biết thông điệp có thể được coi là đã xử lý tại một giai đoạn.
- **Gửi lại (redelivery/retry):** thông điệp chưa được xác nhận, chưa thể kết luận đã xử lý hoặc cần xử lý lại được chuyển đến consumer một lần nữa.
- **Vị trí đọc (offset, cursor, checkpoint):** thông tin thể hiện phần log/stream đã được consumer xử lý tới đâu hoặc sẽ tiếp tục từ đâu sau khởi động lại.

Các cơ chế có cách thể hiện khác nhau tùy loại broker. RabbitMQ sử dụng ACK/NACK cho lần giao trên channel; hệ thống queue có visibility timeout có thể yêu cầu xóa thông điệp sau xử lý; Kafka chủ yếu lưu **committed offset** cho consumer group, không cung cấp cơ chế per-message ACK theo kiểu queue truyền thống.

Điểm chung không phải hình thức API, mà là cam kết vận hành:

> **Không đánh dấu công việc là hoàn thành trước khi hiệu ứng nghiệp vụ cần thiết đã được lưu bền vững; khi chưa xác định được kết quả, phải có cách thử lại hoặc đối soát mà không làm lặp side effect.**

Trong hệ thống phân tán, producer, broker và consumer có thể gặp lỗi độc lập. Một ACK hoặc offset commit chỉ chứng minh một mốc trong giao thức cụ thể; nó **không tự chứng minh toàn bộ quy trình nghiệp vụ liên dịch vụ đã thành công**.

### 1.1. Bối cảnh ví dụ xuyên suốt

Giả sử Order Service ghi nhận một đơn hàng và phát sự kiện:

~~~json
{
  "eventId": "evt-order-1001-placed",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T10:00:00Z",
  "orderId": "ORD-1001",
  "customerId": "CUS-001",
  "items": [
    { "sku": "SKU-01", "quantity": 2 }
  ]
}
~~~

Inventory Consumer nhận sự kiện để tạo một yêu cầu giữ hàng tương ứng. Thông điệp có thể được giao một lần, nhiều lần, hoặc đến trễ tùy cấu hình và tình huống lỗi. Nếu consumer đã tạo reservation thành công nhưng crash trước khi xác nhận với broker, broker có thể giao **OrderPlaced** lần nữa. Hành vi đúng là phát hiện reservation đã tạo cho cùng ý định và trả về/truy xuất cùng kết quả nghiệp vụ, không giữ thêm hai sản phẩm lần thứ hai.

Chính vì vậy, ACK, retry và offset phải được thiết kế cùng **idempotency, giao dịch dữ liệu, thứ tự xử lý và cơ chế phục hồi**.

## 2. Vòng đời một thông điệp từ phát đến hoàn tất

Một luồng bất đồng bộ điển hình:

~~~text
Producer
   |
   | publish event / command
   v
Message broker / durable log
   |
   | deliver / poll
   v
Consumer
   |
   +--> validate schema, identity, business conditions
   |
   +--> process: ghi dữ liệu hoặc phát lệnh/sự kiện tiếp
   |
   +--> lưu kết quả bền vững
   |
   +--> ACK / delete message / commit offset
   |
   v
Công việc đã được ghi nhận là hoàn tất ở phía consumer
~~~

Có thể phát sinh lỗi ở **mọi đoạn**, và hành vi phục hồi sẽ khác nhau.

| Điểm lỗi | Điều có thể đã xảy ra | Điều consumer cần dự liệu |
| --- | --- | --- |
| Trước khi producer gửi | Chưa chắc broker có message | Producer cần chiến lược retry/outbox |
| Broker nhận nhưng ACK về producer bị mất | Message có thể đã được ghi dù producer thấy timeout | Producer publish lại có thể tạo message trùng |
| Broker giao nhưng consumer crash trước xử lý | Chưa có side effect | Message có thể được giao lại |
| Consumer lưu dữ liệu xong, chưa ACK | Side effect có thể đã hoàn thành | Redelivery phải không làm lặp nghiệp vụ |
| ACK được gửi nhưng consumer không thấy kết quả | Không biết broker đã ghi ACK hay chưa | Cần chịu được việc message còn được giao lại |
| Offset commit trước khi dữ liệu được lưu | Broker nghĩ đã xong nhưng nghiệp vụ chưa thực hiện | Có nguy cơ mất xử lý; cần tránh |
| Consumer xử lý quá chậm | Lease hết hạn hoặc rebalance | Có thể có hai lần xử lý chồng lấn nếu không kiểm soát |

Một quá trình xử lý có thể thành công ở consumer nhưng thất bại ở bước gửi ACK. Vì vậy **ACK không được dùng như khóa định danh duy nhất của hiệu ứng nghiệp vụ**.

### 2.1. Ba loại xác nhận thường gặp

Có thể tồn tại nhiều mốc khác nhau trong cùng pipeline:

1. **Producer acknowledgment:** broker xác nhận đã nhận/ghi bản tin theo mức đảm bảo cấu hình.
2. **Consumer acknowledgment:** consumer báo đã hoàn thành việc nhận/xử lý message theo giao thức của broker.
3. **Business acknowledgment/result:** nghiệp vụ đã thực sự đạt kết quả, ví dụ đơn đã được giữ hàng, thanh toán hoàn tất hoặc giao vận chấp nhận.

Đây là ba khái niệm riêng. Producer được broker ACK không có nghĩa consumer đã xử lý. Consumer đã ACK không chứng minh bên thanh toán thực sự chuyển tiền, nếu consumer chỉ đưa yêu cầu sang một hệ thống khác.

## 3. Semantics của việc giao thông điệp

Các hệ thống thường mô tả delivery bằng ba mô hình: at-most-once, at-least-once và exactly-once. Chúng là **cam kết về phạm vi giao/ghi/xử lý được định nghĩa**, cần đọc cùng giới hạn broker, client library và side effect.

### 3.1. At-most-once

Mỗi message có thể được giao **không quá một lần** trong phạm vi bảo đảm. Nếu consumer mất kết nối hoặc lỗi sau khi nhận, message có thể mất cơ hội được xử lý.

~~~text
Broker giao message
      |
      v
Đánh dấu đã tiêu thụ / tiến offset
      |
      v
Xử lý nghiệp vụ
      |
      +--- crash ---> message không được gửi lại
~~~

At-most-once thường chỉ phù hợp nếu việc mất một số bản tin là chấp nhận được hoặc có nguồn dữ liệu khác có thể xây dựng lại, chẳng hạn một số telemetry không quan trọng. Không nên dùng mặc định cho yêu cầu thu tiền, giữ tồn kho hoặc cập nhật đơn hàng quan trọng.

### 3.2. At-least-once

Broker/consumer cố đảm bảo message được xử lý **ít nhất một lần**, miễn là các giả định về durability, retention và phục hồi được đáp ứng. Đổi lại, **message có thể được xử lý nhiều lần**.

~~~text
Nhận -> xử lý -> lưu bền -> ACK/commit
                    |
                    +--- crash trước ACK
                           |
                           v
                      Nhận lại message
~~~

Đây là cấu hình rất phổ biến vì cho phép phục hồi sau lỗi. Consumer phải bảo đảm tác động nghiệp vụ idempotent hoặc được khử trùng lặp.

### 3.3. Exactly-once và giới hạn thực tế

“Exactly-once” không nên hiểu là **bất cứ side effect nào trên thế giới cũng xảy ra đúng một lần**, bất kể lỗi. Một nền tảng có thể cung cấp exactly-once processing cho việc đọc/biến đổi/ghi **bên trong một phạm vi transaction hoặc log cụ thể**.

Ví dụ Kafka hỗ trợ transactional producer và xử lý gắn offset với kết quả ghi vào các Kafka topic khác, khi sử dụng đúng cấu hình producer/consumer và transaction. Điều đó **không tự tạo transaction nguyên tử với một database bên ngoài, HTTP call hay cổng thanh toán**. Nếu consumer gọi Payment Provider thành công rồi crash trước commit offset, replay có thể gọi lại provider; cần idempotency key, tra cứu trạng thái và reconciliation ở phía nghiệp vụ.

Cách diễn đạt thực dụng:

- **Delivery semantics:** message được giao lại như thế nào?
- **Processing semantics:** consumer nhận biết đã xử lý cùng sự kiện chưa?
- **Business effect semantics:** kết quả trên hệ thống đích có thể bị lặp không?
- **End-to-end guarantee:** phạm vi nào cùng một transaction hoặc cùng cơ chế khôi phục?

Thiết kế phải nêu rõ các phạm vi này, không chỉ ghi nhãn “exactly once”.

## 4. ACK và NACK: bản chất và thời điểm phát

**ACK** là tín hiệu hoàn thành một lần giao theo quy định broker. **NACK** hoặc reject thường là tín hiệu consumer không thể chấp nhận lần giao đó; broker có thể đưa message về queue, chuyển dead-letter hoặc thực hiện chính sách khác.

### 4.1. Automatic ACK và manual ACK

Với **auto ACK**, broker/client có thể đánh dấu thông điệp là được nhận mà không chờ xử lý nghiệp vụ hoàn tất. Cách này giảm thao tác quản lý nhưng có thể làm mất message khi consumer chết giữa lúc xử lý.

Với **manual ACK**, consumer chủ động xác nhận sau khi hoàn tất bước cần bảo đảm bền vững:

~~~text
1. Receive message
2. Kiểm tra schema và tính hợp lệ
3. Bắt đầu transaction nghiệp vụ
4. Ghi kết quả và dấu đã xử lý vào DB
5. Commit transaction
6. ACK với broker
~~~

Thứ tự **commit dữ liệu trước ACK** giúp tránh trường hợp broker bỏ message dù DB chưa lưu. Nhưng vẫn còn cửa sổ “DB đã commit, ACK chưa tới broker”; khi redelivery, consumer phải nhận ra sự kiện đã được áp dụng.

### 4.2. ACK không thay thế idempotency

Ví dụ consumer cập nhật:

~~~sql
UPDATE inventory
SET available = available - 2
WHERE sku = 'SKU-01';
~~~

Nếu cùng message tới hai lần và consumer chạy câu lệnh hai lần, tồn kho sẽ bị trừ hai lần. Chỉ gọi ACK sau khi commit **không giải quyết được tình huống này**.

Một cách an toàn hơn là dùng **business reservation ID** cùng ràng buộc duy nhất và transaction:

~~~text
Transaction:
  - Kiểm tra reservationId / eventId đã xử lý chưa
  - Nếu đã xử lý: trả kết quả cũ, không trừ tồn lần nữa
  - Nếu chưa: kiểm tra khả dụng, cập nhật tồn,
             ghi reservation và processed-event marker
Commit
ACK message
~~~

Ràng buộc duy nhất của database hoặc cơ chế ghi có điều kiện cần bảo vệ trường hợp hai consumer xử lý trùng **đồng thời**. Việc chỉ kiểm tra “đã có chưa?” bằng một truy vấn riêng rồi mới ghi, không có transaction/constraint, vẫn có race condition.

### 4.3. NACK, reject và requeue

Consumer có thể từ chối message khi:

- Phụ thuộc tạm thời không sẵn sàng: lỗi mạng, DB timeout, service downstream quá tải.
- Message sai cấu trúc hoặc version không hỗ trợ.
- Dữ liệu nghiệp vụ vi phạm quy tắc không thể sửa bằng retry.
- Không thể xác định kết quả xử lý do phản hồi bị mất.

Không nên **NACK rồi requeue ngay lập tức vô hạn** cho mọi lỗi. Một poison message có thể bị giao liên tục, làm chiếm CPU, giữ prefetch slot và gây nghẽn cả queue.

Chính sách thường gồm: phân loại lỗi, retry có giới hạn và backoff, trì hoãn bằng queue/timer phù hợp, chuyển DLQ khi cần, ghi lại nguyên nhân và có quy trình xử lý/replay. Quyết định NACK, ACK sau khi lưu thất bại, hay chuyển DLQ phụ thuộc semantics của broker và thiết kế hệ thống.

### 4.4. ACK một message hay ACK hàng loạt

Một số broker hỗ trợ ACK cho một message; một số cơ chế cho phép xác nhận hàng loạt/commit cả vị trí cao nhất. Khi dùng batch, phải biết **những message nào đã thực sự hoàn tất**.

Nếu đã xử lý thành công message số 10 và 12 nhưng message số 11 thất bại, không được commit một checkpoint bao phủ cả 11 mà chưa có chiến lược xử lý lỗi tương ứng. Việc ACK “đến vị trí cao nhất” có thể ngầm đánh dấu các message trước đã hoàn tất, tùy broker.

Cần lưu ý rằng **cú pháp ACK không giống nhau giữa RabbitMQ, Kafka, SQS hoặc các hệ thống stream khác**.

## 5. Vị trí đọc: offset, cursor và checkpoint

Trong một message log có thứ tự, ví dụ Kafka partition, mỗi record có **offset** để consumer biết mình đang đọc đâu. Offset không phải định danh nghiệp vụ, timestamp hoặc eventId.

### 5.1. Các khái niệm cần phân biệt

- **Current position:** vị trí consumer hiện sẽ đọc/poll tiếp trong phiên làm việc.
- **Last processed offset:** record cuối đã hoàn tất xử lý theo định nghĩa của ứng dụng.
- **Committed offset/checkpoint:** vị trí đã được ghi bền vững để nhóm consumer có thể khôi phục sau restart/rebalance.
- **High watermark / log end:** mốc broker cho biết dữ liệu log hiện có theo cơ chế của nó.
- **Consumer lag:** khoảng cách giữa dữ liệu có thể đọc và vị trí đã đọc/commit, tùy cách đo của công cụ.

Trong Kafka, **committed offset** thông thường là **offset của record tiếp theo sẽ được đọc** sau khi khôi phục, không phải offset record vừa xử lý. Nếu xử lý an toàn các record offset **40, 41 và 42**, consumer có thể commit **43** cho partition đó.

~~~text
Partition 0:
... [40] [41] [42] [43] [44] [45] ...
             ^   ^    ^
             đã xử lý tới 42

Checkpoint sau khi 42 hoàn tất: offset = 43
Khởi động lại từ 43
~~~

Việc commit sai thành 42 có thể khiến 42 được đọc lại; commit sai thành 44 có thể bỏ qua 43 nếu nó chưa được xử lý. Trong cơ chế at-least-once, đọc lại một record đã xử lý thường an toàn hơn bỏ mất record chưa xử lý, **miễn là có idempotency**.

### 5.2. Offset không phải event ID

Một event có thể có **eventId = evt-001** và xuất hiện tại offset 42 trong một partition. Nếu dữ liệu được replay, đổi topic, republish hoặc chuyển vào DLQ, offset có thể khác, trong khi business eventId vẫn giữ cùng ý nghĩa.

Dùng:

- **Offset/cursor** để xác định vị trí trong log/stream.
- **Event ID** để nhận diện một sự kiện hoặc ý định nghiệp vụ đã được xử lý.
- **Aggregate ID/key** để gom các event liên quan cùng một đối tượng và có thể giữ thứ tự trong partition.
- **Correlation/causation ID** để truy vết luồng công việc qua nhiều dịch vụ.

Không dùng offset làm khóa idempotency toàn hệ thống vì offset chỉ có nghĩa trong phạm vi log/partition tương ứng.

### 5.3. Checkpoint thuộc ai?

Với consumer group, checkpoint thường thuộc **group + topic + partition** hoặc cơ chế tương tự. Hai consumer group khác nhau có thể cùng đọc log với tiến độ riêng. Trong một group, mỗi partition có một owner đang được điều phối tại một thời điểm, nhưng ownership có thể chuyển khi rebalance.

Ví dụ:

~~~text
Topic order-events
  Partition 0 -> Group inventory-projector: next=140
  Partition 1 -> Group inventory-projector: next=99

  Partition 0 -> Group analytics: next=500
  Partition 1 -> Group analytics: next=480
~~~

Dù cùng topic, Inventory và Analytics có thể xử lý tới các mốc khác nhau vì mục đích và yêu cầu riêng. Không nên dùng cùng group ID khi hai năng lực cần **mỗi bên đều nhận mọi event**; nếu dùng chung group, chúng có thể chia partition cho nhau và mỗi bên không thấy toàn bộ sự kiện cần thiết.

### 5.4. Vị trí đọc không nhất thiết đồng nghĩa kết quả đã lưu

Một consumer có thể poll trước nhiều message, xử lý một số nhưng chưa commit kết quả, rồi crash. Current position chỉ là nơi client đã đưa iterator tới; nó không chứng minh side effect đã xong. Thiết kế checkpoint phải gắn với thời điểm xử lý thành công.

## 6. Kafka: poll, commit offset và rebalance

Kafka sử dụng log theo topic/partition. Consumer group phối hợp phân chia partition, và mỗi group có committed offsets. Kafka không yêu cầu consumer gửi ACK riêng cho từng record theo ngữ nghĩa queue kiểu RabbitMQ.

### 6.1. Auto commit

Khi bật tự động commit, client định kỳ commit vị trí đã poll theo cơ chế của client. Nếu ứng dụng xử lý lâu, bất đồng bộ hoặc tách việc xử lý sang thread khác, auto commit có thể ghi mốc **chưa an toàn về mặt nghiệp vụ** nếu không kiểm soát.

Ví dụ:

~~~text
poll() nhận offsets 100..109
       |
       +--> đưa vào worker pool
       |
       +--> consumer commit offset 110
       |
       +--> worker đang xử lý 105
                 |
                 +--> crash
~~~

Khi restart từ 110, record 105 không được replay qua checkpoint dù nghiệp vụ chưa hoàn thành. Do đó với xử lý có side effect cần chắc chắn, thường chủ động quản lý commit khi đã xác nhận kết quả.

### 6.2. Manual commit

Pseudocode cho một partition được xử lý tuần tự:

~~~text
loop:
    records = poll()

    for each record in order:
        process_idempotently_in_db_transaction(record)

    after all records are durable:
        commit(next_offset_after_last_success)
~~~

Nếu mỗi batch có nhiều partition, phải commit **offset an toàn riêng cho từng partition**. Không dùng offset cao nhất của partition A để commit partition B.

Cần phân biệt API của client:

- **commitSync:** chờ phản hồi commit, có thể dễ diễn giải trong các mốc cần chắc chắn; vẫn phải xử lý lỗi/timeout và tránh giả định không thể replay.
- **commitAsync:** không chặn luồng chờ, nhưng cần xử lý callback và thứ tự hoàn tất; một retry commit offset cũ về sau có thể dẫn tới checkpoint lùi nếu không được thiết kế cẩn thận.
- **Commit khi đóng/rebalance:** commit những record đã hoàn tất trong partition bị thu hồi; không cam kết hộ các task còn chạy.

### 6.3. Xử lý từng record và batch

Có hai chiến lược phổ biến:

**Theo record:** xử lý, commit DB, sau đó cập nhật checkpoint an toàn. Dễ lý giải nhưng commit offset mỗi record làm tăng overhead. Có thể gom commit theo lô khi vẫn giữ tiến độ an toàn.

**Theo batch:** xử lý một nhóm record, chỉ commit sau khi toàn batch cần thiết đã hoàn thành. Tăng throughput nhưng khi crash có thể replay cả batch, đòi idempotency.

Nếu offset 100 đã xong, 101 lỗi, 102 đã xong do xử lý song song, **checkpoint an toàn liên tục** chỉ tới 101 (offset tiếp theo sau 100). Không commit 103 vì như vậy bỏ 101. Có thể:

- giữ 102 đã xử lý trong bảng dedup, đợi retry 101 rồi nâng checkpoint;
- dừng xử lý partition ở 101;
- áp chính sách chuyển 101 sang DLQ có ghi bền vững rồi mới coi 101 đã được xử lý theo định nghĩa của pipeline.

Quyết định phải rõ: **“đã hoàn tất” có nghĩa đã áp dụng nghiệp vụ, hay đã chuyển an toàn sang một luồng lỗi có owner?**

### 6.4. Rebalance và partition assignment

Rebalance có thể xảy ra khi consumer tham gia/rời group, thay đổi membership, hoặc có sự kiện điều phối. Partition đang xử lý có thể được chuyển cho consumer khác.

Ví dụ:

~~~text
Consumer A xử lý partition 2, offset 501
    |
    | rebalance
    v
Consumer A mất quyền sở hữu partition 2
Consumer B nhận partition 2, khởi động từ committed offset
~~~

Nếu A vẫn để task nền tiếp tục ghi DB sau khi B bắt đầu xử lý cùng record, có thể xảy ra xử lý trùng hoặc đảo thứ tự ở cấp nghiệp vụ. Cần đảm bảo:

1. Dừng nhận công việc mới ở partition bị revoke.
2. Hoàn tất hoặc hủy có kiểm soát các task chưa xong.
3. Chỉ commit tiến độ thực sự bền vững khi còn quyền phù hợp.
4. Chặn side effect trùng qua idempotency, version hoặc cơ chế fencing khi cần.
5. Quản lý thời gian poll/heartbeat và timeout để tránh rebalance do xử lý lâu.

Khi xử lý nặng, có thể sử dụng pause/resume phù hợp để không tăng backlog trong bộ nhớ, hoặc tách worker nhưng vẫn phải giữ ownership và checkpoint nhất quán.

### 6.5. Trường hợp offset không còn hợp lệ

Nếu consumer nghỉ quá lâu, dữ liệu cần đọc có thể đã bị xóa bởi chính sách retention, hoặc topic bị tái tạo. Cấu hình reset offset như **earliest/latest** chỉ là lựa chọn kỹ thuật cho lúc không có checkpoint hợp lệ; nó **không khôi phục dữ liệu đã hết hạn**.

- **Earliest:** bắt đầu từ mốc sớm nhất hiện còn trong log.
- **Latest:** bắt đầu từ phần dữ liệu mới; có thể bỏ qua lịch sử cần thiết nếu dùng không đúng.
- **Fail/none:** từ chối chạy để con người quyết định cách khôi phục khi không có offset phù hợp.

Đối với pipeline nghiệp vụ quan trọng, mất offset hoặc thiếu dữ liệu retention có thể cần **snapshot, event archive, rebootstrap projection hoặc quy trình đối soát**. Không tùy tiện đặt latest để ứng dụng “chạy xanh” khi những giao dịch cũ chưa được xử lý.

## 7. RabbitMQ: xác nhận theo lần giao

Trong mô hình queue của RabbitMQ, consumer nhận delivery, dùng delivery tag trong phạm vi channel để ACK, NACK hoặc reject. Message chưa được ACK có thể được giao lại khi channel/connection đóng theo cơ chế của broker.

### 7.1. Manual ACK

Luồng thường gặp:

~~~text
RabbitMQ queue
   |
   +-- deliver message tag=18 --> Consumer
                                    |
                                    +-- validate/process
                                    +-- commit DB
                                    +-- basicAck(tag=18)
~~~

**Delivery tag** không phải eventId, không nhất thiết ổn định sau redelivery, và có hiệu lực theo channel. Consumer không dùng tag như khóa dedup nghiệp vụ.

ACK có thể xác nhận một delivery hoặc **multiple** deliveries theo phạm vi được broker hỗ trợ. Khi chọn multiple, phải biết toàn bộ delivery trước mốc đó đã hoàn tất an toàn.

### 7.2. NACK với requeue

Minh họa chính sách:

~~~text
Nếu xử lý thành công:
    commit DB
    ACK

Nếu lỗi hạ tầng tạm thời:
    NACK / đưa vào retry queue có delay phù hợp
    ghi metric retry

Nếu message không thể xử lý:
    reject / NACK không requeue theo chính sách
    broker dead-letter hoặc quy trình cách ly
~~~

**Requeue ngay vô hạn** có thể tạo vòng lặp đỏ, nhất là khi nhiều consumer cùng gặp một message lỗi. Sử dụng retry queue, dead-letter exchange hoặc cơ chế trì hoãn được hỗ trợ; cần xác minh các tính năng, tham số và behavior theo phiên bản/cấu hình broker đang dùng.

### 7.3. Prefetch và thông điệp đang chờ ACK

Prefetch giới hạn số delivery chưa được xác nhận mà broker đưa tới consumer trong phạm vi quy định. Prefetch quá lớn có thể làm một consumer giữ nhiều công việc chưa xử lý, tăng memory, tăng thời gian chờ của các consumer khác và tạo replay lớn khi nó crash.

Prefetch quá nhỏ có thể giảm throughput khi xử lý mỗi message có độ trễ cao. Chọn dựa trên thời gian xử lý, concurrency, mức tải và nhu cầu thứ tự; không coi một giá trị là tối ưu cho mọi queue.

### 7.4. Publisher confirms không phải consumer ACK

RabbitMQ có **publisher confirms** để publisher nhận được tín hiệu từ broker về việc publish theo chế độ đã bật. Đây là cơ chế **đầu vào broker**, không nói rằng consumer đã xử lý và lưu kết quả. Để tăng độ bền, còn cần lựa chọn queue/message durability, xử lý publish failure và consumer ACK đúng thời điểm.

## 8. Queue có visibility timeout: nhận, ẩn, xóa

Một số hệ thống queue như Amazon SQS sử dụng cách diễn đạt khác ACK/NACK:

1. Consumer **receive** một message.
2. Broker tạm **ẩn** message với các consumer khác trong thời gian visibility timeout.
3. Consumer xử lý và **delete** message bằng receipt handle sau khi hoàn thành.
4. Nếu chưa delete khi hết thời gian ẩn, message có thể xuất hiện lại để được nhận lần nữa.

~~~text
Receive -> Invisible (lease)
              |
              +-- xử lý xong, Delete -> hoàn tất
              |
              +-- timeout / consumer crash
                        |
                        v
                    Visible again -> redelivery
~~~

### 8.1. Visibility timeout cần khớp công việc

Nếu một task thường mất 2 phút nhưng visibility timeout chỉ 30 giây, message có thể xuất hiện lại khi consumer đầu tiên vẫn đang làm, dẫn đến xử lý song song cùng một nghiệp vụ. Có thể dùng cơ chế **gia hạn visibility/lease** theo API của hệ thống, nhưng vẫn cần idempotency vì lỗi mạng và hết hạn không thể loại bỏ hoàn toàn.

Ngược lại, timeout quá dài sẽ khiến message chưa xử lý được giao lại chậm sau khi consumer crash. Cần cân bằng thời gian hoàn thành, khả năng retry và yêu cầu khôi phục.

### 8.2. Receipt handle và ID của message

Receipt handle gắn với một lần receive; nó không phải định danh nghiệp vụ ổn định. Khi redelivery, handle có thể đổi. Để chống xử lý trùng, cần eventId hoặc business key được xác minh qua dữ liệu bền vững.

### 8.3. Queue khác stream log

Queue có thể gỡ message sau ACK/delete; stream log thường giữ record theo retention và consumer chỉ di chuyển checkpoint. Vì vậy “replay lịch sử” có thể thực hiện dễ dàng hơn với log còn giữ dữ liệu, trong khi queue đã delete thì cần nguồn lưu lịch sử khác.

Không thiết kế toàn bộ quy trình phục hồi dựa trên khả năng của một loại broker rồi áp nguyên xi sang loại khác.

## 9. Retry: phân loại lỗi trước khi gửi lại

Không phải mọi lỗi đều nên retry. Retry chỉ hữu ích khi nguyên nhân có khả năng biến mất, hoặc khi có phương án xác minh và sửa trước khi xử lý lại.

### 9.1. Ma trận lỗi và xử lý

| Loại lỗi | Ví dụ | Hướng xử lý thường phù hợp |
| --- | --- | --- |
| Tạm thời do hạ tầng | DB connection timeout, service unavailable | Retry có giới hạn, backoff, jitter |
| Quá tải | Rate limit, broker/DB throttling | Backoff theo tín hiệu, kiểm soát concurrency |
| Timeout không rõ kết quả | Gửi lệnh thanh toán, không nhận hồi đáp | Tra cứu kết quả, retry với idempotency key |
| Lỗi schema không hỗ trợ | Event version lạ, payload không parse được | Cách ly/quarantine, DLQ và điều tra |
| Dữ liệu nghiệp vụ không hợp lệ | Order không tồn tại, trạng thái cấm chuyển | Quy tắc từ chối, không retry mù |
| Dữ liệu phụ thuộc chưa đến | Event giao khác thứ tự, projection chưa đồng bộ | Retry chậm, giữ trạng thái chờ hoặc điều phối thứ tự |
| Lỗi code có tính quyết định | Null pointer với cùng payload | Alert, sửa code, DLQ và replay sau sửa |
| Lỗi bảo mật | Thiếu quyền, chữ ký không hợp lệ | Từ chối và điều tra, không retry không giới hạn |

Một consumer phải phân biệt **message lỗi** với **hệ thống nhận lỗi**. Nếu mọi message đang bị fail vì database down, chuyển toàn bộ sang DLQ có thể không đúng mục tiêu; có thể tạm dừng tiêu thụ hoặc giảm concurrency để tránh làm quá tải.

### 9.2. Backoff và jitter

Một ví dụ thời gian retry tăng dần:

~~~text
Lần 1: ngay sau lỗi có phân loại
Lần 2: sau khoảng 1 giây
Lần 3: sau khoảng 2 giây
Lần 4: sau khoảng 4 giây
Lần 5: sau khoảng 8 giây
Sau giới hạn: DLQ hoặc quy trình xử lý được chỉ định
~~~

Các khoảng trên chỉ để minh họa. Dùng **jitter** để tránh hàng nghìn consumer cùng retry tại một thời điểm sau khi hạ tầng phục hồi. Tổng retry cần chịu **ngân sách thời gian và số lần** phù hợp nghiệp vụ.

Nếu mọi tầng đều retry, một event có thể tạo ra số lượng request tới downstream tăng theo cấp số nhân. Nên có trách nhiệm retry rõ: broker/consumer retry ở đâu, service downstream retry ở đâu, và deadline kết thúc là gì.

### 9.3. Retry tại chỗ, retry queue và delayed processing

**Retry tại chỗ:** consumer đợi ngắn rồi thử lại trong cùng lần xử lý. Đơn giản nhưng giữ partition/worker trong thời gian chờ, có thể giảm throughput.

**Retry queue có delay:** đưa một bản ghi hoặc message đại diện cho công việc thất bại sang luồng retry, xác nhận message gốc sau khi **handoff bền vững**. Phải bảo đảm không mất message giữa hai bước và không bỏ qua ý nghĩa thứ tự.

**Delayed processing/scheduler:** lưu công việc và thời điểm xử lý lại, phù hợp với workflow dài hoặc thời gian chờ lớn. Cần có source of truth và cơ chế xác nhận công việc scheduler đã chạy.

**Dead-letter queue (DLQ):** cách ly thông điệp không thể xử lý sau chính sách retry hoặc không phù hợp schema; DLQ cần owner, retention, quan sát và runbook. Nó không tự là cơ chế sửa dữ liệu.

Không áp dụng cùng chiến lược cho mọi event. Một luồng tài chính cần duy trì sự chính xác và khả năng đối soát; một luồng gửi notification có thể chấp nhận chính sách retry và độ trễ khác.

## 10. Dead-letter queue và “poison message”

**Poison message** là thông điệp khiến consumer thất bại lặp lại một cách có tính quyết định hoặc không thể xử lý với code/schema/điều kiện hiện tại.

Ví dụ:

- Event yêu cầu trường bắt buộc nhưng payload không có.
- Event version mới được phát trước khi consumer có khả năng đọc.
- Một dữ liệu ngoại lệ gây lỗi mapping.
- Business reference không tồn tại và theo chính sách không thể khắc phục.
- Bản ghi bị hỏng hoặc không thể deserialize.

### 10.1. Dữ liệu tối thiểu cần giữ

Một message trong DLQ thường cần kèm hoặc liên kết tới:

- Payload gốc và content type/schema version nếu được phép lưu.
- **Event ID**, aggregate ID, producer và mốc thời gian.
- Topic/queue nguồn, partition, offset hoặc delivery metadata có ích.
- **Failure category** và mã lỗi ổn định.
- Thông tin về số lần thử và các mốc retry.
- Trace/correlation ID phục vụ điều tra.
- Thời điểm message được cách ly và owner xử lý.

Không lưu nguyên secret, credential hoặc dữ liệu nhạy cảm trái chính sách; cần cơ chế kiểm soát quyền truy cập, mã hóa và retention.

### 10.2. Khi nào được đánh dấu message gốc là xong?

Nếu hệ thống có chính sách “đưa vào DLQ là hoàn thành trách nhiệm của primary consumer”, điều kiện tối thiểu là **message lỗi đã được ghi bền vững vào DLQ hoặc nguồn theo dõi được xác nhận**. Nếu chỉ gửi bất đồng bộ sang DLQ rồi ACK bản gốc trước khi nhận kết quả, một lần lỗi publish DLQ có thể làm mất dấu message.

Trong Kafka, có thể kết hợp transactional producer/offset commit trong phạm vi hỗ trợ khi chuyển một record sang topic khác. Với broker khác hoặc external DB, cần chiến lược outbox/inbox/handoff phù hợp.

### 10.3. Replay từ DLQ

Replay cần được điều hành có chủ đích:

1. Phân tích nguyên nhân và sửa lỗi code, config hoặc dữ liệu đầu vào.
2. Kiểm tra event có còn hợp lệ theo trạng thái nghiệp vụ hiện tại hay không.
3. Chọn tập message cần replay, tránh đưa tất cả vào cùng lúc.
4. Giữ định danh nghiệp vụ ổn định, không tạo ý định mới ngoài ý muốn.
5. Điều chỉnh lưu lượng để downstream không bị sốc tải.
6. Theo dõi kết quả, phân loại còn lỗi và đối soát side effect đã xảy ra.
7. Lưu vết ai thực hiện replay, tại sao và từ đâu.

Không thể luôn xử lý lại nguyên một event cũ như thể thời gian chưa trôi qua. Ví dụ một yêu cầu giữ hàng quá hạn cần áp quy tắc hiện hành và khả năng có thao tác bù, thay vì tự động giữ hàng lần nữa.

## 11. Idempotency và Inbox Pattern

At-least-once yêu cầu consumer chống việc áp dụng cùng một ý định nhiều lần. **Inbox pattern** là một cách lưu dấu message đã xử lý cùng transaction nghiệp vụ.

### 11.1. Mô hình bảng minh họa

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khóa có thể cần thêm tenant hoặc phạm vi nghiệp vụ để bảo đảm duy nhất đúng context. **consumer_name** chỉ là ví dụ cho một subscriber logic ổn định, không nên là hostname/instance ID có thể thay đổi.

### 11.2. Trình tự xử lý an toàn

~~~text
Begin transaction
  Insert processed-message key (unique)
      |
      +-- Duplicate key:
      |       xác định xử lý trước đã hoàn tất
      |       không áp dụng side effect thêm
      |
      +-- Insert thành công:
              kiểm tra nghiệp vụ
              áp dụng cập nhật có điều kiện
              lưu reservation / result
Commit transaction

ACK / commit offset
~~~

Cần cẩn thận với tình huống xử lý nghiệp vụ thất bại: không commit marker “đã xử lý thành công” khi side effect chưa hoàn tất theo hợp đồng. Nếu quy trình quyết định **từ chối hợp lệ** là một kết quả cuối, có thể lưu chính kết quả từ chối bền vững rồi xác nhận message; cách diễn đạt và bảng trạng thái phải rõ ràng.

### 11.3. Ghi marker trong cùng transaction

Nếu ghi marker trước, commit riêng, rồi crash trước khi ghi nghiệp vụ, lần redelivery sẽ gặp marker và **bỏ qua message chưa được áp dụng**. Vì vậy marker và side effect thuộc cùng database nên được ghi trong cùng transaction, hoặc có một cơ chế điều phối bền vững tương đương.

Nếu side effect là gửi HTTP sang hệ thống khác, một transaction DB cục bộ không thể bảo đảm atomicity với HTTP call. Có thể dùng:

- Idempotency key được dịch vụ đích công nhận.
- Bảng công việc trạng thái **PENDING → CONFIRMED/FAILED**.
- Outbox cho lệnh/sự kiện cần phát.
- Tra cứu trạng thái đích sau timeout trước khi quyết định retry.
- Reconciliation định kỳ cho trạng thái chưa rõ kết quả.

### 11.4. Idempotency key cần chọn theo nghiệp vụ

**eventId** thường hữu ích khi broker redeliver đúng cùng sự kiện. Nhưng nếu producer có thể phát **hai event ID khác nhau đại diện cùng một lệnh nghiệp vụ**, chỉ khử trùng lặp theo eventId không đủ.

Ví dụ hai yêu cầu giữ hàng có:

~~~text
eventId = evt-a, orderId = ORD-1001, reservationRequestId = RQ-001
eventId = evt-b, orderId = ORD-1001, reservationRequestId = RQ-001
~~~

Hai event có ID khác, nhưng cùng reservationRequestId có thể đại diện **một ý định giữ hàng**. Consumer phải bảo vệ **business invariant** bằng khóa nghiệp vụ hoặc constraint phù hợp để không trừ tồn hai lần.

## 12. Outbox Pattern và liên hệ với ACK

Outbox giải quyết một vấn đề ở producer: nếu cập nhật DB thành công nhưng publish event thất bại, các service khác có thể không được thông báo. Nó cũng liên hệ trực tiếp tới consumer khi xử lý message tạo một event mới.

### 12.1. Sơ đồ

~~~text
Consumer nhận OrderPlaced
       |
       v
Database transaction:
  - ghi reservation
  - ghi processed_message marker
  - ghi outbox event InventoryReserved
       |
       v
Commit transaction
       |
       +--> ACK / commit source message
       |
       +--> Outbox publisher gửi InventoryReserved
                         |
                         +--> broker ACK producer
                         +--> đánh dấu outbox đã phát
~~~

Nếu publisher crash trước khi đánh dấu outbox, event có thể được publish lại. Vì thế consumer của **InventoryReserved** cũng cần idempotency.

Outbox không biến toàn bộ thế giới thành giao dịch đúng một lần; nó giúp **không bị mất ý định publish khi giao dịch dữ liệu đã commit**, đồng thời chấp nhận khả năng publish trùng.

### 12.2. Một transaction chứa những gì?

Với cùng một DB, có thể đặt **inbox marker + nghiệp vụ + outbox** trong một transaction để consumer chuyển một message thành trạng thái mới và message tiếp theo một cách bền vững. ACK nguồn chỉ sau commit.

Nếu các bước nằm ở nhiều database hoặc nhiều hệ thống bên ngoài, cần định nghĩa lại ranh giới transaction và quy trình bù; không thể trông chờ một transaction cục bộ quản lý tất cả.

## 13. Quản lý thứ tự thông điệp khi có retry và replay

Delivery order và processing order là hai chuyện khác nhau. Broker có thể giữ thứ tự trong một phạm vi nhất định, nhưng concurrency, retry queue và redelivery có thể làm thứ tự **áp dụng nghiệp vụ** thay đổi.

### 13.1. Thứ tự theo Kafka partition

Kafka duy trì thứ tự record **trong một partition**. Nếu các event của một Order cần xử lý theo thứ tự, producer có thể chọn partition key là **orderId** để đưa cùng order tới một partition. Điều đó không cung cấp thứ tự tổng thể cho mọi Order hoặc nhiều topic.

Ví dụ:

~~~text
Partition 0:
  101 OrderPlaced(ORD-1001)
  102 OrderConfirmed(ORD-1001)
  103 OrderCancelled(ORD-1001)
~~~

Nếu xử lý offset 102 ở worker khác trước khi 101 hoàn tất, business state có thể sai dù log vẫn sắp xếp đúng. Cần chọn:

- xử lý tuần tự trong partition;
- điều phối theo aggregate key;
- hoặc dùng sequence/version kiểm tra chuyển trạng thái hợp lệ.

### 13.2. Retry ngoài luồng có thể phá thứ tự

Giả sử offset 101 thất bại và được đưa sang retry topic, nhưng consumer tiếp tục commit và xử lý 102. Khi 101 trở lại, thứ tự áp dụng thành 102 trước 101.

Cách xử lý phụ thuộc nghiệp vụ:

1. Nếu hai event độc lập, chấp nhận out-of-order và làm handler có điều kiện.
2. Nếu phải giữ thứ tự, dừng partition/key, chờ retry hoặc sử dụng sequence gate.
3. Nếu có state machine, kiểm tra expected version và chờ/đối soát khi thiếu predecessor.
4. Nếu chuyển DLQ, xác định xem consumer có được đi tiếp khi một event quan trọng chưa áp dụng hay không.

Không có chính sách chung luôn đúng; một số workflow thích tính sẵn sàng hơn thứ tự tuyệt đối, nhưng quy tắc tiền/tồn kho đòi hỏi chặt chẽ hơn.

### 13.3. Consumer không nên tự suy luận theo offset giữa các partition

Offset 500 của partition A và offset 400 của partition B không tạo thứ tự thời gian toàn cục. Mốc timestamp cũng không luôn cho thứ tự nhân quả do độ trễ publish và lệch đồng hồ. Nếu cần causal ordering, cần message ID, aggregate sequence hoặc cơ chế nghiệp vụ phù hợp.

## 14. Consumer crash: ba cửa sổ quan trọng

Xét Inventory Consumer ghi reservation vào DB rồi commit Kafka offset.

### 14.1. Crash trước DB commit

~~~text
poll(offset=50)
   |
   v
begin transaction
   |
   X crash
~~~

Chưa có thay đổi DB bền vững. Khi restart từ committed offset trước đó, offset 50 được đọc lại và consumer thử xử lý. Đây là đường phục hồi thường mong muốn.

### 14.2. Crash sau DB commit, trước offset commit

~~~text
poll(offset=50)
   |
   v
DB commit thành công
   |
   X crash trước commit(offset=51)
~~~

Kafka vẫn có thể đưa offset 50 cho consumer mới. **Inbox/unique business key** phải nhận ra đã xử lý; sau đó consumer có thể commit offset 51 an toàn. Không xem redelivery là lỗi nghiêm trọng nếu hệ thống được thiết kế at-least-once.

### 14.3. Crash sau offset commit, trước DB commit

~~~text
poll(offset=50)
   |
   v
commit(offset=51)
   |
   X crash trước DB commit
~~~

Khi restart từ 51, offset 50 bị bỏ qua, có thể làm mất nghiệp vụ. Đây là thứ tự thao tác phải tránh khi offset commit dùng để chứng minh đã hoàn thành.

### 14.4. Không thể tránh mọi cửa sổ bằng cách đảo hai lệnh

Nếu DB commit và offset commit là hai thao tác độc lập, luôn có khoảng trống giữa chúng. **Commit DB trước rồi commit offset + idempotency** là mô hình phổ biến vì cửa sổ lỗi tạo ra trùng có thể khử; cửa sổ tạo mất xử lý thường khó phục hồi hơn.

Đối với use case có yêu cầu mạnh hơn, xem xét transaction trong phạm vi nền tảng hỗ trợ, outbox/inbox hoặc nguồn sự thật và cơ chế replay phù hợp.

## 15. Xử lý song song và checkpoint liên tục

Khi consumer xử lý nhiều event song song, tiến độ xử lý có thể không tuần tự.

Ví dụ:

| Offset | Trạng thái |
| --- | --- |
| 200 | DONE |
| 201 | DONE |
| 202 | PROCESSING |
| 203 | DONE |
| 204 | DONE |

**Checkpoint an toàn** lúc này là **202** (offset tiếp theo chưa hoàn thành), không phải 205. Nếu consumer commit 205, record 202 có nguy cơ mất khả năng replay sau crash.

Một cách triển khai:

~~~text
completedOffsets = tập những offset đã có side effect bền vững
nextCommit = offset thấp nhất chưa hoàn thành liên tiếp

while nextCommit nằm trong completedOffsets:
    nextCommit = nextCommit + 1

commit nextCommit
~~~

Đây chỉ là ý tưởng; hệ thống thực cần tracking theo partition, giới hạn tập đang chờ, xử lý rebalance và chống race giữa task hoàn thành với việc chuyển partition.

### 15.1. Với nhiều partition

Không gom tất cả offset vào một counter chung. Checkpoint có thể có dạng:

~~~text
topic=order-events
partition=0  nextCommit=205
partition=1  nextCommit=88
partition=2  nextCommit=1012
~~~

Khi một partition bị lỗi, các partition khác có thể tiếp tục tiến nếu nghiệp vụ độc lập và client được điều phối đúng. Nhưng nếu aggregate key hoặc invariant trải qua nhiều partition, cần xử lý ở mức nghiệp vụ chứ không kỳ vọng broker tự giữ toàn bộ thứ tự.

### 15.2. Bounded in-flight work

Consumer phải kiểm soát số message đã poll nhưng chưa hoàn tất. Nếu không, khi downstream chậm, hàng nghìn message có thể nằm trong bộ nhớ, khó commit, tăng latency và khiến việc revoke partition kéo dài.

Có thể dùng:

- Giới hạn in-flight theo partition/aggregate key.
- Pause/resume consumer khi queue công việc nội bộ đạt ngưỡng.
- Worker pool hữu hạn.
- Backpressure tới producer khi kiến trúc cho phép.
- Timeout và circuit breaker cho phụ thuộc.
- Theo dõi age của message chưa xử lý và deadline của nghiệp vụ.

## 16. Replay: đọc lại dữ liệu có chủ đích

**Replay** là đưa consumer đọc lại những thông điệp đã từng xuất hiện, thường để tái tạo projection, sửa lỗi xử lý hoặc khôi phục dữ liệu bị sai. Replay khác với redelivery tự động do chưa ACK.

### 16.1. Khi nào cần replay?

- Tạo lại read model từ event log.
- Sửa một bug đã khiến projection tính sai.
- Khôi phục sau khi consumer bị down trong một thời gian.
- Cung cấp dữ liệu lịch sử cho một consumer group mới.
- Đồng bộ lại sau migration hoặc rebuild search index.
- Xử lý lại message đã cách ly trong DLQ.

Replay cần đủ dữ liệu trong retention/archive, schema tương thích hoặc khả năng nâng cấp schema, và cơ chế tránh side effect không mong muốn.

### 16.2. Replay không đồng nghĩa lặp nghiệp vụ

Với Analytics Projection, replay thường có thể xây lại bảng kết quả trong staging hoặc DB mới rồi cutover. Với Payment Consumer, replay event cũ **không được tự động thu tiền lần nữa**.

Nên phân biệt các handler:

- **Projection/rebuild handler:** tạo lại trạng thái dẫn xuất từ event.
- **Business command handler:** có thể tạo side effect thật, cần idempotency và quyền quyết định.
- **Notification handler:** có thể cần đánh dấu đã gửi để không gửi lại email/SMS lịch sử ngoài ý muốn.

Khi replay một luồng đã từng chạy, cần ghi rõ mode, phạm vi và các side effect bị vô hiệu hóa hoặc được bảo vệ.

### 16.3. Khôi phục offset

Ví dụ một consumer group đang commit 1000 nhưng cần xây lại projection từ 200. Không tùy tiện reset offset trong lúc nhiều instance còn hoạt động. Có thể sử dụng **consumer group riêng** để rebuild vào kho dữ liệu mới, hoặc dừng group và kiểm soát việc reset đúng theo công cụ/phiên bản.

Cần lưu:

- Lý do và phạm vi replay.
- Topic, partition, offset đầu/cuối hoặc mốc business event.
- Consumer group đang dùng.
- Snapshot/version schema.
- Kết quả đối soát.
- Người thực hiện và phương án khôi phục.

Nếu dữ liệu cần replay đã bị xóa do retention, cần bootstrap từ snapshot/archive hoặc các nguồn dữ liệu bền vững khác; offset không thể tự tạo lại message đã mất.

## 17. Reconciliation: khi ACK không chứng minh kết quả bên ngoài

Có những thao tác mà consumer gọi sang hệ thống khác, ví dụ:

- Payment Service gửi lệnh thu tiền tới cổng thanh toán.
- Shipping Service gửi yêu cầu tạo vận đơn.
- Notification Service gửi SMS/email.
- Inventory gửi lệnh tới hệ thống kho vật lý.

Nếu request timeout, consumer không biết hệ thống đích đã thực hiện hay chưa. Retry y nguyên có thể tạo side effect trùng, trong khi ACK như thành công có thể bỏ sót công việc.

Một giải pháp có cấu trúc:

1. Ghi **operation ID/business request ID** trước hoặc cùng bước nghiệp vụ.
2. Gửi yêu cầu với idempotency key ổn định nếu đối tác hỗ trợ.
3. Nếu nhận kết quả xác định, lưu trạng thái và ACK/commit.
4. Nếu timeout hoặc kết quả chưa rõ, lưu trạng thái **PENDING_RECONCILIATION**.
5. Tra cứu kết quả ở đối tác hoặc dùng callback được xác thực.
6. Chỉ tạo lệnh mới khi quy tắc xác nhận an toàn; tránh tạo một giao dịch tài chính thứ hai.
7. Có job và cảnh báo cho trạng thái mắc kẹt quá ngưỡng.

Bằng cách này, trạng thái **message đã được broker giao** được tách khỏi **giao dịch bên ngoài đã hoàn tất**. Đôi khi consumer được phép ACK sau khi đã ghi **công việc đối soát bền vững**, dù kết quả cuối cùng chưa có, nếu toàn bộ pipeline định nghĩa rõ trách nhiệm xử lý tiếp.

## 18. Quan hệ giữa thời gian lưu message và vị trí đọc

Một consumer có checkpoint chính xác nhưng vẫn không thể hồi phục nếu broker đã xóa những record cần đọc. Do đó retention, lag và khôi phục là một bài toán chung.

### 18.1. Retention không phải ACK

Với log dạng Kafka, việc consumer commit offset không nhất thiết xóa record khỏi log; retention/compaction chi phối dữ liệu còn được lưu. Một group chậm có thể tụt quá xa so với vùng dữ liệu còn giữ.

Với queue truyền thống, ACK/delete thường làm message rời queue. Sau đó muốn replay phải có bản ghi ở nơi khác như event store, audit log, outbox archive hoặc DLQ theo chính sách.

### 18.2. Chính sách retention theo nhu cầu

Những câu hỏi cần trả lời:

- Consumer có thể dừng tối đa bao lâu mà vẫn đọc đủ message?
- Nếu dừng vượt khoảng đó, có snapshot/archive phục hồi không?
- DLQ giữ bao lâu và ai phải xử lý trước khi hết hạn?
- Message chứa dữ liệu nhạy cảm được lưu, mã hóa và xóa theo chính sách nào?
- Có cần tái tạo projection sau một thay đổi schema trong nhiều tháng?
- Nếu dùng log compaction, các state/tombstone còn đủ để rebuild mô hình không?

Không chọn retention chỉ theo dung lượng ổ cứng; phải tính tới **RPO/RTO, khả năng vận hành, quy định dữ liệu và hành vi phục hồi**.

## 19. Monitoring: biết consumer có đang tiến hay mắc kẹt

ACK và committed offset cung cấp một phần bằng chứng kỹ thuật. Để biết cả hệ thống hoạt động đúng cần quan sát nhiều lớp.

| Nhóm metric | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Consumer lag | Records sau committed offset, lag theo thời gian | Consumer có theo kịp producer không? |
| Throughput | Records nhận/giây, xử lý thành công/giây | Tải và năng lực xử lý |
| Processing latency | Thời gian từ nhận đến DB commit/ACK | Hiệu năng từng handler |
| End-to-end age | Thời gian từ event occurredAt đến nghiệp vụ hoàn tất | Độ trễ nghiệp vụ thực tế |
| Retry | Số lần retry, thời gian chờ, retry exhausted | Phụ thuộc không ổn định hay poison message? |
| DLQ | Số message mới, tuổi message cũ nhất | Khối lượng công việc cần điều tra |
| Duplicate | Tỉ lệ dedup qua inbox/business key | Mức redelivery và hiệu quả chống trùng |
| Ack/commit errors | Lỗi ACK, commit, timeout, failed requeue | Nguy cơ replay/mất checkpoint |
| Rebalance | Số lần rebalance, thời gian mất assignment | Consumer có bị gián đoạn không? |
| In-flight | Message poll nhưng chưa hoàn tất | Áp lực memory và độ trễ |
| Reconciliation | Số trạng thái PENDING chưa có kết quả | Rủi ro nghiệp vụ ngoài broker |

### 19.1. Consumer lag không phải là toàn bộ sự thật

Lag bằng 0 chỉ cho biết consumer đã theo tới mốc nhất định theo cách đo; nó **không đảm bảo side effect chính xác**, nhất là nếu auto commit chạy trước xử lý hoặc message được đưa vào DLQ hàng loạt.

Một pipeline có thể lag thấp nhưng có 1.000 giao dịch thanh toán đang chờ đối soát. Ngược lại, lag cao trong một hệ thống analytics có thể chấp nhận được trong một giai đoạn batch nếu vẫn đáp ứng SLA.

### 19.2. Tách chỉ số kỹ thuật và kết quả nghiệp vụ

Ví dụ với Inventory:

- **Kỹ thuật:** consumer lag, số ACK/commit, số retry, DLQ, DB timeout.
- **Nghiệp vụ:** số reservation tạo, số từ chối hợp lệ, trường hợp giữ trùng, số lượng tồn âm, số reservation hết hạn.

Nếu ACK tăng nhưng reservation thành công giảm bất thường, cần điều tra. Chỉ đo “message processed” theo số ACK có thể che khuất logic lỗi hoặc việc bỏ qua message vì điều kiện sai.

### 19.3. Alert có ý nghĩa

Một số cảnh báo thực tế:

- Lag vượt ngưỡng và tiếp tục tăng trong thời gian đủ dài.
- Tuổi message chưa xử lý vượt deadline nghiệp vụ.
- DLQ xuất hiện message mới thuộc loại sự kiện quan trọng.
- Tỉ lệ retry hoặc lỗi DB tăng liên tục.
- Consumer liên tục rebalance và không giữ được partition đủ lâu.
- Reconciliation backlog vượt thời hạn cho phép.
- Không có message được xử lý trong khi upstream vẫn publish đều.

Tránh cảnh báo mọi lần retry như sự cố nghiêm trọng; retry là hành vi bình thường trong một hệ thống at-least-once được thiết kế đúng.

## 20. Hướng dẫn xử lý sự cố theo triệu chứng

### 20.1. Consumer đứng yên, lag tăng

Kiểm tra theo thứ tự có ý nghĩa:

1. Consumer có còn thuộc group/đăng ký queue không?
2. Broker có đang giữ hoặc giao message không?
3. Handler có kẹt DB, deadlock, network hoặc công việc quá lâu?
4. Có poison message đứng đầu partition/queue không?
5. Có rebalance liên tục, lease hết hạn hoặc heartbeat không thành công?
6. Có backpressure, prefetch, concurrency limit hoặc pause chưa được resume?
7. Checkpoint gần nhất là bao nhiêu; có message đang xử lý dở?
8. Có thể tăng consumer parallelism theo partition/key không, và rủi ro thứ tự là gì?

Không tăng số instance mù khi số partition ít hơn số consumer hoặc khi tất cả lỗi do cùng một database down.

### 20.2. Message bị xử lý hai lần

Kiểm tra:

- Producer có republish sau timeout không?
- Consumer crash sau DB commit trước ACK?
- Visibility timeout hết hạn trong lúc handler còn chạy?
- Kafka rebalance và task cũ vẫn ghi dữ liệu?
- Retry queue tạo một message mới với eventId không ổn định?
- Inbox/dedup key có đúng phạm vi không?
- Unique constraint có bảo vệ concurrency không?

Biện pháp khắc phục phải vừa sửa nguyên nhân tăng duplicate, vừa bảo vệ **idempotency** vì không thể loại bỏ hoàn toàn các cửa sổ redelivery trong mọi trường hợp.

### 20.3. Có thông điệp mới nhưng thiếu bản ghi nghiệp vụ

Điều tra:

1. Consumer có ACK/commit trước DB transaction?
2. Có filter bỏ qua event do schema/handler version không?
3. Có message sang DLQ nhưng dashboard không cảnh báo?
4. Có reset offset tới latest hoặc sai group ID?
5. Có sự kiện bị xóa do retention trong lúc consumer dừng?
6. Có transaction rollback sau khi marker đã ghi?
7. Có áp sai mapping ID/tenant hoặc business state machine từ chối mà không lưu kết quả?

Nếu xác nhận đã bỏ qua message, cần phân tích phạm vi dữ liệu bị ảnh hưởng và cách replay/đối soát an toàn. Không chỉ chuyển lại offset rồi chạy nếu handler có thể tạo side effect trùng.

### 20.4. DLQ tăng nhanh

Phân nhóm theo failure category, schema version, producer và thời điểm thay đổi gần nhất. Một bản deploy phá vỡ tương thích có thể làm mọi message mới lỗi giống nhau. Nếu gốc là hạ tầng tạm thời, sửa phụ thuộc và điều chỉnh retry trước khi replay. Nếu là dữ liệu poison, sửa handler hoặc cách xử lý dữ liệu ngoại lệ.

Không xóa DLQ để dashboard về 0 khi chưa giải quyết và chưa đối soát các nghiệp vụ bị ảnh hưởng.

## 21. Ví dụ triển khai theo từng mốc: Inventory Consumer

Giả sử Inventory Service nhận **OrderPlaced** và tạo một reservation cho mỗi order.

### 21.1. Dữ liệu tối thiểu

~~~text
inventory_stock
  sku
  available_quantity
  version

reservation
  reservation_id
  order_id
  status
  created_at

processed_event
  consumer_name
  event_id
  processed_at

outbox
  event_id
  event_type
  payload
  published_at
~~~

**Ràng buộc chính:** một reservation cho cùng order/ý định giữ hàng không được tạo hai lần. Việc trừ tồn phải bảo toàn điều kiện số lượng khả dụng, kể cả khi hai yêu cầu đến đồng thời.

### 21.2. Trình tự xử lý với Kafka

~~~text
Kafka: poll OrderPlaced(offset=105, partition=2)
   |
   v
Validate event schema + id + tenant
   |
   v
BEGIN DB TRANSACTION
   |
   +--> Nếu business reservation đã tồn tại:
   |         dùng trạng thái đã ghi, không trừ tồn
   |
   +--> Nếu chưa tồn tại:
   |         cố giữ tồn bằng update có điều kiện
   |         ghi reservation RESERVED / REJECTED
   |
   +--> ghi processed_event marker
   +--> ghi outbox event về kết quả
   |
   v
COMMIT DB
   |
   v
mark offset 105 DONE
   |
   v
khi mọi offset trước đó trong partition DONE:
    commit Kafka next offset=106
~~~

Nếu DB timeout trước commit, record 105 chưa được coi là DONE; nó sẽ được retry theo chính sách. Nếu DB commit thành công nhưng offset commit thất bại, record được replay và dedup không làm trừ tồn hai lần.

### 21.3. Cập nhật tồn có điều kiện

Một ý tưởng SQL minh họa:

~~~sql
UPDATE inventory_stock
SET available_quantity = available_quantity - :quantity,
    version = version + 1
WHERE sku = :sku
  AND available_quantity >= :quantity;
~~~

Ứng dụng kiểm tra số dòng cập nhật để xác định giữ hàng thành công hay không, trong transaction có ràng buộc idempotency. Với nhiều SKU trên cùng đơn, cần thiết kế transaction/locking và rollback đầy đủ để không giữ một phần ngoài ý muốn khi nghiệp vụ yêu cầu tất cả hoặc không gì cả.

### 21.4. Kết quả nghiệp vụ khi không đủ hàng

**Không đủ tồn** có thể là kết quả từ chối hợp lệ, không phải lỗi hạ tầng. Consumer có thể lưu **ReservationRejected** bền vững, ghi outbox để thông báo Order, rồi ACK/commit event gốc. Không nên retry cùng yêu cầu vô hạn khi quy tắc nghiệp vụ đã quyết định từ chối, trừ khi nghiệp vụ thật sự muốn chờ hàng bổ sung.

### 21.5. Khi nhận event cũ sau thời gian dài

Nếu Order đã bị hủy hoặc reservation đã hết hạn, consumer không được tự động tái tạo giữ hàng chỉ vì replay một event cũ. Dữ liệu và state machine phải giúp phân biệt event replay, trạng thái cuối đã biết và tình huống cần đối soát.

## 22. Thực hành với Java/Spring: các nguyên tắc áp dụng

Hệ sinh thái Java có thể dùng Spring for Apache Kafka, RabbitMQ client/Spring AMQP hoặc các thư viện khác. Cấu hình và API phụ thuộc phiên bản thư viện; mục tiêu ở đây là hiểu **điểm đặt transaction, ACK và lỗi**, không chép một cấu hình rồi mặc định có bảo đảm exactly-once.

### 22.1. Pseudocode cho consumer có database

~~~java
void onMessage(OrderPlaced event, BrokerDelivery delivery) {
    try {
        // Trong một transaction DB:
        // 1. ghi processed-event marker với unique key
        // 2. kiểm tra và thực hiện reservation có idempotency
        // 3. ghi outbox event mô tả kết quả
        inventoryApplication.handleInTransaction(event);

        // Chỉ ACK khi transaction đã hoàn thành bền vững.
        delivery.acknowledge();
    } catch (TransientInfrastructureException ex) {
        // Không ACK như thành công.
        // Áp dụng retry có giới hạn, delay hoặc cơ chế broker.
        delivery.retryLater(ex);
    } catch (UnsupportedEventException ex) {
        // Cách ly payload bền vững rồi mới hoàn tất
        // trách nhiệm của primary consumer theo chính sách.
        delivery.quarantine(ex);
    }
}
~~~

Đây là **pseudocode về luồng**, không phải API Java thực của mọi broker. Với Kafka, giao diện sẽ gắn việc xử lý với commit offset theo partition thay vì dùng per-message delivery ACK giống RabbitMQ.

### 22.2. Transaction của Spring chưa bao trùm broker và DB mặc định

Một method có annotation **@Transactional** thường gắn với một transaction manager cụ thể. Nếu nó cập nhật DB rồi commit offset ở broker, hai thao tác vẫn có thể **không chung một transaction**. Cần xác minh cách phối hợp transaction ở stack đang dùng, cửa sổ lỗi và yêu cầu idempotency.

Các câu hỏi triển khai:

- Method handler trả thành công khi DB đã commit hay chỉ khi đưa task vào executor?
- Nếu listener ACK ngay sau khi enqueue một task vào memory, task có thể mất khi process crash không?
- Consumer commit offset nào khi chỉ một phần batch thành công?
- Khi rebalance, listener có đợi worker xong và giữ checkpoint đúng?
- Khi một service downstream timeout, có trạng thái kiểm tra kết quả trước retry không?
- Khi DLQ publish thất bại, liệu message gốc có bị ACK mất không?

### 22.3. Không ACK ngay khi mới nhận vào hàng đợi trong memory

Ví dụ rủi ro:

~~~text
onMessage:
    localExecutor.submit(() -> updateDatabase(message))
    ACK(message)
~~~

Nếu process crash sau ACK nhưng trước khi worker ghi DB, message có thể biến mất khỏi queue/replay mặc dù chưa có side effect. Một hàng đợi trong memory **không phải lưu bền vững**.

Nếu muốn ACK sớm, phải có một điểm handoff bền vững được xác định, ví dụ ghi task vào database/job store cùng transaction, có worker khác tiếp tục thực hiện và có monitoring cho trạng thái chưa xử lý.

### 22.4. Kiểm soát thread và partition

Nếu client Kafka yêu cầu thao tác poll/commit trên consumer thread hoặc theo quy tắc thread safety riêng, không chia sẻ consumer object tùy tiện giữa worker. Có thể xử lý trong thread chính, hoặc worker pool nhưng trao kết quả completion về một nơi quản lý offset/assignment duy nhất.

Consumer có thể xử lý song song giữa partitions, nhưng khi thứ tự theo aggregate cần được giữ, các record cùng key không nên được áp dụng ngược nhau.

## 23. Kịch bản kiểm thử cần có

Kiểm thử tốt phải chủ động tạo các cửa sổ lỗi mà sản xuất thực tế có thể gặp.

### 23.1. Các kịch bản nền tảng

| Kịch bản | Hành vi cần chứng minh |
| --- | --- |
| Message hợp lệ đến một lần | Side effect đúng, ACK/checkpoint tăng sau commit |
| Message giao lại cùng eventId | Không có side effect trùng |
| Hai delivery cùng business key xử lý đồng thời | Unique constraint/invariant vẫn được giữ |
| Consumer crash trước DB commit | Message có thể retry, không mất nghiệp vụ |
| Crash sau DB commit trước ACK | Redelivery không áp dụng kết quả hai lần |
| Broker/offset commit thất bại | Không bỏ qua message chưa hoàn thành |
| DB tạm không sẵn sàng | Retry có giới hạn/backoff, không ACK nhầm |
| Payload sai schema | Quarantine/DLQ và ghi nguyên nhân, không requeue vô hạn |
| Message đến sai thứ tự | State machine/sequence gate xử lý theo hợp đồng |
| Rebalance khi worker đang chạy | Không commit offset chưa xử lý hoặc tạo ghi trùng nguy hiểm |
| Replay event cũ | Không gọi lại giao dịch bên ngoài ngoài ý muốn |
| DLQ đầy hoặc publish lỗi | Không bỏ message gốc khi chưa handoff bền vững |
| Consumer nghỉ vượt retention | Có cảnh báo và quy trình bootstrap/đối soát |

Không cần tạo test riêng chỉ để kiểm tra rằng một dòng code gọi phương thức ACK; test cần tạo ra **lỗi thực có ý nghĩa**, rồi chứng minh dữ liệu và checkpoint ở trạng thái đúng.

### 23.2. Ví dụ kiểm thử crash window

Dựng một consumer thử nghiệm có điểm ngắt chủ động:

1. Nhận event giữ hàng với eventId ổn định.
2. Commit reservation thành công.
3. Cố ý dừng process trước ACK/offset commit.
4. Khởi động consumer lại.
5. Xác minh event được redeliver theo cấu hình.
6. Xác minh tổng số reservation, tồn đã trừ và outbox kết quả vẫn đúng **một lần về mặt nghiệp vụ**.
7. Xác minh checkpoint cuối cùng tiến sau khi xử lý an toàn.

Đây là kiểm chứng giá trị thật của at-least-once + idempotency.

## 24. Runbook phục hồi consumer trong production

Khi có sự cố ở một consumer quan trọng, có thể sử dụng một runbook gồm các bước liên kết:

**Bước 1 — Xác định phạm vi:** topic/queue, group, partition, consumer version, event type, thời điểm bắt đầu và lượng dữ liệu bị ảnh hưởng.

**Bước 2 — Phân loại lỗi:** code, schema, kết nối DB, broker, downstream, quyền truy cập, message trùng, stuck transaction hoặc offset sai.

**Bước 3 — Ngăn lan rộng:** giảm concurrency/pause/stop consumer theo điều kiện phù hợp, tránh ACK các message chưa được lưu bền vững.

**Bước 4 — Ghi nhận bằng chứng:** committed offset, log end, lag, DLQ, in-flight, transaction state, event IDs, dấu xử lý ở DB và trạng thái downstream.

**Bước 5 — Chọn cách khôi phục:** retry sau sửa hạ tầng, replay từ offset, xử lý DLQ, rebuild projection từ snapshot hoặc reconciliation nghiệp vụ.

**Bước 6 — Kiểm soát side effect:** bảo đảm handler idempotent, phân biệt replay read model với giao dịch thật, có kế hoạch cho sự kiện quá hạn.

**Bước 7 — Phục hồi từng bước:** khởi động với concurrency/throughput có giới hạn và theo dõi chênh lệch dữ liệu cùng số lượng error/retry.

**Bước 8 — Xác minh end-to-end:** số lượng nghiệp vụ thực sự hoàn thành, không có trùng quan trọng, checkpoint tiến đều và lag giảm bền vững.

**Bước 9 — Ghi lại nguyên nhân:** cửa sổ lỗi, logic ACK/checkpoint, consumer assignment, data reconciliation và cải tiến cần đưa vào code/runbook.

Không đặt **auto.offset.reset=latest** hoặc xóa queue/DLQ như cách chữa triệu chứng nếu chưa hiểu và chưa chấp nhận mất dữ liệu nghiệp vụ.

## 25. Các sai lầm phổ biến

### 25.1. “ACK ngay để tăng tốc”

ACK trước DB commit có thể làm mất xử lý khi crash. Tăng throughput phải dựa vào batch, concurrency hợp lý, transaction và checkpoint an toàn; không đánh đổi bằng việc bỏ qua dữ liệu.

### 25.2. “Broker bảo đảm exactly-once nên không cần idempotency”

Exactly-once chỉ có ý nghĩa trong phạm vi một cơ chế xác định. HTTP call, database ngoài transaction broker hoặc cổng thanh toán vẫn có thể nhận lệnh lặp. Cần bảo vệ business effect.

### 25.3. “Retry tới khi thành công”

Poison message, input sai hoặc trạng thái nghiệp vụ không hợp lệ sẽ không tự sửa sau hàng nghìn lần retry. Vòng lặp như vậy có thể chiếm tài nguyên và chặn các message hợp lệ.

### 25.4. “Offset cao nhất đã xong nghĩa là mọi offset trước đã xong”

Sai khi xử lý song song. Phải commit **vị trí liên tục an toàn**, không phải max offset bất kỳ worker nào báo đã hoàn tất.

### 25.5. “Delivery tag hoặc offset là message ID nghiệp vụ”

Delivery tag có thể thay đổi theo lần giao; offset chỉ thuộc partition/log. Dùng eventId và business key phù hợp cho dedup, giữ offset cho mục tiêu checkpoint.

### 25.6. “DLQ có nghĩa nghiệp vụ đã thành công”

DLQ thường là vùng cách ly để điều tra/xử lý sau. ACK sau handoff bền vững có thể hợp lệ cho pipeline, nhưng kết quả nghiệp vụ vẫn chưa hoàn thành và cần owner chịu trách nhiệm.

### 25.7. “Consumer lag bằng 0 thì mọi thứ ổn”

Consumer có thể đã commit trước xử lý, âm thầm bỏ event hoặc chuyển hết sang DLQ. Phải đo cả kết quả nghiệp vụ và backlog cần đối soát.

### 25.8. “Event replay có thể chạy như production bình thường”

Replay có thể gửi lại email, hoàn tiền, tạo vận đơn hoặc giữ hàng nếu handler không bảo vệ side effect. Cần replay mode, idempotency, phạm vi và kiểm soát kết quả.

### 25.9. “Consumer group nào cũng dùng chung một ID”

Các nhóm có nhiệm vụ độc lập cần vị trí đọc riêng. Nếu dùng cùng group ID, chúng có thể chia message thay vì mỗi nhóm nhận đủ event như dự tính.

### 25.10. “Không cần nghĩ đến retention vì offset đã commit”

Checkpoint chỉ là vị trí; nếu record bị retention xóa, consumer không thể đọc lại. Phải thiết kế archive/snapshot và ngưỡng cảnh báo theo yêu cầu khôi phục.

## 26. Bài tập: thiết kế consumer xử lý thanh toán

Giả sử Payment Consumer đọc **PaymentRequested** từ Kafka. Mỗi event có **eventId**, **paymentRequestId**, **orderId**, **amount**, **currency** và thời điểm tạo. Consumer gửi lệnh thu tiền tới một payment provider và cập nhật trạng thái giao dịch vào DB.

Yêu cầu:

1. **Chọn delivery semantics:** giải thích vì sao at-least-once có thể phù hợp và những side effect cần chống trùng.
2. **Thiết kế định danh:** phân biệt Kafka offset, eventId, paymentRequestId và provider transaction ID. Khóa nào dùng dedup và khóa nào dùng đối soát?
3. **Mô tả transaction:** điều gì phải lưu trước khi gửi lệnh bên ngoài; khi nào cập nhật trạng thái; khi nào commit offset?
4. **Phân tích crash window:** xử lý khi provider đã thu tiền nhưng consumer crash trước khi ghi DB hoặc commit offset. Hãy tránh gọi thu tiền lần nữa nếu chưa tra cứu trạng thái.
5. **Thiết kế retry:** phân biệt provider trả từ chối do thẻ không hợp lệ với timeout mạng hoặc 503. Giới hạn retry và điều kiện chuyển reconciliation.
6. **Thiết kế checkpoint:** nếu offset 100 và 102 xong nhưng 101 đang chờ provider, commit được tới đâu?
7. **Thiết kế rebalance:** consumer A đang giữ partition và gọi provider chậm; consumer B nhận lại partition. Làm sao chặn giao dịch trùng?
8. **Thiết kế DLQ:** trường hợp nào chuyển DLQ, chứa metadata gì, ai xử lý và khi nào được replay?
9. **Định nghĩa metric:** lag, tuổi PENDING, retry count, duplicate rate, số giao dịch cần đối soát và số tiền thu có chứng cứ.
10. **Kiểm chứng:** mô tả một test thực hiện crash sau provider success để chứng minh hệ thống không thu tiền hai lần.

Một phương án đạt yêu cầu phải trả lời được **thao tác nào đã xảy ra trong DB, thao tác nào đã xảy ra ở provider, và một lần redelivery sẽ tiếp tục từ trạng thái nào**. Chỉ mô tả “gặp lỗi thì NACK” là chưa đủ.

## 27. Tóm tắt các nguyên tắc quan trọng

| Câu hỏi | Nguyên tắc |
| --- | --- |
| Khi nào ACK/commit? | Sau khi trạng thái nghiệp vụ hoặc handoff bền vững đã hoàn thành theo hợp đồng |
| Tại sao có redelivery? | Consumer/broker không xác nhận được kết quả, lỗi, lease hết hạn hoặc checkpoint chưa tiến |
| Nếu side effect đã xảy ra mà ACK chưa xong? | Cho phép replay, bảo vệ bằng idempotency và đối soát |
| Offset nói lên điều gì? | Vị trí trong log/partition, không phải định danh nghiệp vụ |
| Commit offset nào trong Kafka? | Offset tiếp theo sau chuỗi record đã xử lý an toàn liên tục |
| Vì sao Kafka và RabbitMQ khác nhau? | Kafka dùng committed offset theo group/partition, RabbitMQ dùng ACK/NACK của delivery |
| Visibility timeout có tác dụng gì? | Tạm ẩn message trong khi xử lý; hết hạn có thể giao lại |
| Có nên retry mọi lỗi? | Không; phân loại transient/permanent/unknown và giới hạn retry |
| DLQ giải quyết điều gì? | Cách ly công việc chưa thể xử lý, giữ bằng chứng và hỗ trợ replay có kiểm soát |
| Exactly-once có bảo đảm với external API? | Không tự động; cần idempotency/transaction phù hợp và reconciliation |
| Khi nào replay? | Khi có đủ lịch sử, mục tiêu rõ, handler chống side effect và kế hoạch đối soát |
| Đo hiệu quả bằng gì? | Lag, retry, DLQ, checkpoint, duplicate, age và kết quả nghiệp vụ end-to-end |

**Thông điệp cốt lõi:** Trong giao tiếp bất đồng bộ, xác nhận và checkpoint là **cơ chế ghi nhận tiến độ xử lý**, còn retry/redelivery là **cơ chế phục hồi khi chưa chắc chắn**. Để hệ thống đáng tin, phải thiết kế chúng cùng giao dịch dữ liệu, tính idempotent, thứ tự, retention, đối soát và khả năng quan sát. Mục tiêu cuối không chỉ là “broker báo đã đọc” mà là **kết quả nghiệp vụ đúng, có bằng chứng và có thể khôi phục sau lỗi**.
