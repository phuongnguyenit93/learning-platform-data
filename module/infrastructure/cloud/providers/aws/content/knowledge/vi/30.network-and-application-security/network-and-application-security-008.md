# Bảo vệ luồng egress và truy cập dịch vụ qua endpoint

Trong VPC, **egress** là lưu lượng do tài nguyên bên trong mạng khởi tạo đi ra đích bên ngoài subnet hoặc VPC. Đích có thể là Internet, mạng tại chỗ, VPC khác, hoặc một dịch vụ AWS như Amazon S3, AWS Secrets Manager và Amazon CloudWatch. Thiết kế egress tốt cần trả lời hai câu hỏi: lưu lượng được phép đi theo đường nào, và workload được phép truy cập chính xác những đích nào?

VPC endpoint giúp workload gọi một số dịch vụ AWS qua mạng riêng của AWS mà không cần đi qua Internet Gateway hoặc NAT Gateway. Khi kết hợp endpoint với route table, security group, endpoint policy, IAM và cơ chế ghi log, đội vận hành có thể giảm bề mặt tấn công và kiểm soát quyền truy cập rõ ràng hơn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả đường đi của một kết nối egress và phân biệt vai trò của route table, security group, network ACL, NAT Gateway và firewall.
- Chọn cách cung cấp egress phù hợp cho IPv4, IPv6 và môi trường cần kiểm tra tập trung.
- Phân biệt Gateway endpoint, Interface endpoint và AWS PrivateLink.
- Thiết kế quyền truy cập endpoint bằng security group, endpoint policy, IAM policy và resource policy.
- Kiểm tra DNS, định tuyến, quyền và log khi workload không truy cập được dịch vụ.

## 1. Hiểu đường đi của lưu lượng egress

Một kết nối outbound thường bắt đầu từ ENI của EC2 instance, task ECS, pod EKS hoặc một tài nguyên khác trong subnet. AWS đánh giá các lớp kiểm soát trên đường đi, sau đó route table chọn next hop phù hợp. Tùy kiến trúc, next hop có thể là NAT Gateway, Internet Gateway, egress-only Internet Gateway, VPC endpoint, Transit Gateway hoặc firewall endpoint.

Ví dụ, một EC2 instance trong private subnet gọi API của một dịch vụ công khai trên Internet:

1. Ứng dụng tạo kết nối TCP tới địa chỉ đích, thường qua cổng 443.
2. Security group của ENI kiểm tra quy tắc outbound. Security group là stateful nên lưu lượng phản hồi của kết nối được phép tự động đi qua.
3. Network ACL của subnet kiểm tra lưu lượng outbound. Network ACL là stateless nên phải có quy tắc phù hợp cho cả chiều đi và chiều về.
4. Route table của subnet chọn tuyến khớp cụ thể nhất. Tuyến mặc định IPv4 thường là `0.0.0.0/0` trỏ tới NAT Gateway.
5. NAT Gateway chuyển đổi địa chỉ nguồn private IPv4 thành địa chỉ công khai của NAT Gateway để kết nối ra Internet.
6. Gói phản hồi quay lại NAT Gateway, được ánh xạ về địa chỉ và cổng của workload, rồi đi vào subnet.

Đường đi thực tế có thể phức tạp hơn khi có firewall tập trung, proxy, Transit Gateway hoặc nhiều VPC. Khi thiết kế, hãy xác định rõ từng hop và bảo đảm đường đi, đường về đối xứng theo yêu cầu của thiết bị kiểm tra trạng thái.

### Các lớp kiểm soát và trách nhiệm

| Thành phần | Phạm vi kiểm soát | Vai trò chính |
|---|---|---|
| Route table | Subnet | Chọn next hop cho địa chỉ đích; không tự xác thực danh tính hay nội dung ứng dụng |
| Security group | ENI hoặc tài nguyên được hỗ trợ | Lọc inbound/outbound theo giao thức, cổng và nguồn/đích; stateful |
| Network ACL | Subnet | Lọc stateless theo IP, giao thức và cổng; phải cho phép cả chiều đi và chiều về |
| NAT Gateway | Đường đi IPv4 | Cho phép tài nguyên private khởi tạo kết nối ra ngoài bằng cơ chế dịch địa chỉ; không phải firewall lọc ứng dụng |
| VPC endpoint | Kết nối tới dịch vụ được hỗ trợ | Đưa lưu lượng tới dịch vụ qua mạng riêng của AWS |
| AWS Network Firewall | Vị trí được định tuyến qua firewall | Kiểm tra và lọc lưu lượng mạng theo luật stateless/stateful |
| Route 53 Resolver DNS Firewall | Truy vấn DNS qua Resolver | Cho phép hoặc chặn truy vấn tên miền theo rule group |
| IAM và resource policy | Danh tính và tài nguyên AWS | Quyết định principal được phép thực hiện API/action nào |

Không một thành phần đơn lẻ nào thay thế tất cả các lớp còn lại. Route table chọn đường; security group và network ACL lọc lưu lượng IP; IAM kiểm soát hành động trên dịch vụ AWS.

## 2. Những cách cung cấp egress phổ biến

### 2.1. Public subnet đi qua Internet Gateway

Một tài nguyên IPv4 trong public subnet có thể truy cập Internet trực tiếp khi đồng thời thỏa mãn các điều kiện:

- Route table của subnet có tuyến `0.0.0.0/0` tới Internet Gateway đã gắn với VPC.
- Tài nguyên có public IPv4 hoặc Elastic IP phù hợp.
- Security group, network ACL và cấu hình hệ điều hành cho phép kết nối.

Tên gọi public subnet chỉ phản ánh route table có tuyến tới Internet Gateway. Một EC2 instance không có public IPv4 vẫn không tự động có đường IPv4 trực tiếp tới Internet.

Đặt workload trực tiếp trong public subnet thường phù hợp với thành phần cần nhận kết nối Internet, chẳng hạn load balancer công khai. Với máy chủ ứng dụng, worker và cơ sở dữ liệu, private subnet thường là lựa chọn an toàn hơn.

### 2.2. Private subnet đi ra IPv4 qua NAT Gateway

NAT Gateway công khai thường được đặt trong public subnet. Route table của public subnet phải có tuyến tới Internet Gateway; route table của private subnet trỏ tuyến mặc định IPv4 tới NAT Gateway.

~~~text
Private subnet
  EC2 / ECS task
       |
  Route 0.0.0.0/0
       |
  Public NAT Gateway
       |
  Internet Gateway
       |
    Internet
~~~

NAT Gateway cho phép workload trong private subnet khởi tạo kết nối outbound. Thiết bị bên ngoài không thể tự khởi tạo một kết nối mới tới workload thông qua NAT Gateway chỉ bằng cách biết địa chỉ công khai của NAT Gateway.

NAT Gateway **không phải bộ lọc đích ở tầng ứng dụng**. Nó không cung cấp chính sách allowlist tên miền hoặc kiểm tra nội dung HTTP như một proxy hay firewall có khả năng nhận biết ứng dụng. Nếu yêu cầu chỉ cho phép workload gọi một nhóm dịch vụ cụ thể, hãy kết hợp NAT với security group, AWS Network Firewall, proxy và các chính sách ở tầng ứng dụng khi phù hợp.

Trong môi trường nhiều Availability Zone, nên triển khai NAT Gateway theo từng AZ và để private subnet ưu tiên NAT Gateway cùng AZ. Cách này giảm phụ thuộc vào một AZ và tránh lưu lượng đi xuyên AZ không cần thiết. Nếu dùng NAT Gateway ở AZ khác, workload có thể tiếp tục truy cập khi NAT Gateway cục bộ không khả dụng, nhưng đường đi và chi phí truyền dữ liệu liên AZ cần được tính đến.

### 2.3. Private subnet đi ra IPv6 qua egress-only Internet Gateway

IPv6 không dùng NAT Gateway theo cách IPv4 thường dùng. Nếu workload có địa chỉ IPv6 toàn cục và chỉ cần khởi tạo kết nối ra Internet, có thể dùng egress-only Internet Gateway.

Route table có tuyến `::/0` tới egress-only Internet Gateway. Thành phần này cho phép kết nối IPv6 outbound và lưu lượng phản hồi thuộc kết nối đã được khởi tạo từ bên trong, đồng thời chặn kết nối IPv6 mới khởi tạo từ Internet vào VPC.

Security group và network ACL vẫn cần được cấu hình phù hợp. Egress-only Internet Gateway không thay thế các lớp kiểm soát đó.

### 2.4. Egress tập trung qua firewall hoặc proxy

Tổ chức có thể định tuyến lưu lượng outbound qua AWS Network Firewall hoặc proxy tập trung để áp dụng chính sách chung, ghi log và kiểm tra lưu lượng. Mô hình thường dùng Transit Gateway hoặc các route table được thiết kế để chuyển lưu lượng từ workload tới firewall trước khi tới NAT Gateway hoặc đích riêng.

~~~mermaid
flowchart LR
    A["Workload trong private subnet"] --> B["Route table"]
    B --> C["Firewall endpoint"]
    C --> D{"Đích được phép?"}
    D -->|Có| E["NAT Gateway hoặc tuyến riêng"]
    D -->|Không| F["Chặn và ghi log"]
    E --> G["Internet hoặc mạng đích"]
~~~

Khi triển khai, cần kiểm tra:

- Mọi tuyến outbound cần kiểm tra đều thực sự đi qua firewall.
- Đường phản hồi quay lại đúng thiết bị có trạng thái kết nối, tránh định tuyến bất đối xứng.
- Firewall endpoint được triển khai và định tuyến phù hợp trên các AZ cần bảo vệ.
- Chính sách cho phép DNS, cập nhật hệ điều hành, dịch vụ AWS và các phụ thuộc ứng dụng cần thiết.
- Log được gửi tới đích lưu trữ và giám sát phù hợp.

Route 53 Resolver DNS Firewall có thể chặn truy vấn tới tên miền không được phép khi workload sử dụng Route 53 Resolver. Nó không thay thế firewall mạng: ứng dụng có thể dùng địa chỉ IP trực tiếp hoặc một DNS resolver khác nếu kiến trúc không kiểm soát các đường đó.

## 3. Kiểm soát egress theo nhiều lớp

Một chính sách egress có hiệu quả thường kết hợp các lớp sau:

**Security group:** Giới hạn outbound theo giao thức, cổng và đích. Với ứng dụng chỉ cần gọi HTTPS tới endpoint trong cùng VPC, có thể cho phép TCP 443 tới security group gắn với Interface endpoint. Quy tắc tham chiếu security group giúp tránh phải duy trì danh sách địa chỉ IP của ENI endpoint.

**Network ACL:** Dùng để bổ sung ranh giới lọc ở subnet. Vì stateless, cần cho phép cổng dịch vụ ở chiều outbound và cổng ephemeral phù hợp ở chiều inbound cho phản hồi, đồng thời xem xét chiều ngược lại. Network ACL không hiểu danh tính IAM hay tên API.

**Route table:** Chỉ định lưu lượng đi qua endpoint, NAT, firewall hoặc mạng kết nối. Một tuyến cụ thể hơn có thể được ưu tiên so với tuyến mặc định. Route table không tự chặn một request theo tên miền hoặc API action.

**AWS Network Firewall hoặc proxy:** Áp dụng chính sách mạng và kiểm tra sâu hơn khi yêu cầu bảo mật cần lọc theo giao thức, tên miền hoặc đặc điểm luồng. Cần kiểm tra khả năng quan sát thực tế với TLS và giao thức ứng dụng được dùng.

**DNS Firewall:** Giới hạn tên miền mà workload có thể phân giải qua Route 53 Resolver. Cần kiểm soát các đường DNS khác nếu muốn chính sách có hiệu lực nhất quán.

**IAM và resource policy:** Giới hạn API/action mà principal được phép thực hiện trên dịch vụ AWS. Ví dụ, một EC2 instance có thể có đường mạng tới S3 nhưng IAM role chỉ được phép đọc một bucket nhất định.

**Chính sách ứng dụng:** Xác thực đầu vào, kiểm soát đích gọi ra và quản lý timeout/retry. Chính sách mạng không thay thế kiểm tra dữ liệu hoặc xác thực ở tầng ứng dụng.

AWS WAF chủ yếu bảo vệ ứng dụng web và API trước lưu lượng HTTP/S đi vào tài nguyên được hỗ trợ. Không nên xem AWS WAF là giải pháp lọc egress tổng quát cho mọi giao thức.

## 4. Truy cập dịch vụ AWS bằng VPC endpoint

VPC endpoint tạo đường kết nối giữa VPC và một dịch vụ hoặc tài nguyên được hỗ trợ. Với endpoint phù hợp, workload có thể truy cập dịch vụ qua mạng riêng của AWS mà không cần tuyến Internet cho request đó.

Lợi ích thường gặp:

- Giảm nhu cầu dùng NAT Gateway cho lưu lượng tới dịch vụ AWS được hỗ trợ.
- Hạn chế việc phụ thuộc vào Internet Gateway và địa chỉ IP công khai.
- Có thể giới hạn quyền truy cập qua endpoint policy, IAM policy và resource policy.
- Giảm số đường egress cần mở và đơn giản hóa thiết kế mạng.

VPC endpoint không tự động làm cho toàn bộ VPC trở thành mạng riêng tuyệt đối. Các luồng khác vẫn có thể đi theo tuyến Internet hoặc mạng kết nối nếu route table cho phép.

### 4.1. Gateway endpoint

Gateway endpoint hiện được dùng cho Amazon S3 và Amazon DynamoDB. Khi tạo endpoint, bạn chọn các route table cần gắn. AWS thêm tuyến sử dụng managed prefix list của dịch vụ để lưu lượng tới các dải địa chỉ dịch vụ được chuyển qua gateway endpoint.

Đặc điểm:

- Không tạo ENI trong subnet.
- Không gắn security group trực tiếp vào endpoint.
- Phải gắn endpoint với route table của các subnet cần truy cập.
- Endpoint policy có thể giới hạn hành động và tài nguyên được truy cập qua endpoint, nếu dịch vụ hỗ trợ.
- Gateway endpoint không cần NAT Gateway hoặc Internet Gateway cho lưu lượng dịch vụ đi qua endpoint.
- Gateway endpoint có phạm vi Region và VPC; không phải đường truy cập tổng quát từ mạng on-premises qua VPN hoặc Direct Connect.

Ví dụ: EC2 trong private subnet cần đọc object từ một S3 bucket. Gắn S3 Gateway endpoint vào route table của private subnet giúp request tới S3 đi qua endpoint. EC2 vẫn cần IAM role cho phép `s3:GetObject`, và bucket policy có thể tiếp tục giới hạn principal hoặc điều kiện truy cập.

### 4.2. Interface endpoint và AWS PrivateLink

Interface endpoint được cung cấp bằng AWS PrivateLink. AWS tạo một hoặc nhiều elastic network interface (ENI) trong các subnet bạn chọn. Mỗi ENI có địa chỉ IP private để workload kết nối tới dịch vụ.

Đặc điểm:

- Có thể dùng cho nhiều dịch vụ AWS, dịch vụ do đối tác cung cấp và endpoint service do tổ chức tự công bố, tùy dịch vụ hỗ trợ.
- Có security group gắn với ENI endpoint.
- Có thể bật Private DNS để tên dịch vụ AWS chuẩn được phân giải thành địa chỉ private của endpoint trong VPC.
- Nên chọn subnet ở nhiều AZ cần phục vụ để tăng khả năng sẵn sàng.
- Thường có chi phí theo thời gian endpoint hoạt động và dữ liệu xử lý; cần kiểm tra bảng giá theo Region và dịch vụ.

Ví dụ: ứng dụng trong private subnet gọi AWS Secrets Manager. Tạo Interface endpoint cho Secrets Manager trong các AZ cần thiết, bật Private DNS, rồi cho phép TCP 443 từ security group của ứng dụng vào security group của endpoint. Ứng dụng tiếp tục gọi SDK bằng hostname dịch vụ thông thường; DNS trong VPC phân giải hostname đó về địa chỉ private của endpoint khi cấu hình phù hợp.

PrivateLink cũng cho phép một nhà cung cấp công bố dịch vụ riêng dưới dạng endpoint service. Bên cung cấp thường đặt dịch vụ phía sau Network Load Balancer hoặc Gateway Load Balancer theo mô hình hỗ trợ; bên tiêu thụ tạo Interface endpoint trong VPC của mình. Hai bên có thể kết nối dịch vụ mà không cần công khai dịch vụ lên Internet hoặc thiết lập kết nối mạng ngang hàng giữa toàn bộ hai VPC.

### 4.3. So sánh Gateway endpoint và Interface endpoint

| Tiêu chí | Gateway endpoint | Interface endpoint |
|---|---|---|
| Cơ chế | Tuyến trong route table qua managed prefix list | ENI có địa chỉ IP private trong subnet |
| Dịch vụ tiêu biểu | S3, DynamoDB | Secrets Manager, CloudWatch, Systems Manager và nhiều dịch vụ khác |
| Security group | Không gắn trực tiếp | Gắn với ENI endpoint |
| DNS riêng | Không cần Private DNS để định tuyến gateway endpoint | Có thể bật Private DNS cho hostname dịch vụ |
| Cấu hình chính | Chọn VPC và route table | Chọn VPC, subnet, security group và tùy chọn DNS |
| Chi phí | Không tính phí endpoint riêng cho Gateway endpoint; vẫn có phí dịch vụ và truyền dữ liệu áp dụng | Thường tính theo giờ endpoint/AZ và dữ liệu xử lý |
| Phạm vi sử dụng | Chủ yếu từ tài nguyên trong VPC gắn route table | Linh hoạt hơn với dịch vụ AWS và endpoint service qua PrivateLink |

Danh sách dịch vụ, loại endpoint và khả năng áp dụng có thể thay đổi theo Region. Trước khi triển khai, hãy xác nhận dịch vụ có hỗ trợ loại endpoint mong muốn và đọc hướng dẫn riêng của dịch vụ.

## 5. Bảo vệ endpoint bằng chính sách và mạng

Một endpoint hoạt động tốt cần có cả đường mạng và quyền truy cập. Hãy kiểm tra từng lớp theo thứ tự sau.

### 5.1. Endpoint policy

Endpoint policy là resource policy gắn vào VPC endpoint để giới hạn những principal, action hoặc resource có thể đi qua endpoint. Endpoint policy không tự cấp quyền IAM cho người gọi và không ghi đè một lệnh Deny từ IAM policy hoặc resource policy. Dịch vụ phải hỗ trợ endpoint policy thì cấu hình này mới có tác dụng.

Ví dụ, endpoint policy cho S3 chỉ cho phép đọc object trong bucket `company-artifacts`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowReadObjectsFromApprovedBucket",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::company-artifacts/*"
    },
    {
      "Sid": "AllowListApprovedBucket",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::company-artifacts"
    }
  ]
}
~~~

Đây là ví dụ giới hạn request đi qua endpoint. IAM role của workload vẫn cần quyền tương ứng, và bucket policy vẫn có thể áp dụng điều kiện riêng. Nếu workload có một đường khác tới S3, endpoint policy không tự động kiểm soát request đi theo đường đó.

Trong môi trường nhiều tài khoản, hãy cân nhắc giới hạn principal hoặc điều kiện tài khoản phù hợp thay vì dựa vào `Principal: "*"` nếu yêu cầu quản trị cần ràng buộc chặt hơn.

### 5.2. IAM policy và resource policy

IAM policy gắn với role hoặc user quyết định danh tính được phép gọi action nào. Resource policy gắn với tài nguyên, chẳng hạn S3 bucket policy, quyết định ai được truy cập tài nguyên và theo điều kiện nào.

Ví dụ, role của ứng dụng chỉ cần đọc object từ một prefix cụ thể. Hãy giới hạn `s3:GetObject` theo ARN prefix cần dùng và chỉ cấp `s3:ListBucket` khi ứng dụng thực sự cần liệt kê. Tránh cấp `s3:*` hoặc quyền trên mọi bucket chỉ để khắc phục lỗi truy cập.

### 5.3. Security group của Interface endpoint

Interface endpoint có ENI, vì vậy security group gắn với endpoint kiểm soát lưu lượng đi vào ENI đó. Với HTTPS, một cấu hình thường gặp là:

- Security group của ứng dụng cho phép outbound TCP 443 tới security group của endpoint.
- Security group của endpoint cho phép inbound TCP 443 từ security group của ứng dụng.
- Network ACL của hai subnet cho phép chiều request và response, bao gồm cổng ephemeral cần thiết.

Nếu ứng dụng và endpoint nằm ở các VPC hoặc mạng kết nối khác nhau, cần xem xét cơ chế tham chiếu security group và phạm vi hỗ trợ tương ứng; nếu không hỗ trợ, dùng CIDR phù hợp và quản lý thay đổi cẩn thận.

### 5.4. DNS và Private DNS

Với Interface endpoint, bật Private DNS giúp workload dùng hostname dịch vụ quen thuộc thay vì phải tự quản lý hostname endpoint. Để tính năng hoạt động, VPC cần bật DNS resolution và DNS hostnames theo yêu cầu của dịch vụ.

Nếu DNS trả về địa chỉ công khai thay vì địa chỉ private của endpoint, hãy kiểm tra:

- Private DNS đã bật trên endpoint chưa.
- Dịch vụ và Region có hỗ trợ Private DNS không.
- DNS resolution và DNS hostnames của VPC đã bật chưa.
- Workload có đang dùng DNS resolver tùy chỉnh hoặc cache kết quả cũ không.
- Có private hosted zone hoặc cấu hình DNS nào xung đột với hostname dịch vụ không.

Gateway endpoint cho S3/DynamoDB hoạt động theo tuyến route table và managed prefix list; nó không cần tạo ENI hoặc Private DNS như Interface endpoint.

## 6. Quy trình thiết kế một luồng truy cập

Hãy dùng quy trình sau cho mỗi loại workload:

1. **Xác định đích:** Workload cần gọi Internet, dịch vụ AWS, mạng nội bộ hay dịch vụ riêng của đối tác?
2. **Xác định giao thức:** Ghi rõ TCP/UDP, cổng, IPv4/IPv6, hostname và Region. Không mở mọi cổng nếu ứng dụng chỉ cần HTTPS.
3. **Chọn đường đi:** Dùng Gateway endpoint cho S3/DynamoDB khi phù hợp; Interface endpoint cho dịch vụ hỗ trợ PrivateLink; NAT cho egress IPv4 tổng quát; egress-only Internet Gateway cho IPv6 outbound; firewall/proxy khi cần kiểm tra tập trung.
4. **Giới hạn nguồn:** Chỉ cho phép workload hoặc security group cần thiết truy cập endpoint. Giảm quyền outbound rộng ở các security group liên quan.
5. **Giới hạn quyền dịch vụ:** Cấp IAM action và resource tối thiểu; bổ sung endpoint policy và resource policy khi dịch vụ hỗ trợ và yêu cầu bảo mật cần đến.
6. **Kiểm tra DNS:** Xác nhận hostname phân giải theo thiết kế, đặc biệt với Interface endpoint và Private DNS.
7. **Bật quan sát:** Dùng VPC Flow Logs để xem luồng IP được chấp nhận hoặc từ chối; dùng log của Network Firewall để điều tra rule; dùng Route 53 Resolver query logging cho truy vấn DNS; dùng CloudTrail để kiểm tra lời gọi API AWS.
8. **Kiểm thử cả đường hợp lệ và đường bị cấm:** Xác nhận workload gọi được dịch vụ cần thiết, đồng thời không truy cập được tài nguyên hoặc đích ngoài phạm vi cho phép.
9. **Đánh giá khả năng sẵn sàng và chi phí:** Kiểm tra endpoint/NAT theo AZ, lưu lượng liên AZ, phí dữ liệu và số lượng endpoint cần triển khai.

## 7. Ví dụ triển khai

### 7.1. Tạo S3 Gateway endpoint cho private subnet

Ví dụ AWS CLI dưới đây tạo S3 Gateway endpoint trong một VPC và gắn vào hai route table của private subnet. Thay các giá trị placeholder bằng ID thực tế trong cùng Region.

~~~bash
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.<REGION>.s3 \
  --vpc-endpoint-type Gateway \
  --route-table-ids <PRIVATE_ROUTE_TABLE_ID_1> <PRIVATE_ROUTE_TABLE_ID_2>
~~~

Sau khi tạo, kiểm tra endpoint ở trạng thái `available`, route table có tuyến sử dụng prefix list của S3 và workload có IAM permission phù hợp. Nếu muốn giới hạn bucket qua endpoint, gắn endpoint policy đã được rà soát.

### 7.2. Tạo Secrets Manager Interface endpoint

Ví dụ sau tạo Interface endpoint cho Secrets Manager, đặt ENI vào hai subnet và bật Private DNS:

~~~bash
aws ec2 create-vpc-endpoint \
  --vpc-id <VPC_ID> \
  --service-name com.amazonaws.<REGION>.secretsmanager \
  --vpc-endpoint-type Interface \
  --subnet-ids <PRIVATE_SUBNET_ID_A> <PRIVATE_SUBNET_ID_B> \
  --security-group-ids <ENDPOINT_SECURITY_GROUP_ID> \
  --private-dns-enabled
~~~

Security group của endpoint phải cho phép inbound TCP 443 từ workload cần truy cập. Security group của workload phải cho phép outbound tương ứng. Role của ứng dụng cần action Secrets Manager tối thiểu, chẳng hạn `secretsmanager:GetSecretValue` trên secret cụ thể. Nếu secret dùng customer managed KMS key, kiểm tra thêm quyền giải mã cần thiết với key policy và IAM policy.

### 7.3. Kiểm tra từ workload

Có thể kiểm tra phân giải DNS và kết nối TCP 443 từ môi trường chạy ứng dụng:

~~~bash
nslookup secretsmanager.<REGION>.amazonaws.com
curl -I https://secretsmanager.<REGION>.amazonaws.com
~~~

Kết quả DNS cần phù hợp với thiết kế Private DNS. Lệnh HTTP chỉ kiểm tra khả năng kết nối ở tầng mạng/HTTP; nó không chứng minh principal có quyền gọi API. Để xác minh quyền, hãy gọi API bằng AWS CLI hoặc SDK với đúng role của workload và một secret được phép truy cập. Không in giá trị secret ra log hoặc terminal khi kiểm tra.

## 8. Quan sát và xử lý sự cố

Khi workload không gọi được dịch vụ, phân loại lỗi trước khi thay đổi rule. Timeout thường gợi ý vấn đề đường mạng, DNS hoặc firewall; phản hồi AccessDenied thường cho thấy request đã tới dịch vụ nhưng thiếu quyền hoặc bị policy từ chối. Đây là dấu hiệu định hướng, không phải kết luận tuyệt đối.

| Triệu chứng | Lớp cần kiểm tra | Cách xác minh |
|---|---|---|
| Timeout khi gọi dịch vụ | Route table, security group, network ACL, firewall | Kiểm tra route của subnet, outbound của workload, inbound của endpoint ENI và Flow Logs |
| Hostname phân giải ra IP không mong đợi | Private DNS, VPC DNS, resolver tùy chỉnh | Dùng `nslookup` hoặc `dig`; kiểm tra cấu hình endpoint và DNS |
| Interface endpoint không kết nối được | Endpoint state, subnet, AZ, security group | Xác nhận endpoint `available`, ENI tồn tại và TCP 443 được phép |
| S3 request đi qua NAT thay vì Gateway endpoint | Route table, prefix list, subnet association | Kiểm tra route table thực sự gắn với subnet và có tuyến prefix list S3 |
| API trả về AccessDenied | IAM, endpoint policy, resource policy, KMS key policy | Kiểm tra principal, action, ARN, condition và các explicit Deny |
| Chỉ một AZ bị lỗi | ENI endpoint, NAT/firewall theo AZ, route table | So sánh subnet, route và endpoint ENI giữa các AZ |
| DNS phân giải được nhưng kết nối thất bại | Security group, NACL, route, firewall | Kiểm tra TCP 443 và cổng ephemeral cho phản hồi |
| Kết nối được nhưng API thất bại | Xác thực, IAM, resource policy, request | Kiểm tra CloudTrail và thông báo lỗi API |

Các nguồn quan sát có vai trò khác nhau:

- **VPC Flow Logs** ghi lại thông tin luồng IP ở ENI, subnet hoặc VPC. Chúng hữu ích để tìm luồng `ACCEPT` hoặc `REJECT`, nhưng không cung cấp đầy đủ URL, nội dung request hay danh tính IAM của mỗi lời gọi API.
- **AWS Network Firewall logs** hỗ trợ điều tra lưu lượng đi qua firewall và rule đã xử lý.
- **Route 53 Resolver query logs** cho biết truy vấn DNS được gửi tới Resolver, hữu ích khi điều tra domain bị chặn hoặc phân giải sai.
- **AWS CloudTrail** ghi nhận hoạt động API của nhiều dịch vụ AWS, hỗ trợ xác định principal, action, tài nguyên và kết quả.
- **CloudWatch metrics** của NAT Gateway và các thành phần mạng giúp phát hiện thay đổi lưu lượng, lỗi cấp phát cổng hoặc gói bị loại bỏ. Chọn metric theo thành phần thực tế đang dùng.

Không nên mở outbound toàn bộ chỉ để kiểm tra lỗi. Hãy thay đổi từng lớp có giả thuyết rõ ràng, chạy lại phép thử và thu hẹp cấu hình sau khi xác định nguyên nhân.

## 9. Lỗi thiết kế thường gặp

**Cho rằng NAT Gateway tự lọc được tên miền.** NAT Gateway thực hiện dịch địa chỉ cho kết nối outbound IPv4. Muốn kiểm soát domain hoặc nội dung ứng dụng, cần dùng firewall/proxy và DNS control phù hợp.

**Tạo endpoint nhưng quên route table hoặc DNS.** Gateway endpoint cần gắn đúng route table. Interface endpoint cần DNS và security group đúng; chỉ tạo endpoint chưa bảo đảm ứng dụng sẽ tự dùng nó.

**Cho rằng endpoint policy cấp quyền truy cập.** Endpoint policy chỉ là một lớp lọc request qua endpoint. IAM policy, resource policy và key policy vẫn có thể từ chối request.

**Mở security group endpoint cho toàn bộ VPC.** Điều này có thể khiến nhiều workload không liên quan truy cập được endpoint ở tầng mạng. Hãy chỉ cho phép security group hoặc CIDR cần thiết.

**Quên tính đến network ACL stateless.** Cho phép cổng 443 outbound nhưng chặn cổng ephemeral inbound có thể khiến kết nối không hoàn tất.

**Dùng một NAT Gateway cho mọi AZ mà không đánh giá tác động.** Cách này tạo phụ thuộc vào AZ chứa NAT Gateway và có thể phát sinh lưu lượng liên AZ. Hãy so sánh chi phí với yêu cầu sẵn sàng.

**Nghĩ rằng VPC endpoint thay thế mọi egress.** Endpoint chỉ phục vụ dịch vụ/tài nguyên được hỗ trợ. Các đích Internet hoặc dịch vụ không có endpoint vẫn cần đường đi khác theo chính sách.

**Không kiểm tra đường đi thay thế.** Endpoint policy không ngăn request đi qua NAT hoặc một đường mạng khác nếu route và quyền vẫn cho phép. Nếu yêu cầu bắt buộc mọi truy cập tới dịch vụ phải qua endpoint, cần thiết kế IAM/resource policy và egress route để hạn chế đường vòng.

## 10. Bài tập tình huống

Một hệ thống xử lý đơn hàng chạy trên EC2 trong private subnet. Ứng dụng cần:

- Đọc tệp cấu hình từ một S3 bucket xác định.
- Lấy mật khẩu cơ sở dữ liệu từ Secrets Manager.
- Gửi thông báo tới một API đối tác công khai qua HTTPS.
- Không cho phép máy chủ nhận kết nối mới trực tiếp từ Internet.

Hãy đề xuất kiến trúc và giải thích lựa chọn của bạn.

Một phương án hợp lý:

1. Tạo S3 Gateway endpoint và gắn vào route table của các private subnet chạy ứng dụng.
2. Tạo Secrets Manager Interface endpoint trong các AZ cần phục vụ, bật Private DNS và giới hạn TCP 443 từ security group của ứng dụng.
3. Cấp IAM role cho EC2 chỉ có quyền đọc object trong bucket/prefix cần thiết và lấy đúng secret; giới hạn endpoint policy và bucket/secret resource policy khi phù hợp.
4. Định tuyến kết nối tới API đối tác qua NAT Gateway hoặc egress firewall/proxy. Nếu tổ chức cần allowlist domain, ghi log hoặc kiểm tra tập trung, đưa firewall/proxy vào đường đi và xác nhận mọi route cần kiểm tra đều đi qua đó.
5. Không gán public IPv4 cho EC2; không có tuyến inbound công khai tới instance. Security group chỉ cho phép inbound từ thành phần nội bộ cần thiết và giới hạn outbound theo nhu cầu.
6. Bật VPC Flow Logs, CloudTrail và log firewall/DNS tương ứng; kiểm thử truy cập hợp lệ và truy cập bị cấm.

Khi đánh giá phương án, hãy nêu rõ request S3 và Secrets Manager đi qua endpoint, request tới API đối tác đi qua egress Internet, và quyền IAM vẫn được kiểm tra độc lập với đường mạng.

## 11. Checklist trước khi đưa vào vận hành

- [ ] Mỗi workload có danh sách đích, giao thức và cổng outbound rõ ràng.
- [ ] Route table của từng subnet trỏ đúng endpoint, NAT, firewall hoặc gateway.
- [ ] Gateway endpoint được gắn vào mọi route table cần dùng.
- [ ] Interface endpoint có ENI ở các AZ cần phục vụ và security group giới hạn nguồn.
- [ ] Private DNS được bật và kiểm tra bằng truy vấn từ workload.
- [ ] Security group và network ACL cho phép đúng chiều request/response.
- [ ] IAM, endpoint policy, resource policy và KMS key policy không cấp quyền rộng hơn yêu cầu.
- [ ] Các đường egress thay thế không làm vô hiệu chính sách endpoint.
- [ ] Firewall/DNS logging, VPC Flow Logs và CloudTrail được cấu hình theo nhu cầu điều tra.
- [ ] Đã kiểm thử cả request được phép, request bị từ chối và khả năng phục hồi khi một AZ gặp sự cố.
- [ ] Chi phí endpoint, NAT, firewall và truyền dữ liệu liên AZ đã được đánh giá.

## Kết luận

Thiết kế egress an toàn bắt đầu từ việc biết workload cần gọi tới đâu và chọn đường đi phù hợp cho từng loại đích. NAT Gateway đáp ứng nhu cầu outbound IPv4 tổng quát; egress-only Internet Gateway hỗ trợ outbound IPv6; firewall hoặc proxy giúp kiểm tra tập trung; VPC endpoint đưa lưu lượng tới dịch vụ AWS được hỗ trợ qua mạng riêng. Khi kết hợp các tuyến mạng với security group, network ACL, DNS, endpoint policy, IAM và resource policy, bạn có thể giới hạn cả đường đi lẫn hành động mà workload được phép thực hiện.

