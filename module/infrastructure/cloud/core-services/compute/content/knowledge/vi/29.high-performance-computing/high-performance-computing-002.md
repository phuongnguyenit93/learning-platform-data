# Scale-up, scale-out và phần có thể song song hóa

Khi một workload tính toán cần xử lý nhiều dữ liệu hơn hoặc hoàn thành nhanh hơn, có hai hướng tăng năng lực thường gặp. **Scale-up** tăng tài nguyên của một máy hoặc một node, chẳng hạn thêm CPU, bộ nhớ, băng thông bộ nhớ hoặc accelerator. **Scale-out** phân phối công việc lên nhiều node để tổng năng lực đến từ cả cụm. Cả hai hướng chỉ đem lại lợi ích khi workload có thể sử dụng phần tài nguyên được bổ sung.

Một chương trình không tự động chạy nhanh gấp đôi khi số core tăng gấp đôi. Một phần công việc có thể phải thực hiện tuần tự; các phần song song có thể cần trao đổi dữ liệu, đồng bộ hoặc chờ I/O. Khi số worker tăng, chi phí phối hợp đôi khi lớn hơn lượng tính toán tiết kiệm được. Vì vậy, quyết định scale-up hay scale-out phải dựa trên cấu trúc thuật toán, mức song song hóa, giới hạn bộ nhớ và mạng, cách chia dữ liệu, cùng mục tiêu hiệu năng và chi phí.

Bài học này thuộc chương **Điện toán hiệu năng cao** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong HPC, hiểu scale-up, scale-out và phần có thể song song hóa giúp chọn cấu hình compute phù hợp, dự báo hiệu năng và tránh chi phí tăng mà thời gian chạy không giảm tương ứng.

## 1. Scale-up và scale-out là gì?

### 1.1. Scale-up (vertical scaling)

Scale-up tăng năng lực của một node hiện có hoặc chuyển workload sang node lớn hơn.

Các tài nguyên có thể tăng:
- Số core hoặc vCPU.
- Dung lượng và băng thông bộ nhớ.
- Tốc độ hoặc số lượng accelerator như GPU.
- Năng lực I/O và storage bandwidth.
- Network bandwidth của node.
- Cache CPU hoặc khả năng truy cập bộ nhớ NUMA.

Ví dụ, một tác vụ mô phỏng chạy trên máy 16 core và 128 GiB RAM có thể được chuyển sang máy 64 core và 512 GiB RAM. Nếu phần lớn thời gian chạy là tính toán có thể song song trên core, thời gian hoàn thành có thể giảm đáng kể.

Scale-up thường đơn giản hơn về lập trình vì dữ liệu có thể nằm trong một không gian bộ nhớ chia sẻ. Tuy nhiên, nó có giới hạn phần cứng, chi phí node lớn, khả năng mở rộng không liên tục và có thể tạo một điểm lỗi tập trung.

### 1.2. Scale-out (horizontal scaling)

Scale-out phân phối workload lên nhiều node kết nối qua mạng. Mỗi node có CPU, memory và thiết bị I/O riêng; các node trao đổi dữ liệu bằng message passing, collective communication, storage dùng chung hoặc cơ chế phân phối của framework.

Ví dụ:
- Chạy mô phỏng miền không gian trên 32 node.
- Chia tập dữ liệu thành nhiều partition để xử lý đồng thời.
- Phân phối các batch inference lên nhiều GPU worker.
- Chạy nhiều job độc lập trên một cluster HPC.

Scale-out có thể mở rộng tổng năng lực vượt giới hạn một máy, đồng thời tận dụng nhiều node phổ thông. Đổi lại, ứng dụng phải xử lý phân vùng dữ liệu, giao tiếp mạng, đồng bộ, lỗi node và kết quả phân tán.

### 1.3. So sánh nhanh

| Tiêu chí | Scale-up | Scale-out |
|---|---|---|
| Cách tăng năng lực | Thêm tài nguyên trong một node | Thêm node vào cụm |
| Bộ nhớ | Thường dùng bộ nhớ chia sẻ trong node | Mỗi node có bộ nhớ riêng, cần trao đổi dữ liệu |
| Giao tiếp | Thread, shared memory, local interconnect | Network, message passing, distributed storage |
| Độ phức tạp ứng dụng | Thường thấp hơn nếu chương trình đã hỗ trợ đa luồng | Thường cao hơn do partition và coordination |
| Giới hạn | Trần phần cứng và chi phí node lớn | Network, synchronization, data distribution và scheduler |
| Khả năng mở rộng | Có thể tăng theo các bậc cấu hình máy | Có thể thêm nhiều node, tùy hiệu suất song song |
| Lỗi | Node lỗi có thể làm dừng toàn bộ tiến trình | Cần xử lý node lỗi và trạng thái phân tán |
| Phù hợp | Workload cần shared memory hoặc dữ liệu tập trung | Workload chia được thành nhiều phần tương đối độc lập |

Không có lựa chọn nào luôn tốt hơn. Một kiến trúc HPC thường kết hợp scale-up trong mỗi node và scale-out giữa các node.

### 1.4. Scale-up bên trong, scale-out bên ngoài

Một cluster có thể gồm nhiều node lớn, mỗi node có nhiều CPU core và một hoặc nhiều GPU. Chương trình dùng thread hoặc GPU kernel trong node, sau đó dùng MPI hoặc distributed runtime giữa các node.

Mô hình này thường được gọi là hybrid parallelism:
- Intra-node parallelism: tận dụng core, thread, shared memory và accelerator trong node.
- Inter-node parallelism: chia workload qua nhiều node và trao đổi dữ liệu qua mạng.

Hybrid không tự động nhanh hơn. Cần tránh oversubscription thread, tranh chấp memory bandwidth và số lượng message quá lớn.

## 2. Xác định phần nào có thể song song hóa

### 2.1. Phân rã công việc

Trước khi tăng số core hoặc node, cần phân tích thuật toán thành:
- Phần bắt buộc chạy tuần tự.
- Phần có thể chạy đồng thời.
- Phần cần trao đổi dữ liệu.
- Phần phải chờ kết quả từ các phần khác.
- Phần đọc/ghi dữ liệu.
- Phần khởi tạo và kết thúc.

Ví dụ một pipeline phân tích dữ liệu có thể gồm:
1. Đọc file đầu vào.
2. Chuẩn hóa dữ liệu.
3. Chia dữ liệu thành partition.
4. Tính toán trên từng partition.
5. Gộp kết quả.
6. Ghi báo cáo.

Bước 4 có thể song song mạnh nếu các partition độc lập. Bước 5 có thể cần reduction hoặc shuffle. Bước 1 và 6 có thể trở thành bottleneck nếu storage không đủ throughput.

### 2.2. Data parallelism

Data parallelism chia dữ liệu thành nhiều phần và chạy cùng một phép tính trên từng phần.

Ví dụ:
- Chia ảnh thành các tile để xử lý.
- Chia ma trận thành block.
- Chia tập dữ liệu theo range hoặc partition.
- Chia miền mô phỏng thành subdomain.

Mô hình này phù hợp khi mỗi phần dữ liệu có thể xử lý độc lập hoặc chỉ cần trao đổi dữ liệu ở một số ranh giới.

### 2.3. Task parallelism

Task parallelism chia công việc thành các tác vụ khác nhau, có thể thực hiện đồng thời.

Ví dụ một pipeline có các tác vụ:
- Giải mã dữ liệu.
- Tính feature.
- Kiểm tra chất lượng.
- Ghi metadata.
- Tạo preview.

Các tác vụ có thể có thời gian chạy và tài nguyên khác nhau. Scheduler cần cân bằng tải và quản lý dependency giữa chúng.

### 2.4. Pipeline parallelism

Pipeline parallelism chia một quy trình thành các stage, mỗi stage xử lý một phần dữ liệu rồi chuyển kết quả sang stage tiếp theo.

Ví dụ:
- Stage A đọc và giải mã.
- Stage B biến đổi.
- Stage C tính toán.
- Stage D ghi kết quả.

Khi pipeline đã được lấp đầy, nhiều stage có thể xử lý các item khác nhau cùng lúc. Throughput có thể tăng, nhưng latency của một item vẫn phụ thuộc tổng thời gian qua các stage. Stage chậm nhất giới hạn throughput của cả pipeline.

### 2.5. Embarrassingly parallel

Một workload được gọi là embarrassingly parallel khi các phần công việc gần như độc lập và cần rất ít giao tiếp.

Ví dụ:
- Render từng frame độc lập.
- Chạy nhiều mô phỏng với các bộ tham số khác nhau.
- Xử lý từng file độc lập.
- Tìm kiếm hoặc đánh giá nhiều candidate riêng biệt.

Đây thường là ứng viên tốt cho scale-out vì chi phí phối hợp thấp. Tuy nhiên, vẫn cần tổng hợp kết quả, quản lý input/output, phân phối task và xử lý task thất bại.

### 2.6. Phụ thuộc dữ liệu và đồ thị công việc

Không phải tác vụ nào cũng chạy song song được. Nếu bước B cần kết quả của bước A, B phải đợi A. Một workload có thể biểu diễn thành directed acyclic graph (DAG) khi không có chu trình phụ thuộc trong lần thực thi đó.

~~~mermaid
flowchart TD
    A["Đọc dữ liệu"] --> B["Chuẩn hóa"]
    B --> C1["Partition 1"]
    B --> C2["Partition 2"]
    B --> C3["Partition 3"]
    C1 --> D["Gộp kết quả"]
    C2 --> D
    C3 --> D
    D --> E["Ghi kết quả"]
~~~

Các partition có thể chạy song song. Bước gộp phải đợi tất cả partition cần thiết hoàn tất. Nếu một partition chậm hơn nhiều, nó có thể quyết định thời gian hoàn thành của cả DAG.

## 3. Định luật Amdahl: giới hạn từ phần tuần tự

### 3.1. Công thức

Định luật Amdahl ước lượng mức tăng tốc tối đa khi một phần chương trình có thể song song hóa, còn phần còn lại phải chạy tuần tự.

Gọi:
- P là tỷ lệ thời gian có thể song song hóa, từ 0 đến 1.
- 1 − P là tỷ lệ thời gian tuần tự.
- N là số đơn vị xử lý.

Speedup lý tưởng:

\[
S(N) = \frac{1}{(1-P) + \frac{P}{N}}
\]

Công thức giả định phần song song được chia đều và không có overhead giao tiếp, đồng bộ, khởi tạo hoặc I/O. Hiệu năng thực tế thường thấp hơn.

### 3.2. Ví dụ với 90% công việc song song

Giả sử 90% thời gian chương trình có thể chạy song song, còn 10% phải chạy tuần tự.

| Số core | Speedup lý tưởng | Hiệu suất song song |
|---:|---:|---:|
| 1 | 1,00× | 100% |
| 2 | 1,82× | 91% |
| 4 | 3,08× | 77% |
| 8 | 4,71× | 59% |
| 16 | 6,40× | 40% |
| 32 | 7,80× | 24% |
| 64 | 8,77× | 14% |

Dù tăng từ 8 lên 64 core, speedup chỉ tăng từ khoảng 4,71 lên 8,77 lần. Phần tuần tự trở thành giới hạn rõ rệt.

### 3.3. Giới hạn khi số core tiến tới vô hạn

Khi N tiến tới vô hạn, phần P có thể được xử lý gần như tức thời, nhưng phần tuần tự vẫn còn:

\[
S_{\max} = \frac{1}{1-P}
\]

Nếu P = 0,9 thì speedup tối đa chỉ là 10 lần. Nếu P = 0,99 thì giới hạn lý tưởng là 100 lần.

Điều này cho thấy tối ưu phần tuần tự có thể đem lại lợi ích lớn hơn việc tiếp tục thêm core khi workload đã gần giới hạn Amdahl.

### 3.4. Tìm phần tuần tự trong chương trình

Phần tuần tự có thể nằm ở:
- Khởi tạo dữ liệu và đọc cấu hình.
- Parse hoặc serialize dữ liệu lớn.
- Một vòng lặp phụ thuộc kết quả vòng trước.
- Giai đoạn reduction hoặc aggregation.
- Lock hoặc critical section.
- Ghi checkpoint hoặc metadata.
- Một service trung tâm mà mọi worker phải gọi.

Cần dùng profiler và trace để tìm bottleneck thực tế. Không nên chỉ nhìn vào số dòng code hoặc phỏng đoán rằng vòng lặp dài nhất là phần tốn thời gian nhất.

## 4. Định luật Gustafson và bài toán tăng kích thước

### 4.1. Vì sao Amdahl chưa mô tả mọi workload?

Amdahl thường xét bài toán có kích thước cố định: khi tăng số core, ta muốn hoàn thành cùng một lượng công việc nhanh hơn.

Trong HPC, khi có thêm tài nguyên, người dùng thường muốn giải bài toán lớn hơn:
- Mô phỏng miền không gian chi tiết hơn.
- Tăng độ phân giải mô hình.
- Dùng tập dữ liệu lớn hơn.
- Tăng số mẫu hoặc số kịch bản.
- Tăng kích thước mô hình khoa học.

Gustafson mô tả trường hợp kích thước bài toán tăng theo năng lực xử lý.

### 4.2. Công thức Gustafson

Gọi:
- N là số đơn vị xử lý.
- α là phần tuần tự đo trong thời gian chạy song song đã mở rộng.

Speedup theo mô hình Gustafson:

\[
S_G(N) = N - \alpha(N-1)
\]

Ví dụ α = 0,05 và N = 32:

\[
S_G = 32 - 0,05 \times 31 = 30,45
\]

Kết quả lý tưởng cho thấy nếu phần tuần tự nhỏ và bài toán mở rộng theo tài nguyên, có thể tận dụng nhiều node hiệu quả hơn.

### 4.3. Khi dùng Amdahl và khi dùng Gustafson?

| Câu hỏi | Mô hình phù hợp |
|---|---|
| Cùng một bộ dữ liệu, tăng core để giảm thời gian? | Amdahl / strong scaling |
| Tăng số node để xử lý bài toán lớn hơn trong thời gian tương tự? | Gustafson / weak scaling |
| Tăng node nhưng dữ liệu và giao tiếp cũng tăng? | Cần benchmark thực tế, cả hai mô hình chỉ là ước lượng |
| Workload bị giới hạn bởi I/O hoặc network? | Cần phân tích bottleneck ngoài CPU |

Không dùng công thức Gustafson để khẳng định hệ thống chắc chắn scale tuyến tính. Nếu dữ liệu trao đổi hoặc chi phí đồng bộ tăng nhanh theo số node, hiệu năng sẽ giảm.

## 5. Strong scaling và weak scaling

### 5.1. Strong scaling

Strong scaling giữ nguyên kích thước bài toán và tăng số đơn vị xử lý.

Ví dụ:
- Cùng một mô phỏng 1 TB dữ liệu.
- Chạy trên 8, 16, 32 và 64 node.
- Đo thời gian hoàn thành và speedup.

Speedup:

\[
S(N) = \frac{T(1)}{T(N)}
\]

Hiệu suất song song:

\[
E(N) = \frac{S(N)}{N}
\]

Trong đó T(1) và T(N) phải được đo với cùng workload và cùng điều kiện so sánh.

Strong scaling giúp trả lời: có thể rút ngắn thời gian bao nhiêu khi thêm tài nguyên cho cùng một bài toán?

### 5.2. Weak scaling

Weak scaling tăng kích thước bài toán tương ứng với số đơn vị xử lý, để lượng công việc trên mỗi đơn vị xử lý gần như giữ nguyên.

Ví dụ:
- 1 node xử lý 10 triệu phần tử.
- 8 node xử lý 80 triệu phần tử.
- 32 node xử lý 320 triệu phần tử.

Nếu thời gian hoàn thành gần như không đổi khi tổng dữ liệu tăng theo số node, weak scaling tốt.

### 5.3. So sánh

| Đặc điểm | Strong scaling | Weak scaling |
|---|---|---|
| Tổng kích thước bài toán | Giữ nguyên | Tăng theo số worker/node |
| Mục tiêu | Giảm thời gian hoàn thành | Tăng kích thước bài toán với thời gian gần ổn định |
| Đại lượng quan tâm | Speedup, efficiency | Thời gian ở mỗi mức quy mô |
| Bottleneck thường thấy | Phần tuần tự, communication, synchronization | Network, storage, partition và global coordination |
| Ứng dụng | Rút ngắn một mô phỏng hoặc phân tích cụ thể | Mô phỏng lớn hơn, độ phân giải cao hơn |

### 5.4. Khi nào strong scaling không còn hiệu quả?

Nếu mỗi node chỉ còn xử lý một lượng dữ liệu rất nhỏ, overhead khởi tạo, communication và synchronization có thể chiếm phần lớn thời gian. Thêm node làm speedup tăng rất ít hoặc thậm chí làm chương trình chậm hơn.

Điểm dừng hợp lý là nơi lợi ích giảm thời gian hoặc tăng quy mô không còn bù được chi phí tài nguyên và vận hành.

## 6. Overhead của song song hóa

### 6.1. Communication overhead

Các worker cần trao đổi dữ liệu:
- Gửi input và nhận output.
- Trao đổi biên giữa các subdomain.
- Gộp kết quả.
- Đồng bộ trạng thái.
- Phân phối metadata và task.

Communication overhead phụ thuộc kích thước message, số lần giao tiếp, topology mạng, latency và bandwidth.

### 6.2. Latency và bandwidth

- **Latency:** thời gian để một thao tác giao tiếp bắt đầu có kết quả.
- **Bandwidth:** lượng dữ liệu có thể truyền trong một đơn vị thời gian.

Một workload gửi nhiều message nhỏ có thể bị giới hạn bởi latency. Workload truyền các block lớn có thể bị giới hạn bởi bandwidth.

Vì vậy, tăng network bandwidth không giải quyết được mọi vấn đề. Nếu thuật toán thực hiện quá nhiều vòng giao tiếp đồng bộ, latency vẫn có thể là bottleneck.

### 6.3. Synchronization overhead

Barrier hoặc collective operation yêu cầu worker chờ nhau. Worker nhanh nhất vẫn phải đợi worker chậm nhất tại điểm đồng bộ.

Các nguyên nhân:
- Phân chia workload không đều.
- Node có hiệu năng khác nhau.
- Một partition chứa nhiều dữ liệu hơn.
- I/O của một worker chậm.
- Network congestion.
- Một node đang bị contention.

Giảm số lần barrier và chọn ranh giới đồng bộ hợp lý có thể cải thiện hiệu năng.

### 6.4. Load imbalance

Nếu một worker nhận 10% dữ liệu nhưng phải xử lý 50% thời gian, các worker còn lại có thể chờ.

Có thể giảm mất cân bằng bằng:
- Static partition khi workload đồng đều và dễ dự đoán.
- Dynamic scheduling khi thời gian từng task khó dự đoán.
- Work stealing khi framework hỗ trợ.
- Chia task nhỏ hơn để phân phối lại.
- Ước lượng chi phí task trước khi lập lịch.

Task quá nhỏ làm tăng scheduling overhead; task quá lớn làm giảm khả năng cân bằng tải.

### 6.5. Contention và false sharing

Trong shared-memory parallelism:
- Nhiều thread có thể tranh chấp cùng lock.
- Nhiều core có thể tranh chấp memory bandwidth.
- False sharing xảy ra khi các thread cập nhật biến khác nhau nhưng nằm trên cùng cache line, khiến cache coherence traffic tăng.
- NUMA remote memory access có thể chậm hơn truy cập local memory.

Tăng số thread mà không phân tích memory locality có thể làm throughput giảm.

### 6.6. I/O bottleneck

Một chương trình có thể tính toán song song rất tốt nhưng bị giới hạn bởi:
- Đọc dữ liệu từ object storage.
- Nhiều node cùng đọc một file lớn.
- Metadata server của parallel file system.
- Checkpoint ghi đồng thời.
- Giai đoạn serialize hoặc tổng hợp output.

Cần đo thời gian CPU, memory stall, network và I/O riêng. Tăng CPU khi storage đã bão hòa thường không giúp.

## 7. Mô hình lập trình song song

### 7.1. Shared-memory threading

Nhiều thread chạy trong một process và chia sẻ address space.

Ví dụ công nghệ:
- POSIX threads.
- OpenMP.
- Thread pool trong runtime.
- Task runtime của ngôn ngữ.

Ưu điểm:
- Chia sẻ dữ liệu trực tiếp.
- Giao tiếp giữa thread có thể nhanh.
- Phù hợp scale-up trong một node.

Thách thức:
- Race condition.
- Lock contention.
- Deadlock.
- Memory visibility.
- False sharing.
- Khó mở rộng vượt giới hạn một node.

### 7.2. Message passing

Các process có bộ nhớ riêng và trao đổi message qua thư viện hoặc runtime. MPI là mô hình phổ biến trong HPC cluster.

Ưu điểm:
- Có thể mở rộng qua nhiều node.
- Ranh giới dữ liệu rõ.
- Phù hợp các mô phỏng phân vùng.

Thách thức:
- Phải serialize hoặc đóng gói dữ liệu.
- Communication latency.
- Deadlock do thứ tự send/receive.
- Đồng bộ và xử lý process lỗi.
- Khó debug khi lỗi chỉ xuất hiện ở quy mô lớn.

### 7.3. GPU và accelerator

GPU có nhiều đơn vị xử lý song song, phù hợp các phép tính có nhiều phần tử độc lập và cấu trúc dữ liệu phù hợp.

GPU thường hiệu quả khi:
- Có đủ công việc song song.
- Dữ liệu có thể được giữ trên device đủ lâu.
- Memory access có tính locality/coalescing tốt.
- Chi phí chuyển dữ liệu host-device không chiếm phần lớn.
- Kernel đủ lớn để bù chi phí launch.

Không phải mọi thuật toán đều phù hợp GPU. Các tác vụ nhiều nhánh rẽ, phụ thuộc tuần tự hoặc dữ liệu nhỏ có thể không đạt lợi ích mong muốn.

### 7.4. Hybrid MPI + OpenMP + GPU

Một node có thể chạy nhiều MPI rank, mỗi rank dùng nhiều OpenMP thread và một hoặc nhiều GPU.

Ví dụ cấu hình minh họa:
- 4 MPI ranks trên mỗi node.
- Mỗi rank sử dụng 8 OpenMP threads.
- Mỗi rank gắn với một GPU.

Tổng số thread CPU và GPU phải khớp với topology thực tế. Nếu mỗi rank tạo quá nhiều thread, có thể xảy ra oversubscription và tranh chấp memory.

### 7.5. Distributed data frameworks

Một số workload không cần MPI trực tiếp. Framework phân tán có thể:
- Chia dữ liệu thành partition.
- Lập lịch task.
- Quản lý shuffle.
- Retry task lỗi.
- Cache dữ liệu trung gian.
- Tổng hợp kết quả.

Framework giúp giảm công sức điều phối nhưng không xóa chi phí network, serialization, skew và storage.

## 8. Chọn scale-up hay scale-out theo đặc điểm workload

### 8.1. Workload cần bộ nhớ chia sẻ lớn

Nếu một thuật toán cần nhiều thread truy cập chung cấu trúc dữ liệu và khó partition, node lớn với RAM lớn có thể phù hợp.

Ví dụ:
- Graph analytics với nhiều truy cập ngẫu nhiên.
- Một số mô hình mô phỏng có trạng thái toàn cục.
- In-memory database hoặc solver cần shared memory.

Cần đo memory bandwidth, NUMA locality và lock contention; chỉ tăng dung lượng RAM không giải quyết được bottleneck băng thông.

### 8.2. Workload có thể chia thành partition

Nếu dữ liệu có thể chia thành block hoặc subdomain và mỗi node xử lý phần riêng, scale-out có thể hiệu quả.

Ví dụ:
- Mô phỏng CFD chia lưới không gian.
- Phân tích ảnh theo tile.
- Xử lý dữ liệu theo partition.
- Rendering theo frame.
- Nhiều lần chạy mô hình với tham số khác nhau.

Cần đánh giá lượng dữ liệu biên và số lần trao đổi giữa partition.

### 8.3. Workload compute-bound

Compute-bound nghĩa thời gian chủ yếu bị giới hạn bởi năng lực tính toán. Nếu phần tính toán song song lớn, tăng core hoặc GPU có thể đem lại lợi ích.

Kiểm tra:
- CPU/GPU utilization.
- Instruction throughput.
- Vectorization.
- Kernel occupancy.
- Arithmetic intensity.
- Thời gian chờ memory.

### 8.4. Workload memory-bound

Memory-bound nghĩa workload bị giới hạn bởi tốc độ hoặc độ trễ truy cập memory.

Tăng số core có thể không cải thiện nếu các core cùng tranh chấp memory bandwidth. Cần xem:
- Memory bandwidth.
- Cache miss.
- Memory locality.
- NUMA placement.
- Kích thước working set.
- Data layout và vectorization.

Scale-up sang node có memory bandwidth cao hoặc thay đổi data layout có thể hữu ích hơn tăng số node.

### 8.5. Workload communication-bound

Nếu mỗi bước tính toán cần nhiều lần trao đổi dữ liệu giữa node, scale-out có thể kém hiệu quả. Cần:
- Giảm số vòng giao tiếp.
- Gộp message nhỏ.
- Tăng compute-to-communication ratio.
- Chọn network low-latency/high-bandwidth.
- Đặt các node gần nhau về topology nếu nền tảng hỗ trợ.
- Giảm global synchronization.

### 8.6. Workload có nhiều job độc lập

Nếu có nhiều job độc lập, scale-out theo số job thường đơn giản hơn việc chia một job duy nhất thành nhiều node.

Ví dụ:
- 500 bộ tham số mô phỏng.
- 10.000 file cần xử lý.
- Nhiều model training độc lập.
- Nhiều batch inference.

Scheduler có thể chạy mỗi job trên một node hoặc nhóm node. Khi đó cần tối ưu throughput cụm, fairness, queue wait và chi phí thay vì chỉ đo speedup của một job.

## 9. Thiết kế phân vùng dữ liệu

### 9.1. Domain decomposition

Trong mô phỏng vật lý hoặc khoa học, miền bài toán được chia thành các subdomain. Mỗi node xử lý một phần và trao đổi dữ liệu biên với node lân cận.

Ví dụ:
- Lưới 3D chia theo trục X/Y/Z.
- Mỗi node tính cập nhật cho các cell nội bộ.
- Mỗi bước thời gian trao đổi halo/ghost cells với node lân cận.
- Sau đó tiếp tục bước tính toán kế tiếp.

Nếu subdomain quá nhỏ, tỷ lệ halo data so với dữ liệu nội bộ tăng và communication overhead lớn. Nếu quá lớn, số node ít hơn và có thể không tận dụng đủ capacity.

### 9.2. Data partitioning theo key/range

Với workload dữ liệu:
- Partition theo key có thể giúp truy vấn theo key nhanh.
- Partition theo range có thể giữ dữ liệu liên tiếp.
- Hash partition có thể phân phối đều nếu key phân bố tốt.
- Partition theo tenant có thể cô lập tải.

Cần kiểm tra data skew. Một key hoặc partition quá nóng có thể khiến một worker chậm hơn nhiều so với các worker khác.

### 9.3. Replication và dữ liệu dùng chung

Một số workload cần nhiều node đọc cùng dữ liệu. Có thể:
- Replicate input tới local storage.
- Dùng parallel file system.
- Cache dữ liệu trên node.
- Dùng object storage với request pattern phù hợp.

Replication tăng dung lượng và chi phí truyền; shared storage có thể trở thành bottleneck nếu nhiều node đọc/ghi đồng thời. Chọn theo kích thước dữ liệu, locality và pattern I/O.

## 10. Mạng và topology cho HPC scale-out

### 10.1. Vì sao mạng quan trọng?

Trong cluster HPC, network ảnh hưởng trực tiếp đến:
- MPI point-to-point communication.
- Collective operations như all-reduce.
- Trao đổi halo giữa subdomain.
- Distributed training gradient synchronization.
- Truy cập parallel storage.
- Checkpoint và dữ liệu trung gian.

Network bandwidth cao giúp truyền nhiều dữ liệu, còn latency thấp giúp giảm chi phí của nhiều message nhỏ. Cả hai đều quan trọng với workload communication-heavy.

### 10.2. Ethernet và interconnect hiệu năng cao

Ethernet phổ thông có thể đáp ứng nhiều workload, đặc biệt khi communication không phải bottleneck. Các workload MPI hoặc distributed training nhạy latency có thể hưởng lợi từ interconnect HPC như InfiniBand hoặc giải pháp Ethernet/RDMA được cloud hỗ trợ.

Cần kiểm tra:
- Latency và bandwidth thực tế.
- RDMA hoặc cơ chế tương đương.
- Hỗ trợ của MPI/runtime.
- Placement và topology của node.
- MTU và cấu hình network.
- Khả năng tương thích instance family và region.

Không nên giả định chỉ cần chọn instance có network bandwidth cao là MPI sẽ tự dùng được RDMA. Driver, library, image, scheduler và cấu hình nền tảng đều cần tương thích.

### 10.3. Placement và locality

Đặt các node gần nhau về mặt hạ tầng có thể giảm latency và tăng tính ổn định của network performance. Một số cloud cung cấp placement group, cluster placement hoặc loại instance chuyên cho HPC.

Đổi lại, capacity có thể khan hiếm hơn và khả năng scale có thể bị giới hạn bởi một vùng placement. Cần kiểm tra quota và khả năng cấp đủ node trước khi chạy job lớn.

## 11. Storage và checkpoint trong workload phân tán

### 11.1. Parallel file system

Parallel file system cho phép nhiều node truy cập dữ liệu chung với throughput tổng cao nếu workload và cấu hình phù hợp.

Phù hợp:
- Mô phỏng đọc/ghi file lớn.
- Nhiều node cùng checkpoint.
- Dataset khoa học lớn.
- Workload cần shared filesystem semantics.

Cần kiểm tra metadata operations, file count, stripe size, locking và số client đồng thời. Nhiều file nhỏ có thể làm metadata server quá tải dù bandwidth tổng còn dư.

### 11.2. Object storage

Object storage phù hợp lưu input/output lớn, artifact, checkpoint dài hạn và kết quả đã hoàn tất. Tuy nhiên, pattern truy cập và semantics khác filesystem.

Cần:
- Dùng multipart upload/download khi phù hợp.
- Gộp nhiều file nhỏ nếu request overhead cao.
- Tránh nhiều worker cùng ghi đè một object key.
- Dùng manifest để theo dõi output partition.
- Kiểm tra consistency và retry semantics của SDK.
- Dùng checksum để xác minh dữ liệu.

### 11.3. Checkpoint phân tán

Một job dài có thể checkpoint trạng thái để tiếp tục sau lỗi node hoặc giới hạn thời gian. Trong môi trường nhiều node, checkpoint cần đại diện cho trạng thái nhất quán của toàn job.

Có thể:
1. Đồng bộ worker tại safe point.
2. Ghi state cục bộ hoặc phân tán.
3. Ghi metadata về version, partition và iteration.
4. Hoàn tất mọi write và xác minh.
5. Công bố checkpoint manifest như một recovery point hợp lệ.

Không đánh dấu checkpoint hoàn tất khi chỉ một phần node đã ghi xong. Khi restore, phải biết file nào thuộc cùng một checkpoint generation.

## 12. Đo hiệu năng và scaling efficiency

### 12.1. Baseline

Trước khi scale, đo baseline:
- Thời gian chạy.
- CPU/GPU utilization.
- Memory usage và bandwidth.
- I/O throughput và latency.
- Network bytes/messages.
- Số worker/node.
- Kết quả đầu ra và độ chính xác.

Không so sánh hai cấu hình nếu input, phiên bản code, compiler flag hoặc điều kiện dữ liệu khác nhau mà không ghi nhận.

### 12.2. Speedup

Speedup đo chương trình nhanh hơn bao nhiêu lần so với baseline:

\[
S(N) = \frac{T(1)}{T(N)}
\]

Ví dụ:
- 1 node: 120 phút.
- 4 node: 36 phút.
- Speedup = 120/36 ≈ 3,33 lần.

Nếu tăng từ 1 lên 4 node, speedup lý tưởng là 4 lần. Hiệu suất song song là 3,33/4 ≈ 83,3%.

### 12.3. Parallel efficiency

\[
E(N) = \frac{S(N)}{N}
\]

Efficiency cho biết tỷ lệ hiệu quả so với mức tăng tài nguyên lý tưởng. Efficiency thấp có thể do phần tuần tự, communication, synchronization, load imbalance, I/O hoặc contention.

Efficiency không phải chỉ số duy nhất để chọn cấu hình. Một job có efficiency thấp ở 64 node vẫn có thể là lựa chọn kinh tế nếu thời gian hoàn thành nhanh hơn và chi phí phù hợp.

### 12.4. Cost efficiency

Có thể theo dõi:
- Cost per completed job.
- Cost per simulation timestep.
- Cost per processed TB.
- Cost per training epoch.
- Node-hours hoặc GPU-hours.
- Queue wait và utilization của cluster.

Một cấu hình lớn hơn có thể giảm thời gian nhưng tăng chi phí tổng. So sánh cost-to-solution: chi phí để có một kết quả đúng trong thời gian đáp ứng yêu cầu.

## 13. Quy trình chọn kiến trúc và cấu hình

1. Xác định mục tiêu: giảm thời gian một job hay tăng kích thước bài toán.
2. Đo baseline và profile code.
3. Ước lượng phần tuần tự và phần song song hóa.
4. Xác định workload compute-bound, memory-bound, I/O-bound hay communication-bound.
5. Thử scale-up trên node có số core, RAM, memory bandwidth hoặc GPU phù hợp.
6. Thử scale-out với các mức node count tăng dần.
7. Đo speedup, efficiency, communication và cost.
8. Kiểm tra data partition, load balance và checkpoint.
9. Xác định điểm scale-out bắt đầu có diminishing returns.
10. Chọn cấu hình đạt SLO và cost-to-solution phù hợp.
11. Lưu benchmark, version, input và cấu hình để tái lập.

~~~mermaid
flowchart TD
    A["Xác định mục tiêu và workload"]
    B["Profile baseline"]
    C["Tìm phần tuần tự và bottleneck"]
    D{"Bộ nhớ chia sẻ hoặc node đơn là giới hạn?"}
    E["Thử scale-up"]
    F["Phân vùng dữ liệu và thuật toán"]
    G["Thử scale-out"]
    H["Đo speedup, efficiency, network và I/O"]
    I["So sánh cost-to-solution"]
    J["Chọn cấu hình và lưu benchmark"]
    A --> B --> C --> D
    D -->|Có| E --> H
    D -->|Không| F --> G --> H
    H --> I --> J
~~~

## 14. Ví dụ: mô phỏng chia miền 3D

Một mô phỏng CFD cập nhật 1 tỷ cell trên lưới 3D. Mỗi cell cần giá trị của các cell lân cận trong bước thời gian tiếp theo.

### 14.1. Scale-up trên một node

Chạy trên một node nhiều core:
- Chia lưới thành tile cho các thread.
- Dùng shared memory để trao đổi dữ liệu trong node.
- Tối ưu NUMA placement.
- Dùng vectorization và memory bandwidth cao.

Ưu điểm là không phải trao đổi halo qua network giữa node. Giới hạn là dung lượng RAM, bandwidth và số core của máy.

### 14.2. Scale-out trên nhiều node

Chia lưới thành subdomain:
- Mỗi node sở hữu một phần cell.
- Mỗi node tính cell nội bộ.
- Tại mỗi timestep, node trao đổi halo/ghost cells với node lân cận.
- Sau trao đổi, node tiếp tục tính bước tiếp theo.

Nếu mỗi subdomain có cạnh quá nhỏ, phần halo chiếm tỷ lệ lớn. Nếu tăng số node, lượng compute trên mỗi node giảm trong khi số lần communication vẫn diễn ra theo từng timestep.

### 14.3. Đánh giá

Đo ở 1, 2, 4, 8, 16 node:
- Thời gian tính toán nội bộ.
- Thời gian halo exchange.
- Thời gian barrier.
- Network bytes và message count.
- Memory bandwidth.
- Tổng thời gian mỗi timestep.

Nếu halo exchange chiếm 35% thời gian ở 16 node, thêm node có thể không đem lại speedup tốt. Có thể cải thiện bằng cách tăng kích thước subdomain, gộp communication, tối ưu topology hoặc chạy nhiều timestep trước khi đồng bộ nếu thuật toán cho phép.

Không được thay đổi thứ tự cập nhật hoặc giảm đồng bộ nếu làm thay đổi tính đúng đắn số học của mô phỏng. Cần kiểm tra sai số và tính ổn định của thuật toán.

## 15. Rủi ro khi scale-out và cách giảm thiểu

### 15.1. Node failure

Một node có thể lỗi giữa job. Cần:
- Checkpoint định kỳ.
- Lưu trạng thái theo generation.
- Có retry/restart policy.
- Kiểm tra output chưa hoàn tất.
- Tránh ghi đè kết quả đã commit.
- Có scheduler hỗ trợ requeue khi node bị mất.

### 15.2. Straggler

Một worker chậm hơn phần còn lại có thể kéo dài barrier hoặc DAG. Theo dõi thời gian từng partition và tìm nguyên nhân: data skew, noisy neighbor, memory pressure, network hoặc I/O.

### 15.3. Nondeterminism

Thứ tự cộng số thực trong parallel reduction có thể khác nhau giữa các lần chạy, gây sai khác nhỏ do floating-point rounding. Một số thuật toán còn nhạy với thứ tự cập nhật.

Cần xác định yêu cầu:
- Kết quả bitwise reproducible.
- Kết quả nằm trong tolerance số học.
- Kết quả đúng theo tiêu chí thống kê/nghiệp vụ.

Nếu cần tái lập, có thể dùng reduction có thứ tự cố định, seed rõ ràng và ghi cấu hình chạy.

### 15.4. Scheduler và cluster contention

Nhiều job scale-out cùng lúc có thể tranh chấp node, network và storage. Cần:
- Queue và partition theo loại workload.
- Fair-share hoặc priority.
- Reservation cho job quan trọng.
- Giới hạn số job đồng thời.
- Theo dõi node utilization và queue wait.
- Tránh để một job chiếm toàn bộ cluster không cần thiết.

## 16. Những sai lầm thường gặp

**Cho rằng thêm core luôn làm job nhanh hơn.** Phần tuần tự và overhead giới hạn speedup. Hãy đo Amdahl và profile.

**Chọn scale-out trước khi phân tích thuật toán.** Nếu dữ liệu phụ thuộc chặt hoặc giao tiếp quá nhiều, thêm node có thể làm chậm. Tối ưu decomposition trước.

**Chỉ đo CPU utilization.** Workload có thể bị giới hạn bởi memory, network hoặc storage. Đo cả các tài nguyên liên quan.

**Nhầm speedup với efficiency.** Speedup 8 lần trên 16 node vẫn có efficiency 50%. Cần xem cả thời gian và chi phí.

**Bỏ qua load imbalance.** Worker nhanh phải đợi worker chậm tại barrier. Đo thời gian theo partition.

**Chia task quá nhỏ.** Scheduler và communication overhead có thể vượt chi phí tính toán. Chọn granularity phù hợp.

**Dùng GPU cho mọi phép tính.** Transfer, launch và memory access có thể làm GPU không hiệu quả. Benchmark theo kernel và workload thật.

**Giả định mạng bandwidth cao là đủ.** Workload nhiều message nhỏ nhạy latency và collective synchronization. Đo cả latency, message rate và bandwidth.

**Tăng node nhưng giữ nguyên storage bottleneck.** Nhiều node cùng đọc/ghi có thể làm filesystem hoặc metadata server quá tải.

**Không kiểm tra NUMA và affinity.** Thread có thể truy cập remote memory hoặc tranh chấp core. Gắn thread/process theo topology.

**Checkpoint không nhất quán.** Restore một phần state của các node có thể tạo trạng thái không hợp lệ. Dùng checkpoint generation và manifest hoàn chỉnh.

**Tối ưu speedup mà quên cost-to-solution.** Cấu hình nhanh nhất chưa chắc kinh tế nhất. So sánh chi phí cho kết quả đạt yêu cầu.

## 17. Checklist thiết kế HPC scaling

### Workload và thuật toán

- [ ] Xác định mục tiêu strong scaling hay weak scaling.
- [ ] Phân tách phần tuần tự và phần song song.
- [ ] Xác định data, task hoặc pipeline parallelism.
- [ ] Lập đồ thị phụ thuộc và điểm đồng bộ.
- [ ] Kiểm tra tính đúng đắn khi chia partition.

### Scale-up

- [ ] Đo CPU, core, memory capacity và bandwidth.
- [ ] Kiểm tra NUMA, affinity và memory locality.
- [ ] Đánh giá GPU/accelerator và chi phí chuyển dữ liệu.
- [ ] Đo contention, lock và false sharing.
- [ ] Xác định giới hạn tối đa của một node.

### Scale-out

- [ ] Chọn cách phân vùng dữ liệu và cân bằng tải.
- [ ] Đo communication latency, bandwidth và message count.
- [ ] Kiểm tra network/interconnect và topology.
- [ ] Kiểm tra storage throughput và metadata workload.
- [ ] Có checkpoint, restart và xử lý node failure.
- [ ] Kiểm tra quota, placement và scheduler capacity.

### Benchmark và chi phí

- [ ] Lưu baseline và điều kiện benchmark.
- [ ] Đo speedup và parallel efficiency.
- [ ] Đo strong scaling và weak scaling nếu phù hợp.
- [ ] Theo dõi I/O, network, synchronization và straggler.
- [ ] So sánh cost-to-solution và thời gian hoàn thành.
- [ ] Chọn điểm dừng khi thêm tài nguyên không còn hiệu quả.

## 18. Ghi nhớ

- Scale-up tăng tài nguyên trong một node; scale-out tăng số node và phân phối công việc.
- Một workload HPC thường kết hợp thread/GPU trong node và message passing giữa các node.
- Phải phân tích phần tuần tự, phụ thuộc dữ liệu và chi phí giao tiếp trước khi mở rộng.
- Định luật Amdahl mô tả giới hạn speedup của bài toán cố định; Gustafson mô tả bài toán tăng kích thước theo tài nguyên.
- Strong scaling giữ nguyên kích thước bài toán; weak scaling tăng bài toán theo số worker.
- Communication, synchronization, load imbalance, memory và I/O có thể làm mất lợi ích của thêm node.
- Data parallelism, task parallelism và pipeline parallelism phù hợp với các cấu trúc workload khác nhau.
- Scale-out hiệu quả khi dữ liệu có thể partition và chi phí phối hợp được kiểm soát.
- HPC cần đo latency và bandwidth mạng, đồng thời xem xét topology và interconnect.
- Checkpoint phân tán phải đại diện cho trạng thái nhất quán của toàn job.
- Chọn cấu hình dựa trên speedup, efficiency, thời gian hoàn thành và cost-to-solution.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Scale-up | Tăng tài nguyên của một node hoặc chuyển sang node lớn hơn. |
| Scale-out | Tăng số node và phân phối workload qua nhiều node. |
| Parallelism | Khả năng thực hiện nhiều phần công việc đồng thời. |
| Serial fraction | Tỷ lệ công việc không thể chạy song song trong mô hình đang xét. |
| Amdahl's Law | Mô hình ước lượng giới hạn speedup của bài toán có kích thước cố định. |
| Gustafson's Law | Mô hình speedup khi kích thước bài toán tăng cùng số đơn vị xử lý. |
| Strong scaling | Tăng tài nguyên nhưng giữ nguyên kích thước bài toán. |
| Weak scaling | Tăng kích thước bài toán theo số đơn vị xử lý. |
| Speedup | Tỷ lệ thời gian baseline chia cho thời gian ở cấu hình mới. |
| Parallel efficiency | Speedup chia cho số đơn vị xử lý được dùng. |
| Data parallelism | Chia dữ liệu thành phần để xử lý cùng một phép tính song song. |
| Task parallelism | Chạy các tác vụ khác nhau đồng thời. |
| Pipeline parallelism | Chia quy trình thành stage xử lý các item khác nhau cùng lúc. |
| Embarrassingly parallel | Workload có các phần gần độc lập, cần ít giao tiếp. |
| Domain decomposition | Chia miền bài toán thành các subdomain phân phối cho worker/node. |
| Halo/ghost cells | Dữ liệu biên được trao đổi giữa các subdomain trong mô phỏng. |
| Communication overhead | Chi phí thời gian và tài nguyên để trao đổi dữ liệu giữa worker. |
| Synchronization | Phối hợp thời điểm hoặc trạng thái giữa các worker. |
| Load imbalance | Phân phối công việc không đều khiến một số worker phải chờ. |
| NUMA | Kiến trúc truy cập bộ nhớ có độ trễ/băng thông phụ thuộc vị trí node memory. |
| False sharing | Các thread cập nhật dữ liệu khác nhau nhưng cùng cache line gây cache coherence traffic. |
| MPI | Message Passing Interface, chuẩn giao tiếp message giữa process trong HPC. |
| OpenMP | API hỗ trợ parallelism trên shared-memory bằng directive và runtime. |
| RDMA | Remote Direct Memory Access, cơ chế truy cập bộ nhớ từ xa với overhead CPU thấp khi được hỗ trợ. |
| Collective operation | Thao tác giao tiếp tập thể như broadcast, reduce hoặc all-reduce. |
| Straggler | Worker hoặc partition chậm hơn phần còn lại và kéo dài thời gian hoàn thành. |
| Checkpoint | Trạng thái đã lưu để khôi phục hoặc tiếp tục một job. |
| Cost-to-solution | Tổng chi phí để hoàn thành một bài toán đạt yêu cầu. |
