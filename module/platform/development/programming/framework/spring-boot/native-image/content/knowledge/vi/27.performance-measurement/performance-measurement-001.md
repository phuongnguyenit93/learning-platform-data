# Xác định mục tiêu trước khi so sánh JVM với native

## Mục tiêu bài học

Biên dịch ứng dụng Spring Boot thành **GraalVM Native Image** có thể giúp giảm thời gian khởi động và mức sử dụng bộ nhớ trong một số workload. Tuy nhiên, native executable không mặc định nhanh hơn JVM ở mọi chỉ số. Ứng dụng chạy lâu, có tải ổn định và được JVM JIT tối ưu có thể có throughput hoặc latency khác với native; native cũng có chi phí build, yêu cầu tương thích và quy trình vận hành riêng.

Vì vậy, trước khi benchmark, cần xác định rõ hệ thống muốn cải thiện điều gì và điều kiện nào được giữ nguyên. Một phép đo có ích phải trả lời câu hỏi vận hành hoặc kinh doanh, chẳng hạn giảm thời gian scale-out, tăng mật độ container trên node, giảm memory limit hay giảm chi phí cho một workload cụ thể.

Bài học này giúp bạn:

- Chuyển nhu cầu sử dụng Native Image thành mục tiêu và giả thuyết có thể đo.
- Chọn workload đại diện cho cách ứng dụng Spring Boot thực sự được triển khai.
- Xác định các chỉ số startup, memory, throughput, latency, CPU và chi phí.
- Phân biệt cold start, warm-up và steady-state.
- Thiết kế phép so sánh JVM và native công bằng, có thể lặp lại.
- Đặt tiêu chí quyết định trước khi xem kết quả benchmark.

## 1. Bắt đầu từ vấn đề cần giải quyết

### 1.1. Native Image là một lựa chọn kiến trúc

Native Image thay đổi cách ứng dụng được build và chạy. Với Spring Boot, Spring AOT chuẩn bị mã bootstrap và metadata; GraalVM Native Image phân tích reachability rồi biên dịch executable cho target platform.

Lợi ích thường được quan tâm:

- Khởi động process nhanh hơn trong môi trường cần tạo instance thường xuyên.
- Giảm memory footprint trong một số ứng dụng và workload.
- Tăng số instance có thể chạy trên cùng node khi memory là giới hạn chính.
- Phù hợp với workload ngắn hạn, scale-to-zero hoặc scale-out nhanh.

Các chi phí và đánh đổi cần đưa vào quyết định:

- Native compilation thường mất nhiều thời gian và tài nguyên build hơn.
- Binary phụ thuộc OS, CPU architecture và thư viện native của target.
- Một số thư viện hoặc hành vi động cần reachability metadata, Runtime Hints hoặc thay đổi thiết kế.
- Hiệu năng steady-state có thể khác JVM đã warm-up và JIT tối ưu.
- Debugging, profiling, observability và quy trình phát hành cần được xác minh trên native.

Không chọn native chỉ vì một con số startup trong ví dụ hoặc vì executable có kích thước nhỏ. Hãy xác định lợi ích đó có cải thiện hệ thống thật hay không.

### 1.2. Viết mục tiêu dưới dạng câu hỏi đo được

Một mục tiêu tốt có ba thành phần: **đối tượng**, **chỉ số** và **điều kiện**.

Ví dụ:

| Nhu cầu | Câu hỏi benchmark |
|---|---|
| Scale-out chậm | Native có giảm thời gian từ lúc tạo process tới readiness khi cùng cấu hình container không? |
| Node thiếu RAM | Native có giảm RSS tại tải mục tiêu và tăng số replica trên node không? |
| Workload ngắn hạn | Native có xử lý cùng số request trong vòng đời ngắn với tổng chi phí thấp hơn không? |
| API tải ổn định | Native có giữ throughput và p95/p99 latency trong ngưỡng SLO sau warm-up không? |
| Chi phí hạ tầng | Với cùng workload và SLO, chi phí compute trên mỗi request thành công thay đổi thế nào? |
| Build pipeline chậm | Thời gian native compilation có làm ảnh hưởng cadence phát hành hoặc chi phí CI không? |

Các câu hỏi này khác nhau và có thể dẫn tới kết luận khác nhau. Một native executable có thể thắng về readiness nhưng không đạt yêu cầu throughput của một API chạy liên tục.

### 1.3. Xác định ưu tiên và ngưỡng chấp nhận

Trước khi chạy benchmark, ghi lại:

- Chỉ số quan trọng nhất.
- SLO hoặc ngưỡng hiện tại của hệ thống.
- Mức cải thiện tối thiểu có ý nghĩa.
- Mức suy giảm tối đa có thể chấp nhận ở các chỉ số phụ.
- Chi phí build và vận hành tăng thêm có được chấp nhận không.

Ví dụ, mục tiêu có thể là giảm RSS tại tải mục tiêu ít nhất 20%, đồng thời throughput không giảm quá 5% và p95 vẫn nằm trong SLO. Các con số này chỉ là ví dụ để minh họa cách đặt ngưỡng; hãy dùng số liệu và ngân sách thực tế của hệ thống.

## 2. Chọn workload đại diện

### 2.1. Phân loại theo vòng đời ứng dụng

Trước hết, xác định ứng dụng thuộc nhóm nào:

| Loại workload | Đặc điểm | Chỉ số thường quan trọng |
|---|---|---|
| Short-lived job | Khởi động, xử lý một lượng việc nhỏ rồi thoát | Startup, thời gian hoàn tất, memory peak |
| Scale-to-zero service | Có thể không có instance trong một khoảng thời gian | Cold start, readiness, first-request latency |
| Bursty API | Tải đến theo đợt, replica tăng/giảm theo nhu cầu | Startup, scale-out time, latency khi tăng tải |
| Long-running API | Chạy liên tục với tải tương đối ổn định | Throughput, p95/p99, CPU, memory, GC |
| Memory-constrained service | Bị giới hạn RAM hoặc mật độ pod | RSS, peak memory, số replica/node |
| Background worker | Nhận message hoặc job trong thời gian dài | Throughput xử lý, queue lag, memory, shutdown |

Không nên dùng một workload tổng hợp duy nhất để đại diện cho mọi loại ứng dụng. Nếu production có cả cold-start và steady-state, cần đo riêng hai chế độ.

### 2.2. Mô tả workload bằng số liệu

Ghi lại các đặc điểm tối thiểu:

- Số request/message mỗi giây và phân bố theo thời gian.
- Tỷ lệ request đọc/ghi và kích thước payload.
- Số lượng tenant, loại dữ liệu và kích thước dataset.
- Tỷ lệ cache hit/miss.
- Số kết nối database, cache, message broker và dịch vụ ngoài.
- Mức concurrency và cách client phát tải.
- Thời gian sống trung bình của một instance.
- Số replica tối thiểu/tối đa và cách autoscaler hoạt động.

Nếu không có production trace, dùng workload được tổng hợp từ contract/API và dữ liệu đã ẩn danh. Ghi rõ giả định để người khác có thể tái lập phép đo.

### 2.3. Chọn các kịch bản tải

Một bộ kịch bản cơ bản:

1. **Cold start:** khởi chạy process mới và đo đến readiness.
2. **First request:** gửi request đầu tiên sau readiness để phát hiện chi phí khởi tạo lazy.
3. **Warm-up:** tăng tải theo lộ trình để JVM có thời gian JIT compile.
4. **Steady-state:** giữ tải ổn định đủ lâu để quan sát throughput, latency và memory.
5. **Burst:** tăng nhanh concurrency để xem khả năng đáp ứng khi tải đột biến.
6. **Soak:** chạy đủ lâu để quan sát memory growth, cache, queue và hành vi GC.
7. **Scale-out/scale-in:** tạo và dừng instance theo kịch bản triển khai thực tế.

Không phải ứng dụng nào cũng cần cả bảy kịch bản. Chọn các kịch bản tương ứng mục tiêu đã đặt ở phần đầu.

## 3. Xây dựng giả thuyết cho JVM và native

### 3.1. Baseline JVM phải được cấu hình hợp lý

So sánh native với JVM chạy bằng cấu hình mặc định chưa chắc phản ánh lựa chọn production. JVM có thể cần:

- Heap sizing phù hợp với container memory limit.
- GC phù hợp với latency/throughput mục tiêu.
- Warm-up đủ để JIT compile hot path.
- CPU quota và số thread phù hợp.
- Cấu hình connection pool và cache giống môi trường triển khai.

Ghi rõ JVM vendor/version, flags và giới hạn tài nguyên. Có thể chạy hai baseline: JVM với cấu hình hiện tại của production và JVM đã được tuning trong cùng ngân sách tài nguyên. Điều này giúp biết native đang được so với trạng thái vận hành nào.

### 3.2. Native cũng cần được build và chạy đúng cách

Native executable chịu ảnh hưởng của:

- GraalVM version và Native Image build options.
- Target OS, CPU architecture và builder/container image.
- Profile, feature flags và cấu hình Spring AOT.
- Reachability metadata, Runtime Hints và resource configuration.
- Optimization/build-time initialization options.
- Cách đặt memory limit, CPU quota và environment variables khi chạy.

Không so một JVM đã được tuning với một native build thiếu cấu hình hoặc chưa chạy đúng workload. Ngược lại, cũng không tinh chỉnh native bằng cách thay đổi nhiều yếu tố cùng lúc rồi quy toàn bộ kết quả cho compiler.

### 3.3. Viết giả thuyết trước khi chạy

Ví dụ:

```text
Muc tieu: giam memory footprint cua API trong container 512 MiB.

Gia thuyet:
- Native co RSS tai steady-state thap hon JVM.
- Native van dat throughput toi thieu 800 requests/second.
- p95 latency khong vuot 150 ms o concurrency muc tieu.
- Readiness time giam du de cai thien scale-out.

Dieu kien:
- Cung source revision, dependency va business configuration.
- Cung database/cache, dataset, CPU quota va memory limit.
- JVM co warm-up; native duoc do ca cold-start va steady-state.
```

Đây là ví dụ minh họa, không phải số liệu cam kết. Mỗi giả thuyết cần có phép đo, ngưỡng đạt và workload tương ứng.

## 4. Chọn chỉ số cần đo

### 4.1. Startup và readiness

Phân biệt các mốc:

- **Process start:** thời điểm hệ điều hành bắt đầu process.
- **Application started:** Spring Boot hoàn tất giai đoạn khởi động mà framework báo cáo.
- **Readiness:** ứng dụng thực sự sẵn sàng nhận traffic theo readiness probe.
- **First request:** thời gian và latency của request đầu tiên.

Readiness quan trọng hơn việc process xuất hiện. Ứng dụng có thể đã mở port nhưng chưa kết nối database, chưa nạp cache hoặc chưa sẵn sàng xử lý nghiệp vụ.

Đo ít nhất:

```text
startup_to_ready_ms = ready_timestamp - process_start_timestamp
first_request_latency_ms =
    first_response_timestamp - first_request_timestamp
```

Nếu startup cần kết nối dịch vụ ngoài, giữ dịch vụ đó ở cùng trạng thái giữa hai lần chạy. Có thể đo thêm thời gian nội bộ của Spring và thời gian chờ dependency để phân biệt chi phí framework với chi phí môi trường.

### 4.2. Memory

Không đồng nhất heap với toàn bộ memory footprint.

| Chỉ số | Ý nghĩa |
|---|---|
| JVM heap used/committed | Heap đang dùng và heap JVM đã cấp phát |
| RSS / working set | Các trang bộ nhớ process đang cư trú trong RAM theo cách hệ điều hành báo cáo |
| Peak RSS | Mức RSS cao nhất trong khoảng đo |
| Container/cgroup memory | Memory được tính theo giới hạn và cách accounting của container |
| Native memory của JVM | Metaspace, code cache, thread stack, direct buffer và các vùng ngoài heap |
| Memory sau warm-up | Footprint khi ứng dụng đã xử lý workload và đạt trạng thái ổn định |

JVM có nhiều vùng ngoài heap; chỉ so `heap used` với RSS của native là không công bằng. Hãy so các chỉ số cùng ý nghĩa, ưu tiên RSS/container memory khi câu hỏi là số instance có thể chạy trên node.

Đo cả memory tại readiness, sau warm-up, trong steady-state và peak dưới burst/soak. Cache, thread pool, connection pool và payload đang xử lý có thể khiến memory tăng sau startup.

### 4.3. Throughput và latency

Ghi:

- Throughput: số request thành công mỗi giây.
- p50: latency trung vị.
- p95 và p99: latency ở đuôi phân phối.
- Error rate và timeout rate.
- Latency của request đầu tiên và latency sau warm-up.

Không chỉ nhìn average latency. Một biến thể có trung bình thấp nhưng p99 cao có thể làm trải nghiệm người dùng và SLO xấu đi.

Giữ cùng payload, request mix, concurrency và thời gian đo. Dùng load generator có khả năng tạo tải ổn định; tránh để chính load generator trở thành nút thắt.

### 4.4. CPU và hiệu quả tài nguyên

Đo CPU usage hoặc CPU-seconds trên một lượng request thành công. Nếu native dùng ít RAM hơn nhưng CPU cao hơn đáng kể, chi phí tổng thể có thể không giảm.

Một số chỉ số hữu ích:

```text
cpu_seconds_per_1000_success =
    process_cpu_seconds / successful_requests * 1000

memory_per_replica =
    aggregate_steady_state_rss / replica_count
```

Với một process, replica_count bằng 1. Khi so nhiều replica, phải dùng cùng cách đo và cùng mức tải trên mỗi replica.

### 4.5. Chỉ số build và vận hành

Native Image còn có các chi phí ngoài runtime:

- Thời gian native compilation.
- CPU/memory tiêu thụ trong CI khi build.
- Kích thước executable và container image.
- Thời gian tải image và rollout.
- Tần suất phải rebuild khi dependency hoặc target platform thay đổi.
- Chi phí duy trì metadata/hints và kiểm thử tương thích.

Nếu ứng dụng phát hành thường xuyên hoặc có nhiều target platform, build time và pipeline capacity có thể là yếu tố quyết định. Đừng bỏ các chi phí này khỏi đánh giá tổng thể.

## 5. Xác định tiêu chí thành công

### 5.1. Không tối ưu mọi chỉ số cùng lúc

Các chỉ số có thể đánh đổi:

- Giảm startup có thể không cải thiện steady-state throughput.
- Giảm RSS có thể đi kèm CPU hoặc latency cao hơn.
- Tăng concurrency có thể tăng throughput nhưng làm p99 xấu đi.
- Giảm memory mỗi replica có thể cho phép tăng mật độ pod, nhưng database connection hoặc downstream capacity có thể trở thành giới hạn mới.

Chọn một chỉ số chính và các guardrail. Ví dụ:

| Loại mục tiêu | Chỉ số chính | Guardrail |
|---|---|---|
| Scale-out | Readiness time | First-request latency, error rate |
| Memory density | RSS/container memory | Throughput, p95/p99, CPU |
| Long-running API | Throughput hoặc p95 | p99, error rate, memory |
| Short-lived job | Total completion time | Kết quả đúng, peak memory |
| Cost efficiency | Chi phí/request thành công | SLO, capacity và build cost |

### 5.2. Tính lợi ích ở cấp hệ thống

Nếu memory mỗi replica giảm, lợi ích cần được tính theo giới hạn node và các tài nguyên dùng chung. Ví dụ, số replica lý thuyết do memory giới hạn:

```text
memory_limited_replicas =
    floor((node_memory - reserved_memory) / memory_per_replica)
```

Đây chỉ là giới hạn theo RAM. Số replica thực tế còn phụ thuộc CPU, database connection, network, file descriptor, scheduler overhead và autoscaler.

Với chi phí, có thể so sánh:

```text
cost_per_success =
    total_compute_cost / successful_requests
```

Tính cả chi phí instance, thời gian chạy, retry, lỗi, build pipeline và vận hành nếu chúng có ảnh hưởng đáng kể. Không kết luận tiết kiệm chỉ từ memory giảm.

### 5.3. Đặt ngưỡng dừng

Trước benchmark, thống nhất các điều kiện loại trừ:

- Error rate vượt ngưỡng.
- p95/p99 vượt SLO.
- Throughput thấp hơn mức tối thiểu.
- Peak memory vượt container limit.
- CPU vượt ngân sách hoặc gây throttling.
- Native build không ổn định hoặc không hỗ trợ một dependency bắt buộc.

Nếu một biến thể không đạt guardrail, không dùng lợi ích ở chỉ số chính để che lấp lỗi đó.

## 6. Thiết kế phép so sánh công bằng

### 6.1. Giữ nguyên các yếu tố không phải biến thử nghiệm

| Yếu tố | Cách kiểm soát |
|---|---|
| Source code | Cùng commit/tag |
| Dependency | Cùng version và lockfile |
| Spring configuration | Cùng business properties và profile tương ứng |
| Database/cache/broker | Cùng phiên bản, dataset và trạng thái |
| CPU | Cùng model, quota và pinning nếu có |
| Memory | Cùng container/cgroup limit |
| Network | Cùng topology và latency tới dependency |
| Load | Cùng request mix, payload, concurrency và duration |
| Observability | Cùng mức log/metrics/tracing overhead |

Nếu native yêu cầu profile/AOT variant riêng, ghi rõ khác biệt đó và bảo đảm logic nghiệp vụ tương đương.

### 6.2. Tách cold-start khỏi steady-state

Không khởi chạy JVM rồi đo ngay một request và so với native theo cùng một cách mà không giải thích. JVM có thể cần warm-up để JIT compile hot paths; native có thể có startup khác nhưng không có cùng cơ chế JIT.

Thực hiện hai nhóm:

1. **Cold-start benchmark:** tạo process mới cho mỗi lượt, đo process-to-readiness và first request.
2. **Steady-state benchmark:** chạy cùng workload warm-up cho cả hai biến thể, sau đó đo trong khoảng thời gian ổn định. JVM có thể JIT compile hot paths trong giai đoạn này; native không có JIT như JVM nhưng vẫn có thể hoàn tất lazy initialization, nạp cache hoặc thiết lập connection.

Nếu production thường xuyên scale-to-zero, cold-start có trọng số cao. Nếu process chạy nhiều ngày, steady-state có thể quan trọng hơn.

### 6.3. Lặp lại và thay đổi thứ tự

Chạy nhiều lượt độc lập. Xen kẽ thứ tự JVM/native hoặc dùng thứ tự ngẫu nhiên để giảm ảnh hưởng của:

- Nhiệt độ CPU và throttling.
- Cache filesystem/page cache.
- Tải nền trên máy.
- Database/cache đã warm.
- Network jitter.
- JIT compilation và GC timing.

Ghi median, percentile và độ dao động. Nếu hai kết quả chênh lệch nhỏ hơn độ nhiễu của phép đo, chưa đủ bằng chứng để kết luận một biến thể tốt hơn.

### 6.4. Tránh benchmark sai do load generator

Load generator phải có đủ CPU/network để tạo tải mục tiêu. Dùng cùng máy hoặc cùng loại máy cho load generation; nếu load generator nằm cùng node với ứng dụng, ghi rõ vì CPU contention có thể làm méo kết quả.

Với latency test, chọn mô hình phát tải phù hợp:

- Closed-loop: client gửi request tiếp theo sau khi request trước hoàn tất; concurrency bị giới hạn.
- Open-loop/rate-based: client cố phát request theo tốc độ định trước; phù hợp để quan sát queueing khi hệ thống quá tải.

Closed-loop có thể che giấu latency tăng ở tải cao vì tốc độ gửi request giảm theo tốc độ phản hồi. Open-loop cần theo dõi queue và dropped requests. Dùng cùng mô hình khi so sánh hai biến thể.

## 7. Quy trình benchmark đề xuất

### Bước 1 — Viết benchmark brief

Ghi mục tiêu, workload, giả thuyết, chỉ số chính, guardrail và ngưỡng thành công. Chỉ bắt đầu đo khi các bên thống nhất cách đánh giá.

### Bước 2 — Chuẩn bị hai biến thể

Build JVM artifact và native executable từ cùng source/dependency. Ghi Java/GraalVM version, build arguments, profile, target OS/CPU và thời gian build.

### Bước 3 — Kiểm tra tính tương đương chức năng

Chạy cùng contract/integration tests trên cả hai biến thể. Xác nhận endpoint, transaction, cache, async, serialization, resource và kết quả nghiệp vụ tương đương trước khi đo hiệu năng.

### Bước 4 — Chạy cold-start

Tạo process mới cho mỗi lượt. Đo process start, application started, readiness và first request. Giữ trạng thái dependency giống nhau.

### Bước 5 — Chạy steady-state và burst

Chạy cùng request mix và concurrency trong giai đoạn warm-up đã chọn cho cả hai biến thể. Sau đó đo throughput, p50/p95/p99, CPU, RSS, memory peak và error rate. Ghi riêng thời gian warm-up của JVM để thấy ảnh hưởng của JIT.

### Bước 6 — Chạy soak và shutdown

Chạy đủ lâu để phát hiện memory growth, queue accumulation, cache behavior và GC. Sau đó đo shutdown và xác nhận task/connection được đóng đúng.

### Bước 7 — Tổng hợp và quyết định

So sánh kết quả với giả thuyết và guardrail. Tính lợi ích ở cấp replica/node hoặc chi phí/request. Ghi cả kết quả bất lợi, độ dao động và giới hạn của phép đo.

## 8. Mẫu benchmark brief

Sử dụng mẫu dưới đây trước khi thực hiện phép đo:

```text
Ung dung:
- Ten service:
- Source revision:
- Spring Boot version:
- JVM version / GraalVM version:
- Target OS / CPU architecture:

Muc tieu:
- Van de hien tai:
- Chi so uu tien:
- Muc cai thien toi thieu:
- Guardrails:

Workload:
- Loai workload:
- Request/message rate:
- Request mix va payload:
- Concurrency:
- Dataset va dependency:
- Thoi gian song cua instance:

Moi truong:
- CPU quota:
- Memory limit:
- Database/cache/broker:
- Network topology:
- Observability overhead:

Phuong phap:
- So lan cold-start:
- Warm-up duration:
- Steady-state duration:
- Burst/soak scenarios:
- Load generator va model:

Ket qua can luu:
- Readiness time:
- First-request latency:
- Throughput:
- p50 / p95 / p99:
- RSS / peak RSS / container memory:
- Heap / GC / CPU:
- Error rate:
- Build time / image size:

Quyet dinh:
- Tieu chi dat:
- Tieu chi loai:
- Ket qua:
- Han che va buoc tiep theo:
```

## 9. Ví dụ chọn mục tiêu cho hai loại dịch vụ

### 9.1. API có scale-to-zero

Giả sử một API chỉ nhận traffic vào một số khung giờ và có thể về zero replica ngoài giờ. Mục tiêu chính là giảm thời gian từ lúc autoscaler tạo container tới lúc readiness thành công.

Kịch bản:

1. Đưa service về zero replica.
2. Gửi request kích hoạt scale-up.
3. Ghi thời điểm tạo pod/process và thời điểm readiness.
4. Gửi request đầu tiên và đo latency/error.
5. Lặp lại nhiều lần với cùng dependency state.

Chỉ số chính là scale-to-ready và first-request latency. Cần đo cả thời gian scheduling/pull image nếu mục tiêu là trải nghiệm end-to-end; nếu chỉ đo process startup, tách phần orchestration ra khỏi phép đo.

Native có thể phù hợp nếu giảm cold start cải thiện SLO đủ nhiều. Nhưng nếu phần lớn thời gian chờ là image pull, database connection hoặc scheduler, giảm thời gian khởi tạo Spring có thể chỉ cải thiện một phần nhỏ.

### 9.2. API chạy liên tục và chịu tải ổn định

Với API chạy liên tục, JVM có thể warm-up và JIT compile hot paths. Mục tiêu có thể là giảm memory để tăng replica density mà vẫn giữ throughput và p99 trong ngưỡng.

Kịch bản:

1. Chạy JVM và native với cùng CPU/memory limit.
2. Warm-up JVM theo thời gian và workload đã định.
3. Tăng concurrency theo các mức cố định.
4. Giữ mỗi mức đủ lâu để ổn định.
5. Ghi throughput, p95/p99, CPU, RSS và error rate.
6. Tìm mức tải tối đa mà cả hai vẫn đạt SLO.

Nếu native giảm RSS nhưng làm throughput giảm vượt ngưỡng, cần tính xem mật độ replica tăng có bù được số instance hoặc CPU cần thêm hay không.

## 10. Những kết luận cần tránh

| Kết luận vội vàng | Vì sao chưa đủ bằng chứng |
|---|---|
| Native luôn nhanh hơn JVM | Kết quả phụ thuộc cold-start, JIT warm-up, workload và cấu hình |
| RSS native thấp hơn nghĩa là heap hiệu quả hơn | RSS và heap là hai chỉ số khác nhau |
| Startup log nhanh hơn nghĩa là readiness nhanh hơn | Dependency, health check và lazy initialization có thể còn chạy |
| Một request đầu tiên đại diện steady-state | JVM có warm-up và JIT; cần đo riêng các giai đoạn |
| Native dùng ít RAM hơn nên chi phí thấp hơn | CPU, số replica, network, build và operational cost cũng ảnh hưởng |
| Build native thành công nghĩa là benchmark hợp lệ | Cần kiểm tra tương đương chức năng và workload |
| Một lần chạy đủ để kết luận | Nhiễu hệ thống và cache có thể làm kết quả sai lệch |

## 11. Checklist trước khi chạy benchmark

- Mục tiêu có gắn với vấn đề vận hành hoặc kinh doanh cụ thể không?
- Đã chọn chỉ số chính và guardrail chưa?
- Workload có phản ánh request mix, concurrency và thời gian sống của instance không?
- Đã phân biệt cold start, first request, warm-up và steady-state chưa?
- JVM baseline có cấu hình hợp lý và được warm-up khi đo steady-state không?
- Native executable có được build cho đúng target OS/CPU không?
- Source, dependency, profile, dataset và dependency services có tương đương không?
- Memory đang so là heap, RSS hay container memory?
- Load generator có đủ năng lực và dùng cùng mô hình phát tải không?
- Có đủ số lượt chạy để đánh giá độ dao động không?
- Đã đặt ngưỡng dừng cho error rate, p95/p99, throughput, CPU và peak memory chưa?
- Đã tính build time, image size và chi phí vận hành vào quyết định chưa?

### Câu hỏi tự kiểm tra

1. Vì sao cần xác định mục tiêu trước khi chọn công cụ benchmark?
2. Khi nào readiness time quan trọng hơn thời gian Spring báo application started?
3. Vì sao phải đo riêng cold-start và steady-state?
4. Vì sao không thể so JVM `heap used` trực tiếp với RSS của native?
5. Một native service giảm memory nhưng tăng CPU và p99 latency thì cần đánh giá thế nào?
6. Vì sao phải giữ cùng workload, dependency và resource limit khi so sánh?
7. Khi nào chi phí native compilation có thể làm thay đổi quyết định triển khai?

**Ghi nhớ:** hãy bắt đầu bằng mục tiêu hệ thống, sau đó chọn workload, chỉ số và guardrail phù hợp. Đo readiness, memory, throughput, latency, CPU và chi phí theo từng giai đoạn; giữ điều kiện so sánh nhất quán và lặp lại phép đo. Chỉ chọn Native Image khi lợi ích quan sát được giải quyết đúng vấn đề của ứng dụng mà vẫn đáp ứng các yêu cầu chức năng, SLO và vận hành.
