# Kiểm tra exposed management service

Trong hạ tầng bảo mật mạng, **management service** là dịch vụ để quản trị viên cấu hình, vận hành, giám sát hoặc điều khiển thiết bị và hệ thống. Ví dụ gồm SSH trên switch, giao diện web của firewall/router, RDP/WinRM trên máy chủ, SNMP, giao diện quản trị hypervisor, bộ điều khiển Wi-Fi và API quản lý cụm. Những dịch vụ này thường có quyền tác động cao: đổi định tuyến, điều chỉnh ACL, đọc thông tin cấu hình, quản lý tài khoản hoặc tắt dịch vụ quan trọng.

**Exposed management service** là dịch vụ quản trị có thể được tiếp cận từ một nguồn hoặc vùng mạng ngoài phạm vi được cho phép theo thiết kế. Không phải cứ mở cổng là đã có lỗ hổng; mục tiêu kiểm thử là xác định **ai có thể kết nối tới mặt phẳng quản trị, từ đâu, qua đường nào và với các lớp kiểm soát gì**.

Bài học thuộc chương **Kiểm thử và xác minh bảo mật mạng**, trong module SECURITY_NETWORK_SECURITY, liên hệ trực tiếp với phân đoạn mạng, firewall, VPN, xác thực kết nối, giám sát và mô hình hóa mối đe dọa.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân loại các dịch vụ quản trị thường gặp, gồm cổng TCP/UDP, web UI, API và kênh out-of-band.
- Phân biệt dịch vụ lắng nghe, dịch vụ có thể tiếp cận và dịch vụ bị phơi lộ **sai chính sách**.
- Lập ma trận truy cập mong đợi và chọn nhiều vị trí kiểm thử để kiểm tra phân đoạn mạng.
- Thực hiện phép đo mạng có tác động thấp, diễn giải đúng kết quả và ghi bằng chứng tái lập.
- Đánh giá tác động của ACL, NAT, security group, VPN, IPv4/IPv6 và xác thực quản trị.
- Đề xuất cách khắc phục theo nhiều lớp và kiểm thử lại mà vẫn duy trì đường quản trị hợp lệ.

## 2. Xác định đúng khái niệm “exposed”

Ba mức đánh giá cần phân biệt:

| Mức | Điều cần chứng minh | Bằng chứng phù hợp |
| --- | --- | --- |
| Đang lắng nghe | Một tiến trình trên thiết bị mở cổng ở interface nào? | Cấu hình, bảng socket hoặc trạng thái dịch vụ được nhà cung cấp hỗ trợ |
| Có thể kết nối từ một nguồn | Máy ở vùng kiểm thử có đến được cổng/dịch vụ đích không? | Kết nối TCP/UDP, phản hồi giao thức, log thiết bị |
| Bị phơi lộ sai thiết kế | Nguồn nói trên có bị chính sách yêu cầu từ chối hay không? | Ma trận truy cập, sơ đồ vùng mạng, phê duyệt của asset owner |

Ví dụ: quản trị viên kết nối SSH tới switch từ bastion trong VLAN quản trị là **đường truy cập mong đợi**. Nếu máy khách trong VLAN Guest cũng kết nối được tới SSH của switch, đó là dấu hiệu **phân đoạn chưa đúng** dù SSH vẫn yêu cầu khóa đăng nhập.

Một trang quản trị trả HTTP 401 hoặc 403 từ Internet vẫn có thể chứng minh **endpoint nhận được yêu cầu**. Nó cho thấy có lớp xác thực/ủy quyền hoặc từ chối ở tầng ứng dụng, chưa chứng minh giao diện đã được cô lập ở tầng mạng. Ngược lại, cổng được báo filtered từ một máy kiểm thử không có nghĩa tất cả nguồn khác đều bị chặn.

**Exposure không đồng nghĩa compromise.** Kiểm tra đường kết nối không tự chứng minh khả năng đăng nhập trái phép, khai thác CVE hay thay đổi cấu hình.

## 3. Bản đồ các dịch vụ quản trị thường gặp

Port trong bảng chỉ là **mặc định hoặc thường thấy**; nhiều thiết bị dùng cổng tùy biến, proxy hoặc controller trung gian.

| Nhóm dịch vụ | Cổng thường gặp | Rủi ro khi lộ ra nguồn không tin cậy |
| --- | --- | --- |
| SSH trên router/switch/Linux | TCP 22 | Mở bề mặt xác thực, lỗ hổng daemon/firmware, nguy cơ thay đổi cấu hình |
| Telnet | TCP 23 | Truyền thông không mã hóa; nguy cơ lộ mật khẩu/lệnh |
| Web UI HTTP/HTTPS | TCP 80, 443, 8080, 8443 | Lộ trang đăng nhập, API đặc quyền hoặc bề mặt lỗi ứng dụng web |
| RDP | TCP/UDP 3389 | Truy cập desktop quản trị, nguy cơ thử thông tin đăng nhập hoặc lỗi dịch vụ |
| WinRM | TCP 5985, 5986 | Truy cập tác vụ quản trị từ xa và quyền hệ thống |
| SNMP | UDP 161; trap UDP 162 | Lộ thông tin mạng, cấu hình; có thể ghi thay đổi nếu phân quyền sai |
| IPMI/BMC | UDP 623, cùng web/SSH tùy model | Điều khiển phần cứng, nguồn và console ngoài hệ điều hành |
| Controller Wi-Fi, SDN, hypervisor | Chủ yếu HTTPS, cổng tùy hãng | Quyền điều khiển tập trung nhiều thiết bị hoặc workload |
| Kubernetes API / kubelet | TCP 6443, 10250 thường gặp | API hạ tầng có thể ảnh hưởng tới toàn cụm nếu chính sách yếu |
| API quản trị ứng dụng, database hoặc message broker | Tùy phần mềm | Quản lý tài khoản, cấu hình, dữ liệu hoặc các tác vụ vận hành |

Lưu ý: dịch vụ trên TCP 443 có thể chỉ là ứng dụng phục vụ người dùng. Để xác định có phải management UI, cần kết hợp inventory, DNS, tên chứng chỉ, HTTP response, URL theo tài liệu, cấu hình và xác nhận từ chủ hệ thống. **Không gán nhãn quản trị chỉ dựa trên port.**

Ngoài dịch vụ trực tiếp còn có interface phụ, IPMI/iLO/iDRAC, console server, remote management agent, reverse tunnel, NAT port forwarding, kênh VPN và cloud control plane. Một số đường không hiển thị trong một lần quét TCP trên địa chỉ chính.

## 4. Mô hình đe dọa

Một dịch vụ quản trị được đặt sai ranh giới có thể tạo đường tấn công:

1. **Reconnaissance:** đối tượng trong vùng không tin cậy phát hiện port và giao diện đăng nhập.
2. **Tiếp cận giao thức:** tương tác với SSH, HTTPS, RDP, SNMP hoặc API.
3. **Lợi dụng điểm yếu:** lỗi firmware, cấu hình TLS/SSH, mật khẩu yếu, phân quyền không đúng hoặc thông tin xác thực bị đánh cắp.
4. **Đặc quyền quản trị:** nếu vượt qua kiểm soát, đối tượng có thể sửa routing/ACL, thêm tài khoản, thay đổi VPN hoặc truy cập tài sản khác.
5. **Duy trì và che giấu:** cấu hình sai có thể làm thay đổi log, luồng lưu lượng hoặc hành vi giám sát.

Đây là **mô hình khả năng**, không phải các bước phải thực hiện trong kiểm thử. Đối với mục tiêu xác minh exposure, thông thường chỉ cần chứng minh đường kết nối trái chính sách và lấy bằng chứng cấu hình; không cần thử xâm nhập.

## 5. Chuẩn bị phạm vi và ma trận truy cập

Trước khi kiểm thử, xác định tài sản và mạng **đã được ủy quyền**: IP/FQDN, người chịu trách nhiệm, thời gian, giới hạn tốc độ, cổng và nguồn được phép sử dụng. Với thiết bị vận hành nhạy cảm, thống nhất điểm dừng khi xuất hiện lỗi. Không thử mật khẩu, khai thác lỗ hổng hay quét tải cao trong bài kiểm tra đường quản trị.

Ví dụ kiến trúc có:

- **Internet:** mọi nguồn bên ngoài và chưa kết nối VPN doanh nghiệp.
- **VLAN người dùng (10.20.0.0/24):** máy tính nhân viên.
- **VLAN khách:** Wi-Fi guest và thiết bị cá nhân.
- **Mạng quản trị (10.30.0.0/24):** router/switch/controller được quản trị qua VPN và bastion.

| Nguồn kiểm thử | Đích, dịch vụ | Mong đợi | Lý do |
| --- | --- | --- | --- |
| Internet | Public IP firewall, HTTPS quản trị | DENY | Không công bố trực tiếp giao diện cấu hình |
| VLAN người dùng | 10.30.0.10, SSH switch | DENY | Ngăn tiếp cận mặt phẳng điều khiển từ máy đầu cuối |
| VLAN khách | 10.30.0.20, HTTPS controller | DENY | Cách ly thiết bị khách khỏi quản trị hạ tầng |
| VPN + bastion có xác thực | 10.30.0.10, SSH | ALLOW có điều kiện | Đường bảo trì được phê duyệt |
| Mạng đối tác | 10.30.0.30, WinRM | DENY nếu không có ngoại lệ | Giảm truy cập giữa các miền tin cậy |
| VLAN quản trị | 10.30.0.20, HTTPS controller | ALLOW có điều kiện | Quản trị đúng vai trò, đúng thiết bị |

Địa chỉ trên chỉ là ví dụ mạng riêng. Tùy hệ thống, Internet có thể truy cập một bastion được cấu hình có chủ đích với MFA và theo dõi phiên; điều quan trọng là **đường truy cập phù hợp chính sách được phê duyệt**.

Bổ sung ma trận cho các interface vật lý/ảo, site-to-site VPN, đối tác, cloud VPC/VNet, đường backup, NAT và IPv6. Nếu thiếu chính sách nguồn/đích chính thức, cần xác nhận với asset owner trước khi gán trạng thái FAIL.

## 6. Điểm quan sát (vantage point) và ranh giới mạng

Một lần quét từ máy admin trong mạng quản trị không thể chứng minh rằng Internet hoặc VLAN khách bị chặn. Cần thực hiện thử nghiệm riêng từ:

1. **Ngoài Internet và ngoài VPN:** đánh giá mặt phẳng quản trị công khai.
2. **VLAN nhân viên/guest/IoT:** đánh giá phân đoạn và khả năng lateral movement.
3. **DMZ, mạng đối tác, site-to-site VPN hoặc cloud peering:** đánh giá đường xuyên miền tin cậy.
4. **Bastion hoặc VLAN quản trị:** làm phép kiểm tra dương, chứng minh nguồn hợp lệ vẫn có thể sử dụng dịch vụ.

~~~mermaid
flowchart LR
    I["Internet"] -->|"Mong đợi: DENY"| F["Firewall WAN admin"]
    G["Guest VLAN"] -->|"Mong đợi: DENY"| C["Wi-Fi controller"]
    U["User VLAN"] -->|"Mong đợi: DENY"| S["Switch SSH"]
    B["VPN + bastion"] -->|"Mong đợi: ALLOW"| M["Management VLAN"]
    M --> S
    M --> C
~~~

Khi dùng Zero Trust, endpoint posture hoặc policy theo user, hai máy thuộc cùng subnet vẫn có thể có quyền khác nhau. Ghi rõ nguồn thực tế, user/role (nếu liên quan), egress IP và thời điểm, tránh suy rộng kết quả cho mọi máy trong vùng.

## 7. Kiểm kê trước khi kiểm thử mạng

Lập bản ghi cho mỗi tài sản:

- ID tài sản, owner, môi trường (production, staging), model, firmware/OS.
- IP quản trị, IP WAN, FQDN, địa chỉ IPv6 và interface thứ cấp.
- Dịch vụ quản trị bật, cổng, giao thức, bind address, đường controller.
- Nơi cấu hình ACL: control plane, firewall biên, NAT/DNAT, cloud security group, reverse proxy, policy VPN.
- Quyền truy cập dự kiến: subnet, bastion, tài khoản, MFA, nhóm vận hành.
- Mức quan trọng, kế hoạch khôi phục và lưu log.

Nguồn kiểm kê phù hợp có thể gồm CMDB, cấu hình thiết bị, sơ đồ mạng, bảng định tuyến, cloud inventory và xác nhận của chủ hệ thống. Với thiết bị đang vận hành, ưu tiên lệnh trạng thái read-only theo hướng dẫn hãng. Không thay đổi cấu hình chỉ để làm rõ kết quả.

## 8. Kiểm tra TCP với tác động thấp

Trong ví dụ này, **192.0.2.10** là địa chỉ tài liệu dành cho minh họa (RFC 5737), không phải mục tiêu thật. Trước khi chạy cần thay bằng tài sản đã được phép kiểm thử và giới hạn port theo phạm vi.

~~~bash
# Từ máy nguồn thuộc vùng đã được cấp quyền:
# Kiểm tra khả năng kết nối TCP tới các cổng quản trị được duyệt.
nmap -sT -p 22,23,80,443,3389,5985,5986,8080,8443,6443,10250 192.0.2.10

# Nếu port mở và chủ hệ thống cho phép nhận diện dịch vụ:
nmap -sT -sV --version-light -p 22,443,8443 192.0.2.10
~~~

Ý nghĩa trạng thái thường gặp:

| Kết quả | Ý nghĩa | Điều không nên suy diễn |
| --- | --- | --- |
| open | Scanner thấy cổng TCP chấp nhận kết nối tại thời điểm đo | Không tự chứng minh đăng nhập thành công hoặc có CVE |
| closed | Host phản hồi rằng cổng chưa chấp nhận kết nối | Không đảm bảo các interface/nguồn khác cũng đóng |
| filtered | Gói bị chặn hoặc không có đủ phản hồi để xác định chắc | Không chứng minh thiết bị hoàn toàn an toàn |
| Host seems down | Không có phản hồi phát hiện host theo cách công cụ đang dùng | Có thể do ICMP/firewall; chưa khẳng định thiết bị không tồn tại |

Các probe nhận diện phiên bản có thể tạo traffic khác TCP connect cơ bản, vì vậy chỉ chạy khi nằm trong phạm vi đã thống nhất. Banner phiên bản có thể bị che, giả mạo hoặc không phản ánh bản vá thực tế; **không suy ra một CVE chỉ từ banner**.

Nếu cổng có thể kết nối từ Internet trong khi ma trận yêu cầu DENY, đã có một phát hiện cần điều tra. Nếu port open từ bastion và được phép thì đó là hành vi mong đợi; vẫn cần kiểm tra cơ chế bảo vệ theo tiêu chí của tổ chức.

## 9. Nhận diện HTTP/TLS và API quản trị

Với cổng web đã được phép kiểm tra, một request nhẹ có thể giúp xác định endpoint. **mgmt.example.test** là tên miền mẫu, không phải hệ thống thật.

~~~bash
# Xem HTTP status/header với giới hạn thời gian kết nối.
# Không dùng tùy chọn bỏ qua kiểm tra chứng chỉ.
curl -I --connect-timeout 3 --max-time 7 https://mgmt.example.test/

# Quan sát trạng thái bắt tay TLS và chứng chỉ khi có OpenSSL.
openssl s_client -connect mgmt.example.test:443 -servername mgmt.example.test -brief < /dev/null
~~~

Các kết quả HTTP **200, 301, 302, 401, 403** đều có thể chứng minh endpoint phản hồi mạng. Mã 401/403 cho biết một lớp kiểm soát hoạt động, chưa phải chứng cứ đủ để kết luận hệ thống không exposed. Một số server từ chối phương thức HEAD bằng 405 nhưng vẫn phục vụ GET; chỉ thử thêm khi có phạm vi cho phép.

Từ chứng chỉ và phản hồi, có thể ghi nhận tên host, giao thức TLS, redirect, trạng thái chứng chỉ và kiểu endpoint, nhưng tránh tiết lộ thông tin đăng nhập, token, session cookie và dữ liệu cấu hình nhạy cảm. Không thử chức năng thay đổi cấu hình hoặc API đặc quyền trong bước kiểm tra exposure.

**HTTPS không thay thế phân đoạn.** TLS bảo vệ dữ liệu trên đường truyền, còn giới hạn nguồn nào được chạm đến cổng quản trị là nhiệm vụ của ACL, firewall, VPN/bastion và policy kết nối.

## 10. UDP, SNMP, BMC và các đường quản trị phụ

SNMP thường chạy UDP 161; BMC/IPMI có thể dùng UDP 623 cùng web/SSH tùy model. Kết quả UDP có thể mơ hồ vì thiếu phản hồi. Một port được công cụ báo **open|filtered** không thể coi là đã xác nhận quyền truy cập SNMP hoặc IPMI.

Cách xác minh có tác động thấp:

1. Đọc cấu hình dịch vụ và interface lắng nghe từ hệ thống quản trị được phép.
2. Đối chiếu ACL của SNMP/BMC và firewall trên đường từ từng vùng nguồn.
3. Dùng phép thử kết nối/đọc thông tin tối thiểu đã được asset owner đồng ý nếu cần.
4. Xem log hoặc flow record để xác định lưu lượng thực sự đến được đích.
5. Báo rõ **giới hạn quan sát** khi không thể phân biệt blocked với no response.

Không dò community string, thử credential hoặc gửi lệnh SNMP SET/IPMI điều khiển nguồn nếu mục đích chỉ là kiểm tra phơi lộ.

Phải xét thêm:

- **IPv6:** host có thể có địa chỉ global và rule bảo mật khác IPv4.
- **NAT/port forwarding:** port public có thể chuyển tiếp vào management IP không nhìn thấy trực tiếp.
- **Đường failover:** link dự phòng hoặc chính sách HA có thể công bố port khi chuyển trạng thái.
- **DNS cũ và IP phụ:** DNS không còn bản ghi chưa đảm bảo IP không còn truy cập được; DNS có bản ghi cũng chưa chứng minh có đường kết nối.
- **Cloud security group/NACL:** quy tắc cho phép quá rộng, IPv6 ::/0 hoặc mở từ peering/VPN.
- **Out-of-band network:** giao diện BMC có thể bỏ qua nhiều biện pháp bảo vệ ở hệ điều hành máy chủ.

## 11. Truy nguyên nguyên nhân phơi lộ

Nếu từ vùng không tin cậy kết nối được tới port quản trị, lần theo đường đi:

1. IP và interface thực của nguồn/đích, DNS và NAT mapping.
2. Route, security group, NACL, firewall rule và thứ tự áp dụng quy tắc.
3. Control-plane ACL hoặc giới hạn allowed management hosts của thiết bị.
4. Reverse proxy, load balancer, VPN, SD-WAN và controller trung gian.
5. Log cùng timestamp tại firewall, thiết bị, bastion và hệ thống giám sát.
6. Lịch sử thay đổi, ngoại lệ tạm thời và rule tự động sinh bởi hệ thống triển khai.

Ví dụ một rule WAN cho TCP 443 có thể được tạo để phục vụ web ứng dụng nhưng vô tình chuyển tiếp tới trang quản trị firewall. Việc sửa đúng rule và bind interface sẽ giải quyết gốc phơi lộ; chỉ thay cổng 443 thành 8443 không làm hẹp nguồn có thể truy cập.

## 12. Đánh giá lớp bảo vệ xác thực và hardening

Khi đã nhận diện quản trị và đường vào, đối chiếu các lớp phòng thủ với cấu hình hoặc bằng chứng được cấp quyền:

| Lớp kiểm soát | Cần xác nhận | Dấu hiệu cần điều tra |
| --- | --- | --- |
| Phân đoạn | Chỉ nguồn trong management subnet hoặc bastion hợp lệ | Port quản trị mở từ Internet/guest/user VLAN |
| Giao thức | SSH, HTTPS, SNMPv3 khi sản phẩm hỗ trợ | Telnet, HTTP rõ văn bản, SNMP v1/v2c bị mở rộng |
| Xác thực | Tài khoản cá nhân, MFA ở đường vào phù hợp, không còn mặc định | Tài khoản dùng chung, xác thực chưa đạt chính sách |
| Phân quyền | RBAC, quyền tối thiểu, read-only theo vai trò | Người vận hành thông thường có quyền admin không cần thiết |
| Session/audit | Session timeout, log và alert, quản lý thay đổi | Không truy vết được đăng nhập hoặc thay đổi |
| Mật mã | TLS/SSH algorithm và chứng chỉ còn phù hợp | Chứng chỉ sai host/hết hạn, thuật toán lỗi thời |
| Firmware/OS | Phiên bản còn hỗ trợ, quy trình vá có kiểm chứng | Thiết bị EOL/EOS hoặc chưa xử lý advisory có liên quan |
| Quản lý sự cố | Cảnh báo truy cập trái phép và rule drift | Không nhận biết được kết nối từ vùng không tin cậy |

**MFA không phải lý do để mở management UI cho toàn Internet** nếu thiết kế yêu cầu VPN/bastion. Ngược lại, cổng quản trị có thể được phân đoạn đúng nhưng vẫn nguy hiểm nếu dùng Telnet hoặc credential mặc định. Kiểm thử bảo mật cần đánh giá đồng thời ranh giới kết nối và quyền quản trị.

Không kết luận “mật khẩu yếu”, “bypass đăng nhập” hay “chiếm được hệ thống” nếu chưa có bằng chứng thích hợp. Bài kiểm tra này chủ yếu xác minh exposure; các kiểm tra xác thực/chuyên sâu phải có phạm vi riêng.

## 13. Chấm mức độ rủi ro theo bối cảnh

Mức ưu tiên phụ thuộc **nguồn truy cập, quyền tác động, khả năng kiểm soát, lỗ hổng đã xác minh và độ quan trọng của tài sản**, không đơn thuần là cổng.

| Kịch bản | Mức ưu tiên tham khảo | Lập luận |
| --- | --- | --- |
| Trang quản trị firewall từ Internet trái chính sách | Cao; có thể khẩn cấp | Giao diện đặc quyền cao tiếp cận bởi nguồn rộng |
| Telnet tới router từ VLAN người dùng | Cao | Không mã hóa và không bảo đảm phân đoạn |
| BMC/IPMI từ mạng khách | Cao | Có thể ảnh hưởng điều khiển phần cứng/console |
| HTTPS quản trị chỉ từ bastion, IAM/MFA và log phù hợp | Truy cập mong đợi | Ranh giới và kiểm soát vận hành đã được thiết lập |
| Public endpoint trả 403, chưa rõ là app hay quản trị | Cần điều tra thêm | Chưa phân loại được chức năng và chính sách liên quan |
| SSH của bastion công khai có chủ đích, xác thực chặt | Tùy thiết kế | Cần review nguồn, MFA, key, phiên và giám sát |

Đây là ví dụ để **triage**, không phải thang điểm CVSS. Với lỗ hổng sản phẩm cụ thể, cần đối chiếu advisory, build chính xác, điều kiện khai thác và kiểm soát giảm thiểu. Đánh giá rủi ro nên ghi rõ giả định và bằng chứng thiếu.

## 14. Cách khắc phục an toàn

### 14.1. Giảm bề mặt quản trị

- Tắt dịch vụ không dùng, đặc biệt Telnet và HTTP quản trị không mã hóa.
- Chỉ bind management service vào interface hoặc IP quản trị được phép khi thiết bị hỗ trợ.
- Áp dụng **deny by default** vào mạng quản trị, cho phép đúng nguồn, đích, cổng, role và thời gian cần thiết.
- Đưa truy cập từ xa qua VPN hoặc bastion được kiểm soát, có MFA và log phiên phù hợp.
- Loại bỏ NAT/port forwarding ngoài dự kiến; rà soát cloud security group, NACL và cả IPv6.
- Tách mạng BMC/out-of-band và giới hạn nguồn tương đương hoặc chặt hơn mạng quản trị thường.

### 14.2. Gia cố xác thực và giám sát

- Dùng SSH/HTTPS an toàn và SNMPv3 theo khả năng hỗ trợ; quản lý vòng đời chứng chỉ và khóa.
- Vô hiệu hóa hoặc đổi credential mặc định; dùng tài khoản định danh cá nhân, RBAC, quyền tối thiểu và MFA ở lớp thích hợp.
- Cập nhật firmware/OS, kiểm tra nguồn và chữ ký bản cập nhật trước triển khai.
- Ghi log đăng nhập quản trị, thay đổi cấu hình, kết nối trái phép và thay đổi firewall rule; tập trung log để điều tra.
- Định kỳ rà soát ngoại lệ, rule mở rộng, địa chỉ quản trị mới và quyền truy cập của đối tác.

Ví dụ pseudo-policy minh họa ý định, **không phải cú pháp của một hãng thiết bị**:

~~~text
ALLOW src=BASTION_IP    dst=SWITCH_MGMT      tcp=22
ALLOW src=MGMT_VPN      dst=FIREWALL_MGMT    tcp=443
ALLOW src=NMS_IP        dst=DEVICE_MGMT      udp=161
DENY  src=ANY_OTHER     dst=MGMT_SUBNET      tcp=22,23,80,443,3389,5985,5986
DENY  src=ANY_OTHER     dst=MGMT_SUBNET      udp=161,623
LOG   denied_management_access
~~~

Trong thực tế, cần bao phủ cổng tùy biến, IPv4/IPv6, rule precedence, route và yêu cầu vận hành của từng thiết bị. Không sao chép mẫu nguyên trạng vì có thể chặn nhầm các luồng quản trị cần thiết.

## 15. Báo cáo bằng chứng có thể tái lập

Mẫu ghi nhận phát hiện giả lập:

~~~text
Finding ID: NET-MGMT-007
Tên: Giao diện HTTPS quản trị firewall tiếp cận từ Internet
Tài sản: FW-EDGE-01, IP đích thuộc phạm vi được phê duyệt
Nguồn kiểm thử: máy ngoài VPN, ghi rõ public egress IP
Thời gian: 2026-11-28 14:00 +07:00 [chỉ là ví dụ]
Mong đợi: DENY theo ma trận truy cập
Thực tế: TCP/443 open; HTTP 401, không thử đăng nhập
Phân loại: Management UI, đã xác minh với asset owner
Nguyên nhân nghi vấn: WAN management access rule
Tác động: Mở bề mặt tấn công của thiết bị bảo mật biên
Khắc phục: Giới hạn vào VPN/bastion; rà soát ACL, NAT và IPv6
Bằng chứng: output phép thử, rule ID, log firewall và timestamp
Giới hạn: Chưa kiểm thử đăng nhập hoặc khả năng khai thác
~~~

Một báo cáo hữu ích có nguồn, đích, cổng, thời gian, quyền kiểm thử, chính sách mong đợi, kết quả thực tế, bằng chứng và đề nghị khắc phục cụ thể. Che thông tin nhạy cảm khi chia sẻ; không đưa mật khẩu, token, cookie, private key hoặc backup chứa secret vào báo cáo.

## 16. Kiểm thử lại sau khi xử lý

Sau khi đội vận hành sửa rule, giao diện bind hoặc thay đường quản trị, kiểm tra **cùng tiêu chí** từ các nguồn đã dùng ban đầu:

| Luồng | Trước sửa giả định | Sau sửa mong đợi |
| --- | --- | --- |
| Internet → firewall HTTPS quản trị | TCP open, HTTP 401 | Bị chặn bởi chính sách |
| VLAN người dùng → switch SSH | TCP open | Không thể kết nối |
| Guest → controller HTTPS | TCP open | Không thể kết nối |
| VPN/bastion → switch SSH | Truy cập hợp lệ | Vẫn quản trị được và có log |
| IPv6 Internet → địa chỉ quản trị | Có thể tiếp cận | Bị chặn theo cùng chính sách |
| Hệ thống giám sát → thiết bị | Hoạt động | Không bị gián đoạn |

**Không coi thiết bị mất kết nối hoàn toàn là một remediation thành công.** Cần chứng minh nguồn không được phép bị chặn trong khi nguồn hợp lệ vẫn hoạt động, các dịch vụ mạng bình thường và log ghi nhận đúng thay đổi.

Ghi bằng chứng trước/sau, xác nhận owner, theo dõi hậu thay đổi. Nếu có rủi ro mất quản trị từ xa, chuẩn bị console/out-of-band hoặc lịch bảo trì thích hợp trước khi áp dụng policy.

## 17. Theo dõi phơi lộ trong vận hành lâu dài

Một bản vá hay rule đúng hôm nay có thể bị đảo ngược sau khi tạo VM, đổi firewall, bật IPv6, chuyển site, thêm VPN đối tác hoặc cập nhật firmware. Nên kết hợp:

- Kiểm kê management interface từ CMDB, cloud inventory và cấu hình mạng.
- Kiểm tra định kỳ từ Internet và các vùng nội bộ được ủy quyền; ưu tiên sau thay đổi firewall, NAT, VPN và thiết bị.
- Policy-as-code/IaC để phát hiện rule mở cổng quản trị cho 0.0.0.0/0, ::/0 hoặc subnet vượt chính sách.
- Review security group, rule any/any, exception hết hạn, interface phụ và đường failover.
- Cảnh báo kết nối quản trị bất thường từ firewall/IDS/IPS, log VPN, bastion và thiết bị đích.
- Ticket với owner, hạn xử lý, bằng chứng sửa và kết quả retest.

Góc nhìn bên ngoài giúp phát hiện phơi lộ Internet; kiểm thử từ VLAN, VPN và cloud peering mới phát hiện nhiều trường hợp lan truyền ngang. Cần cả hai để đánh giá đúng bề mặt quản trị.

## 18. Tình huống luyện tập

### Tình huống A — HTTPS có password nhưng public

Quét ngoài VPN thấy trang quản trị firewall trên cổng 443 trả HTTP 401. Nhóm vận hành nói hệ thống an toàn vì có password mạnh.

**Nhận xét:** endpoint quản trị đang tiếp cận từ nguồn không được phép nếu chính sách yêu cầu qua VPN. Kiểm tra WAN setting, ACL/NAT, thu hẹp đường vào, rồi xác minh Internet bị chặn và bastion vẫn kết nối được.

### Tình huống B — SSH switch từ VLAN khách

Máy thuộc Wi-Fi guest kết nối TCP thành công tới SSH switch, nhưng không biết thông tin đăng nhập.

**Nhận xét:** đã có dấu hiệu thiếu phân đoạn. Không cần thử mật khẩu để chứng minh khả năng tiếp cận sai chính sách. Sửa source ACL và firewall segmentation, retest từ khách và mạng quản trị.

### Tình huống C — IPv4 được chặn, IPv6 bị bỏ quên

Thiết bị mạng có địa chỉ IPv6 global. Chính sách firewall IPv4 chặn web UI từ Internet, nhưng rule IPv6 vẫn cho phép truy cập trang quản trị.

**Nhận xét:** đánh giá chỉ dựa vào IPv4 sẽ bỏ sót đường quản trị. Cần xem interface binding và bảo đảm rule tương đương cho cả IPv4/IPv6.

### Tình huống D — Public HTTPS trả 403 qua reverse proxy

Một endpoint trả 403; banner cho thấy reverse proxy nhưng không rõ backend là cổng quản trị hay ứng dụng người dùng.

**Nhận xét:** có phản hồi mạng nhưng chưa đủ bằng chứng phân loại là management service. Đối chiếu proxy routing, CMDB và asset owner trước khi gán finding nghiêm trọng.

## 19. Checklist cuối bài

| Hạng mục | Tiêu chí đạt |
| --- | --- |
| Phạm vi và quyền kiểm thử | Có tài sản, nguồn, thời gian, tốc độ và owner rõ ràng |
| Inventory | Đã xác định IP/FQDN, interface, cổng và các đường quản trị |
| Ma trận | Có ALLOW/DENY mong đợi theo từng vùng |
| Nguồn đo | Có Internet, user/guest, partner/cloud và bastion nếu liên quan |
| TCP/UDP | Diễn giải trạng thái đúng, không suy diễn khả năng khai thác |
| IPv6/NAT/HA | Đã kiểm tra các đường phụ và failover |
| Xác thực | Có bằng chứng phù hợp cho MFA, RBAC, phiên và log |
| Báo cáo | Tái lập được nguồn, đích, thời điểm, kết quả và rule |
| Khắc phục | Đã thu hẹp bề mặt và loại bỏ dịch vụ không cần |
| Retest | Nguồn trái phép bị chặn, nguồn hợp lệ còn hoạt động |
| Theo dõi | Có quy trình phát hiện drift và owner xử lý |

## 20. Câu hỏi tự kiểm tra

1. Cổng HTTPS quản trị trả **HTTP 403** từ Internet có đủ chứng minh giao diện không bị phơi lộ không? Vì sao?
2. Vì sao một cổng **filtered** từ VLAN người dùng vẫn có thể tiếp cận được từ mạng đối tác hoặc IPv6?
3. Một switch chỉ cho phép SSH bằng khóa nhưng guest VLAN vẫn kết nối TCP thành công. Vấn đề nào đã được xác minh và vấn đề nào chưa?
4. Nêu sự khác nhau giữa kiểm thử Internet exposure và kiểm thử phân đoạn nội bộ.
5. Vì sao thay cổng SSH mặc định không thay thế việc giới hạn nguồn truy cập?
6. Cần thu thập những bằng chứng nào để chủ hệ thống tái lập phát hiện và xác minh sau sửa?
7. Sau khi chặn mọi truy cập tới management subnet, phép kiểm tra nào bảo đảm hoạt động vận hành không bị gián đoạn?

**Ghi nhớ:** kiểm tra exposed management service là phép xác minh **đường tới mặt phẳng quản trị từ các miền tin cậy khác nhau**, đối chiếu trực tiếp với chính sách mạng. Phát hiện cần có bằng chứng tiếp cận thực tế, đánh giá các lớp xác thực và phân đoạn, giải pháp khắc phục nguyên nhân, cùng kiểm thử lại cả luồng bị chặn lẫn luồng được phép.
