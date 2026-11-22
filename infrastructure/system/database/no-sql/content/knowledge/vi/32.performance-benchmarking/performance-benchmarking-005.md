# Tải đều, tải đột biến và giới hạn tốc độ gửi yêu cầu

Một hệ thống NoSQL có thể xử lý 10.000 yêu cầu mỗi giây trong giờ thấp điểm nhưng vẫn timeout hàng loạt khi có 20.000 yêu cầu dồn vào một vài giây. Ngược lại, một phép đo với 500 luồng chạy liên tục có thể báo throughput cao và latency ổn, dù khi người dùng thực tế gửi yêu cầu độc lập với thời gian phản hồi, hàng đợi sẽ phình to và p99 tăng mạnh.

Sự khác nhau nằm ở **mô hình phát sinh tải**, **cách áp giới hạn tốc độ gửi yêu cầu** và **cách đo trạng thái của hệ khi chịu tải**. Muốn kiểm chứng hiệu năng NoSQL, cần phân biệt:

- **Tải đều (steady load):** tốc độ, cơ cấu thao tác và phân bố khóa tương đối ổn định đủ lâu để quan sát cân bằng.
- **Tải đột biến (burst/spike):** số yêu cầu đến tăng nhanh trong thời gian ngắn, có thể dồn vào cùng tenant, collection, partition hoặc key.
- **Tốc độ gửi yêu cầu (offered request rate):** tốc độ nguồn tải *muốn* đưa vào hệ; không nhất thiết bằng tốc độ hệ chấp nhận hoặc hoàn tất.
- **Rate limiting/pacing:** cơ chế khống chế lượng yêu cầu được phát, được nhận hoặc được xử lý trong một khoảng thời gian.
- **Concurrency limit/backpressure:** giới hạn số công việc đồng thời và cách phản ứng khi hệ chưa xử lý kịp.
- **Độ trễ và khả năng phục hồi:** điều xảy ra với p95/p99, lỗi, backlog, retry và độ tươi của dữ liệu trước, trong và sau burst.

Bài thuộc **Database No SQL → Hiệu năng và đo tải**, tập trung vào cách lập một thí nghiệm có khả năng lặp lại, không ngộ nhận kết quả và áp dụng giới hạn tải đúng vị trí. Các số liệu, đồ thị khái niệm và cấu hình dưới đây chỉ để minh họa; chỉ số chịu tải thật phải được đo trên topology, dữ liệu và phiên bản NoSQL thực tế.

> Nguyên tắc cốt lõi: **Một generator chạy chậm vì đang chờ response không phải bằng chứng server khỏe. Một rate limiter bảo vệ server không phải bằng chứng server đủ capacity.** Phải đo riêng tải *được đề nghị*, tải *được chấp nhận*, công việc *hoàn tất*, công việc *bị từ chối*, backlog và latency từ góc nhìn caller.

---

## 1. Vì sao tải đều và tải đột biến cho kết quả khác nhau?

Giả sử một NoSQL cluster xử lý ổn định gần 2.000 operations/s cho một loại thao tác.

Tình huống A:

```text
10:00:00 — 2.000 requests/s
10:00:01 — 2.000 requests/s
10:00:02 — 2.000 requests/s
...
```

Tình huống B:

```text
10:00:00 — 200 requests/s
10:00:01 — 5.000 requests/s
10:00:02 — 5.000 requests/s
10:00:03 — 200 requests/s
...
```

Cả hai có thể có lượng yêu cầu trung bình tương tự trong một cửa sổ đủ dài. Tuy nhiên, B có thể gặp:

- Hàng đợi socket, thread pool hoặc connection pool tăng đột ngột.
- Hot partition bị throttle dù cluster còn tài nguyên tổng.
- CPU/IOPS/network đạt trần tức thời.
- Lock/CAS conflicts tăng do nhiều writers cùng key.
- Cache miss stampede.
- Retry storm sau những timeouts đầu tiên.
- Kafka/CDC consumer lag, khiến search hoặc materialized view trả dữ liệu cũ.
- GC, compaction, flush và background jobs chưa theo kịp.
- Tốc độ hoàn tất sau burst thấp hơn bình thường vì tồn đọng.

**Một giá trị trung bình RPS không mô tả hình dạng dòng yêu cầu đến.**

## 2. Tải đều không đồng nghĩa hệ không có dao động

Trong workload ổn định, vẫn có biến thiên tự nhiên:

```text
Target arrival rate: 1.000 requests/s.

Một giây có thể nhận 970 requests.
Giây tiếp theo có thể nhận 1.035 requests.
```

Điều quan trọng là:

- Tốc độ trung bình và phân bố đến không có xu hướng tăng/giảm lâu dài.
- Cơ cấu READ/WRITE/SCAN, kích thước payload và phân bố key có thể kiểm soát.
- Không còn pha khởi động làm kết quả bị méo.
- Backlog không tăng không giới hạn.
- Các tài nguyên và độ trễ được quan sát đủ lâu.
- Có thể phân biệt dao động tự nhiên với periodic work như compaction hoặc snapshot.

Trong thí nghiệm, **tải đều là điều kiện kiểm soát**, không phải giả định từng giây luôn có đúng một số yêu cầu.

## 3. Tải đột biến có nhiều hình dạng

| Kiểu tải | Hình dạng | Điều cần đánh giá |
| --- | --- | --- |
| **Spike** | Tăng gần tức thời rồi giảm | Headroom, throttle, recovery |
| **Step** | Từ 500 lên 2.000 RPS và giữ | Công suất bền vững mới |
| **Ramp** | Tăng từ từ qua nhiều mức | Điểm gãy throughput/latency |
| **Burst train** | Các xung ngắn lặp liên tiếp | Khả năng xả backlog giữa xung |
| **Microburst** | Rất nhiều requests trong vài ms | Queue/socket/partition pressure |
| **Flash crowd** | Nhiều người cùng thao tác | Skew, hot key, session cache |
| **Diurnal load** | Chu kỳ theo giờ/ngày | Scaling và peak planning |
| **Failure-induced burst** | Clients retry cùng lúc sau outage | Retry amplification |
| **Backfill burst** | Job migration/rebuild tăng đột ngột | Cạnh tranh foreground/background |
| **Catch-up burst** | Worker phục hồi và đọc queue tồn đọng | Ảnh hưởng read/write capacity |

Không thể giả rằng “burst 4× trong 30 giây” tương đương “burst 4× trong 100 mili giây”. Trong khoảng ngắn, giới hạn tạo connection, request queues, các buckets và cơ chế batching có thể chi phối kết quả.

## 4. Ba tốc độ thường bị nhầm

Giả sử trong một giây:

```text
Load generator lên lịch:  10.000 requests
API nhận hợp lệ:           8.000 requests
NoSQL hoàn tất:            6.000 requests
API/limiter từ chối:       2.000 requests
Còn in-flight/backlog:     2.000 requests
```

Các khái niệm:

**Offered rate** — \(\lambda_{\mathrm{offered}}\): lượng yêu cầu nguồn tải muốn gửi trên một đơn vị thời gian.

**Admitted/accepted rate** — \(\lambda_{\mathrm{admitted}}\): lượng yêu cầu được lớp admission chấp nhận vào pipeline.

**Completion rate** — \(\lambda_{\mathrm{completed}}\): lượng yêu cầu hoàn tất thành công hoặc kết thúc theo định nghĩa đo; cần tách success khỏi failure.

Một phương trình kiểm kê trong cửa sổ đo, nếu các nhóm không chồng nhau:

\[
N_{\mathrm{admitted}}
=
N_{\mathrm{completed}}
+
\Delta N_{\mathrm{inflight/backlog}}
\]

với điều kiện đã tính đúng backlog đầu kỳ và cuối kỳ.

Nếu chỉ hiển thị **throughput thành công** 6.000 RPS, chúng ta không biết caller đã gửi 6.000 hay 10.000 requests/s. Khi hệ quá tải, **completed throughput có thể đứng yên hoặc giảm, trong khi offered load tiếp tục tăng**.

## 5. Cần phân biệt request đến và operation xuống NoSQL

Một HTTP request có thể tạo:

```text
GET /dashboard
    -> 3 key reads
    -> 1 range query
    -> 2 cache lookups
```

Một POST có thể tạo:

```text
POST /order
    -> conditional insert
    -> transaction/ledger
    -> outbox write
```

Nếu HTTP RPS là 1.000 nhưng mỗi request thực hiện bình quân 6 NoSQL operations:

\[
\lambda_{\mathrm{db}} \approx 6.000\ \text{operations/s}
\]

Chưa tính retries, background jobs và read/write amplification.

Cần ghi rõ measurement unit:

- HTTP requests/s.
- Logical commands/s.
- Physical database operations/s.
- Reads/s và writes/s.
- Items/rows/documents per second.
- Bytes/s.
- Consumed RCU/WCU hoặc units riêng của engine.
- Query fan-out/partitions touched.
- Events consumed/s.

Một benchmark nói “NoSQL đạt 10.000 RPS” nhưng không nêu request shape là kết luận rất khó sử dụng.

## 6. Workload mở (open-loop) và đóng (closed-loop)

Đây là lựa chọn quan trọng nhất trong đo tải.

### Closed-loop: số clients/threads cố định

Mỗi virtual user:

```text
send request
wait for response
think for 100ms
send next request
```

Tốc độ tạo request phụ thuộc vào thời gian phản hồi. Khi server chậm, các clients **tự gửi ít request hơn**.

Ưu điểm:

- Mô phỏng một số hành vi tương tác thực tế.
- Dễ giới hạn concurrency.
- Hữu ích để đo capacity dưới số users đồng thời.

Nhược điểm:

- Không kiểm tra tốt một dòng arrival không phụ thuộc latency.
- Có thể che giấu overload vì generator tự giảm tốc.
- Dễ gây **coordinated omission** nếu thời gian chậm không được tính vào phân bố latency theo lời hứa của workload.

### Open-loop: gửi theo lịch arrival định trước

```text
T=0ms     request 1
T=10ms    request 2
T=20ms    request 3
T=30ms    request 4
...
```

Generator lên lịch request độc lập với kết quả các requests trước.

Ưu điểm:

- Chủ động áp 100, 1.000 hoặc 10.000 arrivals/s.
- Bộc lộ backlog và overload.
- Phù hợp kiểm tra burst và giới hạn admission.

Nhược điểm:

- Generator cũng có capacity và có thể bị trễ lịch.
- Cần giới hạn số in-flight để tránh tự hết RAM/socket.
- Phải ghi rõ khi không thể gửi đúng lịch, thay vì âm thầm giảm load.
- Cần đo latency từ **thời điểm request đáng lẽ đến** nếu muốn nhìn cả chậm lịch/phát sinh queue.

## 7. Coordinated omission: sai lệch dễ làm p99 trông đẹp

Giả sử server mất 5 giây để trả một request, và load generator chỉ gửi request tiếp theo khi request trước hoàn tất.

Trong 5 giây đó, generator **không phát những requests đã được dự kiến theo tốc độ mục tiêu**. Histogram chỉ chứa một request chậm, thay vì ghi nhận ảnh hưởng lên dòng arrivals mà workload thực tế đại diện.

Ví dụ:

```text
Target: 100 requests/s.
Server stalls: 5 seconds.

Expected arrivals during stall:
    500 requests.

Closed-loop single-client:
    may record only one request spanning stall,
    while the other 499 planned arrivals never occurred.
```

Không phải mọi closed-loop test đều sai. Sai là **diễn giải kết quả như thể đã chịu 100 arrivals/s cố định** dù phép đo không hề phát tải ấy.

Các biện pháp:

1. Chọn mô hình workload theo user behavior cần kiểm chứng.
2. Nếu cần arrival rate, dùng open-loop pacing.
3. Ghi `scheduled`, `sent`, `rejected_by_generator`, `completed`.
4. Đo end-to-end latency từ thời điểm yêu cầu được lên lịch/đến hệ, không chỉ thời gian server xử lý.
5. Kiểm tra generator lag và tài nguyên generator.
6. Nếu dùng corrected histograms, hiểu assumptions của cách hiệu chỉnh; không tự tưởng tượng các requests không hề gửi là đã có response.
7. Công bố rõ mô hình đo.

## 8. Little's Law giúp liên hệ tốc độ, latency và concurrency

Trong hệ ổn định với điều kiện áp dụng phù hợp:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số công việc trung bình trong hệ.
- \(\lambda\): tốc độ hoàn tất/đến ổn định.
- \(W\): thời gian trung bình mỗi công việc ở trong hệ.

Ví dụ:

```text
Throughput ổn định: 2.000 requests/s.
End-to-end mean latency: 50 ms = 0,05 s.
```

Số request in-flight trung bình:

\[
L = 2.000 \times 0{,}05 = 100
\]

Nếu latency tăng lên 500 ms nhưng arrival rate vẫn 2.000/s, số công việc cần giữ trong pipeline có thể tiến tới:

\[
L = 2.000 \times 0{,}5 = 1.000
\]

**Không dùng Little's Law như một lời bảo đảm khi backlog đang tăng không giới hạn**. Trong transient burst, cần xem queue dynamics và số in-flight thực.

## 9. Queue tăng khi tốc độ vào vượt công suất ra

Gọi:

- \(\lambda\): arrival rate.
- \(\mu\): service/completion capacity hữu hiệu.
- \(Q(t)\): backlog, theo một mô hình đơn giản.

Khi \(\lambda > \mu\) liên tục và chưa có admission control:

\[
\Delta Q \approx (\lambda - \mu)\Delta t
\]

Ví dụ:

```text
Incoming: 3.000 ops/s.
Server can complete: 2.000 ops/s.
Burst duration: 20 seconds.
```

Backlog có thể tăng gần:

\[
(3.000 - 2.000)\times20=20.000\ \text{operations}
\]

Nếu sau burst arrival giảm xuống 1.500 ops/s, server có năng lực xả khoảng 500 ops/s khi không có ảnh hưởng phụ, thì cần khoảng 40 giây để xả 20.000 backlog. Đây là tính toán lý tưởng hóa, **không tính timeout, retries, compaction, queue admission hoặc throughput suy giảm**.

Một hệ có thể **vượt qua burst mà không mất dữ liệu** nhưng vẫn vi phạm latency SLO vì backlog hồi phục quá chậm.

## 10. Throughput plateau không có nghĩa tải được phục vụ tốt

Một biểu đồ minh họa:

```text
Offered RPS        500  1000  1500  2000  3000  5000
Completed RPS      500  1000  1500  1900  1950  1800
p99 latency (ms)    20    30    60   180  1200  5000
Error/reject rate    0     0     0    2%   35%   64%
```

Dữ liệu chỉ là giả định.

Nếu chỉ tìm **max completed RPS**, có thể chọn 1.950 RPS dù p99 đã 1,2 giây và 35% requests bị lỗi/từ chối. Công suất sử dụng được phải được định nghĩa bằng **throughput thỏa đồng thời latency, error, freshness và correctness SLO**.

## 11. Phân biệt rate limiting, throttling, pacing và admission control

| Khái niệm | Dùng ở đâu | Tác động chính |
| --- | --- | --- |
| **Load-generator pacing** | Bên phát thử nghiệm | Tạo offered arrival rate đúng lịch |
| **Client-side rate limit** | SDK/service gọi NoSQL | Bảo vệ dependency; tránh quá tải |
| **API rate limiting** | Gateway hoặc service | Giới hạn theo tenant/user/IP/key |
| **Server-side throttling** | Database/service | Từ chối hoặc trì hoãn khi vượt capacity/quota |
| **Concurrency limit** | In-flight operations | Chặn số công việc đồng thời |
| **Admission control** | Trước queue/worker | Quyết định nhận, hoãn hoặc từ chối |
| **Backpressure** | Pipeline/queue/consumer | Buộc producer giảm tốc khi downstream chậm |
| **Load shedding** | Khi quá tải | Bỏ/từ chối ưu tiên thấp để giữ chức năng quan trọng |
| **Retry budget** | Client và worker | Giới hạn tải bổ sung từ retries |

**Giới hạn tốc độ của load generator là công cụ đo. Giới hạn tốc độ của hệ thống sản xuất là cơ chế bảo vệ.** Nếu cả hai cùng hoạt động, phải biết chỗ nào phát sinh `429`, `503` hoặc delay.

## 12. Fixed-window rate limiter và rủi ro biên cửa sổ

Một fixed-window limiter:

```text
Maximum: 100 requests each second.
Window 12:00:00–12:00:01: accept up to 100.
Window 12:00:01–12:00:02: accept up to 100.
```

Một client có thể gửi:

```text
12:00:00.999 -> 100 requests.
12:00:01.001 -> 100 requests.
```

Tức **200 requests trong khoảng 2ms quanh ranh giới**, dù “trung bình mỗi cửa sổ giây” vẫn hợp lệ.

Fixed-window đơn giản, dễ triển khai, nhưng nếu cần giới hạn microburst chặt, có thể không phù hợp.

## 13. Sliding-window limiter

Sliding-window xem tổng arrivals trong một cửa sổ trượt liên tục, ví dụ:

```text
No more than 100 requests within any rolling 1-second window.
```

Cách làm:

- Log timestamps của từng request.
- Sliding-window counter xấp xỉ bằng các buckets nhỏ.
- Những kỹ thuật đếm theo thời gian ở Redis hoặc gateway.

Đánh đổi:

- Chính xác cao có thể cần nhiều state/CPU.
- Distributed limiter cần atomic operations/consistent routing.
- Rolling window hạn chế burst ở ranh giới tốt hơn fixed-window.
- Cần policy cho clock skew và cửa sổ khi failover.

Không coi mọi sliding-window implementation giống nhau; approximate counters có sai số cần công bố.

## 14. Token bucket: kiểm soát tốc độ trung bình và burst

**Token bucket** gồm:

- \(r\): tốc độ thêm token, ví dụ 100 tokens/s.
- \(B\): sức chứa tối đa, ví dụ 250 tokens.
- Mỗi request tốn \(c\) tokens, thường \(c=1\).

```text
tokens(t) = min(B, tokens(previous) + r * elapsed)

if tokens >= cost:
    tokens -= cost
    ALLOW
else:
    REJECT or WAIT
```

Với bucket đầy:

```text
r = 100 requests/s
B = 250 requests
```

hệ có thể chấp nhận một burst tức thời tối đa khoảng 250 requests **trong phạm vi bucket**, rồi duy trì gần 100/s nếu tốc độ đến và chi phí ổn định.

**Không nên hiểu B là số requests được phép bổ sung ngoài mọi giới hạn trong đúng một giây** mà không xét việc tokens được refill trong giây đó.

## 15. Công thức ngân sách token theo khoảng thời gian

Với token bucket không có refill vượt \(B\), tổng tokens có thể được chi trong khoảng dài \(\Delta t\) khi bucket ban đầu đầy thường bị chặn bởi:

\[
N_{\mathrm{allowed}}(\Delta t) \le B + r\Delta t
\]

đối với request cost bằng 1 và cách đo cửa sổ thích hợp.

Ví dụ:

```text
B = 200 tokens.
r = 50 tokens/s.
Observation interval = 10 seconds.
```

Ngưỡng lý thuyết trên có thể là:

\[
200 + 50\times10 = 700
\]

requests được phép trong một cửa sổ nếu bucket bắt đầu đầy và không có giới hạn khác. Tốc độ dài hạn vẫn không vượt \(r\) khi xét thời gian đủ dài.

Trong thực tế, phân bố arrivals, độ chính xác timer, concurrency, clock và atomicity cũng ảnh hưởng.

## 16. Leaky bucket: làm mượt tốc độ xả

Một cách hiểu phổ biến của **leaky bucket** là hàng đợi đệm yêu cầu và xả với tốc độ gần cố định:

```text
Arrival (bursty) -> bounded queue -> worker sends 100/s
```

Ưu điểm:

- Smoothing microbursts.
- Giữ áp lực đầu vào lên dependency tương đối đều.
- Dễ kiểm soát maximum emission rate.

Nhược điểm:

- Khi queue đầy phải từ chối/drop hoặc chuyển backlog sang durable queue.
- Thêm queueing latency.
- Nếu arrivals trung bình vượt service rate, backlog tăng.
- Request có deadline ngắn có thể hết hạn trong queue.
- Dữ liệu cần order/priority/fairness semantics.

**Token bucket thường cho phép burst trong capacity; leaky-bucket shaper hướng tới đầu ra đều hơn.** Không chọn thuật toán chỉ từ tên, vì nhiều thư viện dùng tên leaky bucket cho các biến thể khác nhau.

## 17. Rate limit khác concurrency limit

Một rate limiter:

```text
Maximum average arrival rate: 2.000 requests/s.
```

Nhưng nếu latency tăng từ 20ms lên 2s, số requests in-flight tăng rất mạnh. Chỉ giới hạn RPS có thể chưa đủ để bảo vệ pool/memory.

Một concurrency limiter:

```text
Maximum in-flight operations: 100.
```

Nhưng nếu mỗi operation hoàn tất trong 1ms, nó có thể cho tới khoảng 100.000 operations/s về mặt lý thuyết đơn giản — vượt backend capacity.

Cần phối hợp:

```text
Rate limit -> bảo vệ arrivals/chi phí theo thời gian.
Concurrency limit -> bảo vệ tài nguyên đồng thời.
Queue bound -> bảo vệ backlog/memory.
Deadline -> bảo vệ thời gian chờ.
```

Không dùng `Semaphore(100)` rồi tuyên bố đã giới hạn “100 RPS”.

## 18. Bounded queue là quyết định kinh doanh

Khi tất cả slots bận, một API có thể:

1. **Reject nhanh** bằng response phù hợp, ví dụ 429/503.
2. **Queue ngắn có giới hạn** nếu còn deadline.
3. **Persist durable job** nếu nghiệp vụ chấp nhận async.
4. **Drop/coalesce** các updates không quan trọng.
5. **Degrade** tính năng phụ để dành capacity cho giao dịch chính.

Không nên dùng hàng đợi vô hạn:

```text
Incoming > processing capacity
    -> queue grows forever
    -> memory/GC pressure
    -> more timeouts
    -> retries
    -> bigger queue
```

Queueing **không tạo thêm capacity**, chỉ đổi overload ngay thành backlog và latency trong một thời gian.

## 19. Giới hạn gửi yêu cầu ở client khác giới hạn trên database

Một ứng dụng có ba instance:

```text
Pod A: local limiter = 1.000 RPS
Pod B: local limiter = 1.000 RPS
Pod C: local limiter = 1.000 RPS
```

Tổng cộng có thể gửi gần **3.000 RPS**, không phải 1.000 RPS.

Các lựa chọn:

- Cấu hình quota **per-instance** có chủ đích.
- Phân phối ngân sách quota theo số pods, có động lực scaling.
- Dùng **distributed limiter** atomic trên shared key.
- Dùng queue/stream với number of consumers có giới hạn.
- Tách per-tenant quota khỏi global dependency quota.
- Chấp nhận approximate quota, đo overshoot và rõ contract nếu dùng cache/batching tokens.

Với Kubernetes autoscaling, per-pod limit không thay đổi theo tổng global budget có thể khiến traffic lên NoSQL tăng khi pods tăng.

## 20. Một hạn mức cho tất cả users có thể thiếu công bằng

Giả sử:

```text
Global cap: 5.000 RPS.

Tenant A gửi 4.900 RPS.
Tenant B gửi   100 RPS.
```

Khi A burst lên 7.000, B có thể bị throttle mặc dù B dùng rất ít.

Có thể dùng **hierarchical limits**:

```text
Global:
    5.000 RPS

Per tenant:
    A <= 3.000 RPS
    B <= 1.000 RPS

Per operation:
    expensive search <= 300 RPS
```

Các ngưỡng ví dụ, không phải khuyến nghị chung.

Cần kiểm tra:

- VIP vs free tiers theo policy kinh doanh.
- Tenant quota và fairness.
- Dedicated budgets cho critical writes.
- Background jobs không lấn foreground.
- Không cho một hot key phá toàn service.
- Cách xử lý burst credits.
- Distributed counter consistency và clock skew.

Rate limit là **cơ chế phân bổ capacity và fairness**, không chỉ một phép chia toán học.

## 21. Weighted rate limiting theo chi phí câu lệnh

Một `GET` theo primary key và một `SCAN` toàn bảng không tiêu tốn tài nguyên tương đương.

Ví dụ thang chi phí *giả định*:

```text
Point GET:               1 token
Small conditional WRITE: 3 tokens
Indexed range query:     5 tokens
Large aggregation:      20 tokens
```

Một token bucket với request cost \(c_i\) chấp nhận khi đủ \(c_i\) tokens. Ưu điểm là ngăn một lượng nhỏ expensive queries dùng hết backend.

Nhược điểm:

- Cost estimate có thể sai khi payload/index khác nhau.
- Query có thể phải target nhiều shards tùy filter.
- Cache hit/miss làm chi phí thực thay đổi.
- DynamoDB consumed capacity phụ thuộc kích thước/loại truy cập.
- Cassandra/MongoDB/Redis có cost model riêng.
- Query plans có thể thay khi dữ liệu hoặc index đổi.

Cần dùng **telemetry thực** để hiệu chỉnh trọng số, không giả mọi operation cost cố định mãi mãi.

## 22. HTTP 429, 503 và Retry-After

Khi vượt quota của caller:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 2
```

Nghĩa là caller nên xem hướng dẫn chờ, trong giới hạn retry policy. Với dependency quá tải có thể dùng `503 Service Unavailable` tùy API contract.

Không được giả:

```text
HTTP 429 -> lập tức retry 5 lần.
```

Cần:

- Giữ idempotency key cho business writes.
- Không retry mù non-idempotent operations sau timeout.
- Tôn trọng `Retry-After` khi có và hợp lệ.
- Áp exponential backoff + jitter nếu phù hợp.
- Giới hạn deadline và max attempts.
- Đếm cả retries vào **offered load**.
- Không để mọi clients thức dậy đúng cùng một giây.
- Không che chắn bằng 200/PENDING nếu request thực tế chưa được nhận bền vững.

## 23. Retry amplification phải được đo riêng

Một API nhận:

```text
Original user requests: 1.000/s.
Each request may attempt twice on timeout.
```

Nếu 40% original requests retry một lần:

```text
Original:      1.000/s
Extra retry:     400/s
Total offered: 1.400/s
```

Nếu nhiều tầng cùng retry:

```text
API gateway: 2 attempts
Service:     3 attempts
SDK:         2 attempts
```

Worst-case có thể thành:

\[
2\times3\times2=12
\]

attempts xuống dependency cho **một request nghiệp vụ**, nếu mọi tầng thực hiện hết vòng và không phối hợp.

Đây là lý do “tải đột biến” có thể **được tự tạo bởi chiến lược retry khi service chậm**.

## 24. Open-loop load generator phải tự giới hạn tài nguyên

Khi target cần:

```text
10.000 arrivals/s
```

nhưng backend mất 2 giây để phản hồi, nếu giữ toàn bộ requests thì có thể cần khoảng **20.000 in-flight** (theo mô hình đơn giản), chưa tính queue.

Một generator naïve có thể hết RAM, socket, file descriptors hoặc threads trước backend.

Thiết kế generator:

- Scheduler phát arrival slots theo lịch.
- Bounded in-flight Semaphore.
- Async I/O hoặc thread pool có giới hạn.
- Record `scheduled` và `failed-to-dispatch` riêng.
- Không tạo unbounded waiting futures.
- Không coi generator overload là backend response timeout.
- Đo CPU, heap, GC, network, open sockets của chính máy phát.
- Dùng nhiều generator instances khi cần, phối hợp clock/arrival plan và kết quả.

Nếu generator không tạo đủ offered load, phép đo ở mức target RPS là **INCONCLUSIVE**, không được kết luận server xử lý tốt hơn mức đã thật sự gửi.

## 25. Tại sao dùng `Thread.sleep(1)` không tạo chính xác 1.000 RPS?

Một vòng đơn giản:

```java
while (running) {
    sendRequest();
    Thread.sleep(1);
}
```

Có các vấn đề:

- `sendRequest` có thể block; tốc độ phụ thuộc latency.
- Scheduler/timer có độ phân giải và jitter.
- GC pauses làm lịch bị trễ.
- `Thread.sleep` không đảm bảo thức dậy đúng thời điểm.
- TCP connect, DNS, TLS và serialization tốn thời gian.
- Thời gian xử lý vòng lặp không được trừ khỏi interval.
- `sleep(1)` không có nghĩa chính xác 1.000 requests/s.

Một generator nên dùng **monotonic scheduled deadlines** và ghi missed slots, hoặc dùng công cụ được thiết kế cho constant-arrival-rate workloads.

## 26. Mô hình phân bố arrivals: đều theo slot hay ngẫu nhiên?

### Fixed-spacing arrivals

```text
100 RPS -> 1 request / 10 ms.
```

Dễ dự báo, hữu ích để đo steady rate có cadence ổn.

### Poisson-like arrivals

Khoảng cách giữa events có thể được lấy từ phân bố exponential với trung bình \(1/\lambda\), khi đó arrival count mỗi khoảng có biến thiên.

### Recorded trace replay

Dùng timestamps thực tế đã ẩn danh và được phép sử dụng.

### Correlated bursts

Nhiều clients cùng tương tác với một sự kiện thông báo hoặc campaign:

```text
Push notification at T0.
Thousands of users click within 2 seconds.
```

Không có mô hình arrival nào đúng cho mọi tình huống. Cần **chọn theo nguồn người dùng và rủi ro cần kiểm tra**.

Một fixed-spacing test có thể cho thấy hệ ổn ở 2.000 RPS nhưng không phản ánh microburst dồn vào cùng vài milliseconds.

## 27. Một workload NoSQL không chỉ có RPS

Mỗi request cần mô tả:

```yaml
operation: "GET order by id"
proportion: 0.60
keyDistribution: "zipf-like"
payloadBytes: 200
consistency: "as required"
expectedRows: 1
```

Hoặc:

```yaml
operation: "UPDATE inventory using CAS"
proportion: 0.20
hotKeyFraction: 0.05
documentSizeBytes: 3000
retryPolicy: "bounded"
```

Các chiều ảnh hưởng:

- Read/write ratio.
- Key access distribution.
- Partition/shard key design.
- Hot tenants/keys.
- Document/item size.
- Query selectivity và index coverage.
- Index update amplification.
- Read consistency, quorum và replica lag.
- TTL/compaction/tombstone density.
- Cache hit ratio.
- Transaction scope và contention.
- Batching.
- Compression/network payload.
- Background CDC/repair/reindex.
- Request timeout/retry settings.

**Hai bài benchmark có cùng RPS nhưng khác phân bố khóa có thể có hiệu năng rất khác.**

## 28. Phân bố khóa đều và lệch (skew)

Một bài benchmark với keys được chọn đều:

```text
1.000.000 keys.
Mỗi key có xác suất gần như nhau.
```

Một hệ thực có thể có:

```text
10 keys nóng nhận 40% requests.
Các keys khác nhận 60%.
```

Tác động:

- Một partition có thể quá tải dù average CPU cluster thấp.
- CAS/conflict rate tăng trên hot keys.
- Redis single-thread execution/hot slot bị quá tải.
- DynamoDB partition throughput/throttling có thể giới hạn.
- Cassandra/Scylla large/hot partition gây latency.
- MongoDB một shard hoặc document nóng bị tranh ghi.
- Cache hit rất cao vẫn có thể tạo hot lock hoặc stampede khi expire.

Nên test cả **uniform distribution** và **production-like skew**, kèm các kịch bản cố tình gây hot key.

## 29. Burst tập trung vào một key khác burst phân tán

Ví dụ hai workload cùng 5.000 requests/s:

```text
A: 5.000 point GET trên 500.000 keys.
B: 5.000 conditional UPDATE trên 1 key tồn kho.
```

A chủ yếu thử throughput đọc và cache. B thử:

- Serialization/lock/CAS conflicts.
- Hot partition capacity.
- Retry amplification.
- Idempotency.
- Fairness giữa request đến cùng key.
- Deadline của user.
- Correctness khi failover.

Một khuyến nghị “cluster có thể scale ngang” không có nghĩa workload B cũng tự scale ngang nếu mọi writes **phải đi qua một điểm bảo vệ invariant**.

## 30. Read và write amplification trong burst

Một operation logic có thể tạo nhiều physical operations.

Ví dụ:

```text
Write product:
    update source doc
    update 4 indexes
    append outbox
    update materialized read view async
    invalidate cache
```

Khi 3.000 logical writes/s đến đột ngột, hệ có thể phải làm nhiều hơn 3.000 physical mutations/s.

Tương tự:

```text
One query:
    scans 20 partitions
    returns only 10 rows
```

Một burst 500 queries/s có thể gây 10.000 partition touches/s.

Cần đo:

- Logical RPS và physical operations/s.
- Disk write bytes và compaction.
- Index maintenance cost.
- Query fan-out.
- CDC/event throughput.
- Replica network traffic.
- Cache invalidation rate.
- Read/Write capacity units nơi engine cung cấp.

**Load shedding một phần query nặng có thể tốt hơn giảm đều mọi request**.

## 31. Compaction, flush và background work làm capacity thay đổi theo thời gian

NoSQL storage engines có những hoạt động nền:

```text
Memtable flush
Compaction
Replica repair
Garbage collection
Snapshot/backup
Index build
CDC log retention
Rebalance
TTL/tombstone cleanup
```

Một bài test 30 giây có thể chỉ đo giai đoạn cache nóng khi background work chưa xuất hiện.

Vì thế cần:

- Warm-up.
- Steady-state đủ dài.
- Soak test nhiều chu kỳ compaction/GC.
- Burst trước, trong và sau background tasks.
- Recovery đo đủ lâu để backlog/latency quay lại.
- Ghi operating conditions trong báo cáo.

Không lấy một p99 tốt ở thời điểm chưa có compaction làm bảo đảm cả ngày.

## 32. Tải đều cần pha warm-up đúng nghĩa

Một lịch thử nghiệm mẫu:

```text
Warm-up 5 phút:
    prefill caches, connection pools, JIT, indexes
    không trộn số liệu warm-up vào kết quả chính.

Steady load 10 phút:
    1.000 RPS, 70% reads, 30% writes
    ghi metrics mỗi khoảng nhỏ.

Cooldown/recovery:
    kiểm tra backlog và error state.
```

Thời lượng minh họa, phải điều chỉnh theo hệ thật.

Nếu khởi chạy `1.000 RPS` ngay khi service cold:

- TLS/connection pool chưa warm.
- Java JIT/GC chưa ổn.
- Cache miss cao.
- NoSQL page cache chưa nóng.
- Autoscaling chưa phản ứng.
- CDC consumer chưa bắt kịp.

Có những hệ cố ý cần kiểm tra **cold-start burst**; khi đó không warm-up là **chủ đích và phải nêu rõ**, chứ không phải nhầm nó với steady state.

## 33. Tải đột biến cần đo cả thời gian hồi phục

Một lịch minh họa:

```text
Phase A: 500 RPS  —  5 phút  — baseline
Phase B: 1000 RPS —  5 phút  — steady
Phase C: 5000 RPS — 20 giây — burst
Phase D: 1000 RPS — 10 phút — recovery
```

Đánh giá:

- p95/p99 lúc burst.
- Số requests 429/503/timeout.
- Peak pending connections/queue depth.
- Time-to-recover latency về mức baseline.
- Backlog/CDC lag còn lại sau burst.
- Retry amplification.
- CPU/IOPS saturation và memory.
- Lỗi consistency/correctness trong workload ghi.
- Số operations `UNKNOWN` cần đối soát.

Một hệ có thể “chịu” 20 giây burst nhưng mất 30 phút để khôi phục projection; đây là một kết quả quan trọng, không phải chi tiết phụ.

## 34. Ramp test tìm điểm gãy và headroom

Một lịch:

```text
500 -> 750 -> 1000 -> 1250 -> 1500 -> 1750 -> 2000 RPS
```

Giữ mỗi bậc đủ lâu để đo.

Tại mỗi mức:

- Offered/accepted/completed RPS.
- p50/p95/p99 end-to-end latency.
- Error/reject rate.
- Queue depth và inflight.
- CPU, memory, disk, network.
- Per-node/per-partition load.
- Cache hit.
- Throttling.
- CDC/replication lag.

Điểm gãy có thể là:

- `p99` tăng phi tuyến.
- Completion throughput không tăng nữa.
- Queue/backlog bắt đầu tăng liên tục.
- 429/503 tăng.
- Hot partition throttle trong khi cluster còn rảnh.

Capacity an toàn phải có **headroom**, không nên vận hành thường xuyên ngay sát điểm gãy.

## 35. Soak test phát hiện sự suy giảm theo thời gian

Một hệ đạt 2.000 RPS trong 5 phút chưa chắc giữ được 2.000 RPS trong 4 giờ.

Soak test hữu ích cho:

- Memory/connection leaks.
- Compaction backlog.
- Tombstone accumulation.
- Replication/CDC lag.
- Disk space growth.
- Java GC pressure.
- Index bloat.
- Batch queues không xả.
- TTL expiry waves.
- Cache key churn.
- Background retries.
- File descriptor exhaustion.

Kết quả cần có **xu hướng**, không chỉ một snapshot cuối. Nếu p99 tăng dần trong khi offered load không đổi, đó có thể là dấu hiệu hệ chưa đạt steady state.

## 36. Một thí nghiệm chỉ được công bố khi biết giới hạn generator

Giả sử máy phát báo:

```text
Configured: 5.000 RPS.
Actually scheduled: 5.000 RPS.
Actually dispatched: 3.700 RPS.
```

Vì Java load generator hết CPU hoặc hết worker permits.

Không thể tuyên bố backend đã thử ở **5.000 RPS thực**.

Báo cáo cần:

```text
Target offered rate
Scheduled arrivals
Actual dispatch rate
Generator-dropped/missed slots
Server accepted rate
Server completion rate
Client-observed latency
Generator CPU/heap/network utilization
```

Khi generator bottleneck, có thể cần thêm load generators hoặc đổi I/O model, **không chỉnh server chỉ dựa trên kết quả sai**.

## 37. Java 17: token bucket cục bộ có đồng hồ đơn điệu

Ví dụ sau cài đặt token bucket cho **một JVM**. Dùng `System.nanoTime()` để tính elapsed time và `synchronized` để bảo vệ state trong tiến trình.

```java
public final class LocalTokenBucket {
    private final double capacity;
    private final double refillTokensPerSecond;
    private double tokens;
    private long updatedAtNanos;

    public LocalTokenBucket(
            double capacity,
            double refillTokensPerSecond) {

        if (capacity <= 0 || refillTokensPerSecond <= 0) {
            throw new IllegalArgumentException(
                "Capacity and refill rate must be positive");
        }

        this.capacity = capacity;
        this.refillTokensPerSecond = refillTokensPerSecond;
        this.tokens = capacity;
        this.updatedAtNanos = System.nanoTime();
    }

    public synchronized boolean tryAcquire(double cost) {
        if (!(cost > 0) || cost > capacity) {
            return false;
        }

        long now = System.nanoTime();
        double elapsedSeconds = Math.max(
            0.0, (now - updatedAtNanos) / 1_000_000_000.0);

        tokens = Math.min(
            capacity,
            tokens + elapsedSeconds * refillTokensPerSecond);
        updatedAtNanos = now;

        if (tokens < cost) {
            return false;
        }

        tokens -= cost;
        return true;
    }

    public synchronized double availableTokens() {
        // Chỉ phản ánh trạng thái cập nhật gần nhất.
        return tokens;
    }
}
```

Ví dụ sử dụng:

```java
LocalTokenBucket bucket =
        new LocalTokenBucket(200, 100);

boolean allowed = bucket.tryAcquire(1);

if (allowed) {
    // Submit request to the next bounded stage.
} else {
    // Reject, queue within deadline, or emit a rate-limit signal.
}
```

Giới hạn:

- Chỉ bảo đảm trong một process/JVM.
- Không kiểm soát tổng quota của nhiều API pods.
- `availableTokens()` không chủ động refill để đọc, chỉ để quan sát state.
- Double precision đủ để minh họa nhưng hệ có yêu cầu chặt có thể dùng fixed-point units.
- `synchronized` có overhead và có thể thành lock nóng ở throughput lớn.
- Không bảo đảm capacity của NoSQL, chỉ chặn tốc độ phát lệnh tại vị trí gọi.

## 38. Java 17: demo open-loop pacing và bounded in-flight

Đoạn chương trình độc lập bên dưới **mô phỏng backend bằng `Thread.sleep`**, không gọi NoSQL thật. Mục đích là tách **arrival schedule**, **tải thực sự dispatch được**, **lượng phải từ chối ở generator** và **latency từ mốc lên lịch**. Có thể lưu thành `PacedLoadDemo.java` và chạy với Java 17.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.LockSupport;

public final class PacedLoadDemo {
    record Phase(String name, int rps, int seconds) {}

    static final class Counters {
        final LongAdder scheduled = new LongAdder();
        final LongAdder dispatched = new LongAdder();
        final LongAdder generatorRejected = new LongAdder();
        final LongAdder completed = new LongAdder();
        final LongAdder failures = new LongAdder();
        final LongAdder totalLatencyNanos = new LongAdder();
        final AtomicLong maxLatencyNanos = new AtomicLong();

        void record(long latencyNanos) {
            completed.increment();
            totalLatencyNanos.add(latencyNanos);
            maxLatencyNanos.accumulateAndGet(latencyNanos, Math::max);
        }
    }

    static void simulateBackend() throws InterruptedException {
        // Thay bằng client NoSQL thật khi chạy integration/load test.
        Thread.sleep(20);
    }

    static void runPhase(
            Phase phase,
            ExecutorService pool,
            Semaphore inFlight,
            Counters stats) {

        long intervalNanos = 1_000_000_000L / phase.rps();
        long phaseStart = System.nanoTime();
        int slots = phase.rps() * phase.seconds();

        for (int i = 0; i < slots; i++) {
            long scheduledAt = phaseStart + i * intervalNanos;

            long remaining = scheduledAt - System.nanoTime();
            if (remaining > 0) {
                LockSupport.parkNanos(remaining);
            }

            stats.scheduled.increment();

            // Không tạo unbounded queue khi backend chậm.
            if (!inFlight.tryAcquire()) {
                stats.generatorRejected.increment();
                continue;
            }

            try {
                pool.execute(() -> {
                    try {
                        simulateBackend();
                        stats.record(
                            System.nanoTime() - scheduledAt);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        stats.failures.increment();
                    } finally {
                        inFlight.release();
                    }
                });
                stats.dispatched.increment();
            } catch (RejectedExecutionException ex) {
                inFlight.release();
                stats.generatorRejected.increment();
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        ExecutorService pool =
                Executors.newFixedThreadPool(32);
        Semaphore inFlight = new Semaphore(64);
        Counters stats = new Counters();

        Phase[] plan = {
            new Phase("steady", 100, 3),
            new Phase("burst", 1000, 2),
            new Phase("recovery", 100, 3)
        };

        for (Phase phase : plan) {
            runPhase(phase, pool, inFlight, stats);
            System.out.println(
                "Finished scheduling " + phase.name());
        }

        pool.shutdown();
        if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
            pool.shutdownNow();
        }

        System.out.println("Scheduled=" + stats.scheduled.sum());
        System.out.println("Dispatched=" + stats.dispatched.sum());
        System.out.println(
            "GeneratorRejected=" + stats.generatorRejected.sum());
        System.out.println("Completed=" + stats.completed.sum());
        System.out.println("Failures=" + stats.failures.sum());

        long completed = stats.completed.sum();
        if (completed > 0) {
            double meanMs = stats.totalLatencyNanos.sum()
                    / (double) completed / 1_000_000.0;
            double maxMs = stats.maxLatencyNanos.get()
                    / 1_000_000.0;

            System.out.printf(
                "Mean %.2f ms, max %.2f ms%n", meanMs, maxMs);
        }
    }
}
```

### Giới hạn của demo

- `Thread.sleep(20)` giả lập backend cố định, **không mô phỏng latency thực** của NoSQL, serialization, consistency hoặc network.
- Mã đếm `scheduled` nhưng không tự báo missed schedule deadline. Generator có thể chạy trễ; để test nghiêm túc cần metric `scheduleLatenessNanos` và policy không catch-up vô kiểm soát.
- Thread pool có queue nội bộ; Semaphore giới hạn tổng submitted in-flight ở mức 64, nhưng tasks có thể đang chờ trong pool.
- `stats.record` ghi latency từ **scheduledAt**, gồm queueing trong generator nếu có, nhưng không đủ histogram p95/p99.
- `Scheduled` không phải mọi request đã đi qua network.
- Nếu backend thật có timeout, callback phải ghi rõ outcomes, retries và cancellation.
- Demo dùng chung `Counters` cho các phases; benchmark thực phải lưu histogram/metrics **cho từng phase**.
- Không xem kết quả demo là đo capacity NoSQL. Đây chỉ là ví dụ cách tổ chức một generator có pacing và giới hạn in-flight.

## 39. Vì sao không nên catch-up bằng cách gửi dồn các slot đã trễ?

Giả sử generator bị GC pause 1 giây khi target là 1.000 RPS.

Nếu vòng phát hiện 1.000 slots đã quá hạn rồi cố gửi ngay lập tức:

```text
T0+1s: 1.000 requests được dispatch trong vài ms.
```

Nó tạo **microburst nhân tạo** không nằm trong arrival plan.

Một policy tốt hơn tùy mục đích:

- **Record missed slots** và coi test chưa đạt tải yêu cầu.
- Ghi `schedule lateness` để đo generator capacity.
- Chỉ catch-up khi mô phỏng queue arrivals thật và muốn phát backlog có chủ đích.
- Không reset `phaseStart` lặp lại để che việc phát chậm.
- Với fixed-rate arrival, dùng scheduler/công cụ có semantics rõ khi bị trễ.

Điểm chính là **không âm thầm biến steady load thành burst vì generator lag**.

## 40. Một test plan khai báo được bằng cấu hình

Ví dụ YAML thí nghiệm:

```yaml
testName: "orders-steady-burst-01"
environment: "staging-like-production"
dataset:
  orderCount: 10000000
  customerCount: 100000
  hotCustomerShare: 0.05
workload:
  operations:
    getById: 0.60
    listByCustomer: 0.20
    conditionalUpdate: 0.20
  arrivalModel: "open-loop-fixed-pacing"
  keyDistribution: "skewed"
  payloadProfile: "production-like"
  retries:
    policy: "bounded-and-instrumented"
  stages:
    - name: "warmup"
      rps: 500
      seconds: 300
    - name: "steady"
      rps: 1000
      seconds: 600
    - name: "burst"
      rps: 5000
      seconds: 20
    - name: "recovery"
      rps: 1000
      seconds: 600
limits:
  generatorMaxInFlight: 2000
  generatorQueuePolicy: "reject-and-count"
observability:
  histogram: "end-to-end-and-db"
  metricsIntervalSeconds: 1
  recordGeneratorMissedSlots: true
```

Các con số chỉ minh họa. Bộ dữ liệu thật cần phù hợp topology, kích thước item, indexes, TTL, hot keys, consistency và background workloads. Không chạy stress test phá nguồn giao dịch thật nếu chưa có phạm vi vận hành được phê duyệt.

## 41. Không nên chọn tốc độ dựa trên QPS trung bình một ngày

Ví dụ:

```text
Tổng requests trong ngày: 86.400.000
Average: 1.000 requests/s
```

Nhưng có thể:

```text
Peak minute: 5.000 requests/s
Peak second: 12.000 requests/s
Peak 100ms: 3.000 requests
```

Peak 100ms tương đương một tốc độ tức thời rất khác average. Khi lập tải:

- Chọn baseline từ phân phối thật.
- Giữ peak per-second/per-minute.
- Tái tạo microbursts khi chúng có ảnh hưởng.
- Xem seasonality/flash sale/notifications.
- Xem thay đổi sau rollout/app upgrade.
- Đánh giá headroom cho vùng/hệ gặp lỗi.

**Average throughput chỉ là điểm khởi đầu**, không phải capacity target.

## 42. Histogram latency: đừng chỉ ghi average

Một thí nghiệm có:

```text
95% requests:  20ms.
4% requests:  100ms.
1% requests:  2.000ms.
```

Average có thể trông chấp nhận được cho một số workload, nhưng 1% ở mức 2 giây có thể gây ảnh hưởng lớn lên UX hoặc retry.

Cần đo:

- p50, p90, p95, p99 và p99.9 nếu sample đủ lớn.
- Mean và standard deviation khi hữu ích.
- Max latency nhưng không dùng max đơn độc.
- Latency của success và error riêng.
- Queue wait vs database service time vs network time.
- Client-observed end-to-end latency.
- Per operation type và per tenant/hot partition.
- Time-to-recovery sau burst.

Nếu chỉ có 50 samples, p99 không đáng tin như histogram có hàng chục nghìn samples. Công bố sample count và sampling methodology.

## 43. So sánh percentiles cần cùng cách đo

Một dashboard báo:

```text
Server processing p99 = 50 ms.
Client observed p99   = 900 ms.
```

Khoảng chênh có thể đến từ:

- API queue wait.
- Connection pool acquisition.
- Network RTT/retransmission.
- JSON serialization.
- Load-balancer/proxy queue.
- Client-side scheduling lag.
- Retry hoặc timeout waiting.
- CDC/read-model wait.

Cần gắn timeline:

```text
scheduled -> dispatched -> accepted
    -> enqueued -> DB executed
    -> response written -> client received
```

**p99 của server handler không tương đương p99 mà user cảm nhận**.

## 44. Đo theo từng khoảng ngắn, không chỉ aggregate cả bài

Một burst dài 20 giây trong bài test 30 phút có thể bị che bởi histogram tổng.

Nên có:

```text
1-second or 5-second time series:
    offered RPS
    accepted/completed RPS
    p99 latency
    error/429/timeout
    queue size
    CPU/IOPS
```

Đồng thời giữ **histogram tổng của từng phase** để có sample đủ lớn.

Lưu ý histogram merge phải đúng thuật toán. Không tính p99 của toàn bài bằng cách **lấy trung bình các p99 của từng giây** — điều đó không tạo ra p99 thật.

## 45. Đo lỗi cần có taxonomy

Một cột “errors = 5%” không nói lên nguyên nhân.

Phân nhóm:

| Loại | Ví dụ | Diễn giải |
| --- | --- | --- |
| Admission rejection | HTTP 429 | Rate limit/quota |
| Overload unavailable | 503 | Dependency/queue không thể nhận |
| Client timeout | Deadline exceeded | Response không kịp, write outcome có thể UNKNOWN |
| Transport failure | Connection reset | Network/endpoint |
| NoSQL throttling | Capacity limit | Partition/table/service constraint |
| CAS business conflict | Condition not met | Có thể đúng nghiệp vụ, không phải hạ tầng hỏng |
| Validation failure | Bad payload | Generator/test data có thể sai |
| Auth failure | Invalid token | Test setup hoặc security policy |
| Server 5xx | Internal error | Cần root cause |
| CDC lag SLO violation | Projection chậm | Read-side freshness issue |
| Data invariant violation | Duplicate reservation/charge | Correctness failure |

Một `409` khi hai clients cùng tranh last unit có thể là **kết quả đúng**; không nên nhập nó vào hạ tầng error rate như 5xx. Nhưng vẫn cần đếm business reject rate để hiểu tải thật.

## 46. Rate limit cần có phạm vi rõ

Một key của limiter có thể là:

```text
global
global + region
tenant
tenant + operation
authenticated user
API key
database shard/partition route
destination service
```

Không nên chỉ dùng **IP** cho mọi workload:

- NAT có thể gom nhiều users vào một IP.
- Một user có thể đổi IP hoặc dùng proxy.
- Dễ gây bất công.
- Authentication mới là nguồn identity tin cậy cho quota theo account.
- Phân vùng địa lý và các Regions cần xét global budget.

Không dùng header `X-Tenant-Id` do client tự gửi để cấp thêm quota khi chưa xác thực quyền. Rate limiting và authorization không tách rời hoàn toàn.

## 47. Redis Lua: distributed token bucket theo một key

Một Lua script minh họa cho **một key limiter**. Dùng thời gian lấy từ chính Redis để tránh khác biệt clock giữa nhiều Java pods.

```lua
-- KEYS[1]: token bucket hash
-- ARGV[1]: refill rate tokens/second
-- ARGV[2]: bucket capacity
-- ARGV[3]: request cost
-- ARGV[4]: key TTL in milliseconds

local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

if not rate or not capacity or not cost or not ttl
   or rate <= 0 or capacity <= 0 or cost <= 0 or ttl <= 0 then
    return {0, -1, -1}
end

if cost > capacity then
    return {0, -1, -1}
end

local now = redis.call("TIME")
local nowMs = now[1] * 1000 + math.floor(now[2] / 1000)

local oldTokens = tonumber(redis.call("HGET", KEYS[1], "tokens"))
local lastMs = tonumber(redis.call("HGET", KEYS[1], "last_ms"))

local tokens = oldTokens or capacity
local elapsed = 0

if lastMs then
    elapsed = math.max(0, nowMs - lastMs)
end

tokens = math.min(capacity, tokens + elapsed * rate / 1000)

local allowed = 0
local retryMs = 0

if tokens >= cost then
    allowed = 1
    tokens = tokens - cost
else
    retryMs = math.ceil((cost - tokens) * 1000 / rate)
end

redis.call("HSET", KEYS[1],
    "tokens", tokens,
    "last_ms", nowMs)
redis.call("PEXPIRE", KEYS[1], ttl)

return {allowed, math.floor(tokens), retryMs}
```

### Những giới hạn không được bỏ qua

- Script giúp **atomic decision trên một key trong một Redis instance**, không mặc định tạo global consistent quota xuyên Regions.
- Redis Cluster có slot-rules với multi-key scripts.
- Replication/failover/persistence có thể làm quota state bị rollback tùy cấu hình.
- Key TTL phải đủ lớn so với thời gian refill; TTL quá ngắn khiến bucket liên tục reset thành đầy và vượt quota dự kiến.
- `TIME` là wall clock; nếu server clock đổi, phép `max(0, ...)` giúp tránh refill âm nhưng không giải quyết mọi clock/failover issue.
- Một hot global rate-limit key có thể trở thành bottleneck.
- Script không thay thế limiter/concurrency cap của target NoSQL.
- Với quota tài chính/contract chặt, cần xem yêu cầu độ chính xác, audit và authority khác Redis cache.

## 48. Ước lượng TTL cho token bucket

Nếu bucket có:

```text
B = 100 tokens.
r = 10 tokens/s.
```

Thời gian refill từ rỗng tới đầy:

\[
T_{\mathrm{refill}}=\frac{B}{r}=10\ \text{seconds}
\]

Nếu marker TTL chỉ 1 giây và không có request, key hết hạn nhanh; request tiếp theo có thể tạo bucket mới **đầy 100 tokens**, trong khi một policy tưởng rằng chỉ có 10 tokens được hồi sau một giây.

Một lựa chọn là đặt key TTL **lâu hơn thời gian refill từ rỗng tới đầy**, có thêm margin và xét traffic/idle policy. Tuy vậy, exact strategy phải phù hợp quota semantics, failover và memory cost.

TTL của rate limiter không liên quan trực tiếp tới TTL của processed-event idempotency ledger; hai loại state có cửa sổ an toàn khác nhau.

## 49. Token bucket bảo vệ burst nhưng cũng có thể tạo burst dồn

Giả sử 1.000 clients chờ tokens và đồng thời được cấp quota ở một thời điểm:

- Mỗi client có local bucket riêng, tổng burst có thể rất lớn.
- Distributed bucket có thể cấp nhiều tokens ngay khi refill.
- Retry logic `sleep(retryAfter)` giống nhau có thể tạo **thundering herd**.
- Một limiter đặt quá sâu sau queue đã không bảo vệ được ingress memory.
- Per-tenant limiter có thể không bảo vệ một shard nóng nếu nhiều tenants cùng shard.

Giải pháp tùy workload:

- Jitter cho retry.
- Pacing/shaping ở tầng client.
- Global + per-key + concurrency gates.
- Bounded queue.
- Admission trước expensive parsing/DB work.
- Giám sát hot partitions.
- Chọn burst capacity \(B\) phù hợp backend headroom.

**Cho phép burst là một chính sách**, không phải một đặc tính mặc định luôn tốt.

## 50. Chi phí của limiter không được vượt lợi ích

Một limiter dùng Redis cho mọi request:

```text
API request
    -> Redis EVAL
    -> NoSQL operation
```

Khi lưu lượng rất lớn, limiter có thể tạo:

- Redis hot key.
- RTT bổ sung cho từng request.
- Một dependency mới.
- Failure mode khi Redis không sẵn.
- Chênh lệch giữa quota allowed và NoSQL thực sự nhận do timeout.
- Overshoot khi app fallback `allow` không điều kiện.

Có thể tối ưu:

- Local token reservations/leases từ global quota với guardrails.
- Sharded limiter theo tenant/key.
- Gateway-level native rate limiting.
- Bulkhead/per-shard concurrency.
- Offline quota estimates cho workload ít rủi ro.
- Chỉ dùng global precise limiter cho operations cần.
- Monitoring overshoot theo thực tế.

**Fail-open hay fail-closed khi limiter outage là quyết định rủi ro**, không nên để exception của Redis quyết định ngẫu nhiên.

## 51. NoSQL: MongoDB dưới tải đều và burst

Với MongoDB, các đường cần đo có thể gồm:

- Point find theo `_id`.
- Range/indexed query có sort/limit.
- UpdateOne theo version/CAS.
- Multi-document transaction.
- Aggregation và change streams.
- Read preference/concern và write concern.
- Shard targeting/mongos routing.

Một burst có thể làm rõ:

- Một shard nóng do shard key.
- Query scatter-gather.
- Index update overhead.
- Connection pool wait/checkout latency.
- Document-level write conflicts.
- Transaction aborts/retries.
- Replication lag.
- Cache/page faults.
- Oplog/change stream backlog.

Một indexed GET có latency thấp ở steady rate **không chứng minh** aggregation và transaction có cùng capacity.

Khi benchmark, đừng tự động hạ read concern/write concern chỉ để tăng completed RPS nếu business contract yêu cầu mức mạnh hơn.

## 52. DynamoDB dưới tải đều và burst

Với DynamoDB cần quan sát:

- Partition key distribution.
- Consumed read/write capacity.
- Per-partition hot key behavior.
- Throttling và retry.
- Item size, response size.
- Base table vs GSI access.
- Transactional read/write cost.
- GSI propagation lag.
- DynamoDB Streams consumer lag.
- On-demand/provisioned capacity behavior theo cấu hình thực.

Một table có capacity tổng còn dư **vẫn có thể bị throttle ở một partition key nóng**. Vì thế test nên gồm:

```text
A. Uniform keys.
B. 1% keys receive 40% operations.
C. Sudden burst to a single tenant/key.
```

Phân biệt throttling từ account/table/index/partition theo telemetry của hệ. SDK retry có thể tăng request volume và làm biến dạng offered load; cần đo cả attempts và logical commands.

## 53. Cassandra và ScyllaDB dưới burst

Các yếu tố quan trọng:

- Partition key distribution và hot partitions.
- Wide/large partition đọc nhiều clustering rows.
- LWT/CAS contention.
- Tombstone scans.
- Coordinator load.
- Replica consistency levels.
- Compaction và SSTable read/write amplification.
- Memtable flush.
- Hinted handoff/repair/streaming.
- Driver pooling, speculative execution và retry policy.
- Cross-datacenter network.

Ví dụ:

```text
Uniform read workload:
    SELECT one partition/small range.

Burst hot key:
    2.000 LWT attempts/s on one inventory partition.
```

Hai workload có thể tạo p99 và conflicts rất khác. Một burst làm hàng đợi coordinator tăng không đồng nghĩa tăng số CPUs là đủ nếu invariant phải serialize tại một partition.

Với ScyllaDB/Cassandra, phải đối chiếu khả năng engine/version trước khi chọn caching, metrics, concurrency và CDC tuning.

## 54. Redis vừa có thể là cache vừa là limiter

Redis chịu các nguồn tải:

```text
Application GET/SET cache
Distributed token bucket Lua
Session lookup
Pub/Sub/Streams
Hot counters
```

Một burst vào limiter có thể làm chính **Redis hot key** quá tải, khiến cache GET cũng chậm. Khi chạy benchmark:

- Phân biệt Redis là **subject under test** hay dependency hỗ trợ test.
- Đo cache hit/miss, command latency, event loop/CPU và memory.
- Đo script latency, key hotspots, eviction.
- Test failover/replica read semantics nếu production có.
- Không coi Redis cache successful GET là authoritative confirmation cho inventory/payment.
- Không dùng counter benchmark để suy ra performance của Lua transaction hoặc Streams consumer.

Nếu limiter và cache cùng một Redis cluster, chúng có thể cạnh tranh tài nguyên, dẫn tới vòng phản hồi xấu trong burst.

## 55. Cache hit ratio thay đổi sau burst

Ví dụ steady:

```text
GET 1.000 RPS.
Cache hit: 95%.
NoSQL source: ~50 reads/s.
```

Khi flash crowd vào keys mới:

```text
GET 5.000 RPS.
Cache hit: 20%.
NoSQL source: ~4.000 reads/s.
```

Dù frontend chỉ tăng 5 lần, NoSQL source read rate tăng gần **80 lần** theo ví dụ.

Cần đo đồng thời:

- Cache hit ratio theo phase và key distribution.
- Source fallback QPS.
- Single-flight/coalescing.
- Cache fill latency.
- TTL/eviction patterns.
- Replica lag.
- Negative caching.
- Hot-key invalidation burst.
- Freshness/read-your-writes semantics.

**Tốc độ HTTP không đủ để dự báo tốc độ database nếu cache behavior thay đổi.**

## 56. CDC và materialized view cũng bị ảnh hưởng bởi burst

Một command path:

```text
Write source
    -> outbox/change stream
    -> broker
    -> consumer
    -> read model/search index
```

Một burst có thể làm write authority vẫn ổn nhưng downstream:

- Queue lag tăng.
- Consumer throughput chạm giới hạn.
- Search index refresh chậm.
- Materialized summary đọc dữ liệu cũ.
- Dedupe ledger phát sinh nhiều writes.
- DLQ/poison events bị kẹt.
- Cache invalidation đến muộn.

Cần đo:

```text
source_write_commit_rate
events_published_rate
events_consumed_rate
consumer_backlog
oldest_unprocessed_event_age
projection_revision_lag
time_to_catch_up
```

Một bài load test chỉ đo HTTP 200 mà không đo **projection freshness** có thể bỏ sót vi phạm sản phẩm nghiêm trọng.

## 57. Đường ghi có commit UNKNOWN trong burst

Khi write timeout, server có thể đã commit nhưng ACK bị mất. Nếu client retry một lệnh không lũy đẳng:

```text
INCREMENT +1
timeout after commit
retry +1
```

hiệu ứng trùng.

Trong load test cần:

- Stable operationId.
- Driver retry policy đúng theo API.
- Dedupe marker/ledger.
- Phân biệt APPLIED, REJECTED, UNKNOWN.
- Không đếm client timeout = “server chắc chưa ghi”.
- Reconciliation sau test để kiểm tra business invariants.
- Theo dõi số writes attempted vs distinct logical effects.
- Kiểm tra duplicate charges/reservations/counters.

**Một hệ có thể đạt p99 latency tốt nhưng sai dữ liệu khi retry**, nên performance report cần chứa correctness gates.

## 58. Không tắt consistency safeguards để “đẹp số”

Một test muốn tăng RPS có thể bị cám dỗ:

```text
Disable transactions.
Lower consistency level.
Skip optimistic lock.
Ignore write acknowledgment.
Stop idempotency ledger.
```

Sau thay đổi, p99 có thể đẹp hơn nhưng **không còn là cùng nghiệp vụ**.

Một phép so sánh hợp lệ phải giữ:

- Read/write consistency contract.
- Durability requirements.
- Business invariant checks.
- Tenant authorization.
- Transaction boundary.
- Idempotency behavior.
- Read-your-writes scope nếu được hứa.

Có thể chạy một **thí nghiệm riêng** với consistency khác để hiểu chi phí, nhưng không dùng nó để tuyên bố hệ đạt SLO production nếu sản phẩm không chấp nhận semantics mới.

## 59. Khi nào nên drop, khi nào nên queue?

| Yêu cầu | Có thể từ chối nhanh? | Có thể queue? | Lưu ý |
| --- | --- | --- | --- |
| Public catalog read | Thường có | Rất ngắn | Cache/stale theo contract |
| User search | Có | Ngắn | Không dùng full scan fallback gây bão |
| User profile update | Có thể 429 | Có nếu có intent/receipt | Không ACK đã commit khi chưa ghi |
| Inventory reservation | Có thể reject | Cần thiết kế state/expiry | Không double reserve |
| Payment capture | Không retry mới mù | Durable workflow | UNKNOWN và reconcile |
| Analytics refresh | Thường có thể hoãn | Có | Ưu tiên foreground traffic |
| CDC projection update | Không được silently drop | Durable queue/replay | Theo dõi lag/retention |
| Telemetry sampling | Có thể drop theo policy | Không nhất thiết | Không đánh đồng với business audit |

**Admission semantics là một phần của nghiệp vụ.** Không mọi request nên được queue vô hạn, cũng không mọi event được phép bỏ.

## 60. Recovery SLO sau burst

Một tiêu chí kiểm chứng tốt:

```text
Burst ends at T0.

Within 2 minutes:
    API p99 returns below threshold.
    Queue backlog below threshold.
    No permanent unknown-outcome growth.

Within 5 minutes:
    CDC projection lag returns below freshness threshold.
```

Các ngưỡng chỉ là ví dụ, cần sản phẩm đặt theo rủi ro.

Đo:

- **Time to p99 recovery.**
- **Time to queue drain.**
- **Time to consumer catch-up.**
- **Time to cleanup unknown writes.**
- **Time to return CPU/IOPS headroom.**
- **Time for autoscaling to settle.**

Nếu hệ đáp ứng peak nhưng recovery dài quá cửa sổ giữa các bursts, burst tiếp theo sẽ đến trên nền backlog chưa giải quyết.

## 61. Autoscaling không thể thay toàn bộ admission control

Autoscaling có độ trễ:

```text
Load spike.
Metrics aggregation.
Scale decision.
Provision pods/nodes.
Warm-up connections/caches.
Shift traffic.
```

Trong khoảng đó, cần:

- Headroom sẵn có.
- Rate limiting.
- Concurrency caps.
- Bounded queues.
- Load shedding.
- Retry budgets.
- Cache/circuit-breaker policy.

Với NoSQL, thêm API pods cũng có thể **tăng tải xuống database**, không làm database tự có capacity hơn. Autoscale cần xem throughput/quorum, shard distribution và hot key bottlenecks thật.

## 62. Đặt giới hạn theo SLO, không chỉ theo peak benchmark

Giả sử ramp test cho thấy:

```text
At 2.000 RPS:
    p99=70ms, errors<0.1%

At 2.400 RPS:
    p99=140ms, errors=0.5%

At 3.000 RPS:
    p99=800ms, errors=12%
```

Nếu business yêu cầu:

```text
p99 <= 150ms
error rate <= 0.5%
```

mốc 2.400 RPS có vẻ sát giới hạn và cần headroom; không nên đặt một global steady admission limit bằng 3.000 chỉ vì có lúc completion đạt mức đó.

Cần tính đến:

- Replication/failover N-1 scenarios.
- Periodic compaction/backup.
- Hot-key skew.
- Read/write mix biến đổi.
- Background CDC/index jobs.
- Margin cho burst.
- Mức độ phát hiện/throttle đúng.

**Rate limit phải được hiệu chỉnh bằng capacity dưới các điều kiện SLO và failure mode, không chỉ một con số throughput tối đa.**

## 63. Bài toán N-1: khi mất một node, limiter có còn an toàn?

Giả sử cluster có 4 nodes và workload steady nằm sát tổng capacity. Khi một node không sẵn:

```text
Capacity hữu hiệu có thể giảm.
Rebalance/replication work tăng.
Tail latency cao hơn.
```

Một limiter đặt theo peak của hệ đủ 4 nodes có thể quá cao trong sự cố.

Cần test:

1. Steady rate bình thường.
2. Tháo một node/partition owner theo quy trình cho phép ở staging.
3. Xem capacity hữu hiệu, latency và error.
4. Điều chỉnh admission/backpressure.
5. Quan sát recovery và repair.
6. Đảm bảo không hạ consistency trái nghiệp vụ.
7. Xem hot keys được chuyển route ra sao.

Không suy capacity N-1 bằng cách lấy `3/4` một cách máy móc; shard distribution, quorum và storage workload có thể làm hiệu ứng phi tuyến.

## 64. Những số cần có trong báo cáo tải

Một báo cáo tối thiểu:

```text
Test ID:
Environment and topology:
Database/driver versions:
Dataset, indexes, partitions:
Consistency/durability settings:
Traffic mix, key distribution:
Load model: open/closed/trace:
Warm-up and measurement windows:
Target offered arrival rate:
Actual scheduled/dispatched rate:
Accepted/completed/failed/rejected rates:
p50/p95/p99 end-to-end latency by operation:
Generator missed slots/CPU:
NoSQL CPU/IOPS/network/compaction:
Per-shard hot key/throttling:
Connections and queue:
Retry amplification:
CDC/read model freshness:
Recovery duration:
Business correctness reconciliation:
```

Mỗi biểu đồ cần gắn **time range và phase markers**. Không chỉ đưa một ảnh “CPU 70%” rồi kết luận server còn 30% capacity: một shard/hot key có thể đang quá tải dù CPU trung bình thấp.

## 65. Một bảng ví dụ kết quả đo có cách diễn giải

Các số hoàn toàn giả định:

| Phase | Target RPS | Dispatched RPS | Completed RPS | p99 end-to-end | Reject/timeout | Projection lag p99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Steady | 1.000 | 1.000 | 995 | 48 ms | 0,3% | 0,4 s |
| Ramp 2× | 2.000 | 2.000 | 1.970 | 110 ms | 1,0% | 1,8 s |
| Burst 5× | 5.000 | 4.700 | 2.100 | 2.800 ms | 40% | 24 s |
| Recovery | 1.000 | 1.000 | 1.250 | 320 ms | 3,0% | 9 s |
| Recovered | 1.000 | 1.000 | 995 | 50 ms | 0,3% | 0,5 s |

Giải thích:

- Burst configured 5.000 RPS nhưng dispatch chỉ 4.700: **generator có missed/dropped load** hoặc rate gate upstream; không được gọi đây là test đủ 5.000 đến backend.
- Completed RPS lúc recovery có thể cao hơn offered vì **xả backlog từ phase trước**, nếu thống kê được tính theo completion timestamp.
- Projection lag có thể hồi phục chậm hơn HTTP latency.
- Reject/timeout ở burst cần phân loại rõ thay vì cộng thành “hệ lỗi”.
- Cần kiểm tra queue/backlog và correctness, không chỉ latency.

## 66. Thử nghiệm đối chứng cho rate limiter

Muốn đánh giá limiter, cần ít nhất hai nhóm có cùng workload:

**A — Không limiter hoặc limiter không ràng buộc** (trong môi trường thử nghiệm an toàn):

```text
Burst 5.000 RPS.
Observe queue, errors, p99, backend saturation.
```

**B — Có admission + token bucket + concurrency cap:**

```text
Same offered 5.000 RPS.
Some requests intentionally receive 429.
Accepted requests may have lower p99.
Backend queue protected.
```

Không kết luận B “xử lý được 5.000 RPS” nếu nó **từ chối 3.000 RPS**. Kết luận đúng có thể là:

> Với offered load 5.000 RPS, limiter bảo vệ 2.000 RPS requests đã được chấp nhận trong latency SLO, từ chối phần còn lại có kiểm soát và tránh timeout/queue growth kéo dài.

Đó là một thành công về **overload behavior**, nhưng không phải tăng raw database capacity.

## 67. Giới hạn riêng cho read và write

Một kiến trúc thường có:

```text
Write commands:
    cần consistency/invariant, có thể đắt hơn.

Read queries:
    có thể scale cache/projection, nhưng một số query rất nặng.

Background:
    reindex, CDC, analytics, compaction.
```

Có thể dùng budgets:

```text
critical writes        -> reserved concurrency
point reads            -> larger pool
expensive search       -> smaller pool
bulk exports           -> low priority, rate-limited
reconciliation workers -> durable backlog with upper bound
```

Lưu ý: **Không được hoãn reconciliation vô hạn chỉ để API p99 đẹp**. Nếu payment unknown hoặc CDC retention gần hết, background work có thể mang rủi ro nghiệp vụ rất cao và cần được ưu tiên theo thời hạn.

## 68. Giới hạn per-shard hoặc per-key khó hơn global quota

Một cluster có thể nhận tổng 10.000 RPS nhưng chỉ chịu được 300 RPS lên một partition nóng theo operation type.

Một global quota 8.000 RPS vẫn cho phép:

```text
8.000 requests/s all to hot partition P1.
```

Vì vậy cần:

- Key-aware admission.
- Limit theo tenant/entity hoặc hash-shard khi phù hợp.
- Adaptive concurrency per destination.
- Cache/materialized view giảm read pressure.
- Queue/single-writer cho hot-key mutations nếu business cho phép.
- Data model/sharding redesign nếu bottleneck là key distribution.
- Không làm lost-update khi serialize writes qua worker.
- Theo dõi per-partition saturation.

**Rate limiter không thay thế thiết kế partition key đúng**; nó chỉ giúp hệ không sụp khi phân bố tải bất lợi.

## 69. Adaptive concurrency: phản hồi theo độ trễ

Một chiến lược có thể điều chỉnh số in-flight dựa trên:

- Latency tăng.
- Queue wait.
- Throttling.
- Error rate.
- Service time và throughput.
- Backend saturation.

Ví dụ ý tưởng:

```text
If latency rises and queue grows:
    reduce allowed concurrency gradually.

If latency stable and errors low:
    probe slightly higher concurrency.
```

Rủi ro:

- Một noisy metric khiến limiter dao động.
- Tăng quá nhanh gây burst.
- Decrease quá mạnh gây underutilization.
- Các instances điều chỉnh đồng thời có thể đồng bộ thành herd.
- Không thể đảm bảo fairness giữa tenants nếu chỉ có một adaptive limiter.

Cần thử với **steady, burst, periodic load và dependency failure**, đồng thời có min/max bounds và rollback.

## 70. Các failure scenarios khi tải tăng

| Kịch bản | Hiệu ứng có thể có | Điều cần kiểm chứng |
| --- | --- | --- |
| Traffic burst 10× | Queue tăng, p99 cao | Rate limit + bounded queue |
| Generator GC pause | Missed slots hoặc catch-up burst | Phân biệt lỗi generator |
| One shard hot | Throttling cục bộ | Per-shard metrics, routing |
| DB node failover | Timeout/unknown writes | Idempotency, consistency |
| Cache invalidation burst | Stampede xuống source | Single-flight/backpressure |
| CDC consumer outage | Projection stale | Lag, replay, retention |
| Broker redelivery | Duplicate processing | Consumer idempotency |
| Client retry storm | Offered RPS nhân lên | Retry budgets + jitter |
| Redis limiter outage | Quota không rõ | Fail-open/closed policy |
| TTL expiry wave | Cache misses đồng loạt | TTL jitter/cache warming |
| Expensive query mix shift | CPU/IO spike dù RPS không đổi | Weighted limits/query plans |
| Transaction conflicts | p99 write tăng | CAS revalidation, hot-key fix |
| Batch backfill overlaps peak | Foreground latency xấu | Background scheduling/quota |
| Network partition | Quorum/read issues | Không downgrade consistency |
| Burst after recovery | Queue chưa xả | Time-to-recovery SLO |

## 71. Các sai lầm trong thiết kế benchmark

**“500 threads nghĩa 500 RPS.”** Không; số luồng là concurrency, còn throughput phụ thuộc latency và think time.

**“Benchmark RPS cố định vì mỗi thread ngủ 10 ms.”** Không nếu request trước block hoặc scheduler trễ.

**“Throughput server ổn nên tải đột biến được xử lý.”** Chưa chắc: offered load có thể vượt completion và backlog tăng.

**“Average latency 50 ms nên p99 ổn.”** Tail latency có thể rất cao.

**“Completed RPS là offered RPS.”** Sai khi có 429, queue, retry, generator drop.

**“Đặt token bucket r=100, B=100 nghĩa mỗi giây không thể nhận hơn 100.”** Bucket có burst credits; phải xét \(B+r\Delta t\).

**“Chỉ cần per-pod limiter.”** N pods có thể nhân tổng quota.

**“429 là sự cố server.”** 429 có thể là từ chối có chủ đích và đúng policy; phải phân biệt với 503/timeouts.

**“Tăng retry là tăng availability.”** Có thể tạo retry storm.

**“Queue vô hạn sẽ hấp thụ mọi burst.”** Queue chỉ dời vấn đề sang memory và latency.

**“Cache hit 95% lúc steady sẽ giữ nguyên lúc flash crowd.”** Key distribution và TTL có thể đổi mạnh.

**“Một shard CPU 100% nhưng cluster CPU 40% nghĩa còn dư nhiều capacity.”** Có thể đã chạm bottleneck per-key.

**“Thêm API pods giúp NoSQL nhanh hơn.”** Có thể chỉ làm tải DB tăng.

**“Thử 30 giây đủ đại diện cả ngày.”** Compaction, GC, TTL, repair có thể xuất hiện muộn.

**“Chạy từ cold start rồi gọi steady state.”** Nếu chưa warm-up, metrics trộn nhiều pha.

**“Benchmark đọc/ghi với consistency yếu rồi áp kết quả cho transaction mạnh.”** Không cùng semantics.

**“Tính p99 toàn bài bằng trung bình p99 mỗi giây.”** Không đúng toán thống kê.

**“Một timeout của write nghĩa write chắc chắn không commit.”** Có thể commit rồi ACK mất.

**“Limiter có tác dụng nên backend tăng capacity.”** Limiter chỉ điều chỉnh offered/admitted work, không tự làm tăng sức xử lý vật lý.

## 72. Bài thực hành 1: phân biệt open và closed workload

Cho hai test:

```text
Test A:
    100 virtual users.
    Each waits for response then sends next.

Test B:
    1.000 arrivals/s independent of response.
    Max in-flight = 500.
```

Yêu cầu:

1. Mô hình nào closed-loop, mô hình nào open-loop?
2. Khi server p99 tăng từ 50ms lên 2s, offered rate của hai mô hình thay đổi thế nào?
3. Test nào dễ gặp coordinated omission nếu diễn giải sai?
4. Khi B không có permits, phải ghi số requests bị drop ra sao?
5. Tại sao cần đo generator schedule lateness?
6. Có thể lấy kết quả A để kết luận server ổn ở 1.000 RPS hay không?

Gợi ý: xác định arrival process trước khi nhìn throughput.

## 73. Bài thực hành 2: tính backlog khi burst

Một dịch vụ có:

```text
Normal incoming:    1.000 ops/s.
Capacity:           2.000 ops/s.
Burst incoming:     5.000 ops/s for 15s.
Post-burst incoming:1.000 ops/s.
```

Giả sử queue không giới hạn, không retry, công suất không đổi.

Câu hỏi:

1. Backlog tăng bao nhiêu sau 15 giây?
2. Khi quay về 1.000 ops/s, còn bao nhiêu công suất để xả queue?
3. Cần bao lâu xả hết theo mô hình đơn giản?
4. Điều gì xảy ra nếu queue chỉ chứa 10.000 tasks?
5. Tác động của timeout và retry lên phép tính?

Gợi ý: tăng backlog \((5.000-2.000)\times15\). Capacity dư sau burst \(2.000-1.000\).

## 74. Bài thực hành 3: token bucket

Giới hạn:

```text
Refill rate r = 200 tokens/s.
Capacity B = 500 tokens.
Cost = 1 token/request.
Bucket initially full.
```

Hãy:

1. Tính số requests tối đa có thể cấp ngay tại T0.
2. Ước lượng tổng quota upper bound trong khoảng 5 giây theo mô hình đơn giản.
3. Mô tả vì sao fixed window khác token bucket.
4. Nếu có ba pods, mỗi pod có bucket riêng, tổng burst có thể là bao nhiêu?
5. Đề xuất distributed limiter khi yêu cầu global quota.
6. Nếu limiter Redis bị mất, nên fail-open hay fail-closed cho một API thanh toán?

Gợi ý: câu 6 phụ thuộc correctness/capacity/availability policy, không có câu trả lời chung.

## 75. Bài thực hành 4: phát hiện hot partition

Hai bài tải:

```text
A:
    2.000 RPS GET phân tán trên 1 triệu product IDs.

B:
    2.000 RPS UPDATE cùng inventory key.
```

Hãy đo:

- Per-shard/partition throughput.
- CAS/conflict rate.
- p95/p99.
- Retry amplification.
- Backend CPU/IOPS.
- Query fan-out.
- Queue wait.
- Ràng buộc correctness khi retry.

Sau đó đề xuất một thay đổi data model hoặc concurrency control cho workload B.

## 76. Bài thực hành 5: load generator bị quá tải

Một công cụ cấu hình:

```text
Target offered:       8.000 RPS.
Scheduled:            8.000 RPS.
Dispatched:           5.200 RPS.
Generator CPU:        100%.
Completed success:    5.000 RPS.
```

Câu hỏi:

1. Có được kết luận server chịu được 8.000 RPS không?
2. Có thể kết luận gì một cách chắc chắn hơn?
3. Nên thay đổi generator như thế nào?
4. Vì sao nhiều threads không luôn giải quyết được?
5. Cần giữ metric nào khi generator tự drop request?
6. Khi dùng thêm generator nodes, cần đồng bộ arrival plan và results ra sao?

## 77. Bài thực hành 6: phân tích sau burst

Một hệ:

```text
Before burst:
    API p99 50ms, CDC lag 1s.

During 5x burst:
    API p99 1s, CDC lag 50s.

Five minutes after burst:
    API p99 60ms, CDC lag 40s.
```

Yêu cầu:

1. API đã hồi phục chưa theo latency SLO?
2. Read model đã hồi phục chưa?
3. Nếu trang đơn hàng dùng CDC projection, người dùng có thể thấy gì?
4. Cần bổ sung metrics và cảnh báo nào?
5. Có nên tăng API RPS limit trước khi consumer catch up?
6. Làm sao chứng minh không bị mất events do retention?

## 78. Một ma trận kiểm thử

| Mã | Kịch bản | Tiêu chí |
| --- | --- | --- |
| T01 | Steady fixed arrivals | Actual dispatched theo target, generator healthy |
| T02 | Closed-loop users | Báo đúng workload, không suy offered cố định |
| T03 | Generator pause | Phát hiện missed slots/schedule lag |
| T04 | Burst 4× trong 30s | Đo p99/error/backlog/recovery |
| T05 | Microburst 100ms | Queue/socket/hot partition vẫn an toàn |
| T06 | Repeated burst train | Backlog được xả giữa các xung |
| T07 | Ramp tới saturation | Xác định điểm gãy trong SLO |
| T08 | Soak dài | Không có trend rò rỉ hoặc lag tăng vô hạn |
| T09 | Uniform vs skew keys | Nhận diện hot partition |
| T10 | Cache hit ratio giảm | Source fallback nằm trong budget |
| T11 | Retry storm | Retry budget và jitter có tác dụng |
| T12 | API pod autoscale | Global quota không bị nhân vô ý |
| T13 | Limiter Redis failover | Fail-open/closed theo policy |
| T14 | Token bucket reset/TTL | Không cấp sai burst credits |
| T15 | Rate + concurrency gate | Không có unbounded in-flight |
| T16 | Queue full | Reject/async behavior đúng contract |
| T17 | Write timeout after commit | Không duplicate business effect |
| T18 | NoSQL node failover | Consistency/correctness giữ đúng |
| T19 | CDC consumer stopped | Lag/retention alert và catch-up |
| T20 | Expensive-query burst | Weighted quota hoặc workload isolation |
| T21 | Tenant A noisy | Tenant B không mất fairness quá contract |
| T22 | Hot last-item reservation | CAS/atomic invariant không bị phá |
| T23 | Projection stale after burst | Freshness SLO được đo |
| T24 | Recovery phase | Time-to-recover đạt mục tiêu |
| T25 | Read consistency mix | Không đánh tráo semantics |
| T26 | Client/server latency split | Có đủ histogram theo phase |
| T27 | Generator overload | Kết quả được đánh INCONCLUSIVE |
| T28 | N-1 node | Headroom và limiter đúng |
| T29 | TTL/compaction cycle | Tail latency được quan sát |
| T30 | Batch/backfill at peak | Background jobs được kiểm soát |

## 79. Acceptance criteria

| Mã | Yêu cầu | Bằng chứng |
| --- | --- | --- |
| AC-01 | Mô hình workload (open/closed) được nêu rõ | Test configuration |
| AC-02 | Có offered, scheduled, dispatched, admitted, completed | Counter/trace review |
| AC-03 | Generator không âm thầm giảm load | Schedule lateness/missed slots |
| AC-04 | End-to-end latency histogram đúng | Per-phase p50/p95/p99 và sample count |
| AC-05 | RPS không bị nhầm với concurrency | Test documentation |
| AC-06 | Có steady, ramp, burst, recovery, soak | Test plan |
| AC-07 | Burst duration và peak rõ | Arrival time series |
| AC-08 | Key distribution phản ánh workload | Uniform/skew/hot-key tests |
| AC-09 | Read/write/query mix và payload được giữ | Workload profile |
| AC-10 | Không thay consistency/durability khi so sánh | Driver/database config |
| AC-11 | Rate limit có scope và units rõ | Limiter contract |
| AC-12 | Token bucket xử lý capacity/refill đúng | Boundary tests |
| AC-13 | Multi-pod không vượt global quota ngoài policy | Distributed quota test |
| AC-14 | Concurrency và queue có giới hạn | Overload test |
| AC-15 | Retry có jitter/budget và được đo | Fault load test |
| AC-16 | Quota rejections phân biệt với hạ tầng lỗi | Error taxonomy |
| AC-17 | Hot partitions được theo dõi | Per-shard metrics |
| AC-18 | Cache stampede được kiểm soát | Cache miss burst |
| AC-19 | CDC/read projections đạt freshness target | Source-to-view lag |
| AC-20 | Sau burst backlog xả trong RTO/SLO | Recovery timeline |
| AC-21 | Node failover không phá nghiệp vụ | N-1 fault test |
| AC-22 | Client write timeout không tạo duplicate effects | Idempotency test |
| AC-23 | Background work không che capacity issue | Soak/compaction observation |
| AC-24 | Limiter failover có policy rõ | Redis/gateway failure test |
| AC-25 | Có fairness và isolation cho tenant/workload | Noisy-neighbor test |
| AC-26 | Không tuyên bố capacity vượt tải thực phát | Report audit |
| AC-27 | Có chi phí bổ sung của rate limiter | Dependency latency/cost report |
| AC-28 | Headroom được chọn theo SLO, không chỉ max RPS | Capacity decision record |

Ngưỡng từng mục phải được xác định từ yêu cầu sản phẩm, cấu hình NoSQL, topology và khả năng chịu lỗi cụ thể.

## 80. Runbook thực hiện bài đo tải

### Pha 1 — Chốt câu hỏi và phạm vi

1. Xác định đang đo **capacity**, **overload behavior**, **burst tolerance**, **fairness** hay **recovery**.
2. Chốt throughput, latency, error, freshness và correctness SLO.
3. Xác định loại thao tác/keys, read-write mix, payload và consistency.
4. Xác định dữ liệu test có thể reset, không tác động người dùng thật.
5. Xác định hardware/topology, version và autoscaling policy.
6. Đánh dấu mọi tầng có limiter và retry.

### Pha 2 — Chuẩn bị thí nghiệm

7. Chuẩn bị dataset/indexes/tombstone và dữ liệu có skew.
8. Warm-up nếu đang đo warm steady state.
9. Kiểm tra load generator tự đủ CPU/network/FDs.
10. Định nghĩa open/closed arrival model và think time.
11. Cấu hình max in-flight, queue và timeout/deadline.
12. Kiểm tra đo `scheduled`, `dispatched` và `generator rejected`.
13. Cấu hình log/metrics per phase, p99 histogram, stream lag.
14. Chuẩn bị rollback/stop conditions nếu error/correctness vượt giới hạn.

### Pha 3 — Thực hiện

15. Chạy baseline và xác nhận generator rate.
16. Chạy steady tại mức dự kiến.
17. Chạy ramp để phát hiện điểm gãy.
18. Chạy burst theo độ lớn, thời gian và key skew.
19. Chạy recovery đủ lâu để backlog xả.
20. Chạy repeated bursts nếu thực tế có nhiều chiến dịch liên tiếp.
21. Chạy soak qua các chu kỳ background work.
22. Thử limiter on/off hoặc các policy đối chứng trong staging an toàn.
23. Thử N-1/failover nếu mục tiêu cần resilience.

### Pha 4 — Đối soát kết quả

24. So offered/accepted/completed/failed RPS.
25. Kiểm tra generator có đạt lịch phát không.
26. Xem p95/p99 theo operation và từng phase.
27. Tách 429 business quota, 503 overload, timeout và CAS conflict.
28. Xác định partition/hot key bottleneck thay vì chỉ xem average cluster.
29. Xem cache hit/fallback, connection pool và retry attempts.
30. Xem CDC lag, consumer backlog, projection freshness.
31. Đối soát write effects, idempotency và trạng thái UNKNOWN.
32. Tính time-to-recovery và sai lệch với SLO.

### Pha 5 — Quyết định và lưu báo cáo

33. Chọn steady operating limit có headroom.
34. Chọn burst capacity \(B\) và refill rate \(r\) có chứng cứ.
35. Chọn concurrency/queue bounds và overload response.
36. Đặt per-tenant/per-operation quotas khi cần fairness.
37. Điều chỉnh data model hoặc query plans nếu hot partition/index là gốc.
38. Lập cảnh báo theo p99, backlog, throttling và freshness.
39. Ghi rõ **bảo đảm nào đã được kiểm chứng, giới hạn nào còn chưa kiểm chứng**.
40. Lặp lại sau thay schema, index, driver, topology hoặc traffic profile lớn.

## Kết luận

**Tải đều, tải đột biến và giới hạn tốc độ gửi yêu cầu** là ba mặt của cùng bài toán kiểm chứng hiệu năng NoSQL: **yêu cầu đến theo cách nào, hệ chấp nhận và hoàn tất được bao nhiêu, và điều gì xảy ra khi tốc độ đến vượt khả năng phục vụ?** Một con số throughput trung bình, một vòng lặp 500 threads hoặc một histogram average latency không đủ mô tả hệ.

Hãy bắt đầu bằng **workload có nghĩa**: loại thao tác, kích thước dữ liệu, phân bố khóa/tenant, read/write mix, consistency và cache behavior. Phân biệt **open-loop arrivals** với **closed-loop clients**; tránh coordinated omission và giám sát cả khả năng của load generator. Trong từng phase, đo **offered, dispatched, admitted, completed, rejected, p95/p99, queue/in-flight, per-partition saturation, retries và CDC lag**. Đặc biệt cần đo **thời gian hồi phục sau burst**, vì backlog có thể còn tồn tại lâu sau khi dòng yêu cầu đã giảm.

Các cơ chế **token bucket, sliding window, leaky-bucket shaping, concurrency limit, bounded queue, backpressure và retry budget** giúp hệ phản ứng có kiểm soát khi quá tải. Nhưng **rate limiting không tự tăng capacity** và không thay thiết kế partition key, query path hay idempotency. Một thiết kế đáng tin cậy phải từ chối/hoãn đúng theo hợp đồng, giữ tính đúng khi timeout/failover và có bằng chứng rằng những yêu cầu đã nhận đạt SLO, còn những yêu cầu bị từ chối được tính công khai.

Mục tiêu cuối cùng không phải tạo một biểu đồ RPS thật cao, mà là **biết giới hạn tải có thể phục vụ an toàn, cách điều tiết burst để tránh sụp đổ và cách đo được toàn bộ quá trình hệ trở lại trạng thái khỏe mạnh**.
