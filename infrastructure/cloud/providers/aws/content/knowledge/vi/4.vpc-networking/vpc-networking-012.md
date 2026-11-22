# Thiết kế VPC nhiều AZ cho ứng dụng production

> **Chương:** Mạng VPC  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS từ Region/AZ, IAM và VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; thực hành thiết kế hệ thống an toàn, quan sát được, có khả năng phục hồi và kiểm soát chi phí.

Một ứng dụng production không thể coi “có hai máy chủ” là đủ dự phòng. Nếu cả hai máy nằm trong cùng một Availability Zone (AZ), dùng chung một đường egress, hoặc phụ thuộc vào một cơ sở dữ liệu duy nhất không có cơ chế failover, một sự cố hạ tầng vẫn có thể làm toàn bộ dịch vụ gián đoạn. **Thiết kế VPC nhiều AZ** là cách bố trí mạng và tài nguyên để một lỗi cục bộ không làm mất mọi đường phục vụ ứng dụng.

Bài này dùng ví dụ ứng dụng thương mại điện tử trong một AWS Region, triển khai trên **hai AZ độc lập**. Các CIDR, tên tài nguyên, số lượng máy và Region chỉ là ví dụ. Khi làm thật phải kiểm tra AZ khả dụng trong tài khoản, yêu cầu dữ liệu, tính năng dịch vụ, quota, hiệu năng và giá hiện hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao cần nhiều AZ, phạm vi lỗi mà thiết kế nhiều AZ giải quyết được và giới hạn của một Region.
2. Chia một VPC thành các subnet public, private application và private database **theo từng AZ**, phân bổ CIDR đủ mở rộng.
3. Thiết kế route table, Internet Gateway (IGW), NAT Gateway và VPC endpoint để tránh phụ thuộc mạng không cần thiết.
4. Phối hợp Application Load Balancer (ALB), Auto Scaling, Security Group và RDS Multi-AZ để duy trì dịch vụ khi một AZ gặp lỗi.
5. Đặt mục tiêu khả dụng, năng lực phục vụ, RTO/RPO; lập kế hoạch quan sát, diễn tập phục hồi và kiểm soát chi phí.
6. Đọc một cấu hình hạ tầng dạng Infrastructure as Code và kiểm tra thiết kế bằng AWS CLI ở chế độ chỉ đọc.

## 2. Hiểu đúng “nhiều AZ”

**AWS Region** là một khu vực địa lý; mỗi Region gồm nhiều **Availability Zone** được thiết kế cách ly về nguồn điện, mạng và hạ tầng vật lý nhưng kết nối với nhau qua đường truyền có độ trễ thấp. Một **subnet nằm hoàn toàn trong một AZ**, còn **VPC trải trên phạm vi Region**. Vì vậy, ứng dụng muốn trải hai AZ phải tạo những subnet riêng cho từng AZ.

| Phạm vi | Ví dụ tài nguyên | Hệ quả đối với chịu lỗi |
| --- | --- | --- |
| **AZ** | EC2 instance, EBS volume, subnet, NAT Gateway loại zonal | Lỗi AZ có thể làm gián đoạn tài nguyên ở AZ đó |
| **Region** | VPC, nhiều dịch vụ được quản lý theo Region | Có thể kết hợp các AZ, nhưng Region vẫn là một miền lỗi lớn hơn |
| **Toàn cầu / mạng biên** | Route 53, CloudFront | Hỗ trợ định tuyến/phân phối; không tự làm origin hoặc database nhiều Region |

**Nhiều AZ không đồng nghĩa nhiều Region.** Hai AZ giúp giảm tác động của lỗi tại một vị trí; sự cố có phạm vi cả Region, lỗi phần mềm chung, cấu hình IAM sai, dữ liệu bị xóa hay sự cố từ bên thứ ba vẫn cần phương án riêng.

### 2.1. Bắt đầu bằng mục tiêu nghiệp vụ

Trước khi chọn loại EC2 hay kích thước subnet, hãy làm rõ:

- **RTO (Recovery Time Objective):** mục tiêu thời gian để khôi phục chức năng sau sự cố.
- **RPO (Recovery Point Objective):** mục tiêu lượng dữ liệu có thể mất, được biểu diễn bằng thời gian.
- **SLO:** mục tiêu đo được cho dịch vụ, ví dụ tỷ lệ request thành công và thời gian đáp ứng trong một khoảng thời gian.
- **Tải khi mất AZ:** vùng còn sống phải chịu bao nhiêu request và trong bao lâu?
- **Khả năng vận hành:** đội ngũ có thể quan sát lỗi, khôi phục, rollback và diễn tập định kỳ không?

Không thể suy ra RTO, RPO hoặc tỷ lệ khả dụng thực tế chỉ từ việc đánh dấu “Multi-AZ”. Chúng phụ thuộc vào cấu hình dịch vụ, đường đi, năng lực còn lại và thời gian ứng dụng tự phục hồi.

## 3. Kiến trúc tham chiếu cho ứng dụng production

Giả sử hệ thống có giao diện web, API, dữ liệu đơn hàng và ảnh sản phẩm. Kiến trúc đề xuất:

~~~mermaid
flowchart TB
    U["Người dùng"] --> DNS["Route 53 / tên miền"]
    DNS -.->|"Phân giải DNS"| U
    U --> EDGE["CloudFront + WAF (tùy nhu cầu)"]
    EDGE --> ALB["Application Load Balancer - Internet facing"]

    subgraph VPC["VPC 10.40.0.0/16 - một AWS Region"]
        ALB
        subgraph A["Availability Zone A"]
            PA["Public subnet A: ALB nodes + NAT-A"]
            AA["Private app subnet A: EC2/ECS app"]
            DA["Private DB subnet A: RDS primary (ban đầu)"]
        end
        subgraph B["Availability Zone B"]
            PB["Public subnet B: ALB nodes + NAT-B"]
            AB["Private app subnet B: EC2/ECS app"]
            DB["Private DB subnet B: RDS standby (ban đầu)"]
        end
        ALB --> AA
        ALB --> AB
        AA --> RDS["Endpoint RDS Multi-AZ"]
        AB --> RDS
        RDS --> DA
        DA -.->|"Đồng bộ dữ liệu"| DB
        AA -.->|"Egress tại AZ A"| PA
        AB -.->|"Egress tại AZ B"| PB
    end
    EDGE -.->|"Ảnh và tài nguyên tĩnh"| S3["Amazon S3 Standard - Region"]
    AA -.->|"AWS API qua endpoint (khi phù hợp)"| AWS["Dịch vụ AWS theo Region"]
    AB -.->|"AWS API qua endpoint (khi phù hợp)"| AWS
~~~

*Sơ đồ thể hiện quan hệ logic, không phải mọi packet hop. ALB là tài nguyên logic dùng subnet ở cả hai AZ; RDS primary/standby minh họa mô hình **Multi-AZ DB instance có một standby**. Không mô tả mọi thành phần TLS, IAM, route, NAT, Security Group hoặc cache.*

Luồng yêu cầu chính:

1. Người dùng phân giải DNS và truy cập HTTPS. CloudFront/WAF là lớp tùy chọn, hữu ích khi cần cache, giảm độ trễ phân phối hoặc lọc lưu lượng ở edge.
2. ALB triển khai tại ít nhất hai subnet thuộc hai AZ, kiểm tra sức khỏe ứng dụng rồi phân phối yêu cầu đến target ở các private app subnet.
3. Ứng dụng xử lý nghiệp vụ trên EC2 hoặc ECS service/Auto Scaling, có instance hoặc task ở cả hai AZ.
4. Ứng dụng kết nối tới endpoint của RDS Multi-AZ; RDS quản lý primary/standby và failover theo cơ chế của cấu hình đã chọn.
5. Ảnh/tệp tĩnh lưu ở S3 Standard; kết nối tới các dịch vụ AWS khác có thể sử dụng VPC endpoint phù hợp để hạn chế egress qua NAT.
6. CloudWatch, log, metrics và cảnh báo giúp nhận diện sức khỏe của từng lớp, không chỉ kiểm tra trạng thái EC2.

Trong môi trường không dùng CloudFront, người dùng có thể kết nối trực tiếp tới ALB qua HTTPS và DNS; định tuyến, chứng chỉ và cơ chế bảo vệ cần điều chỉnh tương ứng.

## 4. Kế hoạch IP và subnet theo từng AZ

### 4.1. Chia CIDR theo chức năng

Chọn VPC IPv4 `10.40.0.0/16` làm ví dụ. Dành các subnet `/24` để dễ đọc; sản phẩm thực tế cần tính theo số ENI, pod IP, kế hoạch mở rộng, kết nối mạng và tránh trùng CIDR với on-premises hay VPC peering.

| AZ | Subnet | CIDR | Chứa thành phần |
| --- | --- | --- | --- |
| A | `public-a` | `10.40.0.0/24` | ALB public ENI, NAT-A |
| B | `public-b` | `10.40.1.0/24` | ALB public ENI, NAT-B |
| A | `app-private-a` | `10.40.10.0/24` | EC2/ECS application |
| B | `app-private-b` | `10.40.11.0/24` | EC2/ECS application |
| A | `db-private-a` | `10.40.20.0/24` | RDS subnet group |
| B | `db-private-b` | `10.40.21.0/24` | RDS subnet group |

AWS dành riêng **5 địa chỉ IPv4 mỗi subnet**; một subnet `/24` có 256 địa chỉ tổng cộng và tối đa 251 địa chỉ IPv4 khả dụng trước các hạn chế khác. Đừng tính chỉ theo số máy EC2: ALB, ECS awsvpc, EKS, NAT, RDS và một số VPC endpoint cũng dùng IP/ENI.

**Tách subnet không phải là cơ chế bảo mật tự động.** Việc gọi một subnet là “private” không khiến tài nguyên an toàn nếu route, IP công khai hoặc chính sách truy cập được cấu hình sai. Vai trò public/private cần được định nghĩa bằng **đường định tuyến** và khả năng tiếp cận.

### 4.2. Khi nào cần ba AZ?

Hai AZ là mức tối thiểu phổ biến cho hệ thống cần chịu lỗi một AZ và một số dịch vụ yêu cầu ít nhất hai AZ. Ba AZ có thể tăng lựa chọn khi cân bằng tải, bảo trì hoặc gặp sự cố, nhưng cũng làm phức tạp subnet, đường NAT, phí lưu lượng và tính toán capacity.

Với ba AZ, hãy tạo **đầy đủ subnet cho AZ C**: không chỉ thêm EC2 ở AZ C mà bỏ sót subnet ALB, database và đường đi riêng phù hợp. Với dịch vụ cụ thể, hãy kiểm tra số AZ tối thiểu/tối đa được hỗ trợ và model dữ liệu của dịch vụ.

### 4.3. Tên AZ và AZ ID

Tên như `ap-southeast-1a` có thể ánh xạ tới vị trí vật lý khác nhau giữa một số tài khoản. Khi cần so sánh chính xác vị trí giữa tài khoản, hãy xem **AZ ID** (ví dụ dạng `apse1-az1`). Trong cùng tài khoản, dùng AZ names do API trả về; tránh giả định “AZ a” luôn là một trung tâm dữ liệu cố định đối với mọi tài khoản.

## 5. Route table, Internet Gateway và đường đi hai chiều

VPC có một local route cho CIDR VPC để các subnet trong VPC có thể định tuyến đến nhau, trừ khi có cấu hình định tuyến đặc thù. Việc gói tin có được cho phép hay không vẫn phụ thuộc Security Group, Network ACL, listener, hệ điều hành và các lớp bảo vệ khác.

### 5.1. Public subnet

Một public subnet thường liên kết với route table có:

| Destination | Target | Ý nghĩa |
| --- | --- | --- |
| `10.40.0.0/16` | `local` | Đường nội bộ VPC |
| `0.0.0.0/0` | `igw-prod` | Đường IPv4 ra/vào Internet qua Internet Gateway |

Để EC2 có thể kết nối trực tiếp với Internet qua IGW, cấu hình còn cần **public IPv4 hoặc Elastic IP** và quy tắc SG/NACL phù hợp. Không nên đặt máy chủ ứng dụng hay database ra public subnet chỉ để đơn giản hóa triển khai.

Đối với ALB internet-facing, AWS yêu cầu cấu hình các subnet ở **ít nhất hai AZ**. ALB nhận lưu lượng ở lớp công khai rồi chuyển đến target có thể nằm trong private subnet; target không cần public IP.

### 5.2. Private application subnet

Ứng dụng trong private subnet không có route mặc định trực tiếp tới Internet Gateway. Nếu vẫn cần tạo **kết nối outbound IPv4** đến Internet, có thể dùng NAT Gateway loại zonal trong public subnet.

| Route table | Destination | Target |
| --- | --- | --- |
| `rt-app-a` | `10.40.0.0/16` | `local` |
| `rt-app-a` | `0.0.0.0/0` | `nat-a` ở AZ A |
| `rt-app-b` | `10.40.0.0/16` | `local` |
| `rt-app-b` | `0.0.0.0/0` | `nat-b` ở AZ B |

Đây là mẫu **đường egress theo từng AZ**: app ở AZ A đi qua NAT-A, app ở AZ B đi qua NAT-B. Nếu chỉ dùng NAT-A cho cả hai AZ, khi AZ A gặp lỗi, app ở AZ B có thể vẫn chạy nhưng mất egress Internet. Cấu hình NAT theo AZ tăng chi phí, nhưng giảm phụ thuộc vào AZ khác và giúp tránh một số đường truyền liên AZ.

NAT Gateway không cho phép Internet tự khởi tạo kết nối trực tiếp vào private instance. Nó chủ yếu phục vụ kết nối được bắt đầu từ mạng private. Nếu cần public inbound, dùng ALB, reverse proxy hoặc cấu hình kết nối rõ ràng khác.

**Lưu ý:** AWS có thể cung cấp nhiều loại/kiểu triển khai NAT tùy thời điểm và Region. Khi áp dụng mẫu NAT theo AZ, hãy xác minh loại NAT, phạm vi khả dụng, quota và hành vi định tuyến của loại đó. Không mặc định mọi sản phẩm NAT đều có cùng miền lỗi.

### 5.3. Private database subnet

Với database không cần outbound Internet, route table riêng có thể chỉ cần `local` và các route cần thiết khác phục vụ đường mạng nội bộ/endpoint. **Không tự tạo route `0.0.0.0/0` tới NAT** cho DB nếu không có nhu cầu rõ ràng.

Database vẫn cần truy cập được từ tầng ứng dụng qua mạng VPC, được kiểm soát bằng Security Group và cơ chế xác thực cơ sở dữ liệu. Đặt `PubliclyAccessible=false` cho RDS là một lớp thiết lập quan trọng, nhưng vẫn cần kiểm tra subnet group và chính sách mạng.

### 5.4. VPC endpoint để giảm egress không cần thiết

Ứng dụng có thể cần truy cập S3, DynamoDB, Secrets Manager, Systems Manager, ECR, CloudWatch Logs hoặc các dịch vụ AWS khác.

| Endpoint | Cách hoạt động tổng quát | Khi cân nhắc |
| --- | --- | --- |
| **Gateway endpoint** | Hỗ trợ S3/DynamoDB qua route table và prefix list liên quan | Tránh đi Internet/NAT cho các luồng dịch vụ hỗ trợ trong Region |
| **Interface endpoint** | Dùng ENI/IP riêng tại subnet đã chọn, qua AWS PrivateLink | Truy cập các API dịch vụ tương thích trong private network |

Gateway endpoint cho S3/DynamoDB không dùng cùng mô hình tính phí như interface endpoint; interface endpoint thường có phí theo AZ/giờ và lưu lượng xử lý. Gateway endpoint chỉ giải quyết dịch vụ, đường đi và điều kiện hỗ trợ cụ thể, **không thay thế mọi NAT traffic**.

Với interface endpoint, chọn subnet ở nhiều AZ nếu cần chịu lỗi AZ, cấu hình DNS/SG/endpoint policy phù hợp và thử nghiệm luồng ứng dụng. Đối với dịch vụ cần nhiều endpoint như ECR, phải xác định cả các luồng lấy image, truy cập object S3 và logging liên quan.

## 6. Cân bằng tải và tầng ứng dụng theo AZ

### 6.1. Application Load Balancer

ALB là dịch vụ cân bằng tải layer 7. Trong kiến trúc này:

- Listener HTTPS `443` dùng chứng chỉ ACM phù hợp với tên miền.
- ALB được bật ở hai subnet public thuộc hai AZ.
- Target group trỏ tới ứng dụng chạy `HTTP 8080` hoặc `HTTPS` theo thiết kế, với health check ở endpoint như `/health/ready`.
- Các EC2 instances/ECS tasks phân bố tại app subnet A và B.
- ALB chỉ chuyển request đến những target được coi là khỏe theo trạng thái kiểm tra và cơ chế của dịch vụ.

**Health check ứng dụng** nên phản ánh khả năng nhận request: chương trình có khởi động xong, kết nối đến các phụ thuộc tối quan trọng có dùng được, có đang bị loại khỏi vòng phục vụ hay không? Nếu health check quá nặng hoặc phụ thuộc vào mọi dịch vụ bên ngoài, một sự cố nhỏ có thể khiến toàn bộ target bị đánh dấu lỗi. Thiết kế liveness và readiness theo vai trò riêng khi nền tảng hỗ trợ.

Cross-zone load balancing trên ALB giúp điều phối tới target ở các AZ được bật theo cấu hình của dịch vụ. Cần hiểu rằng **ALB khỏe không có nghĩa toàn bộ ứng dụng khỏe**; target group có thể không còn máy nào phục vụ nếu code hay database đều lỗi.

### 6.2. Auto Scaling và phân bổ capacity

Ví dụ ứng dụng chạy bằng **EC2 Auto Scaling Group (ASG)** ở `app-private-a` và `app-private-b`, tối thiểu bốn instance trong điều kiện bình thường. ASG có thể thay thế instance lỗi và cân bằng giữa AZ theo khả năng cấp tài nguyên và cấu hình.

Giả sử mỗi instance đã được kiểm thử tải, phục vụ tối đa 120 request/giây trước khi chạm giới hạn hiệu năng. Nếu muốn vận hành quanh **70%** công suất ở giờ cao điểm, năng lực hiệu dụng khoảng **84 request/giây/instance**. Với lưu lượng đỉnh 200 request/giây:

~~~text
Công suất cần duy trì khi một AZ ngừng hoạt động = 200 req/s
Công suất mục tiêu mỗi instance = 120 × 70% = 84 req/s
Số instance cần còn sống = ceil(200 / 84) = 3
~~~

Nếu có hai AZ và phân bổ cân bằng, có thể cần **ít nhất ba instance ở mỗi AZ** (tổng sáu) để sau khi mất một AZ, ba instance còn lại tiếp tục xử lý tải đỉnh *theo giả định đo đạc*. Con số này chỉ là minh họa; tải thực tế có thể bị chi phối bởi CPU, bộ nhớ, kết nối database, số request đồng thời, queue và thời gian khởi động máy.

Đừng phụ thuộc hoàn toàn vào việc ASG tự tăng số máy **sau khi AZ đã mất**: có thể mất thời gian để cấp instance mới, khởi động, tải image, đăng ký target và qua health check. Để giữ SLO nghiêm ngặt, cần **đủ dung lượng dự phòng sẵn có**, đồng thời kiểm tra quota EC2, capacity reservation hoặc lựa chọn instance thay thế nếu cần.

### 6.3. Dịch vụ tính toán khác

Với **ECS**, hãy đặt tasks tại subnet nhiều AZ và dùng deployment configuration, load balancer/health checks thích hợp. Với **EKS**, cần phân bố nodes/pods, quản lý topology spread, PodDisruptionBudget và hệ quả khi mất AZ. Với **Lambda** gắn VPC, Lambda quản lý năng lực tính toán, nhưng subnet/ENI và đường egress đến các dịch vụ khác vẫn phải được cấu hình đúng. Không suy rằng chọn nhiều subnet tự động giải quyết mọi giới hạn concurrency hoặc phụ thuộc database.

## 7. Dữ liệu và dịch vụ trạng thái phải chịu được lỗi AZ

Tầng application stateless tương đối dễ nhân bản; database, phiên đăng nhập, cache và lưu trữ là những điểm cần thiết kế cẩn trọng.

### 7.1. RDS Multi-AZ không đồng nghĩa Read Replica

Với **RDS Multi-AZ DB instance deployment**, AWS duy trì **primary** và **standby đồng bộ** ở AZ khác. Ứng dụng truy cập endpoint DB; khi điều kiện failover phù hợp, RDS có thể chuyển vai trò primary. Phải xử lý kết nối ngắt, DNS/connection pool, retry và giao dịch trong thời gian chuyển đổi.

**Read Replica** chủ yếu phục vụ đọc mở rộng và các tình huống sao chép/phục hồi tùy cấu hình, không tự đồng nghĩa cơ chế Multi-AZ failover nói trên. RDS Multi-AZ **DB cluster** có topology và đặc tính riêng (có các DB instance đọc được), nên phải kiểm tra đúng loại triển khai trước khi thiết kế.

Với RDS, **DB subnet group** thường cần subnet tại **ít nhất hai AZ**. Không chỉ tạo subnet DB ở AZ A rồi mong standby tự xuất hiện ở AZ B. Cần kiểm tra công cụ database, loại deployment, khả năng mở rộng và yêu cầu backup/restore.

### 7.2. Những tài nguyên dữ liệu khác

| Thành phần | Phạm vi / lựa chọn | Điểm cần kiểm tra |
| --- | --- | --- |
| **EBS** | Volume gắn với một AZ | Không tự chuyển volume sống sang AZ khác; cần snapshot/backup và quy trình khôi phục |
| **S3 Standard** | Lưu object ở phạm vi Region với khả năng dự phòng nhiều AZ do AWS quản lý | S3 Standard khác các lớp One Zone; phải xem chính sách bảo vệ dữ liệu và quyền truy cập |
| **EFS Regional** | Hệ thống tệp có bản sao qua nhiều AZ, có thể tạo mount target trong AZ tương ứng | Khả năng truy cập mount target, SG/NFS và chi phí lưu lượng |
| **ElastiCache** | Có các tùy chọn Multi-AZ/failover theo engine và cấu hình | Kiểm tra replication group, cluster mode, endpoint và client reconnect |
| **DynamoDB** | Dịch vụ được quản lý với tính sẵn sàng cấp Region | Tính nhất quán, giới hạn hiệu năng và nhu cầu khôi phục nhiều Region |
| **SQS** | Hàng đợi được quản lý theo Region | Retry, dead-letter queue, xử lý trùng lặp và độ bền luồng nghiệp vụ |

Đừng lưu dữ liệu nghiệp vụ quan trọng chỉ trong bộ nhớ một EC2 instance hoặc trên local disk nếu không có chiến lược phục hồi. Đối với phiên đăng nhập, có thể dùng token hoặc session store được quản lý phù hợp; code ứng dụng cần **idempotency** để retry không tạo đơn hàng/thanh toán hai lần.

### 7.3. Khi database failover

Một request đang ghi đơn hàng có thể gặp lỗi mạng hoặc mất kết nối đúng lúc RDS chuyển primary. Không nên retry mọi lệnh ghi một cách mù quáng: nếu không biết giao dịch đã commit hay chưa, retry có thể tạo dữ liệu trùng. Dùng **idempotency key**, giới hạn số lần retry, exponential backoff, kiểm tra trạng thái giao dịch và theo dõi lỗi để xử lý chính xác.

Multi-AZ nâng khả năng chịu lỗi hạ tầng nhưng không bảo vệ khỏi **xóa nhầm dữ liệu, lỗi migration, SQL sai** hoặc thảm họa cấp Region. Cần backup, point-in-time recovery (nếu hỗ trợ), quản lý thay đổi schema và diễn tập khôi phục.

## 8. Phân quyền mạng và bảo mật production

Nên thiết kế theo nguyên tắc **deny by default và least privilege** ở từng tầng:

| Đối tượng | Inbound đề xuất | Outbound cần xét |
| --- | --- | --- |
| **ALB Security Group** | HTTPS `443` từ client/CloudFront theo kiến trúc | App SG trên port ứng dụng `8080`, health check theo cấu hình |
| **App Security Group** | `8080` từ ALB SG | DB SG `5432`, VPC endpoints, các dịch vụ cần thiết |
| **DB Security Group** | `5432` chỉ từ App SG | Theo nhu cầu thực tế của dịch vụ/DB, không mở rộng mặc định |
| **VPC endpoint SG** (interface) | HTTPS từ App SG/CIDR phù hợp | Phản hồi theo connection tracking |

Security Group là **stateful**, nên không cần mở cổng ephemeral chiều ngược cho phản hồi của luồng được theo dõi như với NACL. NACL là **stateless**, gắn ở subnet; nếu chọn custom NACL phải mở đủ inbound và outbound, cả port dịch vụ lẫn port ephemeral của bên mở kết nối. Đánh số rule thấp được xét trước; một Deny trước Allow có thể chặn cả luồng mong muốn.

Các kiểm soát bổ sung:

- Dùng **IAM role** gắn cho workload; tránh lưu access key dài hạn trong image, mã nguồn hay biến cấu hình không bảo vệ.
- Đặt secret trong **AWS Secrets Manager** hoặc giải pháp quản lý bí mật phù hợp, mã hóa và kiểm soát quyền truy cập.
- Bật TLS ở ranh giới công khai; cân nhắc mã hóa kết nối ALB → app và app → DB theo yêu cầu.
- Quản trị bằng **AWS Systems Manager Session Manager** khi phù hợp thay vì mở SSH/RDP công khai; chuẩn bị SSM endpoint/NAT, agent và IAM role.
- Bật S3 Block Public Access ở phạm vi phù hợp; với CloudFront và S3 private origin, dùng **Origin Access Control (OAC)** khi thích hợp.
- Sử dụng AWS WAF cho HTTP(S) tại CloudFront/ALB, giám sát lưu lượng bất thường; WAF không thay thế kiểm tra xác thực/phân quyền trong ứng dụng.
- Phân tách môi trường dev, staging và production bằng tài khoản/VPC/quyền phù hợp; bảo vệ quyền sửa route table, Security Group, NACL và các pipeline triển khai.

**Lưu ý:** private subnet không đồng nghĩa “không thể bị tấn công”. Khi ứng dụng đã bị chiếm quyền, kẻ tấn công có thể thử gọi dịch vụ nội bộ, metadata hoặc tài nguyên mà IAM role được phép. Cần giới hạn cả mạng, IAM, dữ liệu và hành vi ứng dụng.

## 9. Phân tích sự cố theo “blast radius”

Thiết kế production cần xác định không chỉ *có bao nhiêu AZ*, mà còn **mất một thành phần sẽ ảnh hưởng những phần nào**.

| Sự cố | Điều kiến trúc kỳ vọng | Điều phải kiểm chứng |
| --- | --- | --- |
| Một EC2 instance lỗi | ALB loại target; ASG thay thế instance | Health check, số target còn lại, thời gian instance mới sẵn sàng |
| **AZ A mất** | App AZ B và NAT-B tiếp tục hoạt động; ALB phục vụ target khỏe | Capacity còn đủ, route B dùng NAT-B, không có phụ thuộc đơn ở AZ A |
| NAT-A lỗi | Egress của App A bị ảnh hưởng, App B dùng NAT-B | Mỗi private route table trỏ đúng NAT ở AZ của nó |
| Primary RDS ở AZ A lỗi | RDS Multi-AZ chuyển sang standby ở AZ B theo cơ chế dịch vụ | Connection retry, hành vi giao dịch, latency và kết nối sau failover |
| Một ALB target không khỏe | ALB chuyển traffic sang target khỏe | Readiness endpoint, ngưỡng health check, ECS/ASG thay thế |
| Deploy phiên bản lỗi tới cả hai AZ | **Cả hai AZ có thể hỏng cùng lúc** | Rolling/canary, rollback, test release, feature flag |
| Dữ liệu bị xóa hoặc migration sai | Multi-AZ có thể đồng bộ cả thay đổi lỗi | Backup, PITR và phương án phục hồi dữ liệu |
| **Toàn Region không khả dụng** | Thiết kế chỉ một Region có thể ngừng phục vụ | DR nhiều Region nếu nghiệp vụ yêu cầu, RTO/RPO rõ ràng |

### 9.1. Diễn tập một kịch bản mất AZ

1. Trước thử nghiệm, xác định SLO, điều kiện dừng, người chịu trách nhiệm, khách hàng ảnh hưởng và khả năng rollback.
2. Xác minh hạ tầng đã có target ở hai AZ, nhóm tự mở rộng và database có chế độ Multi-AZ phù hợp.
3. Mô phỏng mất một nhóm target/AZ bằng phương pháp được hỗ trợ trong **môi trường thử nghiệm**, đo thời gian phát hiện, thời gian chuyển tải và số request lỗi.
4. Quan sát ALB target health, ASG activity, RDS events, số kết nối DB, độ trễ p95/p99 và số lượng lỗi.
5. Kiểm tra egress từ AZ còn hoạt động, health check, queue consumers và các tác vụ nền.
6. Khôi phục cấu hình, kiểm tra cân bằng tải trở lại và lập biên bản khoảng trống so với RTO/SLO.

Không nên tác động trực tiếp lên production để “chứng minh Multi-AZ” nếu chưa có quy trình thử nghiệm được phê duyệt và giới hạn ảnh hưởng.

## 10. Quan sát hệ thống, cảnh báo và vận hành

### 10.1. Những tín hiệu cần nhìn

| Lớp | Tín hiệu theo dõi |
| --- | --- |
| **ALB** | `HTTPCode_ELB_5XX_Count`, `HTTPCode_Target_5XX_Count`, `TargetResponseTime`, `HealthyHostCount` |
| **EC2/ASG** | CPU, memory qua CloudWatch Agent nếu cấu hình, trạng thái instance, activity và số instance đang phục vụ |
| **RDS** | CPU, connections, free storage, storage latency, RDS events, failover và tình trạng replication phù hợp |
| **NAT Gateway** | Số kết nối, byte xử lý, packet drops/port allocation errors theo metrics dịch vụ |
| **VPC Flow Logs** | Metadata các luồng ACCEPT/REJECT được ghi ở phạm vi chọn |
| **Ứng dụng** | Throughput, tỷ lệ lỗi, latency p95/p99, retry, queue lag, lỗi giao dịch, idempotency conflict |
| **Chi phí** | NAT hours/data processing, load balancer, EC2, RDS Multi-AZ, data transfer, VPC endpoints |

Không nên xem `HealthyHostCount > 0` là đủ để kết luận hệ thống an toàn: khi chỉ còn một target khỏe, request vẫn chạy nhưng mất toàn bộ dư địa dự phòng. Cảnh báo nên so với **số target tối thiểu để chịu lỗi** và năng lực xử lý yêu cầu.

### 10.2. Logging và truy vết

- Dùng **CloudTrail** cho các thay đổi quản trị quan trọng như route table, subnet association, Security Group và IAM; loại event được ghi phụ thuộc cấu hình trail/event data store.
- Bật **VPC Flow Logs** ở phạm vi cần điều tra và tối ưu lưu trữ, retention; bản ghi `REJECT` không tự xác định rule cụ thể nào gây lỗi.
- Sử dụng **ALB access logs** theo nhu cầu kiểm toán và phân tích request; chú ý chi phí và dữ liệu nhạy cảm.
- Tập trung log ứng dụng, correlation/request ID và distributed tracing để tìm nguyên nhân khi luồng đi qua ALB, app, DB và queue.
- Dùng **VPC Reachability Analyzer** phân tích cấu hình đường mạng giữa các endpoint hỗ trợ; kết quả phân tích cần được đối chiếu kiểm thử thực tế.

## 11. Kiểm soát chi phí khi triển khai nhiều AZ

Khả dụng cao có giá thành. Tính chi phí **toàn hệ thống**, thay vì chỉ nhân đôi số EC2:

| Thành phần | Điều làm chi phí tăng | Cách đánh giá |
| --- | --- | --- |
| **Compute nhiều AZ** | Instance/task dự phòng chạy thường trực | Chọn capacity theo lỗi AZ, tải, SLO; tối ưu loại máy và autoscale |
| **RDS Multi-AZ** | Năng lực standby và storage/IO tùy loại cấu hình | So sánh giá chính xác theo engine, size, deployment |
| **NAT Gateway theo AZ** | Phí theo giờ và data processing; số NAT tăng | Phân tích egress thực tế; dùng VPC endpoint khi hợp lý |
| **Cross-AZ data transfer** | Lưu lượng đi qua ranh giới AZ tùy nguồn/đích và dịch vụ | Vẽ luồng, kiểm tra bảng giá thực tế; tránh vòng qua AZ khác |
| **ALB** | Giờ chạy và capacity units theo mô hình tính phí | Đo request rate, connections, rule evaluation, byte xử lý |
| **Interface endpoints** | Có phí theo endpoint AZ/giờ và byte xử lý | Chỉ triển khai endpoint cần thiết và ở đủ AZ theo yêu cầu |
| **Logs, metrics, backups** | Lưu trữ, ingestion, truy vấn, retention | Thiết lập retention, tier, cảnh báo chi phí và ngân sách |

NAT Gateway có thể trở thành khoản lớn khi tải image, gửi telemetry hoặc tải dependency qua Internet. Nếu workload chạy trong private subnet và sử dụng ECR/S3/CloudWatch, hãy kiểm tra những endpoint cần thiết. Tuy vậy, **không khẳng định endpoint luôn rẻ hơn NAT**: phải so sánh phí theo giờ, số AZ, số byte và lưu lượng thực tế.

**Ví dụ so sánh đánh đổi:** một NAT-A dùng chung cho hai AZ giảm số lượng NAT Gateway nhưng tạo phụ thuộc egress vào AZ A và có thể phát sinh luồng liên AZ; hai NAT theo AZ tăng phí cố định nhưng tăng khả năng chịu lỗi. Quyết định dựa vào tác động của việc mất egress đối với nghiệp vụ, chứ không chỉ chọn giá thấp nhất.

## 12. Biểu diễn mạng bằng Infrastructure as Code

Infrastructure as Code (IaC) giúp tái lập subnet, route, NAT và giới hạn quyền một cách nhất quán. Đoạn Terraform sau mô tả **nền mạng IPv4 tối thiểu** cho hai AZ, với một NAT Gateway loại zonal ở mỗi AZ. Đây là **khung minh họa**, chưa tạo ALB/ASG/RDS/Security Group hoặc chính sách vận hành và sẽ phát sinh chi phí nếu áp dụng.

Các tên AZ cần được lấy từ tài khoản và Region thực tế; chọn hai AZ khả dụng khác nhau. Mẫu sử dụng hai subnets database với route nội bộ, đồng thời tạo S3 gateway endpoint cho private route tables.

~~~hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = "ap-southeast-1"
}

variable "az_names" {
  type        = list(string)
  description = "Hai AZ khả dụng, khác nhau trong cùng tài khoản/Region"

  validation {
    condition     = length(var.az_names) == 2 && length(distinct(var.az_names)) == 2
    error_message = "Chọn đúng hai AZ khác nhau."
  }
}

locals {
  zones = {
    a = {
      az          = var.az_names[0]
      public_cidr = "10.40.0.0/24"
      app_cidr    = "10.40.10.0/24"
      db_cidr     = "10.40.20.0/24"
    }
    b = {
      az          = var.az_names[1]
      public_cidr = "10.40.1.0/24"
      app_cidr    = "10.40.11.0/24"
      db_cidr     = "10.40.21.0/24"
    }
  }
}

resource "aws_vpc" "prod" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "prod-vpc" }
}

resource "aws_internet_gateway" "prod" {
  vpc_id = aws_vpc.prod.id
  tags   = { Name = "prod-igw" }
}

resource "aws_subnet" "public" {
  for_each                = local.zones
  vpc_id                  = aws_vpc.prod.id
  availability_zone       = each.value.az
  cidr_block              = each.value.public_cidr
  map_public_ip_on_launch = false
  tags = { Name = format("prod-public-%s", each.key) }
}

resource "aws_subnet" "app" {
  for_each          = local.zones
  vpc_id            = aws_vpc.prod.id
  availability_zone = each.value.az
  cidr_block        = each.value.app_cidr
  tags = { Name = format("prod-app-%s", each.key) }
}

resource "aws_subnet" "db" {
  for_each          = local.zones
  vpc_id            = aws_vpc.prod.id
  availability_zone = each.value.az
  cidr_block        = each.value.db_cidr
  tags = { Name = format("prod-db-%s", each.key) }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.prod.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.prod.id
  }
  tags = { Name = "prod-public-routes" }
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  for_each = local.zones
  domain   = "vpc"
}

resource "aws_nat_gateway" "zonal" {
  for_each      = local.zones
  subnet_id     = aws_subnet.public[each.key].id
  allocation_id = aws_eip.nat[each.key].id
  depends_on    = [aws_internet_gateway.prod]
  tags = { Name = format("prod-nat-%s", each.key) }
}

resource "aws_route_table" "app" {
  for_each = local.zones
  vpc_id   = aws_vpc.prod.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.zonal[each.key].id
  }
  tags = { Name = format("prod-app-routes-%s", each.key) }
}

resource "aws_route_table_association" "app" {
  for_each       = aws_subnet.app
  subnet_id      = each.value.id
  route_table_id = aws_route_table.app[each.key].id
}

resource "aws_route_table" "db" {
  vpc_id = aws_vpc.prod.id
  tags   = { Name = "prod-db-routes-local-only" }
}

resource "aws_route_table_association" "db" {
  for_each       = aws_subnet.db
  subnet_id      = each.value.id
  route_table_id = aws_route_table.db.id
}

data "aws_region" "current" {}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.prod.id
  vpc_endpoint_type = "Gateway"
  service_name      = format("com.amazonaws.%s.s3", data.aws_region.current.name)
  route_table_ids   = concat(
    [for rt in values(aws_route_table.app) : rt.id],
    [aws_route_table.db.id]
  )
}
~~~

**Điểm cần đọc trong đoạn mã:**

1. `for_each = local.zones` tạo subnet theo từng AZ và dùng cùng khóa `a`/`b` để ghép NAT với route table đúng AZ.
2. Public route table trỏ tới IGW; private app route tables trỏ tới NAT tương ứng. DB route table có local route mặc định, **không có đường Internet mặc định**.
3. S3 gateway endpoint thêm route phù hợp cho S3 vào các route tables đã chọn; không đồng nghĩa mọi AWS API đều đi được qua endpoint này.
4. `map_public_ip_on_launch = false` tránh việc EC2 mới trong public subnet tự được cấp public IP; ALB internet-facing được AWS quản lý theo cấu hình riêng.
5. Terraform còn cần state backend an toàn, policy/quyền chạy IaC, kiểm soát drift, review `plan` và thiết kế bổ sung ALB/ASG/RDS. Không chạy `apply` trên tài khoản production chỉ từ ví dụ bài học.

Để kiểm tra logic của bản thiết kế, có thể dùng `terraform fmt`, `terraform validate` và `terraform plan` trong môi trường thử nghiệm được phép. Bản `plan` phải được review vì ví dụ tạo NAT Gateway/EIP và có chi phí.

## 13. Bài thực hành kiểm tra VPC bằng AWS CLI (chỉ đọc)

Ví dụ dùng Region `ap-southeast-1` và các ID giả định; thay theo tài khoản của bạn. Cần AWS CLI có thông tin xác thực được phép gọi các API Describe tương ứng. Các lệnh dưới đây **không tạo hoặc xóa tài nguyên**.

### 13.1. Liệt kê VPC và CIDR

~~~bash
aws ec2 describe-vpcs \
  --region ap-southeast-1 \
  --query "Vpcs[].{VpcId:VpcId,CIDR:CidrBlock,Default:IsDefault}" \
  --output table
~~~

### 13.2. Đối chiếu subnet với AZ

~~~bash
aws ec2 describe-subnets \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-0123456789abcdef0 \
  --query "Subnets[].{Id:SubnetId,CIDR:CidrBlock,AZ:AvailabilityZone,AZ_ID:AvailabilityZoneId,FreeIPs:AvailableIpAddressCount}" \
  --output table
~~~

Kiểm tra subnet public/app/db có nằm ở **cả hai AZ** không; đảm bảo CIDR không chồng lấn và số IP còn trống đáp ứng quá trình scale/failover.

### 13.3. Kiểm tra route table theo subnet

~~~bash
aws ec2 describe-route-tables \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-0123456789abcdef0 \
  --query "RouteTables[].{Id:RouteTableId,Routes:Routes[].{Dest:DestinationCidrBlock,NAT:NatGatewayId,IGW:GatewayId},Subnets:Associations[].SubnetId}" \
  --output json
~~~

Hãy tìm các route mặc định của `app-private-a` và `app-private-b`. Chúng có trỏ tới hai NAT khác AZ không? Route table của DB có bị thêm `0.0.0.0/0` ngoài kế hoạch không? Lưu ý: route table gắn **ngầm** qua main route table có thể không hiển thị bằng một `SubnetId` riêng trong phần association; cần phân biệt explicit và main association.

### 13.4. Kiểm tra NAT theo AZ

~~~bash
aws ec2 describe-nat-gateways \
  --region ap-southeast-1 \
  --filter Name=vpc-id,Values=vpc-0123456789abcdef0 \
  --query "NatGateways[].{Id:NatGatewayId,Subnet:SubnetId,AZ:AvailabilityZone,State:State}" \
  --output table
~~~

Nếu response hoặc phiên bản CLI không có trường AZ cho loại NAT đang sử dụng, đối chiếu `SubnetId` với kết quả `describe-subnets` để suy ra AZ của **NAT Gateway zonal**. Với loại NAT khác, kiểm tra tài liệu của chính loại đó trước khi kết luận về khả dụng.

### 13.5. Kiểm tra ALB/ASG/RDS

~~~bash
aws elbv2 describe-load-balancers --region ap-southeast-1 \
  --query "LoadBalancers[].{Name:LoadBalancerName,Scheme:Scheme,AZs:AvailabilityZones[].ZoneName}" \
  --output json

aws autoscaling describe-auto-scaling-groups --region ap-southeast-1 \
  --query "AutoScalingGroups[].{Name:AutoScalingGroupName,Min:MinSize,Desired:DesiredCapacity,Max:MaxSize,AZs:AvailabilityZones}" \
  --output json

aws rds describe-db-instances --region ap-southeast-1 \
  --query "DBInstances[].{Id:DBInstanceIdentifier,Engine:Engine,MultiAZ:MultiAZ,Public:PubliclyAccessible,PrimaryAZ:AvailabilityZone}" \
  --output table
~~~

Đừng dùng mỗi trường `MultiAZ=true` để tuyên bố thiết kế đã đáp ứng RTO/RPO. Cần xem subnet group, topology thật, backup, trạng thái ứng dụng và kiểm thử failover.

## 14. Bài tập thiết kế và kiểm tra

### Bài tập 1 — tìm điểm lỗi đơn

Một kiến trúc có ALB ở AZ A/B, ba EC2 instance ở AZ A và một EC2 ở AZ B, nhưng cả hai private app subnet đều dùng NAT-A. Database là RDS single-AZ ở AZ A.

**Câu hỏi:** nếu AZ A mất, những thành phần nào còn hoạt động và vì sao website vẫn có thể lỗi?

**Gợi ý:** ALB có thể tiếp tục nhận kết nối ở AZ B và một EC2 tại B còn chạy. Nhưng capacity có thể không đủ, private egress qua NAT-A bị mất, RDS single-AZ mất khả dụng và các endpoint có thể bị ảnh hưởng. Cần phân bổ workload/capacity có chủ đích, đường egress ít phụ thuộc AZ khác và DB có kế hoạch chịu lỗi.

### Bài tập 2 — lập bảng routing

Từ sơ đồ CIDR ở mục 4, hãy điền:

| Subnet | Route `0.0.0.0/0` kỳ vọng | Có nên nhận request Internet trực tiếp? |
| --- | --- | --- |
| `public-a` | ? | ? |
| `public-b` | ? | ? |
| `app-private-a` | ? | ? |
| `app-private-b` | ? | ? |
| `db-private-a` | ? | ? |
| `db-private-b` | ? | ? |

**Đáp án gợi ý:** public-a/public-b → IGW; app-a → NAT-A, app-b → NAT-B; hai DB subnet không có default route ra Internet nếu không cần. Request công khai nên đi vào ALB, không truy cập thẳng App/DB.

### Bài tập 3 — tính capacity khi mất AZ

Giả sử tải đỉnh **360 request/giây**, mỗi instance phục vụ an toàn **90 request/giây** ở mức SLO mục tiêu và hệ thống có hai AZ. Hãy tính số instance phải còn sống khi mất một AZ, rồi tìm cấu hình cân bằng ít nhất giữa hai AZ.

**Gợi ý:** `ceil(360/90) = 4` instance còn sống, nên trong giả định chia đều và mất nguyên một AZ cần ít nhất **4 instance mỗi AZ**, tổng 8 instance, chưa tính margin ngoài giả định, quota/capacity và phụ thuộc khác. Nếu mỗi instance chỉ đạt 90 req/s trong benchmark thử nghiệm, hãy chừa thêm biên an toàn cho biến động tải.

### Bài tập 4 — thiết kế kiểm thử

Hãy viết kế hoạch thử ứng dụng bị lỗi một AZ mà không tác động production: các thông số cần đo trước/sau khi loại một nhóm target, threshold ALB, thời gian thay thế instance, phản ứng RDS, đường NAT, p95 latency và tỷ lệ lỗi. Xác định điều kiện pass/fail dựa trên SLO thay vì chỉ dựa vào “ứng dụng vẫn mở được”.

## 15. Những hiểu lầm phổ biến

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “VPC có hai AZ tự động là ứng dụng HA.” | Cần triển khai **workload, đường mạng và dữ liệu** phù hợp ở cả hai AZ. |
| “Có hai EC2 ở hai AZ là đủ.” | Có thể còn RDS single-AZ, NAT một AZ, dịch vụ nền hay capacity không đủ. |
| “Private subnet không cần Internet nên chẳng cần xét route.” | Ứng dụng có thể cần outbound tới API/package repository; phải chọn NAT hoặc endpoint theo nhu cầu. |
| “Một NAT dùng chung không ảnh hưởng khả dụng.” | NAT zonal ở AZ bị lỗi có thể làm mất egress của subnet AZ khác đang trỏ tới nó. |
| “RDS Multi-AZ không gián đoạn một giây nào.” | Failover có thể làm ngắt kết nối; client phải retry/reconnect và quản lý giao dịch. |
| “Read Replica đồng nghĩa standby failover.” | Mục tiêu và cơ chế của read replica khác với RDS Multi-AZ DB instance deployment. |
| “ALB kiểm tra healthy là sản phẩm luôn khỏe.” | Target có thể còn quá ít capacity hoặc phụ thuộc DB/queue không đáp ứng. |
| “Tăng thêm AZ luôn giảm chi phí.” | Thêm bản sao, đường NAT, endpoint, lưu lượng liên AZ và monitoring có chi phí. |
| “Mất Region vẫn sống vì có nhiều AZ.” | Muốn chịu lỗi Region phải thiết kế DR nhiều Region và kiểm thử riêng. |

## 16. Checklist trước khi đưa ứng dụng lên production

- [ ] Region được chọn theo độ trễ, yêu cầu dữ liệu, dịch vụ hỗ trợ, quota và chi phí.
- [ ] VPC CIDR không trùng với mạng cần kết nối; subnet public/app/db ở ít nhất hai AZ phù hợp.
- [ ] ALB dùng subnet ở nhiều AZ, HTTPS/chứng chỉ/health check và target group được cấu hình đúng.
- [ ] App có instance/task ở nhiều AZ và **đủ capacity khi mất một AZ** ở mức tải đã định.
- [ ] Route tables rõ ràng; egress theo AZ hoặc kiến trúc NAT/endpoint có miền lỗi được chấp nhận.
- [ ] RDS/dữ liệu có phương án Multi-AZ, backup, khôi phục và retry/idempotency phù hợp.
- [ ] SG/NACL chỉ cho phép luồng thật sự cần; app và DB không mở public không cần thiết.
- [ ] IAM role, secrets, encryption, cập nhật phần mềm, WAF và audit đã được rà soát.
- [ ] Log, metrics, traces, cảnh báo và cost budgets có người tiếp nhận và quy trình phản ứng.
- [ ] Có IaC, review thay đổi, rollback, test lỗi AZ và kế hoạch DR theo RTO/RPO.

**Ghi nhớ:** thiết kế nhiều AZ thành công là thiết kế cho **đường đi còn sống khi một AZ ngừng phục vụ**: inbound qua ALB, khả năng xử lý của ứng dụng, outbound qua NAT/endpoint và trạng thái của dữ liệu đều phải được kiểm tra cùng nhau. Mỗi thành phần có phạm vi lỗi riêng; chỉ khi những phụ thuộc quan trọng không dồn về một AZ, mục tiêu khả dụng mới có cơ sở thực hiện.

### Tài liệu AWS chính thức để đọc thêm

- [VPCs and subnets](https://docs.aws.amazon.com/vpc/latest/userguide/configure-subnets.html) — VPC, subnet, AZ và phạm vi địa chỉ.
- [Subnet route tables](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Route_Tables.html) — routing và subnet associations.
- [Connect your VPC to the Internet](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html) — Internet Gateway và mạng public.
- [NAT gateways](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html) — egress, phạm vi hoạt động và chi phí của NAT.
- [Gateway VPC endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html) và [Interface VPC endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/interface-endpoints.html) — kết nối riêng tới dịch vụ AWS.
- [Availability Zones for Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html) — ALB và subnet nhiều AZ.
- [Amazon EC2 Auto Scaling availability](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-add-availability-zone.html) — phân bổ và thay thế capacity giữa AZ.
- [Multi-AZ DB instance deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html) — RDS synchronous standby và failover.
- [Security groups for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html) và [Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html) — kiểm soát mạng ở hai lớp.
- [AWS Well-Architected: Planning for disaster recovery](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_planning_for_recovery_disaster_recovery.html) — RTO, RPO và chiến lược DR.
- [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html) và [Reachability Analyzer](https://docs.aws.amazon.com/vpc/latest/reachability/what-is-reachability-analyzer.html) — quan sát và kiểm tra đường mạng.
