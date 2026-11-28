# Rule theo source, destination và port trong Network Access Control

Khi một người dùng từ mạng khách cố truy cập cơ sở dữ liệu nội bộ, thiết bị kiểm soát mạng cần trả lời được câu hỏi: **ai đang gửi, gửi tới đâu, sử dụng giao thức và cổng nào, và luồng đó có được phép không?** Trong firewall và kiểm soát truy cập mạng (Network Access Control – NAC theo nghĩa rộng), một cách biểu diễn phổ biến là quy tắc dựa trên **source (nguồn), destination (đích), protocol và port**.

Đây là nền tảng của chương **Network access control** thuộc học phần **SECURITY_NETWORK_SECURITY**. Hiểu cách thiết kế và kiểm chứng rule giúp thực hiện phân đoạn mạng, cấu hình firewall/VPN, giám sát bằng IDS/IPS, giảm tiếp xúc DNS và dịch vụ nội bộ, đồng thời xây dựng chính sách an toàn trong mạng có dây, không dây và hạ tầng đám mây.

**Mục tiêu của bài:** sau khi học, bạn có thể phân tích một kết nối thành các trường cần so khớp, thiết kế bộ rule cấp quyền tối thiểu, giải thích việc cho phép lưu lượng phản hồi trong firewall stateful, nhận biết ảnh hưởng của NAT và thứ tự chính sách, kiểm chứng đường đi thực tế, và tránh những lỗi cấu hình khiến phân đoạn mạng mất tác dụng.

## 1. Rule kiểm soát truy cập mạng trả lời những câu hỏi nào?

Một **network access rule** mô tả điều kiện để thiết bị thực thi chính sách cho phép, từ chối hoặc ghi nhận lưu lượng đi qua một điểm kiểm soát. Một bản ghi có thể được diễn đạt:

> Chỉ cho phép các máy ứng dụng thuộc subnet 10.10.20.0/24 kết nối TCP tới máy cơ sở dữ liệu 10.10.30.15 trên cổng đích 5432. Những kết nối khác tới dịch vụ cơ sở dữ liệu phải bị từ chối theo chính sách.

Quy tắc minh họa:

| Thuộc tính | Giá trị | Ý nghĩa |
|---|---|---|
| Source | 10.10.20.0/24 | Máy nằm trong subnet ứng dụng |
| Destination | 10.10.30.15/32 | Một máy DB cụ thể |
| Protocol | TCP | Giao thức vận chuyển |
| Destination port | 5432 | Dịch vụ DB cần truy cập |
| Action | Allow | Cho phép lưu lượng khớp với rule |
| Direction | App → DB | Hướng của kết nối ban đầu |
| Log | Bật theo chính sách | Có bằng chứng kiểm tra và điều tra |
| Owner / purpose | Đội ứng dụng / truy cập DB | Giải thích vì sao quyền tồn tại |

Các địa chỉ **10.10.x.x** trong bài là ví dụ địa chỉ private RFC 1918; đây không phải cấu hình của hệ thống thật. Dải 10.10.20.0/24 chứa nhiều địa chỉ, trong khi /32 chỉ một địa chỉ IPv4. Việc cấp quyền từ cả subnet có thể cần thiết trong một số hệ thống nhiều instance, nhưng với một workload cố định, một nhóm identity hoặc tập IP nhỏ hơn có thể an toàn hơn.

**Rule không trực tiếp xác thực người dùng.** Rule IP/port xác định khả năng truyền thông trên đường mạng. Việc một gói được cho phép đi tới TCP/5432 **không đồng nghĩa** client đã có quyền đăng nhập PostgreSQL hay đọc dữ liệu; xác thực và ủy quyền của ứng dụng/DB vẫn phải được thực thi.

### 1.1. Phân biệt NAC, firewall và chính sách ở ứng dụng

- **NAC / 802.1X:** kiểm soát thiết bị hoặc danh tính nào được tham gia một mạng có dây/Wi-Fi; sau xác thực có thể gán VLAN, role hoặc ACL.
- **ACL mạng:** tập điều kiện match và action được thực thi trên switch, router, firewall, AP hoặc hệ thống ảo.
- **Firewall stateful:** quyết định cho phép/chặn theo chính sách và có thể theo dõi trạng thái phiên để xử lý lưu lượng phản hồi.
- **Ứng dụng / API gateway / service mesh:** có thể phân quyền theo danh tính người dùng, dịch vụ, phương thức HTTP, đường dẫn API hoặc claim; các điều kiện này không được suy ra chỉ từ IP/port.

Các tầng bảo vệ bổ sung nhau. Một máy được gán VLAN nhân viên bằng 802.1X có thể vẫn bị cấm kết nối trực tiếp tới DB theo firewall; DB tiếp tục kiểm tra danh tính ứng dụng.

## 2. Cấu trúc một luồng mạng và bộ 5 thành phần

Với TCP/UDP, một kết nối hoặc luồng thường được mô tả bằng **5-tuple**:

~~~text
(source IP, source port, destination IP, destination port, protocol)

Ví dụ request:
(10.10.20.42, 52144, 10.10.30.15, 5432, TCP)

Ví dụ gói phản hồi trước NAT:
(10.10.30.15, 5432, 10.10.20.42, 52144, TCP)
~~~

**Source IP** là địa chỉ phía gửi trong gói tại điểm quan sát; **destination IP** là địa chỉ đích trong gói tại điểm đó. **Source port** là cổng nguồn và **destination port** là cổng dịch vụ đích đối với kết nối client–server thông thường. **Protocol** phân biệt TCP với UDP; TCP/53 và UDP/53 là hai loại traffic khác nhau.

Trong một kết nối TCP:

1. Client chọn một source port, thường từ vùng port tạm (ephemeral) do hệ điều hành quản lý.
2. Client gửi SYN từ source IP/source port đến destination IP/destination port.
3. Server đáp lại bằng SYN-ACK theo hướng ngược lại.
4. Nếu việc thiết lập thành công và các thành phần đường đi cho phép, các gói tiếp theo thuộc cùng phiên được trao đổi.

~~~mermaid
sequenceDiagram
    participant A as App 10.10.20.42:52144
    participant F as Stateful firewall
    participant D as DB 10.10.30.15:5432
    A->>F: TCP SYN, đích 5432
    Note over F: Match rule App → DB: TCP/5432
    F->>D: SYN
    D-->>F: SYN-ACK, đích 52144
    Note over F: Phản hồi khớp phiên đã được cho phép
    F-->>A: SYN-ACK
    A->>F: ACK và dữ liệu theo phiên
    F->>D: Chuyển tiếp nếu phiên hợp lệ
~~~

**Không nên suy luận rằng rule cho phép TCP/5432 phải có source port 5432.** Kết nối đi ra thường dùng source port động, và gói phản hồi đi vào có destination port là source port động ấy. Nhầm lẫn hai cột port là một nguyên nhân phổ biến khiến rule thất bại.

### 2.1. Source port và destination port

Đối với traffic phát sinh từ client:

| Thao tác | Source port thường gặp | Destination port | Vì sao? |
|---|---|---|---|
| Client truy cập HTTPS | Port động, ví dụ 52144 | TCP/443 | Client kết nối dịch vụ web |
| App truy cập PostgreSQL | Port động, ví dụ 52145 | TCP/5432 | App kết nối máy DB |
| Máy trạm gửi truy vấn DNS | Port động, ví dụ 52146 | UDP/53 hoặc TCP/53 | Resolver nhận tại port 53 |
| Client truy cập SSH | Port động | TCP/22 | SSH server lắng nghe port 22 |

Đây là ví dụ thường gặp. Một ứng dụng có thể chọn source port cụ thể; NAT có thể thay đổi địa chỉ hoặc port; giao thức peer-to-peer hoặc traffic server-to-server có thể không khớp hoàn toàn với mô hình client đơn giản.

### 2.2. Không phải giao thức nào cũng có port

IPv4/IPv6 có các giá trị protocol/next header khác TCP và UDP. Chẳng hạn **ICMP và ICMPv6 không sử dụng source/destination port theo kiểu TCP/UDP**, mà có các trường type/code. Với ICMPv6, chặn tùy tiện có thể phá Neighbor Discovery hoặc Path MTU Discovery.

Vì thế khi thiết kế rule phải phân biệt:

- TCP/UDP: có thể match **port hoặc dải port**.
- ICMP/ICMPv6: thường match theo **protocol và type/code** phù hợp.
- Giao thức khác: khả năng match phụ thuộc nền tảng và cấu hình, không nên mặc định tất cả rule đều có destination port.

## 3. Những trường có thể tham gia quyết định

Bộ ba source, destination, port là lõi của bài, nhưng các firewall thực tế thường có thêm điều kiện.

| Thuộc tính | Ví dụ | Tác dụng | Rủi ro khi hiểu sai |
|---|---|---|---|
| Source CIDR | 10.10.20.0/24 | Xác định dải nguồn | Cấp cả subnet quá rộng |
| Destination IP/CIDR | 10.10.30.15/32 | Giới hạn tài sản nhận | Trỏ nhầm VIP/NAT IP hay IP máy thật |
| L4 protocol | TCP, UDP | Phân biệt loại kết nối | Cho phép TCP nhưng quên UDP; hoặc ngược lại |
| Destination port/range | 443, 5432, 8000–8010 | Hạn chế dịch vụ | Dải port rộng hơn nhu cầu |
| Source port/range | Port động hoặc cụ thể | Điều kiện bổ sung trong một số trường hợp | Nhầm source port với destination port |
| Direction | Inbound, outbound, ingress, egress | Hướng vào/ra giao diện hoặc đối tượng | Hiểu “inbound” theo người dùng thay vì theo thiết bị thực thi |
| Interface / zone | WAN, LAN, Guest, App | Chọn vị trí/quy tắc áp dụng | Rule đặt sai interface hoặc zone |
| Connection state | NEW, ESTABLISHED, RELATED, INVALID | Quyết định dựa trên trạng thái theo nền tảng | Coi traffic không thuộc phiên là phản hồi hợp lệ |
| Identity / group | Người dùng VPN, workload identity | Gắn quyết định với danh tính khi sản phẩm hỗ trợ | Dùng IP như danh tính cố định trong môi trường NAT/DHCP |
| Application | HTTP, DNS, SSH | Có thể nhận diện L7 ở một số thiết bị | Tin cậy tuyệt đối vào port để nhận diện ứng dụng |
| Schedule / tags | Chỉ trong giờ bảo trì | Giới hạn quyền theo thời gian/ngữ cảnh | Quyền mở rộng bị quên sau bảo trì |

**Lưu ý về hướng:** “Inbound” trên VM là lưu lượng **đi vào VM**; “ingress” trên network policy Kubernetes là lưu lượng **đi vào pod đích**; “inbound” trên firewall ở cổng WAN có thể được hiểu theo hướng **đi vào một interface**. Hãy đọc định nghĩa của chính nền tảng thay vì áp dụng một quy ước duy nhất.

### 3.1. CIDR và độ rộng quyền

Một số lựa chọn thường gặp:

- **10.10.30.15/32:** một địa chỉ IPv4.
- **10.10.30.0/24:** toàn bộ mạng 10.10.30.x, lớn hơn rất nhiều.
- **10.0.0.0/8:** toàn bộ dải private 10.x.x.x; chỉ phù hợp nếu có lý do nghiệp vụ rõ ràng.
- **0.0.0.0/0:** tất cả địa chỉ IPv4 theo phép match; thường quá rộng với cổng quản trị và DB.
- **::/0:** tất cả địa chỉ IPv6; chính sách IPv4 không tự kiểm soát traffic IPv6.

Cần xác định **IP nguồn thực sự đến firewall**. Nếu máy đi qua NAT, proxy hoặc gateway, thiết bị thực thi có thể thấy source IP đã bị đổi; khi đó rule theo IP ban đầu có thể không match.

## 4. Rule matching: luồng được xử lý như thế nào?

Một firewall hoặc ACL có thể đánh giá các thuộc tính của gói/phiên, xác định rule phù hợp và thực thi action như **allow**, **deny/drop**, **reject**, **log** hoặc các hành động đặc thù.

Ví dụ khái niệm:

~~~text
Traffic đến điểm kiểm soát
        |
        v
Kiểm tra zone/interface + trạng thái phiên
        |
        v
So khớp source IP, destination IP, protocol, port
        |
        v
Chọn rule theo cơ chế ưu tiên của nền tảng
        |
        +--> ALLOW: cho qua, có thể tạo state/log
        |
        +--> DENY / DROP: bỏ gói
        |
        +--> REJECT: từ chối và có thể gửi phản hồi lỗi
        |
        +--> Không khớp: áp chính sách mặc định của nền tảng
~~~

Không phải mọi hệ thống xử lý rule giống nhau:

- **ACL tuần tự / ordered firewall:** nhiều hệ thống duyệt từ trên xuống và áp dụng **first match**; rule sớm có thể che rule đặt sau.
- **Động cơ chính sách theo ưu tiên:** có thể chọn theo số priority, rule group, layer hoặc loại đối tượng.
- **Security group ở một số cloud:** chủ yếu là tập rule cho phép, thường không có deny rule trực tiếp trong cùng nhóm; đánh giá theo hợp của các allow rule, tùy nhà cung cấp.
- **Network ACL cloud:** có thể có allow và deny, thứ tự theo rule number, thường có đặc tính stateless tùy nền tảng.
- **Kubernetes NetworkPolicy:** các policy cùng chọn một pod có ngữ nghĩa cộng gộp quyền được phép theo hướng ingress/egress; không nên áp tư duy ordered first-match của firewall truyền thống.

**Phải xác minh tài liệu và cấu hình của nền tảng đang dùng.** Không có một câu “rule đầu tiên luôn thắng” đúng cho mọi firewall, cloud, service mesh và network policy.

### 4.1. Default allow và default deny

Khi không có rule cụ thể, hệ thống có thể có:

- **Implicit/default deny:** traffic không được cho phép rõ ràng sẽ bị từ chối; thường là mục tiêu của phân đoạn nhạy cảm.
- **Default allow:** traffic được cho phép trừ khi có rule chặn; phù hợp với một số môi trường nhưng tạo nguy cơ mở ngoài ý muốn nếu không quản lý tốt.

Ví dụ ở môi trường DB, mô hình **default deny + allow cụ thể** thường dễ bảo vệ hơn:

~~~text
ALLOW 10.10.20.0/24  → 10.10.30.15/32  TCP/5432
DENY  Any            → 10.10.30.15/32  TCP/5432
~~~

Các dòng trên là **pseudo-rule**, không phải cú pháp dùng trực tiếp cho một sản phẩm. Khi triển khai còn phải xét trạng thái phiên, NAT, IPv6, các rule khác và điểm thực thi.

### 4.2. Rule shadowing và trùng lặp

Một rule có thể **bị che** nếu rule ưu tiên cao hơn đã match tập traffic đó:

~~~text
01 DENY  ANY               → DB         TCP/5432
02 ALLOW APP_SUBNET        → DB         TCP/5432
~~~

Nếu firewall sử dụng first match, dòng 02 có thể không bao giờ có hiệu lực. Ngược lại:

~~~text
01 ALLOW ANY               → DB         TCP/5432
02 DENY  GUEST_SUBNET      → DB         TCP/5432
~~~

Dòng 01 có thể làm mất tác dụng dòng 02. Ngoài ra còn có vấn đề **overlap**, rule không dùng, đối tượng IP cũ, rule ngoại lệ tồn tại quá lâu và rule không có owner. Cần kiểm tra cả độ ưu tiên, phạm vi match và sự kiện thực thi thực tế.

## 5. Stateful và stateless: điều gì xảy ra với lưu lượng phản hồi?

Đây là điểm dễ sai nhất khi thiết kế rule theo source, destination và port.

### 5.1. Firewall stateful

Một firewall **stateful** theo dõi trạng thái kết nối hoặc luồng. Khi kết nối **App → DB TCP/5432** được cho phép, firewall có thể ghi nhận phiên và cho gói phản hồi **DB → App** tương ứng đi qua mà không cần rule mới cho từng port động.

~~~text
Rule cho phép kết nối mới:
APP 10.10.20.42:any  ---> DB 10.10.30.15:5432 TCP

Phản hồi thuộc phiên:
DB 10.10.30.15:5432  ---> APP 10.10.20.42:52144 TCP

Stateful firewall: nhận diện đây là gói phản hồi của kết nối được cho phép.
~~~

Nhiều nền tảng dùng khái niệm tương tự **NEW**, **ESTABLISHED**, **RELATED**, **INVALID**, nhưng chi tiết và hỗ trợ phụ thuộc hệ thống. Một trạng thái ESTABLISHED không thay thế việc kiểm tra đường đi, NAT và chính sách ban đầu.

### 5.2. ACL stateless

Một ACL **stateless** đánh giá từng gói độc lập. Nếu muốn cho phép TCP App → DB và lưu lượng phản hồi, có thể phải tạo rule cho **cả chiều đi và chiều về**, bao gồm port động của client hoặc các trường trạng thái/flag được phần cứng hỗ trợ.

~~~text
Chiều đi:
APP_SUBNET : ephemeral  ---> DB_IP : TCP/5432

Chiều về:
DB_IP : TCP/5432        ---> APP_SUBNET : ephemeral
~~~

Vì dải ephemeral thay đổi giữa hệ điều hành và cấu hình, phải biết phạm vi cổng thực tế hoặc cơ chế của sản phẩm trước khi dựng ACL phản hồi. **Không mở toàn bộ cổng đến DB chỉ để “cho gói phản hồi”.**

### 5.3. UDP và ICMP

UDP không có bắt tay ba bước như TCP. Một firewall stateful có thể tạo trạng thái luồng UDP dựa trên gói đi ra và thời gian chờ, rồi nhận biết gói phản hồi dự kiến. Dù vậy timeout và cách theo dõi UDP khác nhau theo sản phẩm.

ICMP thường được xử lý theo type/code và liên hệ với luồng (ví dụ một số ICMP lỗi báo về kết nối đang tồn tại), không thể mặc định “cho port phản hồi” vì ICMP không có khái niệm port đích.

**Ví dụ DNS:** client thường gửi truy vấn UDP/53 đến resolver và có thể chuyển sang TCP/53 khi cần. Rule bảo vệ DNS phải xem cả **UDP và TCP 53** nếu mô hình dịch vụ yêu cầu. Các dạng DNS over TLS hoặc DNS over HTTPS dùng luồng cổng/giao thức khác; chỉ lọc port 53 không tự bảo đảm mọi truy vấn DNS đi qua resolver được quản lý.

## 6. Đặt rule ở đâu mới có hiệu lực?

Một rule chỉ kiểm soát được lưu lượng **thực sự đi qua vị trí thực thi**.

~~~mermaid
flowchart LR
    I[Internet] --> E[Firewall biên]
    E --> W[Public web / reverse proxy]
    G[Guest VLAN 50] --> F[Firewall liên vùng]
    S[Staff VLAN 10] --> F
    A[App VLAN 20] --> F
    F --> D[DB VLAN 30]
    V[VPN users] --> VF[VPN policy]
    VF --> F
    C[Cloud subnet / workload] --> CF[Cloud network policy]
    CF --> D
~~~

Sơ đồ minh họa **các điểm áp chính sách**, không khẳng định mọi đường đi trong hệ thống thật đều được phép. Khi triển khai phải kiểm chứng topology, route, route bất đối xứng và các đường kết nối phụ.

### 6.1. Firewall liên VLAN / giữa các zone

Nếu App và DB nằm ở các VLAN và subnet khác nhau, traffic thường cần L3 routing. Đặt firewall/ACL tại thiết bị thực sự thực hiện định tuyến liên VLAN sẽ kiểm soát được lưu lượng này.

**Cảnh báo:** nếu hai máy cùng VLAN và kết nối trực tiếp L2 mà không đi qua firewall liên VLAN, rule trên firewall đó không kiểm soát lưu lượng giữa chúng. Cần host firewall, distributed firewall/microsegmentation hoặc mô hình tách mạng phù hợp.

### 6.2. VPN và quyền sau khi kết nối

VPN tạo đường vào mạng nhưng không có nghĩa mọi người dùng VPN được phép truy cập mọi dịch vụ. Ví dụ:

- User VPN thường: được vào ứng dụng web nội bộ TCP/443.
- Nhóm quản trị: được vào jump host TCP/22 theo danh tính, posture và chính sách.
- Không nhóm nào được kết nối trực tiếp DB TCP/5432 trừ các workload có nhiệm vụ rõ ràng.

Cần biết firewall thấy **địa chỉ trước hay sau khi VPN giải mã/NAT**, và danh tính/nhóm VPN có được truyền đến policy engine không. Lọc theo cả dải VPN nhưng không xét vai trò có thể cấp quá nhiều quyền.

### 6.3. Cloud và Kubernetes

Trong cloud, các điểm thường gặp gồm **security group**, **network ACL**, firewall quản lý, host firewall, policy ở hypervisor và load balancer. Khác biệt stateful/stateless, tính ưu tiên và hướng áp dụng phụ thuộc nhà cung cấp. Một public endpoint được phép ở security group nhưng không có route/Internet gateway phù hợp vẫn có thể không reachable.

Trong Kubernetes, **NetworkPolicy** có thể kiểm soát ingress/egress theo pod selector, namespace selector, ipBlock và port, nếu plugin mạng thực thi chức năng đó. Không được mặc định mọi cluster hỗ trợ NetworkPolicy hoặc mọi đường host-network, node traffic hay egress ra ngoài đều có cùng hành vi.

## 7. Thiết kế rule mẫu cho một hệ thống có phân đoạn

Giả sử doanh nghiệp có các vùng:

| Vùng | Subnet / endpoint minh họa | Vai trò |
|---|---|---|
| **Staff** | 10.10.10.0/24 | Máy nhân viên |
| **App** | 10.10.20.0/24 | Dịch vụ ứng dụng |
| **DB** | 10.10.30.15/32 | Cơ sở dữ liệu |
| **Guest** | 10.10.50.0/24 | Khách/thiết bị chưa quản trị |
| **Management** | 10.10.99.0/24 | Máy quản trị, jump host |
| **VPN Admin** | 10.10.90.0/24 | Dải cấp cho phiên VPN quản trị |
| **Internal DNS** | 10.10.1.53/32 | Resolver nội bộ |
| **Public HTTPS endpoint** | 203.0.113.10/32 | IP tài liệu dùng minh họa; không phải endpoint thật |

Dải 203.0.113.0/24 là mạng **TEST-NET-3** dành cho tài liệu. Nếu vẽ Internet ↔ endpoint này, đó là mô hình để phân tích rule chứ không phải địa chỉ để kiểm tra trên Internet công cộng.

### 7.1. Xác định luồng nghiệp vụ trước khi viết rule

Giả định nghiệp vụ:

1. Người ngoài Internet có thể truy cập HTTPS public qua reverse proxy.
2. Nhân viên được dùng ứng dụng web nội bộ TCP/443.
3. Ứng dụng gọi DB PostgreSQL TCP/5432.
4. Host nội bộ sử dụng DNS resolver được quản lý.
5. Quản trị viên có VPN và quyền tương ứng mới đến jump host SSH.
6. Guest không được đến App, DB hoặc Management trực tiếp.

Một policy ví dụ:

| ID | Source | Destination | Protocol / dst port | Action | Giải thích |
|---|---|---|---|---|---|
| WEB-01 | Internet theo policy | Public HTTPS 203.0.113.10 | TCP/443 | ALLOW | Dịch vụ public qua điểm kết thúc HTTPS |
| APP-01 | Staff 10.10.10.0/24 | App frontend (đích được định danh riêng) | TCP/443 | ALLOW | Nhân viên truy cập ứng dụng |
| DB-01 | App 10.10.20.0/24 | DB 10.10.30.15 | TCP/5432 | ALLOW | Chỉ ứng dụng được kết nối DB |
| DNS-01 | Các client/subnet đã được cấp quyền | Resolver 10.10.1.53 | UDP/53, TCP/53 | ALLOW | Phân giải DNS theo thiết kế |
| ADM-01 | VPN Admin 10.10.90.0/24 | Jump host trong Management | TCP/22 | ALLOW | Vận hành qua VPN |
| GUEST-01 | Guest 10.10.50.0/24 | App/DB/Management | Any | DENY | Tách vùng khách khỏi vùng nhạy cảm |
| DB-DEFAULT | Any khác | DB 10.10.30.15 | TCP/5432 | DENY | Không mở DB cho nguồn ngoài danh sách |
| DEFAULT | Any | Any | Theo policy | DENY | Quyền tối thiểu cho luồng mới |

**Đây là bảng thiết kế khái niệm, không phải danh sách rule có thể chép nguyên vào mọi firewall.** Cần thay “App frontend”, “Jump host”, “Internet” bằng đối tượng/IP cụ thể; định nghĩa DNS client, egress nghiệp vụ và thứ tự ưu tiên trên từng thiết bị. Rule Guest deny có thể không cần riêng nếu default deny đã đủ; có thể đặt để ghi log/diễn đạt yêu cầu, tùy khả năng nền tảng.

### 7.2. Flow App → DB

Giả sử App tại **10.10.20.42** gửi kết nối:

~~~text
Source:       10.10.20.42
Source port:  52844
Destination:  10.10.30.15
Dest. port:   5432
Protocol:     TCP

Rule DB-01: source thuộc 10.10.20.0/24?  Có
             dest là 10.10.30.15?       Có
             TCP?                        Có
             destination port = 5432?    Có
             => ALLOW nếu không có rule ưu tiên hơn ngăn chặn
~~~

Ở chiều ngược lại, nếu firewall stateful tạo phiên, phản hồi TCP/5432 → 52844 có thể được cho qua theo state. Nếu có thiết bị stateless khác trên đường phản hồi, vẫn cần kiểm tra rule chiều về tại thiết bị đó.

### 7.3. Flow Guest → DB

Guest **10.10.50.27** cố kết nối TCP/5432 tới DB:

~~~text
Source: 10.10.50.27  ->  Destination: 10.10.30.15:5432 TCP

DB-01: source không thuộc App subnet => không khớp
GUEST-01 / DB-DEFAULT: khớp deny theo chính sách
Kết quả mong đợi: không thiết lập được kết nối
~~~

Một kết quả từ client như **timeout**, **connection refused** hay log drop có thể khác nhau tùy firewall gửi reject hay drop, route và điểm quan sát. Mục tiêu an ninh là **không có phiên ứng dụng được phép**, không bắt buộc mọi client nhận cùng thông báo lỗi.

### 7.4. Flow Staff → App và App → DB là hai quyền độc lập

Cho Staff truy cập frontend TCP/443 **không tự** cho Staff truy cập DB TCP/5432. Nếu ứng dụng cần gọi DB, quyền đó thuộc luồng App → DB. Đây chính là cách tách các **trust boundary**: user → application và application → data.

Tuy nhiên nếu App bị xâm nhập, đối thủ có thể dùng kết nối DB vốn được cho phép. Do đó ngoài firewall phải áp **xác thực dịch vụ, quyền DB tối thiểu, bảo vệ secret, mã hóa và giám sát truy cập dữ liệu**.

## 8. Thứ tự áp dụng rule và các ngoại lệ thực tế

### 8.1. Ingress / egress không phải chỉ có một chiều

- **Ingress** thường nói về traffic đi vào tài nguyên, interface hoặc zone được quản lý.
- **Egress** thường nói về traffic đi ra tài nguyên, interface hoặc zone đó.
- Với luồng App → DB, cùng một traffic có thể là **egress của App** và **ingress của DB**.
- Một số hạ tầng yêu cầu cả egress policy phía nguồn và ingress policy phía đích cùng cho phép, cộng với route và các kiểm soát ở giữa.

Không nên chỉ kiểm tra một rule **allow** và kết luận kết nối sẽ thành công. Một rule deny khác, thiếu route, ACL stateless chiều về hoặc xác thực ứng dụng thất bại đều có thể làm kết nối không hoạt động.

### 8.2. NAT làm đổi địa chỉ hoặc port tại điểm quan sát

**NAT (Network Address Translation)** có thể đổi source IP, destination IP, source port hoặc destination port. Một ví dụ destination NAT:

~~~text
Client Internet --> 203.0.113.10:443 (public VIP)
                 DNAT -> 10.10.20.10:8443 (backend)

Source và destination mà firewall thấy:
  - Trước DNAT: destination = 203.0.113.10:443
  - Sau DNAT:   destination = 10.10.20.10:8443
~~~

Nền tảng có thể match firewall rule theo thông tin trước NAT, sau NAT hoặc tổ hợp đặc biệt; **thứ tự NAT và filter tùy sản phẩm, chain và đường xử lý**. Vì vậy phải xác minh đúng tài liệu của thiết bị, counter, log và packet trace. Không chuyển rule từ sản phẩm này sang sản phẩm khác chỉ bằng cách chép địa chỉ public/private.

**SNAT** tương tự có thể khiến DB thấy IP của gateway/proxy thay vì địa chỉ nguồn gốc. Nếu nhiều client dùng cùng IP NAT, rule chỉ theo source IP không thể tự phân biệt người dùng. Cần lớp danh tính phù hợp.

### 8.3. Dynamic IP và FQDN objects

Trong các môi trường auto-scaling, DHCP, container, serverless hoặc CDN, IP nguồn/đích có thể thay đổi. Một số firewall hỗ trợ nhóm địa chỉ, tag, workload identity hoặc object theo FQDN, nhưng cách cập nhật DNS, TTL và thực thi policy khác nhau.

Nếu chính sách cần bảo vệ **một dịch vụ**, hãy chọn đối tượng theo role/workload/identity khi hạ tầng có thể thực thi tin cậy; nếu vẫn dùng IP, cần quy trình cập nhật địa chỉ và kiểm chứng sau triển khai. **FQDN rule không mặc nhiên tương đương kiểm tra danh tính ứng dụng qua TLS.**

### 8.4. IPv6 cần rule riêng phù hợp

Chỉ đặt IPv4 source/destination **0.0.0.0/0** hoặc 10.10.x.x không chặn mọi đường IPv6. Với máy dual-stack, cần quản lý IPv6 CIDR, route và firewall phù hợp. **::/0** bao phủ IPv6, không phải IPv4.

Ngoài TCP/UDP, các thông báo **ICMPv6 thiết yếu** hỗ trợ hoạt động của mạng. Chính sách deny-all quá rộng có thể làm hỏng Neighbor Discovery hoặc Path MTU. Cần tham chiếu vai trò từng loại ICMPv6 và chính sách nền tảng khi viết rule.

## 9. Một mẫu đặc tả rule dễ review

Trước khi chuyển chính sách sang câu lệnh riêng của sản phẩm, hãy mô tả bằng một định dạng **không phụ thuộc vendor**:

~~~yaml
policy_id: "DB-01"
description: "Ứng dụng được phép kết nối PostgreSQL"
owner: "team-application"
source:
  cidr: "10.10.20.0/24"
destination:
  cidr: "10.10.30.15/32"
protocol: "tcp"
destination_ports:
  - 5432
direction: "app-to-db"
connection_tracking: "stateful-if-supported"
action: "allow"
logging: "enabled-per-operations-policy"
expiry: null
justification: "Luồng nghiệp vụ App -> PostgreSQL"
verification:
  allowed_source: "10.10.20.42"
  denied_source: "10.10.50.27"
  target: "10.10.30.15:5432"
~~~

Đây là **YAML mô tả chính sách**, không phải cấu hình hợp lệ của nftables, iptables, firewalld, Windows Firewall hay một cloud provider. Để áp dụng cần ánh xạ sang mô hình policy, thứ tự, cú pháp, trạng thái và vị trí thực thi của nền tảng.

### 9.1. Ghi nguyên nhân và vòng đời của quyền

Một rule tốt cần có:

1. **ID và owner:** người/nhóm chịu trách nhiệm nghiệp vụ và kỹ thuật.
2. **Lý do:** luồng dữ liệu nào cần thiết; vì sao chọn port và phạm vi nguồn/đích.
3. **Thời hạn:** quyền vĩnh viễn theo nghiệp vụ hay ngoại lệ bảo trì có ngày hết hạn.
4. **Mức ưu tiên và điểm áp dụng:** rule nằm tại thiết bị/zone/policy nào.
5. **Kế hoạch kiểm chứng:** case được phép, case bị từ chối và cách quan sát.
6. **Log và review:** trường log nào, tần suất xem xét quyền thừa.
7. **Rollback:** cách phục hồi nếu thay đổi chặn luồng hợp lệ.

Rule không có owner và thời hạn xem xét dễ trở thành ngoại lệ tồn tại lâu sau khi hệ thống đã thay đổi.

## 10. Chuyển yêu cầu thành bộ quy tắc có thể kiểm tra

Một trình tự thiết kế hiệu quả:

### Bước 1 — Liệt kê tài sản và quan hệ dữ liệu

Xác định **workload nào khởi tạo kết nối**, **workload nào lắng nghe** và **dịch vụ cần port nào**. Ghi rõ DNS, proxy, service discovery, database, giám sát, backup và các luồng quản trị cần thiết.

Đừng vội viết **Any → Any Allow** để làm hệ thống chạy, vì nó che những phụ thuộc chưa được hiểu rõ.

### Bước 2 — Xác minh đường đi thực tế

Vẽ route, VLAN, VPN, firewall, NAT, load balancer, mesh, cloud policy và host firewall. Xác định các điểm lưu lượng bắt buộc đi qua. Kiểm tra cả chiều đi và chiều về, các đường qua IPv6 và những kết nối giữa hai host cùng VLAN.

### Bước 3 — Tách luồng theo mục đích

Nếu cùng một nguồn cần HTTPS và DNS, tốt hơn nên có các rule mô tả riêng để giải thích và kiểm toán:

~~~text
ALLOW APP_SUBNET -> INTERNAL_API   TCP/443  # Ứng dụng gọi API
ALLOW APP_SUBNET -> DNS_RESOLVER   UDP/53   # DNS thông thường
ALLOW APP_SUBNET -> DNS_RESOLVER   TCP/53   # DNS qua TCP khi cần
DENY  APP_SUBNET -> DB_OTHER       TCP/5432 # Không dùng DB khác
~~~

Các dòng chỉ minh họa. Độ rộng source/destination có thể được thu hẹp thêm bằng một tập IP, object group hoặc danh tính service phù hợp.

### Bước 4 — Chọn trạng thái và cơ chế ưu tiên

Kiểm tra firewall **stateful hay stateless**, lựa chọn default action, thứ tự rule, object match và cách xử lý return traffic. Với đường có nhiều thiết bị, một firewall stateful không tự giải quyết các ACL stateless khác.

### Bước 5 — Kiểm tra trước khi triển khai

Review ít nhất hai chiều:

- **Positive:** nguồn hợp lệ có đến đúng dịch vụ không?
- **Negative:** nguồn không hợp lệ hoặc port khác có bị từ chối không?

Thêm các tình huống thay đổi như IP workload mới, DNS chuyển backend, VPN role thay đổi, IPv6 mới xuất hiện và rule cũ có thể che rule mới.

### Bước 6 — Triển khai có kiểm soát và đọc log

Áp dụng trong phạm vi được phê duyệt, có người chịu trách nhiệm, thời gian theo dõi và rollback. Khi thay đổi policy quan trọng, theo dõi counter/log của rule allow/deny, lỗi ứng dụng và latency; không chỉ dựa vào lời báo “đã ping được”.

### Bước 7 — Xác minh trạng thái sau thay đổi

Từ nguồn có quyền và nguồn không có quyền, kiểm chứng **đúng protocol/destination port** theo phạm vi đã được phép. Đối chiếu kết quả client với log firewall, log host và trạng thái ứng dụng.

## 11. Bộ kiểm thử mẫu: chứng minh cả được phép và bị chặn

Giả sử đã triển khai policy ở mục 7. Với các máy thử nghiệm hợp lệ thuộc các subnet đã nêu, bảng này cung cấp tiêu chí:

| Test | Source | Destination | Protocol/port | Kỳ vọng | Nếu khác dự kiến, kiểm tra |
|---|---|---|---|---|---|
| T1 | App 10.10.20.42 | DB 10.10.30.15 | TCP/5432 | Cho qua kết nối mạng | DB listener, route, firewall, NAT, auth |
| T2 | Guest 10.10.50.27 | DB 10.10.30.15 | TCP/5432 | Từ chối | Rule guest, đường đi khác, ACL/switch |
| T3 | Staff 10.10.10.25 | DB 10.10.30.15 | TCP/5432 | Từ chối nếu không có ngoại lệ | Rule rộng hơn hoặc bị shadow |
| T4 | VPN Admin 10.10.90.10 | Jump host | TCP/22 | Cho qua đúng role | VPN ACL, route, host firewall, SSH |
| T5 | Guest 10.10.50.27 | Jump host | TCP/22 | Từ chối | Policy liên vùng, mạng Wi-Fi khách |
| T6 | App 10.10.20.42 | DNS 10.10.1.53 | UDP/53 và TCP/53 | Cho phép khi thuộc luồng nghiệp vụ | DNS server ACL, UDP timeout, TCP fallback |
| T7 | nguồn không cấp quyền | App API nội bộ | TCP/443 | Từ chối | Lớp ingress, reverse proxy, đường thay thế |

Chỉ dùng bảng với **máy thử nghiệm được sở hữu hoặc được phép kiểm tra**; với môi trường có dữ liệu thật, cần phối hợp vận hành. Một test cổng TCP thành công chứng minh khả năng thiết lập kết nối tại thời điểm quan sát, **không tự xác nhận auth ứng dụng**. Để thử quyền ứng dụng cần bài kiểm tra riêng.

### 11.1. Các lệnh quan sát cục bộ

Trên Linux, quản trị viên có thể **đọc trạng thái** mà không thay đổi rule:

~~~bash
# Xem tiến trình nào đang lắng nghe cổng TCP/UDP
ss -lntup

# Xem route dự kiến đến một đích private
ip route get 10.10.30.15

# Xem bộ rule nftables (cần quyền phù hợp tùy hệ thống)
sudo nft list ruleset

# Hệ thống dùng iptables có thể xem danh sách lọc
sudo iptables -S
~~~

Các lệnh trên là ví dụ cho môi trường Linux phù hợp. Thiết bị có thể không dùng nftables/iptables; rule thực tế còn có thể nằm ở switch, firewall riêng, host Windows hoặc cloud, ngoài phạm vi các lệnh này. **Không thay đổi rule trong khi chẩn đoán nếu chưa có kế hoạch vận hành.**

Trên Windows PowerShell có thể đọc thông tin firewall và tiến trình lắng nghe:

~~~powershell
# Liệt kê một phần rule Windows Firewall
Get-NetFirewallRule | Select-Object -First 20 DisplayName, Direction, Action, Enabled

# Kiểm tra các TCP listener cục bộ
Get-NetTCPConnection -State Listen |
  Select-Object LocalAddress, LocalPort, OwningProcess

# Xem kết nối TCP đến đích trong lab được cho phép
Test-NetConnection -ComputerName 10.10.30.15 -Port 5432
~~~

Lệnh **Test-NetConnection** tạo thử kết nối TCP; chỉ chạy tới mục tiêu được phép kiểm thử. Trong lab Linux, có thể dùng công cụ TCP client phù hợp, ví dụ **nc** nếu hệ thống có hỗ trợ, nhưng cần hiểu kết quả và giới hạn timeout.

### 11.2. Những trạng thái phải phân biệt khi kiểm chứng

| Hiện tượng | Giải thích có thể | Bằng chứng bổ sung nên xem |
|---|---|---|
| TCP kết nối được, ứng dụng từ chối đăng nhập | Luồng mạng đã đến dịch vụ nhưng auth/ủy quyền ứng dụng không cho phép | Log ứng dụng, chứng chỉ, tài khoản DB |
| TCP timeout | Packet bị drop, mất route, dịch vụ/thiết bị không trả lời, mất gói | Firewall deny log, packet capture, route, listener |
| Connection refused | Đích hoặc thiết bị trung gian có thể gửi RST | Listener, host firewall, NAT, địa chỉ đích |
| Rule allow có counter bằng 0 | Lưu lượng không đi qua rule, match sai, chưa phát sinh, hoặc counter không đáng tin theo nền tảng | Source IP thực, NAT, ưu tiên rule, route |
| Rule deny tăng counter dù nguồn hợp lệ | Có thể rule ưu tiên/chính sách khác đang chặn | Policy order, zone, state, source object |
| Một chiều thấy SYN, chiều về không thấy | Phản hồi có thể bị chặn hoặc đi đường khác | ACL stateless, asymmetric routing, return route |
| Kết nối được trên IPv4 nhưng không trên IPv6 | Listener/route/rule hai họ địa chỉ khác nhau | Socket binding, IPv6 firewall, DNS A/AAAA |

Không kết luận “firewall chặn” chỉ từ timeout. Cần quan sát tại những điểm phù hợp và phân biệt **không có route**, **lỗi L1/L2**, **lọc L3/L4** và **lỗi ở tầng ứng dụng**.

## 12. Những lỗi cấu hình thường gặp

### 12.1. Source quá rộng

Ví dụ **Any → DB TCP/5432 Allow** giúp nhiều máy kết nối được nhưng làm mất ranh giới phân đoạn. Nếu chỉ App cần DB, source nên giới hạn theo App subnet hoặc một nhóm workload chính xác hơn.

### 12.2. Destination quá rộng

**App → 10.10.30.0/24 TCP/5432 Allow** mở mọi host trên subnet DB tới port đó, dù ứng dụng chỉ dùng **10.10.30.15**. Dùng /32 hoặc identity/service group cụ thể khi có thể.

### 12.3. Protocol hoặc port không đúng

**Allow TCP/53** có thể làm truy vấn DNS thông thường qua UDP/53 thất bại. Ngược lại, **Any protocol** chỉ để mở một dịch vụ TCP đơn lẻ là quá rộng.

### 12.4. Nhầm source port với destination port

Một rule chỉ cho source port 443 của client sẽ chặn phần lớn kết nối HTTPS bình thường, vì browser thường chọn source port động. Khi giải thích rule hãy ghi rõ cột port nguồn và đích.

### 12.5. Quên lưu lượng phản hồi ở ACL stateless

Cho phép App → DB TCP/5432 nhưng chặn DB → App tới port tạm có thể làm phiên thất bại. Xem loại thiết bị và hướng áp rule để quyết định cấu hình chiều về.

### 12.6. Rule bị che hoặc bị ghi đè bởi policy khác

Trong hệ thống có thứ tự, rule deny trước allow có thể chặn luồng hợp lệ; rule allow tổng quát đặt trước deny làm deny không có tác dụng. Trong hệ thống cloud, hợp của các allow rule có thể cấp quyền rộng hơn dự kiến.

### 12.7. Không tính NAT và proxy

Source trước SNAT khác source firewall phía sau nhìn thấy; destination trước DNAT khác backend sau DNAT. Các proxy cũng có thể phát kết nối mới với source IP của proxy, khiến policy cho IP người dùng không match.

### 12.8. Bỏ quên đường không qua firewall

Hai host cùng VLAN, một route peering, VPN site-to-site hoặc đường quản trị cloud có thể bypass điểm lọc dự kiến. Phân đoạn thực chất dựa trên **đường đi và điểm thực thi**, không chỉ trên sơ đồ vùng mạng.

### 12.9. Không có rule IPv6 tương ứng

Ứng dụng dual-stack có thể vẫn reachable qua IPv6 dù bạn chỉ triển khai rule IPv4. Cần xác định liệu dùng IPv6, có đường Internet hoặc route nội bộ nào và áp policy tương đương khi cần.

### 12.10. Rule mở tạm trở thành vĩnh viễn

Trong sự cố, rule rộng có thể được thêm để chẩn đoán nhưng không có owner hoặc thời hạn. Sau đó trở thành lỗ hổng phân đoạn. Ngoại lệ phải có lý do, phạm vi, người duyệt, thời gian hết hạn và kiểm tra thu hồi.

### 12.11. Chỉ tin vào port để xác định ứng dụng

TCP/443 thường liên quan HTTPS nhưng ứng dụng khác có thể chạy trên 443; một số dịch vụ dùng port không mặc định hoặc tunnel qua cổng được phép. Lọc L3/L4 cần bổ sung xác thực ứng dụng, TLS inspection khi có chính sách phù hợp, proxy, DNS policy hoặc service identity để đáp ứng yêu cầu cao hơn.

## 13. Mô hình hóa mối đe dọa đối với network access rule

Trong threat modeling, một rule **allow** là cạnh thể hiện khả năng tiếp cận một dịch vụ từ một tập nguồn, với điều kiện traffic thật đi qua rule và không bị kiểm soát khác ngăn.

~~~mermaid
flowchart LR
    G[Guest endpoint] -->|TCP/5432 bị từ chối| F[Policy liên vùng]
    A[App workload] -->|TCP/5432 được phép| F
    F --> DB[(Database)]
    DB -.Xác thực DB.-> AUTH[Giới hạn quyền dữ liệu]
    V[VPN quản trị] -->|TCP/22| J[Jump host]
~~~

Một adversary chiếm được máy App có thể sử dụng **đường App → DB vốn được cho phép**. Rule đúng vẫn là lớp phòng vệ cần thiết, nhưng không chặn được mọi hành vi từ workload đã được cấp quyền. Từ đó cần hỏi:

1. Đối thủ ở vị trí nào: Internet, Guest, Staff, App, VPN hay Cloud IAM?
2. Đối thủ kiểm soát source IP hoặc danh tính thực sự ở mức nào? Có thể spoof IP trên đoạn mạng này không? Có anti-spoofing hoặc NAC?
3. Có đường đến firewall hoặc backend không? Có đường thay thế?
4. Rule nào cho luồng đi tới tài sản, protocol/port nào? Stateful hay stateless?
5. Có quyền xác thực dịch vụ sau khi được phép kết nối không?
6. Có khả năng sửa chính firewall policy, security group hoặc route không?
7. Có log/IDS/IPS và phương án ứng phó khi kết nối bất thường không?

**Ví dụ về giới hạn của IP allowlist:** nếu mọi App instance cùng dùng 10.10.20.0/24, việc chiếm một instance có thể giúp đối thủ đến DB qua policy App → DB. Cần kiểm soát phía DB (tài khoản riêng, least privilege, mã hóa, audit), bảo mật workload và phân đoạn bổ sung.

**Ví dụ về control plane:** một tài khoản cloud bị lộ có quyền thay security group có thể mở đường mới dù trước đó data plane chặn. Vì vậy phân quyền IAM, MFA, guardrail và audit cấu hình là một phần của thiết kế network access control, ngoài L3/L4.

## 14. Tương tác với DNS, VPN, IDS/IPS, Wi-Fi và cloud

| Công nghệ | Rule source–destination–port liên quan thế nào? | Giới hạn cần nhớ |
|---|---|---|
| **DNS** | Chỉ cho client được phép hỏi resolver UDP/TCP 53; quản lý egress resolver | DoH/DoT dùng kênh khác; DNSSEC không phải firewall |
| **VPN** | Nguồn sau tunnel thuộc VPN pool hoặc identity group; rule hạn chế tài nguyên đích | Vào VPN không đồng nghĩa toàn quyền trong LAN |
| **IDS/IPS** | Ghi nhận luồng allow/deny, tìm hoạt động quét, truy cập trái phép, lateral movement | IDS chỉ nhìn nơi có sensor/telemetry; không mặc nhiên giải mã TLS |
| **Wi-Fi/NAC** | 802.1X/SSID/VLAN xác định vùng mạng ban đầu; ACL hạn chế Guest, IoT, Staff | MAC có thể giả; VLAN một mình không thay identity/auth |
| **Cloud security group** | Quy định inbound/outbound cho interface/workload theo tính năng provider | Stateful, rule aggregation, object type phụ thuộc cloud |
| **Cloud network ACL** | Có thể lọc traffic ở subnet theo cả hai hướng | Có thể stateless và cần rule cho ephemeral ports tùy cloud |
| **Kubernetes NetworkPolicy** | Có thể match pod/namespace/IP/port theo ingress và egress | Hiệu lực phụ thuộc CNI và loại traffic, không đồng nhất với firewall first-match |
| **Service mesh / mTLS** | Tách quyền mạng với danh tính dịch vụ | Cho TCP/443 không tự chứng minh service identity hợp lệ |
| **Host firewall** | Giới hạn listener trên chính máy, kể cả khi hai host cùng VLAN | Cần quản lý cùng policy mạng, tránh khác biệt làm khó chẩn đoán |

Thực tế nhiều sự cố không xuất phát từ một rule đơn lẻ, mà từ sự **không nhất quán giữa các lớp**: security group cho phép nhưng host firewall chặn; VPN cho route nhưng ACL deny; mạng khách bị tách khỏi DB nhưng có một cổng quản trị vô tình public; hay IPv4 được lọc nhưng IPv6 không có policy tương ứng.

## 15. Bài tập tình huống có đáp án gợi ý

### Tình huống 1 — App kết nối database thất bại

Đội vận hành có rule:

~~~text
ALLOW source=10.10.20.0/24 destination=10.10.30.15/32
      protocol=tcp destination_port=5432
~~~

App **10.10.20.42** không kết nối DB được.

**Câu hỏi:** Có thể khẳng định rule sai không?

**Gợi ý:** chưa. Kiểm tra route giữa App–DB, listener DB, host firewall, stateful/stateless, rule ưu tiên, NAT, chiều về, DNS nếu App dùng hostname, và quyền đăng nhập DB. Một allow rule không đảm bảo mọi lớp còn lại đều cho phép.

### Tình huống 2 — Firewall stateless không trả lời HTTPS

ACL cho phép:

~~~text
Client 10.10.10.25:any → Web 10.10.20.10:443 TCP
~~~

Máy web có listener và ghi nhận SYN đến nhưng client không hoàn tất kết nối.

**Câu hỏi:** còn thiếu giả định nào?

**Gợi ý:** cần xem rule chiều phản hồi **Web:443 → Client:ephemeral TCP**, route ngược và các ACL khác. Nếu ACL không có state tracking, cho phép chiều đi không tự cho phép chiều về.

### Tình huống 3 — Rule allow rộng hơn rule deny

Ordered ACL:

~~~text
10 ALLOW ANY             → 10.10.30.15 TCP/5432
20 DENY  10.10.50.0/24   → 10.10.30.15 TCP/5432
~~~

**Câu hỏi:** Guest có bị chặn theo rule 20 không?

**Gợi ý:** nếu thiết bị dùng first-match theo thứ tự, traffic Guest sẽ match rule 10 trước và được phép; rule 20 không có tác dụng với traffic đó. Cần thu hẹp rule 10 và sắp xếp ưu tiên phù hợp với sản phẩm.

### Tình huống 4 — Sửa rule public IP nhưng backend vẫn không truy cập được

Một khách truy cập **203.0.113.10:443**, NAT chuyển đến **10.10.20.10:8443**. Đội vận hành đã cho phép destination **203.0.113.10:443** trên một điểm kiểm soát nằm sau DNAT.

**Câu hỏi:** vì sao rule có thể không match?

**Gợi ý:** sau DNAT, thiết bị/chain đó có thể thấy destination **10.10.20.10:8443**. Cần biết điểm thực thi và thứ tự NAT/filter cụ thể; không tự giả định rule theo public IP match tại mọi nơi.

### Tình huống 5 — Cloud app bị chiếm nhưng rule phân đoạn vẫn đúng

DB chỉ cho source security group của App truy cập TCP/5432. Một App instance bị chiếm và kẻ tấn công sử dụng được credential DB của chính instance.

**Câu hỏi:** đây có phải chứng cứ rule mạng vô hiệu không?

**Gợi ý:** chưa. Rule đang thực hiện mục tiêu giới hạn **nhóm workload có thể kết nối**. Rủi ro còn lại nằm ở workload được cấp quyền và quyền ứng dụng/DB. Cần phân quyền từng workload, xoay secret, hardening, audit và kiểm soát truy cập dữ liệu.

### Tình huống 6 — DNS hoạt động không ổn định

Subnet Staff được phép truy vấn resolver nội bộ chỉ với **UDP/53**. Truy vấn nhỏ chạy bình thường, nhưng một số trường hợp liên quan DNS qua TCP thất bại.

**Câu hỏi:** cần sửa chính sách thế nào?

**Gợi ý:** nếu resolver và nghiệp vụ yêu cầu DNS qua TCP, thêm rule đúng source/destination cho **TCP/53** bên cạnh UDP/53, đồng thời kiểm tra listener, route và policy DNS; không mở **Any TCP port** để xử lý vấn đề.

## 16. Checklist review rule trước và sau triển khai

- [ ] Có yêu cầu nghiệp vụ xác định rõ **nguồn → đích → giao thức/cổng đích**.
- [ ] Source được giới hạn theo IP/CIDR, zone, workload hoặc identity phù hợp.
- [ ] Destination đủ hẹp và đúng địa chỉ trước/sau NAT tại điểm thực thi.
- [ ] Đã phân biệt **source port** và **destination port**.
- [ ] Đã xét TCP/UDP, ICMP/ICMPv6 và cả IPv4/IPv6 khi môi trường sử dụng.
- [ ] Đã xác định thiết bị/policy thực sự nằm trên đường truyền.
- [ ] Đã xác định cơ chế **stateful/stateless** và nhu cầu lưu lượng phản hồi.
- [ ] Đã xem thứ tự/ưu tiên, rule shadowing, rule rộng hơn và default action.
- [ ] Đã xác minh rule không bị bypass qua VLAN nội bộ, VPN, peering hoặc đường cloud khác.
- [ ] Đã kiểm tra tương tác với host firewall, security group, network ACL và NetworkPolicy khi có.
- [ ] Đã có test **được phép** và test **bị từ chối** từ đúng điểm nguồn.
- [ ] Đã đọc kết quả từ ít nhất hai nơi khi cần: client và log/counter tại điểm áp policy.
- [ ] Đã đánh giá quyền ở ứng dụng sau kết nối mạng, cùng bảo vệ TLS/mTLS và secrets.
- [ ] Đã ghi owner, lý do, ngày review, thời hạn ngoại lệ, log và kế hoạch rollback.
- [ ] Đã kiểm chứng lại sau khi sửa đổi rule, route, VLAN, VPN, DNS hoặc triển khai workload mới.

## 17. Kết luận

Một rule theo **source, destination và port** là cách biểu đạt cụ thể ranh giới truy cập: **nguồn nào được phép nói chuyện với đích nào, bằng giao thức và cổng nào**. Chất lượng của rule phụ thuộc vào độ chính xác của tập IP/identity, vị trí áp dụng, thứ tự ưu tiên, cơ chế stateful/stateless, NAT, IPv4/IPv6 và khả năng kiểm chứng trong mạng thực.

Trong kiến trúc an toàn, rule L3/L4 phải phối hợp với **phân đoạn mạng, 802.1X/NAC, VPN, DNS policy, firewall, IDS/IPS, bảo vệ workload/cloud, TLS và xác thực ứng dụng**. Mục tiêu cuối cùng là chỉ duy trì những đường truy cập cần thiết cho nghiệp vụ, có bằng chứng rõ ràng về cả những kết nối được phép lẫn những kết nối phải bị chặn.
