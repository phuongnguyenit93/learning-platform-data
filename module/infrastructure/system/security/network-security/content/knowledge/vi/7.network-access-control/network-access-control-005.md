# Host firewall: Kiểm soát truy cập mạng tại máy chủ và thiết bị đầu cuối

## 1. Host firewall là gì?

**Host firewall** (tường lửa trên máy, hay *host-based firewall*) là cơ chế lọc kết nối mạng được triển khai ngay trên máy chủ, máy trạm, máy ảo hoặc thiết bị đầu cuối. Nó áp dụng chính sách lên lưu lượng **đi vào**, **đi ra**, và trong một số vai trò đặc biệt là **đi xuyên qua** máy đó. Các điều kiện thường gồm địa chỉ IP, giao thức, cổng, giao diện mạng, trạng thái kết nối hoặc danh tính ứng dụng nếu nền tảng hỗ trợ.

Đây là bài **Host firewall** thuộc chương **Network access control**, trong học phần **SECURITY_NETWORK_SECURITY**. Chủ đề liên kết trực tiếp với phân đoạn mạng, firewall biên, VPN, xác thực kết nối, IDS/IPS, giám sát lưu lượng và thiết kế kiến trúc phòng vệ nhiều lớp. Một hệ thống có thể được bảo vệ bởi firewall mạng nhưng vẫn cần host firewall để hạn chế các kết nối không mong muốn từ mạng nội bộ hoặc từ đường truy cập ít được kiểm soát.

**Tình huống điển hình:** một máy chủ web cần nhận HTTPS từ reverse proxy và SSH từ mạng quản trị. Nếu máy chủ vô tình lắng nghe một cổng cơ sở dữ liệu trên tất cả interface, host firewall có thể giúp ngăn truy cập không được phê duyệt đến cổng đó, ngay cả khi cấu hình ứng dụng chưa kịp sửa.

Sau bài học, bạn có thể:

- Phân biệt host firewall, network firewall, cấu hình socket lắng nghe và xác thực ứng dụng.
- Giải thích inbound, outbound, forwarded traffic, stateful filtering và default deny.
- Thiết kế rule theo nhu cầu nghiệp vụ và kiểm tra hiệu lực từ đúng vị trí nguồn.
- Đọc cấu hình cơ bản trên Linux và Windows mà không làm gián đoạn dịch vụ.
- Liên hệ host firewall với VM, container, cloud, VPN, logging và xử lý sự cố mạng.

## 2. Vị trí trong mô hình phòng vệ nhiều lớp

~~~mermaid
flowchart LR
    Client[Client] --> NetFW[Network firewall / ACL]
    NetFW --> HostFW[Host firewall trên máy đích]
    HostFW --> Socket[Socket TCP hoặc UDP]
    Socket --> App[Ứng dụng]
    App -. Phản hồi .-> HostFW
~~~

Một kết nối đi đến máy chủ thường phải đáp ứng **đồng thời** các điều kiện định tuyến, quy tắc mạng, quy tắc trên host, trạng thái dịch vụ và quyền truy cập của ứng dụng. Cho phép một cổng trên host firewall không làm dịch vụ tự động lắng nghe. Ngược lại, dịch vụ đã lắng nghe trên địa chỉ công cộng cũng không nhất thiết truy cập được nếu một lớp kiểm soát chặn gói.

| Cơ chế | Vị trí phổ biến | Chức năng | Điều không thể kết luận từ cơ chế đó |
| --- | --- | --- | --- |
| Route table | Router, host, VPC/VNet | Chọn next hop/đường đi | Có route chưa chắc được truy cập |
| Network firewall/ACL | Biên hoặc giữa vùng mạng | Cho phép/chặn luồng qua điểm kiểm soát | Không bảo đảm mọi luồng nội bộ đều đi qua nó |
| **Host firewall** | Máy nhận hoặc gửi kết nối | Lọc trực tiếp các luồng của máy | Không thay thế xác thực, vá lỗi và kiểm soát nghiệp vụ |
| Socket bind | Tiến trình ứng dụng | Chọn IP và cổng lắng nghe | Không áp dụng được mọi chính sách về mạng nguồn |
| Xác thực/ủy quyền | Ứng dụng, proxy, danh tính | Quyết định ai được dùng chức năng | Không thay thế kiểm soát kết nối ở L3/L4 |

### 2.1. Hướng của luồng mạng

- **Inbound:** kết nối từ mạng đến một socket/dịch vụ **trên chính host**. Ví dụ TCP/443 từ reverse proxy đến web server.
- **Outbound:** lưu lượng **do host khởi tạo** ra mạng. Ví dụ máy chủ gọi một API qua TCP/443 hoặc truy vấn DNS.
- **Forwarded:** lưu lượng **được host chuyển tiếp** giữa giao diện/mạng; thường gặp khi máy làm router, gateway, VPN server, host container hoặc bridge.
- **Loopback:** lưu lượng nội bộ giữa các tiến trình trên cùng máy, thường qua 127.0.0.1 hoặc ::1. Nếu chặn sai có thể làm ứng dụng nội bộ hỏng.

Trên Linux, các đường input, output và forward được xử lý ở những hook/chain khác nhau. Lưu lượng đến container đã công bố cổng qua NAT đôi khi đi theo đường forwarding, nên không thể suy luận rằng mọi traffic tới container đều bị điều khiển bởi một input rule thông thường.

### 2.2. Liên hệ với OSI

Host firewall truyền thống thường xét IP nguồn/đích ở **Layer 3**, TCP/UDP và cổng ở **Layer 4**, cùng interface và trạng thái luồng. Một số sản phẩm bổ sung rule theo tiến trình, người dùng, profile mạng hoặc danh tính. Việc phát hiện tấn công ứng dụng, lọc nội dung HTTP hoặc xác thực tài khoản không phải khả năng tự động có trong mọi host firewall.

## 3. Rule của host firewall gồm những gì?

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Direction | Inbound / Outbound | Chiều lưu lượng xét từ host |
| Source IP/prefix | 192.0.2.0/24 | Nguồn được phép, có thể thay đổi sau NAT |
| Destination IP | Địa chỉ máy chủ | Địa chỉ nhận hoặc gửi gói |
| Protocol | TCP, UDP, ICMP, ICMPv6 | Giao thức được xét |
| Port | TCP/22, TCP/443, UDP/53 | Cổng dịch vụ, không áp dụng giống nhau cho mọi giao thức |
| Interface/zone/profile | NIC quản trị, Domain, Public | Phạm vi mà chính sách có hiệu lực |
| Connection state | new, established, related, invalid | Trạng thái kết nối được theo dõi |
| Action | Allow, Drop, Reject | Cho phép hoặc từ chối gói |
| Logging | Log deny | Ghi bằng chứng phục vụ giám sát và chẩn đoán |

Các địa chỉ **192.0.2.0/24**, **198.51.100.0/24** và **203.0.113.0/24** trong bài thuộc dải dành cho tài liệu theo RFC 5737. Chúng chỉ là dữ liệu minh họa; khi thực hành phải thay bằng địa chỉ lab thuộc quyền quản trị.

### 3.1. Allow, drop và reject

**Allow/Accept** cho phép gói qua một điểm kiểm tra; **Drop** loại bỏ gói mà thường không phản hồi; **Reject** từ chối có phản hồi lỗi thích hợp khi nền tảng hỗ trợ. **Log** có thể là hành động riêng biệt, không mặc định thay thế quyết định cho phép hay chặn.

Không tồn tại quy tắc tổng quát rằng một lệnh allow sẽ luôn thắng một lệnh deny trên mọi hệ điều hành. Quyết định cuối phụ thuộc vào **thứ tự đánh giá, hook, priority, chain, profile và chính sách quản trị tập trung**. Khi có nhiều bộ quản lý firewall cùng chạy, cần kiểm tra đường đi gói thực tế.

### 3.2. Stateful và stateless filtering

**Stateless firewall** xét từng gói dựa vào trường IP, giao thức và cổng mà không nhất thiết lưu trạng thái của phiên. **Stateful firewall** theo dõi các luồng và có thể nhận diện gói phản hồi của kết nối đã được cho phép. Linux thường sử dụng **conntrack** cho việc này.

Ví dụ: client mở kết nối TCP đến cổng 443 của server. Gói mở đầu được xét như yêu cầu mới; nếu được chấp nhận, gói của luồng tiếp theo được nhận diện nhờ bảng trạng thái. Server không cần mở toàn bộ dải cổng động của client cho mọi nguồn chỉ để gửi phản hồi.

| Trạng thái thông dụng | Diễn giải |
| --- | --- |
| new | Luồng mới được quan sát, chưa đồng nghĩa ứng dụng đã xác thực |
| established | Gói thuộc một luồng đã có trạng thái theo dõi |
| related | Gói có quan hệ với một luồng khác, ví dụ một số ICMP lỗi hợp lệ |
| invalid | Không thể gắn hợp lệ với trạng thái đang theo dõi; thường bị từ chối |

UDP không có quá trình bắt tay như TCP. Với UDP, trạng thái được suy ra từ gói và timeout, không phải “kết nối UDP” giống TCP. Dù là stateful, firewall vẫn không biết người dùng đã đăng nhập ứng dụng hay chưa.

## 4. Chính sách default deny và least privilege

**Default deny** nghĩa là lưu lượng không khớp quy tắc cho phép cần thiết sẽ bị từ chối. Với máy chủ, chặn inbound mặc định rồi mở đúng dịch vụ cần thiết thường là cách thiết kế tốt. Outbound cần phân tích theo nghiệp vụ: host có thể cần DNS, đồng bộ thời gian, cập nhật gói, dịch vụ giám sát và API được phê duyệt.

Một baseline minh họa cho web server:

| Hướng | Nguồn → Đích | Giao thức | Quyết định | Mục đích |
| --- | --- | --- | --- | --- |
| Inbound | Proxy subnet → Web host | TCP/443 | Allow | Nhận HTTPS từ proxy |
| Inbound | Management subnet → Web host | TCP/22 | Allow | Quản trị SSH |
| Inbound | Các nguồn còn lại → SSH | TCP/22 | Deny | Hạn chế cổng quản trị |
| Inbound | Nguồn khác → DB port trên Web host | TCP/5432 | Deny | Ngăn lộ DB không dự kiến |
| Outbound | Web host → Resolver nội bộ | UDP/TCP 53 | Allow khi cần | Phân giải tên |
| Outbound | Web host → API được phép | TCP/443 | Allow | Kết nối phụ thuộc |
| Hai chiều | Lưu lượng chưa được phê duyệt | Theo phạm vi | Deny | Giảm bề mặt kết nối |

Để hiện thực chính sách:

1. **Kiểm kê dịch vụ và owner.** Xác định ứng dụng lắng nghe trên interface nào, port gì, từ mạng nào cần truy cập.
2. **Lập danh sách luồng hai chiều.** Đặc biệt với DNS, NTP, telemetry, VPN, cập nhật và kết nối cơ sở dữ liệu.
3. **Phân vùng nguồn/đích.** Chỉ cho phép subnet quản trị đến cổng quản trị, proxy đến ứng dụng, ứng dụng đến DB phù hợp.
4. **Giữ đường quản trị an toàn.** Có console dự phòng và phương án rollback trước khi áp dụng chặn mặc định lên server từ xa.
5. **Xét IPv4 và IPv6.** Một rule chỉ khớp IPv4 không tự động hạn chế IPv6 theo cùng cách.
6. **Giữ ICMP/ICMPv6 thiết yếu.** Cấm tất cả thông báo điều khiển có thể gây lỗi Path MTU Discovery và Neighbor Discovery ở IPv6.
7. **Kiểm tra rồi giám sát.** Xác minh nguồn được phép truy cập và nguồn không được phép bị chặn, theo dõi thay đổi qua thời gian.

Không có một bộ rule cố định phù hợp mọi máy. Một máy trạm, VM công cộng, server nội bộ và VPN gateway có mục tiêu truy cập rất khác nhau.

## 5. Host firewall trên Linux

Linux thường sử dụng **Netfilter** trong kernel. Các công cụ quản lý phổ biến:

| Công cụ | Chức năng |
| --- | --- |
| nftables / nft | Tạo bảng, chain, rule và xử lý theo hook Netfilter |
| iptables | Giao diện truyền thống, có thể chạy trên backend tương thích nftables |
| UFW | Giao diện đơn giản để quản lý firewall trên một số bản phân phối |
| firewalld | Quản lý firewall theo zone và service |
| conntrack | Theo dõi trạng thái luồng khi được hỗ trợ/cài đặt |

Nhiều công cụ có thể tương tác với cùng cơ chế kernel. Tránh cấu hình chồng chéo nhiều hệ thống quản trị rule mà không biết nơi nào có hiệu lực. Không nên kết luận “firewall tắt” chỉ vì một tiện ích báo inactive.

### 5.1. Lệnh kiểm tra chỉ đọc

~~~bash
# Xem địa chỉ IP và tuyến trên host
ip -br address
ip route
ip -6 route

# Xem socket lắng nghe cùng tiến trình nếu đủ quyền
ss -lntup

# Quan sát toàn bộ ruleset nftables (nếu dùng)
sudo nft list ruleset

# Quan sát UFW (nếu dùng)
sudo ufw status verbose

# Quan sát firewalld (nếu dùng)
sudo firewall-cmd --state
sudo firewall-cmd --get-active-zones
sudo firewall-cmd --list-all
~~~

**Đối chiếu cần thiết:** thấy cổng 443 trong danh sách socket không bảo đảm gói từ xa vào được. Ngược lại, thấy rule allow TCP/443 không chứng minh có tiến trình nào đang nghe cổng đó.

### 5.2. Ví dụ chính sách nftables trong lab

Đoạn bên dưới để **đọc và thử trên máy ảo có console**, không áp dụng nguyên văn cho production. Nó đặt **policy drop cho inbound**; nếu máy đang được quản trị từ xa mà thiếu rule đúng nguồn, kết nối SSH có thể bị mất. Các IP chỉ là địa chỉ tài liệu.

~~~nft
table inet host_example {
    chain input {
        type filter hook input priority 0; policy drop;

        # Giao tiếp nội bộ host
        iifname "lo" accept

        # Dữ liệu của luồng đã có trạng thái
        ct state established,related accept
        ct state invalid drop

        # ICMP/ICMPv6 cần thiết: ví dụ cho phép rộng để dễ quan sát ở lab
        ip protocol icmp accept
        meta l4proto ipv6-icmp accept

        # SSH từ subnet quản trị
        ip saddr 192.0.2.0/24 tcp dport 22 accept

        # HTTPS từ subnet reverse proxy
        ip saddr 198.51.100.0/24 tcp dport 443 accept
    }
}
~~~

Giải thích:

- **inet** giúp dùng chung bảng cho IPv4/IPv6; rule có điều kiện **ip saddr** ở đây chỉ khớp IPv4.
- **input** là nơi xét gói đến socket của chính máy; **forward** và **output** chưa được mô tả trong ví dụ.
- **policy drop** loại những gói còn lại tại chain này.
- **ct state established,related** cho phép luồng phản hồi hoặc liên quan được theo dõi.
- Rule ICMP/ICMPv6 ở đây ưu tiên tính minh họa; production cần xem chính sách giám sát và rate limit mà vẫn giữ các thông điệp thiết yếu.

Ví dụ chưa xét DHCP, IPv6 Router Advertisement theo đặc thù host, container, DNS, log, rate limit hoặc VPN. Một verdict accept ở một chain **không nhất thiết vượt qua** mọi chain/hook khác đang hoạt động. Khi triển khai phải đọc toàn bộ ruleset và kiểm tra lưu lượng thật.

### 5.3. Minh họa UFW

Trên máy lab đang quản lý bằng UFW, rule giới hạn SSH theo nguồn có thể là:

~~~bash
# Chỉ trên lab và sau khi xác định đúng subnet quản trị
sudo ufw allow from 192.0.2.0/24 to any port 22 proto tcp

# Kiểm tra rule đã có và thứ tự hiển thị
sudo ufw status numbered
~~~

Trước khi bật UFW, thay default policy hoặc xóa rule, cần phương án console/rollback và xác định IPv6 có được quản lý hay không. Việc thêm một allow rule **không tự chứng minh** các nguồn khác đã bị chặn, vì còn phụ thuộc những rule hiện có.

## 6. Host firewall trên Windows

**Microsoft Defender Firewall** sử dụng nền tảng lọc của Windows và thường phân loại profile **Domain**, **Private**, **Public**. Chính sách có thể được tổ chức triển khai qua Group Policy hoặc hệ thống quản lý endpoint; cấu hình trên máy không phải lúc nào cũng là quyết định cuối cùng.

Lệnh PowerShell chỉ đọc:

~~~powershell
# Xem trạng thái và action mặc định của từng profile
Get-NetFirewallProfile |
    Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction

# Xem các quy tắc inbound đang bật
Get-NetFirewallRule -Direction Inbound -Enabled True |
    Select-Object DisplayName, Action, Profile

# Cổng TCP đang lắng nghe
Get-NetTCPConnection -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess
~~~

Ví dụ **trong máy lab do bạn quản lý** cho phép ứng dụng thử nghiệm TCP/8443 từ subnet quản trị qua profile Domain:

~~~powershell
New-NetFirewallRule -DisplayName "Lab Web from management" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8443 -RemoteAddress 192.0.2.0/24 -Profile Domain
~~~

Rule này chỉ có ý nghĩa nếu máy đang dùng profile phù hợp và không bị chính sách khác ưu tiên chặn. Windows cũng hỗ trợ ràng buộc một số quy tắc vào đường dẫn chương trình hoặc dịch vụ. Muốn xác minh phải thử từ một client hợp lệ **và** một client ngoài phạm vi.

## 7. VM, cloud, container và VPN

### 7.1. Cloud security group không thay thế host firewall

Cloud thường có route table, security group, network ACL, firewall quản lý và chính sách gắn vào tài nguyên mạng. Chúng có semantics khác nhau theo nhà cung cấp, đặc biệt về statefulness, thứ tự ưu tiên và vị trí áp dụng. Host firewall vẫn chạy bên trong hệ điều hành của VM.

~~~text
Nguồn truy cập
  |
  +--> Route và cloud firewall/security group
          |
          +--> Subnet ACL / Network firewall (nếu có)
                  |
                  +--> Host firewall trong VM
                          |
                          +--> Dịch vụ đang listen
                                  |
                                  +--> Xác thực/ủy quyền ứng dụng
~~~

Khi truy cập thất bại, xác định đúng lớp chặn thay vì mở đồng loạt nhiều lớp để “thử cho nhanh”. Lưu ý NAT hoặc reverse proxy có thể làm địa chỉ nguồn hiển thị tại host khác nguồn ban đầu; rule phải dùng nguồn thực tế ở điểm kiểm tra.

### 7.2. Container và Kubernetes

Docker thường triển khai port publishing, NAT và forwarding bằng cơ chế mạng host. Kết nối đến một cổng publish có thể không đi qua input chain thông thường như kết nối đến tiến trình host. Đặc biệt với một số cấu hình Docker/UFW, policy UFW có thể không kiểm soát luồng publish theo cách người quản trị dự kiến.

Kubernetes **NetworkPolicy** chủ yếu áp dụng cho kết nối pod khi plugin CNI hỗ trợ; nó không tự thay thế host firewall của node. Với hostNetwork pod, ingress, service, overlay network và VPN, cần xác định đường gói cụ thể, nơi NAT xảy ra và hook nào xử lý.

### 7.3. VPN và kiểm soát quản trị

VPN tạo đường kết nối và có thể bảo vệ lưu lượng trên đường truyền, nhưng **VPN không tự cấp quyền** vào tất cả dịch vụ nội bộ. Sau khi người dùng hoặc thiết bị kết nối VPN, host firewall vẫn có thể giới hạn IP nguồn của tunnel và các cổng được dùng.

Ví dụ: quản trị viên phải xác thực VPN, chỉ được cấp IP trong subnet quản trị, sau đó mới được truy cập SSH/RDP tới những máy được phân quyền. Quyền truy cập ứng dụng vẫn cần xác thực riêng và được ghi log.

## 8. Quy trình triển khai host firewall an toàn

Giả sử hệ thống có web server, reverse proxy và database ở ba vùng khác nhau. Dùng quy trình sau:

1. **Xác định tài sản và dịch vụ.** Kiểm kê IP IPv4/IPv6, interface, các cổng lắng nghe, người chịu trách nhiệm và luồng cần thiết.
2. **Xác định đường đi.** Vẽ tuyến hai chiều, VPN, NAT, proxy, cloud rule và mọi nơi có thể lọc gói.
3. **Định nghĩa baseline.** Viết bảng nguồn, đích, giao thức/cổng, chiều, nhóm được phép và thời gian tồn tại rule.
4. **Chọn default policy.** Với inbound, ưu tiên từ chối ngoài whitelist; với outbound, chọn mức hạn chế phù hợp nghiệp vụ.
5. **Giữ kênh cứu hộ.** Thử trên staging/lab, chuẩn bị console quản trị và rollback trước khi áp dụng trên máy từ xa.
6. **Kiểm tra cả allow lẫn deny.** Thực hiện từ nguồn được phép và nguồn bị từ chối, với TCP/UDP, IPv4/IPv6 khi liên quan.
7. **Giám sát và quản lý thay đổi.** Ghi thời điểm đổi rule, lý do, owner, log deny và kỳ hạn rà soát.

### 8.1. Ma trận kiểm thử

| Thử nghiệm | Nguồn | Đích | Kết quả mong đợi |
| --- | --- | --- | --- |
| SSH hợp lệ | Máy quản trị | Server TCP/22 | Được phép |
| SSH ngoài phạm vi | Client khác được cho phép kiểm thử | Server TCP/22 | Bị chặn |
| HTTPS hợp lệ | Reverse proxy | Server TCP/443 | Được phép |
| HTTPS ngoài phạm vi | Client mạng khác | Server TCP/443 | Bị chặn nếu chỉ cho proxy |
| DNS của host | Server | Resolver UDP/TCP 53 | Hoạt động khi được cấp quyền |
| Kết nối database | Web server | DB đúng IP:port | Hoạt động nếu DB cũng cho phép |
| IPv6 quản trị | Client IPv6 | Server TCP/22 | Bị chặn nếu không có nhu cầu IPv6 |

Ví dụ kiểm tra **từ máy thử được phép**, sau khi thay địa chỉ tài liệu bằng IP lab thực:

~~~bash
# Kiểm tra chỉ việc thiết lập kết nối TCP
nc -vz -w 3 192.0.2.10 22
nc -vz -w 3 192.0.2.10 443

# Chẩn đoán đường đi, nếu công cụ có sẵn
traceroute -n 192.0.2.10
~~~

Kết quả kết nối TCP thành công không chứng minh TLS, SSH hoặc ứng dụng đã bảo mật. Kết quả từ một nguồn cũng không chứng minh trạng thái truy cập từ mọi nguồn: rule có thể ràng buộc subnet, interface, profile hoặc thời gian.

## 9. Ghi log, giám sát và phát hiện bất thường

Log firewall có thể cung cấp thời điểm, IP nguồn/đích, protocol, cổng, hành động allow/deny, interface và rule liên quan. Khả năng ghi chi tiết tùy nền tảng và cấu hình.

~~~text
time=2026-11-28T09:10:00Z host=web-lab
direction=inbound src=203.0.113.25 dst=192.0.2.10
proto=tcp dport=22 action=DROP rule=ssh-management-only
~~~

Ví dụ trên cho thấy host chặn một lần truy cập SSH ngoài subnet quản trị. Đây là dấu hiệu **policy đang thực thi**; không thể kết luận có tấn công chỉ dựa vào một bản ghi. Để xác định sự kiện đáng ngờ, cần kết hợp tốc độ lặp lại, nguồn, lịch kiểm thử hợp lệ, log VPN, log đăng nhập, IDS/IPS và hành vi dịch vụ.

Nên cấu hình log các sự kiện deny quan trọng, giới hạn tốc độ ghi để tránh tràn đĩa, đồng bộ thời gian và thu thập log tập trung. Không cần ghi mọi gói cho mọi rule. Việc không thấy log DROP cũng **không chứng minh** không có gói bị chặn: nhiều rule không bật logging.

## 10. Chẩn đoán khi kết nối không hoạt động

~~~mermaid
flowchart TD
    A[Kết nối thất bại] --> B{Dịch vụ có listen đúng IP và port?}
    B -->|Không| C[Kiểm tra process, bind, service health]
    B -->|Có| D{DNS, route và đường mạng hợp lệ?}
    D -->|Không| E[Kiểm tra DNS, subnet, route, VPN]
    D -->|Có| F{Gói có đến host?}
    F -->|Không| G[Kiểm tra cloud rule, network firewall, ACL]
    F -->|Có| H{Host firewall chặn?}
    H -->|Có| I[Kiểm tra nguồn, chiều, profile, state, IPv4/IPv6]
    H -->|Không| J[Kiểm tra TLS, xác thực, ứng dụng và chiều phản hồi]
~~~

**Một số lỗi thường gặp:**

- **Kết nối được từ mạng A nhưng không từ B:** khác biệt rule theo source, NAT, profile/zone, route hoặc network firewall.
- **Dịch vụ chỉ listen 127.0.0.1 hoặc ::1:** socket chỉ nhận loopback, dù firewall inbound cho phép vẫn không truy cập từ mạng.
- **IPv4 chạy, IPv6 thất bại:** thiếu rule IPv6, route, bind, DNS AAAA hoặc các thông điệp ICMPv6 cần thiết.
- **Gói nhỏ đi được, gói lớn bị treo:** xem MTU và Path MTU Discovery; lọc ICMP quá mức có thể gây lỗi.
- **Kết nối TCP được nhưng ứng dụng lỗi:** kiểm tra TLS handshake, chứng chỉ, authentication, proxy và đường phản hồi.
- **Docker publish port nhưng không chịu input rule:** xác minh NAT/forward hooks và quy tắc do container runtime cài.
- **Bị khóa SSH/RDP sau khi đổi policy:** sử dụng kênh console/rollback đã chuẩn bị, không tắt bừa các lớp bảo vệ khác.

## 11. Những hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Có firewall biên thì không cần host firewall.” | Host firewall kiểm soát trực tiếp máy, kể cả khi traffic nội bộ không đi qua firewall biên. |
| “Mở TCP/443 nghĩa là HTTPS đã hoạt động.” | Phải có dịch vụ listen, TLS phù hợp, route và kiểm soát ứng dụng. |
| “Chỉ chặn inbound là đủ cho mọi máy.” | Outbound cũng quan trọng với DNS, API, cập nhật và ngăn kết nối ngoài dự kiến. |
| “Default deny luôn an toàn nếu bật ngay.” | Có thể cắt mất đường quản trị, dịch vụ phụ thuộc hoặc các thông điệp mạng thiết yếu. |
| “Stateful firewall biết ai đã đăng nhập.” | Trạng thái mạng khác với xác thực và quyền ứng dụng. |
| “Chặn toàn bộ ICMP sẽ an toàn hơn.” | Có thể phá PMTUD, chẩn đoán mạng và chức năng IPv6. |
| “Rule allow luôn thắng rule deny.” | Hiệu lực phụ thuộc nền tảng, thứ tự và chính sách hiệu lực. |
| “Container tuân theo input rule giống ứng dụng host.” | NAT/forwarding có thể đi qua hook khác. |
| “Không có log deny nghĩa là không có chặn.” | Logging có thể bị tắt, giới hạn hoặc gửi sang nguồn khác. |

## 12. Bài tập suy luận tình huống

**Giả định:** Máy chủ 192.0.2.10 có input policy mặc định drop; cho phép loopback, established/related, ICMP cần thiết, TCP/22 từ subnet 192.0.2.0/24 và TCP/443 từ subnet 198.51.100.0/24. Hãy xét các gói kết nối **mới** sau, chỉ theo chính sách firewall được mô tả:

| Kết nối | Quyết định kỳ vọng |
| --- | --- |
| 192.0.2.50 → 192.0.2.10:22 | Allow |
| 203.0.113.20 → 192.0.2.10:22 | Drop |
| 198.51.100.5 → 192.0.2.10:443 | Allow |
| 192.0.2.50 → 192.0.2.10:443 | Drop |
| Gói phản hồi thuộc một luồng đã được cho phép | Allow nếu conntrack xác định established/related |
| Kết nối SSH mới qua IPv6 mà không có IPv6 allow tương ứng | Drop |

**Câu hỏi tự kiểm tra:**

1. Vì sao rule từ subnet quản trị phải xét địa chỉ nguồn nhìn thấy tại host sau NAT hoặc proxy?
2. Vì sao kiểm tra truy cập từ localhost không xác minh được chính sách inbound từ proxy?
3. Khi ứng dụng gọi API ngoài Internet, những điểm lọc và luồng outbound nào cần kiểm tra?
4. Vì sao một firewall cho phép TCP session nhưng yêu cầu HTTP vẫn có thể thất bại?
5. Khi dùng VPN, tại sao vẫn cần kiểm soát IP nguồn, interface và quyền vào dịch vụ nội bộ?

**Gợi ý:** (1) Firewall áp dụng lên gói ở vị trí đang lọc. (2) Loopback và truy cập từ xa có thể đi qua đường xử lý khác nhau. (3) Output host, route, VPN/NAT, firewall mạng và chính sách phía đích. (4) TLS, chứng chỉ, xác thực và logic ứng dụng là lớp khác. (5) VPN tạo đường truyền, không tự giới hạn mọi quyền truy cập.

## 13. Tổng kết

Host firewall đưa cơ chế **network access control** tới từng điểm cuối. Thiết kế hiệu quả cần một danh mục luồng rõ ràng, default policy hợp lý, rule theo nguyên tắc quyền tối thiểu, stateful filtering, bao phủ IPv4/IPv6, kiểm thử allow/deny và log phục vụ giám sát. Trong **SECURITY_NETWORK_SECURITY**, nó hoạt động cùng phân đoạn, firewall mạng, VPN, xác thực, IDS/IPS và các biện pháp bảo vệ DNS, cloud và container nhằm hình thành kiến trúc mạng an toàn hơn.

### Tài liệu tra cứu

- **NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy**: nguyên tắc và mô hình chính sách firewall.
- **nftables Wiki / Netfilter Project**: bảng, chain, hook, stateful packet filtering.
- **Ubuntu UFW Documentation**: cách quản trị và quan sát rule UFW.
- **firewalld Documentation**: zone, service và cấu hình firewall trên Linux.
- **Microsoft Learn — Windows Defender Firewall with Advanced Security**: profile, inbound/outbound rule và PowerShell.
- **RFC 4890 — Recommendations for Filtering ICMPv6 Messages in Firewalls**: cân nhắc khi lọc ICMPv6.
