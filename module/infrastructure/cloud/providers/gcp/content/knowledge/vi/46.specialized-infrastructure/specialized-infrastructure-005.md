# Thiết kế HPC với Compute Engine và mạng hiệu năng cao

High Performance Computing (HPC) là nhóm phương pháp sử dụng nhiều tài nguyên tính toán để giải những bài toán có khối lượng xử lý lớn: mô phỏng động lực học chất lưu (CFD), phân tích phần tử hữu hạn (FEA), mô hình thời tiết, mô phỏng vật lý, tính toán tài chính hoặc xử lý dữ liệu khoa học. Một bài toán HPC có thể chạy trên một máy rất mạnh, hoặc chia thành hàng nghìn tiến trình trên nhiều máy cần trao đổi dữ liệu với độ trễ cực thấp.

Google Cloud cung cấp Compute Engine với nhiều dòng máy, mạng VPC, các tùy chọn mạng hiệu năng cao, bộ nhớ/lưu trữ và dịch vụ vận hành hỗ trợ xây dựng cụm HPC. Tuy nhiên, không phải cứ tạo nhiều VM là có HPC tốt. Kết quả phụ thuộc vào **mô hình song song của ứng dụng, hiệu năng giao tiếp giữa node, vị trí đặt VM, kiến trúc bộ nhớ, khả năng đọc/ghi dữ liệu, scheduler, quota và ngân sách**. Thiết kế đúng cần đo *thời gian hoàn thành bài toán* thay vì chỉ nhìn số vCPU hoặc tốc độ danh nghĩa của một giao diện mạng.

## 1. Phân biệt HPC với các workload cloud thông thường

Ứng dụng web có thể phân phối nhiều request tương đối độc lập trên các instance khác nhau. Một ứng dụng HPC dùng MPI có thể yêu cầu tất cả tiến trình cùng đạt điểm đồng bộ trước khi bước mô phỏng tiếp tục; nếu một node chậm hoặc mạng có độ trễ cao, cả tác vụ bị kéo dài.

| Đặc điểm | Web/ứng dụng dịch vụ thông thường | Workload HPC |
| --- | --- | --- |
| Đơn vị công việc | Request hoặc task độc lập | Job, rank, domain decomposition, collective operation |
| Mục tiêu chủ yếu | Latency, availability, RPS | Time-to-solution, throughput job, hiệu quả song song |
| Giao tiếp | HTTP/gRPC, database, queue | MPI, TCP và có thể RDMA trên phần cứng hỗ trợ |
| Cách mở rộng | Thêm instance để phục vụ request | Thêm CPU/node, nhưng phải xét chi phí đồng bộ |
| Rủi ro thường gặp | Quá tải CPU, DB, timeout | Mạng chậm, phân bố tải lệch, I/O nghẽn, một rank lỗi |
| Scheduler | Autoscaler hoặc job queue chung | Slurm, hệ thống batch/scheduler phù hợp |

Có thể chia workload HPC thành hai nhóm:

- **Loosely coupled:** mỗi task gần như độc lập, ví dụ chạy hàng nghìn tham số mô phỏng riêng hoặc render nhiều khung hình. Thường dễ mở rộng theo số task, có thể sử dụng Spot VM nếu có checkpoint hoặc retry phù hợp.
- **Tightly coupled:** nhiều tiến trình liên tục trao đổi dữ liệu, ví dụ một mô phỏng CFD phân miền trên nhiều node. Cần đặc biệt quan tâm đến latency, bandwidth, topology, tính đồng nhất của node và placement.

Từ đầu phải biết ứng dụng thuộc nhóm nào; một kiến trúc tối ưu cho batch độc lập có thể không phù hợp với MPI đa node.

## 2. Thu thập yêu cầu và hồ sơ hiệu năng

Trước khi lựa chọn machine type, nhóm cần đo một bài toán đại diện ở môi trường đang chạy:

| Câu hỏi | Dữ liệu cần ghi | Quyết định liên quan |
| --- | --- | --- |
| Job dùng bao nhiêu CPU core? | CPU utilization, số rank/thread, hiệu quả scale | Số vCPU và node |
| Dùng bao nhiêu RAM? | Peak RSS, memory footprint của mỗi rank, NUMA locality | Dòng máy, RAM/node |
| Trao đổi giữa các rank thế nào? | MPI message size, collective frequency, latency sensitivity | Mạng, placement, RDMA |
| Dữ liệu đầu vào và checkpoint lớn bao nhiêu? | Tổng byte, IOPS, throughput, số file nhỏ | Local SSD, Hyperdisk, Filestore, Parallelstore |
| Job chạy bao lâu? | Median/p95 runtime, thời gian khởi tạo và chờ queue | Scheduler, Spot/standard VM |
| Có GPU hay accelerator không? | GPU memory, kernel utilization, data transfer | GPU machine family, thư viện GPU |
| Bao nhiêu job chạy đồng thời? | Queue depth, job priority, peak demand | Quota, capacity, cluster autoscaling |

Ví dụ, một job yêu cầu 64 rank MPI, mỗi rank dùng khoảng 2 GiB RAM và thường trao đổi thông điệp nhỏ sau mỗi vòng giải. Nếu chỉ tăng số node mà không cải thiện interconnect, phần thời gian chờ đồng bộ có thể tăng mạnh và time-to-solution không giảm.

Hãy chốt bộ dataset và phiên bản chương trình để thử nghiệm. Không so sánh hai VM trên input khác nhau hoặc khi code được biên dịch bằng những compiler flags khác nhau.

## 3. Kiến trúc tham chiếu một cụm HPC trên GCP

Một cụm HPC điển hình gồm login/head node, scheduler, compute nodes, storage và hệ thống quan sát. Các thành phần điều khiển nên tách khỏi node đang chạy job để thao tác quản trị không cạnh tranh tài nguyên với bài toán.

~~~mermaid
flowchart TB
  U["Nhà nghiên cứu / CI"] --> L["Login node / IAP / OS Login"]
  L --> Q["Slurm controller và job queue"]
  Q --> C1["Compute Engine worker group A"]
  Q --> C2["Compute Engine worker group B"]
  C1 <-->|"MPI / network hiệu năng cao"| C2
  C1 <--> F["Shared filesystem"]
  C2 <--> F
  F <--> O["Cloud Storage: input / artifact / backup"]
  Q --> M["Metrics, logs, job accounting"]
  C1 --> M
  C2 --> M
  I["IAM, quota, image và policy"] --> Q
  I --> C
~~~

Mũi tên giữa các worker là biểu diễn logic giao tiếp đa node, không phải một liên kết mạng độc lập có sẵn trong mọi VPC. Với RDMA, sơ đồ thực tế cần thể hiện chính xác NIC, interface và mạng được dòng máy hỗ trợ.

Các quyết định kiến trúc chính:

1. Chạy compute nodes trong **một zone** cho job tightly coupled khi phần cứng và placement hỗ trợ, tránh latency liên zone không cần thiết.
2. Dùng các VM có cấu hình đồng nhất trong một partition để giảm tình trạng rank chậm.
3. Đặt scheduler, image, storage và cơ chế cấp quyền theo vòng đời rõ ràng.
4. Không tạo public IP cho compute nodes nếu không cần; sử dụng đường quản trị và egress có kiểm soát.
5. Tách dữ liệu đầu vào, scratch tạm thời, checkpoint và đầu ra cuối cùng theo yêu cầu hiệu năng và độ bền.

## 4. Lựa chọn dòng máy Compute Engine

Compute Engine có các dòng máy hướng đến HPC, compute-intensive hoặc GPU workloads; các ví dụ có thể gồm dòng H3, H4D và những dòng C hoặc A phù hợp. Danh mục chính xác, số lượng vCPU, RAM, GPU, network bandwidth, RDMA, kiểu đĩa và zone được hỗ trợ có thể thay đổi theo phiên bản sản phẩm và vị trí. **Không giả định một tính năng có trên mọi máy chỉ vì cùng chạy Compute Engine.**

| Tiêu chí | Cách đánh giá |
| --- | --- |
| Hiệu năng CPU | Kiến trúc CPU, clock, instruction sets, compiler optimization và kết quả solver benchmark |
| Memory capacity | Số GiB trên node; đủ RAM cho rank và buffer hay không |
| Memory bandwidth / NUMA | Băng thông bộ nhớ và locality khi nhiều tiến trình chạy cùng node |
| Network | gVNIC, băng thông/tier được hỗ trợ, latency, RDMA nếu có |
| GPU/accelerator | Độ tương thích CUDA/driver, GPU memory và interconnect theo dòng máy |
| Storage | Loại Persistent Disk/Hyperdisk/Local SSD được hỗ trợ, băng thông và IOPS |
| Availability | Quota, capacity thực tế tại zone, reservation và chính sách bảo trì |
| Chi phí | Giá mỗi node-hour và giá cho một job hoàn tất, không chỉ giá mỗi vCPU |

Ví dụ, nếu job sử dụng rất nhiều RAM nhưng CPU không bão hòa, tăng số CPU cores có thể chỉ làm chi phí tăng. Nếu job chủ yếu trao đổi MPI và CPU bị idle trong lúc đợi mạng, cần tập trung vào giao tiếp, placement và phân vùng dữ liệu trước khi đổi sang máy có nhiều vCPU hơn.

Một nhóm nên thử ít nhất hai cấu hình được hỗ trợ và đo time-to-solution với đúng job đại diện. Không chọn VM chỉ từ mức bandwidth tối đa được quảng cáo.

## 5. Placement và miền lỗi

Với HPC tightly coupled, khoảng cách giữa các node và topology mạng ảnh hưởng trực tiếp đến latency. Compute Engine có các tùy chọn placement policy, trong đó **compact placement** có thể hữu ích cho nhóm máy cần đặt gần nhau, nhưng mức hỗ trợ phụ thuộc machine family, zone, số lượng VM và khả năng cấp phát.

Nguyên tắc:

- Ưu tiên đặt nhóm MPI trong cùng zone; tránh trải một communicator qua các region.
- Xác minh loại VM có hỗ trợ placement policy dự kiến và giới hạn số node.
- Kiểm tra capacity thực tế trước khi đặt ngưỡng hàng nghìn rank cho một job.
- Ghi rõ mapping scheduler partition với nhóm máy, zone và đặc tính mạng.
- Không để một job MPI nhiều node bị phân tán vào các máy có cấu hình hoặc network tier khác nhau ngoài chủ đích.

Đặt gần nhau có thể giảm latency nhưng cũng tập trung rủi ro lỗi trong cùng miền hạ tầng. Đây là đánh đổi có ý thức của HPC. Độ bền và phục hồi được giải quyết bằng checkpoint, khả năng chạy lại job, backup dữ liệu và kế hoạch region dự phòng, thay vì buộc một job MPI đồng bộ trải qua nhiều region.

## 6. gVNIC, băng thông mạng và RDMA

Google Virtual NIC (**gVNIC**) là giao diện mạng tối ưu của Google Cloud được hỗ trợ trên các loại VM tương ứng. Dùng gVNIC và network performance tier phù hợp có thể giúp đạt throughput TCP/IP cao hơn, nhưng throughput thực tế còn chịu giới hạn của VM, kiểu lưu lượng, số flow, CPU, packet size và điểm đích.

**Remote Direct Memory Access (RDMA)** là phương thức cho phép giao tiếp bộ nhớ giữa các node với overhead CPU thấp hơn trong những điều kiện phù hợp. Trên Google Cloud, khả năng Cloud RDMA và kết nối hiệu năng cao chỉ có trên một số loại VM/cấu hình được hỗ trợ, đi cùng driver, runtime và cấu trúc network riêng theo tài liệu sản phẩm.

| Thuộc tính | Mạng VPC TCP/IP thông thường | RDMA trên cấu hình được hỗ trợ |
| --- | --- | --- |
| Mô hình ứng dụng | Socket TCP/UDP, HTTP/gRPC, MPI qua TCP | MPI/library có transport RDMA tương thích |
| Overhead CPU | Qua TCP/IP stack và network processing | Có thể giảm overhead nhờ data path thích hợp |
| Yêu cầu hệ điều hành | NIC driver, gVNIC nếu dùng | Driver, userspace stack và cấu hình RDMA tương thích |
| Hạn chế | Băng thông/latency theo loại VM và đường mạng | Hạn chế theo machine family, zone, topology, image và library |
| Mức tương thích | Rộng với phần lớn workload | Cần benchmark và kiểm tra framework/transport |

Không thể bật RDMA chỉ bằng cách chọn gVNIC hoặc tăng MTU. Với loại VM hỗ trợ Cloud RDMA, cần thiết kế đúng NIC/interface, image/driver, library (ví dụ MPI build với transport tương thích) và kiểm tra connectivity qua đúng đường dữ liệu. Cấu hình cụ thể phải lấy theo tài liệu của dòng máy và phiên bản phần mềm đang dùng.

## 7. Độ trễ, băng thông và kích thước thông điệp

Hiệu năng MPI không được quyết định bởi một con số Gbps. Với message nhỏ, latency mỗi lần gửi và tần suất collective có thể chiếm ưu thế; với message lớn, bandwidth, memory copy và độ bão hòa của mạng quan trọng hơn.

Mô hình đơn giản cho một thông điệp:

\[
T_{\text{message}} \approx L + \frac{S}{B}
\]

Trong đó \(L\) là latency cố định, \(S\) là kích thước thông điệp và \(B\) là băng thông hữu hiệu. Đây chỉ là phép gần đúng: truyền đồng thời nhiều message, congestion, MPI collectives và topology có thể làm kết quả khác đáng kể.

Các phép đo nên bao gồm:

- **Ping-pong latency:** thông điệp nhỏ giữa hai node và giữa nhiều cặp node.
- **Sustained bandwidth:** thông điệp lớn và nhiều flow để đánh giá băng thông hữu hiệu.
- **MPI collectives:** Allreduce, Alltoall, Barrier với số rank tăng dần.
- **Ứng dụng thật:** time-to-solution và thời gian MPI wait, không chỉ microbenchmark.

Đối với cùng một mô phỏng, tăng số rank có thể giảm thời gian tính toán nhưng tăng chi phí đồng bộ. Hãy tìm điểm mà lợi ích tính toán còn lớn hơn overhead giao tiếp.

## 8. Thiết kế VPC, subnet, firewall và MTU

Cụm HPC cần VPC/subnet đủ địa chỉ cho worker nodes, controller, storage endpoints và hệ thống quản trị. Với một cụm scale theo đợt, IPAM phải tính **số VM cao nhất**, không chỉ số VM đang chạy lúc bình thường.

Một sơ đồ phân đoạn hợp lý có thể gồm:

| Nhóm | Thành phần | Nguyên tắc |
| --- | --- | --- |
| Management | Login node, scheduler, monitoring | Chỉ nguồn quản trị được phép |
| Compute | Worker nodes, MPI traffic | Cho phép luồng worker-worker cần thiết, không public ingress |
| Storage | NFS/parallel FS endpoint, object storage path | Chỉ workload được ủy quyền |
| Egress | Package registry, APIs và endpoint cập nhật | Private Google Access/NAT/proxy theo yêu cầu |

Các chính sách firewall phải khớp cổng/transport thực tế của scheduler, MPI và storage. Không mở toàn bộ mọi cổng từ internet chỉ vì MPI có thể sử dụng nhiều port động. Kiểm tra riêng hành vi multicast, UDP hoặc các transport đặc thù nếu ứng dụng sử dụng.

**MTU:** VPC cho phép cấu hình MTU trong phạm vi mà sản phẩm hỗ trợ, nhưng jumbo frame chỉ có lợi khi đường đi end-to-end và NIC phù hợp. MTU không tương thích có thể gây fragmentation, packet drop hoặc kết nối khó chẩn đoán. Với Cloud VPN, Interconnect hoặc RDMA, phải xét giới hạn MTU của từng đường kết nối thay vì lấy MTU của VPC làm kết luận chung.

Lệnh quan sát mạng ở mức cơ bản:

~~~bash
gcloud compute networks describe HPC_VPC \
  --project=PROJECT_ID \
  --format="yaml(name,mtu,autoCreateSubnetworks)"

ip -br link
ip -s link
~~~

Hai lệnh ip chạy trên Linux worker node. Các bước này chỉ kiểm tra cấu hình/đếm gói; chúng không chứng minh rằng luồng MPI đã dùng đúng NIC tốc độ cao hoặc RDMA.

## 9. Vì sao Cloud Interconnect không thay thế mạng nội bộ HPC?

Cloud Interconnect và HA VPN cung cấp kết nối giữa Google Cloud với datacenter hoặc các mạng khác theo công nghệ tương ứng. Chúng hữu ích cho giai đoạn đưa dữ liệu đầu vào lên cloud và trả kết quả về tổ chức, nhưng không phải lựa chọn thay thế tự động cho mạng inter-node latency thấp của một job MPI.

Nếu từng bước mô phỏng cần trao đổi dữ liệu với một node ở on-premises, độ trễ xuyên WAN có thể làm mất lợi thế của cụm VM mạnh. Mô hình thường hiệu quả hơn là:

1. Chuyển dataset hoặc checkpoint cần thiết lên storage ở gần compute cluster.
2. Chạy phần tính toán tightly coupled trong cùng zone/placement phù hợp.
3. Đưa artifact và kết quả cuối cùng về storage bền vững.
4. Đồng bộ với datacenter theo batch hoặc cơ chế đã thiết kế.

Khi dữ liệu nhạy cảm phải ở on-prem hoặc chịu ràng buộc residency, cần xem lại mục tiêu đặt compute ở đâu; không cố tối ưu bằng cách kéo mọi vòng lặp thuật toán xuyên hai mạng xa nhau.

## 10. Lưu trữ HPC: input, scratch, checkpoint và output

Các pha I/O của HPC có tính chất khác nhau. Một storage class không nhất thiết tối ưu cho mọi pha.

| Lớp dữ liệu | Đặc tính | Lựa chọn trên GCP cần đánh giá |
| --- | --- | --- |
| Input/reference | Đọc nhiều lần, cần bền vững | Cloud Storage, dữ liệu được stage vào file system |
| Shared working set | Nhiều node đọc/ghi đồng thời | Filestore hoặc Parallelstore trên vùng/VM hỗ trợ |
| Local scratch | Tạm thời, throughput/IOPS cao, không yêu cầu bền vững | Local SSD hoặc disk tương thích |
| Checkpoint | Bản lưu định kỳ để chạy lại sau lỗi | Storage bền vững, snapshot/backup hoặc object storage theo kiến trúc |
| Final results | Lưu lâu, chia sẻ với pipeline khác | Cloud Storage và lifecycle policies |

**Cloud Storage** là object storage, không mặc nhiên có ngữ nghĩa POSIX đầy đủ của một shared filesystem. FUSE/mounting có thể hữu ích trong một số ứng dụng nhưng cần kiểm tra chi phí metadata, consistency và hiệu năng với nhiều file nhỏ.

**Filestore** cung cấp file sharing được quản lý qua giao thức tương ứng; **Parallelstore** hướng đến một số workload HPC/AI cần throughput cao nếu sản phẩm, region và hình thức kết nối được hỗ trợ. Không mặc định loại máy nào cũng dùng được mọi cấp dịch vụ hoặc mức throughput công bố; kiểm tra giới hạn cấp phát và benchmark theo workload thật.

**Local SSD** có thể rất nhanh nhưng mang tính tạm thời theo vòng đời VM. Không đặt checkpoint duy nhất hoặc đầu ra không thể tái tạo trên Local SSD. Đưa dữ liệu quan trọng ra storage bền vững trước khi node bị xóa, hỏng hoặc bị thu hồi.

## 11. Phân bố file và tối ưu I/O song song

HPC thường gặp hai kiểu nghẽn:

- Một số file rất lớn, yêu cầu throughput tuần tự cao.
- Hàng triệu file nhỏ, yêu cầu metadata operations và số IOPS lớn.

Với workload thứ hai, file listing, create và stat có thể tốn thời gian hơn đọc nội dung. Thử thay đổi layout dataset, gom file nhỏ khi định dạng cho phép và sử dụng chiến lược sharding để giảm tranh chấp metadata.

Các phép thử hữu ích:

| Phép thử | Điều cần đo |
| --- | --- |
| IOR hoặc công cụ tương đương | Read/write throughput khi nhiều node truy cập |
| mdtest hoặc workload metadata | Create/stat/remove và latency file nhỏ |
| Checkpoint application benchmark | Kích thước, thời gian checkpoint và resume |
| Scale test | Hiệu năng khi tăng từ một node lên nhiều node |

Không lấy kết quả benchmark từ cache máy chủ hoặc page cache làm throughput storage thực nếu mục tiêu là đo I/O bền vững. Ghi rõ kích thước dataset, cache policy, cách flush và điều kiện chạy.

## 12. Scheduler: Slurm, job queue và cluster autoscaling

Scheduler như **Slurm** quản lý việc xếp hàng, phân bổ node và chạy batch jobs. Trên Google Cloud, Cluster Toolkit và những mẫu triển khai được hỗ trợ có thể giúp tự động hóa thành phần hạ tầng cho HPC; đây là công cụ xây dựng kiến trúc, không thay thế trách nhiệm vận hành scheduler và kiểm thử tương thích phiên bản.

Một vòng đời thông thường:

~~~mermaid
flowchart LR
  S["Nộp job"] --> Q["Slurm queue"]
  Q --> C["Cấp phát worker nodes"]
  C --> D["Stage data / chuẩn bị môi trường"]
  D --> R["MPI / solver execution"]
  R --> O["Checkpoint + output"]
  O --> U["Thu hồi node khi phù hợp"]
  R --> M["Metric / exit code / accounting"]
~~~

Cần định nghĩa:

- Các partition theo nhu cầu CPU/memory/GPU/network và mức ưu tiên.
- Số node tối thiểu/tối đa, queue timeout, preemption policy và thời gian scale-out.
- Cách xử lý job MPI khi không cấp đủ đồng thời tất cả node cần thiết.
- Hạn chế chọn node khác machine type, zone hoặc image khi job cần môi trường đồng nhất.
- Cách tắt node idle để giảm chi phí nhưng vẫn giữ controller, trạng thái job và dữ liệu an toàn.

Với batch độc lập, Cloud Batch hoặc một hệ thống orchestration khác có thể phù hợp tùy loại tác vụ. Không dùng một công cụ điều phối chủ yếu dựa trên task độc lập rồi kỳ vọng nó tự đảm bảo các yêu cầu MPI multi-node tightly coupled nếu sản phẩm chưa hỗ trợ đúng semantics đó.

## 13. Ví dụ script Slurm chạy solver MPI

Mẫu job dưới đây yêu cầu bốn node và tám MPI ranks trên mỗi node. Giá trị chỉ minh họa; số rank phải phù hợp CPU, RAM và chính sách partition đang dùng.

~~~bash
#!/bin/bash
#SBATCH --job-name=cfd-benchmark
#SBATCH --partition=hpc-cpu
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=8
#SBATCH --time=00:30:00
#SBATCH --output=logs/%x-%j.out

set -euo pipefail

echo "Job ID: $SLURM_JOB_ID"
echo "Nodes: $SLURM_JOB_NODELIST"

module load mpi
srun --mpi=pmix ./solver --input ./datasets/case-01.in
~~~

**Điều kiện trước khi chạy:** partition hpc-cpu tồn tại; môi trường có module mpi tương ứng; MPI build và Slurm hỗ trợ cùng PMIx mode; thư mục logs đã tồn tại; executable solver cùng dataset khả dụng trên các node.

Không phải mọi Slurm/MPI installation đều dùng được giá trị **--mpi=pmix** giống nhau. Hãy kiểm tra bằng **srun --mpi=list** và các thiết lập của cluster. Với transport RDMA, cần xác minh MPI/UCX hoặc stack tương ứng chọn đúng đường mạng; lệnh srun thành công không chứng minh RDMA đã hoạt động.

Nên lưu phiên bản solver/compiler/MPI và các environment variables ảnh hưởng thread affinity để kết quả benchmark có thể tái lập.

## 14. MPI tuning, CPU affinity và NUMA

HPC performance chịu ảnh hưởng bởi vị trí tiến trình trên CPU và bộ nhớ. Với node có nhiều NUMA domains, tiến trình có thể truy cập bộ nhớ ở domain xa hơn, làm tăng latency và giảm bandwidth hữu hiệu.

Các thực hành:

- Đặt số rank phù hợp với số core thực và cách hyperthreading được sử dụng.
- Dùng CPU binding/affinity để giảm di chuyển tiến trình không cần thiết.
- Đánh giá NUMA locality giữa thread, memory allocation và NIC.
- Tránh oversubscription nếu ứng dụng không được thiết kế để chia sẻ core.
- Giữ đồng nhất compiler flags, MPI library và OS image giữa các worker.
- Đo cả CPU time, MPI wait, memory bandwidth và số lần cache miss khi có công cụ phù hợp.

Với ứng dụng hybrid MPI + OpenMP, tổng số thread có thể xấp xỉ:

\[
\text{Threads/node} \approx
\text{MPI ranks/node} \times \text{OpenMP threads/rank}
\]

Nếu một node có 64 core hữu dụng nhưng cấu hình 64 MPI ranks và mỗi rank tạo 4 OpenMP threads, có thể tạo 256 threads cạnh tranh CPU. Điều chỉnh **OMP_NUM_THREADS**, số rank và affinity theo kết quả benchmark thay vì mặc định càng nhiều thread càng tốt.

## 15. IaC minh họa: Compute Engine worker không public IP

Terraform có thể chuẩn hóa một worker node. Ví dụ dưới đây minh họa cách chọn subnet, NIC, service account và OS Login cho một VM **có hỗ trợ gVNIC**:

~~~hcl
resource "google_compute_instance" "hpc_worker" {
  project      = var.project_id
  name         = "hpc-worker-example"
  zone         = var.zone
  machine_type = var.machine_type

  boot_disk {
    initialize_params {
      image = var.image
    }
  }

  network_interface {
    subnetwork = var.subnetwork_self_link
    nic_type   = "GVNIC"
    # Không khai báo access_config: không cấp external IPv4 ở đây.
  }

  service_account {
    email  = var.worker_service_account_email
    scopes = ["cloud-platform"]
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  labels = {
    role = "hpc-worker"
  }
}
~~~

Đây là **fragment**, không phải một cluster Terraform hoàn chỉnh: inputs chưa được khai báo, chưa có scheduler, placement policy, file system, firewall, OS image bootstrap hoặc quota. Cần bổ sung các phần này theo loại VM và công cụ orchestration thực tế.

Phạm vi OAuth **cloud-platform** không có nghĩa tự cấp quyền Owner: quyền truy cập cuối cùng vẫn được IAM giới hạn. Service account dùng cho worker chỉ nên có role cần thiết để đọc dữ liệu đầu vào, ghi artifact hoặc metric; không dùng tài khoản quản trị project cho mọi node.

Mẫu trên minh họa VPC/gVNIC, **không phải cấu hình Cloud RDMA**. Những machine family hỗ trợ RDMA có yêu cầu network interface, image, driver và placement riêng; phải làm theo tài liệu phần cứng tương ứng thay vì lấy fragment này làm cấu hình RDMA.

## 16. Chuẩn bị image, dependency và dữ liệu đầu vào

Một cụm 100 node sẽ mất nhiều thời gian khởi động nếu mỗi node phải tải compiler, MPI, solver và hàng trăm GiB dữ liệu từ internet lúc job bắt đầu. Nên xây dựng image hoặc cấu hình khởi tạo có version cho các thành phần ổn định, đồng thời stage dataset qua storage phù hợp.

Quy trình thực hành:

1. Chuẩn hóa base image và phiên bản kernel/driver/NIC.
2. Cài đặt compiler, MPI, solver và thư viện toán học có cùng ABI phù hợp.
3. Xác minh license server, biến môi trường và các quyền truy cập cần thiết.
4. Lưu image/digest, cấu hình bootstrap và package versions để rollback.
5. Tải dữ liệu vào storage/working directory gần worker trước khi job MPI bắt đầu.
6. Kiểm tra checksum và cấu hình để nhiều worker không tải trùng dataset lớn không cần thiết.
7. Chạy smoke test MPI trước khi đưa cluster vào phục vụ workload thật.

Khi cần chạy cập nhật định kỳ, ưu tiên xây dựng lại image và canary trên partition thử nghiệm hơn việc sửa thủ công từng node. Những thay đổi không đồng nhất có thể gây lỗi bí ẩn chỉ xuất hiện khi job chạy trên một nhóm node cụ thể.

## 17. Quota, capacity và đặt lịch tài nguyên

HPC thường cần cấp phát nhiều VM cùng lúc. Có quota chưa đồng nghĩa zone hiện có đủ capacity cho đúng machine family. Ngược lại, có capacity không đảm bảo project có quota hoặc quyền dùng loại máy đó.

Hãy kiểm tra:

- Quota vCPU/GPU/Local SSD/network theo region hoặc cơ chế quota của sản phẩm.
- Machine type và tính năng placement/RDMA có được cung cấp tại zone không.
- Khả năng đặt reservation theo chính sách sản phẩm và cam kết chi phí.
- Thời gian cần để lấy đủ node cho một job nhiều rank.
- Nguy cơ một phần node đã được tạo nhưng phần còn lại không cấp phát được.
- Chính sách queue time, retry và trả node khi job không thể bắt đầu.

Lệnh khám phá ban đầu:

~~~bash
gcloud compute machine-types list \
  --project=PROJECT_ID \
  --zones=ZONE

gcloud compute regions describe REGION \
  --project=PROJECT_ID \
  --format="yaml(quotas)"
~~~

Đây chỉ là các lệnh khám phá, không kết luận capacity tức thời cho một cụm HPC lớn. Quota có thể áp dụng ở nhiều cấp và cơ chế mới theo sản phẩm; hãy xác nhận bằng thông tin hiện hành của project, yêu cầu tăng quota hoặc chiến lược reservation khi có nhu cầu cố định.

## 18. Spot VMs, bảo trì và checkpoint

Spot VMs có thể tiết kiệm chi phí cho những job chịu được gián đoạn. Tuy nhiên, một job MPI tightly coupled có thể phải chạy lại toàn bộ khi một node bị thu hồi, làm mất thời gian và tăng tổng chi phí.

Thích hợp cho Spot khi:

- Các task độc lập, retry được mà không phát sinh side effect trùng.
- Solver hỗ trợ checkpoint/restart và checkpoint được ghi ra storage bền vững.
- Scheduler nhận biết preemption và có retry policy hữu hạn.
- Thời gian job đủ ngắn hoặc checkpoint interval đủ phù hợp với rủi ro.

Nên dùng VM tiêu chuẩn, reservation hoặc mô hình capacity đáng tin cậy hơn cho các job có deadline chặt hoặc chi phí restart cao. Một cụm có thể có partition Spot và partition standard; job được phân loại theo khả năng phục hồi.

**Checkpoint interval** là đánh đổi: checkpoint quá thường xuyên làm mất thời gian I/O; quá thưa làm mất nhiều công việc khi node bị ngắt. Hãy đo thời gian ghi checkpoint và thời gian khôi phục cùng kích thước job thật.

Không coi Local SSD là vị trí duy nhất lưu checkpoint. Khi VM bị xóa hoặc một số hình thức gián đoạn xảy ra, dữ liệu tạm thời có thể không còn.

## 19. Đo hiệu quả song song: strong và weak scaling

**Strong scaling** giữ nguyên kích thước bài toán, tăng số node. **Weak scaling** tăng kích thước bài toán tỷ lệ với số node để xem khả năng mở rộng khi khối lượng mỗi node gần như không đổi.

Giả sử một job chạy 120 phút trên một node và 20 phút trên tám node. Speedup:

\[
S(8) = \frac{120}{20} = 6
\]

Hiệu quả strong scaling với đơn vị là node:

\[
E(8) = \frac{S(8)}{8} = 75\%
\]

Ví dụ này **chỉ minh họa cách tính**, không phải kết quả benchmark của một loại VM GCP nào. Trong thực tế, cần ghi rõ cấu hình một node baseline, số core/rank mỗi node và input giống nhau.

Một bảng kết quả nên ghi:

| Nodes | MPI ranks | Time-to-solution | Speedup | Efficiency | Ghi chú |
| ---: | ---: | --- | --- | --- | --- |
| 1 | Theo cấu hình | Cần đo | 1.0 | 100% | Baseline |
| 2 | Theo cấu hình | Cần đo | Cần tính | Cần tính | Network, CPU wait |
| 4 | Theo cấu hình | Cần đo | Cần tính | Cần tính | Collective time |
| 8 | Theo cấu hình | Cần đo | Cần tính | Cần tính | I/O và contention |
| 16 | Theo cấu hình | Cần đo | Cần tính | Cần tính | Quota, scheduler, placement |

Đừng chỉ đo tốc độ của một kernel. Đo tổng thời gian từ lúc job bắt đầu xử lý đến lúc kết quả sẵn sàng; tách các pha staging, compute, communication, checkpoint và output để biết tối ưu vào đâu.

## 20. Thiết kế thí nghiệm benchmark có thể lặp lại

Quy trình đo:

1. **Cố định artifact:** solver version, container/image, compiler, MPI/transport, flags và dataset.
2. **Cố định vị trí:** cùng zone, cùng machine type, cùng placement policy và số node theo vòng test.
3. **Cố định storage:** cùng file system, dataset, cache policy và kích thước I/O.
4. **Đo network riêng:** ping-pong, bandwidth, MPI collectives trước khi chạy solver.
5. **Đo workload:** time-to-solution, CPU utilization, MPI wait, memory và I/O.
6. **Lặp nhiều lần:** đo biến thiên, tránh một lần chạy bị ảnh hưởng bởi noisy neighbor hoặc giai đoạn khởi tạo.
7. **Thay một biến:** số node, mạng, placement hoặc storage; không thay tất cả cùng lúc.
8. **Tổng hợp:** p50/p95 khi số mẫu đủ, speedup, efficiency và cost per completed job.

Nếu hệ thống có nhiều lớp cache, hãy mô tả phép đo là cold-cache hay warm-cache. Nếu benchmark micro-level cho kết quả tốt nhưng solver vẫn chậm, xem lại domain decomposition, tần suất collective, skew giữa các rank, shared-file metadata và tài nguyên bộ nhớ.

## 21. Quan sát, cảnh báo và vận hành

Hệ thống observability cho HPC cần kết hợp metrics hạ tầng với accounting của scheduler và ứng dụng:

| Lớp | Metric và tín hiệu |
| --- | --- |
| Scheduler | Queue wait, running/pending jobs, node allocation failures, retry/preemption |
| Compute | CPU utilization, NUMA/memory, disk throughput, OOM, kernel errors |
| Network | NIC throughput, packet drop, retransmission, MPI latency và collective wait |
| Storage | IOPS, throughput, metadata latency, filesystem fullness, checkpoint time |
| Ứng dụng | Time-to-solution, convergence, rank exit code, checkpoint consistency |
| Tài chính | VM node-hours, quota use, storage/egress, idle cost, chi phí mỗi job |

Cloud Monitoring và Cloud Logging có thể thu thập một phần thông tin VM/OS nếu agent và quyền được cấu hình. Những metric chuyên biệt như MPI wait hoặc solver convergence cần instrument tại ứng dụng hoặc scheduler. Đừng suy ra một job thành công chỉ vì VM còn chạy.

Các alert hữu ích: cluster mất controller, phần trăm job fail tăng, queue wait vượt mục tiêu, filesystem gần đầy, nhiều node không reachable, data staging lỗi hoặc quota chặn cấp phát. Tách thông báo lỗi job do input sai khỏi sự cố platform để không tạo alert fatigue.

## 22. Security và quản trị truy cập cụm HPC

Cụm HPC có thể xử lý dữ liệu khoa học, tài chính hoặc mô hình thuộc sở hữu trí tuệ. Các lớp bảo vệ cơ bản:

- Quản lý IAM theo người dùng, nhóm, service accounts; hạn chế project Editor/Owner.
- Dùng OS Login/IAP hoặc cơ chế quản trị được phê duyệt thay cho public SSH trên mọi worker.
- Phân tách head/login nodes và compute nodes bằng firewall; worker không cần external IP.
- Hạn chế egress đến package repositories và APIs cần thiết; kiểm tra cách nhận bản vá.
- Dùng encryption và quyền tối thiểu với bucket, Filestore/Parallelstore và disk.
- Không đưa token, SSH private key hoặc license secrets vào image và job script commit.
- Duy trì audit logs cho tạo/xóa VM, thay IAM, thay network và truy cập storage quan trọng.
- Thiết kế quota và budget alerts để một job lỗi không tạo vô hạn VM hoặc chi phí.

Nếu nhiều nhóm chia sẻ một cụm, cần đánh giá isolation ở mức Slurm partition/user, file permissions, network và dữ liệu. Không mặc định Linux user isolation trên cùng một VM là đủ cho mọi dữ liệu có yêu cầu bảo mật cao; khi cần, tách node hoặc cluster theo miền tin cậy.

## 23. Chi phí: tối ưu theo thời gian hoàn thành bài toán

Giá VM mỗi giờ chỉ là một thành phần. Một cấu hình đắt hơn nhưng hoàn thành job nhanh hơn có thể có chi phí tổng thấp hơn:

\[
C_{\text{job}} \approx
\sum_i (\text{Giờ VM}_i \times \text{Đơn giá}_i)
+ C_{\text{storage}} + C_{\text{network}}
+ C_{\text{orchestration}}
\]

Ở đây cần tính cả thời gian boot/staging, thời gian node idle chờ đủ cluster, checkpoint, thất bại và chạy lại. Chi phí data transfer khác region hoặc chuyển dataset từ datacenter lên GCP cũng có thể đáng kể.

Ví dụ, tăng từ 4 lên 8 node chỉ giảm runtime từ 60 xuống 40 phút thì node-hours tăng từ 4 lên khoảng 5,33 node-hours (chưa tính các chi phí khác). Nếu SLA yêu cầu job kết thúc sớm, đánh đổi đó có thể hợp lý; nếu không, 4 node có thể hiệu quả kinh tế hơn.

Các chiến lược:

1. Tắt worker idle bằng scheduler-aware autoscaling.
2. Dùng Spot cho nhóm job có khả năng restart.
3. Cân nhắc reservations/commitments theo nhu cầu dài hạn và điều kiện sản phẩm.
4. Đưa kết quả lâu dài vào object storage, dọn scratch sau khi job hoàn thành.
5. Tối ưu rank/thread topology và I/O trước khi thêm nhiều node.
6. Gắn nhãn job/project/team để tính chi phí theo nhóm sử dụng.

## 24. Tính sẵn sàng và DR cho HPC

HPC thường tối ưu một zone cho hiệu năng, nên cần chiến lược phục hồi khác với ứng dụng web đa region:

- Lưu source code, image build, job definitions và IaC ở nơi có thể khôi phục.
- Ghi checkpoint lên storage bền vững, kiểm thử khả năng restart từ checkpoint đó.
- Duy trì bản sao dữ liệu quan trọng sang vùng khác nếu yêu cầu RPO/RTO và chính sách lưu trữ đòi hỏi.
- Có phương án dựng lại scheduler/cluster ở zone hoặc region khác **nếu phần cứng và quota phù hợp có sẵn**.
- Không giả định có thể chuyển một job MPI đang chạy xuyên region mà không dừng/khởi động lại.
- Xác định RTO và RPO theo job/dataset, không chỉ trạng thái VM.

Ví dụ, một mô phỏng 12 giờ có checkpoint mỗi 30 phút có thể phải khởi động lại tại checkpoint gần nhất sau sự cố. Kết quả phục hồi còn phụ thuộc vào thời gian provision cluster mới và thời gian stage dataset; không được báo RTO chỉ bằng thời gian reboot một VM.

## 25. Bài thực hành: thiết kế cụm CFD nhiều node

**Tình huống:** nhóm nghiên cứu cần chạy mô phỏng CFD bằng MPI. Bài toán gốc có thời gian hoàn thành 3 giờ trên một node, bộ dữ liệu đầu vào vài trăm GiB và checkpoint được ghi định kỳ. Yêu cầu là giảm thời gian hoàn thành, nhưng vẫn kiểm soát được chi phí và có khả năng chạy lại sau lỗi node.

Hãy thực hiện:

1. Đo CPU, RAM peak, MPI wait, input/output bytes và thời gian checkpoint trên cấu hình baseline.
2. Chọn hai machine type/shape Compute Engine có hỗ trợ tại zone định chạy; ghi rõ lý do chọn.
3. Lập IPAM, subnet, firewall, management path và yêu cầu không cấp external IP cho worker.
4. Kiểm tra hỗ trợ gVNIC, placement policy, network performance tier và RDMA nếu ứng dụng cần.
5. Thiết kế head node, Slurm partition, số node tối đa, quota và policy cấp/thu hồi node.
6. Chọn shared filesystem và local scratch theo đặc tính file lớn/file nhỏ, nêu nơi lưu checkpoint.
7. Chạy microbenchmark latency, bandwidth và MPI collective; ghi rõ đường mạng đang được sử dụng.
8. Chạy solver trên 1, 2, 4 và 8 node với cùng dataset, tính speedup và efficiency.
9. Tính node-hours, chi phí storage/network và cost per completed job.
10. Mô phỏng thất bại một worker trong môi trường thử nghiệm, kiểm tra scheduler và restart từ checkpoint.

**Kết quả cần nộp:** sơ đồ kiến trúc, bảng lựa chọn VM/zone, network và storage, cấu hình scheduler/job mẫu, bảng benchmark có số liệu thực, dự toán chi phí và runbook khôi phục.

Không chạy benchmark tải cao trên project production hoặc tăng quota/cấp phát tài nguyên lớn mà chưa có phê duyệt ngân sách, giới hạn thời gian và người chịu trách nhiệm.

## 26. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Tăng vCPU mà không đo MPI wait | Time-to-solution ít giảm, chi phí tăng | Profile compute và communication riêng |
| Chọn VM chỉ theo Gbps công bố | Không đạt latency/throughput của solver | Đo MPI microbenchmarks và ứng dụng thật |
| Coi gVNIC là RDMA | Transport không dùng data path mong đợi | Xác nhận machine/NIC/driver/stack được hỗ trợ |
| Trải một job MPI tightly coupled qua các region | Latency lớn và nhiều failure domain | Giữ job trong một zone khi phù hợp |
| VM nhiều loại trong cùng partition MPI | Rank chậm tạo bottleneck đồng bộ | Dùng node có cấu hình tương đồng |
| Dùng Local SSD làm checkpoint duy nhất | Mất khả năng restart khi node bị thu hồi | Checkpoint ra storage bền vững |
| Dùng object storage như POSIX shared FS không kiểm thử | Tắc metadata hoặc semantics không phù hợp | Đánh giá Filestore/Parallelstore và I/O benchmarks |
| Không tính quota/capacity/placement | Job chờ lâu hoặc chỉ cấp phát được một phần node | Lập kế hoạch quota, reservations, queue policy |
| Dùng Spot cho job không restart được | Mất toàn bộ thời gian khi preemption | Dùng standard VM hoặc thêm checkpoint |
| Không quản lý image/MPI versions | Benchmark không tái lập, runtime lỗi | Image versioning và compatibility tests |
| Chỉ giám sát VM alive | Không phát hiện job fail hoặc không hội tụ | Job accounting, solver metrics và log |
| Bỏ qua chi phí node idle và dữ liệu | Dự toán thấp hơn chi phí thực | Đo cost per completed job |

## 27. Checklist trước khi đưa cụm HPC vào sử dụng

- Workload được phân loại loosely/tightly coupled và có baseline có thể tái lập.
- Có kết quả profile CPU, memory, network communication, I/O và runtime.
- Machine type, zone, placement, NIC và RDMA được kiểm tra theo khả năng hỗ trợ thực tế.
- Cụm có node đồng nhất theo partition và cơ chế phân bổ rank/thread phù hợp.
- IPAM, subnet, firewall, admin access và egress được thiết kế theo quyền tối thiểu.
- Shared FS, scratch, checkpoint và output có chính sách dung lượng, hiệu năng, độ bền rõ.
- Scheduler xử lý pending, retry, node capacity, time limit và cleanup.
- Quota/capacity được xác minh; có phương án không đủ node hoặc bị preemption.
- Đã thử microbenchmark network/MPI và strong/weak scaling với dataset đại diện.
- Có dashboard cho scheduler, node, network, storage, job success và cost.
- Secrets, data, image, license và service accounts được bảo vệ.
- Có checkpoint/restore và kế hoạch khôi phục cluster khi zone hoặc VM lỗi.
- Có bộ giới hạn chi phí, lịch kiểm tra và người sở hữu vận hành cụm.

Thiết kế HPC trên Google Cloud là bài toán tối ưu toàn hệ thống, không phải chỉ chọn VM mạnh nhất. Compute Engine tạo năng lực tính toán; mạng và placement phù hợp giúp các tiến trình cộng tác hiệu quả; storage và scheduler đảm bảo job luôn có dữ liệu và tài nguyên đúng lúc. Khi đo được time-to-solution, scaling efficiency và chi phí mỗi job, nhóm có thể đưa ra quyết định có căn cứ về CPU, GPU, gVNIC, RDMA, lưu trữ và quy mô cụm, đồng thời duy trì bảo mật và khả năng phục hồi của môi trường hạ tầng chuyên biệt.
