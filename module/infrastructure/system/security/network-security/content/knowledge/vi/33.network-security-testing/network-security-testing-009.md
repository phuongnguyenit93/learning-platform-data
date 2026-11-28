# Kiểm tra default deny và ngoại lệ

## 1. Vì sao cần kiểm chứng nguyên tắc default deny?

Trong mạng doanh nghiệp, một chính sách bảo mật **default deny** (mặc định từ chối) chỉ cho phép các luồng đã được phê duyệt và chặn mọi luồng còn lại trong **phạm vi thực thi chính sách**. Nguyên tắc này hỗ trợ phân đoạn mạng, giới hạn truy cập từ Internet, giảm khả năng di chuyển ngang và giảm lưu lượng ra ngoài không cần thiết.

Điểm quan trọng là **cấu hình có quy tắc deny không đồng nghĩa việc chặn thực sự có hiệu lực**. Một đường định tuyến khác, NAT, bộ lọc trên thiết bị khác, một ngoại lệ quá rộng hoặc IPv6 chưa kiểm soát có thể khiến một luồng vẫn đi qua. Ngược lại, một kết nối hợp lệ bị lỗi chưa chắc vì chính sách deny: đích có thể tắt dịch vụ, DNS sai hoặc đường truyền mất kết nối.

Bài học thuộc chương **Kiểm thử và xác minh bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**. Việc kiểm tra áp dụng cho firewall, router ACL, mạng phân đoạn, VPN/ZTNA, network policy trong môi trường container, security group/NACL trong đám mây và các điểm thực thi kiểm soát kết nối khác. Bài học liên hệ với xác thực, giám sát IDS/IPS, bảo vệ DNS, mạng không dây và các dịch vụ nền tảng nhưng tập trung vào **chính sách luồng và ngoại lệ**.

Sau bài học, người học có thể:

- Giải thích ranh giới áp dụng của default deny và phân biệt **deny mặc định**, **deny tường minh** và **allow có điều kiện**.
- Thiết kế **ma trận kiểm thử dương và âm** theo nguồn, đích, giao thức, cổng, danh tính và vùng mạng.
- Kiểm tra nhiều điểm thực thi chính sách, cả IPv4/IPv6, chiều vào/ra và lưu lượng east–west.
- Xác minh ngoại lệ có lý do nghiệp vụ, phạm vi tối thiểu, người phê duyệt, thời hạn và cách thu hồi.
- Thu thập chứng cứ kết nối, log, rule hit và packet path để phân biệt deny thực sự với lỗi kỹ thuật.
- Đánh giá rủi ro của quy tắc quá rộng, shadowed rule, phiên cũ còn tồn tại và sự khác biệt giữa firewall stateful/stateless.

> **Nguyên tắc kiểm thử:** Phải chứng minh đồng thời **luồng cần thiết được cho phép** và **luồng không được phê duyệt bị ngăn chặn**. Chỉ kiểm tra rằng ứng dụng hoạt động bình thường là chưa đủ.

## 2. Hiểu chính xác default deny và ngoại lệ

### 2.1. Default deny là gì?

Tại một điểm kiểm soát được xác định, ta ký hiệu tập luồng mạng có thể xảy ra là \(T\), tập luồng được phê duyệt là \(A\). Chính sách mong muốn:

\[
\operatorname{Decision}(t) =
\begin{cases}
\operatorname{Allow}, & t \in A \text{ và thỏa điều kiện};\\
\operatorname{Deny}, & t \notin A.
\end{cases}
\]

Định nghĩa trên mô tả **ý định bảo mật**, chưa phải cách mọi firewall hoặc cloud service thực thi. Quy tắc có thể nằm ở ingress, egress, cả hai chiều, hoặc chỉ trong một nhóm endpoint. Cần xác định **đúng ranh giới bảo vệ**, không mặc định toàn bộ mạng được bảo vệ chỉ vì một firewall có quy tắc cuối cùng là deny.

Ví dụ: VLAN người dùng chỉ được truy cập ứng dụng HTTPS qua reverse proxy. Kết nối người dùng → database trực tiếp phải bị từ chối. Ngược lại, application server → database trên cổng đã phê duyệt có thể là một **ngoại lệ hợp lệ** so với chính sách cô lập mặc định giữa hai vùng.

### 2.2. Ba loại quyết định phải phân biệt

| Quyết định | Ý nghĩa | Điều cần xác minh |
| --- | --- | --- |
| **Allow tường minh** | Một rule xác định cho phép luồng theo điều kiện (source, destination, service, identity, time...) | Điều kiện đủ hẹp, đúng thứ tự ưu tiên, đúng điểm áp dụng và có chủ sở hữu |
| **Deny tường minh** | Rule chủ động chặn một luồng hoặc nhóm luồng | Không che luồng hợp lệ, có log/rule hit theo nhu cầu điều tra |
| **Deny ngầm định** | Gói không khớp allow nên bị chặn theo cơ chế mặc định | Thực sự tồn tại ở đúng điểm thực thi và áp dụng cho giao thức/chiều đang thử |

Không phải hệ thống nào cũng có một rule `deny any any` có thể nhìn thấy. Một số nền tảng đặt implicit deny cuối rulebase, một số thực thi chính sách dựa trên tập allow, và một số có **mặc định khác nhau giữa ingress và egress**. Vì vậy phải xác định hành vi thực tế theo sản phẩm và cấu hình của tổ chức.

**Ngoại lệ (exception)** là một quyền truy cập được cho phép khác với baseline chặn chung, có **nhu cầu được chứng minh**. Ngoại lệ không nhất thiết vi phạm chính sách: ngoại lệ tốt là một rule được đánh giá, phê duyệt và quản lý vòng đời. Ngoại lệ xấu là một lỗ mở quá rộng, không rõ chủ sở hữu, không có ngày đánh giá lại hoặc tồn tại sau khi nhu cầu đã kết thúc.

### 2.3. Phạm vi chính sách và ma trận kết nối

Đối với một luồng được kiểm soát, nên mô tả đủ:

\[
t = (src,\ dst,\ protocol,\ port,\ direction,\ zone,\ identity,\ time,\ context)
\]

Trong đó `identity` và `context` (user, device posture, service identity, URL/application) chỉ thực thi được nếu thiết bị hoặc lớp kiểm soát hỗ trợ. Một firewall L3/L4 không thể tự hiểu danh tính người dùng hoặc đường dẫn HTTP chỉ vì dữ liệu này xuất hiện trong tài liệu chính sách.

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Source** | Host, CIDR, VLAN/VRF, security group hay danh tính nào được kết nối? |
| **Destination** | Đúng IP/FQDN/service hay một subnet rộng? Có VIP/load balancer/NAT không? |
| **Protocol/port** | TCP/443, UDP/53, TCP/5432 hay cổng/dịch vụ khác? Cần chiều trả lời ra sao? |
| **Direction** | Ingress, egress, east–west hay đường quản trị? Có thay đổi sau NAT không? |
| **Identity và posture** | VPN/ZTNA có giới hạn user, role, nhóm thiết bị và trạng thái máy không? |
| **Time** | Quyền cố định, theo cửa sổ bảo trì, hay ngoại lệ có hạn? |
| **Owner/evidence** | Ai phê duyệt; làm sao biết rule đang được sử dụng và vẫn cần thiết? |

## 3. Các điểm thực thi phải kiểm tra

Một luồng thường đi qua **nhiều lớp**, không chỉ một firewall:

~~~mermaid
flowchart LR
    U["Máy người dùng"] --> S["Switch / VLAN"]
    S --> R["Router / ACL"]
    R --> F["Firewall vùng"]
    F --> L["Load balancer / WAF"]
    L --> A["Application"]
    A --> H["Host firewall"]
    H --> D["Database"]
    F --> G["NAT / Internet gateway"]
    G --> I["Internet"]
    V["VPN / ZTNA"] --> F
~~~

Sơ đồ chỉ là ví dụ. Đường thực tế có thể khác: lưu lượng giữa các host cùng VLAN có thể **không đi qua firewall phân đoạn**, còn traffic container hoặc cloud có thể chịu thêm network policy và security group. Bởi vậy việc kiểm chứng phải trả lời: **gói thử đi qua những điểm nào, và chính sách nào thực sự quyết định cho phép/chặn?**

| Điểm kiểm soát | Khả năng | Hạn chế thường gặp |
| --- | --- | --- |
| Router ACL | Lọc địa chỉ, giao thức/cổng theo interface và chiều | Không mặc nhiên theo dõi trạng thái phiên; có thể bị vượt qua khi đường đi thay đổi |
| Firewall stateful | Theo dõi trạng thái phiên, kiểm soát theo zone và thường có log/rule hit | Phiên đã lập trước khi sửa rule có thể còn hiệu lực tùy nền tảng/chính sách |
| Host firewall | Giới hạn kết nối ngay trên máy | Chính sách dễ lệch nếu quản lý endpoint không nhất quán |
| Cloud security group | Kiểm soát kết nối ở tài nguyên gắn group, nhiều nền tảng có trạng thái phiên | Default ingress/egress và semantics khác nhau theo nhà cung cấp |
| Cloud network ACL | Bộ lọc ở subnet hoặc lớp hạ tầng | Có thể stateless, cần xét riêng chiều trả lời và ephemeral ports |
| Kubernetes NetworkPolicy | Hạn chế traffic pod theo selector/namespace khi CNI hỗ trợ | Pod không bị cô lập nếu không có policy chọn vào; semantics ingress/egress cần kiểm tra cụ thể |
| VPN/ZTNA policy | Giới hạn ứng dụng/danh tính/thiết bị được phép | Kết nối VPN thành công không đồng nghĩa chỉ có ứng dụng được phép là reachable |
| WAF/proxy | Kiểm soát HTTP(S) theo ứng dụng hoặc URL khi có giải mã/quan sát | Không thay thế lọc mọi giao thức, service-to-service hay traffic không đi qua proxy |

### 3.1. Những tình huống dễ tạo cảm giác an toàn giả

- Firewall biên mặc định chặn **ingress**, nhưng **egress** vẫn cho phép rộng.
- Policy áp dụng IPv4 nhưng quản trị host qua IPv6 không đi qua bộ lọc tương đương.
- Rule ở subnet đúng nhưng traffic nội bộ cùng segment đi qua switch L2, không qua firewall.
- NAT làm đổi source/destination; bộ lọc áp dụng địa chỉ trước hoặc sau NAT theo pipeline của thiết bị.
- Rule cuối có deny nhưng một allow rộng phía trước bắt khớp trước; hoặc rule deny bị shadowed.
- Một interface, zone hoặc cloud resource mới chưa được đưa vào chính sách mong muốn.
- Access qua VPN được xác thực nhưng quyền truy cập ngang vẫn cho phép cả mạng nội bộ.
- Workload container có policy ingress nhưng không có policy egress, hoặc selector không bao phủ pod cần kiểm soát.

## 4. Chuẩn bị kiểm thử: bản đồ luồng và nguồn chứng cứ

Kiểm tra default deny là **một bài kiểm thử có chủ đích**, cần phối hợp với chủ ứng dụng, đội vận hành mạng và an ninh. Trước khi chạy, ghi rõ danh sách IP/host, phạm vi được phép, thời gian thử, giới hạn tải, người theo dõi log và phương án dừng. Tránh quét toàn bộ Internet hoặc sản xuất khi không có nhu cầu.

Các đầu vào quan trọng:

1. **Sơ đồ và đường đi:** VLAN/VRF, subnet, gateway, firewall zones, route, NAT, VPN, cloud VPC/VNet, security group và host firewall.
2. **Rulebase hiện hành:** policy ID, thứ tự đánh giá, điều kiện match, action, object group, rule có thời hạn, implicit rules và phương pháp log.
3. **Ma trận kết nối mong muốn:** nguồn, đích, giao thức/cổng, lý do nghiệp vụ, owner và tình trạng phê duyệt.
4. **Baseline lưu lượng:** firewall logs, NetFlow/IPFIX, DNS logs, IDS/IPS, proxy log và telemetry ứng dụng ở khoảng thời gian tương đương.
5. **Nhóm máy thử:** ít nhất một nguồn **được phép**, một nguồn **không được phép**, một đích hợp lệ và một đích/port ngoài quyền.
6. **Bằng chứng và rollback:** mẫu ghi nhận kết quả, thời gian chuẩn, change ticket, cấu hình được lưu và cách dừng khi ảnh hưởng ngoài dự kiến.

Khi đọc rulebase, cần phân biệt cấu hình **dự kiến** với **cấu hình đang thực thi**, bao gồm rule chưa commit, config chưa đồng bộ HA, rule được push từ controller nhưng thiết bị chưa nhận, và các rule tạm còn tồn tại sau thay đổi.

### 4.1. Thiết lập baseline cho ngoại lệ

Mỗi ngoại lệ cần có ít nhất:

| Trường | Nội dung cần lưu |
| --- | --- |
| Exception ID / Change ID | Mã liên kết với yêu cầu và thay đổi |
| Lý do nghiệp vụ | Dịch vụ nào không thể hoạt động nếu không mở luồng? |
| Chủ sở hữu và phê duyệt | Owner dịch vụ, owner chính sách và người có thẩm quyền chấp thuận |
| Scope | Nguồn, đích, protocol/port, chiều, zone, danh tính/ứng dụng nếu được hỗ trợ |
| Nguy cơ và biện pháp bù trừ | Điểm phơi lộ, logging, segmentation, MFA, IDS/IPS, rate limit theo nhu cầu |
| Thời gian | Bắt đầu, hết hạn, kỳ đánh giá lại và điều kiện thu hồi |
| Kiểm chứng | Test dương/âm, rule hit, kết quả vận hành, bằng chứng và lần kiểm tra gần nhất |
| Rollback / loại bỏ | Cách thu hồi rule, kiểm soát phiên còn mở, người thực hiện |

Một rule `0.0.0.0/0 → 10.20.30.0/24 : any` gần như luôn quá rộng so với nhu cầu “một máy backup kết nối tới một API TCP/443”. Phải rà soát **tập nguồn/đích nhỏ nhất khả thi**, giao thức đúng và thời hạn phù hợp. Nếu dùng danh tính hoặc service identity, cần xem thực tế thiết bị có enforce hay chỉ dùng để gắn nhãn.

## 5. Xây dựng ma trận kiểm thử dương và âm

**Kiểm thử dương (positive test)** chứng minh luồng được phép hoạt động. **Kiểm thử âm (negative test)** chứng minh một biến thể không được phê duyệt **không** đi qua. Cần thử cùng một kết nối với các thuộc tính khác nhau để biết rule có đủ hẹp.

Giả sử chính sách:

- VLAN người dùng `10.10.10.0/24` được gọi API `10.20.20.10` qua TCP/443.
- Chỉ host ứng dụng `10.20.20.10` được gọi database `10.30.30.10` qua TCP/5432.
- Collector `10.40.40.20` được phép truy vấn SNMPv3 tại IP quản trị `10.50.50.10` qua UDP/161.
- Người dùng không được kết nối trực tiếp tới database hoặc management plane.
- Một ngoại lệ backup có thời hạn: `10.60.60.25 → 10.30.30.10 : TCP/5432`, được phê duyệt theo change.

Ma trận kiểm thử gợi ý:

| ID | Nguồn | Đích | Luồng | Kỳ vọng | Ý nghĩa |
| --- | --- | --- | --- | --- | --- |
| P1 | 10.10.10.21 | 10.20.20.10 | TCP/443 | **Allow** | API phục vụ người dùng hoạt động |
| N1 | 10.10.10.21 | 10.30.30.10 | TCP/5432 | **Deny** | Không truy cập database trực tiếp |
| N2 | 10.10.10.21 | 10.20.20.10 | TCP/22 | **Deny** | Không mở SSH tới API cho người dùng |
| P2 | 10.20.20.10 | 10.30.30.10 | TCP/5432 | **Allow** | Backend truy cập database đúng quyền |
| N3 | 10.20.20.11 | 10.30.30.10 | TCP/5432 | **Deny** | Host kế bên không thừa hưởng quyền |
| P3 | 10.40.40.20 | 10.50.50.10 | UDP/161 | **Allow có điều kiện** | Chỉ SNMPv3 authPriv/read-only mới được truy vấn |
| N4 | 10.10.10.21 | 10.50.50.10 | UDP/161 | **Deny** | Ngăn máy người dùng tới SNMP agent |
| P4 | 10.60.60.25 | 10.30.30.10 | TCP/5432 | **Allow trong thời hạn ngoại lệ** | Kiểm chứng phạm vi đã được duyệt |
| N5 | 10.60.60.26 | 10.30.30.10 | TCP/5432 | **Deny** | Host khác không thừa hưởng ngoại lệ |
| N6 | 10.60.60.25 | 10.30.30.10 | TCP/22 | **Deny** | Ngoại lệ không mở thêm cổng quản trị |

**Để kết luận P3 thành công**, chỉ thấy UDP đi qua firewall là chưa đủ: SNMPv3 phải được xác thực và có quyền MIB phù hợp. **Để kết luận N4/N5 thành công**, cần bằng chứng rule/flow bị chặn; một ứng dụng trả lỗi hoặc timeout đơn lẻ không chứng minh chính sách được thực thi.

### 5.1. Mở rộng ma trận thành các biến thể cần thiết

| Biến thể | Trường hợp cần kiểm tra |
| --- | --- |
| **Nguồn** | IP cụ thể, host khác cùng subnet, VLAN khác, VPN user khác, service account không được phép |
| **Đích** | VIP và backend, hostname phụ, load balancer, IPv4 và IPv6, endpoint dự phòng/HA |
| **Giao thức/cổng** | TCP/UDP khác nhau dù cùng số port; port đúng và port sai |
| **Chiều truy cập** | Client khởi tạo kết nối và server khởi tạo kết nối ngược, nếu chính sách cho phép một chiều |
| **Phiên mới/cũ** | Kết nối mới sau sửa rule và phiên đã lập trước thay đổi |
| **Vùng mạng** | Nội bộ east–west, Internet ingress, egress, VPN, Wi-Fi guest và cloud interconnect |
| **Thời gian** | Khi ngoại lệ có hiệu lực, khi ngoại lệ hết hạn và sau khi loại bỏ |
| **Identity/device** | User, role, workload/namespace, tình trạng thiết bị nếu control plane hỗ trợ |

Không nhất thiết chạy mọi tổ hợp trên toàn hệ thống. Hãy chọn **tập kiểm thử đại diện dựa trên rủi ro**, bảo đảm mỗi ngoại lệ và mỗi ranh giới quan trọng có cả luồng hợp lệ lẫn luồng không được phép.

## 6. Thực hiện kiểm thử mà không làm gián đoạn dịch vụ

### 6.1. Preflight tại máy nguồn và đích

Đặt đồng hồ máy thử theo cùng nguồn thời gian hoặc lưu timestamp cùng timezone; xác nhận máy nguồn nằm đúng network namespace/VRF/VLAN và đúng danh tính cần test. Kiểm tra địa chỉ đích và dịch vụ đang **lắng nghe thật** để tránh nhầm kết quả âm.

Một phép thử TCP có ba kết quả điển hình:

- **Connected:** bắt tay TCP thành công; chưa chứng minh ứng dụng hoặc cơ chế xác thực hoạt động đúng.
- **Connection refused / TCP RST:** đích hoặc một thiết bị trung gian đã phản hồi từ chối; chưa đủ bằng chứng đó là default-deny firewall.
- **Timeout / unreachable:** có thể do drop, routing, ACL, NAT, host firewall, đích mất điện hoặc lỗi đường mạng; cần đối chiếu log và packet path.

Đối với UDP, không có TCP handshake. Không nên suy ra “UDP/161 đã được phép” chỉ vì lệnh gửi datagram thành công; cần nhận phản hồi SNMP hợp lệ hoặc sự kiện quan sát từ agent/collector theo ngữ nghĩa giao thức.

### 6.2. Lệnh thử kết nối có giới hạn

Các lệnh sau chỉ là ví dụ cho **host thử đã được phép** trong môi trường do tổ chức quản lý. Thay địa chỉ/tên và port theo ma trận test; giới hạn mỗi lần ở một nguồn/đích cụ thể. Dải IP ở trên thuộc mạng riêng minh họa.

Trên Linux:

~~~bash
# Xác nhận đường đi được máy nguồn lựa chọn.
ip route get 10.20.20.10

# Kiểm tra HTTPS được phép; tránh đưa token thật vào dòng lệnh.
curl --silent --show-error --output /dev/null \
  --connect-timeout 3 --max-time 8 \
  --write-out 'http=%{http_code} remote=%{remote_ip}\n' \
  https://app.example.test/health

# Thử đúng một cổng TCP theo ma trận đã phê duyệt.
# Tùy phiên bản netcat, cú pháp timeout có thể khác nhau.
nc -vz -w 3 10.30.30.10 5432

# Kiểm tra phiên TCP hiện có ở host nguồn.
ss -tn
~~~

Tên miền `app.example.test` chỉ là ví dụ; phải ánh xạ đến đúng endpoint kiểm thử. Lệnh `nc` giúp kiểm tra bắt tay TCP, nhưng không chứng minh firewall đã cho phép hay chặn nếu đích không lắng nghe. Nếu cần xác minh HTTPS, giữ kiểm tra chứng thư TLS và xác thực ứng dụng đúng cách; **không tắt kiểm tra TLS** để làm cho test dương “pass”.

Trên Windows PowerShell:

~~~powershell
# Thử đúng một đích/cổng TCP, lấy các trường liên quan.
Test-NetConnection -ComputerName 10.20.20.10 -Port 443
Test-NetConnection -ComputerName 10.30.30.10 -Port 5432

# Kiểm tra cấu hình IP và DNS tại máy thử.
Get-NetIPConfiguration
Resolve-DnsName app.example.test
~~~

Không dùng kết quả ping làm kết luận cho TCP/UDP: **ICMP có thể bị chặn theo chính sách** trong khi HTTPS được phép, hoặc ngược lại. Cũng không quét một subnet rộng chỉ để xác nhận một ngoại lệ cho một API. Nếu cần bắt gói, giới hạn interface, bộ lọc, thời lượng và bảo vệ dữ liệu có thể chứa thông tin nội bộ.

### 6.3. Tìm bằng chứng tại điểm thực thi

Đối chiếu **ba nguồn**: kết quả từ máy thử, trạng thái/log trên firewall/ACL/security group và trạng thái trên đích hoặc ứng dụng. Với sản phẩm có rule hit counter, cần xác minh thời gian, interface/zone, policy ID và action; nếu có NAT, xác định xem log dùng IP trước hay sau dịch.

Một mẫu chứng cứ:

~~~text
Test ID: N1
Change/Policy: CHG-EXAMPLE-101 / FW-USER-DB
Thời gian: 2026-11-28T10:00:00+07:00
Nguồn thực tế: 10.10.10.21; zone: user
Đích thực tế: 10.30.30.10; zone: database
Giao thức/cổng: TCP/5432
Kỳ vọng: DENY
Host result: timeout
Firewall log: action=deny; rule=USER_TO_DB_DENY
Route/NAT: đã xác minh đi qua policy được kiểm thử
Kết luận: PASS - bị chặn đúng tại điểm thực thi
Evidence IDs: LOG-001, HOST-001
~~~

Nếu không có log chặn do implicit deny không bật log, có thể dùng counters, flow logs, packet capture phù hợp hoặc test có giám sát trên ranh giới. Không giả định **“không thấy log” = “không có kết nối”**: log có thể bị lấy mẫu, tắt ở rule, lỗi collector hoặc lưu ở nơi khác.

## 7. Kiểm tra ngoại lệ: chính xác, tối thiểu và có vòng đời

Ngoại lệ cần được đánh giá hai chiều: **có cho luồng nghiệp vụ hợp lệ đi qua không**, và **có mở rộng quyền ra ngoài phạm vi hay không**.

### 7.1. Bộ kiểm tra cho mỗi ngoại lệ

1. **Tính cần thiết:** có bằng chứng chủ dịch vụ cần luồng này không? Có thể thay bằng kết nối từ gateway/proxy hoặc phương án ít đặc quyền hơn không?
2. **Phạm vi tối thiểu:** đúng source, destination, giao thức, cổng, chiều và định danh? Có rule dùng `any` hoặc CIDR rộng khó giải thích không?
3. **Ranh giới:** có kiểm soát IPv4/IPv6, NAT, subnet phụ, HA, VPN và đường dự phòng không?
4. **Biện pháp bảo vệ:** xác thực ứng dụng, mã hóa khi cần, IDS/IPS, rate limit hoặc điều kiện bảo mật bổ sung?
5. **Thời gian:** có ngày hết hạn, kỳ review và tác nhân chịu trách nhiệm xóa rule?
6. **Chứng cứ:** có rule ID, change ticket, log, kiểm thử dương/âm và snapshot trạng thái thực?
7. **Quay lui:** có thể thu hồi luồng và xử lý phiên đang mở mà không làm gián đoạn ngoài kế hoạch?

### 7.2. Ví dụ đặc tả ngoại lệ

Đây là **pseudocode YAML mô tả chính sách**, không phải cấu hình trực tiếp của firewall:

~~~yaml
exception_id: EXC-2026-041
change_id: CHG-2026-201
service: database-backup
business_reason: "Backup job cần truy cập database trong cửa sổ bảo trì"
owner_team: data-platform
approver_role: security-change-approver
status: approved
scope:
  source: "10.60.60.25/32"
  destination: "10.30.30.10/32"
  protocol: tcp
  destination_port: 5432
  direction: east-west
  zone_from: backup
  zone_to: database
effective_from: "2026-11-28T22:00:00+07:00"
expires_at: "2026-11-29T02:00:00+07:00"
controls:
  database_authentication: required
  tls_in_application: required
  log_connections: true
validation:
  positive_test: "backup host can connect and authenticate"
  negative_tests:
    - "other host in backup VLAN cannot connect"
    - "same backup host cannot connect to TCP/22"
    - "access denied after expiry"
  evidence_id: "TEST-2026-041"
revocation:
  owner_team: network-security
  method: "remove approved policy rule, verify new flows denied"
~~~

Một firewall L3/L4 có thể chỉ thực thi source, destination và port; `database_authentication` và TLS trong ví dụ là **kiểm soát tại dịch vụ** cần kiểm thử riêng. Các hệ thống khác nhau có khả năng kích hoạt/hết hạn rule tự động khác nhau; nếu không hỗ trợ expiry tự động thì phải có **ticket nhắc thu hồi**, người chịu trách nhiệm và kiểm tra lại sau thời hạn.

### 7.3. Phát hiện ngoại lệ quá rộng hoặc bị bỏ quên

Các dấu hiệu cần xem xét:

- Source hoặc destination là `any`, `0.0.0.0/0` hoặc `::/0` mà lý do không đủ chặt.
- Mở mọi port để khắc phục sự cố tạm thời nhưng chưa giới hạn lại.
- Quy tắc sao chép nhiều lần gây dư thừa, chồng lấn hoặc che khuất một deny phía sau.
- Ngoại lệ đã hết hạn nhưng vẫn có hit trong rulebase; hoặc lâu không có hit và chủ sở hữu không xác nhận còn cần.
- Khác biệt giữa policy trên firewall chính và dự phòng hoặc giữa cloud region/account.
- Quy tắc chỉ kiểm tra ingress, trong khi đường egress hoặc IPv6 không được kiểm soát.
- Danh tính source group thay đổi thành viên và vô tình đưa thêm thiết bị mới vào phạm vi allow.

**Không xóa ngay một rule chỉ vì “0 hits”**: bộ đếm có thể đã reset, log chưa đầy đủ hoặc traffic chỉ chạy theo lịch tháng/quý. Đối chiếu lịch nghiệp vụ, owner, thời gian giám sát và khả năng rollback rồi mới quyết định thu hồi.

## 8. Những điểm kỹ thuật làm sai kết quả kiểm thử

### 8.1. Firewall stateful, stateless và chiều trả lời

Firewall **stateful** thường cho phép gói phản hồi của phiên đã được chấp thuận theo bảng trạng thái mà không yêu cầu một allow độc lập cho mọi chiều trả lời. Rule thay đổi cũng không nhất thiết ngắt các phiên hiện có ngay. Vì vậy phải thử **phiên mới sau thay đổi** và đánh giá chính sách xử lý **existing sessions** theo nền tảng.

ACL/network ACL **stateless** thường đánh giá các gói vào và ra độc lập; nếu chính sách cho phép TCP client → server nhưng chặn chiều trả lời, phiên vẫn thất bại. Cần xét cổng nguồn tạm thời (*ephemeral ports*) và chiều thực tế. Không vì thế mở `any any` để sửa lỗi: phải thiết kế rule phản hồi chính xác theo kiến trúc hoặc dùng điểm kiểm soát stateful khi phù hợp.

### 8.2. NAT, proxy, route và bất đối xứng

Đích có thể thấy IP của reverse proxy hoặc NAT gateway chứ không thấy IP người dùng. Khi test, phải xác định:

- IP/port nào được policy so khớp **trước/sau NAT**.
- Lưu lượng có đi qua firewall dự kiến hay đi theo route khác.
- Đường trả lời có đi qua cùng điểm kiểm soát stateful hay không.
- DNS có phân giải VIP khác theo site, split-horizon hoặc load balancer.
- Host firewall hoặc chính sách ở cloud/pod có chặn tiếp sau khi firewall vùng đã allow.

Ví dụ, firewall vùng báo `allow` nhưng TCP test vẫn timeout vì host firewall ở database từ chối nguồn. Đây là **test chức năng thất bại ở lớp khác**, không phải bằng chứng firewall vùng vi phạm default deny.

### 8.3. DNS, xác thực và dịch vụ nền tảng

Khi bật default deny ở egress, có thể vô tình chặn **DNS, NTP, PKI/CRL/OCSP, dịch vụ định danh, DHCP relay, log forwarding, monitoring và hệ thống cập nhật**. Lập danh mục luồng nền tảng trước khi cutover; cho phép đúng endpoint/service, hạn chế mở toàn Internet.

Một ứng dụng có thể dùng CDN, IP động, dịch vụ đám mây hoặc DNS trả nhiều địa chỉ. Nếu policy dựa trên FQDN hoặc ứng dụng, cần xác minh cách thiết bị cập nhật DNS cache, TTL, TLS/SNI và cách xử lý khi DNS lỗi. Không tự cho rằng **cho phép DNS UDP/53** nghĩa là đã kiểm soát toàn bộ DNS khi môi trường có TCP/53, DNS-over-HTTPS hoặc resolver riêng.

### 8.4. IPv6, overlay và cấu hình đa môi trường

- Tạo ma trận riêng cho IPv6; policy chỉ dùng IPv4 không có nghĩa IPv6 được chặn.
- Kiểm tra overlay/SD-WAN, VPN split tunnel, service mesh và chính sách pod nếu traffic đi ngoài điểm thực thi dự kiến.
- Với HA/cluster, xác minh rule được áp dụng trên cả node và sau failover.
- Với cloud, xem rõ ingress/egress, security group theo tài nguyên, network ACL theo subnet và rule do IaC/controller quản lý. Default values không đồng nhất giữa sản phẩm.
- Kiểm tra đường quản trị OOB, management VRF hoặc kết nối đối tác; các đường này có thể không đi qua firewall dùng để thử nghiệm.

### 8.5. IDS/IPS và giám sát

IDS/IPS có thể báo traffic đáng ngờ nhưng **không nhất thiết chặn**, tùy inline/passive mode và chính sách. Kết quả test phải phân biệt: `detected`, `alerted`, `dropped`, `rejected` và `allowed`. Không lấy cảnh báo IDS làm bằng chứng rằng firewall đã từ chối. Ngược lại, một rule firewall có thể chặn mà IDS không quan sát do traffic bị drop ở tầng trước.

## 9. Quy trình xác minh trước và sau thay đổi

~~~mermaid
flowchart TD
    A["Xác định phạm vi, rulebase, ngoại lệ"] --> B["Đặt ma trận positive/negative và ngưỡng"]
    B --> C["Xác minh đường đi và dịch vụ test"]
    C --> D["Lưu cấu hình / nguồn chứng cứ"]
    D --> E["Áp dụng thay đổi trong phạm vi được duyệt"]
    E --> F["Thử luồng được phép và luồng bị chặn"]
    F --> G{"Đạt cả hai loại test?"}
    G -->|"Không"| H["Dừng, điều tra log/route/NAT, rollback an toàn"]
    H --> C
    G -->|"Có"| I["Kiểm tra ngoại lệ, IPv6, HA, phiên mới"]
    I --> J{"Rủi ro và vận hành đạt?"}
    J -->|"Không"| H
    J -->|"Có"| K["Bàn giao evidence, owner, expiry và baseline"]
~~~

Các bước chi tiết:

1. **Preflight:** người phê duyệt xác định phạm vi, danh sách hệ thống ảnh hưởng, chỉ số dịch vụ và điều kiện dừng. Thống nhất nơi kiểm thử và lượng traffic giới hạn.
2. **Snapshot:** lưu rulebase đang chạy, NAT, route, security group, host policy, phiên bản cấu hình, trạng thái HA và các exception ID.
3. **Baseline:** chạy test dương/âm đã phê duyệt trước thay đổi (khi an toàn) và ghi trạng thái hệ thống; kiểm tra dữ liệu log có thể truy xuất.
4. **Thực thi:** cập nhật rule có phạm vi cụ thể, xác minh commit/deploy và đồng bộ tới các điểm thực thi.
5. **Kiểm thử:** thực hiện cả P/N theo ma trận, ưu tiên lưu lượng nghiệp vụ cốt lõi và ranh giới nhạy cảm; đối chiếu packet path và log tại nơi chặn/cho phép.
6. **Kiểm tra lệch:** rule shadowing, policy IPv6, egress, HA và existing sessions; kiểm tra ngoại lệ theo thời gian.
7. **Nghiệm thu:** kết hợp chủ dịch vụ và nhóm an ninh chấp thuận; lưu kết quả cùng các rủi ro còn tồn đọng.
8. **Theo dõi:** giám sát lỗi ứng dụng, kết nối bị chặn bất thường, số lượng ngoại lệ, quá hạn và config drift.

**Điều kiện rollback:** luồng nghiệp vụ hợp lệ bị chặn ngoài ngưỡng cho phép, nhiều vùng mất DNS/IdP/log, xuất hiện đường truy cập trái phép hoặc mất khả năng quan sát. Khi quay lui, chọn cấu hình **an toàn đã xác minh**; không tự mở toàn mạng để khôi phục nhanh.

## 10. Tình huống thực hành: mở ngoại lệ backup nhưng giữ default deny

**Bối cảnh:** Một doanh nghiệp dùng ba vùng: USER (máy trạm), APP (dịch vụ nội bộ) và DATA (database). Baseline chỉ cho USER → APP qua HTTPS và APP → DATA qua TCP/5432. Nhóm vận hành cần một máy backup ở vùng BACKUP kết nối vào database trong một ca bảo trì.

**Yêu cầu bảo mật:** Giữ chặn mặc định giữa vùng, cấp ngoại lệ chỉ cho một máy backup, một database, một cổng và thời hạn ngắn; không mở SSH hoặc toàn bộ subnet.

**Bước 1 — Phê duyệt.** Chủ ứng dụng/database xác nhận nhu cầu và cửa sổ. Nhóm an ninh ghi nhận rủi ro, biện pháp kiểm soát ở database (TLS và xác thực), kế hoạch thu hồi rule sau ca.

**Bước 2 — Cấu hình.** Thêm allow cho `10.60.60.25/32 → 10.30.30.10/32 TCP/5432` theo chiều BACKUP → DATA; giữ deny mặc định cho các luồng khác. Lưu rule ID và thứ tự chính sách.

**Bước 3 — Kiểm thử.** P4 từ máy backup đúng phải kết nối và xác thực hợp lệ; N5 từ máy khác cùng subnet phải bị chặn; N6 từ chính máy backup tới TCP/22 phải bị chặn; N1 từ USER trực tiếp tới database tiếp tục bị chặn. Đối chiếu log firewall, NAT/route và database audit.

**Bước 4 — Quan sát.** Chạy một giao dịch backup thử có giới hạn, kiểm tra kết quả, tải hệ thống và log. Nếu mở rule làm lộ thêm nguồn hoặc dịch vụ, dừng và rollback.

**Bước 5 — Thu hồi.** Khi hết thời hạn, gỡ rule, đánh giá existing sessions theo firewall và xác minh **một kết nối mới** từ máy backup đến database bị chặn. Lưu log thu hồi và xác nhận của chủ dịch vụ.

### 10.1. Mẫu kết quả nghiệm thu

| Mục | Kỳ vọng | Bằng chứng cần có |
| --- | --- | --- |
| USER → APP TCP/443 | Allow | Host test, API response đúng, firewall allow |
| USER → DATA TCP/5432 | Deny | Firewall/host deny, source/route đúng |
| APP → DATA TCP/5432 | Allow | Database authentication và log |
| BACKUP host được duyệt → DATA TCP/5432 | Allow khi rule còn hiệu lực | Ticket, policy ID, log, giao dịch thử |
| BACKUP host khác → DATA TCP/5432 | Deny | Deny log và kết quả test |
| BACKUP host được duyệt → DATA TCP/22 | Deny | Deny log, không mở quyền SSH |
| BACKUP host được duyệt → DATA sau expiry | Deny với **phiên mới** | Rule removed, log, kiểm thử sau thu hồi |
| IPv6 và tuyến dự phòng | Không xuất hiện luồng ngoài policy | Rule review và test theo topology |

Kết luận **PASS** chỉ khi cả luồng hợp lệ lẫn luồng không hợp lệ có bằng chứng phù hợp. Nếu chỉ biết “máy backup chạy được job” nhưng chưa thử máy kế bên và chưa kiểm tra cổng khác, ngoại lệ **chưa được xác nhận đủ hẹp**.

## 11. Đưa kiểm chứng vào quy trình vận hành liên tục

### 11.1. Tự động hóa ở mức phù hợp

Có thể dùng **Infrastructure as Code (IaC)** hoặc policy-as-code để đối chiếu rule với manifest đã phê duyệt, phát hiện `any/any` ngoài chính sách, ngoại lệ quá hạn hoặc thay đổi không qua change ticket. Tuy nhiên, kiểm tra tĩnh chỉ cho thấy cấu hình được mô tả; vẫn cần **kiểm chứng runtime** để phát hiện route leak, NAT, overlay, agent chưa cập nhật và đường truyền khác.

Với kiểm thử tự động, nên dùng probes có phạm vi hẹp, tần suất kiểm soát, tài khoản/thiết bị test chuyên dụng và log liên kết tới phiên bản chính sách. Không tạo lưu lượng cao, không cố vượt kiểm soát, không thay đổi dữ liệu ứng dụng khi chỉ cần xác minh kết nối.

### 11.2. Các chỉ số theo dõi

| Chỉ số | Cách hiểu | Lưu ý |
| --- | --- | --- |
| **Positive test pass rate** | Số phép thử allow thành công / tổng phép thử allow hợp lệ | Phải xác minh ứng dụng nếu mục tiêu là nghiệp vụ |
| **Negative test pass rate** | Số phép thử deny có bằng chứng bị chặn / tổng phép thử deny | Timeout không kèm bằng chứng là kết quả chưa kết luận |
| **Exception completeness** | Tỷ lệ ngoại lệ có owner, reason, scope, approval, expiry, test | Không đếm rule không có metadata là “đã quản lý” |
| **Expired exception count** | Ngoại lệ quá hạn nhưng chưa được thu hồi/đánh giá lại | Phải kiểm tra cả rule còn hiệu lực trong runtime |
| **Overly broad rules** | Rule có source/destination/service vượt baseline | Cần bối cảnh; một số rule hạ tầng có lý do đặc thù |
| **Policy drift** | Khác biệt giữa phiên bản phê duyệt và cấu hình thực | Theo dõi thay đổi từ GUI, CLI, automation và controller |
| **Coverage** | Tỷ lệ ranh giới, môi trường và điểm thực thi được test | Phải bao gồm IPv6, HA, cloud, VPN và east–west nếu áp dụng |

Cần kết hợp số liệu vận hành với **phản hồi của chủ dịch vụ** và bằng chứng từ firewall/flow logs. Chỉ số đẹp không chứng minh an toàn khi inventory thiếu một zone hoặc các test âm đều dùng cùng một máy không đi qua firewall mục tiêu.

## 12. Sai lầm thường gặp

- **Chỉ có rule `deny any any` ở cuối:** chưa xem allow phía trên, thứ tự ưu tiên, địa chỉ/zone, egress hoặc đường vòng.
- **Kiểm thử chỉ từ nguồn được phép:** bỏ qua nguy cơ rule cho cả subnet, user group hoặc mạng đối tác.
- **Dùng ping hoặc timeout làm bằng chứng tuyệt đối:** ICMP khác TCP/UDP; timeout có nhiều nguyên nhân.
- **Không biết vị trí lọc so với NAT:** đối chiếu sai source/destination của gói khi đọc log.
- **Không xét stateful session cũ:** sửa rule nhưng phiên trước đó vẫn thông, gây kết luận sai.
- **Bỏ sót IPv6 hoặc đường đi nội bộ cùng VLAN:** traffic có thể không qua policy đang kiểm tra.
- **Mở toàn bộ cổng để sửa lỗi ứng dụng:** thay vì xác định DNS, identity, database và các luồng nền tảng chính xác.
- **Cấp ngoại lệ vĩnh viễn cho công việc tạm:** không có expiry, review và bằng chứng thu hồi.
- **Cho rằng IDS alert là firewall deny:** IDS có thể chỉ quan sát, không chặn.
- **Không kiểm tra rule sau failover hoặc sau deploy:** controller báo thành công nhưng dataplane hoặc node dự phòng chưa áp dụng.
- **Xóa rule “0 hits” ngay:** chưa đối chiếu chu kỳ nghiệp vụ hoặc log/counter bị reset.

## 13. Checklist và câu hỏi tự kiểm tra

| Checklist | Có / Chưa / Không áp dụng |
| --- | --- |
| Đã xác định rõ vùng, nguồn, đích, protocol/port và chiều của policy? | |
| Đã phân biệt default deny ingress/egress/east–west và stateful/stateless? | |
| Đã kiểm tra cả IPv4 và IPv6, NAT, route, HA và đường VPN/cloud phụ? | |
| Có **positive test** cho từng luồng bắt buộc? | |
| Có **negative test** cho nguồn, đích, port, identity hoặc vùng không được phép? | |
| Kết quả âm có log/counter/packet evidence cho thấy chặn đúng ranh giới? | |
| Các ngoại lệ có owner, lý do, scope, phê duyệt, expiry và rollback? | |
| Đã kiểm tra hoạt động sau khi thu hồi ngoại lệ với **phiên mới**? | |
| Đã lưu snapshot policy, kết quả test và xử lý các phần chưa kết luận? | |
| Đã lên lịch rà soát ngoại lệ, drift và đo độ phủ kiểm thử? | |

**Câu hỏi ôn tập:**

1. Vì sao một firewall cấu hình implicit deny ở ingress chưa chứng minh egress đã default deny?
2. Khi `nc` báo timeout tới TCP/5432, cần thu thập thêm chứng cứ gì để kết luận luồng bị firewall chặn?
3. Một rule chỉ cho `10.60.60.25/32` vào database TCP/5432. Hãy đề xuất **hai phép kiểm thử âm** phù hợp.
4. Vì sao đổi một rule từ allow sang deny vẫn có thể không làm ngắt phiên TCP đã thiết lập?
5. Sự khác nhau giữa kiểm thử trên firewall stateful và network ACL stateless là gì?
6. Ngoại lệ backup đã hết hạn nhưng vẫn có một phiên đang hoạt động. Cần xác minh điều gì trước khi tuyên bố ngoại lệ đã được thu hồi hoàn toàn?
7. Vì sao một kết nối hợp lệ thất bại ở host firewall không chứng minh rule của firewall vùng đang chặn?

**Gợi ý trả lời:** (1) Ingress và egress có phạm vi/default khác nhau. (2) Log/rule hit, packet path, NAT, trạng thái dịch vụ và lỗi tuyến. (3) Thử host `10.60.60.26` tới TCP/5432, thử host được phép tới TCP/22. (4) Firewall stateful có thể duy trì session state. (5) Stateless thường cần thiết kế cho cả gói chiều trả lời. (6) Kiểm tra rule đã gỡ, policy có hiệu lực, phiên cũ và test **kết nối mới** bị chặn; xử lý phiên cũ theo quy trình. (7) Có nhiều lớp lọc, cần xác định điểm từ chối thực tế.

**Ghi nhớ:** Default deny chỉ được xác nhận khi ta biết **ranh giới nào thực thi**, **luồng nào thực sự cần**, **ngoại lệ nào được cho phép** và có bằng chứng cả hai chiều kiểm thử: *luồng hợp lệ thông suốt, luồng ngoài chính sách bị chặn*. Mỗi ngoại lệ phải có giới hạn, thời hạn, chủ sở hữu và phép thử sau thu hồi để chính sách không mất hiệu lực theo thời gian.
