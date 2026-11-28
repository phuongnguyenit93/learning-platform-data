# Private DNS zone: thiết kế vùng DNS riêng tư an toàn

**Private DNS zone (vùng DNS riêng tư)** là một vùng tên DNS được phục vụ cho **những mạng hoặc bộ phân giải được cho phép**, thay vì công bố bản ghi của vùng đó qua hệ thống DNS có thể truy vấn công khai từ Internet. Private DNS zone giúp các ứng dụng, máy ảo, container và mạng doanh nghiệp tìm đúng địa chỉ của dịch vụ nội bộ mà không cần gán IP cố định vào mã nguồn.

Ví dụ, một ứng dụng trong mạng sản xuất truy vấn tên **orders.prod.corp.example** và nhận địa chỉ riêng **10.30.20.15** từ DNS nội bộ. Người dùng Internet bên ngoài không được truy vấn cùng vùng private theo đường phân giải công khai thông thường. Tuy nhiên, **không công bố bản ghi DNS không có nghĩa endpoint đã được bảo vệ bằng firewall hay xác thực**: nếu dịch vụ còn đường kết nối khác, DNS riêng tư không chặn được truy cập.

Bài học thuộc chương **DNS security** của module **SECURITY_NETWORK_SECURITY**. Việc triển khai private zone liên quan trực tiếp tới phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, mạng không dây và hạ tầng cloud. Mục tiêu là biết mô hình hóa luồng DNS, kiểm soát ranh giới tin cậy, phân tích sự cố phân giải tên và xây dựng kiến trúc DNS có tính bảo mật, sẵn sàng và khả năng giám sát.

> **Quy ước của bài:** các tên dưới miền **example** (ví dụ corp.example, app.corp.example) là tên dành cho minh họa; các địa chỉ 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24 là các dải TEST-NET dành cho tài liệu. Khi triển khai thật, dùng tên miền do tổ chức sở hữu/quản lý và IP của mạng được phê duyệt.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **DNS zone**, authoritative DNS server, recursive resolver, DNS cache và private DNS zone.
2. Giải thích cơ chế **split-horizon DNS** khi cùng một tên có kết quả khác nhau tùy mạng/bộ phân giải.
3. Thiết kế liên kết private zone với VPC/VNet/mạng nội bộ, bao gồm DNS forwarding qua VPN, leased line hoặc mạng hybrid.
4. Đọc bản ghi A, AAAA, CNAME, PTR, TXT, SRV, SOA, NS; hiểu vai trò TTL và negative caching.
5. Xác định các rủi ro như **DNS shadowing, cấu hình zone chồng lấp, lộ tên nội bộ, DNS hijacking, lạm dụng quyền sửa bản ghi và DNS exfiltration**.
6. Phân biệt bảo mật quyền truy vấn, **DNSSEC**, DoT/DoH, network ACL và xác thực ứng dụng.
7. Kiểm tra truy vấn từ đúng mạng, đúng resolver; tìm nguyên nhân NXDOMAIN, timeout, trả sai IP hoặc DNS cache cũ.
8. Thiết lập log, quyền thay đổi, thử nghiệm và phương án khôi phục cho private DNS zone trong môi trường đa mạng.

## 2. Nền tảng DNS cần biết trước

### 2.1. DNS hoạt động theo chuỗi thành phần

Khi một ứng dụng muốn kết nối tới **orders.prod.corp.example**, các thành phần có thể tham gia:

1. **Ứng dụng và hệ điều hành**: tạo yêu cầu phân giải tên; hệ điều hành có thể có cache, hosts file hoặc cấu hình nhiều resolver.
2. **Stub resolver**: thành phần phía client chuyển yêu cầu DNS tới resolver được cấu hình, thường qua UDP/TCP 53 nếu dùng DNS truyền thống.
3. **Recursive resolver / caching resolver**: tìm câu trả lời từ cache hoặc theo forwarding/recursion policy; thường là dịch vụ DNS của doanh nghiệp, cloud hoặc cluster.
4. **Authoritative DNS server**: nguồn dữ liệu có thẩm quyền cho vùng DNS cụ thể; trả lời theo các bản ghi mà nó quản lý.
5. **Client cache**: lưu kết quả trong một khoảng thời gian được kiểm soát bởi TTL, chính sách resolver và hệ điều hành.

Không phải mọi truy vấn đều đi qua đầy đủ các bước. Resolver có thể có sẵn cache; cloud DNS có thể cung cấp authoritative/private zone và recursion qua dịch vụ quản lý, không hiện thành máy chủ đơn lẻ. Tương tự, một forwarder có thể chuyển truy vấn tới resolver khác thay vì tự truy vấn chuỗi DNS công khai.

### 2.2. Resolver khác authoritative server

| Thành phần | Chức năng | Ví dụ về quyết định |
| --- | --- | --- |
| **Authoritative server** | Sở hữu câu trả lời cho một zone | Bản ghi orders.prod.corp.example thuộc zone prod.corp.example có IP nào? |
| **Recursive resolver** | Tìm và cache câu trả lời cho client | Nếu cache thiếu, nên forward vào DNS nội bộ hay dùng recursion ngoài? |
| **Forwarder** | Chuyển truy vấn phù hợp tới resolver khác | Truy vấn *.corp.example phải tới DNS doanh nghiệp |
| **Stub resolver** | Yêu cầu DNS thay ứng dụng | Hệ điều hành dùng server DNS nào cho tên này? |
| **DNS cache** | Tăng tốc và giảm truy vấn lặp | Có trả kết quả cũ hoặc kết quả âm (NXDOMAIN) còn hạn không? |

Một **private zone không phải là một VPN** và cũng không tự tạo đường định tuyến tới IP trả về. Sau khi client nhận A/AAAA, đường TCP/UDP/ICMP tới IP đó vẫn phải đi qua route, firewall, ACL, security group và cơ chế xác thực ứng dụng tương ứng.

### 2.3. Các loại bản ghi thường gặp

| Record | Ví dụ giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| **A** | orders.prod.corp.example → 10.30.20.15 | Tên tới địa chỉ IPv4 |
| **AAAA** | orders.prod.corp.example → fd12:3456:789a:20::15 | Tên tới địa chỉ IPv6 |
| **CNAME** | api.prod.corp.example → gateway.prod.corp.example | Alias đến một tên DNS khác |
| **NS** | prod.corp.example → nameserver có thẩm quyền | Khai báo nameserver của zone/delegation theo thiết kế |
| **SOA** | serial, refresh, retry, expire, minimum | Thông tin quản lý zone và tham số phục vụ DNS |
| **TXT** | Dữ liệu văn bản phục vụ cơ chế đã được định nghĩa | Không mặc định là bản ghi bí mật; client được phép truy vấn có thể đọc |
| **SRV** | Tên dịch vụ → target và port | Khám phá dịch vụ khi giao thức/client có hỗ trợ |
| **PTR** | IP trong reverse zone → hostname | Tra cứu ngược; không thay xác thực danh tính |

**Không nên đặt token, mật khẩu hoặc private key trong TXT record.** Private zone chỉ giới hạn phạm vi phân giải được thiết kế, không phải kho bí mật. Nếu cùng một owner name có CNAME, cần tuân thủ quy tắc DNS về việc không đặt các loại record xung đột với CNAME ở cùng tên, trừ ngoại lệ do giao thức quy định. Các tính năng alias/ANAME ở apex tùy nhà cung cấp và không phải một loại record chuẩn chung để sao chép giữa nền tảng.

## 3. Private DNS zone là gì và riêng tư ở mức nào?

Private zone thường có ba thuộc tính:

1. **Dữ liệu bản ghi nội bộ** được quản lý ở authoritative DNS riêng, hoặc bởi một dịch vụ DNS có phạm vi truy vấn giới hạn.
2. **Phạm vi nhìn thấy (visibility)** được gắn với mạng, VPC/VNet, DNS view, resolver hoặc chính sách forwarder được cho phép.
3. **Đường đến resolver/authoritative service** chịu kiểm soát định tuyến, ACL, firewall và các điều kiện IAM/định danh khi quản trị.

Ví dụ sơ đồ:

~~~mermaid
flowchart LR
    U["Người dùng nội bộ\nVPN / văn phòng"] --> R["DNS resolver doanh nghiệp"]
    V["Workload trong VPC/VNet"] --> C["Cloud recursive resolver"]
    R -->|"Conditional forwarding\ncorp.example"| I["Resolver endpoint nội bộ"]
    I --> P[("Private zone\nprod.corp.example")]
    C -->|"Zone association"| P
    C -->|"Tên ngoài private zone"| X["DNS recursion / public"]
    Z["Client trên Internet"] --> PR["Public resolver"]
    PR --> PZ["Public DNS view\nkhông chứa private record"]
~~~

Mũi tên nói về **đường phân giải tên**, không phải đường ứng dụng tới máy chủ. Client ngoài Internet có thể biết tên nội bộ bằng nhiều cách khác (log, tài liệu bị lộ, certificate metadata hoặc chia sẻ thông tin), nhưng thông thường **không truy vấn được bản ghi private qua hệ thống DNS công khai** nếu cấu hình đúng. Không coi việc giấu tên là bảo vệ duy nhất.

### 3.1. Private không đồng nghĩa chỉ dùng địa chỉ IP riêng

Private zone thường trả RFC1918 IPv4 hoặc ULA IPv6, nhưng **quy tắc private của zone là phạm vi truy vấn**, không phải bắt buộc giá trị A/AAAA phải là địa chỉ riêng. Có hệ thống lưu bản ghi tên nội bộ trỏ đến public IP được kiểm soát hoặc endpoint có private link. Ngược lại, một bản ghi A trên public DNS có thể trỏ tới 10.0.0.0/8; việc này **không biến public zone thành private zone** mà còn có thể làm lộ sơ đồ mạng.

### 3.2. Split-horizon DNS và split-view

**Split-horizon DNS** là cách cùng một tên DNS nhận câu trả lời khác nhau theo **view/phạm vi mạng/resolver**. Ví dụ:

| Nơi truy vấn | Tên hỏi | Kết quả dự kiến |
| --- | --- | --- |
| Máy nhân viên qua VPN → resolver nội bộ | portal.corp.example | A = 10.30.10.20 |
| Máy trong VPC sản xuất → cloud private resolver | portal.corp.example | A = 10.30.10.20 hoặc endpoint private tương ứng |
| Client Internet → public recursive resolver | portal.corp.example | Không tồn tại công khai, hoặc một địa chỉ public khác nếu có public zone được thiết kế |
| Workload staging → resolver của môi trường staging | portal.corp.example | Có thể không tồn tại hoặc trả endpoint staging theo chính sách riêng |

Split DNS hữu ích để dùng **cùng hostname HTTPS** trong và ngoài mạng khi có yêu cầu, nhưng làm việc kiểm thử trở nên phức tạp: một lệnh DNS trả đúng trong VPC A không chứng minh VPC B hoặc client VPN cũng nhìn thấy cùng kết quả.

Nếu có **public zone và private zone trùng tên**, resolver có thể ưu tiên private zone đối với client thuộc phạm vi liên kết. Trong nhiều hệ thống, tên **không tồn tại trong private zone đang được chọn** sẽ trả kết quả âm, thay vì tự tìm record tương ứng trong public zone. Chi tiết chọn zone, độ ưu tiên khi tên chồng lấp và forwarding rule phụ thuộc sản phẩm: **không dựa vào giả định tự fallback ra public DNS**.

### 3.3. Private DNS zone không phải cơ chế phân quyền truy cập ứng dụng

Giả sử DNS nội bộ cho phép **db.prod.corp.example → 10.30.40.10**. Một người dùng biết địa chỉ 10.30.40.10 vẫn có thể thử kết nối trực tiếp mà không hỏi DNS. Để ngăn đường không được phép, cần:

- **Segmentation/microsegmentation, firewall, network ACL hoặc security group** chỉ cho phép workload đúng kết nối tới DB.
- **DB authentication, TLS/mTLS và quyền SQL tối thiểu** kiểm soát người dùng/tài khoản nào được truy cập dữ liệu.
- **VPN/ZTNA/NAC** xác thực thiết bị và người dùng khi đi vào mạng, nhưng không cấp quyền mặc định tới mọi IP private.
- **Monitoring/IDS/IPS và log** giúp thấy bất thường dù truy vấn DNS không xuất hiện.

DNS private cung cấp **service discovery trong phạm vi có kiểm soát**; nó không thay các lớp bảo vệ kể trên.

## 4. Phạm vi gắn kết zone và đường phân giải

### 4.1. Zone association / virtual network link

Trong cloud, private zone thường được **gắn với một hoặc nhiều mạng ảo** để resolver tương ứng có thể tra cứu bản ghi của zone. Tên gọi khác nhau theo nền tảng, ví dụ private hosted zone association, virtual network link hoặc VPC network visibility.

Để một workload ở mạng khác dùng được zone, thường phải có một trong các cách:

- Gắn zone với mạng đó theo cơ chế cloud cho phép.
- Cấu hình resolver forwarding hoặc DNS peering qua điểm tích hợp được hỗ trợ.
- Tạo đường hybrid DNS giữa mạng tại chỗ và cloud thông qua resolver inbound/outbound endpoint và chính sách phù hợp.

**Peering VPC/VNet không mặc nhiên đồng nghĩa private DNS zone sẽ được nhìn thấy xuyên mạng**. Nhiều nền tảng yêu cầu cấu hình DNS liên kết, DNS resolver policy hoặc forwarding riêng. Tương tự, có route giữa hai mạng chưa đủ nếu client đang hỏi sai resolver.

### 4.2. Luồng phân giải qua private zone

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng trong VPC
    participant R as VPC DNS resolver
    participant Z as Private zone prod.corp.example
    participant S as Dịch vụ 10.30.20.15
    A->>R: A orders.prod.corp.example?
    alt Cache hit còn TTL
      R-->>A: A 10.30.20.15 từ cache
    else Cache miss và private zone có hiệu lực
      R->>Z: Tra bản ghi private
      Z-->>R: A 10.30.20.15 TTL 300
      R-->>A: A 10.30.20.15
    end
    A->>S: Kết nối ứng dụng, ví dụ TLS/TCP 443
    Note over A,S: Route + firewall + xác thực là bước riêng
~~~

**Không kết luận chỉ từ TTL=300 rằng mọi client sẽ đổi địa chỉ sau đúng 300 giây.** Hệ điều hành, resolver, JVM/runtime, ứng dụng hoặc dịch vụ CDN có thể dùng cache với giới hạn/cơ chế khác; một client có kết nối TCP đã mở còn có thể tiếp tục dùng IP cũ sau khi DNS đổi.

### 4.3. Khi tên không tồn tại

Cần phân biệt:

- **NXDOMAIN**: tên được hỏi không tồn tại trong phạm vi câu trả lời mà resolver có thẩm quyền xác định.
- **NOERROR/NODATA**: tên có thể tồn tại nhưng **không có loại record được hỏi**, ví dụ hỏi AAAA khi chỉ có A.
- **SERVFAIL**: resolver không xử lý được truy vấn thành công, có thể do upstream, DNSSEC validation, cấu hình hoặc lỗi khác.
- **REFUSED**: server từ chối trả lời theo policy hoặc trạng thái.
- **Timeout**: không nhận được trả lời trong thời gian đợi; có thể do route, firewall UDP/TCP 53, resolver lỗi hoặc các nguyên nhân khác.

Một **kết quả âm** cũng có thể được cache theo quy tắc DNS negative caching, thường dựa trên dữ liệu SOA và chính sách resolver. Sau khi thêm record thiếu, người dùng có thể vẫn gặp NXDOMAIN cho tới khi negative cache hết hạn hoặc được làm mới phù hợp.

Không nên đổi một zone production chỉ vì một lệnh nslookup trên máy cá nhân trả NXDOMAIN mà chưa xác định máy đó đang hỏi **resolver nào** và resolver có nằm trong phạm vi private zone hay không.

## 5. Thiết kế tên miền và cấu trúc zone

### 5.1. Dùng namespace có quyền sở hữu rõ ràng

Một phương án dễ quản lý là dùng **subdomain của tên miền tổ chức sở hữu**, ví dụ tổ chức sở hữu example.com có thể thiết kế các vùng nội bộ theo dạng **prod.internal.example.com** hoặc **corp.example.com**, với policy phù hợp. Trong bài dùng **corp.example** để minh họa, không phải một domain để triển khai sản xuất.

Không nên mặc định chọn một hậu tố tự đặt không thuộc quyền quản lý hoặc tạo public/private zone trùng tùy tiện. **.local** thường được dùng cho mDNS và có thể gây xung đột nếu dùng như DNS unicast cho môi trường doanh nghiệp.

Các cách đặt tên:

| Cấu trúc | Ví dụ | Lợi ích | Đánh đổi |
| --- | --- | --- | --- |
| Theo môi trường | api.prod.corp.example, api.stg.corp.example | Phân biệt production và staging | Cần quản lý endpoint và certificate theo môi trường |
| Theo dịch vụ | orders.prod.corp.example | Dễ đọc ma trận phụ thuộc ứng dụng | Tên có thể cần cập nhật khi đổi topology |
| Theo vùng địa lý | api.apac.prod.corp.example | Dễ lập policy định tuyến vùng | Không lộ thông tin hạ tầng không cần thiết qua các bản ghi khác |
| Theo khu vực quản trị | db.data.prod.corp.example | Hỗ trợ phân quyền quản lý zone/record | Tạo nhiều zone có thể làm forwarding phức tạp |

**Tên DNS là hợp đồng giữa client và dịch vụ.** Không nên để ứng dụng phụ thuộc vào hostname chứa ID của VM, node hoặc IP động nếu một tên service ổn định có thể dùng được.

### 5.2. Một zone hay nhiều zone?

Với một private zone duy nhất **corp.example**, mọi bản ghi prod, staging và management có thể nằm trong một phạm vi quản trị. Cách này đơn giản nhưng dễ cấp quyền quá rộng.

Nếu chia thành **prod.corp.example**, **stg.corp.example** và **mgmt.corp.example**, mỗi zone có thể có owner/IAM và phạm vi mạng riêng. Tuy nhiên, cần kiểm tra **longest suffix match**, các zone chồng lấp, forwarding rules, cơ chế delegation được hỗ trợ và câu trả lời âm. Không được giả định một zone con tự động hoạt động thông qua NS delegation truyền thống trong mọi dịch vụ private cloud.

Ví dụ yêu cầu:

| Vùng | Mục đích | Quyền sửa đề xuất | Phạm vi nhìn thấy |
| --- | --- | --- | --- |
| prod.corp.example | Ứng dụng production | Hệ thống triển khai có phê duyệt, nhóm DNS sản xuất | VPC/VNet prod và resolver hybrid được cấp |
| stg.corp.example | Môi trường staging | Nhóm platform staging theo RBAC | Mạng staging, lab được phê duyệt |
| mgmt.corp.example | Quản trị và giám sát | Nhóm hạ tầng quản trị | Mạng quản trị hoặc VPN/ZTNA phù hợp |
| data.prod.corp.example | DB và dịch vụ dữ liệu nhạy cảm | Nhóm dữ liệu và platform với quyền hẹp | Chỉ vùng workload cần tra cứu |

Tuy vậy, **phạm vi phân giải tên không nhất thiết được cấp đến từng workload** chỉ bằng zone association ở cấp VPC/VNet. Nếu cần cô lập DNS theo nhóm nhỏ, phải thiết kế resolver policy, network controls hoặc kiến trúc khác hỗ trợ phạm vi chi tiết.

### 5.3. TTL và thay đổi endpoint

TTL (Time To Live) biểu thị thời gian cache thông thường cho record. TTL thấp giúp phát hiện thay đổi record nhanh hơn ở nhiều client, nhưng làm tăng số truy vấn, tải resolver và phụ thuộc vào hạ tầng DNS; TTL cao giảm truy vấn nhưng làm thay đổi chậm hơn.

| Tình huống | Cân nhắc |
| --- | --- |
| Service IP tương đối ổn định | TTL vừa hoặc cao phù hợp mức thay đổi và sức tải |
| Chuẩn bị chuyển endpoint | Giảm TTL có kế hoạch **trước** thay đổi; để cache cũ có thời gian hết hạn |
| Failover tự động | Xem cơ chế health-check/routing của DNS, TTL và connection retry của client |
| Negative caching sau khi thêm record | Kiểm tra SOA/negative TTL và cache ở các resolver |
| JVM/client connection pool | TTL DNS không tự đóng kết nối đang dùng địa chỉ cũ |

**DNS failover không thay thế health check, routing và khả năng phục hồi ứng dụng.** Nếu mọi client cache một IP cũ, việc cập nhật A record cũng chưa chắc chuyển hết traffic tức thời.

### 5.4. CNAME, alias và record apex

CNAME có ích khi tên ổn định trỏ tới tên của backend, nhưng có thể gây thêm bước phân giải và yêu cầu cấu hình đúng phạm vi zone. CNAME tới tên thuộc zone khác **không tự mở quyền truy cập zone đó**; resolver vẫn phải biết cách phân giải tên đích và mạng phải kết nối được tới IP.

**Apex của zone** cần SOA và NS; theo DNS chuẩn, một CNAME ở apex sẽ xung đột với các record bắt buộc đó. Một số dịch vụ cloud cung cấp alias đặc thù để trỏ tới load balancer hoặc endpoint mà không dùng CNAME tiêu chuẩn ở apex; cú pháp và mục tiêu hỗ trợ khác nhau theo nhà cung cấp.

## 6. Private DNS trong hệ thống hybrid và multi-network

Một tổ chức thường có nhiều môi trường: văn phòng, mạng quản trị, VPN nhân viên, data center tại chỗ, VPC/VNet cloud, container cluster và mạng đối tác. **Private zone cần thiết kế đường phân giải riêng**, không thể chỉ thêm bản ghi rồi giả định mọi mạng sẽ nhìn thấy.

### 6.1. Conditional forwarding

**Conditional forwarding** là quy tắc tại resolver: nếu tên hỏi thuộc một suffix nhất định, chuyển truy vấn tới DNS server/resolver được chỉ định thay vì xử lý theo đường recursion chung.

Ví dụ:

~~~text
Resolver văn phòng:
  zone suffix: prod.corp.example
  forward to:   10.60.0.10 và 10.60.0.11 (đầu vào hybrid DNS được cấp quyền)

Resolver văn phòng:
  các tên khác:
  xử lý theo chính sách nội bộ/public resolver phù hợp
~~~

Hai IP forwarder là ví dụ của mạng private. Để hoạt động, đường đi từ resolver văn phòng tới endpoint DNS ở cloud phải được cấu hình route và firewall theo giao thức DNS phù hợp. **Forwarding rules không tự tạo VPN hoặc thay địa chỉ route**.

~~~mermaid
flowchart LR
    O["Client văn phòng"] --> OR["On-prem DNS resolver"]
    OR -->|"prod.corp.example\nConditional forward"| V["VPN / private link"]
    V --> IN["Inbound DNS endpoint\nCloud"]
    IN --> CR["Cloud resolver"]
    CR --> Z[("Private zone\nprod.corp.example")]
    OR -->|"Tên công khai"| PUB["Public recursion\nTheo policy"]
    CW["Cloud workload"] --> CR
    CR -->|"onprem.corp.example\nConditional forward"| OUT["Outbound DNS endpoint"]
    OUT --> V
    V --> DR["On-prem DNS server"]
~~~

Hai hướng trong sơ đồ là **hai nhu cầu khác nhau**:

- **On-prem → cloud:** client tại chỗ cần hỏi các tên thuộc private zone trong cloud. Tùy nền tảng, tạo inbound resolver endpoint hoặc cấu hình DNS trung gian được hỗ trợ.
- **Cloud → on-prem:** workload cloud cần hỏi tên do DNS tại chỗ phục vụ. Tùy nền tảng, tạo outbound resolver endpoint/forwarding rule.

Không bắt buộc cả hai hướng nếu nhu cầu nghiệp vụ chỉ có một hướng. Tuy nhiên, **đường trả lời của từng truy vấn** phải hoạt động, và firewall phải cho phép các phiên DNS phù hợp. Đừng nhầm khả năng cloud phân giải tên của on-prem với việc on-prem đương nhiên phân giải được private zone cloud.

### 6.2. Những điều cần kiểm tra khi forward DNS

| Lớp kiểm tra | Câu hỏi cần trả lời |
| --- | --- |
| Tên miền | Forward suffix nào? Có trùng/chồng lấp với private zone hoặc public domain không? |
| Điểm gửi | Resolver nào nhận câu hỏi từ client và đang áp forwarding rule? |
| Điểm đích | IP của inbound DNS endpoint hoặc on-prem DNS server là gì? Có HA không? |
| Giao thức | UDP/TCP 53 có được route và firewall cho phép không? Có DoT/DoH được thiết kế riêng không? |
| Bảo mật | Ai được hỏi resolver, ai sửa forward rule, có ngăn open resolver không? |
| Đường về | Route/ACL/NAT cho response có đúng không? Có mạng đối tác/VPN chồng lấp IP? |
| Health | Endpoint dự phòng có cùng private zone visibility và chính sách không? |
| Logging | Log có cho biết client, forwarder, response code và thời gian không? |
| Lựa chọn zone | Nếu có zone trùng suffix hoặc conditional forwarding chồng lấp, hệ thống ưu tiên quy tắc nào? |

DNS truyền thống thường sử dụng **UDP/53** cho truy vấn nhỏ thông thường; **TCP/53** cũng cần thiết cho các tình huống như phản hồi vượt kích thước, retry sau truncation, và một số chức năng DNS khác. Không chỉ mở UDP rồi kết luận DNS đã hoạt động hoàn chỉnh.

### 6.3. Chống forwarding loop

Giả sử resolver A ở văn phòng forward toàn bộ corp.example tới resolver B ở cloud, trong khi B cũng forward corp.example trở lại A. Một số truy vấn có thể chạy vòng cho tới khi hết timeout/hop-limit và gây **SERVFAIL**, nghẽn hoặc độ trễ.

Cách tránh:

1. Xác định **bên authoritative** cho từng suffix và phân công vùng quản trị rõ ràng.
2. Tránh hai forwarding rule chỉ vào nhau với cùng suffix nếu không có điều kiện phân nhánh chính xác.
3. Kiểm tra các zone cha/con chồng lấp và cơ chế ưu tiên riêng của nền tảng.
4. Dùng lệnh hỏi trực tiếp từng resolver tại các điểm được phép để tìm mắt xích gây loop.
5. Giám sát timeout, SERVFAIL và số truy vấn forward bất thường sau mỗi lần thay đổi.

### 6.4. Multi-account và multi-region

Nhiều tổ chức triển khai ứng dụng ở nhiều tài khoản dự án và vùng cloud. Cần chọn chiến lược **quản lý zone tập trung** hay **phân quyền từng ứng dụng**:

- Tập trung zone giúp nhất quán tên và cơ chế audit nhưng đòi hỏi liên kết mạng và quyền quản trị được tổ chức cẩn thận.
- Mỗi nhóm ứng dụng có zone con cho phép sở hữu độc lập nhưng có thể gây xung đột suffix, chính sách forward và thiếu nhất quán.
- Nếu kết nối cross-account/cross-project, cần kiểm tra quyền tạo/duyệt liên kết và khả năng dùng resolver/peering/forwarding được nhà cung cấp hỗ trợ.
- Multi-region có thể có endpoint DNS, tuyến mạng và quyền truy cập khác nhau; không suy rằng một zone được cấu hình ở vùng A tự động có đường phân giải/ứng dụng hoàn chỉnh ở vùng B.

**DNS reachability và application reachability là hai phép thử khác nhau.** Một workload giải được hostname sang IP private nhưng không có route/ACL đến IP đó sẽ gặp lỗi kết nối ứng dụng, không phải lỗi DNS.

## 7. Private DNS zone trong các nền tảng cloud

Tên dịch vụ và hành vi mặc định thay đổi theo nhà cung cấp. Bảng sau nêu **mô hình khái niệm** cần xác minh bằng tài liệu nền tảng của tổ chức khi triển khai; không phải hướng dẫn sao chép cấu hình cho một phiên bản sản phẩm bất kỳ.

| Nền tảng | Đơn vị vùng riêng tư | Cách workload nhìn thấy zone | Tích hợp hybrid thường gặp |
| --- | --- | --- | --- |
| **AWS Route 53 Private Hosted Zone** | Private hosted zone, có association tới VPC | Amazon-provided resolver cho VPC được liên kết và cấu hình DNS thích hợp | Route 53 Resolver inbound/outbound endpoints và forwarding rules |
| **Azure Private DNS** | Private DNS zone và virtual network link | DNS resolver của VNet được liên kết; có tùy chọn registration theo khả năng | Azure DNS Private Resolver hoặc cơ chế DNS forwarder đã được thiết kế |
| **Google Cloud DNS Private Zone** | Private managed zone và các VPC network có visibility | Cloud DNS resolver theo VPC/visibility được cấu hình | DNS forwarding, DNS peering, inbound/outbound server policies theo khả năng nền tảng |
| **On-prem DNS** | DNS view hoặc zone nội bộ do doanh nghiệp quản lý | Client sử dụng resolver hoặc forwarding thuộc vùng DNS nội bộ | DNS conditional forwarders qua VPN/private link và firewall |

### 7.1. AWS Route 53 Private Hosted Zone

Các khái niệm quan trọng:

- **Private Hosted Zone (PHZ)** chứa record chỉ hiển thị qua cơ chế resolver phù hợp với các **VPC được liên kết**.
- VPC phải có các thiết lập DNS cần thiết theo mô hình dùng, chẳng hạn DNS resolution thông qua VPC resolver; DNS hostnames tùy tình huống yêu cầu. Không mặc định bật/cài khác với quy định hạ tầng.
- Khi **PHZ phù hợp với tên truy vấn** nhưng bản ghi không tồn tại, resolver có thể trả **NXDOMAIN** mà không tự fallback tới record cùng tên ở public DNS.
- **Route 53 Resolver inbound endpoint** phục vụ mô hình resolver ở on-prem gửi truy vấn vào cơ chế phân giải AWS.
- **Route 53 Resolver outbound endpoint** cùng resolver rule phục vụ mô hình chuyển các suffix cần thiết từ VPC tới DNS server ngoài VPC, ví dụ DNS tại chỗ.
- Liên kết zone giữa tài khoản/VPC phải đi theo cơ chế cho phép và quyền quản trị được duyệt; peering một mình không tương đương association.

Ví dụ yêu cầu nghiệp vụ: workload trong VPC production cần thấy **orders.prod.corp.example → IP private của service**, còn VPC development không được tự động được liên kết với zone production. Tách quyền **sửa record** khỏi quyền **quản trị association**, và giám sát thay đổi cả hai.

Các chi tiết về ưu tiên giữa private hosted zone, Resolver rules và các tên chồng lấp có các ngoại lệ theo dịch vụ; **xác minh effective behavior với đúng VPC và rule được áp dụng**, không suy luận chỉ từ quy tắc tên dài nhất.

### 7.2. Azure Private DNS

Azure sử dụng **Private DNS zone** và **virtual network link** để cho các VNet phù hợp phân giải zone. Có thể liên kết zone tới nhiều VNet theo khả năng và giới hạn nền tảng.

Một số liên kết có thể bật **auto-registration**, giúp tạo/quản lý bản ghi liên quan tới máy ảo được nền tảng hỗ trợ trong VNet liên kết theo chính sách dịch vụ. Không suy rằng chức năng này tự tạo record cho mọi loại PaaS, container hoặc private endpoint.

Với **Private Endpoint / Private Link**, tên dịch vụ có thể được ánh xạ tới IP private thông qua các vùng **privatelink...** tương ứng với dịch vụ. Tính năng DNS zone group hoặc quá trình tự động hóa của nền tảng có thể cập nhật record; cần kiểm tra **zone đúng loại dịch vụ, VNet links và forwarding path cho client on-prem**. Không giả định tạo private endpoint tự động làm mọi client đều phân giải và kết nối đúng.

**Azure DNS Private Resolver** hỗ trợ kiến trúc hybrid với inbound/outbound endpoints và DNS forwarding ruleset. Các rule chỉ có hiệu lực theo liên kết và cấu hình cụ thể; cần đánh giá tránh loop với DNS on-prem.

### 7.3. Google Cloud DNS

**Cloud DNS private managed zone** có phạm vi nhìn thấy theo VPC network được phép. Ngoài private zone, nền tảng có các khái niệm như forwarding zone, DNS peering zone và server policy phục vụ bài toán mạng hỗn hợp; **khác nhau về chiều phân giải, thẩm quyền, cách chia sẻ và quyền quản trị**.

Ví dụ: workload ở VPC A cần phân giải internal.corp.example do on-prem DNS quản lý. Thay vì tự tạo bản ghi trùng trong VPC A, có thể cấu hình một đường forwarding theo khả năng Cloud DNS. Nếu VPC B cần dùng private zone của VPC A, phải xem thiết kế visibility/peering DNS và tuyến kết nối chứ không giả định network peering tự đủ.

Các rule peering, server policy và forwarding có thứ tự chọn/cơ chế khác nhau; khi có vùng tên chồng lấp, cần kiểm tra câu trả lời **từ chính VPC của client**.

### 7.4. Tránh phụ thuộc quá mức vào chức năng riêng nhà cung cấp

Khi thiết kế IaC cho nhiều cloud, nên tách:

~~~yaml
# Pseudo-YAML diễn tả ý định, KHÔNG phải cấu hình triển khai của cloud.
private_dns_intent:
  zone: prod.corp.example
  owner: platform-production
  visibility:
    - production-network
    - approved-hybrid-resolver
  allowed_record_managers:
    - deployment-identity-prod
  records:
    - name: orders.prod.corp.example
      type: A
      value: 10.30.20.15
      ttl_seconds: 300
  hybrid_forwarding:
    from_onprem_suffix: prod.corp.example
    to: authorized-cloud-inbound-resolvers
  security:
    avoid_public_record_publication: true
    log_dns_changes: true
    audit_network_associations: true
~~~

Ý định chính sách này được chuyển thành **Resource/Record/Link/Rule theo từng cloud**, kèm review độ ưu tiên zone và cơ chế xử lý NXDOMAIN. Không dùng pseudo-YAML này như API hay Terraform hợp lệ.

## 8. Kubernetes, service discovery và private DNS

Kubernetes thường dùng **CoreDNS hoặc dịch vụ DNS cluster được cấu hình** để giải các tên service như:

~~~text
orders-api.orders.svc.cluster.local
~~~

Trong đó **cluster.local chỉ là tên miền cluster thường gặp, có thể được thay đổi theo thiết kế**. Các tên Service DNS được quản lý trong phạm vi cluster và có cơ chế khám phá endpoint của Kubernetes, **không đồng nghĩa với private zone cloud** mà VM bên ngoài cluster tự phân giải được.

### 8.1. Phân biệt ba lớp tên

| Lớp | Ví dụ | Ai thường sử dụng? | Điểm bảo mật |
| --- | --- | --- | --- |
| Kubernetes Service DNS | orders-api.orders.svc.cluster.local | Pod trong cluster | NetworkPolicy/CNI, ServiceAccount và quyền ứng dụng vẫn cần |
| Private DNS zone của cloud | orders.prod.corp.example | VM, pod hoặc hệ thống hybrid có resolver phù hợp | Zone visibility, DNS associations và firewall |
| Public DNS | api.example.com | Client Internet | WAF, reverse proxy, TLS, firewall edge |

Pod có thể truy vấn tên private cloud qua đường DNS cluster/forwarder, hoặc dùng cấu hình DNS chuyên biệt tùy cluster. Nhưng **không mặc định mọi pod được phép truy vấn mọi tên private**. Nếu muốn tách quyền theo namespace/workload, cần kết hợp NetworkPolicy, DNS policy/plugin, egress control và xác thực hệ thống.

### 8.2. CoreDNS forwarding và search suffix

Client trong Kubernetes thường có **search domains**. Một tên ngắn như orders-api có thể được thử thêm suffix namespace và cluster domain trước khi hỏi tên ngoài. Điều này tiện lợi, nhưng có thể tăng truy vấn, gây nhầm tên hoặc tạo **DNS leakage** nếu một truy vấn nội bộ bị đẩy tới resolver công khai ngoài ý muốn.

Khi cần tên chính xác, dùng **FQDN đầy đủ** phù hợp với thư viện ứng dụng; trong các lệnh DNS chuẩn, dấu chấm ở cuối hostname có thể biểu thị tên tuyệt đối và ngăn search suffix ở nhiều resolver. Tuy nhiên, không phải mọi SDK/công cụ xử lý trailing dot giống nhau khi ghép với TLS hostname/SNI; cần kiểm thử ứng dụng.

Ví dụ cấu hình CoreDNS forwarder, network policy hoặc plugin khác cần được soạn theo **cấu hình thực tế của cluster**. Không chỉnh CoreDNS chỉ để chữa một hostname chưa được gắn private zone đúng ở cloud.

### 8.3. DNS riêng tư không có nghĩa pod được phép kết nối backend

Một pod từ namespace web có thể giải tên **db.prod.corp.example** vì dùng chung resolver của VPC, nhưng policy mạng vẫn phải **chặn pod đó kết nối TCP/5432** nếu chỉ Orders API được phép vào DB. DNS là cách tìm IP, không phải bộ máy authorization theo tài nguyên dữ liệu.

Phải giám sát cả **DNS query path** và **application connection path**: truy vấn tên thành công rồi kết nối thất bại thường dẫn tới kiểm tra route/ACL/port trước, không nên sửa record bằng cách mở rộng zone visibility hoặc chuyển IP sang public.

## 9. Bảo vệ private DNS zone theo phòng vệ nhiều lớp

Một hệ thống private DNS không an toàn chỉ vì record không nằm trên public DNS. Cần đồng thời bảo vệ **quyền quản trị zone, quyền truy vấn, resolver/forwarder, dữ liệu phản hồi và con đường ứng dụng**.

### 9.1. Kiểm soát quyền sửa record và zone association

Một tài khoản có quyền sửa bản ghi **login.prod.corp.example** có thể trỏ nó tới máy không hợp lệ, gây lỗi hoặc hướng lưu lượng vào một endpoint do đối tượng khác kiểm soát. Nếu người dùng hoặc workload tin hostname đó để tạo kết nối, thay đổi DNS trở thành một hình thức **điều khiển luồng truy cập**.

Nguyên tắc quản trị:

- **Least privilege:** tách quyền tạo/sửa record, xóa zone, quản lý DNS forwarding, liên kết/huỷ liên kết VPC/VNet và quyền đọc query log.
- **Identity được bảo vệ:** yêu cầu MFA khi thích hợp cho quản trị viên; workload automation dùng danh tính dịch vụ có quyền tối thiểu, tránh credential tĩnh đặt trong code.
- **Review thay đổi nhạy cảm:** record đăng nhập, secret manager, DB, metadata endpoint, DNS management và các zone production cần quản lý thay đổi/duyệt theo quy định.
- **Ghi audit:** ai sửa record, tên nào, giá trị trước/sau, TTL, liên kết zone, route/forward rule và thời điểm.
- **Phát hiện drift:** so trạng thái thực tế với IaC/desired state, nhất là bản ghi được tự động hóa cấp phát bởi Kubernetes, private endpoint controller hoặc autoscaling.
- **Bảo vệ xóa nhầm:** backup/export zone được phép, quyền xóa tách biệt, phương án rollback đã thử nghiệm.

Quyền **gắn zone vào mạng** có thể nhạy cảm ngang quyền sửa record: thêm nhầm một VPC phát triển vào zone production sẽ làm tăng phạm vi truy vấn, dù không đổi bản ghi nào.

### 9.2. Quyền truy vấn và nguy cơ open resolver

Private resolver không nên mở cho Internet như một **open recursive resolver**. Nếu client bên ngoài có thể gửi query thông qua endpoint công khai hoặc một forwarding interface bị mở rộng, kết quả private zone có thể bị lộ và resolver có thể bị lạm dụng.

Phương án:

1. Đặt inbound DNS endpoints ở mạng/đường truy cập được kiểm soát.
2. Giới hạn nguồn query theo **mạng và danh tính khi có cơ chế hỗ trợ**, dùng firewall/security group/ACL phù hợp.
3. Chỉ cho resolver thực hiện recursion/forwarding đến upstream được duyệt, tránh biến nó thành đường truy vấn mọi tên ngoài chính sách.
4. Giám sát truy vấn bất thường, tốc độ, các bản ghi lớn, lỗi SERVFAIL/NXDOMAIN và yêu cầu từ nguồn không hợp lệ.
5. Không thiết kế kết nối DNS xuyên mạng quản trị và Internet một cách vô điều kiện để “dễ debug”.

**IP allowlist là kiểm soát mạng, không phải xác thực từng người dùng**. Khi nhiều máy sau NAT/VPN cùng một IP nguồn, chỉ nhìn IP chưa đủ để phân biệt nguồn gốc. Nếu yêu cầu độ tin cậy cao, cần thêm bảo vệ endpoint, danh tính thiết bị hoặc chính sách kết nối theo khả năng nền tảng.

### 9.3. DNSSEC, DoT và DoH giải quyết các vấn đề khác nhau

| Cơ chế | Bảo vệ chính | Không tự giải quyết |
| --- | --- | --- |
| **Private zone visibility** | Giới hạn resolver/mạng được xem dữ liệu zone | Không mã hóa DNS truyền thống; không chặn client kết nối IP trực tiếp |
| **DNSSEC** | Chữ ký giúp DNS validating resolver kiểm tra tính xác thực/toàn vẹn dữ liệu DNS với chuỗi tin cậy phù hợp | Không mã hóa query/response, không che tên client hỏi |
| **DNS over TLS (DoT)** | Bảo vệ kênh DNS client ↔ resolver hoặc giữa các thành phần hỗ trợ qua TLS | Không tự xác minh dữ liệu DNS có đúng với authoritative zone nếu thiếu cơ chế xác thực dữ liệu tương ứng |
| **DNS over HTTPS (DoH)** | Truyền DNS trong HTTPS tới resolver được chọn | Không bảo đảm resolver đó có quyền xem private zone của tổ chức |
| **Firewall/DNS policy** | Hạn chế nguồn query, upstream hoặc endpoint được sử dụng | Không thay TLS giữa ứng dụng và server đích |
| **TLS/mTLS của ứng dụng** | Bảo vệ và xác thực kết nối tới endpoint | Không khắc phục hoàn toàn mọi kiểu DNS hijacking hoặc thiếu authorization |

**DNSSEC không đồng nghĩa mã hóa DNS.** Với private zone, việc ký và validation còn phụ thuộc dịch vụ authoritative/private DNS, chính sách trust anchor và khả năng hỗ trợ nhà cung cấp. Một số dịch vụ private cloud không hỗ trợ signing/validation private zone theo cách giống public DNS; không bật kiểm tra DNSSEC một cách máy móc rồi giả định mọi tên private sẽ có chuỗi tin cậy public hợp lệ.

**DoT/DoH có thể tạo đường bỏ qua resolver nội bộ:** client dùng resolver DoH công khai có thể không nhìn thấy private zone và nhận NXDOMAIN hoặc kết quả public khác. DoH/DoT là cách bảo vệ vận chuyển đến resolver, không làm resolver công khai tự có thẩm quyền cho private zone. Nếu tổ chức yêu cầu dùng resolver nội bộ, cần chính sách endpoint/MDM và egress phù hợp; không chỉ chặn UDP/53 rồi nghĩ mọi DNS đã đi đúng đường.

### 9.4. Ngăn DNS leakage và truy vấn sai upstream

**DNS leakage** xảy ra khi một truy vấn tên nội bộ hoặc metadata hostname đi tới resolver không được phép. Ví dụ máy nhân viên VPN dùng split tunneling nhưng DNS client lại chọn resolver ngoài, khiến **db.prod.corp.example** bị hỏi trên public DNS.

Những yếu tố cần xem:

- Cấu hình **resolver được đẩy qua VPN** và search suffix theo hệ điều hành, profile mạng và client VPN.
- Các interface mạng đồng thời như Ethernet, Wi-Fi, hotspot, VPN, container hoặc browser có DNS riêng.
- Conditional forwarding chính xác cho private namespace, tránh forward toàn bộ tên ngoài phạm vi một cách không cần thiết.
- DNS caching và việc client tiếp tục truy vấn server cũ sau đổi cấu hình.
- Ứng dụng dùng DoH riêng thay vì resolver của hệ điều hành.
- Log tại DNS egress hoặc resolver để xác định **truy vấn private suffix rời khỏi mạng dự kiến**.

Không lấy một kết quả phân giải đúng làm bằng chứng duy nhất rằng **không có leak**; cần xác minh đường query thực tế bằng log/capture được phép, resolver address và chính sách egress.

### 9.5. DNS tunneling và rủi ro exfiltration

DNS có thể bị lạm dụng làm **kênh truyền dữ liệu** nếu workload được tự do gửi truy vấn tới các resolver/tên miền do đối tượng khác điều khiển. Tên truy vấn dài, nhãn có entropy cao, nhiều subdomain hiếm hoặc lưu lượng TXT bất thường có thể là tín hiệu cần kiểm tra, nhưng cũng có thể phát sinh từ telemetry hoặc phần mềm hợp lệ.

Biện pháp phòng vệ:

1. Giới hạn **resolver và đường egress DNS** theo nhu cầu dịch vụ.
2. Thu thập metadata query cần thiết, response code và luồng liên quan theo chính sách quyền riêng tư.
3. Phát hiện bất thường dựa trên baseline, không chặn mọi TXT/record lạ.
4. Tương quan với host/EDR, tài khoản workload, DNS policy, traffic firewall và các hoạt động được duyệt.
5. Kiểm soát DoH/DoT không được duyệt theo chính sách tổ chức, không làm gián đoạn lưu lượng hợp lệ mà không thử nghiệm.

Private DNS zone chỉ quản lý các tên nội bộ; nếu client bị chiếm quyền vẫn có đường ra public resolver hoặc gửi HTTPS tới dịch vụ ngoài, DNS riêng tư không đủ ngăn rò rỉ dữ liệu.

### 9.6. DNS rebinding và host header

Một kẻ tấn công có thể kiểm soát miền bên ngoài để thay câu trả lời DNS theo thời gian, khiến trình duyệt hoặc ứng dụng truy cập IP nội bộ qua hostname khác trong một số kịch bản (**DNS rebinding**). Private zone không tự loại bỏ nguy cơ này.

Phòng vệ cần kết hợp:

- Kiểm tra **Host/authority** và các hostname được phép tại reverse proxy/API, không chấp nhận mọi tên miền truy cập một dịch vụ nhạy cảm.
- Xác thực, CSRF protection và authorization tại ứng dụng.
- Lọc truy cập từ web client không đáng tin tới cổng/quản trị nội bộ, theo kiến trúc.
- DNS rebinding protection của resolver/browser khi có, với ngoại lệ được review.

Với dịch vụ cần TLS, certificate/hostname validation giúp nhận diện đúng peer nhưng không thay authorization; không dựa duy nhất vào việc tên kết thúc bằng corp.example để chứng minh request đáng tin.

## 10. Private DNS và private endpoint / private connectivity

Một **private endpoint** trong cloud thường cho phép client tiếp cận một dịch vụ được quản lý qua địa chỉ private trong mạng ảo, thay vì sử dụng public endpoint theo kiến trúc. DNS giúp hostname của dịch vụ đó phân giải tới **địa chỉ private endpoint** đối với client thuộc phạm vi phù hợp.

Quy trình khái niệm:

1. Tạo/duyệt private endpoint cho dịch vụ được hỗ trợ.
2. Xác định **FQDN chính thức** ứng dụng phải dùng và zone private được nền tảng yêu cầu.
3. Tạo/liên kết zone và record theo cơ chế nhà cung cấp hoặc DNS automation đã được kiểm duyệt.
4. Đảm bảo client VPC/VNet/on-prem sử dụng resolver có đường phân giải tới zone đó.
5. Đảm bảo route và firewall cho phép client hợp lệ kết nối **IP private** của endpoint.
6. Kiểm tra TLS hostname/chứng chỉ và xác thực dịch vụ theo yêu cầu, tránh đổi hostname thành IP nếu làm mất xác minh TLS.
7. Nếu mục tiêu là chặn public access, cấu hình **public network access hoặc network restrictions** của dịch vụ theo khả năng sản phẩm; chỉ tạo private endpoint **không bảo đảm** public endpoint đã bị vô hiệu hóa.

### 10.1. Trường hợp phân giải đúng nhưng không kết nối được

Ví dụ:

~~~text
Client trong VNet A:
  storage.service.example.net -> 10.80.2.15

Ứng dụng:
  kết nối TCP/443 tới 10.80.2.15 bị timeout
~~~

Nếu DNS đúng, kiểm tra **peering/route, security group/NSG, firewall, private endpoint status, return path, TLS và quyền dịch vụ**. Không vội sửa record thành public IP để chữa timeout vì có thể làm mất mục tiêu bảo vệ private connectivity.

### 10.2. Split-view khi cùng hostname có public và private endpoint

Một FQDN public của dịch vụ cloud có thể có chuỗi CNAME/alias liên quan tới private endpoint theo cách nhà cung cấp quy định. Client ở mạng được liên kết private DNS nhận IP private, trong khi client public có thể nhận record public hoặc không thể truy cập dịch vụ nếu public access bị chặn. Cần kiểm tra **kết quả từ từng mạng**, không chỉ phân giải qua một resolver duy nhất.

### 10.3. Chú ý khi tự quản record

Nếu dịch vụ hoặc private endpoint bị thay thế, IP private có thể thay đổi. Tạo record tĩnh thủ công dễ gây **stale DNS** khi hệ thống tự động cấp phát hoặc làm việc chuyển vùng. Nếu nền tảng hỗ trợ cơ chế đồng bộ record từ lifecycle của endpoint, dùng đúng quyền/zone group/automation và kiểm tra audit thay đổi. Dù tự động hóa, vẫn cần thử failover và rollback.

## 11. Threat modeling cho Private DNS zone

Xét mô hình nhân viên/VPN → resolver doanh nghiệp → private zone cloud → API/DB. Tài sản cần bảo vệ gồm **bản ghi DNS**, **khả năng phân giải đúng**, **tính bí mật của tên nội bộ**, **quyền sửa zone/forwarding** và **đường truy cập thật tới dịch vụ**.

| ID | Mối đe dọa / lỗi | Điều kiện | Tác động | Kiểm soát và phép thử |
| --- | --- | --- | --- | --- |
| DNS-T01 | Zone association sai | VPC/VNet không được duyệt được liên kết | Mở rộng phạm vi truy vấn hostname nội bộ | IAM riêng cho association, review network links, test negative từ mạng không được phép |
| DNS-T02 | Record bị sửa trái phép | Identity có quyền ghi quá rộng, secret automation lộ | Hướng client tới server sai, gián đoạn/đánh cắp thông tin tùy lớp khác | RBAC/IAM, MFA, audit diff, TLS hostname verification, kiểm tra record |
| DNS-T03 | Lộ truy vấn private ra public DNS | Client dùng resolver ngoài, VPN split DNS sai | Tiết lộ tên/dấu vết kiến trúc, không phân giải được dịch vụ | Chính sách resolver, forwarding, egress, log/query path tests |
| DNS-T04 | Shadowing / zone trùng tên | Private zone trùng public hoặc zone cha/con, thiếu record | NXDOMAIN/NODATA, ứng dụng gián đoạn hoặc đi sai đích | Kiểm tra zone precedence, inventory, negative test, change control |
| DNS-T05 | Forwarding loop | Hai bên forward cùng suffix qua lại | SERVFAIL, timeout, quá tải resolver | Kiến trúc authority rõ ràng, test từng resolver, telemetry |
| DNS-T06 | Resolver bị mở rộng truy cập | Inbound DNS endpoint cho nguồn ngoài dự kiến | Lộ dữ liệu DNS, bị lạm dụng query | Firewall/SG/ACL, private endpoint, giới hạn recursion, logs |
| DNS-T07 | DNS exfiltration qua public resolver | Workload được dùng DNS egress tùy ý | Truyền dữ liệu bằng query, khó phân biệt traffic hợp lệ | Egress DNS policy, monitoring, EDR, threat hunting |
| DNS-T08 | DNSSEC validation/configuration không phù hợp | Client kỳ vọng trust chain public cho zone private | SERVFAIL, mất khả năng phân giải | Thiết kế trust anchor/validation đúng cơ chế, thử trước rollout |
| DNS-T09 | Record cũ sau failover | TTL/cache hoặc automation chưa đồng bộ | Client kết nối backend không còn sẵn sàng | TTL planning, health check, verify cache và app retry |
| DNS-T10 | Hostname đúng nhưng kết nối thiếu phân quyền | DNS trả IP backend cho nhiều vùng | Truy cập trái phép nếu firewall/API quá rộng | Segmentation, network ACL, TLS/mTLS và authorization |
| DNS-T11 | DNS logs chứa tên hoặc dữ liệu nhạy cảm | Query logs không kiểm soát quyền/retention | Rò rỉ sơ đồ mạng, thông tin người dùng | Data minimization, RBAC, retention, export audit |
| DNS-T12 | DNS proxy bị giả nguồn/đích | Resolver hoặc đường truyền không được bảo vệ phù hợp | Câu trả lời không đúng hoặc truy vấn bị sửa | Kiểm soát mạng, kênh bảo mật được hỗ trợ, quản trị resolver, DNSSEC khi áp dụng |

### 11.1. Liên hệ STRIDE

- **Spoofing:** giả resolver/endpoint hoặc identity có quyền quản trị.
- **Tampering:** thay record, forward rule, cache hoặc đường trả lời DNS trái phép.
- **Repudiation:** không có audit ai sửa zone/association, thiếu log dẫn tới không truy nguyên thay đổi.
- **Information disclosure:** query private bị leak ra public resolver hoặc query log bị lộ.
- **Denial of Service:** xóa record, tạo forwarding loop, TTL/cache sai hoặc resolver quá tải.
- **Elevation of privilege:** tài khoản workload nhận quyền sửa zone production hoặc tự liên kết VPC trái phạm vi.

### 11.2. Bản ghi rủi ro mẫu

| Trường | Nội dung minh họa |
| --- | --- |
| Asset | Tên DNS login.prod.corp.example và endpoint xác thực |
| Trust boundary | VPC sản xuất và mạng VPN nhân viên |
| Tình huống | Một automation identity có quyền sửa toàn bộ zone thay vì chỉ record thuộc sở hữu |
| Nguy cơ | Thay A/CNAME của endpoint đăng nhập hoặc xóa record làm gián đoạn truy cập |
| Kiểm soát mạng | Resolver chỉ cho mạng được duyệt; firewall bảo vệ backend |
| Kiểm soát dữ liệu | TLS certificate/hostname verification, xác thực API, không gửi credential tới peer sai |
| IAM | Thu hẹp quyền sửa record theo tài nguyên/điều kiện được hỗ trợ, tách quyền liên kết zone |
| Detection | DNS change audit, drift detection, probe từ mạng prod/VPN |
| Ứng phó | Khôi phục record hợp lệ, thu hồi identity bị lộ, kiểm tra cache và ứng dụng |
| Rủi ro còn lại | Credential/token đã gửi trước khi phát hiện cần được đánh giá theo bằng chứng và chính sách ứng cứu |

**Không khẳng định DNS hijack tự động đánh cắp mật khẩu.** Hậu quả phụ thuộc việc client kiểm tra TLS/certificate, bảo vệ phiên, hành vi ứng dụng và dịch vụ mà client thực sự kết nối.

## 12. Kiểm chứng Private DNS zone từ đúng điểm nhìn

Phần lớn sự cố private DNS không phải do cú pháp record, mà do **client truy vấn sai resolver, zone không được liên kết với mạng, forwarding không tới đích, cache còn dữ liệu cũ hoặc kết nối ứng dụng không có route**.

### 12.1. Xác định câu hỏi trước khi chạy lệnh

Với một hostname, tối thiểu phải biết:

1. Client chạy ở đâu: VPC/VNet nào, VLAN nào, máy VPN nào, pod/namespace nào?
2. Client hỏi **resolver nào**: địa chỉ IP và đường mạng thực tế, không chỉ tên dịch vụ DNS trong tài liệu.
3. FQDN đầy đủ và **record type** được hỏi: A, AAAA, CNAME hay SRV?
4. Private zone nào có thẩm quyền, được gắn với mạng nào và có forwarding rule nào cạnh tranh?
5. Kỳ vọng cho client **được cấp quyền** là IP gì; cho client **không được cấp quyền** là gì?
6. Sau khi phân giải, ứng dụng đi tới IP/port nào; có route, ACL, certificate và authentication phù hợp không?

Trước khi sửa, ghi **thời điểm, VPC/VNet, resolver, FQDN, record type, response code, answer, TTL còn lại** và ID thay đổi gần nhất.

### 12.2. Thử bằng dig trên máy có công cụ

Giả sử resolver lab nội bộ là **10.60.0.10** và cần kiểm tra bản ghi private:

~~~bash
# Hỏi resolver được chỉ định, không dùng DNS mặc định của máy.
dig @10.60.0.10 orders.prod.corp.example A
dig @10.60.0.10 orders.prod.corp.example AAAA

# Kiểm tra thông tin trả lời ngắn gọn.
dig @10.60.0.10 orders.prod.corp.example A +noall +answer

# So sánh UDP và TCP ở đường được phép.
dig @10.60.0.10 orders.prod.corp.example A +tcp

# Xem thông tin vùng có thẩm quyền khi được hệ thống hỗ trợ.
dig @10.60.0.10 prod.corp.example SOA
~~~

**Chỉ chạy tới resolver thuộc môi trường được phép.** Kết quả A/AAAA rỗng cần đọc **status** và phần authority, không tự kết luận SERVFAIL chỉ vì phần ANSWER không có dòng nào. Một truy vấn do resolver trả lời từ cache không có nghĩa server đó là authoritative.

**Không dùng dig +trace như bài kiểm tra quyết định cho private zone**: cơ chế truy vấn theo các delegation public có thể không đi qua conditional forwarding hoặc private resolver mà ứng dụng đang dùng. Muốn kiểm tra split DNS, phải hỏi resolver thực tế của **từng mạng**.

### 12.3. Dùng nslookup và Windows PowerShell

~~~powershell
# Tra cứu với resolver DNS của môi trường thử nghiệm.
Resolve-DnsName -Name orders.prod.corp.example -Type A -Server 10.60.0.10
Resolve-DnsName -Name orders.prod.corp.example -Type AAAA -Server 10.60.0.10

# Cách kiểm tra bằng nslookup.
nslookup -type=A orders.prod.corp.example 10.60.0.10

# Sau DNS, kiểm tra riêng đường TCP của ứng dụng.
Test-NetConnection -ComputerName orders.prod.corp.example -Port 443
~~~

Các lệnh DNS hỏi resolver chỉ định, còn **Test-NetConnection** sử dụng cơ chế phân giải mặc định của hệ điều hành và đường mạng của client. Nếu kết quả khác nhau, hãy kiểm tra cấu hình DNS mặc định/search suffix/VPN hoặc cache. Kết nối TCP thành công cũng **không tự xác minh** TLS hostname hay quyền API; cần phép thử ứng dụng phù hợp.

Trên các hệ điều hành khác, có thể dùng các công cụ tương đương để kiểm tra **DNS configuration** và **kết nối ứng dụng**, nhưng không mặc định tên lệnh hoặc hành vi cache giống nhau.

### 12.4. Chỉ định hostname và IP khi kiểm tra TLS

Nếu đã biết IP riêng và muốn tách vấn đề DNS khỏi kết nối HTTPS trong lab:

~~~bash
# Buộc IP cho lần thử này nhưng vẫn dùng hostname để kiểm tra TLS/SNI.
curl --resolve orders.prod.corp.example:443:10.30.20.15 \
  --connect-timeout 5 --head https://orders.prod.corp.example/health
~~~

Chỉ dùng endpoint và chứng chỉ **được cấp phép**. Tham số **--resolve** giúp kiểm tra backend cụ thể mà vẫn gửi hostname HTTPS; nó **không tắt certificate verification**. Nếu chứng chỉ của lab không được tin cậy, cấu hình CA/chứng chỉ thử nghiệm hợp lệ, không sử dụng tùy chọn bỏ qua xác minh chỉ để tạo kết quả “thành công”.

### 12.5. Mẫu bảng kết quả theo mạng

| Điểm thử | Resolver thực tế | Tên được hỏi | Kỳ vọng DNS | Kỳ vọng kết nối |
| --- | --- | --- | --- | --- |
| App VPC prod | Resolver của VPC prod | orders.prod.corp.example A | 10.30.20.15 | TCP/443 được phép nếu client thuộc nhóm ứng dụng |
| VM VPC staging chưa được liên kết | Resolver VPC staging | orders.prod.corp.example A | Không nhận bản ghi private, trừ đường được cấp quyền riêng | Không được mặc nhiên kết nối production |
| Client VPN được phê duyệt | Resolver nội bộ có hybrid forwarding | orders.prod.corp.example A | 10.30.20.15 | Theo ACL của VPN và quyền ứng dụng |
| Client Internet | Public resolver | orders.prod.corp.example A | Không nhận bản ghi private | Không có quyền tới IP private qua Internet bình thường |
| Admin mạng quản trị | Resolver mgmt | db.prod.corp.example A | Trả record nếu thiết kế cần | Chỉ cổng quản trị/DB được cấp quyền |
| Pod ứng dụng prod | Resolver cluster/forwarder | orders.prod.corp.example A | Trả đúng theo đường tích hợp | Theo CNI/NetworkPolicy, TLS và authorization |

Đây là **kỳ vọng thiết kế** của bài toán giả định. Mạng staging có thể nhận NXDOMAIN, NODATA, câu trả lời public khác hoặc lỗi resolver tùy namespace và forwarding thực tế; điều cần xác minh là **không có quyền truy vấn/kết nối ngoài phạm vi được duyệt**.

## 13. Xử lý sự cố theo lớp

### 13.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Ứng dụng không truy cập được hostname private"] --> B{"Client đang dùng resolver đúng?"}
    B -- "Không" --> B1["Kiểm tra OS, VPN, DHCP, pod DNS và DoH"]
    B -- "Có" --> C{"Resolver có visibility tới zone?"}
    C -- "Không" --> C1["Kiểm tra VPC/VNet links, forwarding và quyền nguồn"]
    C -- "Có" --> D{"Trả đúng record và status?"}
    D -- "Không" --> D1["Kiểm tra tên, type, record, zone overlap, cache, DNSSEC"]
    D -- "Có" --> E{"Có route/firewall tới IP trả về?"}
    E -- "Không" --> E1["Kiểm tra VPN/peering/ACL/SG và endpoint health"]
    E -- "Có" --> F{"TLS, listener và quyền ứng dụng đúng?"}
    F -- "Không" --> F1["Kiểm tra certificate/SNI, port, authn/authz"]
    F -- "Có" --> G["Đối chiếu log các chặng và thử lại từ đúng client"]
~~~

### 13.2. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| NXDOMAIN trong VPC nhưng record có trong console | VPC chưa liên kết zone, sai suffix, record nằm zone khác, negative cache | Kiểm tra zone association, truy vấn trực tiếp resolver VPC, status/SOA/TTL |
| NXDOMAIN cho tên public khi có private zone trùng tên | Private zone được chọn nhưng thiếu record; không fallback public | Rà split-horizon/zone precedence, tạo record cần thiết hoặc điều chỉnh thiết kế zone |
| SERVFAIL khi hỏi tên hybrid | Forwarding loop, upstream lỗi, DNSSEC validation/trust cấu hình sai, timeout | Truy vấn từng resolver, xem query log và rule; xác nhận upstream authoritative |
| DNS timeout qua VPN | Không có route, DNS endpoint bị chặn, tunnel lỗi hoặc response sai đường | Kiểm tra UDP/TCP 53, route hai chiều, VPN DNS config, health |
| Máy ngoài Internet vẫn biết tên nội bộ | Record public bị công bố hoặc log/certificate/tài liệu làm lộ tên | Phân biệt lộ tên và lộ record; rà public zone, quyền xuất log và endpoint |
| DNS đúng nhưng TCP/443 timeout | Route/SG/firewall hoặc backend không nghe cổng | Kiểm tra IP/route/ACL, private endpoint state, listener |
| DNS đúng nhưng TLS lỗi hostname | Ứng dụng gọi IP thay tên, CNAME/Host/SNI sai, chứng chỉ không khớp | Giữ hostname, xác minh chứng chỉ và điểm kết thúc TLS |
| Chỉ một số pod không giải được tên | NetworkPolicy egress, DNS config pod, namespace search suffix hoặc CNI | Kiểm tra resolver pod, CoreDNS, UDP/TCP 53, identity/network policy |
| Sau đổi IP vẫn nhận IP cũ | Cache resolver/client, TTL chưa hết, JVM/connection pooling | So TTL tại từng hop, xác minh kết nối cũ và kế hoạch cutover |
| IPv4 hoạt động nhưng IPv6 lỗi | AAAA record/route/firewall IPv6 khác, ứng dụng ưu tiên IPv6 | So A/AAAA, kiểm tra network policy dual stack |
| Truy vấn ra public DNS khi dùng VPN | Split DNS sai, resolver riêng, DoH/DoT, route DNS không đúng | Đối chiếu resolver thực tế, VPN/client policy và log egress |
| Một VPC truy vấn đúng, VPC khác sai | Zone link/association, resolver rules và đường hybrid khác nhau | Kiểm tra cấu hình của từng VPC, không suy từ VPC đầu tiên |
| Bản ghi alias tới dịch vụ cloud trả IP không như dự kiến | Chọn nhầm private zone hoặc loại endpoint; lifecycle record thay đổi | Kiểm tra private endpoint/FQDN/record chain và automation |
| Tăng nhiều NXDOMAIN sau rollout | Ứng dụng tạo tên sai/search suffix, forwarding lỗi, DNS exfil nghi vấn | Lấy mẫu query đã ẩn nhạy cảm, kiểm tra client/version và tương quan EDR |

### 13.3. Phân biệt lỗi DNS với lỗi ứng dụng

Ví dụ một client nhận:

~~~text
DNS: orders.prod.corp.example -> 10.30.20.15
TCP: kết nối 10.30.20.15:443 thành công
HTTPS: HTTP 403 Forbidden
~~~

Điều đó cho thấy truy vấn tên và kết nối mạng **có thể đã hoạt động**, còn HTTP 403 là quyết định của proxy hoặc ứng dụng theo cấu hình. Không sửa private zone chỉ vì HTTP trả lỗi quyền; cần kiểm tra authentication, authorization hoặc chính sách gateway.

Ngược lại, nếu DNS trả đúng IP nhưng TLS báo tên chứng chỉ không khớp, đó là vấn đề **xác thực kết nối/TLS**, không nhất thiết là thiếu zone association.

### 13.4. Kiểm tra cache nhiều lớp

Đường phân giải có thể có cache ở:

- Stub resolver/hệ điều hành.
- Recursive resolver ở client/VPC/VPN.
- DNS forwarding resolver và các bộ đệm trung gian.
- Runtime ứng dụng (JVM, DNS cache riêng của SDK) hoặc connection pooling.
- Các lớp service discovery riêng.

Nếu phải xóa cache để kiểm chứng, **chỉ làm trong lab hoặc theo quy trình vận hành**. Flushing cache trên resolver dùng chung có thể tạo tải tăng hoặc ảnh hưởng các ứng dụng khác; một thay đổi zone đáng tin cần được kiểm chứng trong điều kiện TTL/negative caching thông thường.

## 14. Vận hành, quan sát và quản lý thay đổi

### 14.1. Thước đo cần theo dõi

| Chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
| --- | --- | --- |
| Query volume theo zone, resolver và nguồn được phép | Baseline nhu cầu phân giải | Tăng bất thường từ workload, public DNS leak hoặc script lỗi |
| Response code NXDOMAIN/NODATA/SERVFAIL/REFUSED | Phân loại vấn đề | SERVFAIL tăng hoặc NXDOMAIN tăng sau change |
| DNS response time p50/p95/p99 | Tính sẵn sàng và hiệu năng | Timeout/độ trễ tăng ở đường forwarding/hybrid |
| Forwarding failures, upstream health | Chất lượng tuyến hybrid | Endpoint không hoạt động, vòng lặp hoặc packet drops |
| Record/zone/link changes | Bảo vệ tính toàn vẹn | Đổi A/CNAME/association ngoài kế hoạch |
| DNS query ở resolver ngoài được duyệt | Phát hiện rò truy vấn/private suffix | Tên prod/mgmt xuất hiện trên đường public |
| Cache hit ratio, TTL behavior nếu đo được | Tải DNS và mức phân tán truy vấn | Resolver chịu tải tăng sau hạ TTL |
| IPv4/IPv6 resolution coverage | Bao phủ dual stack | Client nhận AAAA không thể kết nối, hoặc IPv6 path thiếu policy |
| End-to-end synthetic lookup | Kết quả thực từ từng VPC/VNet/VPN | Zone còn tồn tại nhưng không còn nhìn thấy từ một mạng |

**Query logs chứa metadata về người dùng và hạ tầng.** Chỉ ghi những trường cần cho vận hành/an ninh, làm sạch dữ liệu nhạy cảm, áp RBAC, retention và audit khi export; không dùng log DNS làm kho lưu toàn bộ hành vi cá nhân nếu không có mục đích và quyền phù hợp.

### 14.2. Synthetic monitoring của private zone

Một health-check tốt không chỉ hỏi resolver central. Hãy kiểm tra **từ từng góc nhìn quan trọng**:

~~~text
Check-1: VM trong VPC production hỏi orders.prod.corp.example A.
Check-2: Client qua VPN hỏi cùng tên, kỳ vọng cùng private endpoint hoặc câu trả lời được duyệt.
Check-3: VM staging không được liên kết, kỳ vọng không nhận bản ghi production.
Check-4: VM management hỏi db.prod.corp.example theo phạm vi được cấp.
Check-5: Pod production hỏi DNS cluster rồi xác minh endpoint ứng dụng.
Check-6: Public client không nhận bản ghi private qua public DNS.
Check-7: DNS query từ VPC tới on-prem zone nếu cấu hình hybrid hai chiều.
Check-8: A/AAAA và DNS TCP fallback hoạt động đúng trên đường được phép.
~~~

Cần ghi cả **hostname, record type, rcode, answer, resolver, nguồn thử, latency và timestamp**. Một test ngoài VPC trả NXDOMAIN chưa chắc đủ chứng minh không thể kết nối IP private từ một đường VPN khác; tiếp tục kiểm tra network reachability theo sơ đồ bảo mật.

### 14.3. Vòng đời thay đổi DNS

Quy trình gợi ý:

1. **Yêu cầu:** mô tả dịch vụ, FQDN, record type, IP/target, zone, mạng nhìn thấy, owner và lý do thay đổi.
2. **Threat review:** liệu record/zone link có làm lộ dữ liệu, hướng lưu lượng tới endpoint khác, mở rộng quyền quản trị hoặc phá split DNS?
3. **Kiểm tra xung đột:** record hiện tại, CNAME/SOA/NS, zone chồng lấp, forwarder, DNSSEC policy và automations.
4. **Kế hoạch cutover:** TTL và negative caching, kết nối còn mở, route/backend mới và điều kiện rollback.
5. **Review/approval:** áp theo quy trình kiểm soát thay đổi của tổ chức.
6. **Triển khai:** dùng IaC/API/console với danh tính được cấp quyền tối thiểu; log thay đổi.
7. **Readback:** truy vấn record từ đúng nguồn mạng, kiểm tra A/AAAA/CNAME/SOA, hiệu lực forwarding và đường ứng dụng.
8. **Negative testing:** xác minh client/mạng không được cấp quyền không có DNS visibility hoặc application reachability trái phép.
9. **Theo dõi:** lỗi DNS, telemetry của ứng dụng, log thay đổi, số client còn dùng địa chỉ cũ.
10. **Rà soát:** bỏ record và zone links không còn dùng, thay đổi tài khoản owner, xác minh định kỳ.

### 14.4. Mẫu bản ghi thay đổi

| Trường | Giá trị minh họa |
| --- | --- |
| Change ID | DNS-PRIV-007 |
| Zone | prod.corp.example |
| FQDN | orders.prod.corp.example |
| Type / target | A → 10.30.20.15 |
| TTL | 300 giây |
| Visibility | VPC production và inbound resolver hybrid được duyệt |
| Record owner | Nhóm ứng dụng Orders |
| Zone owner | Nhóm network/platform |
| Quyền thực thi | Automation identity với quyền đúng record theo khả năng nền tảng |
| Policy liên quan | Firewall/microsegmentation tới TCP/443 |
| Test allow | App VPC prod và VPN được phê duyệt phân giải thành công |
| Test deny | VPC dev/public client không nhận private record trái phạm vi |
| Bằng chứng | Query log/redacted output, change audit, ứng dụng kết nối thành công |
| Rollback | Khôi phục record/association cũ và kiểm tra TTL/cache |
| Review | Theo kỳ kiểm tra zone và thay đổi service |

Lưu trữ cấu hình zone bằng **hệ thống quản lý cấu hình/IaC** khi phù hợp. Không lưu mật khẩu, secret của resolver hay khóa private trong change record, commit hoặc ví dụ tài liệu.

## 15. Bài lab: xây dựng và kiểm chứng một Private DNS zone giả lập

Mục tiêu của bài lab là hiểu bản ghi, phạm vi truy vấn, forwarding, negative caching và quan hệ giữa DNS với firewall. Có thể thực hiện trên **mạng ảo cô lập hoặc dịch vụ private DNS của cloud dùng tài khoản được cấp quyền**, không cần công bố bản ghi lên Internet.

### 15.1. Mô hình giả định

| Thành phần | Giá trị lab |
| --- | --- |
| Zone | prod.corp.example |
| Authoritative DNS/resolver lab | 10.60.0.10 |
| Secondary/backup DNS nếu triển khai | 10.60.0.11 |
| Orders API | orders.prod.corp.example → 10.30.20.15 |
| Orders DB | db.prod.corp.example → 10.30.40.10 |
| Alias API | api.prod.corp.example → orders.prod.corp.example |
| Client thuộc mạng được phép | 10.30.10.25 |
| Client thuộc mạng không được phép | Một VM/lab client chưa gắn zone hoặc chưa được cấp đường tới resolver |
| Chính sách kết nối | Client chỉ gọi Orders API trên TCP/443; chỉ Orders API được phép tới DB theo port đã thiết kế |

**Các IP ở đây dùng trong mạng riêng lab.** Không cấu hình resolver cho phép mọi nguồn Internet truy cập recursion; không thay cấu hình DNS production nếu không có quy trình và phạm vi ủy quyền.

### 15.2. Cấu trúc zone file minh họa

Nếu dùng một authoritative DNS server hỗ trợ zone file theo dạng phổ biến, dữ liệu minh họa có thể giống:

~~~dns
$ORIGIN prod.corp.example.
$TTL 300
@  IN SOA ns1.prod.corp.example. hostmaster.corp.example. (
          2026112801 ; serial
          3600       ; refresh
          900        ; retry
          604800     ; expire
          300        ; negative caching parameter
)
@      IN NS    ns1.prod.corp.example.
ns1    IN A     10.60.0.10
orders IN A     10.30.20.15
db     IN A     10.30.40.10
api    IN CNAME orders.prod.corp.example.
~~~

Đây là **zone data minh họa**, không gồm file cấu hình dịch vụ, view, ACL hay cách triển khai an toàn cho máy chủ DNS cụ thể. Khi dùng cloud private DNS, bạn thường tạo record và scope/link bằng API/IaC/console thay vì tải nguyên zone file này. Nếu dùng secondary DNS và zone transfer, cần bảo vệ các kết nối và quyền chuyển zone; không mặc định cho mọi client tải toàn bộ zone.

Đặc điểm cần phân tích:

- **SOA** mô tả dữ liệu điều hành zone và các tham số liên quan; hostmaster.corp.example. trong SOA là biểu diễn tên mailbox theo định dạng DNS.
- **NS** công bố nameserver có thẩm quyền cho zone; cách private cloud quản lý NS/SOA có thể do nhà cung cấp tự xử lý.
- **A** record trỏ tới IP riêng; không tự mở route.
- **CNAME** trỏ tới tên khác; resolver vẫn phải phân giải tên đích theo DNS policy.
- **TTL 300** khuyến nghị cache thông thường khoảng 5 phút theo dữ liệu record, không đảm bảo mọi runtime đổi kết nối sau 5 phút.
- **Serial** trong zone file là tham số cho quy trình cập nhật/đồng bộ theo cơ chế DNS truyền thống, không tương đương version của mọi managed cloud DNS.

### 15.3. Kịch bản kiểm thử từng bước

1. **Tạo zone private và record** trong lab ở phạm vi mạng production giả lập.
2. **Định phạm vi truy vấn**: chỉ liên kết zone hoặc cho phép resolver của mạng prod; chưa cấp quyền cho client ở vùng dev.
3. **Thử truy vấn A:** từ client prod, yêu cầu orders.prod.corp.example và ghi IP trả về.
4. **Thử truy vấn CNAME:** hỏi api.prod.corp.example, kiểm tra alias và IP cuối cùng.
5. **Thử record không tồn tại:** hỏi missing.prod.corp.example; ghi NXDOMAIN/NODATA, SOA và quan sát negative caching.
6. **Thử từ mạng không được cấp quyền:** xác minh mạng dev/public không nhận private record thông qua resolver/đường công khai ngoài thiết kế.
7. **Tạo forwarding hybrid giả lập:** client văn phòng hỏi thông qua resolver on-prem, chuyển suffix prod.corp.example đến inbound DNS endpoint được phép.
8. **Thử mạng ứng dụng:** DNS trả 10.30.20.15; client được cấp quyền gọi TCP/443 thành công nếu API sẵn sàng.
9. **Thử truy cập trái quyền:** từ client không thuộc nhóm DB, thử kết nối DB qua đúng port của lab và xác minh firewall/ACL từ chối.
10. **Đổi record có kiểm soát:** chuyển Orders API tới endpoint lab mới, đánh giá TTL, cache và kết nối cũ; có kế hoạch hoàn tác.
11. **Kiểm tra audit:** thay đổi record, zone association hoặc forwarding rule phải để lại dấu vết theo quyền của nền tảng.
12. **Khôi phục:** rollback record/association và kiểm tra lại tất cả vùng có liên quan.

### 15.4. Ma trận kết quả kỳ vọng

| Test ID | Nơi phát truy vấn / hành động | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- | --- |
| DNS-L01 | Client prod hỏi orders.prod.corp.example A | Trả 10.30.20.15 | Resolver, answer/TTL, timestamp |
| DNS-L02 | Client prod hỏi api.prod.corp.example | Thấy alias phù hợp và phân giải tới Orders API | CNAME chain và final A |
| DNS-L03 | Client prod hỏi missing.prod.corp.example A | NXDOMAIN theo cấu hình zone | Rcode, SOA/negative cache |
| DNS-L04 | Client dev không được liên kết hỏi cùng record | Không nhận private record ngoài phạm vi được duyệt | Resolver ID, query result, zone visibility |
| DNS-L05 | Client văn phòng được duyệt hỏi qua forwarder | Trả đúng record private | Query log on-prem và cloud inbound endpoint |
| DNS-L06 | Client văn phòng hỏi public hostname khác | Không bị forward sai vào private zone | Query path/log và response phù hợp |
| DNS-L07 | Resolver hybrid lỗi hoặc blocked TCP/53 | Phát hiện lỗi rõ và cảnh báo sức khỏe | SERVFAIL/timeout, flow log theo cơ chế test |
| DNS-L08 | Client prod gọi Orders API sau DNS | Kết nối theo TCP/TLS/authorization | DNS answer, route, TLS và API logs |
| DNS-L09 | Client không được cấp phép gọi DB trực tiếp | Bị firewall/SG/ACL từ chối | Hit counter và kiểm chứng không tới DB |
| DNS-L10 | Record Orders API đổi IP | Client được làm mới sau các điều kiện cache thích hợp | TTL, query mới, app retry và connection state |
| DNS-L11 | IPv6 client nếu có | AAAA/route và policy thống nhất với thiết kế | Dig/Resolve-DnsName AAAA, firewall IPv6 |
| DNS-L12 | Người không có quyền sửa private zone | Không thể thay bản ghi hoặc association | IAM deny và audit event (không thử ngoài quyền lab) |

**Mục tiêu kiểm tra:** chứng minh được sự khác nhau giữa *DNS visibility*, *network reachability* và *application authorization*. Nếu một client dev phân giải không được tên private, điều đó chưa chứng minh nó không thể kết nối tới IP private qua một đường VPN khác; cần kiểm tra firewall riêng.

## 16. Tình huống thực tế và cách phân tích

### Tình huống A — Thêm private zone, website public bất ngờ NXDOMAIN

Doanh nghiệp đã có public zone **example.com** với bản ghi portal.example.com. Nhóm hạ tầng tạo private zone **example.com** để lưu tên nội bộ, nhưng không sao chép những record public mà client VPC vẫn cần.

**Biểu hiện:** người dùng Internet vẫn phân giải được portal.example.com, nhưng workload ở VPC được liên kết với private zone lại nhận NXDOMAIN cho tên đó.

**Phân tích:** private zone đang được chọn cho tên thuộc suffix trùng, trong khi record portal.example.com thiếu ở góc nhìn private; resolver không tự fallback ra public DNS theo kỳ vọng. Giải pháp có thể là **tách private zone thành subdomain riêng**, hoặc quản lý đầy đủ những record cần thiết trong split-view, tùy nền tảng. Không chữa bằng cách mở mọi DNS egress ra public resolver rồi bỏ qua mô hình private DNS.

### Tình huống B — Client VPN không phân giải được tên cloud

Workload trong VPC truy vấn được **orders.prod.corp.example**, còn laptop qua VPN nhận SERVFAIL hoặc timeout.

**Phân tích:** kiểm tra resolver laptop đang dùng, DNS suffix policy của VPN, conditional forwarding tại DNS on-prem, inbound resolver endpoint của cloud, route VPN và UDP/TCP 53. Xem rule nào nhận truy vấn và có forwarding loop hay không. Sau khi DNS đúng, kiểm tra riêng ACL/TLS tới Orders API.

### Tình huống C — Pod phân giải được DB nhưng không thể kết nối

Pod ở namespace web truy vấn được **db.prod.corp.example → 10.30.40.10**, nhưng TCP/5432 bị timeout. Một kỹ sư đề xuất mở public DB để giải quyết.

**Phân tích:** việc DNS trả IP là bước độc lập; policy có thể đang chặn Web→DB **đúng theo nguyên tắc least privilege**. Kiểm tra ma trận kết nối: nếu chỉ Orders API cần DB, hãy giữ deny cho Web và chuyển giao tiếp qua Orders API đúng thiết kế. Không mở DB public hoặc nới zone chỉ để sửa hành vi chưa được phép.

### Tình huống D — Client DoH công khai không phân giải tên nội bộ

Một ứng dụng desktop cấu hình DoH trực tiếp đến resolver công khai. Trong khi DNS của VPN và private zone vẫn hoạt động, ứng dụng riêng đó báo không tìm thấy hostname private.

**Phân tích:** resolver public không được liên kết với zone nội bộ. Cần chọn resolver nội bộ có khả năng DoH/DoT nếu chính sách và công nghệ hỗ trợ, hoặc cấu hình client dùng đường phân giải doanh nghiệp theo thiết kế. Tránh tắt toàn bộ bảo vệ DNS chỉ để cho một ứng dụng đi qua.

### Tình huống E — Đổi private endpoint làm lỗi DNS sau rollout

Một private endpoint của dịch vụ lưu trữ được thay thế nhưng A/CNAME trong private zone vẫn trỏ IP cũ.

**Phân tích:** kiểm tra lifecycle endpoint, cơ chế cập nhật record tự động, zone association, cache và quyền service. Khôi phục record đúng và thử cả DNS lẫn kết nối TLS/authorization. Để tránh tái diễn, quản lý record theo vòng đời endpoint và bổ sung synthetic lookup từ các VNet/VPC quan trọng.

### Tình huống F — Query log cho thấy tên nội bộ bị hỏi ra DNS công khai

Trong log DNS egress, nhiều truy vấn với suffix **mgmt.corp.example** xuất hiện trên đường đến resolver không được duyệt.

**Phân tích:** đây là dấu hiệu cần điều tra cấu hình VPN split DNS, resolver của browser/ứng dụng, policy DoH, DHCP và forwarding. Đồng thời đánh giá mức nhạy cảm của các tên bị lộ. Chặn bừa bãi mọi HTTPS có thể gây gián đoạn; cần xác định endpoint, ứng dụng, danh tính workload và giải pháp egress theo chính sách.

### Tình huống G — Bản ghi DNS quản trị bị sửa trái phép

Một automation account có quyền sửa toàn bộ zone production vô tình hoặc trái phép thay địa chỉ của **auth.prod.corp.example**.

**Phân tích:** điều tra audit ai sửa, quyền IAM, phiên bản IaC, thời điểm cache và hành vi client. Khôi phục record đã được phê duyệt, thu hẹp quyền của automation và kiểm chứng certificate/TLS. Nếu có bằng chứng kết nối tới endpoint không được tin cậy, phối hợp nhóm ứng cứu để đánh giá hậu quả; không khẳng định credential đã bị đánh cắp chỉ vì record thay đổi.

## 17. Câu hỏi ôn tập

**Câu 1.** Private DNS zone khác public DNS zone ở điểm nào?

*Gợi ý:* Phạm vi resolver/mạng có thể nhìn thấy dữ liệu, cơ chế association/forwarding và chính sách truy cập; bản ghi không nhất thiết chứa IP private.

**Câu 2.** DNS trả địa chỉ DB cho một pod có chứng minh pod được quyền đọc database không?

*Gợi ý:* Không. DNS chỉ giúp tìm IP; firewall, NetworkPolicy, TLS và DB authorization quyết định kết nối và thao tác.

**Câu 3.** Vì sao VPC B không phân giải được private zone dù đã peering với VPC A?

*Gợi ý:* Network peering không tự tương đương private-zone association hoặc DNS forwarding/peering theo nền tảng; cần kiểm tra resolver path.

**Câu 4.** Vì sao tên public có thể trả NXDOMAIN trong VPC đã liên kết private zone trùng suffix?

*Gợi ý:* Resolver có thể chọn private zone trước, record thiếu trong zone đó nên trả kết quả âm mà không fallback public.

**Câu 5.** Một client VPN dùng DoH tới resolver public nhưng không tìm thấy tên private. DNS zone có chắc bị lỗi không?

*Gợi ý:* Không. Client có thể đang hỏi sai resolver; resolver public không có visibility của private zone.

**Câu 6.** DNSSEC và DoT khác nhau thế nào?

*Gợi ý:* DNSSEC xác thực/toàn vẹn dữ liệu DNS qua chữ ký và chuỗi tin cậy, còn DoT bảo vệ kênh DNS tới resolver bằng TLS; không thay nhau.

**Câu 7.** Khi chuyển record A sang IP mới, vì sao một số client vẫn dùng IP cũ?

*Gợi ý:* Cache ở hệ điều hành/recursive resolver/runtime, negative caching hoặc connection pool; TTL không tự buộc đóng các phiên đang mở.

**Câu 8.** Trong hybrid DNS, khi nào cần inbound và khi nào cần outbound resolver endpoint?

*Gợi ý:* Inbound phục vụ resolver tại chỗ hỏi tên cloud private; outbound giúp workload cloud hỏi các zone do DNS tại chỗ quản lý, theo khả năng nền tảng.

**Câu 9.** Có thể đặt mật khẩu vào TXT record của private zone vì “không ai trên Internet thấy” không?

*Gợi ý:* Không. Những client/resolver có quyền query, log và người quản trị zone có thể xem; dùng secret manager với quyền phù hợp.

**Câu 10.** Vì sao một lệnh dig +trace không chứng minh private DNS zone đang hoạt động đúng?

*Gợi ý:* Nó có thể đi theo đường phân cấp public và bỏ qua forwarding/zone association mà ứng dụng sử dụng; cần hỏi đúng resolver trong đúng mạng.

**Câu 11.** Sự khác nhau giữa NXDOMAIN và SERVFAIL là gì?

*Gợi ý:* NXDOMAIN biểu thị tên không tồn tại trong câu trả lời có thẩm quyền phù hợp; SERVFAIL là resolver không hoàn thành xử lý thành công, có nhiều nguyên nhân như upstream/validation.

**Câu 12.** Nếu tạo private endpoint thì endpoint public tự động bị vô hiệu hóa chưa?

*Gợi ý:* Không thể giả định. Cần kiểm tra thuộc tính network access riêng của dịch vụ, firewall, zone và route theo sản phẩm.

## 18. Tổng kết

- **Private DNS zone là cách giới hạn khả năng phân giải tên** đến những resolver/mạng được cấp quyền, không phải một cơ chế mã hóa hay phân quyền ứng dụng.
- **Split-horizon DNS** có thể trả đáp án khác nhau cho cùng tên; private zone chồng lấp public zone có thể tạo NXDOMAIN nếu bản ghi thiếu và nền tảng không fallback.
- **Zone association, resolver path, forwarding và route mạng** cần được thiết kế riêng; VPC/VNet peering hoặc VPN tồn tại không tự tạo DNS visibility.
- **Cloud private DNS** có nhiều mô hình: AWS Private Hosted Zone/Resolver, Azure Private DNS/VNet link/Private Resolver, Google Cloud DNS private zone/forwarding/peering; phải kiểm tra ngữ nghĩa cụ thể của từng nền tảng.
- **Kubernetes Service DNS và private zone cloud** là hai phạm vi tên khác nhau; pod có thể dùng CoreDNS và DNS forwarding nhưng vẫn phải chịu network policy và quyền ứng dụng.
- **DNSSEC, DoT/DoH, firewall, IAM và TLS ứng dụng** giải quyết những rủi ro khác nhau. DNSSEC không mã hóa, DoH public không tự phân giải được zone nội bộ và DNS private không thay xác thực dịch vụ.
- **An toàn của private zone phụ thuộc cả quyền sửa record, liên kết mạng, quyền truy vấn, DNS egress, log và audit**. Không đặt bí mật trong TXT record hoặc mở resolver như dịch vụ truy vấn công khai.
- **TTL/negative caching, forwarding loop, zone shadowing và DNS leakage** là nguồn lỗi thường gặp; luôn thử từ đúng client/resolver và phân biệt DNS response với kết nối ứng dụng.
- **Hoàn thành triển khai cần test cả allow và deny**, kiểm tra IPv4/IPv6, VPN/hybrid, private endpoints, TLS/authorization, quy trình đổi record, telemetry, trách nhiệm sở hữu và phương án rollback.
