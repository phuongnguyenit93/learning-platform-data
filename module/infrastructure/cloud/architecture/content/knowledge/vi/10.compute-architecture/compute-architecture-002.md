# Chọn kích thước tài nguyên theo CPU, bộ nhớ, I/O và đặc tính tải

## 1. Vì sao phải sizing tài nguyên có căn cứ?

Khi triển khai ứng dụng trên cloud, việc chọn máy ảo, container, node hoặc cấu hình serverless quá nhỏ có thể gây độ trễ cao, timeout, lỗi bộ nhớ và giảm khả năng phục vụ. Chọn quá lớn lại làm tăng chi phí cố định, lãng phí năng lực và khiến nhóm khó dự báo ngân sách. Cấu hình phù hợp phải được xác định từ **đặc tính workload và mục tiêu dịch vụ**, sau đó được kiểm chứng bằng số liệu đo và thử nghiệm tải.

**Sizing (chọn kích thước tài nguyên)** là quá trình ước lượng và kiểm chứng năng lực compute, bộ nhớ, lưu trữ, mạng và các giới hạn liên quan để ứng dụng đáp ứng mục tiêu nghiệp vụ trong điều kiện tải dự kiến. Nó không chỉ là chọn số vCPU và GB RAM. Một dịch vụ có thể thiếu CPU nhưng vẫn biểu hiện chậm do database I/O; có nhiều RAM nhưng vẫn gặp lỗi do giới hạn file descriptor; có đủ compute nhưng nghẽn vì kết nối mạng hoặc giới hạn quota.

Bài học thuộc chương **Kiến trúc tính toán** của module **CLOUD_ARCHITECTURE**, nối yêu cầu nghiệp vụ với lựa chọn compute và các đánh đổi về độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo **Well-Architected**.

Sau bài này, bạn có thể:

- Phân loại workload theo CPU-bound, memory-bound, I/O-bound, network-bound và đặc tính burst/steady.
- Chọn chỉ số đo phù hợp thay vì chỉ nhìn CPU trung bình.
- Ước lượng cấu hình ban đầu theo tải, concurrency, latency và headroom.
- Thiết kế benchmark, load test, stress test và kiểm tra tải sau sự cố.
- Xác định giới hạn tài nguyên, autoscaling và các tín hiệu cần theo dõi sau triển khai.

## 2. Bắt đầu từ nhu cầu và hình dạng tải

Trước khi chọn cấu hình, hãy mô tả **ứng dụng làm gì và tải đến như thế nào**. Một hệ thống đặt lịch, API tra cứu và bộ xử lý video có đặc tính hoàn toàn khác nhau dù cùng chạy trong cloud.

### 2.1. Bộ câu hỏi đầu vào

| Nhóm | Câu hỏi | Ví dụ dữ liệu cần thu thập |
|---|---|---|
| Quy mô | Có bao nhiêu người dùng hoạt động, request hoặc job mỗi giây/phút? | 120 request/giây trung bình, 400 request/giây giờ cao điểm |
| Đồng thời | Có bao nhiêu request/job đang xử lý cùng lúc? | 250 request in-flight; 40 worker job đồng thời |
| Độ trễ | Mục tiêu p50/p95/p99 là bao nhiêu? | p95 dưới 300 ms cho API đọc |
| Tính chất xử lý | Nhiều phép tính, giữ nhiều dữ liệu trong bộ nhớ hay chờ I/O? | Mã hóa ảnh, phân tích dữ liệu, truy vấn database |
| Kích thước dữ liệu | Request/response, payload, file và working set lớn bao nhiêu? | JSON 20 KB, file 30 MB, cache working set 4 GB |
| Thời gian tải | Tải ổn định hay tăng đột ngột? | Tải theo giờ, burst khi mở bán |
| Tăng trưởng | Dự báo người dùng và dữ liệu trong kỳ nào? | Tăng 30% trong 12 tháng, giả định cần xác minh |
| Phụ thuộc | Database, queue, API đối tác có giới hạn gì? | 1.000 connection tối đa, API đối tác 100 request/giây |
| Tin cậy | Điều gì xảy ra khi mất một instance/AZ? | Các instance còn lại phải chịu phần lớn tải |

Hãy tách **tải trung bình**, **tải đỉnh**, **tải đột biến** và **tải tăng trưởng**. Một cấu hình chạy tốt trong 15 phút benchmark không chứng minh sẽ đáp ứng peak theo mùa, cũng không chứng minh còn đủ năng lực khi một AZ gặp sự cố.

### 2.2. Các hình dạng tải thường gặp

| Hình dạng | Đặc điểm | Hệ quả sizing |
|---|---|---|
| **Steady-state** | Tải tương đối ổn định, ít thay đổi | Có thể chọn capacity nền tương đối cố định và tối ưu utilization |
| **Diurnal/seasonal** | Tải thay đổi theo giờ, ngày hoặc mùa | Cần quan sát chu kỳ, scheduled scaling hoặc autoscaling |
| **Burst** | Tăng rất nhanh trong thời gian ngắn | Cần headroom, queue/buffer, scaling nhanh và giới hạn bảo vệ |
| **Spiky/event-driven** | Job xuất hiện theo sự kiện, có thể không đều | Scale theo backlog, tốc độ xử lý và thời hạn hoàn thành |
| **Long-running** | Một tác vụ chạy lâu, giữ bộ nhớ hoặc CPU | Đánh giá thời gian chạy, concurrency, memory growth và interruption |
| **Batch** | Xử lý khối lượng lớn trong cửa sổ thời gian xác định | Tối ưu throughput, chi phí theo job và lịch chạy |

Một ứng dụng có thể kết hợp nhiều hình dạng: API nhận tải burst còn worker xử lý queue theo steady-state. Nên sizing riêng từng workload thay vì buộc tất cả thành phần dùng cùng cấu hình.

## 3. Nhận diện CPU-bound, memory-bound, I/O-bound và network-bound

Phân loại này giúp đặt giả thuyết ban đầu về cổ chai (bottleneck). Trong thực tế, workload có thể đồng thời bị giới hạn bởi nhiều tài nguyên hoặc bởi một dependency bên ngoài.

### 3.1. CPU-bound

**CPU-bound** là workload mà thời gian xử lý chủ yếu bị giới hạn bởi năng lực tính toán. Ví dụ: mã hóa/giải mã, nén ảnh, tính toán mô phỏng, xử lý JSON nặng, inference hoặc chạy thuật toán phân tích.

Dấu hiệu thường gặp:

- CPU utilization của tiến trình hoặc node cao trong thời gian tải; run queue tăng và request chờ CPU.
- Tăng số request đồng thời làm throughput không tăng tương ứng, latency p95/p99 tăng.
- Profiling cho thấy thời gian tập trung ở hàm tính toán, serialization, compression hoặc garbage collection.

Cách xử lý: tối ưu thuật toán và code trước; sau đó kiểm tra loại CPU, số vCPU, hiệu năng đơn nhân, khả năng song song và giới hạn CPU quota. Nhiều vCPU không phải lúc nào cũng giúp ứng dụng single-thread; phần mềm cần có khả năng tận dụng song song.

### 3.2. Memory-bound

Workload **memory-bound** cần dung lượng RAM lớn hoặc băng thông bộ nhớ cao. Ví dụ: cache trong bộ nhớ, xử lý bảng dữ liệu lớn, JVM với heap lớn, phân tích dữ liệu hoặc số lượng worker đồng thời cao.

Dấu hiệu:

- Working set tiến sát giới hạn; process bị OOM hoặc container bị OOMKilled.
- Paging/swap tăng, garbage collection thường xuyên hoặc thời gian pause kéo dài.
- Latency tăng khi dữ liệu lớn hơn cache hoặc khi concurrency tăng.
- RSS/heap tăng dần theo thời gian, có thể gợi ý memory leak.

Sizing bộ nhớ phải tính không chỉ dữ liệu nghiệp vụ mà còn heap/runtime, native memory, thread stack, buffer, cache, sidecar/agent và phần dành cho hệ điều hành. Với container, **memory limit** là giới hạn cứng theo runtime/orchestrator; đặt limit sát mức tiêu thụ cao nhất trong một phép thử ngắn có thể gây OOM khi tải thay đổi.

### 3.3. I/O-bound

Workload **I/O-bound** thường chờ đọc/ghi lưu trữ hoặc chờ phản hồi từ database, queue hay filesystem. CPU có thể thấp trong khi request vẫn chậm.

Chỉ số cần xem:

- IOPS (số thao tác đọc/ghi mỗi giây).
- Throughput (MB/s hoặc GB/s).
- Latency đọc/ghi, đặc biệt p95/p99.
- Queue depth, thời gian chờ I/O, cache hit rate.
- Số kết nối và thời gian query ở database.

Ví dụ: API tra cứu đọc nhiều bản ghi có thể không cần thêm vCPU nếu database đã đạt giới hạn IOPS hoặc query thiếu index. Cần tối ưu query, index, cache, phân vùng dữ liệu hoặc nâng cấp loại/tầng lưu trữ trước khi tăng compute của API.

### 3.4. Network-bound

Workload **network-bound** bị giới hạn bởi băng thông, độ trễ, số kết nối, packet rate hoặc phụ thuộc mạng bên ngoài. Ví dụ: API gọi nhiều dịch vụ SaaS, truyền file lớn, streaming hoặc microservice có số hop cao.

Dấu hiệu:

- CPU thấp nhưng request chờ lâu ở connect/TLS/remote response.
- Network throughput, packet drop, retransmission hoặc số connection tiến sát giới hạn.
- Latency tăng mạnh khi dependency từ xa chậm; connection pool cạn.
- Lỗi timeout, DNS hoặc NAT/egress gateway xuất hiện khi tải cao.

Cần phân biệt **thời gian xử lý trong ứng dụng** với **thời gian chờ mạng**. Xem distributed trace, network metrics, DNS/TLS timings, connection pool và giới hạn của dịch vụ đối tác. Nâng vCPU không sửa được một API ngoài hệ thống đang trả lời chậm.

### 3.5. Bảng so sánh nhanh

| Loại bottleneck | CPU | RAM | I/O/network | Hướng kiểm tra ưu tiên |
|---|---|---|---|---|
| CPU-bound | Thường cao hoặc bị quota | Có thể bình thường | Không phải giới hạn chính | CPU profiling, parallelism, vCPU/clock |
| Memory-bound | Có thể trung bình | Áp sát limit/working set | Có thể tăng do paging | RSS/heap, GC, cache, memory limit |
| Storage/database I/O-bound | Có thể thấp | Có thể bình thường | IOPS/latency/queue depth cao | Query plan, storage tier, IOPS, cache |
| Network-bound | Có thể thấp | Có thể bình thường | Latency/packet/connection/bandwidth | Trace, DNS/TLS, egress, pool, dependency |

Không dùng một chỉ số riêng lẻ để kết luận bottleneck. Ví dụ CPU cao có thể là hệ quả của retry storm do database chậm; RAM cao có thể là cache hợp lý chứ không phải rò rỉ bộ nhớ. Cần đối chiếu metrics, traces, logs và thử nghiệm có kiểm soát.

## 4. Đo trước khi chọn cấu hình

### 4.1. Số liệu cần thu thập

Đo ở cả cấp **ứng dụng**, **tiến trình/container/VM** và **dịch vụ phụ thuộc**.

| Lớp | Metrics hữu ích |
|---|---|
| Request | Request/s, throughput, số request in-flight, lỗi theo loại, p50/p95/p99 latency |
| CPU | Utilization, throttling, load/run queue, CPU time theo process |
| Memory | Working set/RSS, heap, cache, allocation rate, GC pause, OOM |
| Disk/storage | IOPS, throughput, read/write latency, queue depth, dung lượng và tăng trưởng |
| Network | Bytes/s, packets/s, packet loss/retransmit, connection count, connect/TLS time |
| Runtime | Thread count, event-loop lag, connection pool, queue backlog, worker concurrency |
| Dependency | Database query latency, DB connections, cache hit rate, API đối tác latency/error |

Đo theo cùng khoảng thời gian và gắn metadata như phiên bản ứng dụng, loại instance, AZ, workload, số replica và mức tải. Nếu chỉ nhìn dashboard trung bình theo 5 phút, các spike kéo dài vài giây có thể bị che khuất; chọn độ phân giải metric phù hợp với loại sự cố cần phát hiện.

### 4.2. Phân vị độ trễ quan trọng hơn số trung bình

- **p50** mô tả trải nghiệm của request ở giữa phân bố.
- **p95** cho thấy 5% request chậm nhất vượt ngưỡng này.
- **p99** giúp nhìn phần đuôi chậm, thường quan trọng với giao dịch cần phản hồi nhanh.

Ví dụ p50 = 80 ms, p95 = 250 ms nhưng p99 = 3 giây có thể cho thấy một nhóm request bị chậm do query lớn, GC pause, cold start hoặc dependency timeout. Chỉ báo cáo “latency trung bình 100 ms” sẽ che mất trải nghiệm của nhóm người dùng này.

### 4.3. Đo tải đồng thời

Throughput và concurrency có liên hệ qua định luật Little:

\[
L = \lambda W
\]

Trong đó:

- \(L\) là số request trung bình đang ở trong hệ thống (concurrency).
- \(\lambda\) là throughput trung bình (request/giây).
- \(W\) là thời gian trung bình một request ở trong hệ thống (giây).

Ví dụ, nếu API xử lý 200 request/giây và thời gian trung bình trong hệ thống là 0,25 giây, concurrency trung bình xấp xỉ:

\[
L = 200 \times 0{,}25 = 50
\]

Đây chỉ là quan hệ ở trạng thái ổn định và dùng **latency trung bình**, không phải p95. Nó giúp ước lượng ban đầu số request đang chờ/được xử lý, nhưng không tự cho biết cần bao nhiêu vCPU hay RAM. Phải kết hợp thời gian CPU thực tế mỗi request, bộ nhớ mỗi request, I/O và mức song song của ứng dụng.

## 5. Ước lượng cấu hình CPU và bộ nhớ ban đầu

### 5.1. Ước lượng CPU từ thời gian CPU mỗi request

Nếu đã đo được một request sử dụng trung bình \(t_{cpu}\) giây CPU, throughput mục tiêu là \(R\) request/giây, thì số core CPU tiêu thụ lý tưởng gần đúng:

\[
C_{\text{needed}} = R \times t_{cpu}
\]

Ví dụ: benchmark cho thấy mỗi request dùng 0,012 giây CPU; mục tiêu tải là 300 request/giây:

\[
C_{\text{needed}} = 300 \times 0{,}012 = 3{,}6 \text{ core}
\]

Nếu tổ chức chọn mục tiêu utilization CPU khoảng 60% ở tải mục tiêu, ước lượng ban đầu là:

\[
C_{\text{provisioned}} \approx \frac{3{,}6}{0{,}60}=6 \text{ vCPU}
\]

Đây là phép tính sơ bộ cho **một workload với giả định benchmark đại diện**. Cần cộng nhu cầu của agent/sidecar, tác vụ nền, burst, overhead runtime và xem hệ số utilization có phù hợp với latency mục tiêu. Nếu đặt mục tiêu 60%, điều đó không có nghĩa CPU 60% luôn tối ưu cho mọi ứng dụng; chọn dựa trên đo p95/p99 và khả năng chịu lỗi.

### 5.2. Ước lượng bộ nhớ

Một mô hình dự toán cơ bản:

\[
M_{\text{total}} =
M_{\text{runtime}}+
M_{\text{working set}}+
M_{\text{concurrency}}+
M_{\text{cache}}+
M_{\text{sidecars}}+
M_{\text{headroom}}
\]

Trong đó các khoản phải được đo hoặc ước lượng từ cấu hình runtime. Với Java, cần phân biệt **heap** với **RSS/total process memory**: heap không bao phủ metaspace, code cache, direct/native buffers, thread stacks và thư viện native. Với container, hãy xác minh tổng bộ nhớ có thể dùng dưới memory limit thực tế.

Ví dụ: ứng dụng đo được runtime và native overhead 450 MB, working set 1,1 GB, cache 0,8 GB, concurrency buffers 0,3 GB, sidecar 0,2 GB. Tổng nền là 2,85 GB. Nếu dành 25% headroom trên mức nền, dự toán khoảng 3,56 GB; có thể thử cấu hình 4 GB để benchmark và kiểm tra spike. Con số này là **minh họa**, không phải khuyến nghị sizing chung.

Headroom phải xét theo **kịch bản đỉnh và mức tăng trưởng**, không chỉ thêm tỷ lệ vào mức trung bình. Theo dõi OOM, RSS, allocation và GC trong soak test để phát hiện memory leak hoặc tăng trưởng theo thời gian.

### 5.3. Đơn nhân, đa nhân và kiến trúc CPU

Hai loại máy có cùng số vCPU không nhất thiết có hiệu năng như nhau. Cần kiểm tra:

- Thế hệ CPU, hiệu năng mỗi vCPU, mức xung/kiến trúc và hiệu ứng burst nếu là máy burstable.
- Ứng dụng có song song hóa tốt không; một thread bị nghẽn có thể không tận dụng hết nhiều vCPU.
- Hệ số chia sẻ CPU/oversubscription và quota trong container/orchestrator.
- Khả năng tương thích instruction set, runtime và thư viện native.
- Giá mỗi giờ/đơn vị compute, giới hạn vùng và khả năng mua/reserve capacity.

Nên chọn vài cấu hình ứng viên từ nhỏ đến lớn trong cùng dòng, benchmark trên workload tương đương và so **cost per request/job hoàn thành** thay vì chỉ so giá mỗi giờ.

## 6. Sizing I/O, lưu trữ và mạng

### 6.1. Disk và storage I/O

Tính nhu cầu từ cả **throughput** và **IOPS**. Một file lớn đọc tuần tự có thể cần throughput cao nhưng IOPS thấp; database nhiều transaction nhỏ có thể cần IOPS và latency thấp dù throughput MB/s không lớn.

| Workload | Nhu cầu điển hình | Câu hỏi sizing |
|---|---|---|
| Database OLTP | Nhiều thao tác đọc/ghi nhỏ, latency thấp, IOPS ổn định | Peak IOPS? Write amplification? Dung lượng log/WAL? |
| Data warehouse/analytics | Scan file lớn, throughput cao | MB/s cần thiết? Có thể dùng object storage/columnar format? |
| File/media processing | Đọc/ghi file dung lượng lớn | Kích thước file, số job song song, shared storage hay ephemeral? |
| Cache | Truy cập nhanh, working set giữ trong RAM hoặc storage chuyên dụng | Hit rate, eviction, durability và khả năng warm-up? |
| Batch | Nhiều file hoặc dữ liệu theo đợt | Cửa sổ xử lý, tổng bytes, số worker và thời gian hoàn thành? |

Cần xem giới hạn IOPS/throughput của volume, instance, filesystem, database và mạng cùng lúc. Tăng IOPS của volume sẽ không giúp nếu instance giới hạn bandwidth hoặc database chỉ có thể xử lý ít connection.

### 6.2. Network và connection

Ước lượng lưu lượng:

\[
B_{\text{network}} \approx R \times S_{\text{avg}}
\]

Với \(R\) là request/giây và \(S_{avg}\) là tổng byte truyền trung bình cho mỗi request (cần xem cả inbound và outbound theo đúng hướng). Ví dụ 300 request/giây, tổng dữ liệu phản hồi trung bình 40 KB/request tạo ra khoảng 12.000 KB/s, xấp xỉ 12 MB/s trước khi tính overhead, TLS, retry và các traffic nền.

Đối với connection, hãy tính:

- Số connection đồng thời đến database, cache và API bên ngoài.
- Kích thước pool theo replica: **tổng pool tối đa = pool mỗi replica × số replica**. Autoscaling tăng replica có thể làm database vượt connection limit.
- Timeout, keepalive, retry, DNS/TLS handshake, ephemeral ports và giới hạn NAT/egress nếu có.
- Throughput thực tế và giới hạn băng thông theo loại instance/network interface.

Một thiết kế API scale từ 4 lên 30 replica có thể gây 30 lần số connection pool nếu mỗi replica có pool cố định. Cần đặt giới hạn concurrency/pool toàn hệ thống, dùng pooling phù hợp và xác minh database chịu được tải sau scale-out.

## 7. Quy trình benchmark và kiểm thử tải

Không nên chọn máy dựa trên con số quảng cáo hoặc một lần chạy benchmark thiếu kiểm soát. Hãy xây quy trình lặp lại:

1. **Định nghĩa mục tiêu:** throughput, p95/p99 latency, tỷ lệ lỗi, thời gian xử lý job, mức tải và thời hạn hoàn thành.
2. **Tạo dữ liệu đại diện:** kích thước payload, working set, phân bố key, cache hit/miss và số lượng tenant gần với thực tế.
3. **Cố định biến thử nghiệm:** cùng phiên bản ứng dụng, runtime, region, network, database tier, số replica và tool tạo tải.
4. **Warm-up:** tránh kết luận từ cold cache/JIT initialization nếu production có warm-up; nhưng cũng cần đo riêng cold start nếu đó là kịch bản thực tế.
5. **Tăng tải theo bậc:** từ baseline đến expected peak và stress level; ghi lại điểm throughput không tăng nữa hoặc latency vượt SLO.
6. **So sánh cấu hình:** thay đổi CPU/RAM/I/O từng yếu tố có chủ đích để hiểu tác động; không đổi đồng thời quá nhiều biến.
7. **Soak test:** chạy đủ lâu để phát hiện memory leak, file descriptor leak, cache churn và suy giảm theo thời gian.
8. **Failure/load test:** kiểm tra mất một replica/AZ, dependency chậm, retry, queue backlog và khả năng scale-out.
9. **Ghi kết quả và chi phí:** p50/p95/p99, throughput, lỗi, CPU, RSS, I/O, network và chi phí cho cùng lượng công việc hoàn thành.

### 7.1. Các kiểu kiểm thử khác nhau

| Loại test | Mục tiêu | Cách tạo tải |
|---|---|---|
| **Load test** | Xác minh mục tiêu tải dự kiến | Duy trì tải mục tiêu trong khoảng thời gian đủ dài |
| **Stress test** | Tìm giới hạn và cách hệ thống suy giảm | Tăng vượt tải mục tiêu đến khi lỗi hoặc không còn tăng throughput |
| **Spike test** | Xác minh phản ứng trước tăng tải đột ngột | Tăng nhanh từ nền thấp lên tải cao |
| **Soak/endurance test** | Phát hiện rò rỉ hoặc suy giảm lâu dài | Giữ tải ổn định trong nhiều giờ hoặc theo chu kỳ phù hợp |
| **Capacity test** | Xác định capacity thực của cấu hình | Tăng tải có kiểm soát, đo điểm đạt SLO cuối cùng |
| **Failover test** | Xác minh năng lực còn lại khi mất tài nguyên | Cô lập replica/AZ/dependency theo kế hoạch |

Mỗi phép thử phải có **tiêu chí dừng** để tránh vô tình làm cạn database, gửi giao dịch thật hoặc ảnh hưởng dịch vụ dùng chung. Dùng sandbox và dữ liệu tổng hợp khi có thể; nếu thử production, phải có phê duyệt và giới hạn tác động.

### 7.2. Kết quả benchmark mẫu

Giả sử một API được thử trên ba cấu hình compute, cùng database và cùng bộ tải 250 request/giây:

| Cấu hình thử | CPU p95 | RAM peak | API p95 latency | Error rate | Chi phí tương đối/giờ |
|---|---:|---:|---:|---:|---:|
| 2 vCPU / 4 GB | 92% | 3,4 GB | 720 ms | 1,8% | 1,0 |
| 4 vCPU / 8 GB | 61% | 3,6 GB | 280 ms | 0,15% | 1,9 |
| 8 vCPU / 16 GB | 34% | 3,8 GB | 250 ms | 0,10% | 3,6 |

Đây là **số liệu giả lập cho bài tập**. Nếu SLO là p95 dưới 300 ms và error rate dưới 0,2%, cấu hình 4 vCPU/8 GB đáp ứng ở tải thử với mức chi phí thấp hơn cấu hình 8 vCPU/16 GB. Cấu hình lớn hơn giảm latency thêm 30 ms nhưng chi phí gần gấp đôi; cần cân nhắc headroom, burst và kịch bản mất một replica trước khi kết luận.

Đừng quên benchmark này chỉ đo API và database trong điều kiện cụ thể. Nếu database, queue hoặc bên thứ ba có tải khác ở production, kết quả có thể không lặp lại.

## 8. Chọn loại compute và cấu hình triển khai

Sizing phụ thuộc mô hình compute vì mỗi lựa chọn có cách định nghĩa giới hạn khác nhau:

| Mô hình | Đơn vị sizing | Đặc điểm | Rủi ro cần kiểm tra |
|---|---|---|---|
| VM | vCPU, RAM, disk, network bandwidth | Toàn quyền OS hơn, có thể tùy biến runtime | Vá lỗi, capacity, cấu hình OS, scaling và HA |
| Container service | CPU/memory request, limit, replica, node capacity | Đóng gói workload và scale theo service | CPU throttling, OOM, bin packing, node pressure |
| Kubernetes | Pod requests/limits, node type/count, autoscaler | Điều phối nhiều service và workload khác nhau | Request/limit sai, scheduler không đặt được pod, node pool thiếu capacity |
| Serverless function | Memory/CPU profile theo mức cấp phát, timeout, concurrency/quota | Không quản lý máy chủ, phù hợp xử lý event/API theo mô hình hỗ trợ | Cold start, concurrency, timeout, memory, giới hạn execution |
| Batch/job | CPU/RAM/job, parallelism, I/O và thời gian hoàn thành | Tối ưu xử lý theo đợt, có thể dùng tài nguyên tạm | Job bị retry, dữ liệu trung gian, deadline, interruption |

### 8.1. Request và limit của container

Trong một orchestrator như Kubernetes:

- **CPU request** hỗ trợ scheduler bố trí pod; **CPU limit** có thể làm workload bị throttling khi vượt giới hạn.
- **Memory request** ảnh hưởng việc lập lịch; **memory limit** có thể khiến container bị OOMKilled nếu sử dụng vượt.
- Đặt request quá thấp gây node overcommit và contention; đặt quá cao làm scheduler không tìm đủ node, giảm hiệu suất sử dụng tài nguyên.
- Cần đo usage theo phân vị, tải peak và overhead sidecar trước khi xác định request/limit.

Ví dụ cấu hình minh họa:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "768Mi"
  limits:
    cpu: "1500m"
    memory: "1536Mi"
```

Các giá trị trên **không phải cấu hình khuyến nghị chung**; phải dựa trên profiler và load test. Cũng cần xác minh cách runtime/orchestrator xử lý CPU limit, memory enforcement và loại QoS của pod.

### 8.2. JVM và container memory

Với ứng dụng Java, `-Xmx` không nên bằng toàn bộ memory limit của container. Tổng RSS có thể gồm heap, metaspace, code cache, thread stacks, direct buffers, native libraries và agent. Nếu container có limit 2 GiB nhưng heap được đặt sát 2 GiB, process dễ bị OOM dù heap chưa chạm Xmx.

Hãy đo heap occupancy, GC pause, allocation rate, native memory và RSS ở tải đỉnh. Thử số thread/concurrency thực tế; tăng thread có thể làm tăng stack memory và context switching. Cấu hình runtime nên để lại phần headroom phù hợp và được kiểm chứng bằng soak test.

## 9. Autoscaling, headroom và năng lực khi có sự cố

### 9.1. Autoscaling không thay thế sizing

Autoscaling điều chỉnh số lượng tài nguyên khi tín hiệu tải thay đổi, nhưng vẫn cần **capacity nền, tốc độ mở rộng, quota, thời gian khởi động và giới hạn dependency**.

| Cách scale | Tín hiệu phù hợp | Điều cần lưu ý |
|---|---|---|
| CPU-based | Workload compute-bound, CPU tương quan với throughput | Không tốt nếu CPU thấp nhưng request chờ DB/network |
| Memory-based | Workload có working set thay đổi theo tải | Scale-out không nhất thiết giải phóng memory ở replica hiện có |
| Request/concurrency-based | API xử lý request độc lập | Chọn metric phản ánh khả năng phục vụ và concurrency an toàn |
| Queue-depth-based | Worker xử lý sự kiện/job | Kết hợp backlog, tốc độ xử lý và deadline từng job |
| Scheduled | Tải có chu kỳ dự đoán được | Cần điều chỉnh khi hành vi tải thay đổi |

### 9.2. Capacity và headroom

Nếu có hai replica bình thường, mỗi replica xử lý 50% tải, khi một replica mất thì replica còn lại có thể phải xử lý toàn bộ. Năng lực sau mất một phần tử không thể chỉ tính theo công suất toàn cụm ở trạng thái bình thường.

Một cách ước lượng:

\[
C_{\text{surviving}} \geq D_{\text{peak}}
\]

Trong đó \(C_{surviving}\) là tổng năng lực của các replica còn sống ở kịch bản lỗi được yêu cầu và \(D_{peak}\) là tải đỉnh cần đáp ứng. Nếu mục tiêu chỉ duy trì chức năng cốt lõi ở chế độ suy giảm, phải định nghĩa rõ phần nào bị tắt hoặc giảm chất lượng.

Đối với multi-AZ, thử mất một AZ và xác minh capacity còn lại, database connections, queue consumers, cache warm-up và egress. Với nhiều region, cần thêm dung lượng region DR, quota và cách promote dữ liệu phù hợp.

### 9.3. Tránh scaling gây hỏng dependency

Ví dụ API scale từ 5 lên 50 replica, mỗi replica mở pool database tối đa 30 connection. Số connection lý thuyết có thể tăng từ 150 lên 1.500, vượt giới hạn database. Trước khi scale-out, hãy tính tổng connection theo replica, giữ pool hợp lý, dùng connection proxy/pooling nếu phù hợp và đặt giới hạn concurrency ở ứng dụng.

Scaling quá nhanh cũng có thể tạo cold start, cache miss đồng loạt, surge tải database và retry storm. Cần thiết kế rate limit, queue, jitter/backoff, circuit breaker và quy trình warm-up.

## 10. Ví dụ xuyên suốt: sizing API đặt lịch

Giả sử hệ thống có API đặt lịch và worker gửi email:

- Tải dự kiến: 200 request/giây thông thường, 300 request/giây ở peak.
- Benchmark cho thấy một request dùng trung bình 0,01 giây CPU và working set của mỗi replica khoảng 1,2 GB ở concurrency mục tiêu.
- API cần p95 dưới 300 ms; worker xử lý email bất đồng bộ.
- Yêu cầu vận hành: nếu một replica hoặc một AZ mất, các replica còn lại phải tiếp tục phục vụ giao dịch cốt lõi.

### 10.1. Ước lượng CPU cho API

\[
C_{needed}=300 \times 0{,}01 = 3 \text{ core}
\]

Nếu nhắm tới 60% utilization ở tải đỉnh:

\[
C_{provisioned}=\frac{3}{0{,}60}=5 \text{ vCPU}
\]

Đội có thể thử cấu hình 2 replica × 3 vCPU (tổng 6 vCPU) ở baseline. Nhưng nếu mục tiêu là **sau khi mất một replica vẫn đáp ứng peak**, mỗi replica còn lại phải tự xử lý tải 300 RPS. Khi đó cần tối thiểu khoảng 5 vCPU theo giả định trên cho replica sống sót, trước overhead và headroom; tổng năng lực cấu hình bình thường có thể phải cao hơn. Nếu phân bố trên hai AZ và mỗi AZ chỉ có một replica, cần sizing mỗi replica theo tình huống mất AZ hoặc chấp nhận chế độ suy giảm đã phê duyệt.

### 10.2. Ước lượng bộ nhớ

Giả định working set 1,2 GB/replica, runtime/native overhead 0,45 GB, sidecar 0,15 GB và headroom 25%:

\[
M=(1{,}2+0{,}45+0{,}15)\times1{,}25=2{,}25\text{ GB}
\]

Cấu hình thử ban đầu có thể là 3 GB hoặc mức gần nhất được nền tảng hỗ trợ, rồi kiểm tra RSS, GC và OOM ở concurrency đỉnh. Nếu cache tăng theo số request hoặc dữ liệu giữ lâu hơn, dự toán phải được cập nhật.

### 10.3. Worker cần sizing khác API

Worker email xử lý công việc I/O-bound nhiều hơn CPU-bound, thời gian chờ provider có thể dài. Vì vậy, nên sizing theo **queue backlog, thời gian xử lý trung bình và deadline**. Nếu một worker xử lý được 8 message/giây ở p95 latency cho phép và queue nhận 40 message/giây, cần tối thiểu 5 worker về throughput lý tưởng; nên thử mức cao hơn để có headroom và cần kiểm tra rate limit của provider.

Scaling worker không được tạo retry storm. Message lỗi cần backoff và DLQ; thao tác gửi email nên idempotent theo booking/event ID để xử lý trường hợp nhận message trùng.

### 10.4. Kết quả quyết định ban đầu

| Thành phần | Cấu hình thử | Lý do | Điều kiện phải xác minh |
|---|---|---|---|
| Booking API | Managed container, 2 replica phân bố AZ; mỗi replica thử 5–6 vCPU, 3 GB RAM | Tính theo peak và kịch bản mất replica | Benchmark một replica xử lý 300 RPS; p95/error rate; memory/GC |
| Email worker | Scale riêng theo queue, cấu hình CPU vừa phải, RAM theo số message in-flight | Workload chủ yếu chờ mạng/provider | Message/s, backlog, timeout, rate limit, duplicate |
| Database | Chọn tier theo query/connection/IOPS và HA phù hợp | Compute API không giải quyết database bottleneck | Slow query, connection limit, failover, backup/restore |
| Cache (nếu có) | Working set và hit rate đo được | Giảm truy vấn lặp nếu dữ liệu cho phép | Memory eviction, consistency, warm-up, HA |

Đây là **điểm bắt đầu để thử nghiệm**, không phải đáp án cấu hình production. Cần đo lại bằng dữ liệu đại diện, giá và giới hạn thực tế ở region triển khai, sau đó cập nhật sizing theo kết quả.

## 11. Cost optimization: so năng lực với chi phí

Không nên tối ưu bằng cách chỉ chọn instance rẻ nhất. So sánh các ứng viên theo:

- **Cost per unit of work:** chi phí trên mỗi 1.000 request thành công, mỗi job, mỗi GB xử lý.
- **Utilization và hiệu năng:** CPU/RAM dư hay thiếu, throughput, p95/p99 và error rate.
- **Chi phí nền:** tài nguyên luôn chạy, license, storage, network, NAT, logs, monitoring.
- **Chi phí dự phòng:** bản sao đa AZ, capacity DR, quota và chi phí chạy khi mất tài nguyên.
- **Chi phí vận hành:** giờ kỹ sư, cập nhật hệ điều hành/runtime, trực sự cố, nâng cấp và điều tra lỗi.

### 11.1. Ví dụ cost per 1.000 request

Giả sử hai phương án đạt cùng chức năng và thời gian thử nghiệm:

| Cấu hình | Chi phí/tháng giả định | Request thành công/tháng | Chi phí/1.000 request |
|---|---:|---:|---:|
| A: nhiều replica nhỏ | 9 triệu đồng | 20 triệu | 450 đồng |
| B: ít replica lớn hơn | 7,5 triệu đồng | 20 triệu | 375 đồng |

Số liệu là **ví dụ minh họa**. Nếu cấu hình B có p99 latency cao khi mất một replica hoặc không đáp ứng AZ failure, nó có thể không thỏa yêu cầu reliability dù chi phí đơn vị thấp hơn. Cần so sánh trong cùng một SLO và cùng kịch bản tải.

### 11.2. Right-sizing theo vòng đời

- **Downsize** khi utilization thấp kéo dài và SLO vẫn có headroom; theo dõi trước và sau thay đổi.
- **Upsize** khi đã xác nhận bottleneck là năng lực tài nguyên chứ không phải query, lock, retry hoặc dependency.
- **Scale-to-zero/tắt theo lịch** với dev/test/batch nếu thời gian khởi động và yêu cầu availability cho phép.
- **Dùng thế hệ/loại compute phù hợp** khi benchmark chứng minh hiệu năng tốt hơn và tương thích runtime.
- **Rà soát định kỳ** sau khi tải, code, runtime, database hoặc mô hình traffic thay đổi.

Không tự động giảm cấu hình production chỉ dựa trên CPU trung bình. Hãy xem p95/p99, peak, failover capacity, memory, I/O, queue backlog và các cửa sổ tải hiếm.

## 12. Well-Architected và vận hành sizing

| Trụ cột | Câu hỏi khi sizing |
|---|---|
| **Operational Excellence** | Có baseline, dashboard, alert, load-test định kỳ và owner theo dõi capacity? Có thể tái tạo cấu hình qua IaC? |
| **Security** | Agent, sidecar, encryption và logging có nằm trong dự toán tài nguyên? Quota/limit có ngăn resource exhaustion? |
| **Reliability** | Hệ thống còn đủ năng lực sau khi mất instance/AZ? Database/queue/network có chịu được scale-out? |
| **Performance Efficiency** | CPU, RAM, IOPS, throughput và latency được đo theo workload thực tế? Có so cost per unit? |
| **Cost Optimization** | Có right-size, tắt non-prod, ngân sách, reservation/commitment phù hợp và dự toán tải tăng? |
| **Sustainability** | Có giảm tài nguyên nhàn rỗi, tránh overprovision và sử dụng phần cứng hiệu quả mà vẫn đạt SLO? |

Sizing là **quy trình liên tục** chứ không phải thao tác một lần trước production. Khi traffic tăng, endpoint thêm, truy vấn đổi hoặc ứng dụng chuyển runtime, đặc tính tài nguyên cũng thay đổi. Cần theo dõi và điều chỉnh dựa trên số liệu.

### 12.1. Dashboard tối thiểu cho capacity

Một dashboard theo từng service/environment nên có:

- Request rate, concurrent request, p50/p95/p99 latency và error rate.
- CPU utilization/throttling và CPU time theo replica.
- RSS/working set/heap, GC pause, OOM/restart.
- Disk IOPS/throughput/latency và dung lượng.
- Network bytes/packets, connection count, retransmission và timeout.
- Database connection/query latency, queue depth/backlog, cache hit rate.
- Replica/node count, autoscaling events, quota, capacity sau AZ failure.
- Chi phí theo service, môi trường và đơn vị công việc.

Alert phải dựa trên **triệu chứng ảnh hưởng dịch vụ** và ngưỡng tài nguyên có liên quan. CPU 85% trong một phút có thể không đáng báo động nếu SLO tốt và burst ngắn; ngược lại p99 tăng mạnh, error rate và queue backlog cùng tăng là dấu hiệu cần xử lý ngay.

## 13. Mẫu hồ sơ sizing và bảng kiểm

Mẫu YAML dưới đây dùng để lưu **giả định và kế hoạch xác minh**. Tên trường là ví dụ cho tài liệu dự án, không phải schema chuẩn của nhà cung cấp cloud:

```yaml
service: booking-api
environment: production
workload_profile:
  steady_rps: 200
  peak_rps: 300
  payload_avg_kb: 20
  target_p95_ms: 300
  failure_scenario: one_replica_or_az_unavailable
resource_hypothesis:
  compute:
    vcpu_per_replica: 5
    replica_count: 2
  memory:
    gb_per_replica: 3
  storage:
    iops: pending_benchmark
  network:
    egress_allowlist: approved_dependencies
measurements:
  cpu_seconds_per_request: 0.01
  working_set_gb: 1.2
assumptions:
  - "Representative workload and database response time are validated"
verification:
  - "Peak load test"
  - "p95/p99 latency and error rate"
  - "One replica/AZ failure capacity"
  - "Database connection and I/O saturation"
review_trigger:
  - "Traffic increases beyond forecast"
  - "Runtime or major dependency changes"
  - "SLO or budget changes"
```

Các giá trị trong ví dụ chỉ là giả định từ bài toán đặt lịch. Không biến chúng thành cấu hình thật nếu chưa benchmark và chưa duyệt ngân sách.

### Bảng kiểm trước khi phê duyệt cấu hình

- [ ] Đã mô tả steady, peak, burst, concurrency và tăng trưởng theo kỳ.
- [ ] Đã xác định bottleneck bằng metrics/traces/profiling, phân biệt CPU, RAM, I/O, network và dependency.
- [ ] Đã đo p50/p95/p99 latency, throughput và error rate trên dữ liệu đại diện.
- [ ] Cấu hình CPU/RAM tính cả runtime, sidecar, concurrency và headroom.
- [ ] Disk sizing có cả IOPS, throughput, latency và dung lượng; network có throughput/connection/egress.
- [ ] Đã kiểm tra pool/concurrency và quota ở database, queue, NAT, endpoint và dịch vụ phụ thuộc.
- [ ] Có load/stress/spike/soak/failover test phù hợp; tiêu chí dừng và vùng thử an toàn rõ ràng.
- [ ] Autoscaling có tín hiệu phù hợp, giới hạn, capacity nền và kế hoạch khi scale-out chậm.
- [ ] Kịch bản mất replica/AZ vẫn đáp ứng mục tiêu đã được phê duyệt hoặc có chế độ suy giảm rõ ràng.
- [ ] Đã so cost per unit of work và TCO trong cùng điều kiện SLO.
- [ ] Có dashboard, alert, IaC, người chịu trách nhiệm và trigger để sizing lại.

**Nguyên tắc áp dụng:** chọn cấu hình theo **workload được đo**, kiểm chứng ở tải và sự cố cần chịu, sau đó so sánh chi phí trên cùng mục tiêu chất lượng. CPU, bộ nhớ, I/O và mạng phải được nhìn như một hệ thống phụ thuộc; tăng một loại tài nguyên chỉ hữu ích khi nó xử lý đúng bottleneck đã xác định.
