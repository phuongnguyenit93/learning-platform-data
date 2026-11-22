# Slurm và tổ chức hàng đợi HPC trên Google Cloud

Một bài mô phỏng vật lý có thể cần hàng trăm CPU trong 20 phút, trong khi một bước tối ưu mô hình cần GPU trong nhiều giờ. Nếu các nhóm nghiên cứu cùng yêu cầu máy ảo bằng tay, tài nguyên dễ bị bỏ trống hoặc bị một nhóm chiếm dụng; người dùng không biết khi nào đến lượt chạy, còn quản trị viên khó đo chi phí cho từng dự án. **Slurm** giải quyết lớp điều phối này bằng việc tiếp nhận job, xếp hàng, cấp tài nguyên theo chính sách, giám sát và thu hồi tài nguyên sau khi job kết thúc.

Trên Google Cloud, Slurm có thể phối hợp với Compute Engine để tạo các compute node khi có job được xếp lịch và thu hồi chúng khi không cần nữa. **Cluster Toolkit** cung cấp blueprint và module để triển khai Slurm, networking, shared storage và tài nguyên tính toán theo Infrastructure as Code (IaC). Đội vận hành vẫn phải quản lý chính sách scheduling, quyền truy cập, tính đúng đắn của phần mềm khoa học, quota và chi phí; **autoscaling không đồng nghĩa tài nguyên luôn sẵn có hoặc miễn phí khi hàng đợi trống**.

Bài học thuộc chương **Hạ tầng chuyên biệt** của module **CLOUD_PROVIDERS_GCP**, nơi người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; qua tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Chủ đề này tập trung vào thiết kế và vận hành **hàng đợi Slurm cho workload HPC/AI** trên Google Cloud, không nhầm Slurm với một dịch vụ hàng đợi message thông thường.

> **Phạm vi thực hành:** Các tên project, partition, job, machine type và mốc giá trong bài là minh họa. Không chạy lệnh tạo hoặc phá hạ tầng production từ hướng dẫn này. Các tính năng, hạn mức, hỗ trợ TPU/GPU, loại VM, vùng triển khai và giá phụ thuộc phiên bản Cluster Toolkit, region và cấu hình cụ thể; luôn xác minh trong project thử nghiệm trước khi áp dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt Slurm scheduler, controller, login node, compute node, partition, nodeset và accounting.
- Giải thích vòng đời job từ `PENDING` qua `RUNNING` đến kết thúc, và cách Slurm yêu cầu Compute Engine mở rộng tài nguyên.
- Dùng `sinfo`, `squeue`, `sbatch`, `srun`, `scancel`, `sacct` và `scontrol` để nộp và theo dõi job.
- Tổ chức partition theo CPU, GPU, tính chất batch, mức ưu tiên và loại capacity.
- Cấu hình giới hạn tài nguyên, job array concurrency, fair-share/QOS và retry/checkpoint hợp lý.
- Phân biệt nguyên nhân job chờ do chính sách Slurm với lỗi quota hoặc thiếu capacity Google Cloud.
- Thiết kế shared storage, network, IAM, log, backup và cách tính chi phí vòng đời cluster.
- Hoàn thành lab triển khai cluster mẫu bằng Cluster Toolkit và dọn tài nguyên sau thực hành.

## 1. HPC và Slurm khác gì với ứng dụng cloud thông thường?

**High Performance Computing (HPC)** thường bao gồm mô phỏng số, CFD, nghiên cứu sinh học, rendering, tính toán tài chính, tối ưu hóa hoặc tác vụ AI cần nhiều CPU/GPU, bộ nhớ, I/O hay truyền dữ liệu giữa nhiều node với độ trễ thấp.

Ứng dụng HTTP chạy trên Cloud Run/GKE thường đón request ngay và tự mở rộng theo lưu lượng. Một workload HPC có thể:

- Biết trước số node, core, RAM hoặc GPU cần dùng.
- Chạy hàng chục phút đến nhiều giờ và có thể cần checkpoint.
- Cần nhiều tiến trình chạy đồng bộ theo MPI; không thể tự ý giảm số node giữa chừng.
- Dùng input dataset lớn, tạo hàng nghìn file kết quả.
- Có hạn chót nghiên cứu hoặc ưu tiên theo project, người dùng và ngân sách.
- Cần xếp hàng **đợi đến khi đủ tài nguyên cùng lúc**, thay vì xử lý request riêng lẻ.

Slurm quản lý **batch job queue và resource allocation**. Nó không thay cho Pub/Sub/Cloud Tasks (hàng đợi message/event), không tự đảm bảo code khoa học có khả năng restart, và không phải dịch vụ quản lý hoàn toàn nếu bạn tự triển khai trên Compute Engine.

| Nhu cầu | Công cụ thường hợp lý | Vì sao |
|---|---|---|
| Chạy mô phỏng nhiều node, cần MPI và batch queue | Slurm trên Google Cloud | Hỗ trợ job allocation, partitions, priority, accounting |
| Chạy HTTP API stateless | Cloud Run/GKE | Điều phối request/replica thay vì batch HPC |
| Chạy các batch task độc lập, không cần Slurm policy | Google Cloud Batch | Dịch vụ batch managed, không bắt buộc vận hành Slurm |
| Chạy container Kubernetes với scheduling K8s | GKE và bộ điều phối phù hợp | Dùng Kubernetes API, scheduling/policies |
| Đã có Slurm on-prem và muốn cloud bursting | Slurm hybrid/Cluster Toolkit | Giữ workflow `sbatch`, mở rộng capacity khi được thiết kế |

Cần chọn orchestrator theo mô hình workload, đội ngũ và mức độ kiểm soát. **Cluster Director** là phương án Google-managed Slurm được tài liệu Google Cloud giới thiệu ở trạng thái **Preview** tại thời điểm tham khảo; **Cluster Toolkit** là open-source IaC linh hoạt hơn, với trách nhiệm vận hành cluster vẫn thuộc nhóm triển khai. Không mặc định mọi tính năng hoặc SLA của một phương án có mặt trong phương án còn lại.

## 2. Kiến trúc Slurm trên Google Cloud

Một cluster Slurm thường có các thành phần:

| Thành phần | Nhiệm vụ | Ghi chú vận hành |
|---|---|---|
| Login node | Người dùng SSH, chuẩn bị script, nộp job | Không chạy workload nặng ở đây |
| Slurm controller (`slurmctld`) | Xếp lịch, quyết định phân bổ job/node | Thành phần control plane quan trọng cần giám sát và bảo vệ |
| Compute nodes (`slurmd`) | Chạy các task được phân bổ | Có thể static hoặc dynamic |
| Accounting service (`slurmdbd`), nếu bật | Lưu lịch sử job/association và hỗ trợ accounting | Cần database và cấu hình riêng; `sacct` tùy khả năng lưu lịch sử |
| MUNGE hoặc cơ chế auth cấu hình | Xác thực thành phần Slurm | Bảo vệ secret, quyền trên host và đồng bộ identity |
| Shared filesystem | Chia input, home, software và kết quả | Hiệu năng metadata và throughput quyết định tốc độ I/O |
| Google Cloud VPC/IAM | Network, identity và quyền API tạo/xóa VM | Không nhầm Linux user/Slurm account với IAM principal |
| Cloud Monitoring/Logging | Quan sát VM, controller và ứng dụng | Cần thiết lập collection thích hợp; không mọi metric job tự có |

~~~mermaid
flowchart LR
    U["Nhà nghiên cứu"] -->|SSH/IAP| L["Login node"]
    L -->|sbatch/squeue| C["Slurm controller"]
    C --> Q["Queue / partitions"]
    Q -->|Schedule + resume| N["Dynamic compute nodes"]
    C -->|Allocate| S["Static compute nodes"]
    N -->|Read/write| F[("Shared storage")]
    S --> F
    L --> F
    C -->|Cloud API| CE["Compute Engine / quota / capacity"]
    C --> A[("Accounting service tùy chọn")]
    N --> M["Logs/metrics"]
    C --> M
    S --> M
~~~

Luồng logic:

1. Người dùng vào login node được phép, nộp job qua `sbatch`.
2. `slurmctld` đưa job vào queue và đánh giá partition, resource request, fair-share/QOS cùng tình trạng node.
3. Với dynamic nodeset, Slurm-GCP integration có thể yêu cầu Compute Engine tạo VM phù hợp.
4. VM khởi động, kết nối mạng/storage, chạy `slurmd` và đăng ký trạng thái với controller.
5. Khi đủ tài nguyên, Slurm phân bổ job và lệnh trong job script chạy trên compute node.
6. Job tạo stdout/stderr, checkpoint và output, đồng thời ghi accounting nếu đã cấu hình.
7. Khi job xong, node được giữ, suspend hoặc xóa theo loại nodeset/partition và chính sách power saving.

**Lưu ý:** Thời gian VM khởi động, cài image, mount filesystem và khởi tạo MPI/GPU cũng làm tăng thời gian từ lúc nộp đến lúc job thực thi. Autoscaling không biến một job `PENDING` thành `RUNNING` ngay lập tức.

### 2.1. Login không phải compute

Login node dùng cho thao tác tương tác nhẹ: biên soạn mã nguồn, chuẩn bị input, chạy `squeue`, kiểm tra kết quả. Job nặng phải đưa vào partition và chạy trên compute node.

Nếu nhiều người chạy trực tiếp CPU/GPU calculation trên login node:

- Gây cạnh tranh với Slurm controller hoặc tác vụ quản trị nếu đặt chung không đúng cách.
- Không có accounting/cgroup giới hạn theo job như dự kiến.
- Có thể tăng chi phí login node và làm mất khả năng truy cập cluster khi tải cao.

Áp dụng Linux access control, giới hạn resource cho login session và hướng dẫn rõ cách chuyển công việc sang `sbatch`.

## 3. Các khái niệm scheduling cốt lõi

| Thuật ngữ | Ý nghĩa |
|---|---|
| Job | Một đơn vị công việc người dùng nộp, có script, tài nguyên và lifecycle |
| Job step | Một bước chạy trong allocation, thường được tạo bởi `srun` |
| Partition | Tập compute nodes và các quy tắc chung để job có thể được chạy |
| Nodeset | Nhóm node cùng cấu hình tài nguyên trong Cluster Toolkit, dùng làm đầu vào partition |
| Account / association | Nhóm hạch toán người dùng/dự án theo Slurm Accounting |
| QOS | Policy mức dịch vụ: ưu tiên, preemption, limits tùy cấu hình |
| Fair-share | Cách Slurm tính ưu tiên có xét lịch sử sử dụng và phân bổ |
| Reservation | Nhóm resource được giữ trước cho khoảng thời gian/đối tượng nhất định |
| Walltime | Thời hạn chạy của job, ví dụ `--time=00:30:00` |
| Node resources | CPU, RAM, GPU/GRES, filesystem, topology hoặc feature |
| Static node | Node được cấp trước, có vòng đời theo thiết kế |
| Dynamic node | Node có thể được tạo khi có nhu cầu, thu hồi khi không cần |

**Partition không nhất thiết tương ứng một loại VM duy nhất.** Một partition có thể tham chiếu một hoặc nhiều nodeset. Cần thiết kế resource tương thích với job: trộn machine types quá khác nhau trong cùng partition có thể dẫn đến phân bổ không tối ưu hoặc biến động thời gian chạy.

### 3.1. Job states

| State | Ký hiệu thường gặp | Diễn giải |
|---|---|---|
| Pending | `PD` | Đang chờ tài nguyên, ưu tiên, dependency hoặc chính sách |
| Running | `R` | Job đang chạy |
| Completing | `CG` | Job đang hoàn tất và dọn bước cuối |
| Completed | `CD` | Kết thúc thành công theo trạng thái Slurm |
| Failed | `F` | Job thất bại |
| Cancelled | `CA` | Bị hủy |
| Timeout | `TO` | Vượt giới hạn walltime |
| Node fail | `NF` | Node bị lỗi ảnh hưởng job |
| Out of memory | `OOM` hoặc trạng thái tương ứng | Job bị ảnh hưởng bởi giới hạn bộ nhớ |

Trạng thái cụ thể và mã exit phụ thuộc cấu hình Slurm/plug-in. `COMPLETED` không có nghĩa kết quả khoa học đúng; cần chạy validation trên output, checksum, convergence hoặc kiểm tra nghiệp vụ.

## 4. Chuẩn bị Google Cloud trước khi triển khai

Để tránh chi phí ngoài ý muốn, nên tạo **project lab riêng**, budget alert, quota nhỏ và thời điểm dọn tài nguyên. Một cluster cơ bản vẫn có phí **controller, login node, disk, shared filesystem và network** ngay cả khi không có compute job.

Checklist chuẩn bị:

1. Project được bật billing và có quyền sử dụng Compute Engine, IAM, Filestore hoặc lưu trữ được chọn.
2. Xác minh **region/zone** có machine type, CPU/GPU/TPU và shared storage phù hợp.
3. Kiểm tra quotas: CPU theo region, machine-family quota, GPU và disk IP/address/API khi áp dụng; kiểm tra capacity thực tế ngoài quota.
4. Xác định VPC, subnet, firewall nội bộ, SSH/IAP/OS Login và đường ra để tải package.
5. Chọn topology một zone hay nhiều zone; job MPI giao tiếp mạnh thường cần network/topology tương thích.
6. Chuẩn bị service account của controller đủ quyền quản lý compute node, không phát khóa JSON cho người dùng.
7. Xác định mô hình Linux user/group và Slurm account/QOS; không dùng quyền root chung cho mọi người.
8. Chọn shared filesystem, path mount, input/output và checkpoint policy.
9. Lựa chọn blueprint Cluster Toolkit được duy trì, pin phiên bản và review Terraform plan.
10. Đặt nhãn cloud resources theo cluster/project/owner/cost-center và cách dọn sau lab.

Ví dụ bật các APIs cơ bản bằng tài khoản bootstrap được cấp phép:

~~~bash
gcloud services enable \
  compute.googleapis.com \
  iam.googleapis.com \
  file.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  serviceusage.googleapis.com \
  --project=HPC_LAB_PROJECT_ID
~~~

Các API cần bật có thể khác tùy blueprint. **Đừng cấp Owner mặc định** cho service account controller; hướng dẫn quickstart có thể sử dụng quyền rộng để demo, production cần tạo custom roles/đánh giá quyền thực tế theo principle of least privilege.

### 4.1. Project isolation

Nếu một nhóm HPC dùng chung project với ứng dụng production, các thao tác autoscaling hoặc cạn CPU/GPU quota có thể ảnh hưởng workload không liên quan. Với bài thực hành, ưu tiên project riêng. Đối với production, cân nhắc project per cluster/workload/environment, folder policy và billing labels để kiểm soát blast radius.

## 5. Deploy Slurm bằng Cluster Toolkit

**Cluster Toolkit** là công cụ open-source của Google Cloud dùng blueprint YAML và các module để tạo deployment Terraform/Packer. Nó không phải dịch vụ managed vận hành toàn bộ cluster thay bạn.

Tài liệu quickstart chính thức hướng dẫn:

1. Cài phiên bản `gcluster` được phát hành cho hệ điều hành/kiến trúc của bạn.
2. Dùng blueprint mẫu `examples/hpc-slurm.yaml`.
3. Kiểm tra biến và module; generate deployment folder bằng `gcluster create`.
4. Review Terraform plan rồi triển khai với `gcluster deploy`.
5. SSH vào login node, chạy `srun`/`sbatch` để kích hoạt dynamic compute nodes.
6. Dọn cluster nếu chỉ làm lab.

Ví dụ **chỉ chạy sau khi đã tải Cluster Toolkit chính thức** và xác nhận region/quota/budget:

~~~bash
# Thực hiện trong thư mục bộ Cluster Toolkit đã cài.
./gcluster --version

# Xem các biến cần cấu hình trong blueprint.
./gcluster explain examples/hpc-slurm.yaml

# Tạo deployment Terraform từ blueprint mẫu.
./gcluster create examples/hpc-slurm.yaml \
  -l ERROR --vars project_id=HPC_LAB_PROJECT_ID

# Review plan rồi quyết định có apply hay không.
./gcluster deploy hpc-slurm
~~~

`gcluster create` sinh folder như `hpc-slurm/`; `gcluster deploy` dùng Terraform để tạo hạ tầng thực và có thể phát sinh chi phí. Không chạy `deploy` như bước xác nhận cú pháp; nếu cần kiểm tra trước, dùng `explain` và các chức năng validate/plan. Tên folder phụ thuộc blueprint và phiên bản, hãy kiểm tra output thực tế trước khi chạy lệnh tiếp.

**Trách nhiệm quản trị vẫn còn:** Terraform state, cập nhật image OS, Slurm controller, MUNGE, scheduler config, backup, accounting, security và upgrade. Tài liệu Google Cloud hiện khuyến nghị sử dụng blueprint/modules Cluster Toolkit thay vì trực tiếp dùng Terraform modules trong repository `slurm-gcp` cũ khi không có lý do riêng.

### 5.1. Nodeset và partition trong blueprint

Tổ chức hàng đợi dựa trên **nhóm máy có đặc tính phù hợp**. Cluster Toolkit cung cấp module nodeset và partition. Ví dụ trích đoạn cấu hình **chưa đầy đủ để deploy độc lập**:

~~~yaml
# Trích đoạn từ phần modules của blueprint Cluster Toolkit.
# Các module network, shared filesystem và Slurm controller
# phải được định nghĩa ở những phần khác của blueprint.
- id: cpu_nodes
  source: community/modules/compute/schedmd-slurm-gcp-v6-nodeset
  use: [network]
  settings:
    node_count_dynamic_max: 8
    machine_type: n2-standard-4

- id: cpu_partition
  source: community/modules/compute/schedmd-slurm-gcp-v6-partition
  use: [cpu_nodes, homefs]
  settings:
    partition_name: cpu
    is_default: true
    exclusive: true
    suspend_time: 300
    resume_timeout: 300
    suspend_timeout: 120
~~~

Giải thích:

- `node_count_dynamic_max: 8` giới hạn số node dynamic trong **nodeset** này theo cấu hình Cluster Toolkit; không bảo đảm quota/capacity Google Cloud đủ để tạo 8 VM.
- `machine_type` xác định CPU/RAM của các node thuộc nodeset.
- Partition `cpu` tập hợp nodeset và file system đã định nghĩa trước.
- `is_default: true` để job không chỉ định `--partition` có thể được xếp vào đây.
- `exclusive: true`: node được dành riêng cho một job theo thiết kế module này; với dynamic node có thể xóa ngay sau job thay vì chờ `suspend_time`.
- `resume_timeout` và `suspend_timeout` đặt timeout cho vòng đời node power saving; không phải thời gian chờ tối đa của job trong queue.

**Quan trọng:** Trong Slurm trên Google Cloud, partition module của Cluster Toolkit có `exclusive=true` mặc định và có thể xóa node sau khi job hoàn tất. Khi cấu hình `exclusive=false`, nhiều job có thể chia sẻ node nếu resource allocations tương thích; node nhàn rỗi được suspend sau khoảng quy định. Thử nghiệm hai mô hình và đánh giá phí khởi động so với resource utilization.

### 5.2. Tại sao không tự cấu hình Slurm thủ công trên tất cả VM?

Tự cài Slurm trên VM cho phép kiểm soát sâu, nhưng phải tự xử lý:

- Bootstrap và cập nhật controller/compute images nhất quán.
- Đồng bộ `slurm.conf`, MUNGE auth, user/group IDs và shared mounts.
- Gắn API để tạo/xóa VM, theo dõi trạng thái khi Compute Engine bị lỗi.
- Tự xây monitoring, database accounting, backup và controller failover.
- Giải quyết drift giữa state Slurm và state VM ngoài cloud.

Cluster Toolkit giảm công việc tạo cluster từ đầu, nhưng không loại bỏ việc cần hiểu kiến trúc và vận hành.

## 6. Nộp job: ba loại workload cơ bản

Các ví dụ sau chạy **từ login node có Slurm client** sau khi cluster đã sẵn sàng. Tên partition `cpu` trong script là tên đã được định nghĩa ở ví dụ blueprint; nếu cluster thực tế dùng `debug` hoặc `compute`, thay theo `sinfo`.

### 6.1. Khám phá tài nguyên

~~~bash
# Các partition/nodes hiện có.
sinfo

# In theo định dạng dễ so sánh.
sinfo -o "%P %a %l %D %t"

# Job của chính mình.
squeue --me

# Xem mô tả partition cụ thể.
scontrol show partition cpu

# Xem node status ở partition cụ thể.
sinfo -p cpu -N
~~~

Cột `AVAIL` và `STATE` cho biết partition/node có khả dụng về mặt Slurm hay không. **Một dynamic node chưa tồn tại ngoài Compute Engine** có thể xuất hiện dưới trạng thái power-down hoặc trạng thái logic khác; kiểm tra cách module biểu diễn node và tránh kết luận “có 8 node thì cả 8 đang tính tiền”.

### 6.2. Job CPU đơn giản bằng sbatch

Chuẩn bị thư mục log **trước khi nộp job**:

~~~bash
mkdir -p "$HOME/slurm-lab/logs"
cd "$HOME/slurm-lab"
~~~

Tạo script `hello.sbatch`:

~~~bash
#!/usr/bin/env bash
#SBATCH --job-name=hello-hpc
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:05:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err

set -euo pipefail

echo "Job ID: $SLURM_JOB_ID"
echo "Node list: $SLURM_JOB_NODELIST"
date -u
srun hostname
sleep 10
echo "Job complete"
~~~

Lệnh nộp và theo dõi:

~~~bash
sbatch hello.sbatch
squeue --me
squeue -j JOB_ID
scontrol show job JOB_ID
~~~

Ý nghĩa các lựa chọn:

- `--nodes=1`: yêu cầu một node.
- `--ntasks=1`: một Slurm task, **không có nghĩa chỉ một CPU**.
- `--cpus-per-task=2`: task yêu cầu hai CPU logical theo topology/config của cluster.
- `--mem=4G`: yêu cầu RAM; scheduler cấp phát dựa trên chính sách.
- `--time=00:05:00`: walltime limit, quá hạn job có thể bị kill/cancel.
- `--output` và `--error`: file log; thư mục cha phải tồn tại và ghi được trước khi job bắt đầu.

**Đừng xin 64 CPU cho code chạy một thread.** Slurm cấp tài nguyên theo yêu cầu; nếu ứng dụng không dùng hết, tài nguyên vẫn bị chiếm và chi phí có thể tăng. Với ứng dụng OpenMP, đặt `OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK` sau khi đã đánh giá tính tương thích.

### 6.3. Job array cho sweep tham số

Một nhóm nghiên cứu muốn chạy 16 bộ tham số độc lập. Dùng **job array** thay vì viết 16 script gần như giống nhau:

~~~bash
#!/usr/bin/env bash
#SBATCH --job-name=param-sweep
#SBATCH --partition=cpu
#SBATCH --array=0-15%4
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --output=logs/%x-%A_%a.out

set -euo pipefail

echo "Array parent ID: $SLURM_ARRAY_JOB_ID"
echo "Array task ID: $SLURM_ARRAY_TASK_ID"
echo "Node: $(hostname)"

# Thay lệnh này bằng chương trình mô phỏng thật;
# dùng task index để chọn đúng dữ liệu hoặc seed.
sleep 5
echo "Case $SLURM_ARRAY_TASK_ID done"
~~~

Tùy chọn `--array=0-15%4` tạo 16 array tasks, giới hạn **tối đa bốn task chạy đồng thời trong array này**. Giới hạn này không áp dụng cho toàn cluster hoặc cho các job khác. Slurm còn có giới hạn `MaxArraySize`, account, QOS và số job được nộp nếu cluster cấu hình.

Kiểm tra:

~~~bash
sbatch sweep.sbatch
squeue --me
sacct -j ARRAY_JOB_ID --format=JobID,State,Elapsed,AllocCPUS,ExitCode
~~~

`sacct` yêu cầu cluster có job accounting được cấu hình phù hợp để truy vấn lịch sử đầy đủ. Nếu `sacct` không có dữ liệu, kiểm tra Slurm accounting thay vì kết luận job không chạy.

### 6.4. MPI job nhiều node

Ứng dụng MPI thường cần nhiều task đồng thời và network latency thấp:

~~~bash
#!/usr/bin/env bash
#SBATCH --job-name=mpi-solver
#SBATCH --partition=cpu
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=4
#SBATCH --time=00:20:00
#SBATCH --output=logs/%x-%j.out

set -euo pipefail
echo "Allocated nodes: $SLURM_JOB_NODELIST"

# Ví dụ chạy chương trình đã compile với MPI tương thích.
srun ./solver
~~~

Điều kiện để ví dụ chạy thật:

- `solver` phải có trên compute nodes, đã biên dịch với MPI stack/runtime tương thích.
- Partition phải có ít nhất hai node tương thích và đủ tài nguyên.
- Network, firewall, interface và performance tier cần đáp ứng MPI giữa các node.
- Slurm `srun`/MPI launch plugin được cấu hình phù hợp với MPI library. Nếu dùng `mpirun`, kiểm tra tích hợp của bản MPI thay vì thay trực tiếp mà không thử.

**Hai node không đồng nghĩa hiệu năng gấp đôi.** Chi phí giao tiếp và I/O có thể khiến thuật toán scale kém; cần chạy benchmark strong scaling/weak scaling.

## 7. Theo dõi job và phân tích lý do chờ hàng đợi

Các lệnh Slurm thường dùng:

| Lệnh | Mục đích | Ví dụ |
|---|---|---|
| `squeue` | Xem job trong queue | `squeue --me` |
| `sinfo` | Xem partition và node | `sinfo -R` xem node down/drain |
| `scontrol show job` | Xem chi tiết job: resources, reason, allocation | `scontrol show job JOB_ID` |
| `scontrol show node` | Xem node state/features | `scontrol show node NODE_NAME` |
| `sacct` | Lịch sử và CPU/memory/accounting | `sacct -j JOB_ID` |
| `sstat` | Chỉ số job/step đang chạy nếu được cấu hình | `sstat -j JOB_ID --format=AveCPU,MaxRSS` |
| `sprio` | Các thành phần priority khi dùng priority/multifactor | `sprio -j JOB_ID` |
| `sshare` | Thông tin fair-share khi cấu hình accounting | `sshare -l` |
| `scancel` | Hủy job do mình sở hữu | `scancel JOB_ID` |

Xem các job pending và lý do:

~~~bash
squeue -t PD -o "%.12i %.10P %.12u %.2t %.10M %.12l %R"
scontrol show job JOB_ID
sinfo -R
~~~

Một số lý do thường gặp:

| Reason/state | Nghĩa thường gặp | Kiểm tra |
|---|---|---|
| `Priority` | Job khác được ưu tiên hơn | `sprio`, fair-share, age |
| `Resources` | Chưa có đủ tài nguyên hợp lệ | Node state, VM type, partition, job size |
| `Dependency` | Job chờ job khác | `Dependency` trong job details |
| `QOSGrpCpuLimit` hoặc giới hạn account tương tự | Vượt giới hạn QOS/association | `sacctmgr` theo quyền admin, chính sách quota |
| `ReqNodeNotAvail` | Node yêu cầu không khả dụng | `sinfo`, reservation, drain, powered-down |
| `Nodes required for job are DOWN/DRAIN` | Node lỗi/bị drain | `sinfo -R` và log `slurmd` |
| `CG` quá lâu | Job cleanup hoặc node teardown chưa xong | Epilog, filesystem, controller logs |
| Job pending lâu dù dynamic nodes enabled | API/Quota/capacity/network bootstrap lỗi | Slurm resume logs, Compute Engine operations và quota |

**Phân biệt ba tầng giới hạn:**

1. **Scheduler limit:** job bị chặn bởi partition time limit, account/QOS, fair-share, node eligibility.
2. **Cloud quota:** project chưa đủ quota CPU/GPU/disk hoặc lỗi tốc độ gọi API.
3. **Cloud capacity:** quota còn nhưng zone không có đủ VM/GPU hiện khả dụng; Spot thường biến động mạnh.

Tăng QOS không làm xuất hiện GPU trong một zone đang hết capacity. Tăng quota cũng không bảo đảm Compute Engine có sẵn phần cứng tại thời điểm yêu cầu.

## 8. Tổ chức partitions cho nhiều nhóm HPC

Một tổ chức có thể tách:

| Partition minh họa | Loại node | Workload | Chính sách mẫu |
|---|---|---|---|
| `debug` | CPU nhỏ, dynamic | Test script 1–5 phút | MaxTime ngắn, queue priority phù hợp |
| `cpu` | CPU compute optimized, dynamic | Mô phỏng batch | MaxTime 8 giờ, fair-share |
| `gpu` | GPU VM phù hợp | Training/visualization | GPU quota, per-user GPU cap |
| `mpi` | VM/network cho MPI | Job nhiều node cần topology | Placement/capacity constraints |
| `spot` | Spot VMs | Job restart/checkpoint được | Preemption-aware, giới hạn retry |

Tên và cấu hình này chỉ minh họa, không được tạo sẵn bởi Slurm/Cluster Toolkit. **Có thể dùng một partition cho nhiều nodeset** nếu các đặc tính phù hợp; tách partition khi cần chính sách/giới hạn rõ ràng cho người dùng.

### 8.1. Chính sách nào ở partition, chính sách nào ở QOS?

- **Partition:** nhóm node đủ điều kiện, MaxTime, default, priority tier hoặc cơ chế cho phép truy cập tùy cluster.
- **QOS/account association:** giới hạn tổng concurrent jobs/CPU/GPU, priority, preemption và các chỉ tiêu dùng chung người dùng hoặc nhóm.
- **Job options:** yêu cầu `--time`, `--mem`, `--cpus-per-task`, `--gpus` hoặc `--constraint`.
- **Google Cloud:** quota, reservations, machine-family availability, VM lifecycle, billing.

Để chia tài nguyên công bằng giữa hai nhóm nghiên cứu, chỉ mở hai partitions chưa chắc đủ. Một người có thể gửi hàng nghìn job; cần accounting/QOS, user/association limits, fair-share và giám sát.

### 8.2. Ví dụ chính sách thay đổi tùy loại công việc

| Workload | Yêu cầu | Điều cần quản lý |
|---|---|---|
| Mô phỏng nhỏ nhiều lần | 1–4 CPU, memory thấp, walltime ngắn | Job arrays với concurrency cap |
| Large-memory simulation | RAM lớn, ít node | Mem request, chọn machine family phù hợp |
| MPI tightly coupled | Nhiều node đồng thời, low-latency | Placement, network, shared FS và gang scheduling |
| GPU experiment | GPU type/count và driver/CUDA | Quota GPU, module/image tương thích, max usage |
| Training có checkpoint | Chịu được preemption | Spot partition, checkpoint/restart |
| Job chạy liên tục | Resource ổn định trong nhiều ngày | Static/reservation hoặc capacity ổn định, không tùy tiện Spot |

## 9. Fair-share, QOS và ưu tiên job

Slurm có các cơ chế scheduling priority và accounting như `PriorityType=priority/multifactor`, fair-share tree, job age, job size, partition/QOS priority, reservations và limits. Những yếu tố nào đang bật phụ thuộc `slurm.conf` và database của cluster, không có một công thức bất biến cho mọi cài đặt.

Ví dụ chính sách cho tổ chức:

- Mỗi nhóm được phân bổ phần tài nguyên tương ứng ngân sách HPC.
- Job debug nhỏ có giới hạn walltime và có thể ưu tiên cho trải nghiệm nhanh, nhưng không được giữ GPU đắt nhiều giờ.
- Job sử dụng GPU lâu phải khai account hợp lệ và có quota GPU-hours nội bộ.
- Fair-share cho nhóm dùng ít tài nguyên có khả năng tăng ưu tiên trong giai đoạn sau.
- Giới hạn submission và running jobs để ngăn spam queue.

Một người dùng có thể yêu cầu QOS đã được admin tạo:

~~~bash
# Chỉ hợp lệ khi QOS 'normal' và account đã được cấp cho user.
sbatch --partition=cpu --qos=normal --account=research hello.sbatch

# Quan sát priority, nếu cluster có plugin tương ứng.
sprio -j JOB_ID
sshare -l
~~~

Quản trị viên dùng `sacctmgr` để quản lý accounts, users, associations và QOS. Không đưa trực tiếp lệnh thay đổi quyền hoặc limit trên production vào script của người dùng; những thao tác này phải được review, ghi audit và thực hiện bởi admin được ủy quyền.

### 9.1. Backfill scheduling

Slurm có thể chạy job nhỏ hơn ở những khoảng trống khi các job ưu tiên cao còn đợi đủ node, nếu bộ scheduling/backfill được cấu hình phù hợp. Người dùng nên cung cấp **walltime thực tế**: yêu cầu 24 giờ cho công việc chỉ chạy 10 phút có thể làm giảm hiệu quả backfill và khiến tài nguyên bị giữ không cần thiết.

Tránh “đặt walltime càng lớn càng tốt để khỏi timeout”. Cần đo p95 runtime, thêm biên an toàn hợp lý, checkpoint ở workload dài và điều chỉnh time limit theo bằng chứng.

## 10. Autoscaling: dynamic nodes và vòng đời VM

Trên Google Cloud, Cluster Toolkit hỗ trợ dynamic nodeset: Slurm yêu cầu khởi tạo node khi scheduler cần, rồi thu hồi node không dùng theo cấu hình. Hạ tầng Google Cloud và Slurm phải đồng bộ trạng thái; lỗi giữa hai hệ thống có thể tạo orphan VMs hoặc node `DOWN`.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Slurm controller
    participant API as Compute Engine API
    participant VM as Compute node
    U->>C: sbatch job
    C->>C: Kiểm tra resources, priority, limits
    C->>API: Resume / tạo VM nếu cần
    API-->>C: Operation accepted hoặc lỗi
    API->>VM: Boot, mount storage, start slurmd
    VM-->>C: Node ready
    C->>VM: Allocate job
    VM-->>C: Job completed
    C->>API: Suspend/delete theo partition policy
    API-->>C: VM stopped/deleted
~~~

### 10.1. Static hay dynamic?

| Chọn | Lợi ích | Rủi ro/chi phí |
|---|---|---|
| Static nodes | Giảm chờ khởi động, thích hợp workload liên tục | Capacity có thể nhàn rỗi và vẫn tính phí |
| Dynamic exclusive | Tạo theo job, thu hồi nhanh sau job | Startup latency và chi phí setup mỗi lần |
| Dynamic shared | Nhiều job cùng dùng node, giữ node một thời gian idle | Phức tạp hơn ở sharing, isolation và tài nguyên lẻ |
| Reservation-backed | Tăng độ chắc chắn về capacity theo cam kết | Phí/cam kết reservation, cần quản trị |
| Spot nodes | Tiết kiệm với job có checkpoint/restart | Bị preempt, capacity không bảo đảm, mất tiến độ |

Với module Slurm partition của Cluster Toolkit, `exclusive=true` mặc định có thể khiến node dynamic bị xóa ngay sau khi job xong, bỏ qua `suspend_time`. Với `exclusive=false`, `suspend_time` ảnh hưởng khoảng nhàn rỗi trước khi node được suspend. **Cấu hình power saving phải kiểm tra theo module/version đang dùng**, không suy ra từ tên biến một cách máy móc.

### 10.2. Quota và availability

Dynamic nodeset với `node_count_dynamic_max: 8` là giới hạn cấu hình cluster, nhưng khi job cần 8 VM có thể thiếu:

- Regional CPU quota hoặc quota theo machine family.
- Quota GPU hoặc số lượng accelerator hỗ trợ.
- IP address, Persistent Disk, Filestore network resource.
- Available VM capacity trong zone.
- Quyền `compute.instances.create` hoặc service account IAM.
- Placement policy tương thích với topology.
- Startup image có driver, network và filesystem mount đúng.

Khi job `PENDING` lâu, kiểm tra cả Slurm lý do chờ lẫn Compute Engine activity. Không mặc định “queue còn slot” đồng nghĩa “GCP có 8 máy chờ sẵn”.

## 11. Chọn loại VM, networking và placement cho HPC

HPC chịu ảnh hưởng của **CPU architecture, memory bandwidth, network latency, accelerator topology, storage IOPS** và quy mô node. Một lựa chọn giá rẻ theo số vCPU có thể kéo dài chạy hơn nhiều vì memory hoặc network bottleneck.

| Thành phần | Điều cần kiểm tra |
|---|---|
| CPU VM | ISA, core count, NUMA, memory per core, benchmark ứng dụng |
| Memory | Peak RSS, memory bandwidth, swap không mong muốn |
| GPU | Model, số GPU/node, driver/CUDA/ROCm compatibility, quotas |
| TPU | Slurm TPU nodeset/topology và khả năng hỗ trợ theo generation |
| Network | Băng thông, latency, topology, placement, TCP/gVNIC/RDMA nếu cần |
| Storage | IOPS, throughput, metadata, sharing semantics và chi phí |
| Location | Region/zone hỗ trợ machine type, reservation và data residency |

Google Cloud có các dòng VM và network HPC chuyên biệt, bao gồm cấu hình high-bandwidth/Cloud RDMA cho một số loại workload/VM. **Không tự suy ra mọi Compute Engine VM đều hỗ trợ RDMA**, cũng không giả định chỉ cần thêm network flag là MPI sẽ nhanh hơn. Cần chọn đúng máy, image, driver, topology và benchmark.

### 11.1. MPI và giao tiếp nhiều node

Với tightly coupled simulation, hãy đo:

- Latency và bandwidth giữa các node theo placement.
- Thời gian `MPI_Allreduce` hoặc collectives theo số rank.
- Strong scaling: cùng tổng khối lượng công việc, tăng số node.
- Weak scaling: giữ khối lượng công việc trên mỗi node, tăng tổng workload.
- I/O checkpoint và dữ liệu input để tránh nhầm bottleneck storage với bottleneck compute.

Không chỉ dùng `hostname` trên ba node để chứng minh MPI throughput. `hostname` kiểm tra được việc Slurm cấp node và chạy command, chưa đánh giá năng lực HPC.

## 12. Shared storage và dữ liệu đầu vào/đầu ra

Một cluster HPC thường cần dùng chung dữ liệu giữa login/controller/compute nodes. Google Cloud cung cấp các lựa chọn với đặc tính khác nhau:

| Dịch vụ/cách dùng | Phù hợp | Cần lưu ý |
|---|---|---|
| Filestore (NFS) | Home directory, software và shared files thông thường | Throughput/IOPS, tier, capacity, network |
| Google Cloud Managed Lustre | Scratch I/O song song hiệu năng cao cho HPC | Giá, capacity, lifecycle, dữ liệu không coi là backup |
| Cloud Storage | Dataset, checkpoints, artifact và lưu kết quả bền vững | Object semantics; không là POSIX filesystem mặc định |
| Cloud Storage FUSE | Truy cập object qua mount theo use case phù hợp | Khác filesystem POSIX ở semantics/latency; test ứng dụng |
| Local SSD / local disk | Scratch tạm tốc độ cao trên node | Mất dữ liệu khi node bị xóa/preempt |
| Persistent Disk | Disk của VM hoặc dữ liệu được gắn theo thiết kế | Performance/capacity/attachment, chi phí khi VM dừng |

### 12.1. Stage dữ liệu trước và sau job

Một pattern phổ biến:

~~~mermaid
flowchart LR
    G[("Cloud Storage: input dataset")] -->|Stage-in| L["Scratch/Shared FS"]
    L -->|Run job| C["Compute nodes"]
    C -->|Checkpoint định kỳ| L
    L -->|Stage-out| O[("Cloud Storage: output/artifacts")]
    C --> M["Job stdout/stderr + metrics"]
~~~

Không ghi checkpoint cuối cùng **chỉ** vào disk của dynamic node; khi node bị xóa hoặc Spot bị preempt, checkpoint cũng có thể mất. Với file lớn, cân nhắc stage-in/out có checksum, retry và giới hạn I/O cùng lúc.

### 12.2. Performance của filesystem

Ví dụ 100 job array cùng mở 10.000 file nhỏ có thể làm nghẽn metadata ops dù tổng dữ liệu ít. Các cách cải thiện gồm:

- Gộp file nhỏ hoặc dùng data format phù hợp.
- Tránh tất cả job mở chung một file để append.
- Thiết kế shard output theo job ID hoặc array task ID.
- Giới hạn số task I/O-heavy đồng thời.
- Dùng scratch cục bộ cho bước trung gian, stage-out khi xong.
- Đo throughput/metadata latency ở kích thước workload thực tế.

## 13. Checkpointing và Spot/preemption

Spot VMs có thể bị thu hồi theo chính sách hạ tầng; giá thường thấp hơn máy on-demand nhưng không cam kết liên tục. Nếu cần hoàn thành một MPI run kéo dài nhiều giờ mà không có checkpoint, Spot có thể làm tổng chi phí và thời gian hoàn thành tăng.

Một chiến lược checkpoint tối thiểu:

1. Xác định state cần lưu để restart, gồm tiến độ iteration và random seed.
2. Ghi checkpoint theo chu kỳ phù hợp với chi phí ghi và xác suất preemption.
3. Đưa checkpoint lên shared/durable storage, không chỉ local disk.
4. Dùng file tạm rồi rename/commit theo kiểu an toàn để tránh checkpoint bị ghi dở.
5. Trên rerun, xác định checkpoint mới nhất **hợp lệ**, không chỉ file có timestamp mới nhất.
6. Giới hạn retries và tránh chạy mãi nếu lỗi do cấu hình/memory không phù hợp.
7. Lưu provenance: image/build, input dataset, code version, job ID và output checksum.

**Không có chuyện mọi Slurm job tự restart an toàn sau Spot preemption.** Slurm có thể requeue/restart theo cấu hình, nhưng ứng dụng phải hỗ trợ trạng thái, idempotency và checkpoint. Job `COMPLETED` chỉ nói job process kết thúc thành công, không đủ bằng chứng kết quả đã được stage-out.

## 14. Tổ chức quyền, bảo mật và đa người dùng

HPC cluster là môi trường nhiều người dùng và thường có dữ liệu nghiên cứu nhạy cảm. Phân biệt:

- **Google Cloud IAM:** ai được tạo VM, đọc bucket, quản lý VPC, dùng service account và gọi API.
- **Linux identity:** UID/GID, SSH/OS Login, quyền file trên shared FS.
- **Slurm identity:** user, account, partition, QOS và fair-share/association.
- **Application identity:** quyền riêng khi job gọi dịch vụ Google Cloud.

Được phép `sbatch` không có nghĩa được quyền tạo Compute Engine VM trực tiếp. Controller có thể có service identity riêng để autoscale, còn job chạy dưới Linux user và/hoặc service account thích hợp với dữ liệu của nhóm.

### 14.1. Các kiểm soát nền tảng

- Dùng IAM tối thiểu và phân chia controller SA, login access, compute node SA và admin.
- Ưu tiên OS Login/IAP và private IP khi có thể; hạn chế SSH công khai.
- Không lưu service account JSON key trong home directory, job script hoặc shared filesystem.
- Bảo vệ MUNGE secret và thông tin SlurmDBD/database; bảo đảm cluster nodes tin cậy.
- Tách project/account cho nghiên cứu nhạy cảm hoặc có yêu cầu compliance riêng.
- Pin base VM image và packages; thực hiện patching, vulnerability scan, cập nhật driver có kiểm thử.
- Xác minh users/groups và ACLs trên Filestore/Lustre, không phụ thuộc riêng vào “network nội bộ”.
- Đặt retention/audit cho logs và dữ liệu nghiên cứu; tránh ghi secret/data PII vào stdout.
- Hạn chế người có quyền `scontrol update`, `sacctmgr` và sửa blueprint.

### 14.2. Dữ liệu và việc cấp quyền cho job

Với job cần truy cập Cloud Storage, dùng attached service account/metadata-based credentials theo cấu hình VM và SDK (Application Default Credentials) khi phù hợp, hạn chế bucket/prefix theo nhu cầu. Không đặt token truy cập tĩnh vào script `sbatch`. Đánh giá kỹ **mọi job trên một node có thể có cùng quyền cloud metadata identity** nếu thiết kế không cách ly; không dùng chung node cho các nhóm có mức nhạy cảm khác nhau khi không có biện pháp kiểm soát tương ứng.

## 15. Kế toán tài nguyên, quota và chi phí

Đối với Cloud HPC, chi phí cần nhìn theo **job và toàn bộ vòng đời cluster**, không chỉ thời gian chạy code.

~~~text
Chi phí HPC ≈
  Compute nodes (VM/GPU + boot disk + local SSD nếu có)
  + Controller/login/static nodes
  + Shared filesystem và capacity tối thiểu
  + Network egress/NAT/inter-zone traffic
  + Cloud Storage, logs, Monitoring
  + Reservation/commitment/Spot tuỳ lựa chọn
  + Công sức quản trị, backup và nâng cấp
~~~

Ví dụ giả định: bốn VM mỗi máy 4 vCPU chạy 20 phút tạo tổng:

~~~text
Tổng VM-runtime = 4 node × (20 / 60 giờ) = 1,33 VM-giờ
Tổng vCPU-time  = 4 node × 4 vCPU × (20 / 60 giờ) = 5,33 vCPU-giờ
~~~

**Đây không phải báo giá.** Giá thực tế phụ thuộc machine type, region, Spot/on-demand/reservation, memory/disk, cách tính phí và các tài nguyên phụ. Kiểm tra bảng giá Compute Engine và Pricing Calculator tại thời điểm triển khai.

### 15.1. Phân biệt chi phí VM và chi phí chờ queue

Một job `PENDING` không tự phát sinh **compute-node running time** nếu node chưa được tạo, nhưng cluster vẫn có controller/login/storage phí duy trì. Khi controller gọi tạo VM, bắt đầu có tài nguyên tính phí ngay cả trước khi script job chạy. Khi job kết thúc, thời gian chờ suspend/delete hoặc shared nodes nhàn rỗi vẫn ảnh hưởng chi phí.

Một cách đo hợp lý:

~~~text
Job effective cost ≈ tài nguyên đã phân bổ × runtime/cost rate
                      + phần overhead cluster phân bổ
                      + storage/network/logging liên quan
~~~

Slurm `sacct` có thể ghi CPU allocated và elapsed time, nhưng không tự biết toàn bộ giá Google Cloud, discounts, storage và egress. Muốn showback/chargeback, cần ghép accounting với Cloud Billing export, resource labels và quy tắc phân bổ cluster shared cost.

### 15.2. Các lớp guardrail

| Lớp | Biện pháp | Không thay thế được |
|---|---|---|
| Slurm job | MaxTime, MaxJobs, MaxSubmitJobs, QOS, fair-share, arrays cap | Google Cloud CPU/GPU quota |
| Nodeset | Max dynamic node count, machine type, zone | Budget hoặc thực tế capacity |
| GCP project | Quota CPU/GPU, IAM, org policies, budgets | Slurm user/account fairness |
| Billing | Budget alert, billing export và cost dashboards | Hard spending cap mặc định |
| Application | Checkpoint, timeout, memory profiling | Cluster scheduling policy |

Google Cloud budget alert **không** tự động ngăn chi tiêu. Việc tắt API/project theo một ngưỡng chi phí có thể làm hỏng job và mất dữ liệu; nếu cần auto-remediation phải thiết kế, diễn tập và được phê duyệt.

## 16. Observability: đo cả queue, VM và kết quả khoa học

Một hệ thống Slurm tốt cần nhiều tín hiệu hơn “mọi VM đều xanh”:

| Loại chỉ số | Cần theo dõi |
|---|---|
| Queue | Pending jobs theo partition/account, pending age p95, reason histogram |
| Scheduling | Job start latency, backfill, preemption, QOS rejections |
| Runtime | Job success/fail/timeout/OOM, walltime versus requested |
| Compute | VM active, boot time, node idle, CPU/GPU utilization |
| Filesystem | Throughput, metadata IOPS, capacity, mount error |
| Network | MPI latency/bandwidth, error/retransmit, connection saturation |
| Spend | VM-hours/GPU-hours, node idle cost, shared storage cost |
| Controller | `slurmctld` health, queue depth, sync errors, disk/database |

Các dữ liệu Slurm có thể thu qua job accounting, logs, exporters hoặc các công cụ hiện diện trong deployment; **không phải mọi metric đều có sẵn trong Cloud Monitoring ngay khi triển khai**. Cần cấu hình Ops Agent/monitoring agents, log filters, metrics và alert policies thích hợp với bản toolkit dùng.

### 16.1. Khi queue dài mà compute nhàn rỗi

Đây có thể là vấn đề matching chứ không phải thiếu máy:

- Job chỉ định sai partition/QOS/account.
- Job yêu cầu RAM, GPU hoặc số node không có trong nodeset nào.
- Job có hard dependency chưa đáp ứng.
- Nodes bị `DRAIN` hoặc filesystem/bootstrap lỗi.
- Quota/capacity của machine family bị giới hạn.
- Job yêu cầu 8 nodes cùng lúc nhưng chỉ có 7 node khả dụng.
- Affinity/constraint/feature làm thu hẹp tập node đủ điều kiện.

Hãy xem `scontrol show job` trước, rồi tới `sinfo`, controller logs và Compute Engine operations; không tự sửa `slurm.conf` production để “thử”.

## 17. Sổ tay xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Hành động |
|---|---|---|
| Job luôn `PD (Priority)` | Fair-share hoặc queue priority | Xem `sprio`, lịch chạy, policy account |
| `PD (Resources)` kéo dài | Không đủ resources/eligible nodes | So resource request với nodesets và GCP quota |
| `PD (Dependency)` | Job upstream chưa xong | Xem dependency và trạng thái upstream |
| Node `DOWN` hoặc `DRAIN` | Bootstrap, mount, network, Slurm daemon | `sinfo -R`, `slurmd` logs, Compute VM serial console |
| Resume VM thất bại | IAM, zone capacity, quota, API, image | Compute Engine operations, controller resume logs |
| Job bị `OOM` | Đặt `--mem` thấp hoặc memory leak | Peak RSS, profile, chọn node RAM cao hơn |
| Job chạy lâu hơn dự tính | CPU throttling, I/O, MPI inefficiency | Profiling, filesystem/network metrics |
| Job fail sau Spot preemption | Thiếu checkpoint/requeue phù hợp | Thiết kế restart state, retry có giới hạn |
| `sacct` không có dữ liệu | Accounting DB/SlurmDBD chưa cấu hình | Kiểm tra config, quyền, retention |
| Chi phí cao dù không có job | Controller/login/shared FS/static nodes | Billing theo SKU, node idle, suspend policy |
| Filesystem bị đầy | Checkpoint/log/output nhiều | Quota FS, cleanup theo retention đã phê duyệt |
| User truy cập data team khác | Linux ACL, SA IAM hoặc shared node permissions | Kiểm tra UID/GID, mount ACL, service identity |

**Không xóa VM thủ công trong một partition active** chỉ vì thấy VM idle ở Google Cloud Console: Slurm state và VM lifecycle có thể lệch, khiến job mất node hoặc sinh orphan resources. Dùng quy trình pause/drain/reconfigure của Slurm và Cluster Toolkit đã được duyệt.

## 18. Lab: triển khai và quan sát hàng đợi có giới hạn chi phí

Lab gợi ý trong **project HPC riêng** có quota nhỏ, budget alert và thời gian thực hành hữu hạn.

### Bước 1 — Chuẩn bị

- Xác định project, zone, loại VM và quota thực tế.
- Xác nhận người thao tác có quyền deploy IaC và chỉ được dùng cluster lab.
- Chọn blueprint Slurm mẫu phiên bản đã pin.
- Xem cấu hình controller/login/shared storage; ghi dự toán trước khi deploy.

### Bước 2 — Generate và review

~~~bash
./gcluster explain examples/hpc-slurm.yaml

./gcluster create examples/hpc-slurm.yaml \
  -l ERROR --vars project_id=HPC_LAB_PROJECT_ID

# Chỉ deploy khi đã review Terraform plan và được phê duyệt.
./gcluster deploy hpc-slurm
~~~

Không bỏ qua cảnh báo về Filestore capacity, network resources hoặc quotas. Một cluster có dynamic nodes vẫn tạo những tài nguyên chạy lâu dài.

### Bước 3 — Truy cập login node và nộp job test

Trong quickstart chính thức, dùng SSH-in-browser đến login VM do blueprint tạo. Sau khi Slurm hoàn tất bootstrap:

~~~bash
sinfo
squeue --me

# Chọn partition và số node phù hợp với blueprint thực tế.
srun -N 1 hostname
~~~

Nếu node dynamic ở trạng thái down/power-down, Slurm có thể kích hoạt VM. Quan sát khoảng thời gian từ `srun` đến lúc hostname trả về để đo startup latency.

### Bước 4 — Thực hành job batch và array

- Tạo thư mục `logs/` trước.
- Nộp script `hello.sbatch` và xem `squeue`.
- Nộp `sweep.sbatch` với `--array=0-15%4`.
- Dùng `sacct` nếu accounting đã bật; ghi number of completed, timeout, fail.
- Thử giới hạn `--time` nhỏ hơn runtime **chỉ trên job lab**, quan sát trạng thái `TIMEOUT` và xử lý.

### Bước 5 — Kiểm tra quota, fairness và cost

- Quan sát số VM Compute Engine được tạo đồng thời.
- So sánh số job chạy với giới hạn array và nodeset max.
- Ghi thời gian boot, running/idle và thói quen auto-delete.
- Không tăng quota hoặc instance size chỉ để chứng minh scaling nếu lab budget nhỏ.
- Dùng Cloud Billing report sau khi dữ liệu chi phí được cập nhật để so chi phí thực tế với ước tính.

### Bước 6 — Dọn tài nguyên

Trước khi hủy cluster, xác minh các job không còn chạy và output cần giữ đã được stage-out:

~~~bash
squeue --me
# Dừng/hủy job lab thuộc sở hữu của bạn nếu cần.
# scancel JOB_ID
~~~

Sau khi compute nodes được thu hồi, có thể dùng lệnh trong quickstart:

~~~bash
# CHỈ cho cluster lab riêng; thao tác phá hạ tầng.
./gcluster destroy hpc-slurm --auto-approve
~~~

`gcluster destroy` xóa hạ tầng đang được quản lý bởi deployment. Kiểm tra kế hoạch destroy và danh sách tài nguyên thực tế trước khi chạy; **không áp dụng cho cluster dùng chung hoặc production**. Kiểm tra VM, disk, shared filesystem, load balancer/IP, bucket và Billing sau cleanup; có thể còn artifact/dữ liệu/backup theo retention cần xử lý riêng.

## 19. Bài tập kiến trúc: ba nhóm nghiên cứu

Giả sử một tổ chức có:

- **Nhóm A:** 50.000 case mô phỏng độc lập, mỗi case 1 CPU, 2 GB, khoảng 3 phút.
- **Nhóm B:** MPI job 32 nodes, cần network latency thấp, walltime 2 giờ.
- **Nhóm C:** GPU training lâu, có checkpoint và chấp nhận bị ngắt.

Thiết kế ít nhất ba partition/nodeset phù hợp, ví dụ CPU array, MPI và Spot GPU. Hãy nêu:

1. Job submission syntax cho mỗi loại, gồm tài nguyên và walltime.
2. Cách giới hạn concurrency của nhóm A để không làm nghẽn scheduler hoặc filesystem.
3. Quy tắc fairness/QOS giữa ba nhóm.
4. Tại sao nhóm B cần topology/capacity, và khi nào reservation hữu ích.
5. Chu kỳ checkpoint và đường stage-out cho nhóm C.
6. Quota GCP và resource limits phải kiểm tra trước khi cấp tối đa nodeset.
7. Chi phí luôn-on của controller/login/filesystem và cách chia cho các nhóm.
8. Nguồn metrics/log để phát hiện pending quá lâu, node idle và job fail.

**Gợi ý:** Chỉ tăng node count sau khi biết CPU utilization và time-to-start. Với nhóm A, job array `--array=0-49999%64` giới hạn concurrency của **một array** ở 64 tasks nếu `MaxArraySize`/cluster limits cho phép; không nhất thiết nên nộp 50.000 tasks trong một lần. Chia batch nhỏ và giới hạn input I/O có thể phù hợp hơn. Với nhóm B, không sử dụng Spot nếu mất một node khiến toàn bộ MPI job phải chạy lại và không có checkpoint hữu hiệu.

## 20. Câu hỏi tự kiểm tra

1. Slurm giải quyết vấn đề gì mà Cloud Tasks hoặc Pub/Sub không thay thế trực tiếp?
2. Phân biệt controller, login node và compute node.
3. Nodeset khác partition trong Cluster Toolkit thế nào?
4. Vì sao `node_count_dynamic_max: 8` không bảo đảm chạy được 8 VM?
5. `sbatch` và `srun` dùng khác nhau ở đâu?
6. `--array=0-15%4` có giới hạn tất cả job của cluster ở 4 task không?
7. Khi job `PENDING` lâu, cần phân biệt ba loại giới hạn nào?
8. Vì sao `exclusive=true` có thể khiến node dynamic bị xóa ngay sau job?
9. Tại sao login node không nên chạy mô phỏng lớn?
10. Cần điều gì để `sacct` có lịch sử job hữu ích?
11. Fair-share và QOS có giải quyết được thiếu GPU capacity trong zone không?
12. Một checkpoint chỉ nằm trên local disk của Spot VM có an toàn không?
13. Cloud Storage FUSE có giống filesystem POSIX trong mọi tác vụ MPI không?
14. Tại sao autoscaling Slurm không làm controller và shared FS miễn phí?
15. Những yếu tố nào cần đo khi MPI scale kém dù đã tăng node?

**Đáp án gợi ý**

1. Slurm sắp xếp các job HPC yêu cầu CPU/GPU/memory/node cùng lúc, cấp allocation, ưu tiên, accounting và batch lifecycle; Pub/Sub/Cloud Tasks chủ yếu truyền hoặc lên lịch thực thi message/task.
2. Controller scheduling, login để người dùng chuẩn bị/nộp job, compute chạy workload.
3. Nodeset mô tả nhóm compute node cấu hình tương tự; partition nhóm nodesets và áp policy scheduling.
4. Đây chỉ là giới hạn config; Google Cloud còn quota, available capacity, IAM, topology và network.
5. `sbatch` nộp batch script vào queue; `srun` chạy job step trong allocation hoặc yêu cầu allocation tương tác theo ngữ cảnh.
6. Không. Chỉ giới hạn số task đồng thời của array này; account/QOS/cluster còn các giới hạn khác.
7. Slurm scheduling/limits, Google Cloud quotas, Google Cloud physical capacity/availability.
8. Theo module partition, exclusive dynamic nodes có thể bị delete ngay sau khi job hoàn tất, thay vì chờ `suspend_time`.
9. Không được cấp phát/accounting qua scheduler và có thể chiếm resources dành cho login.
10. Slurm accounting service/database phải được cấu hình và ghi dữ liệu, quyền truy vấn/retention phù hợp.
11. Không. Scheduler policy không sinh ra GPU hardware ngoài quota và capacity.
12. Không; node có thể bị thu hồi, phải stage-out/checkpoint lên shared/durable storage.
13. Không. Object semantics, consistency, metadata latency và behavior khác POSIX; phải benchmark ứng dụng.
14. Vì controller/login/static capacity, shared filesystem, disk, network vẫn chạy và có phí.
15. MPI collectives latency, placement/network bandwidth, data partition, synchronization và filesystem I/O.

## Kết luận

Slurm trên Google Cloud cung cấp một cơ chế quen thuộc để tổ chức hàng đợi HPC trong khi Compute Engine có thể cấp phát tài nguyên động theo nhu cầu. Thiết kế tốt phải **gắn nhu cầu job với nodeset/partition, Slurm fairness/QOS với quota cloud, và autoscaling với bảo vệ dữ liệu/cost**. Một cluster chạy được `srun hostname` mới chứng minh đường điều phối cơ bản; vận hành đáng tin cần thêm benchmark ứng dụng, accounting, shared filesystem phù hợp, checkpoint, bảo mật, quan sát queue và quy trình dọn tài nguyên.

## Tài liệu tham khảo

- [Google Cloud — Cluster Toolkit overview](https://docs.cloud.google.com/cluster-toolkit/docs/overview)
- [Google Cloud — Deploy an HPC cluster with Slurm](https://docs.cloud.google.com/cluster-toolkit/docs/quickstarts/slurm-cluster)
- [Google Cloud — Set up Cluster Toolkit](https://docs.cloud.google.com/cluster-toolkit/docs/setup/configure-environment)
- [Google Cloud — Create a nodeset for a Slurm partition](https://docs.cloud.google.com/cluster-toolkit/docs/modules/slurm-nodeset)
- [Google Cloud — Create a Slurm partition](https://docs.cloud.google.com/cluster-toolkit/docs/modules/slurm-partition)
- [Google Cloud — Slurm TPU deployments overview](https://docs.cloud.google.com/cluster-toolkit/docs/deploy/slurm/slurm-tpu-overview)
- [Google Cloud — Demand scaling overview](https://docs.cloud.google.com/docs/compute-area/scale-overview)
- [Google Cloud — Overview of HPC clusters](https://docs.cloud.google.com/compute/docs/hpc/overview-hpc-clusters)
- [Google Cloud — Choose compute options](https://docs.cloud.google.com/docs/compute-area/choose-compute-options)
- [Google Cloud — Cluster Toolkit release notes](https://docs.cloud.google.com/cluster-toolkit/docs/release-notes)
- [Slurm — sbatch command](https://slurm.schedmd.com/sbatch.html)
- [Slurm — Job arrays](https://slurm.schedmd.com/job_array.html)
- [Slurm — Quality of Service (QOS)](https://slurm.schedmd.com/qos.html)
- [Slurm — Slurm commands overview](https://slurm.schedmd.com/quickstart.html)
- [Google Cloud — Compute Engine quotas](https://docs.cloud.google.com/compute/quotas)
- [Google Cloud — Cloud Billing budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Google Cloud — Pricing Calculator](https://cloud.google.com/products/calculator)

