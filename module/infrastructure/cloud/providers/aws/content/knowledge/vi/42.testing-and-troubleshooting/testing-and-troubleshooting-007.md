# Chẩn đoán DNS, route, Security Group và kết nối VPC

Một ứng dụng trong Amazon VPC có thể không kết nối được tới cơ sở dữ liệu, API nội bộ, dịch vụ AWS hoặc máy chủ on-premises dù EC2 instance vẫn ở trạng thái running. Nguyên nhân thường nằm ở một mắt xích trong đường đi của gói tin: DNS trả về địa chỉ sai, route table chọn sai target, Security Group không cho phép cổng cần thiết, Network ACL chặn gói phản hồi, VPC endpoint thiếu cấu hình hoặc ứng dụng không lắng nghe trên địa chỉ/cổng dự kiến.

Chẩn đoán hiệu quả cần bắt đầu từ một kết nối cụ thể. Hãy xác định nguồn, đích, giao thức, cổng, hướng khởi tạo và thời điểm xảy ra lỗi. Sau đó kiểm tra lần lượt phân giải tên, địa chỉ IP, đường đi, lớp lọc mạng và ứng dụng ở đầu đích. Cách làm này giúp thu hẹp nguyên nhân mà không phải mở rộng quyền truy cập toàn mạng hoặc thay đổi nhiều cấu hình cùng lúc.

Trong AWS, các công cụ như Reachability Analyzer, VPC Flow Logs, Route 53 VPC Resolver query logs, EC2 status checks và CloudWatch cung cấp những góc nhìn khác nhau. Không công cụ nào thay thế hoàn toàn kiểm thử từ chính workload. Bài học hướng dẫn cách kết hợp chúng để xử lý sự cố có bằng chứng và khôi phục kết nối an toàn.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Mô tả đường đi của một kết nối từ workload nguồn đến workload đích trong VPC.
- Phân biệt lỗi DNS, lỗi định tuyến, lỗi Security Group, Network ACL và lỗi ứng dụng.
- Kiểm tra Route 53 VPC Resolver, private hosted zone, DHCP option set và hybrid DNS.
- Đọc route table, longest prefix match, route tới Internet Gateway, NAT Gateway và VPC endpoint.
- Phân tích Security Group stateful và Network ACL stateless, gồm cả ephemeral ports.
- Chẩn đoán kết nối qua VPC peering, Transit Gateway, VPN và Direct Connect.
- Dùng Reachability Analyzer để tìm thành phần chặn đường đi.
- Dùng VPC Flow Logs và Resolver query logs để xác minh hành vi thực tế.
- Sử dụng lệnh Linux, Windows và AWS CLI để thu thập bằng chứng.
- Xây dựng quy trình troubleshooting, runbook và checklist production.

## 1. Mô hình chẩn đoán kết nối VPC

Một request TCP tới dịch vụ trong VPC thường đi qua các bước logic sau:

1. Ứng dụng xác định hostname hoặc địa chỉ IP đích.
2. Nếu dùng hostname, hệ điều hành hỏi DNS resolver và nhận một hoặc nhiều địa chỉ IP.
3. Hệ điều hành chọn địa chỉ IP, địa chỉ nguồn và route cục bộ.
4. Gói tin đi qua subnet route table và các network components như NAT Gateway, Internet Gateway, VPC peering, Transit Gateway hoặc VPC endpoint.
5. Network ACL kiểm tra traffic tại ranh giới subnet.
6. Security Group gắn với network interface kiểm tra traffic vào/ra resource.
7. Hệ điều hành đích nhận gói tin; firewall trên máy và ứng dụng tiếp tục xử lý.
8. Gói phản hồi đi ngược về nguồn qua route và các lớp lọc tương ứng.

~~~mermaid
flowchart TD
    A["Ứng dụng: hostname + port"] --> B["DNS resolution"]
    B --> C["Địa chỉ IP đích"]
    C --> D["Route table / network path"]
    D --> E["Network ACL tại subnet"]
    E --> F["Security Group tại ENI"]
    F --> G["OS firewall / service listener"]
    G --> H["Response traffic"]
    H --> I["Return route + NACL + state tracking"]
    I --> J["Ứng dụng nhận response"]
~~~

Đường đi có thể khác nhau tùy topology. Ví dụ, traffic tới S3 qua gateway endpoint không đi qua NAT Gateway; traffic tới interface endpoint đi tới private IP của endpoint ENI; traffic tới một VPC khác có thể qua peering hoặc Transit Gateway.

### 1.1. Thu thập thông tin trước khi sửa

Với mỗi sự cố, ghi lại:

| Thông tin | Ví dụ |
|---|---|
| Source | EC2 instance ID, ENI ID, subnet và VPC ID |
| Destination | Hostname, IP, ENI hoặc endpoint ID |
| Protocol/port | TCP 443, TCP 5432, UDP 53 |
| Direction | Client khởi tạo outbound hay server khởi tạo inbound |
| Address family | IPv4 hay IPv6 |
| Expected path | Local VPC, IGW, NAT, peering, TGW, VPN hoặc endpoint |
| Symptom | NXDOMAIN, timeout, connection refused, TLS error, HTTP 403/5xx |
| Time window | Thời điểm bắt đầu lỗi và thời điểm kiểm thử |
| Recent changes | Route, SG, NACL, DNS, deployment, endpoint hoặc application release |

Một thông báo connection timed out thường cho biết client không nhận được phản hồi đúng hạn; nó không tự chứng minh Security Group là nguyên nhân. connection refused thường cho thấy đã tới được host nhưng không có listener chấp nhận cổng đó hoặc host chủ động từ chối. NXDOMAIN là kết quả DNS cho biết tên không tồn tại trong phạm vi resolver được hỏi. Phân biệt đúng symptom giúp chọn lớp cần kiểm tra.

## 2. Chẩn đoán DNS trong VPC

DNS biến hostname thành địa chỉ IP. Nếu DNS sai, các bước kiểm tra route và Security Group có thể đang nhắm tới sai đích.

Amazon VPC có Route 53 VPC Resolver, trước đây gọi là Route 53 Resolver. Resolver có sẵn trong VPC và xử lý truy vấn cho public DNS names, tên nội bộ do AWS cung cấp và Route 53 private hosted zones.

Địa chỉ resolver thường dùng:

- IPv4: địa chỉ IPv4 CIDR chính của VPC cộng 2, ví dụ VPC 10.20.0.0/16 có resolver 10.20.0.2.
- Link-local IPv4: 169.254.169.253.
- IPv6: fd00:ec2::253.

### 2.1. Hai DNS attributes của VPC

Hai thuộc tính cần kiểm tra:

| Thuộc tính | Vai trò |
|---|---|
| enableDnsSupport | Cho phép VPC phân giải DNS qua Amazon-provided DNS server. |
| enableDnsHostnames | Cho phép cấp public DNS hostname cho instance có public IP/EIP và hỗ trợ các use case DNS private tương ứng. |

Với private hosted zone và private DNS của interface VPC endpoint, cần bật cả hai thuộc tính. Nếu một thuộc tính bị tắt, Route 53 VPC Resolver có thể không phân giải được Amazon-provided private DNS hostnames.

Kiểm tra bằng AWS CLI:

~~~bash
aws ec2 describe-vpc-attribute \
  --vpc-id vpc-0123456789abcdef0 \
  --attribute enableDnsSupport

aws ec2 describe-vpc-attribute \
  --vpc-id vpc-0123456789abcdef0 \
  --attribute enableDnsHostnames
~~~

Không bật/tắt DNS attributes theo kiểu thử ngẫu nhiên trên production. Xác định trước workload nào phụ thuộc custom DNS, private hosted zone hoặc private endpoint.

### 2.2. Kiểm tra từ EC2 instance

Linux:

~~~bash
cat /etc/resolv.conf

getent hosts api.internal.example.com

dig api.internal.example.com A

dig api.internal.example.com AAAA

dig @10.20.0.2 api.internal.example.com A
~~~

Windows PowerShell:

~~~powershell
Get-DnsClientServerAddress

Resolve-DnsName api.internal.example.com -Type A

Resolve-DnsName api.internal.example.com -Type AAAA
~~~

Cách đọc kết quả:

| Kết quả | Ý nghĩa cần kiểm tra |
|---|---|
| NOERROR có answer | Tên đã phân giải; kiểm tra IP trả về có đúng môi trường/endpoint mong muốn không. |
| NXDOMAIN | Resolver không tìm thấy tên trong namespace đang hỏi; kiểm tra spelling, hosted zone và record. |
| SERVFAIL | Resolver không hoàn tất truy vấn; kiểm tra forwarding rule, upstream DNS, DNS Firewall hoặc DNSSEC. |
| Timeout | Client không nhận được DNS response; kiểm tra resolver address, custom DNS, DHCP options và đường tới DNS server riêng. |
| A đúng nhưng AAAA sai | Workload có thể chọn IPv6 rồi thất bại dù IPv4 hoạt động; kiểm tra IPv6 route và endpoint. |
| IP cũ | Có thể do TTL/cache ở resolver, OS, JVM hoặc ứng dụng; kiểm tra TTL và cache layer. |

Đừng chỉ dùng ping hostname để kết luận DNS lỗi. Ping có thể bị chặn ICMP trong khi DNS và TCP vẫn hoạt động. Hãy dùng dig, Resolve-DnsName hoặc getent để kiểm tra DNS độc lập.

### 2.3. Private hosted zone

Private hosted zone chỉ được phân giải trong các VPC được associate với zone hoặc được liên kết qua cơ chế DNS phù hợp. Kiểm tra:

- Tên domain của hosted zone có khớp với hostname đang hỏi không.
- VPC của workload đã được associate với private hosted zone chưa.
- Record A, AAAA, CNAME hoặc alias có đúng target không.
- Có private hosted zone khác cùng namespace gây shadowing tên public không.
- Resolver rule có đang forward domain đó tới DNS server khác không.
- DHCP option set có trỏ tới custom DNS resolver không.

Một private hosted zone có thể trả NXDOMAIN cho tên mà public DNS có record nếu private namespace được ưu tiên nhưng record nội bộ không tồn tại. Đây là nguyên nhân phổ biến khi ứng dụng trong VPC phân giải khác với máy tính bên ngoài.

### 2.4. Hybrid DNS với on-premises

Khi VPC cần phân giải domain ở data center, hoặc on-premises cần phân giải tên trong private hosted zone, dùng Route 53 VPC Resolver endpoints:

| Endpoint | Hướng truy vấn |
|---|---|
| Inbound Resolver endpoint | DNS resolver on-premises hoặc VPC khác gửi query vào AWS để phân giải private hosted zone. |
| Outbound Resolver endpoint | VPC Resolver gửi query từ AWS tới DNS resolver on-premises theo forwarding rule. |

Luồng outbound điển hình:

1. Tạo outbound endpoint trong VPC có đường mạng tới DNS server on-premises.
2. Security Group của endpoint cho phép outbound TCP/UDP 53 tới resolver đích.
3. Tạo forwarding rule cho domain, ví dụ corp.example.com.
4. Associate rule với các VPC cần dùng.
5. Kiểm tra route qua VPN hoặc Direct Connect và firewall ở hai đầu.

Luồng inbound điển hình:

1. Tạo inbound endpoint với các IP trong nhiều Availability Zones theo yêu cầu availability.
2. Security Group cho phép inbound TCP/UDP 53 từ DNS resolver on-premises.
3. Cấu hình DNS server on-premises forward domain private tới các IP inbound endpoint.
4. Kiểm tra route, NACL và firewall giữa hai mạng.

Không forward query từ on-premises trực tiếp tới địa chỉ VPC CIDR + 2. AWS khuyến nghị dùng inbound Resolver endpoint cho truy vấn từ mạng ngoài VPC.

### 2.5. DNS query logging và DNS Firewall

VPC Resolver query logging ghi lại DNS queries và response code, ví dụ NOERROR, NXDOMAIN hoặc SERVFAIL. Log có thể gửi tới CloudWatch Logs, S3 hoặc Firehose.

Lưu ý: Resolver cache các câu trả lời theo TTL. Query logs ghi các truy vấn unique mà Resolver xử lý; các lần trả lời từ cache có thể không xuất hiện thành một log record mới.

Nếu cần chặn domain, dùng Route 53 Resolver DNS Firewall. Security Group và Network ACL không lọc được traffic DNS tới/từ AmazonProvidedDNS. DNS Firewall mới là lớp kiểm soát domain dành cho các truy vấn đi qua VPC Resolver.

## 3. Đọc và kiểm tra route table

Route table quyết định next hop cho traffic dựa trên destination IP. Mỗi subnet được associate với một route table; nếu không có explicit association, subnet dùng main route table của VPC.

Mỗi route có destination và target. Ví dụ:

| Destination | Target | Ý nghĩa |
|---|---|---|
| 10.20.0.0/16 | local | Traffic nội bộ trong VPC |
| 0.0.0.0/0 | igw-... | IPv4 internet route qua Internet Gateway |
| 0.0.0.0/0 | nat-... | IPv4 outbound route từ private subnet qua NAT Gateway |
| pl-... | vpce-... | Route tới S3/DynamoDB gateway endpoint qua prefix list |
| 10.30.0.0/16 | pcx-... | Route tới VPC peering |
| 10.40.0.0/16 | tgw-... | Route tới Transit Gateway |
| 192.168.0.0/16 | vgw-... | Route tới Virtual Private Gateway/VPN |

### 3.1. Longest prefix match

Khi nhiều route cùng khớp destination, VPC chọn route cụ thể nhất (longest prefix match). Ví dụ:

| Route | Target |
|---|---|
| 0.0.0.0/0 | NAT Gateway |
| 10.30.0.0/16 | VPC peering |
| 10.30.5.0/24 | Transit Gateway |

Traffic tới 10.30.5.10 khớp cả ba route nhưng chọn 10.30.5.0/24 vì prefix cụ thể nhất. Một route cụ thể trỏ sai target có thể làm traffic đi lệch dù default route đúng.

Khi các route có cùng prefix, route priority còn xét loại route: static route được ưu tiên trước prefix-list route, sau đó là propagated route. Khi nghi ngờ, kiểm tra route table thực tế và trạng thái route thay vì chỉ nhìn một default route.

### 3.2. Public subnet và Internet Gateway

Để EC2 truy cập Internet qua IPv4 bằng Internet Gateway, cần đồng thời:

- Internet Gateway được attach vào VPC.
- Route table của subnet có route phù hợp, thường là 0.0.0.0/0 → igw-....
- EC2 có public IPv4 hoặc Elastic IP.
- Security Group và NACL cho phép traffic.
- Ứng dụng đích hoặc firewall bên ngoài cho phép kết nối.

Có route tới IGW không tự cấp public IP cho instance. Một EC2 chỉ có private IP không thể trực tiếp giao tiếp Internet IPv4 qua IGW.

IPv6 là một đường riêng. Workload cần IPv6 CIDR và IPv6 address, cùng route ::/0 tới IGW nếu cần kết nối hai chiều Internet.

### 3.3. Private subnet và NAT Gateway

Private subnet có thể khởi tạo kết nối Internet IPv4 qua NAT Gateway:

- NAT Gateway nằm trong public subnet.
- NAT Gateway ở trạng thái Available và có Elastic IP cho public NAT Gateway.
- Public subnet của NAT có route tới IGW.
- Route table của private subnet có route 0.0.0.0/0 → nat-....
- Security Group/NACL cho phép kết nối và traffic phản hồi.

NAT Gateway cho phép workload private khởi tạo outbound connections; nó không cung cấp inbound access tùy ý từ Internet tới instance private.

Với kiến trúc nhiều AZ, nên cân nhắc NAT Gateway theo từng AZ để giảm phụ thuộc liên AZ và tăng khả năng chịu lỗi. Một route tới NAT Gateway ở AZ khác có thể tạo data transfer liên AZ và phụ thuộc vào AZ đó.

Với IPv6 outbound-only, xem xét Egress-only Internet Gateway và route ::/0; NAT Gateway IPv4 không thay thế cơ chế IPv6 này.

### 3.4. VPC endpoints

Nếu workload truy cập dịch vụ AWS, có thể dùng VPC endpoint để tránh đi qua Internet/NAT:

| Endpoint | Đặc điểm cần kiểm tra |
|---|---|
| Gateway endpoint | Dùng route table và prefix list; phổ biến cho Amazon S3 và DynamoDB. |
| Interface endpoint | Tạo endpoint network interfaces trong subnet; Security Group của endpoint kiểm soát inbound traffic tới ENI. |

Với interface endpoint:

- VPC phải bật enableDnsSupport và enableDnsHostnames nếu dùng private DNS.
- Private DNS name của endpoint phải được bật nếu ứng dụng gọi service hostname chuẩn.
- Security Group endpoint phải cho phép inbound TCP 443 từ workload client.
- Endpoint policy phải cho phép action/resource cần dùng.
- IAM policy và resource policy của dịch vụ đích vẫn áp dụng.

Với gateway endpoint, kiểm tra route table association và endpoint policy. Gateway endpoint không có endpoint ENI để gắn Security Group.

### 3.5. Kiểm tra route table bằng AWS CLI

~~~bash
aws ec2 describe-route-tables \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0

# Inspect every route table in the VPC, including the main route table
aws ec2 describe-route-tables \
  --filters Name=vpc-id,Values=vpc-0123456789abcdef0

aws ec2 describe-route-tables \
  --route-table-ids rtb-0123456789abcdef0
~~~

Đọc các trường:

- Associations: subnet nào đang dùng route table.
- Routes: destination, target và State.
- Origin: route do người dùng tạo hay được propagate.
- State: route active hay blackhole.
- GatewayId, NatGatewayId, VpcPeeringConnectionId, TransitGatewayId: next hop cụ thể.

Một route blackhole không chuyển tiếp được traffic. Kiểm tra target có bị xóa, attachment có mất hoặc propagation có bị tắt hay không.

## 4. Security Group: firewall stateful ở network interface

Security Group là virtual firewall gắn với resource network interface. Security Group chỉ có allow rules; traffic không khớp rule allow sẽ bị từ chối.

Security Group có tính stateful. Khi một kết nối được cho phép, response traffic của kết nối đó được cho phép tự động, kể cả khi không có outbound/inbound rule đối xứng tương ứng.

### 4.1. Kiểm tra đúng interface và đúng cổng

Một EC2 có thể có nhiều ENI và nhiều Security Group. Đừng chỉ xem SG theo tên instance; xác minh ENI thực tế đang nhận traffic.

~~~bash
aws ec2 describe-network-interfaces \
  --network-interface-ids eni-0123456789abcdef0

aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0
~~~

Ví dụ ứng dụng web chạy TCP 443 và kết nối PostgreSQL TCP 5432:

| Resource | Inbound rule | Outbound rule |
|---|---|---|
| ALB SG | TCP 443 từ client CIDR được phép | TCP port ứng dụng tới App SG |
| App SG | TCP port ứng dụng từ ALB SG | TCP 5432 tới DB SG |
| DB SG | TCP 5432 từ App SG | Response traffic được SG stateful cho phép |

Mẫu này giới hạn nguồn theo Security Group của tầng gọi. Tránh mở database port cho 0.0.0.0/0 hoặc toàn bộ VPC nếu chỉ app tier cần truy cập.

### 4.2. Kiểm tra các lỗi Security Group thường gặp

- Inbound rule mở sai port, protocol hoặc source CIDR.
- Rule dùng IP public trong khi traffic thực tế đi bằng private IP.
- SG được gắn vào ENI khác với ENI đang phục vụ.
- Outbound rules bị giới hạn và không cho phép client khởi tạo kết nối.
- Security Group reference không hợp lệ trong topology liên VPC.
- Source workload thay đổi SG nhưng rule tham chiếu chưa cập nhật đúng.
- Traffic qua middlebox/NAT làm source IP khác dự kiến.

Security Group reference cho phép dùng SG làm source/destination trong các topology được hỗ trợ. Với inbound rule, SG được tham chiếu có thể nằm trong cùng VPC, VPC có peering connection hoặc VPC kết nối qua Transit Gateway. Với outbound rule, phạm vi tham chiếu gồm cùng VPC hoặc VPC có peering connection. Tuy nhiên, không phải mọi đường đi qua middlebox đều giữ semantics của SG reference. Khi traffic giữa hai instance trong subnet đi qua middlebox appliance, SG reference có thể không cho phép traffic như mong đợi; khi đó cần kiểm tra private IP hoặc CIDR nguồn/đích.

### 4.3. Những traffic SG không lọc

Security Group không lọc traffic tới/từ một số dịch vụ nền tảng, gồm AmazonProvidedDNS, DHCP, instance metadata, ECS task metadata, Windows license activation, Amazon Time Sync Service và một số địa chỉ router dành riêng. Nếu muốn lọc DNS query qua AmazonProvidedDNS, dùng Route 53 Resolver DNS Firewall.

## 5. Network ACL: firewall stateless ở subnet

Network ACL (NACL) áp dụng tại subnet, có inbound và outbound rules. Khác Security Group, NACL là stateless: AWS không tự cho phép response traffic chỉ vì request ban đầu đã được cho phép.

NACL hỗ trợ cả allow và deny. Rule được xét theo số thứ tự tăng dần; rule đầu tiên khớp traffic sẽ quyết định allow/deny.

### 5.1. Ví dụ vì sao request đi được nhưng response bị chặn

Một máy client ngoài VPC mở TCP connection tới web server trong subnet:

- Request có destination port 443.
- Client chọn một source ephemeral port, ví dụ 49152.
- Response từ server có source port 443 và destination port 49152.

Nếu NACL inbound cho phép request tới port 443 nhưng outbound không cho phép response tới ephemeral port của client, kết nối có thể timeout dù Security Group stateful đã cho phép response.

Ephemeral port range phụ thuộc hệ điều hành và thiết bị khởi tạo. Ví dụ, nhiều Linux kernels dùng khoảng 32768–61000; Windows Server hiện đại thường dùng 49152–65535; NAT Gateway và một số dịch vụ AWS dùng phạm vi khác. Hãy xác định nguồn traffic thực tế và chọn phạm vi cần thiết thay vì sao chép một dải port chung mà không kiểm tra.

### 5.2. Checklist NACL

- Kiểm tra NACL đang associate với subnet nguồn và subnet đích.
- Kiểm tra cả inbound lẫn outbound.
- Kiểm tra rule number thấp hơn có deny trước rule allow hay không.
- Kiểm tra protocol, port, source/destination CIDR.
- Kiểm tra IPv4 và IPv6 riêng; rule IPv4 không áp dụng cho IPv6.
- Kiểm tra ephemeral ports cho response traffic.
- Kiểm tra NACL ở cả hai subnet khi kết nối đi qua hai subnet khác nhau.

NACL không lọc traffic tới/từ AmazonProvidedDNS, DHCP và một số dịch vụ nền tảng khác. Nếu cần domain filtering cho AmazonProvidedDNS, dùng DNS Firewall.

## 6. Kết nối giữa VPC, subnet và mạng on-premises

### 6.1. VPC peering

Khi dùng VPC peering, kiểm tra:

- Peering connection ở trạng thái active.
- CIDR của hai VPC không overlap.
- Route table ở cả hai phía có route tới CIDR VPC peer qua peering connection.
- Security Group cho phép nguồn/đích và port.
- NACL hai subnet cho phép cả request và response.
- DNS resolution options nếu cần phân giải tên qua peering.

VPC peering không có tính transitive. Nếu VPC-A peering với VPC-B và VPC-B peering với VPC-C, traffic không tự động đi từ A sang C qua B. Cần topology như Transit Gateway hoặc một thiết kế network appliance phù hợp.

### 6.2. Transit Gateway

Với Transit Gateway, kiểm tra nhiều lớp:

1. Attachment của VPC/VPN/DX có trạng thái available.
2. Subnet attachment có route tới TGW.
3. TGW route table được association với attachment đúng.
4. Route được propagation hoặc static route đã tồn tại.
5. TGW route table có đường tới attachment đích.
6. Route table của subnet đích có đường phản hồi.
7. SG/NACL tại resource đích cho phép traffic.

Một attachment có thể được associate với một TGW route table, còn propagation là cơ chế đưa route của attachment vào route table. Không nhầm association với propagation.

### 6.3. Site-to-Site VPN và Direct Connect

Nếu kết nối tới on-premises:

- Kiểm tra VPN tunnel state hoặc Direct Connect virtual interface.
- Kiểm tra BGP session và route advertisement nếu dùng dynamic routing.
- Xác minh on-premises firewall cho phép CIDR/port.
- Kiểm tra route về AWS ở phía on-premises.
- Kiểm tra route về on-premises ở VPC/TGW.
- Xác minh CIDR không overlap hoặc bị route summary che lấp.
- Kiểm tra MTU/MSS khi có symptom chỉ lỗi với payload lớn hoặc TLS handshake.

Một đường đi một chiều chưa đủ. Cả request và response phải có route hợp lệ.

## 7. Reachability Analyzer: tìm blocker trong cấu hình mạng

VPC Reachability Analyzer là công cụ phân tích cấu hình tĩnh. Người dùng chọn source, destination, protocol và port; công cụ mô hình hóa virtual network path, trả hop-by-hop details khi path reachable hoặc chỉ ra component đang chặn path.

Reachability Analyzer có thể xác định các vấn đề trong:

- Route table.
- Security Group.
- Network ACL.
- VPC peering hoặc Transit Gateway.
- NAT Gateway, Internet Gateway và một số network components được hỗ trợ.
- Load balancer, VPC endpoint và attachment theo topology được hỗ trợ.

### 7.1. Khi nào dùng?

Ví dụ: EC2 app trong private subnet không kết nối được tới database ENI trên TCP 5432.

1. Chọn app ENI làm source.
2. Chọn database ENI làm destination.
3. Chọn TCP và destination port 5432.
4. Chạy analysis.
5. Đọc path components và explanation code.
6. Sửa đúng route/SG/NACL được chỉ ra.
7. Chạy lại analysis và kiểm tra từ workload.

Reachability Analyzer là static configuration analysis, không gửi gói tin thực qua ứng dụng. Một path được đánh giá reachable không chứng minh database process đang chạy, DNS trả đúng tên, OS firewall cho phép, TLS hợp lệ hoặc ứng dụng chấp nhận request.

Công cụ chỉ hỗ trợ các resource types và topology nhất định. Source/destination phải cùng Region và nằm trong cùng VPC hoặc các VPC kết nối qua peering/TGW được hỗ trợ. Khi gặp unsupported component hoặc path phức tạp, kết hợp Flow Logs và kiểm thử runtime.

## 8. VPC Flow Logs: quan sát traffic thực tế

VPC Flow Logs ghi metadata về IP traffic đi tới và đi từ VPC, subnet hoặc network interface. Có thể gửi log tới CloudWatch Logs, S3 hoặc Firehose.

Flow Logs hữu ích để:

- Xác định traffic có tới ENI không.
- Phân biệt traffic được accept và reject ở network layer.
- Xác định source/destination IP, port và protocol.
- Phân tích hướng request/response.
- Điều tra Security Group hoặc NACL quá chặt.

Một record minh họa:

~~~text
2 123456789012 eni-0123456789abcdef0 10.20.1.15 10.20.3.25 49152 5432 6 12 840 1763652000 1763652060 REJECT OK
~~~

Các trường trong ví dụ lần lượt gồm version, account, interface ID, source/destination address, source/destination port, protocol, packets, bytes, start/end, action và log status.

- ACCEPT: traffic được network controls cho phép.
- REJECT: traffic bị từ chối, ví dụ bởi Security Group hoặc NACL, hoặc packet đến sau khi connection đã đóng.
- OK: log được ghi bình thường.
- NODATA: không có traffic trong aggregation interval.
- SKIPDATA: một số record bị bỏ qua trong interval.

### 8.1. Giới hạn của Flow Logs

Flow Logs không chứa packet payload, không cho biết ứng dụng trả HTTP status nào và không chứng minh service listener đang hoạt động. Traffic tới/từ Amazon DNS server (AmazonProvidedDNS/VPC Resolver), DHCP, instance metadata và một số địa chỉ nền tảng không được ghi. Vì vậy, không có Flow Log record cho DNS query tới VPC Resolver không đồng nghĩa DNS client không gửi truy vấn.

Flow Logs được tổng hợp theo interval và có thể trễ. Một số record có thể bị skip; hãy xem log-status và trạng thái delivery. Khi cần bằng chứng DNS, bật Resolver query logging.

### 8.2. Đọc Flow Logs để xác định chiều lỗi

Ví dụ:

- Có ACCEPT từ app ENI tới DB ENI trên TCP 5432 nhưng không có response: kiểm tra DB listener, host firewall, return route, NACL outbound/inbound và database logs.
- Có REJECT từ app tới DB: kiểm tra SG/NACL theo đúng source/destination/port.
- Có request ACCEPT nhưng response REJECT: thường cần xem NACL stateless và ephemeral port ở chiều trả về.
- Không có record ở ENI đích: kiểm tra route, source ENI, endpoint/attachment và phạm vi Flow Logs.

Flow Logs ghi nhận traffic ở network layer; một record ACCEPT không có nghĩa ứng dụng đã xử lý thành công.

## 9. Phân biệt các công cụ quan sát

| Công cụ | Trả lời câu hỏi | Giới hạn chính |
|---|---|---|
| dig, nslookup, Resolve-DnsName | Hostname phân giải ra IP nào? | Chỉ phản ánh resolver và cache tại thời điểm test |
| Route 53 Resolver query logs | VPC Resolver nhận query gì và trả response code nào? | Cache hit có thể không sinh log record mới |
| Reachability Analyzer | Cấu hình mạng có cho phép virtual path không? | Phân tích tĩnh, không gửi packet tới ứng dụng |
| VPC Flow Logs | ENI/subnet/VPC có traffic nào được accept/reject? | Không có payload; không log AmazonProvidedDNS traffic |
| Network Access Analyzer | Network access có vi phạm intent/security posture không? | Phân tích access path, không phải probe runtime |
| nc, curl, Test-NetConnection | Từ workload thật có kết nối TCP/TLS/HTTP được không? | Chỉ kiểm tra path và service tại thời điểm thực hiện |
| CloudTrail | Ai thay đổi route, SG, NACL hoặc endpoint và khi nào? | Ghi API activity, không phải packet trace |

Một quy trình tốt dùng Reachability Analyzer để tìm cấu hình đáng ngờ, Flow Logs để quan sát traffic và kiểm thử runtime để xác nhận kết quả thực tế.

## 10. Kiểm tra từ chính workload

### 10.1. Linux

Kiểm tra interface và địa chỉ:

~~~bash
ip addr

ip route

ip route get 10.20.3.25
~~~

ip route get cho biết route mà kernel trên máy nguồn sẽ dùng. Nó không hiển thị toàn bộ VPC route table hoặc TGW route table.

Kiểm tra TCP:

~~~bash
nc -vz -w 5 db.internal.example.com 5432

curl -v --connect-timeout 5 https://api.internal.example.com/health

openssl s_client \
  -connect api.internal.example.com:443 \
  -servername api.internal.example.com
~~~

Cách đọc:

- DNS resolve được nhưng nc timeout: kiểm tra route, SG, NACL, firewall và return path.
- nc báo connection refused: TCP đã tới host nhưng port không có listener hoặc host từ chối.
- TCP kết nối được nhưng TLS fail: kiểm tra certificate, SNI, trust store, TLS version và thời gian hệ thống.
- TLS thành công nhưng HTTP 403/5xx: network path đã hoạt động; kiểm tra authorization, load balancer, WAF hoặc ứng dụng.

### 10.2. Windows PowerShell

~~~powershell
Resolve-DnsName db.internal.example.com

Test-NetConnection db.internal.example.com -Port 5432 -InformationLevel Detailed

tracert db.internal.example.com
~~~

Test-NetConnection hiển thị địa chỉ remote, interface nguồn và kết quả TCP test. tracert có thể không hiển thị đầy đủ hop vì ICMP/TTL-expired traffic có thể bị lọc; không kết luận route sai chỉ từ dấu *.

### 10.3. Kiểm tra IPv4 và IPv6 riêng

Nếu DNS trả cả A và AAAA, ứng dụng có thể chọn IPv6 trước hoặc thử cả hai. Một route IPv4 đúng không đảm bảo IPv6 đúng.

~~~bash
dig api.example.com A

dig api.example.com AAAA

curl -4 -v https://api.example.com/health

curl -6 -v https://api.example.com/health
~~~

Nếu chỉ IPv6 thất bại, kiểm tra IPv6 CIDR, địa chỉ gắn vào ENI, route ::/0, Egress-only IGW, SG/NACL IPv6 rules và endpoint support.

## 11. Quy trình troubleshooting theo từng lớp

Dùng trình tự sau cho một kết nối lỗi:

1. **Xác định symptom:** DNS error, timeout, refused, TLS error hay HTTP error.
2. **Kiểm tra DNS:** resolve A/AAAA, so sánh IP với endpoint dự kiến và xem query logs nếu có.
3. **Kiểm tra IP path:** xác định source ENI/subnet, destination ENI/IP, route table association và longest prefix match.
4. **Kiểm tra route hai chiều:** route tới đích và route trả về có hợp lệ không?
5. **Kiểm tra Security Group:** đúng ENI, đúng source/destination, protocol và port.
6. **Kiểm tra NACL:** cả inbound/outbound và ephemeral ports ở hai subnet.
7. **Kiểm tra middlebox/endpoint:** NAT state, IGW attachment, TGW attachment/route table, endpoint ENI/endpoint policy.
8. **Kiểm tra runtime:** TCP connect, TLS handshake, service listener, OS firewall và application logs.
9. **Đối chiếu telemetry:** Reachability Analyzer, Flow Logs, Resolver query logs, CloudTrail và CloudWatch.
10. **Sửa một nguyên nhân đã có bằng chứng:** chạy lại cùng test, so sánh trước/sau và ghi lại thay đổi.

Không mở rộng toàn bộ outbound/inbound thành 0.0.0.0/0 hoặc ::/0 để thử xem có chạy không. Nếu cần một phép thử tạm thời, giới hạn nguồn, port, thời gian, ghi change ticket và rollback ngay sau kiểm chứng.

## 12. Các kịch bản lỗi thường gặp

### 12.1. EC2 không phân giải được private hostname

Triệu chứng: dig app.internal.example.com trả NXDOMAIN hoặc SERVFAIL.

Kiểm tra:

- enableDnsSupport=true và enableDnsHostnames=true.
- Private hosted zone đã associate với đúng VPC.
- Record có đúng tên và target.
- DHCP options có trỏ tới custom DNS resolver ngoài dự kiến không.
- Resolver forwarding rule có domain match cụ thể hơn không.
- DNS Firewall có chặn query không.
- Query logs ghi response code nào.

Nếu custom DNS nằm on-premises, kiểm tra outbound Resolver endpoint, security group TCP/UDP 53, route VPN/DX và upstream DNS server.

### 12.2. App server không kết nối được database trên TCP 5432

Triệu chứng: nc -vz db.internal.example.com 5432 timeout.

Kiểm tra theo thứ tự:

- DNS trả private IP của DB đúng không?
- App subnet route table có route tới DB subnet CIDR qua local không?
- DB ENI có đúng Security Group không?
- DB SG inbound có TCP 5432 từ app SG không?
- App SG outbound có cho TCP 5432 tới DB không nếu egress bị giới hạn?
- NACL của cả hai subnet có allow request và ephemeral response không?
- DB có đang ở trạng thái available và listener trên 5432 không?
- Host firewall và DB access rules có cho phép không?

Nếu Reachability Analyzer báo path reachable nhưng nc vẫn timeout, kiểm tra listener, host firewall, database service và return traffic thực tế.

### 12.3. EC2 private subnet không gọi được public API

Kiểm tra:

- Route table private subnet có 0.0.0.0/0 → nat-... không?
- NAT Gateway có Available và nằm trong public subnet không?
- Public subnet của NAT có 0.0.0.0/0 → igw-... không?
- NAT Gateway có Elastic IP không?
- NACL/SG có cho phép outbound TCP 443 và response ephemeral ports không?
- DNS resolve hostname public đúng không?
- Có proxy, firewall hoặc route cụ thể hơn đang chuyển traffic sang target khác không?

Nếu chỉ gọi một dịch vụ AWS, cân nhắc VPC endpoint để dùng private connectivity và giảm phụ thuộc NAT/Internet.

### 12.4. Kết nối qua VPC peering thất bại

Kiểm tra:

- CIDR hai VPC không overlap.
- Peering connection active.
- Route table ở source có route tới peer CIDR qua peering.
- Route table ở destination có route về source CIDR.
- SG/NACL cho phép traffic cả hai chiều.
- DNS resolution option phù hợp nếu gọi bằng hostname.

Đừng giả định VPC peering có transitive routing.

### 12.5. Kết nối tới interface VPC endpoint timeout

Kiểm tra:

- Endpoint ở trạng thái available.
- Endpoint có subnet/ENI trong AZ mà workload có thể reach.
- Private DNS đã bật và DNS attributes của VPC đúng.
- SG của endpoint cho inbound TCP 443 từ workload.
- SG outbound của workload cho phép TCP 443 tới endpoint.
- NACL của các subnet cho phép request/response.
- Endpoint policy, IAM policy và service resource policy cho phép action.

Nếu TCP 443 kết nối được nhưng API trả AccessDenied, vấn đề nằm ở authorization/policy thay vì network path.

### 12.6. Kết nối hoạt động bằng IP nhưng lỗi bằng hostname

Khả năng cao lỗi nằm ở DNS hoặc TLS hostname validation:

- Hostname resolve sang IP khác với IP vừa kiểm thử.
- Private hosted zone shadowing public record.
- A/AAAA record không đồng nhất.
- Ứng dụng giữ DNS cache lâu hơn TTL.
- TLS certificate không chứa hostname hoặc SNI không được gửi đúng.
- HTTP Host header hoặc reverse proxy virtual host không khớp.

Dùng curl -v và openssl s_client -servername để tách DNS/TCP khỏi TLS/SNI.

## 13. AWS CLI: thu thập cấu hình mạng chỉ đọc

Các lệnh sau giúp thu thập cấu hình trước khi thay đổi:

~~~bash
# VPC DNS attributes
aws ec2 describe-vpc-attribute \
  --vpc-id vpc-0123456789abcdef0 \
  --attribute enableDnsSupport

# Route table associated with a subnet
aws ec2 describe-route-tables \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0

# Security groups attached to the workload
aws ec2 describe-network-interfaces \
  --network-interface-ids eni-0123456789abcdef0

aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0

# Network ACL associated with a subnet
aws ec2 describe-network-acls \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0

# VPC endpoints
aws ec2 describe-vpc-endpoints \
  --filters Name=vpc-id,Values=vpc-0123456789abcdef0

# Flow log configuration
aws ec2 describe-flow-logs \
  --filter Name=resource-id,Values=eni-0123456789abcdef0
~~~

Dùng đúng Region và account profile của resource đang điều tra. Nếu workload đi qua nhiều account, cần quyền đọc cấu hình ở các account/VPC liên quan; thiếu quyền đọc không có nghĩa resource không tồn tại.

## 14. Observability và thay đổi cấu hình

Network troubleshooting cần correlation giữa thời điểm lỗi và thay đổi cấu hình.

Nên theo dõi:

- EC2 status checks và application health.
- VPC Flow Logs ở ENI/subnet/VPC trọng yếu.
- Route 53 VPC Resolver query logs cho các VPC dùng private/hybrid DNS.
- Reachability Analyzer cho các path quan trọng.
- CloudTrail cho thay đổi route table, SG, NACL, VPC endpoint, peering và TGW.
- CloudWatch alarms cho tunnel state, NAT Gateway metrics, endpoint health và application timeout.

VPC Flow Logs có thể gửi tới CloudWatch Logs, S3 hoặc Firehose. Với workload có lưu lượng lớn, cân nhắc chi phí ingest, retention, query và dung lượng archive. Resolver query logs có thể chứa hostname nội bộ và hành vi truy cập; giới hạn quyền truy cập và thời gian lưu.

Khi triển khai thay đổi mạng:

1. Lưu trạng thái trước thay đổi.
2. Ghi rõ resource ID và rule/route cần sửa.
3. Dùng change review hoặc IaC để có diff.
4. Áp dụng từng thay đổi nhỏ.
5. Chạy lại test DNS/TCP/application.
6. Kiểm tra Flow Logs và metric.
7. Rollback nếu symptom xấu hơn.
8. Ghi nguyên nhân gốc và biện pháp ngăn tái diễn.

## 15. Bảo mật khi khắc phục sự cố

Một số thao tác chữa nhanh có thể làm lộ dịch vụ hoặc mở rộng phạm vi truy cập quá mức.

- Không mở SSH/RDP/database port tới 0.0.0.0/0 hoặc ::/0 nếu không có nhu cầu và phê duyệt cụ thể.
- Không thêm rule all traffic chỉ để kiểm tra một cổng.
- Ưu tiên SG reference hoặc CIDR hẹp theo workload.
- Dùng NACL như lớp kiểm soát subnet bổ sung, không sao chép SG rule mà quên response ports.
- Không tắt DNS Firewall hoặc security control trên diện rộng để xử lý một hostname.
- Không thay default route của cả subnet khi chỉ một workload có lỗi.
- Hạn chế quyền sửa route, SG, NACL và Resolver rules theo least privilege.
- Ghi audit và thời hạn cho rule tạm.
- Sau khi test, xóa rule tạm và xác minh cấu hình cuối.

## 16. Tình huống thực hành: chẩn đoán kết nối App → RDS

Một ứng dụng EC2 nằm trong private subnet 10.20.1.0/24. Database RDS có private address trong subnet 10.20.3.0/24. Ứng dụng dùng hostname orders-db.internal.example.com và TCP port 5432.

Người dùng báo lỗi timeout sau một lần cập nhật network policy.

### Bước 1: Xác minh DNS

~~~bash
dig orders-db.internal.example.com A

getent hosts orders-db.internal.example.com
~~~

Kết quả trả về IP 10.20.3.25, đúng private range của DB. Nếu không đúng, kiểm tra private hosted zone, VPC association và Resolver logs trước khi kiểm tra route.

### Bước 2: Kiểm tra route

Subnet app và DB nằm trong cùng VPC. Route table phải có local route cho VPC CIDR. Kiểm tra route table association của cả hai subnet và đảm bảo không có route cụ thể hơn chuyển traffic sai target.

### Bước 3: Kiểm tra Security Group

- App SG outbound cho TCP 5432 tới DB SG.
- DB SG inbound cho TCP 5432 từ App SG.
- SG gắn đúng vào ENI của workload.
- DB đang available và listener trên port 5432.

### Bước 4: Kiểm tra NACL

Subnet app và DB dùng custom NACL. Kiểm tra inbound/outbound trên cả hai NACL, đặc biệt response traffic tới ephemeral port của client. Nếu chỉ allow port 5432 mà deny dải ephemeral ở chiều phản hồi, TCP handshake có thể không hoàn tất.

### Bước 5: Dùng Reachability Analyzer

Chọn app ENI làm source, DB ENI làm destination, TCP port 5432. Nếu analysis chỉ ra NACL hoặc SG chặn, sửa đúng rule. Nếu path reachable, tiếp tục kiểm tra Flow Logs và service listener.

### Bước 6: Kiểm thử runtime

~~~bash
nc -vz -w 5 orders-db.internal.example.com 5432
~~~

Sau khi TCP connect thành công, dùng database client để xác minh TLS, authentication và database authorization. Không dùng việc TCP port mở làm bằng chứng rằng ứng dụng đã truy cập được dữ liệu.

### Bước 7: Xác nhận và ghi nhận

- Chạy lại DNS và TCP test từ cùng EC2.
- Kiểm tra Flow Logs không còn REJECT cho tuple liên quan.
- Kiểm tra ứng dụng hoàn tất health check.
- Ghi lại SG/NACL/route change và lý do.
- Cập nhật runbook để tránh lặp lại lỗi.

## 17. Bài thực hành: phân biệt DNS, route và SG

Mục tiêu: quan sát ba lỗi khác nhau trong môi trường lab.

### Chuẩn bị

- Một VPC có hai private subnets.
- Một EC2 app trong subnet A.
- Một EC2 web/test server trong subnet B, lắng nghe TCP 8080.
- Security Group riêng cho app và server.
- Một private hosted zone có record trỏ tới server.
- VPC Flow Logs được bật cho ENI hoặc subnet trong lab.

### Thử nghiệm A: lỗi DNS

1. Kiểm tra hostname bằng dig hoặc Resolve-DnsName.
2. Thay đổi record trong private hosted zone ở môi trường lab hoặc dùng hostname không tồn tại.
3. Quan sát NXDOMAIN và Resolver query logs.
4. Khôi phục record và kiểm tra TTL/cache.

### Thử nghiệm B: lỗi Security Group

1. Giữ DNS và route đúng.
2. Gỡ rule inbound TCP 8080 từ app SG khỏi server SG.
3. Thử nc -vz server.internal.example.com 8080.
4. Kiểm tra Flow Logs có REJECT cho traffic liên quan.
5. Dùng Reachability Analyzer để tìm SG blocker.
6. Khôi phục rule nguồn hẹp.

### Thử nghiệm C: lỗi Network ACL

1. Tạo custom NACL cho subnet server.
2. Cho inbound TCP 8080 nhưng tạm chặn response traffic ở outbound.
3. Thử kết nối từ app và quan sát timeout.
4. Kiểm tra Flow Logs ở cả hai ENI.
5. Bổ sung rule response ephemeral ports phù hợp với client.
6. Xác nhận TCP connection thành công.

Thực hiện trong tài khoản lab và subnet không phục vụ production. Ghi lại từng thay đổi để có thể khôi phục trạng thái ban đầu.

## 18. Những sai lầm thường gặp

1. **Thấy EC2 running nên cho rằng mạng hoạt động.** Instance state không chứng minh DNS, route hoặc application path đúng.
2. **Chỉ kiểm tra inbound Security Group.** Client cũng cần outbound phù hợp khi egress bị giới hạn.
3. **Quên return path.** Request đi được không có nghĩa response quay lại được.
4. **Nhầm SG với NACL.** SG stateful; NACL stateless và cần allow cả hai chiều.
5. **Mở port ứng dụng trong NACL nhưng quên ephemeral ports.** TCP handshake có thể timeout ở chiều phản hồi.
6. **Cho rằng SG/NACL có thể chặn AmazonProvidedDNS.** DNS tới VPC Resolver cần DNS Firewall nếu muốn lọc domain.
7. **Quên VPC DNS attributes.** Private hosted zone và private DNS endpoint cần DNS support/hostnames phù hợp.
8. **Forward DNS on-premises tới VPC CIDR+2.** Dùng Resolver inbound endpoint theo khuyến nghị AWS.
9. **Có route IGW nên EC2 chắc chắn ra Internet.** IPv4 instance còn cần public IPv4/EIP và rule phù hợp.
10. **Private subnet có NAT route nhưng NAT đặt sai subnet.** NAT Gateway cần public subnet có route tới IGW.
11. **Chỉ kiểm tra route chiều đi.** VPC peering, TGW, VPN và on-prem cần route phản hồi.
12. **Giả định VPC peering có transitive routing.** Peering không tự định tuyến xuyên qua VPC trung gian.
13. **Cho rằng Flow Logs chứa DNS query tới AmazonProvidedDNS.** Loại traffic này không được ghi.
14. **Coi Reachability Analyzer là live packet test.** Công cụ phân tích cấu hình tĩnh; vẫn cần kiểm thử workload.
15. **Thấy Flow Logs ACCEPT là ứng dụng hoạt động.** ACCEPT chỉ phản ánh network controls cho phép traffic.
16. **Không kiểm tra IPv6.** A/AAAA có thể dẫn tới hai đường đi khác nhau.
17. **Nhầm lỗi network với lỗi application.** Connection refused, TLS failure và HTTP 403 có nguyên nhân khác nhau.
18. **Mở all traffic để sửa nhanh.** Làm giảm bảo mật và khó xác định nguyên nhân thực.
19. **Không kiểm tra thay đổi gần thời điểm xảy ra lỗi.** CloudTrail và IaC diff có thể chỉ ra route/SG/NACL bị đổi.
20. **Không xác minh sau rollback/fix.** Cần chạy lại cùng test và lưu bằng chứng.

## 19. Câu hỏi tự kiểm tra

**1. Trình tự cơ bản để chẩn đoán một kết nối VPC là gì?**

Xác định source/destination/protocol/port, kiểm tra DNS, route, SG, NACL, endpoint/middlebox, return path và service listener.

**2. enableDnsSupport khác enableDnsHostnames thế nào?**

DNS support cho phép phân giải qua Amazon-provided DNS server; DNS hostnames kiểm soát việc cấp public DNS hostname và hỗ trợ các use case private DNS. Private hosted zone/private endpoint thường cần cả hai bật.

**3. Vì sao ứng dụng phân giải hostname khác máy tính bên ngoài?**

Có thể do private hosted zone, custom DHCP DNS, forwarding rule, split-horizon DNS hoặc cache.

**4. Khi nào dùng Resolver inbound endpoint?**

Khi DNS resolver on-premises hoặc mạng khác cần gửi query vào AWS để phân giải private hosted zone.

**5. Security Group và NACL khác nhau thế nào?**

Security Group gắn với network interface/resource, chỉ allow và stateful. NACL gắn với subnet, có allow/deny, stateless và xét rule theo số thứ tự.

**6. Vì sao cần ephemeral ports trong NACL?**

Response của TCP client thường quay về destination port tạm do client chọn; NACL phải cho phép traffic phản hồi ở dải port đó.

**7. Một EC2 trong public subnet có cần public IPv4 để ra Internet qua IGW không?**

Có, với IPv4 cần public IPv4 hoặc Elastic IP, route tới IGW và security rules phù hợp.

**8. NAT Gateway cần nằm ở đâu?**

Public subnet có route tới Internet Gateway; private subnet route IPv4 outbound tới NAT Gateway.

**9. Route table chọn route nào khi có nhiều route khớp?**

Route có prefix cụ thể nhất (longest prefix match) thường được chọn; các quy tắc ưu tiên khác áp dụng khi route cùng prefix.

**10. Vì sao VPC peering không thay thế Transit Gateway trong topology nhiều VPC?**

Peering không có transitive routing; Transit Gateway cung cấp hub routing giữa nhiều VPC và mạng kết nối.

**11. Reachability Analyzer có gửi packet thực không?**

Không. Đây là static configuration analysis để tìm virtual path và component blocker.

**12. Flow Logs có ghi packet payload không?**

Không. Flow Logs ghi metadata như IP, port, protocol, bytes, packets và action.

**13. REJECT trong Flow Logs có nghĩa gì?**

Traffic bị từ chối, ví dụ bởi SG/NACL hoặc packet đến sau khi connection đã đóng; cần đối chiếu tuple và cấu hình.

**14. Vì sao không thấy DNS query trong VPC Flow Logs?**

Traffic tới/từ AmazonProvidedDNS bị loại khỏi Flow Logs; dùng Route 53 VPC Resolver query logging.

**15. TCP connect thành công nhưng HTTP trả 403 có còn là lỗi route không?**

Thông thường network path và TCP đã hoạt động; kiểm tra IAM, application authorization, endpoint policy, WAF hoặc resource policy.

**16. Khi nào nên dùng VPC endpoint thay NAT Gateway?**

Khi workload cần truy cập dịch vụ AWS được hỗ trợ qua private connectivity, giảm phụ thuộc Internet/NAT và kiểm soát bằng endpoint policy.

## 20. Checklist production

- [ ] Ghi rõ source, destination, protocol, port, direction và IP family.
- [ ] DNS A/AAAA trả đúng hostname và IP theo môi trường.
- [ ] VPC DNS attributes phù hợp với private hosted zone/private endpoint.
- [ ] Resolver rule, private hosted zone association và DHCP option set đã được kiểm tra.
- [ ] Hybrid DNS dùng Resolver inbound/outbound endpoint đúng hướng.
- [ ] Subnet đang associate với route table dự kiến.
- [ ] Route active, không có blackhole hoặc prefix cụ thể hơn trỏ sai target.
- [ ] Route phản hồi tồn tại ở mọi VPC/TGW/VPN/on-prem network.
- [ ] Public IPv4/IPv6 và IGW/NAT/Egress-only IGW được cấu hình đúng.
- [ ] VPC endpoint DNS, endpoint SG, route và endpoint policy đúng.
- [ ] SG gắn đúng ENI và chỉ mở protocol/port/source cần thiết.
- [ ] NACL hai chiều và ephemeral port range phù hợp.
- [ ] Peering/TGW attachment và route table association/propagation đúng.
- [ ] Reachability Analyzer đã kiểm tra các path quan trọng.
- [ ] VPC Flow Logs được bật tại scope cần thiết và có retention.
- [ ] Resolver query logs được bật cho VPC cần điều tra DNS.
- [ ] CloudTrail có thể truy vết thay đổi mạng.
- [ ] Có kiểm thử runtime từ workload thật bằng DNS/TCP/TLS/application health check.
- [ ] Có dashboard timeout, DNS error, REJECT, NAT/endpoint health và tunnel state.
- [ ] Có runbook rollback và quy trình xóa temporary rule.
- [ ] Định kỳ kiểm tra rule 0.0.0.0/0/::/0, unused routes và SG/NACL không còn cần thiết.

## Tài liệu tham khảo

- [What is Route 53 VPC Resolver?](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver.html)
- [Understanding Amazon DNS and VPC DNS attributes](https://docs.aws.amazon.com/vpc/latest/userguide/AmazonDNS-concepts.html)
- [View and update DNS attributes for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-dns-updating.html)
- [Resolving DNS queries between VPCs and your network](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-overview-DSN-queries-to-vpc.html)
- [How Resolver endpoints forward queries from your VPC to your network](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-overview-forward-vpc-to-network.html)
- [How DNS resolvers on your network forward queries to Resolver endpoints](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-overview-forward-network-to-vpc.html)
- [Route 53 VPC Resolver query logging](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-query-logs.html)
- [Resolver DNS Firewall](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-dns-firewall-overview.html)
- [Configure subnet route tables](https://docs.aws.amazon.com/vpc/latest/userguide/subnet-route-tables.html)
- [How route priority works](https://docs.aws.amazon.com/vpc/latest/userguide/route-tables-priority.html)
- [Enable internet access for a VPC using an internet gateway](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html)
- [Example routing options](https://docs.aws.amazon.com/vpc/latest/userguide/route-table-options.html)
- [Control traffic using security groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html)
- [Security group rules and security group referencing](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html)
- [Control subnet traffic with network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html)
- [Custom network ACLs and ephemeral ports](https://docs.aws.amazon.com/vpc/latest/userguide/custom-network-acl.html)
- [Logging IP traffic using VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html)
- [VPC Flow Logs record examples](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-records-examples.html)
- [VPC Flow Logs limitations](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-limitations.html)
- [Troubleshoot VPC reachability issues](https://docs.aws.amazon.com/vpc/latest/userguide/route-table-routes-troubleshoot.html)
- [Troubleshoot reachability using Reachability Analyzer](https://docs.aws.amazon.com/vpc/latest/userguide/reachability-analyzer.html)
- [How Reachability Analyzer works](https://docs.aws.amazon.com/vpc/latest/reachability/how-reachability-analyzer-works.html)
- [Reachability Analyzer explanation codes](https://docs.aws.amazon.com/vpc/latest/reachability/explanation-codes.html)
- [Troubleshoot VPC peering connections](https://docs.aws.amazon.com/vpc/latest/peering/troubleshoot-vpc-peering-connections.html)
- [Configure an interface VPC endpoint](https://docs.aws.amazon.com/vpc/latest/privatelink/interface-endpoints.html)
- [Monitoring your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/monitoring.html)

