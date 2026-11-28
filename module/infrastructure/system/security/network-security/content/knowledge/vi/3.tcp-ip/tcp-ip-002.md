# IPv4 và IPv6

## Mục tiêu học tập

Trong chương **TCP IP**, bài này giúp bạn hiểu địa chỉ IP, cấu trúc gói tin và cách thiết bị giao tiếp qua mạng IPv4/IPv6. Sau khi học, bạn có thể:

1. Giải thích vai trò của IPv4, IPv6 trong bộ giao thức TCP/IP và phân biệt địa chỉ IP với địa chỉ MAC, cổng TCP/UDP, tên miền.
2. Đọc địa chỉ IPv4/IPv6, xác định tiền tố mạng (prefix), phạm vi địa chỉ, mạng con và tuyến đường mặc định.
3. So sánh header, phân mảnh, khám phá hàng xóm, tự động cấu hình, multicast và thông điệp điều khiển của hai phiên bản.
4. Mô tả cách một kết nối đi qua LAN, router, firewall, VPN hoặc hạ tầng đám mây, kể cả môi trường dual-stack.
5. Nhận diện rủi ro giả mạo địa chỉ, cấu hình router sai, bỏ sót IPv6, kiểm soát ICMP quá mức và khai thác lưu lượng nội bộ; chọn biện pháp bảo vệ, giám sát phù hợp.

> **Ý chính:** IPv4 và IPv6 đều cung cấp địa chỉ và chuyển tiếp gói tin ở lớp mạng. Việc một hệ thống sử dụng địa chỉ private, IPv6 hoặc VPN **không tự động** chứng minh danh tính, bảo mật dữ liệu hay quyền truy cập.

## 1. IP nằm ở đâu trong quá trình truyền dữ liệu?

Internet Protocol (IP) là giao thức lớp Internet trong mô hình TCP/IP, tương ứng gần với lớp mạng (Layer 3) trong mô hình OSI. IP chịu trách nhiệm gắn địa chỉ nguồn/đích và hỗ trợ router chuyển gói tin từ mạng này sang mạng khác theo bảng định tuyến.

Trong một yêu cầu HTTPS, các lớp phối hợp như sau:

~~~text
Ứng dụng       HTTP: GET /orders/42
Vận chuyển     TCP: cổng nguồn tạm thời -> cổng đích 443
Mạng           IP: địa chỉ máy khách -> địa chỉ máy chủ
Liên kết       Ethernet/Wi-Fi: MAC nguồn -> MAC đích của chặng hiện tại
Vật lý         Tín hiệu trên cáp/quang/sóng vô tuyến
~~~

- **Tên miền** như `api.example.com` được phân giải thành địa chỉ IP bằng DNS.
- **Địa chỉ IP** xác định điểm đến ở lớp mạng; router dùng tiền tố địa chỉ để chọn chặng tiếp theo.
- **Cổng TCP/UDP** giúp xác định dịch vụ hoặc điểm cuối vận chuyển trên máy.
- **Địa chỉ MAC** phục vụ việc truyền khung trên một liên kết cục bộ, không được giữ nguyên xuyên suốt mọi router.
- **TLS** bảo vệ kết nối ứng dụng/vận chuyển trong những giao thức có sử dụng nó; IP thông thường không mặc định mã hóa payload.

IP là dịch vụ truyền gói theo kiểu **best effort**: không tự bảo đảm gói đến nơi, đúng thứ tự hoặc chỉ đến một lần. TCP bổ sung cơ chế kiểm soát truyền tin phù hợp; UDP không cung cấp cơ chế tin cậy tương đương ở chính lớp vận chuyển. Với bảo mật, phải kết hợp IP cùng firewall, xác thực, mã hóa và giám sát.

## 2. IPv4: 32 bit, dạng thập phân có dấu chấm

IPv4 dùng địa chỉ **32 bit** (4 byte), thường được viết thành bốn số thập phân từ 0 đến 255, phân cách bằng dấu chấm:

~~~text
192.0.2.130

192        0          2          130
11000000 . 00000000 . 00000010 . 10000010
   8 bit      8 bit      8 bit      8 bit
~~~

Tổng số tổ hợp địa chỉ IPv4 là \(2^{32}\), khoảng 4,29 tỷ; không phải tất cả đều dùng được làm địa chỉ unicast toàn cầu vì còn nhiều dải dành riêng cho các mục đích khác nhau. Sự thiếu hụt IPv4 là một động lực quan trọng dẫn tới IPv6.

### 2.1. Prefix/CIDR và mạng con

Ký hiệu **CIDR** (Classless Inter-Domain Routing) dùng dấu gạch chéo và số bit đầu của địa chỉ dành cho tiền tố mạng: `192.0.2.128/27`.

- `/27`: 27 bit là phần mạng; 5 bit còn lại là phần địa chỉ trong mạng con.
- Subnet mask tương ứng: `255.255.255.224`.
- Kích thước khối: \(2^{32-27}=32\) địa chỉ.
- Với mạng con IPv4 truyền thống này, địa chỉ mạng là `192.0.2.128`, địa chỉ broadcast có hướng của subnet là `192.0.2.159`, các địa chỉ host thông thường là `192.0.2.129` đến `192.0.2.158`.

Ví dụ `192.0.2.130/27` và `192.0.2.150/27` thuộc cùng subnet; `192.0.2.170/27` thuộc subnet kế tiếp (`192.0.2.160/27`). Trên Ethernet thông thường, hai máy trong cùng subnet có thể gửi trực tiếp qua liên kết cục bộ nếu không có chính sách ngăn chặn; đi sang mạng khác thường cần gateway/router.

| Prefix IPv4 | Tổng số địa chỉ trong khối | Host dùng được trong subnet kiểu phổ biến |
| --- | ---: | ---: |
| `/24` | 256 | 254 |
| `/25` | 128 | 126 |
| `/26` | 64 | 62 |
| `/27` | 32 | 30 |
| `/30` | 4 | 2 |

Số host bằng \(2^{(32-p)}-2\) áp dụng cho các subnet IPv4 truyền thống với một địa chỉ mạng và một địa chỉ broadcast. **Không dùng công thức đó một cách máy móc** cho các trường hợp đặc biệt như `/31` trên liên kết điểm-điểm hoặc `/32` định danh một địa chỉ/host route.

### 2.2. Các phạm vi IPv4 cần nhận diện

| Địa chỉ/dải | Ý nghĩa | Lưu ý khi bảo vệ mạng |
| --- | --- | --- |
| `10.0.0.0/8` | Private IPv4 | Thường dùng trong mạng nội bộ, không tự chứng minh thiết bị đáng tin |
| `172.16.0.0/12` | Private IPv4 | Không phải toàn bộ dải `172.0.0.0/8` là private |
| `192.168.0.0/16` | Private IPv4 | Có thể trùng địa chỉ giữa các site/VPN |
| `127.0.0.0/8` | Loopback | Dành cho giao tiếp tại máy; thường gặp `127.0.0.1` |
| `169.254.0.0/16` | IPv4 link-local | Dùng trên liên kết cục bộ, không định tuyến qua Internet |
| `224.0.0.0/4` | Multicast IPv4 | Phục vụ nhóm nhận, cần kiểm soát theo giao thức |
| `0.0.0.0` | Địa chỉ không xác định trong nhiều ngữ cảnh | Không đồng nghĩa địa chỉ của một máy chủ cụ thể |
| `255.255.255.255` | Limited broadcast | Chỉ phục vụ phạm vi liên kết cục bộ phù hợp |
| `192.0.2.0/24` | Dải tài liệu (TEST-NET-1) | Dùng làm ví dụ, không sử dụng như IP public vận hành |

Địa chỉ **private** (RFC 1918) không được định tuyến công khai trên Internet theo cách thông thường, nhưng có thể đi qua VPN, các tuyến nội bộ, kết nối site-to-site hoặc bị cấu hình mở nhầm. Chúng là công cụ quản lý địa chỉ, **không phải cơ chế xác thực**.

### 2.3. IPv4, ARP và gateway

Khi máy A cần gửi gói tới một IP cùng subnet trên Ethernet, nó dùng **ARP (Address Resolution Protocol)** để tìm MAC tương ứng, sau đó gửi khung. Nếu đích nằm ngoài subnet, máy A thường giải quyết MAC của **next-hop/default gateway**, rồi gửi gói IP (địa chỉ IP đích vẫn là đích cuối, trừ khi có NAT).

ARP không có xác thực mạnh theo thiết kế truyền thống, nên trên một phân đoạn Ethernet có thể tồn tại tấn công giả mạo ARP, gây nghe lén hoặc gián đoạn. Những kiểm soát như phân đoạn, Dynamic ARP Inspection khi hỗ trợ, kiểm soát thiết bị truy cập và mã hóa lưu lượng giúp giảm rủi ro.

## 3. IPv6: 128 bit, dạng thập lục phân có dấu hai chấm

IPv6 dùng địa chỉ **128 bit**, thường hiển thị thành tám nhóm, mỗi nhóm 16 bit (bốn chữ số hệ 16):

~~~text
2001:0db8:1234:0001:0000:0000:0000:0042
     \_/
      Nhóm 16 bit (hextet)

Viết gọn: 2001:db8:1234:1::42
~~~

Quy tắc rút gọn:

1. Có thể bỏ các số 0 ở đầu mỗi nhóm: `0db8` thành `db8`.
2. Có thể thay một chuỗi gồm **một hoặc nhiều nhóm 0000 liên tiếp** bằng `::`, nhưng chỉ dùng `::` **một lần trong một địa chỉ**.
3. Khi chuẩn hóa cách viết, nên nén chuỗi nhóm 0 dài nhất; nếu có nhiều chuỗi dài bằng nhau thì ưu tiên chuỗi xuất hiện đầu tiên, và thường không dùng `::` để nén một nhóm 0 đơn lẻ.

Vì `::` có thể đại diện cho nhiều nhóm 0, các chuỗi `2001:db8::1` và `2001:0db8:0:0:0:0:0:1` là cùng địa chỉ. Tổng không gian địa chỉ lý thuyết là \(2^{128}\); một địa chỉ IPv6 không tương đương một cổng ứng dụng hoặc một định danh người dùng.

### 3.1. Prefix IPv6

IPv6 cũng dùng CIDR: `2001:db8:1234:1::42/64`. Trong ví dụ này, 64 bit đầu xác định prefix `2001:db8:1234:1::/64`; 64 bit sau là phần còn lại của địa chỉ giao diện theo cách phân chia phổ biến.

`/64` là kích thước subnet rất phổ biến cho LAN IPv6 dùng SLAAC, nhưng không có nghĩa tất cả các tuyến, liên kết hoặc địa chỉ IPv6 đều phải dùng `/64`. Chẳng hạn, host route có thể là `/128`, liên kết điểm-điểm có thể được thiết kế theo `/127`, và một tổ chức có thể nhận một khối tổng hợp `/48` hoặc `/56` để chia nhiều subnet.

Ví dụ: từ `2001:db8:abcd:1200::/56` có thể tạo \(2^{64-56}=256\) subnet `/64`, có prefix từ `2001:db8:abcd:1200::/64` đến `2001:db8:abcd:12ff::/64`. Đây là **chia prefix**, không phải cấp phát 256 địa chỉ máy.

Địa chỉ IPv6 không có địa chỉ broadcast dạng IPv4 dành riêng cho mỗi subnet; IPv6 dùng **multicast** cho các chức năng phù hợp. Vì vậy cũng không lấy công thức “trừ hai địa chỉ mạng/broadcast” của IPv4 để tính host IPv6.

### 3.2. Các loại và phạm vi IPv6

| Địa chỉ/dải | Vai trò | Đặc điểm cần biết |
| --- | --- | --- |
| `2000::/3` | Vùng địa chỉ global unicast phổ biến hiện nay | Phục vụ định tuyến toàn cầu khi được cấp và công bố phù hợp |
| `fc00::/7` | Unique Local Address (ULA) | Thường dùng nội bộ; trong thực hành hay gặp `fdxx:...` với prefix tạo phù hợp |
| `fe80::/10` | Link-local | Giao tiếp trên một liên kết; không được router chuyển tiếp ngoài liên kết |
| `ff00::/8` | Multicast | Gửi cho nhóm nhận theo phạm vi được quy định |
| `::1/128` | Loopback | Tương tự mục đích `127.0.0.1` |
| `::/128` | Unspecified | Chưa xác định địa chỉ nguồn trong những ngữ cảnh thích hợp |
| `2001:db8::/32` | Prefix tài liệu | Dùng để giảng dạy/ví dụ; không phải mạng Internet thật |

**Link-local** đặc biệt quan trọng với IPv6. Nhiều quá trình như Neighbor Discovery và học router mặc định sử dụng địa chỉ nguồn link-local. Một địa chỉ `fe80::...` có thể trùng trên các liên kết độc lập; hệ điều hành có thể cần chỉ rõ interface/zone, ví dụ `fe80::1%eth0` trên một hệ phù hợp hoặc chỉ số giao diện theo quy ước của hệ điều hành.

**ULA không tương đương firewall:** dù không nhằm được định tuyến trên Internet công cộng, ULA vẫn có thể đi qua các mạng tổ chức hoặc liên kết VPN. Quyền truy cập phải dựa trên chính sách cụ thể.

**Địa chỉ IPv6 không nhất thiết lộ MAC:** nhiều thiết bị hiện đại dùng địa chỉ ổn định sinh theo cơ chế khác MAC và/hoặc địa chỉ tạm thời cho kết nối đi ra. Không nên suy luận danh tính thiết bị chỉ từ phần 64 bit sau của địa chỉ IPv6.

### 3.3. Unicast, multicast và anycast

- **Unicast:** gửi đến một giao diện/điểm đích theo định tuyến thông thường.
- **Multicast:** gửi đến một nhóm giao diện đã tham gia nhóm tương ứng. IPv6 dùng multicast cho các chức năng như Neighbor Discovery thay vì broadcast.
- **Anycast:** nhiều điểm phục vụ chia sẻ cùng địa chỉ; định tuyến đưa gói đến một điểm theo cấu trúc mạng. Cả IPv4 và IPv6 đều có thể dùng mô hình anycast, ví dụ với hạ tầng DNS hoặc dịch vụ phân tán.

Anycast không tự bảo đảm cân bằng tải theo yêu cầu ứng dụng hay chuyển đổi phiên không gián đoạn. Cần tính tới chính sách định tuyến, trạng thái phiên và cách xử lý lỗi.

## 4. So sánh header IPv4 và IPv6

| Thành phần | IPv4 | IPv6 | Ý nghĩa vận hành/bảo mật |
| --- | --- | --- | --- |
| Độ dài địa chỉ | 32 bit | 128 bit | ACL, log, tập luật và hệ thống quan sát phải hiểu cả hai |
| Header cơ bản | Thường 20 byte, có thể dài hơn do options | Cố định 40 byte | IPv6 dùng extension headers khi cần |
| Thông số giới hạn chặng | TTL | Hop Limit | Router giảm giá trị để chống vòng lặp vô hạn |
| Xác định giao thức tiếp | Protocol | Next Header | Cho biết TCP, UDP, ICMP hoặc extension header tiếp theo |
| Kiểm tra lỗi header | Có checksum header IPv4 | Không có checksum riêng cho header IPv6 | Không đồng nghĩa IPv6 không có cơ chế phát hiện lỗi nào ở lớp khác |
| Phân mảnh | Nguồn và, trong tình huống cho phép, router trung gian có thể phân mảnh | Router không phân mảnh; nguồn có thể dùng Fragment extension header | Thiết bị bảo mật phải xử lý đúng phân mảnh/extension headers |
| Phân giải láng giềng trên Ethernet | ARP | Neighbor Discovery qua ICMPv6 | Cần kiểm soát giả mạo theo cơ chế của từng phiên bản |
| Broadcast | Có | Không có broadcast theo kiểu IPv4 | IPv6 dùng multicast cho nhiều tác vụ nội bộ |
| Tự cấu hình phổ biến | DHCPv4 hoặc cấu hình tĩnh | SLAAC, DHCPv6 hoặc cấu hình tĩnh theo thiết kế | Cần kiểm soát nguồn cấp thông tin cấu hình |

Header IPv6 cố định giúp thiết bị xác định trường cơ bản dễ dàng hơn, nhưng **không mặc nhiên làm việc lọc gói đơn giản hơn**. Gói IPv6 có thể chứa nhiều extension headers; một số thiết bị trung gian hoặc công cụ giám sát xử lý chúng không đầy đủ.

### 4.1. Sơ đồ đường đi của một gói tin

~~~mermaid
flowchart LR
    H["Máy khách<br/>IPv4 hoặc IPv6"] -->|Gói IP| L["LAN / Wi-Fi"]
    L --> R["Gateway / Router"]
    R --> F["Firewall / VPN / WAN"]
    F --> S["Mạng dịch vụ"]
    S --> A["API hoặc máy chủ"]
    R -. "Định tuyến theo prefix" .-> F
~~~

Tại mỗi chặng, router chọn tuyến và giảm TTL/Hop Limit. **Địa chỉ IP nguồn/đích thông thường được giữ qua các chặng định tuyến**; địa chỉ liên kết (MAC) thay đổi theo từng chặng. NAT hoặc các cơ chế dịch địa chỉ có thể sửa thông tin IP khi được triển khai.

Một firewall có thể đưa ra quyết định dựa trên họ địa chỉ, địa chỉ nguồn/đích, giao thức, cổng, trạng thái kết nối, zone và các tín hiệu ứng dụng khi được hỗ trợ. Không nên giả định rule IPv4 `0.0.0.0/0` sẽ bao phủ IPv6 `::/0`.

### 4.2. MTU, phân mảnh và Path MTU Discovery

**MTU (Maximum Transmission Unit)** giới hạn kích thước gói có thể đi qua một liên kết ở cấp tương ứng. Ví dụ, Ethernet thường có MTU 1500 byte ở lớp IP theo cấu hình phổ biến; VPN/tunnel có thể làm giảm MTU hữu dụng.

- Với **IPv4**, router có thể phân mảnh gói quá lớn nếu gói cho phép; khi cờ **DF (Don't Fragment)** được đặt và không thể chuyển tiếp, router có thể gửi ICMP thông báo cần phân mảnh với MTU phù hợp. Nhiều ứng dụng dựa vào Path MTU Discovery để tránh phân mảnh.
- Với **IPv6**, router **không** phân mảnh gói; khi gói vượt MTU chặng tiếp, router loại bỏ và gửi ICMPv6 **Packet Too Big** về nguồn. Nguồn phải điều chỉnh kích thước gói, hoặc dùng cơ chế xử lý phù hợp ở đầu nguồn. IPv6 yêu cầu mỗi liên kết hỗ trợ truyền tải gói IPv6 ít nhất 1280 byte, có thể thông qua cơ chế phù hợp của lớp dưới.
- Các gói bị phân mảnh gây khó khăn cho theo dõi phiên, lọc ACL và IDS/IPS nếu những thành phần không tái lắp/diễn giải được đúng nội dung.

**Sai lầm nguy hiểm:** chặn toàn bộ ICMP vì nghĩ đó chỉ là ping. ICMPv4/ICMPv6 chứa thông báo lỗi và điều khiển thiết yếu, trong đó ICMPv6 còn là nền tảng của Neighbor Discovery. Chặn bừa bãi có thể gây hiện tượng kết nối được thiết lập nhưng tải dữ liệu lớn bị treo hoặc IPv6 không tự cấu hình được.

## 5. Thiết bị tìm đường đi và láng giềng như thế nào?

### 5.1. Hai bước độc lập: chọn next-hop và tìm địa chỉ liên kết

Ví dụ máy A có:

~~~text
IPv4: 192.0.2.130/27
IPv4 gateway: 192.0.2.129

IPv6: 2001:db8:10:20::130/64
IPv6 gateway: fe80::1  (trên đúng interface)
~~~

Nếu máy A gửi tới `192.0.2.140`, nó thấy đích thuộc subnet IPv4 của mình nên cần ARP để tìm địa chỉ MAC của đích. Nếu gửi tới `198.51.100.10`, nó cần MAC của gateway `192.0.2.129`.

Với IPv6, A dùng Neighbor Discovery để xác định địa chỉ liên kết của đích cùng link hoặc của router mặc định. Router IPv6 mặc định thường được biểu diễn bằng **địa chỉ link-local**; điều này hợp lệ dù đích cuối là một địa chỉ global unicast.

~~~text
Tra cứu bảng định tuyến theo prefix đích
        |
        +-- Đích on-link -> tìm MAC của đích (ARP / NDP)
        |
        +-- Đích off-link -> chọn next-hop -> tìm MAC của next-hop
        |
        +-- Không có tuyến phù hợp -> không chuyển được gói
~~~

**Longest Prefix Match**: khi nhiều tuyến khớp một địa chỉ, router chọn tuyến có prefix cụ thể nhất trong số các tuyến áp dụng, sau khi xét các quy tắc định tuyến liên quan. Ví dụ, tuyến `2001:db8:10:20::/64` cụ thể hơn `2001:db8::/32`; tuyến mặc định `::/0` khớp mọi địa chỉ IPv6 khi không có tuyến cụ thể hơn.

### 5.2. ARP và Neighbor Discovery không giống nhau

IPv4 dùng ARP trên Ethernet để ánh xạ IPv4 sang MAC. IPv6 dùng **Neighbor Discovery Protocol (NDP)** dựa trên ICMPv6, với những thông điệp phổ biến:

| Thông điệp ICMPv6 | Tác dụng |
| --- | --- |
| Router Solicitation (RS) | Host hỏi để nhận thông tin router |
| Router Advertisement (RA) | Router công bố prefix, thời hạn, thông tin liên quan đến cấu hình và định tuyến mặc định |
| Neighbor Solicitation (NS) | Tìm địa chỉ liên kết của neighbor; cũng dùng trong Duplicate Address Detection |
| Neighbor Advertisement (NA) | Trả lời/giới thiệu thông tin neighbor |
| Redirect | Router thông báo đường next-hop tốt hơn cho những trường hợp phù hợp |

NDP dùng các nhóm multicast IPv6 theo cơ chế giao thức, thay vì broadcast ARP. **NDP không được xác thực bằng mật mã theo mặc định**, nên một thiết bị cùng liên kết có thể cố giả mạo RA hoặc NA nếu lớp mạng không có kiểm soát thích hợp.

## 6. Cấp địa chỉ và cấu hình host

### 6.1. IPv4: thường qua DHCPv4

Một máy IPv4 thường nhận địa chỉ, prefix/mask, gateway, DNS resolver và thời hạn thuê qua DHCPv4; hoặc các thông số được cấu hình tĩnh. Trong môi trường Ethernet chung, máy khách không nên tự coi mọi câu trả lời DHCP là tin cậy. DHCP snooping trên thiết bị hỗ trợ có thể hạn chế nguồn cấp phát DHCP trái phép.

### 6.2. IPv6: SLAAC, RA và DHCPv6

IPv6 cho phép nhiều mô hình cấu hình, không nhất thiết giống IPv4:

1. Host có địa chỉ link-local để giao tiếp cục bộ và tham gia NDP.
2. Host nhận **Router Advertisement** từ router, chứa thông tin prefix cùng các cờ/hướng dẫn áp dụng cho cấu hình.
3. Nếu prefix cho phép tự động cấu hình, host có thể dùng **SLAAC (Stateless Address Autoconfiguration)** để tạo địa chỉ cho giao diện, đồng thời chạy Duplicate Address Detection.
4. Host có thể lấy thông tin cấu hình bổ sung qua RA (ví dụ DNS resolver qua RDNSS khi hệ điều hành hỗ trợ) hoặc DHCPv6, tùy mạng và thiết bị.
5. DHCPv6 có thể cấp địa chỉ hay thông tin cấu hình; **gateway mặc định trong thiết kế IPv6 thông dụng được học qua RA, không phải tùy chọn router kiểu DHCPv4**.

Một thiết bị có thể đồng thời sở hữu nhiều địa chỉ IPv6 trên cùng interface: link-local, địa chỉ global/ULA ổn định và địa chỉ tạm thời nhằm giảm theo dõi khi kết nối ra ngoài. Điều đó ảnh hưởng đến log, ACL và phương pháp nhận diện thiết bị.

~~~mermaid
sequenceDiagram
    participant H as Host IPv6
    participant R as Router trên LAN
    participant N as Neighbor
    H->>H: Có địa chỉ link-local, thực hiện DAD
    H->>R: Router Solicitation (nếu cần)
    R-->>H: Router Advertisement (prefix, thông tin định tuyến)
    H->>H: SLAAC hoặc cấu hình theo chính sách mạng
    H->>N: Neighbor Solicitation (khi cần gửi on-link)
    N-->>H: Neighbor Advertisement
~~~

Để bảo vệ hạ tầng nội bộ, kiểm soát các cổng được phép gửi RA và DHCPv6 trên switch khi thiết bị hỗ trợ (RA Guard, DHCPv6 Guard), quản lý router hợp lệ và giám sát việc thay đổi default route. Các cơ chế lớp 2 này cần kiểm tra khả năng triển khai thực tế và không thay thế xác thực/ủy quyền ứng dụng.

## 7. IPv4 và IPv6 cùng tồn tại như thế nào?

IPv4 và IPv6 là **hai giao thức lớp mạng riêng**. Host chỉ có IPv4 không thể trực tiếp trao đổi gói IPv6 với host chỉ có IPv6 nếu không có cơ chế trung gian phù hợp.

### 7.1. Dual-stack

Trong **dual-stack**, máy, hệ điều hành, mạng và dịch vụ có thể hỗ trợ cả hai họ địa chỉ. DNS có thể cung cấp:

~~~dns
; Ví dụ minh họa, không phải địa chỉ của dịch vụ đang vận hành
api.example.com. IN A     192.0.2.50
api.example.com. IN AAAA  2001:db8:20::50
~~~

Máy khách chọn kết nối IPv4 hoặc IPv6 theo chính sách chọn địa chỉ và khả năng kết nối thực tế; nhiều ứng dụng triển khai cơ chế thử các đường kết nối để tránh phải chờ một đường bị lỗi. Không nên giả định có bản ghi AAAA thì mọi truy cập chắc chắn đi qua IPv6, hoặc ngược lại.

**Rủi ro phổ biến:** firewall chỉ giới hạn TCP/443 cho IPv4 nhưng IPv6 được cho phép rộng hơn; ứng dụng có địa chỉ IPv6 global và xuất hiện trước Internet dù quản trị viên chỉ nghĩ về NAT IPv4. Dual-stack đòi hỏi **hai bộ kiểm soát tương ứng** về truy cập, logging, giám sát và kiểm tra bề mặt tấn công.

### 7.2. Tunnel và dịch giao thức

| Phương án | Mục đích | Giới hạn/cần kiểm soát |
| --- | --- | --- |
| Dual-stack | Chạy song song IPv4 và IPv6 | Quản lý đồng nhất hai tập tuyến, firewall, DNS, log |
| IPv6-over-IPv4 hoặc IPv4-over-IPv6 tunnel | Mang gói của một họ địa chỉ qua hạ tầng họ còn lại | Kiểm soát endpoint, MTU, encapsulation, tuyến và chính sách bảo mật |
| NAT64 + DNS64 | Cho phép máy khách IPv6-only truy cập một số dịch vụ IPv4 qua dịch địa chỉ/giao thức | Ứng dụng dùng IP literal hoặc giao thức đặc thù có thể gặp vấn đề; cần giám sát điểm dịch |
| 464XLAT | Hỗ trợ ứng dụng IPv4 trên một mạng truy cập chỉ có IPv6 với cơ chế dịch phù hợp | Tăng độ phức tạp vận hành, phụ thuộc hệ thống triển khai |

**NAT44** thường gặp trong IPv4 chuyển địa chỉ private sang địa chỉ dùng ở mạng khác. **NAT không phải firewall**: việc dịch địa chỉ hoặc cổng không thay thế quy tắc cho phép/từ chối, kiểm tra danh tính hay mã hóa. IPv6 không đòi NAT để giao tiếp giữa các mạng sử dụng global unicast; vẫn cần firewall và chính sách ingress/egress.

**VPN cũng cần kiểm tra theo cả hai họ địa chỉ.** Ví dụ một VPN chỉ đẩy route IPv4 vào tunnel nhưng hệ điều hành vẫn có đường IPv6 trực tiếp; truy cập IPv6 có thể không đi qua cùng chính sách VPN. Thiết kế nên xác định rõ mạng nào được phép qua tunnel, đường phân giải DNS, đường đi IPv4/IPv6 và cơ chế ngăn truy cập ngoài phạm vi mong muốn.

## 8. Góc nhìn bảo mật: các rủi ro thực tế

### 8.1. Giả mạo địa chỉ nguồn và điều khiển mạng

Vì địa chỉ nguồn IP không tự chứng minh danh tính của bên gửi, một hệ thống chỉ cho phép truy cập vì “IP trong mạng nội bộ” có thể bị lạm dụng. Một số hành vi giả mạo trực tiếp bị hạn chế bởi khả năng nhận phản hồi hay trạng thái phiên, nhưng nguyên tắc đúng vẫn là **không dùng IP nguồn làm yếu tố xác thực duy nhất**.

Các biện pháp:

- **Ingress/egress filtering** và kiểm tra hợp lệ nguồn theo kết cấu mạng để chặn gói có địa chỉ nguồn không thuộc vùng được phép; uRPF có thể hữu ích với điều kiện phù hợp, nhưng phải xét định tuyến bất đối xứng.
- **802.1X/NAC** kiểm soát thiết bị tham gia mạng và vùng mà thiết bị được cấp.
- **ARP inspection/DHCP snooping** trên IPv4 và **RA Guard/DHCPv6 Guard**, kiểm soát NDP trên IPv6 khi hạ tầng hỗ trợ.
- **Xác thực và ủy quyền ở dịch vụ**: TLS/mTLS khi phù hợp, token và quyền theo vai trò/tài nguyên, không tin cậy chỉ dựa trên vị trí subnet.

### 8.2. Rogue Router Advertisement trên IPv6

Một máy ở cùng LAN gửi RA giả với thông số router hấp dẫn có thể khiến một số host học sai default route, DNS hoặc prefix, tùy thiết bị và chính sách chấp nhận RA. Hậu quả có thể là mất kết nối, chuyển lưu lượng qua kẻ tấn công hoặc bị chuyển hướng đến DNS ngoài dự kiến.

Phòng vệ theo lớp gồm: chỉ router được quản lý mới có quyền phát RA ở cổng phù hợp; thiết lập RA Guard theo khả năng switch; kiểm soát cổng truy cập; giám sát sự xuất hiện router/prefix mới; và dùng TLS kiểm tra chứng chỉ để hạn chế tác hại của chuyển hướng lưu lượng. Phải thử nghiệm thực tế vì không phải mọi cơ chế RA Guard đều bao phủ mọi kiểu gói/phần mở rộng trên mọi thiết bị.

### 8.3. IPv6 trở thành đường vượt chính sách IPv4

Đội vận hành có thể tập trung vào `iptables`/quy tắc IPv4, NAT44 và log IPv4 mà quên IPv6 đang hoạt động trên máy. Kẻ tấn công hoặc một dịch vụ cấu hình sai có thể tiếp cận đường IPv6 còn mở. Cách kiểm tra đúng là **kiểm kê cả IPv4 lẫn IPv6**, cả địa chỉ lắng nghe của dịch vụ, tuyến, firewall, DNS và mạng ảo.

Ví dụ:

~~~text
Quy định bảo mật: Chỉ gateway được gọi API quản trị qua TCP/8443

Rule IPv4: ALLOW gateway-v4 -> admin-api-v4 TCP/8443
           DENY  any-v4     -> admin-api-v4 TCP/8443

Rule IPv6: ALLOW gateway-v6 -> admin-api-v6 TCP/8443
           DENY  any-v6     -> admin-api-v6 TCP/8443

API: kiểm tra danh tính và quyền quản trị trên cả hai đường.
~~~

Đây là **policy minh họa**, không phải cú pháp của một sản phẩm firewall cụ thể. Trong môi trường thật, cần xét tiếp IPv6 link-local, ICMPv6 thiết yếu, đường quản trị, mạng container và trường hợp gateway có nhiều địa chỉ.

### 8.4. Phân mảnh, extension headers và IDS/IPS

Đường đi xử lý gói có thể phức tạp khi gói IPv4 phân mảnh hoặc IPv6 dùng Fragment/extension headers. Những khác biệt giữa cách firewall, IDS và đích xử lý gói có thể làm giảm khả năng quan sát hay tạo cơ hội né kiểm tra trên thiết bị cấu hình kém.

Giải pháp là dùng thiết bị hỗ trợ các chuẩn hiện hành và có chính sách xử lý rõ ràng cho extension headers, phân mảnh, fragment nhỏ/bất thường, nguồn gói không hợp lệ; cập nhật firmware/phần mềm và thử nghiệm không làm gián đoạn lưu lượng hợp lệ. **Không tùy tiện chặn toàn bộ extension headers hoặc ICMPv6** khi chưa đánh giá tác động.

### 8.5. Không gian IPv6 lớn không đồng nghĩa không thể tìm thấy máy

Việc quét tuần tự toàn bộ một subnet IPv6 `/64` thường không thực tế, nhưng attacker có thể tìm địa chỉ qua DNS AAAA, nhật ký rò rỉ, tên dịch vụ dự đoán được, địa chỉ đặt thủ công, thông tin mạng cục bộ hoặc thông tin ứng dụng. Phòng vệ cần dựa vào phân đoạn và chính sách, **không dựa vào kỳ vọng rằng địa chỉ IPv6 khó đoán**.

### 8.6. DNS, mã hóa và danh tính

DNS bản ghi **A** ánh xạ tên miền sang IPv4; **AAAA** sang IPv6. Cả hai cần được quản lý trong inventory và đánh giá thay đổi. DNS thông thường không tự bảo đảm kết nối đến một tên miền là an toàn; DNSSEC có thể xác thực tính toàn vẹn/xuất xứ của dữ liệu DNS được ký trong chuỗi tin cậy, nhưng không thay thế HTTPS/TLS.

TLS bảo vệ kết nối ở lớp ứng dụng/vận chuyển phù hợp đối với cả IPv4 và IPv6. **IPv6 không tự động mã hóa mọi gói tin bằng IPsec**; IPsec là bộ cơ chế có thể được sử dụng khi triển khai, với chính sách và quản lý khóa cụ thể.

## 9. Áp dụng vào kiến trúc mạng an toàn

Giả sử doanh nghiệp có bốn vùng: người dùng, ứng dụng, dữ liệu và khách. Đội ngũ cần triển khai cả IPv4 và IPv6:

~~~mermaid
flowchart TB
    U["VLAN nhân viên<br/>IPv4 + IPv6"] --> FW["Firewall phân vùng<br/>ACL IPv4 và IPv6"]
    G["Wi-Fi khách<br/>IPv4 + IPv6"] --> GF["Chính sách khách<br/>Chỉ tài nguyên được phép"]
    GF --> NET["Internet"]
    FW --> API["API / Gateway<br/>TLS, xác thực, ủy quyền"]
    API --> DB["Vùng CSDL<br/>Chỉ ứng dụng được kết nối"]
    FW --> LOG["NetFlow / IPFIX / Log"]
    API --> LOG
    DB --> LOG
~~~

Một bảng luồng chính sách nên ghi **đủ hai họ địa chỉ**, kể cả lúc mạng được coi là private:

| Nguồn | Đích | Quy tắc IPv4/IPv6 | Kiểm soát bổ sung |
| --- | --- | --- | --- |
| Wi-Fi khách | Subnet quản trị và CSDL | Deny cho cả IPv4 và IPv6 | Cô lập layer 2, kiểm soát DNS/RA của vùng khách |
| Nhân viên | API gateway | Chỉ cổng dịch vụ cần thiết trên mỗi họ địa chỉ | MFA khi phù hợp; API phân quyền |
| Nhân viên | CSDL | Deny trực tiếp trên cả hai họ | Theo dõi kết nối bị từ chối |
| API | CSDL cần thiết | Allow đúng đích và cổng của từng họ | TLS, tài khoản ứng dụng, quyền DB tối thiểu |
| Ứng dụng | DNS resolver được quản lý | Allow dịch vụ phân giải phù hợp | Chính sách DNS, ghi log và phát hiện bất thường |
| Máy quản trị | Kênh quản trị | Chỉ qua điểm truy cập được ủy quyền | Xác thực mạnh, ghi vết và giới hạn phiên |

### 9.1. Những điều kiện tối thiểu cho thiết kế tốt

1. **Kiểm kê:** ghi nhận subnet/prefix, VLAN/VRF/VPC, IPv4/IPv6 address, tuyến, gateway, DNS, endpoint VPN, địa chỉ public và tài khoản sở hữu.
2. **Phân đoạn:** xác định những luồng east–west thực sự cần; cấu hình deny-by-default tại ranh giới thích hợp và nêu ngoại lệ được phê duyệt.
3. **Kiểm soát lớp 2:** bảo vệ DHCP, ARP, RA, NDP theo thiết bị và môi trường; tách Wi-Fi khách và thiết bị ít tin cậy.
4. **Kiểm soát lớp 3/4:** chống giả mạo địa chỉ nguồn, áp rule IPv4 và IPv6 nhất quán, giới hạn cổng/protocol và luồng VPN.
5. **Kiểm soát ứng dụng:** TLS, xác thực, ủy quyền theo tài nguyên và quyền tối thiểu; không dùng IP private làm bằng chứng đủ cho quyền nghiệp vụ.
6. **Giám sát và ứng cứu:** thu log định tuyến, firewall, DNS, VPN, DHCP/RA khi phù hợp và thiết bị đầu cuối; đặt cảnh báo cho cấu hình thay đổi và lưu lượng bất thường.

**Lưu ý hạ tầng đám mây:** VPC/VNet và security group/NSG có thể hỗ trợ IPv4/IPv6 theo khả năng của từng nền tảng; quy tắc, tuyến mặc định và địa chỉ công cộng có thể hoạt động khác nhau. Không suy đoán rằng đã bật một rule IPv4 thì IPv6 cũng được bảo vệ. Cần xác minh cấu hình thực tế của nhà cung cấp.

## 10. Chẩn đoán và xác minh kết nối

Những lệnh sau dùng để **quan sát cấu hình và kiểm tra đến endpoint mà bạn có quyền sử dụng**. Tên interface và khả năng lệnh có thể khác theo hệ điều hành, phiên bản và quyền người dùng.

### Linux

~~~bash
# Xem địa chỉ và prefix đã cấu hình trên interface
ip -4 address show
ip -6 address show

# Xem tuyến IPv4/IPv6 và router mặc định
ip -4 route show
ip -6 route show

# Xem neighbor cache (ARP/NDP) theo hai họ
ip -4 neigh show
ip -6 neigh show

# Kiểm tra đường kết nối tới địa chỉ tài liệu nếu có môi trường lab riêng
ping -4 -c 2 192.0.2.1
ping -6 -c 2 2001:db8::1

# Kiểm tra bản ghi DNS khi có công cụ dig
dig A example.com
dig AAAA example.com
~~~

Các địa chỉ `192.0.2.1` và `2001:db8::1` là **địa chỉ ví dụ**, sẽ không phản hồi trên Internet thông thường; hãy thay bằng đích được cấp trong lab. `ping` gửi ICMP Echo; thất bại không tự chứng minh dịch vụ TCP/UDP không hoạt động vì ICMP Echo có thể bị chặn.

### Windows (PowerShell)

~~~powershell
# Xem các địa chỉ được cấp và thông tin adapter
Get-NetIPAddress
Get-NetIPConfiguration

# Xem bảng định tuyến theo họ địa chỉ
Get-NetRoute -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv6

# Xem neighbor cache
Get-NetNeighbor

# Kiểm tra tên miền có bản ghi IPv4 và IPv6
Resolve-DnsName example.com -Type A
Resolve-DnsName example.com -Type AAAA

# Ping qua từng họ địa chỉ tới đích có quyền kiểm tra
ping -4 example.com
ping -6 example.com
~~~

### Đọc kết quả theo chuỗi nguyên nhân

Nếu máy có IPv6 nhưng không tới được dịch vụ, lần lượt hỏi:

1. Giao diện có địa chỉ IPv6 đúng scope, prefix và trạng thái không?
2. Có tuyến phù hợp hoặc default route `::/0` không? RA có xuất phát từ router đúng không?
3. Neighbor Discovery có giải được next-hop trên đúng interface không?
4. Firewall tại host, mạng trung gian và dịch vụ có cho phép gói phù hợp không?
5. ICMPv6 thiết yếu (đặc biệt Packet Too Big và Neighbor Discovery trên liên kết) có bị chặn sai không?
6. DNS AAAA có trỏ đến đích mong muốn, và dịch vụ có lắng nghe trên địa chỉ IPv6 không?
7. Nếu đường truyền đi qua VPN/tunnel, có vấn đề về route/MTU hoặc chính sách hai họ địa chỉ không?
8. Nếu TCP kết nối được nhưng ứng dụng trả lỗi, đây có thể là vấn đề TLS, xác thực, ủy quyền hoặc ứng dụng, không phải lỗi cấp phát IP.

Đọc bảng định tuyến, neighbor cache, DNS, nhật ký firewall và log ứng dụng theo cùng mốc thời gian giúp phân biệt lỗi **địa chỉ → đường đi → truyền thông → quyền truy cập**.

## 11. Tình huống thực hành: chuyển một API từ IPv4 sang dual-stack

**Bối cảnh:** API nội bộ ban đầu chỉ lắng nghe IPv4, ví dụ `192.0.2.50:443`. Nhóm triển khai bổ sung IPv6 `2001:db8:20::50`, tạo bản ghi AAAA và cho phép truy cập từ VLAN ứng dụng.

**Mục tiêu:** API vẫn đáp ứng khách hàng hợp lệ, nhưng mọi truy cập phải qua gateway và được ủy quyền.

### Phân tích mối đe dọa

| Câu hỏi | Phát hiện có thể xảy ra | Phòng vệ cần kiểm chứng |
| --- | --- | --- |
| Ai biết địa chỉ IPv6 mới? | DNS AAAA có thể tiết lộ endpoint | Không dùng tính khó đoán làm phòng vệ chính |
| Có đường vào khác IPv4 không? | Rule IPv6 mặc định rộng hơn rule IPv4 | Đồng bộ chính sách gateway/firewall theo chức năng |
| Ai điều khiển router/prefix ở LAN? | RA giả có thể tạo sai đường đi | Chỉ router đáng tin được phát RA; giám sát thay đổi |
| Token có bị bỏ qua trên IPv6 không? | Endpoint IPv6 đi qua đường ứng dụng khác | Kiểm thử xác thực/ủy quyền đồng nhất |
| Có nhìn thấy sự cố không? | IDS chỉ nhận mirror IPv4 | Bật quan sát/log cho luồng IPv6 và tương quan danh tính |
| Kết nối lớn có lỗi không? | PMTUD bị chặn tại tunnel/firewall | Cho phép ICMPv6 Packet Too Big cần thiết, kiểm thử MTU |

### Bộ tiêu chí chấp nhận

- Client hợp lệ kết nối HTTPS qua A và AAAA tương ứng, với chứng chỉ/TLS được kiểm tra đúng.
- Client không có quyền bị từ chối trên cả hai đường IPv4 và IPv6, dù có thể thiết lập kết nối mạng.
- Máy trong VLAN người dùng không thể kết nối trực tiếp vào cổng quản trị/CSDL ở bất kỳ họ địa chỉ nào.
- Bản ghi firewall/IDS thể hiện được lưu lượng IPv6 đến API; nhật ký ứng dụng ánh xạ tới danh tính yêu cầu.
- Kiểm thử luồng gói lớn qua VPN/tunnel không gặp lỗi MTU/ICMPv6 do chính sách chặn nhầm.
- Thao tác thu hồi quyền áp dụng đồng nhất dù client chuyển từ IPv4 sang IPv6 hoặc ngược lại.

Đây là một ví dụ về cách liên kết **phân tích lưu lượng**, **mô hình hóa mối đe dọa**, **giám sát xâm nhập** và **kiến trúc mạng an toàn** khi đưa IPv6 vào hệ thống đang chạy.

## 12. Lỗi hiểu thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “IPv6 thay IPv4 bằng cách kéo dài địa chỉ; các cơ chế còn lại y hệt.” | IPv6 có header, Neighbor Discovery, SLAAC, ICMPv6 và cách xử lý phân mảnh khác IPv4. |
| “Có địa chỉ private hoặc ULA là an toàn.” | Địa chỉ chỉ biểu thị phạm vi/đường định tuyến; cần xác thực, ủy quyền và phân đoạn. |
| “IPv6 luôn được mã hóa.” | IPv6 không mặc định mã hóa lưu lượng ứng dụng; TLS/IPsec phải được triển khai khi cần. |
| “Chặn hết ICMPv6 để tăng bảo mật.” | Có thể phá Neighbor Discovery và Path MTU Discovery, gây mất hoặc treo kết nối. |
| “NAT thay thế được firewall.” | Dịch địa chỉ khác với kiểm soát quyền và lọc truy cập. |
| “Subnet IPv6 /64 có hai địa chỉ không dùng được giống IPv4.” | IPv6 không có địa chỉ mạng/broadcast tương đương cách tính host IPv4 truyền thống. |
| “Đã bảo vệ IPv4 thì IPv6 cũng sẽ được bảo vệ.” | Cần kiểm tra đầy đủ rule, route, dịch vụ, VPN và log cho IPv6. |
| “Địa chỉ IPv6 dài nên không ai tìm ra máy chủ.” | Có thể tìm qua DNS, cấu hình lộ, địa chỉ có quy luật và thông tin khác. |

## 13. Câu hỏi tự kiểm tra

1. `192.0.2.130/27` thuộc subnet nào, địa chỉ broadcast là gì và có bao nhiêu host dùng được trong trường hợp subnet IPv4 thông thường?
2. Rút gọn địa chỉ `2001:0db8:0000:0000:abcd:0000:0000:0001` sao cho không dùng `::` hai lần. Bạn chọn chuỗi số 0 nào để nén theo cách viết chuẩn hóa?
3. Vì sao gateway IPv6 thường là một địa chỉ link-local dù máy đích nằm ở mạng khác?
4. Nêu khác biệt giữa ARP của IPv4 và NDP của IPv6. Khi một host nhận RA giả, tuyến đi ra có thể thay đổi như thế nào?
5. Điều gì có thể xảy ra nếu firewall chặn toàn bộ ICMPv6, đặc biệt khi máy kết nối qua tunnel có MTU nhỏ?
6. Một API có cả bản ghi A và AAAA nhưng ACL chỉ giới hạn IPv4. Bạn cần kiểm tra những thành phần nào trước khi đưa API ra môi trường vận hành?
7. Hãy phân biệt NAT44, dual-stack và NAT64/DNS64 về mục đích và giới hạn.
8. Địa chỉ nguồn thuộc mạng nội bộ có đủ để một ứng dụng cho phép đọc dữ liệu khách hàng không? Tại sao?
9. Nếu được giao prefix IPv6 `2001:db8:abcd:1200::/56`, có thể chia thành bao nhiêu subnet `/64`?
10. Trong một sự cố kết nối IPv6 lúc được lúc không, hãy sắp xếp trình tự kiểm tra địa chỉ, tuyến, NDP, DNS, ICMPv6/MTU, firewall và quyền ứng dụng.

### Đáp án gợi ý ngắn

1. Subnet `192.0.2.128/27`, broadcast `192.0.2.159`, có 30 địa chỉ host thông thường.
2. `2001:db8::abcd:0:0:1`: có hai chuỗi gồm hai nhóm `0000` bằng nhau, nên ưu tiên nén chuỗi xuất hiện trước.
3. Router và host cùng link có thể dùng địa chỉ `fe80::/10` để thực hiện NDP; link-local không được định tuyến vượt liên kết.
4. ARP ánh xạ IPv4–MAC trên liên kết; NDP dùng ICMPv6 cho khám phá láng giềng/router và nhiều chức năng khác. RA giả có thể khiến host học sai router/prefix tùy chính sách.
5. Có thể gây lỗi Neighbor Discovery hoặc black hole khi gói quá lớn mà nguồn không nhận được Packet Too Big.
6. Kiểm tra địa chỉ lắng nghe, DNS, tuyến, firewall IPv4/IPv6, gateway, TLS, xác thực/ủy quyền và log.
7. NAT44 dịch địa chỉ IPv4; dual-stack chạy song song hai giao thức; NAT64/DNS64 hỗ trợ một số kết nối từ IPv6-only tới IPv4.
8. Không; IP không đủ xác thực chủ thể và ủy quyền với tài nguyên.
9. \(2^8=256\) subnet `/64`.
10. Bắt đầu từ interface/prefix, route/next-hop, neighbor, DNS và khả năng đến đích, rồi kiểm soát ICMPv6/MTU, firewall và xác thực/ủy quyền; có thể điều chỉnh thứ tự theo dấu hiệu lỗi.

## Kết luận

IPv4 và IPv6 cùng giải quyết việc địa chỉ hóa và chuyển tiếp gói tin IP nhưng khác nhau về kích thước địa chỉ, định dạng header, cơ chế khám phá láng giềng, cấu hình host và phân mảnh. Hiểu đúng những khác biệt này giúp triển khai định tuyến, DNS, VPN, firewall, IDS/IPS và hạ tầng đám mây hiệu quả hơn. Để có **mạng an toàn**, hãy bảo vệ và quan sát cả hai họ địa chỉ, giới hạn luồng theo nhu cầu thực, duy trì các thông điệp điều khiển thiết yếu và luôn xác thực, phân quyền ở lớp dịch vụ.
