# Scheduler, hàng đợi và cấp phát tài nguyên cho công việc

Trong điện toán hiệu năng cao (HPC), một công việc tính toán thường cần nhiều CPU core, bộ nhớ lớn, GPU hoặc kết nối mạng tốc độ cao. Nhiều nhóm nghiên cứu và ứng dụng cùng chia sẻ một cụm máy, trong khi số node và thiết bị có hạn. **Scheduler** điều phối công việc nào được chạy, **hàng đợi** xác định nhóm chính sách và năng lực mà công việc có thể sử dụng, còn **cấp phát tài nguyên** quyết định node, CPU, bộ nhớ, GPU và thời gian chạy được dành cho từng job.

Ba thành phần này phối hợp để tăng mức sử dụng cụm, bảo đảm công bằng giữa người dùng và đáp ứng các yêu cầu về thời gian hoàn thành. Một job có thể phải chờ dù cụm vẫn có CPU đang rảnh, bởi scheduler cần tìm đủ tài nguyên cùng lúc, thỏa ràng buộc topology, partition, quota hoặc chính sách ưu tiên.

## 1. Vòng đời của một job HPC

Một job thường đi qua các trạng thái sau:

~~~mermaid
stateDiagram-v2
    [*] --> Submitted
    Submitted --> Pending
    Pending --> Eligible
    Eligible --> Running
    Running --> Completed
    Running --> Failed
    Running --> Timeout
    Pending --> Cancelled
    Eligible --> Cancelled
    Completed --> [*]
    Failed --> [*]
    Timeout --> [*]
    Cancelled --> [*]
~~~

- **Submitted:** người dùng gửi mô tả job và yêu cầu tài nguyên.
- **Pending:** hệ thống đã nhận job nhưng chưa cấp phát tài nguyên.
- **Eligible:** job thỏa các điều kiện ban đầu để được xem xét lập lịch; tên trạng thái cụ thể tùy scheduler.
- **Running:** scheduler đã cấp phát node và job đang thực thi.
- **Completed:** chương trình kết thúc thành công theo trạng thái được scheduler ghi nhận.
- **Failed hoặc Timeout:** job kết thúc lỗi hoặc vượt giới hạn thời gian.
- **Cancelled:** người dùng hoặc người quản trị hủy job trước khi hoàn tất.

Các hệ thống có thể có thêm trạng thái như held, suspended, configuring hoặc completing. Cần phân biệt job đã được nhận với job đã được cấp node: việc submit thành công không có nghĩa tài nguyên đã sẵn sàng.

Một job thường chứa các thông tin: người dùng/project, executable hoặc container image, command, số node, số task, CPU mỗi task, memory, GPU, thời gian tối đa, input/output, queue/partition và các ràng buộc placement.

## 2. Scheduler làm gì?

Scheduler là bộ điều phối trung tâm của cụm. Nó theo dõi job đang chờ, tài nguyên khả dụng, node đang chạy, chính sách người dùng và các ràng buộc kỹ thuật. Khi có cơ hội cấp phát, scheduler chọn job đủ điều kiện và xác định tài nguyên phù hợp.

Một chu trình lập lịch khái quát:

~~~mermaid
flowchart TD
    A["Nhận job và yêu cầu tài nguyên"] --> B["Kiểm tra quyền, quota và queue"]
    B --> C["Lọc job đủ điều kiện"]
    C --> D["Xếp hạng theo priority / fair-share"]
    D --> E["Tìm node và tài nguyên phù hợp"]
    E --> F{"Có thể cấp phát?"}
    F -- "Chưa" --> G["Giữ job trong hàng đợi"]
    G --> H["Chờ tài nguyên hoặc chính sách thay đổi"]
    H --> C
    F -- "Có" --> I["Cấp phát node, CPU, RAM, GPU"]
    I --> J["Khởi chạy job"]
    J --> K["Theo dõi và thu hồi tài nguyên khi kết thúc"]
~~~

Các nhiệm vụ chính:

1. Nhận và kiểm tra yêu cầu của job.
2. Xác định job có được phép dùng queue, partition hoặc tài nguyên yêu cầu hay không.
3. Tính tài nguyên còn có thể cấp phát trên từng node.
4. Chọn job theo priority, fair-share, thời điểm submit và chính sách vận hành.
5. Chọn node theo CPU, memory, GPU, network topology, feature hoặc ràng buộc vị trí dữ liệu.
6. Khởi chạy job, giám sát thời gian và trạng thái.
7. Thu hồi tài nguyên khi job hoàn tất, thất bại hoặc bị hủy.

Scheduler không làm cho một chương trình chạy nhanh hơn bằng cách tự động tăng CPU. Nó điều phối quyền sử dụng tài nguyên và bảo đảm các yêu cầu được thực thi trong giới hạn của cụm.

## 3. Hàng đợi, partition và chính sách sử dụng

Hàng đợi (queue) là nơi job chờ được xử lý. Trong nhiều nền tảng batch, queue gắn với một nhóm tài nguyên, mức ưu tiên, giới hạn thời gian hoặc chính sách truy cập.

Trong Slurm, khái niệm thường dùng là **partition**. Partition xác định tập node và các giới hạn liên quan; người dùng chọn partition khi submit job. Một partition có thể phục vụ công việc ngắn, job GPU, job tương tác hoặc job chạy dài. Trong một số dịch vụ cloud batch, đối tượng queue có thể chứa chính sách scheduling và compute environment riêng.

Ví dụ cách phân loại:

| Queue / partition | Loại công việc | Chính sách thường gặp |
|---|---|---|
| debug | Kiểm tra nhanh, thử script | Giới hạn thời gian ngắn, ít node |
| short | Job hoàn thành nhanh | Thời gian tối đa thấp, ưu tiên quay vòng nhanh |
| compute | Mô phỏng CPU hoặc xử lý song song | Nhiều CPU core, giới hạn node theo project |
| gpu | Huấn luyện hoặc tính toán tăng tốc | Node có GPU, giới hạn số GPU và driver/runtime |
| long | Mô phỏng hoặc phân tích kéo dài | Thời gian tối đa dài, có thể phải chờ lâu |
| high-memory | Job cần working set lớn | Node RAM cao, giới hạn số job đồng thời |

Tên queue chỉ mang ý nghĩa khi gắn với cấu hình thực tế. Một queue có thể dùng chung node với queue khác hoặc dành riêng node; cần xem cấu hình cụm để hiểu ranh giới tài nguyên.

### 3.1. Giới hạn queue

Các giới hạn phổ biến gồm:

- Thời gian tối đa cho một job.
- Số node, CPU, GPU hoặc memory tối đa cho mỗi job.
- Số job đang chạy và đang chờ của một người dùng hoặc project.
- Tổng tài nguyên được phép sử dụng đồng thời.
- Nhóm người dùng được quyền submit.
- Loại node hoặc feature mà job được phép yêu cầu.

Chọn queue không phù hợp có thể khiến job bị từ chối, nằm chờ lâu hoặc không thể sử dụng loại node cần thiết. Nên chọn queue theo đặc điểm công việc và kiểm tra giới hạn trước khi submit.

### 3.2. Queue không đồng nghĩa với thứ tự FIFO

Một số queue xử lý theo thứ tự đến trước, nhưng nhiều scheduler dùng priority, fair-share, reservation hoặc backfill. Vì vậy, job submit trước chưa chắc chạy trước. Một job nhỏ submit sau có thể chạy trước nếu phù hợp với khoảng tài nguyên trống và không làm chậm job ưu tiên cao đã được lên lịch.

## 4. Cấp phát CPU, node và task

Trong HPC, số CPU được yêu cầu thường biểu diễn qua số node, số task, số CPU mỗi task hoặc số core trên mỗi node. Các khái niệm này cần được khai báo nhất quán với mô hình chạy của ứng dụng.

- **Node:** máy tính vật lý hoặc máy ảo tham gia cụm.
- **CPU core:** đơn vị xử lý mà scheduler phân bổ; cách tính có thể tính theo core hoặc hardware thread tùy cấu hình.
- **Task/rank:** một tiến trình hoặc đơn vị thực thi song song, thường do MPI launcher tạo.
- **CPU per task:** số CPU được dành cho mỗi task.
- **Node count:** số node được yêu cầu cho job.

Ví dụ, một job MPI có 4 node, mỗi node chạy 16 rank, tổng cộng 64 rank. Nếu mỗi rank dùng một CPU core thì job cần tối thiểu 64 CPU core. Nếu mỗi rank chạy đa luồng với 4 thread thì yêu cầu có thể là 256 CPU core, tùy cách ứng dụng và scheduler cấu hình binding.

~~~text
Job MPI: 4 node x 16 rank/node = 64 rank

Node 1: rank  0-15
Node 2: rank 16-31
Node 3: rank 32-47
Node 4: rank 48-63

Nếu mỗi rank dùng 1 CPU:
Tổng nhu cầu = 64 CPU core

Nếu mỗi rank dùng 4 thread:
Tổng nhu cầu tối đa = 64 x 4 = 256 CPU core
~~~

Không nên chỉ yêu cầu một số CPU tùy ý rồi để ứng dụng tự tạo nhiều thread hơn số CPU được cấp. Oversubscription làm nhiều tiến trình cạnh tranh cùng core, tăng context switching và có thể giảm hiệu năng.

## 5. Cấp phát bộ nhớ, GPU và tài nguyên chuyên dụng

### 5.1. Bộ nhớ

Job cần yêu cầu memory phù hợp với working set, dữ liệu trung gian và số tiến trình đồng thời. Một job yêu cầu 8 node, mỗi node 64GiB có thể cần tổng cộng 512GiB, nhưng cách khai báo thường là memory mỗi node hoặc memory mỗi CPU tùy scheduler.

Nếu khai báo thấp hơn nhu cầu, job có thể bị OOM kill hoặc node phải chấm dứt job để bảo vệ hệ thống. Nếu khai báo quá cao, scheduler có thể không tìm được node phù hợp dù chương trình thực tế dùng ít bộ nhớ. Nên đo mức dùng peak memory từ các lần chạy thử đại diện và cộng khoảng dự phòng phù hợp.

### 5.2. GPU

GPU là tài nguyên có số lượng hữu hạn và thường gắn với loại node, model GPU, VRAM và topology liên kết. Job cần khai báo số GPU và có thể cần chỉ rõ loại GPU hoặc feature của node.

Cần kiểm tra:

- Số GPU mỗi node và số GPU cần cho job.
- VRAM cần thiết cho model và batch size.
- Driver, CUDA/ROCm và thư viện tương thích.
- Khả năng giao tiếp GPU-GPU như NVLink hoặc topology PCIe nếu workload nhạy với băng thông.
- CPU và RAM host đủ để nạp dữ liệu, điều phối và tiền xử lý.
- GPU được cấp có thực sự được sử dụng; tránh giữ GPU rảnh trong khi chương trình đang chờ I/O.

### 5.3. Network và topology

Một số workload MPI cần giao tiếp liên tục giữa các node. Scheduler có thể xét node trong cùng rack, cùng fabric hoặc nhóm node có network interconnect phù hợp. Nếu ứng dụng cần băng thông cao và độ trễ thấp, placement topology có ảnh hưởng trực tiếp đến thời gian chạy.

Với công việc độc lập theo partition, network có thể ít quan trọng hơn CPU và I/O. Với mô phỏng phân tán, chọn node chỉ dựa trên số lượng CPU có thể tạo ra hiệu năng kém nếu node nằm xa nhau về topology.

## 6. Thuật toán và chính sách lập lịch phổ biến

Các scheduler thường kết hợp nhiều thuật toán hoặc chính sách. Cách triển khai cụ thể khác nhau theo sản phẩm và cấu hình.

### 6.1. FIFO và priority scheduling

**FIFO** xem xét job theo thứ tự submit. Cách này dễ hiểu nhưng có thể khiến job lớn đứng đầu chặn các job nhỏ phía sau dù các job nhỏ có thể chạy trên phần tài nguyên đang trống.

**Priority scheduling** gán mức ưu tiên dựa trên người dùng, project, queue, QoS, thời gian chờ hoặc chính sách quản trị. Job ưu tiên cao được xem xét trước, nhưng có thể bị giới hạn bởi quota và reservation. Nếu chỉ tăng priority cho một nhóm, nhóm khác có nguy cơ chờ quá lâu.

### 6.2. Fair-share

Fair-share giúp phân chia tài nguyên công bằng giữa các người dùng hoặc project theo mức sử dụng trong quá khứ và trọng số được cấu hình. Nhóm đã dùng nhiều tài nguyên gần đây có thể bị giảm mức ưu tiên tương đối, trong khi nhóm ít sử dụng được ưu tiên hơn.

Fair-share không nhất thiết chia CPU đều tại mọi thời điểm. Mục tiêu là cân bằng quyền sử dụng trong một khoảng thời gian, tránh một project chiếm phần lớn năng lực cụm liên tục.

### 6.3. Backfill scheduling

Backfill cho phép chạy job nhỏ hoặc ngắn trong khoảng tài nguyên đang trống, nếu job đó kết thúc trước thời điểm dự kiến cần tài nguyên cho job lớn hơn. Cách này tăng mức sử dụng cụm mà vẫn bảo vệ kế hoạch của job đã được ưu tiên.

Ví dụ, job A cần 8 node và dự kiến được cấp sau 20 phút khi một nhóm node giải phóng. Job B chỉ cần 2 node và có thời gian tối đa 10 phút. Scheduler có thể chạy B ngay nếu chắc chắn B kết thúc trước khi A cần tài nguyên.

Backfill hiệu quả khi job khai báo thời gian chạy tối đa sát thực tế. Nếu mọi job đều yêu cầu thời gian quá dài, scheduler khó tìm khoảng trống an toàn. Nếu yêu cầu thấp hơn thời gian thật, job có thể bị timeout hoặc làm xáo trộn lịch.

### 6.4. Reservation và preemption

**Reservation** giữ trước một tập tài nguyên cho một thời điểm hoặc nhóm người dùng cụ thể, ví dụ phiên thực nghiệm có lịch. Reservation giúp bảo đảm năng lực cho công việc quan trọng nhưng có thể làm giảm mức sử dụng chung nếu tài nguyên được giữ mà không dùng.

**Preemption** cho phép scheduler dừng hoặc tạm dừng job có ưu tiên thấp để nhường tài nguyên cho job ưu tiên cao. Chỉ dùng hiệu quả khi workload có thể checkpoint, khôi phục hoặc chạy lại an toàn. Job không hỗ trợ checkpoint có thể mất nhiều thời gian tính toán đã thực hiện.

## 7. Ví dụ cấu hình và submit job bằng Slurm

Slurm là một workload manager phổ biến trong cụm HPC. Job thường được mô tả bằng script với các chỉ thị tài nguyên và lệnh thực thi.

Ví dụ job chạy MPI trên 4 node, 16 task mỗi node, yêu cầu 64GiB memory mỗi node và tối đa 45 phút:

~~~bash
#!/bin/bash
#SBATCH --job-name=weather-sim
#SBATCH --partition=compute
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=16
#SBATCH --cpus-per-task=1
#SBATCH --mem=64G
#SBATCH --time=00:45:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err

module load mpi
srun ./weather-simulation input/config.yaml
~~~

Submit job:

~~~bash
sbatch weather-sim.sbatch
~~~

Trong ví dụ:

- partition là compute.
- 4 node, mỗi node 16 task, tổng 64 task.
- Mỗi task yêu cầu một CPU.
- Memory được yêu cầu theo node theo cú pháp Slurm minh họa.
- Thời gian tối đa là 45 phút.
- stdout và stderr được lưu theo job name và job ID.

Cú pháp và chính sách memory có thể khác theo cấu hình cụm. Ví dụ dùng thư mục logs đã tồn tại; scheduler không tự tạo thư mục này. Với ứng dụng OpenMP hoặc hybrid MPI/OpenMP, cần tăng cpus-per-task và cấu hình số thread phù hợp.

Một ví dụ GPU có thể yêu cầu một node và hai GPU:

~~~bash
#!/bin/bash
#SBATCH --job-name=training
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --gres=gpu:2
#SBATCH --time=02:00:00
#SBATCH --output=logs/%x-%j.out

srun python train.py --config config.yaml
~~~

Tên tài nguyên GPU và cú pháp yêu cầu GPU phụ thuộc cấu hình Slurm; một số cụm dùng loại GPU cụ thể hoặc GRES/TRES được định nghĩa riêng. Luôn kiểm tra tài liệu cluster trước khi submit.

## 8. Theo dõi hàng đợi và trạng thái cấp phát

Sau khi submit, người dùng cần theo dõi job và tìm nguyên nhân nếu job chờ lâu.

Các lệnh Slurm thường dùng:

~~~bash
# Xem job của người dùng hiện tại
squeue -u "$USER"

# Xem node và partition
sinfo

# Xem chi tiết một job
scontrol show job JOB_ID

# Xem lịch sử sử dụng tài nguyên sau khi job kết thúc
sacct -j JOB_ID --format=JobID,JobName,Partition,AllocCPUS,Elapsed,State,ExitCode,MaxRSS
~~~

Một số trạng thái thường gặp:

| Trạng thái | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| PENDING (PD) | Đang chờ điều kiện lập lịch | Lý do pending, queue, quota, node và thời gian dự kiến |
| RUNNING (R) | Đang chạy | CPU, memory, GPU, I/O và log |
| COMPLETING (CG) | Đang hoàn tất và thu hồi tài nguyên | Tiến trình kết thúc, file output và cleanup |
| COMPLETED (CD) | Job hoàn tất thành công theo scheduler | Xác minh output và kết quả nghiệp vụ |
| FAILED (F) | Job kết thúc lỗi | Exit code, log và nguyên nhân runtime |
| TIMEOUT (TO) | Vượt thời gian giới hạn | Thời gian thực tế và checkpoint |
| CANCELLED (CA) | Job bị hủy | Người hoặc chính sách hủy và trạng thái output |

Để xem lý do chờ, kiểm tra trường Reason trong squeue hoặc scontrol show job. Các lý do thường gặp là thiếu CPU, memory hoặc GPU, node không khả dụng, giới hạn tài khoản, reservation, dependency hoặc priority thấp. Không nên kết luận job bị treo chỉ từ trạng thái Pending; cần đọc lý do scheduler cung cấp.

Sau khi job kết thúc, đối chiếu AllocCPUS, Elapsed và MaxRSS với yêu cầu đã khai báo. Nếu CPU được cấp nhiều nhưng mức sử dụng thấp, cần xem ứng dụng có đủ khả năng song song hay đang chờ I/O. Nếu MaxRSS sát giới hạn, tăng memory hoặc giảm batch size. Nếu thời gian chạy thường thấp hơn nhiều so với time limit, điều chỉnh yêu cầu thời gian có thể giúp backfill.

## 9. Ví dụ phân tích cấp phát tài nguyên

Giả sử cụm có 10 node giống nhau, mỗi node có 64 CPU core và 256GiB RAM. Tổng năng lực thô là 640 CPU core và 2.560GiB RAM. Sau khi trừ phần dành cho hệ điều hành và daemon, scheduler sử dụng giá trị allocatable theo cấu hình thực tế.

Ba job đang chờ:

| Job | Số node | CPU mỗi node | RAM mỗi node | Thời gian ước tính |
|---|---:|---:|---:|---:|
| A - mô phỏng lớn | 4 | 64 | 200GiB | 3 giờ |
| B - phân tích trung bình | 2 | 32 | 96GiB | 40 phút |
| C - tiền xử lý | 1 | 8 | 32GiB | 10 phút |

Nếu job A được ưu tiên và cần bốn node trống cùng lúc, scheduler phải tìm được bốn node đáp ứng cả CPU lẫn RAM. Các job khác có thể chạy trên những node còn lại nếu quota và chính sách cho phép. Nếu không đủ bốn node phù hợp, A tiếp tục chờ dù tổng CPU rảnh của cụm có thể lớn hơn 256 core, bởi tài nguyên rảnh có thể bị phân mảnh trên nhiều node hoặc không đủ RAM trên từng node.

Nếu job C chạy trong 10 phút trên một node đang rảnh và kết thúc trước khi A được cấp phát, backfill có thể cho C chạy trước. Nếu C yêu cầu 3 giờ dù thực tế chỉ cần 10 phút, scheduler khó sử dụng khoảng trống đó một cách an toàn.

Bảng giúp thấy rằng cấp phát phải xét đồng thời CPU, RAM, số node, topology, quota và thời gian. Chỉ nhìn tổng số CPU rảnh là chưa đủ.

## 10. Hiệu quả sử dụng và tối ưu yêu cầu

Yêu cầu tài nguyên nên dựa trên đo đạc, không dựa vào cấu hình lớn nhất có thể.

- Chạy benchmark nhỏ để đo CPU, memory, GPU và I/O.
- Thử nhiều kích thước node/task để tìm điểm mở rộng hiệu quả.
- Tránh yêu cầu nhiều node hơn mức ứng dụng có thể khai thác.
- Với job MPI, kiểm tra hiệu năng liên lạc giữa node và affinity/binding.
- Với GPU, kiểm tra utilization, VRAM và thời gian GPU chờ dữ liệu.
- Với job I/O-bound, xem throughput của storage và metadata server trước khi tăng CPU.
- Khai báo thời gian tối đa sát thực tế, có dự phòng hợp lý.
- Dùng job array hoặc partition khi các tác vụ độc lập, thay vì một job lớn tuần tự không cần thiết.
- Dùng checkpoint để phục hồi tiến độ của công việc dài hoặc có khả năng preemption.

Cấp phát quá ít làm job chạy chậm hoặc thất bại. Cấp phát quá nhiều làm giảm số job có thể chạy đồng thời, tăng thời gian chờ và chi phí. Mục tiêu là chọn tài nguyên đủ cho hiệu năng mong muốn với mức sử dụng hiệu quả.

## 11. Cấp phát trong môi trường cloud HPC

Trong cloud, scheduler có thể phối hợp với compute fleet hoặc autoscaling group để bổ sung node khi hàng đợi có nhu cầu. Cơ chế này cho phép mở rộng theo tải nhưng có thêm thời gian khởi tạo máy, tải image, mount storage và cấu hình mạng.

Một số đánh đổi cần xem xét:

- **Capacity on demand:** có thể tăng node khi queue dài, nhưng quota vùng và loại instance có thể giới hạn khả năng cấp phát.
- **Node startup latency:** job vẫn chờ trong khi máy mới được tạo và khởi tạo.
- **Instance type:** chọn CPU, RAM, GPU, local NVMe và network phù hợp với job.
- **Spot/preemptible capacity:** giảm chi phí nhưng node có thể bị thu hồi; job cần checkpoint và retry.
- **Placement group hoặc topology:** có thể cải thiện network cho workload MPI nhưng giới hạn khả năng tìm đủ node.
- **Chi phí nhàn rỗi:** giữ node sẵn sàng giúp giảm thời gian chờ nhưng tăng chi phí khi queue rỗng.
- **Storage throughput:** nhiều node đọc cùng dữ liệu có thể tạo bottleneck ở shared filesystem hoặc object storage.

Cloud HPC nên kết hợp queue policy, giới hạn concurrency, autoscaling và ngân sách. Nếu job ngắn nhưng node cần nhiều phút để khởi tạo, batch nhỏ có thể kém hiệu quả; gom tác vụ thành nhóm hoặc duy trì một pool nhỏ có thể giảm overhead.

## 12. Xử lý tình huống job chờ lâu hoặc chạy kém

Khi job Pending, thực hiện theo trình tự:

1. Đọc trạng thái và lý do pending từ scheduler.
2. Kiểm tra queue/partition có nhận loại job và người dùng/project hay không.
3. Đối chiếu yêu cầu CPU, RAM, GPU và node với năng lực allocatable.
4. Kiểm tra quota, giới hạn số job, reservation, dependency và QoS.
5. Kiểm tra node có bị drain, down hoặc bị ràng buộc feature/topology hay không.
6. Nếu yêu cầu tài nguyên quá lớn, chạy thử với kích thước nhỏ hơn để xác định điểm nghẽn.
7. Nếu cụm đang thiếu capacity, trao đổi với quản trị viên về node pool hoặc lịch cấp phát theo chính sách.

Khi job đã Running nhưng hiệu năng thấp:

- Kiểm tra CPU utilization và CPU binding.
- Kiểm tra memory peak, swap và lỗi OOM.
- Với GPU, xem GPU utilization, VRAM và data pipeline.
- Đo I/O wait, throughput và thời gian đọc/ghi.
- Kiểm tra network latency và communication overhead giữa node.
- So sánh thời gian từng phase với baseline.
- Kiểm tra ứng dụng có thực sự scale khi tăng số node hay không.

Không nên tăng số node theo phản xạ. Nếu ứng dụng đang chờ storage, tăng CPU có thể làm chi phí tăng mà thời gian hoàn thành không cải thiện.

## 13. Checklist submit và vận hành job HPC

- [ ] Chọn đúng queue/partition theo loại workload và quyền sử dụng.
- [ ] Xác định số node, task, CPU mỗi task và số thread của ứng dụng.
- [ ] Ước lượng memory peak cho mỗi node hoặc mỗi CPU theo cú pháp scheduler.
- [ ] Khai báo đúng số GPU, loại GPU và yêu cầu VRAM/topology nếu cần.
- [ ] Chọn thời gian tối đa dựa trên benchmark và khoảng dự phòng.
- [ ] Kiểm tra quota, QoS, reservation, dependency và giới hạn concurrency.
- [ ] Dùng image/runtime và dependency có phiên bản xác định.
- [ ] Kiểm tra đường dẫn input/output, quyền truy cập và dung lượng lưu trữ.
- [ ] Theo dõi pending reason, node allocation, log và metric khi chạy.
- [ ] Đối chiếu CPU, memory, GPU và thời gian thực tế với yêu cầu đã khai báo.
- [ ] Có checkpoint hoặc phương án retry cho job dài, dễ bị preemption.
- [ ] Xác minh output và trạng thái cuối trước khi coi công việc hoàn tất.

Scheduler quyết định thứ tự và vị trí chạy dựa trên chính sách cùng tài nguyên khả dụng; queue/partition xác định phạm vi tài nguyên và giới hạn; cấp phát mô tả phần CPU, RAM, GPU, node và thời gian dành cho job. Khi khai báo yêu cầu sát thực tế, theo dõi lý do chờ và đo hiệu năng sau chạy, người vận hành có thể giảm thời gian chờ, tăng hiệu quả sử dụng cụm và kiểm soát chi phí HPC trên đám mây.
