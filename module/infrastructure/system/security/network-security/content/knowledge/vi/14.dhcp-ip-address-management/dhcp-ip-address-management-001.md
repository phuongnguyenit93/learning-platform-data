# DHCP lease: Vòng đời cấp phát địa chỉ IP, gia hạn và kiểm soát an toàn

## 1. Khái niệm và mục tiêu

**DHCP (Dynamic Host Configuration Protocol)** là giao thức giúp thiết bị nhận cấu hình mạng từ dịch vụ quản lý tập trung. **DHCP lease** là quyền sử dụng một địa chỉ IP trong **thời hạn được máy chủ DHCP xác nhận**, thường kèm thông số subnet mask, default gateway, DNS và các tùy chọn mạng khác. Với DHCPv4, client không mặc nhiên sở hữu IP vĩnh viễn sau khi nhận một lời đề nghị cấp phát.

Chủ đề thuộc chương **DHCP và IP management** của học phần **SECURITY_NETWORK_SECURITY**. Quản trị lease giúp mạng phân đoạn, firewall, VPN, DNS, NAC/802.1X và giám sát IDS/IPS hoạt động tin cậy: thiết bị có IP đúng subnet, các bản ghi mạng có thể đối chiếu với lịch sử địa chỉ, và hạ tầng có khả năng phục hồi khi DHCP server hoặc relay gặp sự cố.

**Ví dụ:** một laptop gia nhập Wi-Fi công ty, được cấp địa chỉ trong VLAN nhân viên, subnet mask, gateway và DNS. Sau một thời gian, nó phải gia hạn hoặc nhận lại cấu hình; địa chỉ đó có thể được phân bổ cho thiết bị khác khi không còn lease hợp lệ.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Diễn giải **DORA** (Discover, Offer, Request, Acknowledge) của DHCPv4.
2. Phân biệt **lease duration**, **T1/renewal**, **T2/rebinding**, **expiry** và việc client khởi động lại.
3. Thiết kế **scope/pool, reservation, exclusion, relay** và liên hệ với IP Address Management (IPAM).
4. Phân biệt DHCPv4, DHCPv6 và IPv6 SLAAC.
5. Chẩn đoán lỗi cấp hoặc gia hạn IP mà không gây gián đoạn máy đang vận hành.
6. Phân tích rủi ro rogue DHCP, pool exhaustion, IP conflict và các biện pháp phòng vệ ở switch và máy chủ.

## 2. Các thành phần của một hệ thống DHCP

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| DHCP client | Thiết bị xin cấu hình mạng | Laptop, VM, máy trạm |
| DHCP server | Cấp, quản lý và gia hạn lease | Dịch vụ DHCP tập trung |
| Scope/subnet | Phạm vi cấu hình dành cho một mạng IP | 192.0.2.0/24 |
| Dynamic pool | Tập địa chỉ được cấp động | 192.0.2.100–192.0.2.199 |
| Exclusion | Địa chỉ không được cấp qua pool động | Gateway hoặc địa chỉ dùng tĩnh |
| Reservation | Quy tắc gắn một địa chỉ với định danh client | Máy in có địa chỉ dự kiến cố định |
| Lease duration | Thời hạn sử dụng IP sau khi được xác nhận | 8 giờ |
| DHCP relay | Chuyển thông điệp DHCP giữa các subnet | IP helper trên gateway |
| IPAM | Quản lý subnet, pool, allocation và lịch sử IP | Hệ thống quản lý tài nguyên địa chỉ |

Các địa chỉ **192.0.2.0/24**, **198.51.100.0/24** và **203.0.113.0/24** dùng trong bài đều thuộc dải IPv4 dành cho tài liệu theo RFC 5737. Chúng **không phải địa chỉ triển khai thực tế**; trong lab phải thay bằng địa chỉ được phân bổ hợp lệ.

### 2.1. Dynamic lease, reservation và static address

- **Dynamic lease:** server cấp từ tập địa chỉ còn khả dụng, với thời hạn giới hạn; client có thể nhận IP khác ở lần cấp kế tiếp.
- **DHCP reservation:** server dự định cấp cùng một IP cho client có định danh phù hợp; client vẫn có thể nhận **DHCP lease** và gia hạn bình thường.
- **Static configuration:** IP được cấu hình ngay trên thiết bị, không phải một lease DHCP.
- **Exclusion:** ngăn một địa chỉ bị phân phối qua pool động; quy tắc kết hợp exclusion và reservation phụ thuộc phần mềm server.

Đừng đồng nhất định danh DHCP với MAC vật lý: DHCPv4 có **Client Identifier (Option 61)**; máy ảo, hệ điều hành và thiết bị Wi-Fi có thể thay định danh/MAC theo chính sách riêng. Một thiết bị có thể xuất hiện với nhiều client identifier và một IP từng được dùng bởi nhiều thiết bị ở các thời điểm khác nhau.

### 2.2. Lease không phải chứng nhận quyền truy cập

Được DHCP cấp IP **không chứng minh** người dùng đã được xác thực hoặc thiết bị đã an toàn. Network Access Control, VLAN/VRF, host firewall, firewall nội bộ, VPN, xác thực ứng dụng và kiểm soát danh tính là các lớp riêng. DHCP chủ yếu cung cấp **cấu hình địa chỉ và thông số mạng**.

## 3. DHCPv4: Quy trình DORA

DHCPv4 thường sử dụng **UDP 68 phía client**, **UDP 67 phía server**. Khi chưa có cấu hình IPv4, client có thể phát broadcast trong subnet; nếu server nằm ở subnet khác, **DHCP relay** giúp chuyển thông điệp qua router.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Relay nếu có
    participant S as DHCP server
    C->>R: DHCPDISCOVER
    R->>S: Chuyển Discover
    S-->>R: DHCPOFFER
    R-->>C: Chuyển Offer
    C->>R: DHCPREQUEST
    R->>S: Chuyển Request
    S-->>R: DHCPACK
    R-->>C: Chuyển ACK
    Note over C: Xác minh và dùng IPv4 đã được cấp
~~~

Relay được đưa vào sơ đồ để mô tả mạng nhiều subnet. Khi client và server nằm cùng mạng phù hợp, không nhất thiết có relay.

### 3.1. DHCPDISCOVER: Tìm server

Client chưa có địa chỉ IPv4 hợp lệ thường gửi DHCPDISCOVER từ **0.0.0.0:68** đến **255.255.255.255:67**. Gói có thể chứa định danh client và danh sách tùy chọn cần. Broadcast này không tự vượt qua mọi router; relay phải được cấu hình đúng để chuyển tới server tập trung.

### 3.2. DHCPOFFER: Đề nghị cấu hình

Server đề nghị một IP kèm các thông số như subnet mask, router, DNS và thời hạn lease theo chính sách. Client có thể thấy nhiều offer và chọn một offer thích hợp.

**OFFER chưa phải chứng cứ client đã dùng IP thành công.** Trạng thái cấp phát chỉ hoàn tất sau khi server xác nhận và client chấp nhận cấu hình hợp lệ.

### 3.3. DHCPREQUEST: Chọn hoặc xin gia hạn

Client chọn đề nghị và yêu cầu địa chỉ bằng DHCPREQUEST. Ở giai đoạn chọn offer ban đầu, client thường broadcast REQUEST để các server khác biết lựa chọn. **Requested IP Address (Option 50)** và **DHCP Server Identifier (Option 54)** có ý nghĩa theo đúng trạng thái giao thức.

**Cùng loại bản tin DHCPREQUEST còn dùng ở INIT-REBOOT, RENEWING và REBINDING**, nhưng không có cùng yêu cầu về địa chỉ đích và option trong mọi trạng thái. Không giả định mọi REQUEST đều là bắt đầu một DORA mới.

### 3.4. DHCPACK: Xác nhận lease

Server xác nhận địa chỉ và các tùy chọn được cấp bằng DHCPACK. Client thực hiện kiểm tra phù hợp, ví dụ phát hiện xung đột IPv4 theo khả năng hệ điều hành, rồi sử dụng địa chỉ trong thời hạn có hiệu lực.

Server có thể trả **DHCPNAK** nếu địa chỉ client yêu cầu không hợp lệ trong bối cảnh cụ thể. Client phải quay về quá trình lấy cấu hình hợp lệ theo trạng thái DHCP.

### 3.5. Các bản tin bổ trợ

| Bản tin | Mục đích |
| --- | --- |
| DHCPDISCOVER | Tìm dịch vụ DHCP |
| DHCPOFFER | Đề nghị địa chỉ và tùy chọn |
| DHCPREQUEST | Chọn/gia hạn/xác nhận địa chỉ theo trạng thái |
| DHCPACK | Xác nhận các thông số lease |
| DHCPNAK | Thông báo yêu cầu địa chỉ không hợp lệ trong bối cảnh thích hợp |
| DHCPDECLINE | Client báo địa chỉ được cấp/đề nghị có dấu hiệu bị trùng |
| DHCPRELEASE | Client chủ động trả địa chỉ khi không còn sử dụng |
| DHCPINFORM | Client có IP theo cách khác yêu cầu một số thông số cấu hình |

Không phải mọi client luôn gửi RELEASE khi mất nguồn, chuyển Wi-Fi hoặc tắt máy. Server phải quản lý expiry và tái sử dụng địa chỉ mà không dựa hoàn toàn vào RELEASE.

## 4. Vòng đời lease: T1, T2 và expiry

Sau khi nhận DHCPACK, client vào trạng thái **BOUND**. Client được phép sử dụng IP trong lease còn hiệu lực và thường cố gia hạn **trước** khi hết hạn.

~~~mermaid
flowchart LR
    Init[INIT hoặc INIT-REBOOT] --> Select[SELECTING / REQUESTING]
    Select --> Bound[BOUND]
    Bound -->|T1| Renew[RENEWING]
    Renew -->|ACK| Bound
    Renew -->|T2 chưa có ACK| Rebind[REBINDING]
    Rebind -->|ACK| Bound
    Rebind -->|Expiry chưa gia hạn| Expired[Ngừng dùng IP hết hạn]
    Expired --> Init
~~~

Sơ đồ giản lược, chưa thể hiện mọi nhánh DHCPNAK, kiểm tra xung đột hoặc hỏng mạng. Mỗi DHCPACK gia hạn thành công có thể đưa ra thời hạn và tham số mới.

### 4.1. Ý nghĩa ba mốc thời gian

- **Lease duration:** thời gian hiệu lực của quyền dùng địa chỉ bắt đầu từ lần cấp/gia hạn thành công tương ứng.
- **T1 — renewal:** client thử gia hạn với **server ban đầu**, trong DHCPv4 thường dùng DHCPREQUEST **unicast** khi có thể liên lạc.
- **T2 — rebinding:** nếu gia hạn chưa thành công, client thử với **bất kỳ server phù hợp**; DHCPv4 thường broadcast DHCPREQUEST.
- **Expiry:** nếu lease hết hạn mà không có xác nhận hợp lệ mới, client **phải ngừng dùng IP cũ** và chuyển sang quá trình lấy địa chỉ phù hợp.

Các DHCPv4 option liên quan là **51 (lease time)**, **58 (renewal time/T1)** và **59 (rebinding time/T2)**. Khi T1/T2 không được server cung cấp và không có điều kiện đặc biệt, giá trị mặc định thông dụng theo RFC 2131 là **T1 = 50%** và **T2 = 87,5%** thời lượng lease. Không xem đây là giá trị cứng của mọi DHCP client, mọi policy hoặc của DHCPv6.

### 4.2. Ví dụ lease 8 giờ bắt đầu lúc 08:00

| Mốc | Phép tính | Giờ tương ứng |
| --- | --- | --- |
| DHCPACK / BOUND | Bắt đầu lease | **08:00** |
| **T1** | 8 h × 0,5 = 4 h | **12:00** |
| **T2** | 8 h × 0,875 = 7 h | **15:00** |
| **Expiry** | 08:00 + 8 h | **16:00** |

Nếu client nhận DHCPACK gia hạn lúc **12:01**, các mốc sẽ được thiết lập lại theo lease vừa được cấp. Client **không phải** dừng dùng IP lúc 16:00 của lease cũ nếu đã gia hạn thành công và lease mới còn hiệu lực.

### 4.3. Nếu DHCP server mất kết nối

Giả sử máy đang có lease hợp lệ đến 16:00, nhưng server tạm không liên lạc được:

1. Trước thời điểm hết hạn, máy thường vẫn sử dụng địa chỉ đang có; mất liên lạc với DHCP server **không tự động làm hết lease ngay**.
2. Tới T1, client thử gia hạn với server cấp địa chỉ trước đó.
3. Tới T2, client thử rebind theo cơ chế DHCPv4 để tìm server phù hợp.
4. Nếu đến expiry vẫn không gia hạn, máy không được tiếp tục dùng địa chỉ đã hết hạn.

Máy **mới gia nhập mạng** trong thời gian DHCP không sẵn sàng có thể không nhận được địa chỉ từ đầu, trong khi máy đã có lease hợp lệ vẫn hoạt động tạm thời. Thời lượng lease ảnh hưởng tới khả năng chịu gián đoạn này.

### 4.4. INIT-REBOOT

Client khởi động lại và còn nhớ địa chỉ từng sử dụng có thể thử **INIT-REBOOT** để yêu cầu xác nhận địa chỉ vẫn hợp lệ trên mạng hiện tại. Không được suy ra rằng IP cũ vẫn dùng được khi máy đổi subnet/VLAN/VPN, hoặc khi lease/định danh client đã thay đổi.

## 5. DHCPv4 options và cách đọc một lease

| Trường/option | Ý nghĩa | Gợi ý kiểm tra khi gặp sự cố |
| --- | --- | --- |
| yiaddr | Địa chỉ IPv4 server đề nghị/cấp trong bản tin thích hợp | Đúng subnet và pool không? |
| chaddr / Option 61 | Địa chỉ phần cứng/định danh client | Có bị đổi định danh hoặc trùng không? |
| Option 1 | Subnet Mask | Mask có đúng mạng client không? |
| Option 3 | Router / Default Gateway | Gateway có đúng VLAN và truy cập được không? |
| Option 6 | DNS servers | Có cấp resolver đúng và đáng tin không? |
| Option 15 | Domain name | Có cấp đúng hậu tố domain theo thiết kế không? |
| Option 50 | Requested IP Address | Client xin địa chỉ nào ở trạng thái đang xét? |
| Option 51 | IP Address Lease Time | Lease dài bao lâu (giây)? |
| Option 54 | DHCP Server Identifier | Server nào được chọn theo trạng thái DHCP? |
| Option 58 | Renewal Time Value | Client bắt đầu gia hạn lúc nào? |
| Option 59 | Rebinding Time Value | Client bắt đầu rebind lúc nào? |
| Option 82 | Relay Agent Information | Relay có gửi thông tin vị trí/circuit theo chính sách không? |

**Option 82** thường do relay hoặc thiết bị mạng hỗ trợ bổ sung, không phải chữ ký mật mã chứng thực client. Nếu tin vào thông tin relay từ một cổng không được kiểm soát, server có thể ra quyết định cấp phát theo dữ liệu không đáng tin.

### 5.1. Cấu hình IP đúng chưa chắc mạng hoạt động

Ngay cả khi client nhận DHCPACK thành công:

- DNS được cấp có thể lỗi, sai phân vùng tên miền hoặc không nằm trong vùng được phép truy cập.
- Gateway bị sai, route đi/đường về không đúng hoặc firewall chặn lưu lượng.
- Máy có thể dùng một địa chỉ trùng với thiết bị cấu hình tĩnh.
- NAC/802.1X có thể chỉ cho phép traffic đến một số dịch vụ cho đến khi xác thực.
- VPN, proxy hoặc chính sách phân đoạn có thể thay đổi đường đi sau khi interface đã có IP.

**DHCP cấp thông số cấu hình**, không bảo đảm thành công của ứng dụng hay quyền truy cập tài nguyên.

## 6. DHCP relay: Khi server nằm ở subnet khác

DHCPDISCOVER ban đầu thường là broadcast trên mạng client; router không tự chuyển tiếp mọi broadcast IPv4. **DHCP relay agent** nhận thông điệp DHCP ở mạng client và chuyển đến DHCP server ở mạng khác theo cấu hình.

~~~mermaid
flowchart LR
    C[Client VLAN 20] -->|DHCP broadcast| R[Gateway / DHCP relay]
    R -->|Forward to server| S[DHCP server]
    S -->|Offer / ACK| R
    R -->|Forward to client| C
~~~

DHCPv4 relay thường dùng **giaddr** để cho server biết mạng phía client/relay, phục vụ lựa chọn subnet cấp phát. Một số kiến trúc dùng Option 82 bổ sung thông tin cổng/circuit; tính năng này phải được thiết kế nhất quán giữa relay, switch và server.

### 6.1. Ví dụ sơ đồ cấp địa chỉ tập trung

| Thành phần | Địa chỉ hoặc dữ liệu minh họa |
| --- | --- |
| VLAN nhân viên | **192.0.2.0/24** |
| Gateway/relay VLAN nhân viên | **192.0.2.1** |
| Server DHCP tập trung ở VLAN khác | **198.51.100.10** |
| Dynamic pool của nhân viên | **192.0.2.100–192.0.2.199** |
| DNS resolver | **192.0.2.53** |
| Lease duration | **8 giờ** |

Nếu relay không cấu hình chuyển tiếp đến server, mạng có firewall chặn luồng giữa relay và server, hoặc server không có scope tương ứng, client sẽ không nhận đúng lease. Nếu relay gắn địa chỉ mạng nguồn sai, server có thể chọn nhầm scope.

### 6.2. DHCP và chính sách firewall

Luồng DHCPv4 có cổng client **UDP 68** và server **UDP 67**; lưu lượng relay-server có hình thức cổng và địa chỉ cụ thể theo giao thức/triển khai. Cần áp dụng policy **đúng hướng và đúng cặp relay/server**, không mở UDP 67/68 vô điều kiện giữa mọi VLAN.

Một rule cho nhân viên truy cập HTTPS đến ứng dụng **không thay thế** rule DHCP/relay cần cho việc cấp phát. Ngược lại, server DHCP phải thuộc nhóm dịch vụ hạ tầng được phép, không phải máy nào cũng được phản hồi DHCP cho mọi client.

## 7. Chọn lease duration theo điều kiện vận hành

Thời lượng lease là sự đánh đổi giữa khả năng tái sử dụng IP, khối lượng giao dịch DHCP và tính sẵn sàng khi mất server.

| Mạng | Đặc trưng | Cân nhắc chọn thời hạn |
| --- | --- | --- |
| Wi-Fi khách/sự kiện | Thiết bị đến và đi liên tục, pool dễ bị chiếm trong thời gian dài | Có thể ngắn hơn để tái sử dụng địa chỉ, phải thử thiết bị thực |
| Máy trạm văn phòng | Client tương đối ổn định và hay tái kết nối | Giá trị vừa/dài tùy số lượng và tính sẵn sàng server |
| Thiết bị cố định | Cần địa chỉ dự đoán được | Reservation được quản lý hoặc static IP đúng quy trình |
| VM/thiết bị ngắn hạn | Khởi tạo/hủy liên tục, IPAM động | Tích hợp lease lifecycle với hệ thống quản lý |
| Mạng qua WAN không ổn định | Có thể mất liên lạc tới DHCP server theo từng đợt | Tránh lease quá ngắn làm nhiều máy đồng loạt hết hạn |

### 7.1. Khi lease quá ngắn

- Client phải renew thường xuyên hơn, làm tăng lưu lượng DHCP và số sự kiện cần giám sát.
- Mất kết nối tới server/relay lâu có thể khiến nhiều thiết bị đến expiry.
- Thiết bị IoT hoặc firmware cũ có thể có hành vi renewal chưa ổn định, cần kiểm thử.
- Khi giảm lease time ở server, những client đã có lease **không tự thay thời hạn ngay** nếu chưa nhận thông số mới.

### 7.2. Khi lease quá dài

- Thiết bị đã rời mạng có thể còn chiếm lease đến khi hết hạn hoặc được release theo khả năng client.
- Pool có số lượng IP hạn chế có thể cạn trong mạng có nhiều khách luân chuyển.
- Thay đổi gateway/DNS thông qua DHCP có thể đến chậm với những client chưa renew.
- Lease log có thể chứa client đã rời mạng nhưng lease vẫn còn hiệu lực.

Không có một thời lượng lease duy nhất đúng cho mọi subnet. Cần dùng **pool size, lượng thiết bị đồng thời, client churn, thời gian phục hồi server, độ ổn định mạng và yêu cầu thay đổi options** để lựa chọn.

## 8. Quản trị DHCP lease với IPAM

**IP Address Management (IPAM)** quản lý phạm vi địa chỉ và trạng thái phân bổ của tổ chức: subnet, pool, địa chỉ tĩnh, reservation, thiết bị, lịch sử thuê và quan hệ với DNS. DHCP lease là **một nguồn dữ liệu** quan trọng của IPAM, không phải bảng định danh người dùng hay nguồn sự thật duy nhất về máy đang online.

### 8.1. Ví dụ dải địa chỉ và phép tính

~~~text
Subnet:           192.0.2.0/24
Gateway:          192.0.2.1
DNS resolver:     192.0.2.53
Dynamic pool:     192.0.2.100 - 192.0.2.199
Pool capacity:    199 - 100 + 1 = 100 IPv4
Lease duration:   8 giờ = 28.800 giây
T1 mặc định:      14.400 giây
T2 mặc định:      25.200 giây
~~~

Không đồng nhất **256 giá trị của một subnet /24** với số địa chỉ có thể cấp động. Pool có thể chỉ chiếm một phần của subnet và phải xét các địa chỉ không hợp lệ, địa chỉ infrastructure, reservation, exclusion, conflict và chính sách triển khai.

### 8.2. Trạng thái địa chỉ cần giám sát

| Trạng thái | Ý nghĩa vận hành | Điểm cần lưu ý |
| --- | --- | --- |
| Available / free | Có thể cấp theo policy | Phụ thuộc trạng thái thực của server |
| Offered / pending | Có đề nghị hoặc tiến trình cấp phát chưa kết thúc | Chưa chứng minh client đã nhận IP |
| Active / leased | Lease được server ghi nhận còn hiệu lực | Không chứng minh client còn online |
| Reserved | Dành cho định danh client được cấu hình | Không nhất thiết là active lease |
| Declined / conflict | IP bị nghi có xung đột | Cần điều tra trước khi cho cấp lại |
| Expired / reclaimed | Lease hết hạn và có thể được thu hồi | Thời điểm thu hồi phụ thuộc sản phẩm |

Ví dụ **100 địa chỉ** trong pool, **78 lease active**, tỷ lệ active lease trên dung lượng pool là **78%**. Đây chưa chắc là tỷ lệ địa chỉ còn dùng được: một số IP có thể bị reserved, conflict hoặc chưa được reclaim. Báo cáo cần phân biệt **active utilization** với **free allocatable addresses**.

### 8.3. Những metric nên theo dõi

1. Dung lượng pool thực sự cấp phát được và mức cao nhất theo giờ/ngày.
2. Số lease active, offered, expired, declined/conflict và reserved.
3. Tần suất DHCPDISCOVER/DHCPREQUEST, tỷ lệ DHCPACK/DHCPNAK và lỗi không đủ IP.
4. Renewal/rebinding failures, scope latency và lượng client sắp hết hạn.
5. Trạng thái relay, server, HA/failover, replication và các dấu hiệu cấp trùng.
6. Đồng bộ thông tin DHCP, IPAM, NAC, switch/Wi-Fi controller và DNS.

### 8.4. Lease và Dynamic DNS

Một số môi trường tích hợp DHCP với **Dynamic DNS (DDNS)** để cập nhật hostname/IP và bản ghi **A/PTR** khi phù hợp. Nếu địa chỉ được tái sử dụng mà bản ghi cũ chưa được cập nhật, DNS hoặc log ứng dụng có thể gắn hostname với IP đã đổi chủ.

Việc tạo và xóa DNS record phụ thuộc **chính sách, quyền cập nhật, TTL, cache và phần mềm DHCP/DNS**. Không suy ra mọi bản ghi DNS sẽ ngay lập tức thay đổi mỗi khi một lease được cấp lại.

## 9. DHCPv6 và SLAAC: Không áp dụng nguyên xi quy tắc DHCPv4

**DHCPv6** có chức năng cấp địa chỉ/cấu hình trong những mô hình stateful và dùng các thông điệp **SOLICIT, ADVERTISE, REQUEST, REPLY** ở quy trình điển hình (với những biến thể được giao thức cho phép). Nhưng IPv6 còn có **Stateless Address Autoconfiguration (SLAAC)**, trong đó thiết bị tự tạo địa chỉ dựa trên **Router Advertisement (RA)** thay vì nhất thiết nhận một lease cấp địa chỉ từ DHCPv6.

| Thuộc tính | DHCPv4 | DHCPv6 / IPv6 |
| --- | --- | --- |
| UDP client/server | **68 / 67** | **546 / 547** |
| Cấp địa chỉ | DHCPDISCOVER → OFFER → REQUEST → ACK | DHCPv6 SOLICIT → ADVERTISE → REQUEST → REPLY khi stateful |
| Nhận dạng | chaddr/MAC và Client Identifier tùy client | **DUID, IAID**, Identity Association |
| Tài nguyên được cấp | IPv4 address lease | Có thể là **IA_NA/IAADDR** hoặc delegated prefix **IA_PD** |
| Gia hạn | RENEWING, REBINDING với T1/T2 DHCPv4 | RENEW/REBIND theo T1/T2 của IA; semantics theo **RFC 8415** |
| Default gateway | Router Option 3 | **Router Advertisement** cung cấp default router theo mô hình thông thường |
| Địa chỉ tự cấu hình | Không phải cơ chế SLAAC | **SLAAC** có thể dùng mà không có DHCPv6 lease cấp địa chỉ |
| Thời hạn | Lease duration theo IPv4 | Preferred/valid lifetimes của IAADDR hoặc prefix cần được tôn trọng |

### 9.1. Stateful DHCPv6

Khi cấp IPv6 qua DHCPv6 stateful, client sử dụng danh tính như **DUID** và **IAID**, các cấu trúc **Identity Association** và lifetime phù hợp. Cần phân biệt thời điểm **T1/T2** để gia hạn IA với **preferred lifetime / valid lifetime** của địa chỉ được cấp.

**Không lấy tỷ lệ 50% và 87,5% của DHCPv4 rồi áp đặt như quy tắc cứng cho mọi DHCPv6 lease.** Cách xử lý giá trị lifetime, T1/T2 và thông điệp theo RFC 8415 cùng cấu hình thực tế.

### 9.2. SLAAC và Stateless DHCPv6

SLAAC cấu hình địa chỉ IPv6 từ thông tin RA và cơ chế địa chỉ của client. Thiết bị có thể nhận DNS/cấu hình khác bằng cơ chế phù hợp mà **không có DHCPv6 lease cấp địa chỉ**. Các cờ M/O trong RA liên quan tới việc gợi ý sử dụng DHCPv6, nhưng hành vi từng client và kiến trúc mạng cần được xác minh.

Với IPv6, đừng chờ DHCPv6 cung cấp default router như DHCPv4 Option 3; đó là vai trò quan trọng của **Router Advertisement**.

### 9.3. DHCPv6 Prefix Delegation

Một router/client có thể được ủy quyền **prefix IPv6** qua **IA_PD** để sử dụng ở mạng phía sau. Prefix được ủy quyền có vòng đời và ảnh hưởng rộng hơn việc cấp một IP cho laptop: khi đổi prefix, các subnet/thiết bị phía sau và route/firewall liên quan có thể cần cập nhật.

### 9.4. Dual-stack và bảo mật

Chỉ cấu hình DHCP snooping ở IPv4 **không tự bảo vệ** các luồng DHCPv6 và RA. Cần kiểm tra DHCPv6 Guard/RA Guard, nguồn DNS IPv6, policy firewall IPv6 và khả năng giám sát của hạ tầng. Rogue RA có thể ảnh hưởng default route IPv6 ngay cả khi DHCPv4 hoạt động bình thường.

## 10. Những rủi ro bảo mật liên quan DHCP lease

### 10.1. Rogue DHCP server

**Rogue DHCP server** là máy cấp cấu hình DHCP trái phép trong phạm vi mạng. Nó có thể cấp default gateway hoặc DNS sai, khiến thiết bị mất khả năng truy cập dịch vụ hoặc đưa một phần lưu lượng qua đường không tin cậy. Một server DHCP được cấu hình nhầm cũng có thể gây hậu quả tương tự mà không có ý đồ tấn công.

**Biện pháp:** xác định danh sách DHCP server/relay tin cậy; kiểm soát uplink và switch access port; dùng DHCP snooping khi nền tảng hỗ trợ; theo dõi OFFER/ACK và Server Identifier ngoài dự kiến. Không chỉ kiểm tra DHCP từ một máy: server lạ có thể chỉ xuất hiện ở một VLAN/địa điểm.

### 10.2. DHCP starvation và cạn pool

**DHCP starvation** là tình huống cố ý làm cạn nguồn cấp địa chỉ bằng cách tạo lượng yêu cầu cấp phát hoặc các định danh client giả vượt dự kiến. Pool exhaustion cũng có thể phát sinh **hoàn toàn hợp lệ** do quá nhiều thiết bị, thời lượng lease dài, cấu hình scope thiếu địa chỉ hoặc VM được tạo hàng loạt.

**Biện pháp:** monitor free allocatable addresses, tăng nhanh của lease mới, số client ID khác thường, giới hạn DHCP traffic trên access port nếu thiết bị hỗ trợ và kiểm soát quyền cắm thiết bị. Không quy mọi spike DHCP thành tấn công nếu chưa đối chiếu lịch sự kiện, Wi-Fi khách hoặc triển khai hệ thống.

### 10.3. IP conflict và client identifier

Trùng địa chỉ có thể do một máy dùng **static IP nằm trong pool động**, do nhiều server không phối hợp, do sai trạng thái failover hoặc do cấp phát bị lỗi. Client có thể phát hiện xung đột qua các cơ chế IPv4 Address Conflict Detection rồi thông báo **DHCPDECLINE** khi phù hợp.

**Biện pháp:** quản lý exclusion/reservation bằng IPAM, điều tra địa chỉ ở trạng thái conflict/declined, đối chiếu bảng MAC của switch và lịch sử lease. Tránh xóa hàng loạt lease trên production nhằm “giải phóng IP” khi chưa xác định ảnh hưởng.

### 10.4. DHCP snooping, DAI, IP Source Guard và NAC

| Cơ chế | Cách hỗ trợ | Giới hạn hoặc lưu ý |
| --- | --- | --- |
| **DHCP snooping** | Phân biệt port trusted/untrusted và ngăn phản hồi DHCP server từ nguồn trái phép; có thể tạo binding | Cấu hình sai uplink/relay trusted có thể chặn DHCP hợp lệ |
| **Dynamic ARP Inspection (DAI)** | Đối chiếu ARP với binding hoặc thông tin nguồn được tin cậy | Thiết bị cấu hình IP tĩnh có thể cần xử lý riêng |
| **IP Source Guard** | Hạn chế sử dụng IP/MAC ở access port theo binding/policy | Phụ thuộc khả năng switch và vòng đời lease |
| **802.1X / NAC** | Xác thực và/hoặc gán quyền/vùng cho thiết bị/người dùng | Cần thiết kế thứ tự cấp quyền port, VLAN và việc client lấy DHCP |
| **RA Guard/DHCPv6 Guard** | Hạn chế nguồn IPv6 RA/DHCPv6 không được phê duyệt | Cần kiểm thử tương thích mạng và thiết bị IPv6 |

Các tính năng này không đồng nghĩa một bộ bảo vệ hoàn chỉnh cho mọi giao thức. Ví dụ, **DHCP snooping chỉ hỗ trợ kiểm soát DHCP trên hạ tầng có khả năng thực thi**; không thay thế WAF, IDS/IPS, host firewall hay xác thực ứng dụng.

### 10.5. Lease history trong điều tra an ninh

Với một sự kiện IDS/IPS lúc **T**, phân tích IP nguồn phải tra lease history **tại chính thời điểm T**, kèm subnet, VLAN, client identifier/MAC và vị trí mạng nếu có. IP có thể được cấp lại sau khi lease hết hạn; một client cũng có thể thay MAC khi đổi mạng.

Để tăng độ tin cậy, kết hợp:

- DHCP server/relay logs có mốc thời gian và server identity.
- Switch MAC/cổng, Wi-Fi controller hoặc NAC/802.1X records.
- VPN/identity logs và asset inventory.
- DNS history, host telemetry, firewall logs và thông tin đổi VLAN.

**Không dùng IP hiện tại để tự động quy trách nhiệm cho một người dùng trong sự kiện quá khứ.** Đồng bộ thời gian, bảo vệ quyền truy cập log và chính sách lưu trữ dữ liệu là thành phần cần thiết của quy trình điều tra.

## 11. Quan sát DHCP lease trên hệ điều hành và hạ tầng

Các bước dưới đây ưu tiên **chỉ đọc**. Chúng dành cho máy của bạn hoặc môi trường lab/production bạn được phép quản trị, không yêu cầu phát lưu lượng gây cạn pool hay dựng DHCP server giả để thử.

### 11.1. Windows client

~~~powershell
# Xem DHCP Enabled, IPv4, mask, gateway, DNS, DHCP server
# và Lease Obtained / Lease Expires (khi có).
ipconfig /all

# Thông tin IP và interface từ PowerShell.
Get-NetIPConfiguration
Get-NetIPInterface
~~~

Nếu card mạng dùng static IP, bị disable hoặc không có DHCPv4 lease, bạn sẽ không thấy đầy đủ trường tương tự card có DHCP. Khi xử lý sự cố, kiểm tra **đúng interface**: Wi-Fi, Ethernet, VPN và adapter ảo có thể có cấu hình khác nhau.

Lệnh như **ipconfig /release** và **ipconfig /renew** làm thay đổi trạng thái IP và có thể cắt phiên làm việc từ xa. Không sử dụng như thao tác chẩn đoán đầu tiên trên máy production thiếu phương án khôi phục.

### 11.2. Linux client

~~~bash
# Xem địa chỉ IPv4 và tuyến đang có.
ip -4 addr show
ip -4 route

# Với hệ thống dùng NetworkManager:
nmcli -f GENERAL,IP4,DHCP4 device show

# Với hệ thống dùng systemd-resolved:
resolvectl status
~~~

Không phải Linux nào cũng có NetworkManager, systemd-resolved hoặc một vị trí lease file chung. Một số máy dùng systemd-networkd, cloud-init, DHCP client khác hoặc network namespace của container; hãy xác định **cơ chế quản trị mạng thực tế** trước khi diễn giải kết quả.

### 11.3. Capture DHCPv4 tại interface lab được phép

~~~bash
# Chỉ trên interface thuộc lab và có quyền thu thập lưu lượng.
# Thay <lab-iface> bằng interface thực.
sudo tcpdump -i <lab-iface> -nn -vv 'udp port 67 or udp port 68'
~~~

Trong traffic, xem **message type, Server Identifier, Client Identifier, requested IP, lease time, T1/T2, giaddr và các option mạng**. Capture một interface không nhìn thấy gói **không chứng minh không có DHCP trong subnet khác**; phải xác định điểm quan sát, đường broadcast/relay và quyền mirror/SPAN nếu cần.

### 11.4. DHCP server/IPAM

Trên giao diện quản trị của server được cấp quyền, xem:

1. Scope, pool, exclusions và reservations.
2. Lease active, offered/pending, expired, declined/conflict.
3. Các sự kiện cấp phát thất bại do pool exhaustion.
4. Server identity, relay/giaddr và Option 82 nếu áp dụng.
5. Thông số lease duration, T1/T2 nếu sản phẩm hỗ trợ cấu hình.
6. HA/failover replication và các lỗi liên lạc.
7. Dynamic DNS update và đối chiếu IPAM.

Không giả định tất cả sản phẩm đều có cùng các trạng thái hoặc lệnh quản trị. Các log chỉ cho biết quan sát từ **một hệ thống cụ thể**, cần đối chiếu với client và đường mạng.

## 12. Xử lý sự cố theo triệu chứng

~~~mermaid
flowchart TD
    A[Client không có IP mong đợi] --> B{Link / VLAN / NAC đúng?}
    B -->|Không| C[Kiểm tra interface, switch, Wi-Fi, 802.1X]
    B -->|Có| D{Discover / Request đến relay hoặc server?}
    D -->|Không| E[Kiểm tra client DHCP, snooping, relay, UDP]
    D -->|Có| F{Server có Offer / ACK đúng subnet?}
    F -->|Không| G[Kiểm tra scope, pool, HA, relay / server logs]
    F -->|Có| H{Client dùng được địa chỉ?}
    H -->|Không| I[Kiểm tra NAK, conflict, client ID và expiry]
    H -->|Có| J[Kiểm tra gateway, DNS, route, firewall, dịch vụ]
~~~

### 12.1. Không nhận được IPv4

Một máy có thể không có IPv4 dùng được hoặc sử dụng địa chỉ **169.254.0.0/16** (IPv4 link-local) khi không có cấu hình IPv4 mong đợi. Đó **không tự chứng minh** DHCP server đã ngừng hoạt động.

**Kiểm tra:** interface có link, VLAN và NAC đúng, DHCP client được bật, Discover tới được relay/server, Offer có quay về client, pool còn địa chỉ, DHCP snooping có chặn nhầm không.

### 12.2. Được cấp IP sai subnet

**Khả năng:** VLAN gắn sai, rogue DHCP server, relay giaddr/Option 82 không đúng hoặc server có policy chọn nhầm scope. Cần so sánh VLAN tại switch với gateway, Server Identifier, DHCPACK, scope và DNS/router option được nhận.

Không “sửa tạm” bằng cách tăng subnet mask hoặc mở tất cả ACL khi chưa tìm ra mạng mà client thực sự thuộc về.

### 12.3. Mất kết nối sau nhiều giờ

**Khả năng:** DHCP server/relay không tới được lúc T1/T2, firewall chặn renewal, máy chuyển mạng mà vẫn giữ thông tin cũ, lease quá ngắn hoặc failover lỗi. Hãy kiểm tra **Lease Obtained/Expires**, server identity, bản tin DHCPREQUEST/ACK và tuyến truyền tại các thời điểm liên quan.

Nếu lỗi đồng loạt ở một VLAN, ưu tiên kiểm tra relay/scope/đường mạng; nếu chỉ một máy, kiểm tra client ID, hệ điều hành và driver.

### 12.4. Pool còn IP theo thống kê nhưng client vẫn báo hết địa chỉ

**Khả năng:** pool cấp động nhỏ hơn tưởng tượng, địa chỉ reserved/excluded, declined/conflicted hoặc reclaim chưa chạy; đồng bộ HA lệch. Cần xác minh số **free allocatable addresses**, không chỉ active lease count.

### 12.5. DHCPACK thành công nhưng DNS không hoạt động

**Khả năng:** DNS resolver ở Option 6 sai, DNS server lỗi, firewall chặn UDP/TCP 53, sai vùng DNS hoặc DDNS record không đồng bộ. Đây là lỗi cấu hình/kết nối **khác với hết lease**.

### 12.6. Hai thiết bị có cùng IP

**Khả năng:** static IP trùng pool, HA/scope cấp trùng, client hoặc hệ thống kiểm tra conflict không phát hiện kịp. Đối chiếu DHCP server history, ARP/neighbor table, switch MAC table, reservation và IPAM trước khi đổi địa chỉ hoặc xóa lease.

## 13. Thiết kế tính sẵn sàng và quản trị thay đổi

### 13.1. Failover và dự phòng

Mạng có nhiều VLAN và client quan trọng cần phương án dự phòng DHCP phù hợp: server HA/failover được **sản phẩm hỗ trợ**, các relay có đường tới server còn hoạt động, giám sát trạng thái replication và kế hoạch khôi phục.

**Không để hai DHCP server độc lập tùy tiện cấp trùng một pool** nếu không có đồng bộ hoặc phân vùng địa chỉ rõ ràng. Cấu hình không nhất quán có thể tạo trùng địa chỉ, đặc biệt trong split-brain.

### 13.2. Thay đổi lease time, router hoặc DNS

1. Kiểm kê client, scope, owner, tùy chọn hiện tại và phụ thuộc ứng dụng.
2. Xác nhận subnet, relay, firewall, DNS, IPAM và HA phù hợp thiết kế mới.
3. Thử trên lab/VLAN thử nghiệm với client vừa nhận IP và client đã có lease.
4. Triển khai theo lịch, có rollback cấu hình và logging trước/sau thay đổi.
5. Giám sát renewal và xác nhận các client nhận options mới khi lease được gia hạn/đổi cấu hình.

Không cho rằng thay Option 3/6 trên server sẽ lập tức đổi route hoặc DNS trên **mọi** client online. Thời điểm nhận lại cấu hình phụ thuộc lease và hành vi hệ điều hành.

### 13.3. Quản trị dữ liệu lịch sử

DHCP lease log có thể chứa địa chỉ MAC, tên máy, định danh client và thời điểm thiết bị xuất hiện trong mạng. Chỉ cấp quyền xem/sửa cho vai trò thích hợp, áp dụng thời hạn lưu log, đồng bộ timestamp và hạn chế công khai danh sách thiết bị khi không cần thiết.

## 14. Tình huống thực hành

**Bối cảnh:** mạng nhân viên **192.0.2.0/24** dùng dynamic pool **192.0.2.100–192.0.2.199** (100 IP). DHCP server tập trung ở subnet khác qua relay, gateway **192.0.2.1**, lease duration **8 giờ**. Laptop A nhận DHCPACK tại **08:00** cho **192.0.2.110**. Đường từ relay tới server gián đoạn từ **11:30 tới 15:30**.

Giả sử T1/T2 dùng tỷ lệ mặc định của DHCPv4:

| Thời điểm | Hành vi/kỳ vọng |
| --- | --- |
| 08:00 | A có lease hiệu lực, expiry dự kiến 16:00 |
| 11:30 | Đường relay–server bị gián đoạn; lease A chưa hết hạn |
| 12:00 | T1: bắt đầu thử gia hạn; chưa liên lạc được server |
| 15:00 | T2: bắt đầu thử rebind; server vẫn không tới được |
| 15:30 | Đường mạng hồi phục; A có cơ hội nhận DHCPACK trước expiry |
| 16:00 | Nếu không nhận xác nhận gia hạn, lease cũ hết hạn và phải ngừng dùng IP đó |

**Câu hỏi tự kiểm tra:**

1. Vì sao A không bắt buộc mất IP ngay lúc 11:30?
2. Tính T1, T2 và expiry của lease từ 08:00, duration 8 giờ.
3. Laptop B mới đến VLAN lúc 13:00 có thể gặp vấn đề nào khác laptop A?
4. Nếu A được DHCPACK gia hạn lúc 15:40, nó có phải ngừng sử dụng IP lúc 16:00 không?
5. Tại sao firewall giữa relay và server phải cho đúng DHCP traffic dù ứng dụng của nhân viên dùng HTTPS?
6. Nếu A nhận địa chỉ hợp lệ nhưng DNS không hoạt động, đó có tự động là lỗi lease expiry?
7. Một số máy trong VLAN nhận gateway lạ: cần điều tra những nguyên nhân gì?
8. Vì sao tổng 100 khách ghé trong ngày chưa chắc làm cạn pool 100 địa chỉ?
9. Vì sao IP của laptop A hôm nay không đủ để xác định danh tính người dùng IP này trong log tuần trước?
10. Khi triển khai dual-stack, những lớp kiểm soát nào phải thêm ngoài DHCPv4 snooping?

**Gợi ý:** (1) Lease của A còn hiệu lực. (2) T1=12:00, T2=15:00, expiry=16:00. (3) B có thể không nhận được IP mới khi server không tới được. (4) Không, nếu ACK gia hạn cấp thời hạn còn hiệu lực mới. (5) DHCP/relay là luồng UDP hạ tầng riêng. (6) Không; cần kiểm tra DNS Option 6, resolver và route. (7) Rogue DHCP, VLAN/relay/scope sai. (8) Phụ thuộc số thiết bị đồng thời, thời điểm hết hạn và tái sử dụng. (9) IP có thể được cấp lại. (10) DHCPv6, RA/SLAAC, DHCPv6 Guard/RA Guard và firewall IPv6.

## 15. Các hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Nhận DHCPOFFER là đã có IP sử dụng hoàn tất.” | Thông thường cần REQUEST/ACK và xác minh địa chỉ. |
| “IP luôn gắn với một MAC vĩnh viễn.” | Địa chỉ và client identifier có thể đổi; IP được cấp lại theo thời gian. |
| “T1 là lúc lease hết hạn.” | T1 là mốc renewal; expiry là mốc khác. |
| “Không renew tại T1 thì client mất IP ngay.” | Khi lease vẫn còn hiệu lực, client có thể tiếp tục dùng và thử rebind. |
| “Reservation là IP tĩnh cấu hình trên client.” | Reservation được quản trị ở server và vẫn có thể dùng DHCP. |
| “DHCPACK chứng minh thiết bị đã xác thực an toàn.” | DHCP không thay NAC/802.1X, firewall hoặc xác thực ứng dụng. |
| “DHCPv6 cấp default gateway giống IPv4 Option 3.” | IPv6 sử dụng Router Advertisement để cung cấp default router. |
| “SLAAC luôn có DHCPv6 lease cấp địa chỉ.” | SLAAC có thể hoạt động không cần DHCPv6 stateful. |
| “Lease càng ngắn càng tốt.” | Lease quá ngắn gây nhiều renewal và tăng rủi ro khi server mất kết nối. |
| “Active leases bằng số thiết bị đang online.” | Client rời mạng có thể còn lease chưa hết hạn. |
| “Có DHCP snooping rồi không cần bảo vệ DNS.” | Rogue DNS/RA, DNS server và quyền ứng dụng là lớp riêng. |
| “Một lần không capture thấy DHCP nghĩa là server đã chết.” | Có thể do điểm quan sát sai hoặc client đang trong lease còn hiệu lực. |

## 16. Tổng kết

**DHCP lease** là cơ chế phân phối và quản lý quyền sử dụng địa chỉ IP theo thời gian. Đối với DHCPv4, cần hiểu **DORA**, tiến trình **BOUND → RENEWING (T1) → REBINDING (T2) → expiry**, cùng scope, pool, reservation, relay và lịch sử cấp địa chỉ trong IPAM.

Về an toàn mạng, cần ngăn **rogue DHCP**, theo dõi **DHCP starvation/pool exhaustion**, kiểm soát **IP conflict** và bảo vệ vị trí tin cậy bằng DHCP snooping/NAC cùng chính sách firewall. Với mạng IPv6/dual-stack, phải hiểu riêng **DHCPv6, Router Advertisement và SLAAC**. Lease log là nguồn đối chiếu có ích cho IDS/IPS và điều tra, nhưng chỉ có ý nghĩa khi gắn **đúng thời điểm** và đối chiếu các nguồn danh tính khác.

Trong **SECURITY_NETWORK_SECURITY**, quản trị lease chính xác là điều kiện giúp phân đoạn, firewall, VPN, bảo vệ DNS và giám sát lưu lượng có dữ liệu nền đáng tin cậy, giảm lỗi vận hành và nâng khả năng truy vết khi xảy ra sự cố.

### Tài liệu tham khảo

- **RFC 2131 — Dynamic Host Configuration Protocol:** vòng đời lease, DHCPv4 và renewal/rebinding.
- **RFC 2132 — DHCP Options and BOOTP Vendor Extensions:** DHCPv4 options như router, DNS, lease time và Server Identifier.
- **RFC 3046 — DHCP Relay Agent Information Option:** DHCPv4 Option 82.
- **RFC 5227 — IPv4 Address Conflict Detection:** quy tắc kiểm tra xung đột địa chỉ IPv4.
- **RFC 5737 — IPv4 Address Blocks Reserved for Documentation:** địa chỉ tài liệu dùng trong ví dụ.
- **RFC 8415 — Dynamic Host Configuration Protocol for IPv6 (DHCPv6):** IA_NA, IA_PD, lifetimes, message types và quy trình renew/rebind.
- **RFC 4862 — IPv6 Stateless Address Autoconfiguration:** SLAAC và trạng thái/lifetime của địa chỉ.
- **RFC 4861 — Neighbor Discovery for IPv6:** Router Advertisement và thông tin router IPv6.
