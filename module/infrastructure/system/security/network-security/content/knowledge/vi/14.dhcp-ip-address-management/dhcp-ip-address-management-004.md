# Rogue DHCP server: phát hiện máy chủ DHCP trái phép và bảo vệ cấp phát địa chỉ IP

Trong chương **DHCP và IP management** của module **SECURITY_NETWORK_SECURITY**, **rogue DHCP server** là một máy chủ hoặc tiến trình DHCP cung cấp cấu hình mạng cho client **ngoài phạm vi được tổ chức cho phép**. Nó có thể là thiết bị do người khác vô tình cắm vào mạng, một máy ảo bị nối bridge sai, hoặc một thành phần cố ý phát thông tin mạng độc hại. Hậu quả không dừng ở việc cấp sai địa chỉ IP: client có thể bị đưa tới **gateway, DNS resolver hoặc tuyến mạng không đáng tin**, mất kết nối, lộ thông tin hoặc đi qua một điểm có khả năng theo dõi/chặn lưu lượng.

Phân tích rogue DHCP là ví dụ điển hình của phòng vệ theo nhiều lớp: hiểu **lưu lượng DHCP**, xác định **trust boundary tại switch/AP/VLAN**, ngăn server trái phép bằng **DHCP snooping và kiểm soát cổng**, đối chiếu **DHCP lease với IP address management (IPAM)**, rồi dùng log, packet capture và dữ liệu thiết bị để điều tra.

Sau bài học, bạn có thể:

- Mô tả DHCPv4 DORA, vai trò của DHCP relay và những trường thông tin cần quan sát khi có nhiều DHCP OFFER.
- Nhận diện tác động của rogue DHCP lên IP, subnet mask, default gateway, DNS và các tùy chọn khác.
- Phân biệt rogue DHCP với DHCP server hợp lệ thứ hai, lỗi relay, xung đột IP và rogue IPv6 Router Advertisement.
- Thiết kế kiểm soát bằng DHCP snooping, trusted/untrusted port, segmentation, NAC và quản lý cấu hình IPAM.
- Thu thập evidence để xác định **server nào đã cấp lease**, **thiết bị vật lý nào phát gói** và **client nào bị ảnh hưởng** mà không làm gián đoạn diện rộng.
- Xây dựng bộ kiểm thử phòng ngừa, phát hiện và khôi phục cho hệ thống doanh nghiệp, Wi-Fi, VPN hoặc cloud/hybrid.

## 1. DHCP bình thường hoạt động ra sao?

**DHCP (Dynamic Host Configuration Protocol)** cấp phát tự động cấu hình mạng, giúp máy trạm không cần nhập thủ công mỗi lần kết nối. Với IPv4, DHCP thường cung cấp địa chỉ IPv4, subnet mask, thời gian thuê (lease), default router, DNS resolver và một số tùy chọn phục vụ tổ chức. DHCPv4 dùng **UDP/67 tại server** và **UDP/68 tại client**.

### 1.1. DORA: Discover → Offer → Request → Acknowledge

~~~mermaid
sequenceDiagram
    participant C as Client mới vào VLAN 20
    participant S as DHCP server hợp lệ
    C->>S: DHCPDISCOVER (tìm server)
    S-->>C: DHCPOFFER (đề xuất IP, lease, options)
    C->>S: DHCPREQUEST (chọn offer / xin IP)
    S-->>C: DHCPACK (xác nhận lease và options)
    Note over C: Áp cấu hình IP, router, DNS
~~~

- **DHCPDISCOVER:** client chưa có cấu hình phù hợp thường phát broadcast trong broadcast domain để tìm dịch vụ DHCP.
- **DHCPOFFER:** một hoặc nhiều server có thể đề xuất địa chỉ cùng cấu hình; client chưa nhất thiết áp dụng ngay.
- **DHCPREQUEST:** client chọn đề xuất hoặc yêu cầu gia hạn địa chỉ, tùy trạng thái DHCP.
- **DHCPACK:** server xác nhận thông số lease. Một số trường hợp server từ chối bằng **DHCPNAK** hoặc client gửi **DHCPDECLINE** khi phát hiện địa chỉ không phù hợp.

Trong giai đoạn cấp phát đầu tiên, client có thể gửi từ **0.0.0.0:68 tới 255.255.255.255:67**. Phản hồi có thể broadcast hoặc unicast tùy trạng thái, cờ DHCP và cấu trúc mạng. Khi **gia hạn lease**, client thường liên hệ server đã cấp lease bằng unicast ở giai đoạn phù hợp; vì vậy không phải mọi lần gia hạn đều tạo lại đủ bốn bản tin DORA.

> **Điểm then chốt:** Khi nhiều DHCP server cùng có thể trả lời trong một VLAN, client có thể nhận **nhiều OFFER**. Client chọn offer thế nào phụ thuộc hệ điều hành, trạng thái và chính sách client; không thể khẳng định server có OFFER đầu tiên sẽ luôn thắng.

### 1.2. DHCP options quan trọng với bảo mật

| Trường / option DHCPv4 | Chức năng | Rủi ro khi nhận giá trị sai |
| --- | --- | --- |
| **yiaddr** | Địa chỉ IPv4 được đề xuất/cấp cho client | Trùng IP, ngoài subnet, không định tuyến được |
| **Option 1 – Subnet Mask** | Xác định phạm vi mạng trực tiếp | Route sai, mất liên lạc với host cùng VLAN |
| **Option 3 – Router** | Default gateway cho client | Mất Internet hoặc lưu lượng tới gateway trái phép |
| **Option 6 – Domain Name Server** | DNS resolver client sẽ sử dụng | Phân giải sai, theo dõi tên truy vấn, dẫn đến endpoint giả |
| **Option 15 – Domain Name** | Tên miền liên quan cấu hình máy | Lỗi tìm tên nội bộ hoặc search suffix sai tùy client |
| **Option 51 – IP Address Lease Time** | Thời hạn thuê địa chỉ | Lease quá ngắn gây churn; quá dài kéo dài cấu hình sai |
| **Option 54 – DHCP Server Identifier** | Định danh server theo quy tắc DHCPv4 | Giúp nhận biết server được chọn, nhưng chưa phải chứng cứ xác thực mật mã |
| **Option 58/59 – T1/T2** | Các mốc làm mới và rebinding lease | Ảnh hưởng thời điểm client tìm lại server |
| **Option 82 – Relay Agent Information** | Metadata do thiết bị trung gian hỗ trợ thêm | Hỗ trợ xác định nguồn/đường đi khi thiết bị và chính sách cho phép |
| **Option 121 – Classless Static Route** | Cung cấp các tuyến cụ thể nếu client hỗ trợ | Có thể đổi đường đi đến mạng nội bộ hoặc dịch vụ nhạy cảm |

Không phải client hay hệ điều hành nào cũng áp dụng mọi option. Ví dụ, client có thể bỏ qua một tùy chọn không hỗ trợ hoặc ưu tiên cơ chế cấu hình khác. Khi điều tra, cần so sánh **option nằm trong OFFER/ACK** với **route, DNS và IP thực tế client đã áp dụng**.

### 1.3. DHCP relay và ranh giới VLAN

Broadcast DHCPDISCOVER ban đầu thường không tự đi qua router. Khi DHCP server phục vụ nhiều VLAN, **DHCP relay agent** (trên router, L3 switch hoặc thiết bị tương đương) chuyển tiếp yêu cầu tới server theo cấu hình, có thể đặt trường **giaddr** để biểu thị mạng nhận yêu cầu.

~~~mermaid
flowchart LR
    C["Client trong VLAN 20"] --> S["Access switch"]
    S --> R["DHCP relay / L3 gateway"]
    R -->|Chuyển tiếp yêu cầu| D["DHCP server được phép"]
    D -->|Trả lời qua relay| R
    R --> S
    S --> C
~~~

Một server DHCP trái phép trên **cùng broadcast domain** có thể trả lời trực tiếp trước khi relay hoàn tất xử lý; chỉ cấu hình đúng DHCP server trung tâm **không đủ** để ngăn host khác tự gửi OFFER/ACK ở access network. Ngược lại, một relay bị cấu hình sai có thể khiến client nhận lease từ server không đúng dù không có thiết bị lạ trong VLAN.

## 2. Rogue DHCP server là gì và xuất hiện từ đâu?

**Rogue** nói tới **trạng thái không được ủy quyền**, không nhất thiết nói tới mục đích xấu. Một router gia đình kết nối nhầm cổng LAN vào mạng công ty và vẫn bật DHCP có thể gây sự cố tương đương một thiết bị cố ý giả mạo.

| Nguồn phát DHCP ngoài dự kiến | Ví dụ | Tác động thường gặp |
| --- | --- | --- |
| **Router/AP cá nhân** | Cắm cổng LAN của router dân dụng vào switch công ty, DHCP mặc định còn bật | Client nhận sai gateway/DNS hoặc sai dải IP |
| **Máy tính/VM chia sẻ Internet** | Bật Internet Connection Sharing, phần mềm lab hoặc bridge sai | Xuất hiện OFFER trong VLAN doanh nghiệp |
| **Thiết bị IoT hoặc appliance** | Thiết bị có chế độ DHCP server để phục vụ mạng riêng nhưng được nối sai | Gây cạnh tranh cấp phát hoặc xung đột |
| **Server không còn được phê duyệt** | DHCP cũ chưa tắt sau migration | Nhiều policy cấp IP/option khác nhau |
| **Sai cấu hình DHCP relay/helper** | Chuyển tiếp yêu cầu tới cả DHCP server không còn được sử dụng | Cấp lease khác mong muốn qua đường hợp lệ về mặt routing |
| **Hành vi có chủ đích** | Endpoint phát OFFER mang router hoặc DNS do đối tượng kiểm soát | Có thể phá kết nối, đổi đường đi, gây theo dõi hoặc hỗ trợ tấn công tiếp |

### 2.1. Mô hình đường tấn công

~~~mermaid
flowchart TD
    C["Client mới kết nối VLAN người dùng"] --> Q["Gửi DHCPDISCOVER"]
    Q --> A["DHCP server được phép"]
    Q --> B["Rogue DHCP server cùng phạm vi nhận broadcast"]
    A --> OA["OFFER hợp lệ"]
    B --> OB["OFFER chứa options không được phê duyệt"]
    OA --> X{"Client chọn offer nào?"}
    OB --> X
    X -->|Chọn hợp lệ| G["IP/router/DNS theo chính sách"]
    X -->|Chọn rogue| R["Áp cấu hình trái phép hoặc bị từ chối"]
    R --> I["Mất kết nối, đổi DNS/route hoặc rủi ro dữ liệu"]
~~~

Việc có rogue server **không đảm bảo** mọi client đều nhận cấu hình sai. Những client đã có lease hợp lệ, đang dùng IP tĩnh hoặc chưa renew có thể chưa bị ảnh hưởng; hệ điều hành và thời điểm gia hạn cũng tạo sự khác biệt.

### 2.2. Các hậu quả có thể xảy ra

1. **Denial of service:** client nhận địa chỉ không thuộc subnet, gateway không tồn tại hoặc cấu hình gây lỗi định tuyến; người dùng mất mạng dù switch và Wi-Fi còn kết nối.
2. **DNS redirection:** Option 6 trỏ đến resolver không được phê duyệt; kết quả DNS có thể bị thao túng hoặc bị ghi nhận ngoài chính sách.
3. **Gateway redirection:** Option 3 chỉ tới thiết bị lạ. Nếu thiết bị đó thực sự chuyển tiếp được lưu lượng và các điều kiện đường đi đáp ứng, nguy cơ nghe lén/chèn sửa có thể tăng; nếu không, hậu quả thường là mất kết nối.
4. **Route manipulation:** một số DHCP option có thể tác động bảng định tuyến trên client hỗ trợ, dẫn tới lưu lượng vào đường không mong muốn.
5. **Sai lệch IPAM:** lease trên endpoint không tồn tại trong cơ sở dữ liệu DHCP/IPAM được quản trị; khó truy dấu tài sản và có thể xung đột IP.
6. **Gián đoạn quy trình bảo mật:** DNS filtering, proxy, VPN split tunneling, network access control hoặc endpoint monitoring dựa vào cấu hình mạng có thể không hoạt động như thiết kế.

**DHCP không phải cơ chế xác thực dịch vụ hoặc mã hóa traffic ứng dụng.** Một rogue DHCP có thể làm lệch cấu hình mạng, nhưng việc đánh cắp nội dung HTTPS còn phụ thuộc xác thực TLS, chính sách trust của client, đường truyền và những điều kiện khác. Không suy từ “gateway bị đổi” thành “mọi dữ liệu đã bị giải mã”.

## 3. Dấu hiệu nhận biết rogue DHCP trên mạng

Một số triệu chứng rất dễ bị nhầm với DNS, firewall, lỗi Wi-Fi hoặc xung đột IP bình thường. Cần kết hợp nguồn dữ liệu trước khi kết luận.

| Hiện tượng | Có thể do rogue DHCP? | Những nguyên nhân khác cần loại trừ |
| --- | --- | --- |
| Máy cùng VLAN nhận **gateway hoặc DNS khác nhau** không theo policy | Có, nhiều nguồn cấp options | VLAN/policy có nhiều scope hợp lệ, IP tĩnh, VPN/MDM |
| Máy nhận IP **ngoài pool** hoặc subnet dự kiến | Có | DHCP scope sai, relay giaddr sai, IP tự gán |
| Đổi mạng hoặc renew xong mất Internet | Có | DNS lỗi, route sai, captive portal, DHCP server chính quá tải |
| DNS trả kết quả bất thường trên một nhóm client | Có thể do Option 6 sai | Cache, split DNS, DNSSEC, proxy/VPN, resolver bị lỗi |
| Log thấy nhiều DHCP OFFER cho cùng một yêu cầu | Có thể, cần so server ID | DHCP failover hoặc nhiều server hợp lệ được cấu hình |
| Client tự nhận **169.254.0.0/16** | Có thể do không lấy được lease | DHCP hợp lệ không phản hồi, chặn DHCP, AP/switch lỗi |
| DHCP server có lease đúng nhưng client dùng IP khác | Có thể | Lease cũ, địa chỉ tĩnh, VM/container network, nguồn DHCP thứ hai |
| Chỉ một tầng Wi-Fi hoặc một switch gặp lỗi | Có thể rogue cắm gần đó | SSID–VLAN mapping sai, DHCP relay không đúng, lỗi access port |

**169.254/16** là phạm vi IPv4 link-local thường được client chọn khi không có cấu hình IPv4 phù hợp theo khả năng của hệ thống. Nó **không tự chứng minh** có rogue DHCP; cũng không được xem là một lease do DHCP server trái phép cấp.

### 3.1. Ba dấu hiệu quan trọng trong packet capture

Khi phân tích DHCPv4, tập trung:

- **Cùng transaction ID (xid) và client identity** có một hay nhiều DHCPOFFER? Phải ghép theo thời gian, client hardware address/chaddr và thông tin giao thức; một trường riêng lẻ có thể bị giả mạo hoặc trùng.
- **Option 54** (server identifier), địa chỉ nguồn và MAC của Ethernet frame có khớp inventory DHCP hợp lệ không? Trong lưu lượng qua relay, các trường này có thể chỉ những thành phần khác nhau.
- **Option 3/6 và lease** trong DHCPACK nào cuối cùng được client áp dụng? DHCPOFFER đơn thuần không chứng minh client đã chấp nhận đề xuất đó.

Các bản tin DHCP có thể xuất hiện qua broadcast hoặc unicast; nguồn IP của packet không phải lúc nào cũng là định danh tốt nhất của server. Sử dụng **server identifier, giaddr, Option 82, interface/VLAN và log phía server** cùng nhau.

## 4. Ví dụ phân tích hai DHCP OFFER cạnh tranh

Giả sử VLAN 20 có mạng **10.40.20.0/24**. DHCP server được phép là **10.40.20.5**, default gateway chuẩn là **10.40.20.1**, DNS nội bộ là **10.40.0.53**. Một thiết bị chưa được quản trị tại **10.40.20.250** cũng gửi OFFER.

| Thông tin | OFFER từ server hợp lệ | OFFER từ thiết bị chưa được duyệt |
| --- | --- | --- |
| DHCP message | DHCPOFFER | DHCPOFFER |
| Transaction ID | 0x5a12c031 | 0x5a12c031 |
| Client MAC | 02:11:22:33:44:55 | 02:11:22:33:44:55 |
| Option 54 – Server Identifier | 10.40.20.5 | 10.40.20.250 |
| IP đề xuất | 10.40.20.108/24 | 10.40.20.180/24 |
| Router (Option 3) | 10.40.20.1 | 10.40.20.254 |
| DNS (Option 6) | 10.40.0.53 | 10.40.20.253 |
| Lease time | 8 giờ | 30 phút |
| Trạng thái trong inventory | Approved | Unknown |

**Giải thích:** Hai OFFER đề xuất cấu hình khác nhau cho cùng một yêu cầu, cho thấy có nhiều nguồn cấp cấu hình. Tuy nhiên, **chưa thể kết luận client đã dùng server trái phép**. Cần tìm DHCPREQUEST, DHCPACK và cấu hình IP/gateway/DNS đang hoạt động trên client.

Ví dụ chuỗi sự kiện tiếp theo:

~~~text
10:04:11.002  DHCPDISCOVER  client=02:11:22:33:44:55  xid=0x5a12c031
10:04:11.019  DHCPOFFER     server_id=10.40.20.250  router=10.40.20.254
10:04:11.036  DHCPOFFER     server_id=10.40.20.5    router=10.40.20.1
10:04:11.070  DHCPREQUEST   requested=10.40.20.180 server_id=10.40.20.250
10:04:11.084  DHCPACK       server_id=10.40.20.250 router=10.40.20.254
10:04:11.120  Client        IP=10.40.20.180 gateway=10.40.20.254
~~~

Đây là **log tổng hợp giả định**, không phải bằng chứng từ hệ thống thật. Nó cho thấy client đã chọn đề xuất từ server chưa được duyệt và nhận ACK tương ứng. Để xác định **thiết bị phát gói**, tiếp tục liên kết **MAC nguồn của frame**, VLAN, port switch, AP association hoặc bảng chuyển tiếp MAC; không mặc định IP trong Option 54 là bằng chứng không thể giả mạo.

## 5. Xác định vị trí rogue DHCP và dựng evidence

### 5.1. Dòng điều tra từ client đến cổng vật lý

~~~mermaid
flowchart TD
    A["Client nhận IP/gateway/DNS bất thường"] --> B["Lưu cấu hình client, timestamp, VLAN, lease"]
    B --> C["Capture DHCPDISCOVER/OFFER/REQUEST/ACK"]
    C --> D["Xác định server_id, MAC nguồn, giaddr, Option 82"]
    D --> E{"Server có trong danh sách được phép?"}
    E -- "Có" --> F["Kiểm tra scope, failover, relay và thay đổi cấu hình"]
    E -- "Không / Chưa rõ" --> G["Đối chiếu MAC table, port, AP/SSID, LLDP và sơ đồ mạng"]
    G --> H["Xác minh thiết bị thực tế và chủ sở hữu"]
    H --> I["Cô lập có kiểm soát, phục hồi lease, kiểm chứng và giữ bằng chứng"]
    F --> I
~~~

### 5.2. Những nguồn bằng chứng cần ghép

| Nguồn | Bằng chứng hữu ích | Giới hạn |
| --- | --- | --- |
| **Client** | IP/prefix, gateway, DNS, DHCP server identifier, lease acquired/expires, interface và VLAN | Client có thể nhận cấu hình khác sau khi renew; cần ghi thời điểm |
| **Packet capture** | DISCOVER/OFFER/REQUEST/ACK, xid, option values, Ethernet source MAC, relay info | Chỉ thấy traffic tại điểm capture; có thể bỏ gói hoặc sai điểm mạng |
| **Switch DHCP snooping log** | Vi phạm server message từ untrusted port, VLAN, interface, MAC | Phụ thuộc việc bật feature và độ chi tiết log/counter của vendor |
| **MAC address table / LLDP** | MAC học trên switch port/uplink nào; thiết bị lân cận | MAC có thể đổi/spoof; học qua trunk/AP không luôn định danh thiết bị cuối |
| **Wi-Fi controller/AP** | SSID–VLAN, MAC client, AP association, bridge path | Client phía AP không nhất thiết xuất hiện ở một switch port riêng |
| **DHCP server hợp lệ** | Lease history, scope, reservation, failover partner | Không thấy lease của rogue không chứng minh client không có cấu hình |
| **IPAM / CMDB** | Danh sách approved server, pool, VLAN, gateway, DNS, owner | Inventory có thể lỗi thời |
| **Firewall, DNS, proxy và endpoint** | Dấu hiệu client truy cập resolver/gateway không chuẩn, lưu lượng bị đổi đường | Một dấu hiệu downstream không thay thế DHCP packet evidence |

**MAC address và Option 54 có thể bị giả mạo.** Nếu sự kiện quan trọng, phải liên kết nhiều nguồn và xác minh thiết bị ở đường mạng thực tế; không tùy tiện quy kết một người dùng chỉ từ địa chỉ mạng.

### 5.3. Thu thập và bảo quản

Một case nên lưu: timestamp có múi giờ, client MAC/IP, switch/AP/VLAN, server identifier, cấu hình lease, PCAP hoặc event ID, trạng thái DHCP snooping, đường uplink/relay, thay đổi gần thời điểm phát sinh và kết quả xác minh thiết bị. Giới hạn PCAP vào phạm vi cần thiết; dữ liệu có thể chứa MAC, hostname, domain và thông tin định danh tài sản.

Giữ bản gốc ở nơi phân quyền phù hợp, ghi người thu thập và thời gian, có thể tính hash SHA-256 cho tệp PCAP và phân tích trên bản sao. **Hash chỉ chứng minh tệp không bị thay đổi sau khi tạo hash**, không khẳng định dữ liệu capture đã bao phủ toàn bộ VLAN.

## 6. DHCP snooping: control cốt lõi ở tầng truy cập

**DHCP snooping** là chức năng của một số switch để phân biệt cổng tin cậy (*trusted*) và không tin cậy (*untrusted*) đối với lưu lượng DHCP. Với DHCPv4, nó có thể **ngăn DHCP server message không hợp lệ phát ra từ cổng untrusted**, đồng thời xây dựng bảng ánh xạ lease phục vụ kiểm soát khác. Cách hoạt động chi tiết phụ thuộc nhà cung cấp và cấu hình.

### 6.1. Trusted và untrusted port

~~~mermaid
flowchart TD
    C["Client trên access port\nUNTRUSTED"] --> S["Access switch bật DHCP snooping cho VLAN 20"]
    X["Thiết bị rogue trên access port\nUNTRUSTED"] --> S
    S -->|Trusted uplink theo topology| R["DHCP relay / Server hợp lệ"]
    R -->|DHCP OFFER/ACK được phép| S
    S -->|Forward ACK hợp lệ| C
    S -. "Drop/alert OFFER từ rogue" .-> L["Switch logs / SOC"]
~~~

Nguyên tắc triển khai:

- **Bật DHCP snooping trên đúng VLAN** có client và lưu lượng DHCP liên quan.
- **Access port cho endpoint** thường là **untrusted**, vì endpoint không được phép cấp lease cho các máy khác.
- Chỉ đánh dấu **trusted** cho cổng mà topology thực sự cho phép **server/relay đã được duyệt** gửi DHCP server message đi qua.
- Cân nhắc **trunk, uplink, Wi-Fi AP, hypervisor và relay**: một trunk mang nhiều VLAN không tự động nên được tin toàn bộ nếu không rõ thiết bị và đường DHCP hợp lệ ở mỗi VLAN.
- Kiểm tra chính sách **Option 82, rate limiting DHCP packets và bảng binding** theo khả năng thiết bị. Cấu hình sai có thể chặn DHCP hợp lệ.
- Duy trì **monitoring** vì cấu hình port bị thay đổi hoặc uplink bị thay thế có thể làm mất coverage.

Một thiết bị rogue nằm **phía sau cổng đã được trust** có thể không bị loại bởi cơ chế snooping tại switch access đó. Vì vậy cần giới hạn trust domain, bảo vệ uplink và quản lý đường nối vật lý/hypervisor/Wi-Fi, thay vì xem DHCP snooping là tuyệt đối.

### 6.2. DHCP snooping binding table dùng để làm gì?

Switch có thể ghi lại **MAC – IP – VLAN – interface – thời gian lease** của client DHCP hợp lệ:

~~~text
VLAN  MAC                IP             Port       Lease remaining
20    02:11:22:33:44:55  10.40.20.108   Gi1/0/12  05:42:00
20    02:66:77:88:99:aa  10.40.20.109   Gi1/0/18  06:10:00
~~~

Đây là **dữ liệu minh họa**. Bảng này có thể được sử dụng bởi các công nghệ liên quan:

| Control | Chức năng | Cần lưu ý |
| --- | --- | --- |
| **Dynamic ARP Inspection (DAI)** | Kiểm tra ARP dựa trên binding hoặc policy phù hợp | Cần cơ chế cho host IP tĩnh; dữ liệu binding sai gây chặn nhầm |
| **IP Source Guard** | Hạn chế gói nguồn IP/MAC không phù hợp binding trên access port | Phụ thuộc loại traffic, thiết bị và chính sách; không thay auth ứng dụng |
| **DHCP snooping** | Ngăn server message từ cổng không tin cậy và học binding | Không tự xác minh mật mã danh tính server, không xử lý mọi tấn công lớp 3/7 |

**DHCP snooping không phải firewall toàn năng.** Nó đặc biệt hữu ích ở ranh giới L2 nơi client có thể nhận DHCP broadcast, còn DNS security, phân đoạn, Wi-Fi authentication, VPN/ZTNA, IDS/IPS và kiểm soát ứng dụng vẫn cần triển khai theo threat model.

### 6.3. Option 82 và relay: hỗ trợ truy vết nhưng cần tương thích

**DHCP Option 82** có thể mang thông tin như circuit ID hoặc remote ID do thiết bị trung gian thêm vào. Một số hệ thống sử dụng nó để phân biệt cổng/đường truy cập và áp scope đúng. Tuy nhiên:

- Không tin Option 82 do endpoint tùy tiện tự gửi nếu hạ tầng không kiểm soát.
- Switch/relay có thể thêm, thay hoặc loại bỏ Option 82 theo policy; hành vi giữa thiết bị khác nhau.
- Server và relay phải tương thích cách xử lý Option 82; cấu hình không khớp có thể làm client không nhận được lease.
- Định danh trong Option 82 thường chỉ giúp truy nguồn đến **đường mạng/thiết bị**, không đủ để xác thực danh tính con người.

## 7. Các lớp bảo vệ bổ sung

### 7.1. Kiểm soát truy cập vật lý và thiết bị

Các biện pháp thực tế gồm:

1. Tắt hoặc giới hạn cổng switch không sử dụng; kiểm soát việc thay đổi cấu hình cổng.
2. Sử dụng **802.1X/NAC** và chính sách cấp VLAN phù hợp cho thiết bị được quản lý.
3. Giới hạn MAC/port security khi phù hợp để giảm thiết bị cắm ngoài ý muốn, đồng thời hiểu rằng MAC có thể bị spoof.
4. Kiểm kê AP, router cá nhân, IP phone, IoT và hypervisor có khả năng chạy DHCP server.
5. Tách **guest, user, IoT, management và server VLAN**, áp trust boundary rõ ràng.

Một cổng đã xác thực 802.1X **không tự chứng minh endpoint sạch**: máy được cấp quyền vẫn có thể vô tình bật dịch vụ DHCP. Vì vậy NAC và DHCP snooping nên bổ trợ cho nhau.

### 7.2. Quản lý DHCP server, scope và IPAM

Tổ chức nên duy trì **nguồn sự thật** cho các trường:

| Nội dung IPAM/CMDB | Ví dụ | Vai trò |
| --- | --- | --- |
| VLAN và prefix | VLAN 20 / 10.40.20.0/24 | Định nghĩa broadcast domain được bảo vệ |
| DHCP server/relay được duyệt | 10.40.20.5 / gateway relay | Làm baseline phân biệt server lạ |
| Pool, exclusion và reservation | 10.40.20.100–200 | Tránh trùng IP và quản lý cấp phát |
| Gateway chính thức | 10.40.20.1 | Phát hiện Option 3 sai |
| DNS resolver theo chính sách | 10.40.0.53 | Phát hiện Option 6 sai, phối hợp DNS filtering |
| Lease time và DHCP options | Lease 8 giờ, route policy | Phát hiện thay đổi hoặc scope ngoài dự kiến |
| Trusted switch ports và owner | Uplink được xác minh | Cấu hình và audit DHCP snooping |
| DHCP failover/HA topology | Các server đã được phê duyệt | Tránh gọi nhầm server hợp lệ là rogue |

Giám sát **cấu hình DHCP server**, thay đổi DNS/router options, cập nhật firmware và bảo vệ quyền quản trị là cần thiết. Rogue DHCP có thể xuất hiện từ **server hợp lệ bị thay đổi cấu hình sai**, nên chỉ nhìn IP server có thuộc danh sách approved chưa đủ.

### 7.3. Giám sát chủ động và phản ứng

Có thể kết hợp:

- **DHCP snooping violation log/counter** trên switch access.
- **Passive DHCP discovery** từ port mirror hoặc sensor IDS/NDR theo từng VLAN.
- **So sánh OFFER/ACK và Option 54** với inventory, xem các IP/MAC/giaddr không mong đợi.
- **Endpoint telemetry** về DHCP server, default gateway, DNS thay đổi bất thường.
- **DNS/firewall log** để phát hiện lưu lượng tới DNS resolver hoặc gateway không thuộc danh sách quản lý.
- **Alert thay đổi cấu hình** trên switch, Wi-Fi controller, relay và DHCP server.

Việc giám sát cần giảm noise: DHCP server HA, relay hợp lệ, VM lab đã được cấp quyền hoặc thay đổi pool theo kế hoạch không nên bị coi là tấn công. Định nghĩa alert có **context VLAN, port, server ID, thời gian, scope** và chủ sở hữu hệ thống.

## 8. Phân biệt DHCPv4, DHCPv6 và rogue Router Advertisement

Trong mạng **IPv6**, cơ chế cấu hình khác IPv4:

- **DHCPv6** dùng **UDP/546 ở client** và **UDP/547 ở server/relay**. Nó có thể cấp địa chỉ và những thông tin cấu hình theo chế độ.
- **Router Advertisement (RA)** theo ICMPv6 cung cấp thông tin router/default gateway và các tín hiệu về SLAAC/DHCPv6. DHCPv6 **không cấp default router theo cùng kiểu Option 3 của DHCPv4**.
- Client có thể có địa chỉ IPv6 qua **SLAAC**, **DHCPv6 stateful** hoặc mô hình kết hợp; hành vi và hỗ trợ tùy hệ điều hành.
- Một **rogue RA** có thể quảng bá router/prefix không đúng dù **không có rogue DHCPv6 server**.

| Mối đe dọa | Giao thức/thông điệp | Kiểm soát ở access network |
| --- | --- | --- |
| Rogue DHCPv4 | DHCPOFFER/DHCPACK qua UDP 67/68 | **DHCP snooping cho IPv4** nếu switch hỗ trợ |
| Rogue DHCPv6 | DHCPv6 Advertise/Reply và thông điệp liên quan qua UDP 546/547 | **DHCPv6 Guard** hoặc tính năng tương đương nếu hỗ trợ |
| Rogue IPv6 router | ICMPv6 Router Advertisement | **RA Guard** và chính sách thiết bị nguồn tin cậy |
| IPv6 neighbor spoofing | ICMPv6 Neighbor Discovery | ND inspection/SAVI hoặc các cơ chế tương đương tùy hạ tầng |

**Không dùng DHCPv4 snooping làm bằng chứng toàn bộ IPv6 đã được bảo vệ.** Ngược lại, chặn bừa mọi ICMPv6 có thể phá Neighbor Discovery, Router Advertisement hợp lệ và Path MTU Discovery. Policy IPv6 cần được thiết kế riêng, có kiểm thử chức năng.

## 9. Kiểm tra cấu hình client và packet capture

Chỉ sử dụng công cụ trên **thiết bị hoặc mạng được cấp quyền kiểm tra**. Phần lớn thao tác đầu tiên nên là **đọc trạng thái**, chưa vội renew hàng loạt vì có thể xóa mất bằng chứng lease cũ hoặc gây gián đoạn.

### 9.1. Windows

~~~powershell
# Xem địa chỉ IPv4, DHCP Enabled, DHCP Server, gateway, DNS, lease time.
ipconfig /all

# Xem IP và gateway theo interface.
Get-NetIPConfiguration

# Xem DNS resolver theo interface (IPv4).
Get-DnsClientServerAddress -AddressFamily IPv4
~~~

Hãy lưu lại **tên interface, MAC, DHCP server, Lease Obtained/Expires, IPv4, mask, gateway, DNS** cùng thời điểm thu thập. Nếu máy có nhiều adapter (Wi-Fi, Ethernet, VPN, VM), không được mặc định adapter đầu tiên là đường mạng đang gây lỗi.

### 9.2. Linux

~~~bash
# Cấu hình IP, route và default gateway.
ip -4 address show
ip -4 route show

# Xem thông tin IP, DHCP options nếu máy dùng NetworkManager.
nmcli device show

# Xem resolver hiện hành nếu hệ thống dùng systemd-resolved.
resolvectl status

# Quan sát tối đa 40 packet DHCPv4 trên interface được phép.
sudo tcpdump -ni eth0 -c 40 '(udp port 67 or udp port 68)'

# Quan sát tối đa 40 packet DHCPv6, nếu cần phân tích IPv6.
sudo tcpdump -ni eth0 -c 40 '(udp port 546 or udp port 547)'
~~~

Tên interface **eth0** chỉ là ví dụ; nhiều hệ thống dùng tên khác. Trên một số mạng, capture ở client có thể **không thấy OFFER gửi unicast tới client khác**. Muốn quan sát toàn bộ VLAN cần dùng **SPAN/TAP** hoặc sensor ở vị trí thích hợp, được cấu hình và cấp quyền đúng.

Trong **Wireshark**, những display filter hữu ích:

~~~text
bootp
udp.port == 67 || udp.port == 68
bootp.option.dhcp == 2
bootp.option.dhcp == 5
dhcpv6
udp.port == 546 || udp.port == 547
icmpv6.type == 134
~~~

Trong nhiều phiên bản Wireshark, DHCPv4 vẫn sử dụng tên trường **bootp**. Với các filter theo option, cần kiểm tra danh sách field của phiên bản đang dùng. **DHCP message type 2** là OFFER và **5** là ACK; **ICMPv6 type 134** là Router Advertisement.

### 9.3. Cần đọc gì trong packet?

1. **Frame:** MAC nguồn/đích, VLAN tag nếu quan sát được, interface/sensor.
2. **IPv4/UDP:** nguồn/đích, UDP/67–68; trạng thái broadcast/unicast.
3. **DHCP:** transaction ID, chaddr/client ID, message type, Option 54, yiaddr, Option 1/3/6/51 và Option 82 nếu có.
4. **Thời gian:** OFFER nào, REQUEST nào, ACK nào liên quan cùng client và giao dịch?
5. **Kiểm chứng sau cấp phát:** client có thực sự cấu hình IP/gateway/DNS tương ứng không?

Không cần thu thập payload không liên quan. Capture có thể ghi hostname, MAC và metadata thiết bị; áp dụng kiểm soát truy cập và thời hạn lưu theo chính sách tổ chức.

## 10. Quy trình ứng phó rogue DHCP theo mức độ rủi ro

### Bước 1 — Xác nhận phạm vi và triệu chứng

Ghi nhận thời gian, tòa nhà/tầng, SSID, VLAN, switch, số client bị ảnh hưởng và thay đổi gần nhất. Phân biệt người dùng mất mạng vì **không nhận được lease** với người nhận **lease sai**.

### Bước 2 — Thu bằng chứng trước khi thay cấu hình

Sao lưu cấu hình IP/gateway/DNS của vài client đại diện, DHCP events, switch snooping logs, capture ngắn ở đúng broadcast domain và inventory DHCP. Nếu có nhiều server hợp lệ/failover, đối chiếu chúng trước khi gắn nhãn rogue.

### Bước 3 — Xác định server và đường phát traffic

Dựa vào Option 54 và DHCPACK để nhận biết server đã cấp lease; liên kết với Ethernet MAC nguồn, **switch MAC table**, LLDP, AP association hoặc MAC học phía trunk. Nếu server ở phía sau relay, kiểm tra **giaddr** và cấu hình helper trên L3 gateway.

### Bước 4 — Ngăn ảnh hưởng bằng biện pháp có kiểm soát

Ưu tiên loại bỏ nguồn DHCP trái phép ở **cổng hoặc thiết bị đã được xác nhận**, hoặc dùng cấu hình DHCP snooping/ACL phù hợp và đã kiểm thử. Nếu port chứa nhiều dịch vụ, voice VLAN, AP hoặc uplink chung, phải xét tác động trước khi disable. Có thể cần cơ chế change/incident response của tổ chức khi xử lý môi trường sản xuất.

### Bước 5 — Khôi phục client

Sau khi ngăn nguồn sai, kiểm tra DHCP server hợp lệ có phục vụ được không; trên các client bị ảnh hưởng, gia hạn lease hoặc kết nối lại **theo nhóm có kiểm soát**, đồng thời xác nhận:

- Địa chỉ IP/prefix thuộc pool đúng.
- Default gateway là router theo chính sách.
- DNS resolver và các tùy chọn nghiệp vụ chính xác.
- Truy cập DNS, dịch vụ nội bộ và Internet được phục hồi.
- Log cho thấy client nhận DHCPACK từ server được phê duyệt.

Không khẳng định toàn mạng đã phục hồi chỉ vì một client dùng lại được. Client chưa renew có thể còn giữ lease sai cho tới khi hết hạn hoặc tới kỳ gia hạn.

### Bước 6 — Rà soát bảo mật sau sự cố

Nếu rogue server đã cung cấp DNS/gateway trái phép, đánh giá **nguy cơ lưu lượng đã đi qua đích ngoài chính sách** trong thời gian có ảnh hưởng. Đối chiếu resolver/proxy/endpoint log và sự kiện xác thực phù hợp; kiểm tra liệu có dữ liệu nhạy cảm bị truy cập trái phép hay không. Không tự động kết luận có rò rỉ chỉ dựa trên DHCPACK.

Cuối cùng, ghi lại điểm yếu ở topology, cấu hình access switch, DHCP snooping, NAC/IPAM và quy trình onboarding thiết bị; chọn control bổ sung theo threat model.

## 11. Case study: router cá nhân gây lỗi DNS và gateway

### 11.1. Bối cảnh

Một văn phòng có VLAN 20, DHCP server chính **10.40.20.5**, gateway **10.40.20.1**, DNS nội bộ **10.40.0.53**. Một nhóm nhân viên bắt đầu mất truy cập ứng dụng khi chuyển từ Wi-Fi sang Ethernet. Trong cùng thời gian, đội support ghi nhận một router cá nhân được nối vào cổng switch để chia sẻ kết nối phòng họp.

Đội network chưa được phép khẳng định router này là nguyên nhân chỉ dựa trên vị trí gần sự cố.

### 11.2. Bằng chứng giả định

| Evidence | Quan sát | Suy luận hợp lý |
| --- | --- | --- |
| **E1 – client config** | Một số máy dùng gateway 10.40.20.254 và DNS 10.40.20.253 | Cấu hình không khớp baseline |
| **E2 – packet capture** | OFFER/ACK với Option 54 = 10.40.20.250, router/DNS không chuẩn | Có server DHCP ngoài danh sách được phép cung cấp cấu hình |
| **E3 – access switch** | MAC nguồn DHCP liên quan đến cổng Gi1/0/22, cùng VLAN 20 | Khoanh vùng nguồn vật lý cần xác minh |
| **E4 – inventory** | Gi1/0/22 không thuộc danh sách đường cấp DHCP, DHCP server approved chỉ có 10.40.20.5 | Có sai lệch so với chính sách |
| **E5 – kiểm tra hiện trường** | Router cá nhân trên Gi1/0/22 đang chạy DHCP server | Bằng chứng thiết bị thực tế phát DHCP trái phép |
| **E6 – sau containment** | Không còn OFFER lạ trong capture và client mới nhận cấu hình hợp lệ | Control đã có hiệu quả trong phạm vi kiểm thử |

### 11.3. Cách xử lý

1. Lưu lại cấu hình IP của client bị ảnh hưởng, event DHCP và danh sách port/thiết bị.
2. Xác minh Gi1/0/22 chỉ phục vụ thiết bị rogue trước khi cô lập cổng theo quy trình vận hành.
3. Ngừng khả năng phát OFFER trái phép vào VLAN 20; sau đó bật hoặc sửa DHCP snooping **theo topology được kiểm chứng**, không tự động trust mọi uplink.
4. Cho một số client bị ảnh hưởng renew có kiểm soát và kiểm tra cả gateway, DNS, phân giải tên, đường đi và ứng dụng.
5. Giám sát theo thời gian đủ để phát hiện client khác còn lease sai hoặc server rogue xuất hiện ở cổng khác.
6. Rà soát hướng dẫn sử dụng router/AP cá nhân, kiểm soát access port, onboarding thiết bị, Wi-Fi guest và inventory.

**Residual risk:** Một endpoint đã được cấp quyền vẫn có thể bật DHCP server ở access network nếu thiếu kiểm soát tại cổng, hoặc một thiết bị phía sau trusted uplink có thể không bị chặn bởi snooping tại switch đang xét. Cần kết hợp trust-zone review, inventory và giám sát thay đổi.

## 12. Thiết kế policy và bộ kiểm thử trước triển khai

### 12.1. Mẫu mô tả control

~~~yaml
# Mẫu mô tả để review, không phải cấu hình switch có thể áp trực tiếp.
control_id: NET-DHCP-004
objective: "Block unauthorized DHCPv4 server messages in user VLAN"
scope:
  vlans: [20]
  client_ports: "Access ports for user/guest endpoints"
  trusted_ports: "Only verified paths to approved DHCP server or relay"
approved_dhcp_servers:
  - "10.40.20.5"
allowed_network_parameters:
  prefix: "10.40.20.0/24"
  default_router: "10.40.20.1"
  dns_resolvers:
    - "10.40.0.53"
preventive_controls:
  - "DHCP snooping on VLAN 20"
  - "Access port trust review"
  - "802.1X/NAC as appropriate"
detective_controls:
  - "Snooping violation logs"
  - "DHCP offer server identifier inventory comparison"
owner: "Network Operations"
validation:
  - "Approved DHCP relay/server traffic is forwarded"
  - "Unauthorized DHCP server message on test untrusted port is blocked"
  - "Client obtains expected lease/options after policy change"
  - "Switch violation event can be correlated to interface/VLAN"
review_trigger: "New VLAN, AP, switch, relay or DHCP failover change"
~~~

Các địa chỉ, cổng, VLAN và tiêu chí trong mẫu phải được thay bằng thông tin topology thực. Nếu switch không hỗ trợ DHCP snooping, cần xem khả năng control thay thế, mức phơi nhiễm và rủi ro còn lại; một firewall ở giữa VLAN khác không nhất thiết thấy được OFFER giữa các host trong cùng VLAN.

### 12.2. Ma trận kiểm thử có quyền

| Test | Cách xác minh an toàn | Kết quả kỳ vọng |
| --- | --- | --- |
| **P1 – cấp lease bình thường** | Kết nối client lab vào VLAN test, quan sát DORA qua server được phép | Nhận IP/router/DNS đúng; server ID thuộc inventory |
| **P2 – gia hạn lease** | Cho client hợp lệ renew trong môi trường thử nghiệm | Không bị chặn bởi snooping hoặc sai relay |
| **P3 – relay qua VLAN** | Client test ở VLAN dùng DHCP relay, xem giaddr và server response | Relay/server hoạt động, OFFER/ACK tới đúng VLAN |
| **N1 – server không được phép** | Trong lab cô lập và được phê duyệt, phát một DHCP server message giả lập từ access port untrusted | Switch drop/ghi log theo policy; không cấp lease từ nguồn này |
| **N2 – sai Option 3/6** | Phân tích sample PCAP và baseline; không cấp lease độc hại trên mạng production | Alert hoặc đánh dấu sai lệch gateway/DNS |
| **N3 – wrong trusted port** | Review cấu hình trust và mô phỏng đường đi trong lab | Không có access port của client được trust ngoài phạm vi phê duyệt |
| **N4 – IPv6** | Đánh giá DHCPv6 Guard/RA Guard ở VLAN dual-stack bằng traffic test được cấp quyền | Rogue DHCPv6/RA bị xử lý theo chính sách mà IPv6 hợp lệ vẫn hoạt động |
| **O1 – telemetry** | Tạo một sự kiện vi phạm DHCP từ lab và truy vết log | Có thời gian, VLAN, interface, loại vi phạm và chủ sở hữu |
| **R1 – khôi phục** | Loại nguồn rogue trong lab, rồi renew client test | Cấu hình chuẩn được khôi phục, DNS và ứng dụng chạy đúng |

Không cần gây **DHCP starvation** hoặc phát nhiều OFFER trên VLAN production để thử policy; chọn lab cách ly, packet replay/simulator có kiểm soát hoặc chức năng test của thiết bị khi phù hợp. Trước thay đổi có nguy cơ làm mất mạng, chuẩn bị phương án quản trị ngoài băng và rollback.

## 13. Giám sát và chỉ số vận hành

| Chỉ số / tín hiệu | Ý nghĩa | Điều cần kiểm chứng |
| --- | --- | --- |
| Số **DHCP server IDs** khác inventory theo VLAN | Phát hiện nguồn cấp mới ngoài kế hoạch | Failover/relay hợp lệ có được khai báo chưa |
| Số **snooping violations** theo switch/port/VLAN | Quan sát attempt phát server message từ cổng untrusted | Có bị false positive do trust topology sai không |
| DHCP discover-to-ack latency | Trải nghiệm cấp phát và hiệu quả relay/server | Độ trễ tăng do server, network hay policy? |
| Tỷ lệ DHCP lease thành công/thất bại | Chất lượng dịch vụ DHCP | Có tách client cố định IP hoặc lỗi Wi-Fi không |
| Mức sử dụng pool và conflict rate | Phát hiện cạn IP, reservation sai hoặc xung đột | Không đồng nhất pool exhaustion với rogue DHCP |
| Tỷ lệ client có gateway/DNS sai baseline | Dấu hiệu cấu hình trái phép hoặc thay đổi scope | Kiểm tra VLAN/role/VPN và ngoại lệ đã phê duyệt |
| Thay đổi **trusted ports** và config snooping | Phát hiện drift cấu hình phòng ngừa | Có ticket/owner và kiểm thử sau thay đổi không |
| Endpoint đổi resolver/gateway ngoài lịch | Phát hiện sự kiện ảnh hưởng người dùng | Client có dùng VPN, Wi-Fi hoặc cấu hình tĩnh hợp lệ không |
| Phạm vi IPv6 Guard / RA Guard | Đảm bảo mạng dual-stack được xem xét | Không phá RA/ND hợp lệ |

Một tỷ lệ cảnh báo cao **không tự chứng minh** có nhiều rogue DHCP nguy hiểm. Có thể do thay đổi switch/VLAN, sự cố relay hoặc thiết bị thí nghiệm đã được ủy quyền. SOC/network team cần **triage dựa trên topology và trạng thái client**, không chỉ đếm event.

## 14. Những nhầm lẫn thường gặp

1. **“Có hai OFFER là chắc chắn bị tấn công.”** DHCP failover, nhiều DHCP server hợp lệ hoặc cấu hình dự phòng có thể tạo nhiều OFFER. Phải đối chiếu server inventory và policy.
2. **“Offer đầu tiên luôn thắng.”** Cách client chọn offer không phải quy luật tuyệt đối giống nhau trên mọi hệ điều hành.
3. **“Chỉ cần firewall ở router là chặn được rogue DHCP.”** Client và rogue server cùng VLAN có thể trao đổi ở L2 mà không đi qua router.
4. **“Option 54 chứng minh danh tính server.”** Server identifier hữu ích để correlate nhưng không được xác thực mật mã mặc định.
5. **“Bật DHCP snooping là xong.”** Trust ports, VLAN coverage, relay, AP, hypervisor, DHCPv6 và giám sát vẫn phải đúng.
6. **“Tất cả uplink/trunk đều nên trusted.”** Trust phải theo đường dẫn server/relay được phê duyệt; trust rộng tạo điểm bypass.
7. **“Không thấy rogue ACK là không có vấn đề.”** Capture có thể thiếu gói hoặc client chưa renew; cần kiểm tra đa điểm.
8. **“Client 169.254.x.x là đã nhận DHCP từ server lạ.”** Đây thường là IPv4 link-local fallback, không phải chứng cứ của rogue DHCP.
9. **“Rogue DHCP và DHCP starvation giống nhau.”** Rogue DHCP cấp cấu hình không được duyệt; starvation là hành vi/hiện tượng làm cạn địa chỉ cấp phát, có thể kết hợp nhưng là vấn đề khác.
10. **“DHCPv6 cấp gateway như DHCPv4.”** IPv6 default-router thông thường đến từ Router Advertisement, cần kiểm soát RA riêng.
11. **“Gateway sai nghĩa là nội dung HTTPS đã bị lộ.”** Cần chứng cứ về đường đi, TLS, các hệ thống liên quan và tác động thực tế.
12. **“Chỉ cần chặn thiết bị lạ rồi tất cả client tự đúng ngay.”** Lease cũ có thể vẫn tồn tại; cần kiểm chứng và khôi phục từng nhóm.
13. **“MAC/OUI là bằng chứng đủ để quy trách nhiệm.”** MAC có thể bị giả mạo hoặc học qua bridge/AP; cần xác nhận thiết bị và log thời gian phù hợp.
14. **“DHCP security thay thế bảo vệ DNS.”** Client vẫn cần DNS resolver đáng tin, DNSSEC/DoT/DoH khi phù hợp và bảo vệ ứng dụng.

## 15. Bài tập vận dụng và gợi ý đáp án

### Bài 1 — Đọc DHCP OFFER

Một client ở VLAN 20 nhận hai OFFER có **cùng xid và client MAC**. OFFER A có Option 54 là **10.40.20.5**, Option 3 là **10.40.20.1**. OFFER B có Option 54 là **10.40.20.250**, Option 3 là **10.40.20.254**. IPAM chỉ liệt kê **10.40.20.5** là DHCP server hợp lệ. Cần xem tiếp thông tin nào để xác định client có thật sự bị ảnh hưởng không?

**Gợi ý:** tìm DHCPREQUEST/ACK, IP/gateway/DNS mà client đã áp dụng, server identifier và MAC nguồn/port tương ứng. OFFER B cho thấy nguồn cần điều tra, nhưng không tự chứng minh lease được chọn.

### Bài 2 — Chọn trusted port

Một switch có 24 cổng: cổng 1–22 cho máy trạm, cổng 23 nối AP phục vụ Wi-Fi khách và cổng 24 nối tới L3 gateway chạy DHCP relay. Hãy xác định **vị trí cần xem xét để trust DHCP server messages** và giải thích vì sao không nên trust toàn bộ access ports.

**Gợi ý:** chỉ trust đúng đường từ relay/server hợp lệ theo tài liệu topology và cách AP/SSID/VLAN hoạt động; các access port của client thường để untrusted. Phải xác minh lưu lượng qua cổng AP, tránh suy luận chỉ từ vai trò vật lý của thiết bị.

### Bài 3 — Windows mất mạng sau khi nối Ethernet

Một máy Windows đang dùng **169.254.1.20/16**, không có gateway IPv4. Đội hỗ trợ kết luận ngay “rogue DHCP đã cấp sai IP”. Nhận định đó có đủ cơ sở không?

**Gợi ý:** chưa. Đây thường là địa chỉ link-local khi không lấy được IPv4 phù hợp. Kiểm tra đường L2, DHCPDISCOVER/OFFER, policy snooping, server hợp lệ, relay, VLAN và IP config trước khi quy kết rogue.

### Bài 4 — Mạng dual-stack vẫn bị chuyển gateway

Tổ chức bật DHCP snooping cho IPv4. Một số client IPv6 vẫn chọn default router lạ. Nên điều tra giao thức và control nào?

**Gợi ý:** kiểm tra **ICMPv6 Router Advertisement**, nguồn MAC/port, network prefix và **RA Guard** ở access network; đánh giá DHCPv6 Guard riêng. Không tìm Option 3 DHCPv4 để kết luận sự cố IPv6.

### Bài 5 — Viết kế hoạch phát hiện và ứng phó

Một khu vực có bốn VLAN (**USER**, **GUEST**, **IoT**, **MANAGEMENT**) và DHCP server trung tâm qua relay. Hãy xây dựng **threat→control→evidence** cho rogue DHCP trên USER và GUEST, nêu:

- Client hợp lệ được cấp thông tin IP/gateway/DNS thế nào?
- Các port nào được xem là trusted theo topology?
- Log hoặc packet evidence nào cần lưu khi có OFFER trái phép?
- Làm thế nào truy ra thiết bị thật từ Option 54 tới MAC/switch/AP?
- Khi cô lập một cổng có nguy cơ chung AP/uplink, kiểm soát gián đoạn ra sao?
- Khi nào có thể khẳng định client đã phục hồi và rủi ro còn lại là gì?

**Gợi ý:** ưu tiên xác minh thiết kế broadcast domain, DHCP relay, DHCP snooping và inventory, sau đó kiểm tra từng VLAN bằng test có quyền. Không mở trust toàn bộ hay renew hàng loạt trước khi lưu bằng chứng sự cố.

## 16. Ghi nhớ khi bảo vệ DHCP và quản lý IP

**Rogue DHCP server** là bất kỳ nguồn cấp DHCP nào **không được cho phép** theo chính sách mạng, dù xuất hiện do vô ý hay có chủ đích. Nó có thể làm sai **IP, router, DNS, route và lease**, ảnh hưởng tính sẵn sàng và tạo điều kiện cho các mối đe dọa khác. Để xác định một máy client thực sự bị tác động, cần đối chiếu **DHCPOFFER → DHCPREQUEST → DHCPACK → cấu hình client**, không dừng ở một OFFER hoặc một alert.

Trong kiến trúc **SECURITY_NETWORK_SECURITY**, lớp bảo vệ thiết thực là **DHCP snooping tại đúng access VLAN/port**, kết hợp **NAC, segmentation, inventory DHCP/IPAM, kiểm soát DHCP relay và giám sát lưu lượng**. Với mạng IPv6 cần xem xét **DHCPv6 Guard và RA Guard** riêng. Quy trình điều tra dùng packet capture, server identifier, switch/AP logs và dữ liệu lease để xác định nguồn gây sai lệch, phục hồi an toàn và ngăn sự cố tái diễn mà vẫn giữ các kết nối hợp lệ hoạt động.
