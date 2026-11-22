# Phối hợp load balancer, Auto Scaling và nhiều AZ trên AWS

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **Elastic Load Balancing (ELB)**, **EC2 Auto Scaling**, **target group**, **health check** và **Availability Zone (AZ)** phối hợp để phục vụ ứng dụng liên tục khi lưu lượng thay đổi.
- Chọn **Application Load Balancer (ALB)**, **Network Load Balancer (NLB)** hoặc một loại cân bằng tải khác theo giao thức và nhu cầu; phân biệt cân bằng tải với mở rộng năng lực xử lý.
- Tạo kiến trúc web/API với **ALB trên nhiều public subnets**, **Auto Scaling group (ASG) chạy EC2 ở private subnets thuộc nhiều AZ**, và hệ thống dữ liệu có cơ chế khả dụng phù hợp.
- Hiểu **load balancer health check**, **EC2/ELB health check của ASG**, **health check grace period**, **instance warmup**, **target deregistration delay** và vai trò của chúng khi scale hoặc thay máy lỗi.
- Lựa chọn **target tracking**, **step scaling**, **scheduled scaling** hoặc **predictive scaling** theo dữ liệu tải; định nghĩa min/desired/max capacity và kiểm thử trong các tình huống cao điểm, lỗi một instance, lỗi một AZ.
- Xác minh bằng AWS Console, AWS CLI, CloudWatch và công cụ kiểm thử thực; khoanh vùng các lỗi về subnet, security group, target registration, health check, policy, quota và dữ liệu trạng thái.
- Ước lượng tài nguyên/chi phí, thiết kế bảo mật, logging, backup, RTO/RPO và phương án phục hồi thay vì coi số lượng instance là thước đo duy nhất về độ tin cậy.

**Bối cảnh:** Đây là bài của chương **Cân bằng tải và mở rộng**, thuộc module **CLOUD_PROVIDERS_AWS**. Người học đã gặp các khối cơ bản của AWS: **Region/AZ, IAM, VPC, compute, storage, database, tích hợp và serverless**. Trong thực tế, một API chạy trên EC2/ECS cần kết hợp **phân phối yêu cầu**, **quản lý số lượng backend** và **đặt backend ở nhiều miền lỗi** để đáp ứng mục tiêu an toàn, quan sát được, phục hồi được và có chi phí phù hợp.

> **Phạm vi bài:** Ví dụ thực hành dùng **Application Load Balancer + Amazon EC2 Auto Scaling** để hiểu rõ cơ chế. Với **ECS Service Auto Scaling**, **EKS Horizontal Pod Autoscaler** hoặc Lambda concurrency, phần mở rộng năng lực xử lý do cơ chế riêng quản lý; không được tự coi những cơ chế đó là EC2 Auto Scaling group dù vẫn có thể kết hợp ALB/NLB.

## 1. Ba thành phần giải quyết ba vấn đề khác nhau

Một instance EC2 đơn lẻ có thể phục vụ website khi lưu lượng thấp. Nhưng khi traffic tăng hoặc instance gặp sự cố, cần trả lời ba câu hỏi:

1. **Yêu cầu của người dùng sẽ được gửi đến instance nào?** → **Load balancer**.
2. **Cần bao nhiêu instance lúc này, và ai thêm/bớt instance?** → **Auto Scaling**.
3. **Nếu một AZ bị gián đoạn, có backend ở AZ khác và đường truy cập còn hoạt động không?** → **Phân bố Multi-AZ**, kết hợp health check và các phụ thuộc chịu lỗi.

| Thành phần | Trách nhiệm chính | Không tự làm |
| --- | --- | --- |
| **Load balancer** | Nhận kết nối/yêu cầu, chọn target phù hợp, kiểm tra target health theo cấu hình | Không tự tạo EC2 khi tải tăng; không sao lưu dữ liệu |
| **EC2 Auto Scaling group** | Duy trì và điều chỉnh số lượng EC2 theo min/desired/max, thay instance bị đánh dấu unhealthy | Không thay thế routing yêu cầu HTTP của ALB; không tự đồng bộ database |
| **Nhiều Availability Zone** | Phân tách thành phần qua các miền lỗi trong cùng Region | Không đảm bảo HA khi chỉ có backend khỏe ở một AZ hoặc phụ thuộc chung bị lỗi |
| **CloudWatch / alarms** | Đo latency, error, capacity, CPU và metric để quyết định/cảnh báo | Không tự sửa mọi lỗi ứng dụng |
| **Database/queue/cache** | Quản lý dữ liệu và trạng thái của ứng dụng | Không tự được bảo vệ chỉ vì EC2 scale được |

**Hiểu đúng:** Load balancer và ASG phối hợp để **phân phối traffic và thay đổi số backend**. **Multi-AZ** cung cấp khả năng cô lập lỗi cơ sở hạ tầng. Cả ba cần được cấu hình đúng, sau đó **kiểm thử thực** ở mức ứng dụng.

### Luồng ứng dụng web điển hình

~~~mermaid
flowchart TB
    Client[Khách hàng / Browser] --> DNS[Route 53 / DNS]
    DNS --> ALB[Application Load Balancer - Region]
    ALB --> TG[Target group: HTTP 8080]

    subgraph VPC["VPC trong một AWS Region"]
        subgraph AZA["Availability Zone A"]
            PubA[Public subnet A / ALB node]
            AppA[Private subnet A / EC2 A]
        end
        subgraph AZB["Availability Zone B"]
            PubB[Public subnet B / ALB node]
            AppB[Private subnet B / EC2 B]
        end
        TG --> AppA
        TG --> AppB
        ASG[EC2 Auto Scaling group] -. Khởi tạo, đăng ký, thay thế .-> AppA
        ASG -. Khởi tạo, đăng ký, thay thế .-> AppB
    end

    AppA --> DB[(RDS Multi-AZ hoặc DB phù hợp)]
    AppB --> DB
    AppA --> S3[(S3: ảnh / object)]
    AppB --> S3
    ASG --> CW[CloudWatch / scaling policies]
~~~

Đây là **sơ đồ logic**. ALB là tài nguyên vùng được bật trong nhiều AZ; DNS và các node của ALB xử lý lưu lượng vào theo cơ chế dịch vụ. **Target group** chứa các target phù hợp; **ASG** tạo/xóa EC2 và tích hợp việc đăng ký/deregister vào target group. Một yêu cầu không đi tuần tự qua tất cả các AZ trong sơ đồ.

## 2. Load balancer nào phù hợp?

AWS cung cấp nhiều loại Elastic Load Balancing, phục vụ những lớp giao thức khác nhau.

| Loại | Lớp / đặc điểm nổi bật | Tình huống phù hợp | Điểm cần xét |
| --- | --- | --- | --- |
| **Application Load Balancer (ALB)** | Layer 7: HTTP/HTTPS, route theo path/host/header và nhiều khả năng cho ứng dụng web | Website, REST API, microservices dùng HTTP(S), gRPC theo khả năng hỗ trợ | Target group, health check, TLS, routing rule, idle timeout, sticky sessions |
| **Network Load Balancer (NLB)** | Layer 4: TCP/UDP/TLS, hiệu năng cao, địa chỉ IP có thể ổn định theo cấu hình | TCP/UDP service, game server, dịch vụ cần IP tĩnh/tính năng L4 | Cross-zone, client IP preservation, TLS/listener, loại target và kiểm tra health |
| **Gateway Load Balancer (GWLB)** | Tích hợp/scale các thiết bị ảo kiểm tra lưu lượng qua cơ chế phù hợp | Network firewall/inspection appliance | GWLB endpoint, route symmetry, thiết bị appliance và tính sẵn sàng |
| **Classic Load Balancer (CLB)** | Thế hệ cũ cho ứng dụng legacy | Duy trì workload cũ đã triển khai | Nên đánh giá chuyển sang ALB/NLB cho kiến trúc mới |

**Quy tắc chọn nhanh:**

- API dùng HTTPS với route `/users`, `/orders` → bắt đầu bằng **ALB**.
- Dịch vụ TCP/UDP đặc thù hoặc cần địa chỉ IP tĩnh của load balancer → đánh giá **NLB**.
- Muốn cài firewall appliance vào tuyến mạng → **GWLB**.
- Muốn ứng dụng container chạy Fargate sau ALB: dùng **target type = ip** khi phù hợp; ASG EC2 trong bài dùng **target type = instance**.

### Listener và target group là hai cấu hình khác nhau

**Listener** quy định ALB nhận giao thức/cổng nào và dùng **rule** để chuyển request đi đâu. **Target group** chứa danh sách EC2/IP/Lambda theo loại hỗ trợ, protocol/port đích và thông số health check.

Ví dụ:

~~~text
Người dùng:
  HTTPS 443 → ALB listener
                  ├─ /api/* → target group "api" → EC2 port 8080
                  └─ /web/* → target group "web" → EC2 port 3000
~~~

Trên public ALB, nên dùng **HTTPS và chứng chỉ TLS được quản lý qua ACM** theo yêu cầu bảo mật. Kết nối ALB → backend có thể là HTTP trong VPC khi chính sách cho phép, hoặc HTTPS end-to-end khi cần. Dùng IAM/Secrets Manager để quản lý các bí mật của ứng dụng; ALB không thay thế xác thực nghiệp vụ.

## 3. Hiểu Availability Zone và cách bố trí subnet

**AWS Region** gồm nhiều AZ, là những vùng hạ tầng riêng biệt để giảm rủi ro lỗi cùng lúc. Một **subnet chỉ nằm trong một AZ**. Một VPC trải trên Region và chứa subnet thuộc nhiều AZ.

Với ứng dụng public web/API thông thường:

- **ALB internet-facing:** bật ở **ít nhất hai AZ** (ALB yêu cầu tối thiểu hai AZ) và dùng **public subnet riêng trong mỗi AZ** với tuyến phù hợp tới Internet Gateway.
- **EC2 backend trong ASG:** dùng các **private subnets ở ít nhất hai AZ**, cho phép truy cập backend từ SG của ALB.
- **RDS/khối dữ liệu:** triển khai chế độ Multi-AZ hoặc replication/backup phù hợp với RTO/RPO; chỉ có nhiều EC2 không làm dữ liệu trở nên đa AZ.
- **Đường egress:** nếu EC2 cần gọi Internet/API, xem NAT Gateway mỗi AZ hoặc VPC endpoint theo nhu cầu; không mặc định mọi instance private bắt buộc có NAT.
- **IAM/security:** dùng instance profile/role, Security Group, private subnets và chính sách truy cập dữ liệu đúng mức.

### Vì sao public ALB với private EC2?

Public ALB là điểm vào được kiểm soát; backend không cần public IP để nhận request từ Internet. Luồng thường như sau:

~~~mermaid
flowchart LR
    User[Internet / HTTPS 443] --> ALB[Public ALB, SG ALB]
    ALB -->|TCP 8080| A[EC2 A, private IP]
    ALB -->|TCP 8080| B[EC2 B, private IP]
    A --> DB[(Private DB)]
    B --> DB
~~~

**Security Group mẫu:**

| Tài nguyên | Inbound | Outbound |
| --- | --- | --- |
| **ALB SG** | TCP/443 từ nguồn khách hàng được phép (có thể công khai `0.0.0.0/0` cho web public) | Đến SG backend trên TCP/8080 và các cổng health check cần thiết |
| **EC2 backend SG** | TCP/8080 **từ ALB SG**, không mở trực tiếp từ Internet | Đến database, S3 endpoint/API hoặc các đích ứng dụng cần thiết |
| **DB SG** | Cổng DB như TCP/5432 **từ backend SG** | Theo yêu cầu DB; không cấp public inbound tùy tiện |

**ALB cần đường đi hợp lệ đến backend qua VPC**, không có nghĩa backend phải nằm trong public subnet. Kiểm tra cả **route table, SG và NACL**. Khi NACL bị siết chặt, phải nhớ NACL **stateless**, cần tính cổng phản hồi/ephemeral ports theo chiều đi và về.

### Kịch bản lỗi một AZ

Khi AZ A mất khả năng phục vụ, mục tiêu là yêu cầu mới tiếp tục đến **healthy targets ở AZ B**, tùy tình trạng ALB/DNS và cấu hình. ASG có thể cố tạo/thay instance ở những AZ còn đủ điều kiện, nhưng **không cam kết cấp phát ngay** nếu thiếu capacity, quota hoặc ảnh máy/launch template có vấn đề.

Dù có hai AZ, **desired capacity = 2** chỉ thường tương ứng **một backend mỗi AZ** ở trạng thái bình thường. Nếu AZ A lỗi, backend B có thể bị quá tải nếu không còn dư năng lực. **Khả dụng** và **đủ năng lực chịu tải khi lỗi** là hai mục tiêu cần đo riêng.

## 4. Cross-zone load balancing và phân bố target

**Cross-zone load balancing** cho phép một node của load balancer gửi yêu cầu tới healthy target nằm ở AZ khác, thay vì chỉ dùng target trong AZ của node đó.

### Khác biệt ALB và NLB

| Cấu hình | ALB | NLB |
| --- | --- | --- |
| Cross-zone ở cấp load balancer | **Luôn bật**, không thể tắt ở cấp ALB | **Mặc định tắt**, có thể bật |
| Điều chỉnh ở cấp target group | Có thể **override** để tắt cho target group theo hỗ trợ | Có thể bật/tắt hoặc kế thừa cấu hình load balancer |
| Lý do cân nhắc tắt ở TG | Muốn giới hạn phạm vi phục vụ theo AZ, giảm ảnh hưởng chéo ở một số kiến trúc | Muốn giữ traffic tại AZ, tối ưu lựa chọn fault domain/chi phí theo kiến trúc |
| Yêu cầu kiểm thử | Mức phân bố target, stickiness, khả năng phục vụ mỗi AZ | Tài nguyên của từng AZ, client affinity, cross-zone và phí liên quan |

**Lưu ý quan trọng:** Không phát biểu “ALB không thể tắt cross-zone ở bất cứ đâu”. Tại **cấp ALB** cross-zone luôn bật, nhưng một **target group** có thể được cấu hình tắt cross-zone; các tính năng như stickiness và Lambda target có giới hạn khi tắt cross-zone ở target group. Để dự đoán routing thực tế, xem cả **ALB attributes lẫn target group attributes**.

### Ví dụ tại sao cross-zone có ích

Giả sử có hai AZ:

- Node ALB ở AZ A nhận 50% traffic, AZ A có **2 target**.
- Node ALB ở AZ B nhận 50% traffic, AZ B có **6 target**.

Nếu **không cross-zone**, hai target AZ A có thể gánh tải lớn hơn hẳn từng target AZ B. Nếu cross-zone bật, các node có thể phân phối đến toàn bộ healthy targets theo thuật toán phù hợp. Tuy vậy, **cross-zone không thay khả năng đủ capacity của một AZ khi AZ còn lại lỗi**.

### Target distribution không luôn cân bằng tuyệt đối

Số request tới mỗi target còn phụ thuộc:

- Thuật toán cân bằng tải được chọn (ALB hỗ trợ các thuật toán như round robin/least outstanding requests/weighted random theo cấu hình và hạn chế liên quan);
- phiên dài, thời gian xử lý request không đều;
- **sticky session** giữ người dùng trên cùng target;
- slow start, health check, deregistration và số healthy targets;
- traffic distribution đầu vào theo DNS/zone và chính sách routing của load balancer.

**Đừng dùng session stickiness để thay thiết kế lưu trạng thái đúng cách.** Session đăng nhập và giỏ hàng cần được lưu ở hệ thống chia sẻ thích hợp như DynamoDB/RDS/ElastiCache hoặc dùng token được bảo vệ, tránh mất phiên khi target bị thay.

## 5. Target group và health check

### 5.1. Health check của load balancer

Mỗi target group có cấu hình health check:

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Protocol** | HTTP | Cách kiểm tra target |
| **Port** | `traffic-port` hoặc cổng riêng | Cổng gửi health check |
| **Path** | `/health/ready` | Endpoint ứng dụng dùng để trả trạng thái sẵn sàng |
| **Matcher** | HTTP `200` | Mã phản hồi được chấp nhận theo cấu hình |
| **Interval** | 15–30 giây trong ví dụ | Chu kỳ thăm dò |
| **Timeout** | Phù hợp latency health endpoint | Thời gian chờ mỗi lần |
| **Healthy threshold** | Nhiều lần liên tiếp thành công | Ngưỡng đánh dấu healthy |
| **Unhealthy threshold** | Nhiều lần liên tiếp thất bại | Ngưỡng đánh dấu unhealthy |

Ví dụ với ứng dụng Java/Spring Boot, `/health/ready` nên phản ánh liệu instance **đã khởi tạo xong và có thể phục vụ request**. Đừng để endpoint trả 200 ngay khi process vừa chạy nhưng migration/config vẫn chưa hoàn tất.

### 5.2. Liveness, readiness và dependency

**Liveness:** tiến trình còn sống/không bế tắc nghiêm trọng?

**Readiness:** instance có thể nhận request mới hay chưa?

Ví dụ backend đang khởi động cần 90 giây tải cấu hình, warm cache và mở kết nối database. Dùng **readiness** cho target group để ALB chưa gửi traffic khi ứng dụng chưa sẵn sàng; tránh thay instance liên tục trong thời gian boot.

**Cân bằng:** Nếu readiness phụ thuộc quá chặt vào một dịch vụ ngoài có thể gián đoạn tạm thời (chẳng hạn một API thanh toán), tất cả target cùng báo unhealthy và bị thay hàng loạt dù lỗi không nằm ở EC2. Chọn tiêu chí readiness/liveness theo mức ảnh hưởng thật và thiết kế retry/circuit breaker.

### 5.3. Các trạng thái target cần đọc

Khi kiểm tra target health thường gặp các trạng thái như:

- **initial:** đang đăng ký/đợi kết quả health check.
- **healthy:** đã đạt điều kiện health check.
- **unhealthy:** không đạt điều kiện; cần xem reason code và response thực.
- **draining:** đang ngừng nhận yêu cầu mới theo quá trình deregistration.
- **unused:** target không được dùng do cấu hình/điều kiện liên quan; xem lý do chi tiết.

**Đừng chỉ xem số EC2 ở trạng thái `running`.** Một EC2 đang chạy nhưng ứng dụng bị lỗi, SG chặn port hoặc health endpoint trả 503 sẽ **không** được xem như backend sẵn sàng.

### 5.4. Nếu tất cả target đều unhealthy

Không nên giả định rằng load balancer luôn chặn toàn bộ lưu lượng đến target unhealthy. **ALB có cơ chế fail-open** trong một số tình huống khi toàn bộ targets trong các AZ được bật đều không khỏe: nó có thể vẫn chuyển yêu cầu đến các target đó. Đây không phải giải pháp HA; cần giám sát **HealthyHostCount = 0**, target error, app error và khắc phục nguyên nhân nhanh.

## 6. Auto Scaling group quản lý vòng đời EC2 ra sao?

**Amazon EC2 Auto Scaling group (ASG)** là nhóm EC2 được quản lý theo cấu hình khởi tạo và capacity mong muốn. Trong một kiến trúc nhiều AZ, ASG thường gắn nhiều subnet tương ứng để AWS có thể cố phân bố nhóm instance qua các AZ.

### 6.1. Launch template

**Launch template** mô tả cách tạo một instance:

- AMI và architecture phù hợp;
- instance type hoặc kết hợp loại máy;
- IAM instance profile/role;
- security groups và cấu hình networking phù hợp;
- EBS root/data mapping và mã hóa khi dùng;
- user data/bootstrap để cài ứng dụng, đọc secret bằng cơ chế an toàn;
- tags, metadata security (ưu tiên IMDSv2 theo bối cảnh), monitoring.

**Lỗi phổ biến:** launch template tạo EC2 bình thường nhưng **không cài hoặc không khởi chạy ứng dụng**. ASG sẽ tiếp tục cho ra EC2 `running`, còn target group sẽ báo unhealthy.

### 6.2. Min, desired, max capacity

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **MinSize** | Mức capacity tối thiểu ASG cố duy trì | 2 |
| **DesiredCapacity** | Mục tiêu số lượng instance hiện tại khi dùng đơn vị instance | 4 |
| **MaxSize** | Trần ASG được phép tăng đến theo cấu hình | 10 |

Nếu traffic tăng, một scaling policy có thể điều chỉnh desired từ 4 lên 6; ASG tạo thêm instance nếu quota/capacity cho phép. Khi traffic giảm, desired có thể hạ và ASG chọn instance để terminate theo chính sách của nhóm.

**DesiredCapacity không phải số target healthy đảm bảo.** Instance có thể ở `Pending`, `InService`, `Terminating`, health check chưa đạt, hoặc bị giới hạn do capacity shortage.

### 6.3. Phân bố và AZ rebalancing

ASG cố giữ số instance cân bằng qua các AZ được chỉ định, và có tiến trình **AZRebalance** để điều chỉnh phân bố khi cần. Nhưng:

- ASG chỉ có thể chọn AZ/subnet đã được cấu hình và có khả năng khởi tạo tài nguyên;
- mất một AZ có thể khiến khả năng phục vụ tạm thời giảm;
- AZ rebalancing không thay yêu cầu dự phòng capacity trong AZ còn lại;
- policies về termination, lifecycle hooks và các lỗi cấp phát có thể ảnh hưởng thời gian tái cân bằng.

### 6.4. Khi nào ASG thay instance lỗi?

ASG kiểm tra trạng thái instance qua các nguồn được hỗ trợ. Với **mặc định**, ASG dùng **EC2 health checks** và các tín hiệu hỗ trợ liên quan, **không tự động thay instance chỉ vì target group báo unhealthy** trừ khi tích hợp **ELB health checks** được bật.

Khi **HealthCheckType = ELB** và ASG gắn target group, Auto Scaling có thể đánh dấu và thay EC2 mà ELB xem là unhealthy. Nếu nhóm gắn nhiều target groups, việc một target group coi instance unhealthy cũng có thể dẫn đến quyết định thay theo cơ chế health check được cấu hình.

**Quan trọng:** Health check của ALB quyết định **traffic đến target**; ELB health checks của ASG tác động đến **quyết định thay EC2**. Hai hành vi liên quan, không đồng nhất.

## 7. Liên kết ASG, target group và health checks

Để tích hợp:

1. Tạo ALB có listener và target group phù hợp (ví dụ `instance` target group, HTTP/8080).
2. Tạo launch template bảo đảm EC2 có ứng dụng/health endpoint.
3. Tạo ASG với subnets thuộc ít nhất hai AZ, `MinSize`, `DesiredCapacity`, `MaxSize`.
4. **Attach target group ARN** cho ASG; ASG tự đăng ký instance mới vào target group và deregister khi scale in/terminate.
5. Bật **ELB health checks** ở ASG nếu muốn target health ảnh hưởng việc thay EC2, đồng thời đặt **health check grace period** đủ để ứng dụng hoàn tất bootstrap.
6. Thiết lập dynamic/scheduled scaling policy và kiểm thử cả tăng tải lẫn thay instance lỗi.

~~~mermaid
sequenceDiagram
    participant P as Scaling policy / CloudWatch
    participant A as EC2 Auto Scaling
    participant E as EC2 instance
    participant T as ALB target group
    participant U as Khách hàng
    P->>A: Tăng DesiredCapacity
    A->>E: Launch instance bằng launch template
    A->>T: Đăng ký target mới
    T->>E: HTTP health check /health/ready
    alt Healthy
      T-->>A: Target healthy
      U->>T: Request qua ALB
      T->>E: Chuyển request
    else Unhealthy sau khi hết grace period
      T-->>A: Unhealthy (nếu ASG dùng ELB health checks)
      A->>E: Thay instance theo lifecycle
    end
    P->>A: Giảm DesiredCapacity khi phù hợp
    A->>T: Deregister target
    T-->>E: Draining trong giới hạn thiết lập
    A->>E: Terminate sau tiến trình liên quan
~~~

Sơ đồ thể hiện tiến trình logic; thời điểm chính xác phụ thuộc health checks, hook, thời gian warmup/deregistration và chính sách của ASG.

### Health check grace period khác instance warmup

**Health check grace period** của ASG: thời gian bảo vệ instance mới khỏi một số quyết định thay do health check khi ứng dụng còn khởi tạo. Quá ngắn gây vòng lặp tạo/xóa; quá dài khiến việc thay instance thực sự lỗi chậm đi. **Console tạo ASG có default khác CLI/SDK**, nên cần **đặt giá trị tường minh** theo thời gian bootstrap đo được.

**Default instance warmup:** khoảng thời gian để policy scaling coi một instance mới đã đóng góp đầy đủ vào tín hiệu tải. Nó giúp tránh **scale out lặp quá mức** trong lúc instance mới chưa xử lý tải và đo metric chưa ổn định.

**Target group health threshold:** điều kiện ALB bắt đầu/tiếp tục định tuyến tới một target.

Ba thông số cần đồng bộ theo lifecycle, nhưng **không phải cùng một bộ đếm**. Ví dụ ứng dụng boot 80 giây, health check cần 2 chu kỳ 15 giây, warmup cần thêm thời gian tải cache: hãy đo thời gian thực để chọn grace period, interval và warmup hợp lý.

### Deregistration delay và graceful shutdown

Khi scale in, việc bỏ target khỏi nhóm nên cho phép request đang thực thi hoàn tất trong giới hạn định nghĩa:

- **Target deregistration delay** kiểm soát khoảng thời gian target ở trạng thái draining trước khi hoàn tất deregistration.
- Ứng dụng cần xử lý **SIGTERM/shutdown**, ngừng nhận request mới, hoàn tất request đang chạy hoặc trả lỗi có kiểm soát.
- **ASG lifecycle hooks** có thể cung cấp bước chờ cho deploy/decommission/workflow bên ngoài; cần quản lý timeout và heartbeat theo tài liệu.
- Tránh terminate instance đang giữ job không thể lặp lại. Chuyển job nền sang SQS/Step Functions và thiết kế **idempotency/retry** khi phù hợp.

**Scale in đúng chưa đủ nếu ứng dụng giữ state trong RAM hoặc chỉ trên một EBS volume.** Nếu người dùng mất session/giỏ hàng hoặc dữ liệu khi instance bị thay, kiến trúc dữ liệu cần điều chỉnh.

## 8. Lựa chọn scaling policy theo tín hiệu phù hợp

### 8.1. Target tracking scaling

**Target tracking** đặt một mục tiêu metric, ASG điều chỉnh capacity để tiến về mức đó, tương tự bộ điều khiển tải.

| Metric | Hợp lý khi | Rủi ro nếu dùng thiếu kiểm chứng |
| --- | --- | --- |
| **ASGAverageCPUUtilization** | CPU tăng gần tỷ lệ thuận với số request/work | CPU thấp nhưng ứng dụng nghẽn database, network hoặc I/O |
| **ALBRequestCountPerTarget** | Request là đơn vị gần đúng cho tải của từng web instance trong target group | Request khác nhau về độ nặng, long polling/websocket hoặc luồng không qua ALB |
| **Custom metric** như queue backlog per instance | Worker bất đồng bộ xử lý job từ SQS | Thiếu metric, dữ liệu không đo đúng capacity, độ trễ giám sát |

Ví dụ web API mà mỗi instance phục vụ gần giống nhau và traffic qua ALB, `ALBRequestCountPerTarget` có thể phù hợp hơn CPU nếu CPU không phản ánh yêu cầu. Nhưng mục tiêu metric cần dựa trên **benchmark SLO**, không đoán tùy ý.

### 8.2. Step scaling

Dùng **CloudWatch alarm** để thêm/bớt capacity theo các mức ngưỡng, ví dụ CPU vượt 70% trong nhiều chu kỳ thì tăng 2 instance, trên 85% thì tăng thêm nhiều hơn tùy policy. Phù hợp khi cần kiểm soát phản ứng theo từng mức, nhưng cần cẩn thận cooldown/warmup và dao động (flapping).

### 8.3. Scheduled scaling

Nếu tải có lịch đáng tin, ví dụ flash sale lúc 20:00 mỗi ngày, cấu hình desired/min capacity tăng **trước thời điểm bắt đầu** để có sẵn backend khi khách truy cập. Sau khung giờ, có thể giảm capacity theo lịch nếu mô hình tải cho phép.

### 8.4. Predictive scaling

AWS có chế độ dự báo dựa trên lịch sử tải ở các điều kiện hỗ trợ để chuẩn bị năng lực trước khi nhu cầu đến. Cần dữ liệu lịch sử phù hợp và kiểm tra dự báo so với hành vi thực; không nên mặc định mô hình sẽ dự đoán đúng các chiến dịch bất thường.

### 8.5. Không dùng scale out để chữa mọi lỗi

Nếu CPU không cao nhưng latency tăng do database khóa bảng hoặc connection pool cạn, việc tăng EC2 có thể khiến DB bị tấn công bởi **nhiều kết nối hơn**, làm lỗi nghiêm trọng hơn. Trước khi tăng max capacity, cần xác nhận **điểm nghẽn thực** bằng metric của ALB, ứng dụng, DB, queue và storage.

## 9. Tính capacity có xét mất một AZ

Giả sử API được thử tải và mỗi EC2 xử lý bền vững **100 request/giây** trong điều kiện đáp ứng p95 latency mục tiêu. Traffic cao điểm cần phục vụ là **300 request/giây**.

### 9.1. Chỉ xét tải bình thường

Lý thuyết tối thiểu:

\[
N_{\text{normal}} = \left\lceil \frac{300}{100} \right\rceil = 3\ \text{instances}
\]

Nhưng 3 instance không đủ headroom cho peak đột biến, deploy, rolling replacement hay AZ failure. Nếu phân đều 4 instance ở hai AZ thì có 2 mỗi AZ, khi một AZ ngừng hoạt động sẽ chỉ còn 2 × 100 = 200 request/giây, thấp hơn yêu cầu 300.

### 9.2. Thiết kế duy trì tải đỉnh khi mất một AZ

Muốn sau khi mất một AZ vẫn phục vụ **300 request/giây** với **ít nhất 25% headroom về khả năng xử lý**, mỗi AZ còn lại cần khoảng:

\[
N_{\text{surviving AZ}}
= \left\lceil \frac{300 \times 1.25}{100} \right\rceil
= 4
\]

Khi bố trí **4 instance/AZ**, tổng capacity bình thường là **8 instance**. Nếu AZ A bị lỗi và còn AZ B với 4 instance, AZ B có năng lực lý thuyết khoảng 400 request/giây, cao hơn mục tiêu 300.

**Đây là ví dụ capacity planning**, không phải lời đảm bảo. Instance có thể có hiệu năng không đều, traffic phân bố theo kết nối, database là nút nghẽn hoặc một AZ lỗi khiến cross-zone/data transfer thay đổi. Cần kiểm thử thực ở mức request và tài nguyên dùng chung.

### 9.3. Chọn min/desired/max như thế nào?

Ví dụ chính sách có thể đặt:

- **Min/Desired = 8** nếu bắt buộc chịu được một AZ mất ngay trong giờ cao điểm mà không chờ scale out.
- **Max = 12** để có thêm dư địa cho tăng tải hoặc cân bằng sau lỗi, miễn quotas và ngân sách cho phép.
- Dùng **target tracking** cho biến động bình thường, nhưng không tự giảm dưới mức dự phòng cứng nếu đó là SLO được yêu cầu.
- Với traffic thấp hơn phần lớn thời gian, có thể dùng baseline thấp và dựa vào scale out, nhưng phải chấp nhận **khoảng thời gian suy giảm** khi một AZ lỗi trong lúc chưa kịp tạo thêm EC2.

**Điểm cần quyết định rõ:** “chịu lỗi AZ không downtime” khác với “có thể mở rộng phục hồi trong vài phút”. Hai mục tiêu này dẫn tới **baseline capacity/chi phí rất khác nhau**.

### 9.4. Quy tắc Little’s Law và concurrent requests

Với API HTTP, concurrency xấp xỉ:

\[
\text{Concurrent requests} \approx \text{RPS}\times\text{Latency (giây)}
\]

Ví dụ 300 RPS với thời gian phục vụ trung bình 0,2 giây tương ứng khoảng 60 yêu cầu đồng thời; con số này chưa gồm kết nối chờ, long polling và tải không cân bằng. Nên đo p95/p99 latency, concurrency, số connection và queue của ứng dụng để xác định capacity thực.

## 10. Những vấn đề ứng dụng phải giải quyết khi scale qua nhiều AZ

### 10.1. Không đặt session chỉ ở RAM một EC2

Một người dùng đăng nhập qua EC2 A, request tiếp theo có thể đến EC2 B. Nếu session chỉ ở RAM A, người dùng có thể bị đăng xuất. Với ASG, A còn có thể bị terminate trong scale in.

Phương án:

- Sử dụng session có thể xác minh an toàn bằng token phù hợp;
- lưu session/state ở Redis/ElastiCache, DynamoDB hoặc database được quản lý theo yêu cầu;
- chỉ dùng stickiness khi có lý do và biết rủi ro khi target biến mất.

### 10.2. File và dữ liệu không nên sống duy nhất ở một volume EBS

EBS volume gắn AZ, instance store có tính tạm thời. Nếu người dùng upload ảnh vào thư mục local trên EC2 A, request tới EC2 B có thể không thấy file; khi A bị thay, file có thể không được phục hồi đúng.

Thiết kế phổ biến: lưu object trên **S3**, file dùng chung cần NFS thì khảo sát **EFS**, dữ liệu quan hệ đặt ở **RDS/Aurora** hoặc cơ chế HA phù hợp. Giảm trạng thái local giúp ASG thay EC2 an toàn.

### 10.3. Database cần cơ chế sẵn sàng riêng

ASG có thể tạo thêm 10 EC2 nhưng không biến một database single-AZ thành Multi-AZ. Cần:

- DB instance/cluster có cơ chế failover, Multi-AZ hoặc replication theo RPO/RTO;
- connection pooling, retry/backoff, timeout và xử lý reconnect sau DB failover;
- chiến lược backup/restore được thử nghiệm;
- giới hạn connection nhằm tránh scale backend làm cạn DB.

### 10.4. Công việc dài và queue

API nên trả kết quả nhanh nếu có thể, còn việc gửi email/tạo PDF/resize ảnh có thể đưa vào **Amazon SQS**, sau đó worker ECS/EC2/Lambda xử lý. Nếu worker chạy trong ASG, scale theo **queue backlog per instance** và thời gian xử lý, không nhất thiết theo ALB RPS. Thiết kế retry, DLQ và idempotency để không mất/nhân đôi công việc khi instance bị thay.

### 10.5. Deployment đồng thời trên nhiều AZ

Rolling deployment hoặc instance refresh có thể thay một phần EC2 trong ASG. Nếu mỗi phiên bản ứng dụng chỉ tương thích một schema DB nhất định, quá trình nhiều phiên bản cùng phục vụ traffic có thể lỗi dù health check xanh. Cần thiết kế backward-compatible schema/API, readiness, graceful draining và rollout/canary theo yêu cầu.

## 11. Thực hành cấu hình ALB + EC2 Auto Scaling trên AWS Console

> **Môi trường lab:** Dùng VPC riêng và hai AZ đã được cấp quyền. Các ID/tên bên dưới là minh họa, không chạy nguyên văn trên production. Tạo EC2, ALB, NAT, logging và RDS có thể phát sinh phí; đặt AWS Budget trước và dọn tài nguyên lab theo quy trình của nhóm.

### Bước 1 — Chuẩn bị VPC, subnet và security group

Giả sử Region `ap-southeast-1`, có:

| Khu vực | Subnet | Vai trò |
| --- | --- | --- |
| AZ A | `public-a` | Node ALB internet-facing |
| AZ B | `public-b` | Node ALB internet-facing |
| AZ A | `private-app-a` | EC2 trong ASG |
| AZ B | `private-app-b` | EC2 trong ASG |

- Public subnet có route phù hợp đến Internet Gateway.
- Private subnets không nhận kết nối trực tiếp từ Internet.
- `sg-alb`: inbound HTTPS/443 từ client được phép; outbound tới backend TCP/8080.
- `sg-app`: inbound TCP/8080 từ **`sg-alb`**, outbound tới tài nguyên thực sự cần.
- EC2 có IAM instance profile để đọc cấu hình/log, không nhúng access key vào user data.

Nếu user data cần tải package từ Internet, private subnet cần **outbound path** phù hợp (NAT/VPC endpoints hoặc cách đóng gói AMI). Một EC2 không bootstrap được do thiếu network vẫn có thể đạt trạng thái `running`.

### Bước 2 — Tạo launch template

Dùng AMI/test application có HTTP listener trên **8080** và endpoint **`/health/ready`** trả 200 khi ứng dụng sẵn sàng.

Trong EC2 Console → **Launch Templates**, tạo template, chọn instance type/AMI, SG backend, IAM role, EBS root encryption và cấu hình metadata phù hợp.

**Kiểm chứng trước:** Tạo tạm một EC2 lab bằng template và thử `curl http://localhost:8080/health/ready`, kiểm tra log. Nếu bootstrap chưa đúng, đừng xây ASG rồi mới debug hàng loạt máy.

### Bước 3 — Tạo target group

Trong EC2/ELB Console → **Target Groups**:

- Loại **Instances**;
- VPC đúng, giao thức **HTTP**, port **8080**;
- Health check path `/health/ready`, matcher `200`;
- Đặt interval, timeout và thresholds theo thời gian boot/response thực.

Ở bài toán ASG, **để ASG quản lý đăng ký target**. Tránh duy trì danh sách instance target thủ công sau khi group đã tự quản lý lifecycle.

### Bước 4 — Tạo ALB

Trong **Load Balancers**:

- Type = **Application Load Balancer**.
- Scheme = **internet-facing** (hoặc internal nếu chỉ phục vụ VPC/on-premises).
- Chọn **ít nhất hai public subnets** khác AZ.
- Gắn `sg-alb`.
- Listener **HTTPS/443**, chứng chỉ ACM phù hợp; default action forward đến target group đã tạo.
- Tùy ứng dụng: HTTP/80 có thể redirect HTTPS; WAF, access logs và các listener routing rules.

### Bước 5 — Tạo ASG và tích hợp target group

Tại **Auto Scaling Groups**:

- Chọn launch template;
- Chọn **private-app-a** và **private-app-b**;
- Thiết lập `MinSize=2`, `DesiredCapacity=2`, `MaxSize=6` cho lab ban đầu;
- Liên kết đúng **target group ARN**;
- Cấu hình **ELB health checks** và grace period đủ cho bootstrap;
- Đặt default instance warmup/termination protection theo mục đích;
- Gắn tags và scaling policy.

Khi group tạo xong, kiểm tra EC2 ở **cả hai AZ**, target chuyển từ `initial` sang `healthy` và request đi qua ALB.

### Bước 6 — Tạo scaling policy

Ví dụ cho lab: **target tracking ASGAverageCPUUtilization = 55%**. Mức 55% không phải công thức chung; nếu app bị giới hạn bởi I/O/DB, CPU sẽ không đại diện đúng tải. Có thể chuyển sang ALBRequestCountPerTarget sau khi đo ứng dụng.

### Bước 7 — Kiểm thử có kiểm soát

- Gọi `https://<dns-cua-alb>/health/ready` qua client lab; ghi kết quả và latency.
- Tạo tải bằng công cụ kiểm thử ứng dụng trong giới hạn được cấp phép; quan sát metric và số instance tăng.
- Làm một instance lab trở nên unhealthy có kiểm soát hoặc thực hiện quy trình thử thay instance, xem ALB ngừng gửi traffic và ASG thay khi ELB health checks bật.
- Kiểm tra giảm tải/scale in, deregistration và request đang xử lý.
- Diễn tập mất một AZ theo phương pháp đã được cho phép và xem có đủ capacity/SLO không; không cố làm gián đoạn hạ tầng AWS thật.

**Kỳ vọng:** Hiểu rõ health check, số instance, độ trễ scale out và khả năng phục vụ khi tài nguyên lỗi, thay vì chỉ nhìn dashboard thấy “green”.

## 12. AWS CLI: kiểm tra cấu hình và tác động an toàn trong lab

Các ví dụ dưới dùng AWS CLI với `--profile lab`. Thay tên, ARN, ID, Region bằng tài nguyên lab thật trước khi chạy. Không sao chép ví dụ vào production nếu chưa review.

### 12.1. Đọc danh tính, ALB và target groups

~~~bash
aws sts get-caller-identity --profile lab

aws elbv2 describe-load-balancers \
  --names shop-alb \
  --region ap-southeast-1 --profile lab

aws elbv2 describe-target-groups \
  --names shop-web-tg \
  --region ap-southeast-1 --profile lab
~~~

Chú ý thuộc tính `Scheme`, `Type`, các subnets/AZ của ALB, target type/protocol/port và health check configuration.

### 12.2. Xem target health cụ thể

~~~bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/shop-web-tg/0123456789abcdef \
  --region ap-southeast-1 --profile lab
~~~

Kết quả chứa target ID, cổng, health state, reason và description khi có. Ví dụ target `unhealthy` có reason liên quan timeout: kiểm tra health path, SG, ứng dụng có listen cổng và phản hồi đủ nhanh.

### 12.3. Xem Auto Scaling group, scaling policies và activities

~~~bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names shop-web-asg \
  --region ap-southeast-1 --profile lab

aws autoscaling describe-policies \
  --auto-scaling-group-name shop-web-asg \
  --region ap-southeast-1 --profile lab

aws autoscaling describe-scaling-activities \
  --auto-scaling-group-name shop-web-asg \
  --max-items 20 \
  --region ap-southeast-1 --profile lab
~~~

Đọc `MinSize`, `MaxSize`, `DesiredCapacity`, `VPCZoneIdentifier`, `TargetGroupARNs`, `HealthCheckType`, `HealthCheckGracePeriod`, `Instances[].LifecycleState` và trạng thái scaling activities. Đây là cách nhanh để tách lỗi **không tạo được EC2** với lỗi **EC2 tạo được nhưng target unhealthy**.

### 12.4. Liên kết target group với ASG (chỉ khi lab đang thiếu)

~~~bash
aws autoscaling attach-load-balancer-target-groups \
  --auto-scaling-group-name shop-web-asg \
  --target-group-arns arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/shop-web-tg/0123456789abcdef \
  --region ap-southeast-1 --profile lab
~~~

Sau đó xác minh trạng thái attachment, target registration và target health. **Không attach nhầm** target group của môi trường khác hoặc chuyển traffic production không theo quy trình.

### 12.5. Bật ELB health checks và đặt grace period (chỉ lab)

~~~bash
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name shop-web-asg \
  --health-check-type ELB \
  --health-check-grace-period 180 \
  --region ap-southeast-1 --profile lab
~~~

Giá trị **180 giây chỉ minh họa**; đo từ khi instance `InService` đến lúc app readiness ổn định, sau đó cân nhắc health thresholds và bootstrap. Nếu grace period quá dài, instance lỗi thực sẽ bị thay chậm. Nếu quá ngắn, ASG có thể thay máy đang khởi tạo hợp lệ.

### 12.6. Đặt target tracking CPU (chỉ lab)

Với ASG đã có metric và role/permissions phù hợp:

~~~bash
aws autoscaling put-scaling-policy \
  --auto-scaling-group-name shop-web-asg \
  --policy-name cpu-target-55 \
  --policy-type TargetTrackingScaling \
  --target-tracking-configuration '{"PredefinedMetricSpecification":{"PredefinedMetricType":"ASGAverageCPUUtilization"},"TargetValue":55.0}' \
  --region ap-southeast-1 --profile lab
~~~

Câu lệnh trên dùng cách trích dẫn JSON của **shell Bash**. Trên Windows PowerShell, quoting khác; có thể đặt cùng JSON vào file và dùng `--target-tracking-configuration file://cpu-target.json` để tránh lỗi escape.

Đối với policy **ALBRequestCountPerTarget**, cần đưa đúng `ResourceLabel` kết hợp **full name** của ALB và target group theo định dạng AWS yêu cầu. Không tự ghép ARN theo cảm tính; lấy full name từ API/Console và so với tài liệu.

### 12.7. Kiểm tra chính sách phân bổ AZ

~~~bash
aws ec2 describe-subnets \
  --subnet-ids subnet-0123456789abcdef0 subnet-0fedcba9876543210 \
  --query 'Subnets[].{SubnetId:SubnetId,AZ:AvailabilityZone,AZId:AvailabilityZoneId,VpcId:VpcId}' \
  --region ap-southeast-1 --profile lab
~~~

Với kiến trúc nhiều account, **tên AZ như `ap-southeast-1a` không nhất thiết trỏ cùng physical AZ giữa các account**; nếu phải đối chiếu vật lý, xem **AvailabilityZoneId**.

## 13. Giám sát hiệu quả: ALB, ASG và ứng dụng

### 13.1. Các metrics đáng theo dõi

| Nhóm | CloudWatch metric hoặc chỉ số | Ý nghĩa / cảnh báo |
| --- | --- | --- |
| **ALB** | `RequestCount` | Số yêu cầu đi qua ALB; hiểu traffic trends |
| **ALB target group** | `HealthyHostCount`, `UnHealthyHostCount` | Phân bố backend sẵn sàng; báo động khi số healthy nhỏ hoặc về 0 |
| **ALB** | `TargetResponseTime` | Độ trễ backend, theo dõi p95/p99 khi có dữ liệu phù hợp |
| **ALB** | `HTTPCode_ELB_5XX_Count`, `HTTPCode_Target_5XX_Count` | Phân biệt lỗi do ALB phát sinh và backend trả về |
| **ALB** | `TargetConnectionErrorCount` | Lỗi ALB không thiết lập được kết nối đến target |
| **ALB** | `RequestCountPerTarget` | Quan sát tải trung bình theo target group và thiết kế target tracking |
| **ASG** | `GroupDesiredCapacity`, `GroupInServiceInstances`, `GroupPendingInstances` | Capacity mục tiêu và khả dụng; cần bật ASG group metrics collection theo cấu hình |
| **EC2** | `CPUUtilization`, status checks, network, EBS metrics | Phân biệt CPU, I/O, instance error hoặc băng thông |
| **Ứng dụng** | p95/p99 latency, errors, queue depth, DB pool, throughput | Kiểm tra trải nghiệm và nút nghẽn nghiệp vụ thực |

CloudWatch metric cho ASG có thể cần bật **group metrics collection**; không giả định mọi chỉ số đã được gửi với độ phân giải và retention mong muốn.

### 13.2. Những cảnh báo nên có

- **HealthyHostCount thấp** so với mức dự phòng; đặc biệt tất cả healthy targets bằng 0.
- **ALB TargetResponseTime p95/p99** vượt SLO trong nhiều chu kỳ.
- **5xx/TargetConnectionError** tăng đồng thời với scale event hoặc deploy.
- **ASG DesiredCapacity ≠ InServiceInstances** kéo dài bất thường, scaling activities thất bại.
- **ASG gần MaxSize** nhưng CPU/RPS/queue tiếp tục tăng.
- **DB connection/CPU** hoặc queue lag cho thấy scale-out backend gây áp lực lên downstream.
- **Chi phí EC2/ALB/NAT** tăng nhanh so với budget.

Bảo đảm có **application logs, ALB access logs** khi yêu cầu kiểm toán/điều tra, **CloudTrail** để theo dõi thay đổi SG, route, launch template và scaling policy. Không để log chứa secret hoặc dữ liệu cá nhân không cần thiết, đặt retention phù hợp.

### 13.3. “Đã scale out” không phải SLO

ASG có thể tăng từ 2 lên 6 EC2, nhưng khách hàng vẫn lỗi vì:

- một nửa target chưa healthy;
- database hết connections;
- ứng dụng đẩy traffic vào dependency lỗi;
- TLS certificate hết hạn;
- state local mất khi thay instance.

Do đó nên đặt mục tiêu theo **người dùng** (availability, p95 latency, error rate) và dùng ASG/ALB metrics để giải thích nguyên nhân.

## 14. Các lỗi hay gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra theo thứ tự |
| --- | --- | --- |
| **ALB trả 503** | Không có target phù hợp/đăng ký, target group không phục vụ hoặc lỗi route listener | Listener/default action → target groups → registered targets → health |
| **ALB trả 502** | Target đóng kết nối/sai protocol/TLS backend hoặc trả phản hồi không hợp lệ | Target app logs, listener/target protocol, keepalive/timeouts |
| **ALB trả 504** | Timeout kết nối/chờ phản hồi từ backend | Backend latency, SG/NACL, overload, DB, timeout settings |
| **EC2 chạy nhưng target unhealthy** | Health path sai, app chưa listen, SG chặn port, matcher không khớp | `describe-target-health`, local `curl`, SG app từ ALB SG |
| **ASG liên tục tạo/xóa EC2** | ELB health check grace quá ngắn, bootstrap lỗi, image lỗi, dependency readiness quá chặt | ASG activities, user data/cloud-init, app logs, health thresholds |
| **ASG không tăng dù traffic lớn** | Chưa có policy, metric không tăng, max size đã chạm, CloudWatch thiếu dữ liệu hoặc scaling activities lỗi | Scaling policy, alarms, desired/max, group metrics/activities |
| **ASG desired tăng nhưng InService không tăng** | EC2 capacity/Spot shortage, quota, launch template sai, subnet hết IP | Scaling activities, EC2 launch failures, subnet free IP, quotas |
| **Một AZ có traffic thấp/không có backend** | ASG subnet list thiếu AZ, target placement/health lỗi hoặc cross-zone TG cấu hình khác | ALB enabled AZ, ASG VPCZoneIdentifier, TG cross-zone, target AZ |
| **Scale in làm rớt request đang chạy** | Deregistration delay ngắn, app không graceful shutdown, job giữ state | TG attributes, lifecycle hooks, application shutdown |
| **Tăng instance không cải thiện latency** | DB/storage/cache/queue là bottleneck | DB metrics, connections, CPU/I/O, app traces, request pattern |
| **User bị log out khi scale hoặc instance lỗi** | Session trên RAM/local disk, sticky session không đủ | Session storage, token, shared state, target lifetime |
| **Chỉ lúc chuyển AZ mới lỗi** | SG/NACL/routes khác nhau, capacity B thiếu, dependency single-AZ | So từng subnet/AZ, health, endpoint routes và failover |
| **ALB public không truy cập được** | Route IGW/public subnet sai, SG listener, DNS/TLS certificate | Subnets/IGW, SG ALB, listener 443, ACM, DNS |
| **Bỗng tăng chi phí** | Min/desired/max tăng, traffic/LB capacity, NAT cross-AZ, log retention | Cost Explorer theo tags, scaling history, pricing và tải thực |

### Quy trình điều tra ngắn

~~~text
1. Xác nhận FQDN, ALB, listener, target group, ASG, Region và thời điểm lỗi.
2. Kiểm tra client → ALB (DNS, HTTPS/TLS, HTTP status).
3. Kiểm tra target group (HealthyHostCount, từng target reason, backend app logs).
4. Kiểm tra ALB → backend (SG, port, VPC route, health path, NACL).
5. Kiểm tra ASG (Desired, InService, Pending, activities, launch template, AZ).
6. Xem CloudWatch CPU/RPS/latency/error, DB/queue và scaling policies.
7. Sửa một nguyên nhân rõ ràng, kiểm thử từ client thật và so metric trước/sau.
8. Kiểm tra scale in, lỗi một AZ và quyền truy cập ngoài phạm vi vẫn bị từ chối.
~~~

**Nếu nghi lỗi route/security:** sử dụng **VPC Reachability Analyzer** để phân tích đường đi theo cấu hình AWS; bổ sung **VPC Flow Logs** và thử kết nối thực. Reachability Analyzer là phân tích tĩnh, không chứng minh listener/TLS/ứng dụng đã khỏe.

## 15. Bảo mật và quản trị triển khai

**IAM, VPC và TLS** cần được phối hợp với scaling:

1. **Instance profile/role:** EC2 được tạo từ launch template nên dùng IAM role có quyền tối thiểu để đọc S3/Secrets Manager/CloudWatch hoặc truy cập tài nguyên cần thiết; không nhúng static access key vào AMI/user data.
2. **Security groups:** Backend chỉ nhận app port từ ALB SG; database chỉ nhận từ app SG. Không mở SSH/22 ra toàn Internet để debug; ưu tiên **AWS Systems Manager Session Manager** khi môi trường hỗ trợ.
3. **Private subnets:** Không cấp public IP cho EC2 backend nếu không cần. Cấu hình egress đúng dịch vụ; NAT/VPC endpoint theo thiết kế.
4. **HTTPS/WAF:** Dùng HTTPS/ACM ở public ALB, cân nhắc AWS WAF, rate limiting hoặc CloudFront theo rủi ro và nhu cầu.
5. **Mã hóa dữ liệu:** EBS encrypted, S3 encryption, RDS encryption/KMS, TLS tới DB khi cần; quyền truy cập dữ liệu không phụ thuộc vào việc ALB đã cân bằng tải.
6. **Infrastructure as Code:** Quản lý ALB, target groups, launch template, ASG, SG, policies và alerts bằng CloudFormation/CDK/Terraform hoặc công cụ nhóm đang dùng.
7. **Audit:** Bật CloudTrail, kiểm tra thay đổi launch template versions, scaling policies, listener rules, target groups và SG; cô lập quyền quản trị khác với quyền runtime.

Một ALB public chỉ nên cho phép **những đường/port public mà ứng dụng chủ đích công khai**. Các endpoint vận hành nội bộ, metric hoặc admin dashboard nên được đặt sau auth/mạng phù hợp, tránh vô tình expose qua listener rule.

## 16. Chi phí: Multi-AZ và tự động mở rộng phải có ngân sách

**Auto Scaling không đồng nghĩa tự động tiết kiệm tiền.** Nó cố duy trì hoặc thay capacity theo policy; nếu min quá cao, không scale in hoặc target metric không hợp lý, nhóm EC2 có thể chạy dư cả tháng.

### Những thành phần phải tính

| Khoản phí | Vì sao ảnh hưởng |
| --- | --- |
| **EC2 instances** | Số lượng giờ chạy, instance type, On-Demand/Spot/Savings Plans khi phù hợp |
| **EBS volumes/snapshots** | Mỗi instance có root/data volumes; snapshot và log retention có thể tăng |
| **ALB/NLB** | Phí thời gian hoạt động và đơn vị năng lực/xử lý theo loại LB |
| **Network transfer** | Dữ liệu ra Internet, truyền giữa AZ/Region và các đường endpoint/NAT theo biểu giá |
| **NAT Gateway / VPC endpoints** | Chi phí cố định/tính theo dung lượng tùy loại; thường bị bỏ sót ở nhiều AZ |
| **CloudWatch/logs/tracing** | Metrics, custom metrics, logs, alerts và lưu trữ |
| **RDS/ElastiCache/SQS** | Backend scale có thể làm tăng tài nguyên và request downstream |
| **Dự phòng cho lỗi một AZ** | Baseline cao hơn nếu phải duy trì SLO trước cả khi scale out |

**Chú ý cross-zone:** ALB có cách tính phí/cross-zone riêng theo dịch vụ; NLB khi bật cross-zone có thể phát sinh các loại phí truyền dữ liệu liên AZ theo chính sách hiện hành. Để dự toán chính xác, xem **AWS ELB pricing** theo loại và Region, không áp một quy tắc chung.

### Chiến lược tối ưu dựa trên dữ liệu

- Đặt **min/desired/max** có lý do dựa trên SLO và khả năng chấp nhận lỗi một AZ.
- Đo request/instance, CPU, p95 latency và thời gian bootstrap để tránh tăng size quá mức.
- Chọn instance type, loại mua và Spot phù hợp tính chịu gián đoạn của workload; phần năng lực tối thiểu cho web quan trọng thường cần xét tính tin cậy của nguồn capacity.
- Dùng scheduled scaling cho tải theo lịch và dynamic scaling cho phần dao động.
- Tối ưu health checks, warmup, graceful shutdown để giảm thời gian EC2 không phục vụ nhưng vẫn bị tính phí.
- Áp dụng **AWS Budgets**, **Cost Explorer**, tags `service`, `environment`, `owner` và alerts để phát hiện bất thường.

**Không tối ưu chi phí bằng cách giảm số AZ nếu ứng dụng bắt buộc phải chịu lỗi cấp AZ.** Cần so sánh chi phí với RTO/RPO và mức mất doanh thu khi outage.

## 17. Ba kịch bản kiến trúc để lựa chọn

### A. Website nhỏ có traffic đều, uptime vừa phải

**Yêu cầu giả định:** Trang thông tin nội bộ, lưu lượng thấp, một nhóm nhỏ vận hành, mức downtime cho bảo trì được chấp nhận.

**Khảo sát:** ALB + ASG ở hai AZ với min nhỏ, instance gp3, trạng thái tách khỏi EC2 và backup cơ bản. Nếu chính sách không đòi độ sẵn sàng quá cao, có thể chọn phương án đơn giản hơn sau khi đánh giá chi phí, nhưng không khẳng định một AZ là HA.

### B. API thương mại điện tử có campaign tăng tải đột biến

**Yêu cầu giả định:** HTTPS/REST, cao điểm nhiều lần bình thường, downtime làm mất đơn, database cần giao dịch ACID.

**Khảo sát:**

- ALB public qua ít nhất hai AZ, HTTPS/ACM, WAF nếu cần;
- ASG ở private subnets nhiều AZ, target tracking **ALBRequestCountPerTarget** hoặc CPU đã thử tải, kết hợp scheduled scaling trước campaign;
- RDS Multi-AZ, S3 cho ảnh/hóa đơn, SQS cho công việc nền; app stateless và quản lý DB pool;
- alarms HealthyHostCount, error rate, p95 latency, ASG capacity và DB connections;
- kiểm thử load, scale, AZ loss và phục hồi dữ liệu.

**Điểm cần tính:** số instance duy trì SLO khi một AZ lỗi; thời gian boot/warmup có thể quá chậm nếu chờ traffic tăng rồi mới scale.

### C. Hệ thống TCP với địa chỉ IP ổn định

**Yêu cầu giả định:** Khách hàng dùng giao thức TCP đặc biệt, hệ thống bên ngoài cần allowlist địa chỉ IP của LB.

**Khảo sát:** NLB với các AZ phù hợp, listener/target group TCP/TLS, kết hợp ASG EC2. Kiểm tra **cross-zone** (NLB mặc định tắt ở cấp LB), khả năng chịu lỗi khi một AZ thiếu healthy targets, cách phân bố kết nối và graceful shutdown. Kiểm thử TCP thực thay vì dùng health endpoint HTTP không tương thích nếu ứng dụng không cung cấp nó.

## 18. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Thiết kế kiến trúc hai AZ

**Đề bài:** API phục vụ người dùng qua `https://api.example.com`, backend Java trên EC2 cổng 8080, dùng PostgreSQL và lưu ảnh.

Hãy vẽ sơ đồ có:

- Route 53/ALB public, HTTPS listener/ACM;
- public subnets ở AZ A/B, private backend subnets ở AZ A/B;
- target group, health check `/health/ready`;
- ASG với launch template, min/desired/max và health-check grace period;
- RDS Multi-AZ, S3 và SQS nếu công việc nền có thể xử lý bất đồng bộ;
- CloudWatch alarms, IAM role, security groups và AWS Budgets.

Giải thích tại sao RDS Multi-AZ và storage của ứng dụng quan trọng dù đã có nhiều EC2.

### Bài tập 2 — Tính capacity chịu lỗi AZ

Ứng dụng qua ALB đạt **75 RPS/EC2** khi vẫn đáp ứng p95 latency. Mục tiêu traffic cao điểm **225 RPS** và sau khi mất một AZ vẫn muốn dư **ít nhất 20%** năng lực.

1. Tính số instance tối thiểu cần còn hoạt động trong AZ sống sót: `ceil(225 × 1,20 / 75) = 4`.
2. Nếu có hai AZ và muốn đủ capacity **ngay lập tức**, cần bố trí ít nhất **4 instance/AZ**, tức 8 instance lúc bình thường.
3. Đề xuất min/desired/max hợp lý, nêu đánh đổi chi phí.
4. Nếu chấp nhận thời gian suy giảm trước khi scale out, bạn có thể giảm baseline thế nào và cần kiểm thử gì?

### Bài tập 3 — Mất instance nhưng ASG không thay

ALB target group đánh dấu instance `unhealthy` vì health endpoint trả HTTP 500. EC2 vẫn ở trạng thái `running` và ASG giữ nguyên instance sau một thời gian dài.

**Yêu cầu:** Kiểm tra `HealthCheckType` của ASG, việc attach target group, grace period, target health reasons, log ứng dụng, scaling activities. Đề xuất thay đổi tối thiểu để ASG có thể thay instance mà ALB xác định unhealthy.

### Bài tập 4 — Scale out nhưng response chậm hơn

ASG tăng từ 2 lên 8 instance sau khi CPU vượt 70%, nhưng p95 latency vẫn tăng từ 200 ms lên 2 giây; DB connection limit đạt ngưỡng.

**Yêu cầu:** Phân biệt nguyên nhân liên quan CPU/backend capacity với DB bottleneck, vẽ luồng giám sát, chọn chỉ số cần alert và đề xuất hướng cải thiện như connection pooling, caching, queue, DB tuning hoặc xử lý truy vấn. Giải thích vì sao tiếp tục tăng EC2 có thể làm DB quá tải hơn.

### Bài tập 5 — Scale in an toàn

Một target xử lý request xuất báo cáo trong 90 giây; ASG scale in và chấm dứt instance sau khi deregistration khiến yêu cầu bị gián đoạn.

**Yêu cầu:** Đánh giá `deregistration_delay.timeout_seconds`, graceful shutdown, ASG lifecycle hooks, giới hạn timeout client/ALB và phương án đẩy tác vụ dài vào SQS/Step Functions. Xác nhận request được retry/idempotent trong quá trình thay instance.

### Câu hỏi tự kiểm tra

1. **ALB và ASG có vai trò giống nhau không?** Không. ALB chọn target/route traffic; ASG quản lý capacity và vòng đời EC2.
2. **Có hai instance trong cùng một AZ có phải Multi-AZ?** Không. Cần phân bố qua ít nhất hai AZ và xử lý các phụ thuộc chung.
3. **EC2 `running` có nghĩa ALB target đã `healthy`?** Không. Health check đòi ứng dụng/port/path hoạt động.
4. **ALB luôn mở cross-zone ở mọi cấp cấu hình?** Ở cấp load balancer luôn bật; target group có thể override theo khả năng hỗ trợ.
5. **Bật health check trên target group có khiến ASG tự thay mọi instance unhealthy?** Không mặc định; phải xét `HealthCheckType=ELB` của ASG cùng target group attachment và grace period.
6. **ASG tăng capacity có tự tăng khả năng xử lý database?** Không. Database cần được đo và scale/thiết kế HA riêng.
7. **Nên dùng CPU hay request/target?** Chọn metric phản ánh workload và SLO theo benchmark; không có metric đúng cho mọi ứng dụng.
8. **Mất một AZ, ASG có bảo đảm phục vụ ngay đủ peak?** Không. Cần năng lực dự phòng trong AZ còn lại, health/routing đúng và kiểm thử failure.

## 19. Checklist trước khi triển khai production

- [ ] Đã xác định SLO về availability, p95/p99 latency, RTO/RPO và traffic bình thường/cao điểm.
- [ ] Đã chọn **ALB/NLB/GWLB** theo giao thức/tính năng, không theo tên phổ biến.
- [ ] ALB internet-facing có HTTPS listener/ACM, public subnets **ít nhất hai AZ** và SG phù hợp.
- [ ] Backend ASG dùng private subnets nhiều AZ, launch template/AMI/role đã kiểm thử khởi động.
- [ ] Target group đúng **instance/ip** type, port, health path, matcher, thresholds và cross-zone attributes.
- [ ] ASG gắn **đúng target group ARN**; biết `MinSize`, `DesiredCapacity`, `MaxSize` và subnet list.
- [ ] Đã cấu hình ELB health checks cho ASG khi muốn thay unhealthy targets; đã đo và đặt grace period.
- [ ] Đã đặt warmup, scale in/deregistration delay và graceful shutdown theo thời gian thực tế.
- [ ] Scaling policy dùng metric phù hợp với tải và SLO; đã thử scale out/in, quota/capacity shortage.
- [ ] Từng AZ còn đủ năng lực theo yêu cầu outage; đã diễn tập mất một instance/AZ có kiểm soát.
- [ ] Ứng dụng stateless phù hợp; session/file/jobs được lưu ở hệ thống chia sẻ/khôi phục được.
- [ ] Database, cache, S3/EFS, SQS và phụ thuộc ngoài có khả năng HA/backup/restore phù hợp.
- [ ] IAM least privilege, SG app nhận từ ALB SG, KMS/TLS, audit log và quyền quản trị an toàn.
- [ ] Có alarm cho HealthyHostCount, latency, 5xx, ASG desired/in-service, DB connection và chi phí.
- [ ] Có IaC, runbook, rollback, kiểm tra biến động DNS/route và quy trình thay đổi deployment.
- [ ] Dự toán đủ chi phí EC2, EBS, ALB/NLB, NAT/endpoints, network transfer, monitoring và dự phòng AZ.

## 20. Tổng kết

**Load balancer phân phối kết nối đến healthy targets; Auto Scaling quản lý số lượng backend; Multi-AZ phân tách miền lỗi.** Chúng cần **được thiết kế và kiểm thử như một hệ thống**: listener → target group → health check → ASG/launch template → subnet/AZ → database/storage → monitoring.

Với website/API HTTP(S), kiến trúc khởi đầu phổ biến là **ALB ở ít nhất hai AZ**, **ASG EC2 backend ở private subnets nhiều AZ**, scaling policy dựa trên metric phản ánh tải, và **backend stateless**. Nhưng kết quả chỉ đáng tin khi có readiness, grace period, graceful shutdown, capacity trong AZ còn lại và sự bảo vệ phù hợp cho dữ liệu/queue/database. Mục tiêu cuối là **ứng dụng an toàn, phản hồi ổn định, phục hồi được và có chi phí đo được**, chứ không chỉ số EC2 tự động tăng giảm.

### Tài liệu AWS chính thức để tra cứu khi triển khai

- [Elastic Load Balancing overview](https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/what-is-load-balancing.html)
- [Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html)
- [ALB target group attributes, cross-zone behavior](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-target-group-attributes.html)
- [ALB target group health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html)
- [Network Load Balancer cross-zone attributes](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/edit-load-balancer-attributes.html)
- [Amazon EC2 Auto Scaling overview](https://docs.aws.amazon.com/autoscaling/ec2/userguide/what-is-amazon-ec2-auto-scaling.html)
- [Attach a load balancer to an Auto Scaling group](https://docs.aws.amazon.com/autoscaling/ec2/userguide/attach-load-balancer-asg.html)
- [Auto Scaling health check grace period](https://docs.aws.amazon.com/autoscaling/ec2/userguide/health-check-grace-period.html)
- [Target tracking scaling policies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-target-tracking.html)
- [Scaling policies and instance warmup](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-scaling-cooldowns.html)
- [Monitor Application Load Balancers with CloudWatch](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html)
- [AWS Elastic Load Balancing pricing](https://aws.amazon.com/elasticloadbalancing/pricing/)

**Ghi chú triển khai:** Phạm vi hỗ trợ, thông số mặc định, metric, giá và giao diện Console có thể thay đổi. Luôn kiểm tra tài liệu AWS, quota và Region thực tế trước khi áp dụng vào hệ thống đang phục vụ người dùng.
