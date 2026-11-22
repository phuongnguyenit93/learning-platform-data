# Giới hạn tốc độ và áp lực ngược khi bên nhận chậm trong Microservices

## Mục tiêu học tập

Giao tiếp bất đồng bộ giúp producer gửi công việc mà không phải chờ consumer hoàn tất từng tác vụ. Queue, topic và message broker có thể hấp thụ một phần tải đột biến; tuy nhiên **message đã được nhận vào hàng đợi không đồng nghĩa bên nhận có đủ năng lực xử lý**. Khi producer tạo công việc nhanh hơn tốc độ consumer hoàn thành, backlog tăng, dữ liệu cũ đi, bộ nhớ hoặc dung lượng broker có thể cạn, số lần retry có thể bùng nổ và nghiệp vụ không hoàn tất đúng hạn.

Bài học làm rõ hai cơ chế có quan hệ chặt chẽ nhưng khác nhau:

- **Giới hạn tốc độ (rate limiting):** Quy định hoặc điều tiết lượng yêu cầu/message được chấp nhận, gửi hoặc xử lý trong một khoảng thời gian; ví dụ 500 request/giây cho một API hoặc 200 message/giây tới một dependency.
- **Áp lực ngược (backpressure):** Cơ chế để bên nhận hoặc tầng trung gian báo cho phía trước rằng năng lực tiêu thụ đã chạm giới hạn, từ đó **làm chậm, tạm dừng, trì hoãn hoặc từ chối** việc tạo/thêm công việc thay vì chất đống không giới hạn.

**Ý tưởng quan trọng nhất:** Queue giúp **đệm tải**; backpressure giúp **ngăn tốc độ đầu vào vượt quá khả năng và ngân sách của toàn luồng**. Một queue không giới hạn không phải là giải pháp backpressure.

Sau bài học, người học có thể:

1. Phân biệt **throughput**, **arrival rate**, **service rate**, **concurrency**, **queue depth**, **consumer lag**, **message age**, **latency** và **backlog growth**.
2. Tính được backlog tăng/giảm theo chênh lệch tốc độ đến và tốc độ xử lý, biết khi nào cần admission control hoặc mở rộng worker.
3. Giải thích token bucket, leaky bucket, fixed/sliding window, concurrency limiter, bounded queue, pull-based demand, prefetch và pause/resume consumer.
4. Thiết kế backpressure xuyên **producer → broker → consumer → database/external API**, không chỉ ở một nơi.
5. Phân biệt **làm chậm**, **buffer có giới hạn**, **retry trì hoãn**, **từ chối**, **gộp cập nhật**, **loại bỏ có chủ đích** và **dead-letter queue** theo ý nghĩa nghiệp vụ.
6. Phân tích những đánh đổi về ordering, retry, ACK, idempotency, TTL, SLA/SLO, khả năng mở rộng và fairness.
7. Dùng metric, load test và failure injection để kiểm chứng khi consumer chậm, dịch vụ phụ thuộc lỗi hoặc lưu lượng tăng đột biến.

**Bối cảnh:** Chủ đề thuộc nhóm **Giao tiếp bất đồng bộ** trong kiến trúc Microservices. Ví dụ sử dụng hệ thống đặt hàng, xử lý thanh toán, thông báo và telemetry. Không phải mọi ví dụ đều phù hợp với mọi nghiệp vụ; đặc biệt **không được âm thầm bỏ message mang ý nghĩa giao dịch tiền bạc hoặc quyền lợi khách hàng**.

## 1. Vì sao một hàng đợi dài không chứng minh hệ thống khỏe?

Giả sử Order nhận 900 sự kiện đặt hàng mỗi giây và ghi vào broker. Một nhóm Inventory consumer chỉ xử lý bền vững 600 sự kiện mỗi giây. Trong vài phút đầu, API tạo đơn vẫn trả nhanh, broker vẫn có thể nhận message, dashboard API có vẻ xanh. Nhưng có thêm 300 message tồn đọng mỗi giây.

~~~mermaid
flowchart LR
    U["Client / Order"] -->|900 message/s| B[("Message Broker\nBacklog tăng")]
    B -->|600 message/s| I["Inventory Consumer"]
    I --> DB[("Inventory DB")]
    M["Metrics / Alert"] -. "queue age, lag, error" .-> B
    CTRL["Admission control"] -. "làm chậm hoặc từ chối" .-> U
~~~

Chênh lệch liên tục:

- Tốc độ đến **λ = 900 message/s**.
- Tốc độ xử lý bền vững **μ = 600 message/s**.
- Backlog tăng gần **λ − μ = 300 message/s**, trước khi tính retry và message lỗi.
- Sau 5 phút, backlog tăng khoảng **300 × 300 = 90.000 message**.
- Nếu payload trung bình 2 KB, riêng nội dung message tương đương khoảng **180 MB** theo đơn vị thập phân, chưa kể metadata, replication, indexes, log segment và overhead của broker.
- Nếu producer giảm xuống 200 message/s trong khi consumer vẫn xử lý 600 message/s, tốc độ xả backlog lý tưởng là **400 message/s**, cần khoảng **90.000 / 400 = 225 giây** để xả phần tồn đọng đó.

Đây là ví dụ tính toán lý tưởng: throughput ngoài thực tế phụ thuộc partition, xử lý lỗi, database locks, I/O, độ dài payload và khả năng consumer giữ tốc độ ổn định. Nhưng kết luận vẫn rõ: **ngay cả khi không message nào bị mất, người dùng có thể nhận kết quả quá muộn để nó còn giá trị**.

### Ba mục tiêu phải tách biệt

1. **Acceptance:** Hệ thống có nhận yêu cầu và lưu bền vững theo hợp đồng không?
2. **Processing:** Có đang xử lý đủ nhanh và đúng invariant không?
3. **Completion:** Nghiệp vụ có đi tới trạng thái cuối trong thời hạn người dùng chấp nhận không?

Một API trả 202 Accepted trong 20 ms nhưng đa số đơn mất 30 phút mới xác nhận không thể được coi là đáp ứng tốt nếu sản phẩm cam kết xác nhận trong vài giây. Backpressure là một phần của việc bảo vệ **completion SLO**, không chỉ bảo vệ CPU.

## 2. Khái niệm và đơn vị đo cốt lõi

### 2.1. Arrival rate và processing rate

**Arrival rate (λ):** Số message hoặc yêu cầu đến một biên trong một đơn vị thời gian; có thể đo tại API gateway, producer, broker topic, queue hoặc consumer.

**Service/processing rate (μ):** Số message được xử lý **thành công và hoàn tất** trong một đơn vị thời gian. Đếm số lần poll hoặc đọc message không tương đương số lần xử lý thành công.

Một service có thể poll được 1.000 message/s nhưng chỉ commit xong 300 message/s. Nếu đo nhầm poll rate là throughput, hệ thống có thể báo vẫn khỏe trong khi lượng công việc chưa ACK tăng mạnh.

### 2.2. Queue depth, lag, message age và end-to-end latency

| Đại lượng | Ý nghĩa | Cần cẩn thận |
|---|---|---|
| **Queue depth / ready messages** | Số công việc đang chờ ở một queue | Không phải lúc nào cũng gồm message đang được consumer giữ |
| **Unacked / in-flight messages** | Message đã giao cho worker nhưng chưa xác nhận hoàn thành | Nhiều unacked có thể phản ánh consumer chậm hoặc prefetch quá lớn |
| **Consumer lag** | Mức consumer đứng sau cuối log ở hệ thống log-based | Lag theo offset không trực tiếp là số công việc còn cần xử lý trong mọi cơ chế commit |
| **Oldest message age** | Tuổi message cũ nhất chưa hoàn thành | Quan trọng hơn depth khi SLO dựa vào thời hạn |
| **Queue wait time** | Thời gian từ lúc enqueue đến lúc bắt đầu xử lý | Có thể rất lớn dù thời gian xử lý mỗi job nhỏ |
| **Processing latency** | Thời gian worker xử lý một attempt | Không bao gồm toàn bộ thời gian chờ hoặc retry |
| **End-to-end completion time** | Từ lúc nhận yêu cầu đến lúc nghiệp vụ hoàn thành | Chỉ số gắn trực tiếp với trải nghiệm và cam kết |
| **Retry amplification** | Lượng attempt tăng thêm do lỗi/retry | Một logical operation có thể tạo nhiều attempts |
| **Saturation** | CPU, memory, pool, lock, I/O hoặc dependency gần hết năng lực | Có thể chạm trần ở DB dù CPU consumer còn thấp |

Một queue có depth 1.000 có thể là bình thường khi throughput là 100.000/s và công việc rất ngắn; cũng có thể nghiêm trọng khi consumer chỉ xử lý 2/s và message có hạn dùng 5 phút. **Không đánh giá sức khỏe chỉ từ độ dài hàng đợi.**

### 2.3. Concurrency không đồng nghĩa throughput

Concurrency là số tác vụ có thể xử lý đồng thời. Throughput là số tác vụ hoàn thành mỗi giây. Tăng concurrency giúp khi xử lý I/O-bound và dependency còn capacity; nhưng khi database bị khóa, connection pool đầy hoặc một tài nguyên dùng chung đã saturation, tăng worker có thể **giảm throughput** do tranh chấp và timeout.

Ví dụ một worker cần trung bình 100 ms xử lý một task độc lập. Theo phép xấp xỉ lý tưởng, 10 slots có thể xử lý gần 100 task/s. Tuy nhiên nếu cả 10 cùng tranh một lock DB hoặc provider chỉ chấp nhận 20 request/s, throughput thực sẽ thấp hơn đáng kể.

### 2.4. Little's Law dùng khi nào?

Với hệ thống gần trạng thái ổn định, một quan hệ hữu ích là:

**L = λ × W**

Trong đó:

- L là số công việc trung bình trong hệ thống;
- λ là throughput trung bình của công việc hoàn thành trong cùng điều kiện;
- W là thời gian trung bình một công việc ở trong hệ thống.

Nếu xử lý ổn định 100 request/s và một request tồn tại trung bình 0,25 giây, số request đang hiện diện trung bình khoảng 25.

**Không dùng Little's Law như bảo đảm khi queue liên tục phình to**: nếu arrival rate vượt năng lực xử lý trong thời gian dài, hệ thống chưa ở trạng thái ổn định; L và W sẽ tăng theo thời gian. Muốn đánh giá overload, trước tiên dùng chênh lệch arrival/completion rate và tuổi message, sau đó đo latency thực.

## 3. Rate limiting và backpressure có gì khác nhau?

**Rate limiting** thường áp đặt một giới hạn định lượng, ví dụ:

- Tối đa 100 request/giây cho một tenant.
- Gửi tối đa 50 lệnh thanh toán/giây tới một payment provider.
- Mỗi account chỉ được tạo tối đa 20 export job/phút.
- Chỉ đưa tối đa 200 event/giây vào một service đang có quota.

**Backpressure** là một vòng phản hồi dựa trên năng lực, có thể khiến rate limit thay đổi theo trạng thái của phía nhận. Khi consumer chậm, queue age tăng hoặc resource saturation xuất hiện, nguồn phát phải điều chỉnh; khi có capacity dư, nguồn có thể tăng dần.

Một hệ thống có **fixed rate limit 500/s** nhưng consumer chỉ xử lý được 100/s vẫn có thể backlog tăng mãi. Ngược lại, một consumer có cơ chế **demand/credits** và chỉ yêu cầu thêm khi có chỗ có thể backpressure tốt mà không cần mọi nơi dùng một con số giới hạn cố định.

### 3.1. Các mức phản hồi

| Phía trước nhìn thấy điều gì? | Phía trước cần làm gì? |
|---|---|
| Consumer còn capacity | Tiếp tục trong giới hạn |
| Consumer bắt đầu đầy in-flight | Chậm lại hoặc giảm prefetch/concurrency |
| Broker queue đã gần ngưỡng | Giảm tốc producer, tạm dừng intake hoặc trả lỗi admission |
| Dependency trả 429/rate limit | Tôn trọng Retry-After, giới hạn tốc độ gửi |
| Nghiệp vụ đã quá deadline | Không tiếp tục đẩy công việc vô ích; chuyển trạng thái phù hợp |
| Message lỗi không thể xử lý | Cách ly theo DLQ/runbook, không retry nóng vô hạn |
| Dữ liệu có thể mất theo contract | Có thể drop/sample/coalesce theo chính sách rõ ràng |
| Dữ liệu không được phép mất | Không âm thầm drop; cần lưu bền, từ chối có thông báo hoặc chuyển trách nhiệm |

### 3.2. Sơ đồ lan truyền áp lực

~~~mermaid
flowchart LR
    P["Producer / API"] --> Q[("Bounded queue / broker")]
    Q --> C["Consumer workers"]
    C --> D[("Database / downstream")]
    D -. "429, latency, saturation" .-> C
    C -. "ít credits / giảm prefetch" .-> Q
    Q -. "queue age, capacity, publish throttle" .-> P
    P -. "429/503/202 có điều kiện hoặc admission control" .-> U["Caller"]
~~~

Trong thực tế, broker không phải lúc nào cũng tự đẩy tín hiệu áp lực ngược tới producer. Cần quy ước riêng: producer tham chiếu lag/oldest age, gateway có admission controller, broker có quota hoặc publisher confirms, worker dừng nhận thêm khi đầy, v.v.

**Bài học:** Backpressure phải đi xuyên các biên phù hợp; chỉ giảm concurrency consumer có thể làm queue dài hơn nếu producer không hạ tốc.

## 4. Những nguyên nhân khiến bên nhận chậm

Không phải tất cả vấn đề đều do “consumer thiếu replica”. Phân loại nguyên nhân trước khi mở rộng:

| Nguyên nhân | Triệu chứng thường gặp | Hướng xử lý |
|---|---|---|
| CPU-bound xử lý nặng | CPU cao, thời gian xử lý tăng | Tối ưu thuật toán, profiling, scale worker nếu có capacity |
| Database lock/contention | CPU worker thấp hoặc vừa, query p99 tăng | Giảm song song, tối ưu transaction/index, phân vùng workload |
| External API rate limit | Nhiều 429 hoặc Retry-After | Giới hạn outbound, quota, delay, không retry nóng |
| Kết nối DB/HTTP pool cạn | Wait queue tăng, timeout pool | Bounded concurrency, chỉnh pool theo capacity thực |
| Broker partition là nút thắt | Một partition lag cao, partition khác thấp | Phân vùng theo key, xử lý hot key, giữ ordering đúng |
| Message payload lớn | Serialization/I/O tăng, network bão hòa | Giới hạn kích thước, dùng reference nếu cần, tối ưu payload |
| Event schema hoặc poison message | Một nhóm event retry liên tục | DLQ sau policy, sửa dữ liệu/hợp đồng, replay có kiểm soát |
| Consumer process restart/rebalance | Pause xử lý, lag dao động | Xem lifecycle, phân bổ partition, tránh block poll loop quá lâu |
| Downstream bị outage | Tỷ lệ lỗi tăng, retry dày | Circuit breaker, backoff, giảm intake, đối soát |
| Chính sách ACK sai | Message unacked tăng hoặc giao lặp | ACK sau commit, giới hạn prefetch, xử lý redelivery |

**Chẩn đoán năng lực bền vững** bằng completed business operations/s dưới tải ổn định, không đo số message được đọc từ broker.

## 5. Ba vị trí áp dụng điều tiết tốc độ

### 5.1. Ở producer hoặc API ingress

Đây là điểm tốt để ngăn thêm công việc trước khi gây chi phí. Ví dụ tạo báo cáo tốn tài nguyên có thể từ chối với **429 Too Many Requests** hoặc **503 Service Unavailable** và thông tin thử lại phù hợp khi đã vượt quota/capacity.

Nếu API đã trả **202 Accepted**, cần đảm bảo mức bền vững/khả năng phục hồi tương ứng. Không trả Accepted rồi âm thầm bỏ yêu cầu vì queue đầy.

Ứng dụng multi-tenant có thể giới hạn tốc độ **per tenant**, **per customer**, **per operation type** và **global** để một khách hàng không chiếm toàn bộ capacity. Cần chống việc người gọi né rate limit bằng nhiều kết nối hoặc chuyển instance.

### 5.2. Ở broker/queue

Có thể sử dụng:

- Giới hạn dung lượng queue hoặc retention;
- Producer quota, publisher flow control hoặc broker-side throttling;
- Queue/topic riêng cho workload khác nhau;
- TTL, max age và DLQ theo contract;
- Partition/consumer group phù hợp nhu cầu ordering;
- Nơi đo lag, oldest message age và publish failures.

Broker giúp cách ly producer/consumer **trong một khoảng dao động có giới hạn**, nhưng nếu mọi producer cứ gửi nhiều hơn consumer xử lý được thì cuối cùng broker cũng hết capacity hoặc thời hạn dữ liệu.

### 5.3. Ở consumer và các dependency phía sau

Consumer chỉ nhận công việc tương ứng capacity đã có. Cần giới hạn:

- Số message được giữ **in-flight**;
- Số task đang xử lý trong executor;
- Số request đồng thời tới DB/payment provider;
- Số batch được xử lý trong một thời điểm;
- Kích thước buffer cục bộ giữa poll loop và worker;
- Số lần retry có thể hoạt động song song.

Tăng concurrency khi backend đã saturation có thể làm tình hình xấu hơn. Giảm prefetch hoặc pause fetch có ích để giữ số công việc thực sự đang xử lý ổn định.

## 6. Các thuật toán giới hạn tốc độ

### 6.1. Fixed window

Cho phép tối đa N request trong một cửa sổ cố định, ví dụ 1.000 request mỗi phút.

**Ưu:** Đơn giản, dễ giải thích và lưu counter.  
**Nhược:** Có thể burst ở ranh giới cửa sổ: 1.000 request ngay cuối phút và 1.000 request đầu phút kế tiếp, tạo 2.000 request trong khoảng rất ngắn.

Phù hợp quota thô khi không yêu cầu làm mượt lưu lượng ở thời điểm ngắn.

### 6.2. Sliding window

Ước lượng hoặc đếm request trong cửa sổ trượt (ví dụ 60 giây vừa qua) để giảm burst tại ranh giới.

**Ưu:** Công bằng hơn theo thời gian trượt.  
**Nhược:** Lưu trữ/chi phí cập nhật có thể cao hơn; thuật toán xấp xỉ và thuật toán chính xác có đánh đổi khác nhau.

### 6.3. Token bucket

Bucket nạp token với tốc độ **r token/giây**, chứa tối đa **B token**. Mỗi request tiêu thụ token; nếu không còn token thì request phải chờ hoặc bị từ chối.

Ví dụ **r = 300/s, B = 600**:

- Khi rảnh đủ lâu, có thể gửi một burst tối đa gần 600 request (nếu mỗi request dùng một token).
- Khi burst đã tiêu thụ hết, tốc độ duy trì gần 300 request/s.
- Khi tải vượt giới hạn, admission controller có thể trả lỗi hoặc xếp chờ có giới hạn.

**Ưu:** Cho phép burst ngắn hợp lý trong khi kiểm soát tốc độ dài hạn.  
**Cẩn thận:** B quyết định burst pressure; r phải phù hợp capacity thực và giới hạn downstream. Bucket quá lớn vẫn có thể làm DB quá tải trong vài giây.

### 6.4. Leaky bucket / paced output

Hình dung request được nhận vào một bucket/queue và rời đi với nhịp gần cố định.

**Ưu:** Làm mượt outbound traffic, hữu ích khi provider giới hạn tốc độ.  
**Nhược:** Phải quyết định nếu bucket đầy thì chờ hay từ chối; queue vô hạn chỉ chuyển vấn đề sang latency và memory.

Một số tài liệu mô tả leaky bucket theo cách khác nhau; khi thiết kế thật cần ghi rõ đang dùng **shaping** hay **policing**, và có buffer bao nhiêu.

### 6.5. Concurrency limiter

Giới hạn tối đa **K tác vụ đồng thời**, thay vì chỉ giới hạn request/giây. Khi mỗi message cần một database connection hoặc external API call, K phản ánh lượng tài nguyên đang dùng.

Ví dụ một provider cho phép 20 request đồng thời, consumer có 100 workers thì vẫn cần **outbound concurrency limit = 20** hoặc mức phù hợp. Không nên cho 100 workers mở 100 kết nối chỉ vì message đang chờ trong broker.

**Rate và concurrency là hai chiều bổ sung:** 20 concurrency với thời gian xử lý 50 ms có throughput khác 20 concurrency với thời gian xử lý 5 giây. Khi dependency chậm, throughput có thể tự giảm dù concurrency không đổi.

### 6.6. Adaptive limits

Giới hạn có thể điều chỉnh theo CPU, latency p95/p99, tỷ lệ lỗi, queue age hoặc phản hồi từ downstream. Mô hình thường là **tăng dần khi khỏe, giảm nhanh khi thấy overload**, có hysteresis để tránh dao động liên tục.

Không để controller tự tăng concurrency chỉ vì lag cao trong khi DB đang quá tải. Cần **phân biệt thiếu worker** với **downstream saturation**. Những thuật toán phức tạp nên có fallback và ngưỡng an toàn khi metric thiếu hoặc phản hồi chậm.

## 7. Bounded queue: nơi lưu đệm phải có giới hạn

Một queue cục bộ không giới hạn có thể trông như hấp thụ tải tốt trong load test ngắn, nhưng khi producer > consumer suốt nhiều phút, memory tăng và GC pause/OOM xuất hiện.

Thiết kế đúng cần xác định:

- Giới hạn **số message**, và nếu payload lớn, cả **dung lượng byte**.
- Mức tối đa của **in-flight + queued**.
- Chính sách khi full: **block trong giới hạn**, **reject**, **pause upstream** hoặc **drop có chủ đích**.
- Tuổi tối đa để công việc còn giá trị.
- Priority/fairness và giới hạn một tenant chiếm queue.
- Nếu buffer ở memory, điều gì xảy ra khi process restart?
- Nếu buffer ở broker, broker có quota và chiến lược recovery không?

### Các chính sách khi đầy

| Chính sách | Khi nào phù hợp | Nguy cơ |
|---|---|---|
| Chờ có timeout | Caller có ngân sách thời gian và chờ hữu ích | Giữ kết nối/thread, có thể lan overload upstream |
| Tạm dừng poll/fetch | Consumer chủ động giảm intake | Cần duy trì broker heartbeat/lease và xử lý assignment |
| Trả 429/503 hoặc tín hiệu busy | Có thể yêu cầu upstream thử lại sau | Phải truyền retry-after và tránh retry storm |
| Chuyển sang durable queue | Cần tiếp nhận bền vững và xử lý sau | Queue vẫn có quota và age SLO |
| Coalesce cập nhật | Chỉ trạng thái mới nhất có giá trị | Có thể mất trung gian quan trọng nếu contract không cho |
| Sample/drop | Telemetry có thể chấp nhận mất một phần | Không dùng cho giao dịch/đơn hàng nếu chưa có quyền và hợp đồng |
| DLQ | Message lỗi vĩnh viễn hoặc retry vượt ngưỡng | Không nên dùng DLQ làm queue tràn thông thường nếu chưa có thiết kế xử lý |

**Quy tắc:** Không được tự động coi việc ném message đi là giải pháp backpressure hợp lệ. Bỏ cập nhật vị trí GPS tần suất cao theo chính sách khác hoàn toàn bỏ sự kiện PaymentCaptured.

## 8. Pull-based demand, credits và Reactive Streams

Trong mô hình **push**, producer gửi khi có dữ liệu; consumer có thể bị ngập nếu không kiểm soát. Trong mô hình **pull** hoặc **credit-based flow control**, bên nhận công bố số đơn vị công việc nó còn đủ chỗ xử lý.

Ví dụ một consumer có tối đa 40 slots:

1. Consumer yêu cầu tối đa 40 message.
2. Broker giao không quá giới hạn in-flight đã thỏa thuận.
3. Khi worker hoàn thành và ACK, một slot trở lại.
4. Consumer nhận thêm theo năng lực giải phóng.
5. Khi dependency chậm, slot được giải phóng ít hơn và tốc độ lấy message tự giảm.

Điều này giúp **không để tiến trình consumer nhận công việc nhanh hơn capacity cục bộ**, nhưng không nhất thiết làm producer chậm ngay: broker vẫn có thể backlog tăng. Vì vậy cần kết hợp **upstream rate/admission control** để bảo vệ tuổi message và dung lượng broker.

Trong **Reactive Streams**, subscriber có thể yêu cầu số phần tử qua demand, chẳng hạn chỉ request thêm khi đã xử lý được phần đang có. Tuy nhiên, các ranh giới với broker, database, callback bên ngoài hoặc queue tự viết có thể **làm mất tín hiệu backpressure** nếu adapter nhận hết rồi đổ vào buffer vô hạn.

Đừng nhầm “framework reactive” với “backpressure đã hoạt động end-to-end”. Cần lần theo tín hiệu demand thực tế từ consumer về nguồn và xem mọi bộ đệm xen giữa có giới hạn hay không.

## 9. Prefetch, poll, ACK và offset commit

### 9.1. Broker giao được bao nhiêu message trước khi consumer hoàn thành?

Một số nền tảng push-based có tham số **prefetch** hoặc số message chưa ACK tối đa. Prefetch lớn tăng throughput nếu handler nhanh, nhưng có thể khiến một consumer giữ quá nhiều message khi xử lý chậm, tăng memory và giảm fairness.

Prefetch quá nhỏ lại có thể không tận dụng đủ capacity khi latency mỗi message cao. Chọn dựa trên **throughput đo được, concurrency thực, thời gian xử lý và fairness**, không đặt theo số replica tùy tiện.

### 9.2. RabbitMQ: ACK và prefetch

Với queue kiểu AMQP có manual acknowledgment, worker nhận message, hoàn thành thao tác bền vững rồi mới ACK. Cấu hình prefetch giúp giới hạn số delivery chưa ACK theo phạm vi mà broker/client áp dụng.

Lưu ý:

- ACK trước khi business commit có thể mất công việc nếu process chết sau ACK.
- Không ACK khi xử lý thất bại có thể dẫn đến redelivery.
- NACK/requeue **ngay lập tức và liên tục** khi downstream lỗi có thể tạo hot retry loop.
- Nên phân biệt lỗi transient cần delayed retry với poison message cần DLQ.
- Unacked count cao là dấu hiệu cần xem latency xử lý, prefetch và handler.

### 9.3. Kafka: lag, partitions, polling và offset

Kafka dùng một mô hình log và consumer offset. Consumer lag thường được hiểu là chênh lệch giữa vị trí cuối log và offset đã xử lý/commit theo cách đo cụ thể. Một nhóm consumer không thể khai thác song song vượt số partition được gán trong cùng consumer group tại thời điểm đó theo mô hình partition assignment thông thường.

Cần phân biệt:

- Poll và nhận record;
- Giao record cho worker;
- Business side effect đã commit;
- Commit offset thể hiện tiến độ.

Nếu **commit offset trước khi side effect bền vững**, crash có thể làm mất việc. Nếu commit sau khi xử lý, crash trước commit có thể khiến record được xử lý lại, nên handler cần idempotent.

**Pause/resume partitions** có thể giúp một consumer ngừng lấy thêm record khi buffer cục bộ đầy. Nhưng poll loop, heartbeat, rebalance và giới hạn thời gian xử lý của client vẫn phải được quản lý đúng; không nên block consumer thread vô thời hạn rồi cho rằng broker sẽ chờ mãi.

Cấu hình và semantics chi tiết khác nhau theo broker/client/version; cần xác minh tài liệu của nền tảng đang dùng trước khi áp dụng vào production.

### 9.4. ACK không có nghĩa đã hoàn thành nghiệp vụ liên miền

Nếu Inventory ACK command sau khi lưu reservation và outbox, đây là hoàn thành **trách nhiệm xử lý command ở Inventory**. Order vẫn có thể PENDING vì chưa nhận event hoặc Payment chưa xong. Broker ACK, producer confirmation và business completion là ba mốc khác nhau.

## 10. Retry và backpressure có thể xung đột

Một hệ thống đang quá tải thường xuất hiện nhiều timeout/503/429. Nếu mỗi lỗi lập tức tạo 3 retries, lượng công việc sẽ còn tăng. Khi lỗi phần lớn do overload, retry quá mức là **positive feedback loop**: tải tăng → latency tăng → timeout tăng → retry nhiều → tải tăng.

### Chính sách retry an toàn hơn

1. Chỉ retry những lỗi có khả năng hồi phục.
2. Chỉ retry thao tác có idempotency phù hợp.
3. Dùng **exponential backoff + jitter** và tổng số attempt tối đa.
4. Có **retry budget** giới hạn phần lưu lượng retry so với original traffic.
5. Tôn trọng **Retry-After**, quota của provider và deadline nghiệp vụ.
6. Không cho producer, gateway, consumer và SDK đều retry độc lập cùng một logical operation.
7. Nếu downstream đang overload, giảm concurrency/dispatch trước khi tăng retry.
8. Khi quá hạn nghiệp vụ, xử lý theo contract; không âm thầm bỏ operation đã được cam kết.

~~~text
Nhận PaymentCommand
  ↓
Kiểm tra idempotency key và deadline
  ↓
Nếu còn capacity: thực thi một attempt
  ├─ Thành công → ghi kết quả, ACK, phát event
  ├─ Lỗi nghiệp vụ xác định → ghi REJECTED, ACK, phát event
  ├─ Lỗi tạm thời → lên lịch delayed retry, không spin nóng
  └─ Kết quả không rõ sau timeout → truy vấn/đối soát theo operationId
~~~

**DLQ không dành riêng cho overload.** Nếu provider tạm dừng 10 phút, đưa mọi payment vào DLQ ngay có thể biến sự cố tạm thành khối lượng xử lý thủ công khổng lồ. Phải định nghĩa retry window, trạng thái Pending/ReviewRequired và thời hạn hoàn thành.

## 11. Đo backlog và xác định lúc nào phải điều tiết

Một chính sách thực tế có thể dựa trên nhiều tín hiệu:

- **Oldest message age:** Có message nào sắp vượt business SLO?
- **Arrival − completion rate:** Backlog đang tăng hay giảm?
- **Consumer lag theo partition:** Có một hot partition hoặc key?
- **In-flight/queue capacity:** Số slot còn trống là bao nhiêu?
- **DB latency và connection utilization:** Dependency nào đang saturation?
- **Error/timeout/429:** Chậm do overload hay lỗi dữ liệu?
- **Retry amplification:** Mỗi logical operation tạo bao nhiêu attempts?
- **Dead-letter và stuck operations:** Có message không thể tiến tới trạng thái cuối?

### Ví dụ ngưỡng điều khiển

Giả sử dịch vụ xử lý notification có:

- Mục tiêu completion trong 60 giây;
- Normal throughput 5.000 notification/s;
- Message age tốt dưới 15 giây;
- Cảnh báo khi oldest message age vượt 30 giây kéo dài;
- Bắt đầu giảm admission cho workload ít ưu tiên khi oldest age vượt 45 giây;
- Từ chối công việc mới (hoặc defer theo policy) trước khi capacity/retention cạn.

Những ngưỡng trên chỉ minh họa. Để tránh controller bật/tắt liên tục, cần **hysteresis**: ví dụ giảm tải khi age vượt ngưỡng cao, chỉ tăng lại sau khi age xuống dưới một ngưỡng thấp và duy trì ổn định. Hành vi khi metric thiếu phải được xác định trước.

### Công thức ước lượng thời gian xả backlog

Nếu backlog **B**, trong khi nguồn tiếp tục gửi với tốc độ **λ** và consumer hoàn thành **μ**, với **μ > λ**:

**Thời gian xả lý tưởng ≈ B / (μ − λ)**

Nếu μ ≤ λ, backlog không tự giảm. Nếu backlog 60.000 và chênh lệch xả chỉ 100 message/s, cần khoảng 600 giây để hết tồn đọng, chưa kể retry và tốc độ thay đổi.

Đó là lý do **cải thiện processing rate 5% có thể không đủ** nếu arrival rate đang vượt capacity 50%. Khi quá tải nghiêm trọng, cần admission control, chia loại công việc hoặc tăng năng lực ở **đúng bottleneck**.

## 12. Đo concurrency bằng một ví dụ thực tế

Giả sử Inventory consumer xử lý bền vững 400 reservation/s; mỗi attempt mất trung bình 80 ms trong điều kiện bình thường và không có contention lớn. Theo xấp xỉ đơn giản:

**Concurrency cần thiết ≈ throughput × processing time = 400 × 0,08 = 32 slots.**

Nhưng đây không phải bảo đảm 32 workers sẽ đạt 400/s. Nếu reservation cần khóa cùng một SKU nóng, thời gian xử lý tăng với concurrency; DB có thể không chịu nổi 32 requests cùng lúc. Cần load test để tìm ngưỡng **throughput cao nhất nhưng latency/error còn chấp nhận được**.

### Vì sao tăng consumer không luôn giúp?

- Kafka consumer group chỉ phân phối parallelism theo số partition.
- Một key nóng có thể dồn nhiều message vào một partition.
- Database có thể khóa cùng bản ghi stock.
- External API có quota thấp hơn tổng số worker.
- Tăng workers làm tăng connection pool và memory.
- Retry và event duplication có thể tăng nếu ACK/offset không được kiểm soát.

**Scale đúng nơi:** Có thể cần phân hoạch workload, tối ưu transaction, xử lý theo batch, cache hợp lý, giới hạn một hot key hoặc thay đổi đặc tả nghiệp vụ; không phải chỉ tăng replica.

## 13. Chia workload, fairness và ưu tiên

Một queue trộn cả **PaymentAuthorized**, **SendWelcomeEmail** và **AnalyticsEvent** tạo rủi ro: khi email provider chậm, số email tồn đọng có thể chiếm capacity khiến công việc quan trọng bị trễ.

Có thể tổ chức:

- Queue riêng theo **mức quan trọng/SLO**;
- Consumer group riêng cho workload có resource khác nhau;
- Per-tenant quotas để tránh noisy neighbor;
- Priority queue có quy tắc tránh starvation;
- Dedicated concurrency dành cho payment/reconciliation;
- Capacity dự phòng cho health/recovery work;
- Bulkhead giữa các dependency (email SMTP không nuốt hết DB connections cho orders).

### Starvation và ưu tiên

Ưu tiên tuyệt đối cho high priority có thể khiến low priority không bao giờ được xử lý. Cần quan tâm **fairness** như weighted round-robin, bảo đảm tối thiểu cho nhóm thấp hoặc tuổi message tối đa. Không nên chỉ chọn priority mà bỏ qua completion SLO của những tác vụ còn lại.

### Hot key và ordering

Nếu cần giữ thứ tự các cập nhật cho cùng orderId, partition theo orderId có thể phù hợp. Nhưng một tài khoản/tenant tạo tải quá lớn có thể trở thành hot partition. Khi thay partition key để phân phối đều hơn, phải kiểm tra không phá invariant và yêu cầu ordering trong domain.

## 14. Coalescing, sampling và dropping: chỉ dùng khi nghiệp vụ cho phép

Một số dữ liệu có thể giảm số message mà không làm sai kết quả:

- **Telemetry nhiệt độ:** Nếu ứng dụng chỉ cần giá trị mới nhất, có thể gộp cập nhật theo sensorId trong khoảng thời gian ngắn.
- **Tín hiệu vị trí liên tục:** Có thể sample theo tần suất với hợp đồng chất lượng dữ liệu rõ.
- **Đánh dấu “đã xem” lặp:** Có thể giữ trạng thái cao nhất hoặc gộp sự kiện nếu sản phẩm cho phép.
- **Index/search projection:** Một số cập nhật trung gian có thể được gộp khi projection cuối phản ánh phiên bản mới nhất một cách đúng đắn.

Ngược lại, với **PaymentCaptured**, **RefundIssued**, **InventoryAdjusted** hoặc dữ liệu phải kiểm toán, việc drop/coalesce sai có thể gây sai tài sản, sổ sách hoặc pháp lý. Nếu công việc không thể tiếp nhận, phải phản hồi lỗi hoặc lưu bền theo hợp đồng và duy trì trạng thái để đối soát.

### Quy tắc quyết định

Trước khi giảm dữ liệu, hỏi:

1. Một message là **sự kiện có giá trị lịch sử** hay chỉ là **bản cập nhật trạng thái mới nhất**?
2. Nếu bỏ message trung gian, kết quả cuối có còn đúng không?
3. Ai được quyền chấp nhận tỷ lệ mất dữ liệu?
4. Consumer có dùng message đó để kích hoạt side effect không?
5. Có nghĩa vụ audit, replay hoặc đối soát không?
6. TTL hết hạn nên dẫn đến trạng thái nào?

Không dùng “backpressure” làm tên gọi đẹp cho **mất dữ liệu âm thầm**.

## 15. TTL, deadline và công việc đã hết giá trị

Một message có thể đến consumer sau khi mục tiêu nghiệp vụ không còn ý nghĩa. Ví dụ một yêu cầu gửi OTP sau 10 phút, trong khi OTP chỉ có hiệu lực 2 phút. Xử lý đầy đủ sau hạn vừa lãng phí capacity vừa có thể gây hiểu nhầm.

Phải phân biệt:

- **Broker TTL/retention:** Message tồn tại được bao lâu trong hệ thống lưu trữ.
- **Business deadline:** Operation còn được phép bắt đầu/hoàn tất đến khi nào.
- **Reservation expiry:** Trạng thái nghiệp vụ có thể hết hiệu lực theo rule.
- **Cancellation:** Tín hiệu yêu cầu dừng công việc không còn cần thiết.

Với job hết hạn, có thể đánh dấu EXPIRED/REJECTED theo state machine và ACK message sau khi lưu trạng thái tương ứng. Nhưng với payment đã được provider xử lý, hết hạn chờ không có nghĩa charge chưa xảy ra; vẫn phải query/reconcile thay vì bỏ qua.

### Cẩn thận khi drop expired message ở broker

Nếu broker tự loại bỏ message hết TTL, cần biết ai sẽ cập nhật trạng thái nghiệp vụ đang PENDING. Một message biến mất không tự động chuyển Order sang FAILED theo hợp đồng. Có thể cần expiration event, dead-letter routing, scheduled reconciliation hoặc cơ chế workflow có deadline riêng.

## 16. ACK, idempotency và kết quả không chắc chắn

Khi consumer bị chậm, tăng retry hoặc thay đổi ACK timing dễ làm tăng message lặp.

Một quy trình đúng thường gồm:

1. Nhận message mang **eventId/messageId** và **business operationId**.
2. Kiểm tra message đã xử lý hoặc operation đang/đã hoàn tất chưa.
3. Thực thi logic và side effect theo transaction boundary hợp lệ.
4. Lưu trạng thái cùng dấu vết idempotency.
5. Công bố event kết quả qua outbox hoặc cơ chế bền vững phù hợp.
6. ACK/commit offset chỉ sau mốc hoàn thành trách nhiệm cục bộ.

### Kịch bản crash sau commit

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Database
    B->>C: Message M
    C->>D: Commit trạng thái + processedId
    D-->>C: Commit OK
    Note over C: Consumer crash trước ACK
    B->>C: Redelivery M
    C->>D: Kiểm tra processedId
    D-->>C: Đã xử lý
    C-->>B: ACK M
~~~

Nếu consumer không idempotent, lần redelivery có thể trừ stock hoặc charge thêm lần nữa. Đảm bảo **at-least-once delivery** không tự đảm bảo **exactly-once business effect**.

### Transactional outbox

Producer hoặc consumer có thể cần lưu business state và event cần phát trong cùng một transaction cục bộ:

~~~text
BEGIN TRANSACTION
  UPDATE order SET status = 'PENDING' WHERE id = 'O-101'
  INSERT INTO outbox(eventId, eventType, payload, state)
COMMIT

Relay:
  đọc outbox chưa phát
  publish
  ghi nhận đã phát
~~~

Relay có thể publish lặp nếu crash sau publish nhưng trước khi đánh dấu, nên downstream vẫn cần dedup/idempotency. Outbox không giải quyết backpressure trực tiếp; outbox backlog cũng phải có capacity, age metrics và policy khi broker không nhận thêm.

## 17. Thiết kế admission control cho API nhận công việc

Một API async thường trả **202 Accepted** khi nhận công việc nền. Điều này tạo trách nhiệm: hệ thống phải có nơi lưu bền và kế hoạch xử lý trong điều kiện capacity đã tuyên bố.

### Mô hình đơn giản

~~~mermaid
flowchart TD
    R["POST /reports"] --> A{"Auth, quota, input hợp lệ?"}
    A -- "Không" --> X["4xx phù hợp"]
    A -- "Có" --> C{"Có capacity / deadline khả thi?"}
    C -- "Không" --> T["429/503 + Retry-After phù hợp"]
    C -- "Có" --> D["Commit job PENDING + outbox"]
    D --> O["202 Accepted + jobId/statusUrl"]
    O --> W["Worker xử lý khi có slots"]
~~~

Không nên quyết định admission bằng CPU tức thời duy nhất. Nếu queue đã có hàng triệu job quá hạn nhưng CPU hiện thấp do DB outage, tiếp nhận thêm vô hạn không phải hành vi đúng.

### Rate limit theo từng tenant và global

Có thể đặt hai lớp:

- **Per tenant:** Ví dụ mỗi tenant tối đa 50 report jobs/phút và tối đa 5 jobs đang chạy.
- **Global:** Ví dụ toàn service tối đa 500 jobs/phút và 40 jobs đồng thời.
- **Capacity-aware:** Khi oldest age hoặc p99 vượt ngưỡng, giảm mức intake một cách có kiểm soát.

Các con số minh họa. Công bằng không chỉ về số request mà còn về **chi phí mỗi request**: một job xuất báo cáo cho 10 triệu bản ghi tốn hơn một job 100 bản ghi. Có thể cần weighted quota hoặc ước tính cost units.

### Idempotency khi caller retry admission

Client có thể timeout trước khi nhận 202; server có thể đã lưu job. Nếu client retry với cùng logical request, server cần trả cùng jobId/status thay vì tạo job trùng. Nếu server chưa nhận được yêu cầu thì lần retry tạo mới hợp lệ. Hợp đồng idempotency phải cho phép phân biệt hai tình huống.

## 18. Java ví dụ: bounded executor cho consumer

Một cách bảo vệ consumer là giới hạn số worker và queue nội bộ. Ví dụ minh họa bằng Java:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class BoundedConsumerWorkers {
    private final ThreadPoolExecutor pool = new ThreadPoolExecutor(
        8,
        8,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(200),
        new ThreadPoolExecutor.AbortPolicy()
    );

    public boolean trySchedule(Runnable work) {
        try {
            pool.execute(work);
            return true;
        } catch (RejectedExecutionException full) {
            // Không nuốt message hoặc xác nhận ACK khi chưa xử lý.
            // Caller cần tạm dừng nhận thêm / trì hoãn phù hợp.
            return false;
        }
    }

    public void close() {
        pool.shutdown();
    }
}
~~~

Trong ví dụ:

- Tối đa 8 tasks chạy trong pool tại một thời điểm.
- Queue trong memory tối đa 200 tasks chờ.
- Khi đầy, **AbortPolicy** báo từ chối, thay vì tăng buffer vô hạn.
- Hàm trả false không có nghĩa message phải bị bỏ. Broker adapter chịu trách nhiệm **pause, defer, requeue có trì hoãn hoặc trả tín hiệu overload** theo semantics của transport.

**Điểm quan trọng:** Bounded executor chỉ bảo vệ tiến trình. Nếu broker vẫn nhận hàng triệu message, phải có policy broker + producer/admission control. Nếu process chết, những task đã đưa vào memory queue có thể mất; broker chỉ có thể redeliver khi ACK và offset được quản lý đúng.

### Pseudocode adapter consumer

~~~text
onBrokerMessage(message):
    if businessDeadlineExpired(message):
        persistBusinessExpiryIfApplicable(message)
        ackOnlyAfterDurableHandling(message)
        return

    admitted = boundedWorkers.trySchedule(() => {
        try:
            processIdempotently(message)
            ackOnlyAfterDurableHandling(message)
        catch TransientFailure:
            scheduleDelayedRetryWithBudget(message)
        catch PermanentInvalidMessage:
            quarantineOrDLQ(message)
    })

    if not admitted:
        pauseOrReduceFetch()
        deferDeliverySafely(message)
        recordBackpressureMetric()
~~~

Code trên diễn tả trách nhiệm, không phải API hoàn chỉnh. Tùy broker, **deferDeliverySafely** có thể cần NACK không requeue nóng, pause partition, giới hạn unacked, hoặc không nhận message ngay từ đầu. Tránh việc ACK quá sớm rồi mất message, cũng tránh worker gọi lại đồng bộ liên tục khi nguồn phụ thuộc vẫn quá tải.

### Vì sao không luôn dùng CallerRunsPolicy?

Với Java executor, CallerRunsPolicy có thể làm **thread gọi execute chạy task ngay** khi pool/queue đầy. Điều này tạo một dạng phản áp lực lên caller nếu caller có thể block hợp lý. Nhưng nếu caller là **Kafka poll loop**, thread phục vụ heartbeat hoặc một request thread có deadline rất ngắn, chạy tác vụ nặng ngay tại caller có thể gây rebalance, timeout hoặc giữ request lâu ngoài ý muốn. Không nên chọn một rejection policy chỉ từ tên gọi; phải xét vai trò thread gọi và semantics nguồn.

## 19. Ví dụ rate limit token bucket bằng pseudocode

~~~text
config:
    refillRate = 300 tokens per second
    capacity = 600 tokens
    tokens = 600
    lastRefillAt = monotonicNow()

tryAdmit(cost = 1):
    now = monotonicNow()
    elapsed = max(0, now - lastRefillAt)
    tokens = min(capacity, tokens + refillRate * elapsed)
    lastRefillAt = now

    if tokens >= cost:
        tokens -= cost
        return ADMITTED

    return THROTTLED
~~~

Khi triển khai thật:

- Dùng đồng hồ monotonic để đo elapsed trong một process.
- Với nhiều API instances, cần quyết định limiter **per instance** hay **shared/distributed**; cộng quota từ nhiều instance có thể vượt global target nếu mỗi instance tự cấp toàn quota.
- Thao tác cập nhật tokens phải thread-safe/atomic theo phạm vi sử dụng.
- Một request có cost cao có thể tiêu thụ nhiều token, không nhất thiết 1 token/request.
- Nếu THROTTLED, chọn **reject/queue ngắn/Retry-After** theo API contract.
- Các limit cố định cần thay đổi khi downstream capacity và p99 latency biến động.

Đây là phác thảo thuật toán, không phải thư viện production-ready. Đặc biệt cần xử lý phân bố tải giữa instances, restart, đồng hồ, burst, fairness và giám sát.

## 20. Autoscaling consumer theo backlog: lợi ích và bẫy

Consumer scaling có thể sử dụng CPU, queue depth, consumer lag, oldest age hoặc số pending operations. Với async processing, CPU không phải lúc nào cũng phản ánh tình trạng backlog: worker có thể đang chờ external API và CPU thấp dù queue rất dài.

### Chiến lược sơ bộ

1. Đo processing throughput của một replica ở tải bền vững.
2. Đặt completion SLO, xác định tuổi message tối đa.
3. Tính backlog và lượng capacity cần để xả trước hạn.
4. Scale thêm trong giới hạn **DB/external API** chịu được.
5. Có cooldown/hysteresis, không tăng giảm replica liên tục.
6. Giữ reservation cho retry/reconciliation và workload ưu tiên.
7. Nếu không thể tăng processing capacity, **giảm producer admission**.

### Giới hạn thực tế

- Một Kafka topic có 6 partitions thường giới hạn số consumer xử lý partitions song song trong cùng group; tăng 20 replicas có thể làm nhiều replicas không được gán partition.
- Nếu consumer đang chờ một DB lock, thêm replica có thể tăng lock contention.
- Nếu provider có quota 100 request/s, tăng consumer không vượt được quota một cách hợp lệ.
- Autoscaler phản hồi có độ trễ. Với burst rất ngắn, queue có giới hạn và admission control vẫn cần thiết.
- Scale phải giữ idempotency và không phá ordering theo aggregate.

**Mục tiêu không phải queue depth = 0 bất kể giá**, mà là completion time và chi phí nằm trong giới hạn, đồng thời hệ thống phục hồi được khi bất thường.

## 21. Bảo vệ downstream service và database

Giả sử Payment provider cho phép 200 API calls/s nhưng consumer nhận 1.000 PaymentCommand/s. Nếu gửi ngay toàn bộ, provider trả 429; retry lại khiến lưu lượng tăng. Cần outbound limiter và state machine.

~~~mermaid
flowchart LR
    Q[("Payment Commands")] --> C["Payment Consumer"]
    C --> L{"Rate + concurrency permits?"}
    L -- "Có" --> P["Payment Provider"]
    L -- "Chưa" --> D["Delay / pause, giữ trạng thái PENDING"]
    P --> R["Persist result + outbox"]
    P -. "429 / Retry-After" .-> D
~~~

Các điểm cần ghi rõ:

- **Quota provider:** Theo merchant/tenant/API key hay toàn account? Rate và concurrency có thể đều bị giới hạn.
- **Thứ tự nghiệp vụ:** Một payment attempt có thể cần kết quả trước khi mở attempt mới.
- **Idempotency:** Retry cùng logical charge phải dùng cùng key/hợp đồng provider.
- **Kết quả không chắc chắn:** Timeout sau commit phải query/reconcile; không tạo charge khác.
- **Deadline/expiry:** Một payment pending quá lâu có thể yêu cầu thao tác nghiệp vụ riêng, không chỉ drop command.
- **Cách giảm tải:** Giảm tốc dispatch và admission, không tự mở rộng worker vượt quota.

**Bulkhead** giúp dành resource riêng cho từng dependency để lỗi provider không làm cạn mọi thread/connection. **Circuit breaker** có thể giảm lời gọi vô ích trong outage; nhưng nó không tự quản lý hàng triệu message đang chờ, vẫn cần backpressure và recovery.

## 22. Backpressure ở từng kiểu ứng dụng

### 22.1. Notification/email

Thường có thể trì hoãn trong một khoảng hợp lý. Giới hạn outbound theo quota SMTP/provider, retry với backoff, theo dõi oldest age. Có thể ưu tiên email xác nhận giao dịch hơn email marketing. Nếu thông báo đã quá hạn có thể vẫn cần ghi business state thay vì bỏ tùy tiện.

### 22.2. Export report

Phù hợp với durable job queue và API trả 202. Có per-user quota, giới hạn jobs đồng thời theo CPU/DB capacity, tránh vài người gửi hàng nghìn report. Worker có thể báo progress, cho cancel các bước chưa hoàn thành.

### 22.3. Analytics/telemetry

Một số telemetry có thể sample hoặc coalesce theo contract. Khi quá tải cần báo rõ tỷ lệ drop/sample; các event phục vụ audit, thanh toán hoặc security investigation có thể có yêu cầu retention khác. Không áp dụng chung chính sách drop cho mọi topic chỉ vì đều là event.

### 22.4. Inventory reservation

Không được âm thầm bỏ ReserveInventory đã được Order cam kết tiếp nhận. Có thể giới hạn số đơn mới, phân vùng theo SKU/warehouse, giữ state PENDING, bảo vệ invariants và xử lý timeout/hết hạn theo chính sách. Hot SKU có thể cần serializing updates hoặc thiết kế data contention riêng.

### 22.5. Payment processing

Rate limit thường gắn provider quota và mức rủi ro tài chính. Cần idempotency, reconciliation, expiry và trạng thái trung gian. Khi không còn capacity, admission control ở Order nên cân nhắc từ chối hoặc chấp nhận PENDING có cam kết phù hợp; không đẩy vô hạn rồi mất khả năng kiểm soát.

### 22.6. CDC và projection

Nếu consumer projection lag, read model có thể stale. Cần đo độ trễ dữ liệu, cân nhắc tăng consumer hoặc tối ưu bulk apply, theo dõi retention để tránh mất event chưa đọc. Coalescing cập nhật phải giữ semantics của event stream và khả năng rebuild projection.

## 23. Observability: biết overload bắt đầu từ đâu

Một dashboard đủ hữu ích nên gồm tối thiểu:

| Nhóm metric | Ví dụ | Câu hỏi |
|---|---|---|
| Producer | accepted/s, rejected/s, pending admissions | Có đang nhận quá nhiều việc? |
| Broker | publish rate, queue depth, retention usage | Broker có đang đầy hoặc chậm? |
| Consumer | processed-success/s, failures/s, in-flight | Consumer có thực sự hoàn tất không? |
| Message time | oldest age, enqueue-to-start, completion latency | Công việc có còn đúng hạn? |
| Retry | attempts, retry budget used, backoff queue | Retry có khuếch đại tải không? |
| External dependency | p95/p99, 429, timeout, connection pool | Nút thắt ở provider/DB? |
| Processing distribution | lag per partition/key/tenant | Có hot partition hoặc noisy neighbor? |
| Reliability | DLQ, duplicate detection, reconciliation pending | Công việc bị mắc kẹt ở đâu? |
| Capacity | CPU, memory, GC, DB locks, disk/broker storage | Nguồn tài nguyên nào saturation? |

### Trace và correlation

Mỗi logical operation nên có operationId/correlationId; message có eventId/messageId, attempt number và thông tin producer/consumer. Truy vết async có thể cần span links hoặc context propagation qua broker. Đừng dùng orderId/customerId làm metric label có cardinality lớn; lưu định danh riêng trong structured log/trace có kiểm soát.

### Một chuỗi log minh họa

~~~text
correlationId=O-101 event=ORDER_ACCEPTED state=PENDING
correlationId=O-101 event=RESERVE_INVENTORY_ENQUEUED
consumer=inventory event=BACKPRESSURE_ACTIVE inFlight=40 queueAgeMs=18000
consumer=inventory event=RESERVATION_STARTED operationId=O-101
consumer=inventory event=RESERVATION_COMMITTED operationId=O-101
correlationId=O-101 event=INVENTORY_RESERVED
correlationId=O-101 event=ORDER_PROGRESS_UPDATED
~~~

Log cho phép phân biệt “message đã publish” với “consumer bắt đầu”, “business commit” và “Order thấy kết quả”. Cần tránh log secrets hoặc toàn bộ payload nhạy cảm.

## 24. Kịch bản kiểm thử có kiểm soát

Mỗi thử nghiệm nên ghi lại **accepted count**, **completed count**, **rejected count**, **queue age**, **retry attempts**, **side effects** và **thời gian phục hồi**. Không chỉ nhìn CPU hoặc độ dài queue.

| Kịch bản | Cách tạo tình huống | Kỳ vọng |
|---|---|---|
| Producer gửi nhanh hơn consumer | Arrival tăng từ 300 lên 900/s | Backlog được giới hạn/giám sát; admission phản ứng theo policy |
| Burst ngắn | Đột ngột gửi 2.000 messages | Bucket/buffer hấp thụ phần cho phép, không OOM |
| Downstream 429 | Provider trả rate limit | Consumer giảm dispatch và tôn trọng Retry-After |
| Database lock contention | Nhiều updates vào cùng SKU | Không tăng concurrency vô hạn; invariant vẫn đúng |
| Worker crash sau commit trước ACK | Kill process đúng thời điểm | Redelivery không nhân side effect |
| Broker publish bị lỗi | Cắt kết nối broker | Outbox/job bền, không báo Accepted giả |
| Poison message | Schema sai hoặc dữ liệu không hợp lệ | Retry có giới hạn, DLQ và cảnh báo owner |
| Consumer lag một partition | Hot partition/key | Phát hiện mất cân bằng và giữ ordering hợp lệ |
| TTL hết hạn | Làm chậm xử lý vượt business deadline | Trạng thái nghiệp vụ được cập nhật/đối soát |
| Retry storm | Nhiều timeout trong outage | Jitter, retry budget, concurrency và circuit breaker chặn khuếch đại |
| Memory queue đầy | Dừng workers, liên tục enqueue | Bounded queue reject/pause đúng, không nuốt message |
| Consumer scale tăng | Thêm replica/partition phù hợp | Throughput tăng nếu bottleneck cho phép, không tăng lỗi |

### Load test theo giai đoạn

**Giai đoạn A — Baseline:** Đo throughput hoàn thành ở tải ổn định, latency và resource bottleneck.

**Giai đoạn B — Burst:** Tăng arrival rate trong một khoảng ngắn; kiểm tra buffer, token bucket, API admission và thời gian xả.

**Giai đoạn C — Sustained overload:** Cho producer nhanh hơn consumer trong vài phút; quan sát old-message age và mốc bắt đầu throttle.

**Giai đoạn D — Dependency slowdown:** Làm chậm database hoặc provider; xác minh concurrency tự bị giới hạn thay vì tăng retry.

**Giai đoạn E — Recovery:** Hạ tốc producer, khôi phục dependency và đo thời gian xả backlog. Chứng minh business operations cuối cùng hoàn tất hoặc nhận trạng thái kết thúc rõ.

## 25. Bài thực hành: thiết kế backpressure cho Inventory

**Bài toán:** Order nhận tối đa 900 ReserveInventory commands/s trong giờ cao điểm. Inventory chỉ hoàn tất khoảng 600 commands/s trên dữ liệu thử nghiệm hiện tại; một SKU nóng có thể làm DB lock chậm. Sản phẩm muốn 95% đơn có kết quả giữ hàng trong 30 giây.

### Bước 1 — Xác định invariant và hợp đồng

- Inventory sở hữu reservation; Order không cập nhật tồn kho trực tiếp.
- ReserveInventory có operationId và idempotency key.
- Order có state INVENTORY_PENDING, RESERVED, REJECTED, REVIEW_REQUIRED.
- API tạo đơn phải phân biệt Accepted với hoàn thành.
- Định nghĩa deadline, retry và hành vi khi Inventory không đủ capacity.

### Bước 2 — Tính backlog

Dùng **arrival 900/s, completion 600/s** để ước tính mức tăng backlog sau 2, 5 và 10 phút. So sánh với dung lượng broker, retention và business deadline 30 giây.

Chỉ từ con số này, trả lời: “Nếu không giảm intake hoặc tăng completion, 95% đơn hoàn thành trong 30 giây có khả thi không?”

### Bước 3 — Đặt giới hạn nhiều tầng

- API/admission: rate/quota theo tenant và global.
- Broker: capacity, oldest-age alert và publisher throttle nếu có.
- Consumer: giới hạn in-flight, bounded workers, batch/partition phù hợp.
- DB: concurrency limit và kiểm soát hot SKU.
- Retry: exponential backoff, jitter, operationId ổn định.

### Bước 4 — Thiết kế feedback

Vẽ các trạng thái NORMAL, DEGRADED, THROTTLED và RECOVERING theo backlog age, DB latency và error rate. Có hysteresis, cooldown và lối thoát khi metric thiếu.

### Bước 5 — Tiêm lỗi

Làm chậm DB, tạo các message trùng, crash consumer trước ACK, gửi message sai schema, làm broker không nhận publish. Kiểm tra không có stock bị trừ sai, không ACK trước commit, không message bị bỏ âm thầm.

### Bước 6 — Đo kết quả

Lưu biểu đồ completed/s, arrival/s, oldest age, p95 completion latency, reject rate, retries và DB contention. Đo thời gian hệ thống phục hồi khi producer giảm xuống 200/s.

### Bước 7 — Viết ADR

So sánh:

1. Chỉ tăng consumer replicas;
2. Chỉ tăng dung lượng broker;
3. Giới hạn ingress + bounded consumer + throttled outbound + cân nhắc scale đúng bottleneck.

Giải thích vì sao phương án (3) thường bền vững hơn khi producer vượt năng lực bền vững, nhưng cần đánh giá chi phí từ chối, UX và chính sách nghiệp vụ.

**Sản phẩm:** Bảng capacity, sơ đồ backpressure, rate-limit policy, error/expiry semantics, load test, recovery plan và ADR có lý do đo được.

## 26. Câu hỏi ôn tập

1. Rate limiting khác backpressure ở điều gì? Hai cơ chế bổ sung nhau như thế nào?
2. Producer 900/s, consumer 600/s: backlog tăng bao nhiêu sau 5 phút? Nếu mỗi message 2 KB, phần payload tương ứng bao nhiêu?
3. Khi arrival rate vượt processing rate kéo dài, Little's Law có thể được áp dụng như một hệ ổn định không?
4. Vì sao queue depth bằng 1.000 có thể vừa bình thường vừa rất nguy hiểm tùy throughput và message age?
5. Nếu DB đã chạm lock contention, tăng consumer replicas có chắc tăng throughput không?
6. Token bucket với refill 300/s và capacity 600 giải quyết burst như thế nào? Nó có thể gây burst quá lớn khi nào?
7. Concurrency limiter và request/second limiter bảo vệ những tài nguyên khác nhau ra sao?
8. Tại sao buffer vô hạn là một cách che dấu overload thay vì xử lý backpressure?
9. Prefetch quá lớn ảnh hưởng tới unacked messages, memory và fairness thế nào?
10. Vì sao ACK trước business commit có nguy cơ mất công việc? ACK sau commit có thể cần idempotency vì sao?
11. Kafka lag khác queue depth kiểu push broker như thế nào? Khi nào tăng replica không còn giúp do số partition?
12. Vì sao requeue ngay lập tức khi provider trả 429 có thể tạo retry storm?
13. DLQ nên dùng cho lỗi dạng nào? Vì sao overload tạm thời không nên mặc định đẩy mọi message vào DLQ?
14. Khi nào được phép coalesce/drop? Vì sao không áp dụng cho PaymentCaptured?
15. Nếu message hết TTL nhưng Order vẫn PENDING, hệ thống cần bổ sung bước nghiệp vụ nào?
16. Tại sao một request trả 202 nhanh vẫn có thể vi phạm completion SLO?
17. Làm sao tìm ra bottleneck nằm ở consumer CPU, DB lock, partition hay external API?
18. Vì sao metric oldest message age quan trọng hơn chỉ đếm số message đang chờ?
19. Điều gì xảy ra khi người dùng retry POST tạo job sau timeout? Idempotency giải quyết tình huống nào?
20. Với một hệ thống nhiều tenant, bạn bảo vệ fairness và tránh noisy neighbor ra sao?
21. Khi source chỉ giảm tốc sau 5 phút cảnh báo, feedback loop có thể quá chậm ở đâu?
22. Vì sao phải kiểm tra cancellation, deadline và kết quả không chắc chắn trong một workflow async?
23. Phân biệt throughput poll, throughput ACK và throughput business completion.
24. Tại sao rate limit cố định không đủ khi capacity dependency thay đổi theo thời gian?
25. Bạn chọn metric, ngưỡng, rollback và các thử nghiệm gì để chứng minh hệ thống phục hồi sau overload?

## 27. Checklist triển khai

- [ ] Đã xác định **business completion SLO**, không chỉ request acceptance latency.
- [ ] Biết arrival rate, completion rate, queue depth, consumer lag và oldest message age.
- [ ] Phân biệt message đang chờ, đang xử lý và đã hoàn thành bền vững.
- [ ] Bounded queue, bounded concurrency và quota được áp dụng ở những nơi cần thiết.
- [ ] Producer/admission biết khi nào cần giảm tốc hoặc từ chối; không nhận vô hạn công việc.
- [ ] Broker có capacity/retention/lag metrics và policy khi đầy.
- [ ] Consumer prefetch, poll, pause/resume và ACK/offset commit phù hợp với transport.
- [ ] Không ACK/commit tiến độ trước khi trách nhiệm xử lý bền vững hoàn thành.
- [ ] Có idempotency cho logical business operation và xử lý duplicate/redelivery.
- [ ] Retry có budget, max attempts, backoff, jitter và tôn trọng Retry-After.
- [ ] Không tăng concurrency khi downstream đang saturation mà chưa có bằng chứng capacity.
- [ ] Có fairness theo tenant/workload, không để một hàng đợi phụ chiếm hết tài nguyên quan trọng.
- [ ] Coalescing/sampling/drop chỉ dùng khi contract nghiệp vụ cho phép và có quan sát.
- [ ] TTL/broker expiry không được làm mất trạng thái PENDING cần đối soát.
- [ ] Có state machine cho UNKNOWN, EXPIRED, RETRYING, COMPENSATION_PENDING khi phù hợp.
- [ ] Metrics và traces liên kết operationId/messageId/correlationId mà không làm metrics high-cardinality.
- [ ] Đã test burst, sustained overload, provider 429, poison message, crash before ACK và recovery.
- [ ] Đã đo thời gian xả backlog khi arrival giảm hoặc capacity tăng.
- [ ] Có runbook khi queue age vượt SLO, backlog không giảm, DLQ tăng hoặc broker gần hết dung lượng.
- [ ] Các limit và ngưỡng phản ánh chi phí, mức ưu tiên, yêu cầu bảo mật và tác động người dùng.

**Kết luận:** Với Microservices giao tiếp bất đồng bộ, queue không loại bỏ giới hạn năng lực; nó chỉ làm một phần quá tải xuất hiện **muộn hơn**. Thiết kế vững chắc cần **admission control ở đầu vào, rate/concurrency limit ở dependency, buffer có giới hạn, tín hiệu backpressure, retry có kiểm soát, xử lý idempotent, trạng thái nghiệp vụ rõ và metric end-to-end**. Khi bên nhận chậm, hệ thống phải giảm tốc, trì hoãn có giới hạn hoặc từ chối theo hợp đồng — không tích lũy vô hạn rồi hy vọng consumer sẽ bắt kịp.