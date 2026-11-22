# Thu thập log, ECS Exec và xử lý task bị dừng

Khi một ứng dụng chạy trên **Amazon Elastic Container Service (ECS)** không phục vụ được yêu cầu, dấu hiệu quan sát được có thể chỉ là “task đang chạy rồi biến mất”, “service liên tục thay task”, hoặc “CloudWatch không có log”. Để tìm nguyên nhân, không nên vội tăng CPU/RAM hay mở rộng IAM policy. Cần phân biệt **log ứng dụng**, **sự kiện vòng đời ECS**, **lệnh chẩn đoán tương tác bằng ECS Exec** và **thông tin task đã STOPPED**.

Ví dụ: một dịch vụ Java trên **AWS Fargate** khởi tạo task nhưng bị dừng sau 10 giây. Có thể image không tải được từ Amazon ECR, execution role thiếu quyền lấy secret, cấu hình mạng không tới CloudWatch Logs, Java process hết RAM hoặc ứng dụng chủ động thoát vì sai biến môi trường. Mỗi nguyên nhân để lại dấu vết ở một lớp khác nhau.

Bài học thuộc chương **Container với ECS**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung liên hệ hệ sinh thái AWS gồm Region/AZ, IAM, VPC, compute, storage, database, tích hợp và serverless để rèn khả năng triển khai ứng dụng an toàn, giám sát hiệu quả, phục hồi sau sự cố và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **CloudWatch Logs**, **FireLens**, **ECS service events**, **task state change events**, **CloudTrail** và **Container Insights**.
2. Cấu hình **awslogs** trong ECS task definition, hiểu vai trò của **task execution role**, log group, log stream prefix và retention.
3. Lựa chọn ghi log có cấu trúc, theo dõi task ARN, correlation ID và xử lý thông tin nhạy cảm.
4. Chuẩn bị và sử dụng **ECS Exec** với Session Manager, IAM task role, network endpoints và quy tắc kiểm toán.
5. Đọc **stopCode**, **stoppedReason**, **containers[].reason**, **exitCode** và sự kiện ECS service để xác định vì sao task dừng.
6. Chẩn đoán các lỗi thường gặp: **CannotPullContainer**, **ResourceInitializationError**, **EssentialContainerExited**, OOM, health check thất bại và quyền AWS bị từ chối.
7. Xây dựng runbook bảo mật, lưu giữ bằng chứng sau khi task biến mất và kiểm thử trước khi triển khai production.

## 2. Mô hình chẩn đoán: mỗi lớp để lại dấu vết khác nhau

~~~mermaid
flowchart TD
    CLIENT["Client / ALB"] --> SERVICE["ECS Service<br/>Desired count + deployments"]
    SERVICE --> TASK["ECS Task<br/>Task definition revision"]
    TASK --> APP["Application containers"]
    APP --> LOG["stdout/stderr → awslogs<br/>CloudWatch Logs"]
    TASK --> EVENT["STOPPED state change<br/>EventBridge"]
    SERVICE --> EV["Service events<br/>Deployment / placement / health"]
    TASK --> EXEC["ECS Exec + SSM<br/>Task RUNNING"]
    APP --> METRIC["Container Insights<br/>CPU / Memory / network"]
    CONTROL["AWS API / IAM identity"] --> TRAIL["CloudTrail<br/>Ai gọi ECS API?"]
~~~

| Nguồn thông tin | Câu hỏi nó trả lời tốt nhất | Giới hạn |
|---|---|---|
| **Ứng dụng stdout/stderr** | Code lỗi gì, stack trace nào, request nào thất bại? | Có thể trống nếu container không khởi động hoặc logger chưa được cấu hình |
| **CloudWatch Logs** | Log các container được thu thập ra sao theo thời gian? | Cần log driver, quyền và đường mạng; không tự có mọi log của host |
| **ECS task details** | Task đang ở trạng thái nào, vì sao STOPPED, container exit code nào? | Task STOPPED chỉ hiện diện trong danh sách điều tra ECS trong một thời gian ngắn |
| **ECS service events** | Deployment, health replacement, placement hoặc scale bị lỗi gì? | Không thay thế log ứng dụng hoặc toàn bộ lịch sử trạng thái task |
| **EventBridge task state change** | Task chuyển sang RUNNING/STOPPED khi nào và thông tin sự kiện là gì? | Phải cấu hình lưu trữ/chuyển tiếp nếu muốn tra cứu lịch sử lâu dài |
| **ECS Exec** | Bên trong container đang RUNNING có file/process/env/network gì? | Không truy cập task đã STOPPED; cần bật từ trước và có quyền |
| **CloudTrail** | Principal nào gọi ECS API, chẳng hạn ExecuteCommand, UpdateService? | Không ghi mọi lệnh shell hoặc nội dung stdout trừ khi bật log phiên thích hợp |
| **CloudWatch metrics/Container Insights** | CPU, memory, số task, lỗi/độ trễ diễn biến thế nào? | Metric chưa đủ kết luận nguyên nhân ứng dụng crash |

Quy trình điều tra tốt sử dụng **nhiều nguồn bằng chứng** và có mốc thời gian thống nhất, tránh suy luận chỉ từ một dòng lỗi.

## 3. Log ứng dụng trong ECS: stdout/stderr là điểm xuất phát

### 3.1. Vì sao nên ghi log ra stdout/stderr?

Container có thể bị thay thế bất cứ lúc nào do deployment, lỗi hoặc scale-in. Nếu chỉ ghi log vào tệp trong filesystem của container, tệp đó có thể không còn khi task dừng. Thay vào đó, ứng dụng nên ghi log **stdout/stderr**; log driver của ECS chuyển log đến hệ thống tập trung.

Với Java/Spring Boot, có thể dùng SLF4J/Logback hoặc hệ thống tương đương để in log có cấu trúc theo mức **INFO/WARN/ERROR**, cùng **service, environment, requestId/traceId, taskId** khi có. Không cần truy cập container qua shell để đọc log bình thường.

**Lưu ý:** nếu tác vụ dùng sidecar hoặc process thứ cấp ghi log ra file, cần cấu hình thu thập tương ứng; **awslogs** chỉ chuyển output của những stream mà driver được gắn. Không tự gom mọi file trong container hoặc mọi log của ECS agent trên EC2.

### 3.2. Cấu hình awslogs trong task definition

Ví dụ một ECS task chạy trên Fargate, với container tên **orders-api** và log group **/ecs/orders/prod** đã được tạo trước. JSON dưới đây minh họa các trường chính, không phải tài nguyên production sẵn dùng:

~~~json
{
  "family": "orders-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::111122223333:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::111122223333:role/ordersTaskRole",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:v12",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/orders/prod",
          "awslogs-region": "ap-southeast-1",
          "awslogs-stream-prefix": "orders"
        }
      }
    }
  ]
}
~~~

Giá trị image/role/account chỉ là ví dụ; để đăng ký và chạy thành công cần image có thật, role hợp lệ, subnet/security group, service hoặc RunTask và những phụ thuộc ứng dụng cần thiết.

| Option | Công dụng | Điều cần kiểm tra |
|---|---|---|
| **logDriver = awslogs** | Gửi output container vào CloudWatch Logs | Driver được hỗ trợ trên loại compute/agent |
| **awslogs-group** | Tên CloudWatch log group | Group tồn tại đúng Region hoặc có quyền tạo |
| **awslogs-region** | Region lưu log | Có thể khác Region task, nhưng cần thiết kế và kiểm soát chi phí/dữ liệu |
| **awslogs-stream-prefix** | Tiền tố tạo tên log stream | **Bắt buộc với Fargate**; khuyến nghị với EC2 |
| **awslogs-create-group** | Có tự tạo group nếu chưa có hay không | Mặc định false; khi bật phải cấp **logs:CreateLogGroup** |
| **awslogs-multiline-pattern / awslogs-datetime-format** | Gom nhiều dòng log theo pattern | Tăng xử lý CPU; chỉ dùng khi format ổn định; không dùng cả hai đồng thời |

Với prefix **orders**, container **orders-api**, task ID giả định **abcdef1234567890**, tên stream điển hình:

~~~text
orders/orders-api/abcdef1234567890
~~~

Tạo **log group trước** trong pipeline IaC, gắn retention, mã hóa/KMS nếu phù hợp, phân quyền và tag chi phí. Tránh để log group mặc định lưu quá lâu khi không có nhu cầu pháp lý/vận hành.

### 3.3. Execution role và task role không giống nhau

Đây là nguồn lỗi IAM phổ biến:

| Role | Ai sử dụng? | Ví dụ quyền |
|---|---|---|
| **Task execution role** | ECS/Fargate agent để chuẩn bị runtime | Lấy image từ ECR, gửi log bằng awslogs, lấy secrets/environment files theo cơ chế task definition |
| **Task role** | Code ứng dụng trong container | Đọc S3, ghi DynamoDB, gọi SQS; cấp **ssmmessages** để ECS Exec khi cần |
| **EC2 container instance role** | ECS agent trên EC2 host trong mô hình EC2 launch type | Đăng ký host với ECS và thao tác host cần thiết |
| **Người vận hành IAM principal** | Kỹ sư/CI gọi ECS API | DescribeTasks, ExecuteCommand, UpdateService theo scope |

Đối với **awslogs thông thường trên Fargate**, quyền **logs:CreateLogStream** và **logs:PutLogEvents** cần nằm ở **execution role**; nếu bật tính năng tự tạo log group, phải xét thêm **logs:CreateLogGroup**. Managed policy như **AmazonECSTaskExecutionRolePolicy** có thể cung cấp những quyền nền tảng trong các trường hợp phù hợp, nhưng phải kiểm tra chính sách và tài nguyên cụ thể.

**Không gắn AdministratorAccess vào task role để sửa lỗi đẩy log.** Có thể chỉ đang thiếu quyền ở execution role, log group sai Region hoặc task không tới được CloudWatch Logs qua network.

### 3.4. Đọc log bằng AWS CLI và CloudWatch Logs Insights

~~~bash
# Xem sự kiện gần đây; cần quyền CloudWatch Logs phù hợp.
aws logs tail /ecs/orders/prod \
  --region ap-southeast-1 \
  --since 30m

# Theo dõi log mới trong lúc thử nghiệm có kiểm soát.
aws logs tail /ecs/orders/prod \
  --region ap-southeast-1 \
  --since 5m \
  --follow
~~~

Nếu log group chứa nhiều tasks, lọc theo **log stream** hoặc **task ID** để tránh trộn sự kiện. Trong CloudWatch Logs Insights, có thể thử:

~~~text
fields @timestamp, @logStream, @message
| filter @message like /ERROR|Exception|OutOfMemory/
| sort @timestamp desc
| limit 100
~~~

Với ứng dụng ghi log JSON, bạn có thể truy vấn theo trường đã parse như **level**, **requestId** hoặc **traceId** khi định dạng và thiết lập Logs Insights hỗ trợ. Đặt thời gian truy vấn hẹp theo lúc task dừng để giảm nhiễu và chi phí query.

## 4. FireLens, logging nâng cao và dữ liệu có cấu trúc

**Amazon ECS FireLens** tích hợp log routing, thường sử dụng **Fluent Bit** làm log router sidecar để đẩy log tới nhiều điểm nhận tùy loại plugin được hỗ trợ. Cách này phù hợp khi doanh nghiệp muốn tập trung logs vào hệ thống phân tích, Amazon Data Firehose, OpenSearch hoặc giải pháp quan sát khác.

~~~mermaid
flowchart LR
    APP["Application container<br/>stdout/stderr"] --> FIRE["FireLens log router<br/>Fluent Bit sidecar"]
    FIRE --> CW["CloudWatch Logs"]
    FIRE --> OUT["Destination khác<br/>theo output plugin"]
    ECS["ECS task metadata"] -. "Thêm metadata khi cấu hình" .-> FIRE
~~~

Trong task definition, application container thường khai báo **logDriver = awsfirelens**, còn log router container dùng **firelensConfiguration**. Một cấu hình đúng phải xem kỹ output plugin, thông tin xác thực, routing, bộ nhớ buffer, retry và đường mạng đến đích.

### 4.1. Chọn awslogs hay FireLens?

| Khía cạnh | awslogs | FireLens |
|---|---|---|
| Độ đơn giản | Ít thành phần, dễ cấu hình | Cần thêm router container/config |
| Điểm nhận | CloudWatch Logs | Nhiều đích theo plugin được hỗ trợ |
| Chuẩn hóa dữ liệu | Ứng dụng nên tự ghi JSON | Có thể parse/transform/filter tại router |
| Điểm lỗi mới | Driver/CloudWatch Logs | Router, plugin, buffer, CPU/memory và đích nhận |
| Chi phí | Logs ingestion/storage/query | Thêm tài nguyên router, lưu lượng và đích nhận |

**Đừng khiến log router trở thành điểm lỗi khó quan sát.** Thiết lập resource cho sidecar, giám sát log router, cơ chế buffer/retry và log riêng cho chính router. Khi FireLens không hoạt động, có thể mất log dù application container vẫn chạy hoặc task có thể bị ảnh hưởng tùy cấu hình essential/dependencies.

### 4.2. Thiết kế log ứng dụng dễ truy vết

Một log record có cấu trúc có thể trông như:

~~~json
{
  "timestamp": "2026-11-20T03:00:00Z",
  "level": "ERROR",
  "service": "orders-api",
  "environment": "prod",
  "requestId": "req-example-008",
  "traceId": "trace-example-456",
  "message": "Database connection timeout",
  "errorType": "DB_TIMEOUT"
}
~~~

Nên ghi **timestamp UTC**, service/version, correlation ID, task/container metadata và thông điệp có thể hành động. Cố gắng không ghi **mật khẩu, access key, cookie phiên, bearer token, nội dung cá nhân không cần thiết**. Với Java stack trace nhiều dòng, cân nhắc JSON một dòng hoặc multiline settings phù hợp để truy vấn ổn định.

### 4.3. CloudTrail và metrics không phải application logs

- **CloudTrail** hữu ích để tìm ai đã thay service/task definition hoặc ai mở ECS Exec. Nó không thay thế log nghiệp vụ của container.
- **CloudWatch Container Insights** giúp đo CPU/memory/network/task counts theo cấu hình quan sát. Metric tăng/giảm bất thường là dấu hiệu, không đủ để kết luận nguyên nhân.
- **ECS task/service state change events** giúp xây chuỗi thời gian về deployment, health và task termination.

## 5. ECS Exec: truy cập chẩn đoán một container đang chạy

**ECS Exec** sử dụng **AWS Systems Manager Session Manager** để tương tác với container trong ECS task **đang RUNNING**, không cần mở SSH inbound hoặc quản lý SSH key của EC2 host. Có thể chạy shell/lệnh tương tác theo loại container được hỗ trợ và giới hạn của môi trường.

ECS Exec phù hợp để kiểm tra DNS, file cấu hình không nhạy cảm, process, biến môi trường đã loại bỏ bí mật, cổng lắng nghe hoặc truy cập network trong một task đang chạy. **Không dùng ECS Exec làm phương thức triển khai ứng dụng thường xuyên**: sửa thủ công trong container tạo ra trạng thái không thể tái lập và sẽ mất khi task thay thế.

### 5.1. Kiến trúc ECS Exec

~~~mermaid
sequenceDiagram
    participant OP as Người vận hành + AWS CLI
    participant ECS as Amazon ECS API
    participant SSM as SSM Session Manager
    participant TASK as Container trong ECS task
    OP->>ECS: ExecuteCommand (IAM kiểm tra)
    ECS-->>OP: Thông tin thiết lập phiên
    OP->>SSM: Kết nối qua Session Manager plugin
    TASK->>SSM: SSM core agent dùng task role
    SSM-->>OP: Kênh tương tác mã hóa
    OP->>TASK: Lệnh kiểm tra được phép
    TASK-->>OP: Output
~~~

ECS/Fargate agent quản lý **ExecuteCommandAgent** trong container để thực hiện phiên. Có thể quan sát trạng thái agent trong **DescribeTasks → containers[].managedAgents**.

### 5.2. Điều kiện trước khi dùng ECS Exec

| Điều kiện | Ý nghĩa |
|---|---|
| **Task đang RUNNING** | Không Exec được vào task đã STOPPED hoặc chưa khởi động |
| **enableExecuteCommand = true** | Phải bật cho task khi được tạo; bật trên service không sửa task cũ đã tồn tại |
| **AWS CLI + Session Manager plugin** | CLI tương tác cần plugin và phiên bản tương thích |
| **Agent/platform tương thích** | ECS agent/platform version/OS phải hỗ trợ ECS Exec |
| **Task IAM role** | Có bốn quyền **ssmmessages** để tạo/mở data/control channels |
| **Operator IAM permission** | Người dùng có quyền **ecs:ExecuteCommand** trên tài nguyên phù hợp |
| **Network** | Task đến được **ssmmessages** qua NAT/Internet hoặc VPC interface endpoint |
| **Filesystem và tài nguyên** | ECS Exec cần ghi vào filesystem và có thêm CPU/memory overhead |
| **Audit** | CloudTrail và cấu hình log phiên CloudWatch/S3 phù hợp |

Các giới hạn quan trọng trong tài liệu AWS:

- ECS Exec **không được hỗ trợ trên task có filesystem root hoàn toàn read-only** bằng **readonlyRootFilesystem**.
- Lệnh trong ECS Exec chạy dưới quyền **root** trong container, kể cả khi ứng dụng được cấu hình chạy bằng user không phải root. Đây là quyền rất nhạy cảm.
- ECS Exec không hỗ trợ tác vụ ở cấu hình **IPv6-only** theo giới hạn hiện hành được nêu trong tài liệu.
- Một PID namespace dùng chung có thể giới hạn số phiên exec đồng thời; các tính năng sidecar có thể cần chỉ rõ container đích.
- Không thể bật ECS Exec cho **task đang chạy đã tạo trước đó**; cần tạo task mới có tính năng này.

Ở EC2 launch type, AWS có yêu cầu ECS agent/version tương ứng; với Fargate Linux, tài liệu chỉ ra **platform version 1.4.0 trở lên** (Windows có ngưỡng riêng). Kiểm tra tài liệu ở Region/môi trường hiện tại khi triển khai.

### 5.3. IAM cho task role

Ví dụ policy cho **task role** để SSM core agent tạo và mở các kênh giao tiếp:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowECSExecChannels",
      "Effect": "Allow",
      "Action": [
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Đây là policy cần thiết cho **kênh bên trong container** và chỉ nên gắn vào những task role có nhu cầu ECS Exec. **Không nhầm với quyền ecs:ExecuteCommand của người vận hành**. Nếu cấu hình thêm KMS customer managed key cho phiên exec hoặc lưu log phiên ở S3/CloudWatch Logs, sẽ cần quyền KMS/log/S3 bổ sung theo kiến trúc; kiểm tra chính sách KMS key và tài khoản của tài nguyên.

Phân quyền operator nên giới hạn **cluster, task, container, tags và điều kiện** được ECS hỗ trợ, chỉ mở khi thật sự cần. Có thể hạn chế đường truy cập Session Manager trực tiếp không qua ECS Exec theo tài liệu AWS, để tránh kênh ngoài quy trình kiểm toán.

### 5.4. Bật ECS Exec cho service

Ví dụ cập nhật một ECS service để **các task mới** được launch với ECS Exec:

~~~bash
aws ecs update-service \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --service orders-api \
  --enable-execute-command \
  --force-new-deployment
~~~

**Cảnh báo:** lệnh trên thay đổi cấu hình service và **force-new-deployment** có thể tạo/thay thế task đang phục vụ. Chỉ chạy trong môi trường được phép, có kế hoạch deployment/rollback và kiểm thử. Nếu chỉ bật cờ ở service mà không tạo task mới, task đang chạy có thể tiếp tục có **enableExecuteCommand = false**.

Với **RunTask** tạo standalone task, cần chỉ định **--enable-execute-command** ngay khi tạo task nếu muốn dùng ECS Exec sau đó.

### 5.5. Xác nhận agent và mở phiên

~~~bash
# Đọc thông tin của task đang RUNNING.
aws ecs describe-tasks \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --tasks arn:aws:ecs:ap-southeast-1:111122223333:task/training-cluster/TASK_ID \
  --query 'tasks[].{Task:taskArn,Status:lastStatus,Exec:enableExecuteCommand,Containers:containers[].{Name:name,Agents:managedAgents}}'

# Chỉ Exec sau khi Exec=true và agent có lastStatus=RUNNING.
aws ecs execute-command \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --task arn:aws:ecs:ap-southeast-1:111122223333:task/training-cluster/TASK_ID \
  --container orders-api \
  --interactive \
  --command "/bin/sh"
~~~

Giá trị **TASK_ID**, cluster và container là placeholder; container image phải thực sự có **/bin/sh** hoặc shell khác phù hợp. ECS Exec chỉ hỗ trợ **interactive sessions** qua cơ chế CLI này nên cờ **--interactive** được yêu cầu. Không mặc định image distroless có shell. Khi cần chẩn đoán image tối giản, ưu tiên log, metric hoặc thêm công cụ chẩn đoán theo quy trình xây dựng image.

Các lệnh kiểm tra an toàn bên trong container có thể gồm **pwd**, **ps**, kiểm tra tên file cấu hình được phép, DNS lookup nếu có công cụ, hoặc kết nối thử đến một service endpoint lab. Tránh lệnh sửa dữ liệu/kill process, in toàn bộ environment hoặc đọc secret không có lý do nghiệp vụ.

### 5.6. Nếu ECS Exec không kết nối được

Thứ tự kiểm tra:

1. **Task lastStatus = RUNNING**, **enableExecuteCommand = true**.
2. **ExecuteCommandAgent lastStatus = RUNNING** trong container đích.
3. Người vận hành có **ecs:ExecuteCommand**, không bị SCP/boundary/explicit deny chặn.
4. Task role có đúng **ssmmessages** actions, không chỉ execution role.
5. Task truy cập được **ssmmessages endpoint**; với private subnet không có NAT, cân nhắc interface VPC endpoint, DNS và security group cho HTTPS.
6. Nếu dùng KMS để mã hóa phiên bằng key do khách hàng quản lý, xác minh KMS key permissions và đường mạng đến KMS.
7. Image/container cho phép ECS Exec ghi file và còn đủ CPU/RAM; **readonlyRootFilesystem** không tương thích.
8. AWS CLI và **Session Manager plugin** đúng phiên bản; shell tồn tại.

Với HTTP proxy trong task, kiểm tra **NO_PROXY** phù hợp cho metadata/task role endpoints (ví dụ **169.254.169.254** và **169.254.170.2** khi dùng), nếu không việc lấy credentials có thể thất bại.

**Lưu ý:** ECS Exec không dùng để “cứu” một task đã STOPPED; với task đó hãy sử dụng log, reason, exit code và sự kiện được lưu.

## 6. Ghi log và kiểm toán phiên ECS Exec

Ghi log container ứng dụng và ghi log **ECS Exec session** là **hai việc khác nhau**. Log ứng dụng được điều khiển bởi log driver; logging của ECS Exec được điều khiển bởi **executeCommandConfiguration** ở cấp ECS cluster.

| Chế độ ECS Exec logging | Hành vi |
|---|---|
| **NONE** | Không gửi nội dung phiên exec vào đích ghi log theo cơ chế này |
| **DEFAULT** | Gửi log phiên đến CloudWatch Logs theo **awslogs** trong task definition; nếu không có awslogs phù hợp, không có log phiên ở đó |
| **OVERRIDE** | Chọn log group CloudWatch hoặc S3 bucket (hoặc cả hai) theo cluster execute command configuration |

AWS sử dụng **CloudTrail** để ghi sự kiện **ExecuteCommand** nhằm điều tra principal gọi lệnh; việc kiểm toán **toàn bộ output của shell** cần cấu hình logging phiên riêng. Để upload transcript của phiên exec vào S3/CloudWatch Logs theo cơ chế hỗ trợ, image cần công cụ **script** và **cat**; image quá tối giản có thể không ghi transcript dù phiên tương tác hoạt động.

**Biện pháp production:** hạn chế người có thể ECS Exec, thiết lập phê duyệt khi cần, lưu log theo retention, mã hóa bằng KMS nếu yêu cầu, kiểm tra quyền đọc log và không đưa secrets vào command. Phiên exec chạy root nên phạm vi IAM/cluster/container rất quan trọng.

## 7. Task bị dừng: hiểu đúng trạng thái, stopCode và exitCode

Một ECS task có các trạng thái vòng đời như **PROVISIONING**, **PENDING**, **ACTIVATING**, **RUNNING**, **DEACTIVATING**, **STOPPING**, **DEPROVISIONING**, **STOPPED** tùy giai đoạn và loại triển khai. **STOPPED** không nhất thiết là lỗi:

- Một standalone task chạy batch kết thúc thành công có thể STOPPED với exit code **0**.
- ECS service chủ động stop task để triển khai bản mới hoặc scale-in.
- Một essential container bị crash khiến task STOPPED.
- Task không khởi động được do image, network, IAM hoặc tài nguyên.

### 7.1. Những trường thông tin cần đọc

| Trường trong DescribeTasks | Cách đọc | Không nên nhầm với |
|---|---|---|
| **lastStatus / desiredStatus** | Trạng thái hiện tại và mục tiêu của task | Một mình STOPPED không chứng minh có sự cố |
| **stopCode** | Nhóm nguyên nhân mức API của việc dừng | Chuỗi lỗi chi tiết như ResourceInitializationError |
| **stoppedReason** | Thông điệp mô tả lý do dừng | Không ổn định để automation khớp nguyên văn |
| **stoppingAt / stoppedAt** | Mốc thời gian quá trình stop | Không thay thế log ứng dụng |
| **containers[].name** | Container nào trong task | Task có thể có nhiều essential/nonessential containers |
| **containers[].exitCode** | Mã thoát của process container, khi có | Không phải ECS stopCode |
| **containers[].reason** | Chi tiết lỗi từng container, nếu ECS ghi nhận | Có thể rỗng dù process lỗi |
| **containers[].lastStatus** | Trạng thái riêng của container | Task-level state khác với container-level state |
| **taskDefinitionArn** | Revision đã launch task | Không tự bằng revision mới nhất đang được đăng ký |

**Các giá trị stopCode** ở ECS Task API có thể gồm **TaskFailedToStart**, **EssentialContainerExited**, **UserInitiated**, **ServiceSchedulerInitiated**, **SpotInterruption**, **TerminationNotice**, **InfrastructureHealth** theo tập enum được AWS hỗ trợ. Trong khi đó các chuỗi như **CannotPullContainerError**, **ResourceInitializationError**, **OutOfMemoryError** thường xuất hiện như **nhóm thông báo lỗi** trong reason/diagnostics; không mặc nhiên là giá trị của trường **stopCode**.

### 7.2. Mã thoát của container nói lên điều gì?

| exitCode quan sát | Cách hiểu thường gặp | Kiểm tra bổ sung |
|---|---|---|
| **0** | Process hoàn thành bình thường | Có chủ ý chạy batch/oneshot hay service web đã thoát quá sớm? |
| **1** hoặc mã ứng dụng khác | Ứng dụng trả mã lỗi | Stack trace, cấu hình, dependency, logic start |
| **137** | Process bị **SIGKILL**; đôi khi vì OOM | Task/container memory, OOM diagnostic, host/container events; không kết luận chỉ từ 137 |
| **143** | Process nhận **SIGTERM**, có thể do scale-in/deploy/stop có kiểm soát | ECS service events, deployment, timestamp, termination flow |
| **Không có exitCode** | Có thể container chưa chạy đến giai đoạn sinh mã thoát | stoppedReason, pull image, secret, network và initialization |

**Quan trọng:** **143 không tự là lỗi**, **137 không luôn là OOM** và **exitCode 0 không bảo đảm tác vụ đạt kết quả nghiệp vụ**. Ghép exit code với stopCode, stoppedReason, thời gian và logs trước khi kết luận.

## 8. Quy trình điều tra task STOPPED

~~~mermaid
flowchart TD
    A["Phát hiện task STOPPED / service thiếu capacity"] --> B["Ghi task ARN, cluster, Region,<br/>thời gian, task definition revision"]
    B --> C["DescribeTasks:<br/>stopCode, stoppedReason,<br/>containers[].exitCode/reason"]
    C --> D{"Container đã chạy được?"}
    D -->|"Chưa"| E["Image pull / secrets / logging<br/>IAM execution role / network / storage"]
    D -->|"Đã chạy"| F["Application logs<br/>OOM / exit / health / signal"]
    E --> G["Service events + CloudTrail + metrics"]
    F --> G
    G --> H["Xác định nguyên nhân gốc<br/>và áp dụng bản sửa tối thiểu"]
    H --> I["Deploy thử và xác minh<br/>RUNNING, healthy, log, SLO"]
~~~

### Bước 1 — Thu thập bằng chứng trước khi biến mất

Lưu **cluster, service, task ARN, task definition revision, Region, task stop time** và mọi lý do dừng. Theo tài liệu AWS, task STOPPED chỉ hiển thị trong ECS Console khoảng **một giờ**; thời gian tra cứu qua API cũng có giới hạn. Để có lịch sử dài, lưu **ECS Task State Change events** bằng EventBridge và lưu log/metrics tập trung.

### Bước 2 — Liệt kê và mô tả task

~~~bash
# Liệt kê task STOPPED mà ECS hiện còn trả về.
aws ecs list-tasks \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --desired-status STOPPED

# Xem lý do dừng và mã thoát của task vừa phát hiện.
aws ecs describe-tasks \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --tasks arn:aws:ecs:ap-southeast-1:111122223333:task/training-cluster/TASK_ID \
  --query 'tasks[].{Task:taskArn,Definition:taskDefinitionArn,Status:lastStatus,StopCode:stopCode,StoppedReason:stoppedReason,StoppedAt:stoppedAt,Containers:containers[].{Name:name,Exit:exitCode,Reason:reason,Status:lastStatus}}' \
  --output json
~~~

Nếu **list-tasks** không còn hiển thị task, kiểm tra log, EventBridge event đã lưu hoặc nguồn quan sát khác; không mặc định task chưa từng chạy.

### Bước 3 — Đối chiếu service events

Nếu task do ECS service quản lý:

~~~bash
aws ecs describe-services \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --services orders-api \
  --query 'services[].{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Deployments:deployments[].{Status:status,Desired:desiredCount,Running:runningCount},Events:events[0:10]}' \
  --output json
~~~

Các sự kiện về **task placement**, **target group health**, **deployment failures**, **capacity** hoặc **resource constraints** giúp phân biệt lỗi ứng dụng với lỗi scheduler/infrastructure. Với service dùng ALB, xem health check reason từ target group và log ứng dụng. Một task có thể bị service scheduler thay thế vì health check dù ứng dụng không tự thoát trước đó.

### Bước 4 — Kiểm tra log và metric

Tìm CloudWatch log stream theo **task ID** và **container name**, lọc những phút trước khi STOPPED. Nếu không có log, xác định container có tạo stream chưa, execution role có quyền, log group có tồn tại và đường mạng tới CloudWatch Logs có hoạt động không.

Đối chiếu **CPU/memory**, thông báo OOM, database connection errors, số target healthy và network. Với task trên EC2 launch type, có thể cần kiểm tra thêm **ECS agent/container runtime logs trên EC2 host**; Fargate không cho truy cập host theo cách tương tự.

### Bước 5 — Đưa ra giả thuyết và thử nghiệm có kiểm soát

Chỉ thay đổi **một nhóm nguyên nhân** sau khi có căn cứ: sửa image tag, cấp quyền chính xác cho execution role, thêm VPC endpoint, tăng memory theo benchmark, sửa ALB path hoặc đổi cấu hình application. Sau đó chạy task trong môi trường thử nghiệm và kiểm tra task đạt **RUNNING/healthy**, log xuất hiện, API hoạt động và không còn crash loop.

## 9. Những nhóm lỗi task dừng phổ biến

| Dấu hiệu | Nguyên nhân thường gặp | Bằng chứng ưu tiên | Hướng xử lý |
|---|---|---|---|
| **CannotPullContainerError** | Image tag/digest không tồn tại, ECR permission thiếu, registry không truy cập được | stoppedReason, ECR image, execution role, VPC endpoints | Kiểm tra image URI, quyền pull, route, DNS và ECR |
| **ResourceInitializationError** | Không lấy được secret, ECR auth, env file S3 hoặc CloudWatch Logs | Message trong stoppedReason; execution role/network | Kiểm tra endpoint, SG, NAT, IAM và tài nguyên thực |
| **ResourceNotFoundException** | Secret/key/tài nguyên cần tải không tồn tại hoặc sai Region/ARN | stoppedReason và ARN | Sửa tên/ARN/Region, quyền truy cập tương ứng |
| **EssentialContainerExited** | Process container essential thoát | exitCode, application logs | Sửa lỗi ứng dụng, command, config, phụ thuộc |
| **OutOfMemoryError / OOM** | Memory container/task không đủ hoặc leak | ECS reason, exitCode, memory metrics, Java heap | Profile memory, điều chỉnh JVM, memory, leak |
| **CannotStartContainerError** | Entrypoint, quyền file, binary/architecture, mount config sai | containers[].reason, image metadata, app bootstrap | Sửa image, command, platform, mount |
| **Health check failures** | ALB/ECS health path/cổng không đạt, app khởi động chậm | ECS service events, target group health | Sửa /ready, SG/port, startPeriod/grace |
| **SpotInterruption / termination** | Spot capacity bị thu hồi, host/capacity bất thường | stopCode/event và infrastructure logs | Thiết kế retry, checkpoint, capacity dự phòng |
| **Task placement thất bại** | Thiếu CPU/RAM, subnet IP, quota, AZ capacity hoặc constraint | Service events, placement/capacity error | Bổ sung capacity hoặc sửa constraint/network |
| **ServiceSchedulerInitiated** | Deployment, scale-in hoặc service health replacement | stopCode, service events, deployment timeline | Xác nhận thao tác dự kiến trước khi xem là sự cố |

**Không dùng automation để so khớp nguyên văn stoppedReason** như một API hợp đồng ổn định; AWS có thể điều chỉnh câu chữ. Ưu tiên trường có cấu trúc **stopCode**, exitCode và những thông tin có thể kiểm chứng trong event/log. Khi không có một trường chắc chắn, xây quy tắc phát hiện với nhiều tín hiệu và giám sát kết quả.

## 10. Tình huống A: Task không tải được image trong private subnet

**Bối cảnh:** ECS service sử dụng Fargate, tasks ở private subnets. Sau lần phát hành, task chuyển **PENDING → STOPPED** với thông báo **CannotPullContainerError** hoặc một lỗi khởi tạo liên quan ECR.

Những khả năng cần kiểm tra:

1. **Image URI và tag/digest** có thực sự tồn tại trong ECR và thuộc đúng Region/account không?
2. **Task execution role** có quyền ECR cần thiết (ví dụ **ecr:GetAuthorizationToken**, **ecr:BatchGetImage**, **ecr:GetDownloadUrlForLayer**) không?
3. Task có đường mạng HTTPS đến registry/API ECR không?
4. Với private subnet không có NAT, có **VPC interface endpoints ecr.api, ecr.dkr** và **S3 gateway endpoint** cho các lớp image trong tình huống được hỗ trợ không?
5. Security group, endpoint SG, DNS, route table, NACL và các điều kiện image/cache có phù hợp không?

**Hướng xử lý:** sửa đúng image/permission/network. Không nên cấp full ECR admin cho application task role; yêu cầu pull image thường được thực hiện qua **execution role**, và kiểm tra các endpoint phù hợp với Fargate platform/Region.

## 11. Tình huống B: Log không xuất hiện ở CloudWatch

**Bối cảnh:** ECS task dừng ngay khi launch, CloudWatch log group **/ecs/orders/prod** không có stream nào.

**Không kết luận ngay code Java chưa ghi log.** Task có thể chưa tạo được container hoặc awslogs driver chưa khởi tạo. Thứ tự kiểm tra:

1. Task definition revision thật có **logConfiguration** cho container lỗi hay không?
2. **awslogs-region** có đúng với log group đang tìm? **awslogs-stream-prefix** đã khai báo với Fargate chưa?
3. Log group đã tồn tại chưa? Nếu dùng **awslogs-create-group**, execution role có **logs:CreateLogGroup** không?
4. Execution role có **logs:CreateLogStream**, **logs:PutLogEvents** trên tài nguyên phù hợp không?
5. Task có đường tới CloudWatch Logs qua NAT hoặc VPC endpoint **logs** khi cần không?
6. Có lỗi **ResourceInitializationError** về việc khởi tạo logger trong stoppedReason không?
7. Nếu dùng FireLens, log router container có crash hoặc thiếu đích/kết nối hay không?

Khi log stream bắt đầu xuất hiện, cần ghi rõ **task ID → stream name**. Đặt **retention** và quyền truy cập logs để không phải xử lý quá nhiều log nhạy cảm hoặc chi phí lưu không giới hạn.

## 12. Tình huống C: Java service dừng do memory

**Bối cảnh:** ECS task Fargate được cấp **512 MiB**, ứng dụng Java tải nhiều object lớn vào memory. Task dừng khi lưu lượng tăng, log có thể chỉ có vài dòng hoặc không có stack trace cuối cùng.

**Bước chẩn đoán:**

1. Xem **containers[].exitCode**, stoppedReason và lỗi **OutOfMemoryError** nếu có.
2. Kiểm tra CloudWatch/Container Insights memory, thời điểm tăng tải và thay đổi phiên bản.
3. Phân biệt **Java heap**, **off-heap/native memory**, thread stacks, metaspace và overhead của Java process/container.
4. Xem JVM options và kích thước heap tương quan với **task/container memory limit**; không cấu hình Xmx chiếm toàn bộ memory của container mà bỏ qua overhead.
5. Tái hiện trong staging bằng dataset/request đại diện; xác định có memory leak hay chỉ cần sizing hợp lý.

**Vì sao exitCode 137 chưa đủ?** Đây thường là kết quả SIGKILL nhưng có thể do nguyên nhân khác. Chỉ kết luận OOM khi thêm memory metrics, reason/log hoặc bằng chứng runtime phù hợp.

### Thực hành Java logging

Một ứng dụng Java nên log lỗi với **requestId**, error type và thông tin đủ tìm nguyên nhân:

~~~java
try {
    processOrder(orderId);
} catch (Exception ex) {
    log.error("Order processing failed: orderId={}", orderId, ex);
    throw ex;
}
~~~

Đoạn code minh họa; **orderId** phải không chứa dữ liệu nhạy cảm. Khi log exception, kiểm tra khả năng stack trace chứa token, request body hoặc PII. Dùng thư viện logging và structured fields theo quy định của ứng dụng.

## 13. Tình huống D: Task RUNNING nhưng bị ALB thay liên tục

**Bối cảnh:** Process Java chạy, nhưng ECS service event cho biết target unhealthy rồi service stop task và launch task mới.

**Nguyên nhân khả dĩ:**

- ALB health check dùng **/health** nhưng ứng dụng chỉ có **/actuator/health/readiness**.
- Container lắng nghe port **8080** nhưng target group/SG dùng port khác.
- Ứng dụng khởi động chậm, chưa sẵn sàng khi health check đánh giá; **healthCheckGracePeriodSeconds** hoặc start period chưa phù hợp.
- Endpoint trả 500 do dependency tùy chọn bị lỗi, gây thay thế không cần thiết.
- Route từ ALB subnets đến task ENI, security group hoặc NACL chưa phù hợp.

**Cách xử lý:** đối chiếu ECS service events, ALB target group health reason và access logs của application. Sửa đúng endpoint/protocol/port hoặc cấu hình grace phù hợp. Không chỉ tăng desiredCount để che chuỗi thay thế liên tục.

**Liveness khác readiness:** liveness cho biết tiến trình cần restart hay không; readiness cho biết có sẵn sàng phục vụ lưu lượng hay không. Thiết kế health endpoint phản ánh điều kiện thật nhưng tránh phụ thuộc quá nhiều vào service không thiết yếu.

## 14. Tình huống E: ECS Exec báo TargetNotConnectedException

**Bối cảnh:** Service đang RUNNING nhưng khi dùng **aws ecs execute-command** gặp **TargetNotConnectedException** hoặc phiên bị timeout.

Checklist thực hiện:

| Kiểm tra | Kết quả cần có |
|---|---|
| Task được tạo với ECS Exec | **enableExecuteCommand = true** |
| SSM agent | **containers[].managedAgents** có ExecuteCommandAgent **RUNNING** |
| IAM task role | Các action **ssmmessages** |
| IAM operator | **ecs:ExecuteCommand** đúng cluster/task/container |
| Đường mạng | Task tới endpoint **ssmmessages** qua HTTPS |
| VPC endpoints | SG/DNS/routing cho ssmmessages và KMS nếu dùng customer managed key |
| Container image | Có shell cần gọi, filesystem ghi được, còn CPU/memory |
| Client | AWS CLI và Session Manager plugin tương thích |

**Không mở SSH port hoặc thay task role thành AdministratorAccess để thử may rủi.** Nếu đang dùng readonlyRootFilesystem, thiết kế một quy trình chẩn đoán thay thế hoặc thay đổi image/cấu hình có phê duyệt cho workload cụ thể.

## 15. Lưu giữ sự kiện task để điều tra sau một giờ

Do task STOPPED không hiện lâu trong ECS Console, hệ thống production nên giữ **ECS Task State Change events** bằng **Amazon EventBridge** và chuyển tới kho lưu/luồng xử lý phù hợp: CloudWatch Logs, SQS, Lambda, EventBridge archive hoặc hệ thống quan sát theo thiết kế.

Một event mang các trường như **source = aws.ecs**, **detail-type = ECS Task State Change**, **detail.lastStatus**, **detail.stopCode**, **detail.stoppedReason**, **detail.containers[].exitCode** theo sự kiện thực tế.

Ví dụ event pattern dùng cho EventBridge rule để theo dõi task STOPPED:

~~~json
{
  "source": ["aws.ecs"],
  "detail-type": ["ECS Task State Change"],
  "detail": {
    "lastStatus": ["STOPPED"]
  }
}
~~~

Pattern chỉ định sự kiện muốn bắt, chưa tự tạo log destination. Cần cấu hình **EventBridge target**, IAM role/resource policy, retention, lọc dữ liệu nhạy cảm và định tuyến cảnh báo. Một task service được stop do triển khai có chủ ý cũng có thể tạo event, vì vậy alert phải phân biệt **stop có kế hoạch** và **task lỗi bất thường**.

### 15.1. Tự động hóa alert theo mức độ nghiêm trọng

Gợi ý phân tầng:

| Mức độ | Ví dụ | Hành động |
|---|---|---|
| **P1** | Service mất toàn bộ healthy targets, desired > running kéo dài | Báo động trực ca, đánh giá rollback/khôi phục |
| **P2** | Tỷ lệ task STOPPED bất thường sau deploy | Điều tra stopCode, service events, logs |
| **P3** | Một standalone batch task lỗi, có retry và DLQ | Ghi nhận, retry theo thiết kế, cảnh báo khi vượt ngưỡng |
| **Thông tin** | Task STOPPED do service scheduler rollout theo kế hoạch | Ghi event, không tạo cảnh báo khẩn nếu hệ thống vẫn khỏe |

Điều chỉnh ngưỡng theo SLO, môi trường production/staging, nhóm workload và chi phí alert. Đừng tạo cảnh báo P1 cho mọi STOPPED event.

## 16. Bảo mật, quyền và giới hạn khi chẩn đoán

### 16.1. Ít quyền nhất ở từng đường truy cập

| Vai trò | Quyền điển hình | Tránh |
|---|---|---|
| **Developer đọc log** | logs:DescribeLogStreams, logs:FilterLogEvents hoặc quyền truy vấn phù hợp | Quyền sửa/xóa log group không cần thiết |
| **ECS operator** | ecs:DescribeTasks, ecs:ListTasks, ecs:DescribeServices theo cluster/service | Quyền thay đổi mọi ECS cluster nếu không cần |
| **ECS Exec operator** | ecs:ExecuteCommand giới hạn cluster/task/container, quyền kết nối/kms liên quan | Mở ECS Exec mọi nơi hoặc bypass audit |
| **Task execution role** | ECR pull, awslogs, secret injection theo task definition | Cấp S3/DynamoDB toàn tài khoản cho ứng dụng |
| **Task role** | API ứng dụng + ssmmessages khi ECS Exec bật | AdministratorAccess, log/debug toàn bộ secret |

ECS Exec chạy lệnh dưới **root trong container**: chỉ cho phép trên task được phê duyệt, có nhật ký và timeout. Không chạy lệnh chẩn đoán có thể đổi dữ liệu production trừ khi có quy trình thay đổi chính thức.

### 16.2. Không để thông tin nhạy cảm đi vào log

Đặt bộ lọc/redaction cho:

- AWS access key, session token, API token, mật khẩu, connection string.
- Authorization/Cookie headers và dữ liệu định danh không cần thiết.
- Full request body, response body hoặc stack trace chứa payload cá nhân.
- Nội dung command/terminal output khi ECS Exec được bật audit.

Xác định **Region lưu log**, KMS encryption, retention và quyền đọc. Ghi log đầy đủ nhưng lưu quá lâu hoặc quá rộng có thể gây rủi ro an ninh và chi phí lớn.

### 16.3. Vì sao không thể chẩn đoán bằng ECS Exec mọi lúc?

Không thể Exec vào task STOPPED, task chưa bật tính năng, task không có shell hoặc cấu hình readonly rootfs không tương thích. Ngoài ra, người vận hành cũng không nên phụ thuộc vào shell access để xác nhận SLO. **Log, metric, events, health checks và tracing** phải được thiết kế trước sự cố.

## 17. Quy trình chuẩn khi triển khai và xử lý sự cố

### Trước triển khai

1. Tạo task definition với **awslogs** hoặc FireLens theo yêu cầu, chọn log group và retention.
2. Đặt **task execution role** và **task role** đúng trách nhiệm; kiểm tra image/ECR, secret, KMS và VPC connectivity.
3. Thiết lập **CloudWatch metrics/Container Insights**, ECS service event monitoring, EventBridge state change capture và SLO.
4. Nếu cần ECS Exec ở môi trường cụ thể, bật có kiểm soát, tạo quyền ssmmessages, operator IAM, logging phiên và thử trước.
5. Tạo health check có ý nghĩa, graceful shutdown và đảm bảo memory/CPU cho app cùng sidecar/SSM agent.

### Khi task dừng bất thường

1. **Không thay đổi quyền hoặc capacity ngay.** Ghi timestamp, deployment version, task ARN, cluster/Region.
2. Xem **stopCode + stoppedReason + containers[].exitCode/reason**.
3. Xem **service events** và đối chiếu có deployment/scale-in/health replacement không.
4. Tìm **CloudWatch Logs** theo task ID; nếu trống, quay về kiểm tra logger/execution role/network.
5. Xem **metrics** để kiểm chứng memory, CPU, health; xem Events đã lưu nếu task không còn tra cứu được.
6. Tái hiện trong staging/lab; với task còn RUNNING, có thể dùng ECS Exec có phê duyệt.
7. Sửa đúng nguyên nhân, triển khai có rollback, xác minh task ổn định, target healthy, log đầy đủ và SLO đạt.

### Sau sự cố

Ghi lại **nguyên nhân gốc, bằng chứng, thay đổi, kết quả sau sửa, rủi ro còn lại và hành động ngăn lặp lại**. Nếu lỗi do thiếu log hoặc thiếu sự kiện lịch sử, ưu tiên bổ sung observability để lần sau không mất dữ liệu điều tra.

## 18. Bài tập thực hành

### Bài tập A — Thiết lập log cho Java API

Một service Java chạy Fargate có container tên **billing-api**. Mục tiêu là lưu stdout/stderr tại CloudWatch Logs, truy vết được mỗi task theo ID và chỉ giữ log theo retention của tổ chức.

**Yêu cầu:** đề xuất log group, stream prefix, quyền execution role và ví dụ đoạn **logConfiguration**. Mô tả cách xác minh sau deploy bằng **aws logs tail** và **ecs describe-tasks**.

**Gợi ý:** log group **/ecs/billing/prod**, prefix **billing**; dùng **awslogs**, pre-create log group, cấp **logs:CreateLogStream/PutLogEvents** cho execution role, rồi kiểm tra stream dạng **billing/billing-api/TASK_ID**.

### Bài tập B — CloudWatch không có log

Task STOPPED trước khi in “Application started”, trong stoppedReason có thông báo liên quan **ResourceInitializationError** và CloudWatch logging.

**Yêu cầu:** nêu ít nhất bốn giả thuyết cần kiểm tra trước khi kết luận lỗi Java.

**Gợi ý:** log group chưa có, sai Region, thiếu quyền execution role, không có đường mạng đến **logs** endpoint, cấu hình awslogs sai hoặc task chưa tạo thành công.

### Bài tập C — ECS Exec không có agent RUNNING

Task đang RUNNING nhưng **enableExecuteCommand = false**. Một kỹ sư có quyền ecs:ExecuteCommand vẫn không mở được phiên.

**Yêu cầu:** giải thích vì sao IAM Allow không đủ và đề xuất cách khắc phục.

**Gợi ý:** task hiện tại chưa được tạo với ECS Exec. Bật tính năng cho service/task **mới**, lập kế hoạch deployment, kiểm tra managedAgent, task role ssmmessages, network và plugin. Không thể sửa cờ trên task đã tồn tại.

### Bài tập D — Container exit 137

Một Java worker dừng với **exitCode 137** và service tự thay task. Memory utilization tăng cao ở thời điểm sự cố.

**Yêu cầu:** nêu bằng chứng để kết luận OOM, cách phân biệt OOM với SIGKILL khác và phương án sửa lâu dài.

**Gợi ý:** đối chiếu reason/CloudWatch metrics/runtime logs, JVM heap/off-heap/threads, memory limit và load test. Khắc phục memory leak, streaming/chunking hoặc sizing phù hợp; đừng chỉ tăng RAM mà bỏ qua nguyên nhân.

### Bài tập E — EventBridge cảnh báo quá nhiều

Hệ thống gửi P1 mỗi khi có event **ECS Task State Change → STOPPED**, kể cả lúc rollout bình thường.

**Yêu cầu:** thiết kế cách lọc/cảnh báo tốt hơn.

**Gợi ý:** phân biệt stopCode và service deployment/desired/healthy targets, đo tỷ lệ STOPPED bất thường, kiểm tra batch kết thúc thành công, giữ event lịch sử và dùng metric/SLO trước khi nâng severity.

## 19. Checklist production

- [ ] Task definition có log driver phù hợp cho từng container cần quan sát.
- [ ] Log group, Region, stream prefix, retention và mã hóa phù hợp.
- [ ] **Execution role** có quyền image pull, logs và secret injection theo task definition.
- [ ] **Task role** có đúng quyền API ứng dụng; thêm ssmmessages chỉ khi ECS Exec được duyệt.
- [ ] Logs chứa timestamp, severity, service, version, request/trace ID và không lộ bí mật.
- [ ] FireLens router/sidecar (nếu dùng) có resource, retry, log và monitoring riêng.
- [ ] Có CloudWatch metrics, Container Insights hoặc phương án giám sát tương đương.
- [ ] Có quy trình lưu **ECS task STOPPED events** qua EventBridge để điều tra lâu dài.
- [ ] Có runbook đọc stopCode, stoppedReason, container exitCode và service events.
- [ ] ECS Exec chỉ được bật cho task mới đúng quy trình, có operator IAM và Session Manager plugin.
- [ ] Task được phép Exec có **ExecuteCommandAgent RUNNING**, network tới ssmmessages và filesystem ghi được.
- [ ] Phiên Exec có log/audit phù hợp; ECS Exec chạy root nên được giới hạn chặt.
- [ ] Đã kiểm thử image pull, secrets, CloudWatch Logs, DNS/VPC endpoints và ALB health.
- [ ] Đã kiểm thử graceful shutdown, OOM/Crash, deployment replacement và retry cho batch.
- [ ] Đã tính log ingestion/storage/query, FireLens overhead, CloudWatch và mạng vào ngân sách.

## 20. Ghi nhớ

Khi một ECS task bị dừng, hãy **lấy bằng chứng trước**: log container nếu có, **stopCode**, **stoppedReason**, **exitCode**, service events và metric theo thời điểm. **awslogs** thu stdout/stderr của container, còn **FireLens** phục vụ định tuyến log nâng cao; những quyền này thường liên quan đến **task execution role** và mạng. **ECS Exec** cho phép kiểm tra tương tác một task **RUNNING** đã được bật tính năng, sử dụng **SSM Session Manager**, **task role ssmmessages**, quyền operator và kiểm toán phù hợp. Exec không sửa được lịch sử của task đã STOPPED. Một kiến trúc vận hành tốt cần chuẩn bị sẵn **logging, metrics, task state events, IAM least privilege, network endpoints và runbook có kiểm thử**, trước khi xảy ra sự cố.

### Tài liệu AWS chính thức để đối chiếu khi triển khai

- [Amazon ECS task logging với awslogs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html) — thu log container.
- [LogConfiguration API](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html) — log driver và các tham số.
- [Using FireLens to route container logs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html) — sidecar và routing.
- [Monitor Amazon ECS containers with ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html) — điều kiện, quyền, giới hạn, logging phiên.
- [Running commands using ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec-run.html) — lệnh AWS CLI và Session Manager plugin.
- [Amazon ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) — quyền của ứng dụng.
- [Amazon ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) — quyền ECR/log/secrets.
- [Viewing Amazon ECS stopped task errors](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/stopped-task-errors.html) — CLI và ECS Console.
- [Amazon ECS stopped task error categories](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/stopped-task-error-codes.html) — các nhóm lỗi khi dừng.
- [Resolve Amazon ECS stopped task errors](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/resolve-stopped-errors.html) — phương pháp khắc phục.
- [ECS task API stopCode and stoppedReason](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Task.html) — định nghĩa các trường trạng thái.
- [ECS task lifecycle events and EventBridge](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-lifecycle-events.html) — lưu dấu vết vòng đời.
- [Troubleshooting ECS OutOfMemoryError](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/out-of-memory.html) — memory failures.
- [CloudWatch Logs Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html) — truy vấn logs.
- [Amazon ECS pricing](https://aws.amazon.com/ecs/pricing/) và [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/) — chi phí vận hành.
