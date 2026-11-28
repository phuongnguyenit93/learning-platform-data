# Tầng vật lý và liên kết dữ liệu trong mô hình OSI

Trong mô hình OSI, **tầng vật lý (Layer 1)** đưa tín hiệu qua môi trường truyền, còn **tầng liên kết dữ liệu (Layer 2)** tổ chức các bit thành khung, trao đổi dữ liệu giữa những thiết bị trên cùng một liên kết hoặc miền mạng cục bộ. Hai tầng là nền móng để IP, TCP/UDP và các ứng dụng hoạt động. Với an ninh mạng, đây cũng là nơi xuất hiện các rủi ro như cắm thiết bị trái phép, nghe lén đường truyền, giả mạo địa chỉ MAC, thao túng ARP, vượt ranh giới VLAN do cấu hình sai và làm gián đoạn mạng bằng vòng lặp chuyển mạch.

Bài học thuộc chương **OSI và giao thức** của học phần **SECURITY_NETWORK_SECURITY**, gắn nguyên lý L1/L2 với phân đoạn mạng, kiểm soát truy cập, quan sát lưu lượng, mô hình hóa mối đe dọa và xây dựng hạ tầng mạng an toàn.

## 1. Vị trí và nhiệm vụ của hai tầng

Hãy hình dung máy A gửi một bản tin đến máy B qua một switch Ethernet:

~~~text
Máy A                         Switch                           Máy B
Ứng dụng                                                       Ứng dụng
TCP/UDP                                                        TCP/UDP
IP                                                              IP
L2: đóng khung --[frame]--> L2: đọc MAC --[frame]-----------> L2: nhận khung
L1: phát tín hiệu =========> L1: nhận/phát tín hiệu ==========> L1: giải tín hiệu
        cáp đồng / cáp quang / sóng vô tuyến trên từng liên kết
~~~

Ở mỗi liên kết, phần cứng chuyển **bit thành tín hiệu** rồi khôi phục bit ở đầu nhận. Phần liên kết dữ liệu xác định **khung bắt đầu và kết thúc ở đâu**, thiết bị nào trên mạng cục bộ cần nhận khung và liệu dữ liệu có bị lỗi trong khi truyền hay không.

| Tiêu chí | Tầng 1 — Vật lý | Tầng 2 — Liên kết dữ liệu |
|---|---|---|
| Đơn vị xử lý | Bit, tín hiệu điện/quang/vô tuyến | Khung (frame) |
| Câu hỏi chính | Truyền bit bằng cách nào? | Chuyển khung đến cổng/thiết bị nào trên liên kết? |
| Chức năng | Môi trường truyền, mã hóa tín hiệu, tốc độ liên kết, đồng bộ bit, đầu nối | Đóng khung, địa chỉ MAC, truy nhập môi trường, phát hiện lỗi, chuyển mạch |
| Thiết bị tiêu biểu | Dây cáp, bộ thu phát (transceiver), repeater, hub; phần PHY của NIC | Switch/bridge, điểm truy cập Wi-Fi; phần MAC của NIC |
| Chỉ báo sự cố | Mất link, suy hao, nhiều lỗi tín hiệu, lệch tốc độ/duplex | Sai VLAN, MAC không học được, loop, khung bị loại, ARP sai |
| Ví dụ phòng vệ | Khóa tủ mạng, kiểm soát cổng vật lý, bảo vệ cáp/quang, chống nhiễu | 802.1X, port security, VLAN/ACL, DHCP snooping, Dynamic ARP Inspection, MACsec |

**Ranh giới quan trọng:** switch L2 chủ yếu chuyển khung trong cùng miền L2; router hoặc switch L3 chuyển **gói IP** giữa các mạng IP. Một thiết bị có thể thực hiện nhiều tầng cùng lúc; tên thiết bị không quyết định tuyệt đối chức năng của từng cổng.

## 2. Tầng vật lý (Physical Layer)

### 2.1. Từ bit thành tín hiệu

Một chuỗi nhị phân như **10110010** không tự đi qua cáp hay không khí. Bộ PHY (physical-layer transceiver) của giao diện mạng mã hóa hoặc điều chế dữ liệu thành biến thiên điện áp, ánh sáng hoặc sóng vô tuyến. Đầu nhận xử lý tín hiệu, lấy lại đồng hồ bit và khôi phục chuỗi bit. Việc truyền thực tế có thể dùng nhiều cặp dây, nhiều làn quang, nhiều sóng mang và các kỹ thuật xử lý tín hiệu phức tạp; không nên đồng nhất «1 bit = 1 xung điện».

Các yếu tố chính:

- **Môi trường truyền:** cáp đồng xoắn đôi, sợi quang, không gian vô tuyến.
- **Băng thông và tốc độ đường truyền:** tốc độ danh định của liên kết, ví dụ 1 Gb/s hoặc 10 Gb/s, khác với tốc độ ứng dụng thu được vì còn overhead, lỗi và tranh chấp tài nguyên.
- **Suy hao và nhiễu:** khoảng cách, đầu nối kém, uốn cong sợi quang, nhiễu điện từ hoặc giao thoa vô tuyến có thể làm chất lượng tín hiệu giảm.
- **Đồng bộ và chế độ liên kết:** hai đầu cần hỗ trợ chế độ tương thích; một số Ethernet trên cáp đồng sử dụng auto-negotiation để trao đổi khả năng tốc độ/duplex.
- **Tỷ lệ lỗi bit (BER):** thể hiện mức độ sai bit; BER tăng có thể dẫn đến các frame bị loại ở tầng 2.

### 2.2. Các môi trường truyền thường gặp

| Môi trường | Đặc điểm | Điểm cần quan tâm về vận hành/an ninh |
|---|---|---|
| Cáp đồng xoắn đôi Ethernet | Phổ biến ở mạng LAN; đầu nối dạng 8P8C thường được gọi là RJ45; đôi dây xoắn giảm nhiễu | Dây hỏng, sai đấu nối, nhiễu, cổng mạng ở khu vực công cộng, nguy cơ cắm thiết bị lạ |
| Quang đa mode (multimode) | Phù hợp nhiều liên kết ngắn/trung bình trong tòa nhà hoặc trung tâm dữ liệu; khoảng cách tùy chuẩn tốc độ/quang | Bụi đầu nối, suy hao quang, lựa chọn module/SFP và loại sợi đúng |
| Quang đơn mode (single-mode) | Hỗ trợ khoảng cách xa hơn với module quang thích hợp | Kiểm soát đường đi sợi quang, đo công suất quang, bảo vệ vị trí đấu nối |
| Vô tuyến Wi-Fi | Thiết bị chia sẻ môi trường sóng vô tuyến; chịu ảnh hưởng khoảng cách, vật cản, nhiễu và kênh | Vùng phủ sóng vượt phạm vi vật lý, nghe tín hiệu ngoài tòa nhà, gây nhiễu/chèn sóng, AP giả mạo |

**Ví dụ chuẩn khoảng cách:** 1000BASE-T thường chạy tới 100 m trên hệ thống cáp đồng đạt yêu cầu; 10GBASE-T có thể đạt 100 m trên Cat 6A được lắp đặt đúng chuẩn. Các giá trị này phụ thuộc chuẩn PHY và chất lượng toàn bộ kênh cáp, không áp dụng máy móc cho mọi tốc độ hoặc loại dây.

**PoE (Power over Ethernet)** có thể truyền nguồn điện cùng đường cáp mạng theo các chuẩn IEEE 802.3 liên quan. PoE phục vụ camera, điện thoại IP và AP; khi thiết kế cần kiểm tra khả năng cấp nguồn, tổng công suất switch, nhiệt độ bó cáp và an toàn điện. Có điện PoE **không có nghĩa** đường dữ liệu đang hoạt động tốt.

### 2.3. Tốc độ, duplex và lỗi đường truyền

- **Half-duplex:** ở một thời điểm một phía truyền trên môi trường chung; Ethernet dùng hub lịch sử gắn với cơ chế CSMA/CD và va chạm (collision).
- **Full-duplex:** hai phía có thể truyền/nhận đồng thời trên liên kết điểm–điểm; Ethernet switch hiện đại phần lớn sử dụng chế độ này và không vận hành theo cơ chế va chạm CSMA/CD.
- **Auto-negotiation:** khi hai đầu hỗ trợ, nên cấu hình tương thích để tránh lệch duplex hoặc tốc độ. Tắt tự thương lượng tùy tiện có thể gây lỗi khó chẩn đoán.
- **Counters:** CRC/FCS errors, symbol errors, link flaps, drops cho biết tín hiệu hoặc liên kết bất thường; cần xem cả hai đầu cổng, không chỉ một chỉ số.

Tầng vật lý không nhận biết người dùng hay địa chỉ IP. Vì vậy kiểm soát tủ mạng, patch panel, đường cáp, phòng thiết bị và cổng kết nối chưa sử dụng là một phần của an ninh mạng, dù không xuất hiện trong cấu hình firewall.

## 3. Tầng liên kết dữ liệu (Data Link Layer)

### 3.1. Framing, địa chỉ và phát hiện lỗi

Tầng 2 nhận dữ liệu từ tầng mạng (ví dụ gói IPv4/IPv6), thêm thông tin điều khiển để tạo **frame**. Trong mạng Ethernet, mỗi frame thường mang:

- **Địa chỉ MAC đích và nguồn:** địa chỉ lớp liên kết của giao diện trên một đoạn mạng; thông thường dài 48 bit. MAC có thể do nhà sản xuất gán, do hệ điều hành tạo ngẫu nhiên hoặc bị thay đổi; **không phải bằng chứng định danh đáng tin cậy**.
- **EtherType:** cho biết giao thức được đóng gói, ví dụ 0x0800 cho IPv4, 0x86DD cho IPv6, 0x0806 cho ARP trong Ethernet II.
- **Payload:** dữ liệu lớp trên, kèm padding nếu cần để đạt kích thước khung tối thiểu.
- **Frame Check Sequence (FCS):** thường dùng CRC-32 để **phát hiện** lỗi truyền. CRC không mã hóa, không xác thực nguồn và không ngăn sửa đổi có chủ ý.

Sơ đồ một frame Ethernet II cơ bản (số trong ngoặc là độ dài theo byte):

~~~text
Trên đường truyền:
[Preamble (7)][SFD (1)] [MAC đích (6)][MAC nguồn (6)][EtherType (2)]
                              [Payload / padding (46..1500)][FCS (4)]
                         <---------- frame Ethernet ---------->
~~~

- **Preamble/SFD** giúp đồng bộ và đánh dấu bắt đầu frame; không tính vào độ dài Ethernet frame thường được nêu.
- Frame Ethernet II không gắn VLAN thông thường dài **64–1518 byte** (tính từ MAC đích đến FCS), với payload Ethernet tối đa 1500 byte theo MTU phổ biến. Frame dưới chuẩn tối thiểu cần padding; các giao thức và đường truyền hỗ trợ jumbo frame có giới hạn riêng.
- Tag **IEEE 802.1Q dài 4 byte** được chèn giữa MAC nguồn và trường loại/độ dài, làm frame tối đa thông thường tăng từ 1518 lên **1522 byte**. Thiết bị có thể không hiển thị FCS/tag trong packet capture do cơ chế NIC hoặc offload.
- Trong **IEEE 802.3 với trường Length/LLC**, ý nghĩa trường 2 byte và cách phân biệt giao thức khác với Ethernet II dùng EtherType; không nên gọi mọi frame 802.3 đều là cùng một định dạng.

**Ví dụ đọc frame:** nếu Wireshark ghi Destination MAC = aa:bb:cc:dd:ee:ff, Source MAC = 02:11:22:33:44:55 và Type = 0x0800 thì frame Ethernet đang chở một gói IPv4 tới MAC đích nêu trên. Từ frame này chưa thể kết luận người dùng nào đã gửi, đường đi IP sẽ như thế nào hay nội dung đã được mã hóa.

### 3.2. Switch học MAC và chuyển khung

Switch Ethernet xây dựng bảng **MAC address table / forwarding database (FDB)** theo từng VLAN và cổng. Một quá trình đơn giản:

1. Frame đi vào cổng 1, nguồn có MAC A thuộc VLAN 10; switch học **(VLAN 10, MAC A) → cổng 1**.
2. Nếu MAC đích B đã có trong bảng VLAN 10, switch chuyển frame đến cổng tương ứng (trừ khi đích ở chính cổng nhận hoặc có luật kiểm soát khác).
3. Nếu chưa biết vị trí MAC đích, switch có thể **flood unknown unicast** tới các cổng thích hợp của VLAN 10, ngoại trừ cổng nhận.
4. Broadcast (ví dụ ff:ff:ff:ff:ff:ff) thường được chuyển đến các cổng cùng VLAN; multicast có cơ chế xử lý riêng, có thể được giới hạn bằng IGMP/MLD snooping nếu được cấu hình.
5. Bảng MAC có tuổi thọ; khi MAC chuyển cổng hoặc entries hết hạn, switch học lại.

~~~text
                 VLAN 10
Laptop A ---p1---+
                 |    Switch L2 ----p2---- Laptop B
Printer  ---p3---+             |
                               +--p4---- Thiết bị C (VLAN 20)

Frame broadcast từ A: đến các cổng thuộc VLAN 10, không tự đi vào VLAN 20.
Để liên lạc VLAN 10 <-> VLAN 20: cần định tuyến L3 và chính sách cho phép.
~~~

Một switch L2 thường tách **collision domain** theo từng cổng Ethernet full-duplex, nhưng **broadcast domain** được giới hạn theo VLAN. Khi có nhiều đường kết nối L2 dự phòng, loop có thể làm broadcast nhân lên liên tục. STP/RSTP giúp tránh vòng lặp bằng cách chọn đường chuyển tiếp phù hợp hoặc chặn một số đường dự phòng.

### 3.3. MAC không đồng nghĩa IP

MAC dùng để chuyển frame trong phạm vi L2; IP dùng để định tuyến giữa các mạng L3. Với IPv4, **ARP** hỗ trợ tìm MAC tương ứng với địa chỉ IPv4 trong mạng cục bộ: máy gửi broadcast ARP request, bên phù hợp trả lời, rồi kết quả được ghi vào ARP/neighbor cache.

**ARP không phải một cơ chế xác thực.** Kẻ ở cùng miền L2 có thể tìm cách gửi thông tin ARP giả để lừa máy trạm/gateway. Với IPv6, việc tìm hàng xóm dùng **Neighbor Discovery (ND)** dựa trên ICMPv6; cơ chế và kiểm soát khác ARP, dù đều tác động tới việc phân giải địa chỉ link-layer.

Lưu ý: ARP thường được thảo luận tại ranh giới L2/L3 vì ánh xạ IPv4 ↔ MAC và được đóng trực tiếp trong Ethernet frame. Không nên giản lược rằng ARP là giao thức định tuyến IP hay rằng ARP xử lý tất cả các địa chỉ IPv6.

### 3.4. Ethernet và Wi-Fi giống nhau ở mục tiêu, khác nhau ở frame

Ethernet IEEE 802.3 và Wi-Fi IEEE 802.11 đều cung cấp vận chuyển dữ liệu qua liên kết, nhưng cách truy cập môi trường và định dạng frame không hoàn toàn giống nhau:

| Đặc tính | Ethernet có switch | Wi-Fi |
|---|---|---|
| Môi trường | Thường là liên kết cáp điểm–điểm, full-duplex | Môi trường sóng vô tuyến dùng chung, ảnh hưởng bởi tranh chấp, nhiễu |
| Truy nhập kênh | Full-duplex switched Ethernet không cần CSMA/CD | Họ cơ chế CSMA/CA và điều phối truyền theo chuẩn 802.11 |
| Khung dữ liệu | MAC nguồn/đích, EtherType hoặc Length/LLC, FCS | Các trường điều khiển/địa chỉ phụ thuộc loại frame và hướng liên lạc; có frame quản lý và điều khiển |
| Bảo mật liên kết | 802.1X, MACsec ở môi trường/thiết bị hỗ trợ | WPA2/WPA3, 802.1X/EAP trong chế độ Enterprise, Protected Management Frames (PMF) theo khả năng/chính sách |

Một access point có thể bridge lưu lượng giữa Wi-Fi và Ethernet. Do cấu trúc frame khác nhau, không nên giả định bản capture 802.11 có vị trí trường và số địa chỉ MAC y hệt Ethernet.

## 4. Những giao thức và cơ chế L2 quan trọng

| Chuẩn/giao thức | Vai trò | Ý nghĩa về bảo mật |
|---|---|---|
| IEEE 802.3 / Ethernet | Truyền và đóng khung trên LAN có dây | Cần bảo vệ cổng vật lý, phân đoạn và giám sát lỗi |
| IEEE 802.11 / Wi-Fi | Kết nối LAN không dây | Cấu hình WPA2/WPA3 phù hợp, quản lý AP, bảo vệ frame quản lý |
| IEEE 802.1Q / VLAN | Gắn nhãn lưu lượng VLAN trên liên kết trunk; chia miền broadcast | Giới hạn VLAN được phép trên trunk, quản lý native VLAN và kiểm soát định tuyến liên VLAN |
| STP/RSTP (họ IEEE 802.1D/802.1Q) | Duy trì topology L2 không vòng lặp | BPDU Guard/Root Guard trên đúng vai trò cổng, giám sát thay đổi topology |
| IEEE 802.1X / EAPOL | Kiểm soát truy cập mạng theo cổng, chuyển thông điệp EAP | Xác thực thiết bị/người dùng trước khi cấp quyền mạng, phụ thuộc triển khai AAA |
| IEEE 802.1AE / MACsec | Mã hóa và bảo vệ tính toàn vẹn trên từng liên kết Ethernet hỗ trợ | Chống nghe lén/sửa đổi frame trên đường truyền được bảo vệ; không thay thế bảo vệ đầu cuối |
| IEEE 802.1AB / LLDP | Trao đổi thông tin lân cận trên liên kết | Hữu ích kiểm kê, nhưng có thể tiết lộ thông tin topology nếu bật trên cổng không tin cậy |
| IEEE 802.1AX / LACP | Gom nhiều liên kết vật lý thành nhóm logic | Dùng đúng cấu hình nhóm/cổng, kiểm soát lỗi nối và topology |

### 4.1. VLAN access và trunk

- **Access port:** thường gắn thiết bị đầu cuối vào một VLAN theo cấu hình switch. Frame Ethernet của host thường không mang tag VLAN trên đường access.
- **Trunk port:** mang nhiều VLAN giữa switch, router, firewall, hypervisor hoặc AP phù hợp; 802.1Q gắn nhãn VLAN để phân biệt traffic.
- **Tag 802.1Q:** gồm TPID (thông dụng 0x8100) và TCI với **PCP 3 bit**, **DEI 1 bit**, **VID 12 bit**. VID 0 và 4095 có ý nghĩa dành riêng; VID 1–4094 thường dùng làm VLAN ID tùy khả năng thiết bị.
- **Native/untagged VLAN:** cách xử lý frame không tag trên trunk phụ thuộc cấu hình và nhà sản xuất. Tránh để native VLAN chứa tài nguyên nhạy cảm; thống nhất cấu hình hai đầu và chỉ cho phép danh sách VLAN cần thiết.

**VLAN là cơ chế phân đoạn L2, không tự tạo chính sách cho phép/từ chối giữa các VLAN.** Nếu router hoặc switch L3 định tuyến giữa VLAN mà không có ACL/firewall tương ứng, các mạng vẫn có thể truy cập lẫn nhau.

### 4.2. 802.1X khác với port security

**802.1X** có ba thành phần điển hình: *supplicant* (máy trạm), *authenticator* (switch/AP) và *authentication server* (thường RADIUS). Máy trạm trao đổi EAP qua EAPOL ở liên kết, authenticator chuyển tiếp thông tin xác thực tới server rồi áp dụng quyền truy cập theo chính sách. Có thể kết hợp VLAN động, chứng chỉ và chính sách cho thiết bị IoT theo năng lực hạ tầng.

**Port security** thường giới hạn số lượng hoặc tập MAC được học trên cổng. Vì địa chỉ MAC có thể bị giả mạo, port security không thể thay thế xác thực mạnh bằng 802.1X. Với thiết bị không hỗ trợ supplicant, một số mạng dùng MAC Authentication Bypass (MAB) nhưng cần hiểu đây là cơ chế có độ tin cậy thấp hơn.

### 4.3. MACsec bảo vệ từng chặng

MACsec (802.1AE) có thể cung cấp **bảo mật, tính toàn vẹn và bảo vệ chống phát lại** cho frame qua một liên kết Ethernet được cấu hình tương thích. Khóa có thể được thỏa thuận bằng các cơ chế quản lý khóa liên quan như MKA. Khi frame đi ra khỏi phạm vi liên kết được MACsec bảo vệ, sự bảo vệ đó không mặc nhiên tiếp tục.

Vì vậy MACsec hữu ích với đường nối switch–switch hoặc thiết bị–switch trên môi trường có nguy cơ bị nghe lén, nhưng vẫn cần TLS/VPN và các kiểm soát ở tầng trên nếu dữ liệu phải được bảo vệ **xuyên suốt giữa các đầu cuối**.

## 5. Ví dụ: lưu lượng đi trong VLAN và đi qua router

Giả sử ta có:

~~~text
                     Switch
Máy A (VLAN 10) ---- access 10
  192.168.10.11/24       |
                         +---- trunk VLAN 10,20 ---- Router/L3 gateway
Máy B (VLAN 10) ---- access 10                       VLAN 10: 192.168.10.1
  192.168.10.12/24                                   VLAN 20: 192.168.20.1
                         |
Máy C (VLAN 20) ---- access 20
  192.168.20.21/24
~~~

**Trường hợp 1 — A liên lạc B (cùng VLAN và cùng subnet):**

1. A xác định 192.168.10.12 cùng subnet; nếu chưa biết MAC của B, A gửi ARP request broadcast trong VLAN 10.
2. B phản hồi ARP với MAC của mình; A lưu ánh xạ IP–MAC trong neighbor cache.
3. A đóng gói IP packet vào Ethernet frame có **MAC đích = MAC B**. Switch dựa vào VLAN 10 và bảng MAC để chuyển frame.
4. L1 thực hiện truyền tín hiệu trên từng đoạn. Trường IP đích vẫn là 192.168.10.12; không cần router cho quá trình này.

**Trường hợp 2 — A liên lạc C (khác subnet/VLAN):**

1. A nhận ra 192.168.20.21 không thuộc subnet của mình và chọn default gateway 192.168.10.1.
2. A phân giải **MAC của gateway VLAN 10**, sau đó gửi Ethernet frame đến MAC này; **IP đích vẫn là 192.168.20.21**.
3. Router/L3 nhận frame, bỏ phần đóng khung L2 của chặng trước, tra bảng định tuyến/chính sách, rồi tạo **frame L2 mới** trong VLAN 20 hướng tới MAC của C (sau khi phân giải địa chỉ nếu cần).
4. MAC nguồn/đích thay đổi theo chặng; trong định tuyến IPv4 thông thường, TTL giảm. IP nguồn/đích được giữ theo nguyên lý định tuyến, trừ khi có NAT hay chức năng biến đổi khác.
5. Nếu chính sách ACL/firewall chặn lưu lượng từ VLAN 10 sang VLAN 20, kết nối dừng ở điểm kiểm soát L3 dù cả hai cổng L2 đều hoạt động bình thường.

**Bài học bảo mật:** đặt máy chủ, thiết bị quản trị, IoT và khách vào VLAN phù hợp chỉ là bước đầu. Cần đặt quy tắc cho lưu lượng giữa các nhóm, kiểm soát thiết bị được phép nối cổng và theo dõi các hành vi bất thường trong từng miền L2.

## 6. Bề mặt tấn công và biện pháp phòng vệ

### 6.1. Rủi ro ở tầng vật lý

| Nguy cơ | Cách ảnh hưởng | Phòng vệ phù hợp |
|---|---|---|
| Cắm thiết bị vào ổ mạng/cổng switch chưa kiểm soát | Có thể được vào mạng nội bộ hoặc nghe thông tin quảng bá trên VLAN được cấp | Khóa cổng chưa dùng, 802.1X, phân quyền mạng theo vai trò, giám sát thiết bị |
| Trộm/can thiệp cáp, patch panel, tủ mạng | Mất dịch vụ hoặc lộ thông tin ở những đường truyền không mã hóa | Kiểm soát ra vào, camera, niêm phong, quản lý thay đổi, bảo vệ đường cáp |
| Nhiễu điện từ, suy hao quang, kết nối không đạt chuẩn | Tăng lỗi bit, FCS errors, link flap | Đo kiểm cáp/quang, kiểm tra module, quản lý nguồn/tiếp địa, giám sát counter |
| Nhiễu/gây nhiễu vô tuyến | Làm giảm tốc độ hoặc mất kết nối Wi-Fi | Khảo sát RF, thiết kế phủ sóng/kênh/công suất và cơ chế giám sát nhiễu theo quy định |

Các lớp mã hóa bảo vệ **nội dung dữ liệu**, nhưng không làm dây cáp ngừng đứt hoặc vô tuyến ngừng bị gây nhiễu. Thiết kế cần cả an ninh vật lý lẫn dự phòng kết nối hợp lý.

### 6.2. Rủi ro ở tầng liên kết dữ liệu

| Kịch bản | Nguyên lý gây hại | Kiểm soát giảm thiểu |
|---|---|---|
| **MAC spoofing** | Thiết bị tự nhận địa chỉ MAC khác để vượt qua kiểm tra yếu | 802.1X dựa trên chứng chỉ/chính sách, kiểm kê endpoint, port security như lớp bổ sung |
| **CAM/MAC table flooding** | Nhiều địa chỉ MAC nguồn làm tăng tải bảng học MAC, có thể dẫn tới flooding trên một số thiết bị | Giới hạn MAC và rate, giám sát, cô lập cổng bất thường; hành vi cụ thể tùy thiết bị |
| **ARP spoofing/poisoning** | Gửi ánh xạ IP–MAC sai để chuyển hướng hoặc làm gián đoạn lưu lượng IPv4 trong miền L2 | DHCP snooping cung cấp binding, Dynamic ARP Inspection (DAI), phân đoạn, mã hóa đầu cuối, giám sát ARP |
| **DHCP spoofing** | DHCP server trái phép đưa gateway/DNS hoặc cấu hình mạng không mong muốn | DHCP snooping và phân biệt cổng trusted/untrusted, cấu hình port và giám sát server DHCP |
| **VLAN hopping do sai cấu hình** | Cổng tự thành trunk hoặc kết hợp tag/native VLAN ngoài dự kiến | Cố định chế độ cổng, tắt thương lượng trunk không cần thiết, hạn chế allowed VLAN, cấu hình native VLAN nhất quán |
| **STP/BPDU manipulation** | Thiết bị lạ làm thay đổi root bridge/topology, gây chuyển hướng hoặc gián đoạn | BPDU Guard ở cổng edge, Root Guard nơi phù hợp, giám sát topology, quản lý cáp |
| **L2 loop / broadcast storm** | Frame lặp hoặc nhân bản liên tục trên liên kết dự phòng sai thiết kế | RSTP/MSTP, storm control, kiểm soát thay đổi, chống loop theo tính năng thiết bị |
| **Rogue AP / evil twin / deauthentication** | AP không được phép dụ kết nối; một số frame quản lý không được bảo vệ có thể bị giả mạo | Quản trị danh sách AP, WPA2-Enterprise/WPA3-Enterprise tùy yêu cầu, xác thực chứng chỉ EAP, PMF, giám sát không dây |
| **IPv6 RA/ND giả mạo** | Thông báo router hoặc láng giềng không hợp lệ làm sai thông tin cấu hình/đường đi | RA Guard/ND inspection phù hợp, lọc theo vai trò cổng, giám sát IPv6; xác minh tính tương thích thiết bị |

**Giới hạn của các biện pháp:** DHCP snooping và DAI chỉ hiệu quả khi cổng trusted được phân định đúng và binding phù hợp với các máy dùng IP tĩnh. BPDU Guard cần đặt ở cổng edge chứ không tùy tiện bật trên toàn bộ uplink. Một số chức năng kiểm tra IPv6 có ngoại lệ/giới hạn theo phần cứng và kiểu frame; luôn đánh giá trên cấu hình thực tế.

### 6.3. Thiết kế phòng vệ theo lớp

Một ví dụ cho mạng văn phòng nhỏ:

1. **Tầng vật lý:** khóa tủ mạng, quản lý sơ đồ cáp/cổng, vô hiệu hóa ổ mạng chưa sử dụng, giới hạn quyền can thiệp switch và AP.
2. **Kiểm soát truy cập L2:** dùng 802.1X/EAP-TLS ở thiết bị hỗ trợ; có chính sách cô lập thiết bị chưa xác thực và phương án giới hạn cho IoT/thiết bị ngoại lệ.
3. **Phân đoạn:** tách VLAN nhân viên, khách, máy chủ, thiết bị quản trị và IoT; cấp trunk chính xác cho các uplink; tránh mở mọi VLAN theo mặc định.
4. **Bảo vệ control plane:** DHCP snooping/DAI, BPDU Guard, storm control và theo dõi MAC move/topology change khi hạ tầng hỗ trợ.
5. **Kiểm soát liên VLAN:** áp dụng ACL/firewall theo nguyên tắc quyền tối thiểu, chỉ cho phép dịch vụ và chiều kết nối cần thiết.
6. **Bảo vệ dữ liệu và giám sát:** ưu tiên TLS, cân nhắc MACsec cho liên kết trọng yếu, thu thập log switch/AP, counter cổng, sự kiện xác thực và lưu lượng bất thường.

Điểm cần nhớ: **lọc tại firewall ở tầng 3/4 không xử lý hết các vấn đề phát sinh bên trong cùng VLAN**. Ngược lại, VLAN, MAC filtering hay port security đơn lẻ cũng không thay thế bảo mật ứng dụng và xác thực danh tính.

## 7. Quan sát và chẩn đoán hai tầng

### 7.1. Dấu hiệu định hướng điều tra

| Triệu chứng | Nơi kiểm tra trước | Các nguyên nhân có thể |
|---|---|---|
| Giao diện báo link down | L1 | Đứt/sai cáp, transceiver không phù hợp, cổng hỏng, thiết bị không cấp nguồn |
| Link up nhưng nhiều CRC/FCS errors | L1 và L2 | Nhiễu, suy hao, lỗi cáp/quang, duplex không tương thích |
| Máy nhận IP nhưng không liên hệ được máy cùng VLAN | L2 và cấu hình IP | Sai access VLAN, bị chặn port, ARP/neighbor bất thường, isolation |
| Gặp broadcast tăng đột biến, mạng chập chờn | L2 | Loop, storm, host tạo lưu lượng bất thường, topology thay đổi |
| Cùng VLAN liên hệ được, khác VLAN không được | L3/chính sách | Chưa có route, sai gateway, ACL/firewall, DHCP cấp sai subnet |
| Wi-Fi chập chờn dù switch uplink ổn định | L1 vô tuyến và L2 802.11 | Nhiễu RF, độ phủ kém, tranh chấp kênh, roaming hoặc xác thực lỗi |

Không kết luận sự cố mạng là do firewall khi chưa xác minh link, VLAN, neighbor table và route. Đồng thời, một link **up** chỉ xác nhận mức liên kết tối thiểu; nó không chứng minh lưu lượng được phép đến dịch vụ đích.

### 7.2. Lệnh quan sát an toàn trên Linux

Các ví dụ sau chỉ đọc trạng thái. Thay **enp1s0** bằng tên giao diện thực tế, và chạy trong mạng được phép quản trị.

~~~bash
# Xem tên, trạng thái và địa chỉ phần cứng các giao diện
ip -br link

# Xem số khung/byte, lỗi và gói bị loại trên giao diện
ip -s link show dev enp1s0

# Xem tốc độ, duplex, trạng thái link của NIC Ethernet (nếu hỗ trợ)
ethtool enp1s0

# Xem bảng ánh xạ láng giềng (ARP IPv4, ND IPv6)
ip neigh show

# Nếu máy đang làm Linux bridge: xem VLAN của bridge
bridge vlan show

# Quan sát tối đa 20 frame ARP, VLAN hoặc EAPOL trên cổng được phép
sudo tcpdump -i enp1s0 -e -nn -c 20 'arp or vlan or ether proto 0x888e'
~~~

Lệnh **tcpdump -e** yêu cầu in thông tin L2 như MAC khi giao diện/capture cung cấp. Quyền bắt gói có thể cần administrator/root; chỉ xem lưu lượng do giao diện nhận được. Switch thông thường **không** gửi tất cả lưu lượng của các cổng khác cho một máy trạm; muốn phân tích traffic của một liên kết cần phương án mirror/SPAN hoặc tap đã được cho phép. Một số NIC và driver lược bỏ VLAN tag hoặc FCS khỏi kết quả capture.

### 7.3. Lệnh quan sát trên Windows (PowerShell)

~~~powershell
# Thông tin giao diện, tốc độ link, MAC
Get-NetAdapter | Format-Table Name, Status, LinkSpeed, MacAddress

# Thống kê lưu lượng/lỗi (tùy driver)
Get-NetAdapterStatistics -Name "Ethernet"

# Xem ánh xạ IP - MAC đã học
Get-NetNeighbor -AddressFamily IPv4
~~~

Trong Wireshark có thể dùng một số **display filter** sau để đọc những frame đã được capture hợp lệ:

| Bộ lọc | Ý nghĩa |
|---|---|
| **arp** | Thông điệp ARP của IPv4 |
| **vlan** | Frame có tag VLAN mà bộ giải mã quan sát được |
| **eth.type == 0x0800** | Ethernet frame mang IPv4 |
| **eth.type == 0x86dd** | Ethernet frame mang IPv6 |
| **eapol** | 802.1X/EAPOL trong capture |
| **stp** | Thông điệp STP/BPDU mà Wireshark nhận diện |
| **lldp** | Thông tin thiết bị lân cận qua LLDP |

Để bắt các frame quản lý 802.11 trực tiếp qua vô tuyến, card Wi-Fi/driver và chế độ capture phải hỗ trợ; capture trên Ethernet phía sau AP có thể chỉ thấy frame đã được bridge sang Ethernet.

### 7.4. Tình huống thực hành: xác định lỗi VLAN

Một laptop được cấp IP **192.168.10.20/24**, gateway **192.168.10.1**, nhưng không liên hệ được máy in **192.168.10.50** ở cùng subnet.

1. Kiểm tra trạng thái link, tốc độ và counter lỗi. Nếu link down hoặc lỗi vật lý tăng, xử lý cáp/cổng trước.
2. Kiểm tra thông tin IP/subnet của laptop và máy in. Nếu địa chỉ thuộc hai subnet khác nhau, giả định «cùng VLAN/cùng mạng» có thể đã sai.
3. Xác minh cổng switch của cả hai thuộc VLAN dự kiến và VLAN được truyền trên đường uplink cần thiết.
4. Xem neighbor/ARP cache sau một lần thử kết nối hợp lệ. Nếu chưa phân giải được MAC của máy in, kiểm tra ARP request có ra cổng, có bị cô lập ở L2 và thiết bị đích có phản hồi hay không.
5. Nếu ARP thành công nhưng giao thức ứng dụng vẫn không kết nối, tiếp tục kiểm tra chính sách trên host, dịch vụ máy in và các lớp trên; không quy toàn bộ lỗi cho L2.
6. Nếu cùng lúc có MAC move liên tục, STP topology change hoặc mức broadcast tăng bất thường, điều tra loop/cấu hình switch và thiết bị mới cắm.

Trong báo cáo sự cố, nên lưu **thời điểm**, cổng switch, VLAN, tốc độ/duplex, số counter trước–sau, bảng MAC/neighbor liên quan và thay đổi cấu hình gần nhất. Các dữ kiện này giúp phân biệt lỗi vật lý, lỗi chuyển mạch và lỗi ở tầng cao hơn.

## 8. Những ngộ nhận thường gặp

- **“Có MAC thì xác định được người dùng.”** Sai: MAC có thể được đặt lại hoặc giả mạo; danh tính cần cơ chế xác thực và liên kết với hệ thống quản lý thiết bị.
- **“Switch chỉ hoạt động ở tầng 2.”** Không luôn đúng: switch quản lý có chức năng L3, ACL, VXLAN hoặc chức năng bảo mật bổ sung.
- **“CRC bảo vệ dữ liệu khỏi kẻ tấn công.”** Sai: FCS/CRC phát hiện lỗi truyền tình cờ, không chứng minh nguồn phát hợp lệ hay tính bí mật.
- **“VLAN khác nhau thì chắc chắn không truy cập được nhau.”** Sai: định tuyến giữa VLAN cùng chính sách firewall/ACL quyết định kết nối liên VLAN.
- **“Thiết bị cùng subnet sẽ luôn nhìn thấy nhau.”** Chưa chắc: có thể lệch VLAN, port isolation, cấu hình host/firewall hoặc sự cố ARP.
- **“MACsec tương đương TLS.”** Không: MACsec bảo vệ liên kết Ethernet cụ thể, còn TLS được thiết kế để bảo vệ phiên giao tiếp của ứng dụng giữa các endpoint.
- **“Mạng full-duplex có va chạm Ethernet như dùng hub.”** Sai trong vận hành switched Ethernet full-duplex hiện đại; hiện tượng mất gói vẫn có thể do lỗi tín hiệu, congestion hoặc cấu hình.

## 9. Ghi nhớ để thiết kế mạng an toàn

Một thiết kế tốt liên kết ba câu hỏi: **bit có truyền ổn định không** (L1), **frame đi đúng miền và thiết bị được phép không** (L2), và **lưu lượng giữa các miền có đúng chính sách không** (L3 trở lên).

Về kỹ thuật, hãy bắt đầu từ chất lượng cáp/quang/RF và bảo vệ cổng vật lý; tiếp theo xác thực thiết bị, giới hạn VLAN, bảo vệ các giao thức điều khiển L2 và quan sát bảng MAC/neighbor; cuối cùng định tuyến có kiểm soát, mã hóa phù hợp và giám sát liên tục. Cách tiếp cận này giảm cả lỗi vận hành thường ngày lẫn các đường tấn công xuất phát từ nội bộ mạng LAN.
