# Default gateway: Cổng mặc định trong mạng TCP/IP

> **Chương:** TCP IP  
> **Chủ đề:** Default gateway  
> **Phạm vi học tập:** SECURITY_NETWORK_SECURITY — tìm hiểu đường đi của lưu lượng mạng để xác định điểm phân đoạn, kiểm soát bằng firewall/VPN, phát hiện bất thường và tiến tới thiết kế mạng an toàn.

Khi một máy tính gửi dữ liệu đến máy khác, câu hỏi quan trọng nhất ở bước đầu không phải “gửi lên Internet bằng cách nào?” mà là **“địa chỉ đích có thể đến trực tiếp trên liên kết mạng hiện tại hay phải chuyển cho một router?”**. Nếu bảng định tuyến không có tuyến cụ thể hơn đến mạng đích, thiết bị có thể dùng **default gateway** để chuyển gói ra ngoài các mạng mà nó biết rõ. Đây là nền tảng để hiểu phân đoạn mạng, các quy tắc firewall giữa VLAN, đường ra Internet, VPN và luồng east–west trong hệ thống doanh nghiệp.

## 1. Mục tiêu học tập

Sau bài học, bạn cần có khả năng:

1. Giải thích default gateway là gì, khi nào được dùng và vì sao không phải mọi gói tin đều đi qua nó.
2. Đọc bảng định tuyến IPv4/IPv6; phân biệt **tuyến trực tiếp**, **tuyến cụ thể** và **tuyến mặc định**.
3. Mô tả đúng IP đích, IP next hop, MAC đích của frame, ARP/Neighbor Discovery, TTL/Hop Limit và luồng phản hồi khi đi qua router.
4. Kiểm tra cấu hình gateway trên Linux/Windows và chẩn đoán lỗi kết nối theo từng lớp.
5. Nhận diện rủi ro bảo mật tại gateway và các biện pháp bảo vệ như phân đoạn, ACL, firewall, chống giả mạo DHCP/ARP/RA và giám sát log.
6. Phân biệt gateway của host với DNS, NAT, VPN, firewall và các đối tượng route trong cloud.

## 2. Default gateway thực chất là gì?

**Default gateway** (cổng mặc định) là **next hop được chọn khi thiết bị không tìm được tuyến phù hợp cụ thể hơn** trong bảng định tuyến. Trong mạng IP thông thường, next hop này là một router, giao diện định tuyến của firewall hoặc switch lớp 3 có khả năng chuyển tiếp gói IP sang mạng khác.

- **IPv4:** tuyến mặc định có prefix **0.0.0.0/0**.
- **IPv6:** tuyến mặc định có prefix **::/0**.
- **Gateway address:** thường là địa chỉ IP của router **có thể tiếp cận trên liên kết hiện tại**. Với IPv6, đó thường là địa chỉ link-local của router, ví dụ **fe80::1**, kèm giao diện mạng.
- **Default route ≠ bắt buộc đi Internet.** Nó có thể trỏ đến router nội bộ, cổng VPN hoặc thiết bị bảo mật. Router kế tiếp mới quyết định có đường đến đích hay không.

Một máy có thể có nhiều default route (nhiều card mạng, Wi-Fi và Ethernet, VPN, các router dự phòng) hoặc không có default route nào. Khi không có default route, máy vẫn có thể giao tiếp với các mạng **đã có tuyến trực tiếp hoặc tuyến cụ thể**; nó chỉ không biết đường mặc định để đi đến các đích chưa có tuyến.

**Phân biệt thuật ngữ:** “Gateway” trong hệ thống phần mềm còn có nghĩa là API gateway, application gateway hoặc proxy. Bài này nói đến **default IP gateway** trong quá trình định tuyến. Các thiết bị hoặc phần mềm khác có thể đảm nhiệm cả hai vai trò, nhưng đây là hai chức năng khác nhau.

## 3. Sơ đồ mạng ví dụ và dữ liệu ban đầu

Giả sử hệ thống lab được phân thành hai mạng:

| Thành phần | IP / prefix | Vai trò |
| --- | --- | --- |
| Client A | 10.10.10.25/24 | Máy người dùng trong VLAN 10 |
| Gateway tại VLAN 10 | 10.10.10.1/24 | Router R, cổng đến mạng User |
| Gateway tại VLAN 20 | 10.20.20.1/24 | Router R, cổng đến mạng App |
| Server B | 10.20.20.50/24 | Web/API server trong VLAN 20 |
| Client C | 10.10.10.80/24 | Máy khác cùng mạng với A |

Các địa chỉ **10.10.10.0/24** và **10.20.20.0/24** chỉ là ví dụ riêng cho lab. Đường đi minh họa:

~~~mermaid
flowchart LR
    subgraph U["VLAN 10 — User: 10.10.10.0/24"]
      A["Client A: 10.10.10.25"]
      C["Client C: 10.10.10.80"]
      GU["Router R: 10.10.10.1"]
    end
    subgraph S["VLAN 20 — App: 10.20.20.0/24"]
      GS["Router R: 10.20.20.1"]
      B["Server B: 10.20.20.50"]
    end
    A -->|"Gửi frame đến MAC của gateway"| GU
    GU -->|"Router định tuyến qua VLAN 20"| GS
    GS -->|"Frame mới đến MAC của B"| B
    A <-.->|"Cùng subnet: trực tiếp"| C
~~~

Trong lab này, R có đủ giao diện định tuyến và đã bật IP forwarding, đồng thời chính sách firewall cho phép luồng kiểm thử. Các kết nối có thể còn bị chặn bởi firewall trên máy đích; **việc có route không đồng nghĩa được phép truy cập**.

Trên Client A, bảng định tuyến IPv4 đơn giản có thể hiển thị:

~~~text
Destination         Next hop       Interface
10.10.10.0/24       on-link        eth0
0.0.0.0/0           10.10.10.1     eth0
~~~

Trên Server B, cần có tuyến đưa lưu lượng phản hồi về 10.10.10.0/24, chẳng hạn default gateway 10.20.20.1. **Đường về là điều kiện thiết yếu:** A có thể gửi packet tới B nhưng phiên TCP vẫn thất bại nếu B không có route phản hồi hoặc bị chính sách chặn.

## 4. Gói tin đi qua default gateway như thế nào?

### 4.1. Trường hợp cùng mạng: A gửi đến C

Client A muốn gửi đến **10.10.10.80**. Theo địa chỉ /24, A có tuyến trực tiếp tới **10.10.10.0/24**. Hệ điều hành chọn tuyến này:

1. A tra bảng định tuyến và biết rằng 10.10.10.80 nằm trên liên kết eth0.
2. A tra neighbor cache; nếu chưa có ánh xạ, dùng **ARP** (IPv4) để hỏi MAC của **10.10.10.80**.
3. A tạo frame có **MAC đích là MAC của C**, còn IP đích trong packet vẫn là **10.10.10.80**.
4. Switch chuyển frame trong mạng lớp 2 phù hợp; router mặc định **không cần tham gia** vào đường đi IP này.

Điều kiện “cùng mạng” ở đây dựa trên **kết quả chọn tuyến và tính khả dụng của liên kết**, không đơn giản chỉ nhìn các chữ số đầu của IP. Subnet mask sai, cấu hình route đặc biệt hoặc VLAN không khớp đều có thể khiến kết nối thất bại.

### 4.2. Trường hợp khác mạng: A gửi đến B

Client A muốn truy cập **10.20.20.50**. Nếu không có tuyến cụ thể hơn, hệ điều hành chọn **0.0.0.0/0 qua 10.10.10.1**.

1. A xác định **IP đích cuối cùng vẫn là 10.20.20.50**, còn **next hop** cho chặng đầu là **10.10.10.1**.
2. A dùng ARP tìm MAC của gateway **10.10.10.1** (không tìm MAC của B ở subnet xa).
3. A đóng packet IP vào frame có **MAC nguồn của A** và **MAC đích của giao diện gateway tại VLAN 10**.
4. R nhận frame, bỏ lớp liên kết của chặng đầu, tra bảng định tuyến của chính R, giảm **TTL** IPv4 (hoặc **Hop Limit** IPv6) và chuyển tiếp nếu route cùng chính sách cho phép.
5. R xác định B ở mạng kết nối trực tiếp **10.20.20.0/24**, tìm MAC của B bằng ARP trên VLAN 20 rồi tạo **frame mới** để gửi đến B.
6. B xử lý packet và gửi phản hồi theo bảng định tuyến của B; trên đường về, R chuyển tiếp lại đến A.

| Thuộc tính | A → R (chặng 1) | R → B (chặng 2) |
| --- | --- | --- |
| IP nguồn | 10.10.10.25 | 10.10.10.25 |
| IP đích | 10.20.20.50 | 10.20.20.50 |
| MAC nguồn | MAC của A | MAC giao diện R ở VLAN 20 |
| MAC đích | MAC giao diện R ở VLAN 10 | MAC của B |
| TTL | Giá trị do A đặt | Thường giảm một đơn vị khi R forward |

Bảng trên giả định **định tuyến IP thông thường, không có NAT hay tunnel**. NAT hoặc đóng gói qua VPN có thể thay đổi thông tin nhìn thấy; chính các cơ chế đó phải được phân tích riêng.

**Điểm mấu chốt:** default gateway chỉ thay đổi *nơi gửi frame trên chặng tiếp theo*. Trong định tuyến IP bình thường, nó **không làm IP đích biến thành IP của gateway** và không tự dịch IP nguồn. Đừng nhầm **địa chỉ next hop** với **địa chỉ đích cuối**.

### 4.3. Với IPv6 có gì khác?

Ý tưởng chọn route tương tự IPv4, nhưng thay vì ARP, thiết bị dùng **Neighbor Discovery (ND)** dựa trên ICMPv6 để tìm và duy trì neighbor; host thường học default router qua **Router Advertisement (RA)**. Ví dụ:

~~~text
default via fe80::1 dev eth0 proto ra
2001:db8:10:10::/64 dev eth0
~~~

Địa chỉ **fe80::1** là link-local; phải gắn đúng giao diện vì nhiều liên kết khác nhau có thể dùng địa chỉ link-local cùng dạng. ICMPv6 ND/RA có vai trò thiết yếu, vì vậy chặn tùy tiện mọi ICMPv6 có thể làm hỏng khám phá neighbor hoặc tuyến mặc định.

## 5. Thiết bị chọn tuyến nào trước?

Hệ điều hành tra bảng định tuyến và thường ưu tiên **longest prefix match**: tuyến có số bit prefix khớp nhiều nhất với đích được xét trước. Khi có nhiều tuyến cạnh tranh với cùng độ cụ thể, metric, ưu tiên route, ECMP và chính sách định tuyến của hệ điều hành có thể ảnh hưởng lựa chọn. Trên hệ thống nhiều bảng định tuyến (policy routing), các rule có thể quyết định bảng nào được tra trước.

Ví dụ một host có bảng sau:

~~~text
10.10.10.0/24       dev eth0                 # directly connected
10.20.20.0/24       via 10.10.10.254 dev eth0
0.0.0.0/0           via 10.10.10.1   dev eth0
~~~

| IP đích | Tuyến được chọn | Vì sao? |
| --- | --- | --- |
| 10.10.10.80 | 10.10.10.0/24, trực tiếp | /24 cụ thể hơn /0 |
| 10.20.20.50 | 10.20.20.0/24 qua 10.10.10.254 | /24 cụ thể hơn /0 |
| 203.0.113.25 | 0.0.0.0/0 qua 10.10.10.1 | Không có tuyến cụ thể phù hợp |

Địa chỉ **203.0.113.25** nằm trong dải dành cho tài liệu; chỉ dùng minh họa, không đại diện một dịch vụ Internet thực tế. Router **10.10.10.254** trong ví dụ là một next hop thay thế giả định, phải thực sự tồn tại và biết đường đến 10.20.20.0/24 thì tuyến đó mới hoạt động.

Từ đây rút ra ba quy tắc:

- Default gateway **không được dùng** nếu đã có tuyến phù hợp cụ thể hơn.
- Thêm một static route có thể khiến một luồng đi theo router khác dù default gateway không đổi.
- Có default gateway **không bảo đảm** mạng đích tồn tại, router sẽ chuyển tiếp được hoặc firewall cho phép.

Nếu hai tuyến mặc định cùng tồn tại, hãy kiểm tra **metric/priority, interface, chính sách định tuyến và trạng thái thực tế**. Không nên kết luận “Wi-Fi luôn thắng Ethernet” hoặc ngược lại; cách chọn route phụ thuộc cấu hình hệ thống.

## 6. Default gateway được cấu hình từ đâu?

### 6.1. IPv4: thủ công hoặc DHCP

Máy có thể nhận địa chỉ IP, subnet mask và router mặc định qua DHCP. Trong DHCPv4, **Router Option (Option 3)** cho biết danh sách router trên subnet; các tùy chọn route khác, như **Classless Static Route Option (Option 121)**, có thể thay đổi cách host cài tuyến khi client hỗ trợ. Một máy cũng có thể dùng cấu hình tĩnh do quản trị viên thiết lập.

Ví dụ cấu hình logic:

~~~text
IPv4 address:    10.10.10.25
Subnet mask:     255.255.255.0
Default gateway: 10.10.10.1
DNS resolver:    10.10.40.53
~~~

Với cấu hình thông thường, gateway **10.10.10.1** phải là next hop mà máy có thể tiếp cận trên liên kết eth0. Nếu điền nhầm **10.20.20.1** làm gateway cho máy ở **10.10.10.0/24**, thiết bị thường không thể phân giải next hop trên liên kết. Có các trường hợp đặc biệt dùng route đến gateway hoặc cấu hình “on-link”, nhưng cần hiểu và cấu hình rõ, không coi đó là mặc định.

### 6.2. IPv6: Router Advertisement

Trong IPv6, host thường học default router qua **RA**; RA có router lifetime và các thông tin liên quan. DHCPv6 có thể cấp thông tin địa chỉ hoặc tùy chọn khác, nhưng **DHCPv6 chuẩn không đóng vai trò cấp default-router option như DHCPv4 Option 3**. Host có thể có nhiều default router được học từ nhiều RA và điều chỉnh lựa chọn khi router hết hiệu lực.

Vì default route có thể đến từ mạng, **nguồn cấu hình tự động là một ranh giới tin cậy**: thiết bị phát DHCPv4 sai hoặc RA giả có thể khiến host chọn sai cổng ra.

### 6.3. Gateway dự phòng và địa chỉ ảo

Mạng doanh nghiệp thường không muốn một router vật lý là điểm lỗi duy nhất. Các cơ chế dự phòng gateway như VRRP/HSRP có thể cung cấp **địa chỉ gateway ảo** và quy trình chuyển vai trò giữa nhiều thiết bị. Máy trạm vẫn dùng một IP gateway logic, trong khi router đang hoạt động nhận và chuyển tiếp lưu lượng.

**Dự phòng gateway chưa đủ bảo đảm kết nối end-to-end:** phải kiểm tra đường đi tiếp theo, đường phản hồi, đồng bộ state firewall khi cần và cách ứng dụng phản ứng khi chuyển đổi thiết bị.

## 7. Phân biệt default gateway với các thành phần dễ nhầm

| Thành phần | Chức năng chính | Mối quan hệ với default gateway |
| --- | --- | --- |
| **DNS resolver** | Biến tên miền thành dữ liệu phân giải như địa chỉ IP | DNS tìm **đích**; routing quyết định **đi bằng đường nào**. DNS server không nhất thiết trùng gateway. |
| **DHCP** | Cấp cấu hình mạng tự động | DHCP có thể thông báo IP gateway; bản thân DHCP không chuyển tiếp packet ứng dụng. |
| **Router** | Chọn và chuyển tiếp gói giữa mạng IP | Router thường là default gateway của host, nhưng cũng xử lý các tuyến khác. |
| **Firewall / ACL** | Cho phép hoặc chặn luồng theo chính sách | Có thể nằm ngay trên router/gateway hoặc nơi khác; có route không đồng nghĩa có quyền. |
| **NAT** | Dịch địa chỉ hoặc cổng theo quy tắc | Có thể xảy ra trên gateway ra ngoài, nhưng router không mặc nhiên phải NAT. |
| **VPN** | Tạo tunnel và bảo vệ lưu lượng qua mạng trung gian | VPN có thể thêm các tuyến cụ thể, thay default route hoặc dùng split/full tunnel. |
| **Proxy / API gateway** | Trung gian ở tầng ứng dụng | Có thể là đích của một kết nối TCP/TLS; khác với next hop ở tầng IP. |

Ví dụ **split tunnel VPN** chỉ đưa lưu lượng tới subnet nội bộ **10.20.20.0/24** qua tunnel, còn các đích khác vẫn dùng default gateway của mạng truy cập. Với **full tunnel**, phần lớn hoặc toàn bộ lưu lượng thích hợp được định tuyến qua VPN theo chính sách. Khi kiểm tra sự cố VPN, phải xem route được cài và thứ tự ưu tiên; **có biểu tượng VPN kết nối** không chứng minh gói đang đi trong tunnel.

Trong cloud, bảng định tuyến subnet/VPC có thể dùng một **đối tượng đích** như Internet gateway, NAT gateway, transit gateway hoặc virtual appliance cho tuyến mặc định. Những đối tượng này khác cách host vật lý dùng một IP next hop, nhưng vẫn thể hiện nguyên lý “không có tuyến cụ thể hơn thì theo route mặc định”. Tường lửa cloud, security group, NACL và quyền ứng dụng tiếp tục quyết định lưu lượng có được phép hay không.

## 8. Kiểm tra default gateway trong thực tế

### 8.1. Trên Linux

Các lệnh dưới đây chủ yếu ở chế độ **quan sát**, phù hợp với host lab. Thay tên giao diện **eth0**, IP và tên máy cho đúng môi trường.

~~~bash
# Địa chỉ/mask trên từng giao diện
ip -4 addr show
ip -6 addr show

# Bảng định tuyến IPv4 và IPv6
ip -4 route show
ip -6 route show

# Tuyến hệ điều hành thực sự chọn cho hai IP đích
ip -4 route get 10.10.10.80
ip -4 route get 10.20.20.50

# Trạng thái ARP/ND neighbor cache
ip -4 neigh show
ip -6 neigh show

# Kiểm tra khả năng liên lạc (ICMP có thể bị lọc)
ping -c 3 10.10.10.1
ping -c 3 10.20.20.50

# Quan sát các hop; dấu * có thể do router chặn/không trả lời probe
traceroute -n 10.20.20.50
~~~

Ví dụ kết quả **minh họa**, không phải kết quả chạy trên máy của người học:

~~~text
$ ip -4 route show
default via 10.10.10.1 dev eth0
10.10.10.0/24 dev eth0 proto kernel scope link src 10.10.10.25

$ ip -4 route get 10.20.20.50
10.20.20.50 via 10.10.10.1 dev eth0 src 10.10.10.25

$ ip -4 route get 10.10.10.80
10.10.10.80 dev eth0 src 10.10.10.25
~~~

Dòng có **via 10.10.10.1** là bằng chứng máy dự định gửi packet qua gateway. Dòng chỉ có **dev eth0** cho biết đích được coi là trực tiếp trên liên kết đó. **ip route get** cho thấy quyết định của host, chưa chứng minh gateway thực sự forward được hay đích trả lời.

Khi được phép thu thập lưu lượng trong lab, quan sát ARP và ICMP:

~~~bash
# Chỉ thu trong phạm vi mạng thực hành mà bạn quản lý
sudo tcpdump -ni eth0 -c 30 'arp or (icmp and (host 10.10.10.1 or host 10.20.20.50))'
~~~

Muốn quan sát chi tiết MAC đích của frame, thêm cờ hiển thị Ethernet header phù hợp với công cụ (ví dụ **tcpdump -e**) hoặc xem Ethernet II trong Wireshark. Với TLS, không kỳ vọng thấy payload ứng dụng ở dạng rõ.

### 8.2. Trên Windows

~~~powershell
# Kiểm tra cấu hình IP và gateway từ DHCP hoặc tĩnh
ipconfig /all

# Liệt kê route và interface
route print
Get-NetRoute -AddressFamily IPv4

# Tìm đường đi và bảng ARP/neighbor
tracert -d 10.20.20.50
arp -a
Get-NetNeighbor -AddressFamily IPv4

# Kiểm tra một phiên TCP tới cổng ứng dụng trong lab
Test-NetConnection 10.20.20.50 -Port 443
~~~

Không diễn giải **PingSucceeded=False** hoặc dấu sao trong traceroute như bằng chứng duy nhất của việc mất route: ICMP có thể bị firewall lọc hoặc rate limit. Kết hợp **route**, **neighbor**, **log firewall**, trạng thái dịch vụ và kiểm thử TCP/HTTPS để phân biệt lỗi.

### 8.3. Thay đổi gateway trong lab

Cấu hình default route sai có thể làm mất kết nối từ xa với chính máy đang quản trị. Vì vậy, chỉ thay đổi trong **VM/lab cô lập có console phục hồi** hoặc theo thủ tục thay đổi mạng đã được phê duyệt. Một lệnh Linux thường gặp:

~~~bash
# VÍ DỤ CHỈ DÙNG TRONG VM LAB: thay default route IPv4
sudo ip route replace default via 10.10.10.1 dev eth0

# Xác nhận sau khi thay đổi
ip -4 route show
ip -4 route get 10.20.20.50
~~~

Lệnh trên đổi trạng thái runtime; cấu hình có thể bị hệ thống quản lý mạng (NetworkManager, netplan, systemd-networkd hoặc DHCP) ghi đè hoặc thay khi khởi động lại. Muốn lưu lâu dài phải sử dụng công cụ cấu hình được môi trường quản lý chấp nhận.

## 9. Quy trình chẩn đoán khi “không ra khỏi mạng”

Hãy đi theo thứ tự để không nhầm lỗi gateway với lỗi ứng dụng:

| Bước | Kiểm tra | Dấu hiệu / giả thuyết |
| --- | --- | --- |
| 1. Cấu hình host | IP, prefix, giao diện, trạng thái link, VLAN | Sai subnet mask hoặc interface down làm chọn đường sai. |
| 2. Chọn route | ip route get / route print | Không có route, default route sai, tuyến VPN cụ thể hơn chiếm ưu tiên. |
| 3. Next hop | ARP/ND, trạng thái neighbor, cổng switch | Host không tìm được MAC của next hop hoặc sai VLAN. |
| 4. Gateway | Interface/route/forwarding, firewall, log deny | Gateway nhận packet nhưng không có đường đi hoặc chính sách chặn. |
| 5. Đường về | Route trên server/router đối diện, NAT state | Packet đến đích nhưng phản hồi đi nhầm đường hoặc bị chặn. |
| 6. Dịch vụ | DNS, cổng TCP/UDP, TLS, xác thực ứng dụng | Đường mạng có thể đúng nhưng service vẫn thất bại. |

### Ví dụ A — Cùng VLAN truy cập được, khác VLAN thất bại

Client A ping được 10.10.10.80 nhưng không kết nối được 10.20.20.50. Kiểm tra **route get**: nếu nó chọn **via 10.10.10.1**, bước tiếp theo là xác nhận neighbor của 10.10.10.1, cấu hình forwarding và rule giữa VLAN 10 ↔ VLAN 20. Nếu A gửi được mà B không trả lời, kiểm tra route và host firewall trên B.

### Ví dụ B — Truy cập qua IP được nhưng tên miền không hoạt động

Nếu kết nối HTTPS bằng IP theo cách kiểm tra phù hợp đã chứng minh được kết nối, nhưng phân giải tên thất bại, hãy kiểm tra **DNS resolver**, truy vấn và chính sách DNS. Lưu ý truy cập HTTPS bằng IP có thể thất bại vì **hostname trong TLS certificate/SNI** không khớp; như vậy không kết luận vội rằng routing sai.

### Ví dụ C — Mở VPN xong, một số đích đi đường khác

So sánh **bảng route trước/sau VPN**, đặc biệt các prefix cụ thể và metric của default route. Với split tunnel, một mạng nội bộ có thể đi qua VPN dù default route vẫn trỏ router Wi-Fi; với full tunnel, tuyến mặc định có thể được thay đổi hoặc chia thành các prefix có hiệu quả tương đương. Kiểm tra route tới **từng IP đích cụ thể**, tránh chỉ nhìn gateway hiển thị trong giao diện hệ điều hành.

### Ví dụ D — Client gửi được SYN nhưng không thấy SYN-ACK

Đường ra đã đi một phần, song lỗi có thể nằm ở firewall trên đường, ứng dụng không lắng nghe, phản hồi bị chặn hoặc **return route không đúng**. Lấy flow log/capture ở hai phía hoặc trên gateway nếu được cấp quyền. Không thêm các rule mở rộng toàn bộ cổng chỉ để kiểm tra một nguyên nhân chưa xác nhận.

## 10. Vì sao default gateway là điểm nhạy cảm về bảo mật?

Gateway thường nằm tại **ranh giới giữa các subnet hoặc giữa mạng nội bộ với mạng bên ngoài**, nên vị trí này ảnh hưởng trực tiếp tới khả năng quan sát và kiểm soát lưu lượng. Tuy nhiên, host có thể có các tuyến khác đi vòng default gateway; vì vậy **kiểm soát gateway thôi chưa đủ để bảo vệ toàn bộ lưu lượng**.

### 10.1. Các tình huống rủi ro chính

| Rủi ro | Điều có thể xảy ra | Biện pháp phòng vệ phù hợp |
| --- | --- | --- |
| **Rogue DHCP** | Thiết bị không được phép phát cấu hình IPv4, cấp default gateway hoặc DNS sai. | DHCP snooping trên switch được hỗ trợ, phân định trusted port, 802.1X/NAC, giám sát lease và thay đổi. |
| **ARP spoofing/poisoning** | Host bị thuyết phục rằng IP gateway thuộc về MAC của thiết bị khác; lưu lượng có thể bị chuyển hướng, nghe lén ở nơi có thể hoặc gây gián đoạn. | Dynamic ARP Inspection (DAI), DHCP snooping bindings, IP Source Guard khi thích hợp, tách miền L2 và mã hóa end-to-end. |
| **Rogue IPv6 RA** | Host nhận route ::/0 hoặc cấu hình mạng do thiết bị giả mạo quảng bá. | RA Guard ở điểm truy cập phù hợp, kiểm soát cổng/thiết bị, giám sát RA và cấu hình IPv6 đúng. |
| **Gateway bị chiếm quyền** | Kẻ tấn công sửa route, ACL, NAT, DNS forwarding, hoặc làm gián đoạn dịch vụ. | Cô lập management plane, MFA/RBAC quản trị, cập nhật bản vá, sao lưu cấu hình, audit log và giám sát thay đổi. |
| **Route/ACL quá rộng** | Người dùng truy cập được các subnet hoặc dịch vụ không cần thiết, tăng nguy cơ lateral movement. | Segmentation, default-deny theo vùng, quy tắc ít quyền, kiểm thử allow/deny, log. |
| **Đường egress không kiểm soát** | Máy bị xâm nhập liên lạc ra ngoài qua gateway hoặc tuyến phụ ít được giám sát. | Egress filtering, DNS security, proxy/secure gateway theo thiết kế và giám sát lưu lượng ra. |

**Giới hạn cần nhớ:** DAI thường dựa vào thông tin ràng buộc do DHCP snooping thu thập, nên với host IP tĩnh có thể cần cấu hình binding/ARP ACL phù hợp; RA Guard cũng phải được triển khai đúng trên thiết bị và cổng thực sự hỗ trợ. Những tính năng này giảm rủi ro nhưng không thay thế xác thực và mã hóa ở lớp ứng dụng.

### 10.2. Đường đi của tấn công giả mạo gateway

Về mặt mô hình mối đe dọa, một máy lạ xuất hiện trong VLAN User có thể cố làm cho Client A **chọn nhầm next hop** qua phát DHCP không hợp lệ, gửi RA giả hoặc làm sai ánh xạ ARP. Hậu quả có thể là mất kết nối, định tuyến qua một thiết bị không được phê duyệt hoặc để lộ metadata mạng. Khi đó:

1. **Tài sản:** độ tin cậy của quyết định route, tính sẵn sàng của kết nối và dữ liệu trao đổi.
2. **Ranh giới tin cậy:** tín hiệu điều khiển mạng lớp 2 (DHCP/ARP/RA) đến từ thiết bị trên cùng liên kết.
3. **Bề mặt kiểm soát:** switch access, NAC, cấu hình gateway, firewall, DNS/TLS và quản trị endpoint.
4. **Bằng chứng:** thay đổi địa chỉ gateway/DNS, ánh xạ IP–MAC biến động, bản ghi DHCP/RA, cảnh báo DAI/RA Guard, thay đổi đường traceroute và log switch.

Mục đích của việc phân tích là **phát hiện và ngăn cấu hình sai/giả mạo trong mạng được phép quản trị**. Không thử giả mạo ARP, DHCP hoặc RA trên mạng của người khác.

### 10.3. Gateway, firewall và Zero Trust

Default gateway giúp đặt **điểm kiểm soát giữa các vùng mạng**: router/firewall có thể từ chối luồng **User → Database** trong khi vẫn cho phép **App → Database** trên đúng cổng. Tuy nhiên, chính sách chỉ dựa vào IP/port chưa xác minh người dùng thực sự là ai, thiết bị có đáng tin cậy không hoặc người dùng có quyền với chức năng ứng dụng nào.

Một kiến trúc Zero Trust bổ sung **xác thực danh tính, trạng thái thiết bị, quyền theo tài nguyên, quyết định chính sách, điểm thực thi và giám sát liên tục theo ngữ cảnh**. Router/gateway vẫn có ích cho phân đoạn và lọc east–west; vị trí “ở trong LAN” không nên tự cấp quyền truy cập dữ liệu.

Ví dụ policy logic tối thiểu:

~~~text
ALLOW  src=User subnet       dst=App gateway     service=HTTPS      purpose=web access
ALLOW  src=App workload      dst=Database        service=DB port    purpose=app data
DENY   src=User subnet       dst=Database        service=any        purpose=segmentation
DENY   src=unapproved source dst=Management      service=any        purpose=least privilege
~~~

Đây là **mô tả ý định**, không phải cú pháp cấu hình của firewall cụ thể. Cần áp rule tại đúng nơi có thể quan sát đường đi; nếu host có thêm NIC, VPN, đường cloud peering hoặc route tĩnh, phải kiểm tra các lối đi đó để tránh bỏ sót.

## 11. Bài thực hành: xác định và bảo vệ cổng mặc định

### 11.1. Chuẩn bị

Dùng môi trường VM hoặc phòng lab có quyền quản trị. Chuẩn bị Client A (10.10.10.25/24), Router R (10.10.10.1/24 và 10.20.20.1/24), Server B (10.20.20.50/24). Có thể cần switch/VLAN ảo. Trên R, bật IP forwarding và cấu hình firewall có chủ đích; trên B, cấu hình route ngược qua 10.20.20.1. **Không sử dụng địa chỉ hoặc thay đổi tuyến trong mạng sản xuất** cho bài tập này.

### 11.2. Các mốc thực hành

| Mốc | Nhiệm vụ | Bằng chứng đạt |
| --- | --- | --- |
| **A — Kiểm kê** | Xem IP/prefix, default route, ARP/ND của A và B. | Bản ghi địa chỉ nguồn, next hop, interface và tuyến về. |
| **B — So sánh** | Truy cập C trong cùng subnet và B khác subnet. | Với C: on-link; với B: next hop R, có bằng chứng route get và ARP. |
| **C — Quan sát frame** | Bắt packet ở A và, nếu có quyền, ở hai cổng R. | IP đích giữ nguyên khi router chuyển tiếp; MAC đích theo từng chặng thay đổi. |
| **D — Kiểm tra chặn** | Thiết lập rule chỉ cho phép luồng ứng dụng cần thiết giữa User và App. | Có log cho phép đúng cổng và log chặn một cổng không được phép. |
| **E — Mô phỏng lỗi an toàn** | Trong VM lab có console phục hồi, thử một cấu hình gateway/route không hợp lệ rồi khôi phục. | Ghi được triệu chứng, route dự kiến, neighbor state và bước khôi phục. |
| **F — Đánh giá bảo mật** | Kiểm kê vị trí có thể nhận rogue DHCP/RA/ARP và cơ chế switch bảo vệ. | Bảng rủi ro, biện pháp, giới hạn, log/kiểm thử dự kiến. |

Một bản báo cáo tốt cần có **sơ đồ đường đi, hai bảng route thực tế, kết quả route lookup, một dấu vết ARP/ND, kiểm thử allow/deny và giải thích đường phản hồi**. Ảnh chụp màn hình “ping thành công” không đủ để chứng minh rằng cổng mặc định đã được chọn và mạng đã được phân đoạn.

## 12. Tình huống tự kiểm tra kèm hướng giải

**Câu 1.** Client 10.10.10.25/24 có default gateway 10.10.10.1. Khi gửi đến 10.10.10.99, máy dùng MAC của ai?

**Hướng giải:** Nếu route trực tiếp 10.10.10.0/24 vẫn được ưu tiên và hai máy cùng liên kết, client phân giải MAC **của 10.10.10.99**; default gateway không tham gia chuyển packet đó.

**Câu 2.** Client có tuyến 10.20.20.0/24 qua 10.10.10.254 và default gateway 10.10.10.1. Packet đến 10.20.20.50 đi qua đâu?

**Hướng giải:** Host chọn **10.10.10.254** vì tuyến /24 cụ thể hơn /0. Muốn kết nối thành công, next hop .254 phải có đường đi và đường phản hồi hợp lệ.

**Câu 3.** Một host không có default route nhưng vẫn kết nối được 10.10.10.80. Điều đó mâu thuẫn không?

**Hướng giải:** Không. Host vẫn dùng tuyến trực tiếp cùng subnet; default route chỉ là phương án cuối khi không có tuyến cụ thể phù hợp.

**Câu 4.** Sau khi kết nối Wi-Fi khách, IPv6 hoạt động qua một router không mong muốn dù DHCPv4 gateway vẫn đúng. Nên kiểm tra gì?

**Hướng giải:** Kiểm tra **IPv6 default route và RA**, nguồn phát RA, cấu hình phân đoạn Wi-Fi và RA Guard. DHCPv4 gateway không xác định đường đi IPv6.

**Câu 5.** Client ping được gateway nhưng không truy cập HTTPS server ở VLAN khác. Khẳng định “gateway tốt nên không thể là lỗi mạng” có đúng không?

**Hướng giải:** Sai. Ping gateway chỉ xác minh một phần đường đi. Cần kiểm tra route/forwarding của R, firewall ở R và B, route phản hồi, TCP, TLS và ứng dụng.

**Câu 6.** Gateway đã chặn User → Database trực tiếp. Vì sao vẫn cần xác thực giữa App và Database?

**Hướng giải:** Nếu App bị chiếm quyền, kẻ tấn công có thể tận dụng chính đường App → Database đang được phép. Cần giới hạn danh tính dịch vụ, quyền DB, bảo vệ kết nối và giám sát, ngoài lớp phân đoạn mạng.

## 13. Ghi nhớ và tài liệu tham khảo

**Công thức tư duy khi gặp một gói tin:** **IP đích → tra bảng route → chọn next hop/interface → tìm MAC neighbor → gửi frame → router kiểm tra route/chính sách → đường phản hồi**.

- **Default gateway** là tuyến dự phòng cho đích chưa có route cụ thể hơn; không phải là tên khác của DNS, NAT, firewall hay “Internet”.
- Khi đi qua gateway, **địa chỉ MAC thay đổi theo chặng**, còn **IP nguồn/đích thông thường giữ nguyên** nếu không có NAT hoặc cơ chế thay đổi/đóng gói khác.
- **ARP (IPv4)** và **Neighbor Discovery (IPv6)** tìm hoặc xác nhận next hop trong liên kết cục bộ; không được nhầm next hop với đích IP cuối.
- **Route đúng chưa chắc kết nối thành công**: forwarding, policy firewall, trạng thái dịch vụ và return path cũng quyết định kết quả.
- Trong bảo mật mạng, kiểm soát DHCP/ARP/RA, phân đoạn, ACL, egress, log và chính sách truy cập theo danh tính giúp hạn chế sự cố khi cổng mặc định bị sai hoặc bị lợi dụng.

Nguồn chuẩn để tra cứu sâu:

1. **RFC 1122 — Requirements for Internet Hosts: Communication Layers:** nguyên tắc về IP host và tương tác với gateway.
2. **RFC 1812 — Requirements for IP Version 4 Routers:** nhiệm vụ chuyển tiếp và hành vi của router IPv4.
3. **RFC 2132 — DHCP Options and BOOTP Vendor Extensions:** định nghĩa các tùy chọn DHCPv4, bao gồm Router Option.
4. **RFC 3442 — The Classless Static Route Option for DHCPv4:** biểu diễn các route cụ thể do DHCP cấp.
5. **RFC 4861 — Neighbor Discovery for IP Version 6:** RA, default router, neighbor discovery.
6. **NIST SP 800-207 — Zero Trust Architecture:** phân biệt phạm vi mạng và quyết định truy cập dựa trên danh tính/ngữ cảnh.

Khi áp dụng vào thiết bị hoặc cloud cụ thể, cần đối chiếu phiên bản tài liệu của nhà cung cấp vì cách chọn metric, thực thi route và firewall khác nhau giữa các hệ thống.
