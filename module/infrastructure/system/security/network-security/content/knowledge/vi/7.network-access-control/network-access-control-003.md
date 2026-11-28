# Firewall rule

> **Chương:** Network access control  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Thiết kế các lớp phòng vệ mạng bằng phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi và hạ tầng đám mây; kết hợp phân tích lưu lượng, mô hình hóa mối đe dọa và giám sát để vận hành mạng an toàn.

## 1. Firewall rule là gì?

**Firewall rule** (quy tắc tường lửa) quy định điều kiện để một luồng hoặc gói tin mạng được **cho phép (allow/accept)**, **từ chối (deny/drop/reject)**, ghi log hoặc xử lý theo một hành động khác. Rule là đơn vị cụ thể để thực thi **chính sách kiểm soát truy cập mạng** (Network Access Control).

Ví dụ: “Chỉ máy thuộc phân đoạn ứng dụng được kết nối TCP đến cổng PostgreSQL của cơ sở dữ liệu; các mạng khác không được kết nối trực tiếp.” Chính sách này có thể được diễn đạt bằng một hay nhiều firewall rule, tùy loại thiết bị, chiều kết nối, NAT, zone và khả năng theo dõi trạng thái.

Firewall rule trả lời câu hỏi **lưu lượng nào có thể đi qua điểm kiểm soát này**, nhưng không chứng minh rằng người dùng đã được xác thực, ứng dụng không có lỗ hổng hay đường truyền được mã hóa. Bảo vệ mạng hiệu quả đòi hỏi phối hợp **phân đoạn, danh tính, mã hóa, giám sát và ứng cứu**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Đọc và thiết kế rule theo nguồn, đích, giao thức, cổng, chiều lưu lượng, zone và hành động.
2. Phân biệt firewall **stateful/stateless**, rule có thứ tự và rule không xét theo thứ tự.
3. Hiểu sự liên hệ giữa firewall rule với routing, NAT, VPN, DNS, IPv6 và phân đoạn mạng.
4. Áp dụng **least privilege**, **default deny**, giới hạn phạm vi và quản lý vòng đời rule.
5. Thiết kế ma trận kiểm thử allow/deny, phân tích log và khắc phục rule sai hoặc bị che khuất.

## 2. Firewall kiểm tra thông tin nào?

Một rule ở tầng mạng và vận chuyển (L3/L4) thường dựa trên những tiêu chí sau:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Source address / subnet** | Địa chỉ hoặc dải mạng nguồn của gói | 10.30.10.0/24 |
| **Destination address / subnet** | Địa chỉ, mạng hoặc đối tượng đích | 10.20.30.15/32 |
| **Protocol** | IP protocol: TCP, UDP, ICMPv4, ICMPv6... | TCP |
| **Source port** | Cổng nguồn đối với TCP/UDP, thường do hệ điều hành chọn động | 51432 |
| **Destination port** | Cổng dịch vụ ở đích | 443, 22, 5432 |
| **Direction** | Ingress/inbound, egress/outbound hoặc qua vùng (forwarding) | Từ VPN sang vùng quản trị |
| **Zone / interface** | Vùng mạng và giao diện nhận/gửi, nếu firewall hỗ trợ | Internet → DMZ |
| **Connection state** | Trạng thái kết nối được firewall theo dõi | NEW, ESTABLISHED, RELATED |
| **Identity / application** | Người dùng, thiết bị, ứng dụng hoặc phân loại L7 trên sản phẩm hỗ trợ | Nhóm quản trị viên, ứng dụng HTTPS |
| **Action** | Cho phép, bỏ gói, từ chối có phản hồi, ghi log hoặc chuyển qua xử lý bổ sung | ALLOW, DROP, REJECT |
| **Priority / order** | Vị trí hoặc độ ưu tiên nếu engine xử lý theo thứ tự | Rule 10 trước rule 20 |

**5-tuple** thường được dùng để nhận diện luồng TCP/UDP: **IP nguồn, IP đích, cổng nguồn, cổng đích, giao thức**. Tuy nhiên, không phải mọi rule đều cần đủ năm trường. ICMP không có cổng TCP/UDP; với ICMP cần quan tâm **type/code**, ví dụ Echo Request, Destination Unreachable hoặc ICMPv6 Packet Too Big.

**Cần phân biệt:** firewall ở L3/L4 thường ra quyết định bằng IP, protocol, port và trạng thái. Firewall có khả năng kiểm tra lớp ứng dụng có thể thêm URL, hostname, SNI, HTTP method hoặc nhận diện ứng dụng. Mức tin cậy của điều kiện L7 phụ thuộc khả năng nhìn thấy lưu lượng, mã hóa TLS, xác thực nguồn dữ liệu và chức năng của thiết bị; tên miền hoặc SNI tự chúng **không xác thực danh tính máy chủ hay người dùng**.

## 3. Rule xử lý gói tin như thế nào?

Firewall thường kiểm tra gói đi qua một **hook/chain hoặc chính sách áp dụng tại interface/zone**. Tùy nền tảng, trình tự có thể gồm kiểm tra trạng thái, bảng route, NAT, các chain và policy bảo mật. Vì vậy, phải biết **thiết bị đang áp dụng rule ở điểm nào trên đường đi**.

~~~mermaid
flowchart TD
    A[Gói tin đến firewall] --> B[Nhận diện ingress interface / zone]
    B --> C[Kiểm tra state, NAT và điều kiện nền tảng]
    C --> D{Có rule khớp theo cơ chế của thiết bị?}
    D -- Có --> E{Hành động?}
    E -- Allow --> F[Cho chuyển tiếp hoặc xử lý tiếp]
    E -- Drop / Reject --> G[Chặn, ghi log nếu được cấu hình]
    D -- Không --> H[Áp dụng default policy]
    H --> I[Allow hoặc deny theo policy]
~~~

### 3.1. Rule có thứ tự: first match

Nhiều firewall theo ACL hoặc security policy xử lý rule **từ trên xuống**, dừng ở **rule khớp đầu tiên**. Khi đó, rule đặt trước có thể che mất (*shadow*) rule ở dưới:

| Thứ tự | Điều kiện | Action | Vấn đề |
|---|---|---|---|
| 10 | Mọi nguồn → 10.20.30.15, TCP 5432 | ALLOW | Quá rộng. |
| 20 | Chỉ subnet 10.20.20.0/24 → 10.20.30.15, TCP 5432 | ALLOW | Không tăng bảo mật: traffic đã khớp rule 10. |
| 30 | Mọi nguồn còn lại → DB | DENY | Không chặn được kết nối DB đã được rule 10 cho phép. |

Nếu mục tiêu là **chỉ ứng dụng** được truy cập DB, hãy xóa/sửa rule quá rộng, đặt rule cho phép cụ thể ở trên chính sách từ chối và **xác minh bằng thử nghiệm thực tế**.

### 3.2. Không phải hệ thống nào cũng dùng first match

Một số nền tảng dùng rule có **priority số**, rule chain, hoặc **tập hợp nhiều rule cho phép** không phụ thuộc thứ tự hiển thị. Ví dụ, **AWS security group** là cơ chế **stateful**, có các rule **allow** và không có rule deny riêng trong security group; các rule không được xét như ACL first-match. **AWS network ACL** là cơ chế **stateless**, đánh giá các rule có số thứ tự tăng dần và có allow/deny.

Do đó, không thể mang nguyên tư duy “rule 1 luôn thắng rule 2” áp dụng cho mọi firewall. Phải đọc cơ chế của đúng nền tảng và biết **default action** của nó.

### 3.3. Allow, drop, reject và log

- **ALLOW/ACCEPT:** cho phép gói hoặc kết nối phù hợp đi tiếp, có thể còn bị kiểm tra ở lớp khác.
- **DROP/DENY im lặng:** bỏ gói mà không gửi phản hồi rõ ràng cho bên gửi; ứng dụng có thể chờ timeout.
- **REJECT:** chủ động trả phản hồi lỗi phù hợp khi nền tảng và giao thức hỗ trợ; giúp chẩn đoán nhưng cũng có thể cung cấp tín hiệu cho bên quét.
- **LOG:** thường là hành động bổ sung hoặc một rule log riêng; cần cấu hình vị trí, tần suất và mức chi tiết để tránh tràn log.

Tên hành động và việc có tiếp tục xét rule khác sau khi log hay không tùy sản phẩm. Không giả định log tự động đồng nghĩa chặn.

## 4. Stateful và stateless firewall

Đây là khác biệt quan trọng khi viết rule hai chiều.

### 4.1. Stateful

Firewall **stateful** lưu thông tin trạng thái/flow (connection tracking). Khi phía trong chủ động mở một kết nối được phép, firewall có thể nhận diện **gói phản hồi hợp lệ** và cho đi qua mà không cần viết rule đối xứng cho mọi cổng nguồn động.

~~~text
Client 10.10.10.25:51432
    -> Server 10.20.20.10:443    TCP SYN (kết nối mới)
Firewall: kiểm tra policy allow -> lưu trạng thái flow
Server 10.20.20.10:443
    -> Client 10.10.10.25:51432  TCP SYN-ACK (phản hồi)
Firewall: nhận diện flow hợp lệ -> cho phép theo state
~~~

Stateful không có nghĩa tự xác thực người dùng hoặc phát hiện mọi hành vi độc hại. Với UDP, firewall có thể tạo **trạng thái giả (pseudo-state)** từ cặp địa chỉ/cổng và timeout; không có TCP handshake. Với ICMP, thiết bị có thể nhận diện thông điệp lỗi liên quan flow ban đầu, nhưng cách xử lý phụ thuộc engine.

Các rule có thể thay đổi trong khi flow đang hoạt động; một số thiết bị vẫn duy trì phiên đã được chấp nhận cho đến khi connection tracking hết hạn hoặc bị xóa. **Muốn kiểm tra việc thu hồi quyền, cần phân biệt kết nối mới và phiên đang tồn tại.**

### 4.2. Stateless

Firewall **stateless** xét từng gói theo trường header và chính sách tại hướng tương ứng, không tự biết gói là phản hồi của một phiên đã được cho phép. Với ACL stateless, muốn ứng dụng hoạt động có thể phải cho phép **lưu lượng chiều về** theo đúng địa chỉ và cổng động cần thiết. Mở toàn bộ dải cổng không kiểm soát để “sửa lỗi” là cách làm nguy hiểm.

| Khía cạnh | Stateful | Stateless |
|---|---|---|
| Quyết định chính | Rule + ngữ cảnh trạng thái kết nối | Rule áp dụng trên từng gói |
| Phản hồi lưu lượng | Thường cho phép theo session hợp lệ | Cần rule chiều về phù hợp |
| Ưu thế | Đơn giản hóa rule trả lời; ngăn một số gói không thuộc flow | Dễ dự đoán ở cấp packet, có thể phù hợp ACL mạng hiệu năng cao |
| Hạn chế | Tốn trạng thái, chịu ảnh hưởng timeout, bất đối xứng tuyến và cạn bảng flow | Dễ cấu hình thiếu hoặc quá rộng ở chiều về |

**Định tuyến bất đối xứng** có thể gây sự cố khi hai chiều một phiên đi qua những stateful firewall khác nhau mà không chia sẻ trạng thái. Khi phân tích lỗi, xem cả đường đi và đường về.

## 5. Default deny và nguyên tắc quyền tối thiểu

**Default deny** nghĩa là chỉ cho phép lưu lượng được xác định hợp lệ; phần còn lại bị từ chối theo policy. **Least privilege** nghĩa là cho đúng nguồn, đích, giao thức, dịch vụ, thời gian và điều kiện cần cho chức năng.

Trong mạng doanh nghiệp, triển khai thường theo hướng:

1. **Xác định luồng bắt buộc** từ yêu cầu ứng dụng và chủ tài sản: ai cần kết nối tới đâu, bằng giao thức gì.
2. **Phân vùng tin cậy**: Internet, DMZ, Application, Database, Management, User, Guest Wi-Fi, Partner/VPN và cloud.
3. **Cho phép luồng cụ thể**; giữ rule dưới dạng dễ đọc, gắn owner và lý do.
4. **Từ chối mặc định** các luồng không được cấp phép; cân nhắc log cho sự kiện có giá trị.
5. **Kiểm chứng luồng hợp lệ và không hợp lệ** trước/sau khi áp dụng.

Không được suy từ “deny all” rằng mạng sẽ vận hành bình thường. Cần cho phép có kiểm soát các giao thức thiết yếu như DNS, DHCP, NTP, health checks, thông điệp ICMP phục vụ chẩn đoán/Path MTU Discovery, ICMPv6 cần cho IPv6 và dịch vụ quản trị theo từng vùng.

## 6. Thiết kế một bộ rule cho ứng dụng ba tầng

Giả sử hệ thống minh họa gồm:

- **Internet:** nguồn công cộng; điểm truy cập HTTPS công khai là VIP **203.0.113.20** (dải dành cho tài liệu).
- **DMZ/WAF:** reverse proxy hoặc WAF nhận HTTPS từ Internet.
- **Application subnet:** **10.20.20.0/24**, ứng dụng tại **10.20.20.10**.
- **Database subnet:** **10.20.30.0/24**, PostgreSQL tại **10.20.30.15:5432**.
- **Management subnet:** jump host **10.20.40.10**.
- **VPN-admin subnet:** **10.30.10.0/24** sau xác thực VPN, chỉ chứa nhóm được cấp quyền theo thiết kế.
- **DNS resolver nội bộ:** **10.20.50.53**.

~~~mermaid
flowchart LR
    U[Internet] -->|TCP 443| V[VIP / WAF ở DMZ]
    V -->|TCP 8443| A[App 10.20.20.10]
    A -->|TCP 5432| D[(DB 10.20.30.15)]
    A -->|DNS UDP/TCP 53| N[Resolver 10.20.50.53]
    P[VPN admins 10.30.10.0/24] -->|TCP 22| J[Jump host 10.20.40.10]
~~~

### 6.1. Ma trận luồng được cấp phép

| Rule logic | Nguồn / zone | Đích / zone | Dịch vụ | Hành động | Mục đích |
|---|---|---|---|---|---|
| R-010 | Internet | HTTPS VIP/WAF tại DMZ | TCP 443 | ALLOW | Người dùng truy cập ứng dụng qua cửa ngõ công khai |
| R-020 | WAF | App 10.20.20.10 | TCP 8443 | ALLOW | WAF chuyển yêu cầu đến backend |
| R-030 | App 10.20.20.10 | DB 10.20.30.15 | TCP 5432 | ALLOW | Ứng dụng truy cập cơ sở dữ liệu |
| R-040 | VPN-admin 10.30.10.0/24 | Jump host 10.20.40.10 | TCP 22 | ALLOW | Quản trị qua điểm trung gian |
| R-050 | App 10.20.20.10 | Resolver 10.20.50.53 | UDP/TCP 53 | ALLOW | Truy vấn DNS qua resolver được quản lý |
| R-060 | Các zone / đích xác định | Luồng ICMP vận hành cần thiết | ICMPv4/ICMPv6 có chọn lọc | ALLOW có giới hạn | Báo lỗi, PMTU, khám phá và giám sát theo nhu cầu |
| R-990 | Các luồng còn lại | Các đích còn lại | Giao thức khác | DENY + LOG theo chính sách | Thực hiện default deny |

**Đây là bảng chính sách logic phục vụ học tập, không phải tập rule copy trực tiếp vào thiết bị.** Thực tế còn có health check, xác thực/SSO, monitoring, đồng bộ thời gian, cập nhật hệ thống, backup, giao diện quản trị và luồng hạ tầng tùy môi trường.

### 6.2. Phân tích các quyết định

**Vì sao Internet không được truy cập thẳng DB?** DB chứa dữ liệu nhạy cảm; chỉ dịch vụ ứng dụng được phép kết nối tới cổng cần thiết. Phân đoạn giảm tác động nếu một thành phần khác bị chiếm quyền.

**Vì sao chỉ VPN-admin được vào jump host?** VPN tạo kênh bảo vệ nhưng không tự cấp quyền quản trị cho mọi người dùng VPN. Trên thực tế còn cần chính sách theo danh tính, MFA, posture và quyền tối thiểu trên jump host.

**Vì sao app chỉ dùng DNS nội bộ?** Quy tắc egress ngăn app gửi DNS tự do tới resolver bất kỳ; tuy nhiên **DNS over HTTPS/DoT** hoặc các kênh ứng dụng khác có thể cần chính sách L7/egress bổ sung.

**Vì sao không mở any → any để tránh lỗi kết nối?** Rule quá rộng làm mất tác dụng phân đoạn, khiến kẻ tấn công có thể di chuyển ngang giữa các subnet nếu chiếm được một máy.

### 6.3. Dạng rule giả mã dễ đọc

~~~text
# MINH HỌA - KHÔNG PHẢI CÚ PHÁP CỦA FIREWALL CỤ THỂ
allow from Internet  to WAF_VIP        service tcp/443     reason HTTPS_PUBLIC
allow from WAF       to APP           service tcp/8443    reason WAF_TO_APP
allow from APP       to DB            service tcp/5432    reason APP_TO_DB
allow from VPN_ADMIN to JUMP_HOST     service tcp/22      reason ADMIN_SSH
allow from APP       to DNS_RESOLVER  service udp,tcp/53  reason INTERNAL_DNS
allow required ICMP errors and on-link IPv6 control traffic per zone/interface
deny all other cross-zone traffic; log selected denies with rate limits
~~~

Trên firewall **stateful**, phản hồi hợp lệ có thể được chấp nhận theo trạng thái; trên thiết bị **stateless** phải thiết kế chiều về phù hợp. Nếu VIP dùng **DNAT** từ 203.0.113.20 sang IP của WAF, điều kiện địa chỉ ở rule phải bám đúng **thứ tự xử lý NAT và firewall** của nền tảng. Không tự mặc định rule luôn thấy địa chỉ trước hoặc sau NAT.

## 7. NAT, routing và vị trí triển khai rule

Firewall rule chỉ có tác dụng với **lưu lượng thực sự đi qua điểm thực thi**. Không thể ngăn một đường truy cập trực tiếp bằng rule đặt trên tuyến khác.

### 7.1. Routing và policy không giống nhau

- **Route table** quyết định gói được gửi tới next hop nào khi có route phù hợp.
- **Firewall policy** quyết định lưu lượng có được phép qua điểm kiểm soát hay không.
- **NAT** thay đổi địa chỉ/cổng theo cấu hình; không thay thế kiểm soát truy cập và cũng không tự chứng minh truy cập an toàn.
- **Application/IAM policy** quyết định người dùng/dịch vụ được làm gì sau khi kết nối đến được hệ thống.

Một gói có thể bị chặn vì không có route, rule deny, NAT sai, thiếu trạng thái kết nối, host firewall chặn hoặc dịch vụ không lắng nghe. Khi kiểm tra, cần tách từng nguyên nhân.

### 7.2. Inbound, outbound và transit

| Đường lưu lượng | Nơi thường cần rule | Ví dụ |
|---|---|---|
| **Ingress vào host** | Host firewall INPUT hoặc inbound security group | Admin SSH tới jump host |
| **Egress từ host** | Host firewall OUTPUT hoặc outbound security group | App hỏi DNS resolver |
| **Transit giữa zone** | Firewall/router FORWARD, policy zone-based hoặc NACL | App subnet truy cập DB subnet |
| **Ingress từ Internet qua NAT** | Firewall biên + NAT + backend policy | Khách kết nối HTTPS VIP |

Các tên chain/hook thay đổi theo sản phẩm. Rule INPUT của Linux bảo vệ chính host đó; lưu lượng **được định tuyến xuyên qua** thiết bị thuộc luồng forwarding và có đường xử lý khác.

## 8. IPv4, IPv6 và các giao thức điều khiển

Sao chép rule IPv4 không có nghĩa chính sách IPv6 đã tương đương. Một mạng dual-stack có thể công khai dịch vụ qua IPv6 dù IPv4 chỉ cho truy cập qua VPN. Cần kiểm kê **cả hai họ địa chỉ** và kiểm thử riêng.

### 8.1. ICMP là thành phần vận hành, không chỉ là ping

Với IPv4, thông điệp **Destination Unreachable / Fragmentation Needed** (ICMPv4 type 3/code 4) hỗ trợ Path MTU Discovery. Với IPv6, **Packet Too Big** (ICMPv6 type 2) rất quan trọng vì router IPv6 không thực hiện phân mảnh gói khi chuyển tiếp. ICMPv6 còn phục vụ **Neighbor Discovery** (Router Solicitation, Router Advertisement, Neighbor Solicitation, Neighbor Advertisement), thiết yếu trên liên kết IPv6.

**Chặn toàn bộ ICMP/ICMPv6 có thể làm hỏng truyền dữ liệu lớn, kết nối VPN hoặc hoạt động IPv6.** Nên cho phép các thông điệp cần thiết theo **type/code, nguồn, đích, hướng và vị trí mạng**, kèm kiểm soát rate limit nếu thích hợp. Không chuyển các thông điệp NDP vốn thuộc phạm vi liên kết qua mọi zone một cách vô điều kiện.

### 8.2. Lưu ý với giao thức không phải TCP

| Giao thức | Đặc điểm | Thiết kế rule |
|---|---|---|
| **UDP** | Không có handshake TCP; phản hồi phụ thuộc timeout của stateful engine | Cho phép đúng resolver/dịch vụ và xem bảng trạng thái, chiều về |
| **ICMPv4/ICMPv6** | Dùng **type/code**, không dùng TCP/UDP port | Tránh rule “ICMP any any” không cần thiết; giữ lỗi vận hành hợp lệ |
| **ESP/AH hoặc IPsec** | Giao thức IP riêng; IKE thường dùng UDP 500/4500, tùy mô hình | Kiểm tra các thành phần thực sự dùng và vị trí terminate VPN |
| **GRE và các tunnel khác** | Có thể không sử dụng cổng TCP/UDP | Rule theo IP protocol/đích; cân nhắc dữ liệu bên trong tunnel |

Với IPSec qua NAT, **NAT-T dùng UDP 4500** khi thích hợp. Mở TCP 443 không tự cho phép mọi loại VPN, và mở UDP 500/4500 không tự chứng minh xác thực VPN đúng.

## 9. Phòng tránh rule quá rộng, trùng lặp và shadowed rule

### 9.1. Những mẫu rule cần cảnh giác

| Mẫu | Vì sao rủi ro | Hướng thay đổi |
|---|---|---|
| Any source → Any destination, Any service, ALLOW | Mất khả năng phân đoạn và truy vết mục đích | Chia theo zone, tài sản, dịch vụ và owner |
| Internet → toàn bộ mạng quản trị, TCP 22 | Lộ mặt phẳng quản trị | Chỉ từ VPN/bastion được cấp quyền; thêm MFA, logging |
| User subnet → DB subnet, toàn bộ cổng | Cho phép đi ngang và truy cập ngoài ứng dụng | Chỉ application tier đến DB IP/cổng |
| Mọi máy → mọi DNS resolver | Khó kiểm soát egress và theo dõi truy vấn | Chỉ resolver được quản lý; xét DoH/DoT |
| Rule cho phép rộng nằm trước deny cụ thể | Deny bị che trên firewall first-match | Loại/sửa allow rộng, kiểm tra thứ tự thực tế |
| Rule tạm không hạn sử dụng | Trở thành quyền lâu dài ngoài thiết kế | Gắn ticket, owner, expiration và review |
| Rule chỉ áp dụng IPv4 trong hệ dual-stack | Tạo đường IPv6 khác chính sách | Tạo phạm vi IPv6 tương ứng, kiểm chứng riêng |

### 9.2. Shadowing, redundancy và conflict

- **Shadowed:** một rule không bao giờ được xét tới vì lưu lượng phù hợp đã khớp rule ở trước, trong engine first-match.
- **Redundant:** hai rule có cùng hiệu lực trong phần lớn hoặc toàn bộ tập gói; loại bỏ rule dư cần xem log, object group và phụ thuộc.
- **Conflicting:** hai rule hoặc hai lớp policy thể hiện ý định trái nhau; phải kiểm tra **cơ chế hợp nhất/ưu tiên thực** của nền tảng.

Sử dụng **hit counter** để hỗ trợ xem rule còn dùng không, nhưng counter bằng 0 **không đủ** để xóa: có thể rule chỉ dùng khi failover, khôi phục thảm họa hoặc tác vụ định kỳ hiếm.

## 10. Firewall rule trong cloud và môi trường hiện đại

Cloud triển khai nhiều tầng chính sách đồng thời:

~~~text
Internet / user / on-premises
  -> Cloud edge / Internet gateway / load balancer
  -> VPC/VNet route + network ACL / subnet policy
  -> Security group / workload NIC policy
  -> Host firewall / container network policy
  -> Service authentication and authorization
~~~

Các tầng này có thể cùng chặn một luồng; muốn cho phép lưu lượng, **mọi tầng bắt buộc trên đường đi** cần có cấu hình phù hợp.

**Ví dụ với AWS:** security group theo tài nguyên mạng là **stateful allow rules**. Network ACL tại subnet là **stateless**, có thứ tự rule allow/deny và phải xem cả inbound lẫn outbound. Không suy rằng mọi cloud provider dùng đúng các đặc tính đó; cần tra tài liệu nền tảng đang triển khai.

Trong **Kubernetes**, network policy phụ thuộc khả năng hỗ trợ của **CNI** và cách cộng gộp các policy. Một NetworkPolicy mặc định không thay thế firewall của node, security group, load balancer hay quyền RBAC/IAM. Đối với egress, cần kiểm tra DNS và dịch vụ hệ thống để không làm gián đoạn cluster.

Trong **Zero Trust**, kiểm tra IP/port chỉ là một phần. Việc cấp quyền còn phụ thuộc **danh tính người dùng, trạng thái thiết bị, ngữ cảnh truy cập và chính sách tại dịch vụ**. Firewall rule không thay thế mTLS, xác thực, phân quyền ứng dụng hay giám sát.

## 11. Tích hợp với threat modeling và giám sát xâm nhập

Một rule tốt nên liên hệ với **tài sản, đường tấn công và mục tiêu bảo mật**. Ví dụ kịch bản: kẻ tấn công chiếm một máy ở Wi-Fi khách và tìm cách đi sang mạng quản trị.

~~~mermaid
flowchart TD
    A[Thiết bị bị chiếm ở Guest Wi-Fi] --> B{Có đường tới Management?}
    B -- Không theo ACL --> C[Giảm nguy cơ di chuyển ngang]
    B -- Có --> D[Thử truy cập SSH / API quản trị]
    D --> E{Có xác thực / phân quyền?}
    E -- Không đạt --> F[Ứng dụng từ chối và log]
    E -- Bị vượt qua --> G[Nguy cơ chiếm hệ thống quản trị]
    C --> H[Giám sát hit/drop và anomaly]
    F --> H
~~~

**Kiểm soát nhiều lớp:** tách Guest Wi-Fi thành zone riêng; chỉ cho DNS/DHCP và egress Internet hợp lệ; deny tới management subnet; truy cập quản trị chỉ qua VPN/bastion có MFA và quyền tối thiểu; giám sát firewall, IDS/IPS và nhật ký ứng dụng.

Firewall thường không quan sát được toàn bộ hành vi **nằm trong luồng đã được cho phép**, ví dụ ứng dụng web có lỗi logic hoặc dữ liệu bị gửi qua HTTPS hợp lệ. IDS/IPS, WAF, endpoint protection và phân tích ứng dụng cung cấp tín hiệu bổ sung. Dữ liệu được mã hóa có thể làm giảm khả năng nhìn sâu payload của sensor.

### Các sự kiện đáng theo dõi

- Nhiều lần deny từ cùng một nguồn tới nhiều IP hoặc cổng khác nhau (**scan**).
- Truy cập từ zone không được cấp quyền tới subnet quản trị hoặc cơ sở dữ liệu.
- Thay đổi rule ngoài change window, mở any-any hoặc thay đổi chính sách egress.
- Rule chưa từng sử dụng bỗng nhận nhiều lưu lượng, hoặc hit counter của rule quan trọng thay đổi bất thường.
- Truy vấn DNS, chuyển dữ liệu ra ngoài hoặc truy cập từ VPN khác với hành vi thường ngày.
- Mất log, firewall hết bộ nhớ trạng thái hoặc thay đổi tuyến khiến sensor không còn nhìn thấy traffic.

Không nên tự suy ra mọi lần deny đều là tấn công. Các lỗi DNS, PMTU, dịch vụ chưa mở hoặc quét kiểm kê được cấp phép cũng có thể tạo log tương tự. Correlate với nguồn dữ liệu và bối cảnh vận hành.

## 12. Kiểm thử firewall rule đúng cách

Đừng chỉ kiểm tra đường **được phép**. Bộ kiểm thử tốt còn xác minh **đường bị cấm**, cả chiều đi/về, giao thức, phiên hiện có và tác động ngoài dự kiến.

### 12.1. Ma trận kiểm thử

| Test | Nguồn | Đích | Kỳ vọng | Cần quan sát |
|---|---|---|---|---|
| T-01 | Internet | WAF VIP TCP 443 | ALLOW | Kết nối TLS/HTTPS phục vụ đúng |
| T-02 | Internet | DB TCP 5432 | DENY | Không có đường trực tiếp tới DB |
| T-03 | App 10.20.20.10 | DB 10.20.30.15 TCP 5432 | ALLOW | Ứng dụng có thể kết nối DB |
| T-04 | Guest Wi-Fi | DB TCP 5432 | DENY | Firewall/ACL chặn truy cập trái phép |
| T-05 | VPN-admin hợp lệ | Jump host TCP 22 | ALLOW | SSH đi được, authentication vẫn bắt buộc |
| T-06 | User VPN thường | Jump host TCP 22 | DENY | Phân quyền theo zone/role đúng |
| T-07 | App | Resolver nội bộ UDP/TCP 53 | ALLOW | DNS trả lời qua resolver cho phép |
| T-08 | App | Resolver ngoài không được cấp quyền | DENY theo egress policy | Không bypass DNS policy |
| T-09 | Đích IPv6/đường VPN | ICMPv6 Packet Too Big liên quan | ALLOW theo chính sách | PMTUD/luồng lớn không bị black hole |

### 12.2. Các lệnh chẩn đoán minh họa

Chỉ chạy trên hệ thống và đích được phép kiểm thử; địa chỉ bên dưới dùng để minh họa. **Đừng sử dụng một kết quả timeout đơn lẻ để khẳng định firewall đã chặn**.

**Linux/macOS, từ máy nằm trong đúng zone kiểm thử:**

~~~bash
# Kiểm tra HTTPS từ vùng được phép
curl -I --connect-timeout 5 https://example.com

# Kiểm tra một TCP port cụ thể; thay bằng đích nội bộ được cấp quyền
nc -vz -w 3 10.20.30.15 5432

# Kiểm tra phân giải qua DNS resolver cho phép (nếu có dig)
dig @10.20.50.53 example.com

# Kiểm tra route cục bộ tới đích
ip route get 10.20.30.15
~~~

**Windows PowerShell:**

~~~powershell
Test-NetConnection -ComputerName 10.20.30.15 -Port 5432
Test-NetConnection -ComputerName 10.20.40.10 -Port 22
Resolve-DnsName example.com -Server 10.20.50.53
~~~

Để xác minh **deny**, cần kết hợp kết quả client với log rule và quan sát từ phía đích. TCP timeout có thể do thiếu route, firewall, mất gói hoặc host không trả lời; TCP connection refused thường chỉ ra có phản hồi từ đích hoặc thiết bị trung gian, nhưng vẫn cần xem gói/log để xác định.

Nếu có quyền vận hành, dùng **packet capture** ở hai phía của firewall để kiểm tra SYN, SYN-ACK, ICMP lỗi và đường đi NAT. Không kết luận một rule hoạt động chỉ từ lưu lượng thấy ở một phía.

### 12.3. Kiểm thử sau thay đổi

1. Ghi **baseline** cho kết nối quan trọng, log và rule hiện hành.
2. Thực hiện sửa rule trong cửa sổ thay đổi phù hợp và có **rollback** đã chuẩn bị.
3. Kiểm thử các case allow/deny cùng các dịch vụ phụ thuộc, bao gồm DNS, health check, VPN và traffic trả lời.
4. Kiểm tra IPv4/IPv6, các phiên **mới và đang tồn tại**, trạng thái NAT và routing nếu liên quan.
5. Xem log, hit counter, metric lỗi và xác nhận của owner ứng dụng.
6. Ghi lại bằng chứng, quyết định chấp nhận rủi ro còn lại và lịch rà soát.

Với quản trị từ xa, một rule sai có thể làm mất kết nối quản trị. Vì vậy cần kênh quản lý ngoài băng hoặc cơ chế tự rollback được chuẩn bị trước khi áp dụng chính sách trên hệ thống thật.

## 13. Quy trình quản lý vòng đời rule

Một bộ rule vận hành lâu năm thường có **rule cũ, duplicate, ngoại lệ tạm và tài khoản/dịch vụ không còn tồn tại**. Quản lý vòng đời quan trọng không kém bước tạo rule.

~~~mermaid
flowchart LR
    A[Yêu cầu truy cập] --> B[Xác minh nhu cầu, owner và rủi ro]
    B --> C[Thiết kế rule tối thiểu]
    C --> D[Review và phê duyệt]
    D --> E[Triển khai có kiểm soát]
    E --> F[Kiểm thử và giám sát]
    F --> G[Rà soát định kỳ / khi có thay đổi]
    G --> H{Rule còn cần?}
    H -- Có --> F
    H -- Không --> I[Thu hồi và xác minh]
~~~

Mỗi rule quan trọng nên có ít nhất:

| Trường quản trị | Nội dung |
|---|---|
| **ID / name** | Định danh duy nhất và dễ truy tìm |
| **Owner / requester** | Người yêu cầu và chủ dịch vụ chịu trách nhiệm |
| **Business reason** | Chức năng nào cần luồng này |
| **Source/destination/service** | Phạm vi chính xác và địa chỉ đối tượng |
| **Direction / zone / platform** | Điểm thực thi và cơ chế áp dụng |
| **Security justification** | Liên hệ phân đoạn, đánh giá rủi ro và kiểm soát thay thế |
| **Change reference** | Ticket, người duyệt, thời điểm triển khai |
| **Expiration / review date** | Hạn dùng ngoại lệ và ngày rà soát |
| **Validation evidence** | Test allow/deny, log, kết quả đánh giá sau triển khai |

**Infrastructure as Code / policy as code** giúp kiểm soát phiên bản, review và so cấu hình kỳ vọng với thực tế. Tuy nhiên việc cấu hình được lưu trong Git **không tự bảo đảm** đã deploy đúng hoặc không có thay đổi ngoài quy trình; vẫn cần phát hiện drift và kiểm tra trạng thái thực.

### Một mẫu yêu cầu mở rule

~~~yaml
# Ví dụ biểu mẫu, không phải file cấu hình của thiết bị
rule_id: FW-APP-DB-001
owner: application-team
change_id: CHG-EXAMPLE-001
source_zone: application
source_ip: 10.20.20.10/32
destination_zone: database
destination_ip: 10.20.30.15/32
protocol: tcp
destination_port: 5432
action: allow
direction: application-to-database
reason: "Dịch vụ ứng dụng truy vấn PostgreSQL"
review_on: "Khi thay đổi ứng dụng hoặc phân đoạn DB"
validation:
  allowed: "App -> DB TCP 5432"
  denied: "Guest/User -> DB TCP 5432"
~~~

Mẫu dùng **source IP cụ thể** thay vì toàn bộ subnet khi ổn định và thích hợp; nếu workload dùng địa chỉ động, lựa chọn object group, identity/tag hoặc cơ chế policy phù hợp hơn. Tránh tạo rule cho địa chỉ tạm mà không có quy trình cập nhật.

## 14. Phân tích sự cố thường gặp

### Tình huống A — Ứng dụng không kết nối được database sau khi siết ACL

**Quan sát:** ứng dụng trả lỗi kết nối DB, trong khi DB vẫn chạy. Một firewall mới chỉ cho phép TCP 5432 từ địa chỉ IP cũ của ứng dụng.

**Cách điều tra:** kiểm tra source IP **thực tế** sau NAT, subnet/zone mới, route, log deny, trạng thái TCP và đúng port DB. Với môi trường autoscaling, có thể cần group/tag hoặc egress proxy thay vì IP tĩnh. Chỉ mở đúng nguồn cần thiết sau khi xác minh; không giải quyết bằng allow toàn subnet vô điều kiện.

### Tình huống B — Cho phép HTTPS nhưng người dùng vẫn gặp lỗi

**Quan sát:** rule Internet → WAF TCP 443 được cho phép, nhưng trang chỉ hoạt động một phần.

**Giả thuyết:** WAF → app TCP 8443 hoặc app → DNS/DB bị chặn, health check fail, chứng chỉ TLS sai, WAF từ chối request hoặc back-end không hoạt động. Kiểm tra tuần tự **từng hop, từng layer**; rule 443 ở biên không chứng minh toàn chuỗi đã hoạt động.

### Tình huống C — Kết nối VPN được nhưng không vào mạng quản trị

**Quan sát:** người dùng đăng nhập VPN, có IP từ pool VPN nhưng SSH vào jump host timeout.

**Giả thuyết:** user thuộc nhóm VPN khác, route push/split tunnel sai, firewall chưa cho zone VPN-admin, đường về bất đối xứng, host firewall chặn hoặc SSH không lắng nghe. Kiểm tra identity mapping, route hai chiều và rule hiệu lực; **VPN connected không đồng nghĩa được cấp quyền tới mọi subnet**.

### Tình huống D — Gói nhỏ được nhưng truyền dữ liệu lớn qua tunnel bị treo

**Quan sát:** kết nối mở được, ping gói nhỏ thành công, ứng dụng tải file lớn timeout.

**Giả thuyết:** tunnel làm giảm Path MTU, firewall đã chặn ICMPv4 Fragmentation Needed hoặc ICMPv6 Packet Too Big nên nguồn không giảm kích thước phù hợp. Xác nhận bằng capture, PMTU, MTU tunnel và rule ICMP. Không khắc phục bằng cách mở mọi ICMP vô điều kiện.

### Tình huống E — Rule deny đặt rồi nhưng traffic vẫn đi được

**Quan sát:** người quản trị thêm deny tới subnet DB song kiểm thử vẫn thành công.

**Giả thuyết:** allow rộng đã khớp trước, security group kiểu allow-only không hỗ trợ deny như mong đợi, luồng đi qua firewall khác, phiên stateful cũ chưa hết hoặc rule áp dụng sai zone/hướng. So đường đi thực, thứ tự/priority, connection state và log của thiết bị đúng; không kết luận rule bị “phớt lờ” trước khi kiểm tra mô hình xử lý.

## 15. Checklist thiết kế và review firewall rule

- [ ] Biết **tài sản nào cần bảo vệ**, ai là owner và mục đích nghiệp vụ của luồng.
- [ ] Xác định đúng source, destination, IP/CIDR, zone/interface, direction, protocol, port hoặc ICMP type/code.
- [ ] Kiểm tra địa chỉ **trước/sau NAT**, route và điểm firewall thực sự quan sát gói.
- [ ] Biết nền tảng là stateful hay stateless; cách đánh giá thứ tự/priority và default policy.
- [ ] Cho phép cụ thể, áp dụng **default deny** phù hợp và tránh any-any.
- [ ] Rà soát shadowed, redundant, conflicting rule, các object group và exception.
- [ ] Kiểm tra đường truy cập quản trị, VPN, xác thực/MFA và quyền của thiết bị đầu cuối.
- [ ] Giữ các luồng vận hành cần thiết: DNS, DHCP, NTP, PMTUD, ICMPv6 NDP theo phạm vi.
- [ ] Xem cả IPv4/IPv6, lưu lượng đi/về và các phiên stateful hiện có.
- [ ] Có log/hit counter phù hợp; tránh spam log và lộ thông tin nhạy cảm.
- [ ] Kiểm thử **allow và deny**, xác nhận bằng log/capture từ đúng điểm.
- [ ] Gắn rule với owner, change ticket, lý do, hạn rà soát/thu hồi và bằng chứng xác minh.
- [ ] Chuẩn bị rollback, kênh quản lý khi mất kết nối và theo dõi sau triển khai.

## 16. Câu hỏi tự kiểm tra

**1. Firewall rule “allow TCP 443” có chứng minh ứng dụng HTTPS an toàn không?**  
Không. Rule chỉ quyết định cho phép kết nối theo điều kiện của firewall. Bảo mật ứng dụng còn cần xác thực, phân quyền, TLS, vá lỗi và giám sát.

**2. Vì sao một deny rule có thể không hoạt động trên firewall first-match?**  
Vì một allow rule rộng phía trước đã khớp traffic. Trên nền tảng khác, có thể vì deny không được hỗ trợ trong loại policy đó hoặc traffic không đi qua đúng điểm thực thi.

**3. Stateful firewall có cần mở riêng tất cả các ephemeral port chiều về?**  
Thường không, nếu phản hồi thuộc flow hợp lệ được engine nhận diện. Với ACL stateless phải thiết kế rule chiều về thích hợp; không thể áp dụng mặc định tư duy stateful.

**4. Tại sao rule NAT và rule firewall phải được đánh giá cùng nhau?**  
NAT có thể đổi IP/cổng mà rule nhìn thấy; thứ tự xử lý khác nhau theo thiết bị. Rule so địa chỉ không đúng giai đoạn có thể không khớp hoặc mở sai phạm vi.

**5. Vì sao không nên chặn mọi ICMP/ICMPv6?**  
Một số ICMP truyền lỗi cần cho vận hành, đặc biệt PMTUD; ICMPv6 còn có Neighbor Discovery. Chặn quá mức có thể làm hỏng IPv6 hoặc lưu lượng gói lớn.

**6. Một rule có hit counter bằng 0 đã đủ cơ sở xóa chưa?**  
Chưa. Có thể là rule dự phòng, dùng theo lịch hoặc khi failover. Cần owner, mục đích, cửa sổ quan sát, log, phụ thuộc và kiểm thử an toàn trước khi thu hồi.

## 17. Tài liệu tham khảo

- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): nguyên tắc thiết kế, vận hành và quản lý chính sách firewall.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): kiểm soát truy cập dựa trên danh tính, ngữ cảnh và quyền tối thiểu.
- [RFC 4443 — ICMPv6](https://www.rfc-editor.org/rfc/rfc4443): thông điệp điều khiển và báo lỗi IPv6.
- [RFC 4890 — Recommendations for Filtering ICMPv6 Messages in Firewalls](https://www.rfc-editor.org/rfc/rfc4890): lưu ý lọc ICMPv6 cho phép mạng hoạt động đúng.
- [RFC 8201 — Path MTU Discovery for IPv6](https://www.rfc-editor.org/rfc/rfc8201): vai trò thông điệp Packet Too Big.
- [AWS VPC Security Groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html): một ví dụ về security group có trạng thái và các rule allow.

**Ghi nhớ:** Firewall rule hữu ích khi **đúng luồng, đúng điểm thực thi, đúng phạm vi, đúng trạng thái và có bằng chứng kiểm thử**. Một bộ rule tốt phản ánh nhu cầu thực, giảm khả năng di chuyển ngang, giữ được các giao thức mạng thiết yếu và được rà soát khi hạ tầng thay đổi.
