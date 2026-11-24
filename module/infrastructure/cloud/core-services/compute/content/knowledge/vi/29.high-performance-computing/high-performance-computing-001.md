# Workload HPC và khác biệt với dịch vụ web thông thường

Điện toán hiệu năng cao (High-Performance Computing — HPC) dùng nhiều lõi CPU, GPU, bộ tăng tốc, bộ nhớ và mạng tốc độ cao để giải quyết bài toán tính toán lớn trong thời gian hợp lý. Các workload điển hình gồm mô phỏng khí động học, động lực học chất lỏng, dự báo thời tiết, mô hình phân tử, phân tích địa chấn, mô phỏng vật liệu, huấn luyện mô hình khoa học và xử lý dữ liệu quy mô lớn.

HPC có cách tổ chức khác với một dịch vụ web thông thường. Web service thường nhận nhiều request độc lập, tối ưu latency của từng request và mở rộng bằng cách thêm replica. HPC thường chạy một job gồm nhiều tiến trình hoặc worker phối hợp trên một tập node; hiệu năng phụ thuộc vào khả năng chia nhỏ phép tính, trao đổi dữ liệu, đồng bộ và sử dụng tài nguyên đồng thời. Thêm node không nhất thiết làm job nhanh hơn nếu phần giao tiếp hoặc phần tuần tự trở thành nút thắt.

Bài học này giới thiệu đặc trưng workload HPC, mô hình song song, cách bố trí CPU/GPU và node, vai trò của mạng và storage, cùng các chỉ số đo hiệu năng. Sau bài học, bạn có thể:

- Phân biệt HPC, web service, batch processing và high-throughput computing.
- Nhận diện bài toán compute-bound, memory-bound, communication-bound và I/O-bound.
- Chọn mô hình song song phù hợp: shared-memory, distributed-memory, task parallelism và data parallelism.
- Giải thích vai trò của MPI, OpenMP, GPU và các bộ tăng tốc.
- Hiểu strong scaling, weak scaling, speedup, efficiency và giới hạn Amdahl.
- Đánh giá latency, bandwidth, FLOPS, memory bandwidth, IOPS và thời gian hoàn tất job.
- Lựa chọn cấu hình cloud compute, interconnect, storage và scheduler theo đặc tính workload.
- Thiết kế benchmark và profiling để tìm bottleneck trước khi mở rộng cụm.

## 1. HPC là gì và giải quyết loại vấn đề nào?

HPC tập trung vào việc hoàn thành một phép tính lớn hoặc một tập công việc khoa học/kỹ thuật bằng cách khai thác song song nhiều tài nguyên. Một job có thể chạy trên một máy nhiều socket, một node nhiều GPU hoặc hàng trăm node liên kết bằng mạng tốc độ cao.

Ví dụ:

- **Mô phỏng chất lưu:** chia không gian thành các ô lưới; mỗi tiến trình tính một miền con và trao đổi giá trị ở biên với tiến trình lân cận.
- **Dự báo thời tiết:** tính toán trên lưới không gian và thời gian, lặp qua nhiều bước mô hình; thường cần CPU/GPU, memory bandwidth và interconnect mạnh.
- **Mô phỏng phân tử:** tính lực giữa các hạt hoặc phân tử; có thể dùng GPU và thuật toán giảm số phép tương tác.
- **Phân tích địa chấn:** xử lý các mảng dữ liệu lớn, đọc/ghi song song và tính toán ma trận.
- **Mô phỏng vật liệu:** dùng phương pháp số hoặc mô hình lượng tử; có thể yêu cầu bộ nhớ lớn, nhiều phép toán tuyến tính và giao tiếp MPI.
- **Huấn luyện mô hình khoa học:** phân phối tensor và dữ liệu qua nhiều GPU; hiệu năng phụ thuộc tính toán, bộ nhớ GPU và đồng bộ gradient.

Điểm chung là khối lượng tính toán lớn, có thể chia thành các phần song song và có tiêu chí đo thời gian hoàn tất hoặc độ chính xác kết quả.

### HPC, web service và high-throughput computing

| Đặc điểm | HPC job | Web service | High-throughput computing (HTC) |
|---|---|---|---|
| Đơn vị công việc | Một job lớn hoặc một nhóm tiến trình phối hợp | Request hoặc phiên người dùng | Nhiều job tương đối độc lập |
| Mục tiêu chính | Giảm thời gian hoàn tất phép tính lớn | Đáp ứng request nhanh và ổn định | Hoàn tất nhiều job trong một khoảng thời gian |
| Song song | Thường cần phối hợp trong job | Thường phân tán request giữa replica | Phân phối job độc lập qua worker |
| Giao tiếp | MPI, collective, shared memory, interconnect | HTTP/gRPC, cache, database | Queue, object storage, scheduler |
| Tài nguyên | CPU/GPU, memory bandwidth, network latency/bandwidth | CPU/RAM theo request, network và dependency | Tổng throughput và chi phí trên mỗi job |
| Điều phối | Batch scheduler, job allocation, topology-aware placement | Load balancer, autoscaler, orchestrator | Queue/scheduler, worker pool |
| Thước đo | Time-to-solution, speedup, efficiency, FLOPS | p95/p99 latency, RPS, error rate | Jobs/hour, queue age, cost/job |

Một hệ thống có thể kết hợp các mô hình. Ví dụ, API nhận yêu cầu mô phỏng rồi đưa job vào queue; web service quản lý trạng thái job, còn HPC cluster thực hiện phép tính. Không nên dùng cùng một cơ chế autoscaling cho cả API và job HPC nếu chúng có cách sử dụng tài nguyên khác nhau.

## 2. Đặc trưng của workload HPC

Trước khi chọn máy, hãy xác định workload bị giới hạn bởi loại tài nguyên nào. Cùng một số lượng CPU core có thể cho kết quả rất khác nếu một ứng dụng cần nhiều phép toán số học, một ứng dụng cần đọc dữ liệu liên tục và ứng dụng khác thường xuyên trao đổi dữ liệu giữa node.

### Compute-bound

Workload compute-bound dành phần lớn thời gian thực hiện phép toán trên CPU hoặc GPU. Ví dụ gồm một số kernel đại số tuyến tính, mô phỏng số và xử lý tín hiệu. Các chỉ số cần xem gồm FLOPS, IPC, vectorization, utilization, clock behavior và thời gian kernel.

Tăng số core hoặc dùng GPU có thể cải thiện hiệu năng nếu thuật toán song song hóa tốt và dữ liệu được cung cấp đủ nhanh. Nếu kernel bị giới hạn bởi dependency tuần tự hoặc instruction latency, thêm core không mang lại mức tăng tương ứng.

### Memory-bound

Workload memory-bound chờ dữ liệu từ RAM nhiều hơn là thực hiện phép toán. Các ứng dụng duyệt mảng lớn, sparse matrix hoặc truy cập bộ nhớ không liên tục có thể bị giới hạn bởi memory bandwidth, cache miss và NUMA locality.

Các yếu tố cần xem:

- Băng thông bộ nhớ mỗi socket hoặc node.
- Dung lượng RAM và working set.
- Cache hit/miss và memory access pattern.
- NUMA placement và first-touch policy.
- Số kênh bộ nhớ và tốc độ DIMM theo cấu hình instance.

Tăng CPU core mà không tăng băng thông bộ nhớ có thể làm nhiều core tranh chấp cùng một tài nguyên.

### Communication-bound

Workload communication-bound dành nhiều thời gian trao đổi dữ liệu giữa tiến trình hoặc node. Ví dụ là mô phỏng miền phân tách, distributed training và các thuật toán có collective communication thường xuyên.

Độ trễ mạng, băng thông, topology, số lần đồng bộ và kích thước message có thể quyết định hiệu năng. Một cluster có nhiều FLOPS nhưng interconnect yếu vẫn có thể chạy chậm nếu các tiến trình thường xuyên chờ nhau.

### I/O-bound

Workload I/O-bound chờ đọc hoặc ghi dữ liệu từ storage. Các pipeline đọc checkpoint, dữ liệu khoa học hoặc output lớn có thể bị giới hạn bởi throughput, IOPS, metadata operations và số file nhỏ.

Hãy phân biệt:

- Throughput tuần tự khi đọc/ghi file lớn.
- IOPS và latency với nhiều thao tác nhỏ hoặc ngẫu nhiên.
- Metadata throughput khi mở/đóng rất nhiều file.
- Khả năng truy cập song song từ nhiều node.
- Thời gian checkpoint và khôi phục.

### Workload hỗn hợp

Nhiều ứng dụng chuyển bottleneck theo giai đoạn. Một job có thể compute-bound trong bước giải hệ phương trình, communication-bound khi đồng bộ và I/O-bound khi ghi checkpoint. Vì vậy, cần profiling theo phase thay vì gắn nhãn workload chỉ từ một metric tổng thể.

## 3. Các mô hình song song cơ bản

Song song hóa là chia một bài toán thành các phần có thể thực hiện đồng thời, đồng thời quản lý dữ liệu phụ thuộc và kết hợp kết quả. Không phải phép tính nào cũng có thể chia tùy ý.

### Data parallelism

Cùng một phép toán được thực hiện trên nhiều phần dữ liệu khác nhau. Ví dụ, chia một ma trận thành các block; mỗi worker xử lý một phần rồi ghép kết quả. Data parallelism phù hợp với vector/matrix operation, xử lý ảnh, mô phỏng trên lưới và một số workload machine learning.

### Task parallelism

Các tác vụ khác nhau được thực hiện đồng thời. Ví dụ, một pipeline có bước đọc dữ liệu, tiền xử lý, mô phỏng và ghi kết quả; một số bước có thể chạy chồng lấp nếu không phụ thuộc hoàn toàn vào nhau.

### Shared-memory parallelism

Nhiều thread chạy trên các core trong cùng một node và truy cập không gian bộ nhớ chung. Cách này thường có chi phí trao đổi thấp hơn giao tiếp giữa node, nhưng cần quản lý race condition, lock contention, false sharing và locality.

OpenMP là mô hình phổ biến cho shared-memory parallelism trong C/C++ và Fortran. Thread có thể chia vòng lặp hoặc vùng tính toán thành các phần chạy song song.

### Distributed-memory parallelism

Mỗi tiến trình có không gian bộ nhớ riêng, thường chạy trên một node hoặc một nhóm core. Tiến trình trao đổi dữ liệu qua message passing, phổ biến nhất là MPI trong nhiều ứng dụng HPC.

Distributed memory cho phép mở rộng qua nhiều node và tổng hợp bộ nhớ của cả cụm, nhưng chi phí giao tiếp và đồng bộ cần được tính vào thuật toán.

### Hybrid parallelism

Một ứng dụng có thể kết hợp MPI giữa node với OpenMP trong mỗi node, hoặc MPI cùng GPU kernel. Ví dụ, mỗi node chạy một MPI rank; mỗi rank dùng nhiều CPU thread và điều khiển một hoặc nhiều GPU. Hybrid model giúp tận dụng tài nguyên trong node và giảm số tiến trình MPI, nhưng cần đặt rank/thread đúng với topology.

~~~mermaid
flowchart TD
    J["Một HPC job"] --> N1["Node 1"]
    J --> N2["Node 2"]
    N1 --> M1["MPI rank 0"]
    N1 --> M2["MPI rank 1"]
    N2 --> M3["MPI rank 2"]
    N2 --> M4["MPI rank 3"]
    M1 --> T1["OpenMP threads"]
    M2 --> T2["OpenMP threads"]
    M3 --> T3["OpenMP threads"]
    M4 --> T4["OpenMP threads"]
    M1 --> G1["GPU kernel"]
    M3 --> G2["GPU kernel"]
~~~

## 4. MPI, OpenMP và giao tiếp giữa tiến trình

### MPI

Message Passing Interface (MPI) là chuẩn lập trình cho phép các tiến trình trao đổi dữ liệu. Các thao tác thường gặp:

- Point-to-point: gửi/nhận message giữa hai rank.
- Broadcast: một rank gửi dữ liệu tới nhiều rank.
- Reduce: kết hợp giá trị từ nhiều rank thành kết quả.
- All-reduce: mọi rank tham gia phép kết hợp và nhận kết quả.
- All-to-all: trao đổi dữ liệu giữa nhiều cặp rank.
- Barrier: các rank chờ nhau tại một điểm đồng bộ.

Các collective operation thuận tiện nhưng có thể trở thành bottleneck nếu gọi quá thường xuyên hoặc message lớn. Khi một rank chậm hơn, các rank khác có thể phải chờ ở collective.

### OpenMP

OpenMP cung cấp directive và runtime để chia vùng code thành thread. Mẫu phổ biến là chia vòng lặp độc lập:

~~~c
#include <omp.h>
#include <stddef.h>

void scale(double *a, size_t n, double factor) {
    #pragma omp parallel for
    for (size_t i = 0; i < n; ++i) {
        a[i] *= factor;
    }
}
~~~

Ví dụ chỉ phù hợp khi mỗi iteration ghi một phần tử riêng và không có dependency giữa các iteration. Nếu nhiều thread cập nhật chung một biến, cần reduction hoặc cơ chế đồng bộ thích hợp.

### MPI + OpenMP

Hybrid MPI/OpenMP thường chia miền dữ liệu giữa rank, rồi chia tiếp miền của mỗi rank cho thread. Cần tránh oversubscription: tổng số thread được tạo không nên vượt quá CPU core được cấp cho job nếu chưa có chủ đích rõ ràng.

Ví dụ một node được cấp 32 CPU core có thể chạy 2 MPI rank, mỗi rank 16 OpenMP thread. Đây chỉ là cấu hình thử nghiệm ban đầu; số rank/thread tối ưu phụ thuộc cache, NUMA, kích thước dữ liệu và communication pattern.

### GPU programming

GPU phù hợp với phép toán có nhiều phần tử độc lập và đủ công việc để bù chi phí truyền dữ liệu, launch kernel và đồng bộ. Các nền tảng phổ biến gồm CUDA, HIP, OpenCL, SYCL và framework cấp cao.

Để GPU đạt hiệu năng tốt:

- Dữ liệu nên được giữ trên device đủ lâu để giảm host-device transfer.
- Kernel cần có đủ parallel work và memory access coalescing phù hợp.
- Tránh đồng bộ CPU-GPU quá thường xuyên.
- Theo dõi GPU utilization, memory utilization, memory bandwidth và kernel time.
- Kiểm tra driver, runtime, thư viện toán học và phiên bản framework tương thích.

GPU không tự động tăng tốc mọi ứng dụng. Một workload ít song song, nhiều nhánh rẽ hoặc truyền dữ liệu nhỏ liên tục có thể không có lợi khi chuyển sang GPU.

## 5. Cách phân chia bài toán và trao đổi dữ liệu

Một thuật toán song song cần quyết định cách chia dữ liệu, cách phân công công việc và cách kết hợp kết quả.

### Domain decomposition

Với mô phỏng trên không gian, domain decomposition chia lưới thành các miền con. Mỗi rank tính một miền, sau đó trao đổi halo/ghost cells ở biên để cập nhật bước tiếp theo.

Kích thước miền con ảnh hưởng tới tỷ lệ tính toán trên giao tiếp. Nếu mỗi rank chỉ giữ một miền rất nhỏ, tỷ lệ biên so với dữ liệu nội bộ tăng và thời gian trao đổi có thể chiếm phần lớn.

### Partitioning và load balance

Các phần việc cần có khối lượng tương đương hoặc scheduler có cơ chế phân phối động. Nếu một rank xử lý vùng phức tạp hơn nhiều, các rank còn lại sẽ chờ ở barrier hoặc collective.

Có thể dùng static partition khi chi phí từng phần dễ dự đoán. Dynamic scheduling hữu ích khi task có thời gian chạy không đều, nhưng phát sinh overhead điều phối và có thể làm giảm locality.

### Overlap computation và communication

Một số MPI application có thể dùng non-blocking communication để bắt đầu truyền dữ liệu rồi tiếp tục tính phần không phụ thuộc dữ liệu đang truyền. Khi truyền hoàn tất, ứng dụng xử lý vùng biên. Overlap chỉ có lợi nếu phần tính toán đủ dài và implementation/network stack hỗ trợ tiến triển giao tiếp hiệu quả.

### Đồng bộ và race condition

Barrier, lock, atomic operation và collective có chi phí. Đồng bộ quá thường xuyên làm giảm khả năng song song; đồng bộ không đúng có thể gây race condition, deadlock hoặc kết quả sai. Cần xác định rõ ownership dữ liệu và dependency giữa các bước.

## 6. Chỉ số hiệu năng HPC

HPC cần nhiều chỉ số hơn CPU utilization. Một job có thể dùng CPU 100% nhưng vẫn không đạt hiệu năng mong muốn vì memory stall hoặc mất cân bằng giữa rank.

| Chỉ số | Ý nghĩa | Khi cần theo dõi |
|---|---|---|
| Time-to-solution | Thời gian từ lúc bắt đầu đến khi có kết quả hợp lệ | Chỉ số chính của một job |
| Throughput | Số job hoặc đơn vị công việc hoàn tất trong một khoảng thời gian | Cụm chạy nhiều job |
| FLOPS | Số phép toán dấu phẩy động mỗi giây | Kernel tính toán số học |
| Speedup | Tỷ lệ thời gian chạy tuần tự so với song song | Đánh giá mở rộng |
| Parallel efficiency | Speedup chia cho số processing element | Đánh giá hiệu quả sử dụng tài nguyên |
| Memory bandwidth | Tốc độ di chuyển dữ liệu giữa RAM và CPU/GPU | Workload memory-bound |
| Network latency | Thời gian truyền/nhận message nhỏ | MPI communication nhiều message |
| Network bandwidth | Lượng dữ liệu truyền mỗi giây | Message lớn và collective |
| IOPS / storage throughput | Số thao tác hoặc byte đọc/ghi mỗi giây | Checkpoint và dataset |
| Queue wait time | Thời gian job chờ trước khi được cấp tài nguyên | Trải nghiệm người dùng cluster |
| Cost per solution | Chi phí compute/storage/network cho một kết quả hợp lệ | Tối ưu chi phí cloud |

### FLOPS và giới hạn lý thuyết

FLOPS đo số phép toán dấu phẩy động mỗi giây. Peak FLOPS của CPU/GPU là mức lý thuyết dựa trên số core, vector width, clock và số phép toán mỗi chu kỳ. Ứng dụng thường đạt thấp hơn do memory access, instruction dependency, branching, communication, synchronization và phần tuần tự.

Không nên so sánh hai hệ thống chỉ bằng peak FLOPS. Hãy đo sustained performance với kernel và dữ liệu đại diện.

### Latency và bandwidth

Latency là thời gian để một thao tác hoặc message bắt đầu/hoàn tất theo cách đo cụ thể. Bandwidth là lượng dữ liệu truyền trong một đơn vị thời gian. Một ứng dụng gửi rất nhiều message nhỏ thường nhạy với latency; một ứng dụng trao đổi ít message nhưng rất lớn thường nhạy với bandwidth.

Một mạng có bandwidth cao chưa chắc phù hợp nếu latency hoặc topology không đáp ứng communication pattern. Ngược lại, mạng latency thấp nhưng bandwidth thấp có thể hạn chế trao đổi tensor hoặc halo dữ liệu lớn.

## 7. Speedup, efficiency và định luật Amdahl

### Speedup

Speedup so sánh thời gian chạy trên một tài nguyên tham chiếu với thời gian chạy khi dùng nhiều tài nguyên:

\[
S(N) = \frac{T(1)}{T(N)}
\]

Trong đó \(T(1)\) là thời gian chạy với một processing element theo baseline đã chọn; \(T(N)\) là thời gian chạy với \(N\) processing element.

Ví dụ, job chạy 100 phút trên 1 node và 30 phút trên 4 node:

\[
S(4) = \frac{100}{30} \approx 3.33
\]

Speedup lý tưởng là 4 lần, nhưng kết quả đo chỉ đạt khoảng 3,33 lần.

### Parallel efficiency

Hiệu suất song song:

\[
E(N) = \frac{S(N)}{N}
\]

Với speedup 3,33 trên 4 node:

\[
E(4) = \frac{3.33}{4} \approx 83.3\%
\]

Efficiency giúp nhìn ra lượng tài nguyên bị mất do phần tuần tự, communication, synchronization, imbalance hoặc overhead.

### Amdahl's Law

Nếu phần tuần tự chiếm tỷ lệ \(s\), phần còn lại có thể song song hóa, speedup tối đa với \(N\) processing element theo mô hình đơn giản là:

\[
S(N) = \frac{1}{s + \frac{1-s}{N}}
\]

Ví dụ, nếu 10% chương trình không thể song song hóa, dù dùng rất nhiều core, speedup vẫn bị giới hạn bởi phần tuần tự:

\[
\lim_{N \to \infty} S(N) = \frac{1}{s} = 10
\]

Định luật này giải thích vì sao thêm core không thể tăng tốc vô hạn. Cần tối ưu phần tuần tự, giảm đồng bộ và giảm giao tiếp để cải thiện scaling.

### Gustafson's Law

Với workload mà kích thước bài toán tăng theo số processing element, Gustafson's Law mô tả khả năng mở rộng bằng cách giữ thời gian chạy gần cố định nhưng xử lý bài toán lớn hơn:

\[
S_G(N) = N - s(N-1)
\]

Trong đó \(s\) là phần tuần tự đo theo thời gian chạy song song. Đây là góc nhìn hữu ích cho mô phỏng lớn hơn khi có thêm tài nguyên, thay vì chỉ chạy cùng một input trên nhiều core.

## 8. Strong scaling và weak scaling

### Strong scaling

Strong scaling giữ nguyên kích thước bài toán, tăng số processing element và đo thời gian hoàn tất. Mục tiêu là giải cùng một bài toán nhanh hơn.

Khi tăng số node, lượng công việc tính toán trên mỗi node giảm nhưng phần giao tiếp, đồng bộ và khởi tạo có thể không giảm tương ứng. Vì vậy, efficiency thường suy giảm khi mở rộng quá xa.

### Weak scaling

Weak scaling tăng kích thước bài toán tỷ lệ với số processing element, giữ lượng công việc trên mỗi processing element gần như không đổi. Mục tiêu là giải bài toán lớn hơn trong thời gian tương đương.

Weak scaling phù hợp với các mô phỏng có thể mở rộng miền không gian hoặc độ phân giải. Nếu thời gian tăng khi số node tăng, có thể có overhead giao tiếp, contention hoặc I/O.

| Cách đo | Kích thước bài toán | Số tài nguyên | Mục tiêu |
|---|---|---|---|
| Strong scaling | Giữ nguyên | Tăng | Giảm time-to-solution |
| Weak scaling | Tăng theo tài nguyên | Tăng | Giữ thời gian cho bài toán lớn hơn |

Không nên so sánh kết quả strong scaling với weak scaling như cùng một phép thử. Cần ghi rõ kích thước input, số rank/thread/GPU, topology và cách đo.

## 9. Roofline model và xác định giới hạn tính toán

Roofline model giúp phân tích ứng dụng bị giới hạn bởi compute throughput hay memory bandwidth. Một đại lượng quan trọng là arithmetic intensity:

\[
AI = \frac{\text{Số phép toán}}{\text{Số byte dữ liệu di chuyển}}
\]

Nếu arithmetic intensity thấp, workload có thể bị giới hạn bởi memory bandwidth. Nếu arithmetic intensity cao, workload có thể tiến gần giới hạn compute peak.

Mô hình roofline đơn giản biểu diễn performance tối đa gần đúng:

\[
P \le \min(P_{peak}, AI \times BW_{memory})
\]

Trong đó \(P_{peak}\) là peak compute performance và \(BW_{memory}\) là băng thông bộ nhớ. Mô hình thực tế cần tính thêm cache, vectorization, instruction mix và hiệu năng của memory hierarchy.

Roofline không phải một chỉ số duy nhất để quyết định mua máy. Nó giúp xác định nên ưu tiên tăng compute capability, cải thiện locality, giảm data movement hay tối ưu thuật toán.

## 10. Chọn CPU, GPU, bộ nhớ và node

### CPU

CPU phù hợp với logic điều khiển, thuật toán có dependency phức tạp, workload branch-heavy hoặc code chưa được chuyển sang accelerator. Khi chọn instance, xem:

- Số core vật lý và vCPU.
- Kiến trúc, thế hệ CPU và instruction set.
- Clock behavior dưới tải dài.
- Số socket, NUMA node và cache.
- Memory channel và băng thông.
- Tỷ lệ core/giá và hiệu năng sustained.

Không nên chỉ chọn instance có nhiều vCPU nhất. Nếu application dùng OpenMP và bị giới hạn memory bandwidth, một node có ít core nhưng băng thông RAM cao hơn có thể nhanh hơn.

### GPU và accelerator

GPU phù hợp với workload có data parallelism lớn và thư viện hỗ trợ. Cần xem:

- Số GPU, kiến trúc và khả năng tương thích framework.
- VRAM capacity và memory bandwidth.
- Interconnect giữa GPU trong cùng node.
- Host-to-device transfer và topology PCIe/NVLink hoặc kết nối tương đương.
- Driver, runtime, compiler và thư viện toán học.
- Hiệu năng precision cần thiết: FP64, FP32, TF32, FP16, BF16 hoặc integer.

Một GPU có throughput cao ở FP16 không đồng nghĩa phù hợp với mô phỏng khoa học cần FP64. Chọn accelerator theo precision và accuracy requirement của thuật toán.

### Bộ nhớ và NUMA

Với multi-socket server, mỗi CPU socket thường có vùng bộ nhớ local và remote. Truy cập remote NUMA có thể có latency cao hơn hoặc băng thông thấp hơn local. Pinning thread và phân bổ memory gần CPU xử lý dữ liệu có thể cải thiện hiệu năng.

Hãy đo working set, memory bandwidth, cache miss và NUMA traffic. Cần kiểm tra chính sách first-touch và cách runtime phân bổ thread.

### Một node hay nhiều node?

Một node lớn có thể tránh một phần network communication nhưng bị giới hạn bởi số socket, RAM và accelerator trong node. Nhiều node cho tổng tài nguyên lớn hơn nhưng cần interconnect và thuật toán phân tán tốt.

Chọn số node bằng benchmark strong/weak scaling, không chỉ dựa trên tổng vCPU hoặc tổng GPU.

## 11. Mạng và interconnect cho HPC

Mạng HPC cần hỗ trợ giao tiếp giữa tiến trình với latency thấp, bandwidth cao và khả năng xử lý nhiều message đồng thời. Tùy cloud và instance family, có thể có Ethernet tốc độ cao, network adapter tối ưu HPC hoặc fabric hỗ trợ RDMA.

### RDMA

Remote Direct Memory Access (RDMA) cho phép truyền dữ liệu giữa memory của các máy với ít can thiệp CPU hơn so với một số đường truyền truyền thống. RDMA có thể giảm latency và CPU overhead cho MPI communication, nhưng cần hỗ trợ đồng bộ từ instance type, network fabric, driver, kernel và MPI library.

Không phải mọi instance có network bandwidth cao đều hỗ trợ RDMA hoặc cùng một semantics. Kiểm tra tài liệu nền tảng về adapter, placement group/topology, OS image và thư viện được hỗ trợ.

### Latency, bandwidth và topology

Đối với MPI:

- Latency thấp có lợi cho nhiều message nhỏ và collective thường xuyên.
- Bandwidth cao có lợi cho message lớn, halo exchange và distributed tensor.
- Topology tốt giảm số hop và contention giữa các node.
- Placement gần nhau có thể cải thiện giao tiếp nếu nền tảng cung cấp topology-aware placement.

Một cluster cần benchmark all-reduce, point-to-point và pattern gần với ứng dụng thực. Không nên chỉ dùng iperf hoặc ping rồi kết luận MPI sẽ đạt hiệu năng tương tự.

## 12. Storage và dữ liệu cho HPC

HPC có thể đọc dataset lớn, ghi nhiều checkpoint và tạo output dung lượng cao. Storage cần được chọn theo pattern:

| Loại dữ liệu | Mô hình storage thường phù hợp | Chú ý |
|---|---|---|
| Dataset lớn, đọc chủ yếu | Object storage hoặc file storage song song | Throughput, parallel read, cache và chi phí request |
| File input/output dùng chung | Parallel file system hoặc shared file system | Metadata rate, concurrent clients và locking |
| Scratch tạm thời | Local NVMe hoặc ephemeral disk | Tốc độ cao nhưng có thể mất khi node dừng |
| Checkpoint | Durable object/file storage | Atomic publish, versioning, thời gian ghi và khôi phục |
| Kết quả cuối | Durable object storage hoặc file storage | Retention, integrity và quyền truy cập |

Không nên đặt checkpoint duy nhất trên local NVMe nếu node có thể bị terminate hoặc job cần restart trên node khác. Có thể dùng local scratch cho dữ liệu tạm và đẩy checkpoint/output quan trọng sang storage bền vững.

### Checkpoint và restart

Job HPC dài có thể mất nhiều giờ hoặc nhiều ngày. Checkpoint lưu trạng thái mô phỏng hoặc tiến trình tính toán để tiếp tục sau lỗi, bảo trì hoặc thời gian allocation kết thúc.

Một checkpoint cần ghi đủ metadata:

- Phiên bản code và compiler.
- Input dataset và tham số.
- Số bước/time step đã hoàn thành.
- Trạng thái solver, model hoặc optimizer.
- Sơ đồ partition và số rank/thread nếu cần tương thích.
- Checksum và version để xác minh tính toàn vẹn.

Nên ghi checkpoint vào file/key mới, xác minh rồi mới cập nhật manifest hiện hành. Không ghi đè checkpoint tốt trước khi bản mới hoàn tất.

## 13. Batch scheduler và quản lý tài nguyên HPC

HPC cluster thường dùng batch scheduler để xếp hàng và cấp phát tài nguyên cho job. Người dùng mô tả yêu cầu CPU, memory, GPU, thời gian chạy, partition hoặc queue; scheduler quyết định khi nào job được cấp node.

Các khái niệm thường gặp:

- **Job:** đơn vị công việc được submit.
- **Partition/queue:** nhóm node hoặc chính sách cấp phát.
- **Allocation:** tài nguyên được cấp cho job.
- **Task/rank:** tiến trình hoặc đơn vị thực thi trong job.
- **Walltime:** thời gian tối đa được phép chạy.
- **Fair-share/priority:** chính sách ưu tiên giữa người dùng hoặc project.
- **Backfill:** chạy job nhỏ hơn vào khoảng trống mà không làm trễ job ưu tiên cao theo kế hoạch.

Slurm là một batch scheduler phổ biến trong HPC. Một job script minh họa:

~~~bash
#!/bin/bash
#SBATCH --job-name=fluid-sim
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=4
#SBATCH --time=02:00:00
#SBATCH --partition=compute
#SBATCH --output=slurm-%j.out

module load compiler mpi
srun ./solver --input case.dat
~~~

Ví dụ yêu cầu 4 node, mỗi node 8 MPI task và mỗi task 4 CPU thread. Tổng số CPU được yêu cầu theo cấu hình này là 4 × 8 × 4 = 128 core/CPU slot tùy cách cluster định nghĩa và cấp phát. Cần bảo đảm node thực tế có đủ core và cấu hình thread của ứng dụng khớp với allocation.

### Scheduler khác autoscaler web

Web autoscaler thường phản ứng với request rate hoặc CPU utilization của replica. HPC scheduler cần cấp một allocation nhất quán cho job nhiều node, bảo đảm tài nguyên đồng thời và topology phù hợp. Thêm node vào cluster không có nghĩa job đang chạy tự động nhận thêm node; nhiều job HPC cần được submit với số node/rank xác định.

Có thể tự động co giãn node pool theo hàng đợi scheduler, nhưng phải bảo đảm node mới gia nhập cluster, cài runtime và được scheduler nhận diện trước khi job được dispatch.

## 14. Chỉ số của scheduler và hiệu quả cụm

Ngoài hiệu năng của một job, quản trị cluster cần theo dõi mức sử dụng và khả năng phục vụ nhiều nhóm người dùng.

| Chỉ số | Ý nghĩa |
|---|---|
| Queue wait time | Thời gian từ submit đến khi job bắt đầu |
| Job turnaround time | Thời gian từ submit đến khi job hoàn tất |
| Utilization | Tỷ lệ tài nguyên được dùng trong khoảng thời gian |
| Throughput | Số job hoàn tất mỗi giờ/ngày |
| Node idle time | Thời gian node được cấp nhưng không có công việc hữu ích |
| Fragmentation | Tài nguyên còn trống nhưng không đủ cấu hình để đặt job đang chờ |
| Failed/preempted jobs | Job lỗi, bị dừng hoặc phải submit lại |
| Cost per job/result | Chi phí để hoàn tất một job hoặc tạo một kết quả hợp lệ |

Utilization cao không luôn đồng nghĩa hiệu quả cao. Nếu job bị chờ lâu, chạy quá chậm hoặc tạo output không hợp lệ, cụm có thể sử dụng nhiều CPU nhưng không mang lại kết quả đúng hạn.

## 15. Benchmark và profiling workload HPC

Benchmark cần đại diện cho input, thuật toán, precision, compiler và topology thực tế. Một microbenchmark tốt có thể kiểm tra một thành phần, nhưng không thay thế end-to-end benchmark.

### Quy trình benchmark

1. Xác định bài toán, input size, độ chính xác và tiêu chí kết quả đúng.
2. Chọn baseline một node hoặc cấu hình tham chiếu.
3. Cố định compiler, flags, thư viện, driver và phiên bản code.
4. Warm-up runtime, cache hoặc GPU nếu phù hợp.
5. Đo thời gian từng phase: compute, communication, I/O và checkpoint.
6. Tăng dần số core, rank, node hoặc GPU.
7. Chạy strong scaling và weak scaling riêng.
8. Lặp lại đủ lần để hiểu biến động.
9. Ghi speedup, efficiency, throughput, cost và chất lượng kết quả.
10. Profile bottleneck rồi chỉ thay đổi một nhóm tham số mỗi lần.

### Profiling

Các loại công cụ thường dùng:

- CPU profiler để tìm hot function, call stack và instruction bottleneck.
- Hardware performance counter để đo cache miss, branch, memory bandwidth và IPC.
- MPI profiler để xem thời gian message, collective và wait.
- GPU profiler để đo kernel duration, occupancy, memory transfer và utilization.
- I/O profiler để đo read/write throughput, metadata operation và checkpoint time.

Khi phân tích, phân biệt thời gian CPU đang tính toán với thời gian tiến trình chờ giao tiếp hoặc storage. CPU utilization thấp trong một job MPI có thể là dấu hiệu tiến trình đang chờ rank khác hoặc chờ I/O.

### Báo cáo benchmark cần có

- Model CPU/GPU, node type, số node và topology.
- Số rank, thread, GPU và binding/pinning.
- Phiên bản compiler, MPI, runtime, driver và thư viện.
- Kích thước input, precision và tham số thuật toán.
- Time-to-solution và thời gian từng phase.
- Speedup, parallel efficiency và strong/weak scaling.
- Network latency/bandwidth, memory bandwidth và I/O metrics liên quan.
- Số lần chạy, độ biến động và điều kiện môi trường.
- Chi phí trên mỗi kết quả hoàn tất.

## 16. Ví dụ: mô phỏng chất lưu phân tán

Một ứng dụng mô phỏng chất lưu chia miền không gian thành lưới 3D. Mỗi MPI rank giữ một phần lưới, tính các bước cập nhật và trao đổi halo cells với các rank lân cận.

Giả sử một lần chạy baseline trên 1 node mất 120 phút. Khi tăng lên 4 node, job mất 38 phút:

\[
S(4) = \frac{120}{38} \approx 3.16
\]

\[
E(4) = \frac{3.16}{4} \approx 79\%
\]

Speedup chưa đạt tuyến tính. Nhóm cần profile:

- Tỷ lệ thời gian trao đổi halo so với compute.
- Số message và kích thước message.
- Thời gian chờ ở collective/barrier.
- Load imbalance giữa các miền lưới.
- Memory bandwidth và NUMA placement.
- I/O checkpoint và output.

Nếu communication chiếm tỷ lệ lớn, có thể tăng kích thước miền trên mỗi rank, giảm số lần đồng bộ, overlap compute/communication hoặc dùng interconnect latency thấp hơn. Nếu memory-bound, cần cải thiện data layout, locality và vectorization. Nếu load imbalance cao, cần phân vùng lại miền hoặc dùng partitioning phù hợp.

Không nên kết luận ngay rằng cần thêm node. Thêm node có thể làm miền mỗi rank nhỏ hơn và tăng tỷ lệ biên cần trao đổi, khiến hiệu năng xấu đi.

## 17. Tối ưu hiệu năng và chi phí trên cloud

HPC cloud cung cấp khả năng tạo cluster theo nhu cầu, chọn nhiều loại CPU/GPU, storage và interconnect. Tuy nhiên, tài nguyên hiệu năng cao có giá cao và thời gian cấp phát/khởi động cũng là một phần của chi phí.

### Chọn cấu hình theo bottleneck

| Bottleneck | Hướng tối ưu có thể thử |
|---|---|
| Compute-bound | CPU/GPU có throughput phù hợp, vectorization, tối ưu kernel |
| Memory-bound | RAM bandwidth cao, locality, NUMA binding, data layout |
| Communication-bound | Interconnect latency thấp, bandwidth cao, topology-aware placement, giảm collective |
| I/O-bound | Parallel storage, batching, caching, giảm file nhỏ và metadata operation |
| Load imbalance | Repartition, dynamic scheduling hoặc điều chỉnh kích thước task |
| Startup/queue delay | Giữ capacity nền, image/boot tối ưu, scheduler policy và reservation |

### Cost per solution

Một cấu hình đắt hơn theo giờ vẫn có thể rẻ hơn nếu hoàn thành job nhanh hơn đáng kể. Chỉ số nên so sánh:

\[
CostPerSolution =
\frac{ComputeCost + StorageCost + NetworkCost + OtherCost}
{NumberOfValidResults}
\]

Ví dụ, cấu hình A tốn 10 đơn vị/giờ và chạy 4 giờ, tổng compute cost là 40. Cấu hình B tốn 18 đơn vị/giờ nhưng chạy 1,5 giờ, tổng compute cost là 27. Nếu kết quả và độ chính xác tương đương, cấu hình B có thể hiệu quả hơn dù đơn giá theo giờ cao hơn.

Phải tính cả thời gian chờ, storage, truyền dữ liệu, license, checkpoint và tài nguyên idle. Với workload chạy theo đợt, tự động tạo cluster trước job và xóa sau khi hoàn tất có thể giảm chi phí, nhưng cần giữ lại log và kết quả bền vững.

### Spot/interruptible trong HPC

Một số batch workload có thể chạy trên capacity có thể bị thu hồi nếu có checkpoint, retry và scheduler hỗ trợ thay node. Tuy nhiên, MPI job đồng bộ nhiều node có thể bị ảnh hưởng lớn khi một node bị mất; cả job có thể phải restart từ checkpoint. Cần so sánh chi phí tiết kiệm với thời gian chạy lại, khả năng cấp phát lại và deadline.

Không nên đặt mọi thành phần điều phối hoặc storage stateful trên capacity có thể bị thu hồi chỉ vì giá thấp.

## 18. Tính đúng đắn và khả năng tái lập kết quả

HPC tối ưu hiệu năng nhưng vẫn phải bảo đảm kết quả khoa học/kỹ thuật đúng. Một thay đổi compiler, precision, thứ tự phép cộng hoặc thuật toán song song có thể làm kết quả khác do floating-point arithmetic không kết hợp hoàn toàn.

### Determinism và reproducibility

Để tái lập:

- Ghi lại source commit và build artifact.
- Ghi compiler, flags, MPI, runtime, driver và thư viện.
- Lưu input dataset, seed, tham số và precision.
- Lưu số rank/thread/GPU và cấu hình topology.
- Ghi cách tổng hợp kết quả và tolerance số học.
- Lưu checkpoint/output với checksum và version.

Kết quả floating-point giữa các cấu hình song song khác nhau có thể sai khác nhỏ do thứ tự reduction. Cần xác định tolerance và tiêu chí khoa học, không chỉ so sánh byte-for-byte nếu thuật toán không bảo đảm determinism.

### Kiểm thử

- Unit test cho kernel và phép toán cơ bản.
- Reference test với input nhỏ có kết quả đã biết.
- Regression test cho output và tolerance.
- Conservation/invariant checks cho mô phỏng vật lý nếu phù hợp.
- Test nhiều số rank/thread để phát hiện race hoặc lỗi partition.
- Restart test từ checkpoint để xác minh phục hồi.

## 19. Những sai lầm thường gặp

1. **Coi HPC như web service:** dùng RPS và replica count làm thước đo chính cho job nhiều node.
2. **Giả định thêm core luôn nhanh hơn:** bỏ qua phần tuần tự, communication và memory bottleneck.
3. **Chỉ nhìn peak FLOPS:** không đo sustained performance trên workload thật.
4. **Dùng GPU cho mọi phép tính:** bỏ qua transfer, branching, precision và khả năng song song.
5. **Oversubscription CPU:** tạo nhiều thread/rank hơn số core được cấp.
6. **Bỏ qua NUMA và pinning:** thread truy cập memory remote hoặc cạnh tranh cache.
7. **Interconnect không phù hợp:** dùng mạng thông thường cho workload MPI nhạy latency mà không benchmark.
8. **Chia miền quá nhỏ:** tăng tỷ lệ giao tiếp trên tính toán.
9. **Không đo load imbalance:** một rank chậm làm cả job chờ.
10. **Checkpoint chỉ trên local disk:** mất khả năng restart khi node bị thay thế.
11. **Đo benchmark không tái lập:** thay đổi compiler, input hoặc topology giữa các lần chạy.
12. **Tối ưu đơn giá theo giờ:** bỏ qua cost per solution và thời gian chờ scheduler.

## 20. Checklist thiết kế và đánh giá workload HPC

- [ ] Đã mô tả bài toán, input size, output và tiêu chí đúng.
- [ ] Đã xác định workload compute-bound, memory-bound, communication-bound hay I/O-bound theo từng phase.
- [ ] Đã chọn mô hình shared-memory, distributed-memory, data/task parallelism hoặc hybrid phù hợp.
- [ ] Số MPI rank, OpenMP thread và GPU khớp allocation.
- [ ] CPU/GPU, RAM, NUMA và precision phù hợp thuật toán.
- [ ] Interconnect đáp ứng latency, bandwidth và topology cần thiết.
- [ ] Storage đáp ứng throughput, IOPS, metadata và checkpoint.
- [ ] Scheduler có queue, partition, walltime và priority phù hợp.
- [ ] Có checkpoint bền vững và restart test.
- [ ] Đã đo time-to-solution, speedup, efficiency và throughput.
- [ ] Đã chạy strong scaling và weak scaling đúng cách.
- [ ] Đã profile CPU, MPI, GPU, memory và I/O theo phase.
- [ ] Có báo cáo benchmark ghi đầy đủ phần cứng và phần mềm.
- [ ] Có kiểm thử tính đúng đắn và khả năng tái lập kết quả.
- [ ] Đã tính cost per solution và thời gian chờ tài nguyên.
- [ ] Có chính sách dọn cluster và bảo toàn output sau job.

## 21. Bài tập vận dụng

Một nhóm khoa học chạy mô phỏng trên lưới 3D. Baseline trên 1 node mất 90 phút. Khi dùng 4 node, thời gian giảm còn 30 phút. Khi tăng lên 8 node, thời gian chỉ còn 24 phút. Profile cho thấy 35% thời gian ở cấu hình 8 node dành cho MPI communication và barrier; memory bandwidth trên mỗi node đã gần mức bão hòa.

1. Tính speedup và parallel efficiency ở 4 node và 8 node so với baseline.
2. Kết quả có thể hiện strong scaling tốt hay không? Giải thích.
3. Vì sao tăng gấp đôi số node từ 4 lên 8 không làm job nhanh gấp đôi?
4. Nên điều tra những yếu tố nào trong domain decomposition, MPI communication và load balance?
5. Nếu workload memory-bound, việc thêm CPU core có thể giúp tới mức nào?
6. Đề xuất các chỉ số cần thu thập trong lần benchmark tiếp theo.

Gợi ý: speedup 4 node là 90/30 = 3, efficiency 3/4 = 75%. Speedup 8 node là 90/24 = 3,75, efficiency 3,75/8 ≈ 46,9%. Đây là strong scaling vì kích thước bài toán giữ nguyên. Communication/barrier và memory bandwidth bão hòa làm giảm lợi ích khi tăng node. Hãy kiểm tra kích thước miền mỗi rank, tỷ lệ halo, message count/size, collective, rank imbalance, NUMA và memory access. Theo dõi time-to-solution, phase time, MPI wait, network latency/bandwidth, memory bandwidth, cache miss và cost per solution.

## Kết luận

HPC giải quyết bài toán tính toán lớn bằng cách phối hợp CPU, GPU, bộ nhớ, mạng và storage trên một hoặc nhiều node. Khác với web service tập trung vào request latency và replica, workload HPC thường có job dài, tiến trình phối hợp và chi phí communication đáng kể. Hiệu năng cần được đánh giá bằng time-to-solution, speedup, parallel efficiency, FLOPS, memory bandwidth, network metrics và cost per solution. Chọn đúng mô hình song song, cấu hình phần cứng, interconnect, scheduler và checkpoint — rồi benchmark, profile theo từng phase — giúp mở rộng workload có cơ sở thay vì chỉ tăng số node.
