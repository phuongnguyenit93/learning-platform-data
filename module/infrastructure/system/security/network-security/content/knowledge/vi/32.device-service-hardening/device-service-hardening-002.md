# Tắt dịch vụ và port không cần thiết

## 1. Vì sao tắt dịch vụ và cổng dư thừa là một biện pháp hardening quan trọng?

Một máy chủ, router, switch, firewall, thiết bị Wi-Fi, VPN gateway hay workload trên cloud có thể chạy nhiều dịch vụ ngoài nhiệm vụ chính. Mỗi dịch vụ có khả năng nhận kết nối từ mạng tạo thêm một điểm có thể bị dò quét, khai thác lỗ hổng, dùng mật khẩu yếu hoặc lạm dụng cấu hình. **Giảm số dịch vụ và cổng truy cập không cần thiết** giúp thu hẹp *attack surface* (bề mặt tấn công), đơn giản hóa chính sách firewall và làm cho hoạt động giám sát bất thường rõ ràng hơn.

Ví dụ, một máy chủ ứng dụng chỉ cung cấp HTTPS trên TCP/443 có thể vẫn chạy Telnet (23), FTP (21), dịch vụ chia sẻ tệp SMB (445), web quản trị mặc định trên 8080 hoặc tác nhân thử nghiệm trên 9090. Nếu những dịch vụ này không phục vụ chức năng đã được phê duyệt, việc để chúng hoạt động tạo rủi ro không tương xứng với giá trị.

Tuy nhiên, **không phải mọi cổng đang mở đều không cần thiết**, và cũng không được tắt hàng loạt chỉ vì cổng không quen thuộc. DNS, DHCP, NTP, VPN, SSH, SNMP, BGP, RADIUS, dịch vụ xác thực, giám sát hoặc sao lưu có thể là thành phần bắt buộc tùy vai trò thiết bị. Hardening phải dựa trên mục đích kinh doanh, bản đồ phụ thuộc, điểm quản trị và khả năng khôi phục.

Trong module **SECURITY_NETWORK_SECURITY**, chủ đề này liên kết trực tiếp với phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, mạng không dây và cloud: thiết bị chỉ cung cấp các dịch vụ đúng vai trò; các lớp mạng chỉ cho phép những luồng cần thiết; hệ thống giám sát nhận biết khi bề mặt tấn công thay đổi.

Sau bài học, người học có thể:

- Phân biệt dịch vụ đang chạy, socket lắng nghe, cổng được cho phép qua firewall và cổng nhìn thấy từ một vị trí mạng.
- Lập danh mục dịch vụ, xác định bên sử dụng, phụ thuộc và mức độ cần thiết trước khi thay đổi.
- Tắt dịch vụ dư thừa hoặc hạn chế phạm vi tiếp cận dịch vụ cần thiết trên Linux, Windows, thiết bị mạng và môi trường cloud.
- Kiểm tra cả TCP, UDP, IPv4, IPv6, các interface, các vùng mạng và cơ chế tự khởi động lại.
- Thực hiện thay đổi có lưu cấu hình, giám sát, kế hoạch rollback và bằng chứng xác minh.

## 2. Phân biệt service, port và quyền truy cập qua mạng

**Dịch vụ (service)** là chương trình hoặc tính năng cung cấp một chức năng: web server, DNS resolver, SSH daemon, API quản trị, VPN server. **Port TCP/UDP** là số hiệu đầu cuối vận chuyển trong một giao thức; một port có thể được nhiều ứng dụng sử dụng ở các IP, giao thức hoặc thời điểm khác nhau. Trong bài này, “port” nghĩa là **cổng logic lớp vận chuyển**, không phải cổng vật lý Ethernet trên switch.

Một dịch vụ có thể chạy nhưng không mở cổng mạng (chỉ dùng IPC/socket Unix); có thể lắng nghe trên \`127.0.0.1\` nhưng không trên địa chỉ LAN; hoặc có cổng đang lắng nghe nhưng bị firewall chặn từ một vùng mạng. Một cổng bị firewall “đóng” đối với người dùng Internet chưa chắc đã đóng đối với VLAN quản trị hoặc một workload cùng subnet.

| Trạng thái | Ý nghĩa | Điều cần kiểm chứng |
|---|---|---|
| Service đã cài đặt | Gói/tính năng có trên hệ thống | Có đang chạy, tự khởi động hay có thể được kích hoạt khi có yêu cầu không? |
| Service đang chạy | Tiến trình/tính năng hoạt động | Có bind TCP/UDP, Unix socket hoặc mở kết nối outbound không? |
| TCP **LISTEN** | Một tiến trình chờ kết nối tại địa chỉ và port | Bind vào loopback, IP riêng, mọi interface hay IPv6? |
| UDP socket bind | Có ứng dụng nhận datagram trên địa chỉ/port | UDP không có trạng thái LISTEN giống TCP; phải quan sát ứng dụng và luồng thực tế |
| Firewall **allow** | Một quy tắc có thể cho phép lưu lượng khớp điều kiện | Còn quy tắc khác, thứ tự xử lý, deny, NAT, zone hoặc ACL không? |
| Cổng **open** trong kết quả quét | Có phản hồi phù hợp từ vị trí máy quét tại thời điểm quét | Có phải dịch vụ mong đợi và có quyền truy cập đúng đối tượng không? |
| Cổng **filtered / open\|filtered** | Bị lọc hoặc không thể kết luận rõ từ phản hồi | Không đồng nghĩa dịch vụ đã dừng; UDP thường khó kết luận hơn TCP |
| Không thấy cổng từ Internet | Internet không tiếp cận được trong phép kiểm tra | Cần kiểm tra riêng east-west, VPN, mạng quản trị, IPv6 và đường cloud |

### Ba câu hỏi phải trả lời riêng

1. **Dịch vụ có cần tồn tại không?** Nếu không, ưu tiên dừng, tắt khởi động hoặc gỡ tính năng theo quy trình.
2. **Nếu cần, nó có cần được truy cập qua mạng không?** Nếu không, cấu hình chỉ lắng nghe trên loopback hoặc Unix socket.
3. **Nếu cần truy cập mạng, ai được phép kết nối?** Hạn chế theo nguồn, zone, identity, thiết bị, giao thức, cổng và thời gian phù hợp.

Một chính sách firewall chặn inbound chỉ giảm khả năng tiếp cận; **không loại bỏ** mã dễ bị khai thác, tác vụ nền, lỗi cấu hình hoặc nguy cơ khi attacker đã ở bên trong. Ngược lại, dừng dịch vụ mà không sửa một allow rule quá rộng có thể khiến cổng mở lại khi service được cài lại hoặc khởi chạy từ một cơ chế khác.

## 3. Xác định cổng và dịch vụ nào thực sự cần

Thay vì dùng danh sách cổng “xấu” áp dụng cho mọi hệ thống, hãy xây dựng **baseline theo vai trò**.

| Loại tài sản | Dịch vụ có thể cần | Dịch vụ cần xem xét loại bỏ/hạn chế nếu không có chức năng tương ứng |
|---|---|---|
| Reverse proxy / web frontend | TCP/443 từ client; TCP/80 chỉ khi phục vụ redirect hoặc HTTP cần thiết; kênh health check nội bộ | Telnet, FTP, SSH mở toàn Internet, dashboard debug/public, database port |
| Máy chủ ứng dụng | Kết nối inbound từ proxy đến port ứng dụng; kết nối outbound đúng backend | RDP/SMB/debug console mở cho mọi subnet; agent thử nghiệm |
| Database | Port DB từ application tier/replica/backup được phê duyệt | Port DB từ Internet hoặc VLAN người dùng; web admin mặc định |
| DNS resolver nội bộ | TCP/UDP 53 từ client được phép và upstream cần thiết | Recursive DNS cho Internet công cộng nếu không được thiết kế phục vụ public |
| VPN gateway | Giao thức/cổng VPN theo sản phẩm, luồng xác thực và quản trị được bảo vệ | Telnet/HTTP quản trị, dịch vụ thử nghiệm, SSH quản trị từ mạng ngoài không giới hạn |
| Router/switch/firewall | Routing protocol, NTP, AAA, SSH/HTTPS quản trị hoặc SNMPv3 theo thiết kế | Telnet, HTTP không mã hóa, SNMPv1/v2c khi không cần, FTP/TFTP server trái nhu cầu |
| Máy người dùng | Client outbound; một số agent quản trị theo chính sách | RDP/SMB server hoặc dịch vụ chia sẻ không cần; cơ chế phát hiện tự động trong vùng không tin cậy |
| Workload/container | Port ứng dụng đã định nghĩa; health/metrics chỉ trong vùng giám sát | Runtime API, Docker daemon API, debug/profiler, metrics hoặc kubelet endpoint công khai |

Bảng trên là ví dụ; cổng cụ thể và phụ thuộc thực tế thay đổi theo sản phẩm, kiến trúc và chính sách. **Không tắt TCP/53 chỉ vì DNS thường dùng UDP**: DNS có thể cần TCP cho phản hồi lớn, zone transfer được phân quyền và các cơ chế giao thức. Tương tự, NTP/123, DHCP/67–68, Kerberos/88, LDAP/636, BGP/179 hoặc các cổng VPN có thể rất quan trọng ở thiết bị phù hợp.

### Bảng quyết định cho từng dịch vụ

Với mỗi service/socket, ghi tối thiểu:

| Trường | Câu hỏi cần trả lời |
|---|---|
| Host, vai trò, môi trường | Máy nào, dev/staging/prod, chủ sở hữu là ai? |
| Tên service và tiến trình | Gói/tính năng nào tạo ra socket? |
| Protocol, local address, local port | TCP hay UDP, IPv4/IPv6, loopback hay mọi interface? |
| Client/nguồn hợp lệ | Ai gọi tới, từ subnet/VPN/jump host/cloud workload nào? |
| Phụ thuộc và đầu ra | Service gọi ra ngoài tới đâu, ứng dụng khác có đang dùng nó không? |
| Mức độ cần thiết | Bắt buộc, cần nhưng có thể thu hẹp, hay không dùng? |
| Cơ chế khởi chạy | systemd, socket activation, Windows Service, scheduled task, container, orchestrator? |
| Phương án thay đổi | Stop/disable/uninstall, đổi bind address, hoặc thu hẹp firewall/ACL? |
| Kiểm chứng/rollback | Phép thử nào chứng minh dịch vụ chính vẫn hoạt động và cách khôi phục? |
| Owner và thay đổi được phê duyệt | Ai quyết định và giám sát sau triển khai? |

Không thể kết luận “không dùng” chỉ vì không thấy kết nối trong vài phút. Dịch vụ có thể chỉ được gọi khi sao lưu, rollover chứng chỉ, failover, khởi động lại, DR drill, lịch hàng tháng hoặc sự cố khẩn cấp.

## 4. Khảo sát bề mặt tấn công trước khi tắt

### 4.1. Khảo sát trên Linux

Các lệnh sau mang tính **quan sát**, dùng trên máy có quyền quản trị hợp lệ:

~~~bash
# TCP listening và UDP sockets; tùy hệ thống cần sudo để xem process/PID.
sudo ss -lntup

# Liệt kê unit đang chạy và các socket systemd có thể kích hoạt service.
systemctl list-units --type=service --state=running
systemctl list-sockets --all

# Kiểm tra một service cụ thể trước khi thay đổi.
systemctl status avahi-daemon.service
systemctl is-enabled avahi-daemon.service
systemctl cat avahi-daemon.service

# Cấu hình firewall đang hiệu lực (phụ thuộc hệ điều hành/công cụ).
sudo nft list ruleset
~~~

Giải thích \`ss\`:

- \`0.0.0.0:PORT\` thường có nghĩa là lắng nghe trên mọi IPv4 local address; \`[::]:PORT\` có thể bao phủ IPv6 và trên một số cấu hình cũng liên quan IPv4. **Phải xác minh riêng từng họ địa chỉ**.
- \`127.0.0.1:PORT\` hoặc \`[::1]:PORT\` chỉ lắng nghe trên loopback tương ứng; vẫn cần xem có proxy hoặc tunnel nào đưa dịch vụ ra mạng khác không.
- Một socket \`udp\` không hiện \`LISTEN\` như TCP; dùng \`ss -lnup\` kết hợp log/flow thay vì kết luận UDP không hoạt động.
- Dùng \`systemctl list-sockets\` để nhận biết **socket activation**: service có thể chưa chạy nhưng được kích hoạt khi có kết nối.
- Một container hoặc pod có thể tạo socket riêng trong namespace mạng; khảo sát trên host chưa chắc phản ánh toàn bộ workload.

Có thể kiểm tra thêm cấu hình \`systemd\`, \`cron\`, \`inetd/xinetd\`, process supervisor hoặc runtime container nếu dịch vụ được chạy lại tự động.

### 4.2. Khảo sát trên Windows

Dùng PowerShell có quyền phù hợp:

~~~powershell
# Các TCP listening endpoint và tiến trình sở hữu.
Get-NetTCPConnection -State Listen |
  Sort-Object LocalAddress, LocalPort |
  Select-Object LocalAddress, LocalPort, OwningProcess

# UDP endpoints không có trạng thái Listen theo TCP.
Get-NetUDPEndpoint |
  Sort-Object LocalAddress, LocalPort |
  Select-Object LocalAddress, LocalPort, OwningProcess

# Phân giải PID đã được xác minh thành tên tiến trình.
Get-Process -Id 1234

# Kiểm tra trạng thái và kiểu khởi động một service.
Get-Service -Name RemoteRegistry

# Xem firewall rule đang có hiệu lực.
Get-NetFirewallRule -PolicyStore ActiveStore |
  Where-Object Enabled -eq 'True' |
  Select-Object DisplayName, Direction, Action, Profile
~~~

Danh sách từ \`Get-NetFirewallRule\` **chưa cho biết mọi port và source IP**: cần tra thêm \`Get-NetFirewallPortFilter\`, \`Get-NetFirewallAddressFilter\`, profile và rule nguồn GPO/MDM. \`Get-Process\` cho PID nhưng không tự kết luận service nào có vai trò hợp lệ; có thể đối chiếu \`Win32_Service\`, service executable path và owner.

**Windows có nhiều dịch vụ sử dụng RPC hoặc cổng động**. Không chặn cổng cao một cách máy móc khi chưa xác định ứng dụng hoặc cơ chế truy cập, vì có thể làm gián đoạn AD, quản trị, sao lưu và ứng dụng doanh nghiệp.

### 4.3. Kiểm tra từ đúng vị trí trong mạng

Trên máy kiểm thử được cấp phép, dùng phép quét có phạm vi hẹp để xác nhận kết quả từ vị trí người dùng, VLAN quản trị và subnet không được phép. Ví dụ dùng địa chỉ dành cho tài liệu:

~~~bash
# Chỉ thực hiện đối với host và phạm vi được cho phép.
nmap -sT -sV -p 21,22,23,53,80,443,445,3389,5985,5986 192.0.2.20

# Với UDP, phản hồi bị thiếu có thể cho kết quả open|filtered.
nmap -sU -p 53,123,161 192.0.2.20
~~~

Kết quả quét phụ thuộc vào vị trí máy quét, ACL/NAT, firewall state, kỹ thuật phát hiện service và thời điểm. Khi cần xác minh việc tắt cổng, nên đối chiếu **ảnh chụp trước và sau** từ cùng vantage point, đồng thời đọc socket trên chính host. Không coi \`filtered\` là tương đương \`closed\`.

### 4.4. Thiết bị mạng, Wi-Fi và cloud

- **Router/switch/firewall:** kiểm kê dịch vụ quản trị, đường truy cập vào *management plane*, ACL áp dụng trên interface quản trị, local user/AAA, SNMP, NETCONF/RESTCONF, HTTP/HTTPS, SSH/Telnet. Kiểm tra giao thức định tuyến và kiểm soát lưu lượng *control plane* riêng với dịch vụ ứng dụng.
- **Wi-Fi/AP/controller:** xác định controller/API quản trị, captive portal, discovery service, SSH, web admin, quản trị từ wireless client hoặc guest VLAN; xác minh tính năng vẫn cần cho provision/roaming.
- **Cloud:** kiểm tra listener trong VM/container, host firewall, security group/NSG, subnet ACL/NACL, private endpoint, ingress/load balancer, cấu hình public IP và API quản trị. Mỗi lớp trả lời một câu hỏi khác nhau.
- **Kubernetes:** \`containerPort\` là metadata của container, **không** tự mở cổng hay là firewall rule; cần xem process bind, Service, Ingress/Gateway, NetworkPolicy, node port, hostNetwork và quyền của API server. NetworkPolicy chỉ thực thi nếu CNI hỗ trợ.
- **Thiết bị chuyên dụng/IoT:** có thể không cung cấp khả năng dừng daemon tùy ý; ưu tiên cập nhật firmware, tắt tính năng trong giao diện quản trị được hỗ trợ và cách ly bằng firewall/ACL.

## 5. Thứ tự ưu tiên khi loại bỏ bề mặt tấn công

Một trình tự thường hợp lý:

1. **Loại bỏ tính năng không cần:** gỡ role/gói/plugin hoặc vô hiệu hóa daemon sau khi được chủ hệ thống phê duyệt; đây là bước giảm rủi ro căn bản nhất.
2. **Chặn cơ chế tự hồi sinh:** tắt auto-start/service, socket activation, scheduled task, container restart/deployment template hoặc cấu hình quản lý tập trung, nếu chúng thuộc phạm vi dịch vụ muốn bỏ.
3. **Thu hẹp điểm lắng nghe:** với chức năng chỉ phục vụ nội bộ host, bind vào loopback hoặc Unix socket; với dịch vụ quản trị, bind vào interface/VLAN quản trị khi nền tảng hỗ trợ.
4. **Hạn chế khả năng tiếp cận:** áp dụng firewall/ACL, security group, segmentation, VPN, jump host và xác thực mạnh theo danh sách nguồn/đích được phép.
5. **Giữ kiểm chứng và phát hiện sai lệch:** ghi baseline; cảnh báo khi port mới xuất hiện, rule mở rộng hoặc service khởi động trở lại.

**Không dùng firewall như biện pháp thay thế duy nhất** nếu daemon thực sự không cần. Nhưng cũng không được gỡ một dịch vụ vẫn phục vụ chức năng thiết yếu chỉ để “giảm số cổng”; trong trường hợp đó hãy giới hạn đường truy cập.

### Ví dụ lựa chọn biện pháp theo tình huống

| Phát hiện | Biện pháp ưu tiên | Chứng cứ xác nhận |
|---|---|---|
| Telnet server không được sử dụng | Disable/uninstall Telnet server; dùng SSH có xác thực phù hợp nếu cần quản trị | Không còn listener TCP/23; từ các vùng mạng không kết nối được; SSH quản trị còn hoạt động |
| HTTP admin của switch trong LAN | Vô hiệu HTTP không mã hóa khi có HTTPS/SSH thay thế; chỉ cho phép quản trị qua management zone | TCP/80 không còn mở; truy cập HTTPS/SSH từ nguồn cho phép thành công |
| DB port mở tới VLAN người dùng | Giới hạn firewall/security group tới application tier; nếu DB vẫn cần thì **không tắt daemon** | Kết nối ứng dụng còn tốt; nguồn không được phép bị từ chối |
| Metrics/debug port lắng nghe trên mọi interface | Đổi bind sang loopback/monitoring interface, hoặc đưa sau authenticated proxy và ACL | Collector vẫn lấy metrics; mạng người dùng không truy cập trực tiếp |
| mDNS/SSDP/UPnP không dùng trên server | Tắt daemon/tính năng discovery được xác nhận dư thừa | Không còn listener/broadcast liên quan; ứng dụng chính không bị ảnh hưởng |
| RDP trên máy quản trị | Giữ nếu phục vụ vận hành nhưng giới hạn qua bastion/VPN và chính sách tài khoản | Bastion truy cập được; VLAN thông thường không thể kết nối |

## 6. Ví dụ hardening Linux có kiểm soát

Giả sử một VM Linux chạy API nội bộ và trước đó vô tình cài dịch vụ quảng bá mDNS. Đội vận hành xác minh dịch vụ \`avahi-daemon\` không phục vụ discovery hay quy trình cấu hình trong môi trường này.

### Bước A — Ghi trạng thái trước thay đổi

~~~bash
# Ghi lại kết quả vào hồ sơ thay đổi/kho chứng cứ theo quy định nội bộ.
systemctl status avahi-daemon.service
systemctl is-enabled avahi-daemon.service
systemctl list-sockets --all
sudo ss -lntup
~~~

Xác định socket nào liên quan: \`avahi-daemon\` thường gắn với multicast DNS UDP/5353. Nhưng nếu UDP/5353 đang do ứng dụng khác sử dụng thì phải điều tra trước; **không suy luận từ số port sang tên service**.

### Bước B — Tắt dịch vụ sau khi được phê duyệt

~~~bash
# Ví dụ có điều kiện: chỉ làm khi avahi-daemon đã được xác nhận không cần.
sudo systemctl disable --now avahi-daemon.service

# Nếu một socket unit liên quan có thể tự kích hoạt lại dịch vụ,
# xem tên unit và trạng thái thực tế trước khi quyết định disable socket.
systemctl list-sockets --all
~~~

\`disable --now\` dừng service hiện tại và bỏ liên kết tự khởi động của unit; **không phải bảo đảm vĩnh viễn** mọi cơ chế activation đều bị chặn. Nếu dịch vụ do một socket unit, dependency, tác vụ quản lý cấu hình hoặc orchestrator khởi chạy, cần xử lý đúng cơ chế đó. \`mask\` mạnh hơn \`disable\` nhưng có thể phá phụ thuộc; không dùng mặc định khi chưa đánh giá.

### Bước C — Kiểm tra và rollback nếu phát hiện phụ thuộc

~~~bash
systemctl is-active avahi-daemon.service
systemctl is-enabled avahi-daemon.service
sudo ss -lnup

# Chỉ rollback khi theo kế hoạch đã lưu: khôi phục service.
sudo systemctl enable --now avahi-daemon.service
~~~

Dòng rollback là **mẫu phương án**, không chạy cùng lần với bước tắt trong một kịch bản thực tế. Nếu trước thay đổi unit vốn ở trạng thái \`disabled\`, rollback phải khôi phục **đúng trạng thái gốc**, không tự ý bật auto-start. Nếu hệ thống không sử dụng systemd hoặc tên unit khác, áp dụng cơ chế tương ứng.

### Tại sao không đơn giản chặn UDP/5353 trên firewall?

Nếu dịch vụ không cần, dừng daemon loại bỏ một phần mã nhận và xử lý lưu lượng. Firewall vẫn hữu ích để giới hạn multicast giữa các phân đoạn, nhưng một chặn trên một interface không chắc đã ngăn listener được truy cập từ loopback, interface khác hoặc cấu hình container đặc biệt.

## 7. Ví dụ Windows: vô hiệu hóa service không cần và kiểm tra firewall

Giả sử chính sách máy chủ không cho phép sử dụng **Remote Registry** và chủ hệ thống xác nhận không có công cụ quản trị/backup nào phụ thuộc. Đây là ví dụ về hardening service, **không mặc định đồng nhất Remote Registry với một cổng TCP cố định** vì truy cập có thể liên quan cơ chế RPC/SMB.

~~~powershell
# Kiểm tra service, ghi lại trạng thái trước thay đổi.
Get-Service -Name RemoteRegistry |
  Select-Object Name, Status, StartType

# Sau khi đánh giá phụ thuộc và phê duyệt:
Stop-Service -Name RemoteRegistry
Set-Service -Name RemoteRegistry -StartupType Disabled

# Xác minh trạng thái cuối.
Get-Service -Name RemoteRegistry |
  Select-Object Name, Status, StartType
~~~

Nếu dịch vụ không chạy, \`Stop-Service\` có thể không cần thiết. Nếu bị phụ thuộc bởi quy trình hợp lệ, phải hủy hoặc sửa kế hoạch. Khi rollback, khôi phục **kiểu khởi động ban đầu** (Automatic/Manual/Disabled) và chỉ khởi động lại nếu trước đó đang chạy.

Đối với dịch vụ vẫn cần, chẳng hạn WinRM/RDP trên jump host, nên xem **các firewall rule đang cho phép**. Trên Windows, nhiều rule cùng áp dụng và Group Policy có thể ghi đè cấu hình local. Tạo thêm một rule Allow có \`RemoteAddress\` hạn chế **không bảo đảm** các rule Allow rộng khác đã hết hiệu lực; phải rà toàn bộ tập quy tắc, profile và chính sách quản lý tập trung.

Ví dụ lệnh khảo sát rule:

~~~powershell
# Cần kiểm tra tiếp port/address filter và chính sách có hiệu lực.
Get-NetFirewallRule -PolicyStore ActiveStore |
  Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' } |
  Select-Object DisplayName, Action, Profile

Get-NetFirewallRule -DisplayGroup "Windows Remote Management" |
  Get-NetFirewallPortFilter

Get-NetFirewallRule -DisplayGroup "Windows Remote Management" |
  Get-NetFirewallAddressFilter
~~~

Tên \`DisplayGroup\` phụ thuộc bản Windows và ngôn ngữ hệ thống. Nếu các lệnh không trả về rule, hãy tìm theo tên/id cụ thể trong cấu hình đang dùng; không suy đoán đã an toàn.

## 8. Hardening management plane trên thiết bị mạng

Các dịch vụ quản trị có quyền thay đổi cấu hình nên được xem xét trước những dịch vụ thông thường. Cùng một router/switch có thể vừa cần giao thức định tuyến và giám sát, vừa có web UI hoặc Telnet cũ mà không ai dùng.

| Dịch vụ/tính năng | Quyết định nếu không cần | Nếu vẫn cần |
|---|---|---|
| **Telnet / HTTP quản trị** | Vô hiệu hóa nếu có đường thay thế đã kiểm thử | Ưu tiên SSH và HTTPS với phiên bản giao thức, thuật toán, chứng chỉ và xác thực an toàn |
| **SNMP v1/v2c** | Tắt khi không dùng | Ưu tiên SNMPv3 với xác thực và bảo vệ riêng tư, giới hạn manager IP/VRF và quyền |
| **TFTP / FTP server** | Tắt nếu không thuộc quy trình backup/config hiện hành | Dùng cơ chế truyền bảo vệ phù hợp, hạn chế nguồn, quyền và thời gian |
| **Discovery (LLDP, CDP, mDNS, UPnP...)** | Giảm hoặc tắt theo thiết kế từng interface/zone | Giới hạn vào liên kết tin cậy; LLDP/CDP có thể cần cho vận hành và thoại IP |
| **API/NETCONF/RESTCONF/SSH** | Tắt giao thức quản trị không dùng | Bật AAA, RBAC, MFA nơi hỗ trợ, management ACL, audit log |
| **Routing protocols** | Tắt trên interface không tham gia | Giới hạn peer, xác thực khi giao thức hỗ trợ, chính sách route và control-plane protection |
| **DNS/DHCP/NTP/RADIUS/TACACS+** | Chỉ tắt vai trò server/client không cần | Giữ luồng cần thiết, kiểm soát server tin cậy và dự phòng phù hợp |

Một số giao thức như OSPF không hoạt động như TCP/UDP “port mở” thông thường; ví dụ OSPF dùng IP protocol number 89. Do đó, hardening không thể chỉ quét TCP/UDP mà cần **kiểm kê tính năng, interface và giao thức điều khiển**.

Khi tắt web quản trị hoặc thay đổi ACL management plane, phải có **đường truy cập quản trị thay thế** (console/OOB hoặc phiên SSH đã kiểm tra) trước khi áp dụng. Cấu hình lưu, commit/rollback và thứ tự câu lệnh tùy hãng; không sao chép lệnh của thiết bị này sang thiết bị khác. Với thiết bị HA, cần xét sự đồng bộ cấu hình, failover và mặt phẳng dự phòng trước khi triển khai.

### Ví dụ thiết kế luồng quản trị

~~~mermaid
flowchart LR
    U["Máy người dùng"] -->|"TCP/443 ứng dụng"| W["Web / API"]
    J["Jump host trong management VLAN"] -->|"SSH/HTTPS quản trị"| N["Router / Switch / Firewall"]
    S["Hệ thống giám sát"] -->|"SNMPv3 theo chính sách"| N
    U -.->|"Không được phép: Telnet, SSH quản trị"| N
    G["Internet"] -.->|"Không được phép: web admin"| N
~~~

Sơ đồ diễn tả **chính sách dự kiến**, không phải kết quả kiểm tra thực tế. Phải xác nhận enforcement tại firewall/ACL, interface quản trị và các đường khác như IPv6, VPN và cloud peering.

## 9. Firewall, phân đoạn và chính sách cloud: chỉ cho phép kết nối cần thiết

Sau khi quyết định service nào được phép hoạt động, biến kết quả thành một **ma trận luồng**, ví dụ:

| Nguồn | Đích | Protocol/port | Mục đích | Quyết định |
|---|---|---|---|---|
| Internet | Reverse proxy | TCP/443 | Truy cập ứng dụng | Allow theo thiết kế |
| Internet | Web/app server: TCP/22 | TCP/22 | Quản trị trực tiếp | Deny |
| Jump host | Linux app server | TCP/22 | Quản trị đã xác thực | Allow giới hạn nguồn |
| Reverse proxy | Application tier | TCP/8443 | Backend HTTPS | Allow |
| Application tier | Database tier | TCP/5432 | PostgreSQL | Allow từ nguồn ứng dụng |
| User VLAN | Database tier | TCP/5432 | Truy cập DB trực tiếp | Deny |
| Monitoring subnet | Metrics endpoint | TCP/9090 | Thu thập metrics | Allow nếu thực sự cần |
| User VLAN/Internet | Metrics endpoint | TCP/9090 | Không có nhu cầu | Deny |

Ma trận cần bao quát cả **inbound** và **outbound**, kết nối giữa các subnet và luồng quản trị. Khi dùng stateful firewall, phản hồi của kết nối đã cho phép thường được xử lý theo trạng thái; không nên mở rộng cổng ephemeral inbound theo một dải lớn chỉ vì ứng dụng client dùng ephemeral source port. Với giao thức hoặc thiết bị không stateful, phải mô tả chiều trả lời đúng theo giao thức và ACL thực tế.

### Các điểm dễ nhầm trong môi trường cloud/container

- **Security group/NSG**: quy tắc có thể gắn vào NIC, VM hoặc workload; phải kiểm tra tính kế thừa và rule ưu tiên. Một rule Allow giới hạn không bảo đảm an toàn khi vẫn còn rule mở rộng ở nơi khác.
- **Load balancer / reverse proxy**: port backend có thể không public nhưng vẫn truy cập được từ nguồn không mong đợi trong VPC/VNet; cần kiểm tra cả backend.
- **Kubernetes Service/Ingress**: việc xóa \`containerPort\` khỏi manifest không dừng process listening. Việc xóa Ingress có thể chặn truy cập bên ngoài nhưng vẫn còn Service/NodePort hoặc hostNetwork; phải xác minh toàn tuyến.
- **Serverless/managed services**: không phải mọi listener có thể tắt trong hệ điều hành; dùng control plane, network policy, private connectivity và IAM đúng sản phẩm.
- **IPv6**: có thể có đường tới đích qua IPv6 dù chính sách IPv4 đã khóa. Cần kiểm tra listener/rule/route cho cả hai.

## 10. Quy trình thay đổi an toàn: khảo sát → phê duyệt → tắt → xác minh

~~~mermaid
flowchart TD
    A["Inventory socket, service, rule và luồng đang dùng"] --> B["Xác định vai trò, owner, phụ thuộc và baseline"]
    B --> C{"Service còn cần thiết?"}
    C -->|"Không"| D["Lập phương án stop/disable/uninstall và kiểm soát tự khởi chạy"]
    C -->|"Có"| E{"Có cần truy cập từ mạng không?"}
    E -->|"Không"| F["Bind loopback/local socket"]
    E -->|"Có"| G["Giới hạn nguồn, zone, identity và protocol"]
    D --> H["Đánh giá tác động, backup cấu hình, kế hoạch rollback"]
    F --> H
    G --> H
    H --> I["Thay đổi trong phạm vi được phê duyệt"]
    I --> J["Kiểm tra chức năng + listener + đường truy cập từ nhiều vùng"]
    J --> K{"Đạt tiêu chí thành công?"}
    K -->|"Không"| L["Rollback theo trạng thái gốc; điều tra ảnh hưởng"]
    K -->|"Có"| M["Ghi baseline mới, quan sát và cảnh báo drift"]
~~~

**Bước 1 — Kiểm kê.** Thu danh sách service, listener IPv4/IPv6, TCP/UDP, port mapping container, rule firewall, thiết bị mạng và luồng ứng dụng trong khoảng thời gian đại diện. Ghi owner và môi trường.

**Bước 2 — Tìm phụ thuộc.** Hỏi chủ hệ thống, xem change history, flow logs, dependency map, kịch bản DR/backup, job định kỳ và các tài sản có chức năng dự phòng. Đặc biệt cẩn thận với DNS, DHCP, VPN, NTP, PKI, AD, cluster heartbeat, orchestration và các kênh giám sát.

**Bước 3 — Lựa chọn mục tiêu.** Với dịch vụ thừa, đề xuất stop/disable/uninstall. Với dịch vụ cần nhưng lộ quá rộng, đề xuất ràng buộc địa chỉ bind, firewall/ACL, VLAN quản trị, IAM, TLS và xác thực phù hợp.

**Bước 4 — Chuẩn bị rollback.** Lưu cấu hình trước thay đổi, cách truy cập console/OOB, giá trị \`StartType\` hoặc \`is-enabled\` gốc, rule/ACL gốc, port mapping, lệnh phục hồi phù hợp hệ thống và tiêu chí kích hoạt rollback.

**Bước 5 — Triển khai có phạm vi.** Thử trên staging hoặc một node canary trước khi áp dụng diện rộng. Với cụm HA, kiểm tra hệ thống dự phòng và failover; với thiết bị định tuyến, tránh tự cắt phiên quản trị.

**Bước 6 — Kiểm chứng nhiều chiều.** Kiểm tra service có dừng/đổi bind thật không, cổng có còn truy cập từ vùng không được phép không, dịch vụ chính còn đạt health check, auth, backup, giám sát và đường quản trị hợp lệ không.

**Bước 7 — Theo dõi sau thay đổi.** Quan sát log từ chối, lỗi ứng dụng, dependency, độ trễ, cảnh báo availability và tái xuất hiện listener. Tự động so sánh với baseline và mở change ticket khi cần điều chỉnh.

### Tiêu chí đạt và điều kiện rollback (ví dụ)

| Điều kiện | Đạt khi | Hành động nếu không đạt |
|---|---|---|
| Dịch vụ thừa | Không chạy và không tự khởi động sau reboot/rolling restart | Kiểm tra socket activation, supervisor, policy automation; sửa theo change |
| Port không cần | Không còn listener, hoặc không còn đường tới từ vùng không được phép theo mục tiêu | Kiểm tra bind, IPv6, firewall, proxy/NAT, container mapping |
| Dịch vụ chính | API/DNS/VPN/routing/ứng dụng hoạt động đúng với phép thử đã định nghĩa | Rollback theo trạng thái đã lưu, điều tra phụ thuộc |
| Quản trị hợp lệ | Jump host/OOB, SSH/HTTPS, AAA và audit còn hoạt động | Dùng kênh OOB/console và rollback trước khi mất quyền điều khiển |
| Giám sát | Collector nhận dữ liệu, logs vẫn được gửi, dashboard không có lỗi mới | Kiểm tra luồng monitoring và điều chỉnh rule đúng phạm vi |

## 11. Tình huống điển hình và cách ra quyết định

### Tình huống A — Telnet mở trên thiết bị mạng

Phép kiểm tra từ VLAN người dùng phát hiện TCP/23 của switch. Chủ hệ thống xác nhận chỉ dùng SSH qua VLAN quản trị.

- **Kết luận:** Telnet server là tính năng dư thừa; mở từ user VLAN càng tăng rủi ro.
- **Xử lý:** xác nhận SSH/OOB đang hoạt động, xuất/backup cấu hình, tắt Telnet theo tài liệu thiết bị, áp ACL quản trị phù hợp, kiểm tra từ VLAN người dùng và management VLAN.
- **Chú ý:** không cắt đồng thời các đường quản trị trước khi xác minh truy cập thay thế.

### Tình huống B — Database mở ở mọi interface

PostgreSQL lắng nghe trên \`0.0.0.0:5432\` và security group cho phép truy cập từ toàn bộ VPC. Ứng dụng chỉ cần kết nối từ hai server trong application tier.

- **Kết luận:** Database **vẫn cần**, nhưng phạm vi tiếp cận rộng hơn mức cho phép.
- **Xử lý:** đánh giá HA/replication, backup, monitoring, DBA access; thu hẹp bind nếu phù hợp kiến trúc, firewall/security group và kiểm soát xác thực đến đúng nguồn.
- **Xác minh:** kết nối của hai server hợp lệ, replication/backup tiếp tục; các nguồn khác bị từ chối.

### Tình huống C — Dịch vụ tự mở lại sau reboot

Đội vận hành dừng một service debug trên Linux, kiểm tra port đã đóng. Sau reboot, service lại chạy và mở TCP/8080.

- **Nguyên nhân có thể:** unit còn \`enabled\`, socket activation, container restart policy, config management hoặc deployment template khôi phục trạng thái.
- **Xử lý:** kiểm tra cơ chế khởi chạy thực tế, sửa nguồn cấu hình hợp lệ và xác minh bằng restart/redeploy trong điều kiện kiểm soát.
- **Bài học:** đóng port tạm thời chưa đồng nghĩa hardening bền vững.

### Tình huống D — Chặn SMB làm hỏng hệ thống quản trị

Một quy tắc blanket deny TCP/445 được triển khai trên tất cả server. GPO, quản trị tệp, backup hoặc tác vụ nội bộ bị ảnh hưởng.

- **Nguyên nhân:** suy diễn “SMB nguy hiểm” thành “SMB không bao giờ cần”.
- **Xử lý:** rollback theo thay đổi đã lưu; xác định nguồn/đích cần SMB, chỉ cho phép cặp hợp lệ và ghi ngoại lệ có owner.
- **Bài học:** mục tiêu là **least functionality và least access**, không phải số cổng càng thấp càng tốt bằng mọi giá.

### Tình huống E — Metrics endpoint trên cloud

Một ứng dụng xuất Prometheus metrics qua TCP/9090. Endpoint bị public thông qua quy tắc load balancer, dù chỉ monitoring subnet cần.

- **Kết luận:** chức năng metrics hữu ích; việc public endpoint là sai phạm vi.
- **Xử lý:** giới hạn listener/ingress tới monitoring network hoặc đặt sau proxy có xác thực; rà Service/Ingress/NodePort hoặc security group liên quan.
- **Xác minh:** collector hợp lệ vẫn scrape được, Internet/VLAN người dùng không truy cập được.

### Tình huống F — Thiết bị Wi-Fi công bố trang quản trị

Access point cho phép web admin từ cùng SSID khách. Cổng HTTP/HTTPS mở dù cấu hình chỉ yêu cầu quản trị qua controller.

- **Xử lý:** xác minh quy trình provision và failover, tắt giao diện local không cần hoặc hạn chế đến management VLAN, kiểm tra cô lập guest, logging và firmware.
- **Giới hạn:** một số sản phẩm yêu cầu dịch vụ cục bộ cho khôi phục; cần duy trì đường cứu hộ theo tài liệu thiết bị.

## 12. Giám sát phát hiện dịch vụ hoặc cổng xuất hiện trở lại

Hardening chỉ có giá trị lâu dài khi phát hiện **configuration drift** và quá trình triển khai vô tình mở rộng bề mặt tấn công.

Các tín hiệu nên theo dõi:

- Listener mới trên \`0.0.0.0\` hoặc \`[::]\`, đặc biệt ở cổng quản trị hoặc debug.
- Service bị chuyển từ \`disabled\` sang \`enabled\`; role/package không được phê duyệt được cài mới.
- Firewall/security group có rule Allow mới từ \`0.0.0.0/0\` hoặc \`::/0\`, trừ trường hợp thực sự được thiết kế public.
- Container mới publish host port hoặc Ingress/NodePort mới xuất hiện.
- IP/port được phép qua phân đoạn thay đổi so với baseline; đường quản trị bỏ qua jump host.
- Một daemon đã tắt xuất hiện trở lại sau reboot, patch, cấu hình tự động hoặc redeploy.

Một cách tổ chức dữ liệu để so sánh là lưu tập hợp chuẩn hóa:

~~~text
(asset_id, network_namespace, ip_family, protocol,
 local_address, local_port, process_or_service, exposed_zone,
 approved_clients, configuration_owner)
~~~

Chạy so sánh theo lịch hoặc khi có thay đổi lớn; mỗi khác biệt được gắn với change ticket, owner và phân loại: **được phê duyệt**, **cần xác minh** hoặc **không phù hợp baseline**. Không tự động dừng mọi listener mới nếu chưa loại trừ trường hợp khẩn cấp hoặc dịch vụ thiết yếu; ưu tiên cảnh báo và luồng phê duyệt.

### Liên kết giám sát và phòng vệ nhiều lớp

- **Firewall/IDS/IPS:** phát hiện kết nối tới cổng bị cấm, bất thường east-west, nỗ lực khai thác dịch vụ quản trị cũ.
- **DNS và xác thực:** xác định tên/thiết bị mới, đăng nhập quản trị bất thường, thay đổi dịch vụ ngoài cửa sổ bảo trì.
- **Cấu hình mạng:** phát hiện thay đổi ACL, VPN policy, NAT, port forwarding, public endpoint và control-plane access.
- **CMDB/IaC/config management:** duy trì nguồn sự thật về cổng nào được phép tồn tại và lý do tồn tại.

## 13. Những sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Chặn port bằng firewall rồi coi service đã bị loại bỏ | Daemon vẫn tồn tại và có thể được truy cập từ đường khác hoặc mở lại | Dừng/tắt/gỡ nếu thật sự không cần, sau đó xác minh firewall và listener |
| Chỉ quét từ Internet | Bỏ sót VPN, VLAN người dùng, east-west, IPv6 và cloud peering | Kiểm tra từ nhiều vùng có mục đích rõ ràng |
| Không kiểm tra UDP | DNS, NTP, SNMP, discovery và nhiều protocol dùng UDP | Thu socket/flow và thử nghiệm giao thức phù hợp |
| Xóa mọi cổng không biết tên | Làm hỏng AD, DNS, cluster, backup, giám sát | Xác định owner và phụ thuộc trước khi thay đổi |
| Tin rằng \`disable\` bảo đảm service không chạy lại | Socket activation, container restart, automation có thể kích hoạt lại | Kiểm tra các cơ chế activation, reboot/redeploy và baseline |
| Thêm rule Allow giới hạn nhưng giữ rule Allow rộng | Quyền truy cập rộng có thể vẫn còn | Rà tất cả rule áp dụng và kiểm chứng từ vùng bị cấm |
| Quên IPv6 hoặc \`0.0.0.0\` | Listener trên các interface khác vẫn lộ | Kiểm tra IPv4, IPv6, loopback, interface và namespace |
| Tắt SSH/HTTPS quản trị trước khi có OOB | Có thể mất quyền điều khiển thiết bị từ xa | Kiểm thử kênh thay thế và có rollback/commit-confirm phù hợp |
| Không kiểm tra sau reboot/deploy | Hardening bị cấu hình cũ ghi đè | Giám sát drift và kiểm tra sau các sự kiện thay đổi |
| Kết luận \`filtered\` là \`closed\` | Nhầm trạng thái mạng với trạng thái dịch vụ | Đối chiếu listener nội bộ, firewall và kiểm tra từ đúng vị trí |

## 14. Checklist thao tác và câu hỏi luyện tập

### Checklist

- [ ] Xác định rõ vai trò thiết bị và owner của dịch vụ trước khi can thiệp.
- [ ] Có inventory của TCP/UDP, IPv4/IPv6, bind address, process và service/socket activation.
- [ ] Có baseline traffic, change ticket, phụ thuộc của ứng dụng và lịch vận hành quan trọng.
- [ ] Tách dịch vụ **không cần** khỏi dịch vụ **cần nhưng lộ quá rộng**.
- [ ] Đã chọn stop/disable/uninstall hoặc thu hẹp bind/ACL/firewall đúng mục đích.
- [ ] Đã kiểm tra kênh quản trị thay thế và lưu trạng thái/cấu hình phục hồi.
- [ ] Đã thử chức năng ứng dụng, xác thực, DNS/VPN, monitoring, backup và failover có liên quan.
- [ ] Đã xác minh từ host và từ các vùng mạng được phép/không được phép, bao gồm IPv6.
- [ ] Đã xác minh tính bền vững qua restart/redeploy nếu thuộc kế hoạch.
- [ ] Đã cập nhật baseline và cơ chế cảnh báo khi port/service thay đổi.

### Câu hỏi tự kiểm tra

1. Điểm khác nhau giữa \`ss\` hiển thị \`0.0.0.0:8080\`, firewall chặn 8080 từ Internet và việc tắt hẳn service 8080 là gì?
2. Vì sao phép quét thấy TCP/445 \`filtered\` chưa đủ chứng minh đã tắt SMB server?
3. Một database cần TCP/5432 từ đúng hai application server. Bạn sẽ tắt dịch vụ hay giới hạn quyền truy cập, và chứng minh kết quả như thế nào?
4. Vì sao phải kiểm tra systemd socket activation, container restart policy và IaC sau khi đã dừng daemon?
5. Khi hardening switch/router, những điểm khác nhau giữa management plane và control plane cần được chú ý?
6. Việc chỉ xóa \`containerPort\` khỏi Kubernetes manifest có bảo đảm cổng không mở nữa không? Vì sao?
7. Hãy lập ma trận luồng tối thiểu cho web frontend, application tier, database và jump host; mô tả hai phép thử chặn và hai phép thử cho phép.

**Điểm cần nhớ:** “Tắt dịch vụ và port không cần thiết” là một bài toán **xác định chức năng cần thiết và giới hạn truy cập theo vai trò**. Một kết quả hardening đạt yêu cầu khi dịch vụ dư thừa không còn vận hành, dịch vụ cần thiết chỉ lộ cho đúng đối tượng, hành vi hệ thống vẫn đáp ứng yêu cầu vận hành và các kiểm chứng có thể lặp lại.
