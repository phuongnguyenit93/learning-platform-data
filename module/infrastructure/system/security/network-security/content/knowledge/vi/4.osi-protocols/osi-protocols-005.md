# Ethernet frame: cấu trúc, truyền tải và bảo mật ở tầng liên kết dữ liệu

## 1. Ethernet frame là gì?

**Ethernet frame (khung Ethernet)** là đơn vị dữ liệu được trao đổi trên một liên kết Ethernet ở **tầng 2 – Data Link** của mô hình OSI. Một frame có địa chỉ MAC đích, MAC nguồn, thông tin nhận diện dữ liệu được đóng gói, vùng dữ liệu và mã kiểm tra lỗi. Switch Ethernet dựa vào các thông tin tầng 2, đặc biệt là MAC đích và VLAN, để quyết định chuyển tiếp frame.

Trong học phần **SECURITY_NETWORK_SECURITY**, hiểu cấu trúc frame là nền tảng để phân tích lưu lượng, chia VLAN, cấu hình switch, phát hiện giả mạo MAC/ARP, kiểm soát cổng truy cập và xác định giới hạn bảo vệ của các cơ chế như FCS, 802.1X và MACsec. Ethernet không tự xác thực danh tính của máy gửi hoặc mã hóa nội dung.

Đặt trong mô hình OSI:

| Tầng | Ví dụ | Vai trò khi gửi một gói IPv4 |
| --- | --- | --- |
| Tầng 7–5: Ứng dụng, trình bày, phiên | HTTP, TLS, DNS | Sinh và xử lý dữ liệu ứng dụng |
| Tầng 4: Transport | TCP, UDP | Đóng gói dữ liệu theo kết nối hoặc datagram |
| Tầng 3: Network | IPv4, IPv6 | Định tuyến gói theo địa chỉ IP |
| **Tầng 2: Data Link** | **Ethernet II, IEEE 802.3, 802.1Q** | Đóng gói gói IP vào frame, chuyển tiếp theo MAC và VLAN |
| Tầng 1: Physical | Cáp đồng, quang, tín hiệu điện/quang | Biểu diễn và truyền các bit |

**Phân biệt phạm vi:** Gói IP có thể đi qua nhiều router nhưng frame Ethernet chỉ có ý nghĩa trên liên kết/đoạn mạng tầng 2 tương ứng. Khi router chuyển gói sang chặng Ethernet mới, router tạo frame mới với địa chỉ MAC phù hợp chặng đó; địa chỉ IP nguồn/đích thường được giữ nguyên khi định tuyến thông thường (ngoại trừ các biến đổi như NAT).

## 2. Bố cục Ethernet II trên đường truyền

Đây là dạng frame phổ biến khi mang IPv4, IPv6 hoặc ARP:

~~~text
Trên đường truyền:
  Preamble 7B | SFD 1B | MAC đích 6B | MAC nguồn 6B
               | EtherType 2B | Data + Padding 46–1500B | FCS 4B | IFG
                \___________ Ethernet MAC frame ___________/

Nếu gắn 1 thẻ 802.1Q:
  MAC đích 6B | MAC nguồn 6B | TPID 2B | TCI 2B
               | EtherType 2B | Data + Padding | FCS 4B
                              \__ VLAN tag 4B __/
~~~

Trong sơ đồ, **B** là byte (octet). Preamble và Start Frame Delimiter (SFD) được truyền trước frame; **Interframe Gap (IFG)** là khoảng nghỉ truyền tương đương thời gian của 12 byte ở tốc độ đường truyền. Chúng **không được tính** vào độ dài Ethernet MAC frame 64–1518 byte.

| Trường | Kích thước | Chức năng và ý nghĩa |
| --- | ---: | --- |
| Preamble | 7 byte | Chuỗi đồng bộ để thiết bị nhận bắt nhịp tín hiệu, thường biểu diễn bằng 7 byte 0x55 |
| SFD | 1 byte | Đánh dấu điểm bắt đầu frame, thường biểu diễn 0xD5 |
| Destination MAC | 6 byte | Địa chỉ MAC nhận; có thể là unicast, multicast hoặc broadcast |
| Source MAC | 6 byte | Địa chỉ MAC của thiết bị phát frame trên liên kết |
| EtherType/Length | 2 byte | Xác định giao thức cấp trên ở Ethernet II hoặc độ dài dữ liệu ở IEEE 802.3 |
| Payload và Padding | Biến thiên | Dữ liệu được đóng gói; có thể thêm byte đệm để đạt kích thước frame tối thiểu |
| FCS | 4 byte | Giá trị CRC-32 để phát hiện lỗi bit ngẫu nhiên trong quá trình truyền |
| IFG | 96 bit-times | Khoảng cách giữa các frame, không phải trường của frame |

### 2.1. Địa chỉ MAC và loại frame

Địa chỉ MAC Ethernet thông thường dài **48 bit**, viết thành sáu cặp byte, ví dụ **02:11:22:33:44:55**.

- **Unicast:** Gửi đến một địa chỉ MAC đơn lẻ, chẳng hạn 00:11:22:33:44:55. Switch tìm cổng ra dựa vào bảng MAC và VLAN.
- **Broadcast:** MAC đích **ff:ff:ff:ff:ff:ff**. Frame được phát tới các cổng phù hợp trong cùng miền broadcast/VLAN, ngoại trừ cổng nhận và tùy chính sách switch.
- **Multicast:** MAC đích chỉ một nhóm thiết bị, ví dụ **01:00:5e:xx:xx:xx** thường dùng cho multicast IPv4 và **33:33:xx:xx:xx:xx** cho IPv6; cách phân phối có thể phụ thuộc IGMP/MLD snooping hoặc quy tắc xử lý địa chỉ điều khiển.

Bit thấp nhất của byte đầu tiên trong MAC xác định địa chỉ **individual (0)** hay **group (1)**; MAC nguồn hợp lệ trong frame Ethernet thông thường phải là địa chỉ individual. Bit kế tiếp chỉ phân biệt địa chỉ **universally administered (0)** và **locally administered (1)**. MAC nguồn có thể bị phần mềm thay đổi; vì vậy MAC **không phải** bằng chứng xác thực danh tính.

### 2.2. EtherType khác Length như thế nào?

Hai byte sau MAC nguồn được giải nghĩa theo kiểu khung:

| Giá trị trường hai byte | Cách diễn giải |
| --- | --- |
| **0–1500** (0x0000–0x05DC) | Trường **Length** của IEEE 802.3; dữ liệu phía sau thường có **LLC** (IEEE 802.2), có thể kèm SNAP |
| **1501–1535** (0x05DD–0x05FF) | Khoảng giá trị không dùng để phân biệt Length/EtherType trong Ethernet chuẩn |
| **Từ 1536** (0x0600) | Trường **EtherType** của Ethernet II, cho biết giao thức được đóng gói |

Một số EtherType hay gặp:

| EtherType | Giao thức/ý nghĩa |
| --- | --- |
| 0x0800 | IPv4 |
| 0x0806 | ARP |
| 0x86DD | IPv6 |
| 0x8100 | Thẻ VLAN C-tag IEEE 802.1Q; EtherType thực nằm sau thẻ |
| 0x88A8 | Thẻ VLAN S-tag IEEE 802.1ad, thường dùng trong QinQ |
| 0x888E | EAPOL, dùng trong kiểm soát truy cập IEEE 802.1X |
| 0x88CC | LLDP, khám phá thiết bị lân cận ở tầng 2 |

Khi trường này là **Length**, bên nhận phải phân tích các byte LLC/SNAP tiếp theo; **không** coi chúng là phần đầu của IPv4 chỉ vì nội dung trông giống một IP header. Với Ethernet II, EtherType cho phép thiết bị chuyển trực tiếp payload đến thành phần xử lý tương ứng.

### 2.3. Kích thước tối thiểu, tối đa và MTU

Với Ethernet thông thường, **không có VLAN tag**:

- Frame nhỏ nhất: **64 byte** = 6 (MAC đích) + 6 (MAC nguồn) + 2 (EtherType/Length) + **46** (payload và padding) + 4 (FCS).
- Frame lớn nhất: **1518 byte** = 6 + 6 + 2 + **1500** + 4.
- **MTU Ethernet thường là 1500 byte**, tức kích thước tối đa của gói tầng trên mang trong trường payload, **không** bao gồm Ethernet header, FCS, preamble hoặc IFG.

Với **một thẻ VLAN IEEE 802.1Q** (4 byte), frame có thể lên đến **1522 byte** khi vẫn mang payload 1500 byte. Độ dài frame tối thiểu theo định nghĩa MAC vẫn là **64 byte**; phần payload/padding có thể giảm còn 42 byte do bốn byte thẻ VLAN cũng được tính vào độ dài. Một thiết bị không hỗ trợ khung gắn VLAN đúng kích thước có thể coi chúng là frame quá cỡ.

Một frame Ethernet II mang payload ARP 28 byte cần **18 byte padding** để có ít nhất 46 byte ở trường dữ liệu. Những byte đệm này không phải dữ liệu ARP và không được ứng dụng đọc như nội dung ARP. **Jumbo frame** là cấu hình mở rộng theo thiết bị/mạng, không có một kích thước phổ quát; thường cần hỗ trợ nhất quán giữa các điểm kết nối.

**Lưu ý khi đọc Wireshark/tcpdump:** Nhiều card mạng không chuyển FCS cho hệ điều hành. Gói bắt được có thể dài 60 byte khi frame trên dây thực tế dài 64 byte, hoặc không hiển thị thẻ VLAN vì tính năng VLAN offload của NIC. Không kết luận frame sai định dạng chỉ từ việc hai thành phần này vắng mặt trong bản capture.

## 3. VLAN tag 802.1Q nằm ở đâu?

Khi một frame được gắn VLAN tag, switch chèn **4 byte giữa Source MAC và EtherType/Length gốc**:

~~~text
Không gắn thẻ:
  [Dst MAC 6] [Src MAC 6] [EtherType 2] [Payload] [FCS 4]

Gắn thẻ 802.1Q:
  [Dst MAC 6] [Src MAC 6] [TPID 2 = 0x8100] [TCI 2]
  [EtherType 2] [Payload] [FCS 4]
~~~

TCI (Tag Control Information) là 16 bit:

| Thành phần | Số bit | Ý nghĩa |
| --- | ---: | --- |
| PCP | 3 | Priority Code Point, phục vụ phân loại ưu tiên QoS (0–7) |
| DEI | 1 | Drop Eligible Indicator, chỉ báo mức ưu tiên có thể bị loại khi nghẽn |
| VID | 12 | VLAN ID; VLAN sử dụng thông thường nằm trong **1–4094** |

VID **0** biểu thị frame ưu tiên không chỉ định VLAN (priority-tagged), còn **4095** được dự trữ. Trên trunk, frame có thể có một tag hoặc nhiều tag theo cơ chế **QinQ**; S-tag thường có TPID **0x88A8**. Số tag ảnh hưởng kích thước và cách phân tích header, vì vậy không thể cố định EtherType của IP luôn ở byte thứ 12–13 trong mọi frame.

Ví dụ phần **header** của một Ethernet II frame gắn VLAN 100:

~~~text
00 11 22 33 44 55  02 aa bb cc dd ee  81 00  00 64  08 00
|--- MAC đích ---|  |--- MAC nguồn ---|  TPID    TCI   EtherType
                                               VLAN 100   IPv4
~~~

TCI = **0x0064** nghĩa là PCP=0, DEI=0 và VID=100. Dòng hex này mới là **18 byte header để minh họa**, không phải frame hoàn chỉnh để truyền trên mạng.

**Access port** thường nhận/gửi frame không gắn thẻ từ thiết bị cuối và gán nó vào VLAN đã cấu hình. **Trunk port** thường mang nhiều VLAN và sử dụng tag để phân biệt, đồng thời có thể có native VLAN không gắn thẻ theo cấu hình. Quy tắc cụ thể phải kiểm tra theo loại thiết bị và cấu hình; không nên mặc định mọi frame trên trunk đều có tag.

## 4. Phân tích một frame ARP từng byte

Giả sử máy A có MAC **02:11:22:33:44:55**, IP **192.0.2.10/24**, muốn tìm MAC của **192.0.2.1** trong cùng LAN. Máy phát ARP Request qua một Ethernet II frame broadcast.

~~~text
Ethernet II header (14 byte):
  ff ff ff ff ff ff                  Destination MAC: broadcast
  02 11 22 33 44 55                  Source MAC: máy A
  08 06                              EtherType: ARP

ARP Request payload (28 byte):
  00 01                              Hardware type: Ethernet (1)
  08 00                              Protocol type: IPv4 (0x0800)
  06                                 Hardware address length: 6
  04                                 Protocol address length: 4
  00 01                              Operation: request (1)
  02 11 22 33 44 55                  Sender hardware address
  c0 00 02 0a                        Sender IP: 192.0.2.10
  00 00 00 00 00 00                  Target hardware address: chưa biết
  c0 00 02 01                        Target IP: 192.0.2.1

Padding (18 byte):                  Bổ sung để đủ 46 byte payload
FCS (4 byte):                       CRC-32 của frame được phát
~~~

Phép tính: **14 + 28 + 18 + 4 = 64 byte**. Preamble 7 byte, SFD 1 byte và IFG không nằm trong phép cộng này. Giá trị FCS thực tế phụ thuộc vào đúng các byte phát, kể cả padding, nên ví dụ không tự bịa một CRC cố định.

Máy giữ IP **192.0.2.1** có thể trả lời bằng ARP Reply **unicast** đến MAC của máy A. Sau khi biết MAC của next-hop, máy A mới đóng gói gói IP vào Ethernet frame gửi tới MAC đó.

**Trường hợp đi qua router:** Nếu A muốn truy cập **198.51.100.20** ở mạng khác, **IP đích vẫn là 198.51.100.20** nhưng **MAC đích trong frame đầu tiên là MAC của default gateway**, không phải MAC của máy 198.51.100.20. Router sẽ bóc header tầng 2 của chặng vào rồi tạo frame mới cho chặng ra.

## 5. Switch xử lý frame như thế nào?

Một switch học địa chỉ MAC **theo VLAN** và dùng bảng chuyển tiếp (forwarding database, FDB) để đưa frame đến cổng phù hợp:

1. **Nhận và kiểm tra:** Cổng nhận frame, xác định VLAN theo tag/cấu hình ingress, áp dụng chính sách và kiểm tra tính hợp lệ ở tầng MAC.
2. **Học MAC nguồn:** Switch cập nhật ánh xạ **(VLAN, source MAC) → cổng vào** nếu chính sách cho phép.
3. **Tra MAC đích:** Nếu địa chỉ unicast đã biết và cổng đích hợp lệ, switch chuyển frame đến cổng tương ứng.
4. **Flood khi cần:** Broadcast hoặc unknown unicast thường được nhân bản đến các cổng đủ điều kiện trong **cùng VLAN**, ngoại trừ cổng nhận; multicast có thể được xử lý riêng nhờ IGMP/MLD snooping và các quy tắc địa chỉ điều khiển.
5. **Phát frame ra:** Switch thực hiện quy tắc tag/untag của cổng ra, có thể tính lại FCS nếu frame bị thay đổi. Router hoặc thiết bị tầng 3 đi qua ranh giới mạng sẽ đóng gói lại địa chỉ MAC cho chặng tiếp theo.

Ví dụ, máy A thuộc VLAN 100 gửi broadcast ARP. Switch không tự chuyển frame đó sang VLAN 200 nếu không có chức năng/chính sách đặc biệt ở tầng cao hơn. **VLAN giúp phân tách miền broadcast**, nhưng việc cô lập an toàn còn phụ thuộc trunk, cấu hình định tuyến giữa VLAN, ACL và chính sách truy cập.

**Vì sao loop tầng 2 nguy hiểm?** Ethernet frame không có trường TTL như IP. Một vòng lặp chuyển mạch có thể gây nhân bản broadcast, làm bảng MAC thay đổi liên tục và tạo broadcast storm. Các giao thức spanning tree như RSTP/MSTP cùng thiết kế topo mạng, BPDU Guard và storm control giúp giảm rủi ro này.

## 6. FCS phát hiện lỗi, không xác thực thiết bị

**Frame Check Sequence (FCS)** là 4 byte CRC-32, dùng để phát hiện phần lớn lỗi truyền dẫn vô tình. Thiết bị nhận tính CRC và đối chiếu; frame bị lỗi thường bị loại ngay ở phần cứng nên không xuất hiện trong bản capture thông thường. CRC không có khóa bí mật: kẻ tấn công sửa nội dung frame có thể tính FCS mới hợp lệ.

Phân biệt các cơ chế:

| Cơ chế | Phạm vi | Điều không nên suy diễn |
| --- | --- | --- |
| Ethernet FCS/CRC-32 | Phát hiện lỗi bit của frame trên một liên kết | Không chống nghe lén, sửa đổi có chủ ý hay giả MAC |
| IPv4 header checksum | Kiểm tra header IPv4 (IPv6 không có trường này) | Không chứng thực người gửi và không bảo vệ toàn bộ nội dung ứng dụng |
| TCP/UDP checksum | Phát hiện lỗi ở dữ liệu/phần header vận chuyển theo quy tắc giao thức | Không có tính xác thực mật mã |
| 802.1X/EAPOL | Kiểm soát xác thực truy cập cổng mạng | Bản thân 802.1X không đồng nghĩa mã hóa mọi frame |
| MACsec (IEEE 802.1AE) | Bảo vệ tính toàn vẹn, xác thực nguồn ở liên kết và có thể mã hóa frame trên liên kết được thiết lập | Không tự cung cấp bảo vệ đầu cuối qua mọi router/đường truyền |
| TLS/IPsec | Bảo vệ truyền thông ở các tầng tương ứng | Không thay thế cấu hình an toàn cho switch, VLAN và cổng truy cập |

## 7. Các tấn công và biện pháp phòng vệ liên quan đến frame

| Rủi ro | Cơ chế diễn ra ở Ethernet/LAN | Kiểm soát thực tế |
| --- | --- | --- |
| **MAC spoofing** | Thiết bị phát frame với MAC nguồn giả để né quy tắc dựa trên MAC | 802.1X/NAC, xác thực thiết bị, port security như biện pháp bổ sung; ghi log và rà soát MAC thay đổi |
| **MAC table flooding** | Nhiều MAC nguồn giả làm FDB bị quá tải, có thể tăng unknown-unicast flooding | Port security, giới hạn MAC/cổng, theo dõi FDB và cảnh báo bất thường |
| **ARP spoofing/poisoning** | ARP giả mạo trong payload của Ethernet frame làm sai ánh xạ IP–MAC | DHCP Snooping kết hợp Dynamic ARP Inspection (DAI), phân đoạn và mã hóa ở tầng cao |
| **VLAN hopping/misconfiguration** | Trunk được thương lượng không mong muốn, native VLAN hoặc double-tagging bị khai thác trong điều kiện phù hợp | Cấu hình access/trunk tường minh, vô hiệu trunk negotiation nơi không cần, giới hạn allowed VLAN, quản lý native VLAN |
| **Broadcast storm/loop** | Broadcast hoặc unknown unicast bị lặp và lan rộng trong miền tầng 2 | RSTP/MSTP, BPDU Guard ở edge port, storm control, giám sát băng thông |
| **Nghe lén/tampering trên liên kết** | Frame thu được hoặc bị thay đổi trên đoạn mạng không được bảo vệ | MACsec khi hạ tầng hỗ trợ, 802.1X kiểm soát truy cập, TLS/IPsec cho dữ liệu nhạy cảm |

Một số lưu ý vận hành:

- **Port security** có thể giới hạn số MAC học trên một cổng nhưng không chứng minh chủ sở hữu hợp pháp của địa chỉ MAC; không xem nó tương đương xác thực mật mã.
- **DAI** cần nguồn ánh xạ IP–MAC tin cậy (thường từ DHCP Snooping; host dùng IP tĩnh cần cấu hình tương ứng). Không bật mặc định trên toàn mạng mà bỏ qua cơ chế cấp phát IP thực tế.
- **ARP** là giao thức của IPv4 LAN; khi phân tích IPv6, cần xét **NDP**, Router Advertisement và những kiểm soát tương ứng như RA Guard thay vì áp dụng nguyên mẫu ARP.
- **VLAN** giảm phạm vi phát tán frame nhưng không mã hóa dữ liệu. Hai VLAN vẫn có thể giao tiếp qua router/firewall nếu chính sách cho phép.
- Các địa chỉ MAC điều khiển dành riêng có thể được switch xử lý đặc biệt; không coi mọi multicast đều được flood giống broadcast.

## 8. Thực hành quan sát Ethernet frame

### 8.1. Đọc frame bằng Wireshark

Trên một máy hoặc môi trường lab được phép thu thập lưu lượng:

1. Bắt gói ở card mạng đang kết nối, tạo lưu lượng bằng thao tác truy cập dịch vụ hoặc ping gateway.
2. Chọn một gói ARP hoặc IPv4, mở cây **Ethernet II** và xem **Destination**, **Source**, **Type**.
3. Nếu có VLAN tag hiển thị, mở **802.1Q Virtual LAN** để kiểm tra **Priority**, **DEI**, **ID**.
4. Đối chiếu cột độ dài với nội dung frame và lưu ý tính năng bỏ FCS/VLAN tag của card mạng.

Bộ lọc hiển thị (display filter) hữu ích:

~~~text
eth.type == 0x0806                   # ARP
eth.type == 0x0800                   # IPv4 (kể cả sau VLAN tag nếu bộ giải mã hỗ trợ)
eth.dst == ff:ff:ff:ff:ff:ff         # Ethernet broadcast
vlan.id == 100                      # Frame hiển thị VLAN 100
eapol                               # Trao đổi IEEE 802.1X/EAPOL
~~~

Điểm quan sát: Wireshark thường giải mã tầng ứng dụng từ frame. Trường Ethernet Type cho biết giao thức ngay sau header Ethernet (hoặc sau tag), còn việc nhận ra HTTP/TLS/TCP đòi hỏi tiếp tục phân tích các tầng phía trong.

### 8.2. Quan sát bằng tcpdump trên Linux

~~~bash
# Thay eth0 bằng đúng interface của máy lab.
sudo tcpdump -i eth0 -e -n -vv 'arp or ip or ip6'

# Hiển thị các frame có VLAN tag khi driver/NIC đưa tag vào capture.
sudo tcpdump -i eth0 -e -n -vv 'vlan'

# Kiểm tra khả năng offload VLAN của card mạng (chỉ đọc cấu hình).
ethtool -k eth0
~~~

Tùy quyền truy cập, thiết bị, driver và vị trí capture, bạn có thể **không thấy** frame của các máy khác trên switch hoặc không thấy FCS/tag như trên dây thực. SPAN/mirror port hoặc thiết bị TAP cần được bố trí đúng nếu bài lab cần quan sát lưu lượng ngoài máy cục bộ.

### 8.3. Đọc Ethernet/VLAN header bằng Python

Đoạn mã dưới đây chỉ **phân tích header có sẵn**; nó không gửi frame, không xác minh CRC/FCS và không giả định capture có FCS:

~~~python
def parse_ethernet_header(data: bytes) -> dict:
    if len(data) < 14:
        raise ValueError("Header Ethernet cần tối thiểu 14 byte")

    mac = lambda part: ":".join(f"{b:02x}" for b in part)
    dest, src = mac(data[:6]), mac(data[6:12])
    value = int.from_bytes(data[12:14], "big")
    offset, vlans = 14, []

    while value in (0x8100, 0x88A8):
        if len(data) < offset + 4:
            raise ValueError("VLAN tag bị cắt cụt")
        tci = int.from_bytes(data[offset:offset + 2], "big")
        vlans.append({
            "pcp": (tci >> 13) & 0x7,
            "dei": (tci >> 12) & 0x1,
            "vid": tci & 0x0FFF,
        })
        value = int.from_bytes(data[offset + 2:offset + 4], "big")
        offset += 4

    kind = ("802.3 length" if value <= 1500 else
            "EtherType" if value >= 1536 else "reserved")
    return {
        "destination": dest,
        "source": src,
        "vlans": vlans,
        "field_kind": kind,
        "field_value": f"0x{value:04x}",
        "payload_offset": offset,
    }


# Đây là 18 byte header minh họa, chưa phải frame hoàn chỉnh.
header = bytes.fromhex(
    "00 11 22 33 44 55 02 aa bb cc dd ee 81 00 00 64 08 00"
)
print(parse_ethernet_header(header))
~~~

Kết quả cần nhận ra: MAC đích **00:11:22:33:44:55**, MAC nguồn **02:aa:bb:cc:dd:ee**, VLAN **100**, giao thức tiếp theo **0x0800 (IPv4)**, dữ liệu tầng trên bắt đầu ở **offset 18**. Nếu không có VLAN tag, offset thường là **14**.

## 9. Tình huống phân tích và chẩn đoán

**Tình huống A – Ping trong cùng VLAN thất bại.** Trước hết kiểm tra hai máy có cùng subnet/IP phù hợp, đúng VLAN access và trạng thái cổng. Quan sát ARP Request có phát đi không, ARP Reply có về không, MAC nguồn/đích và bảng MAC của switch. Nếu có ARP Request nhưng không có Reply, nguyên nhân có thể là máy đích tắt, cấu hình VLAN/trunk sai, chính sách ACL hoặc vấn đề ARP; chỉ dựa vào Ethernet header chưa đủ để kết luận.

**Tình huống B – Ping liên VLAN thất bại.** Frame gửi đến đích thuộc mạng khác phải có **MAC đích của gateway** ở chặng đầu. Kiểm tra default gateway, ARP cho gateway, interface định tuyến giữa VLAN và ACL/firewall. Đừng tìm MAC của IP từ xa trong frame của chặng LAN đầu tiên.

**Tình huống C – Switch báo nhiều lần MAC flapping.** Một MAC học được luân phiên trên hai cổng có thể báo hiệu loop, kết nối dự phòng cấu hình sai, thiết bị di động hoặc hành vi giả MAC. Đối chiếu (VLAN, MAC, port), trạng thái STP, topo và thời điểm thay đổi trước khi kết luận là tấn công.

**Tình huống D – Bắt gói không thấy VLAN tag hoặc FCS.** Kiểm tra vị trí đặt điểm capture, đường access/trunk, khả năng VLAN offload và FCS stripping của NIC. Thiếu tag/FCS trong file pcap không tự chứng minh thiết bị gửi thiếu trường đó trên dây.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Mỗi Ethernet frame đều dài 1518 byte.” | 1518 byte là kích thước **tối đa thông thường của frame không VLAN**; frame tối thiểu 64 byte và có nhiều độ dài ở giữa. |
| “MTU 1500 là kích thước toàn frame.” | MTU 1500 thường là giới hạn **payload tầng trên**; cộng Ethernet header và FCS sẽ lớn hơn. |
| “FCS hợp lệ là nội dung đáng tin.” | FCS chỉ phát hiện lỗi truyền dẫn, không xác minh danh tính hay ngăn sửa dữ liệu có chủ ý. |
| “EtherType của IPv4 luôn nằm ở offset 12.” | Đúng với Ethernet II **không tag**; VLAN tag làm thay đổi offset. |
| “Switch luôn gửi frame đến đúng một cổng.” | Broadcast, unknown unicast và một số multicast có thể được flood trong miền VLAN. |
| “Máy gửi đến IP ngoài subnet phải biết MAC của server từ xa.” | Trên chặng Ethernet đầu tiên, máy gửi đến **MAC của next-hop/default gateway**. |
| “Chia VLAN là đủ chống nghe lén.” | VLAN phân tách miền tầng 2; bảo mật cần thêm kiểm soát truy cập, cấu hình switch và mã hóa phù hợp. |

## 11. Tự kiểm tra

1. **Vì sao ARP Request 28 byte cần padding?** Vì payload Ethernet II không VLAN phải có ít nhất 46 byte; ARP 28 byte cần thêm 18 byte đệm.
2. **Frame Ethernet II có EtherType 0x86DD mang dữ liệu gì?** IPv6.
3. **Một frame gắn thẻ 802.1Q, TCI = 0x0064, thuộc VLAN nào?** VLAN 100, PCP=0 và DEI=0.
4. **Tại sao capture chỉ có 60 byte vẫn có thể tương ứng frame Ethernet hợp lệ?** Card mạng có thể đã loại FCS 4 byte trước khi cung cấp gói cho công cụ capture.
5. **FCS có ngăn kẻ tấn công giả MAC nguồn không?** Không; kẻ tấn công có thể tạo frame mới với MAC nguồn giả và CRC hợp lệ.
6. **Nếu IP đích ở mạng khác, frame đầu tiên ghi MAC đích của ai?** MAC của next-hop (thường là default gateway) trên đường Ethernet hiện tại.

Khi phân tích sự cố hoặc đánh giá an ninh mạng, nên đọc frame theo thứ tự: **MAC đích/nguồn → VLAN tag (nếu có) → EtherType hoặc Length → payload → FCS nếu được cung cấp**, đồng thời xác định **cổng, VLAN, điểm capture và chặng mạng** đang quan sát. Những yếu tố đó quyết định một frame được chuyển tiếp tới đâu và cơ chế bảo vệ nào thực sự có hiệu lực.
