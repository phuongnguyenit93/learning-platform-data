# Service enumeration và fingerprinting trong kiểm thử bảo mật mạng

## 1. Service enumeration và fingerprinting là gì?

Khi kiểm tra an toàn một mạng, việc biết một địa chỉ IP đang hoạt động mới chỉ là bước đầu. Người kiểm thử cần biết tại các điểm truy cập được phép có những **dịch vụ nào đang lắng nghe**, chúng giao tiếp bằng giao thức gì, đang dùng cấu hình hay phần mềm nào, và liệu tình trạng đó có khớp với danh mục tài sản/chính sách bảo mật hay không.

**Service enumeration** (liệt kê dịch vụ) là quá trình nhận diện và mô tả các dịch vụ quan sát được qua mạng: endpoint, cổng, giao thức, trạng thái truy cập, kiểu phản hồi, tên máy/virtual host, chức năng dự đoán và những đặc điểm cấu hình liên quan.

**Fingerprinting** (nhận diện dấu vân tay) là quá trình suy luận đặc tính của thiết bị, hệ điều hành, ứng dụng hoặc phiên bản dựa trên mẫu phản hồi, banner, thông số bắt tay, chứng chỉ, HTTP headers, giao thức ứng dụng hoặc nhiều dấu hiệu ghép lại.

Trong chương **Kiểm thử và xác minh bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**, kỹ năng này giúp kiểm chứng hiệu quả của phân đoạn mạng, firewall, VPN, IDS/IPS, DNS security, Wi-Fi và kiểm soát truy cập cloud. Một hệ thống cấu hình phòng vệ tốt cần **biết và quản lý** những dịch vụ nào đang lộ ra theo từng vùng truy cập; đồng thời phải tránh việc người ngoài dễ dàng thu được thông tin nhạy cảm từ giao diện quản trị hoặc phiên bản phần mềm.

### 1.1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt host discovery, port scanning, service enumeration, version detection, OS/device fingerprinting và vulnerability assessment.
- Chọn cách quan sát thụ động hoặc kiểm thử chủ động phù hợp với mục đích và phạm vi được phép.
- Diễn giải trạng thái TCP/UDP, banner, TLS certificate, SSH host key, HTTP response và DNS metadata mà không kết luận quá mức.
- Dùng các ví dụ lệnh Nmap, curl, OpenSSL, dig và các nguồn log để quan sát dịch vụ trong lab hoặc hệ thống được phép.
- Tương quan kết quả với asset inventory, cấu hình firewall, CMDB, Kubernetes/cloud control plane và telemetry.
- Thiết kế quy trình đo lường trước/sau khi hardening, phát hiện cấu hình ngoài baseline, lưu bằng chứng và báo cáo mức tin cậy.
- Hiểu rủi ro của việc truy vấn dịch vụ thật: tải, log, IDS/IPS alert, lockout, thiết bị cũ dễ lỗi và rò rỉ dữ liệu nhạy cảm.

> **Nguyên tắc:** Phát hiện một cổng đang mở không đồng nghĩa đã biết chắc dịch vụ, phiên bản hay lỗ hổng. Mọi kết luận cần có **điểm quan sát, bằng chứng, mức độ chắc chắn và phạm vi áp dụng**.

## 2. Phân biệt các công đoạn kiểm thử

| Công đoạn | Câu hỏi chính | Đầu ra thường thấy | Điều chưa chứng minh |
|---|---|---|---|
| Asset discovery | Có những IP, FQDN hoặc thiết bị nào thuộc phạm vi? | Inventory sơ bộ, địa chỉ và hostname | Mọi host đều trả lời ping hay đang bật dịch vụ |
| Host discovery | Host có dấu hiệu reachable không? | ICMP/ARP/TCP response, telemetry | Không phản hồi nghĩa là host không tồn tại |
| Port scanning | Từ một vị trí, cổng/giao thức có phản hồi thế nào? | TCP open/closed/filtered, UDP open/filtered | Phần mềm chạy trên cổng và mức độ an toàn |
| **Service enumeration** | Endpoint đó nói giao thức/ứng dụng gì? | HTTP, SSH, DNS, SMTP, SNMP, TLS, thông tin endpoint | Độ chính xác tuyệt đối của tên/phiên bản |
| **Fingerprinting** | Các phản hồi gợi ý loại phần mềm, phiên bản, OS hay thiết bị nào? | Banner, TLS stack characteristics, OS hints, product signatures | Hệ điều hành hoặc bản phát hành chắc chắn, nhất là qua proxy |
| Configuration assessment | Dịch vụ có được hardening theo baseline không? | TLS versions, anonymous access, authentication, ACL, headers | Có thể khai thác được hay không |
| Vulnerability assessment | Có dấu hiệu CVE hoặc điểm yếu phù hợp không? | Phát hiện cần xác minh, mức ưu tiên | CVE áp dụng và khai thác được chỉ vì banner trùng |
| Penetration test | Kiểm chứng tác động của điểm yếu trong phạm vi được phép | Bằng chứng tác động theo rules of engagement | Không được tự mở rộng phạm vi hoặc thử phá hoại |

Quy trình thông thường: **inventory → xác định phạm vi → kiểm tra reachability/cổng → enumeration → fingerprinting → xác minh cấu hình và phiên bản → đánh giá rủi ro → kiểm tra lại sau khắc phục**. Không phải lúc nào cũng cần chủ động quét: môi trường production nhạy cảm có thể ưu tiên telemetry, config API và log sẵn có.

### 2.1. Một endpoint không phải một dịch vụ độc lập

Cần phân biệt:

- **Socket/port:** `192.0.2.10:443/tcp` là điểm truy cập ở tầng vận chuyển, chưa chắc ứng dụng phía sau là web server thuần túy.
- **Giao thức:** cổng 443 thường là HTTPS, nhưng có thể là một dịch vụ dùng TLS khác hoặc proxy. Một giao thức có thể chạy trên cổng phi chuẩn.
- **Service instance:** một Nginx hoặc load balancer có thể phục vụ nhiều virtual host bằng Host header/SNI, mỗi tên miền dẫn đến ứng dụng khác.
- **Backend:** response có thể do CDN/WAF/proxy tạo, không nhất thiết phản ánh phiên bản ứng dụng hoặc OS backend.
- **Đường truy cập:** cùng endpoint có thể xuất hiện khác nhau tùy nguồn trong VPN, management VLAN, Internet hoặc cloud VPC.

Do đó, record enumeration nên chứa **nguồn kiểm thử + destination IP/port/protocol + FQDN/SNI (nếu có) + thời gian UTC + kết quả**.

## 3. Nhìn từ góc độ phòng thủ: tại sao cần enumeration?

Một inventory cấu hình cho biết **dịch vụ đáng ra phải bật**; enumeration từ từng vùng truy cập cho biết **dịch vụ thực sự có thể quan sát** ở thời điểm kiểm thử. Hai nguồn không phải lúc nào trùng nhau.

Ví dụ một firewall có thể chỉ cho phép HTTPS từ mạng quản trị, nhưng policy ở interface IPv6 lại chưa được áp dụng. Nếu chỉ thử từ subnet IPv4 nội bộ, nhóm vận hành sẽ bỏ sót đường truy cập qua IPv6. Tương tự, một load balancer có thể lộ trang quản trị qua địa chỉ private trong VPN mà mạng người dùng thông thường vẫn truy cập được.

Các mục tiêu phòng vệ thường gặp:

1. **Giảm attack surface:** phát hiện Telnet, HTTP quản trị plaintext, FTP, cổng debug, API không cần thiết, dịch vụ thừa.
2. **Xác minh segmentation:** user network không đến được management plane; app segment chỉ được truy cập database theo quy tắc.
3. **Kiểm chứng firewall/ACL:** trạng thái nhìn thấy từ các nguồn có khớp rule dự kiến không?
4. **Kiểm chứng hardening:** chỉ giao thức và phiên bản TLS phù hợp, không có cổng legacy sau migration.
5. **Nhận diện drift:** sau reboot, firmware upgrade, triển khai container/cloud hoặc thay rule, dịch vụ có đổi khác không?
6. **Chuẩn bị incident response:** khi phát hiện lưu lượng bất thường, biết endpoint thực sự phục vụ gì để điều phối đúng owner.

**Phát hiện cổng mở ≠ lỗ hổng.** Lỗ hổng phụ thuộc phiên bản phần mềm thực, cấu hình, đường truy cập, quyền, độ phơi bày, biện pháp giảm thiểu và điều kiện khai thác. Một dịch vụ không hiển thị ở điểm kiểm thử cũng chưa chắc đã tắt trên toàn mạng.

## 4. Phương pháp thụ động và chủ động

### 4.1. Passive enumeration

Quan sát từ dữ liệu đã được tổ chức cho phép thu thập mà không tạo traffic truy vấn bổ sung tới dịch vụ đang kiểm tra:

- NetFlow/IPFIX, firewall session logs, VPC flow logs để thấy các 5-tuple và lưu lượng hai chiều.
- PCAP/TAP/SPAN từ cảm biến đã triển khai, phân tích TCP handshake, TLS metadata, DNS, HTTP plaintext khi có.
- DHCP/IPAM/CMDB, container orchestration, cloud inventory API và load balancer target groups.
- Reverse proxy/API gateway logs, TLS termination logs, service mesh telemetry.
- IDS/IPS/NDR detections để đánh dấu phiên có hành vi khác thường.

Ưu điểm là ít làm tăng tải cho dịch vụ. Giới hạn: **không có traffic không đồng nghĩa không có dịch vụ**; inventory có thể cũ; telemetry có sampling/drop; traffic TLS được mã hóa; một sensor chỉ quan sát được một phần mạng.

### 4.2. Active enumeration

Tạo những yêu cầu giới hạn và được phê duyệt để kiểm tra phản hồi trực tiếp: kết nối TCP, giao tiếp giao thức, kiểm tra TLS handshake, HTTP HEAD/GET một endpoint công khai nội bộ, DNS query hay đọc banner được server tự gửi.

Ưu điểm: kiểm tra được reachability theo vị trí, thu thông tin giao thức mà inventory không có. Rủi ro: có thể kích hoạt IDS/IPS, làm tải tăng, bị rate limiting, ghi log nhạy cảm hoặc ảnh hưởng appliance cũ. Các bài kiểm thử chủ động cần **rules of engagement** (RoE) mô tả cụ thể mục đích, nguồn, đích, thời gian, cường độ và cách dừng khi có sự cố.

| Tiêu chí | Passive | Active |
|---|---|---|
| Traffic bổ sung tới target | Không hoặc tối thiểu với hoạt động quan sát | Có |
| Khả năng thấy dịch vụ chưa có lưu lượng | Thấp | Có thể kiểm tra |
| Mức ảnh hưởng production | Thường thấp hơn, nhưng capture/log có chi phí | Phụ thuộc tốc độ và nội dung probe |
| Kết quả phụ thuộc điểm quan sát | Có | Có, gồm cả ACL/routing/firewall từ nguồn thử |
| Dễ nhầm với traffic tấn công | Thấp nếu chỉ đọc dữ liệu sẵn có | Có thể bị IPS/WAF nhận diện như reconnaissance |
| Khả năng thấy cấu hình backend | Giới hạn | Giới hạn; proxy/WAF có thể trả thay |

Không dùng kỹ thuật lẩn tránh giám sát hoặc cố che nguồn kiểm thử trong một bài kiểm tra hardening thông thường. Thay vào đó, phối hợp SOC, ghi change/test ID và đối chiếu alert để kiểm tra chính quy trình giám sát.

## 5. Xác định phạm vi trước khi kiểm thử

Một tác vụ enumeration có thể rất nhỏ hoặc vô tình trở thành quét toàn bộ hệ thống. Trước khi bắt đầu cần thống nhất:

- **Ai phê duyệt:** người sở hữu tài sản, security owner, vận hành network/SOC và đầu mối dừng kiểm thử.
- **Phạm vi:** IP/CIDR, hostname, cổng, giao thức, interface, cloud account/region và môi trường (lab, staging, production).
- **Nguồn phép thử:** máy kiểm thử, management subnet, vị trí qua VPN và những vùng truy cập cần so sánh.
- **Thời gian:** cửa sổ kiểm thử, thời điểm có tải thấp, deadline và giới hạn tốc độ/đồng thời.
- **Mức hoạt động:** chỉ đọc banner, TLS handshake, HTTP headers, DNS queries; không thực hiện đăng nhập thử hàng loạt, brute force, khai thác hoặc chạy script có tác động.
- **Dịch vụ ngoại lệ:** PLC/OT, thiết bị y tế, mạng không dây nhạy cảm, thiết bị end-of-life hoặc rate-limited appliances cần phương pháp riêng.
- **Điều kiện dừng:** latency/loss tăng, sự cố ứng dụng, rate limit, IDS/IPS phản ứng không mong muốn hoặc owner yêu cầu.
- **Bằng chứng:** thời gian UTC, công cụ/phiên bản, command/parameters, nguồn scan, output, logs, giới hạn và nơi lưu bảo vệ.

### 5.1. Mô hình phạm vi

~~~mermaid
flowchart LR
    I["CMDB, IPAM, scope đã phê duyệt"] --> P["Kế hoạch kiểm thử giới hạn"]
    P --> S1["Nguồn: management zone"]
    P --> S2["Nguồn: user zone"]
    P --> S3["Nguồn: VPN hoặc cloud segment"]
    S1 --> T["Endpoint được phép kiểm tra"]
    S2 --> T
    S3 --> T
    T --> R["Record có source, UTC, endpoint, bằng chứng"]
    R --> V["Đối chiếu firewall, service owner, baseline"]
    V --> F["Finding và kiểm tra lại sau sửa"]
~~~

Với mục tiêu kiểm chứng segmentation, **cùng đích nhưng nhiều nguồn thử** thường hữu ích hơn quét vô số cổng từ một nguồn.

## 6. TCP port scanning và ý nghĩa trạng thái

TCP thiết lập kết nối thông thường qua SYN → SYN-ACK → ACK. Nhưng trạng thái mà công cụ ghi nhận phụ thuộc kiểu scan, network path, firewall, timeout, rate limiting và phiên bản công cụ.

| Trạng thái Nmap | Ý nghĩa thực dụng | Giới hạn |
|---|---|---|
| `open` | Có phản hồi phù hợp với cổng TCP đang chấp nhận kết nối hoặc UDP trả lời theo probe | Chưa chứng minh dịch vụ/phiên bản chính xác |
| `closed` | Công cụ nhận phản hồi phù hợp với không có listener hoặc từ chối ở cổng | Có thể do thiết bị trung gian sinh phản hồi |
| `filtered` | Không thể xác định open/closed vì lọc hoặc không nhận đủ phản hồi | Host có thể vẫn hoạt động, đường đi có vấn đề |
| `unfiltered` | Trạng thái lọc có thể xác định nhưng chưa biết open/closed ở một số kiểu scan | Không phải bảo đảm cổng mở |
| `open|filtered` | Không phân biệt được mở và bị lọc theo kiểu probe | Phổ biến ở UDP hoặc một số scan type |
| `closed|filtered` | Không phân biệt rõ đóng và lọc | Phụ thuộc kiểu scan, không thường thấy với connect scan |

Các trạng thái trên là **nhãn suy luận của Nmap từ phản hồi**, không phải thuộc tính tuyệt đối của thiết bị ở mọi vị trí. Ví dụ `22/tcp open` từ bastion không có nghĩa SSH reachable từ Internet.

**Một số bẫy suy luận:**

- Cổng 443 thường dùng TLS/HTTPS, nhưng có thể phục vụ giao thức khác hoặc reverse proxy.
- Port forwarding/NAT có thể chuyển kết nối tới máy khác, khiến banner thuộc backend khác với IP quan sát.
- Firewall reject có thể gửi TCP RST làm một cổng trông như `closed`, dù service còn tồn tại phía sau.
- Một cổng `filtered` không cho biết packet bị chặn ở firewall nào; cần log/PCAP tại nhiều điểm.
- Rate limiting, SYN cookies, overload và middlebox có thể làm kết quả thay đổi giữa các lần.
- TCP SYN scan thường cần quyền raw packet; TCP connect scan thường dùng API kết nối của hệ điều hành. Cách chọn ảnh hưởng điều kiện thực hiện và cách ghi log.

### 6.1. Ví dụ kiểm tra TCP có kiểm soát

Các lệnh trong bài dùng **địa chỉ dành cho tài liệu** `192.0.2.10`, hostname `app.example.test`, chỉ để minh họa trên lab thuộc quyền quản lý. Không dùng trên hệ thống ngoài phạm vi đã được phê duyệt.

~~~bash
# Quét một host và đúng ba cổng đã được phê duyệt.
# -sT: TCP connect; -sV: nhận diện service/version bằng probe.
# --version-light: tập probe gọn hơn, có thể giảm độ chắc chắn.
# --max-rate và --max-retries: giới hạn một phần tác động.
nmap -sT -sV --version-light \
  -p 22,80,443 \
  --max-rate 10 --max-retries 1 \
  --host-timeout 90s \
  -oN service-check.txt \
  192.0.2.10
~~~

Lệnh giả định đã có Nmap trên máy kiểm thử và Nmap có thể kết nối đích. `--max-rate` giới hạn tốc độ phát packet ở phần engine phù hợp, **không bảo đảm** tất cả yêu cầu mức ứng dụng tạo bởi `-sV% đều có chung giới hạn chính xác; giới hạn tổng thể còn phụ thuộc script, timeout và độ đồng thời. Với thiết bị nhạy cảm nên giảm phạm vi, thử từng dịch vụ, dùng cấu hình timing thận trọng và theo dõi tài nguyên.

**Lưu ý về `-sV`:** công cụ có thể gửi nhiều probe có nội dung giao thức để phân biệt sản phẩm/phiên bản. Đây không phải hoạt động hoàn toàn thụ động; một số dịch vụ cũ hoặc ứng dụng tự viết có thể log lỗi hoặc phản ứng khác thường. Trong production cần phê duyệt cường độ và dừng khi hệ thống bị ảnh hưởng.

### 6.2. Một kết quả giả định

~~~text
Nmap scan report for 192.0.2.10
PORT    STATE    SERVICE  VERSION
22/tcp  open     ssh      OpenSSH (version chưa xác minh)
80/tcp  closed   http
443/tcp open     ssl/http reverse-proxy (chưa rõ phiên bản)
~~~

Kết quả chỉ để minh họa cách đọc. Không thể suy luận rằng backend là Linux cụ thể từ một dòng `OpenSSH` hoặc rằng HTTP/443 hoàn toàn an toàn vì port 80 đóng. Cần kiểm tra bản build thực, thông số TLS, chính sách xác thực, CVE applicability và khả năng truy cập từ từng vùng.

### 6.3. Vì sao không nên bắt đầu bằng quét mọi cổng?

Một dải cổng lớn và nhiều host có thể tạo rất nhiều kết nối, log và alert; ở môi trường production, việc đó gây rủi ro và khiến kết quả khó xử lý. Nên bắt đầu từ inventory và danh sách cổng thực sự cần kiểm chứng, rồi mở rộng **chỉ trong phạm vi được duyệt** khi có căn cứ.

Không chạy những chức năng tự động thử khai thác, mật khẩu hoặc kiểm tra tính gây gián đoạn chỉ để lấy tên dịch vụ. Enumeration và version detection nên giữ ở mức quan sát/handshake phù hợp mục tiêu.

## 7. UDP enumeration: tại sao khó kết luận hơn TCP?

UDP không có bắt tay ba bước và nhiều dịch vụ **không phản hồi** khi nhận một datagram không hợp lệ. Do đó việc không thấy response có thể là:

- Dịch vụ đang hoạt động nhưng bỏ qua payload không hợp lệ.
- Cổng bị firewall chặn hoặc ICMP trả lời bị giới hạn tốc độ.
- Đường đi bất đối xứng, packet loss hoặc VPN/NAT can thiệp.
- Server chỉ phản hồi khi nhận đúng cấu trúc protocol.
- Mạng có rate limit hoặc IDS/IPS chặn probe.

Với UDP, kết quả `open|filtered` khá thường gặp; **không được trình bày như đã xác nhận dịch vụ mở**. Một ICMP Port Unreachable phù hợp có thể cho biết cổng đóng, nhưng phải xét nguồn phát, NAT, firewall và cách công cụ xử lý.

| Dịch vụ ví dụ | UDP thường dùng | Bằng chứng đáng tin hơn việc “không có ICMP” |
|---|---|---|
| DNS | 53/udp | DNS response hợp lệ với ID, question, flags/rcode |
| NTP | 123/udp | Bản tin NTP đúng cấu trúc từ server được phép |
| SNMP | 161/udp | SNMP response phù hợp policy và quyền |
| DHCP | 67/68/udp | Bản tin giao thức trong segment/VLAN phù hợp |
| QUIC/HTTP/3 | 443/udp | QUIC handshake/transport telemetry, server/client logs |

### 7.1. Ví dụ UDP giới hạn

~~~bash
# Chỉ trên host DNS/NTP được phép, ba cổng được thống nhất với owner.
nmap -sU -sV --version-light \
  -p 53,123,161 \
  --max-rate 5 --max-retries 1 \
  --host-timeout 90s \
  -oN udp-check.txt \
  192.0.2.10
~~~

UDP service probing có thể tạo request không được ứng dụng mong đợi. Trước khi chạy phải xác minh đích có thực sự phục vụ các giao thức trên; không gửi SNMP community mặc định, thử hàng loạt credential hoặc gửi payload có khả năng gây khuếch đại. Các thiết bị nhạy cảm cần phương án kiểm tra qua API/log và thử trong lab trước.

Với DNS, một truy vấn hợp lệ có giới hạn giúp xác định dịch vụ tốt hơn một UDP probe chung:

~~~bash
# Chỉ truy vấn DNS resolver nằm trong phạm vi được duyệt.
dig @192.0.2.10 app.example.test A +time=2 +tries=1
~~~

DNS response `REFUSED`, `SERVFAIL` hoặc `NXDOMAIN` có thể vẫn cho thấy server đã xử lý query theo một chính sách; cần phân biệt **dịch vụ tồn tại** với **trả nội dung mong đợi**.

## 8. Service enumeration ở lớp ứng dụng

Sau khi quan sát một cổng reachable, cần **kiểm tra đúng giao thức** để xác định service. Các tín hiệu phổ biến:

| Giao thức | Dấu hiệu có thể dùng | Điều kiện và giới hạn |
|---|---|---|
| SSH | Chuỗi nhận diện `SSH-2.0-...`, host key algorithms | Banner có thể đổi/ẩn; host key không tự chứng minh OS |
| HTTP/HTTPS | Status, `Server` header, redirects, title, allowed methods | Reverse proxy/WAF và app có thể ghi hoặc giả banner |
| TLS | Chứng chỉ, SAN, issuer, ALPN, negotiated protocol/cipher | Cert có thể từ LB/CDN; SNI quyết định endpoint |
| DNS | Authoritative/recursive behavior, rcode, EDNS flags | Cache, split DNS, policy và client source ảnh hưởng |
| SMTP | `220` greeting, STARTTLS support | Greeting có thể che/giả bản phát hành; policy theo nguồn |
| FTP | Greeting và lệnh được hỗ trợ | Giao thức plaintext có rủi ro, chỉ quan sát trong lab/phạm vi |
| SNMPv3 | Cấu hình user/security level, trả lời polling được phép | Không suy ra secret; `authPriv` quan trọng hơn banner |
| RDP | Handshake và certificate metadata | NLA, gateway, ACL, phiên bản client/server ảnh hưởng |
| SMB | Negotiated dialect, signing/encryption requirements | Không được thử chia sẻ/đăng nhập vượt phạm vi |
| Database | Handshake/version protocol, TLS support | Proxy và driver có thể giấu version; tránh gửi truy vấn thay đổi |

Một số dịch vụ chỉ gửi banner khi client gửi thông điệp đúng cấu trúc. **Không thử ngẫu nhiên payload**, đặc biệt trên thiết bị công nghiệp, controller hoặc service tự viết; probe cần được owner chấp thuận và biết tính tương thích.

### 8.1. HTTP và HTTPS

~~~bash
# Kiểm tra response headers; -I dùng HTTP HEAD.
# Server có thể không hỗ trợ HEAD, khi đó cần kiểm tra cách khác.
curl --head --silent --show-error --max-time 5 \
  https://app.example.test/

# Trong lab, ánh xạ hostname tới IP được phép nhưng vẫn dùng
# hostname để kiểm tra TLS SNI và certificate verification.
curl --head --silent --show-error --max-time 5 \
  --resolve app.example.test:443:192.0.2.10 \
  https://app.example.test/
~~~

Các trường đáng chú ý: status, `Server`, `Via`, `Location`, `Strict-Transport-Security` (khi có), cookie flags, `WWW-Authenticate` và dấu hiệu proxy/WAF. Tuy vậy, **một header không đáng tin như nguồn duy nhất của version**: banner có thể bị thay đổi, proxy trả thay, hoặc cấu hình ẩn thông tin.

Một HTTP `403` hoặc `401` không có nghĩa host không có dịch vụ; nó cho thấy endpoint xử lý request và áp dụng một cơ chế chặn/xác thực nào đó. Không tiếp tục bằng credential guessing để “lấy cho được 200” nếu mục tiêu chỉ là enumeration.

### 8.2. TLS fingerprinting và chứng chỉ

~~~bash
# Quan sát TLS handshake và certificate ở FQDN đã được duyệt.
openssl s_client \
  -connect app.example.test:443 \
  -servername app.example.test \
  -verify_return_error \
  -verify_hostname app.example.test \
  </dev/null
~~~

Các tín hiệu gồm TLS protocol/cipher được đàm phán, server certificate, chain, SAN, thời hạn, issuer, public-key algorithm và ALPN. **SNI rất quan trọng** trên host có nhiều ứng dụng; kiểm tra IP trực tiếp mà không truyền SNI có thể nhận chứng chỉ mặc định không đại diện cho FQDN cần đánh giá.

TLS fingerprint (ví dụ đặc tính ClientHello/ServerHello) có thể hỗ trợ nhận diện công nghệ nhưng thay đổi theo phiên bản thư viện, proxy, LB, policy TLS và thiết bị trung gian. JA3 chủ yếu mô tả **ClientHello của phía client**, nên không được lấy JA3 của trình duyệt làm bằng chứng trực tiếp cho phiên bản server. Các fingerprint server-side cũng là suy luận; nhiều triển khai có thể trùng mẫu và cấu hình có thể thay đổi.

Không dùng `curl -k` hoặc tùy chọn tắt xác minh certificate để “qua được lỗi” rồi kết luận kết nối an toàn. Nếu cert validation fail, đó chính là một phát hiện cần xác minh: hostname, trust chain, expiry, đồng hồ client hoặc TLS interception.

### 8.3. SSH banner và host key

SSH server thường gửi một dòng nhận diện phiên bản giao thức và có thể có thông tin triển khai. Ngoài ra, host key fingerprint hỗ trợ xác định endpoint đã thay đổi hay chưa.

~~~bash
# Thu public host key từ endpoint đã được cho phép.
# Đầu ra chỉ phục vụ kiểm kê, chưa được coi là key đã xác thực.
ssh-keyscan -T 5 -p 22 192.0.2.10

# So với bản ghi host key đã được tổ chức xác minh độc lập;
# không tự động chấp nhận key mới khi khác fingerprint.
~~~

`ssh-keyscan` **không xác minh danh tính máy chủ**; một attacker MITM có thể trình host key khác. Cần đối chiếu fingerprint với inventory/CA hoặc kênh tin cậy. Một banner `OpenSSH_...` có thể là bản tự biên dịch, backport patch hoặc đã bị cấu hình thay đổi, nên không suy CVE chỉ từ số phiên bản.

### 8.4. DNS, proxy và virtual host

DNS enumeration an toàn trong phạm vi có thể xem thông tin A/AAAA/CNAME/SRV/TXT được công bố hoặc cho phép truy vấn; không mặc định truy vấn zone transfer, liệt kê account/service nội bộ hay thu lượng lớn record khi chưa được duyệt.

Một reverse proxy có thể trả các ứng dụng khác nhau theo **Host header** và **TLS SNI**. Khi báo cáo một dịch vụ web phải ghi đủ FQDN, đích IP/port, scheme HTTP/HTTPS và nguồn thử; `443/tcp open` không tương đương “đã liệt kê mọi ứng dụng trên IP”.

## 9. Fingerprinting hệ điều hành, thiết bị và phần mềm

**Service fingerprinting** thường kết hợp:

- Banner/greeting/response code.
- Trường protocol và feature negotiation.
- TLS phiên bản, bộ thuật toán và ALPN.
- Kiểu HTTP response, headers, redirect, cookie/challenge.
- SSH identification, host-key algorithms và extensions.
- Format lỗi, thứ tự header, response trước input không hợp lệ **trong phạm vi kiểm thử an toàn**.
- Metadata từ inventory, cloud tags, cấu hình controller hoặc phiên bản package được xác minh trên host.

**OS/device fingerprinting** đôi khi suy luận từ TCP/IP stack: TTL ban đầu ước lượng, TCP window, MSS/options, thứ tự options, phản ứng với gói đặc thù, ICMP behavior. Nhưng các dấu hiệu đó bị ảnh hưởng bởi NAT, load balancer, proxy, firewall, hệ điều hành đã tuning và cả hệ thống gửi/nhận khác nhau.

| Bằng chứng | Có thể hỗ trợ | Không đủ để khẳng định |
|---|---|---|
| HTTP `Server: nginx` | Có proxy/server tự giới thiệu là Nginx | Backend OS, patch level, có lỗ hổng |
| SSH banner `OpenSSH_X.Y` | Dấu hiệu một triển khai SSH | Package build, backported fixes, CVE thực sự áp dụng |
| TLS certificate SAN | Danh sách tên mà chứng chỉ được cấp cho | Tất cả tên đó đều có dịch vụ đang hoạt động |
| TCP TTL/options | Đặc điểm stack tại điểm quan sát | OS chính xác khi có trung gian |
| SNMP sysDescr (khi được phép) | Model/OS do thiết bị khai báo | Tính xác thực nếu cấu hình/agent đã bị sửa |
| Cloud API inventory | Loại instance, image, phiên bản phần mềm theo metadata | Chính xác tuyệt đối về trạng thái runtime/sidecar |
| Package inventory và vendor advisory | Build thật, patch/backport liên quan | Rủi ro khai thác trong bối cảnh cụ thể nếu chưa kiểm chứng |

### 9.1. Sử dụng mức độ tin cậy

Một hệ thống báo cáo nên phân loại:

- **Confirmed:** xác nhận qua nhiều nguồn độc lập hoặc nguồn quản trị đáng tin, ví dụ `rpm/dpkg`, image digest và change record trên host được phép, kết hợp handshake.
- **High confidence:** phản hồi protocol khớp nhiều đặc điểm và inventory phù hợp, chưa có bằng chứng xác thực bản build.
- **Tentative:** banner hoặc fingerprint đơn lẻ gợi ý sản phẩm/phiên bản.
- **Unknown:** không đủ dữ kiện, kết quả bị proxy/filter/timeout hoặc nguồn có thể bị giả mạo.

Trong báo cáo, viết “Server header gợi ý Nginx” thay vì “máy chạy Nginx phiên bản X có CVE Y” nếu chưa xác minh bản build thực tế. Có thể yêu cầu asset owner đối chiếu package/firmware, vì nhiều nhà cung cấp backport bản vá bảo mật mà giữ version string cũ.

### 9.2. Vì sao scan nhận diện OS hay sai?

OS detection chủ động thường cần nhiều kiểu phản hồi, lý tưởng có ít nhất cổng mở và đóng để so sánh dấu vân tay; proxy/WAF/LB có thể can thiệp. Một số kiểu probe dùng raw sockets và cần đặc quyền; trên mạng production nhạy cảm không nên bật chỉ vì muốn một tên OS đẹp trong report.

Cần ghi “OS suspected” hoặc “indeterminate”, đặc biệt với thiết bị mạng, appliance chuyên dụng, container, host sau NAT, service mesh và đích được bảo vệ bằng firewall.

## 10. Kiểm thử theo lớp phòng vệ và vị trí

Một phép enumeration tạo kết quả của **đường đi từ nguồn thử tới đích**. Kiểm thử network security cần đặt nguồn phù hợp với mục tiêu phân đoạn.

### 10.1. Ma trận reachability mong đợi

Ví dụ chính sách giả định:

| Nguồn | Đích | Cổng được phép | Kỳ vọng |
|---|---|---|---|
| Bastion trong management zone | Switch management | 22/tcp | SSH mở với danh tính đúng |
| User VLAN | Switch management | Không | Không truy cập trực tiếp cổng quản trị |
| App subnet | Database | 5432/tcp | Chỉ ứng dụng được phép kết nối |
| Guest Wi-Fi | Corporate DNS internal | Không | Không thể đọc dịch vụ DNS nội bộ |
| VPN admin group | Firewall management UI | 443/tcp theo policy | Có HTTPS và kiểm tra danh tính/RBAC |
| Internet ngoài tổ chức | Internal admin API | Không | Không công khai endpoint |
| Monitoring segment | Network device | 161/udp theo policy | SNMPv3 authPriv, quyền đọc giới hạn |

Tất cả dòng trên là **ví dụ kiểm thử**, không phải chính sách mặc định cho mọi mạng. Thử từ mỗi vùng bằng tài khoản/máy đại diện đã phê duyệt; kiểm tra cả IPv4/IPv6 và các route OOB/backup nếu có.

### 10.2. Các kết luận cần đối chiếu

- **Thấy open từ user VLAN khi policy nói deny:** xác minh IP/route và firewall hit logs, NAT, alternate interface, ACL precedence và cơ chế quản trị chạy trên interface khác.
- **Thấy filtered từ bastion khi policy nói allow:** có thể firewall chặn, route sai, host down hoặc sensor/probe bị giới hạn; không vội tắt ACL.
- **TLS certificate khác mong đợi:** có thể sai SNI, chuyển backend, thay certificate, interception hoặc nhầm đích.
- **Nhiều nguồn thử đều thấy giống nhau:** tăng độ tin cậy nhưng vẫn phải kiểm tra kết nối qua cùng middlebox hay không.
- **Sau migrate thiết bị, port cũ còn mở:** có thể là proxy/vhost, service chưa tắt, IPv6 quên cấu hình hoặc đường quản trị phụ.

Mạng cloud thường có nhiều lớp policy: security group, network ACL, route table, private endpoint, load balancer, Kubernetes NetworkPolicy hoặc service mesh authorization. Enumeration từ một VM không tự kiểm chứng mọi lớp; cần đối chiếu control plane và telemetry.

## 11. Không làm gián đoạn dịch vụ trong lúc kiểm thử

Một số thiết bị mạng, hệ thống nhúng hoặc dịch vụ cũ có thể không chịu được nhiều kết nối/hội thoại bất thường. Ngay cả probe nhẹ cũng có thể tạo log lớn hoặc kích hoạt rate limit. Do đó:

1. **Thử lab/staging trước** khi chưa biết ảnh hưởng.
2. Giảm số host, số cổng, tần suất, retry và đồng thời; đặt stop condition cụ thể.
3. Tránh probe trạng thái đăng nhập, brute force, thử mật khẩu mặc định, thay cấu hình hoặc kiểm tra khả năng khai thác nếu chỉ được giao enumeration.
4. Hạn chế active probes tới OT/IoT, VPN concentrator, firewall/IPS, controller nhạy cảm; phối hợp vendor và owner.
5. Theo dõi CPU, RAM, session tables, response latency, IDS/IPS alerts và packet drops.
6. Ghi nguồn scanner và change ID để SOC phân biệt test hợp lệ với hoạt động đáng ngờ.
7. Nếu bất kỳ triệu chứng gián đoạn nào xuất hiện, dừng kiểm thử, thông báo owner và giữ log/capture cần thiết.

**Ranh giới quy trình:** phát hiện được service mới không tự động cho phép đăng nhập, dò account, tải dữ liệu hay thử khai thác. Những bước đánh giá sâu phải có phạm vi/phê duyệt riêng.

### 11.1. Bảo vệ bằng chứng thu được

Banner đôi khi chứa username, đường dẫn hệ thống, tenant ID, tên nội bộ, phiên bản và thông tin cấu hình. Kết quả enumeration cần được phân loại phù hợp; không đẩy các output nhạy cảm lên issue tracker công khai hay kênh chat rộng quyền.

Nên ghi hash cho output cuối sau khi file ổn định, lưu với incident/test ID; người có quyền có thể tái lập lệnh theo phương pháp đã ghi. Nếu chuyển output giữa nhóm, giữ đường dẫn tới kho bảo vệ, danh tính người nhận, thời điểm và phiên bản.

## 12. Workflow kiểm thử có thể tái lập

~~~mermaid
flowchart TD
    A["Scope + authorization + baseline"] --> B["Thu asset inventory và telemetry"]
    B --> C["Chọn nguồn kiểm thử và cửa sổ phù hợp"]
    C --> D["Khảo sát TCP/UDP giới hạn"]
    D --> E["Service enumeration theo giao thức"]
    E --> F["Fingerprinting có mức độ tin cậy"]
    F --> G["Đối chiếu config, vendor, asset owner"]
    G --> H["Finding: exposure, owner, evidence, risk"]
    H --> I["Hardening hoặc exception được duyệt"]
    I --> J["Re-test từ cùng các vùng nguồn"]
    J --> K["Lưu kết quả, so baseline và theo dõi drift"]
~~~

### 12.1. Thu thập bằng chứng nhất quán

Cho mỗi phép thử, tối thiểu lưu:

~~~yaml
test_id: NST-2026-004
authorized_scope:
  source_zone: "management-lab"
  target: "192.0.2.10"
  allowed_tcp_ports: [22, 80, 443]
  allowed_udp_ports: [53]
  time_window_utc: "2026-11-28T04:00:00Z/2026-11-28T04:15:00Z"
  purpose: "Xác minh bề mặt dịch vụ của thiết bị thử nghiệm"
evidence:
  scanner: "nmap"
  command_ref: "lab-runbook/nst-004-command"
  output_ref: "secure-evidence/NST-2026-004/service-check.txt"
  sha256: "<tính khi file đã ổn định>"
  notes: "Ví dụ giả định; kiểm tra packet drop và rate limit"
finding:
  endpoint: "192.0.2.10:443/tcp"
  observed_state: "open"
  suggested_protocol: "HTTPS via reverse proxy"
  confidence: "medium"
  corroboration_needed: "certificate, app owner, config"
owner_role: "network-security"
~~~

Thông tin này là **mẫu record**, không phải kết quả quét có thật. Trường `observed_state` phải đi kèm nguồn thử và thời gian; tránh ghi trạng thái cổng như thuộc tính không đổi của asset.

### 12.2. Từ dữ liệu thô tới finding

Một finding hữu ích nên gồm:

| Trường | Ví dụ |
|---|---|
| Asset | `switch-branch-01`, owner Network Operations |
| Quan sát | `23/tcp open` từ `user-vlan` trong giờ kiểm thử |
| Phương pháp | TCP connect + banner đối chiếu log, time range UTC |
| Kỳ vọng baseline | Management plane chỉ qua bastion SSH |
| Chứng cứ | Output đã hash, firewall log ref, config snapshot ref |
| Độ tin cậy | Cao cho reachability, chưa xác định đầy đủ ACL đường khác |
| Rủi ro | Telnet plaintext có thể tiết lộ credential/lệnh; user VLAN tiếp cận trực tiếp |
| Khuyến nghị | Migrate sang SSH, giới hạn management ACL, tắt Telnet sau khi kiểm tra |
| Validation | Kiểm tra lại từ user VLAN và bastion; test cả IPv4/IPv6 |
| Trạng thái | Open/mitigated/verified, người chịu trách nhiệm và hạn |

Dựa trên kết quả này, vulnerability management có thể yêu cầu xem bản build/firmware, cấu hình xác thực và chính sách cập nhật. **Không tự gán CVE chỉ vì một banner**.

## 13. Case study: phát hiện dịch vụ quản trị lộ ngoài vùng cho phép

### 13.1. Bối cảnh giả định

Một chi nhánh có router và switch, firewall phân đoạn user VLAN, guest Wi-Fi, VPN admin và management VLAN. Chính sách hiện tại yêu cầu quản trị qua SSH hoặc HTTPS từ bastion. Sau thay đổi thiết bị, đội kiểm thử được giao xác nhận bề mặt quản trị của một switch trong lab tích hợp.

### 13.2. Các quan sát

| Điểm thử | Endpoint | Quan sát | Diễn giải ban đầu |
|---|---|---|---|
| Bastion | `192.0.2.10:22/tcp` | Open, trả SSH banner | SSH reachable theo thiết kế |
| User VLAN | `192.0.2.10:22/tcp` | Filtered | Có dấu hiệu ACL hoạt động, cần firewall log xác nhận |
| User VLAN | `192.0.2.10:23/tcp` | Open, banner Telnet | Vi phạm mục tiêu loại bỏ plaintext management |
| Guest Wi-Fi | `192.0.2.10:443/tcp` | Không nhận phản hồi | Chưa xác định do lọc hay route |
| Bastion | `app.example.test:443/tcp` | HTTPS, cert hợp lệ | Cần xác định endpoint thuộc proxy hay switch UI |

Dữ liệu là minh họa. Phép thử cần được ghi rõ địa chỉ **sau NAT**, DNS/IPv6 và source interface thực tế.

### 13.3. Phân tích cùng owner

- Cấu hình switch cho thấy Telnet còn bật trên interface management; management ACL áp dụng thiếu một zone.
- Firewall policy hit logs xác nhận session từ user VLAN đi vào cổng 23.
- Thiết bị có hỗ trợ SSH host key/AAA; nhóm Network kiểm tra đường console/OOB trước migration.
- Nguồn `app.example.test` có reverse proxy; HTTPS certificate của proxy không đủ để khẳng định firmware trên switch.
- Một collector còn dùng SNMPv2c; cần xử lý phụ thuộc trước khi tắt cộng đồng cũ.

### 13.4. Khắc phục và re-test

1. Bật/quản lý SSH và AAA với quyền và audit phù hợp; xác minh host key từ inventory tin cậy.
2. Cập nhật ACL management zone cho IPv4/IPv6; rollout theo đợt và chuẩn bị rollback/OOB.
3. Chuyển collector sang SNMPv3 authPriv, xác minh telemetry.
4. Tắt Telnet và SNMPv2c khi phụ thuộc đã chuyển xong.
5. Kiểm tra lại từ bastion, user VLAN, guest Wi-Fi và nguồn VPN admin; so sánh output cùng phương pháp trước/sau.
6. Ghi service owner, config change, bằng chứng firewall logs và trạng thái verified.

**Bài học:** enumeration đã xác minh **sự lộ diện của một đường quản trị**; fingerprinting chỉ hỗ trợ mô tả công nghệ. Quyết định ưu tiên dựa vào quyền truy cập thực, cấu hình plaintext, khả năng chiếm quản trị và tài sản bị ảnh hưởng.

## 14. Đánh giá độ tin cậy và xử lý kết quả mâu thuẫn

Khi các nguồn dữ liệu không trùng nhau, không chọn một câu trả lời tùy tiện. Một số tình huống:

### 14.1. Nmap báo cổng mở nhưng inventory ghi đã tắt

Khả năng gồm config drift, service tự bật lại, port forwarding, proxy, virtual host, lỗi inventory hoặc IP bị tái sử dụng. Xác minh owner/asset identity, network path, config effective, banner/host key và change logs. Không lập tức gọi là “dịch vụ trái phép” nếu chưa phân định endpoint.

### 14.2. Banner ghi phiên bản lỗi thời nhưng owner nói đã vá

Có thể vendor backport bản vá, banner bị cố định/giả, proxy trả header khác hoặc owner chưa cập nhật kiểm kê. Yêu cầu package/firmware build, patch history và vendor advisory. Báo cáo tách **version observed** khỏi **version verified** và CVE applicability.

### 14.3. TCP báo filtered từ một vùng nhưng open từ vùng khác

Kết quả có thể phản ánh segmentation đúng kỳ vọng, nhưng cũng có route, DNS, ACL, NAT hoặc health-check thay đổi. Kiểm tra nguồn/đích chính xác, thời gian, firewall logs và quy tắc ở mọi interface liên quan.

### 14.4. UDP báo open|filtered, không có log ở server

Không đủ bằng chứng nói UDP service tồn tại hay bị chặn ở đúng firewall. Có thể probe không hợp lệ, log bị lấy mẫu, route bất đối xứng, ICMP rate limit, hoặc sensor không quan sát đường đi. Cần kiểm tra protocol query hợp lệ có kiểm soát, config server và telemetry.

### 14.5. TLS trả chứng chỉ không khớp hostname

Kiểm tra SNI, FQDN, DNS mapping, load balancer, CA/trust, cert rotation và thời gian máy. Lỗi này là phát hiện cấu hình cần phân định nguyên nhân, không nên bỏ xác minh để làm phép thử “thành công”.

## 15. Kiểm tra trước/sau hardening

Mục tiêu không chỉ là tìm dịch vụ. Cần chứng minh thay đổi đã thu hẹp bề mặt bị lộ mà vẫn bảo toàn dịch vụ hợp lệ.

| Kịch bản | Trước hardening | Kỳ vọng sau hardening |
|---|---|---|
| SSH từ bastion | Open | Open, host key xác minh, AAA và audit hoạt động |
| Telnet từ user VLAN | Có thể open | Không còn khả năng truy cập |
| HTTPS management từ guest | Có thể mở do ACL sai | Không reachable theo policy |
| TLS tới admin UI từ nguồn hợp lệ | Version/cert không đạt baseline | Certificate/hostname và TLS policy đúng |
| SNMPv2c | Collector còn dùng | Collector chuyển sang SNMPv3 authPriv; v1/v2c tắt |
| Cổng debug/database từ subnet không cần thiết | Open/filtered tùy config | Không truy cập ngoài đường được phép |
| IDS/IPS giám sát scan hợp lệ | Có thể tạo alert | SOC nhận diện đúng test ID, logging hoạt động |
| IPv6 management | Chưa đánh giá | Policy tương đương IPv4 khi cần |

Giữ điều kiện re-test nhất quán: cùng nguồn, host/endpoint, cổng, giao thức, công cụ hoặc phương pháp tương đương, time window có ghi và kết quả log. Khi một phần dịch vụ dùng dynamic cloud IP hoặc load balancer, cần quy kết theo asset identity và FQDN, không chỉ so IP.

Sau khi hardening, nếu đường SSH từ bastion bị đóng cùng với Telnet, đó là **regression về vận hành**, không phải thành công của việc giảm số cổng mở. Phải xác minh các đường quản trị thiết yếu, dịch vụ nghiệp vụ và phục hồi OOB/rollback.

## 16. Những ngộ nhận thường gặp

1. **“Ping không trả lời nên host không tồn tại.”** ICMP có thể bị chặn; vẫn có TCP/UDP service hoặc host trong network.
2. **“Port 443 mở nghĩa là HTTPS an toàn.”** Có thể là TLS sai cấu hình, proxy hoặc protocol khác; cần xác minh certificate và access control.
3. **“Cổng 22 mở là lỗ hổng.”** SSH có thể là đường quản trị hợp lệ, được hạn chế đúng nguồn, identity và cấu hình.
4. **“Server banner là bản build chính xác.”** Banner có thể bị che, sửa, proxy hoặc giữ version cũ sau backport.
5. **“UDP không phản hồi nghĩa là closed.”** UDP có thể bỏ qua probe và công cụ thường trả open|filtered.
6. **“Nmap kết luận hệ điều hành X nên chắc chắn đúng.”** Stack signature bị ảnh hưởng bởi thiết bị trung gian và nhiều OS dùng đặc điểm giống nhau.
7. **“Một scan từ Internet kiểm chứng xong phân đoạn nội bộ.”** Mỗi vùng nguồn có route/ACL khác.
8. **“Dịch vụ không xuất hiện trên TCP port chuẩn tức không chạy.”** Có thể chạy ở cổng khác, qua tunnel, UDP/QUIC hoặc proxy.
9. **“Có CVE theo banner nên được phép thử khai thác.”** Kiểm chứng CVE và exploit thuộc bước/phạm vi khác, cần phê duyệt.
10. **“Không có packet ở PCAP tức không có traffic.”** Sensor/filter/drop/offload hoặc đường bất đối xứng có thể làm thiếu dữ liệu.
11. **“Quét càng nhanh càng tốt.”** Tăng cường độ có thể làm sai dữ liệu, gây load, false alert và gián đoạn.
12. **“Xóa banner sẽ giải quyết toàn bộ rủi ro.”** Giảm disclosure là biện pháp phụ; cần vá, hardening, IAM và segmentation.
13. **“Lỗi TLS certificate có thể bỏ qua vì đang test.”** Tắt verify che mất một rủi ro quan trọng.
14. **“Không cần lưu nguồn scan hay timestamp.”** Không thể giải thích vì sao hai lần kiểm thử khác nhau khi chính sách và đường đi thay đổi.

## 17. Checklist vận hành

### Trước khi kiểm thử

- [ ] Có scope, tài sản/owner, nguồn thử, cửa sổ và người phê duyệt.
- [ ] Xác định mục tiêu: service exposure, fingerprint, phân đoạn, TLS/SSH/SNMP hay drift.
- [ ] Có baseline/inventory và danh sách cổng/giao thức cần thử.
- [ ] Đã xem nguồn passive phù hợp trước; có lý do cho probe chủ động.
- [ ] Đã đánh giá thiết bị nhạy cảm, giới hạn rate/retry/parallelism, stop condition.
- [ ] Thông báo SOC/on-call theo quy trình, chuẩn bị nơi lưu output được bảo vệ.

### Trong khi kiểm thử

- [ ] Ghi UTC, nguồn scan, IP/FQDN/SNI, port/protocol, tool/version và command.
- [ ] Phân biệt `open`, `closed`, `filtered`, `open|filtered`.
- [ ] Diễn giải banner/headers/cert/host key là dấu hiệu, không tuyệt đối.
- [ ] Kiểm tra SNMP/DNS/TLS/HTTP theo giao thức hợp lệ và quyền đã duyệt.
- [ ] Theo dõi service health, packet loss, SOC alerts và phản ứng của mục tiêu.
- [ ] Không thử mật khẩu, phá dịch vụ hay thay cấu hình ngoài RoE.
- [ ] Xác nhận đường VPN, firewall/NAT, LB/proxy, IPv4/IPv6 ảnh hưởng kết quả.

### Khi tổng hợp và re-test

- [ ] Gắn mỗi kết luận với điểm quan sát, nguồn bằng chứng và mức tin cậy.
- [ ] So kết quả với config/CMDB/vendor build trước khi gán vulnerability.
- [ ] Có owner, impact, remediation, acceptance criteria và hạn xử lý.
- [ ] Re-test trước/sau cùng điều kiện hoặc ghi rõ khác biệt.
- [ ] Đã chứng minh dịch vụ hợp lệ vẫn hoạt động và OOB/rollback có thể dùng.
- [ ] Output và log có phân loại, checksum, quyền truy cập, retention phù hợp.
- [ ] Ghi phần chưa xác minh, ngoại lệ, rủi ro tồn đọng và kỳ review tiếp.

## 18. Câu hỏi tự kiểm tra

**1. Service enumeration khác port scanning ở điểm nào?**

Port scanning quan sát trạng thái cổng ở một đường truy cập; enumeration đi sâu vào giao thức và chức năng service, ví dụ handshake, HTTP headers hoặc DNS response để mô tả endpoint.

**2. Nmap thấy `161/udp open|filtered`. Có thể khẳng định SNMP đang chạy không?**

Chưa. Đó là trạng thái không phân biệt được cổng mở hay bị lọc; cần protocol response hợp lệ, cấu hình và log/counters khi được phép.

**3. Banner cho biết OpenSSH phiên bản X. Có thể lập tức gán một CVE cho host không?**

Không. Cần xác minh package/firmware build, backport patch, điều kiện cấu hình, quyền truy cập và advisory áp dụng; banner có thể giả hoặc do trung gian.

**4. Quét HTTPS theo IP và thấy chứng chỉ khác với domain dự kiến. Nguyên nhân có thể là gì?**

Thiếu SNI, default certificate của LB/proxy, DNS/CDN mapping, cert chưa đúng SAN/chain hoặc nhầm endpoint. Thử lại theo FQDN và xác minh chain/hostname trong phạm vi đã duyệt.

**5. Vì sao phải kiểm thử từ cả bastion và user VLAN?**

Vì reachability phụ thuộc nguồn. SSH mở từ bastion có thể đúng chính sách, còn mở từ user VLAN là vi phạm phân đoạn management plane.

**6. Nếu sau hardening mọi cổng quản trị đều filtered, đã thành công chưa?**

Chưa chắc. Cần kiểm tra đường quản trị hợp lệ qua bastion/OOB vẫn hoạt động, monitoring/automation còn chạy và audit đầy đủ; có thể đã tự khóa quản trị.

**7. Tại sao HTTP `Server` header không phải bằng chứng về OS của máy backend?**

Header có thể được reverse proxy, CDN/WAF hoặc ứng dụng đặt tùy ý; một IP có thể có nhiều backend và virtual host.

**8. Tại sao không nên dùng mặc định các bài scan có nhiều probe trên thiết bị OT/IoT hoặc firewall cũ?**

Một số thiết bị có tài nguyên hạn chế và bộ xử lý giao thức không chịu được lưu lượng bất thường; kiểm thử có thể gây tải hoặc gián đoạn. Cần thử lab, giảm scope/cường độ và phối hợp owner.

**9. Fingerprinting có làm thay công việc xác minh vulnerability không?**

Không. Fingerprinting cung cấp dấu hiệu công nghệ hoặc phiên bản; đánh giá lỗ hổng cần xác minh bản build, cấu hình, đường truy cập, biện pháp giảm thiểu và điều kiện bị ảnh hưởng.

---

**Ghi nhớ:** Kiểm thử **service enumeration và fingerprinting** giúp thấy sự khác biệt giữa **dịch vụ dự kiến** và **bề mặt mạng thực sự quan sát được**. Chỉ coi kết quả có giá trị khi gắn với nguồn kiểm thử, phương pháp, thời gian, mức tin cậy và bằng chứng bổ trợ; rồi dùng chúng để kiểm tra segmentation, hardening, giảm exposure và xác nhận hiệu quả sau khắc phục.
