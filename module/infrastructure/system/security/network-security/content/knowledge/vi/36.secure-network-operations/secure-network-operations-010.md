# Runbook cho lỗi kết nối thường gặp

## 1. Mục đích, phạm vi và cách sử dụng

Trong chương **Quản trị vận hành mạng an toàn** của module **SECURITY_NETWORK_SECURITY**, runbook là tài liệu tác nghiệp giúp người trực hệ thống chẩn đoán, cô lập và khôi phục sự cố kết nối bằng một quy trình có thể lặp lại, có bằng chứng và có thể bàn giao. Chủ đề này áp dụng kiến thức về mô hình mạng, phân đoạn, firewall, VPN, IDS/IPS, bảo vệ DNS, Wi-Fi và cloud networking vào xử lý sự cố thực tế.

Một lỗi “không vào được dịch vụ” có thể phát sinh ở nhiều điểm: laptop không được cấp địa chỉ IP; DNS không phân giải được tên; định tuyến sai; firewall từ chối; VPN cấp quyền không phù hợp; TLS xác thực thất bại; proxy lỗi; backend không sẵn sàng; hoặc log thiếu khiến nhóm vận hành kết luận nhầm. Runbook phải giúp phân biệt các khả năng này trước khi thay đổi cấu hình.

**Mục tiêu học tập:** sau bài học, người học có thể:

1. Phân loại triệu chứng và khoanh vùng sự cố theo đường truyền từ client đến dịch vụ.
2. Thu thập chứng cứ mạng có ngữ cảnh mà không làm lộ bí mật hoặc ảnh hưởng hệ thống.
3. Chạy các bước kiểm tra DNS, TCP, routing, firewall, VPN, TLS, Wi-Fi, proxy, load balancer, cloud và Kubernetes.
4. Xác định tiêu chí quyết định khi nào tiếp tục tại chỗ, khi nào chuyển cho nhóm khác và khi nào cần quy trình incident.
5. Khôi phục có kiểm soát, xác nhận chức năng, cập nhật hồ sơ và đề xuất biện pháp phòng ngừa tái phát.

Tài liệu dùng ví dụ giả định và địa chỉ dành cho tài liệu như **192.0.2.0/24**, **198.51.100.0/24**, **203.0.113.0/24** và tên **example.test**. Thay chúng bằng tài sản thực tế **chỉ trong phạm vi được ủy quyền**.

### 1.1. Nguyên tắc an toàn

- Bắt đầu bằng **kiểm tra chỉ đọc**, nguồn log hiện có, số liệu giám sát và một phép thử kết nối có giới hạn. Không chạy quét diện rộng, tạo tải lớn, xóa cache, reset đường truyền hoặc sửa rule khi chưa có lý do và quyền phù hợp.
- **Không tắt firewall, IDS/IPS, xác thực chứng chỉ, MFA, phân đoạn mạng hoặc logging** chỉ để khiến kết nối hoạt động. Nếu cần thay đổi chính sách, dùng change/incident workflow, phạm vi tối thiểu, thời hạn, phê duyệt và rollback.
- Không gửi password, token, cookie, dữ liệu cá nhân, private key hoặc payload nhạy cảm vào ticket, log chia sẻ hay ảnh chụp màn hình. PCAP chỉ thực hiện khi được cho phép và phải quản lý quyền truy cập, thời hạn lưu trữ.
- Phân biệt **sự kiện quan sát được**, **giả thuyết nguyên nhân** và **hành động đã thực hiện**. Một phép ping thất bại không chứng minh toàn bộ đường mạng bị hỏng vì ICMP có thể bị chặn.
- Khi nhiều dịch vụ cùng ảnh hưởng hoặc có dấu hiệu tấn công, chuyển sang quy trình incident response của tổ chức; bảo toàn log và phối hợp SOC thay vì tự sửa tùy tiện.

## 2. Khung xử lý chuẩn: từ tiếp nhận đến đóng sự cố

Mỗi runbook bên dưới sử dụng cùng vòng lặp:

~~~mermaid
flowchart TD
    A["Tiếp nhận: ai, ở đâu, từ khi nào?"] --> B["Đánh giá mức ảnh hưởng\nvà điều kiện an toàn"]
    B --> C["Ghi nhận kết nối mong đợi\nsource → DNS → route → destination:port"]
    C --> D["Thu log, metrics và phép thử chỉ đọc"]
    D --> E{"Giả thuyết có bằng chứng?"}
    E -->|Chưa| F["Kiểm tra lớp tiếp theo\nhoặc chuyển nhóm phụ trách"]
    F --> D
    E -->|Có| G["Chọn phương án khắc phục\nđược phép + rollback"]
    G --> H["Xác minh: kết nối, bảo mật,\ntelemetry và tác động xung quanh"]
    H --> I{"Đạt tiêu chí khôi phục?"}
    I -->|Không| F
    I -->|Có| J["Cập nhật ticket / timeline\nvà phòng ngừa tái phát"]
~~~

### 2.1. Dữ liệu tối thiểu trong ticket

| Trường | Cần ghi |
| --- | --- |
| **Incident/change ID** | Mã hồ sơ và mức độ ưu tiên |
| **Thời gian** | Thời điểm bắt đầu, thời điểm quan sát; chuẩn UTC hoặc timezone rõ ràng |
| **Nguồn** | Tài sản, user/identity, IP hiện tại, subnet/VLAN/VPC/namespace, vị trí truy cập |
| **Đích** | FQDN, IP được trả lời, protocol, port, URL hoặc tên dịch vụ |
| **Đường dự kiến** | Wi-Fi/LAN → router → VPN/ZTNA → firewall/segment → proxy/LB → workload |
| **Triệu chứng** | Thông báo lỗi nguyên văn, bước bị lỗi, tần suất, có tái hiện được không |
| **Mức ảnh hưởng** | Số user/địa điểm/workload, có ảnh hưởng nghiệp vụ hay an toàn không |
| **Thay đổi gần đây** | DNS, policy, route, chứng chỉ, deploy, phiên bản agent, nhà mạng |
| **Kết quả thử** | Lệnh hoặc công cụ, thời gian, kết quả, event/request ID liên quan |
| **Owner và escalation** | Nhóm phụ trách, kênh on-call, thời hạn cập nhật |
| **Khôi phục** | Hành động được duyệt, bằng chứng trước/sau, rollback, nguyên nhân còn mở |

**Dấu hiệu đáng ưu tiên:** sự cố đồng loạt nhiều site, mất kết nối quản trị hạ tầng, dịch vụ bảo mật trung tâm ngừng hoạt động, xác thực diện rộng thất bại, lỗi route giữa mạng quan trọng, hoặc dấu hiệu lưu lượng độc hại/ảnh hưởng dữ liệu. Phân loại SEV dựa trên chuẩn nội bộ, không tự gắn mức độ chỉ từ một mã lỗi.

### 2.2. Câu hỏi khoanh vùng trong vài phút đầu

- Chỉ **một người**, **một thiết bị**, **một VLAN/site**, **một ứng dụng**, hay **nhiều vùng** bị ảnh hưởng?
- Dùng **tên miền** lỗi nhưng **IP** hoạt động, hay cả hai cùng lỗi?
- Lỗi bắt đầu **trước hoặc sau** thay đổi policy, route, DNS, chứng chỉ hoặc deploy?
- Có khác biệt giữa mạng có dây, Wi-Fi, VPN, kết nối trong VPC, từ Internet hay giữa các workload?
- Có bằng chứng dịch vụ đích đang lắng nghe đúng port và khỏe mạnh không?
- Lưu lượng bị chặn **đúng thiết kế bảo mật** hay do một cấu hình sai?
- Có đủ khả năng quan sát ở hai đầu và thiết bị trung gian chưa?

## 3. Bản đồ triệu chứng: chọn runbook phù hợp

| Dấu hiệu ban đầu | Lớp cần kiểm tra trước | Runbook |
| --- | --- | --- |
| Không có IP hợp lệ, địa chỉ tự gán, gateway trống | Link/Wi-Fi, VLAN, DHCP, NAC | §5 |
| Không phân giải được tên, trả sai địa chỉ | Resolver, DNS, split-horizon | §6 |
| Không có route, unreachable hoặc chỉ lỗi một subnet | Routing, ACL, NAT, overlay | §7 |
| Timeout đến đúng IP:port | TCP path, firewall, service, packet loss | §8 |
| Connection refused | Đích trả RST, listener, proxy | §8 |
| Firewall deny, policy miss, truy cập khác zone lỗi | Security policy/segmentation | §9 |
| VPN kết nối nhưng không tới ứng dụng | VPN route, ZTNA policy, identity | §10 |
| TLS handshake/certificate error | TLS, PKI, mTLS, thời gian hệ thống | §11 |
| HTTP 502/503/504, proxy error | Proxy, WAF, LB, backend | §12 |
| Chỉ lỗi khi ở Wi-Fi hoặc khi roaming | RF, 802.1X, DHCP, AP, NAC | §13 |
| Chỉ lỗi giữa cloud VPC hoặc Kubernetes services | Route, security group, NetworkPolicy, service endpoints | §14 |
| Mạng lúc nhanh lúc chậm; gói lớn bị treo | Loss, MTU, PMTUD, QoS, asymmetric routing | §15 |

### 3.1. Đọc lỗi theo lớp, tránh suy diễn

~~~text
Từ client đến dịch vụ:

Wi-Fi/Ethernet
   ↓
IP address + default gateway + local route
   ↓
DNS FQDN → IP          (nếu truy cập bằng tên)
   ↓
Route + NAT + firewall/segmentation + VPN/overlay
   ↓
TCP hoặc UDP đến đúng service port
   ↓
TLS handshake / identity / certificate
   ↓
HTTP/API/proxy/load balancer/service health
   ↓
Ứng dụng và dữ liệu phía sau
~~~

Mỗi bước là một phép kiểm tra **cần thiết trong một số đường đi**, không phải thứ tự tuyến tính bắt buộc. Ví dụ DNS có thể được thực hiện trước TCP; proxy có thể phân giải DNS thay client; ICMP không nhất thiết cùng policy với TCP; kết nối QUIC dùng UDP 443 thay cho TCP 443.

## 4. Bộ công cụ chẩn đoán chỉ đọc

Nên thực hiện phép thử từ **chính vị trí gặp lỗi** và, khi được phép, một vị trí đối chứng đã biết hoạt động. Nếu thử từ máy admin ở mạng quản trị, đường đi có thể khác hoàn toàn máy khách.

### 4.1. Linux

~~~bash
# Giao diện, địa chỉ, trạng thái link
ip -br address
ip -s link

# Route hiện có và route dự kiến tới đích
ip route
ip route get 198.51.100.20

# Resolver: khả dụng tùy distribution / DNS service
resolvectl status
resolvectl query api.example.test

# Công cụ DNS tùy hệ thống có cài đặt
dig api.example.test A
dig api.example.test AAAA

# Thử TCP/TLS/HTTP qua URL và port yêu cầu
curl -v --connect-timeout 5 --max-time 15 https://api.example.test/health

# Kiểm tra listener trên CHÍNH máy chủ đích (nếu có quyền)
ss -lntp

# Ping chỉ là một tín hiệu, có thể bị policy chặn
ping -c 4 198.51.100.20

# Quan sát đường đi ở mức hop (có thể thiếu/khác đường ứng dụng)
traceroute 198.51.100.20
~~~

Có thể dùng \`curl --resolve api.example.test:443:198.51.100.20 https://api.example.test/health\` để thử **tạm thời** ánh xạ tên sang IP cho riêng lệnh curl, vẫn giữ tên cho TLS/SNI và kiểm tra chứng chỉ. Phép thử chỉ phù hợp nếu kết nối trực tiếp là đường hợp lệ; khi ứng dụng bắt buộc đi qua proxy, service mesh hoặc gateway, không được sử dụng kết quả này để kết luận đường thực tế. Không dùng \`curl -k\` để hợp thức hóa lỗi chứng chỉ.

### 4.2. Windows PowerShell

~~~powershell
# Địa chỉ, DNS server, gateway
Get-NetIPConfiguration
Get-DnsClientServerAddress
Get-NetRoute

# Truy vấn DNS
Resolve-DnsName api.example.test -Type A
Resolve-DnsName api.example.test -Type AAAA

# Thử TCP port và route quan sát từ client
Test-NetConnection api.example.test -Port 443 -InformationLevel Detailed

# Thông tin mạng dạng truyền thống
ipconfig /all
route print

# Kiểm tra interface
Get-NetAdapter
~~~

\`Test-NetConnection\` với \`-Port\` kiểm tra khả năng thiết lập TCP, **không chứng minh HTTPS, TLS, xác thực hoặc ứng dụng hoạt động**. Trường \`PingSucceeded: False\` có thể do ICMP bị chặn. Dùng công cụ HTTP/API riêng để xác thực chức năng dịch vụ.

### 4.3. Thiết bị mạng và cloud

Trên router/firewall/switch, ưu tiên truy vấn **read-only** trong giao diện hoặc CLI của sản phẩm: trạng thái interface, VLAN, VRF, route/FIB, session table, policy hit count, NAT translation, deny log, tunnel status, dropped packets và HA failover events. Cú pháp khác nhau theo hãng; không áp một lệnh giả định cho mọi thiết bị.

Trong cloud, đối chiếu route table, security group/NSG, network ACL, flow logs, load balancer target health và audit events. Cloud console hiển thị “allow” ở một lớp chưa chứng minh các lớp khác đều cho phép. Cần kiểm tra chiều đi và chiều về.

### 4.4. Thu thập gói khi cần

Khi log, metric và phép thử không đủ giải thích, người được ủy quyền có thể capture có giới hạn thời gian, số gói, phạm vi IP/port và độ dài snaplen.

~~~bash
# Ví dụ lab, chạy trên interface thật đã xác nhận trong phạm vi cho phép.
# Capture giới hạn 100 packet, 96 byte đầu mỗi packet; file vẫn có metadata nhạy cảm.
sudo tcpdump -ni eth0 -c 100 -s 96 \
  'host 198.51.100.20 and tcp port 443'
~~~

Không tự động gửi PCAP lên dịch vụ bên ngoài hoặc chia sẻ công khai. Capture ở một đầu chỉ cho thấy góc nhìn của đầu đó; muốn kết luận gói rơi ở đâu phải đối chiếu thêm log hoặc quan sát ở phía trung gian/đích. Với TLS, payload thường mã hóa; không vì thế mà tự giải mã lưu lượng người dùng ngoài phạm vi cho phép.

## 5. Runbook A — Không có địa chỉ IP, gateway hoặc kết nối lớp truy nhập

**Triệu chứng:** máy không lấy được địa chỉ hợp lệ; hệ điều hành báo “No Internet”; chỉ một VLAN/SSID gặp lỗi; có địa chỉ tự gán 169.254.0.0/16 khi kỳ vọng DHCP IPv4; không thấy default gateway.

**Phạm vi cần phân biệt:** lỗi vật lý/Wi-Fi, sai VLAN, NAC/802.1X, pool DHCP hết địa chỉ, DHCP relay sai, gateway/down hoặc cấu hình IP tĩnh sai.

**Bước kiểm tra:**

1. Xác nhận interface nào thực sự dùng để truy cập, link status, SSID/BSSID, VLAN và mạng kỳ vọng. Máy có nhiều NIC/VPN có thể chọn nhầm interface.
2. So sánh địa chỉ IP, prefix, gateway và DNS server với **IPAM** hoặc cấu hình mạng chuẩn; kiểm tra trùng IP nếu có dấu hiệu.
3. Với DHCP: tra lease, DHCP Discover/Offer/Request/Ack theo log hệ thống hoặc capture được phép; xem pool còn cấp được địa chỉ không, DHCP relay có tới server không.
4. Với mạng có NAC: xem kết quả 802.1X, trạng thái chứng chỉ, VLAN được gán và thông báo từ RADIUS/NAC.
5. Kiểm tra switch port/AP, lỗi interface, flapping, cổng bị quarantine hoặc segmentation policy.
6. So sánh một thiết bị cùng VLAN và một thiết bị ở VLAN khác để xác định phạm vi.

**Kết luận định hướng:**

| Quan sát | Giả thuyết ưu tiên |
| --- | --- |
| Link down, cáp/AP không hoạt động | Vật lý, AP/switch, interface |
| Link up nhưng không thấy DHCP Offer | DHCP server/relay, VLAN, ACL trên đường DHCP |
| Có lease nhưng gateway sai | Scope/DHCP option, cấu hình tĩnh, IPAM |
| RADIUS reject, chỉ user nhất định lỗi | 802.1X identity/certificate/posture, chính sách NAC |
| Có IP/gateway đúng nhưng không ra ngoài | Chuyển sang routing, DNS hoặc firewall ở §6–§9 |

**Khắc phục có kiểm soát:** chuyển cho owner của switch/AP, DHCP, NAC hoặc network platform; chỉnh cấu hình theo change procedure, tránh mass renew hoặc restart DHCP toàn site khi chưa biết ảnh hưởng. **Đạt yêu cầu:** client lấy đúng địa chỉ, gateway và resolver; lưu lượng hợp lệ qua segment được phép; log NAC/DHCP không còn lỗi; kiểm tra một thiết bị đối chứng.

## 6. Runbook B — Lỗi DNS hoặc phân giải sai tên

**Triệu chứng:** \`Could not resolve host\`, \`DNS_PROBE_FINISHED_NXDOMAIN\`, \`SERVFAIL\`, phân giải tới IP cũ, hoặc chỉ không truy cập được bằng hostname.

**Bước kiểm tra:**

1. Ghi rõ FQDN, loại bản ghi (A, AAAA, CNAME, SRV...), resolver được hệ điều hành/ứng dụng sử dụng, thời điểm và mạng nguồn.
2. Truy vấn cùng FQDN bằng resolver đang dùng. Phân biệt:
   - **NXDOMAIN:** resolver báo tên không tồn tại theo ngữ cảnh trả lời hiện tại; có thể sai tên, sai zone/view hoặc cache phủ định.
   - **SERVFAIL:** truy vấn không hoàn tất thành công; xem forwarder, authoritative zone, DNSSEC validation, upstream hoặc lỗi dịch vụ.
   - **NOERROR không có bản ghi loại mong đợi:** tên có thể tồn tại nhưng thiếu bản ghi A/AAAA cần dùng.
   - **Timeout:** resolver không phản hồi hoặc đường UDP/TCP 53 bị ảnh hưởng.
3. So sánh phản hồi từ **resolver được phê duyệt** ở hai vị trí có/không lỗi; chú ý split-horizon và private DNS. Không tự dùng resolver công cộng để bỏ qua chính sách doanh nghiệp.
4. Đối chiếu TTL, bản ghi authoritative, lần thay đổi gần đây, zone delegation, forwarder, policy chặn tên miền và bản ghi cache.
5. Xác minh khác biệt IPv4/IPv6: một host có A hoạt động nhưng AAAA trỏ tới đường không thông có thể gây lỗi tùy ứng dụng/hệ điều hành.
6. Nếu IP phân giải được nhưng TCP/TLS lỗi, chuyển §7, §8 hoặc §11.

**Tình huống mẫu:** \`api.example.test\` tại văn phòng A trả 198.51.100.20, tại VPN trả 203.0.113.10. Trước khi sửa DNS, xác nhận hai view có cố ý khác nhau không; nếu cùng một hostname phục vụ hai môi trường, mỗi view có thể hợp lệ.

**Khắc phục:** sửa zone, delegations, resolver/forwarder hoặc policy DNS thông qua owner và change; tránh xóa cache toàn hệ thống để “thử vận may” vì có thể che dấu nguyên nhân. **Xác minh:** truy vấn đúng từ từng view cần thiết, kết nối đến IP tương ứng hoạt động, log resolver không ghi lỗi, TTL và kết quả ứng dụng ổn định.

## 7. Runbook C — Không có đường định tuyến hoặc unreachable

**Triệu chứng:** \`Network is unreachable\`, \`No route to host\`, \`Destination unreachable\`, chỉ một subnet/VPC/site lỗi, hoặc trace cho thấy tuyến không như dự kiến.

**Bước kiểm tra:**

1. Xác nhận IP đích hiện tại và route từ máy nguồn (\`ip route get\` hoặc bảng route Windows); xác định gateway/VRF/interface được chọn.
2. Từ **cả hai phía nếu được phép**, kiểm tra route tới địa chỉ đối phương; route chiều về rất quan trọng, đặc biệt khi dùng NAT, peering, VPN hay tunnel.
3. Kiểm tra route table/FIB trên gateway, route specificity, policy-based routing, quảng bá BGP/OSPF, subnet overlap, next-hop health và route propagation.
4. Đối chiếu ACL/firewall: thông báo “host unreachable” có thể do thiết bị trung gian chủ động trả ICMP; cũng có trường hợp firewall chỉ drop khiến nhìn giống timeout.
5. Nếu đường đi qua tunnel, kiểm tra trạng thái, selector, peer routes, MTU và route export/import.
6. Với NAT, xác nhận vị trí NAT, mapping nguồn/đích, trạng thái session và địa chỉ mà firewall downstream thực sự nhìn thấy.

~~~text
Nguồn 192.0.2.15
    ↓ default gateway/VRF
Router A ── route/ACL/NAT ── Router B
    ↓                           ↓
Log phía nguồn             Log phía đích
    └──────── Đối chiếu chiều về ────────┘
Đích 198.51.100.20:443
~~~

**Cảnh báo diễn giải:** traceroute không hiển thị một hop không có nghĩa hop bị lỗi; ICMP TTL-exceeded có thể bị rate-limit hoặc chặn. Mạng ECMP hoặc bất đối xứng cũng khiến đường probe khác đường ứng dụng.

**Khắc phục:** khôi phục route thiếu, sửa next hop/propagation/VRF theo thẩm quyền; nếu có xung đột CIDR, cần quyết định kiến trúc thay vì thêm route tạm không kiểm soát. **Xác minh:** route hai chiều, kết nối đúng port thành công, phân đoạn vẫn đúng yêu cầu và không mở đường bypass.

## 8. Runbook D — TCP timeout, connection refused hoặc mất gói

**Triệu chứng:** \`Connection timed out\`, \`Connection refused\`, bắt tay chậm, tải dữ liệu gián đoạn hoặc chỉ một port không dùng được.

### 8.1. Phân biệt các quan sát

| Quan sát | Diễn giải thận trọng | Việc cần làm |
| --- | --- | --- |
| SYN gửi đi nhưng không thấy trả lời | Có thể drop, mất gói, đích không tới, listener không đáp ứng hoặc đường về lỗi | So sánh log/sensor dọc đường, route hai chiều, chính sách |
| SYN → RST | Một thiết bị trả lời từ chối TCP, thường do không có listener hoặc reject policy | Xác nhận nguồn phát RST, service/listener, firewall |
| SYN → SYN-ACK → ACK | TCP đã thiết lập; lỗi có thể ở TLS, proxy, app hoặc về sau | Kiểm tra TLS/HTTP và application logs |
| SYN retransmission tăng | Loss, drops, congestion, policy hoặc phản hồi không tới | So sánh metrics interface, firewall, flow, path |
| TCP thiết lập nhưng API vẫn timeout | Kết nối transport chưa chứng minh backend phản hồi | Chuyển TLS, proxy, LB hoặc ứng dụng |
| Chỉ UDP lỗi | UDP path, state tracking, ACL, timeout, NAT hoặc dịch vụ đích | Dùng phép thử UDP phù hợp, tránh suy từ TCP |

### 8.2. Quy trình

1. Xác minh **destination IP + port + protocol** và loại thông báo. Có thể service dùng port khác cổng hiển thị trong URL do proxy/LB.
2. Kiểm tra client có chọn đúng IP IPv4/IPv6, proxy hoặc gateway không; dùng công cụ kết nối đúng ứng dụng.
3. Ở máy đích, kiểm tra listener (\`ss -lntp\` hoặc công cụ OS tương ứng) và health của service. Listener trên \`127.0.0.1\` không tự tiếp nhận kết nối từ mạng bên ngoài.
4. Đối chiếu firewall/ACL/NAT: quyết định allow/deny, session state, policy ID, route chiều về, các lỗi conntrack/NAT saturation.
5. Đọc counters interface: drops, errors, retransmission, RTT; kiểm tra đặc tính tải theo thời gian thay vì đo một gói duy nhất.
6. Khi bằng chứng chưa đủ, thu capture có giới hạn tại nguồn và đích để xác định SYN/SYN-ACK/RST đi tới đâu, có được phép và có giữ an toàn dữ liệu hay không.

**Khắc phục:** nếu thiếu listener, chuyển application owner; nếu rule sai, dùng quy trình change; nếu quá tải, đánh giá capacity/connection limit và điều chỉnh có kiểm soát; nếu packet loss do phần cứng, chuyển network platform. **Xác minh:** thiết lập đúng giao thức, phản hồi tầng ứng dụng trong SLO, log không báo bất thường và không tạo mở rộng quyền truy cập.

## 9. Runbook E — Firewall, ACL, segmentation hoặc IDS/IPS chặn kết nối

**Triệu chứng:** firewall có log deny, đổi VLAN thì lỗi, traffic east–west bị chặn, IDS/IPS báo signature rồi terminate session, hoặc luồng hợp lệ ngừng sau thay đổi rule.

**Bước kiểm tra:**

1. Thu **flow tuple** có ngữ cảnh: thời gian UTC, source/destination IP, port, protocol, source/destination zone, user/workload identity và thiết bị enforcement.
2. Đọc rule/policy ID từ log hoặc kiểm tra session; xác nhận **rule có hiệu lực** trên đúng đường đi, không chỉ policy định nghĩa trong repository.
3. So sánh với **ma trận luồng được phê duyệt**: có yêu cầu hợp lệ không, segment này có được phép trao đổi với segment kia không, flow có cần mTLS/ZTNA không?
4. Kiểm tra NAT trước/sau policy, thứ tự rule, firewall HA, asymmetric routing, stateful inspection và deny do IPS, WAF, DLP hay threat feed.
5. Phân loại: **deny đúng chính sách**, **rule thiếu cho luồng hợp lệ**, **false positive**, **route bypass**, hay **log thiếu thông tin**.
6. Nếu là cảnh báo xâm nhập hoặc có dấu hiệu tấn công, phối hợp SOC/Incident Response trước khi thay đổi enforcement.

**Không thực hiện:** tạo rule \`any → any\`, bỏ toàn bộ IDS/IPS inspection, gỡ segmentation, xóa blocklist diện rộng hoặc tắt log chỉ để test. Nếu rule cần ngoại lệ, phải xác định đích, nguồn, dịch vụ, thời hạn và người phê duyệt.

**Khắc phục:** nếu deny đúng policy, trả kết quả và đề xuất luồng thay thế được duyệt; nếu thiếu rule hợp lệ, áp dụng least privilege qua change; nếu false positive, hiệu chỉnh ngoại lệ hẹp hoặc chữ ký theo quy trình security. **Xác minh:** luồng hợp lệ hoạt động và **negative test** vẫn bị chặn, có event ID chứng minh enforcement/telemetry.

## 10. Runbook F — VPN, ZTNA hoặc truy cập từ xa

**Triệu chứng:** không kết nối được VPN, tunnel up nhưng ứng dụng nội bộ không truy cập được, một nhóm user bị policy deny, split-tunnel gây khác biệt, hoặc token xác thực hết hạn.

**Bước kiểm tra:**

1. Phân biệt **không xác thực được**, **không lập tunnel được**, **tunnel lập nhưng không được cấp route**, và **được cấp route nhưng đích từ chối**.
2. Kiểm tra log client/gateway: auth result, MFA, device posture, chứng chỉ, session expiry, assigned IP/route/DNS và policy decision; ẩn mọi token.
3. Xác nhận tunnel interface, DNS split-view, route ưu tiên và các subnet được phép sau khi kết nối.
4. Xác nhận **identity của user**, posture của thiết bị và nhóm quyền khớp với tài nguyên đích; VPN “connected” không tự chứng minh user được vào mọi mạng nội bộ.
5. Với truy cập qua ZTNA, kiểm tra connector, health ứng dụng, identity-based policy và lớp xác thực ứng dụng.
6. Với IPsec/site-to-site, kiểm tra trạng thái IKE/SA, selectors, rekey, route, NAT traversal và time synchronization theo log của sản phẩm; không ghi khóa bí mật vào hồ sơ.

**Khắc phục:** IAM/ZTNA owner xử lý xác thực/policy; network platform xử lý tunnel và route; application owner xác nhận dịch vụ. Không tắt MFA hoặc cấp nhóm admin rộng để giải quyết tạm. **Xác minh:** user thử nghiệm có quyền truy cập đúng ứng dụng, user đối chứng không có quyền vẫn bị chặn, log truy cập đầy đủ và phiên hoạt động ổn định.

## 11. Runbook G — TLS, mTLS và chứng chỉ

**Triệu chứng:** \`certificate verify failed\`, \`hostname mismatch\`, \`unknown ca\`, \`handshake failure\`, \`bad certificate\` hoặc kết nối TCP thành công nhưng HTTPS thất bại.

### 11.1. Các nhóm nguyên nhân

| Dấu hiệu | Nguyên nhân cần xác minh |
| --- | --- |
| Certificate expired / not yet valid | Hạn chứng chỉ hoặc đồng hồ client/server không đúng |
| Hostname mismatch | Tên truy cập không khớp SAN của certificate |
| Unknown CA / unable to build chain | Trust store chưa tin cậy CA hoặc server thiếu intermediate |
| Handshake failure | Version TLS/cipher suite/SNI/ALPN không tương thích hoặc policy chặn |
| mTLS certificate rejected | Client cert sai danh tính, hết hạn, không được tin cậy hoặc không đúng policy |
| TLS reset sau proxy | TLS interception, backend TLS policy hoặc proxy/WAF xử lý lỗi |

### 11.2. Quy trình

1. Xác nhận FQDN, service port, hostname được dùng cho SNI, TLS termination point (proxy/LB/backend) và trust store của client.
2. Đối chiếu certificate chain, SAN, thời gian hiệu lực, issuer, mTLS requirement và lịch rotation.
3. Kiểm tra thời gian hệ thống/NTP; lệch thời gian có thể khiến xác minh chứng chỉ thất bại.
4. Từ client được phép, dùng công cụ chẩn đoán bắt tay TLS. Ví dụ:

~~~bash
# Phép thử TLS chỉ đọc tới hostname và port được ủy quyền.
openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -verify_return_error
~~~

5. Nếu TLS termination tại load balancer, kiểm tra chứng chỉ trên listener và kết nối TLS tới backend **riêng biệt**. Sự thành công ở client → LB không chứng minh LB → backend cũng thành công.
6. Đối chiếu bản ghi audit thay đổi CA/certificate, certificate manager, secret distribution và log ứng dụng.

**Khắc phục:** cấp/gia hạn chứng chỉ đúng SAN và chain, sửa trust bundle hoặc policy tương thích trong phạm vi an toàn, khôi phục NTP, cập nhật cấu hình mTLS theo owner. Không dùng \`--insecure\`, \`-k\` hoặc tắt certificate verification như cách sửa lâu dài. **Xác minh:** TLS handshake tin cậy, đúng danh tính và chính sách, ứng dụng trả response hợp lệ, cả đầu vào lẫn backend hoạt động.

## 12. Runbook H — Proxy, WAF, load balancer và lỗi HTTP

**Triệu chứng:** có kết nối TCP/TLS nhưng nhận \`HTTP 403\`, \`407\`, \`429\`, \`502\`, \`503\`, \`504\`; một backend lỗi, một đường truy cập tốt hơn đường khác.

| HTTP / biểu hiện | Cách hiểu ban đầu | Kiểm tra tiếp |
| --- | --- | --- |
| **403 Forbidden** | Request bị từ chối bởi authorization, WAF hoặc policy khác | Nguồn phát 403, WAF rule ID, app auth |
| **407 Proxy Authentication Required** | Proxy yêu cầu xác thực | Proxy credentials/session, config, identity |
| **429 Too Many Requests** | Rate limit / quota | Thời điểm, key, route, chính sách và tải |
| **502 Bad Gateway** | Proxy/LB nhận phản hồi lỗi hoặc không hợp lệ từ upstream | Backend connection/TLS, process, gateway logs |
| **503 Service Unavailable** | Không có backend đủ điều kiện, bảo trì, quá tải hoặc lỗi app | Target health, health check, autoscaling |
| **504 Gateway Timeout** | Proxy/LB quá hạn chờ upstream | Backend latency, route, timeouts, dependency |
| TCP OK nhưng 404 | Đã tới một HTTP endpoint, nhưng path/routing/app không trả tài nguyên | Host header, path rewrite, virtual host |

Mã HTTP thường do **một lớp trung gian cụ thể** tạo ra; không nên khẳng định 503 luôn do backend down. Cần xác định actor tạo response qua headers được phép, request ID và log tương ứng.

**Bước kiểm tra:**

1. Ghi URL, method, request ID (nếu có), Host header, SNI, source network và thời gian. Giữ an toàn dữ liệu truy vấn và auth header.
2. Kiểm tra proxy configuration, biến môi trường \`HTTP_PROXY\`/\`HTTPS_PROXY\`, PAC nếu có, DNS của proxy và connectivity tới upstream.
3. Với WAF: tìm matching rule, bot/rate controls, source reputation, request sample đã được ẩn dữ liệu nhạy cảm; phân biệt block bảo mật hợp lệ và false positive.
4. Với LB: kiểm tra listener, target group, health check path/port, số backend healthy, lỗi TLS/backend, connection draining và thời điểm deploy.
5. Đối chiếu ứng dụng: logs, dependency health, latency, application-level readiness; kiểm tra khác biệt giữa readiness và liveness nếu dùng orchestrator.
6. Nếu chỉ một vùng/route lỗi, so sánh traffic steering và backend pool; không phân phối toàn bộ traffic tới vùng chưa được kiểm thử.

**Khắc phục:** sửa health check, routing, upstream config hoặc triển khai bản rollback qua owner thích hợp; ngoại lệ WAF phải hẹp và phê duyệt. **Xác minh:** HTTP status và response body đúng kỳ vọng, độ trễ trong SLO, không phát sinh bypass WAF, bộ đếm 5xx/4xx trở lại baseline.

## 13. Runbook I — Wi-Fi, 802.1X và truy cập thiết bị

**Triệu chứng:** một SSID kết nối chập chờn; thiết bị đăng nhập Wi-Fi nhưng không lấy IP; chỉ một khu vực bị ảnh hưởng; 802.1X reject; người dùng di chuyển giữa AP thì phiên bị gián đoạn.

**Bước kiểm tra:**

1. Xác định SSID, AP/BSSID, radio band, cường độ tín hiệu, chất lượng kết nối, thời điểm roam và mật độ thiết bị; dữ liệu này mang tính tình huống và có thể thay đổi nhanh.
2. Kiểm tra trạng thái association/authentication, EAP/RADIUS, chứng chỉ và gán VLAN qua NAC.
3. Xác nhận DHCP và DNS sau khi đã kết nối Wi-Fi; lớp 802.11 thành công không đồng nghĩa có IP hoặc truy cập Internet.
4. So sánh cùng user với thiết bị khác; cùng thiết bị tại AP khác; mạng có dây hoặc SSID khác, nếu quy trình cho phép.
5. Kiểm tra AP uplink, switch port, PoE, radio interference, công suất, channel utilization, cơ chế roaming và chính sách guest isolation.
6. Đối chiếu log controller với log NAC và sự kiện client cùng timestamp.

**Khắc phục:** nhóm Wi-Fi/NAC điều chỉnh cấu hình AP/RADIUS hoặc DHCP được duyệt; không tắt 802.1X và không nối mạng khách vào VLAN nội bộ. **Xác minh:** thiết bị được xác thực đúng danh tính, nhận đúng VLAN, giữ kết nối khi di chuyển trong phạm vi thử nghiệm và không truy cập được zone bị cấm.

## 14. Runbook J — Cloud VPC/VNet và Kubernetes

### 14.1. Cloud network

**Triệu chứng:** máy ảo trong một subnet không vào được service ở subnet/VPC khác; sau deploy tài nguyên mới mất kết nối; public/private endpoint hoạt động khác nhau; site-to-cloud lỗi.

**Bước kiểm tra:**

1. Xác minh source/destination resource ID, IP private/public, subnet, route table và endpoint DNS trả về từ chính workload.
2. Kiểm tra effective routes, transit/peering attachments, return path, CIDR overlap, NAT/egress gateway và network appliance.
3. Đối chiếu **stateful security groups/NSGs** và **stateless network ACLs** theo đặc tính thực tế của nhà cung cấp; đánh giá chiều đi/về và ephemeral return traffic theo sản phẩm.
4. Xác minh private DNS zone, private link/endpoint, firewall inspection routing và proxy requirements.
5. Tra flow logs, LB health, cloud audit log tại thời điểm sự cố; phát hiện config drift sau thay đổi hạ tầng-as-code.
6. Tách lỗi provider/service disruption khỏi cấu hình của tenant bằng trạng thái dịch vụ, metrics và phép thử đối chứng.

**Xử lý:** chỉnh policy, route hoặc endpoint thông qua cloud/network platform và IaC/change đã phê duyệt. Không tạo public IP hoặc mở toàn bộ security group như giải pháp tạm thiếu kiểm soát. **Xác minh:** flow hai chiều đúng, luồng được phép đi qua điểm bảo vệ bắt buộc, flow logs có thể truy xuất và negative control vẫn bị chặn.

### 14.2. Kubernetes: service reachable hay network policy deny?

**Triệu chứng:** Pod không gọi được Service, lỗi chỉ ở một namespace, ingress trả 503, hoặc connection timeout sau thay đổi NetworkPolicy.

Một số lệnh chỉ đọc trong namespace thử nghiệm:

~~~bash
kubectl get pods -n application-prod -o wide
kubectl get services -n application-prod
kubectl get endpointslices -n application-prod
kubectl get networkpolicies -n application-prod
kubectl describe service internal-api -n application-prod
kubectl describe pod backend-pod -n application-prod
~~~

Không tự cho rằng một NetworkPolicy đã được enforcement nếu CNI không hỗ trợ hoặc cấu hình mạng thực tế có ngoại lệ.

**Bước kiểm tra:**

1. Xác nhận service name/namespace, port, \`targetPort\`, selectors, endpoint slices và pod readiness; Service tồn tại nhưng không có endpoint khỏe mạnh thường không thể nhận traffic như mong đợi.
2. Kiểm tra DNS nội bộ cluster và khả năng giải tên từ workload đang lỗi, không chỉ từ node quản trị.
3. Kiểm tra policy ingress **ở đích** và egress **ở nguồn**, cùng các global/cluster policy của CNI nếu có; xác nhận chính sách có áp lên pod labels thực tế.
4. Kiểm tra kube-proxy/eBPF datapath, CNI health, overlay/underlay, MTU và kết nối node-to-node theo cách phù hợp nền tảng.
5. Nếu có service mesh, xác minh sidecar/ambient policy, mTLS, service identity và traffic routing; mesh configuration cũng có thể là nguyên nhân lỗi.
6. Kiểm tra ingress controller/LB, backend readiness, sự kiện deploy gần nhất và resource pressure.

**Khắc phục:** sửa selector, readiness, service port hoặc policy một cách có kiểm soát; nhóm platform và app owner cùng xác nhận. Không xóa hàng loạt NetworkPolicy để kiểm tra. **Xác minh:** positive test qua Service hoạt động và negative test từ namespace không được phép vẫn bị chặn; metrics và log mạng đủ phục vụ truy vết.

## 15. Runbook K — Chập chờn, độ trễ, MTU hoặc đường đi bất đối xứng

**Triệu chứng:** kết nối vẫn thiết lập nhưng tải file lớn bị treo, một số request timeout, chỉ UDP/QUIC gặp lỗi, hiệu năng kém sau bật VPN/overlay hoặc chỉ ảnh hưởng lưu lượng xuyên nhiều lớp encapsulation.

**Bước kiểm tra:**

1. Xác định **baseline**, thời điểm và pattern: chỉ giờ cao điểm, chỉ gói lớn, chỉ một hướng, hay mọi luồng.
2. Đối chiếu throughput/RTT/jitter/packet loss từ telemetry hoặc phép thử có giới hạn; phân biệt network latency với thời gian xử lý backend.
3. Kiểm tra interface error/drop, queue, congestion, bandwidth saturation, QoS/shaping và giới hạn session/conntrack/NAT.
4. Xác minh **MTU ở từng chặng**, overhead của VPN/GRE/VXLAN/IPsec, Path MTU Discovery (PMTUD) và ICMP cần thiết. Một kết nối TCP có thể bắt tay bình thường nhưng bị treo khi gửi segment lớn.
5. Nếu có dual-stack, đối chiếu IPv4/IPv6 và đường đi hai chiều. IPv6 route hoặc firewall không đồng nhất có thể gây lỗi chỉ với một số client.
6. Xem ECMP/asymmetric routing: stateful firewall có thể thấy một chiều và drop chiều còn lại; phải kiểm chứng trên session logs và flow path.
7. Xem các thay đổi mới: firmware, route, BGP convergence, profile VPN, tunnel MTU, policy IPS và dịch vụ CDN/LB.

### 15.1. Lưu ý về phép thử MTU

- Kiểm tra kích thước gói phải xét cả IPv4/IPv6 headers, transport headers và overhead tunnel.
- Một số công cụ ping hỗ trợ đặt kích thước và cờ không phân mảnh, nhưng cú pháp và ý nghĩa khác nhau theo OS; cần chọn đúng công cụ, tránh gửi tải lớn.
- ICMP bị chặn không mặc nhiên chứng minh lỗi PMTUD; cần kết hợp log, MSS/MTU quan sát, counters và capture trong phạm vi cho phép.
- Không giảm MTU toàn hệ thống khi chưa xác nhận lớp xảy ra lỗi; điều này có thể che giấu sự cố routing/policy và ảnh hưởng workload khác.

**Khắc phục:** sửa PMTUD/ICMP policy cần thiết, MTU/tunnel hoặc MSS clamping **nếu phù hợp kiến trúc và đã kiểm chứng**; xử lý congestion/capacity qua owner. **Xác minh:** truyền dữ liệu kích thước thực tế thành công, các luồng khác không bị suy giảm, counters/latency ổn định và control security vẫn thực thi.

## 16. Khi dữ liệu mâu thuẫn: bảng xác định nguyên nhân

Trong sự cố phức tạp, nhiều công cụ có thể cho kết quả khác nhau. Cần ưu tiên **bằng chứng từ cùng flow, cùng thời gian và cùng đường đi**, thay vì ghép các phép thử không tương đương.

| Hiện tượng | Không nên kết luận vội | Phép kiểm chứng cần thêm |
| --- | --- | --- |
| Ping tới đích thất bại nhưng HTTPS hoạt động | “Mạng hỏng” | ICMP có thể bị chặn; kiểm tra TCP/TLS/HTTP đúng port |
| DNS trả kết quả nhưng HTTPS không vào | “DNS tốt thì mọi thứ tốt” | Route, TCP, TLS, proxy, application health |
| Firewall log allow nhưng client timeout | “Firewall không liên quan” | Có route hồi đáp, NAT, IPS, downstream firewall và service không? |
| Client thấy RST | “Ứng dụng chủ động reject” | RST có thể do firewall/proxy; kiểm tra vị trí sinh RST |
| VPN báo connected | “Đã truy cập được toàn mạng” | Split routes, ZTNA authorization, DNS, segment policy |
| TCP thành công | “Dịch vụ khỏe” | TLS, HTTP status, backend dependencies, response latency |
| DNS của máy admin đúng | “Client cũng phân giải đúng” | Split DNS, proxy DNS, cache và network context khác nhau |
| Kubernetes Service tồn tại | “Service có backend khỏe” | EndpointSlice, pod readiness, CNI/NetworkPolicy |
| Route table có đường hợp lệ | “Mọi gói đều đến đích” | Next-hop health, ACL, MTU, session, đường về |
| IPS sinh alert | “Đã ngăn chặn lưu lượng” | IDS chỉ phát hiện hay IPS đã block; đọc action, disposition |

### 16.1. Phương pháp đối chứng tối thiểu

Thay đổi **một biến mỗi lần** nếu có thể:

- Cùng client, cùng đường mạng, cùng dịch vụ nhưng hostname và địa chỉ phân giải được so sánh.
- Cùng ứng dụng và cấu hình, thử từ hai zone có chính sách khác nhau.
- Cùng subnet nhưng hai máy có posture hoặc identity khác nhau.
- Cùng FQDN trước và sau thay đổi DNS (theo cửa sổ TTL).
- Cùng deployment qua hai backend hoặc vùng, có bằng chứng request routing.

Đối chứng giúp khoanh vùng nhưng không tạo quyền bypass. Nếu tuyến thay thế vi phạm phân đoạn hoặc yêu cầu bảo mật, không dùng làm phép thử production.

## 17. Cây quyết định nhanh cho ca trực

~~~mermaid
flowchart TD
    A["Không kết nối được dịch vụ"] --> B{"Client có IP, gateway, link đúng?"}
    B -->|Không| C["§5 L2 / DHCP / NAC / Wi-Fi"]
    B -->|Có| D{"Truy cập bằng hostname?"}
    D -->|Có| E{"DNS đúng view và trả IP hợp lệ?"}
    E -->|Không| F["§6 DNS"]
    E -->|Có| G{"Có route hợp lệ tới đích?"}
    D -->|Không| G
    G -->|Không| H["§7 Routing / tunnel / NAT"]
    G -->|Có| I{"TCP/UDP tới đúng service port?"}
    I -->|Không| J["§8-10 Firewall / TCP / VPN / cloud path"]
    I -->|Có| K{"TLS/mTLS thành công?"}
    K -->|Không| L["§11 TLS / PKI"]
    K -->|Có| M{"Lớp HTTP/API trả kết quả đúng?"}
    M -->|Không| N["§12-14 Proxy / LB / app / K8s"]
    M -->|Có| O{"Đạt SLO và ổn định?"}
    O -->|Không| P["§15 Loss / MTU / QoS"]
    O -->|Có| Q["Đối chiếu log bảo mật,\nđóng ticket có chứng cứ"]
~~~

**Điểm kiểm soát:** cây này mô tả lộ trình chẩn đoán thông thường cho TCP/HTTPS. Với UDP-only, ICMP, proxy tạo kết nối riêng, mTLS nhiều hop hoặc các giao thức khác, kỹ sư phải điều chỉnh nhánh sao cho phù hợp kiến trúc thực tế.

## 18. Phân vai, điều kiện chuyển cấp và giao tiếp

| Nhóm | Vấn đề phụ trách điển hình | Thông tin cần gửi khi escalation |
| --- | --- | --- |
| Helpdesk/endpoint | NIC, DHCP phía client, cấu hình proxy, user/device state | Asset, interface, thời điểm, lỗi chính xác, kết quả client |
| Network operations | Switch/router, VLAN, routing, tunnel, NAT, HA | Source/dest, route path, interface counters, thay đổi gần đây |
| DNS/PKI/IAM | Resolver, zone, certificate, trust, authentication | FQDN, resolver, error code, cert info không chứa key, auth event |
| Network security | Firewall, segmentation, ZTNA policy, IPS/WAF | Flow tuple, rule ID, policy purpose, requested business access |
| Cloud/Kubernetes platform | VPC/NSG, CNI, service routing, cluster networking | Resource/namespace, route/policy, endpoint, flow logs |
| Application/SRE | Listener, backend, health check, app logs, latency | Request ID, HTTP status, hostname, timeout, deployment version |
| SOC/Incident response | Dấu hiệu tấn công, data exfiltration, bất thường log | Timeline, raw event references, các thay đổi đã thực hiện |

Một escalation tốt tránh câu “mạng bị lỗi” chung chung:

> Từ workload \`web-a\` (192.0.2.15, zone APP) tới \`api.example.test\` (198.51.100.20:443), từ 08:45 UTC ngày kiểm thử: DNS trả đúng IP, route chọn gateway G1, TCP SYN timeout. Firewall nội bộ có deny event ID \`fw-2741\` theo policy \`APP-TO-DATA\`. Chưa thay đổi cấu hình. Đề nghị nhóm Network Security kiểm tra liệu đây là deny đúng thiết kế hay thiếu policy cho luồng được phê duyệt; owner ứng dụng cung cấp change request \`NET-321\`.

Khi có ảnh hưởng lớn, cần thông báo **phạm vi đã xác nhận**, **hành động đang được duyệt/thực hiện**, **giải pháp giảm tác động hợp lệ** và **thời điểm cập nhật tiếp theo** theo quy định. Tránh công bố “đã tìm thấy nguyên nhân” nếu mới chỉ có giả thuyết.

## 19. Hai tình huống thực hành từ đầu đến cuối

### 19.1. Case 1 — Website nội bộ không truy cập được qua VPN

**Mô tả:** Một nhóm nhân sự truy cập \`portal.example.test\` từ văn phòng thành công, nhưng qua VPN thì trình duyệt báo timeout.

**Thu thập:**

- VPN kết nối và có IP tunnel đúng dải quy định.
- Resolver khi ở VPN trả \`portal.example.test\` về 198.51.100.20.
- TCP tới 198.51.100.20:443 timeout từ VPN; cùng dịch vụ hoạt động ở văn phòng.
- Route trên máy VPN chọn tunnel, không đi ra Internet trực tiếp.
- Firewall giữa VPN zone và APP zone ghi deny, policy ID xác định.

**Phân tích:** các bằng chứng cho thấy vùng VPN có đường route nhưng luồng bị enforcement từ chối. Cần xem deny là chủ đích hay policy chưa cập nhật. Không đổi DNS và không kết luận server down.

**Hành động:** application owner xác nhận yêu cầu kết nối; policy owner quyết định mức quyền; network platform áp dụng một thay đổi hẹp được duyệt nếu hợp lệ. SOC theo dõi thay đổi nếu thuộc diện bắt buộc.

**Xác minh:** đúng user/nhóm có quyền truy cập, user đối chứng không có quyền vẫn bị chặn; log cho phép hoặc deny đúng, trang hoạt động qua TLS tin cậy; cập nhật ticket và thời hạn review rule.

### 19.2. Case 2 — API trong Kubernetes trả 503 sau deployment

**Mô tả:** Ingress trả 503 sau bản deploy mới, trong khi DNS tới ingress và TLS handshake vẫn thành công.

**Thu thập:**

- DNS, TCP và TLS ở client → ingress đều đạt.
- Ingress controller báo không có upstream healthy.
- Service \`internal-api\` tồn tại nhưng EndpointSlice không chứa endpoint ready như mong đợi.
- Pod mới tồn tại nhưng readiness probe thất bại sau thay đổi \`targetPort\` hoặc đường dẫn health check.

**Phân tích:** lỗi nằm ở ánh xạ/service readiness hoặc cấu hình backend; việc mở firewall Internet không giải quyết được upstream không sẵn sàng.

**Hành động:** application owner kiểm tra \`targetPort\`, labels, readiness probe và deploy version; platform owner hỗ trợ nếu có dấu hiệu CNI/ingress. Thực hiện rollback khi được phê duyệt và an toàn.

**Xác minh:** EndpointSlice có endpoint ready, ingress gửi request tới backend đúng, tỷ lệ 503 giảm, chức năng API và log ứng dụng bình thường, network policy ngăn kết nối trái phép vẫn hoạt động.

## 20. Checklist phục hồi và đóng ticket

### 20.1. Trước khi khắc phục

- [ ] Có incident/change ID, owner và phạm vi đã xác nhận.
- [ ] Có thời gian UTC, source, destination, port, identity và dấu hiệu lỗi.
- [ ] Đã đối chiếu ít nhất một nguồn log với phép thử cụ thể.
- [ ] Nêu giả thuyết nguyên nhân, mức chắc chắn và bằng chứng phản bác có thể có.
- [ ] Biện pháp không làm mất bảo vệ quan trọng; ngoại lệ có phê duyệt.
- [ ] Có phạm vi thay đổi, cách quan sát tác động và rollback đã kiểm tra.

### 20.2. Sau khi khắc phục

- [ ] Luồng **được phép** hoạt động từ vị trí người dùng thật hoặc mô phỏng đúng đường đi.
- [ ] Luồng **không được phép** vẫn bị từ chối theo chính sách đã phê duyệt.
- [ ] DNS, TLS, identity, route và application response đúng theo thiết kế.
- [ ] Không xuất hiện lỗi mới ở các site, subnet hoặc backend có liên quan.
- [ ] Health metrics, latency, error rate và telemetry trở về ngưỡng chấp nhận.
- [ ] Không bỏ sót log/audit cần thiết; không để lại exception vượt thời hạn.
- [ ] Ticket ghi nguyên nhân, hành động, người duyệt, bằng chứng trước/sau và điểm cần phòng ngừa.
- [ ] Nếu root cause chưa chắc chắn, ghi rõ phần chưa xác nhận và kế hoạch tiếp tục điều tra.

### 20.3. Chỉ số học từ sự cố

Các chỉ số nên đo với định nghĩa nhất quán:

- **MTTD:** từ khi sự cố bắt đầu đến khi được hệ thống/nhân sự phát hiện (phải nói rõ cách xác định mốc).
- **MTTA:** từ khi mở alert/ticket đến lúc người phụ trách xác nhận.
- **MTTR:** thời gian trung bình để khôi phục theo định nghĩa nội bộ; báo kèm tác động và tỷ lệ sự cố mở lại.
- **Change failure rate:** tỷ lệ thay đổi gây lỗi cần rollback hoặc can thiệp.
- **Repeat incident rate:** tỷ lệ lỗi tái phát do cùng nguyên nhân trong khoảng thời gian xác định.
- **Telemetry completeness:** mức đủ dữ liệu flow, DNS, firewall, VPN, proxy hoặc app để truy vết.

Không tối ưu MTTR bằng cách bỏ qua xác minh bảo mật hoặc đóng ticket trước khi người dùng có thể hoạt động đúng. Cần cân bằng khôi phục, bằng chứng và kiểm soát rủi ro.

## 21. Bài tập tình huống và tự kiểm tra

### Bài tập 1 — Lập một runbook từ thông báo lỗi

**Đầu bài:** Máy khách tại VLAN-20 truy cập \`billing.example.test\` qua TCP 443 bị timeout. DNS trả 203.0.113.45, client có IP/gateway đúng, các ứng dụng khác vẫn hoạt động. Kết quả network flow log cho thấy source subnet được route qua firewall vùng DATA, nhưng firewall ghi drop do policy.

**Yêu cầu:** viết ticket ngắn, chọn bước kiểm tra tiếp theo, xác định nhóm cần escalation và hai phép thử sau thay đổi để xác nhận bảo mật.

**Gợi ý đáp án:** thu tuple source/destination và rule ID, đối chiếu data-flow được duyệt; chuyển Network Security/policy owner. Nếu được cấp quyền theo least privilege, kiểm tra kết nối billing thành công và một luồng không được phép vẫn bị chặn.

### Bài tập 2 — Kết nối HTTPS thất bại nhưng ping hoạt động

**Đầu bài:** \`ping api.example.test\` thành công, \`curl\` báo \`certificate verify failed\`. Phép thử TCP tới 443 thành công. Chứng chỉ trên LB vừa được thay đổi.

**Yêu cầu:** xác định lớp lỗi, thứ tự kiểm tra và cách khôi phục.

**Gợi ý đáp án:** tập trung TLS/PKI, kiểm tra SAN, chain, SNI, issuer, validity, trust store và thời gian hệ thống. Khôi phục chứng chỉ/chain đúng qua owner; **không** dùng \`curl -k\` như giải pháp.

### Bài tập 3 — Lỗi chỉ xảy ra với tải lớn

**Đầu bài:** Ứng dụng qua VPN tải JSON nhỏ bình thường nhưng file lớn thường treo. Firewall không có deny, TCP bắt tay thành công.

**Yêu cầu:** nêu ba giả thuyết và bằng chứng cần tìm.

**Gợi ý đáp án:** (1) PMTUD/MTU khi qua encapsulation, (2) loss hoặc congestion gây retransmission, (3) timeout/giới hạn ứng dụng hoặc proxy. Đối chiếu MTU/MSS, TCP retransmission, interface counters, proxy/backend timing và kích thước request; không thay đổi cấu hình toàn mạng chỉ dựa trên hiện tượng.

### Câu hỏi ôn tập

**Câu 1.** Một firewall báo \`allow\` nhưng TCP timeout. Đã loại trừ firewall chưa?

**Trả lời:** Chưa. Cần kiểm tra session/inspection, NAT, route hồi đáp, firewall khác, kết nối tới listener và khả năng phản hồi của backend.

**Câu 2.** Truy vấn DNS \`NXDOMAIN\` có luôn nghĩa là domain đã bị xóa khỏi Internet không?

**Trả lời:** Không. Có thể sai zone, split-horizon, view, cache hoặc resolver policy. Cần đối chiếu authoritative data và resolver đúng ngữ cảnh.

**Câu 3.** VPN đã connected thì sao vẫn không vào được ứng dụng nội bộ?

**Trả lời:** Vì còn các bước route, DNS, ZTNA policy, user authorization, firewall phân đoạn và service health. Tunnel up chỉ xác nhận một phần đường truy cập.

**Câu 4.** Vì sao sau khi mở allow rule cần kiểm thử kết nối bị cấm?

**Trả lời:** Để chứng minh thay đổi không vô tình mở rộng quyền hoặc phá vỡ phân đoạn; kết nối thành công không đủ chứng minh cấu hình an toàn.

**Câu 5.** Trong sự cố có nghi vấn tấn công, có nên reset firewall hoặc xóa log để khôi phục nhanh?

**Trả lời:** Không. Cần điều phối Incident Response, bảo toàn chứng cứ, đánh giá ảnh hưởng và thực hiện biện pháp cô lập/khôi phục được phê duyệt.

---

## 22. Mẫu runbook dùng lại cho một loại lỗi

Sao chép và điền mẫu bên dưới vào hệ thống quản lý vận hành. Các thông số là **placeholder**, phải được nhóm owner chuẩn hóa trước khi áp dụng.

~~~markdown
# RB-NET-XXX: <Tên triệu chứng>

Owner: <Nhóm chịu trách nhiệm>
Approver / escalation: <Nhóm và kênh>
Scope: <Site, zone, service, cloud account, cluster>
Prerequisites: <Quyền, tài khoản, công cụ, nguồn log>
Safety: <Điều được phép / điều cần approval>
Severity rules: <Dấu hiệu cần mở incident khẩn cấp>

## Trigger
- Symptom:
- Expected:
- Observed:
- First seen (UTC):

## Context
- Source identity / IP / VLAN:
- Destination FQDN / IP / port / protocol:
- Expected path / trust boundaries:
- Change and deployment history:

## Diagnostics (read-only)
1. <Kiểm tra>
   - Evidence:
   - Pass/Fail condition:
2. <Kiểm tra>
   - Evidence:
   - Pass/Fail condition:

## Decision
- If <condition> -> <runbook or owner>
- If <security alert> -> <incident response>
- If <evidence insufficient> -> <bounded next test>

## Approved remediation
- Change/incident ID:
- Proposed fix and blast radius:
- Approver:
- Rollback:
- Verification checks:

## Closure
- Positive test and negative test:
- Logs/metrics restored:
- Evidence links:
- Root cause or unresolved hypothesis:
- Follow-up action and owner:
~~~

**Nguyên tắc cuối:** xử lý lỗi kết nối trong một mạng an toàn là xác minh được **đường đi, quyền truy cập, điểm thực thi chính sách, trạng thái dịch vụ và bằng chứng giám sát**. Một runbook tốt giúp khôi phục kết nối hợp lệ đồng thời duy trì phân đoạn, xác thực, kiểm soát truy cập và khả năng truy vết sự cố.
