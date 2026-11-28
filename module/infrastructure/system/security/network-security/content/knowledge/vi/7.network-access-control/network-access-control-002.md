# Network ACL: kiểm soát truy cập bằng quy tắc lưu lượng mạng

**Network Access Control List (Network ACL, ACL mạng)** là tập các quy tắc xác định gói tin hoặc luồng kết nối nào được **cho phép** (permit/allow) và gói tin nào bị **từ chối** (deny/drop/reject) tại một điểm kiểm soát mạng. Mỗi quy tắc thường dựa trên địa chỉ IP nguồn và đích, giao thức, cổng, hướng lưu lượng và độ ưu tiên. ACL giúp giới hạn đường đi có thể sử dụng giữa các mạng, dịch vụ và vùng bảo mật; nó là một công cụ cơ bản để **phân đoạn mạng** và thực thi nguyên tắc **quyền tối thiểu**.

Trong chương **Network access control** của module **SECURITY_NETWORK_SECURITY**, Network ACL kết nối các chủ đề định tuyến, firewall, VPN, giám sát IDS/IPS, xác thực kết nối, DNS, Wi-Fi và bảo mật hạ tầng đám mây. Để thiết kế kiến trúc mạng an toàn, cần hiểu ACL kiểm soát được điều gì, điều gì nằm ngoài phạm vi của nó và cách kiểm chứng đường truyền được bảo vệ thực sự.

## 1. Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Giải thích ACL mạng khác gì với định tuyến, firewall có trạng thái, kiểm soát truy cập dựa trên danh tính và quyền ứng dụng.
2. Đọc một quy tắc theo **nguồn → đích, giao thức, cổng, hướng, hành động, mức ưu tiên**; phân tích thứ tự khớp quy tắc và mặc định từ chối.
3. Phân biệt **stateless ACL** với **stateful filtering**, bao gồm việc xử lý gói phản hồi.
4. Thiết kế ACL cho nhiều vùng mạng theo nguyên tắc chỉ mở các luồng nghiệp vụ cần thiết.
5. Kiểm tra và xử lý tình huống kết nối bị chặn nhầm, quy tắc quá rộng, đường bất đối xứng, NAT và IPv6.
6. Biết cách rà soát ACL, ghi log, quản lý thay đổi và kết hợp phòng vệ nhiều lớp trong hạ tầng tại chỗ và cloud.

## 2. ACL hoạt động ở đâu?

Một thiết bị hoặc hệ thống áp dụng ACL sẽ kiểm tra thuộc tính của gói tin tại **điểm thực thi chính sách** (enforcement point), ví dụ: interface của router, switch lớp 3, firewall, mạng con trong cloud hoặc mạng ảo của workload. ACL phổ biến nhất hoạt động ở **tầng mạng (L3)** và **tầng vận chuyển (L4)**; một số nền tảng có khả năng lọc nâng cao ở các tầng khác, nhưng cần đọc rõ phạm vi của loại ACL đang triển khai.

~~~mermaid
flowchart LR
    U["Mạng người dùng"] --> R["Router / Firewall\nđiểm thực thi ACL"]
    R -->|Chỉ luồng được phép| D["DMZ / Web"]
    R -->|Chỉ luồng được phép| A["Mạng ứng dụng"]
    A -->|Chính sách riêng| B[("Mạng dữ liệu")]
    R -->|Lưu lượng có điều kiện| I["Internet"]
~~~

Đối với gói tin đi qua điểm thực thi, việc xử lý về mặt khái niệm gồm:

1. Xác định **hướng** và giao diện, subnet hoặc vùng mà gói đang đi qua.
2. Lấy thuộc tính liên quan: IP nguồn/đích, IPv4 hay IPv6, protocol (TCP/UDP/ICMP...), cổng nếu giao thức có cổng, và trạng thái kết nối nếu hệ thống hỗ trợ.
3. So các thuộc tính với danh sách quy tắc, theo **mô hình ưu tiên của thiết bị**.
4. Thực hiện hành động của quy tắc phù hợp; nếu không khớp, áp dụng **hành vi mặc định đã cấu hình**.
5. Chuyển gói tới bước xử lý tiếp theo hoặc loại bỏ gói; ghi log/counter nếu được bật và hỗ trợ.

**Điểm cần nhớ:** ACL chỉ quyết định liệu một gói có được vượt qua điểm thực thi hay không. Nó **không tự tạo route**, không đảm bảo máy đích đang nghe cổng và không tự xác thực người dùng hay mã hóa dữ liệu. Một kết nối muốn thành công phải đồng thời có định tuyến hợp lệ, phân giải tên/địa chỉ đúng, chính sách ở mọi điểm trung gian cho phép và dịch vụ đích sẵn sàng.

### 2.1. Phân biệt các cơ chế thường gặp

| Cơ chế | Trả lời câu hỏi | Phạm vi / giới hạn |
| --- | --- | --- |
| **Network ACL** | Gói hoặc luồng có được phép đi qua điểm kiểm soát không? | Chủ yếu dựa trên IP, giao thức, cổng, hướng; không đủ để kết luận người dùng có quyền xem dữ liệu |
| **Routing** | Gói đi qua đường/interface nào để tới đích? | Có route không có nghĩa được ACL cho phép |
| **Firewall** | Có nên cho phép, theo dõi và/hoặc kiểm tra lưu lượng không? | Firewall có thể dùng ACL và theo dõi trạng thái; tính năng phụ thuộc sản phẩm |
| **Security group / network policy** | Workload/instance/pod nào được gửi và nhận loại lưu lượng nào? | Ngữ nghĩa stateful, phạm vi áp dụng, thứ tự rule khác nhau theo nền tảng |
| **NAC / 802.1X** | Thiết bị hoặc người dùng nào được gia nhập mạng? | Kiểm soát quyền vào mạng; có thể cấp VLAN/chính sách nhưng không thay cho ACL giữa dịch vụ |
| **IAM / RBAC / quyền API** | Danh tính nào được thực hiện hành động lên tài nguyên? | Vẫn cần bảo vệ luồng mạng và phân đoạn |
| **VPN / TLS** | Lưu lượng có được bảo vệ trong quá trình truyền không? | Mã hóa không đồng nghĩa được quyền truy cập mọi máy hoặc cổng |
| **IDS/IPS / WAF** | Có tín hiệu tấn công hoặc vi phạm chính sách cần phát hiện/chặn không? | Cần kết hợp giới hạn kết nối và phân quyền; khả năng quan sát phụ thuộc lưu lượng được giải mã hay không |

Một kỹ sư có thể kết hợp **NAC để nhận diện thiết bị**, **ACL để giới hạn đường kết nối**, **TLS/mTLS để bảo vệ và xác thực dịch vụ**, **IAM để quyết định quyền với dữ liệu** và **IDS/IPS để giám sát hoạt động bất thường**.

## 3. Cấu trúc một quy tắc ACL

Một quy tắc thường có các thành phần sau:

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Priority / Sequence | 100 | Xác định quy tắc nào được xét trước nếu nền tảng dùng danh sách có thứ tự |
| Action | ALLOW, DENY | Cho phép hoặc chặn lưu lượng phù hợp |
| Source | 10.20.10.0/24 | Dải địa chỉ nguồn; /24 chứa 256 địa chỉ IPv4 |
| Destination | 10.20.20.10/32 | Đích cụ thể: một IP đơn |
| Protocol | TCP | Loại giao thức L4/L3 cần khớp |
| Source port | ANY | Cổng nguồn, thường là cổng tạm thời do client chọn |
| Destination port | 443 | Cổng dịch vụ HTTPS trên đích |
| Direction | INGRESS / EGRESS | Hướng đi vào/ra **theo điểm thực thi**, không nhất thiết theo góc nhìn của ứng dụng |
| Logging / Counter | enabled | Ghi nhận số lần khớp hoặc sự kiện, tùy khả năng nền tảng |
| Description / Owner | app-client-to-api | Mục đích, người phụ trách để rà soát sau này |

Ví dụ quy tắc trung lập, **minh họa logic, không phải cấu hình của một hãng cụ thể**:

~~~text
PRIORITY 100
ACTION   ALLOW
DIRECTION INGRESS_TO_APP
SOURCE   10.20.10.0/24
DEST     10.20.20.10/32
PROTOCOL TCP
SRC_PORT ANY
DST_PORT 443
COMMENT  "Mạng nhân viên truy cập API HTTPS"
~~~

Quy tắc này chỉ cho phép những gói phù hợp với các điều kiện đã nêu **tại điểm và hướng nó được áp dụng**. Nó không cho phép mọi luồng ngược lại, không đồng nghĩa tất cả host trong dải nguồn có quyền gọi mọi API và cũng không quyết định HTTP request nào được ứng dụng chấp nhận.

### 3.1. CIDR và phạm vi địa chỉ

ACL mạng thường dùng **CIDR (Classless Inter-Domain Routing)** để mô tả địa chỉ:

| CIDR IPv4 | Phạm vi ví dụ | Phạm vi chính sách |
| --- | --- | --- |
| 10.20.20.10/32 | Chỉ 10.20.20.10 | Một host |
| 10.20.20.0/24 | 10.20.20.0–10.20.20.255 | Một subnet gồm 256 địa chỉ; một phần địa chỉ có thể dành riêng tùy môi trường |
| 10.20.0.0/16 | 10.20.0.0–10.20.255.255 | Nhiều subnet; rộng hơn /24 |
| 0.0.0.0/0 | Toàn bộ địa chỉ IPv4 | Mọi nguồn/đích IPv4, nếu không có điều kiện khác |
| ::/0 | Toàn bộ địa chỉ IPv6 | Mọi nguồn/đích IPv6, **không** đồng nghĩa với 0.0.0.0/0 |

**Prefix càng ngắn, vùng IP càng rộng.** Một thay đổi từ 10.20.20.10/32 sang 10.20.0.0/16 có thể mở quyền tới hàng chục nghìn địa chỉ. Trong cloud, dải IP của subnet đôi khi có địa chỉ dành riêng cho hạ tầng, nhưng độ rộng CIDR của quy tắc vẫn cần được đánh giá đầy đủ.

Cần kiểm tra **đồng thời IPv4 và IPv6**. Chặn cổng quản trị trên IPv4 không đủ nếu cùng dịch vụ có IPv6 và chính sách IPv6 rộng hơn.

### 3.2. Giao thức và cổng

**TCP** và **UDP** có cổng nguồn/đích. Ví dụ, đích TCP/443 thường là HTTPS qua TCP; HTTP/3 dùng QUIC trên **UDP/443**. Một quy tắc chỉ cho phép TCP/443 không tự cho phép UDP/443.

**ICMP** không có cổng TCP/UDP; nhiều ACL sử dụng loại/thông điệp (type/code) khi cần lọc ICMP. Chặn toàn bộ ICMP có thể làm khó việc chẩn đoán và ảnh hưởng chức năng mạng như phát hiện MTU phù hợp. Với IPv6, **ICMPv6** đặc biệt quan trọng cho Neighbor Discovery và các chức năng điều khiển mạng; không chặn bừa bãi tất cả ICMPv6.

Không được suy ra tên dịch vụ chỉ từ cổng: một ứng dụng có thể dùng cổng không chuẩn, và dịch vụ đặt trên 443 không có nghĩa là nội dung hợp lệ hoặc đã được chứng thực.

### 3.3. Thứ tự quy tắc và hành vi mặc định

**Nhiều nền tảng ACL dùng nguyên tắc “khớp trước, xử lý trước” (first match)**, xét các mục theo thứ tự hoặc số ưu tiên rồi dừng tại mục đầu tiên phù hợp:

| Thứ tự | Hành động | Source | Destination | Protocol/port | Ý định |
| ---: | --- | --- | --- | --- | --- |
| 100 | ALLOW | 10.20.10.0/24 | 10.20.20.10/32 | TCP/443 | Mở truy cập HTTPS cần thiết |
| 200 | DENY | 10.20.10.0/24 | 10.20.20.0/24 | ALL | Chặn các kết nối khác tới vùng ứng dụng |
| 900 | DENY | ANY | ANY | ALL | Từ chối phần còn lại (minh họa) |

Nếu đưa quy tắc **DENY ANY → ANY** lên đầu, mọi quy tắc ALLOW phía dưới có thể trở nên vô hiệu (*shadowed rules*). Tương tự, một ALLOW nguồn rộng/đích rộng đặt trước quy tắc DENY cụ thể có thể làm mất ý nghĩa của quy tắc DENY.

Tuy nhiên, **không áp dụng máy móc first match cho mọi sản phẩm**: một số hệ thống chọn quy tắc theo độ ưu tiên, có rule mặc định, nhóm chính sách hoặc ngữ nghĩa chỉ cho phép (*allow-only*). Hãy xác nhận rõ cách quyết định của nền tảng trước khi cấu hình.

Với nhiều ACL kiểu router, có **implicit deny** khi không quy tắc nào khớp. Một số nền tảng có rule mặc định khác hoặc ngoại lệ dành cho hạ tầng. **Default deny** là nguyên tắc thiết kế nên áp dụng, nhưng luôn phải đọc hành vi thực tế của thiết bị.

## 4. Ingress, egress và trạng thái kết nối

### 4.1. Hướng luôn phụ thuộc điểm thực thi

- **Ingress (inbound):** lưu lượng đi **vào** interface, subnet, workload hoặc boundary được bảo vệ.
- **Egress (outbound):** lưu lượng đi **ra khỏi** điểm đó.

Một gói từ người dùng tới API vừa là **egress** đối với phía người dùng, vừa là **ingress** đối với phía API. Vì vậy câu “mở inbound 443” là chưa đủ để triển khai: cần nói **mở ở đâu, trên interface/subnet nào, cho nguồn/đích nào**.

Trong mạng nhiều hop, cùng một gói có thể gặp nhiều chính sách. Cho phép ở một subnet không vô hiệu hóa quy tắc từ chối trên firewall/host khác.

### 4.2. Stateless ACL và gói phản hồi

ACL **stateless** xét từng gói độc lập, thường không nhớ gói thuộc kết nối TCP nào trước đó. Khi đó, một hướng ALLOW không tự động cho phép phản hồi.

Ví dụ minh họa trong phòng lab:

~~~text
Client: 10.20.10.25:53000
Server: 10.20.20.10:443

Request:
10.20.10.25:53000 -- TCP --> 10.20.20.10:443

Response:
10.20.20.10:443 -- TCP --> 10.20.10.25:53000
~~~

Nếu tại điểm áp dụng stateless ACL, cả hai hướng đều bị lọc, cần quy tắc **phù hợp ở mỗi hướng**. Mở chiều request từ client tới server port 443 nhưng chặn toàn bộ chiều response có thể khiến TCP handshake không hoàn thành dù server đang hoạt động.

Bảng ví dụ giả định client ở mạng 10.20.10.0/24 được cấu hình dùng **cổng tạm thời 49152–65535**:

| Hướng tại bộ lọc | Source | Source port | Destination | Dest port | Hành động |
| --- | --- | --- | --- | --- | --- |
| Client → API | 10.20.10.0/24 | 49152–65535 | 10.20.20.10/32 | TCP 443 | ALLOW |
| API → Client | 10.20.20.10/32 | TCP 443 | 10.20.10.0/24 | 49152–65535 | ALLOW |
| Còn lại | ANY | ANY | ANY | ANY | DENY |

**Dải cổng tạm thời ở đây chỉ là giả định lab.** Nhiều hệ điều hành, ứng dụng hoặc thiết bị NAT dùng dải khác. Cần xác định dải nguồn/đích trên hệ thống thực trước khi triển khai và không mở dải rộng một cách tùy tiện. Đối với giao thức có nhiều kết nối phụ hoặc hành vi đặc biệt, mô hình từng gói có thể phức tạp hơn ví dụ trên.

### 4.3. Stateful filtering

Firewall hoặc security group **stateful** theo dõi trạng thái kết nối. Khi một luồng khởi tạo được chấp nhận, lưu lượng phản hồi phù hợp với kết nối đã theo dõi thường được cho phép tự động theo chính sách sản phẩm.

| Tính chất | Stateless ACL | Stateful firewall/filter |
| --- | --- | --- |
| Cách đánh giá | Từng gói độc lập | Gói và trạng thái/phiên đang theo dõi |
| Lưu lượng phản hồi | Thường phải có quy tắc tương ứng | Thường được cho phép theo trạng thái kết nối |
| Quản lý | Rõ ràng nhưng dễ thiếu chiều phản hồi | Đơn giản hơn cho luồng client–server thông thường |
| Phụ thuộc | Quy tắc, thứ tự, interface, hướng | Quy tắc, bảng trạng thái, timeout, đặc điểm giao thức |
| Nguy cơ vận hành | Mở cổng ephemeral quá rộng hoặc chặn phản hồi | Bảng trạng thái đầy, timeout, luồng bất đối xứng |

**Stateful không đồng nghĩa bảo đảm an toàn toàn bộ dữ liệu.** Một kết nối TCP được ACL cho phép vẫn có thể gọi API thiếu kiểm tra quyền; một phiên TLS hợp lệ vẫn có thể gửi nội dung độc hại. Những rủi ro này cần kiểm soát bổ sung ở tầng ứng dụng và giám sát.

## 5. Ví dụ kiến trúc: phân đoạn và bảo vệ API

Xét một hệ thống giả định:

| Vùng | Dải / host minh họa | Vai trò |
| --- | --- | --- |
| Người dùng nội bộ | 10.20.10.0/24 | Máy trạm truy cập ứng dụng |
| DMZ / Reverse proxy | 10.20.20.10/32 | Tiếp nhận HTTPS của người dùng |
| Ứng dụng nội bộ | 10.20.30.10/32 | API xử lý nghiệp vụ |
| Dữ liệu | 10.20.40.10/32 | Database, chỉ phục vụ ứng dụng |
| DNS nội bộ | 10.20.50.53/32 | Resolver phục vụ tên miền nội bộ |
| Mạng quản trị | 10.20.60.0/24 | Bastion và công cụ vận hành đã được xác thực |

Sơ đồ luồng:

~~~mermaid
flowchart LR
    U["User VLAN\n10.20.10.0/24"] -->|"TCP/443"| P["Reverse proxy\n10.20.20.10"]
    P -->|"TCP/8443"| A["App API\n10.20.30.10"]
    A -->|"TCP/5432"| D[("Database\n10.20.40.10")]
    U -->|"DNS UDP/TCP 53"| N["DNS\n10.20.50.53"]
    M["Admin VLAN\n10.20.60.0/24"] -->|"SSH qua bastion được cấp phép"| B["Bastion"]
    B -->|"Cổng quản trị cần thiết"| A
~~~

Giả định nghiệp vụ:

- Người dùng chỉ cần gọi **reverse proxy qua TCP/443**, không gọi thẳng API hoặc database.
- Reverse proxy giao tiếp với API qua **TCP/8443**; ứng dụng giao tiếp với database qua **TCP/5432**.
- DNS nội bộ nhận truy vấn hợp lệ từ mạng được cấp quyền; cần kiểm soát riêng việc chuyển tiếp DNS và log.
- Quản trị viên đi qua **bastion**, có xác thực/MFA phù hợp và quyền tối thiểu; không mở SSH từ toàn bộ mạng người dùng.
- Mỗi vùng có chính sách **default deny**. Các luồng cấp phép được rà soát ở cả ingress và egress theo điểm thực thi thực tế.

### 5.1. Ma trận luồng mong muốn

| ID | Nguồn | Đích | Giao thức, cổng đích | Kết quả mong muốn | Lý do |
| --- | --- | --- | --- | --- | --- |
| F1 | User VLAN | Reverse proxy | TCP/443 | ALLOW | Người dùng truy cập web |
| F2 | Reverse proxy | App API | TCP/8443 | ALLOW | Proxy chuyển request hợp lệ |
| F3 | App API | Database | TCP/5432 | ALLOW | Xử lý dữ liệu ứng dụng |
| F4 | User VLAN | DNS | UDP/TCP 53 | ALLOW | Phân giải tên miền nội bộ theo chính sách |
| F5 | Bastion | App API | TCP/22 nếu thực sự cần SSH | ALLOW có điều kiện | Quản trị qua đầu mối kiểm soát |
| F6 | User VLAN | Database | ANY | DENY | Không cho máy người dùng truy cập dữ liệu trực tiếp |
| F7 | Internet không tin cậy | App API / Database | ANY | DENY | Không công khai backend |
| F8 | App API | Internet | ANY | DENY theo mặc định | Hạn chế exfiltration; thêm ngoại lệ có kiểm soát nếu cần |

Bảng này mô tả **luồng khởi tạo được phép**. Để chuyển thành ACL stateless, phải xét thêm gói phản hồi, cổng tạm thời, interface và hướng; với stateful, kiểm tra ngữ nghĩa lưu lượng trả lời của sản phẩm.

### 5.2. Chuyển ma trận sang policy trung lập

Ví dụ **policy mô tả ý định**, không phải mã cấu hình áp dụng được cho router, AWS, Azure hay Kubernetes:

~~~yaml
policy: internal-segmentation
default: deny
flows:
  - id: F1
    from: 10.20.10.0/24
    to: 10.20.20.10/32
    protocol: tcp
    destination_port: 443
    action: allow
    reason: user-to-web
  - id: F2
    from: 10.20.20.10/32
    to: 10.20.30.10/32
    protocol: tcp
    destination_port: 8443
    action: allow
    reason: web-to-api
  - id: F3
    from: 10.20.30.10/32
    to: 10.20.40.10/32
    protocol: tcp
    destination_port: 5432
    action: allow
    reason: api-to-db
  - id: F4
    from: 10.20.10.0/24
    to: 10.20.50.53/32
    protocol: udp,tcp
    destination_port: 53
    action: allow
    reason: managed-dns
~~~

Trước khi chuyển policy này sang cú pháp cụ thể phải làm rõ: hướng thực thi, phạm vi subnet/host, chiều phản hồi, rule ưu tiên, cách NAT ảnh hưởng địa chỉ được nhìn thấy, hỗ trợ IPv6, các luồng tới dịch vụ nền tảng (DHCP/DNS/health check, giám sát...) và yêu cầu quản trị. Trong môi trường thật, địa chỉ IP có thể biến động khi instance được thay thế; lúc đó một giải pháp gắn rule với identity/tag/security group có thể phù hợp hơn CIDR cố định nếu nền tảng hỗ trợ.

### 5.3. Vì sao quy tắc quá rộng nguy hiểm?

So sánh:

~~~text
RỦI RO CAO:
ALLOW 10.20.0.0/16 -> 10.20.40.0/24 TCP/5432

GIỚI HẠN THEO NHU CẦU:
ALLOW 10.20.30.10/32 -> 10.20.40.10/32 TCP/5432
~~~

Quy tắc đầu tiên có thể cho nhiều host không liên quan tới nghiệp vụ truy cập database. Nếu một máy trong mạng người dùng bị xâm nhập, phạm vi tiếp cận dữ liệu lớn hơn đáng kể. Quy tắc thứ hai thu hẹp đến đúng nguồn và đích minh họa, nhưng vẫn phải có **xác thực database, phân quyền tài khoản DB và giám sát truy vấn**.

## 6. Network ACL trên router, firewall và cloud

Tên gọi ACL có thể giống nhau nhưng cách triển khai **không đồng nhất**. Đọc tài liệu của nền tảng được dùng là bước bắt buộc trước khi sao chép chính sách.

| Môi trường / loại chính sách | Phạm vi phổ biến | Đặc điểm cần nhớ |
| --- | --- | --- |
| Router / switch lớp 3 | Interface và hướng vào/ra | Có thể có standard/extended ACL, thứ tự rule, implicit deny; vị trí áp dụng ảnh hưởng phạm vi lọc |
| Firewall stateful | Interface, zone, mạng nguồn/đích, ứng dụng hoặc đối tượng | Có thể theo dõi kết nối, hỗ trợ NAT và ghi log; thứ tự xử lý NAT/routing/policy phụ thuộc sản phẩm |
| **AWS VPC Network ACL** | Liên kết với **subnet** | **Stateless**, quy tắc inbound/outbound độc lập, đánh giá theo số rule tăng dần đến rule khớp đầu tiên; có rule mặc định |
| **AWS Security Group** | Liên kết với network interface/instance và một số tài nguyên được hỗ trợ | **Stateful**, các rule cho phép theo hướng được cấu hình, không có rule DENY tường minh trong security group |
| **Azure Network Security Group (NSG)** | Subnet hoặc network interface theo cấu hình | **Stateful**, có quy tắc allow/deny và priority; quy tắc mặc định cần được xem xét |
| **Google Cloud VPC firewall rules** | Tài nguyên/traffic trong VPC theo target, tag hoặc service account tùy loại rule | Có tính **stateful**; cơ chế ưu tiên, inheritance và rule mặc định khác ACL subnet của AWS |
| **Kubernetes NetworkPolicy** | Lưu lượng đến/đi từ pod được chọn trong namespace | Hành vi phụ thuộc CNI có hỗ trợ NetworkPolicy; chủ yếu chính sách cho phép ingress/egress, không phải mọi tính năng L7 đều sẵn có |

**Ví dụ trên AWS:** Nếu subnet của application có NACL stateless, cần cấu hình cả inbound lẫn outbound để chiều yêu cầu và chiều phản hồi hợp lệ. Security Group của instance có thể cho phép một kết nối và lưu lượng trả lời theo trạng thái. Để lưu lượng hoạt động, **cả NACL, Security Group, route và chính sách tại máy đích** đều phải đáp ứng.

Không nên gọi mọi network policy của cloud là “Network ACL AWS”. Cần xác nhận **điểm gắn chính sách**, **đối tượng được lọc**, **cách khớp rule** và **quy tắc xử lý gói trả lời** của từng nền tảng.

### 6.1. Vị trí áp dụng ACL có thể thay đổi kết quả

Hai quy tắc giống nhau ở hai vị trí khác nhau không nhất thiết bảo vệ cùng một phạm vi:

- **ACL inbound tại interface mạng người dùng:** kiểm soát lưu lượng *đi vào router từ mạng người dùng* trước khi tới các mạng khác, nếu giao thức và nền tảng xử lý theo thứ tự đó.
- **ACL outbound tại interface mạng dữ liệu:** kiểm soát lưu lượng *rời router để đi vào mạng dữ liệu*.
- **ACL của subnet cloud:** có thể lọc ở ranh giới subnet và không thể hiện đúng như ACL đặt trên interface router vật lý.
- **Firewall host / network policy pod:** lọc sát workload, hữu ích khi nhiều dịch vụ dùng chung subnet và cần microsegmentation.

Nhiều hệ thống có thể có **luồng nội bộ cùng subnet** không đi qua điểm ACL dự kiến. Ví dụ, ACL trên interface router liên VLAN không nhất thiết lọc được hai máy giao tiếp trực tiếp trong cùng một VLAN. Khi đó cần bộ lọc tại host, switch phù hợp hoặc phân đoạn khác.

### 6.2. NAT, load balancer và địa chỉ được nhìn thấy

**NAT (Network Address Translation)** có thể thay đổi địa chỉ/cổng nguồn hoặc đích. Tại một số điểm thực thi, ACL khớp với địa chỉ **trước NAT**, nhưng tại điểm khác nó thấy địa chỉ **sau NAT**. Thứ tự xử lý NAT, route và ACL là đặc thù sản phẩm, vì vậy phải xác minh bằng tài liệu hoặc công cụ quan sát của thiết bị.

Ví dụ, nếu 10.20.10.25 đi Internet qua NAT và được dịch sang địa chỉ công cộng của cổng ra, rule của hệ thống ở ngoài mạng nội bộ có thể nhìn thấy **địa chỉ công cộng**, không phải 10.20.10.25. Cũng vậy, một load balancer hoặc proxy có thể khởi tạo kết nối mới từ chính IP của nó tới backend; ACL của backend sẽ thấy nguồn là proxy, không phải IP người dùng ban đầu.

Đừng mở CIDR rộng chỉ để “sửa nhanh” một sự cố mà chưa biết chính xác địa chỉ nguồn/đích tại điểm lọc.

## 7. Thiết kế chính sách theo nguyên tắc quyền tối thiểu

Một ACL có thể hoạt động đúng về kỹ thuật nhưng vẫn **quá rộng** so với nhu cầu kinh doanh. Quy trình thiết kế nên bắt đầu từ **luồng cần thiết**, rồi mới viết rule:

1. **Liệt kê tài sản và vùng:** người dùng, hệ thống công khai, API, database, DNS, mạng quản trị, VPN và mạng khách.
2. **Xác định luồng nghiệp vụ:** ai cần nói chuyện với ai, giao thức gì, cổng đích, hướng khởi tạo và tần suất sử dụng.
3. **Định ranh giới tin cậy:** Internet, VPN, Wi-Fi khách, DMZ, mạng ứng dụng và vùng dữ liệu có các yêu cầu khác nhau.
4. **Chọn điểm thực thi:** router, firewall, subnet ACL, security group, host firewall, network policy; đảm bảo lưu lượng thật sự đi qua điểm đó.
5. **Tạo allowlist chính xác:** phạm vi nguồn/đích nhỏ nhất có thể, cổng/giao thức tối thiểu, xác định chính sách với IPv4 và IPv6.
6. **Xử lý phản hồi:** phân biệt stateless với stateful; thêm rule cần thiết cho TCP/UDP và traffic nền tảng theo hướng thực tế.
7. **Chặn phần còn lại:** xác nhận hành vi default deny hoặc bổ sung rule từ chối phù hợp với nền tảng.
8. **Kiểm thử và giám sát:** đo kết quả luồng được phép, luồng phải bị chặn, log/counter và ảnh hưởng tới dịch vụ.
9. **Gắn trách nhiệm:** ghi owner, lý do, ngày rà soát và thời hạn cho ngoại lệ, nhất là rule tạm thời.

### 7.1. Policy cho quản trị, VPN và Wi-Fi

Một số yêu cầu hay bị bỏ sót:

- **Quản trị:** giới hạn SSH/RDP/HTTPS quản trị từ bastion hoặc mạng quản trị; yêu cầu MFA/identity policy phù hợp; không dựa vào ACL để thay cho mật khẩu/khóa và phân quyền máy chủ.
- **VPN:** kiểm soát **địa chỉ sau khi vào VPN** (địa chỉ được cấp cho client hoặc địa chỉ tại cổng VPN tùy thiết kế), đồng thời xác thực người dùng/thiết bị và chỉ cấp quyền tới dịch vụ cần thiết.
- **Wi-Fi khách:** chặn kết nối vào vùng dữ liệu và quản trị; nếu yêu cầu truy cập Internet, cho phép các luồng cần thiết qua gateway theo chính sách.
- **DNS:** cấp quyền truy vấn tới resolver được quản lý; lưu ý cả UDP và TCP/53 nếu kiến trúc dùng DNS truyền thống, và phân tích riêng DoT/DoH khi có.
- **DHCP, NTP, ICMP/ICMPv6:** rà các luồng nền tảng để tránh tạo sự cố mạng ngoài ý muốn.
- **Egress:** chỉ cho workload ra các dịch vụ cần thiết, kể cả hệ thống cập nhật, kho phụ thuộc, registry và dịch vụ cloud được duyệt. Cần cách quản lý địa chỉ động hoặc endpoint phù hợp.

### 7.2. ACL bảo vệ được gì trong threat modeling?

| Mối đe dọa | ACL giúp thế nào | Giới hạn cần bổ sung |
| --- | --- | --- |
| Truy cập trái phép cổng quản trị | Chặn nguồn ngoài vùng quản trị | Xác thực mạnh, MFA, phân quyền quản trị, audit |
| Di chuyển ngang sau khi máy trạm bị xâm nhập | Hạn chế kết nối đến subnet/tài nguyên khác | Microsegmentation, EDR, danh tính workload |
| Tiếp cận trực tiếp database từ Internet | Chặn các luồng tới cổng DB | Cấu hình DB, xác thực, encryption, kiểm tra quyền |
| Truyền dữ liệu ra Internet ngoài nhu cầu | Chính sách egress giới hạn đường kết nối | DLP/kiểm soát ứng dụng, giám sát, hạn chế secret, kiểm soát SaaS |
| Nghe lén thông tin | Giới hạn điểm tiếp cận/quan sát một số luồng | **TLS/VPN** để bảo vệ nội dung truyền; ACL không mã hóa gói |
| Dịch vụ lộ dữ liệu do API thiếu phân quyền | Có thể giảm đối tượng kết nối tới API | **Authorization ở ứng dụng** mới quyết định người dùng được xem tài nguyên nào |
| Tấn công trên kết nối đã được cho phép | Có thể chặn một số địa chỉ/cổng | IDS/IPS, WAF, bản vá và kiểm tra an toàn ứng dụng |

Nguyên tắc “**Zero Trust**” không thể đạt được chỉ bằng ACL. Nó đòi hỏi xác thực liên tục/phù hợp ngữ cảnh, quyền tối thiểu, kiểm tra thiết bị và giám sát. ACL là một thành phần thực thi của kiến trúc đó.

## 8. Những lỗi thường gặp khi cấu hình Network ACL

| Lỗi | Dấu hiệu | Cách tránh |
| --- | --- | --- |
| Đặt deny rộng trước allow cụ thể | Rule cho phép không có hiệu lực | Kiểm tra thứ tự và rule shadowing |
| Chỉ mở một hướng của ACL stateless | TCP handshake hoặc phản hồi thất bại | Đối chiếu chiều request và response với cổng thực tế |
| Mở 0.0.0.0/0 tới dịch vụ nội bộ | Bề mặt truy cập tăng mạnh | Giới hạn nguồn và đích theo nhu cầu |
| Chỉ kiểm tra IPv4 | Có thể còn đường IPv6 chưa hạn chế | Kiểm kê dual stack và chính sách IPv6 |
| Khớp sai IP do NAT hoặc proxy | Rule có vẻ đúng nhưng gói không khớp | Kiểm tra địa chỉ tại điểm thực thi và thứ tự NAT |
| Route bất đối xứng qua stateful firewall | Gói phản hồi không đi qua nơi lưu trạng thái | Xác minh tuyến đi/về, thiết kế HA và state synchronization |
| Mở cổng nhưng ứng dụng vẫn lỗi | TCP kết nối được nhưng TLS/HTTP thất bại | Kiểm tra DNS, TLS, xác thực, quyền API, health ứng dụng |
| Bỏ sót DNS/DHCP/NTP/ICMPv6 | Lỗi phân giải tên, cấp địa chỉ, đồng bộ thời gian hoặc IPv6 | Liệt kê luồng nền tảng trước khi áp dụng default deny |
| Rule tạm không có owner/hạn dùng | Quy tắc mở rộng tồn tại nhiều năm | Gắn ticket, expiry/review date và tự động cảnh báo |
| Bật log mọi gói khối lượng lớn | Log đầy, tốn chi phí, khó tìm sự cố | Chọn lọc rule quan trọng, sampling/rate limit theo nền tảng |

Phân biệt hành động **DROP** (thường loại bỏ im lặng) và **REJECT** (có thể gửi phản hồi từ chối, tùy giao thức/sản phẩm). Vì vậy, một phép thử bị **timeout** có thể là do drop, mất kết nối hoặc sai route; lỗi **connection refused** có thể do dịch vụ không lắng nghe hoặc cơ chế reject. Không kết luận nguyên nhân chỉ từ một thông báo ở client.

### 8.1. Vì sao ping không đủ để xác minh ACL?

Lệnh ping thường gửi ICMP Echo, trong khi truy cập website sử dụng TCP/443 hoặc HTTP/3 qua UDP/443. Ping thành công **không chứng minh** TCP/443 được phép; ping thất bại cũng **không chứng minh** dịch vụ HTTPS không truy cập được. Khi kiểm tra, phải dùng đúng giao thức, địa chỉ đích và cổng của luồng cần bảo vệ.

### 8.2. Một rule chỉ mở được kết nối, chưa xác thực người dùng

Giả sử rule cho phép toàn bộ 10.20.10.0/24 gọi API TCP/443. Một thiết bị bị lộ hoặc một người dùng không có quyền nhưng ở trong subnet này vẫn có thể **thiết lập kết nối tới API**. Ứng dụng phải xác thực và phân quyền trên từng request; chỉ dựa vào IP nguồn có thể bị vượt qua bởi thiết bị bị xâm nhập, NAT hoặc thay đổi topology.

## 9. Kiểm chứng và khắc phục sự cố theo từng lớp

Một phép thử tốt gồm **kiểm tra luồng phải được cho phép** và **kiểm tra luồng phải bị từ chối**. Thực hiện từ các máy thử nghiệm và vùng mạng **đã được cho phép kiểm tra**, không quét hệ thống bên ngoài phạm vi.

### 9.1. Bài thử kết nối phù hợp

Trên Windows PowerShell, có thể kiểm tra TCP đến host trong lab:

~~~powershell
Test-NetConnection -ComputerName 10.20.20.10 -Port 443
Test-NetConnection -ComputerName 10.20.40.10 -Port 5432
~~~

Kết quả kỳ vọng nếu chạy **từ User VLAN**:

- TCP/443 tới reverse proxy: **được phép** qua chính sách mạng, nếu dịch vụ và tuyến hoạt động.
- TCP/5432 tới database: **bị chặn** theo chính sách, trừ khi có đường/quy tắc khác ngoài mô hình.

Để kiểm tra HTTP/HTTPS và chứng chỉ từ client, có thể dùng một hostname lab đã được cấu hình chứng chỉ đúng và phân giải tới địa chỉ cần thử:

~~~bash
curl --resolve app.example.test:443:10.20.20.10 \
  --connect-timeout 5 --head https://app.example.test/health
~~~

Lệnh minh họa này chỉ thành công khi có máy chủ lab, endpoint và **chứng chỉ hợp lệ với app.example.test**. Nếu chứng chỉ chưa được tin cậy, cần cấu hình CA/chứng chỉ thử nghiệm phù hợp; **không tắt xác minh TLS** để làm kết quả trông thành công. Kiểm tra HTTP/3 cần công cụ và server hỗ trợ QUIC, đồng thời kiểm tra chính sách **UDP/443** riêng.

### 9.2. Quy trình tìm nguyên nhân

~~~mermaid
flowchart TD
    A["Luồng kết nối thất bại"] --> B{"Địa chỉ và DNS đúng?"}
    B -- "Không" --> B1["Kiểm tra resolver / địa chỉ đích"]
    B -- "Có" --> C{"Tuyến đi/về hợp lệ?"}
    C -- "Không" --> C1["Kiểm tra route, NAT, next hop"]
    C -- "Có" --> D{"Rule tại mọi điểm thực thi cho phép?"}
    D -- "Không" --> D1["Kiểm tra hướng, priority, CIDR, protocol, port"]
    D -- "Có" --> E{"Stateful/return path hợp lệ?"}
    E -- "Không" --> E1["Kiểm tra chiều phản hồi và bảng trạng thái"]
    E -- "Có" --> F{"Dịch vụ / TLS / quyền ứng dụng đúng?"}
    F -- "Không" --> F1["Kiểm tra listener, chứng chỉ, HTTP status, auth"]
    F -- "Có" --> G["Đối chiếu log và bằng chứng quan sát"]
~~~

Các bước chẩn đoán hữu ích:

1. **Xác minh 5-tuple thực tế**: IP nguồn, cổng nguồn, IP đích, cổng đích, giao thức. Đối với ICMP cần lưu ý thông tin loại/type thay vì cổng.
2. **Kiểm tra định tuyến và NAT**: route của cả hai chiều, địa chỉ trước/sau khi dịch, đường đi qua firewall hoặc proxy.
3. **Xem effective policy** tại từng điểm lọc: ACL interface, subnet ACL, security group, host firewall, Kubernetes policy nếu có; xác nhận rule ưu tiên và default.
4. **Xem hit counter, flow log và log từ chối** nếu sản phẩm hỗ trợ; bộ đếm không tăng có thể do lưu lượng không đến điểm kiểm tra hoặc khớp rule khác.
5. **Xem phiên và trạng thái TCP**: SYN, SYN-ACK, ACK trong trace được phép; state timeout hoặc asymmetric path có thể gây thất bại.
6. **Kiểm tra dịch vụ**: port listening, chứng chỉ TLS, mTLS, HTTP status, DNS và quyền ứng dụng.
7. **So sánh kỳ vọng với thực tế** và ghi nguyên nhân; chỉ sửa rule sau khi đã xác định rõ luồng và phạm vi cần thay đổi.

**Lưu ý giám sát:** lưu lượng có thể bị chặn ở lớp mạng khiến ứng dụng **không có access log**. Ngược lại, access log có request không chứng minh mọi điểm mạng đã được cấu hình đúng cho các luồng khác. Cần kết hợp flow log, firewall logs, IDS/IPS, telemetry ứng dụng và sơ đồ đường đi.

### 9.3. Bảng kết quả thử nghiệm mẫu

| Test | Vị trí phát | Luồng | Mong đợi | Cần ghi nhận |
| --- | --- | --- | --- | --- |
| T01 | User VLAN | TCP tới proxy:443 | ALLOW | Kết nối thành công; chứng chỉ/HTTP hợp lệ |
| T02 | User VLAN | TCP tới DB:5432 | DENY | Không lập được kết nối; rule deny/hit log nếu có |
| T03 | Proxy | TCP tới API:8443 | ALLOW | TCP và kiểm tra TLS/mTLS nếu thiết kế yêu cầu |
| T04 | User VLAN | TCP tới API:8443 trực tiếp | DENY | Không có đường truy cập bỏ qua reverse proxy |
| T05 | App API | TCP tới DB:5432 | ALLOW | Kết nối ứng dụng có tài khoản/quyền đúng |
| T06 | Mạng khách | TCP tới bastion/SSH | DENY | Không truy cập được cổng quản trị |
| T07 | User VLAN | UDP/TCP tới DNS:53 | ALLOW | Resolver hoạt động và trả lời theo chính sách |
| T08 | Internet giả lập trong lab | TCP tới API:8443 | DENY | Không công khai backend |

Kết quả trên là **kỳ vọng của mô hình**. Phải ghi cả **thực tế, thời điểm, điểm đặt rule, nguồn/đích, người kiểm tra và bằng chứng** để có thể tái kiểm tra sau mỗi lần thay đổi.

## 10. Vận hành ACL an toàn

### 10.1. Vòng đời một thay đổi

Một quy tắc nên được xem là thay đổi cấu hình cần quản lý:

1. **Yêu cầu:** mô tả nghiệp vụ, chủ sở hữu, nguồn, đích, giao thức, cổng, môi trường, thời hạn và độ nhạy dữ liệu.
2. **Đánh giá:** xem mức mở rộng quyền; kiểm tra nguồn đáng tin cậy, ranh giới tin cậy, IPv4/IPv6 và rule hiện có.
3. **Thiết kế:** ưu tiên allowlist nhỏ, quy tắc có tên và mô tả, thứ tự phù hợp, thời hạn cho ngoại lệ.
4. **Phê duyệt theo quy trình tổ chức:** rà soát tác động bảo mật và nguy cơ gián đoạn.
5. **Triển khai có kiểm soát:** kiểm tra cú pháp, tạo backup và phương án rollback; dùng infrastructure as code và review thay đổi nếu hệ thống hỗ trợ.
6. **Xác minh:** thử cả luồng được phép và bị chặn; theo dõi lỗi, rule hit và tác động vận hành.
7. **Rà soát định kỳ:** loại quy tắc không còn dùng, đối chiếu chủ sở hữu và bằng chứng nghiệp vụ; xem xét phạm vi quá rộng.

Trong sản xuất, **default deny** cần triển khai theo giai đoạn nếu trước đó mạng đang mở rộng. Việc chặn ngay mọi luồng chưa biết có thể gián đoạn DNS, cập nhật bảo mật, hệ thống giám sát, cơ sở dữ liệu hoặc kết nối quản trị. Thu thập luồng cần thiết và chuẩn bị đường quản trị/rollback trước khi siết chặt.

### 10.2. Một bản ghi rule dễ kiểm toán

| Trường | Giá trị minh họa |
| --- | --- |
| Rule ID | ACL-APP-104 |
| Người phụ trách | Nhóm vận hành ứng dụng |
| Lý do | Reverse proxy phải gọi API |
| Source | 10.20.20.10/32 |
| Destination | 10.20.30.10/32 |
| Protocol/port | TCP/8443 |
| Direction/point | Theo ingress của vùng API |
| Action | ALLOW |
| Phê duyệt / ticket | Tham chiếu thay đổi nội bộ |
| Ngày rà soát | Theo kỳ rà soát chính sách |
| Bằng chứng | Luồng proxy → API thành công; user → API bị từ chối |

Không cần ghi thông tin mật như mật khẩu hoặc khóa riêng vào mô tả ACL hay ticket. Khi dùng automation, nên bảo vệ credential của công cụ triển khai và kiểm tra cấu hình trước khi thay đổi.

## 11. Tình huống phân tích và bài tập

### Tình huống A: Website hoạt động nhưng API không nhận request

Nhân viên gọi web qua TCP/443 thành công, nhưng reverse proxy báo lỗi gateway khi liên lạc App API ở TCP/8443. Giả sử app lắng nghe đúng cổng và DNS phân giải chính xác.

**Hướng phân tích:** truy dấu gói từ IP proxy tới IP API, kiểm tra effective ACL ở egress proxy và ingress API, rule 8443, đường phản hồi và trạng thái firewall. Nếu sử dụng stateless ACL, cần xét cả chiều API trả lời về proxy. Chỉ sau khi xác nhận kết nối TCP đã thành công mới chuyển sang kiểm tra TLS giữa proxy và API.

### Tình huống B: Người dùng bất ngờ truy cập được database

Mặc dù có rule DENY User VLAN → DB, một máy người dùng vẫn kết nối được TCP/5432. Nguyên nhân giả định là ALLOW 10.20.0.0/16 → 10.20.40.0/24 đã đứng trước rule DENY cụ thể trên một firewall theo first match.

**Hướng xử lý:** xem thứ tự và rule khớp thực tế; thu hẹp hoặc bỏ rule ALLOW rộng sau khi xác định các luồng hợp lệ, rồi thử lại các trường hợp user → DB bị chặn và app → DB được phép. Kiểm tra thêm policy tại host, dịch địa chỉ và đường mạng có đi qua firewall hay không.

### Tình huống C: Sau khi siết egress, server không truy cập được dịch vụ cloud

Một workload xử lý đơn hàng không còn tải bản cập nhật hoặc gửi cảnh báo tới endpoint cloud, trong khi policy default deny vừa được áp dụng.

**Hướng xử lý:** đối chiếu luồng cần thiết, DNS, địa chỉ endpoint động, chính sách egress và nhu cầu qua proxy/NAT. Chỉ mở endpoint, giao thức và cổng đáp ứng mục tiêu; không mặc định sửa lỗi bằng ALLOW ANY → ANY.

### Câu hỏi tự kiểm tra

1. **ACL có ngăn người dùng đã truy cập được API đọc đơn hàng của người khác không?**
   Không tự động. API phải xác thực và kiểm tra quyền truy cập từng tài nguyên; ACL chỉ giới hạn luồng kết nối tại điểm thực thi.

2. **Một rule ALLOW TCP/443 cho request trên stateless ACL có đủ cho TCP phản hồi không?**
   Không nhất thiết. Phải kiểm tra rule chiều trả lời, cổng nguồn/đích, dải cổng tạm thời và vị trí áp dụng ACL.

3. **Đặt DENY ANY trước ALLOW cụ thể trong ACL first match gây gì?**
   Rule DENY có thể khớp trước khiến rule ALLOW không bao giờ được áp dụng.

4. **Chặn 0.0.0.0/0 có tự chặn IPv6 không?**
   Không. IPv6 cần chính sách riêng theo cú pháp và hành vi của nền tảng, ví dụ ::/0.

5. **Vì sao dùng VPN không thay thế Network ACL?**
   VPN bảo vệ/kết nối người dùng vào mạng, nhưng ACL hoặc chính sách tương đương vẫn cần giới hạn dịch vụ và vùng mà phiên VPN được tiếp cận.

6. **Có thể dùng ping để khẳng định cổng SSH được mở không?**
   Không. Ping thông thường dùng ICMP, còn SSH dùng TCP/22; cần thử đúng luồng.

### Bài tập thực hành tổng hợp

Thiết kế ACL cho hệ thống gồm **User VLAN**, **Guest Wi-Fi**, **DMZ**, **App**, **Database**, **Admin VPN/Bastion** và **DNS Resolver**. Yêu cầu: người dùng chỉ truy cập HTTPS qua DMZ, App chỉ truy cập DB đúng cổng, mạng khách không tiếp cận nội bộ, quản trị chỉ đi qua bastion, mọi vùng mặc định từ chối kết nối không được liệt kê.

Hãy nộp:

- Một sơ đồ có các vùng và **điểm thực thi** ACL.
- Ma trận ít nhất tám luồng (allow và deny), ghi nguồn, đích, protocol, cổng và hướng.
- Mô tả cách xử lý chiều phản hồi đối với **stateless** và **stateful**.
- Ít nhất năm test case có cả đường được phép và đường bị chặn, kèm kết quả dự kiến.
- Hai rủi ro còn lại mà ACL **không giải quyết** và biện pháp bổ sung (ví dụ dữ liệu ứng dụng bị lộ do quyền API, credential bị đánh cắp).

## 12. Các nguyên tắc cần ghi nhớ

- **Network ACL là kiểm soát lưu lượng tại một vị trí cụ thể**: luôn xác định điểm áp dụng, hướng, IP nguồn/đích, giao thức, cổng và ưu tiên của rule.
- **Least privilege và default deny** là mục tiêu thiết kế; cần biết hành vi khớp quy tắc và mặc định của sản phẩm đang dùng.
- **Stateless** thường cần cho phép request và response tường minh; **stateful** có thể tự cho phép lưu lượng phản hồi của kết nối đã theo dõi.
- **ACL, routing, NAT, TLS, IAM và quyền ứng dụng** là các cơ chế khác nhau, phối hợp để tạo đường kết nối vừa hoạt động vừa an toàn.
- Luôn kiểm tra **IPv4/IPv6, luồng quản trị, DNS, cổng tạm thời, QUIC/UDP, mạng khách, egress và log** trước khi tuyên bố chính sách hoàn chỉnh.
- Quy tắc cần có **lý do, owner, phạm vi, thời hạn/rà soát, kiểm thử và khả năng rollback**. Giám sát phải phát hiện sai cấu hình và thay đổi ngoài dự kiến.
