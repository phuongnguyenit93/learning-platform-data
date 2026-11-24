# Chọn capacity cho batch theo deadline và ngân sách

Batch processing xử lý một tập công việc hữu hạn như tổng hợp báo cáo, ETL, render media, tính toán mô phỏng, xử lý ảnh hoặc huấn luyện theo lô. Khác với API tương tác, batch thường có thể chạy trong một khoảng thời gian dài hơn và chia thành nhiều task. Tuy nhiên, batch vẫn có deadline, giới hạn ngân sách và yêu cầu về chất lượng dữ liệu. Chọn quá ít compute khiến job trễ hạn; chọn quá nhiều có thể hoàn thành sớm nhưng lãng phí chi phí hoặc làm quá tải database, storage và network.

Chọn capacity là bài toán cân bằng giữa **khối lượng công việc**, **thời gian khả dụng**, **năng lực mỗi worker**, **mức song song hóa**, **độ tin cậy của capacity** và **chi phí toàn bộ pipeline**. Không nên bắt đầu bằng câu hỏi “cần bao nhiêu VM?” mà cần xác định batch phải hoàn thành khi nào, có bao nhiêu dữ liệu, mỗi đơn vị tốn bao nhiêu CPU/memory/I/O, phần nào có thể chạy song song và điều gì xảy ra khi worker bị lỗi hoặc bị thu hồi.

Trong module CLOUD_CORE_SERVICES_COMPUTE, bài học kết nối lựa chọn CPU, bộ nhớ, mạng, VM, container, serverless và compute có thể bị thu hồi với mục tiêu vận hành batch. Bạn sẽ xây dựng capacity estimate từ benchmark, kiểm tra deadline feasibility, so sánh các cấu hình và điều chỉnh theo ngân sách thay vì chỉ tối đa hóa số lượng instance.

Sau bài học, bạn có thể:

- Phân rã deadline thành queue, provisioning, execution, output commit và buffer.
- Ước lượng compute demand từ số lượng dữ liệu và thời gian xử lý đo được.
- Tính số worker/vCPU cần thiết có xét utilization và parallel efficiency.
- Chọn CPU, memory, GPU, storage và network theo bottleneck thực tế.
- So sánh VM, container, serverless, on-demand, committed capacity và spot/interruptible.
- Lập cost model gồm compute, storage, network, orchestration, retry và thời gian nhàn rỗi.
- Thiết kế autoscaling, checkpoint, retry và backpressure để giữ deadline khi capacity thay đổi.
- Benchmark, load test và chọn cấu hình đáp ứng cả deadline lẫn ngân sách.

## 1. Bắt đầu từ deadline và ngân sách

Hai ràng buộc đầu tiên là thời điểm phải hoàn thành và số tiền tối đa có thể chi cho một lần chạy hoặc một kỳ vận hành.

### Deadline không chỉ là thời gian compute

Tổng thời gian từ lúc batch được tạo đến lúc kết quả được chấp nhận có thể gồm:

1. **Queue wait:** thời gian chờ scheduler hoặc capacity.
2. **Provisioning:** tạo VM/container/function, attach network và cấp storage.
3. **Startup:** tải image, bootstrap, nạp model hoặc warm cache.
4. **Execution:** thời gian xử lý dữ liệu.
5. **Commit/output:** ghi kết quả, publish event, tạo manifest và kiểm tra checksum.
6. **Validation:** kiểm tra chất lượng và tính đầy đủ.
7. **Buffer:** dự phòng cho straggler, retry, interruption và biến động tải.

Do đó:

\[
T_{\text{total}} =
T_{\text{queue}} + T_{\text{provision}} + T_{\text{startup}} +
T_{\text{execution}} + T_{\text{commit}} + T_{\text{validation}}
\]

Thời gian thực thi còn lại cho compute:

\[
T_{\text{execution,budget}} =
T_{\text{deadline}} - T_{\text{other stages}} - T_{\text{buffer}}
\]

Ví dụ batch phải hoàn thành trước 06:00. Lịch chạy bắt đầu lúc 05:00, nhưng queue/provision/startup cần 4 phút, commit và validation cần 5 phút, buffer 6 phút. Thời gian execution budget chỉ còn 45 phút. Nếu lập capacity theo toàn bộ 60 phút, ước lượng sẽ quá lạc quan.

### Ngân sách cần có phạm vi rõ

Ngân sách có thể được xác định theo:

- Một lần chạy batch.
- Một ngày hoặc một tháng.
- Một pipeline hoặc một nhóm workload.
- Chi phí compute trực tiếp.
- Tổng chi phí cloud gồm compute, storage, network, logging và dịch vụ phụ thuộc.

Cần biết ngân sách là hard cap (không được vượt) hay target (có thể vượt trong tình huống đặc biệt để giữ deadline). Nếu deadline và ngân sách không thể đồng thời đáp ứng, phải nêu rõ trade-off: giảm phạm vi dữ liệu, thay đổi thuật toán, tăng deadline, dùng capacity rẻ hơn có rủi ro, hoặc xin ngân sách bổ sung.

### Bảng xác định mục tiêu

| Câu hỏi | Ví dụ | Ý nghĩa với capacity |
|---|---|---|
| Batch bắt đầu khi nào? | 01:00 mỗi ngày | Xác định cửa sổ chạy |
| Deadline là khi nào? | 03:00 | Ràng buộc tổng thời gian |
| Execution budget còn bao lâu? | 90 phút sau khi trừ startup/commit/buffer | Giới hạn thời gian compute |
| Dữ liệu có bao nhiêu? | 500 GB hoặc 20 triệu record | Xác định work volume |
| Ngân sách mỗi lần chạy? | 12 USD | Giới hạn cost/run |
| Nếu trễ thì sao? | Báo cáo chậm, không ảnh hưởng giao dịch | Xác định mức ưu tiên deadline |
| Nếu thiếu capacity? | Có thể dùng fallback on-demand | Xác định policy dự phòng |
| Có thể chạy lại? | Có, checkpoint theo partition | Cho phép spot/interruptible |

## 2. Lập workload profile trước khi chọn instance

Một workload profile mô tả công việc thực tế thay vì chỉ mô tả tên ứng dụng.

Thông tin cần thu thập:

- Tổng số record, file, object, partition hoặc task.
- Kích thước dữ liệu đầu vào và đầu ra.
- CPU time hoặc wall-clock time cho một đơn vị.
- Memory peak và working set.
- Đọc/ghi storage, IOPS, throughput và số request.
- Network bytes, packet rate và cross-zone/region transfer.
- Tỷ lệ task có thể chạy song song.
- Thời gian khởi tạo, warm-up và shutdown.
- Phân phối thời gian task, bao gồm task chậm nhất.
- Tỷ lệ lỗi, retry và interruption.
- Các bước tuần tự và dependency giữa các bước.
- Khả năng checkpoint, idempotency và khôi phục.

### Phân loại bottleneck

| Loại workload | Dấu hiệu | Capacity nên ưu tiên |
|---|---|---|
| CPU-bound | CPU gần bão hòa, tăng CPU cải thiện throughput | Nhiều vCPU, CPU clock/architecture phù hợp |
| Memory-bound | Working set lớn, paging/OOM hoặc GC nhiều | RAM lớn, memory bandwidth, heap tuning |
| I/O-bound | CPU thấp nhưng chờ disk/object storage | Storage throughput/IOPS, batch I/O, cache |
| Network-bound | CPU thấp, thời gian chờ truyền dữ liệu cao | Network bandwidth, locality, parallel transfer |
| GPU/accelerator-bound | CPU chờ accelerator, kernel utilization cao | GPU/accelerator phù hợp, memory VRAM và data pipeline |
| Coordination-bound | Nhiều worker nhưng throughput tăng ít | Giảm lock, shuffle, serialization và giao tiếp |
| Dependency-bound | Database/API giới hạn tốc độ | Pool, quota, batch query, backpressure và capacity dependency |

Không chọn máy nhiều CPU cho một workload đang bị giới hạn bởi database connection hoặc network. Tăng compute trong trường hợp đó có thể làm chi phí tăng mà throughput không cải thiện.

### CPU time và wall-clock time

CPU time là tổng thời gian CPU thực sự thực thi; wall-clock time là thời gian người dùng chờ. Một task chạy 10 phút với 4 core bận liên tục có thể tiêu thụ xấp xỉ 40 core-minutes, nhưng nếu chỉ chờ network phần lớn thời gian thì CPU time thấp hơn nhiều.

Khi benchmark, cần ghi cả:

- Wall-clock duration.
- CPU utilization và CPU time.
- Memory peak/working set.
- I/O wait và network wait.
- Throughput (record/second, GB/minute, task/hour).
- Error/retry rate.

## 3. Ước lượng tổng compute demand

Có thể bắt đầu bằng phép đo trên một cấu hình chuẩn rồi ngoại suy có kiểm soát.

### Phương pháp theo CPU work

Giả sử mỗi record tiêu thụ trung bình \(s\) CPU-seconds và có \(N\) record:

\[
W_{\text{CPU}} = N \times s
\]

Nếu muốn đổi sang CPU core-hours:

\[
W_{\text{CPU,core-hours}} =
\frac{N \times s}{3600}
\]

Ví dụ 12 triệu record, mỗi record trung bình 0,08 CPU-second:

\[
W_{\text{CPU}} =
12{,}000{,}000 \times 0.08
= 960{,}000\ \text{CPU-seconds}
\]

Tương đương khoảng 266,7 core-hours. Đây là tổng công CPU lý tưởng theo phép đo, chưa tính overhead, skew, retry và hiệu suất song song.

### Phương pháp theo throughput đo được

Nếu một worker có cấu hình cụ thể xử lý được \(r\) record/second trong điều kiện tải đại diện, thời gian xử lý lý tưởng của \(N\) record với \(P\) worker tương đương:

\[
T_{\text{ideal}} = \frac{N}{P \times r}
\]

Trong thực tế, throughput có thể không tăng tuyến tính do coordination, I/O, lock, network, cache contention và task skew. Dùng parallel efficiency \(\eta\) để mô hình hóa:

\[
T_{\text{execution}} \approx
\frac{N}{P \times r \times \eta}
\]

Với \(\eta\) nằm trong khoảng 0 đến 1. Đây là mô hình ước lượng; cần đo \(\eta\) ở các mức parallelism khác nhau.

### Ước lượng vCPU cần thiết

Nếu tổng CPU demand là \(W_{\text{CPU}}\) core-hours, execution window là \(D\) giờ, mục tiêu utilization là \(U\), và parallel efficiency là \(\eta\):

\[
V_{\text{required}} \approx
\frac{W_{\text{CPU}}}{D \times U \times \eta}
\]

Ví dụ tổng công việc là 2 core-hours, execution window 15 phút (0,25 giờ), target utilization 70% và parallel efficiency 80%:

\[
V_{\text{required}} =
\frac{2}{0.25 \times 0.70 \times 0.80}
\approx 14.29\ \text{vCPU}
\]

Có thể bắt đầu thử nghiệm với 16 vCPU tổng. Nếu dùng bốn worker 4 vCPU, tổng capacity danh nghĩa là 16 vCPU. Sau đó benchmark để xác nhận throughput, memory và dependency có đáp ứng hay không.

Công thức này phù hợp với workload CPU-bound. Với workload I/O-bound, GPU-bound hoặc dependency-bound, cần mô hình riêng theo bottleneck và benchmark end-to-end.

### Không ngoại suy tuyến tính quá xa

Một worker tăng gấp đôi CPU không nhất thiết xử lý gấp đôi nhanh. Một số nguyên nhân:

- Thuật toán tuần tự không song song được.
- Memory bandwidth hoặc cache trở thành bottleneck.
- Storage/network không tăng tương ứng.
- Database/API giới hạn request.
- Coordination và shuffle tăng theo số worker.
- Task có kích thước không đồng đều.
- Instance lớn có thể có hiệu năng mỗi vCPU khác instance nhỏ.

Luôn benchmark trên vài điểm capacity và vẽ đường throughput/cost để thấy vùng lợi ích giảm dần.

## 4. Phân rã và song song hóa batch

Tăng worker chỉ có ích khi công việc có thể chia và phân phối. Trước khi tăng capacity, hãy tìm cách giảm phần tuần tự.

### Chia partition

Chia input thành partition độc lập theo key, range, object hoặc shard. Mỗi task có ID ổn định, input version và output riêng.

Ví dụ 20 triệu record có thể chia thành 200 partition, mỗi partition 100.000 record. Scheduler phân phối partition cho worker; worker hoàn tất thì nhận partition tiếp theo.

Cần tránh partition quá lớn gây thời gian chạy dài và tốn nhiều công việc khi retry; partition quá nhỏ tạo overhead scheduling, metadata và kết nối.

### Fan-out/fan-in

- Fan-out: tạo nhiều task độc lập từ một batch.
- Fan-in: tổng hợp kết quả sau khi các task hoàn tất.

Cần có manifest theo dõi task trạng thái PENDING/RUNNING/COMPLETED/FAILED, số attempt, output reference và checksum. Fan-in chỉ nên đọc output đã commit hợp lệ.

### Task skew và straggler

Nếu 90 partition hoàn tất trong 5 phút nhưng 10 partition cần 30 phút, batch vẫn phải chờ các task chậm. Tăng số worker không giải quyết triệt để nếu một partition quá lớn hoặc dữ liệu lệch.

Biện pháp:

- Chia partition theo khối lượng ước lượng thay vì chỉ số lượng record.
- Đo duration theo partition và key.
- Dùng dynamic work stealing.
- Có speculative execution cho task chậm khi side effect idempotent.
- Tránh hai worker cùng ghi output cuối nếu không có commit/fencing.

### Định luật Amdahl

Nếu tỷ lệ phần việc tuần tự là \(f\), tốc độ tăng tối đa với \(P\) worker theo mô hình lý tưởng:

\[
Speedup(P) = \frac{1}{f + \frac{1-f}{P}}
\]

Nếu 20% pipeline là tuần tự (\(f=0.2\)), tăng vô hạn worker cũng chỉ đạt speedup tối đa 5 lần. Vì vậy, tối ưu phần tuần tự như load input, merge, validation và commit có thể đem lại lợi ích lớn hơn thêm VM.

## 5. Chọn CPU và hình dạng instance

CPU phù hợp phụ thuộc vào tính chất tính toán, không chỉ số vCPU.

### General-purpose

Phù hợp workload cân bằng CPU/memory, ETL vừa phải, orchestration, API phụ trợ và job hỗn hợp.

### Compute-optimized

Phù hợp CPU-bound như nén, mã hóa, tính toán số, simulation và transform dữ liệu. Cần so sánh hiệu năng mỗi vCPU, clock, architecture và giá mỗi giờ.

### Memory-optimized

Phù hợp join lớn, in-memory aggregation, cache, graph processing và workload có working set lớn. Cần tính cả memory bandwidth và giới hạn heap/runtime.

### GPU/accelerator

Phù hợp ML training/inference batch, image/video processing hoặc tính toán có kernel hỗ trợ accelerator. GPU không tự động tăng tốc mọi workload. Cần tính thời gian nạp dữ liệu, CPU preprocessing, VRAM, batch size và utilization thực tế.

### ARM và x86

So sánh theo hiệu năng ứng dụng và tương thích binary/dependency, không chỉ theo giá. Kiểm tra container image multi-arch, thư viện native, compiler flags, runtime và license.

### Một worker lớn hay nhiều worker nhỏ?

| Lựa chọn | Ưu điểm | Hạn chế |
|---|---|---|
| Ít worker lớn | Ít task coordination, có thể dùng RAM lớn và xử lý partition lớn | Failure domain lớn hơn, scale granularity thấp, có thể khó tận dụng hết |
| Nhiều worker nhỏ | Dễ scale ngang, task failure giới hạn, có thể dùng pool capacity đa dạng | Nhiều connection, network traffic, scheduler overhead và coordination |
| Worker hỗn hợp | Dùng shape khác nhau cho stage khác nhau | Pipeline phức tạp hơn, cần routing và capacity policy |

Chọn theo kích thước partition, memory footprint, khả năng song song, quota và giá thực tế. Không có một cấu hình tối ưu cho mọi stage.

## 6. Memory, storage và network cũng là capacity

Batch có thể thất bại dù CPU đủ nếu memory hoặc I/O không đáp ứng.

### Memory

Ước lượng memory theo:

- Working set của một task.
- Số task đồng thời trên một worker.
- Runtime/heap overhead.
- Buffer, shuffle, cache và serialization.
- Native memory ngoài heap.
- OS, agent và container overhead.
- Peak memory thay vì chỉ average.

Nếu một task cần 3 GiB working set và worker chạy 4 task song song, cần tối thiểu khoảng 12 GiB cho phần task, cộng overhead và headroom. Cần benchmark peak memory và kiểm tra OOM.

### Storage

Phân biệt:

- Ephemeral/local disk cho scratch, shuffle và temporary output.
- Persistent block storage cho dữ liệu cần tồn tại theo volume lifecycle.
- Object storage cho input/output bền vững và chia sẻ giữa worker.
- Shared file storage cho workload cần filesystem semantics.

Đánh giá throughput, IOPS, queue depth, latency, file count và metadata operation. Nhiều file nhỏ có thể bị giới hạn bởi request/metadata rate dù tổng dung lượng thấp.

### Network

Đo bytes/second, packet rate, latency và cross-zone/cross-region transfer. Nếu mỗi worker tải cùng một dataset lớn, scale-out có thể làm tăng egress và saturate source storage.

Tối ưu bằng data locality, partitioning, compression, caching, batch transfer và tránh shuffle không cần thiết. Tính phí data transfer vào cost model.

## 7. Chọn mô hình compute: VM, container hay serverless

| Mô hình | Phù hợp khi | Cần lưu ý |
|---|---|---|
| VM/instance group | Job dài, cần OS/runtime đặc thù, disk hoặc GPU; cần kiểm soát instance family | Boot time, patching, capacity reservation, autoscaling và shutdown |
| Container trên orchestrator | Task đóng gói được, cần scheduler, queue worker và node pool đa dạng | Pod startup, image pull, requests/limits, node capacity và orchestration overhead |
| Serverless function | Task ngắn, event-driven, có giới hạn runtime/concurrency rõ | Invocation duration, memory/CPU coupling, cold start, payload và service quotas |
| Managed batch service | Cần queue, job definition, retry, scheduling và capacity management tích hợp | Semantics của scheduler, quota, pricing, retry và khả năng custom |
| Managed data processing | ETL/SQL/stream/batch có engine chuyên dụng | Chi phí theo worker/slot/data, startup và minimum billing unit |

Một batch có thể kết hợp nhiều mô hình: scheduler managed tạo job, container xử lý partition, function xử lý sự kiện ngắn và database/object storage giữ trạng thái.

### Thời gian khởi động và thời lượng job

Với job chỉ chạy 20 giây, 90 giây khởi động VM có thể chiếm phần lớn deadline. Với job chạy 6 giờ, startup 90 giây có thể không đáng kể. Vì vậy, compute shape và platform cần được đánh giá theo toàn bộ lifecycle chứ không chỉ giá CPU/giờ.

### Minimum billing và scale-to-zero

Serverless hoặc managed service có thể tính phí theo request, thời gian, memory/CPU hoặc đơn vị xử lý. VM thường có billing theo thời gian cấp phát với quy tắc làm tròn/commitment của provider. Kiểm tra minimum billing, startup, idle và storage charges trước khi so sánh.

## 8. Chọn capacity ổn định hay capacity có thể thu hồi

Các lựa chọn phổ biến:

- **On-demand:** mua capacity theo nhu cầu, linh hoạt nhưng giá đơn vị thường cao hơn các hình thức commitment.
- **Reserved/committed use/savings plan:** đổi cam kết sử dụng hoặc chi tiêu lấy mức giá ưu đãi; có thể kém linh hoạt nếu workload thay đổi.
- **Spot/preemptible/interruptible:** tận dụng capacity dư thừa với giá thấp hơn, nhưng có thể bị thu hồi.
- **Capacity reservation/dedicated capacity:** giữ hoặc bảo đảm khả năng cấp phát theo sản phẩm và điều kiện provider; có thể phát sinh chi phí.
- **Hybrid pool:** kết hợp capacity ổn định làm baseline và capacity rẻ/interruptible cho phần co giãn.

### Khi nào dùng spot cho batch?

Phù hợp khi:

- Job có thể chia thành partition độc lập.
- Worker có checkpoint và output commit an toàn.
- Retry/idempotency được thiết kế.
- Có capacity thay thế hoặc deadline đủ margin.
- Không giữ state duy nhất trên instance.
- Có thể chuyển task sang on-demand khi cần.

Cần tránh đặt toàn bộ batch deadline-critical trên spot nếu không có fallback. Interruption rate và khả năng có capacity thay thế khác nhau theo region, instance family và thời điểm; không giả định spot luôn có sẵn.

### Mô hình capacity mix

Một cách tiếp cận là:

- Baseline on-demand/committed để bảo đảm mức throughput tối thiểu.
- Spot pool cho phần workload có thể retry.
- On-demand burst hoặc reservation để cứu deadline khi spot thiếu.
- Queue giữ task chưa xử lý và phân phối lại khi worker bị thu hồi.

Tỷ lệ giữa các pool nên dựa trên lịch sử interruption, giá, thời gian khởi tạo, quota và deadline miss rate.

## 9. Cost model cho một lần chạy batch

Chi phí không chỉ là số vCPU nhân giá theo giờ. Cần tính toàn bộ resource và thời gian bị tính phí.

\[
C_{\text{total}} =
C_{\text{compute}} + C_{\text{storage}} + C_{\text{network}} +
C_{\text{managed services}} + C_{\text{observability}} +
C_{\text{retry/waste}}
\]

### Compute cost

Với worker type \(i\):

\[
C_{\text{compute}} = \sum_i N_i \times T_i \times P_i
\]

Trong đó:

- \(N_i\): số worker.
- \(T_i\): thời gian tính phí mỗi worker (giờ).
- \(P_i\): giá mỗi worker mỗi giờ.

Nếu worker được tính phí theo vCPU/memory/request, thay bằng đơn vị tính tương ứng. Tính cả thời gian boot, idle, drain và thời gian bị giữ do billing granularity.

### Storage và network cost

Có thể gồm:

- GB-month của volume/object storage.
- IOPS/throughput provisioned.
- Read/write request count.
- Snapshot và backup retention.
- Data transfer giữa zone/region.
- Internet egress hoặc NAT processing.
- Data processing charge của managed service.

### Chi phí retry và interruption

Nếu job chạy lại 10% công việc do interruption, tổng compute không còn bằng thời gian thành công lý tưởng. Cần đo wasted compute và chi phí checkpoint/recovery.

Có thể mô hình hóa:

\[
C_{\text{effective}} =
C_{\text{successful work}} + C_{\text{retries}} + C_{\text{idle}}
\]

Đừng chỉ so sánh giá spot với on-demand. So sánh cost per successful batch hoặc cost per million records đã được xác nhận.

### Chi phí cơ hội của deadline miss

Batch trễ có thể gây hậu quả nghiệp vụ như báo cáo không kịp, dữ liệu downstream chậm hoặc vi phạm SLA. Nếu có thể ước lượng, đưa chi phí đó vào quyết định capacity. Một cấu hình compute đắt hơn có thể có tổng chi phí kỳ vọng thấp hơn nếu giảm đáng kể nguy cơ trễ hạn.

## 10. Tối ưu theo ràng buộc deadline và ngân sách

Bài toán có thể mô tả:

- Minimize tổng chi phí.
- Subject to thời gian hoàn thành không vượt deadline.
- Subject to memory/storage/network capacity không bị vượt.
- Subject to availability, quota, security và data locality.
- Subject to xác suất hoàn thành đúng hạn đạt ngưỡng chấp nhận.

Không nên chỉ chọn cấu hình có chi phí thấp nhất theo benchmark trung bình. Cần xét biến động thời gian, task skew, capacity availability, interruption và retry.

### Cost-performance frontier

Với mỗi cấu hình, đo:

- Tổng chi phí.
- Thời gian hoàn thành p50/p90/p95.
- Throughput.
- Tỷ lệ thất bại/retry.
- Peak resource utilization.
- Cost per successful unit.

Cấu hình A có thể rẻ nhất nhưng không đạt deadline. Cấu hình B có thể nhanh hơn nhưng chi phí vượt ngân sách. Cấu hình C nằm trong cả hai ràng buộc và có buffer đủ lớn.

### SLO cho batch

Đặt mục tiêu như:

- 99% batch hoàn tất trước 05:45.
- Chi phí mỗi lần chạy không vượt 15 USD ở điều kiện thông thường.
- Retry rate dưới 3%.
- Không mất partition đã commit.
- Có fallback capacity trong một khoảng thời gian xác định.

SLO giúp quyết định capacity theo xác suất, không chỉ theo một lần benchmark.

## 11. Ví dụ tính toán: batch phải hoàn tất trong 30 phút

Một batch xử lý 12.000 record. Benchmark trên một worker 4 vCPU cho thấy mỗi record cần trung bình 0,6 CPU-second. Tổng CPU demand:

\[
12{,}000 \times 0.6 = 7{,}200\ \text{CPU-seconds}
= 2\ \text{core-hours}
\]

Deadline tổng là 30 phút. Trừ 4 phút provisioning/startup, 3 phút output commit/validation và 3 phút buffer, execution budget còn 20 phút. Giả sử target utilization 70% và parallel efficiency 80%.

\[
V_{\text{required}} =
\frac{2}{(20/60) \times 0.70 \times 0.80}
\approx 10.72\ \text{vCPU}
\]

Về mặt CPU, 12 vCPU là ngưỡng ước lượng ban đầu; 16 vCPU tạo thêm headroom để benchmark và chịu skew. Tuy nhiên, cần kiểm tra memory, storage và dependency trước khi chốt.

Giả sử giá minh họa:

| Cấu hình | Capacity danh nghĩa | Giá giả định | Execution ước lượng | Nhận xét |
|---|---:|---:|---:|---|
| 3 worker × 4 vCPU | 12 vCPU | 0,24 USD/worker-hour | Khoảng 17,9 phút theo mô hình CPU | Sát execution budget 20 phút, ít margin |
| 4 worker × 4 vCPU | 16 vCPU | 0,24 USD/worker-hour | Khoảng 13,4 phút | Có margin hơn, compute cost xấp xỉ 0,21 USD cho 13,4 phút |
| 2 worker × 8 vCPU | 16 vCPU | 0,43 USD/worker-hour | Cần benchmark shape lớn | Có thể giảm coordination nhưng hiệu năng/giá phụ thuộc CPU và memory |

Giá chỉ là giả định để minh họa cách tính; không đại diện bảng giá của nhà cung cấp. Execution estimate cũng dựa trên giả định parallel efficiency giữ ở 80%. Nếu database chỉ cho phép 5 query đồng thời, 16 vCPU không bảo đảm throughput tăng tương ứng.

Quyết định nên dựa trên benchmark cả pipeline. Nếu 4 × 4 vCPU đáp ứng p95 deadline với chi phí thấp hơn ngân sách, chọn cấu hình đó. Nếu p95 vẫn trễ, kiểm tra bottleneck trước khi tiếp tục tăng worker.

## 12. Ví dụ ngân sách cố định: chọn rẻ nhất vẫn đạt deadline

Một pipeline cần xử lý 2 TB dữ liệu trước 04:00. Ngân sách compute và storage tối đa 20 USD mỗi lần chạy. Đã benchmark ba cấu hình:

| Cấu hình | Thời gian p95 | Compute cost | Storage/network | Tổng cost | Đạt deadline? |
|---|---:|---:|---:|---:|---|
| 4 worker on-demand | 95 phút | 12 USD | 3 USD | 15 USD | Không |
| 8 worker mixed on-demand/spot | 55 phút | 13 USD | 3,5 USD | 16,5 USD | Có |
| 12 worker on-demand | 38 phút | 22 USD | 4 USD | 26 USD | Có, vượt ngân sách |

Trong ví dụ, cấu hình 8 worker là lựa chọn phù hợp vì đáp ứng cả deadline và ngân sách. Cấu hình 4 worker rẻ hơn nhưng không đạt deadline; cấu hình 12 worker nhanh hơn nhưng vượt ngân sách.

Cần kiểm tra thêm tỷ lệ spot interruption. Nếu p95 55 phút đã tính retry và interruption lịch sử, kết quả đáng tin hơn. Nếu chưa, cần chạy thử fault injection hoặc dành fallback on-demand.

## 13. Deadline có xác suất: dùng p90/p95 thay vì average

Batch có task duration biến động. Average có thể che khuất một nhóm task chậm, dẫn đến deadline miss.

Theo dõi:

- p50: trải nghiệm điển hình.
- p90/p95: phần lớn lần chạy.
- p99: tail latency hoặc batch hiếm khi kéo dài.
- Max: worst observed, không phải worst possible.

Nếu deadline cứng, capacity nên được chọn dựa trên phân phối nhiều lần chạy và buffer phù hợp. Một batch có average 40 phút nhưng p95 75 phút sẽ không đáp ứng deadline 60 phút ổn định.

### Tail và straggler

Với nhiều partition, thời gian batch hoàn tất phụ thuộc task cuối cùng. Nếu 1.000 partition chạy song song, chỉ vài partition cực chậm cũng có thể kéo dài toàn bộ batch.

Cách xử lý:

- Theo dõi duration theo partition/key.
- Cân bằng kích thước partition.
- Cho phép worker lấy task tiếp theo khi hoàn tất.
- Dùng speculative copy cho task straggler nếu output commit idempotent.
- Giảm data skew ở join/group-by.
- Tách stage dài và stage ngắn để scale riêng.

## 14. Autoscaling theo queue depth và deadline

Autoscaling nên phản ứng theo cả khối lượng công việc còn lại và thời gian còn lại đến deadline.

Metric có thể dùng:

- Queue depth.
- Oldest message age.
- Estimated remaining work.
- Average/p95 task duration.
- Worker throughput.
- Deadline slack (thời gian còn lại sau khi trừ estimated execution).
- Worker startup time và capacity availability.
- Error/retry/interruption rate.

### Deadline slack

\[
Slack = T_{\text{deadline remaining}} -
T_{\text{estimated work remaining}}
\]

Nếu slack giảm về gần 0, hệ thống cần tăng capacity hoặc kích hoạt fallback. Nếu slack lớn, có thể giảm worker để tiết kiệm chi phí, miễn là không ảnh hưởng deadline.

### Ước lượng worker theo queue

Nếu còn \(Q\) task, mỗi worker xử lý trung bình \(r\) task/second, còn \(D\) giây và target utilization \(U\):

\[
N_{\text{workers}} \geq
\left\lceil \frac{Q}{r \times D \times U} \right\rceil
\]

Công thức dùng throughput đo được trong cùng loại task. Nếu có nhiều loại task, hãy tính theo từng queue/partition hoặc tổng CPU demand thay vì gộp một rate không đại diện.

### Scale-out và scale-in

Scale-out cần tính thời gian provision và startup. Tạo worker sau khi deadline slack đã cạn có thể không còn giúp kịp hạn.

Scale-in nên:

- Ngừng nhận task mới trên worker cần loại.
- Hoàn tất task ngắn hoặc checkpoint task dài.
- Release lease/visibility timeout đúng cách.
- Flush output đã commit.
- Drain và terminate.
- Không xóa worker đang giữ trạng thái duy nhất.

Dùng cooldown/hysteresis để tránh scale lên xuống liên tục khi queue depth dao động.

## 15. Checkpoint, retry và compute có thể bị thu hồi

Nếu batch chạy trên spot/preemptible capacity, worker có thể bị thu hồi. Khả năng chạy lại an toàn giúp giảm chi phí mà không làm mất dữ liệu.

Thiết kế nên có:

- Task ID ổn định.
- Input version/checksum.
- Idempotency key cho side effect.
- Checkpoint bền vững ngoài instance.
- Output key deterministic hoặc manifest commit.
- Lease/visibility timeout và fencing nếu có worker overlap.
- Retry với exponential backoff và jitter.
- Dead-letter queue cho task lỗi vĩnh viễn.
- Interruption handler để ngừng nhận task mới và checkpoint trong thời gian cho phép.

Không dựa hoàn toàn vào shutdown notice. Instance có thể mất đột ngột; checkpoint định kỳ và idempotency mới là lớp bảo vệ chính.

### Chọn checkpoint interval

Checkpoint quá thưa làm tăng lượng công việc phải chạy lại; checkpoint quá dày tạo overhead I/O và storage. Đo:

- Thời gian tạo checkpoint.
- Thời gian restore.
- Công việc kỳ vọng bị mất giữa hai checkpoint.
- Chi phí storage/transaction.
- Tác động lên throughput của batch.

Với batch chia partition, commit mỗi partition có thể đơn giản hơn checkpoint liên tục trong một task. Với ML training hoặc simulation dài, checkpoint theo thời gian hoặc số bước có thể phù hợp hơn.

## 16. Giới hạn dependency và backpressure

Compute capacity không thể vượt capacity của dependency mà không gây nghẽn.

Ví dụ 20 worker cùng đọc một database, mỗi worker mở 30 connection có thể tạo tối đa 600 connection. Nếu database chỉ chịu được 150 connection cho batch, tăng worker sẽ làm timeout, retry và giảm throughput.

Cần tính capacity end-to-end:

- Database connections và query throughput.
- Object storage request rate và bandwidth.
- Message broker partitions/consumer count.
- API rate limit và quota.
- NAT gateway/egress port.
- Shared cache throughput.
- DNS resolver capacity.
- Network bandwidth giữa zone/region.

Biện pháp:

- Giới hạn concurrency ở worker và function.
- Connection pool có trần theo toàn fleet.
- Batch read/write thay vì request nhỏ liên tục.
- Backpressure theo dependency saturation.
- Queue buffer để tách tốc độ producer/consumer.
- Retry có budget, không retry đồng loạt.
- Tách stage để dependency yếu không chặn toàn bộ compute.

### Capacity của pipeline là bottleneck nhỏ nhất

Một pipeline có thể có 100 vCPU nhưng database chỉ xử lý 5.000 record/second. Khi đó throughput thực tế không vượt giới hạn database nếu không thay đổi query, partitioning hoặc data access pattern.

Theo dõi throughput ở từng stage thay vì chỉ nhìn CPU utilization toàn cluster.

## 17. Benchmark và load test để chốt cấu hình

Ước lượng bằng công thức chỉ tạo điểm khởi đầu. Benchmark thực tế xác nhận hiệu năng và cost.

### Chuẩn bị benchmark

- Dùng dữ liệu đại diện cả kích thước và phân phối.
- Bao gồm cold start, image pull và data warm-up nếu production có.
- Dùng cùng phiên bản code, runtime và dependency.
- Ghi lại instance type, vCPU, memory, disk và network.
- Chạy nhiều lần ở các mức concurrency khác nhau.
- Đo p50/p95 duration, throughput, error, retry và resource usage.
- Tính cost per successful batch.

### Ma trận thử nghiệm

| Thử nghiệm | Thay đổi | Điều cần biết |
|---|---|---|
| Baseline | 1 worker/shape chuẩn | Throughput và resource profile ban đầu |
| Scale CPU | Giữ số worker, đổi vCPU/shape | Hiệu năng theo mỗi worker |
| Scale horizontal | Tăng số worker | Parallel efficiency và coordination overhead |
| Scale memory | Tăng RAM/heap | OOM/GC và throughput |
| Storage | Đổi IOPS/throughput/cache | I/O bottleneck |
| Network | Thay locality/transfer concurrency | Network saturation và egress cost |
| Spot mix | Thêm interruptible capacity | Interruption, retry và cost per success |
| Deadline test | Chạy toàn batch theo giờ cao điểm | p95 completion và buffer |
| Failure test | Dừng worker giữa task | Checkpoint, retry và data integrity |

### Quy trình benchmark có kiểm soát

1. Chọn baseline nhỏ nhưng đủ chạy toàn pipeline.
2. Chạy với dữ liệu đại diện và ghi metric.
3. Tăng một biến tại một thời điểm.
4. Tìm điểm throughput bắt đầu tăng ít hơn chi phí.
5. Lặp lại để có phân phối p50/p95.
6. Kiểm thử dependency và interruption.
7. So sánh cost/deadline frontier.
8. Chốt cấu hình với buffer và quota dự phòng.

Không so sánh hai cấu hình bằng các lần chạy có input, cache state hoặc dependency load khác nhau mà không ghi nhận khác biệt.

## 18. Lập ngân sách capacity theo stage

Các stage khác nhau có thể cần compute shape khác nhau. Không nhất thiết dùng một pool lớn cho toàn pipeline.

Ví dụ ETL:

| Stage | Đặc điểm | Capacity phù hợp |
|---|---|---|
| Extract | Nhiều request I/O, CPU thấp | Worker vừa phải, network tốt, concurrency có giới hạn |
| Transform | CPU/memory cao | Compute-optimized hoặc memory-optimized theo profile |
| Shuffle/join | Network và memory cao | Network throughput, memory và partition strategy |
| Load | Database-bound | Worker ít hơn, batch write, connection pool giới hạn |
| Validate | CPU thấp, logic tuần tự | Worker nhỏ hoặc serverless task |

Scale từng stage theo queue và bottleneck riêng giúp tránh cấp dư CPU ở stage đang chờ database.

### Buffer capacity

Giữ headroom cho:

- Worker fail hoặc interruption.
- Partition straggler.
- Provisioning delay.
- Data volume tăng.
- Capacity quota/spot availability thay đổi.
- Dependency latency tăng.

Headroom không phải lúc nào cũng là một tỷ lệ cố định. Xác định từ biến động lịch sử và hậu quả của deadline miss.

## 19. Chiến lược tối ưu chi phí

### Tối ưu thuật toán trước khi mua thêm compute

Giảm số phép tính, tránh đọc dữ liệu lặp, pushdown filter/aggregation vào nơi phù hợp, giảm serialization và shuffle. Một thay đổi thuật toán giảm 30% CPU demand có thể rẻ hơn tăng worker.

### Tối ưu data locality

Đặt compute gần dữ liệu trong cùng region/zone khi phù hợp. Tránh cross-region transfer không cần thiết. Nếu workload cần đọc cùng dataset nhiều lần, cân nhắc cache hoặc staging vào storage phù hợp.

### Tối ưu shape và utilization

- Benchmark giá/throughput thay vì chỉ giá/giờ.
- Tránh worker quá lớn nhưng sử dụng thấp.
- Tránh quá nhiều worker nhỏ tạo coordination overhead.
- Dùng autoscaling theo remaining work.
- Tắt capacity khi queue rỗng.
- Dùng batch size phù hợp để giảm scheduling overhead.

### Tối ưu commitment

Dùng committed capacity cho baseline ổn định, phần burst dùng on-demand hoặc spot. Không cam kết quá mức nếu batch volume thay đổi theo mùa hoặc theo event.

### Theo dõi cost per successful unit

Metric hữu ích:

- USD/batch.
- USD/million records.
- USD/GB transformed.
- USD/rendered minute.
- USD/training step hoặc epoch.
- Cost of retry/interruption.
- Cost of idle capacity.

Cost per successful unit cho phép so sánh cấu hình khác nhau ngay cả khi một cấu hình hoàn tất nhanh hơn nhưng dùng nhiều tài nguyên.

## 20. Các tình huống chọn capacity

### Tình huống A: báo cáo đêm có deadline cứng

Batch tổng hợp dữ liệu trước giờ mở cửa. Input ổn định, CPU-bound, có thể chia partition. Deadline quan trọng, nhưng dữ liệu không cần hoàn thành trong vài phút.

Chiến lược:

- Benchmark throughput theo vCPU.
- Chọn baseline on-demand đủ đáp ứng p95 deadline.
- Có thể dùng spot cho partition có thể retry.
- Giữ fallback on-demand khi deadline slack thấp.
- Checkpoint theo partition và validate manifest trước publish.

### Tình huống B: ETL lớn nhưng ngân sách chặt

Input nhiều TB, deadline tương đối rộng, workload có thể retry.

Chiến lược:

- Tối ưu filter/pushdown và data locality.
- Chọn storage/network throughput đủ lớn.
- Dùng spot pool rộng theo nhiều instance family/zone.
- Giới hạn concurrency theo storage và database.
- Checkpoint theo partition, DLQ task lỗi và scale theo queue depth.
- Tính cost per GB processed, không chỉ compute cost.

### Tình huống C: render media với deadline gần

Job render có task độc lập, nhưng một số frame rất nặng và output cần commit.

Chiến lược:

- Benchmark theo loại frame/scene.
- Dùng GPU nếu pipeline thực sự được tăng tốc.
- Chia task theo segment cân bằng.
- Giữ capacity ổn định cho phần không thể retry nhanh.
- Dùng spot cho segment có checkpoint hoặc output riêng.
- Theo dõi straggler và speculative execution có kiểm soát.

### Tình huống D: batch chạy theo event, volume khó dự đoán

Số lượng job thay đổi lớn theo ngày.

Chiến lược:

- Queue làm buffer.
- Autoscale theo oldest message age và estimated remaining work.
- Giữ baseline nhỏ nếu cần latency khởi động thấp.
- Scale burst bằng on-demand/spot theo policy.
- Rate-limit dependency.
- Đặt ngân sách/maximum concurrency và cảnh báo khi slack thấp.

### Tình huống E: ML training dài và tốn GPU

Training nhiều giờ, GPU đắt, interruption gây mất tiến độ nếu không checkpoint.

Chiến lược:

- Benchmark GPU utilization và data loader throughput.
- Tối ưu batch size, mixed precision và input pipeline khi phù hợp.
- Lưu model, optimizer, scheduler và RNG state.
- Checkpoint theo thời gian hoặc step.
- Dùng capacity ổn định cho deadline quan trọng; spot cho run có thể tiếp tục.
- Tính cả chi phí GPU idle khi CPU data pipeline không cấp dữ liệu đủ nhanh.

## 21. Quy trình ra quyết định capacity

Có thể dùng quy trình tuần tự sau:

1. **Chốt deadline:** xác định thời điểm bắt đầu, deadline và thời gian dành cho queue/provision/commit/buffer.
2. **Chốt ngân sách:** hard cap, target cost và chi phí phụ trợ.
3. **Profile workload:** input volume, CPU, memory, I/O, network, dependency và task distribution.
4. **Xác định bottleneck:** CPU, memory, storage, network, GPU hay dependency.
5. **Chia workload:** partition, stage, checkpoint và idempotency.
6. **Tạo baseline:** benchmark trên một cấu hình đơn giản.
7. **Ước lượng capacity:** tính worker/vCPU và kiểm tra quota.
8. **Benchmark nhiều shape:** đo throughput, p95 và cost.
9. **Chọn capacity mix:** baseline ổn định, burst, spot/fallback.
10. **Thiết lập autoscaling:** queue/deadline-aware, concurrency cap và cooldown.
11. **Kiểm thử lỗi:** worker loss, interruption, dependency throttling và retry.
12. **Theo dõi production:** deadline miss, cost per success, retry, saturation và điều chỉnh.

### Bảng quyết định

| Nếu ưu tiên | Hướng chọn |
|---|---|
| Deadline rất cứng | Capacity ổn định, headroom, quota/reservation và fallback |
| Ngân sách cứng, deadline rộng | Spot/interruptible, queue, checkpoint và autoscaling |
| Workload biến động | Baseline nhỏ + burst capacity |
| CPU-bound | Compute-optimized sau benchmark |
| Memory-bound | Memory-optimized và kiểm soát working set |
| I/O-bound | Storage throughput, cache và data locality |
| Dependency-bound | Giới hạn worker/concurrency, tối ưu dependency |
| Job dài, khó chạy lại | Capacity ổn định và checkpoint thường xuyên |
| Job chia nhỏ, idempotent | Pool spot rộng và retry có kiểm soát |

## 22. Vận hành, observability và cảnh báo

Capacity plan phải được so sánh với kết quả production.

### Metric cần theo dõi

**Deadline và throughput**

- Batch start/end time.
- End-to-end duration và execution duration.
- Queue wait và provisioning time.
- Records/GB/tasks processed per second.
- Remaining work và deadline slack.
- p50/p90/p95/p99 completion duration.
- Deadline success rate.

**Compute**

- vCPU utilization, CPU throttling và run queue.
- Memory peak, OOM, page fault và GC.
- GPU utilization, VRAM và accelerator idle time.
- Disk throughput, IOPS, latency và disk pressure.
- Network throughput, packet drop và retransmission.

**Reliability**

- Worker failure/interruption.
- Retry count, task attempt và duplicate suppression.
- Checkpoint duration/restore time.
- DLQ count và oldest task age.
- Dependency timeout/throttle.
- Partition straggler và speculative task count.

**Cost**

- Compute cost per batch.
- Storage/network/managed-service cost.
- Idle worker time.
- Retry/wasted compute.
- Cost per successful record/GB/task.
- Forecast cost so với budget.

### Cảnh báo hữu ích

- Deadline slack xuống dưới ngưỡng an toàn.
- Estimated completion vượt deadline.
- Queue age tăng liên tục.
- Worker startup hoặc provisioning chậm.
- Retry/interruption rate tăng.
- Database connections gần quota.
- Storage/network saturation.
- Cost forecast vượt ngân sách.
- Spot capacity giảm và fallback chưa đủ.

Cảnh báo nên gắn với hành động: tăng worker, chuyển fallback, giảm concurrency, pause producer hoặc thông báo owner. Tránh cảnh báo chỉ dựa trên CPU cao nếu CPU cao là trạng thái mong muốn và batch vẫn tiến triển đúng hạn.

## 23. Những sai lầm thường gặp

**Chia deadline cho số worker để suy ra thời gian.** Cách này bỏ qua startup, commit, parallel efficiency, task skew và dependency. Hãy đo throughput end-to-end.

**Chỉ tính giá compute.** Storage request, network egress, NAT, logs, retry và idle capacity có thể làm tổng chi phí tăng đáng kể.

**Tăng worker khi database đã bão hòa.** Điều này tạo thêm connection và retry nhưng không tăng throughput. Giới hạn concurrency và tối ưu dependency trước.

**Dùng average để cam kết deadline.** Tail task và biến động capacity có thể làm batch trễ. Theo dõi p95/p99 và buffer.

**Dùng spot cho toàn bộ workload không checkpoint.** Interruption có thể làm mất nhiều giờ xử lý. Chỉ dùng khi job có thể retry hoặc có fallback phù hợp.

**Chọn instance theo vCPU mà bỏ qua memory/network.** Worker có thể CPU còn thấp nhưng OOM hoặc chờ I/O. Benchmark toàn bộ resource profile.

**Partition quá lớn hoặc quá nhỏ.** Partition lớn làm retry đắt; partition nhỏ tạo overhead scheduling và metadata. Chọn granularity bằng benchmark.

**Scale-out quá muộn.** Nếu provisioning mất 5 phút và deadline slack chỉ còn 2 phút, thêm worker không cứu được batch. Dự báo remaining work sớm.

**Không tính quota và capacity availability.** Autoscaler có thể yêu cầu worker nhưng cloud không cấp đủ instance/accelerator. Kiểm tra quota và fallback trước giờ chạy.

**Không tính thời gian output validation.** Compute hoàn tất nhưng dữ liệu chưa commit hoặc chưa được kiểm tra vẫn chưa phải batch thành công.

**Không đo cost per successful batch.** Một cấu hình giá rẻ nhưng retry nhiều có thể đắt hơn cấu hình ổn định.

## 24. Checklist chọn capacity cho batch

### Deadline và ngân sách

- [ ] Deadline end-to-end đã xác định rõ.
- [ ] Đã trừ queue, provisioning, startup, commit, validation và buffer.
- [ ] Ngân sách là hard cap hay target đã được xác định.
- [ ] Đã tính compute, storage, network, managed service, logs và retry.
- [ ] Có tiêu chí xử lý khi deadline và budget xung đột.

### Workload profile

- [ ] Input volume, size và phân phối dữ liệu đã được đo.
- [ ] CPU time và wall-clock time được phân biệt.
- [ ] Memory peak/working set được đo.
- [ ] Storage IOPS/throughput và network throughput được đo.
- [ ] Dependency quota và connection limit được xác định.
- [ ] Task skew và phần tuần tự được nhận diện.

### Capacity và architecture

- [ ] Đã xác định bottleneck chính.
- [ ] Đã benchmark worker shape và số worker.
- [ ] Có parallel efficiency estimate.
- [ ] Partition size và checkpoint interval phù hợp.
- [ ] VM/container/serverless/managed batch được so sánh theo lifecycle.
- [ ] Quota, accelerator và capacity reservation được xác minh.
- [ ] Có headroom hoặc fallback theo deadline.

### Cost và reliability

- [ ] Cost per successful batch/unit được tính.
- [ ] Spot/interruptible chỉ dùng cho task có thể retry.
- [ ] Idempotency, checkpoint và DLQ được kiểm thử.
- [ ] Autoscaling tính queue depth, remaining work và deadline slack.
- [ ] Retry/backoff không gây retry storm.
- [ ] Dependency có backpressure và concurrency cap.

### Vận hành

- [ ] Có dashboard deadline, throughput, resource và cost.
- [ ] Có cảnh báo deadline slack và budget forecast.
- [ ] Có test ở tải đại diện và p95/p99.
- [ ] Đã thử worker failure/interruption.
- [ ] Có runbook chuyển capacity/fallback.
- [ ] Sau mỗi lần chạy có so sánh estimate với actual và cập nhật model.

## 25. Tự kiểm tra

1. Vì sao deadline của batch cần trừ queue, provisioning, startup, commit và validation?
2. Phân biệt CPU time với wall-clock time và cho biết khi nào mỗi đại lượng hữu ích.
3. Với tổng CPU demand 12 core-hours, execution window 1 giờ, utilization mục tiêu 75% và parallel efficiency 80%, cần khoảng bao nhiêu vCPU?
4. Vì sao tăng số worker không luôn làm batch nhanh hơn theo tỷ lệ tuyến tính?
5. Amdahl's Law giúp nhận diện giới hạn nào của parallelization?
6. Khi nào nên chọn compute-optimized, memory-optimized hoặc GPU instance?
7. Vì sao batch có deadline cứng thường cần capacity ổn định hoặc fallback bên cạnh spot?
8. Cost model cần tính những khoản nào ngoài giá VM/giờ?
9. Queue depth và deadline slack có thể kết hợp để điều khiển autoscaling ra sao?
10. Vì sao p95 completion duration có thể hữu ích hơn average khi cam kết deadline?
11. Nếu throughput không tăng khi tăng worker, cần kiểm tra dependency và bottleneck nào?
12. Hãy lập capacity plan cho batch 5 triệu record phải hoàn thành trong 45 phút với ngân sách cố định, bao gồm benchmark, worker count, capacity mix, cost và fallback.

Chọn capacity cho batch là quyết định dựa trên dữ liệu đo và các ràng buộc thực tế. Khi phân rã deadline, profile workload, ước lượng compute demand, benchmark nhiều cấu hình và tính đủ chi phí, đội ngũ có thể chọn mức capacity vừa đáp ứng thời hạn vừa nằm trong ngân sách. Capacity mix, autoscaling theo remaining work, checkpoint và backpressure giúp kế hoạch tiếp tục hiệu quả khi dữ liệu, giá và khả năng cấp phát thay đổi.
# Chọn capacity cho batch theo deadline và ngân sách

## 1. Vì sao phải cân bằng deadline và ngân sách?

Batch processing xử lý một tập công việc trong một khoảng thời gian: tổng hợp dữ liệu cuối ngày, tạo báo cáo, chuyển mã video, huấn luyện mô hình, lập hóa đơn, đồng bộ dữ liệu hoặc chạy kiểm thử. Khác với API tương tác, batch thường có thể xếp hàng và chạy nền. Tuy nhiên, nó vẫn có deadline: báo cáo phải sẵn sàng trước giờ làm việc, dữ liệu phải được xử lý trước chu kỳ tiếp theo hoặc kết quả phải hoàn tất trước một mốc nghiệp vụ.

Tăng số máy, CPU hoặc GPU thường rút ngắn thời gian chạy, nhưng làm tăng chi phí và có thể gây nghẽn ở storage, network, database hoặc quota. Chọn ít capacity giúp tiết kiệm tức thời nhưng có thể khiến batch trễ deadline, làm backlog tích lũy và ảnh hưởng công việc tiếp theo. Vì vậy, capacity planning cần trả lời đồng thời ba câu hỏi:

- Có bao nhiêu công việc và mỗi công việc tiêu thụ tài nguyên nào?
- Cần bao nhiêu capacity để hoàn tất trước deadline với mức dự phòng hợp lý?
- Mức capacity đó có nằm trong ngân sách và giới hạn của dependency không?

Mục tiêu không phải chạy nhanh nhất bằng mọi giá. Mục tiêu là hoàn tất đúng hạn với chi phí phù hợp, đồng thời có phương án khi tải tăng, worker lỗi hoặc capacity không sẵn có.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, bài học kết nối lựa chọn VM, container, serverless, CPU, bộ nhớ, mạng và accelerator với xử lý nền, tự động mở rộng và tối ưu chi phí vận hành.

Sau bài học, người học có thể:

- Phân loại batch theo deadline, độ ưu tiên, khối lượng và khả năng chia nhỏ.
- Ước lượng CPU, RAM, GPU, storage, network và thời gian xử lý.
- Tính worker capacity cần thiết từ throughput và thời gian khả dụng.
- Phân biệt scale-up, scale-out, parallelism và giới hạn hiệu suất.
- Chọn VM, container, managed batch service hoặc serverless phù hợp.
- Lập ngân sách compute, storage, network, retry và dự phòng.
- Kết hợp capacity ổn định với Spot/Preemptible khi workload cho phép.
- Thiết kế queue, autoscaling, checkpoint, retry và deadline monitoring.
- Đánh giá chi phí trên mỗi đơn vị công việc hoàn tất.

## 2. Xác định yêu cầu batch

### 2.1. Deadline nghiệp vụ và thời gian xử lý

Deadline là thời điểm cuối cùng kết quả phải sẵn sàng. Cần phân biệt deadline với thời gian compute thuần. Một batch có thể phải chờ input, chờ capacity, tải dữ liệu, khởi tạo container, xử lý, ghi output và kiểm tra kết quả.

Thời gian từ lúc nhận batch đến lúc hoàn tất có thể mô hình hóa:

\[
T_{total}=T_{queue}+T_{provision}+T_{data}+T_{compute}+T_{finalize}
\]

Trong đó:

- \(T_{queue}\): thời gian chờ trong queue hoặc scheduler.
- \(T_{provision}\): thời gian cấp VM/node/container/function và khởi tạo runtime.
- \(T_{data}\): thời gian đọc input, tải model hoặc đồng bộ dữ liệu.
- \(T_{compute}\): thời gian xử lý chính.
- \(T_{finalize}\): ghi output, commit manifest, kiểm tra và thông báo kết quả.

Nếu deadline là \(D\), thời gian thực sự dành cho compute chỉ là:

\[
T_{compute,budget}=D-T_{queue}-T_{provision}-T_{data}-T_{finalize}-T_{reserve}
\]

\(T_{reserve}\) là phần dự phòng cho biến động và lỗi. Nếu kết quả âm hoặc quá nhỏ, cấu hình capacity hiện tại không thể đáp ứng deadline; cần giảm overhead, thay đổi cách xử lý, tăng ngân sách hoặc thương lượng deadline.

### 2.2. Deadline cứng và deadline mềm

| Loại deadline | Ý nghĩa | Chiến lược capacity |
|---|---|---|
| Cứng | Trễ hạn gây vi phạm nghiệp vụ, hợp đồng hoặc quy định | Giữ capacity dự phòng, ưu tiên cao, kiểm soát dependency và có fallback |
| Mềm | Có thể trễ trong giới hạn chấp nhận được | Xếp hàng, tận dụng capacity rẻ, co giãn theo backlog |
| Theo cửa sổ | Phải hoàn tất trong một khoảng thời gian, ví dụ ban đêm | Lập lịch theo giờ, tránh tranh chấp với workload khác |
| Theo freshness | Dữ liệu không được cũ quá một ngưỡng | Theo dõi tuổi backlog và thời điểm dữ liệu, không chỉ thời lượng job |

Một batch có thể có nhiều mốc: input phải được nhận trước 01:00, xử lý xong trước 05:00 và báo cáo được publish trước 06:00. Hãy ghi rõ deadline cho từng giai đoạn để tránh dùng toàn bộ cửa sổ cho compute.

### 2.3. Ưu tiên và phân loại công việc

Không phải mọi task trong batch đều có cùng mức ưu tiên. Có thể chia thành:

- Critical: phải hoàn tất trước deadline cứng.
- High: ảnh hưởng trực tiếp đến hoạt động của người dùng hoặc hệ thống khác.
- Normal: cần hoàn tất theo lịch nhưng có thể trễ ngắn.
- Best-effort: có thể chờ capacity rẻ hoặc chạy khi tải thấp.

Scheduler cần hỗ trợ priority, deadline, fairness và giới hạn tài nguyên theo nhóm. Nếu tất cả job cùng một queue và cùng priority, tác vụ lớn có thể chặn tác vụ nhỏ hoặc workload quan trọng.

### 2.4. Xác định khối lượng công việc

Ghi lại:

- Số lượng record, file, message, partition hoặc task.
- Kích thước input và output.
- Thời gian xử lý trung bình, p95 và p99 của một đơn vị.
- Tỷ lệ task lỗi, retry và phải chạy lại.
- Mức độ song song và dependency giữa các task.
- Tài nguyên cần cho mỗi worker: vCPU, RAM, GPU, disk và network.
- Tần suất batch và xu hướng tăng trưởng dữ liệu.

Không dùng duy nhất thời gian trung bình nếu phân bố task lệch mạnh. Một số file lớn hoặc partition khó có thể trở thành straggler và quyết định thời điểm batch thực sự hoàn tất.

### 2.5. Phân biệt batch độc lập và batch có dependency

Batch gồm các task độc lập có thể phân phối dễ dàng cho nhiều worker. Batch có dependency cần thực hiện theo DAG: một bước phải hoàn tất trước bước khác, hoặc nhiều nhánh phải hội tụ trước khi publish kết quả.

Với DAG, deadline của toàn batch phụ thuộc critical path, không phải tổng thời gian của mọi task. Cần tính cả thời gian chờ giữa các bước, đồng bộ và barrier.

## 3. Đo resource profile của workload

### 3.1. CPU-bound

CPU-bound workload dùng nhiều phép tính và ít chờ I/O. Ví dụ: nén, mã hóa, phân tích số, compile hoặc xử lý ảnh. Tăng vCPU có thể tăng throughput nếu ứng dụng có đủ parallelism và không bị giới hạn bởi memory bandwidth hoặc lock contention.

Đo CPU utilization, CPU throttling, run queue, context switch, thời gian xử lý trên mỗi task và throughput. CPU utilization thấp có thể do worker đang chờ storage/network chứ không có nghĩa cần thêm CPU.

### 3.2. Memory-bound

Workload như xử lý dataframe lớn, join, sort hoặc cache có thể cần nhiều RAM. Thiếu RAM gây swap, OOM hoặc spill ra disk, làm thời gian xử lý tăng mạnh.

Đo peak resident memory, memory per task, page fault, swap, OOM event và memory bandwidth nếu có. Khi tăng parallelism, tổng RAM thường tăng theo số task đồng thời; không chỉ dựa vào memory trung bình của một worker.

### 3.3. I/O-bound và network-bound

ETL, copy dữ liệu, object processing hoặc query nhiều nguồn có thể bị giới hạn bởi IOPS, throughput storage, network bandwidth, latency hoặc quota API. Thêm worker có thể làm nhiều request cùng tranh chấp một backend và giảm throughput tổng.

Đo read/write MB/s, IOPS, queue depth, network throughput, packet loss, connection count, request latency và throttling. Đặt worker gần dữ liệu khi có thể để giảm cross-zone/region transfer và latency.

### 3.4. GPU và accelerator

Workload ML, render hoặc mô phỏng có thể cần GPU/accelerator. Đo thời gian GPU thực sự bận, VRAM, memory bandwidth, data loader throughput, interconnect và thời gian copy dữ liệu giữa CPU/GPU.

GPU utilization thấp có thể do CPU không cung cấp dữ liệu đủ nhanh hoặc storage chậm. Thêm GPU trong tình huống đó làm chi phí tăng mà throughput không cải thiện.

### 3.5. Benchmark ở cấu hình đại diện

Benchmark cần dùng dữ liệu có kích thước và phân bố giống production. Thử ít nhất một số mức concurrency và ghi nhận:

- Throughput hoàn tất, không chỉ số task đã bắt đầu.
- Thời gian p50/p95/p99 và thời gian task cuối cùng.
- CPU, RAM, GPU, disk và network utilization.
- Số lỗi, retry, OOM và throttling.
- Chi phí compute và dependency trong cùng khoảng đo.

Không ngoại suy tuyến tính từ một lần chạy nhỏ nếu workload có cache, shuffle, lock, quota hoặc điểm nghẽn chung.

## 4. Ước lượng capacity từ throughput

### 4.1. Mô hình throughput đơn giản

Gọi:

- \(Q\): số đơn vị công việc cần hoàn tất.
- \(r_w\): throughput đo được của một worker ở cấu hình đã chọn, tính bằng task/giây.
- \(N\): số worker đồng thời.
- \(\eta\): hiệu suất mở rộng tổng hợp, phản ánh overhead và tranh chấp khi chạy song song.
- \(T\): thời gian compute khả dụng.

Capacity gần đúng:

\[
Q_{capacity}=N\times r_w\times \eta\times T
\]

Để hoàn tất batch:

\[
N_{required}=\left\lceil\frac{Q}{r_w\times\eta\times T}\right\rceil
\]

\(\eta\) nên được đo từ benchmark ở mức parallelism tương ứng. Không mặc định nó bằng 1; overhead điều phối, shuffle, network và lock có thể làm hiệu suất giảm khi tăng worker.

### 4.2. Mô hình theo CPU-seconds

Nếu đã ước lượng tổng nhu cầu CPU là \(W_{cpu}\) vCPU-seconds, mỗi worker có \(V\) vCPU, target utilization là \(u\), hiệu suất song song là \(\eta\), và thời gian compute khả dụng là \(T\) giây:

\[
N_{required}=\left\lceil\frac{W_{cpu}}{V\times u\times\eta\times T}\right\rceil
\]

Mô hình này phù hợp với workload CPU-bound khi CPU demand được đo đáng tin cậy. Với I/O-bound, memory-bound hoặc GPU-bound, cần lập budget riêng cho tài nguyên tương ứng và lấy giới hạn capacity nhỏ nhất.

### 4.3. Ví dụ tính số worker

Một batch có 24.000 task. Benchmark cho thấy mỗi task tiêu thụ trung bình 30 vCPU-seconds. Tổng nhu cầu:

\[
W_{cpu}=24.000\times30=720.000\text{ vCPU-seconds}
\]

Deadline là 2 giờ. Dành 10 phút cho provision, tải dữ liệu, finalize và dự phòng, nên thời gian compute khả dụng là 110 phút, tương đương 6.600 giây. Mỗi worker có 4 vCPU; target utilization là 70%; hiệu suất song song ước lượng 80%.

\[
N_{required}=\left\lceil\frac{720.000}{4\times0,70\times0,80\times6.600}\right\rceil=49
\]

Vậy cần khoảng 49 worker theo mô hình này. Đây là điểm khởi đầu để kiểm thử; cần xác minh memory, I/O, network, quota và phân bố task. Nếu 24.000 task có một số job rất dài, cần thêm capacity hoặc chia partition để tránh straggler.

### 4.4. Tính capacity khi có workload mới liên tục

Nếu batch nhận thêm task trong lúc xử lý, gọi \(\lambda\) là tốc độ task đến và \(\mu\) là tốc độ task hoàn tất của toàn pool. Backlog chỉ giảm khi:

\[
\mu>\lambda
\]

Nếu backlog hiện tại là \(B\) task, thời gian drain gần đúng trong điều kiện tốc độ ổn định:

\[
T_{drain}=\frac{B}{\mu-\lambda}
\]

Nếu \(\mu\leq\lambda\), queue không thể giảm bền vững. Cần tăng capacity, giảm tốc độ nhận việc hoặc điều chỉnh lịch/ưu tiên.

### 4.5. Xét task không đồng đều và straggler

Một batch có thể hoàn thành gần hết nhưng một vài task cuối kéo dài hơn nhiều. Có thể dùng partition cân bằng, dynamic work stealing, speculative execution hoặc chia nhỏ task lớn. Tuy nhiên, speculative execution chạy trùng một task làm tăng chi phí và cần output idempotent.

Theo dõi thời gian task cuối, độ lệch kích thước partition và throughput theo worker. Nếu 95% task xong sớm nhưng 5% cuối kéo dài, thêm worker không chắc giải quyết được nếu các task đó không thể chia nhỏ.

## 5. Parallelism và hiệu suất mở rộng

### 5.1. Chia công việc thành đơn vị song song

Các dạng parallelism phổ biến:

- Data parallelism: chia dữ liệu thành partition độc lập.
- Task parallelism: chạy các bước khác nhau cùng lúc.
- Pipeline parallelism: xử lý các giai đoạn khác nhau đồng thời trên các phần dữ liệu khác nhau.
- Model/compute parallelism: chia phép tính hoặc mô hình qua nhiều CPU/GPU.

Chọn cách chia theo cấu trúc dữ liệu và dependency. Partition quá nhỏ làm overhead scheduling tăng; quá lớn làm giảm khả năng cân bằng tải và tăng thời gian retry khi worker lỗi.

### 5.2. Định luật Amdahl

Định luật Amdahl mô tả giới hạn tăng tốc khi chỉ một phần công việc có thể song song. Nếu tỷ lệ tuần tự là \(s\), số worker là \(N\), speedup lý tưởng gần đúng:

\[
S(N)=\frac{1}{s+\frac{1-s}{N}}
\]

Nếu 10% công việc không thể song song, dù tăng worker vô hạn thì speedup tối đa chỉ là 10 lần. Trong thực tế còn có overhead điều phối, đồng bộ và I/O nên speedup thấp hơn.

### 5.3. Scale-up và scale-out

**Scale-up** tăng tài nguyên của một worker, ví dụ từ 4 lên 16 vCPU hoặc thêm RAM. Cách này hữu ích khi một task cần bộ nhớ lớn, có phần tuần tự đáng kể hoặc khó phân tán.

**Scale-out** tăng số worker để xử lý nhiều partition song song. Cách này phù hợp với task độc lập, nhưng bị giới hạn bởi parallelism, dependency và network/storage.

Có thể kết hợp: chọn worker đủ lớn để chạy hiệu quả từng task, rồi scale-out theo số task độc lập. Không mặc định worker càng lớn hoặc càng nhiều đều tốt hơn.

### 5.4. Xác định điểm bão hòa

Tăng worker theo từng nấc và quan sát throughput. Nếu tăng worker từ 16 lên 32 nhưng throughput chỉ tăng rất ít trong khi latency, I/O hoặc lỗi tăng, hệ thống có thể đã bão hòa ở dependency hoặc phần tuần tự.

Đặt operating point trước vùng bão hòa để giữ headroom. Dùng dữ liệu benchmark và tải production đại diện, không lấy mức tối đa của một bài test ngắn làm capacity bền vững.

### 5.5. Chi phí đồng bộ và giao tiếp

Distributed batch cần truyền dữ liệu, shuffle, barrier hoặc aggregate kết quả. Chi phí network và serialization có thể vượt phần compute tiết kiệm được. Gom dữ liệu theo partition phù hợp, dùng compression khi có lợi và hạn chế trao đổi giữa worker.

Với GPU multi-node, kiểm tra interconnect và topology. Thêm node nhưng giao tiếp chậm có thể làm thời gian hoàn tất tăng.

## 6. Lập ngân sách capacity

### 6.1. Ngân sách compute

Compute cost phụ thuộc số worker, cấu hình, thời gian chạy và loại giá. Mô hình đơn giản:

\[
C_{compute}=N\times P_{worker-hour}\times H
\]

Trong đó \(P_{worker-hour}\) là giá mỗi worker-hour và \(H\) là số giờ chạy. Nếu worker có nhiều cấu hình hoặc giá thay đổi theo vùng/loại capacity, tính riêng từng nhóm rồi cộng lại.

Với autoscaling, nên tính theo capacity-time thực tế:

\[
C_{compute}=\sum_{i=1}^{k}N_i\times P_i\times H_i
\]

### 6.2. Tổng chi phí batch

Compute chỉ là một phần. Tổng chi phí có thể gồm:

\[
C_{total}=C_{compute}+C_{storage}+C_{network}+C_{orchestration}+C_{retry}+C_{observability}
\]

Trong đó:

- Storage: input, output, checkpoint, temporary data và snapshot.
- Network: data transfer, cross-zone/region, NAT hoặc egress.
- Orchestration: scheduler, control plane, queue và managed service charge.
- Retry: compute chạy lại, request dependency và lưu trữ trung gian.
- Observability: log, metric, trace và retention.

Tính cả chi phí lưu trữ dữ liệu tạm sau khi batch kết thúc và chi phí giữ capacity dự phòng trong cửa sổ chờ.

### 6.3. Tính số worker tối đa theo ngân sách

Nếu ngân sách còn lại cho compute là \(B_c\), giá một worker-hour là \(P\), và thời gian dự kiến là \(H\), số worker tối đa theo ngân sách:

\[
N_{budget}=\left\lfloor\frac{B_c}{P\times H}\right\rfloor
\]

Nếu \(N_{required}>N_{budget}\), kế hoạch không đồng thời đáp ứng deadline và ngân sách theo giả định hiện tại. Cần xem xét giảm resource cost, cải thiện thuật toán, tăng hiệu suất, dùng capacity rẻ hơn, chia batch theo cửa sổ hoặc điều chỉnh deadline. Không âm thầm hạ capacity rồi để batch trễ.

### 6.4. Ví dụ chi phí

Giả sử cần 49 worker, mỗi worker có giá minh họa 0,20 USD/giờ và chạy trong 110 phút:

\[
C_{compute}=49\times0,20\times\frac{110}{60}\approx17,97\text{ USD}
\]

Nếu storage, network, queue và observability ước tính thêm 8 USD, tổng dự kiến khoảng 25,97 USD. Cần cộng reserve cho retry và biến động nếu ngân sách yêu cầu mức tin cậy cao.

Giá 0,20 USD/giờ chỉ là giả định minh họa, không phải báo giá cloud. Lập kế hoạch thực tế phải dùng giá theo region, instance type, operating system, license và mô hình cam kết tại thời điểm chạy.

### 6.5. Cost per completed unit

Để so sánh cấu hình, dùng:

\[
C_{unit}=\frac{C_{total}}{Q_{completed}}
\]

Ví dụ chi phí trên mỗi triệu record, mỗi video, mỗi partition hoặc mỗi model training run. Cấu hình worker rẻ hơn nhưng chạy lâu, retry nhiều hoặc không đáp ứng deadline có thể có cost per completed unit cao hơn.

### 6.6. Ngân sách và deadline tạo thành miền khả thi

Capacity cần đủ lớn để đáp ứng deadline nhưng không vượt ngân sách. Có thể hình dung:

- Dưới capacity tối thiểu: batch không hoàn tất đúng hạn.
- Trong miền khả thi: batch đạt deadline và chi phí nằm trong budget.
- Trên capacity cần thiết: deadline không cải thiện tương xứng, chi phí tăng.

Mục tiêu là chọn điểm thấp nhất trong miền khả thi có đủ headroom và đáp ứng mức rủi ro chấp nhận được.

## 7. Chọn loại compute cho batch

### 7.1. VM và instance group

VM phù hợp với batch cần kiểm soát hệ điều hành, binary native, GPU driver, local disk hoặc cấu hình mạng đặc thù. Instance group/autoscaling group có thể tăng giảm số máy theo queue hoặc lịch.

Ưu điểm:

- Kiểm soát cấu hình CPU/RAM, accelerator và hệ điều hành.
- Phù hợp job dài hoặc phần mềm cần môi trường tùy chỉnh.
- Có thể dùng Spot/Preemptible để giảm giá nếu job chịu được gián đoạn.

Điểm cần tính:

- Thời gian boot, cài agent và tải dữ liệu.
- Capacity quota, zone availability và image maintenance.
- Idle time khi job chưa đến hoặc đã hoàn tất.
- Cơ chế drain, checkpoint và thay thế VM lỗi.

### 7.2. Container và Kubernetes Job

Container đóng gói ứng dụng/runtime nhất quán; Kubernetes Job quản lý số lần chạy hoàn tất và pod song song. Phù hợp batch có nhiều task, cần resource request/limit, node pool đa dạng hoặc tích hợp với queue và scheduler.

Ưu điểm:

- Khai báo CPU/RAM/GPU và parallelism theo workload.
- Dùng node pool riêng cho high-memory, GPU hoặc Spot.
- Có thể tái sử dụng image, policy và telemetry của cluster.

Điểm cần tính:

- Thời gian pull image, scheduling và node scale-out.
- Pod Pending do thiếu tài nguyên, taint hoặc quota.
- Chi phí cluster/node idle và control plane.
- Job retry, backoffLimit, activeDeadlineSeconds và dữ liệu tạm.

Ví dụ Kubernetes Job:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: nightly-etl
spec:
  completions: 24000
  parallelism: 49
  backoffLimit: 3
  activeDeadlineSeconds: 6600
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: etl
          image: registry.example.com/data/etl@sha256:0123456789abcdef...
          resources:
            requests:
              cpu: "4"
              memory: "8Gi"
            limits:
              cpu: "4"
              memory: "8Gi"
```

Manifest minh họa. `completions: 24000` và `parallelism: 49` phù hợp khi mỗi pod xử lý đúng một completion unit; nếu một pod xử lý nhiều partition, cần điều chỉnh mô hình. `activeDeadlineSeconds` áp dụng cho thời gian hoạt động của Job theo semantics Kubernetes, không phải thời gian của một pod riêng lẻ. Cần cộng thời gian provisioning và finalize vào deadline tổng thể ở tầng orchestration.

### 7.3. Managed batch service

Managed batch service cung cấp queue, scheduler, compute environment, job definition, retry và capacity allocation. Phù hợp khi muốn tập trung vào job thay vì tự xây scheduler và lifecycle.

Kiểm tra:

- Loại instance/accelerator và vùng hỗ trợ.
- Maximum vCPU, quota và allocation strategy.
- Job priority, dependency, retry và timeout semantics.
- Spot/On-Demand mix và fallback.
- Chi phí điều phối, storage, log và network.
- Cách theo dõi job bị stuck, failed hoặc vượt deadline.

### 7.4. Serverless function và workflow

Serverless phù hợp với task ngắn, event-driven, có thể chia nhỏ và không cần giữ worker lâu. Workflow orchestration có thể điều phối nhiều bước và retry theo state machine.

Ưu điểm là giảm quản lý hạ tầng và scale theo invocation. Hạn chế có thể gồm maximum execution duration, concurrency quota, cold start, giới hạn ephemeral storage, payload và chi phí invocation khi retry nhiều.

Nếu batch có task dài hoặc dữ liệu lớn, cân nhắc chia thành nhiều function nhỏ, dùng queue hoặc chuyển phần compute nặng sang container/VM.

### 7.5. Bảng chọn nhanh

| Nhu cầu | Lựa chọn thường phù hợp | Điểm cần kiểm tra |
|---|---|---|
| Task ngắn, event-driven | Serverless function | Max duration, concurrency, retry và request cost |
| Nhiều task container độc lập | Kubernetes Job hoặc managed batch | Scheduling, node capacity, image pull và parallelism |
| Job dài, driver/native đặc thù | VM/instance group | Boot time, image, quota và lifecycle |
| GPU training/render | GPU VM, GPU node pool hoặc managed batch | VRAM, driver, interconnect và checkpoint |
| Workload biến động, chịu gián đoạn | Spot/Preemptible pool kết hợp stable capacity | Interruption, retry, checkpoint và fallback |
| Quy trình nhiều bước phụ thuộc | Workflow orchestration + queue/compute | State, deadline, retry và idempotency |

## 8. Kết hợp capacity ổn định và capacity linh hoạt

### 8.1. Stable baseline

Với batch có deadline cứng, có thể giữ một phần capacity ổn định để đảm bảo tiến độ tối thiểu. Phần còn lại dùng Spot/Preemptible hoặc capacity linh hoạt để tăng throughput khi có sẵn.

Không coi commitment giảm giá là capacity reservation nếu sản phẩm chỉ cam kết mức giá. Chỉ tính tài nguyên là capacity được giữ chỗ khi dịch vụ và điều khoản cụ thể bảo đảm khả năng cấp phát.

### 8.2. Phân chia theo ưu tiên

Ví dụ một batch có hai lớp:

- Critical partition: chạy trên stable capacity để đảm bảo kết quả tối thiểu.
- Flexible partition: chạy trên Spot hoặc capacity rẻ hơn; có thể retry nếu bị thu hồi.

Scheduler cần giới hạn số job flexible được fallback sang stable để không làm quá tải workload critical.

### 8.3. Xử lý interruption

Với Spot/Preemptible worker:

- Lưu checkpoint và kết quả trung gian bên ngoài máy.
- Dùng task ID ổn định và output idempotent.
- Khi nhận interruption notice, ngừng nhận task mới và checkpoint nếu đủ thời gian.
- Nếu mất đột ngột, lease/heartbeat phát hiện worker chết và queue giao lại task.
- Đa dạng hóa instance type và zone để tăng khả năng tìm capacity.

Không phụ thuộc hoàn toàn vào interruption notice; worker có thể mất mà không đủ thời gian xử lý graceful shutdown.

### 8.4. Khi capacity linh hoạt không có sẵn

Có thể chờ queue, giảm tốc độ nhận job, chuyển một phần sang stable pool nếu còn ngân sách, hoặc điều chỉnh deadline. Không tạo vòng lặp yêu cầu capacity liên tục khi quota/availability không đáp ứng.

### 8.5. So sánh chi phí có tính interruption

Tổng chi phí của capacity linh hoạt cần tính thêm:

- Công việc phải chạy lại.
- Checkpoint và storage operation.
- Thời gian chờ capacity thay thế.
- Stable fallback khi Spot thiếu.
- Chi phí điều phối và quan sát interruption.

Giá mỗi giờ thấp không bảo đảm cost per completed task thấp.

## 9. Queue, scheduler và autoscaling

### 9.1. Queue làm bộ đệm

Queue tách thời điểm nhận job khỏi thời điểm xử lý. Nó giúp hấp thụ burst và cho phép scheduler phân phối task theo priority, deadline hoặc resource requirement.

Queue cần có giới hạn dung lượng, retention, dead-letter policy và metric tuổi message. Nếu producer tạo việc nhanh hơn capacity xử lý trong thời gian dài, backlog sẽ tăng và deadline bị trễ.

### 9.2. Scale theo backlog và deadline

Queue depth chỉ cho biết số việc đang chờ. Để dự đoán deadline, cần biết throughput hiện tại, thời gian còn lại và tốc độ job mới đến.

Metric hữu ích:

- Queue depth và age of oldest task.
- Arrival rate và completion rate.
- Estimated work remaining (CPU/GPU seconds hoặc task-seconds).
- Deadline slack của job gần đến hạn.
- Worker utilization và startup time.
- Dependency saturation và retry rate.

Autoscaler nên tăng capacity khi estimated work remaining vượt khả năng xử lý trong cửa sổ còn lại. Khi dependency bão hòa, tăng worker có thể không giúp; cần giảm concurrency hoặc xử lý bottleneck.

### 9.3. Ước lượng thời gian drain

Nếu backlog là \(B\), throughput hiện tại \(\mu\) task/giây và task mới đến ở tốc độ \(\lambda\), thời gian drain xấp xỉ \(B/(\mu-\lambda)\) khi \(\mu>\lambda\). Dùng giá trị throughput đo được ở mức tải hiện tại, không dùng throughput lý tưởng từ benchmark đơn lẻ.

### 9.4. Scale-out có giới hạn

Đặt max workers dựa trên:

- Deadline và throughput cần đạt.
- Database connection budget và API rate limit.
- Storage/network capacity.
- CPU/RAM/GPU quota và node capacity.
- Ngân sách chi phí.
- Số task có thể chạy song song.

Nếu autoscaler đạt max mà queue vẫn tăng, phát cảnh báo sớm và thực hiện runbook: tăng quota đã phê duyệt, giảm input, ưu tiên job critical hoặc điều chỉnh deadline.

### 9.5. Scale-in và kết thúc batch

Khi queue giảm, giảm worker theo từng bước để tránh dao động. Trước khi terminate worker, ngừng nhận task mới, hoàn tất hoặc checkpoint task đang chạy và flush kết quả. Xác minh output được commit trước khi xóa tài nguyên tạm.

Sau batch, thu hồi capacity không cần thiết, nhưng giữ log, metric, manifest và artifact theo retention. Đừng xóa checkpoint trước khi xác nhận batch hoàn tất và có thể phục hồi.

## 10. Thiết kế task để sử dụng capacity hiệu quả

### 10.1. Chọn kích thước partition

Partition quá nhỏ tạo overhead scheduler, network và metadata; partition quá lớn làm giảm parallelism và tăng lượng công việc phải chạy lại. Benchmark vài kích thước để tìm điểm cân bằng.

Một quy tắc thực dụng là task nên đủ dài để compute lớn hơn đáng kể so với startup/dispatch overhead, nhưng không dài đến mức một lần lỗi làm mất quá nhiều tiến độ.

### 10.2. Idempotency và output commit

Worker có thể bị retry sau timeout hoặc interruption. Mỗi task cần ID ổn định và output commit có thể lặp an toàn. Ghi output vào vị trí tạm, xác minh checksum, sau đó cập nhật manifest/commit marker atomic. Tránh hai worker ghi đè cùng output mà không có coordination.

### 10.3. Checkpoint

Với task dài, lưu checkpoint định kỳ vào storage bền vững. Chọn interval dựa trên chi phí ghi và lượng compute có thể mất. Checkpoint cần version, checksum và metadata về code/input để tránh khôi phục bằng phiên bản không tương thích.

### 10.4. Retry và dead-letter

Phân biệt lỗi transient, lỗi dữ liệu và lỗi code. Retry transient với backoff và jitter; đưa poison task vào dead-letter queue sau số lần thử giới hạn. Không retry vô hạn vì vừa tăng chi phí vừa làm queue không thể drain.

### 10.5. Xử lý straggler

Theo dõi task chậm hơn nhiều so với median. Có thể chia nhỏ task lớn, cân bằng partition hoặc dùng speculative execution cho tác vụ idempotent. Chỉ bật speculative execution khi chi phí chạy trùng thấp hơn giá trị của việc giảm tail latency.

## 11. Quản lý tài nguyên và dependency

### 11.1. RAM và concurrency

Nếu mỗi task dùng \(M_t\) RAM và worker có \(M_w\) RAM, số task đồng thời tối đa theo memory gần đúng:

\[
K_{memory}=\left\lfloor\frac{M_w-M_{reserve}}{M_t}\right\rfloor
\]

Trong đó \(M_{reserve}\) dành cho runtime, cache, agent và overhead. Concurrency thực tế phải lấy giới hạn nhỏ nhất giữa CPU, RAM, GPU, I/O và dependency.

### 11.2. Database và connection pool

Batch worker thường mở nhiều connection khi scale-out. Nếu mỗi worker có pool tối đa \(P\), số worker là \(N\), tổng connection tiềm năng là \(N\times P\). Giới hạn worker theo connection budget của database và workload khác dùng chung.

Giảm pool size hoặc dùng connection proxy có thể giúp quản lý kết nối, nhưng không làm database xử lý được nhiều query hơn capacity thực. Theo dõi pool wait, query latency, lock và throughput.

### 11.3. API quota và rate limit

Nếu mỗi task gọi external API, tính tổng request theo số task, số lần gọi và retry. Dùng token bucket hoặc rate limiter chung để tổng tốc độ không vượt quota. Tôn trọng `Retry-After`, backoff và retry budget.

### 11.4. Storage và network

Đo throughput đọc/ghi, IOPS, network transfer và chi phí egress. Batch có shuffle lớn có thể tạo network bottleneck; lưu output ở vùng xa có thể tăng latency và chi phí. Đặt worker gần data và dùng format/partition phù hợp.

### 11.5. GPU và accelerator

GPU worker có thể đắt và khan hiếm. Đảm bảo batch có đủ task để lấp đầy GPU, data loader không làm accelerator chờ và checkpoint không chiếm quá nhiều thời gian. Cân nhắc GPU stable cho job deadline cứng, GPU Spot cho job có thể checkpoint.

## 12. Dự phòng deadline và rủi ro

### 12.1. Headroom

Không lập kế hoạch ở đúng giới hạn throughput trung bình. Dành headroom cho biến động input, task dài, node failure, retry, provisioning và dependency slowdown. Headroom nên dựa trên dữ liệu lịch sử và mức rủi ro chấp nhận được.

### 12.2. Percentile thay vì chỉ average

Nếu batch có deadline nghiêm ngặt, dùng p95/p99 của thời gian task và throughput thay vì chỉ average. Kiểm tra ngày có volume lớn, dependency chậm và vùng capacity khan hiếm.

### 12.3. Kịch bản lỗi

Mô phỏng:

- Một phần worker bị lỗi hoặc Spot bị thu hồi.
- Node pool không scale do quota hoặc thiếu IP.
- Database chậm hoặc hết connection.
- Object storage throttling.
- Một partition lớn trở thành straggler.
- Scheduler hoặc queue tạm gián đoạn.
- Retry tăng làm backlog phình to.

Xác định batch vẫn hoàn tất trong deadline hay có thể degraded theo ưu tiên. Nếu không, cần thay đổi baseline, deadline hoặc quy trình nghiệp vụ.

### 12.4. Nhiều batch cạnh tranh

Khi nhiều batch cùng chạy, tổng capacity không thể được lập kế hoạch độc lập. Dùng quota theo queue/tenant, priority, fairness và giới hạn tổng worker. Tránh batch ít ưu tiên chiếm hết GPU, database hoặc network khi batch critical sắp đến deadline.

## 13. Ví dụ lập kế hoạch hoàn chỉnh

### 13.1. Bối cảnh

Một hệ thống xử lý 24.000 partition dữ liệu mỗi đêm. Deadline là 02:00–04:00, tức 2 giờ. Batch cần 10 phút để khởi tạo, tải metadata, finalize và publish; dành thêm 10 phút reserve. Benchmark đo mỗi partition cần 30 vCPU-seconds. Worker có 4 vCPU; target utilization 70%; hiệu suất mở rộng 80%.

### 13.2. Tính capacity

Thời gian compute khả dụng:

\[
T=120-10-10=100\text{ phút}=6.000\text{ giây}
\]

Tổng CPU demand:

\[
W=24.000\times30=720.000\text{ vCPU-seconds}
\]

Số worker:

\[
N=\left\lceil\frac{720.000}{4\times0,70\times0,80\times6.000}\right\rceil=54
\]

Kế hoạch ban đầu cần khoảng 54 worker 4 vCPU trong cửa sổ compute. Sau đó benchmark tải 54 worker để xác minh throughput, memory, storage và database; nếu efficiency thực tế thấp hơn 80%, phải tính lại.

### 13.3. Tính ngân sách

Giả sử giá minh họa là 0,20 USD mỗi worker-hour. Compute cost:

\[
C=54\times0,20\times\frac{100}{60}=18\text{ USD}
\]

Nếu budget compute là 20 USD, còn 2 USD headroom cho capacity bổ sung; storage, network và orchestration phải nằm trong ngân sách riêng hoặc được trừ trước khi tính worker budget. Nếu tổng ngân sách batch chỉ là 20 USD bao gồm mọi chi phí, phải trừ các khoản phụ trước khi tính số worker.

### 13.4. Phương án capacity

- Giữ 20 worker stable để bảo đảm tiến độ cơ bản.
- Mở rộng thêm tối đa 34 worker Spot khi có capacity.
- Job critical được ưu tiên stable; partition linh hoạt chạy trên Spot.
- Khi Spot bị thu hồi, queue giữ phần việc còn lại; scheduler chỉ fallback một phần sang stable nếu budget/headroom cho phép.
- Theo dõi queue age, estimated work remaining và deadline slack.

Phương án này chỉ hợp lệ nếu 20 stable worker đủ đáp ứng yêu cầu tối thiểu hoặc có cơ chế điều chỉnh deadline cho phần linh hoạt. Nếu toàn bộ 24.000 partition phải hoàn tất đúng 2 giờ ngay cả khi Spot mất hoàn toàn, baseline stable phải đủ capacity cho kịch bản đó.

### 13.5. Sau lần chạy đầu

So sánh dự báo với thực tế: thời gian provision, throughput, p95/p99 task duration, retry, interruption, chi phí và thời điểm publish. Cập nhật model capacity bằng số liệu thực tế thay vì giữ nguyên giả định ban đầu.

## 14. Những sai lầm thường gặp

- **Tính capacity từ CPU trung bình:** bỏ qua RAM, I/O, network và GPU.
- **Dùng toàn bộ deadline cho compute:** quên queue, provision, data transfer và finalize.
- **Giả định throughput tăng tuyến tính:** bỏ qua phần tuần tự, synchronization và bottleneck.
- **Không đo task cuối:** straggler khiến batch trễ dù phần lớn task đã hoàn tất.
- **Chọn worker quá lớn:** có thể lãng phí tài nguyên nếu task không tận dụng parallelism.
- **Chọn quá nhiều worker:** tạo contention ở database, storage, network hoặc API quota.
- **Chỉ tính compute cost:** quên storage, egress, retry, orchestration và observability.
- **Dùng giá Spot như cam kết:** capacity có thể không sẵn hoặc bị thu hồi.
- **Không có stable fallback:** batch critical bị trễ khi Spot mất.
- **Không có checkpoint/idempotency:** retry gây mất tiến độ hoặc output trùng.
- **Scale theo queue depth đơn thuần:** không xét deadline, throughput và dependency saturation.
- **Không có budget guardrail:** autoscaler tạo chi phí vượt dự kiến.
- **Không benchmark trên dữ liệu đại diện:** dự báo sai khi input lớn hoặc phân bố khác.
- **Không cập nhật model:** traffic và thời gian xử lý thay đổi nhưng capacity plan không được rà soát.

## 15. Checklist chọn capacity cho batch

### Yêu cầu và workload

- [ ] Đã xác định deadline nghiệp vụ, cửa sổ chạy và mức ưu tiên.
- [ ] Đã đo số task, kích thước input/output và phân bố thời gian xử lý.
- [ ] Đã xác định task độc lập, DAG dependency và phần có thể song song hóa.
- [ ] Đã phân loại CPU, RAM, GPU, storage và network bottleneck.
- [ ] Đã benchmark bằng dữ liệu đại diện và ghi p50/p95/p99.

### Capacity và scheduling

- [ ] Đã trừ queue, provisioning, data transfer, finalize và reserve khỏi deadline.
- [ ] Đã tính số worker từ throughput hoặc resource demand.
- [ ] Đã xác minh parallel efficiency và điểm bão hòa.
- [ ] Đã tính worker theo RAM, GPU, IOPS, network và dependency quota.
- [ ] Đã thiết lập priority, queue, retry, checkpoint và idempotency.
- [ ] Đã xác định stable baseline và điều kiện dùng Spot/Preemptible.

### Ngân sách

- [ ] Đã tính compute, storage, network, orchestration, retry và observability.
- [ ] Đã dùng giá đúng region, instance type và mô hình billing.
- [ ] Đã tính cost per completed unit.
- [ ] Đã đặt max workers, quota và budget alert.
- [ ] Đã có phương án khi capacity cần thiết vượt budget.

### Vận hành

- [ ] Theo dõi queue age, throughput, estimated work remaining và deadline slack.
- [ ] Có cảnh báo khi worker pool đạt max mà backlog vẫn tăng.
- [ ] Đã thử worker failure, interruption, dependency throttling và quota exhaustion.
- [ ] Scale-in có drain và không xóa output/checkpoint chưa commit.
- [ ] Sau batch có báo cáo thời gian, chi phí, lỗi và capacity thực tế.
- [ ] Định kỳ cập nhật mô hình khi volume, code hoặc giá cloud thay đổi.

## 16. Kết luận

Chọn capacity cho batch là bài toán cân bằng giữa khối lượng công việc, thời gian khả dụng, hiệu suất song song và ngân sách. Bắt đầu bằng deadline nghiệp vụ, đo resource profile và throughput trên dữ liệu đại diện. Trừ thời gian queue, provisioning, tải dữ liệu, finalize và reserve trước khi tính số worker. Dùng benchmark để xác định parallel efficiency, điểm bão hòa và ảnh hưởng của straggler.

Sau đó chọn VM, container, managed batch hoặc serverless theo thời lượng task, yêu cầu runtime và cách điều phối. Tính tổng chi phí gồm compute, storage, network, orchestration, retry và quan sát; dùng cost per completed unit để so sánh. Nếu cần tiết kiệm, có thể kết hợp stable baseline với Spot/Preemptible cho phần việc chịu gián đoạn, nhưng phải có checkpoint, idempotency và fallback phù hợp.

Autoscaling nên dựa trên backlog, estimated work remaining và deadline slack, đồng thời tuân thủ giới hạn của database, storage, network, quota và ngân sách. Đo kết quả sau mỗi batch rồi cập nhật capacity model giúp hệ thống hoàn tất đúng hạn với mức chi phí có thể dự báo và kiểm soát.
