# Kiểm soát hiện tượng bỏ sót độ trễ khi bộ phát tải cũng bị chậm

Một nhóm phát triển Java đo hiệu năng một cụm NoSQL bằng cách chạy 100 worker đồng thời. Mỗi worker gửi truy vấn mới **ngay sau khi** truy vấn trước hoàn tất. Khi database khỏe, mỗi truy vấn mất 10 ms; báo cáo cho thấy khoảng 10.000 lượt truy vấn/giây. Khi database quá tải, thời gian phản hồi tăng lên 1 giây. Lúc này 100 workers chỉ gửi được khoảng 100 lượt/giây. Có thể bộ đo vẫn ghi nhận đa số request đã hoàn tất khá nhanh trong một đoạn kiểm thử hoặc báo cáo percentile gây hiểu nhầm nếu những thời điểm hệ thống nghẽn có ít mẫu.

Vấn đề nằm ở vòng phản hồi: **hệ thống chậm làm chính bộ phát tải chậm, và bộ phát tải chậm lại giảm số yêu cầu tác động lên hệ thống**. Những lượt yêu cầu lẽ ra đến trong lúc hệ thống nghẽn không được phát, cũng không có thời gian chờ để ghi vào histogram. Đây là một dạng của **coordinated omission (CO)** — hiện tượng bỏ sót một phần thời gian chờ/độ trễ do lịch sinh yêu cầu phụ thuộc vào tiến độ phản hồi hay khả năng chạy của bộ phát tải.

Bài học thuộc **Database No SQL → Hiệu năng và đo tải**, tập trung vào cách tránh hiện tượng **bỏ sót độ trễ khi chính load generator cũng bị chậm**. Ta sẽ phân biệt closed-loop và open-loop, thiết kế lịch phát độc lập, ghi nhận thời điểm dự kiến/phát thực tế/hoàn thành, kiểm soát generator backlog và dropped attempts, sử dụng histogram/percentiles đúng nghĩa, đánh giá coordinated-omission correction, kiểm tra sức khỏe bộ phát tải Java và đo NoSQL khi quá tải.

> **Nguyên tắc:** Muốn biết hệ thống ứng xử ra sao trước **lượng yêu cầu dự kiến đến**, phải đo được lượng yêu cầu **được lên lịch, thực sự gửi, hoàn tất, thất bại và không thể gửi**. Không được chỉ tính latency của những request đã hoàn tất trong khi load generator tự giảm tốc. Một p99 đẹp không có ý nghĩa nếu tốc độ phát thực tế thấp hơn mục tiêu hoặc generator bị kẹt đúng lúc database chậm nhất.

> **Phạm vi:** Bài dùng mô hình toán, Java 21 và ví dụ benchmark giả định để diễn giải. Không phải mọi công cụ đo tải đều có cùng scheduling/clock/histogram semantics. Trước khi dùng số đo để ra quyết định capacity, cần kiểm tra cơ chế **arrival generation, timestamping, timeout accounting, retry accounting và generator saturation** của công cụ và phiên bản đang chạy.

## 1. Một thí nghiệm tưởng đúng nhưng có vấn đề

Giả sử một Java test:

~~~~java
while (running) {
    long started = System.nanoTime();
    repository.readOneKey();
    long completed = System.nanoTime();

    latencyRecorder.record(completed - started);
}
~~~~

Nếu chạy nhiều threads, đoạn mã có vẻ đo đúng thời gian của mỗi read. Nhưng **thời điểm bắt đầu request tiếp theo phụ thuộc vào thời điểm request trước đã hoàn tất**.

### 1.1. Khi NoSQL phản hồi nhanh

Mỗi worker mất 10 ms/request:

~~~~text
Worker A: [req 10ms][req 10ms][req 10ms][req 10ms]...
Worker B: [req 10ms][req 10ms][req 10ms][req 10ms]...
~~~~

Với 100 workers, throughput lý tưởng gần:

\[
\frac{100}{0{,}010}=10.000\ \text{request/s}
\]

Giả định workers luôn bận và bỏ qua overhead.

### 1.2. Khi NoSQL chậm

Mỗi request mất 1 giây:

~~~~text
Worker A: [-------------- request 1 s --------------] next
Worker B: [-------------- request 1 s --------------] next
~~~~

Với cùng 100 workers, throughput lý tưởng giảm còn:

\[
\frac{100}{1}=100\ \text{request/s}
\]

Hệ thống **không còn bị tác động bởi 10.000 request/s**; test đã tự giảm tải theo latency. Nếu workload production thực sự có 10.000 arrivals/s độc lập, kết quả này không mô tả phản ứng trước đúng offered load.

### 1.3. Vì sao latency histogram có thể bị đánh lừa?

Khi hệ chậm, một worker giữ một request trong thời gian dài và không gửi nhiều request khác. Các thời điểm đáng lẽ có arrivals hoặc queueing không tạo mẫu mới. Tỷ lệ mẫu ở thời gian nghẽn bị giảm; một percentile tổng hợp có thể phản ánh quá nhiều giai đoạn nhanh.

Không phải mọi closed-loop test đều báo latency thấp: request đang chạy chậm vẫn được đo 1 giây nếu hoàn tất và được ghi đúng. Lỗi là **phân phối samples và offered workload khác với workload cần đánh giá**, chứ không phải đồng hồ luôn đo sai request đang chạy.

## 2. Coordinated omission chính xác là gì?

**Coordinated omission** xảy ra khi quá trình thu thập latency bỏ qua những khoảng chờ/những arrivals được mô hình hóa vì việc phát hoặc đo một request mới phụ thuộc vào việc request trước hoàn tất hoặc do scheduler/generator bị trì hoãn.

Nó thường xuất hiện trong:
- Benchmark closed-loop với số workers/connections cố định.
- Một generator định gửi fixed RPS nhưng tick scheduler bị block.
- Thread pool generator bị cạn, không tạo logical attempts đúng lịch.
- Chỉ đo từ thời điểm thực sự gửi, bỏ phần chờ trong queue của generator.
- Chỉ ghi latency request thành công; bỏ timeout/dropped/shed.
- Một script sleep sau response thay vì theo kế hoạch thời gian tuyệt đối.
- Client driver tự backpressure nhưng báo cáo không ghi nhận offered-vs-achieved.
- Một phép đo chỉ tập trung vào completed ops trong khi outstanding ops còn rất nhiều lúc kết thúc.

### 2.1. CO không có nghĩa máy chủ đã trả lời sai

Mỗi request được gửi có thể thật sự mất 10 ms theo stopwatch của client. Nhưng nếu 1.000 logical arrivals bị bỏ qua vì generator tạm dừng, histogram của **những request đã gửi** không thể tự mô tả trải nghiệm của toàn bộ workload được mô phỏng.

### 2.2. CO không phải lỗi của percentiles

Tính toán p99 đúng trên tập samples không giúp nếu tập samples:
- Thiếu requests ở giai đoạn nghẽn.
- Bỏ những request never completed.
- Không chứa queue delay trước thời điểm send.
- Đã bị load generator tự throttling.
- Có các attempt retries được đếm không đúng.

**Sai tập mẫu thì percentile tính đúng vẫn có thể trả lời sai câu hỏi.**

### 2.3. CO khác lỗi đồng hồ

Một số vấn đề có thể xảy ra đồng thời:
- Clock skew giữa máy generator và database.
- Timer resolution kém.
- GC pause làm scheduler trễ.
- CPU contention khiến sample timestamp bị lấy muộn.
- Coordinated omission do không tạo logical arrivals.

Cần phân biệt chúng để chẩn đoán.

### 2.4. CO cũng có thể nằm ở client phía người dùng thật

Một người dùng thường không gửi request tiếp theo trước khi giao diện hoàn tất thao tác hiện tại; đó là **closed-loop user behavior** hợp lệ cho một số mô hình. Nếu mục tiêu là mô phỏng đúng một nhóm người dùng như vậy, closed-loop không tự “sai”.

CO trở thành vấn đề khi muốn suy ra latency dưới **arrival workload độc lập** hoặc so sánh một SLO mà test đã không tái tạo, nhưng vẫn dùng closed-loop result để tuyên bố hệ chịu được fixed RPS.

## 3. Closed-loop và open-loop

| Thuộc tính | Closed-loop | Open-loop theo lịch arrivals |
| --- | --- | --- |
| Tạo request mới | Sau response/think time | Theo lịch độc lập với response |
| Số outstanding | Thường giới hạn theo users/workers | Có thể tăng khi latency tăng |
| Offered rate khi source chậm | Thường giảm | Vẫn có lịch arrivals mục tiêu |
| Tương tự hành vi nào? | User tuần tự, một số session workflows | External arrivals, hệ có independent clients |
| Nguy cơ đo | CO nếu dùng để mô tả fixed-arrival workload | Generator saturation/drops nếu không đủ năng lực |
| Cần đo | Concurrency, think time, achieved RPS | Scheduled, sent, completed, rejected, lag |
| Dùng khi | Mô hình tương tác có dependency rõ | Đo khả năng phục vụ tải đến có kiểm soát |

### 3.1. Closed-loop không xấu trong mọi trường hợp

Một workflow:
1. User search rooms.
2. Chờ kết quả.
3. Chọn phòng.
4. Chờ booking draft.
5. Confirm.

Các bước có **quan hệ nhân quả**: không thể confirm trước khi có draft. Một virtual user closed-loop có thể mô phỏng đúng workflow. Nhưng nếu thực tế có 100.000 users độc lập cùng search lúc 09:00, phát tải theo arrival schedule cho các workflows là một vấn đề khác.

### 3.2. Open-loop đúng nghĩa

Một generator định 2.000 requests/s:
- Cứ 0,5 ms có một **logical scheduled arrival**, bất kể requests trước đã xong chưa.
- Nếu không có capacity phát, phải **ghi nhận thiếu capacity**, không tự kéo giãn lịch và gọi đó là 2.000 RPS.
- Đơn vị cần đo là logical arrival, attempt, completion và outcome.

### 3.3. Open-loop có thể vẫn mắc CO

Nếu dùng một scheduler nhưng scheduler bị GC pause 2 giây, nó có thể không chạy những ticks đã định. Nếu chỉ đo các requests thực sự phát sau pause, những logical arrivals trong pause bị bỏ sót.

Do đó một công cụ ghi nhãn “constant throughput/open-loop” chưa chắc đủ. Phải xem nó xử lý **late schedule ticks** và **dropped/missed arrivals** như thế nào.

## 4. Ba mốc thời gian tối thiểu

Với logical attempt i, cần tách:

- \(S_i\): **scheduledArrivalAt** — thời điểm workload model dự kiến request đến.
- \(D_i\): **actualDispatchAt** — thời điểm client thực sự bắt đầu phát request vào transport/driver.
- \(C_i\): **completedAt** — thời điểm result/error/timeout được ghi nhận.

Khi dùng cùng một monotonic clock trong generator:

\[
L_{\text{scheduler},i} = \max(0,D_i-S_i)
\]

\[
L_{\text{dispatch-to-completion},i} = C_i-D_i
\]

\[
L_{\text{schedule-to-completion},i} = C_i-S_i
\]

Trong trường hợp đơn giản \(S_i \le D_i \le C_i\):

\[
L_{\text{schedule-to-completion}} =
L_{\text{scheduler}} +
L_{\text{dispatch-to-completion}}
\]

### 4.1. Từng số trả lời câu hỏi khác nhau

| Số đo | Trả lời |
| --- | --- |
| Scheduler lag | Generator có phát đúng lịch không? |
| Dispatch-to-completion latency | Một attempt đã được gửi chờ kết quả bao lâu theo client? |
| Schedule-to-completion latency | Logical scheduled arrival phải chờ tổng cộng bao lâu? |
| Service-side processing time | Database xử lý nội bộ bao lâu? |
| Pool acquisition wait | Request chờ connection trong client pool bao lâu? |
| Queueing before send | Bị giữ tại generator/application trước transport bao lâu? |

Không phải tất cả ba mốc đủ cho full end-to-end user latency nếu còn proxy, queue hay retry tại các tầng khác. Nhưng chúng ngăn lỗi phổ biến: **bỏ hẳn khoảng generator chậm**.

### 4.2. Một timeline rõ ràng

~~~~text
Time axis (ms)
0                    30                 120           170
|--------------------|------------------|-------------|
Scheduled S=0        Dispatch D=30      DB result     Completed C=170
                     ^                   ^             ^
                     queue/scheduler lag DB work       callback observed

Scheduler lag:       30 ms
Dispatch->completion:140 ms
Scheduled->completion:170 ms
~~~~

Nếu chỉ đo từ D, sẽ báo 140 ms và bỏ 30 ms trước send. Với SLA gắn vào scheduled-arrival của workload, 170 ms mới là số cần đánh giá.

### 4.3. Scheduled time là một giả định của workload

Một scheduled attempt chưa thực sự tới NoSQL không có **measured server latency**. Nếu generator quá tải và không gửi được:
- Không nên bịa ra response latency thực.
- Phải ghi missed/dropped arrival.
- Có thể đánh giá nó là load-generation failure hoặc mô hình hóa latency giả định theo một phương pháp correction riêng, nhưng cần ghi nhãn.

### 4.4. Monotonic clock thay vì wall-clock

Trong cùng JVM, dùng System.nanoTime để đo elapsed intervals:
- Tránh NTP/clock adjustment làm thời gian âm hoặc nhảy.
- Không so System.nanoTime giữa hai processes/machines.
- Lưu UTC timestamp riêng để correlate traces/events, không trừ raw wall-clock hai machines làm latency chuẩn.

Nếu muốn server-side timings, dùng span/trace với clock semantics phù hợp hoặc đo riêng từng hop.

## 5. Một phép tính cho thấy mẫu bị mất

Giả sử mục tiêu là 1.000 scheduled arrivals/s, tức một arrival mỗi 1 ms. Một sự cố khiến generator hoặc database không thể tiến triển trong 2 giây.

Số arrivals theo lịch trong khoảng đó:

\[
N_{\text{planned}}=1.000\times2=2.000
\]

Nếu generator chỉ xử lý một synchronous call đang kẹt và **không tạo 1.999 arrivals còn lại**, histogram không có mẫu latency từ 1.999 logical arrivals ấy.

### 5.1. Điều gì xảy ra với p99?

Một run 10 giây gồm:
- Nhiều samples 5–10 ms khi hệ khỏe.
- Một hoặc ít samples chậm vì worker bị block.
- Hàng nghìn arrivals theo workload kỳ vọng không có mẫu.

p99 của samples đã ghi có thể vẫn rất thấp nếu slow samples chiếm tỷ lệ nhỏ, dù một hệ nhận independent arrivals ở cùng tốc độ có thể đã queue/drop phần lớn lưu lượng. Không thể suy từ p99 ấy rằng system đáp ứng 1.000 independent arrivals/s.

### 5.2. Không có một p99 “đúng” nếu workload chưa định nghĩa

Cần nói rõ:
- Arrivals ở mức request hay transaction/session?
- Có queue khi server nghẽn không?
- Request quá deadline thì drop hay retry?
- Client có chấp nhận backpressure không?
- Mỗi user có think time/causal dependencies không?

Chỉ sau đó mới xác định latency distribution cần đo.

## 6. Offered load, achieved throughput và completion rate

Ít nhất cần ba số:

- **Planned/Offered load:** số logical arrivals workload lên lịch.
- **Attempted/sent load:** số requests thực sự được đưa tới client transport/driver.
- **Completed load:** số requests có terminal outcome trong cửa sổ đo.

Thêm:
- Dropped before send.
- Rejected by admission.
- Timed out.
- Failed.
- Still in flight.
- Retried.
- Cancelled.

### 6.1. Công thức

Với thời gian kiểm thử T:

\[
\lambda_{\text{planned}}=\frac{N_{\text{scheduled}}}{T}
\]

\[
\lambda_{\text{sent}}=\frac{N_{\text{sent}}}{T}
\]

\[
\lambda_{\text{completed}}=\frac{N_{\text{completed}}}{T}
\]

\[
R_{\text{delivery}}=\frac{N_{\text{sent}}}{N_{\text{scheduled}}}
\]

Nếu planned=10.000/s nhưng sent=2.000/s:
- Không gọi run đó là kiểm thử đạt 10.000 RPS.
- Cần báo generator unable to deliver 80% logical arrivals.
- Sau khi xử lý capacity generator mới dùng kết quả để đánh giá source ở desired offered rate.

### 6.2. Completed không nhất thiết bằng sent trong cửa sổ ngắn

Các requests còn in-flight tại cuối cửa sổ; completion rate có thể thấp hơn send rate trong quá tải. Nếu kết thúc đo và chỉ lấy completed samples:
- Các slowest requests còn pending bị bỏ khỏi latency histogram.
- p99 bị optimistic.

Cần final drain window hoặc ghi chúng là incomplete/timeout theo hợp đồng.

### 6.3. Retries làm gì với offered load?

Một logical request có thể tạo ba attempts:

~~~~text
Logical request R-901
    attempt #1 -> timeout
    attempt #2 -> retry
    attempt #3 -> success
~~~~

Báo cáo cần phân biệt:
- Logical arrivals.
- Physical attempts.
- Success logical requests.
- Retry amplification.
- End-to-end logical latency từ lần scheduled đầu tới final outcome.

Nếu chỉ đo latency attempt #3, sẽ bỏ thời gian chờ attempts #1/#2.

## 7. Một mô hình result đầy đủ

Một record có thể gồm:

~~~~json
{
  "runId": "nosql-load-459",
  "logicalRequestId": "req-000091",
  "attemptId": "req-000091-1",
  "operation": "GET_BOOKING",
  "tenantClass": "standard",
  "keyDistribution": "zipfian",
  "scheduledOffsetMicros": 91000,
  "dispatchOffsetMicros": 95000,
  "completionOffsetMicros": 220000,
  "outcome": "SUCCESS",
  "httpOrDriverError": null,
  "retryIndex": 0,
  "partitionClass": "hot",
  "bytesReceived": 421
}
~~~~

Cần gắn runId và một origin/clock domain thống nhất. Offsets được tính so với monotonic start trong **cùng process**, không dùng chúng như timestamps UTC liên máy.

### 7.1. Các outcome khác nhau

| Outcome | Ý nghĩa | Có dispatch latency? |
| --- | --- | --- |
| SUCCESS | Request gửi và nhận kết quả hợp lệ | Có |
| DB_ERROR | Request gửi nhưng source trả error | Có |
| CLIENT_TIMEOUT | Request đã gửi nhưng hết client deadline | Có elapsed-to-timeout, chưa biết response cuối |
| REJECTED | Admission/pool/client không nhận | Có thể chỉ có scheduled-to-reject |
| SCHEDULE_MISSED | Đã đến lịch nhưng generator không kịp phát | Không có measured service latency |
| DROPPED_BY_GENERATOR | Load generator chủ động bỏ | Không có measured service latency |
| CANCELLED | Logical request bị hủy | Đo tới cancellation và lý do |
| STILL_IN_FLIGHT | Chưa có terminal outcome tại snapshot | Không được tự loại khỏi counters |
| RETRY_SCHEDULED | Một attempt khác sẽ được tạo | Không tính là logical completion |

### 7.2. Đừng trộn outcome với latency

p99 của **successful requests** hữu ích, nhưng phải luôn đi kèm:
- Success rate.
- Deadline miss rate.
- Error rate.
- Drop/reject rate.
- Achieved load.
- In-flight count.

Nếu 99% requests bị drop, p99 của 1% successes có thể rất đẹp nhưng SLO tổng thể vẫn thất bại.

### 7.3. Timeouts là dữ liệu bị censor

Nếu timeout ở 1 giây:
- Ta biết request **chưa hoàn tất hợp lệ trong 1 giây**.
- Không biết latency thực sự nếu nó được phép chạy tiếp.
- Không nên ghi timeout như một success latency đúng 1 giây rồi coi percentile đầy đủ.
- Ghi timeout outcome và duration-to-timeout; dùng SLO success-within-deadline là chính.
- Khi có recovery tracing, có thể đo completion eventual riêng.

## 8. Đo độ trễ từ mốc nào cho đúng?

Có nhiều câu hỏi:

1. **Transport latency:** từ lúc gửi tới lúc callback nhận.
2. **Logical arrival-to-outcome:** từ mốc workload scheduled tới terminal outcome.
3. **End-user workflow latency:** từ thao tác user tới hoàn thành business workflow.
4. **Server processing latency:** từ lúc server nhận/dispatch tới lúc xử lý xong.
5. **Queue waiting time:** thời gian chờ trước khi server hoặc driver bắt đầu.

Mốc đo đúng phụ thuộc câu hỏi. Đừng thay một metric cho tất cả.

### 8.1. Một bảng báo cáo lý tưởng

| Metric | Phân phối cần báo |
| --- | --- |
| Planned-to-dispatch lag | p50/p95/p99/max |
| Dispatch-to-completion success latency | p50/p95/p99/p99.9 |
| Planned-to-terminal success latency | p50/p95/p99/p99.9 |
| Deadline miss | Count/rate, gồm timeout/drop/reject theo contract |
| Actual source response latency | p50/p95/p99 và errors |
| Generator CPU/scheduler delay | Tài nguyên và tick lag |
| Offered/sent/completed | RPS theo cửa sổ ngắn |

### 8.2. Latency không bao gồm những requests chưa bao giờ phát

Không tự tuyên bố schedule-to-completion latency cho SCHEDULE_MISSED. Đây là lý do phải có một **đường báo cáo riêng về độ phủ lịch phát**.

### 8.3. Measuring at wrong boundary

Nếu một connection pool chờ 300 ms, database query chạy 20 ms:
- Driver chỉ đo actual network send→response có thể báo 20 ms.
- API caller chịu 320 ms.
- Generator nếu đo từ trước pool acquisition sẽ thấy toàn bộ.
- Nếu test “database query latency” chỉ bao gồm service time thì có thể đúng cho mục tiêu riêng, nhưng không nói được user-visible latency.

## 9. Histogram, percentile và lựa chọn cửa sổ

Một histogram gom những latency samples vào các buckets theo resolution/capacity.

### 9.1. Percentiles

- p50: 50% samples có latency không lớn hơn khoảng giá trị đó.
- p95: 95%.
- p99: 99%.
- p99.9: 99,9%.

Không được cộng trung bình p99 của mỗi node rồi gọi là p99 toàn hệ; cần merge **histogram/distribution** đúng đơn vị và trọng số, hoặc phân tích raw samples.

### 9.2. Vì sao average không đủ?

Một hệ:
- 99% request 5 ms.
- 1% request 2.000 ms.

Average khoảng 24,95 ms, nhưng p99/p99.9 phản ánh vùng tail quan trọng. Nếu những requests 2 giây bị bỏ do CO, average và tail đều có thể bị làm đẹp.

### 9.3. Không trộn ba loại latency trong một histogram

Một histogram chỉ chứa successful dispatch→completion, một histogram đo scheduled→completion và một histogram corrected synthetic **không phải cùng một đại lượng**.

Đặt tên rõ:
- observed_success_latency_us.
- scheduled_success_latency_us.
- generator_schedule_lag_us.
- corrected_latency_estimate_us.
- timeout_or_drop_count.

### 9.4. Window duration

Một p99 toàn run có thể che 2 giây overload. Nên báo:
- Per-second offered/completed/errors.
- Sliding short-window p99.
- Histograms theo load stage.
- Worst window.
- Full-run distribution có ghi rõ warmup/cooldown.

Không dùng một percentile của vài samples để tuyên bố SLO; nêu sample count và độ tin cậy thống kê.

### 9.5. Histogram bounds và precision

Nếu recorder chỉ chứa tới 1 giây:
- Latency 5 giây có thể bị clamp, error hoặc bỏ.
- Một số công cụ tự resize/overflow theo chính sách.
- Tail SLO cần range đủ lớn và đếm overflow.
- Unit microseconds/nanoseconds phải thống nhất.

## 10. Sửa coordinated omission bằng histogram correction

Một số thư viện như **HdrHistogram** có các API cho phép **ước tính** những samples bị bỏ trong một mô hình arrival interval đều, chẳng hạn các thao tác có tên liên quan đến *correctForCoordinatedOmission* hoặc *recordValueWithExpectedInterval*.

### 10.1. Ý tưởng

Giả sử một request được đo 1.000 ms trong khi workload kỳ vọng một arrival mỗi 10 ms. Một cách correction mô phỏng rằng trong khoảng đang chờ, những logical arrivals sau có thể đã phải chịu các độ trễ xấp xỉ:

~~~~text
1000 ms
 990 ms
 980 ms
 ...
  20 ms
  10 ms
~~~~

Đó là **các samples suy diễn**, không phải những requests đã thực sự được gửi.

### 10.2. Mã minh họa HdrHistogram

~~~~java
import org.HdrHistogram.Histogram;

public final class CorrectionIllustration {
    public static void main(String[] args) {
        long maxMicros = 60_000_000L; // 60 seconds
        long expectedIntervalMicros = 10_000L; // 10 ms

        Histogram observed = new Histogram(maxMicros, 3);

        // Một sample thật: request mất 1 giây.
        observed.recordValue(1_000_000L);

        Histogram estimated = observed
                .copyCorrectedForCoordinatedOmission(
                        expectedIntervalMicros
                );

        System.out.println("observed count=" +
                observed.getTotalCount());
        System.out.println("estimated count=" +
                estimated.getTotalCount());
    }
}
~~~~

Đây là ví dụ sử dụng thư viện ngoài JDK; tên phương thức và cách thống kê cần xác minh theo phiên bản thư viện đang dùng. Mã không chạy benchmark thực, chỉ minh họa một phép correction.

### 10.3. Correction dùng khi nào?

Có thể hữu ích khi:
- Biết rõ mô hình expected interval.
- Không thể đo trực tiếp từng scheduled arrival đã bị bỏ.
- Muốn nhìn một **ước lượng bổ sung** về tail thay vì chỉ raw observed samples.
- Nêu minh bạch giả định và không gọi estimated observations là requests thực.

### 10.4. Correction không thể làm gì?

- Không biết chính xác request bị bỏ sẽ được server xử lý thế nào.
- Không dựng lại queue policy, drop rules, connection limits hay traffic mix thực.
- Không sửa một generator không đạt offered RPS.
- Không phân biệt stale/strong reads hay hot-key distribution nếu thiếu metadata.
- Không hồi sinh events mà load generator chưa từng gửi.
- Không tạo actual timeout/error outcomes.
- Không thay đo lịch arrivals và actual dispatch.
- Có thể không phù hợp arrival patterns biến thiên mạnh, Poisson hay workflows có dependency.
- Có thể đếm quá mức nếu histogram đã chứa queue delay từ scheduled time rồi còn áp correction lần nữa.

**Correction là một phép mô hình hóa có giả định, không phải giấy chứng nhận kết quả đo đã đúng.**

### 10.5. Hai histogram nên được báo riêng

~~~~text
observed_dispatch_latency:
    measured attempts only

scheduled_end_to_end_latency:
    observed for attempts actually scheduled and dispatched

corrected_estimate:
    synthetic inferred samples under expected-interval model
~~~~

Không gộp raw và corrected thành một percentile “thật”.

## 11. Kiến trúc bộ phát tải độc lập với kết quả

Một driver open-loop có thể tách:

~~~~mermaid
flowchart LR
    PLAN["Arrival plan"] --> SCHED["Dedicated scheduler"]
    SCHED --> ADMISSION["Nonblocking admission"]
    ADMISSION --> CLIENT["Async NoSQL client"]
    CLIENT --> DB[("NoSQL")]
    DB --> CLIENT
    CLIENT --> RESULTS["Outcome collector"]
    SCHED --> MISSED["Schedule miss ledger"]
    ADMISSION --> REJECTED["Rejected / dropped ledger"]
    RESULTS --> HIST["Histograms + counters"]
    MISSED --> HIST
    REJECTED --> HIST
~~~~

### 11.1. Scheduler không được chờ response

Scheduler tạo logical arrival theo lịch. Nó không đợi previous request complete, không giữ lock chung quanh network I/O, không gọi blocking query trên scheduler thread.

### 11.2. Async client không làm load vô hạn trở nên hợp lệ

Khi planned arrivals vượt capacity:
- In-flight requests tăng.
- Client pool queue tăng.
- Heap/socket pressure tăng.
- Có thể OOM nếu không bound.

Cần giới hạn queues/permits và **ghi nhận admission failure**. Không chặn scheduler cho tới khi có permit rồi âm thầm chuyển lịch.

### 11.3. Đường phát và đường ghi metric tách nhau

Metric recorder cũng có thể gây nghẽn:
- Serialize record quá nặng.
- Push remote metrics đồng bộ.
- Log mọi request.
- Global synchronized histogram.
- GC do allocation quá cao.

Dùng bounded, low-overhead aggregation, per-thread recorders/interval histograms, sampling cho traces, và ghi rõ metrics dropped nếu collector quá tải.

### 11.4. Warmup/JIT

Java JIT compilation, class loading, DNS, TLS handshakes, pool warmup, GC và Redis/NoSQL caches đều có thể ảnh hưởng thời gian phát/response. Tách warmup khỏi steady-state measurement, nhưng không dùng warmup để che một outage production có thật.

## 12. Java 21: mô hình một logical arrival

~~~~java
public enum AttemptOutcome {
    SUCCESS,
    CLIENT_ERROR,
    SERVER_ERROR,
    TIMEOUT,
    ADMISSION_REJECTED,
    SCHEDULE_MISSED,
    CANCELLED
}

public record ScheduledAttempt(
        long requestId,
        long plannedAtNanos
) {}

public record AttemptTiming(
        long requestId,
        long plannedAtNanos,
        long dispatchedAtNanos,
        long finishedAtNanos,
        AttemptOutcome outcome
) {
    public long schedulerLagNanos() {
        return Math.max(0L,
                dispatchedAtNanos - plannedAtNanos);
    }

    public long dispatchLatencyNanos() {
        return finishedAtNanos - dispatchedAtNanos;
    }

    public long scheduledLatencyNanos() {
        return finishedAtNanos - plannedAtNanos;
    }
}
~~~~

### 12.1. Chỉ tạo AttemptTiming khi đã gửi và kết thúc

Một SCHEDULE_MISSED không có dispatchedAt. Để biểu diễn đúng, production có thể dùng sealed result types:
- SentAndCompleted.
- SentAndTimedOut.
- MissedBeforeSend.
- RejectedBeforeSend.
- StillInFlight.

Không bịa dispatchedAt=plannedAt cho một request chưa từng gửi.

### 12.2. RequestId và retryId

Dùng:
- LogicalRequestId cho arrival/workflow.
- AttemptId cho từng physical try.
- RetryIndex.
- OperationId nếu write có side effects/idempotency.

Phân biệt chúng để không đếm retry thành một người dùng mới hoặc gửi duplicate write.

### 12.3. Clock source

Tất cả nanos trong record nên từ cùng monotonic source/VM. Nếu events tổng hợp từ nhiều generators, gửi:
- Per-generator durations/histograms.
- Wall-clock anchor chỉ để xác định window.
- Clock synchronization status.

Không trừ trực tiếp System.nanoTime từ hai machines.

## 13. Java 21: bộ scheduler có mốc dự kiến

Một đoạn minh họa cách **không phụ thuộc vào response để định lịch arrivals**. Nó đánh dấu những arrivals đã quá trễ thay vì tự giảm planned RPS.

~~~~java
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Semaphore;
import java.util.concurrent.locks.LockSupport;

public final class OpenLoopSketch {
    public interface AsyncNoSqlOperation {
        CompletionStage<?> send(long logicalRequestId);
    }

    public interface Metrics {
        void scheduled(long id);
        void missedSchedule(long id, long lagNanos);
        void rejectedAdmission(long id);
        void completed(
                long id,
                long scheduleLagNanos,
                long dispatchLatencyNanos,
                long scheduledLatencyNanos,
                Throwable error
        );
        void failedToSubmit(long id, Throwable error);
    }

    private final AsyncNoSqlOperation transport;
    private final Metrics metrics;
    private final Semaphore permits;

    public OpenLoopSketch(
            AsyncNoSqlOperation transport,
            Metrics metrics,
            int maxInFlight
    ) {
        this.transport = transport;
        this.metrics = metrics;
        this.permits = new Semaphore(maxInFlight);
    }

    // Educational driver: one logical arrival per interval.
    public void run(
            long arrivalCount,
            long intervalNanos,
            long maxStartLagNanos
    ) {
        if (arrivalCount < 0 || intervalNanos <= 0
                || maxStartLagNanos < 0) {
            throw new IllegalArgumentException();
        }

        long epoch = System.nanoTime();

        for (long id = 0; id < arrivalCount; id++) {
            long plannedAt = epoch + id * intervalNanos;
            metrics.scheduled(id);

            // Sleep only until this absolute planned time,
            // never relative to the previous response.
            while (true) {
                long remaining = plannedAt - System.nanoTime();
                if (remaining <= 0) break;
                LockSupport.parkNanos(remaining);
            }

            long now = System.nanoTime();
            long lag = Math.max(0L, now - plannedAt);

            if (lag > maxStartLagNanos) {
                metrics.missedSchedule(id, lag);
                continue;
            }

            if (!permits.tryAcquire()) {
                metrics.rejectedAdmission(id);
                continue;
            }

            long dispatchedAt = System.nanoTime();
            try {
                CompletionStage<?> stage = transport.send(id);

                stage.whenComplete((response, error) -> {
                    long finishedAt = System.nanoTime();
                    try {
                        metrics.completed(
                                id,
                                dispatchedAt - plannedAt,
                                finishedAt - dispatchedAt,
                                finishedAt - plannedAt,
                                error
                        );
                    } finally {
                        permits.release();
                    }
                });
            } catch (RuntimeException ex) {
                permits.release();
                metrics.failedToSubmit(id, ex);
            }
        }
    }
}
~~~~

### 13.1. Điều mà ví dụ làm được

- Planned arrivals không phụ thuộc completion trước đó.
- Ghi một logical scheduled item cho mỗi tick.
- Có đo scheduler lag.
- Có đếm tick missed nếu quá ngưỡng.
- Có bounded maxInFlight.
- Khi quá in-flight limit, ghi admission rejection thay vì block scheduler.
- Đo dispatch-to-completion và schedule-to-completion cho sends đã hoàn tất.
- Không chờ NoSQL response trên scheduler thread.

### 13.2. Điều mà ví dụ chưa làm được

- Chưa có per-operation timeout, cancellation hoặc drain.
- Chưa dùng bounded async metrics implementation.
- Chưa xử lý khi transport.send trả null, lỗi callback registration và process shutdown.
- Chưa kiểm tra overflow của epoch + id × interval cho runs cực dài.
- Chưa có planned traffic mix/keys/tenants.
- Chưa có Poisson arrival schedule hoặc bursts.
- Chưa tính network/server timing riêng.
- Chưa phân biệt HTTP/driver status để phân loại success/error.
- Chưa có retry policy.
- Chưa giải quyết pause/resume và multi-generator coordination.
- Callback completed có thể chịu scheduling delay và chưa phản ánh exact packet receive time.
- Không bảo đảm mỗi tick được phát; **missed/rejected counts chính là chứng cứ capacity generator không đủ**.

Đây là code **giải thích logic**, không phải benchmark harness production hoàn chỉnh. Một phần quan trọng của câu trả lời đúng là không che đậy những hạn chế này.

### 13.3. Vì sao không block khi hết permit?

Nếu:

~~~~java
permits.acquire();
sendAsync();
~~~~

trên scheduler thread, nó có thể đợi hàng giây khi system quá tải. Trong thời gian đợi, không tạo các logical arrivals tiếp theo; CO quay lại. Có thể dùng một bounded queue để giữ arrivals, nhưng vẫn phải ghi planned timestamp và queue delay/missed/deadline outcomes.

### 13.4. Catch-up burst có nên gửi tất cả late ticks?

Nếu JVM bị pause 3 giây, 10.000 scheduled arrivals có thể đã trễ. Gửi 10.000 requests lập tức sau pause:
- Không tái tạo original arrival timing.
- Tạo burst khác với workload mong muốn.
- Có thể tự gây overload mới.

Tốt hơn là chọn và công bố:
- Skip/miss quá deadline, đếm rõ.
- Admit vào bounded queue với planned timestamp.
- Hoặc run test invalid và tăng năng lực generator.

Không âm thầm “bù” bằng burst rồi coi RPS đã đạt đúng lịch.

## 14. Tại sao scheduleAtFixedRate chưa đủ?

Java ScheduledExecutorService.scheduleAtFixedRate cung cấp fixed-rate scheduling theo API, nhưng khi task bị chậm:
- Các lần chạy trễ có thể tiếp nối để bắt kịp.
- Task execution không nhất thiết đúng real-time.
- Nếu callback làm blocking I/O, scheduler thread có thể kẹt.
- Một GC pause làm các lần chạy trễ dồn lại.

Nếu mỗi tick chỉ gọi sendAsync và **ghi planned time/lag**, có thể dùng như một thành phần trong harness. Nhưng không mặc định nó đã:
- Đếm logical arrivals bị thiếu.
- Ngăn catch-up burst.
- Đo scheduled end-to-end latency.
- Bảo vệ event-loop/metrics thread.
- Ghi drop/reject outcomes.

### 14.1. Fixed delay khác fixed rate

- **Fixed delay:** chờ một khoảng sau lần task trước kết thúc; tự kéo dài khi xử lý chậm.
- **Fixed rate:** hướng tới các mốc thời gian được lên lịch, có thể chạy late.
- **Response-driven:** request sau chỉ bắt đầu khi response trước hoàn tất.

Ba khái niệm khác nhau, và cả fixed rate cũng phải có instrumentation về missed schedule.

### 14.2. Sleep cũng không chính xác tuyệt đối

Thread sleep/park có:
- Timer granularity.
- OS scheduling jitter.
- CPU preemption.
- GC pauses.
- Interrupt/spurious wakeups.

Dùng planned timestamps, đo scheduler lag và tạo headroom; không dựa vào “sleep(1)” như bằng chứng phát đúng 1.000 RPS.

## 15. Chọn mô hình arrival: đều, ngẫu nhiên hay burst

Không phải production traffic lúc nào cũng đều.

### 15.1. Constant arrival rate

Một arrival mỗi 1 ms:
- Dễ tái lập và hiểu.
- Hữu ích để khảo sát capacity.
- Có thể tạo thói quen đồng bộ nếu chia load generator sai.

### 15.2. Poisson/exponential inter-arrival

Các arrivals có khoảng cách biến động theo một phân phối. Hữu ích để mô hình hóa một lớp traffic độc lập ngẫu nhiên, nhưng không tự phù hợp mọi ứng dụng.

Cần:
- Seed ngẫu nhiên được lưu.
- Planned timestamps được tạo trước/không phụ thuộc response.
- Không lấy “sleep ngẫu nhiên sau khi request hoàn thành” thay cho open-loop arrival process.

### 15.3. Burst và diurnal pattern

NoSQL load có thể đến từ:
- Flash sale.
- Scheduled campaigns.
- Batch imports.
- CDC catch-up.
- Login storms.
- Cache stampede.
- Region failover.

Một test RPS trung bình 5.000 không chứng minh hệ chịu được 20.000 RPS trong 10 giây.

### 15.4. Traffic mix

Một arrival plan nên xác định:
- GET/PUT/conditional update tỷ lệ.
- Hot vs cold keys.
- Partition distribution (uniform/Zipfian).
- Payload bytes.
- Query selectivity.
- Consistency level.
- Cache hit/miss mix.
- Multi-document transaction share.
- Tenant distribution.

Nếu generator không theo đúng mix khi overload (ví dụ chậm đặc biệt ở writes rồi ngưng tạo writes mới), measured workload đã bị thay đổi.

## 16. NoSQL driver làm chậm generator ở đâu?

### 16.1. Connection pool acquisition

Java driver có pool 100 connections:
- 100 requests chiếm pool.
- Requests mới chờ acquire.
- Nếu benchmark đo start sau acquire, thời gian chờ bị bỏ.

Đo:
- Time waiting for client connection.
- Number waiting.
- Pool saturation.
- Open connections.
- Timed-out acquires.

### 16.2. Async API cũng có queue

Async MongoDB/Cassandra/Redis/HTTP driver có thể:
- Enqueue requests nội bộ.
- Chờ event-loop.
- Chờ permits.
- Chờ broker flow control.
- Complete Future sau response.

“Không block user thread” không có nghĩa không có queue delay hoặc unlimited capacity.

### 16.3. GC pause

Một JVM pause 1 giây:
- Scheduler không tạo ticks.
- Callback không record response đúng lúc.
- Metrics recorder chậm.
- Batch updates có thể dồn sau pause.

Cần theo dõi JVM GC pause time và generator scheduling lag, nhưng không đổ mọi high p99 cho GC nếu database cũng đang chậm.

### 16.4. DNS, TLS và authentication

Nếu benchmark tạo NoSQL client mỗi request:
- Connection handshakes/auth làm tải khác production.
- Load generator CPU/sockets có thể là bottleneck.
- RPS không đạt.
- Requests không đo đúng pool reuse.

Dùng client lifecycle theo production scenario; đo cold connection/rotation riêng nếu đó là workload cần test.

### 16.5. Serialization và payload generation

Tạo document lớn hoặc JSON mỗi tick cũng tiêu CPU/GC. Pre-generate payload có kiểm soát nếu muốn đo database/driver, nhưng đừng loại bỏ serialization nếu production yêu cầu thực hiện bước đó.

## 17. Khi hệ quá tải: queue, reject, timeout và backpressure

Một hệ cố định offered arrivals 10.000/s nhưng chỉ xử lý 7.000/s:

\[
\Delta Q \approx (10.000-7.000)\times T
\]

Trong 5 giây, backlog có thể tăng khoảng 15.000 requests nếu không drop và các tốc độ ổn định.

### 17.1. Không để queue vô hạn

Nếu generator giữ mọi logical arrivals trong memory:
- Queue tăng.
- Latency scheduled→completion tăng.
- Cuối cùng OOM.
- Test kết thúc mà còn hàng nghìn outstanding.

Dùng bounded queue, max in-flight, max waiting time và outcomes riêng.

### 17.2. Backpressure phải được ghi nhận

Nếu server trả 429/throttle:
- Đó là kết quả có ý nghĩa.
- Không giảm rate mà xóa dấu vết.
- Nếu client obey Retry-After, phân biệt user behavior modeling với fixed-arrival capacity run.

### 17.3. Rate limit không đồng nghĩa thất bại hoàn toàn

Một system có thể bảo vệ backend bằng 429/503 thay vì queue vô hạn. Nhưng nếu SLO yêu cầu 99,9% successful within deadline ở offered load, tỷ lệ reject vẫn là SLO failure.

### 17.4. Latency cận dưới từ timeout

Khi request đã timeout ở 2 giây, bạn không biết nó sẽ hoàn tất ở 3 hay 30 giây. Trình bày:
- Timeout threshold.
- Timeout rate.
- Outstanding at end.
- Completed latency distribution.
- SLO pass rate.

Không thay mọi timeout bằng một success sample 2 giây rồi tuyên bố p99=2s.

## 18. Lập bảng kết quả không che generator slowdown

Ví dụ một run 60 giây, target 5.000 arrivals/s:

| Metric | Giá trị minh họa |
| --- | ---: |
| Planned arrivals | 300.000 |
| Sent attempts | 240.000 |
| Schedule missed | 40.000 |
| Admission rejected | 20.000 |
| Successful completions | 220.000 |
| Failed/timed out completions | 15.000 |
| Still in flight at end | 5.000 |
| Planned rate | 5.000/s |
| Sent rate | 4.000/s |
| Completion count during run | 235.000 |
| Delivery coverage | 80% |

Những số trên chỉ mô tả **logical attempts đầu tiên, chưa có retry**. Kết quả 220.000 success + 15.000 error + 5.000 in-flight = 240.000 sent; 240.000 sent + 40.000 missed + 20.000 rejected = 300.000 planned.

### 18.1. Kết luận hợp lệ

- Generator không đạt planned RPS.
- Có 20% scheduled arrivals không được gửi.
- Phải điều tra generator/admission limits.
- Không được dùng successful-only p99 để tuyên bố NoSQL đạt SLO tại 5.000 RPS.

### 18.2. Không nên kết luận

- “Database có thể xử lý ổn 5.000 RPS.”
- “40.000 request bị miss có latency 0.”
- “15.000 timeout không ảnh hưởng p99.”
- “Average completed latency đủ để bỏ qua failures.”
- “Tăng thread pool đến vô hạn để đạt plan.”

## 19. SLO theo deadline thay vì p99 thành công đơn lẻ

Giả sử API có SLO:
- 99% logical arrivals phải trả kết quả hợp lệ trong 200 ms từ mốc arrival.
- Được phép reject theo policy khác nếu công bố rõ.

Một metric thẳng:

\[
SLO_{\text{pass}}=
\frac{\text{logical arrivals thành công trong 200 ms}}
{\text{total expected logical arrivals}}
\]

Nếu generator không tạo được một arrival:
- Với benchmark khả năng đáp ứng fixed arrivals, nó không thể tính là success.
- Nhưng phải phân biệt lỗi **generator** với lỗi **SUT** trong báo cáo.

### 19.1. Không gán lỗi generator cho database bừa bãi

Một run có scheduleMissRate=20% là run không hợp lệ để định lượng đúng năng lực SUT ở planned rate, trừ khi mô hình test đã định trước cách đánh giá những missed arrivals.

Nêu rõ “load generator capacity insufficient” thay vì quy mọi miss thành DB timeout.

### 19.2. Mục tiêu kép

Một tiêu chí benchmark có thể yêu cầu:

- Generator delivery coverage ≥99,9%.
- Schedule lag p99 dưới ngưỡng.
- SUT successful-within-deadline ≥99%.
- Origin errors/throttles trong ngân sách.
- Không vượt resource limits.
- Không có sai lệch correctness/consistency.

Nếu generator coverage không đạt, cần tăng năng lực generator hoặc giảm planned rate và thử lại, không tối ưu p99 bằng cách bỏ samples.

## 20. Kiểm tra bộ phát tải trước khi kiểm tra NoSQL

### 20.1. Generator saturation

Theo dõi:
- CPU của load generator.
- JVM heap/GC pause.
- Event-loop utilization.
- Scheduler tick lag.
- Timer oversleeps.
- Context switches.
- Thread counts.
- Socket/ephemeral port exhaustion.
- Network bandwidth/packet drops.
- DNS/TLS handshakes.
- Metric recorder lag.
- Async request backlog.
- Driver queue và pool waits.

### 20.2. Dummy endpoint baseline

Đầu tiên chạy generator tới một endpoint rất nhẹ hoặc stub có latency được kiểm soát:
- Có đạt scheduled RPS không?
- Scheduler lag phân phối thế nào?
- Có missed ticks?
- Có queue/histogram overflow?
- Có tạo retries không?

Một generator không đạt planned rate với stub **không thể** được tin khi đo NoSQL nặng.

### 20.3. Độc lập tài nguyên

Nếu generator chạy cùng VM với database:
- CPU/IO contention có thể khiến cả hai chậm.
- Benchmark thay đổi hệ thống đang đo.
- Không biết lỗi do generator hay SUT.

Nên tách resource domains khi mục tiêu là đo capacity NoSQL; nếu benchmark end-to-end cùng node theo thiết kế thật, phải khai báo ranh giới rõ.

### 20.4. Nhiều generator nodes

Khi một generator không đủ capacity:
- Chia arrival plan theo deterministic shards/IDs.
- Mỗi generator ghi planned/sent/missed riêng.
- Tổng hợp counters đúng.
- Đồng bộ wall-clock để chọn windows, không trừ monotonic nanos giữa máy.
- Tránh tất cả nodes phát burst đúng cùng một millisecond nếu workload không chủ đích.
- Bảo vệ metrics collector khỏi thành bottleneck.

## 21. Những công cụ đo có thể giúp và giới hạn

Một số nhóm công cụ được dùng trong thực tế:

| Nhóm | Ví dụ | Điều phải kiểm tra |
| --- | --- | --- |
| Java microbenchmarks | JMH | Throughput/latency của method vs end-to-end NoSQL |
| HTTP load generators | wrk, wrk2, k6, Gatling | Open/closed arrival semantics, rate limits |
| DB benchmark framework | YCSB-style workloads | Client concurrency, target throughput, latency reporting |
| Histogram libraries | HdrHistogram | Units, range, correction mode |
| Metrics/tracing | Prometheus, OpenTelemetry | Instrumentation overhead, missing outcomes |
| Chaos/fault testing | Fault injection tooling | Generator lag vs source fault separation |

### 21.1. Không suy từ tên công cụ

Một công cụ có tùy chọn fixed RPS vẫn có thể:
- Không giữ đúng lịch khi overload.
- Drop scheduled arrivals.
- Hết workers/connections.
- Chỉ record sent requests.
- Không tách scheduled vs actual send.

Cần xem cấu hình và semantics cụ thể của phiên bản chạy.

### 21.2. wrk2 và constant-throughput hướng tiếp cận

wrk2 được biết đến như một nỗ lực thiết kế load generation có mục tiêu throughput định trước và xử lý coordinated omission theo một mô hình đo. Tuy nhiên vẫn cần xác minh:
- Target rate có đạt không?
- Connection/thread capacity.
- Tool version và correction behavior.
- Error, timeout và socket limits.
- Workload có đại diện cho NoSQL calls thật không?

Không coi một công cụ là “miễn CO tuyệt đối”.

### 21.3. JMH dùng để làm gì?

JMH rất hữu ích cho Java microbenchmark như:
- Serialization.
- Hashing/cache lookup.
- Codec.
- Local data-structure performance.

Nhưng một JMH benchmark gọi remote NoSQL bằng phương pháp tuần tự không tự trở thành fixed-arrival distributed load test. Phải xác định câu hỏi đo và workload.

## 22. NoSQL-specific benchmarking: dữ liệu và partition skew

Một điểm làm CO nguy hiểm hơn là **workload phân phối không đều**.

### 22.1. Hot partition

Giả sử 80% requests tập trung vào một partition:
- Khi partition đó chậm, những workers đợi partition đó không phát requests mới.
- Measured traffic mix có thể tự chuyển tương đối sang các partitions nhanh còn lại.
- Tỷ lệ hot-key trong sent/completed samples khác planned mix.

Cần report planned và actual per:
- Partition class.
- Tenant tier.
- Key popularity.
- Operation type.

### 22.2. Query selectivity

Một query:
- Point lookup.
- Range scan.
- Aggregation.
- Secondary-index lookup.

có latency khác nhau. Nếu slow range scans giữ worker lâu, closed-loop generator phát ít range scans hơn, khiến báo cáo aggregate quá lạc quan.

### 22.3. Read vs write mix

Nếu writes chậm hơn reads:
- Worker chuyên writes tự giảm throughput.
- Completed samples chứa tỷ lệ reads cao hơn.
- p99 tổng hợp không còn đại diện planned ratio.

Phải tách counters/latencies theo operation class, đồng thời đo actual mix.

### 22.4. Strong vs eventual reads

Các mức read consistency có cost và guarantee khác nhau. Không so một run dùng eventual với run strong mà bỏ qua:
- Consistency mode.
- Replica locality.
- Read repair/replication lag.
- Partition skew.
- Generator scheduling health.

## 23. Đo batch, pipeline và bất đồng bộ

### 23.1. Batching có thể che latency từng item

Một batch 1.000 events:
- Mất 2 giây mới được flush.
- Network call chỉ mất 20 ms.

Nếu metric đo từ khi gửi batch, sẽ báo 20 ms nhưng item đầu đã chờ gần 2 giây. Cần item scheduled/enqueue/flush/ack timestamps.

### 23.2. Pipelining

Pipelining nhiều operations trên một connection có thể tăng throughput. Nhưng phải đo:
- Queued time.
- In-flight count.
- Backpressure.
- Per-operation completion.
- Ordered dependency effects.

Một large pipeline có p99 thấp cho những ops hoàn tất đầu nhưng còn backlog chưa hoàn tất là báo cáo thiếu.

### 23.3. Async callbacks bị trễ

Server có thể trả response nhưng event-loop callback được chạy muộn do CPU/GC:
- Dispatch-to-callback latency bao gồm client-side delay.
- Đây là thực tế client-visible latency, không nhất thiết DB service time.
- Cần correlate với server metrics để phân biệt.

### 23.4. Streaming queries

Một cursor/stream trả:
- First byte/first row latency.
- Per-page latency.
- Total drain time.
- Time waiting for consumer backpressure.

Benchmark chỉ đo first row có thể bỏ phần thời gian đọc hết dataset, còn chỉ đo total duration không nói được responsiveness.

## 24. Rate control khi target đã quá tải

Một câu hỏi: “Nếu database đang quá tải, có nên giữ offered rate cố định không?”

**Tùy mục đích test**.

### 24.1. Capacity/overload test

Muốn tìm giới hạn chịu tải:
- Tiếp tục tạo logical arrivals theo plan trong một giai đoạn hữu hạn.
- Dùng generator có capacity và admission accounting.
- Không cho queue vô hạn.
- Đo error/reject/tail và time-to-recovery.
- Có guard để không gây ảnh hưởng production thật.

### 24.2. Adaptive client/backpressure test

Muốn mô phỏng production client tuân server retry/backoff:
- Khi 429/Retry-After, client giảm/tạm ngưng theo rule.
- Đó là behavior đang được đo.
- Báo planned user intents vs actual attempts/retries.
- Không gọi achieved RPS là fixed offered RPS.

### 24.3. Hai test không thay nhau

Một system có thể:
- Có admission control tốt và user-visible reliability cao dưới adaptive traffic.
- Nhưng không đủ capacity để xử lý offered 20.000/s constant arrivals.

Cần cả hai nếu câu hỏi sản phẩm yêu cầu.

## 25. Đo bảo đảm đúng khi write timeout

Một write NoSQL có thể commit nhưng client timeout trước khi nhận ACK. Khi benchmark retry:
- Có thể tạo duplicate business effects.
- Latency logic không chỉ là một attempt.
- Phải dùng operationId/idempotency theo contract.
- Timeout là UNKNOWN outcome của write cho tới khi reconcile, không là chắc chắn failed commit.

### 25.1. Benchmark không được tạo dữ liệu rác vô hạn

Khi stress writes:
- Test IDs/tenants riêng.
- Cleanup/retention policy.
- Capacity safeguards.
- Không flood shared production database.
- Không dùng public payment side effects.
- Per-run namespace và operation IDs.

### 25.2. Throughput thành công chưa đủ correctness

Một run đạt 20.000 operations/s nhưng:
- Double-bookings.
- Lost increments.
- Cross-tenant reads.
- Incorrectly acknowledged writes.

thì kết quả không hợp lệ về nghiệp vụ. Đo accuracy/invariants ngoài latency.

### 25.3. Chỉ dùng eventual projection đúng phạm vi

Nếu benchmark source write rồi đọc search index eventual:
- Đo projection visibility lag riêng.
- Không gọi query miss ngay là write rollback.
- Không đưa stale search result vào phép đo source commit status.

## 26. Latency distribution khi có timeouts và missing observations

### 26.1. Survival/censoring trực giác

Một request timeout ở 1 giây cho biết chưa có terminal success trong deadline; ta không biết completion time cuối cùng. Nếu chỉ báo distribution những requests đã xong, **slowest pending requests bị thiếu**.

Có thể báo:
- Successful-within-T rate.
- Timeout/drop/reject counts.
- Histogram của successes.
- In-flight age distribution.
- Lower-bound observations cho unfinished khi thực sự cần phân tích.

### 26.2. Đừng cộng fake slow samples với real samples không nhãn

Nếu dùng corrected histogram:
- Ghi estimator configuration/expected interval.
- Ghi corrected total sample count.
- Không gọi synthetic count là physical attempts.
- Không trộn với timeout outcomes như thể chúng là success.

### 26.3. Percentiles của mixtures

Nếu một run gồm:
- 90% point reads.
- 10% expensive scans.

Tổng p99 có thể che p99 của scan. Report per operation và aggregate, không đổi denominator tùy ý.

### 26.4. Một tail latency sample không nói đủ

Có thể có:
- GC pause generator.
- Network packet loss.
- NoSQL compaction.
- Hot partition.
- Throttling.
- Reconnect/TLS.
- Consumer backpressure.

Cần telemetry song song với histogram để phân tích nguyên nhân.

## 27. Đồng hồ và đo theo nhiều nút

### 27.1. System.nanoTime

Trong cùng JVM:
- Dùng cho durations.
- Không chia sẻ absolute nanoTime giữa JVMs.

### 27.2. Wall-clock / NTP

Để đặt sự kiện vào timeline chung:
- Dùng UTC timestamps/anchors.
- Theo dõi NTP sync/skew.
- Không trừ wall-clock của hai servers khác nhau nếu cần chính xác microsecond mà không có clock discipline.

### 27.3. Trace correlation

Có thể ghi:
- traceId.
- logicalRequestId.
- scheduledOffset.
- send timestamp.
- database server span.
- response timestamp.

Đảm bảo instrumentation sampling không loại bỏ phần lớn slow traces mà không có trọng số/counters bù.

### 27.4. RPS aggregation

Nhiều generators có clock lệch:
- Mỗi node báo counts theo local windows.
- Central aggregator cần alignment hoặc dùng total run duration/count rõ.
- Nếu phân tích millisecond bursts, cần đồng bộ clock tốt hơn.
- Không suy từ gộp histogram đơn giản rằng tất cả concurrent in-flight được phản ánh.

## 28. Một protocol benchmark từng bước

### Bước 1 — Xác định câu hỏi

Ví dụ:
- “NoSQL point read API xử lý được bao nhiêu **independent arrivals/s** với 99% thành công trong 100 ms?”
- Không chỉ “benchmark nhanh nhất là bao nhiêu?”.

### Bước 2 — Mô tả workload

- Read/write ratio.
- Key distribution.
- Payload.
- Consistency.
- Cache policy.
- Session dependencies.
- Burst patterns.
- Planned RPS stages.

### Bước 3 — Calibrate generator

- Chạy dummy/stub endpoint.
- Xác minh delivery coverage.
- Schedule lag.
- CPU/GC/network headroom.
- Metrics overhead.

### Bước 4 — Warmup và baseline

- Warm JIT/client pools.
- Tạo dataset theo phân phối.
- Tách warmup khỏi measurement khi phù hợp.
- Ghi database cache/compaction state.

### Bước 5 — Chạy fixed-arrival stages

- Tăng offered rate theo bước.
- Giữ mỗi stage đủ lâu.
- Không nhảy stage khi previous backlog còn lớn.
- Ghi planned vs sent vs completed mỗi giây.

### Bước 6 — Giới hạn load generator

- Bounded max in-flight/queue.
- Missed/rejected accounting.
- Hard deadlines.
- Đừng biến tình huống quá tải thành OOM.

### Bước 7 — Thu thập distributions

- Scheduled→dispatch.
- Dispatch→completion.
- Scheduled→completion.
- Errors/timeouts/drops.
- Per-key/per-operation p99.

### Bước 8 — Xác minh NoSQL

- CPU/IO.
- Pool waits.
- Hot partitions.
- Compaction/GC.
- Replica lag/quorum.
- Throttles.
- Data correctness.

### Bước 9 — Đánh giá run validity

Nếu generator miss quá nhiều planned arrivals:
- Gắn nhãn invalid/inconclusive cho claim fixed RPS.
- Tăng generator capacity hoặc điều chỉnh test.
- Không thay achieved RPS thành planned RPS trong báo cáo.

### Bước 10 — Repeat và compare

- Nhiều runs.
- Workload seed cố định hoặc được mô tả.
- Confidence intervals nếu đủ samples.
- So cùng conditions.
- Không chọn run đẹp nhất bỏ runs xấu.

## 29. Ví dụ: kết quả ngụy tạo bởi closed-loop

Giả sử có 50 clients, no think time.

| Giai đoạn | Mean response latency | Closed-loop throughput lý tưởng |
| --- | ---: | ---: |
| NoSQL khỏe | 5 ms | 10.000 req/s |
| NoSQL chậm vừa | 50 ms | 1.000 req/s |
| NoSQL nghẽn | 500 ms | 100 req/s |
| NoSQL gần timeout | 2.000 ms | 25 req/s |

Theo công thức xấp xỉ:

\[
X\approx\frac{N}{R+Z}
\]

với N số clients, R response time và Z think time. Khi Z=0, X≈N/R.

### 29.1. Quan sát chính

- Khi latency tăng 100 lần, achieved offered rate giảm gần 100 lần.
- Chính lúc DB nghẽn, bộ phát càng ít requests.
- Test tự tạo một feedback loop giảm tải.
- Không thể dùng bảng đó để khẳng định latency khi DB phải tiếp nhận fixed 10.000 independent arrivals/s.

### 29.2. Closed-loop vẫn hữu ích

Nếu production là 50 terminals mà mỗi terminal luôn đợi response rồi mới gửi next command, closed-loop có thể đại diện hợp lý. Cần công bố:
- N terminals.
- Think-time distribution.
- Workflow dependencies.
- Throughput thực.
- Latency từ user command tới result.

Không dùng cùng kết quả để suy năng lực cho một hệ có 10.000 users độc lập.

## 30. Một bảng so sánh open-loop overload

Giả sử planned RPS=10.000 trong 30 giây. NoSQL chỉ phục vụ 7.000/s khi ổn định.

~~~~text
Scheduled arrivals:      300,000
Possible service:        210,000 (idealized over 30 s)
Potential backlog:        90,000
~~~~

Trong thực tế:
- Requests có thể bị queue, reject hoặc timeout.
- Service rate thay đổi theo overload.
- Retries có thể tăng physical attempts.
- Generator có thể không phát hết 300.000 nếu thiếu capacity.

### 30.1. Điều quan trọng

Open-loop không làm NoSQL bỗng xử lý được 10.000/s; nó **lộ rõ** backlog/rejections/latency thay vì tự làm tải giảm theo response time.

### 30.2. Khi queue vượt giới hạn

Nếu admission queue max 10.000:
- Một số arrivals bị rejected.
- Đó là kết quả có ý nghĩa.
- Phải ghi planned and rejected counts.
- Không đo p99 của accepted-only rồi bỏ 80.000 rejected khỏi kết luận SLO.

## 31. Một benchmark spec minh họa

~~~~yaml
experiment: nosql-coordinated-omission-control
generator:
  javaVersion: 21
  scheduling: independent-absolute-arrivals
  maxInFlight: 5000
  maxSchedulerLagMillis: 5
  dropAccounting: explicit
  metrics:
    - planned_arrivals
    - dispatch_attempts
    - schedule_misses
    - admission_rejections
    - completed_successes
    - timeouts
    - errors
    - in_flight_at_end
    - scheduled_to_dispatch_latency
    - dispatch_to_completion_latency
    - scheduled_to_terminal_latency
workload:
  operationMix:
    pointReadPercent: 70
    conditionalWritePercent: 20
    rangeQueryPercent: 10
  keys: zipfian
  consistency: explicit-per-operation
  offeredRpsStages:
    - 1000
    - 3000
    - 5000
    - 10000
  steadyStageSeconds: 120
faults:
  - database_slowdown
  - hot_partition
  - generator_gc_pause
  - generator_cpu_throttle
  - client_pool_exhaustion
  - network_delay
  - server_throttling
  - retry_storm
  - cache_eviction
  - replica_failover
measure:
  - offered_vs_sent_vs_completed
  - delivery_coverage
  - error_and_timeout_rate
  - p50_p95_p99_p999_by_operation
  - generator_lag_p99
  - source_pool_waits
  - shard_hotspots
  - steady_state_and_recovery
  - correctness_invariants
~~~~

Đây là **spec thí nghiệm**, không phải một cấu hình native được mọi tool hỗ trợ.

### 31.1. Một run nên có report metadata

~~~~json
{
  "runId": "co-459-2026-11-14",
  "workloadPolicyVersion": "v3",
  "plannedRps": 5000,
  "arrivalModel": "fixed-interval",
  "generatorNodes": 4,
  "timeUnit": "microseconds",
  "histogramMode": "raw-and-scheduled",
  "correctionMode": "none",
  "maxSchedulerLagMillis": 5,
  "maxInFlight": 5000,
  "sampleWindowSeconds": 1,
  "warmupExcluded": true
}
~~~~

Nếu có correction:
- Nêu method và expected interval.
- Nêu histogram nào dùng synthetic samples.
- Không giấu raw outcomes.

## 32. Fault injection: test khả năng đo thay vì chỉ test database

| Fault | Cách tạo | Điều cần xác minh |
| --- | --- | --- |
| Generator GC pause | Tạo pause có kiểm soát trong test | Scheduled ticks vẫn được đếm; missed/lag tăng |
| Generator CPU throttle | Giới hạn CPU cgroup | Delivery coverage giảm được phát hiện |
| Scheduler thread blocked | Inject blocking action | Không báo đạt fixed RPS giả |
| Client pool full | Giảm max connections | Pool wait/reject có metric |
| NoSQL latency spike | Inject 1 s delay | Tail và backlog hiện rõ |
| NoSQL throttling | Trả rate limit | 429/errors không bị xóa |
| Network delay | Thêm latency/loss | Timeout và retry accounting đúng |
| Cache stampede | Expire hot key | Planned hot-key mix giữ, source overload thấy |
| Heavy compaction | Mô phỏng background IO pressure | p99 tăng ở đúng stage |
| Write quorum loss | Mất replica quorum | Failure/UNKNOWN được phân loại |
| Retry burst | Bật policy retry không jitter rồi sửa | Attempt amplification đo được |
| End-of-run pending | Kết thúc khi 5.000 in-flight | Chúng không bị bỏ khỏi báo cáo |
| Histogram range overflow | Inject response > max bucket | Overflow được phát hiện |
| Metric exporter blocked | Tắc export | Generator không dừng im lặng |
| Distributed generator clock skew | Lệch UTC anchors | Không trừ raw cross-node nanoTime |
| 1000-key avalanche | Nhiều keys mất cache | Origin protection và offered load được quan sát |
| Cold client connections | Restart pool | TLS/auth cost được tách |
| Closed-loop accidental regression | Đổi async sang blocking send | Delivery coverage thay đổi và test fail |

### 32.1. Test generator pause 2 giây

Với target 2.000 arrivals/s:
- Planned trong pause: 4.000.
- Nếu generator không thể gửi, phải ghi missed/rejected.
- Không chấp nhận báo “0 requests nên không có latency”.
- Đo backlog nếu implementation dùng bounded queue.
- Khi resume, không tự flood 4.000 requests rồi gọi đó là đúng arrival timing.

### 32.2. Test database slowdown

Nếu DB từ 10 ms lên 1 s:
- Closed-loop achieved RPS có thể giảm.
- Open-loop planned RPS vẫn giữ theo workload.
- In-flight, timeout/reject và scheduled latency tăng.
- Generator phải đủ headroom để không thành bottleneck; nếu không, gắn nhãn inconclusive.

### 32.3. Test histogram

Một số tools loại bỏ samples do:
- Negative/overflow duration.
- Timeout không trả success.
- Writer thread bị block.
- Low recorder capacity.

Phải kiểm tra counters và sample totals, không chỉ nhìn đồ thị percentile.

## 33. Runbook khi benchmark báo p99 đẹp bất thường

### Bước 1 — So ba throughput

- Planned arrivals/s?
- Sent attempts/s?
- Completed/successful/s?
- Có đoạn nào planned=10k nhưng sent=1k?

Nếu có, chưa thể kết luận SUT đạt target.

### Bước 2 — Kiểm tra timing boundary

- Latency start là scheduled hay actual send?
- Pool acquisition nằm trong hay ngoài metric?
- Có đo queue wait của generator không?
- Timeouts/drops được ghi ở đâu?

### Bước 3 — Kiểm tra scheduling

- Closed-loop response-driven?
- Fixed delay hay fixed rate?
- Scheduler có block on I/O?
- Có catch-up bursts?
- Có missing tick ledger?
- Schedule lag p99/max?

### Bước 4 — Kiểm tra generator health

- CPU/GC/heap.
- Thread pool.
- Socket/network.
- Metrics recorder.
- TLS/DNS.
- Pool connections.
- JVM pauses.

### Bước 5 — Kiểm tra NoSQL

- Source-side RPS.
- Hot partitions.
- CPU/IO/compaction.
- Replication/quorum.
- Throttles/errors.
- Client/server queueing.
- Data correctness.

### Bước 6 — Đánh giá run validity

- Có đạt delivery coverage không?
- Có overshoot/undershoot nghiêm trọng không?
- End-of-run pending được tính?
- Retry attempts được tách?
- Histograms có đủ range và samples?

### Bước 7 — Chạy lại có kiểm soát

- Tách generator khỏi SUT.
- Dùng nhiều generator nodes nếu cần.
- Nạp workload theo schedule độc lập.
- Đặt bounded in-flight/admission.
- Ghi scheduled/sent/completed/missed.
- So raw và corrected (nếu có) dưới nhãn rõ.
- Repeat để kiểm chứng.

## 34. Những ngộ nhận thường gặp

1. **“Stopwatch từng request đúng là benchmark đúng.”** Có thể bỏ lịch arrivals không phát.
2. **“100 threads luôn tạo cùng RPS.”** Throughput thay đổi khi latency thay đổi.
3. **“Closed-loop luôn sai.”** Đúng nếu production workflow cũng response-dependent và mục tiêu tương ứng.
4. **“Closed-loop chứng minh fixed-arrival capacity.”** Không tự chứng minh.
5. **“Open-loop luôn không có coordinated omission.”** Scheduler cũng có thể chậm/miss.
6. **“Fixed rate nghĩa chính xác real-time.”** OS/GC có jitter.
7. **“scheduleAtFixedRate tự tính missed arrivals.”** Phải đo và xử lý late ticks.
8. **“Sleep sau response là open-loop.”** Vẫn phụ thuộc response.
9. **“Send time là scheduled arrival time.”** Có queue/scheduler lag.
10. **“Không có request trong GC pause thì không có latency.”** Logical arrivals có thể bị bỏ.
11. **“Nếu generator chậm, database vẫn đã được test ở target RPS.”** Không.
12. **“Achieved throughput là offered throughput.”** Khác khi overload.
13. **“100% request gửi thành công nghĩa không có queue.”** Vẫn có scheduler/client waits.
14. **“Chỉ p99 successful requests là đủ.”** Cần timeout/drop/reject/in-flight.
15. **“Timeout là latency success đúng bằng deadline.”** True completion không biết.
16. **“Request còn pending cuối run có thể bỏ.”** Thiên lệch tail.
17. **“Correction làm dữ liệu đo thành observations thật.”** Là ước lượng synthetic.
18. **“Correction dùng cho mọi arrival model.”** Có assumptions.
19. **“Correction thay thế open-loop generator.”** Không.
20. **“Áp correction hai lần không sao.”** Có thể double count.
21. **“Merge p99 của nodes bằng average là p99 tổng.”** Sai toán.
22. **“p99 một giờ phản ánh mọi spike.”** Short windows có thể bị che.
23. **“Histogram range 1 s đủ cho timeouts 30 s.”** Có truncation/overflow risk.
24. **“CPU generator không quan trọng.”** Có thể là bottleneck.
25. **“Async API không có queue.”** Driver có internal backlog.
26. **“Virtual threads tự giải quyết database bottleneck.”** Không tăng source capacity.
27. **“Connection pool wait không phải latency.”** Với client-visible latency có.
28. **“Request retry là một request user mới.”** Cần logical-vs-attempt distinction.
29. **“Retry latency chỉ tính final success attempt.”** Bỏ toàn bộ waits trước.
30. **“Rate limiting không cần báo vì không phải latency.”** Là outcome quan trọng.
31. **“Dùng queue vô hạn để không drop.”** Có thể OOM và che overload.
32. **“Bù late requests bằng burst là đúng schedule.”** Thay đổi traffic pattern.
33. **“Một histogram chung cho reads/writes tốt hơn.”** Che operation-specific tail.
34. **“Hot key mix giữ nguyên khi closed-loop chậm.”** Có thể thay đổi tỷ trọng measured.
35. **“Cache hit ratio cao nghĩa NoSQL đủ capacity.”** Cache misses/bursts vẫn có thể quá tải.
36. **“Metrics exporter đồng bộ không ảnh hưởng đo.”** Có thể block generator.
37. **“JVM nanoTime giữa hai nodes có cùng epoch.”** Không.
38. **“Wall-clock UTC luôn chính xác microsecond.”** Có clock skew/adjustments.
39. **“Source server p99 thay thế user p99.”** Không bao gồm client/proxy/queue.
40. **“Run tốt nhất là capacity thật.”** Cần repeat/conditions.
41. **“Một test fake endpoint chậm là DB chậm.”** Cần isolate và correlate.
42. **“NoSQL write timeout chắc chắn rollback.”** Kết quả có thể unknown.
43. **“Tối ưu RPS bằng bỏ errors.”** Không hợp lệ.
44. **“SUT trả 503 nhanh là p99 thành công tốt nên pass.”** SLO gồm availability.
45. **“Kết quả test không cần offered/sent/missed counts.”** Không thể đánh giá CO.
46. **“Generator miss có thể quy hết lỗi DB.”** Phải phân biệt test harness capacity.
47. **“Không cần bài test GC pause.”** Đó là failure mode chính của generator.
48. **“JMH gọi remote DB tự là workload fixed arrival.”** Không.
49. **“Một test có thành công nhiều là không cần correctness checks.”** Latency không thay invariants.
50. **“Coordinated omission chỉ ảnh hưởng average.”** Tail percentiles và interpretation cũng sai.

## 35. Bài tập thực hành: phát tải Java cho NoSQL ba vùng

Một nền tảng booking dùng:
- Java 21 và NoSQL document/key-value storage.
- Redis cache phía trước.
- 100 generator workers ở ba machines.
- Đọc 70%, ghi điều kiện 20%, range scan 10%.
- Planned target 5.000 arrivals/s.
- Request deadline 500 ms.
- Hot keys chiếm 60% traffic.
- Generator và DB có thể cùng chịu CPU pressure.
- Khi nguồn quá tải, DB query p99 có thể tăng 10 ms→2 s.
- Một số writes trả timeout nhưng vẫn có thể đã commit.
- Báo cáo hiện tại chỉ có p95/p99 những requests thành công.

### Phần A — Phát hiện CO

Một worker luôn chờ hoàn tất rồi mới gửi request khác.

1. Đó là closed-loop hay open-loop?
2. Nếu 100 workers và mean latency=10 ms, throughput lý tưởng là bao nhiêu?
3. Nếu mean latency=1 s, throughput lý tưởng là bao nhiêu?
4. Tại sao workload đã thay đổi đúng lúc source chậm?
5. Vì sao p99 successful-only không phản ánh fixed 5.000 arrivals/s?

### Phần B — Ba timestamps

Cho:
- Scheduled S=100 ms.
- Dispatch D=145 ms.
- Completed C=300 ms.

Tính:
1. Scheduler lag.
2. Dispatch-to-completion latency.
3. Scheduled-to-completion latency.
4. Metric nào phù hợp khi benchmark theo planned arrivals?
5. Nếu request chưa bao giờ được gửi, có measured service latency không?

**Gợi ý:** 45 ms, 155 ms và 200 ms.

### Phần C — Generator pause

Target=2.000 arrivals/s, JVM stop-the-world pause 2 giây.

1. Có bao nhiêu planned arrivals trong pause?
2. Nếu generator chỉ gửi 1% số đó, coverage là bao nhiêu?
3. Nếu scheduler bù ngay 4.000 ticks sau pause, workload thay đổi thế nào?
4. Nếu skip những ticks quá deadline, phải báo metrics gì?
5. Thiết kế test fail khi generator lag vượt ngưỡng ra sao?

### Phần D — Tính offered, sent, completed

Trong 60 giây:
- Scheduled 300.000.
- Sent 240.000.
- Success 220.000.
- Error/timeout 15.000.
- In-flight at end 5.000.

Giả sử 40.000 missed schedule và 20.000 admission rejection.

1. Planned rate?
2. Sent rate?
3. Delivery coverage?
4. Có thể tuyên bố NoSQL đã được test đúng 5.000 RPS không?
5. Vì sao 5.000 in-flight không nên bỏ khỏi báo cáo?

### Phần E — Correction

Cho một observed latency sample 1.000 ms, expected interval 10 ms.

1. HdrHistogram-style correction tạo loại samples nào?
2. Samples đó có thực sự được gửi không?
3. Nó có biết server sẽ reject hay queue các requests giả định không?
4. Nếu actual measured latency đã tính scheduled queue time, correction có thể sai thế nào?
5. Báo cáo raw và corrected ra sao để người đọc không hiểu nhầm?

### Phần F — Java generator

Thiết kế:
- PlannedArrival record.
- Async NoSQL transport.
- Absolute schedule.
- Monotonic timestamps.
- Nonblocking admission.
- Bounded max in-flight.
- Missed/rejected ledger.
- Timeouts/errors/in-flight.
- Histograms theo operation.

Giải thích vì sao không gọi blocking repository.read() trên scheduler thread.

### Phần G — NoSQL và hot partition

- 60% keys tập trung một partition.
- Range scans mất 2 s khi compaction.
- Point reads mất 10 ms.
- Writes mất 100 ms.

1. Closed-loop có thể làm operation mix measured lệch planned thế nào?
2. Cần đo per-operation/per-partition RPS gì?
3. Connection pool wait có tính vào client-visible latency không?
4. Nếu database trả throttling, SLO đo thế nào?
5. Nếu cache miss cùng lúc, điều gì xảy ra với source?

### Phần H — Retry

Một logical booking write:
- Attempt #1 timeout ở 500 ms.
- Attempt #2 retry và trả success sau 100 ms.
- Source có thể đã commit attempt #1.

1. Logical end-to-end latency tính từ đâu?
2. Có nguy cơ duplicate booking không?
3. OperationId/idempotency ledger dùng thế nào?
4. Timeout có đồng nghĩa failed commit không?
5. Physical attempts khác logical arrivals thế nào?

### Phần I — Multi-generator

Ba machines cùng phát:
- A scheduled 100.000, sent 100.000.
- B scheduled 100.000, sent 80.000.
- C scheduled 100.000, sent 50.000.

1. Tổng planned/sent coverage?
2. Có nên lấy average p99 của A/B/C không?
3. Nếu B bị GC pause và C bị CPU throttle, run có valid ở target tổng không?
4. Làm sao align time windows?
5. Có được trừ trực tiếp System.nanoTime của A và B không?

### Phần J — Fault injection

Thiết kế ít nhất 12 tests:
1. Scheduler GC pause 2 s.
2. Source latency spike 1 s.
3. Generator CPU quota 10%.
4. Client connection pool full.
5. Metrics exporter blocked.
6. Network delay/loss.
7. 429 throttling.
8. Request timeout 500 ms.
9. 5.000 outstanding requests lúc kết thúc.
10. Mass cache expiry.
11. Hot partition compaction.
12. Retry storm.
13. Histogram overflow.
14. Read/write mix drift.
15. Generator clock skew.
16. Slow result serialization.

Với mỗi test:
- Planned/sent/completed counts.
- Scheduler lag.
- Observed/scheduled latency.
- Timeout/drop/reject.
- SUT resource evidence.
- Validity conclusion.

### Phần K — Báo cáo capacity

Thiết kế một báo cáo gồm:
- Target RPS vs achieved.
- Arrival model.
- Delivery coverage.
- p50/p95/p99/p99.9 theo timing boundary.
- Timeout/reject/drop rates.
- In-flight at end.
- Retry amplification.
- Source CPU/IO, hot partitions và pool waits.
- Corrected histogram nếu dùng, được dán nhãn estimate.
- Generator health.
- Data correctness.
- RTO khi fault kết thúc.

### Phần L — Phản biện

Một đồng nghiệp nhận xét:

> “100 workers là đủ, mỗi worker cứ gửi request sau khi nhận response. Nếu database chậm, RPS giảm thì đó là đặc tính tự nhiên. Báo p99 các requests thành công là được; timeouts không có latency nên bỏ. Cứ dùng scheduleAtFixedRate là open-loop, không cần đo missed ticks. Sau mỗi run có thể áp correction rồi coi kết quả là latency thật.”

Hãy phản biện dựa trên:
- Closed-loop workload assumptions.
- CO và self-throttling.
- Scheduled vs dispatched timestamps.
- Generator capacity.
- Timeout/censored outcomes.
- Fixed-rate scheduler delay.
- Synthetic correction limitations.
- Offered/sent/completed reconciliation.
- SLO và business correctness.

### Hướng giải

Một test đáng tin:
- Mô hình hóa **independent planned arrivals** khi đo fixed-rate capacity.
- Không để gửi request sau phụ thuộc kết quả request trước.
- Giữ **scheduled, dispatch và completion timestamps**.
- Ghi **missed ticks, admissions, drops, timeouts và in-flight**.
- Đặt bounded concurrency/queues nhưng **không giảm planned RPS trong bí mật**.
- Đo p99 của successful attempts và scheduled-end-to-end với đúng nhãn.
- Dùng correction chỉ như **estimate minh bạch giả định**.
- Calibrate generator với stub và giám sát CPU/GC/pool.
- Chạy nhiều load stages, fault injection và báo generator delivery coverage.
- Không dùng những runs mà generator không đạt target để tuyên bố SUT đạt fixed-RPS SLO.

## 36. Checklist trước khi tin một số p99

1. **Workload là closed-loop hay independent arrivals?**
2. **Mục tiêu câu hỏi hiệu năng/SLO đã được nêu rõ?**
3. **RPS theo plan có độc lập với response?**
4. **Có scheduled timestamp cho mỗi logical arrival?**
5. **Có actual dispatch timestamp và completion timestamp?**
6. **Có đo scheduler lag p95/p99/max?**
7. **Có phát hiện tick bị miss khi generator pause?**
8. **Không dùng response-driven sleep thay fixed-arrival plan?**
9. **Có phân biệt fixed delay với fixed rate?**
10. **Nếu scheduler bắt kịp, có nhận biết catch-up bursts?**
11. **Load generator có đủ CPU/GC/network headroom?**
12. **Có calibrate với stub hoặc baseline nhẹ?**
13. **Có tách generator và SUT resources theo mục tiêu đo?**
14. **Có planned/sent/completed counts theo từng time window?**
15. **Có reported delivery coverage và run validity?**
16. **Có ghi admission rejection và schedule miss?**
17. **Bounded queues/max in-flight và deadlines rõ?**
18. **Có ghi requests vẫn in-flight cuối run?**
19. **Timeouts/errors không bị loại khỏi SLO denominators?**
20. **Có tách logical requests và physical retry attempts?**
21. **Client pool wait có được đo đúng boundary?**
22. **Async driver queue có được quan sát?**
23. **Có p99 theo read/write/query/partition class?**
24. **Có giữ planned mix khi overload hoặc ghi drift?**
25. **Có metric về hot keys/cache misses/compaction/replica lag?**
26. **Histogram có đủ range/precision và không overflow âm thầm?**
27. **Không average các p99 của nodes thành global p99?**
28. **Raw và corrected histograms được tách rõ nếu có?**
29. **Expected interval và assumptions của correction được lưu?**
30. **Không áp correction khi samples đã phản ánh queue/schedule time mà không đánh giá double counting?**
31. **Có đồng hồ monotonic cho elapsed trong JVM?**
32. **Không trừ raw nanoTime giữa machines?**
33. **Metrics recorder không block generator?**
34. **Có dùng short-window p99 thay vì chỉ full-run summary?**
35. **Có test generator GC pause/CPU throttle/scheduler block?**
36. **Có test server slowdown/throttle/network delay/pool exhaustion?**
37. **Có xác minh end-to-end logical success-within-deadline?**
38. **Có correctness checks cho NoSQL writes/transactions?**
39. **Có repeat runs và mô tả conditions?**
40. **Không tuyên bố SUT đạt target load nếu generator coverage không đủ?**

**Kết luận:** Khi bộ phát tải tự chậm lại lúc NoSQL đang nghẽn, các request đáng lẽ đến trong thời gian ấy có thể không được gửi và vì thế không xuất hiện trong histogram. Đó là **coordinated omission**, một nguồn sai lệch nghiêm trọng khi dùng closed-loop benchmark hoặc một fixed-rate scheduler không theo dõi lateness để suy khả năng phục vụ **independent arrivals**. Cách kiểm soát là xác định đúng workload model; lưu **scheduled arrival, actual dispatch và completion**; đối chiếu **planned/sent/completed/missed/rejected/timeouts/in-flight**; và thiết kế generator async với **bounded in-flight, deadlines, schedule-lag monitoring**. HdrHistogram-style correction có thể cung cấp **ước lượng bổ sung dưới giả định rõ**, nhưng không thay thế những requests thực đã bị bỏ hay sửa được một generator không đạt offered rate. Hãy báo **p99 cùng availability, load coverage, generator health và source resource metrics**, kiểm chứng bằng fault injection khi cả database lẫn bộ phát tải chậm, và chỉ kết luận NoSQL đáp ứng SLO tại một tải mục tiêu khi **thí nghiệm thực sự đã áp được tải đó**.
