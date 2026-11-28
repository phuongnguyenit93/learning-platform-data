# Cloud firewall và managed network control

**Cloud firewall** là nhóm cơ chế kiểm soát lưu lượng mạng trong hạ tầng đám mây, thường dựa trên nguồn, đích, giao thức, cổng, vùng mạng, danh tính workload và trong một số trường hợp cả nội dung hoặc đặc điểm ứng dụng. **Managed network control** là những kiểm soát mạng được nhà cung cấp cloud quản lý một phần hoặc toàn bộ về hạ tầng vận hành, ví dụ firewall phân tán theo workload, network ACL, dịch vụ firewall tập trung, DNS filtering, WAF, chống DDoS, quản lý kết nối riêng và công cụ phân tích đường đi.

Khác với một firewall vật lý đứng tại cửa Internet của trung tâm dữ liệu, mạng cloud có nhiều đường kết nối đồng thời: từ Internet vào load balancer, giữa các máy ảo trong cùng VPC/VNet, giữa các dự án/tài khoản, từ workload tới dịch vụ quản lý của cloud, hoặc qua VPN, private link và kết nối hybrid. Một chính sách chỉ kiểm soát **Internet ingress** có thể không bao phủ **east–west traffic** hoặc **egress**. Ngược lại, một workload ở private subnet vẫn có thể gửi dữ liệu ra ngoài theo đường NAT, proxy hoặc endpoint nếu chính sách cho phép.

Trong chương **Bảo mật mạng cloud** của module **SECURITY_NETWORK_SECURITY**, cloud firewall là một lớp trong kiến trúc phòng vệ nhiều tầng, kết hợp với **phân đoạn mạng, VPN, TLS, kiểm soát DNS, IDS/IPS, IAM, API authorization, giám sát và quản trị cấu hình**. Bài học tập trung cách xác định điểm thực thi thực sự của từng policy, lựa chọn managed controls phù hợp và chứng minh bằng kiểm thử rằng lưu lượng được phép đi đúng đường còn lưu lượng trái chính sách bị chặn.

> **Nguyên tắc cốt lõi:** **Có route không có nghĩa được phép truy cập; bị chặn route không thay thế chính sách bảo mật; có kết nối private không tự đồng nghĩa có quyền dữ liệu.** Phải xác minh đồng thời đường đi, bộ lọc lưu lượng, danh tính và quyền ở hệ thống đích.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **security group/instance firewall, subnet network ACL, cloud network firewall, NGFW, WAF, DNS firewall** và chống DDoS theo tầng và phạm vi áp dụng.
2. Giải thích **shared responsibility** đối với cấu hình policy cloud, vận hành dịch vụ managed và cập nhật workload.
3. Phân tích **ingress, egress, east–west, north–south** và lưu lượng hybrid trong VPC/VNet.
4. Phân biệt **stateful** và **stateless filtering**, connection tracking, chiều trả lời và thứ tự xét rule tùy nhà cung cấp.
5. Thiết kế **default deny, least privilege**, phân đoạn application/data/management, hạn chế egress và kiểm soát dịch vụ cloud nội bộ.
6. Hiểu vì sao **route table, NAT, Internet gateway, private endpoint, peering và transit hub** không tự thay firewall hoặc IAM.
7. Xác định điểm triển khai **managed NGFW/IDS/IPS/TLS inspection** trên những luồng thực sự đi qua nó và rủi ro bất đối xứng định tuyến.
8. Bảo vệ **Kubernetes, autoscaling workloads, serverless, API gateway** bằng controls phù hợp mức trừu tượng.
9. Xây dựng **IaC/policy-as-code, kiểm soát drift, vòng đời ngoại lệ và thay đổi có phê duyệt**.
10. Thiết kế **flow logs, firewall logs, DNS logs và cảnh báo**, kiểm thử cả allow/deny, điều tra sai rule không gây gián đoạn diện rộng.

## 2. Shared responsibility: nhà cung cấp quản lý gì, khách hàng chịu trách nhiệm gì?

Cloud managed services giúp giảm nhu cầu vận hành thiết bị vật lý, nhưng **không đồng nghĩa nhà cung cấp tự thiết kế policy đúng nghiệp vụ**. Phân chia trách nhiệm còn phụ thuộc loại dịch vụ và hợp đồng.

| Nội dung | Nhà cung cấp cloud thường quản lý | Tổ chức sử dụng cloud thường chịu trách nhiệm |
| --- | --- | --- |
| Hạ tầng vật lý, mạng lõi dịch vụ | Trung tâm dữ liệu, phần cứng và lớp cung cấp dịch vụ | Đánh giá cam kết dịch vụ và yêu cầu tuân thủ |
| Distributed firewall service | Nền tảng thực thi, API và độ sẵn sàng theo sản phẩm | Chọn nguồn/đích, protocol, rule, đối tượng áp dụng |
| Managed network firewall | Control/data plane theo phạm vi dịch vụ cung cấp | Policy, routing steering, HA, bảo vệ luồng bypass |
| VPC/VNet, subnet, route | Cung cấp cơ chế mạng ảo | Thiết kế CIDR, định tuyến, kết nối và phân đoạn |
| TLS endpoints/chứng thư | Có thể cung cấp dịch vụ cấp phát/quản lý | Đặt đúng tên, trust, renewal và backend validation |
| IAM | Cung cấp hệ thống định danh/quyền | Least privilege, phân tách vai trò, MFA, khóa truy cập |
| Logs/monitoring | Công cụ thu thập và lưu trữ theo khả năng sản phẩm | Bật đúng nguồn, retention, bảo vệ log, điều tra |
| Workloads do khách hàng vận hành | Tùy mô hình IaaS/PaaS/SaaS | Cập nhật ứng dụng, host, container, secret và quyền dữ liệu |

### 2.1. IaaS, PaaS và SaaS có mặt phẳng kiểm soát khác nhau

- **IaaS VM:** tổ chức thường kiểm soát VPC/VNet, security groups/NSGs, route tables, host firewall và hệ điều hành máy.
- **Managed container/Kubernetes:** cần xét đồng thời mạng cloud, CNI, NetworkPolicy, ingress, service identity và control plane.
- **PaaS database hoặc object storage:** có thể dùng private endpoint, resource policy, service firewall, IAM và mã hóa; người dùng không luôn quản lý được firewall bên trong dịch vụ.
- **SaaS:** đa phần không cho chỉnh network firewall của nhà cung cấp; kiểm soát theo tenant, conditional access, identity, DLP và cấu hình dịch vụ có sẵn.

**Không dùng một checklist VM cho tất cả cloud services**. Điểm có thể thiết lập firewall và cách chứng minh chính sách đang hoạt động thay đổi theo sản phẩm.

## 3. Mô hình luồng traffic của mạng cloud

Một kiến trúc cloud phải quan sát ít nhất bốn hướng:

| Luồng | Ví dụ | Rủi ro điển hình | Kiểm soát gợi ý |
| --- | --- | --- | --- |
| **North–south ingress** | Internet → public load balancer → API | Exposed backend, scanning, HTTP abuse | DDoS protection, WAF, edge policy, workload firewall |
| **North–south egress** | VM → NAT/Internet → dịch vụ ngoài | Data exfiltration, truy cập C2, tải package độc hại | Egress allowlist, DNS control, firewall/proxy, telemetry |
| **East–west** | App VM → DB VM; pod → pod | Lateral movement, cross-tenant access | Security group, microsegmentation, K8s NetworkPolicy, workload auth |
| **Hybrid/cross-network** | On-prem → VPN/leased line → cloud | Quá rộng CIDR, route leak, trust zone bị trộn | Network firewall, route policy, segmentation, identity |

### 3.1. Ví dụ kiến trúc đa lớp

~~~mermaid
flowchart TB
    INTERNET["Internet / untrusted"] -->|"HTTPS 443"| EDGE["Cloud DDoS protection / WAF / Public LB"]
    EDGE -->|"Chỉ backend port được duyệt"| APP["Private Application subnet"]
    APP -->|"Chỉ TCP 5432 từ app identity"| DB[("Private Data subnet")]
    APP -->|"Egress theo policy"| EFW["Managed Egress Firewall / Proxy"]
    EFW --> NAT["NAT / Public Egress"]
    NAT --> INTERNET
    APP -->|"Private endpoint + IAM"| PAA["Managed cloud service"]
    ONPREM["On-prem / branch"] -->|"VPN / private circuit"| HUB["Transit hub / routing controls"]
    HUB -->|"Kiểm soát luồng hybrid"| APP
    MGMT["Management / Bastion / PAM"] -->|"Truy cập quản trị được duyệt"| APP
    EDGE -. "Access and WAF logs" .-> SOC["SOC / SIEM"]
    EFW -. "Flow/alert logs" .-> SOC
    APP -. "Workload/app logs" .-> SOC
~~~

Sơ đồ thể hiện **vai trò logic**, không phải bắt buộc tất cả luồng sử dụng một appliance hay đi qua cùng một route. **Cần kiểm tra chính xác đường đi** để biết firewall tập trung có thực sự nhìn thấy lưu lượng giữa hai tài nguyên hay không.

### 3.2. Trust zones theo dữ liệu, không chỉ theo CIDR

Một VPC có thể chứa ứng dụng public, job nội bộ, cơ sở dữ liệu và hệ thống quản trị. **Chung VPC không đồng nghĩa chung mức tin cậy**. Nên phân vùng dựa trên chức năng/dữ liệu:

1. **Edge/DMZ:** nơi tiếp nhận kết nối công khai.
2. **Application:** services phục vụ nghiệp vụ.
3. **Data:** database, storage và backend nhạy cảm.
4. **Management:** bastion, administration endpoints, automation.
5. **Security/shared services:** DNS resolver, PKI, log collectors, egress proxy.
6. **Partner/hybrid:** nguồn từ tổ chức khác hoặc on-prem kết nối cloud.

Nên lập **ma trận luồng hợp lệ** giữa các zone, rồi ánh xạ vào các controls và điểm thực thi được cloud hỗ trợ.

## 4. Những tầng firewall và managed network control

| Kiểm soát | Tầng/điểm tác động phổ biến | Điểm mạnh | Không tự thay thế |
| --- | --- | --- | --- |
| **Security group / workload firewall rule** | Gắn NIC/VM/instance hoặc đối tượng dịch vụ theo sản phẩm | Lọc phân tán theo nguồn/đích/cổng và workload | WAF, phân quyền bản ghi, tất cả egress ngoài đường |
| **Subnet network ACL** | Ranh giới subnet hoặc tài nguyên mạng theo nền tảng | Rào chắn bổ sung, có thể hỗ trợ allow/deny có thứ tự | Identity/role của người dùng, nội dung HTTP |
| **Managed network firewall / NGFW** | Điểm mạng được route/steer qua | Policy tập trung, stateful filtering, IPS, domain/app controls nếu hỗ trợ | Bảo vệ các luồng không được chuyển qua nó |
| **WAF** | HTTP(S) qua CDN/LB/API gateway/proxy | Kiểm tra một số mẫu HTTP độc hại, rule theo ứng dụng | Lọc mọi TCP/UDP, object-level authorization |
| **DNS firewall / resolver policy** | Truy vấn DNS của workload dùng resolver được quản lý | Giới hạn một số tên miền/nhóm domain | Lọc IP direct, DoH không kiểm soát, IAM |
| **Cloud DDoS protection** | Edge/network service theo sản phẩm | Hấp thụ/giảm một số luồng quá tải | Mọi lỗ hổng ứng dụng và truy cập nội bộ |
| **Kubernetes NetworkPolicy / microsegmentation** | Pod/workload hoặc overlay/CNI | Hạn chế east–west linh hoạt | Cloud firewall, TLS identity, quyền API |
| **Private endpoint / service endpoint** | Kết nối tới managed services theo kiểu sản phẩm | Giảm đường đi công khai và kiểm soát điểm kết nối | IAM/resource policy, kiểm soát mọi hoạt động dữ liệu |
| **Route table, NAT, gateway** | Đường chuyển tiếp và dịch địa chỉ | Kết nối các mạng và điều hướng qua điểm kiểm tra | Bản thân không phải quyết định cấp quyền ứng dụng |

**Các tên là loại chức năng, không phải khẳng định mọi nhà cung cấp đều triển khai như nhau.** Nhiều sản phẩm kết hợp nhiều lớp hoặc có khả năng gắn vào đối tượng khác nhau.

### 4.1. Ví dụ khái niệm giữa các nền tảng

- Trên **AWS**, các khái niệm thường gặp là **Security Groups**, **Network ACLs**, **AWS Network Firewall**, WAF và dịch vụ bảo vệ DDoS.
- Trên **Azure**, những cơ chế thường gặp là **Network Security Groups**, **Azure Firewall**, WAF tại edge/application gateway và DDoS protection.
- Trên **Google Cloud**, thường có **VPC firewall rules/firewall policies**, các dịch vụ **Cloud NGFW**, WAF/DDoS ở edge và chính sách mạng cho workload.

Tên sản phẩm và giới hạn tính năng có thể thay đổi; **không chuyển trực tiếp thứ tự rule hoặc ngữ nghĩa statefulness từ cloud này sang cloud khác**. Khi triển khai phải đọc tài liệu đúng phiên bản dịch vụ, xét loại endpoint và cơ chế enforcement.

## 5. Stateful và stateless filtering

### 5.1. Stateful firewall

**Stateful filtering** duy trì thông tin về kết nối đã được chấp nhận để xử lý các gói tin liên quan, thường cho phép traffic phản hồi theo trạng thái mà không phải viết mirror rule inbound/outbound cho từng bước. Nhưng trạng thái được tracking và định nghĩa thế nào **phụ thuộc giao thức, sản phẩm và giới hạn connection tracking**.

Ví dụ: một workload được phép khởi tạo TCP tới API ở cổng 443; firewall stateful thường nhận diện traffic trả lời của kết nối đó. Điều này **không có nghĩa API có quyền mở bất kỳ kết nối mới nào tới workload**.

### 5.2. Stateless network ACL

**Stateless filtering** đánh giá gói tin theo rule mà không dựa trên state của kết nối như một stateful firewall. Nếu muốn client kết nối TCP 443 tới server qua một điểm stateless, có thể phải cho traffic request **và chiều phản hồi theo port tương ứng**, tùy thiết kế.

Ví dụ trong sản phẩm có subnet NACL stateless, cần xét chiều outbound trả về **ephemeral client ports**, không chỉ inbound destination 443. Dải ephemeral ports **khác nhau theo hệ điều hành, dịch vụ và môi trường**, không suy đoán một dải chung cho mọi hệ thống.

### 5.3. So sánh

| Thuộc tính | Stateful | Stateless |
| --- | --- | --- |
| Biết trạng thái phiên | Có, theo khả năng sản phẩm | Không hoặc không theo mô hình connection tracking |
| Traffic phản hồi | Có thể tự nhận diện luồng trả lời | Thường cần rule chiều ngược phù hợp |
| Phụ thuộc rule order | Tùy engine và policy | Nhiều sản phẩm dùng thứ tự/priority tường minh |
| Vị trí phù hợp | Workload security, firewall dịch vụ | Một số subnet ACL, gói cơ bản |
| Lưu ý bảo mật | State table, asymmetric route, timeout | Ephemeral ports, hai chiều, priority/deny logic |

**Không mặc định “stateful = không cần egress policy”**. Dù return traffic được theo dõi, việc **khởi tạo kết nối outbound** vẫn cần policy phù hợp với yêu cầu kiểm soát egress.

### 5.4. Ví dụ sai và đúng

**Sai:** cho TCP 443 inbound vào một web server, rồi tin rằng mọi kết nối ngược từ server tới Internet sẽ tự được phép vì firewall stateful.

**Đúng:** phân biệt kết nối inbound được phép và **kết nối outbound mới do server khởi tạo**. Egress rule riêng vẫn có ý nghĩa cho cập nhật, gọi API ngoài hoặc cấm kết nối không cần thiết.

## 6. Rule evaluation, default behavior và priority

Khi thiết kế, phải trả lời:

- Rule có **allow và deny** rõ ràng hay chỉ có allow?
- Quy tắc mặc định khi **không có rule khớp** là gì?
- Policy đánh giá **first match**, priority số nhỏ trước, hierarchy hay cơ chế kết hợp khác?
- Có **inherited/org-level policy** áp dụng trước local rules không?
- Có implied rules, connection state hoặc exceptions được hệ thống tự tạo không?
- Có thể chỉ định **source/destination bằng nhóm workload, tags, service identity hoặc IP/CIDR**?
- Security rule áp vào **NIC, VM, subnet, VPC, transit attachment, workload** hay upstream gateway?

### 6.1. Default deny là mục tiêu, không phải giả định

**Deny by default** nghĩa là chỉ những luồng đã được phê duyệt mới đi qua. Tuy nhiên, một số nền tảng có **default egress allow** hoặc những implied rules ở cấp network. Một số nhóm rule tự có hành vi từ chối khi không được allow; một số có policy inheritance riêng.

Vì thế phải xác minh **effective policy** thực tế, không chỉ đọc file IaC của một nhóm tài nguyên. Một VM có thể đồng thời chịu rule từ NIC, subnet, hierarchical policy, firewall trung tâm và host firewall.

### 6.2. “Allow all temporarily” cần giới hạn

Trong sự cố, một rule **0.0.0.0/0 → any:any allow** có thể giúp kết nối nhưng phá vỡ phân đoạn. Nếu có ngoại lệ được phê duyệt, cần **owner, lý do, ticket, thời hạn, phạm vi tối thiểu và test rollback**. Không để rule khẩn cấp tồn tại không thời hạn.

### 6.3. Rule shadowing và policy conflicts

**Rule shadowing** xảy ra khi một rule rộng đã khớp trước khiến rule hẹp phía sau không có tác dụng (với engine có thứ tự phù hợp). Có thể gặp tình trạng:

- Rule allow rộng vô hiệu hóa deny cụ thể theo thứ tự.
- Một rule cấp tổ chức chặn traffic dù security group local cho phép.
- Một subnet ACL chặn chiều return dù firewall workload cho phép kết nối mới.
- Một policy theo tag không áp dụng vì workload không còn tag hoặc đang ở network khác.

**Kết luận phải dựa trên effective rule analysis và test thực tế**, không suy từ tên rule.

## 7. Security groups và distributed workload firewalls

Một số nền tảng dùng **security groups** hoặc đối tượng tương đương để áp rule tại điểm gần workload, giảm nhu cầu chuyển mọi east–west traffic tới một thiết bị tập trung.

### 7.1. Lợi ích

- Policy gắn với **vai trò workload**, không chỉ với địa chỉ IP có thể thay đổi do autoscaling.
- Có thể giới hạn **app-tier → db-tier** mà không mở toàn subnet.
- Phân đoạn được thực thi gần VM/NIC hoặc service theo khả năng sản phẩm.
- Dễ quản lý bằng IaC, labels/tags, nhóm tài nguyên hoặc references được hỗ trợ.

### 7.2. Cẩn thận với nguồn/destination references

Một rule “source = app group” có thể có hành vi khác trên mỗi cloud, tùy VPC/peering/network scope. Đừng hiểu nó luôn kiểm tra danh tính người dùng hay chứng thư TLS. **Group membership trong firewall là nhận diện tài nguyên mạng được gán**, không phải AuthN của ứng dụng.

Nếu dùng IP/CIDR, phải kiểm tra tác động của **autoscaling, ENI changes, load balancer addresses, NAT và dynamic IP assignment**. Các reference-based rules có thể linh hoạt hơn nhưng phải kiểm soát quyền gắn tag/group để tránh workload không tin cậy tự nhận làm app-tier.

### 7.3. Ví dụ ma trận traffic

| Source role | Destination role | Protocol/port | Kỳ vọng |
| --- | --- | --- | --- |
| Public load balancer | Web/app instances | TCP 8443 | Allow khi đúng service |
| App instances | Database | TCP 5432 | Allow từ đúng app-tier |
| Internet | Database | TCP 5432 | **Deny** |
| App instances | Management SSH | TCP 22 | **Deny** trừ luồng quản trị được duyệt |
| Bastion/PAM | Managed app instances | TCP 22 hoặc cổng quản trị được phê duyệt | Allow có điều kiện |
| App instances | Approved egress gateway | TCP 443 hoặc cổng cần thiết | Allow trong phạm vi kiểm soát |

Những cổng chỉ là ví dụ; hệ thống thật phải lấy **service inventory** và các dependency thực tế. Không dùng subnet đủ rộng để thay một vai trò workload khi đã có cơ chế reference chính xác.

## 8. Network ACL ở cấp subnet

Network ACL có thể bổ sung lớp kiểm soát **rộng theo subnet**, nhưng không phải công cụ tốt để mô tả mọi quyền chi tiết của ứng dụng. Trong một số nền tảng, ACL kiểu này là stateless và cần rule cho cả chiều đi lẫn chiều về.

### 8.1. Vai trò phù hợp

- Chặn những nguồn/đích hoặc giao thức rõ ràng không được phép tại ranh giới subnet.
- Bổ sung phòng vệ khi một workload security rule bị cấu hình sai.
- Giới hạn một số hướng kết nối giữa vùng mạng có trust level khác nhau.
- Hỗ trợ chiến lược containment ở phạm vi mạng khi có quy trình phê duyệt.

### 8.2. Những giới hạn

- Khó quản lý **ephemeral port ranges** nếu traffic và hệ điều hành đa dạng.
- Có thể tạo outage do thứ tự rule, implicit deny hoặc chiều phản hồi.
- Không biết danh tính người dùng hoặc quyền ứng dụng.
- Cần kiểm tra phạm vi được áp dụng thật: không phải mọi traffic giữa hai workload cùng subnet đều đi qua cùng ACL trên mọi sản phẩm.

**Chỉ có ACL subnet không đủ để bảo vệ dữ liệu** nếu application hoặc IAM chấp nhận một request trái quyền.

## 9. Managed network firewall và cloud NGFW

**Managed network firewall** là dịch vụ cho phép tổ chức xây dựng policy tập trung hơn cho một số đường traffic, có thể gồm **stateful packet inspection, rule theo domain, detection/prevention hoặc quản lý threat feeds** tùy sản phẩm.

### 9.1. Vị trí triển khai

Những mô hình phổ biến:

- **Centralized egress inspection:** workloads private gửi traffic tới điểm firewall/proxy rồi mới ra Internet.
- **Hub-and-spoke inspection:** nhiều mạng ứng dụng nối qua một hub, firewall kiểm soát những luồng được đưa qua hub.
- **Ingress inspection:** traffic public hoặc hybrid đi qua firewall ở điểm vào theo thiết kế.
- **East–west inspection:** các zone nhạy cảm trao đổi qua đường được steer qua firewall.

~~~mermaid
flowchart LR
    A["App VPC/VNet A"] -->|"Route được kiểm soát"| HUB["Transit Hub"]
    B["App VPC/VNet B"] -->|"Route được kiểm soát"| HUB
    ONP["On-prem VPN/private circuit"] --> HUB
    HUB -->|"Steered traffic"| FW["Managed Network Firewall"]
    FW --> INTERNET["NAT/Internet egress"]
    FW --> DB["Sensitive shared services"]
    FW -. "Alert/flow logs" .-> SIEM["SIEM / Security Analytics"]
~~~

**Sơ đồ không khẳng định mọi kết nối A → B đều đi qua firewall.** Nếu tồn tại peering, endpoint hoặc route trực tiếp không qua hub, firewall trung tâm có thể không thấy những luồng đó.

### 9.2. Routing symmetry và connection tracking

Nhiều stateful firewall yêu cầu **luồng request và response đi qua cùng hệ thống/state context** để nhận diện phiên ổn định. Nếu route đưa chiều đi qua firewall A nhưng chiều về đi thẳng hoặc qua firewall B không chia sẻ state, traffic có thể bị drop hoặc không được kiểm tra như dự kiến.

Cần kiểm tra:

1. **Forward path** và **return path** tại từng hop.
2. NAT/SNAT có thay đổi địa chỉ nguồn hoặc port không?
3. Đường đi qua Availability Zones/regions và sự hỗ trợ stateful inspection của dịch vụ.
4. **Failover** có giữ đúng route, policy và connection state kỳ vọng không?
5. Traffic IPv6, hybrid, intra-subnet hoặc private endpoints có đi qua cùng điểm kiểm soát không?

### 9.3. Managed không đồng nghĩa “mặc định nhìn thấy mọi lưu lượng”

Một dịch vụ có thể chạy sẵn và chứa hàng trăm rules, nhưng **không kiểm soát được traffic chưa đi qua điểm enforcement**. Để audit, không chỉ hỏi “đã triển khai managed firewall chưa?”, mà phải hỏi **luồng quan trọng nào đã được định tuyến qua nó, policy nào có hiệu lực, và log nào chứng minh?**

## 10. NGFW, IDS/IPS và TLS inspection: chức năng và giới hạn

### 10.1. Stateful filtering và application awareness

Một số managed firewalls cung cấp:

- Phân tích kết nối stateful theo protocol/port.
- Danh mục ứng dụng hoặc domain filtering theo cơ chế sản phẩm.
- IDS/IPS signatures, threat intelligence hoặc bot/network threat detection.
- Giới hạn egress theo tập nguồn/đích được quản lý.
- TLS inspection nếu có cơ chế giải mã, certificate/trust policy và quyền triển khai phù hợp.

**Không phải mọi cloud firewall có đầy đủ chức năng NGFW**, và quy tắc “domain allowlist” có thể phụ thuộc DNS, SNI hoặc thông tin ứng dụng; không suy rằng nó kiểm soát mọi IP hoặc mọi kết nối được mã hóa end-to-end.

### 10.2. IDS khác IPS

**IDS** quan sát và phát cảnh báo; **IPS** có thể chặn hoặc can thiệp theo policy nếu hoạt động inline đúng vị trí. Một hệ thống đặt ở chế độ **alert-only** không thể được coi là đã phòng ngừa cùng mức như một IPS đang **enforce**.

### 10.3. TLS inspection không phải tính năng vô điều kiện

Nếu traffic HTTPS được mã hóa, firewall thông thường không nhìn thấy đầy đủ payload HTTP chỉ từ IP/port. **TLS decryption/inspection** đòi hỏi thiết kế tin cậy và tuân thủ thích hợp, có thể yêu cầu trust anchors được cấp phát cho clients hoặc cơ chế proxy được tổ chức cho phép.

Rủi ro phải đánh giá:

- Bảo vệ CA/private keys và quyền riêng tư dữ liệu.
- **mTLS, certificate pinning, QUIC/HTTP3 hoặc ECH** có thể ảnh hưởng khả năng kiểm tra theo sản phẩm.
- Tác động latency, capacity, HA và fail mode.
- Dịch vụ nhạy cảm không được phép giải mã hoặc traffic không tương thích.
- Có thể cần **xác minh lại TLS upstream** thay vì chỉ giải mã đoạn phía client.

**Không tắt xác minh chứng thư hoặc phát tán root CA không rõ nguồn** để làm TLS inspection hoạt động.

## 11. WAF và DDoS protection trong kiến trúc cloud

**WAF** bảo vệ lớp HTTP(S) ở CDN, application gateway, API gateway hoặc proxy được hỗ trợ. Nó có thể hạn chế một số kiểu request bất thường, nhưng không phải firewall bảo vệ mọi gói TCP/UDP trong VPC/VNet.

| Rủi ro | Lớp bảo vệ nên xem xét |
| --- | --- |
| HTTP request độc hại vào public API | WAF, gateway validation, application controls |
| SYN flood hoặc volumetric flood | Network/edge DDoS protection, capacity và upstream mitigation |
| Database lộ cổng TCP trực tiếp | Security group/NSG, subnet/network firewall, private access |
| Workload gửi dữ liệu ra domain không phê duyệt | Egress firewall/proxy, DNS/network policy, IAM/data controls |
| Người dùng có token hợp lệ nhưng đọc sai tenant | Application authorization, data policy |
| Phát hiện lateral movement | East–west controls, IDS/IPS, EDR, logs |

### 11.1. Bảo vệ origin

Nếu CDN/WAF đứng trước public origin, cần **ngăn truy cập trực tiếp origin** khi kiến trúc yêu cầu. Một public IP, alternate LB, IPv6 listener hoặc route riêng có thể làm client đi vòng qua WAF. Dùng **network restrictions, private connectivity, mTLS/identity validation** theo khả năng nền tảng, thay vì chỉ ẩn origin trong DNS.

### 11.2. Rate limiting và chống lạm dụng

Rate limiting tại WAF/API gateway giúp hạn chế request theo IP, identity, token hoặc route, nhưng không tự sửa lỗi authorization. Với nguồn qua CDN/NAT, cần xác minh **client IP có thật được suy luận từ trusted proxy chain**; không tin X-Forwarded-For từ client tự gửi.

### 11.3. Đánh đổi khả dụng

Rule WAF/IPS quá chặt có thể chặn khách hàng hợp lệ; rule quá lỏng làm tăng exposure. Cần có giai đoạn **observe-only/canary** nếu được sản phẩm hỗ trợ, theo dõi false positives, change tickets và rollback.

## 12. Route table, NAT và Internet gateway không phải firewall

Một đường mạng thành công thường cần **route phù hợp**, **đường truyền/gateway khả dụng** và **các chính sách firewall cho phép**. Hai câu hỏi độc lập:

- **Routing:** gói tin được đưa qua next hop nào?
- **Policy enforcement:** gói tin hoặc kết nối có được phép vượt qua ranh giới này không?

### 12.1. Internet gateway và NAT

Trong nhiều kiến trúc cloud, **Internet gateway** là một thành phần kết nối VPC/VNet hoặc vùng mạng ra Internet theo khả năng sản phẩm. **NAT** dịch địa chỉ/port cho những traffic phù hợp, thường giúp private workloads dùng địa chỉ egress chung để kết nối ra ngoài.

**NAT không tự thay stateful firewall, DNS filtering hoặc quyền API.** Việc không có public IP trên VM cũng không có nghĩa VM không thể **khởi tạo kết nối outbound tới Internet**. Nếu subnet có default route tới NAT/gateway và các policy cho phép, malware trên VM vẫn có thể tạo traffic ra ngoài.

### 12.2. Bảng ví dụ: đường đi và quyền

| Route | Firewall/effective policy | Kết quả dự kiến |
| --- | --- | --- |
| Có route từ App tới DB | Deny TCP 5432 | Không kết nối DB được |
| Có route từ App tới DB | Allow TCP 5432 đúng nguồn | Kết nối mạng có thể thành công; DB vẫn cần auth |
| Không có route tới DB | Allow trên security group | Không đến được đích dù rule allow |
| App có default route qua NAT | Egress allow-all | Có thể ra nhiều đích ngoài ý định |
| App route qua managed firewall | Firewall policy chặn domain/đích | Bị chặn nếu traffic thực sự qua firewall và rule áp dụng |

**Kết nối TCP thành công chỉ cho thấy đường và policy ở mức network đã cho phép**, không chứng minh ứng dụng hoặc người dùng được cấp quyền dữ liệu.

### 12.3. NAT làm thay đổi cách ghi log

Sau NAT, nhiều workloads có thể xuất hiện cùng **source public IP** tại dịch vụ ngoài. Log egress chỉ ghi IP công cộng không đủ xác định instance nào đã kết nối; cần kết hợp **flow logs phía workload/VPC, NAT translation logs khi có, thời gian, port và identity**.

Trong môi trường tổ chức có mạng chồng CIDR, NAT có thể được dùng để xử lý xung đột, nhưng làm correlation và debugging khó hơn. Phải ghi rõ **địa chỉ trước và sau dịch** để tránh áp policy nhầm vùng.

## 13. Egress control và phòng chống data exfiltration

**Egress** là traffic do workload nội bộ khởi tạo tới bên ngoài zone đã định nghĩa. Một workload phục vụ web thường chỉ cần một số luồng outbound như gọi API đối tác, lấy gói cập nhật, truy vấn DNS được quản lý và gửi telemetry; không nhất thiết cần quyền kết nối tới **mọi IP và mọi port**.

### 13.1. Nguyên tắc thiết kế

1. Kiểm kê **đích egress cần thiết** theo service owner và ứng dụng.
2. Đưa traffic qua **điểm kiểm soát phù hợp**: distributed firewall, proxy, managed egress firewall hoặc endpoint policy.
3. Định nghĩa **protocol/port, destination, service identity** và điều kiện theo khả năng sản phẩm.
4. Giới hạn truy cập Internet trực tiếp từ workloads nhạy cảm.
5. Quản lý **DNS resolver**, hành vi khi DNS fail và khả năng ứng dụng dùng direct IP/DoH.
6. Ghi log allow/deny, có cơ chế phê duyệt đích mới và kiểm thử dependency.

### 13.2. IP allowlist và domain allowlist

- **IP allowlist** ổn khi đích có địa chỉ ổn định và được quản lý, nhưng CDN/managed services có thể thay IP liên tục.
- **Domain/FQDN allowlist** thuận tiện hơn cho một số ứng dụng nhưng phụ thuộc DNS, TLS/SNI hoặc khả năng nhận dạng của firewall; **không mặc nhiên lọc được mọi kết nối đến IP đích**.
- **Application identity / managed service endpoints** có thể hỗ trợ ràng buộc đích theo dịch vụ, nhưng cần kiểm tra provider-specific features.

Không dùng việc có tên DNS giống đối tác làm bằng chứng ứng dụng đã kết nối tới **đúng danh tính TLS**; client vẫn phải xác minh chứng thư máy chủ ở tầng TLS.

### 13.3. Các đường bypass thường gặp

- Instance có public IP và route Internet khác đường firewall tập trung.
- Một subnet mới chưa gắn route tới egress inspection.
- Workload dùng **IPv6** ra Internet trong khi egress filter chỉ xét IPv4.
- DNS firewall chỉ áp khi dùng resolver mặc định, nhưng workload dùng resolver khác/DoH.
- Private endpoints/service paths đi ngoài thiết bị NGFW, cần security/resource policies riêng.
- Autoscaling tạo instance tại subnet có default rules khác với subnet chuẩn.

Vì vậy, egress security cần một **network coverage matrix** chứ không chỉ một rule tập trung.

### 13.4. Data exfiltration không chỉ qua Internet

Kẻ tấn công có thể lạm dụng **object storage bucket, managed database, logging service, SaaS API hoặc hệ thống backup** vốn là điểm đến được phép về mạng. Firewall L3/L4 không biết dữ liệu nào được phép tải lên. Cần **IAM/resource policy, service perimeter, DLP, logging và phân quyền dữ liệu** bổ sung.

## 14. Private endpoints và managed-service access

**Private endpoint**, **private service connectivity** hoặc khái niệm tương đương cho phép workload truy cập một dịch vụ quản lý qua đường mạng riêng theo thiết kế của cloud. Phương thức, phạm vi và cách DNS hoạt động khác nhau theo loại dịch vụ.

### 14.1. Điều private endpoint có thể cải thiện

- Giảm việc để một số kết nối ứng dụng ↔ managed service đi qua public Internet.
- Hỗ trợ áp dụng routing, security group/firewall, DNS và resource policies phù hợp.
- Kiểm soát những VPC/VNet hoặc principals được phép kết nối tới endpoint theo cơ chế sản phẩm.
- Tăng tính nhất quán cho đường đi giữa zone ứng dụng và dịch vụ nhạy cảm.

### 14.2. Điều private endpoint không tự cung cấp

- Không mặc nhiên **xác thực người dùng cuối** hoặc cấp quyền đọc mọi bucket/database.
- Không loại bỏ nhu cầu **TLS server identity validation**.
- Không tự ngăn workload gửi dữ liệu tới **tài nguyên khác** cùng loại dịch vụ nếu resource/service policies không giới hạn.
- Không bảo đảm mọi DNS name đều resolve sang private IP nếu private DNS cấu hình sai.
- Không thay audit của cloud IAM, database hoặc storage layer.

### 14.3. Mô hình ba lớp

Một ứng dụng ghi dữ liệu tới object storage nên có ít nhất:

| Lớp | Câu hỏi |
| --- | --- |
| **Network path** | Workload có đi qua endpoint/route được phê duyệt không? |
| **Network policy** | Ai có thể kết nối tới endpoint/dịch vụ này theo nguồn và giao thức? |
| **Resource authorization** | Service principal có quyền **PutObject** vào đúng bucket/prefix không? |

Khi cần, bổ sung **encryption policy, object ownership, key policy và DLP**. Một đường truyền private không làm mất rủi ro **overprivileged IAM**.

### 14.4. Kiểm tra DNS ở private endpoint

Nếu API có public hostname nhưng mạng nội bộ cần dùng private endpoint, DNS cấu hình không nhất quán có thể khiến client:

- Đi theo public endpoint thay vì private endpoint.
- Không kết nối được dù endpoint đã tạo.
- Resolve khác nhau giữa on-prem, branch, VPN và subnet cloud.
- Gặp hostname/SNI mismatch nếu sử dụng địa chỉ hoặc tên không đúng.

**DNS giải quyết định vị; IAM quyết định quyền; firewall giới hạn đường đi**. Cần thử cả ba ở đúng nguồn client.

## 15. Hybrid network, peering và transit connectivity

Mạng cloud thường nối với data center qua **site-to-site VPN** hoặc kết nối riêng; nhiều VPC/VNet nối qua **peering/transit hub**. Việc nối mạng có thể làm tăng phạm vi lateral movement nếu các zone được tin quá rộng.

### 15.1. Peering không tự là firewall

Một kết nối **VPC/VNet peering** hoặc đường kết nối tương tự chỉ cung cấp khả năng liên thông theo thiết kế sản phẩm. Route, firewall, DNS và IAM vẫn quyết định ứng dụng nào truy cập được tài nguyên nào.

**Không mặc định peering có tính bắc cầu (transitive) hay cho phép mọi luồng**; hành vi phụ thuộc nền tảng, thiết kế transit và tính năng routing được sử dụng.

### 15.2. Hub-and-spoke

Một **transit hub** có thể tập trung quản lý route, kết nối on-prem và điểm kiểm tra firewall. Để đạt segmentation:

- Đặt **route domain/attachment policy** rõ ràng cho từng spoke.
- Tránh việc toàn bộ spokes tự động học mọi route mà không có nhu cầu.
- Chỉ steer traffic qua firewall ở điểm được thiết kế.
- Xác minh **return route symmetry** và failover.
- Phối hợp distributed security groups/NSGs cho các luồng không qua hub.

### 15.3. CIDR overlap và giới hạn theo route

Hai mạng dùng cùng **10.10.0.0/16** có thể tạo xung đột định tuyến. Tổ chức có thể dùng renumbering, NAT hoặc network architecture khác theo khả năng sản phẩm. Đây là quyết định kết nối, **không phải cách cấp quyền mặc định**.

Nếu phải NAT, log cần tương quan IP trước/sau; những rule firewall dựa trên CIDR cũng phải đặt tại **điểm quan sát đúng địa chỉ đã dịch**.

### 15.4. Rủi ro từ mạng đối tác

Đối tác kết nối qua VPN/private link không tự thuộc cùng trust zone với nhân viên. Cần giới hạn đúng **subnet/service/port**, xác thực service và phân quyền dữ liệu. **Không mở all-to-all** giữa cloud VPC và partner CIDR chỉ vì đường VPN đã mã hóa.

## 16. IPv6 và dual-stack cloud firewalls

**IPv4 và IPv6 phải được thiết kế như hai đường mạng cần được bảo vệ**, không phải một cơ chế tự động kế thừa policy từ nhau.

### 16.1. Những điểm cần rà soát

1. Workload/subnet/VPC có IPv6 addresses hoặc public IPv6 reachability không?
2. Có **::/0 route**, internet gateway hoặc egress-only gateway theo khả năng cloud không?
3. Firewall/security groups/NSGs đã có **IPv6 rules tương đương yêu cầu IPv4** chưa?
4. DNS có AAAA records khiến client chọn IPv6 thay vì IPv4 không?
5. Managed network firewall/IPS có thực sự xử lý luồng IPv6 ở điểm kiểm tra không?
6. VPN/hybrid và private endpoints có hỗ trợ IPv6 theo topology đang dùng không?
7. Network flow logs và SIEM có tương quan IPv6 đầy đủ không?

### 16.2. Ví dụ sai cấu hình

Một web service được giới hạn inbound IPv4 từ public LB, nhưng NIC có IPv6 global address và inbound IPv6 rule rộng. Nếu Internet có route phù hợp, client có thể thử đi trực tiếp vào dịch vụ, **bỏ qua lớp WAF/LB**.

**Đóng IPv4 public không tự đóng IPv6**. Phải đánh giá effective routing, policy và listener trên cả hai address families.

### 16.3. Egress-only gateway không phải full egress firewall

Một số nền tảng có **egress-only Internet gateway** cho IPv6. Mục tiêu chính là hỗ trợ kết nối khởi tạo từ phía trong theo mô hình dịch vụ; **đừng coi đây là kiểm soát destination allowlist, DNS filtering hoặc ứng dụng**. Workload vẫn cần egress policy ở lớp được hỗ trợ.

## 17. East–west microsegmentation và Kubernetes

Trong cloud, nhiều workload thường chia sẻ một subnet, cluster hoặc network overlay. **Subnet segmentation đơn lẻ** có thể quá thô để bảo vệ traffic giữa các pods/services hoặc giữa hai ứng dụng cùng network.

### 17.1. Microsegmentation

Microsegmentation phân quyền kết nối ở mức **workload role, service, label, identity hoặc nhóm tài nguyên**. Mục tiêu là:

- Chỉ frontend được phép gọi backend API.
- Chỉ backend service được phép kết nối database trên cổng cần thiết.
- Job batch không được gọi API admin nếu không cần.
- Workloads thuộc môi trường **dev** không thể kết nối trực tiếp **production data**.
- Pod bị xâm nhập không mặc nhiên có đường tới mọi pod cùng cluster.

### 17.2. Kubernetes NetworkPolicy

**Kubernetes NetworkPolicy** có thể mô tả những luồng ingress/egress giữa pods và CIDR theo khả năng CNI/plugin. Một số điểm quan trọng:

1. **CNI phải hỗ trợ NetworkPolicy enforcement**; có file YAML không có nghĩa policy hoạt động.
2. Đối tượng được chọn bằng **podSelector, namespaceSelector** và những trường policy được Kubernetes hỗ trợ.
3. **Ingress và egress isolation** cần được thiết kế rõ; policy chọn pods/traffic theo semantics của Kubernetes.
4. Cần có rules cho DNS, metrics, health probes, service discovery và API dependencies hợp lệ.
5. **Service mesh authorization và mTLS** bổ sung xác thực service, không bị NetworkPolicy thay thế.
6. Nếu pods có **hostNetwork**, node-level exposure hoặc những loại networking đặc biệt, phải kiểm tra cách plugin xử lý.

### 17.3. Ví dụ policy logic

Giả sử có các workload:

| Workload | Nguồn được phép | Đích được phép | Điều kiện khác |
| --- | --- | --- | --- |
| frontend | Public ingress controller | backend-api:8443 | API authentication tại backend |
| backend-api | frontend hoặc job đã duyệt | database:5432, identity provider, telemetry | Workload identity và application auth |
| database | Chỉ backend-api | Egress tối thiểu cho backup/monitoring | DB authentication và encryption |
| admin-tool | Bastion/PAM | Service management endpoints | MFA/JIT và audit |

Không thể coi **tất cả pods cùng namespace** là cùng một trust level. Cần đối chiếu quyền sửa label/namespace, vì policy dựa trên selector có thể bị suy yếu nếu workload không tin cậy được phép tự gắn nhãn “admin”.

### 17.4. Cloud firewall và Kubernetes policy bổ sung nhau

Cloud firewall thường bảo vệ ranh giới VPC/subnet/node/LB, còn NetworkPolicy có thể bảo vệ **pod-to-pod** khi CNI hỗ trợ. Một gói tin có thể được các lớp xử lý khác nhau tùy NAT, overlay, eBPF và implementation; **không tự giả định cloud firewall nhìn thấy đúng pod IP hoặc pod identity**.

## 18. Serverless và PaaS network controls

Không phải workload nào cũng có VM/NIC do tổ chức quản lý trực tiếp. **Serverless functions, managed container platforms, managed databases** có các điểm cấu hình truy cập riêng.

### 18.1. Các câu hỏi cần trả lời

- Dịch vụ có **public endpoint** hay chỉ private ingress?
- Có thể giới hạn nguồn theo network policy/connector/private endpoint không?
- Egress đi qua **VPC/VNet connector, NAT, managed egress** hay mạng do nhà cung cấp quản lý?
- Có hỗ trợ identity-based access, service-to-service authentication và IAM không?
- DNS và TLS của kết nối tới các managed services được kiểm soát ở đâu?
- Có thể bật firewall/flow logs ở đúng điểm enforcement không?

### 18.2. Function không có public IP vẫn có thể gọi dịch vụ ngoài

Một function nằm trong một môi trường managed có thể có egress mặc định hoặc cấu hình connector tùy sản phẩm. **Không suy từ việc không quản lý VM/NIC rằng egress bị khóa**. Phải kiểm tra tài liệu sản phẩm và thử đường ra thực tế.

### 18.3. Managed database có thể có firewall riêng

Một database PaaS có thể hỗ trợ **allowed networks/private endpoint/service firewall**, nhưng việc kết nối tới database vẫn cần **database credentials/workload identity và quyền trên dữ liệu**. Ngược lại, database account hợp lệ cũng không được phép đi từ một mạng không được duyệt nếu thiết kế yêu cầu private-only access.

## 19. Identity, IAM và firewall policy là các lớp khác nhau

Trong cloud, **IAM** quyết định chủ thể nào được gọi management API hoặc truy cập tài nguyên theo policy; **network firewall** kiểm soát traffic ở những điểm được áp dụng; **ứng dụng/database** kiểm tra quyền nghiệp vụ.

### 19.1. Hai loại quyền thường bị trộn

1. **Quyền sửa firewall:** cloud IAM cho phép một operator hoặc automation thay đổi security group, route table hoặc managed firewall policy.
2. **Quyền traffic đi qua firewall:** effective network rules cho phép một nguồn kết nối tới một đích.

Một người có quyền IAM sửa security group có thể **mở rộng kết nối** dù không có quyền đọc database. Ngược lại, mở TCP 5432 tới database không tự cấp quyền đăng nhập hoặc SELECT trong DB.

### 19.2. Giới hạn quyền thay đổi network controls

- Chỉ roles/automation được phê duyệt mới có thể sửa firewall, route, peering và endpoint.
- Dùng MFA/JIT, workload identity và phê duyệt thay đổi theo rủi ro.
- Ghi audit **ai sửa rule nào, thời điểm nào, trước/sau ra sao**.
- Kiểm soát quyền **gắn tags, thay đổi security group assignment hoặc chuyển workload sang subnet khác**.
- Có cơ chế phát hiện cấu hình drift và tự sửa/rollback **theo chính sách được phê duyệt**, tránh thay đổi ngầm không đánh giá tác động.

### 19.3. Rủi ro policy theo tag

Nếu rule dựa trên tag **role=database** và một user có thể tự gắn tag đó lên VM bất kỳ, user có thể khiến VM nhận policy hoặc quyền kết nối không đúng. **Bảo vệ quyền thay đổi thuộc tính đối tượng chọn rule** quan trọng không kém rule itself.

### 19.4. Network policy không thay thế OAuth/PKI

Một API đặt trong private subnet vẫn phải kiểm tra **TLS server identity, access token audience/scope và object authorization**. Network policy giúp giảm ai có thể đến cổng API nhưng không đảm bảo request HTTP đã được phép.

## 20. Ví dụ chính sách trung lập với nhà cung cấp

YAML dưới đây mô tả **ý định bảo mật**. Nó **không phải** cú pháp áp dụng trực tiếp vào AWS Security Group, Azure NSG, Google Cloud Firewall Policy, Kubernetes NetworkPolicy hoặc một managed NGFW cụ thể.

~~~yaml
cloudNetworkSecurityPolicy:
  name: three-tier-cloud-defense
  environment: isolated-training
  ownership:
    networkTeam: cloud-platform
    securityTeam: security-operations
    applicationOwner: order-service
    defaultDecision: deny-unless-explicitly-approved
  zones:
    publicEdge:
      cidr: 10.50.10.0/24
      exposure: public-load-balancer-only
    application:
      cidr: 10.50.20.0/24
      exposure: private
    data:
      cidr: 10.50.30.0/24
      exposure: private
    management:
      cidr: 10.50.90.0/24
      exposure: approved-admin-path-only
  ingress:
    - name: internet-to-public-lb
      from: internet
      to: public-load-balancer
      protocol: tcp
      destinationPort: 443
      enforcement: cloud-edge-and-waf
    - name: lb-to-app
      from: approved-load-balancer-role
      to: app-tier
      protocol: tcp
      destinationPort: 8443
      enforcement: workload-firewall
    - name: app-to-db
      from: approved-app-role
      to: database-tier
      protocol: tcp
      destinationPort: 5432
      enforcement: workload-firewall-and-database-policy
    - name: bastion-to-admin
      from: approved-bastion-role
      to: approved-management-targets
      protocol: tcp
      destinationPort: 22
      conditions:
        - privileged-identity
        - mfa
        - jit-approval
  egress:
    mode: reviewed-service-specific-allowlist
    directInternetFromDataZone: deny
    approvedProxyOrFirewallRoute: required-when-internet-needed
    dnsResolver: organization-managed
    privateManagedServices: require-endpoint-and-resource-policies
    inspectIpv4AndIpv6: true
    reviewDoHAndDirectIpBypass: true
  eastWest:
    default: deny
    restrictCrossEnvironment: true
    requireWorkloadServiceIdentity: for-sensitive-applications
    podNetworkPolicy: enabled-when-cni-enforces
  managedFirewall:
    requiredTrafficClasses:
      - reviewed-internet-egress
      - selected-hybrid-to-data-access
    routeSymmetryRequired: according-to-firewall-state-model
    detectBypassRoutes: true
    failoverTested: true
    ipsMode: stage-and-approve
  managedServiceAccess:
    privateEndpointsPreferred: for-sensitive-managed-services
    restrictEndpointPolicies: when-supported
    requireCloudIamAndResourcePolicy: true
  logging:
    flowLogs: enabled-at-relevant-layers
    firewallDecisionLogs: enabled
    dnsLogs: enabled-for-managed-resolver
    networkConfigurationAudit: enabled
    recordPolicyVersion: true
    redactSecrets: true
  governance:
    changesViaReviewedIac: true
    temporaryRulesRequireExpiry: true
    blockUnapprovedPublicExposure: true
    scanEffectiveRulesAndRoutes: true
    positiveAndNegativeTests: required
    incidentRollbackPlan: required
~~~

**Quan trọng:** Các từ khóa như **enforcement**, **requiredTrafficClasses** hoặc **blockUnapprovedPublicExposure** là yêu cầu thiết kế. Chỉ có ý nghĩa khi đã được ánh xạ sang sản phẩm thực và được xác minh bằng cấu hình/flow tests. **Không coi YAML có default: deny là bằng chứng provider đang default deny.**

### 20.1. Ma trận policy từ YAML

| Source | Destination | Port/protocol | Lớp enforcement | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Internet | Public LB | TCP 443 | Edge/WAF và cấu hình LB | Allow |
| Internet | App VM private | TCP 8443 | Routing + workload firewall | Deny |
| Internet | DB private | TCP 5432 | Routing + network/workload controls | Deny |
| Public LB | App tier | TCP 8443 | Workload firewall | Allow |
| App tier | DB tier | TCP 5432 | Workload + DB auth | Allow có điều kiện |
| App tier | DB management port | Chỉ cổng đặc quyền tương ứng | Security policy | Deny nếu không được duyệt |
| Data tier | Internet | Any | Egress route/firewall | Deny theo thiết kế |
| Admin bastion | Approved target | TCP 22 | PAM, workload policy và audit | Allow trong phạm vi phê duyệt |
| Dev environment | Production DB | TCP 5432 | Network segmentation | Deny |

### 20.2. Lưu ý IP trong ví dụ

Các dải **10.50.0.0/16** ở đây là địa chỉ private dành cho mô hình, **không đại diện mạng thật**. Port **8443, 5432 và 22** chỉ minh họa luồng; tổ chức cần dùng đúng inventory và giới hạn chỉ vào tài nguyên cần thiết.

## 21. Infrastructure as Code và policy-as-code

Trong cloud, firewall policy có thể thay đổi thường xuyên khi hệ thống autoscale, tạo cluster, thêm route hoặc đổi endpoints. **Infrastructure as Code (IaC)** và **policy-as-code** giúp quản lý thay đổi có thể kiểm toán.

### 21.1. Quy trình quản trị thay đổi

1. **Định nghĩa yêu cầu:** service owner nêu nguồn, đích, port, thời gian và lý do.
2. **Thiết kế rule:** ưu tiên đối tượng workload/service thay CIDR quá rộng khi tính năng cho phép.
3. **Code review:** network team và security reviewer kiểm tra least privilege, IPv6 và đường bypass.
4. **Static analysis/policy checks:** cảnh báo public database ports, allow-all egress hoặc rules không có owner.
5. **Plan/diff:** xem thay đổi dự kiến trên đúng tài nguyên và vùng.
6. **Apply theo canary/staged deployment:** có cửa sổ thay đổi và rollback.
7. **Runtime validation:** kiểm tra effective policies, routes và kết quả allow/deny.
8. **Continuous drift detection:** phát hiện thay đổi ngoài IaC hoặc quyền vừa được cấp thêm.

### 21.2. Những guardrails có giá trị

- Không cho tạo security group mở **database ports tới Internet** trừ ngoại lệ có phê duyệt rõ.
- Cảnh báo quy tắc **0.0.0.0/0 hoặc ::/0** cho các cổng quản trị.
- Bắt buộc tag **owner, environment, business justification, ticket, expiry** với rule tạm.
- Không cho gắn public IP hoặc public LB lên backend nhạy cảm ngoài mô hình cho phép.
- Phát hiện route mới có thể **bypass managed firewall inspection**.
- Giới hạn ai có thể sửa **flow logs, DNS rules, security alerts và cloud audit policy**.

### 21.3. Khác biệt desired state và effective state

Một IaC repository mô tả policy mong muốn, nhưng tài nguyên thật có thể bị thay đổi thủ công, bị policy cấp cao ghi đè hoặc dùng một attachment không thuộc IaC. Cần so **desired state ↔ deployed state ↔ effective policy ↔ observed traffic outcome**.

Không lấy kết quả **plan success** hoặc **terraform apply success** làm bằng chứng security boundary đã đúng; phải thực hiện negative tests.

### 21.4. Vòng đời ngoại lệ

Một rule tạm để vendor xử lý sự cố nên có **ticket, approver, owner, thời điểm hết hạn, giám sát và cách thu hồi**. Định kỳ xem rule không còn traffic hợp lệ hoặc không còn service owner; không xóa tự động một rule production quan trọng khi chưa đánh giá tác động.

## 22. Flow logs, firewall logs và các giới hạn quan sát

Cloud thường cung cấp nhiều nguồn telemetry: **VPC/VNet flow logs, managed firewall logs, WAF logs, DNS resolver logs, load balancer access logs, VPN/tunnel logs, cloud audit logs và workload logs**. Chúng cho biết các khía cạnh khác nhau, không phải một bản ghi có thể chứng minh toàn bộ đường đi.

### 22.1. Flow log thường thể hiện gì?

Tùy nền tảng và loại log, flow record có thể có:

| Trường | Ý nghĩa |
| --- | --- |
| Timestamp / time window | Khi record được ghi hoặc khoảng quan sát |
| Source/destination IP | Hai địa chỉ trong phạm vi quan sát, có thể trước/sau NAT tùy nguồn |
| Source/destination port | Cổng vận chuyển khi được hỗ trợ |
| Protocol | TCP, UDP, ICMP hoặc thông tin giao thức liên quan |
| Action / disposition | Accepted/rejected hoặc trạng thái quan sát tương ứng nếu có |
| Bytes/packets | Lượng traffic tổng hợp theo kiểu log |
| Interface/workload/subnet ID | Tài nguyên mạng nơi quan sát |
| Traffic direction | Ingress/egress hoặc định nghĩa khác theo nguồn log |
| Network/account/project ID | Ngữ cảnh cloud của bản ghi |
| Flow/policy context | Một số dịch vụ có rule ID, policy version hoặc security context bổ sung |

**Flow logs không phải full packet capture** và thường **không chứa HTTP URL, SQL query, toàn bộ payload, danh tính user hoặc lý do business authorization**. Một số log được tổng hợp, lấy mẫu, có độ trễ hoặc có những loại traffic không được ghi theo thiết kế sản phẩm.

### 22.2. Tại sao cần nhiều log?

- **Flow logs:** cho biết luồng TCP/UDP ở điểm mạng được theo dõi.
- **Managed firewall decision logs:** có thể cho biết rule/action/IPS signature cụ thể tùy chế độ.
- **DNS logs:** giúp tương quan hostname được resolve, nhưng không chứng minh mọi traffic dùng DNS đã ghi.
- **WAF/API gateway logs:** biết HTTP host/path/status khi traffic qua điểm kiểm soát đó và được ghi theo policy.
- **Cloud control-plane audit:** ai sửa security group, route table, endpoint policy và quyền IAM.
- **Host/EDR logs:** tiến trình nào khởi tạo kết nối và hành vi endpoint.
- **Application/database logs:** user nào truy cập đối tượng dữ liệu nào và kết quả nghiệp vụ.

Khi cần xác định **một luồng có bị chặn vì rule nào**, nên lấy log ở **enforcement point thực sự có trách nhiệm**, không kết luận chỉ từ việc client timeout.

### 22.3. Log giả lập: egress bị từ chối

~~~json
{
  "timestamp": "2026-11-28T19:05:00+07:00",
  "dataset": "synthetic-training-event",
  "event_type": "cloud_network_policy_decision",
  "environment": "lab",
  "network_zone": "app-private",
  "workload_ref": "app-tier-lab-03",
  "source_ip": "10.50.20.23",
  "source_port": 53324,
  "destination_ip": "198.51.100.80",
  "destination_port": 443,
  "protocol": "tcp",
  "traffic_direction": "egress",
  "enforcement_point": "approved-managed-egress-firewall",
  "rule_id": "deny-unapproved-internet-egress",
  "decision": "deny",
  "policy_version": "lab-policy-12",
  "bytes_forwarded": 0,
  "note": "Dia chi va tai nguyen deu la du lieu gia lap"
}
~~~

Dải **198.51.100.0/24** dành cho tài liệu. Sự kiện trên giả lập một firewall đã ghi **deny**, không phải log trích từ nhà cung cấp cloud cụ thể. Một sản phẩm thật có thể dùng tên field, trạng thái action và cách đếm bytes khác.

### 22.4. Log giả lập: control plane mở rộng ingress

~~~json
{
  "timestamp": "2026-11-28T19:10:00+07:00",
  "dataset": "synthetic-training-event",
  "event_type": "network_rule_changed",
  "environment": "lab",
  "resource": "db-tier-firewall-group",
  "actor": "lab-automation-identity",
  "operation": "update-ingress-rule",
  "before": {
    "source": "approved-app-tier",
    "destination_port": 5432
  },
  "after": {
    "source": "0.0.0.0/0",
    "destination_port": 5432
  },
  "approval_ticket": null,
  "policy_compliance": "violation",
  "response": "require-review-and-containment"
}
~~~

Log control plane cho biết một rule bị mở rộng, nhưng **không tự chứng minh database đã nhận traffic Internet**. Cần kết hợp **public reachability, route tables, effective rules, listener và flow tests** trước khi kết luận impact.

## 23. Phát hiện bất thường và chỉ số vận hành

### 23.1. Theo dõi exposure

Các câu hỏi cần trả lời định kỳ:

1. Có VM, LB, database, Kubernetes ingress hoặc API endpoint nào **public ngoài danh mục**?
2. Có rule inbound từ **0.0.0.0/0** hoặc **::/0** tới database/management ports không?
3. Có rule **allow-any egress** ở data tier, secret-processing workloads hoặc privileged workloads không?
4. Có route mới dẫn traffic ra Internet mà **bypass egress inspection** không?
5. Có security group mới, tags hoặc network attachments không thuộc chính sách IaC?
6. Có private endpoint/service policy mới cho phép truy cập tới tài nguyên dữ liệu ngoài dự kiến không?
7. Có đường hybrid/peering mới nối các trust zones vốn phải cách ly không?

### 23.2. Chỉ số nên thu thập

| Metric/signal | Giá trị phòng vệ |
| --- | --- |
| Số public resources theo môi trường | Theo dõi tăng giảm bề mặt tấn công |
| Số high-risk firewall rules | Rà soát mở cổng quản trị hoặc nguồn quá rộng |
| Firewall allow/deny theo zone | Phân biệt traffic hợp lệ với policy violations |
| Egress volume và destination categories | Phát hiện thay đổi đích/khối lượng bất thường |
| Route drift / unexpected next-hop | Nhận biết đường bypass inspection |
| IPS alert rate và mode | Biết alert-only hay enforced, phân tích false positives |
| TLS inspection errors | Phát hiện cấu hình certificate/trust không đúng |
| DNS resolver anomalies | Quan sát những truy vấn bất thường theo nguồn được quản lý |
| Firewall throughput/dropped packets | Đánh giá capacity, outage, queue và fail mode |
| IaC/policy compliance | Theo dõi thay đổi không được phê duyệt |
| Mean time to remove risky rule | Đo năng lực giảm exposure |
| Approved-flow success rate | Phát hiện chính sách quá chặt làm hỏng ứng dụng |

### 23.3. Không nhầm blocked attempts với successful compromise

Một tập log chứa nhiều luồng deny từ Internet có thể phản ánh **scanner tự động hoặc thử kết nối thông thường**, không chứng minh server bị xâm nhập. Ngược lại, ít log deny không chứng minh an toàn nếu firewall không được định tuyến nhận traffic, logging bị tắt hoặc workload được phép truy cập sai.

**Cần giám sát coverage trước khi đánh giá số lượng cảnh báo.**

### 23.4. Bảo vệ log

Log firewall/DNS có thể chứa IP và hostname liên quan người dùng hoặc hoạt động nội bộ. Cần có **IAM riêng cho đọc/xóa log, retention, mã hóa, audit và redaction**. Không ghi private keys, bearer tokens hoặc payload nhạy cảm chỉ vì cần chứng minh firewall rule.

## 24. Quy trình troubleshooting khi cloud traffic bị chặn hoặc đi sai đường

Trong cloud, một lỗi “không vào được dịch vụ” có thể nằm ở DNS, route, firewall, TLS, IAM, database policy hoặc ứng dụng. Cần điều tra **từ nguồn đến đích theo từng hop**.

### Bước 1 – Mô tả luồng bị ảnh hưởng

Ghi tối thiểu:

~~~text
Source workload: app-tier-03 / 10.50.20.23
Destination:    database-tier / 10.50.30.15
Protocol:       TCP
Destination:    5432
Expected:       Allow only from approved app-tier
Observed:       Connection timeout / refusal / application error
Scope:          Authorized lab or approved production diagnostic
~~~

Không suy một lỗi **timeout** là firewall deny. Đích có thể không chạy dịch vụ, route không tồn tại hoặc host firewall từ chối.

### Bước 2 – Kiểm tra name resolution và địa chỉ

- Tên DNS được resolve tới **địa chỉ nào** tại nguồn?
- Có sự khác nhau giữa **A và AAAA** không?
- DNS private endpoint/split-horizon có hoạt động trên đúng VPC/VNet/VPN không?
- Một IP sau NAT có làm log và rule source khác với giá trị mong đợi không?

### Bước 3 – Kiểm tra route và next-hop

- Nguồn có route tới đích, và đích có return route không?
- Luồng có đi qua **transit hub, NAT, peering, managed firewall** đúng thiết kế?
- Có đường bypass, bất đối xứng hoặc route blackhole?
- Có policy routing/BGP propagation thay đổi ngoài dự kiến?

### Bước 4 – Kiểm tra effective firewall policy ở cả hai đầu

- Security group/NSG gắn đúng NIC/workload không?
- Subnet ACL có cho request **và return traffic** theo statefulness của sản phẩm không?
- Rule priority/hierarchy và implicit rules có làm thay đổi kết quả không?
- Managed firewall có được **traffic thực tế đi qua** không?
- Có local host firewall hoặc Kubernetes NetworkPolicy chặn tiếp không?

### Bước 5 – Kiểm tra TLS và quyền ứng dụng

Nếu TCP connect thành công nhưng client báo TLS certificate error, đó là lỗi **xác thực endpoint**, không phải lý do để mở firewall rộng hơn. Nếu TLS kết nối nhưng API trả 401/403, cần kiểm tra **token, audience, scope và dữ liệu** thay vì tự mở cổng.

### Bước 6 – Xác minh bằng log và test có kiểm soát

Đối chiếu flow logs với rule decision logs, load balancer/access logs và ứng dụng, theo **timestamp + source + destination + protocol + request ID** khi có. Dùng connectivity test của cloud hoặc probe giới hạn trong môi trường được phép; ghi lại chính xác **hop gây deny**.

### Bước 7 – Sửa theo phạm vi hẹp

Nếu thực sự thiếu rule **app-tier → db-tier TCP 5432**, chỉ thêm rule đúng nguồn/đích. **Không đổi thành 0.0.0.0/0:any** để “chạy trước”. Sau chỉnh sửa phải kiểm thử negative: Internet và workload không được cấp quyền **vẫn không tới DB**.

### 24.1. Bảng khoanh vùng theo triệu chứng

| Triệu chứng | Khả năng cần kiểm tra | Bằng chứng tốt |
| --- | --- | --- |
| TCP timeout | Route, firewall drop, host không trả lời | Effective rule/route và logs tại hop |
| TCP connection refused | Dịch vụ không nghe port hoặc chủ động reject | Listener/host logs và network capture được phép |
| TLS hostname mismatch | Endpoint/certificate/SNI sai | TLS validation errors, SAN và upstream config |
| HTTP 401/403 | AuthN/AuthZ, token, role | API gateway/app decision logs |
| Chỉ một Availability Zone bị lỗi | Route, firewall endpoint, health, backend pool | AZ-level config và path tests |
| Chỉ IPv6 bị lỗi hoặc bypass | AAAA, ::/0 route, IPv6 rules | IPv6-specific route/flow logs |
| DNS truy vấn được nhưng IP không connect | Route hoặc network rule | DNS result + actual packet path |
| Cloud service private endpoint lỗi | Private DNS, endpoint acceptance/policy, IAM | Endpoint logs, service policy và resolution |
| Stateful firewall drop ngẫu nhiên | Asymmetric routing, state table/capacity | Both-direction path và connection telemetry |
| Sau scale-out chỉ instance mới lỗi | Auto-attach group, subnet, tags, IaC drift | Workload metadata và effective rules |

## 25. Kiểm thử an toàn cloud firewall trong lab

Chỉ thực hiện với **cloud account/project, VPC/VNet, VM hoặc service test được cấp phép**. Không thử port scanning diện rộng đối với tài nguyên người khác và không tạo tải lớn vào managed firewall, WAF hay DNS của bên thứ ba. Mục tiêu là **kiểm chứng least privilege**, không tạo chứng minh bằng một đợt tấn công.

### 25.1. Ma trận positive và negative tests

| Mã | Tình huống | Kỳ vọng |
| --- | --- | --- |
| T-01 | Internet kết nối HTTPS tới public LB được duyệt | Allow đúng endpoint và TLS hợp lệ |
| T-02 | Internet thử vào trực tiếp private app VM | Deny hoặc không có đường theo thiết kế |
| T-03 | Internet thử tới DB TCP 5432 | Deny; DB không public reachable |
| T-04 | Public LB gọi app-tier trên TCP 8443 | Allow từ LB đã được phê duyệt |
| T-05 | Workload không thuộc LB group gọi app-tier TCP 8443 | Deny |
| T-06 | App-tier gọi DB TCP 5432 | Allow theo policy; DB authentication vẫn bắt buộc |
| T-07 | Job dev gọi production DB TCP 5432 | Deny theo segmentation |
| T-08 | Data-tier khởi tạo kết nối Internet không được duyệt | Deny theo egress policy |
| T-09 | App-tier gọi approved external API qua egress inspection | Allow và log tại điểm kiểm tra |
| T-10 | App-tier gọi unapproved IP/domain từ policy test | Deny hoặc xử lý đúng policy |
| T-11 | Đường NAT public egress thay đổi source IP | Log correlation xác định đúng workload gốc |
| T-12 | Vô tình bỏ return rule trong subnet ACL **lab cô lập** | Test thấy chiều phản hồi bị chặn theo thiết kế stateless |
| T-13 | Stateful session hợp lệ có return traffic | Response được xử lý theo state; không mở kết nối mới ngoài policy |
| T-14 | Đường hub→firewall→spoke và chiều về | Symmetry đúng, stateful flows ổn định |
| T-15 | Route dự phòng có thể bypass firewall | Phát hiện và từ chối route không đúng thiết kế |
| T-16 | Private endpoint tới managed storage | Đường private theo DNS/route, IAM/resource policy vẫn đúng |
| T-17 | Workload không có quyền IAM gọi managed storage qua private endpoint | Network có thể kết nối nhưng operation bị từ chối |
| T-18 | Bật IPv6 trên app/public endpoint trong lab | IPv6 có policy tương đương và không lộ origin |
| T-19 | Gateway VPN từ on-prem gọi đúng API | Allow đúng service/port, không được mở tới mọi subnet |
| T-20 | NetworkPolicy chặn pod không đúng role gọi DB | Deny khi CNI thực sự hỗ trợ enforcement |
| T-21 | Autoscaling tạo VM/pod mới | Nhận đúng group/labels/policies và log |
| T-22 | Thay đổi tạm rule theo ticket có expiry | Rule được phê duyệt, audit và thu hồi đúng hạn |
| T-23 | Managed firewall IPS chuyển alert-only → enforced trong lab | Action/telemetry đúng profile; không ảnh hưởng traffic hợp lệ ngoài test |
| T-24 | Một security rule public DB bị đề xuất qua IaC | Guardrail phát hiện trước triển khai |
| T-25 | Một thay đổi ngoài IaC xảy ra trong lab | Drift detection tạo cảnh báo và quy trình xử lý |
| T-26 | Client truy cập API qua TLS nhưng dùng token không đủ quyền | Network allow, application authorization deny |
| T-27 | DNS resolver dùng endpoint không được kiểm soát trong lab | Phát hiện/deny theo chính sách nguồn; không suy DNS filtering bao phủ tự động |
| T-28 | Failover firewall hoặc route có kiểm soát | Policy và logging duy trì; không fail-open ngoài dự kiến |

### 25.2. Cách thu thập bằng chứng

1. Ghi **test account/project, network zone, source/destination, protocol, port, expected result**.
2. Chụp **effective route/effective rule** bằng công cụ cấu hình hoặc analyzer phù hợp.
3. Dùng probe có giới hạn, ghi kết quả kết nối và **flow/firewall logs**.
4. Đối chiếu **backend/app logs**, xác nhận request có hoặc không đến ứng dụng.
5. Với test IPv6, ghi riêng địa chỉ, route, rule và listener IPv6.
6. Với managed firewall, kiểm tra **policy version, enforcement mode, forward/return path**.
7. Kiểm tra **luồng hợp lệ vẫn hoạt động** sau khi siết policy.
8. Ghi ticket và rollback của mọi thay đổi test.

### 25.3. Những phép kiểm tra kết nối đơn giản

Trên máy lab có quyền sử dụng, có thể kiểm tra kết nối TCP tới một endpoint **được phép thử**:

~~~powershell
# Windows: minh họa trong lab; thay bằng IP của mạng được cấp phép.
Test-NetConnection -ComputerName 10.50.30.15 -Port 5432
Test-NetConnection -ComputerName 10.50.20.20 -Port 8443
~~~

~~~bash
# Linux: nếu có công cụ nc.
nc -vz -w 3 10.50.30.15 5432
nc -vz -w 3 10.50.20.20 8443
~~~

**TCP thành công không chứng minh ứng dụng đã xác thực người dùng hoặc dữ liệu được phép**, và **TCP thất bại không tự chứng minh firewall rule đã deny**: có thể do host/service ngừng hoặc DNS/route sai. Phải đối chiếu điểm thực thi policy và trạng thái service thực tế.

### 25.4. Không thử gây gián đoạn để đo an toàn

Những tình huống như DDoS, SYN flood, packet fragmentation bất thường, IPS signature stress hoặc tạo nhiều kết nối để làm cạn state table **không nên dùng trên production hoặc dịch vụ của bên thứ ba**. Trong đào tạo, ưu tiên traffic thử ít, synthetic logs và mô phỏng có giới hạn trong lab cô lập.

## 26. Runbook: phát hiện firewall rule cloud mở quyền ngoài dự kiến

**Tình huống:** SOC phát hiện một security rule của nhóm database bị sửa từ **source=app-tier** sang **source=0.0.0.0/0** trên TCP 5432. Đây là một **configuration violation cần điều tra ngay**, nhưng phải xác minh hệ thống có thực sự bị public exposed hay không trước khi kết luận dữ liệu đã bị truy cập.

### Giai đoạn 1 – Xác minh hiệu lực và phạm vi

1. Xác định **cloud account/project, region, VPC/VNet, subnet, NIC/instance, firewall group, rule ID** và thời điểm thay đổi.
2. Đọc **audit log control plane**: principal nào đã sửa, API nào được gọi, request có gắn change ticket không?
3. Xác minh rule được **gắn vào database thực sự** hay chỉ là rule không được sử dụng.
4. Kiểm tra public IP/IPv6, internet gateway, route tables, public LB, NAT và network ACL để xác định **Internet có đường đến DB không**.
5. Kiểm tra **host firewall, database listener và DB auth**, vì khả năng mở network không đồng nghĩa DB trả dữ liệu.
6. Đọc flow logs và DB audit logs trong khoảng thời gian ảnh hưởng. Nếu thiếu log, ghi nhận đây là **giới hạn bằng chứng**, không tự giả định an toàn.
7. Tìm những tài nguyên khác dùng cùng rule hoặc những rule tương tự do automation tạo ra.

### Giai đoạn 2 – Khoanh vùng an toàn

- Nếu rule vi phạm đã được xác nhận, thu hẹp nguồn về **app-tier được duyệt** hoặc áp deny ở điểm phù hợp theo change/incident procedure.
- Nếu nghi có xâm nhập, bảo vệ log và những thông tin điều tra cần thiết trước thao tác có thể làm mất bằng chứng, theo quy trình tổ chức.
- Giới hạn những đường không cần thiết tới database; không xóa bừa các route hợp lệ phục vụ hệ thống ứng dụng.
- Kiểm tra và thu hồi quyền của principal đã sửa rule nếu có bằng chứng sử dụng trái phép.
- Với tình huống có khả năng lộ credential, phối hợp nhóm database/IAM xử lý quyền và secrets, không trông chờ một network rule.

### Giai đoạn 3 – Xác minh sửa lỗi

1. App-tier gọi database theo đúng port: **allow**.
2. Workload ngoài app-tier gọi database: **deny**.
3. Internet tới DB qua IPv4 và IPv6: **deny/không có đường** theo thiết kế.
4. Managed firewall hoặc network ACL liên quan thực sự áp dụng đúng nơi.
5. Control-plane alert phát hiện một thay đổi rule lặp lại trong lab.
6. Log ứng dụng vẫn ghi kết nối hợp lệ sau khi sửa, không gây outage ngoài phạm vi.

### Giai đoạn 4 – Tìm nguyên nhân và phòng tái diễn

- Xác định nguồn thay đổi: thao tác thủ công, CI/CD, IaC misconfiguration, quyền IAM quá rộng hay lỗi tự động hóa.
- Bổ sung guardrail chặn hoặc cảnh báo **database port exposed to all addresses**.
- Giới hạn quyền đổi ingress rules, route, tags và security group assignments.
- Thêm automated negative tests, drift detection và phê duyệt ngoại lệ có expiry.
- Đánh giá phạm vi dữ liệu đã bị truy cập theo chứng cứ, không từ một sơ đồ mạng giả định.

**Kết luận incident cần tách ba việc:** **rule đã mở rộng**, **đường truy cập thật sự tồn tại** và **dữ liệu đã bị truy cập hay chưa**. Ba kết luận này yêu cầu những loại bằng chứng khác nhau.

## 27. Tình huống tổng hợp: managed egress firewall có nhưng traffic vẫn đi ra ngoài

Một công ty triển khai managed cloud firewall để kiểm soát Internet egress của hai môi trường **production** và **development**. Đội bảo mật quy định production workloads chỉ được gọi một số API đối tác. Firewall có rules chặn những domain không nằm trong allowlist và đưa log về SIEM.

Sau một thay đổi mạng, đội vận hành thêm subnet **prod-batch-new** cho autoscaling. Subnet này có default route đến NAT public egress **không đi qua managed firewall**, trong khi các subnet cũ có route qua firewall. Một job mới được tạo ở subnet đó có thể kết nối tới địa chỉ ngoài danh sách đích được duyệt.

### 27.1. Phân tích

1. **Policy firewall không nhất thiết sai**: rule deny có thể hoạt động trên những subnet đã được steer qua firewall.
2. **Coverage sai**: subnet mới không có route qua enforcement point.
3. **IaC governance chưa đủ**: route table association hoặc policy guardrail không bắt buộc new subnet đi qua egress inspection.
4. **Telemetry dễ gây ngộ nhận**: firewall logs không có traffic từ subnet mới vì không nhìn thấy nó, không phải vì không có traffic.
5. **Nguồn egress công khai khác nhau**: NAT direct path có thể có public IP khác, khiến đối tác thấy một nguồn không có trong danh sách dự kiến.

### 27.2. Sơ đồ nguyên nhân

~~~mermaid
flowchart TD
    OLD["Production subnet cũ"] -->|"Route qua kiểm soát"| FW["Managed Egress Firewall"]
    FW --> NAT1["Approved NAT/egress"]
    NAT1 --> EXT["External endpoints"]
    NEW["Production batch subnet mới"] -->|"Default route khác"| NAT2["Direct NAT egress"]
    NAT2 --> EXT
    FW -. "Không thấy traffic từ subnet mới" .-> ALERT["Coverage gap"]
    IAC["IaC / Route guardrails"] -. "Thiếu ràng buộc subnet mới" .-> NEW
~~~

### 27.3. Hướng sửa

- Gắn subnet mới vào **route policy/attachment đúng** để egress đi qua kiểm soát, nếu đây là kiến trúc được duyệt.
- Kiểm tra **return path và stateful behavior** sau khi steer traffic.
- Bật flow logs tại subnet mới và so sánh với firewall logs để xác nhận **traffic coverage**.
- Áp distributed egress restrictions trên workloads nếu sản phẩm cho phép, tránh phụ thuộc hoàn toàn vào một hub.
- Đưa rule **“mọi production subnet phải có approved inspection route”** vào kiểm tra IaC/policy-as-code.
- Kiểm thử egress tới đích được phép và không được phép, gồm IPv6, failover và subnet autoscaling mới.

### 27.4. Không giải quyết sai bằng cách chặn bừa

Nếu chỉ chặn public NAT IP mới bằng một rule ở firewall tập trung, biện pháp có thể vô nghĩa vì traffic **không đi qua firewall đó**. Nếu xóa default route mà chưa đánh giá dependencies, ứng dụng có thể mất khả năng tải update hoặc gọi API thiết yếu.

Cần sửa **đúng đường đi**, xác minh **đúng điểm thực thi** và giữ **traffic hợp lệ** tiếp tục hoạt động.

### 27.5. Bài học

**Sự tồn tại của một managed firewall không chứng minh toàn bộ cloud egress được bảo vệ.** Bài toán cốt lõi là **routing coverage + effective firewall policy + egress identity + telemetry + kiểm thử sau thay đổi mạng**.

## 28. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Biện pháp phù hợp |
| --- | --- | --- |
| “Private subnet là không thể gửi Internet” | Workload vẫn có thể dùng NAT/egress gateway | Kiểm tra effective routes và egress controls |
| “Có route nghĩa là firewall đã allow” | Nhầm đường đi với cấp quyền | Xác minh routing và filtering riêng |
| “Managed firewall đã triển khai nên thấy mọi traffic” | Luồng bypass không bị kiểm tra | Coverage matrix, route enforcement, flow tests |
| “Security group stateful nên không cần egress policy” | Workload có thể khởi tạo kết nối mới ngoài ý định | Explicit outbound review và deny/allow model |
| “Stateless ACL inbound 443 là đủ” | Return traffic bị chặn hoặc mở sai ephemeral ports | Kiểm tra hai chiều và range theo thực tế |
| “Rule local allow sẽ thắng mọi rule” | Policy cấp tổ chức hoặc ACL vẫn deny | Effective rule analysis và priority semantics |
| “Một cloud firewall rule áp dụng giống mọi cloud khác” | Sai statefulness, scope, order hoặc attachment | Chuyển đổi theo provider-specific behavior |
| “Đóng public IPv4 là đủ” | Lộ qua IPv6, alternate LB hoặc endpoint | Dual-stack và multi-path exposure review |
| “Private endpoint đồng nghĩa có quyền đọc data” | Overprivileged IAM/resource access | Endpoint + IAM + resource authorization |
| “DNS filtering chặn mọi đích Internet” | Direct IP/DoH hoặc resolver khác bypass | Egress network controls và DNS governance |
| “WAF chặn hết traffic VPC” | WAF không bảo vệ mọi L3/L4/east–west flows | Workload firewall, network firewall và app checks |
| “IPS alert-only đã chặn tấn công” | Chỉ cảnh báo, không enforce | Kiểm tra mode, placement và action |
| “TLS inspection thấy mọi payload HTTPS” | Mã hóa, mTLS/ECH/QUIC hoặc policy giới hạn quan sát | Phân biệt điểm giải mã thực và ngoại lệ |
| “Peering/VPN là cùng trust zone” | Lateral movement giữa partner/on-prem/cloud | Segmentation, firewall và identity |
| “Kubernetes NetworkPolicy luôn hoạt động khi có YAML” | CNI không enforce hoặc traffic đặc biệt bypass | Xác minh CNI/cluster policy bằng negative tests |
| “Service group/reference là danh tính người dùng” | Nhầm workload selection với user auth | IAM và app authn/authz độc lập |
| “NAT IP xác định đúng VM gây traffic” | Nhiều workloads dùng chung public IP | Correlation từ source flow/translation logs |
| “Có flow log thì biết toàn bộ HTTP/payload” | Thiếu nội dung và lý do ứng dụng | Kết hợp proxy/WAF/app/DB logs |
| “Mở 0.0.0.0/0 tạm rồi để lại” | Public exposure kéo dài | Ticket, owner, expiry, guardrails |
| “IaC apply thành công nghĩa là compliant” | Cấu hình deployed/effective khác desired state | Drift + effective state + runtime tests |
| “HTTP 403 chứng minh firewall đang chặn” | Có thể do ứng dụng từ chối sau khi vào mạng | Đọc log đúng enforcement point |
| “Bỏ qua failover route vì primary an toàn” | Đường dự phòng có policy yếu hơn | Kiểm thử AZ/region/DR và IPv6 |
| “Cloud IAM tự bảo vệ mọi TCP port” | IAM management/API không thay L3/L4 control | Network firewall và service auth riêng |
| “Giảm số log deny nghĩa là giảm rủi ro” | Logging/inspection coverage có thể bị mất | Đo cả coverage và outcomes |

## 29. Câu hỏi tự kiểm tra và bài tập thiết kế

### Câu hỏi 1

**Cloud firewall** và **managed network control** có khác nhau về phạm vi trách nhiệm không?

**Gợi ý:** firewall là một nhóm controls lọc traffic; managed network controls còn bao gồm các cơ chế mạng/dịch vụ quản lý có khả năng giám sát, chuyển hướng hoặc bảo vệ, nhưng khách hàng vẫn chịu trách nhiệm cấu hình policy phù hợp.

### Câu hỏi 2

Một VM trong private subnet không có public IP. Có thể kết luận nó không thể gửi dữ liệu ra Internet không?

**Gợi ý:** Không. Kiểm tra default route, NAT/egress gateway, firewall outbound và những endpoint dịch vụ cloud.

### Câu hỏi 3

Stateful và stateless firewall khác nhau ra sao khi xử lý traffic trả lời TCP?

**Gợi ý:** stateful theo dõi trạng thái kết nối; stateless thường cần rule cho mỗi chiều và đúng ephemeral ports theo thực tế.

### Câu hỏi 4

Vì sao rule allow TCP 5432 từ app-tier không đồng nghĩa app user có quyền truy vấn mọi database records?

**Gợi ý:** network connection và DB authentication/authorization là các lớp độc lập.

### Câu hỏi 5

Một managed firewall báo không có deny events từ subnet mới. Có thể kết luận subnet đó tuân thủ egress policy không?

**Gợi ý:** Không. Xem route có đưa traffic qua firewall không và logging có bao phủ subnet hay không.

### Câu hỏi 6

Vì sao private endpoint không giải quyết toàn bộ rủi ro data exfiltration tới managed object storage?

**Gợi ý:** quyền IAM/resource policies, bucket/account đích và việc có thể ghi dữ liệu ra ngoài vẫn cần được kiểm soát.

### Câu hỏi 7

Tại sao cần kiểm tra IPv6 khi public IPv4 của origin đã được đóng?

**Gợi ý:** route/listener/firewall rule theo IPv6 có thể tạo một đường tới origin khác.

### Câu hỏi 8

Security group và Kubernetes NetworkPolicy nên phối hợp thế nào?

**Gợi ý:** cloud firewall bảo vệ tài nguyên/đường mạng ở mức hỗ trợ, CNI NetworkPolicy bảo vệ pod-level flows; phải kiểm tra enforcement và những đường mạng đặc biệt.

### Câu hỏi 9

Một VPC peering cho phép định tuyến giữa hai môi trường. Có nên xem việc này là đã cấp quyền trao đổi dữ liệu giữa mọi workload không?

**Gợi ý:** Không. Route và filtering phải được kiểm soát, còn dịch vụ đích cần authn/authz riêng.

### Câu hỏi 10

Vì sao flow logs không đủ để kết luận ai đã truy cập bản ghi database số 42?

**Gợi ý:** flow log mô tả kết nối và bytes, không biết quyền user và object nghiệp vụ; cần app/DB audit logs.

### Câu hỏi 11

Nếu firewall NGFW đặt trong hub nhưng chiều về đi qua đường peering trực tiếp, điều gì có thể xảy ra?

**Gợi ý:** stateful session có thể không được nhận diện, traffic bị drop hoặc không được quan sát đầy đủ; cần route symmetry phù hợp.

### Câu hỏi 12

Một policy IaC báo “default deny” nhưng test từ Internet vẫn vào DB. Điều tra theo thứ tự nào?

**Gợi ý:** effective rules/attachments, public route/IPv6, alternate endpoints, firewall placement, host/service và log tại đích.

### Bài tập thiết kế kiến trúc

Một doanh nghiệp có **public API**, **application tier**, **managed PostgreSQL**, **object storage**, **Kubernetes cluster**, **on-prem VPN** và **batch jobs** trong cloud. Có thêm một managed firewall phục vụ egress và một WAF ở public LB.

Hãy thực hiện:

1. Vẽ sơ đồ **Internet, edge, application, data, management, hybrid và egress zones** cùng các tuyến dự kiến.
2. Ghi rõ **TLS termination**, firewall attachment và nơi xác thực service/workload trên mỗi chặng.
3. Lập ma trận **nguồn → đích → cổng → hành vi allow/deny → điểm thực thi**.
4. Giải thích vị trí phù hợp của security groups, subnet ACL, managed network firewall, WAF và DDoS protection.
5. Thiết kế network policy cho **frontend → backend → database** và ràng buộc workload/tenant ở API.
6. Xác định những traffic cần đi qua centralized firewall và làm sao bảo đảm **không bypass qua new subnet, NAT hoặc IPv6**.
7. Thiết kế quyền **private endpoint + IAM/resource policy** cho object storage; phân biệt kết nối tới endpoint và quyền ghi object.
8. Đưa ra phương án xử lý **hybrid VPN/transit routing**, source CIDR overlap và return path symmetry.
9. Mô tả IaC guardrails cho public DB ports, 0.0.0.0/0, ::/0, expired temporary rules và thiếu flow logs.
10. Viết ít nhất **mười positive/negative tests**, bao gồm Internet-to-DB denied, app-to-DB allowed, dev-to-prod denied, egress allowlist, IPv6, Kubernetes, endpoint IAM và firewall failover.
11. Thiết kế SIEM correlation từ flow logs, firewall decision logs, cloud audit logs và application/database audit.
12. Lập runbook khi một quy tắc DB bị thay đổi thành public inbound và khi subnet mới không đi qua egress firewall.

**Tiêu chí đạt:** kiến trúc chứng minh được rằng **luồng hợp lệ tới đúng dịch vụ, luồng trái quyền bị chặn tại đúng điểm, managed controls có coverage thật, log đủ để điều tra và có cơ chế kiểm soát thay đổi**.

## 30. Những điều cần ghi nhớ

- **Cloud firewall là một phần của kiến trúc phòng vệ nhiều lớp**, không phải thay thế IAM, application authorization, DNS, TLS hay IDS/IPS.
- **Security groups/workload firewalls, subnet ACLs, managed network firewalls, WAF và DDoS protection có phạm vi khác nhau**. Chọn theo luồng và điểm thực thi thực tế.
- **Stateful khác stateless**, đặc biệt với return traffic và ephemeral ports; rule evaluation, default behavior và priority phụ thuộc nhà cung cấp.
- **Route tables, NAT, peering và Internet gateway quyết định đường kết nối, không tự cấp quyền dữ liệu**. Private subnet vẫn có thể có egress qua NAT hoặc private services.
- **Managed firewall chỉ bảo vệ traffic đi qua nó**; phải xác minh routing coverage, symmetry, failover, IPv4/IPv6 và những subnet/workloads tạo mới.
- **Private endpoints giảm public exposure nhưng không tự cấp quyền truy cập managed services**; cần endpoint policy, IAM/resource authorization và TLS identity.
- **Egress filtering và east–west microsegmentation giảm khả năng di chuyển ngang/lộ dữ liệu**, song không thể thay quyền ứng dụng hoặc bảo vệ nội dung tại các PaaS APIs được phép.
- **Kubernetes, serverless và managed PaaS cần những network controls ở đúng lớp**, với enforcement được xác minh thay vì chỉ tin tên tính năng.
- **IaC, policy-as-code, audit, drift detection và ngoại lệ có thời hạn** giúp thay đổi cloud network security có thể rà soát và thu hồi.
- **Flow logs không phải packet capture hoặc business audit**; phối hợp firewall, DNS, API/DB, IAM và control-plane logs để tìm đúng nguyên nhân.
- **Kiểm thử positive và negative cases trong lab được phép** là bằng chứng tốt nhất rằng chính sách đã triển khai thực sự bảo vệ đúng các trust boundaries.
