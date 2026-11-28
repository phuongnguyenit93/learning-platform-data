# Kiểm thử đường đi được phép và bị cấm trong phân đoạn mạng

## 1. Mục tiêu của kiểm thử segmentation

**Network segmentation (phân đoạn mạng)** chia hạ tầng thành các vùng có mức tin cậy và chức năng khác nhau, sau đó chỉ cho phép những luồng kết nối phù hợp với nhu cầu nghiệp vụ. Một kiến trúc có VLAN, subnet, firewall, VPN hoặc cloud security group chưa chắc đã được phân đoạn đúng: các đường đi thực tế có thể khác sơ đồ, các rule có thể quá rộng và nhiều luồng east–west có thể không đi qua điểm kiểm soát dự kiến.

**Kiểm thử đường đi được phép và bị cấm** là quá trình xác minh hai loại kỳ vọng:

1. **Positive test:** luồng được phép thực sự đi qua được các điểm kiểm soát và đáp ứng mục tiêu hoạt động.
2. **Negative test:** luồng không được phép thực sự bị chặn tại đúng ranh giới, kể cả khi có nhiều đường đi, nhiều giao thức hoặc cấu hình mạng thay đổi.

Đây là một bước quan trọng của module **SECURITY_NETWORK_SECURITY**. Kết quả kiểm thử hỗ trợ đánh giá hiệu quả phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, mạng không dây và cloud network, đồng thời cung cấp bằng chứng cho threat modeling và thiết kế kiến trúc mạng an toàn.

**Sau bài học, người học có thể:**

- Chuyển chính sách phân đoạn thành **ma trận kết nối** có nguồn, đích, giao thức, cổng, chiều, điều kiện và kết quả mong đợi.
- Thiết kế bộ kiểm thử kết hợp luồng **allow** và **deny**, phân biệt kiểm tra kết nối mạng với xác thực ứng dụng.
- Thu thập bằng chứng từ máy nguồn, máy đích và firewall/cloud/CNI để biết một gói đã đi tới đâu và bị xử lý như thế nào.
- Nhận diện những trường hợp dễ bỏ sót như IPv6, NAT, stateful return traffic, kết nối đã thiết lập, DNS, mạng khách, VPN và lưu lượng nội bộ.
- Ghi nhận pass/fail có thể tái hiện, xác định nguyên nhân sai khác và kiểm tra lại sau khi sửa policy.

> **Phạm vi thực hành:** chỉ gửi gói thử hoặc tạo kết nối trong phòng lab và hệ thống được phép kiểm tra. Các địa chỉ công khai minh họa thuộc dải tài liệu 192.0.2.0/24, 198.51.100.0/24 và 203.0.113.0/24; chúng không đại diện cho dịch vụ thật trên Internet. Các lệnh minh họa cần được điều chỉnh theo topology, quyền truy cập và endpoint thử nghiệm có kiểm soát.

## 2. Những gì cần xác minh trước khi chạy phép thử

### 2.1. Định nghĩa một đường đi mạng

Một **đường đi (network path)** gồm điểm nguồn, điểm đích và các thành phần chuyển tiếp hoặc thực thi policy ở giữa: switch, router, firewall, VPN gateway, NAT, load balancer, CNI, host firewall và đôi khi cả identity-aware proxy. Cùng một cặp máy có thể dùng nhiều đường khác nhau tùy địa chỉ nguồn, DNS, protocol, routing, VPN hoặc chính sách cloud.

Để mô tả một luồng IP, thường bắt đầu bằng **5-tuple**:

| Thành phần | Ví dụ |
|---|---|
| Source IP | 10.10.10.21 |
| Source port | 51842 |
| Destination IP | 10.30.10.15 |
| Destination port | 5432 |
| Protocol | TCP |

Trong mạng hiện đại cần bổ sung **IPv4/IPv6, source/destination zone, tài khoản hoặc danh tính dịch vụ, nhãn workload, interface, VPN context, NAT, thời điểm, môi trường và phiên kết nối**. Cặp IP và cổng giống nhau chưa bảo đảm hai phép thử chạy qua cùng ranh giới tin cậy.

### 2.2. Kết nối được phép nghĩa là gì?

Một kết nối có thể đi qua tầng mạng nhưng bị từ chối ở tầng ứng dụng, ví dụ:

- TCP three-way handshake hoàn thành, sau đó HTTPS trả **401 Unauthorized** vì chưa đăng nhập.
- TLS handshake hoàn thành, API trả **403 Forbidden** vì người gọi thiếu quyền.
- Máy chủ TCP trả **RST** vì ứng dụng chưa lắng nghe ở cổng đích.
- TCP kết nối được đến load balancer, nhưng upstream backend đang lỗi.

Trong ví dụ đầu tiên và thứ hai, **đường mạng có thể đã được cho phép đúng**; 401/403 là chính sách ứng dụng. Ngược lại, một timeout chưa đủ chứng minh firewall đã chặn, vì còn có thể do route, dịch vụ đích, DNS, mất gói hoặc quá tải.

Do đó, **kết quả mong đợi phải nêu rõ kiểm tra lớp nào**: kết nối TCP, phản hồi UDP, DNS resolution, TLS, HTTP hay nghiệp vụ đầy đủ.

### 2.3. Kết nối bị cấm nghĩa là gì?

Với đường mạng bị cấm, kết quả phù hợp có thể là:

- **DROP:** thiết bị loại bỏ gói mà không gửi phản hồi về nguồn.
- **REJECT:** thiết bị gửi phản hồi từ chối, ví dụ TCP reset hoặc thông báo ICMP thích hợp.
- **L7 denial:** kết nối mạng được thiết lập nhưng proxy hoặc ứng dụng từ chối yêu cầu theo danh tính/quyền. Đây là cách chặn ở **tầng ứng dụng**, không phải bằng chứng đã cô lập ở tầng mạng.

Nếu yêu cầu là **phân đoạn ở tầng mạng**, một HTTP 403 **không chứng minh** network deny. Nếu yêu cầu là **chính sách truy cập ứng dụng**, 403 có thể đúng. Phải so sánh với chính sách ở đúng điểm kiểm soát.

## 3. Mô hình lab dùng xuyên suốt

Giả sử doanh nghiệp triển khai một ứng dụng xử lý đơn hàng, chia thành các vùng:

- **USER:** máy trạm nhân viên trong LAN.
- **DMZ:** reverse proxy phục vụ HTTPS.
- **APP:** dịch vụ API nội bộ.
- **DATA:** database chỉ được API truy cập.
- **MGMT:** bastion cho quản trị viên đã xác thực.
- **GUEST:** Wi-Fi khách, không có quyền kết nối mạng nội bộ.
- **SHARED:** DNS resolver, IdP và hệ thống log.

~~~mermaid
flowchart LR
    USER["USER / LAN"] -->|"HTTPS 443: ALLOW"| WEB["DMZ / Web"]
    WEB -->|"TCP 8443: ALLOW"| API["APP / API"]
    API -->|"TCP 5432: ALLOW"| DB["DATA / DB"]
    API -->|"DNS: ALLOW"| DNS["SHARED / Resolver"]
    API -->|"Telemetry: ALLOW"| LOG["SHARED / Logs"]
    MGMT["MGMT / Bastion"] -.->|"Quản trị theo quyền"| API
    MGMT -.->|"Quản trị theo quyền"| DB
    USER -. "DENY direct" .-> DB
    WEB -. "DENY direct" .-> DB
    GUEST["GUEST / Wi-Fi"] -. "DENY" .-> API
    GUEST -. "DENY" .-> DB
~~~

Đường nét liền biểu thị luồng mong muốn; đường nét đứt biểu thị luồng cần bị chặn hoặc truy cập quản trị phụ thuộc điều kiện. Đường **API → DB** cần được bảo vệ cả bằng firewall/network policy lẫn danh tính và quyền database.

Giả sử trong lab các endpoint có địa chỉ sau:

| Vùng | Endpoint minh họa | IP | Dịch vụ kiểm tra |
|---|---|---|---|
| USER | user01.lab.example.test | 10.10.10.21 | Máy nguồn có quyền chạy test |
| DMZ | web.lab.example.test | 198.51.100.20 | TCP/443 |
| APP | api.lab.example.test | 10.20.10.20 | TCP/8443 |
| DATA | db.lab.example.test | 10.30.10.15 | TCP/5432 |
| MGMT | bastion.lab.example.test | 10.40.10.10 | SSH/22 khi được duyệt |
| GUEST | guest01.lab.example.test | 10.50.10.21 | Máy nguồn từ mạng khách |
| SHARED | dns.lab.example.test | 10.60.10.53 | UDP/TCP 53 |

Các IP riêng 10.x là giả định cho mạng lab; **198.51.100.20** là địa chỉ dành cho tài liệu. Những tên thuộc **lab.example.test** cần được cấu hình trong DNS lab nếu muốn chạy được ví dụ. Không tự áp dụng các dải này vào production.

## 4. Chuyển sơ đồ thành ma trận allow/deny

### 4.1. Ma trận kiểm thử tối thiểu

| Test ID | Nguồn | Đích | L4 / cổng | Kỳ vọng tại mạng | Lý do |
|---|---|---|---|---|---|
| **ALLOW-01** | USER | DMZ Web | TCP/443 | ALLOW | Người dùng truy cập web |
| **ALLOW-02** | DMZ Web | APP API | TCP/8443 | ALLOW | Web gọi API |
| **ALLOW-03** | APP API | DATA DB | TCP/5432 | ALLOW | API truy vấn database |
| **ALLOW-04** | APP API | DNS nội bộ | UDP/TCP 53 | ALLOW | Phân giải tên |
| **ALLOW-05** | MGMT Bastion | APP API | TCP/22, theo quy trình | ALLOW có điều kiện | Quản trị qua bastion |
| **DENY-01** | USER | DATA DB | TCP/5432 | DENY | Người dùng không kết nối DB trực tiếp |
| **DENY-02** | DMZ Web | DATA DB | TCP/5432 | DENY | Web chỉ làm việc với API |
| **DENY-03** | GUEST | APP API | TCP/8443 | DENY | Wi-Fi khách không truy cập APP |
| **DENY-04** | GUEST | DATA DB | TCP/5432 | DENY | Wi-Fi khách không truy cập DATA |
| **DENY-05** | USER | MGMT Bastion | TCP/22 | DENY, trừ nhóm được cấp quyền | Chặn quản trị trái phép |
| **DENY-06** | APP API | Internet đích chưa phê duyệt | TCP/443 | DENY khi dùng egress allowlist | Giảm bề mặt kết nối ra ngoài |

Đây chỉ là **mẫu**. Bộ test thực phải bao quát mọi rule quan trọng, nhất là biên giữa vùng dữ liệu nhạy cảm, quản trị, cloud và hệ thống có yêu cầu tuân thủ. Có thể phát sinh thêm test theo địa chỉ **IPv6**, trạng thái VPN, thiết bị BYOD hoặc yêu cầu xác thực.

### 4.2. Trường cần có cho mỗi test case

~~~yaml
test_id: DENY-01
purpose: User LAN must not connect directly to production database
source:
  zone: USER
  host: user01.lab.example.test
  ip: 10.10.10.21
destination:
  zone: DATA
  host: db.lab.example.test
  ip: 10.30.10.15
transport:
  protocol: TCP
  port: 5432
expected_network_decision: DENY
expected_enforcement_point: internal-segmentation-firewall
required_evidence:
  - source_connection_result
  - firewall_rule_id_and_drop_log
  - no_unexpected_successful_session
owner: network-security-team
status: planned
~~~

Định dạng trên chỉ minh họa cấu trúc quản lý test, không phải file thực thi. Với phép thử **ALLOW**, ghi cả tiêu chí chức năng tối thiểu (chẳng hạn TLS handshake hoặc HTTP health response), ngoài tiêu chí có cho phép ở tầng mạng.

### 4.3. Chọn ca kiểm thử theo rủi ro

Ưu tiên xác minh **đường đến crown jewels** (cơ sở dữ liệu nhạy cảm, identity provider, tài khoản quản trị, khóa, máy chủ sao lưu), **ranh giới Internet/VPN/Wi-Fi khách**, các **rule mới thay đổi**, rule **any-to-any**, kết nối **east–west** và tài sản có địa chỉ IPv6. Một ca test phủ được một rule, một điều kiện và một vị trí nguồn nhất định; nó không chứng minh toàn mạng đã được cô lập.

## 5. Thiết kế positive test cho luồng được phép

### 5.1. Kiểm tra theo các tầng

Một positive test tốt giúp phân biệt lỗi mạng với lỗi ứng dụng:

1. **Tên miền:** resolver có trả đúng IP dự kiến cho FQDN ở vùng đó không? Nếu dùng DNS split-view, so sánh với chính sách của view được kiểm tra.
2. **Routing:** máy nguồn có route đến đích? Gói đi qua firewall/NAT/gateway dự kiến không?
3. **Transport:** thiết lập được phiên TCP hoặc nhận phản hồi UDP hợp lệ từ endpoint test?
4. **TLS/xác thực:** nếu ứng dụng dùng TLS, tên chứng chỉ, CA, SNI và danh tính có đúng không?
5. **Ứng dụng:** endpoint trả nội dung hoặc mã trạng thái được kỳ vọng đối với tài khoản thử nghiệm?
6. **Telemetry:** log tại firewall, load balancer và dịch vụ xác nhận đúng luồng, rule và thời điểm?

**Ví dụ:** ALLOW-02 yêu cầu kết nối TCP/8443 từ DMZ Web đến APP API. Nếu TCP bắt tay thành công nhưng API trả 401, **đường mạng có thể đã PASS** trong khi bài test ứng dụng phải kiểm tra thêm thông tin xác thực. Nếu TCP timeout, cần tìm bằng chứng ở firewall/route/endpoint trước khi kết luận nguyên nhân.

### 5.2. Kiểm tra đường phản hồi

Một kết nối thành công không chỉ cần gói đi đến đích mà còn cần **đường về**. Firewall **stateful** thường theo dõi một kết nối đã được cho phép rồi cho phép gói phản hồi theo state. ACL **stateless** có thể phải khai báo cả chiều yêu cầu và phản hồi, bao gồm cổng nguồn động (*ephemeral port*).

Ví dụ, khi API mở kết nối từ cổng nguồn 51842 tới DB TCP/5432, chiều trả lời là **DB:5432 → API:51842**. Nếu ACL ở subnet DATA không cho phép gói phản hồi, test sẽ thất bại dù rule ingress của database có vẻ đúng.

### 5.3. Không giới hạn kiểm tra ở TCP

Các đường hợp lệ khác cần bộ phép thử phù hợp:

- **DNS:** UDP/53 và khả năng chuyển sang TCP/53 khi cần.
- **NTP/UDP:** xác minh phản hồi từ nguồn giờ được duyệt; không suy lỗi từ một UDP probe không có phản hồi.
- **ICMP/ICMPv6:** các loại message cần thiết cho Path MTU Discovery và Neighbor Discovery trong IPv6.
- **VPN:** luồng kết nối, cấp quyền theo nhóm và route sau khi xác thực.
- **QUIC/HTTP/3:** thường hoạt động trên UDP/443, không chỉ TCP/443.
- **Routing/control plane:** các giao thức nền hoặc health check có thể không đi cùng luồng ứng dụng và cần bài kiểm tra riêng.

## 6. Thiết kế negative test cho luồng bị cấm

### 6.1. Chọn vị trí nguồn thật sự có ý nghĩa

Để chứng minh **USER → DATA** bị chặn, phải thử từ **thiết bị thực sự thuộc vùng USER**, không phải từ laptop quản trị trong MGMT. Tương tự, kiểm tra GUEST cần dùng thiết bị kết nối vào đúng SSID/VLAN mạng khách. Với cloud, cần kiểm tra từ subnet, security group, VPC/VNet hoặc workload identity tương ứng.

Khi mạng có **VPN**, cùng một thiết bị có thể đổi vùng, source IP, DNS view hoặc route sau khi kết nối. Một test từ máy ở ngoài VPN và một test sau khi vào VPN là **hai trường hợp riêng**.

### 6.2. Chọn endpoint có thể xác minh

**Negative test đáng tin cậy** cần một đích thực sự hoạt động trong lab. Nếu database tắt hoặc port không mở, kết nối thất bại dù firewall đang cho qua tất cả. Do đó, nên có một phép thử kiểm soát từ nguồn **được phép** tới cùng đích/cổng tại cùng khoảng thời gian.

Ví dụ:

- **ALLOW-03:** API → DB:5432 kết nối thành công.
- **DENY-01:** USER → DB:5432 bị chặn và firewall log xác nhận policy deny.

Cặp kết quả này mạnh hơn việc chỉ quan sát một timeout từ USER. Không sử dụng kỹ thuật vượt kiểm soát; mục tiêu là **kiểm chứng chính sách bằng gói thử hợp lệ**, không tìm cách đi vòng ngoài phạm vi.

### 6.3. DROP, REJECT, RST và TIMEOUT không đồng nghĩa

| Quan sát tại client | Giải thích có thể | Kết luận nào cần tránh |
|---|---|---|
| TCP handshake thành công | Đường mạng đến endpoint TCP được mở cho luồng này | Không suy rằng người dùng có quyền ứng dụng |
| HTTP 401/403 sau handshake | Ứng dụng hoặc proxy từ chối danh tính/quyền | Không coi là chứng cứ network segmentation deny |
| TCP RST/Connection refused | Endpoint không lắng nghe, hoặc thiết bị trung gian chủ động từ chối | Không kết luận vị trí rule chặn chỉ từ thông báo |
| Timeout/no response | Có thể do DROP, route lỗi, host tắt, packet loss, ACL hoặc rate limit | Không coi timeout tự thân là PASS cho deny |
| ICMP admin prohibited | Một thiết bị báo không được phép theo chính sách | Cần xác định nguồn ICMP và đường gói |
| Firewall log: denied với 5-tuple khớp | Bằng chứng một điểm thực thi đã chặn luồng | Cần xem các đường thay thế và trạng thái luồng nếu phạm vi yêu cầu |

**Mục tiêu negative test là xác nhận quyết định policy tại ranh giới được chỉ định**, không chỉ tạo ra bất kỳ lỗi kết nối nào.

### 6.4. Ca âm tính theo biến thể

Một cặp nguồn–đích nên được kiểm tra theo các biến thể thực sự có trong thiết kế:

1. **Port khác:** DB chỉ cho TCP/5432 từ API; các port quản trị hay cổng ngoài nhu cầu phải bị chặn.
2. **Nguồn khác:** kiểm thử USER, GUEST, DMZ, MGMT không được cấp quyền và môi trường kiểm thử.
3. **Chiều khởi tạo ngược:** DATA có được mở kết nối mới tới USER hay không theo chính sách?
4. **IPv4 so với IPv6:** chính sách có bao phủ cả hai stack nếu hệ thống dùng dual-stack không?
5. **Kết nối mới so với kết nối đã tồn tại:** sau khi thu hẹp rule, conntrack có thể vẫn cho một số phiên cũ hoạt động đến khi hết hạn hoặc bị xóa.
6. **Đường vòng hợp lệ ngoài sơ đồ:** qua peering, transit gateway, load balancer, overlay, NAT hoặc service mesh có bypass enforcement không?
7. **Nhóm danh tính khác:** tài khoản VPN, nhóm thiết bị hoặc nhãn workload khác nhau có quyền đúng theo thiết kế không?

Chỉ chạy các biến thể nằm trong phạm vi kiểm tra được chấp thuận, có giới hạn về số lượng probe và thời gian.

## 7. Công cụ kiểm thử trong phòng lab

Các lệnh bên dưới dùng **địa chỉ giả định**. Để tái hiện, cấu hình một endpoint TCP test và hệ thống mạng lab tương ứng. Đừng kết nối tới dịch vụ sản xuất không thuộc phạm vi kiểm thử.

### 7.1. Kiểm tra nhanh TCP từ Linux

~~~bash
# Từ máy nguồn được phép: kiểm tra TCP connect tới API
nc -vz -w 3 10.20.10.20 8443

# Từ máy USER: negative test tới DB đang hoạt động
nc -vz -w 3 10.30.10.15 5432

# Quan sát kết nối TCP hiện tại
ss -tn

# Xem route dự kiến tới DB
ip route get 10.30.10.15
~~~

**nc** (netcat) có nhiều biến thể; tham số và thông báo có thể khác giữa hệ điều hành. Với TCP, kết quả “succeeded” chứng minh client hoàn thành kết nối tới port, **chưa chứng minh ứng dụng đúng danh tính**. Kết quả “failed/timed out” cần đối chiếu bằng chứng từ mạng và máy đích.

### 7.2. Kiểm tra HTTPS và danh tính đích

~~~bash
# Gửi yêu cầu HTTPS qua DNS được cấu hình trong lab
curl -v --connect-timeout 3 --max-time 10 https://web.lab.example.test/health

# Nếu lab dùng DNS tách biệt, chỉ định ánh xạ IP để giữ nguyên SNI/Host
# Điều kiện: server phải có chứng chỉ tin cậy với tên web.lab.example.test
curl -v --connect-timeout 3 --max-time 10 \
  --resolve web.lab.example.test:443:198.51.100.20 \
  https://web.lab.example.test/health
~~~

Khi thử đúng HTTPS, nên kiểm tra **chứng chỉ TLS và tên máy**. Không dùng tùy chọn bỏ kiểm tra chứng chỉ như một bằng chứng ứng dụng đã xác thực an toàn. Nếu lab dùng CA nội bộ, cần cài CA đáng tin vào môi trường kiểm thử hoặc chỉ định CA phù hợp.

**HTTP 200** hoặc mã trạng thái dự kiến khác từ endpoint test có thể xác nhận end-to-end. **HTTP 401/403** vẫn chứng minh HTTP stack đã nhận request và đưa ra quyết định tầng ứng dụng, miễn xác định được endpoint chính xác.

### 7.3. Kiểm tra DNS và địa chỉ IPv6

~~~bash
# Truy vấn resolver nội bộ từ vùng APP được phép
dig @10.60.10.53 api.lab.example.test A +time=2 +tries=1
dig @10.60.10.53 api.lab.example.test AAAA +time=2 +tries=1

# Kiểm tra khả năng dùng DNS qua TCP theo yêu cầu kiến trúc
dig @10.60.10.53 api.lab.example.test A +tcp +time=2 +tries=1

# Xem đường route IPv6, nếu lab có IPv6
ip -6 route
~~~

Truy vấn DNS thành công **không** chứng minh được TCP từ client tới API. Nếu policy cho phép DNS nội bộ mà chặn ứng dụng DATA, resolver vẫn có thể trả IP của DB; điều cần kiểm soát là **kết nối tới DB**, không nhất thiết là việc biết hostname DB.

### 7.4. Kiểm tra TCP từ Windows

~~~powershell
# Positive test tới web khi đã cấu hình endpoint tương ứng trong lab
Test-NetConnection -ComputerName 198.51.100.20 -Port 443 -InformationLevel Detailed

# Negative test từ vùng USER tới DB
Test-NetConnection -ComputerName 10.30.10.15 -Port 5432 -InformationLevel Detailed

# Xem route và địa chỉ trên máy đang dùng
Get-NetRoute
Get-NetIPAddress
~~~

**TcpTestSucceeded = False** chỉ cho biết TCP connect test không thành công; không đủ chứng minh firewall đã từ chối. Trường hợp True chứng minh kết nối TCP tới port đã thực hiện được theo ngữ cảnh của phép thử. Ping/ICMP nếu có trong kết quả chỉ hỗ trợ chẩn đoán, không nên lấy làm tiêu chí thay thế TCP.

### 7.5. Quan sát gói ở nguồn/đích

~~~bash
# Trên nguồn có quyền bắt gói: theo dõi SYN, RST và phản hồi TCP
sudo tcpdump -ni any 'host 10.30.10.15 and tcp port 5432'

# Nếu cần so sánh đường trả lời, ghi lại 5-tuple của kết nối
sudo tcpdump -ni any 'host 10.20.10.20 and tcp port 8443'
~~~

Nếu bắt gói tại nguồn thấy SYN đi ra nhưng máy đích không thấy SYN, cần xét các điểm trung gian. Nếu đích nhận SYN và gửi SYN/ACK nhưng nguồn không nhận được, có thể có lỗi **chiều trả lời**, routing hoặc stateful policy. Chỉ quan sát một chiều chưa đủ kết luận nguyên nhân.

## 8. Phân tích bằng chứng theo ba điểm quan sát

Để phân biệt lý do network allow/deny, nên kết hợp ba điểm:

~~~mermaid
flowchart LR
    S["Nguồn: lệnh thử + capture"] --> F["Firewall/router/CNI: rule ID, counters, logs"]
    F --> D["Đích: capture + trạng thái dịch vụ"]
    F -. "Log allow/deny" .-> E["Kho bằng chứng"]
    S -. "Kết quả kết nối" .-> E
    D -. "Có/không nhận gói" .-> E
~~~

### 8.1. Những mẫu dấu vết thường gặp

| Nguồn | Điểm kiểm soát | Đích | Kết luận sơ bộ |
|---|---|---|---|
| SYN → SYN/ACK → ACK | ALLOW đúng rule | Nhận SYN, phát SYN/ACK | TCP path thành công; còn cần app test |
| SYN rồi retransmission | DENY/DROP khớp luồng | Không nhận SYN | Bằng chứng mạnh của segmentation deny |
| SYN → RST | Không ghi drop | Đích phát RST | Đường có thể mở, nhưng dịch vụ/cổng đích từ chối |
| SYN tới firewall | ALLOW | Đích không thấy SYN | Kiểm tra route/NAT/thiết bị kế tiếp sau firewall |
| SYN tới đích, SYN/ACK không về nguồn | Chiều đi ALLOW, chiều về bị chặn hoặc sai route | Đích có trả lời | Kiểm tra reverse path, state, ACL chiều về |
| Ứng dụng trả 403 | ALLOW tới ứng dụng | Xử lý request | Mạng có thể PASS; kiểm tra ủy quyền ở ứng dụng |

Mỗi dòng chỉ là **mẫu phân tích**. Trong trường hợp TLS proxy, load balancer hoặc NAT, client có thể kết nối đến một thiết bị trung gian; cần đặt capture theo đúng chặng cần chứng minh. Packet offloading trên host còn có thể làm kích thước gói quan sát khác packet thực trên dây.

### 8.2. Dữ liệu tối thiểu phải lưu

Ghi **test ID**, thời gian UTC, IP/port nguồn và đích, giao thức, danh tính/zone, vị trí máy thử, DNS answer nếu dùng tên, đường đi/NAT, lệnh và đầu ra, rule/policy ID, log allow/deny, trạng thái đích, người thực hiện và kết luận. Với báo cáo học thuật hoặc vận hành, chú thích IP minh họa và che dữ liệu nhạy cảm trước khi chia sẻ.

### 8.3. Có cần ghi log mọi gói deny không?

Không nhất thiết. Ghi mọi packet có thể gây quá tải log/SIEM, tăng chi phí và che khuất tín hiệu hữu ích. Nên thu thập theo **rule quan trọng, sampling/rate limit hoặc khoảng thời gian test có kiểm soát**, đồng thời dùng counters và flow logs theo khả năng thiết bị. Cần cân nhắc lưu giữ bằng chứng, an toàn thông tin và hạn chế tác động tới hệ thống.

## 9. Các yếu tố có thể làm sai kết quả

### 9.1. NAT, load balancer và proxy

Khi có **SNAT/DNAT**, firewall ở các vị trí khác nhau có thể quan sát **5-tuple trước hoặc sau NAT**. Một allow/deny log chứa địa chỉ không giống máy nguồn chưa chắc là log không liên quan. Load balancer có thể kết thúc TCP của client và tạo kết nối mới tới backend; khi đó kiểm tra client → LB và LB → backend là **hai luồng riêng**.

### 9.2. Stateful firewall và kết nối đã thiết lập

Nếu thay policy từ allow sang deny khi một TCP session đang mở, firewall stateful có thể tiếp tục cho lưu lượng phiên đó theo conntrack cho tới khi session hết hạn hoặc bị xóa, tùy cấu hình. Một test chỉ dùng phiên cũ không chứng minh policy dành cho **kết nối mới** bị lỗi. Khi kiểm thử sau thay đổi, thực hiện kết nối **NEW** độc lập và ghi rõ trạng thái phiên. Không xóa bảng conntrack trên production chỉ để phục vụ kiểm thử khi chưa đánh giá tác động.

### 9.3. DNS, cache và nhiều địa chỉ đích

Hostname có thể trả nhiều bản ghi **A/AAAA**, nhiều IP theo vùng hoặc thông qua **CNAME** đến CDN. Nếu client chỉ thử một IP, chưa đủ bằng chứng tất cả endpoint được bảo vệ giống nhau. Split-view DNS có thể làm tên nội bộ trả kết quả khác ngoài VPN; TTL và cache cũng ảnh hưởng. Có thể ghi song song **FQDN và IP thực tế** để tái hiện chính xác.

### 9.4. Routing bất đối xứng, peering và nhiều đường

Hai chiều lưu lượng có thể đi qua firewall khác nhau, nhất là môi trường đa vùng, SD-WAN, cloud transit gateway hoặc khi thay đổi route. Phép thử phải xác định **đường đi thực**, vì một rule đúng trên firewall A không giúp nếu gói đi vòng qua firewall B. Traceroute/tracert hỗ trợ khảo sát nhưng nhiều thiết bị không trả ICMP và kết quả không cho biết đầy đủ đường hoặc policy.

### 9.5. Stateless ACL và cổng nguồn động

Một ACL stateless có thể cho SYN đi đến TCP/443 nhưng chặn SYN/ACK trở lại vì không mở chiều trả lời từ **source port 443 đến client ephemeral port**. Không nên khắc phục bằng một rule any-to-any. Hãy giới hạn theo cặp vùng, địa chỉ, giao thức và dải cổng phù hợp chính sách.

### 9.6. Phân biệt network deny và lỗi giao thức

| Dấu hiệu | Không nên kết luận vội | Đối chiếu tiếp |
|---|---|---|
| DNS NXDOMAIN | Firewall chặn API | Kiểm tra DNS view/zone và FQDN |
| HTTP 403 | Phân đoạn chặn network | Xem định danh, proxy và ứng dụng |
| TCP RST | Chắc chắn firewall deny | Xem nguồn RST và listener ở đích |
| ICMP Echo timeout | TCP/443 không đi được | Test trực tiếp đúng TCP/443 |
| UDP không trả lời | UDP bị firewall chặn | Dùng ứng dụng test có phản hồi định nghĩa rõ và flow logs |
| Một IP bị chặn | Toàn bộ hostname được bảo vệ | Kiểm tra các IP khác, IPv6, DNS view và route |

## 10. Kiểm thử segmentation trên các nền tảng khác nhau

### 10.1. VLAN, router ACL và firewall nội bộ

**VLAN** tách broadcast domain ở tầng 2, nhưng **không tự đảm bảo** có tường lửa giữa các VLAN. Truy cập inter-VLAN có thể được router/L3 switch chuyển tiếp nếu ACL cho phép hoặc không có kiểm soát. Vì vậy, thử cả từ client trong VLAN USER đến DATA và từ USER đến ứng dụng được phép. Đối chiếu rule trên interface VLAN, zone policy và thiết bị L3 thực sự định tuyến.

### 10.2. Cloud VPC/VNet, security group và subnet ACL

Trong cloud, đường đi chịu ảnh hưởng của **route tables, security group/NSG, network ACL, NAT gateway, peering, load balancer và private endpoints**:

- **AWS Security Group:** là cơ chế stateful, các rule được phép có tính cộng gộp khi gắn nhiều group; cần xác minh ingress và egress.
- **AWS Network ACL:** là stateless, có các rule allow/deny theo thứ tự; kiểm tra cả chiều phản hồi.
- **Azure NSG:** có các rule ưu tiên và default rules; cần xem effective security rules và luồng qua subnet/NIC phù hợp.
- **VPC/VNet peering, transit và private link:** có thể tạo đường mới đến tài sản, nên kiểm tra các cặp nguồn/đích ở ranh giới thực tế.

**Flow log ACCEPT/REJECT** hữu ích nhưng không đại diện cho mọi điểm kiểm soát hoặc hành vi ứng dụng; tùy dịch vụ, log có thể được tổng hợp, giới hạn hoặc thiếu một số loại traffic. Ghép chúng với trạng thái service và thử kết nối từ đúng máy nguồn.

### 10.3. Kubernetes NetworkPolicy và overlay

Trong Kubernetes, **NetworkPolicy** có thể cô lập ingress/egress của pod được chọn nếu **CNI hỗ trợ thực thi**. Một policy có tên **default-deny** không chặn mọi pod nếu selector không khớp, policy khác mở quyền hoặc CNI không thực thi. Các rule allow thường **cộng gộp** chứ không áp dụng thứ tự deny/allow kiểu firewall truyền thống.

Có thể bắt đầu bằng các lệnh **chỉ đọc**:

~~~bash
kubectl get networkpolicy -n orders
kubectl get pods -n orders --show-labels
kubectl describe networkpolicy -n orders
~~~

Sau đó, với **pod kiểm thử sẵn có và được cấp quyền**, thử kết nối từ namespace/label được phép và namespace/label bị cấm. Khi cả nguồn và đích bị cô lập, cần xác nhận **egress nguồn** và **ingress đích**. Lưu ý tác động của Service/ClusterIP, NAT, service mesh, NetworkPolicy ở namespace khác và node-level traffic. Không tạo pod hoặc gửi lưu lượng test trong cluster thật khi chưa nằm trong phạm vi được duyệt.

### 10.4. VPN và Zero Trust Network Access

Một user đã xác thực VPN vẫn cần chỉ được đến tài nguyên theo vai trò. Ma trận kiểm thử có thể so sánh:

| Bối cảnh | Đích nghiệp vụ | Đích quản trị | Kỳ vọng |
|---|---|---|---|
| Chưa đăng nhập VPN | Ứng dụng chỉ dành cho VPN | Bastion | DENY ở đường bên ngoài |
| VPN, nhóm nhân viên thường | Ứng dụng được ủy quyền | Bastion | ALLOW ứng dụng, DENY bastion |
| VPN, nhóm vận hành | Ứng dụng theo quyền | Bastion qua điều kiện xác thực | ALLOW có điều kiện |
| Wi-Fi khách | Tài nguyên nội bộ | Bastion | DENY |

Nếu có ZTNA/identity-aware proxy, một kết nối đến proxy có thể thành công nhưng yêu cầu bị từ chối theo danh tính ở tầng trên. Cần phân biệt **network path đến proxy** với **quyền truy cập tới backend**.

### 10.5. Mạng không dây và thiết bị không quản lý

Từ **SSID guest**, xác nhận máy nhận đúng VLAN, route, DNS và policy; thử truy cập tới vài tài sản nội bộ đại diện trong phạm vi. Nếu hệ thống dùng 802.1X/NAC, kết quả có thể phụ thuộc trạng thái xác thực thiết bị, vai trò hoặc posture. Không coi việc máy khách thấy SSID khác là bằng chứng truy cập được subnet đó.

## 11. Tiêu chí PASS, FAIL và INCONCLUSIVE

Đánh giá test có thể dùng ba trạng thái:

| Kết quả | Khi nào dùng | Ví dụ |
|---|---|---|
| **PASS** | Kết quả đúng với kỳ vọng và có đủ bằng chứng đáng tin | ALLOW-03 TCP established; DENY-01 log firewall DROP đúng 5-tuple, nguồn không có session |
| **FAIL** | Có bằng chứng trái với chính sách | USER thiết lập TCP đến DB dù phải deny; API không gọi được DB dù phải allow |
| **INCONCLUSIVE** | Không đủ bằng chứng hoặc điều kiện thử chưa hợp lệ | DB tắt, mất log, route sai, chỉ thấy timeout hoặc nguồn test không thuộc vùng yêu cầu |

Với negative test, **client timeout không phải tự động PASS**. Với positive test, **một HTTP 403 không phải tự động FAIL mạng** nếu mục tiêu chỉ là TCP/TLS connectivity. Ghi rõ tiêu chí để tránh báo cáo sai.

### 11.1. Mẫu biên bản kết quả

~~~text
Test ID:             DENY-01
Business requirement: USER must not reach DATA/DB directly
Source:              user01 (USER), 10.10.10.21
Destination:         db01 (DATA), 10.30.10.15:5432/TCP
Time:                2026-11-28T03:15:00Z (minh họa)
Method:              TCP connect, new session
Expected:            DENY at internal segmentation firewall
Client observation:  Timeout; no TCP session established
Firewall observation: Drop rule SEG-DENY-102 matched correct 5-tuple
Destination:         No SYN observed in matching capture interval
Control positive:    API -> same DB:5432 succeeded
Conclusion:          PASS for this test path and time
Owner:               Network Security
Evidence:            test log, firewall event, packet capture
~~~

Đây là **ví dụ kết quả giả định** để minh họa cách báo cáo. Không sử dụng các dữ kiện minh họa làm bằng chứng kiểm thử cho hạ tầng thực.

### 11.2. Độ bao phủ cần báo cáo

Không chỉ đưa ra tỷ lệ “số test PASS / tổng test”. Cần xác định bộ kiểm thử bao phủ:

- Bao nhiêu **luồng allow** và **luồng deny** quan trọng theo ma trận?
- Những **vùng mạng** nào chưa có máy nguồn hợp lệ để kiểm tra?
- Đã thử **IPv6** và **egress** nếu hạ tầng dùng chúng chưa?
- Có kiểm tra **đường VPN, peering, cloud, Wi-Fi khách và east–west** không?
- Có test với **connection NEW** sau thay đổi policy không?
- Những test nào **INCONCLUSIVE**, thiếu log hoặc chưa có chủ sở hữu xác nhận?

Một tỷ lệ PASS cao không chứng minh an toàn nếu các đường nhạy cảm nhất chưa được đưa vào bộ kiểm thử.

## 12. Quy trình kiểm thử trong môi trường vận hành

### Bước 1 — Xác định chính sách gốc

Lấy **ma trận kết nối đã được phê duyệt**, sơ đồ phân đoạn và danh mục tài sản. Xác định rõ **source zone, destination zone, service, direction, environment, rule owner** và mục đích kiểm soát. Khi chính sách chưa rõ, đánh dấu điểm cần xác minh; không tự suy rằng “không thấy rule” là có thể chạy bất kỳ phép thử nào.

### Bước 2 — Xác định nguồn và đích thử

Chọn máy kiểm thử ở **đúng vùng**, có endpoint đích **đang hoạt động** và cách xác minh kết quả. Với ca âm tính quan trọng, thiết lập cặp positive control từ nguồn được phép. Kiểm tra DNS, route và quyền sử dụng công cụ trước khi thu thập kết quả.

### Bước 3 — Chọn mức độ tác động

Ưu tiên kết nối TCP đơn giản hoặc giao dịch ứng dụng an toàn, có timeout ngắn và số lần thử có giới hạn. Tránh dùng tải cao, thay đổi policy hoặc quét nhiều cổng khi mục tiêu chỉ là xác minh một rule. Với hệ thống nhạy cảm, phối hợp lịch thay đổi, điểm liên lạc ứng cứu và phương án dừng test khi có bất thường.

### Bước 4 — Thu thập baseline

Ghi trạng thái chính sách, rule IDs, source IP, route, DNS answer, trạng thái dịch vụ và phép thử control. Không làm thay đổi policy trong khi đang xác minh baseline nếu chưa có kế hoạch và phạm vi thay đổi riêng.

### Bước 5 — Chạy positive rồi negative

Chạy positive test để xác nhận endpoint có thể phục vụ đường được phép. Sau đó từ nguồn bị cấm thực hiện negative test tương ứng. Lặp lại cho các tổ hợp có mức rủi ro cao, chú ý đường vòng, IPv6, VPN và các nhóm quyền.

### Bước 6 — Đối chiếu log, capture và effective policy

Khớp bằng **timestamp, 5-tuple, điểm thực thi, rule ID, policy version**. Nếu kết quả trái kỳ vọng, phân biệt policy deny, routing, NAT, stateful tracking, endpoint, ứng dụng và dịch vụ nền.

### Bước 7 — Xác nhận kết quả và xử lý sai lệch

Gán **PASS/FAIL/INCONCLUSIVE**, đính kèm bằng chứng, mức độ rủi ro, người sở hữu và bước tiếp theo. Nếu phát hiện luồng bị cấm nhưng vẫn mở, ưu tiên đánh giá **mức độ phơi lộ và tác động nghiệp vụ**, rồi sửa tại điểm thực thi đúng theo quy trình thay đổi.

### Bước 8 — Kiểm tra hồi quy sau khi thay đổi

Sau khi sửa rule, chạy lại **test đã FAIL** và những luồng **ALLOW phụ thuộc** có thể bị ảnh hưởng. Kiểm tra cả **new connections**; cần xét kết nối còn tồn tại trong state table. Lưu phiên bản ma trận và bằng chứng mới để so sánh với lần sau.

~~~mermaid
flowchart TD
    A["Chính sách đã duyệt + sơ đồ mạng"] --> B["Ma trận allow/deny"]
    B --> C["Chuẩn bị nguồn, đích, baseline"]
    C --> D["Positive control"]
    D --> E{"Endpoint và đường hợp lệ hoạt động?"}
    E -- "Không" --> I["INCONCLUSIVE / điều tra nền tảng"]
    E -- "Có" --> F["Negative test từ nguồn bị cấm"]
    F --> G["Đối chiếu log + packet capture + effective policy"]
    G --> H{"Kết quả khớp kỳ vọng?"}
    H -- "Có" --> P["PASS + lưu bằng chứng"]
    H -- "Không" --> Q["FAIL hoặc INCONCLUSIVE + phân tích nguyên nhân"]
    Q --> R["Sửa có kiểm soát + kiểm tra hồi quy"]
    R --> D
~~~

## 13. Case study: Web bị cấm truy cập database trực tiếp

### 13.1. Yêu cầu

Một dịch vụ web trong **DMZ** chỉ được truy cập **API**. Chỉ API trong vùng APP được mở kết nối **database TCP/5432** ở DATA. Ma trận có:

~~~text
WEB -> API:8443      ALLOW
API -> DB:5432       ALLOW
WEB -> DB:5432       DENY
USER -> DB:5432      DENY
~~~

### 13.2. Bộ kiểm thử

1. Từ API, tạo TCP connection mới đến DB:5432; xác nhận DB đang lắng nghe và kết nối thành công.
2. Từ WEB, tạo TCP connection mới đến API:8443; xác nhận đường Web → API hoạt động.
3. Từ WEB, thử TCP connect đến DB:5432 và thu log tại firewall liên vùng.
4. Từ USER, thử TCP connect đến cùng DB:5432 và thu log tương ứng.
5. Nếu hệ thống có IPv6, lặp lại với địa chỉ IPv6 thực tế của endpoint; không suy từ kết quả IPv4.

### 13.3. Kết quả giả định

~~~text
ALLOW API -> DB TCP/5432       success
ALLOW WEB -> API TCP/8443     success
DENY  WEB -> DB TCP/5432      unexpected success
DENY  USER -> DB TCP/5432     blocked, rule SEG-DENY-102
~~~

**Phát hiện:** yêu cầu phân đoạn **WEB → DATA** đang bị vi phạm. Giả sử log cho thấy Web → DB được match bởi một allow rule rộng **DMZ → internal any** trên firewall. Đây là nguyên nhân hợp lý trong mô hình ví dụ; cần đối chiếu chính xác rule ID, interface, NAT và effective policy trước khi sửa hệ thống thực.

**Khuyến nghị:** thay allow quá rộng bằng danh sách luồng phục vụ nghiệp vụ, giữ WEB → API:8443 và loại bỏ quyền WEB → DB. Rà soát đường đi khác qua peering, load balancer hoặc host firewall. Sau sửa, thực hiện lại cả hai positive tests và hai negative tests; xác nhận không làm đứt ứng dụng hợp lệ.

**Bài học:** chỉ kiểm tra “WEB → API còn chạy” sẽ bỏ lỡ lỗ hổng. Chỉ kiểm tra “USER → DB bị chặn” cũng không đảm bảo mọi nguồn không được phép đều bị chặn. **Positive và negative tests phải bao phủ các ranh giới quan trọng**.

## 14. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ kiểm tra luồng được phép | Không phát hiện đường truy cập thừa | Thêm negative test cho từng trust boundary |
| Dùng một timeout làm bằng chứng deny | Có thể nhầm route hoặc server down thành policy chặn | Kiểm tra endpoint còn sống và log/capture tại điểm thực thi |
| Thử từ máy quản trị thay vì nguồn thật | Sai zone và sai quyền | Chọn nguồn thuộc đúng VLAN/subnet/nhãn/role |
| Chỉ thử một địa chỉ IP của hostname | Bỏ sót endpoint khác hoặc IPv6 | Lưu DNS answer, kiểm tra các đích hợp lệ trong phạm vi |
| Bỏ qua NAT/load balancer | Không khớp 5-tuple, bỏ sót chặng backend | Ghi tuple trước/sau NAT, phân tách luồng client/LB/backend |
| Dùng ICMP ping thay thế TCP/UDP app test | Ping bị chặn không phản ánh kết nối ứng dụng | Kiểm thử đúng protocol/port và service |
| Chỉ xem cấu hình firewall | Có thể kiểm tra sai thiết bị hoặc đường đi bỏ qua policy | Chứng minh bằng packet flow, effective rule, capture và logs |
| Không xét session đã thiết lập | Phiên cũ vẫn chạy sau đổi rule | Test kết nối NEW, xem session table theo quyền |
| Chặn mọi ICMP để đạt deny | Có thể làm hỏng PMTUD, IPv6 | Phân loại các thông điệp ICMP/ICMPv6 cần thiết |
| Báo PASS khi không đủ bằng chứng | Tạo cảm giác an toàn sai | Dùng INCONCLUSIVE và yêu cầu kiểm chứng |
| Thử sản xuất không giới hạn | Gây quá tải, log nhiễu hoặc gián đoạn | Chỉ gửi lưu lượng thấp và có phạm vi, lịch, người liên lạc rõ ràng |

## 15. Câu hỏi luyện tập

**Câu 1 — Đánh giá bằng chứng.** Một kết nối từ Wi-Fi khách đến database bị timeout. Kết luận “segmentation đã chặn thành công” có hợp lệ chưa?

*Gợi ý:* chưa. Cần xác minh DB hoạt động từ nguồn được phép, route hợp lệ, đúng VLAN Wi-Fi khách, log deny/capture và điểm thực thi. Nếu không đủ dữ liệu thì kết quả **INCONCLUSIVE**.

**Câu 2 — Lỗi chiều phản hồi.** API gửi SYN tới database, database trả SYN/ACK nhưng API không nhận được. Firewall chiều đi ghi ALLOW. Nêu ít nhất ba nơi cần xem xét.

*Gợi ý:* route chiều về; stateless ACL và ephemeral ports; stateful firewall bất đối xứng; NAT; firewall gần nguồn và đích. Có thể cần capture tại nhiều điểm để xác định vị trí mất gói.

**Câu 3 — Luồng được phép nhưng HTTP 403.** Frontend gọi API qua HTTPS, TCP và TLS đều thành công nhưng API trả 403. Test mạng và test nghiệp vụ nên ghi gì?

*Gợi ý:* **network connectivity** có thể PASS nếu đúng đích và policy; **application authorization** cần kiểm tra role/token. Không coi 403 là bằng chứng network deny.

**Câu 4 — Kiểm thử sau đổi rule.** Firewall vừa sửa từ allow sang deny, nhưng một TCP session đã có trước đó vẫn truyền dữ liệu. Có thể kết luận rule mới vô hiệu không?

*Gợi ý:* chưa. Firewall stateful có thể giữ session hiện tại; cần thử **kết nối mới** và đối chiếu conntrack/rule theo mô hình thiết bị.

**Câu 5 — Phủ sót IPv6.** IPv4 từ GUEST đến DATA bị chặn. Hệ thống có địa chỉ IPv6 cho cả hai vùng. Cần bổ sung gì?

*Gợi ý:* ca GUEST → DATA trên IPv6, policy và route IPv6, các bản ghi AAAA, cùng bằng chứng tại điểm kiểm soát. Một test IPv4 không chứng minh chính sách dual-stack.

**Câu 6 — Cloud và Kubernetes.** NetworkPolicy đã cấu hình default-deny, nhưng hai pod vẫn kết nối được. Nêu các giả thuyết.

*Gợi ý:* CNI không hỗ trợ/không thực thi; selector nhãn không chọn pod; NetworkPolicy khác có allow; đi qua endpoint hoặc kiểu traffic CNI xử lý riêng. Kiểm tra dataplane thực tế thay vì chỉ đọc YAML.

**Câu 7 — Tạo một test case.** Theo mô hình lab, hãy viết test case từ **GUEST → APP API TCP/8443** gồm source, destination, protocol, kỳ vọng, điểm chặn và ba bằng chứng cần thu thập.

*Gợi ý:* kỳ vọng **DENY** ở ranh giới GUEST–APP; có positive control DMZ Web → APP API, quan sát client không có session, log deny phù hợp và đích không nhận kết nối thử.

## 16. Checklist cuối cùng

Trước khi xác nhận một đợt kiểm thử segmentation hoàn tất, rà soát:

- Đã có **ma trận allow/deny** gắn với yêu cầu nghiệp vụ và chủ sở hữu.
- Mỗi test dùng **đúng source zone, destination zone, danh tính, protocol/port và direction**.
- Negative test có **positive control** hoặc bằng chứng khác chứng minh đích hoạt động.
- Đã đối chiếu **lệnh thử, firewall/CNI/cloud logs, effective policy và capture** ở các điểm phù hợp.
- Đã phân biệt **network deny** với **DNS, routing, service, TLS hoặc authorization failure**.
- Đã xét **IPv4/IPv6, NAT, stateful/stateless, VPN, Wi-Fi, cloud và east–west** khi có trong phạm vi.
- Test nào không đủ dữ liệu được ghi **INCONCLUSIVE** cùng lý do và bước cần xác minh.
- Sai lệch có **người sở hữu, đánh giá mức ảnh hưởng, kế hoạch sửa và kết quả regression test**.

**Điều cần ghi nhớ:** một mạng an toàn phải chứng minh được **đường cần dùng thực sự hoạt động** và **đường không được phép thực sự bị chặn**. Việc có firewall, VLAN hay network policy mới chỉ thể hiện ý định kiến trúc; kiểm thử từ đúng nguồn, đến đúng đích và đối chiếu bằng chứng nhiều lớp mới chứng minh được kết quả thực thi.

### Tài liệu tham khảo

- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): xây dựng, kiểm tra và vận hành chính sách firewall.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): kiểm soát truy cập theo tài nguyên và ranh giới tin cậy.
- [NIST SP 800-115 — Technical Guide to Information Security Testing and Assessment](https://csrc.nist.gov/pubs/sp/800/115/final): lập kế hoạch và thực hiện kiểm thử bảo mật có kiểm soát.
- [Kubernetes Documentation — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): mô hình cô lập và tính cộng gộp các quyền cho phép.
- [AWS VPC Documentation — Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html): cơ chế stateless và rule theo thứ tự.
- [AWS VPC Documentation — Security Group Rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html): xử lý stateful, ingress và egress.
- [RFC 8201 — Path MTU Discovery for IP version 6](https://www.rfc-editor.org/rfc/rfc8201): lý do phải xem xét ICMPv6 Packet Too Big trong chính sách lọc.
- [RFC 4890 — Recommendations for Filtering ICMPv6 Messages in Firewalls](https://www.rfc-editor.org/rfc/rfc4890): các loại ICMPv6 thiết yếu và cách lọc theo ngữ cảnh.
