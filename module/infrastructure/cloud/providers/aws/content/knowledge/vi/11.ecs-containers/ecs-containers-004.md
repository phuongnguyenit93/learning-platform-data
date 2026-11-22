# ECS cluster, task definition và service

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt rõ **Amazon ECS cluster**, **task definition**, **task** và **service**; mô tả luồng từ container image đến ứng dụng đang chạy.
- Chọn mô hình chạy **AWS Fargate**, **Amazon EC2** hoặc năng lực quản lý container được ECS hỗ trợ, dựa trên yêu cầu vận hành, tài nguyên và chi phí.
- Viết một **task definition JSON** có CPU, memory, image, port, environment, secrets, log driver và IAM roles hợp lý.
- Giải thích vì sao **task execution role** và **task role** phục vụ hai nhóm quyền khác nhau, và vì sao service cần đúng cấu hình VPC, subnet, security group và endpoint.
- Triển khai **ECS service** có nhiều task qua nhiều Availability Zone, đi qua Application Load Balancer, có health checks, rolling deployment và cách rollback khi lỗi.
- Phân biệt **RunTask** một lần với service duy trì `desiredCount`, cũng như **ECS Service Auto Scaling** với scaling của các EC2 container instances.
- Theo dõi trạng thái và giải quyết lỗi `CannotPullContainerError`, `ResourceInitializationError`, task `STOPPED`, target `unhealthy` và deployment không về trạng thái ổn định.
- Đánh giá hiệu năng, tính sẵn sàng, bảo mật, dữ liệu bền vững, khả năng giám sát và chi phí của ứng dụng container trên AWS.

**Ngữ cảnh:** Bài thuộc chương **Container với ECS** trong module **CLOUD_PROVIDERS_AWS**. Khi ứng dụng Java/Spring Boot hoặc API khác được đóng gói thành container, việc hiểu ECS giúp bạn kết hợp hạ tầng **Region/AZ**, **IAM**, **VPC**, **Elastic Load Balancing**, **S3/EFS/RDS**, dịch vụ tích hợp như **SQS** và **CloudWatch** để triển khai ứng dụng an toàn, mở rộng được và có khả năng phục hồi. Bài tập trung vào ba khái niệm cốt lõi: **cluster, task definition và service**.

> **Lưu ý phiên bản:** Giao diện Console, tùy chọn Fargate, thông số task và chiến lược deployment có thể phát triển. Ví dụ dùng Linux container trên AWS Fargate với `awsvpc`, phù hợp để học mô hình. Các ARN, ID và tên tài nguyên bên dưới chỉ minh họa, cần thay bằng tài nguyên lab hợp lệ.

## 1. Bức tranh tổng thể: từ image đến service

Amazon Elastic Container Service (**Amazon ECS**) là dịch vụ orchestration giúp **chạy và quản lý container**. Thay vì đăng nhập vào từng máy để khởi động `docker run`, bạn khai báo cấu hình mong muốn; ECS phối hợp hạ tầng chạy task, theo dõi trạng thái và thay thế task khi cần.

Bốn khái niệm nền tảng:

| Khái niệm | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **Cluster** | Không gian logic chứa các service/task và cấu hình capacity để chạy chúng | `orders-prod` |
| **Task definition** | Bản thiết kế có version (revision) mô tả một hoặc nhiều container, image, tài nguyên, role, log, storage | `orders-api:7` |
| **Task** | Một **lần chạy cụ thể** của task definition, có ARN và trạng thái riêng | Task ID `a1b2...`, đang `RUNNING` |
| **Service** | Bộ quản lý duy trì số lượng task mong muốn và thực hiện deployment, health/replacement, tích hợp ALB/NLB | `orders-api-service`, `desiredCount=3` |

~~~mermaid
flowchart TB
    Dev[Nhà phát triển] --> Image[Container image]
    Image --> ECR[Amazon ECR / registry]
    ECR --> TD[Task definition family:revision]
    Cluster[ECS cluster] --> Service[ECS service: desiredCount = 3]
    TD --> Service
    Service --> T1[Task 1]
    Service --> T2[Task 2]
    Service --> T3[Task 3]
    T1 --> C1[orders-api container]
    T2 --> C2[orders-api container]
    T3 --> C3[orders-api container]
    ALB[Application Load Balancer] --> T1
    ALB --> T2
    ALB --> T3
~~~

**Cách đọc:** Image chứa chương trình và thư viện; **task definition** quy định image sẽ chạy thế nào; **task** là đơn vị đang chạy; **service** duy trì tập task; **cluster** là phạm vi tổ chức để ECS vận hành các tài nguyên này. **ALB không tự tạo task** và **task definition tự nó không khởi chạy container**.

### Ví dụ từ ứng dụng Java

Nhóm phát triển có image `orders-api:v1.0.0` chạy Spring Boot cổng 8080:

1. Build và push image vào **Amazon ECR**.
2. Đăng ký task definition `orders-api:1` (CPU, RAM, image URI, port 8080, task role, log).
3. Tạo ECS cluster và ECS service với `desiredCount=2`.
4. ECS scheduler yêu cầu chạy hai **tasks** theo task definition.
5. Nếu service gắn target group của ALB, hai tasks healthy trở thành backend của API.
6. Khi một task bị dừng ngoài dự kiến, service cố khởi chạy **task thay thế** để tiến về desiredCount.
7. Khi có image v2, đăng ký task definition revision mới và cập nhật service để triển khai.

Chỉ với **RunTask** mà không tạo service, bước 6 **không tự xảy ra như một cam kết duy trì desiredCount**.

## 2. ECS cluster: vùng tổ chức và năng lực chạy container

**Cluster** là một tài nguyên logic ở cấp **Region**, không phải mặc định là một máy chủ, một VPC hay một Kubernetes cluster. Trong một cluster có thể có nhiều services và standalone tasks dùng capacity/launch models được hỗ trợ.

Ví dụ:

~~~text
Region ap-southeast-1
└── ECS cluster: commerce-prod
    ├── Service: orders-api       → 3 tasks
    ├── Service: catalog-api      → 2 tasks
    ├── Service: worker           → 4 tasks
    └── Standalone task: data-migration (run once)
~~~

Có thể chạy nhiều service cùng cluster; việc cùng cluster **không tự cho phép** các task kết nối mạng hoặc gọi tài nguyên AWS của nhau. Quyền truy cập vẫn dựa vào **VPC, security group, IAM, DNS và cấu hình ứng dụng**.

### Cluster chứa những gì?

Tùy mô hình, cluster liên kết với:

- **Capacity providers** như `FARGATE`, `FARGATE_SPOT` hoặc provider dùng EC2 Auto Scaling group;
- **EC2 container instances** đã đăng ký ECS agent, nếu chạy kiểu EC2;
- cấu hình **Container Insights/monitoring**, tags và dịch vụ liên quan;
- các **services**, **tasks** và deployment đang được ECS quản lý.

**Không nhầm cluster với subnet:** Khi tạo **service hoặc chạy task dùng `awsvpc`**, bạn chọn subnets/security groups cho task. Một cluster có thể sử dụng nhiều subnets trong VPC theo cấu hình dịch vụ; không suy luận mọi task trong cluster cùng một subnet hoặc cùng một AZ.

### Khi nào tách cluster?

Nên cân nhắc tách cluster khi cần phân chia **môi trường** (dev/staging/prod), chính sách capacity, vận hành, phân quyền và chi phí. Nhưng **cluster không phải ranh giới bảo mật mạnh như AWS account**. Hệ thống nhạy cảm có thể cần tách tài khoản, VPC, IAM và tổ chức vận hành thay vì chỉ đặt hai service trong hai cluster.

## 3. Chọn nơi chạy task: Fargate hay EC2?

ECS điều phối task; tài nguyên chạy task có thể do AWS quản lý nhiều hơn hoặc do bạn quản trị máy chủ.

| Tiêu chí | **ECS trên AWS Fargate** | **ECS trên Amazon EC2** |
| --- | --- | --- |
| Máy chủ host | AWS quản lý hạ tầng host | Bạn quản lý fleet EC2 (AMI, patching, capacity, agent) |
| Tính tài nguyên | Cấp CPU/RAM theo task và lựa chọn cấu hình được hỗ trợ | Task sử dụng tài nguyên khả dụng trên EC2 container instances |
| Scale task | ECS Service Auto Scaling / service scheduler | ECS Service Auto Scaling **và** bảo đảm fleet EC2 còn chỗ |
| Mạng | Bắt buộc `awsvpc`, task có ENI và security group theo cấu hình | Có thể dùng `awsvpc`, `bridge`, `host` tùy OS/điều kiện |
| Kiểm soát host | Giới hạn thao tác kernel/host, không SSH host nền tảng | Có thể kiểm soát cấu hình OS, instance type, GPU, daemon/agent |
| Giá | Theo mức sử dụng vCPU/RAM/task time và thành phần bổ sung | Theo giá EC2/EBS và các tài nguyên khác; tối ưu mức độ sử dụng host |
| Phù hợp | API, web, worker, workload muốn ít vận hành host | Nhu cầu host customization, lựa chọn máy đặc thù hoặc tận dụng tải ổn định |

**Điểm khởi đầu:** Nếu ưu tiên chạy web/API mà ít phải quản trị EC2, hãy khảo sát **Fargate**. Nếu cần kiểm soát phần cứng/host hoặc muốn bin-pack nhiều container trong fleet EC2 dài hạn, khảo sát **ECS trên EC2**. AWS còn có tùy chọn capacity được quản lý khác theo phạm vi dịch vụ/Region; hãy đối chiếu tài liệu ECS hiện hành trước khi chọn.

### Capacity provider strategy

Capacity provider mô tả nguồn năng lực để ECS chạy task. Đối với Fargate thường có:

- `FARGATE`: task chạy trên nguồn capacity Fargate thông thường.
- `FARGATE_SPOT`: dùng capacity dư thừa với giá ưu đãi nhưng **có thể bị gián đoạn**, thích hợp workload chịu được retry và mất task tạm thời.

Strategy có thể đặt **base** và **weight** để phân chia cách cấp task giữa providers theo cơ chế hỗ trợ. Không bảo đảm Spot luôn có capacity hoặc 100% task sẽ được phân phối đúng tỷ lệ mọi thời điểm.

Ví dụ tư duy cho worker bất đồng bộ:

~~~text
Desired tasks: 10
Capacity strategy tham khảo:
  FARGATE       base=2, weight=1
  FARGATE_SPOT  base=0, weight=3

Mục tiêu: có nền task thường, phần còn lại tận dụng Spot khi available.
Không dùng chiến lược này nếu mọi task đều bắt buộc sống liên tục.
~~~

**Phân biệt:** Khi cấu hình service, `launchType` và `capacityProviderStrategy` là hai cách chỉ định capacity; theo AWS API, **không truyền đồng thời** cả hai trong cùng cấu hình tạo service.

### EC2 còn cần lớp scale host

Với ECS trên EC2, `desiredCount=10` không tự bảo đảm host đủ CPU/RAM/ENI/port để chạy 10 task. Có hai lớp:

1. **Service Auto Scaling:** điều chỉnh số lượng **tasks** mong muốn.
2. **Cluster capacity scaling / EC2 Auto Scaling:** duy trì số lượng và loại **EC2 container instances** đủ chỗ cho task.

Có thể dùng **capacity provider được hỗ trợ với managed scaling** để phối hợp ASG, nhưng vẫn cần đặt min/max capacity, AZ, quota, AMI, instance types và bảo mật host.

## 4. Task definition: bản thiết kế có revision, không phải task đang chạy

**Task definition** là tài liệu JSON khai báo cách ECS chạy một hoặc nhiều container. Khi đăng ký vào ECS, một **family** sẽ có **revision** tăng dần:

~~~text
orders-api:1
orders-api:2
orders-api:3
...
~~~

Mỗi revision đã đăng ký là một cấu hình cụ thể; muốn đổi image, CPU, environment, role hoặc cấu hình container, thông thường đăng ký **revision mới** rồi cập nhật service. **Sửa tag image trong registry mà không đổi task definition không phải quy trình deployment có thể audit/rollback tốt**; ưu tiên image digest hoặc tag bất biến.

### Các nhóm trường quan trọng

| Trường | Mô tả | Vấn đề thực tế |
| --- | --- | --- |
| `family` | Tên nhóm task definitions | `orders-api` |
| `requiresCompatibilities` | Kiểm tra tương thích với Fargate hoặc môi trường liên quan | `["FARGATE"]` |
| `networkMode` | Mô hình mạng; Fargate phải là `awsvpc` | Có ENI và SG cho task |
| `cpu`, `memory` | Tài nguyên cấp ở cấp task | Chọn cặp hợp lệ theo platform |
| `runtimePlatform` | OS family và CPU architecture | Linux x86_64/ARM64 theo image hỗ trợ |
| `containerDefinitions` | Image, tên container, CPU/memory, env, port, health, logs | Mọi container chính và sidecar |
| `executionRoleArn` | Quyền để ECS/agent kéo image, gửi logs, đọc secret được tham chiếu | Không phải quyền ứng dụng gọi S3 |
| `taskRoleArn` | Quyền cho mã ứng dụng trong container gọi AWS API | Least privilege theo service |
| `volumes`, `mountPoints` | Storage được task sử dụng theo loại hỗ trợ | Data tạm, EFS, EBS được quản lý theo cơ chế riêng |
| `ephemeralStorage` | Dung lượng tạm tăng thêm cho Fargate theo hỗ trợ | Không dùng như cơ chế backup |

**Fargate CPU/RAM:** phải chọn **cặp hỗ trợ**, không tự phối `cpu=256` với `memory=8192`. Một ví dụ hợp lệ cho Linux là **512 CPU units (0,5 vCPU) + 1024 MiB**; các mức lớn hơn còn phụ thuộc OS/platform version/Region và các giới hạn khác.

### Ví dụ JSON: task definition cho Spring Boot API

Giả sử đội ngũ đã tạo ECR repository, CloudWatch Logs group và hai IAM roles. File `task-definition.json`:

~~~json
{
  "family": "orders-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "runtimePlatform": {
    "operatingSystemFamily": "LINUX",
    "cpuArchitecture": "X86_64"
  },
  "executionRoleArn": "arn:aws:iam::111122223333:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::111122223333:role/ordersAppTaskRole",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:v1.0.0",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "APP_ENV",
          "value": "lab"
        }
      ],
      "secrets": [
        {
          "name": "DB_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:orders-db-password-xxxxxx"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/orders-api",
          "awslogs-region": "ap-southeast-1",
          "awslogs-stream-prefix": "orders"
        }
      },
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "curl -fsS http://localhost:8080/health/ready || exit 1"
        ],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
~~~

**Đọc cấu hình:**

- `family` tạo ra các revision `orders-api:n`.
- Task dùng **0,5 vCPU, 1 GiB RAM**; đây là resource cho **toàn task**, không phải mỗi container.
- Image lấy từ ECR; container lắng nghe `8080`.
- `APP_ENV` không chứa dữ liệu bí mật; **DB_PASSWORD** được ECS chèn từ Secrets Manager khi tạo task theo tích hợp được hỗ trợ.
- `awslogs` gửi container logs về CloudWatch Logs group đã chuẩn bị. Nếu log group chưa tồn tại hoặc execution role thiếu quyền, task có thể lỗi khởi tạo.
- Container health check gọi `curl` **bên trong image**; image phải có công cụ `curl` và endpoint `/health/ready`. Nếu image tối giản không có `curl`, thay health command bằng phương án thật sự có trong image.
- `essential=true` nghĩa container quan trọng: khi container này dừng, task không thể tiếp tục như một ứng dụng lành mạnh và sẽ kết thúc theo vòng đời ECS.

**Đây là JSON minh họa có cấu trúc đầy đủ nhưng không tự tạo tài nguyên phụ thuộc.** IAM roles, ECR image, CloudWatch log group, secret, subnet, security group và ALB target group phải tồn tại và có quyền tương thích trước khi chạy.

### Một task có thể có nhiều container

Ví dụ web API và log/telemetry sidecar trong cùng task:

~~~text
Task: orders-api:3
  ├── container "orders-api"  (essential)
  └── container "telemetry"   (sidecar)
~~~

Containers cùng task trên `awsvpc` chia sẻ network namespace/ENI và có thể giao tiếp qua **localhost**, nhưng có tài nguyên, lifecycle, health checks và volume mounts riêng theo cấu hình. Đừng chia mỗi microservice độc lập thành sidecar chỉ vì muốn chạy chung: scaling, triển khai và lỗi của chúng sẽ bị ràng buộc cùng task.

## 5. IAM: task role khác task execution role

Đây là một trong những nhầm lẫn gây lỗi phổ biến nhất với ECS.

| IAM role | Ai sử dụng? | Quyền điển hình |
| --- | --- | --- |
| **Task execution role** | ECS container/Fargate agent làm công việc khởi tạo và vận hành hỗ trợ | Kéo image từ ECR, ghi `awslogs`, đọc secret trong **task definition** |
| **Task role** | Mã ứng dụng đang chạy trong container | `s3:GetObject`, `sqs:SendMessage`, `dynamodb:PutItem` hoặc API AWS cần dùng |
| **Container instance role** | ECS agent trên EC2 host trong mô hình ECS on EC2 | Cho EC2 đăng ký cluster, làm các API agent cần |
| **Service-linked / infrastructure roles** | Dịch vụ ECS trong các tích hợp cụ thể | Quản lý ELB, hạ tầng EBS/ECS service connect theo trường hợp |

### Ví dụ tách quyền

API cần:

- **Kéo image ECR:** task execution role.
- **Gửi logs CloudWatch:** task execution role.
- **ECS chèn `DB_PASSWORD` từ Secrets Manager vào container:** task execution role cần `secretsmanager:GetSecretValue`; thêm quyền KMS phù hợp nếu secret dùng customer managed key.
- **Ứng dụng Java trực tiếp gọi S3 GetObject:** task role.
- **Ứng dụng Java trực tiếp gọi Secrets Manager runtime:** task role, khác với việc ECS chèn secret lúc tạo task.

Có thể bắt đầu từ AWS managed policy hỗ trợ ECS task execution role cho các thao tác chuẩn rồi thêm **quyền tối thiểu theo secret/log/image thực tế**. Không gắn `AdministratorAccess` để tránh xử lý policy.

### Ví dụ identity policy cho task role chỉ đọc báo cáo S3

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::orders-reports-example/reports/*"
    }
  ]
}
~~~

Nếu object SSE-KMS bằng customer managed key, còn cần xét **kms:Decrypt**, IAM/key policy/bucket policy và Region. Quyền task role **không thay** security group hoặc route mạng tới S3 endpoint.

### Trust policy ECS role

Đối với các IAM roles được ECS task assume theo tích hợp chuẩn, trust policy cần cho phép principal dịch vụ phù hợp như `ecs-tasks.amazonaws.com` và hành động `sts:AssumeRole`. IAM permission quyết định **role được làm gì**, trust policy quyết định **ai/cái gì được assume role**. Có thể dùng điều kiện `aws:SourceAccount`, `aws:SourceArn` theo hướng dẫn IAM ECS để giảm rủi ro confused deputy.

## 6. Task: một lần chạy, có trạng thái và vòng đời riêng

Task là **instance thực tế** của task definition. Một lần gọi `RunTask` tạo một hoặc nhiều task, tùy `count` và capacity. Mỗi task có ID, ARN, last status, desired status và các chi tiết container/attachments.

Vòng đời khái niệm:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> PENDING
    PENDING --> ACTIVATING
    ACTIVATING --> RUNNING
    RUNNING --> DEACTIVATING
    DEACTIVATING --> STOPPING
    STOPPING --> DEPROVISIONING
    DEPROVISIONING --> STOPPED
    PENDING --> STOPPED: Không thể khởi tạo
~~~

Sơ đồ minh họa các trạng thái phổ biến; không phải mọi môi trường/API đều hiển thị từng trạng thái hoặc chuyển theo cùng chuỗi thời gian. Khi xử lý lỗi, đọc **`lastStatus`**, **`desiredStatus`**, **`stopCode`**, **`stoppedReason`** và `containers[].reason/exitCode` từ `DescribeTasks`.

### Standalone task

`RunTask` phù hợp:

- Job xử lý dữ liệu một lần;
- database migration theo quy trình có giám sát;
- tác vụ được EventBridge Scheduler/Step Functions kích hoạt;
- worker batch được điều phối riêng.

Nếu task dừng thành công hoặc thất bại, **ECS không mặc định chạy lại để giữ desired count** như một service. Hệ thống điều phối job phải quyết định retry, idempotency, DLQ và cảnh báo.

### Service-managed task

ECS service cố duy trì `desiredCount`; scheduler thay task bị dừng và có thể đăng ký task mới với target group. Tuy nhiên việc thay không đảm bảo ngay lập tức nếu:

- không đủ Fargate capacity/EC2 capacity, IP hoặc quota;
- image không kéo được;
- IAM/secrets/logs bị lỗi;
- ứng dụng health check không đạt;
- cấu hình network/ALB sai.

**Task `RUNNING` không đồng nghĩa API sẵn sàng nhận traffic.** ECS container health, ALB target health và readiness của ứng dụng là các tín hiệu cần phân biệt.

## 7. ECS service: duy trì trạng thái mong muốn

Một **ECS service** khai báo và theo dõi:

- cluster và service name;
- task definition revision đang dùng;
- launch type/capacity provider strategy;
- `desiredCount` và service scheduling/deployment config;
- network configuration (subnets, security groups, public IP theo mô hình);
- load balancer, target group và service discovery nếu có;
- deployment, circuit breaker, alarm/rollback và scaling theo cấu hình;
- tags, security, placement/availability và lifecycle.

### Service scheduler làm gì?

Giả sử `desiredCount=3`:

~~~text
Trạng thái bình thường:  RUNNING 3 / desired 3
Một task bị dừng:       RUNNING 2 / desired 3
ECS lên lịch thay thế:  PENDING 1, RUNNING 2
Task mới đã sẵn sàng:  RUNNING 3 / desired 3
~~~

Nếu có deployment mới, ECS có thể tạm chạy **nhiều hơn hoặc ít hơn desired** trong các giới hạn `minimumHealthyPercent` và `maximumPercent`, tùy strategy và capacity thực tế.

### Một service có thể chạy task không qua load balancer

Ví dụ worker SQS:

~~~text
ECS service: invoice-worker
desiredCount=4
Tasks: poll SQS → xử lý idempotent → ghi S3/RDS
Không cần ALB để nhận HTTP từ Internet.
~~~

Ngược lại, web/API cần phân phối HTTP thường tích hợp **ALB**, nhưng ECS service **không bắt buộc** gắn ALB mới hợp lệ.

## 8. Networking với Fargate: awsvpc, ENI và các AZ

Với Fargate, `awsvpc` là network mode bắt buộc. Mỗi task có **elastic network interface (ENI)** và địa chỉ IP từ subnet được chọn; task dùng security groups áp dụng cho ENI của nó.

### Kiến trúc web API hai AZ

~~~mermaid
flowchart TB
    User[Browser / mobile] --> DNS[Route 53 / DNS]
    DNS --> ALB[ALB internet-facing, HTTPS 443]
    subgraph VPC["VPC: 10.20.0.0/16 trong Region"]
      subgraph A["AZ A"]
        PA[Public subnet A: ALB node]
        TA[Private subnet A: Fargate task ENI]
      end
      subgraph B["AZ B"]
        PB[Public subnet B: ALB node]
        TB[Private subnet B: Fargate task ENI]
      end
      ALB --> TG[Target group type ip]
      TG -->|TCP 8080| TA
      TG -->|TCP 8080| TB
    end
    TA --> DB[(RDS Multi-AZ)]
    TB --> DB
    TA --> S3[(S3 / SQS qua endpoint phù hợp)]
    TB --> S3
    ECS[ECS service / desiredCount 2] -. Duy trì tasks .-> TA
    ECS -. Duy trì tasks .-> TB
~~~

**Lưu ý:** sơ đồ là quan hệ logic; ALB được kích hoạt trong các AZ và định tuyến đến target theo cơ chế ELB. Các task không cần public IP để nhận request **từ ALB** nếu route và SG cho phép.

### Security groups theo hướng lưu lượng

| Thành phần | Quy tắc tối thiểu tham khảo |
| --- | --- |
| **ALB SG** | Inbound TCP/443 từ client được phép; outbound TCP/8080 đến task SG |
| **Task SG** | Inbound TCP/8080 từ **ALB SG**, không mở cho toàn Internet |
| **DB SG** | Inbound port DB, ví dụ TCP/5432, từ **task SG** |
| **Task outbound** | Chỉ tới DB/endpoints/API mà ứng dụng và khởi tạo task thực sự cần |

**Fargate trong private subnet** thường không có public IP (`assignPublicIp=DISABLED`). Nhưng việc kéo image ECR, lấy secret, gửi logs và gọi dịch vụ AWS vẫn cần **đường mạng outbound**:

- Có thể dùng **NAT Gateway** để truy cập public service endpoints qua Internet egress;
- hoặc **VPC endpoints** cho ECR API, ECR Docker registry, S3 (khi cần tải layer), CloudWatch Logs, Secrets Manager và dịch vụ liên quan, tùy workload/platform;
- cần kiểm tra **private DNS**, endpoint security groups, route table/NACL, bucket/endpoint policy và DNS resolver.

**Thiếu đường đi tới ECR/Secrets Manager/CloudWatch có thể khiến task bị `ResourceInitializationError`** dù task definition/IAM roles đã đúng.

### Target group type khi dùng awsvpc

Vì task có **ENI/IP riêng**, khi gắn ECS service dùng `awsvpc` với ALB hoặc NLB, target group phải có **target type = `ip`**, không phải `instance`.

Nếu bạn dùng EC2 launch type với network mode `bridge` trong các kịch bản được hỗ trợ, cách đăng ký target/port mapping có thể khác. **Không copy nguyên target group kiểu `instance` từ bài EC2 ASG sang Fargate awsvpc**.

### DHCP và DNS

Task mới dùng cấu hình DNS của VPC khi tạo. Khi VPC thay DHCP option set, task `awsvpc` đã chạy có thể không tự nhận cấu hình mới: cần thiết kế deployment/task replacement để áp dụng thiết lập. DNS phân giải đúng chưa bảo đảm kết nối thành công; tiếp tục kiểm tra SG, route, endpoint, IAM và ứng dụng.

## 9. Tích hợp ALB, health checks và khám phá dịch vụ

### ALB ở phía trước API

Một ECS service phục vụ HTTP thường liên kết:

~~~text
HTTPS listener 443 (ALB)
   └── target group "orders-api-tg", target type = ip
        ├── task ENI 10.20.10.21 : 8080
        └── task ENI 10.20.20.29 : 8080
~~~

Khi service scale out hoặc deployment task revision mới, ECS cập nhật đăng ký/deregister target cho target group tương ứng. Vì IP task thay đổi qua lifecycle, **không hardcode private IP task** trong client.

### Ba mức health check

| Lớp | Phát hiện | Lưu ý |
| --- | --- | --- |
| **Container health check** trong task definition | Command bên trong container có chạy thành công không | Cần tool trong image; `startPeriod` giúp thời gian khởi động |
| **ALB target group health check** | Target trả lời HTTP/gRPC theo cấu hình từ ALB | Kiểm tra port, path, matcher, SG ALB → task |
| **Service/deployment health** | Scheduler quan sát trạng thái task, container/LB health và deployment | `RUNNING` có thể chưa đủ để thành target healthy |

Ví dụ `/health/ready` trả 200 chỉ khi app đã lắng nghe, hoàn tất migration cần thiết và kết nối dependency quan trọng đúng mức. Nếu readiness phụ thuộc tất cả dịch vụ phụ bất ổn, toàn bộ task có thể đồng loạt unhealthy dù thay task không giải quyết được lỗi; hãy thiết kế health dựa trên khả năng phục vụ thực sự.

### Service-to-service communication

Giữa các ECS services nội bộ, có thể dùng:

- **ECS Service Connect** cho khám phá/tên dịch vụ và cơ chế quan sát/đường kết nối trong phạm vi hỗ trợ;
- **AWS Cloud Map** service discovery với DNS/registration phù hợp;
- **Internal ALB/NLB** nếu cần một endpoint HTTP/TCP ổn định và routing/load balancing riêng.

**Không giả định hai service trong cùng cluster tự phân giải được tên nhau** bằng service name khi chưa cấu hình service discovery hoặc endpoint. Cần lập kế hoạch namespace, DNS, SG và các cổng nội bộ.

## 10. Rolling deployment: thay task an toàn

Một ECS service có thể thay revision đang chạy bằng revision mới theo deployment configuration. Với **rolling deployment**, scheduler thay dần task cũ bằng task mới và sử dụng các thông số:

| Tham số | Ý nghĩa trong rolling update | Ví dụ |
| --- | --- | --- |
| `desiredCount` | Số task mong muốn sau deployment | 4 |
| `minimumHealthyPercent` | Mức healthy tối thiểu so với desired, làm tròn lên | 100% → ít nhất 4 healthy theo quy tắc áp dụng |
| `maximumPercent` | Mức tổng task tối đa trong deployment so với desired, làm tròn xuống | 200% → tối đa 8 task trong các trạng thái được tính |
| `healthCheckGracePeriodSeconds` | Khoảng thời gian service bỏ qua một số kiểm tra health từ LB/VPC Lattice/container theo cơ chế hỗ trợ khi task khởi tạo | Ví dụ 90 giây sau khi task bắt đầu |
| `deploymentCircuitBreaker` | Phát hiện rolling deployment không đạt steady state; có thể rollback | `enable=true`, `rollback=true` |

Mức mặc định phổ biến với rolling update là **minimum 100%, maximum 200%**, nhưng không xem mặc định của mọi deployment strategy là giống nhau; kiểm tra API/Console.

### Ví dụ thay 4 task

Giả sử `desiredCount=4`, `minimumHealthyPercent=100`, `maximumPercent=200` và còn capacity:

~~~mermaid
sequenceDiagram
    participant Dev as CI/CD
    participant ECS as ECS service scheduler
    participant F as Fargate capacity
    participant LB as ALB target group
    Dev->>ECS: Update service sang orders-api:8
    ECS->>F: Tạo tasks revision 8
    F-->>ECS: Tasks RUNNING
    ECS->>LB: Đăng ký IP mới, chờ healthy
    LB-->>ECS: Targets mới healthy
    ECS->>LB: Deregister/drain tasks revision 7
    ECS->>F: Dừng tasks revision 7
    ECS-->>Dev: Deployment tới steady state
~~~

Nếu revision mới lỗi do image, secrets, port, memory hoặc health check, **circuit breaker** có thể đánh dấu deployment thất bại và **rollback về deployment đã hoàn thành trước đó** khi được bật và có bản trước đủ điều kiện.

**Không phải mọi kiểu deployment có cùng rollback configuration**: ECS hiện có các strategy như rolling, blue/green, linear và canary theo controller/khả năng hỗ trợ. Khi dùng triển khai nâng cao hoặc CodeDeploy/external controller, cách thiết lập health, traffic shift và rollback có thể khác. Bài tập trung vào rolling.

### Chú ý desired = 1 hoặc capacity thiếu

Nếu min healthy = 100%, max percent = 100% và `desiredCount=1`, service có thể không có khoảng trống để thêm task mới cũng không được dừng task cũ, khiến deployment mắc kẹt. Cấu hình nên cho phép ít nhất một task **được tạo hoặc dừng** theo strategy, có đủ capacity và quota.

**Deregistration delay** của ALB, **container stop timeout** và graceful shutdown của ứng dụng ảnh hưởng request đang chạy. Đừng chỉ update task definition rồi coi deployment an toàn.

## 11. ECS Service Auto Scaling: tăng số task theo nhu cầu

**ECS Service Auto Scaling** dựa trên **Application Auto Scaling** để tự điều chỉnh **desired task count** của một ECS service. Các lựa chọn có thể gồm target tracking, step scaling, scheduled scaling và những cơ chế được hỗ trợ khác.

### Metrics thường dùng

| Metric | Dùng khi | Dấu hiệu chọn sai |
| --- | --- | --- |
| **ECSServiceAverageCPUUtilization** | CPU tương quan với tải API/worker | CPU thấp nhưng latency tăng do DB/network |
| **ECSServiceAverageMemoryUtilization** | RAM phản ánh sức ép memory của task | Memory cao do cache hợp lệ, scale task không làm giảm footprint mỗi task |
| **ALBRequestCountPerTarget** | Web/API qua ALB, request tương đối đồng đều về độ nặng | Long polling, request rất không đều hoặc app không chạy sau ALB |
| **Custom metric** (queue backlog per task, thời gian chờ) | Worker xử lý SQS và tải không đến qua HTTP | Thiếu cơ chế publish metric, muốn scale nhưng số đo không phản ánh backlog |

Ví dụ:

~~~text
Service orders-api:
  min tasks = 2
  max tasks = 10
  target tracking = CPU trung bình mục tiêu 60%

Khi CPU cao kéo dài → tăng desiredCount nếu điều kiện đủ.
Khi CPU giảm ổn định → giảm desiredCount theo policy.
~~~

Đây là ví dụ để học, **không phải khuyến nghị 60% cho mọi ứng dụng**. Cần benchmark CPU, request rate, memory, concurrency, latency p95/p99 và tác động downstream.

### Hai tầng scaling khi dùng ECS trên EC2

~~~mermaid
flowchart TD
    L[CloudWatch workload metric] --> S[Service Auto Scaling]
    S --> D[Tăng desired task count]
    D --> H{EC2 cluster có đủ capacity?}
    H -->|Có| T[Tasks mới RUNNING]
    H -->|Không| P[Tasks chờ placement / capacity]
    P --> C[Capacity provider managed scaling / EC2 ASG]
    C --> T
~~~

Nếu chỉ tăng desired task mà EC2 hosts thiếu CPU/RAM/ENI/port hoặc placement constraints, task không thể được đặt. Trong Fargate, không quản trị EC2 host trực tiếp, nhưng vẫn có thể gặp lỗi capacity availability, IP/quota và limits.

### Tại sao không scale mọi thứ vô hạn?

- App thêm task nhưng **RDS connection pool hoặc database throughput** vẫn là nút nghẽn.
- NAT/ALB/VPC endpoints, S3/SQS/KMS API quotas và chi phí tăng theo lưu lượng.
- Spot interruption/placement làm capacity biến động.
- API giữ session/file trên local disk không thể chuyển qua task mới an toàn.

Trước khi tăng max tasks, cần có **load test** và điểm giới hạn downstream.

## 12. Multi-AZ và khả năng phục hồi của ECS service

Một service đặt tasks trong **subnets của ít nhất hai AZ** giúp giảm phạm vi ảnh hưởng khi một AZ bị lỗi. Tuy nhiên **chọn hai subnet không tự đảm bảo mọi lúc có task khỏe ở cả hai AZ**.

Cần xét:

1. **Placement:** ECS scheduler phân bổ theo capacity, availability và policy được hỗ trợ; kiểm tra task chạy tại những AZ nào.
2. **Desired count:** Với hai tasks trong hai AZ, nếu một task/AZ lỗi thì có thể còn một task, nhưng workload có thể quá tải.
3. **ALB:** Bật tối thiểu hai AZ, target group đúng kiểu `ip`, health checks hoạt động.
4. **Dữ liệu:** RDS Multi-AZ, S3, EFS/backup hoặc thiết kế replication đúng RTO/RPO; không để thông tin nghiệp vụ duy nhất trong một task.
5. **Capacity dự phòng:** Số tasks còn lại phải đủ phục vụ lượng traffic mà tổ chức muốn duy trì khi một AZ biến mất, hoặc chấp nhận thời gian scale-out.
6. **Quotas/IP:** Private subnets cần đủ địa chỉ IP, ENI và service limits cho cả deployment surge.
7. **Graceful failure:** client timeout, retries/backoff, circuit breaker và idempotency khi task bị dừng hoặc thay thế.

### Bài toán capacity đơn giản

Giả sử API cần **240 RPS**, một task đã benchmark xử lý bền vững **80 RPS** trong mức p95 latency yêu cầu.

Bình thường:

\[
N_{\text{minimum}}=\lceil 240/80\rceil=3\ \text{tasks}
\]

Nhưng ba tasks phân bố qua hai AZ là **không đủ** để chịu lỗi một AZ mà giữ cùng mức tải. Nếu muốn **một AZ còn lại** phục vụ đủ 240 RPS ngay lập tức, cần **ít nhất 3 task khỏe trong mỗi AZ**, tức **6 tasks** bình thường; còn nên dự phòng thêm cho peak và deploy theo SLO.

Đây là phép tính **capacity theo giả định**, không có nghĩa service tự bảo đảm số task mỗi AZ. Cần kiểm thử placement và failure behavior, điều chỉnh theo metrics thực tế và chi phí.

### Đừng nhầm failover task với backup dữ liệu

Nếu một task API bị `STOPPED`, ECS service có thể tạo task mới. Nhưng nếu file hóa đơn chỉ nằm trong ephemeral storage của task cũ, file có thể mất. **ECS service xử lý vòng đời compute, không tự backup dữ liệu ứng dụng**. Cần S3/EFS/database và kế hoạch phục hồi dữ liệu riêng.

## 13. Storage trong task: ephemeral, EFS và EBS

| Storage | Đặc tính | Phù hợp với |
| --- | --- | --- |
| **Ephemeral storage của Fargate** | Dữ liệu tạm gắn lifecycle task, bị xóa khi task dừng | Cache, scratch, file tạm có thể tái tạo |
| **Amazon EFS** | Shared filesystem qua NFS được quản lý, nhiều task/instance có thể cùng mount theo điều kiện | File dùng chung, content, upload cần POSIX |
| **Amazon EBS volumes cho ECS tasks** | Block volume được quản lý theo khả năng ECS hỗ trợ, thường liên quan task/AZ và cấu hình lúc deploy | Stateful task chuyên biệt, dữ liệu cần block device |
| **S3** | Object storage qua API, không phải filesystem POSIX gắn trực tiếp | Ảnh, hóa đơn, log, backup, data lake |
| **RDS/Aurora/DynamoDB** | Dịch vụ dữ liệu được quản lý | Dữ liệu nghiệp vụ có query, consistency và chính sách HA phù hợp |

**Fargate Linux platform 1.4.0 hoặc mới hơn** thường có **20 GiB ephemeral storage mặc định**, có thể cấu hình tăng **tối đa 200 GiB** cho những trường hợp hỗ trợ; image đã tải và giải nén cũng chiếm dung lượng này. Storage tạm **không phải backup** và không tự chuyển sang task mới.

**EBS cho ECS tasks** có khả năng sử dụng khác EBS root disk của EC2 host: cần kiểm tra các loại deployment/volume configuration được ECS hỗ trợ, quyền **ECS infrastructure role**, AZ, chi phí và lifecycle. Không mặc định rằng một volume EBS bất kỳ có thể chia sẻ để nhiều Fargate tasks cùng mount đa AZ. Nếu yêu cầu shared file đa AZ, EFS thường là lựa chọn dễ hiểu hơn.

## 14. Bảo mật và cấu hình cho ứng dụng trong ECS

### Image và supply chain

- Lưu image trong ECR/registry được quản lý; quản lý ai có quyền push/pull.
- Dùng **immutable tags hoặc image digest** để deployment lặp lại và audit được.
- Scan image và giảm số package, chạy container **không root** khi khả thi.
- Chọn CPU architecture khớp image (`X86_64` vs `ARM64`), patch image nền và secret libraries.
- Không nhúng password hoặc AWS access key trong Dockerfile/image.

### Secrets

- Sử dụng **AWS Secrets Manager** hoặc **SSM Parameter Store** theo yêu cầu.
- Khi ECS inject secret vào environment của container, execution role cần đọc secret; **rotation ở Secrets Manager không có nghĩa biến môi trường trong task đang chạy tự đổi**, thường phải triển khai task mới.
- Secret được đưa vào biến môi trường vẫn có nguy cơ lộ qua debug dump, process introspection/logging bên trong container; áp dụng phân quyền và log hygiene.
- Nếu app tự lấy secret runtime, cấp quyền ở **task role** phù hợp.

### IAM và mạng

- Tách **task role** khỏi **execution role**; chỉ quyền tối thiểu trên S3/SQS/DB/KMS.
- Đặt API tasks trong **private subnets**, chỉ mở backend port từ ALB SG khi cần.
- Sử dụng TLS tới ALB và cân nhắc TLS tới backend/DB, bảo vệ certificate/connection string.
- Dùng SG/VPC endpoint policies và IAM cùng nhau; **đường mạng có sẵn không cấp quyền API**.
- Với ECS Exec để debug, kiểm soát quyền dùng SSM channels, audit, encryption và chính sách tắt/mở; không dùng ECS Exec làm phương thức vận hành bình thường của ứng dụng.

### IAM account boundary

ECS cluster ở cùng account **không cách ly tài nguyên tốt bằng tách AWS account**. Với prod và dev hoặc dữ liệu có mức phân loại khác nhau, cân nhắc account/VPC/role/key policy riêng. Sự khác biệt giữa task role và execution role càng quan trọng khi nhiều nhóm dùng chung môi trường.

## 15. Quan sát: đọc log, metrics, events và trạng thái task

Trong ECS, điều tra lỗi nên kết hợp **ECS service events**, **DescribeTasks**, **CloudWatch Logs/Metrics** và log load balancer. Không kết luận nguyên nhân chỉ từ một dòng `STOPPED`.

| Nguồn | Thông tin hữu ích | Cạm bẫy |
| --- | --- | --- |
| **ECS task status / stoppedReason** | Vì sao task không chạy hoặc bị dừng | Thông báo có thể chỉ ra lớp lỗi, cần đọc container reason/exit code |
| **ECS service events** | Không đặt được task, ALB unhealthy, deployment bắt đầu/thất bại | Không phải mọi lỗi ứng dụng được thể hiện đầy đủ |
| **CloudWatch Logs (awslogs)** | stdout/stderr, stack trace, ứng dụng Java, bootstrap | Thiếu log có thể do container chưa khởi tạo hoặc execution role/network |
| **CloudWatch ECS CPU/Memory** | Mức sử dụng CPU/RAM theo cluster/service/task tương ứng | CPU thấp không chứng minh ứng dụng khỏe |
| **Container Insights** | Quan sát sâu hơn ở cấp ECS/task/container khi bật | Chi phí thu thập và phạm vi metrics phụ thuộc cấu hình |
| **ALB target health / 5xx / latency** | API có nhận traffic và phản hồi đúng không | Target healthy không đảm bảo mọi endpoint nghiệp vụ đúng |
| **CloudTrail** | Ai đăng ký task definition, cập nhật service, thay quyền | Không thay container application logs |
| **VPC Flow Logs / Resolver logs** | Hỗ trợ điều tra kết nối và DNS | Network ACCEPT không chứng minh HTTP/DB thành công |

### Tối thiểu cần theo dõi

- **RunningTaskCount so với DesiredTaskCount**; deployment không ổn định kéo dài.
- **CPU/Memory utilization**, OOM/exit code, error rate và application p95/p99 latency.
- **ALB HealthyHostCount**, 5xx, target connection errors.
- **Deployment failures**, task launch/capacity errors, secrets access và log delivery errors.
- **SQS queue backlog** cho worker, DB connection saturation và các dependencies.
- **Chi phí Fargate/EC2, NAT, ALB, CloudWatch và data transfer** theo tags/environment.

Đặt log retention và kiểm soát quyền truy cập log có chứa thông tin nghiệp vụ; tách metric cảnh báo hệ thống (CPU) khỏi chỉ số chất lượng dịch vụ (API lỗi, độ trễ).

## 16. Thực hành qua AWS Console: triển khai Orders API hai AZ

> **Môi trường lab:** Dùng account, Region và VPC lab có quyền thích hợp. Bạn cần một container image thật, IAM roles, security groups, ECR, CloudWatch log group; có thể phát sinh chi phí Fargate, ALB, public IP/NAT/VPC endpoints và logs. Đặt budget và dọn tài nguyên khi kết thúc. Không thực hiện trực tiếp trên production nếu chưa kiểm tra thay đổi.

### Bước 1 — Chuẩn bị image và quyền

1. Build ứng dụng trả lời `GET /health/ready` bằng HTTP 200 khi hoàn toàn sẵn sàng.
2. Push image `orders-api:v1.0.0` lên **Amazon ECR**; ghi lại URI và architecture.
3. Tạo `ecsTaskExecutionRole` có quyền pull image, ghi logs và đọc secret cần cho task definition.
4. Tạo `ordersAppTaskRole` có quyền API ứng dụng (S3/SQS...) với resource ARN cụ thể.
5. Tạo CloudWatch Logs group `/ecs/orders-api`; chuẩn bị secret nếu task dùng.

### Bước 2 — Chuẩn bị VPC và ALB

Giả định VPC có:

- `public-a`, `public-b`: hai subnets ở hai AZ, dùng cho **ALB internet-facing**.
- `private-app-a`, `private-app-b`: hai subnets ở hai AZ, dùng cho **Fargate tasks**.
- `sg-alb`: inbound HTTPS 443 từ client hợp lệ; outbound tới `sg-orders-tasks` TCP 8080.
- `sg-orders-tasks`: inbound TCP 8080 từ `sg-alb`, outbound theo API/DB/log needs.
- Đường egress phù hợp để tasks kéo ECR image và sử dụng logs/secrets, qua NAT hoặc VPC endpoints hỗ trợ.

Tạo **ALB** với HTTPS listener/ACM theo nhu cầu, **target group loại `ip`**, port 8080, HTTP health check `/health/ready`.

### Bước 3 — Tạo ECS cluster

ECS Console → **Clusters → Create cluster**. Chọn cấu hình cluster/capacity theo mô hình **Fargate** phù hợp môi trường. Tên `orders-lab`.

**Quan trọng:** Tạo cluster không tự chạy container; bạn cần task definition và service hoặc RunTask.

### Bước 4 — Đăng ký task definition

ECS Console → **Task definitions → Create new task definition**. Điền:

- Fargate, Linux, `awsvpc`;
- `0.5 vCPU`, `1 GiB memory`;
- image ECR URI, container name `orders-api`, port 8080;
- execution role và task role;
- environment/secrets/log configuration;
- container health check có lệnh thực sự tồn tại trong image.

Sau khi tạo, ghi lại `orders-api:1` (hoặc revision thực) và so lại JSON.

### Bước 5 — Tạo ECS service

Trong cluster `orders-lab` → **Services → Create**:

- Compute: Fargate hoặc capacity provider strategy tương ứng;
- Task definition `orders-api:1`;
- Service name `orders-api`, **desired tasks = 2**;
- Subnets `private-app-a` và `private-app-b`, SG của task, public IP disabled;
- Load balancing: ALB/target group `ip` đã chuẩn bị, container name `orders-api`, port 8080;
- Health check grace period phù hợp thời gian boot thực;
- Deployment rolling, circuit breaker/rollback nếu hỗ trợ và phù hợp.

Chờ tasks vào `RUNNING`, container healthy và ALB targets healthy; kiểm tra `https://<alb-dns>/health/ready` từ client lab.

### Bước 6 — Triển khai phiên bản mới

1. Build/push image `v1.0.1`.
2. Đăng ký **task definition revision mới** có image URI/tag hoặc digest mới.
3. **Update service** tham chiếu revision mới.
4. Theo dõi deployment, task health, ALB targets, logs và lỗi.
5. Khi triển khai lỗi, xem ECS service events/circuit breaker và phiên bản trước; không tăng desiredCount vô hạn chỉ để che lỗi.

### Bước 7 — Kiểm tra khả dụng nhiều AZ

Xem `DescribeTasks` và ENI/subnet/AZ thực; thử một task bị dừng trong lab và xác minh service tạo task mới. Kiểm tra số healthy tasks, latency và tác động lúc thay. **Không chủ động phá hạ tầng AZ thật** để mô phỏng outage; dùng phương pháp thử failure được phê duyệt.

## 17. Thực hành AWS CLI: cluster, task definition và service

Các ID, ARN và tên sau là **giả định**. Người học phải thay bằng giá trị của account/VPC/Region lab. Ví dụ lệnh được viết theo AWS CLI v2; trên Windows PowerShell, nên dùng file JSON thay vì các dòng quote phức tạp.

### 17.1. Kiểm tra caller và tạo cluster

~~~bash
aws sts get-caller-identity --profile lab

aws ecs create-cluster \
  --cluster-name orders-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

Xem cluster:

~~~bash
aws ecs describe-clusters \
  --clusters orders-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

### 17.2. Đăng ký task definition

Lưu JSON ở mục 4 thành `task-definition.json`, đảm bảo image/role/log/secret thật đã tồn tại:

~~~bash
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json \
  --region ap-southeast-1 \
  --profile lab

aws ecs describe-task-definition \
  --task-definition orders-api \
  --region ap-southeast-1 \
  --profile lab
~~~

Đọc `taskDefinitionArn` và `revision`; nếu mới đăng ký ở family rỗng, revision đầu là 1. Nếu family từng tồn tại, revision có thể lớn hơn, **không hardcode version khi deploy thực**.

### 17.3. Tạo service bằng JSON

Lưu ví dụ sau thành `service.json`; điều kiện tiên quyết là target group **đã được gắn với ALB**, đúng VPC và `targetType=ip`.

~~~json
{
  "cluster": "orders-lab",
  "serviceName": "orders-api",
  "taskDefinition": "orders-api:1",
  "desiredCount": 2,
  "launchType": "FARGATE",
  "platformVersion": "LATEST",
  "networkConfiguration": {
    "awsvpcConfiguration": {
      "subnets": [
        "subnet-0123456789abcdef0",
        "subnet-0fedcba9876543210"
      ],
      "securityGroups": [
        "sg-0123456789abcdef0"
      ],
      "assignPublicIp": "DISABLED"
    }
  },
  "loadBalancers": [
    {
      "targetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/orders-api-tg/0123456789abcdef",
      "containerName": "orders-api",
      "containerPort": 8080
    }
  ],
  "healthCheckGracePeriodSeconds": 90,
  "deploymentConfiguration": {
    "minimumHealthyPercent": 100,
    "maximumPercent": 200,
    "deploymentCircuitBreaker": {
      "enable": true,
      "rollback": true
    }
  }
}
~~~

Chạy:

~~~bash
aws ecs create-service \
  --cli-input-json file://service.json \
  --region ap-southeast-1 \
  --profile lab
~~~

**Không truyền đồng thời** `launchType` và `capacityProviderStrategy` trong yêu cầu này. Nếu chuyển qua capacity providers, cần sửa đúng trường và kiểm tra provider đã liên kết cluster. Với container task definition không trỏ image hợp lệ hoặc không có subnet egress, service tạo ra nhưng tasks có thể liên tục thất bại.

### 17.4. Đọc trạng thái service và tasks

~~~bash
aws ecs describe-services \
  --cluster orders-lab \
  --services orders-api \
  --region ap-southeast-1 \
  --profile lab

aws ecs list-tasks \
  --cluster orders-lab \
  --service-name orders-api \
  --region ap-southeast-1 \
  --profile lab
~~~

Lấy task ARN thực rồi mô tả:

~~~bash
aws ecs describe-tasks \
  --cluster orders-lab \
  --tasks arn:aws:ecs:ap-southeast-1:111122223333:task/orders-lab/0123456789abcdef0123456789abcdef \
  --region ap-southeast-1 \
  --profile lab
~~~

Khi service ổn định, nên kiểm tra:

- `runningCount` và `desiredCount`;
- `deployments`, `events`, target health;
- các task ENI/subnet/AZ;
- container `lastStatus`, `healthStatus`, `exitCode` nếu có.

### 17.5. Cập nhật task definition revision mới

Sau khi push image v2 và đăng ký revision `orders-api:2` (giá trị thực có thể khác):

~~~bash
aws ecs update-service \
  --cluster orders-lab \
  --service orders-api \
  --task-definition orders-api:2 \
  --region ap-southeast-1 \
  --profile lab
~~~

Nếu image được trỏ bằng mutable tag nhưng task definition không đổi, có thể dùng `--force-new-deployment` để yêu cầu tạo deployment mới, tuy nhiên để **reproducible release** nên dùng digest hoặc revision mô tả rõ artifact mới.

~~~bash
aws ecs wait services-stable \
  --cluster orders-lab \
  --services orders-api \
  --region ap-southeast-1 \
  --profile lab
~~~

Lệnh wait chỉ cho biết trạng thái theo waiter criteria; vẫn cần **test HTTP thực, metrics, log và tác động downstream**. Waiter có thể timeout khi task lỗi hoặc service không đạt steady state; xem service events thay vì tăng sleep/retry tùy tiện.

### 17.6. Xem nguyên nhân khi task bị dừng

Task đã dừng có thể cần lấy ARN từ **ECS Console / task list theo desired status** hoặc kết quả deployment trước; đừng chỉ dùng danh sách task đang RUNNING.

~~~bash
aws ecs list-tasks \
  --cluster orders-lab \
  --desired-status STOPPED \
  --region ap-southeast-1 \
  --profile lab

aws ecs describe-tasks \
  --cluster orders-lab \
  --tasks <task-arn-thuc-te> \
  --region ap-southeast-1 \
  --profile lab
~~~

**Trong ví dụ trên**, `<task-arn-thuc-te>` là chỗ giữ chỗ, không phải token Bash hợp lệ để chạy nguyên văn (dấu `<` có ý nghĩa đặc biệt trong shell). Thay bằng ARN thực trước khi thực hiện. Trạng thái task STOPPED chỉ hiển thị trong khoảng thời gian lưu giữ mà ECS hỗ trợ; log/metric dài hạn cần được cấu hình riêng.

### 17.7. Xử lý lifecycle và dọn tài nguyên lab

Sau khi thu thập kết quả, đưa `desiredCount` về 0 và xóa service theo quy trình lab; dọn target group/ALB, log group, secret, ECR images, IAM roles và cluster **chỉ nếu tài nguyên do lab tạo** và không còn phụ thuộc. **Xóa cluster không tự xóa mọi tài nguyên bên ngoài** như ALB, ECR, CloudWatch Logs hoặc VPC.

## 18. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân hay gặp | Kiểm tra đúng lớp |
| --- | --- | --- |
| `CannotPullContainerError` | Sai image URI/tag/digest, thiếu ECR pull quyền, ECR endpoint/network lỗi | Image tồn tại, execution role, ECR auth, SG, NAT/VPC endpoints |
| `ResourceInitializationError` | Không lấy secret/SSM config, không tạo log stream, lỗi kết nối dịch vụ khởi tạo | Execution role, `secretsmanager:GetSecretValue`, KMS, Logs, DNS/egress |
| Task `STOPPED` ngay | Essential container crash, thiếu biến môi trường, image architecture sai, startup command lỗi | DescribeTasks, `stoppedReason`, exit code, CloudWatch Logs |
| Task `RUNNING` nhưng ALB unhealthy | App chưa listen, port/path/matcher sai, SG ALB→task lỗi | Target health reason, task ENI IP, local endpoint, health config |
| Task không được đặt/cấp phát | Fargate capacity/quota, subnet thiếu IP; EC2 host thiếu CPU/RAM/ENI/port | ECS service events, subnet free IP, service limits, capacity providers |
| Desired = 4 nhưng Running = 2 kéo dài | Task startup/placement failures, launch/config/network lỗi | ECS events, stopped tasks, quota, executionRole, egress |
| Service deployment bị rollback | Revision mới không healthy hoặc circuit breaker triggered | Deployment history, events, container logs, compare task definitions |
| Không kết nối DB | Sai DB hostname/port/SG, DNS/VPC route, IAM auth hoặc credentials | SG task→DB, resolver, Secrets Manager, DB logs; tách network vs auth |
| Đọc S3 bị `AccessDenied` | Task role thiếu S3/KMS hoặc bucket/key policy Deny | Caller task role, IAM policy, bucket policy, KMS key |
| Logs trống | App chưa chạy, awslogs config sai, execution role thiếu Logs, networking lỗi | Log group/stream, task initialization logs và `stoppedReason` |
| Task bị OOM | Memory quá thấp, JVM heap không phù hợp container limit | Exit code/OOM, CloudWatch/Container Insights, JVM container flags |
| Scale ra không cải thiện p95 | RDS, cache, network hoặc dependency là nút nghẽn | APM/traces, DB connections, queue, downstream latency |
| Chỉ AZ B lỗi | SG/NACL/route/endpoint AZ B khác AZ A; capacity thiếu | Kiểm tra task subnet/ENI/AZ, egress/ALB health theo AZ |
| Secret đã rotate nhưng app vẫn dùng giá trị cũ | Secret được inject khi task bắt đầu, task hiện tại chưa được thay | Deploy task revision/restart có kiểm soát, hoặc runtime refresh mechanism |
| IP task thay đổi làm client lỗi | Hardcode task IP, không có discovery/load balancer | Dùng ALB/Service Connect/Cloud Map, TTL và retry hợp lý |

### Quy trình chẩn đoán có thứ tự

~~~text
1. Xác nhận account, Region, cluster, service, task definition revision.
2. Xem DescribeServices: desired/running/pending, deployments, events.
3. Xem DescribeTasks cả task RUNNING và STOPPED: stopCode/stoppedReason,
   container reason/exitCode, ENI, health status.
4. Nếu lỗi trước lúc container khởi động: kiểm tra ECR image,
   execution role, network egress, Secrets Manager, CloudWatch Logs.
5. Nếu container chạy nhưng API lỗi: ALB target type ip, port/path,
   task security group, app log, DB/DNS và readiness.
6. Nếu scale/deploy lỗi: kiểm tra capacity/quotas, policy, min/max,
   deployment configuration, AZ, circuit breaker và rollback.
7. Sửa một nguyên nhân cụ thể; deploy lại lab, kiểm thử HTTP/SQS,
   quan sát latency/errors và kết quả sau thay đổi.
~~~

**Không xử lý lỗi bằng cách cấp `AdministratorAccess`, mở SG `0.0.0.0/0` cho port backend hoặc gắn public IP cho mọi task mà không đánh giá.** Những thay đổi đó có thể che lỗi IAM/egress và tạo rủi ro lớn hơn.

## 19. Quan sát và kiểm soát chi phí

### Fargate tính chi phí theo những thành phần nào?

Phụ thuộc cấu hình và giá hiện hành, chi phí Fargate thường liên quan tới **vCPU**, **memory**, **thời gian task chạy theo chính sách billing**, và **ephemeral storage cấp thêm** khi vượt phần mặc định. Một số nền tảng/kiến trúc và Spot capacity có mức giá khác nhau.

Ngoài Fargate, phải tính:

- **ALB** và các chỉ số sử dụng năng lực/load balancer;
- **CloudWatch Logs/metrics/Container Insights**;
- **NAT Gateway**, VPC endpoints, public IPv4 và truyền dữ liệu giữa AZ/ra Internet;
- **ECR storage/scanning/image transfer** theo mức sử dụng;
- **Secrets Manager/KMS**, S3/EFS/EBS, RDS, SQS;
- tài nguyên dự phòng Multi-AZ và môi trường staging/prod.

### Ví dụ tính vCPU-hours và GB-hours

Service chạy **4 Fargate tasks** liên tục trong **30 ngày**, mỗi task **0,5 vCPU, 1 GiB RAM**:

\[
H = 4 \times 24 \times 30 = 2880\ \text{task-hours}
\]

\[
\text{vCPU-hours} = 2880 \times 0.5 = 1440
\]

\[
\text{GB-hours} = 2880 \times 1 = 2880
\]

Để quy đổi tiền, nhân các giá vCPU-hour/GB-hour **tại đúng Region, OS/architecture, mô hình On-Demand hay Spot**, rồi cộng chi phí liên quan. Đây chỉ là ước lượng capacity, không phản ánh mọi chi tiết làm tròn/chu kỳ tính phí của nhà cung cấp.

### Khi nào EC2 có thể tối ưu hơn?

Nếu nhiều task dùng CPU/RAM tương đối ổn định và một fleet EC2 được khai thác tốt, mô hình ECS on EC2 có thể giảm một số chi phí compute so với Fargate, nhưng bạn nhận thêm trách nhiệm patching/AMI/host security, capacity management, scaling, spot interruption và vận hành instance. **So sánh tổng chi phí sở hữu**, không chỉ giá một task hoặc một instance.

### Cost guardrails

- Đặt **AWS Budgets**, cost allocation tags (`application`, `environment`, `team`) và cảnh báo bất thường.
- Đặt `min/max tasks` có lý do; `desiredCount` cao suốt tháng có thể đắt.
- Chọn CPU/RAM theo benchmark; Fargate CPU/memory overprovision cũng có chi phí.
- Lưu image/log theo retention phù hợp, xóa tài nguyên lab đã ngừng dùng.
- Đo NAT/endpoint/data transfer; nhiều task đặt across AZ có thể làm tăng lưu lượng.
- Không dùng Fargate Spot cho phần workload không chấp nhận gián đoạn chỉ vì giá thấp.

## 20. Ba tình huống thiết kế

### Tình huống A — API thương mại điện tử cần luôn sẵn sàng

**Yêu cầu:** API Java/Spring Boot qua HTTPS, có dữ liệu đơn hàng và ảnh sản phẩm, traffic tăng theo chiến dịch.

**Gợi ý:**

- ECR image bất biến;
- ECS cluster + **Fargate service** với `desiredCount` tối thiểu phù hợp, tasks qua hai AZ;
- ALB public + target group `ip` + health `/health/ready`;
- RDS Multi-AZ, S3 lưu ảnh/hóa đơn, SQS cho xử lý nền;
- task role chỉ có quyền S3/SQS cần thiết; execution role kéo ECR/ghi logs/đọc secret;
- Service Auto Scaling theo CPU hoặc `ALBRequestCountPerTarget` sau benchmark;
- CloudWatch alarms/Container Insights và deployment circuit breaker;
- kiểm thử khi một task/AZ gặp sự cố, DB failover và tải cao điểm.

**Bài học:** ECS làm nhiệm vụ compute scheduling; **data HA, auth, network và cost** vẫn cần thiết kế độc lập.

### Tình huống B — Worker nhận sự kiện SQS

**Yêu cầu:** Sinh hóa đơn PDF từ đơn hàng, xử lý lâu, có thể retry và chạy thêm worker khi backlog tăng.

**Gợi ý:**

- ECS service chạy task worker, **không cần ALB**;
- task definition có môi trường cấu hình và quyền SQS/S3 vừa đủ;
- scale số task theo **queue backlog per task** hoặc metric thực tế;
- **visibility timeout, DLQ và idempotency** để xử lý task bị gián đoạn;
- cân nhắc `FARGATE_SPOT` cho phần worker chịu được interruption, giữ nền capacity thường nếu cần;
- lưu file ra S3, không chỉ trong ephemeral storage.

### Tình huống C — Batch job định kỳ

**Yêu cầu:** Một job tổng hợp dữ liệu chạy mỗi đêm, hoàn thành rồi dừng, không phục vụ HTTP.

**Gợi ý:**

- Dùng task definition riêng cho job;
- **EventBridge Scheduler/Step Functions + RunTask** theo cơ chế phù hợp;
- không duy trì một ECS service 24/7 chỉ để chạy job một lần/ngày;
- xử lý exit code, retries, timeout, idempotency và audit log;
- chọn Fargate/EC2 theo thời gian chạy, cấu hình tài nguyên và chi phí.

## 21. Checklist trước khi triển khai

- [ ] Đã hiểu **cluster ≠ task definition ≠ task ≠ service** và chọn `RunTask` hay service đúng nhu cầu.
- [ ] Chọn Fargate/EC2 dựa trên resource, giới hạn platform, quản trị host và tổng chi phí.
- [ ] Image ECR tồn tại, tag/digest quản trị tốt và kiến trúc CPU phù hợp.
- [ ] Task definition có cặp CPU/memory hợp lệ, container name/port, log/health config, environment và secret reference đúng.
- [ ] Task execution role kéo ECR, gửi CloudWatch Logs, đọc secret theo nhu cầu; task role chỉ quyền API của ứng dụng.
- [ ] Với `awsvpc`, chọn subnets, security groups, IP/network egress và DNS phù hợp.
- [ ] Nếu dùng ALB/NLB với `awsvpc`, target group có **target type = ip**, port và health check đúng.
- [ ] Chọn nhiều AZ và xác minh placement thực; đủ task/capacity dự phòng theo yêu cầu SLO.
- [ ] `desiredCount`, deployment min/max, grace period, circuit breaker/rollback và graceful shutdown được kiểm chứng.
- [ ] Service Auto Scaling chọn metrics thực tế, giới hạn min/max, hiểu tác động lên DB/SQS và chi phí.
- [ ] Không lưu dữ liệu cần bền vững chỉ trong ephemeral storage; chọn S3/EFS/EBS/DB đúng bài toán.
- [ ] Có CloudWatch logs/alarms, ECS events, health metrics, tracing, log retention và audit.
- [ ] Secrets/KMS/IAM, TLS/VPC endpoints, public/private network và image security đều được đánh giá.
- [ ] Đã thử task bị STOPPED, image lỗi, health check lỗi, scale out/in và recovery trên môi trường lab.
- [ ] Có IaC, change review, rollback, cleanup và ngân sách theo Region/workload.

## 22. Bài tập tự kiểm tra

### Bài tập 1 — Nhận diện bốn khái niệm

Nhóm vận hành có:

~~~text
Cluster: sales-lab
Task definition: product-api:5
Service: product-api-service, desiredCount=3
Tasks: 3 task ARN, mỗi task chạy 1 product-api container
~~~

Hãy giải thích trường nào là **bản thiết kế**, trường nào là **cơ chế duy trì**, trường nào là **đơn vị thực thi**, và vì sao sửa image URI trong revision 5 rồi không tạo revision mới là cách quản lý release không tốt.

### Bài tập 2 — So sánh execution role và task role

Container Java:

1. ECS kéo image từ ECR.
2. ECS tải secret từ Secrets Manager và inject thành environment.
3. Java SDK ghi message vào SQS.
4. Java SDK đọc object SSE-KMS từ S3.

Hãy phân loại action/IAM roles cho từng bước, bao gồm KMS permissions, key policy và tài nguyên S3/SQS cụ thể. Giải thích vì sao chỉ cấp quyền ECR pull vào task role sẽ không sửa được lỗi kéo image.

### Bài tập 3 — Tìm lỗi target group

Service Fargate có tasks `RUNNING` trong private subnets, ALB trả HTTP 503. Target group đã tạo với **target type `instance`**, backend port 8080.

Nêu ít nhất bốn kiểm tra cần làm: target type, cấu hình ECS service load balancer, task SG, target health, endpoint/path ứng dụng và outbound network cho task startup. Đề xuất cách thay target group đúng và kiểm chứng.

### Bài tập 4 — Deployment rollback

Service chạy `orders-api:3` ổn định. Nhóm tạo revision 4 nhưng image quên lệnh `curl`; task definition health check vẫn gọi `curl`.

Hãy mô tả trạng thái có thể quan sát, ECS service events/logs, cách circuit breaker rollback hoạt động nếu bật, và cách sửa image/health command rồi deploy revision 5. Nêu vì sao `RUNNING` không đồng nghĩa healthy.

### Bài tập 5 — Đảm bảo phục vụ khi mất một AZ

Load test cho thấy 1 task phục vụ bền vững 60 RPS; hệ thống phải duy trì 180 RPS ngay khi một AZ mất khả năng phục vụ.

1. Tính số task khỏe tối thiểu phải **còn lại** ở AZ sống sót (`ceil(180/60)=3`).
2. Nếu hai AZ cân bằng và cần phục vụ ngay không chờ scale, tối thiểu có bao nhiêu task toàn hệ thống?
3. Nếu muốn 25% headroom, cần bao nhiêu task/AZ? (`ceil(180×1.25/60)=4`).
4. Tại sao scheduler placement, subnet IP, Fargate capacity và sức chịu tải RDS vẫn phải được kiểm thử?

### Câu hỏi ngắn

**1. Tạo ECS cluster có tự tạo container không?** Không. Cần task definition + RunTask hoặc service và capacity phù hợp.

**2. Task definition có sửa trực tiếp image của revision đã đăng ký không?** Không theo mô hình quản lý revision thông thường; đăng ký revision mới.

**3. Một standalone task dừng có tự được ECS thay để luôn có một task chạy không?** Không; service mới duy trì desired count, hoặc hệ thống điều phối riêng phải quyết định retry.

**4. Fargate task có cần EC2 instance do mình quản trị không?** Không, AWS vận hành host; bạn vẫn cấu hình CPU/RAM, mạng, IAM, storage và chi phí.

**5. API dùng Fargate awsvpc với ALB chọn target group type nào?** `ip`.

**6. App muốn gửi SQS message thì cấp quyền role nào?** Task role; execution role phục vụ công việc ECS agent.

**7. `desiredCount=3` có chắc ba tasks đều healthy không?** Không. Cần xem running/health/placement và logs.

**8. Mất một task thì ECS service có khôi phục dữ liệu trên ephemeral storage cũ không?** Không. Dữ liệu bền vững cần lưu ngoài task.

## 23. Tổng kết

Trong ECS, **cluster là nơi tổ chức workloads**, **task definition là bản thiết kế có revision**, **task là một lần chạy cụ thể**, còn **service duy trì số task mong muốn và điều phối deployment**. Khi hiểu rõ sự khác biệt này, bạn có thể đưa container image thành ứng dụng được vận hành có kiểm soát.

Với web/API, mô hình thường bắt đầu bằng **Fargate service trên nhiều AZ**, **task definition khai báo CPU/RAM, IAM và log**, **ALB target group loại `ip`**, health checks, rolling deployment và autoscaling dựa trên metric. Với job ngắn hạn, cân nhắc **RunTask**. Với workload đặc thù, ECS trên EC2 là lựa chọn nhưng cần quản lý thêm host capacity.

**Tính sẵn sàng của hệ thống không chỉ là ECS có tạo lại task hay không.** Hãy kết hợp **IAM least privilege, VPC routing, AWS Region/AZ, dữ liệu trên RDS/S3/EFS, CloudWatch, backup/restore, load test và AWS Budgets**. Thiết kế tốt phải đồng thời an toàn, vận hành được, có khả năng khôi phục và đủ hiệu quả chi phí.

### Tài liệu AWS chính thức để đối chiếu khi triển khai

- [Amazon ECS concepts and overview](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/Welcome.html)
- [Amazon ECS clusters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/clusters.html)
- [Task definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [Creating an ECS task definition](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/create-task-definition.html)
- [Amazon ECS services](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_services.html)
- [Amazon ECS service definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_definition_parameters.html)
- [Service deployments and rolling updates](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html)
- [Amazon ECS service auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html)
- [Task networking with awsvpc](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html)
- [Best practices for IAM roles in ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html)
- [Amazon ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)
- [Amazon ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)
- [Fargate task ephemeral storage](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-storage.html)
- [AWS CLI ECS command reference](https://docs.aws.amazon.com/cli/latest/reference/ecs/)
- [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/) và [Amazon ECS pricing](https://aws.amazon.com/ecs/pricing/)

**Khi lên production:** Đối chiếu tính năng và giới hạn ở **Region/account, OS/platform, instance/capacity provider và thời điểm thực tế**; kiểm thử triển khai, failover, security và chi phí trên môi trường có kiểm soát trước khi mở cho người dùng.
