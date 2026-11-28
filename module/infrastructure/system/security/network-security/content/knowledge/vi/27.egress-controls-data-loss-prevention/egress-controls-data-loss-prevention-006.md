# Kiểm soát port và protocol đi ra: thiết kế egress filtering gắn với phòng chống thất thoát dữ liệu

Một máy chủ ứng dụng chỉ cần gọi dịch vụ thanh toán qua HTTPS, hỏi DNS resolver nội bộ và gửi logs tới collector. Nếu firewall cho phép **mọi outbound TCP/UDP tới mọi địa chỉ**, một tiến trình bị xâm nhập có thể liên lạc với nhiều đích không thuộc mục đích vận hành. Nhưng ngay cả khi tổ chức chỉ mở **TCP/443**, dữ liệu vẫn có thể bị chuyển ra ngoài qua **một kết nối HTTPS được phép tới đích không đáng tin**. Vì vậy, kiểm soát port và protocol đi ra là bước quan trọng để **giảm attack surface và hạn chế kênh liên lạc không cần thiết**, nhưng không thể thay thế việc kiểm soát **đích, danh tính, hành vi và dữ liệu**.

**Egress traffic** là lưu lượng rời một ranh giới được định nghĩa: process → host, Pod → namespace/network, subnet → VPC, VPC → Internet, hoặc mạng công ty → đối tác. **Egress controls** đặt các điều kiện cho luồng ra ngoài: ai khởi tạo, đến đâu, dùng **transport protocol/port**, qua gateway nào và có được thực hiện theo policy không. **Data Loss Prevention (DLP)** nhằm phát hiện/ngăn việc truyền dữ liệu nhạy cảm trái phép; kiểm soát cổng chỉ là **một lớp** trong chiến lược này.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, chủ đề thuộc chương **Kiểm soát egress và chống thất thoát dữ liệu**. Kiến thức kết nối với firewall, phân đoạn, VPN, IDS/IPS, DNS, TLS/mTLS, bảo mật wireless/container/Kubernetes/cloud và Zero Trust. Bài tập tập trung vào **định nghĩa luồng được phép, thiết kế policy outbound least privilege, kiểm tra các đường ngoại lệ và đánh giá tác động trước khi chặn**. Ví dụ IP, domain, policy và log là giả định phục vụ học tập; không thay đổi production firewall và không gửi lưu lượng đến đích không thuộc quyền quản trị.

> **Nguyên tắc:** “Mở TCP/443” không tương đương “chỉ cho phép truy cập dịch vụ đáng tin”, “chặn UDP/53” không đồng nghĩa “không còn đường phân giải DNS”, và “traffic bị firewall từ chối” chưa chứng minh dữ liệu chưa bị rò rỉ qua một kênh khác. Quyết định egress an toàn phải gắn **nguồn → đích → protocol/port → mục đích → identity → giám sát**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **ingress/egress theo ranh giới quan sát**, hướng kết nối và đường đi gói phản hồi.
2. Hiểu **TCP, UDP, ICMP/ICMPv6, IP protocol numbers, source/destination ports** và các giao thức ứng dụng chạy phía trên chúng.
3. Phân tích sự khác biệt giữa **stateful firewall/SG** và **stateless NACL**, bao gồm **ephemeral return ports**.
4. Thiết kế allowlist **nguồn, đích, transport protocol, destination port**, có xét NAT, proxy và IPv4/IPv6.
5. Nhận diện **DNS UDP/TCP 53, DoT, DoH, QUIC/HTTP/3, SSH, SMTP, NTP, cơ chế dynamic ports** và nguy cơ policy chỉ xét cổng.
6. Giải thích **tại sao allow TCP/443 tới 0.0.0.0/0 không phải kiểm soát DLP đủ mạnh**.
7. Kết hợp **egress gateway/proxy, authenticated access, FQDN/HTTP-aware controls, firewall, DNS governance và DLP** theo trust boundary.
8. Áp dụng thiết kế trong **host firewall, cloud security groups/NACL, Kubernetes NetworkPolicy/CNI, container, hybrid/VPN và service mesh**.
9. Thiết kế **telemetry, policy-as-code, exception lifecycle, rollout/rollback** và tránh gây gián đoạn DNS, PKI, monitoring hoặc các kết nối nghiệp vụ.
10. Thực hiện **đánh giá lab có quyền, case studies và ma trận ALLOW/DENY**, phân biệt chính sách bị chặn đúng với lỗi ứng dụng hoặc routing.

## 2. Xác định ranh giới trước khi nói “đi ra”

Một packet có thể là **egress** tại một ranh giới nhưng trở thành **ingress** ở ranh giới kế tiếp:

~~~text
Application / Pod A
       |
       | EGRESS from Pod A
       v
Node / Host
       |
       | EGRESS from host
       v
Subnet / VPC egress gateway
       |
       | EGRESS from VPC
       v
Internet / Partner network
       |
       | INGRESS to destination
       v
External service
~~~

Vì vậy một câu như **“mở outbound 443”** chưa rõ nếu thiếu **nguồn nào, firewall nào, destination CIDR nào và chiều trả lời**. Cũng phải phân biệt:

- **Network egress**: packet đi ra network namespace/subnet/zone theo policy.
- **Application egress**: ứng dụng chủ động kết nối API, DNS, message broker hoặc database.
- **Data egress**: dữ liệu rời một miền kiểm soát/đơn vị bảo mật; có thể nằm trong flow network hợp lệ.
- **Cross-zone/tenant egress**: data hoặc traffic vượt trust boundary dù vẫn ở cùng cloud/cluster.

### Ba ví dụ

| Luồng | Ranh giới có ý nghĩa | Mục tiêu kiểm soát |
|---|---|---|
| API → DB cùng VPC | App subnet → DB subnet | Chỉ API được gọi DB trên cổng được duyệt |
| Pod → Internet qua NAT | Pod/CNI → node/VPC → public egress | Chỉ workload đúng được ra đích đã duyệt |
| Nhân viên upload file lên SaaS | Endpoint → gateway → SaaS tenant | Không rò dữ liệu bí mật dù HTTPS hợp lệ |

**Không mặc định lưu lượng cùng subnet hoặc cùng cloud là không cần chính sách**. Một workload bị xâm nhập có thể lạm dụng east–west traffic để di chuyển ngang hoặc đưa dữ liệu tới service không thuộc quyền.

## 3. Flow inventory là đầu vào của mọi egress policy

Trước khi viết rule, phải biết ứng dụng **thật sự cần gọi những gì**.

| Trường inventory | Câu hỏi |
|---|---|
| **Source identity** | Workload/process/Pod/ServiceAccount/user nào khởi tạo? |
| **Source network** | Host, subnet, namespace, VPC, VPN zone, IPv4/IPv6 nào? |
| **Destination identity** | Service owner, partner, SaaS tenant, gateway hoặc resolver nào? |
| **Destination address** | IP/CIDR/FQDN/Service cụ thể; thay đổi do DNS/CDN/NAT không? |
| **Transport protocol** | TCP, UDP, ICMP/ICMPv6, GRE hoặc protocol khác? |
| **Destination port** | TCP/443, UDP/53, TCP/5432, nhiều port động? |
| **Application protocol** | HTTPS, gRPC, DNS, SSH, SMTP, DB, NTP, QUIC? |
| **Direction/return path** | Ai khởi tạo và gói trả lời đi theo boundary nào? |
| **Data classification** | Dữ liệu public, internal, confidential hay regulated? |
| **Required authentication** | mTLS, API token, OAuth audience, service identity, DB auth? |
| **Business purpose** | Vì sao phải cho luồng chạy; ai sở hữu? |
| **Telemetry/acceptance** | Log, test ALLOW/DENY, SLO, expiry và rollback? |

### Ví dụ bảng flow đã phê duyệt

| ID | Nguồn | Đích | Giao thức/cổng | Quyết định |
|---|---|---|---|---|
| **F01** | app/catalog | payment API qua egress gateway | HTTPS TCP/443 | ALLOW theo đích và identity |
| **F02** | app/catalog | resolver doanh nghiệp | DNS UDP/TCP 53 | ALLOW qua resolver được duyệt |
| **F03** | app/catalog | log collector | TCP/4317 hoặc port do collector cấu hình | ALLOW có mTLS/auth |
| **F04** | app/catalog | mọi public IP TCP/443 | Không thuộc danh mục | DENY theo thiết kế |
| **F05** | app/catalog | public SMTP TCP/25 | Không có nhu cầu | DENY |
| **F06** | monitoring-agent | approved NTP server UDP/123 | Theo kiến trúc | ALLOW nếu thực cần |
| **F07** | test/sandbox | production DB TCP/5432 | Không có nhu cầu | DENY |

Tên và số port ở đây là **minh họa**; một OTLP collector có thể dùng protocol/port khác tùy cấu hình. Nếu hệ thống dùng NTP của host thay vì Pod trực tiếp, đừng tự thêm rule Pod→Internet UDP/123.

## 4. TCP, UDP, ICMP không phải một nhóm cổng chung

**TCP** và **UDP** có namespace port riêng. **ICMP/ICMPv6 không sử dụng TCP/UDP source/destination ports**; chúng có type/code. Các protocol khác (như ESP/AH hoặc GRE trong một số hạ tầng) có cách biểu diễn riêng.

| L4/protocol | Có source/destination port? | Ví dụ |
|---|---|---|
| **TCP** | Có: 16-bit port mỗi phía | HTTPS, SSH, SMTP, TCP DNS, database |
| **UDP** | Có: 16-bit port mỗi phía | UDP DNS, NTP, QUIC, nhiều giao thức real-time |
| **ICMPv4** | Không | Echo, destination unreachable, fragmentation needed |
| **ICMPv6** | Không | Packet Too Big, Neighbor Discovery, Router Advertisement theo mạng |
| **ESP/AH, GRE** | Không theo TCP/UDP port model | Tunnel/protocol theo kiến trúc |

**TCP/443 và UDP/443 không phải cùng một firewall rule về protocol.** Nhiều ứng dụng hiện đại có thể dùng HTTPS trên **TCP/443** hoặc HTTP/3 qua **QUIC trên UDP/443**, tùy client/server/đường mạng.

### Port là chỉ báo, không phải bằng chứng protocol

Một server có thể phục vụ **HTTP trên TCP/8080**, **SSH trên TCP/2222**, hoặc ứng dụng tùy biến trên TCP/443. Vì vậy:

1. Allow TCP/443 **không chứng minh payload chắc chắn là HTTPS**.
2. Nhận diện một **TLS ClientHello/SNI** cũng không tự chứng minh API đích đúng tổ chức/tenant.
3. Chặn TCP/25 không chắc chắn chặn mọi cách gửi email nếu app dùng **HTTPS API** tới dịch vụ email.
4. Chặn DNS UDP/53 không chặn hoàn toàn **DoH qua HTTPS** hoặc các proxy được phép nếu không có lớp kiểm soát khác.

## 5. Source port và destination port của một kết nối

Giả sử ứng dụng nội bộ **10.20.20.10:53124** kết nối API **198.51.100.20:443**:

~~~text
Outbound TCP request:
  SRC 10.20.20.10:53124
  DST 198.51.100.20:443

Inbound TCP response:
  SRC 198.51.100.20:443
  DST 10.20.20.10:53124
~~~

**198.51.100.0/24 là dải IP dùng cho tài liệu**, không phải endpoint thanh toán thật. Port **53124** minh họa ephemeral source port được hệ điều hành/runtime chọn.

### Vì sao dễ mở sai rule?

- Rule outbound cần xét **destination service port 443** trên request.
- Response hướng vào nguồn thường có **destination ephemeral port 53124**, không phải destination 443.
- **Stateful firewall** có connection tracking thường cho response phù hợp với phiên được phép.
- **Stateless ACL** cần xem chiều trả lời tường minh theo ranh giới cụ thể.
- NAT/proxy có thể đổi **source IP/source port** ở điểm đi ra; muốn điều tra phải biết 5-tuple trước và sau translation.

### Ephemeral range thay đổi

Không có một dải ephemeral port toàn cầu phù hợp cho mọi OS/container/NAT. Dải có thể chịu ảnh hưởng kernel settings, ứng dụng bind source port, NAT gateway, load balancer hoặc firewall. **Không hardcode “49152–65535” như quy luật cho tất cả môi trường**, cũng không mở mọi port inbound nếu có một cơ chế stateful phù hợp.

## 6. Stateful egress firewall và stateless ACL

### Stateful

Khi một firewall **có trạng thái** cho outbound TCP/443 tới đích được duyệt, nó có thể tự chấp nhận **response thuộc kết nối được theo dõi**. Điều này không nghĩa cho phép server ngoài khởi tạo một kết nối tùy ý ngược vào workload.

~~~text
Stateful:
  OUT: app:53124 -> payment:443 = ALLOW
  RETURN: payment:443 -> app:53124
          = allowed as established related flow

  NEW unsolicited inbound: payment:443 -> app:22
          = evaluated separately / DENY if not allowed
~~~

### Stateless

Một ACL **stateless** đánh giá gói theo từng chiều:

~~~text
OUTBOUND app subnet:
  ALLOW app CIDR -> payment CIDR TCP dst 443

INBOUND app subnet:
  ALLOW payment CIDR -> app CIDR TCP dst ephemeral range

The actual return route must match the policies
on every applicable boundary.
~~~

Đây là mô hình hai chiều **chỉ để giải thích**. Chi tiết rule gồm priority, CIDR, source/destination matching, network interfaces và hạn chế đặc biệt theo nhà cung cấp.

### Phân biệt một số nền tảng

| Loại policy | Hành vi quan trọng |
|---|---|
| **AWS Security Group** | Stateful, cho phép return traffic của kết nối hợp lệ theo connection tracking semantics |
| **AWS VPC Network ACL** | Stateless, ordered rules; cần xem inbound/outbound và ephemeral returns |
| **Azure NSG** | Có stateful flow tracking, không diễn giải như AWS NACL |
| **Google Cloud VPC firewall rules** | Stateful trong mô hình firewall connection tracking; thứ tự/targets khác AWS |
| **Kubernetes NetworkPolicy** | CNI thực thi policy L3/L4, thường cho response của kết nối được phép theo semantics |
| **Host firewall** | Tùy nftables/iptables/Windows Firewall/ruleset và connection tracking thực tế |

**Không copy một danh sách return ephemeral NACL sang mọi loại firewall**. Điều quan trọng là đánh giá **effective policy, hướng, protocol và connection state** đúng cho sản phẩm đang dùng.

## 7. Allowlist theo đích: cổng đúng nhưng đích sai vẫn phải từ chối

Quy tắc rộng kiểu:

~~~text
ALLOW source app subnet
TO any IPv4 destination (0.0.0.0/0)
TCP destination port 443
~~~

cho phép một ứng dụng khởi tạo HTTPS hoặc TCP tùy ý trên cổng 443 tới rất nhiều đích, bao gồm những dịch vụ không nằm trong danh mục. Nó **có thể cần trong một giai đoạn chuyển đổi được kiểm soát**, nhưng không phải chính sách DLP đích cuối cùng cho workload nhạy cảm.

### Mô hình chặt hơn

~~~text
ALLOW catalog -> approved payment gateway/service
  protocol TCP
  port 443
  service identity / origin validation required

ALLOW catalog -> approved DNS resolver
  UDP/53 and TCP/53 where required

ALLOW catalog -> approved telemetry collector
  exact protocol/port according to deployment

DENY other destinations by default
  with logging and exception workflow
~~~

### “Approved destination” có thể được định nghĩa bằng gì?

| Cách định danh | Điểm mạnh | Giới hạn |
|---|---|---|
| **Static IP/CIDR** | Đơn giản tại L3/L4 | IP/CDN/NAT đổi, IP shared hosting có nhiều tenant |
| **FQDN-aware egress policy** | Gắn với tên dịch vụ theo cơ chế hỗ trợ | DNS caching, CDN, IP sharing, SNI/hostname trust |
| **HTTP-aware proxy** | Có thể kiểm tra method, Host, URL/headers theo policy | TLS termination, privacy, protocol coverage |
| **Service identity/mTLS** | Kiểm tra peer/service danh tính mật mã | Cần PKI, issuance và policy; không tự biết object data |
| **Private endpoint/service connect** | Có thể tránh Internet public và giới hạn route | Không tự xác thực đúng quyền người dùng/workload |
| **SaaS tenant-aware controls** | Phân biệt tenant doanh nghiệp với tenant cá nhân khi có hỗ trợ | Cần tích hợp sản phẩm, identity/session và phạm vi dữ liệu |

**Không nên coi “destination có certificate hợp lệ” là đích được cho phép**. Certificate cho biết danh tính theo trust policy; authorization cần xác định **đúng service/tenant/path** được tổ chức phê duyệt.

## 8. Mặc định từ chối và exception tối thiểu

Một chiến lược phổ biến là **default deny outbound** cho những workload/network zone được kiểm kê kỹ, sau đó chỉ cho phép các flows cần thiết.

### Các bước trước khi bật

1. Inventory **source workloads và owner**.
2. Xác định **DNS, PKI/CRL/OCSP (nếu dùng), NTP, metadata/identity, logging, monitoring, update services** đang đi đâu.
3. Xem **tác động tới ứng dụng và đường HA/DR** khi một đích bị chặn.
4. Tính **stateful/stateless return path** và vùng áp policy.
5. Kiểm thử ở staging với **positive + negative test cases**.
6. Có thời hạn cho **temporary exceptions**, owner, ticket, expiry và rollback.
7. Đo **DENY và SLO** sau rollout; chỉ mở bổ sung khi chứng minh có nhu cầu.

### Tránh hai cực đoan

- **Allow-any toàn mạng** giảm sự cố ban đầu nhưng tăng khả năng lateral movement/exfiltration.
- **Deny-all không inventory** có thể làm hỏng DNS, certificate validation, cập nhật hệ thống, giám sát, auth/PKI hoặc giao dịch kinh doanh.

**Least privilege là allow có chủ đích và có bằng chứng**, không phải “chặn mọi thứ càng nhanh càng tốt”.

## 9. Danh mục các giao thức outbound phổ biến

| Protocol/port thường gặp | Mục đích | Quy tắc thiết kế |
|---|---|---|
| **TCP/443** | HTTPS, nhiều API, SaaS, gRPC qua TLS | Giới hạn đích/identity; không coi mọi 443 đều đáng tin |
| **UDP/443** | HTTP/3/QUIC và ứng dụng khác | Xác định nhu cầu thực; proxy/inspection support |
| **TCP/80** | HTTP, redirect, một số repository/health | Tránh truyền dữ liệu nhạy cảm plaintext nếu không được duyệt |
| **UDP/53, TCP/53** | DNS truyền thống | Chỉ resolver được phép, xem NodeLocal/managed DNS |
| **TCP/853** | DNS over TLS theo cách dùng phổ biến | Resolver policy, không coi mọi 853 là trusted |
| **UDP/853** | DNS over QUIC theo triển khai hỗ trợ | Xem nhu cầu và phân loại protocol thực |
| **UDP/123** | NTP | Dùng time source được duyệt; có thể host-managed |
| **TCP/22** | SSH/SFTP | JIT/approved hosts, keys và session audit |
| **TCP/25/465/587** | SMTP/SMTPS/submission theo cấu hình | Chỉ mail relay được duyệt, auth/mTLS khi cần |
| **TCP/5432** | PostgreSQL mặc định thường gặp | Chỉ DB được phê duyệt, database authentication |
| **TCP/6379** | Redis thường gặp | Chỉ private broker/cache, TLS/auth phù hợp |
| **TCP/3389** | RDP mặc định thường gặp | Chỉ quản trị có kiểm soát, không mở Internet tùy ý |
| **TCP/4317, 4318** | OTLP gRPC/HTTP convention | Chỉ collector được duyệt, TLS/mTLS |
| **ICMP/ICMPv6** | Network control/diagnostics/PMTUD | Lọc theo type/code, không chặn cơ học tất cả |

Các port là **đặc trưng thông dụng, không bảo đảm mọi ứng dụng sử dụng đúng port**. Không được cho phép một dịch vụ **chỉ vì số cổng trông hợp lý** hoặc chặn một protocol thiết yếu chỉ vì không thuộc TCP/UDP.

## 10. TCP/443 không đồng nghĩa “an toàn vì có TLS”

TLS bảo vệ **một kết nối giữa những điểm kết thúc được xác định**, nhưng không tự nói dữ liệu có được phép rời tổ chức hay không.

~~~text
App with confidential data
     |
     | TLS to external.example.test:443
     v
Public HTTPS endpoint

Network firewall:
  TCP/443 permitted to 0.0.0.0/0

Result:
  Connection may be allowed even if external
  destination is NOT approved for that data.
~~~

### Ba lớp không hoán đổi

1. **Transport permission:** được phép TCP/443 tới địa chỉ nào?
2. **Peer authentication:** đích có đúng certificate/SAN/service identity không?
3. **Data authorization:** workload có được gửi **loại dữ liệu cụ thể** cho dịch vụ/tenant/recipient đó không?

Nếu chỉ có lớp 1 và lớp 2, một đích bên ngoài **có TLS hoàn toàn hợp lệ** vẫn có thể nhận dữ liệu không được phép. DLP cần thêm **classification, destination/tenant policies, content/metadata inspection có phép, endpoint/app controls và audit**.

### Không dựa duy nhất vào SNI

SNI không luôn đại diện cho **HTTP Host, URL path, tenant hoặc user identity**; một số giao thức/triển khai có thêm mã hóa thông tin bắt tay. Khi dùng proxy/FQDN filters, cần tính **DNS resolution, SNI/Host consistency, CDN/shared IP, TLS handshake và protocol detection**, không coi một chuỗi domain trong packet là chứng thực đủ.

## 11. Quyết định theo cổng và theo giao thức ứng dụng

~~~text
           Packet leaves workload
                    |
                    v
       L3/L4: Source/dest IP, TCP/UDP/port
                    |
              ALLOW by port?
               /          \
             No           Yes
             |             |
           DENY     Is destination approved?
                          /        \
                         No        Yes
                         |          |
                        DENY    Protocol identity /
                                app policy / DLP
                                      |
                              ALLOW / DENY / REVIEW
~~~

Mô hình chỉ mô tả **các quyết định riêng**, không yêu cầu mọi firewall thực hiện đủ các bước. Một L3/L4 ACL thường không biết **HTTP path, user, tenant, payload classification**. Một proxy ứng dụng có thể kiểm soát HTTP nhưng không nhất thiết hiểu **opaque TCP hoặc end-to-end TLS không được terminate**. Cần đặt **đúng enforcement point**.

## 12. Phát hiện và quản trị protocol drift

**Protocol drift** xuất hiện khi ứng dụng chuyển sang giao thức/port mới, ví dụ:

- Browser/SDK chuyển từ HTTP/2 trên **TCP/443** sang HTTP/3 trên **UDP/443**.
- DNS client bật DoH/DoT, không còn dùng resolver UDP/53.
- API đối tác đổi port, endpoint/CDN, proxy hoặc transport.
- Dịch vụ gRPC đổi từ HTTP/2 trực tiếp sang TLS qua ingress.
- Agent monitoring thay OTLP/gRPC bằng OTLP/HTTP.

### Vì sao drift là vấn đề bảo mật?

Nếu policy chỉ cho TCP/443 mà client tự chuyển sang UDP/443, dịch vụ có thể lỗi hoặc fallback theo đặc điểm của client. Nếu operator mở ngay UDP/443 tới **mọi Internet IP** để sửa, họ có thể vô tình tăng phạm vi egress. Ngược lại, nếu DLP/proxy chỉ nhìn TCP/443, QUIC có thể tạo **lỗ hổng quan sát** nếu sản phẩm không hỗ trợ.

### Quy trình xử lý

1. Xác nhận **protocol/port mới** có thật và thuộc mục đích nghiệp vụ.
2. Kiểm tra **proxy, firewall và monitoring** có hỗ trợ protocol đó không.
3. Cập nhật **đích và scope** thay vì mở cổng toàn cầu.
4. Test tình huống **client dùng protocol mới, fallback và lỗi do bị chặn**.
5. Ghi thay đổi trong flow inventory, IaC policy và alert thresholds.

## 13. DNS egress: một luồng nhỏ nhưng ảnh hưởng toàn ứng dụng

DNS thường là **phụ thuộc đầu tiên** trước khi ứng dụng mở TCP/UDP tới API hoặc database bằng hostname. Nếu chặn DNS không đúng, triệu chứng ở ứng dụng có thể là **không resolve được tên**, gây ra lỗi timeout rộng dù đường TCP/443 phía sau vẫn đúng.

### Luồng truy vấn DNS truyền thống

~~~text
App/Pod:10.20.20.10:53000
      |
      | UDP/53 query
      v
Approved resolver:10.20.0.53:53
      |
      | UDP response to source ephemeral port
      v
App/Pod:10.20.20.10:53000
~~~

Khi bản tin DNS yêu cầu TCP/53 hoặc được cấu hình dùng TCP, policy phải xem **đúng TCP flow**. Nếu dùng **NodeLocal DNSCache, stub resolver, systemd-resolved, CoreDNS hay cloud-managed DNS**, source/destination thực có thể không giống sơ đồ.

### Chính sách DNS khuyến nghị

- Xác định **resolver được tổ chức phê duyệt** và khả năng phục vụ nội bộ/external.
- Chỉ cho workload gửi DNS tới resolver cần thiết; chặn **unapproved resolver** theo ranh giới có thể kiểm soát.
- Cho phép cả **UDP/TCP** khi DNS implementation/case yêu cầu.
- Ghi telemetry và phát hiện **destination mới, query rate bất thường, hostname dài hoặc patterns lạ** một cách cân đối.
- Không lưu toàn bộ query string của người dùng vô thời hạn; có thể chứa **PII hoặc internal hostnames**.
- Đảm bảo DNS của control plane/host không bị policy dành cho Pod chặn nhầm.

**Chặn UDP/53 tới Internet không chặn mọi đường DNS.** Workload có thể dùng resolver qua **HTTPS (DoH), TLS (DoT) hoặc các kênh khác**. Muốn kiểm soát DNS nghiêm ngặt, cần kiến trúc resolver/proxy, egress destinations và endpoint policies được thực thi.

## 14. DoH, DoT, DoQ và ranh giới lọc theo port

| Cơ chế | Transport/port phổ biến | Điểm cần lưu ý |
|---|---|---|
| **DNS truyền thống** | UDP/53, TCP/53 | Có thể quan sát truy vấn ở resolver theo chính sách |
| **DNS over HTTPS (DoH)** | HTTPS thường trên TCP/443; có thể dùng HTTP/3 qua UDP/443 | Dễ lẫn với HTTPS khác ở mức port |
| **DNS over TLS (DoT)** | TCP/853 | TLS mã hóa payload DNS trên hop |
| **DNS over QUIC (DoQ)** | UDP/853 theo chuẩn phổ biến | Cần protocol-aware enforcement |
| **Resolver qua private API** | Theo thiết kế provider | Có thể dùng endpoint đặc biệt hoặc đường không qua Internet |

Một chính sách **“chặn UDP/53, cho TCP/443 tới mọi IP”** không thể tuyên bố “DNS bắt buộc qua resolver công ty”. Cần xác định **những dịch vụ/ứng dụng nào được phép sử dụng DoH/DoT** và triển khai **FQDN/service-aware egress, endpoint/browser policy, DNS governance** khi phù hợp.

### Khó khăn của nhận diện dựa vào SNI/domain

Một địa chỉ IP/CDN có thể phục vụ nhiều hostname; TLS metadata có thể bị che một phần, và DNS caching không luôn trùng với traffic HTTP. Một firewall chỉ có thông tin **port 443** không thể phân biệt chắc chắn **API thanh toán** với **DoH tới resolver ngoài quyền**. Không giải quyết sự thiếu visibility bằng cách kiểm soát DNS theo port mà bỏ qua các đường ứng dụng/proxy khác.

## 15. QUIC và HTTP/3: vì sao UDP/443 cần chính sách riêng

**HTTP/3** chạy trên **QUIC**, thường dùng **UDP/443**, khác với HTTP/1.1 hoặc HTTP/2 chạy qua TCP/TLS thông thường. Một client có thể thử QUIC rồi fallback về TCP tùy triển khai, trạng thái mạng và policy.

~~~text
Client
  |--- UDP/443 (QUIC/HTTP3) ---> Approved API/CDN
  |
  +--- TCP/443 (HTTPS) -------> Approved API/CDN

These are separate protocol/port flows.
Allowing one does not automatically allow the other.
~~~

### Hai sai lầm đối lập

1. **Chặn UDP/443 rồi kết luận “đã ngăn HTTPS”**: HTTPS trên TCP/443 vẫn có thể hoạt động.
2. **Mở UDP/443 đến mọi IP để sửa chậm ứng dụng**: có thể tạo đường egress không được DLP/proxy quan sát đúng.

### Cách lựa chọn

- Nếu tổ chức **không cho phép QUIC** qua boundary này, chặn UDP/443 theo policy có phê duyệt và kiểm tra client fallback/hiệu năng.
- Nếu cần QUIC, cho phép **đúng service/destination, protocol support và telemetry**, không mặc định all Internet.
- Kiểm tra **giao thức thực tế và TLS identity**, bởi UDP/443 không phải nhãn bảo đảm payload là HTTP/3 hợp lệ.
- Lưu ý service mesh/egress proxy/WAF có thể có **mức hỗ trợ HTTP/3 khác HTTP/2**.
- Thử cả **trình duyệt, API SDK, mobile client, health checks và đường dự phòng**.

**Giới hạn QUIC là quyết định kiến trúc mạng và trải nghiệm**, không phải phương pháp mặc định để phát hiện nội dung nhạy cảm.

## 16. ICMP, ICMPv6 và Path MTU Discovery

Một chính sách “chỉ cho TCP/UDP các port cần thiết, deny tất cả ICMP” có thể gây lỗi kết nối khó chẩn đoán, đặc biệt trên **VPN, overlay, IPv6 và các đường có MTU khác nhau**.

### Path MTU Discovery (PMTUD)

~~~text
Application sends TCP data over tunnel
               |
      Packet too large for path
               |
        Network reports problem
       ICMP Fragmentation Needed (v4)
       ICMPv6 Packet Too Big (v6)
               |
        Sender adjusts packet size
~~~

Nếu phản hồi điều khiển cần thiết bị chặn không đúng, ứng dụng có thể **connect được với gói nhỏ** nhưng **truyền dữ liệu lớn bị timeout**. Điều này thường bị hiểu nhầm là lỗi TLS, WAF hoặc DLP.

### Đặc biệt với IPv6

IPv6 dùng **ICMPv6** cho nhiều hoạt động nền tảng: PMTUD và **Neighbor Discovery** trong mạng liên quan. Không thể coi ICMPv6 là dịch vụ tùy chọn giống một cổng TCP có thể khóa tùy ý. Khi thiết kế firewall phải phân biệt **ICMPv6 type/code theo hướng và phạm vi link**, không mở tất cả global cũng không chặn tất cả.

### Chính sách phù hợp

1. Inventory các **loại ICMP/ICMPv6 cần thiết** cho định tuyến, MTU và health checks.
2. Giới hạn theo **type/code/source/destination/hướng** nếu sản phẩm hỗ trợ.
3. Kiểm thử **small vs large payload**, IPv4/IPv6 và tunnel/overlay được duyệt.
4. Không dùng ping failure làm bằng chứng duy nhất rằng một ứng dụng TCP không reachable.

## 17. Giao thức có port động, điều khiển và kênh dữ liệu

Một số ứng dụng không chỉ dùng một port cố định, hoặc có **kênh control và data khác nhau**. Ví dụ kinh điển là FTP; ngoài ra RPC frameworks, một số media/VoIP, database failover hoặc service discovery có thể liên quan dải port động theo triển khai.

### Vì sao “chỉ mở cổng control” đôi khi chưa đủ?

~~~text
Client ---> Control connection to service
               |
               | Negotiates data endpoint
               v
Client <-----> Separate data flow / dynamic port
~~~

Trong **FTP active/passive**, network path và port cần thiết khác nhau. Một firewall có helper/ALG hoặc proxy protocol-aware có thể hỗ trợ một số mô hình, nhưng **không nên bật rộng toàn bộ high ports** chỉ vì không rõ ứng dụng dùng gì.

### Quy trình đúng

- Tìm **giao thức và client/server mode** theo tài liệu triển khai được cấp quyền.
- Đánh giá có thể **thay giao thức legacy** bằng HTTPS API hoặc SFTP/SSH phù hợp không.
- Xác định **dải data ports cố định và nhỏ nhất** nếu ứng dụng cho cấu hình.
- Kiểm tra **stateful inspection, NAT traversal, protocol proxy** ở boundary.
- Test đúng các thao tác thực tế, không chỉ TCP connect tới control port.
- Giữ authentication/encryption/DLP phù hợp với dữ liệu truyền.

**Không đồng nhất “dynamic port” với “toàn bộ ephemeral 1024–65535 bắt buộc mở outbound tới Internet”.** Cần đánh giá từng giao thức và ranh giới thật.

## 18. SMTP, SSH, remote admin và giao thức có nguy cơ dữ liệu rời mạng

### SMTP/email

Một workload backend không nên tự do gửi email tới mọi mail server trên Internet nếu mục đích nghiệp vụ chỉ yêu cầu gửi qua **mail relay được quản lý**. Xem:

- **SMTP submission/relay** và cổng thực đang dùng (25, 465, 587 hoặc custom).
- Authentication, TLS và quy định của nhà cung cấp mail.
- Data classification, recipient/domain restrictions, attachment scanning.
- Application email API qua **HTTPS TCP/443**; chặn TCP/25 không đủ để ngăn mọi email exfiltration.

### SSH/SFTP

SSH/SFTP có thể là kênh quản trị hoặc truyền file hợp lệ. Không cho phép outbound SSH tới bất kỳ địa chỉ nào chỉ vì đội vận hành cần SFTP tới một đối tác:

- Dùng **approved host + host key verification**, JIT/change ticket khi nhạy cảm.
- Giới hạn **source identity, destination port và data scope**.
- Theo dõi file transfer và quyền truy cập theo owner.
- Chặn **port forwarding/tunnel** nếu xung đột policy, theo khả năng sản phẩm và quyền hợp pháp.

### Remote management

RDP, SSH, WinRM hoặc agent management có thể dùng port khác nhau. Nên ưu tiên **approved management broker/jump host** và policy theo role, thay vì host-to-any outbound. Đừng cấp quyền mạng rộng chỉ vì cần truy cập một máy phục vụ hỗ trợ.

## 19. NAT, SNAT, proxy và đường thực tế của gói đi ra

Một workload có thể có địa chỉ private nhưng sau NAT gateway, external destination chỉ thấy một địa chỉ egress IP chung. Firewall ở các điểm khác nhau có **thông tin nguồn/đích khác nhau**.

~~~text
App Pod: 10.20.20.10:53124
       |
       | CNI/host policies
       v
Node or subnet routing
       |
       | SNAT / NAT Gateway
       v
Public source: 203.0.113.10:62010
       |
       v
External API: 198.51.100.20:443
~~~

**203.0.113.0/24 và 198.51.100.0/24 là dải tài liệu**. Port và IP minh họa không đại diện bản ghi thật.

### Những trường hợp cần lưu ý

| Hiện tượng | Hệ quả |
|---|---|
| **Source NAT** | Destination không thấy Pod IP hoặc identity của user |
| **Destination NAT** | Policy có thể đánh giá trước/sau translation tùy dataplane |
| **Shared egress IP** | Allowlist phía đối tác cho IP chung không phân biệt workload bên trong |
| **HTTP proxy** | App có thể chỉ kết nối proxy, proxy mới kết nối đích |
| **Service mesh egress gateway** | Client identity nhìn thấy ở backend có thể là gateway identity |
| **Split-tunnel VPN** | Một số traffic không đi qua egress boundary dự kiến |
| **Private endpoint/peering** | Dữ liệu vẫn rời trust zone dù không ra Internet public |

**Không dùng một public NAT IP làm chứng cứ rằng tất cả service phía sau có quyền giống nhau**. Cần phân quyền tại **source workload và egress gateway**, đồng thời giữ audit gắn với danh tính nguồn.

## 20. Host, container và namespace network egress

Một process nằm trong container/Pod không đồng nghĩa nó không có đường ra Internet. Tùy container network, node, CNI hoặc Docker bridge, Pod có thể mở outbound tới host, subnet lân cận hoặc public IP mà **không cần publish host port**.

### Docker

- **Dockerfile EXPOSE** là metadata cho inbound service, **không phải egress firewall**.
- Không có **docker run -p** cũng không có nghĩa container không thể outbound.
- Docker bridge, user-defined network, **host network** và rootless mode có network isolation khác nhau.
- Container bị gắn nhiều Docker networks có thể nối tới **nhiều trust zones**.
- Kiểm soát outbound có thể nằm ở host firewall, bridge filtering, proxy hoặc cloud boundary; phải xác định **effective path**.

### Kubernetes

- **Namespace không tự chặn egress** giữa các Pod/namespace.
- **Kubernetes NetworkPolicy Egress** có thể giới hạn nguồn Pod theo CNI support.
- **NetworkPolicy thông thường không tự lọc FQDN/HTTP path** nếu không có extension.
- **HostNetwork/node traffic** và traffic đặc biệt có thể có coverage khác nhau tùy CNI.
- **Pod IP** có thể đổi theo rollout; nên dùng Pod/namespace selectors phù hợp thay vì hardcode tất cả Pod IP.
- Với **dual-stack**, cần kiểm tra v4/v6 policies và IP blocks riêng.

### Ai có thể thay policy?

Kubernetes RBAC/admission, Linux capabilities, container privilege và quyền chỉnh cloud firewall ảnh hưởng trực tiếp tới khả năng bypass. Một Pod có quyền **NET_ADMIN/hostNetwork** hoặc owner được sửa NetworkPolicy có thể khiến mô hình trust thay đổi; **egress filtering chỉ đáng tin khi quyền chỉnh cấu hình được bảo vệ**.

## 21. Kubernetes NetworkPolicy: chỉ cho Pod đi đúng service

Giả sử app **app=catalog** trong namespace **catalog-prod** chỉ cần gọi payment service **app=payment** ở namespace **payments-prod** trên TCP/8443, cộng resolver DNS theo đường được quản trị.

### Policy egress theo destination Pod/namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: catalog-allow-payment
  namespace: catalog-prod
spec:
  podSelector:
    matchLabels:
      app: catalog
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: payments-prod
          podSelector:
            matchLabels:
              app: payment
      ports:
        - protocol: TCP
          port: 8443
~~~

**Đây là manifest minh họa**, giả định cluster CNI thực thi Kubernetes NetworkPolicy và destination Pod có label như mô tả. Một phần tử **to** chứa namespaceSelector và podSelector cùng nhau là **AND**; nếu tách thành hai phần tử khác nhau thì thành **OR**, có thể mở ra toàn namespace hoặc một tập Pod không mong muốn.

### Cần gì để flow hoạt động?

1. **Source Pod** được policy trên cho egress TCP/8443.
2. **Destination Pod** không bị ingress isolation chặn hoặc có ingress allow tương ứng.
3. **Service/endpoints/route/CNI** hoạt động đúng.
4. **DNS** được phép nếu client gọi Service theo tên.
5. **TLS/mTLS/service authentication** và payment API authorization hợp lệ.
6. Không có **cloud SG/network firewall hoặc mesh policy** chặn đường đã duyệt.

### Các policy cùng chọn một Pod được cộng quyền

NetworkPolicy chuẩn có **additive allow semantics**; nếu đã có một policy khác cho catalog **egress tới mọi đích TCP/443**, thêm policy chặt hơn **không thu hồi** phần allow đó. Cần sửa/xóa policy cấp quyền thừa và kiểm tra effective set.

## 22. Kubernetes DNS egress và default-deny

Khi workload có default-deny egress, cần thiết kế riêng **DNS resolver path**.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: catalog-allow-dns-example
  namespace: catalog-prod
spec:
  podSelector:
    matchLabels:
      app: catalog
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

**Chỉ dùng được nếu resolver thực nằm ở những Pod được selector chọn**, và CNI đánh giá đúng destination/backend sau các bước Service translation. Nhiều cluster dùng **NodeLocal DNSCache, cloud-managed DNS hoặc DNS proxy ở node**, nên phải quan sát DNS configuration thực trước khi áp.

### Tránh sửa lỗi DNS bằng mở tất cả egress

Nếu DNS fail sau áp policy:

1. Xác định resolver IP và thực thể phục vụ (CoreDNS/NodeLocal/managed).
2. Kiểm tra UDP/TCP DNS path và namespace/labels.
3. Tìm các **policy khác đang chọn source Pod**.
4. Xem CNI policy enforcement, service NAT translation và host-network exceptions.
5. Chỉ mở đúng resolver theo thiết kế.
6. Test lại **resolution + application flow**; chỉ DNS PASS chưa có nghĩa payment API reachable.

### ipBlock và Service IP

Ví dụ allow **ipBlock CIDR** có thể phù hợp cho external endpoint, nhưng với Service ClusterIP hoặc Pod IP được NAT, **giai đoạn áp policy trước/sau translation có thể khác giữa CNI và cloud**. Không mặc định một CIDR chỉ định Service VIP luôn là lựa chọn bền vững hơn dùng Pod/namespace selectors.

## 23. Cloud egress: route, Security Group, NACL và NAT gateway

Trong cloud, một workload chỉ có private IP nhưng vẫn có thể truy cập Internet thông qua **NAT gateway, egress firewall, proxy hoặc private endpoint**. Không có public IP trên instance/Pod **không đồng nghĩa outbound bị chặn**.

~~~text
Private App Subnet
        |
   SG / Subnet NACL
        |
      Route table
        |
   NAT / Egress Firewall
        |
   Internet Gateway / Transit / Partner
        |
     Destination
~~~

Đường thật có thể không đi qua mọi thành phần trong sơ đồ; các provider dùng route/SG/NACL/firewall và gateway với semantics khác nhau. Hãy vẽ **đúng path đến đích** thay vì áp quy tắc chung “private subnet an toàn”.

### Ma trận đánh giá

| Thành phần | Câu hỏi |
|---|---|
| **Route table** | Destination CIDR đi qua next hop nào? Có default route Internet không? |
| **Workload/ENI Security Group** | Outbound port/protocol/destination cho phép gì? |
| **Subnet Network ACL** | Có stateless outbound/return inbound rules phù hợp không? |
| **NAT gateway** | Traffic đi ra với source public/private IP nào? Ai chia sẻ egress IP? |
| **Cloud network firewall** | Có policy theo địa chỉ, state, ứng dụng/FQDN nếu hỗ trợ không? |
| **Private endpoint/peering/transit** | Dữ liệu đi qua private path nhưng có vượt vùng tin cậy không? |
| **DNS resolver** | App có thể tự dùng external resolver hoặc DoH/DoT không? |
| **Telemetry** | Có VPC flow logs, firewall decision logs và proxy logs không? |

### AWS ví dụ theo semantics

- **Security Group** có thể giới hạn outbound TCP/443 tới một CIDR/target phù hợp và nhận return traffic theo **stateful connection tracking**.
- **Network ACL** cần kiểm tra **chiều outbound tới destination service port và chiều inbound response tới ephemeral destination port** nếu ACL đang hạn chế return path.
- **NAT Gateway** chủ yếu cung cấp translation/egress path, **không tự là cơ chế DLP theo user/object/HTTP payload**.
- Nếu cần kiểm soát FQDN/HTTP/SaaS tenant hoặc egress inspection, phải dùng cơ chế **egress filtering/proxy/cloud network firewall** phù hợp và xác minh đường không bypass.

Không sao chép AWS NACL kiểu stateless để kết luận **Azure NSG hoặc Google Cloud firewall cũng phải mở return ephemeral rules giống hệt**; các nền tảng đó có stateful flow handling và thứ tự/quy tắc riêng.

## 24. IPv6 egress và các đường bypass chính sách IPv4

Khi tổ chức chỉ kiểm tra outbound **IPv4 0.0.0.0/0**, workload dual-stack có thể còn đường **IPv6** qua địa chỉ/route/firewall khác.

~~~text
Application dual-stack
       |
       +-- IPv4 -> NAT v4 -> Egress firewall v4
       |
       +-- IPv6 -> IPv6 route/gateway -> v6 firewall
                      (must be independently assessed)
~~~

### Điểm quan trọng

1. Dải **::/0** đại diện toàn bộ không gian IPv6, tách biệt với IPv4 0.0.0.0/0.
2. Host, Pod, gateway và Service có thể chọn **AAAA/IPv6** khi DNS/OS hỗ trợ.
3. Stateful firewall v4 rule không tự áp cho mọi v6 flow; khi dùng **ipBlock** cần CIDR v6 phù hợp.
4. Trong IPv6, **ICMPv6** có vai trò bắt buộc cho PMTUD/neighbor/routing ở các phạm vi liên quan.
5. Một đường IPv6 có thể không đi qua cùng IPv4 NAT/egress gateway; phải kiểm tra **route và enforcement point** thực.
6. **NAT64/DNS64** hoặc proxy dual-stack có thể thay đổi địa chỉ/giao thức nhìn thấy tại boundary.

### Test tối thiểu

| Trường hợp | Mong muốn |
|---|---|
| Service được duyệt qua IPv4 | ALLOW |
| Service được duyệt qua IPv6 khi triển khai | ALLOW |
| Đích ngoài quyền qua IPv4 | DENY |
| Đích ngoài quyền qua IPv6 | DENY |
| Truyền payload lớn qua path v6/VPN | PMTUD hoạt động |

**IPv4 policy PASS không đủ để tuyên bố không có egress bypass ở IPv6**; ghi rõ **NOT_APPLICABLE** nếu kiến trúc không chạy IPv6 và xác minh giả định đó.

## 25. Egress proxy/gateway: kiểm soát đích và ứng dụng

Một egress proxy/gateway giúp **tập trung chính sách** hơn so với mở direct Internet cho mọi workload.

~~~text
Workload A ─┐
Workload B ─┼──> Authenticated Egress Gateway
Workload C ─┘       |
                   +-- policy: identity, destination, port
                   +-- optional TLS/HTTP inspection
                   +-- DLP / rate / audit where supported
                   |
                   v
              Approved services
~~~

### Hai điểm phải bảo vệ cùng lúc

1. **Source → Gateway**: ai được dùng proxy, ai có thể yêu cầu route nào; không cho một workload giả mạo danh tính workload khác.
2. **Gateway → Destination**: proxy chỉ kết nối tới **origin/port/protocol được duyệt**, kiểm tra trust và áp policy nội dung khi hợp pháp/phù hợp.

Nếu mọi Pod được tự do bỏ qua gateway và mở trực tiếp TCP/443 ra Internet, proxy chỉ là **đường khuyến nghị**, không phải enforcement point. Cần **egress routing/firewall/NetworkPolicy** khiến traffic nhạy cảm phải đi qua điểm kiểm soát được định nghĩa.

### HTTP CONNECT và phạm vi visibility

Trong **HTTP CONNECT tunnel**, proxy có thể biết target hostname/port mà client đề nghị, nhưng **không nhất thiết xem được payload HTTPS** nếu TLS đi xuyên tunnel đến server. Nếu proxy **terminate/re-encrypt TLS**, phải thiết kế **trust, certificate validation, privacy và phạm vi inspection**. Không đánh đồng **proxy đã xác thực client** với **DLP đã kiểm tra file/JSON payload**.

### Egress gateway không phải open forward proxy

Một open proxy cho mọi authenticated user tới mọi IP/port có thể làm tăng blast radius của credential bị lộ. Thiết kế an toàn nên có:

- Destination allowlist theo **service owner/identity**, không chỉ TCP/443.
- Quyền theo **source workload/user và action**, có hạn chế kết nối đồng thời.
- Bảo vệ **link-local/metadata/private management destinations** khỏi proxy misuse.
- Chặn hoặc điều kiện hóa **dynamic upstream address**, DNS resolution và redirect.
- Các đường **cloud private endpoints** vẫn có policy nếu vượt trust boundary.
- Audit có phân tách **source principal, destination, protocol, policy decision**.

## 26. FQDN-aware egress và giới hạn của DNS/SNI allowlists

Một chính sách cho phép **api.partner.example.test** có vẻ cụ thể hơn mở toàn Internet, nhưng việc ánh xạ tên → IP không bất biến:

~~~text
api.partner.example.test
     |
     | DNS answers may vary
     v
  IP A / IP B / CDN shared address
     |
     v
TLS handshake + HTTP Host/path
~~~

### Những vấn đề phải giải quyết

| Vấn đề | Tác động |
|---|---|
| **DNS TTL và IP rotation** | IP được phép có thể hết hạn hoặc thay đổi liên tục |
| **CDN shared IP** | Một IP có thể host nhiều tenant/hostname |
| **SNI/HTTP Host mismatch** | Policy domain có thể không khớp origin thực tế |
| **Encrypted Client Hello hoặc protocol khác** | Metadata SNI có thể không quan sát được như kỳ vọng |
| **DNS caching ở app/proxy** | Firewall và client có thể dùng bộ IP tại thời điểm khác nhau |
| **HTTP redirect** | Client có thể chuyển sang hostname/port chưa duyệt |
| **DNS rebinding/poisoning trong threat model** | Cần ràng buộc resolver, target và policy khi resolve |
| **IP literal/alternate DNS** | Client có thể bỏ đường FQDN nếu còn direct route |

**Không phải mọi FQDN policy đều có cùng độ tin cậy**: có sản phẩm resolve DNS rồi lập IP set, có proxy kiểm tra CONNECT target, có cơ chế xác thực server certificate và HTTP Host. Hãy xác minh **thời điểm matching, nguồn DNS, resolver trust và cách xử lý CDN/multi-tenant**.

### Không nhầm tên miền với dữ liệu DLP

Ngay cả khi chỉ cho phép một domain SaaS, tổ chức vẫn có thể cần phân biệt **tenant công ty** với **tài khoản cá nhân tại cùng SaaS provider**. L3/L4 và FQDN allowlist không nhất thiết có thông tin để thực hiện điều này. Khi cần, dùng **tenant-aware access controls/SSE/CASB/API integration hoặc endpoint DLP** được hỗ trợ.

## 27. DLP kết hợp egress: chặn kênh khác chặn dữ liệu

DLP quan tâm **dữ liệu gì, ở đâu, ai gửi, gửi tới ai, theo hành động nào và có được phép không**. Kiểm soát port/protocol giới hạn các kênh mạng, nhưng không tự biết một file chứa bí mật kinh doanh, dữ liệu cá nhân hoặc khóa API.

~~~text
Source workload / user
       |
       | Data classification + policy
       v
Network egress allowlist
       |
       v
Authenticated proxy / SaaS controls
       |
       v
Optional content-aware DLP enforcement
       |
       v
Approved destination and tenant
~~~

### So sánh những lớp kiểm soát

| Lớp | Có thể kiểm soát | Không tự kiểm soát |
|---|---|---|
| **L3/L4 egress firewall** | IP/CIDR, protocol/port, một số trạng thái phiên | File content, user tenant, HTTP body |
| **DNS resolver policy** | Tên miền/truy vấn qua resolver được quản lý | Dữ liệu HTTPS ở endpoint đã được phép |
| **Secure web gateway / HTTP proxy** | Domain, URL, user/app context, HTTP action theo khả năng | Mọi opaque TCP hoặc TLS passthrough |
| **CASB/SSE tenant-aware** | SaaS app/tenant/action khi có tích hợp | Dữ liệu đi qua giao thức không thuộc coverage |
| **Endpoint DLP** | File/process/user action trên máy theo agent | Thiết bị/đường không có agent |
| **Data classification / rights management** | Nhãn dữ liệu và chính sách sử dụng | Không tự chặn mọi network route |
| **Application DLP** | Chính sách export/share/upload trên backend | Traffic được gửi ngoài app mà nó quản lý |

### Ví dụ thực tế

Một báo cáo tài chính được xuất **qua HTTPS TCP/443 tới một SaaS đã được allow**, nhưng người nhận thuộc **tenant cá nhân không được chấp thuận**. Network firewall nhìn thấy port/đích hợp lệ; DLP hoặc SaaS tenant policy mới có thể quyết định **hành động export/share đó không được phép** nếu có đủ context.

**Chặn toàn bộ lưu lượng 443 để chống exfiltration không phải giải pháp thực tế cho hệ thống cần HTTPS**. Thiết kế phải kết hợp **đúng dịch vụ, danh tính, phân loại dữ liệu và điểm enforcement**.

## 28. TLS inspection: giới hạn kỹ thuật, quyền riêng tư và rủi ro

TLS encryption làm giảm khả năng đọc payload tại một **network middlebox** không terminate traffic. Một số giải pháp có thể **kiểm tra TLS/HTTPS** bằng proxy được quản trị, nhưng đây là quyết định có ảnh hưởng lớn.

### Phải xác định

1. Tổ chức có **quyền/đồng thuận/phạm vi hợp pháp** để inspection loại traffic này không?
2. Kết nối nào được **giải mã, passthrough hoặc loại trừ**, và vì sao?
3. Certificate/trust của proxy, origin validation, CA key storage và log retention được bảo vệ thế nào?
4. **Certificate pinning, mTLS, end-to-end application encryption** có làm proxy không thể/không nên terminate không?
5. Hệ thống có hiểu đúng **HTTP/2, HTTP/3/QUIC, gRPC, WebSocket và streaming** không?
6. Dữ liệu giải mã có được gửi sang hệ thống DLP hay analytics khác? Giảm **bản sao dữ liệu nhạy cảm** ra sao?
7. Khi inspection lỗi, chính sách là **fail closed** hay bypass được phê duyệt theo loại dữ liệu?
8. Người dùng và owner có được thông báo về **quy trình và giới hạn giám sát** theo chính sách không?

**Không cài root CA trái phép, không tắt certificate verification và không sử dụng TLS interception để đọc dữ liệu cá nhân ngoài phạm vi được duyệt**. Egress security cần đạt an toàn mà không tạo một kho dữ liệu giải mã kém bảo vệ hơn hệ thống ban đầu.

### Phạm vi visibility

| Đường | Network firewall L3/L4 | Proxy L7 không terminate | Proxy L7 terminate hợp lệ |
|---|---|---|---|
| HTTPS TCP/443 | IP/port/flow | Có thể có hostname/CONNECT metadata | Có thể xem HTTP metadata/payload theo cấu hình |
| HTTP/3 QUIC UDP/443 | IP/port/flow | Phụ thuộc sản phẩm, nhiều giới hạn | Chỉ nếu proxy thực sự hỗ trợ QUIC/HTTP3 |
| mTLS ứng dụng | IP/port/flow | TLS metadata có giới hạn | Cần kiến trúc terminate với xác thực hai chiều được duyệt |
| Proprietary encrypted TCP | IP/port/flow | Không biết nội dung nếu không hiểu protocol | Chỉ khi có hỗ trợ và quyền giải mã phù hợp |

Không được quảng cáo “kiểm tra 100% egress content” nếu còn **opaque protocols, ứng dụng tự mã hóa payload, device ngoài agent hoặc các đường không qua proxy**.

## 29. Giám sát C2 và exfiltration qua kênh hợp lệ

Một attacker hoặc phần mềm bị xâm nhập có thể dùng **protocol/port được mạng cho phép** để liên lạc với hệ thống ngoài quyền. Vì vậy network egress controls vừa có tác dụng **ngăn một số đường truyền**, vừa cung cấp **tín hiệu điều tra** khi thấy hành vi bất thường.

### Những tín hiệu phòng thủ nên chú ý

| Tín hiệu | Câu hỏi phân tích |
|---|---|
| **Destination lần đầu xuất hiện** | Workload có lý do nghiệp vụ để gọi đích đó không? |
| **Port/protocol mới** | Có deployment/SDK update hay protocol drift nào được duyệt? |
| **Traffic volume lệch baseline** | Có job batch hợp lệ hoặc export bất thường? |
| **Nhiều DENY liên tiếp** | App bị lỗi config, scan nội bộ hay nghi hành vi lạ? |
| **DNS query bất thường** | Resolver/client thay đổi, domain mới hoặc lỗi retry? |
| **Long-lived encrypted connection** | Streaming hợp lệ hay kênh cần điều tra thêm? |
| **SaaS destination tenant không phê duyệt** | Có hành vi upload/share ra tài khoản ngoài tổ chức? |
| **Late-night high-volume outbound** | Backup/job có lịch, hay exfiltration risk? |
| **Source identity không khớp app owner** | Credential/workload misconfiguration hoặc compromise? |

**Không tự coi một tín hiệu là bằng chứng tấn công.** Các chương trình backup, CI/CD, metrics và data synchronization cũng có traffic tăng đột biến. Cần kiểm tra **change history, request ID, application owner, DLP policy và nội dung được phép** trước khi quyết định containment.

### Giới hạn phát hiện

Một kết nối HTTPS tới dịch vụ được duyệt có thể không lộ payload tại network firewall. Không thể khẳng định “không có data loss” từ flow logs **ACCEPT/DENY**. Cần dữ liệu từ **app audit, proxy, endpoint DLP, SaaS API, identity logs và data classification** theo quyền hợp pháp.

## 30. Cloud, hybrid và VPN: private traffic vẫn có thể làm mất dữ liệu

Không phải exfiltration chỉ xảy ra qua Internet gateway:

- Workload cloud gửi dữ liệu tới **VPC/VNet khác** qua peering.
- API gọi **managed SaaS hoặc object storage** qua private endpoint nhưng sai account/tenant.
- Chi nhánh dùng **VPN tunnel** tới trung tâm dữ liệu/đối tác; một route rộng vượt phân đoạn mong muốn.
- Service qua **multi-cluster mesh/egress gateway** sang trust domain khác.
- Một app gọi **metadata/management service** ở private/link-local network ngoài nhu cầu.

### Kiểm soát cần tính theo đích thực

| Đường | Quy tắc quan trọng |
|---|---|
| **Public Internet** | Allowlist đích, proxy, firewall, DLP/tenant controls |
| **Private peering** | Route/CIDR và workload identity, boundary authorization |
| **VPN/transit** | Tunnel encryption chưa thay per-service authorization |
| **Cloud object storage endpoint** | Account/bucket/project/tenant identity và IAM controls |
| **Multi-cluster** | Cluster/trust domain identity, network policy ở hai phía |
| **Service mesh egress gateway** | Caller policy, destination identity và đường direct bypass |

**Một endpoint được truy cập qua private IP không chứng minh dữ liệu vẫn thuộc tổ chức**. Cloud storage/service cần nhận diện **account, bucket, tenant, role và API operation**.

## 31. Threat model cho egress từ một workload nhạy cảm

Xem một ứng dụng **billing** có quyền đọc dữ liệu giao dịch và cần gọi payment provider, logging collector, identity service. Nếu billing bị xâm nhập, kẻ tấn công có thể tận dụng các quyền mạng của nó; dù firewall đã chặn phần lớn port, một kênh **HTTPS tới đích hợp lệ** vẫn có thể bị lạm dụng nếu ứng dụng/credential bị chiếm.

~~~text
                    Billing workload
                  (sensitive records)
                    /      |       \
                   /       |        \
              Payment    Logging     Identity
             TCP/443    TCP/4317    TCP/443
              ALLOW       ALLOW       ALLOW
                  |
              Unauthorized paths:
                 X arbitrary SaaS HTTP/HTTPS
                 X direct external SMTP/SSH
                 X unapproved DNS/DoH service
                 X management/metadata endpoint
~~~

### Những threat scenarios

| Mối đe dọa | Port-only rule có giúp không? | Lớp cần bổ sung |
|---|---|---|
| **Lateral movement đến DB khác** | Có nếu chặn IP/port phù hợp | Workload identity/DB auth/microsegmentation |
| **Upload dữ liệu qua public HTTPS** | Ít nếu vẫn allow mọi TCP/443 | Destination allowlist, proxy, app/endpoint DLP |
| **DNS-based unauthorized communication** | Chặn một số direct UDP/TCP/53 | Resolver policy, DoH/DoT controls, analytics |
| **Gửi email trực tiếp tới server ngoài** | Chặn TCP/25/465/587 tới outside relay | Email API/HTTPS controls, recipient DLP |
| **Lạm dụng allowed payment API** | Không nếu traffic vẫn đúng 443/đích | API auth, scope, data validation, anomaly detection |
| **Rò dữ liệu qua object storage cross-account** | Không đủ với IP/443 | Cloud IAM, endpoint/tenant/bucket policy |
| **Vượt qua egress proxy** | Chỉ nếu direct paths bị chặn | Route/firewall/CNI enforcement, negative tests |
| **Tấn công làm cạn tài nguyên** | Có thể hạn chế theo rate/connection | Quotas, WAF/gateway, resource controls |

### Xác định tài sản và trust boundary

1. **Dữ liệu** cần bảo vệ là loại nào, giá trị và phạm vi owner?
2. Những workload nào được **đọc dữ liệu trước khi gửi đi**?
3. Đích hợp pháp ở **account/tenant/region nào**?
4. Nếu network credentials bị lộ, attacker có thể dùng **đường khác** nào?
5. Lớp nào có thể **chứng minh danh tính đích** và **kiểm tra hành động upload/share**?
6. Sự kiện nào cần alert, ai có quyền **cô lập source** và điều kiện dừng ứng cứu?

**Không chỉ threat-model destination “Internet”**: một service nội bộ hoặc cloud tenant khác cũng có thể là đích trái quyền của dữ liệu được bảo vệ.

## 32. Policy as Code: lưu ý định và kiểm tra rule

Để tránh rule nằm rải rác trên console firewall, SG, CNI và proxy, nên lưu **security intent** trong cấu hình có thể review và test.

### Ví dụ khai báo policy logic, không phải cú pháp chạy trực tiếp

~~~yaml
policy_id: billing-egress-v1
environment: staging
owner: billing-platform
source_workload: billing-api
default_action: deny
allowed_flows:
  - id: payment-api
    destination_service: approved-payment-provider
    transport: tcp
    destination_port: 443
    identity_requirement: validate-server-and-client-policy
    data_class: restricted-transaction-data
  - id: company-dns
    destination_service: approved-dns-resolver
    transports:
      - udp
      - tcp
    destination_port: 53
  - id: telemetry
    destination_service: approved-otel-collector
    transport: tcp
    destination_port: 4317
exceptions:
  - id: legacy-integration
    enabled: false
    owner: integration-team
    expiry: "2026-12-31"
verification:
  positive_flow_tests_required: true
  negative_flow_tests_required: true
  ipv4_ipv6_review_required: true
~~~

Đây là **schema mô tả học tập**, không phải Terraform, Kubernetes NetworkPolicy hoặc file có thể import vào một cloud firewall. Các trường phải được chuyển sang **effective provider policy** và test trên hệ thống thật; không phát sinh nhầm rằng một YAML đẹp đã chặn traffic.

### Lint nên phát hiện

| Kiểm tra | Phát hiện |
|---|---|
| **Unknown source/owner** | Rule không rõ chịu trách nhiệm |
| **Wildcard destination** | All Internet/any tenant ngoài chính sách |
| **Protocol missing/ANY** | Mở cả TCP/UDP/ICMP không chủ ý |
| **Port range too broad** | Quyền lớn hơn nhu cầu app |
| **Rule precedence/overlap** | Shadowed allow/deny hoặc broad allow |
| **Stateful/stateless mismatch** | Thiếu return path, sai ephemeral |
| **IPv4/IPv6 asymmetry** | Đường v6 không được lọc tương đương |
| **NAT/proxy bypass** | Workload có direct route quanh gateway |
| **Policy/secret owner drift** | Rule cũ, quyền cloud admin quá rộng |
| **Expired exception** | Ngoại lệ tạm không được thu hồi |
| **Missing negative tests** | Không chứng minh đích ngoài quyền bị chặn |
| **Unapproved protocol upgrade** | App sử dụng QUIC/DoH mới không được review |

**Rule linter không hiểu đầy đủ data classification/tenant identity** nếu không có input đáng tin. Policy-as-code bổ trợ quản trị, không thể thay security review và runtime validation.

## 33. Configuration drift, temporary exceptions và change management

**Configuration drift** xảy ra khi policy đang vận hành khác desired state đã được phê duyệt. Một trường hợp phổ biến: đội vận hành mở outbound TCP/443 tới 0.0.0.0/0 để chữa lỗi dependency rồi quên thu hẹp sau sự cố.

~~~text
Approved flow inventory
         |
      Desired IaC
         |
      Deployment
         |
     Runtime policy
         |
   Read-only comparison
         |
       Drift?
      /      \
    No        Yes
    |          |
 Monitor    Owner review
             + rollback plan
~~~

### Nguyên tắc quản trị

- Mọi allow mới có **ticket, business owner, source/destination, protocol, duration và evidence**.
- **Emergency allow** phải có TTL, điều kiện thu hồi, người phê duyệt và postmortem.
- Mọi thay đổi **NAT/route, LB, DNS, cloud region, IPv6, ServiceAccount, proxy và provider endpoint** kích hoạt review.
- Quyền sửa firewall/NetworkPolicy/proxy theo **least privilege**; ai có thể mở “allow any” là một quyền nhạy cảm.
- Lưu **cloud/API audit logs** của thay đổi rule và người thực hiện.
- Không tự động rollback một rule gây drift mà chưa xác minh nó có phải **biện pháp ứng cứu đang hoạt động** theo ticket hợp lệ không.
- Diễn tập **revert policy** với đúng owner trước khi thay đổi phạm vi subnet/namespace lớn.

### Hạn chế burst và race khi deploy

Một số thay đổi firewall rule có thể được thực thi trong nhiều bước hoặc có độ trễ giữa control plane và dataplane. Không mặc định nhóm API changes là **atomic transaction**. Trên egress gateway, triển khai allow mới/deny cũ theo thứ tự có kiểm soát và test negative flows sau từng đợt.

## 34. Telemetry: đọc flow logs, proxy logs và DLP events đúng phạm vi

Một luồng bị từ chối có thể xuất hiện trong **firewall/CNI/SG/NACL logs**, còn một nội dung upload bị DLP chặn có thể xuất hiện ở **proxy/app/CASB/endpoint**. Hai loại bằng chứng khác nhau.

### Log flow giả lập

~~~text
timestamp=2026-11-28T15:00:00+07:00
environment=staging
source_workload=billing-api
source_ip=10.20.20.10
source_port=53124
destination_ip=198.51.100.20
destination_port=443
transport=tcp
network_boundary=egress-firewall
policy_id=billing-egress-v1
decision=DENY
reason=destination_not_in_approved_set
bytes=0
data_classification=NOT_OBSERVED_AT_L4
~~~

Đây **không phải chuẩn log cố định** của AWS/Azure/GCP/CNI và **bytes=0** trong log giả lập không đại diện mọi semantics của flow logs thật. Flow logs có thể aggregate/sample, ghi theo interface, thiếu payload hoặc không nêu được rule cụ thể.

### Log proxy/DLP giả lập

~~~text
timestamp=2026-11-28T15:01:00+07:00
source_principal=billing-api-service
application=corporate-file-sharing
destination_tenant=personal-tenant-example
transport=https
destination_port=443
policy_id=restricted-data-sharing
decision=DENY
reason=unapproved_destination_tenant
content_sample=[NOT_LOGGED]
credential=[NOT_LOGGED]
trace_id=example-trace-001
~~~

**Không sao chép payload dữ liệu nhạy cảm vào SIEM chỉ để chứng minh DLP DENY.** Nên lưu metadata tối thiểu, hashed/classification identifiers theo chính sách, masking, retention, quyền truy cập và chain-of-custody khi xử lý sự cố.

### Correlation theo từng lớp

| Nguồn | Câu hỏi trả lời tốt | Không tự chứng minh |
|---|---|---|
| **Host/CNI socket events** | Process/workload mở kết nối nào | Data content đúng policy |
| **Cloud VPC flow logs** | Packet/flow theo interface/điểm thu quan sát | HTTP method, token, tài liệu được gửi |
| **Egress firewall logs** | Rule decision theo flow khi ghi nhận | Backend thật sự xử lý request |
| **Proxy HTTP/SSE logs** | URL/Host/tenant/action theo khả năng | Mọi non-proxy traffic cũng được nhìn thấy |
| **DNS resolver logs** | Truy vấn qua resolver được duyệt | Toàn bộ DoH hoặc direct-IP connections |
| **App audit logs** | User/workload, object, export/share action | Network path nếu app bị bypass |
| **Endpoint DLP** | File/process action trên endpoint có agent | Trường hợp server/cloud workload không có agent |
| **IdP/IAM audit** | Principal/session/role và thay đổi quyền | Payload được truyền qua kết nối |

**Một firewall ACCEPT không chứng minh DLP ALLOW, cũng như DLP DENY không tự chứng minh mọi packet đến đích đã bị drop.** Phải biết enforcement point và outcome cụ thể.

## 35. Runbook khi outbound bị chặn hoặc phát hiện egress lạ

### Giai đoạn 1 — Phân loại sự cố

1. Source **workload/process/user, namespace/host/subnet, IP và owner**.
2. Destination **IP/CIDR/FQDN/service identity/tenant**, protocol và port.
3. Thời điểm, môi trường, thay đổi gần nhất và business impact.
4. Lỗi **DNS resolution, TCP connect timeout/refused, UDP application timeout, TLS handshake, proxy 403, DLP denial hay backend 5xx**?
5. Có **NAT, VPN, egress gateway, load balancer hoặc IPv6** trên path không?

### Giai đoạn 2 — Định vị đúng lớp

~~~text
Egress request fails
        |
    DNS resolves?
      /      \
     No      Yes
     |        |
  DNS path   Can packet reach destination?
             /                   \
            No                   Yes
            |                     |
  Route / SG / NACL / CNI      TLS or proxy policy?
                              /           \
                            Fail          Pass
                             |             |
                         PKI/SAN/        App/DLP/tenant
                         CONNECT         authorization
~~~

### Giai đoạn 3 — Khi có dấu hiệu thất thoát dữ liệu

- Xác định **data class, source identity, destination account/tenant, khối lượng/loại hành động** qua nguồn audit được phép.
- Đối chiếu flow với **business approved transfer**; tránh quy kết sai các tác vụ backup/sync.
- Nếu rủi ro nghiêm trọng, kích hoạt **incident response** và cô lập đúng source/destination theo quyền và change khẩn.
- Bảo toàn logs/chứng cứ mà không phát tán thêm dữ liệu nhạy cảm.
- Kiểm tra cả **những đường egress tương đương**: proxy, private endpoint, IPv6, multi-cluster, SaaS API.
- Thu hồi/rotate **credential/token** khi có bằng chứng cần thiết; tránh chỉ chặn một port rồi kết luận sự cố đã xử lý.

### Giai đoạn 4 — Sửa có kiểm soát

1. Kiểm tra **rule thực áp dụng**, priority/state, source identity và destination sau NAT.
2. Nếu flow hợp lệ bị chặn, thêm **allow hẹp nhất** cho service/port/protocol/nguồn được duyệt.
3. Nếu protocol mới xuất hiện, xác minh nó thuộc thay đổi được phê duyệt trước khi mở.
4. Nếu dữ liệu bị gửi sai tenant, sửa **tenant-aware DLP/app authorization**, không chỉ IP/port.
5. Không “tạm thời mở 0.0.0.0/0 ANY” mà thiếu owner, TTL, blast radius và audit.
6. Test **ALLOW nghiệp vụ + DENY ngoài quyền**, cả DNS/IPv6/proxy fallback.

### Giai đoạn 5 — Hậu kiểm

Ghi **policy diff, owner, exception expiry, đường thực, flow/DLP telemetry, business SLO, rollback readiness** và nguyên nhân gốc. Không đóng sự cố chỉ vì một API timeout đã hết: phải chứng minh **traffic ngoài quyền vẫn bị chặn** và DLP không mất coverage trên các giao thức mới.

## 36. Case study 1: chỉ mở TCP/443 vẫn không ngăn upload sai tenant

**Bối cảnh giả định:** Bộ phận tài chính dùng dịch vụ lưu trữ SaaS để trao đổi tài liệu. Công ty chặn mọi port outbound ngoại trừ DNS và **TCP/443**; firewall không giới hạn destination hoặc tenant của dịch vụ HTTPS.

### Sự kiện

~~~text
Employee workstation
        |
        | HTTPS TCP/443
        v
SaaS provider shared hostname
        |
        +-- Corporate tenant (approved)
        |
        +-- Personal tenant (not approved)

L3/L4 firewall:
  ALLOW TCP/443 to provider IP

Missing control:
  SaaS account/tenant + data classification
~~~

Một nhân viên vô tình upload tài liệu **restricted** vào **tenant cá nhân** tại cùng provider. Kết nối TLS hợp lệ, IP và TCP/443 được phép, không có dấu hiệu port/protocol bất thường.

### Phân tích nguyên nhân

1. Network policy kiểm soát **kênh HTTPS**, nhưng không phân biệt **tenant hoặc hành động upload**.
2. Một destination domain/IP có thể phục vụ **nhiều accounts/tenants**.
3. DLP dựa vào flow logs không thấy được loại file/recipient.
4. Chính sách “TLS hợp lệ nên an toàn” đánh đồng **encrypted transfer** với **authorized transfer**.

### Thiết kế khắc phục

- Bổ sung **SaaS tenant-aware policies/identity-aware proxy/CASB/SSE** hoặc application integration được phép.
- Phân loại dữ liệu, hạn chế upload/share theo **data label, owner, tenant và action**.
- Giới hạn outbound đến **SaaS endpoints cần thiết** thay vì toàn Internet.
- Bảo vệ credentials, xác minh user/session/tenant và cảnh báo upload bất thường.
- Test **corporate tenant ALLOW** và **personal tenant DENY** với **dữ liệu tổng hợp không nhạy cảm**.

**Bài học:** Restrict port là cần thiết nhưng **không đủ cho DLP khi đích được phép có nhiều tenant và dữ liệu nhạy cảm**.

## 37. Case study 2: default-deny làm lỗi DNS và health checks

**Bối cảnh giả định:** Một nhóm triển khai default-deny egress cho Kubernetes namespace **catalog-prod**, chỉ cho TCP/443 tới API đối tác. Sau rollout, service trả lỗi name resolution timeout và readiness/health của một số Pod trở nên không ổn định.

### Trước rollout

~~~text
App -> NodeLocal DNSCache (per cluster)
App -> Partner API HTTPS TCP/443
App -> Internal logging collector TCP/4317
~~~

### Policy mới

~~~text
ALLOW catalog -> partner CIDR TCP/443
DENY all other outbound by default

No verified DNS resolver path.
No telemetry flow allowed.
~~~

### Lỗi suy luận

- Nhóm viết rule theo **endpoint nghiệp vụ cuối cùng** nhưng quên **phụ thuộc DNS** và log collector.
- Họ copy mẫu allow CoreDNS Pod theo nhãn mà **cluster thật dùng NodeLocal DNSCache**.
- DNS timeout làm ứng dụng không mở TCP đến partner dù firewall 443 đã cho phép.
- Thiếu telemetry làm việc điều tra sau rollout khó hơn.

### Hướng xử lý

1. Đọc DNS configuration thực của Pod và xác định **resolver path**, không mở all UDP/53 toàn Internet.
2. Xem CNI NetworkPolicy enforcement/Service NAT/host-network handling.
3. Thêm đúng allow DNS UDP/TCP theo nguồn/đích đã xác minh và logging collector theo nhu cầu.
4. Chạy **resolve test, HTTPS call, telemetry delivery** và negative egress tests.
5. Rollout từng nhóm workload hoặc namespace có kiểm soát.

**Bài học:** Một egress policy an toàn phải bảo vệ **availability của những dependencies được phê duyệt**, không chỉ chặn “Internet”.

## 38. Case study 3: AWS NACL chặn gói phản hồi vì sai ephemeral port

**Bối cảnh giả định:** Ứng dụng tại **10.20.20.10** khởi tạo TCP connection tới partner **198.51.100.20:443**. AWS Security Group đã cho outbound phù hợp, nhưng subnet custom NACL chỉ allow chiều outbound và không allow inbound response tới ephemeral destination port.

### Mô hình gói

~~~text
Request from application subnet:
  src 10.20.20.10:53124
  dst 198.51.100.20:443
  subnet NACL OUTBOUND: ALLOW

Response to application subnet:
  src 198.51.100.20:443
  dst 10.20.20.10:53124
  subnet NACL INBOUND: DENY (no applicable allow)
~~~

**Giả định route và NAT path đã được cấu hình phù hợp**; ví dụ giản lược để cô lập tác động của NACL.

### Vì sao operator có thể sửa sai?

Nếu chỉ nhìn “outbound 443 đã mở”, operator có thể tăng phạm vi egress lên **0.0.0.0/0** hoặc thêm port ngẫu nhiên mà không giải quyết **inbound return path**. AWS NACL stateless **không tự theo dõi phiên** như Security Group stateful.

### Cách xử lý

1. Ghi 5-tuple request/response **ở đúng điểm trước/sau NAT**.
2. Đọc **NACL thực gắn với subnet** và first-match rule priority.
3. Xác minh destination ephemeral range **của client/source ở điểm áp ACL**.
4. Chỉ bổ sung rule inbound return path cần thiết với CIDR/protocol phù hợp, theo chính sách được duyệt.
5. Test HTTPS hợp lệ và tiếp tục DENY đường không được phép.

**Bài học:** Không thể thiết kế egress chỉ với port đích của gói request khi **boundary dùng stateless ACL**.

## 39. Case study 4: HTTP/3/QUIC thay đổi coverage của proxy

**Bối cảnh giả định:** Tổ chức cho phép HTTPS qua một secure web gateway có hỗ trợ kiểm soát **HTTP/1.1 và HTTP/2 trên TCP/443**. Sau cập nhật client, một số kết nối sử dụng **HTTP/3 trên UDP/443**; nhóm giám sát chỉ thấy lượng TCP qua proxy giảm.

### Dấu hiệu

~~~text
Before:
  Client -> HTTPS proxy -> Approved API TCP/443

After:
  Client -> UDP/443 to external endpoint

Observed:
  Proxy TCP request count decreases
  App still functions via an alternate path
~~~

Đây là tình huống mô phỏng: **không phải mọi client/OS tự mở direct QUIC**. Muốn xác định có bypass hay không phải xem **network route, proxy/PAC settings, firewall logs và application protocol**.

### Rủi ro

- Policy trên **proxy TCP** không nhìn đầy đủ traffic UDP path.
- Mở UDP/443 tới mọi đích có thể vô tình cấp quyền lớn hơn thiết kế.
- Nếu firewall chặn UDP/443, client có thể fallback về TCP/443 hoặc lỗi; hành vi phụ thuộc client/protocol.

### Cách xử lý

1. Đo **actual UDP/443 flows và endpoint owners**.
2. Xác định có cần HTTP/3 hay có thể yêu cầu TCP path có kiểm soát.
3. Nếu cho QUIC, chọn **gateway/firewall hỗ trợ HTTP/3/QUIC** và test policy theo đích/nội dung khi khả thi.
4. Test **UDP path ALLOW/DENY, fallback TCP, latency và security coverage**.
5. Ghi protocol change trong flow inventory và DLP visibility.

**Bài học:** Không được đồng nhất “cùng cổng số 443” với **cùng transport, cùng proxy path hoặc cùng khả năng DLP**.

## 40. Case study 5: NetworkPolicy allow hẹp nhưng policy khác mở rộng egress

**Bối cảnh giả định:** Ứng dụng **catalog** trong Kubernetes có NetworkPolicy chỉ allow tới payment service TCP/8443. Nhóm đánh giá tin rằng namespace đã được cách ly egress. Nhưng một Helm chart cũ cũng tạo policy **allow-all egress** chọn cùng Pod.

~~~text
Policy A: app=catalog
  egress ALLOW payment Pod TCP/8443

Policy B: app=catalog
  egress ALLOW any destination

Effective NetworkPolicy:
  Union of allowed flows
  => includes any destination from Policy B
~~~

### Nguyên nhân

Kubernetes NetworkPolicy chuẩn có **additive allow semantics**. Thêm một policy hẹp hoặc một default-deny khác **không ghi đè quyền đã được policy B cấp**. Không có **DENY rule ưu tiên cao** kiểu AWS NACL trong resource NetworkPolicy chuẩn.

### Khắc phục

1. Liệt kê tất cả NetworkPolicies **chọn cùng source Pod** và các policy mở rộng CNI nếu có.
2. Tính **effective egress allow set** trước khi tuyên bố có isolation.
3. Sửa/xóa **policy B** có owner/approval, không chỉ thêm policy C.
4. Dùng RBAC/admission hạn quyền tạo policy allow rộng, nhất là ở namespace multi-tenant.
5. Kiểm tra từ một Pod lab đã phê duyệt rằng **payment ALLOW** và **unapproved destination DENY**.

**Bài học:** Một manifest đúng không chứng minh **tập quyền thực tế** đúng khi nhiều policies cùng áp dụng.

## 41. Case study 6: IPv6 tạo đường ra không qua IPv4 NAT/inspection

**Bối cảnh giả định:** Workload được triển khai dual-stack. Policy kiểm soát IPv4 egress qua NAT và proxy, nhưng security review chưa kiểm tra IPv6 routes/SG. Một tên miền đối tác có AAAA record, khiến ứng dụng chọn IPv6 path ở môi trường hỗ trợ.

~~~text
IPv4:
  App -> NAT v4 -> Inspected egress

IPv6:
  App -> IPv6 gateway -> Destination
         (policy/telemetry not yet verified)
~~~

### Những điều cần xác nhận

1. Host/Pod có **IPv6 address** và route ngoài trust zone thực sự không?
2. Đích có AAAA record và ứng dụng có dùng IPv6 không?
3. Firewall/SG/CNI trên IPv6 path có **effective outbound deny/allow** đúng không?
4. Proxy/DLP có quan sát cùng đường, hay chỉ áp cho v4?
5. Khi test từ nguồn lab, egress ngoài quyền bị chặn tương đương trên hai address families không?

**Không tự suy rằng có IPv6 là chắc chắn bị bypass**. Hãy dùng route/policy/telemetry để kiểm chứng, sau đó sửa đúng v6 boundary. Nếu triển khai không dùng IPv6, ghi bằng chứng và trạng thái NOT_APPLICABLE, nhưng vẫn review khi bật dual-stack sau này.

**Bài học:** Chỉ số “IPv4 policy coverage 100%” không đại diện **đường egress IPv6 hoặc các translation paths**.

## 42. Thực hành an toàn: xác minh outbound path và policy trong lab

Lab chỉ sử dụng **host/cluster staging hoặc máy thuộc quyền quản trị**, tài khoản có quyền đọc và **test endpoint đã được chủ dịch vụ phê duyệt**. Không thay production firewall, không quét các IP ngoài phạm vi và không truyền file có dữ liệu thật để chứng minh DLP. Nếu thiếu môi trường, thực hiện **phân tích gói và policy trên giấy**.

### 42.1. Bối cảnh giả lập

~~~text
Source workload: catalog-api
Source subnet:   10.20.20.0/24
Source IP:       10.20.20.10

Approved DNS:    10.20.0.53 UDP/TCP 53
Approved API:    api.partner.example.test TCP/443
Approved logs:   telemetry.example.test TCP/4317

Unauthorized destination:
                 198.51.100.90 TCP/443

Expected:
  approved DNS:     ALLOW
  approved API:     ALLOW
  telemetry:        ALLOW
  unapproved HTTPS: DENY
  direct SMTP:      DENY
~~~

Tên trong **.example.test**, **198.51.100.0/24** và IP private là ví dụ để phân tích. Chúng **không phải endpoint thật để truy cập**. Mô hình yêu cầu cả policy trên workload, route/gateway và phía đối tác hoạt động phù hợp khi kiểm thử E2E.

### 42.2. Xác định 5-tuple của HTTPS

~~~text
Request:
  src=10.20.20.10:53124
  dst=198.51.100.20:443
  transport=tcp

Response:
  src=198.51.100.20:443
  dst=10.20.20.10:53124
  transport=tcp
~~~

Trả lời:

1. Stateful firewall phải cho phép gói nào để mở kết nối?
2. Nếu có AWS NACL stateless ở app subnet, rule return-direction nào có thể cần?
3. Nếu request qua NAT và source đổi IP/port, log ở firewall ngoài và log ở CNI sẽ nhìn thấy những thông tin gì khác nhau?
4. Nếu traffic dùng **UDP/443**, rule TCP/443 phía trên có cho phép nó không?

### 42.3. Đọc socket và route trên Linux (nếu được phép)

~~~bash
# Chỉ đọc, không thay cấu hình.
ss -tuna
ip route show
ip -6 route show

# Chỉ tra cách kernel dự kiến route tới IP tài liệu;
# kết quả phụ thuộc bảng route của host lab.
ip route get 198.51.100.20
~~~

Các lệnh này giúp quan sát **socket/route dự kiến**, không tự chứng minh firewall đã cho traffic qua hoặc DLP đã quan sát payload. **ss** có thể không có trong container image tối giản; không cài tool vào production container chỉ để chạy bài tập.

### 42.4. Đọc network policy Kubernetes (nếu dùng cluster lab)

~~~bash
kubectl config current-context
kubectl -n catalog-prod get pods -o wide --show-labels
kubectl -n catalog-prod get networkpolicy
kubectl -n catalog-prod get networkpolicy -o yaml
kubectl -n payments-prod get pods -o wide --show-labels
kubectl get namespaces --show-labels
~~~

Đây là các lệnh **đọc Kubernetes API**; chúng không chứng minh CNI thực sự enforce policy. Kubernetes API output có thể chứa cấu hình/tên nội bộ, cần giới hạn phạm vi lưu và chia sẻ.

### 42.5. Đọc cloud firewall/ACL khi có quyền

~~~bash
# Ví dụ AWS CLI chỉ đọc. ID là placeholder, chỉ dùng
# trong tài khoản lab được cấp phép khi đã thay ID thực.
aws ec2 describe-network-acls \
  --network-acl-ids acl-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Khi phân tích, xem **NACL association, inbound/outbound, protocol, CIDR, rule number, rule action và port ranges**. Không chỉ tìm sự tồn tại của một ALLOW; phải xác định **rule nào khớp đầu tiên theo thứ tự** và response path.

### 42.6. Kiểm tra ứng dụng sau khi owner cung cấp endpoint staging

~~~bash
# Chỉ dùng khi tên miền đã được thay bằng endpoint staging có phép.
# Không dùng -k/--insecure và không gửi dữ liệu nhạy cảm.
curl --connect-timeout 3 --max-time 8 \
  --silent --show-error --output /dev/null \
  --write-out 'http=%{http_code} total=%{time_total}\n' \
  https://api.partner.example.test/health
~~~

**HTTP response PASS không chứng minh egress allowlist/DLP đúng**: kết nối có thể qua đường không được kiểm soát. Cần đối chiếu **route, proxy, firewall decision logs và identity của đích**. Với negative tests, dùng **approved synthetic destination** thuộc lab; không thử ngẫu nhiên IP public.

### 42.7. Dùng dữ liệu giả để kiểm thử DLP/tenant controls

Thay vì upload dữ liệu khách hàng, xây **file giả** có nhãn classification test hoặc nội dung marker do owner DLP phê duyệt. Kết quả kỳ vọng:

| Đích | Dữ liệu giả | Kỳ vọng |
|---|---|---|
| Corporate tenant được duyệt | Bộ dữ liệu thử không nhạy cảm | ALLOW |
| Personal tenant không được duyệt | Marker DLP thử nghiệm | DENY theo tenant/data policy |
| Unapproved domain | Không cần payload, chỉ kết nối test | DENY ở egress boundary |
| Đích hợp lệ nhưng API action trái quyền | Request không thay đổi dữ liệu | App authorization DENY |

**Không tự đặt dữ liệu y tế, tài chính hoặc thông tin cá nhân thật trong bài thực hành**. Ghi nhận policy ID và kết quả, không sao chép nội dung giả có thể bị nhầm với secret thật vào log chia sẻ.

### 42.8. Phiếu nghiệm thu

~~~text
Lab ID:                  EGRESS-PORT-PROTO-001
Timestamp/timezone:      [time]
Environment:             [approved lab/staging]
Source owner/workload:   [service identity]
Source namespace/subnet: [namespace + CIDR]
Destination owner:       [service/tenant]
Destination IP/FQDN:     [approved]
Protocol:                [TCP/UDP/ICMPv6...]
Destination port/type:   [port or ICMP type/code]
Source ephemeral port:   [if applicable]
Policy boundary:         [host/SG/NACL/CNI/proxy]
NAT/proxy path:          [pre/post translation]
IPv4/IPv6:              [coverage]
Expected network result: [ALLOW/DENY]
Observed network result: [source + evidence]
TLS/service identity:    [verified/not tested]
DLP/data decision:       [approved/denied/not observed]
Business/API result:     [success/denied/not tested]
Negative tests:          [approved test identifiers]
Verdict:                 [PASS/FAIL/INCONCLUSIVE]
Change/owner:            [ticket and responder]
~~~

**Một flow DENY vì đích không tồn tại hoặc DNS sai chưa chứng minh firewall đã chặn đúng.** Hãy xác định **bằng chứng policy decision tại enforcement point** và đồng thời chứng minh source có thể dùng đường được phép.

## 43. Ma trận kiểm thử egress port/protocol và DLP

| Test ID | Tình huống | Kết quả kỳ vọng |
|---|---|---|
| **EG-01** | Source app gọi approved API TCP/443 | ALLOW đúng destination và TLS identity |
| **EG-02** | App gọi unapproved IP TCP/443 | DENY dù port 443 được dùng |
| **EG-03** | App gọi approved IP trên TCP/22 ngoài hợp đồng | DENY theo protocol/port |
| **EG-04** | App gọi approved endpoint bằng UDP/443 không được phép | DENY riêng UDP/443 |
| **EG-05** | App cần QUIC/HTTP3 được duyệt | ALLOW có kiểm soát và telemetry thực |
| **EG-06** | QUIC bị chặn nhưng client fallback TCP | Kết quả ứng dụng và policy vẫn đúng |
| **EG-07** | App dùng DNS UDP/53 tới resolver được duyệt | Query/response ALLOW |
| **EG-08** | DNS TCP/53 khi cần | ALLOW đúng resolver |
| **EG-09** | DNS trực tiếp tới resolver không phê duyệt | DENY theo policy |
| **EG-10** | DoT TCP/853 ngoài hợp đồng | DENY nếu không được phê duyệt |
| **EG-11** | DoQ UDP/853 ngoài hợp đồng | DENY nếu không được phê duyệt |
| **EG-12** | DoH qua HTTPS ngoài hợp đồng | Không bypass resolver policy qua 443 |
| **EG-13** | SaaS corporate tenant qua HTTPS | ALLOW theo tenant/data policy |
| **EG-14** | SaaS personal tenant qua cùng hostname | DENY share/upload trái quyền |
| **EG-15** | SMTP TCP/25 đến Internet | DENY nếu workload không phải mail relay |
| **EG-16** | SMTP/HTTPS email API được phê duyệt | ALLOW có authentication và recipient controls |
| **EG-17** | SSH/SFTP tới host đối tác có phép | ALLOW đúng destination/host identity |
| **EG-18** | SSH tới IP bất kỳ ngoài danh mục | DENY |
| **EG-19** | App kết nối DB được duyệt TCP/5432 | ALLOW và DB auth riêng |
| **EG-20** | Sandbox gọi DB production | DENY bằng policy workload/network |
| **EG-21** | Telemetry collector TCP/4317 | Logging hoạt động không mất coverage |
| **EG-22** | NTP UDP/123 nếu workload thật cần | ALLOW đúng time source |
| **EG-23** | App không cần NTP trực tiếp | Không mở outbound UDP/123 toàn Internet |
| **EG-24** | PMTUD trên VPN/IPv4 | ICMP feedback cần thiết được xử lý phù hợp |
| **EG-25** | PMTUD/ICMPv6 trên dual-stack | Không làm blackhole gói lớn |
| **EG-26** | Request TCP/443 và response ephemeral | Đường stateful/stateless được cấu hình đúng |
| **EG-27** | AWS NACL thiếu inbound ephemeral return | Phát hiện đúng root cause |
| **EG-28** | AWS SG stateful với response flow | Không mở inbound any chỉ vì response port |
| **EG-29** | NAT biến đổi source IP/port | Logs và rule khớp đúng điểm đánh giá |
| **EG-30** | App cố bypass authenticated egress gateway | Direct path DENY |
| **EG-31** | Gateway nhận client không được phép dùng proxy | DENY theo workload/user identity |
| **EG-32** | Gateway target là cloud metadata/management sai quyền | DENY theo destination boundary |
| **EG-33** | DNS/FQDN/CDN IP thay đổi có chủ đích | Policy cập nhật, không cấp any Internet |
| **EG-34** | Shared CDN IP chứa nhiều tenant/hosts | Không tự coi IP allow là tenant allow |
| **EG-35** | HTTP redirect tới hostname ngoài danh sách | Proxy/DLP không âm thầm mở rộng quyền |
| **EG-36** | TLS certificate sai hostname ở approved API | Client/proxy từ chối identity mismatch |
| **EG-37** | TLS inspection không hỗ trợ pinned/mTLS app | Có thiết kế ngoại lệ/đường bảo vệ hợp lệ |
| **EG-38** | App source có NetworkPolicy egress deny mặc định | Chỉ rules được duyệt hoạt động |
| **EG-39** | NetworkPolicy hẹp cộng policy allow-all | Phát hiện additive union và quyền thừa |
| **EG-40** | Source/destination Pod selectors AND bị tách thành OR | Lint/test phát hiện mở rộng tập nguồn/đích |
| **EG-41** | NodeLocal DNSCache khác CoreDNS Pod | Policy phản ánh đúng DNS path |
| **EG-42** | CNI không thực thi NetworkPolicy | Không kết luận PASS chỉ vì YAML tồn tại |
| **EG-43** | hostNetwork/container privileged có đường khác | Audit/host controls chặn bypass |
| **EG-44** | Traffic IPv4 ngoài quyền | DENY |
| **EG-45** | Traffic IPv6 ngoài quyền | DENY ở v6 boundary |
| **EG-46** | Private endpoint tới sai cloud account/bucket | Cloud IAM/tenant policy DENY |
| **EG-47** | VPN/peering cho traffic sai trust zone | DENY theo segmented egress |
| **EG-48** | Flow logs báo ACCEPT nhưng DLP DENY upload | Dashboard phân loại đúng các lớp |
| **EG-49** | No flow logs từ một đường cần giám sát | Coverage UNKNOWN, không kết luận an toàn |
| **EG-50** | Thay đổi policy có người phê duyệt | IaC diff, owner, TTL, canary, rollback đầy đủ |
| **EG-51** | Emergency allow hết hạn | Được thu hồi và retest có bằng chứng |
| **EG-52** | Sau rollout app vẫn có SLO đạt | ALLOW dependencies + DENY không mong muốn |
| **EG-53** | DLP phát hiện export bằng dữ liệu giả | Quyết định theo data class và tenant đúng |
| **EG-54** | TLS payload không được inspect | Không tuyên bố nội dung đã được kiểm tra |
| **EG-55** | Long-lived connection sau quyền bị thu hồi | Connection/session expiry theo chính sách |
| **EG-56** | Hệ thống log chứa token/payload nhạy cảm | Được redact và hạn quyền truy cập |

### Diễn giải kết quả

- **PASS:** chính sách được quan sát đúng trên **nguồn, đích, protocol/port, network path và data/action**, có bằng chứng cả ALLOW và DENY khi phù hợp.
- **FAIL:** luồng hợp lệ bị chặn ngoài ý định, dữ liệu trái quyền qua kênh được phép hoặc có direct egress bypass.
- **INCONCLUSIVE:** chưa biết route/NAT/proxy, không có CNI/firewall telemetry, không xác định tenant/identity hoặc probe sai đích.
- **NOT_APPLICABLE:** tính năng không có trong kiến trúc (ví dụ chỉ IPv4 và không dùng QUIC) sau khi xác minh.

**Không đồng nhất HTTP status 200 với network policy PASS hoặc “DLP an toàn”.** Khi ứng dụng cho phép hoạt động, cần biết **nó đã dùng đúng egress path và destination identity**.

## 44. Những hiểu nhầm và sai sót thường gặp

| Hiểu nhầm | Vì sao sai hoặc thiếu | Cách tiếp cận phù hợp |
|---|---|---|
| “Outbound là mọi traffic đến Internet” | Traffic vượt subnet/VPC/namespace cũng là egress theo boundary | Xác định ranh giới trước |
| “Chặn mọi port trừ 443 là hết data loss” | HTTPS đến đích/tenant sai vẫn có thể gửi dữ liệu | Destination/identity/data-aware DLP |
| “TCP/443 luôn là HTTPS hợp lệ” | Port không chứng minh protocol hay danh tính | TLS/app inspection khi có hỗ trợ |
| “UDP/443 được phép vì TCP/443 đã được phép” | Hai transport khác nhau | Rule riêng TCP và UDP |
| “Chặn UDP/443 nghĩa HTTPS bị chặn” | TCP HTTPS vẫn có thể hoạt động | Kiểm tra HTTP/2 và HTTP/3 paths |
| “Chặn UDP/53 là hết DNS bên ngoài” | TCP DNS, DoH/DoT/DoQ và proxy có đường khác | Resolver governance, egress identity |
| “DNS luôn chỉ cần UDP/53” | DNS có TCP/53 và những resolver modes khác | Inventory DNS path thực |
| “DoT và DoH là cùng cổng” | DoT thường TCP/853, DoH thường HTTPS/443 | Phân biệt transport/app layer |
| “Mọi UDP/443 đều là QUIC” | Port chỉ là quy ước, không xác nhận payload | Protocol-aware telemetry |
| “NTP cho mọi Pod là bắt buộc” | Nhiều workload dùng đồng hồ node/host | Chỉ mở khi có nhu cầu thật |
| “ICMP không liên quan ứng dụng HTTPS” | PMTUD bị chặn có thể làm upload timeout | Kiểm tra ICMP/ICMPv6 cần thiết |
| “ICMPv6 có thể chặn toàn bộ cho an toàn” | IPv6 cần ICMPv6 cho hoạt động nền tảng | Lọc theo type/code, scope |
| “Egress chỉ cần destination port, không cần return path” | Stateless ACL yêu cầu xem response ephemeral | Vẽ 5-tuple hai chiều |
| “Response TCP dùng destination 443” | Client response destination là ephemeral port | Đọc request/response đúng |
| “Ephemeral range luôn cố định trên mọi OS” | OS/NAT/application khác nhau | Xác minh tại nguồn/điểm áp policy |
| “AWS SG và AWS NACL đều stateful” | NACL stateless, SG stateful | Thiết kế rule theo loại boundary |
| “Azure NSG là AWS NACL” | State/priority/semantics khác nhau | Theo đặc tả provider |
| “NAT gateway tự là DLP firewall” | NAT dịch địa chỉ, không hiểu file/tenant | Thêm firewall/proxy/DLP |
| “Private IP nghĩa không ra Internet được” | NAT/route/connector có thể cung cấp outbound | Xem route/gateway thực |
| “Không publish Docker port thì không egress” | Docker publish chủ yếu liên quan inbound host mapping | Kiểm soát outbound độc lập |
| “Docker EXPOSE là egress allowlist” | EXPOSE chỉ là image metadata | Host/CNI/cloud policy thực |
| “Namespace Kubernetes tự chặn egress” | Namespace không phải firewall | NetworkPolicy nếu CNI enforce |
| “Một NetworkPolicy hẹp sẽ thu hẹp policy allow-all” | NetworkPolicy có additive union | Sửa policy cấp quyền thừa |
| “Có NetworkPolicy YAML nghĩa chắc chắn packet bị chặn” | CNI/host paths có thể không thực thi | Runtime/CNI validation |
| “Dùng ipBlock cho ClusterIP luôn đúng” | NAT/service translation có khác biệt | Xem CNI dataplane |
| “Một rule IPv4 deny cũng bao phủ IPv6” | Address families, routes và ACL có thể tách | Test dual-stack |
| “FQDN allowlist bảo đảm đúng SaaS tenant” | Domain/CDN shared-hosting có thể phục vụ nhiều tenant | Tenant-aware controls |
| “Allow DNS name thì IP luôn cố định” | DNS TTL/CDN/IP rotation | Theo dõi resolution/policy refresh |
| “SNI là danh tính user và đích tuyệt đối” | SNI không xác thực user/tenant và có thể bị che | TLS identity + app policy |
| “Proxy CONNECT luôn xem được HTTP body” | CONNECT có thể là tunnel TLS opaque | Biết TLS termination |
| “Có egress gateway nghĩa không có direct bypass” | Route khác có thể tránh gateway | Firewall/CNI egress enforcement |
| “Cloud object storage private endpoint luôn cùng account” | Endpoint/network không đồng nghĩa tenant ownership | IAM/bucket/account policy |
| “TLS encryption chứng minh việc chuyển dữ liệu được phép” | TLS không phân quyền nội dung | DLP/classification/recipient policy |
| “TLS inspection là việc luôn phải làm” | Privacy/legal, pinning, mTLS, availability constraints | Risk-based, authorized inspection |
| “Chỉ cần log payload thật để chứng minh DLP” | Có thể tạo bản sao dữ liệu nhạy cảm | Redacted metadata/test markers |
| “Flow ACCEPT nghĩa dữ liệu đã tới app” | ACCEPT ở một điểm không bảo đảm kết quả E2E | App/proxy logs và trace |
| “Flow REJECT chắc chắn là do NACL” | Có thể SG, host, CNI hoặc thành phần khác | Correlation rule/packet path |
| “Không thấy flow log nghĩa không có egress” | Logging có giới hạn coverage/sampling | Kiểm tra collector/path |
| “DNS timeout nghĩa app server hỏng” | Egress resolver policy có thể chặn | Phân lớp DNS/TCP/TLS |
| “Mở all egress khi lỗi để đảm bảo SLA” | Gây mở rộng quyền có thể tồn tại lâu | Rule hẹp, TTL, rollback |
| “Policy as Code PASS là runtime đã chặn đúng” | Còn drift, NAT, CNI, policy overlap | Positive/negative runtime tests |
| “Không thấy alert nghĩa không có exfiltration” | Data có thể đi qua kênh được phép, TLS che payload | Data/app/endpoint telemetry |
| “Một test từ một node đủ đại diện cả cluster” | AZ, subnet, node và HA path khác nhau | Test đường active/dự phòng |
| “Chặn một đích là đã xử lý compromise” | Credential và kênh khác có thể còn | Incident response toàn diện |
| “Egress deny và DLP deny là cùng một kết quả” | Network action khác content/data action | Ghi đúng enforcement layer |

## 45. Câu hỏi tự kiểm tra

1. **Egress** được định nghĩa theo những ranh giới nào? Vì sao cùng một packet có thể là egress ở node nhưng ingress ở VPC gateway?
2. Egress port/protocol filtering có vai trò gì trong DLP và giới hạn nào?
3. Vì sao chặn tất cả trừ TCP/443 vẫn có thể để dữ liệu nhạy cảm rời tổ chức?
4. Phân biệt **source port** và **destination port** ở request/response TCP tới HTTPS API.
5. Vì sao **stateful SG** khác **stateless AWS NACL** khi xử lý gói phản hồi?
6. Có thể giả định dải ephemeral port luôn là 49152–65535 không? Cần kiểm chứng gì?
7. Vì sao phải xác định cả **source identity, destination identity, protocol, port và business owner**?
8. TCP/443 và UDP/443 có phải cùng giao thức/port rule không?
9. HTTP/3/QUIC thường sử dụng transport nào? Vì sao cần đánh giá proxy/DLP coverage riêng?
10. DNS UDP/53 và TCP/53 có ý nghĩa gì? Khi nào TCP DNS có thể cần?
11. DoH, DoT và DoQ khác nhau ra sao về cổng/transport phổ biến?
12. Vì sao chặn external UDP/53 không bảo đảm không có direct DoH?
13. DNS resolver policy ở Kubernetes khác gì khi cluster có NodeLocal DNSCache?
14. Vì sao ICMPv6 và PMTUD có thể ảnh hưởng HTTPS upload dù TCP/443 được phép?
15. Trong firewall, ICMP/ICMPv6 được lọc bằng thuộc tính gì thay TCP/UDP port?
16. Một ứng dụng dùng FTP hoặc dynamic RPC ports cần thiết kế rule thế nào để không mở toàn bộ high ports?
17. SFTP khác FTP về mô hình giao thức/kết nối và các ràng buộc security ra sao?
18. Vì sao chặn SMTP TCP/25 không chắc chặn gửi email trái phép qua HTTPS API?
19. NAT Gateway có vai trò gì và nó không tự thực hiện loại DLP nào?
20. Flow logs trước/sau SNAT có thể khác nhau những trường nào?
21. Nếu workload chia sẻ một public NAT IP, làm sao gắn egress traffic với source workload?
22. Dockerfile EXPOSE có giới hạn outbound traffic không? Vì sao?
23. Kubernetes NetworkPolicy dùng **egress** và **podSelector/namespaceSelector** như thế nào?
24. Vì sao hai selectors đặt trong một phần tử khác với đặt trong hai phần tử danh sách?
25. Nếu một Pod có policy egress hẹp và policy allow-all khác, effective quyền thế nào?
26. Vì sao NetworkPolicy có trong Kubernetes API chưa chứng minh CNI đang enforce?
27. Một Service FQDN được cho phép có thể chuyển đổi nhiều IP qua CDN như thế nào?
28. IP allowlist trên shared CDN có tự phân biệt tenant doanh nghiệp không?
29. Một proxy HTTP CONNECT có đọc được HTTPS payload trong mọi trường hợp không?
30. TLS inspection cần đáp ứng những yêu cầu nào về privacy, certificate trust và quyền hạn?
31. Vì sao private endpoint tới object storage vẫn cần cloud IAM/bucket/tenant policy?
32. Nếu cùng dữ liệu được gửi sang VPC khác qua peering, có thể là data egress không?
33. IPv6 có thể tạo policy gap thế nào khi tổ chức chỉ rà IPv4?
34. Với TLS/mTLS, khác biệt giữa **xác thực server** và **quyền gửi một loại dữ liệu** là gì?
35. Trường dữ liệu nào nên có trong policy-as-code để quản lý các quyền outbound?
36. Một temporary allow rule cần owner, TTL, change record và rollback ra sao?
37. Khi app timeout, cách phân biệt lỗi DNS, TCP, NACL, proxy, TLS, DLP và API response là gì?
38. Flow logs ACCEPT/REJECT khác proxy decision/DLP decision thế nào?
39. Tại sao không nên lưu payload bí mật vào logs chỉ để điều tra một cảnh báo DLP?
40. Nêu các dấu hiệu giám sát có thể cho thấy egress lạ, và vì sao không nên coi một dấu hiệu là bằng chứng tấn công.
41. Trong case study 1, tại sao TCP/443 allowlist không ngăn upload sai SaaS tenant?
42. Trong case study 2, vì sao sửa lỗi DNS bằng mở toàn bộ Internet là lựa chọn kém?
43. Trong case study 3, gói response bị chặn ở đâu và cách khắc phục phải dựa trên thuộc tính gì?
44. Trong case study 4, làm sao xác định QUIC thật sự bypass proxy thay vì chỉ là thống kê TCP giảm?
45. Trong case study 5, vì sao thêm default-deny khác không chặn policy allow-all?
46. Trong case study 6, những bằng chứng nào phải có để chứng minh IPv6 path được kiểm soát tương đương?
47. Hãy lập ma trận **catalog → payment ALLOW**, **catalog → DNS ALLOW**, **catalog → arbitrary HTTPS DENY**.
48. Hãy bổ sung vào ma trận trường **source identity, destination owner, data class và negative test**.
49. Khi triển khai egress controls, tại sao phải kiểm tra **SLO ứng dụng và bảo mật** đồng thời?
50. Cần những bằng chứng nào để kết luận một chính sách egress có hiệu lực **trên tất cả đường active/HA/IPv6/proxy**?

## 46. Ghi nhớ trọng tâm

**Kiểm soát port và protocol đi ra** là một lớp **egress filtering** nhằm hạn chế kết nối ngoài nhu cầu từ workload, host, Pod, subnet hoặc mạng doanh nghiệp. Thiết kế cần mô tả **nguồn, đích, hướng, transport protocol, destination port, route/NAT/proxy, identity và mục đích nghiệp vụ**. **TCP và UDP** có port riêng; **ICMP/ICMPv6** dùng type/code và phục vụ các chức năng quan trọng như PMTUD. **Stateful firewall** có cơ chế theo dõi kết nối; **stateless ACL** cần xét chiều phản hồi và ephemeral ports. Không sao chép semantics của AWS NACL sang mọi nền tảng.

**Port control không phải DLP đầy đủ.** Một flow TCP/443 tới đích hợp lệ vẫn có thể gửi dữ liệu ngoài quyền, đặc biệt khi **SaaS có nhiều tenant, object storage cross-account hoặc API đã được cho phép nhưng bị lạm dụng**. Kết hợp **destination allowlists, xác thực service, FQDN/HTTP-aware egress proxy, identity/tenant-aware policy, data classification, application/endpoint DLP và audit**. Khi có TLS inspection, phải kiểm soát **quyền riêng tư, tính hợp pháp, certificate trust, phạm vi giao thức và dữ liệu giải mã**.

**Đừng quên DNS UDP/TCP/53, DoH/DoT/DoQ, HTTP/3/QUIC UDP/443, SMTP/SSH, dynamic ports, IPv6, ICMPv6/PMTUD và đường private/VPN/peering**. Docker EXPOSE không giới hạn outbound; Kubernetes namespace không tự cô lập egress; NetworkPolicy cần **CNI enforcement** và có **additive allow semantics**. NAT gateway dịch địa chỉ nhưng không tự xác minh tenant hay nội dung. Egress gateway chỉ đáng tin khi **không có direct route bypass** ngoài thiết kế.

Vận hành hiệu quả dựa vào **flow inventory, least-privilege policy-as-code, rule owner, expiry của ngoại lệ, read-only verification, observability, runbook và rollout/rollback theo SLO**. Nghiệm thu phải đồng thời chứng minh **luồng hợp pháp hoạt động đúng** và **luồng ngoài quyền bị từ chối tại đúng enforcement point**, kiểm tra cả active/HA, IPv4/IPv6 và protocol drift. Không tuyên bố “đã chặn thất thoát dữ liệu” chỉ vì một port đóng hoặc flow log không ghi nhận bất thường; phải kết nối **bằng chứng mạng, danh tính, ứng dụng và dữ liệu** theo chính sách đã phê duyệt.
