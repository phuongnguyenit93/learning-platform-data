# Gateway endpoint và interface endpoint

> **Chương:** Mạng VPC  
> **Module:** CLOUD_PROVIDERS_AWS — tìm hiểu hạ tầng Region/AZ, IAM, VPC và các dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp, serverless để thiết kế ứng dụng an toàn, dễ giám sát, có khả năng phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Trong Amazon VPC, một máy EC2 hoặc ứng dụng trong private subnet thường cần gọi API của Amazon S3, DynamoDB, Systems Manager, Secrets Manager, CloudWatch hoặc dịch vụ khác. Nếu tất cả lưu lượng đó đi qua NAT Gateway và đường truy cập Internet, kiến trúc có thể phát sinh chi phí, phụ thuộc không cần thiết vào tuyến egress và khó giới hạn theo dịch vụ. **VPC endpoint** cung cấp một đường kết nối riêng đến dịch vụ được hỗ trợ, giúp thiết kế truy cập phù hợp với mạng riêng và chính sách bảo mật.

Sau bài học, bạn có thể:

1. Giải thích **gateway endpoint** và **interface endpoint** là gì, cách mỗi loại chuyển tiếp lưu lượng từ VPC.
2. Chọn loại endpoint phù hợp cho S3, DynamoDB và các dịch vụ hỗ trợ AWS PrivateLink.
3. Phân biệt vai trò của **route table**, **DNS**, **ENI**, **security group**, **IAM policy**, **endpoint policy** và **resource policy**.
4. Tạo và kiểm tra endpoint bằng AWS Console hoặc AWS CLI trong sandbox; nêu được cách dọn tài nguyên và nơi phát sinh chi phí.
5. Chẩn đoán các lỗi phổ biến: timeout, DNS trả về địa chỉ không mong muốn, `AccessDenied`, nhầm Region, sai route table hoặc security group.
6. Xây dựng thiết kế nhiều AZ và giải thích giới hạn của VPC endpoint khi truy cập từ VPC khác hoặc mạng on-premises.

## 1. VPC endpoint giải quyết vấn đề gì?

Giả sử một ứng dụng chạy trong **private subnet**, không có public IPv4 và không có default route ra Internet. Ứng dụng vẫn cần tải ảnh từ S3, đọc tham số từ AWS Systems Manager và gọi các API nội bộ của AWS. Có hai cách kết nối phổ biến:

- Cấu hình **đường egress qua NAT Gateway** và sử dụng DNS/API endpoint thông thường của AWS.
- Tạo **VPC endpoint** dành cho dịch vụ được hỗ trợ để kết nối riêng từ mạng trong hoặc mạng đã liên thông với VPC.

VPC endpoint là thành phần kết nối mạng; nó **không tự cấp quyền IAM**, **không mã hóa dữ liệu thay cho ứng dụng**, **không chặn toàn bộ lưu lượng Internet khác** và **không bảo đảm mọi dịch vụ AWS đều có endpoint**. Quyền gọi API vẫn được đánh giá qua IAM/resource policy và các ràng buộc khác.

### 1.1. Hai đường đi thường gặp

~~~mermaid
flowchart TD
    A[Ứng dụng trong private subnet] --> B{Đích cần truy cập}
    B -->|S3 hoặc DynamoDB qua gateway endpoint| C[Route table: AWS-managed prefix list]
    C --> D[Gateway VPC endpoint]
    D --> E[S3 / DynamoDB]
    B -->|Dịch vụ hỗ trợ AWS PrivateLink| F[DNS dịch vụ: private IP của endpoint]
    F --> G[Interface VPC endpoint: ENI + security group]
    G --> H[Dịch vụ AWS / endpoint service]
    B -->|Đích ngoài phạm vi endpoint| I[NAT Gateway / egress phù hợp nếu được cấu hình]
    I --> J[Internet hoặc public service endpoint]
~~~

**Ý chính:** gateway endpoint chủ yếu dựa trên **tuyến trong route table**; interface endpoint chủ yếu dựa trên **địa chỉ private IP của ENI**, thường được ứng dụng tìm thấy thông qua **DNS**. Cả hai được cấu hình trong một Region và phải tương thích với dịch vụ cụ thể.

### 1.2. Phân biệt các loại endpoint

AWS có thêm các loại endpoint phục vụ mục đích khác (ví dụ **Gateway Load Balancer endpoint** cho kiến trúc kiểm tra lưu lượng). Bài này chỉ so sánh hai loại thường dùng để truy cập dịch vụ:

| Tiêu chí | Gateway endpoint | Interface endpoint |
|---|---|---|
| Cơ chế | Tuyến đến dịch vụ qua **route table** và AWS-managed prefix list | **Elastic Network Interface (ENI)** có private IP trong subnet |
| Dịch vụ điển hình | **Amazon S3, Amazon DynamoDB** | Nhiều dịch vụ AWS như Systems Manager, Secrets Manager, CloudWatch Logs; dịch vụ đối tác hoặc endpoint service riêng; S3 cũng có tùy chọn interface |
| Vị trí cấu hình | VPC + các route table cần sử dụng | VPC + subnet ở những AZ được hỗ trợ + security group |
| Đổi cách phân giải DNS? | **Không yêu cầu** chuyển DNS dịch vụ thành private IP | Thường bật **private DNS**; hoặc dùng DNS name riêng của endpoint |
| Security group gắn với endpoint | Không | Có, gắn với ENI |
| Truy cập qua peering, Transit Gateway, VPN, Direct Connect | Không thể dùng gateway endpoint của VPC khác qua các kết nối này | Có thể, nếu dịch vụ, routing, DNS và chính sách cho phép |
| Phí endpoint | Không có phí tạo/sử dụng gateway endpoint | Thường tính **phí theo giờ cho mỗi AZ** và **theo dung lượng dữ liệu xử lý** |
| Giới hạn quyền | Endpoint policy; IAM, resource policy cũng áp dụng | IAM/resource policy; endpoint policy nếu dịch vụ hỗ trợ |
| Trường hợp hay dùng | EC2/Lambda trong VPC truy cập S3/DynamoDB cùng Region | Workload trong VPC cần gọi AWS API từ private subnet không đi qua NAT |

Các quy tắc dịch vụ, AZ, IP address type, DNS và giá có thể thay đổi. Trước khi triển khai, kiểm tra **service name** và **endpoint type** thực tế trong Region đang dùng.

## 2. Gateway endpoint: định tuyến riêng đến S3 và DynamoDB

### 2.1. Hoạt động dựa trên route table

Một **gateway VPC endpoint** được tạo trong VPC và liên kết với một hoặc nhiều **route table**. AWS thêm tuyến cho một **AWS-managed prefix list** chứa dải IP của dịch vụ đích trong Region, với target là endpoint ID.

~~~mermaid
flowchart LR
    A[EC2 trong private subnet] --> B[Subnet route table]
    B -->|Destination: pl-... S3 prefix list| C[Target: vpce-... Gateway endpoint]
    C --> D[Amazon S3 cùng Region]
    B -->|0.0.0.0/0 nếu tồn tại| E[NAT Gateway / Internet egress]
~~~

Ví dụ một route table có thể hiển thị:

| Destination | Target | Vai trò |
|---|---|---|
| `10.20.0.0/16` | `local` | Giao tiếp nội bộ VPC |
| `pl-xxxxxxxx` | `vpce-xxxxxxxx` | Đường đến dịch vụ S3 qua gateway endpoint |
| `0.0.0.0/0` | `nat-xxxxxxxx` | Đường egress Internet khác, nếu kiến trúc cần |

**Prefix list** là tập CIDR do AWS quản lý cho một dịch vụ. Địa chỉ IP S3 mà DNS trả về vẫn có thể là địa chỉ public của dịch vụ, nhưng khi đích khớp tuyến của prefix list, lưu lượng được định tuyến qua gateway endpoint, **không cần public IP của EC2 hoặc NAT Gateway** cho kết nối đó.

Tuyến gateway endpoint chỉ xuất hiện trong những route table **đã liên kết với endpoint**. Nếu subnet của ứng dụng sử dụng route table khác chưa được liên kết, ứng dụng có thể tiếp tục đi qua NAT (nếu có) hoặc không kết nối được. Cũng cần xem các tuyến khác có mức ưu tiên cao hơn có làm thay đổi đường đi hay không.

### 2.2. Giới hạn phạm vi

- Gateway endpoint dùng cho **S3 và DynamoDB**, với tên dịch vụ theo Region, chẳng hạn `com.amazonaws.ap-southeast-1.s3` hoặc `com.amazonaws.ap-southeast-1.dynamodb`.
- **VPC chứa gateway endpoint** là phạm vi truy cập trực tiếp. Không thể dùng endpoint đó thông qua VPC peering, Transit Gateway, Site-to-Site VPN hoặc Direct Connect từ một VPC/mạng khác.
- Với gateway endpoint, truy cập dịch vụ theo thiết kế **cùng Region**. Đối với bucket S3 nằm ở Region khác, cần kiểm tra tuyến và lựa chọn truy cập khác; đừng mặc định mọi S3 request đều đi qua gateway endpoint.
- Gateway endpoint **không tạo ENI** và **không có security group gắn trực tiếp**. Security group của EC2, network ACL và chính sách dịch vụ vẫn có thể ảnh hưởng.
- Gateway endpoint được AWS quản lý về khả năng sẵn sàng; bạn không chọn ENI tại từng AZ như interface endpoint.

### 2.3. Endpoint policy cho S3

Khi tạo gateway endpoint, có thể để **default endpoint policy** cho phép truy cập rộng ở lớp endpoint hoặc cấu hình **custom endpoint policy** để giới hạn các thao tác/tài nguyên đi qua endpoint.

Ví dụ endpoint policy **chỉ cho phép đọc một bucket thực hành** `aws-lab-dev-data-example`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListTrainingBucket",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::aws-lab-dev-data-example"
    },
    {
      "Sid": "ReadTrainingObjects",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::aws-lab-dev-data-example/*"
    }
  ]
}
~~~

**`Principal: "*"` trong endpoint policy không có nghĩa là cấp công khai quyền đọc bucket.** Endpoint policy chỉ là lớp kiểm soát các request **đi qua endpoint**; IAM policy, bucket policy và các cơ chế đánh giá quyền khác vẫn phải cho phép. Nếu người dùng có đường mạng khác tới S3, endpoint policy **không tự giới hạn đường ngoài endpoint**.

Điểm cần nhớ:

- `s3:ListBucket` áp dụng trên ARN **bucket**, còn `s3:GetObject` áp dụng trên ARN **object**.
- Endpoint policy chỉ áp dụng cho traffic qua endpoint, không phải chính sách toàn tài khoản.
- Để yêu cầu bucket chỉ chấp nhận request qua endpoint được duyệt, có thể cân nhắc `aws:SourceVpce` trong **bucket policy**, nhưng phải xem trước tác động tới AWS Console, automation và dịch vụ AWS truy cập thay mặt người dùng.

## 3. Interface endpoint: kết nối bằng private IP qua AWS PrivateLink

### 3.1. ENI được tạo trong subnet

**Interface VPC endpoint** là một loại endpoint sử dụng **AWS PrivateLink**. Khi tạo interface endpoint, bạn chọn một hoặc nhiều subnet trong VPC, thông thường **tối đa một subnet cho mỗi AZ** đối với endpoint đó. AWS tạo **endpoint ENI** trong mỗi subnet đã chọn và cấp **private IP** theo cấu hình được hỗ trợ.

~~~mermaid
flowchart TB
    A[Ứng dụng trong private subnet AZ-a] --> D[DNS dịch vụ]
    B[Ứng dụng trong private subnet AZ-b] --> D
    D --> E[Private DNS trả IP của endpoint ENI]
    E --> F[Endpoint ENI ở AZ-a]
    E --> G[Endpoint ENI ở AZ-b]
    F --> H[AWS PrivateLink]
    G --> H
    H --> I[Dịch vụ: Systems Manager / Secrets Manager / khác]
~~~

Khác với gateway endpoint, interface endpoint **không cần tuyến riêng kiểu prefix-list → vpce**. Khách hàng truy cập địa chỉ **private IP của endpoint ENI**, và VPC routing thông thường chuyển tiếp gói tin tới IP đó, miễn routing, security group và NACL cho phép.

### 3.2. Private DNS là điểm quyết định trải nghiệm ứng dụng

Giả sử có interface endpoint cho `com.amazonaws.ap-southeast-1.ssm`. Khi **private DNS được hỗ trợ và bật**, truy vấn tên API chuẩn:

~~~text
ssm.ap-southeast-1.amazonaws.com
~~~

từ môi trường phân giải DNS phù hợp trong VPC sẽ trả về **private IP của endpoint ENI**. Ứng dụng và AWS CLI thường có thể tiếp tục sử dụng hostname dịch vụ mặc định mà không sửa code.

Nếu không bật private DNS (hoặc dịch vụ không hỗ trợ), bạn thường phải sử dụng **DNS name riêng của VPC endpoint** từ kết quả `describe-vpc-endpoints` và chỉ định endpoint URL khi cần. **Không nên tự ghép URL** vì cấu trúc DNS name thay đổi theo dịch vụ, Region và endpoint.

Điều kiện và giới hạn cần kiểm tra:

1. VPC phải có các cấu hình DNS phù hợp, thường gồm **DNS resolution** (`enableDnsSupport`) và **DNS hostnames** (`enableDnsHostnames`).
2. Dịch vụ phải hỗ trợ private DNS cho endpoint đó.
3. Nếu dùng DNS server riêng hoặc truy cập từ on-premises, cần thiết kế **DNS forwarding/Route 53 Resolver** để truy vấn dịch vụ được phân giải đúng.
4. Bật private DNS trong VPC **không mặc nhiên sửa DNS của máy ở mạng bên ngoài**.
5. Một số dịch vụ có hướng dẫn riêng về tên miền endpoint, IPv4/IPv6 và phương án kết nối. Kiểm tra endpoint cụ thể trong Console hoặc tài liệu dịch vụ.

### 3.3. Security group và NACL ở interface endpoint

Interface endpoint có **security group** gắn với endpoint ENI. Với API HTTPS thông thường:

- **Endpoint security group:** cho phép **inbound TCP 443** từ security group hoặc CIDR của các workload được phép gọi.
- **Workload security group:** cho phép **outbound TCP 443** tới endpoint.
- **Network ACL:** nếu dùng ACL hạn chế, cho phép lưu lượng hai chiều và cổng phản hồi phù hợp.
- **Subnet IP:** có đủ địa chỉ để AWS cấp cho ENI; endpoint ENI là tài nguyên có vòng đời và phải được theo dõi.
- **IAM và endpoint policy:** vẫn kiểm soát thao tác API; kết nối TCP thành công không đồng nghĩa được phép `GetSecretValue` hoặc API khác.

**Ví dụ:** một Lambda function chạy trong VPC có security group `sg-app` gọi Secrets Manager qua interface endpoint; security group `sg-vpce` của endpoint nên cho phép inbound 443 từ `sg-app` thay vì mở `0.0.0.0/0` nếu không có nhu cầu thực tế.

### 3.4. Truy cập từ mạng khác

Một interface endpoint **có thể** được truy cập từ VPC khác qua peering/Transit Gateway hoặc từ on-premises qua VPN/Direct Connect nếu kết nối mạng, tuyến trả lời, DNS, security group, chính sách và hỗ trợ dịch vụ đều phù hợp. Tính năng này làm interface endpoint hữu ích cho kiến trúc kết nối tập trung hoặc truy cập riêng từ trung tâm dữ liệu.

Ví dụ:

~~~mermaid
flowchart LR
    A[Ứng dụng on-premises] --> B[VPN / Direct Connect]
    B --> C[VPC có endpoint]
    C --> D[Interface endpoint ENI]
    D --> E[AWS PrivateLink]
    E --> F[Dịch vụ hỗ trợ]
~~~

Đường truyền riêng qua VPN/Direct Connect **không tự động bảo đảm DNS đúng**. Tên dịch vụ phải phân giải về private IP endpoint hoặc client cần dùng endpoint-specific DNS name phù hợp.

**AWS PrivateLink** cũng có mô hình **endpoint service**: bên cung cấp có thể công bố dịch vụ của mình (thường phía sau Network Load Balancer) để bên tiêu thụ tạo **interface endpoint** trong VPC của họ. Trong mô hình này có thể có cơ chế cho phép principal và chấp thuận yêu cầu kết nối. Đây là một trường hợp khác với dùng interface endpoint đến API dịch vụ AWS được AWS quản lý.

## 4. Chọn gateway endpoint hay interface endpoint?

### 4.1. Bảng quyết định

| Nhu cầu | Lựa chọn đề xuất | Lý do |
|---|---|---|
| EC2 trong VPC tải object từ S3 cùng Region | **S3 gateway endpoint** | Không mất phí endpoint; route table đơn giản |
| Ứng dụng VPC đọc/ghi DynamoDB cùng Region | **DynamoDB gateway endpoint** | Dùng tuyến prefix list cho dịch vụ |
| Private EC2 gọi AWS Systems Manager API | **Interface endpoint cho SSM** | Dịch vụ hỗ trợ PrivateLink và không cần NAT cho API này |
| Lambda trong VPC gọi Secrets Manager | **Interface endpoint cho Secrets Manager** | API kết nối qua private IP của endpoint |
| Ứng dụng trong VPC gửi log tới CloudWatch Logs | **Interface endpoint cho CloudWatch Logs** | Có thể giảm nhu cầu NAT cho API Logs |
| Mạng on-premises cần truy cập S3 qua địa chỉ riêng | **Cân nhắc S3 interface endpoint** | Gateway endpoint không thể được sử dụng từ on-premises |
| VPC khác cần dùng endpoint của một dịch vụ AWS qua kết nối riêng | **Interface endpoint + routing/DNS phù hợp** | Gateway endpoint không hỗ trợ dùng thông qua kết nối VPC khác |
| Ứng dụng cần duyệt web hoặc gọi API công khai bất kỳ | **NAT/egress có kiểm soát** | VPC endpoint không thay thế kết nối Internet tổng quát |

**Không chọn interface endpoint chỉ vì nó có tên “private”.** Đối với S3/DynamoDB trong cùng VPC và Region, gateway endpoint thường đơn giản và tiết kiệm hơn. Đối với dịch vụ chỉ hỗ trợ interface endpoint hoặc nhu cầu liên thông mạng, interface endpoint là lựa chọn phù hợp.

### 4.2. Trường hợp riêng: S3 có cả hai loại endpoint

S3 vừa hỗ trợ **gateway endpoint**, vừa có khả năng truy cập bằng **interface endpoint**. Thiết kế thực tế thường là:

- **Workload trong VPC:** dùng **S3 gateway endpoint** nếu chỉ cần truy cập S3 cùng Region.
- **Client từ on-premises:** dùng **S3 interface endpoint** với đường mạng riêng và DNS được cấu hình đúng.
- **Môi trường hỗn hợp:** AWS có cơ chế DNS riêng để truy cập on-premises dùng interface endpoint trong khi workload tại VPC dùng gateway endpoint; các tùy chọn liên quan **private DNS only for inbound Resolver endpoint** có điều kiện sử dụng cụ thể, bao gồm cấu hình gateway endpoint. Cần kiểm tra hướng dẫn chính thức cho S3 trước khi áp dụng.

Không nên mặc định tạo đồng thời cả hai loại cho cùng VPC mà chưa xác định luồng truy cập và chi phí.

## 5. Bảo mật: endpoint policy, IAM policy và resource policy

### 5.1. Ba lớp kiểm soát khác nhau

~~~mermaid
flowchart TD
    A[Principal: EC2 role / Lambda role / user] --> B[IAM policy: có quyền gọi API?]
    B --> C[VPC endpoint: request có đi qua endpoint?]
    C --> D[Endpoint policy: request này được phép?]
    D --> E[Resource policy nếu áp dụng: bucket/secret/khác]
    E --> F[Dịch vụ thực hiện kiểm tra quyền còn lại]
    F --> G[Allow hoặc Deny]
~~~

Sơ đồ là **cách kiểm tra tư duy**, không phải biểu diễn chính xác mọi bước nội bộ của IAM. AWS có nhiều cơ chế đánh giá chính sách, gồm **explicit deny**, permissions boundary, session policy, SCP và các quy định riêng từng dịch vụ.

| Lớp | Kiểm soát điều gì? | Nếu thiếu `Allow` phù hợp? |
|---|---|---|
| **Identity-based IAM policy** | Principal có quyền yêu cầu action trên resource không | Thường bị từ chối |
| **Endpoint policy** | Các request được phép đi qua endpoint | Bị từ chối ở lớp endpoint nếu policy không cho phép |
| **Resource-based policy** | Tài nguyên chấp nhận principal/điều kiện nào | Tùy mô hình cấp quyền và loại tài nguyên, có thể từ chối |
| **SCP/permissions boundary/session policy** | Giới hạn quyền hiệu lực của principal/phiên | Có thể bị từ chối dù IAM policy có `Allow` |

**Endpoint policy không thay thế IAM policy.** Default endpoint policy thường cho phép toàn bộ traffic ở **lớp endpoint**, nhưng không tự cấp toàn bộ quyền dịch vụ.

**Không phải interface endpoint nào cũng hỗ trợ endpoint policy.** Cần tra cứu tính năng của endpoint service cụ thể; một số endpoint có chính sách mặc định hoặc cách kiểm soát riêng.

### 5.2. Giới hạn S3 bucket theo VPC endpoint

Trong tình huống cần buộc S3 request phải đi qua endpoint cụ thể, bucket policy có thể sử dụng **global condition key** `aws:SourceVpce`. Ví dụ sau chỉ để **minh họa cơ chế**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyRequestsOutsideApprovedEndpoint",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::aws-lab-dev-data-example",
        "arn:aws:s3:::aws-lab-dev-data-example/*"
      ],
      "Condition": {
        "StringNotEquals": {
          "aws:SourceVpce": "vpce-0123456789abcdef0"
        }
      }
    }
  ]
}
~~~

Trong policy minh họa, request không đến từ endpoint được chấp thuận sẽ khớp với `Deny`. **Không áp dụng nguyên văn policy này vào bucket dùng chung/production**: AWS Console thường không đi qua endpoint của VPC; workflow của dịch vụ AWS, quản trị khẩn cấp và tự động hóa có thể bị chặn. Nếu thực sự áp dụng, cần thiết kế trước ngoại lệ có điều kiện, phương án khôi phục và kiểm thử từng đường truy cập được phép.

Nên phân biệt:

- `aws:SourceVpce`: ID của VPC endpoint đã dùng cho request.
- `aws:SourceVpc`: VPC nguồn trong những ngữ cảnh được hỗ trợ.
- `aws:VpcSourceIp`: địa chỉ IP riêng nguồn trong VPC khi điều kiện này có mặt; không dùng riêng để xác thực duy nhất VPC, vì CIDR có thể trùng giữa các VPC.
- **Source IP công khai** và **private IP của ENI** không nhất thiết là thông tin phù hợp để viết cùng một policy cho mọi loại endpoint.

### 5.3. VPC endpoint không loại bỏ mọi nhu cầu egress

- Nếu route table vẫn có `0.0.0.0/0` qua NAT và ứng dụng gọi đích khác, lưu lượng đó vẫn có thể đi qua NAT.
- Nếu API được gọi bằng tên miền/Region không khớp endpoint hoặc không bật private DNS đúng cách, request có thể sử dụng đường khác hoặc thất bại.
- Endpoint chỉ thay đổi đường mạng cho **dịch vụ và phạm vi đã cấu hình**, không tự thay thế firewall, monitoring, IAM hay kiểm soát dữ liệu.
- TLS/HTTPS và xác minh chứng chỉ vẫn cần được sử dụng theo yêu cầu dịch vụ; kết nối riêng không đồng nghĩa có thể bỏ kiểm tra TLS.

## 6. Chi phí, hiệu năng và tính sẵn sàng

### 6.1. So sánh chi phí

| Thành phần | Chi phí endpoint | Khoản phí khác vẫn có thể phát sinh |
|---|---|---|
| **Gateway endpoint cho S3/DynamoDB** | Không có phí endpoint theo giờ hoặc xử lý dữ liệu | Phí request, storage, đọc/ghi, truyền dữ liệu và dịch vụ tương ứng |
| **Interface endpoint** | Thường có phí mỗi giờ theo AZ và GB dữ liệu xử lý | Dữ liệu liên AZ, DNS/Resolver nếu cấu hình thêm, phí dịch vụ đích, log và các thành phần liên quan |
| **NAT Gateway** | Phí NAT theo giờ và GB xử lý | Phí truyền dữ liệu và các phí network liên quan |
| **VPC Flow Logs / CloudWatch Logs** | Theo tài nguyên/nhật ký của dịch vụ | Ingest, lưu trữ, truy vấn và retention nếu sử dụng |

Không nên nêu một giá cố định cho mọi Region. Khi ước tính, dùng **AWS Pricing Calculator** và bảng giá hiện hành:

~~~text
Ước tính interface endpoint hàng tháng
≈ (số AZ có endpoint × giờ hoạt động × giá/giờ/AZ)
  + (GB xử lý qua endpoint × giá/GB)
  + phí mạng, dịch vụ, logging liên quan nếu có
~~~

Đặt endpoint trong **hai AZ** để tăng khả năng sẵn sàng có thể làm tăng phí theo giờ, nhưng giảm rủi ro một AZ không khả dụng. Nếu chỉ đặt ở một AZ, client ở AZ khác có thể đi xuyên AZ, phát sinh độ trễ/phí và phụ thuộc AZ chứa ENI.

### 6.2. Thiết kế nhiều AZ

- **Gateway endpoint:** liên kết tất cả **route table** của các private subnet cần truy cập S3/DynamoDB; rà soát route table sau khi thêm subnet mới.
- **Interface endpoint:** chọn subnet trong **các AZ cần phục vụ**, phù hợp danh sách AZ endpoint service hỗ trợ và mục tiêu chịu lỗi.
- **Security group:** cho phép đúng nhóm workload từ các AZ liên quan, không chỉ subnet đang chạy thử.
- **DNS:** xác minh client thực sự phân giải về endpoint ENI được mong đợi, kể cả sau thay đổi AZ hoặc cấu trúc VPC.
- **Giám sát:** dùng thông tin endpoint state, DNS, Flow Logs, CloudTrail và chỉ số dịch vụ nếu có để kiểm tra hành vi thực tế.
- **Phục hồi:** nhiều ENI không tự bảo đảm ứng dụng chịu lỗi; SDK retry, timeout, circuit breaker và phụ thuộc dịch vụ cũng phải được thiết kế.

## 7. Thực hành trên sandbox: tạo, kiểm tra và dọn endpoint

> **Điều kiện:** chỉ thao tác trên AWS account/sandbox được phép, đúng Region và VPC. Bài lab có thể tạo **interface endpoint tính phí** theo giờ/GB; xem giá và dọn ngay sau buổi học. Không cần thực thi các lệnh nếu bạn chỉ học lý thuyết. Các ID dưới đây phải được thay bằng ID sandbox thực tế, không được dùng trên production.

Bài này dùng các giá trị minh họa:

| Biến | Ý nghĩa |
|---|---|
| `REGION=ap-southeast-1` | Region thực hành |
| `VPC_ID` | VPC có private subnets |
| `ROUTE_TABLE_ID` | Route table của private subnet cần truy cập S3 |
| `SUBNET_A`, `SUBNET_B` | Hai subnet thuộc hai AZ khác nhau, còn đủ địa chỉ IP |
| `ENDPOINT_SG` | Security group của interface endpoint |
| `APP_SG` | Security group của workload EC2/Lambda gọi endpoint |
| `BUCKET` | Bucket S3 thử nghiệm cùng Region, bạn được phép truy cập |

### 7.1. Bước 1 — Xác minh danh tính, VPC, Region và dịch vụ hỗ trợ

Nếu đang dùng AWS CLI v2 trong terminal Bash:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

REGION=ap-southeast-1
VPC_ID=vpc-0123456789abcdef0
ROUTE_TABLE_ID=rtb-0123456789abcdef0
SUBNET_A=subnet-0123456789abcdef0
SUBNET_B=subnet-0123456789abcdef1
ENDPOINT_SG=sg-0123456789abcdef0
APP_SG=sg-0123456789abcdef1

aws sts get-caller-identity --profile "$AWS_PROFILE"

aws ec2 describe-vpcs --vpc-ids "$VPC_ID" --region "$REGION"
aws ec2 describe-route-tables --route-table-ids "$ROUTE_TABLE_ID" --region "$REGION"
aws ec2 describe-subnets --subnet-ids "$SUBNET_A" "$SUBNET_B" --region "$REGION"

aws ec2 describe-vpc-endpoint-services \
  --service-names "com.amazonaws.$REGION.s3" "com.amazonaws.$REGION.ssm" \
  --region "$REGION"
~~~

Các **ID trên đều là ví dụ giả định**; thay bằng tài nguyên sandbox được cấp. Nếu chưa có profile `aws-lab-dev`, thực hiện cấu hình đăng nhập do tổ chức hướng dẫn hoặc dùng CloudShell với danh tính đã đăng nhập và bỏ dòng `export AWS_PROFILE=...`.

Cần xác minh:

1. `Account` và `Arn` của STS đúng tài khoản thực hành.
2. VPC, route table, subnet thuộc đúng Region; subnet được gán đúng AZ theo thiết kế.
3. `com.amazonaws.<region>.s3` có thể tạo **gateway endpoint**; `com.amazonaws.<region>.ssm` có thể tạo **interface endpoint** ở AZ được hỗ trợ.
4. Interface endpoint cần private DNS phù hợp và VPC DNS được bật.
5. Role hiện tại có quyền thao tác EC2 VPC endpoints; nếu không, chuyển sang phần đọc/mô phỏng thay vì tự mở rộng quyền.

### 7.2. Bước 2 — Tạo S3 gateway endpoint

~~~bash
GW_EP_ID=$(aws ec2 create-vpc-endpoint \
  --vpc-id "$VPC_ID" \
  --vpc-endpoint-type Gateway \
  --service-name "com.amazonaws.$REGION.s3" \
  --route-table-ids "$ROUTE_TABLE_ID" \
  --region "$REGION" \
  --query 'VpcEndpoint.VpcEndpointId' \
  --output text)

echo "$GW_EP_ID"

aws ec2 describe-route-tables \
  --route-table-ids "$ROUTE_TABLE_ID" \
  --region "$REGION" \
  --query 'RouteTables[].Routes[]' \
  --output table
~~~

Kết quả mong đợi: route table có thêm đường đến **S3 prefix list** với target là **gateway endpoint ID**. Nếu ứng dụng có nhiều private subnet ở nhiều route table, cần liên kết đủ những route table sẽ sử dụng endpoint.

Tại thời điểm tạo, endpoint policy mặc định thường cho phép traffic của dịch vụ qua endpoint; bạn có thể áp custom policy riêng khi đã hiểu rõ quyền cần thiết. Endpoint policy không thay thế IAM policy và bucket policy.

### 7.3. Bước 3 — Chuẩn bị security group cho interface endpoint

Đối với SSM interface endpoint, cần cho endpoint ENI nhận HTTPS từ workload. Nếu `ENDPOINT_SG` là security group **được phép sửa** và chưa có rule tương ứng:

~~~bash
aws ec2 authorize-security-group-ingress \
  --group-id "$ENDPOINT_SG" \
  --protocol tcp \
  --port 443 \
  --source-group "$APP_SG" \
  --region "$REGION"
~~~

Nếu rule đã tồn tại, API có thể trả `InvalidPermission.Duplicate`; không cần thêm lần nữa. Bảo đảm workload security group cho phép **egress TCP 443** và network ACL cho phép traffic phản hồi. Không mở inbound 443 từ toàn Internet nếu chỉ các workload trong VPC cần dùng endpoint.

### 7.4. Bước 4 — Tạo SSM interface endpoint ở hai AZ

~~~bash
IF_EP_ID=$(aws ec2 create-vpc-endpoint \
  --vpc-id "$VPC_ID" \
  --vpc-endpoint-type Interface \
  --service-name "com.amazonaws.$REGION.ssm" \
  --subnet-ids "$SUBNET_A" "$SUBNET_B" \
  --security-group-ids "$ENDPOINT_SG" \
  --private-dns-enabled \
  --region "$REGION" \
  --query 'VpcEndpoint.VpcEndpointId' \
  --output text)

echo "$IF_EP_ID"

aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids "$GW_EP_ID" "$IF_EP_ID" \
  --region "$REGION" \
  --query 'VpcEndpoints[].{Id:VpcEndpointId,Type:VpcEndpointType,State:State,Service:ServiceName}' \
  --output table
~~~

Đợi endpoint đạt trạng thái **`available`** trước khi kiểm thử. Với interface endpoint, kiểm tra **DNS entries**, **subnet IDs**, **network interface IDs**, **security group** trong Console hoặc kết quả `describe-vpc-endpoints`.

**Lưu ý về Systems Manager:** endpoint `ssm` hỗ trợ API SSM, nhưng một EC2 private instance muốn sử dụng đầy đủ **Session Manager/SSM Agent** có thể cần thêm những endpoint như `ssmmessages`, `ec2messages` (tùy Region, phiên bản agent và chức năng), cùng quyền IAM phù hợp. Đừng kết luận chỉ một interface endpoint `ssm` là đủ cho mọi tác vụ quản trị EC2.

### 7.5. Bước 5 — Kiểm tra từ workload trong private subnet

Thực hiện trong **EC2 private instance** hoặc môi trường chạy ứng dụng gắn với VPC; chạy từ laptop ngoài VPC không chứng minh được đường đi qua endpoint. Đảm bảo workload có **IAM role** với quyền tối thiểu cho những API kiểm tra.

**Kiểm tra DNS interface endpoint:**

~~~bash
nslookup ssm.ap-southeast-1.amazonaws.com
~~~

Khi private DNS hoạt động, kết quả từ DNS phù hợp trong VPC thường chứa **private IP** của endpoint ENI. Kiểm tra các địa chỉ này với ENI của interface endpoint; **DNS đúng là điều kiện cần, chưa chứng minh API được cho phép**.

**Kiểm tra API SSM (nếu role có quyền `ssm:DescribeInstanceInformation`):**

~~~bash
aws ssm describe-instance-information \
  --region ap-southeast-1 \
  --max-results 5
~~~

**Kiểm tra S3 gateway endpoint (nếu có quyền truy cập bucket):**

~~~bash
BUCKET=aws-lab-dev-data-example

aws s3api head-bucket \
  --bucket "$BUCKET" \
  --region ap-southeast-1
~~~

Bucket phải **tồn tại, ở Region phù hợp** và IAM/bucket policy/endpoint policy phải cho phép. Một lỗi `403 AccessDenied` không nhất thiết chỉ ra sự cố mạng; trước tiên hãy tách lỗi **kết nối/TLS/DNS** khỏi lỗi **phân quyền IAM/S3**.

Để xác minh lưu lượng đến đúng endpoint, có thể kết hợp thông tin DNS, route table, endpoint ENI, VPC Flow Logs nếu được bật và log yêu cầu API theo cơ chế dịch vụ hỗ trợ. **VPC Flow Logs** phản ánh metadata luồng mạng, không cho biết nội dung từng API call.

### 7.6. Bước 6 — Xóa tài nguyên để ngừng phát sinh phí

Khi đã kết thúc bài lab, chỉ xóa endpoint mà **chính bạn vừa tạo** và được phép dọn:

~~~bash
aws ec2 delete-vpc-endpoints \
  --vpc-endpoint-ids "$GW_EP_ID" "$IF_EP_ID" \
  --region "$REGION"
~~~

Kiểm tra endpoint chuyển sang trạng thái đang xóa và biến mất khỏi danh sách. AWS gỡ tuyến gateway endpoint liên quan và ENI của interface endpoint theo vòng đời xóa endpoint. Nếu bạn đã tạo riêng security group cho bài lab, xóa sau khi không còn endpoint tham chiếu; nếu chỉ thêm rule vào một security group dùng chung, cân nhắc gỡ đúng rule vừa thêm theo quy trình của nhóm.

**Cảnh báo:** Các biến shell `GW_EP_ID`, `IF_EP_ID` chỉ còn trong phiên terminal. Ghi ID của endpoint bài lab vào ghi chú kỹ thuật để có thể tìm/xóa khi terminal đóng; kiểm tra lại `Account`/`Region` trước khi thao tác.

## 8. Chẩn đoán sự cố theo dấu hiệu

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| EC2 trong private subnet không truy cập được S3, nhưng có gateway endpoint | Route table của subnet chưa liên kết endpoint; bucket khác Region; IAM/bucket policy hạn chế | Kiểm tra subnet → route table → prefix list target → bucket Region và quyền |
| EC2 gọi SSM/Secrets Manager bị timeout | Endpoint ENI chưa `available`, SG của endpoint chặn inbound 443, NACL hoặc DNS/routing lỗi | `describe-vpc-endpoints`, kiểm tra ENI, SG, route, DNS và Flow Logs |
| API endpoint hostname vẫn phân giải về địa chỉ public | Private DNS chưa bật/hỗ trợ; VPC DNS cấu hình sai; DNS server riêng chưa forward | Kiểm tra endpoint private DNS, `enableDnsSupport`, `enableDnsHostnames` và resolver |
| API trả `AccessDenied` dù có kết nối HTTPS | IAM, endpoint policy, resource policy, SCP, boundary hoặc session policy chặn | Xác nhận principal qua STS; đọc policy và CloudTrail |
| Không tạo được interface endpoint ở một subnet | AZ không được dịch vụ hỗ trợ; subnet thiếu IP; quota hoặc cấu hình endpoint sai | Xem thông báo lỗi, service details, subnet/AZ, quota |
| Máy ở VPC khác không dùng được S3 gateway endpoint | Gateway endpoint không truy cập được qua peering/TGW/VPN | Dùng endpoint trong VPC đích hoặc thiết kế interface endpoint khi phù hợp |
| Truy cập từ on-premises đến interface endpoint không thành công | Thiếu route, DNS forwarding, SG hoặc đường về | Kiểm tra VPN/DX/TGW, DNS name của endpoint, subnet và luồng hai chiều |
| Có interface endpoint nhưng chi phí NAT vẫn cao | Một phần traffic vẫn gọi endpoint public/dịch vụ khác; DNS không trỏ đúng; NAT vẫn phục vụ các đích khác | Đối chiếu DNS, flow logs, endpoint services đang dùng và Cost Explorer |
| S3 bucket bị từ chối ngay trong Console sau khi thêm policy `SourceVpce` | Console không truy cập qua VPC endpoint được yêu cầu | Xem lại bucket policy và đường truy cập quản trị đã thiết kế |
| Endpoint policy cho phép đọc nhưng application vẫn không đọc được | Identity policy thiếu quyền, bucket policy deny, KMS key policy hoặc điều kiện khác | Xem `s3:GetObject`, ARN object, KMS và tất cả lớp chính sách |

### 8.1. Quy trình kiểm tra có thứ tự

1. **Account/Region:** xác minh chính xác môi trường đang thao tác.
2. **Dịch vụ và endpoint type:** có hỗ trợ loại endpoint đó tại Region/AZ không?
3. **Endpoint state:** endpoint đã `available` chưa?
4. **Đường mạng:** với gateway kiểm tra **route table/prefix list**; với interface kiểm tra **DNS → private IP ENI → security group/NACL/routing**.
5. **TLS và API:** có kết nối HTTPS đến dịch vụ không? Nếu được, lỗi trả về là `AccessDenied` hay lỗi nghiệp vụ?
6. **Phân quyền:** xét IAM, endpoint policy, resource policy, SCP/boundary/session policy và chính sách riêng của dịch vụ.
7. **Chi phí và dọn dẹp:** kiểm tra endpoint, ENI và các tài nguyên hỗ trợ còn tồn tại sau bài lab.

## 9. Bài tập thiết kế kiến trúc

**Tình huống:** Một hệ thống xử lý đơn hàng dùng:

- **API/Lambda** trong hai private subnet thuộc hai AZ.
- **DynamoDB** lưu trạng thái đơn hàng.
- **S3** lưu hóa đơn và file export.
- **Secrets Manager** lưu thông tin cấu hình nhạy cảm cho thành phần có sử dụng secret.
- **CloudWatch Logs** thu thập log.
- Không muốn cho workload truy cập Internet tùy ý, đồng thời vẫn cần giám sát và kiểm soát chi phí.

**Hãy thiết kế** các endpoint cần thiết và ghi rõ route table, subnet/AZ, security group, IAM và endpoint/resource policy.

Một thiết kế tham khảo:

| Nhu cầu | Endpoint | Bố trí | Lớp bảo vệ đi kèm |
|---|---|---|---|
| Đọc/ghi S3 cùng Region | S3 gateway | Liên kết route table của cả hai private subnet | IAM role tối thiểu, bucket policy, endpoint policy nếu cần |
| Truy cập DynamoDB | DynamoDB gateway | Liên kết route table của cả hai private subnet | IAM policy giới hạn table và action |
| Truy cập Secrets Manager | Interface `secretsmanager` | Tạo endpoint ENI tại AZ cần phục vụ, private DNS | SG inbound 443 từ app, IAM/KMS nếu có |
| Gửi CloudWatch Logs từ thành phần dùng Logs API | Interface `logs` | Một hoặc nhiều AZ theo SLO, private DNS | SG, IAM Logs permissions, retention/cost |
| Xác thực, gọi dịch vụ bổ sung | Xem xét endpoint khác như STS/KMS/SSM khi thực sự có nhu cầu | Theo luồng API và tài liệu từng dịch vụ | Không thêm endpoint chỉ để “đủ danh sách” |

**Phân tích đánh đổi:**

- Hai gateway endpoint không tính phí riêng nên thường phù hợp S3/DynamoDB nội vùng.
- Mỗi interface endpoint bổ sung có thể làm tăng chi phí theo giờ và lưu lượng; chỉ tạo khi API thực sự cần.
- Có hai AZ giúp giảm rủi ro phụ thuộc một AZ, nhưng cần cơ chế retry và khả năng phục hồi ở tầng ứng dụng.
- Nếu ứng dụng có đường egress khác, việc dùng VPC endpoint không tự buộc toàn bộ lưu lượng tới AWS API đi qua endpoint; policy và cấu hình DNS phải phù hợp.
- Để giám sát chi phí, gắn tag cho tài nguyên hỗ trợ, bật báo cáo Billing/Cost Explorer theo quyền được cấp, đặt cảnh báo Budget và dọn tài nguyên không dùng.
- Trước khi công bố “không cần NAT”, liệt kê **tất cả dependency**: container registry, image pull, package mirror, telemetry, authentication, API ngoài AWS và các tính năng hỗ trợ; có thể cần thêm endpoint hoặc egress khác tùy hệ thống.

## 10. Những hiểu lầm cần tránh

**“Gateway endpoint là một máy ảo gateway trong subnet.”** Sai. Nó là đích route do AWS quản lý; không có endpoint ENI hay security group của riêng loại gateway endpoint.

**“Có interface endpoint thì tự động dùng hostname dịch vụ chuẩn.”** Chỉ khi DNS của endpoint/dịch vụ được cấu hình đúng. Nếu không, cần endpoint-specific DNS name và routing phù hợp.

**“Tạo endpoint là đã cho phép mọi API.”** Sai. IAM policy và các giới hạn khác vẫn quyết định quyền, còn endpoint policy là lớp kiểm soát bổ sung khi dịch vụ hỗ trợ.

**“S3 luôn phải dùng interface endpoint để truy cập riêng.”** Sai. Gateway endpoint là lựa chọn phổ biến, không tính phí endpoint, cho S3 cùng Region từ workload trong VPC.

**“Gateway endpoint từ VPC A có thể được chia sẻ cho VPC B qua peering.”** Sai. Gateway endpoint không hỗ trợ truy cập theo đường đó; cần cân nhắc endpoint riêng tại VPC B hoặc thiết kế khác.

**“Interface endpoint không có chi phí vì không dùng NAT.”** Sai. Interface endpoint thường tính theo AZ/giờ và dung lượng dữ liệu xử lý.

**“Chỉ cần endpoint ở một AZ là ứng dụng nhiều AZ luôn chịu lỗi tốt.”** Sai. Điều này có thể tạo phụ thuộc vào AZ đặt endpoint ENI; cần chọn AZ và kế hoạch phục hồi theo mức sẵn sàng yêu cầu.

## 11. Tự kiểm tra kiến thức

1. Vì sao S3 gateway endpoint cần liên kết route table, trong khi interface endpoint thường cần private DNS và security group?
2. Khi EC2 không có public IP, route table cũng không có NAT, nó vẫn có thể đọc S3 qua gateway endpoint trong điều kiện nào?
3. Vì sao `aws:SourceVpce` trong bucket policy có thể khiến AWS Console không truy cập được bucket?
4. Trong kiến trúc hai AZ, cần cân nhắc điểm gì khi chỉ tạo một interface endpoint ENI ở một AZ?
5. Khi interface endpoint đã `available` nhưng API trả `AccessDenied`, đâu là các policy nên rà soát?
6. Khi nào nên chọn S3 interface endpoint thay vì gateway endpoint?
7. Endpoint policy có thể thay IAM role policy để cấp `secretsmanager:GetSecretValue` cho Lambda không?
8. Một dịch vụ không hỗ trợ VPC endpoint cần truy cập Internet, ứng dụng cần loại đường mạng nào? Vì sao NAT Gateway không nhất thiết thay thế các endpoint chuyên dụng?
9. Nếu dự án dùng CloudWatch Logs và một số dịch vụ AWS khác, làm sao ước tính chi phí giao tiếp riêng trước khi tạo tất cả endpoints?

**Tiêu chí hoàn thành:** bạn có thể mô tả đúng **đường đi packet**, lựa chọn endpoint theo dịch vụ và phạm vi mạng, xác định chính sách cho phép API, kiểm thử trên sandbox và dọn tài nguyên tránh chi phí không cần thiết.

## Tài liệu AWS chính thức để tra cứu

- [Access an AWS service using an interface VPC endpoint](https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html)
- [Gateway endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html)
- [Gateway endpoints for Amazon S3](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html)
- [Gateway endpoints for DynamoDB](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-ddb.html)
- [AWS PrivateLink concepts](https://docs.aws.amazon.com/vpc/latest/privatelink/concepts.html)
- [Interface endpoint DNS names](https://docs.aws.amazon.com/vpc/latest/privatelink/privatelink-access-aws-services.html)
- [VPC endpoint policies](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-access.html)
- [Amazon S3 interface endpoints](https://docs.aws.amazon.com/AmazonS3/latest/userguide/privatelink-interface-endpoints.html)
- [AWS PrivateLink pricing](https://aws.amazon.com/privatelink/pricing/)
- [AWS IAM policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)

> **Ghi chú khi thực hành:** Các ID, tên bucket, ví dụ CLI và JSON trong bài chỉ dùng để giải thích. Hãy kiểm tra hỗ trợ dịch vụ, Region/AZ, quyền IAM, DNS, mức giá và quy trình dọn tài nguyên hiện hành của AWS trước khi thay cấu hình trong một account thực tế.
