# Network segmentation là gì?

**Network segmentation** (phân đoạn mạng) là việc chia một hệ thống mạng thành những **phân đoạn có ranh giới kiểm soát lưu lượng riêng**, rồi quy định những kết nối nào được phép đi **trong cùng phân đoạn** và **giữa các phân đoạn**. Mỗi phân đoạn có thể đại diện cho nhóm thiết bị, hệ thống nghiệp vụ, mức độ nhạy cảm của dữ liệu, vai trò quản trị hoặc một vùng có mức độ tin cậy khác nhau.

Ví dụ, máy tính khách đến văn phòng chỉ cần dùng Internet; máy chủ ứng dụng cần kết nối đến cơ sở dữ liệu; nhân viên quản trị cần truy cập một số giao diện điều hành. Nếu tất cả thiết bị cùng chia sẻ một mạng phẳng và kết nối được với nhau không hạn chế, một thiết bị bị chiếm quyền có thể trở thành điểm xuất phát để dò tìm và tiếp cận nhiều tài sản khác. Phân đoạn mạng giới hạn những đường đi đó theo **nhu cầu thực tế của từng hệ thống**.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, đây là nền tảng cho phòng vệ nhiều lớp: kết hợp thiết kế trust zone, firewall và ACL, kiểm soát VPN, phân tích lưu lượng, IDS/IPS, xác thực kết nối, bảo vệ mạng không dây, DNS và hệ thống đám mây. Phân đoạn giúp giảm phạm vi ảnh hưởng khi xảy ra sự cố, nhưng vẫn phải phối hợp với quản lý danh tính, vá lỗi và bảo vệ ứng dụng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích network segmentation, lợi ích và giới hạn của nó.
2. Phân biệt phân đoạn vật lý, VLAN/subnet, phân đoạn theo vùng và microsegmentation.
3. Giải thích vai trò khác nhau của VLAN, định tuyến, firewall, ACL và kiểm soát truy cập dựa trên danh tính.
4. Đọc sơ đồ trust zone, nhận diện lưu lượng giữa các vùng và lập ma trận cho phép/từ chối.
5. Thiết kế phân đoạn cho hệ thống web nhiều tầng, mạng khách, quản trị, VPN hoặc tài nguyên cloud.
6. Kiểm thử đường đi hợp lệ, đường đi bị cấm và phát hiện cấu hình khiến phân đoạn mất tác dụng.

## 2. Hiểu đúng khái niệm segmentation

### 2.1. Mạng phẳng và mạng được phân đoạn

Trong **mạng phẳng** (*flat network*), nhiều thiết bị nằm trong một miền liên lạc rộng và có ít chính sách hạn chế kết nối giữa chúng. Thuật ngữ này mô tả cách bố trí và mức kiểm soát; một subnet chung không nhất thiết có nghĩa mọi kết nối đều được phép nếu đã áp dụng host firewall hoặc chính sách khác.

Trong **mạng được phân đoạn**, các nhóm tài sản được tách ra theo chức năng hoặc rủi ro, đồng thời kết nối qua ranh giới được điều khiển bằng quy tắc cụ thể. Ví dụ:

| Nhóm tài sản | Mục đích | Nhu cầu kết nối điển hình |
| --- | --- | --- |
| Người dùng nội bộ | Truy cập ứng dụng, công cụ làm việc | HTTPS tới ứng dụng và một số dịch vụ hạ tầng |
| Khách/thiết bị không quản lý | Truy cập Internet cơ bản | Không được kết nối trực tiếp tới hệ thống nội bộ |
| DMZ | Tiếp nhận lưu lượng từ ngoài | Chỉ gọi các API nội bộ được khai báo |
| Application | Xử lý nghiệp vụ | Đến cơ sở dữ liệu và dịch vụ phụ trợ đã chỉ định |
| Data | Lưu dữ liệu quan trọng | Chỉ phục vụ ứng dụng và tác vụ quản trị được phê duyệt |
| Management | Quản trị và giám sát | Đường truy cập đặc quyền, tách với người dùng thông thường |

**Điểm cốt lõi:** phân đoạn không chỉ là đặt các nhóm ở dải IP khác nhau. Mục tiêu là xác định và **thực thi** kết nối nào được đi qua từng ranh giới, kể cả khi các phân đoạn có tuyến định tuyến tới nhau.

### 2.2. Phân đoạn, cô lập và kiểm soát truy cập

Ba khái niệm liên quan nhưng không hoàn toàn đồng nghĩa:

- **Phân đoạn (segmentation):** chia mạng thành các miền và đặt chính sách cho đường kết nối giữa chúng.
- **Cô lập (isolation):** hạn chế hoặc loại bỏ khả năng liên lạc giữa các miền; đây có thể là kết quả mong muốn của một chính sách phân đoạn, ví dụ mạng khách không được gọi mạng quản trị.
- **Kiểm soát truy cập (access control):** quyết định một nguồn có được thực hiện kết nối hoặc thao tác với đích hay không; có thể thực thi trên firewall, gateway, máy chủ, danh tính dịch vụ hoặc trong ứng dụng.

Một hệ thống thường cần **cho phép có chọn lọc** chứ không cô lập hoàn toàn: API phải liên lạc được với database để phục vụ khách hàng, nhưng máy tính ở mạng khách thì không.

## 3. Vì sao phải phân đoạn mạng?

### 3.1. Hạn chế di chuyển ngang

**Lateral movement** là việc kẻ tấn công, sau khi giành được quyền ở một điểm, tìm cách tiếp cận các máy hoặc tài khoản khác. Khi môi trường cho phép kết nối rộng, kẻ tấn công có nhiều đường để thử. Phân đoạn theo nguyên tắc **least privilege** làm giảm tập đường kết nối có thể dùng.

Ví dụ: một máy in hoặc thiết bị IoT bị chiếm quyền không nên được phép mở kết nối tới máy chủ cơ sở dữ liệu hoặc giao diện quản trị switch.

### 3.2. Giảm phạm vi ảnh hưởng của sự cố

**Blast radius** là phạm vi hệ thống có thể chịu ảnh hưởng từ một sự cố. Khi dịch vụ công khai bị xâm nhập, chính sách DMZ → Data từ chối giúp hạn chế đường truy cập trực tiếp đến dữ liệu. Phân đoạn không bảo đảm sự cố được ngăn chặn hoàn toàn, vì kẻ tấn công vẫn có thể lợi dụng **luồng được phép** hoặc thông tin xác thực bị lộ.

### 3.3. Bảo vệ tài sản theo mức rủi ro

Máy chủ chứa dữ liệu nhạy cảm, điểm quản trị, thiết bị người dùng và thiết bị của khách không cần chung chính sách. Phân đoạn cho phép áp dụng ranh giới chặt hơn với dữ liệu quan trọng, tài khoản đặc quyền và dịch vụ ít cần công bố.

### 3.4. Tăng khả năng giám sát và điều tra

Khi các luồng giữa vùng đi qua điểm thực thi đã biết, firewall log, IDS/IPS, NetFlow và log ứng dụng có thể giúp trả lời: ai kết nối đến đâu, qua dịch vụ gì, có thuộc ma trận truy cập hay không. Tuy nhiên, khả năng quan sát phụ thuộc vị trí cảm biến; lưu lượng **trong cùng phân đoạn** có thể không đi qua firewall trung tâm.

### 3.5. Quản trị thay đổi và tuân thủ yêu cầu bảo mật

Một ma trận luồng truy cập rõ ràng giúp giải thích vì sao quy tắc tồn tại, ai sở hữu, lúc nào cần rà soát và có thể thu hồi khi nào. Một số tiêu chuẩn hoặc quy định có yêu cầu liên quan đến cách ly hệ thống nhất định; mức đáp ứng cụ thể phải đối chiếu với văn bản áp dụng và thiết kế thực tế, không thể suy từ việc “đã tạo VLAN”.

## 4. Các cấp độ và kỹ thuật phân đoạn

### 4.1. Phân đoạn vật lý

**Physical segmentation** dùng hạ tầng vật lý hoặc đường kết nối riêng, như switch, cáp và thiết bị kiểm soát độc lập cho các môi trường nhạy cảm. Cách này giúp giảm một số đường đi ngoài ý muốn nhưng tốn kém và vẫn cần cơ chế bảo vệ giao diện quản trị, tài khoản, cập nhật phần mềm và kết nối giữa các mạng.

### 4.2. VLAN – phân tách miền lớp 2

**VLAN** (*Virtual LAN*) chia một hạ tầng chuyển mạch thành các miền quảng bá lớp 2 riêng. Ví dụ, VLAN 10 cho người dùng và VLAN 20 cho máy chủ.

Lợi ích là các thiết bị ở VLAN khác nhau thường không trao đổi lớp 2 trực tiếp nếu thiếu cơ chế kết nối. Tuy nhiên:

- Khi thiết bị định tuyến hoặc switch lớp 3 bật **inter-VLAN routing**, các VLAN có thể liên lạc với nhau nếu chính sách cho phép.
- VLAN **không tự mã hóa** lưu lượng và không tự thực hiện phân quyền theo người dùng.
- Cấu hình trunk, native VLAN, cổng switch và thiết bị nhiều giao diện phải được kiểm soát để tránh đường đi không mong muốn.
- Các thiết bị trong cùng VLAN vẫn cần cơ chế hạn chế kết nối ngang nếu rủi ro yêu cầu.

**VLAN là công cụ tách mạng lớp 2; mức bảo vệ liên vùng phụ thuộc thêm vào cách định tuyến và thực thi chính sách.**

### 4.3. Subnet và định tuyến lớp 3

**Subnet** là phạm vi địa chỉ IP có cấu trúc chung. Tách subnet giúp tổ chức địa chỉ, định tuyến và gắn chính sách vào các vùng. Tuy nhiên, hai subnet có thể đi tới nhau thông qua router; **khác subnet không mặc nhiên nghĩa là không thể kết nối**.

**VRF** (*Virtual Routing and Forwarding*) tạo các bảng định tuyến tách biệt trên thiết bị hỗ trợ, giúp chia miền định tuyến. Việc kết nối giữa các VRF (*route leaking* hoặc qua thiết bị trung gian) cần được thiết kế rõ, tránh tạo đường đi phá vỡ ranh giới.

### 4.4. Firewall, ACL và policy gateway

**Firewall** hoặc **ACL** thực thi chính sách trên các luồng mạng, ví dụ chỉ cho ứng dụng kết nối đến PostgreSQL trên TCP 5432. Firewall theo dõi trạng thái (*stateful*) có thể cho phép gói phản hồi thuộc kết nối đã thiết lập mà không cần mở quyền khởi tạo kết nối mới theo chiều ngược lại. ACL đơn giản thường xét các trường như nguồn, đích, giao thức và cổng; khả năng theo dõi phiên phụ thuộc loại thiết bị và cơ chế thực thi.

Một chính sách tốt cần chỉ rõ **nguồn, đích, dịch vụ, chiều khởi tạo, lý do và hành động**. Quy tắc “User VLAN được truy cập mọi Server VLAN” vẫn quá rộng dù hai mạng đã được chia VLAN.

### 4.5. Microsegmentation

**Microsegmentation** tạo chính sách với độ chi tiết nhỏ, có thể theo workload, ứng dụng, nhóm máy, nhãn triển khai hoặc danh tính dịch vụ, thay vì chỉ dựa vào subnet. Ví dụ:

- API đơn hàng chỉ được gọi database đơn hàng.
- API thanh toán chỉ được truy cập dịch vụ thanh toán và những đích bắt buộc.
- Máy trạm của bộ phận vận hành được dùng đúng dịch vụ quản lý; các máy trạm khác không được kết nối tới cùng đích.

Microsegmentation có thể thực hiện bằng host firewall, agent trên workload, nền tảng ảo hóa/SDN, chính sách network trong cụm container hoặc các điểm kiểm soát phân tán.

Chú ý: chính sách Kubernetes NetworkPolicy phụ thuộc việc **CNI/network plugin có hỗ trợ thực thi**; tạo đối tượng policy không bảo đảm hiệu lực nếu hạ tầng chưa hỗ trợ. NetworkPolicy tiêu chuẩn chủ yếu điều khiển kết nối mạng, không tự mã hóa hoặc phân quyền thao tác nghiệp vụ.

### 4.6. Phân đoạn theo danh tính và truy cập ứng dụng

Trong mô hình **Zero Trust**, vị trí trong mạng không phải bằng chứng đủ để được phép truy cập. Danh tính người dùng, thiết bị, workload, trạng thái rủi ro và quyền trên tài nguyên cần được xét tiếp. Những cơ chế như NAC/802.1X, VPN có phân quyền, ZTNA, mTLS và IAM có thể bổ sung cho phân đoạn mạng.

**Microsegmentation và Zero Trust có thể phối hợp**, nhưng không phải từ đồng nghĩa: phân đoạn quyết định đường liên lạc, còn kiểm soát danh tính và ứng dụng quyết định ai được làm gì khi đã tới dịch vụ.

## 5. Phân đoạn theo trust zone

**Trust zone** là vùng gồm những tài sản được quản lý theo các yêu cầu bảo mật và giả định tin cậy tương đối giống nhau. Vùng có thể đại diện cho nhiều subnet hoặc nhiều tài nguyên ở các môi trường khác nhau; một subnet cũng có thể được phân nhỏ hơn bằng chính sách workload.

| Vùng | Ví dụ tài sản | Nguyên tắc truy cập |
| --- | --- | --- |
| Untrusted/Internet | Client bên ngoài | Chỉ tiếp cận các điểm công bố có chủ đích |
| DMZ | Reverse proxy, WAF, gateway | Nhận từ Internet; chỉ gọi dịch vụ nội bộ cần thiết |
| Application | API, dịch vụ xử lý nghiệp vụ | Chỉ nhận từ đúng gateway và gọi đúng tài nguyên phụ thuộc |
| Data | Database, kho dữ liệu nhạy cảm | Hạn chế nguồn, tài khoản và quyền truy vấn |
| Management | Bastion, công cụ vận hành | Chỉ cho người và hệ thống quản trị đã xác thực |
| Guest/IoT | Khách, thiết bị không quản lý, cảm biến | Giới hạn đường đến mạng nghiệp vụ và quản trị |

**Điểm giao nhau giữa các zone** là nơi một kết nối đi từ vùng áp dụng chính sách này sang vùng khác. Quyền đi từ A đến B, rồi B đến C, không mặc nhiên cho phép A kết nối trực tiếp đến C.

Ngoài các đường **north–south** giữa Internet và hệ thống, cần quan tâm đường **east–west** giữa máy chủ, dịch vụ và workload nội bộ. Nhiều cuộc tấn công di chuyển ngang xảy ra trên east–west traffic nên chỉ đặt firewall ở biên Internet là chưa đủ.

## 6. Ví dụ kiến trúc web nhiều tầng

Giả sử doanh nghiệp triển khai hệ thống đặt hàng với các địa chỉ **minh họa trong mạng riêng**, không biểu thị cấu hình có thật:

| Phân đoạn | Dải IPv4 minh họa | Thành phần |
| --- | --- | --- |
| DMZ | 10.10.10.0/24 | Reverse proxy: 10.10.10.10 |
| Application | 10.10.20.0/24 | Order API: 10.10.20.15 |
| Data | 10.10.30.0/24 | PostgreSQL: 10.10.30.5 |
| Guest | 10.10.50.0/24 | Máy khách và thiết bị không quản lý |
| Management | 10.10.99.0/24 | Bastion: 10.10.99.10; giám sát và log collector |

~~~mermaid
flowchart LR
    I["Internet / khách hàng"] -->|"HTTPS 443"| F0{"Edge policy"}
    F0 --> W["DMZ: Reverse proxy"]
    W -->|"HTTPS 8443"| F1{"DMZ → App policy"}
    F1 --> A["Application: Order API"]
    A -->|"TCP 5432"| F2{"App → Data policy"}
    F2 --> D[("Data: PostgreSQL")]
    M["Management: Bastion"] -->|"SSH 22 theo quyền"| F3{"Admin policy"}
    F3 --> A
    G["Guest / IoT"] -. "Không được vào App/Data/Admin" .-> X["Deny"]
~~~

Các hình thoi là **điểm thực thi chính sách logic**. Trên hệ thống thực, chúng có thể là firewall vật lý, firewall ảo, security group, host firewall hoặc nhiều lớp phối hợp. Sơ đồ không ngụ ý mỗi hình thoi cần một thiết bị riêng.

Luồng hợp lệ:

1. Khách hàng truy cập reverse proxy qua HTTPS; Internet không có quyền đi thẳng đến database.
2. Reverse proxy chuyển yêu cầu cho Order API qua dịch vụ đã chỉ định; API vẫn xác thực, kiểm tra quyền người dùng và áp dụng bảo vệ ứng dụng.
3. Order API dùng tài khoản database được cấp quyền tối thiểu để truy cập PostgreSQL.
4. Nhân viên vận hành truy cập qua kênh quản trị được bảo vệ và chỉ dùng bastion vào máy đã được cấp quyền.
5. Guest/IoT không được khởi tạo kết nối tới các vùng nghiệp vụ và quản trị nếu không có một nhu cầu cụ thể được chấp thuận.

Ngay cả khi reverse proxy bị xâm nhập, kết nối **DMZ → PostgreSQL** cần bị chặn. Nhưng nếu API chấp nhận yêu cầu trái phép từ proxy, kẻ tấn công vẫn có thể lợi dụng **đường DMZ → Application hợp lệ**. Đây là lý do phân đoạn phải phối hợp với bảo vệ ứng dụng và dữ liệu.

## 7. Ma trận luồng truy cập: mô tả chính sách rõ ràng

Trước khi cấu hình thiết bị, nên lập **traffic flow matrix**. Mỗi dòng phải nêu nguồn khởi tạo, đích, dịch vụ, quyết định và lý do nghiệp vụ.

| Nguồn khởi tạo | Đích | Dịch vụ | Quyết định | Lý do và điều kiện |
| --- | --- | --- | --- | --- |
| Internet | Reverse proxy DMZ | TCP 443 | Cho phép | Điểm truy cập web công khai; bảo vệ HTTPS/API |
| Reverse proxy DMZ | Order API | TCP 8443 | Cho phép có điều kiện | Chỉ proxy xác định; xác thực giữa dịch vụ khi phù hợp |
| Order API | PostgreSQL | TCP 5432 | Cho phép có điều kiện | Chỉ dịch vụ ứng dụng, tài khoản DB giới hạn quyền |
| Bastion | Máy chủ API | TCP 22 | Cho phép có điều kiện | Danh tính quản trị được duyệt; MFA ở kênh truy cập, log phiên |
| Các dịch vụ được khai báo | DNS resolver nội bộ | UDP/TCP 53 | Cho phép có điều kiện | Chỉ tới resolver đã được phê duyệt; không mở tuỳ ý đến mọi đích |
| Các hệ thống phải gửi log | Log collector | Ví dụ syslog TLS TCP 6514 | Cho phép có điều kiện | Chỉ đúng collector và nguồn được chỉ định |
| Guest/IoT | Internet | Dịch vụ được duyệt | Cho phép có điều kiện | Giới hạn rủi ro và lọc lưu lượng đi ra |
| Internet | PostgreSQL | Mọi cổng | Từ chối | Không công khai data zone |
| DMZ | PostgreSQL | Mọi cổng | Từ chối | Không được bỏ qua tầng ứng dụng |
| Guest/IoT | Application/Data/Management | Mọi cổng không được khai báo | Từ chối | Ngăn kết nối ngang và truy cập đặc quyền |
| Các nguồn–đích khác | Bất kỳ | Bất kỳ | Từ chối mặc định | Chỉ mở nhu cầu được phê duyệt |

**Chiều khởi tạo kết nối** rất quan trọng. Ví dụ, cho phép API bắt đầu kết nối đến database không tự cho database khởi tạo phiên mới đến bất kỳ máy nào trong application zone. Với firewall stateful, lưu lượng phản hồi của phiên được cho phép có thể được xử lý dựa trên trạng thái; đối với ACL stateless phải xét quy tắc phản hồi đúng cơ chế của thiết bị.

Không nên quên các phụ thuộc vận hành hợp lệ như DNS, đồng bộ thời gian, cập nhật phần mềm, hệ thống danh tính, sao lưu và giám sát. Chúng cũng phải có **đích cụ thể và quyền tối thiểu**, thay vì mở toàn bộ vùng chỉ vì một ứng dụng “cần truy cập dịch vụ chung”.

## 8. Ví dụ chính sách trung lập với sản phẩm

Đoạn YAML sau minh họa cách diễn đạt ma trận luồng. Đây là **tài liệu mô hình hóa**, không phải cú pháp có thể áp dụng trực tiếp cho thiết bị firewall:

~~~yaml
networkSegmentation:
  defaultAction: deny
  zones:
    dmz: "10.10.10.0/24"
    application: "10.10.20.0/24"
    data: "10.10.30.0/24"
    guest: "10.10.50.0/24"
    management: "10.10.99.0/24"

  allowRules:
    - id: public-to-web
      source: internet
      destination: "dmz/reverse-proxy"
      protocol: tcp
      port: 443
      reason: "Website đặt hàng"

    - id: web-to-api
      source: "dmz/reverse-proxy"
      destination: "application/order-api"
      protocol: tcp
      port: 8443
      requirements: [service-authentication, api-authorization]
      reason: "Chuyển yêu cầu nghiệp vụ"

    - id: api-to-db
      source: "application/order-api"
      destination: "data/postgresql"
      protocol: tcp
      port: 5432
      requirements: [db-authentication, least-privilege-db-role]
      reason: "Truy vấn dữ liệu đơn hàng"

    - id: bastion-to-api-host
      source: "management/bastion"
      destination: "application/api-host"
      protocol: tcp
      port: 22
      requirements: [admin-authentication, session-audit]
      reason: "Quản trị máy chủ được phê duyệt"
~~~

Khi chuyển chính sách thành cấu hình thật cần xác định: thiết bị nào nằm trên đường lưu lượng, các đối tượng nguồn/đích được ánh xạ thế nào, quy tắc ingress/egress, hoạt động NAT, IPv4/IPv6, tính stateful/stateless, thứ tự rule và luồng phản hồi. **Các trường requirements mô tả kiểm soát bổ sung**, không có nghĩa firewall lọc TCP/IP tự thực thi được phân quyền API hoặc database.

### 8.1. Tránh quy tắc quá rộng

Ví dụ một rule “10.10.10.0/24 → 10.10.0.0/16, any” có thể vô tình cho phép DMZ tới cả data và management zone. Thay vào đó, chỉ cho reverse proxy cần thiết đến đúng Order API và cổng đã xác định. Quy tắc ngoại lệ nên có người sở hữu, lý do, thời điểm rà soát và hạn hết hiệu lực nếu chỉ dùng tạm thời.

### 8.2. Chặn đường đi ra ngoài không cần thiết

Phân đoạn không chỉ bảo vệ **lưu lượng vào**. Lưu lượng ra ngoài (*egress*) từ data zone và workload nhạy cảm cần được xét. Nếu database không có nhu cầu kết nối Internet trực tiếp, nên không cấp đường hoặc quyền egress rộng. Dịch vụ cần cập nhật hay gửi log có thể đi qua endpoint/proxy được quản lý và ghi nhận.

## 9. Quy trình thiết kế phân đoạn mạng

### Bước 1 – Kiểm kê tài sản, dữ liệu và quyền sở hữu

Xác định server, container, thiết bị mạng, thiết bị cá nhân, máy IoT, hệ thống quản trị, dữ liệu nhạy cảm và nhà cung cấp liên quan. Cần biết **chủ sở hữu**, mức quan trọng và yêu cầu liên lạc của từng tài sản. Một danh sách subnet mà không biết workload bên trong sẽ khiến quy tắc khó duy trì.

### Bước 2 – Nhóm tài sản theo chức năng và mức rủi ro

Chia thành các vùng như public/DMZ, user, application, data, guest/IoT và management. Hạn chế gom các tài sản có mức tin cậy khác nhau chỉ vì chúng ở cùng văn phòng hoặc cùng cloud account.

### Bước 3 – Lập ma trận phụ thuộc nghiệp vụ

Liệt kê luồng **bắt buộc** để hệ thống hoạt động, ai khởi tạo, giao thức/cổng, đích, định danh dịch vụ, mức đặc quyền và điều kiện truy cập. Xem xét cả đường quản trị, DNS, NTP, giám sát, sao lưu và các luồng đi qua VPN hoặc dịch vụ cloud.

### Bước 4 – Chọn điểm thực thi chính sách

Quyết định nên dùng VLAN, VRF, router ACL, firewall, host firewall, security group, NetworkPolicy, ZTNA hoặc kết hợp. Điều quan trọng là **mọi đường đi liên quan** phải qua điểm thực thi phù hợp; firewall trung tâm không thể lọc kết nối giữa hai workload nếu lưu lượng của chúng không đi qua firewall đó.

### Bước 5 – Áp dụng mặc định từ chối theo lộ trình

Với hệ thống hiện hữu, cần đo đạc phụ thuộc trước khi siết rule. Có thể triển khai theo giai đoạn: quan sát, lập danh sách cho phép, thử nghiệm trong môi trường đại diện, áp dụng theo nhóm, giám sát rồi điều chỉnh. **Default deny** là trạng thái mục tiêu cho luồng không được khai báo; không nên bật thay đổi lớn thiếu kế hoạch khiến dịch vụ đột ngột ngừng hoạt động.

### Bước 6 – Kiểm thử cả luồng hợp lệ và không hợp lệ

Không chỉ kiểm thử API vẫn truy cập được DB, mà còn phải thử **DMZ → DB**, **Guest → Management** và các đường cấm khác. Kiểm tra cả tuyến dự phòng, hai chiều, IPv6, NAT và những máy có nhiều giao diện mạng.

### Bước 7 – Giám sát, quản lý ngoại lệ và rà soát định kỳ

Theo dõi log allow/deny, lưu lượng giữa zone, thay đổi rule và các kết nối chưa được công bố. Mỗi lần thêm ứng dụng, đổi subnet, tạo kết nối đối tác hoặc tài nguyên cloud mới cần kiểm tra lại giả định phân đoạn.

## 10. Mối liên hệ với các lớp phòng vệ mạng khác

### 10.1. Firewall, IDS và IPS

Firewall thực thi quyền kết nối; IDS/IPS có thể phát hiện hoặc ngăn một số hành vi đáng ngờ trên các luồng mà cảm biến quan sát được. Một luồng nằm trong danh sách cho phép **vẫn có thể độc hại**, ví dụ yêu cầu API chứa hành vi khai thác. Vì vậy, phân đoạn và phát hiện xâm nhập giải quyết những phần khác nhau của rủi ro.

Đặt IDS ở điểm giao nhau quan trọng có thể giúp quan sát north–south và east–west traffic; với lưu lượng mã hóa, metadata mạng không đủ để hiểu mọi thao tác ứng dụng. Cần kết hợp log ứng dụng, xác thực và endpoint.

### 10.2. VPN và truy cập từ xa

VPN tạo kênh kết nối được bảo vệ, **không đồng nghĩa thiết bị từ xa trở thành thành viên tin cậy của mọi phân đoạn**. Người dùng kết nối VPN chỉ nên tới ứng dụng hoặc vùng được cấp quyền; tài khoản nhà thầu không nên có đường truy cập quản trị hoặc dữ liệu chỉ vì đã vào VPN.

### 10.3. Bảo vệ DNS

DNS là phụ thuộc quan trọng của ứng dụng. Có thể buộc các phân đoạn sử dụng resolver được phê duyệt, hạn chế truy vấn trực tiếp tới đích ngoài không cần thiết và theo dõi DNS để phát hiện tên đáng ngờ. DNS filtering không thay thế kiểm soát kết nối theo IP/danh tính; kẻ tấn công có thể dùng IP trực tiếp hoặc phương thức phân giải khác nếu thiết kế chỉ phụ thuộc vào chặn tên miền.

### 10.4. Mạng không dây

Mạng Wi-Fi cho khách, nhân viên và thiết bị IoT có thể sử dụng SSID, VLAN hoặc chính sách truy cập khác nhau. **SSID khác nhau không bảo đảm phân đoạn** nếu chúng cuối cùng được nối vào cùng mạng không hạn chế. Cần kiểm tra ánh xạ SSID–VLAN, quy tắc liên vùng, client isolation khi phù hợp và quyền quản trị access point/controller.

### 10.5. Xác thực và phân quyền ứng dụng

Một rule cho phép TCP 443 hoặc 5432 chỉ quyết định khả năng kết nối mạng. API vẫn phải kiểm tra người gọi được đọc đơn hàng nào; database phải giới hạn tài khoản ứng dụng; các kết nối cần được mã hóa và xác thực theo yêu cầu. Phân đoạn **không tự khắc phục** mật khẩu yếu, lỗi phân quyền hoặc phần mềm chưa vá.

## 11. Phân đoạn trong môi trường ảo hóa và đám mây

### 11.1. VPC/VNet, subnet và chính sách bảo mật

Trong cloud, tài nguyên thường được tổ chức bằng VPC/VNet, subnet, route table, security group và network ACL hoặc các cơ chế tương đương. **Route table xác định có đường đi**, trong khi firewall/security group/ACL và chính sách dịch vụ xác định luồng nào được cho phép. Khả năng stateful, thứ tự đánh giá và mặc định khác nhau theo nền tảng, nên phải kiểm tra đúng tài liệu của dịch vụ sử dụng.

Ví dụ, chỉ cho application workload kết nối tới managed database qua private endpoint hoặc đường mạng riêng phù hợp. Tuy nhiên, việc sử dụng private endpoint không tự kiểm soát mọi quyền truy cập dữ liệu: vẫn cần xác thực cơ sở dữ liệu và IAM theo dịch vụ.

### 11.2. Hub, peering và môi trường hybrid

Peering, transit gateway, kết nối riêng và site-to-site VPN có thể tạo đường giữa nhiều mạng. Không nên giả định “đã tách VPC” là không có lưu lượng ngang nếu route và chính sách cho phép kết nối qua hub. Phải vẽ toàn bộ đường đi, đặc biệt là từ mạng đối tác tới management/data zone.

### 11.3. Container và workload thay đổi liên tục

Trong môi trường container, địa chỉ IP có thể thay đổi khi workload được tạo hoặc thay thế. Chính sách dựa trên **nhãn, định danh workload hoặc namespace** có thể dễ duy trì hơn danh sách IP tĩnh, nhưng chỉ hiệu quả khi nền tảng thực thi chính sách đúng. Kiểm tra namespace mặc định, quy tắc ingress/egress, DNS egress và lưu lượng giữa pod/service.

### 11.4. Không bỏ quên mặt phẳng quản trị cloud

Cloud API và bảng điều khiển quản trị có thể sử dụng HTTPS qua Internet, nằm **ngoài đường lọc gói tin giữa các subnet nội bộ**. Vì vậy phải kiểm soát IAM, MFA, tài khoản đặc quyền, audit log và giới hạn quyền triển khai. Microsegmentation của workload không tự bảo vệ toàn bộ cloud control plane.

## 12. Những lỗi làm mất tác dụng phân đoạn

| Lỗi thiết kế/cấu hình | Tác động có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Tạo VLAN nhưng bật định tuyến không giới hạn | Các vùng vẫn kết nối rộng | Bổ sung policy tại router/firewall hoặc workload |
| Rule any/any giữa hai vùng | Một máy bị chiếm có nhiều đích tiếp cận | Thu hẹp nguồn–đích–dịch vụ theo nhu cầu |
| Chỉ lọc ingress, bỏ qua egress | Workload có thể kết nối ra ngoài quá rộng | Xác định phụ thuộc và kiểm soát cả đường ra |
| Có tuyến phụ, VPN hoặc peering chưa kiểm kê | Bỏ qua điểm thực thi dự kiến | Kiểm kê route, tunnel, gateway và kiểm thử các đường |
| Máy chủ hai NIC nối hai vùng và chuyển tiếp ngoài kế hoạch | Tạo cầu nối mạng trái thiết kế | Loại bỏ đường nối hoặc giới hạn và giám sát chuyển tiếp |
| Chỉ có firewall biên, bỏ qua east–west | Máy cùng vùng/cluster vẫn có thể kết nối tùy ý | Host firewall, distributed firewall, microsegmentation |
| Bỏ quên IPv6 | Luồng IPv6 có thể không chịu cùng chính sách IPv4 | Đồng bộ chính sách hai họ địa chỉ hoặc quản lý IPv6 rõ ràng |
| Không tính NAT hoặc định tuyến bất đối xứng | Quy tắc không khớp hoặc stateful firewall từ chối nhầm | Xác minh IP trước/sau NAT, tuyến đi và tuyến về |
| Cho phép toàn bộ dịch vụ chung | DNS, sao lưu, giám sát trở thành đường xuyên vùng rộng | Giới hạn đúng endpoint, chiều kết nối và danh tính |
| Không ghi log, không rà soát ngoại lệ | Quy tắc thừa tồn tại lâu và khó điều tra | Log, đặt thời hạn ngoại lệ, quản lý thay đổi |
| Chỉ kiểm tra chiều cho phép | Đường bị cấm có thể vẫn mở mà không phát hiện | Viết negative test cho từng ranh giới quan trọng |

Không nên chỉ kiểm tra “hai máy có ping được nhau không”. ICMP có thể bị chặn trong khi TCP được phép, hoặc ngược lại. Muốn xác minh phân đoạn phải kiểm tra **dịch vụ đích thực tế**, chiều kết nối và trạng thái ứng dụng.

## 13. Kiểm thử và giám sát phân đoạn

### 13.1. Lập kế hoạch kiểm thử

Mỗi ca thử nên có: mã kiểm thử, máy xuất phát, địa chỉ/danh tính đích, giao thức/cổng, kỳ vọng, quyền kiểm thử, thời điểm, kết quả và bằng chứng log. Chỉ thực hiện trong môi trường được phép; những phép thử ảnh hưởng sản xuất phải tuân theo kế hoạch và giới hạn đã phê duyệt.

Ví dụ với kiến trúc ở mục 6:

| Mã | Nguồn | Đích | Phép thử | Kỳ vọng |
| --- | --- | --- | --- | --- |
| T-01 | Client Internet | Reverse proxy 10.10.10.10 | HTTPS 443 qua điểm công bố | Được phép, TLS hợp lệ |
| T-02 | Reverse proxy | Order API 10.10.20.15 | TCP 8443 và xác thực dịch vụ | Cho phép khi hợp lệ |
| T-03 | Order API | PostgreSQL 10.10.30.5 | TCP 5432 và quyền truy vấn được cấp | Cho phép đúng nghiệp vụ |
| T-04 | Reverse proxy | PostgreSQL 10.10.30.5 | TCP 5432 | Bị từ chối |
| T-05 | Guest 10.10.50.0/24 | Bastion 10.10.99.10 | TCP 22 | Bị từ chối |
| T-06 | Máy không thuộc nhóm ứng dụng | PostgreSQL 10.10.30.5 | TCP 5432 | Bị từ chối |
| T-07 | Bastion 10.10.99.10 | Máy chủ ứng dụng được cấp quyền | TCP 22 | Được phép sau xác thực |

**Lưu ý ở T-01:** địa chỉ 10.10.10.10 là địa chỉ nội bộ minh họa; trên Internet người dùng thường kết nối qua IP hoặc tên miền công khai/NAT/load balancer tương ứng. Cần kiểm thử điểm công bố thực tế, không suy từ địa chỉ riêng rằng có thể truy cập trực tiếp qua Internet.

### 13.2. Lệnh minh họa trong môi trường lab được ủy quyền

Trên Windows, có thể kiểm tra khả năng kết nối TCP tới một đích kiểm thử:

~~~powershell
Test-NetConnection -ComputerName 10.10.20.15 -Port 8443
~~~

Trên Linux, nếu máy có công cụ netcat, có thể thử bắt tay TCP:

~~~bash
nc -vz -w 3 10.10.20.15 8443
~~~

Những lệnh này **chỉ kiểm tra khả năng kết nối ở mức mạng** và có thể tạo log trên hệ thống đích. Kết nối thành công không chứng minh người dùng có quyền gọi API; kết nối thất bại cũng có thể do dịch vụ ngừng hoạt động, lỗi định tuyến hoặc firewall. Phải đối chiếu thêm trạng thái ứng dụng và log tại điểm thực thi.

### 13.3. Quan sát và xác định nguyên nhân khi thất bại

Nếu một kết nối bị từ chối ngoài dự kiến, hãy đối chiếu:

1. IP nguồn/đích và subnet có đúng không, đặc biệt trước/sau NAT?
2. Tuyến đi/tuyến về có qua đúng firewall hay gateway?
3. Rule thực tế có khớp giao thức, cổng, chiều khởi tạo và địa chỉ IPv4/IPv6?
4. Host firewall hoặc security group có quy tắc riêng không?
5. Đích có đang lắng nghe dịch vụ và ứng dụng có yêu cầu xác thực bổ sung không?
6. Có sự kiện allow/deny, reset, timeout hoặc lỗi TLS nào trong log?

Với ca thử bị cấm nhưng **vẫn thành công**, ưu tiên xác định đường đi đã vượt qua kiểm soát bằng cách nào; không chỉ sửa một rule trên firewall mà chưa biết gói tin có thực sự đi qua nó hay không.

### 13.4. Chỉ số theo dõi

Để đánh giá tiến độ phân đoạn, có thể theo dõi tỷ lệ tài sản có chủ sở hữu, tỷ lệ luồng đã được khai báo, số rule quá rộng, ngoại lệ quá hạn, số ca kiểm thử âm tính đạt và số kết nối trái ma trận bị phát hiện. Các chỉ số cần đi kèm khả năng kiểm chứng và phạm vi đo, thay vì chỉ đếm số VLAN hoặc số rule firewall.

## 14. Tình huống: thiết bị IoT bị chiếm quyền

Một văn phòng có nhiều camera, máy in và cảm biến. Giả sử một thiết bị IoT trong guest/IoT zone bị chiếm quyền và cố truy cập hệ thống lưu đơn hàng.

**Nếu mạng phẳng hoặc rule quá rộng:** thiết bị có thể thấy nhiều host, tiếp cận cổng dịch vụ không liên quan và thử khai thác tiếp, khiến khả năng di chuyển ngang tăng.

**Nếu phân đoạn đúng thiết kế:** thiết bị IoT chỉ được kết nối tới gateway điều khiển hoặc dịch vụ cloud được phê duyệt. Những luồng IoT → Application, IoT → Data và IoT → Management bị chặn theo ma trận. Nhật ký chặn các kết nối này có thể cung cấp chỉ dấu để điều tra.

**Rủi ro còn lại:** nếu gateway điều khiển chung cho IoT và hệ thống nghiệp vụ bị xâm nhập, nó có thể trở thành cầu nối. Vì vậy phải kiểm tra chính sách từ gateway đến các zone khác, xác thực giữa dịch vụ và quyền của chính gateway.

**Bài học:** phân đoạn giảm đường đi không cần thiết và thu hẹp phạm vi ảnh hưởng; bảo vệ ứng dụng, danh tính và giám sát vẫn cần thiết tại những điểm giao nhau được phép.

## 15. Câu hỏi và bài tập tự kiểm tra

### Câu hỏi 1

Vì sao việc tạo VLAN 10 cho người dùng và VLAN 20 cho database chưa đủ để kết luận database đã được cách ly?

**Gợi ý:** VLAN tách miền lớp 2; nếu inter-VLAN routing đang cho phép kết nối không giới hạn, người dùng vẫn có đường truy cập database. Cần kiểm tra chính sách L3/L4 và quyền ứng dụng.

### Câu hỏi 2

API thuộc application zone được phép gọi PostgreSQL trong data zone. Điều đó có cấp quyền cho reverse proxy ở DMZ gọi PostgreSQL trực tiếp không?

**Gợi ý:** Không. Mỗi luồng qua ranh giới có chính sách riêng; quyền kết nối không mang tính bắc cầu.

### Câu hỏi 3

Firewall biên Internet đã chặn toàn bộ SSH từ bên ngoài. Vì sao vẫn cần kiểm soát SSH giữa các server nội bộ?

**Gợi ý:** Máy nội bộ có thể bị xâm nhập; kết nối east–west và quyền quản trị là đường di chuyển ngang cần được giới hạn.

### Câu hỏi 4

VPN có mã hóa và MFA đã đủ để cho nhân viên truy cập toàn bộ mạng quản trị chưa?

**Gợi ý:** Chưa. VPN và MFA hỗ trợ bảo vệ đường vào; quyền tới từng tài sản, danh tính thiết bị, vai trò và phiên quản trị vẫn phải được kiểm soát.

### Câu hỏi 5

Một policy trên Kubernetes đã được tạo nhưng tất cả pod vẫn có thể kết nối. Cần kiểm tra những gì?

**Gợi ý:** CNI có thực thi NetworkPolicy không, selector có khớp nhãn/namespace không, policy áp dụng ingress hay egress, và còn đường kết nối nào khác ngoài phạm vi policy?

### Bài tập thiết kế

Thiết kế mạng cho doanh nghiệp có **Web, API, Database, nhân viên, khách Wi-Fi, IoT và bastion quản trị**. Hãy:

1. Chia ít nhất năm trust zone, nêu nhóm tài sản trong từng vùng.
2. Vẽ sơ đồ đường đi từ người dùng bên ngoài tới dữ liệu nghiệp vụ.
3. Viết tối thiểu **năm rule cho phép có lý do** và **ba rule từ chối quan trọng**.
4. Chỉ ra ba đường tấn công di chuyển ngang nếu thiết bị IoT hoặc máy người dùng bị chiếm quyền.
5. Đề xuất ba phép kiểm thử âm tính và loại log cần xem để xác nhận chính sách đang có hiệu lực.

Đối chiếu thiết kế với nguyên tắc: **mỗi đường kết nối phải có nhu cầu, điểm thực thi và bằng chứng kiểm thử**. Nếu một luồng chưa rõ lý do, hãy làm rõ với chủ hệ thống trước khi mở quyền.

## 16. Những điều cần ghi nhớ

- **Network segmentation là việc chia mạng và kiểm soát lưu lượng giữa các phần**, nhằm giảm khả năng truy cập không cần thiết và phạm vi ảnh hưởng của sự cố.
- **VLAN, subnet hay VPC chỉ tạo cấu trúc.** Mức cô lập thực tế phụ thuộc định tuyến, firewall/ACL, host policy và các đường kết nối khác.
- **Cho phép theo đúng nhu cầu nghiệp vụ, mặc định từ chối phần còn lại.** Cần xét cả lưu lượng đi vào, đi ra, kết nối east–west và đường quản trị.
- **Microsegmentation** thu hẹp chính sách đến workload, nhóm ứng dụng hoặc danh tính, đặc biệt hữu ích khi các dịch vụ dùng chung hạ tầng.
- **Phân đoạn phải kết hợp xác thực, phân quyền, bảo vệ DNS, VPN, IDS/IPS và bảo vệ ứng dụng.** Một kết nối được phép vẫn có thể bị lạm dụng.
- **Luôn kiểm thử cả đường được phép và bị cấm**, kiểm tra IPv4/IPv6, VPN/cloud peering, NAT, tuyến dự phòng và những điểm có thể bỏ qua firewall.
- **Bài toán cần giải là rủi ro và đường kết nối thực tế**, không phải số lượng VLAN đã tạo.
