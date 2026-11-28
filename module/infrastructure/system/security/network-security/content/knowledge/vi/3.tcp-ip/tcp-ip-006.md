# ARP và Neighbor Discovery: phân giải địa chỉ và bảo vệ mạng cục bộ

## 1. Vì sao hai giao thức này quan trọng?

Trong mạng Ethernet, một thiết bị có thể biết **địa chỉ IP đích** nhưng vẫn cần biết **địa chỉ MAC của chặng kế tiếp** để đóng gói khung Ethernet và truyền trên cùng liên kết. Hai cơ chế đảm nhận công việc này là:

- **ARP (Address Resolution Protocol)** cho IPv4: tìm địa chỉ MAC tương ứng với địa chỉ IPv4 ở mạng cục bộ.
- **Neighbor Discovery (ND hoặc NDP)** cho IPv6: dùng các bản tin ICMPv6 để phân giải địa chỉ lớp liên kết, phát hiện router, xác định tiền tố mạng, kiểm tra địa chỉ trùng lặp và theo dõi khả năng liên lạc với láng giềng.

Cả hai đều tác động trực tiếp đến **đường đi của lưu lượng ở chặng đầu**. Nếu một máy trạm tin nhầm ánh xạ IP–MAC hoặc tin một thông báo router giả, lưu lượng có thể bị chuyển tới thiết bị không mong muốn, bị gián đoạn hoặc bị quan sát trái phép.

Sau bài này, người học có thể:

1. Giải thích lúc nào máy trạm phân giải MAC của đích và lúc nào phân giải MAC của default gateway.
2. Đọc một trao đổi ARP Request/Reply và các bản tin ND chủ yếu.
3. Phân biệt phân giải láng giềng, phát hiện router, DAD và kiểm tra khả năng tiếp cận trong IPv6.
4. Nhận diện dấu hiệu ARP spoofing, Neighbor Advertisement giả và rogue Router Advertisement.
5. Chọn biện pháp bảo vệ phù hợp cho mạng IPv4, IPv6 và mạng chạy đồng thời hai giao thức (dual stack).
6. Sử dụng công cụ hệ điều hành và bộ phân tích gói tin để kiểm tra, khoanh vùng lỗi.

## 2. Phân giải IP thành MAC: hiểu đúng phạm vi

Địa chỉ IP dùng để định tuyến ở lớp mạng; địa chỉ MAC dùng để chuyển khung trên liên kết Ethernet. Thiết bị đầu cuối trước tiên dùng **bảng định tuyến** để xác định địa chỉ IP của *next hop*:

- Nếu đích thuộc mạng **on-link** (cùng liên kết theo bảng định tuyến), next hop là chính IP đích.
- Nếu đích ở mạng khác, next hop thường là **địa chỉ IP của gateway**. Máy trạm phân giải MAC của gateway, không cố tìm MAC của máy đích ở Internet.
- Ánh xạ IP–MAC được lưu tạm trong **neighbor cache** (IPv6) hoặc **ARP cache** (IPv4). Các mục có thể hết hạn, đổi trạng thái hoặc được cập nhật.

Ví dụ trong một VLAN:

| Thiết bị | IPv4 | MAC minh họa |
|---|---|---|
| Máy A | `192.0.2.10/24` | `02:00:00:00:00:10` |
| Máy B | `192.0.2.20/24` | `02:00:00:00:00:20` |
| Gateway | `192.0.2.1/24` | `02:00:00:00:00:01` |

Khi A gửi cho `192.0.2.20`, A tìm MAC của **B**. Khi A gửi cho `198.51.100.50` qua default route, A tìm MAC của **gateway `192.0.2.1`**. IP nguồn/đích trong gói IP vẫn là địa chỉ của hai đầu cuối; MAC nguồn/đích trong khung Ethernet tương ứng với **chặng Ethernet hiện tại**.

> Ví dụ dùng dải IPv4 `192.0.2.0/24`, `198.51.100.0/24` và IPv6 `2001:db8::/32` dành cho tài liệu, không phải địa chỉ thực cần cấu hình vào mạng sản xuất.

## 3. ARP trong IPv4

### 3.1. Trình tự hoạt động

Khi máy A chưa biết MAC của B:

1. A tra bảng định tuyến, kết luận `192.0.2.20` thuộc cùng mạng.
2. A kiểm tra ARP cache. Nếu chưa có ánh xạ sử dụng được, A phát **ARP Request** dưới dạng khung broadcast Ethernet đến `ff:ff:ff:ff:ff:ff`, hỏi ai có IP `192.0.2.20`.
3. B nhận request, nhận ra địa chỉ IPv4 đích trong yêu cầu là của mình và thường trả **ARP Reply** unicast cho A, mang MAC của B.
4. A lưu ánh xạ `192.0.2.20 → 02:00:00:00:00:20` vào cache, sau đó gửi khung dữ liệu.
5. Khi cache không còn hợp lệ, hệ điều hành có thể phân giải lại; hành vi và thời gian lưu phụ thuộc cách triển khai.

~~~mermaid
sequenceDiagram
    participant A as Máy A
    participant LAN as VLAN / Ethernet
    participant B as Máy B
    A->>LAN: ARP Request (broadcast): Ai có 192.0.2.20?
    LAN->>B: Chuyển ARP Request
    B-->>A: ARP Reply: 192.0.2.20 ở MAC ...:20
    A->>B: Gửi khung Ethernet tới MAC ...:20
~~~

Trong Ethernet/IPv4, ARP có EtherType **`0x0806`**. Một bản tin ARP thông dụng gồm:

| Trường | Giá trị thường gặp | Vai trò |
|---|---|---|
| Hardware type | `1` | Mạng Ethernet |
| Protocol type | `0x0800` | Địa chỉ giao thức IPv4 |
| Hardware address length | `6` | MAC dài 6 byte |
| Protocol address length | `4` | IPv4 dài 4 byte |
| Opcode | `1` hoặc `2` | Request hoặc Reply |
| Sender MAC/IP | MAC/IP của bên gửi | Thông tin mà bên nhận có thể học |
| Target MAC/IP | MAC/IP của bên được hỏi | Request thường chưa biết target MAC |

ARP hoạt động trực tiếp trên liên kết, **không phải** một bản tin TCP hay UDP và không dùng cổng TCP/UDP. Router bình thường không chuyển tiếp ARP broadcast qua các mạng con khác.

### 3.2. Những trường hợp cần phân biệt

**Gratuitous ARP (GARP):** Một host chủ động phát thông tin ánh xạ địa chỉ của chính nó, thường khi vừa nhận IP, chuyển giao IP ảo hoặc có thay đổi đường dự phòng. GARP có thể là ARP Request hoặc Reply tùy thiết bị. Nó hữu ích trong failover, nhưng vì thiếu xác thực nên cũng cần giám sát khi xuất hiện bất thường.

**ARP Probe/Announcement:** Trong kiểm tra xung đột IPv4 theo RFC 5227, host có thể gửi ARP Probe với sender protocol address là `0.0.0.0` để kiểm tra địa chỉ dự định dùng; sau đó có thể thông báo địa chỉ. Đây là cơ chế phát hiện xung đột, không phải chứng thực quyền sở hữu địa chỉ.

**Proxy ARP:** Router hoặc thiết bị khác trả lời ARP thay cho một IP không nằm trực tiếp trên host trả lời. Cơ chế này có thể hữu ích trong một số cấu hình kế thừa, nhưng có thể che dấu lỗi subnet/mask và làm tăng độ phức tạp bảo mật. Không kết luận mọi ARP Reply có sender MAC của router là tấn công khi chưa kiểm tra Proxy ARP hoặc IP ảo.

**ARP cache:** Cache có thể chứa mục động và mục được cấu hình tĩnh. Entry tĩnh dùng trong tình huống đặc biệt nhưng tăng công quản trị, nhất là khi thay card mạng hoặc đổi gateway.

### 3.3. Giới hạn bảo mật của ARP

ARP **không có xác thực nguồn gốc tích hợp**. Một host trong cùng miền lớp 2 có thể cố gửi bản tin ARP sai để thiết bị khác cập nhật ánh xạ IP–MAC theo ý nó. Để hiểu nguy cơ, xét tình huống giả định:

- Gateway thật: `192.0.2.1 → 02:00:00:00:00:01`.
- Một máy không đáng tin cậy phát thông tin sai rằng `192.0.2.1` tương ứng với một MAC khác.
- Nếu máy A chấp nhận thông tin giả, một số khung của A có thể tới MAC sai: gây **mất kết nối**, **chuyển tiếp qua trung gian** hoặc **nghe lén** tùy khả năng của thiết bị đó.

Đây là **ARP spoofing / ARP cache poisoning**. Thông tin ARP đáng ngờ không nhất thiết là tấn công: thay đổi MAC hợp lệ do failover, thay phần cứng hay cấu hình mạng cũng có thể tạo triệu chứng tương tự. Cần đối chiếu với cấu hình switch, gateway, DHCP và nhật ký sự kiện.

## 4. Neighbor Discovery trong IPv6

IPv6 **không sử dụng ARP**. Nó sử dụng **Neighbor Discovery Protocol (NDP)** dựa trên **ICMPv6**, theo các nguyên tắc trong RFC 4861 và phần bổ sung liên quan. ND đảm nhận nhiều việc hơn việc tìm MAC.

### 4.1. Năm loại bản tin cốt lõi

| Loại ICMPv6 | Type | Nhiệm vụ chính |
|---|---:|---|
| Router Solicitation (RS) | 133 | Host hỏi để router sớm phát thông tin cấu hình mạng |
| Router Advertisement (RA) | 134 | Router thông báo chính nó, các tiền tố và tham số liên kết |
| Neighbor Solicitation (NS) | 135 | Tìm MAC, kiểm tra láng giềng hoặc kiểm tra địa chỉ trùng |
| Neighbor Advertisement (NA) | 136 | Trả lời NS hoặc chủ động thông báo thông tin láng giềng |
| Redirect | 137 | Router đề xuất next hop thích hợp hơn trong một số trường hợp |

NS/NA làm công việc gần với ARP Request/Reply, nhưng hai cặp này **không hoàn toàn tương đương**: NS/NA còn tham gia Duplicate Address Detection (DAD) và Neighbor Unreachability Detection (NUD). RS/RA/Redirect lại là khả năng riêng của ND.

Bản tin ND phải được kiểm tra chặt chẽ, bao gồm **IPv6 Hop Limit bằng 255**. Hop Limit giúp từ chối bản tin đã đi qua router (không còn 255), nhưng **không** chống được một host giả mạo ngay trên cùng liên kết. RA hợp lệ phải có địa chỉ IPv6 nguồn link-local của router; các quy tắc kiểm tra khác phụ thuộc loại bản tin.

### 4.2. Phân giải MAC bằng multicast

Giả sử A có `2001:db8:10::10/64` và muốn liên lạc với B có `2001:db8:10::20/64` trên cùng liên kết:

1. A tra route và neighbor cache.
2. Nếu chưa có ánh xạ của B, A gửi NS với **Target Address** là `2001:db8:10::20`.
3. Thông thường NS đi đến địa chỉ IPv6 **solicited-node multicast** được suy từ 24 bit cuối của IP đích: `ff02::1:ff00:20`.
4. Khung Ethernet tương ứng dùng multicast MAC `33:33:ff:00:00:20`. Các nút quan tâm đến địa chỉ này xử lý NS.
5. B gửi NA, thường unicast cho A, cung cấp thông tin MAC của mình qua tùy chọn Target Link-Layer Address.
6. A cập nhật neighbor cache, rồi tiếp tục giao tiếp.

~~~mermaid
sequenceDiagram
    participant A as Máy A (IPv6)
    participant Group as Nhóm solicited-node
    participant B as Máy B
    A->>Group: NS: ai có 2001:db8:10::20?
    Group->>B: Multicast ND tới nhóm phù hợp
    B-->>A: NA: địa chỉ thuộc MAC ...:20
    A->>B: Truyền dữ liệu qua MAC ...:20
~~~

**Lợi ích so với broadcast ARP:** NS thường dùng multicast đến nhóm có phạm vi hẹp hơn thay vì phát broadcast Ethernet đến mọi nút trong VLAN. Điều này không có nghĩa multicast hoàn toàn miễn nhiễm quá tải; hoạt động còn phụ thuộc tính năng chuyển mạch và quản lý multicast của thiết bị.

Địa chỉ IPv6 **`fe80::/10`** là phạm vi link-local; mỗi giao diện IPv6 thường có địa chỉ link-local. Một router cũng thường được các host sử dụng bằng **địa chỉ link-local của router** làm next hop cho default route.

### 4.3. Phát hiện router và cấu hình địa chỉ

Khi kết nối vào mạng IPv6, host có thể phát RS tới nhóm **`ff02::2`** (all-routers). Router trả RA theo chu kỳ hoặc đáp ứng RS, thường từ địa chỉ nguồn link-local. RA cung cấp các thông tin có thể gồm:

- **Router Lifetime:** cho biết router có thể được chọn làm default router trong bao lâu; lifetime bằng 0 nghĩa là RA đó không giới thiệu router làm default router.
- **Prefix Information Option (PIO):** công bố tiền tố và các cờ. Cờ **L** nói tiền tố có thể được xem là on-link; cờ **A** cho phép dùng tiền tố để tự cấu hình địa chỉ SLAAC khi phù hợp.
- **Managed (M) / Other (O) flags:** gợi ý host lấy địa chỉ và/hoặc thông tin khác qua DHCPv6; hành vi phụ thuộc hỗ trợ và chính sách của hệ điều hành.
- **MTU, thông tin DNS qua RDNSS** nếu router và client hỗ trợ.

**SLAAC (Stateless Address Autoconfiguration)** thường dùng thông tin tiền tố từ RA để hình thành địa chỉ IPv6. Phần định danh giao diện (interface identifier) trên hệ thống hiện đại có thể là địa chỉ ổn định theo tiền tố hoặc địa chỉ riêng tư thay đổi định kỳ, **không nhất thiết được tạo trực tiếp từ MAC**.

Cần phân biệt: **DHCPv6 không phải nguồn cung cấp default gateway theo cơ chế chuẩn thông dụng của IPv6**; thông tin default router thường đến từ RA. Vô hiệu hóa SLAAC vì dùng DHCPv6 không có nghĩa tự động bỏ qua RA.

### 4.4. Duplicate Address Detection (DAD)

Trước khi đưa địa chỉ IPv6 mới vào dùng bình thường, host thường thực hiện DAD:

1. Địa chỉ dự kiến được coi là *tentative*.
2. Host gửi NS để dò trùng, **địa chỉ nguồn IPv6 là `::`** (unspecified), Target Address là địa chỉ đang kiểm tra; NS thường gửi đến solicited-node multicast của target.
3. Nếu nhận dấu hiệu có nút khác đã sở hữu địa chỉ đó, host không nên sử dụng địa chỉ trùng; hệ điều hành có thể báo lỗi.

DAD giúp phát hiện **trùng địa chỉ**, nhưng **không chứng minh danh tính** chủ sở hữu. Một thiết bị độc hại ở cùng liên kết có thể gây nhiễu quá trình này. DAD áp dụng cho địa chỉ IPv6 tạo theo nhiều cơ chế, không chỉ SLAAC.

### 4.5. Neighbor Unreachability Detection (NUD)

ND theo dõi việc một láng giềng còn phản hồi hay không. Các trạng thái thường gặp trong neighbor cache:

| Trạng thái | Ý nghĩa thực tế |
|---|---|
| `INCOMPLETE` | Đang thử phân giải địa chỉ lớp liên kết |
| `REACHABLE` | Có bằng chứng tương đối gần đây rằng láng giềng liên lạc được |
| `STALE` | Đã có MAC nhưng cần xác nhận lại khi sử dụng |
| `DELAY` | Chờ một khoảng trước khi thăm dò chủ động |
| `PROBE` | Gửi NS để kiểm tra khả năng liên lạc |
| `FAILED` | Không hoàn thành phân giải/kiểm tra láng giềng |

Tên và cách hiển thị có thể khác nhau theo hệ điều hành. **`STALE` không tự động có nghĩa bị tấn công hoặc mất mạng**; đây có thể là trạng thái bình thường cho entry chưa sử dụng gần đây.

### 4.6. ICMPv6 là thành phần thiết yếu

ND sử dụng ICMPv6. Bên cạnh các type 133–137, mạng IPv6 còn cần một số thông báo ICMPv6 khác như **Packet Too Big** phục vụ Path MTU Discovery. Chặn toàn bộ ICMPv6 bằng firewall có thể gây mất phân giải láng giềng, hỏng việc nhận default router, lỗi truy cập không ổn định hoặc hiện tượng kết nối chỉ hoạt động với gói nhỏ.

Chính sách bảo mật phù hợp là **lọc theo vai trò và loại thông điệp**, giới hạn nguồn phát RA trên cổng access khi cần, và giữ các bản tin vận hành hợp lệ trong phạm vi cần thiết.

## 5. So sánh ARP và IPv6 Neighbor Discovery

| Tiêu chí | ARP (IPv4) | ND (IPv6) |
|---|---|---|
| Phân giải L3 → L2 | ARP Request/Reply | ICMPv6 NS/NA |
| Cách gửi yêu cầu cơ bản | Ethernet broadcast | Solicited-node multicast |
| Giao thức trên liên kết | ARP, EtherType `0x0806` | IPv6 + ICMPv6, EtherType IPv6 `0x86dd` |
| Phát hiện router | Thường nhờ cấu hình/DHCPv4 và giao thức khác | RS/RA tích hợp |
| Phát hiện trùng địa chỉ | ARP Probe/Announcement có thể hỗ trợ | DAD dùng NS/NA |
| Kiểm tra láng giềng còn hoạt động | Chủ yếu theo cơ chế cache/hệ điều hành | NUD là thành phần chuẩn |
| Xác thực bản tin mặc định | Không | Không |
| Tấn công điển hình | ARP cache poisoning | Spoofed NA, rogue RA, ND DoS |
| Bảo vệ đặc thù ở switch | DHCP snooping + Dynamic ARP Inspection | RA Guard, ND inspection/IPv6 first-hop security |

Cả hai cùng **giải quyết chặng cục bộ**. Chúng không thay thế định tuyến IP, TLS, VPN hay xác thực ứng dụng. Tấn công sửa ánh xạ chặng đầu không tự động giải mã được nội dung có mã hóa đầu cuối, dù vẫn có thể gây mất kết nối, thu thập metadata hoặc điều hướng lưu lượng.

## 6. Rủi ro an ninh từ các bản tin không được xác thực

Một điểm yếu chung là host thường phải tin một số thông tin xuất hiện trên liên kết để có thể gửi và nhận dữ liệu. Các trường hợp quan trọng:

### 6.1. ARP spoofing / cache poisoning

**Cơ chế:** thiết bị trên cùng miền lớp 2 phát ánh xạ IPv4–MAC không đúng. Tùy cơ chế cập nhật ARP cache và cấu hình thiết bị đích, một phần lưu lượng có thể chuyển sai MAC.

**Hậu quả:** mất kết nối, chuyển tiếp qua thiết bị trung gian, thu thập metadata, hoặc gián đoạn dịch vụ. Nếu kết nối ứng dụng được bảo vệ bởi TLS với xác thực chứng chỉ đúng cách, việc kiểm soát chặng Ethernet vẫn không đủ để đọc được nội dung mã hóa.

**Dấu hiệu giám sát:** IP gateway đổi MAC bất ngờ; một IP xuất hiện với nhiều MAC trong thời gian ngắn; số ARP Reply hoặc gratuitous ARP tăng đột biến; các cổng switch học MAC bất thường. Một số thay đổi là hợp lệ trong HA/VRRP hoặc bảo trì, cần đối chiếu trước khi kết luận.

### 6.2. Neighbor Advertisement giả

**Cơ chế:** một nút phát NA sai, khiến thiết bị khác cập nhật thông tin neighbor hoặc hiểu nhầm khả năng tiếp cận một địa chỉ IPv6.

**Hậu quả:** tương tự ARP poisoning ở phạm vi liên kết. Một số tùy chọn/flag trong NA (chẳng hạn Solicited, Override, Router) ảnh hưởng đến cách host xử lý; không nên giả định mọi NA đều được chấp nhận như nhau.

**Dấu hiệu:** một IPv6 có thay đổi MAC bất thường; log ND inspection; xung đột địa chỉ hoặc lưu lượng NS/NA quá nhiều.

### 6.3. Rogue Router Advertisement

**Cơ chế:** thiết bị không được ủy quyền gửi RA trong VLAN; host có thể cập nhật default router, tiền tố, DNS hoặc tham số mạng dựa trên RA đó.

**Hậu quả:** sai default route, DNS bị định hướng sai (khi host áp dụng thông tin DNS từ RA), sự cố truy cập hoặc chuyển hướng lưu lượng. Rủi ro tồn tại ngay cả trong mạng mà quản trị viên chủ yếu dùng IPv4: nhiều hệ điều hành vẫn bật IPv6.

**Dấu hiệu:** RA xuất phát từ cổng access hoặc MAC không thuộc danh sách router; default IPv6 route mới không rõ nguồn; xuất hiện tiền tố lạ, router lifetime bất thường hoặc thay đổi DNS không có trong kế hoạch.

### 6.4. Làm cạn tài nguyên và phá hoại DAD

Một lượng lớn yêu cầu phân giải địa chỉ, mục neighbor chưa hoàn chỉnh hoặc tín hiệu DAD bất thường có thể tạo áp lực cho bộ nhớ, CPU hay bảng neighbor của host/router. Lỗi thiết bị hoặc cấu hình cũng có thể sinh hiện tượng tương tự. Cần quan sát tải, bộ đếm điều khiển (control-plane counters), số mục INCOMPLETE/FAILED và độ trễ trước khi xác định nguyên nhân.

## 7. Kiến trúc phòng vệ theo từng lớp

### 7.1. Bảo vệ mạng IPv4

**DHCP snooping** trên switch quản lý có thể tạo cơ sở dữ liệu ràng buộc **IP–MAC–VLAN–cổng** cho client nhận địa chỉ bằng DHCPv4. **Dynamic ARP Inspection (DAI)** dùng các ràng buộc phù hợp và chính sách kiểm tra để loại bỏ ARP sai trên cổng không được tin cậy.

Cần triển khai có kiểm soát:

- Phân biệt **cổng trusted** (ví dụ uplink đã được xác nhận) và **untrusted** (thường là cổng người dùng); đặt nhầm trusted trên cổng access làm giảm hiệu quả.
- Máy dùng IP tĩnh có thể cần **ARP ACL / binding tĩnh** phù hợp; chỉ bật DAI mà chưa xử lý trường hợp này có thể làm mất kết nối hợp lệ.
- Theo dõi log vi phạm và rate limiting ở switch; không dựa vào một dấu hiệu ARP đơn lẻ để tự động cách ly thiết bị.
- Tách VLAN/miền broadcast theo độ tin cậy; dùng kiểm soát truy cập ở switch như 802.1X/NAC, chính sách cổng và theo dõi MAC để giảm số nguồn có thể gửi bản tin giả.

DAI không thay thế xác thực người dùng, chính sách ACL giữa VLAN hoặc bảo vệ ứng dụng. Nó cũng **không bảo vệ ND trong IPv6**.

### 7.2. Bảo vệ mạng IPv6

**RA Guard** giới hạn những cổng được phép gửi Router Advertisement. Thiết kế điển hình: chỉ cổng kết nối router hợp lệ được phép phát RA; cổng access của máy trạm không được phát RA. Trên thiết bị quản lý phù hợp, có thể kết hợp **IPv6 ND inspection/first-hop security** với các ràng buộc địa chỉ, chính sách bảo vệ nguồn, DHCPv6 Guard và giới hạn lưu lượng điều khiển.

Các điểm triển khai cần chú ý:

- RA Guard chỉ xử lý một lớp vấn đề; bản thân nó không ngăn mọi NA giả, không thay thế ND inspection và không xác thực toàn bộ IPv6.
- Chọn switch/phiên bản firmware xử lý đúng các trường hợp IPv6 extension header và phân mảnh. Một số triển khai cũ có thể bị qua mặt nếu kiểm tra RA không đầy đủ.
- Cho phép NS/NA/RS/RA **hợp lệ theo vai trò cổng**. Chặn bừa mọi ICMPv6 làm hỏng hoạt động cơ bản của IPv6.
- Đối chiếu RA với router dự kiến, tiền tố được cấp phát, thông tin DNS và chính sách địa chỉ.
- Giám sát cả IPv4 lẫn IPv6 trên mạng dual stack; tắt giao thức theo cảm tính có thể che giấu vấn đề thiết kế, thay vì giải quyết nguồn phát bản tin giả.

**SEND (Secure Neighbor Discovery, RFC 3971)** bổ sung cơ chế bảo vệ mật mã cho ND, nhưng triển khai thực tế cần hỗ trợ của nhiều thành phần và không phổ biến trên mọi hệ điều hành/thiết bị. Không nên xem SEND là tính năng mặc định của mạng IPv6.

### 7.3. Những lớp bảo vệ chung

| Lớp bảo vệ | Mục tiêu | Ví dụ thực hành |
|---|---|---|
| Quản lý truy cập L2 | Hạn chế nguồn phát bản tin trái phép | 802.1X/NAC, quản lý cổng access, VLAN hợp lý |
| Kiểm tra bản tin first hop | Xác minh thông báo tương ứng với ràng buộc/chính sách | DAI cho ARP; RA Guard, ND inspection cho IPv6 |
| Cấu hình và quản lý thay đổi | Phân biệt thay đổi hợp lệ với giả mạo | Danh sách MAC/IP router, cấu hình HA, kiểm kê prefix |
| Giám sát | Phát hiện biến động trước khi gây gián đoạn lớn | Log switch, packet capture, bảng neighbor, thống kê control plane |
| Bảo mật lớp cao hơn | Giảm thiệt hại nếu chuyển hướng chặng đầu | TLS đúng chứng chỉ, SSH, xác thực dịch vụ, phân tách quyền |

Với mạng nhiều tenant, máy ảo hoặc container, phải xét **ranh giới lớp 2 thực tế**: các host có thể cùng VLAN dù nằm trên máy vật lý khác nhau; ngược lại, khác VLAN thường không phát ARP/ND trực tiếp tới nhau qua router.

## 8. Quan sát và chẩn đoán trên hệ điều hành

Chỉ chạy ví dụ ở thiết bị và mạng mà bạn được phép kiểm tra. Tên giao diện như `eth0`, địa chỉ IP và kết quả hiển thị chỉ là minh họa.

### 8.1. Linux

~~~bash
# Xác định IP và route trước khi kết luận vấn đề phân giải địa chỉ
ip -4 addr show
ip -4 route show
ip -6 addr show
ip -6 route show

# Xem bảng neighbor của hai họ địa chỉ
ip -4 neigh show
ip -6 neigh show

# Kiểm tra route mà kernel sẽ dùng đến một đích
ip -4 route get 198.51.100.50
ip -6 route get 2001:db8:20::50

# Quan sát ARP/ICMPv6 trên một giao diện trong lab
sudo tcpdump -ni eth0 -e -vv 'arp or icmp6'
~~~

Ví dụ neighbor cache (giá trị giả định):

~~~text
192.0.2.1 dev eth0 lladdr 02:00:00:00:00:01 REACHABLE
2001:db8:10::20 dev eth0 lladdr 02:00:00:00:00:20 STALE
fe80::1 dev eth0 lladdr 02:00:00:00:00:01 REACHABLE
~~~

Với một IPv6 đích chưa có trong cache, hãy xem kernel định tuyến qua gateway hay coi đích là on-link trước khi mong chờ NS cho địa chỉ đó. Mục `STALE` vẫn có thể dùng; mục `INCOMPLETE` tồn tại lâu cùng với các lần NS lặp lại thường chỉ ra vấn đề phân giải hoặc không có phản hồi.

### 8.2. Windows

~~~powershell
# Route và địa chỉ giao diện
ipconfig /all
Get-NetRoute -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv6

# Bảng neighbor
arp -a
Get-NetNeighbor -AddressFamily IPv4
Get-NetNeighbor -AddressFamily IPv6
netsh interface ipv6 show neighbors
~~~

Tên cột/trạng thái có thể khác giữa các phiên bản Windows. Khi thấy MAC lạ, kiểm tra đúng **InterfaceIndex**, VLAN, route và gateway thực tế; trên máy có Wi-Fi, VPN hoặc nhiều card mạng, cùng một đích có thể đi qua các giao diện khác nhau.

### 8.3. Bộ lọc trong Wireshark

~~~text
arp
icmpv6.type == 133 || icmpv6.type == 134
icmpv6.type == 135 || icmpv6.type == 136
icmpv6.type == 137
~~~

Trong Ethernet capture, xem **source/destination MAC**, địa chỉ IPv4/IPv6, opcode hoặc ICMPv6 type và cờ/option thích hợp. Với ARP, chú ý Sender MAC/IP và Target IP. Với ND, chú ý Target Address, Source/Target Link-Layer Address option, RA prefix, router lifetime và hop limit.

> Khi đánh giá “thiếu packet”, nhớ rằng capture tại máy trạm chỉ nhìn thấy lưu lượng đến card mạng đó. Muốn phân tích cả VLAN, có thể cần SPAN/mirror port hoặc capture đúng điểm mạng theo quyền quản trị.

## 9. Lab an toàn: phân biệt luồng bình thường và dấu hiệu sai lệch

Mục tiêu là **quan sát hành vi hợp lệ**, không phát bản tin giả hay gây gián đoạn mạng. Môi trường đề xuất: hai máy ảo cùng VLAN lab và một router ảo (nếu cần thử đường khác mạng). Địa chỉ phải khớp với cấu hình lab thực tế.

### Bài A — ARP trên cùng subnet và qua gateway

1. Ghi IP, subnet mask, default gateway, MAC từng máy; kiểm tra bảng route.
2. Dùng công cụ capture hợp lệ để quan sát `arp` trên giao diện lab.
3. Từ A, gửi một gói ping đến B cùng subnet, sau đó gửi đến một đích khác subnet có route qua gateway.
4. Đối chiếu các ARP Request xuất hiện: khi đến B là truy vấn IP của B; khi đến đích khác subnet là truy vấn IP next hop/gateway (nếu chưa có trong cache).
5. Đọc lại cache, ghi IP–MAC đã học; không suy diễn rằng mỗi lần ping đều phải sinh ARP mới, vì có thể đã có cache.

**Kết quả mong đợi:** A dùng MAC của B cho kết nối cùng mạng và MAC của gateway để chuyển gói qua mạng khác. Khi chỉ nhìn packet capture trên A, có thể không thấy ARP mới nếu ánh xạ còn hợp lệ.

### Bài B — ND trên IPv6

1. Bật IPv6 đúng cách trên các VM trong lab; ghi địa chỉ link-local, global/unicast (nếu có) và default route.
2. Quan sát `icmpv6.type == 135 || icmpv6.type == 136` khi A kết nối với IPv6 on-link của B.
3. Xác định NS Target Address và solicited-node multicast; kiểm tra NA trả về.
4. Đọc `ip -6 neigh show` hoặc `Get-NetNeighbor -AddressFamily IPv6`, so sánh với MAC đúng của B.
5. Nếu có router IPv6 trong lab, quan sát RS/RA bằng bộ lọc type 133/134 và đối chiếu prefix, router lifetime, default route với cấu hình dự kiến.

**Kết quả mong đợi:** việc tìm MAC dùng NS/NA; thông tin về router/prefix xuất hiện trong RA. NS có thể được gửi unicast khi kiểm tra NUD, nên không khẳng định mọi NS đều multicast.

### Bài C — Phân tích một cảnh báo giả định

Bộ giám sát báo rằng trong một VLAN access có RA từ MAC không thuộc router đã đăng ký, đồng thời một số máy xuất hiện default IPv6 route mới.

**Các bước phân tích phòng vệ:** xác minh timestamp và cổng switch phát RA; kiểm tra xem đây có phải router dự phòng/bài kiểm thử được phê duyệt; so sánh prefix, lifetime và DNS với cấu hình; đánh giá ảnh hưởng tới client; rồi áp dụng chính sách RA Guard ở cổng access nếu hạ tầng hỗ trợ và đã kiểm thử. Giữ lại bản capture, log và thay đổi cấu hình để có thể kiểm tra lại nguyên nhân.

## 10. Quy trình xử lý sự cố ARP/ND

Khi máy A không liên lạc được với đích, xử lý theo chuỗi nguyên nhân:

1. **Xác định IP và mạng:** IP/mask hoặc IPv6 prefix có đúng không? Có trùng địa chỉ hoặc DAD thất bại không?
2. **Xác định next hop:** Bảng route chọn giao diện/địa chỉ gateway nào? Đích là on-link hay off-link?
3. **Kiểm tra ánh xạ láng giềng:** Có entry đúng cho IP next hop không? Entry đang REACHABLE, STALE, INCOMPLETE hay FAILED?
4. **Quan sát bản tin thực tế:** Request/NS có ra đúng giao diện? Reply/NA có quay lại? MAC và Target Address có hợp lý?
5. **Kiểm tra switch/L2:** VLAN, port isolation, MAC learning, DHCP snooping/DAI, RA Guard và ND inspection có đang chặn gói hợp lệ không?
6. **Kiểm tra tuyến và chính sách L3/L4:** Nếu phân giải thành công nhưng ứng dụng vẫn lỗi, tiếp tục đánh giá ACL/firewall, routing, MTU/ICMPv6, TCP/TLS và dịch vụ đích.

| Triệu chứng | Khả năng cần kiểm tra | Bằng chứng hữu ích |
|---|---|---|
| IPv4 ping cùng subnet lỗi, ARP cache trống | Sai VLAN, ARP Reply không quay lại, host đích tắt, chính sách DAI | ARP capture hai phía, bảng MAC switch, DAI log |
| IPv4 mất mạng sau thay gateway | GARP chưa cập nhật, MAC HA thay đổi, cache cũ hoặc giả mạo | ARP cache trước/sau, log VRRP/HA, thông tin gateway chuẩn |
| IPv6 có địa chỉ nhưng không có default route | Không nhận RA, router lifetime 0, chính sách client hoặc RA Guard | ICMPv6 RA capture, route table, log switch |
| IPv6 neighbor ở INCOMPLETE/FAILED | NS không ra/NA không về, sai link, policy filter | ICMPv6 NS/NA capture và trạng thái neighbor |
| IPv6 chỉ lỗi với gói lớn | Path MTU Discovery/Packet Too Big bị chặn | ICMPv6 capture, MTU giao diện, firewall counters |
| IPv6 xuất hiện prefix hoặc DNS lạ | Router mới, cấu hình nhầm hoặc rogue RA | RA capture, MAC nguồn/cổng switch, danh sách router được phép |

Trước khi xóa cache hàng loạt, đổi trạng thái trusted port hoặc ngắt giao thức trên mạng vận hành, cần xác định phạm vi ảnh hưởng và có phương án khôi phục. Những thao tác đó có thể làm gián đoạn dịch vụ và làm mất dấu vết chẩn đoán.

## 11. Sai lầm thường gặp

- **“Cứ biết IP đích là ARP/NDP IP đó.”** Sai khi đích ở xa: máy phân giải MAC của **next hop** theo route.
- **“IPv6 dùng ARP như IPv4.”** Sai: IPv6 dùng **ICMPv6 Neighbor Discovery**.
- **“Multicast có nghĩa không bị giả mạo.”** Sai: multicast thay đổi cách phân phối bản tin; xác thực nguồn vẫn là vấn đề riêng.
- **“Chặn ICMPv6 giúp mạng an toàn hơn trong mọi trường hợp.”** Sai: nhiều phần cốt lõi của IPv6 phụ thuộc ICMPv6.
- **“DAD chứng minh thiết bị là chủ IP.”** Sai: DAD tìm xung đột, không có xác thực quyền sở hữu.
- **“Dùng DHCPv6 thì không cần RA.”** Không đúng với cách thiết lập default router IPv6 thông thường.
- **“Mọi thay đổi MAC của gateway là tấn công.”** Có thể do failover, Proxy ARP hoặc bảo trì; cần xác thực với sơ đồ hạ tầng.
- **“Chỉ cần DAI là bảo vệ được dual stack.”** DAI bảo vệ ARP của IPv4; IPv6 cần các chính sách first-hop riêng.

## 12. Tự kiểm tra kiến thức

1. Nếu `192.0.2.10/24` gửi gói tới `198.51.100.20` qua `192.0.2.1`, nó cần biết MAC của địa chỉ IPv4 nào trên Ethernet đầu tiên?
2. Tại sao ARP Request thông thường được gửi broadcast nhưng NS phân giải địa chỉ IPv6 thường đi solicited-node multicast?
3. NS của DAD khác NS phân giải địa chỉ thông thường chủ yếu ở điểm nào?
4. Khi host IPv6 thấy RA phát từ một cổng máy trạm, đâu là các bằng chứng cần kiểm tra trước khi áp dụng RA Guard?
5. Đâu là khác biệt giữa `STALE` và `FAILED` trong neighbor cache?
6. Vì sao tắt toàn bộ ICMPv6 có thể khiến website hoạt động chập chờn dù DNS và TCP vẫn được cho phép?

**Gợi ý đối chiếu:** (1) MAC của `192.0.2.1`; (2) multicast chọn nhóm quan tâm thay cho broadcast toàn VLAN; (3) nguồn NS là `::` khi DAD kiểm tra địa chỉ tentative; (4) MAC/cổng nguồn, router hợp lệ, prefix, log và thay đổi hạ tầng; (5) STALE đã biết ánh xạ nhưng cần kiểm tra lại, FAILED là kiểm tra/phân giải thất bại; (6) ND và Packet Too Big là cơ chế cần thiết cho kết nối IPv6.

## 13. Tài liệu chuẩn để học sâu

- **RFC 826:** Ethernet Address Resolution Protocol — nền tảng ARP.
- **RFC 5227:** IPv4 Address Conflict Detection — ARP Probe/Announcement.
- **RFC 4861:** Neighbor Discovery for IP version 6 — RS, RA, NS, NA, Redirect, NUD.
- **RFC 4862:** IPv6 Stateless Address Autoconfiguration — SLAAC và DAD.
- **RFC 3971:** Secure Neighbor Discovery — cơ chế SEND.
- **RFC 6105 / RFC 7113:** RA Guard và các cân nhắc triển khai chống né tránh kiểm tra.
- **RFC 8106:** DNS Configuration trong Router Advertisements.
- **RFC 8981:** Temporary Address Extensions for SLAAC.

Các RFC mô tả chuẩn giao thức; khi triển khai cần thêm tài liệu của hệ điều hành, phiên bản switch và router đang sử dụng để xác nhận chính xác hành vi hỗ trợ.

**Điểm cần ghi nhớ khi thiết kế mạng an toàn:** ARP và ND là lớp nền quyết định máy trạm giao tiếp với ai ở chặng Ethernet đầu tiên. Phải đánh giá đồng thời định tuyến next hop, tính đúng đắn của thông báo trên liên kết, chính sách kiểm soát cổng và bằng chứng giám sát trong cả IPv4 lẫn IPv6.
