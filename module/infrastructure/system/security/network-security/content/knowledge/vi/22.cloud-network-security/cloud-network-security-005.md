# Network ACL và stateless filtering: kiểm soát gói tin tại ranh giới mạng cloud

Một ứng dụng cloud có thể mở đúng cổng HTTPS, có security group cho phép truy cập và route table hợp lệ nhưng vẫn bị timeout. Nguyên nhân đôi khi rất đơn giản: **network access control list (Network ACL/NACL) cho phép gói request vào subnet nhưng chặn gói phản hồi đi ra**. Khác với stateful firewall, bộ lọc stateless không tự ghi nhớ kết nối TCP đã thiết lập hay truy vấn UDP đã gửi để mặc nhiên cho phép traffic đáp ứng.

**Network ACL** trong bài này là tập các quy tắc lọc lưu lượng mạng dựa trên các thuộc tính gói như **hướng đi, giao thức, địa chỉ IP/CIDR và cổng hoặc loại ICMP**, tùy nền tảng. **Stateless filtering** nghĩa là quyết định cho từng gói/chiều lưu lượng theo rule mà **không dựa trên connection state** được tích lũy từ các gói trước. Khi dùng đúng, nó là một lớp phòng vệ bổ trợ tại ranh giới subnet; khi hiểu sai, nó dễ tạo lỗ hổng quá rộng hoặc gây mất dịch vụ âm thầm.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, chủ đề thuộc chương **Bảo mật mạng cloud** và kết nối trực tiếp với phân đoạn mạng, firewall stateful, VPN, IDS/IPS, DNS, NAT, định tuyến và kiến trúc nhiều lớp. Bài học tập trung vào **thiết kế ít đặc quyền, lập ma trận hai chiều, kiểm thử và vận hành có bằng chứng**, thay vì chỉ hướng dẫn bấm một màn hình cloud.

> **Phạm vi thuật ngữ:** AWS VPC **Network ACL** là ví dụ thực tế tiêu biểu của ACL **stateless** ở cấp subnet. **Azure Network Security Group (NSG)** và **Google Cloud VPC firewall rules** có cơ chế theo dõi trạng thái lưu lượng được phép trong mô hình của chúng; không được coi chúng là bản sao stateless của AWS NACL. Chi tiết về rule, association, logging và thứ tự áp dụng luôn phải đối chiếu tài liệu của nhà cung cấp và phiên bản sản phẩm đang dùng.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **stateless packet filtering** và **stateful connection tracking**, giải thích vì sao traffic phản hồi cần được xét riêng khi dùng NACL stateless.
2. Mô tả vai trò của **subnet NACL, security group, firewall/NGFW, route table, WAF, IAM và workload authorization** trong cloud.
3. Giải thích **ingress/egress, source/destination CIDR, protocol, destination port, rule priority, first-match và implicit deny** trong mô hình AWS NACL.
4. Thiết kế **ma trận gói đi–gói về** với client ephemeral ports cho TCP, UDP/DNS và những luồng phù hợp khác.
5. Xây dựng ví dụ bảo vệ **subnet ứng dụng, database và mạng client** mà không nhầm quyền được định tuyến với quyền ứng dụng.
6. Đánh giá các yếu tố **IPv4/IPv6, ICMP/ICMPv6, PMTUD, NAT, load balancer, VPN, peering và transit routing**.
7. Nhận diện sai sót như **shadowed rules, đảo chiều cổng, mở CIDR quá rộng, rule drift, thiếu rule phản hồi**.
8. Thiết kế **logging, policy-as-code, kiểm thử ALLOW/DENY, runbook và rollback** trong môi trường cloud có thay đổi liên tục.

## 2. Mô hình tư duy: một gói tin và một luồng kết nối

Một gói TCP/UDP thường được mô tả trong bài lọc mạng bằng **5-tuple**:

~~~text
(source IP, source port, destination IP, destination port, protocol)

Ví dụ TCP request:
(10.10.10.25, 53000, 10.20.20.10, 8443, TCP)

Ví dụ TCP response:
(10.20.20.10, 8443, 10.10.10.25, 53000, TCP)
~~~

Hai gói có địa chỉ và cổng **đảo chiều**. Với firewall stateful, một gói response hợp lệ có thể được chấp nhận vì thiết bị **ghi nhận connection state** từ phiên đã cho phép theo cơ chế của nền tảng. Với ACL stateless, gói response phải **tự khớp một rule cho phép ở chiều mà nó đang đi qua**.

### Stateless không có nghĩa không xét giao thức

Stateless filter vẫn có thể kiểm tra một số thuộc tính IP/TCP/UDP/ICMP nếu sản phẩm hỗ trợ. Điều **không có** là sự ghi nhớ trạng thái phiên trước đó làm căn cứ cấp quyền cho chiều phản hồi. Vì vậy:

- Một gói **SYN** vào cổng dịch vụ có thể được phép nhờ rule inbound.
- Một gói **SYN-ACK** phản hồi có thể bị chặn nếu rule outbound thiếu cổng đích của client.
- Một gói khác từ cùng CIDR tới cổng đã được allow có thể qua NACL dù **không liên quan phiên hợp lệ**.
- NACL stateless không kiểm tra **user identity, token JWT, quyền truy cập database hoặc tính hợp lệ nghiệp vụ**.

### Phân biệt ba câu hỏi

| Câu hỏi | Lớp thường trả lời |
|---|---|
| Có tuyến tới IP đích không? | Route table, gateway, peering, VPN, transit |
| Gói được phép qua ranh giới mạng không? | NACL, SG, firewall, host firewall |
| Người dùng/workload có quyền dùng API hoặc dữ liệu không? | IAM, mTLS identity, application authorization |

**Có route không đồng nghĩa có permission; được NACL cho qua không đồng nghĩa được xác thực.**

## 3. Stateless và stateful: so sánh cốt lõi

| Khía cạnh | Stateless NACL | Stateful SG/firewall |
|---|---|---|
| Đối tượng quyết định | Gói/chiều lưu lượng theo rule | Gói kết hợp chính sách và trạng thái kết nối theo khả năng sản phẩm |
| Traffic phản hồi | Cần rule tương ứng theo hướng response | Thường được cho phép khi thuộc phiên đã được chấp nhận |
| Tập rule | Có thể có **ALLOW/DENY** và thứ tự, ví dụ AWS NACL | Phụ thuộc sản phẩm; AWS SG chủ yếu là **ALLOW** |
| Scope | Với AWS NACL: **subnet association** | Với AWS SG: gắn vào network interface/tài nguyên tương ứng |
| Quyền danh tính | Không kiểm tra IAM hay quyền application | SG stateful cũng không tự hiểu tài khoản/tenant |
| Kiểm soát cổng tạm thời | Phải xét dải ephemeral cho chiều về | Connection tracking giảm nhu cầu mở rule phản hồi riêng |
| Chi phí vận hành | Dễ sai chiều, CIDR và ưu tiên rule | Cần quan tâm giới hạn state tables, timeout, state exhaustion |

**Không mặc định “stateful luôn an toàn hơn” hoặc “stateless luôn nhanh hơn”.** Mức an toàn phụ thuộc **phạm vi chính sách, loại traffic, triển khai, giới hạn nền tảng và năng lực giám sát**. Hai lớp thường nên bổ trợ nhau.

### Một cảnh báo về từ “network ACL”

Trong sách, **ACL** có thể chỉ danh sách permit/deny trên router, switch, firewall hoặc thiết bị khác. Chức năng cụ thể khác nhau: có ACL stateless, cơ chế ACL gắn với stateful firewall, network policy của container và nhiều API cloud. **Không suy tính stateless từ chữ ACL trong tên sản phẩm**.

## 4. Cloud security nhiều lớp: NACL nằm ở đâu?

~~~text
                Internet / Partner / VPN
                          |
                     Route / Gateway
                          |
                  [Subnet boundary]
                    Network ACL
                   ingress / egress
                          |
                [Instance / Pod / ENI]
                Security Group / CNI
                          |
                     Host Firewall
                          |
                    TLS / mTLS / IAM
                          |
                Application / Database
~~~

Sơ đồ là **mô hình logic**. Trên AWS, NACL được liên kết với subnet và SG được gắn với network interface/tài nguyên phù hợp; các cơ chế thực thi nằm trong mạng ảo của nhà cung cấp. **Không suy vị trí thiết bị vật lý, thứ tự mọi bước packet processing hoặc hỗ trợ mọi tính năng từ sơ đồ minh họa**.

### Mỗi lớp ngăn điều gì?

| Lớp | Vai trò thiết kế |
|---|---|
| **Route table** | Quyết định next hop hoặc đích reachable |
| **NACL/subnet ACL** | Lọc gói tại ranh giới subnet theo địa chỉ, hướng, giao thức và cổng |
| **Security group / microsegmentation** | Quyền mạng gần workload và tracking kết nối khi hỗ trợ |
| **NGFW/NVA** | Chính sách tập trung, inspection, egress control và logging theo khả năng |
| **WAF/API gateway** | Kiểm soát HTTP/API, rate limit và các quy tắc ở tầng ứng dụng |
| **IAM/PKI/mTLS** | Danh tính và xác thực user, thiết bị hoặc workload |
| **Application authorization** | Quyết định quyền theo hành động, tenant và đối tượng dữ liệu |

**NACL không phải WAF, IDS/IPS, DDoS shield hay cơ chế Zero Trust đầy đủ.** Nó hạn chế mặt phẳng mạng theo đặc tính gói, không thể bảo đảm một request HTTPS hợp lệ về nghiệp vụ.

## 5. AWS VPC Network ACL: mô hình cần nắm

Trong mô hình AWS VPC NACL phổ biến:

1. NACL gắn với **một hoặc nhiều subnet**, mỗi subnet liên kết với một NACL tại một thời điểm.
2. Có **rule inbound và outbound riêng**.
3. Rule có **number/priority**, chọn theo thứ tự số tăng dần và dùng **rule đầu tiên khớp** cho gói.
4. Rule có hành động **ALLOW** hoặc **DENY**, cùng điều kiện như protocol, CIDR và port/type-code khi hỗ trợ.
5. Nếu không có rule thông thường nào khớp, **rule mặc định đánh dấu \*** có thể từ chối theo mô hình rule set.
6. NACL **stateless**: không tự cho qua gói return traffic chỉ vì request đã được phép.
7. **Default NACL** đi kèm VPC thường được cấu hình cho phép traffic vào/ra, trong khi **custom NACL mới tạo** thường khởi đầu bằng cấu hình từ chối nếu chưa thêm allow rule. Phải kiểm tra **effective config thật**, không tin vào tên “default/custom” như bảo đảm bất biến.

**Ví dụ nền tảng** ở các phần sau mô tả kiểu luật AWS NACL; không sao chép nguyên cho Azure NSG hoặc Google Cloud VPC firewall vì semantics và điểm gắn policy khác.

### First-match và rule number

~~~text
Inbound rule  80: DENY  TCP/443 from 10.0.0.0/8
Inbound rule 100: ALLOW TCP/443 from 10.10.10.0/24
Inbound rule   *: DENY  all remaining traffic

Gói từ 10.10.10.25 tới TCP/443:
  - Khớp rule 80 -> DENY
  - KHÔNG xét tiếp rule 100
~~~

Đây là **shadowed allow rule**: dù có một ALLOW cụ thể hơn, nó vô hiệu nếu một DENY tổng quát hơn đã khớp trước. Vì vậy cần **đọc rule theo priority** và thử chính các luồng được phép/bị từ chối, không chỉ tìm xem trong danh sách có một ALLOW hay chưa.

## 6. Inbound, outbound và cổng tạm thời (ephemeral ports)

Hãy xét **ứng dụng** trong subnet **10.20.20.0/24** nhận TCP request từ client ở **10.10.10.0/24** tới port **8443**. Client chọn source port **53000**.

~~~text
Client                               Application
10.10.10.25:53000                 10.20.20.10:8443
          |                                |
          |  TCP SYN  src 53000 dst 8443   |
          +------------------------------->|
          |                                |
          |  SYN-ACK src 8443 dst 53000    |
          |<-------------------------------+
          |                                |
          |  HTTPS application traffic     |
          |<------------------------------>|
~~~

### Ở subnet của application

| Hướng | Source CIDR | Protocol | **Destination port** | Mục đích |
|---|---|---|---:|---|
| **Inbound** | 10.10.10.0/24 | TCP | **8443** | Nhận request từ client |
| **Outbound** | 10.10.10.0/24 | TCP | **ephemeral của client**, ví dụ 53000 | Trả lời client |

Trong rule outbound, địa chỉ đích là client và **cổng đích là cổng tạm thời của client**, không còn là 8443. Đây là nguyên nhân phổ biến khiến “mở port 8443 cả inbound lẫn outbound” vẫn không đủ cho một NACL stateless.

### Ở subnet của client nếu cũng bị NACL stateless kiểm soát

| Hướng | Counterpart CIDR | Protocol | Destination port | Mục đích |
|---|---|---|---:|---|
| **Outbound** | 10.20.20.0/24 | TCP | 8443 | Gửi request |
| **Inbound** | 10.20.20.0/24 | TCP | ephemeral của client | Nhận response |

**NACL chỉ nhìn gói khi nó đi qua ranh giới subnet áp dụng**, còn rule có hiệu lực phụ thuộc vị trí nguồn/đích, network implementation và tuyến thực. Phải thiết kế **đúng ở mọi subnet có chính sách liên quan**.

## 7. Ephemeral port range không có một giá trị toàn cầu

**Ephemeral ports** thường được client/OS hoặc NAT chọn cho các kết nối ngắn hạn. Phạm vi thực tế thay đổi theo **OS, network stack, cấu hình, NAT gateway, load balancer, hệ thống container và client library**.

Ví dụ các dải có thể gặp trong một số hệ điều hành/cấu hình:

- **32768–60999** là một phạm vi local port thường gặp ở một số Linux, nhưng có thể thay đổi.
- **49152–65535** có thể xuất hiện ở nhiều client hiện đại và trong các trường hợp được cấu hình.
- Một số client hoặc dịch vụ dùng các khoảng khác; không phải mọi hệ thống cloud đều bắt buộc dùng một dải duy nhất.

**Không lấy một khoảng ví dụ rồi kết luận đó là dải bắt buộc của mọi client.** Trước khi triển khai, xác nhận dải có thể dùng của **những hệ thống thực sự là đối tác giao tiếp**, cả sau NAT/load balancer và trên đường failover.

### Ví dụ phạm vi hợp nhất trong lab

Ở một bài kiểm thử giới hạn, nếu nhóm client thực sự dùng các ephemeral ports nằm trong **32768–65535**, NACL có thể cần cho phép cổng đích thuộc khoảng đó cho chiều response theo CIDR đối tác được duyệt.

**Mở cổng ephemeral rộng là tradeoff.** Vì stateless không biết session, rule này có thể cho phép các gói **chưa hề là response** nếu chúng khớp CIDR/protocol/port. Bù lại bằng SG/host firewall stateful, identity, phân đoạn và chính sách đích cụ thể.

## 8. Ví dụ ba tầng: client, application và database

Đây là **mô hình giả định** dùng IP private và cổng được thiết kế để học. Nó không phải cấu hình sẵn của một nhà cung cấp hay hướng dẫn áp dụng ngay vào production.

~~~text
              Client subnet
               10.10.10.0/24
                     |
              TCP dst 8443
                     |
           +-------------------+
           | Application NACL  |
           | 10.20.20.0/24     |
           +-------------------+
                     |
             App 10.20.20.10
                     |
              TCP dst 5432
                     |
           +-------------------+
           | Database NACL     |
           | 10.30.30.0/24     |
           +-------------------+
                     |
             DB 10.30.30.10
~~~

### 8.1. Luồng nghiệp vụ được phép

| Flow | Nguồn | Đích | Port dịch vụ | Kỳ vọng |
|---|---|---|---|---|
| **F1** | Client 10.10.10.0/24 | App 10.20.20.0/24 | TCP 8443 | ALLOW |
| **F2** | App 10.20.20.0/24 | DB 10.30.30.0/24 | TCP 5432 | ALLOW |
| **F3** | Client 10.10.10.0/24 | DB 10.30.30.0/24 | TCP 5432 | DENY |
| **F4** | Guest/Untrusted | App admin port | TCP 22/3389 hoặc port quản trị khác | DENY theo chính sách |
| **F5** | DB 10.30.30.0/24 | Internet không được duyệt | Bất kỳ | DENY |

**Kỳ vọng ALLOW là quyền mạng có giới hạn**, không tự bảo đảm HTTPS, DB credentials hoặc authorization thành công.

### 8.2. NACL cho subnet ứng dụng (mẫu logic AWS-style)

Trong bảng này, **Destination port** là port mà gói đang đi tới; rule **được xét theo thứ tự tăng dần trong từng hướng**.

| Direction | Rule # | Protocol | Counterpart CIDR | Destination port | Action | Lý do |
|---|---:|---|---|---|---|---|
| Inbound | 100 | TCP | **10.10.10.0/24** | **8443** | ALLOW | Client gọi App |
| Inbound | 110 | TCP | **10.30.30.0/24** | **32768–65535** | ALLOW | DB trả lời kết nối do App khởi tạo |
| Inbound | * | ALL | All | All | DENY | Không có rule phù hợp |
| Outbound | 100 | TCP | **10.10.10.0/24** | **32768–65535** | ALLOW | App trả lời client |
| Outbound | 110 | TCP | **10.30.30.0/24** | **5432** | ALLOW | App gọi DB |
| Outbound | * | ALL | All | All | DENY | Không có rule phù hợp |

### 8.3. NACL cho subnet database (mẫu logic)

| Direction | Rule # | Protocol | Counterpart CIDR | Destination port | Action | Lý do |
|---|---:|---|---|---|---|---|
| Inbound | 100 | TCP | **10.20.20.0/24** | **5432** | ALLOW | App gọi DB |
| Inbound | * | ALL | All | All | DENY | Không có rule phù hợp |
| Outbound | 100 | TCP | **10.20.20.0/24** | **32768–65535** | ALLOW | DB trả lời App |
| Outbound | * | ALL | All | All | DENY | Không có rule phù hợp |

**Giả định quan trọng:** client và app sử dụng dải source ephemeral được biểu diễn, ứng dụng dùng đúng 8443, database dùng đúng 5432, traffic không đi qua NAT/LB thay đổi 5-tuple và các luồng DNS, NTP, CA, logging, backup khác **chưa được đưa vào bảng**. Triển khai thật phải bổ sung từng luồng hợp lệ còn thiếu, không dùng allow-all để “cho chạy”.

### 8.4. Đối chiếu security group và ứng dụng

- **App SG**: inbound TCP/8443 chỉ từ nguồn/SG của client đúng policy; egress tới DB TCP/5432 khi cần.
- **DB SG**: inbound TCP/5432 chỉ từ app SG hoặc nguồn được duyệt; egress có kiểm soát.
- **Host firewall**: chỉ lắng nghe dịch vụ trên interface/cổng mong muốn.
- **TLS/mTLS và database credentials**: xác thực client/service, kiểm soát tài khoản và quyền dữ liệu.
- **Application policy**: không tin bất kỳ người nào đến từ subnet client đều có quyền đọc/sửa dữ liệu.

Các SG trên AWS là stateful theo mô hình SG, vì vậy **không cần mở riêng chiều response trong SG như cách phải làm với NACL**; vẫn cần chính sách phù hợp cho những phiên **mới khởi tạo**.

## 9. Đọc packet trace: vì sao rule đảo chiều cổng gây timeout?

Giả sử application server **10.20.20.10:8443** nhận request từ client **10.10.10.25:53000**. NACL inbound cho phép port 8443, nhưng NACL outbound chỉ có rule:

~~~text
Outbound ALLOW to 10.10.10.0/24, TCP destination port 8443
~~~

Response có dạng:

~~~text
Src 10.20.20.10:8443  ->  Dst 10.10.10.25:53000
                                        ^^^^^
                              Destination port là 53000
~~~

Gói **không khớp outbound rule port 8443** vì bộ lọc xét **destination port 53000**, dẫn tới bị chặn nếu không có allow rule khác. Client có thể thấy **TCP connect timeout**, không nhận SYN-ACK, hoặc ứng dụng hiện thông báo “network unreachable/timeout” tùy vị trí/chính sách.

**Một số công cụ chỉ nói “port 8443 mở” mà không chứng minh đường response**. Cần ghi gói theo **5-tuple hai chiều** và đối chiếu rule ở từng ranh giới.

## 10. First-match, rule shadowing và độ ưu tiên

Trong kiểu NACL rule-numbered first-match, khi số nhỏ hơn khớp trước, những rule số lớn hơn không thể “cứu” gói:

~~~text
Inbound:
  100 DENY  TCP 10.0.0.0/8     -> port 8443
  110 ALLOW TCP 10.10.10.0/24 -> port 8443
    * DENY  ALL

Packet 10.10.10.25 -> 10.20.20.10:8443:
  Rule 100 khớp -> DENY
  Rule 110 không được xét
~~~

### Các dạng shadowing hay gặp

| Tình huống | Hệ quả |
|---|---|
| DENY CIDR rộng trước ALLOW CIDR hẹp | ALLOW bị che |
| ALLOW CIDR rộng trước DENY IP cụ thể | DENY bị che, tạo đường cho traffic định chặn |
| Allow-all với rule number thấp | Các rule hạn chế bên dưới không còn tác dụng |
| Rule mới chèn vào vị trí ưu tiên sai | Đường hợp lệ bị gián đoạn hoặc bị mở ngoài ý muốn |
| Chỉ cập nhật IPv4, quên IPv6 | Policy v4/v6 khác nhau |

**Rule number không phải mức độ rủi ro hay nhãn trang trí; nó có thể quyết định hành động cho gói.** Cần dùng diff, lint/analysis và bảng test theo **effective ordered rules**, không chỉ dựa vào danh sách các rule tồn tại.

## 11. Default deny, explicit deny và least privilege

**Default deny** nghĩa traffic không khớp rule allow sẽ bị từ chối theo cách bộ lọc triển khai. **Explicit deny** là một rule chỉ định chặn nguồn/đích/protocol cụ thể. Hai thứ không đồng nhất:

- Nếu đã có **explicit allow rộng ưu tiên cao**, một explicit deny đặt sau có thể không hiệu lực.
- Nếu dựa vào **default deny**, khi thêm allow rule mới phải kiểm tra tác động lên các flow trước đây bị chặn.
- Một deny rule có thể giúp thể hiện ranh giới rõ hơn, nhưng không thể thay **allowlist tối thiểu, security group và IAM**.

### Câu hỏi thiết kế trước khi thêm ALLOW

1. Gói có **nguồn và đích chính xác** là gì sau NAT/LB?
2. Port và protocol là **gói đi hay gói về**?
3. Luồng được phép cho **mọi workload trong subnet** hay chỉ một service? Nếu chỉ một service, cần lớp gần workload.
4. Có **IPv6, UDP, DNS, PMTUD và management traffic** đi cùng không?
5. Có rule ưu tiên cao hơn đã khớp trước không?
6. Khi mở rule, những **đường không mong muốn** nào cũng có thể đi qua?
7. Ai sẽ sở hữu, giám sát và kiểm thử quyền này khi workload thay đổi?

Không đặt **0.0.0.0/0 allow all** chỉ để khắc phục timeout rồi quên thu hồi. Khi có nhu cầu public service, có thể phải cho phép những CIDR rộng tại edge, nhưng backend cần **phân đoạn và policy chặt hơn ở các lớp tiếp theo**.

## 12. DNS và UDP: không có TCP handshake nhưng vẫn có traffic phản hồi

Một ứng dụng cần phân giải tên DNS trước khi gọi API. Với một truy vấn UDP thông thường, client chọn source port tạm thời và gửi tới resolver cổng UDP/53:

~~~text
App 10.20.20.10:54123    -> DNS 10.40.40.53:53    UDP query
App 10.20.20.10:54123    <- DNS 10.40.40.53:53    UDP response

Outbound tại App subnet:
  destination = DNS resolver, port 53/UDP

Inbound tại App subnet:
  source = DNS resolver, destination port 54123/UDP
~~~

### Ma trận ví dụ cho resolver thuộc mạng quản lý

| Direction tại App subnet | Counterpart CIDR | Protocol | Destination port | Dùng cho |
|---|---|---|---|---|
| Outbound | **10.40.40.53/32** | UDP | **53** | DNS query |
| Inbound | **10.40.40.53/32** | UDP | **ephemeral của App** | DNS response |
| Outbound | **10.40.40.53/32** | TCP | **53** | DNS qua TCP nếu client cần |
| Inbound | **10.40.40.53/32** | TCP | **ephemeral của App** | TCP DNS response |

Đây chỉ là logic cho một resolver **được định tuyến tới qua ranh giới áp dụng NACL**. Một số cloud sử dụng **dịch vụ DNS nội bộ/link-local/managed resolver** có cách xử lý đặc biệt; không mặc định NACL chặn được mọi gói tới resolver mặc định của nền tảng. Cần đọc tài liệu provider và thực nghiệm theo đường đi thực.

### Vì sao TCP/53 vẫn quan trọng?

DNS không phải chỉ dùng UDP/53. Những tình huống như response lớn, DNSSEC, chuyển vùng giữa DNS servers hoặc ứng dụng theo thiết kế có thể dùng TCP/53. **Không mở TCP/53 ra mọi mạng để “phòng hờ”**: xác định đúng resolver, nguồn client, đường traffic và nhu cầu. Các cơ chế **DoT (thường TCP/853)**, **DoH (thường HTTPS)** hoặc DNS khác có protocol/port và endpoint riêng; chúng không được tự giải quyết chỉ bằng rule UDP/53.

### Stateless UDP và rủi ro mở rộng

Với UDP, stateless NACL không tự biết datagram nào là trả lời cho query trước. Rule inbound tới ephemeral port **có thể nhận gói khác cùng đặc tính**; security group/host/application phải tiếp tục xác thực nguồn và nội dung phù hợp. Không dùng “gói đến từ resolver IP” làm bằng chứng DNS answer đáng tin khi threat model còn có spoofing hoặc thiết bị bị chiếm.

## 13. ICMP, ICMPv6, Path MTU Discovery và reachability

Khi thiết kế lọc IP, đội vận hành thường chỉ nghĩ đến TCP/UDP. Tuy nhiên, **ICMP/ICMPv6** chứa những thông báo lỗi hoặc tín hiệu điều khiển cần cho hoạt động mạng.

### Path MTU Discovery (PMTUD)

Khi một gói lớn không thể đi qua đường có MTU nhỏ hơn, mạng có thể phải gửi thông tin về việc **gói quá lớn** để nguồn điều chỉnh kích thước. **IPv4 ICMP Destination Unreachable/Fragmentation Needed** và **IPv6 ICMPv6 Packet Too Big** là các ví dụ quan trọng trong cơ chế PMTUD theo ngữ cảnh giao thức.

~~~text
App -> [VPN / overlay path with smaller MTU] -> Service
            |
       Packet too large
            |
      ICMP/ICMPv6 feedback
            |
       App adjusts size

Nếu feedback cần thiết bị chặn:
  gói nhỏ hoạt động;
  kết nối/HTTPS upload/gRPC message lớn có thể timeout.
~~~

**Không chặn toàn bộ ICMP/ICMPv6** chỉ vì không cần ping. Phải phân loại thông báo cần cho mạng hoạt động, chính sách provider và bề mặt rủi ro; chỉ mở **đúng loại/code/nguồn** khi nền tảng cho phép và việc lọc thực sự nằm trên path.

### IPv6 có thêm yêu cầu riêng

- **IPv6 không dùng broadcast** theo kiểu IPv4; nhiều chức năng link-local dựa vào ICMPv6.
- Neighbor Discovery, Router Advertisement và một số cơ chế điều khiển **có thể được xử lý ở lớp virtual networking do cloud provider quản lý**.
- Không giả định một rule NACL có thể hoặc nên lọc toàn bộ traffic nền tảng đó.
- Khi dual-stack, cần kiểm tra **IPv6 CIDR, route ::/0, SG/ACL IPv6, security group behavior và cả IPv6 return path**.

**Các rule IPv4 không tự áp dụng cho IPv6.** Một dịch vụ có record AAAA và địa chỉ IPv6 public có thể reachable theo đường khác IPv4 nếu tổ chức không có chính sách tương ứng.

## 14. NAT làm thay đổi những gì NACL quan sát?

**Network Address Translation (NAT)** có thể thay đổi địa chỉ IP nguồn/đích và, trong nhiều tình huống PAT, cả port. Vì vậy rule phải dựa trên **địa chỉ và cổng thực tại ranh giới mà NACL xét**, không nhất thiết là danh tính ban đầu của client.

~~~text
Private App:   10.20.20.10:54000
      |
      v
NAT mapping:   public-address:62000   (ví dụ)
      |
      v
External API:  198.51.100.30:443

Return gói từ API:
  198.51.100.30:443 -> NAT public-address:62000

Sau dịch ngược:
  198.51.100.30:443 -> 10.20.20.10:54000
~~~

Đây là mô hình NAT tổng quát; **port và địa chỉ dịch thực tế do thiết bị/nền tảng quyết định**, không luôn giống ví dụ.

### Cần ghi rõ trên sơ đồ

1. NAT thực hiện ở đâu: gateway, firewall, load balancer, public/private endpoint?
2. NACL đang bảo vệ subnet nào: workload subnet, NAT subnet, subnet gateway?
3. Ở mỗi ranh giới, gói có **source/destination IP và destination port** nào?
4. Cần rule nào cho request và response **trước/sau translation**?
5. Return traffic được định tuyến lại qua **cùng thiết bị stateful NAT** hay qua path khác?

**Không tự áp rule source CIDR của Internet client gốc lên hop đã qua SNAT** nếu NACL lúc đó chỉ thấy IP proxy/NAT. Tương tự, đừng mặc định source IP luôn được bảo toàn qua một loại load balancer — cần kiểm tra loại listener, target, network mode và kiến trúc cụ thể.

## 15. Load balancer, CDN/WAF và điểm kết thúc TLS

Một website cloud có thể có sơ đồ:

~~~text
Internet Client
       |
     CDN/WAF
       |
  Public Load Balancer Subnet
       |          [NACL-LB]
       v
  Private Application Subnet
       |          [NACL-APP] + SG
       v
    Backend API
       |
  Database Subnet
                  [NACL-DB] + SG
~~~

### Những sai lầm thường gặp

- Cho phép **source IP của browser** ở App subnet khi backend thực tế chỉ nhận kết nối từ **LB nodes/proxy**.
- Chỉ mở inbound 443 cho LB mà quên outbound response tới cổng client hoặc các health-check/management flows theo cấu hình.
- Cho phép LB → App tới port 443 nhưng upstream app thật sự lắng nghe **8443/8080**, hoặc không phân biệt TLS termination với TCP pass-through.
- Chỉ xét một AZ/region, bỏ node/đường HA khác có CIDR/port/source IP khác.
- Dùng **X-Forwarded-For** từ HTTP header làm source IP của rule NACL; NACL xử lý **IP header**, không đọc header ứng dụng.

### TLS termination làm thay đổi trust boundary

~~~text
Browser === TLS A ===> CDN/LB === TLS B ===> App
                          |
                      Proxy có thể thấy
                      HTTP sau TLS A
~~~

NACL không đánh giá **certificate chain, SNI match, mTLS client identity hay HTTP authorization**. Một đoạn TLS giữa client và LB được bảo vệ không chứng minh LB → App cũng được mã hóa; cần kiểm tra từng TLS hop, SG và network path.

### Load balancer health checks

Health check có thể bắt đầu từ các địa chỉ/đường được nhà cung cấp quản lý và yêu cầu port/protocol riêng. Nếu NACL chặn health-check traffic, load balancer có thể đánh dấu target **unhealthy** dù ứng dụng phục vụ khi được gọi trực tiếp. Không mở toàn bộ CIDR để chữa lỗi trước khi xác định **đúng health-check nguồn/port, route và rule**.

## 16. Cross-subnet, peering, transit và VPN hybrid

Trong hybrid cloud, packet đi từ on-premises sang cloud có thể qua firewall, IPsec VPN, transit hub, route table và NACL của nhiều subnet.

~~~text
On-prem client
    |
  On-prem Firewall
    |
    | VPN/IPsec protected path
    v
Cloud VPN gateway -> Transit/Hub routing
    |
    v
Application subnet NACL
    |
    v
App SG / workload
    |
    v
Application
~~~

### Những điều cần phân biệt

| Vấn đề | Điểm cần kiểm chứng |
|---|---|
| **VPN SA** | Đường IPsec được thiết lập và traffic selectors phù hợp chưa? |
| **BGP/route** | Prefix tới app và return route đã được chọn/đưa vào forwarding table chưa? |
| **Firewall on-prem** | Stateful session có đi và về qua cùng boundary cần thiết không? |
| **Cloud NACL** | Inbound port dịch vụ và outbound ephemeral return có hợp lệ không? |
| **Cloud SG** | Source identity/CIDR và service port đã được cấp quyền chưa? |
| **NAT/translation** | NACL đang nhìn nguồn trước hay sau NAT? |
| **DNS** | Client thực sự resolve tới IP private đúng hay public proxy? |
| **Application identity** | TLS/mTLS, service principal và quyền dữ liệu có đúng không? |

**VPN tunnel UP và route BGP Established không chứng minh ứng dụng reachable.** Gói vẫn có thể bị NACL, SG, host firewall, DNS, LB hoặc ứng dụng từ chối.

### Peering không có nghĩa transitive routing

Nhiều cloud có quy định cụ thể về khả năng truyền traffic qua peering/transit. **Không tự coi mọi mạng cùng nối tới hub đều có quyền kết nối lẫn nhau.** NACL là một điểm chặn nhưng phải kết hợp route propagation, firewall/SG và ngăn route leak giữa **Dev/Test/Prod/Management/Guest**.

### NACL có lọc traffic trong cùng subnet không?

Với mô hình AWS NACL gắn **ranh giới subnet**, traffic giữa các instance **cùng subnet** không phải luôn đi qua đường kiểm soát NACL như một gói đi vào/ra subnet. Vì vậy không được dùng NACL làm **cơ chế phân đoạn giữa hai workload cùng subnet**. Cần SG, host firewall, workload identity hoặc microsegmentation theo kiến trúc.

## 17. Không đồng nhất NACL giữa AWS, Azure và Google Cloud

Tên sản phẩm dễ gây nhầm trong thiết kế multi-cloud hoặc khi di chuyển workload.

| Nền tảng/cơ chế | Điểm nổi bật | Điều phải tránh suy diễn |
|---|---|---|
| **AWS VPC Network ACL** | Subnet-level, **stateless**, inbound/outbound rules, numbered first-match, allow/deny | Không tự cho return traffic; không phải SG |
| **AWS Security Group** | Gần workload/ENI, **stateful** theo semantics SG, rule cho phép | Không thay authorization và không có deny kiểu NACL |
| **AWS Network Firewall stateless rule groups** | Thành phần lọc stateless theo kiến trúc firewall chuyên dụng | Không đồng nhất scope, thứ tự, traffic action với VPC NACL |
| **Azure Network Security Group (NSG)** | Chính sách theo rule/priority tại subnet/NIC, **stateful flow handling** | Không tự yêu cầu ephemeral return rule giống AWS NACL |
| **Google Cloud VPC firewall rules** | Chính sách firewall gắn với mạng/tài nguyên theo mô hình provider, **stateful** | Không đồng nhất điểm áp, priority và identity với NACL |
| **Kubernetes NetworkPolicy** | Ý định điều khiển ingress/egress theo pod/namespace/IP/port do CNI triển khai | Không phải AWS subnet NACL; hành vi cần kiểm tra CNI |

**Azure NSG** có rule inbound/outbound và priority, nhưng **đây không phải bằng chứng nó stateless**. **Google Cloud VPC firewall** có cách áp rule theo direction, priority, target và những policy cấp bậc khác tùy mô hình, không phải clone của AWS NACL. Khi chuyển workload, cần viết lại **policy intent và test matrix**, không chỉ dịch tên resource.

### Shared responsibility

Cloud provider chịu trách nhiệm những phần hạ tầng theo mô hình chia sẻ của sản phẩm; khách hàng phải chịu trách nhiệm **định nghĩa chính sách, quản lý tài khoản, cấu hình CIDR/rule, phân quyền tài nguyên, observability và kiểm thử** theo phạm vi của mình. Các đặc tính cụ thể có thể khác nhau theo dịch vụ managed.

## 18. Bảo vệ IPv4 và IPv6 đồng thời

Một tài sản dual-stack có thể có:

~~~text
IPv4: 10.20.20.10       IPv4 CIDR policy
IPv6: 2001:db8:20::10  IPv6 CIDR policy (documentation prefix)
~~~

**2001:db8::/32** dành cho ví dụ tài liệu, không phải prefix để triển khai. Nếu tài nguyên có địa chỉ IPv6 thật, hãy thiết kế riêng:

- Inbound/Outbound IPv6 CIDR và port phù hợp.
- Route tới IPv6 gateway/egress mechanism theo nền tảng.
- Security group/firewall policy cho cả IPv6.
- ICMPv6/PMTUD cần thiết theo đường và tính năng provider.
- DNS AAAA và client Happy Eyeballs có thể chọn IPv6 khi v4 bị chặn.
- Log/alert cho **v6 bypass** nếu chỉ kiểm tra v4 trong staging.

**IPv4 default route 0.0.0.0/0 khác IPv6 ::/0.** Không dùng một rule v4 để khẳng định đóng toàn bộ Internet ingress/egress. Khi bật IPv6 mới hoặc thêm AAAA record, cần chạy lại policy test theo cả hai address family.

## 19. NACL không thay thế identity-based security hay anti-DDoS

Stateless ACL có ích để giảm **bề mặt tiếp cận gói IP**, nhưng không biết ai đang dùng token, chứng chỉ hay quyền tenant:

| Nhu cầu | NACL làm được gì? | Cần lớp bổ trợ nào? |
|---|---|---|
| Chỉ cho App subnet gọi DB port | Lọc CIDR, TCP port theo direction | SG/host firewall, DB auth, TLS/mTLS |
| Phân quyền API theo user/tenant | Không đọc được identity/claim | API gateway, OAuth/JWT, application authorization |
| Phát hiện SQL injection | Không hiểu nội dung API/DB query | WAF/app validation và logging |
| Chống DDoS quy mô lớn | Có thể chặn một số traffic tại ranh giới áp dụng | Provider anti-DDoS, edge capacity, rate limit, WAF |
| Ngăn nguồn không tin cậy reach subnet | Có thể chặn dựa trên CIDR/protocol | Routing/SG, anti-spoofing theo platform |
| Phân đoạn hai pod cùng subnet | Không nên xem là ranh giới đủ | SG, CNI network policy, service identity |
| Ghi danh tính người dùng cho request | Không trực tiếp | IAM, app logs, trace và SIEM |

**Chặn gói tại NACL không ngăn traffic tiêu thụ băng thông hoặc năng lực ở mọi lớp phía trước**. Vì thế NACL không phải giải pháp đủ cho volumetric DDoS. Cũng không được coi CIDR nguồn như danh tính mạnh: NAT/proxy, thay đổi IP và tình huống spoofing làm giảm giá trị của nhận diện dựa duy nhất trên IP.

## 20. Thiết kế rule từ flow inventory, không từ phỏng đoán port

Trước khi tạo NACL, hãy liệt kê **luồng ứng dụng thật**:

1. **Luồng khởi tạo:** service nào chủ động mở kết nối tới service nào?
2. **Source/Destination CIDR:** bao gồm IP sau NAT/proxy và CIDR các subnet HA.
3. **Transport/protocol/port:** TCP, UDP, ICMP/ICMPv6; port đích của request.
4. **Return traffic:** port đích của response, ephemeral policy, route chiều về.
5. **Cloud control dependencies:** DNS, NTP, CA/PKI, metadata/management, telemetry, backup nếu có đường cần áp ACL.
6. **Security boundary:** NACL, SG, firewall, application IAM đang kiểm soát phần nào?
7. **Owner và mục đích:** tài sản/nhóm nào cần luồng, vì sao và tới khi nào?
8. **Khả năng kiểm chứng:** log, synthetic request, negative test và cách rollback.

### Bảng nguồn sự thật mẫu

| Flow ID | Initiator | Target | Transport | Service port | Return ephemeral | Owner | Boundary |
|---|---|---|---|---|---|---|---|
| APP-API-01 | Client subnet | App subnet | TCP | 8443 | Client OS range | App team | NACL + SG |
| APP-DB-02 | App subnet | DB subnet | TCP | 5432 | App OS range | Data platform | NACL + DB SG |
| APP-DNS-03 | App subnet | Resolver | UDP/TCP | 53 | App client range | Infra/DNS | Path-dependent |
| APP-OBS-04 | App subnet | Logging collector | TCP | 443 | App client range | SRE | NACL + SG/egress |
| APP-PKI-05 | App subnet | Certificate/CA service | TCP | theo service | App client range | PKI owner | Boundary-dependent |

Các luồng trên chỉ là ví dụ. **Không ngầm mở DNS/NTP/PKI tới toàn Internet**: phải xác định dịch vụ thực, phương thức managed cloud, endpoint và route.

### Tạo quy tắc từ flow

Đối với một luồng TCP/UDP do A khởi tạo tới B, lập ít nhất:

~~~text
REQUEST:
  A subnet OUTBOUND -> B service destination port
  B subnet INBOUND  <- A source CIDR, service destination port

RESPONSE (stateless):
  B subnet OUTBOUND -> A ephemeral destination port
  A subnet INBOUND  <- B source CIDR, ephemeral destination port

Then verify:
  routes, NAT/proxy changes, SG/host policy, TLS/application
~~~

Không phải mọi đường đều vượt cả hai subnet ACL (ví dụ DNS nội bộ managed hoặc cùng subnet). Quy tắc này là **mô hình phân tích hai chiều**, cần thay bằng **packet path thực tế** trước khi tạo cấu hình.

## 21. Policy as Code và quản trị thay đổi NACL

NACL thường được quản lý tốt hơn khi **rule intent, người sở hữu, lý do cấp quyền và cấu hình thực tế** nằm trong quy trình quản lý hạ tầng. Có thể dùng Infrastructure as Code (IaC) và policy-as-code để kiểm soát sự nhất quán, nhưng **một file IaC đúng cú pháp không chứng minh policy an toàn hoặc traffic hoạt động**.

### Ví dụ cấu trúc policy mô tả, không chạy trực tiếp

~~~yaml
policy_id: app-subnet-nacl
environment: staging
subnet_cidr: 10.20.20.0/24
owner: cloud-network-team
rule_model: stateless-first-match
rules:
  inbound:
    - number: 100
      action: allow
      protocol: tcp
      source_cidr: 10.10.10.0/24
      destination_port: 8443
      purpose: "approved-client-to-app"
    - number: 110
      action: allow
      protocol: tcp
      source_cidr: 10.30.30.0/24
      destination_port_range: "32768-65535"
      purpose: "db-response-to-app"
  outbound:
    - number: 100
      action: allow
      protocol: tcp
      destination_cidr: 10.10.10.0/24
      destination_port_range: "32768-65535"
      purpose: "app-response-to-client"
    - number: 110
      action: allow
      protocol: tcp
      destination_cidr: 10.30.30.0/24
      destination_port: 5432
      purpose: "app-to-database"
default_action: deny
~~~

Đây là **schema học tập**, không phải Terraform, CloudFormation hay cấu hình import được vào AWS. Nếu hiện thực bằng IaC cụ thể, phải map đúng **field, provider constraints, protocol/type-code, IPv4/IPv6 và thứ tự rule**.

### Lint/validation nên kiểm tra

| Kiểm tra tự động | Mục đích |
|---|---|
| **Rule number uniqueness** | Tránh trùng ưu tiên ở cùng direction |
| **Rule reachability** | Phát hiện ALLOW/DENY bị rule trước che |
| **CIDR overlap analysis** | Nhận ra allow rộng hoặc vùng giao nhau không chủ ý |
| **Ephemeral return matrix** | Kiểm tra request được phép có response path được thiết kế |
| **IPv4/IPv6 policy parity** | Không bỏ sót một address family |
| **Default rule posture** | Xác định traffic không khớp sẽ bị chặn |
| **Rule owner/expiry** | Phát hiện quyền tạm thời quá hạn, thiếu người chịu trách nhiệm |
| **Diff against actual state** | Phát hiện thao tác console/manual drift |
| **Negative test coverage** | Chứng minh đường không mong muốn vẫn bị từ chối |

**Một số thay đổi rule có thể tác động traffic ngay khi API chấp nhận**, trước khi toàn bộ phép kiểm thử hoàn tất. Đừng giả định mọi bước cập nhật nhiều rule diễn ra **nguyên tử** theo ý định nếu nhà cung cấp không cam kết. Cần triển khai thứ tự an toàn, canary/chia nhỏ vùng ảnh hưởng khi khả thi, và kế hoạch phục hồi.

## 22. Quản lý drift, owner và quyền tạm thời

**Configuration drift** xảy ra khi rule hiện hành khác **desired state** đã được phê duyệt, ví dụ kỹ sư mở tạm UDP/53 từ all CIDRs rồi quên thu hồi.

~~~text
Approved security intent (desired)
                 |
                 v
       IaC / Change management
                 |
                 v
        Cloud NACL actual rules
                 |
            Read-only diff
                 |
          Unexpected change?
              /      \
            No        Yes
            |          |
         Monitor     Verify owner/ticket
                       |
                Review risk + revert plan
~~~

### Nguyên tắc quản trị

- Mọi ALLOW/DENY thay đổi phải có **service owner, mục đích và tài liệu nguồn–đích**.
- Quyền cấp tạm có **expiry/review date**, không phải allow-all không thời hạn.
- Rà soát khi **thay CIDR, thêm subnet, bật IPv6, mở VPN/peering, đổi LB hoặc cloud region**.
- Đặt quyền quản lý NACL theo **least privilege**; không cho app operator thay policy toàn bộ VPC khi không cần.
- Lưu audit logs của cloud API/console và liên kết với change ticket.
- Khi có drift bất ngờ, xác minh đó có phải **sửa chữa sự cố đang được phê duyệt** trước khi tự động rollback.

**Không để bot tự xóa rule nguy hiểm trong mọi trường hợp** nếu chưa biết nó đang bảo vệ một luồng ứng cứu quan trọng. Auto-remediation có thể hữu ích khi policy và phạm vi đủ rõ, nhưng cần xác định owner, blast radius và rollback.

## 23. Flow logs và telemetry: chứng cứ nào đáng tin?

Khi gói bị chặn, mạng cloud có thể có telemetry như **flow logs**, firewall logs, route analytics, traffic mirroring và metric counters tùy sản phẩm. Trong AWS, **VPC Flow Logs** có thể ghi nhận ACCEPT/REJECT cho một số traffic quan sát được, nhưng **không nên suy một bản ghi REJECT tự chỉ rõ rule number của NACL**.

### Ví dụ log giả lập

~~~text
timestamp=2026-11-28T12:00:00Z
interface=eni-example
srcaddr=10.20.20.10
srcport=8443
dstaddr=10.10.10.25
dstport=53000
protocol=6
action=REJECT
bytes=0
~~~

**Đây là log học thuật, không phải format chuẩn đầy đủ của một provider.** Trong một số hệ thống flow logs, các trường **bytes/packets có quy tắc riêng** và không được hiểu là packet capture nguyên vẹn. Với những bản ghi thực tế, thời gian, aggregation window, sampling/collection status và giao diện quan sát đều ảnh hưởng kết luận.

### Những giới hạn phải nhớ

1. **ACCEPT** ở một điểm không bảo đảm ứng dụng đã nhận request hoặc client có quyền.
2. **REJECT** có thể xuất phát từ **SG hoặc NACL** tùy nguồn log và cách hạ tầng ghi nhận; phải đối chiếu effective rules.
3. **Không thấy log** không chứng minh không có gói: có thể do collection lag, sampling, path sai, interface không được bật hoặc traffic không thuộc phạm vi ghi log.
4. Flow log thường **không chứa payload HTTP/TLS** và không thể chỉ ra quyền tenant hoặc lý do business authorization.
5. Gói đi qua **NAT/proxy** có source/destination khác nhau theo điểm quan sát.
6. Những traffic cloud-managed đặc biệt có thể không xuất hiện giống traffic application thông thường.

### Ghép bằng chứng đúng lớp

| Nguồn | Bằng chứng |
|---|---|
| **Route/FIB** | Nguồn có thể đưa gói tới đúng next hop không? |
| **NACL/SG effective config** | Gói cụ thể có khớp ALLOW hay DENY theo hướng/priority? |
| **Flow logs/packet trace có phép** | Có dấu hiệu gói tới/đi, 5-tuple và action gì? |
| **Load balancer** | Listener/target/health check có nhận traffic không? |
| **TLS/application** | Handshake/call có thành công, status nào? |
| **IAM/DB auth** | Caller được nhận diện và cấp quyền đúng không? |

**Một RCA (root-cause analysis) tốt xác định chính sách cụ thể làm gói bị chặn, không chỉ ghi “network issue”.**

## 24. Runbook khi ứng dụng timeout nghi do NACL

### Giai đoạn 1 — Xác nhận request và path

1. Xác nhận **nguồn, đích, port dịch vụ, transport, thời điểm, region, subnet và network interface**.
2. Ghi **IP thực tế sau DNS, NAT, CDN/LB hoặc VPN**, không chỉ tên miền.
3. Xác định request và response **5-tuple** ở những điểm quan trọng.
4. Kiểm tra route tới đích và **return route**; xét peering, transit, VPN, asymmetric routing.
5. Phân biệt lỗi **DNS, connect timeout, TLS handshake, HTTP status, application timeout**.

### Giai đoạn 2 — Đọc đúng NACL rule

~~~text
Traffic fails
     |
     +-- Check packet path and affected subnet
     |
     +-- Check applicable INBOUND rules
     |     first matching numbered rule?
     |
     +-- Check applicable OUTBOUND rules
     |     response destination port = ephemeral?
     |
     +-- Check any second subnet NACL
     |
     +-- Check SG/host firewall, route, NAT and TLS/app
     |
     +-- Correlate flow logs and approved connection test
~~~

**Không được chỉ nhìn một rule ALLOW có tồn tại.** Phải xem rule nào **khớp đầu tiên**, tại **đúng subnet** và **đúng hướng**.

### Giai đoạn 3 — Phân biệt lỗi do NACL với lỗi khác

| Dấu hiệu | Khả năng cần xem |
|---|---|
| Inbound request được ghi ACCEPT, response REJECT ở subnet | Outbound ephemeral NACL/SG hoặc policy liên quan |
| Gói không tới subnet đích | Routing, peering, VPN, LB, DNS hoặc upstream firewall |
| NACL allow hai chiều, SG vẫn REJECT | SG rule/connection tracking/endpoint |
| TCP kết nối được, HTTPS lỗi | Certificate/trust/SNI/TLS hoặc application |
| Chỉ gói lớn lỗi | PMTUD/ICMP, MTU VPN/overlay và app limits |
| Chỉ IPv6 lỗi | AAAA, v6 route/ACL/SG hoặc IPv6 gateway |
| Chỉ AZ/region B lỗi | NACL association, CIDR/route hoặc LB ở vùng đó |
| Ping không trả lời nhưng HTTPS thành công | ICMP policy có thể khác TCP; không tự là outage |

### Giai đoạn 4 — Thay đổi có kiểm soát

1. Tính **quy tắc tối thiểu cần thêm/sửa**, xác nhận source CIDR và port range.
2. Xem **rule precedence** để không tạo allow bị shadowed hoặc deny bị bỏ qua.
3. Đánh giá **tác động đến những workload khác cùng subnet**, không chỉ host đang lỗi.
4. Có owner, change ticket, thời gian triển khai, rollback và người kiểm tra.
5. Nếu cần chữa cháy, ưu tiên **rule hẹp có thời hạn** thay vì allow-all không kiểm soát.
6. Sau khi áp dụng, xác minh **ALLOW flows** hoạt động và **DENY flows** vẫn bị chặn.

### Giai đoạn 5 — Hậu kiểm

Ghi rule diff, subnet association, thời điểm, phản hồi của ứng dụng, flow logs, tác động tới IPv6/DNS/monitoring, nguyên nhân gốc, những chính sách cần thêm test và việc thu hồi quyền tạm. **Khôi phục được kết nối chưa đủ nếu thay đổi đã vô tình mở DB hoặc management cho nguồn không được phép.**

## 25. Case study 1: HTTPS timeout do thiếu outbound ephemeral

**Bối cảnh giả định:** App đặt tại **10.20.20.10:8443**. Client tại **10.10.10.25:53000** truy cập bằng HTTPS qua mạng private; DNS và route đúng, NACL inbound cho phép cổng 8443, SG cũng cho phép.

### Hiện tượng

~~~text
Inbound to App subnet:
  source 10.10.10.25:53000 -> destination 10.20.20.10:8443
  NACL result: ALLOW

Outbound from App subnet:
  source 10.20.20.10:8443 -> destination 10.10.10.25:53000
  Current NACL allows only destination TCP/8443
  NACL result: DENY (no matching allow for dst port 53000)
~~~

**Kết luận ban đầu:** lưu lượng request vào được ranh giới subnet nhưng response không khớp rule outbound hiện hành. Client có thể thấy TCP connect timeout hoặc TLS không hoàn tất. Không cần mở source từ Internet hoặc thay đổi certificate để sửa lỗi này.

### Phương án sửa đúng

1. Xác nhận dải ephemeral **thật** của nhóm client và CIDR tương ứng.
2. Thêm/sửa outbound ALLOW theo **CIDR đối tác** và **destination ephemeral range**, ưu tiên hợp lệ trong ordered rule set.
3. Xác minh ở client subnet có rule inbound cho response nếu NACL stateless của subnet đó có thể chặn.
4. Không bỏ qua SG, route, NAT hoặc application TLS verification.
5. Test lại HTTPS hợp lệ và thử từ mạng khác không được phép để xác nhận vẫn DENY.

### Bài học

**Mở cùng một service port ở inbound và outbound không mô tả một kết nối hai chiều.** Gói response dùng destination ephemeral port của bên khởi tạo; phân tích bằng 5-tuple giải quyết nhầm lẫn này.

## 26. Case study 2: rule DENY ưu tiên cao che ALLOW

**Bối cảnh giả định:** Một subnet ứng dụng chỉ cho phép client CIDR **10.10.10.0/24** tới TCP/8443. Trong một đợt tăng cường bảo vệ, đội vận hành thêm DENY cho một dải mạng rộng trước rule allow.

~~~text
Inbound:
  80  DENY  TCP/8443 from 10.0.0.0/8
  100 ALLOW TCP/8443 from 10.10.10.0/24
  *   DENY  all

Client packet:
  src 10.10.10.25 -> dst 10.20.20.10:8443

First matching rule = 80 -> DENY
~~~

### Vì sao dễ bỏ sót?

- Giao diện hiển thị vẫn có rule **ALLOW từ client subnet** nên người đọc lướt nghĩ đúng.
- Dashboard application báo timeout và DB không có log request.
- Một số subnet khác không áp cùng NACL nên người dùng chỉ lỗi ở một vùng.

### Cách xử lý

1. Đọc effective NACL **theo số rule**, xác minh subnet association.
2. Tìm CIDR overlap và những rule **không bao giờ có thể được áp dụng** vì đã bị che.
3. Thiết kế lại thứ tự theo chính sách được duyệt, không xóa mọi DENY để cho phép dịch vụ.
4. Chạy cả **positive tests** cho client CIDR và **negative tests** cho nguồn nằm trong dải muốn chặn.
5. Thêm policy-as-code test phát hiện shadowing/over-broad ALLOW trước deploy.

**Bài học:** Rule precedence là một phần của **effective security posture**, không phải chỉ là chi tiết hiển thị.

## 27. Case study 3: chuyển ứng dụng sang đa cloud, nhầm tính stateful

**Bối cảnh giả định:** Đội phát triển có ứng dụng chạy trên Azure, nơi một NSG được cấu hình cho phép luồng TCP client → app. Khi chuyển cùng ứng dụng sang AWS, nhóm sao chép ý tưởng inbound allow vào NACL stateless mà không thiết kế outbound ephemeral.

### Những khác biệt xuất hiện

| Thành phần | Môi trường ban đầu | Môi trường mới |
|---|---|---|
| Network policy | Azure NSG, stateful flow handling | AWS VPC NACL, stateless |
| Inbound | Allow client → TCP/443 | Allow client → TCP/443 |
| Return traffic | Được đánh giá theo trạng thái flow của NSG | Cần outbound rule phù hợp ở NACL |
| Workload-level policy | NSG/NIC/subnet theo kiến trúc | SG stateful gắn với workload/ENI |
| Rule priority/semantics | Theo thiết kế NSG | Numbered first-match NACL |

### Sai lầm chính

Nhóm lấy **ngữ nghĩa của resource cũ** để áp vào một resource có **cùng vai trò chung nhưng cách quyết định khác**. Điều cần chuyển là **security intent**: “client được phép gọi HTTPS và không ai khác truy cập DB”, rồi tạo rule tương ứng với mỗi nhà cung cấp.

### Kiểm thử sau migration

1. Kiểm tra App subnet NACL inbound/outbound đúng port.
2. Xác minh source CIDR sau LB/NAT, return path.
3. Kiểm tra SG stateful và host/application auth.
4. Test IPv4/IPv6, DNS và health-check.
5. Test nguồn không được cấp quyền và quyền DB/management.

**Bài học:** Network policy là một **hợp đồng bảo mật và kết nối**; dịch cú pháp cloud mà không dịch semantics dễ tạo outage hoặc quyền thừa.

## 28. Bài thực hành an toàn: dựng ma trận gói và kiểm tra rule

Mục tiêu bài lab là **chứng minh được quyết định NACL cho một packet hai chiều** từ dữ liệu giả lập hoặc môi trường lab/staging đã phê duyệt. Không thay đổi production NACL, không quét IP ngoài phạm vi và không dùng lưu lượng phá hoại.

### Bước 1 — Viết flow cần cho phép

~~~text
Environment:        isolated lab / staging
Client subnet:      10.10.10.0/24
Application subnet: 10.20.20.0/24
Database subnet:    10.30.30.0/24
Client:             10.10.10.25:53000
App:                10.20.20.10:8443
DB:                 10.30.30.10:5432

Expected:
  Client -> App TCP/8443: ALLOW
  App -> DB TCP/5432: ALLOW
  Client -> DB TCP/5432: DENY
~~~

### Bước 2 — Tự tính hướng gói request/response

| Gói | Source IP:port | Destination IP:port | NACL/Direction cần kiểm tra |
|---|---|---|---|
| P1 request | **10.10.10.25:53000** | **10.20.20.10:8443** | Client OUT; App IN |
| P2 response | **10.20.20.10:8443** | **10.10.10.25:53000** | App OUT; Client IN |
| P3 DB request | **10.20.20.10:54001** | **10.30.30.10:5432** | App OUT; DB IN |
| P4 DB response | **10.30.30.10:5432** | **10.20.20.10:54001** | DB OUT; App IN |
| P5 forbidden | **10.10.10.25:53002** | **10.30.30.10:5432** | Client OUT; DB IN |

Nếu giả định **client subnet NACL custom cũng default deny**, bài lab phải có đầy đủ rule Client OUT/IN cho P1/P2 trước khi kiểm thử E2E. **Không được kết luận App NACL đã đúng cho toàn luồng** chỉ vì P1/P2 đi qua App.

### Bước 3 — Tự áp first-match cho một packet

~~~text
Packet:
  source       = 10.10.10.25
  destination  = 10.20.20.10
  protocol     = TCP
  dest port    = 8443
  direction    = App subnet INBOUND

Rules:
  80  DENY  10.10.10.0/25 TCP 8443
  100 ALLOW 10.10.10.0/24 TCP 8443
  *   DENY  all

10.10.10.25 thuộc 10.10.10.0/25
  => first match = 80, result DENY

Đổi nguồn thành 10.10.10.200:
  => không khớp 10.10.10.0/25
  => khớp 10.10.10.0/24 ở rule 100, result ALLOW
~~~

**Bài thử này không chạy bất kỳ packet nào thật**. Nó kiểm tra kiến thức về **CIDR containment và rule priority**, giúp phát hiện tình huống ALLOW quá rộng hoặc DENY bị che trước khi deploy.

### Bước 4 — Đọc NACL qua cloud API có quyền (tùy chọn)

Với tài khoản AWS **có quyền đọc** trên lab/staging, CLI có thể giúp xem effective config để so sánh với bài tập:

~~~bash
# Chỉ là cú pháp ví dụ; thay ID bằng NACL trong tài khoản lab có phép.
aws ec2 describe-network-acls \
  --network-acl-ids acl-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Đây là lệnh **describe/read-only**, không chỉnh sửa rule. Chạy lệnh cần AWS CLI, cấu hình authentication/region và quyền IAM phù hợp. Kết quả cần được kiểm tra các trường như **Associations, Entries, RuleNumber, Egress, Protocol, CidrBlock/Ipv6CidrBlock, RuleAction và PortRange** khi áp dụng.

Nếu NACL được gắn nhiều subnet, hãy xác nhận **association** đúng với subnet cần thử. Đọc rule của một NACL có cùng tên nhưng không gắn subnet liên quan sẽ dẫn đến kết luận sai.

### Bước 5 — Kiểm thử kết nối nếu môi trường cho phép

Chỉ dùng một số phép thử **đến đích lab/staging được chủ dịch vụ phê duyệt**, ví dụ một HTTPS health endpoint. Có thể dùng **curl** để phân biệt connect failure với application response:

~~~bash
# Hostname giả định; không chạy tới domain ngoài phạm vi.
curl --connect-timeout 2 --max-time 5 \
  --silent --show-error --output /dev/null \
  --write-out 'connect=%{time_connect} total=%{time_total} http=%{http_code}\n' \
  https://app.example.test/health
~~~

**app.example.test** là tên tài liệu. Đừng dùng **curl -k/--insecure** để bỏ qua certificate verification nếu bài kiểm thử cần xác nhận TLS end-to-end. Lệnh curl chủ yếu giúp quan sát kết nối/app, **không tự nói NACL rule nào chặn gói**.

### Bước 6 — Ghi biên bản

~~~text
Test ID:            NACL-LAB-01
Environment:        lab/staging, owner
Date/timezone:      timestamp
Cloud/provider:     provider and resource type
Network path:       source, destination, subnet, route, NAT/LB
Source IP:port:     observed or hypothetical
Destination IP:port: observed or hypothetical
Protocol/family:    TCP/UDP/ICMP, IPv4/IPv6
Direction:          INBOUND/OUTBOUND per boundary
NACL association:   subnet -> actual NACL ID
First matched rule: rule number and action
SG/host policy:     relevant approved policy
Expected:           ALLOW or DENY
Observed:           flow/application evidence if actually tested
Verdict:            PASS/FAIL/INCONCLUSIVE
Evidence owner:     ticket/log references (no secrets)
~~~

**INCONCLUSIVE** đúng khi không xác định được source IP sau NAT, packet path, rule association hoặc trạng thái flow log. Không tự tuyên bố “đã an toàn” chỉ vì chưa thấy traffic trái phép.

## 29. Ma trận kiểm thử NACL và stateless filtering

Ma trận dưới đây nhằm kiểm chứng **khả năng phục vụ hợp lệ và chặn truy cập ngoài quyền**. Các phép kiểm thử gây thay đổi route, chặn traffic, failover hay tải cao phải thực hiện trên lab hoặc theo change có phê duyệt.

| Test ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| **NACL-01** | Client subnet hợp lệ gọi App TCP/8443 | Inbound App và outbound response hợp lệ |
| **NACL-02** | Client nguồn không được duyệt gọi App TCP/8443 | Bị chặn tại đúng boundary theo policy |
| **NACL-03** | Client hợp lệ gọi App admin port không được duyệt | DENY dù network có route |
| **NACL-04** | App gọi DB TCP/5432 | Gói đi và về được phép, DB auth riêng |
| **NACL-05** | Client trực tiếp gọi DB TCP/5432 | DENY; không bypass App |
| **NACL-06** | App nhận response vào destination ephemeral port | Rule App INBOUND đúng CIDR/dải client ephemeral |
| **NACL-07** | Client nhận response từ App | Client INBOUND đúng dải ephemeral khi NACL áp dụng |
| **NACL-08** | Outbound rule chỉ mở cổng dịch vụ thay vì ephemeral | Phát hiện lỗi chiều response trước production |
| **NACL-09** | Rule DENY ưu tiên cao che ALLOW | First-match quyết định chính xác và có cảnh báo shadowing |
| **NACL-10** | Rule ALLOW quá rộng che DENY | Policy lint bắt được phạm vi cấp quyền sai |
| **NACL-11** | Rule số lớn hơn được thêm vào dưới deny tổng quát | Lưu lượng vẫn DENY; reviewer không hiểu nhầm |
| **NACL-12** | DNS UDP/53 tới resolver được duyệt | Query và response đều hoạt động theo path thực |
| **NACL-13** | DNS TCP/53 khi ứng dụng yêu cầu | Không bị chặn ngoài ý muốn |
| **NACL-14** | DNS tới resolver không nằm trong policy | Bị từ chối nếu thiết kế yêu cầu và ranh giới lọc hỗ trợ |
| **NACL-15** | HTTPS tải lớn qua VPN/overlay | Không bị lỗi PMTUD do chặn feedback cần thiết |
| **NACL-16** | IPv6 address/AAAA trên dịch vụ dual-stack | Route và NACL/SG v6 được kiểm tra riêng |
| **NACL-17** | IPv6 đi tới management service không được duyệt | DENY theo policy tương ứng |
| **NACL-18** | Traffic qua NAT gateway hoặc SNAT proxy | Rule dùng đúng source/destination được quan sát tại boundary |
| **NACL-19** | Health check từ LB tới backend | Target health và policy đáp ứng thiết kế |
| **NACL-20** | LB/region dự phòng nhận traffic | NACL/SG của subnet dự phòng tương đương về intent |
| **NACL-21** | VPN peer/route failover được diễn tập | Luồng hợp lệ phục hồi, NACL không mở ngoài quyền |
| **NACL-22** | Peered VPC/transit route tới vùng khác | Chỉ thông tuyến đã cấp quyền, không route leak |
| **NACL-23** | Hai workload cùng subnet | Không dựa riêng NACL để thực thi microsegmentation |
| **NACL-24** | SG chặn flow dù NACL cho phép | Triage xác định đúng lớp denial |
| **NACL-25** | NACL chặn flow dù SG cho phép | Triage xác định đúng chiều/port/rule |
| **NACL-26** | Một kết nối TLS hợp lệ nhưng ứng dụng trả 403 | Không xem NACL là nơi phân quyền nghiệp vụ |
| **NACL-27** | Flow Logs REJECT trên một interface | Điều tra SG/NACL và rule theo packet path, không tự khẳng định NACL |
| **NACL-28** | Thay đổi rule bằng IaC ở staging | Rule diff, priority, CIDR, association khớp thiết kế |
| **NACL-29** | Quyền tạm hết hạn | Được review/thu hồi theo change và phép thử hồi quy |
| **NACL-30** | Collector/flow logs không có dữ liệu | Trạng thái UNKNOWN/INCONCLUSIVE, không kết luận traffic không tồn tại |
| **NACL-31** | Ứng dụng sử dụng port ngoài danh mục | Không tự mở rộng rule; cần owner review |
| **NACL-32** | API đầu cuối sau thay đổi NACL | Authentication, TLS, response, latency và negative access tests đúng |

### Tiêu chí đánh giá kết quả

- **PASS:** điều được thử có bằng chứng từ đúng path, đúng subnet/rule và ứng dụng phù hợp kỳ vọng.
- **FAIL:** đã có bằng chứng rõ một luồng hợp lệ bị chặn hoặc luồng ngoài quyền được cho phép.
- **INCONCLUSIVE:** thiếu nguồn/đích sau NAT, sai điểm đặt probe, không đủ log hoặc route chưa được xác nhận.
- **NOT_APPLICABLE:** chức năng không có trong kiến trúc thật, chẳng hạn IPv6 không được triển khai.

Một **DENY thành công** là kết quả bảo mật tích cực khi nó chặn **luồng ngoài quyền**; một **ALLOW thành công** chỉ là tích cực khi luồng đó thực sự cần thiết và các lớp xác thực/authorization còn nguyên.

## 30. Những hiểu nhầm và sai sót thường gặp

| Hiểu nhầm | Vì sao sai/thiếu | Cách tiếp cận đúng |
|---|---|---|
| “Có rule inbound cho dịch vụ là đủ” | Stateless không tự cho chiều response | Vẽ request/response 5-tuple |
| “Cổng response cũng là cổng 8443” | Source của server là 8443, destination client là ephemeral | Dùng destination port của gói thật |
| “Ephemeral ports luôn là 49152–65535” | Dải thay đổi theo OS/NAT/config | Xác minh nguồn sinh port và failover |
| “NACL có nhớ TCP SYN/ACK” | AWS NACL stateless | SG/host stateful tiếp tục kiểm soát phiên |
| “NACL cho phép thì ứng dụng chắc chắn reachable” | Route/SG/TLS/DNS/app có thể lỗi | Kiểm tra theo lớp |
| “Có ALLOW cụ thể trong danh sách nghĩa là được phép” | Có thể bị DENY trước shadow | Xét first-match theo rule number |
| “ALLOW ưu tiên thấp có thể ghi đè DENY ưu tiên cao” | Không đúng với AWS first-match NACL | Sắp rule theo policy và test |
| “Default NACL luôn deny” | Default VPC NACL có cấu hình cho phép sẵn theo mô hình AWS | Xem rule thực và đối chiếu posture |
| “Custom NACL mới luôn cho traffic đi qua” | Thường không có allow rules ban đầu | Đọc effective rules trước association |
| “Azure NSG cũng stateless như AWS NACL” | Azure NSG có cơ chế stateful flows | Thiết kế theo provider semantics |
| “Google VPC firewall cần return ephemeral NACL tương tự” | Google VPC firewall rules có stateful behavior | Không sao chép mô hình AWS |
| “Security group và NACL là hai tên cho một đối tượng” | Scope/rule/state khác nhau | Defense-in-depth và đúng owner |
| “Cùng subnet đã được NACL phân đoạn” | Boundary NACL có thể không lọc east–west cùng subnet | SG/CNI/host/identity policy |
| “NACL thay WAF hoặc IAM” | Không đọc JWT/API payload, user identity | Xác thực và authorization riêng |
| “CIDR nguồn là danh tính không giả mạo” | NAT/proxy/IP changes và threat model | Dùng mTLS/IAM và anti-spoofing phù hợp |
| “Chặn mọi ICMP sẽ bảo mật hơn” | Có thể làm PMTUD hỏng, đặc biệt IPv6 | Lọc có điều kiện, kiểm tra ICMP cần thiết |
| “Chỉ phải mở UDP/53 vì DNS không dùng TCP” | DNS có thể dùng TCP/53 và những giao thức khác | Xác định resolver/application thật |
| “IPv4 rule cũng chặn IPv6” | Hai address family được quản lý riêng | Test IPv4/IPv6 |
| “Flow log REJECT nghĩa đúng một NACL rule chặn” | REJECT không luôn cho rule ID hay tách SG/NACL | Ghép logs với effective policies |
| “Không có flow log nghĩa không có gói” | Có thể thiếu nguồn, thời điểm, coverage | Xem collection status và path |
| “Một probe tại một AZ đại diện cả cloud” | Subnet NACL/route/SG có thể khác theo vùng | Test đường active và dự phòng |
| “Mở 0.0.0.0/0 sẽ sửa hết lỗi connectivity” | Có thể mở rộng quyền mà lỗi gốc vẫn còn | Triage từ DNS/route tới NACL và app |
| “Đổi rule NACL không ảnh hưởng hệ thống khác” | NACL có thể gắn nhiều subnet/bao nhiều workload | Kiểm tra association và blast radius |
| “IaC validate PASS nghĩa mạng đã an toàn” | Cú pháp đúng chưa chứng minh intent và traffic | Positive/negative runtime tests |
| “Tunnel VPN UP là tất cả NACL đúng” | NACL và SG vẫn có thể từ chối gói | Test return path end-to-end |
| “NACL đủ cho chống DDoS” | Không bảo vệ được mọi lớp/băng thông phía trước | Provider anti-DDoS và đa lớp |

## 31. Câu hỏi tự kiểm tra

1. **Stateless** nghĩa là gì? Nó khác **stateful connection tracking** ở chỗ nào?
2. Một gói TCP từ **10.10.10.25:53000** tới **10.20.20.10:8443** có 5-tuple gì? 5-tuple của response là gì?
3. Vì sao App subnet cần **outbound destination ephemeral port** dù inbound đã cho phép 8443?
4. Nếu Client subnet có NACL custom default deny, cần thiết kế thêm những rule nào?
5. AWS NACL có những đặc điểm gì về **subnet association, rule priority, allow/deny và return traffic**?
6. Vì sao rule **80 DENY 10.0.0.0/8** có thể vô hiệu rule **100 ALLOW 10.10.10.0/24**?
7. Trong ví dụ App–DB, vì sao **App INBOUND ephemeral từ DB** có thể cần dù App chủ động gọi DB outbound 5432?
8. Nếu App và DB nằm cùng subnet, NACL có còn là ranh giới phân đoạn tin cậy giữa hai workload không?
9. Tại sao không có một dải ephemeral port toàn cầu đúng cho mọi hệ điều hành và NAT?
10. Đối với DNS UDP/53, destination port của request và response ở App subnet khác nhau thế nào?
11. Khi có DNS managed resolver trong cloud, vì sao không được mặc định NACL lọc mọi DNS query?
12. PMTUD và ICMP/ICMPv6 có liên quan gì đến lỗi “ping nhỏ thành công, HTTPS upload lớn timeout”?
13. Vì sao IPv6 cần CIDR, route và ACL/SG riêng khi bật dual-stack?
14. NACL nhìn thấy source IP nào ở một kết nối đi qua **SNAT hoặc load balancer**?
15. Một WAF/CDN chấp nhận HTTP request có chứng minh NACL App/DB cho phép đúng luồng không?
16. NACL khác AWS Security Group, Azure NSG và Google Cloud VPC firewall như thế nào?
17. Vì sao Network ACL không thể kiểm soát quyền truy cập **item của tenant khác** qua API HTTPS?
18. Khi VPN tunnel UP nhưng API timeout, cần kiểm tra những lớp nào trước khi sửa NACL?
19. Một bản ghi Flow Log **REJECT** có đủ để khẳng định NACL rule số 110 gây lỗi không?
20. Cần thiết kế policy-as-code test nào để phát hiện **shadowed rule và over-broad ALLOW**?
21. Nếu thay NACL trên subnet được nhiều service dùng chung, cần xét blast radius ra sao?
22. Sự khác nhau giữa **positive test** và **negative test** cho NACL là gì?
23. Khi App gọi DB qua TCP/5432, tại sao rule NACL hai chiều chưa đủ chứng minh DB session an toàn?
24. Chỉ số nào giúp xác minh một thay đổi NACL không làm suy giảm **DNS, health check, TLS và ứng dụng**?
25. Vì sao NACL không thay provider anti-DDoS hoặc rate limiting ở tầng API?
26. Nếu chính sách NACL đúng trên giấy nhưng flow logs trống, nên kết luận PASS, FAIL hay INCONCLUSIVE? Cần dữ liệu gì thêm?
27. Hãy tự thiết kế ma trận NACL cho một app subnet gọi **hai dịch vụ TCP và một resolver DNS**, gồm response traffic.
28. Nếu migration từ Azure NSG sang AWS NACL, ba giả định nào cần kiểm tra lại?

## 32. Ghi nhớ trọng tâm

**Network ACL stateless ra quyết định theo từng gói và từng chiều, không tự nhớ connection state.** Trong mô hình AWS VPC NACL, traffic vào và ra subnet được so với **danh sách rule riêng, có thứ tự số tăng dần và first-match**, rồi rơi vào mặc định nếu không khớp. Muốn một kết nối TCP/UDP hoạt động, cần nhìn đủ **source/destination, protocol, service port, ephemeral return port, CIDR, subnet association và đường đi thực**. Một inbound ALLOW cho port ứng dụng **không thay thế outbound ALLOW cho response**.

NACL là **một lớp trong defense-in-depth**: kết hợp **route, SG/firewall stateful, NAT, VPN, TLS/mTLS, IAM, WAF/IDS/IPS và authorization của ứng dụng**. Không coi CIDR nguồn là danh tính mạnh, không tự áp semantics AWS sang Azure/Google Cloud, không quên **DNS, UDP, IPv4/IPv6, ICMP/PMTUD, LB health checks, peering/transit và đường HA**. Với mạng hai chiều, gói phản hồi có **destination port khác gói request** là nguồn sai sót rất phổ biến.

Vận hành an toàn dựa trên **flow inventory, ordered rule analysis, IaC/policy-as-code, owner/change control, drift detection, flow logs có diễn giải đúng, positive/negative tests, runbook và rollback**. Không đóng một sự cố chỉ vì đã làm request hợp lệ chạy: phải chứng minh rằng **traffic được cấp quyền hoạt động ở đúng nơi, traffic không được cấp quyền vẫn bị từ chối**, và những lớp xác thực/quan sát phía sau NACL không bị bỏ qua.
