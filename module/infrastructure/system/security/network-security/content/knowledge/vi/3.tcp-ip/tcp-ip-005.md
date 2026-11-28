# Routing table: bảng định tuyến trong TCP/IP

Khi một máy cần gửi gói IP đến máy khác, nó phải quyết định **đưa gói ra interface nào** và **chuyển cho router kế tiếp nào**. Câu trả lời chủ yếu nằm trong **routing table (bảng định tuyến)**. Router sử dụng bảng này để chuyển tiếp giữa các mạng; máy tính, máy chủ, thiết bị VPN và nhiều thiết bị mạng khác cũng dùng bảng định tuyến khi gửi lưu lượng.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, hiểu bảng định tuyến là điều kiện để phân tích lưu lượng, chia vùng mạng, đặt firewall hoặc IDS/IPS đúng chỗ, kiểm tra VPN, bảo vệ đường ra Internet và thiết kế kết nối an toàn trong hạ tầng đám mây. Một route giúp hệ thống *tìm đường* đến đích; route **không tự cấp quyền** cho kết nối, không xác thực người dùng và không thay thế chính sách bảo mật.

Sau bài này, bạn sẽ có thể:

- Đọc các trường quan trọng của một route: **destination prefix, next hop, interface, metric** và nguồn route.
- Giải thích cách chọn route theo **longest-prefix match**, cách dùng default route và phân biệt metric với độ dài prefix.
- Theo dõi lưu lượng trong cùng subnet, giữa các subnet và qua VPN.
- Xem, kiểm tra và thử thêm route tĩnh trên Linux trong môi trường thực hành.
- Phân tích các lỗi định tuyến thường gặp và tác động đến firewall, giám sát, mạng nội bộ và cloud.

## 1. Routing table là gì?

**Routing table** chứa những chỉ dẫn để hệ điều hành hoặc thiết bị định tuyến quyết định chặng kế tiếp của gói IP. Mỗi dòng trong bảng là một **route** đến một địa chỉ hoặc một tập địa chỉ đích. Thiết bị so khớp **IP đích** với các route và chọn đường phù hợp theo quy tắc của ngăn xếp mạng.

Ví dụ máy nhân viên có địa chỉ **10.10.10.25/24**, interface **eth0** và gateway **10.10.10.1**:

~~~text
Destination       Next hop      Interface
10.10.10.0/24     on-link       eth0
0.0.0.0/0         10.10.10.1    eth0
~~~

Hai dòng có ý nghĩa khác nhau:

1. Đích thuộc **10.10.10.0/24** có thể đến trực tiếp trên liên kết qua **eth0**; host không cần gửi cho router để tìm một host khác thuộc cùng liên kết.
2. Đích không khớp route cụ thể hơn có thể dùng **default route** và được gửi đến **10.10.10.1**.

Trên Ethernet IPv4, nếu đích trực tiếp trên liên kết, host cần phân giải MAC của **IP đích** bằng ARP; nếu đích đi qua gateway, host cần MAC của **IP gateway**. Trong cả hai trường hợp, địa chỉ IP đích trong gói vẫn là đích cuối cùng, trừ khi có cơ chế như NAT thay đổi nó.

### Routing khác forwarding ở điểm nào?

- **Routing** là việc xác định và duy trì các đường đi, có thể thông qua cấu hình tĩnh hoặc giao thức như OSPF, IS-IS, BGP.
- **Forwarding** là việc xử lý gói thực tế: tra thông tin chuyển tiếp, chọn interface ra và gửi đến chặng kế tiếp.
- Trong nhiều thiết bị mạng, **RIB** (*Routing Information Base*) lưu các thông tin route được học và chọn; **FIB** (*Forwarding Information Base*) là cấu trúc tối ưu được dùng để chuyển tiếp gói. Cách hiện thực tùy hệ điều hành và thiết bị.

Một thiết bị có route đến đích vẫn có thể không gửi được gói: interface có thể down, gateway không truy cập được, firewall chặn, hoặc phía đích không có đường trả lời.

## 2. Các thành phần của một route

Một dòng route có thể biểu diễn như sau:

~~~text
10.20.20.0/24 via 10.10.10.1 dev eth0 metric 100
~~~

| Thành phần | Giá trị minh họa | Vai trò |
| --- | --- | --- |
| **Destination prefix** | 10.20.20.0/24 | Tập địa chỉ IP đích mà route bao phủ |
| **Next hop / gateway** | 10.10.10.1 | Router sẽ nhận gói để tiếp tục chuyển tiếp |
| **Outgoing interface** | eth0 | Giao diện mà gói được đưa ra |
| **Metric** | 100 | Chi phí/ưu tiên theo quy tắc của hệ thống khi so các route đủ điều kiện |
| **Protocol / nguồn** | kernel, static, DHCP, OSPF… | Route được tạo hoặc học từ đâu |
| **Scope / kiểu route** | link, global, local; unicast, blackhole… | Giới hạn sử dụng và hành vi của route |

Không phải hệ điều hành nào cũng in tất cả các trường; tên trường và cách tính metric cũng khác nhau. Một số route còn có thông tin về nguồn IP ưu tiên, MTU, trọng số khi dùng nhiều next hop hoặc bảng định tuyến áp dụng.

**Next hop phải có cách tiếp cận hợp lệ:** host phải biết gửi đến gateway bằng một đường trực tiếp hoặc một cơ chế phân giải next hop phù hợp. Cấu hình route trỏ đến IP gateway không thể tiếp cận thường bị từ chối hoặc dẫn đến mất kết nối; route không tự tạo ra một đường vật lý.

### Các loại route thường gặp

| Loại | Ví dụ | Khi nào xuất hiện? |
| --- | --- | --- |
| **Connected / on-link** | 10.10.10.0/24 dev eth0 | Subnet gắn trực tiếp với interface, thường được tạo khi cấu hình IP |
| **Local** | 10.10.10.25/32 local dev eth0 | Địa chỉ của chính thiết bị; kernel có thể quản lý ở bảng riêng |
| **Static** | 10.20.20.0/24 via 10.10.10.1 | Quản trị viên khai báo thủ công |
| **Dynamic** | Route học từ OSPF hoặc BGP | Router học thông tin từ thiết bị khác theo giao thức |
| **Default** | 0.0.0.0/0 via 10.10.10.1 | Đường dự phòng khi không có prefix đích cụ thể hơn |
| **Blackhole / unreachable** | blackhole 10.99.0.0/16 | Cố ý loại bỏ hoặc báo không thể đến đích tùy loại route |

**Static** và **dynamic** mô tả cách route được tạo ra; **connected**, **default** và **blackhole** mô tả vai trò hoặc hành vi. Chúng là các cách phân loại khác nhau, không phải lúc nào cũng loại trừ nhau: một default route có thể được cấu hình tĩnh hoặc học động.

## 3. Prefix, CIDR và longest-prefix match

Đích của một route thường viết theo **CIDR**: địa chỉ mạng kèm số bit prefix. IPv4 dài 32 bit nên độ dài prefix nằm từ **/0** đến **/32**. IPv6 dài 128 bit, từ **/0** đến **/128**.

Ví dụ:

- **10.20.0.0/16** bao phủ 10.20.0.0 đến 10.20.255.255.
- **10.20.20.0/24** bao phủ 10.20.20.0 đến 10.20.20.255 và là tập con của 10.20.0.0/16.
- **10.20.20.7/32** chỉ khớp một địa chỉ IPv4.
- **0.0.0.0/0** khớp mọi địa chỉ IPv4, nhưng chỉ được dùng khi không có route được ưu tiên hơn theo chính sách tra bảng.

Khi nhiều route **trong cùng ngữ cảnh tra cứu** đều khớp IP đích, hệ thống thông thường chọn route có **prefix dài nhất** (*longest-prefix match*, LPM), tức route cụ thể nhất.

Giả sử eth0 của host thuộc **10.10.10.0/24**, cả hai router **10.10.10.1** và **10.10.10.254** đều truy cập được trên liên kết:

~~~text
10.10.10.0/24   dev eth0
10.20.0.0/16    via 10.10.10.254 dev eth0
10.20.20.0/24   via 10.10.10.1   dev eth0
10.20.20.7/32   via 10.10.10.254 dev eth0
default         via 10.10.10.1   dev eth0
~~~

| IP đích | Route được chọn | Giải thích |
| --- | --- | --- |
| 10.10.10.60 | 10.10.10.0/24, on-link | Đích nằm trong mạng trực tiếp |
| 10.20.20.8 | 10.20.20.0/24 via .1 | /24 cụ thể hơn /16 |
| 10.20.20.7 | 10.20.20.7/32 via .254 | /32 cụ thể nhất |
| 10.20.30.8 | 10.20.0.0/16 via .254 | Khớp /16 nhưng không khớp /24 |
| 8.8.8.8 | default via .1 | Không có route cụ thể hơn |

**Metric không vượt qua longest-prefix match thông thường:** một route /24 có metric lớn vẫn được ưu tiên hơn route /16 khớp cùng đích chỉ vì /24 cụ thể hơn. Metric thường quan trọng khi cần phân xử các route cùng prefix và đủ điều kiện, nhưng thứ tự xử lý còn phụ thuộc chính sách, giao thức và cách hệ điều hành hiện thực.

### Bảng route nào được tra trước?

Trên Linux, **policy routing** dùng các quy tắc (*routing policy database* / RPDB) để chọn bảng route dựa trên tiêu chí như địa chỉ nguồn, địa chỉ đích, interface vào, mark hoặc ưu tiên rule. LPM được áp dụng **trong bảng** đã được chọn. Vì vậy, không nên khẳng định mọi route trên toàn máy đều tham gia một phép so prefix duy nhất.

Một hệ thống Linux thông thường có các bảng như:

- **local**: route cho địa chỉ của chính máy, broadcast và một số đích đặc biệt.
- **main**: các connected route, static route và default route thông thường.
- **default**: bảng phụ dự phòng, thường rỗng trong cấu hình cơ bản.
- **Bảng tùy chỉnh**: phục vụ policy routing, đa WAN, container hay VPN.

Nếu có nhiều đường ngang nhau và được thiết lập **ECMP** (*Equal-Cost Multi-Path*), thiết bị có thể phân phối các luồng qua nhiều next hop dựa trên hash; không nên mặc định mọi gói của một kết nối sẽ luân phiên qua các tuyến.

## 4. Một gói IP đi qua bảng định tuyến thế nào?

Xét hệ thống:

~~~mermaid
flowchart LR
    U["Laptop<br/>10.10.10.25/24"] --> SW["Switch<br/>VLAN Users"]
    SW --> F["Firewall / Router<br/>10.10.10.1<br/>10.20.20.1"]
    F --> APP["App server<br/>10.20.20.20/24"]
    F --> WAN["Router WAN / VPN"]
    WAN --> EXT["Mạng khác"]
~~~

Laptop có route đến **10.10.10.0/24** và default route qua **10.10.10.1**. Firewall có interface lớp 3 ở subnet **10.10.10.0/24** và **10.20.20.0/24**.

Khi laptop mở kết nối TCP tới **10.20.20.20:443**:

1. Ứng dụng xác định IP đích. Nếu dùng tên miền thì việc phân giải DNS thường xảy ra trước; DNS chọn địa chỉ đích, còn routing table quyết định cách gửi tới địa chỉ đó.
2. Hệ điều hành tra bảng route. Đích **10.20.20.20** không nằm trong **10.10.10.0/24**, nên laptop dùng default gateway **10.10.10.1**.
3. Trên Ethernet IPv4, laptop dùng ARP để lấy MAC của gateway **10.10.10.1**, rồi gửi khung đến MAC đó. IP đích trong gói vẫn là **10.20.20.20**.
4. Firewall nhận gói, kiểm tra các chính sách áp dụng, tra route tới **10.20.20.0/24** và chuyển tiếp qua interface phía App nếu được phép. Router giảm TTL của gói IPv4 trong quá trình chuyển tiếp.
5. App server phản hồi tới **10.10.10.25** theo bảng route **của chính server**, thông thường qua gateway **10.20.20.1**. Firewall phải xử lý được gói phản hồi.

Hai điều dễ nhầm:

- **MAC thay đổi theo từng liên kết Ethernet**, còn cặp IP nguồn/đích có thể giữ nguyên qua các router; NAT và tunnel là các ngoại lệ cần xét riêng.
- **Có route chiều đi chưa đủ:** nếu đích thiếu route về, firewall chặn, policy trên host từ chối hoặc dịch vụ không lắng nghe thì kết nối vẫn thất bại.

### Gói cùng subnet

Nếu laptop **10.10.10.25/24** gửi đến **10.10.10.50/24**, connected route dẫn lưu lượng ra eth0 trực tiếp tới MAC của **10.10.10.50** trên liên kết, không cần router xử lý luồng đó. Một firewall chỉ đặt ở ranh giới giữa các subnet thường **không thấy** lưu lượng nội bộ cùng VLAN. Để kiểm soát, có thể cần host firewall, port ACL, private VLAN, microsegmentation hoặc cảm biến bố trí thích hợp.

## 5. Quan sát routing table trên Linux

Các lệnh sau **chỉ đọc trạng thái**, phù hợp để phân tích đường đi trong môi trường bạn được phép kiểm tra:

~~~bash
# Xem địa chỉ và trạng thái của các interface
ip -br addr

# Xem bảng route chính cho IPv4/IPv6
ip -4 route show table main
ip -6 route show table main

# Xem mọi route, kể cả các bảng đặc biệt
ip -4 route show table all

# Xem các rule chọn bảng định tuyến
ip rule show

# Kiểm tra lựa chọn route thực tế cho đích
ip -4 route get 10.20.20.20

# Kiểm tra route khi chọn một địa chỉ nguồn cụ thể
ip -4 route get 10.20.20.20 from 10.10.10.25

# Xem neighbor đã phân giải ở lớp liên kết
ip neigh show
~~~

Trên laptop minh họa, đầu ra rút gọn có thể như sau:

~~~text
$ ip -br addr
eth0     UP      10.10.10.25/24

$ ip -4 route show table main
default via 10.10.10.1 dev eth0 metric 100
10.10.10.0/24 dev eth0 proto kernel scope link src 10.10.10.25

$ ip -4 route get 10.20.20.20
10.20.20.20 via 10.10.10.1 dev eth0 src 10.10.10.25
~~~

Đây là **kết quả minh họa**, không phải log của một máy thực. Cần hiểu:

- **via 10.10.10.1**: gói sẽ gửi tới router kế tiếp trên liên kết.
- **dev eth0**: interface ra được chọn.
- **src 10.10.10.25**: địa chỉ nguồn được hệ thống đề xuất trong tra cứu này; ứng dụng hoặc policy có thể ảnh hưởng đến việc chọn nguồn.
- **proto kernel scope link**: connected route được kernel tạo cho mạng có thể truy cập trực tiếp.

Với Windows, có thể kiểm tra bằng:

~~~powershell
# Bảng định tuyến IPv4 theo dạng quen thuộc
route print -4

# Xem route trong PowerShell
Get-NetRoute -AddressFamily IPv4
~~~

**Lưu ý:** các lệnh hiển thị của Linux và Windows không nhất thiết trình bày metric hay lựa chọn route giống nhau. Nếu kết quả không khớp dự đoán, hãy kiểm tra cả routing rules, các bảng phụ và phần mềm VPN/ảo hóa.

## 6. Thực hành route tĩnh và route mặc định

Giả sử một phòng lab có máy **10.10.10.25/24** và router phụ **10.10.10.254** dẫn tới mạng **10.40.0.0/16**. Ta muốn lưu lượng tới **10.40.0.0/16** đi qua router phụ, còn phần lớn đích khác vẫn đi qua gateway **10.10.10.1**.

Trên Linux, một quản trị viên có thể cấu hình:

~~~bash
# Minh họa: yêu cầu quyền quản trị và router .254 phải truy cập được
sudo ip route add 10.40.0.0/16 via 10.10.10.254 dev eth0

# Xác minh kết quả trước khi thử dịch vụ
ip -4 route get 10.40.2.15

# Gỡ route tạm khi kết thúc thí nghiệm
sudo ip route del 10.40.0.0/16 via 10.10.10.254 dev eth0
~~~

Kết quả tra route dự kiến sẽ chứa **10.40.2.15 via 10.10.10.254 dev eth0** nếu không có bảng/chính sách khác chi phối. Các lệnh **ip route add/del** thay đổi bảng route đang hoạt động và thường **không tự tồn tại qua khởi động lại**; cấu hình vĩnh viễn được quản lý qua NetworkManager, systemd-networkd hoặc công cụ mạng của bản phân phối.

Chỉ thử trên máy lab hoặc môi trường được cấp quyền: thay đổi route, đặc biệt là **default route**, có thể cắt kết nối SSH, VPN hoặc đường tới hệ thống quản trị. Đọc trạng thái và lưu sẵn phương án khôi phục trước khi sửa route trên máy từ xa.

### Metric khi có hai đường ra

Ví dụ hai default route tới hai gateway:

~~~text
default via 192.0.2.1 dev wan0 metric 100
default via 198.51.100.1 dev wan1 metric 200
~~~

Giả sử cả hai interface/gateway đều hợp lệ và hệ điều hành chấp nhận cấu hình này, đường **metric 100** thường được ưu tiên so với đường **metric 200** cho cùng prefix default. Tuy vậy, metric nhỏ **không bảo đảm** gateway còn kết nối đến Internet. Nếu WAN chính mất kết nối ở xa nhưng interface vẫn UP, cơ chế chuyển dự phòng có thể cần giám sát sức khỏe đường truyền và cập nhật route.

Để làm ví dụ trên nhất quán, wan0 và wan1 phải có địa chỉ thuộc những subnet phù hợp với từng gateway. Một tuyến có metric thấp cũng không vượt qua rule policy routing chọn bảng khác.

## 7. Routing table, firewall, NAT và phân đoạn mạng

Mỗi cơ chế giải quyết một vấn đề khác nhau:

| Cơ chế | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Routing table** | Đi đến IP đích qua đâu? | 10.30.0.0/16 qua firewall nội bộ |
| **Firewall / ACL** | Gói hoặc kết nối này có được phép không? | Chỉ App được kết nối DB TCP 5432 |
| **NAT** | Có cần đổi địa chỉ/cổng trên luồng không? | Mạng private truy cập Internet qua địa chỉ public |
| **DNS** | Tên miền tương ứng địa chỉ nào? | app.example.test trỏ tới IP của dịch vụ |
| **IDS/IPS** | Luồng nào được quan sát hoặc ngăn chặn? | Cảm biến kiểm tra lưu lượng giữa hai vùng |

Không nên diễn giải route tới một subnet là quyền truy cập mặc định tới tất cả host của subnet đó.

Ví dụ mô hình ba vùng:

| Vùng | Subnet | Mục đích |
| --- | --- | --- |
| Users | 10.10.10.0/24 | Máy trạm |
| App | 10.20.20.0/24 | Dịch vụ web/API |
| DB | 10.30.30.0/24 | Dữ liệu |

Nếu ba subnet có connected route trên cùng firewall/router, thiết bị **có khả năng biết đường** giữa chúng. Nhưng chính sách nên giới hạn:

1. Users → App: chỉ các cổng ứng dụng cần thiết (ví dụ TCP 443).
2. App → DB: chỉ host/service được phép và cổng DB tương ứng (ví dụ TCP 5432).
3. Users → DB: mặc định từ chối, trừ ngoại lệ được phê duyệt.

Gói App → DB cần route phù hợp trên firewall/router và **route chiều về** từ DB. Nếu firewall trạng thái nằm trên một chiều nhưng gói trả lời đi đường khác, thiết bị có thể không thấy đầy đủ phiên và loại bỏ gói; đây là một vấn đề của **asymmetric routing**.

Trong môi trường có nhiều router, cũng cần kiểm tra liệu một route cụ thể hơn có khiến lưu lượng đi tắt, bỏ qua firewall hoặc IDS/IPS dự kiến hay không. Để đánh giá rủi ro, hãy vẽ rõ **nguồn → interface → next hop → subnet đích → đường trả lời** thay vì chỉ nhìn sơ đồ logic các vùng.

## 8. Routing table trong VPN và mạng đám mây

### VPN: split tunnel và full tunnel

Khi VPN được kết nối, hệ điều hành có thể tạo **interface tunnel** như tun0/wg0 và bổ sung route. Ví dụ:

~~~text
10.10.10.0/24      dev eth0
172.16.0.0/16      dev wg0
default            via 10.10.10.1 dev eth0
~~~

Trong cấu hình minh họa này, địa chỉ **172.16.4.20** được định tuyến qua VPN, còn các đích khác khớp default sẽ qua eth0. Đây là nguyên tắc của **split tunneling**: chỉ một số mạng được định tuyến qua tunnel.

Với **full tunneling**, VPN thường đưa phần lớn hoặc toàn bộ lưu lượng cần bảo vệ qua tunnel bằng route mặc định hoặc các route bao phủ dải rộng, đôi khi kèm ngoại lệ để vẫn tiếp cận được endpoint VPN. Cách triển khai cụ thể phụ thuộc hệ điều hành và phần mềm.

Ba vấn đề bảo mật thường gặp:

- **Trùng subnet:** mạng tại nhà và mạng doanh nghiệp cùng dùng 192.168.1.0/24, khiến route on-link hoặc route cụ thể hơn đưa lưu lượng đến sai nơi.
- **Rò rỉ lưu lượng/DNS:** route DNS resolver hoặc lưu lượng IPv6 không đi qua VPN theo thiết kế, gây lệch chính sách quan sát và kiểm soát.
- **Đường đi và quyền truy cập:** route vào tunnel chỉ nói gói có thể chọn tunnel; ACL, danh tính người dùng, xác thực máy và policy phía VPN vẫn phải quyết định khả năng truy cập.

Không thể đánh giá an toàn VPN chỉ bằng việc có địa chỉ IP tunnel. Hãy xem **route tới từng đích cụ thể**, rule định tuyến, DNS và firewall hai phía.

### Cloud: route table là một phần của chính sách mạng

Trong các môi trường VPC/VNet, có thể có route table cho subnet, gateway ra Internet/NAT, mạng kết nối qua VPN hoặc private link và một số route định tuyến nội bộ. Tuy nhiên, cách gắn route table, thứ tự ưu tiên, loại next hop và khả năng chuyển tiếp **phụ thuộc nhà cung cấp**.

Ví dụ hệ thống cloud có mạng:

~~~text
10.50.0.0/16      local
10.60.0.0/16      virtual-network-gateway
0.0.0.0/0         egress-firewall
~~~

Đây là **sơ đồ logic**, không phải cú pháp route table của một nhà cung cấp cụ thể. Mục tiêu là hiểu ý nghĩa: lưu lượng nội bộ ở lại mạng ảo, lưu lượng tới chi nhánh đi qua gateway riêng, phần còn lại đi qua firewall đầu ra.

Khi kiểm tra một đường đi cloud, cần đối chiếu route table **với** security group, network ACL, firewall trên VM, gateway, peering/transit và quy tắc NAT. Một route cho phép chuyển tiếp tới gateway không chứng minh gateway có thể định tuyến hoặc lọc đúng ở chặng sau.

## 9. IPv6 routing table

IPv6 dùng cùng các khái niệm **destination prefix, next hop, interface, default route** và **longest-prefix match**, nhưng địa chỉ và cơ chế tìm neighbor khác IPv4.

Ví dụ máy có địa chỉ **2001:db8:10::25/64**:

~~~text
2001:db8:10::/64 dev eth0
default via fe80::1 dev eth0
~~~

- **2001:db8:10::/64** là subnet IPv6 cục bộ.
- **::/0** là default route IPv6.
- **fe80::1** là địa chỉ link-local của gateway; link-local chỉ có ý nghĩa trên một liên kết nên **dev eth0** là thông tin cần thiết để xác định phạm vi.
- IPv6 dùng **Neighbor Discovery (ND)** dựa trên ICMPv6 thay vì ARP để tìm neighbor, và router có thể công bố prefix/default router bằng Router Advertisement.

Dải **2001:db8::/32** trong ví dụ được dành cho tài liệu. Đừng chặn toàn bộ ICMPv6: Neighbor Discovery và một số thông báo lỗi thiết yếu sẽ bị ảnh hưởng. Trong mạng **dual-stack**, kiểm tra riêng hai bảng route vì IPv4 và IPv6 có thể sử dụng hai đường ra khác nhau.

### Route và an ninh IPv6

Rogue Router Advertisement có thể làm host học một default router ngoài dự kiến; thiếu chính sách IPv6 có thể tạo đường đi vượt qua kiểm soát chỉ áp dụng với IPv4. Các biện pháp như RA Guard, quản lý quyền cấu hình router và giám sát route/RA nên được cân nhắc dựa trên thiết bị và topology thực tế.

## 10. Các lỗi thường gặp khi đọc hoặc cấu hình route

| Hiện tượng | Nguyên nhân định tuyến có thể có | Cần kiểm tra |
| --- | --- | --- |
| Truy cập được cùng subnet nhưng không ra mạng khác | Không có default route, gateway sai hoặc gateway không forward | ip route, địa chỉ gateway, chính sách router |
| Một subnet cụ thể không truy cập được | Route cụ thể hơn trỏ sai interface/next hop | ip route get đến một IP của subnet lỗi |
| Kết nối từ A tới B đi được nhưng không nhận phản hồi | B không có route về hoặc firewall/state làm rơi gói | Route hai đầu, policy, log và trace |
| Chỉ lỗi khi bật VPN | Route VPN chồng lấn, split tunnel, DNS/IPv6 không đi cùng tuyến | Route trước/sau VPN, policy rules, DNS |
| Mạng thỉnh thoảng gián đoạn | Đường truyền không ổn định, ECMP/policy, thay đổi route động | Metric, trạng thái next hop, lịch sử route và log |
| Route tồn tại nhưng TCP kết nối thất bại | Firewall, NAT, MTU/PMTUD, dịch vụ, TLS hoặc xác thực | Log nhiều lớp, trace, TCP handshake |
| Gói đi qua đường không được giám sát | Route cụ thể hơn hoặc chính sách nguồn đưa luồng đi nhánh khác | Bảng route/rule theo cả hai chiều và vị trí sensor |

### Quy trình xử lý sự cố theo thứ tự

1. **Xác định đúng luồng:** địa chỉ nguồn, đích, giao thức, cổng, thời gian và vị trí máy. Nếu nhập tên miền, xác minh DNS đã trả về IP nào.
2. **Kiểm tra interface:** IP/prefix, trạng thái, VLAN/Wi-Fi/tunnel. Không nên dựa riêng vào chữ **UP** để kết luận có kết nối đầu cuối.
3. **Hỏi hệ điều hành chọn đường nào:** dùng **ip route get** với IP đích và xem route table, rule nếu kết quả khác dự kiến.
4. **Kiểm tra next hop:** gateway có thể tiếp cận trên liên kết không? ARP/ND đã có neighbor chưa? Nếu là VPN, tunnel có hoạt động không?
5. **Theo dõi từng chặng:** xem router/firewall logs, route cụ thể hơn ở các router trung gian, NAT, trạng thái interface và chính sách.
6. **Xác minh đường về:** route và firewall phía đích cho gói phản hồi có phù hợp không, có đường đi bất đối xứng qua stateful firewall không?
7. **Kiểm tra lớp ứng dụng:** dù routing đúng, một dịch vụ không lắng nghe hoặc bị từ chối xác thực vẫn không hoạt động.

Có thể dùng **ping**, **traceroute** hoặc **tracepath** trong phạm vi được cấp phép để có thêm tín hiệu, nhưng ICMP bị lọc hoặc thiết bị không phản hồi TTL hết hạn có thể làm kết quả thiếu chặng. **tcpdump/Wireshark** và flow logs giúp quan sát, song chỉ thấy lưu lượng tại điểm bắt được dữ liệu.

## 11. Tình huống tổng hợp

Máy trạm có IP **192.168.10.20/24** với bảng định tuyến:

~~~text
192.168.10.0/24    dev eth0
172.16.0.0/16      via 192.168.10.254 dev eth0
172.16.20.0/24     via 192.168.10.1   dev eth0
default            via 192.168.10.1   dev eth0
~~~

Giả sử **192.168.10.1** và **192.168.10.254** đều có thể tiếp cận trên eth0, không có policy routing khác:

| Đích | Đường đi máy trạm chọn | Lý do |
| --- | --- | --- |
| 192.168.10.50 | eth0 trực tiếp | Connected route /24 |
| 172.16.20.8 | Gateway 192.168.10.1 | Route 172.16.20.0/24 cụ thể hơn /16 |
| 172.16.30.8 | Gateway 192.168.10.254 | Khớp route 172.16.0.0/16 |
| 203.0.113.8 | Gateway 192.168.10.1 | Dùng default route |

Giờ giả sử **172.16.20.8** là database nội bộ, chỉ ứng dụng được phép truy cập. Việc route chọn **192.168.10.1** chỉ chứng minh đó là **chặng kế tiếp** trong tra cứu; chính sách trên firewall, ACL hoặc database có thể tiếp tục từ chối máy trạm. Cũng cần xác nhận database biết đường trả lời về **192.168.10.20**.

Đây là cách đọc routing table trong một kiến trúc mạng an toàn: trước hết trả lời **“gói đi đâu?”**, sau đó kiểm tra **“gói có được đi qua đó không?”**, và cuối cùng xác minh **“gói phản hồi có quay về đúng đường và được chấp nhận không?”**.
