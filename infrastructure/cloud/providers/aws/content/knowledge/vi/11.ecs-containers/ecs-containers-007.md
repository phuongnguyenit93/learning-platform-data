# Mạng awsvpc, Security Group và kết nối ALB

> **Chương:** Container với ECS  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — tìm hiểu hệ sinh thái AWS từ Region/AZ, IAM và VPC tới tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; thực hành thiết kế, triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

Trong Amazon Elastic Container Service (**Amazon ECS**), một ứng dụng container không thể phục vụ người dùng chỉ nhờ image chạy thành công. Ứng dụng còn cần địa chỉ mạng, cổng lắng nghe, quy tắc bảo mật, định tuyến và một cách đưa request đến những **task** đang khỏe. Với network mode **`awsvpc`**, ECS cấp giao diện mạng trong VPC cho task; với **Application Load Balancer (ALB)**, hệ thống phân phối HTTP(S) tới các task qua **target group**.

Bài học tập trung vào ba câu hỏi liên kết với nhau:

1. **`awsvpc`:** task được cấp IP, ENI và cổng như thế nào?
2. **Security Group:** ai được gửi traffic tới task và task được gọi những hệ thống nào?
3. **ALB:** làm sao listener, target group và health check tìm đúng IP/port của task, ngay cả khi task bị thay thế?

Các tên tài nguyên, VPC CIDR, ID và image trong bài đều mang tính minh họa. Trước khi triển khai production phải đối chiếu tính năng và quota theo Region, launch type, phiên bản nền tảng và yêu cầu bảo mật thật.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích mô hình **task ENI** của `awsvpc` và sự khác nhau với `bridge`, `host` ở những trường hợp ECS hỗ trợ.
2. Vẽ đường đi **client → ALB listener → target group → task IP:containerPort**, kể cả health check.
3. Chọn **target type `ip`** cho ECS tasks dùng `awsvpc` và phân biệt với `instance`.
4. Cấp Security Group theo **least privilege** cho ALB, ECS tasks, cơ sở dữ liệu và interface VPC endpoints.
5. Hiểu cách private subnet, NAT Gateway, VPC endpoints, DNS và IAM ảnh hưởng tới việc pull image, gửi log và truy cập AWS API.
6. Đọc một cấu hình mẫu Task Definition/ECS Service và xử lý lỗi `Target.Timeout`, `Target.ResponseCodeMismatch`, `CannotPullContainerError`, `ResourceInitializationError`.
7. Đánh giá những vấn đề vận hành như nhiều AZ, deployment, graceful shutdown, capacity, monitoring và chi phí.

## 2. Mô hình tư duy: ECS cluster, service, task và ENI

| Thành phần | Trách nhiệm | Tác động đến mạng |
| --- | --- | --- |
| **Cluster** | Nhóm logic quản lý ECS tasks/services | Không tự cấp IP công khai cho mọi task |
| **Task Definition** | Mẫu chạy container: image, CPU/memory, port, IAM roles, network mode | `networkMode: awsvpc` quy định cách task dùng mạng VPC |
| **Task** | Một lần chạy của Task Definition, gồm một hoặc nhiều container | Có network interface/IP khi dùng `awsvpc` |
| **Service** | Duy trì desired task count, thay task lỗi, quản lý deployment | Gắn task với ALB target group và đặt task trong subnet/SG |
| **ALB** | Nhận HTTP(S), chọn target theo listener/rules và target-group health | Chuyển request tới **private IP và port** của task |
| **Security Group** | Tường lửa stateful tại ENI | Chỉ cho phép luồng được cấp quyền, áp dụng cho ENI của task |

Trong `awsvpc`, mỗi task có **task networking riêng**. Về mặt logic, task được gắn một **Elastic Network Interface (ENI)** và có **private IP** trong subnet đã chọn. Các container trong **cùng task** chia sẻ network namespace và có thể trao đổi qua `localhost` nếu cổng phù hợp; các **task khác nhau** có IP/ENI riêng nên không giao tiếp với nhau bằng `localhost`.

### 2.1. Mạng của task trên Fargate và EC2

- **AWS Fargate:** bắt buộc dùng `awsvpc`. Trên các platform version hiện hành phù hợp, traffic của task đi qua task ENI; bạn quản lý subnet và Security Group, không quản lý máy chủ EC2 làm host.
- **ECS trên EC2:** hỗ trợ `awsvpc` cùng các network mode khác tùy hệ điều hành và cấu hình. Với `awsvpc`, task dùng ENI/task IP; năng lực gắn ENI của container instance và hỗ trợ **awsvpcTrunking** có thể ảnh hưởng mật độ task.
- **Windows containers:** khả năng hỗ trợ network mode, version và kiến trúc có điểm khác Linux. Không bê nguyên mọi ví dụ network mode của Linux sang Windows mà chưa kiểm tra tài liệu.

**Task ENI khác EC2 instance ENI theo mục đích phân quyền.** Với `awsvpc`, Security Group dành cho **task** giúp kiểm soát riêng workload thay vì mở cổng cho toàn bộ EC2 host. Trên Fargate, đây là mô hình vận hành mạng tiêu chuẩn.

### 2.2. So sánh `awsvpc` với `bridge` và `host`

| Network mode | Mô hình điển hình | Host port | Dùng với ALB |
| --- | --- | --- | --- |
| **`awsvpc`** | Task có IP trong VPC và task ENI | `hostPort` bằng `containerPort` hoặc để ECS xác định theo quy tắc mode | **Target group type `ip`** |
| **`bridge`** | Container Linux chia sẻ đường mạng host qua bridge/NAT | Có thể dùng dynamic host port mapping trên EC2 | Target registration thường theo instance ID và host port |
| **`host`** | Container dùng network namespace của EC2 host | Port của container tương ứng với host | Cần quản lý va chạm port khi đặt task trên EC2 |

Với ứng dụng mới dùng Fargate, `awsvpc` giúp ánh xạ rõ **task IP + cổng ứng dụng**, dễ áp Security Group theo service. Đổi lại, cần đủ địa chỉ IP trong subnet và xét giới hạn ENI/compute.

### 2.3. Một task có hai container thì sao?

Ví dụ task gồm `api` và `telemetry-sidecar`:

~~~text
Task ENI: 10.30.10.25
├── api               : lắng nghe 0.0.0.0:8080
└── telemetry-sidecar : lắng nghe 127.0.0.1:4317

Từ api trong cùng task: gọi localhost:4317
Từ ALB bên ngoài task: gọi 10.30.10.25:8080
~~~

Hai container trong cùng task **không thể cùng bind một IP/port xung đột**. Nếu API chỉ bind `127.0.0.1:8080`, ALB từ bên ngoài task không thể kết nối tới `10.30.10.25:8080`. Hãy để listener của ứng dụng lắng nghe `0.0.0.0` hoặc địa chỉ phù hợp khi phải nhận traffic qua ENI.

## 3. Kiến trúc tham chiếu: ALB public, ECS tasks private

Giả sử một ứng dụng API được container hóa và triển khai trên Fargate ở hai Availability Zone (**AZ A/B**) trong một VPC.

~~~mermaid
flowchart TB
    User["Người dùng Internet"] --> DNS["Route 53 / DNS"]
    DNS -.->|"Trả tên/địa chỉ"| User
    User --> ALB["ALB internet-facing\nHTTPS listener :443"]
    ALB --> TG["Target group\nTarget type = ip; HTTP :8080"]

    subgraph VPC["VPC 10.30.0.0/16"]
      subgraph AZA["Availability Zone A"]
        PubA["Public subnet A\nALB nodes; NAT-A nếu cần"]
        AppA["Private app subnet A\nTask ENI 10.30.10.25:8080"]
      end
      subgraph AZB["Availability Zone B"]
        PubB["Public subnet B\nALB nodes; NAT-B nếu cần"]
        AppB["Private app subnet B\nTask ENI 10.30.11.31:8080"]
      end
      TG --> AppA
      TG --> AppB
      AppA --> DB["RDS / service dữ liệu private"]
      AppB --> DB
      AppA -.->|"HTTPS egress"| PubA
      AppB -.->|"HTTPS egress"| PubB
    end
    AppA -.->|"Logs / image / secrets theo kết nối phù hợp"| AWS["ECR, S3, CloudWatch Logs,\nSecrets Manager"]
    AppB -.->|"Logs / image / secrets theo kết nối phù hợp"| AWS
~~~

*Sơ đồ thể hiện quan hệ logic, không phải tất cả hop mạng. ALB là một tài nguyên logic trải các subnet được bật ở nhiều AZ; target group lưu task IP động do ECS đăng ký. Đường thực tế tới dịch vụ AWS phụ thuộc NAT hoặc VPC endpoints và IAM.*

### 3.1. Kế hoạch subnet mẫu

| Thành phần | CIDR minh họa | AZ | Route mặc định IPv4 |
| --- | --- | --- | --- |
| `public-a` | `10.30.0.0/24` | A | `0.0.0.0/0 → Internet Gateway` |
| `public-b` | `10.30.1.0/24` | B | `0.0.0.0/0 → Internet Gateway` |
| `app-a` | `10.30.10.0/24` | A | `0.0.0.0/0 → NAT-A` nếu ứng dụng cần Internet egress |
| `app-b` | `10.30.11.0/24` | B | `0.0.0.0/0 → NAT-B` nếu ứng dụng cần Internet egress |
| `db-a` | `10.30.20.0/24` | A | Không cần default Internet route nếu DB không cần egress đó |
| `db-b` | `10.30.21.0/24` | B | Không cần default Internet route nếu DB không cần egress đó |

Mỗi **subnet nằm trong một AZ**. Subnet có thể chứa nhiều task ENI; phải dự trù số private IP cho desired count, scale-out, **deployment overlap** (task cũ và mới cùng chạy một thời gian), ALB/endpoint ENI và các hạ tầng khác.

**Private subnet** không đồng nghĩa task không bao giờ kết nối được Internet. Task không nhận public IP, nhưng có thể chủ động kết nối outbound qua NAT hoặc truy cập AWS service qua VPC endpoint khi được cấu hình.

### 3.2. Đường đi của một request HTTPS

1. Client phân giải `api.example.com`, kết nối HTTPS tới ALB public trên cổng `443`.
2. **ALB Security Group** xét inbound từ client.
3. ALB listener kiểm tra rule theo host/path, chọn **target group** của ECS service.
4. ALB gửi request (ví dụ HTTP tới `8080`) đến **private IP của task ENI** đã đăng ký trong target group.
5. **Task Security Group** xét inbound `TCP 8080`, cho phép khi nguồn hợp lệ, ví dụ SG của ALB.
6. Container `api` xử lý và gửi phản hồi; Security Group stateful tự cho phép phản hồi của kết nối được theo dõi.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant L as ALB :443
    participant T as ECS Task 10.30.10.25:8080
    participant D as Database :5432
    C->>L: HTTPS GET /orders
    L->>T: HTTP GET /orders, target IP:8080
    T->>D: TCP 5432 (nếu cần)
    D-->>T: Kết quả dữ liệu
    T-->>L: HTTP 200 + JSON
    L-->>C: HTTPS 200 + JSON
~~~

Với mô hình ALB terminate TLS, đoạn **ALB → task** có thể dùng HTTP nội bộ. Nếu yêu cầu bảo mật cần TLS end-to-end, chọn target group HTTPS và cấu hình chứng chỉ/trust phù hợp trên container; không suy rằng TLS ở listener tự bảo vệ luôn hop backend.

## 4. `awsvpc`: IP, cổng và giới hạn vận hành

### 4.1. Task có IP nào?

Trong ECS Service sử dụng `awsvpc`, phần `networkConfiguration.awsvpcConfiguration` chỉ định:

- Danh sách **subnet IDs** được phép đặt tasks.
- Danh sách **Security Group IDs** gắn với task ENI.
- `assignPublicIp` là `ENABLED` hoặc `DISABLED` trong các môi trường hỗ trợ; production thường chọn **`DISABLED`** khi tasks nằm sau ALB trong private subnet.

Nếu service đặt task ở nhiều subnet khác AZ, ECS có thể triển khai tasks ở các subnet/AZ đó theo cơ chế scheduler và năng lực sẵn có. Tuy nhiên, không nên coi việc có hai subnet trong cấu hình là **cam kết** rằng lúc nào cũng có đúng một nửa tasks ở mỗi AZ; phải quan sát phân bố, capacity và chiến lược scaling.

### 4.2. Port mapping trong Task Definition

Ví dụ task definition chọn `networkMode=awsvpc` và container `api` lắng nghe `8080`:

~~~json
{
  "networkMode": "awsvpc",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/shop-api:release-2026-11",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ]
    }
  ]
}
~~~

*Đây là fragment để đọc và phân tích, không phải Task Definition hoàn chỉnh: bản triển khai Fargate còn cần family, CPU, memory, execution role và các trường phù hợp khác.*

Với `awsvpc`, `hostPort` có thể bỏ qua hoặc bằng `containerPort` theo quy tắc của mode; không dùng mô hình dynamic host port kiểu `bridge` để yêu cầu `hostPort=0` ánh xạ sang một port host ngẫu nhiên. ALB kết nối tới **task IP:8080**, không phải IP của EC2 host với một port được phân phát.

**Quan trọng:** trường `containerPort` là thông tin ECS dùng để định tuyến/đăng ký target, nhưng **không tự khởi động server bên trong image**. Ứng dụng cần thật sự lắng nghe cổng tương ứng. Dockerfile `EXPOSE` cũng chỉ là metadata, không thay thế cấu hình listener.

### 4.3. ENI, IP và khả năng mở rộng

Với Fargate, IP/ENI của task được cấp khi task khởi tạo và giải phóng khi task dừng theo cơ chế dịch vụ. Khi ECS thay thế task:

~~~text
Task cũ  arn:...:task/old  →  10.30.10.25:8080
Task mới arn:...:task/new  →  10.30.10.47:8080
~~~

ALB không nên hardcode IP cũ vào ứng dụng. **ECS Service tự quản lý target registration/deregistration** cho các tasks theo cấu hình load balancer.

Những giới hạn cần tính:

- **IP address utilization** ở từng subnet: scale-out và rolling deployment có thể cần nhiều IP hơn số task ổn định.
- **EC2 network limits** nếu chạy ECS EC2 với `awsvpc`: ENI/trunking, instance types và resource availability.
- **Fargate quota / task CPU-memory** và nguồn capacity theo AZ.
- **Kết nối đến phụ thuộc**: không chỉ CPU; RDS connection limits, NAT connection capacity và downstream throughput cũng có thể trở thành điểm nghẽn.

## 5. Security Group theo nguyên tắc least privilege

Security Group là **stateful**. Nó đánh giá inbound/outbound tại network interface; phản hồi của một connection được theo dõi thường được cho phép mà không cần rule đối xứng dành riêng cho ephemeral ports. **Network ACL** ở subnet là stateless, có Allow/Deny theo rule number và vẫn phải kiểm tra **cả hai chiều** khi cấu hình tùy chỉnh.

### 5.1. Bốn nhóm Security Group

Giả sử:

- `sg-alb` gắn ALB.
- `sg-api` gắn ECS task ENI.
- `sg-db` gắn RDS.
- `sg-vpce` gắn các interface VPC endpoints (nếu dùng).

| Security Group | Inbound nên cân nhắc | Outbound cần cân nhắc |
| --- | --- | --- |
| **`sg-alb`** | `TCP 443` từ client/CIDR hợp lệ | `TCP 8080` đến `sg-api` và port health check nếu khác |
| **`sg-api`** | `TCP 8080` **chỉ từ `sg-alb`** | `TCP 5432` đến `sg-db`, `TCP 443` tới endpoints/API cần dùng |
| **`sg-db`** | `TCP 5432` **chỉ từ `sg-api`** | Phù hợp với hoạt động DB và chính sách mạng |
| **`sg-vpce`** | `TCP 443` từ `sg-api` hoặc CIDR private được phép | Phản hồi trên kết nối stateful; xem chính sách endpoint |

Security Group rule có thể tham chiếu **Security Group ID** làm nguồn/đích trong các trường hợp được AWS hỗ trợ. Nhờ vậy, nếu task cũ `10.30.10.25` bị thay bằng task mới `10.30.10.47`, bạn **không phải cập nhật CIDR/IP trong SG của ALB hoặc database**.

### 5.2. Rule minh họa cho ALB

~~~text
sg-alb
  IN  TCP 443   Source 0.0.0.0/0    (nếu API thực sự công khai)
  OUT TCP 8080  Destination sg-api

sg-api
  IN  TCP 8080  Source sg-alb
  OUT TCP 5432  Destination sg-db
  OUT TCP 443   Destination được phép cho API và AWS endpoints

sg-db
  IN  TCP 5432  Source sg-api
~~~

Nếu chỉ có nhân viên nội bộ sử dụng, ALB nên có **`Scheme: internal`** hoặc đầu vào mạng được giới hạn thay vì mở public `0.0.0.0/0`. Nếu cần IPv6, thêm rule IPv6 phù hợp (`::/0` khi thật sự public) và kiểm tra ALB IP address type/VPC.

**Đừng chỉ tạo inbound cho `sg-api` rồi bỏ quên outbound.** Khi quản lý egress chặt, task vẫn cần truy cập database, ECR/S3 để lấy image, CloudWatch Logs, Secrets Manager hoặc dịch vụ khác tùy vòng đời và ứng dụng. Default outbound “allow all” của SG mới có thể giúp demo chạy nhanh, nhưng không phải chính sách least privilege cuối cùng.

### 5.3. Vì sao không mở `TCP 8080` từ toàn Internet cho task?

Task trong private subnet có thể không có route công khai, nhưng mở SG quá rộng vẫn làm tăng phạm vi truy cập từ **các mạng kết nối với VPC**, gồm peering, VPN hoặc transit gateway nếu tồn tại và routing phù hợp. Quy tắc “API task chỉ nhận từ `sg-alb`” giảm diện tấn công và ngăn các nguồn được định tuyến tới task nhưng không được ủy quyền.

Security Group **không xác thực người dùng HTTP**: ALB có thể làm TLS/authentication một phần, nhưng ứng dụng vẫn phải xác minh token, quyền truy cập dữ liệu và chống request giả mạo theo nghiệp vụ.

### 5.4. Network ACL có ảnh hưởng thế nào?

Nếu sử dụng custom NACL, hãy xem cả các subnet **ALB** và **task**:

| Packet | Ranh giới | Destination port cần xét |
| --- | --- | --- |
| Client → ALB | Inbound public subnet | `443` |
| ALB → client | Outbound public subnet | Ephemeral port của client |
| ALB → task | Outbound public subnet và inbound private app subnet | `8080` |
| Task → ALB | Outbound app subnet và inbound public subnet | Ephemeral port của kết nối phía ALB |

Đây là mô hình tổng quát của luồng TCP, không phải bảng rule hoàn chỉnh cho toàn VPC. Port ephemeral phụ thuộc nền tảng/đường đi; còn health checks, egress tới AWS APIs, DB và các service khác có luồng riêng. Một NACL **Deny** có thể chặn traffic dù SG đã Allow.

## 6. Kết nối ALB: listener, target group và target type

**ALB** hoạt động ở Layer 7; một listener nhận HTTP/HTTPS theo **port**, sau đó listener rules chọn hành động, thường là **forward tới target group**. Target group chứa các target mà ALB sẽ gửi request đến, được đánh giá sức khỏe theo health check.

### 6.1. Vì sao `TargetType=ip` là bắt buộc với `awsvpc`?

Với ECS Service dùng `awsvpc`, AWS yêu cầu **target group có target type `ip`**, không dùng `instance`. Lý do: traffic phải đến **task ENI/private IP**, không đến ID của EC2 container instance.

~~~text
Đúng với awsvpc:
  Target type: ip
  ECS đăng ký: 10.30.10.25:8080, 10.30.11.31:8080

Sai với awsvpc:
  Target type: instance
  Mong ECS đăng ký: i-0123456789abcdef0:8080
~~~

`instance` có chỗ dùng trong các thiết kế ECS EC2 với mạng/port mapping tương ứng, nhưng **không áp dụng trực tiếp cho `awsvpc`**.

### 6.2. Listener và target group khớp cổng thế nào?

Một cấu hình phổ biến:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| ALB scheme | `internet-facing` | Tiếp nhận traffic công khai |
| ALB listener | `HTTPS :443` | TLS với chứng chỉ ACM |
| Listener rule | `Host: api.example.com` hoặc `Path: /api/*` | Chọn backend theo yêu cầu |
| Target group | `HTTP :8080`, `TargetType=ip` | Tập ECS task IP:port |
| ECS Service load balancer | `containerName=api`, `containerPort=8080` | Gắn đúng container với target group |
| Container app | Lắng nghe `0.0.0.0:8080` | Nhận request/health check |

Không có yêu cầu ALB listener port phải bằng container port. ALB có thể terminate HTTPS ở `443` và forward HTTP ở `8080`. Với kết nối nội bộ đòi TLS, target group có thể chọn HTTPS nếu server container thực sự hỗ trợ.

### 6.3. Health check của target group

Ví dụ:

~~~text
Protocol: HTTP
Port: traffic-port (8080)
Path: /health/ready
Success code: 200
Interval: 30 seconds (ví dụ)
Healthy threshold: 2
Unhealthy threshold: 3
Timeout: theo cấu hình hỗ trợ
~~~

Health check là request thật từ các ALB nodes tới task. Nó cần **Network ACL/Security Group cho phép** đường đi và container phải trả status đúng. Nếu ứng dụng chỉ có endpoint `/health/ready` mà target group mặc định kiểm tra `/` (trả `404`), ECS task có thể `RUNNING` nhưng target vẫn **unhealthy**.

Phân biệt:

- **ECS container health check:** command chạy trong container (nếu khai báo) để báo tình trạng container.
- **ALB target-group health check:** request qua mạng đến IP/port/path của target.
- **ECS Service scheduler:** dùng kết quả health checks và cơ chế triển khai để thay tasks hoặc chờ service ổn định.

Một container báo `HEALTHY` nhưng ALB `unhealthy` có thể do mạng/port/HTTP path. Ngược lại, ALB có thể truy cập được một trang `200` nhưng nghiệp vụ thực tế chưa sẵn sàng. Tín hiệu health cần được thiết kế sát nhu cầu.

### 6.4. Không phải cứ `RUNNING` là đã nhận traffic

Các bước thường diễn ra:

~~~mermaid
flowchart LR
    NEW["ECS tạo task"] --> ENI["ENI/IP + SG"]
    ENI --> PULL["Pull image + init/log/secrets"]
    PULL --> START["Container chạy, listener khởi động"]
    START --> REG["Đăng ký task IP:port vào target group"]
    REG --> HEALTH["ALB health checks"]
    HEALTH --> READY["Target healthy, nhận request"]
    READY --> DRAIN["Deployment/scale-in: deregistration/draining"]
    DRAIN --> STOP["Task được dừng"]
~~~

*Trình tự thực tế có thể chồng lấn ở một số giai đoạn. Diagram minh họa các trạng thái mà người vận hành cần kiểm tra, không phải một máy trạng thái chính xác của toàn bộ ECS/ELB API.*

**ALB có hành vi “fail-open”** trong một số tình huống khi tất cả registered targets của target group trong các AZ đang bật đều bị đánh giá không khỏe: ALB vẫn có thể phân phối request tới các target đó. Vì vậy, **không dựa vào ALB health check như cơ chế duy nhất để chặn mọi request nguy hiểm**; cần xử lý lỗi phù hợp trong ứng dụng và chiến lược DR.

### 6.5. Grace period và draining

- **`healthCheckGracePeriodSeconds`** trong ECS Service cho phép scheduler bỏ qua một số tình trạng health-check không khỏe trong thời gian ứng dụng khởi động; giá trị cần dựa trên thời gian init thực tế, không dùng để che lỗi liên tục.
- **Target group deregistration delay** giúp các kết nối/request đang xử lý có thời gian hoàn tất khi target bị loại khỏi vòng nhận request; nhưng không thể bảo đảm mọi request dài đều thành công.
- **SIGTERM và graceful shutdown**: ứng dụng cần ngừng nhận việc mới, kết thúc request đang xử lý, giải phóng DB connections và thoát trong giới hạn được ECS/nền tảng cấp.
- **Deployment circuit breaker/rollback** (với kiểu ECS deployment được hỗ trợ) giúp giảm rủi ro rollout không đạt steady state; cần kiểm tra cấu hình và cơ chế rollback đang bật.

Health check không nên “đợi database trả lời 15 giây” khi phần lớn request cần vài trăm mili giây. Chọn timeout, threshold và readiness nhất quán với SLO.

## 7. VPC egress của ECS tasks trong private subnet

Một task private thường cần hai nhóm kết nối:

1. **Lưu lượng phục vụ:** ALB gửi request đến task; task truy cập RDS, Redis, service nội bộ.
2. **Lưu lượng khởi tạo và vận hành:** tải image ECR, đọc secret, gửi log, gọi AWS API, cập nhật telemetry.

Khi egress lỗi, ECS task có thể **không khởi động được** hoặc không gửi được log, mặc dù ALB SG và task SG đã cho phép `TCP 8080`.

### 7.1. NAT Gateway

Giải pháp dễ hiểu là gắn private subnet với route mặc định `0.0.0.0/0` tới NAT Gateway ở public subnet, trong khi NAT có đường Internet Gateway phù hợp.

~~~text
App subnet A: 0.0.0.0/0 -> NAT-A (public subnet AZ A)
App subnet B: 0.0.0.0/0 -> NAT-B (public subnet AZ B)
~~~

Mẫu **NAT theo AZ** giảm phụ thuộc egress vào một AZ. Một NAT zonal đặt ở AZ A dùng chung cho tasks AZ B có thể trở thành điểm lỗi đơn khi AZ A gặp sự cố. Tuy nhiên, mỗi NAT Gateway có phí theo thời gian và lượng dữ liệu xử lý; phải cân nhắc **availability vs cost**.

NAT **không làm task private trở thành endpoint công khai**: nó hỗ trợ các kết nối outbound được khởi tạo từ mạng private.

### 7.2. VPC endpoints cho các dịch vụ AWS cần thiết

Với Fargate pull image từ **Amazon ECR** và dùng **awslogs**, những endpoint thường được đánh giá:

| Dịch vụ | Loại kết nối/endpoint thường gặp | Mục đích |
| --- | --- | --- |
| **ECR API** | Interface endpoint `com.amazonaws.<region>.ecr.api` | Xác thực/metadata ECR trong quy trình pull |
| **ECR Docker registry** | Interface endpoint `com.amazonaws.<region>.ecr.dkr` | Docker Registry API khi lấy image |
| **Amazon S3** | Gateway endpoint cho S3 | Truy cập các lớp image/lưu trữ S3 theo đường phù hợp |
| **CloudWatch Logs** | Interface endpoint `com.amazonaws.<region>.logs` | Container log delivery qua `awslogs` |
| **Secrets Manager** | Interface endpoint `com.amazonaws.<region>.secretsmanager` | Truy xuất secrets ở bước khởi tạo/app |
| **SSM Parameter Store** | Endpoint `ssm` và endpoint liên quan khi cần | Đọc parameters tùy cơ chế app |

Danh sách trên là **tham khảo theo nhu cầu**. Các yêu cầu endpoint còn phụ thuộc Fargate platform version, ECR/registry công khai hay riêng, image layer location, loại secrets, AWS Regions và cách ứng dụng gọi API. Không phải mọi service ECS đều cần toàn bộ endpoint; ngược lại, thiếu endpoint cho một dependency thực sự đang dùng có thể làm deployment thất bại.

**Cấu hình PrivateLink:** interface endpoint ENI có Security Group cần cho phép inbound `TCP 443` từ task SG; cần VPC DNS/private DNS, route/NACL và endpoint policy phù hợp. S3 gateway endpoint sử dụng route table và policy khác interface endpoint; không thể chỉ tạo endpoint rồi mặc định mọi luồng AWS API đã thông.

### 7.3. Role nào cần quyền ECR và ghi log?

Trong Task Definition thường phân biệt:

- **Task execution role:** ECS/Fargate dùng cho các hoạt động như pull image từ ECR, ghi CloudWatch Logs qua log driver và lấy secrets được ECS inject theo hỗ trợ.
- **Task role:** containerized application dùng AWS SDK/API, ví dụ gọi S3 hoặc DynamoDB.

Hai role **không đồng nghĩa**. Ví dụ app có task role được `s3:GetObject` nhưng execution role thiếu ECR permissions vẫn không pull image được; ngược lại cấp execution role quá rộng không thay thế đúng quyền mà ứng dụng cần bên trong container.

## 8. Cấu hình triển khai mẫu bằng CloudFormation

Đoạn sau minh họa một ECS Fargate service chạy sau ALB HTTPS, task network mode `awsvpc`, các tasks nằm trong **hai private app subnets**. Ví dụ giả định **VPC, public/private subnets, Security Groups, ECS cluster, ACM certificate, ECR image và IAM roles đã tồn tại**. Đây là tài liệu để đọc và tùy biến, **không phải template production hoàn chỉnh**: triển khai thật tạo ALB, task và các tài nguyên tính phí.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: ECS Fargate awsvpc behind HTTPS ALB (learning example)

Parameters:
  ClusterArn:
    Type: String
  VpcId:
    Type: AWS::EC2::VPC::Id
  PublicSubnetA:
    Type: AWS::EC2::Subnet::Id
  PublicSubnetB:
    Type: AWS::EC2::Subnet::Id
  PrivateAppSubnetA:
    Type: AWS::EC2::Subnet::Id
  PrivateAppSubnetB:
    Type: AWS::EC2::Subnet::Id
  AlbSecurityGroupId:
    Type: AWS::EC2::SecurityGroup::Id
  TaskSecurityGroupId:
    Type: AWS::EC2::SecurityGroup::Id
  CertificateArn:
    Type: String
  ImageUri:
    Type: String
  ExecutionRoleArn:
    Type: String
  TaskRoleArn:
    Type: String

Resources:
  ApiLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      RetentionInDays: 14

  ApiTask:
    Type: AWS::ECS::TaskDefinition
    Properties:
      Family: shop-api
      RequiresCompatibilities: [FARGATE]
      NetworkMode: awsvpc
      Cpu: '256'
      Memory: '512'
      ExecutionRoleArn: !Ref ExecutionRoleArn
      TaskRoleArn: !Ref TaskRoleArn
      ContainerDefinitions:
        - Name: api
          Essential: true
          Image: !Ref ImageUri
          PortMappings:
            - ContainerPort: 8080
              Protocol: tcp
          LogConfiguration:
            LogDriver: awslogs
            Options:
              awslogs-group: !Ref ApiLogGroup
              awslogs-region: !Ref AWS::Region
              awslogs-stream-prefix: api

  ApiTargetGroup:
    Type: AWS::ElasticLoadBalancingV2::TargetGroup
    Properties:
      VpcId: !Ref VpcId
      TargetType: ip
      Port: 8080
      Protocol: HTTP
      HealthCheckProtocol: HTTP
      HealthCheckPort: traffic-port
      HealthCheckPath: /health/ready
      Matcher:
        HttpCode: '200'

  PublicAlb:
    Type: AWS::ElasticLoadBalancingV2::LoadBalancer
    Properties:
      Type: application
      Scheme: internet-facing
      Subnets:
        - !Ref PublicSubnetA
        - !Ref PublicSubnetB
      SecurityGroups:
        - !Ref AlbSecurityGroupId

  HttpsListener:
    Type: AWS::ElasticLoadBalancingV2::Listener
    Properties:
      LoadBalancerArn: !Ref PublicAlb
      Port: 443
      Protocol: HTTPS
      Certificates:
        - CertificateArn: !Ref CertificateArn
      DefaultActions:
        - Type: forward
          TargetGroupArn: !Ref ApiTargetGroup

  ApiService:
    Type: AWS::ECS::Service
    DependsOn: HttpsListener
    Properties:
      Cluster: !Ref ClusterArn
      ServiceName: shop-api-service
      TaskDefinition: !Ref ApiTask
      LaunchType: FARGATE
      DesiredCount: 4
      HealthCheckGracePeriodSeconds: 60
      DeploymentConfiguration:
        DeploymentCircuitBreaker:
          Enable: true
          Rollback: true
      NetworkConfiguration:
        AwsvpcConfiguration:
          AssignPublicIp: DISABLED
          Subnets:
            - !Ref PrivateAppSubnetA
            - !Ref PrivateAppSubnetB
          SecurityGroups:
            - !Ref TaskSecurityGroupId
      LoadBalancers:
        - TargetGroupArn: !Ref ApiTargetGroup
          ContainerName: api
          ContainerPort: 8080
~~~

### 8.1. Đọc các điểm kết nối quan trọng

| Chỗ cấu hình | Phải khớp với |
| --- | --- |
| `ApiTask.NetworkMode: awsvpc` | Task dùng ENI/IP trong subnet |
| `ApiTask.ContainerDefinitions.Name: api` | `ApiService.LoadBalancers.ContainerName: api` |
| `PortMappings.ContainerPort: 8080` | `LoadBalancers.ContainerPort: 8080` và ứng dụng listen `:8080` |
| `ApiTargetGroup.TargetType: ip` | ECS task IP trong `awsvpc` |
| `ApiTargetGroup.HealthCheckPath` | HTTP path thực tế trả `200` của container |
| `PublicAlb.Subnets` | Hai **public subnets** thuộc AZ khác nhau |
| `ApiService.Subnets` | Hai **private app subnets** với IP/egress đủ dùng |
| `ApiService.SecurityGroups` | SG cho **task ENI**, cho inbound `8080` từ ALB SG |
| `ExecutionRoleArn` | Quyền pull ECR, ghi log, inject secrets theo nhu cầu |

Đoạn CloudFormation **không tự tạo route table, NAT Gateway hoặc VPC endpoints**, không tạo các SG ingress/egress rules và không bảo đảm image/tag/certificate hợp lệ. Người học phải kiểm tra trước các yếu tố ấy cùng IAM/ACM/CloudWatch Logs. Việc chỉ có `DesiredCount: 4` cũng không bảo đảm sau khi mất một AZ còn đủ xử lý tải thực tế.

### 8.2. Task Definition có thể có nhiều container

Nếu có sidecar, `LoadBalancers.ContainerName` phải trỏ tới container **thật sự nhận request từ ALB**. Task ENI và Security Group áp dụng ở phạm vi task, không riêng một container. Nếu cần hai service có quyền mạng khác nhau, thường nên tách chúng thành **hai ECS services/tasks** thay vì kỳ vọng có SG riêng cho từng container cùng task.

## 9. Kiểm tra hệ thống bằng AWS CLI (chỉ đọc)

Các lệnh sau chỉ xem trạng thái. Thay `my-ecs-cluster`, `shop-api-service`, ARNs/IDs mẫu và Region theo môi trường được cấp quyền. Không cần tạo hoặc sửa tài nguyên.

### 9.1. Xem ECS service, network config và target group

~~~bash
aws ecs describe-services \
  --region ap-southeast-1 \
  --cluster my-ecs-cluster \
  --services shop-api-service \
  --query "services[].{Name:serviceName,Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Network:networkConfiguration,LoadBalancers:loadBalancers,Events:events[0:5].message}" \
  --output json
~~~

Đối chiếu subnet/SG, `assignPublicIp` và `containerPort`/target group ARN. `RunningCount` bằng `DesiredCount` **chưa đủ**: còn phải kiểm tra target health và lỗi ứng dụng.

### 9.2. Xem network mode của task definition

~~~bash
aws ecs describe-task-definition \
  --region ap-southeast-1 \
  --task-definition shop-api \
  --query "taskDefinition.{Family:family,Revision:revision,NetworkMode:networkMode,Ports:containerDefinitions[].portMappings,ExecutionRole:executionRoleArn,TaskRole:taskRoleArn}" \
  --output json
~~~

Nếu task revision đã thay, dùng ARN/revision mà service hiện đang chạy; không chỉ suy ra từ tên family.

### 9.3. Liệt kê tasks và xem ENI/IP

~~~bash
aws ecs list-tasks \
  --region ap-southeast-1 \
  --cluster my-ecs-cluster \
  --service-name shop-api-service

aws ecs describe-tasks \
  --region ap-southeast-1 \
  --cluster my-ecs-cluster \
  --tasks TASK_ARN_1 TASK_ARN_2 \
  --query "tasks[].{Id:taskArn,Status:lastStatus,Desired:desiredStatus,Health:healthStatus,ENI:attachments[].details,Containers:containers[].{Name:name,Status:lastStatus,Reason:reason}}" \
  --output json
~~~

`TASK_ARN_1`/`TASK_ARN_2` là placeholders. Trong `attachments[].details` có thể có `networkInterfaceId`, `privateIPv4Address`, `subnetId` và thông tin liên quan. Trường xuất hiện thay đổi theo platform/launch type, nên không dựa vào mỗi vị trí trong mảng.

### 9.4. Đọc thông tin ENI và Security Group thực tế

~~~bash
aws ec2 describe-network-interfaces \
  --region ap-southeast-1 \
  --network-interface-ids eni-0123456789abcdef0 \
  --query "NetworkInterfaces[].{Id:NetworkInterfaceId,PrivateIP:PrivateIpAddress,Subnet:SubnetId,Groups:Groups[].GroupId,Status:Status}" \
  --output json
~~~

ENI ID ở đây chỉ minh họa; thay bằng ID đọc được từ `describe-tasks`. Đối chiếu IP/SG/subnet với sơ đồ dự kiến và sự thay đổi khi ECS thay task.

### 9.5. Xem target type và health status của ALB

~~~bash
aws elbv2 describe-target-groups \
  --region ap-southeast-1 \
  --target-group-arns TARGET_GROUP_ARN \
  --query "TargetGroups[].{Name:TargetGroupName,Type:TargetType,Protocol:Protocol,Port:Port,HealthPath:HealthCheckPath,Matcher:Matcher}" \
  --output json

aws elbv2 describe-target-health \
  --region ap-southeast-1 \
  --target-group-arn TARGET_GROUP_ARN \
  --query "TargetHealthDescriptions[].{Target:Target,State:TargetHealth.State,Reason:TargetHealth.Reason,Description:TargetHealth.Description}" \
  --output json
~~~

Với `awsvpc`, mong đợi `Type=ip`, còn target IDs là **task private IP**. Nếu target `unhealthy`, đọc `Reason` (ví dụ timeout hoặc response code mismatch) rồi kiểm tra mạng/path/container, không mặc định phải tăng CPU.

### 9.6. Xem log container khi đã bật awslogs

~~~bash
aws logs describe-log-streams \
  --region ap-southeast-1 \
  --log-group-name /ecs/shop-api \
  --order-by LastEventTime \
  --descending \
  --max-items 10
~~~

Ví dụ nhóm log `/ecs/shop-api` không nhất thiết trùng tên CloudFormation ở mục 8 (nơi log group được tự đặt tên). Phải đọc **LogConfiguration** của task definition thực tế để xác định đúng log group, Region và stream prefix trước khi tra.

## 10. Chẩn đoán kết nối: từ DNS đến port của container

Khi người dùng gặp `502`, `503`, `504` hoặc target-group `unhealthy`, hãy xác định tầng lỗi theo thứ tự:

~~~text
Client / DNS
   ↓
ALB public subnet + listener :443 + certificate
   ↓
Listener rule → Target group type ip
   ↓
Task private IP:8080 + task SG + NACL
   ↓
Container listener 0.0.0.0:8080
   ↓
Readiness / business dependencies (RDS, APIs, secrets...)
~~~

### 10.1. Bảng lỗi thường gặp

| Triệu chứng | Khả năng chính | Cách kiểm tra |
| --- | --- | --- |
| **Không tạo được ECS Service sau khi gắn ALB** | Target group không phải `ip`, sai `containerName/containerPort` hoặc listener chưa gắn TG | `describe-task-definition`, `describe-services`, `describe-target-groups` |
| **Target.Timeout** | SG/NACL chặn TCP 8080, app chưa listen hoặc request quá lâu | Kiểm tra inbound task từ ALB SG, port/container logs, health check timeout |
| **Target.ResponseCodeMismatch** | Endpoint health trả `404`, `301`, `401`, `500` hoặc code khác matcher | Gọi đúng `/health/ready`, xem logs và matcher |
| **Target.ConnectionError** | Không có listener ở task IP/port, task đang restart hoặc kết nối bị reset | Bind address `0.0.0.0`, container status, ECS events |
| **ECS task RUNNING nhưng ALB 503** | Không có target healthy/target registration đúng, ALB listener/TG sai | `describe-target-health` và listener rules |
| **CannotPullContainerError** | Image/tag ECR sai, execution role thiếu quyền, không có NAT/endpoint | ECR URI, role, ECR API/DKR + S3 connectivity |
| **ResourceInitializationError** | Không truy cập được secrets/logging/image metadata hoặc config khởi tạo | Task stopped reason, endpoints/DNS/KMS/IAM, awslogs config |
| **Task mới bị dừng liên tục khi deploy** | Container crash, thiếu memory, health check fail, grace quá ngắn | Stopped reason, logs, target health, rollout events |
| **App gọi DB bị timeout** | Task SG egress, DB SG inbound, route/NACL hoặc DNS | Kiểm tra `sg-api → sg-db:5432` và DB connection pool |
| **App gọi AWS SDK bị AccessDenied** | Task role thiếu quyền hoặc endpoint/bucket policy chặn | Task role, IAM policies, CloudTrail và policy của tài nguyên |
| **Client HTTPS không vào ALB** | Route DNS/IGW, SG ALB inbound 443, listener/certificate | Truy vấn DNS, `describe-load-balancers`, ALB logs |

**Đừng “sửa thử” bằng cách mở `0.0.0.0/0` cho task SG**: nó che nguyên nhân và tăng rủi ro. Hãy xác định chính xác nguồn IP/SG, port và trạng thái target.

### 10.2. Phân biệt lỗi ALB 502, 503 và 504

- **502 Bad Gateway** có thể do kết nối backend lỗi, reset hoặc response sai định dạng.
- **503 Service Unavailable** thường liên quan việc ALB không có target khả dụng/được đăng ký hoặc không thể phục vụ yêu cầu theo routing.
- **504 Gateway Timeout** có thể do timeout khi kết nối/đợi response từ target.

Không coi mã HTTP là chẩn đoán đầy đủ; đọc **ALB access logs**, metrics và `TargetHealth.Reason` cùng logs ứng dụng. Khi tất cả registered targets đều unhealthy, phải nhớ cơ chế **fail-open** của ALB có thể khiến traffic vẫn tới những target đó.

### 10.3. Kiểm tra từ trong task

Nếu môi trường cho phép **ECS Exec** và có cấu hình IAM/SSM phù hợp, người vận hành có thể kiểm tra listener/DNS trong container thay vì mở SSH tới host:

~~~bash
# Chỉ minh họa thao tác khi ECS Exec đã được bật và cấp phép
aws ecs execute-command \
  --region ap-southeast-1 \
  --cluster my-ecs-cluster \
  --task TASK_ARN \
  --container api \
  --interactive \
  --command "/bin/sh"
~~~

ECS Exec **không phải** tính năng tự luôn bật. Nó cần điều kiện platform, permissions và SSM communication, có thể chưa có shell trong image tối giản. Việc mở exec vào production là hành động đặc quyền; nên có phê duyệt/logging thích hợp. Nếu image không có `curl`/`sh`, dùng logs, metrics hoặc công cụ debug được cho phép thay vì thay đổi image production tùy tiện.

## 11. Nhiều AZ, deployment và khả năng chịu lỗi

### 11.1. ECS Service ở hai AZ chưa tự tạo high availability

Giả sử service có **4 tasks**, hai tasks ở mỗi AZ:

~~~text
AZ A: task 1, task 2
AZ B: task 3, task 4
ALB enabled ở A và B, target group có 4 private IP
~~~

Khi AZ A mất, B còn hai tasks. Nếu ứng dụng chỉ chịu tối đa `100 req/s` mỗi task theo benchmark an toàn và tải đỉnh là `350 req/s`, B chỉ chịu được `200 req/s`, **không đạt yêu cầu dù còn hai tasks chạy**.

Muốn giữ tải đỉnh `350 req/s` khi mất một AZ mà mỗi task an toàn ở `100 req/s`:

~~~text
Số task cần còn sống = ceil(350 / 100) = 4
Nếu chia đều hai AZ và mất toàn bộ một AZ:
  Dự phòng tối thiểu theo giả định = 4 task / AZ
  Tổng khi cả hai AZ khỏe = 8 task
~~~

Đây là mô hình capacity giả định. Thực tế còn phụ thuộc CPU, memory, độ trễ RDS, connection limit, quota Fargate/EC2, tốc độ scale-out và hành vi của ALB. **Auto Scaling sau sự cố cần thời gian**, không phải bảo đảm tức thời.

### 11.2. Deployment overlap và health

Khi rollout phiên bản mới, ECS có thể khởi tạo tasks mới và giữ tasks cũ trong một khoảng thời gian tùy deployment configuration. Việc đó cần:

- Đủ **IP trong subnet** để có task ENI mới.
- Đủ CPU/memory/quota và các image/secrets có sẵn.
- Ứng dụng mới healthy trước khi thay hết những target cũ.
- Readiness path và `healthCheckGracePeriodSeconds` phù hợp.
- Dừng task cũ theo graceful shutdown, cấu hình target deregistration delay và xử lý request đang chạy.
- Rollback khi bản mới không đạt trạng thái cần thiết.

Một deployment thành công về mặt infrastructure chưa chắc tương đương nghiệp vụ thành công; nên đo `HTTPCode_Target_5XX_Count`, latency và tỉ lệ giao dịch ngay sau rollout.

### 11.3. Dữ liệu trạng thái và session

Tránh lưu session hoặc dữ liệu đơn hàng chỉ trong bộ nhớ một task. Khi ECS thay task và đổi private IP, dữ liệu nội bộ có thể biến mất. Với ứng dụng cần HA:

- Lưu dữ liệu giao dịch ở RDS/DynamoDB và xử lý retry/idempotency.
- Lưu session theo cơ chế phù hợp như token/stateless hoặc session store có khả năng chịu lỗi.
- Lưu file/user uploads trên S3/EFS hoặc dịch vụ phù hợp, không dựa vào writable layer tạm thời của container.
- Thiết kế shutdown và job handling để task bị scale-in không làm mất công việc đang xử lý.

## 12. Một VPC, nhiều ECS services: phân tách traffic

Ví dụ hệ thống thương mại điện tử có hai ECS services:

- **Catalog API**: container port `8080`, path `/catalog/*`, chỉ đọc dữ liệu sản phẩm.
- **Checkout API**: container port `9090`, path `/checkout/*`, đọc/ghi dữ liệu đơn hàng.

Có thể dùng một ALB với hai **target groups riêng**, mỗi group có `TargetType=ip` và health check path riêng:

| Thành phần | Catalog | Checkout |
| --- | --- | --- |
| ECS service | `catalog-service` | `checkout-service` |
| Task SG | `sg-catalog` | `sg-checkout` |
| Container port | `8080` | `9090` |
| Target group | `tg-catalog-ip` | `tg-checkout-ip` |
| Listener rule | `/catalog/*` | `/checkout/*` |
| Health path | `/catalog/health` | `/checkout/health` |
| DB access | Chỉ đọc theo role/network | Đọc/ghi theo role/network |

**Security Group của ALB** cần outbound tới cả hai SG trên đúng port. **Catalog task SG** chỉ cho inbound 8080 từ ALB SG; **Checkout task SG** chỉ cho inbound 9090 từ ALB SG. Phân quyền database và AWS API nên khác nhau ở task role.

Nếu Checkout gọi Catalog **từ backend**, không tự định tuyến thông qua public ALB nếu yêu cầu riêng tư/độ trễ/chi phí không phù hợp. Có thể cân nhắc nội bộ qua **internal ALB**, ECS Service Connect hoặc cơ chế service discovery được hỗ trợ; mô hình định tuyến và SG phải được thiết kế riêng cho traffic service-to-service.

## 13. Giám sát, bảo mật và chi phí

### 13.1. Metrics cần theo dõi

| Lớp | Metrics / dấu hiệu |
| --- | --- |
| **ALB** | `RequestCount`, `HTTPCode_ELB_5XX_Count`, `HTTPCode_Target_5XX_Count`, `TargetResponseTime` |
| **Target group** | `HealthyHostCount`, `UnHealthyHostCount`, `TargetConnectionErrorCount` |
| **ECS Service** | Desired/Running/Pending task counts, service events, deployment failures |
| **Containers** | CPU/memory utilization, exit code, OOM, app logs và latency |
| **Network** | VPC Flow Logs, NACL/SG REJECTs (cần kết hợp cấu hình), NAT traffic và endpoint errors |
| **Data dependencies** | RDS connections/latency, queue backlog, cache hits, DB errors |
| **Chi phí** | Fargate vCPU/GB thời gian, ALB capacity, NAT hours/bytes, PrivateLink endpoints, logs/metrics, data transfer |

`HealthyHostCount > 0` không phải dấu hiệu dư sức chịu một AZ lỗi. Cần cảnh báo theo **mức tối thiểu để đạt SLO**, không chỉ theo số target đang sống.

### 13.2. CloudTrail, logs và quyền quản trị

Để audit deployment và thay đổi hạ tầng:

- **CloudTrail** cho ECS/ELB/EC2/IAM control-plane operations theo cấu hình có hiệu lực.
- **CloudWatch Logs** cho stdout/stderr của container khi `awslogs` được bật và execution role/đường mạng hoạt động.
- **ALB access logs** (nếu bật) để điều tra request, trạng thái backend, latency.
- **VPC Flow Logs** cho metadata network connections; bản ghi `REJECT` **không tự xác định chính xác rule nào chặn**.
- Quản lý IAM role riêng cho CI/CD, task execution và task application; hạn chế `iam:PassRole`, `ecs:UpdateService` và quyền sửa SG/ALB.

Không ghi secret/token hoặc thông tin khách hàng nhạy cảm vào log. Thiết lập retention và phân quyền đọc logs theo yêu cầu.

### 13.3. Cost trade-offs

- **Fargate** giảm công quản lý EC2 host, nhưng trả phí cho tài nguyên task theo cấu hình/usage, cân nhắc Savings Plans và tải thực tế.
- **ALB** có phí theo thời gian và Load Balancer Capacity Units; chia sẻ một ALB có thể tiết kiệm hơn một ALB cho mỗi service, nhưng tăng nhu cầu quản lý listener rules và blast radius.
- **NAT theo AZ** nâng tính sẵn sàng nhưng thêm phí giờ và data processing; **interface VPC endpoints** có phí theo ENI/AZ và bytes xử lý.
- **CloudWatch Logs** và Container Insights có phí ingest/retention/metrics; cấu hình quan sát có chủ đích.
- **Dữ liệu liên AZ** có thể phát sinh phí theo luồng cụ thể; vẽ đường ALB/task/DB/endpoint trước khi ước tính.

Không chọn một thiết kế mạng chỉ bằng cách so số lượng NAT hoặc số ALB. **Tổng chi phí phải đi cùng RTO/SLO, bảo mật và năng lực vận hành**.

## 14. Quy trình triển khai và kiểm chứng production

1. **Chuẩn bị network:** VPC, public/private subnets tối thiểu hai AZ, IGW, private egress qua NAT/endpoint theo nhu cầu, DNS và IP capacity.
2. **Chuẩn bị Security Groups:** ALB inbound 443, ALB outbound port ứng dụng; task inbound chỉ từ ALB SG, task outbound đến DB/AWS endpoints phù hợp.
3. **Chuẩn bị image & IAM:** image trong registry, task execution role cho pull/log/secrets; task role theo AWS APIs mà app cần.
4. **Tạo Task Definition:** `networkMode=awsvpc`, container name/port đúng, resource requirements, log configuration, health/stop behavior phù hợp.
5. **Tạo ALB và target group:** ALB enabled ở nhiều AZ, HTTPS listener/chứng chỉ, target group **`ip`**, health check chính xác.
6. **Tạo ECS Service:** chọn Fargate hoặc EC2 launch type/capacity provider phù hợp, private subnets, task SG, `assignPublicIp=DISABLED` khi cần, gắn đúng containerName/containerPort vào target group.
7. **Kiểm tra steady state:** ECS desired/running, target group healthy, HTTP request hoạt động qua ALB/DNS và DB/API dependency đúng quyền.
8. **Kiểm thử rollout/rollback:** triển khai một bản giả lập, quan sát task mới đăng ký và task cũ draining, xác minh request không bị gián đoạn quá SLO.
9. **Kiểm tra khi AZ gặp lỗi:** mô phỏng trong staging và xem capacity/egress còn lại, không gây sự cố cho production ngoài kế hoạch.
10. **Theo dõi sau triển khai:** metrics, logs, alerts, chi phí, audit và kế hoạch xử lý security incidents.

### 14.1. Checklist trước khi đưa vào vận hành

- [ ] Task Definition có `networkMode=awsvpc`; ECS Service dùng đúng subnet/SG, đúng launch type.
- [ ] Target group có **`TargetType=ip`**, liên kết listener và container name/port đúng.
- [ ] Container lắng nghe địa chỉ có thể truy cập từ task ENI, không chỉ `127.0.0.1`.
- [ ] ALB ở các public subnets được cấu hình route/IGW đúng; task private không có public IP không cần thiết.
- [ ] SG ALB ↔ SG task chỉ mở cổng ứng dụng/health; SG task ↔ DB/API đúng nguồn và đích.
- [ ] ECR, S3, CloudWatch Logs, Secrets Manager và các dependency khác có IAM + NAT/VPC endpoint hoạt động.
- [ ] Readiness path trả đúng mã HTTP, grace period và deregistration delay phù hợp.
- [ ] ECS tasks có mặt ở nhiều AZ và capacity khi mất một AZ đã được tính/kiểm thử.
- [ ] Log/metrics/traces, cảnh báo triển khai và rollback đã bật và có người tiếp nhận.
- [ ] Chi phí NAT, endpoint, Fargate, ALB, logging và cross-AZ traffic được dự toán.

## 15. Bài tập củng cố

### Bài tập 1 — Chọn target type

Một ECS Fargate service có task IP `10.30.10.25` và container port `8080`, nhưng target group được tạo với `TargetType=instance`. Vì sao không phù hợp? Phải đổi gì?

**Gợi ý:** Fargate dùng `awsvpc` và task ENI/private IP, không phải target EC2 container instance. Dùng **target group type `ip`** và cấu hình ECS service gắn đúng container `api`/`8080`.

### Bài tập 2 — Lỗi Security Group

ALB listener HTTPS 443 đã hoạt động. Task SG chỉ có inbound `TCP 8080` từ `10.99.0.0/16`, trong khi ALB nằm tại `10.30.0.0/16`. Target group báo timeout.

**Gợi ý:** inbound task SG không cho phép nguồn ALB thực tế. Giới hạn đúng bằng **source `sg-alb`** (nếu hỗ trợ tham chiếu SG) hoặc CIDR nguồn phù hợp. Kiểm tra ALB SG outbound 8080 và NACL nếu có.

### Bài tập 3 — App khỏe trong container, ALB unhealthy

Task ở trạng thái `RUNNING`; app chỉ có `/health/ready` trả 200, còn GET `/` trả 404. Target group được cấu hình path mặc định `/` và matcher 200.

**Gợi ý:** ALB health check đang gọi sai path. Chọn `/health/ready`, sau đó xem lại health status, network và behavior trong rollout.

### Bài tập 4 — Tại sao task không pull được image?

Task Fargate đặt trong private subnet, `assignPublicIp=DISABLED`, subnet không có NAT. Team tạo target group đúng và mở SG ALB → task 8080 nhưng task dừng với `CannotPullContainerError`.

**Gợi ý:** lỗi xảy ra **trước khi container phục vụ traffic**. Kiểm tra đường tới ECR/registry và S3 image layers, các VPC endpoints cần thiết, endpoint SG, DNS và task **execution role**. Target group không giải quyết image pull.

### Bài tập 5 — Mất một AZ

Service có bốn tasks, hai tasks/AZ; tải đỉnh 350 req/s, một task phục vụ an toàn 100 req/s. Khi AZ A mất, B còn hai tasks. Hệ thống đáp ứng tải đỉnh không?

**Gợi ý:** không, B chỉ có năng lực khoảng 200 req/s. Muốn tối thiểu 350 req/s khi mất một AZ, cần khoảng **bốn tasks còn sống**, tương đương bốn tasks/AZ trong mô hình chia đều đơn giản, chưa tính margin và dependency capacity.

### Bài tập 6 — Hai container cùng task

Task có container `api` và `metrics`. `metrics` lắng nghe `127.0.0.1:4317`; `api` muốn gửi telemetry tới `localhost:4317`. Có cần mở SG inbound 4317 từ ALB không?

**Gợi ý:** không, các containers **trong cùng task dùng chung network namespace** khi `awsvpc`; `localhost` có thể dùng nội bộ. ALB chỉ cần vào `api:8080`; SG không cần công khai cổng sidecar.

### Bài tập 7 — Thiết kế nhiều services

Một ALB phải phân phối `/catalog/*` đến container port 8080 và `/checkout/*` đến port 9090. Hãy vẽ listener rules, hai target groups kiểu `ip` và hai ECS services có task SG tách biệt. Kiểm tra trường `containerName/containerPort` của từng service.

**Gợi ý:** không dùng một target group chứa lẫn hai backend có health endpoint và quyền khác nhau. Mỗi ECS service có target group riêng; listener rules dựa trên path/host chọn đúng group.

## 16. Ghi nhớ

- **`awsvpc`** trao cho ECS task một **network identity trong VPC**: task ENI, private IP và Security Group. Với Fargate, đây là network mode bắt buộc.
- Với ECS Service dùng `awsvpc`, ALB phải dùng **target group type `ip`**, trỏ tới **private task IP + container port**. Listener của ALB có thể là HTTPS 443, còn container lắng nghe HTTP 8080.
- **SG ALB** cho phép client vào listener và ALB đi tới task port; **SG task** chỉ cho phép inbound từ ALB SG, đồng thời phải cho các luồng outbound thực sự cần. NACL tùy chỉnh vẫn cần hai chiều vì stateless.
- **Task RUNNING không đồng nghĩa ALB healthy**. Health path, HTTP status, bind address, IAM/image pull, network egress và dependency phải đồng thời đúng.
- Thiết kế production cần **nhiều AZ, capacity dự phòng, graceful shutdown, logging/metrics, IAM least privilege và kiểm soát chi phí**. Đừng sửa sự cố kết nối bằng cách mở rộng mọi Security Group thay vì tìm đúng nguyên nhân.

### Tài liệu AWS chính thức

- [Task networking with the awsvpc network mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html) — task ENI, networking và các giới hạn.
- [Amazon ECS task networking for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html) — subnet, public IP, task ENI và platform versions.
- [Use an Application Load Balancer for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/alb.html) — ALB và target groups cho ECS.
- [Amazon ECS service definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_definition_parameters.html) — network configuration, load balancer và health check grace period.
- [Amazon ECS task definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html) — port mappings, roles và containers.
- [Security group rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html) và [Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html) — kiểm soát mạng stateful/stateless.
- [ALB target groups](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-target-groups.html) và [Target group health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html) — target type và health.
- [Amazon ECR VPC endpoints](https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html) — private image pulls, S3 và endpoint dependencies.
- [VPC endpoints for Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html) — ECS APIs, connectivity và platform differences.
- [Task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) và [Task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) — phân biệt quyền ECS runtime và ứng dụng.
- [Amazon ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html) — truy cập để debug container khi đã cấu hình quyền.
- [Troubleshoot ECS service load balancers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/troubleshoot-service-load-balancers.html) — phân tích target health và lỗi kết nối.
