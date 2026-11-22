# Thiết kế workload HPC và sử dụng máy ảo GPU

Một nhóm nghiên cứu phải chạy 20.000 mô phỏng kỹ thuật trước cuối tuần; một nhóm khác cần huấn luyện mô hình AI trên tập dữ liệu lớn, trong khi nhóm thiết kế cần dựng hình 3D theo phiên làm việc. Cả ba đều muốn sử dụng năng lực tính toán lớn của Microsoft Azure, nhưng **không nên cùng chọn một loại VM GPU, cùng cấu trúc cluster hoặc cùng cơ chế tính phí**.

**High-Performance Computing (HPC)** là cách tổ chức tài nguyên tính toán, mạng và lưu trữ để thực thi khối lượng công việc đòi hỏi hiệu năng cao. **GPU** là một loại bộ xử lý tăng tốc cho các phép toán phù hợp; GPU hữu ích trong nhiều workload HPC, AI và đồ họa nhưng **không phải mọi workload HPC đều cần GPU**. Thiết kế đúng phải bắt đầu từ mô hình tính toán, mức song song, yêu cầu bộ nhớ và dữ liệu, sau đó mới chọn loại VM, scheduler và mô hình chi phí.

Bài học thuộc chương **Compute co giãn và xử lý theo lô** của module `CLOUD_PROVIDERS_AZURE`. Module giúp khám phá Azure từ subscription, resource group, Microsoft Entra ID tới mạng ảo, compute, lưu trữ và dữ liệu, rồi học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Với HPC, việc **co giãn tài nguyên theo hàng đợi và giải phóng VM khi không có việc** thường quan trọng không kém tốc độ thực thi của một job.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân loại workload thành **batch độc lập**, **HPC liên kết chặt bằng MPI**, **GPU accelerated computing**, **AI training/inference** hoặc **visualization**.
2. Lựa chọn họ VM Azure theo **CPU, GPU, VRAM, RAM, I/O và kết nối liên nút**, thay vì chỉ nhìn số vCPU.
3. Giải thích vì sao **RDMA/InfiniBand** và **accelerated networking** không phải cùng một tính năng.
4. Thiết kế tầng lưu trữ dữ liệu đầu vào, scratch và output với Azure Blob Storage, Azure Managed Lustre, Azure NetApp Files hoặc giải pháp phù hợp.
5. So sánh **Azure Batch**, **Azure CycleCloud với Slurm** và các mô hình điều phối khác theo loại job.
6. Chuẩn bị GPU driver, thư viện CUDA/ROCm, MPI, NCCL và image theo điều kiện phần cứng.
7. Lập chiến lược quota, capacity, autoscaling, checkpoint và xử lý Spot eviction.
8. Tính **chi phí mỗi job** thay vì chỉ so giá/giờ của một VM.
9. Theo dõi GPU utilization, VRAM, throughput, runtime, I/O và các lỗi phân tán.
10. Lập được kiến trúc tham khảo cho bài toán mô phỏng kỹ thuật hoặc huấn luyện AI đa node.

## 2. HPC, batch, GPU và AI: những khái niệm khác nhau

| Khái niệm | Bản chất | Ví dụ | Điều cần tối ưu |
|---|---|---|---|
| **Batch processing** | Xếp hàng rồi xử lý các tác vụ theo lô, có thể không cần tương tác trực tiếp. | Chuyển đổi 100.000 tệp, render nhiều cảnh độc lập. | Throughput, lịch chạy, autoscale, chi phí/job. |
| **HPC** | Kết hợp tài nguyên hiệu năng cao để giải bài toán tính toán lớn. | CFD, mô phỏng vật liệu, dự báo thời tiết. | Thời gian hoàn thành, tính song song, băng thông/độ trễ. |
| **CPU HPC** | Dùng CPU với khả năng tính toán/bộ nhớ/kết nối mạnh. | Một phần solver MPI, code không khai thác GPU. | Hiệu năng CPU, RAM, bộ nhớ và RDMA nếu cần. |
| **GPU computing** | Dùng GPU tăng tốc thuật toán phù hợp. | CUDA kernels, deep learning, rendering. | GPU throughput, VRAM, giao tiếp GPU–CPU/GPU–GPU. |
| **Distributed training** | Huấn luyện mô hình trên nhiều GPU hoặc node. | Data parallel, model parallel AI. | VRAM, đồng bộ gradient, interconnect, checkpoint. |
| **Inference** | Phục vụ yêu cầu dự đoán trên mô hình đã huấn luyện. | API nhận diện hình ảnh, LLM serving. | Latency, throughput, SLA, chi phí/request. |

Một job **batch độc lập** như 20.000 mô phỏng Monte Carlo có thể chạy hiệu quả trên hàng trăm CPU VM rời nhau vì mỗi tác vụ ít phải trao đổi dữ liệu. Ngược lại, một solver **MPI liên kết chặt** liên tục trao đổi dữ liệu biên giữa các tiến trình: tốc độ mạng và vị trí các node có thể quyết định hiệu năng. Một mô hình AI lớn còn cần xem **VRAM của mỗi GPU**, interconnect và cách chia tham số.

Do đó **“nhiều VM hơn” không mặc nhiên đồng nghĩa “job chạy nhanh hơn”**. Một workload tuần tự có thể gần như không hưởng lợi từ thêm node, trong khi giao tiếp đồng bộ có thể làm tốc độ kém đi khi scale quá lớn.

## 3. Phân tích workload trước khi chọn VM

Một bảng khảo sát tối thiểu nên gồm:

| Câu hỏi | Dữ liệu cần đo | Hệ quả kiến trúc |
|---|---|---|
| Tác vụ có độc lập nhau không? | Số jobs, dependency graph, dữ liệu trao đổi | Batch task pool hay cluster MPI |
| CPU/GPU đang được sử dụng ra sao? | CPU time, GPU utilization, kernel profile | CPU VM, GPU VM hay tối ưu code trước |
| Cần bao nhiêu RAM/VRAM? | Peak resident memory, GPU memory, batch size | SKU theo bộ nhớ và phương án sharding |
| I/O có là nút thắt? | Dung lượng input/output, read/write IOPS, throughput, metadata operations | Object storage hay POSIX parallel file system |
| Có liên lạc giữa các node không? | Message rate, size, collective communication | Ethernet đủ dùng hay RDMA/InfiniBand |
| Thời gian hoàn thành mục tiêu? | Deadline, queue wait, runtime thực tế | Parallelism, quota, capacity reservation khi cần |
| Có thể gián đoạn không? | Checkpoint interval, retry, idempotency | Spot, autoscale hoặc VM chuyên dụng |
| Dữ liệu có nhạy cảm không? | Phân loại dữ liệu, residency, quyền và audit | Private networking, encryption, RBAC, region |
| Có tính mùa vụ không? | Giờ chạy/ngày, số job/tháng | Scale-to-zero và ngân sách |

### Ba kiểu song song thường gặp

**Embarrassingly parallel:** mỗi tác vụ chạy trên dữ liệu riêng, gần như không trao đổi. Phù hợp hàng đợi batch và nhiều node rời nhau.

**Tightly coupled / MPI:** nhiều tiến trình giải một bài toán chung, giao tiếp thường xuyên. Cần lựa chọn mạng và cách cấp phát node phù hợp; có thể hưởng lợi từ InfiniBand/RDMA.

**GPU parallel:** một hoặc nhiều GPU thực hiện lượng lớn phép toán song song trong một node; khi phân tán sang nhiều node phải quan tâm đồng bộ tensor/gradient và băng thông liên nút.

```text
            Workload
                |
        +-------+-------+
        |               |
   Jobs độc lập?     Cần chia một job?
        |               |
        v               v
  Batch task pool    CPU MPI hoặc GPU
  + autoscale           |
                    +---+-----------+
                    |               |
               1 node đủ?      Nhiều node?
                    |               |
                    v               v
              CPU/GPU VM       Scheduler + mạng
              + local I/O       hiệu năng cao
```

## 4. Tư duy đo hiệu năng: speedup và efficiency

Giả sử một chương trình chạy **8 giờ trên 1 node**. Nếu chạy 4 node trong **2,5 giờ**, ta có:

```text
Speedup   = T(1 node) / T(N nodes) = 8 / 2,5 = 3,2
Efficiency = Speedup / N = 3,2 / 4 = 80%
```

Thời gian hoàn thành giảm nhưng không tỷ lệ tuyến tính 4 lần. Phần overhead có thể do:

- Đọc/ghi dữ liệu đầu vào và checkpoint.
- Trao đổi MPI giữa các node.
- Đồng bộ dữ liệu/gradient trên GPU.
- Phần code tuần tự, chuẩn bị dữ liệu hoặc khởi tạo môi trường.
- Tranh chấp tài nguyên lưu trữ hoặc queue wait.

Theo **Amdahl's law**, nếu có tỷ lệ công việc không song song hóa được, speedup bị giới hạn dù số node rất lớn. Ngược lại, nhiều bài toán tăng quy mô dữ liệu cùng số node có thể được phân tích theo weak scaling. Khi đánh giá, cần ghi rõ **strong scaling** (cùng kích thước bài toán, tăng node) hay **weak scaling** (tăng dữ liệu cùng tài nguyên).

Đối với GPU, đo thời gian **end-to-end** gồm tải dữ liệu và copy CPU↔GPU, không chỉ thời gian một kernel. Một GPU có thông số lý thuyết cao có thể chậm nếu VRAM không đủ, I/O liên tục bị nghẽn hoặc workload không khai thác được phép tính song song.

## 5. Chọn họ Azure VM theo đặc tính workload

Azure cung cấp nhiều họ VM; tên SKU, thế hệ phần cứng, khả năng GPU/RDMA và region sẵn có thay đổi theo thời gian. Dùng các nhóm sau để **định hướng chọn**, không coi tên series là cam kết tính năng của mọi SKU.

| Nhóm VM | Đặc điểm khái quát | Tình huống phù hợp |
|---|---|---|
| **HB/HC và một số H-series** | Tối ưu HPC chủ yếu dùng CPU, RAM/băng thông bộ nhớ và một số SKU có mạng tốc độ cao/RDMA. | Solver MPI, tính toán kỹ thuật, mô phỏng khoa học trên CPU. |
| **NC-series** | Các cấu hình GPU tính toán/tăng tốc tùy thế hệ. | GPU compute, một số bài toán AI training/inference hoặc HPC GPU. |
| **ND-series** | Các cấu hình GPU mạnh cho những workload AI quy mô lớn theo thế hệ. | Distributed training/model lớn khi đáp ứng GPU memory và interconnect. |
| **NV-series** | GPU cho đồ họa, rendering hoặc virtual desktop tùy thế hệ. | Visualization, remote workstation, ứng dụng đồ họa. |
| **D/E/F-series** | VM CPU đa dụng, tối ưu bộ nhớ hoặc CPU tương đối, tùy series. | Pre/post-processing, coordinator, batch task không cần GPU. |

**Không mặc định NC, ND hay NV đều có cùng GPU, VRAM, số GPU, NVLink hoặc RDMA.** Ngay trong cùng một nhóm, thế hệ VM có thể khác đáng kể. Cần xem thông số SKU **chính xác**: `Standard_...`, số GPU, dung lượng VRAM, vCPU, RAM, loại local storage và network capabilities.

### CPU HPC hay GPU HPC?

Chọn GPU khi:

- Thuật toán có thư viện/kernels hỗ trợ GPU phù hợp.
- Khối lượng phép toán song song đủ lớn so với chi phí truyền dữ liệu.
- VRAM chứa được data/model hoặc có giải pháp chia phù hợp.
- Đội ngũ có khả năng vận hành driver, runtime và profiling GPU.

Không nên chọn GPU chỉ vì tính toán “nặng”. Nếu solver được tối ưu cho CPU/MPI, phụ thuộc nhiều vào bộ nhớ hệ thống hoặc phần lớn runtime là I/O tuần tự, GPU VM đắt tiền có thể **không cải thiện thời gian hay chi phí**.

### Cân đối GPU, RAM và CPU

Một node GPU vẫn cần CPU để giải mã dữ liệu, chuẩn bị minibatch, điều khiển tác vụ, thực hiện network stack và ghi checkpoint. Nếu cấp GPU mạnh nhưng CPU/RAM quá thấp, GPU chờ dữ liệu và utilization giảm.

Ngược lại, nếu model không vừa VRAM:

- Giảm batch size hoặc precision theo yêu cầu độ chính xác.
- Chọn GPU có VRAM lớn hơn, nếu SKU phù hợp.
- Dùng gradient accumulation, activation checkpointing, model/tensor parallelism hoặc kỹ thuật phân tán được framework hỗ trợ.
- Xác minh chi phí đồng bộ và độ phức tạp thay vì mặc định “nhiều GPU là giải pháp”.

## 6. Bộ nhớ GPU và giao tiếp giữa các GPU

Cần phân biệt các lớp kết nối:

| Thành phần | Vai trò | Tác động |
|---|---|---|
| **GPU VRAM/HBM** | Bộ nhớ trực tiếp của GPU. | Model/tensor và batch có vừa bộ nhớ hay không. |
| **CPU RAM** | Bộ nhớ host, buffer dữ liệu, pre/post-processing. | Giữ pipeline đủ dữ liệu cung cấp GPU. |
| **PCIe** | Trao đổi CPU↔GPU hoặc thiết bị trong node. | Copy và I/O có thể tạo nút thắt. |
| **NVLink/NVSwitch** | Liên kết GPU–GPU tốc độ cao trên những cấu hình hỗ trợ. | Hữu ích với model parallelism/collectives nội node. |
| **Ethernet** | Kết nối mạng IP giữa các VM. | Phù hợp nhiều batch workloads hoặc cluster không cần liên kết rất thấp. |
| **InfiniBand/RDMA** | Truy cập bộ nhớ trực tiếp từ xa khi VM/network hỗ trợ. | Hữu ích cho MPI hoặc multi-node training cần đồng bộ nhanh. |

**NVLink trong node không thay thế InfiniBand giữa các node.** GPU VM có nhiều GPU trên một node chưa chắc có kết nối liên node tốc độ cao. Khi mua năng lực cho distributed training, phải kiểm tra cả **topology nội node** và **interconnect giữa node**.

### GPU memory không cộng đơn giản thành một vùng dùng chung

Một VM có 4 GPU, mỗi GPU 40 GiB VRAM, **không tự biến thành một GPU với 160 GiB VRAM**. Mỗi GPU thường có không gian bộ nhớ riêng; framework phải quản lý phân phối tensor/model hoặc truyền dữ liệu. Cách tính dung lượng hiệu quả phụ thuộc chiến lược song song và overhead.

Ví dụ mô hình cần 60 GiB trên **một thiết bị**:

- 1 GPU 40 GiB có thể không đủ.
- 2 GPU 40 GiB có thể dùng nếu framework hỗ trợ chia model/tensor hoặc offloading phù hợp.
- 1 GPU có VRAM đủ lớn có thể đơn giản hơn nếu được hỗ trợ và đáp ứng chi phí.

Với precision như FP32, FP16 hoặc BF16, việc giảm kích thước dữ liệu có thể tiết kiệm bộ nhớ và tăng throughput nhưng còn phụ thuộc hỗ trợ phần cứng, độ ổn định số học và yêu cầu kết quả. Không thay đổi precision của mô phỏng khoa học hay mô hình tài chính mà không kiểm thử sai số.

## 7. Thiết kế mạng HPC: Ethernet, Accelerated Networking và RDMA

**Accelerated Networking** trong Azure giúp giảm một phần overhead network virtualization và cải thiện throughput/latency trên các SKU được hỗ trợ. Nó **không đồng nghĩa** với việc VM có **RDMA** hoặc InfiniBand.

**RDMA (Remote Direct Memory Access)** cho phép những giao tiếp bộ nhớ từ xa với đường dữ liệu tối ưu hơn, có thể đặc biệt hữu ích cho các thuật toán liên lạc liên tục. Trong Azure, một số VM HPC/GPU có networking chuyên dụng và driver/runtime tương thích.

### Những điều phải kiểm tra với cluster MPI/GPU phân tán

1. **SKU cụ thể** có hỗ trợ RDMA/InfiniBand không?
2. Các node có ở **region, zone và topology** phù hợp theo hướng dẫn của SKU không?
3. Image/OS hỗ trợ driver network, kernel và MPI stack cần thiết không?
4. Công cụ scheduler có cấp các node theo topology phù hợp cho một job MPI không?
5. Dịch vụ đang dùng có hỗ trợ traffic cần thiết trong subnet/NSG không?
6. Đã đo network latency, bandwidth và MPI collective theo workload thật chưa?

Với cluster hiệu năng cao, sự phân bổ node về mặt vật lý có thể ảnh hưởng độ trễ. Các cơ chế như **proximity placement groups** hoặc placement/network topology được dịch vụ hỗ trợ có thể hữu ích, nhưng **không tự bảo đảm RDMA**, cũng không đảm bảo luôn còn capacity. Khả năng hỗ trợ thay đổi theo family/SKU và kiểu điều phối.

### VNet, NSG và private access

Một kiến trúc phổ biến:

```text
        Quản trị viên / CI pipeline
                  |
           Microsoft Entra ID
                  |
             Bastion / VPN
                  |
             VNet HPC
         +--------+---------+
         |                  |
    Head / scheduler     Compute subnet
       node             +------+------+
         |              |             |
     Job queue       CPU/GPU-01    CPU/GPU-N
         |              |             |
         +--------> Shared file system <----+
                         |
                Blob output/checkpoints
```

Nên ưu tiên private IP cho compute nodes, giới hạn ingress SSH/RDP từ mạng quản trị, và dùng managed identity/Entra RBAC để truy cập Storage theo quyền tối thiểu. Với mạng RDMA/InfiniBand, cần bảo đảm cấu hình phù hợp với các yêu cầu của nhà cung cấp và không chặn nhầm traffic nội cluster.

**Không cấp public IP cho mỗi GPU node chỉ để cài đặt phần mềm.** Có thể dùng image chuẩn, private endpoints, egress qua NAT/firewall hoặc phương án phân phối package được tổ chức phê duyệt.

## 8. Dữ liệu: tách nguồn, working set và kết quả

Một job HPC thường có nhiều loại dữ liệu:

- **Input lâu dài:** dataset, mesh, checkpoint gốc, model weights.
- **Scratch/working set:** dữ liệu tạm, intermediate tensors, file phân vùng, cache.
- **Output:** kết quả mô phỏng, mô hình đã huấn luyện, artifact và logs.
- **Metadata:** job ID, phiên bản code, tham số, người chạy, seed, image và provenance.

Không nên đặt mọi lớp lên cùng một ổ đĩa với cùng công nghệ lưu trữ.

| Dịch vụ / loại lưu trữ | Điểm mạnh | Ràng buộc cần xem |
|---|---|---|
| **Azure Blob Storage / ADLS Gen2** | Dữ liệu object quy mô lớn, lưu input/output/checkpoint, tích hợp quản lý vòng đời. | Tập tin qua object API, không tự là POSIX parallel file system cho mọi solver. |
| **Azure Managed Lustre** | Hệ thống file hiệu năng cao theo những region/SKU hỗ trợ, phù hợp nhiều bài toán HPC. | Cần cấu hình cluster file system, liên kết với Blob hoặc nơi chứa dữ liệu, quota và chi phí. |
| **Azure NetApp Files** | Dịch vụ file có hiệu năng cao theo mức dịch vụ và giao thức hỗ trợ. | Capacity pool, throughput/latency, giao thức, networking và phí. |
| **Azure Files** | File share SMB/NFS được quản lý theo loại share hỗ trợ. | Không mặc định đáp ứng metadata/IOPS của mọi workload HPC hàng nghìn node. |
| **Managed disks** | Dữ liệu đĩa gắn VM; các loại đĩa có đặc điểm hiệu năng khác nhau. | Cấu hình IOPS/throughput và giới hạn VM; không tự chia sẻ như parallel FS. |
| **Local NVMe/temporary disk** | Scratch/cache rất nhanh trên một số VM. | **Ephemeral**: không dùng làm bản sao duy nhất của kết quả hay checkpoint quan trọng. |

### Mô hình staging dữ liệu

```text
Azure Blob: data/raw, models, reference
          |
          | stage input / hydrate
          v
Shared HPC file system (nếu ứng dụng cần POSIX)
          |
          +--> Compute nodes / GPU nodes
          |       |
          |       +--> Local scratch / temporary checkpoints
          |
          v
      Validated outputs
          |
          | upload theo phiên bản job
          v
Azure Blob: results/<job-id>/, checkpoints/, logs/
```

Quy trình:

1. Tải dataset về vùng có throughput phù hợp trước khi đồng loạt khởi chạy jobs.
2. Phân chia file theo cách ứng dụng đọc, tránh hàng triệu tác vụ cùng truy cập một file metadata nhỏ.
3. Dùng local scratch cho dữ liệu tái tạo được hoặc cache.
4. Lưu checkpoint quan trọng vào nơi **bền vững**, theo chu kỳ hợp lý.
5. Sau job, đồng bộ output, kiểm tra checksum/cấu trúc và ghi provenance.
6. Chỉ dọn scratch sau khi xác nhận output đã lưu và còn khả năng khôi phục.

Tốc độ GPU cao **không cứu được** một workflow luôn chờ đọc dữ liệu từ Storage. Hãy đo IOPS, throughput, latency và số thao tác metadata bên cạnh GPU utilization.

## 9. Chọn công cụ điều phối: Azure Batch, CycleCloud hay dịch vụ khác?

Một HPC cluster cần hệ thống quyết định **job nào chạy, cần bao nhiêu node, khi nào mở rộng/thu hẹp và làm sao thu thập kết quả**.

| Giải pháp | Mô hình | Khi phù hợp |
|---|---|---|
| **Azure Batch** | Quản lý pool compute, jobs và tasks theo cơ chế của dịch vụ; hỗ trợ autoscale và các kịch bản multi-instance task được cấu hình đúng. | Nhiều batch tasks, render, mô phỏng độc lập, batch workload cần Azure-managed orchestration. |
| **Azure CycleCloud + Slurm** | Quản lý vòng đời cluster HPC; Slurm lập lịch jobs/partitions/nodes. | Trung tâm HPC có phần mềm MPI, job queue quen thuộc, cluster CPU/GPU phức tạp. |
| **Azure Machine Learning** | Jobs/pipelines, distributed training và quản lý ML lifecycle theo cấu hình được hỗ trợ. | Workload AI/ML cần tracking, datasets, environment, model registry. |
| **Azure Kubernetes Service** | Orchestration container có thể dùng GPU node pools và scheduler/integration phù hợp. | Workload containerized, inference/service và một số batch/distributed patterns. |
| **VM tự quản lý** | Tự triển khai scheduler, images, scripts, queue và scale. | Trường hợp đặc thù; phải tự gánh chi phí và độ phức tạp vận hành. |

Không nên đánh đồng **VM Scale Sets** với scheduler HPC: VMSS hỗ trợ quản lý nhóm VM, nhưng không mặc nhiên cung cấp queue, job dependency, MPI topology và retry theo semantics của ứng dụng.

### Azure Batch: nhiều tác vụ tương đối độc lập

Ý tưởng:

```text
Job: monthly-risk-simulation
      |
      +--> Task 0001 -> compute node
      +--> Task 0002 -> compute node
      +--> Task 0003 -> compute node
      ...
      +--> Task 20000 -> compute node
      |
      +--> collect results -> Blob Storage
```

Trong Azure Batch, **pool** chứa compute nodes; **job** tổ chức các tasks; **task** thực thi lệnh hoặc chương trình. Cấu hình bao gồm VM image, size, quota, node count/autoscale, quyền Storage, startup tasks và các phụ thuộc khác.

Một số workloads MPI có thể sử dụng khả năng **multi-instance tasks** của Batch trong những cấu hình được hỗ trợ; không giả định mọi application MPI/RDMA chạy được mà không kiểm tra networking, image, và cơ chế bố trí tiến trình.

### Azure CycleCloud và Slurm: cluster kiểu HPC truyền thống

CycleCloud giúp triển khai/quản lý cluster theo template và các thành phần cần thiết; Slurm xử lý **job queue, resource requests, partition, node allocation và job states**.

Ví dụ lệnh submit một script Slurm trên một cluster **đã được cấu hình**:

```bash
sbatch --nodes=4 --time=02:00:00 run-solver.sh
squeue --me
sacct -j <JOB_ID>
```

Lệnh trên chỉ là minh họa để giải thích giao diện scheduler. Cú pháp, partition, GPU resource directive và tài khoản Slurm có thể khác; đặt tài nguyên cụ thể trong script theo cluster thực tế. Không chạy submit trên cluster Production khi chưa được phê duyệt hoặc định mức chi phí.

### Khi nào không cần scheduler phức tạp?

Nếu chỉ có một job GPU nhỏ chạy mỗi tuần trên một VM, việc dựng cluster Slurm cố định có thể tốn công và phí không cần thiết. Một batch job được lập lịch, một managed ML job hoặc VM có tự động khởi tạo và tắt sau khi hoàn thành có thể đơn giản hơn.

## 10. Thiết kế node và hàng đợi HPC

Một cluster chuyên nghiệp thường tách:

- **Login/management node:** nơi kỹ sư chuẩn bị lệnh; không chạy job tính toán nặng thường xuyên.
- **Scheduler/head node:** quản lý queue, policies và phân bổ node.
- **CPU compute nodes:** xử lý pre/post-processing hoặc solver CPU.
- **GPU compute nodes:** thực thi training/render/GPU kernels.
- **Shared file system:** dữ liệu dùng chung với throughput phù hợp.
- **Control plane/monitoring:** logs, metrics, cảnh báo, billing, automation.

### Partitions và chính sách queue

Ví dụ phân vùng logic:

| Partition / queue | Tài nguyên | Chính sách minh họa |
|---|---|---|
| `cpu-short` | CPU VM | Jobs ngắn, thời gian tối đa thấp. |
| `cpu-mpi` | HPC CPU nodes, interconnect tương thích | Multi-node MPI. |
| `gpu-single` | GPU nodes | 1 node, giới hạn GPU và VRAM theo nhu cầu. |
| `gpu-distributed` | GPU nodes có network phù hợp | Multi-node distributed training. |
| `spot-batch` | Spot VM khi hỗ trợ | Chỉ jobs idempotent/có checkpoint. |

Các partition là **quy hoạch scheduler**, không nhất thiết là tên được Azure tạo sẵn. Cần phân quyền queue, giới hạn tài nguyên mỗi nhóm và áp dụng fair-share/priorities nếu nhiều đội cùng dùng cluster.

### Autoscale và scale-to-zero

Quy trình lý tưởng cho batch:

1. Có job trong queue → scheduler/Batch tăng node phù hợp.
2. VM khởi động và chạy startup/driver/bootstrap.
3. Scheduler chờ node ready và cấp phát cho job.
4. Job chạy, ghi log và checkpoint.
5. Job hoàn thành → lưu output vào bền vững.
6. Node idle quá ngưỡng → giải phóng để tránh tính phí compute không cần thiết.

**Scale-to-zero của compute nodes không có nghĩa toàn bộ cluster miễn phí lúc rảnh.** Head node, storage, gateway, vault, network và log platform vẫn có thể phát sinh chi phí. Một số scheduler/template có thể cần cấu hình riêng để scale compute nodes xuống 0 mà không ảnh hưởng dịch vụ điều phối.

## 11. Chuẩn bị GPU VM: image, driver, runtime và framework

GPU VM được cấp phát **không đồng nghĩa** driver và ứng dụng đã sẵn sàng. Phải kiểm tra:

| Lớp | Thành phần | Kiểm tra |
|---|---|---|
| Hạ tầng | SKU GPU chính xác, region/zone, quota | VM được tạo trên phần cứng phù hợp. |
| OS / image | Ubuntu/RHEL/Windows hoặc image HPC/AI hỗ trợ | Kernel, firmware, patch và support matrix. |
| Driver GPU | NVIDIA hoặc AMD driver theo model GPU | Driver nhận thiết bị và không có lỗi. |
| Compute runtime | CUDA/cuDNN hoặc ROCm theo phần cứng và ứng dụng | Phiên bản tương thích với driver và framework. |
| Thư viện phân tán | MPI, UCX, NCCL hoặc runtime tương ứng | Bản build phù hợp network và driver, có test liên node. |
| Ứng dụng | Solver, PyTorch/TensorFlow hoặc phần mềm ISV | Phiên bản, license, precision, kiểm thử dữ liệu. |
| Container | Image + GPU container runtime/toolkit nếu sử dụng | GPU device và driver host truy cập đúng cách. |

**CUDA là nền tảng của NVIDIA**, không phải mọi GPU đều sử dụng CUDA. Nếu VM dùng GPU AMD, cần kiểm tra stack phần mềm/ROCm được hỗ trợ; nếu ứng dụng chỉ có CUDA kernels, đổi sang GPU khác hãng có thể không thực thi được.

### Kiểm tra GPU trên Linux

Sau khi kết nối bằng kênh quản trị an toàn và bảo đảm driver NVIDIA đã được cài:

```bash
nvidia-smi
```

Xem thêm những thông số tiện cho benchmark:

```bash
nvidia-smi \
  --query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu \
  --format=csv
```

Lệnh `nvidia-smi` không có hoặc không tìm thấy GPU có thể do VM không sử dụng NVIDIA GPU, driver chưa cài/không tương thích, OS/image chưa đúng hoặc phần cứng không được expose theo cấu hình. Trước khi cài lại driver, hãy xác minh **SKU**, GPU vendor, image và hướng dẫn driver phù hợp.

Công cụ `nvcc --version` có thể giúp kiểm tra CUDA compiler khi toolkit có sẵn; việc không có `nvcc` **không tự chứng minh** CUDA runtime/driver không hoạt động, vì nhiều container/runtime không chứa compiler.

### Kiểm tra topology GPU

Với NVIDIA và driver hỗ trợ:

```bash
nvidia-smi topo -m
```

Kết quả hỗ trợ quan sát liên kết giữa GPU, CPU và các thiết bị có liên quan. Cần đối chiếu tài liệu SKU nếu ứng dụng dựa vào NVLink/NVSwitch; không suy luận từ tên series.

### Quản lý image

Với cluster sản xuất:

1. Chốt một **golden image** hoặc container image có version.
2. Ghi driver, CUDA/ROCm, MPI/NCCL, package, checksum và OS version.
3. Thử một job chuẩn trên 1 node, sau đó nhiều node.
4. Chỉ nâng cấp image theo đợt, tránh trộn các node khác phiên bản trong một job cần tương thích.
5. Cất cấu hình trong IaC/version control, **không** đưa khóa truy cập Storage hay secret vào image.

Nếu job MPI/GPU báo lỗi sau nâng cấp driver, có thể phải kiểm tra đồng bộ phiên bản kernel, userspace libraries, driver/firmware và container runtime trước khi kết luận mã ứng dụng sai.

## 12. Quota, capacity và lựa chọn region/zone

Đây là điểm dễ gây thất bại khi triển khai GPU/HPC trên Azure.

**Quota** là giới hạn số tài nguyên (chẳng hạn vCPU của family trong một region) được subscription cho phép yêu cầu. **Capacity** là mức phần cứng Azure thực tế có thể cấp phát theo SKU và vị trí lúc triển khai.

Một subscription có **quota đủ** vẫn có thể gặp lỗi **insufficient capacity** cho SKU cụ thể tại thời điểm đó. Ngược lại, region có GPU sẵn không giúp được nếu quota family của subscription bằng 0.

| Yếu tố | Cần kiểm tra |
|---|---|
| **SKU availability** | SKU được hỗ trợ ở region/zone dự kiến và trong subscription? |
| **Regional vCPU quota** | Tổng quota region còn đủ không? |
| **VM-family quota** | Hạn mức family GPU/HPC cần dùng còn đủ không? |
| **Availability Zone** | Có cấu hình zone cụ thể không; SKU có hỗ trợ không? |
| **Physical capacity** | Có đủ node theo kích thước và thời điểm cần dùng không? |
| **Placement/network constraints** | RDMA/InfiniBand, zone, placement group và loại network có hạn chế bổ sung? |
| **Commercial options** | On-demand, reservation, capacity reservation hoặc Spot có phù hợp? |

**Reserved Instance** thường là cơ chế tối ưu chi phí theo cam kết sử dụng, **không tự bảo đảm** có capacity vật lý khi tạo VM. Nếu workload có deadline chặt, đánh giá **on-demand capacity reservation** trong phạm vi family/SKU được hỗ trợ hoặc phương án đảm bảo năng lực được Azure cung cấp. Không giả định mọi GPU/HPC SKU có thể đặt trước capacity bằng cùng một cơ chế.

### Kiểm tra ban đầu qua Azure CLI

Lệnh sau là **chỉ đọc**, minh họa với region `eastus`; thay region trước khi kết luận:

```bash
az account show \
  --query "{Subscription:id,Name:name,Tenant:tenantId}" \
  --output table

az vm list-skus \
  --location eastus \
  --resource-type virtualMachines \
  --size Standard_NC \
  --output table
```

Dùng lệnh tiếp theo để xem quota/usage khi API hỗ trợ:

```bash
az vm list-usage \
  --location eastus \
  --output table
```

`list-skus` giúp kiểm tra những SKU được báo hỗ trợ và các hạn chế được API trả về; `list-usage` giúp kiểm tra hạn mức. **Không lệnh nào bảo đảm instance sẽ cấp phát thành công tại thời điểm job bắt đầu**.

Nếu cần quota bổ sung, thực hiện quy trình yêu cầu tăng quota qua Azure Portal hoặc kênh hỗ trợ phù hợp. Với GPU hiếm, xin quota không nên là bước cuối cùng sau khi đã chốt deadline triển khai.

## 13. On-demand, Spot và phương án xử lý gián đoạn

| Lựa chọn | Lợi thế | Rủi ro / điều kiện |
|---|---|---|
| **On-demand VM** | Mô hình linh hoạt, không cần cam kết dài hạn. | Giá theo thời gian sử dụng; vẫn có rủi ro capacity. |
| **Azure Spot VM** | Có thể có mức giá thấp hơn khi có capacity nhàn rỗi. | Có thể bị **evict**, không bảo đảm sẵn sàng hay thời gian chạy. |
| **Reservation / savings mechanism** | Có thể giảm chi phí khi mức sử dụng ổn định. | Điều kiện SKU/phạm vi và cam kết, không đồng nghĩa bảo đảm capacity. |
| **Capacity reservation (nếu hỗ trợ)** | Có thể phù hợp workload bắt buộc có năng lực sẵn ở thời điểm xác định. | Phạm vi SKU, region, zone, mức phí và yêu cầu vận hành riêng. |

### Khi nào dùng Spot?

Dùng Spot khi job:

- Có thể **retry** hoặc **resume từ checkpoint**.
- Không có deadline tuyệt đối hoặc có buffer xử lý.
- Có dữ liệu đầu vào ở storage bền vững, output được ghi định kỳ.
- Không giữ state duy nhất trên local NVMe/temporary disk.
- Scheduler có logic thay thế node bị evict.

Tránh đặt **node điều phối duy nhất**, metadata thiết yếu hoặc job MPI dài nhiều giờ **không có checkpoint** trên Spot mà không có phương án xử lý gián đoạn. Với job MPI chặt chẽ, mất một node có thể làm toàn bộ job thất bại.

### Checkpoint như một phần của thiết kế

Ví dụ job train 12 giờ, cứ mỗi 30 phút ghi checkpoint ra storage bền vững:

```text
Start ── 30m ── checkpoint 01 ── 30m ── checkpoint 02 ── ...
                                        |
                                  Spot eviction
                                        |
                          Requeue job với checkpoint 02
                                        |
                                     Resume
```

Checkpoint cần chứa **model weights/optimizer state, tiến độ xử lý, seed, cấu hình dữ liệu và metadata cần thiết**. Một file weight đơn lẻ có thể không đủ để resume đúng một tiến trình training.

Với HPC mô phỏng khoa học, checkpoint phải phù hợp trạng thái solver và khả năng restart; không coi việc copy một thư mục file đang ghi dở là checkpoint nhất quán.

## 14. Bảo mật dữ liệu và truy cập trong cluster HPC

Do HPC thường xử lý dữ liệu nghiên cứu, dữ liệu khách hàng hoặc mô hình có giá trị, phải kiểm soát cả **cluster** lẫn **pipeline dữ liệu**.

### Phân quyền

- Dùng **Microsoft Entra ID** và **Azure RBAC** để quản lý tài nguyên Azure theo phạm vi tối thiểu.
- Dùng managed identity cho node/ứng dụng có nhu cầu truy cập Storage hoặc Key Vault theo quyền được cấp.
- Với Slurm, thiết lập account/user/group và queue permissions riêng; quyền trong scheduler **không tự đồng nhất** với Azure RBAC.
- Nếu dùng shared filesystem, kiểm tra quyền POSIX/SMB/NFS theo giao thức, không dựa vào việc file “ở trong VNet”.
- Tách người có quyền tạo hàng trăm GPU nodes với người chỉ có quyền submit jobs.

### Mạng và bí mật

- Compute nodes dùng **private IP**; đường quản trị qua Bastion/VPN hoặc kênh được phê duyệt.
- Dùng private endpoints/DNS khi phù hợp để truy cập Storage/Key Vault qua private network.
- NSG/firewall giới hạn traffic quản trị, quản lý và dữ liệu; không chặn nhầm interconnect HPC.
- Secrets/certificates phải nằm trong vault hoặc cơ chế an toàn; không nhúng vào startup script, image hay job output.
- Kiểm soát outbound để giảm nguy cơ rò rỉ dữ liệu; cần đồng thời cho phép các endpoint hệ thống/driver/package được thiết kế.
- Bật encryption at rest và TLS trong phạm vi hỗ trợ, không chia sẻ credential Storage trong command line/log.

### Quản trị nguồn gốc kết quả

Lưu theo mỗi job:

```text
job_id
input_dataset_version
code_git_commit
container_or_vm_image_version
driver_and_runtime_version
vm_sku_and_gpu_count
scheduler_parameters
start_and_end_timestamp
output_location
validation_metrics
owner_and_cost_center
```

Metadata này giúp tái lập kết quả, điều tra chênh lệch sau nâng cấp image và phân bổ chi phí theo phòng ban.

## 15. Chi phí HPC/GPU: đo theo job hoàn thành

**Giá VM/giờ thấp nhất chưa chắc cho chi phí mỗi kết quả thấp nhất.** VM nhanh hơn có thể rút ngắn thời gian chạy đủ lớn để tiết kiệm tổng chi phí.

Công thức đơn giản:

```text
Compute cost = số VM × số giờ chạy VM × giá/VM-giờ
Total cost   = compute + storage + data transfer + networking
               + scheduler/head nodes + logging + license + phí khác

GPU-hours    = số VM × số GPU/VM × giờ chạy
Cost/job     = tổng chi phí gắn với job / số job hoàn thành hợp lệ
```

### Ví dụ minh họa, không phải báo giá Azure

Một job distributed training dùng:

- **4 GPU VM**, mỗi VM có **2 GPU**.
- Job chạy **6 giờ**.
- Giả sử giá minh họa **5 USD/VM-giờ**.

```text
Compute cost = 4 × 6 × 5 = 120 USD
GPU-hours    = 4 × 2 × 6 = 48 GPU-giờ
Compute cost / GPU-hour = 120 / 48 = 2,50 USD
```

Con số 5 USD/VM-giờ **hoàn toàn giả định** để luyện phép tính; không suy ra SKU Azure nào có giá đó. Tổng tiền thực tế còn bao gồm lưu trữ, log, dữ liệu truyền, node điều phối và thời gian VM chạy chờ khởi động hoặc chờ queue.

### So sánh hai SKU theo thời gian hoàn thành

Giả sử cùng một job có hai phương án:

| Phương án | Giá giả định | Thời gian đo được | Compute cost |
|---|---:|---:|---:|
| VM A | 4 USD/giờ | 10 giờ | 40 USD |
| VM B | 7 USD/giờ | 5 giờ | 35 USD |

B nhanh hơn và rẻ hơn trên một job, dù giá/giờ cao hơn. Điều kiện là kết quả có **cùng độ chính xác**, cùng dữ liệu và workload thực sự đạt được thời gian đo nêu trên.

Đối với batch jobs, cần đo **jobs/giờ** và **USD/1.000 jobs**; với AI inference, đo **latency, requests/s, cost/1.000 requests**; với mô phỏng, đo **time-to-solution** và sai số khoa học.

### Phí ẩn cần tránh

- GPU nodes idle vì scheduler hoặc storage.
- Head node chạy 24/7 dù compute jobs chỉ chạy vài giờ/tuần.
- Spot eviction khiến một job phải chạy lại từ đầu.
- Storage tier quá đắt cho dữ liệu ít truy cập, snapshot/checkpoint retention dài.
- Chuyển dữ liệu qua region hoặc egress ngoài Azure.
- Dữ liệu lớn copy lại giữa nodes do thiếu shared caching.
- License phần mềm solver/visualization tính theo node hoặc số core.
- Thêm GPU nhưng không tăng throughput vì bottleneck network/CPU/I/O.

## 16. Benchmark và lựa chọn cấu hình bằng dữ liệu

Trước khi mở rộng cluster, thực hiện **benchmark có kiểm soát**.

### Bộ đo tối thiểu

| Thành phần | Metric |
|---|---|
| CPU | CPU utilization, cycles, memory bandwidth, RAM peak |
| GPU | GPU utilization, VRAM usage, power/temperature, kernel time |
| I/O | Read/write throughput, IOPS, p95 latency, metadata ops |
| Network | Bandwidth, latency, retransmissions, MPI collectives |
| Scheduler | Queue wait, node startup time, allocated/used time |
| Application | Time-to-solution, samples/s, steps/s, accuracy/convergence |
| Cost | Compute spend, GPU-hours, cost/job, idle ratio |

### Ba vòng thử nghiệm

**Vòng 1 – baseline:** chạy job nhỏ trên 1 CPU hoặc GPU node; đo thời gian, RAM/VRAM, I/O và kết quả.

**Vòng 2 – scale-up:** tăng số CPU/GPU trong cùng node nếu SKU/framework hỗ trợ; kiểm tra hiệu suất và communication nội node.

**Vòng 3 – scale-out:** tăng số node, giữ kích thước bài toán hoặc quy mô tăng theo kế hoạch; đo MPI/NCCL overhead, throughput, chi phí và độ ổn định.

Đừng so sánh hai SKU nếu khác phiên bản model, compiler flags, batch size, precision hoặc dataset; như vậy benchmark không còn công bằng.

### Hiểu GPU utilization thấp

Ví dụ GPU utilization chỉ 20% có thể do:

- Dataloader/CPU giải mã dữ liệu quá chậm.
- Dữ liệu được đọc từ filesystem có latency cao.
- Batch size quá nhỏ để tận dụng GPU.
- Kernel chưa tối ưu hoặc pipeline có nhiều thao tác CPU.
- GPU chờ collective communication của node khác.
- Mỗi job không tận dụng hết GPU được cấp, dẫn tới oversizing.

Cần profile chính xác thay vì tự động thêm GPU hoặc đổi SKU.

## 17. Vận hành và giám sát cluster

Azure Monitor có thể hỗ trợ thu thập metrics/logs của VM và thành phần hạ tầng. **Các metric GPU chi tiết thường cần công cụ trong guest, agent, exporter hoặc tích hợp được cấu hình**; không nên giả định mọi GPU VM tự hiển thị đầy đủ VRAM, nhiệt độ và utilization trên trang metrics mặc định.

Tổ chức theo ba lớp:

1. **Infrastructure:** VM state, CPU, memory (khi agent hỗ trợ), network, disk, GPU status, quota và capacity failures.
2. **Scheduler:** queue wait, failed jobs, node readiness, scale actions, idle GPU count và eviction events.
3. **Application:** training loss/convergence, solver errors, checkpoint age, outputs validated, business SLA.

### Cảnh báo đề xuất

- GPU node chạy hơn một ngưỡng thời gian nhưng utilization gần 0 và không có job hữu ích.
- Job failed/retried quá nhiều hoặc Spot eviction vượt mức kế hoạch.
- VRAM gần đầy, CUDA out-of-memory hoặc GPU hardware error được ghi log.
- Dataloader/storage throughput suy giảm gây tăng runtime.
- Checkpoint cuối cùng quá cũ so với chính sách khôi phục.
- Queue wait vượt deadline và quota/capacity sắp thiếu.
- Compute spend/ngân sách theo dự án vượt ngưỡng.
- Node hết phiên bản image/driver được phê duyệt.

### Quy trình kết thúc job

1. Kiểm tra exit code/scheduler state.
2. Đánh giá tính đúng đắn hoặc metric hội tụ, không chỉ kiểm tra “process ended”.
3. Xác minh output/checkpoint có trên storage bền vững và có checksum/version.
4. Ghi lại cost, runtime, SKU, node count và GPU-hours.
5. Dọn local scratch/temporary files theo chính sách.
6. Giải phóng nodes không cần thiết; xác minh autoscaling hoạt động.
7. Ghi lỗi, benchmark hoặc cải tiến cho lần chạy sau.

## 18. Quy trình triển khai tham khảo trên Azure

Ví dụ dự án cần chạy **hàng nghìn mô phỏng độc lập** và **một số jobs GPU**. Không cần tạo cluster lớn ngay từ đầu.

### Giai đoạn A – Thiết kế

1. Thu thập input size, tính chất song song, CPU/GPU profile, deadline và phân loại dữ liệu.
2. Chọn Batch nếu chủ yếu là tác vụ độc lập; cân nhắc CycleCloud/Slurm nếu MPI và queue HPC chuyên dụng.
3. Chọn region/SKU có quota và khả năng đáp ứng hạ tầng dự kiến.
4. Quy hoạch VNet/subnets, private access, Storage, shared file system và DNS.
5. Lập ngân sách, tags `project`, `owner`, `environment`, `costCenter` và policy cleanup.

### Giai đoạn B – Chuẩn bị node

1. Tạo compute pool/cluster nhỏ theo workflow được cấp phép.
2. Chọn image OS đã được hỗ trợ, cài đúng GPU driver/runtime hoặc dùng image được chuẩn hóa.
3. Kết nối Storage bằng identity được cấp quyền tối thiểu.
4. Kiểm tra GPU bằng `nvidia-smi` nếu dùng NVIDIA; kiểm tra MPI/RDMA nếu dự định multi-node.
5. Dùng input nhỏ để thử từ đầu tới cuối.

### Giai đoạn C – Thử nghiệm và scale

1. Chạy baseline có metric.
2. Thử tăng node và so sánh efficiency/cost/job.
3. Thiết lập scheduler policy, job retry và checkpoint.
4. Kiểm tra kết quả đúng, không bị mất dữ liệu khi một node bị thay thế.
5. Mở rộng theo quota/capacity đã được phê duyệt.

### Giai đoạn D – Vận hành

1. Tạo dashboard queue, GPU, storage và cost.
2. Đặt alerts cho failed jobs và idle GPU.
3. Lập runbook khôi phục từ checkpoint.
4. Định kỳ xem xét hiệu suất theo SKU/driver.
5. Giảm tài nguyên sau giờ chạy và xác minh chi phí thực tế.

**Chỉ chạy lệnh tạo GPU VM/cluster trong subscription được cho phép**, vì GPU VM và filesystem hiệu năng cao có thể phát sinh chi phí lớn. Những lệnh CLI trong bài ưu tiên kiểm tra ở chế độ chỉ đọc.

## 19. Sơ đồ kiến trúc tham khảo cho HPC kết hợp GPU

```text
                Nhà phát triển / nhà nghiên cứu
                       |
                Microsoft Entra ID
                       |
                VPN / Azure Bastion
                       |
               +-------------------+
               | HPC head / queue  |
               | Slurm hoặc Batch  |
               +---------+---------+
                         |
                   Job scheduling
                 /               \
                v                 v
       +----------------+   +------------------+
       | CPU compute     |   | GPU compute       |
       | solver / prep   |   | training / accel  |
       | scale on demand |   | scale on demand   |
       +--------+--------+   +---------+--------+
                |                      |
                +---------+------------+
                          |
                Shared HPC file system
                  (nếu workload cần)
                          |
                stage data / checkpoints
                          |
                  Azure Blob Storage
                 inputs / outputs / logs

     Azure Monitor + budget + alerts + job metadata
```

Đây là sơ đồ logic; trong Azure Batch, scheduler và compute pool được cung cấp theo mô hình managed của dịch vụ, không nhất thiết có “head VM” do bạn tạo. Với CycleCloud/Slurm, node điều phối được thiết kế và vận hành theo template/cluster đã triển khai.

## 20. Tình huống thực tế A: mô phỏng CFD cần MPI

**Yêu cầu:** mô phỏng dòng khí có một bài toán lớn, chia trên 32 tiến trình và trao đổi dữ liệu biên liên tục. Phần mềm solver hỗ trợ MPI trên CPU; chưa xác minh bản GPU.

**Sai lầm dễ gặp:** chọn ngay GPU ND-series chỉ vì tên “HPC”, rồi tạo 32 tác vụ Batch độc lập. Nhưng ở đây 32 tiến trình **cùng giải một bài toán**, cần giao tiếp MPI và dữ liệu chung.

**Thiết kế hợp lý hơn:**

1. Benchmark solver CPU trên một node.
2. Chọn họ VM HPC CPU phù hợp, kiểm tra RDMA nếu đặc tính giao tiếp cho thấy cần.
3. Dùng CycleCloud/Slurm hoặc cơ chế cluster phù hợp để cấp các node trong cùng job.
4. Chuẩn bị MPI stack, shared file system và mesh data.
5. Chạy thử với 1, 2, 4, 8 nodes; đo time-to-solution, MPI efficiency, RAM và I/O.
6. Chọn quy mô đạt deadline với chi phí hợp lý; không mở rộng vô hạn khi efficiency giảm.
7. Lưu checkpoint, output và metadata ở storage bền vững.
8. Định kỳ kiểm thử sai số nghiệm số khi thay compiler/MPI/library.

**Tiêu chí thành công:** đúng kết quả khoa học, runtime đạt mục tiêu, sử dụng tốt CPU/RDMA và có thể restart khi một node gặp lỗi.

## 21. Tình huống thực tế B: huấn luyện GPU phân tán

**Yêu cầu:** mô hình AI quá lớn để huấn luyện nhanh trên một GPU; có nhiều dữ liệu trong Blob Storage, cần chạy thí nghiệm theo tuần.

**Thiết kế tham khảo:**

1. Ước lượng memory model/optimizer/activations và VRAM cần thiết.
2. Thử 1 GPU rồi nhiều GPU trong một node để đo scaling.
3. Nếu cần nhiều node, chọn GPU VM có interconnect phù hợp và framework hỗ trợ distributed training.
4. Dùng Slurm, Azure Machine Learning hoặc workflow khác đáp ứng quản lý distributed jobs.
5. Cài image/driver/CUDA/framework version tương thích; kiểm tra NCCL communication.
6. Đưa dữ liệu gần node, thiết kế dataloader prefetch/caching.
7. Ghi checkpoint định kỳ vào bền vững, chứa đủ trạng thái để resume.
8. Đo GPU utilization, throughput (samples/s), convergence, network time và cost/training run.
9. Dùng Spot chỉ khi có logic gián đoạn và deadline chấp nhận được.
10. Lưu model artifacts và metadata có kiểm soát quyền.

Nếu gặp lỗi `CUDA out of memory`, không nên ngay lập tức tăng số node. Trước hết kiểm tra batch size, model placement, precision, fragmentation và VRAM từng GPU. Thêm node chỉ giúp khi phần mềm hỗ trợ phân tán tài nguyên đúng cách.

## 22. Bảng chẩn đoán lỗi HPC/GPU thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không tạo được GPU VM: quota exceeded | Hết quota family hoặc quota regional vCPU | Kiểm tra usage/quota, xin quota hoặc đổi phương án. |
| Có quota nhưng deployment vẫn fail | Không còn capacity phù hợp SKU/zone/placement | Thử region/SKU/zone khác theo kế hoạch, xét capacity reservation nếu hỗ trợ. |
| `nvidia-smi` không hoạt động | Driver sai/missing, VM không có NVIDIA GPU, image/kernel không tương thích | Kiểm tra SKU và vendor, driver support matrix, log kernel. |
| CUDA runtime mismatch | CUDA toolkit/framework, driver hoặc container version không tương thích | Chốt lại image và version tương thích, kiểm thử trên node nhỏ. |
| GPU utilization thấp | CPU/dataloader, storage bottleneck, batch nhỏ, kernel không hiệu quả | Profile end-to-end, tăng prefetch và tối ưu dữ liệu. |
| `CUDA out of memory` | Model/batch/activations vượt VRAM GPU đang dùng | Điều chỉnh batch, precision, checkpointing hoặc phân tán phù hợp. |
| MPI/NCCL treo | Mismatch versions, mạng/driver, topology hoặc firewall, tiến trình không đồng bộ | Kiểm tra logs, interconnect, rank allocation và small collective test. |
| Job GPU chậm hơn CPU | Code không được tăng tốc, copy overhead, cấu hình không phù hợp | Benchmark lại thuật toán và đo time-to-solution. |
| Jobs liên tục retry | Script không idempotent, thiếu dependency, Spot eviction, lỗi node | Xem scheduler logs, checkpoint và retry policy. |
| Output mất sau khi VM bị giải phóng | Chỉ ghi trên temporary/local scratch | Đưa output/checkpoint lên storage bền vững trước cleanup. |
| Storage throughput thấp | Quá nhiều file nhỏ, shared FS không đủ capacity, data staging kém | Dùng cache/parallel FS phù hợp, đo IOPS và metadata operations. |
| Chi phí vượt dự toán | Idle GPUs, cluster không scale down, copy dữ liệu liên vùng | Phân tích tags, VM-hours, storage và log; tối ưu queue/retention. |

### Phương pháp điều tra nhanh

1. **Định danh job:** job ID, scheduler state, thời gian bắt đầu, image version và SKU.
2. **Kiểm tra tài nguyên:** VM state, quota, GPU visible, VRAM, CPU/RAM.
3. **Kiểm tra dữ liệu:** input có sẵn, mount/file permissions và throughput.
4. **Kiểm tra phân tán:** số ranks, nodes, network và thư viện MPI/NCCL.
5. **Kiểm tra ứng dụng:** stack trace, exit code, convergence và kết quả một job mẫu.
6. **Kiểm tra chi phí:** node time và số lần retry, Spot events.
7. **Khôi phục:** chọn checkpoint cuối cùng hợp lệ, sửa nguyên nhân rồi requeue.
8. **Đóng sự cố:** xác nhận output đúng, node đã giải phóng và bài học được ghi lại.

## 23. Bài thực hành: thiết kế phương án HPC/GPU có kiểm soát

**Bối cảnh:** Nhóm nghiên cứu có hai loại công việc trong cùng dự án:

- **Nhóm A:** 10.000 mô phỏng độc lập, mỗi job dùng 4 vCPU, chạy khoảng 20 phút trên một cấu hình CPU giả định.
- **Nhóm B:** huấn luyện một mô hình AI, cần 4 GPU chạy liên tục trong khoảng 8 giờ và phải có checkpoint tối đa mỗi 60 phút.
- Input chung là 4 TB trong Blob Storage; output dự kiến 800 GB.
- Nhóm chỉ chạy hai đợt lớn mỗi tháng và muốn giảm compute idle.
- Dữ liệu không được đưa lên VM public; phải dùng identity và mạng riêng.
- Yêu cầu so sánh cost/job, phục hồi sau lỗi và xác minh quota.

### Nhiệm vụ

1. Nhóm A phù hợp với Batch task pool hay cluster MPI chặt? Vì sao?
2. Nhóm B nên thử single-node multi-GPU trước hay triển khai ngay multi-node? Vì sao?
3. Chọn **tiêu chí SKU** cho CPU nodes và GPU nodes, không chỉ nêu tên family.
4. Thiết kế pipeline Blob → staging → compute → Blob output.
5. Nêu biện pháp xử lý data locality và tránh 10.000 tasks cùng tải dữ liệu lớn.
6. Lập chính sách scheduler để scale lên theo queue và giải phóng compute sau job.
7. Thiết kế checkpoint, retry và cách dùng Spot có trách nhiệm.
8. Chọn 5 metric đánh giá hiệu năng và 5 metric/nguồn cho giám sát vận hành.
9. Lập công thức dự toán VM-hours/GPU-hours và các khoản chi phí còn lại.
10. Chỉ ra 3 rủi ro bảo mật và biện pháp giảm thiểu.

### Gợi ý lời giải

**Nhóm A:** vì các mô phỏng độc lập, Azure Batch hoặc scheduler batch tương đương phù hợp. Nếu dùng 100 task slots song song và giả định mỗi slot xử lý 1 job mỗi 20 phút, **thời gian tính toán lý tưởng** là:

```text
10.000 jobs / 100 jobs đồng thời = 100 lượt
100 lượt × 20 phút = 2.000 phút ≈ 33 giờ 20 phút
```

Đây chưa tính thời gian cấp phát node, lấy dữ liệu, lưu output, retries và sự không đều của runtime. “100 task slots” là đơn vị logic; số VM cần thiết tùy mỗi VM có bao nhiêu vCPU và cấu hình tasks/node. Với job 4 vCPU, 100 jobs chạy đồng thời cần ngân sách tài nguyên tương ứng và tránh oversubscription gây chậm.

**Nhóm B:** xác minh 4 GPU cần ở **cùng một node** hay nhiều node tùy VRAM, liên kết GPU và framework. Nếu đủ bộ nhớ và GPU trên một node, thử single-node multi-GPU giúp giảm overhead liên node. Nếu bắt buộc phân tán, chọn network và scheduler thích hợp. Checkpoint ít nhất theo chu kỳ 60 phút hoặc ngắn hơn theo yêu cầu RPO của training.

**Lưu trữ:** Blob giữ dữ liệu gốc và output; stage dữ liệu đến file system hoặc cache đủ throughput trước khi phân phối jobs; không dùng local scratch làm bản duy nhất. Với data 4 TB, chi phí truyền/đọc và warmup có thể đáng kể.

**Co giãn:** tạo nodes khi queue có job, định cấu hình idle timeout, thu hồi nodes sau khi output đã xác minh. Với hai đợt/tháng, giữ GPU nodes luôn bật có thể lãng phí lớn.

**Bảo mật:** private subnet, RBAC/managed identity, bí mật trong Key Vault, network policy và logs. Không cấp account key Storage dùng chung vào script tất cả nodes.

**Nghiệm thu:** so sánh runtime/cost thật với baseline, thử failure/retry, chứng minh checkpoint khôi phục được và kiểm tra mọi GPU VM đã được giải phóng sau job.

## 24. Tự kiểm tra kiến thức

**Câu 1.** HPC có đồng nghĩa bắt buộc dùng GPU không?

A. Có, mọi HPC job đều phải dùng NC/ND VM.  
B. Không; HPC có thể tối ưu cho CPU, GPU hoặc kết hợp.  
C. Có, trừ khi chỉ có một node.

**Đáp án: B.** Lựa chọn phần cứng phụ thuộc thuật toán, mức song song, bộ nhớ và cách ứng dụng sử dụng accelerator.

**Câu 2.** Khi nào kết nối RDMA/InfiniBand quan trọng hơn Ethernet thông thường?

**Đáp án:** Với một số workload MPI hoặc distributed GPU training có giao tiếp liên node thường xuyên, nhạy với latency/băng thông. Không phải batch độc lập nào cũng cần RDMA.

**Câu 3.** Azure Accelerated Networking có bảo đảm VM sử dụng RDMA không?

**Đáp án:** Không. Accelerated Networking cải thiện đường mạng VM trên các cấu hình hỗ trợ; RDMA/InfiniBand là tính năng khác và phải được xác minh theo SKU/network.

**Câu 4.** Một VM có 4 GPU, mỗi GPU 40 GiB VRAM. Có mặc định một tiến trình dùng được 160 GiB VRAM liên tục không?

**Đáp án:** Không. VRAM nằm trên các GPU khác nhau; muốn sử dụng tổng bộ nhớ phải có framework/chiến lược phân phối thích hợp.

**Câu 5.** Khi GPU utilization chỉ 15%, có nên thêm GPU ngay?

**Đáp án:** Không. Trước hết profile CPU/dataloader, storage, network, batch size và kernel; thêm GPU khi bottleneck ở nguồn khác có thể làm chi phí tăng mà throughput không cải thiện.

**Câu 6.** Vì sao có quota GPU vẫn có thể không tạo được VM?

**Đáp án:** Quota cho phép yêu cầu tài nguyên nhưng **physical capacity** của SKU/zone/region có thể không đủ tại thời điểm cấp phát.

**Câu 7.** Dùng Azure Spot VM phù hợp với loại job nào?

**Đáp án:** Job có thể checkpoint/retry, không đặt state duy nhất trên local disk và chấp nhận eviction; không phù hợp các job không thể gián đoạn với deadline nghiêm ngặt mà không có dự phòng.

**Câu 8.** Azure Batch và CycleCloud/Slurm khác nhau ở đâu?

**Đáp án:** Batch cung cấp mô hình managed pool/job/task cho batch workflows. CycleCloud quản lý cluster HPC và Slurm cung cấp scheduler với queue/partition/resource allocation, thường phù hợp môi trường HPC/MPI chuyên sâu.

**Câu 9.** Nếu output chỉ ghi vào local NVMe rồi VM bị giải phóng, chuyện gì có thể xảy ra?

**Đáp án:** Dữ liệu tạm có thể bị mất. Output/checkpoint quan trọng phải được chuyển sang storage bền vững trước khi node bị dọn.

**Câu 10.** VM giá 7 USD/giờ chạy job trong 5 giờ so với VM 4 USD/giờ chạy 10 giờ; phương án nào rẻ hơn về compute?

**Đáp án:** Phương án 7 × 5 = 35 USD, so với 4 × 10 = 40 USD, nếu cùng job/kết quả; tổng chi phí còn phụ thuộc storage/network và phụ phí khác.

**Câu 11.** Tại sao cần lưu driver/runtime version theo job?

**Đáp án:** Để tái lập kết quả, giải thích thay đổi throughput hoặc sai số, và xử lý incompatibility sau khi nâng cấp image.

**Câu 12.** Có thể chọn GPU ND-series chỉ dựa trên tên nhóm để chắc chắn nhận được NVLink và InfiniBand không?

**Đáp án:** Không. Phải kiểm tra model/SKU/series generation, số GPU, topology GPU–GPU và interconnect được hỗ trợ.

**Câu 13.** Một solver MPI 4 node chạy lâu hơn 1 node. Có thể do đâu?

**Đáp án:** Overhead đồng bộ/network, workload quá nhỏ để scale, placement, MPI configuration hoặc I/O. Cần benchmark strong scaling và profiler.

**Câu 14.** Có cần thêm bản backup ngoài local scratch nếu sử dụng Azure Managed Lustre hoặc Blob không?

**Đáp án:** Các hệ thống có mục đích khác nhau: scratch/cache không phải nguồn dữ liệu bền vững, và storage bền vững vẫn cần chính sách backup/versioning/recovery phù hợp yêu cầu; không dựa vào một bản dữ liệu duy nhất.

**Câu 15.** Kết quả của một job được coi là hoàn tất khi scheduler báo exit code 0 chưa?

**Đáp án:** Chưa đủ. Cần kiểm tra dữ liệu đầu ra, độ chính xác/hội tụ, metadata, checkpoint/output ở storage bền vững, và xác minh tài nguyên được thu hồi.

**Tóm lại:** Thiết kế HPC/GPU trên Azure là bài toán phối hợp **thuật toán – VM – bộ nhớ – mạng – lưu trữ – scheduler – bảo mật – chi phí**. Bắt đầu bằng benchmark nhỏ, hiểu điểm nghẽn, chọn đúng họ VM, chỉ mở rộng khi có bằng chứng hiệu quả và luôn chuẩn bị checkpoint/khôi phục. Một cluster tốt không phải cluster nhiều GPU nhất, mà là cluster **hoàn thành công việc đúng, đúng hạn và với tổng chi phí có thể kiểm soát**.
