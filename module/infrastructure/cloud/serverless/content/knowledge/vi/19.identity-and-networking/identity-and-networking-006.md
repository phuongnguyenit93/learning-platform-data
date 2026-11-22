# Private endpoint, egress và kiểm soát đường ra Internet

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt kết nối vào function (ingress) với kết nối từ function ra hệ thống khác (egress).
- Giải thích private endpoint, private IP, VPC/VNet integration, NAT và firewall trong kiến trúc serverless.
- Thiết kế đường truy cập riêng từ workload nội bộ đến HTTP function hoặc managed service.
- Kiểm soát đường ra Internet bằng route, NAT, firewall, proxy và allowlist.
- Kết nối Java function với database, object storage, API nội bộ và dịch vụ cloud qua mạng riêng.
- Nhận diện các lỗi DNS, route, IAM, security group, quota và giới hạn kết nối.
- Áp dụng các mẫu cấu hình phổ biến trên AWS Lambda và Google Cloud Run functions.

## 1. Vì sao serverless vẫn cần thiết kế mạng?

Serverless loại bỏ phần lớn công việc quản lý máy chủ, nhưng function vẫn phải giao tiếp với các hệ thống khác. Một Java function có thể nhận HTTP request từ ứng dụng, đọc dữ liệu trong database private, tải file từ object storage, gọi API của đối tác và phát message lên queue. Mỗi kết nối đều đi qua một đường mạng có quy tắc định tuyến, DNS, xác thực và kiểm soát truy cập riêng.

Nếu function chỉ gọi dịch vụ công khai, kiến trúc có thể đơn giản. Nhưng hệ thống production thường có yêu cầu:

- Database không được mở public Internet.
- Chỉ workload trong mạng doanh nghiệp mới được gọi một endpoint nội bộ.
- Function phải gọi API đối tác từ một IP egress cố định để đối tác allowlist.
- Mọi lưu lượng Internet phải đi qua firewall hoặc proxy để kiểm tra và ghi log.
- Dịch vụ cloud được truy cập qua private endpoint để tránh đi ra Internet công cộng.
- Các môi trường production, staging và development phải được phân tách mạng.
- Kết nối hybrid phải đi qua VPN hoặc đường truyền riêng tới data center.

Vì vậy, dù function được quản lý bởi nền tảng serverless, kiến trúc vẫn cần xác định function nhận lưu lượng từ đâu, gọi đi đâu, dùng địa chỉ nguồn nào và ai được phép thiết lập kết nối.

### 1.1. Ingress và egress là hai hướng khác nhau

**Ingress** là lưu lượng đi vào function hoặc dịch vụ. Ví dụ, một ứng dụng nội bộ gọi HTTP endpoint của function.

**Egress** là lưu lượng function khởi tạo đi ra ngoài. Ví dụ, function mở kết nối đến Cloud SQL, RDS, một API đối tác hoặc Internet.

~~~mermaid
flowchart LR
    A[Client nội bộ] -->|Ingress| B[HTTP function]
    B -->|Egress private| C[Private database]
    B -->|Egress Internet| D[NAT / Firewall]
    D --> E[API đối tác]
    B -->|Private service access| F[Managed cloud service]
~~~

Một cấu hình private ingress không tự động giới hạn egress. Tương tự, kết nối egress qua VPC không làm endpoint HTTP tự trở thành private. Hai hướng cần được thiết kế và kiểm tra độc lập.

### 1.2. Private endpoint là gì?

Private endpoint là điểm kết nối cho phép workload truy cập một dịch vụ qua mạng private, thường bằng địa chỉ IP private hoặc một cơ chế định tuyến riêng. Mục tiêu là giữ traffic trong phạm vi mạng được kiểm soát, giảm phụ thuộc vào public Internet và thu hẹp bề mặt phơi lộ dịch vụ.

Tùy cloud provider, cách triển khai có thể là:

- Private endpoint/interface endpoint gắn với network interface trong VPC.
- Gateway endpoint định tuyến traffic tới dịch vụ được quản lý mà không cần public IP.
- Private Service Connect endpoint hoặc service attachment.
- Internal load balancer đứng trước dịch vụ.
- Private DNS trỏ hostname dịch vụ tới địa chỉ private.
- Private link hoặc private endpoint cho database, storage và SaaS.

Private endpoint không đồng nghĩa với xác thực. Một client có thể kết nối được đến IP private nhưng vẫn cần IAM, database credential, TLS hoặc application authorization. Mạng và danh tính là hai lớp bảo vệ bổ sung cho nhau.

### 1.3. Mạng private không đồng nghĩa với không có Internet

Một function có thể đồng thời:

- Truy cập database bằng private IP.
- Gọi Google APIs hoặc AWS APIs qua private endpoint.
- Gọi API đối tác qua NAT với public IP cố định.
- Bị chặn truy cập các website hoặc destination không nằm trong allowlist.

Đây là kiến trúc thường gặp: đường nội bộ đi qua VPC, còn đường Internet được kiểm soát ở một điểm egress tập trung.

## 2. Các thành phần mạng cần nắm

### 2.1. VPC, subnet và route table

VPC là mạng logic riêng trong cloud. Subnet chia VPC thành các vùng địa chỉ IP và thường gắn với một zone hoặc region tùy dịch vụ. Route table quyết định gói tin đi tới destination nào thông qua next hop nào.

Ví dụ, một subnet có thể có:

| Destination | Next hop | Ý nghĩa |
|---|---|---|
| `10.20.0.0/16` | Local | Giao tiếp nội bộ trong VPC |
| `10.40.0.0/16` | Peering/VPN | Đến mạng kết nối khác |
| `0.0.0.0/0` | NAT Gateway | Egress IPv4 ra Internet |
| Prefix của dịch vụ cloud | VPC endpoint/PSC | Truy cập dịch vụ qua private path |

Route table chỉ quyết định đường đi. Nó không thay thế firewall, IAM hay kiểm tra TLS. Một route tồn tại không có nghĩa kết nối chắc chắn thành công; security group, firewall rule, network ACL, DNS và chính sách phía đích vẫn có thể chặn.

### 2.2. Private IP và public IP

Private IP dùng trong phạm vi mạng private hoặc các mạng được kết nối có route phù hợp. Public IP có thể được định tuyến trên Internet. Workload serverless thường không có public IP riêng ổn định theo từng invocation.

Khi đối tác yêu cầu allowlist IP nguồn, cần một điểm egress có địa chỉ public tĩnh, chẳng hạn NAT Gateway dùng Elastic IP trên AWS hoặc Cloud NAT dùng địa chỉ IP đã reserve trên Google Cloud. Function khởi tạo kết nối ra ngoài; địa chỉ public mà đối tác nhìn thấy là địa chỉ NAT/proxy theo thiết kế mạng.

Không nên nhầm địa chỉ IP của endpoint với địa chỉ IP egress. Một HTTP function có thể nhận request qua hostname công khai nhưng gọi API đối tác qua NAT IP riêng.

### 2.3. NAT Gateway và NAT không phải firewall

NAT (Network Address Translation) chuyển đổi địa chỉ IP/port giữa mạng private và mạng bên ngoài. NAT Gateway cho phép workload không có public IP khởi tạo kết nối ra Internet, đồng thời đối tác nhìn thấy địa chỉ public của NAT.

NAT chủ yếu giải quyết việc dịch địa chỉ và đường đi. Nó không tự tạo ra chính sách allowlist theo hostname hoặc nội dung HTTP. Muốn giới hạn destination, cần kết hợp firewall, route policy, proxy hoặc cơ chế kiểm soát egress phù hợp.

~~~mermaid
flowchart LR
    A[Serverless function] --> B[Private subnet / VPC route]
    B --> C[NAT Gateway]
    C --> D[Static public IP]
    D --> E[Internet API]
    B --> F[Private endpoint]
    F --> G[Managed service]
~~~

### 2.4. Firewall, security group và network ACL

Các cơ chế này có vai trò khác nhau:

- **Security group:** firewall cấp resource/interface, thường là stateful; quy định inbound/outbound theo protocol, port và nguồn/đích.
- **Network ACL:** áp dụng ở cấp subnet, thường stateless; cần xét cả chiều đi và chiều về, bao gồm ephemeral port.
- **Cloud firewall:** áp dụng chính sách ở cấp mạng hoặc tổ chức; có thể kiểm soát traffic giữa subnet, Internet và hybrid network.
- **Egress proxy:** điểm trung gian để áp dụng allowlist hostname, kiểm tra TLS theo chính sách, xác thực hoặc ghi log request.
- **Route table:** quyết định next hop, không phải cơ chế kiểm tra nội dung traffic.

Một kết nối có thể bị chặn ở bất kỳ lớp nào. Khi điều tra, hãy kiểm tra lần lượt DNS, route, firewall/security group, NAT, TLS và chính sách ở phía đích.

### 2.5. DNS private và public

DNS chuyển hostname thành địa chỉ IP. Với private endpoint, private DNS zone thường giúp cùng một hostname dịch vụ trả về private IP khi truy vấn từ VPC được liên kết.

Ví dụ, `db.internal.example` có thể resolve thành `10.20.5.12` trong VPC production, nhưng không tồn tại hoặc trả kết quả khác ở mạng bên ngoài. Split-horizon DNS cho phép cùng hostname có kết quả khác nhau theo vị trí truy vấn.

DNS sai có thể khiến function cố kết nối đến public endpoint dù đã cấu hình private route. Khi kiểm thử, hãy xác minh hostname mà ứng dụng thực sự dùng, DNS resolver, private zone association và TTL/cache của DNS.
 
## 3. Mạng của serverless function khác máy ảo thế nào?

Một function không phải là một máy ảo mà nhóm có thể đăng nhập, gán địa chỉ IP public rồi tự quản lý route. Nền tảng tạo execution environment và quản lý vòng đời của nó. Cách function kết nối VPC phụ thuộc dịch vụ serverless và cấu hình network integration của provider.

Một số nguyên tắc chung:

- Function thường khởi tạo kết nối outbound; nó không nhất thiết lắng nghe trên một private IP do người dùng quản lý.
- Một function được gắn với VPC có thể có network interface hoặc đường kết nối do nền tảng quản lý.
- Mỗi invocation không nhất thiết có một IP riêng; IP nguồn có thể thay đổi theo instance hoặc đường egress.
- Muốn có IP nguồn ổn định, cần một NAT/proxy hoặc egress gateway có địa chỉ tĩnh.
- VPC integration có thể thay đổi đường đi mặc định và làm phát sinh yêu cầu route, DNS, firewall, NAT.
- Concurrency serverless có thể tăng nhanh; cần tính tổng số connection đến database và endpoint private.

### 3.1. Kết nối mạng không đồng nghĩa với public endpoint

Một HTTP function có thể có URL public nhưng chỉ cho phép caller đã xác thực. Ngược lại, một endpoint có private IP vẫn cần authorization. Khi thiết kế, hãy trả lời riêng hai câu hỏi:

1. Ai có thể thiết lập kết nối mạng đến endpoint?
2. Ai có quyền thực hiện hành động nghiệp vụ sau khi kết nối thành công?

Câu thứ nhất thuộc ingress, routing và firewall. Câu thứ hai thuộc IAM, token, application authorization và policy của tài nguyên.

### 3.2. Các đường kết nối phổ biến

| Nhu cầu | Cách triển khai thường gặp |
|---|---|
| Function gọi database private | VPC/VNet integration, private subnet và firewall rule |
| Workload nội bộ gọi HTTP function | Private ingress, internal load balancer hoặc private API endpoint |
| Function gọi dịch vụ cloud | Private service endpoint, gateway endpoint hoặc private API access |
| Function gọi Internet với IP cố định | NAT gateway hoặc egress proxy có static public IP |
| Function chỉ được gọi một số domain | Egress firewall/proxy có allowlist |
| Function truy cập data center | VPN, Interconnect/Direct Connect hoặc mạng hybrid tương đương |

## 4. Private ingress: giới hạn ai có thể gọi function

Private ingress hữu ích khi function xử lý dữ liệu nội bộ hoặc cung cấp API chỉ dành cho ứng dụng trong mạng doanh nghiệp. Tuy nhiên, cách cấu hình khác nhau giữa các nền tảng.

### 4.1. AWS Lambda: private API endpoint đứng trước function

Lambda không hoạt động như một VM có private IP cố định để client trong VPC kết nối trực tiếp đến port của function. Một mẫu phổ biến là đặt API Gateway private REST API phía trước Lambda:

~~~mermaid
flowchart LR
    A[Client trong VPC] --> B[Interface VPC endpoint]
    B --> C[Private API Gateway]
    C --> D[Lambda integration]
    D --> E[Application logic]
    E --> F[Private database]
~~~

Client trong VPC truy cập API Gateway qua interface VPC endpoint cho dịch vụ `execute-api`. API Gateway private API có thể được bảo vệ bằng resource policy giới hạn VPC/VPC endpoint, đồng thời dùng IAM authorization hoặc cơ chế xác thực phù hợp. Lambda permission giới hạn API Gateway nào được phép invoke function.

Một lựa chọn khác là internal Application Load Balancer tích hợp Lambda target trong những kiến trúc phù hợp. Khi đó, load balancer và listener là điểm ingress private; cần cấu hình security group, target permission và xác thực ở lớp ứng dụng.

Không nhầm việc cấu hình Lambda vào VPC để outbound access với việc tạo private inbound endpoint. Lambda VPC configuration chủ yếu cung cấp network access từ function tới tài nguyên trong VPC; private API Gateway hoặc internal load balancer mới là điểm tiếp nhận kết nối từ client.

### 4.2. Google Cloud Run functions: ingress settings và internal load balancing

Cloud Run functions (thế hệ 2) chạy trên nền Cloud Run. Có thể cấu hình ingress để giới hạn nguồn request, chẳng hạn chỉ nhận traffic nội bộ hoặc traffic đi qua internal Application Load Balancer theo mô hình được hỗ trợ.

Các lựa chọn ingress thường được diễn giải như sau:

- **All:** nhận request từ các nguồn được phép theo IAM và cấu hình dịch vụ.
- **Internal:** chỉ nhận traffic được Google Cloud xác định là internal theo các điều kiện mạng/dịch vụ.
- **Internal and Cloud Load Balancing:** nhận traffic nội bộ và traffic qua Cloud Load Balancing được hỗ trợ.

Ingress setting kiểm soát đường vào dịch vụ. Nó không tự tạo một private IP cho function và không cấu hình đường egress đến database. Nếu cần endpoint private cho người dùng trong VPC hoặc mạng hybrid, hãy chọn mô hình internal load balancer, Private Service Connect hoặc đường truy cập nội bộ phù hợp với loại client và sản phẩm đang dùng.

### 4.3. Private ingress vẫn cần IAM

Ngay cả khi endpoint chỉ nhận traffic nội bộ, hãy cấu hình invoker permission. Ví dụ, một workload trong VPC có thể kết nối đến private API nhưng không nên được phép gọi mọi operation.

Áp dụng đồng thời:

- Ingress restriction để giới hạn nguồn mạng.
- IAM/authentication để xác định caller.
- Authorization trong ứng dụng để kiểm tra quyền trên từng tài nguyên.
- TLS để bảo vệ dữ liệu khi truyền.
- Rate limit và quota để giới hạn mức sử dụng.

## 5. Private egress: cho function truy cập mạng nội bộ

Private egress là đường để function khởi tạo kết nối đến địa chỉ private như database, internal API, cache hoặc dịch vụ trong VPC. Tên tính năng và cách kết nối phụ thuộc cloud provider.

### 5.1. AWS Lambda VPC configuration

Khi cấu hình Lambda vào VPC, chọn các subnet và security group. Lambda quản lý network interface cần thiết để function truy cập tài nguyên trong VPC.

Ví dụ SAM:

~~~yaml
Resources:
  OrderFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: com.example.OrderHandler
      CodeUri: target/function.zip
      VpcConfig:
        SubnetIds:
          - subnet-private-a
          - subnet-private-b
        SecurityGroupIds:
          - sg-lambda-egress
~~~

Các subnet thường được chọn ở nhiều Availability Zone để tăng khả năng sẵn sàng. Security group của Lambda chỉ nên cho phép outbound đến các destination/port cần thiết. Security group của database phải cho phép inbound từ security group của Lambda trên đúng port database.

Lambda đặt trong subnet có route local tới database private có thể truy cập database mà không cần NAT. Nhưng nếu function cần gọi public Internet, route private subnet phải có đường egress phù hợp, thường là NAT Gateway. Gán Lambda vào subnet được gọi là public không tự cấp public IP cho Lambda ENI và không tự tạo Internet access.

### 5.2. Google Cloud: Serverless VPC Access connector

Cloud Run functions thế hệ 2 có thể dùng Serverless VPC Access connector để gửi traffic từ function vào VPC. Connector là tài nguyên riêng trong một region và kết nối đến VPC network. Cần cấu hình dải IP, region, throughput và scaling theo yêu cầu tải.

Có thể chọn chính sách egress:

- `private-ranges-only`: traffic đến dải private được route qua VPC; traffic Internet còn lại có thể đi theo đường mặc định của serverless environment.
- `all-traffic`: toàn bộ outbound traffic đi qua VPC, nơi có thể áp dụng route, NAT và firewall tập trung.

Tên flag và lựa chọn cấu hình có thể khác giữa phiên bản CLI và cách triển khai. Với `gcloud functions deploy` gen2, cấu hình connector và egress settings theo tài liệu phiên bản hiện hành của Google Cloud CLI.

### 5.3. Direct VPC egress trên Google Cloud

Với nền tảng và region hỗ trợ, Direct VPC egress cho phép Cloud Run/Cloud Run functions kết nối trực tiếp với VPC qua subnet, không cần Serverless VPC Access connector. Nó giúp giảm lớp connector riêng và cho phép áp dụng route/firewall của VPC.

Cần kiểm tra khả năng hỗ trợ theo loại workload, region, networking mode và giới hạn hiện hành. Direct VPC egress và connector có các đặc tính về khởi tạo, scaling, IP allocation, throughput và chi phí khác nhau; hãy benchmark theo concurrency thực tế.

### 5.4. Kết nối database private

Một function có thể kết nối đến database qua private IP nếu đường mạng, DNS và firewall được cấu hình đúng. Ví dụ:

~~~mermaid
flowchart LR
    A[Java function] --> B[VPC integration]
    B --> C[Private DNS]
    C --> D[Database private IP]
    D --> E[Database port]
~~~

Các bước cần kiểm tra:

1. Function được kết nối vào đúng VPC/network và subnet.
2. Có route đến CIDR của database hoặc mạng peering/hybrid.
3. Security group/firewall cho phép đúng protocol và port.
4. Database chỉ lắng nghe trên interface và địa chỉ cần thiết.
5. Private DNS resolve hostname về đúng private IP.
6. TLS và database authentication được cấu hình đúng.
7. Connection pool và concurrency không vượt capacity của database.

Nếu database dùng private service access hoặc private service connect, cần cấu hình đúng cơ chế kết nối của provider. Không mở database ra public Internet chỉ để xử lý lỗi route của function.


## 6. Truy cập managed service qua private endpoint

Nhiều cloud service có endpoint private để workload truy cập mà không cần gửi traffic qua public Internet. Lợi ích là giảm public exposure, kiểm soát đường đi và có thể dùng policy ở endpoint. Cách triển khai phụ thuộc từng dịch vụ.

### 6.1. AWS: Gateway endpoint và Interface endpoint

AWS cung cấp hai nhóm VPC endpoint thường gặp:

**Gateway endpoint** được dùng cho một số dịch vụ như Amazon S3 và DynamoDB. Endpoint được gắn vào route table của subnet; traffic đến prefix của dịch vụ được định tuyến qua gateway endpoint. Nó không tạo một network interface riêng trong subnet.

**Interface endpoint** dùng AWS PrivateLink và tạo network interface trong subnet đã chọn. Client kết nối đến private IP của interface endpoint. Security group của endpoint kiểm soát traffic vào interface; private DNS có thể giúp hostname dịch vụ resolve tới endpoint private.

~~~mermaid
flowchart TD
    A[Lambda trong private subnet] --> B{Dịch vụ đích}
    B -->|S3 hoặc DynamoDB| C[Gateway endpoint]
    B -->|Secrets Manager, SQS, SNS...| D[Interface endpoint]
    C --> E[Managed service]
    D --> E
~~~

Khi dùng interface endpoint:

- Chọn subnet ở các Availability Zone phù hợp.
- Cho phép TCP 443 từ security group của Lambda đến security group của endpoint.
- Bật private DNS nếu muốn dùng hostname mặc định của dịch vụ.
- Kiểm tra endpoint policy và IAM policy của principal.
- Kiểm tra DNS và route từ từng subnet.

Với gateway endpoint, thêm endpoint vào đúng route table. Nếu Lambda ở subnet khác route table, traffic có thể vẫn đi theo route mặc định và không qua endpoint.

Endpoint policy là lớp lọc bổ sung. Nó không thay thế IAM policy của caller hoặc resource policy của dịch vụ. Request phải được phép qua các lớp policy liên quan.

### 6.2. Google Cloud: Private Google Access và Private Service Connect

Trên Google Cloud, có nhiều cách để truy cập Google APIs và managed services qua đường private:

- **Private Google Access:** cho phép workload không có external IP trong subnet truy cập các Google APIs/services được hỗ trợ qua hạ tầng Google.
- **Private Service Connect (PSC):** tạo endpoint private trong VPC để truy cập Google APIs, dịch vụ được publish hoặc dịch vụ khác hỗ trợ PSC.
- **Private Service Access (PSA):** cơ chế kết nối private service qua VPC peering cho một số managed services, ví dụ các cấu hình Cloud SQL private IP truyền thống.
- **Private IP của managed service:** service có địa chỉ private trong mạng được kết nối theo cơ chế provider hỗ trợ.

Các cơ chế này không hoàn toàn thay thế nhau. Chọn theo dịch vụ cụ thể, hướng kết nối, yêu cầu DNS, region và cách tổ chức VPC. Đọc tài liệu của dịch vụ đích để biết nó hỗ trợ Private Google Access, PSC hay PSA.

### 6.3. Cloud SQL: private IP và connector

Cloud SQL có thể được truy cập bằng private IP trong cấu hình mạng phù hợp. Google Cloud SQL connectors/Auth Proxy có thể hỗ trợ xác thực, mã hóa và quản lý kết nối, nhưng bản thân connector không tự biến mọi đường mạng thành private. Nếu yêu cầu không đi qua public Internet, hãy cấu hình private IP/PSC theo lựa chọn được hỗ trợ và bảo đảm function có VPC egress đến mạng đó.

Cần phân biệt:

- **Network path:** function có route đến private IP của database hay không.
- **Authentication:** danh tính nào được phép kết nối.
- **Database authorization:** user/database role nào được đọc hoặc ghi bảng.
- **Transport security:** kết nối có được bảo vệ bằng TLS hay cơ chế mã hóa phù hợp không.

Một connector có thể đơn giản hóa authentication và TLS nhưng không loại bỏ yêu cầu cấu hình route, firewall, DNS và database permissions.

### 6.4. Private endpoint không bảo đảm mọi traffic đều private

Một SDK có thể chọn hostname public theo mặc định, dù VPC đã có endpoint private. Private DNS phải được cấu hình để hostname đó resolve đúng địa chỉ endpoint. Một số dịch vụ có hostname riêng cho private endpoint hoặc yêu cầu bật private DNS.

Khi kiểm thử, hãy xác minh:

1. Ứng dụng đang gọi hostname nào.
2. DNS trả về địa chỉ private hay public.
3. Route table có đường đến endpoint.
4. Security group/firewall cho phép TCP port cần thiết.
5. Endpoint policy và IAM cho phép request.
6. TLS certificate vẫn hợp lệ với hostname mà client sử dụng.

## 7. Kiểm soát egress ra Internet

Egress là một trong những điểm quan trọng nhất khi bảo vệ workload serverless. Một function có thể bị khai thác để gửi dữ liệu ra ngoài, gọi domain độc hại hoặc tạo lượng traffic lớn. Kiểm soát egress giúp giới hạn destination và tạo khả năng quan sát đường ra.

### 7.1. Ba mức chính sách egress

Có thể phân loại chính sách theo mức kiểm soát:

| Mô hình | Hành vi | Khi phù hợp |
|---|---|---|
| Direct/default egress | Function tự đi theo đường Internet mặc định của nền tảng | Workload đơn giản, không yêu cầu IP cố định hoặc kiểm tra tập trung |
| Private-range egress | Traffic private đi qua VPC; Internet đi theo đường mặc định | Cần truy cập database private nhưng không cần kiểm soát toàn bộ Internet |
| All-traffic through VPC | Mọi traffic đi qua VPC, NAT và firewall/proxy | Cần static IP, audit hoặc egress allowlist tập trung |

Tên chế độ và semantics phụ thuộc provider. Trên Google Cloud, lựa chọn `private-ranges-only` và `all-traffic` của VPC egress là ví dụ phổ biến. Trên AWS Lambda trong VPC, route table và endpoint quyết định traffic đi qua NAT, endpoint hoặc đường kết nối khác.

### 7.2. Đưa toàn bộ egress qua NAT và firewall

Một kiến trúc tập trung có thể như sau:

~~~mermaid
flowchart LR
    A[Serverless functions] --> B[Private VPC subnet]
    B --> C[Route table]
    C --> D[Firewall / egress proxy]
    D --> E[NAT Gateway]
    E --> F[Static public IP]
    F --> G[Allowed Internet destinations]
    D --> H[Blocked destinations]
~~~

Các bước:

1. Function được kết nối vào VPC hoặc subnet thông qua cơ chế serverless networking.
2. Route table đưa traffic Internet đến firewall, proxy hoặc NAT theo thiết kế.
3. Firewall/proxy áp dụng chính sách allow/deny.
4. NAT thực hiện address translation và cung cấp IP nguồn public ổn định.
5. Log và metric ghi nhận destination, byte, lỗi và số kết nối.

Trong một số kiến trúc, firewall đứng trước NAT; kiến trúc khác dùng firewall sau NAT hoặc proxy riêng. Thứ tự phụ thuộc sản phẩm, route symmetry và yêu cầu quan sát. Hãy kiểm tra đường đi cả chiều request lẫn response để tránh asymmetric routing.

### 7.3. NAT không giới hạn domain

NAT Gateway hoặc Cloud NAT thường không hiểu hostname HTTP. Nếu chỉ cấu hình NAT và cấp một static IP, function vẫn có thể gọi nhiều destination Internet tùy route và firewall hiện có.

Để chỉ cho phép các domain cần thiết, cân nhắc:

- Egress proxy có allowlist hostname.
- Firewall hỗ trợ FQDN/domain policy phù hợp.
- DNS policy/filter kết hợp kiểm soát network.
- Application-level allowlist cho hostname và port.
- Egress firewall chặn mọi destination không được phép theo IP/CIDR nếu phù hợp.

Allowlist IP có thể khó duy trì với SaaS/CDN vì địa chỉ IP thay đổi và nhiều domain dùng chung IP. Allowlist hostname dễ vận hành hơn khi có proxy hoặc firewall hỗ trợ, nhưng cần hiểu cách sản phẩm xử lý DNS, TLS, redirect và QUIC/UDP.

### 7.4. DNS filtering không phải lớp bảo vệ duy nhất

Chỉ chặn DNS không đủ để bảo đảm egress an toàn. Workload có thể dùng IP trực tiếp, DNS-over-HTTPS, resolver khác hoặc kết nối qua một hostname được phép nhưng redirect đến destination khác.

Kết hợp DNS policy với firewall/egress proxy, application allowlist và kiểm soát IAM. Nếu cần kiểm tra TLS, cân nhắc tác động của TLS inspection đến certificate pinning, mTLS, privacy và quy định dữ liệu.

### 7.5. Static egress IP cho đối tác

Một số API đối tác chỉ cho phép request từ IP đã đăng ký. Khi đó, function cần đi qua NAT/proxy có public IP tĩnh:

- Trên AWS, NAT Gateway có thể sử dụng Elastic IP.
- Trên Google Cloud, Cloud NAT có thể sử dụng địa chỉ IP đã reserve.
- Với kiến trúc proxy tập trung, proxy hoặc firewall có thể là điểm egress public.

Đăng ký tất cả IP có thể được dùng theo thiết kế HA. Nếu NAT chạy ở nhiều zone hoặc có nhiều egress path, đối tác cần allowlist đủ các IP. Không giả định một function có một IP egress cố định nếu chưa có NAT/proxy được cấu hình.

### 7.6. Egress IPv4 và IPv6

Nếu VPC/subnet hỗ trợ IPv6, cần thiết kế riêng route và firewall cho IPv6. NAT Gateway IPv4 không tự xử lý IPv6. Trên AWS, outbound IPv6 từ subnet private thường dùng egress-only Internet Gateway khi cần kết nối một chiều ra Internet. Trên các nền tảng khác, cơ chế egress IPv6 có thể khác.

Nếu chỉ kiểm soát IPv4 mà bỏ qua IPv6, function có thể đi ra ngoài qua một đường chưa được áp dụng chính sách. Kiểm kê cả A/AAAA DNS record, route IPv6 và firewall rule trước khi công bố rằng egress đã được giới hạn.

## 8. Egress trong Java function

Mã Java tạo kết nối outbound bằng hostname hoặc IP; đường đi thực tế do network integration, DNS, route, firewall và NAT quyết định. Thay đổi code không thể thay thế cấu hình VPC. Tuy nhiên, ứng dụng vẫn cần giới hạn destination ở mức nghiệp vụ, đặt timeout và tránh mở quá nhiều kết nối đồng thời.

### 8.1. Dùng hostname và TLS

Ưu tiên hostname của dịch vụ thay vì hardcode IP, đặc biệt khi dùng private DNS hoặc managed endpoint. Hostname giúp DNS chuyển đến IP phù hợp theo môi trường. TLS cần kiểm tra certificate và hostname; không tắt hostname verification chỉ vì đang kết nối qua private IP.

Ví dụ Java HTTP client:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Set;

public final class PartnerClient {

    private static final Set<String> ALLOWED_HOSTS =
            Set.of("api.partner.example");

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    public String fetchStatus(String orderId) throws Exception {
        URI uri = URI.create(
                "https://api.partner.example/v1/orders/" + orderId);

        String host = uri.getHost();
        if (host == null || !ALLOWED_HOSTS.contains(host)) {
            throw new SecurityException("Destination host is not allowed");
        }

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() / 100 != 2) {
            throw new IllegalStateException(
                    "Partner API returned status " + response.statusCode());
        }

        return response.body();
    }
}
~~~

Ví dụ minh họa application-level hostname allowlist, không thay thế firewall. Nếu URL có thể bị điều khiển bởi user, cần validate scheme, hostname, port, redirect và địa chỉ sau DNS resolution để giảm nguy cơ SSRF. Cần đặc biệt thận trọng với redirect: một hostname được phép có thể trả redirect đến host khác.

`connectTimeout` giới hạn thời gian thiết lập kết nối; `HttpRequest.timeout` giới hạn thời gian chờ request/response. Cả hai cần nằm trong deadline còn lại của function. Nếu function có thể chạy nhiều request song song, dùng client tái sử dụng và giới hạn concurrency/connection pool.

### 8.2. Khi nào dùng proxy?

Egress proxy phù hợp khi tổ chức cần:

- Allowlist domain và port ở một điểm tập trung.
- Ghi log destination và request metadata theo chính sách.
- Xác thực workload trước khi cho phép egress.
- Chuyển tiếp traffic qua kiểm tra bảo mật hoặc TLS inspection.
- Giữ một điểm egress có IP tĩnh cho đối tác.

Ứng dụng cần được cấu hình để sử dụng proxy theo cơ chế mà HTTP client/SDK hỗ trợ. Không phải mọi SDK đều tự động tôn trọng system proxy. Kiểm tra riêng client library và tránh cấu hình proxy bằng cách truyền secret hoặc credential trong URL.

Proxy là một thành phần quan trọng của đường đi; cần thiết kế HA, capacity, timeout, DNS, TLS certificate và xử lý khi proxy không sẵn sàng. Nếu proxy lỗi mà function tự bypass sang Internet trực tiếp, chính sách egress có thể bị vô hiệu hóa. Hãy chọn rõ hành vi fail-closed hay fail-open theo yêu cầu bảo mật.

### 8.3. Tránh SSRF và destination ngoài dự kiến

Server-Side Request Forgery (SSRF) xảy ra khi attacker điều khiển địa chỉ mà server gọi. Trong serverless, SSRF có thể khiến function truy cập metadata endpoint, private API, database hoặc dịch vụ nội bộ mà caller không được phép truy cập trực tiếp.

Các biện pháp:

- Không cho client truyền URL tùy ý nếu không cần thiết.
- Ưu tiên map một mã dịch vụ sang hostname cố định trong allowlist.
- Chỉ cho phép scheme và port cần thiết, thường là HTTPS/443.
- Kiểm tra redirect và hostname cuối cùng sau redirect.
- Chặn loopback, link-local, private IP hoặc dải nhạy cảm nếu use case không cần truy cập.
- Không dựa duy nhất vào kiểm tra DNS ở ứng dụng; áp dụng egress firewall/proxy.
- Không cấp runtime service account quyền rộng để truy cập mọi tài nguyên nội bộ.

Metadata endpoint của cloud có thể cung cấp credential hoặc token cho workload. Egress policy nên ngăn request không cần thiết đến endpoint nhạy cảm; đồng thời dùng service identity và metadata protection theo hướng dẫn của provider.

## 9. Cấu hình mạng trên các nền tảng serverless

### 9.1. AWS Lambda trong VPC

Khi Lambda được gắn VPC, cần xác định:

1. Private subnet ở các Availability Zone cần thiết.
2. Security group của Lambda với outbound tối thiểu.
3. Security group của database/API nội bộ với inbound từ Lambda.
4. Route table đến database, peering, VPN hoặc Transit Gateway.
5. NAT Gateway nếu cần Internet IPv4.
6. Gateway/interface VPC endpoints cho dịch vụ AWS được truy cập thường xuyên.
7. Private DNS và endpoint policy nếu dùng interface endpoint.
8. Reserved concurrency hoặc account concurrency để bảo vệ downstream.

Mẫu route table đơn giản:

| Destination | Target |
|---|---|
| CIDR của VPC | `local` |
| CIDR mạng data center | VPN/Transit Gateway |
| Prefix S3/DynamoDB | Gateway endpoint |
| `0.0.0.0/0` | NAT Gateway |

Nếu mọi traffic Internet phải qua firewall, route `0.0.0.0/0` có thể đi qua AWS Network Firewall hoặc appliance/proxy theo kiến trúc đã chọn trước khi ra NAT. Đảm bảo route response đối xứng và không tạo vòng lặp.

### 9.2. Google Cloud Run functions

Với Cloud Run functions thế hệ 2, có thể chọn một trong các hướng:

- Serverless VPC Access connector để đưa traffic vào VPC.
- Direct VPC egress nếu nền tảng, region và cấu hình function hỗ trợ.
- Private ingress hoặc internal load balancing để giới hạn nguồn gọi.
- Cloud NAT với địa chỉ IP reserve để có static egress IPv4.
- Cloud Firewall/Cloud NGFW hoặc proxy để kiểm soát destination.
- Private Google Access hoặc PSC để truy cập Google APIs/dịch vụ qua private path.

Với connector, xác định dải IP không trùng CIDR hiện có, chọn region phù hợp và sizing theo throughput. Với Direct VPC egress, kiểm tra khả năng hỗ trợ, IP allocation, network tags và giới hạn của service. Trong cả hai trường hợp, kiểm tra egress mode: chỉ private ranges hay toàn bộ traffic.

### 9.3. Azure Functions

Trên Azure Functions, VNet integration thường dùng để kiểm soát outbound traffic từ function đến tài nguyên trong VNet. Private Endpoint có thể được dùng để đưa một số dịch vụ như Storage, Key Vault hoặc ứng dụng được hỗ trợ vào mạng private. NAT Gateway hoặc Azure Firewall có thể cung cấp egress IP cố định và kiểm soát đường ra theo cấu hình plan/networking.

Khả năng và giới hạn cụ thể phụ thuộc hosting plan, OS, region và tính năng networking. Hãy kiểm tra plan có hỗ trợ VNet integration, route-all và private endpoint cho đúng dịch vụ trước khi thiết kế.

### 9.4. So sánh nhanh theo provider

| Nhu cầu | AWS | Google Cloud | Azure |
|---|---|---|---|
| Function outbound đến VPC | Lambda VPC configuration | VPC connector hoặc Direct VPC egress | VNet integration |
| Private access tới dịch vụ | Interface/Gateway VPC endpoint, PrivateLink | PSC, Private Google Access, PSA | Private Endpoint |
| Static egress IP | NAT Gateway + Elastic IP | Cloud NAT + reserved IP | NAT Gateway |
| Kiểm soát egress tập trung | Network Firewall/proxy, route | Cloud Firewall/Cloud NGFW/proxy, route | Azure Firewall/proxy, route |
| Private inbound HTTP | Private API Gateway/Interface endpoint hoặc internal ALB | Internal ingress/load balancer, PSC theo mô hình hỗ trợ | Private Endpoint hoặc internal ingress theo hosting model |

Không nên coi tên tính năng giữa các provider là tương đương hoàn toàn. Hãy kiểm tra semantics, region, quota, pricing và giới hạn của đúng dịch vụ serverless đang dùng.

## 10. Danh tính, network policy và bảo vệ nhiều lớp

Mạng private giới hạn đường kết nối, nhưng không xác định đầy đủ quyền nghiệp vụ. Một request có thể đi qua VPC endpoint và vẫn bị IAM từ chối; ngược lại, caller có IAM permission nhưng không có route hoặc firewall rule thì cũng không thể kết nối.

### 10.1. Phân tách các lớp kiểm soát

| Lớp | Câu hỏi | Ví dụ cơ chế |
|---|---|---|
| Network reachability | Có đường mạng đến destination không? | Route, VPC, VPN, peering |
| Network filtering | Traffic có được phép qua không? | Security group, firewall, NACL |
| Service exposure | Endpoint có nhận traffic từ nguồn này không? | Private ingress, API endpoint policy |
| Identity | Ai đang gọi? | IAM, service account, workload identity |
| Authorization | Caller được làm gì trên resource? | IAM role, database role, application policy |
| Transport security | Dữ liệu được bảo vệ thế nào? | TLS, mTLS, certificate validation |
| Application validation | Request có hợp lệ và an toàn không? | Schema validation, allowlist, SSRF protection |

Không dựa vào một lớp duy nhất. Ví dụ, private endpoint chỉ giới hạn đường mạng; nếu mọi principal trong VPC đều có quyền truy cập dữ liệu, bề mặt rủi ro vẫn lớn.

### 10.2. Least privilege cho egress

Chỉ cho function kết nối đến destination cần thiết:

- Chỉ mở database port đến security group của database.
- Chỉ cho phép HTTPS đến API cần dùng.
- Dùng endpoint policy để giới hạn dịch vụ/tài nguyên khi provider hỗ trợ.
- Tách subnet hoặc security group theo loại workload.
- Không dùng một security group outbound rộng cho mọi function nếu chúng có nhu cầu khác nhau.
- Giới hạn runtime service account và secret access theo từng function.
- Dùng firewall rule có owner, mục đích và ngày rà soát.

Nếu function chỉ cần truy cập database và S3, không nhất thiết phải cho phép Internet egress rộng. Có thể dùng private endpoint cho S3, route đến database private và deny các destination khác theo chính sách mạng.

### 10.3. TLS và mTLS

Private network không đồng nghĩa traffic đã được mã hóa. Dùng TLS cho kết nối database và HTTP API nếu dịch vụ hỗ trợ. Với hệ thống yêu cầu xác thực hai chiều, mTLS có thể xác minh cả client và server bằng certificate.

Quản lý certificate qua dịch vụ phù hợp, lên kế hoạch rotation và không tắt certificate verification để khắc phục lỗi tạm thời. TLS inspection qua proxy có thể thay đổi certificate chain mà client nhìn thấy; cần thiết kế trust store và certificate pinning phù hợp.

### 10.4. Phân đoạn môi trường và tenant

Không dùng chung network policy rộng giữa production và development. Tách VPC/VNet hoặc subnet theo môi trường và áp dụng route/endpoint riêng. Nếu dùng Shared VPC hoặc mạng trung tâm, vẫn cần phân tách bằng subnet, security group, firewall policy và IAM.

Với multi-tenant, giới hạn concurrency và egress theo tenant khi cần. Không cho tenant truyền URL hoặc IP tùy ý để function gọi thay họ. Nếu sản phẩm cần tích hợp endpoint do tenant cấu hình, phải có quy trình xác minh domain, chặn dải IP nhạy cảm và kiểm tra redirect/DNS rebinding.

## 11. Thiết kế static egress và high availability

Một điểm egress tập trung giúp allowlist và audit dễ hơn, nhưng cũng tạo thành phần quan trọng trong đường đi của request. Nếu NAT, firewall hoặc proxy không sẵn sàng, function có thể mất khả năng gọi dịch vụ bên ngoài.

### 11.1. NAT theo zone/region

Trên AWS, NAT Gateway thường được triển khai theo Availability Zone và route của subnet private trỏ đến NAT phù hợp trong zone để giảm phụ thuộc cross-AZ. Nếu nhiều subnet cùng đi qua một NAT ở zone khác, sự cố zone đó có thể ảnh hưởng nhiều workload và có thể phát sinh chi phí truyền dữ liệu liên vùng.

Cloud NAT trên Google Cloud là dịch vụ managed theo region, nhưng vẫn cần cấu hình địa chỉ IP, subnet/range, logging và capacity theo nhu cầu. Với mọi provider, hãy kiểm tra giới hạn port/connections, số IP NAT và cách mở rộng khi concurrency tăng.

### 11.2. Static IP và allowlist đối tác

Nếu đối tác chỉ cho phép IP đã đăng ký:

1. Reserve địa chỉ public tĩnh ở tầng NAT/proxy.
2. Đưa mọi route egress cần thiết qua đúng điểm đó.
3. Đăng ký toàn bộ IP có thể dùng trong failover/HA.
4. Kiểm thử IP nguồn thực tế từ môi trường triển khai.
5. Giám sát NAT/proxy và cảnh báo khi egress path thay đổi.

Không đăng ký một IP dựa trên kết quả thử nghiệm từ laptop hoặc môi trường local. Địa chỉ nguồn của local machine khác với địa chỉ NAT mà function sử dụng trong cloud.

### 11.3. Capacity và cạn port

NAT/proxy có giới hạn về số kết nối đồng thời, port mapping và throughput. Một function serverless có thể scale nhanh hơn khả năng cấp port hoặc xử lý của điểm egress.

Để tránh nghẽn:

- Tái sử dụng HTTP client và connection pool an toàn.
- Đặt giới hạn connection pool và concurrency.
- Dùng keep-alive phù hợp để giảm tạo kết nối mới.
- Chọn đủ NAT IP/capacity theo số kết nối đồng thời.
- Theo dõi port allocation, dropped packets, connection errors và latency.
- Dùng retry có backoff và jitter, tránh retry storm khi NAT/proxy đang quá tải.

Không tăng max instances chỉ để xử lý latency nếu bottleneck là NAT, proxy hoặc API đích. Tăng concurrency có thể làm tình trạng cạn port nặng hơn.

## 12. Quan sát và xử lý sự cố kết nối

Khi function không kết nối được private endpoint hoặc Internet, hãy điều tra theo đường đi của gói tin. Một log lỗi chung như `Connection timed out` chưa cho biết nguyên nhân nằm ở DNS, route, firewall hay destination.

### 12.1. Quy trình chẩn đoán

1. **Xác nhận hostname và port:** ứng dụng đang gọi đúng hostname, protocol và port chưa?
2. **Kiểm tra DNS:** hostname resolve thành private hay public IP? Có private zone đúng VPC không?
3. **Kiểm tra route:** subnet của function có route đến destination hoặc NAT/endpoint không?
4. **Kiểm tra firewall:** security group, NACL, cloud firewall và endpoint SG có cho phép chiều đi/chiều về không?
5. **Kiểm tra NAT/endpoint:** NAT có địa chỉ và capacity phù hợp? VPC endpoint đã gắn đúng subnet/route table chưa?
6. **Kiểm tra TLS:** certificate, hostname verification, trust store và thời gian hệ thống có hợp lệ không?
7. **Kiểm tra IAM/policy:** caller có quyền invoke function hoặc sử dụng service đích không?
8. **Kiểm tra destination:** database/API có lắng nghe, còn capacity và cho phép nguồn kết nối không?

Phân biệt một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể |
|---|---|
| `UnknownHostException` | DNS resolver, private zone hoặc hostname sai |
| `Connection timed out` | Route thiếu, firewall drop, NAT/endpoint lỗi hoặc destination không phản hồi |
| `Connection refused` | Đã đến host nhưng port không lắng nghe hoặc service từ chối |
| `UnknownHost` với private endpoint | Private DNS không liên kết đúng VPC/subnet |
| `SSLHandshakeException` | Certificate, TLS version, hostname hoặc trust store |
| `403` từ managed service | IAM, endpoint policy hoặc resource policy |
| `429` hoặc throttling | Quota, rate limit hoặc capacity dịch vụ |
| Kết nối chập chờn khi scale | NAT/port exhaustion, connection pool hoặc giới hạn downstream |

### 12.2. Log và metric mạng

Các nguồn quan sát có thể gồm:

- VPC Flow Logs để xem metadata lưu lượng mạng được chấp nhận/từ chối.
- NAT Gateway/Cloud NAT metrics và logs để phát hiện lỗi, dropped packets, port usage hoặc throughput.
- Firewall logs để biết rule nào cho phép/chặn traffic.
- DNS query logs để điều tra hostname resolve sai.
- API Gateway/Cloud Run request logs và Lambda/Cloud Run function logs.
- Trace phân tán để xác định thời gian nằm ở DNS, connect, TLS, server hay database.
- Metric ứng dụng cho timeout, connection pool, số kết nối và retry.

Flow log thường không chứa nội dung payload ứng dụng. Nó giúp xác định địa chỉ, port, protocol và trạng thái traffic; cần kết hợp log ở ứng dụng và dịch vụ đích để hiểu nguyên nhân đầy đủ.

### 12.3. Tránh ghi log quá nhiều dữ liệu

Log địa chỉ IP, hostname và request ID khi cần điều tra, nhưng tránh ghi token, cookie, query chứa dữ liệu cá nhân hoặc toàn bộ request body. Với hostname hoặc IP do user cung cấp, cần cân nhắc privacy và chính sách retention.

Đặt metric dimension có cardinality hợp lý. Không tạo một time series riêng cho mỗi request ID hoặc URL tùy ý; dùng request ID trong log/trace thay vì metric label.

## 13. Các mẫu kiến trúc thường dùng

### 13.1. Function chỉ truy cập database private

~~~mermaid
flowchart LR
    A[Internal HTTP caller] --> B[Authenticated function]
    B --> C[VPC integration]
    C --> D[Private database]
~~~

Phù hợp khi function chỉ phục vụ ứng dụng nội bộ và không cần gọi Internet. Tắt public ingress nếu kiến trúc hỗ trợ, giới hạn IAM invoker và chỉ mở database port từ security group/connector cần thiết.

### 13.2. Function truy cập managed service qua endpoint private

~~~mermaid
flowchart LR
    A[Function] --> B[Private network]
    B --> C[Private endpoint]
    C --> D[Object storage hoặc secret service]
~~~

Phù hợp khi cần truy cập S3, DynamoDB, Secrets Manager, Google APIs hoặc managed service được hỗ trợ qua private path. Kết hợp endpoint policy, IAM, private DNS và firewall.

### 13.3. Function gọi Internet qua egress tập trung

~~~mermaid
flowchart LR
    A[Function] --> B[VPC egress]
    B --> C[Firewall / proxy]
    C --> D[NAT static IP]
    D --> E[Partner API]
~~~

Phù hợp khi đối tác yêu cầu static IP, tổ chức cần audit egress hoặc phải áp dụng allowlist domain. Thiết kế HA và capacity cho firewall/proxy/NAT.

### 13.4. Function có cả private và public destination

~~~mermaid
flowchart TD
    A[Function] --> B{Destination}
    B -->|Private service| C[Private route / endpoint]
    B -->|Internet API| D[Firewall / proxy / NAT]
    C --> E[Internal database or managed service]
    D --> F[Approved external API]
~~~

Đây là mẫu phổ biến nhất. Điều quan trọng là route cho private service không vô tình bị NAT ra Internet, còn traffic Internet không bypass firewall/proxy khi chính sách yêu cầu egress tập trung.

## 14. Checklist thiết kế private endpoint và egress

- [ ] Đã phân biệt rõ ingress với egress.
- [ ] Đã xác định client nào cần gọi function và destination nào function cần gọi.
- [ ] Database và dịch vụ nội bộ không bị mở public chỉ để xử lý lỗi kết nối.
- [ ] Private endpoint/service endpoint được chọn đúng theo dịch vụ và provider.
- [ ] Private DNS resolve đúng IP từ network của function.
- [ ] Route table có đường đi và đường về phù hợp.
- [ ] Security group, NACL và firewall chỉ mở protocol/port cần thiết.
- [ ] IAM, endpoint policy và resource policy được cấu hình độc lập với network.
- [ ] Egress mode được chọn rõ: direct, private ranges hay all traffic qua VPC.
- [ ] NAT/proxy có static IP nếu đối tác yêu cầu allowlist.
- [ ] NAT không bị nhầm là firewall; domain allowlist được áp dụng ở lớp phù hợp.
- [ ] Cả IPv4 và IPv6 đều được xem xét.
- [ ] Runtime service account có quyền tối thiểu.
- [ ] HTTP client có connect/request timeout và connection pool giới hạn.
- [ ] Có bảo vệ SSRF nếu function gọi URL do người dùng cung cấp.
- [ ] Có flow logs, firewall/NAT/DNS logs và metric ứng dụng phù hợp.
- [ ] Đã kiểm thử khi scale, khi endpoint/NAT lỗi và khi DNS thay đổi.
- [ ] Có kế hoạch HA, capacity và rà soát rule định kỳ.

## 15. Tự kiểm tra

**Câu 1.** Private ingress và private egress khác nhau thế nào?

**Gợi ý trả lời:** Private ingress giới hạn nguồn có thể gọi function. Private egress cho phép function khởi tạo kết nối đến tài nguyên trong mạng private. Cấu hình một hướng không tự động bảo vệ hướng còn lại.

**Câu 2.** Vì sao Lambda được gắn vào VPC vẫn cần NAT khi gọi public Internet?

**Gợi ý trả lời:** Lambda trong private subnet có thể truy cập tài nguyên nội bộ nhưng không tự có public IP hoặc Internet route. Cần route qua NAT Gateway hoặc đường egress được thiết kế phù hợp.

**Câu 3.** NAT Gateway có thể chặn mọi domain trừ allowlist không?

**Gợi ý trả lời:** NAT chủ yếu dịch địa chỉ và cung cấp đường ra; nó không phải firewall hiểu hostname HTTP. Cần firewall hỗ trợ FQDN, egress proxy hoặc cơ chế kiểm soát destination phù hợp.

**Câu 4.** Vì sao private endpoint vẫn cần IAM và TLS?

**Gợi ý trả lời:** Private endpoint giới hạn đường mạng nhưng không xác định caller được phép làm gì và không tự bảo đảm mã hóa end-to-end. IAM/authorization kiểm soát danh tính và quyền; TLS bảo vệ dữ liệu truyền.

**Câu 5.** Vì sao DNS private có thể khiến function kết nối sai endpoint?

**Gợi ý trả lời:** Private zone có thể chưa được liên kết với VPC, hostname có thể resolve thành public IP hoặc resolver/cache trả kết quả cũ. Cần kiểm tra DNS từ chính network/runtime có đường kết nối.

**Bài tập tình huống:** Một Java function xử lý đơn hàng cần đọc Cloud SQL/RDS private, lấy secret, sau đó gọi API của đối tác chỉ chấp nhận IP đã allowlist. Công ty yêu cầu mọi egress Internet phải được ghi log và chỉ cho phép domain đối tác. Hãy thiết kế ingress, private egress, private endpoint, NAT/static IP, firewall/proxy, IAM và DNS. Nêu cách triển khai cho AWS Lambda và Google Cloud Run functions, cùng các phép kiểm thử cần thực hiện.

**Gợi ý:** Giữ database private và đưa function vào VPC/VPC connector hoặc Direct VPC egress phù hợp. Dùng interface endpoint cho Secrets Manager trên AWS hoặc private access/PSC cho dịch vụ Google Cloud tương ứng. Route Internet qua egress firewall/proxy và NAT có static IP; đăng ký toàn bộ IP HA với đối tác. NAT không thay thế domain filtering nên dùng proxy hoặc firewall có FQDN policy. Cấp runtime identity quyền đọc đúng secret và database; private ingress/IAM giới hạn caller. Kiểm thử DNS, route, firewall, endpoint policy, IP nguồn thực tế, TLS, redirect, retry và hành vi khi NAT/proxy không sẵn sàng.

## Kết luận

Thiết kế mạng cho serverless cần tách biệt ingress, egress và quyền truy cập. Private endpoint cùng VPC/VNet integration giúp function truy cập database và managed service mà không mở public exposure. NAT cung cấp đường ra và IP nguồn ổn định, còn firewall/proxy mới là nơi áp dụng chính sách destination và ghi log. Private DNS, route, security group, IAM, TLS và capacity đều phải được kiểm tra cùng nhau. Khi triển khai trên AWS Lambda, Google Cloud Run functions hoặc Azure Functions, hãy chọn đúng cơ chế networking của provider, giới hạn egress theo nhu cầu và kiểm thử ở mức concurrency gần production.
