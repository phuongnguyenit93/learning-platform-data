# Backpressure, vùng đệm và kiểm soát tốc độ tiêu thụ

Trong kiến trúc hướng sự kiện (**event-driven architecture**), producer có thể phát sinh sự kiện nhanh hơn tốc độ consumer xử lý. Điều này xảy ra khi lưu lượng tăng đột biến, một nhóm consumer mất khả năng hoạt động, dịch vụ downstream chậm hoặc năng lực xử lý được cấp phát không đủ. Nếu hệ thống tiếp tục nhận dữ liệu mà không kiểm soát, hàng đợi tăng liên tục, bộ nhớ và lưu trữ bị chiếm dụng, độ trễ xử lý kéo dài, retry làm tải nặng hơn và cuối cùng có thể gây lỗi dây chuyền.

**Backpressure**, **buffering** và **consumer rate control** là ba cơ chế cần được thiết kế cùng nhau. Backpressure điều tiết hoặc truyền tín hiệu rằng phía nhận không thể tiếp tục theo tốc độ hiện tại; buffering hấp thụ chênh lệch tạm thời giữa tốc độ vào và ra; rate control giới hạn tốc độ xử lý hoặc phát dữ liệu để bảo vệ tài nguyên và các dependency. Một kiến trúc sự kiện tốt phải xác định giới hạn, hành vi khi quá tải, mức dữ liệu được phép mất, thứ tự ưu tiên và cách phục hồi backlog.

Bài học thuộc chương **Kiến trúc sự kiện** của lộ trình **Cloud Architecture**. Trọng tâm là biến yêu cầu về độ tin cậy, khả năng mở rộng, hiệu năng, chi phí và vận hành thành các cơ chế có thể quan sát, kiểm thử và điều chỉnh. Sau bài học, bạn có thể:

- Phân biệt backpressure, buffering, throttling, rate limiting và load shedding.
- Đo chênh lệch giữa tốc độ producer và consumer, ước tính backlog và thời gian xử lý hết hàng đợi.
- Chọn buffer trong bộ nhớ, queue bền vững, log phân vùng hoặc kho lưu trữ phù hợp.
- Thiết kế consumer concurrency, batch size, polling, pull/push và rate limit.
- Xử lý queue đầy, consumer chậm, downstream lỗi, poison message và retry storm.
- Thiết kế backpressure theo từng tầng, kể cả khi producer không thể tạm dừng.
- Đặt SLO cho queue age, consumer lag, throughput và thời gian phục hồi.
- Đánh giá chi phí lưu trữ, compute và độ phức tạp vận hành của chiến lược điều tiết.

## 1. Vì sao cần kiểm soát dòng sự kiện?

Một hệ thống có thể hoạt động tốt ở tải bình thường nhưng thất bại khi lưu lượng tăng nhanh. Ví dụ nền tảng đặt thuê thiết bị phát ra 2.000 sự kiện mỗi giây khi khách đặt hàng, trong khi consumer ghi dữ liệu phân tích chỉ xử lý được 1.200 sự kiện mỗi giây. Mỗi giây backlog tăng thêm 800 sự kiện. Nếu tình trạng kéo dài, queue tiếp tục lớn lên ngay cả khi không có lỗi ở producer.

Các nguyên nhân thường gặp:

- **Burst traffic:** chương trình khuyến mãi, đầu giờ làm việc hoặc thiết bị IoT gửi dữ liệu cùng thời điểm.
- **Consumer capacity thấp:** số worker không đủ, batch nhỏ, xử lý tuần tự hoặc cấu hình CPU/RAM thấp.
- **Downstream bottleneck:** database, API đối tác, object storage hoặc dịch vụ tìm kiếm chậm.
- **Consumer failure:** deployment lỗi, credential hết hạn, network outage hoặc lỗi runtime.
- **Uneven partitioning:** một partition/key nhận nhiều dữ liệu hơn phần còn lại.
- **Retry amplification:** message lỗi bị retry nhiều lần, chiếm worker và làm giảm năng lực xử lý message tốt.
- **Unbounded buffering:** ứng dụng giữ message trong RAM hoặc queue mà không có giới hạn và chính sách khi đầy.

Một queue có thể che giấu sự mất cân bằng trong một khoảng thời gian. Nó không tạo ra năng lực xử lý vô hạn. Nếu tốc độ trung bình của producer cao hơn consumer trong thời gian dài, backlog sẽ tiếp tục tăng cho đến khi nguồn phát giảm tải, consumer tăng năng lực hoặc dữ liệu bị loại bỏ/chuyển hướng theo chính sách.

## 2. Phân biệt các cơ chế điều tiết

Những thuật ngữ liên quan thường bị dùng thay thế nhau nhưng giải quyết các vấn đề khác nhau.

| Cơ chế | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Backpressure** | Tín hiệu hoặc cơ chế truyền ngược trạng thái quá tải để nguồn phát giảm tốc, tạm dừng hoặc điều chỉnh | Consumer yêu cầu publisher chỉ gửi thêm khi đã xử lý xong một batch |
| **Buffering** | Lưu tạm dữ liệu để hấp thụ chênh lệch thời gian giữa đầu vào và đầu ra | Queue giữ message khi worker đang bận |
| **Rate limiting** | Đặt giới hạn tốc độ request/event trong một khoảng thời gian | Tối đa 500 request/giây cho một tenant |
| **Throttling** | Từ chối, trì hoãn hoặc làm chậm request khi vượt quota/năng lực cho phép | API trả 429 hoặc broker giảm tốc giao message |
| **Load shedding** | Chủ động loại bỏ hoặc từ chối một phần tải để bảo vệ hệ thống cốt lõi | Bỏ telemetry không quan trọng khi buffer gần đầy |
| **Admission control** | Quyết định có nhận thêm công việc hay không dựa trên năng lực và chính sách | Chỉ nhận job mới khi còn slot xử lý |
| **Concurrency control** | Giới hạn số tác vụ đang chạy đồng thời | Worker tối đa 32 invocation song song |
| **Batching** | Gom nhiều sự kiện thành một đơn vị xử lý | Ghi 100 record bằng một batch insert |

Các cơ chế có thể phối hợp. Rate limiting có thể giảm đầu vào; queue hấp thụ burst; consumer concurrency control bảo vệ database; backpressure truyền tình trạng quá tải ngược lại producer khi giao thức hỗ trợ. Load shedding là lựa chọn cuối cùng khi hệ thống không thể nhận toàn bộ tải và cần bảo vệ dữ liệu hoặc chức năng ưu tiên.

## 3. Mô hình tốc độ producer và consumer

Ký hiệu:

- \(\lambda\): tốc độ sự kiện đến, tính bằng events/second.
- \(\mu\): tốc độ xử lý của consumer group, tính bằng events/second.
- \(B(t)\): số message đang chờ tại thời điểm \(t\).
- \(C\): dung lượng buffer tối đa.
- \(N\): số consumer/worker đang hoạt động.
- \(S\): năng lực xử lý trung bình của một worker.

Trong trường hợp đơn giản, tốc độ thay đổi backlog gần đúng là:

\[
\frac{dB}{dt} = \lambda - \mu
\]

Khi \(\lambda > \mu\), backlog tăng. Khi \(\lambda < \mu\), backlog giảm nếu không còn yếu tố giới hạn khác. Nếu tốc độ đến và xử lý dao động, cần xem xét giá trị theo từng khoảng thời gian và cả các đỉnh ngắn hạn.

Nếu mỗi worker xử lý trung bình \(S\) sự kiện/giây và có \(N\) worker, năng lực lý thuyết:

\[
\mu \approx N \times S
\]

Đây chỉ là ước lượng ban đầu. Tăng N không nhất thiết tăng throughput tuyến tính nếu database, lock, network, API quota hoặc partition count đang là giới hạn.

### 3.1. Ví dụ backlog

Giả sử producer phát \(\lambda = 2.000\) events/giây và consumer group xử lý \(\mu = 1.200\) events/giây.

- Backlog tăng: \(2.000 - 1.200 = 800\) events/giây.
- Sau 10 phút, backlog tăng khoảng \(800 \times 600 = 480.000\) events.
- Nếu sự kiện trung bình 2 KB, payload thô phát sinh thêm khoảng 960 MB, chưa tính metadata, index, replication và overhead lưu trữ.

Nếu producer sau đó giảm xuống 600 events/giây trong khi consumer vẫn xử lý 1.200, backlog giảm 600 events/giây. Một backlog 480.000 sự kiện cần khoảng 800 giây, tức 13 phút 20 giây, để xử lý hết nếu các tốc độ giữ nguyên và không có message mới vượt năng lực.

### 3.2. Throughput trung bình có thể che giấu burst

Ví dụ producer trung bình chỉ phát 500 events/giây, nhưng mỗi phút có burst 5.000 events/giây trong 10 giây. Consumer có thể xử lý 1.000 events/giây. Buffer cần đủ hấp thụ phần chênh trong khoảng burst và consumer cần thời gian nhàn tải để xử lý hết phần tồn.

Nếu chỉ đo trung bình 1 phút, hệ thống có thể không lộ ra thời gian queue age tăng đột ngột. Do đó cần theo dõi cả tốc độ theo cửa sổ ngắn, backlog, tuổi message cũ nhất và thời gian catch-up.

## 4. Tính kích thước buffer và thời gian chịu burst

Buffer nên được thiết kế theo **mức burst, thời gian gián đoạn consumer, kích thước message và thời gian phục hồi**, không chỉ dựa vào số lượng message hiện tại.

Khi producer phát \(\lambda\) và consumer xử lý \(\mu\) trong thời gian \(T\), lượng buffer cần thêm xấp xỉ:

\[
B_{\text{needed}} = \max(0, \lambda - \mu) \times T
\]

Nếu consumer dừng hoàn toàn, \(\mu = 0\), buffer cần tối thiểu:

\[
B_{\text{needed}} = \lambda \times T
\]

Ví dụ 1.500 events/giây, consumer mất kết nối 15 phút:

\[
1.500 \times 900 = 1.350.000\ \text{events}
\]

Nếu mỗi event trung bình 4 KB, payload thô cần khoảng 5,4 GB. Khi lập dung lượng thật, phải cộng metadata, index, replication factor, retention, segment overhead, số bản sao, tốc độ ghi và phần headroom.

### 4.1. Tính thời gian buffer còn lại

Nếu buffer hiện có \(B\) message, dung lượng tối đa \(C\), và tốc độ tăng ròng \(r = \lambda - \mu > 0\), thời gian gần đúng đến khi đầy:

\[
T_{\text{full}} = \frac{C-B}{r}
\]

Ví dụ buffer hiện có 300.000 message, giới hạn 1.000.000, tốc độ tăng ròng 700 events/giây:

\[
T_{\text{full}} = \frac{700.000}{700} = 1.000\ \text{giây}
\]

Hệ thống có khoảng 16 phút 40 giây trước khi đạt giới hạn nếu tốc độ không đổi. Cảnh báo nên phát trước ngưỡng đầy đủ để operator còn thời gian điều tiết hoặc khôi phục consumer.

### 4.2. Dung lượng byte quan trọng hơn số message

Hai queue cùng có 100.000 message có thể có yêu cầu lưu trữ rất khác nhau nếu một queue chứa event 500 byte còn queue kia chứa file metadata 100 KB. Cần theo dõi:

- Message count.
- Tổng dung lượng bytes.
- Kích thước message p50/p95/p99.
- Retention và replication overhead.
- Tốc độ phát sinh dữ liệu.
- Dung lượng vật lý còn lại và giới hạn quota của broker.

Đối với tệp lớn, nên lưu object riêng và đưa reference/metadata vào queue, thay vì nhúng nội dung lớn vào message nếu nền tảng và nghiệp vụ không yêu cầu.

## 5. Buffer ở đâu và dùng loại nào?

Không phải buffer nào cũng có cùng đặc tính. Lựa chọn phụ thuộc vào việc dữ liệu có được phép mất, thời gian cần giữ, thứ tự, dung lượng, latency và khả năng vận hành.

| Loại buffer | Ưu điểm | Giới hạn/rủi ro | Trường hợp phù hợp |
| --- | --- | --- | --- |
| **In-memory queue** | Rất nhanh, triển khai đơn giản | Mất khi process/node restart; RAM hữu hạn | Workload tạm thời, dữ liệu có thể tái tạo |
| **Disk-backed local queue** | Sống qua restart của process, giảm áp lực RAM | Phụ thuộc ổ đĩa, dung lượng và độ bền node | Gateway/edge cần store-and-forward |
| **Managed message queue** | Durability, visibility/ack, retry và scale do dịch vụ cung cấp | Quota, retention, kích thước message, semantics riêng | Công việc bất đồng bộ và tách producer/consumer |
| **Distributed log/stream** | Retention, replay, partition và consumer offset | Quản lý partition, storage và consumer lag | Event stream lớn, nhiều consumer cần replay |
| **Object storage buffer** | Dung lượng lớn, chi phí lưu trữ có thể thấp | Latency cao hơn, phải quản lý manifest và lifecycle | Tệp/batch lớn, archive tạm hoặc import/export |
| **Database staging table** | Có thể kết hợp transaction và query | Tạo tải lên database, contention, cleanup | Batch nghiệp vụ nhỏ khi cần trạng thái/query |
| **Workflow/state store** | Lưu tiến trình và trạng thái từng bước | Không tối ưu cho lưu thông lượng event lớn | Quy trình nghiệp vụ dài, cần chờ và retry |

### 5.1. Buffer trong bộ nhớ không phải hàng đợi bền vững

Một queue trong RAM có thể làm ứng dụng tiếp tục nhận nhanh nhưng khi process crash, message chưa xử lý có thể mất. Nếu dữ liệu cần bảo toàn, phải có acknowledgment sau khi ghi vào vùng lưu trữ bền vững hoặc dùng broker đảm bảo persistence phù hợp.

Ngay cả queue bền vững cũng cần xác định replication, durability, retention, backup và hành vi khi broker/zone gặp sự cố. Không nên coi từ “managed queue” là bằng chứng rằng message không thể mất.

### 5.2. Store-and-forward ở biên

Một gateway tại nhà kho có thể mất Internet trong 20 phút nhưng vẫn cần nhận dữ liệu cảm biến. Gateway ghi event vào disk queue, tiếp tục xử lý tại chỗ và gửi lên cloud khi kết nối trở lại. Trong trường hợp này cần:

- Dung lượng disk đủ cho thời gian offline thiết kế.
- Quy tắc ghi khi disk gần đầy.
- Event ID và sequence để deduplicate/phát hiện thiếu.
- Retry có backoff và giới hạn tốc độ đồng bộ bù.
- Mã hóa dữ liệu tại chỗ, quản lý vòng đời file và quyền truy cập.
- Chính sách xóa sau khi cloud xác nhận ở mức yêu cầu.

## 6. Backpressure từ consumer tới producer

Backpressure hiệu quả nhất khi phía tiêu thụ có thể phản hồi năng lực thực tế tới phía phát. Hình thức cụ thể phụ thuộc giao thức.

### 6.1. Pull-based consumption

Trong mô hình pull, consumer chủ động lấy message khi sẵn sàng. Consumer có thể giảm tốc bằng cách:

- Giảm số message lấy mỗi lần.
- Giảm số request polling đồng thời.
- Giới hạn số message đang xử lý.
- Chỉ lấy batch mới sau khi hoàn tất/ack batch hiện tại.
- Tạm dừng polling khi downstream bão hòa.

Đây thường là cách trực tiếp để consumer kiểm soát tải của chính nó. Tuy nhiên, nếu client poll liên tục với batch lớn hoặc nhiều consumer không giới hạn, vẫn có thể gây quá tải.

### 6.2. Push-based delivery

Trong mô hình push, event source chủ động gửi message tới endpoint/consumer. Consumer có thể trả trạng thái chấp nhận, lỗi tạm thời hoặc throttling theo semantics nền tảng. Nhà cung cấp có thể retry, giảm tốc hoặc chuyển message sang trạng thái lỗi. Cần hiểu chính xác việc trả HTTP 429/5xx có làm event source retry hay không, retry bao lâu và có thể gây duplicate như thế nào.

### 6.3. Demand-based protocol

Một số streaming/reactive protocol cho phép subscriber yêu cầu số lượng phần tử mà nó có thể xử lý. Publisher chỉ gửi theo demand đã công bố. Kiểu backpressure này có thể giúp hạn chế buffer không kiểm soát giữa các stage, nhưng chỉ có hiệu lực khi toàn bộ chuỗi thực thi tôn trọng cơ chế demand.

### 6.4. Ví dụ luồng backpressure

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Durable Queue
    participant C as Consumer
    participant D as Database

    P->>Q: Publish event
    Q-->>P: Accepted
    C->>Q: Pull batch khi còn capacity
    Q-->>C: Batch events
    C->>D: Ghi dữ liệu
    D-->>C: Latency tăng / throttling
    C->>Q: Giảm polling và concurrency
    Note over C,Q: Backlog tăng nhưng consumer không bị quá tải thêm
    D-->>C: Capacity phục hồi
    C->>Q: Tăng xử lý dần theo giới hạn
~~~

Trong queue pull-based, producer thường không nhận trực tiếp tín hiệu từ consumer. Backpressure diễn ra ở consumer–queue; queue buffer tách producer khỏi consumer. Nếu queue sắp đầy, hệ thống có thể thêm admission control ở producer/API hoặc giảm tốc từ nguồn phát. Cần phân biệt những ranh giới này khi vẽ kiến trúc.

## 7. Kiểm soát tốc độ consumer

Tăng consumer count là một cách mở rộng, nhưng cần kiểm soát tốc độ để không làm quá tải dependency.

### 7.1. Giới hạn concurrency

Nếu mỗi worker mở một kết nối database và thực thi một transaction, số worker đồng thời không nên vượt quá năng lực connection pool, CPU và I/O của DB. Một worker group có thể đặt:

- Maximum concurrent invocations.
- Maximum inflight messages.
- Number of consumer threads.
- Connection pool size.
- Per-tenant concurrency.
- Downstream request concurrency.

Các giới hạn phải được phối hợp. Nếu function cho phép concurrency 500 nhưng DB proxy chỉ hỗ trợ 100 connection hữu ích, phần còn lại có thể chỉ chờ và tăng latency/cost.

### 7.2. Batch size

Batch lớn có thể tăng throughput do giảm overhead mỗi message và tận dụng bulk insert. Nhưng batch quá lớn tăng memory, thời gian xử lý, khả năng timeout và số message bị retry cùng lúc nếu batch thất bại.

| Batch size | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Nhỏ | Latency từng message thấp, lỗi khoanh vùng hẹp | Overhead poll/transaction lớn |
| Vừa | Cân bằng throughput và latency | Cần benchmark theo payload |
| Lớn | Tận dụng xử lý bulk, giảm số lần gọi | RAM lớn, retry nhiều dữ liệu, timeout và head-of-line blocking |

Batch phù hợp phụ thuộc event size, DB operation, timeout, ack semantics và thứ tự nghiệp vụ. Nên đo throughput và p95/p99, không chỉ số record/giây.

### 7.3. Polling interval

Poll quá thường xuyên khi queue rỗng tạo request và chi phí không cần thiết. Poll quá thưa làm tăng thời gian chờ event. Một số broker hỗ trợ long polling: request chờ tới khi có message hoặc hết thời gian quy định. Cần cân bằng latency, cost và giới hạn kết nối.

### 7.4. Token bucket và leaky bucket

**Token bucket** cấp token theo tốc độ cố định, tích lũy token tới một burst limit. Request chỉ được xử lý khi có token. Cơ chế này cho phép burst ngắn nhưng giữ tốc độ dài hạn trong ngưỡng.

**Leaky bucket** đưa request vào hàng đợi và xử lý ở tốc độ gần cố định; nếu queue đầy, request có thể bị từ chối. Nó phù hợp khi muốn làm phẳng burst nhưng có thể tăng latency.

Ví dụ token bucket:

~~~text
capacity = 100 tokens
refill_rate = 50 tokens/second

on_message(message):
    refill_tokens()

    if tokens >= cost(message):
        consume_tokens(cost(message))
        process(message)
    else:
        defer_or_reject(message)
~~~

Đây là giả mã. Trong distributed system, token bucket cần trạng thái dùng chung hoặc phân phối quota có chủ đích nếu nhiều consumer cùng áp một giới hạn toàn cục. Nếu mỗi instance tự cấp 50 token/giây, 20 instance có thể tạo tổng quota 1.000 token/giây, không phải 50.

## 8. Bảo vệ downstream và tránh retry storm

Backpressure không chỉ bảo vệ queue; nó phải bảo vệ database, API đối tác, object store và dịch vụ nội bộ mà consumer gọi.

Một downstream chậm có thể khiến worker giữ invocation lâu hơn, số concurrency tăng, connection bị chiếm và message visibility hết hạn. Broker gửi message lại trong khi lần xử lý trước có thể vẫn đang chạy, tạo duplicate và tăng tải.

Các biện pháp:

- Đặt timeout cho từng lời gọi downstream.
- Giới hạn concurrency và connection pool.
- Dùng circuit breaker khi dependency liên tục lỗi.
- Retry có exponential backoff và jitter.
- Chỉ retry lỗi tạm thời có khả năng phục hồi.
- Dùng idempotency để retry không lặp side effect.
- Tách queue theo loại workload hoặc mức ưu tiên để lỗi một nhóm không chặn nhóm khác.
- Dùng bulkhead để giới hạn tài nguyên cho dependency hoặc tenant.
- Theo dõi latency, status code, quota/throttling và connection saturation.

### 8.1. Circuit breaker và backpressure

Circuit breaker có thể mở khi tỷ lệ lỗi hoặc timeout vượt ngưỡng, ngăn consumer tiếp tục gọi dependency đang không khỏe. Khi circuit mở, consumer có thể tạm giữ message, chuyển sang retry sau, hoặc đưa một loại công việc sang xử lý khác. Cần tránh để mọi worker liên tục thử lại trong khi circuit đang mở.

Backpressure điều chỉnh tốc độ; circuit breaker cô lập dependency lỗi. Chúng bổ sung cho nhau nhưng không thay thế nhau.

### 8.2. Retry có thể làm tải tăng gấp nhiều lần

Nếu mỗi message được thử tối đa 5 lần, tỷ lệ lỗi cao khiến số lần xử lý thực tế tăng mạnh. Nếu 30% message thất bại ở mỗi lần thử độc lập, kỳ vọng số lần gọi tăng so với một lần xử lý thành công sẽ cao hơn đáng kể. Khi dependency đang lỗi theo cụm, giả định độc lập còn quá lạc quan.

Cần đo **attempts per message**, retry rate và số lần gọi downstream thay vì chỉ đo số message hoàn tất.

## 9. Queue đầy và chính sách overload

Buffer hữu hạn có thể đầy. Đây không phải trường hợp ngoại lệ mà là trạng thái phải được thiết kế trước.

Khi buffer đạt ngưỡng, tổ chức cần xác định theo mức quan trọng:

1. **Tạm dừng producer** nếu có thể truyền backpressure.
2. **Giảm tốc nguồn phát** bằng rate limit hoặc admission control.
3. **Từ chối có kiểm soát** với mã lỗi/Retry-After phù hợp để caller thử lại.
4. **Đẩy sang durable spillover storage** nếu có phương án lưu trữ đã thiết kế.
5. **Ưu tiên message quan trọng** và loại bỏ dữ liệu có thể tái tạo/không quan trọng theo chính sách.
6. **Ghi nhận sự kiện bị loại** và cảnh báo để không mất dấu dữ liệu.
7. **Từ chối công việc mới** khi không còn năng lực bảo toàn các cam kết hiện tại.

Không được âm thầm drop message nghiệp vụ bắt buộc giữ. Với dữ liệu telemetry có thể mất, cần nêu rõ sampling/drop policy, số lượng bị loại và giới hạn chất lượng dữ liệu được chấp nhận.

### 9.1. Admission control ở API

Nếu producer là client gọi API, API có thể giới hạn tốc độ theo user, tenant hoặc endpoint. Khi không thể nhận thêm, có thể trả:

- HTTP 429 Too Many Requests khi caller vượt rate/quota.
- HTTP 503 Service Unavailable khi dịch vụ tạm không thể tiếp nhận công việc.
- Header Retry-After nếu có thời điểm thử lại phù hợp.
- Một mã lỗi và correlation ID để caller theo dõi.

Chỉ trả 202 Accepted sau khi đã tiếp nhận công việc theo mức durability/semantics mà API cam kết. Nếu message chưa được ghi bền vững mà API đã báo accepted, hệ thống có thể mất công việc sau sự cố.

## 10. Backpressure trong hệ thống nhiều tầng

Một kiến trúc thực tế có thể có chuỗi: client → API → event bus → queue → function/worker → database → downstream API. Mỗi tầng có một giới hạn và một buffer riêng.

~~~mermaid
flowchart LR
    S["Sources / Clients"] --> A["API admission control"]
    A --> Q1["Durable event buffer"]
    Q1 --> C["Consumer group"]
    C --> L["Concurrency / rate limiter"]
    L --> D["Database / external dependency"]
    D -. "Latency, quota, error signals" .-> L
    L -. "Consumer demand / pause" .-> Q1
    Q1 -. "Queue age / capacity" .-> A
    A -. "429 / 503 / Retry-After" .-> S
~~~

Nếu mỗi tầng chỉ chuyển tải sang tầng tiếp theo mà không có giới hạn, quá tải sẽ lan truyền. Ví dụ API nhận nhiều request và đưa tất cả vào queue; queue tăng nhưng consumer không thể ghi DB nhanh hơn. Khi queue đầy, API phải giảm nhận hoặc từ chối thay vì tiếp tục tạo backlog không giới hạn.

### 10.1. Truyền backpressure xuyên nhiều service

Không phải mọi giao thức đều hỗ trợ truyền tín hiệu ngược xuyên toàn chuỗi. Một số hệ thống dùng control plane riêng để đọc queue depth và điều chỉnh rate; hệ khác dùng consumer pull và quota. Cần mô tả rõ:

- Tầng nào sở hữu tín hiệu quá tải?
- Ngưỡng nào kích hoạt giảm tốc?
- Tốc độ điều chỉnh nhanh hay từ từ?
- Khi tín hiệu mất, hệ thống mặc định tiếp tục hay fail closed?
- Ai quyết định ưu tiên hoặc loại bỏ công việc?
- Bao lâu thì phục hồi tốc độ sau khi downstream khỏe?

Nếu không có một tín hiệu backpressure end-to-end, vẫn có thể dùng local control ở từng tầng, nhưng cần tránh phản ứng đồng thời tạo dao động.

## 11. Autoscaling consumer và điều tiết đồng thời

Autoscaling tăng số consumer để bắt kịp backlog. Nhưng scale chỉ có hiệu quả khi downstream còn capacity và workload có thể phân phối song song.

### 11.1. Metric autoscaling

Các metric thường dùng:

| Metric | Ý nghĩa | Hạn chế |
| --- | --- | --- |
| Queue depth | Số message đang chờ | Không phản ánh tuổi message hoặc kích thước payload |
| Age of oldest message | Độ trễ của message cũ nhất | Có thể nhạy với một partition bị kẹt |
| Consumer lag | Chênh lệch offset hoặc vị trí đọc | Cần hiểu semantics của từng stream/broker |
| Processing throughput | Số message hoàn thành mỗi giây | Không nói rõ backlog có giảm không |
| Processing latency | Thời gian xử lý một message/batch | Tăng có thể do downstream hoặc payload |
| Downstream saturation | DB CPU/connection, API 429/latency | Cần dùng như giới hạn scale, không chỉ mục tiêu tăng |
| Error/retry rate | Chất lượng xử lý | Scale thêm có thể làm lỗi tệ hơn nếu lỗi do dependency |

### 11.2. Scale theo backlog mục tiêu

Nếu backlog hiện tại là \(B\), mức backlog mong muốn là \(B_t\), số worker hiện tại là \(N\), một cách ước tính đơn giản:

\[
N_{\text{new}} \approx N \times \frac{B}{B_t}
\]

Ví dụ 4 worker xử lý backlog 60.000 message, mục tiêu là 15.000 message trong cùng cửa sổ điều khiển:

\[
N_{\text{new}} \approx 4 \times \frac{60.000}{15.000} = 16
\]

Đây chỉ là khởi điểm toán học. Cần giới hạn theo max capacity, quota, DB connection, partition count và tốc độ khởi tạo worker. Nếu downstream chỉ hỗ trợ 8 worker, scale lên 16 có thể làm throughput giảm do contention.

### 11.3. Scale-up và scale-down khác nhau

Scale-up thường cần phản ứng nhanh khi backlog tăng. Scale-down nên thận trọng hơn để tránh dao động hoặc cắt worker đang xử lý. Có thể dùng:

- Cooldown và stabilization window.
- Hysteresis: ngưỡng scale-up cao hơn ngưỡng scale-down.
- Minimum capacity để xử lý tải nền.
- Maximum capacity theo downstream quota.
- Graceful shutdown và drain trước khi terminate.
- Giới hạn tốc độ tăng số worker trong mỗi chu kỳ.

### 11.4. Partition là giới hạn song song

Với distributed log có 12 partition, một consumer group thường chỉ có tối đa 12 consumer đọc partition độc lập tại cùng thời điểm nếu mỗi partition chỉ gán cho một consumer trong group. Tăng consumer lên 50 không tạo 50 luồng xử lý partition độc lập; nhiều consumer có thể idle. Nếu cần throughput cao hơn, phải xem cách partition key, số partition và bảo đảm ordering có thể thay đổi ra sao.

## 12. Công bằng giữa tenant và mức ưu tiên

Một tenant phát burst lớn có thể chiếm toàn bộ consumer capacity và làm tenant khác bị chậm. Hệ thống multi-tenant cần tránh **noisy neighbor**.

Có thể áp dụng:

- Per-tenant rate limit và quota.
- Queue riêng theo tenant hoặc theo lớp ưu tiên khi cần isolation mạnh.
- Weighted fair queuing hoặc scheduler phân bổ capacity theo trọng số.
- Giới hạn concurrency mỗi tenant.
- Admission control có xét tier/service plan.
- Giám sát queue age và failure rate theo tenant.
- Chính sách xử lý tenant có backlog bất thường hoặc gửi payload vượt hạn mức.

Không nhất thiết tạo một queue vật lý cho mọi tenant. Số lượng queue lớn tạo gánh nặng quản trị và chi phí; partition key, logical quota và scheduler có thể đủ nếu mức isolation phù hợp.

### 12.1. Ưu tiên công việc

Ví dụ phân loại:

| Mức | Loại event | Chính sách |
| --- | --- | --- |
| P0 | Lệnh an toàn/điều khiển có thời hạn nghiêm ngặt | Đường xử lý riêng, capacity bảo đảm, không bị queue báo cáo chặn |
| P1 | Giao dịch nghiệp vụ như xác nhận đơn/thanh toán | Durability và xử lý đúng ưu tiên cao |
| P2 | Thông báo và cập nhật giao diện | Có thể chậm trong khoảng đã công bố |
| P3 | Analytics, telemetry phụ trợ | Có thể batch, sampling hoặc trì hoãn theo chính sách |

Tên mức chỉ là ví dụ. Không đưa công việc P0 vào queue thông thường nếu thời hạn phản hồi và an toàn không thể đáp ứng qua cơ chế đó. Priority queue cũng có rủi ro starvation đối với mức thấp; cần quota hoặc weighted scheduling.

## 13. Xử lý poison message và hàng đợi bị kẹt

**Poison message** là message mà consumer liên tục không thể xử lý do dữ liệu sai, schema không tương thích, vi phạm invariant hoặc lỗi có tính lặp lại. Nếu cứ retry mãi, message có thể chiếm capacity và ngăn các message sau tiến triển.

Cần:

- Phân loại lỗi permanent/transient.
- Đặt max delivery count hoặc retry duration.
- Cách ly vào DLQ/quarantine sau ngưỡng.
- Lưu mã lỗi, event ID và metadata đủ điều tra.
- Có công cụ xem payload theo quyền và masking dữ liệu.
- Sửa producer/schema hoặc dữ liệu trước khi replay.
- Replay theo batch nhỏ và theo dõi tác động.
- Bảo đảm idempotency khi message đã được xử lý một phần.

Trong queue có ordering theo group/partition, một poison message có thể chặn tiến trình các message sau trong cùng nhóm. Cần hiểu semantics của broker và lựa chọn skip/quarantine/resequence có chủ đích; không tự ý bỏ qua message nếu nó đại diện cho nghiệp vụ bắt buộc.

## 14. Ordering, batch acknowledgment và checkpoint

Cách ack ảnh hưởng trực tiếp tới backpressure và độ tin cậy.

- **Ack từng message:** phạm vi retry nhỏ, nhiều thao tác ack hơn.
- **Ack theo batch:** hiệu quả hơn nhưng một lỗi batch có thể khiến nhiều message được giao lại.
- **Checkpoint theo offset:** consumer stream ghi vị trí đã xử lý; checkpoint quá sớm có thể làm mất sự kiện sau restart.
- **Visibility timeout/lease:** message tạm ẩn khi đang xử lý; nếu xử lý lâu hơn timeout, broker có thể giao lại.
- **Partition offset:** cho phép phát hiện consumer lag và replay từ vị trí đã lưu.

Khi batch chứa 100 event và event thứ 70 lỗi, cần biết 69 event trước đó đã commit chưa. Nếu tất cả được retry, consumer cần idempotency. Nếu ack riêng một phần, phải bảo đảm broker hỗ trợ đúng semantics.

Đối với workload có side effect, chỉ ack sau khi kết quả được ghi bền vững theo mức cam kết. Không ack ngay khi nhận message rồi mới xử lý trong background không được kiểm soát.

## 15. Vùng đệm và giới hạn dữ liệu trong bộ nhớ

Ứng dụng consumer có thể tạo thêm buffer nội bộ ngoài broker. Ví dụ polling 1.000 message rồi đẩy vào thread pool có queue vô hạn. Broker báo consumer đã nhận, nhưng công việc vẫn nằm trong RAM; khi process crash, tùy ack timing message có thể bị mất hoặc phải đợi visibility timeout.

Thiết kế an toàn:

- Giới hạn số message fetch mỗi lần.
- Giới hạn executor queue capacity.
- Chỉ fetch khi còn slot xử lý.
- Không giữ payload lớn lâu hơn cần thiết.
- Áp backpressure giữa các stage trong pipeline.
- Dùng disk/durable queue nếu cần giữ qua restart.
- Theo dõi memory, GC pause và số tác vụ đang chờ nội bộ.

~~~mermaid
flowchart LR
    Q["Broker queue"] --> F["Fetcher"]
    F --> B["Bounded in-flight buffer"]
    B --> W["Worker pool"]
    W --> DB["Downstream"]
    DB --> ACK["Ack / checkpoint"]
    W -. "No free slots" .-> F
~~~

Một bounded buffer tạo giới hạn rõ ràng. Khi đầy, fetcher ngừng lấy thêm message và broker tiếp tục giữ dữ liệu. Đây là backpressure cục bộ giữa fetcher và worker.

## 16. Kiểm soát tốc độ producer

Consumer control chỉ có thể giảm tốc tới mức queue/broker cho phép. Nếu producer tiếp tục phát quá nhanh, backlog vẫn tăng. Khi nguồn phát có thể điều khiển, cần truyền tín hiệu admission/rate tới producer.

Các cách:

- Token bucket theo tenant, thiết bị hoặc API key.
- Quota theo loại event và kích thước payload.
- Client SDK tôn trọng Retry-After và exponential backoff.
- Sampling cho telemetry có thể giảm mẫu.
- Batch publish để giảm overhead nhưng vẫn giới hạn batch size.
- Tạm dừng nguồn ingest không quan trọng khi buffer vượt ngưỡng.
- Lập lịch phát dữ liệu theo cửa sổ thay vì đồng loạt.

Với thiết bị IoT hoặc hệ thống bên ngoài không thể điều khiển, cần thiết kế buffer ở gateway/broker, quota, spillover hoặc drop policy cho loại dữ liệu được phép mất.

### 16.1. Không tạo vòng điều khiển dao động

Nếu hệ thống scale consumer lên ngay khi queue tăng, sau đó scale xuống ngay khi queue giảm một chút, số worker có thể dao động liên tục. Nếu producer cũng tăng tốc khi thấy consumer nhanh và giảm khi thấy chậm, hệ thống có thể dao động mạnh hơn.

Dùng cửa sổ đo, hysteresis, cooldown và giới hạn tốc độ thay đổi. Có thể làm mượt metric hoặc dùng control loop có tỷ lệ điều chỉnh vừa phải. Điều quan trọng là tránh phản ứng quá nhanh với nhiễu ngắn hạn.

## 17. Observability và SLO cho dòng sự kiện

Một queue có backlog không nhất thiết là sự cố nếu backlog nằm trong mức bình thường và tuổi message vẫn đáp ứng SLA. Ngược lại, queue depth thấp nhưng một partition bị kẹt hoặc message cũ không được xử lý có thể là sự cố nghiêm trọng.

Các metric nên theo dõi:

| Nhóm | Metric | Ý nghĩa |
| --- | --- | --- |
| Producer | Publish rate, rejected rate, publish latency | Khả năng phát và mức bị admission control |
| Queue | Depth, bytes, age of oldest message, retention headroom | Tồn đọng và thời gian trước khi hết buffer |
| Consumer | Processing rate, concurrency, duration p95/p99 | Năng lực thực tế |
| Lag | Consumer lag/offset lag, oldest unprocessed age | Khoảng cách giữa nguồn và vị trí đã xử lý |
| Reliability | Retry count, duplicate rate, DLQ count | Chất lượng giao nhận |
| Downstream | DB latency, connections, API 429/5xx | Nút thắt phía sau |
| Resource | CPU, memory, disk, network, GC | Khả năng tài nguyên |
| Recovery | Backlog drain rate, time to drain | Tốc độ phục hồi sau burst/outage |
| Cost | Broker storage, request, egress, worker duration | Chi phí toàn luồng |

### 17.1. SLO ví dụ

Một hệ thống thông báo có thể đặt mục tiêu:

- 99% message được xử lý trong vòng 60 giây.
- Message cũ nhất không vượt 5 phút trong điều kiện tải bình thường.
- Backlog từ burst thiết kế được xử lý hết trong 15 phút sau khi nguồn giảm tải.
- DLQ message được cảnh báo trong vòng 1 phút.
- Không drop event nghiệp vụ đã được API xác nhận durable.

Đây là chỉ tiêu minh họa. SLO thực tế phải dựa trên nhu cầu nghiệp vụ và khả năng hạ tầng. Với giao dịch tài chính, ngưỡng mất dữ liệu có thể bằng không ở phạm vi đã cam kết; với telemetry phụ trợ, sampling/drop có thể được chấp nhận.

### 17.2. Cảnh báo theo thời gian còn lại tới khi đầy

Thay vì chỉ cảnh báo queue depth > 80%, có thể ước tính:

\[
T_{\text{full}} = \frac{\text{capacity còn lại}}{\text{backlog growth rate}}
\]

Cảnh báo khi thời gian tới đầy nhỏ hơn thời gian cần thiết để scale, khôi phục hoặc điều tiết nguồn. Cách này thích ứng hơn khi mỗi queue có capacity và tốc độ tăng khác nhau. Nếu growth rate không ổn định, cần làm mượt hoặc dùng percentile phù hợp.

## 18. Ví dụ thiết kế: xử lý sự kiện đơn hàng trong đợt cao điểm

Giả sử nền tảng đặt thuê thiết bị nhận 3.000 event/giây trong 5 phút khi chiến dịch khuyến mãi bắt đầu. Consumer cập nhật read model và gửi thông báo; database chỉ xử lý an toàn khoảng 1.800 event/giây ở workload hiện tại.

### 18.1. Phân loại dữ liệu và đường xử lý

- Event xác nhận đơn là dữ liệu nghiệp vụ quan trọng, cần durable delivery và idempotency.
- Event analytics có thể được batch hoặc trì hoãn.
- Notification có thể chạy sau, với SLA riêng.
- Read model có thể eventual consistent trong một khoảng được công bố.
- Payment state vẫn phải được đọc/ghi qua service có thẩm quyền.

### 18.2. Tính backlog

Chênh lệch trong burst:

\[
3.000 - 1.800 = 1.200\ \text{events/giây}
\]

Trong 300 giây, backlog tăng:

\[
1.200 \times 300 = 360.000\ \text{events}
\]

Nếu sau khuyến mãi producer giảm về 600 event/giây và consumer vẫn đạt 1.800, tốc độ drain ròng là:

\[
1.800 - 600 = 1.200\ \text{events/giây}
\]

Thời gian xử lý hết backlog xấp xỉ 300 giây, tức 5 phút, nếu throughput giữ ổn định và không có retry/partition bottleneck.

### 18.3. Kiến trúc tham chiếu

~~~mermaid
flowchart TB
    P["Order producers"] --> A["API admission / rate policy"]
    A --> Q1["Durable queue: business events"]
    A --> Q2["Queue: analytics events"]
    Q1 --> C1["Order consumer group"]
    Q1 --> C2["Notification consumer"]
    Q2 --> C3["Analytics batch consumer"]
    C1 --> DB[("Transactional database / read model")]
    C2 --> EMAIL["Email/SMS provider"]
    C3 --> LAKE[("Analytics storage")]
    DB -. "DB saturation / connection metrics" .-> CTRL["Capacity controller"]
    CTRL -. "Concurrency and poll limits" .-> C1
    CTRL -. "Rate limits" .-> A
~~~

Tách queue giúp analytics không chặn đường xử lý sự kiện đơn hàng. Consumer order có giới hạn concurrency theo DB capacity; notification có rate limit theo quota email/SMS; analytics có thể batch. Producer nhận tín hiệu 429/503 hoặc retry policy khi admission control đạt ngưỡng.

### 18.4. Kịch bản lỗi

| Tình huống | Phản ứng |
| --- | --- |
| DB latency tăng | Giảm consumer concurrency/poll, circuit breaker phù hợp, cảnh báo queue age |
| Email provider trả 429 | Giảm rate gửi, backoff/jitter, DLQ theo chính sách |
| Queue analytics tăng nhanh | Batch, sampling loại dữ liệu được phép, tăng capacity lưu trữ có kiểm soát |
| Consumer deployment lỗi | Rollback, giữ message trong queue, không ack sớm |
| Một partition bị nóng | Xem lại key distribution và partition strategy |
| Buffer tiến gần giới hạn | Admission control, ưu tiên business events, spillover hoặc drop loại dữ liệu được phép |

### 18.5. Tiêu chí kiểm thử

1. Phát burst 3.000 events/giây trong 5 phút và đo backlog/bytes.
2. Giới hạn DB về năng lực 1.800 events/giây; xác nhận concurrency không gây quá tải.
3. Dừng consumer 2 phút; xác nhận queue giữ dữ liệu trong giới hạn retention.
4. Khởi động lại consumer giữa batch; xác nhận duplicate được xử lý idempotent.
5. Giả lập email provider trả 429/5xx; kiểm tra rate control và DLQ.
6. Đưa một partition vào tải lệch; kiểm tra phát hiện hot partition.
7. Đo thời gian drain backlog sau khi producer trở về mức nền.
8. Kiểm tra alert phát trước khi queue đạt giới hạn và có runbook xử lý.

## 19. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Tăng queue size nhưng không tăng/điều tiết consumer | Chỉ trì hoãn thời điểm đầy, queue age kéo dài | Tính rate gap, drain time và capacity plan |
| Queue hoặc executor không giới hạn | OOM, latency cao và crash dây chuyền | Bounded buffer, admission control và giới hạn concurrency |
| Retry ngay lập tức mọi lỗi | Retry storm và làm downstream yếu hơn | Backoff, jitter, max attempts và circuit breaker |
| Scale worker chỉ theo queue depth | Tăng worker dù DB đã bão hòa | Kết hợp backlog với downstream saturation |
| Ack trước khi xử lý bền vững | Message mất khi process crash | Ack sau commit/side effect có cơ chế khôi phục |
| Batch quá lớn | Memory pressure và retry cả lô | Benchmark batch size, thời gian và lỗi từng phần |
| Chỉ nhìn số message | Bỏ sót message lớn và dung lượng gần đầy | Theo dõi bytes, age và retention headroom |
| Bỏ qua hot partition | Tổng throughput còn dư nhưng một partition bị kẹt | Đo lag theo partition và xem lại key |
| Ưu tiên không có fairness | Tenant lớn hoặc P0 làm tenant khác starvation | Quota, weighted scheduling và per-tenant metrics |
| Drop message im lặng | Mất nghiệp vụ không phát hiện | Drop policy rõ, audit counter và alert |
| Không có DLQ owner/replay policy | Message lỗi bị bỏ quên hoặc replay sai | Runbook, retention, phân quyền và dedup |
| Scale up/down quá nhạy | Dao động worker và chi phí | Cooldown, hysteresis, stabilization window |
| Coi queue durable là backup | Mất dữ liệu khi retention/quota/region failure | Xem xét backup, replication và recovery riêng |

## 20. Quy trình thiết kế và triển khai

1. **Đo workload:** xác định producer rate, burst, message size, consumer throughput và thời gian gián đoạn thiết kế.
2. **Phân loại event:** đánh dấu dữ liệu bắt buộc giữ, dữ liệu có thể trì hoãn và loại có thể sampling/drop.
3. **Xác định SLO:** queue age, end-to-end latency, mất dữ liệu, thời gian drain và DLQ handling.
4. **Chọn buffer:** in-memory, disk, managed queue, stream hay object storage theo durability và retention.
5. **Tính capacity:** số message/bytes, headroom, replication, quota và thời gian tới đầy.
6. **Thiết kế backpressure:** pull/push/demand, admission control, producer feedback và overload behavior.
7. **Giới hạn consumer:** concurrency, batch, polling, downstream connections và per-tenant quota.
8. **Thiết kế lỗi:** timeout, retry, idempotency, ordering, poison message, DLQ và replay.
9. **Thiết kế autoscaling:** metric backlog/lag cùng downstream capacity, cooldown và max workers.
10. **Triển khai quan sát:** queue bytes/depth/age, processing rate, retry, DLQ, resource và drain time.
11. **Kiểm thử quá tải:** burst, consumer outage, downstream throttle, queue full và phục hồi.
12. **Định kỳ xem lại:** dự báo tăng trưởng, retention, quota, chi phí và chính sách ưu tiên.

## 21. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi cần trả lời |
| --- | --- |
| **Độ tin cậy** | Buffer có đủ cho outage thiết kế? Ack sau durability? Retry/idempotency/DLQ có bảo vệ message? Có kiểm thử drain và restore? |
| **Bảo mật** | Event và buffer có mã hóa? Ai có quyền đọc/replay? Payload có secret/PII? Tenant có cô lập quota và dữ liệu? |
| **Hiệu quả hiệu năng** | Throughput, queue age, p95/p99 và thời gian drain đạt mục tiêu? Batch/concurrency có phù hợp downstream? |
| **Tối ưu chi phí** | Buffer retention, replication, worker idle, retry và log volume có hợp lý? Tăng queue có tạo chi phí lưu trữ đáng kể? |
| **Khả năng vận hành** | Có metric, alert theo time-to-full, runbook queue full/DLQ, owner và capacity review? |

### Checklist nghiệm thu

- [ ] Producer rate, peak burst, message size và consumer throughput được đo hoặc ước tính có cơ sở.
- [ ] Buffer có giới hạn count/bytes, retention, durability và headroom rõ.
- [ ] Có công thức hoặc mô hình xác định thời gian tới đầy và thời gian drain.
- [ ] Backpressure/admission control có hành vi xác định khi consumer hoặc downstream chậm.
- [ ] Consumer concurrency, batch size, polling và connection pool được giới hạn.
- [ ] Retry có phân loại lỗi, backoff, jitter, max attempts và DLQ.
- [ ] Consumer idempotent; ack/checkpoint theo durability semantics.
- [ ] Hot partition, tenant fairness và priority starvation được xem xét.
- [ ] Queue đầy có chính sách pause/reject/spill/drop được phê duyệt.
- [ ] Autoscaling xét cả backlog và capacity của downstream.
- [ ] Alert theo queue age, bytes, retry, DLQ và time-to-full có owner.
- [ ] Burst, outage, throttling, restart và recovery đã được kiểm thử.

## 22. Bài tập áp dụng

Một nền tảng IoT nhận telemetry từ 25.000 thiết bị. Mỗi thiết bị gửi trung bình 1 event mỗi 5 giây, nhưng khi mạng trở lại sau outage, các thiết bị có thể gửi backlog cùng lúc. Consumer ghi dữ liệu vào database phân tích, năng lực ghi ổn định hiện tại là 7.000 events/giây. Message có kích thước trung bình 1,5 KB. Dữ liệu telemetry có thể sampling một phần, nhưng event cảnh báo an toàn phải được giữ đầy đủ.

Hãy thiết kế:

1. Tính tốc độ producer trung bình trước khi xét burst và xác định rate gap với consumer.
2. Nếu consumer ngừng 10 phút, cần buffer bao nhiêu event và dung lượng payload thô bao nhiêu?
3. Chia event thành các lớp ưu tiên nào? Loại nào được sampling hoặc drop khi buffer gần đầy?
4. Backpressure được truyền tới thiết bị/gateway ra sao? Thiết bị nào không hỗ trợ pause thì cần cơ chế nào?
5. Consumer scale theo queue depth hay queue age? Làm sao tránh scale làm database quá tải?
6. Thiết kế batch, idempotency, retry, DLQ và ordering cho cảnh báo.
7. Đặt SLO cho event alert, telemetry thông thường và thời gian drain backlog.
8. Kiểm thử kịch bản hàng loạt thiết bị reconnect và gửi dữ liệu dồn cùng lúc thế nào?

Một phương án tốt không chỉ chọn một queue lớn. Nó phân loại sự kiện theo giá trị nghiệp vụ, bảo đảm đường xử lý cảnh báo, hấp thụ backlog trong giới hạn, điều tiết consumer theo capacity database và có chính sách rõ khi buffer gần đầy.

**Điểm cốt lõi:** buffering hấp thụ chênh lệch tạm thời, backpressure và rate control giữ tốc độ trong năng lực thực tế, còn admission control/load shedding quyết định điều gì được nhận khi hệ thống quá tải. Chúng cần được thiết kế theo toàn bộ chuỗi producer–broker–consumer–downstream. Queue không tạo ra throughput vô hạn; một kiến trúc bền vững phải biết giới hạn của mình, đo được thời gian tới đầy và thời gian phục hồi, đồng thời bảo toàn đúng loại sự kiện mà nghiệp vụ cam kết.
