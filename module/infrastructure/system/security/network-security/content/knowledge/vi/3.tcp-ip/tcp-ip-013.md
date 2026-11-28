# DHCP và cấp phát địa chỉ trong mạng TCP/IP

DHCP (*Dynamic Host Configuration Protocol*) tự động cung cấp thông số mạng cho thiết bị khi kết nối vào một mạng TCP/IP. Thay vì nhập thủ công địa chỉ IP, mặt nạ mạng, cổng mặc định và máy chủ DNS trên từng máy, quản trị viên định nghĩa chính sách tại máy chủ DHCP. Máy khách nhận cấu hình, sử dụng trong một khoảng thời gian và gia hạn khi cần.

Trong hệ thống bảo mật mạng, DHCP vừa giúp quản lý địa chỉ tập trung, vừa là điểm cần bảo vệ: một DHCP giả mạo có thể phát địa chỉ gateway hoặc DNS độc hại, trong khi kẻ tấn công có thể chiếm dụng toàn bộ dải cấp phát. Bài học trình bày cơ chế **DHCPv4**, **DHCPv6**, cấp phát qua các VLAN, giám sát lưu lượng và các biện pháp phòng vệ.

## 1. DHCP giải quyết vấn đề gì?

Một máy tính dùng IPv4 muốn liên lạc hiệu quả thường cần các tham số sau:

| Tham số | Ví dụ | Vai trò |
| --- | --- | --- |
| Địa chỉ IPv4 | 192.168.40.105 | Định danh giao diện trong mạng IPv4 |
| Subnet mask / prefix | 255.255.255.0 hay /24 | Xác định địa chỉ nào thuộc cùng mạng con |
| Default gateway | 192.168.40.1 | Chuyển gói tin đến mạng khác |
| DNS resolver | 192.168.40.10 | Phân giải tên miền thành địa chỉ IP |
| Thời hạn thuê (*lease*) | 8 giờ | Khoảng thời gian máy khách được quyền dùng địa chỉ được cấp |
| Tùy chọn bổ sung | Tên miền tìm kiếm, NTP, tuyến tĩnh | Hỗ trợ các dịch vụ và chính sách nội bộ |

**DHCP không tự tạo kết nối Internet.** Máy khách vẫn cần đúng VLAN, đường đi đến gateway, định tuyến, DNS, chính sách firewall và đôi khi NAT. Có địa chỉ hợp lệ từ DHCP không đồng nghĩa với việc mọi dịch vụ đã thông.

Có bốn cách tổ chức địa chỉ phổ biến:

- **Địa chỉ tĩnh cấu hình trên thiết bị:** phù hợp với gateway, hạ tầng hoặc thiết bị yêu cầu định danh ổn định; người quản trị tự đảm bảo địa chỉ không trùng.
- **Cấp phát động qua DHCP:** địa chỉ lấy từ một *pool* trong thời hạn lease; phù hợp laptop, điện thoại và máy trạm.
- **Đặt trước địa chỉ (*DHCP reservation*):** máy khách vẫn nhận cấu hình qua DHCP nhưng máy chủ ưu tiên một địa chỉ cố định dựa trên định danh phù hợp, chẳng hạn client identifier hoặc MAC.
- **Cấp phát tự động lâu dài:** một số triển khai DHCP có thể giữ ổn định ánh xạ địa chỉ cho máy khách; chính sách này phụ thuộc máy chủ, khác với lease động thông thường.

Định danh máy khách không nhất thiết chỉ là MAC. DHCPv4 có thể dùng **Option 61 (Client Identifier)**, và tính năng MAC ngẫu nhiên trên Wi-Fi có thể làm reservation theo MAC hoặc việc ước lượng số thiết bị không còn chính xác.

## 2. Thành phần và phạm vi hoạt động của DHCPv4

Một hệ thống DHCPv4 gồm:

1. **DHCP client:** thiết bị yêu cầu thông số cấu hình.
2. **DHCP server:** quản lý scope, pool, reservation, lease và các DHCP option.
3. **DHCP relay agent:** chuyển yêu cầu từ mạng con này đến máy chủ ở mạng con khác.
4. **Thiết bị mạng:** switch, router, firewall và VLAN quyết định gói DHCP có đi đến đúng nơi không.

DHCPv4 dùng **UDP 68 ở máy khách** và **UDP 67 ở máy chủ**. Máy mới kết nối có thể chưa biết địa chỉ của mình hoặc của DHCP server, nên giai đoạn đầu thường sử dụng broadcast **255.255.255.255** trong mạng cục bộ. Router không tự chuyển broadcast này giữa các subnet; vì thế cần DHCP relay nếu máy chủ nằm ở VLAN hoặc mạng khác.

### Bốn thông điệp DORA

```mermaid
sequenceDiagram
    autonumber
    participant C as DHCP client
    participant S as DHCP server
    C->>S: DHCPDISCOVER: Tìm máy chủ (thường broadcast)
    S-->>C: DHCPOFFER: Đề xuất IP, lease và tùy chọn
    C->>S: DHCPREQUEST: Yêu cầu dùng đề xuất đã chọn
    S-->>C: DHCPACK: Xác nhận lease và cấu hình
    Note over C,S: Mô tả cùng mạng; nếu khác VLAN, DHCP relay chuyển tiếp
```

| Bước | Nội dung cốt lõi | Điều cần quan sát |
| --- | --- | --- |
| **DISCOVER** | Client tìm DHCP server; có thể gửi địa chỉ từng dùng và danh sách option mong muốn | Trong khởi tạo, thường từ 0.0.0.0:68 đến 255.255.255.255:67 |
| **OFFER** | Server đề xuất địa chỉ còn khả dụng, thời hạn lease và cấu hình | Có thể có nhiều OFFER từ các server khác nhau |
| **REQUEST** | Client chọn một đề xuất, nêu máy chủ được chọn; các server khác biết đề xuất của mình không được dùng | Khi lựa chọn ban đầu, REQUEST thường là broadcast |
| **ACK** | Server xác nhận lease; client có thể kiểm tra xung đột trước khi sử dụng địa chỉ | Phản hồi từ UDP 67 đến UDP 68, có thể broadcast hoặc unicast tùy trạng thái và khả năng client |

**OFFER chưa phải xác nhận cuối cùng.** Client cần được ACK trước khi coi lease đã cấp xong. Một số phản hồi khác cũng quan trọng:

- **DHCPNAK:** server từ chối yêu cầu sử dụng địa chỉ, chẳng hạn địa chỉ cũ không hợp lệ trên mạng hiện tại.
- **DHCPDECLINE:** client báo địa chỉ được đề xuất có dấu hiệu đã bị thiết bị khác dùng.
- **DHCPRELEASE:** client thông báo không còn cần lease; trên thực tế không phải mọi thiết bị ngắt mạng đều gửi RELEASE.
- **DHCPINFORM:** client đã có địa chỉ IPv4 bằng cách khác và chỉ yêu cầu các tùy chọn cấu hình bổ sung.

Các tên gọi Discover, Offer, Request, Ack là **loại thông điệp** trong DHCP; chúng không phải các lệnh TCP. Toàn bộ quá trình cấp phát DHCPv4 chạy trên UDP.

### Các trường đáng chú ý trong gói tin

| Trường / option | Ý nghĩa khi phân tích lưu lượng |
| --- | --- |
| Transaction ID (**xid**) | Giúp đối chiếu các thông điệp thuộc cùng giao dịch |
| **chaddr** và Client Identifier (Option 61) | Thông tin định danh của client; cách máy chủ sử dụng tùy chính sách |
| **yiaddr** | Địa chỉ IPv4 mà server đề xuất hoặc cấp cho client |
| **giaddr** | Địa chỉ relay agent; thường dùng để chọn subnet cấp phát |
| Option 53 | Loại thông điệp DHCP, ví dụ DISCOVER, OFFER, REQUEST, ACK |
| Option 50 | Địa chỉ IPv4 mà client yêu cầu |
| Option 54 | Server Identifier, chỉ rõ DHCP server |
| Option 51 | Lease Time |
| Option 1 / 3 / 6 | Lần lượt là subnet mask / router / DNS server |
| Option 55 | Danh sách thông số client yêu cầu |
| Option 82 | Thông tin relay agent, có thể phản ánh cổng hoặc điểm truy nhập nếu hạ tầng hỗ trợ |

Option 82 không tự động xuất hiện ở mọi mạng. Khi bật tính năng này, cần cấu hình nhất quán giữa relay, switch và DHCP server vì quy tắc tin cậy, chèn hoặc kiểm tra option khác nhau theo thiết bị.

## 3. Lease: nhận, gia hạn và hết hạn địa chỉ

Lease giúp địa chỉ được tái sử dụng khi thiết bị rời mạng. Ví dụ, cấp lease **8 giờ**; nhiều hệ thống mặc định hai mốc:

- **T1 ≈ 50% lease (4 giờ):** client vào trạng thái **RENEWING**, thường gửi DHCPREQUEST unicast đến server đã cấp lease.
- **T2 ≈ 87,5% lease (7 giờ):** nếu vẫn chưa gia hạn thành công, client vào trạng thái **REBINDING**, gửi yêu cầu broadcast để server thích hợp khác có thể trả lời.
- **Hết hạn lease (8 giờ):** nếu chưa được gia hạn hoặc cấp lease mới, client phải ngừng sử dụng địa chỉ đã hết hiệu lực.

```text
0 giờ                4 giờ             7 giờ             8 giờ
|---------------------|-----------------|-----------------|
BOUND                 T1                T2                Expire
Dùng IP hợp lệ        RENEWING          REBINDING         Không còn lease hợp lệ
                      Unicast REQUEST   Broadcast REQUEST
```

**T1/T2 có thể được cấu hình khác** và không phải lúc nào cũng đúng các tỉ lệ mặc định. Khi gia hạn được ACK, thời gian lease được cập nhật theo phản hồi. Khi chuyển sang VLAN hoặc subnet mới, địa chỉ cũ có thể không còn hợp lệ và client cần xin cấu hình phù hợp.

Lease ngắn giúp thu hồi địa chỉ nhanh, thích hợp mạng khách thay đổi liên tục, nhưng làm tăng lưu lượng gia hạn và tải lên dịch vụ DHCP. Lease dài giảm số lần gia hạn song có thể giữ địa chỉ lâu hơn khi client mất kết nối mà không gửi RELEASE. Cần chọn theo tần suất thay đổi thiết bị, số địa chỉ khả dụng và khả năng chịu lỗi của dịch vụ.

## 4. Thiết kế scope và dải cấp phát

**Scope** xác định phạm vi mạng và chính sách cấp phát; **pool** là các địa chỉ có thể cấp động nằm trong phạm vi đó. Ví dụ cho VLAN 40:

| Hạng mục | Thiết kế |
| --- | --- |
| Mạng | 192.168.40.0/24 |
| Network address | 192.168.40.0 |
| Broadcast address | 192.168.40.255 |
| Gateway | 192.168.40.1 |
| DNS nội bộ | 192.168.40.10 và 192.168.40.11 |
| Pool DHCP | 192.168.40.100–192.168.40.199 (**100 địa chỉ**) |
| Vùng giữ ngoài pool | 192.168.40.1–192.168.40.99 và 192.168.40.200–192.168.40.254 |
| Lease đề xuất ban đầu | 8 giờ, điều chỉnh theo số máy thực tế |

Địa chỉ **.0** và **.255** có vai trò đặc biệt trong mạng **/24** này, không được đưa vào pool máy trạm. Gateway, DNS và thiết bị cấu hình tĩnh cũng phải nằm ngoài pool động hoặc được quản lý bằng reservation nhất quán.

Một bản thiết kế chính sách có thể viết như sau. Đây là **mô tả trung lập với nhà cung cấp**, chưa phải file cấu hình có thể nạp trực tiếp vào DHCP server:

```yaml
scope: 192.168.40.0/24
vlan: 40
gateway: 192.168.40.1
dns_servers:
  - 192.168.40.10
  - 192.168.40.11
dynamic_pool:
  first: 192.168.40.100
  last: 192.168.40.199
lease_seconds: 28800
reservations:
  - device: printer-01
    address: 192.168.40.20
    identity: "client-id-hoac-mac-da-xac-minh"
```

Khi tính dung lượng, cần xét số **thiết bị đồng thời**, nhiều giao diện trên một thiết bị, địa chỉ còn giữ lease và phần dư cho tăng trưởng. Ví dụ pool có 100 địa chỉ nhưng thường có 95 thiết bị đồng thời thì dư địa rất ít. Ngoài việc mở rộng pool, có thể chọn prefix lớn hơn hoặc phân tách mạng đúng nhu cầu.

**Không mở hai DHCP server cùng cấp từ một pool chồng lấn** nếu chúng không có cơ chế điều phối lease. Nếu cần dự phòng, dùng tính năng HA/failover mà sản phẩm hỗ trợ hoặc chia pool có kiểm soát, kèm kiểm tra sự đồng bộ về gateway, DNS và reservation.

## 5. DHCP relay khi máy chủ nằm ở mạng khác

Giả sử doanh nghiệp có máy chủ DHCP tập trung tại **192.168.10.10**, còn máy khách thuộc VLAN 20, subnet **192.168.20.0/24**. Yêu cầu broadcast từ máy khách không tự qua router để đến máy chủ. Trên giao diện định tuyến VLAN 20 (SVI hoặc cổng router) cấu hình **DHCP relay** trỏ đến máy chủ tập trung.

```text
VLAN 20 / 192.168.20.0/24                         VLAN máy chủ / 192.168.10.0/24
[Client chưa có IP] --broadcast--> [Gateway + DHCP relay] --unicast--> [DHCP server]
                                   192.168.20.1                  192.168.10.10
                        relay ghi giaddr = 192.168.20.1
```

Luồng xử lý cơ bản:

1. Relay nhận DISCOVER từ client trên VLAN 20.
2. Relay chuyển thông điệp đến DHCP server và ghi thông tin nguồn mạng, thường qua **giaddr = 192.168.20.1**.
3. Server chọn scope **192.168.20.0/24**, tạo OFFER và trả về qua relay.
4. Relay chuyển OFFER về client trên VLAN 20; REQUEST và ACK đi theo cơ chế tương ứng.

Một DHCP server có thể phục vụ nhiều VLAN, miễn là từng VLAN có scope phù hợp và đường định tuyến/ACL cho phép lưu lượng relay cần thiết. Ví dụ:

| VLAN | Mục đích | Subnet | Pool gợi ý |
| --- | --- | --- | --- |
| 10 | Máy trạm nội bộ | 192.168.10.0/24 | 192.168.10.100–192.168.10.199 |
| 20 | Wi-Fi khách | 192.168.20.0/24 | 192.168.20.50–192.168.20.249 |
| 30 | Thiết bị IoT/camera | 192.168.30.0/24 | 192.168.30.100–192.168.30.149 |

**Tách VLAN không có nghĩa mọi thiết bị được phép truy cập lẫn nhau.** DHCP cấp thông tin IP; firewall/ACL vẫn phải giới hạn lưu lượng giữa mạng khách, máy trạm, IoT và hệ thống quản trị.

Khi một VLAN nhận IP của VLAN khác, hãy kiểm tra cấu hình relay/giaddr, ánh xạ scope, VLAN trên cổng switch và các chính sách DHCP server trước khi thay đổi dải địa chỉ.

## 6. DHCPv6 và quan hệ với SLAAC

IPv6 có hai cơ chế lớn để máy khách hình thành địa chỉ toàn cục: **SLAAC** (*Stateless Address Autoconfiguration*) và **DHCPv6**. Chúng có thể kết hợp. Khác với DHCPv4, IPv6 thường nhận **default router từ Router Advertisement (RA)** thuộc Neighbor Discovery, không phải từ DHCPv6.

| Mô hình | Nguồn địa chỉ | Nguồn thông số DNS | Default router |
| --- | --- | --- | --- |
| SLAAC | Client tự tạo từ prefix quảng bá qua RA có cờ A phù hợp | RA/RDNSS nếu hệ điều hành hỗ trợ, hoặc cấu hình khác | RA |
| SLAAC + DHCPv6 stateless | SLAAC | Có thể lấy thêm DNS/domain từ DHCPv6 | RA |
| DHCPv6 stateful | DHCPv6 cấp địa chỉ (IA_NA); có thể cùng tồn tại với SLAAC tùy RA/client | DHCPv6 hoặc RA theo triển khai | RA |

Hai cờ trong RA thường gặp:

- **M (Managed):** báo hiệu có thể dùng DHCPv6 quản lý địa chỉ.
- **O (Other configuration):** báo hiệu có thông tin cấu hình bổ sung từ DHCPv6.

Cờ **A** trong Prefix Information Option của RA cho biết prefix có thể được dùng với SLAAC. **M/O không thay thế chính sách client**: hệ điều hành và phiên bản triển khai quyết định có sử dụng DHCPv6 hay không. Không nên chỉ dựa vào M/O để kết luận một host đã được cấp địa chỉ hoặc DNS như dự tính.

DHCPv6 dùng **UDP 546 (client)** và **UDP 547 (server/relay)**. Máy khách thường liên hệ DHCPv6 server/relay bằng multicast **ff02::1:2** trong phạm vi liên kết. Quy trình phổ biến là **SOLICIT → ADVERTISE → REQUEST → REPLY**; tùy chọn *Rapid Commit* có thể rút gọn trao đổi.

DHCPv6 sử dụng **DUID** và **IAID** để nhận diện client/association, không đồng nhất với MAC như nhiều người mới học thường giả định. Ngoài IA_NA để cấp địa chỉ cho host, **DHCPv6 Prefix Delegation (IA_PD)** cho phép cấp một hoặc nhiều prefix cho router phía sau, ví dụ router chi nhánh triển khai các mạng LAN con. DHCPv6 có cơ chế relay riêng với các thông điệp **RELAY-FORW** và **RELAY-REPL**.

**Điểm cần nhớ khi vận hành dual-stack:** DHCPv4 hoạt động đúng không chứng minh IPv6 cũng đúng. Cần kiểm tra RA, chính sách SLAAC/DHCPv6, DNS IPv6, route IPv6 và các cơ chế bảo vệ RA/DHCPv6 riêng.

## 7. Rủi ro bảo mật và cách phòng vệ

DHCPv4 thông dụng không có xác thực đầu cuối được triển khai rộng rãi giữa mọi client và server. Vì vậy thiết bị cùng phân đoạn L2 có thể gửi hoặc phản hồi gói DHCP trái phép. Phòng vệ chủ yếu nằm ở hạ tầng switch, phân đoạn mạng, kiểm soát truy cập và giám sát.

| Nguy cơ | Cách xảy ra | Tác động | Giảm thiểu |
| --- | --- | --- | --- |
| **Rogue DHCP server** | Thiết bị lạ phản hồi DISCOVER với gateway/DNS do nó kiểm soát | Chuyển hướng lưu lượng, gián đoạn dịch vụ, hỗ trợ tấn công trung gian | **DHCP snooping**, chỉ tin cậy cổng đến server/relay hợp lệ, phát hiện OFFER bất thường |
| **DHCP starvation** | Kẻ tấn công phát nhiều yêu cầu với định danh giả để chiếm pool | Máy hợp lệ không còn địa chỉ | Giới hạn tốc độ DHCP trên cổng access, port security/NAC, cảnh báo pool cạn |
| **Xung đột địa chỉ** | IP tĩnh trùng pool hoặc thông tin lease không nhất quán | Rớt kết nối, ARP bất thường, DHCPDECLINE | Quản lý IPAM, vùng loại trừ, kiểm tra log/ARP và reservation |
| **Giả mạo IP/ARP sau khi có lease** | Host dùng địa chỉ hoặc ánh xạ ARP trái phép | Can thiệp lưu lượng cùng VLAN | Kết hợp DHCP snooping binding với **Dynamic ARP Inspection** và **IP Source Guard** nếu hỗ trợ |
| **DNS/router option độc hại** | Server giả mạo phát DNS/gateway sai | Phân giải sai, chuyển lưu lượng qua điểm tấn công | Chặn DHCP server trái phép, kiểm tra DHCP option, theo dõi gateway/DNS hiệu lực |
| **Rogue RA/DHCPv6** | Thiết bị lạ quảng bá router IPv6 hoặc trả lời DHCPv6 | Host có thể đi qua router/thiết lập không tin cậy | **RA Guard**, **DHCPv6 Guard** và giám sát IPv6 theo hỗ trợ thiết bị |

**DHCP snooping** thường phân loại cổng switch thành *trusted* và *untrusted*. Cổng kết nối đến DHCP server/relay được phép phát phản hồi server hợp lệ; cổng máy khách không được tự ý phát OFFER/ACK. Switch có thể lưu bảng binding liên kết địa chỉ IP, MAC, VLAN và cổng. Cấu hình sai cổng trusted hoặc không xử lý đúng lưu lượng đi qua relay có thể làm ngừng cấp phát, nên cần thử nghiệm theo sơ đồ mạng thực.

Dynamic ARP Inspection hoặc IP Source Guard phụ thuộc dữ liệu binding của DHCP snooping; máy dùng IP tĩnh có thể cần binding hoặc quy tắc phù hợp. Trên IPv6, bảo vệ RA và DHCPv6 phải được đánh giá riêng; DHCP snooping cho IPv4 không tự loại bỏ mọi rủi ro IPv6.

Việc bật ghi log nên trả lời được câu hỏi: **ai được cấp địa chỉ nào, khi nào, từ VLAN/cổng nào và bởi server nào?** Đồng bộ thời gian hệ thống, đặt chính sách lưu trữ hợp lý và hạn chế truy cập log vì chúng có thể chứa thông tin định danh thiết bị.

## 8. Chẩn đoán lỗi DHCP theo triệu chứng

Trước khi sửa, xác định **máy khách ở VLAN nào, kỳ vọng lấy scope nào và có DHCP relay không**. Sau đó kiểm tra từng chặng: client → switch/VLAN → relay → server → phản hồi trở về.

| Triệu chứng | Giả thuyết ưu tiên | Kiểm tra thực tế |
| --- | --- | --- |
| Máy Windows có **169.254.x.x/16** | Không nhận được cấu hình IPv4 DHCP hợp lệ; hệ thống tự chọn IPv4 link-local (APIPA) | DHCP client, VLAN, relay, ACL, server và pool |
| Không thấy **DHCPOFFER** sau DISCOVER | DISCOVER không đến server, server không có scope/địa chỉ hoặc phản hồi bị chặn | Capture tại client/relay/server; log server; bảng cấp phát |
| Có OFFER nhưng không có ACK | REQUEST không đến server, policy từ chối hoặc phản hồi bị chặn | Transaction ID, Server Identifier, DHCPNAK, firewall |
| Có ACK nhưng máy vẫn báo IP trùng | Xung đột IP tĩnh, bảng lease sai hoặc phát hiện trùng trên client | DHCPDECLINE, ARP, log IPAM/reservation |
| Có IP nhưng không ra mạng ngoài | Gateway, subnet, route, firewall, NAT hoặc đường truyền có vấn đề | Bảng route, thử kết nối gateway/IP đích, chính sách mạng |
| Ping IP được nhưng không phân giải tên | DNS option hoặc DNS resolver bị lỗi/chặn | DNS thực nhận, truy vấn DNS và ACL đến DNS |
| Chỉ một VLAN bị lỗi | Sai scope, relay, trunk/tag VLAN hoặc ACL liên VLAN | So sánh SVI/relay/giaddr và gói tin của VLAN hoạt động |
| IPv4 ổn nhưng IPv6 lỗi | RA, DHCPv6, prefix hoặc route IPv6 không đúng | RA flags/prefix, DHCPv6 SOLICIT/REPLY và route IPv6 |

**169.254.0.0/16** là dải IPv4 link-local, dùng để giao tiếp trong phạm vi liên kết khi không có địa chỉ phù hợp; nó không phải địa chỉ được router cấp cho Internet. IPv6 cũng có địa chỉ link-local **fe80::/10**, nhưng việc một host có địa chỉ này là bình thường và không tự chứng minh DHCPv6 thất bại.

### Lệnh kiểm tra trên máy khách

Trên Linux (điều chỉnh tên interface cho đúng):

```bash
ip -4 address show dev eth0
ip -4 route
nmcli device show eth0
resolvectl status
# Bắt gói DHCPv4 khi kiểm tra trên mạng được phép quản trị:
sudo tcpdump -ni eth0 -vvv 'udp port 67 or udp port 68'
# DHCPv6 dùng cặp cổng riêng:
sudo tcpdump -ni eth0 -vvv 'udp port 546 or udp port 547'
```

**nmcli** có trên hệ thống dùng NetworkManager; **resolvectl** có trên hệ thống dùng systemd-resolved. Nếu không cài các thành phần này, dùng lệnh tương ứng với trình quản lý mạng/DNS của máy. Công cụ bắt gói cần quyền phù hợp và nên được dùng trong phạm vi được phép quản trị.

Trên Windows:

```powershell
ipconfig /all
route print -4
Get-NetIPConfiguration
```

Trong môi trường thử nghiệm, có thể dùng **ipconfig /renew** để chủ động yêu cầu cấp lại DHCPv4. Thao tác này có thể làm gián đoạn kết nối đang mở; không nên chạy tùy tiện trên máy chủ sản xuất hoặc phiên làm việc từ xa.

Trong Wireshark, có thể lọc gói DHCPv4 theo giao thức BOOTP/DHCP (thường là bộ lọc hiển thị **bootp** tùy phiên bản), và gói DHCPv6 theo **dhcpv6**. Hãy đối chiếu **xid**, Client Identifier, Server Identifier, địa chỉ được đề nghị, **giaddr**, DHCP option và thời điểm từng gói.

Một quy trình đọc capture hiệu quả:

1. Có DISCOVER/SOLICIT hay chưa? Nếu chưa, kiểm tra trạng thái interface, client và tầng liên kết.
2. Có OFFER/ADVERTISE từ server mong đợi không? Nếu không, tìm điểm mất gói, cấu hình relay, scope và chính sách chống DHCP giả.
3. Client có gửi REQUEST không? Nếu có, yêu cầu chọn server và địa chỉ nào?
4. Có ACK/REPLY hay NAK không? Kiểm tra giá trị lease, gateway, DNS, prefix và lý do bị từ chối.
5. Nếu có nhiều phản hồi server, xác minh từng địa chỉ nguồn và đường đi: đây có thể là thiết kế dự phòng hợp lệ hoặc DHCP trái phép.

## 9. Ví dụ vận hành: mở mạng Wi-Fi khách an toàn

Một văn phòng mở VLAN 20 cho Wi-Fi khách, với subnet **192.168.20.0/24**, gateway **192.168.20.1** và pool **192.168.20.50–192.168.20.249**. DHCP server tập trung nằm trong VLAN 10.

**Thiết kế và triển khai:**

1. Tạo VLAN, subnet, SVI/default gateway và scope riêng cho khách; xác định DNS mà khách được phép dùng.
2. Cấu hình DHCP relay trên gateway VLAN 20 hướng đến server tập trung, cùng các route/ACL cần cho trao đổi DHCP.
3. Không cho khách truy cập mạng quản trị hoặc IoT; áp dụng firewall policy và NAT nếu kiến trúc truy cập Internet cần NAT.
4. Bật DHCP snooping trên switch được hỗ trợ; đánh dấu đúng cổng dẫn đến server/relay và giới hạn các cổng access.
5. Kết nối một client thử nghiệm, đọc lease, gateway, DNS và kiểm tra khả năng truy cập theo đúng chính sách.
6. Bắt gói DORA tại phía client hoặc relay để xác minh scope, server và thời gian cấp phát; kiểm tra log/bảng lease.
7. Theo dõi mức sử dụng pool, số lỗi cấp phát, yêu cầu bất thường và server DHCP ngoài danh sách cho phép.

**Tiêu chí đạt:** client VLAN 20 nhận IP trong pool .50–.249, subnet /24, gateway .1, DNS đúng chính sách, truy cập Internet theo ACL nhưng không vào hệ thống nội bộ bị cấm. Nếu client nhận địa chỉ thuộc VLAN 10, cần điều tra relay/scope/VLAN; nếu nhận DNS lạ, kiểm tra nguồn OFFER và cấu hình cấp phát.

Với IPv6, thực hiện kiểm tra bổ sung về RA hợp lệ, prefix, cơ chế SLAAC/DHCPv6, default router và RA Guard. Chỉ kiểm tra DHCPv4 là chưa đủ để khẳng định mạng khách an toàn theo cả hai giao thức.

## 10. Những nguyên tắc cần ghi nhớ

- **DHCP là cấp phát cấu hình, không phải định tuyến hay kiểm soát truy cập.** Phân đoạn, gateway, ACL, firewall và DNS phải được thiết kế đồng bộ.
- **DHCPv4 ban đầu thường dùng broadcast UDP 68→67.** DHCP relay giúp phục vụ client ở các subnet khác mà không phải đặt DHCP server trong mọi VLAN.
- **DORA kết thúc bằng DHCPACK.** Sau đó client quản lý vòng đời lease qua RENEWING, REBINDING và hết hạn.
- **Scope phải khớp subnet, pool không được đè lên IP tĩnh** và hệ thống nhiều server phải có phương án tránh cấp trùng.
- **DHCPv6 và SLAAC không tương đương DHCPv4.** IPv6 default router đến từ RA; DHCPv6 có thể cấp địa chỉ, thông số khác và prefix cho router.
- **Bảo mật DHCP bắt đầu từ ranh giới tin cậy L2.** Giám sát gói tin, giới hạn phản hồi từ server trái phép, quản lý binding và log là những kỹ năng vận hành thiết yếu.

Khi nắm được cách đọc gói DISCOVER/OFFER/REQUEST/ACK, phân biệt đúng phạm vi broadcast với relay và đối chiếu lease với cấu hình VLAN/gateway/DNS, bạn có thể khoanh vùng nhanh sự cố cấp phát địa chỉ và nhận diện nhiều dấu hiệu tấn công ngay tại lớp kết nối mạng.
