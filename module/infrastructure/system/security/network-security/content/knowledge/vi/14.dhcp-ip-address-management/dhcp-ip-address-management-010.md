# IPv6 address management: quản lý địa chỉ, prefix và danh tính thiết bị

**IPv6 address management** là quá trình quy hoạch, cấp phát, ghi nhận, giám sát và thu hồi địa chỉ IPv6 cùng các **network prefix** trong suốt vòng đời hệ thống. So với IPv4, IPv6 không đơn giản chỉ là địa chỉ dài hơn: một interface có thể đồng thời sở hữu **link-local address, global unicast address, địa chỉ ULA, địa chỉ tạm thời**, và các địa chỉ ấy có thể được tạo theo nhiều cơ chế khác nhau.

Vì vậy, khi một quản trị viên hỏi “thiết bị nào đang dùng địa chỉ này?”, câu trả lời không nhất thiết nằm trong **DHCP lease table**. Thiết bị có thể tự tạo địa chỉ bằng **Stateless Address Autoconfiguration (SLAAC)**; hệ điều hành có thể dùng nhiều địa chỉ nguồn theo thời gian; hoặc một router được **DHCPv6 Prefix Delegation** cấp nguyên một prefix để phân phối tiếp xuống mạng con.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, quản lý địa chỉ IPv6 gắn trực tiếp với phân đoạn mạng, firewall, NAC, VPN, bảo vệ DNS, IDS/IPS và cloud networking. Một thiết kế tốt phải bảo đảm ba mục tiêu đồng thời: **đủ địa chỉ và định tuyến ổn định; chính sách truy cập đúng vùng; khả năng liên hệ địa chỉ với tài sản, người dùng và sự kiện bảo mật khi cần**.

> **Phạm vi:** Bài sử dụng các prefix dành cho tài liệu và mạng nội bộ giả định, không phải thông tin một hệ thống đang vận hành. Các lệnh kiểm tra chỉ được dùng trên thiết bị/lab có quyền quản trị. IPv6 có nhiều lựa chọn triển khai; không áp dụng một công thức DHCPv6/SLAAC duy nhất cho mọi hệ điều hành, thiết bị và nền tảng cloud.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **link-local, global unicast, unique local, multicast và địa chỉ IPv6 tạm thời** theo phạm vi sử dụng.
2. Thiết kế cây cấp phát **/48 → /56 → /64** cho tổ chức, chi nhánh và VLAN mà không nhầm ranh giới prefix.
3. Giải thích **Router Solicitation (RS), Router Advertisement (RA), SLAAC, Duplicate Address Detection (DAD)** và trạng thái vòng đời địa chỉ.
4. So sánh **SLAAC, DHCPv6 stateful, DHCPv6 stateless, DHCPv6 Prefix Delegation (PD)** và cấu hình tĩnh.
5. Xây dựng mô hình **IP Address Management (IPAM)** kết hợp DNS, DHCPv6, switch, NAC, router và endpoint telemetry.
6. Nhận diện nguy cơ **rogue RA, rogue DHCPv6, Neighbor Discovery spoofing, thay đổi prefix và chính sách IPv6 bị bỏ quên**.
7. Kiểm thử từ phía client, gateway và hệ thống giám sát để xác minh **kết nối, phân giải DNS, cấp phát và quy trách nhiệm**.

## 2. Những loại địa chỉ IPv6 cần biết

IPv6 dùng địa chỉ **128 bit**, thường viết bằng tám nhóm hexa 16 bit phân cách bằng dấu hai chấm. Có thể rút gọn các nhóm 0 theo quy tắc chuẩn, nhưng không được tùy ý thay đổi giá trị prefix.

| Loại địa chỉ | Prefix hoặc cách nhận diện | Vai trò và lưu ý |
|---|---|---|
| **Link-local unicast** | Trong **fe80::/10**; phổ biến dùng prefix **fe80::/64** trên interface | Liên lạc trong một link, dùng cho Neighbor Discovery và next-hop; không định tuyến qua các router |
| **Global Unicast Address (GUA)** | Phần lớn cấp phát Internet hiện nay nằm trong **2000::/3** | Dùng cho mạng được định tuyến theo chính sách; có GUA không đồng nghĩa được firewall cho truy cập Internet |
| **Unique Local Address (ULA)** | **fc00::/7**, trong thực tế triển khai thường dùng nhánh **fd00::/8** với Global ID tự tạo theo quy tắc phù hợp | Dùng cho mạng nội bộ; không dành cho định tuyến công khai trên Internet |
| **Multicast** | **ff00::/8** | Trao đổi một tới nhiều, bao gồm nhóm được ND và DHCPv6 dùng; IPv6 không dùng broadcast như IPv4 |
| **Loopback** | **::1/128** | Giao tiếp với chính host |
| **Unspecified** | **::/128** | Chỉ trạng thái chưa xác định địa chỉ trong những ngữ cảnh phù hợp; không phải địa chỉ cấp cho thiết bị |
| **Documentation** | **2001:db8::/32** | Dùng trong ví dụ, sơ đồ và tài liệu; không dùng như prefix Internet vận hành |

**Không nên dùng “địa chỉ public” làm đồng nghĩa với “Internet có thể kết nối đến”.** GUA có thể là địa chỉ định tuyến được trong hệ thống, nhưng **firewall, security group, ACL, route, NAT64/proxy hoặc chính sách ứng dụng** vẫn quyết định khả năng truy cập.

### Interface có thể sở hữu nhiều địa chỉ

~~~text
Laptop (một interface Wi-Fi)
    |
    +-- fe80::...                   Link-local
    |
    +-- 2001:db8:1200:100a::...    GUA ổn định trong prefix lab
    |
    +-- 2001:db8:1200:100a::...    GUA tạm thời khác
    |
    +-- fd12:3456:789a:10::...     ULA nếu mạng công bố prefix ULA
~~~

Các địa chỉ có thể cùng tồn tại và có **preferred lifetime**, **valid lifetime** khác nhau. Một địa chỉ có thể còn hợp lệ cho kết nối cũ nhưng không còn được ưu tiên tạo kết nối mới. Vì vậy, hệ thống IPAM cần mô hình hóa quan hệ **một tài sản – nhiều địa chỉ – nhiều thời điểm**, không cố gán một máy với đúng một IPv6 vĩnh viễn.

## 3. Quy hoạch prefix: quản lý mạng thay vì đếm từng địa chỉ

Trong IPv6, đơn vị cần quản lý trước tiên thường là **prefix** chứ không phải từng địa chỉ host. Điều này giúp tách các vùng, cấp quyền định tuyến, lập bảng firewall, cấp phát cho chi nhánh và tự động hóa.

Một mô hình hay gặp:

~~~text
Tổ chức:       2001:db8:1200::/48
                   |
         +---------+---------+
         |                   |
Site A:  2001:db8:1200:1000::/56
Site B:  2001:db8:1200:2000::/56
         |
         +-- 2001:db8:1200:100a::/64   Employee VLAN
         +-- 2001:db8:1200:1014::/64   Server VLAN
         +-- 2001:db8:1200:1032::/64   Guest VLAN
~~~

**Các địa chỉ 2001:db8 ở trên chỉ dùng cho ví dụ.** Trong mạng thực, prefix GUA phải đến từ nguồn cấp phát hợp lệ (nhà cung cấp, RIR theo điều kiện, cloud provider...) và được định tuyến tương ứng.

### Vì sao /64 thường là đơn vị mạng host?

SLAAC truyền thống cho địa chỉ unicast thường dùng prefix **/64** để host tạo Interface Identifier (IID) 64 bit. Rút subnet thành **/80, /112 hoặc /120** tùy tiện rồi kỳ vọng mọi hệ điều hành vẫn SLAAC bình thường là lỗi thiết kế thường gặp.

Một số trường hợp chuyên biệt có quy ước riêng, ví dụ **/127 trên liên kết router-to-router** theo các hướng dẫn kỹ thuật tương ứng. Đó **không phải mẫu mặc định** cho LAN có host SLAAC.

### Kiểm tra ranh giới bit: /48, /56, /64

| Mức | Prefix mẫu | Phần nào đã cố định? | Cách dùng minh họa |
|---|---|---|---|
| Tổ chức | **2001:db8:1200::/48** | Ba hextet đầu | Phân bổ toàn bộ không gian site |
| Site A | **2001:db8:1200:1000::/56** | Ba hextet đầu + 8 bit cao của hextet thứ tư | Site A chứa các /64 có hextet thứ tư từ **1000 đến 10ff** |
| VLAN Employee | **2001:db8:1200:100a::/64** | Bốn hextet đầu | Prefix mạng host |
| VLAN Server | **2001:db8:1200:1014::/64** | Bốn hextet đầu | Prefix mạng host khác |
| Site B | **2001:db8:1200:2000::/56** | Ba hextet đầu + 8 bit cao khác của hextet thứ tư | Site B không trùng Site A |

Một **/48** có **65.536 prefix /64** về mặt toán học; mỗi **/56** có **256 prefix /64**. Đây là sức chứa phân đoạn lý thuyết, không có nghĩa mọi đơn vị đều cần dùng hết. Cách cấp phát thực tế phải dự trù **site, môi trường dev/test/prod, mạng khách, mạng IoT, DMZ, quản trị và tăng trưởng**.

**Không tự suy diễn prefix từ VLAN ID:** Có thể chọn cách ánh xạ dễ nhớ, nhưng VLAN là khái niệm Layer 2 còn prefix IPv6 là Layer 3. Bảng quy hoạch phải là **nguồn sự thật** khi tạo route, RA, firewall và DNS.

## 4. Các cơ chế cấu hình địa chỉ và phân phối prefix

| Cơ chế | Ai cấp hoặc tạo địa chỉ? | Vai trò của RA | Khi nào dùng? |
|---|---|---|---|
| **SLAAC** | Host tự sinh địa chỉ từ prefix được quảng bá trên link | Cần RA có Prefix Information Option phù hợp và cho phép tự cấu hình | LAN người dùng, mạng thiết bị hỗ trợ SLAAC |
| **DHCPv6 stateful** | DHCPv6 server cấp địa chỉ theo yêu cầu và trạng thái lease | RA thường vẫn cung cấp thông tin default router/khả năng on-link | Mạng muốn quản lý cấp phát qua server, nếu client hỗ trợ |
| **DHCPv6 stateless** | Địa chỉ thường từ SLAAC, DHCPv6 chỉ trả thông tin bổ trợ (như DNS) | RA và cờ điều khiển có thể báo host dùng dịch vụ bổ trợ | Mạng SLAAC cần cấu hình bổ sung |
| **Static / cấu hình quản lý** | Quản trị viên hoặc automation đặt địa chỉ/prefix | Có thể nhận default route từ RA hoặc cấu hình riêng | Gateway, appliance, dịch vụ hạ tầng cần định danh ổn định |
| **DHCPv6 Prefix Delegation** | Server ủy quyền một **prefix** cho router/client yêu cầu | Router nhận prefix có thể tự quảng bá các /64 xuống LAN riêng | CPE, nhánh văn phòng, router phân phối xuống mạng con |

**Không phải mọi hệ điều hành hỗ trợ DHCPv6 stateful như nhau.** Ví dụ, một số nhóm thiết bị di động ưu tiên SLAAC và không nhận địa chỉ qua DHCPv6 stateful. Khi thiết kế Wi-Fi/BYOD, nên kiểm tra tập thiết bị thật thay vì cho rằng bật cờ M trong RA sẽ bắt tất cả host dùng DHCPv6.

### Các khái niệm dễ bị nhầm

- **DHCPv6 không cấp default gateway như DHCPv4 Option 3.** Thông tin router mặc định thường đến từ **IPv6 Router Advertisement (RA)** hoặc cấu hình khác.
- **SLAAC không đồng nghĩa không có DNS.** Một host có thể nhận resolver qua **RA RDNSS (RFC 8106)** hoặc cơ chế khác tùy OS.
- **DHCPv6 stateless không đồng nghĩa “không có lưu lượng DHCP”.** Nó vẫn sử dụng giao thức DHCPv6, nhưng không cần server duy trì lease cho địa chỉ tự tạo của host.
- **DHCPv6 stateful cũng không tự xác thực người dùng.** Lease hoặc DUID chỉ là dữ liệu vận hành, không thay thế NAC/802.1X, IAM hay chứng thực thiết bị.

## 5. SLAAC và Router Advertisement hoạt động như thế nào?

IPv6 Neighbor Discovery (ND) dùng các thông điệp **ICMPv6**. Host có thể nghe RA định kỳ hoặc chủ động gửi **Router Solicitation (RS)** để nhận thông tin cấu hình sớm hơn.

~~~text
Host                         Router trong VLAN
 |                                  |
 | --- Router Solicitation (133) -->|
 |                                  |
 |<-- Router Advertisement (134) ---|
 |    Prefix 2001:db8:1200:100a::/64
 |    Default router lifetime
 |    Các cờ A/L, M/O tùy thiết kế
 |    DNS RDNSS/DNSSL nếu hỗ trợ
 |                                  |
 | Tạo địa chỉ IID phù hợp           |
 |                                  |
 | -- Neighbor Solicitation (135) ->|  DAD/ND trong phạm vi link
 |<-- Neighbor Advertisement (136) -|  Có thể xảy ra khi đã có địa chỉ
 |                                  |
 | Hoàn tất kiểm tra địa chỉ         |
 | Lựa chọn địa chỉ và default route |
~~~

Sơ đồ chỉ mô tả luồng khái niệm; trong DAD, host phát Neighbor Solicitation cho địa chỉ dự định sử dụng để kiểm tra trùng lặp và **không nhất thiết có Neighbor Advertisement phản hồi**. Nếu không có phản hồi hoặc tín hiệu xung đột theo quy trình phù hợp, địa chỉ có thể được đưa vào sử dụng.

### Các thông tin trong RA cần kiểm tra

| Thành phần | Ý nghĩa |
|---|---|
| **Router Lifetime** | Cho biết router quảng bá có thể được dùng làm default router trong bao lâu |
| **Prefix Information Option (PIO)** | Prefix và các thuộc tính cho host |
| **A flag trong PIO** | Cho biết prefix có thể sử dụng cho SLAAC theo quy tắc hỗ trợ |
| **L flag trong PIO** | Gợi ý prefix được xem là on-link; không đồng nghĩa firewall mở quyền |
| **M flag trong RA** | Gợi ý sử dụng DHCPv6 để lấy địa chỉ stateful khi host hỗ trợ |
| **O flag trong RA** | Gợi ý dùng DHCPv6 để lấy các thông tin cấu hình khác |
| **RDNSS/DNSSL** | Thông tin DNS resolver và search domain qua RA nếu thiết bị hỗ trợ |
| **Preferred/Valid Lifetime** | Quản lý thời gian ưu tiên và thời gian địa chỉ còn hiệu lực |

**M và O không phải “lệnh bắt buộc” tuyệt đối cho mọi hệ điều hành.** Hành vi chọn SLAAC, DHCPv6, DNS và giữ địa chỉ phụ thuộc nền tảng và cấu hình client. Một host cũng có thể có nhiều địa chỉ đến từ cơ chế khác nhau.

### Default route không phải DNS server

Một máy có thể nhận **IPv6 GUA hợp lệ nhưng không có default route** nếu RA bị chặn hoặc router lifetime không phù hợp. Ngược lại, có thể có default route nhưng **không phân giải được tên** vì RDNSS/DHCPv6 DNS sai hoặc resolver không truy cập được. Đây là hai sự cố khác nhau, phải kiểm tra riêng.

## 6. DAD, Neighbor Discovery và vòng đời địa chỉ

**Duplicate Address Detection (DAD)** giúp host phát hiện xung đột trước khi sử dụng một địa chỉ unicast theo ngữ cảnh phù hợp. ND còn hỗ trợ tìm địa chỉ liên kết Layer 2 của neighbor, phát hiện neighbor không còn tới được và các chức năng IPv6 khác.

### Địa chỉ tentative, preferred và deprecated

| Trạng thái/khái niệm | Ý nghĩa thực tế |
|---|---|
| **Tentative** | Địa chỉ đang trải qua DAD hoặc chưa được phép dùng như địa chỉ thông thường |
| **Preferred** | Địa chỉ có thể được ưu tiên để tạo kết nối mới tùy thuật toán chọn nguồn |
| **Deprecated** | Địa chỉ không còn được ưu tiên cho kết nối mới, nhưng có thể còn hợp lệ cho kết nối đã tồn tại |
| **Valid lifetime** | Thời gian địa chỉ còn được xem là hợp lệ; hết hạn thì phải ngừng sử dụng theo quy tắc |
| **Temporary address** | Địa chỉ được tạo với cơ chế riêng tư, có vòng đời riêng so với địa chỉ ổn định |

RA thay đổi **Preferred Lifetime** hoặc **Valid Lifetime** có thể ảnh hưởng nhiều host cùng lúc. Đặc biệt trong **renumbering**, không thể giả định giảm ngay valid lifetime trong RA là mọi host sẽ xóa địa chỉ tức thì: chuẩn SLAAC có các quy tắc xử lý lifetime nhằm hạn chế hành vi RA giả mạo rút ngắn thời gian. Cần kiểm thử hệ điều hành thật và lên kế hoạch thời gian chuyển đổi.

### Những điều ND không bảo đảm

- ND/RA mặc định không phải chứng cứ **xác thực nguồn đáng tin** nếu không có các kiểm soát bổ sung.
- Neighbor cache chỉ phản ánh **quan sát tạm thời**, không phải danh sách tài sản đầy đủ.
- Một địa chỉ GUA có thể biến mất khỏi interface hoặc đổi theo thời gian mà không có DHCP lease.
- DAD không tự thay thế **định danh thiết bị, NAC hoặc bảo vệ chống giả mạo**.

## 7. DHCPv6 stateful: địa chỉ, lease và DUID

**DHCPv6** có thể cấp địa chỉ và thông tin cấu hình cho những client hỗ trợ. Nó thường dùng **UDP cổng 546 ở client** và **UDP cổng 547 ở server/relay**. Khác DHCPv4, giao thức dùng **multicast phù hợp**, không dựa trên broadcast IPv4.

Một luồng stateful DHCPv6 thường gặp:

~~~text
DHCPv6 Client               Relay (nếu có)              DHCPv6 Server
      |                            |                           |
      |  SOLICIT ----------------->|-------------------------->|
      |<--------------------------|<----------------- ADVERTISE|
      |  REQUEST ---------------->|-------------------------->|
      |<--------------------------|<-------------------- REPLY|
      |                            |                           |
      |  RENEW / REBIND theo thời hạn và điều kiện              |
      |                            |                           |
~~~

Cơ chế **Rapid Commit** có thể rút ngắn một số trao đổi khi cả client/server hỗ trợ và cấu hình cho phép. Vì thế không nên tuyên bố mọi phiên DHCPv6 đều có đúng bốn bản tin.

### Các định danh quan trọng

- **DUID (DHCP Unique Identifier):** định danh client/server theo thiết kế DHCPv6. DUID không nhất thiết bằng MAC và có thể thay đổi khi hệ điều hành hoặc cấu hình được cài lại.
- **IA_NA:** Identity Association for Non-temporary Addresses, thường liên quan tới địa chỉ cấp qua DHCPv6 stateful.
- **IA_PD:** Identity Association for Prefix Delegation, dùng khi router/client xin cấp nguyên prefix.
- **Lease lifetimes:** thời hạn ưu tiên/hợp lệ của địa chỉ, cùng những mốc trao đổi renewal; cần phân biệt với lifetime từ RA.
- **Relay metadata:** hỗ trợ chuyển tiếp yêu cầu qua các mạng, có thể giúp gắn với giao diện/link khi được cấu hình.

**DUID không phải chứng thực mật mã rằng một người dùng là chủ của địa chỉ**. IPAM cần gắn với thời gian, switch port, VLAN, NAC/RADIUS, asset inventory và log endpoint để điều tra chính xác.

### DHCPv6 relay khi server nằm ngoài VLAN

Thông điệp multicast DHCPv6 liên kết cục bộ không tự đi qua router như một kết nối unicast bất kỳ. Trong kiến trúc server tập trung, cần một **DHCPv6 relay** thích hợp tại router/gateway hoặc thiết bị hỗ trợ, cấu hình tuyến và firewall tương ứng. Nếu relay sai, client vẫn có thể nhận RA/SLAAC bình thường nhưng **không nhận được thông tin DHCPv6**, dễ khiến sự cố bị chẩn đoán nhầm là lỗi routing chung.

## 8. DHCPv6 Prefix Delegation (PD): cấp phát cho router, không chỉ host

DHCPv6 PD dùng khi một router cần nhận một **prefix được ủy quyền** để phục vụ các mạng ở phía sau. Trường hợp thường gặp là router tại chi nhánh, thiết bị CPE hoặc một gateway phân phối tiếp các /64 cho LAN.

~~~text
            [Upstream / DHCPv6 PD Server]
                         |
                  Delegates /56
                  2001:db8:1200:1000::/56
                         |
                 [Branch Router]
                         |
          +--------------+---------------+
          |                              |
      Employee LAN                  IoT LAN
  2001:db8:1200:100a::/64    2001:db8:1200:101e::/64
          |                              |
         RA                             RA
          |                              |
       IPv6 hosts                    IPv6 devices
~~~

**Prefix Delegation là cấp quyền sử dụng một khối địa chỉ cho router; không tự tạo firewall rules hoặc chính sách phân đoạn.** Khi router nhận prefix khác do đổi ISP, lease hết hạn hoặc thay đổi hạ tầng, những LAN phía sau phải được **renumber**, cập nhật RA, route, DNS và chính sách mạng. Thiết kế không nên gắn cứng toàn bộ quyền truy cập vào một prefix động mà không có cơ chế đồng bộ.

### Phân biệt prefix WAN và prefix delegated

Router có thể có một địa chỉ IPv6 trên uplink WAN và một prefix PD dành cho các LAN bên trong; đó là **hai đối tượng khác nhau**. Có địa chỉ WAN không đảm bảo router đã được cấp PD, và có PD không đồng nghĩa mọi LAN đã nhận RA hoặc route đúng.

**IPAM phải lưu được quan hệ “prefix được cấp → router sở hữu → subnet phía sau → thời hạn cấp phát → trạng thái triển khai”.**

## 9. Stable address, privacy extension và khả năng quy trách nhiệm

Trong IPv6, một interface có thể tạo IID bằng nhiều cách. Không nên mặc định **IID luôn được suy từ MAC theo EUI-64**. Nhiều hệ điều hành hiện đại dùng cơ chế tạo địa chỉ ổn định nhưng không phơi bày MAC, đồng thời có thể tạo địa chỉ tạm.

| Cơ chế | Mục tiêu | Hệ quả đối với IPAM |
|---|---|---|
| **Địa chỉ cấu hình tĩnh** | Tên và endpoint dễ dự đoán cho server/hạ tầng | Cần quản trị trùng lặp, route, DNS và thay đổi thủ công/tự động |
| **DHCPv6 address lease** | Server ghi lịch sử cấp phát nếu client hỗ trợ | Có lease nhưng cần đối chiếu DUID với tài sản, thời gian và danh tính thật |
| **Stable SLAAC IID (ví dụ RFC 7217)** | Ổn định trong một ngữ cảnh prefix/interface mà không bắt buộc lộ MAC | Không nhất thiết có lease; prefix thay đổi có thể làm địa chỉ thay đổi |
| **Temporary/privacy address (ví dụ RFC 8981)** | Giảm liên kết hoạt động mạng qua các lần kết nối | Một thiết bị có nhiều địa chỉ, thay đổi theo thời gian, cần telemetry theo phiên |

### Nên ghi lại những gì?

Trong mạng người dùng, nên ưu tiên **định danh tài sản và ngữ cảnh kết nối**, sau đó mới liên hệ với các địa chỉ IPv6:

~~~text
Asset ID / Owner / Device identity
             |
    NAC session / 802.1X / Wi-Fi AP / switch port
             |
         VLAN / prefix
             |
   Observed IPv6 address(es)
             |
   First seen / last seen / flow session
~~~

**Không xây toàn bộ nhận diện thiết bị chỉ từ một địa chỉ IPv6.** Address privacy, DHCPv6 DUID, VM/container lifecycle và cấu hình VPN có thể làm địa chỉ xuất hiện/biến mất nhanh. Khi truy vết một sự cố, phải biết **địa chỉ đó thuộc tài sản nào vào thời điểm cụ thể**, không chỉ chủ sở hữu hiện tại của prefix.

## 10. IPAM: nguồn sự thật cho prefix và tài sản

**IP Address Management (IPAM)** là tập hợp quy trình và hệ thống quản lý không gian địa chỉ, phân quyền cấp phát, hiện trạng sử dụng và mối quan hệ với DNS/DHCP. Với IPv6, IPAM không thể chỉ là một spreadsheet liệt kê địa chỉ server.

### Mô hình dữ liệu nên có

| Thực thể | Trường thông tin hữu ích |
|---|---|
| **Address block / prefix** | IPv6 prefix, prefix length, cấp cha, tình trạng, nguồn cấp phát, owner, khu vực |
| **Site / security zone** | Site, VLAN/VRF, subnet, mục đích, mức tin cậy và chính sách |
| **Gateway / RA config** | Interface, prefix advertised, A/L/M/O, router lifetime, RDNSS và nguồn thay đổi |
| **DHCPv6 scope / pool** | Pool, server/relay, DUID/IA_NA, cấp phát PD, lease và lịch sử |
| **Address observation** | IPv6, hostname/asset, interface, nguồn bằng chứng, first/last seen |
| **DNS association** | Tên AAAA/PTR phù hợp, quản trị zone, người phê duyệt, TTL |
| **Routing/security policy** | Route, VRF, firewall zone, ACL, chủ quản lý và ID thay đổi |
| **Lifecycle** | Reserved, assigned, deprecated, released, quarantined, pending validation |

Một hệ thống IPAM thường kết hợp dữ liệu **đã quy hoạch (desired state)** với dữ liệu **đã quan sát (observed state)**. Hai loại không luôn trùng nhau:

- Desired: “VLAN Employee tại Site A dùng prefix 2001:db8:1200:100a::/64.”
- Observed: “Một host vẫn có địa chỉ trong prefix cũ sau khi đổi RA.”
- Desired: “Server cố định nhận AAAA từ hệ thống DNS nội bộ.”
- Observed: “Một máy đã đổi địa chỉ nhưng DNS vẫn trỏ đến địa chỉ cũ.”

Sự chênh lệch cần được phát hiện và giải quyết theo change management; **không tự xóa mọi địa chỉ lạ** nếu chưa biết chúng thuộc privacy address, thiết bị hợp lệ hay luồng định tuyến khác.

### Quy trình phê duyệt prefix

1. Xác định site và nhóm nhu cầu: employee, server, IoT, guest, management, DMZ, VPN.
2. Chọn prefix cha có quyền sở hữu rõ ràng.
3. Cấp phát prefix con **không trùng ranh giới bit**; giữ phần dự phòng mở rộng.
4. Gắn prefix với VRF/VLAN, gateway, RA/DHCPv6 và DNS theo mẫu cấu hình được quản lý.
5. Xem firewall policy ở cả **IPv6 và IPv4** nếu môi trường dual-stack.
6. Kiểm thử client/gateway trước khi đưa vào production.
7. Ghi phiên bản thay đổi, thời điểm, owner và phương án rollback.

## 11. Kết hợp IPAM với DNS và DHCPv6: DDI

**DDI** thường là cách gọi nhóm chức năng **DNS, DHCP và IPAM**. Các hệ thống này có liên hệ chặt nhưng không hoàn toàn đồng nhất.

| Thành phần | Dữ liệu chính | Vì sao phải đối chiếu? |
|---|---|---|
| **IPAM** | Prefix, tài sản, phạm vi cấp phát, owner và trạng thái | Đảm bảo không trùng, có phân đoạn, có lịch sử |
| **DHCPv6** | Lease địa chỉ/PD và cấu hình bổ trợ cho client dùng DHCPv6 | Không bao phủ mọi SLAAC host |
| **DNS AAAA** | Tên → IPv6 address | Có thể lỗi thời khi host đổi địa chỉ |
| **Reverse DNS PTR** | IPv6 address → tên trong vùng reverse **ip6.arpa** | Không phải chứng cứ chủ sở hữu hay định danh an toàn |
| **RA/RDNSS** | Prefix, default router, tùy chọn DNS trong link | Có thể cấp thông tin cho host không dùng DHCPv6 |

### AAAA và PTR không phải nguồn danh tính cuối cùng

Ví dụ một server lab:

~~~text
app01.lab.example.test.     AAAA     2001:db8:1200:1014::10

Reverse DNS:
  PTR dưới nhánh ip6.arpa phù hợp
  có thể trỏ về app01.lab.example.test.
~~~

**AAAA** và **PTR** dùng cho phân giải và vận hành, nhưng record có thể được cấu hình sai, stale hoặc không có. PTR không tự chứng minh máy đang giữ địa chỉ là máy được nêu trong tên. Điều tra bảo mật cần thêm **NAC, asset inventory, log hệ điều hành, kết nối và thời gian**.

### DNS động và quyền cập nhật

Nếu tổ chức dùng **Dynamic DNS update**, cần phân quyền rõ ai được tạo/sửa bản ghi, dùng kênh xác thực thích hợp và có cơ chế dọn bản ghi không còn hợp lệ. Không nên cho mọi client tùy ý sửa AAAA/PTR của tài sản khác. SLAAC temporary address cũng không nhất thiết được cập nhật vào DNS; việc ghi tất cả địa chỉ tạm có thể gây bùng nổ bản ghi và ảnh hưởng quyền riêng tư.

### RA RDNSS và DHCPv6 DNS

Một mạng có thể công bố DNS resolver qua **RA RDNSS**, **DHCPv6** hoặc cấu hình endpoint. Client có thể dùng một hay nhiều nguồn theo hệ điều hành. Khi điều tra “có IPv6 nhưng không duyệt web được”, cần tách:

1. Có IPv6 address phù hợp và không bị DAD failure không?
2. Có default route không?
3. Có DNS resolver IPv6 hoặc resolver IPv4 truy cập được không?
4. DNS server đã nhận cấu hình từ **đâu**?
5. Có firewall chặn DNS, ICMPv6 hoặc đường IPv6 tới đích không?

## 12. Bảo mật RA và Neighbor Discovery

IPv6 RA và ND chạy trong phạm vi link, vì vậy thiết bị không được tin cậy trên cùng VLAN có thể gây rủi ro nếu switch/endpoint chấp nhận thông điệp giả hoặc cấu hình sai.

### 12.1. Rogue Router Advertisement

Một thiết bị phát **RA không được phép** có thể khiến host học default route hoặc prefix không mong muốn, từ đó mất kết nối, chọn đường đi sai hoặc đưa lưu lượng qua một thiết bị không được tin cậy. Phạm vi tác động phụ thuộc VLAN, khả năng của switch, cấu hình host và các kiểm soát đã triển khai.

**Biện pháp phòng thủ:**

- **RA Guard** trên switch hỗ trợ, chỉ cho RA từ cổng kết nối router tin cậy.
- Phân chia user/guest/IoT VLAN để giảm miền ảnh hưởng và đường lateral movement.
- Xác định interface/trunk đáng tin, kiểm tra đường uplink và kết nối dự phòng.
- Giám sát nguồn RA, thay đổi router lifetime, prefix và DNS RDNSS bất thường.
- Kiểm thử tương thích RA Guard với **IPv6 extension headers/fragmentation** và phiên bản thiết bị; không giả định mọi triển khai cũ chặn mọi biến thể.

### 12.2. Rogue DHCPv6 và cấu hình DNS không tin cậy

Một DHCPv6 server trái phép có thể cung cấp thông tin cấu hình không phù hợp, ví dụ địa chỉ hoặc resolver không được quản lý, nếu client chấp nhận. **DHCPv6 Guard/Snooping** trên switch hoặc giải pháp tương đương giúp giới hạn cổng có quyền trả lời DHCPv6. Tuy nhiên, DHCPv6 **không phải nguồn default gateway chuẩn**, nên bảo vệ DHCPv6 không thay thế RA Guard.

### 12.3. ND spoofing và Neighbor cache

Neighbor Solicitation/Advertisement hỗ trợ xác định neighbor trên link. Nếu bị lạm dụng hoặc cấu hình sai, host có thể học thông tin neighbor không phù hợp. Biện pháp giảm rủi ro gồm bảo vệ switch phù hợp, phân đoạn, giám sát bất thường và thiết bị NAC/endpoint. Những giải pháp như **SEND (Secure Neighbor Discovery)** tồn tại trong tiêu chuẩn nhưng không phổ biến đồng đều trên mọi môi trường; phải kiểm chứng hỗ trợ thực tế.

### 12.4. Không chặn toàn bộ ICMPv6

ICMPv6 là phần **thiết yếu** của IPv6: RA/RS, NS/NA, Packet Too Big cho Path MTU Discovery và các thông báo lỗi cần thiết. Một firewall chặn mọi ICMPv6 có thể làm hỏng IPv6 dù TCP/UDP policy cho phép.

**Chính sách đúng là giới hạn theo loại thông điệp, phạm vi, interface và nguồn tin cậy**, đồng thời cho các luồng ICMPv6 thiết yếu hoạt động theo thiết kế. RA/ND link-local không có cùng mô hình cần cho phép xuyên router như ICMPv6 lỗi giữa các host/đường truyền.

## 13. IPv6 firewall, phân đoạn và NAC

Một tổ chức có mạng IPv4 được bảo vệ tốt vẫn có thể để quên đường IPv6 nếu router, client hoặc cloud service hỗ trợ dual-stack nhưng bộ quy tắc IPv6 chưa tương ứng.

| Nguy cơ | Ví dụ | Biện pháp |
|---|---|---|
| **IPv6 policy gap** | IPv4 chặn guest → server, IPv6 lại cho route trực tiếp | Ma trận truy cập áp dụng độc lập cho IPv6; kiểm thử dual-stack |
| **Không gắn IP với role** | Firewall chỉ biết GUA, thiếu thông tin user/thiết bị | Tương quan NAC/RADIUS/802.1X, VLAN, EDR và IPAM |
| **Địa chỉ nguồn đổi** | Privacy address đổi trong khi một rule cố định theo /128 | Ưu tiên chính sách theo zone/role/identity; đánh giá quy tắc theo prefix |
| **Luồng east–west** | Hai máy cùng VLAN giao tiếp không qua firewall biên | Host firewall, microsegmentation hoặc kiểm soát nội bộ |
| **Mạng khách/IoT** | Thiết bị có IPv6 tự cấu hình nhưng truy cập được tài sản nội bộ | Tách zone, kiểm soát RA, DNS và quyền kết nối |
| **VPN dual-stack** | VPN giới hạn IPv4 nhưng IPv6 ra ngoài trực tiếp | Xác minh route, DNS, split tunnel và firewall trên thiết bị |

**IPv6 không cần NAT để trở nên an toàn.** Firewall stateful có thể áp chính sách **deny unsolicited inbound**, chỉ cho phép những kết nối mới cần thiết và xử lý phản hồi theo state. Không có NAT không đồng nghĩa host phải chấp nhận mọi kết nối đến. Ngược lại, NAT cũng không thay thế xác thực hoặc phân quyền ứng dụng.

## 14. IPv6 trong cloud, container và hạ tầng ảo

Nhiều nhà cung cấp cloud cho phép gắn IPv6 prefix/address vào VPC/VNet, subnet, NIC, load balancer hoặc workload; khả năng SLAAC/DHCPv6, phân phối route và DNS **không nhất thiết giống mạng Ethernet vật lý**.

### Những điểm cần quản lý

- **Nguồn prefix:** được cloud provider cấp, được đưa vào theo phương án được hỗ trợ, hay do tổ chức quản lý?
- **Subnet boundary:** kích thước prefix và ràng buộc cụ thể của nền tảng; không áp máy móc mô hình campus LAN.
- **Route table:** IPv6 default route, peering/transit, VPN và kết nối nội bộ có thể khác IPv4.
- **Security group/NSG/NACL:** phải có rule phù hợp cho IPv6; quy tắc IPv4 không tự áp dụng cho IPv6.
- **DNS AAAA và service discovery:** quyết định dịch vụ nào công bố IPv6; kiểm thử certificate/TLS và app.
- **Egress:** kiểm soát kết nối ra ngoài và khả năng giám sát flow logs cho workload có GUA.
- **Lifecycle:** IP/address association có thể thay đổi khi VM/pod được tạo lại hoặc auto scale.

### Container/Kubernetes

Kubernetes có các cách triển khai IPv4, IPv6 hoặc dual-stack tùy phiên bản và CNI. **Pod CIDR, Service CIDR, node addressing, DNS và NetworkPolicy** cần được thiết kế đồng bộ. Không được giả định đổi cluster sang dual-stack là mọi NetworkPolicy IPv4 cũ đã bảo vệ IPv6.

IPAM trong cluster có thể thuộc **CNI hoặc nền tảng** chứ không được quản lý bằng một DHCPv6 lease table truyền thống. Khi truy vết, cần tương quan pod/namespace/node/service account với IP và **khung thời gian**, vì IP có thể nhanh chóng được cấp lại.

## 15. Giám sát và quy trách nhiệm địa chỉ IPv6

Trong một sự cố bảo mật, đội SOC có thể nhận được log:

~~~text
timestamp: 2026-11-28T10:15:00+07:00
src_ipv6:  2001:db8:1200:100a:abcd::25
dst_ipv6:  2001:db8:1200:1014::10
protocol:  tcp
dst_port:  443
action:    allow
zone:      employee-to-application
~~~

Đây là **log lab giả định**. Địa chỉ IPv6 nguồn trong log **không đủ** để xác định cá nhân hoặc tiến trình. Quy trình xác minh:

1. **IPAM:** prefix thuộc site, VLAN/VRF và policy nào?
2. **NAC/Wi-Fi/switch:** endpoint nào kết nối trong khoảng thời gian đó, tại port/AP và session nào?
3. **DHCPv6:** có lease phù hợp không? Nếu không, host có thể dùng SLAAC hoặc cấu hình khác.
4. **Neighbor cache và router logs:** có quan sát IPv6–link-layer association ở thời điểm phù hợp không? Cache có thể đã hết hạn.
5. **EDR/host:** interface và tiến trình nào sở hữu/đã dùng địa chỉ khi tạo phiên?
6. **Flow/NAT/proxy/VPN:** có đường nào thay đổi nguồn hoặc ngữ cảnh địa chỉ không?
7. **Ứng dụng/IAM:** tài khoản nào thực hiện request? Một IP không chứng minh user đã được ứng dụng xác thực.

### Mẫu dữ liệu tương quan

| Trường | Vai trò |
|---|---|
| Timestamp + timezone | Tránh ghép nhầm địa chỉ đã được tái sử dụng ở thời điểm khác |
| Prefix, VRF, VLAN, interface | Xác định ranh giới và điểm đặt policy |
| IPv6 /128 được quan sát | Địa chỉ trong sự kiện cụ thể |
| Source of observation | EDR, flow log, DHCPv6, ND cache, Wi-Fi AP hoặc router |
| Asset/device ID | Định danh máy theo hệ thống quản lý |
| NAC/RADIUS session | Bằng chứng truy cập mạng và quyền ở thời điểm sự kiện |
| Application identity | Tài khoản, service account hoặc token được xác minh ở app |
| First/last seen | Giới hạn khả năng quy thuộc một địa chỉ tạm |
| Confidence / reviewer | Mức chắc chắn và người kiểm tra |

**Lưu ý quyền riêng tư:** Không nhất thiết lưu mọi temporary IPv6 address vô thời hạn. Log cần tuân theo phân quyền, thời gian lưu, mục đích điều tra và chính sách bảo vệ dữ liệu. Địa chỉ IP cũng có thể là dữ liệu cá nhân trong những bối cảnh pháp lý nhất định.

## 16. Một thiết kế IPv6 address management có thể kiểm chứng

**Bài toán giả định:** Doanh nghiệp có Site A với nhân viên, máy chủ, khách và thiết bị IoT. Tổ chức đã được phân một khối IPv6 đủ lớn; ở đây minh họa bằng **2001:db8:1200::/48**. Mạng sử dụng SLAAC cho laptop, địa chỉ được quản lý cho server và firewall kiểm soát giữa các zone.

### 16.1. Bảng quy hoạch

| Thành phần | IPv6 prefix lab | Cơ chế | Yêu cầu bảo mật |
|---|---|---|---|
| Site A | **2001:db8:1200:1000::/56** | Cấp từ IPAM cho site | Không cấp trùng Site B |
| Employee VLAN 10 | **2001:db8:1200:100a::/64** | SLAAC + RA DNS hoặc cấu hình phù hợp | NAC/802.1X, host firewall, chỉ truy cập app được duyệt |
| Server VLAN 20 | **2001:db8:1200:1014::/64** | Static hoặc automation/IPAM | DNS AAAA ổn định, chỉ luồng cần thiết |
| Guest VLAN 50 | **2001:db8:1200:1032::/64** | SLAAC | Chặn truy cập tài sản nội bộ, Internet theo policy |
| IoT VLAN 30 | **2001:db8:1200:101e::/64** | Phù hợp khả năng thiết bị | Chỉ kết nối dịch vụ quản lý thiết bị được phê duyệt |
| Site B | **2001:db8:1200:2000::/56** | Khối khác Site A | Định tuyến và IPAM độc lập |

Các giá trị hexa **100a, 1014, 101e, 1032** đều thuộc dải /64 trong **2001:db8:1200:1000::/56**. Bảng này giúp liên kết VLAN ID với prefix một cách dễ nhớ, nhưng chỉ là **quy ước của ví dụ**.

### 16.2. Luồng truy cập mong muốn

~~~text
         [Employee VLAN 10 /64]
                    |
               [L3 gateway]
                    |
           [Stateful Firewall]
           /        |        \
      [Server]   [Guest]    [IoT]
       VLAN 20   VLAN 50   VLAN 30

 Employee -> App HTTPS/443:           ALLOW theo policy
 Employee -> DB trực tiếp:            DENY
 Guest -> các zone nội bộ:            DENY
 IoT -> hệ thống quản lý được duyệt:  ALLOW có giới hạn
 Các luồng khác:                      DENY theo chính sách
~~~

**Quan trọng:** Nếu routing trực tiếp trên L3 switch cho traffic đi giữa VLAN mà không qua firewall, các rule tại firewall sẽ không tự áp dụng cho những luồng đó. Phải xác định **điểm thực thi thực tế** bằng route, interface và kiểm thử.

### 16.3. Ma trận cấp phát và truy cập

| Test | Nguồn | Đích / hành động | Kỳ vọng |
|---|---|---|---|
| IP6-01 | Laptop Employee | Nhận RA và tạo GUA trong prefix 100a::/64 | Có địa chỉ hợp lệ và không xung đột |
| IP6-02 | Laptop Employee | Có default route và DNS resolver phù hợp | Kết nối/tra cứu tên thành công |
| IP6-03 | Host Guest | Truy cập ứng dụng nội bộ qua IPv6 | Bị chặn tại đúng policy |
| IP6-04 | Host Employee | Kết nối HTTPS tới app được phê duyệt | Cho phép; log có IPv6 và đúng zone |
| IP6-05 | Server VLAN 20 | DNS AAAA/PTR đúng với địa chỉ quản lý | Đúng DNS và inventory |
| IP6-06 | DHCPv6 PD router trong lab | Nhận prefix con và công bố /64 xuống LAN | Không chồng lấn, route chính xác |
| IP6-07 | Thiết bị không phải router | Cố gửi RA trong lab được phép | Bị kiểm soát tại cổng/zone theo policy |
| IP6-08 | Laptop có temporary IPv6 | Tạo một kết nối ra app | SOC có thể tương quan với asset và thời gian |

Test **IP6-07** chỉ thực hiện trong lab được ủy quyền với công cụ/sự kiện đã được đội quản trị phê duyệt; không tự phát RA giả trên mạng chung đang vận hành.

## 17. Thực hành quan sát an toàn trên endpoint

Mục tiêu là **đọc cấu hình IPv6**, không can thiệp cấp phát hoặc phát gói quảng bá sai chính sách.

### Trên Linux được phép quản trị

~~~bash
ip -6 addr show
ip -6 route show
ip -6 neigh show
ip -br link
~~~

Những lệnh này chủ yếu đọc trạng thái interface, route và neighbor cache. Cần chú ý **scope**, **temporary**, **dynamic**, **tentative**, **deprecated**, **valid_lft/preferred_lft** nếu công cụ/hệ điều hành hiển thị. Nếu không có thông tin RA/DHCPv6 trong output, không nên suy ngay thiết bị không dùng chúng.

### Trên Windows được phép quản trị

~~~powershell
ipconfig /all
route print -6
Get-NetIPAddress -AddressFamily IPv6
Get-NetRoute -AddressFamily IPv6
Get-DnsClientServerAddress -AddressFamily IPv6
~~~

Những lệnh PowerShell yêu cầu môi trường có module/cmdlet tương ứng. Một DNS resolver IPv4 vẫn có thể xử lý AAAA query, nên **không có DNS server IPv6 trong một danh sách** không tự chứng minh máy không thể phân giải tên IPv6.

### Quan sát gói trong PCAP được phép

Các bộ lọc hiển thị Wireshark tham khảo:

~~~text
icmpv6.type == 133
icmpv6.type == 134
icmpv6.type == 135
icmpv6.type == 136
udp.port == 546 || udp.port == 547
ipv6
~~~

Các ICMPv6 type tương ứng:

- **133:** Router Solicitation.
- **134:** Router Advertisement.
- **135:** Neighbor Solicitation.
- **136:** Neighbor Advertisement.

Chỉ dùng PCAP thu thập hợp pháp từ network interface/điểm quan sát được cấp quyền. Tùy switch, SPAN, Wi-Fi và hệ điều hành, một sensor có thể không thấy mọi multicast hoặc gói giữa các host; **không thấy RA trong PCAP chưa đủ để kết luận router không gửi RA**.

### Phiếu kiểm tra cho mỗi VLAN

~~~text
Test ID:                 IPV6-IPAM-01
Timestamp/timezone:      [đã xác minh]
Site/VLAN/VRF:           [vị trí thật]
Expected prefix:        [prefix do IPAM cấp]
Observed IPv6:          [địa chỉ và scope]
Source of address:      [SLAAC / DHCPv6 / static / chưa rõ]
RA source and options:  [router, PIO, M/O, DNS nếu có]
Default route:          [next hop + interface]
DNS resolver:           [nguồn cấu hình + kết quả kiểm tra]
DAD/lifetimes:          [thông tin quan sát]
Security policy:        [rule, zone, allow/deny]
Evidence:               [client state, router logs, capture]
Owner:                  [người chịu trách nhiệm]
Result:                 [PASS / FAIL / INCONCLUSIVE]
~~~

## 18. Xử lý sự cố IPv6 address management

### 18.1. Host có IPv6 nhưng không truy cập Internet

Có thể do:

1. Chỉ có **link-local**, không nhận GUA/ULA cần thiết.
2. Có GUA nhưng **không có default route** phù hợp vì RA thiếu hoặc bị chặn.
3. Default route tồn tại nhưng upstream không có tuyến trả về hoặc policy firewall chặn.
4. DNS resolver không hoạt động hoặc trả kết quả không phù hợp.
5. ICMPv6 Packet Too Big bị chặn khiến **Path MTU Discovery** thất bại ở một số đường truyền.
6. IPv6 VPN/split tunnel hoặc security group cloud khác chính sách IPv4.

Quy trình: đọc địa chỉ → route → RA/DNS → firewall/flow → ứng dụng. Không đổi DHCPv6 server trước khi xác nhận vấn đề nằm ở khâu nào.

### 18.2. Host không nhận địa chỉ DHCPv6

Kiểm tra lần lượt:

- Host và OS có hỗ trợ **DHCPv6 stateful** không?
- Router gửi RA với các thông tin phù hợp và client có nhận được không?
- DHCPv6 relay, server, scope và policy có hoạt động đúng không?
- UDP 546/547 được phép đi qua những điểm cần thiết không?
- DUID/IA_NA, pool và lifetime có bị lỗi hoặc cạn địa chỉ theo cấu hình không?
- Host có thể vẫn có **SLAAC GUA** và truy cập mạng bình thường dù không có DHCPv6 lease.

Không nên buộc mọi thiết bị dùng DHCPv6 stateful nếu hệ sinh thái client không hỗ trợ. Mô hình hỗn hợp SLAAC + DNS RA hoặc DHCPv6 stateless có thể phù hợp hơn tùy nền tảng.

### 18.3. Host có hai default router hoặc prefix lạ

Đây có thể là thiết kế dự phòng có chủ đích, cấu hình còn sót hoặc **rogue RA**. Cần xem router source, interface, router lifetime, prefix, chính sách RA Guard và change log. **Không kết luận đang bị tấn công chỉ vì có nhiều RA**; trong một mạng có nhiều router, điều này có thể hợp lệ.

Nếu xác minh RA không được phép, thực hiện containment qua cổng/zone thích hợp theo quy trình, theo dõi ảnh hưởng tới host và xác nhận cấu hình phục hồi. Tránh chặn toàn bộ ICMPv6.

### 18.4. Renumbering sau đổi prefix

Khi prefix từ ISP hoặc PD đổi:

1. Lấy prefix mới vào IPAM, xác minh không trùng và có route.
2. Cập nhật RA/PD downstream, default route và firewall prefix objects.
3. Đồng bộ AAAA/PTR, service discovery và kiểm tra app/TLS endpoint nếu cần.
4. Đánh giá **preferred/valid lifetime** của prefix cũ; có thể cần giai đoạn cùng tồn tại hai prefix.
5. Kiểm tra VPN/cloud peering, ACL, DNS và monitoring.
6. Thu hồi prefix cũ có kiểm soát sau khi xác minh kết nối và phiên đang sử dụng.

**Không tự động coi thông báo RA mới là host sẽ tức khắc bỏ mọi địa chỉ cũ.** Hệ điều hành có thể giữ địa chỉ theo lifetime và cơ chế bảo vệ. Một kế hoạch renumbering phải có cửa sổ chuyển đổi và bằng chứng từ client thật.

## 19. Những sai lầm cần tránh

| Nhận định sai | Hậu quả | Cách hiểu đúng |
|---|---|---|
| “IPv6 chỉ là IPv4 dài hơn” | Bỏ qua SLAAC, RA/ND, nhiều địa chỉ và privacy extension | Quản lý prefix, lifecycle và danh tính |
| “DHCPv6 cấp default gateway” | Máy có lease nhưng không biết đường đi | Xác minh RA/default route riêng |
| “Mọi host đều hỗ trợ DHCPv6 stateful” | Wi-Fi/BYOD và các OS khác có thể không nhận địa chỉ | Thử thiết bị thật, chọn SLAAC/DHCPv6 phù hợp |
| “Có DHCP lease thì biết chắc người dùng” | DUID/IPv6 không chứng minh danh tính | Kết hợp NAC, EDR, Wi-Fi/session và thời gian |
| “Không có lease nghĩa là host trái phép” | SLAAC tạo địa chỉ không cần DHCPv6 lease | Kiểm tra RA, asset và telemetry |
| “IPv6 IID chắc chắn chứa MAC” | Cơ chế stable/privacy address có thể không dựa EUI-64 | Không suy MAC từ IID |
| “Một interface có đúng một IPv6” | Thiếu temporary, ULA, link-local và nhiều prefix | IPAM hỗ trợ nhiều địa chỉ/tài sản |
| “Dùng /120 cho mọi VLAN để dễ quản lý” | SLAAC host có thể không hoạt động | Dùng /64 thông thường cho host LAN |
| “Chặn hết ICMPv6 an toàn hơn” | Hỏng ND, RA và Path MTU Discovery | Lọc theo loại/zone/nguồn, giữ thông điệp thiết yếu |
| “RA Guard luôn đủ bảo vệ” | Hiệu quả phụ thuộc thiết bị và cấu hình | Kết hợp port trust, ND/DHCPv6 guard và giám sát |
| “IPv4 firewall đã bảo vệ cả IPv6” | Dual-stack có thể mở đường khác | Thiết kế/test chính sách IPv6 riêng |
| “NAT là điều kiện bắt buộc để bảo mật” | Dễ bỏ qua firewall stateful và least privilege | Áp chính sách quyền trực tiếp cho IPv6 |
| “PTR record xác định chắc chủ máy” | DNS có thể stale hoặc bị cấu hình sai | Dùng nhiều nguồn bằng chứng |
| “Prefix được cấp không bao giờ đổi” | ISP/PD và cloud có thể renumber | Kế hoạch lifecycle, automation, DNS và rollback |

## 20. Câu hỏi tự kiểm tra

1. Vì sao một interface có thể có đồng thời link-local, GUA và temporary IPv6?
2. Prefix **2001:db8:1200:1000::/56** chứa bao nhiêu mạng **/64**? Liệt kê hai /64 hợp lệ trong đó.
3. Vì sao **/64** thường được dùng cho LAN cần SLAAC? Có phải mọi đường kết nối IPv6 đều phải là /64 không?
4. Phân biệt **SLAAC**, **DHCPv6 stateful**, **DHCPv6 stateless** và **DHCPv6 PD**.
5. DHCPv6 có tự cung cấp default router cho một host như DHCPv4 Option 3 không? Nếu không, host thường học từ đâu?
6. RA chứa những thông tin nào liên quan tới prefix, đường đi và DNS?
7. **A/L trong PIO** khác **M/O trong RA** ở điểm nào? Vì sao M/O không bắt mọi OS phải dùng DHCPv6?
8. **DAD** làm gì và vì sao không thể coi Neighbor cache là asset inventory đầy đủ?
9. DUID khác MAC như thế nào và vì sao DUID không đủ để chứng minh danh tính người dùng?
10. Vì sao một router nhận IPv6 WAN address chưa chắc đã nhận được delegated prefix cho LAN?
11. Khi điều tra địa chỉ temporary trong firewall log, cần ghép những nguồn thông tin nào?
12. RA Guard và DHCPv6 Guard có vai trò khác nhau ra sao?
13. Vì sao chặn toàn bộ ICMPv6 có thể làm hỏng kết nối mặc dù TCP/443 vẫn được phép?
14. Một mạng dùng cloud IPv6 và IPv4 dual-stack cần kiểm thử những rule/path nào riêng?
15. Sau khi prefix ISP đổi, phải cập nhật RA, DNS, firewall và IPAM theo những bước nào để tránh gián đoạn?

## 21. Ghi nhớ trọng tâm

**IPv6 address management là quản lý prefix, cơ chế cấp phát, trạng thái địa chỉ và danh tính tài sản theo thời gian.** SLAAC dựa vào **RA**, DHCPv6 có thể cấp địa chỉ hoặc thông tin bổ trợ, **DHCPv6 PD** cấp prefix cho router; còn **default router thường được học qua RA**, không phải một tùy chọn gateway kiểu DHCPv4. Một máy có thể dùng đồng thời GUA, ULA, link-local, stable address và temporary address, nên **không thể dùng DHCPv6 lease table làm nguồn danh tính duy nhất**.

Thiết kế vững chắc bắt đầu từ **quy hoạch /48–/56–/64 có kiểm soát**, ghi nhận trong **IPAM/DDI**, rồi đồng bộ gateway, RA/DHCPv6, DNS, routing và firewall cho cả IPv4/IPv6 khi dual-stack. Cần kết hợp **NAC, RA Guard, DHCPv6 Guard, ND monitoring, EDR, flow logs và quyền tối thiểu**, đồng thời giữ ICMPv6 thiết yếu. Chỉ tuyên bố hệ thống hoạt động đúng khi đã kiểm chứng **địa chỉ, default route, DNS, phân đoạn, truy cập hợp lệ, truy cập bị chặn và khả năng quy thuộc thiết bị trong khoảng thời gian cụ thể**.
