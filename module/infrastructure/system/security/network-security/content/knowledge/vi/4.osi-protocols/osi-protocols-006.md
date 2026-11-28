# IP packet: cấu trúc, chuyển tiếp và ý nghĩa đối với an ninh mạng

Trong mô hình OSI, **IP (Internet Protocol)** hoạt động ở **tầng 3 — Network**. Đơn vị dữ liệu của IP thường được gọi là **IP packet** (gói IP), hoặc **IP datagram**. Đây là đơn vị mà bộ định tuyến (router) sử dụng để quyết định chuyển lưu lượng đến mạng nào. Trong học phần **SECURITY_NETWORK_SECURITY**, hiểu chính xác gói IP là nền tảng để phân tích lưu lượng, xây dựng phân đoạn mạng, firewall, VPN, IDS/IPS, bảo vệ DNS và các kết nối trên Wi-Fi hoặc hạ tầng đám mây.

Sau bài này, người học có thể:

- Phân biệt gói IP với Ethernet frame, TCP segment và UDP datagram.
- Đọc các trường quan trọng trong header IPv4, IPv6 và suy ra vai trò của chúng.
- Giải thích đường đi của gói tin qua router, MTU, phân mảnh và Path MTU Discovery.
- Nhận diện những rủi ro như giả mạo địa chỉ nguồn, lẩn tránh IDS qua phân mảnh và lọc sai lưu lượng ICMP.
- Đọc gói tin bằng Wireshark/tcpdump để xác minh nhận định về mạng.

## 1. IP packet nằm ở đâu trong quá trình đóng gói?

Một ứng dụng tạo dữ liệu; TCP hoặc UDP (tầng 4) thêm thông tin vận chuyển; IP (tầng 3) thêm header gồm địa chỉ IP nguồn, đích và thông tin chuyển tiếp; công nghệ tầng liên kết như Ethernet hoặc Wi-Fi (tầng 2) đưa gói IP vào frame để truyền trên từng liên kết.

~~~text
Dữ liệu ứng dụng
      ↓
[ TCP header | Dữ liệu ứng dụng ]               ← TCP segment
      ↓
[ IP header | TCP segment ]                     ← IP packet
      ↓
[ Ethernet header | IP packet | Ethernet FCS ]  ← Ethernet frame
      ↓
Bit được truyền trên đường vật lý
~~~

Với UDP, phần bên trong gói IP là UDP datagram thay vì TCP segment. IP cũng có thể chở ICMP, IPsec ESP hoặc giao thức tầng trên khác, không bắt buộc phải là TCP/UDP.

**Ranh giới quan trọng:** Địa chỉ MAC trong Ethernet frame phục vụ việc chuyển frame trên **liên kết hiện tại**; địa chỉ IP đích cho router biết nơi cần chuyển gói tin ở **tầng mạng**. Header tầng 2 thường được thay ở mỗi hop. Địa chỉ IP nguồn và đích thông thường được giữ nguyên khi đi qua router, ngoại trừ các cơ chế có chủ đích như NAT hoặc đường hầm.

IP cung cấp dịch vụ **không thiết lập kết nối (connectionless)** và **cố gắng chuyển tốt nhất (best effort)**. Nó không hứa rằng mọi gói sẽ đến, đến đúng thứ tự hay không bị trùng lặp. Các chức năng khôi phục mất gói, sắp xếp và kiểm soát luồng của TCP nằm ở tầng vận chuyển, không phải khả năng tự có của IP.

## 2. Cấu trúc một gói IPv4

Một gói IPv4 gồm **header dài 20–60 byte** và phần **payload** có độ dài thay đổi. Header cơ bản dài 20 byte khi không có options:

~~~text
  0                   15                  31
  +--------+--------+----------+----------+
  |Version |  IHL   | DSCP/ECN |Total Len  |
  +--------+--------+----------+----------+
  |        Identification     |Flags|Offset|
  +---------------------------+-----+------+
  |      TTL      |  Protocol  |  Checksum |
  +---------------+------------+-----------+
  |             Source IPv4 address       |
  +---------------------------------------+
  |           Destination IPv4 address    |
  +---------------------------------------+
  | Options + padding (nếu có)            |
  +---------------------------------------+
  | Payload: TCP, UDP, ICMP, ...          |
  +---------------------------------------+
~~~

Sơ đồ trên thể hiện **nhóm trường**, không biểu diễn độ rộng từng ô theo cùng một tỉ lệ. Chi tiết độ rộng theo chuẩn:

| Trường IPv4 | Độ rộng | Vai trò khi đọc gói |
|---|---:|---|
| Version | 4 bit | Giá trị **4** xác định IPv4. |
| IHL (Internet Header Length) | 4 bit | Độ dài header theo đơn vị **4 byte**; IHL = 5 nghĩa là 20 byte; tối đa 15 nghĩa là 60 byte. |
| DSCP và ECN | 6 + 2 bit | Đánh dấu lớp dịch vụ (QoS) và báo tắc nghẽn có hỗ trợ ECN; có thể được mạng xử lý hoặc thay đổi theo chính sách. |
| Total Length | 16 bit | Độ dài **toàn bộ gói IPv4**, gồm header và payload; tối đa **65.535 byte**. |
| Identification | 16 bit | Cùng với thông tin nguồn/đích, giao thức và offset, giúp bên nhận nhận diện các mảnh thuộc một datagram để ghép lại. |
| Flags | 3 bit | Trong đó **DF** = Don't Fragment; **MF** = More Fragments. Một bit được dành riêng. |
| Fragment Offset | 13 bit | Vị trí phần dữ liệu của mảnh trong datagram gốc, tính theo **đơn vị 8 byte**. |
| TTL (Time To Live) | 8 bit | Giảm khi gói qua router để tránh vòng lặp chuyển tiếp kéo dài vô hạn. |
| Protocol | 8 bit | Giao thức nằm trong payload, ví dụ **1 = ICMP**, **6 = TCP**, **17 = UDP**, **50 = ESP**. |
| Header Checksum | 16 bit | Phát hiện lỗi trên **header IPv4**, không kiểm tra toàn bộ payload và không phải cơ chế xác thực mật mã. |
| Source Address | 32 bit | Địa chỉ IPv4 nguồn được ghi trong gói, chưa chắc chứng minh danh tính của người gửi. |
| Destination Address | 32 bit | Địa chỉ IPv4 đích mà thiết bị chuyển tiếp dùng để tra bảng định tuyến. |
| Options + Padding | 0–40 byte | Trường tùy chọn, có thể làm header dài hơn 20 byte; ít gặp trong lưu lượng ứng dụng thông thường. |

### Cách đọc ba trường dễ nhầm

**Total Length không phải kích thước Ethernet frame.** Nếu IPv4 Total Length = 1.040 byte và IHL = 5 thì payload IP = 1.040 − 20 = **1.020 byte**. Kích thước Ethernet frame còn có overhead của tầng liên kết, nằm ngoài Total Length.

**Protocol không phải số cổng.** Giá trị Protocol = 6 chỉ cho biết IP đang mang TCP. Cổng nguồn 51.234 hoặc cổng đích 443, nếu có, nằm trong **TCP header**. Với các mảnh IPv4 không phải mảnh đầu tiên, phần dữ liệu có thể không chứa TCP/UDP header, khiến chính sách chỉ dựa trên cổng trở nên khó áp dụng.

**TTL không đo số giây thực tế.** Mặc dù tên có chữ “Time”, trong chuyển tiếp thực tế TTL hoạt động như giới hạn hop: mỗi router giảm tối thiểu 1; khi không thể chuyển tiếp do TTL hết, router thường hủy gói và có thể gửi **ICMP Time Exceeded**. Công cụ traceroute sử dụng chính hành vi này để khám phá các hop trung gian.

## 3. Cấu trúc một gói IPv6

IPv6 sử dụng **base header cố định 40 byte**, mang địa chỉ nguồn/đích **128 bit**. Các khả năng mở rộng được tổ chức qua **extension headers** riêng, thay vì nhồi options vào base header như IPv4.

~~~text
  +---------------------------------------+
  | Version | Traffic Class | Flow Label  |
  +---------------------------------------+
  | Payload Length | Next Header |HopLimit|
  +---------------------------------------+
  |           Source IPv6 address         |
  |                 (128 bit)             |
  +---------------------------------------+
  |         Destination IPv6 address      |
  |                 (128 bit)             |
  +---------------------------------------+
  | Extension headers (nếu có)            |
  +---------------------------------------+
  | Payload tầng trên                    |
  +---------------------------------------+
~~~

| Trường IPv6 | Độ rộng | Ý nghĩa |
|---|---:|---|
| Version | 4 bit | Giá trị **6**. |
| Traffic Class | 8 bit | Phân loại dịch vụ và thông tin ECN, chức năng gần với DSCP/ECN ở IPv4. |
| Flow Label | 20 bit | Nhãn luồng có thể giúp thiết bị nhận biết các gói trong cùng luồng theo cơ chế hỗ trợ. |
| Payload Length | 16 bit | Độ dài **phần sau base header 40 byte**, bao gồm cả extension headers nếu có; không cộng 40 byte base header. Trường hợp jumbogram có quy tắc riêng. |
| Next Header | 8 bit | Chỉ ra header **ngay kế tiếp**: một extension header hoặc giao thức tầng trên, ví dụ TCP (6), UDP (17), ICMPv6 (58). |
| Hop Limit | 8 bit | Vai trò tương đương TTL của IPv4. |
| Source/Destination Address | 128 bit mỗi trường | Địa chỉ IPv6 nguồn và đích. |

Các khác biệt có tác động trực tiếp khi phân tích mạng:

| Nội dung | IPv4 | IPv6 |
|---|---|---|
| Độ dài header cơ bản | 20 byte, có thể dài hơn bởi options | 40 byte cố định |
| Địa chỉ | 32 bit | 128 bit |
| Trường tổng kích thước | **Total Length** gồm cả IPv4 header | **Payload Length** không gồm base header |
| Chống vòng lặp | TTL | Hop Limit |
| Kiểm tra lỗi header IP | Có Header Checksum | **Không có** header checksum |
| Phân mảnh | Nguồn và một số router có thể phân mảnh khi được phép | **Chỉ máy nguồn** phân mảnh với Fragment extension header; router không phân mảnh |
| Phân giải địa chỉ ở mạng cục bộ | Thường dùng ARP | Neighbor Discovery (thuộc ICMPv6) |
| Giao thức trong payload | Trường Protocol | Chuỗi Next Header, có thể qua nhiều extension headers |

**Lưu ý bảo mật:** Một firewall hoặc IDS/IPS xử lý IPv6 cần hiểu chuỗi extension headers để tìm đúng giao thức tầng trên. Kiểm tra duy nhất giá trị Next Header trong base header có thể bỏ sót TCP/UDP khi có extension header đứng giữa. Ngược lại, không phải gói IPv6 nào cũng có extension headers.

## 4. Gói IP đi qua mạng như thế nào?

Giả sử máy A gửi TCP tới máy B trên một mạng khác:

~~~text
Máy A (192.0.2.10)
    │  IPv4 packet: 192.0.2.10 → 198.51.100.20
    │  Frame tầng 2: MAC máy A → MAC router R1
    ▼
Router R1
    │  Tra route dựa trên IP đích; giảm TTL; cập nhật
    │  IPv4 Header Checksum; tạo frame mới cho hop sau
    ▼
Router R2
    │  Tiếp tục định tuyến và đóng gói tầng 2 phù hợp
    ▼
Máy B (198.51.100.20)
    │  IP chuyển payload cho TCP (Protocol = 6)
    ▼
Ứng dụng nhận dữ liệu qua tầng vận chuyển
~~~

Các địa chỉ **192.0.2.0/24** và **198.51.100.0/24** trong ví dụ là dải dành cho tài liệu; chúng không phải đích Internet để đem ra thử ping.

Quy trình có năm ý chính:

1. **Máy nguồn chọn đường:** dựa trên IP đích và bảng định tuyến, máy quyết định gửi trực tiếp trong cùng mạng liên kết hay gửi tới default gateway.
2. **Tìm địa chỉ tầng liên kết của next hop:** thông thường dùng ARP với IPv4 hoặc Neighbor Discovery với IPv6. Khi đi tới mạng khác, MAC cần tìm thường là **MAC của gateway kế tiếp**, không phải MAC của đích cuối.
3. **Router đọc IP header:** tra route để chọn next hop, giảm TTL/Hop Limit, đóng gói lại vào frame phù hợp với liên kết đi ra. Với IPv4, vì TTL thay đổi, Header Checksum phải được cập nhật.
4. **Thiết bị trung gian có thể can thiệp theo chính sách:** firewall có thể cho/chặn, NAT có thể viết lại IP và cổng trong các giao thức hỗ trợ, VPN có thể đóng gói gói gốc trong một gói ngoài. Các biến đổi này phụ thuộc kiến trúc; router thuần túy không tự động làm tất cả.
5. **Máy nhận xử lý:** IP kiểm tra header cần thiết, xử lý các mảnh nếu có, rồi chuyển payload cho giao thức tương ứng như TCP, UDP hoặc ICMP.

Đường đi theo chiều về có thể khác chiều đi (**asymmetric routing**). Vì thế, một firewall theo dõi trạng thái kết nối cần thấy đủ lưu lượng cần thiết theo kiến trúc; không nên mặc định mọi gói đều đi và về qua đúng một thiết bị.

## 5. Ví dụ giải mã một gói IPv4 cụ thể

Giả sử bộ bắt gói cho thấy những giá trị sau:

| Trường | Giá trị ví dụ | Cách suy luận |
|---|---|---|
| Version / IHL | 4 / 5 | IPv4, header 5 × 4 = **20 byte**. |
| Source / Destination | 192.0.2.10 / 198.51.100.20 | IP nguồn và đích, không đồng nghĩa đã xác thực nguồn. |
| Protocol | 6 | Payload chứa TCP. |
| TTL | 64 tại điểm quan sát | Gói còn giới hạn hop 64; không đủ để khẳng định chính xác đã qua bao nhiêu router. |
| DF | 1 | Router không được phân mảnh gói IPv4 này. |
| TCP header | 20 byte | Giả định TCP không có options. |
| Dữ liệu ứng dụng | 1.000 byte | Nằm bên trong payload TCP. |
| Total Length | 1.040 byte | 20 (IP) + 20 (TCP) + 1.000 (dữ liệu). |

Trong ví dụ này, **IPv4 payload = 1.020 byte**. Với một liên kết có MTU 1.500 byte, gói IP 1.040 byte nằm dưới giới hạn và không cần phân mảnh vì kích thước. Nếu đi qua một router, TTL có thể giảm từ 64 xuống 63; IP nguồn/đích thông thường vẫn như cũ và IPv4 Header Checksum sẽ thay đổi.

Giá trị TTL ban đầu phụ thuộc hệ điều hành và cấu hình. Không thể chỉ nhìn TTL quan sát được để kết luận một cách chắc chắn về hệ điều hành, số hop đã đi hoặc sự tồn tại của cuộc tấn công.

## 6. MTU, phân mảnh và Path MTU Discovery

**MTU (Maximum Transmission Unit)** là kích thước tối đa của đơn vị dữ liệu tầng mạng mà một liên kết có thể chở mà không phải phân mảnh ở tầng mạng đó. MTU Ethernet phổ biến là **1.500 byte** đối với gói IP, nhưng đường truyền thực tế có thể có MTU khác, nhất là qua VPN và các lớp đóng gói.

### Phân mảnh IPv4

Xét một gói IPv4 ban đầu có **20 byte header + 4.000 byte payload = 4.020 byte**, cần đi qua liên kết MTU = 1.500 byte. Giả sử IHL = 5, không có IP options, **DF = 0** và thiết bị chuyển tiếp có khả năng phân mảnh:

- Mỗi mảnh chứa IP header riêng dài 20 byte.
- Dữ liệu tối đa trong mỗi mảnh không phải mảnh cuối là 1.500 − 20 = **1.480 byte**; 1.480 chia hết cho 8.
- Fragment Offset dùng đơn vị **8 byte**, không phải byte trực tiếp.

| Mảnh | Payload của mảnh | Total Length | Fragment Offset | MF |
|---|---:|---:|---:|---:|
| 1 | 1.480 byte | 1.500 byte | 0 | 1 |
| 2 | 1.480 byte | 1.500 byte | 185 | 1 |
| 3 | 1.040 byte | 1.060 byte | 370 | 0 |

Tổng payload nhận được khi ghép là **1.480 + 1.480 + 1.040 = 4.000 byte**. Các mảnh giữ thông tin nhận dạng datagram phục vụ ghép lại; **máy đích** thực hiện tái lắp ghép, không đòi hỏi mỗi router phải ghép xong rồi mới chuyển tiếp.

Nếu **DF = 1** và một router IPv4 gặp liên kết có MTU nhỏ hơn gói cần chuyển, router không được phân mảnh gói. Nó phải bỏ gói và có thể gửi **ICMP Destination Unreachable, code 4 (Fragmentation Needed)** cho nguồn để hỗ trợ Path MTU Discovery.

### IPv6 và lựa chọn tránh phân mảnh

Router IPv6 **không phân mảnh** gói. Nếu gói vượt MTU của liên kết đi ra, router bỏ gói và gửi **ICMPv6 Packet Too Big (type 2)** theo quy tắc giao thức. Máy nguồn điều chỉnh kích thước hoặc, khi cần, tự tạo các mảnh với **Fragment extension header**. IPv6 yêu cầu liên kết hỗ trợ MTU tối thiểu **1.280 byte** ở tầng IP theo cơ chế tương ứng.

Trong triển khai hiện đại, thường ưu tiên **Path MTU Discovery (PMTUD)** hoặc **Packetization Layer PMTUD (PLPMTUD)** để chọn kích thước phù hợp và tránh phân mảnh không cần thiết. Nếu firewall chặn bừa bãi ICMP Fragmentation Needed hoặc ICMPv6 Packet Too Big, lưu lượng có thể bị hiện tượng **PMTU black hole**: gói nhỏ đi được, nhưng các gói lớn liên tục thất bại.

Phân mảnh cũng gây khó khăn cho bảo mật: mảnh đến sai thứ tự, thiếu mảnh hoặc có vùng dữ liệu chồng lấn có thể làm hệ thống đầu cuối và IDS tái lắp ghép khác nhau. Thiết bị kiểm soát lưu lượng cần xử lý mảnh nhất quán, giới hạn tài nguyên tái lắp ghép và tuân theo quy tắc IPv4/IPv6 tương ứng.

## 7. Liên hệ IP packet với các lớp phòng vệ mạng

Đọc đúng IP header giúp phân biệt **thông tin dùng để định tuyến**, **thông tin tầng vận chuyển** và **thông tin ứng dụng**, qua đó đặt chính sách ở đúng vị trí.

| Tình huống / rủi ro | IP packet tiết lộ gì? | Cách phòng vệ hoặc kiểm tra |
|---|---|---|
| **IP source spoofing** | Trường Source Address có thể bị giả mạo; địa chỉ ghi trên gói không tự xác thực chủ thể. | Chống giả mạo tại biên mạng bằng ingress filtering/BCP 38, uRPF khi phù hợp với định tuyến; kết hợp xác thực ở tầng cao hơn. |
| **Lọc truy cập giữa các subnet** | IP nguồn/đích và Protocol cho biết hướng lưu lượng và loại payload; TCP/UDP port nằm sâu hơn. | ACL, firewall L3/L4 và phân đoạn VLAN/VPC; áp dụng chính sách cho cả IPv4 lẫn IPv6, tính đến trạng thái kết nối. |
| **Lẩn tránh IDS/IPS qua phân mảnh** | IPv4 Fragment Offset, MF hoặc IPv6 Fragment extension header cho biết thông tin mảnh. | Tái lắp ghép/chuẩn hóa mảnh một cách nhất quán, kiểm soát mảnh bất thường và tài nguyên lưu trạng thái. |
| **Quét mạng, đường đi bất thường** | IP đích, Protocol, TTL/Hop Limit cung cấp dấu hiệu về lưu lượng và tuyến đi. | Kết hợp flow logs, IDS/IPS, firewall logs và bối cảnh; không kết luận tấn công chỉ từ một trường header. |
| **Lỗi gói lớn qua VPN/tunnel** | IP Total Length/Payload Length, cờ DF và phản hồi ICMP hỗ trợ tìm lỗi MTU. | Thiết lập tunnel MTU/MSS phù hợp và cho phép ICMP thiết yếu theo chính sách. |
| **Lọc IPv6 chưa đầy đủ** | Next Header có thể trỏ đến một extension header thay vì thẳng đến TCP/UDP. | Dùng firewall/IDS hiểu IPv6 và extension headers; áp dụng chính sách nhất quán cho dual-stack. |
| **Nhầm IP với bảo mật nội dung** | Header thường nhìn thấy khi chuyển tiếp; IPv4 checksum chỉ phát hiện lỗi header. | Dùng TLS, IPsec hoặc VPN theo mô hình đe dọa để bảo vệ tính bí mật/toàn vẹn và xác thực phù hợp. |

Một số nguyên tắc cần ghi nhớ:

- **IP source/destination không phải danh tính đã xác thực.** NAT, proxy, load balancer, tunnel và kỹ thuật spoofing khiến việc quy địa chỉ IP về một người dùng cụ thể không đáng tin nếu thiếu log và ngữ cảnh.
- **Firewall chỉ nhìn header IP chưa đủ để hiểu ứng dụng.** Phải phân tích thêm header tầng vận chuyển, trạng thái phiên hoặc dữ liệu tầng ứng dụng nếu chính sách yêu cầu.
- **NAT không đồng nghĩa với mã hóa hoặc cơ chế xác thực.** NAT có thể thay đổi địa chỉ/cổng; bảo vệ truy cập cần chính sách firewall và lớp bảo mật phù hợp.
- **ICMP là một phần hoạt động của IP.** Chặn toàn bộ ICMP/ICMPv6 có thể làm hỏng chẩn đoán, PMTUD và một số chức năng thiết yếu của IPv6 như Neighbor Discovery.

### Ví dụ phân tích sự cố: ứng dụng HTTPS hoạt động với gói nhỏ nhưng treo khi tải dữ liệu lớn

Giả sử hai chi nhánh kết nối qua VPN. Kiểm tra DNS, bắt tay TCP và truy cập một trang nhỏ đều thành công, nhưng truyền dữ liệu lớn hay bị đứng.

1. Xác minh chiều đi, chiều về và vị trí bắt gói: gói IP đi trong tunnel có thể cần thêm overhead của header ngoài.
2. So sánh kích thước gói IP với MTU khả dụng trong tunnel; quan sát DF của IPv4 hoặc thông báo ICMPv6 Packet Too Big nếu dùng IPv6.
3. Kiểm tra liệu thông báo ICMP phục vụ PMTUD bị firewall bỏ hay không; kiểm tra cả tunnel MTU và TCP MSS.
4. Chỉnh cấu hình MTU/MSS hoặc chính sách cho phép ICMP thiết yếu theo kết quả đo; bắt gói lần nữa để xác nhận truyền dữ liệu lớn thành công.

Đây là **giả thuyết chẩn đoán** chứ không phải kết luận sẵn: lỗi tương tự cũng có thể do mất gói, định tuyến bất đối xứng, thiết bị trung gian hoặc lỗi ứng dụng. Bằng chứng từ IP header và ICMP giúp thu hẹp nguyên nhân.

## 8. Thực hành đọc IP packet bằng Wireshark hoặc tcpdump

Chỉ bắt gói trên hệ thống/mạng mà bạn có quyền quan sát. Có thể sử dụng một file PCAP được cung cấp hợp lệ nếu không có quyền bắt gói trực tiếp.

### A. Kiểm tra với Wireshark

Mở một gói tin và mở rộng cây **Internet Protocol Version 4** hoặc **Internet Protocol Version 6**. Đối chiếu các giá trị Version, Source, Destination, TTL/Hop Limit, Protocol/Next Header và Length. Các bộ lọc hiển thị hữu ích:

~~~text
ip                                # Chỉ gói IPv4
ipv6                              # Chỉ gói IPv6
ip.proto == 6                     # IPv4 chở TCP
ip.flags.df == 1                  # IPv4 có cờ Don't Fragment
ip.flags.mf == 1 || ip.frag_offset > 0
                                  # Các gói IPv4 thuộc chuỗi mảnh
icmp.type == 3 && icmp.code == 4  # IPv4: Fragmentation Needed
icmpv6.type == 2                  # IPv6: Packet Too Big
~~~

Một gói IPv6 có extension headers cần được mở rộng từng header để tìm đúng giao thức tầng trên; bộ lọc kiểm tra trực tiếp **ipv6.nxt** không thay thế việc đọc toàn bộ chuỗi Next Header.

### B. Quan sát bằng tcpdump trên Linux

Trên máy đã cài tcpdump và có quyền bắt gói, thay tên interface cho phù hợp:

~~~bash
sudo tcpdump -nni eth0 -vv -c 10 'ip or ip6'
~~~

Tùy phiên bản và loại gói, kết quả có thể hiện các trường như **ttl**, **id**, **flags [DF]**, **proto**, **length**, IP nguồn/đích và cổng tầng vận chuyển. Tùy chọn **-nn** tắt phân giải tên và số cổng; **-vv** tăng độ chi tiết; **-c 10** kết thúc sau 10 gói.

Hãy chọn một gói IPv4/TCP và tự kiểm tra phép tính:

~~~text
IPv4 header length = IHL × 4
IPv4 payload length = Total Length − IPv4 header length
TCP application data length =
    IPv4 payload length − TCP header length
~~~

Phép tính cuối áp dụng cho **gói chứa TCP header và dữ liệu đầy đủ**; không dùng máy móc với mảnh IPv4 không phải mảnh đầu, gói bị cắt khi capture hoặc các giao thức khác. Với IPv6, cần tính thêm độ dài extension headers nếu muốn tìm lượng dữ liệu ứng dụng.

### C. Các câu hỏi tự kiểm tra khi đọc PCAP

1. Gói bạn đang xem thuộc IPv4 hay IPv6? Dựa vào trường nào?
2. IP đích có nằm trong cùng mạng cục bộ với máy gửi không? Nếu không, frame tầng 2 sẽ gửi tới MAC của thiết bị nào?
3. Trường nào cho thấy IPv4 không được phép phân mảnh? Khi gói vượt MTU, điều gì có thể xảy ra?
4. Vì sao chỉ dựa trên trường Next Header đầu tiên của IPv6 có thể phân loại nhầm gói?
5. Vì sao bắt được một gói có Source Address cụ thể vẫn chưa thể khẳng định người gửi đã được xác thực?

## 9. Ghi nhớ cốt lõi

**IP packet = IP header + payload**, ở tầng 3; nó được mang trong frame của từng liên kết và có thể chở TCP, UDP, ICMP hoặc nhiều giao thức khác. **IPv4** có header cơ bản 20 byte, Total Length gồm cả header, TTL và Header Checksum; **IPv6** có base header 40 byte, Payload Length không gồm base header, Hop Limit và chuỗi Next Header.

Router chọn next hop theo IP đích, giảm TTL/Hop Limit và thay frame tầng 2 trên liên kết tiếp theo. **MTU và PMTUD** quyết định kích thước gói thích hợp; IPv4 có khả năng phân mảnh trong mạng khi được phép, còn router IPv6 không phân mảnh. Khi thiết kế firewall, VPN và IDS/IPS, luôn xét **địa chỉ có thể bị giả mạo, fragment/extension headers và ICMP thiết yếu** để chính sách vừa an toàn vừa duy trì kết nối.
