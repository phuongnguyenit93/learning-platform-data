# Ước lượng thông lượng mục tiêu khi mở rộng Spring Batch

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Chuyển yêu cầu nghiệp vụ về số bản ghi, hạn hoàn thành và thời gian xử lý thành **thông lượng mục tiêu có đơn vị rõ ràng**.
- Phân biệt thông lượng **nghiệp vụ hữu ích** với số lượt đọc, xử lý, ghi hoặc retry mà hệ thống báo cáo.
- Tính ngân sách thời gian sau khi trừ chuẩn bị dữ liệu, xác minh kết quả, phần dự phòng và các giai đoạn không thể song song hóa.
- Ước lượng nhu cầu worker, connection và năng lực CPU/DB/API từ số đo baseline; phát hiện khi tăng thread vẫn không đạt SLA.
- Kiểm chứng ước lượng bằng load test đại diện, đo p95/p99 của thời gian job, phân bố partition, rollback/restart và throughput bền vững.
- Chọn mô hình Spring Batch phù hợp với tài nguyên thực tế mà không đánh đổi tính đúng đắn dữ liệu.

## 1. Thông lượng mục tiêu là gì?

Với workload lớn trong module **SPRING_BATCH_SCALING_OPERATIONS**, việc chạy multi-threaded step, parallel steps, partitioning hoặc remote workers là **phương tiện**; đích cuối là hoàn tất khối lượng nghiệp vụ đúng hạn, kết quả đúng và có khả năng restart.

**Thông lượng (throughput)** là lượng công việc hoàn thành trên một đơn vị thời gian. Tuy nhiên, “công việc” phải được định nghĩa trước. Một job có thể đồng thời công bố:

- `readCount/s`: số item reader trả về cho step trên một giây; chưa chắc đã xử lý thành công hoặc ghi bền vững.
- `processCount/s`: số item đi qua processor; có thể gồm nhiều lượt nếu retry.
- `writeCount/s`: số item mà Spring Batch ghi nhận writer đã xử lý; chưa chắc bằng số dòng vật lý mới trong DB.
- `businessItems/s`: số đơn vị nghiệp vụ **duy nhất và hợp lệ** đã hoàn tất đúng quy tắc (ví dụ mỗi đơn hàng được import đúng vào bảng đích).
- `bytes/s` hoặc `transactions/s`: bổ sung khi item có kích thước khác nhau hoặc một item kích hoạt nhiều câu SQL/API.

Để tính khả năng đáp ứng SLA, nên dùng **thông lượng nghiệp vụ hữu ích, duy trì được trên toàn job**:

~~~text
R_effective = số đơn vị nghiệp vụ hợp lệ và duy nhất hoàn tất
              ------------------------------------------------
                     thời gian thực tế đã trôi qua (giây)
~~~

Mẫu số có thể tính theo **thời gian toàn job** hoặc **thời gian riêng giai đoạn xử lý**; hai cách trả lời các câu hỏi khác nhau, phải ghi nhãn rõ. Không thay thời gian thực tế bằng tổng CPU time hay tổng thời gian các worker vì các worker đang chạy đồng thời.

Ví dụ hai worker cùng chạy 60 giây, mỗi worker ghi hợp lệ 12.000 đơn hàng. Thông lượng của giai đoạn là `24.000 / 60 = 400 orders/s`, **không phải** `24.000 / 120 = 200 orders/s`. Nhưng nếu cả job còn 20 giây chuẩn bị và 10 giây đối soát, thông lượng **end-to-end** là `24.000 / 90 ≈ 267 orders/s`.

### Ba khái niệm dễ bị trộn lẫn

| Thuật ngữ | Câu hỏi nó trả lời | Dễ sai ở đâu? |
| --- | --- | --- |
| **Thông lượng yêu cầu** (`R_target`) | Cần bao nhiêu item hợp lệ/giây để hoàn thành đúng hạn? | Không trừ thời gian chuẩn bị, downtime hoặc validation |
| **Thông lượng bền vững quan sát được** (`R_sustainable`) | Job thực sự giữ được tốc độ nào trên workload đại diện? | Dùng tốc độ peak vài giây đầu hoặc chỉ đo trên cache nóng |
| **Năng lực hệ thống có dự phòng** (`R_capacity`) | Hệ thống chịu được biến động, retry, tải đồng thời với biên an toàn nào? | Lấy throughput lý tưởng một thread nhân thẳng với số worker |

Số thread hoặc số partition là **input cấu hình**; tốc độ hoàn tất và chi phí tài nguyên là **kết quả đo**. Không nên gọi “8 partition/s” là throughput item nếu chưa định nghĩa mỗi partition chứa bao nhiêu công việc.

## 2. Chốt đơn vị công việc và nhu cầu đầu vào

Giả sử job xử lý bảng `orders`. Cần xác định rõ **cái gì được tính là một item**:

- Một dòng `orders`, một đơn hàng gồm nhiều dòng chi tiết hay một lô file?
- Có bao nhiêu record bị lọc hợp lệ? Filter có được coi là “hoàn thành nghiệp vụ” hay chỉ những record được ghi?
- Có trường hợp một input sinh nhiều output, hoặc nhiều input được gộp thành một output?
- Dữ liệu cần xử lý là snapshot cố định tại business date, hay liên tục tăng khi job đang chạy?
- Khối lượng đầu vào có lệch theo tenant, loại payload hoặc mùa cao điểm?

Ví dụ 20 triệu dòng nguồn, trong đó 2 triệu là duplicate và được bỏ qua theo quy tắc nghiệp vụ. Nếu SLA yêu cầu **quét và phân loại toàn bộ nguồn** trong cửa sổ, khối lượng đọc vẫn là 20 triệu, dù đầu ra chỉ có 18 triệu đơn hàng duy nhất. Phải định lượng cả **work done** (đọc/xử lý) và **business completion** (đầu ra hợp lệ), không dùng một tỷ lệ làm đại diện cho mọi stage.

Nên thu thập theo từng nhóm công việc:

| Thông tin | Ví dụ | Vì sao cần? |
| --- | --- | --- |
| Khối lượng `N` | 18 triệu đơn hàng/ngày | Tử số của mục tiêu |
| Tốc độ tăng | +15%/quý | Nhu cầu tương lai và headroom |
| Quy mô item | p50 2 KB, p99 120 KB | CPU, mạng, memory, kích thước batch |
| Phân bố chi phí | 5% item cần nhiều truy vấn hơn | Ước lượng skew theo partition |
| Tỷ lệ lỗi/retry | Trung bình 10% thao tác lặp lại | Nhu cầu năng lực thô cao hơn throughput hữu ích |
| Tải nền từ ứng dụng khác | 40% pool DB được dùng giờ cao điểm | Năng lực còn lại cho batch |
| SLA | Hoàn thành trước 05:00 | Giới hạn thời gian end-to-end |
| Mức tin cậy | 99% job phải đúng SLA | Cần xem phân vị p99, không chỉ average |

Nếu mỗi item có chi phí rất khác nhau, có thể dùng thêm **đơn vị công việc có trọng số**. Chẳng hạn bản ghi bình thường cần một lần ghi, bản ghi phức tạp cần năm lần ghi; khi đó ngoài record/s, đo thêm SQL operations/s, CPU-seconds và bytes/s.

## 3. Chuyển SLA thành ngân sách thời gian xử lý hữu ích

Công thức nền tảng:

~~~text
T_available = T_SLA_window - T_prepare - T_finalize - T_reserve - T_other

R_target = N_required / T_available
~~~

Trong đó:

- `T_SLA_window`: khoảng thời gian từ lúc dữ liệu có thể bắt đầu xử lý tới hạn chót.
- `T_prepare`: xác định snapshot, kiểm tra đầu vào, staging, khởi tạo job.
- `T_finalize`: tổng hợp/merge, kiểm chứng dữ liệu, publish kết quả.
- `T_reserve`: thời gian dành cho biến động, retry, sự cố ngắn; đây là **ngân sách thời gian**, không phải số item.
- `T_other`: thời gian phải đợi khóa, tài nguyên hoặc dependency biết trước nhưng chưa nằm trong các mục trên.

Tất cả thành phần phải đo hoặc ước lượng dựa trên cùng điều kiện tải. Nếu giai đoạn chuẩn bị và xử lý có thể overlap thật sự, cần lập sơ đồ đường găng thay vì trừ hai lần; ví dụ này giả định chúng **tuần tự**.

### Ví dụ xuyên suốt: 18 triệu đơn hàng trong 3 giờ

Job được phép bắt đầu lúc 02:00 và phải hoàn thành trước 05:00:

| Khoản mục | Phút |
| --- | ---: |
| Cửa sổ SLA từ 02:00 đến 05:00 | 180 |
| Chuẩn bị snapshot, kiểm tra nguồn | −20 |
| Đối soát và publish kết quả | −10 |
| Dự phòng cho sự cố/tải dao động | −30 |
| **Thời gian còn cho xử lý dữ liệu** | **120** |

Do đó:

~~~text
N_required   = 18.000.000 đơn hàng hợp lệ
T_available  = 120 phút × 60 = 7.200 giây

R_target     = 18.000.000 / 7.200
             = 2.500 đơn hàng hợp lệ/giây
~~~

Con số **2.500/s** là thông lượng hữu ích mà giai đoạn xử lý phải **duy trì trong 2 giờ đã dành**, không phải một peak ngắn ngủi. Nếu throughput dao động, việc có lúc đạt 4.000/s không bù được thời gian dài chạy dưới 1.500/s trừ khi trung bình tích lũy thực sự đủ.

Để tính cho một job có nhiều stage chạy tuần tự, có thể phân ngân sách riêng:

~~~text
02:00 ─ 02:20   chuẩn bị snapshot
02:20 ─ 04:20   đọc, xử lý, ghi dữ liệu
04:20 ─ 04:30   verify & publish
04:30 ─ 05:00   phần dự phòng
~~~

Nếu throughput giai đoạn xử lý chỉ đạt 2.000/s, 18 triệu đơn hàng mất `18.000.000 / 2.000 = 9.000 giây = 150 phút`: giai đoạn sẽ vượt ngân sách 120 phút thêm 30 phút và ăn hết toàn bộ phần dự phòng.

### SLA theo phân vị thay vì một lần chạy “đẹp”

Nếu yêu cầu 99% job hoàn thành đúng hạn, hãy đo **phân phối thời gian hoàn thành từ nhiều lần chạy** dưới tập tải đại diện. `p99(job_duration)` phải phù hợp giới hạn; `average(job_duration)` thấp chưa đủ.

Một chỉ số `p95(step_duration)` không thể cộng/nhân tùy ý rồi gọi là `p95(job_duration)`, vì phân phối và sự tương quan giữa các step khác nhau. Cần đo end-to-end hoặc dùng mô hình xác suất có dữ liệu thực.

## 4. Từ throughput hữu ích sang năng lực thô cần có

Trong thực tế, một phần công việc làm lại do retry, rollback, message giao lại, lỗi mạng hoặc conflict. Để lập kế hoạch, định nghĩa **hệ số công việc thô**:

~~~text
W = số lượt thao tác xử lý thực tế / số item nghiệp vụ hoàn tất hợp lệ

R_raw_required = R_target × W
~~~

Nếu trung bình cần xử lý tương đương **1,10 lượt** cho mỗi item hoàn tất (`W = 1,10`), giai đoạn trên cần:

~~~text
R_raw_required = 2.500 × 1,10 = 2.750 lượt xử lý tương đương/giây
~~~

`W` là mô hình dựa trên số đo, không phải một hằng số của Spring Batch. Nếu mỗi attempt độc lập lỗi với xác suất `p` và retry đến khi thành công, số attempt kỳ vọng là `1/(1-p)`; nhưng giả định độc lập thường không đúng khi DB bị nghẽn hoặc API cùng trả 429. Khi tải tăng, retry có thể tăng theo và tạo **retry storm**.

Cũng không nên cho mọi loại operation cùng một hệ số: đọc có thể lặp lại, processor có thể bị gọi nhiều lần, writer có thể được thực thi lại sau rollback; dùng metric thực tế cho từng stage khi có dữ liệu.

### Headroom khác với retry

Ngoài công việc làm lại, vận hành thường yêu cầu **dự phòng năng lực** để chịu biến động dữ liệu/nguồn tài nguyên. Ví dụ muốn công suất thô cao hơn nhu cầu tính toán 20%:

~~~text
R_raw_planned = R_target × W × 1,20
              = 2.500 × 1,10 × 1,20
              = 3.300 lượt xử lý tương đương/giây
~~~

Đây là cách định nghĩa **20% công suất cao hơn nhu cầu**, không phải công thức duy nhất cho “20% utilization reserve”. Nếu chính sách là chỉ sử dụng tối đa 80% công suất, cần tính `R_capacity ≥ R_raw_required / 0,80 = 3.437,5/s`. Phải thống nhất quy ước để tránh tranh luận giữa hai con số đều được gọi là “20% buffer”.

Trong ví dụ, phần dự phòng **30 phút** ở mục 3 là dự phòng thời gian; `1,20` ở đây là dự phòng **năng lực tức thời**. Có thể dùng cả hai để bảo thủ, nhưng phải ghi rõ vì nếu số liệu đã được đo với tải xấu nhất và có dự phòng, có nguy cơ cộng dự phòng hai lần không chủ ý.

## 5. Năng lực cuối cùng bị giới hạn bởi bottleneck

Một worker không chỉ tiêu thụ CPU. Mỗi item có thể đi qua reader, processor, DB writer, object storage, network và dịch vụ API.

~~~mermaid
flowchart LR
    S["Nguồn dữ liệu / Reader"] --> P["Processor: CPU + API"]
    P --> W["Writer: DB / Object storage"]
    W --> V["Verify / Merge"]
    S -.-> C["DB connections + I/O"]
    P -.-> A["Rate limit / network"]
    W -.-> C
    V -.-> D["SLA deadline"]
~~~

Với một pipeline ổn định, không backlog tăng vô hạn, thông lượng tối đa bị chặn bởi stage hẹp nhất:

~~~text
R_pipeline ≤ min(R_reader, R_processor, R_writer, R_external)
~~~

Đây là **cận trên đơn giản hóa**: không thể lấy tốc độ cao nhất của từng stage đo ở những thời điểm khác nhau rồi cho rằng tất cả giữ được tốc độ đó khi cùng chạy. Pipeline nhiều stage còn mất thời gian làm đầy/xả pipeline và cần buffer/backpressure.

### Ví dụ: vì sao bốn worker vẫn chưa đủ?

Giả sử một worker độc lập xử lý được `900 lượt/s` trong bài đo nhỏ. Theo quy tắc nhân tuyến tính lý tưởng:

~~~text
số worker tối thiểu lý tưởng = ceil(3.300 / 900) = 4
4 worker × 900 = 3.600 lượt/s (giả định không tranh chấp)
~~~

Nhưng kiểm thử tải cho thấy DB chỉ chịu bền vững **2.800 lượt ghi tương đương/giây** trong thời gian dài. Khi đó thêm worker không làm năng lực end-to-end vượt trần DB:

~~~text
R_raw_max       ≈ min(4 × 900, 2.800) = 2.800/s
R_effective_max ≈ 2.800 / 1,10 ≈ 2.545 item hợp lệ/s
~~~

Mức `2.545/s` chỉ nhỉnh hơn mục tiêu `2.500/s` và **không đạt yêu cầu năng lực dự phòng 3.300/s**. Khi tính tốc độ thực tế dao động, lock và thời gian restart, thiết kế này có rủi ro SLA. Giải pháp đúng có thể là tối ưu SQL/index, batch writer, tăng I/O DB, giảm số thao tác ghi mỗi item, nới cửa sổ xử lý hoặc thay đổi phân chia dữ liệu; chỉ thêm thread không giải quyết.

### Các giới hạn thường gặp

| Nút thắt | Dấu hiệu | Hướng thử nghiệm |
| --- | --- | --- |
| Reader/SQL | Full table scan, DB đọc nhiều hơn mong đợi, cursor chờ I/O | Index đúng predicate, paging/keyset, snapshot và phân vùng nguồn |
| Processor CPU | CPU gần bão hòa, worker ít chờ I/O | Giảm cấp phát, tối ưu thuật toán, chia theo partition độc lập |
| Writer DB | Commit chậm, lock wait/deadlock, write IOPS bão hòa | Batch writes, khóa unique, thiết kế upsert, giảm contention |
| Pool connection | Worker đợi lấy connection, timeout khi tăng thread | Sizing pool và số transaction thực tế; giảm concurrency |
| API ngoài | 429/throttling, p95 latency tăng | Global rate limiter, backoff, cache hoặc giảm số request |
| Network/serialization | Worker remote bận chuyển dữ liệu | Giảm payload, gom batch, đưa xử lý gần dữ liệu |
| JobRepository | Metadata update/partition count quá dày | Cân đối chunk/partition size, monitor repository |
| Phân chia lệch | Một worker kéo dài trong khi worker khác rảnh | Chia theo khối lượng/chi phí thực thay vì ID range đều |

## 6. Ước lượng tài nguyên từ thông lượng yêu cầu

### 6.1. CPU: tính theo CPU time trên mỗi item

Nếu processor cần trung bình `c` CPU-second cho một item nghiệp vụ và cần xử lý `R` item/s, nhu cầu lý tưởng:

~~~text
CPU_cores_busy ≈ R × c

CPU_cores_provisioned ≥ (R × c) / target_CPU_utilization
~~~

Giả sử trong một bài đo riêng, item tốn trung bình 4 ms CPU và cần 2.500 item/s:

~~~text
CPU busy demand = 2.500 × 0,004 = 10 CPU cores
Nếu target CPU utilization = 70%:
cores cần provision ≈ 10 / 0,70 ≈ 14,3 cores
~~~

Đây chỉ là nhu cầu phần **processor CPU**; chi phí reader/writer, GC, phân bố item nặng, giới hạn quota container và contention có thể cần thêm tài nguyên. Không đồng nhất “16 vCPU được cấp” với “16 CPU luôn sẵn sàng ở 100%”.

### 6.2. API latency và số yêu cầu đang bay

Với hệ thống có request I/O đang chờ, định luật Little cho hệ thống ổn định cho trực giác sizing:

~~~text
L ≈ λ × W

L : số request trung bình đang ở hệ thống
λ : số request hoàn tất mỗi giây
W : thời gian một request ở hệ thống (giây)
~~~

Ví dụ cần `400 API requests/s`, thời gian đáp ứng trung bình `0,20 s`:

~~~text
L ≈ 400 × 0,20 = 80 request đồng thời
~~~

Nếu thực tế chỉ có 40 connection/in-flight slot dùng được, throughput tối đa theo cùng độ trễ trung bình chỉ xấp xỉ `40 / 0,20 = 200 requests/s`, chưa tính queue/backoff. Thêm `@Async` task nhưng không tăng capacity hoặc không giảm latency chỉ đẩy thêm công việc vào hàng đợi.

Nếu nhà cung cấp giới hạn **250 RPS**, mục tiêu 400 RPS không khả thi dù hệ thống nội bộ có 1.000 thread. Lúc đó cần giảm số lần gọi, dùng batch API hoặc điều chỉnh lịch xử lý.

### 6.3. Connection pool và transaction

Một partition có reader cursor có thể giữ kết nối lâu; writer có thể dùng transaction connection khác; JobRepository có connection/transaction riêng. Vì vậy không có công thức cố định “`poolSize = số worker`”.

Cần đo **peak connections**, thời gian chờ connection, DB max connections và mức sử dụng bởi dịch vụ khác. Giới hạn executor, JDBC pool và khả năng DB phải được thiết kế cùng nhau. Một job partition thành 8 worker có thể chạy tốt trên 8 CPU core nhưng timeout nếu chỉ còn 4 connection khả dụng.

### 6.4. Chunk size và chi phí commit

Với chunk-oriented processing, một mô hình đơn giản:

~~~text
R_chunk_worker ≈ C / (C × t_item + t_commit + t_fixed_chunk)

C              : số item trong chunk
t_item         : thời gian trung bình cho mỗi item
t_commit       : chi phí commit
t_fixed_chunk  : chi phí cố định khác mỗi chunk
~~~

Nếu `t_item = 5 ms`, tổng chi phí cố định mỗi chunk là `40 ms`:

| Chunk size | Thời gian theo mô hình | Thông lượng worker xấp xỉ |
| --- | ---: | ---: |
| 20 | `20 × 5 + 40 = 140 ms` | `20 / 0,140 ≈ 143 item/s` |
| 200 | `200 × 5 + 40 = 1.040 ms` | `200 / 1,040 ≈ 192 item/s` |

Tăng chunk size giúp giảm chi phí commit trên mỗi item trong mô hình này. Tuy vậy, chunk quá lớn làm transaction kéo dài, chiếm bộ nhớ, tăng lượng rollback/retry khi lỗi và gây lock contention. Hãy đo throughput, heap, commit latency và rollback trong workload thật, không chọn chunk lớn nhất chỉ theo công thức.

## 7. Parallelism có giới hạn: bước tuần tự và partition lệch tải

Đối với công việc có phần tuần tự chiếm tỷ lệ `s`, luật Amdahl cho cận trên tốc độ tăng khi có `p` worker:

~~~text
Speedup(p) ≤ 1 / (s + (1 - s) / p)
~~~

Nếu 10% thời gian của phần đang xét không song song hóa được và dùng 8 worker:

~~~text
Speedup(8) ≤ 1 / (0,10 + 0,90 / 8) ≈ 4,71 lần
~~~

Trong Spring Batch, phần tuần tự có thể là chuẩn bị snapshot, một reader duy nhất, merge kết quả hoặc tạo report. Tăng số partition lên 16 không xóa được chi phí đó.

Ngay cả khi toàn bộ công việc *có thể* chia, partitioning còn vướng **skew**:

~~~text
T_partition_phase ≥ max(T_partition_1, T_partition_2, ..., T_partition_n)
~~~

Ví dụ bốn partition có thời gian `100 s, 100 s, 110 s, 420 s`. Giai đoạn chỉ hoàn tất khi partition nặng nhất xong, tức ít nhất 420 giây; ba worker khác có thể rảnh phần lớn thời gian. Chia theo khoảng ID bằng nhau thường không bảo đảm số bản ghi, kích thước payload hoặc chi phí API bằng nhau.

Chia lại theo quantile hoặc theo nhóm có trọng số là hướng cải thiện. Nhưng nếu phải giữ tất cả giao dịch của một tài khoản cùng worker để bảo toàn thứ tự, không thể tùy tiện chẻ nhóm chỉ để cân bằng CPU.

### Parallel steps: thời gian ở nhánh găng

Với hai flow độc lập A và B được chạy bằng `split` rồi cần một step C:

~~~text
T_parallel_job ≈ T_prepare + max(T_A, T_B) + T_C + overhead
~~~

Tối ưu B từ 6 phút xuống 3 phút không giúp giảm thời gian job nếu A vẫn mất 18 phút. Trong đo lường, luôn ghi duration của **flow chậm nhất**, vì nó quyết định điểm join.

## 8. Java: bộ tính mục tiêu và kiểm tra năng lực ban đầu

Đoạn Java 17 dưới đây chuyển input kế hoạch thành các con số, nhằm kiểm tra tính hợp lý **trước** khi benchmark. Nó không đụng trực tiếp Spring Batch nên có thể chạy riêng như chương trình console:

~~~java
import java.time.Duration;
import java.util.Locale;

public final class BatchThroughputEstimate {

    public static void main(String[] args) {
        long eligibleItems = 18_000_000L;

        Duration slaWindow = Duration.ofMinutes(180);
        Duration prepare = Duration.ofMinutes(20);
        Duration finalizeStage = Duration.ofMinutes(10);
        Duration reserve = Duration.ofMinutes(30);

        Duration available = slaWindow
                .minus(prepare)
                .minus(finalizeStage)
                .minus(reserve);

        if (eligibleItems <= 0 || available.isZero() || available.isNegative()) {
            throw new IllegalArgumentException("Invalid items/time budget");
        }

        double seconds = available.toMillis() / 1000.0;
        double effectiveItemsPerSecond = eligibleItems / seconds;

        // Hai hệ số phải được hiệu chỉnh theo dữ liệu benchmark.
        double workAmplification = 1.10; // retry/rework
        double capacityMargin = 1.20;    // thêm 20% năng lực thô
        double rawRequired = effectiveItemsPerSecond * workAmplification;
        double plannedRawCapacity = rawRequired * capacityMargin;

        // Các số đo giả định từ benchmark:
        double oneWorkerRawRate = 900.0;
        double observedDbRawCeiling = 2_800.0;

        long idealWorkers = (long) Math.ceil(
                plannedRawCapacity / oneWorkerRawRate);
        double idealAggregateRawRate = idealWorkers * oneWorkerRawRate;
        double cappedRawRate = Math.min(
                idealAggregateRawRate, observedDbRawCeiling);
        double estimatedNetRate = cappedRawRate / workAmplification;

        System.out.printf(Locale.US,
                "Available: %.0f seconds%n", seconds);
        System.out.printf(Locale.US,
                "Target effective: %.0f business items/s%n",
                effectiveItemsPerSecond);
        System.out.printf(Locale.US,
                "Raw required: %.0f work units/s%n", rawRequired);
        System.out.printf(Locale.US,
                "Planned raw capacity: %.0f work units/s%n",
                plannedRawCapacity);
        System.out.printf(Locale.US,
                "Ideal workers without contention: %d%n", idealWorkers);
        System.out.printf(Locale.US,
                "Effective after measured DB cap: %.0f items/s%n",
                estimatedNetRate);
        System.out.println(
                cappedRawRate >= plannedRawCapacity
                        ? "Capacity margin: PASS (estimated)"
                        : "Capacity margin: FAIL; remove bottleneck");
    }
}
~~~

Kết quả dự kiến (làm tròn):

~~~text
Available: 7200 seconds
Target effective: 2500 business items/s
Raw required: 2750 work units/s
Planned raw capacity: 3300 work units/s
Ideal workers without contention: 4
Effective after measured DB cap: 2545 items/s
Capacity margin: FAIL; remove bottleneck
~~~

Từng số trong ví dụ chỉ có ý nghĩa khi cách tính item, retry factor và DB limit được đo trên **cùng một loại công việc**. Nếu processor và writer có hai dạng throughput khác đơn vị, phải đổi về cùng số thao tác/bản ghi trước khi dùng phép `min`.

## 9. Đo baseline và throughput bền vững trong Spring Batch

Một benchmark có ích nên đi từ **một worker có tính đúng đắn đã được xác minh**, rồi tăng dần mức song song. Tránh chọn baseline từ 100 bản ghi vừa nằm trong cache rồi nhân lên cho 18 triệu bản ghi.

### 9.1. Thu thập đúng dữ liệu từ metadata

Spring Batch lưu các chỉ số step như `READ_COUNT`, `WRITE_COUNT`, `COMMIT_COUNT`, `ROLLBACK_COUNT` vào `BATCH_STEP_EXECUTION` của JDBC JobRepository. Với PostgreSQL và tên partition dạng `workerStep:partition0`, có thể đọc số liệu của một `JobExecution`:

~~~sql
SELECT
    STEP_NAME,
    STATUS,
    READ_COUNT,
    FILTER_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    EXTRACT(EPOCH FROM (END_TIME - START_TIME)) AS elapsed_seconds
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
  AND STEP_NAME LIKE 'workerStep:%'
ORDER BY STEP_NAME;
~~~

Tham số `:jobExecutionId` được bind bởi client hỗ trợ named parameter (hoặc thay bằng placeholder đúng công cụ SQL). Cần dùng **tên worker step thực tế** của ứng dụng. Đừng cộng cả manager step và các worker nếu muốn tránh đếm nhầm.

Lưu ý:

- `readCount` không tự động tương đương số business key duy nhất đã hoàn tất.
- `writeCount` là metric của quá trình writer, không chứng minh DB cuối cùng có từng ấy dòng mới hoặc side effect ngoài DB chính xác một lần.
- `commitCount` và `rollbackCount` giúp phát hiện overhead/fault tolerance; chúng không thay thế số item hợp lệ.
- `StepExecution` của các partition chạy đồng thời có khoảng thời gian trùng nhau. **Không cộng** `elapsed_seconds` của mọi partition để làm thời gian toàn job.
- Khi restart cùng `JobInstance`, có thể có nhiều `JobExecution`; phải quyết định đo một lần chạy hay toàn bộ thời gian để hoàn tất một business window.

Để đo `R_effective`, xác định số business key đầu ra đã commit/đối soát thành công và chia cho **wall-clock time** từ thời điểm bắt đầu yêu cầu đến khi kết quả hoàn tất theo SLA. Với output có upsert/deduplication, hãy lấy số key hợp lệ thực thay vì tổng số lần gọi writer.

### 9.2. Một bộ số đo vận hành tối thiểu

| Chỉ số | Công dụng |
| --- | --- |
| `job_duration_seconds`, p50/p95/p99 | Chứng minh hoàn thành cửa sổ SLA |
| `business_items_completed_total` | Tử số thông lượng hữu ích; phải tránh đếm lặp retry |
| `items_read_total` / `items_written_total` | Phân tích throughput mỗi stage |
| `step_commit_count` / `step_rollback_count` | Chi phí transaction và tỷ lệ lỗi |
| `partition_duration_seconds`, `partition_item_count` | Phát hiện skew và đường găng |
| `executor_active_threads` / `executor_queue_size` | Đo mức song song thực, hàng đợi và starvation |
| `jdbc_connections_active` / `pending` | Phát hiện cạn pool và chờ DB |
| `db_lock_wait`, `slow_queries`, `IOPS` | Xác định nút thắt DB |
| `api_requests_per_second` / `429` / p95 latency | Rate limit và retry storm |
| `retries_total` / `skips_total` / `business_duplicates` | Đối chiếu năng lực thô với kết quả nghiệp vụ |

Tên metric nêu ở bảng là **tên khuyến nghị cho dashboard**, không bảo đảm Spring Batch/Micrometer xuất sẵn tất cả tên đó. Cần kết hợp các metric framework có sẵn với custom metrics và DB observability, đồng thời kiểm soát cardinality label (ví dụ không gắn `orderId` duy nhất lên metric).

### 9.3. Chuẩn thử nghiệm có thể so sánh

1. Cố định dataset hoặc snapshot, số record, loại payload và số lượng tenant. Có trường hợp item nặng, ID thưa, partition lệch và chunk lỗi.
2. Đo mức **1 worker** ít nhất một vài lượt để xác định tốc độ bền vững và độ dao động.
3. Lặp với **2, 4, 8 worker**, giữ nguyên tổng lượng dữ liệu và kiểm tra đầu ra tương đương.
4. Đo cả giai đoạn chuẩn bị, xử lý, đối soát, không báo chỉ thời gian processor.
5. Chạy đủ dài để cache/GC, connection pool, checkpoint, DB WAL/IO và ảnh hưởng tải nền xuất hiện; ghi nhận trạng thái ổn định.
6. Thử dưới tải đồng thời giống production (các API/DB khác), không chỉ trong môi trường trống.
7. Cố tình gây rollback/retry và restart một partition sau vài chunk; xác nhận thời gian hồi phục, idempotency và tỷ lệ rework.
8. Quan sát throughput **toàn job**; ngừng tăng concurrency khi đường cong bão hòa hoặc lỗi/tài nguyên xấu đi.

Nếu throughput tăng từ 900 lên 1.700 rồi 2.600 nhưng 8 worker chỉ đạt 2.750/s, hãy tìm giới hạn tài nguyên thay vì tiếp tục nhân theo 900. Một phép đo 4 worker chỉ có giá trị suy rộng nếu DB/CPU/hạ tầng chịu được tổ hợp workload tương ứng.

## 10. Tính throughput khi nguồn liên tục phát sinh dữ liệu

Không phải job nào cũng xử lý snapshot cố định. Với backlog và dòng dữ liệu đến liên tục, chỉ hoàn thành “bằng tốc độ dữ liệu đến” là **chưa đủ để xóa backlog**.

Gọi:

- `B`: số item còn tồn đầu kỳ.
- `λ`: tốc độ có thêm item mới (item/s).
- `μ`: tốc độ hệ thống hoàn thành item hợp lệ (item/s).

Nếu `μ > λ` và hệ thống ổn định, thời gian xóa backlog xấp xỉ:

~~~text
T_catchup ≈ B / (μ - λ)
~~~

Ví dụ tồn 3 triệu item, nguồn thêm 100 item/s, job hoàn tất bền vững 600 item/s:

~~~text
T_catchup ≈ 3.000.000 / (600 - 100)
          = 6.000 giây = 100 phút
~~~

Nếu `μ ≤ λ`, backlog không thể giảm bền vững. Nếu không có snapshot nhất quán hoặc input tăng khi worker đang quét, cần định nghĩa watermark và chiến lược xử lý late arrivals; không nên coi phép đo `readCount` một lần chạy là toàn bộ nhu cầu.

## 11. Lựa chọn kiến trúc Spring Batch dựa trên nhu cầu đo được

| Dấu hiệu thực tế | Phương án đáng xem xét | Điều kiện trước khi áp dụng |
| --- | --- | --- |
| Một processor nặng CPU, reader/writer đã đủ nhanh | Song song hóa processor theo mô hình hỗ trợ của phiên bản Batch | Không chia sẻ mutable state; hiểu rõ transaction boundary |
| Nhiều flow độc lập, mỗi flow xử lý một nguồn riêng | **Parallel steps** qua `split` | Luồng tổng hợp phải đợi các flow cần thiết; không có dependency ẩn |
| Một tập input lớn chia theo ID/tenant/file | **Partitioning** local | Partition bao phủ đủ, không chồng lấn; reader `@StepScope`, restart ổn định |
| Một node thiếu CPU/RAM/network, dữ liệu chia được | **Remote partitioning** | Metadata và worker protocol bền vững, retry/idempotent, quan trắc remote |
| Reader trung tâm đủ nhanh, processor/writer tốn tài nguyên | **Remote chunking** | Message delivery, backpressure, side effect chống lặp, không đẩy nghẽn sang broker |
| DB writer đã bão hòa khi chỉ 2 worker | Tối ưu write, index, transaction, partition vật lý hoặc năng lực DB | Không tăng worker theo công thức tuyến tính |
| API ngoài có RPS thấp | Cache, batch API, rate limiter, lập lịch lại | Tuân thủ giới hạn API và tránh retry storm |

Tăng concurrency ở **cấp job** cũng phải tính chung: hai `JobExecution` chạy song song, mỗi job có 8 partition, có thể tạo tới 16 worker cùng đòi connection và CPU. Scheduler cần chính sách giới hạn overlap, xếp hàng hoặc phân quyền tài nguyên để tổng công suất không bị vượt quá khả năng hạ tầng.

Chọn kiến trúc phải dựa vào **trần bottleneck và sự độc lập dữ liệu**, không chỉ vì framework có thể tạo nhiều thread.

## 12. Kịch bản nhạy cảm: khi dự báo ban đầu thay đổi

Quay lại bài toán 18 triệu đơn hàng và 7.200 giây xử lý. Điều gì xảy ra nếu khối lượng tăng?

| Kịch bản | Items cần hoàn tất | `R_target` hữu ích | `R_raw_planned` với `W=1,10` và nhân 1,20 |
| --- | ---: | ---: | ---: |
| Baseline | 18.000.000 | 2.500/s | 3.300/s |
| Tăng 25% số item | 22.500.000 | 3.125/s | 4.125/s |
| Giảm thời gian xử lý còn 90 phút | 18.000.000 | ≈3.333/s | ≈4.400/s |
| Tải tăng 25% và chỉ còn 90 phút | 22.500.000 | ≈4.167/s | 5.500/s |

Số ở bảng làm tròn nhằm hoạch định năng lực. Không nên trình bày chúng như benchmark đã đạt. Đối với loại item có kích thước phân bố lệch, phải cập nhật cả chi phí CPU/DB/API tương ứng; tăng 25% record không nhất thiết chỉ tăng 25% thời gian.

Để đánh giá rủi ro, hãy lập ít nhất ba kịch bản:

- **Normal:** workload ngày thường, retry ít, tài nguyên ổn định.
- **Busy:** dữ liệu mùa cao điểm, có cạnh tranh DB/API, vài partition nặng.
- **Recovery:** một worker/partition lỗi và phải restart, job vẫn cần hoàn tất hoặc có quy trình chạy bù rõ ràng.

Chỉ khi kịch bản tải và recovery dự kiến đáp ứng mục tiêu SLA/chi phí chấp nhận được mới nên triển khai production với concurrency đó.

## 13. Checklist nghiệm thu mục tiêu thông lượng

Một ước lượng được coi là đủ căn cứ khi có các bằng chứng sau:

1. **Đã định nghĩa item nghiệp vụ:** cách đếm hợp lệ, duplicate, filter, skip và đơn vị đo của từng stage.
2. **SLA có cửa sổ rõ ràng:** giờ bắt đầu/kết thúc, timezone, thời gian staging/verify, ràng buộc chạy bù và thời gian dự phòng.
3. **Có công thức mục tiêu:** `N / T_available` cùng hệ số retry/rework và headroom được định nghĩa thống nhất.
4. **Có phép đo baseline:** ít nhất một cấu hình worker hoàn thành thật, dữ liệu đại diện và số đo end-to-end.
5. **Đã xác định bottleneck:** CPU, DB, index, connection, API, mạng, metadata; có cận trên throughput thực tế.
6. **Đã kiểm tra correctness:** các partition không bỏ sót/chồng lấn; xử lý độc lập; writer an toàn khi retry và restart.
7. **Đã đo scaling curve:** nhiều mức concurrency, throughput bền vững, p95/p99 duration, tình trạng queue/lock và lợi ích cận biên.
8. **Có phương án khi không đạt:** tối ưu bottleneck, giảm work mỗi item, đổi kiến trúc, mở rộng tài nguyên, kéo dài cửa sổ hoặc chia lịch.
9. **Có điều kiện vận hành:** cảnh báo nguy cơ lỡ deadline, backlog, stalled partition, retry storm, DB saturation và công cụ phục hồi.

### Bài tập tự kiểm tra

Một job có 9 triệu item hợp lệ cần xử lý trong cửa sổ 2 giờ. Trước xử lý cần 15 phút staging, sau xử lý cần 5 phút verify và dành 10 phút dự phòng. Benchmark cho thấy mỗi worker đạt 600 lượt/s khi chạy riêng, chi phí retry/rework trung bình `W = 1,08`, muốn năng lực cao hơn nhu cầu thô 15%.

**Câu hỏi:** Tính thời gian hữu ích, thông lượng mục tiêu, throughput thô có margin và số worker tối thiểu *theo mô hình tuyến tính*. Nếu DB có trần 1.200 lượt/s, cấu hình ba worker có đủ không?

**Gợi ý lời giải:**

~~~text
T_available = (120 - 15 - 5 - 10) × 60 = 5.400 giây

R_target = 9.000.000 / 5.400 ≈ 1.666,67 item/s

R_raw_required = 1.666,67 × 1,08 ≈ 1.800 lượt/s

R_raw_planned = 1.800 × 1,15 = 2.070 lượt/s

Workers tuyến tính tối thiểu = ceil(2.070 / 600) = 4

DB cap = 1.200 lượt/s
⇒ R_effective_max ≈ 1.200 / 1,08 ≈ 1.111 item/s
~~~

Ngay cả bốn worker cũng không đủ nếu trần DB thực tế là 1.200 lượt/s. Cần nâng năng lực DB, giảm số write/query mỗi item, tối ưu staging/SQL hoặc nới cửa sổ. Đây chính là lý do ước lượng throughput phải **đối chiếu nút thắt** trước khi ấn định `gridSize`.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps, partitioning, remote processing.
- [Spring Batch 5.2 Reference – Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): tham chiếu cấu hình cho các phiên bản Batch 5.x.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): số liệu Batch, kết hợp Micrometer để quan sát job/step.
- [Spring Batch Reference – JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): metadata, trạng thái step và restart.
- [Spring Batch Reference – Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/index.html): vai trò của reader/writer trong throughput end-to-end.

## Ghi nhớ

**Ước lượng thông lượng mục tiêu bắt đầu từ nghiệp vụ: số item hợp lệ phải hoàn thành trong thời gian xử lý hữu ích, rồi mới xét hệ số retry, dự phòng và tài nguyên.** Số worker chỉ là một phần của mô hình; tốc độ thực tế bị giới hạn bởi bottleneck, thời gian trên đường găng, độ lệch partition, transaction và side effect. Hãy đo năng lực bền vững của toàn job cùng tính đúng đắn khi retry/restart trước khi quyết định scale Spring Batch.
