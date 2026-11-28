# Giao thức quản trị và giao thức nghiệp vụ

Trong cùng một hạ tầng mạng, một gói tin có thể phục vụ hai mục đích rất khác nhau: nhân viên vận hành đăng nhập thiết bị để thay đổi cấu hình, hoặc ứng dụng xử lý đơn hàng cho khách. Cả hai đều dùng những giao thức mạng tiêu chuẩn, nhưng yêu cầu về **ai được truy cập, được làm gì, đi theo tuyến nào và phải ghi nhận ra sao** không giống nhau.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, phân biệt giao thức quản trị và giao thức nghiệp vụ giúp thiết kế mạng an toàn: phân đoạn hệ thống, cấu hình firewall, VPN, xác thực kết nối, giám sát IDS/IPS và phân tích lưu lượng. Khái niệm này cũng áp dụng khi quản lý DNS, mạng không dây và tài nguyên trên đám mây.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt giao thức quản trị, giao thức nghiệp vụ và giao thức phục vụ hạ tầng theo **mục đích sử dụng thực tế**.
- Liên hệ các giao thức này với mô hình OSI/TCP-IP và nhận diện những cổng mặc định thường gặp.
- Xác định đường đi, điểm kết thúc kết nối, danh tính và quyền tối thiểu cho lưu lượng quản trị và nghiệp vụ.
- Xây dựng ma trận truy cập giữa các vùng, bao gồm các luồng phải từ chối.
- Giải thích vì sao dùng HTTPS, VPN hay TLS không tự làm một kết nối trở nên đáng tin cậy.
- Lựa chọn cách ghi log, phân tích lưu lượng và kiểm thử ranh giới mạng khi triển khai hoặc điều tra sự cố.

## 2. Phân loại theo chức năng, không chỉ theo số cổng

### 2.1. Giao thức quản trị

**Giao thức quản trị** được dùng để quan sát, cấu hình, vận hành hoặc điều khiển hệ thống và thiết bị. Ví dụ:

- Quản trị viên dùng **SSH** để đăng nhập máy chủ hoặc thiết bị mạng.
- Bộ điều khiển dùng **NETCONF qua SSH** hoặc **RESTCONF qua HTTPS** để đọc và cập nhật cấu hình thiết bị.
- Hệ thống giám sát dùng **SNMP** để lấy số liệu hoặc nhận thông báo từ thiết bị.
- Nhân viên hỗ trợ dùng **RDP** để điều khiển máy tính Windows được cấp quyền.
- Hệ thống vận hành nhận **syslog**, sự kiện bảo mật và dữ liệu đo lường từ nhiều vùng mạng.

Các giao thức này có thể cấp khả năng điều khiển cấu hình, truy cập thông tin nhạy cảm hoặc ảnh hưởng đến toàn bộ hạ tầng. Vì vậy, lưu lượng quản trị thường cần vùng truy cập riêng, danh tính mạnh, phân quyền rõ, theo dõi phiên và giới hạn nguồn kết nối.

### 2.2. Giao thức nghiệp vụ

**Giao thức nghiệp vụ** chuyên chở yêu cầu và dữ liệu cần thiết để sản phẩm hoặc hoạt động của tổ chức vận hành. Ví dụ:

- **HTTPS** phục vụ trang web, REST API, ứng dụng di động hoặc giao tiếp giữa dịch vụ.
- **gRPC trên HTTP/2** phục vụ gọi hàm từ dịch vụ này sang dịch vụ khác.
- **PostgreSQL wire protocol** hay các giao thức cơ sở dữ liệu khác phục vụ truy vấn dữ liệu nghiệp vụ.
- **AMQP** kết nối dịch vụ gửi và nhận thông điệp qua message broker.
- **MQTT** truyền sự kiện từ cảm biến đến hệ thống xử lý, thường gặp ở IoT.
- **SMTP** truyền email theo luồng công việc, chẳng hạn gửi thông báo giao dịch.

Các giao thức này cần chính sách riêng về xác thực người dùng hoặc dịch vụ, quyền đối với đối tượng nghiệp vụ, bảo vệ dữ liệu, kiểm soát lỗi và chống lạm dụng.

### 2.3. Giao thức và dịch vụ hạ tầng hỗ trợ

Không phải lưu lượng nào cũng thuộc thuần túy một trong hai nhóm. **DNS** giúp phân giải tên, **DHCP** cấp thông số mạng, **NTP** đồng bộ thời gian, còn **syslog** chuyển nhật ký. Chúng hỗ trợ vận hành nhiều hệ thống và có thể nằm trên các ranh giới bảo mật quan trọng.

Một nhóm khác là **giao thức control plane**, chẳng hạn OSPF hoặc BGP, dùng để trao đổi thông tin định tuyến. Chúng điều khiển cách mạng chuyển tiếp gói tin nhưng không đồng nhất với việc quản trị thiết bị qua SSH/NETCONF. Phân biệt các nhóm giúp tránh nhầm giữa luồng định tuyến, luồng quản trị và luồng dữ liệu ứng dụng.

> **Quy tắc phân loại:** Hãy hỏi “Kết nối này thực hiện hành động gì và trên tài nguyên nào?” trước khi hỏi “Nó dùng giao thức hay cổng nào?” HTTPS trên cổng 443 có thể là website cho khách hàng, API nội bộ hoặc bảng điều khiển quản trị.

## 3. Vị trí trong mô hình OSI

Mô hình OSI cung cấp cách xem một kết nối ở nhiều lớp. Nó giúp đặt biện pháp bảo vệ đúng vị trí, nhưng bản thân OSI không quy định dịch vụ nào là “quản trị” hay “nghiệp vụ”.

| Lớp OSI | Ví dụ | Câu hỏi bảo mật cần xét |
| --- | --- | --- |
| L7 – Ứng dụng | SSH, HTTP(S), SNMP, SMTP, MQTT, giao thức cơ sở dữ liệu | Lệnh, API, dữ liệu và quyền ứng dụng có hợp lệ không? |
| L6 – Trình diễn | Mã hóa, định dạng và biểu diễn dữ liệu; thường tích hợp trong giao thức hiện đại | Dữ liệu có được mã hóa và xử lý định dạng an toàn không? |
| L5 – Phiên | Thiết lập và duy trì phiên logic; không luôn có lớp riêng trong TCP/IP | Phiên gắn với danh tính nào, hết hạn và bị thu hồi thế nào? |
| L4 – Giao vận | TCP, UDP, QUIC dùng UDP | Ai được khởi tạo kết nối đến cổng dịch vụ nào? |
| L3 – Mạng | IPv4/IPv6, định tuyến, IPsec ở mô hình triển khai liên quan | Subnet hoặc workload có đường đi và quyền qua ranh giới không? |
| L2 – Liên kết dữ liệu | Ethernet, VLAN, Wi-Fi và cơ chế truy cập lớp liên kết | Có tách đúng miền kết nối, kiểm soát truy cập mạng không? |
| L1 – Vật lý | Cáp, sóng vô tuyến, cổng vật lý | Có nguy cơ truy cập vật lý hoặc kết nối không được quản lý không? |

Trong mô hình TCP/IP thực tế, HTTP, SSH, SNMP và các giao thức ứng dụng thường được gọi chung là **giao thức tầng ứng dụng**; TLS không phải một lớp OSI độc lập cố định. Phân loại lớp giúp suy luận, còn điểm thực thi bảo mật cụ thể tùy công nghệ.

Ví dụ, tường lửa L3/L4 có thể chặn từ Internet tới TCP 22. Tuy nhiên, nếu quản trị API và API nghiệp vụ đều dùng HTTPS 443, chỉ nhìn IP và cổng chưa đủ để xác định chính xác **người dùng, endpoint và thao tác**. Khi đó cần thêm gateway, xác thực danh tính, phân quyền L7 và nhật ký ứng dụng.

## 4. Các giao thức quản trị thường gặp

Số cổng trong bảng là **giá trị thông dụng**, không phải quy tắc bắt buộc của mọi hệ thống. Một dịch vụ có thể được cấu hình cổng khác hoặc hoạt động sau proxy.

| Giao thức / dịch vụ | Giao vận và cổng thường gặp | Công dụng | Kiểm soát khuyến nghị |
| --- | --- | --- | --- |
| SSH | TCP 22 | Truy cập dòng lệnh, thực thi lệnh, truyền tệp qua SFTP | Khóa hoặc cơ chế xác thực mạnh; giới hạn nguồn; ghi log; quản trị qua bastion khi phù hợp |
| NETCONF qua SSH | TCP 830 | Đọc, sửa cấu hình thiết bị bằng mô hình dữ liệu | Danh tính máy/người quản trị, phân quyền thao tác, kiểm toán thay đổi |
| RESTCONF | HTTPS, thường TCP 443 | Quản lý cấu hình/trạng thái thiết bị qua API | TLS hợp lệ, xác thực, phân quyền tài nguyên và log API |
| SNMP | Thường UDP 161 (truy vấn), UDP 162 (thông báo) | Thu thập chỉ số, trạng thái và thông báo sự kiện | Ưu tiên SNMPv3 với xác thực và mã hóa (authPriv) |
| RDP | TCP/UDP 3389 thông dụng | Điều khiển máy Windows từ xa | Truy cập qua kênh kiểm soát, NLA/xác thực mạnh, giới hạn nhóm người dùng |
| WinRM | HTTP 5985 hoặc HTTPS 5986 thông dụng | Quản trị Windows từ xa | Cấu hình xác thực mạnh, ưu tiên kênh bảo vệ thích hợp, giới hạn nguồn |
| Syslog | UDP 514; syslog qua TLS thường TCP 6514 | Chuyển nhật ký sự kiện đến hệ thống tập trung | Bảo vệ truyền tải, xác thực điểm nhận khi có hỗ trợ, giới hạn nguồn và quản lý lưu trữ |

**Chú ý về SNMP:** SNMPv1/v2c dùng *community string* và không cung cấp cơ chế bảo vệ tương đương SNMPv3 authPriv. Việc đổi community string không thay thế mã hóa. Nếu phải duy trì phiên bản cũ, cần cô lập đường truyền và giới hạn chặt nguồn được phép trong khi có kế hoạch nâng cấp.

**Chú ý về syslog:** Syslog truyền nhật ký là lưu lượng phục vụ vận hành/quan sát, nhưng bản thân nó không cấp chức năng điều khiển thiết bị. Luồng nhật ký thường theo chiều **thiết bị → log collector**, trong khi truy vấn SNMP thường theo chiều **monitoring → thiết bị**. Đặt nhầm chiều sẽ khiến hệ thống giám sát mất dữ liệu hoặc vô tình mở quyền không cần thiết.

## 5. Các giao thức nghiệp vụ thường gặp

| Giao thức / dịch vụ | Giao vận và cổng thường gặp | Ví dụ nghiệp vụ | Kiểm soát khuyến nghị |
| --- | --- | --- | --- |
| HTTPS | HTTP/1.1 hoặc HTTP/2 qua TLS trên TCP 443; HTTP/3 qua QUIC/UDP 443 | Web, REST API, thanh toán, dịch vụ nội bộ | TLS đúng cấu hình, xác thực, phân quyền từng yêu cầu, chống lạm dụng API |
| gRPC | Phổ biến qua HTTP/2, thường TLS/TCP 443 hoặc cổng riêng | Gọi dịch vụ nội bộ | Danh tính workload, mTLS khi phù hợp, phân quyền phương thức |
| PostgreSQL | TCP 5432 mặc định | Ứng dụng truy vấn cơ sở dữ liệu | Cho phép đúng máy ứng dụng; TLS nếu cần; tài khoản và quyền SQL tối thiểu |
| MySQL | TCP 3306 mặc định | Ứng dụng đọc/ghi dữ liệu | Giới hạn nguồn, bảo vệ kết nối và phân quyền trong DB |
| AMQP 0-9-1 | TCP 5672; qua TLS thường 5671 | Hàng đợi đơn hàng, gửi sự kiện | TLS, tài khoản theo dịch vụ, quyền publish/consume theo queue hoặc exchange |
| MQTT | TCP 1883; qua TLS thường 8883 | Thiết bị gửi dữ liệu cảm biến | Xác thực thiết bị, mã hóa, quyền publish/subscribe theo topic |
| SMTP | TCP 25 cho chuyển tiếp giữa máy chủ; 587 cho submission; 465 cho submission qua TLS ngầm | Thư xác nhận, thông báo hệ thống | Chống gửi thư trái phép, xác thực ở điểm submission, mã hóa theo chính sách |

Một số giao thức có thể phục vụ **cả hai mục đích** tùy bối cảnh. HTTPS có thể phục vụ trang quản trị firewall; SSH/SFTP có thể dùng cho một luồng trao đổi tệp nghiệp vụ được kiểm soát; MQTT có thể vừa cung cấp dữ liệu cảm biến vừa cho phép gửi lệnh điều khiển thiết bị. Khi phân loại, phải xét tài khoản gọi, tài nguyên đích, mức đặc quyền và thao tác cụ thể.

Không nên suy luận “TCP 443 thì an toàn” hoặc “giao thức dùng TLS thì không cần kiểm soát khác”. TLS chủ yếu bảo vệ đường truyền và xác thực đầu cuối theo cấu hình; nó **không tự quyết định** người dùng được xem đơn hàng của ai hay API có được phép sửa cấu hình thiết bị hay không.

## 6. Tách luồng quản trị và luồng nghiệp vụ trong kiến trúc mạng

Xét doanh nghiệp có ứng dụng thương mại điện tử và hệ thống quản lý hạ tầng. Các vùng phục vụ những chức năng khác nhau:

- **Public/DMZ:** reverse proxy, web gateway, điểm tiếp nhận kết nối công khai.
- **Application:** API và dịch vụ xử lý đơn hàng.
- **Data:** cơ sở dữ liệu nghiệp vụ.
- **Management:** bastion, hệ thống quản trị, máy giám sát và công cụ điều phối.
- **Network devices:** firewall, switch, router, thiết bị Wi-Fi được quản lý.

~~~mermaid
flowchart TB
    U["Khách hàng / Internet"] -->|"HTTPS:443"| W["Public/DMZ: Web gateway"]
    W -->|"HTTPS API:8443"| A["Application: Order API"]
    A -->|"PostgreSQL:5432"| D[("Data: Order DB")]

    O["Nhân viên vận hành"] -->|"VPN / ZTNA + MFA"| B["Management: Bastion"]
    B -->|"SSH:22 / NETCONF:830"| N["Router / Switch / Firewall"]
    B -->|"SSH:22 (theo quyền)"| S["Máy chủ ứng dụng"]
    N -->|"Syslog TLS:6514"| L["Management: Log collector"]
    M["Management: Monitoring"] -->|"SNMPv3:161"| N
~~~

Sơ đồ mô tả **luồng logic được xét duyệt**, không yêu cầu mỗi hộp phải có một thiết bị mạng vật lý riêng. Trên thực tế, firewall, ACL, security group, định tuyến và kiểm soát trên workload phải phối hợp để thực thi chính sách.

Các kết nối nghiệp vụ đi từ gateway đến API và cơ sở dữ liệu. Đường quản trị bắt đầu từ danh tính vận hành, đi qua điểm truy cập được bảo vệ, rồi tới đúng máy hoặc thiết bị được phép. Việc API nằm trên cùng máy với dịch vụ SSH **không có nghĩa** các client gọi API được phép kết nối SSH đến máy đó.

### 6.1. Ví dụ ma trận luồng cho phép và từ chối

| Nguồn khởi tạo | Đích | Giao thức / cổng | Quyết định | Điều kiện |
| --- | --- | --- | --- | --- |
| Khách bên ngoài | Web gateway | HTTPS / TCP 443 (hoặc HTTP/3 nếu được hỗ trợ) | Cho phép | Endpoint công khai đã công bố, kiểm soát API tại L7 |
| Web gateway | Order API | HTTPS / TCP 8443 | Cho phép có điều kiện | Xác thực dịch vụ, chỉ gọi API cần thiết |
| Order API | Order DB | PostgreSQL / TCP 5432 | Cho phép có điều kiện | Nguồn API xác định; tài khoản DB chỉ có quyền nghiệp vụ |
| Nhân viên vận hành hợp lệ | Điểm truy cập quản trị | VPN/ZTNA theo cấu hình | Cho phép có điều kiện | MFA, danh tính và trạng thái thiết bị theo chính sách |
| Bastion | Router/switch được phân quyền | SSH / TCP 22, NETCONF / TCP 830 | Cho phép có điều kiện | Phiên được ghi nhận, tài khoản có đặc quyền phù hợp |
| Monitoring | Thiết bị được giám sát | SNMPv3 / UDP 161 | Cho phép có điều kiện | Chỉ tài khoản giám sát, SNMPv3 authPriv |
| Thiết bị mạng | Log collector | Syslog qua TLS / TCP 6514 | Cho phép có điều kiện | Chỉ collector được xác định; bảo vệ đường truyền |
| Internet | Thiết bị mạng / bastion | SSH, RDP, NETCONF | Từ chối | Giao diện quản trị không công khai |
| Web gateway / API | Thiết bị mạng | SSH, SNMP, NETCONF | Từ chối mặc định | Không có nhu cầu nghiệp vụ |
| Internet / DMZ | Order DB | Giao thức cơ sở dữ liệu | Từ chối | Không cho bỏ qua tầng ứng dụng |

Ma trận xác định **chiều khởi tạo kết nối**. Với firewall theo dõi trạng thái, gói tin phản hồi của một phiên hợp lệ thường được xử lý theo trạng thái kết nối. Những giao thức dùng nhiều kết nối hoặc phương thức thông báo riêng phải được xét theo hành vi thực tế, không suy ra tất cả luồng hai chiều đều được tự do khởi tạo.

### 6.2. Mô hình chính sách minh họa

Đoạn YAML dưới đây là **mô tả chính sách độc lập với sản phẩm**, không phải cấu hình có thể nạp trực tiếp cho firewall:

~~~yaml
defaultAction: deny
flows:
  - id: customer-web
    source: public-clients
    destination: dmz/web-gateway
    protocol: tcp
    port: 443
    purpose: business
    action: allow

  - id: web-to-order-api
    source: dmz/web-gateway
    destination: app/order-api
    protocol: tcp
    port: 8443
    purpose: business
    requirements: [service-authentication, api-authorization]
    action: allow

  - id: bastion-to-network-device
    source: management/bastion
    destination: network-devices/approved-targets
    protocol: tcp
    port: 22
    purpose: administration
    requirements: [strong-authentication, least-privilege, session-audit]
    action: allow

  - id: monitoring-to-network-device
    source: management/monitoring
    destination: network-devices/approved-targets
    protocol: udp
    port: 161
    purpose: monitoring
    requirements: [snmpv3-auth-priv]
    action: allow
~~~

**Một cổng là điều kiện lọc mạng, không phải chứng nhận về chức năng.** Khi triển khai, phải ánh xạ các nhãn thành IP, danh tính workload hoặc đối tượng chính sách thật; kiểm tra đường định tuyến; đồng thời thực thi các yêu cầu xác thực/phân quyền tại đúng ứng dụng hoặc thiết bị.

## 7. Bảo vệ giao thức quản trị

### 7.1. Dùng mạng hoặc đường truy cập quản trị có kiểm soát

Nên tách quyền truy cập giao diện quản trị khỏi đường vào của người dùng nghiệp vụ. Có thể sử dụng VLAN/subnet quản trị, bastion, VPN hoặc ZTNA, security group riêng, firewall host và hệ thống xác thực tập trung. Mục tiêu là chỉ thiết bị và danh tính được phép mới đến được giao diện quản trị.

**Out-of-band management** là đường quản lý độc lập với mạng dịch vụ chính, hữu ích khi cần khắc phục sự cố hạ tầng. Tuy nhiên, mạng quản trị riêng vẫn cần xác thực, phân quyền và giám sát; việc tách vật lý không làm nó tự an toàn.

### 7.2. Xác thực, phân quyền và quản lý đặc quyền

- Dùng MFA cho đường truy cập quản trị khi có thể; hạn chế tài khoản dùng chung và định danh rõ người vận hành.
- Ưu tiên khóa SSH hoặc cơ chế xác thực mạnh; bảo vệ khóa và thông tin xác thực, thu hồi ngay khi không còn quyền.
- Phân quyền lệnh, nhóm thiết bị và phạm vi cấu hình theo công việc; hạn chế đăng nhập toàn quyền.
- Quản lý chứng thư, khóa API và bí mật của bộ điều khiển tự động; không lưu chúng trực tiếp trong mã nguồn hoặc log.
- Ghi nhận yêu cầu thay đổi, tài khoản sử dụng, thời điểm, thiết bị đích và kết quả tác vụ.

Một kết nối SSH có mã hóa vẫn có thể gây thiệt hại nếu người dùng sở hữu tài khoản đặc quyền bị lộ. Mã hóa bảo vệ kênh truyền; **phân quyền và kiểm toán** bảo vệ hành động được thực hiện qua kênh đó.

### 7.3. Giảm bề mặt tấn công

Tắt dịch vụ quản trị không dùng đến; không công bố SSH, RDP hoặc giao diện cấu hình trực tiếp ra Internet nếu không có yêu cầu và cơ chế bảo vệ tương xứng. Ưu tiên giao thức và chế độ xác thực hiện đại, cập nhật bản vá, giới hạn nguồn truy cập và tránh bật cả giao thức quản trị cũ lẫn giao thức mới một cách không cần thiết.

Với thiết bị Wi-Fi, lưu lượng khách nối vào SSID của khách cần bị cách ly khỏi giao diện quản trị access point/controller. Với hạ tầng đám mây, cần bảo vệ **cloud management API** bằng IAM, xác thực mạnh, phân quyền theo tài nguyên, log hoạt động và chính sách tổ chức. Các API quản trị đám mây có thể truy cập qua Internet dưới dạng HTTPS, nên một subnet quản trị riêng **không đủ** để kiểm soát toàn bộ quyền điều hành cloud.

## 8. Bảo vệ giao thức nghiệp vụ

### 8.1. Xác thực và phân quyền ở tầng ứng dụng

Trong API đơn hàng, việc client có thể kết nối HTTPS tới server không có nghĩa client được xem hoặc sửa đơn hàng của người khác. Ứng dụng cần xác thực caller và kiểm tra **quyền đối với từng tài nguyên/hành động**. Dịch vụ nội bộ cũng cần danh tính riêng; một máy nằm trong application zone không được mặc nhiên xem là đáng tin cậy.

Đối với cơ sở dữ liệu, tài khoản ứng dụng nên chỉ có quyền cần thiết, dùng cơ chế bảo vệ kết nối phù hợp và không sử dụng tài khoản quản trị DB cho luồng nghiệp vụ hằng ngày. Với message broker, quyền publish/subscribe phải giới hạn theo queue, topic hoặc phạm vi nghiệp vụ.

### 8.2. Bảo vệ dữ liệu và chống lạm dụng

Ưu tiên TLS với xác thực điểm cuối đúng, quản lý vòng đời chứng thư và chống cấu hình mã hóa yếu. Đặt giới hạn tốc độ và kích thước yêu cầu thích hợp; kiểm soát đầu vào, tránh lộ dữ liệu qua log và quan sát các lỗi xác thực/phân quyền. Sử dụng WAF hoặc bảo vệ API tại điểm có ý nghĩa nhưng vẫn phải kiểm soát logic nghiệp vụ trong ứng dụng.

Đối với giao thức chạy qua UDP hoặc kết nối lâu dài như MQTT, cần xét giới hạn tài nguyên, quản lý phiên, quyền của từng thiết bị và trường hợp thiết bị bị chiếm quyền. Các biện pháp đó bổ sung cho firewall và IDS/IPS.

### 8.3. Phân đoạn giữa các dịch vụ nghiệp vụ

Không mở toàn bộ dải application zone đến data zone. Chỉ những workload cần truy cập DB mới được phép kết nối tới đúng đích và cổng; đồng thời DB kiểm tra danh tính và quyền. **Microsegmentation** giúp kiểm soát lưu lượng đông–tây (east–west) giữa workload, kể cả khi chúng ở cùng mạng ảo hoặc cùng cụm triển khai.

## 9. Phân tích lưu lượng và giám sát hai nhóm giao thức

Muốn đánh giá một kết nối, trước tiên cần biết **ai khởi tạo, đích ở đâu, dùng giao thức gì, thời điểm nào và mục đích dự kiến là gì**. Các nguồn dữ liệu thường gồm flow log, firewall log, log VPN/ZTNA, DNS log, sự kiện IDS/IPS, nhật ký xác thực và log ứng dụng.

| Dấu hiệu quan sát | Cách diễn giải có thể xảy ra | Kiểm tra bổ sung |
| --- | --- | --- |
| Máy chủ web bắt đầu kết nối TCP 22 đến nhiều thiết bị mạng | Có thể là dò quét đường quản trị hoặc cấu hình sai | Đối chiếu danh sách luồng cho phép, danh tính nguồn, log firewall |
| Nhiều lần SSH thất bại từ mạng người dùng tới bastion | Có thể là nhập sai, tự động hóa lỗi hoặc thử đăng nhập trái phép | Kiểm tra tài khoản, địa chỉ nguồn, MFA, mốc thời gian |
| Bộ giám sát đột ngột gửi nhiều truy vấn SNMP tới thiết bị lạ | Có thể là thay đổi cấu hình giám sát hoặc lạm dụng thông tin xác thực | So sánh inventory, lịch thay đổi và đích UDP 161 |
| Order API phát sinh truy vấn DB tăng đột biến | Có thể do tải thật, lỗi ứng dụng hoặc lạm dụng API | Ghép log API, metric DB, tài khoản và loại truy vấn |
| Dữ liệu ra ngoài tăng mạnh trên HTTPS | Có thể là tải hợp lệ hoặc rò rỉ dữ liệu | Xác định dịch vụ đích, danh tính, dung lượng và hành vi ứng dụng |
| Thiết bị mạng ngừng gửi log về collector | Có thể lỗi kết nối, cấu hình hoặc thao tác che giấu dấu vết | Kiểm tra sức khỏe collector, tuyến, chứng thư và log tại nguồn |

Số cổng giúp **lọc sơ bộ** nhưng không đủ kết luận loại lưu lượng: TCP 443 có thể là API quản trị, API nghiệp vụ hoặc ứng dụng khác; lưu lượng có thể qua NAT, proxy hoặc được mã hóa. IDS/IPS và công cụ phân tích phải kết hợp metadata, danh tính, bối cảnh tài sản và nhật ký L7 để giảm cảnh báo sai.

### Ví dụ bộ lọc khi phân tích gói tin

Trong Wireshark, các bộ lọc hiển thị dưới đây hỗ trợ kiểm tra **lưu lượng được phép thu thập**:

~~~text
tcp.port == 22
tcp.port == 830
udp.port == 161 || udp.port == 162
tcp.port == 5432
tcp.port == 443 || udp.port == 443
~~~

Đây là bộ lọc dựa trên cổng, **không phải bộ nhận dạng chắc chắn giao thức hoặc ý định**. Ví dụ, TLS có thể che nội dung yêu cầu; muốn biết một lệnh quản trị đã thực thi hay API đã sửa tài nguyên nào cần đọc log ở đầu cuối tương ứng. Trên hạ tầng sản xuất, thu thập gói tin phải tuân thủ phạm vi được ủy quyền và chính sách bảo vệ dữ liệu.

## 10. Kịch bản phân tích rủi ro

### 10.1. Máy chủ ứng dụng bị chiếm quyền

Giả sử kẻ tấn công khai thác được một API nằm trong application zone. Từ đó, chúng thử kết nối SSH tới router và cơ sở dữ liệu.

**Đường đến router:** Chính sách app → network management phải từ chối SSH, NETCONF, SNMP và các giao thức quản trị khi không có mục đích rõ ràng. IDS/IPS hoặc flow log có thể cảnh báo hành vi máy chủ ứng dụng bất ngờ liên hệ với các cổng quản trị.

**Đường đến DB:** API có thể vẫn được phép kết nối TCP 5432 để làm nghiệp vụ. Do đó, firewall một mình không loại bỏ rủi ro; tài khoản DB chỉ có quyền tối thiểu, API kiểm tra phân quyền, và hệ thống cần theo dõi truy vấn bất thường.

**Bài học:** Cùng một máy bị chiếm quyền có thể thử tấn công cả đường quản trị lẫn nghiệp vụ; mỗi đường cần ranh giới mạng và kiểm soát danh tính/hành động riêng.

### 10.2. Tài khoản vận hành bị đánh cắp

Tài khoản có quyền SSH vào máy chủ hoặc thay đổi cấu hình firewall có thể gây ảnh hưởng lớn ngay cả khi mạng nghiệp vụ đã phân đoạn. Giảm thiểu bằng MFA, quyền theo vai trò, tài khoản riêng, phiên truy cập được ghi nhận, giới hạn thời gian cấp quyền và cơ chế thu hồi nhanh. Những thay đổi nhạy cảm có thể cần phê duyệt trong quy trình vận hành.

### 10.3. Giao diện quản trị bị công bố nhầm

Một nhóm triển khai dịch vụ mới có thể mở TCP 443 từ Internet đến giao diện quản trị vì “đó là HTTPS”. Cách phát hiện là kiểm kê điểm kết thúc TLS, tên miền, đường dẫn API, chủ sở hữu hệ thống và chính sách truy cập; kiểm thử xem tài nguyên quản trị có lộ ra ngoài phạm vi cho phép không. Biện pháp khắc phục là giới hạn kênh truy cập quản trị theo danh tính và nguồn phù hợp, đồng thời giữ các endpoint công khai cần thiết cho nghiệp vụ.

## 11. Quy trình xác minh thiết kế và cấu hình

Có thể dùng quy trình sau khi xây dựng hệ thống hoặc rà soát thay đổi:

1. **Kiểm kê dịch vụ:** Liệt kê giao thức, cổng thực tế, máy chủ đích, người hoặc workload gọi, dữ liệu và mức đặc quyền. Không mặc định phân loại theo tên cổng.
2. **Đánh dấu chức năng:** Với từng luồng, ghi rõ nghiệp vụ, quản trị, quan sát/hạ tầng hoặc control plane. Trường hợp đa chức năng cần tách quyền theo thao tác.
3. **Vẽ trust zone:** Xác định public, DMZ, application, data, management, network devices và các điểm giao nhau, kể cả VPN/cloud.
4. **Lập ma trận cho phép/từ chối:** Chỉ mở các đường cần thiết, ghi nhận người sở hữu và mục đích; quy định hành vi mặc định khi chưa có rule.
5. **Xác định điểm thực thi:** Kiểm tra tuyến mạng có đi qua firewall/security group/host firewall đúng như dự kiến; kiểm tra thêm xác thực và phân quyền L7.
6. **Kiểm thử tích cực:** Xác minh các luồng nghiệp vụ hợp lệ, truy cập quản trị được ủy quyền, giám sát và luồng gửi log vẫn hoạt động.
7. **Kiểm thử tiêu cực:** Từ máy nghiệp vụ, thử kết nối đến cổng quản trị bị cấm; từ bên ngoài, thử đường trực tiếp đến DB hoặc giao diện quản trị trong phạm vi kiểm thử đã cấp phép.
8. **Quan sát và rà soát:** Lưu log allow/deny, xác thực và hành động quản trị; xác minh cảnh báo cho đường đi lạ, rà soát rule dư thừa và thời hạn ngoại lệ.

Ví dụ kiểm thử cho kiến trúc ở mục 6:

| Tình huống | Kỳ vọng |
| --- | --- |
| Khách hàng truy cập HTTPS web gateway | Thành công với yêu cầu hợp lệ |
| Web gateway gọi API nghiệp vụ bằng danh tính hợp lệ | Thành công đúng quyền |
| Nhân viên không có quyền quản trị thử SSH vào router | Bị từ chối và có sự kiện để kiểm tra |
| Order API thử NETCONF đến thiết bị mạng | Bị chặn do không thuộc luồng cho phép |
| Monitoring gửi truy vấn SNMPv3 hợp lệ đến thiết bị được quản lý | Nhận được kết quả được cấp quyền |
| Thiết bị mạng gửi syslog qua TLS đến collector | Collector nhận được sự kiện và bảo vệ được kênh truyền |
| Internet kết nối trực tiếp vào DB hoặc SSH của máy nội bộ | Bị từ chối |

Nếu một phép thử thất bại, cần xác định vấn đề nằm ở định tuyến, firewall, chứng thư, xác thực, phân quyền hay ứng dụng. **Kết nối TCP thành công** không đồng nghĩa **yêu cầu được phép thực hiện**; ngược lại, gói bị chặn tại mạng không chứng minh rằng ứng dụng phía sau đã được cấu hình an toàn.

## 12. Câu hỏi tự kiểm tra

1. Một hệ thống dùng HTTPS 443 cho cả website công khai và trang quản trị thiết bị. Vì sao không thể dùng số cổng để quyết định chính sách?
2. SNMP polling và syslog forwarding có cùng chiều khởi tạo kết nối không? Nếu khác, điều đó ảnh hưởng thế nào tới firewall?
3. Vì sao nên hạn chế đường SSH từ application zone tới thiết bị mạng dù ứng dụng có thể cần truy cập Internet để phục vụ khách hàng?
4. Một API có TLS hợp lệ và firewall cho phép TCP 443. Những kiểm soát nào vẫn cần thiết để tránh người dùng xem dữ liệu của nhau?
5. Khi triển khai trên cloud, vì sao cần kiểm soát IAM đối với API quản lý tài nguyên dù đã có mạng quản trị riêng?
6. Lưu lượng DNS và BGP nên được gọi chung là giao thức quản trị thiết bị không? Giải thích chức năng từng loại.

**Gợi ý trả lời:** (1) Chức năng, danh tính và quyền ở L7 khác nhau; (2) SNMP polling thường từ monitoring đến thiết bị UDP 161, còn syslog thường từ thiết bị đến collector; (3) giảm khả năng di chuyển ngang và thay đổi hạ tầng khi máy nghiệp vụ bị chiếm; (4) xác thực người dùng, phân quyền đối tượng, kiểm soát API và nhật ký; (5) quyền cloud management API dựa trên danh tính/chính sách cloud và có thể hoạt động ngoài đường mạng nội bộ; (6) DNS là dịch vụ phân giải tên, BGP là giao thức trao đổi định tuyến thuộc control plane, không đồng nhất với SSH/NETCONF.

## 13. Những điều cần ghi nhớ

- **Mục đích và mức đặc quyền** quyết định một luồng là quản trị hay nghiệp vụ; số cổng chỉ là một tín hiệu kỹ thuật.
- **Mạng quản trị cần được bảo vệ độc lập với mạng dịch vụ.** Kiểm soát danh tính, phân quyền và ghi nhận hoạt động quản trị là trọng tâm.
- **Giao thức nghiệp vụ cũng cần phòng vệ nhiều lớp.** Firewall, TLS, xác thực dịch vụ và kiểm tra quyền đối tượng bảo vệ các phần khác nhau của cùng kết nối.
- **Phân loại đúng lưu lượng hỗ trợ phát hiện bất thường.** Ví dụ, máy chủ web truy cập NETCONF của switch là tín hiệu cần điều tra.
- **OSI giúp đặt câu hỏi đúng ở từng lớp.** Muốn kết luận an toàn phải kết hợp tuyến mạng, cổng, danh tính, hành động ứng dụng và bằng chứng quan sát thực tế.
