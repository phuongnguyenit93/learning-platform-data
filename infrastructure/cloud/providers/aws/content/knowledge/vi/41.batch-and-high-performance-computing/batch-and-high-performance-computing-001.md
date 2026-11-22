# Lựa chọn EC2, ECS, EKS hoặc AWS Batch cho xử lý theo lô

Xử lý theo lô (batch processing) là cách thực thi công việc trên một tập dữ liệu hoặc một nhóm tác vụ rồi kết thúc khi hoàn thành. Ví dụ gồm chuyển đổi dữ liệu ban đêm, tạo báo cáo, xử lý ảnh/video, mô phỏng Monte Carlo, render, tính giá, ETL, phân tích log và huấn luyện mô hình. Workload có thể chạy vài giây, vài giờ hoặc nhiều ngày; có thể là một tiến trình độc lập, hàng nghìn job song song hoặc một phép tính HPC phân tán trên nhiều máy.

Trên AWS, bốn lựa chọn thường được cân nhắc là Amazon EC2, Amazon ECS, Amazon EKS và AWS Batch. Đây không phải bốn dịch vụ cùng một lớp: EC2 cung cấp máy tính; ECS và EKS điều phối container; AWS Batch quản lý hàng đợi và lịch chạy batch job, sau đó sử dụng compute environment dựa trên EC2, Fargate, ECS Managed Instances hoặc EKS. Hiểu đúng vai trò của từng lớp giúp tránh tự xây dựng scheduler khi không cần, đồng thời tránh chọn nền tảng quá phức tạp cho một tác vụ đơn giản.

Bài học đi từ cách phân loại workload, so sánh mô hình, chọn compute và scheduler đến storage, network, IAM, retry, Spot, HPC, chi phí và vận hành. Mục tiêu là chọn được kiến trúc phù hợp với độ song song, độ dài job, yêu cầu phần cứng, khả năng chịu gián đoạn và năng lực vận hành của tổ chức.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt batch, scheduled task, long-running service, stream processing và HPC.
- Giải thích vai trò của EC2, ECS, EKS và AWS Batch trong kiến trúc xử lý theo lô.
- Chọn EC2 trực tiếp khi cần kiểm soát hệ điều hành, phần cứng, network hoặc scheduler riêng.
- Chạy một-off và scheduled container task bằng ECS RunTask và EventBridge Scheduler.
- Chọn Kubernetes Job/CronJob trên EKS và hiểu cách cấp phát node bằng Karpenter hoặc Cluster Autoscaler.
- Thiết kế AWS Batch với job definition, job queue, compute environment và scheduling policy.
- Chọn EC2 On-Demand/Spot, Fargate/Fargate Spot hoặc ECS Managed Instances cho Batch.
- Hiểu AWS Batch trên EKS là mô hình orchestration overlay và các giới hạn compute.
- Sử dụng retry, timeout, dependency, array job, fair-share, resource-aware scheduling và multi-node parallel job.
- Thiết kế HPC với MPI, EFA, cluster placement group, GPU và shared storage.
- Bảo vệ workload bằng IAM roles, VPC, security groups, KMS và secret management.
- Theo dõi queue, job, pod, task, instance, log và chi phí.
- Thiết kế job idempotent, checkpoint, recovery, backpressure và quy trình dọn tài nguyên.

## 2. Hiểu đúng workload trước khi chọn dịch vụ

Không phải workload chạy trong container đều là batch. Trước khi chọn dịch vụ, hãy xác định công việc được kích hoạt thế nào, kéo dài bao lâu, có cần duy trì liên tục không và có quan hệ phụ thuộc giữa các job hay không.

### 2.1 Các dạng workload

| Dạng workload | Đặc điểm | Ví dụ |
|---|---|---|
| One-off task | Chạy một lần rồi kết thúc | Chuyển một file, tạo báo cáo ad-hoc |
| Scheduled batch | Chạy theo giờ/ngày/tháng hoặc lịch nghiệp vụ | ETL lúc 02:00, tổng hợp cuối ngày |
| Queue-driven batch | Có việc mới thì đưa vào queue, worker lấy xử lý | Resize ảnh, xử lý hóa đơn |
| Large-scale parallel batch | Nhiều job độc lập chạy đồng thời | Monte Carlo, render hàng triệu frame |
| Dependency pipeline | Job sau chỉ chạy khi job trước thành công | Extract → transform → publish |
| Long-running service | Luôn duy trì một số instance để nhận request | API, worker service liên tục |
| Stream processing | Xử lý event liên tục, stateful hoặc stateless | Fraud stream, telemetry |
| HPC tightly coupled | Nhiều node trao đổi dữ liệu liên tục với latency thấp | MPI simulation, computational fluid dynamics |

Một ECS service duy trì desired count phù hợp với service dài hạn. Một ECS standalone task phù hợp với tiến trình chạy xong rồi dừng. AWS Batch bổ sung queue, dependency, retry và capacity scheduling cho workload batch. Kubernetes Job/CronJob cung cấp primitive batch trên EKS; nếu cần multi-tenant queue/fair-share, cần thêm scheduler hoặc dùng AWS Batch trên EKS.

### 2.2 Đặc tính cần thu thập

| Thuộc tính | Câu hỏi |
|---|---|
| Trigger | Người dùng gọi, message đến, lịch chạy hay pipeline kích hoạt? |
| Arrival rate | Bao nhiêu job mỗi phút/giờ/ngày? Có burst không? |
| Parallelism | Mỗi job độc lập hay cần nhiều node chạy đồng thời? |
| Duration | P50/P95/P99 runtime là bao lâu? |
| Resource profile | CPU, RAM, GPU, disk, network và accelerator cần bao nhiêu? |
| Interruption tolerance | Có thể dừng giữa chừng rồi chạy lại không? |
| Dependency | Có thứ tự hoặc điều kiện giữa các job không? |
| Latency/SLA | Job phải bắt đầu trong bao lâu và hoàn thành trước deadline nào? |
| Data locality | Dữ liệu ở S3, EFS, FSx, EBS hay database? |
| Isolation | Tenant có cần kernel, node, network hoặc IAM isolation riêng? |
| Operations | Đội ngũ có kỹ năng EC2, Docker, ECS, Kubernetes hay HPC scheduler? |
| Cost model | Tối ưu theo thời gian chạy, utilization, license hay chi phí vận hành? |

### 2.3 Batch và HPC khác nhau ở đâu?

Batch mô tả cách tổ chức công việc: nhận input, chạy, ghi output và kết thúc. HPC mô tả loại tính toán có yêu cầu hiệu năng cao, thường dùng nhiều CPU/GPU, memory bandwidth, network tốc độ cao hoặc storage song song. Một workload HPC có thể được submit như batch job.

Hai nhóm HPC thường gặp:

- **Loosely coupled/embarrassingly parallel:** mỗi task xử lý một phần dữ liệu độc lập; có thể chạy hàng trăm hoặc hàng nghìn container/instance.
- **Tightly coupled:** các node phải trao đổi dữ liệu thường xuyên, ví dụ MPI; cần network latency/bandwidth cao và khả năng khởi động nhiều node cùng lúc (gang scheduling).

Loại thứ nhất phù hợp với array jobs hoặc queue-driven workers. Loại thứ hai cần multi-node parallel job, placement strategy và có thể cần EFA.

## 3. Bốn lớp kiến trúc: compute, orchestration, scheduling và workflow

Một kiến trúc batch có thể tách thành bốn lớp:

    Event / Schedule / API / Message
                 |
          Workflow / Queue
                 |
          Batch Scheduler
                 |
       Container / Process Runtime
                 |
       Compute Capacity (EC2/Fargate)
                 |
        S3 / EFS / FSx / Database

| Lớp | Trách nhiệm | Dịch vụ hoặc thành phần |
|---|---|---|
| Trigger | Quyết định khi nào có việc | EventBridge Scheduler, SQS, API, Step Functions |
| Workflow | Điều phối thứ tự, timeout, branch, approval | Step Functions, MWAA, custom orchestrator |
| Batch scheduler | Queue, priority, dependency, retry, capacity allocation | AWS Batch hoặc Kubernetes batch scheduler |
| Container orchestration | Placement và lifecycle container | ECS hoặc Kubernetes trên EKS |
| Compute | CPU, RAM, GPU, network và disk | EC2, Fargate, ECS Managed Instances |
| Storage | Input, output, checkpoint và shared data | S3, EBS, EFS, FSx for Lustre |

EC2 là compute substrate. ECS/EKS điều phối container. AWS Batch là batch scheduler và capacity manager. EventBridge Scheduler kích hoạt tác vụ theo thời gian; Step Functions điều phối quy trình nhiều bước. Một dịch vụ có thể tích hợp nhiều lớp, nhưng không nên gán trách nhiệm scheduler cho EC2 hoặc cho ECS service scheduler.

## 4. So sánh EC2, ECS, EKS và AWS Batch

| Tiêu chí | EC2 trực tiếp | ECS | EKS | AWS Batch |
|---|---|---|---|---|
| Vai trò chính | Máy ảo/compute | Container orchestration do AWS quản lý | Kubernetes managed control plane | Batch job queue, scheduler và capacity orchestration |
| Đơn vị thực thi | Process, VM, container tự quản | Task hoặc service | Pod, Job, CronJob | Job, array job, MNP job hoặc service job |
| Scheduler | Tự xây hoặc cài Slurm/engine | ECS task placement; RunTask/Service | Kubernetes scheduler/controller | Batch scheduler: FIFO, fair-share, priority, dependency |
| Compute | EC2 On-Demand/Spot | EC2, Fargate, Fargate Spot | Node EC2; có thể dùng các mô hình node khác theo workload | EC2, Fargate, ECS Managed Instances; EKS compute environment dùng EC2 |
| Queue/retry/dependency | Tự xây | Tự tích hợp SQS/Step Functions hoặc logic riêng | Kubernetes Job retry; queue nâng cao cần thành phần bổ sung | Có sẵn job queue, retry, dependency, fair-share |
| Autoscaling | Auto Scaling Group/EC2 Fleet | Capacity provider và Service Auto Scaling | Karpenter/Cluster Autoscaler/HPA theo lớp | Scheduler điều chỉnh compute environment theo queue demand |
| HPC/MPI | Kiểm soát cao nhất | Có thể chạy task, nhưng cần tự điều phối nhiều node | Có thể dùng MPI operator/queue và EC2 node | MNP, GPU, EFA trên EC2 compute environments |
| Độ tùy chỉnh | Rất cao | Trung bình đến cao | Rất cao, Kubernetes API/ecosystem | Tập trung vào batch; tùy chỉnh qua compute environment/job definition |
| Độ phức tạp vận hành | Quản lý OS, patch, scaling, scheduler | Quản lý cluster/capacity và task | Quản lý Kubernetes, node, CNI, add-on, scheduler | Quản lý queue, CE, job definition, IAM và underlying capacity policy |
| Khi phù hợp | Legacy, custom OS, HPC, scheduler chuyên biệt | Container one-off/scheduled task hoặc service đơn giản | Nền tảng Kubernetes dùng chung, policy và ecosystem phong phú | Nhiều batch job, queue, dependency, fair-share, retry và scale theo nhu cầu |

### 4.1 Quy tắc chọn nhanh

- Chọn EC2 trực tiếp khi cần toàn quyền kiểm soát máy, driver, kernel, AMI, EFA, license daemon hoặc scheduler HPC riêng.
- Chọn ECS khi ứng dụng đã đóng gói container, số tác vụ vừa phải, cần chạy một lần hoặc theo lịch, và không cần queue scheduler chuyên biệt.
- Chọn EKS khi tổ chức đã vận hành Kubernetes, cần chuẩn hóa workload container theo Kubernetes API, hoặc cần operator/CRD và ecosystem của Kubernetes.
- Chọn AWS Batch khi cần quản lý hàng đợi, ưu tiên, phụ thuộc, retry, array job, multi-node parallel job và tự cấp phát compute theo nhu cầu.

AWS Batch không thay thế EC2/ECS/EKS. Batch dùng các nền tảng đó để chạy job. ECS service scheduler cũng không thay thế Batch scheduler: service giữ số task dài hạn; Batch quản lý các đơn vị công việc hữu hạn.

## 5. EC2 trực tiếp cho xử lý theo lô

EC2 phù hợp khi ứng dụng cần quyền kiểm soát sâu về hệ điều hành, thiết bị, filesystem, network, daemon hoặc phần mềm thương mại. Tuy nhiên, EC2 chỉ cấp máy; người vận hành phải giải quyết việc nhận job, xếp hàng, cấp capacity, retry, checkpoint, cleanup và quan sát.

### 5.1 Kiến trúc đơn giản

    EventBridge / SQS
          |
       Worker ASG
          |
       EC2 instance
          |
       Process / script / container
          |
       S3 / EFS / FSx / database

Một worker có thể poll SQS, nhận message, tải input, chạy process, ghi output và xác nhận message. Auto Scaling Group tăng/giảm số worker theo queue depth hoặc metric custom. Cần xử lý visibility timeout, duplicate message, DLQ, graceful shutdown và idempotency.

### 5.2 Khi nên dùng EC2 trực tiếp

- Phần mềm yêu cầu custom AMI, kernel module, driver hoặc package hệ điều hành.
- Cần GPU, EFA, NVMe local instance store hoặc phần cứng đặc thù.
- Cần license daemon, process chạy lâu hoặc nhiều tiến trình chia sẻ bộ nhớ trên cùng máy.
- Cần scheduler HPC như Slurm qua AWS ParallelCluster hoặc hệ thống nội bộ.
- Cần placement group và cấu hình network/storage sâu.
- Có đội ngũ đủ năng lực quản lý patch, image, capacity, failure và lifecycle.

### 5.3 Chọn instance family

| Loại workload | Instance/resource nên benchmark |
|---|---|
| CPU-bound | Compute optimized (C) |
| Memory-bound | Memory optimized (R/X/U theo nhu cầu) |
| General-purpose | M |
| GPU training/inference/rendering | Accelerated computing (G/P/Trn/Inf theo framework) |
| High network throughput | Network-optimized, EFA nếu MPI/tightly coupled |
| High local I/O | Instance store/NVMe hoặc EBS tối ưu IOPS/throughput |

Không chọn theo vCPU đơn lẻ. Đo CPU utilization, memory pressure, page cache, disk queue, network, GPU utilization, runtime và cost per job.

### 5.4 Tự xây scheduler cần những gì?

Nếu chạy EC2 mà tự xây batch platform, cần ít nhất:

- Job registry và trạng thái QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED.
- Queue và cơ chế lease/visibility timeout.
- Resource reservation để không overcommit CPU/RAM/GPU.
- Worker heartbeat và phát hiện node mất.
- Retry policy, backoff và dead-letter queue.
- Idempotency key và output commit.
- Priority/fair-share để tenant không chiếm hết capacity.
- Scaling policy và capacity warm-up.
- Audit, metrics, logs và cost allocation.
- Cleanup process cho instance, volume, ENI, artifact và temporary data.

Nếu phải tự triển khai phần lớn danh sách này, hãy đánh giá AWS Batch trước khi đầu tư scheduler riêng.

### 5.5 Spot trên EC2

EC2 Spot tận dụng capacity chưa được sử dụng và có thể giảm chi phí đáng kể. AWS có thể thu hồi Spot instance; interruption notice thường cung cấp khoảng hai phút trước khi stop/terminate, nhưng event được gửi theo best effort.

Thiết kế workload chịu interruption:

- Lưu checkpoint thường xuyên vào S3/EFS/FSx hoặc storage bền vững.
- Chia job thành chunk có thể chạy lại.
- Ghi tiến độ theo task ID/partition.
- Commit output theo run ID, không ghi đè kết quả chưa hoàn chỉnh.
- Lắng nghe EventBridge interruption/rebalance event.
- Có thể đa dạng instance type và Availability Zone.
- Dùng On-Demand cho phần cần ổn định và Spot cho phần có thể retry.

Không dùng Spot cho tiến trình không thể phục hồi hoặc có side effect không idempotent nếu chưa có cơ chế bảo vệ.

## 6. Amazon ECS cho one-off và scheduled container tasks

Amazon ECS là container orchestration service do AWS quản lý. ECS task là một lần chạy task definition; ECS service duy trì một số task mong muốn. Với batch đơn giản, dùng standalone task qua RunTask hoặc EventBridge Scheduler để chạy task theo lịch.

### 6.1 Task definition, task và service

| Khái niệm | Vai trò |
|---|---|
| Task definition | Blueprint: image, command, CPU, memory, volumes, ports, roles và logging |
| Task | Một lần instantiate task definition |
| Standalone task | Chạy độc lập, kết thúc khi công việc hoàn tất |
| ECS service | Duy trì desired count và thay thế task bị dừng/lỗi |
| Cluster | Nhóm logic chứa task/service và capacity |
| Capacity provider | Liên kết ECS với EC2 Auto Scaling hoặc Fargate/Fargate Spot |

Không dùng ECS service chỉ để chạy job rồi kết thúc. Service scheduler được thiết kế để duy trì desired count; nếu task thoát sau khi xử lý xong, service có thể tạo task thay thế và chạy lặp. Với batch một lần, dùng RunTask.

### 6.2 ECS standalone task

Luồng thực thi:

    Event / SQS / API / EventBridge Scheduler
                   |
                RunTask
                   |
             ECS cluster
                   |
          Capacity provider
             /          \
          Fargate       EC2
             \          /
              ECS task
                  |
          Application exits
                  |
             Task STOPPED

ECS placement dựa trên CPU/memory trong task definition, placement constraints và strategy. Với Fargate, AWS quản lý compute cho task. Với EC2, có thể tự đăng ký instance hoặc dùng capacity provider với cluster auto scaling để thêm/bớt capacity.

### 6.3 Chạy theo lịch bằng EventBridge Scheduler

EventBridge Scheduler hỗ trợ lịch một lần, rate-based và cron-based, có thể chọn timezone. Scheduler có thể gọi ECS RunTask làm target. Một schedule nên cấu hình:

- Target cluster và task definition revision.
- Launch type/capacity provider strategy.
- Network configuration và subnet/security group.
- Task count và container overrides.
- Execution role của Scheduler để gọi RunTask.
- Retry policy, maximum event age và dead-letter queue nếu cần.
- Flexible time window nếu không cần chạy chính xác tại một giây.

Nếu task phụ thuộc dữ liệu đầu vào hoặc cần nhiều bước, dùng Step Functions hoặc một workflow engine để quản lý state và lỗi. EventBridge Scheduler chỉ phát lệnh chạy theo lịch; nó không cung cấp đầy đủ job dependency graph và fair-share queue như AWS Batch.

### 6.4 Capacity providers

ECS hỗ trợ các capacity provider phổ biến:

- **Fargate:** không quản lý EC2 instance; task yêu cầu CPU/memory theo cấu hình Fargate.
- **Fargate Spot:** capacity giá thấp hơn nhưng có thể bị gián đoạn; phù hợp batch có thể retry.
- **EC2 capacity provider:** liên kết Auto Scaling Group và hỗ trợ cluster auto scaling.

Capacity provider strategy có thể phối hợp On-Demand và Spot theo base/weight. Chọn strategy để phần công việc quan trọng có capacity ổn định, còn phần chịu interruption tận dụng Spot.

### 6.5 Task role và task execution role

Hai role có mục đích khác nhau:

- **Task execution role:** ECS/Fargate agent dùng để pull image từ ECR, ghi log và lấy secret được cấu hình trong task definition.
- **Task role:** credential được cấp cho code bên trong container để gọi S3, DynamoDB, SQS hoặc dịch vụ AWS khác.

Không cấp quyền ứng dụng vào execution role nếu không cần. Mỗi workload nên có task role riêng với least privilege. Nếu task chạy trong private subnet, cấu hình VPC endpoints hoặc NAT để truy cập ECR, CloudWatch, S3 và các dịch vụ cần thiết.

### 6.6 ECS không tự thay thế standalone task

ECS service scheduler thay task bị lỗi để giữ desired count. Nhưng standalone task được gọi bằng RunTask hoặc EventBridge Scheduler không tự được service scheduler tạo task thay thế khi task fail. Nếu cần retry, workflow phải gọi lại RunTask hoặc dùng AWS Batch.

### 6.7 Khi ECS là lựa chọn tốt

- Một task hoặc vài nhóm task chạy theo lịch.
- Workload không cần queue phức tạp hoặc fair-share.
- Đã có task definition và ECS cluster/capacity provider.
- Có thể dùng Fargate để giảm vận hành compute.
- Có thể để EventBridge Scheduler hoặc Step Functions điều phối retry/dependency.

Nếu bắt đầu cần quản lý hàng nghìn job, priority, queue, dependency và retry theo exit reason, AWS Batch thường phù hợp hơn.

## 7. Amazon EKS với Kubernetes Job và CronJob

Amazon EKS cung cấp Kubernetes control plane được quản lý. Kubernetes có primitive cho batch: Job chạy một hoặc nhiều Pod đến khi đạt số lần hoàn thành; CronJob tạo Job theo lịch.

### 7.1 Kubernetes Job

Một Job quản lý Pod để thực hiện công việc hữu hạn. Các trường thường dùng:

| Trường | Ý nghĩa |
|---|---|
| completions | Số lần hoàn thành thành công cần đạt |
| parallelism | Số Pod tối đa chạy đồng thời |
| backoffLimit | Số lần retry khi Pod thất bại |
| activeDeadlineSeconds | Giới hạn thời gian Job hoạt động |
| ttlSecondsAfterFinished | Thời gian giữ Job sau khi hoàn tất trước khi cleanup |
| restartPolicy | Thường là Never hoặc OnFailure tùy thiết kế |

Kubernetes Job controller theo dõi Pod và tạo Pod thay thế theo policy. Điều này không đồng nghĩa Job có queue toàn cục, fair-share hoặc quản lý quota nghiệp vụ giữa nhiều team.

### 7.2 Ví dụ Kubernetes Job

    apiVersion: batch/v1
    kind: Job
    metadata:
      name: image-resize
      namespace: batch
    spec:
      completions: 1
      parallelism: 1
      backoffLimit: 3
      activeDeadlineSeconds: 1800
      ttlSecondsAfterFinished: 3600
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: worker
              image: 123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/image-worker:1.4.2
              command: ["python", "resize.py"]
              resources:
                requests:
                  cpu: "1"
                  memory: "2Gi"
                limits:
                  cpu: "2"
                  memory: "4Gi"

Manifest là ví dụ khởi đầu; image, namespace, resource request/limit, service account và volume phải được điều chỉnh theo cluster. Container cần xử lý tín hiệu kết thúc và ghi output idempotent.

### 7.3 Kubernetes CronJob

CronJob tạo Job theo cron schedule. Các trường quan trọng:

- schedule: biểu thức cron.
- timeZone: timezone cho schedule nếu phiên bản Kubernetes hỗ trợ.
- concurrencyPolicy: Allow, Forbid hoặc Replace.
- startingDeadlineSeconds: thời gian tối đa cho phép khởi chạy trễ.
- successfulJobsHistoryLimit/failedJobsHistoryLimit: số Job giữ lại.
- suspend: tạm dừng lịch.

Nếu job trước có thể chạy lâu hơn khoảng cách giữa hai lần lịch, chọn concurrencyPolicy có chủ đích. Allow cho phép chồng lấn; Forbid bỏ qua lần mới khi job trước còn chạy; Replace kết thúc job cũ để tạo job mới. Không dùng Replace nếu job không chịu được termination.

### 7.4 Scheduling và autoscaling

Kubernetes scheduler đặt Pod lên node dựa trên requests, affinity/anti-affinity, taints/tolerations, topology spread và các ràng buộc khác. Để node capacity tăng theo pod pending, có thể dùng Karpenter hoặc Cluster Autoscaler.

Các lớp scaling khác nhau:

- HPA/KEDA điều chỉnh số Pod theo metric hoặc event.
- Karpenter/Cluster Autoscaler điều chỉnh node capacity.
- Kubernetes Job/CronJob điều khiển số lần chạy và số Pod song song.
- Queue/scheduler bổ sung điều khiển fairness, quota và priority ở cấp workload.

Không tăng parallelism mà không kiểm tra downstream capacity, database connection, API rate limit và S3 request pattern. Job fan-out quá lớn có thể làm nghẽn hệ thống nhận dữ liệu.

### 7.5 IAM cho Pod

Ứng dụng trong Pod cần IAM role qua EKS Pod Identity hoặc IAM Roles for Service Accounts (IRSA). Gắn role với Kubernetes service account và giới hạn quyền theo namespace/workload. Không gắn quyền rộng vào node instance role rồi để mọi Pod thừa hưởng.

### 7.6 Khi chọn EKS native Job/CronJob

- Tổ chức đã có Kubernetes platform và đội ngũ vận hành.
- Cần dùng Kubernetes API, admission policy, operator, service mesh hoặc ecosystem.
- Job có thể quản lý bằng manifest/GitOps.
- Cần tùy chỉnh pod scheduling, sidecar, init container, volume và network policy.
- Đã có queue/scheduler layer phù hợp hoặc workload không cần queue nâng cao.

Nếu mục tiêu chỉ là chạy vài batch job và không có yêu cầu Kubernetes, vận hành EKS cluster có thể tạo overhead lớn hơn giá trị nhận được.

## 8. AWS Batch: batch scheduler được quản lý

AWS Batch là dịch vụ quản lý việc lập lịch, xếp hàng và cấp phát compute cho batch jobs. Người dùng mô tả job và yêu cầu tài nguyên; Batch tìm compute environment phù hợp, chờ capacity nếu cần, chạy container và theo dõi trạng thái.

### 8.1 Bốn thành phần cốt lõi

| Thành phần | Trách nhiệm |
|---|---|
| Job definition | Blueprint của container/process: image, command, vCPU, memory, GPU, role, volume, logging và retry/timeout |
| Job queue | Nơi job chờ được scheduler đánh giá và xếp lịch |
| Compute environment (CE) | Compute resource để chạy job; managed hoặc unmanaged |
| Job | Một lần thực thi được submit vào queue |

Luồng cơ bản:

    Producer / Scheduler / Workflow
                  |
               SubmitJob
                  |
               Job queue
                  |
            Batch scheduler
                  |
          Compute environment
           /              \
       ECS platform       EKS platform
       EC2/Fargate/        EC2 nodes
       ECS Managed         and Pods
       Instances
           \              /
             Container job
                  |
              S3 / DB

Một queue có thể liên kết với một hoặc nhiều compute environments. Scheduler xét thứ tự CE trong queue; nếu CE đầu tiên không hợp lệ hoặc không có loại tài nguyên phù hợp, có thể thử CE tiếp theo theo cấu hình.

### 8.2 Managed và unmanaged compute environments

**Managed compute environment:** AWS Batch quản lý capacity theo cấu hình min/desired/max vCPU, instance types, Spot/On-Demand hoặc Fargate. Đây là lựa chọn thường dùng vì giảm công việc provisioning và scale.

**Unmanaged compute environment:** người dùng tự quản lý compute instances và capacity. Dùng khi cần cấu hình đặc thù, dedicated host, storage hoặc cách quản lý hạ tầng không nằm trong mô hình managed. Người vận hành phải đảm bảo ECS agent/node capacity và lifecycle phù hợp.

### 8.3 Queue, priority và CE order

Một tổ chức có thể tách queue theo SLA:

| Queue | Priority | Compute environment | Workload |
|---|---:|---|---|
| critical | Cao | EC2 On-Demand | Job cần hoàn thành đúng deadline |
| standard | Trung bình | EC2 On-Demand + Spot | ETL thông thường |
| flexible | Thấp | EC2 Spot hoặc Flex capacity | Simulation có thể chờ |
| gpu | Theo policy | GPU EC2 | Training/rendering |

Priority giữa queue và order của CE là hai cấu hình khác nhau. Queue priority quyết định queue nào được scheduler xét trước; CE order quyết định môi trường nào được thử trước trong một queue.

### 8.4 FIFO và fair-share scheduling

Nếu không gắn scheduling policy, Batch scheduler mặc định dùng FIFO. FIFO đơn giản nhưng job lớn ở đầu queue có thể làm job nhỏ phía sau chờ lâu (head-of-line blocking).

Fair-share scheduling dùng share identifier để phân bổ capacity giữa tenant/workload. Ví dụ:

- Team A có nhiều job liên tục.
- Team B chỉ gửi job vào cuối ngày.
- Fair-share giúp Team A không chiếm toàn bộ capacity khiến Team B bị đói tài nguyên.

Fair-share không thay thế queue priority hoặc job dependency. Chọn share decay/window và weight theo mục tiêu công bằng, SLA và mức sử dụng đã thỏa thuận.

### 8.5 Resource-aware scheduling

Batch có thể quản lý consumable resources ngoài CPU/RAM, ví dụ license token, database connection budget hoặc quota API. Job khai báo số lượng tài nguyên cần dùng; scheduler chỉ chạy khi các consumable resources sẵn sàng. Cơ chế này giúp tránh khởi chạy job khi compute còn trống nhưng dịch vụ downstream đã hết capacity.

## 9. Compute environments của AWS Batch

AWS Batch hiện hỗ trợ compute environments dựa trên Amazon ECS hoặc Amazon EKS. Với ECS orchestration, các compute types gồm EC2, Fargate, Fargate Spot và ECS Managed Instances. Với EKS orchestration, compute environment sử dụng EC2 On-Demand/Spot nodes.

### 9.1 ECS compute environment: EC2

EC2 compute environment cho phép chọn:

- Allowed instance types hoặc instance families.
- Minimum, desired và maximum vCPU.
- On-Demand hoặc Spot.
- Allocation strategy.
- Subnets và security groups.
- Launch template, AMI và storage configuration theo khả năng hỗ trợ.
- Placement group, instance profile và service role.

AWS Batch quản lý EC2 instance trong ECS cluster cho managed CE. Compute environment có thể scale về minimum vCPU sau khi job hoàn thành; nếu minvCpus lớn hơn 0, capacity warm có thể giảm startup latency nhưng vẫn phát sinh chi phí.

### 9.2 Allocation strategy

Allocation strategy quyết định Batch chọn instance type/pool thế nào khi cần thêm capacity.

| Strategy | Mục đích | Khi cân nhắc |
|---|---|---|
| BEST_FIT | Chọn loại phù hợp, ưu tiên chi phí thấp | Muốn cost thấp và chấp nhận chờ capacity |
| BEST_FIT_PROGRESSIVE | Chọn loại đáp ứng job, mở rộng sang loại khác khi cần | On-Demand CE cần throughput và khả năng lấy capacity |
| BEST_FIT_PROGRESSIVE_ORDERED | Ưu tiên theo thứ tự instanceTypes đã khai báo | Cần kiểm soát thứ tự loại instance |
| SPOT_CAPACITY_OPTIMIZED | Ưu tiên pool Spot có capacity sâu | Giảm xác suất interruption |
| SPOT_PRICE_CAPACITY_OPTIMIZED | Cân bằng giá và khả năng có capacity | Khuyến nghị chung cho nhiều Spot workload |
| SPOT_CAPACITY_OPTIMIZED_PRIORITIZED | Ưu tiên capacity nhưng tôn trọng thứ tự instance ở mức best effort | Cần định hướng instance type và vẫn ưu tiên khả năng cấp phát |

Các strategy không áp dụng giống nhau cho mọi compute type. Fargate và ECS Managed Instances không dùng allocationStrategy như EC2. Với Spot, nên đa dạng instance type và AZ nếu workload cho phép. Với một số strategy, Batch có thể vượt maxvCpus tối đa một instance để đáp ứng capacity; hãy xem behavior cụ thể trước khi đặt budget hard limit.

### 9.3 Fargate và Fargate Spot

Fargate phù hợp với container job không cần quản lý EC2 instance, custom AMI, GPU hoặc host-level device. AWS Batch có thể tạo Fargate compute environment và cấp task resources theo job.

Các giới hạn cần lưu ý theo tài liệu hiện hành:

- Job Fargate có giới hạn vCPU/memory và các tổ hợp size được hỗ trợ; mức cao nhất được tài liệu nêu là 32 vCPU và 244 GiB memory.
- Không hỗ trợ GPU hoặc Elastic Fabric Adapter.
- Không có các tham số EC2 như instanceTypes, launchTemplate, placementGroup và minvCpus.
- Job không nên kỳ vọng chạy lâu hơn 14 ngày trên Fargate.
- Fargate Spot có thể bị gián đoạn; Windows containers không được hỗ trợ trên Fargate Spot.

Fargate là lựa chọn dễ vận hành cho job nhỏ/vừa, cần isolation ở task runtime và có startup nhanh. Nếu cần GPU, privileged container, host volume/device, hơn 32 vCPU hoặc hơn 244 GiB memory, hãy đánh giá ECS Managed Instances hoặc EC2.

### 9.4 ECS Managed Instances

Amazon ECS Managed Instances kết hợp trải nghiệm vận hành managed với compute flexibility của EC2. ECS quản lý provisioning, scaling, patching và termination của instance dựa trên job resource requirement. Trong AWS Batch, loại compute environment này chỉ dùng với ECS orchestration, không dùng cho EKS compute environment.

Chọn ECS Managed Instances khi job cần:

- GPU hoặc instance family cụ thể.
- Nhiều hơn giới hạn CPU/RAM của Fargate.
- Privileged access, host-level device hoặc volume.
- Instance ARM64/Graviton hoặc cấu hình x86/ARM theo yêu cầu.
- On-Demand Capacity Reservations, Reserved Instances hoặc EC2 Instance Savings Plans.
- Tổ hợp vCPU/memory linh hoạt mà Fargate không cung cấp.

Fargate vẫn đơn giản hơn khi job nằm trong giới hạn resource và không cần GPU/host access. EC2 managed compute environment phù hợp khi cần MNP, custom AMI/launch template, fine-grained allocation strategy hoặc minvCpus warm pool.

### 9.5 AWS Batch compute environment trên EKS

AWS Batch có thể điều phối job trên EKS cluster theo mô hình overlay:

1. Tạo hoặc chọn EKS cluster.
2. Cấp quyền Kubernetes RBAC cho Batch truy cập API server.
3. Kết nối cluster và tạo EKS compute environment.
4. Tạo job queue liên kết với CE.
5. Đăng ký job definition theo pod specification.
6. Submit job qua AWS Batch API.

Batch gọi Kubernetes API để tạo, theo dõi và xóa Pod/node. Không cần cài operator hoặc custom resource của Batch trong cluster. Batch quản lý lifecycle node mà nó tạo, gắn label/taint để workload khác không đặt Pod lên các node này (ngoại lệ có thể là DaemonSet được cấu hình nhắm tới node đó). Batch không đặt job lên node do hệ thống khác quản lý.

EKS compute environment của AWS Batch dùng EC2 On-Demand/Spot; không hỗ trợ Fargate. Khi queue rỗng, Batch có thể scale node về min capacity, mặc định là zero nếu không đặt khác. Cần kiểm tra EKS Kubernetes version, access entry/authentication, RBAC, node IAM, subnet IP và capacity.

### 9.6 Batch trên EKS hay Kubernetes Job thuần?

| Nhu cầu | EKS Job/CronJob thuần | AWS Batch trên EKS |
|---|---|---|
| Kubernetes manifest/GitOps | Native | Dùng Batch API và job definition |
| Queue và priority | Cần tự xây hoặc cài scheduler | Có job queue và priority |
| Dependency giữa job | Workflow/scheduler riêng | Có job dependencies |
| Retry | Job controller và backoffLimit | Batch retry strategy và exit rules |
| Fair-share | Scheduler bổ sung | Scheduling policy |
| Node scaling | Karpenter/Cluster Autoscaler | Batch quản lý node dành cho Batch CE |
| Kubernetes customizations | Toàn quyền Kubernetes | Batch quản lý lifecycle của job/node trong phạm vi CE |
| Phù hợp | Nền tảng Kubernetes đa mục đích, workload cần native K8s | Batch-centric platform cần queue, retry và capacity management |

Nếu team đã có queue như Kueue/Volcano hoặc hệ thống scheduling riêng, so sánh chức năng và vận hành trước khi thêm Batch. Tránh để hai scheduler cùng điều khiển một lớp capacity.

## 10. Job definition và vòng đời job trong AWS Batch

### 10.1 Job definition

Job definition mô tả cách chạy container:

- Container image và registry.
- Command/entrypoint.
- vCPU, memory và GPU resource requirement.
- Execution role và job role.
- Environment variables và parameters.
- Volumes/mount points.
- Logging configuration.
- Retry strategy và timeout.
- Network/security options tùy compute platform.

Job definition có revision. Hãy version hóa image bằng tag bất biến hoặc digest, giữ job definition revision theo release và tránh dùng tag latest trong production.

### 10.2 Job role và execution role

- **Job role:** IAM role mà code trong container assume để truy cập S3, DynamoDB, SQS, KMS hoặc API AWS.
- **Execution role:** quyền của ECS/Fargate agent hoặc runtime để pull image, ghi log, lấy secret theo cấu hình.
- **Batch service-linked role:** cho AWS Batch quản lý compute resources và tích hợp với các dịch vụ liên quan.

Với EKS compute environment, cần thêm IAM role/Pod identity hoặc service account configuration phù hợp với cluster. Không nhầm quyền người submit job với quyền mà container runtime có.

### 10.3 Submit job

Ví dụ CLI:

    aws batch submit-job \
      --job-name orders-transform-20261120 \
      --job-queue batch-standard \
      --job-definition orders-transform:4 \
      --parameters input=s3://company-data/raw/orders/ \
      --container-overrides '{"command":["python","main.py","--mode","daily"]}' \
      --region ap-southeast-1

Lệnh minh họa cần có job queue, job definition và image đã đăng ký. Parameters có thể được dùng trong command/job definition; container overrides thay đổi cấu hình của lần submit. Không truyền secret trực tiếp trong command line hoặc environment variable nếu có thể dùng Secrets Manager/secret injection.

### 10.4 Job states

Một job thường đi qua các trạng thái:

    SUBMITTED
        |
    PENDING (chờ dependency/resource)
        |
    RUNNABLE (đủ điều kiện chờ compute)
        |
    STARTING
        |
    RUNNING
       / \
 SUCCEEDED FAILED

Job có thể ở RUNNABLE lâu nếu CE không hợp lệ, thiếu capacity, vCPU quota, instance type không có sẵn, job resource không phù hợp hoặc queue bị chặn. RUNNABLE lâu không nhất thiết là lỗi code của container; cần kiểm tra scheduler/CE/compute quota.

### 10.5 Dependencies

SubmitJob có thể khai báo job phụ thuộc vào các job khác. Job phụ thuộc chỉ được chuyển sang RUNNABLE sau khi dependency thành công; nếu dependency thất bại, job phụ thuộc cũng có thể chuyển FAILED.

Một job có thể phụ thuộc tối đa 20 job theo quota hiện hành. Với pipeline phức tạp, dùng Step Functions, MWAA hoặc orchestrator phù hợp để quản lý branch, condition, compensation và timeout.

### 10.6 Retry strategy

AWS Batch hỗ trợ từ 1 đến 10 attempts. Có thể dùng evaluateOnExit để quyết định retry hoặc exit dựa trên exit code, reason hoặc status reason.

Ví dụ policy:

| Tình huống | Hành động |
|---|---|
| Exit code 137/OOM | Có thể tăng memory hoặc đưa sang queue khác; không retry vô hạn |
| Exit code 1 do input sai | EXIT, đưa record vào quarantine |
| Throttling/network transient | RETRY với backoff |
| EC2 instance failure/Spot interruption | RETRY nếu job idempotent/checkpoint |
| AccessDenied/KMS deny | EXIT và sửa IAM/policy |
| Dependency không có | Không submit job downstream cho đến khi dữ liệu sẵn sàng |

Retry tạo thêm attempt; ứng dụng phải chịu được việc chạy lại. Không dựa vào retry để che lỗi dữ liệu hoặc side effect trùng lặp.

### 10.7 Timeout và cancellation

Job timeout giới hạn thời gian một attempt chạy. Nếu attempt bị kết thúc do timeout, Batch không tự retry attempt đó theo behavior được tài liệu hóa; lỗi tự phát có thể được retry nếu cấu hình. Fargate job không nên kỳ vọng chạy quá 14 ngày.

Khi hủy job, container có thể nhận tín hiệu kết thúc trước khi bị dừng. Hãy xử lý SIGTERM, flush output/checkpoint và release lock/license. Không giả định cleanup code luôn được chạy nếu process bị terminate đột ngột.

## 11. Array jobs, GPU và multi-node parallel jobs

### 11.1 Array jobs

Array job dùng chung job definition/parameters và tạo nhiều child jobs có thể chạy song song. Kích thước array từ 2 đến 10.000 child jobs.

Ví dụ xử lý 5.000 file:

    aws batch submit-job \
      --job-name resize-campaign \
      --job-queue batch-standard \
      --job-definition resize-image:2 \
      --array-properties size=5000 \
      --region ap-southeast-1

Trong container, biến môi trường AWS_BATCH_JOB_ARRAY_INDEX xác định index của child job. Ứng dụng dùng index để chọn partition/file/input tương ứng. Không để tất cả child job cùng đọc và ghi một output path.

Array job phù hợp:

- Monte Carlo parameter sweep.
- Render frames.
- ETL theo partition.
- Tạo embedding theo batch tài liệu.
- Xử lý ảnh/video độc lập.

### 11.2 Dependencies giữa array jobs

Batch hỗ trợ:

- SEQUENTIAL: child index chạy lần lượt theo thứ tự.
- N_TO_N: child index của job downstream chờ child index tương ứng của upstream hoàn thành.

Nếu hủy parent array job, các child job có thể bị hủy theo. Nếu một child job thất bại, parent có thể kết thúc FAILED sau khi các child hoàn tất. Hãy thiết kế aggregation/finalization job để xác minh tất cả partition trước khi publish.

### 11.3 GPU scheduling

Job definition có thể yêu cầu số lượng và loại accelerator. Batch dùng yêu cầu này để chọn EC2 accelerated instances phù hợp và phân bổ GPU cho container. Điều kiện:

- Compute environment phải chứa GPU instance family phù hợp.
- Image cần CUDA/driver/library tương thích với host/runtime.
- Resource request phải phản ánh số GPU thực tế.
- Theo dõi GPU utilization, memory, driver errors và queue wait.
- Không cấp GPU cho job chỉ cần CPU vì GPU instance có chi phí cao.

Fargate không cung cấp GPU; chọn EC2 hoặc ECS Managed Instances theo khả năng hỗ trợ của compute environment.

### 11.4 Multi-node parallel jobs (MNP)

MNP cho phép một job đơn lẻ trải trên nhiều EC2 instance. Đây là gang scheduling: các node được cấp cho cùng job để ứng dụng phân tán giao tiếp với nhau.

Một MNP job có:

- Main node khởi động trước.
- Child nodes khởi động sau main node.
- Node groups có thể có cấu hình container/resource khác nhau.
- Job hoàn tất theo trạng thái của main node; sau đó child nodes được dừng.
- Node của MNP là single-tenant: chỉ một job container chạy trên mỗi EC2 instance.

MNP phù hợp với MPI, distributed training hoặc framework hỗ trợ IP-based inter-node communication. MNP yêu cầu EC2 compute environment; không dùng Fargate.

### 11.5 Failure semantics của MNP

Nếu bật retry, main node failure sẽ kích hoạt attempt mới. Child node failure không tự kích hoạt thêm attempt theo cùng cách; ứng dụng cần phát hiện lỗi giao tiếp và báo trạng thái phù hợp cho main node. Job status tổng thể được xác định từ main node.

Đừng chỉ kiểm tra exit code của một child process. Cần log node index, host, rank, rendezvous endpoint và lỗi network để điều tra.

## 12. HPC: MPI, EFA, placement groups và shared storage

HPC tightly coupled cần nhiều node trao đổi dữ liệu thường xuyên. Hiệu năng phụ thuộc vào network latency/bandwidth, đồng bộ hóa, topology, CPU/GPU và tốc độ đọc/ghi dữ liệu. Một job có thể dùng nhiều instance nhưng vẫn chạy chậm nếu network hoặc storage không đáp ứng.

### 12.1 AWS Batch MNP với MPI

Một MNP job thường khởi chạy main node và nhiều child nodes. Ứng dụng dùng MPI hoặc framework tương tự để khởi tạo ranks, khám phá địa chỉ node và phân phối dữ liệu.

Các điều kiện thiết kế:

- Chọn EC2 instance types tương thích với workload và network.
- Dùng cluster placement group khi cần đặt node gần nhau trong cùng AZ.
- Mở security group cho giao tiếp nội bộ giữa các node/port cần thiết.
- Cấu hình hostname, DNS, MPI transport và rendezvous.
- Chọn storage dùng chung hoặc phân vùng input/output hợp lý.
- Đo scaling efficiency khi tăng số node.

### 12.2 Elastic Fabric Adapter (EFA)

EFA là network device hỗ trợ HPC application có nhu cầu communication cao. AWS Batch hỗ trợ job dùng EFA khi thỏa điều kiện:

- EC2 instance type hỗ trợ EFA.
- AMI và operating system có EFA driver phù hợp.
- Các instance dùng EFA nằm trong cùng cluster placement group.
- Security group cho phép inbound/outbound traffic giữa các instance trong chính security group đó.
- Job definition truyền device EFA vào container qua hostPath /dev/infiniband/uverbs0; nếu khai báo permissions, cần READ, WRITE và MKNOD theo yêu cầu của connector/runtime.

EFA là tính năng cần cấu hình đồng bộ giữa instance, AMI, security group, placement group và container. Chỉ chọn instance có EFA không đủ để ứng dụng MPI sử dụng EFA.

### 12.3 Placement groups

| Strategy | Mục đích | Workload |
|---|---|---|
| Cluster | Đặt instance gần nhau trong một AZ để giảm latency/tăng throughput | HPC tightly coupled, MPI |
| Partition | Tách nhóm instance vào partition phần cứng khác nhau | Distributed systems cần giảm correlated failure |
| Spread | Phân tán một nhóm nhỏ instance lên phần cứng khác nhau | Workload cần giảm lỗi tương quan |

Cluster placement group có thể gặp giới hạn capacity khi launch nhiều instance cùng lúc. Hãy benchmark và xác nhận khả năng cấp phát ở Region/AZ trước khi đưa SLA vào production. Placement group không bảo đảm mọi loại instance luôn có sẵn.

### 12.4 Storage cho HPC

| Storage | Pattern |
|---|---|
| Amazon S3 | Dataset bền vững, checkpoint, kết quả, archive |
| EBS | Block storage cho node, scratch và application disk |
| EFS | Shared NFS filesystem cho nhiều node và file-based workflows |
| FSx for Lustre | Parallel file system throughput cao cho HPC, ML và analytics |
| Instance store/NVMe | Scratch rất nhanh nhưng mất khi instance bị terminate |

Một pattern phổ biến là lưu dataset bền vững trên S3, mount FSx for Lustre làm scratch/working set, sau đó ghi kết quả về S3. Chọn dung lượng/throughput FSx theo read/write pattern và kiểm tra data repository association nếu dùng S3 integration.

### 12.5 AWS Batch hay AWS ParallelCluster?

AWS Batch phù hợp khi tổ chức muốn queue, job definition, retry, array/MNP và managed capacity. AWS ParallelCluster phù hợp khi cần dựng HPC cluster với scheduler như Slurm và kiểm soát môi trường cluster theo cách HPC truyền thống.

Hai lựa chọn có thể bổ sung cho nhau ở cấp tổ chức nhưng không nên để hai scheduler cùng điều khiển một job. Hãy chọn theo cách người dùng submit job, license/toolchain, topology, interactive login, queue policy và khả năng vận hành.

## 13. Storage, networking và data movement

### 13.1 Chọn storage theo vòng đời dữ liệu

| Loại dữ liệu | Nơi lưu phù hợp | Lý do |
|---|---|---|
| Input/output bền vững | S3 | Durable, tách compute và chia sẻ giữa job |
| Checkpoint cần phục hồi | S3/EFS/FSx hoặc database phù hợp | Tồn tại qua instance/task/pod restart |
| Shared POSIX file | EFS hoặc FSx | Nhiều worker đọc/ghi cùng filesystem |
| Block device/scratch | EBS | Block semantics và throughput có thể cấu hình |
| Temporary scratch tốc độ cao | Instance store/NVMe | I/O nhanh, chấp nhận mất khi node kết thúc |
| HPC working set | FSx for Lustre | Parallel file system throughput cao |

Không lưu output duy nhất trong writable container layer, ephemeral task storage hoặc local instance store nếu cần phục hồi sau khi job kết thúc.

### 13.2 Network placement

Đặt compute gần data và service phụ thuộc trong cùng Region. Chọn private subnets cho workload không cần public inbound; sử dụng NAT hoặc VPC endpoints để truy cập ECR, S3, CloudWatch, Secrets Manager và các API AWS.

Các điểm cần kiểm tra:

- Subnet IP capacity, đặc biệt khi ECS awsvpc hoặc EKS VPC CNI tạo ENI/IP cho task/pod.
- Security group ingress/egress giữa worker, database, FSx/EFS và node peers.
- DNS resolution và route table.
- NAT Gateway throughput và data processing cost.
- Cross-AZ data transfer khi compute và storage ở AZ khác.
- MTU/jumbo frame và network interface capability cho HPC nếu phù hợp.

### 13.3 S3 access pattern

Nhiều worker cùng đọc/ghi S3 cần partition hóa dữ liệu và tránh nhiều job tranh chấp cùng object key hoặc tạo quá nhiều small files/metadata. Sử dụng multipart upload cho file lớn, retry có backoff, checksum và commit marker. Khi fan-out hàng nghìn job, cân nhắc giới hạn concurrency và theo dõi throttling/capacity của downstream.

### 13.4 File systems

EFS phù hợp với shared file access và workload cần POSIX semantics. FSx for Lustre phù hợp với throughput cao và parallel I/O. EBS gắn với instance hoặc volume lifecycle; khi instance kết thúc, cần xác định volume được giữ hay xóa. Instance store luôn phải xem là ephemeral.

## 14. IAM, secrets và bảo mật workload

### 14.1 Role theo runtime

| Nền tảng | Role chính | Dùng cho |
|---|---|---|
| EC2 trực tiếp | EC2 instance profile | Credential cho process trên máy |
| ECS | Task execution role | Pull image, logs, secrets |
| ECS | Task role | Quyền của application trong container |
| EKS | Pod Identity hoặc IRSA role | Quyền AWS của Pod/service account |
| AWS Batch ECS | Job role và execution role | Quyền application và quyền runtime |
| AWS Batch EKS | Kubernetes RBAC + pod IAM role | Batch API access và quyền AWS của workload |
| AWS Batch service | Service-linked role | Batch quản lý compute/resource |

Không dùng instance role hoặc node role làm quyền mặc định cho mọi workload nếu có thể cấp role riêng theo job/task/pod. Người submit job chỉ nên được PassRole các role đã được allowlist.

### 14.2 Secrets

Không đưa password, API key hoặc access key vào Docker image, command line, log hay source code. Dùng Secrets Manager/Systems Manager Parameter Store và inject theo cơ chế phù hợp với ECS/EKS/Batch. Hạn chế quyền đọc secret theo workload và xoay vòng theo policy.

### 14.3 Container hardening

- Dùng image tối giản, version/digest bất biến.
- Scan image và dependency.
- Chạy non-root khi có thể.
- Read-only root filesystem nếu ứng dụng hỗ trợ.
- Giới hạn Linux capabilities và privilege.
- Đặt CPU/memory requests/limits hoặc Batch resource requirements.
- Không mount host path/device nếu không thực sự cần.
- Giữ secret ngoài image và environment log.
- Cập nhật base image và patch theo lịch.

HPC/EFA có thể cần device access đặc biệt; cấp đúng device/permission thay vì bật privileged container toàn bộ nếu không cần.

### 14.4 Encryption và data protection

Mã hóa S3/EBS/EFS/FSx bằng cơ chế phù hợp, dùng KMS customer-managed key khi cần kiểm soát key policy. Bật TLS cho service-to-service và database connection. Kiểm tra key policy cho runtime role, service role và người vận hành.

### 14.5 Audit

CloudTrail ghi nhận API quản trị như SubmitJob, RegisterJobDefinition, CreateComputeEnvironment, RunTask hoặc thay đổi EKS. Kết hợp Batch job history, ECS task events, Kubernetes audit/logs và application logs để xác định:

- Ai submit job?
- Job dùng image/definition revision nào?
- Role nào được cấp?
- Job đọc/ghi resource nào?
- Job chạy ở Region/AZ/compute environment nào?
- Ai thay đổi queue, CE hoặc IAM policy?

## 15. Reliability, retry và idempotency

### 15.1 Batch thường là at-least-once

Một job có thể được chạy lại sau lỗi node, interruption, timeout hoặc lỗi dịch vụ. Vì vậy, không giả định code chỉ được thực thi đúng một lần. Hãy thiết kế idempotent output:

- Gán job_id/run_id duy nhất.
- Lưu trạng thái từng partition/chunk.
- Dùng conditional write/upsert theo business key.
- Ghi output vào staging prefix.
- Validate record count/schema/checksum.
- Chỉ publish sau khi tất cả phần việc thành công.
- Dọn staging cũ theo retention policy.

### 15.2 Checkpoint và resume

Job dài nên checkpoint tiến độ định kỳ. Checkpoint cần lưu ở storage bền vững và chứa version của input/schema/code khi cần. Khi resume, kiểm tra checkpoint có tương thích với code mới và dữ liệu đầu vào chưa bị thay đổi.

Với MPI/HPC, checkpoint cần đồng bộ trạng thái của các rank hoặc dùng application-level checkpoint. Chỉ lưu checkpoint của main process có thể không đủ nếu state phân tán trên nhiều node.

### 15.3 Spot interruption

Khi nhận rebalance/interruption event:

1. Ngừng nhận chunk mới.
2. Lưu checkpoint hoặc flush kết quả an toàn.
3. Ghi trạng thái công việc đã hoàn thành.
4. Đóng file/socket và release license.
5. Thoát trước khi instance bị thu hồi nếu có thể.
6. Để scheduler retry phần chưa hoàn thành.

Thông báo hai phút là cơ hội graceful shutdown, không phải SLA bảo đảm. Luôn thiết kế job có thể bị dừng đột ngột.

### 15.4 Retry policy

Retry chỉ lỗi transient hoặc lỗi có khả năng tự phục hồi. Với lỗi code/data/permission, chuyển FAILED và tạo remediation. Dùng exponential backoff, jitter và giới hạn attempts để tránh retry storm.

### 15.5 Queue backpressure

Nếu tốc độ submit lớn hơn tốc độ xử lý, queue sẽ tăng. Hãy theo dõi age of oldest job, queue depth, RUNNABLE duration, arrival/completion rate và downstream capacity. Giới hạn concurrency, dùng fair-share và resource-aware scheduling. Không tăng max capacity mà chưa xác nhận database/API/storage chịu được lưu lượng tăng.

## 16. Orchestration và event-driven pipelines

AWS Batch thường là executor trong pipeline nhiều bước. Step Functions có thể điều phối submit job, chờ kết quả, branch theo trạng thái và gọi bước tiếp theo.

    EventBridge / S3 event / API
                 |
            Step Functions
                 |
          Validate input
                 |
           Submit Batch job
                 |
           Wait / DescribeJob
                 |
         Job SUCCEEDED?
             /       \
           Yes        No
            |          |
      Validate output  Retry / alert
            |
       Publish dataset
            |
       Notify consumers

### 16.1 Chọn orchestrator

| Nhu cầu | Công cụ |
|---|---|
| Lịch một lần/cron/rate | EventBridge Scheduler |
| Workflow nhiều bước, retry, branch, wait | Step Functions |
| DAG dữ liệu, lịch data engineering | MWAA/Airflow |
| Message buffering và decoupling | SQS |
| Queue và scheduling batch compute | AWS Batch |
| Container task đơn giản | ECS RunTask |
| Kubernetes-native workflow | Job/CronJob hoặc workflow engine trên EKS |

### 16.2 Job dependency

AWS Batch có dependency trực tiếp giữa job. Step Functions phù hợp khi dependency có branch, approval, compensation hoặc tích hợp nhiều AWS services. Không tạo dependency graph lớn chỉ bằng chuỗi script nếu cần quan sát và retry từng bước.

### 16.3 Duplicate trigger

EventBridge, SQS và orchestrator có thể giao event lặp theo delivery semantics. Dùng idempotency key dựa trên business event ID, source object version hoặc scheduled execution ID. Trước khi submit job, kiểm tra job tương ứng đã được xử lý hay chưa.

## 17. Monitoring và troubleshooting

### 17.1 Metrics cần theo dõi

| Lớp | Metrics/trạng thái |
|---|---|
| Queue | Depth, oldest job age, submitted/runnable/running/failed |
| AWS Batch | Job state, CE state, desired/allocated vCPU, job attempts, scheduling delay |
| EC2 | CPU, memory agent, disk, network, Spot interruption, instance launch failures |
| ECS | Task state, stopped reason, placement failure, service/task count |
| EKS | Pod pending, restart, OOMKilled, node pressure, scheduler events, IP capacity |
| Application | Runtime, throughput, error rate, retry count, checkpoint, output count |
| Storage | S3 request/latency/error, EBS throughput/queue, EFS/FSx throughput/capacity |
| Cost | Cost per job, cost per TB, idle capacity, Spot/On-Demand ratio |

### 17.2 AWS Batch job RUNNABLE quá lâu

Kiểm tra theo thứ tự:

1. Job queue có compute environment gắn đúng không?
2. Compute environment có status VALID không?
3. CE có đủ maxvCpus và quota EC2 không?
4. Instance types có đáp ứng vCPU/memory/GPU yêu cầu không?
5. Subnet còn IP và có route tới ECR/S3/log endpoints không?
6. Spot capacity có khả dụng không?
7. CE order/queue priority có đẩy job sang môi trường không phù hợp không?
8. Job có đòi consumable resource/license chưa sẵn sàng không?

### 17.3 ECS task không khởi chạy

Kiểm tra task stopped reason, capacity provider, task definition revision, CPU/memory placement, subnet IP, security group, ECR pull permission, execution role và log configuration. Với EC2 capacity provider, kiểm tra ASG managed scaling và instance registration.

### 17.4 EKS Pod Pending

Kiểm tra Kubernetes events, resource requests, node selector, affinity, taints/tolerations, node group capacity, Karpenter constraints, subnet IP và service quota. Nếu Pod OOMKilled, điều chỉnh memory request/limit và xử lý memory leak.

### 17.5 Job thất bại lặp lại

Xem exit code, reason, container log, attempt number và image digest. Xác định lỗi transient, code, data, IAM hay capacity. Tránh retry vô hạn một lỗi deterministic.

### 17.6 Log và trace

Ghi job ID, run ID, tenant, input version, image digest, queue, CE, instance/node, attempt và output location. Không ghi PII/secret hoặc payload đầy đủ nếu không cần. Đặt retention CloudWatch/S3 theo policy và dùng correlation ID nối log giữa workflow, scheduler và container.

## 18. Chi phí và tối ưu

### 18.1 AWS Batch không thu phí điều phối riêng

AWS Batch không có additional service charge cho việc sử dụng scheduler. Người dùng trả tiền cho tài nguyên AWS được tạo để chạy và lưu dữ liệu job, ví dụ EC2, Fargate, ECS Managed Instances, EKS, EBS, S3, EFS, FSx, network và CloudWatch.

### 18.2 Thành phần chi phí theo mô hình

| Mô hình | Các khoản cần tính |
|---|---|
| EC2 trực tiếp | EC2 On-Demand/Spot, EBS, AMI/storage, network, load balancer nếu có, logging |
| ECS trên EC2 | EC2, EBS, network, logs và capacity idle |
| ECS/Fargate | vCPU/memory theo thời gian task, ephemeral storage, data transfer và logs |
| EKS native | EKS cluster control plane, EC2/Fargate nodes, EBS, networking, add-ons và logs |
| AWS Batch trên ECS | Underlying EC2/Fargate/ECS Managed Instances cùng storage/network/logging |
| AWS Batch trên EKS | EKS cluster, EC2 nodes do Batch quản lý, storage/network/logging |

### 18.3 Chi phí ẩn thường gặp

- EC2 warm capacity hoặc Batch minvCpus giữ máy idle.
- EKS control plane và node capacity khi queue rỗng.
- Fargate Spot/EC2 Spot interruption làm job chạy lại.
- NAT Gateway và cross-AZ data transfer.
- S3 request, EBS volume còn sót, EFS/FSx capacity.
- CloudWatch log ingestion/retention quá dài.
- License token hoặc phần mềm HPC thương mại.
- Retry storm và job chạy lại do output không idempotent.

### 18.4 Tối ưu

- Dùng Fargate cho job phù hợp giới hạn và không cần host-level access.
- Dùng Spot cho workload chịu interruption, đa dạng instance types/AZ.
- Chọn EC2 allocation strategy theo capacity/cost.
- Đặt min/max capacity và scale-down delay phù hợp.
- Dùng queue riêng cho SLA khác nhau.
- Dùng fair-share để ngăn tenant chiếm hết compute.
- Chọn vCPU/memory request sát nhu cầu; đo OOM và CPU throttling.
- Dừng ECS task/EC2 worker khi không còn việc.
- Với EKS, scale node về zero hoặc mức tối thiểu nếu phù hợp; tính cả EKS cluster charge.
- Tối ưu input partitioning, file size và data locality.
- Theo dõi cost per successful job, cost per TB và queue wait time.

## 19. Case study: xử lý ảnh theo lô đa tenant

### 19.1 Bối cảnh

Một nền tảng thương mại điện tử nhận 100.000 ảnh sản phẩm mỗi ngày từ nhiều tenant. Mỗi ảnh cần resize ba kích thước, tạo thumbnail, kiểm tra metadata và ghi kết quả vào S3. Có burst lớn sau chiến dịch marketing; mỗi ảnh độc lập, job có thể retry.

### 19.2 Các phương án

| Phương án | Ưu điểm | Hạn chế |
|---|---|---|
| EC2 worker + SQS | Kiểm soát sâu, đơn giản khi có worker platform | Tự quản retry, visibility, scaling, fairness và job status |
| ECS RunTask | Container đơn giản, Fargate/EC2 capacity provider | Phải tự điều phối queue/retry/fair-share |
| EKS Job | Kubernetes-native, có thể dùng chung platform | Overhead Kubernetes; queue fairness cần thiết kế |
| AWS Batch array jobs | Fan-out lớn, retry, queue, capacity scale và job status | Cần thiết kế job definition/queue/CE và output idempotent |

### 19.3 Thiết kế đề xuất

- S3 nhận ảnh gốc và phát event.
- SQS/EventBridge hoặc ingestion service gom yêu cầu và chống duplicate.
- AWS Batch array job hoặc job thường theo partition.
- ECS managed compute environment dùng Fargate cho job nhỏ, hoặc EC2 Spot nếu cần throughput/cost tốt hơn.
- Job role chỉ được đọc raw prefix và ghi output prefix của tenant.
- Output ghi vào staging path theo run ID, sau đó publish manifest.
- CloudWatch theo dõi queue age, failure, throughput và cost.

### 19.4 Bảo vệ tenant

Tenant ID lấy từ hệ thống xác thực/metadata đã tin cậy, không lấy từ prompt hoặc command do người dùng tự do truyền vào. Job role/policy giới hạn S3 prefix; application validate object key và không cho phép path traversal. Ghi audit event theo tenant và job ID.

### 19.5 Scaling và retry

Đặt max concurrency để không làm nghẽn database/catalog. Dùng Spot cho phần xử lý có thể retry; lưu trạng thái mỗi ảnh và output idempotent. Nếu một ảnh lỗi do input corrupt, chuyển quarantine thay vì retry mãi.

## 20. Lab A: chạy batch task bằng ECS và EventBridge Scheduler

### Mục tiêu

Tạo ECS task definition chạy một script đọc dữ liệu S3, ghi kết quả và chạy theo lịch.

### Chuẩn bị

- ECR image có script batch.
- ECS cluster và Fargate hoặc EC2 capacity provider.
- Task execution role và task role.
- Subnet/security group và S3 access.
- EventBridge Scheduler role.

### Bước 1: tạo task definition

1. Khai báo image digest/tag bất biến.
2. Đặt CPU/memory phù hợp.
3. Khai báo command/entrypoint.
4. Gắn task role chỉ có quyền đọc input và ghi output.
5. Gắn execution role để pull image và ghi logs.
6. Cấu hình awslogs và network mode.

### Bước 2: chạy thử standalone task

1. Dùng ECS RunTask.
2. Chọn cluster và capacity provider.
3. Cấu hình subnet/security group.
4. Theo dõi task state và stopped reason.
5. Kiểm tra output trên S3.

### Bước 3: tạo schedule

1. Tạo EventBridge Scheduler schedule kiểu cron hoặc rate.
2. Chọn ECS RunTask làm target.
3. Chọn cluster/task definition và network configuration.
4. Gắn Scheduler execution role.
5. Cấu hình retry/dead-letter queue.
6. Chạy thử một lần và xác minh log/output.

### Bước 4: kiểm thử lỗi

Thử job trả exit code khác 0. Xác nhận ECS task chuyển STOPPED và workflow/scheduler có cơ chế phát hiện, gọi lại hoặc thông báo. Không kỳ vọng ECS tự thay standalone task.

## 21. Lab B: tạo AWS Batch queue và compute environment

### Mục tiêu

Tạo managed EC2 compute environment, job queue, job definition và submit một job đọc/ghi S3.

### Bước 1: chuẩn bị image

1. Build container image có script batch.
2. Push lên Amazon ECR.
3. Kiểm thử image local.
4. Tạo S3 input/output prefix.

### Bước 2: tạo compute environment

1. Chọn managed EC2 compute environment.
2. Chọn instance families phù hợp workload.
3. Đặt minvCpus = 0 cho lab không cần warm capacity.
4. Đặt maxvCpus giới hạn chi phí.
5. Chọn On-Demand hoặc Spot.
6. Chọn subnets/security groups và service role.
7. Xác nhận CE status VALID.

### Bước 3: tạo job queue

1. Tạo queue batch-lab.
2. Gắn CE theo computeEnvironmentOrder.
3. Chọn priority.
4. Tạo fair-share policy nếu lab có nhiều tenant.

### Bước 4: đăng ký job definition

1. Chọn image ECR.
2. Khai báo vCPU và memory.
3. Gắn job role.
4. Cấu hình command, environment và log driver.
5. Cấu hình retry/timeout.
6. Đăng ký revision.

### Bước 5: submit và quan sát

1. SubmitJob vào queue.
2. Theo dõi trạng thái SUBMITTED/PENDING/RUNNABLE/STARTING/RUNNING.
3. Xem CloudWatch logs.
4. Kiểm tra output S3.
5. Xác nhận CE scale down khi queue rỗng.

### Bước 6: thử retry

Cho script trả lỗi transient ở lần đầu và thành công ở lần sau. Kiểm tra attempt count, evaluateOnExit và output idempotency.

## 22. Lab C: Batch trên EKS và Kubernetes Job

### Mục tiêu

So sánh Kubernetes Job thuần với AWS Batch EKS compute environment trên cùng một cluster.

### Phần A: Kubernetes Job

1. Tạo namespace batch-lab.
2. Tạo service account và IAM role qua Pod Identity/IRSA.
3. Áp dụng Job manifest.
4. Theo dõi Pod bằng kubectl.
5. Kiểm tra backoffLimit, activeDeadlineSeconds và TTL cleanup.
6. Tạo CronJob với concurrencyPolicy phù hợp.

### Phần B: AWS Batch EKS

1. Xác nhận EKS cluster version được hỗ trợ.
2. Tạo access entry/RBAC để Batch gọi Kubernetes API.
3. Tạo EKS compute environment dùng EC2 On-Demand hoặc Spot.
4. Tạo job queue và EKS job definition.
5. Submit job qua AWS Batch API.
6. Theo dõi job state trong Batch và Pod/node trong Kubernetes.
7. Xác nhận Batch chỉ dùng node do CE quản lý.

### So sánh

Ghi lại thời gian triển khai, queue wait, node provisioning, job runtime, retry behavior, mức độ tùy chỉnh và số thành phần vận hành. Chọn mô hình theo nhu cầu scheduling và kỹ năng team.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** EC2, ECS, EKS và AWS Batch thuộc những lớp nào?

**Đáp án:** EC2 là compute; ECS/EKS là container orchestration; AWS Batch là batch scheduler và capacity orchestration dùng các compute platform đó.

**Câu 2.** Khi nào nên dùng EC2 trực tiếp?

**Đáp án:** Khi cần custom OS/AMI/driver, thiết bị đặc thù, EFA, license daemon, HPC scheduler hoặc kiểm soát hạ tầng sâu.

**Câu 3.** ECS standalone task khác ECS service thế nào?

**Đáp án:** Standalone task chạy công việc rồi kết thúc; ECS service duy trì desired count và thay thế task để giữ ứng dụng chạy.

**Câu 4.** ECS có tự thay thế standalone task khi job thất bại không?

**Đáp án:** Không. Cần workflow retry hoặc dùng AWS Batch.

**Câu 5.** EventBridge Scheduler phù hợp với việc gì?

**Đáp án:** Kích hoạt tác vụ một lần, theo rate hoặc cron, ví dụ gọi ECS RunTask theo lịch.

**Câu 6.** Kubernetes Job và CronJob khác nhau thế nào?

**Đáp án:** Job quản lý một công việc hữu hạn; CronJob tạo Job theo lịch.

**Câu 7.** AWS Batch có những thành phần cốt lõi nào?

**Đáp án:** Job definition, job queue, compute environment và job.

**Câu 8.** AWS Batch có thu phí dịch vụ riêng không?

**Đáp án:** Không. Người dùng trả phí cho compute, storage, network và các tài nguyên AWS được sử dụng.

**Câu 9.** AWS Batch managed compute environment hỗ trợ những compute type nào?

**Đáp án:** EC2 On-Demand/Spot, Fargate/Fargate Spot và ECS Managed Instances; EKS compute environment sử dụng EC2.

**Câu 10.** AWS Batch trên EKS hoạt động theo mô hình nào?

**Đáp án:** Overlay orchestration: Batch gọi Kubernetes API để tạo/theo dõi/xóa Pod và quản lý node dành cho Batch; không cần cài Batch operator trong cluster.

**Câu 11.** AWS Batch EKS compute environment có hỗ trợ Fargate không?

**Đáp án:** Không. Batch trên EKS dùng EC2 On-Demand hoặc Spot; muốn dùng Fargate hãy chọn ECS compute environment.

**Câu 12.** Fair-share scheduling giải quyết vấn đề gì?

**Đáp án:** Phân bổ compute giữa tenant/workload để một nhóm không chiếm hết capacity.

**Câu 13.** Array job có thể có tối đa bao nhiêu child jobs?

**Đáp án:** 10.000 theo giới hạn hiện hành.

**Câu 14.** AWS Batch retry strategy hỗ trợ bao nhiêu attempts?

**Đáp án:** Từ 1 đến 10 attempts.

**Câu 15.** MNP job là gì?

**Đáp án:** Một job duy nhất chạy trên nhiều EC2 instance theo gang scheduling, phù hợp MPI và distributed HPC.

**Câu 16.** EFA cần những điều kiện chính nào?

**Đáp án:** Instance/OS hỗ trợ, EFA driver, cùng cluster placement group, security group cho phép traffic nội bộ và device được truyền vào container.

**Câu 17.** Vì sao Spot workload cần checkpoint và idempotency?

**Đáp án:** Spot có thể bị thu hồi; job có thể chạy lại nên cần lưu tiến độ và tránh duplicate side effect/output.

**Câu 18.** Task execution role khác task role trên ECS thế nào?

**Đáp án:** Execution role cho agent pull image/ghi log/lấy secret; task role cấp quyền AWS cho code bên trong container.

**Câu 19.** Vì sao job RUNNABLE lâu không nhất thiết là lỗi code?

**Đáp án:** Có thể thiếu compute capacity, quota, instance type phù hợp, subnet IP hoặc CE không hợp lệ.

**Câu 20.** Khi nào chọn EKS native Job thay vì AWS Batch trên EKS?

**Đáp án:** Khi workload cần Kubernetes-native workflow/API và tổ chức đã có queue/scheduler phù hợp; Batch phù hợp khi cần queue, dependency, retry, fair-share và capacity management.

## 24. Checklist production readiness

- [ ] Workload được phân loại: one-off, scheduled, queue-driven, parallel, long-running hay HPC.
- [ ] Resource profile và arrival rate được benchmark.
- [ ] Chọn đúng lớp compute, orchestration, scheduler và workflow.
- [ ] EC2 trực tiếp có kế hoạch patch, capacity, scheduler và cleanup.
- [ ] ECS standalone task có retry/orchestration bên ngoài khi cần.
- [ ] ECS service chỉ dùng cho workload cần duy trì desired count.
- [ ] EKS Job/CronJob có requests/limits, backoff, deadline và cleanup policy.
- [ ] Karpenter/Cluster Autoscaler và Kubernetes quota được kiểm thử.
- [ ] AWS Batch queue, CE order, priority và fair-share phù hợp SLA.
- [ ] Managed/unmanaged CE và compute type được chọn rõ.
- [ ] Fargate limits/GPU/host access/MNP được kiểm tra.
- [ ] Batch on EKS RBAC/access entry và EC2-only compute đã được xác nhận.
- [ ] Job definition revision và image digest được version hóa.
- [ ] Job role/execution role/service role theo least privilege.
- [ ] Subnet IP, NAT/VPC endpoint, security group và DNS được kiểm tra.
- [ ] Storage bền vững cho input/output/checkpoint.
- [ ] Job idempotent và output commit an toàn.
- [ ] Retry, timeout, dependency và cancellation có runbook.
- [ ] Spot interruption được kiểm thử.
- [ ] HPC MNP/EFA/placement group/FSx được benchmark nếu sử dụng.
- [ ] Queue depth, oldest job age, RUNNABLE duration và job failure có alarm.
- [ ] Cost per successful job/TB được theo dõi.
- [ ] Có quy trình dọn EC2/EBS/ENI/logs/temporary data.
- [ ] Có rollback và incident response owner.

## 25. Tài liệu tham khảo chính thức

1. [AWS Batch components](https://docs.aws.amazon.com/batch/latest/userguide/batch_components.html) — compute environment, queue, job definition và scheduling.
2. [Compute environments for AWS Batch](https://docs.aws.amazon.com/batch/latest/userguide/compute_environments.html) — ECS/EKS compute environments.
3. [Managed compute environments](https://docs.aws.amazon.com/batch/latest/userguide/managed_compute_environments.html) — EC2, Fargate, Spot và ECS Managed Instances.
4. [Amazon EKS compute environments for AWS Batch](https://docs.aws.amazon.com/batch/latest/userguide/eks.html) — overlay model, RBAC, node scaling và giới hạn EKS.
5. [Job queues](https://docs.aws.amazon.com/batch/latest/userguide/job_queues.html) — queue priority và compute environment order.
6. [Fair-share scheduling policies](https://docs.aws.amazon.com/batch/latest/userguide/job_scheduling.html) — FIFO và fair-share.
7. [Job definitions](https://docs.aws.amazon.com/batch/latest/userguide/job_definitions.html) — container, resource, role, volume và logging.
8. [Automated job retries](https://docs.aws.amazon.com/batch/latest/userguide/job_retries.html) — retry strategy và evaluateOnExit.
9. [Job dependencies](https://docs.aws.amazon.com/batch/latest/userguide/job_dependencies.html) — dependency và resource-aware scheduling.
10. [Array jobs](https://docs.aws.amazon.com/batch/latest/userguide/array_jobs.html) — fan-out và child job.
11. [Multi-node parallel jobs](https://docs.aws.amazon.com/batch/latest/userguide/multi-node-parallel-jobs.html) — gang scheduling và MPI.
12. [Elastic Fabric Adapter with AWS Batch](https://docs.aws.amazon.com/batch/latest/userguide/efa.html) — EFA device, placement group và security group.
13. [Fargate compute environments](https://docs.aws.amazon.com/batch/latest/userguide/fargate-compute-environments.html) — giới hạn Fargate.
14. [Amazon ECS Managed Instances compute environments](https://docs.aws.amazon.com/batch/latest/userguide/ecs_managed_instances.html) — compute lifecycle do ECS quản lý.
15. [AWS Batch pricing](https://aws.amazon.com/batch/pricing/) — không có phí dịch vụ Batch riêng.
16. [Amazon ECS standalone tasks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/standalone-tasks.html) — chạy task một lần.
17. [Schedule ECS tasks with EventBridge Scheduler](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/tasks-scheduled-eventbridge-scheduler.html) — cron/rate/one-time schedule.
18. [Schedule containers on Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/scheduling_tasks.html) — service, standalone và scheduled tasks.
19. [Amazon ECS capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-cluster-best-practice.html) — EC2, Fargate và Fargate Spot.
20. [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) — Job controller, completions, parallelism và retry.
21. [Kubernetes CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/) — lịch chạy và concurrency policy.
22. [EC2 Spot best practices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-best-practices.html) — interruption và diversification.
23. [EC2 placement groups](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/placement-groups.html) — cluster, partition và spread strategies.
24. [AWS ParallelCluster](https://docs.aws.amazon.com/parallelcluster/latest/ug/what-is-aws-parallelcluster.html) — quản lý HPC cluster và scheduler.

---

**Kết luận:** EC2 cung cấp compute và quyền kiểm soát sâu; ECS chạy container task/service với vận hành đơn giản; EKS cung cấp Kubernetes Job/CronJob và hệ sinh thái Kubernetes; AWS Batch quản lý queue, dependency, retry, fairness và capacity cho batch job trên ECS hoặc EKS. Hãy chọn theo workload, resource profile, khả năng chịu interruption, nhu cầu HPC, độ phức tạp scheduling và tổng chi phí. Kiểm thử retry, Spot interruption, output idempotency và cleanup trước khi đưa pipeline vào production.
