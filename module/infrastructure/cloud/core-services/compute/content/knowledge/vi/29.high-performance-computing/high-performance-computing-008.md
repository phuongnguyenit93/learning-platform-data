# Đánh giá thời gian hoàn thành, hiệu suất song song và chi phí toàn cụm

Một cụm điện toán hiệu năng cao (HPC) có thể dùng hàng chục hoặc hàng nghìn CPU core, GPU, bộ nhớ dung lượng lớn và mạng tốc độ cao. Tuy nhiên, số node hoặc số core lớn không tự động tạo ra kết quả nhanh hơn hay rẻ hơn. Khi tăng quy mô cụm, thời gian trao đổi dữ liệu, đồng bộ, chờ scheduler, khởi tạo tài nguyên và phần công việc không thể song song có thể làm giảm lợi ích.

Đánh giá HPC cần trả lời ba câu hỏi cùng lúc: mất bao lâu để có kết quả hợp lệ, tài nguyên song song được sử dụng hiệu quả tới đâu và tổng chi phí của toàn bộ cụm là bao nhiêu. Một cấu hình tốt phải đáp ứng deadline và chất lượng kết quả với chi phí phù hợp, kể cả chi phí mạng, storage, phần mềm, thời gian chờ và tài nguyên nhàn rỗi.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, chương **Điện toán hiệu năng cao**. Nội dung trình bày cách đo time-to-solution, speedup, strong/weak scaling, parallel efficiency, profiling, benchmark công bằng và mô hình hóa chi phí toàn cụm để lựa chọn cấu hình CPU/GPU, số node, interconnect và thời gian chạy.

## 1. Đánh giá HPC ở cấp toàn cụm

Một benchmark đơn lẻ có thể cho biết kernel chạy nhanh đến đâu, nhưng chưa thể phản ánh trải nghiệm hoàn chỉnh của một workload HPC. Người dùng thường quan tâm từ lúc gửi job đến khi nhận được kết quả có thể sử dụng.

Các giai đoạn thường có:

1. Submit job và chờ scheduler cấp tài nguyên.
2. Provision hoặc khởi động node, container và runtime.
3. Stage input từ object/file storage tới node.
4. Nạp dữ liệu, khởi tạo MPI/GPU và phân phối tiến trình.
5. Thực hiện tính toán và trao đổi dữ liệu.
6. Checkpoint, ghi output và đồng bộ kết quả.
7. Post-processing, kiểm tra tính đúng đắn và công bố kết quả.

~~~mermaid
flowchart LR
    A["Submit job"] --> B["Queue / scheduling"]
    B --> C["Provision cluster"]
    C --> D["Stage input"]
    D --> E["Initialize runtime"]
    E --> F["Parallel compute"]
    F --> G["Checkpoint / output"]
    G --> H["Validate result"]
    H --> I["Result available"]
~~~

Nếu chỉ đo thời gian ở bước tính toán, nhóm có thể bỏ qua thời gian queue, provisioning, data staging và post-processing. Với job ngắn, các phần ngoài compute có thể chiếm tỷ trọng đáng kể.

### 1.1. Phạm vi đo phải khớp mục tiêu

| Mục tiêu | Phạm vi đo phù hợp |
|---|---|
| So sánh thuật toán | Thời gian thực thi phần tính toán với input và điều kiện giống nhau |
| So sánh số node | End-to-end runtime và compute time trên từng quy mô cụm |
| Đánh giá dịch vụ HPC | Submit-to-result, bao gồm queue, provisioning và data movement |
| Đánh giá chi phí | Thời gian tính phí của mọi tài nguyên và dịch vụ liên quan |
| Kiểm tra deadline | Thời gian hoàn thành kết quả hợp lệ trong điều kiện tải thực tế |
| Kiểm tra khả năng phục vụ | Throughput hoặc số job hoàn thành trong một khoảng thời gian |

Không trộn các phạm vi đo khác nhau trong cùng một bảng kết quả. Nếu báo cáo compute time, hãy ghi rõ thời gian queue và provisioning được loại trừ.

## 2. Time-to-solution và thời gian hoàn thành

Time-to-solution (TTS) là thời gian từ một mốc bắt đầu đã xác định đến khi có kết quả đúng và dùng được. Với góc nhìn người dùng, mốc bắt đầu thường là lúc submit job; mốc kết thúc là lúc kết quả đã được ghi bền vững và qua bước xác thực cần thiết.

~~~text
TTS =
  T_queue
  + T_provision
  + T_stage_in
  + T_initialize
  + T_compute
  + T_checkpoint_and_stage_out
  + T_validate
~~~

Tùy workload, một số giai đoạn có thể chồng lấp. Khi đó không nên cộng thời gian của các tác vụ song song một cách máy móc; cần đo elapsed wall-clock từ mốc đầu đến mốc cuối và dùng breakdown để giải thích.

### 2.1. Wall-clock time và CPU time

- **Wall-clock time:** thời gian thực tế trôi qua từ khi bắt đầu tới khi kết thúc.
- **CPU time:** tổng thời gian CPU thực sự chạy cho các process/thread.
- **GPU active time:** thời gian GPU thực hiện kernel hoặc hoạt động được công cụ đo ghi nhận.
- **Queue wait:** thời gian job chờ tài nguyên trước khi được chạy.
- **Elapsed job time:** khoảng thời gian job ở trạng thái running theo scheduler; có thể bao gồm init, I/O và cleanup.

Một job MPI chạy 64 rank trong 10 phút có thể tiêu thụ gần 640 rank-minute CPU nếu các rank hoạt động liên tục, nhưng wall-clock vẫn chỉ khoảng 10 phút. CPU time và wall-clock trả lời hai câu hỏi khác nhau.

### 2.2. Mốc bắt đầu và kết thúc

Để so sánh công bằng, định nghĩa trước:

- Start: submit timestamp, allocation start hoặc thời điểm tiến trình chính bắt đầu.
- End: computation finished, output committed hoặc result validated.
- Có tính thời gian tải image/container không?
- Có tính checkpoint và ghi output không?
- Có tính thời gian queue không?
- Có tính retry hoặc restart sau failure không?

Với bài toán khoa học, kết quả chỉ được xem là hoàn thành khi đáp ứng tiêu chí chính xác hoặc sai số đã đặt. Một lần chạy nhanh nhưng kết quả sai không phải một nghiệm hoàn thành.

### 2.3. Deadline và percentile

Không chỉ dùng thời gian trung bình. Với workload production, hãy theo dõi p50, p90, p95 và p99 của TTS. Nếu cần bảo đảm deadline, p95/p99 và tỷ lệ job vượt deadline thường hữu ích hơn một giá trị trung bình.

Đối với job batch, đo nhiều lần với các điều kiện tải khác nhau: cụm rảnh và cụm đang có tải, input nhỏ/trung bình/lớn, cache nóng và cache lạnh, job chạy một mình và chạy đồng thời, thời điểm scheduler có đủ hoặc thiếu node.

## 3. Throughput và thời gian hoàn thành không giống nhau

Latency/TTS mô tả thời gian hoàn thành một job. Throughput mô tả số job hoặc lượng công việc hoàn thành trong một đơn vị thời gian.

Ví dụ:

- Một job chạy trên 16 node hoàn thành trong 8 phút.
- Bốn job chạy đồng thời, mỗi job trên 4 node, có thể hoàn thành mỗi job trong 15 phút nhưng tạo nhiều kết quả hơn trong cùng một giờ.

Nếu mục tiêu là một mô phỏng lớn cần kết quả sớm, tối ưu latency có thể quan trọng hơn. Nếu mục tiêu là xử lý hàng nghìn mô phỏng độc lập, throughput toàn cụm và số nghiệm trên mỗi đô la có thể quan trọng hơn.

### 3.1. Throughput của cụm

~~~text
Throughput = Số job hoàn thành hợp lệ / Khoảng thời gian đo
~~~

Với job có kích thước khác nhau, số job/giờ có thể gây hiểu nhầm. Có thể dùng số timestep/giây, số cell/giây, số molecule-step/giây hoặc đơn vị công việc chuyên ngành.

### 3.2. Batch scheduling

Job độc lập có thể chạy dưới dạng job array hoặc batch. Khi đó, việc tăng số node cho từng job không phải lúc nào cũng tốt bằng việc chạy nhiều job nhỏ song song.

Hãy xác định mục tiêu tối ưu: một job lớn hoàn thành sớm nhất, tổng số job hoàn thành trong ngày, chi phí thấp nhất cho một nghiệm, tỷ lệ đáp ứng deadline cao nhất hoặc cân bằng giữa latency, throughput và chi phí.

## 4. Speedup và hiệu suất song song

Speedup đo mức nhanh hơn khi dùng nhiều tài nguyên song song so với baseline.

~~~text
S(p) = T(1) / T(p)
~~~

Trong đó T(1) là thời gian chạy baseline trên một đơn vị tài nguyên đã định nghĩa; T(p) là thời gian chạy cùng bài toán trên p đơn vị tài nguyên; p có thể là số core, rank, GPU hoặc node và phải ghi rõ đơn vị.

Nếu một bài toán mất 120 phút trên 1 node và 20 phút trên 6 node, speedup theo số node là 6 lần, với điều kiện mỗi node có cấu hình giống nhau và phạm vi đo nhất quán.

### 4.1. Parallel efficiency

~~~text
E(p) = S(p) / p
     = T(1) / (p * T(p))
~~~

Nếu p = 6 và speedup = 4.8 thì efficiency = 0.8, tương đương 80%. Điều đó có nghĩa mức tăng tốc đạt 80% so với speedup tuyến tính lý tưởng ở quy mô đang xét.

Efficiency không phải phần trăm CPU utilization. Một job có thể dùng CPU gần 100% trên mọi node nhưng efficiency thấp do baseline, communication hoặc thuật toán. Ngược lại, một workload có I/O hoặc synchronization có thể có CPU utilization thấp dù một phần công việc vẫn tiến triển đúng thiết kế.

### 4.2. Strong scaling

Strong scaling giữ nguyên kích thước bài toán và tăng số tài nguyên. Câu hỏi là: cùng một input, tăng node có rút ngắn thời gian giải được bao nhiêu?

| Số node | Thời gian chạy | Speedup | Efficiency |
|---:|---:|---:|---:|
| 1 | 120 phút | 1.00x | 100% |
| 2 | 66 phút | 1.82x | 91% |
| 4 | 38 phút | 3.16x | 79% |
| 8 | 25 phút | 4.80x | 60% |
| 16 | 20 phút | 6.00x | 38% |

Trong ví dụ, thêm node vẫn giảm thời gian, nhưng lợi ích biên giảm dần. Tăng từ 8 lên 16 node chỉ tiết kiệm 5 phút, trong khi số node tăng gấp đôi.

### 4.3. Weak scaling

Weak scaling tăng kích thước bài toán theo số tài nguyên để giữ lượng công việc trên mỗi tài nguyên gần như không đổi. Mục tiêu là xem cụm có thể mở rộng tổng khối lượng công việc mà thời gian chạy vẫn gần ổn định hay không.

| Số node | Tổng kích thước input | Input/node | Thời gian |
|---:|---:|---:|---:|
| 1 | 10 triệu cell | 10 triệu | 12 phút |
| 2 | 20 triệu cell | 10 triệu | 13 phút |
| 4 | 40 triệu cell | 10 triệu | 14 phút |
| 8 | 80 triệu cell | 10 triệu | 17 phút |

Thời gian tăng khi số node tăng có thể phản ánh chi phí giao tiếp, đồng bộ, I/O hoặc mất cân bằng tải. Weak scaling tốt không có nghĩa một input cố định sẽ chạy nhanh hơn khi thêm node.

### 4.4. Baseline phải được định nghĩa

Nếu không thể chạy bài toán lớn trên một node, baseline có thể là cấu hình nhỏ nhất có ý nghĩa, chẳng hạn 2 node. Khi đó cần ghi rõ speedup được tính so với 2 node, không gọi đó là speedup tuyệt đối từ một node.

Không so sánh speedup giữa các máy khác CPU, memory, GPU hoặc compiler mà không chuẩn hóa baseline và giải thích khác biệt.

## 5. Giới hạn song song: Amdahl và Gustafson

Không phải mọi phần của chương trình đều có thể chia cho nhiều core. Phần tuần tự, giao tiếp và đồng bộ giới hạn speedup.

### 5.1. Định luật Amdahl

Nếu tỷ lệ f của công việc có thể song song và phần còn lại 1-f là tuần tự, speedup lý tưởng với p worker là:

~~~text
S(p) = 1 / ((1 - f) + f/p)
~~~

Ví dụ, nếu 90% công việc có thể song song và 10% là tuần tự, khi p tiến tới rất lớn, speedup tối đa tiến tới 10 lần. Thêm node vượt ngưỡng đó không thể cải thiện phần tuần tự.

Mô hình này giả định phần tuần tự cố định và không mô tả đầy đủ communication, contention hoặc thay đổi kích thước dữ liệu. Nó giúp nhận ra giới hạn cơ bản, không thay thế benchmark.

### 5.2. Định luật Gustafson

Trong nhiều workload HPC, khi có thêm tài nguyên, nhóm có thể giải bài toán lớn hơn trong thời gian tương tự. Gustafson xem xét scaled workload thay vì giữ input cố định.

~~~text
S_G(p) = p - alpha * (p - 1)
~~~

Trong đó alpha là tỷ lệ thời gian tuần tự trong lần chạy song song theo mô hình. Công thức mô tả tiềm năng tăng quy mô bài toán khi số worker tăng, với giả định phù hợp về phần tuần tự.

### 5.3. Ý nghĩa khi chọn cụm

- Dùng strong scaling khi cần rút ngắn thời gian một bài toán cố định.
- Dùng weak scaling khi cần xử lý bài toán lớn hơn theo năng lực cụm.
- Nếu phần tuần tự chiếm tỷ trọng cao, tối ưu thuật toán hoặc pipeline trước khi mua thêm node.
- Nếu communication chiếm nhiều thời gian, xem lại partition, topology và interconnect.
- Nếu I/O chiếm nhiều thời gian, tối ưu data layout và storage path.

## 6. Overhead khi chạy song song

Thời gian song song thực tế có thể được mô hình hóa đơn giản:

~~~text
T(p) = T_parallel_work(p)
     + T_serial
     + T_communication
     + T_synchronization
     + T_imbalance
     + T_runtime_overhead
~~~

Các thành phần này có thể chồng lấp; biểu thức nhằm phân loại nguyên nhân. Tăng p làm giảm phần parallel work nhưng có thể tăng communication, synchronization và runtime overhead.

### 6.1. Communication

Trong MPI, các rank trao đổi dữ liệu bằng point-to-point hoặc collective operations như broadcast, reduce, all-reduce và all-to-all. Khi số rank tăng, số peer hoặc lượng dữ liệu trao đổi có thể tăng nhanh.

Communication bị ảnh hưởng bởi latency và bandwidth của interconnect, số rank và pattern giao tiếp, kích thước message, topology và placement của node, congestion trên network, NUMA và đường đi từ CPU tới NIC/GPU.

### 6.2. Synchronization

Barrier, lock, collective operation và dependency giữa các bước khiến worker phải chờ nhau. Nếu một rank chậm hơn, các rank khác có thể đứng đợi tại điểm đồng bộ.

Hãy dùng profiler hoặc MPI tracing để xác định thời gian chờ collective, lock contention và imbalance thay vì chỉ nhìn CPU utilization trung bình.

### 6.3. Load imbalance

Nếu một node nhận nhiều dữ liệu hoặc tác vụ khó hơn, nó có thể trở thành straggler. Các node còn lại kết thúc sớm nhưng vẫn phải chờ node chậm nhất trước khi qua bước tiếp theo.

Biện pháp:

- Chia dữ liệu cân bằng hơn.
- Dùng dynamic scheduling cho workload có thời gian xử lý biến động.
- Tránh partition quá nhỏ gây overhead scheduler.
- Theo dõi thời gian xử lý từng rank/task.
- Đặt dữ liệu gần tài nguyên đang xử lý.

## 7. Đánh giá CPU, GPU và interconnect

HPC thường kết hợp CPU, GPU và mạng tốc độ cao. Số lượng core hoặc GPU chỉ là thông số đầu vào; cần đo xem workload có tận dụng được các tài nguyên đó không.

### 7.1. CPU

Theo dõi:

- Core/thread thực sự được cấp và sử dụng.
- CPU utilization theo từng node và từng rank.
- IPC, cache miss và memory bandwidth khi công cụ hỗ trợ.
- NUMA locality và remote memory access.
- CPU throttling hoặc oversubscription.

Một node nhiều core nhưng memory bandwidth thấp có thể không nhanh hơn node ít core hơn cho workload memory-bound.

### 7.2. GPU

Theo dõi:

- GPU utilization và thời gian kernel.
- Memory utilization và memory bandwidth.
- Host-to-device/device-to-host transfer.
- Kernel launch overhead.
- GPU occupancy và mức sử dụng multiprocessor.
- Thời gian chờ CPU hoặc communication.

GPU utilization thấp có thể do batch nhỏ, kernel ngắn, data transfer hoặc CPU không cung cấp dữ liệu đủ nhanh. Tăng số GPU mà không tăng khả năng cấp dữ liệu có thể làm chi phí tăng mà TTS ít thay đổi.

### 7.3. Interconnect

Đo bandwidth và latency bằng benchmark phù hợp với network fabric thực tế. Với MPI, cần test cả point-to-point và collective operations, trên cùng node và giữa node.

Không dùng kết quả network benchmark lý thuyết thay cho ứng dụng thực. Pattern giao tiếp của ứng dụng, message size và topology có thể tạo hiệu năng khác xa bài test tổng hợp.

## 8. Profiling và phân tích bottleneck

Benchmark cho biết cấu hình nào nhanh hơn; profiling giúp giải thích vì sao.

Các nhóm công cụ có thể dùng:

- CPU profiler và hardware performance counter.
- GPU profiler và tracing.
- MPI profiler/tracer.
- System monitoring theo node.
- Storage latency/throughput metrics.
- Scheduler accounting và job state history.
- Application-level timers cho từng phase.

### 8.1. Phân rã thời gian ứng dụng

Thêm timestamp hoặc timer quanh các phase quan trọng:

~~~python
from time import perf_counter

start = perf_counter()
load_input()
t_input = perf_counter()

initialize_solver()
t_init = perf_counter()

solve()
t_solve = perf_counter()

write_output()
t_output = perf_counter()

print({
    "input_seconds": t_input - start,
    "initialize_seconds": t_init - t_input,
    "solve_seconds": t_solve - t_init,
    "output_seconds": t_output - t_solve,
    "total_seconds": t_output - start,
})
~~~

Trong chương trình MPI, timestamp từ các node có thể lệch nhau. Để đo elapsed time của phase song song, dùng clock monotonic trên từng process và thu thập max/critical-path duration; không trừ trực tiếp timestamp wall-clock giữa host nếu chưa đồng bộ clock.

### 8.2. Thời gian quan trọng là critical path

Một phase song song có thể gồm nhiều task. Thời gian kết thúc phase thường do task chậm nhất quyết định, không phải tổng hay trung bình thời gian của mọi task.

Hãy ghi minimum, median, maximum duration theo rank; thời gian chờ barrier/collective; thời gian communication; số byte gửi/nhận; thời gian I/O; và mức phân bố công việc giữa node.

Average có thể che giấu một rank bị chậm đáng kể; maximum và percentile giúp nhận ra straggler.

## 9. Benchmark công bằng và có thể tái lập

Một kết quả benchmark chỉ có ý nghĩa khi input, phần mềm, cấu hình và điều kiện chạy được ghi nhận.

### 9.1. Cố định workload

Ghi lại:

- Input dataset, kích thước và checksum.
- Phiên bản ứng dụng và commit.
- Compiler, flags và thư viện toán học.
- MPI implementation và version.
- Container image digest hoặc package checksum.
- CPU/GPU model, memory và interconnect.
- Số node, core/rank/thread/GPU.
- Scheduler partition, placement và binding.
- Precision, tolerance và tiêu chí đúng.

### 9.2. Warm-up và số lần chạy

Một số ứng dụng cần warm-up để compile JIT, nạp cache, khởi tạo GPU context hoặc tạo connection. Tách warm-up khỏi các lần đo chính nếu mục tiêu là steady-state runtime; nếu mục tiêu là cold-start/TTS thì phải giữ phần khởi tạo trong phạm vi đo.

Chạy lặp lại nhiều lần và báo median cùng độ phân tán. Với môi trường nhiều nhiễu, có thể báo p95 hoặc confidence interval. Không loại bỏ lần chạy chậm nếu không có lý do xác định và ghi lại.

### 9.3. Không thay đổi nhiều biến cùng lúc

Khi thử nghiệm, thay một nhóm yếu tố có chủ đích:

- Số node.
- Số rank mỗi node.
- Threads mỗi rank.
- Số GPU mỗi node.
- CPU/GPU type.
- Network topology.
- Storage tier.
- Compiler/MPI tuning.

Nếu thay cùng lúc số node, compiler, input và storage, sẽ khó xác định nguyên nhân cải thiện.

### 9.4. Kiểm tra tính đúng đắn

Mỗi cấu hình phải tạo kết quả đáp ứng tiêu chí chất lượng. Với mô phỏng số, kết quả song song có thể khác thứ tự phép cộng do floating-point reduction; hãy dùng tolerance khoa học được xác định trước thay vì đòi bitwise identical khi thuật toán không bảo đảm điều đó.

Không chấp nhận cấu hình nhanh hơn nếu kết quả sai, thiếu dữ liệu hoặc không thể tái lập theo yêu cầu.

## 10. Mô hình chi phí toàn cụm

Chi phí HPC không chỉ là giá CPU/GPU. Một job có thể sử dụng node compute, interconnect, storage, snapshot, data transfer, license phần mềm, scheduler, monitoring và thời gian vận hành.

Mô hình tổng quát:

~~~text
C_cluster =
    C_compute
  + C_accelerator
  + C_network
  + C_storage
  + C_data_transfer
  + C_software_license
  + C_scheduler_and_services
  + C_support_and_operations
  + C_idle_capacity
~~~

Với cloud, một số khoản được tính trực tiếp theo usage; khoản khác nằm trong dịch vụ managed hoặc license. Với cụm on-premises, cần phân bổ chi phí mua máy, mạng, storage, điện, làm mát, bảo trì và nhân sự theo thời gian sử dụng.

### 10.1. Compute node-hours

Nếu một loại node có giá r_i trên mỗi node-hour, số node là n_i và thời gian tính phí là h_i:

~~~text
C_compute = sum(n_i * r_i * h_i)
~~~

Phải dùng billable time thực tế của nhà cung cấp. Một số dịch vụ tính phí từ lúc provision, theo giây/phút, theo giờ hoặc có thời gian tối thiểu; thời gian queue trước khi cấp node có thể không tính compute nhưng vẫn ảnh hưởng TTS. Node được cấp nhưng job đang chờ I/O hoặc idle vẫn có thể bị tính phí.

### 10.2. GPU và accelerator

GPU thường có giá theo node hoặc accelerator-hour. Cần phân biệt giá node GPU với giá GPU riêng, tránh cộng hai lần nếu giá node đã bao gồm accelerator.

Một node GPU có thể đắt hơn nhiều node CPU. Chỉ so sánh chi phí khi cùng tạo ra kết quả hợp lệ với chất lượng tương đương. Nếu GPU utilization thấp hoặc dữ liệu transfer chiếm phần lớn thời gian, chi phí accelerator có thể không tạo giá trị tương xứng.

### 10.3. Network

Chi phí network có thể bao gồm:

- Interconnect hoặc network tier cao cấp.
- Data transfer giữa zone/region.
- Egress tới Internet hoặc hệ thống bên ngoài.
- Network appliance hoặc private connectivity.
- Lưu lượng giữa compute và storage nếu dịch vụ tính phí riêng.

Không phải mọi cloud đều tính phí mọi loại traffic. Cần phân biệt traffic nội bộ miễn phí, traffic giữa AZ, traffic giữa region và egress theo bảng giá của dịch vụ cụ thể.

### 10.4. Storage và I/O

Storage cost có thể gồm dung lượng provisioned, dung lượng thực dùng, IOPS provisioned, throughput, request count, snapshot, backup và data retrieval.

Workload HPC thường tạo file checkpoint hoặc intermediate data lớn. Nếu checkpoint quá thường xuyên hoặc giữ nhiều phiên bản, chi phí storage và request có thể đáng kể. Hãy tính cả chi phí stage-in/stage-out và thời gian compute chờ storage.

### 10.5. License và phần mềm

Phần mềm thương mại có thể tính license theo core, socket, node, GPU hoặc thời gian chạy. Một cấu hình nhiều core có thể làm tăng license cost ngay cả khi compute price không đổi.

Đưa compiler, solver, MPI distribution, visualization, scheduler plugin và commercial library vào inventory chi phí. Kiểm tra điều khoản license khi chạy trên cloud, đặc biệt với autoscaling và node tạm thời.

## 11. Chi phí nhàn rỗi và utilization

Tài nguyên được provision nhưng không làm công việc hữu ích vẫn có thể phát sinh chi phí. Các nguồn idle thường gặp:

- Node đã được cấp nhưng job chưa bắt đầu.
- Job giữ allocation trong khi chờ một rank hoặc dependency.
- Node quá lớn so với mức song song của ứng dụng.
- GPU không có đủ batch để giữ hoạt động.
- Cluster giữ capacity dự phòng trong thời gian ít workload.
- Job kết thúc nhưng node chưa được scale-in hoặc release.

### 11.1. Utilization

Có thể theo dõi utilization ở nhiều tầng:

- **Allocated utilization:** tỷ lệ thời gian tài nguyên được scheduler cấp cho job.
- **CPU utilization:** tỷ lệ thời gian CPU thực hiện work so với khả năng CPU.
- **GPU utilization:** tỷ lệ hoạt động GPU theo metric của thiết bị.
- **Memory utilization:** mức sử dụng bộ nhớ so với capacity.
- **Network utilization:** mức dùng bandwidth so với khả năng liên kết.
- **Storage utilization:** IOPS/throughput thực tế so với mức có thể cấp.

Các chỉ số này không thay thế nhau. Một node có allocated utilization 100% có thể vẫn có CPU utilization thấp do job đang chờ network hoặc storage.

### 11.2. Phân bổ chi phí cụm dùng chung

Với cluster nhiều nhóm dùng chung, cần có quy tắc chargeback hoặc showback. Có thể phân bổ theo node-hours, GPU-hours, core-hours, memory-hours, storage consumption, network usage hoặc tỷ trọng reservation.

Nếu chỉ chia chi phí theo số job, nhóm chạy một mô phỏng nhỏ và nhóm chạy một job GPU lớn có thể bị tính như nhau, dẫn tới quyết định không công bằng.

### 11.3. Tài nguyên dự phòng

Capacity dự phòng giúp giảm queue wait và đáp ứng deadline, nhưng làm tăng chi phí nhàn rỗi. Cần cân bằng:

- Mức SLA/deadline cần đáp ứng.
- Mức biến động workload.
- Thời gian khởi động hoặc provision node.
- Chi phí giữ capacity.
- Khả năng dùng chung node giữa nhiều job.
- Khả năng dùng instance có thể bị thu hồi cho job chịu được interruption.

## 12. Cost per solution và hiệu quả kinh tế

Một chỉ số hữu ích là chi phí trên mỗi kết quả hợp lệ:

~~~text
Cost per solution =
  Total cost attributable to workload
  / Number of validated solutions
~~~

Với một job tạo một kết quả, cost per solution gần bằng tổng chi phí phân bổ cho job. Với batch gồm nhiều job, cần chia theo số nghiệm hợp lệ; không tính job thất bại hoặc output không đạt tiêu chí như nghiệm thành công.

Một số chỉ số bổ sung:

~~~text
Throughput per dollar = Valid work units completed / Total cost

Cost per node-hour = Total cluster cost / Allocated node-hours

Cost efficiency = Useful work / Total resource cost
~~~

Định nghĩa useful work phải cụ thể theo ứng dụng: timestep, cell update, simulation, training step hoặc nghiệm đã xác thực. Không dùng một đơn vị chung chung để so sánh workload khác bản chất.

### 12.1. Deadline-aware cost

Nếu một cấu hình nhanh hơn nhưng đắt hơn, quyết định phụ thuộc giá trị của thời gian:

- Nếu phải hoàn thành trước deadline cứng, cấu hình nhanh có thể là lựa chọn duy nhất.
- Nếu có thể chạy qua đêm, cấu hình rẻ hơn có thể tốt hơn.
- Nếu có nhiều job độc lập, tối ưu throughput/$ có thể phù hợp hơn tối ưu TTS cho một job.
- Nếu queue wait lớn hơn compute time, tăng node trong job không giải quyết được bottleneck chính.

Hãy đánh giá các cấu hình nằm trên Pareto frontier: không có cấu hình nào vừa nhanh hơn vừa rẻ hơn cấu hình đó. Sau đó chọn điểm phù hợp deadline, ngân sách và chất lượng.

### 12.2. Ví dụ tính cost per solution

Giả sử giá một node CPU là 3 đơn vị tiền/node-hour. Một job tạo một nghiệm hợp lệ và cần 30 phút allocation trên 8 node. Chi phí phụ trợ phân bổ gồm storage 1,2; network 0,8; license 2,0 và scheduler/service 0,5.

~~~text
Compute cost = 8 * 3 * 0.5 = 12.0
Other cost   = 1.2 + 0.8 + 2.0 + 0.5 = 4.5
Total cost   = 12.0 + 4.5 = 16.5
Cost/solution = 16.5 / 1 = 16.5
~~~

Một cấu hình 16 node hoàn thành trong 25 phút:

~~~text
Compute cost = 16 * 3 * (25/60) = 20.0
Other cost   = 1.2 + 1.0 + 2.0 + 0.5 = 4.7
Total cost   = 20.0 + 4.7 = 24.7
Cost/solution = 24.7 / 1 = 24.7
~~~

Cấu hình 16 node nhanh hơn 5 phút nhưng chi phí trên nghiệm tăng từ 16,5 lên 24,7 đơn vị. Nếu deadline yêu cầu dưới 25 phút, cấu hình 16 node có thể cần thiết; nếu deadline là 40 phút, cấu hình 8 node kinh tế hơn. Các số liệu là giả định minh họa, chưa bao gồm queue wait nếu thời gian đó không bị tính phí.

## 13. So sánh cấu hình trên Pareto frontier

Một cấu hình HPC có ít nhất hai mục tiêu thường xung đột: giảm TTS và giảm chi phí. Có thể biểu diễn mỗi cấu hình bằng cặp:

~~~text
Configuration = (TTS, Cost per solution)
~~~

Cấu hình A chi phối cấu hình B nếu A không chậm hơn và không đắt hơn B, đồng thời tốt hơn ít nhất một tiêu chí. Các cấu hình không bị cấu hình khác chi phối tạo thành Pareto frontier.

Ví dụ:

| Cấu hình | TTS | Cost/solution | Nhận xét |
|---|---:|---:|---|
| 4 node CPU | 50 phút | 10 | Rẻ nhất nhưng chậm |
| 8 node CPU | 30 phút | 16 | Cân bằng |
| 16 node CPU | 25 phút | 25 | Nhanh hơn nhưng chi phí cao |
| 4 node GPU | 18 phút | 21 | Nhanh và rẻ hơn 16 node CPU trong ví dụ |
| 8 node GPU | 15 phút | 34 | Nhanh nhất nhưng đắt |

Các số liệu chỉ minh họa cách đọc bảng. Nếu cấu hình 4 node GPU nhanh hơn và rẻ hơn cấu hình 16 node CPU, cấu hình 16 node CPU bị chi phối trong workload này. Kết luận có thể thay đổi với input khác hoặc tiêu chí chất lượng khác.

### 13.1. Thêm ràng buộc trước khi chọn

Pareto frontier chưa đủ để ra quyết định. Cần thêm:

- Deadline tối đa.
- Ngân sách tối đa.
- Precision hoặc chất lượng kết quả.
- Memory capacity và memory bandwidth.
- Giới hạn số GPU hoặc license.
- Khả năng cấp node đúng thời điểm.
- Yêu cầu về vùng dữ liệu và bảo mật.

Loại bỏ cấu hình không đáp ứng ràng buộc trước, sau đó chọn trong tập cấu hình còn lại.

## 14. Tối ưu chi phí mà vẫn giữ hiệu năng

Tối ưu chi phí hiệu quả bắt đầu từ bottleneck. Giảm giá node nhưng tăng runtime gấp đôi có thể làm tổng chi phí tăng. Ngược lại, một node đắt hơn có thể hoàn thành sớm và giảm billable node-hours.

### 14.1. Chọn đúng kích thước node

- Memory-bound workload cần đủ RAM và memory bandwidth.
- Compute-bound workload cần CPU/GPU throughput.
- Communication-bound workload cần interconnect và topology tốt.
- I/O-bound workload cần storage throughput/IOPS phù hợp.
- Workload ít song song có thể hiệu quả hơn trên ít node mạnh.

Không chọn node chỉ theo vCPU count. Kiểm tra generation CPU, core frequency, NUMA, RAM bandwidth, GPU memory và network fabric.

### 14.2. Tối ưu số rank và thread

MPI rank và thread count ảnh hưởng communication, memory footprint và CPU binding. Một số workload tốt với một rank mỗi core; workload khác dùng một rank mỗi NUMA domain và nhiều thread.

Thử nghiệm các tổ hợp có kiểm soát:

- Một rank mỗi node với nhiều thread.
- Nhiều rank mỗi node với ít thread.
- Một rank mỗi GPU hoặc theo cách mapping phù hợp ứng dụng.
- CPU binding và NUMA placement.

Tránh oversubscription khi tổng thread vượt số core được cấp mà ứng dụng không được thiết kế cho điều đó. Kiểm tra affinity để process không di chuyển tùy tiện giữa NUMA node.

### 14.3. Giảm data movement

- Đặt input gần cluster hoặc stage vào local scratch trước khi chạy.
- Dùng data format thuận lợi cho truy cập song song.
- Giảm số lần đọc/ghi file nhỏ.
- Gộp I/O thành block lớn khi phù hợp.
- Overlap communication và computation nếu thuật toán cho phép.
- Chỉ ghi checkpoint theo RPO và mức rủi ro phù hợp.

Giảm thời gian I/O có thể rút ngắn TTS và giảm node-hours bị tính phí.

### 14.4. Rightsizing và autoscaling

Scheduler và autoscaler có thể cấp số node phù hợp theo workload. Cần cân bằng thời gian scale-up với thời gian job và chi phí giữ capacity.

Với job MPI tightly coupled, không thể tùy ý scale node giữa một phase tính toán nếu ứng dụng không hỗ trợ dynamic process management. Có thể scale giữa các job, giữa các stage hoặc giữa các batch.

### 14.5. Reserved, on-demand và interruptible capacity

| Loại capacity | Lợi ích | Rủi ro/chi phí cần xét |
|---|---|---|
| On-demand | Có thể cấp theo nhu cầu, không cần cam kết dài hạn | Đơn giá thường cao hơn mức cam kết |
| Reserved/committed | Giảm đơn giá khi mức dùng ổn định | Trả tiền cho cam kết và nguy cơ capacity không dùng hết |
| Spot/preemptible | Giá thấp hơn khi có capacity dư | Có thể bị thu hồi; cần checkpoint/retry và capacity dự phòng |

Workload HPC có checkpoint và job độc lập thường phù hợp hơn với interruptible capacity. Job MPI tightly coupled hoặc chạy dài không thể checkpoint có thể bị ảnh hưởng lớn khi một node mất, vì vậy cần tính cả xác suất interruption và chi phí chạy lại.

## 15. Checkpoint, failure và chi phí chạy lại

Checkpoint tạo điểm phục hồi cho job dài. Nó làm tăng I/O và có thể tạm dừng tính toán, nhưng giảm lượng công việc phải chạy lại khi node hoặc job lỗi.

Chi phí kỳ vọng cần xét:

~~~text
Expected total cost =
  Normal execution cost
  + Checkpoint cost
  + Expected restart cost
  + Recovery and data transfer cost
~~~

Nếu checkpoint quá thường xuyên, overhead ghi dữ liệu làm giảm hiệu suất. Nếu checkpoint quá thưa, failure có thể làm mất nhiều tiến độ.

### 15.1. Đo checkpoint overhead

Theo dõi:

- Thời gian tạo checkpoint.
- Kích thước checkpoint.
- Storage throughput và latency.
- Thời gian resume.
- Số lần checkpoint bị lỗi.
- Lượng compute time mất do restart.

Checkpoint cần được lưu ở storage còn tồn tại sau khi node bị mất. Local scratch có thể dùng làm vùng staging nhưng không nên là bản duy nhất.

### 15.2. Tính chi phí retry

Khi job thất bại, chi phí đã tiêu thụ trước failure vẫn là chi phí thực. Tổng cost không chỉ là lần chạy thành công cuối cùng. Ghi lại attempt count, thời gian compute đã tiêu tốn, checkpoint được khôi phục và phần output bị loại bỏ.

Đối với job array, có thể retry từng task lỗi thay vì chạy lại cả batch nếu các task độc lập và kết quả được lưu theo key riêng.

## 16. Chi phí cụm on-premises và cloud

Chi phí on-premises thường gồm đầu tư ban đầu và chi phí vận hành định kỳ. Chi phí cloud chủ yếu theo usage, reservation/commitment và các dịch vụ liên quan. Hai mô hình cần được so sánh trên cùng thời gian sử dụng và cùng mức dịch vụ.

### 16.1. Total cost of ownership on-premises

Các thành phần:

- Máy chủ CPU/GPU, memory và accelerator.
- Switch, NIC, cable và fabric interconnect.
- Storage, controller và backup.
- Rack, điện, UPS và làm mát.
- License, support và bảo trì.
- Nhân sự vận hành, thay thế linh kiện và nâng cấp.
- Chi phí cơ hội khi capacity không được sử dụng.

Phân bổ capital expenditure theo thời gian khấu hao và utilization thực tế. Nếu cụm chỉ được dùng 20% thời gian, chi phí trên mỗi giờ compute hữu ích có thể cao dù phần cứng đã mua xong.

### 16.2. Cloud HPC

Các thành phần:

- Compute node và GPU-hour.
- High-performance network hoặc placement group nếu có tính phí.
- Persistent disk, parallel file system, object storage và snapshot.
- Data transfer giữa region/AZ hoặc egress.
- License phần mềm và managed scheduler.
- Image registry, logging, monitoring và support.
- Reservation/commitment không được sử dụng hết.

Cloud có thể giảm nhu cầu đầu tư trước và giúp mở rộng theo đợt, nhưng chi phí data staging, storage và idle provisioned capacity có thể làm hóa đơn cao hơn dự tính.

### 16.3. So sánh theo utilization

Để so sánh, tính:

~~~text
Effective cost per useful node-hour =
  Total ownership or cloud cost
  / Useful node-hours delivered
~~~

Useful node-hours cần phản ánh thời gian tài nguyên thực sự tạo công việc hữu ích, theo định nghĩa thống nhất. Với on-premises, phân bổ chi phí khấu hao, điện và vận hành theo utilization; với cloud, cộng billable time và các dịch vụ phát sinh.

## 17. Dashboard và chỉ số vận hành

Dashboard HPC nên kết nối ba lớp: tiến độ job, hiệu suất tài nguyên và chi phí.

| Nhóm | Chỉ số |
|---|---|
| Time-to-solution | Submit-to-result, queue wait, provisioning, stage-in/out, compute, validation |
| Parallel performance | Speedup, efficiency, strong/weak scaling, rank imbalance |
| CPU | Utilization, throttling, IPC, memory bandwidth, NUMA locality |
| GPU | Utilization, memory, kernel time, transfer time |
| Network | Bandwidth, latency, retransmission, collective time |
| Storage | IOPS, throughput, latency, capacity, checkpoint duration |
| Scheduler | Allocated node-hours, pending jobs, idle allocation, job failure |
| Cost | Compute cost, GPU cost, storage, network, license, cost/solution |
| Quality | Valid result rate, precision/tolerance, retry count |

### 17.1. Gắn nhãn chi phí với workload

Mỗi job nên có metadata như project, team, owner, experiment ID, application version và cost center. Nhờ vậy, có thể tổng hợp chi phí theo nhóm và truy nguyên job tạo ra chi phí bất thường.

Nếu dùng cluster chung, thống nhất cách phân bổ chi phí scheduler, capacity dự phòng, network và storage. Công bố rõ phần nào là chi phí trực tiếp và phần nào là chi phí phân bổ.

### 17.2. Cảnh báo

Thiết lập cảnh báo khi:

- Job vượt deadline hoặc TTS tăng đột biến.
- Parallel efficiency giảm khi số node tăng.
- Một rank/node trở thành straggler.
- GPU utilization thấp kéo dài.
- Network hoặc storage latency tăng.
- Allocated node-hours vượt ngân sách.
- Cost per solution tăng so với baseline.
- Retry hoặc checkpoint failure tăng.

## 18. Quy trình đánh giá và chọn cấu hình

Một quy trình thực tế có thể triển khai theo các bước:

1. **Xác định mục tiêu:** deadline, throughput, chất lượng và ngân sách.
2. **Chọn workload đại diện:** input có kích thước và pattern giống production.
3. **Định nghĩa baseline:** một node hoặc cấu hình nhỏ nhất có ý nghĩa.
4. **Lập ma trận thử nghiệm:** số node, rank/thread, CPU/GPU, network và storage.
5. **Chạy benchmark lặp lại:** tách warm-up khỏi steady-state khi cần.
6. **Kiểm tra kết quả:** xác nhận precision, tolerance và completeness.
7. **Tính speedup/efficiency:** so với baseline cùng phạm vi đo.
8. **Profiling:** xác định serial work, communication, imbalance và I/O.
9. **Tính cost toàn cụm:** bao gồm compute, network, storage, license và idle capacity.
10. **Lập Pareto frontier:** loại cấu hình vừa chậm hơn vừa đắt hơn.
11. **Chọn cấu hình:** đáp ứng deadline và ngân sách với biên dự phòng.
12. **Theo dõi production:** so sánh số liệu thực với benchmark và cập nhật khi workload thay đổi.

## 19. Ví dụ thực tế: chọn cấu hình cho mô phỏng CFD

Một nhóm kỹ thuật chạy mô phỏng động lực học chất lưu (CFD) trên cụm cloud. Mỗi lần chạy dùng cùng mesh và tiêu chí hội tụ. Kết quả chỉ hợp lệ khi solver đạt residual tolerance và file kết quả được ghi hoàn chỉnh.

Nhóm thử nghiệm strong scaling với một input cố định:

| Cấu hình | Compute time | TTS | Speedup theo compute time |
|---|---:|---:|---:|
| 1 node CPU | 120 phút | 132 phút | 1.00x |
| 2 node CPU | 66 phút | 78 phút | 1.82x |
| 4 node CPU | 38 phút | 50 phút | 3.16x |
| 8 node CPU | 25 phút | 37 phút | 4.80x |
| 16 node CPU | 20 phút | 32 phút | 6.00x |

TTS bao gồm 12 phút queue/provision/stage/validation theo giả định của ví dụ. Nếu những phần này thay đổi theo cấu hình hoặc tải cụm, cần đo riêng cho từng lần chạy thay vì cộng một hằng số.

Trong phép tính chi phí bên dưới, giả định 5 phút trong 12 phút ngoài compute là thời gian provision được tính phí node; 7 phút còn lại là queue, stage và validation không bị tính compute node-hour. Storage, network và license đã được phản ánh riêng trong chi phí phụ trợ.

### 19.1. Đọc hiệu suất song song

Với baseline một node:

- 4 node đạt speedup khoảng 3,16x và efficiency khoảng 79%.
- 8 node đạt speedup 4,8x và efficiency 60%.
- 16 node đạt speedup 6x và efficiency 37,5%.

Hiệu suất giảm khi số node tăng. Nhóm profiling thấy communication và barrier wait tăng ở 16 node; điều đó gợi ý cần xem lại domain decomposition và collective operations trước khi cấp thêm node.

### 19.2. So sánh chi phí

Giả sử đơn giá node là 3 đơn vị tiền/node-hour và chi phí phụ trợ được phân bổ theo ví dụ:

| Cấu hình | Compute cost | Chi phí phụ trợ | Tổng cost/solution |
|---|---:|---:|---:|
| 8 node, 30 phút billable | 12,0 | 4,5 | 16,5 |
| 16 node, 25 phút billable | 20,0 | 4,7 | 24,7 |

16 node rút ngắn compute time nhưng làm chi phí mỗi nghiệm tăng đáng kể. Nếu deadline cho phép 40 phút, 8 node là lựa chọn tiết kiệm hơn. Nếu deadline dưới 25 phút, nhóm phải cân nhắc 16 node hoặc tối ưu thuật toán/communication để đạt deadline với chi phí thấp hơn.

### 19.3. Quyết định sau benchmark

Nhóm chọn 8 node làm cấu hình mặc định cho các lần chạy không gấp. Với experiment có deadline cứng, dùng 16 node theo policy riêng. Trước khi mở rộng tiếp, nhóm thử tối ưu partition, giảm synchronization và cải thiện I/O; mọi thay đổi đều được benchmark lại với cùng input và tiêu chí hội tụ.

Ví dụ trên dùng số liệu giả định nhằm minh họa cách ra quyết định. Trong thực tế cần dùng billable time, queue time và giá dịch vụ thực tế của region/contract.

## 20. Ma trận lựa chọn theo loại workload

| Đặc điểm workload | Ưu tiên đo | Hướng cấu hình cần thử |
|---|---|---|
| Compute-bound | FLOP/s, speedup, CPU/GPU utilization | Core/GPU throughput, vectorization, rank/thread mapping |
| Memory-bound | Memory bandwidth, cache miss, NUMA | RAM bandwidth, memory capacity, NUMA placement |
| Communication-bound | MPI time, latency, collective duration | Interconnect, topology, rank placement, message aggregation |
| I/O-bound | Storage latency, throughput, IOPS | Parallel filesystem, local scratch, data layout |
| Embarrassingly parallel | Throughput, cost per job | Job array, nhiều job độc lập, node nhỏ |
| Tightly coupled MPI | TTS, parallel efficiency, tail rank time | Node đồng nhất, interconnect nhanh, placement ổn định |
| GPU-heavy | GPU kernel time, utilization, transfer | GPU memory, accelerator count, CPU feed rate |
| Long-running/checkpointed | TTS có retry, checkpoint overhead, expected cost | Durable checkpoint storage, interruptible capacity khi phù hợp |

Ma trận chỉ là điểm bắt đầu. Benchmark với input đại diện mới quyết định cấu hình phù hợp.

## 21. Những sai lầm thường gặp

- **Chỉ đo kernel time:** bỏ qua queue, provisioning, data staging, checkpoint và validation.
- **So sánh phạm vi đo khác nhau:** một cấu hình tính cả I/O, cấu hình khác chỉ tính compute.
- **Dùng CPU utilization thay parallel efficiency:** hai chỉ số phản ánh các khía cạnh khác nhau.
- **Không ghi baseline:** speedup không có ý nghĩa nếu baseline hoặc đơn vị p không rõ.
- **Nhầm strong scaling với weak scaling:** hai phép thử trả lời hai câu hỏi khác nhau.
- **Giả định speedup tuyến tính:** serial fraction, communication và synchronization làm giảm lợi ích.
- **Chỉ xem average:** straggler hoặc rank chậm bị che khuất.
- **Benchmark bằng input không đại diện:** kết quả không phản ánh production.
- **Không kiểm tra correctness:** cấu hình nhanh nhưng kết quả sai vẫn được tính là thành công.
- **Chỉ tính giá node:** bỏ qua GPU, network, storage, license, transfer và idle capacity.
- **Không tính thời gian cấp phát:** node có thể bị tính phí khi job chờ I/O hoặc chưa dùng hết.
- **Tối ưu latency cho workload batch:** có thể làm giảm throughput và tăng cost trên tổng số nghiệm.
- **Dùng Spot cho job không thể phục hồi:** chi phí retry có thể vượt phần tiết kiệm.
- **Không tính checkpoint:** bỏ qua cả I/O overhead lẫn chi phí chạy lại khi failure.
- **Scale node để xử lý queue wait:** tăng node trong job không nhất thiết giúp scheduler cấp job sớm hơn.
- **Không lưu metadata benchmark:** không thể tái lập hoặc giải thích khác biệt giữa hai lần chạy.

## 22. Checklist đánh giá hiệu suất và chi phí HPC

Trước khi chốt cấu hình, hãy xác nhận:

- [ ] Đã định nghĩa mốc start và end của time-to-solution.
- [ ] Đã tách queue, provisioning, stage-in/out, initialization, compute và validation.
- [ ] Đã ghi input, checksum, application version, compiler và MPI version.
- [ ] Đã ghi CPU/GPU model, memory, interconnect, node count và rank/thread mapping.
- [ ] Baseline có ý nghĩa và đơn vị p được nêu rõ.
- [ ] Strong scaling và weak scaling được thử đúng mục tiêu.
- [ ] Speedup và parallel efficiency được tính từ cùng phạm vi đo.
- [ ] Đã kiểm tra Amdahl limit và phần công việc tuần tự.
- [ ] Đã profiling communication, synchronization, imbalance và I/O.
- [ ] Đã đo critical path, maximum rank time và tail latency.
- [ ] Benchmark được lặp lại và báo độ phân tán.
- [ ] Kết quả đáp ứng precision/tolerance và completeness.
- [ ] Cost bao gồm compute, accelerator, network, storage, transfer, license và dịch vụ.
- [ ] Đã tính billable time, idle allocation, reservation và retry.
- [ ] Cost per solution chỉ tính nghiệm hợp lệ.
- [ ] Đã so sánh Pareto frontier theo deadline và ngân sách.
- [ ] Có dashboard, cost attribution và cảnh báo production.
- [ ] Đã lưu cấu hình và artifact để tái lập benchmark.

## 23. Ghi nhớ

Đánh giá HPC phải kết hợp time-to-solution, hiệu suất song song và chi phí toàn cụm. TTS phản ánh thời gian từ submit tới kết quả hợp lệ; speedup và parallel efficiency cho biết lợi ích khi tăng tài nguyên; strong scaling giữ nguyên bài toán, còn weak scaling tăng kích thước theo số worker.

Khi tăng node, phần tuần tự, communication, synchronization, load imbalance và I/O có thể làm giảm lợi ích. Hãy dùng profiling và benchmark lặp lại với input, phần mềm, kiến trúc và tiêu chí đúng được ghi nhận. Chi phí toàn cụm cần tính compute/GPU, network, storage, data transfer, license, scheduler, idle capacity và retry. Cuối cùng, chọn cấu hình trên Pareto frontier sao cho đáp ứng deadline và chất lượng với cost per solution phù hợp; không chọn chỉ theo số core hoặc tốc độ của một kernel.
