# AWS Network Firewall và lọc lưu lượng VPC

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vai trò của AWS Network Firewall trong kiến trúc bảo vệ mạng của Amazon VPC.
- Phân biệt firewall, firewall policy, rule group, firewall endpoint và VPC endpoint association.
- So sánh Classic policy với Next Generation policy và chọn mô hình phù hợp.
- Giải thích luồng xử lý stateless, stateful, firewall engine và IPS engine.
- Viết quy tắc lọc theo địa chỉ IP, cổng, giao thức, trạng thái kết nối, SNI và HTTP host.
- Thiết kế route table để đưa traffic qua firewall, bảo đảm luồng đi và về đối xứng.
- Chọn mô hình triển khai distributed, centralized hoặc kết hợp trong môi trường nhiều VPC.
- Thiết kế TLS inspection, logging, monitoring và kiểm soát chi phí.
- Phối hợp Network Firewall với Security Groups, Network ACLs, Route 53 Resolver DNS Firewall, AWS WAF, Transit Gateway, Cloud WAN và AWS Firewall Manager.
- Triển khai thử nghiệm, xác minh kết quả, xử lý lỗi định tuyến và vận hành firewall trong production.

## 1. Bài toán: kiểm soát lưu lượng giữa VPC và Internet

Một ứng dụng chạy trong VPC thường trao đổi dữ liệu với nhiều đích: người dùng trên Internet, API của đối tác, dịch vụ AWS, máy chủ on-premises và workload trong các VPC khác. Security group kiểm soát kết nối ở cấp network interface, còn Network ACL lọc packet tại ranh giới subnet. Khi tổ chức cần kiểm tra sâu hơn theo giao thức, domain, dấu hiệu xâm nhập hoặc nội dung ứng dụng, hai lớp này có thể chưa đủ.

Ví dụ, một công ty muốn:

- Chỉ cho phép máy chủ production truy cập các domain bên ngoài đã phê duyệt.
- Chặn kết nối đến địa chỉ IP, cổng hoặc domain độc hại.
- Phát hiện và ngăn một số mẫu tấn công ở tầng ứng dụng.
- Kiểm tra TLS traffic theo chính sách bảo mật.
- Ghi lại traffic được cho phép hoặc bị chặn để điều tra sự cố.
- Áp dụng cùng một baseline cho nhiều VPC và tài khoản AWS.

AWS Network Firewall là dịch vụ firewall mạng được quản lý cho Amazon VPC. Dịch vụ cung cấp firewall endpoints theo Availability Zone và áp dụng firewall policy để kiểm tra lưu lượng được định tuyến qua các endpoint đó. Stateful inspection sử dụng engine tương thích Suricata, cho phép theo dõi flow và nhận diện nhiều giao thức ở tầng ứng dụng.

Network Firewall không tự động nhìn thấy toàn bộ traffic của VPC. Bạn phải cấu hình route table để đưa đúng luồng traffic qua firewall endpoint. Nếu route bỏ qua endpoint, policy không thể kiểm tra luồng đó.

Trong hệ sinh thái AWS, Network Firewall kết hợp với:

- **Amazon VPC** để xác định subnet, route table và đường đi của traffic.
- **Security Groups và Network ACLs** để kiểm soát truy cập ở cấp network interface và subnet.
- **AWS Transit Gateway hoặc AWS Cloud WAN** để tập trung traffic từ nhiều VPC.
- **Amazon Route 53 Resolver DNS Firewall** để bảo vệ đường truy vấn DNS.
- **AWS WAF** để kiểm tra HTTP requests tại các điểm kết thúc ứng dụng như CloudFront, Application Load Balancer và API Gateway.
- **AWS Firewall Manager** để quản lý policy trên nhiều tài khoản trong AWS Organizations.
- **Amazon CloudWatch, Amazon S3 và Amazon Data Firehose** để thu thập, lưu trữ và chuyển tiếp log.

## 2. Network Firewall bảo vệ ở đâu?

Network Firewall hoạt động trên đường truyền mạng được định tuyến qua firewall endpoint. Dịch vụ có thể kiểm tra traffic ở nhiều lớp:

| Lớp | Dữ liệu có thể dùng để lọc |
|---|---|
| L3 - Network | IPv4/IPv6, địa chỉ nguồn và đích |
| L4 - Transport | TCP, UDP, ICMP, port và trạng thái flow |
| L7 - Application | Protocol detection, TLS SNI, HTTP host/header và một số thuộc tính ứng dụng |
| TLS inspection | Giải mã traffic TLS trong scope đã cấu hình, kiểm tra payload rồi mã hóa lại |

Stateful engine có thể nhận diện giao thức ứng dụng ngay cả khi ứng dụng dùng port không phổ biến. Ví dụ, TLS có thể chạy trên port khác 443 và HTTP có thể chạy trên port khác 80. Khả năng nhận diện phụ thuộc protocol parser, flow context và loại traffic được hỗ trợ.

Network Firewall bảo vệ traffic đi qua endpoint. Một subnet không tự động được bảo vệ chỉ vì firewall đã tồn tại trong VPC. Cần kiểm tra route table của subnet nguồn, subnet đích và các thiết bị trung gian để xác nhận đường đi thực tế.

### Network Firewall và các lớp kiểm soát khác

| Dịch vụ | Phạm vi chính | Ví dụ |
|---|---|---|
| Security Groups | Stateful access control gắn với ENI | Chỉ cho phép app server nhận TCP/443 từ ALB |
| Network ACLs | Stateless packet filtering tại subnet | Chặn một CIDR đã biết ở ranh giới subnet |
| AWS Network Firewall | Stateful network inspection trên traffic được định tuyến qua endpoint | Lọc domain, giao thức, dấu hiệu xâm nhập |
| Route 53 Resolver DNS Firewall | Lọc truy vấn DNS qua Route 53 Resolver | Chặn phân giải domain độc hại |
| AWS WAF | HTTP/HTTPS request inspection tại điểm kết thúc web | Chặn SQL injection, bot hoặc request bất thường |
| AWS Shield | Bảo vệ trước các cuộc tấn công DDoS | Bảo vệ dịch vụ công khai |

Network Firewall không thay thế security groups. Security groups vẫn là lớp kiểm soát ở cấp tài nguyên, kể cả khi một luồng traffic không đi qua firewall endpoint.

AWS WAF cũng có mục tiêu khác. WAF hiểu cấu trúc HTTP request và áp dụng rule ở lớp ứng dụng web. Network Firewall kiểm tra traffic ở tầng mạng và transport, có thể kết hợp stateful application protocol inspection. Một kiến trúc web công khai có thể dùng cả WAF và Network Firewall.

## 3. Các thành phần của AWS Network Firewall

Một triển khai thường gồm bốn thành phần chính:

| Thành phần | Vai trò |
|---|---|
| Firewall | Gắn policy kiểm tra với VPC hoặc Transit Gateway attachment và xác định các AZ có endpoint |
| Firewall policy | Định nghĩa rule groups, thứ tự đánh giá và hành vi mặc định |
| Rule group | Tập hợp các quy tắc có thể tái sử dụng |
| Firewall endpoint | Điểm xử lý traffic trong một subnet và Availability Zone |

Một firewall sử dụng một firewall policy tại một thời điểm. Policy có thể được chia sẻ cho nhiều firewall. Rule group có thể được tham chiếu từ nhiều policy và chia sẻ qua AWS Resource Access Manager khi phù hợp.

Với firewall gắn VPC, mỗi Availability Zone cần một firewall subnet riêng để tạo endpoint. Endpoint bảo vệ các subnet khác trong VPC, nhưng không bảo vệ subnet mà endpoint đang nằm trong đó. Không đặt workload hoặc tài nguyên ứng dụng vào firewall subnet.

Mỗi subnet endpoint cần có ít nhất một địa chỉ IP khả dụng. Khi tạo firewall, chọn một subnet cho từng AZ mà bạn muốn triển khai endpoint; các VPC bổ sung dùng VPC endpoint association chỉ có thể đặt endpoint ở những AZ đã có endpoint trong VPC chính.

Ngoài endpoint chính, VPC endpoint association có thể tạo thêm endpoint để mở rộng phạm vi bảo vệ sang VPC khác hoặc thêm endpoint trong VPC. Các endpoint dùng chung policy và cấu hình của firewall gốc.

~~~mermaid
flowchart TD
    A["Workload subnet"] --> B["Route table"]
    B --> C["Firewall endpoint in AZ"]
    C --> D["Firewall policy"]
    D --> E["Rule groups"]
    E --> F["Allow / Drop / Reject / Alert"]
    F --> G["Next network hop"]
    H["CloudWatch / S3 / Firehose"] <-->|"Logs"| D
~~~

## 4. Hai loại firewall policy: Classic và Next Generation

AWS Network Firewall hiện có hai loại firewall policy. Một firewall chỉ gắn một loại policy tại một thời điểm.

| Tiêu chí | Classic policy | Next Generation policy |
|---|---|---|
| Trạng thái | Vẫn được hỗ trợ đầy đủ | Được AWS khuyến nghị cho firewall mới |
| Inspection engines | Stateless engine và stateful engine | Firewall engine và IPS engine |
| Rule groups | Stateless và stateful | Firewall và IPS |
| Mặc định của lớp access control | Phụ thuộc stateless/stateful default actions | Firewall engine Drop by default |
| Mặc định của lớp IPS | Stateful engine dùng action order hoặc strict order | IPS engine Pass by default |
| Rule ordering | Stateless theo priority; stateful theo Action Order hoặc Strict Order | Firewall section theo priority; IPS section theo action order |
| Stateless rule groups | Có | Không |
| Embedded rules | Tùy cấu hình Classic | Hỗ trợ trong từng section |
| Cách dùng | Duy trì hệ thống hiện có | Baseline mới, tách access control và threat prevention |

Next Generation policy là lựa chọn nên cân nhắc cho triển khai mới. Classic policy vẫn phù hợp khi đang vận hành hệ thống cũ hoặc có yêu cầu tương thích với rule groups hiện hữu. Không thể gắn đồng thời Classic và Next Generation policy lên cùng một firewall.

Next Generation policy yêu cầu firewall ở chế độ source-preserving. Không thể gắn policy này vào firewall chạy proxy mode hoặc no-source-preservation mode.

### 4.1 Next Generation policy

Next Generation policy tách xử lý thành hai engine:

1. **Firewall engine:** kiểm soát truy cập. Engine này Drop by default; connection chỉ được chấp nhận khi vượt qua các hook và rule cần thiết.
2. **IPS engine:** kiểm tra dấu hiệu xâm nhập bằng Suricata-compatible rules. Engine này Pass by default và chặn hoặc từ chối traffic khớp rule drop/reject.

Luồng xử lý:

~~~mermaid
flowchart TD
    A["Incoming packet / connection"] --> B["Firewall engine"]
    B --> C{"Accepted by firewall rules?"}
    C -->|No| D["Firewall default action"]
    C -->|Yes| E{"Bypass IPS?"}
    E -->|Yes| F["Forward to destination"]
    E -->|No| G["IPS engine"]
    G --> H{"Threat rule matches?"}
    H -->|Drop / Reject| I["Block or reject"]
    H -->|No match / Pass| F
~~~

Firewall section chứa rule groups hoặc embedded rules cho access control. Mỗi entry trong section có priority; số nhỏ hơn được đánh giá trước. IPS section chứa IPS rule groups hoặc embedded rules. IPS engine dùng action order: pass, drop, reject rồi alert.

Có thể bật **Monitor mode** để quan sát hành vi policy trước khi chuyển sang **Enforce mode**. Trong monitor mode, đội vận hành đánh giá những kết nối nào sẽ bị ảnh hưởng và điều chỉnh allow rules trước khi thực thi chặn traffic thật.

Next Generation policy có thể tích hợp AWS managed rule groups và Active Threat Defense. Managed rule groups giúp bổ sung threat signatures do AWS hoặc đối tác duy trì. Hãy xem mô tả, nguồn cập nhật, dung lượng và tác động trước khi thêm vào production.

### 4.2 Classic policy

Classic policy dùng hai engine theo trình tự:

1. Stateless engine kiểm tra từng packet trước.
2. Stateful engine kiểm tra packet theo ngữ cảnh của flow nếu stateless rule hoặc default action chuyển packet sang stateful engine.

Stateless engine phù hợp với rule đơn giản dựa trên IP, protocol, port và packet attributes. Stateful engine dùng Suricata-compatible rules để theo dõi flow, nhận diện protocol và kiểm tra thuộc tính ứng dụng.

Trong Classic policy, stateful rule evaluation có hai chế độ:

- **Strict order:** rule được đánh giá theo thứ tự bạn định nghĩa; rule khớp đầu tiên quyết định kết quả.
- **Action order:** engine nhóm rule theo action, thường là pass trước, sau đó drop, reject và alert. Vì pass có thể được đánh giá trước drop, thứ tự bạn viết trong file không nhất thiết là thứ tự thực thi.

Strict order giúp kiểm soát precedence rõ ràng hơn. Khi dùng Strict order, hãy thiết kế stateful default actions có chủ đích để traffic không khớp rule không bị vô tình cho qua hoặc bị chặn mà không có log.

### 4.3 Chọn policy type

- Chọn Next Generation cho firewall mới nếu không có ràng buộc tương thích.
- Giữ Classic nếu policy hiện tại đã được kiểm thử và việc chuyển đổi cần kế hoạch migration riêng.
- Không chuyển policy type chỉ bằng cách đổi một field trong cấu hình. Hai loại policy có resource type, rule group và API riêng.
- Khi migration, hãy xây policy mới, kiểm tra rule coverage, triển khai ở môi trường thử nghiệm, sau đó chuyển firewall sang policy mới theo change plan.

## 5. Rule groups và cách viết rule

Rule group là tập hợp các điều kiện nhận diện traffic và action cần thực hiện. Rule group có thể được tái sử dụng trong nhiều firewall policies.

### 5.1 Rule groups trong Classic policy

Classic policy hỗ trợ:

- **Stateless rule group:** lọc packet theo header và thuộc tính mạng.
- **Stateful rule group:** lọc flow bằng standard stateful rules, domain list hoặc Suricata-compatible rule strings.

Stateless action thường gồm Pass, Drop, Forward to stateful rule groups và custom actions. Stateless engine không có ngữ cảnh flow đầy đủ. Nếu cần application protocol detection, logging chi tiết hoặc reject, hãy dùng stateful engine.

### 5.2 Rule groups trong Next Generation policy

Next Generation policy hỗ trợ:

- **Firewall rule group:** định nghĩa access control, có thể dùng visual rule builder, text rule builder hoặc domain list.
- **IPS rule group:** định nghĩa threat detection/prevention bằng Suricata-compatible rule strings.
- **Embedded rules:** viết rule trực tiếp trong policy section, không cần tạo resource rule group riêng.

Referenced rule group phù hợp khi muốn tái sử dụng và chia sẻ giữa nhiều policy. Embedded rules phù hợp với rule chỉ có ý nghĩa trong một policy và không cần quản lý capacity cố định riêng.

### 5.3 Stateful Suricata rules

Suricata rule thường có cấu trúc:

~~~text
action protocol source source_port direction destination destination_port (options)
~~~

Một rule mẫu chặn TLS đến domain độc hại dựa trên SNI:

~~~text
drop tls $HOME_NET any -> $EXTERNAL_NET any (ssl_state:client_hello; tls.sni; content:"malware.example"; startswith; nocase; endswith; msg:"Block prohibited TLS domain"; flow:to_server; sid:2001001; rev:1;)
~~~

Ý nghĩa:

- **drop:** chặn traffic khớp rule.
- **tls:** áp dụng cho TLS protocol.
- **$HOME_NET:** mạng nội bộ được định nghĩa trong policy.
- **$EXTERNAL_NET:** mạng ngoài.
- **tls.sni:** kiểm tra Server Name Indication trong TLS Client Hello.
- **content:** chuỗi domain cần nhận diện.
- **flow:to_server:** giới hạn hướng client đến server.
- **sid:** ID duy nhất của rule trong ngữ cảnh rule set.
- **rev:** phiên bản của rule.

Đây là ví dụ minh họa. Hãy kiểm tra cú pháp Suricata được AWS Network Firewall hỗ trợ, thứ tự rule và behavior trên traffic thực tế trước khi dùng.

### 5.4 Domain list rules

Domain list rule group có thể định nghĩa allow list hoặc deny list. Một số target type phổ biến:

| Target type | Nguồn domain | Điều kiện |
|---|---|---|
| TLS_SNI | Tên miền trong TLS Client Hello | Client phải gửi SNI có thể quan sát |
| HTTP_HOST | Host trong HTTP request | Với HTTPS mã hóa, cần TLS inspection để đọc HTTP host |
| AWS_ROUTE_53_RESOLVED_DOMAIN | Domain được Route 53 Resolver phân giải | Cần traffic đi qua luồng DNS Resolver được hỗ trợ và cấu hình validation phù hợp |

Tên domain có thể là tên chính xác hoặc wildcard theo cú pháp domain list. Ví dụ **.example.com** có thể khớp example.com và các subdomains. Hãy thử cả domain gốc và subdomain để xác nhận phạm vi match.

Domain list dựa trên SNI/HTTP host không đồng nghĩa Network Firewall đã đọc được toàn bộ payload TLS. Khi không bật TLS inspection, firewall vẫn có thể nhìn thấy SNI trong Client Hello nhưng payload ứng dụng bên trong TLS vẫn được mã hóa.

### 5.5 Rule evaluation và default action

Một policy cần trả lời ba câu hỏi:

1. Rule nào được đánh giá trước?
2. Khi không có rule nào khớp thì traffic được xử lý ra sao?
3. Traffic được cho qua có cần tiếp tục đi qua IPS engine hay không?

Với Next Generation policy, firewall engine mặc định Drop. Bạn phải viết rule cho connection được phép. IPS engine kiểm tra threat rules sau khi firewall engine accept, trừ khi rule cho phép bỏ qua IPS inspection.

Với Classic policy, stateless default action có thể Forward to stateful rule groups, Pass hoặc Drop. Stateful default actions áp dụng cho packet không khớp stateful rule trong Strict order. Không nên để mặc định mơ hồ vì traffic có thể đi qua mà không được kiểm tra theo ý định.

## 6. Các biến mạng và phạm vi HOME_NET

Suricata sử dụng các biến như **HOME_NET** và **EXTERNAL_NET** để viết rule dễ đọc.

Mặc định, HOME_NET thường dựa trên CIDR của VPC chứa firewall. Trong centralized inspection architecture, traffic có thể đến từ nhiều VPC spoke. Nếu HOME_NET chỉ chứa CIDR inspection VPC, rule có thể không nhận diện đúng nguồn traffic từ các spoke.

Ví dụ, organization có:

- Inspection VPC: **10.0.0.0/16**
- Production VPC: **10.10.0.0/16**
- Development VPC: **10.20.0.0/16**

Nếu muốn kiểm tra traffic của hai VPC spoke, cần cấu hình policy variables để HOME_NET bao gồm các CIDR được bảo vệ. Hãy đặt biến ở cấp policy khi cần chia sẻ cho nhiều rule groups; tránh override HOME_NET riêng lẻ trong từng rule group vì dễ tạo behavior không nhất quán.

Đối với east-west inspection, hãy xác định rõ mạng nguồn và đích nào là nội bộ. Một rule được viết cho egress traffic có thể không khớp đúng nếu flow direction hoặc HOME_NET bị cấu hình sai.

## 7. Route table quyết định traffic có đi qua firewall hay không

Sau khi tạo firewall, bạn phải chèn firewall endpoint vào đường đi của traffic. Network Firewall không tự thay đổi route table của VPC để buộc mọi traffic đi qua endpoint.

Giả sử workload subnet đang có route:

| Destination | Target hiện tại |
|---|---|
| **10.0.0.0/16** | local |
| **0.0.0.0/0** | Internet Gateway |

Để kiểm tra egress traffic, route table của workload subnet cần gửi traffic Internet-bound tới firewall endpoint. Route table của firewall subnet sau đó chuyển traffic tới Internet Gateway hoặc NAT gateway tùy kiến trúc.

Đối với inbound inspection qua Internet Gateway, cần cập nhật cả route table edge-associated của Internet Gateway để traffic đi vào subnet workload cũng đi qua firewall endpoint. Nếu chỉ sửa chiều outbound, traffic inbound có thể đi vòng qua firewall.

### 7.1 Luồng egress qua Internet Gateway

~~~mermaid
flowchart LR
    A["EC2 in workload subnet"] --> B["Workload route table"]
    B --> C["Firewall endpoint"]
    C --> D["Firewall subnet route table"]
    D --> E["Internet Gateway"]
    E --> F["Internet"]
    F --> E
    E --> G["IGW edge route table"]
    G --> C
    C --> H["Workload subnet"]
~~~

Các bước logic:

1. Workload route table gửi **0.0.0.0/0** tới firewall endpoint trong cùng AZ.
2. Firewall endpoint xử lý policy.
3. Firewall subnet route table chuyển traffic đã được phép tới Internet Gateway.
4. Với traffic phản hồi, route table của Internet Gateway chuyển traffic về firewall endpoint.
5. Firewall endpoint gửi traffic về workload subnet.

Nếu dùng NAT Gateway cho private subnet, hãy đặt firewall trên đường đi trước NAT theo thiết kế egress phù hợp để firewall có thể nhìn thấy địa chỉ nguồn private ban đầu. Kiểm tra cả route table của workload, firewall subnet, NAT subnet và Internet Gateway.

### 7.2 Inbound inspection

Đối với traffic từ Internet vào public subnet:

1. Internet Gateway nhận traffic.
2. Edge-associated route table của Internet Gateway chuyển traffic đích đến firewall endpoint.
3. Firewall kiểm tra và cho phép hoặc chặn.
4. Firewall subnet route table chuyển traffic đến workload subnet.
5. Response traffic quay lại firewall endpoint trước khi đi ra Internet Gateway.

Không chỉ kiểm tra route table của workload subnet. Inbound routing thường cần edge-associated route table của Internet Gateway.

### 7.3 Inter-subnet và east-west traffic

Để kiểm tra traffic giữa các subnet, cần route traffic giữa các subnet qua firewall endpoint. Cần xem route table của subnet nguồn, subnet đích và đường phản hồi. Traffic trong cùng subnet không đi qua firewall endpoint theo route table thông thường.

VPC peering traffic cũng không tự động được đưa qua firewall endpoint. Khi cần inspection giữa VPCs, hãy thiết kế qua Transit Gateway hoặc một mô hình routing hỗ trợ service insertion thay vì giả định VPC peering sẽ đi qua firewall.

## 8. Symmetric routing và Availability Zone

AWS Network Firewall sử dụng stateful inspection nên cần thấy cả request và response của cùng một flow. Request và response phải đi qua cùng firewall endpoint. Nếu chiều đi qua endpoint ở AZ-A nhưng chiều về qua endpoint ở AZ-B, stateful engine có thể không có đủ flow context để kiểm tra chính xác.

Đây là asymmetric routing.

Các nguyên tắc quan trọng:

- Tạo firewall endpoint ở mỗi AZ có workload cần bảo vệ.
- Route workload trong AZ tới endpoint phù hợp trong cùng AZ.
- Bảo đảm cả chiều đi và chiều về sử dụng cùng endpoint.
- Tránh thiết kế route khiến response traffic đi vòng qua firewall.
- Khi dùng Transit Gateway với inspection VPC, bật appliance mode trên attachment của inspection VPC.
- Khi dùng native Transit Gateway Network Firewall attachment, AWS tự quản lý appliance mode cho mô hình đó.

Mỗi endpoint được triển khai theo AZ và scale độc lập. Băng thông tối đa là 100 Gbps cho traffic qua các endpoint của một firewall trong một AZ; nhiều endpoint association trong AZ đó dùng chung giới hạn. Hãy kiểm tra quota và tải thực tế khi thiết kế capacity.

### 8.1 Kiểm tra symmetric routing

Có thể dùng:

- VPC Reachability Analyzer để kiểm tra đường đi dự kiến.
- Network Firewall flow logs để đối chiếu hai hướng traffic.
- Alert rule tạm thời để xác nhận stateful engine nhìn thấy flow established.
- CloudWatch metric **StreamExceptionPolicyPackets** để theo dõi stream exception.
- VPC Flow Logs để kiểm tra ENI và subnet traffic.

Nếu chỉ thấy flow log của request mà không có response, có thể response đang đi vòng qua firewall hoặc bị security group/Network ACL chặn.

## 9. Kiến trúc triển khai: distributed, centralized và combined

AWS Network Firewall hỗ trợ nhiều mô hình triển khai. Chọn mô hình dựa trên số VPC, số tài khoản, lưu lượng, yêu cầu isolation, routing và chi phí.

### 9.1 Distributed deployment

Mỗi VPC cần inspection có firewall riêng và policy riêng hoặc policy được tái sử dụng.

Phù hợp với môi trường ít VPC, workload có yêu cầu bảo mật riêng hoặc cần giảm chi phí xử lý qua Transit Gateway.

Ưu điểm:

- Traffic được kiểm tra gần workload.
- Routing dễ hiểu trong một VPC.
- Có thể tách blast radius theo ứng dụng hoặc tài khoản.
- Không cần đưa mọi traffic qua một hub.

Đánh đổi:

- Nhiều firewall endpoints và chi phí theo giờ.
- Cần quản lý policy trên nhiều VPC.
- Việc đồng bộ rule và logging phức tạp hơn khi số VPC tăng.

### 9.2 Centralized inspection VPC với Transit Gateway

Một inspection VPC chứa Network Firewall endpoints. Nhiều spoke VPC kết nối vào Transit Gateway. Route tables của Transit Gateway chuyển traffic cần kiểm tra qua inspection VPC.

~~~mermaid
flowchart TD
    A["Spoke VPC A"] --> T["Transit Gateway"]
    B["Spoke VPC B"] --> T
    C["Spoke VPC C"] --> T
    T --> I["Inspection VPC"]
    I --> F["Network Firewall endpoints"]
    F --> T
    T --> E["Egress VPC"]
    E --> N["NAT Gateway"]
    N --> G["Internet Gateway"]
    G --> X["Internet"]
~~~

Mô hình này phù hợp khi tổ chức cần một điểm quản trị tập trung cho east-west và north-south traffic.

Khi dùng Transit Gateway với inspection VPC:

- Bật appliance mode trên attachment của inspection VPC để giữ flow đi và về qua cùng AZ.
- Dùng Transit Gateway route tables để tách spoke, inspection và egress paths.
- Route workload subnet qua TGW.
- Route traffic từ TGW tới inspection endpoint trong cùng AZ.
- Kiểm tra route quay về spoke và route ra Internet.
- Xem xét chi phí Transit Gateway data processing và cross-AZ traffic.

### 9.3 Native Transit Gateway attachment

AWS Network Firewall hỗ trợ native attachment với Transit Gateway. Khi tạo firewall gắn trực tiếp Transit Gateway, AWS tạo và quản lý hạ tầng VPC nội bộ, endpoint và attachment cần thiết. Appliance mode được bật tự động để hỗ trợ routing đối xứng.

Đây là mô hình centralized nên ưu tiên đánh giá cho thiết kế mới có Transit Gateway. Nó hỗ trợ east-west inspection và centralized internet egress khi kết hợp với egress VPC có NAT Gateway và Internet Gateway.

Lợi ích:

- Giảm phần hạ tầng inspection VPC do khách hàng tự quản lý.
- Appliance mode được quản lý tự động.
- Hỗ trợ phân bổ chi phí Network Firewall cho tài khoản phát sinh traffic theo tính năng Transit Gateway tương ứng.
- Đơn giản hóa một số cấu hình route so với inspection VPC truyền thống.

Cần xem xét yêu cầu đặc thù trước khi chọn native attachment. Một số trường hợp như cần ingress inspection tập trung, cần một số loại metrics/logs của endpoint ENI hoặc yêu cầu routing chuyên biệt có thể phù hợp với inspection VPC do khách hàng quản lý hơn.

### 9.4 AWS Cloud WAN

Nếu tổ chức đã dùng AWS Cloud WAN làm backbone mạng toàn cầu, có thể dùng service insertion để đưa traffic qua inspection VPC có Network Firewall. Mô hình này phù hợp với phân đoạn mạng đa Region và chính sách định tuyến toàn cầu.

### 9.5 Combined deployment

Có thể kết hợp centralized firewall cho traffic giữa VPCs với distributed firewall cho một số workload đặc biệt. Ví dụ, phần lớn workload đi qua hub inspection, nhưng một ứng dụng có throughput cao hoặc policy riêng dùng firewall endpoint tại VPC của nó.

Đừng mặc định centralized luôn rẻ hơn. Cần so sánh số lượng endpoint, chi phí Transit Gateway, cross-AZ traffic, lưu lượng xử lý và mức độ phức tạp vận hành.

## 10. Những traffic không đi qua Network Firewall

Một số traffic không tự động được nhìn thấy bởi Network Firewall:

| Traffic | Lý do | Kiểm soát bổ sung |
|---|---|---|
| DNS query tới VPC .2 Resolver (AmazonProvidedDNS) | DNS Resolver dùng đường xử lý riêng, không đi qua firewall endpoint | Route 53 Resolver DNS Firewall |
| Traffic giữa hai resource trong cùng subnet | Route local trong subnet không đi qua endpoint | Security Groups |
| Traffic qua VPC peering | Peering route không tự động được chèn qua firewall endpoint | Security Groups hoặc thiết kế lại qua Transit Gateway |
| Traffic qua AWS Global Accelerator | Đường đi global edge không dựa trên VPC route table theo cách firewall có thể chèn vào | AWS WAF, Security Groups và kiểm soát ở điểm kết thúc |
| Traffic có route bỏ qua endpoint | Firewall không nằm trên data path | Sửa route table và kiểm tra đường đi |

DNS là một điểm quan trọng. Network Firewall có thể kiểm tra SNI hoặc HTTP host trong connection sau khi DNS phân giải, nhưng không nhìn thấy truy vấn gửi tới AmazonProvidedDNS tại địa chỉ VPC .2. Điều này tạo ra một đường egress riêng có thể bị lợi dụng cho DNS tunneling hoặc domain generation algorithms.

Hãy triển khai Route 53 Resolver DNS Firewall trên các VPC cần kiểm soát truy vấn DNS. Kết hợp DNS Firewall với Network Firewall để bảo vệ cả DNS resolution path và connection data path.

## 11. Domain filtering và Route 53 Resolved IP validation

Domain filtering có thể dựa trên SNI trong TLS Client Hello hoặc HTTP host trong HTTP request. Khi không bật TLS inspection, firewall vẫn có thể đọc SNI nhưng không đọc được payload HTTP bên trong TLS.

Route 53 Resolved IP validation giúp kiểm tra địa chỉ đích của connection với IP mà Route 53 Resolver đã phân giải cho domain. Cơ chế này bổ sung độ tin cậy cho domain-based filtering, đặc biệt khi client tự khai báo domain khác với địa chỉ IP thực tế được resolver trả về.

Một domain-based control cần cân nhắc:

- Client có gửi SNI hay không.
- Ứng dụng có dùng QUIC/HTTP3 trên UDP hay không.
- Có dùng proxy hoặc custom DNS resolver không.
- Domain có dùng CDN và nhiều IP thay đổi không.
- DNS query có đi qua Route 53 Resolver để có resolved IP context không.
- Có cần TLS inspection để kiểm tra HTTP host hoặc URL hay không.

Domain allow list không tự động kiểm soát mọi cách một ứng dụng có thể truy cập dịch vụ. Hãy kết hợp với IP/port/protocol controls, DNS Firewall và egress architecture.

## 12. TLS inspection

TLS inspection cho phép Network Firewall kết thúc kết nối TLS từ client, giải mã traffic trong scope, áp dụng stateful rules trên payload đã giải mã, rồi mã hóa lại trước khi gửi đến server.

Luồng khái quát:

~~~mermaid
flowchart LR
    A["TLS client"] --> B["Network Firewall"]
    B --> C["Decrypt using inspection configuration"]
    C --> D["Stateful / IPS rules inspect payload"]
    D --> E["Re-encrypt"]
    E --> F["Destination server"]
~~~

Để bật TLS inspection:

1. Chuẩn bị certificate trong AWS Certificate Manager.
2. Tạo TLS inspection configuration.
3. Xác định inbound hoặc outbound scope theo protocol, source/destination IP và port.
4. Với outbound inspection, chuẩn bị CA certificate để firewall tạo certificate cho server đích.
5. Cài trust chain tương ứng trên client workloads để client tin certificate do firewall phát hành.
6. Với inbound inspection, chuẩn bị server certificates cho domain được bảo vệ.
7. Gắn TLS inspection configuration vào firewall policy mới.
8. Kiểm thử certificate validation, application compatibility, latency và logging.

TLS inspection configuration cần được tạo trước khi gắn vào policy mới. AWS cho phép thay một TLS inspection configuration đã gắn bằng configuration khác; không thể thêm configuration vào một firewall policy đã tồn tại.

### 12.1 Những giới hạn cần biết

- Hỗ trợ TLS 1.1, 1.2 và 1.3 theo điều kiện tương thích.
- TLS 1.0 và các phiên bản SSL cũ không được hỗ trợ.
- StartTLS không được hỗ trợ để giải mã.
- TLS trên UDP như QUIC không được hỗ trợ bởi TLS inspection.
- Encrypted Client Hello (ECH) hoặc trường hợp không có SNI có thể khiến kết nối bị reset.
- SNI trong Client Hello phải phù hợp với certificate phía server.
- WebSocket qua HTTP/2 không được hỗ trợ; WebSocket qua HTTP/1.1 được hỗ trợ.
- Nếu TLS đã được kết thúc tại Application Load Balancer trước firewall, firewall phía sau ALB không thể giải mã lại TLS ban đầu đã kết thúc ở ALB.
- Bật TLS inspection có thể ngắt các flow đang hoạt động nằm trong scope.
- TLS handshake và certificate revocation checking có thể làm tăng latency ban đầu.

Khi firewall giải mã traffic, stateful engine có thể áp dụng rule theo payload bên trong như HTTP headers. Với traffic nằm trong TLS inspection scope, các TLS keywords khác ngoài TLS.SNI không được dùng để match như khi traffic còn mã hóa; TLS.SNI vẫn có thể được kiểm tra. Network Firewall hỗ trợ decrypted payload inspection cho HTTP/2.

Không nên giải mã mọi traffic một cách mặc định. Hãy xác định mục tiêu kiểm soát, loại trừ workload nhạy cảm hoặc không tương thích, đánh giá quyền riêng tư và kiểm thử hiệu năng trước khi mở rộng.

## 13. Logging: Alert, Flow và TLS

Network Firewall hỗ trợ ba loại log:

| Log type | Khi phát sinh | Dùng để |
|---|---|---|
| Alert | Khi rule có action tạo alert hoặc pass rule có alert modifier khớp | Theo dõi gần thời gian thực, điều tra rule match |
| Flow | Khi flow kết thúc hoặc hết idle timeout | Phân tích volume, packet count, duration và hai chiều traffic |
| TLS | Khi bật TLS inspection và có sự kiện TLS liên quan | Điều tra SNI mismatch, certificate validation và revocation |

Alert log thường là công cụ chính để theo dõi sự kiện đang diễn ra. Flow log không phải real-time; nếu connection còn mở, chưa có flow log là hành vi bình thường.

Alert log và flow log có thể chia sẻ flow ID để correlation. Alert log có trường **alert.action** và **verdict.action**. Trường alert.action mô tả action của rule alert, còn verdict.action phản ánh verdict cuối cùng của traffic. Khi điều tra traffic có thực sự bị chặn hay không, hãy kiểm tra verdict cuối.

### 13.1 Log destinations

Mỗi log type có thể gửi đến một destination:

| Destination | Phù hợp với |
|---|---|
| CloudWatch Logs | Phân tích nhanh, Logs Insights, alarms và vận hành |
| Amazon S3 | Lưu trữ dài hạn, Athena, audit và phân tích quy mô lớn |
| Amazon Data Firehose | Streaming đến SIEM hoặc hệ thống phân tích bên ngoài |

Network Firewall cấu hình một destination cho mỗi log type. Nếu cần sao chép cùng một loại log đến nhiều nơi, có thể gửi vào CloudWatch Logs rồi dùng subscription filter hoặc pipeline khác để chuyển tiếp.

Với S3, log được gom thành file và xuất theo chu kỳ khoảng 5 phút. Một file có thể chứa nhiều flow. Nếu bật monitoring dashboard sử dụng Athena, bucket log cần ở cùng Region với firewall và prefix không nên bắt đầu bằng dấu gạch chéo.

Tách alert logs và flow logs vào log groups hoặc S3 prefixes riêng để dễ truy vấn. Bảo vệ log bằng encryption, bucket policy, retention và quyền truy cập theo vai trò.

## 14. CloudWatch metrics và cảnh báo

Network Firewall phát hành metrics trong Amazon CloudWatch. Một số metric vận hành quan trọng:

| Metric | Ý nghĩa |
|---|---|
| ReceivedPackets | Số packet được firewall nhận |
| PassedPackets | Số packet được cho phép |
| DroppedPackets | Số packet bị drop |
| RejectedPackets | Số packet bị reject |
| Bytes | Lượng dữ liệu được xử lý |
| Packets | Lưu lượng packet theo hướng hoặc engine |
| StreamExceptionPolicyPackets | Số lần stream exception policy được áp dụng |

Tên metric và dimension có thể khác nhau theo loại policy, engine, traffic direction và cấu hình inspection. Hãy xem metric catalog trong CloudWatch tại đúng Region trước khi tạo alarm.

Các cảnh báo nên xem xét:

- DroppedPackets tăng đột biến so với baseline.
- RejectedPackets tăng bất thường.
- StreamExceptionPolicyPackets tăng cùng thời điểm ứng dụng báo lỗi.
- ReceivedPackets tăng gần giới hạn throughput dự kiến.
- Alert logs xuất hiện nhiều signature có severity cao.
- TLS logs ghi nhận nhiều SNI mismatch hoặc certificate revocation failures.
- Endpoint hoặc firewall có trạng thái không ổn định.

Không nên đặt alarm chỉ dựa trên tổng số packet bị drop. Một chính sách deny-by-default có thể tạo lượng drop lớn nhưng hoàn toàn đúng thiết kế. Hãy kết hợp metric với rule identity, severity, traffic source và thay đổi gần nhất.

## 15. AWS Firewall Manager và quản trị nhiều tài khoản

AWS Firewall Manager giúp quản lý tập trung các chính sách bảo mật trên AWS Organizations. Với Network Firewall, đội security có thể xác định phạm vi tài khoản hoặc OU, triển khai policy và theo dõi mức độ tuân thủ.

Một mô hình vận hành có thể gồm:

- Security account quản lý baseline và policy.
- Network account sở hữu Transit Gateway, inspection VPC hoặc native attachment.
- Application accounts chứa spoke VPC và workload.
- Logging account lưu log tập trung.
- AWS RAM chia sẻ Transit Gateway hoặc rule group khi cần.

Khi dùng centralized inspection, hãy xác định rõ trách nhiệm:

| Vai trò | Trách nhiệm |
|---|---|
| Network platform | Transit Gateway, route tables, firewall endpoints và connectivity |
| Security engineering | Firewall policy, rule groups, threat signatures và exception |
| Application team | Tags, workload requirements, testing và allowlist request |
| SOC / Incident response | Theo dõi alert, điều tra và phản ứng sự cố |
| FinOps | Theo dõi endpoint, data processing, logging và cross-AZ cost |

AWS Firewall Manager có thể áp dụng policy theo scope của organization. Cần kiểm tra quyền service-linked role, tài khoản administrator, Region hỗ trợ và trạng thái triển khai tại member accounts.

## 16. Quy trình triển khai một firewall mới

Một triển khai có thể chia thành các bước sau:

1. Xác định traffic cần kiểm tra: egress, ingress, east-west hoặc kết hợp.
2. Chọn distributed, centralized hoặc combined architecture.
3. Chọn policy type: Next Generation cho firewall mới hoặc Classic cho hệ thống hiện hữu.
4. Chuẩn bị firewall subnet riêng ở từng AZ.
5. Tạo firewall rule groups và IPS rule groups.
6. Tạo firewall policy với default actions, mode, stream exception và HOME_NET.
7. Tạo firewall và gắn policy.
8. Lấy firewall endpoint ID theo từng AZ.
9. Cập nhật route table để đưa traffic qua endpoint.
10. Bảo đảm request/response routing đối xứng.
11. Bật alert/flow/TLS logging theo yêu cầu.
12. Kiểm tra CloudWatch metrics và tạo alarms.
13. Thử nghiệm allow, drop, reject, domain filtering và failure scenarios.
14. Mở rộng dần sang production sau khi xác nhận behavior.

### 16.1 Tạo Next Generation firewall rule group

Ví dụ tạo firewall rule group cho phép TLS tới domain thuộc example.com. Đây là minh họa cú pháp của Next Generation firewall engine; cần kiểm thử và điều chỉnh theo policy thật.

Lưu rule string vào file **firewall-rules.json**:

~~~json
{
  "RulesSource": {
    "RulesString": "accept:hook tcp:all $HOME_NET any -> $EXTERNAL_NET any (tcp.session:setup,established; app-layer-protocol:unknown|tls; sid:1;)\naccept:hook tcp:all $EXTERNAL_NET any -> $HOME_NET any (tcp.session:setup,established; app-layer-protocol:unknown|tls; sid:2;)\naccept:flow tls:<client_hello $HOME_NET any -> $EXTERNAL_NET any (tls.sni; dotprefix; content:\".example.com\"; endswith; nocase; sid:3;)\n"
  }
}
~~~

Tạo rule group:

~~~bash
aws network-firewall create-rule-group \
  --rule-group-name allow-example-https \
  --type FIREWALL \
  --capacity 100 \
  --firewall-rule-group file://firewall-rules.json \
  --region ap-southeast-1
~~~

IPS rule group có thể dùng Suricata-compatible rule string. Ví dụ chặn một SNI giả định:

~~~json
{
  "RulesSource": {
    "RulesString": "drop tls $HOME_NET any -> $EXTERNAL_NET any (ssl_state:client_hello; tls.sni; content:\"bad.example\"; startswith; nocase; endswith; msg:\"Block prohibited SNI\"; sid:2001; rev:1;)\n"
  }
}
~~~

Lưu JSON trên thành file **ips-rules.json** trước khi chạy lệnh tạo IPS rule group.

Tạo IPS rule group:

~~~bash
aws network-firewall create-rule-group \
  --rule-group-name block-known-bad-sni \
  --type IPS \
  --capacity 100 \
  --ips-rule-group file://ips-rules.json \
  --region ap-southeast-1
~~~

Capacity được cố định khi tạo rule group. Hãy chừa khoảng trống để thêm rule về sau. Một rule group đã đạt capacity không thể thêm rule vượt mức đã đặt.

### 16.2 Tạo Next Generation firewall policy

Sau khi rule groups ở trạng thái ACTIVE, lấy ARN của từng rule group và đưa vào policy definition.

Ví dụ **policy.json**:

~~~json
{
  "FirewallRuleGroupEntries": [
    {
      "Priority": 1,
      "ResourceArn": "arn:aws:network-firewall:ap-southeast-1:111122223333:firewall-rulegroup/allow-example-https"
    }
  ],
  "IpsRuleGroupEntries": [
    {
      "ResourceArn": "arn:aws:network-firewall:ap-southeast-1:111122223333:ips-rulegroup/block-known-bad-sni"
    }
  ],
  "PolicyMode": "ENFORCE",
  "FirewallDefaultAction": "DROP"
}
~~~

Tạo policy:

~~~bash
aws network-firewall create-firewall-policy-v2 \
  --firewall-policy-v2-name production-egress-policy \
  --firewall-policy-v2 file://policy.json \
  --region ap-southeast-1
~~~

Thay account ID và ARN bằng kết quả thực tế. Trong Next Generation policy, Firewall section có priority; IPS section không có priority và sử dụng action order của IPS engine.

### 16.3 Tạo firewall VPC-attached

Sau khi policy đã ACTIVE, tạo firewall với subnet dành riêng cho endpoint tại mỗi AZ:

~~~bash
aws network-firewall create-firewall \
  --firewall-name production-egress-firewall \
  --firewall-policy-arn arn:aws:network-firewall:ap-southeast-1:111122223333:firewall-policy-v2/production-egress-policy \
  --vpc-id vpc-0123456789abcdef0 \
  --subnet-mappings SubnetId=subnet-firewall-a SubnetId=subnet-firewall-b \
  --region ap-southeast-1
~~~

Lấy trạng thái và endpoint ID:

~~~bash
aws network-firewall describe-firewall \
  --firewall-arn arn:aws:network-firewall:ap-southeast-1:111122223333:firewall/production-egress-firewall \
  --region ap-southeast-1
~~~

Trong kết quả, kiểm tra trạng thái firewall và attachment theo từng Availability Zone. Chỉ cập nhật route sau khi endpoint đã sẵn sàng.

### 16.4 Cập nhật route tables

Ví dụ với egress traffic:

| Route table | Destination | Target |
|---|---|---|
| Workload subnet AZ-A | **0.0.0.0/0** | Firewall endpoint AZ-A |
| Firewall subnet AZ-A | **0.0.0.0/0** | NAT Gateway hoặc Internet Gateway theo kiến trúc |
| Workload subnet AZ-B | **0.0.0.0/0** | Firewall endpoint AZ-B |
| Firewall subnet AZ-B | **0.0.0.0/0** | NAT Gateway hoặc Internet Gateway theo kiến trúc |

Nếu cần inbound inspection, cập nhật thêm edge-associated route table của Internet Gateway để traffic đến subnet workload đi qua firewall endpoint. Đừng bỏ qua chiều response.

## 17. Bật logging bằng AWS CLI

Tạo file **logging.json** với log destination. Ví dụ gửi Alert logs đến CloudWatch Logs và Flow logs đến S3:

~~~json
{
  "LoggingConfiguration": {
    "LogDestinationConfigs": [
      {
        "LogType": "ALERT",
        "LogDestinationType": "CloudWatchLogs",
        "LogDestination": {
          "logGroup": "network-firewall-alerts"
        }
      },
      {
        "LogType": "FLOW",
        "LogDestinationType": "S3",
        "LogDestination": {
          "bucketName": "central-network-firewall-logs",
          "prefix": "production/flow"
        }
      }
    ]
  }
}
~~~

Áp dụng logging configuration:

~~~bash
aws network-firewall update-logging-configuration \
  --firewall-arn arn:aws:network-firewall:ap-southeast-1:111122223333:firewall/production-egress-firewall \
  --logging-configuration file://logging.json \
  --region ap-southeast-1
~~~

S3 bucket cần bucket policy cho log delivery service. Nếu dùng TLS inspection, có thể bật thêm TLS log type để điều tra certificate validation và SNI mismatch.

## 18. Testing và xác minh policy

Trước khi đưa policy vào production, hãy kiểm tra ít nhất các tình huống sau:

| Test | Kết quả mong đợi |
|---|---|
| Client truy cập domain được allow | Connection được chấp nhận |
| Client truy cập domain nằm trong deny list | Connection bị drop hoặc reject theo policy |
| Client truy cập port không được phép | Firewall default action xử lý đúng |
| Client dùng domain nhưng SNI không có hoặc sai | Kết quả khớp với rule và TLS inspection behavior |
| Response traffic quay về qua endpoint khác AZ | Phát hiện vấn đề asymmetric routing |
| Workload truy vấn VPC .2 DNS Resolver | DNS Firewall xử lý truy vấn; Network Firewall không thấy query đó |
| Flow đang mở chưa kết thúc | Alert logs có thể xuất hiện; flow log chỉ xuất hiện sau khi flow kết thúc |
| Firewall endpoint bị mất hoặc route sai | Xác minh behavior fail-close và khả năng phục hồi |

Trong giai đoạn đầu, có thể chạy policy ở monitor mode nếu loại policy hỗ trợ, hoặc dùng một nhóm workload canary. Đọc alert/flow logs trước khi chuyển sang enforce để giảm nguy cơ chặn nhầm traffic hợp lệ.

Không kiểm thử bằng một kết nối duy nhất rồi kết luận toàn bộ policy đúng. Cần thử nhiều protocol, port, AZ, chiều traffic, IPv4/IPv6 và các ứng dụng có hành vi kết nối đặc biệt.

## 19. Quản lý thay đổi và vòng đời rule

Firewall policy và rule groups là thành phần kiểm soát đường truyền của workload. Một thay đổi nhỏ có thể làm gián đoạn nhiều ứng dụng.

Quy trình thay đổi nên có:

1. Yêu cầu thay đổi với nguồn traffic, đích, port, protocol và business justification.
2. Owner xác nhận allowlist hoặc exception.
3. Review rule syntax và priority.
4. Kiểm tra capacity còn lại.
5. Kiểm thử trong một tài khoản hoặc VPC không production.
6. Chạy canary và xem output logs.
7. Mở rộng rollout theo nhóm VPC hoặc AZ.
8. Theo dõi metrics và lỗi ứng dụng.
9. Giữ phiên bản policy trước để rollback.

Với Next Generation policy, Firewall section dùng priority nên phải review thứ tự khi thêm rule. IPS engine dùng action order nên cần hiểu rõ pass/drop/reject/alert interactions.

Với Classic policy dùng Strict order, rule đầu tiên khớp có thể quyết định verdict. Khi thêm một pass rule rộng ở đầu, các drop rules phía sau có thể không bao giờ được đánh giá. Hãy kiểm tra rule shadowing và overlap.

## 20. Chi phí của AWS Network Firewall

Các thành phần chi phí cần theo dõi:

- Firewall endpoint hours theo Availability Zone.
- Data processing theo lượng traffic được xử lý.
- TLS inspection hoặc advanced inspection khi được bật.
- Logging destination như CloudWatch Logs, S3 và Data Firehose.
- Transit Gateway hoặc Cloud WAN data processing.
- Cross-AZ traffic khi route traffic sang endpoint ở AZ khác.
- Athena hoặc công cụ phân tích khi truy vấn log lưu ở S3.

Chiến lược tối ưu chi phí:

- Chọn số AZ phù hợp với yêu cầu HA và vị trí workload.
- Dùng centralized inspection khi nhiều VPC có chung baseline và mô hình routing phù hợp.
- Dùng distributed firewall cho workload có nhu cầu isolation hoặc throughput riêng.
- Tránh route traffic qua AZ khác nếu có thể.
- Chỉ bật flow logging trên phạm vi cần thiết; alert logs thường hữu ích hơn cho sự kiện bảo mật.
- Đặt retention và lifecycle cho log S3.
- Kiểm soát TLS inspection scope vì giải mã traffic làm tăng chi phí và latency.
- Xem xét chi phí Transit Gateway data processing khi so sánh centralized và distributed models.

Network Firewall tự động scale theo traffic. Endpoint có thể scale độc lập theo AZ; giới hạn bandwidth là 100 Gbps cho mỗi AZ theo quota hiện hành. Khi có kế hoạch tăng traffic đột biến như launch hoặc migration, hãy kiểm tra capacity, quota và liên hệ AWS Support nếu cần tư vấn.

## 21. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Firewall đã tạo nhưng traffic không bị lọc | Route table chưa trỏ tới endpoint | Kiểm tra route table nguồn, đích và edge route |
| Outbound đi được nhưng inbound không được kiểm tra | Chỉ cập nhật route chiều đi | Cập nhật edge-associated route table của IGW |
| Stateful rules không match | Asymmetric routing hoặc flow context không đầy đủ | Kiểm tra cùng endpoint/AZ ở hai chiều |
| Traffic bị drop dù có pass rule | Action order đưa pass lên trước hoặc default action không phù hợp | Kiểm tra rule order và policy default |
| Traffic không bị drop dù có drop rule | Pass rule được đánh giá trước trong Action Order | Dùng Strict order hoặc Next Generation policy |
| Domain allow list không hoạt động | SNI/HTTP host không quan sát được hoặc wildcard sai | Kiểm tra protocol, SNI, TLS inspection và rule syntax |
| HTTPS URL rule không match | Payload HTTPS vẫn mã hóa | Cấu hình TLS inspection nếu cần đọc HTTP content |
| DNS query vẫn ra ngoài | Query tới VPC .2 Resolver bypass Network Firewall | Dùng Route 53 Resolver DNS Firewall |
| Không có Flow log ngay lập tức | Connection vẫn đang mở | Chờ flow kết thúc hoặc idle timeout |
| Không có Alert log cho drop | Rule action không tạo alert hoặc logging chưa bật | Kiểm tra alert action, modifier và logging config |
| TLS connection bị reset | SNI thiếu, không khớp certificate hoặc TLS không hỗ trợ | Kiểm tra TLS logs và certificate |
| Traffic bị gián đoạn sau khi bật TLS inspection | Flow cũ bị reset khi scope mới áp dụng | Lên kế hoạch drain/reconnect và rollout theo giai đoạn |
| Một AZ có latency cao | Traffic cross-AZ hoặc asymmetric routing | Kiểm tra route theo AZ và endpoint metrics |
| Transit Gateway traffic bị drop | Chưa bật appliance mode trên inspection VPC attachment | Bật appliance mode hoặc dùng native TGW attachment |
| Endpoint không tạo được | AZ không hỗ trợ hoặc subnet không đáp ứng yêu cầu | Kiểm tra AZ, subnet và endpoint status |
| DroppedPackets tăng đột ngột | Policy update, traffic spike hoặc route sai | Correlate metrics, logs, change history và route tables |

### 21.1 Điều tra asymmetric routing

1. Lấy source IP, destination IP, port và protocol của flow.
2. Kiểm tra route table của subnet nguồn.
3. Kiểm tra route table của firewall subnet.
4. Kiểm tra route table của subnet đích hoặc Internet Gateway.
5. So sánh AZ của endpoint cho request và response.
6. Với Transit Gateway, kiểm tra appliance mode và TGW route tables.
7. Dùng flow logs để tìm hai hướng traffic cùng flow.
8. Kiểm tra security group và Network ACL nếu chỉ thiếu response traffic.
9. Sửa route và kiểm thử lại bằng một connection mới.

### 21.2 Điều tra policy không chặn traffic

1. Xác nhận traffic thực sự đi qua endpoint.
2. Kiểm tra policy type và section chứa rule.
3. Kiểm tra rule group đã được attach vào policy.
4. Kiểm tra thứ tự rule hoặc priority.
5. Kiểm tra default action.
6. Kiểm tra HOME_NET và EXTERNAL_NET.
7. Kiểm tra flow direction, protocol và port.
8. Kiểm tra log có rule match hay không.
9. Thử lại bằng một flow mới để tránh state cũ.

## 22. Best practices

### Thiết kế kiến trúc

- Xác định rõ traffic ingress, egress và east-west cần kiểm tra.
- Chọn centralized hoặc distributed theo số VPC, throughput và isolation.
- Đánh giá native Transit Gateway attachment cho centralized deployment mới.
- Triển khai endpoint tại mỗi AZ có workload.
- Duy trì symmetric routing.
- Đặt firewall endpoint trong dedicated subnet.
- Không giả định mọi traffic trong VPC đều đi qua firewall.

### Thiết kế policy và rule

- Ưu tiên Next Generation policy cho firewall mới.
- Dùng Monitor mode trước khi Enforce khi có thể.
- Tách access control và IPS responsibilities.
- Đặt rule group priority rõ ràng.
- Dùng strict order với Classic policy.
- Quản lý HOME_NET cho centralized inspection.
- Chừa capacity khi tạo rule group.
- Test domain list với SNI, HTTP host, subdomains và các ứng dụng thực tế.
- Dùng managed rule groups có kiểm soát và theo dõi cập nhật.

### TLS inspection và DNS

- Chỉ giải mã traffic nằm trong scope cần kiểm tra.
- Quản lý certificate và trust chain qua ACM.
- Kiểm thử ứng dụng với TLS version, SNI và cipher suites.
- Đánh giá QUIC, ECH và StartTLS limitations.
- Dùng Route 53 Resolver DNS Firewall cho truy vấn DNS tới VPC Resolver.
- Không dùng domain allow list như lớp kiểm soát duy nhất.

### Monitoring và vận hành

- Bật Alert logs cho sự kiện bảo mật cần theo dõi.
- Dùng Flow logs cho phân tích traffic sau khi flow kết thúc.
- Bật TLS logs khi dùng TLS inspection.
- Correlate alert/flow bằng flow ID và verdict cuối.
- Theo dõi DroppedPackets, RejectedPackets và StreamExceptionPolicyPackets.
- Lưu log dài hạn ở S3 với lifecycle.
- Tạo dashboard và alarms theo baseline.
- Duy trì runbook xử lý asymmetric routing và policy misconfiguration.

### Governance và bảo mật

- Quản lý policy bằng version control và change review.
- Dùng Firewall Manager để áp dụng baseline trên nhiều tài khoản.
- Chia sẻ rule groups bằng RAM khi cần.
- Giới hạn quyền sửa firewall, policy, rule groups và route tables.
- Dùng KMS customer managed key khi có yêu cầu quản trị khóa; không thu hồi quyền hoặc xóa key đang bảo vệ tài nguyên.
- Có quy trình exception với owner và thời hạn.
- Đánh giá chi phí endpoint, traffic processing, TGW và logging định kỳ.

## 23. Giới hạn và quota cần theo dõi

Quota có thể thay đổi theo Region và thời điểm. Hãy kiểm tra Service Quotas và tài liệu AWS trước rollout lớn.

| Hạng mục | Giá trị mặc định được tài liệu công bố |
|---|---:|
| Firewalls trên mỗi account/Region | 5, có thể yêu cầu tăng |
| Firewall policies trên mỗi account/Region | 20 cho từng policy family |
| Rule groups trên mỗi account/Region | 50 cho mỗi loại tương ứng |
| Rule groups trong một Classic policy | Tối đa 20 stateful và 20 stateless |
| VPC endpoint associations trên mỗi account/Region | 300, có thể yêu cầu tăng |
| VPC endpoint associations cho một firewall/AZ | 50 |
| Stateful rule group capacity | Tối đa 30.000 |
| Stateless rule group capacity | Tối đa 30.000 |
| Stateful rules trong Classic policy | 30.000 mặc định, có thể tăng theo quota |
| Bandwidth qua endpoint trong một AZ | 100 Gbps |
| TLS inspection configurations trên mỗi account/Region | 20 |
| TLS inspection configurations trong một policy | 1 |

Next Generation policy có quota riêng cho Firewall engine và IPS engine. Capacity của rule groups được cố định khi tạo; hãy chừa dư địa cho thay đổi tương lai. Quota có thể khác giữa Classic và Next Generation policy.

## 24. Bài tập tự luyện

1. AWS Network Firewall khác Security Groups ở phạm vi kiểm tra nào?
2. Vì sao tạo firewall trong VPC chưa đủ để traffic được kiểm tra?
3. Một firewall endpoint có thể bảo vệ subnet mà chính nó đang nằm trong đó không?
4. Vì sao cần endpoint ở mỗi AZ có workload?
5. Phân biệt Classic policy và Next Generation policy.
6. Next Generation firewall engine và IPS engine có default behavior khác nhau như thế nào?
7. Classic stateful Action Order có thể khiến pass rule ảnh hưởng drop rule ra sao?
8. Vì sao Strict order thường dễ kiểm soát hơn?
9. Stateless default action Forward to stateful có ý nghĩa gì?
10. Rule group capacity có thể tăng sau khi tạo không?
11. Vì sao cần cấu hình HOME_NET khi dùng centralized inspection?
12. Domain list dựa trên TLS_SNI có đọc được HTTP payload đã mã hóa không?
13. Khi nào cần TLS inspection để lọc HTTPS theo HTTP host?
14. Vì sao Network Firewall không thấy DNS query gửi tới VPC .2 Resolver?
15. Route 53 Resolver DNS Firewall bổ sung lớp bảo vệ nào?
16. Vì sao request và response phải qua cùng firewall endpoint?
17. Transit Gateway appliance mode giúp giải quyết vấn đề gì?
18. Khi nào nên chọn native Transit Gateway attachment?
19. Alert log và Flow log khác nhau về thời điểm xuất hiện như thế nào?
20. Một alert log có alert.action=allowed nhưng verdict.action=drop. Traffic cuối cùng được xử lý ra sao?
21. Vì sao TLS logs không xuất hiện nếu không bật TLS inspection?
22. TLS inspection có hỗ trợ QUIC không?
23. AWS WAF và Network Firewall có thể dùng cùng nhau trong kiến trúc nào?
24. Vì sao không nên chỉ dựa vào DroppedPackets để xác định sự cố?
25. Khi nào nên dùng AWS Firewall Manager?

### Gợi ý đáp án

1. Security Groups kiểm soát truy cập ở ENI; Network Firewall kiểm tra traffic được route qua endpoint, có thể inspect stateful và application protocols.
2. Vì route table phải đưa traffic qua firewall endpoint.
3. Không. Firewall endpoint không bảo vệ subnet chứa chính endpoint đó.
4. Để giảm cross-AZ routing, hỗ trợ HA và giữ flow đối xứng.
5. Classic dùng stateless/stateful engines; Next Generation tách firewall access control và IPS engines.
6. Firewall engine Drop by default; IPS engine Pass by default.
7. Action Order đánh giá pass trước drop nên pass rule có thể được áp dụng trước dù viết sau trong rule set.
8. Strict order đánh giá theo thứ tự ưu tiên do người quản trị định nghĩa.
9. Packet không match stateless rule sẽ được chuyển sang stateful engine để kiểm tra theo flow.
10. Không. Capacity được cố định khi tạo.
11. Vì traffic đến từ nhiều VPC spoke có thể nằm ngoài CIDR inspection VPC mặc định.
12. Không. SNI có thể quan sát trong Client Hello; payload HTTP bên trong TLS vẫn mã hóa nếu không TLS inspection.
13. Khi cần đọc HTTP host hoặc URL bên trong HTTPS đã giải mã.
14. Vì truy vấn dùng đường xử lý riêng của AmazonProvidedDNS.
15. Lọc DNS queries trước khi client thiết lập connection.
16. Stateful engine cần flow context hai chiều để kiểm tra application protocol.
17. Giữ request và response qua cùng appliance/endpoint AZ.
18. Khi cần centralized inspection mới và muốn AWS quản lý hạ tầng attachment.
19. Alert log gần real-time khi rule match; Flow log xuất khi flow kết thúc hoặc timeout.
20. Verdict cuối là drop; alert.action chỉ mô tả action của rule alert.
21. TLS logs chỉ phát sinh cho sự kiện liên quan TLS inspection.
22. Không. TLS inspection không hỗ trợ UDP-based QUIC.
23. WAF bảo vệ HTTP requests tại ALB/CloudFront/API Gateway; Network Firewall kiểm tra traffic ở tầng mạng trên đường đi tới workload.
24. Vì drop có thể là behavior bình thường của deny-by-default; cần correlate với rule, flow, severity và change history.
25. Khi cần quản trị policy bảo mật trên nhiều tài khoản và OU trong AWS Organizations.

## 25. Câu hỏi phỏng vấn

### AWS Network Firewall là gì?

AWS Network Firewall là dịch vụ firewall được quản lý cho Amazon VPC. Dịch vụ cung cấp firewall endpoints theo AZ và dùng firewall policy để kiểm tra traffic được route qua endpoint.

### Network Firewall có tự động lọc mọi traffic trong VPC không?

Không. Bạn phải cập nhật route tables để đưa các luồng cần kiểm tra qua firewall endpoint. Traffic không đi qua endpoint sẽ không được policy kiểm tra.

### Khi nào nên dùng Next Generation policy?

Khi triển khai firewall mới và muốn tách access control khỏi IPS inspection. Next Generation policy có firewall engine Drop by default và IPS engine Pass by default, giúp tách rõ hai nhiệm vụ.

### Vì sao Network Firewall cần symmetric routing?

Stateful engine theo dõi flow và cần nhìn thấy cả request lẫn response. Nếu hai chiều đi qua endpoint khác nhau, application layer inspection có thể không hoạt động đúng.

### Firewall endpoint có thể đặt cùng subnet với workload không?

Không nên. Firewall endpoint nằm trong dedicated subnet và endpoint không bảo vệ subnet mà nó đang ở trong đó.

### Network Firewall có thay thế Route 53 Resolver DNS Firewall không?

Không. Query tới AmazonProvidedDNS trong VPC đi qua đường riêng và không được Network Firewall nhìn thấy. DNS Firewall bảo vệ đường truy vấn DNS này.

### Khi nào cần TLS inspection?

Khi chính sách cần kiểm tra payload HTTPS sau khi giải mã, chẳng hạn HTTP host/header hoặc nội dung ứng dụng. Nếu chỉ cần lọc theo SNI, có thể không cần giải mã toàn bộ TLS traffic.

### Vì sao nên tách Alert và Flow logs?

Alert logs hỗ trợ giám sát sự kiện rule match gần thời gian thực. Flow logs hỗ trợ phân tích traffic volume và connection state sau khi flow kết thúc.

### Khi nào dùng centralized inspection?

Khi nhiều VPC hoặc tài khoản cần dùng chung baseline và tổ chức muốn quản lý policy tập trung. Transit Gateway hoặc Cloud WAN có thể làm hub định tuyến.

### Network Firewall khác AWS WAF thế nào?

Network Firewall kiểm tra traffic mạng được route qua endpoint. AWS WAF kiểm tra HTTP/HTTPS requests tại các dịch vụ web được hỗ trợ. Hai dịch vụ có thể bổ sung cho nhau.

## 26. Checklist trước khi đưa vào production

### Architecture và routing

- [ ] Traffic ingress, egress và east-west đã được xác định.
- [ ] Mô hình distributed/centralized/combined đã được review.
- [ ] Firewall endpoint nằm trong dedicated subnet.
- [ ] Có endpoint ở các AZ cần bảo vệ.
- [ ] Route table của workload subnet đã trỏ đúng endpoint.
- [ ] Route table của firewall subnet đã trỏ đúng next hop.
- [ ] Inbound path đã được kiểm tra qua IGW edge route table nếu cần.
- [ ] Request và response đi qua cùng endpoint.
- [ ] Transit Gateway appliance mode hoặc native attachment được cấu hình đúng.
- [ ] Traffic bypass đã được ghi nhận và có lớp kiểm soát bổ sung.

### Policy và rules

- [ ] Policy type phù hợp với yêu cầu và khả năng tương thích.
- [ ] Default actions đã được review.
- [ ] Rule group priority và evaluation order rõ ràng.
- [ ] HOME_NET bao gồm tất cả mạng cần bảo vệ.
- [ ] Domain rules được kiểm tra với SNI, HTTP host và subdomains.
- [ ] Rule group capacity có khoảng trống tăng trưởng.
- [ ] Managed rule groups được đánh giá tác động.
- [ ] Monitor/canary test thành công trước enforce rollout.

### TLS và logging

- [ ] TLS inspection scope được giới hạn.
- [ ] ACM certificates và trust chain được chuẩn bị.
- [ ] Ứng dụng tương thích với TLS inspection limitations.
- [ ] Alert, Flow và TLS logs được bật theo nhu cầu.
- [ ] Log destination có IAM/bucket policy phù hợp.
- [ ] CloudWatch alarms và dashboards được tạo.
- [ ] S3 retention/lifecycle và encryption được cấu hình.

### Governance và recovery

- [ ] Policy/rule được lưu trong version control.
- [ ] Có owner và approval cho exception.
- [ ] AWS Firewall Manager được cân nhắc cho multi-account governance.
- [ ] Có runbook xử lý asymmetric routing và false positive.
- [ ] Có rollback plan cho policy và route changes.
- [ ] Quota, throughput và chi phí được kiểm tra.
- [ ] Có lịch review rule groups và managed signatures.

## 27. Tài liệu tham khảo chính thức

- [What is AWS Network Firewall?](https://docs.aws.amazon.com/network-firewall/latest/developerguide/what-is-aws-network-firewall.html)
- [Firewall components in AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-components.html)
- [AWS Network Firewall firewall policy versions](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-policy-versions.html)
- [Next Generation policies in AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-policies-v2.html)
- [How Network Firewall filters traffic with a Next Generation policy](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-policy-processing-v2.html)
- [Creating a Next Generation policy](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-policy-v2-creating.html)
- [Rule groups for Next Generation policies](https://docs.aws.amazon.com/network-firewall/latest/developerguide/rule-groups-v2.html)
- [Managing your own rule groups](https://docs.aws.amazon.com/network-firewall/latest/developerguide/rule-groups.html)
- [How AWS Network Firewall filters network traffic](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-policy-processing.html)
- [Managing evaluation order for Suricata compatible rules](https://docs.aws.amazon.com/network-firewall/latest/developerguide/suricata-rule-evaluation-order.html)
- [Examples of stateful rules for Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/suricata-examples.html)
- [VPC route table configuration for AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/vpc-config-route-tables.html)
- [VPC subnet configuration for AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/vpc-config-subnets.html)
- [Creating a firewall in AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/creating-firewall.html)
- [AWS Network Firewall no-source-preservation mode](https://docs.aws.amazon.com/network-firewall/latest/developerguide/no-source-preservation-mode.html)
- [Troubleshooting general issues](https://docs.aws.amazon.com/network-firewall/latest/developerguide/troubleshooting-general-issues.html)
- [Inspecting SSL/TLS traffic with TLS inspection configurations](https://docs.aws.amazon.com/network-firewall/latest/developerguide/tls-inspection-configurations.html)
- [Considerations for TLS inspection](https://docs.aws.amazon.com/network-firewall/latest/developerguide/tls-inspection-considerations.html)
- [Using SSL/TLS certificates with TLS inspection configurations](https://docs.aws.amazon.com/network-firewall/latest/developerguide/tls-inspection-certificate-requirements.html)
- [Contents of a Network Firewall log](https://docs.aws.amazon.com/network-firewall/latest/developerguide/firewall-logging-contents.html)
- [Sending Network Firewall logs to Amazon S3](https://docs.aws.amazon.com/network-firewall/latest/developerguide/logging-s3.html)
- [AWS Network Firewall quotas](https://docs.aws.amazon.com/network-firewall/latest/developerguide/quotas.html)
- [AWS Security Services Best Practices - Network Firewall](https://aws.github.io/aws-security-services-best-practices/guides/network-firewall/)


