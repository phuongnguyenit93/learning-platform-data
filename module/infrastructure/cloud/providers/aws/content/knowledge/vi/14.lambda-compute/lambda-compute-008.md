# Kết nối Lambda với VPC và dịch vụ riêng tư

Trong AWS, một **Lambda function** có thể nhận sự kiện từ API Gateway, EventBridge hoặc SQS rồi xử lý dữ liệu mà không cần quản lý máy chủ. Nhưng khi nghiệp vụ cần truy vấn một **Amazon RDS database private**, gọi **Amazon ElastiCache** hoặc truy cập **Amazon EFS**, function cần một đường mạng tới các tài nguyên đang nằm trong **Amazon Virtual Private Cloud (VPC)**. Việc đó khác với truy cập S3 hoặc DynamoDB qua AWS service endpoints, và càng khác với cách một client bên trong VPC gọi **Lambda Invoke API**.

Nếu chỉ chọn vài subnet rồi nhấn Save mà chưa hiểu routing, security groups và VPC endpoints, ứng dụng có thể gặp timeout khi kết nối database, không lấy được Secrets Manager secret, hoặc mất truy cập tới API bên ngoài. Bài này xây dựng mô hình mạng và bảo mật để tránh các lỗi đó.

Bài thuộc chương **Điện toán Lambda** của mô-đun **CLOUD_PROVIDERS_AWS**, kết nối kiến thức Region/AZ, IAM, VPC, EC2, RDS, EFS, S3, mạng tích hợp và serverless. Mục tiêu là thiết kế Lambda có kết nối riêng tư, quyền tối thiểu, khả năng giám sát, phục hồi và kiểm soát chi phí.

> **Ý chính:** Lambda **không chuyển hẳn vào subnet của bạn** khi được gắn VPC. Nó vẫn chạy trong hạ tầng do Lambda quản lý và dùng **Hyperplane Elastic Network Interface (ENI)** để kết nối tới tài nguyên trong VPC của bạn. Gắn VPC ảnh hưởng tới **đường đi outbound từ code**; nó không biến Lambda thành máy chủ có địa chỉ private IP để client kết nối trực tiếp.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Lambda-managed VPC**, **customer VPC** và **Hyperplane ENI**.
2. Lựa chọn private subnets ở nhiều Availability Zones, route tables, security groups và NACL cho Lambda.
3. Giải thích vì sao **public subnet không tự cấp Internet access** cho Lambda và khi nào cần NAT Gateway.
4. Chọn **Gateway VPC Endpoint** cho S3/DynamoDB và **Interface Endpoint (AWS PrivateLink)** cho các AWS APIs như Secrets Manager, STS hoặc Lambda Invoke API.
5. Phân biệt **Lambda gọi tài nguyên trong VPC** với **client trong VPC gọi Lambda**.
6. Tạo thiết kế Lambda → RDS/RDS Proxy, ElastiCache hoặc EFS có tính tới scale, authentication và kết nối.
7. Xác định IAM execution role cần quyền ENI, quyền truy cập dịch vụ, đồng thời tránh mở rộng quyền code quá mức.
8. Đọc cấu hình bằng Console/CLI, kiểm tra endpoint/routing/SG và troubleshoot timeout, DNS, `AccessDenied`.
9. Áp dụng Java AWS SDK v2 để truy cập dịch vụ private mà không hardcode credentials.
10. Cân nhắc IPv6, concurrency, độ sẵn sàng theo AZ và chi phí NAT/PrivateLink/RDS Proxy.

## 2. Mô hình đúng: Lambda vẫn ở hạ tầng Lambda quản lý

Theo mô hình thực thi Lambda thông thường, AWS chạy các execution environments trong **Lambda-managed VPC** mà khách hàng không trực tiếp nhìn thấy hoặc quản trị. Nếu function cần nói chuyện với database private trong VPC của bạn, bạn cấu hình **VpcConfig** gồm subnet IDs và security group IDs của **customer VPC**.

Lambda tạo và quản lý **Hyperplane ENIs** cho những tổ hợp subnet và security groups đó, để lưu lượng từ function đi vào địa chỉ private của VPC. Đây là một **đường kết nối mạng được quản lý**, không phải một EC2 network interface được gắn trực tiếp vào từng container theo cách thủ công.

~~~mermaid
flowchart LR
    T["API Gateway / EventBridge / SQS event"] --> L["AWS Lambda execution environment<br/>(Lambda-managed VPC)"]
    L --> H["Lambda Hyperplane ENI"]
    subgraph V["Customer VPC · 10.20.0.0/16"]
      S["Private subnets<br/>AZ-a, AZ-b"]
      DB["RDS / RDS Proxy<br/>private endpoint"]
      EC["ElastiCache / private API"]
      EFS["EFS mount targets"]
      EP["S3 Gateway / Interface VPC endpoints"]
      NAT["NAT Gateway<br/>khi cần IPv4 Internet"]
      H --> S
      S --> DB
      S --> EC
      S --> EFS
      S --> EP
      S --> NAT
    end
~~~

### 2.1. Bốn điều cần nhớ

- **Function vẫn có thể được invoke từ bên ngoài VPC** qua cơ chế trigger được cấp phép; VPC attachment không tự ngăn API Gateway/EventBridge/SQS kích hoạt function.
- **Function không có listener TCP/HTTP trực tiếp trên Hyperplane ENI** để hệ thống khác gửi request tới như một EC2 server.
- **Traffic do code khởi tạo tới tài nguyên private** tuân theo route tables, SG/NACL và DNS của những subnets/đích liên quan.
- **Không gắn VPC nếu không cần**: một function chỉ dùng S3/DynamoDB công khai qua AWS APIs có thể hoạt động tốt không có VPC attachment. Việc thêm VPC khi không cần làm phức tạp networking và có thể phát sinh NAT/endpoint fees.

### 2.2. Phân biệt các lớp khi bị lỗi

| Lớp | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Invoke** | Có ai được phép kích hoạt function không? | API Gateway, SQS event source mapping, `lambda:InvokeFunction` |
| **VPC network** | Từ function có đường IP/DNS tới backend không? | Subnet route, Hyperplane ENI, SG, VPC endpoint |
| **AWS IAM** | Execution role có quyền gọi AWS API không? | `secretsmanager:GetSecretValue`, `s3:GetObject` |
| **Application** | Backend có lắng nghe, TLS/auth có đúng không? | RDS port 5432, JDBC credentials, TLS certificate |
| **Operations** | Có quá tải connection hoặc hết timeout không? | Lambda concurrency, RDS max_connections, NAT capacity |

Để xử lý sự cố nhanh, xác định **thất bại ở lớp nào**, thay vì thêm một rule `0.0.0.0/0` hoặc IAM `*` theo cảm tính.

## 3. Hyperplane ENI: hoạt động, chia sẻ và vòng đời

Khi gắn một Lambda function vào một **tổ hợp subnet IDs và security group IDs** chưa được Lambda sử dụng, AWS tạo Hyperplane ENI. Những functions trong **cùng account** có tổ hợp network configuration giống nhau có thể tái sử dụng ENI thay vì tạo một ENI mới cho mỗi function/invocation.

Theo tài liệu AWS hiện hành, một Hyperplane ENI hỗ trợ tối đa khoảng **65.000 connections/ports**; Lambda có thể tự bổ sung ENIs khi nhu cầu kết nối tăng vượt khả năng của ENI hiện có. Đây **không phải** quota 65.000 Lambda invocations hay bảo đảm database phục vụ được 65.000 SQL connections.

### 3.1. Cấu hình VPC lần đầu có thể có trạng thái `Pending`

- Khi function mới cần Hyperplane ENI chưa sẵn có, nó có thể ở trạng thái **`Pending`** cho tới khi ENI được tạo.
- Function mới chưa được invoke cho tới khi trạng thái **`Active`**.
- Với function đã chạy và được đổi VPC config, có thể còn các phiên bản cũ vẫn invoke được trong khi một số thao tác update/publish bị chặn tạm thời.
- Việc tạo ENI có thể mất vài phút; **đây là provisioning**, không phải một lỗi cold start Java của từng invocation.

### 3.2. Function ít dùng có thể chuyển `Inactive`

Theo AWS, nếu function không được sử dụng trong **14 ngày**, Lambda có thể thu hồi Hyperplane ENI không dùng và đặt function thành `Inactive`. Lần invoke đầu tiên tiếp theo có thể thất bại, sau đó Lambda chuyển qua `Pending` để cấp lại network resource. Hệ thống không nên dựa vào **sự tồn tại vĩnh viễn** của ENI.

Khi tháo VPC config hoặc xóa function, quá trình dọn ENI có thể tiếp tục một khoảng thời gian; nếu role dùng cho việc dọn ENI bị xóa quá sớm, ENI có thể mồ côi. Không tự xóa ENI còn do Lambda quản lý hay đang được function/version khác dùng.

### 3.3. Tối ưu tổ hợp subnet/SG

Tạo SG riêng cho mỗi function chỉ vì muốn tách tên có thể làm tăng số tổ hợp network. Nên tái sử dụng SG khi **cùng ranh giới quyền** và traffic cần giống nhau; ngược lại, không gộp mọi function chung SG nếu điều đó mở quyền vượt yêu cầu. Đánh đổi giữa security segmentation, reuse ENI và vận hành phải được xem xét ở mức ứng dụng.

## 4. Chọn VPC, subnet và Availability Zone

### 4.1. Một kiến trúc hai AZ

Ví dụ:

| Thành phần | Giá trị minh họa |
|---|---|
| VPC | `vpc-app`, CIDR `10.20.0.0/16` |
| Private subnet A | `10.20.10.0/24` ở `ap-southeast-1a` |
| Private subnet B | `10.20.20.0/24` ở `ap-southeast-1b` |
| Lambda SG | `sg-lambda-orders`, egress theo nhu cầu |
| RDS/Proxy SG | `sg-db-orders`, inbound TCP 5432 từ Lambda SG |
| S3 Gateway Endpoint | Gắn vào route tables của hai private subnets |
| Secrets Manager Interface Endpoint | ENIs + SG cho TCP 443 và private DNS |
| NAT Gateway | Tùy chọn, khi cần IPv4 Internet ngoài những endpoints đã bố trí |

IDs/địa chỉ chỉ là ví dụ. Với production, chọn **ít nhất hai private subnets ở các AZ khác nhau** nếu tài nguyên đích/Region/kiến trúc hỗ trợ. Cần đủ IPv4 address space, network routes, NACL và target services sẵn sàng ở các AZ đó.

### 4.2. `SubnetIds` phải cùng một VPC

Một Lambda VpcConfig tham chiếu subnets và security groups thuộc **cùng VPC**. Không dùng một subnet ở VPC A và một subnet ở VPC B làm chung VpcConfig. Nếu backend ở VPC B, cần kết nối liên VPC (peering, Transit Gateway hoặc service-specific connectivity) hoặc thiết kế share VPC/PrivateLink phù hợp.

### 4.3. Route table là cấu hình của subnet, không phải của Lambda code

Lưu lượng tới private CIDR **trong cùng VPC** dùng route `local` có sẵn. Các tuyến ra ngoài VPC được cấu hình trên route tables gắn với subnets đã chọn:

| Destination | Target | Tác dụng |
|---|---|---|
| `10.20.0.0/16` | `local` | Giao tiếp với tài nguyên nội bộ VPC |
| `0.0.0.0/0` | `nat-...` | IPv4 Internet egress từ private subnet khi cần |
| S3 prefix list | `vpce-...` loại Gateway | Gọi S3 qua gateway endpoint |
| `::/0` | Egress-only Internet Gateway | IPv6 outbound nếu cấu hình dual-stack phù hợp |
| Peer CIDR | `pcx-...` hoặc TGW attachment | Nối tài nguyên ở VPC khác theo kiến trúc định tuyến |

Nếu một subnet dùng **custom route table**, chỉnh main route table sẽ không giúp subnet đó. Hãy đọc subnet–route-table associations và route ở **chiều đi lẫn chiều về**.

### 4.4. Tính sẵn sàng theo AZ

Lambda chọn network capacity dựa trên subnets đã gắn. Chọn subnets ở nhiều AZ giúp giảm single-AZ dependency; nhưng nếu cả hai subnets đều dùng một NAT Gateway ở AZ-a, hoặc database chỉ có một endpoint kém sẵn sàng, toàn hệ thống vẫn có điểm lỗi. Thiết kế cả **Lambda → network egress → endpoint → database**, không chỉ chọn hai AZ cho Lambda.

## 5. Security Groups, NACL và DNS

### 5.1. Security Group stateful

Để Lambda gọi RDS PostgreSQL/Proxy private endpoint qua TCP 5432:

- **Lambda SG:** cho phép **egress TCP 5432** tới SG của RDS/Proxy hoặc CIDR được duyệt.
- **RDS/Proxy SG:** cho phép **inbound TCP 5432** từ **Lambda SG** (cùng VPC hoặc tham chiếu SG peer được hỗ trợ).
- Security groups là **stateful**: response traffic của một connection hợp lệ thường được cho phép tự động.

Không cần mở inbound `0.0.0.0/0` trên Lambda SG để AWS API Gateway/SQS invoke function. Invoke không phải TCP connection trực tiếp tới Lambda Hyperplane ENI.

### 5.2. Một bảng minh họa

| Security Group | Inbound | Outbound |
|---|---|---|
| `sg-lambda-orders` | Không cần rule inbound cho chức năng gọi RDS | TCP 5432 tới `sg-db-orders`; TCP 443 tới endpoint SG |
| `sg-db-orders` | TCP 5432 từ `sg-lambda-orders` | Theo nhu cầu DB/Proxy, thường không phải mở rộng không kiểm soát |
| `sg-vpce-secrets` | TCP 443 từ `sg-lambda-orders` | Phản hồi stateful theo SG; kiểm tra chính sách tương ứng |

Nếu một interface endpoint (Secrets Manager, STS...) có SG inbound chỉ cho một CIDR khác, Lambda sẽ timeout khi gọi API dù IAM role đã đúng.

### 5.3. Network ACL stateless và ephemeral ports

NACL áp dụng cho subnets và **stateless**; khi tạo restrictive NACL, phải cho phép chiều trả về trên **ephemeral ports** và đúng hướng inbound/outbound. Tài liệu troubleshooting Lambda đặc biệt lưu ý Hyperplane ENI sử dụng các source ports **1024–65535** cho traffic TCP/UDP; NACL quá hẹp có thể gây lỗi intermittent.

Đừng dùng NACL để thay Security Group. Với hầu hết mô hình, SG là lớp điều khiển nguồn/đích chính; NACL là lớp bổ sung khi chính sách mạng yêu cầu.

### 5.4. DNS trong VPC

Lambda code thường kết nối qua hostname như `orders-proxy.proxy-abc.ap-southeast-1.rds.amazonaws.com` hoặc `secretsmanager.ap-southeast-1.amazonaws.com`. Kiểm tra:

1. VPC DNS attributes `enableDnsSupport` và `enableDnsHostnames`.
2. Route 53 Resolver, private hosted zones và các forwarding rules.
3. Private DNS của interface endpoints.
4. DNS trả IP có thể tới được qua route table/SG/NACL.
5. TLS hostname verification khớp hostname thực, đặc biệt với RDS Proxy/database.

Một function gặp `UnknownHostException` là lỗi DNS; `SocketTimeoutException` thường gợi ý mạng/service, còn `AccessDeniedException` từ AWS SDK là IAM/resource policy.

## 6. VPC attachment có làm mất Internet access không?

**Có thể, nếu không thiết kế egress.** Theo mặc định, function không gắn customer VPC có đường ra AWS public service APIs và Internet từ môi trường do Lambda quản lý. Sau khi gắn customer VPC, lưu lượng **outbound do code tạo** đi qua networking của VPC đó; muốn đi Internet phải cấp đường thích hợp.

### 6.1. Public subnet không tự giúp Lambda ra Internet

Nhiều người gắn Lambda vào subnet có route `0.0.0.0/0 → Internet Gateway` rồi chờ nó truy cập HTTPS bên ngoài. Nhưng **Lambda không nhận public IPv4 address chỉ vì subnet đó là public**. Internet Gateway không chuyển tiếp outbound IPv4 từ ENI có private IP mà không có cơ chế NAT/public address phù hợp.

AWS khuyến nghị gắn Lambda vào **private subnets** và dùng **NAT Gateway** ở public subnet nếu phải ra IPv4 Internet.

~~~mermaid
flowchart LR
    L["Lambda VPC-connected"] --> R["Private subnet route table"]
    R --> NAT["0.0.0.0/0 → NAT Gateway"]
    NAT --> IGW["Public subnet → Internet Gateway"]
    IGW --> EXT["External HTTPS API / Internet"]
    R --> S3["S3 Gateway Endpoint"]
    R --> SM["Secrets Manager Interface Endpoint"]
~~~

### 6.2. Route tables mẫu cho NAT Gateway

| Nơi | Destination | Target |
|---|---|---|
| Private subnet | VPC CIDR | `local` |
| Private subnet | `0.0.0.0/0` | `nat-123...` |
| Public subnet chứa NAT | VPC CIDR | `local` |
| Public subnet chứa NAT | `0.0.0.0/0` | `igw-123...` |

NAT Gateway cần cấu hình thích hợp, thường với **Elastic IP** khi là public NAT Gateway. Nếu dùng nhiều AZ cho HA, nên cân nhắc **một NAT Gateway mỗi AZ** và private route tables hướng tới NAT trong cùng AZ, tránh single-AZ point of failure/cross-AZ data processing. NAT có phí theo giờ và dữ liệu xử lý.

### 6.3. IPv6 outbound từ dual-stack subnets

Lambda hỗ trợ **outbound IPv6** khi bật `Ipv6AllowedForDualStack=true` và **tất cả** subnets trong VpcConfig là **dual-stack** (có cả IPv4 và IPv6 CIDR). AWS **không hỗ trợ outbound IPv6 cho IPv6-only subnets** trong cấu hình VPC Lambda này.

Với IPv6 cần đi Internet mà không cho inbound trực tiếp, có thể dùng **egress-only Internet Gateway** và route `::/0` theo kiến trúc hỗ trợ. IPv4 Internet traffic vẫn cần NAT nếu endpoint bên ngoài chỉ hỗ trợ IPv4; bật IPv6 **không tự thay thế** `0.0.0.0/0` và NAT.

## 7. VPC endpoints: gọi AWS APIs mà không cần Internet egress

Khi function trong private subnet cần gọi một AWS service, có thể dùng **VPC endpoint** thay cho NAT nếu dịch vụ/Region/đường mạng hỗ trợ. Hai loại phổ biến:

- **Gateway Endpoint:** hỗ trợ **Amazon S3** và **DynamoDB**; gắn với route tables, không có hourly endpoint charge cho gateway endpoint tiêu chuẩn.
- **Interface Endpoint (AWS PrivateLink):** tạo ENIs trong subnets cho dịch vụ như Secrets Manager, STS, ECR, SQS, Lambda APIs, CloudWatch Logs theo khả năng hỗ trợ; có SG, Private DNS, endpoint policy và phí theo giờ/data processing.

### 7.1. Bảng lựa chọn endpoint

| Function code muốn gọi | Endpoint trong `ap-southeast-1` | Loại |
|---|---|---|
| `S3 GetObject/PutObject` | `com.amazonaws.ap-southeast-1.s3` | Gateway |
| `DynamoDB GetItem/PutItem` | `com.amazonaws.ap-southeast-1.dynamodb` | Gateway |
| `SecretsManager GetSecretValue` | `com.amazonaws.ap-southeast-1.secretsmanager` | Interface |
| `STS AssumeRole` (nếu code thực sự gọi) | `com.amazonaws.ap-southeast-1.sts` | Interface |
| `SQS SendMessage/ReceiveMessage` từ code | `com.amazonaws.ap-southeast-1.sqs` | Interface |
| `SSM GetParameter` | `com.amazonaws.ap-southeast-1.ssm` | Interface |
| `KMS Encrypt/Decrypt` từ code | `com.amazonaws.ap-southeast-1.kms` | Interface |
| `Lambda Invoke API` từ code/client | `com.amazonaws.ap-southeast-1.lambda` | Interface |
| `CloudWatch Logs API` từ code | `com.amazonaws.ap-southeast-1.logs` | Interface |

**Bảng là ví dụ cho Region Singapore**; xác nhận tên dịch vụ, availability và nhu cầu network thật trước khi tạo. Endpoint không tự cấp IAM permission. S3/DynamoDB gateway endpoints thường dùng cho traffic tới dịch vụ **cùng Region** theo giới hạn gateway endpoint, không phải đường truy cập cross-Region tự động.

### 7.2. S3 Gateway Endpoint

Trong VPC Console → Endpoints, chọn service S3 loại **Gateway**, VPC và route tables cần áp dụng. AWS cập nhật route qua S3 prefix list. Khi Lambda gọi S3 cùng Region, traffic có thể đi qua endpoint mà không cần NAT.

Kiểm tra:

1. Endpoint đúng VPC/Region.
2. Route tables của các private subnets có route prefix list → `vpce-...`.
3. Endpoint policy và S3 bucket policy cho phép IAM principal/action/key.
4. DNS và SDK Region đúng.
5. Không nhầm endpoint policy với quyền IAM `s3:GetObject`.

### 7.3. Interface Endpoint

Ví dụ Secrets Manager interface endpoint:

- Tạo endpoint cho `com.amazonaws.ap-southeast-1.secretsmanager`.
- Chọn **private subnets** và ít nhất các AZ cần dùng theo độ sẵn sàng.
- Gắn endpoint SG cho **inbound TCP 443** từ Lambda SG.
- Bật **Private DNS** nếu muốn AWS SDK dùng hostname mặc định và tự resolve sang private IP.
- Cấp `secretsmanager:GetSecretValue` trên đúng secret ARN và `kms:Decrypt` khi cần.
- Theo dõi endpoint policy, DNS, routes, SG, Availability Zones và chi phí.

### 7.4. Tránh lầm tưởng Lambda logs/SQS trigger cần endpoint từ code

**Lambda service** quản lý việc chuyển logs tiêu chuẩn tới CloudWatch Logs và polling event source mappings như SQS theo cơ chế Lambda, khác với **AWS SDK calls phát ra từ function code**. Nếu code chủ động gọi `SQS SendMessage` hoặc `CloudWatchLogs PutLogEvents`, nó cần network path tương ứng; nhưng không nhất thiết phải tạo SQS/Logs endpoint chỉ để Lambda nhận SQS events hay ghi log qua runtime logging thông thường.

Tương tự, Lambda nhận sự kiện từ EventBridge/API Gateway không cần inbound TCP route vào ENI của bạn. Network VPC chủ yếu quyết định các kết nối **do code khởi tạo**.

## 8. Lambda gọi RDS trong private subnet

### 8.1. Kết nối trực tiếp tới RDS

Cho Lambda function `orders-api` gọi PostgreSQL RDS ở private endpoint `orders-db.abc.ap-southeast-1.rds.amazonaws.com:5432`.

Cần:

1. Lambda VpcConfig chọn subnets có đường tới DB endpoint.
2. Lambda SG outbound TCP 5432 tới DB SG.
3. DB SG inbound TCP 5432 từ Lambda SG.
4. Database đang ở trạng thái available và DNS name phân giải đúng.
5. JDBC URL, TLS CA/hostname, user/password hoặc IAM DB authentication hợp lệ.
6. Execution role có quyền lấy secret nếu lưu trong Secrets Manager.
7. Nếu lấy secret qua SDK từ private subnet không có NAT, có **Secrets Manager interface endpoint**.

**Không cần mở RDS publicly accessible** để Lambda trong cùng VPC truy cập. Việc bật public access thường làm tăng bề mặt tấn công mà không giải quyết vấn đề Lambda VPC routing.

### 8.2. Vì sao Lambda concurrency gây cạn DB connections?

Một Lambda execution environment có thể tái sử dụng TCP/JDBC connection giữa các invocations **trong cùng environment**. Nhưng khi lượng concurrent invocations tăng, Lambda có thể tạo nhiều execution environments. Nếu mỗi environment giữ 5 JDBC connections và có 300 environments, hệ thống có thể tạo khoảng **1.500 DB connections**, vượt `max_connections` của DB nhỏ.

Đừng giả định Lambda execution environments dùng chung connection pool. Pool chỉ được chia sẻ **trong phạm vi một environment**, không giữa tất cả functions/invocations.

### 8.3. Amazon RDS Proxy

**RDS Proxy** là lớp proxy quản lý pool connections cho RDS/Aurora được hỗ trợ. Lambda kết nối proxy endpoint; proxy giữ và tái sử dụng backend connections với database. Nó giúp đối phó bursty concurrency, connection overhead và một số tình huống failover.

~~~mermaid
flowchart LR
    L["Nhiều Lambda execution environments"] --> P["RDS Proxy endpoint<br/>private DNS/TCP 5432"]
    P --> DB["RDS/Aurora DB"]
    SM["Secrets Manager / IAM auth"] --> P
~~~

RDS Proxy **không loại bỏ mọi giới hạn connections**. Khi workload giữ transaction lâu, sử dụng session state khiến proxy phải pin client vào DB connection, lợi ích pooling giảm. Cần quan sát `ClientConnections`, `DatabaseConnections`, `DatabaseConnectionsBorrowLatency`, DB CPU/connections và timeout.

### 8.4. Security Groups khi dùng Proxy

Ví dụ:

| Source | Destination | Rule |
|---|---|---|
| Lambda SG | RDS Proxy SG | Egress TCP 5432 |
| RDS Proxy SG | Lambda SG | Inbound TCP 5432 |
| RDS Proxy SG | RDS DB SG | Egress TCP 5432 |
| RDS DB SG | RDS Proxy SG | Inbound TCP 5432 |

Có thể thiết kế tách direct DB access và proxy access để chỉ cho Lambda đi qua proxy. Tránh mở DB ingress cho toàn bộ VPC CIDR khi chỉ một workload cần kết nối.

### 8.5. Secrets và IAM database authentication

- **Secrets Manager** lưu/rotate DB password; không hardcode password vào Lambda environment variables dưới dạng plaintext.
- Execution role cấp `secretsmanager:GetSecretValue` cho secret ARN được duyệt; với customer KMS key có thể cần `kms:Decrypt`.
- Có thể dùng **IAM database authentication** khi engine/proxy hỗ trợ, tránh quản lý password trong code; cần `rds-db:connect` trên ARN đúng và ký token có hạn sử dụng.
- Nếu dùng credentials từ Secrets Manager, thiết kế cache có TTL và xử lý rotation để tránh gọi secret API trên mọi request/khởi tạo DB connection.

RDS Proxy có phí riêng, không phải thành phần miễn phí. Khi database nhỏ, concurrency thấp, có thể so sánh direct connection với proxy theo số lượng connection, latency, độ phức tạp và chi phí.

## 9. Kết nối với ElastiCache, EFS và private HTTP API

### 9.1. Amazon ElastiCache

ElastiCache cho Valkey/Redis OSS/Memcached thường chạy ở private endpoints trong VPC. Lambda kết nối qua TCP tới cluster/reader endpoint:

- Redis/Valkey thường dùng `6379` (hoặc port cấu hình khác), Memcached `11211`.
- Cần SG inbound từ Lambda SG trên đúng port, routing và DNS.
- Chú ý TLS, AUTH/ACL, Redis client connection pool và Lambda concurrency.
- Cache là **optimization**, không nên là nguồn dữ liệu duy nhất nếu yêu cầu durability cao.

Không tạo NAT chỉ để nói chuyện với ElastiCache nằm trong cùng VPC; route `local` và SG thường đủ.

### 9.2. Amazon EFS

Lambda có thể mount **Amazon EFS** để truy cập dữ liệu chia sẻ dạng filesystem:

- Function phải có **VPC configuration**.
- EFS file system có **mount target** trong các AZ mà Lambda dùng, hoặc topology mạng theo điều kiện hỗ trợ; AWS khuyến nghị mount target ở mỗi AZ kết nối.
- **EFS access point** định nghĩa đường dẫn và POSIX identity.
- Local mount path trong Lambda bắt đầu bằng `/mnt/`.
- SG của EFS mount target cho **inbound TCP 2049 (NFS)** từ Lambda SG.
- Execution role cần `elasticfilesystem:ClientMount` và `ClientWrite` nếu ghi, cùng EFS resource policy phù hợp.

~~~yaml
# Ví dụ khái niệm CloudFormation VPC + EFS của Lambda
VpcConfig:
  SubnetIds:
    - subnet-PRIVATE-A
    - subnet-PRIVATE-B
  SecurityGroupIds:
    - sg-LAMBDA
FileSystemConfigs:
  - Arn: arn:aws:elasticfilesystem:ap-southeast-1:111122223333:access-point/fsap-EXAMPLE
    LocalMountPath: /mnt/shared
~~~

Đây là **đoạn cấu hình minh họa**, không phải template hoàn chỉnh hay ARN/IDs dùng được. EFS có phí storage/throughput, cần quản lý permissions và file locking nếu nhiều invocations cùng ghi.

### 9.3. Gọi private HTTP API trong VPC

Một Lambda có thể gọi **internal Application Load Balancer** hoặc dịch vụ chạy ECS/EC2 bằng private DNS name (Route 53 private hosted zone, internal ALB DNS). Hãy kiểm tra:

1. Lambda subnet có tuyến tới private ALB ENIs/target VPC.
2. Internal ALB SG inbound TCP 443 từ Lambda SG.
3. Listener/target group healthy; security groups/NACL giữa ALB và ECS/EC2.
4. TLS hostname, service authentication và authorization.
5. Nếu ở VPC khác, có VPC peering/Transit Gateway/PrivateLink architecture tương ứng.

**VPC Peering không hỗ trợ transitive routing**: Lambda trong VPC A không thể đi tới VPC C thông qua hai peering A–B và B–C. Cần đường trực tiếp hoặc dịch vụ transit phù hợp.

## 10. Inbound private invoke là một bài toán khác

Câu hỏi “EC2 trong VPC có thể gọi Lambda mà không ra Internet không?” khác hoàn toàn câu hỏi “Lambda có thể gọi RDS private không?”.

### 10.1. Client trong VPC gọi Lambda Invoke API

Tạo một **Interface VPC Endpoint** cho Lambda service:

~~~text
com.amazonaws.ap-southeast-1.lambda
~~~

Khi bật Private DNS, một EC2/ECS workload trong VPC có thể gọi `lambda:InvokeFunction` bằng AWS SDK tới Lambda API theo đường AWS PrivateLink, **không cần NAT/public Internet** nếu cấu hình phù hợp. Cần:

- Interface endpoint trong VPC, SG inbound 443 từ client.
- DNS settings và private DNS đúng.
- IAM policy trên caller và resource-based permission nếu cross-account/được yêu cầu.
- Endpoint policy có thể giới hạn principals, functions, actions.

**VPC endpoint này không phải cách cấu hình Lambda function để tới RDS**. Nó là điểm truy cập **Lambda API** cho caller nằm trong VPC.

~~~mermaid
flowchart LR
    C["EC2/ECS client trong VPC"] --> EP["Lambda interface endpoint<br/>PrivateLink"]
    EP --> API["Lambda Invoke API"]
    API --> F["Lambda execution environment"]
    F --> HE["Hyperplane ENI nếu function gắn VPC"]
    HE --> DB["Private database"]
~~~

### 10.2. Lambda không phải một private TCP server

Không thể lấy private IP của Hyperplane ENI rồi tạo direct TCP request tới handler giống EC2. Những cách invoke hợp lệ gồm:

- `InvokeFunction` qua Lambda API và IAM.
- API Gateway (REST/HTTP APIs hoặc private REST API theo cấu hình).
- ALB target group loại Lambda (ALB invoke Lambda theo cơ chế integration, không TCP tới Hyperplane ENI).
- EventBridge, SQS, SNS, S3 notifications và event source mappings.
- Lambda Function URLs khi phù hợp; **IAM auth không tự biến Function URL thành private VPC endpoint**.

Nếu yêu cầu frontend chỉ truy cập từ mạng riêng, thiết kế **API Gateway private API/PrivateLink** hoặc mô hình integration/authorization phù hợp; đừng nhầm VpcConfig outbound với inbound isolation.

## 11. IAM execution role cho Lambda VPC

Lambda cần quyền tạo/quản lý Hyperplane ENIs trong customer VPC. AWS cung cấp managed policy **`AWSLambdaVPCAccessExecutionRole`**, gồm quyền EC2 ENI và CloudWatch Logs cơ bản.

### 11.1. Các EC2 actions liên quan

Theo tài liệu AWS, những quyền dành cho ENI gồm:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "VpcNetworkInterfaceManagement",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSubnets",
        "ec2:DeleteNetworkInterface",
        "ec2:AssignPrivateIpAddresses",
        "ec2:UnassignPrivateIpAddresses"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Không phải tất cả các action có thể giới hạn theo ENI ARN theo cách giống IAM resource thông thường. `AWSLambdaVPCAccessExecutionRole` dễ dùng trong lab, nhưng có một caveat: những EC2 permissions gắn trên **execution role** cũng **có thể được function code dùng để gọi EC2 APIs**. Do đó, đừng coi managed policy này hoàn toàn không ảnh hưởng attack surface.

AWS lưu ý các quyền ENI chỉ cần để Lambda **tạo/quản lý kết nối**, không cần trong mỗi lần invoke; có thể xem xét tháo policy sau khi cấu hình ổn định theo runbook, nhưng cần đánh giá **đổi VPC config, scale, ENI recreation và cleanup**. Không tháo quyền rồi xóa role trước khi dọn ENIs mà không kiểm tra.

### 11.2. IAM role trust

Execution role của Lambda thường tin service principal:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowLambdaService",
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Đây là **trust** cho Lambda service assume role; business permissions vẫn là policy khác, chẳng hạn `secretsmanager:GetSecretValue` trên một secret ARN hoặc `s3:GetObject` trên một prefix.

### 11.3. Hạn chế EC2 APIs khi gọi từ function code

AWS tài liệu hóa kỹ thuật dùng IAM **`lambda:SourceFunctionArn`** để **deny các EC2 ENI management APIs từ function code**, trong khi Lambda service vẫn có thể tạo ENI vì hành động của service không mang condition key đó. Ví dụ policy **phải được kiểm thử trước khi áp dụng**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyEniApiCallsFromFunctionCode",
      "Effect": "Deny",
      "Action": [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSubnets",
        "ec2:DeleteNetworkInterface",
        "ec2:AssignPrivateIpAddresses",
        "ec2:UnassignPrivateIpAddresses"
      ],
      "Resource": "*",
      "Condition": {
        "ArnEquals": {
          "lambda:SourceFunctionArn": "arn:aws:lambda:ap-southeast-1:111122223333:function:orders-api"
        }
      }
    }
  ]
}
~~~

`lambda:SourceFunctionArn` dùng **unqualified function ARN** (không thêm version/alias). Để triển khai chính sách này, cần đánh giá chức năng của code và quyền node/network, bảo đảm các EC2 APIs không phải một phần hợp lệ của business logic. Không gắn deny rộng bừa bãi vào shared role làm hỏng các functions khác.

### 11.4. Giới hạn nơi function được gắn VPC

IAM hỗ trợ Lambda condition keys `lambda:VpcIds`, `lambda:SubnetIds`, `lambda:SecurityGroupIds` để giới hạn người tạo/update function chỉ dùng VPC/subnet/SG được phép. Chúng được dùng với `lambda:CreateFunction` và `lambda:UpdateFunctionConfiguration`; đây là **control-plane guardrails**, không phải route table hoặc security group rules.

## 12. IAM cho dịch vụ riêng tư và Secrets Manager

Để function chỉ được đọc một secret và một S3 object prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadDbSecret",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:orders/db-*"
    },
    {
      "Sid": "ReadOrderConfig",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::orders-config-example/app/*"
    }
  ]
}
~~~

Đây là **ví dụ IAM policy theo nguyên tắc quyền tối thiểu**; thay account, secret ARN và bucket/key thật. Với SSE-KMS/customer-managed key, cần key policy và `kms:Decrypt` phù hợp. Cấp quyền đọc secret không đồng nghĩa có mạng tới Secrets Manager; để gọi service đó từ private subnet, cần NAT hoặc interface endpoint.

Không đưa database password vào log, exception message, CloudWatch logs, response HTTP hoặc stack trace chi tiết. Nếu dùng Secrets Manager rotation, thiết kế cache/TTL và retry khi password được rotate.

### 12.1. IAM resource policy khi invoke Lambda

Quyền **người gọi Lambda** nằm ở một nhánh khác. Ví dụ API Gateway/S3/EventBridge invoke function có thể cần resource-based permission `lambda:AddPermission` được cấu hình theo service principal, SourceArn/SourceAccount và trigger. Quản trị execution role là chưa đủ để một external caller invoke.

Khi client từ EC2 dùng Lambda interface endpoint, caller vẫn cần `lambda:InvokeFunction`; endpoint policy có thể thêm hạn chế nhưng không thay IAM.

## 13. Cấu hình bằng AWS Management Console

Đường thao tác tổng quát:

1. Mở **AWS Lambda Console → Functions → chọn function**.
2. Vào **Configuration → VPC → Edit**.
3. Chọn đúng VPC chứa database/private resources hoặc VPC có đường đến chúng.
4. Chọn **ít nhất hai private subnets ở hai AZ khác nhau** khi khả thi.
5. Chọn security group có egress tới backend; chuẩn bị SG inbound từ Lambda SG ở RDS/Proxy/ALB.
6. Nếu cần IPv6 outbound, bật **Allow IPv6 traffic for dual-stack subnets** và xác minh tất cả subnets dual-stack.
7. Kiểm tra execution role có quyền ENI; thêm quyền S3/Secrets Manager/KMS độc lập theo nhu cầu.
8. Cấu hình NAT hoặc VPC endpoints theo luồng traffic thực tế.
9. Save; quan sát function `State`/`LastUpdateStatus` cho tới khi cập nhật thành công.
10. Test bằng request hợp lệ và xem logs, DB metrics, network errors.

**Đừng chỉnh VPC production trực tiếp chỉ để “test internet”.** Thay đổi có thể ảnh hưởng toàn bộ invocations, concurrency và khả năng kết nối; nên dùng môi trường lab, IaC/code review, rollback plan.

## 14. AWS CLI chỉ đọc: kiểm tra Function VpcConfig

Các ví dụ dùng AWS CLI v2, profile `dev` có quyền đọc, Region Singapore `ap-southeast-1`, function `orders-api`. Hãy thay bằng môi trường thật trước khi chạy.

### 14.1. Xác nhận account/role

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws lambda get-function-configuration \
  --function-name orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --query '{FunctionName:FunctionName,State:State,LastUpdate:LastUpdateStatus,Role:Role,Vpc:VpcConfig,Timeout:Timeout,MemoryMB:MemorySize}' \
  --output json
~~~

Nếu `VpcConfig.VpcId` trống, function có thể chưa được gắn customer VPC. `State=Active` chỉ cho thấy function sẵn sàng ở cấp Lambda, không chứng minh kết nối RDS/Secrets Manager đã hoạt động.

### 14.2. Đọc subnet và route tables

~~~bash
aws ec2 describe-subnets \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Subnets[].{Subnet:SubnetId,AZ:AvailabilityZone,Cidr:CidrBlock,Ipv6:Ipv6CidrBlockAssociationSet[].Ipv6CidrBlock,AvailableIPs:AvailableIpAddressCount}' \
  --output json

aws ec2 describe-route-tables \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Hãy tìm **route table của đúng subnet mà Lambda VpcConfig sử dụng**. Nếu một subnet không có explicit association, nó kế thừa **main route table**. Xác minh route tới DB CIDR, NAT, S3 Gateway endpoint hoặc TGW/peering như kiến trúc yêu cầu.

### 14.3. Đọc Security Group và endpoints

~~~bash
aws ec2 describe-security-groups \
  --group-ids sg-LAMBDA sg-DB \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws ec2 describe-vpc-endpoints \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --query 'VpcEndpoints[].{Id:VpcEndpointId,Service:ServiceName,Type:VpcEndpointType,State:State,PrivateDns:PrivateDnsEnabled,RouteTables:RouteTableIds}' \
  --output json
~~~

Các ID `vpc-EXAMPLE`, `sg-LAMBDA`, `sg-DB` chỉ là **placeholders** và lệnh sẽ lỗi nếu chưa được thay. Interface Endpoint dùng ENIs và SG; Gateway Endpoint dùng route table associations. Không kết luận endpoint chưa tồn tại chỉ vì không thấy route table ID ở **Interface** endpoint.

### 14.4. Đọc Hyperplane ENIs khi có quyền

~~~bash
aws ec2 describe-network-interfaces \
  --filters Name=interface-type,Values=lambda \
  --profile dev \
  --region ap-southeast-1 \
  --query 'NetworkInterfaces[].{Id:NetworkInterfaceId,Subnet:SubnetId,Vpc:VpcId,Type:InterfaceType,Status:Status,Description:Description}' \
  --output table
~~~

ENIs do Lambda quản lý có metadata/interface type đặc thù. Có thể không có quyền xem hoặc dữ liệu chưa kịp cập nhật; không xóa ENI vì nhìn thấy tên có chữ “Lambda”. Hyperplane ENI có thể được chia sẻ giữa functions/versions trong account.

## 15. Cấu hình thay đổi bằng CLI và IaC

Các ví dụ dưới đây **thay đổi tài nguyên AWS** nếu chạy với credentials/IDs hợp lệ. Chỉ dùng trong môi trường được cấp phép và có phê duyệt.

### 15.1. File VPC config cho CLI

Tạo file `vpc-config.json` với giá trị thật:

~~~json
{
  "SubnetIds": [
    "subnet-EXAMPLE-PRIVATE-A",
    "subnet-EXAMPLE-PRIVATE-B"
  ],
  "SecurityGroupIds": [
    "sg-EXAMPLE-LAMBDA"
  ],
  "Ipv6AllowedForDualStack": false
}
~~~

Và thao tác:

~~~bash
# THAY ĐỔI CẤU HÌNH FUNCTION - không chạy trên production chưa được duyệt.
aws lambda update-function-configuration \
  --function-name orders-api \
  --vpc-config file://vpc-config.json \
  --profile dev \
  --region ap-southeast-1
~~~

Khi VpcConfig thay đổi, chờ cập nhật xong:

~~~bash
# Waiter chỉ đọc trạng thái, không thay function.
aws lambda wait function-updated \
  --function-name orders-api \
  --profile dev \
  --region ap-southeast-1

aws lambda get-function-configuration \
  --function-name orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --query '{State:State,LastUpdateStatus:LastUpdateStatus,Reason:LastUpdateStatusReason,Vpc:VpcConfig}' \
  --output json
~~~

Không thay danh sách subnets/SG bằng placeholders trong ví dụ. Khi chạy qua PowerShell, có thể sử dụng `file://vpc-config.json` như trên để tránh vấn đề quoting JSON trực tiếp trong shell.

### 15.2. Ví dụ AWS SAM template

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: 'Example Lambda with VPC access (illustrative)'
Parameters:
  PrivateSubnetA:
    Type: AWS::EC2::Subnet::Id
  PrivateSubnetB:
    Type: AWS::EC2::Subnet::Id
  LambdaSecurityGroup:
    Type: AWS::EC2::SecurityGroup::Id
Resources:
  OrdersFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: orders-api-example
      Runtime: java21
      Handler: com.example.OrdersHandler::handleRequest
      CodeUri: target/orders-lambda.jar
      MemorySize: 512
      Timeout: 15
      VpcConfig:
        SubnetIds:
          - !Ref PrivateSubnetA
          - !Ref PrivateSubnetB
        SecurityGroupIds:
          - !Ref LambdaSecurityGroup
        Ipv6AllowedForDualStack: false
      Policies:
        - AWSLambdaVPCAccessExecutionRole
~~~

Đây là **template minh họa**, không có database, secret hay source code đi kèm và chưa được hoàn thiện để deploy production. `Policies: AWSLambdaVPCAccessExecutionRole` cung cấp quyền ENI nhưng **không cấp quyền Secrets Manager/S3 nghiệp vụ**. Cần thêm role/policies đúng resource, network endpoints, logs, alarms, code artifact, CI/CD và kiểm tra IAM security.

## 16. Java 21 Lambda kết nối RDS Proxy và Secrets Manager

Ví dụ dưới đây minh họa **luồng private DB** ở mức code. Hãy giả sử:

- Lambda có VpcConfig và SG cho phép TCP 5432 tới RDS Proxy private endpoint.
- Secrets Manager chứa JSON với keys `username` và `password`.
- Execution role có `secretsmanager:GetSecretValue` trên secret và quyền KMS phù hợp.
- Lambda gọi Secrets Manager được qua interface endpoint hoặc NAT.
- Postgres endpoint có TLS, CA/trust store đã được cấu hình phù hợp.

### 16.1. Handler Java

~~~java
package com.example;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueRequest;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Map;

public class OrdersDbHealthHandler
        implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    private static final ObjectMapper JSON = new ObjectMapper();

    // Tái sử dụng SDK client giữa invocations trong cùng execution environment.
    private static final SecretsManagerClient SECRETS =
            SecretsManagerClient.builder()
                    .region(Region.of(System.getenv("AWS_REGION")))
                    .build();

    @Override
    public Map<String, Object> handleRequest(
            Map<String, Object> event, Context context) {

        try {
            String secretId = requiredEnv("DB_SECRET_ARN");
            String proxyHost = requiredEnv("DB_PROXY_HOST");
            String database = requiredEnv("DB_NAME");

            String rawSecret = SECRETS.getSecretValue(
                    GetSecretValueRequest.builder()
                            .secretId(secretId)
                            .build())
                    .secretString();
            JsonNode creds = JSON.readTree(rawSecret);

            // Với RDS Proxy dùng đúng DNS hostname của proxy.
            // verify-full yêu cầu trust CA và hostname validation hợp lệ.
            String jdbcUrl = "jdbc:postgresql://" + proxyHost
                    + ":5432/" + database
                    + "?sslmode=verify-full&connectTimeout=3&socketTimeout=5";

            try (Connection conn = DriverManager.getConnection(
                            jdbcUrl,
                            creds.path("username").asText(),
                            creds.path("password").asText());
                 PreparedStatement statement = conn.prepareStatement("SELECT 1");
                 ResultSet result = statement.executeQuery()) {

                boolean ok = result.next() && result.getInt(1) == 1;
                return Map.of("status", ok ? "ok" : "unhealthy");
            }
        } catch (Exception e) {
            // Không log secret, JDBC URL chứa thông tin nhạy cảm hoặc SQL payload.
            context.getLogger().log(
                    "Database health check failed: "
                    + e.getClass().getSimpleName());
            throw new IllegalStateException("Database unavailable");
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing configuration: " + key);
        }
        return value;
    }
}
~~~

Các dependencies chính của project Maven/Gradle gồm `aws-lambda-java-core`, `software.amazon.awssdk:secretsmanager`, `postgresql JDBC driver` và `jackson-databind` (quản lý versions theo BOM/lockfile). Đây là **ví dụ học tập**, không phải production repository. Phải đảm bảo package handler/artefact phù hợp runtime Lambda Java và đúng certificate trust config.

### 16.2. Vì sao cần cải thiện code trước production?

- **Cache Secrets Manager** theo TTL/rotation thay vì gọi API lấy secret trong mỗi invocation; có thể dùng AWS Parameters and Secrets Lambda Extension hoặc cache thư viện được hỗ trợ.
- Tái sử dụng **DB connection** hợp lý hoặc dùng RDS Proxy/IAM DB auth. Đoạn trên mở/đóng connection mỗi lần để dễ trình bày, không phải cách tối ưu.
- Đặt **Lambda timeout** lớn hơn các network timeouts dự kiến và có timeout/circuit breaker/retry hạn chế.
- Dùng prepared statements cho mọi SQL nhận input từ request; ví dụ `SELECT 1` không nhận input.
- Kiểm soát Lambda concurrency để database và proxy không bị quá tải.
- Thực hiện schema migration bằng quy trình riêng, không dùng handler mỗi lần invoke để chạy DDL.

### 16.3. Lỗi code thường gặp

Nếu `SecretsManagerClient` báo connection timeout, kiểm tra endpoint/NAT và SG 443. Nếu client nhận `AccessDeniedException`, kiểm tra IAM secret ARN/KMS key policy. Nếu JDBC timeout, kiểm tra SG 5432, DNS/route và Proxy/DB state. Nếu JDBC trả authentication failed, điều tra secret rotation/IAM database auth; **không mở rộng IAM wildcard** để chữa lỗi database password.

## 17. Trigger, concurrency và tác động tới backend

### 17.1. Event source không đi qua Lambda ENI như một inbound server

| Trigger | Cơ chế chính | VPC consideration |
|---|---|---|
| API Gateway | API Gateway invoke Lambda | VpcConfig dùng cho **outbound code calls**, không để API Gateway TCP vào ENI |
| EventBridge rule | EventBridge gọi Lambda theo quyền integration | Không cần inbound SG trên Lambda |
| S3 event notification | S3 service invoke Lambda | Chỉ code gọi S3 mới cần endpoint/NAT từ customer VPC |
| SQS event source mapping | Lambda service poll SQS và invoke | Function code chủ động `SendMessage` mới cần SQS network path |
| ALB Lambda target | ALB dùng integration invoke Lambda | Không phải kết nối TCP trực tiếp tới Hyperplane ENI |
| EC2/ECS code gọi `InvokeFunction` | AWS Lambda API | Có thể dùng Lambda interface endpoint trong client VPC |

### 17.2. Concurrency tăng nhanh

Lambda có thể tăng số execution environments khi event load tăng. Một database/ElastiCache cluster nhỏ có thể không theo kịp. Thiết kế:

- **Reserved concurrency** cho function để giới hạn số invocations đồng thời khi cần.
- RDS Proxy hoặc pooling phù hợp cho SQL.
- Queue/SQS và batch/window size khi cần hấp thụ burst.
- Retry/backoff với jitter; tránh retry storm và dead-letter/re-drive chính sách phù hợp.
- **Idempotency** để việc retry không tạo duplicate writes.
- Đo `ConcurrentExecutions`, `Throttles`, `Duration`, DB connections và downstream latency.

Reserved concurrency có thể giảm đột biến DB, nhưng cũng làm tăng throttling và độ trễ queue khi cấu hình quá thấp. Cân bằng theo SLO và dữ liệu thực.

### 17.3. Cold start và Hyperplane ENI provisioning

Đừng nhầm **cold start** (khởi tạo Java runtime/application) với **lần đầu tạo Hyperplane ENI** khi gắn VPC. Hyperplane ENI có thể được tái sử dụng, nhưng initialization của Java vẫn chịu ảnh hưởng memory/CPU, dependencies, TLS connections, clients và DB bootstrap. Dùng CloudWatch `Init Duration`, distributed tracing/metrics và thử tải để phân tích nguyên nhân.

## 18. Monitoring, security và incident response

### 18.1. CloudWatch và Lambda logs

Theo dõi:

- Lambda metrics `Invocations`, `Errors`, `Duration`, `Throttles`, `ConcurrentExecutions`, `IteratorAge` (nếu phù hợp).
- `State`/`LastUpdateStatus` khi cấu hình VPC hoặc khi function chuyển `Inactive/Pending`.
- Application logs có correlation/request ID, HTTP/JDBC status, latency theo dependency nhưng **không in secrets**.
- RDS/Proxy metrics về client/backend connections, borrow latency, database CPU và connections.
- NAT Gateway metrics/cost, Interface Endpoint metrics/flow logs khi áp dụng.
- X-Ray/tracing hoặc OpenTelemetry theo thiết kế để tách thời gian network từ thời gian xử lý ứng dụng.

### 18.2. VPC Flow Logs, Reachability Analyzer và CloudTrail

- **VPC Flow Logs:** giúp quan sát IP/port/protocol, `ACCEPT/REJECT` trên ENIs/subnets/VPC; `ACCEPT` không chứng minh backend trả HTTP/SQL thành công.
- **Reachability Analyzer:** phân tích thành phần mạng có thể chặn đường từ một network interface/endpoint phù hợp; phải chọn đúng source/destination được hỗ trợ.
- **CloudTrail:** kiểm toán ai thay `UpdateFunctionConfiguration`, IAM role, SG, route table hoặc tạo endpoint. CloudTrail không thay application tracing.
- **IAM Access Analyzer / Config / Security Hub:** đánh giá quyền rộng, public exposure và compliance theo cấu hình tổ chức.

### 18.3. Guardrails

- Chỉ người được phép mới được gắn function vào VPC/subnet/SG, dùng IAM condition keys.
- Execution role chỉ có quyền đọc secret/key cần thiết; tuyệt đối tránh `AdministratorAccess`.
- Endpoint policies, bucket policies và SG giới hạn đúng đường truy cập.
- KMS encrypted secrets/environment variables; TLS cho DB/API.
- Không để secrets trong environment plain text hoặc log; không đưa secret vào tracing span attributes.
- Giữ IaC/approval và rollback nếu update VPC làm ngưng kết nối.

## 19. Troubleshooting: các lỗi có thể gặp

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra trước |
|---|---|---|
| Function mới `Pending` lâu sau khi gắn VPC | Hyperplane ENI đang tạo, thiếu quyền EC2 hoặc subnet hết IP | `StateReason`/`LastUpdateStatusReason`, execution role, subnet IP |
| Function `Inactive` sau thời gian dài không dùng | Hyperplane ENI bị thu hồi sau 14 ngày idle | State, đợi khởi tạo lại trước retry |
| `ENILimitReachedException` | VPC/ENI quota hoặc quản lý interfaces | ENI/service quota và yêu cầu hỗ trợ phù hợp |
| Lambda gọi RDS timeout | SG egress/inbound 5432, route, DNS/Proxy/DB | SG của Lambda và DB/Proxy, subnet associations |
| Lambda gọi Secrets Manager timeout | Thiếu NAT/Secrets Manager endpoint, endpoint SG/DNS sai | VPC endpoint hoặc NAT, Private DNS, TCP 443 |
| `SecretsManager AccessDenied` | IAM role/secret policy/KMS deny | Execution role, ARN secret, key policy |
| AWS SDK gọi S3 từ VPC bị timeout | Không có gateway endpoint/NAT hoặc route sai | Route tables S3 prefix list, policy, Region |
| Đã gắn Lambda vào public subnet nhưng không ra Internet | Không có public IP cho Hyperplane ENI | Private subnet + NAT cho IPv4 |
| IPv6 outbound không hoạt động | Không phải tất cả subnets dual-stack, chưa bật IPv6 hoặc thiếu `::/0` egress | `Ipv6AllowedForDualStack`, subnet IPv6, route/SG |
| API Gateway không gọi được Lambda | Invoke permission/integration sai | Lambda resource policy, API Gateway logs; **không** mở inbound Lambda SG |
| EC2 không gọi `InvokeFunction` private được | Thiếu Lambda interface endpoint/DNS/SG/IAM | `com.amazonaws.region.lambda`, endpoint SG 443, caller IAM |
| Function `running` nhưng SQL auth lỗi | Secret sai/rotate, JDBC TLS/DB user | RDS Proxy/DB auth, secret version, TLS |
| RDS vượt `max_connections` | Lambda concurrency hoặc pool quá rộng | `ConcurrentExecutions`, RDS/Proxy metrics |
| NACL gây intermittent TCP failures | Return ephemeral ports bị chặn | TCP/UDP `1024–65535` theo hướng AWS |
| Interface endpoint DNS trả public IP | Private DNS/VPC DNS attributes chưa bật, conditional forward sai | Endpoint configuration và Route 53 Resolver |
| VPC B không truy cập VPC C qua A | Peering non-transitive | Peering trực tiếp, TGW hoặc PrivateLink |
| S3/SQS trigger không kích hoạt | Event source mapping/resource permission bị lỗi | Trigger configuration/IAM, không nhầm với Lambda VPC egress |
| Function bị timeout khi gọi external API | NAT/Internet egress thiếu; remote timeout | `0.0.0.0/0` → NAT, NAT SG/NACL, remote DNS |
| Phí NAT cao dù chỉ gọi S3 | Traffic S3 đi qua NAT thay vì gateway endpoint | Endpoint/route table và AWS billing |

### 19.1. Quy trình chẩn đoán 7 bước

1. Xác nhận đúng **AWS account, Region, function ARN, VpcConfig**.
2. Đọc **State/LastUpdateStatus**, để biết đang chờ provisioning hay function đã Active.
3. Ghi rõ **destination hostname/IP, TCP port, AWS API service**.
4. Kiểm tra DNS resolution, route table của **đúng Lambda subnets**.
5. Kiểm tra SG egress/inbound, NACL (kể cả ephemeral return ports).
6. Kiểm tra IAM execution role/resource policy/KMS/endpoint policy riêng.
7. Đối chiếu CloudWatch logs, Flow Logs và DB/proxy metrics; thử lại bằng testcase tối giản được phê duyệt.

**Không dùng “mở mọi port và cấp admin để thử”** làm quy trình chuẩn. Nếu chỉ muốn tìm nguyên nhân, ưu tiên CLI đọc cấu hình/metrics và thay đổi có rollback trong lab.

## 20. Chi phí và kiến trúc phục hồi

### 20.1. Chi phí cần tách

| Thành phần | Chi phí thường gặp |
|---|---|
| Lambda compute | Invocations, duration và các tính năng được chọn |
| Hyperplane ENI | Không xem nó như một EC2 instance riêng để tự vận hành; xem các phí VPC network liên quan |
| NAT Gateway | Giờ sử dụng và dữ liệu xử lý; thêm transfer cross-AZ nếu đi qua AZ khác |
| Interface VPC Endpoint | Endpoint-hour theo AZ và data processing |
| Gateway Endpoint S3/DynamoDB | Không có phí endpoint-hour/data processing của Gateway endpoint tiêu chuẩn |
| RDS / RDS Proxy | DB compute/storage/I/O và proxy fees |
| EFS | Storage/throughput và các phí liên quan |
| CloudWatch/X-Ray/CloudTrail | Logs ingestion, retention, trace và audit |
| Data transfer | Theo AZ/Region/Internet/service path tùy kiến trúc |

Một function mất NAT nhưng chỉ gọi **S3 và Secrets Manager** có thể dùng S3 Gateway Endpoint và Secrets Manager Interface Endpoint thay vì duy trì NAT Gateway chỉ cho hai luồng này. Tuy nhiên, Interface Endpoint có phí riêng; so sánh cost theo traffic volume, AZ, number of endpoints và SLO thực tế.

### 20.2. Độ sẵn sàng

- Chọn ít nhất hai private subnets/AZ khi phù hợp.
- Nếu dùng NAT cho IPv4 egress liên tục, thiết kế NAT đa AZ và route table AZ-local nếu cần HA.
- Interface Endpoints cần ENIs ở các AZ sử dụng, SG và Private DNS đúng.
- RDS nên dùng Multi-AZ phù hợp; RDS Proxy hỗ trợ quản lý connections và một số failover.
- Đặt concurrency/timeout/retries trong giới hạn của DB/Redis/HTTP API.
- Đừng coi việc có VPC attachment là chiến lược disaster recovery; còn phải có backup/replication/cross-Region failover nếu yêu cầu.

### 20.3. Nên gắn VPC khi nào?

| Workload | Có cần VpcConfig? | Lý do |
|---|---|---|
| Xử lý S3 events rồi ghi DynamoDB | **Không bắt buộc** | Có thể dùng AWS service APIs từ Lambda-managed environment |
| Đọc RDS private endpoint | **Thường cần** | Có mạng riêng tới DB |
| Gọi ElastiCache private cluster | **Cần đường private** | Private IP và SG của cache |
| Mount EFS | **Có** | Kết nối EFS mount targets qua VPC |
| Gọi external public REST API | **Không bắt buộc** | Nếu gắn VPC, cần NAT/IPv6 egress |
| EC2 gọi Lambda qua PrivateLink | **Không yêu cầu Lambda tự gắn VPC** | Lambda interface endpoint nằm ở **VPC của caller** |
| Gọi service qua cross-VPC PrivateLink | **Tùy thiết kế** | Lambda muốn kết nối private endpoint trong VPC của mình |

## 21. Bài thực hành chỉ đọc: phân tích một Lambda VPC architecture

### 21.1. Điều kiện

- AWS CLI v2, profile `dev` có quyền xem Lambda, EC2, IAM và các resources liên quan.
- Nếu có quyền đọc, dùng function và VPC trong account lab. Nếu không, có thể phân tích sơ đồ/tables/JSON minh họa.
- **Không tạo NAT, endpoint, sửa SG, đổi VpcConfig hay invoke production function** trong bài lab cơ bản.
- Tất cả IDs trong lệnh đều là placeholder; thay bằng resources có quyền xem nếu chạy.

### 21.2. Phần A — Nhận diện mạng

~~~bash
aws sts get-caller-identity --profile dev

aws lambda get-function-configuration \
  --function-name orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --query '{Name:FunctionName,State:State,Vpc:VpcConfig,Role:Role}' \
  --output json
~~~

Ghi VPC ID, subnet IDs, SG IDs, `Ipv6AllowedForDualStack`. Nếu không có VpcConfig, giải thích function có thể gọi RDS private bằng cách nào (nếu có network resource connection khác được hỗ trợ theo kiến trúc).

### 21.3. Phần B — Đọc route và SG

~~~bash
aws ec2 describe-route-tables \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws ec2 describe-security-groups \
  --group-ids sg-LAMBDA sg-DB \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Hỏi: Lambda có route local đến RDS private không? SG DB mở đúng port cho Lambda SG không? Nếu SQL timeout nhưng Secrets Manager hoạt động, bạn nên kiểm tra gì đầu tiên?

### 21.4. Phần C — Kiểm tra endpoints

~~~bash
aws ec2 describe-vpc-endpoints \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Phân loại Gateway Endpoint và Interface Endpoint. Với S3: endpoint có gắn vào đúng route tables chưa? Với Secrets Manager: endpoint SG mở inbound 443 và bật private DNS chưa?

### 21.5. Phần D — Quyết định có cần NAT không

Giả sử function chỉ gọi:

1. RDS PostgreSQL private trong cùng VPC.
2. Secrets Manager qua interface endpoint.
3. S3 cùng Region qua gateway endpoint.

Hỏi: Cần NAT Gateway **chỉ vì ba luồng này** không? **Không**, nếu tất cả service/endpoint/network/SG/IAM đã hỗ trợ đầy đủ. Nếu function sau này gọi API thanh toán chỉ có public IPv4 endpoint, cần thiết kế thêm egress (ví dụ NAT Gateway) hoặc thay cách tích hợp.

### 21.6. Phần E — Phân biệt trigger và data plane

Hệ thống có SQS queue kích hoạt Lambda và Lambda ghi dữ liệu vào RDS. Nếu mất SQS VPC endpoint nhưng Lambda service vẫn poll queue, trigger còn có thể hoạt động không? Trong thiết kế Lambda-managed event source mapping tiêu chuẩn, **có thể**; cần kiểm tra trigger IAM/config. Nếu **code** tự gửi message tới SQS từ private subnet, nó lại cần SQS network path.

### 21.7. Phần F — Viết runbook

Tạo bảng:

| Thành phần | Đã kiểm tra? | Owner | Rủi ro |
|---|---|---|---|
| Lambda VpcConfig và trạng thái | ... | Team ứng dụng | ENI pending/inactive |
| Private subnet AZs/routes | ... | Network | Single AZ/NAT |
| Lambda SG → RDS Proxy SG | ... | Network/DBA | JDBC timeout |
| Secrets Manager endpoint | ... | Platform | Không lấy được credentials |
| IAM/KMS/bucket policies | ... | Security | AccessDenied |
| DB connections và concurrency | ... | App/DBA | DB exhaustion |
| CloudWatch/Flow Logs/alarms | ... | SRE | Không phát hiện lỗi |
| Backup/rollback | ... | App/DBA | Mất dữ liệu/gián đoạn |

## 22. Tình huống kiến trúc và câu hỏi tự đánh giá

### 22.1. Tình huống: API xử lý đơn hàng

Một API Gateway route gọi Lambda Java. Lambda truy vấn RDS PostgreSQL private và ghi object hóa đơn lên S3. Ứng dụng cần TLS tới DB, quản lý secret và không cần Internet công khai.

Thiết kế hợp lý:

1. Lambda gắn hai private subnets khác AZ trong cùng VPC với RDS Proxy.
2. SG Lambda egress 5432 tới Proxy, SG Proxy inbound 5432 từ Lambda.
3. Secrets Manager Interface Endpoint với SG inbound 443 từ Lambda; role có `GetSecretValue`/KMS phù hợp.
4. S3 Gateway Endpoint trên đúng route tables; role có `PutObject` đúng bucket prefix.
5. RDS Proxy pool connections và Lambda reserved concurrency để bảo vệ DB.
6. API Gateway invoke Lambda qua integration permission; **không mở inbound Lambda SG**.
7. CloudWatch/X-Ray/CloudTrail cùng runbook backup và rollback.

### 22.2. Câu hỏi tự kiểm tra

1. Gắn Lambda vào customer VPC có nghĩa execution environment chạy trực tiếp trong subnet đó không?
2. Hyperplane ENI có được tạo một cái cho mỗi invocation không?
3. Vì sao function mới gắn VPC có thể `Pending`?
4. Điều gì có thể xảy ra sau 14 ngày function không dùng?
5. Lambda có Internet chỉ vì nó chọn public subnet không?
6. Khác nhau giữa Gateway VPC Endpoint và Interface Endpoint là gì?
7. Muốn gọi Secrets Manager từ private subnet không NAT, cần gì ngoài IAM permission?
8. Gọi S3 cùng Region từ Lambda trong VPC có nhất thiết phải qua NAT không?
9. Vì sao Lambda SG không cần inbound để nhận trigger từ API Gateway?
10. Khác nhau giữa RDS Proxy SG inbound và Lambda SG outbound trên TCP 5432?
11. Với restrictive NACL, ephemeral port range nào được AWS nhắc tới cho Lambda VPC?
12. Một EC2 trong VPC muốn gọi Lambda Invoke API không qua Internet cần endpoint loại nào?
13. Lambda VpcConfig và endpoint `com.amazonaws.region.lambda` khác nhiệm vụ như thế nào?
14. `AWSLambdaVPCAccessExecutionRole` cho phép các EC2 APIs nào, và vì sao cần xem xét security?
15. `lambda:SourceFunctionArn` có thể dùng trong tình huống nào?
16. Vì sao RDS trực tiếp có thể cạn connections khi Lambda concurrency tăng?
17. Lambda có thể mount EFS nếu không có VPC connection không?
18. Với IPv6, cần điều kiện gì ở **tất cả subnets**?
19. Vì sao function có `State=Active` nhưng JDBC vẫn timeout?
20. Nếu ứng dụng chỉ xử lý S3/SQS/DynamoDB events qua AWS APIs, VPC attachment có luôn cần không?

### Đáp án định hướng

- **Hyperplane ENI:** kết nối từ execution environment do Lambda quản lý tới customer VPC; không phải private server nhận inbound.
- **Networking:** private subnet + route table + SG/NACL + DNS; muốn IPv4 Internet dùng NAT, gọi AWS APIs có thể dùng VPC endpoints.
- **RDS:** dùng SG đúng hướng, secrets/DB auth và RDS Proxy khi cần pool connections.
- **Invoke:** client trong VPC dùng Lambda interface endpoint là bài toán khác với outbound VpcConfig.
- **Vận hành:** IAM least privilege, đồng bộ AZ, kiểm tra trạng thái ENI, concurrency, logs, metrics và tổng chi phí mạng.

## 23. Tài liệu AWS chính thức

1. [Giving Lambda functions access to resources in an Amazon VPC](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html) — Customer VPC, Hyperplane ENI, IAM và IPv6.
2. [Enable internet access for VPC-connected Lambda functions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-internet.html) — Private subnets, NAT Gateway, Internet egress.
3. [Troubleshoot networking issues in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/troubleshooting-networking.html) — NACL ephemeral ports, VPC endpoints và lỗi timeout.
4. [Connecting inbound interface VPC endpoints for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-endpoints.html) — Private invoke qua Lambda API.
5. [AWS Lambda with Amazon RDS](https://docs.aws.amazon.com/lambda/latest/dg/services-rds.html) — RDS direct connection và RDS Proxy.
6. [Automatically connecting Lambda functions and RDS DB instances](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/lambda-rds-connect.html) — VPC, SG và RDS auto-connect.
7. [RDS Proxy connection management](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html) — Pooling, limits và failover.
8. [RDS Proxy network prerequisites](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-network-prereqs.html) — VPC, subnets, AZ và SG.
9. [Lambda with EFS file systems](https://docs.aws.amazon.com/lambda/latest/dg/configuration-filesystem-efs.html) — Access point, mount targets, NFS/2049.
10. [Access AWS services through VPC endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/privatelink-access-aws-services.html) — PrivateLink interface endpoints và private DNS.
11. [S3 Gateway VPC Endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html) — Route tables, endpoint policy và giới hạn.
12. [DynamoDB Gateway Endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-ddb.html) — Private DynamoDB access.
13. [Using source function ARN for IAM access control](https://docs.aws.amazon.com/lambda/latest/dg/permissions-source-function-arn.html) — `lambda:SourceFunctionArn`.
14. [Lambda execution role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html) — Role trust, permissions và least privilege.
15. [Lambda permissions and resource-based policies](https://docs.aws.amazon.com/lambda/latest/dg/access-control-resource-based.html) — Invoke authorization.
16. [AWS CLI get-function-configuration](https://docs.aws.amazon.com/cli/latest/reference/lambda/get-function-configuration.html) — Đọc VpcConfig, state và execution role.
17. [AWS CLI update-function-configuration](https://docs.aws.amazon.com/cli/latest/reference/lambda/update-function-configuration.html) — Chỉnh subnets/SG/IPv6.
18. [Using AWS SAM with Lambda VPC](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-function.html) — IaC VpcConfig.
19. [Amazon VPC security groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html) — Stateful rules.
20. [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html) — Chẩn đoán network.
21. [Lambda pricing](https://aws.amazon.com/lambda/pricing/) — Request, duration và các cấu hình.
22. [AWS PrivateLink pricing](https://aws.amazon.com/privatelink/pricing/) — Interface endpoint-hour và data processing.
23. [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/) — NAT Gateway, IPv4 và truyền dữ liệu.

> **Ghi nhớ:** Lambda kết nối VPC **để outbound code có thể đi tới tài nguyên private**. Cần quy hoạch subnet/AZ, Hyperplane ENI, route tables, SG/NACL, DNS, NAT/PrivateLink, IAM và sức chịu tải backend. **VPC attachment không tạo inbound TCP server**; client muốn gọi Lambda riêng tư phải dùng integration/Lambda API thông qua cơ chế được hỗ trợ. Chỉ khi xem cả network, identity, application, reliability và billing, thiết kế serverless mới thực sự an toàn và bền vững.

