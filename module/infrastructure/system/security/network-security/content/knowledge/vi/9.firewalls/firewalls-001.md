# Packet filtering firewall

**Packet filtering firewall** (tường lửa lọc gói) là cơ chế bảo mật mạng cho phép hoặc từ chối lưu lượng bằng cách kiểm tra thông tin của từng gói tin và đối chiếu với các quy tắc (*rules*) đã được định nghĩa. Những trường thường dùng gồm địa chỉ IP nguồn/đích, giao thức TCP/UDP/ICMP, cổng nguồn/đích, interface và hướng lưu lượng. Khi một gói phù hợp với chính sách, tường lửa thực thi hành động tương ứng.

Ví dụ, hệ thống đặt hàng có API và cơ sở dữ liệu PostgreSQL. Cơ sở dữ liệu chỉ nên nhận kết nối từ API trên TCP 5432; máy khách, mạng Wi-Fi khách và Internet không được truy cập trực tiếp. Packet filtering firewall là một cách thực thi ranh giới kết nối đó.

Trong module **SECURITY_NETWORK_SECURITY**, hiểu đúng lọc gói là nền tảng để thiết kế phân đoạn mạng, chính sách firewall, đường truy cập VPN, giám sát IDS/IPS, bảo vệ DNS, Wi-Fi và các workload trong cloud. Tuy nhiên, bộ lọc dựa trên header không tự xác thực người dùng, đánh giá quyền đối với từng API hay phân tích nội dung ứng dụng đã mã hóa. Nó là **một lớp phòng vệ** cần kết hợp với các lớp khác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích packet filtering hoạt động ở lớp mạng và giao vận như thế nào.
2. Xác định những trường header thường xuất hiện trong một rule.
3. Phân biệt packet filtering **stateless** và firewall kiểm tra **trạng thái kết nối** (*stateful*).
4. Đọc và thiết kế chính sách dựa trên nguồn, đích, giao thức/cổng, hướng, thứ tự rule và hành động mặc định.
5. Lập ma trận allow/deny cho một hệ thống nhiều trust zone và chuyển thành chính sách trung lập với nhà cung cấp.
6. Giải thích các lưu ý thực tế về NAT, IPv4/IPv6, phân mảnh, DNS, ICMP, định tuyến và lưu lượng phản hồi.
7. Xây dựng phép kiểm thử được phép và phân tích log để xác nhận firewall thực sự hoạt động theo thiết kế.

## 2. Firewall lọc gói quan sát thông tin nào?

Các rule truyền thống chủ yếu áp dụng trên những thông tin ở lớp 3 và lớp 4 trong mô hình OSI:

| Trường | Ví dụ | Vai trò trong chính sách |
| --- | --- | --- |
| IP nguồn | 10.20.20.15 | Xác định máy hoặc nhóm mạng khởi tạo |
| IP đích | 10.20.30.5 | Giới hạn tài nguyên nhận kết nối |
| Giao thức IP | TCP, UDP, ICMP, ICMPv6 | Phân biệt kiểu lưu lượng cần đánh giá |
| Cổng nguồn | TCP 52000 | Đầu cuối nguồn của kết nối TCP/UDP |
| Cổng đích | TCP 443, TCP 5432, UDP 53 | Dịch vụ mạng được yêu cầu |
| Cờ TCP | SYN, ACK, RST | Phục vụ điều kiện lọc có hỗ trợ, nhưng không tự chứng minh trạng thái kết nối |
| Interface/zone | WAN, DMZ, application, data | Xác định ranh giới và hướng gói đi qua |
| Loại và mã ICMP | Echo, Destination Unreachable, Packet Too Big | Kiểm soát thông điệp điều khiển hoặc báo lỗi mạng khi hỗ trợ |

**ICMP không có khái niệm cổng TCP/UDP.** Giao thức này dùng các loại thông điệp (*type*) và mã (*code*). IPv6 còn cần một số loại ICMPv6 cho Neighbor Discovery và Path MTU Discovery. Chặn toàn bộ ICMP hoặc ICMPv6 có thể khiến kết nối bị lỗi, dù các rule TCP/UDP đã cho phép.

Một gói mở kết nối TCP tới API có thể được diễn tả:

~~~text
Source IP:         10.20.10.10
Destination IP:    10.20.20.15
Protocol:          TCP
Source port:       52000
Destination port:  8443
TCP flags:         SYN
Direction:         DMZ -> Application
~~~

Tường lửa lọc gói có thể kiểm tra các trường này để quyết định **có cho phép kết nối ở mức mạng hay không**. Từ đây không thể suy ra yêu cầu HTTP là GET hay POST, người dùng được phép xem đơn hàng nào hoặc API có đang xử lý dữ liệu đúng quy tắc.

## 3. Cách packet filtering firewall ra quyết định

Một mô hình đơn giản gồm:

1. Gói tới điểm thực thi chính sách như firewall biên, router ACL hoặc host firewall.
2. Hệ thống xác định interface, zone, hướng lưu lượng và các trường header liên quan.
3. Gói được so với những rule có hiệu lực theo cơ chế đánh giá của nền tảng.
4. Hệ thống cho qua, loại bỏ, từ chối có phản hồi hoặc xử lý theo action được cấu hình.
5. Nếu không có rule khớp, chính sách mặc định hoặc kết thúc chuỗi quyết định kết quả.

~~~mermaid
flowchart TD
    A["Gói tin tới điểm kiểm soát"] --> B["Nhận diện interface / hướng / zone"]
    B --> C["Phân tích IP, giao thức và cổng"]
    C --> D{"Khớp rule có hiệu lực?"}
    D -->|Có| E{"Action"}
    E -->|Allow| F["Cho phép xử lý / chuyển tiếp"]
    E -->|Drop| G["Loại bỏ gói"]
    E -->|Reject| H["Từ chối có phản hồi nếu hỗ trợ"]
    D -->|Không| I["Áp dụng chính sách mặc định"]
    F --> L["Ghi log / đếm lưu lượng nếu cấu hình"]
    G --> L
    H --> L
    I --> L
~~~

Đây là **sơ đồ khái niệm**: các firewall thực tế có thể xử lý NAT, kiểm tra trạng thái, chuyển tiếp phần cứng, chính sách bổ sung và ghi log ở những giai đoạn khác nhau. Không thể áp dụng cùng thứ tự cho mọi sản phẩm.

### 3.1. Các hành động

| Hành động | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Allow / Accept | Cho phép gói đi tiếp theo quá trình xử lý mạng | Không đồng nghĩa dịch vụ hoặc quyền ứng dụng hợp lệ |
| Drop | Loại bỏ gói, thường không gửi phản hồi từ rule | Client có thể timeout, nhưng timeout không chỉ do firewall |
| Reject | Từ chối và có thể trả lỗi ICMP hoặc TCP reset | Cách trả lời phụ thuộc giao thức và nền tảng |
| Log | Ghi thông tin về kết quả lọc | Có thể kết hợp action hoặc dùng quy tắc riêng |
| Rate limiting / hành động khác | Giới hạn tốc độ hay thao tác nâng cao | Chỉ có khi sản phẩm hỗ trợ; không phải mọi bộ lọc gói đều có |

Không nên coi drop im lặng là phương án luôn tốt hơn reject: việc chọn phản hồi cần phù hợp mục tiêu bảo mật và khả năng chẩn đoán sự cố.

## 4. Thành phần của một rule hiệu quả

Một rule nên trả lời được: **ai khởi tạo, muốn đến đâu, dùng giao thức/cổng gì, đi qua ranh giới nào, được thực hiện hành động gì và vì sao?**

~~~text
ALLOW source=10.20.20.15
      destination=10.20.30.5
      protocol=TCP
      destination-port=5432
      direction=Application-to-Data
      reason=Order-API-needs-PostgreSQL

DENY  source=10.20.50.0/24
      destination=10.20.99.0/24
      protocol=ANY
      direction=Guest-to-Management
      reason=Protect-administration-zone
~~~

Đây là **ký pháp giải thích**, không phải cú pháp firewall thực tế. Tùy thiết bị, rule còn chứa ưu tiên, interface, đối tượng nguồn/đích, lịch, trạng thái, tag và tùy chọn ghi log.

### 4.1. Nguồn và đích nên cụ thể

Rule cho phép toàn bộ DMZ tới toàn bộ mạng nội bộ tạo phạm vi truy cập rộng hơn cần thiết. Tốt hơn là cho phép đúng reverse proxy tới đúng API trên cổng dịch vụ đã chỉ định. Nhờ vậy, nếu một máy khác trong DMZ bị chiếm quyền, nó không tự có đường đi giống reverse proxy.

### 4.2. Phân biệt cổng nguồn và cổng đích

Khi client kết nối tới PostgreSQL:

~~~text
Yêu cầu: 10.20.20.15:52000 -> 10.20.30.5:5432 TCP
Phản hồi: 10.20.30.5:5432 -> 10.20.20.15:52000 TCP
~~~

Cổng 5432 là **cổng đích ở chiều yêu cầu** nhưng là **cổng nguồn ở chiều phản hồi**. Cổng 52000 của client là cổng tạm thời, thay đổi theo kết nối. Vì vậy, thiết kế lọc stateless phải xét cẩn thận quy tắc theo cả hai chiều.

### 4.3. Đặt tên và quản lý vòng đời rule

Mỗi rule sản xuất nên có chủ sở hữu, lý do nghiệp vụ, ticket thay đổi, mức ưu tiên, ngày rà soát và thời hạn nếu là ngoại lệ tạm. Tên có nghĩa như allow-order-api-to-postgres dễ đánh giá hơn một chuỗi số khó hiểu. Những rule không còn nhu cầu phải được rà soát để thu hồi có kiểm soát.

## 5. Thứ tự rule và default policy

Nhiều firewall và ACL dùng cơ chế **first match**: gói gặp rule đầu tiên khớp điều kiện thì thực hiện action ở đó. Các hệ thống khác có chuỗi, ưu tiên hoặc cấu trúc xử lý riêng, nên **phải kiểm tra tài liệu nền tảng**.

Giả sử một chuỗi dùng first match:

| Thứ tự | Điều kiện | Action |
| --- | --- | --- |
| 1 | API 10.20.20.15 đến DB 10.20.30.5, TCP 5432 | Allow |
| 2 | Mọi nguồn khác đến DB 10.20.30.5, TCP 5432 | Deny |
| 3 | Guest đến management zone | Deny |
| Cuối | Lưu lượng chưa được khai báo | Deny mặc định |

Nếu một rule allow rộng được đặt trước rule deny cụ thể, rule chặn có thể không bao giờ được xét. Ngược lại, một rule deny-all đặt sai vị trí có thể làm các rule allow phía dưới không còn hiệu lực. Đó là lý do phải xét **thứ tự và logic đánh giá**, không chỉ kiểm tra một rule có tồn tại.

**Default deny** nghĩa là các luồng chưa được phê duyệt bị từ chối. Đây là nguyên tắc thường phù hợp với vùng quan trọng, nhưng cần kiểm kê các luồng hợp lệ như DNS, NTP, cập nhật, sao lưu và quản trị trước khi triển khai để tránh gián đoạn. **Default allow** có thể thuận tiện trong một số giai đoạn vận hành nhưng để lại các đường kết nối không được chủ động xét duyệt.

## 6. Stateless packet filtering và stateful inspection

### 6.1. Stateless filtering

**Stateless packet filter** đánh giá gói dựa trên rule và các trường hiện có **mà không dùng bảng theo dõi phiên đã được tạo từ những gói trước**.

Ưu điểm là logic lọc theo header rõ ràng và có thể triển khai trên ACL đơn giản, router hoặc các điểm lọc chuyên dụng. Tuy nhiên, bộ lọc stateless không tự biết gói phản hồi có thuộc kết nối mà client đã khởi tạo không; phải thiết kế riêng các điều kiện phản hồi.

**Không được coi TCP ACK flag là bằng chứng chắc chắn của một phiên đã thiết lập.** Cờ trong header là dữ liệu của một gói; một gói có ACK không chứng minh được firewall từng thấy quá trình bắt tay TCP.

### 6.2. Stateful inspection

**Stateful firewall** theo dõi ngữ cảnh và trạng thái kết nối, thường thông qua *connection tracking*. Khi thấy yêu cầu khởi tạo phù hợp chính sách, firewall có thể ghi nhận luồng và cho phép gói phản hồi tương ứng theo trạng thái thay vì mở quyền khởi tạo kết nối mới theo chiều ngược lại.

~~~mermaid
sequenceDiagram
    participant C as Client 10.20.20.15
    participant F as Stateful firewall
    participant S as Database 10.20.30.5
    C->>F: SYN đến TCP 5432
    Note over F: Kiểm tra rule cho luồng khởi tạo
    F->>S: SYN được phép
    S-->>F: SYN-ACK về cổng tạm của client
    Note over F: Đối chiếu bản ghi trạng thái
    F-->>C: Chuyển gói phản hồi
    C->>F: ACK và lưu lượng tiếp theo
    F->>S: Xử lý theo policy/trạng thái
~~~

Với UDP, không có quá trình bắt tay tương đương TCP. Firewall có thể sử dụng thông tin cặp endpoint và bộ đếm thời gian để theo dõi luồng UDP một cách quy ước. Thông điệp ICMP liên quan tới một luồng cũng có thể được xử lý theo trạng thái khi nền tảng hỗ trợ.

| Tiêu chí | Stateless | Stateful |
| --- | --- | --- |
| Cơ sở quyết định | Trường gói hiện tại và rule | Trường gói, rule và trạng thái luồng |
| Xử lý lưu lượng phản hồi | Cần điều kiện lọc chiều về | Có thể khớp bản ghi kết nối |
| Tài nguyên lưu trạng thái | Không duy trì state table kiểu connection tracking | Cần bảng trạng thái và timeout |
| Khả năng hiểu nội dung API | Không | Vẫn không, nếu chỉ bổ sung state tracking |
| Rủi ro vận hành | Rule chiều về thiếu hoặc quá rộng | Hết hạn state, đường bất đối xứng, bảng trạng thái đầy |

**Stateful firewall cũng thực hiện packet filtering.** Sự phân biệt ở đây là giữa lọc gói thuần theo header và việc bổ sung nhận biết trạng thái kết nối; không nên đồng nhất mọi packet filtering firewall với stateless.

## 7. Kiến trúc ví dụ: bảo vệ hệ thống đặt hàng

Giả sử mạng doanh nghiệp được chia thành:

| Zone | Dải IPv4 minh họa | Thành phần |
| --- | --- | --- |
| DMZ | 10.20.10.0/24 | Reverse proxy 10.20.10.10 |
| Application | 10.20.20.0/24 | Order API 10.20.20.15 |
| Data | 10.20.30.0/24 | PostgreSQL 10.20.30.5 |
| Guest/IoT | 10.20.50.0/24 | Thiết bị khách, thiết bị ít được quản lý |
| Management | 10.20.99.0/24 | Bastion 10.20.99.10 và công cụ vận hành |

~~~mermaid
flowchart LR
    U["Internet / khách"] -->|"HTTPS 443"| E{"Edge filtering"}
    E --> W["DMZ / Reverse proxy"]
    W -->|"HTTPS 8443"| A{"DMZ-App filtering"}
    A --> API["Application / Order API"]
    API -->|"PostgreSQL TCP 5432"| D{"App-Data filtering"}
    D --> DB[("Data / PostgreSQL")]
    M["Management / Bastion"] -->|"SSH 22 được duyệt"| F{"Admin filtering"}
    F --> API
    G["Guest / IoT"] -. "Không được vào Data/Admin" .-> X["Deny"]
~~~

Các hình thoi thể hiện **điểm thực thi chính sách logic**, có thể là nhiều loại firewall/ACL/security group hoặc host firewall phối hợp. Sơ đồ không ngụ ý mỗi hình cần một thiết bị vật lý.

### 7.1. Ma trận luồng truy cập

| Nguồn khởi tạo | Đích | Dịch vụ | Kỳ vọng | Ghi chú |
| --- | --- | --- | --- | --- |
| Internet | Điểm công bố web DMZ | TCP 443 | Allow | Bảo vệ TLS và endpoint ở lớp ứng dụng |
| Reverse proxy 10.20.10.10 | API 10.20.20.15 | TCP 8443 | Allow có điều kiện | Chỉ proxy được phê duyệt |
| API 10.20.20.15 | DB 10.20.30.5 | TCP 5432 | Allow có điều kiện | Chỉ tài khoản DB có quyền tối thiểu |
| Bastion 10.20.99.10 | API host được quản trị | TCP 22 | Allow có điều kiện | Tài khoản và phiên quản trị được kiểm soát |
| Dịch vụ nội bộ có nhu cầu | Resolver DNS được duyệt | UDP/TCP 53 | Allow có điều kiện | Giới hạn đích DNS, không mở tùy ý |
| DMZ | Data zone | Mọi luồng chưa được duyệt | Deny | Không cho bypass API |
| Guest/IoT | Management/Data | Mọi dịch vụ | Deny | Giảm đường di chuyển ngang |
| Internet | Database | Mọi dịch vụ | Deny | Không công bố trực tiếp |
| Mọi luồng còn lại | Bất kỳ | Bất kỳ | Deny mặc định | Chỉ mở nhu cầu đã rõ |

Việc cho phép TCP 8443 không thay thế **xác thực và phân quyền API**. Tương tự, TCP 5432 được mở không có nghĩa mọi truy vấn cơ sở dữ liệu đều được phép.

### 7.2. Chính sách mô tả trung lập với nhà cung cấp

~~~yaml
firewallPolicy:
  name: order-service-isolation
  defaultAction: deny
  rules:
    - name: public-to-proxy
      source: internet
      destination: dmz/reverse-proxy
      protocol: tcp
      destinationPort: 443
      action: allow
      purpose: public-https

    - name: proxy-to-api
      source: dmz/reverse-proxy
      destination: application/order-api
      protocol: tcp
      destinationPort: 8443
      action: allow
      purpose: order-requests

    - name: api-to-db
      source: application/order-api
      destination: data/postgresql
      protocol: tcp
      destinationPort: 5432
      action: allow
      purpose: order-data

    - name: bastion-to-api-host
      source: management/bastion
      destination: application/api-host
      protocol: tcp
      destinationPort: 22
      action: allow
      purpose: authorized-ssh

    - name: guest-to-management
      source: guest
      destination: management
      protocol: any
      action: deny
      purpose: guest-isolation
~~~

Đây là **tài liệu mô hình hóa**, không phải cú pháp có thể nạp trực tiếp cho một thiết bị. Khi triển khai phải ánh xạ các zone và đối tượng thành địa chỉ thực; tính đến interface, hành vi stateful/stateless, rule order, NAT và đường đi của lưu lượng.

## 8. Chiều vào, chiều ra và kết nối giữa các zone

- **Ingress:** lưu lượng đi vào một interface, zone hoặc workload theo góc nhìn của điểm thực thi.
- **Egress:** lưu lượng đi ra từ interface, zone hoặc workload đó.
- **North–south:** lưu lượng từ bên ngoài đi vào hệ thống và chiều ngược lại.
- **East–west:** lưu lượng giữa các server, workload hoặc phân đoạn nội bộ.

Cùng một gói có thể là **egress tại zone nguồn** và **ingress tại zone đích**. Khi viết tài liệu rule, hãy ghi rõ điểm nhìn thay vì dùng câu chung chung “mở cổng 443” mà không nêu chiều.

Không chỉ kiểm soát kết nối từ Internet vào. Nếu data zone không có nhu cầu truy cập Internet trực tiếp, egress của database cũng nên được giới hạn. DNS, đồng bộ thời gian, cập nhật và hệ thống thu thập log cần được khai báo như các luồng hợp lệ cụ thể.

Với stateless ACL, gói phản hồi phải khớp điều kiện chiều về theo thiết kế. Với stateful firewall, gói phản hồi thường được đánh giá dựa trên connection tracking, nhưng vẫn phải kiểm tra routing, timeout và các trường hợp có nhiều firewall trên đường đi.

## 9. NAT, phân mảnh, IPv6 và định tuyến

### 9.1. NAT: địa chỉ trước và sau dịch

**NAT** có thể thay đổi IP hoặc cổng nguồn/đích. Một kết nối tới public IP của web gateway có thể được DNAT về máy ở DMZ; lưu lượng ra ngoài có thể đi qua SNAT. Tùy nền tảng, firewall rule được đánh giá với địa chỉ **trước NAT hoặc sau NAT** ở những giai đoạn khác nhau.

Để không cấu hình sai, cần xác định chính xác nơi xử lý NAT, trường nào xuất hiện trong log và gói mang địa chỉ nào tại điểm lọc. Không nên chuyển rule giữa hai hãng firewall bằng cách sao chép IP mà bỏ qua thứ tự NAT/filter.

### 9.2. Phân mảnh IP

Trong IPv4, những mảnh sau mảnh đầu có thể không chứa đầy đủ header TCP/UDP. Một thiết bị chỉ kiểm tra cổng sẽ gặp giới hạn nếu đánh giá từng mảnh độc lập. Một số firewall có cơ chế xử lý phân mảnh, tái lắp ghép hoặc theo dõi trạng thái mảnh; khả năng và hành vi khác nhau theo sản phẩm.

IPv6 xử lý phân mảnh theo cơ chế extension header riêng. Rule IPv6 cần xét cách thiết bị phân tích chuỗi extension header và xử lý các gói bị phân mảnh. Không được mặc định một rule IPv4 sẽ kiểm soát cả lưu lượng IPv6.

### 9.3. ICMP và ICMPv6

ICMP phục vụ báo lỗi và kiểm tra mạng, không chỉ ping. Cần có chính sách hợp lý cho các thông điệp phục vụ **Path MTU Discovery** và chức năng mạng thiết yếu. Với IPv6, Neighbor Discovery dựa vào ICMPv6 là thành phần quan trọng tại liên kết. Chặn toàn bộ ICMPv6 có thể gây mất kết nối hoặc lỗi khó phát hiện.

### 9.4. Định tuyến và đường phụ

Policy chỉ có hiệu lực khi gói **thực sự đi qua điểm lọc**. Nếu hai máy trong cùng VLAN trao đổi lớp 2 trực tiếp, firewall ở router có thể không thấy lưu lượng. Một tunnel VPN, mạng ảo, nhiều NIC, peering cloud hoặc tuyến dự phòng có thể tạo đường đi ngoài sơ đồ dự kiến.

Định tuyến bất đối xứng (*asymmetric routing*) có thể làm firewall stateful nhận gói phản hồi mà không có state tương ứng. Khi đó kết nối bị rớt dù rule allow đã tồn tại. Cần xem tuyến đi-về và cơ chế đồng bộ trạng thái, không nên mở rule quá rộng để che lỗi kiến trúc.

## 10. Packet filtering trên các nền tảng

| Nơi áp dụng | Công nghệ thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| Router hoặc switch L3 | Access control list (ACL) | Interface, chiều áp dụng, thứ tự, IPv4/IPv6 |
| Firewall vật lý/ảo | Zone policies, ACL, stateful rules | Trạng thái phiên, NAT, default action, HA/failover |
| Máy chủ | Linux/Windows host firewall | Rule ingress/egress, profile, ứng dụng, quyền sửa rule |
| Cloud VPC/VNet | Network ACL, security group, firewall dịch vụ | Rule có stateful không, route, scope, thứ tự |
| Container/Kubernetes | NetworkPolicy hoặc giải pháp CNI hỗ trợ | Policy được thực thi không, selector, ingress/egress |
| Wi-Fi/IoT | VLAN, ACL tại gateway, policy phân đoạn | Ánh xạ SSID, guest isolation, quyền vào management |
| VPN | ACL/firewall tại gateway, chính sách theo người dùng | Không cho tunnel tạo quyền toàn mạng theo mặc định |

**Không phải mọi security group và network ACL đều có cùng ngữ nghĩa.** Nền tảng cloud thường có cơ chế riêng về stateful/stateless, thứ tự và default action; cần đọc chính sách đúng sản phẩm đang vận hành.

Với Kubernetes, tạo NetworkPolicy không bảo đảm đã có lọc gói nếu plugin mạng chưa hỗ trợ thực thi policy. Lọc mạng cũng không tự mã hóa hoặc cấp quyền thao tác bên trong ứng dụng.

## 11. Ưu điểm và giới hạn

### 11.1. Ưu điểm

- **Đơn giản và có thể kiểm chứng:** rule dựa trên những trường mạng rõ ràng, dễ chuyển từ ma trận truy cập.
- **Linh hoạt về vị trí:** có thể thực thi tại router, gateway, máy chủ, hypervisor hoặc trong cloud.
- **Hạn chế bề mặt kết nối:** giúp cô lập data zone, management zone và mạng khách khi cấu hình đúng.
- **Bổ trợ giám sát:** rule hit counter, allow/deny log và flow data cung cấp tín hiệu về kết nối bị từ chối hoặc đường truy cập bất thường.

### 11.2. Giới hạn

- **Không hiểu đầy đủ nghiệp vụ L7:** cùng TCP 443 có thể chứa yêu cầu hợp lệ hoặc lạm dụng API.
- **Không tự biết danh tính người dùng:** IP có thể qua NAT, proxy, VPN hoặc được cấp phát lại.
- **Không tự khẳng định tính an toàn của nội dung mã hóa:** TLS bảo vệ dữ liệu, nhưng rule IP/cổng không chứng minh phân quyền ứng dụng.
- **Phụ thuộc đường đi:** gói bỏ qua firewall sẽ không chịu rule đặt tại đó.
- **Rule phức tạp dễ phát sinh lỗi:** thứ tự, ngoại lệ, chiều phản hồi, NAT và IPv6 cần được kiểm tra thực tế.
- **Stateless cần thiết kế chiều về:** mở quá rộng để cho phép phản hồi có thể tạo rủi ro không cần thiết.

## 12. Quy trình thiết kế chính sách lọc gói

1. **Kiểm kê tài sản:** xác định máy chủ, workload, ứng dụng, DNS resolver, bastion, kết nối VPN, cloud và chủ sở hữu.
2. **Xác định trust zone:** Internet, DMZ, application, data, management, guest/IoT hoặc các nhóm phù hợp rủi ro.
3. **Lập ma trận nghiệp vụ:** nguồn khởi tạo, đích, cổng/giao thức, lý do và các yêu cầu về danh tính.
4. **Chọn điểm thực thi:** firewall tại tuyến, router ACL, host firewall, security group hay kết hợp để bao phủ cả đường phụ.
5. **Thiết kế thứ tự và mặc định:** đặt rule cụ thể đúng độ ưu tiên, dùng deny mặc định cho kết nối không được khai báo khi triển khai phù hợp.
6. **Giải quyết lưu lượng phản hồi:** xác định stateless/stateful, NAT, timeout, ICMP cần thiết và phụ thuộc DNS/NTP/giám sát.
7. **Kiểm thử có kế hoạch:** đo cả các luồng được phép lẫn bị cấm, kiểm tra IPv4/IPv6 và đường dự phòng.
8. **Triển khai và giám sát:** lưu cấu hình trước thay đổi, giữ phương án rollback, đối chiếu log và tác động hệ thống.
9. **Rà soát vòng đời:** đánh giá quyền thừa, rule không có hit, chủ sở hữu, ngoại lệ tạm và thay đổi kiến trúc.

Rule **allow** không nên được tạo chỉ vì một tiến trình đang phát sinh kết nối. Phải xác minh đó là lưu lượng nghiệp vụ hợp lệ, thay vì cấu hình sai hoặc hành vi bất thường của một tài sản đã bị chiếm quyền.

### 12.1. Những câu hỏi trước khi duyệt rule

| Câu hỏi | Dữ liệu cần có |
| --- | --- |
| Ai yêu cầu? | Chủ dịch vụ hoặc ticket được duyệt |
| Tại sao cần? | Phụ thuộc nghiệp vụ hoặc quản trị cụ thể |
| Nguồn và đích nào? | Host/workload hoặc dải tối thiểu |
| Dịch vụ nào? | Giao thức và cổng, hoặc loại ICMP |
| Chiều nào? | Nguồn khởi tạo, hướng interface/zone |
| Dùng stateless hay stateful? | Cách xử lý phản hồi và timeout |
| Có NAT hoặc tuyến khác? | Địa chỉ tại điểm lọc, route và đường failover |
| Bằng chứng kiểm thử? | Kết quả allow/deny và log liên quan |
| Khi nào rà soát? | Thời hạn, người sở hữu và cách thu hồi |

## 13. Kiểm thử firewall bằng luồng hợp lệ và luồng bị cấm

Chỉ kiểm tra một rule có xuất hiện trong cấu hình **không chứng minh** gói sẽ gặp rule đó. Cần xác minh trên tuyến thực tế, bằng các phép thử **trong phạm vi đã được cho phép**.

| Ca | Nguồn | Đích và dịch vụ | Kết quả mong đợi |
| --- | --- | --- | --- |
| T-01 | Reverse proxy 10.20.10.10 | API 10.20.20.15, TCP 8443 | Được phép theo rule |
| T-02 | Order API 10.20.20.15 | DB 10.20.30.5, TCP 5432 | Được phép với ứng dụng có quyền |
| T-03 | Reverse proxy 10.20.10.10 | DB 10.20.30.5, TCP 5432 | Bị chặn |
| T-04 | Máy Guest/IoT | Bastion 10.20.99.10, TCP 22 | Bị chặn |
| T-05 | Bastion 10.20.99.10 | API host được duyệt, TCP 22 | Được phép sau xác thực |
| T-06 | Máy không thuộc nhóm API | DB 10.20.30.5, TCP 5432 | Bị chặn |
| T-07 | Client có quyền dùng DNS | Resolver được khai báo, UDP/TCP 53 | Hoạt động theo nhu cầu |
| T-08 | Workload có IPv6 | Dịch vụ tương ứng qua IPv6 | Khớp chính sách IPv6 đã duyệt |

### 13.1. Lệnh kiểm tra kết nối trong lab

Trên Windows:

~~~powershell
Test-NetConnection -ComputerName 10.20.20.15 -Port 8443
~~~

Trên Linux nếu đã cài netcat:

~~~bash
nc -vz -w 3 10.20.20.15 8443
~~~

Các lệnh trên **tạo kết nối chủ động** và có thể xuất hiện trong log; chỉ thực hiện trong lab hoặc môi trường được ủy quyền. Kết nối TCP thành công chưa chứng minh API cho phép thao tác. Kết nối thất bại cũng có thể do dịch vụ không lắng nghe, sai tuyến, firewall host hoặc lỗi mạng khác.

### 13.2. Đọc log firewall

Ví dụ sự kiện giả lập:

~~~json
{
  "timestamp": "2026-11-28T09:12:30+07:00",
  "action": "deny",
  "source_zone": "dmz",
  "source_ip": "10.20.10.10",
  "destination_zone": "data",
  "destination_ip": "10.20.30.5",
  "protocol": "tcp",
  "destination_port": 5432,
  "rule_id": "deny-dmz-to-data",
  "description": "Ví dụ minh họa, không phải dữ liệu sản xuất"
}
~~~

Log giúp xác nhận **một sự kiện lọc cụ thể tại điểm quan sát**, không tự chứng minh mọi tuyến đều bị chặn hoặc người gửi có động cơ tấn công. Nếu không thấy log, cần kiểm tra liệu gói có thực sự đi qua thiết bị, rule có bật logging hay không và firewall có giới hạn hoặc lấy mẫu log.

### 13.3. Cách khoanh vùng khi kết quả không đúng kỳ vọng

1. Xác minh IP nguồn/đích, cổng và giao thức đúng chưa.
2. Kiểm tra DNS, route, interface và khả năng lưu lượng đi qua đường khác.
3. Đối chiếu địa chỉ/port trước và sau NAT.
4. Xem thứ tự rule, default action, hit counter và chính sách IPv4/IPv6.
5. Kiểm tra state table, thời gian chờ, đường phản hồi và HA nếu dùng stateful.
6. Kiểm tra host firewall, listener, TLS, xác thực và log ứng dụng.

Không nên mở rộng rule thành allow-any để xử lý một sự cố chưa rõ nguyên nhân. Việc đó có thể khôi phục dịch vụ tạm thời nhưng đồng thời mở đường vượt ranh giới an toàn.

## 14. Lỗi thiết kế và cấu hình thường gặp

| Sai sót | Tác động | Cách kiểm tra/giảm thiểu |
| --- | --- | --- |
| Rule allow rộng đứng trước deny cụ thể | Lưu lượng không mong muốn được cho qua | Xem thứ tự/ưu tiên và hit counter |
| Chỉ có firewall biên, thiếu kiểm soát east–west | Máy cùng subnet có thể liên lạc trực tiếp | Host firewall, microsegmentation, kiểm thử nội vùng |
| Không xét chiều phản hồi stateless | Kết nối hợp lệ bị treo hoặc bị mở quá rộng | Thiết kế rule hai chiều theo cặp endpoint thực tế |
| Chỉ cấu hình IPv4 | IPv6 có thể đi theo chính sách khác | Kiểm kê IPv6, DNS AAAA, route và ICMPv6 |
| Chặn mọi ICMPv6 | Lỗi Neighbor Discovery và Path MTU Discovery | Cho phép loại ICMPv6 thiết yếu theo topology |
| Không xét TCP 53 cho DNS | Một số phân giải DNS lỗi | Kiểm tra nhu cầu DNS và rule UDP/TCP |
| Nhầm địa chỉ NAT | Rule không khớp hoặc log khó hiểu | Kiểm tra thứ tự NAT/filter và địa chỉ tại điểm lọc |
| Stateful firewall gặp route bất đối xứng | Gói phản hồi không khớp state | Kiểm tra tuyến, trạng thái và HA |
| Máy nhiều NIC hoặc tunnel tạo đường phụ | Có thể bypass firewall đã thiết kế | Kiểm kê topology, route, VPN và gateway |
| Rule không có chủ sở hữu hoặc không hết hạn | Quyền thừa tích lũy | Quản lý thay đổi, expiry và rà soát định kỳ |
| Đánh đồng allow TCP 443 với bảo mật web | API vẫn có thể bị lạm dụng | Xác thực, phân quyền L7, log và bảo vệ ứng dụng |

## 15. Kết hợp packet filtering với phòng vệ nhiều lớp

### 15.1. IDS/IPS

Packet filtering quyết định **những đường mạng được phép**; IDS/IPS giúp phát hiện hoặc ngăn một số mẫu hoạt động bất thường trên lưu lượng mà cảm biến quan sát được. Một luồng HTTPS hợp lệ ở lớp 4 vẫn có thể chứa yêu cầu độc hại. Khi TLS mã hóa nội dung, firewall dựa trên header không tự đọc được nội dung; cần kết hợp log ứng dụng và kiểm soát tại đầu cuối.

### 15.2. VPN và xác thực

VPN bảo vệ kênh truyền, không tự cho người dùng quyền truy cập mọi subnet nội bộ. Sau khi xác thực VPN, chính sách lọc gói vẫn cần giới hạn nhóm tài nguyên. Các hành động quản trị còn phải được kiểm soát bằng MFA, phân quyền và ghi nhận phiên.

### 15.3. DNS, Wi-Fi và IoT

Các thiết bị khách và IoT có thể chỉ cần DNS, NTP và một số endpoint dịch vụ đã phê duyệt. Tách SSID/VLAN có ích khi kết hợp rule kiểm soát inter-VLAN và cách ly client phù hợp. Packet filtering không thay thế bảo vệ chính giao thức DNS hoặc cơ chế xác thực Wi-Fi.

### 15.4. Zero Trust, cloud và workload

Trong Zero Trust, quyết định truy cập còn xét danh tính, trạng thái thiết bị và quyền tài nguyên. Trên cloud, security group/network ACL thực thi một phần chính sách mạng nhưng IAM, quyền quản trị cloud API và log audit vẫn cần riêng. Với container, NetworkPolicy chỉ có hiệu quả khi nền tảng mạng hỗ trợ và thực thi đúng selector, ingress và egress.

## 16. Tình huống: reverse proxy bị chiếm quyền

Giả sử reverse proxy ở DMZ bị chiếm quyền và cố kết nối trực tiếp đến PostgreSQL:

**Trường hợp cấu hình rộng:** rule cho phép toàn bộ DMZ đi vào mạng nội bộ trên mọi cổng, khiến máy bị chiếm quyền có nhiều đích để tiếp cận và tăng nguy cơ di chuyển ngang.

**Trường hợp lọc đúng phạm vi:** chỉ luồng reverse proxy → Order API trên TCP 8443 được phép. Kết nối từ reverse proxy tới PostgreSQL trên TCP 5432 bị firewall chặn. Log deny giúp đội giám sát điều tra lý do kết nối trái ma trận.

**Rủi ro còn lại:** proxy vẫn có quyền gửi yêu cầu tới API. Nếu API có lỗi phân quyền, attacker có thể lạm dụng **đường đã được phép**. Vì vậy cần xác thực giữa dịch vụ, kiểm soát quyền từng API, tài khoản database tối thiểu và giám sát các hành vi bất thường.

Tình huống cho thấy packet filtering giảm phạm vi đường mạng, còn bảo vệ ứng dụng và dữ liệu ngăn lạm dụng trên những đường hợp lệ.

## 17. Câu hỏi và bài tập tự kiểm tra

1. Vì sao rule cho phép TCP 443 không chứng minh một API đã được bảo vệ khỏi truy cập trái phép?
2. Gói TCP có cờ ACK có đủ chứng minh nó là phản hồi của kết nối hợp lệ khi firewall stateless không? Vì sao?
3. Hai máy trong cùng VLAN gửi dữ liệu trực tiếp qua switch. Firewall tại router biên có luôn quan sát được không?
4. Nếu một rule allow-all đứng trước rule deny-DB trong chuỗi first-match thì điều gì xảy ra?
5. Một ứng dụng có IPv4 và IPv6; chỉ rule IPv4 được giới hạn. Rủi ro nào có thể còn lại?
6. Vì sao ICMPv6 cần chính sách chi tiết thay vì deny-all?
7. Trong mạng có DNAT, nên kiểm tra những thông tin nào trước khi kết luận IP của một rule không khớp?
8. Tại sao phải đối chiếu cả lưu lượng allow và deny khi kiểm thử firewall?

**Gợi ý:** (1) phân quyền L7 không nằm trong rule cổng; (2) không, ACK chỉ là một flag; (3) không nếu gói không đi qua router/firewall; (4) rule deny có thể không được xét; (5) IPv6 có thể còn đường truy cập; (6) Neighbor Discovery và Path MTU Discovery phụ thuộc ICMPv6; (7) địa chỉ trước/sau NAT, thứ tự xử lý và log; (8) để chắc chắn dịch vụ hoạt động và đường trái phép bị chặn.

### Bài tập thực hành trên giấy

Một doanh nghiệp có **User** (10.50.10.0/24), **Application** (10.50.20.0/24) và **Data** (10.50.30.0/24). Chỉ máy API 10.50.20.15 được gọi PostgreSQL 10.50.30.5:5432; người dùng chỉ được truy cập API trên HTTPS 443.

Hãy thiết kế ma trận gồm hai rule allow và ít nhất ba rule deny; xác định chiều khởi tạo và phản hồi nếu dùng stateless ACL; giải thích stateful inspection xử lý khác ở đâu; đề xuất ba negative test và các nguồn log cần đối chiếu. Kết quả đạt yêu cầu khi mỗi luồng có **nguồn, đích, dịch vụ, lý do và kỳ vọng kiểm thử**.

## 18. Ghi nhớ

- **Packet filtering firewall kiểm tra header và ngữ cảnh mạng để quyết định cho phép hoặc chặn gói**; đây là một lớp cơ bản của phân đoạn mạng.
- **Rule tốt phải giới hạn nguồn, đích, giao thức/cổng, chiều và lý do.** Tránh cấp quyền quá rộng.
- **Thứ tự rule và default policy quyết định hành vi thực tế.** Không giả định mọi firewall có cùng ngữ nghĩa.
- **Stateless không theo dõi phiên; stateful có thể nhận diện gói phản hồi theo connection tracking.** Cờ TCP ACK không thay thế kiểm tra trạng thái.
- **NAT, IPv6, ICMPv6, phân mảnh, DNS và route phụ là những điểm cần xét kỹ** khi viết và kiểm thử rule.
- **Cho phép đường TCP không đồng nghĩa cho phép hành động ứng dụng.** Luôn kết hợp xác thực, phân quyền, TLS và IDS/IPS.
- **Kiểm thử cả luồng được phép lẫn bị từ chối**, xác nhận gói đi qua đúng điểm thực thi, đọc log và quản lý vòng đời rule.
