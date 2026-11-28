# Host, interface, subnet và route

Trong một mạng, máy tính không gửi gói tin trực tiếp đến mọi địa chỉ IP mà nó biết. Máy phải xác định địa chỉ nào thuộc mạng kết nối trực tiếp, địa chỉ nào cần đi qua bộ định tuyến, và gửi khung dữ liệu ra giao diện nào. Bốn khái niệm **host**, **interface**, **subnet** và **route** mô tả các quyết định đó.

Đây là nền tảng của **SECURITY_NETWORK_SECURITY**: muốn phân đoạn hệ thống, triển khai firewall/VPN/IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi hay mạng đám mây, trước hết phải biết một luồng lưu lượng đi từ host nào, qua các interface và subnet nào, theo route nào. Khi phân tích gói tin hoặc mô hình hóa mối đe dọa, bốn khái niệm này cũng giúp xác định ranh giới tin cậy và vị trí đặt điểm kiểm soát.

Sau bài học, bạn có thể:

- Phân biệt host, interface, địa chỉ IP, subnet, gateway và route.
- Đọc ký hiệu CIDR, nhận biết hai địa chỉ có cùng subnet hay không.
- Giải thích đường đi của gói tin trong cùng subnet và giữa các subnet.
- Đọc bảng định tuyến cơ bản, hiểu quy tắc chọn prefix cụ thể nhất và default route.
- Dùng kiến thức định tuyến để thiết kế phân đoạn mạng và khoanh vùng lỗi kết nối.

## 1. Bốn khái niệm và mối quan hệ

| Khái niệm | Ý nghĩa | Ví dụ | Góc nhìn bảo mật |
| --- | --- | --- | --- |
| **Host** | Thiết bị hoặc hệ thống tham gia truyền thông trên mạng; có thể có nhiều giao diện | Laptop, máy chủ, VM, container | Nguồn/đích của luồng, danh tính và mức độ tin cậy |
| **Interface** | Điểm kết nối mạng của host hoặc router, vật lý hay ảo | Ethernet eth0, Wi-Fi wlan0, loopback lo, interface VLAN, tunnel VPN | Điểm vào/ra lưu lượng và nơi gắn cấu hình, quy tắc lọc |
| **Subnet** | Phạm vi địa chỉ IP được xác định bởi network prefix và độ dài prefix | 10.10.10.0/24 | Đơn vị lập kế hoạch địa chỉ và phân đoạn ở lớp IP |
| **Route** | Quy tắc chỉ đường tới một prefix đích qua interface, có thể qua next hop | default via 10.10.10.1 dev eth0 | Xác định luồng sẽ đi qua thiết bị kiểm soát nào |

Một host có thể có nhiều interface; một interface có thể mang nhiều địa chỉ IP. Địa chỉ của interface thường nằm trong một subnet đã được cấu hình. Host dựa vào bảng định tuyến để quyết định interface ra và, khi cần, **next hop** (router kế tiếp). Router bản thân cũng là một host theo nghĩa có giao diện và địa chỉ, nhưng thực hiện thêm chức năng chuyển tiếp lưu lượng giữa các mạng.

**Phân biệt quan trọng:** subnet là khái niệm lớp 3 (IP); VLAN là cơ chế phân tách ở lớp 2 (Ethernet). Trong thiết kế thông thường, mỗi VLAN gắn với một subnet riêng, nhưng chúng không đồng nghĩa và không tự động tạo ra nhau.

## 2. Host và interface: địa chỉ được gắn ở đâu?

Giả sử một laptop dùng card Ethernet với cấu hình:

| Thuộc tính | Giá trị minh họa |
| --- | --- |
| Host | Laptop của nhân viên |
| Interface | eth0 |
| IPv4/prefix | 10.10.10.25/24 |
| Default gateway | 10.10.10.1 |
| MAC của eth0 | 02:00:00:00:10:25 |

**Host** là toàn bộ laptop, còn **eth0** là một đường nối mạng cụ thể của laptop. **10.10.10.25** là địa chỉ IPv4 gắn với interface đó; **/24** là độ dài network prefix. Địa chỉ MAC thuộc lớp liên kết dữ liệu và được dùng để chuyển khung trong một miền lớp 2, khác vai trò của địa chỉ IP.

Một máy chủ có thể đồng thời có eth0 nối mạng nội bộ, eth1 nối mạng quản trị, lo dùng giao tiếp nội bộ và tun0 phục vụ VPN. Đường đi đến một đích có thể thay đổi tùy bảng route, chính sách định tuyến và trạng thái các interface. Vì vậy, chỉ biết tên máy chưa đủ để kết luận lưu lượng xuất phát từ địa chỉ nào hoặc đi qua mạng nào.

Hai lưu ý thực tế:

- Interface **UP** không đảm bảo truy cập được đích: địa chỉ, VLAN, ARP/Neighbor Discovery, route, firewall và dịch vụ đích đều có thể gây lỗi.
- Một interface có thể mang nhiều địa chỉ IP; một hệ thống nhiều interface có thể có nhiều đường ra. Khi viết chính sách bảo mật, cần xem cả địa chỉ nguồn và đường đi thực tế.

## 3. Subnet và CIDR: đâu là mạng kết nối trực tiếp?

**CIDR** viết địa chỉ theo dạng **địa-chỉ/độ-dài-prefix**. Với IPv4, prefix dài từ /0 đến /32; số bit đầu tiên xác định phần mạng. Chẳng hạn:

- **10.10.10.25/24** thuộc subnet **10.10.10.0/24**; subnet mask tương ứng là **255.255.255.0**.
- Subnet /24 có **256** địa chỉ IPv4. Trong mô hình subnet Ethernet thông thường, địa chỉ mạng 10.10.10.0 và địa chỉ broadcast 10.10.10.255 không gán cho host; còn **254** địa chỉ unicast khả dụng.
- **10.10.11.20/24** thuộc **10.10.11.0/24**, nên không cùng subnet với 10.10.10.25/24.

Không thể kiểm tra hai địa chỉ có cùng mạng chỉ bằng cách đếm các nhóm số giống nhau. Phải áp dụng prefix:

| Địa chỉ/prefix | Network | Ghi chú |
| --- | --- | --- |
| 192.0.2.10/25 | 192.0.2.0/25 | Dải .0 đến .127 |
| 192.0.2.100/25 | 192.0.2.0/25 | Cùng subnet với .10/25 |
| 192.0.2.130/25 | 192.0.2.128/25 | Khác subnet dù cùng ba octet đầu |

Các địa chỉ **192.0.2.0/24** và **2001:db8::/32** trong ví dụ kỹ thuật được dành cho tài liệu; không phải địa chỉ để dùng trực tiếp trên Internet.

Mặc dù /24 phổ biến, không phải subnet nào cũng có 254 host: **/30** thường xuất hiện trong ví dụ đường nối router, **/31** được dùng cho một số liên kết point-to-point, còn **/32** biểu diễn một địa chỉ IPv4 đơn lẻ. Quy tắc trừ hai địa chỉ không áp dụng máy móc cho mọi loại prefix.

### Cùng subnet chưa chắc đã giao tiếp được

Thông thường, các host trong cùng subnet Ethernet có thể trao đổi trực tiếp qua switch sau khi phân giải địa chỉ lớp 2. Tuy nhiên, **VLAN khác nhau, private VLAN, client isolation, port ACL hoặc host firewall** vẫn có thể ngăn giao tiếp. Ngược lại, cấu hình subnet chồng lấn, proxy ARP hoặc mạng ảo có thể làm đường đi khác với trực giác. Hãy xem cấu hình và route thực tế thay vì suy ra kết nối chỉ từ địa chỉ IP.

## 4. Route: host chọn đường đi như thế nào?

Một route thường có các thông tin:

- **Destination prefix:** tập địa chỉ IP mà route áp dụng, ví dụ 10.20.20.0/24.
- **Next hop/gateway:** địa chỉ router kế tiếp nếu đích không trực tiếp trên liên kết.
- **Outgoing interface:** giao diện sẽ gửi gói tin ra.
- **Metric/ưu tiên và nguồn học route:** giúp chọn đường khi có các route phù hợp theo quy tắc của hệ điều hành; route có thể là connected, static hoặc học từ giao thức định tuyến.

Một host có IP 10.10.10.25/24 và gateway 10.10.10.1 thường có bảng IPv4 tương tự:

~~~text
Destination        Next hop       Interface
10.10.10.0/24      on-link        eth0
0.0.0.0/0          10.10.10.1     eth0
~~~

**On-link/connected route** cho biết subnet đã nối trực tiếp qua eth0; khi cần gửi tới 10.10.10.50, host phân giải MAC của chính 10.10.10.50. **Default route (0.0.0.0/0)** áp dụng khi không có route cụ thể hơn; với 10.20.20.20, host gửi khung lớp 2 đến MAC của gateway **10.10.10.1**, trong khi **địa chỉ IP đích của gói vẫn là 10.20.20.20**.

Trong một bảng route thông thường, **longest-prefix match** ưu tiên prefix khớp đích dài nhất. Xét bảng minh họa có hai router khác nhau trên cùng LAN:

~~~text
10.10.10.0/24    dev eth0
10.20.0.0/16     via 10.10.10.254 dev eth0
10.20.20.0/24    via 10.10.10.1   dev eth0
default          via 10.10.10.1   dev eth0
~~~

- Đích **10.20.20.20** khớp /24, /16 và default, nên chọn **10.20.20.0/24 qua .1**.
- Đích **10.20.30.20** khớp /16 và default, nên chọn **10.20.0.0/16 qua .254**.
- Đích **8.8.8.8** chỉ khớp default trong bảng này, nên đi qua **.1**.

Ví dụ trên giả định hai next hop **10.10.10.1** và **10.10.10.254** đều có thể truy cập trên subnet local. Trong hệ thống có **policy routing**, quy tắc chọn bảng route theo nguồn, interface, đánh dấu gói tin hoặc tiêu chí khác có thể tác động trước bước so prefix. Route không đồng nghĩa với quyền truy cập: firewall và các chính sách khác có thể tiếp tục chặn gói tin dù có đường đi hợp lệ.

### Các bước gửi một gói tin IPv4

1. Ứng dụng xác định **IP đích**; nếu người dùng nhập tên miền, quá trình phân giải DNS thường diễn ra trước.
2. Host tra bảng route và chọn **interface ra**, **địa chỉ nguồn phù hợp** và **next hop**, nếu cần.
3. Trên Ethernet, host sử dụng **ARP** để tìm MAC của IP next hop: MAC của đích nếu on-link, hoặc MAC của gateway nếu đi ra mạng khác.
4. Switch chuyển tiếp khung Ethernet tới cổng thích hợp. Router kiểm tra gói IP, chọn chặng tiếp theo, giảm **TTL** và đóng gói lại trong khung lớp 2 phù hợp với mạng kế tiếp.
5. Các thiết bị firewall, VPN gateway, IDS/IPS hoặc chính sách trên host có thể cho phép, chặn, ghi log hoặc xử lý luồng tại những điểm tương ứng. Đích trả lời theo **bảng route của chính nó**; kết nối hai chiều đòi hỏi đường về và chính sách cho chiều trả lời.

ARP chỉ phân giải IP sang MAC trong phạm vi liên kết IPv4; nó không tìm trực tiếp MAC của server ở subnet xa. Trong IPv6, **Neighbor Discovery (ND)** qua ICMPv6 đảm nhiệm vai trò tương tự và còn tham gia tìm router.

## 5. Mô hình thực tế: phân đoạn Users, App và Database

Giả sử doanh nghiệp tổ chức ba subnet, mỗi subnet đi với một VLAN, và mọi lưu lượng liên subnet phải qua firewall kiêm router:

~~~mermaid
flowchart LR
    U["Host người dùng<br/>10.10.10.25/24"] --> V10["VLAN Users<br/>10.10.10.0/24"]
    V10 --> FW["Firewall / Router L3"]
    FW --> V20["VLAN App<br/>10.20.20.0/24"]
    V20 --> A["App server<br/>10.20.20.20"]
    FW --> V30["VLAN DB<br/>10.30.30.0/24"]
    V30 --> DB["Database<br/>10.30.30.30"]
~~~

| Vùng | Subnet | Gateway trên firewall | Tài nguyên |
| --- | --- | --- | --- |
| Users | 10.10.10.0/24 | 10.10.10.1 | Laptop 10.10.10.25 |
| App | 10.20.20.0/24 | 10.20.20.1 | Web/API 10.20.20.20 |
| DB | 10.30.30.0/24 | 10.30.30.1 | Database 10.30.30.30 |

Các gateway ở bảng trên là địa chỉ interface lớp 3 của firewall trong từng subnet. Mỗi server cần route phù hợp để gửi phản hồi về subnet nguồn; thường là default route qua gateway của subnet mình.

### Theo dõi một yêu cầu HTTPS

1. Laptop **10.10.10.25** muốn kết nối **10.20.20.20:443**. IP đích nằm ngoài **10.10.10.0/24**, nên laptop chọn default route qua **10.10.10.1**.
2. Laptop gửi khung Ethernet đến MAC của interface Users trên firewall. Địa chỉ IP nguồn/đích vẫn là **10.10.10.25 → 10.20.20.20** nếu chưa có NAT.
3. Firewall kiểm tra policy **Users → App**, xác định route đến **10.20.20.0/24** qua interface App rồi chuyển tiếp nếu được phép.
4. Server App nhận yêu cầu, trả lời về **10.10.10.25** qua gateway **10.20.20.1**. Một firewall có trạng thái thường cho phép gói phản hồi thuộc kết nối đã được cho phép theo bảng trạng thái của nó.

Một bộ quy tắc tối thiểu theo nguyên tắc **least privilege** có thể là:

| Luồng | Chính sách ví dụ | Lý do |
| --- | --- | --- |
| Users → App, TCP 443 | Cho phép theo nhu cầu nghiệp vụ | Người dùng truy cập ứng dụng |
| App → DB, TCP 5432 | Chỉ cho phép từ App được cấp quyền | Ứng dụng truy cập PostgreSQL |
| Users → DB, mọi cổng | Từ chối | Tránh truy cập trực tiếp cơ sở dữ liệu |
| Các luồng liên vùng khác | Từ chối mặc định, mở theo yêu cầu | Giảm khả năng di chuyển ngang |

**Các port chỉ là ví dụ**, cần thay theo dịch vụ thực tế. Nên xác thực ở lớp ứng dụng và tại database; chính sách IP/port không thay thế xác thực và phân quyền. Nếu không có gateway, route hoặc chính sách cho luồng App → DB thì việc hai subnet tồn tại trên cùng firewall không tự bảo đảm ứng dụng truy cập được database.

### Vì sao ranh giới ở đây là quan trọng?

- **VLAN** hạn chế phạm vi broadcast/ARP của Ethernet và cô lập các miền lớp 2 khi được cấu hình đúng.
- **Router/firewall** là điểm kiểm soát liên subnet, nơi có thể áp dụng ACL, kiểm tra trạng thái, ghi log và giám sát IDS/IPS.
- **Host firewall** vẫn cần thiết vì hai host cùng subnet có thể giao tiếp mà không đi qua firewall liên subnet.
- **IDS/IPS** chỉ quan sát hoặc xử lý được luồng nằm trên đường đi của nó; lưu lượng nội bộ cùng VLAN có thể không đi qua cảm biến đặt tại firewall.
- **VPN** tạo interface/tunnel và có thể thêm các route riêng; route quyết định lưu lượng nào đi vào tunnel, còn chính sách phân quyền quyết định đích nào được phép truy cập.

Hãy kiểm tra cả **đường đi chiều về**: thiếu return route hoặc đường đi bất đối xứng qua các firewall có trạng thái có thể làm phiên kết nối thất bại dù chiều đi có route và rule hợp lệ.

## 6. IPv6: cùng mô hình, một số cơ chế khác

IPv6 vẫn có host, interface, subnet và route. Ví dụ interface có địa chỉ **2001:db8:10::25/64** thuộc subnet **2001:db8:10::/64**. /64 phổ biến trên LAN IPv6, nhưng không phải mọi liên kết đều bắt buộc dùng /64; một số kết nối point-to-point sử dụng prefix khác.

So với IPv4:

| Nội dung | IPv4 | IPv6 |
| --- | --- | --- |
| Độ dài địa chỉ | 32 bit | 128 bit |
| Ví dụ default route | 0.0.0.0/0 | ::/0 |
| Tìm địa chỉ MAC của neighbor | ARP | Neighbor Discovery dùng ICMPv6 |
| Cơ chế broadcast | Có broadcast IPv4 | Không có broadcast IPv4-style; dùng multicast |
| Khám phá router và tự cấu hình | Thường dùng DHCPv4 hoặc cấu hình tĩnh | Router Advertisement, SLAAC, DHCPv6 hoặc cấu hình tĩnh tùy môi trường |

IPv6 có **link-local address** (thường thuộc fe80::/10), được dùng trên chính liên kết; route tới router IPv6 có thể tham chiếu gateway link-local gắn với interface cụ thể. Đừng chặn toàn bộ ICMPv6 vì Neighbor Discovery và một số thông báo lỗi thiết yếu của IPv6 phụ thuộc vào nó. Mọi phân đoạn và rule IPv4 nên được rà soát tương ứng cho IPv6 nếu hệ thống bật dual-stack.

Về bảo mật, **RA spoofing** và **ND spoofing** là các rủi ro cần xét ở lớp liên kết; các biện pháp như RA Guard có thể hữu ích khi phần cứng, topology và cấu hình phù hợp.

## 7. Đọc trạng thái mạng trên Linux

Các lệnh sau chỉ **xem thông tin** và phù hợp cho việc khám phá hoặc khắc phục sự cố trong môi trường được phép:

~~~bash
# Liệt kê interface và IP gắn với chúng
ip -br addr

# Bảng định tuyến IPv4 và IPv6
ip -4 route show
ip -6 route show

# Xem hệ điều hành dự kiến đi đâu để tới một đích
ip -4 route get 10.20.20.20

# Xem cache neighbor: ARP (IPv4) hoặc ND (IPv6)
ip neigh show

# Kiểm tra có quy tắc policy routing nào được áp dụng
ip rule show
~~~

Trong mô hình ba VLAN bên trên, laptop có thể hiển thị đầu ra tương tự:

~~~text
$ ip -br addr
eth0             UP             10.10.10.25/24

$ ip -4 route show
default via 10.10.10.1 dev eth0
10.10.10.0/24 dev eth0 proto kernel scope link src 10.10.10.25

$ ip -4 route get 10.20.20.20
10.20.20.20 via 10.10.10.1 dev eth0 src 10.10.10.25
~~~

Đây là **đầu ra minh họa**, không phải kết quả thực thi trên máy của bạn. Tên interface, metric, route bổ sung và định dạng có thể khác theo hệ điều hành hoặc phiên bản công cụ.

Để phân tích từng tầng, có thể kết hợp **ping** hoặc **traceroute** với log firewall, thông tin DHCP và lưu lượng bắt được bằng **tcpdump/Wireshark** trong phạm vi được cấp phép. Ping không chứng minh rằng TCP/UDP của ứng dụng hoạt động; nhiều thiết bị lọc ICMP. Traceroute cũng có thể không hiển thị toàn bộ các router do chính sách lọc hoặc cách mạng xử lý TTL.

## 8. Sự cố thường gặp và cách khoanh vùng

| Triệu chứng | Nghi vấn cần kiểm tra | Bằng chứng hữu ích |
| --- | --- | --- |
| Không tới được host cùng subnet | Sai subnet mask, VLAN/port, trùng IP, ARP/ND hoặc host firewall | IP/prefix của hai host, switch VLAN, bảng neighbor |
| Tới gateway nhưng không tới mạng khác | Thiếu route, firewall chặn, router không chuyển tiếp hoặc mất route chiều về | Bảng route hai đầu, log firewall, trace |
| Ping được IP nhưng mở ứng dụng thất bại | Policy cổng/protocol, dịch vụ không lắng nghe, TLS hoặc xác thực lỗi | Kết nối TCP đến port đích, log dịch vụ và firewall |
| Truy cập bằng IP được nhưng bằng tên miền không được | DNS resolver, bản ghi DNS hoặc chính sách DNS | Kết quả phân giải tên và IP đích thực tế |
| Chỉ lỗi sau khi kết nối VPN | Route VPN/split tunnel, subnet trùng, policy qua tunnel | Interface VPN, ip route get, DNS qua VPN |
| IPv4 chạy nhưng IPv6 lỗi hoặc đi ngoài dự kiến | Default route IPv6, RA/ND, rule IPv6 thiếu hoặc khác IPv4 | ip -6 route, ip -6 addr, log firewall IPv6 |

Quy trình chẩn đoán có thể thực hiện theo thứ tự:

1. **Xác định luồng:** IP nguồn, IP đích, protocol/port, interface và thời điểm; tránh kết luận từ tên miền khi chưa biết IP đã phân giải.
2. **Kiểm tra interface và địa chỉ:** interface có hoạt động không, IP/prefix và VLAN có đúng không?
3. **Kiểm tra route ở nguồn:** đích được xem là on-link hay đi gateway nào? Lệnh tra route phải khớp với đích đang kiểm tra.
4. **Kiểm tra từng chặng và điểm lọc:** route của router, NAT nếu có, firewall ACL/state, host firewall, dịch vụ đích và vị trí cảm biến giám sát.
5. **Kiểm tra chiều về:** server chọn gateway nào để trả lời, route có đối xứng hợp lý không và policy có cho phép phản hồi không?

Lưu ý **NAT không thay thế định tuyến**: NAT thay đổi thông tin địa chỉ/cổng theo quy tắc, còn bảng route vẫn cần thiết để chuyển gói tới mạng kế tiếp. Một route thành công cũng không đồng nghĩa các firewall cho phép truy cập.

## 9. Áp dụng khi thiết kế mạng an toàn

Khi xây dựng kiến trúc mạng, hãy lập bảng **nguồn → đích → giao thức/cổng → subnet/VLAN → next hop → điểm kiểm soát → luồng trả lời** trước khi cấu hình rule. Cách biểu diễn này giúp phát hiện đường đi bỏ qua firewall, các subnet chồng lấn, hoặc quyền truy cập rộng hơn nhu cầu.

Một số nguyên tắc thực hành:

- **Phân tách vùng tin cậy:** thiết bị nhân viên, server ứng dụng, database, hệ thống quản trị và khách Wi-Fi nên có phạm vi địa chỉ và policy phù hợp với nhu cầu truy cập.
- **Kiểm soát ở đúng nơi lưu lượng đi qua:** firewall liên subnet không thấy mọi luồng cùng VLAN; kết hợp host firewall, kiểm soát cổng switch và giám sát bên trong khi cần.
- **Bảo vệ lớp liên kết:** cân nhắc DHCP snooping, Dynamic ARP Inspection và phòng chống rogue RA theo khả năng thiết bị để giảm giả mạo gateway/neighbor.
- **Kiểm soát route và thay đổi cấu hình:** tránh route quá rộng, default gateway ngoài dự kiến, route chồng lấn và subnet trùng giữa mạng nội bộ, VPN, đối tác.
- **Thiết kế cho mạng đám mây:** trong VPC/VNet, subnet, route table, gateway, security group và network ACL là các cơ chế riêng biệt; phải kiểm tra cả đường đi lẫn policy của từng nền tảng.
- **Duy trì quan sát và kiểm chứng:** đối chiếu bảng route, flow log, firewall log, DNS và sensor IDS/IPS với các luồng thật; đo cả chiều đi và chiều về.

### Ví dụ suy luận cuối bài

Máy A là **10.10.10.25/24**, máy B là **10.10.10.80/24**, máy C là **10.20.20.20/24**. A có default gateway **10.10.10.1**.

- **A → B:** A nhận biết B thuộc 10.10.10.0/24, nên thử gửi trực tiếp trên liên kết qua MAC của B. Nếu switch hoặc policy cô lập client thì kết nối vẫn có thể bị chặn.
- **A → C:** C nằm ngoài subnet của A, nên A gửi gói tới MAC của gateway 10.10.10.1. Router/firewall phải có route và policy thích hợp đến subnet của C.
- **C → A:** C không tự dùng route của A; nó cần gateway/route của chính mình và các chính sách cho phép trả lời. Chỉ nhìn route chiều A → C sẽ chưa đủ để xác nhận kết nối thành công.

Nắm được bốn khái niệm này cho phép bạn chuyển một câu hỏi mơ hồ như “vì sao server không kết nối được?” thành các kiểm tra cụ thể: **host nào, interface nào, subnet nào, route nào và policy nào đang quyết định đường đi của luồng đó?**
