# Port scanning an toàn và có kiểm soát

## 1. Tại sao phải quét cổng khi kiểm thử bảo mật mạng?

**Port scanning** là hoạt động gửi những gói hoặc yêu cầu kết nối có chủ đích tới các cổng mạng của một đích nhằm xác định trạng thái có thể quan sát được của từng cổng từ một vị trí mạng cụ thể. Đây là một kỹ thuật **kiểm thử bề mặt phơi lộ dịch vụ (network exposure)**, không đồng nghĩa khai thác lỗ hổng và cũng không tự chứng minh ứng dụng phía sau cổng đang an toàn.

Trong chương **Kiểm thử và xác minh bảo mật mạng** của mô-đun **SECURITY_NETWORK_SECURITY**, quét cổng được dùng để kiểm tra hiệu lực của phân đoạn mạng, firewall, VPN, IDS/IPS, chính sách truy cập, DNS, mạng không dây và tài nguyên cloud. Ví dụ, sau khi triển khai một firewall rule chỉ cho phép HTTPS tới API gateway, nhóm network có thể kiểm tra từ từng vùng tin cậy rằng cổng 443 hoạt động, trong khi cổng quản trị 22 không được phép truy cập từ Internet.

Một cuộc quét tốt trả lời những câu hỏi có thể kiểm chứng:

- Một IP hoặc hostname **thực sự có cổng TCP/UDP nào tiếp cận được từ điểm kiểm thử**?
- Những cổng quản trị hoặc dịch vụ nội bộ có bị phơi lộ ra zone không phù hợp không?
- Quy tắc firewall/ACL hoặc cloud security group có hoạt động như thiết kế không?
- Một thay đổi cấu hình làm mở thêm cổng, đóng nhầm cổng hay thay đổi đường đi không?
- Khác biệt giữa các góc nhìn Internet, mạng nội bộ, VPN và Wi-Fi khách là gì?

**Ranh giới bắt buộc:** chỉ thực hiện quét trên hệ thống có quyền kiểm thử rõ ràng, trong đúng phạm vi, khung giờ và giới hạn đã được phê duyệt. Kể cả thao tác chỉ mở TCP connection cũng có thể ảnh hưởng thiết bị cũ, dịch vụ nhạy cảm hoặc hệ thống chống xâm nhập.

Sau bài học, người học có thể xây dựng kế hoạch quét có kiểm soát, lựa chọn kỹ thuật ít tác động, đọc đúng kết quả, xác minh độc lập và báo cáo bằng chứng mà không nhầm trạng thái cổng với kết luận về lỗ hổng.

## 2. Port, socket và service: hiểu đúng đối tượng đang đo

Trong TCP/IP, **port** là một trường 16 bit ở tầng transport, giúp phân biệt điểm cuối giao tiếp trong phạm vi địa chỉ IP và giao thức. TCP và UDP có không gian cổng riêng; TCP/53 và UDP/53 là hai trường hợp khác nhau. Một socket hoặc flow thường được mô tả bằng **5-tuple** gồm IP nguồn, port nguồn, IP đích, port đích và protocol.

| Khái niệm | Ví dụ | Điều cần nhớ |
| --- | --- | --- |
| Port đích | TCP/443, TCP/22, UDP/53 | Số port không bảo đảm giao thức ứng dụng đúng như tên phổ biến |
| Listening service | Tiến trình lắng nghe TCP/8443 | Có listener chưa chắc đi tới được từ mọi zone |
| Network path | Client → Firewall → Load balancer → Server | Kết quả phụ thuộc điểm xuất phát và các policy trung gian |
| Exposed service | TCP/443 được truy cập từ mạng khách | Cần đối chiếu thiết kế truy cập và owner |
| Application security | TLS, authentication, authorization, patch level | Không thể xác định đầy đủ chỉ bằng trạng thái cổng |
| Local-only binding | Listener trên 127.0.0.1 | Có thể xuất hiện trong host inventory nhưng không truy cập qua NIC ngoài |

Quét cổng có thể xác nhận **khả năng giao tiếp tại điểm quét**, nhưng không thay thế kiểm toán cấu hình, xác minh danh tính dịch vụ hoặc kiểm thử ứng dụng.

### 2.1. Các trạng thái thường gặp trong Nmap

| Trạng thái | Cách hiểu thực tế | Không nên suy diễn |
| --- | --- | --- |
| **open** | Probe nhận phản hồi phù hợp với cổng đang chấp nhận kết nối hoặc giao thức | Dịch vụ không có lỗ hổng, hoặc backend chính là máy đã quét |
| **closed** | Đích/thiết bị trung gian trả phản hồi từ chối phù hợp; ví dụ TCP RST | Máy không có dịch vụ ở mọi interface hay mọi thời điểm |
| **filtered** | Không đủ phản hồi hoặc có tín hiệu chặn, khiến công cụ không xác định open/closed | Chắc chắn một firewall cụ thể đã chặn |
| **unfiltered** | Trạng thái lọc xác định bằng loại probe nhất định nhưng chưa kết luận open/closed | Cổng chắc chắn đang mở |
| **open|filtered** | Không phân biệt được đang mở hay bị lọc, thường gặp ở UDP | UDP service chắc chắn đang chạy |
| **closed|filtered** | Không đủ thông tin phân biệt hai trạng thái ở một số phương pháp | Đích chắc chắn đã đóng |

Ý nghĩa và trạng thái khả dụng phụ thuộc **loại scan và cách phản hồi**. Ví dụ TCP connect scan nhận một kết nối thành công có thể đánh dấu open; UDP không trả lời có thể được ghi open|filtered vì nhiều dịch vụ UDP im lặng khi nhận payload không phù hợp.

## 3. Giới hạn pháp lý, phạm vi và Rules of Engagement (RoE)

**RoE** là thỏa thuận vận hành quy định chính xác hoạt động nào được phép, ở đâu, khi nào và ai chịu trách nhiệm. Không nên bắt đầu chỉ vì một IP xuất hiện trong tài liệu hay công ty có vẻ sở hữu domain. Một tài sản có thể thuộc nhà cung cấp cloud, đối tác, CDN hoặc bên thứ ba có chính sách kiểm thử riêng.

### 3.1. Những câu hỏi phải có câu trả lời trước khi quét

1. **Ai phê duyệt?** Chủ sở hữu hệ thống, nhóm security/network, người điều phối thay đổi và đơn vị thứ ba nếu áp dụng.
2. **Tài sản nào được phép?** Danh sách IP, hostname, subnet, interface, tenant, cluster hoặc instance ID; nêu rõ loại trừ.
3. **Từ đâu được phép?** Source IP/zone, VPN, jump host hoặc điểm kiểm thử cloud; thiết lập quyền truy cập và ghi log.
4. **Kỹ thuật nào?** TCP connect, kiểm tra cổng cụ thể, UDP có kiểm soát, service detection hay chỉ đọc cấu hình.
5. **Lưu lượng tối đa?** Số đích đồng thời, số cổng, tốc độ probe, thời gian mỗi host, retry và cửa sổ maintenance.
6. **Khi nào phải dừng?** Ứng dụng báo lỗi tăng, IDS/IPS alert nghiêm trọng, CPU tăng, packet drop hoặc yêu cầu từ người phụ trách.
7. **Ai nhận thông báo?** NOC/SOC/on-call, kênh escalation, thời điểm bắt đầu/dừng và danh tính nguồn quét.
8. **Dữ liệu được giữ thế nào?** File output, log, timestamp, địa chỉ và dữ liệu nhận diện dịch vụ; quyền xem, retention và đường truyền.

Một mẫu RoE gọn:

| Mục | Ví dụ được phê duyệt |
| --- | --- |
| Mã kiểm thử | CHG-EXAMPLE-1042 |
| Mục tiêu | Xác minh chỉ TCP/443 mở từ VLAN ứng dụng tới API gateway |
| Tài sản | 192.0.2.10, một địa chỉ thử nghiệm đã được chỉ định |
| Nguồn | Scanner ở VLAN TEST, IP đã đăng ký với SOC |
| Trong phạm vi | TCP/22, 80, 443 và 8443 trên một host |
| Ngoài phạm vi | UDP diện rộng, script khai thác, brute-force, stress test |
| Thời gian | 02:00–02:20 UTC trong maintenance window |
| Giới hạn | Một host tại một thời điểm, probe rate thấp, retry hạn chế |
| Điều kiện dừng | Error rate tăng, báo động production, on-call yêu cầu |
| Người liên hệ | Network on-call và chủ sở hữu API |
| Bảo toàn kết quả | Output XML/text, UTC, command, phiên bản và change ticket |

Các địa chỉ 192.0.2.0/24, 198.51.100.0/24 và 203.0.113.0/24 trong bài là **dải dành cho tài liệu**, không phải đích quét thực tế; khi thực hành phải thay bằng tài sản lab hoặc tài sản đã cấp quyền.

### 3.2. Tài sản cần được đánh giá riêng

Không áp dụng cùng mức quét cho mọi hệ thống:

| Nhóm tài sản | Lưu ý |
| --- | --- |
| Server/VM thông thường | Quét tốc độ thấp theo RoE, theo dõi metrics và logs |
| Firewall/router/VPN appliance | CPU control plane, rate limit, IDS/IPS, cơ chế quản trị dễ bị ảnh hưởng |
| ICS/OT, medical, thiết bị mạng cũ | Có thể nhạy cảm với probe lạ; ưu tiên kiểm kê thụ động hoặc phê duyệt chuyên biệt |
| Cloud managed service | Phải tuân chính sách provider, tenant và quyền đối với dịch vụ do bên thứ ba sở hữu |
| Load balancer/CDN/WAF | Kết quả có thể phản ánh edge/VIP, không phản ánh origin |
| Kubernetes/service mesh | Lưu lượng qua service VIP, sidecar và policy khác với node interface |
| Wi-Fi/guest network | Ràng buộc 802.1X, client isolation, SSID, VLAN, NAC, controller policy |

Đặc biệt với hệ thống nhạy cảm, **không quét chủ động** nếu chưa có phương án được owner phê duyệt. Có thể bắt đầu từ configuration inventory, firewall log hoặc flow telemetry.

## 4. Mô hình tác động và kiểm soát tải

Port scan thực chất tạo traffic và có thể kích hoạt state tables, log pipeline, endpoint connection handlers, authentication policy hoặc IDS/IPS. Rủi ro tăng khi số đích, số port, retry và parallelism tăng.

| Yếu tố | Nguy cơ | Kiểm soát |
| --- | --- | --- |
| Quét cả dải IP lớn | Tạo nhiều session và log, ảnh hưởng thiết bị mạng | Khởi đầu từ allowlist IP chính xác và ít port |
| Retry cao khi filtered | Kéo dài traffic và tải trên firewall | Giới hạn retry, host-timeout và đánh giá lại thay vì ép phản hồi |
| Song song nhiều host/port | Tăng connection backlog, CPU, session table | Giới hạn concurrent hosts và probe rate |
| Service/version detection | Gửi payload ứng dụng không mong đợi | Chỉ dùng khi cần, được phép và trên port xác định |
| UDP scan | Dễ bị mất phản hồi, có thể kích hoạt dịch vụ thật | Chỉ port đã cho phép, ngắt sớm nếu có tác động |
| Script/automation không kiểm soát | Vượt phạm vi hoặc chạy vô hạn | Review command, dry-run kế hoạch, giới hạn thời gian |
| IDS/IPS/WAF phản ứng với scan | Block, rate limit hoặc false positive | Thông báo SOC, giám sát, không cố lách hoặc vô hiệu hóa |

Không tồn tại một tốc độ được bảo đảm "an toàn" cho mọi hệ thống. **Giới hạn 5 packet/giây cũng có thể gây rủi ro cho một thiết bị rất yếu hoặc sai giao thức.** Sử dụng mức khởi đầu thận trọng, tăng chỉ khi chủ hệ thống cho phép và quan sát được tác động.

## 5. Chọn kỹ thuật phù hợp

### 5.1. TCP connect scan

**TCP connect scan** sử dụng cơ chế connect của hệ điều hành để thử thiết lập TCP connection. Ưu điểm là hành vi dễ diễn giải, không cần raw packet privileges ở nhiều môi trường, phù hợp cho kiểm thử kết nối đến vài cổng đã được phê duyệt. Mỗi lần thử có thể tạo một session hoặc log trên hệ thống đích.

### 5.2. TCP SYN scan

**TCP SYN scan** quan sát phản hồi với SYN mà không cần hoàn tất kết nối theo cách TCP connect thông thường. Cách thực hiện phụ thuộc quyền raw socket và nền tảng; thiết bị bảo mật vẫn có thể ghi nhận, chặn hoặc bị ảnh hưởng. Trong bài về **quét có kiểm soát**, TCP connect thường là điểm khởi đầu dễ quản trị hơn. Không sử dụng kỹ thuật để né giám sát hay che nguồn.

### 5.3. UDP scan

UDP không có three-way handshake. Một UDP service hợp lệ có thể im lặng trước gói không đúng định dạng; một số lỗi ICMP có thể bị lọc hoặc giới hạn tốc độ. Vì thế UDP scan thường xuất hiện **open|filtered**. Khi cần xác minh DNS, NTP hoặc dịch vụ UDP khác, nên ưu tiên **truy vấn đúng giao thức với dữ liệu tối thiểu** do owner chấp thuận, thay vì dựa chỉ vào kết quả UDP scan diện rộng.

### 5.4. Service detection và OS fingerprinting

Quét service version có thể phát payload ở tầng ứng dụng; OS fingerprinting có thể dùng nhiều probe khác nhau. Hai loại này **khác với xác nhận cổng cơ bản**, có nguy cơ tác động cao hơn và đòi hỏi phạm vi/phê duyệt riêng. Không mặc định bật toàn bộ chế độ phát hiện chỉ để lấy một danh sách port.

| Phương án | Câu hỏi trả lời | Mức cân nhắc |
| --- | --- | --- |
| Đọc listener tại host | Tiến trình đang lắng nghe cổng nào? | Không kiểm chứng mạng từ xa |
| TCP connect trên cổng cụ thể | Đường tới port có thiết lập TCP không? | Khởi đầu phù hợp cho kiểm thử có phép |
| SYN scan có phép | Trạng thái phản hồi SYN ở góc nhìn scanner | Cần hiểu hành vi và quyền công cụ |
| UDP query đúng dịch vụ | Resolver/service có phản hồi hợp lệ không? | Chỉ khi biết giao thức và được phép |
| Service/version probe | Dịch vụ ứng dụng nào trả phản hồi? | Chỉ dùng khi cần bằng chứng nâng cao |
| Vulnerability scan | Có dấu hiệu cấu hình/yếu điểm đã biết không? | Phạm vi riêng, không đồng nhất với port scan |

## 6. Quy trình quét an toàn từ lập kế hoạch đến xác minh

~~~mermaid
flowchart TD
    A[Phê duyệt RoE và owner] --> B[Khóa danh sách IP, port, protocol, nguồn quét]
    B --> C[Kiểm tra health, backup và thời gian]
    C --> D[Chọn phương án ít tác động và mức rate thấp]
    D --> E[Quét một host và ít port đầu tiên]
    E --> F{Có cảnh báo hoặc tải bất thường?}
    F -->|Có| G[Dừng, lưu bằng chứng, thông báo on-call]
    F -->|Không| H[Đối chiếu listener, firewall, flow và ứng dụng]
    H --> I{Cần quét tiếp trong phạm vi?}
    I -->|Có| J[Tiếp tục từng nhóm nhỏ, theo dõi liên tục]
    J --> F
    I -->|Không| K[Tổng hợp kết quả, rủi ro và test lại]
~~~

### 6.1. Giai đoạn chuẩn bị

- Xác nhận IP thực tế của tài sản và mapping FQDN/DNS tại thời điểm kiểm thử.
- Lấy cấu hình firewall, ACL, cloud security group hoặc network policy dự kiến; ghi expected open/closed theo nguồn.
- Kiểm tra backup và cách khôi phục cấu hình khi có sự cố vận hành.
- Thông báo SOC/NOC để phân biệt traffic thử nghiệm với tấn công thật; **không tắt IDS/IPS hoặc audit** chỉ để scan "đẹp".
- Chọn health metrics giám sát: request error rate, latency, CPU control plane, firewall session drops, packet loss, log rate.
- Chốt cách dừng quét, người nhận escalation và nơi lưu output.

### 6.2. Giai đoạn thực hiện

Bắt đầu từ **một đích**, **một số cổng**, không bật tính năng khám phá toàn dải hoặc các script bổ sung. Chỉ tăng phạm vi nếu không có dấu hiệu ảnh hưởng và trong giới hạn RoE. Ghi giờ bắt đầu/kết thúc, source IP, command, Nmap version và cảnh báo trong hệ thống giám sát.

### 6.3. Giai đoạn kiểm chứng

Đừng kết luận từ output scanner đơn lẻ. Đối chiếu với thông tin listener, chính sách firewall và log ở cả phía nguồn lẫn đích; kiểm tra dữ liệu khác biệt theo zone, NAT, VPN và load balancer. Mọi mở cổng ngoài dự kiến cần owner xác nhận có thật và có phù hợp thiết kế không.

## 7. Bài lab: TCP connect scan rất giới hạn với Nmap

Ví dụ chỉ dành cho **host lab hoặc tài sản đã được cấp quyền** có IP tài liệu 192.0.2.10. Những lệnh này minh họa cú pháp, không được hiểu là yêu cầu quét một hệ thống công khai.

### 7.1. Chọn một vài port được phê duyệt

~~~bash
# Chỉ một host, ba cổng TCP; dùng kết nối TCP chuẩn.
# Không bật service detection, NSE script, OS fingerprinting hay quét UDP.
nmap -sT -n -p 22,80,443 \
  --max-retries 1 --max-rate 5 --max-parallelism 1 \
  --host-timeout 120s \
  -oA scan-lab-192-0-2-10 \
  192.0.2.10
~~~

Giải thích:

| Tùy chọn | Mục đích |
| --- | --- |
| **-sT** | TCP connect scan, thử kết nối qua hệ điều hành |
| **-n** | Tránh reverse DNS lookup cho địa chỉ đích |
| **-p 22,80,443** | Chỉ scan ba port đã duyệt |
| **--max-retries 1** | Giới hạn số lần truyền lại probe của Nmap; giảm thời lượng nhưng có thể tăng false negative |
| **--max-rate 5** | Giới hạn tốc độ probe theo cơ chế scheduler của Nmap; không phải cam kết không tác động dịch vụ |
| **--max-parallelism 1** | Hạn chế số probe outstanding trong cơ chế scan |
| **--host-timeout 120s** | Giới hạn tổng thời gian xử lý một host |
| **-oA** | Ghi kết quả normal, XML và grepable theo cùng tiền tố để phục vụ kiểm chứng |

Các tham số thời gian là **minh họa**, không được coi là chuẩn an toàn cho thiết bị OT hoặc appliance đặc thù. Khi bị IDS/IPS block, kết quả có thể thay đổi giữa các lần quét; cần dừng và điều tra, không tìm cách né bộ lọc.

Nếu host discovery trước scan thất bại vì ICMP bị chặn, Nmap có thể báo host down mặc dù TCP service tồn tại. Tùy RoE, có thể thử **trên đúng một IP đã xác định** bằng cách bỏ qua bước host discovery:

~~~bash
# Chỉ dùng -Pn khi đã xác minh mục tiêu và được phê duyệt.
nmap -sT -Pn -n -p 443 \
  --max-retries 1 --max-rate 3 --host-timeout 90s \
  -oA scan-lab-443 \
  192.0.2.10
~~~

**-Pn không phải cách lách firewall**: nó chỉ yêu cầu Nmap coi đích là up để thực hiện scan, dù host discovery không có phản hồi. Nếu dùng với danh sách đích rất lớn, sẽ tăng lượng probe và thời gian; vì vậy không dùng trên một CIDR rộng ngoài phạm vi.

### 7.2. Kiểm tra một cổng trên Windows

Trên PowerShell của một client được phép kiểm thử:

~~~powershell
# Kết quả phản ánh đường TCP từ đúng máy client đang chạy.
Test-NetConnection -ComputerName 192.0.2.10 -Port 443
~~~

Thông tin quan trọng là kết quả TCP connect tại **điểm xuất phát cụ thể**. Công cụ này không kết luận được toàn bộ các tầng DNS, proxy, TLS, HTTP hoặc ứng dụng phía sau.

### 7.3. Kiểm tra listener cục bộ

Nếu có quyền đọc trên server Linux đích:

~~~bash
# Chỉ đọc socket đang lắng nghe; -p có thể cần quyền phù hợp.
ss -lntup

# Xác nhận địa chỉ giao diện và route của chính host.
ip -br addr
ip route show
~~~

Listener 0.0.0.0:443 hoặc [::]:443 có thể lắng nghe rộng hơn 127.0.0.1:443, nhưng firewall host, service mesh, policy routing hoặc cloud security group vẫn có thể chặn từ xa. Nếu Nmap báo open mà server không có listener tương ứng, hãy kiểm tra VIP, reverse proxy, NAT, transparent proxy hoặc việc quét nhầm asset.

## 8. UDP scan: kiểm tra ít cổng và thừa nhận bất định

Một ví dụ trong lab được phép kiểm tra UDP/53:

~~~bash
# Chỉ một UDP port; xem trước khả năng ảnh hưởng của dịch vụ.
nmap -sU -n -p 53 \
  --max-retries 1 --max-rate 2 --host-timeout 120s \
  -oA scan-lab-udp53 \
  192.0.2.10
~~~

Nếu kết quả là **open|filtered**, không được ghi "DNS đang chạy" hoặc "firewall chặn" như kết luận chắc chắn. Máy chủ UDP có thể không phản hồi payload do scanner gửi. Với DNS resolver được phép kiểm thử, phép thử đúng giao thức và câu hỏi kiểm tra rõ ràng thường hữu ích hơn:

~~~bash
# Kiểm tra truy vấn vô hại tới resolver được cấp quyền.
dig @192.0.2.10 example.test A +time=2 +tries=1
~~~

Đọc response code, answer và thời gian; nếu không có phản hồi, cần kiểm tra mạng, DNS ACL, query policy và logs. Không dùng các truy vấn gây thay đổi cấu hình hoặc yêu cầu zone transfer, khuếch đại hay tải lớn nếu chưa có phạm vi riêng. Một DNS query thành công cũng chỉ chứng minh **trường hợp đã thử** hoạt động.

Với NTP, SNMP, SIP, VPN hoặc giao thức OT, cần biết request payload hợp lệ trước khi gửi probe; ưu tiên log, cấu hình và test native được owner chấp thuận. **Không quét UDP diện rộng theo mặc định**.

## 9. Diễn giải kết quả theo vị trí quét

Một port open từ mạng ứng dụng nhưng filtered từ mạng khách có thể là **đúng thiết kế**, không phải kết quả mâu thuẫn.

| Điểm xuất phát | Đích | TCP/443 | TCP/22 | Diễn giải ví dụ |
| --- | --- | --- | --- | --- |
| VLAN APP | API VIP | open | filtered | Ứng dụng truy cập HTTPS; quản trị bị hạn chế |
| VLAN GUEST | API VIP | filtered | filtered | Khách bị chặn theo segmentation |
| VPN ADMIN | IP quản trị thiết bị | closed | open | SSH dành cho quản trị, HTTPS không có listener tại IP này |
| Internet | Public WAF VIP | open | filtered | HTTPS được công bố, quản trị không lộ tại edge |

Bảng chỉ là **kết quả giả định**; một port closed có thể được phản hồi bởi thiết bị trung gian và filtered có thể do timeout, rate limiting hoặc sự cố định tuyến. Cần ghi thời gian, source IP, topology và firewall policy để hiểu đúng.

### 9.1. Quét từ Internet khác quét từ trong VPC

Một server sau load balancer có thể có cổng 22 mở **trên private IP** nhưng không có tuyến trực tiếp từ Internet. Ngược lại, VIP public có cổng 443 open do edge proxy chấp nhận TCP, dù backend đang down. Do đó không lấy kết quả scan VIP để suy ra chính xác trạng thái các backend.

Với dual-stack, IPv4 và IPv6 có thể áp dụng firewall policy khác nhau. Nếu có AAAA record và endpoint nghe IPv6, cần kiểm tra IPv6 trong phạm vi phê duyệt; scan IPv4 không đủ kết luận "không phơi lộ Internet".

### 9.2. DNS và đích được quét

Hostname có thể trả nhiều A/AAAA theo khu vực, TTL hoặc sức khỏe backend; tại hai máy khác nhau có thể phân giải ra hai IP khác. Ghi **IP thực mà scanner đã thử**, resolver, answer và timestamp. Với CDN hoặc dịch vụ SaaS bên thứ ba, cần tuân theo điều kiện kiểm thử của chủ sở hữu; không coi quyền sở hữu hostname là quyền quét mọi hạ tầng mà DNS chỉ tới.

### 9.3. NAT, proxy, WAF và tunnel

NAT thay IP/port; reverse proxy L7 kết thúc TCP và thiết lập upstream connection mới; VPN có thể đóng gói outer traffic. Phép thử quét chỉ chứng minh **đường tới điểm trả lời probe**, không thể bỏ qua log session/NAT để xác định backend thực. IDS/IPS cũng có thể chặn hoặc rate limit scan, khiến nhiều trạng thái filtered xuất hiện cùng lúc.

## 10. Đối chiếu scanner với chính sách bảo mật

Quét cổng an toàn phát huy giá trị khi có **expected exposure matrix**:

| Tài sản và đường đi | Port được phép | Kết quả kỳ vọng | Bằng chứng bổ sung |
| --- | --- | --- | --- |
| APP subnet → API gateway | TCP/443 | open | Gateway access log và firewall allow |
| GUEST subnet → API gateway | TCP/443 | filtered hoặc không kết nối được theo policy | Firewall deny, network segmentation policy |
| ADMIN VPN → firewall management | TCP/22 hoặc HTTPS management theo thiết kế | Chỉ open từ zone ADMIN | AAA log, management ACL, VPN identity |
| Internet → firewall management | Không port quản trị nào được phép | Không thiết lập được connection | Internet-facing policy, device management binding |
| API gateway → backend service | TCP/8443 | open từ gateway | Backend listener, host firewall, target health |
| APP subnet → database | Chỉ đúng kết nối qua service được phép | Không truy cập trực tiếp nếu policy cấm | DB access policy và microsegmentation |

Không phải mọi tổ chức đều dùng cùng port hay cùng kiểu chặn; matrix phải được xây từ **kiến trúc đã phê duyệt**. Mọi sai lệch cần gắn với owner, rủi ro, mức ảnh hưởng và thay đổi khắc phục được kiểm soát.

**Open là thuộc tính quan sát, không phải lỗ hổng mặc định.** Dịch vụ có chủ đích xuất bản như HTTPS có thể hoàn toàn hợp lệ, nhưng vẫn cần kiểm tra TLS configuration, authentication, patch và access control bằng những phương pháp riêng. Cổng không mở từ một zone cũng không chứng minh dịch vụ được bảo vệ khỏi lateral movement từ zone khác.

## 11. Khi kết quả không khớp dự kiến

### 11.1. Dự kiến closed/filtered nhưng scanner báo open

Đặt giả thuyết cạnh tranh:

- Có listener ngoài ý định trên host hoặc container.
- Firewall rule mới, security group, NACL hoặc Kubernetes NetworkPolicy mở quyền truy cập.
- Scanner chạm VIP/load balancer/proxy khác với server được kỳ vọng.
- DNS record hoặc IP mapping đã đổi sau deploy.
- Một thiết bị trung gian trả lời thay backend.
- Scan thực hiện từ zone được phép trong khi báo cáo mô tả zone khác.

Xác minh bằng host socket/listener, firewall logs, LB backend mapping, config version và owner. Không sửa một rule production ngay chỉ dựa trên một dòng scanner.

### 11.2. Dự kiến open nhưng scanner báo closed

Có thể listener dừng, bind sai interface, firewall/host trả RST, backend restart hoặc scan tới IP cũ. Đối chiếu process/port listening, OS logs, LB target health, route và các lần thử application-level. **Closed không cho biết nguyên nhân duy nhất**.

### 11.3. Dự kiến open nhưng scanner báo filtered

Có thể bị chặn bởi firewall/NACL/IDS, packet loss, route bất đối xứng, rate limit hoặc scanner timeout quá ngắn. Dùng firewall/session log và, khi thực sự cần, packet capture tại hai điểm để tìm SYN/SYN-ACK/RST. Không tăng retry, concurrency hoặc dùng cơ chế né IDS chỉ để biến filtered thành open.

### 11.4. UDP open|filtered

Điều này thường yêu cầu kiểm tra đúng giao thức hoặc cấu hình dịch vụ. Nếu cổng là UDP/53, DNS query hợp lệ có thể xác nhận resolver trả lời; với giao thức khác cần hướng dẫn của owner. Không suy rằng dịch vụ đang chạy chỉ vì không nhận ICMP port unreachable.

## 12. Giám sát an toàn trong khi quét

Một lần kiểm thử có kiểm soát phải để lại bằng chứng vận hành:

| Nguồn quan sát | Điều cần theo dõi |
| --- | --- |
| Scanner logs | Command, source, target, time UTC, elapsed time, errors |
| Firewall/NAT session | Flow số lượng, rule match, drop/deny, session capacity |
| IDS/IPS/WAF | Alert, block/rate-limit, false positive liên quan probe |
| Application metrics | Error rate, latency, request timeout, throughput |
| Server/OS | CPU, memory, socket backlog, connection errors |
| Router/switch | Interface drops, control-plane CPU, route adjacency |
| Cloud/VPC logs | Network policy decisions và flow tại resource được hỗ trợ |
| SOC/NOC incident channel | Người theo dõi và quyết định tiếp tục hoặc dừng |

**Điều kiện dừng:** dừng nếu có tác động vận hành rõ ràng, vượt giới hạn RoE, cảnh báo ngoài dự kiến hoặc người phụ trách yêu cầu. Lưu thời điểm dừng và kết quả đã có; chỉ tiếp tục sau khi nguyên nhân và phạm vi được đánh giá lại.

Với production nhạy cảm, monitoring cần chủ động: không chờ scanner chạy hết mới kiểm tra dashboard. Việc "không ai báo lỗi" không phải bằng chứng tuyệt đối rằng scan không gây tác động.

## 13. Bằng chứng và báo cáo kiểm thử

Một bản báo cáo nên tách **quan sát**, **kỳ vọng thiết kế** và **đánh giá rủi ro**.

### 13.1. Mẫu kết quả minh họa

~~~text
TEST ID: CHG-EXAMPLE-1042
Mục tiêu: Xác minh chỉ TCP/443 mở từ VLAN TEST tới API gateway
Owner: Network Security
Ngày/giờ: 2026-11-28T02:05:00Z - 2026-11-28T02:07:00Z
Scanner source: VLAN TEST, IP được đăng ký trong phạm vi phê duyệt
Target: 192.0.2.10 (lab/documentation address)
Method: TCP connect, ports 22/80/443, low rate, no scripts

Expected:
  22: not reachable
  80: not reachable
  443: reachable

Observed (giả định):
  22/tcp: filtered
  80/tcp: closed
  443/tcp: open

Đối chiếu:
  - Host listener xác nhận 443 đang nghe trên interface dự kiến
  - Firewall policy cho phép TEST -> TCP/443, chặn TCP/22
  - Không ghi nhận tăng error rate trong cửa sổ quét

Giới hạn:
  - Chỉ một nguồn và một IP được kiểm thử
  - Không kiểm tra UDP, IPv6, TLS hoặc lỗ hổng ứng dụng
  - Trạng thái chỉ phản ánh cửa sổ kiểm thử

Kết luận:
  - Các cổng được kiểm tra cho kết quả phù hợp với expected exposure
  - Chưa đủ cơ sở kết luận toàn bộ API hoặc mọi zone đều an toàn
~~~

Mỗi kết quả nên giữ output thô có timestamp, Nmap version, command, scope phê duyệt và kết quả log phía thiết bị. XML/normal output có thể giúp tái kiểm tra; khi lưu phải tránh làm lộ sơ đồ dịch vụ và endpoint quản trị cho người không có quyền.

### 13.2. Giữ nguyên nguồn gốc của bằng chứng

Tạo mã phiên kiểm thử và gắn file output với asset, time window, scanner identity, RoE/change ticket. Hash output để đối chiếu tính toàn vẹn nếu cần:

~~~bash
sha256sum scan-lab-192-0-2-10.xml
~~~

Hash giúp phát hiện file bị thay đổi so với giá trị lưu, không tự chứng minh kết quả quét đúng hoặc quyền quét đã được cấp. Nên giữ log gốc, output đã xử lý cho báo cáo và quyền truy cập theo chính sách.

## 14. Kịch bản thực hành: cổng quản trị lộ ngoài ý định

**Bối cảnh:** hệ thống gồm API gateway có VIP 192.0.2.10, được phép công bố TCP/443 từ mạng khách. Cổng SSH/22 chỉ cho phép qua VPN quản trị. Sau một đợt thay đổi cloud security group, nhóm kiểm thử được giao xác minh cổng từ hai zone.

### Bước 1. Xác định kỳ vọng

| Zone kiểm thử | TCP/443 | TCP/22 |
| --- | --- | --- |
| GUEST | Được phép | Phải chặn |
| VPN ADMIN | Được phép nếu phù hợp thiết kế | Được phép cho nguồn quản trị đã xác thực |

### Bước 2. Quét một IP và đúng hai cổng theo RoE

Từ GUEST, thực hiện TCP connect scan tốc độ thấp tới 22 và 443, theo dõi ứng dụng và log. Từ VPN ADMIN, làm tương tự trong cửa sổ được duyệt. Không mở rộng ra toàn subnet hoặc toàn bộ 65.535 port nếu không được phê duyệt.

### Bước 3. Kết quả giả định và phân tích

| Nguồn | 22/tcp | 443/tcp | Đánh giá |
| --- | --- | --- | --- |
| GUEST | open | open | **Sai thiết kế:** cổng quản trị tiếp cận được từ GUEST |
| VPN ADMIN | open | open | Có thể phù hợp thiết kế |

Nhóm cần xác minh **chính xác endpoint nào trả lời cổng 22**: VIP, load balancer, firewall chuyển tiếp hay backend; đối chiếu security group, firewall rules, host listening và flow logs. Nếu mở nhầm thật, báo owner để sửa theo change process. Không tự động tắt SSH trên host production khi chưa có đường quản trị thay thế; có thể làm mất quyền truy cập phục hồi.

### Bước 4. Khắc phục và kiểm thử lại

Sau khi owner áp dụng policy đã phê duyệt, kiểm tra lại từ cả GUEST và VPN ADMIN:

- GUEST không thiết lập được TCP/22; TCP/443 vẫn hoạt động.
- VPN ADMIN vẫn truy cập được cổng quản trị theo chính sách.
- Firewall log và security group thể hiện rule mới, không có tăng lỗi ứng dụng.
- Có chứng cứ timestamp trước/sau, change ticket và người xác nhận.

**Bài học:** sửa mở cổng ngoài ý định phải đồng thời bảo vệ khả năng quản trị hợp lệ và kiểm tra các zone khác. Một kết quả filtered từ GUEST chưa tự chứng minh mọi đường đi khác đã bị đóng.

## 15. Sai lầm thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Quét IP hoặc dải mạng không có quyền | Rủi ro vận hành và pháp lý | RoE rõ owner, source, target, window |
| Quét toàn bộ port ngay lần đầu | Tạo traffic và alert không cần thiết | Bắt đầu từ danh sách nhỏ, mở rộng có phép |
| Tin vào giá trị mặc định là an toàn | Parallelism/retry có thể cao với thiết bị yếu | Đặt giới hạn, quan sát và stop conditions |
| Bật script/service detection không đánh giá | Gửi payload ngoài dự kiến | Chỉ dùng kỹ thuật bổ sung nếu đã phê duyệt |
| Gọi filtered là "firewall chắc chắn chặn" | Sai nguyên nhân | Kiểm tra route, IDS, timeout, packet capture/log |
| Gọi closed là "host hoàn toàn an toàn" | Bỏ qua listener khác, đường khác hoặc IPv6 | Kết hợp inventory và nhiều zone |
| Gọi open là "có lỗ hổng" | Kết luận sai | So với expected design, xác minh service và policy |
| Quên NAT, WAF, LB, CDN | Quét nhầm edge thay backend | Ghi topology và IP thực đã được scanner thử |
| Quên UDP và IPv6 trong phạm vi phù hợp | Thiếu một phần bề mặt phơi lộ | Lập kế hoạch protocol/address family có chọn lọc |
| Dùng một client để suy mọi zone | Bỏ qua microsegmentation | So theo nguồn đã duyệt và policy |
| Quên SYN retransmission, packet loss | Đếm nhầm hoặc kết luận filtered sai | Đối chiếu flow/PCAP, timeouts, counters |
| Tăng tốc khi bị chặn | Làm tăng tải và làm IDS/IPS phản ứng mạnh | Dừng và điều tra cùng owner |
| Không kiểm tra sau khi đổi rule | Không biết khắc phục có hiệu lực hay không | Retest cùng điều kiện, kèm negative test |
| Chỉ giữ ảnh chụp màn hình | Thiếu ngữ cảnh, khó tái kiểm chứng | Lưu raw output, command, UTC, RoE và logs |

## 16. Checklist kiểm thử port scanning an toàn

- [ ] Đã có phê duyệt và RoE rõ asset owner, subnet/host, nguồn quét, thời gian và kỹ thuật.
- [ ] Đã loại trừ tài sản nhạy cảm hoặc có quy trình kiểm thử riêng, đặc biệt ICS/OT và thiết bị cũ.
- [ ] Đã biết expected ports theo kiến trúc và zone tin cậy, không quét chỉ để thu danh sách dài.
- [ ] Đã ghi IP thực, FQDN/DNS answer, asset ID và chính sách NAT/LB/proxy có liên quan.
- [ ] Đã chọn phương án ít tác động, giới hạn port/host/rate/retries/time và không dùng scripts ngoài phạm vi.
- [ ] Đã thông báo NOC/SOC, chuẩn bị metrics giám sát và điều kiện dừng.
- [ ] Đã thực hiện theo nhóm nhỏ, không tăng tốc hoặc né IDS/IPS khi bị chặn.
- [ ] Đã phân biệt open, closed, filtered và open|filtered theo đúng kiểu scan.
- [ ] Đã đối chiếu với listener, firewall/ACL, security group, flow logs và tình trạng ứng dụng.
- [ ] Đã xác minh khác biệt giữa client zones, VPN, cloud, Wi-Fi khách và IPv4/IPv6 nếu thuộc phạm vi.
- [ ] Đã phân biệt bề mặt cổng với xác thực, cấu hình TLS, phiên bản dịch vụ và lỗ hổng ứng dụng.
- [ ] Đã lưu command, tool version, timestamp UTC, kết quả thô, owner, change ticket và giới hạn của kết luận.
- [ ] Đã thực hiện retest sau khắc phục, bao gồm luồng **được phép** và luồng **phải chặn**.

**Nguyên tắc cuối:** port scanning có giá trị khi trả lời một câu hỏi kiểm thử cụ thể bằng lượng probe nhỏ nhất cần thiết, từ nguồn đã phê duyệt và có khả năng giám sát tác động. Kết quả phải được đọc trong bối cảnh firewall, NAT, VPN, IDS/IPS, DNS, cloud và lớp ứng dụng; một dòng trạng thái cổng chỉ là quan sát tại một thời điểm và vị trí, không phải phán quyết toàn diện về an toàn mạng.
