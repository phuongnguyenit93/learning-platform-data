# Giới hạn mạng được phép truy cập qua VPN

> **Chương:** VPN và truy cập từ xa  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Trọng tâm:** Áp dụng nguyên tắc đặc quyền tối thiểu (least privilege) cho kết nối VPN: chỉ cho người dùng, thiết bị hoặc đối tác truy cập **đúng subnet, dịch vụ và cổng** được phê duyệt; kết hợp xác thực, định tuyến, firewall, phân đoạn, DNS, giám sát và ứng phó sự cố.

## 1. Vì sao VPN cần giới hạn mạng được phép truy cập?

**Virtual Private Network (VPN)** tạo một kênh kết nối logic giữa hai đầu cuối qua mạng khác, thường sử dụng cơ chế bảo vệ bằng mật mã. Trong **remote-access VPN**, người dùng ở nhà, trên mạng Wi-Fi công cộng hoặc tại chi nhánh có thể truy cập các tài nguyên nội bộ theo chính sách tổ chức. Tuy nhiên, **kết nối VPN thành công không đồng nghĩa người dùng có quyền vào toàn bộ mạng doanh nghiệp**.

Một mạng nội bộ thường chứa nhiều vùng có mức độ tin cậy khác nhau: máy tính nhân viên, máy chủ ứng dụng, cơ sở dữ liệu, hạ tầng DNS/DHCP, backup, hệ thống quản trị, thiết bị mạng và môi trường thử nghiệm. Nếu VPN cho phép truy cập rộng toàn bộ các dải private IP, tài khoản bị xâm nhập hoặc thiết bị nhiễm mã độc có thể trở thành **điểm xuất phát cho truy cập ngang (lateral movement)**.

**Giới hạn mạng được phép truy cập qua VPN** nghĩa là tạo và thực thi chính sách để một kết nối VPN chỉ đi tới **những mạng, đích và dịch vụ cần thiết cho vai trò đã xác minh**. Đây vừa là bài toán **định tuyến** (client gửi gói đi đâu), vừa là bài toán **phân quyền mạng** (gói nào được cho phép thực sự).

Ví dụ: nhân viên kinh doanh chỉ cần API quản lý đơn hàng và cổng SSO; kỹ sư vận hành cần các dịch vụ quản trị có kiểm soát; đối tác chỉ cần một API riêng. Không có lý do mặc định để cả ba nhóm truy cập trực tiếp subnet database, giao diện quản trị switch hoặc hệ thống backup.

**Thông điệp chính:** Cấu hình route tới một mạng chỉ giúp mạng đó có thể được tìm thấy. **Route không phải quyền truy cập**, và kênh VPN được mã hóa **không phải một lời xác nhận rằng mọi traffic bên trong đều an toàn**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **VPN tunnel, route, traffic selector/AllowedIPs và chính sách cho phép truy cập**.
2. Thiết kế phân quyền mạng cho người dùng, quản trị viên, đối tác và các kết nối site-to-site.
3. So sánh **split tunneling** với **full tunneling** và hiểu vì sao lựa chọn đường đi không thay firewall.
4. Viết ma trận truy cập dựa trên **nguồn đã xác thực, subnet đích, giao thức, cổng, dịch vụ và ngữ cảnh thiết bị**.
5. Xử lý các tình huống **IPv4/IPv6, DNS/split DNS, overlapping CIDR, NAT, asymmetric routing và cloud route propagation**.
6. Kiểm tra an toàn chính sách trên Linux/Windows, đối chiếu log VPN, firewall, IAM và ứng dụng.
7. Xây dựng quy trình triển khai, giám sát, thu hồi quyền và ứng phó khi cấu hình VPN quá rộng.

## 2. Các thuật ngữ và ranh giới tin cậy

| Thuật ngữ | Ý nghĩa | Điểm cần nhớ |
|---|---|---|
| **VPN client** | Thiết bị/ứng dụng khởi tạo kết nối | Client không phải nguồn dữ liệu luôn đáng tin |
| **VPN gateway/concentrator** | Điểm kết thúc hoặc quản lý tunnel | Có thể là nơi xác thực, gắn role, lọc và ghi log |
| **VPN address pool** | Dải IP cấp cho client trong tunnel | Không nên dùng IP tái cấp làm danh tính duy nhất |
| **Protected subnet** | Mạng nội bộ được tổ chức bảo vệ | Có thể chứa nhiều mức độ nhạy cảm khác nhau |
| **Split tunnel** | Chỉ một số đích dùng VPN; traffic khác đi theo mạng cục bộ | Không tự giới hạn quyền truy cập bên trong tunnel |
| **Full tunnel** | Phần lớn hoặc toàn bộ traffic theo chính sách đi qua VPN | Không tự cho phép truy cập mọi subnet, và phải xét IPv6 |
| **Route/pushed route** | Thông tin quyết định next hop/interface tới một prefix | Quyết định đường đi chứ không phải authorization |
| **Traffic selector / AllowedIPs** | Mô tả traffic liên quan tunnel theo cơ chế VPN cụ thể | Có semantics khác nhau theo IPsec/WireGuard và hướng cấu hình |
| **Network ACL/firewall policy** | Quy tắc cho phép/từ chối traffic thực tế | Phải nằm trên data path và bao phủ hai chiều cần thiết |
| **Identity-based policy** | Phân quyền theo danh tính/nhóm/thiết bị đã xác minh | Không chỉ dựa vào IP, MAC hoặc tên nhóm do client tự khai |
| **Microsegmentation** | Hạn chế giao tiếp giữa workload/vùng nhỏ | Bổ sung cho chính sách VPN tại ranh giới |
| **ZTNA** | Cấp truy cập theo ngữ cảnh và từng ứng dụng/tài nguyên | Có thể thay hoặc bổ sung truy cập VPN tới subnet |

**Truy cập mạng được phép** có thể được mô tả ở nhiều mức: prefix IP, máy đích, TCP/UDP port, ứng dụng và chức năng nghiệp vụ. Một rule cho phép TCP 443 tới một máy chủ **không thay kiểm tra user/role ở ứng dụng HTTPS**.

## 3. Ba câu hỏi khác nhau: kết nối, định tuyến và phân quyền

Giả sử người dùng đã đăng nhập VPN thành công và được cấp IP tunnel **10.255.10.24**.

1. **VPN tunnel có hoạt động không?** Client và gateway đã xác thực theo cấu hình, thương lượng/tạo được tunnel và có thể bảo vệ các gói liên quan.
2. **Có route tới mạng đích không?** Client có thể có route **10.20.10.0/24 via VPN**, nhưng các mạng khác cũng có thể reachable qua route mặc định hoặc route chồng lấn.
3. **Có được phép dùng dịch vụ đích không?** VPN gateway, firewall, host policy và ứng dụng mới quyết định client đó có được kết nối đến **10.20.10.15 TCP 443** hay không.

~~~mermaid
flowchart TD
    A[Người dùng và thiết bị khởi tạo VPN] --> B{Xác thực / MFA / posture đạt?}
    B -- Không --> X[Từ chối VPN]
    B -- Có --> C[Tạo tunnel và cấp identity / IP pool]
    C --> D[Chọn route theo split/full tunnel]
    D --> E{Destination và service trong policy được phép?}
    E -- Không --> F[Firewall/gateway deny + log]
    E -- Có --> G[Routing/segmentation tới subnet đích]
    G --> H{Application có xác thực / authorization đúng?}
    H -- Không --> I[Ứng dụng từ chối]
    H -- Có --> J[Cho phép chức năng nghiệp vụ]
~~~

### 3.1. Vì sao không thể chỉ đẩy route hẹp xuống client?

Một cấu hình remote-access VPN có thể **chỉ push route cho subnet ứng dụng**. Điều này giảm số traffic vô tình đi vào tunnel và hỗ trợ trải nghiệm người dùng, nhưng **không phải ranh giới bảo mật đủ mạnh**:

- Client có thể bị cấu hình sai hoặc bị người có quyền quản trị thiết bị thay đổi route.
- Gateway có thể còn **route mặc định hoặc route tới các subnet nhạy cảm**.
- Một ứng dụng/proxy trong mạng cho phép có thể chuyển traffic tiếp nếu không kiểm soát.
- IPv6 hoặc kết nối thông qua DNS/proxy có thể đi theo data path khác.

Do đó phải thực thi **deny tại VPN gateway, phân đoạn/firewall hoặc điểm bảo vệ workload**. Thông tin route trên client hỗ trợ vận hành, **không được xem là bằng chứng quyền truy cập đã được hạn chế**.

## 4. Nguyên tắc thiết kế least privilege cho remote-access VPN

### 4.1. Phân quyền theo nhiệm vụ, không theo sự tiện lợi

Một nhân viên cần dùng hệ thống báo cáo không nhất thiết phải mở **mọi TCP/UDP port của toàn bộ 10.0.0.0/8**. Hãy trả lời:

- **Ai** truy cập: user, nhóm IAM, vai trò, tài khoản dịch vụ, đối tác?
- **Thiết bị nào** truy cập: thiết bị quản lý, tình trạng mã hóa ổ đĩa/EDR, chứng chỉ, độ tin cậy?
- **Dịch vụ nào** thực sự cần: API, DNS, source control, bastion, CI, database?
- **Địa chỉ nào** đại diện cho dịch vụ đó: subnet, IP, load balancer hoặc application proxy?
- **Cổng/giao thức nào** phải mở và có cần kết nối chiều về?
- **Khi nào và ở đâu** được phép: ca trực, phê duyệt tạm, session lifetime?
- **Ai là owner** của tài nguyên và thời hạn rà soát quyền?

### 4.2. Quy tắc mẫu

**Default deny:** lưu lượng từ remote-access VPN không có rule allow rõ ràng được từ chối. **Explicit allow:** chỉ mở tới đúng đích và service đã được owner phê duyệt. **Defense in depth:** cùng luồng được bảo vệ ở **VPN gateway, inter-zone firewall và application authorization** khi cần.

### 4.3. Không dùng “VPN user” là một vai trò chung

Một pool cho hàng nghìn người với chính sách chung thường khiến kỹ sư phải mở nhiều mạng để hỗ trợ ngoại lệ. Nên chia nhóm như **EMPLOYEE, SUPPORT, ENGINEERING, ADMIN, PARTNER**, kèm identity và device posture được xác minh. Nếu dùng subnet nguồn khác nhau theo vai trò, cần **bảo vệ mapping user → pool/role** và xử lý tái cấp IP.

## 5. Kiến trúc tham chiếu cho doanh nghiệp

Giả sử tổ chức có các vùng IPv4 minh họa:

| Zone | Dải / mục đích | Mức độ nhạy cảm |
|---|---|---|
| **VPN Employee** | 10.255.10.0/24 — IP cấp cho nhân viên | Nguồn remote-access có xác thực |
| **VPN Admin** | 10.255.20.0/24 — phiên admin được cấp quyền | Nguồn quản trị có kiểm soát bổ sung |
| **App Frontend** | 10.20.10.0/24 — web/API nội bộ | Có thể cho phép một số nhóm |
| **App Services** | 10.20.20.0/24 — backend private | Không mặc định cho VPN client truy cập trực tiếp |
| **Database** | 10.20.30.0/24 — DB | Chỉ backend/bastion được phép |
| **Engineering** | 10.20.50.0/24 — Git/CI/dev tooling | Chỉ nhóm kỹ thuật theo dịch vụ |
| **Management** | 10.20.90.0/24 — thiết bị mạng/servers | Chỉ đường quản trị được phê duyệt |
| **DNS/Identity** | 10.20.5.0/24 — resolver, SSO, directory | Truy cập đến dịch vụ cần thiết, không mở toàn subnet |

Các địa chỉ là **ví dụ**, không phải gợi ý bắt buộc sử dụng trong production.

~~~mermaid
flowchart TB
    E[Employee device] -->|MFA + trusted posture| V[VPN Gateway]
    A[Admin device] -->|MFA + elevated policy| V
    P[Partner device] -->|Partner identity| V
    V --> Z[Identity-aware policy / firewall]
    Z -->|Employee: HTTPS| APP[App Frontend zone]
    Z -->|Engineer: approved services| ENG[Engineering zone]
    Z -->|Admin: bastion only| B[Bastion / Management entry]
    B --> MGMT[Management targets]
    APP -->|Service-to-service authorized| BACK[Backend zone]
    BACK -->|DB service only| DB[(Database zone)]
    Z -. Direct DB/Management denied .-> DB
    Z --> DNS[Approved DNS / identity services]
    V -. Auth/tunnel events .-> SOC[SOC / SIEM]
    Z -. Allow/deny flows .-> SOC
~~~

**Bastion** hoặc **ZTNA/application gateway** giúp tránh cấp quyền TCP/SSH/RDP trực tiếp tới từng máy quản trị cho cả nhóm VPN. Tuy nhiên bastion cũng cần MFA, authorization, session logging phù hợp và kiểm soát truy cập sang đích cuối.

## 6. Ma trận truy cập theo vai trò

| Vai trò | Từ nguồn VPN | Đích và dịch vụ | Policy | Lý do |
|---|---|---|---|---|
| **Employee** | Role EMPLOYEE / pool phù hợp | Internal App 10.20.10.15 TCP 443 | Allow | Dùng ứng dụng nghiệp vụ |
| **Employee** | Role EMPLOYEE | DNS resolver 10.20.5.53 UDP/TCP 53 | Allow | Phân giải split DNS cần thiết |
| **Employee** | Role EMPLOYEE | Database 10.20.30.0/24 mọi port | **Deny** | Không cần kết nối DB trực tiếp |
| **Employee** | Role EMPLOYEE | Management 10.20.90.0/24 mọi port | **Deny** | Giảm bề mặt quản trị |
| **Engineer** | Role ENGINEERING | Git/CI được duyệt TCP 443 | Allow | Công cụ phát triển |
| **Engineer** | Role ENGINEERING | DB production trực tiếp | **Deny** mặc định | Nếu cần phải qua đường được phê duyệt |
| **Admin** | Role ADMIN + MFA/posture | Bastion TCP 443 hoặc SSH theo thiết kế | Allow có điều kiện | Quản trị qua điểm giám sát |
| **Admin** | Role ADMIN | Management subnet toàn bộ port | **Deny** mặc định | Bastion không đồng nghĩa cho phép lateral movement |
| **Partner** | Role PARTNER | Partner API VIP TCP 443 | Allow | Chỉ dịch vụ hợp đồng |
| **Partner** | Role PARTNER | DNS/Management/DB khác | **Deny** trừ phụ thuộc xác minh | Cách ly đối tác |
| **Mọi VPN user** | Any role | Internet/private đích ngoài policy | Deny tại protected network | Không mở phạm vi do có tunnel |

**Lưu ý:** ma trận ở tầng mạng chỉ kiểm soát địa chỉ/cổng. Với HTTPS có thể cần thêm **application authorization** để phân biệt chức năng của một API. Khi nhiều hostname chia sẻ một IP:443, rule IP/port **không tự giới hạn được hostname hoặc API cụ thể**; cần gateway/L7 policy phù hợp.

### 6.1. Một rule phải có đủ metadata

Một quy tắc thực tế nên nêu: **ID, owner, source identity/role hoặc verified pool, destination, protocol/port, action, chiều flow, enforcement point, lý do, ngày phê duyệt, test case, hạn rà soát và log policy**. Rule có thể đang tồn tại nhưng không nằm trên đường gói đi qua; cần xác minh **data path thực tế**.

## 7. Split tunneling và full tunneling

### 7.1. Split tunneling

Với **split tunnel**, chỉ các prefix/tài nguyên được cấu hình gửi qua VPN, còn traffic đến Internet thường đi qua gateway mạng hiện tại của client.

~~~mermaid
flowchart TB
    C[Laptop từ xa] -->|10.20.10.0/24 theo VPN route| V[VPN tunnel / gateway]
    C -->|Internet traffic theo local default route| I[Local ISP / Internet]
    V --> F[VPN Firewall]
    F --> A[Approved private app]
    F --x D[Other private networks]
~~~

**Lợi ích:** giảm tải VPN gateway, băng thông và độ trễ cho traffic Internet; đôi khi phù hợp khi SaaS có cơ chế bảo vệ endpoint và identity riêng.

**Rủi ro:** thiết bị đồng thời kết nối mạng cục bộ có thể không tin cậy và mạng nội bộ VPN, khó giám sát toàn bộ egress tại corporate gateway; DNS hoặc IPv6 có thể đi đường không dự kiến; ứng dụng local network có thể tăng rủi ro nếu endpoint bị xâm nhập.

### 7.2. Full tunneling

Với **full tunnel**, phần lớn hoặc toàn bộ IP traffic thuộc phạm vi cấu hình được đưa vào VPN, thường bằng route mặc định qua tunnel. Tùy sản phẩm, có thể có ngoại lệ cho mạng local hoặc đường đến chính VPN server.

**Lợi ích:** tổ chức có thể áp egress firewall, DNS filtering, inspection hoặc chính sách mạng tập trung cho traffic đi qua gateway.

**Rủi ro:** tăng tải gateway, độ trễ và chi phí, yêu cầu HA/DDoS/capacity; nếu triển khai không đầy đủ **IPv4/IPv6**, vẫn có đường egress ngoài tunnel. Full tunnel có thể làm hỏng dịch vụ local/voice/conference nếu QoS hoặc định tuyến chưa phù hợp.

### 7.3. So sánh theo mục tiêu bảo mật

| Tiêu chí | Split tunnel | Full tunnel |
|---|---|---|
| Route tới private subnet | Một số prefix được push/configure | Thường có cả route mặc định qua tunnel |
| Internet egress | Thường qua ISP của client | Thường qua gateway được quản lý |
| Tải lên VPN gateway | Thấp hơn cho traffic SaaS công khai | Cao hơn, cần capacity planning |
| Khả năng quan sát Internet traffic | Phụ thuộc endpoint/SSE và mạng local | Có thể quan sát tại gateway nếu traffic thật sự đi qua |
| Rủi ro DNS/IPv6 leak | Cần kiểm tra | **Cũng cần kiểm tra** |
| Quyền tới mạng internal | **Phải có firewall/identity policy** | **Cũng phải có firewall/identity policy** |
| Truy cập LAN local | Có thể giữ theo route | Có thể bị hạn chế, phụ thuộc ngoại lệ |

**Không có lựa chọn nào mặc định luôn an toàn hơn trong mọi bối cảnh.** Quyết định theo threat model, tài sản, khả năng thiết bị, egress/SSE và quy định tổ chức. Dù chọn cách nào, **source VPN không được có quyền mặc định đến toàn bộ private network**.

## 8. Pushed routes, traffic selectors và AllowedIPs không thay quyền truy cập

Các loại VPN có cấu hình đường đi và ràng buộc IP khác nhau:

| Công nghệ | Khái niệm liên quan | Vai trò thực tế | Giới hạn cần nhớ |
|---|---|---|---|
| **IPsec/IKEv2** | Traffic selectors / SPD, IPsec SAs | Xác định traffic được bảo vệ trong các Security Association | Cần policy firewall/zone và kiểm tra authorization; selector không thay phân quyền ứng dụng |
| **SSL/TLS-based VPN** | Pushed routes, user/group policy, gateway ACL | Điều hướng client và kiểm soát quyền qua VPN product | Client route không đủ nếu gateway vẫn forward tự do |
| **WireGuard** | AllowedIPs của từng peer và route phía client | Gắn prefix với peer để chọn hướng và kiểm tra IP nguồn theo cryptokey routing | Không phải quyền truy cập cấp ứng dụng; firewall vẫn cần hạn chế đích/port ở protected network |
| **Site-to-site VPN** | Tunnel interfaces, traffic selectors, BGP/static routes | Nối các subnet/AS qua tunnel | Route propagation sai có thể mở rộng mạng không dự kiến |
| **Per-app/ZTNA access** | App resource/connector/identity policy | Giới hạn tài nguyên theo ứng dụng thay vì toàn mạng | Phải kiểm tra connector reachability và backend authorization |

### 8.1. WireGuard AllowedIPs phải được hiểu theo hai phía

Trong WireGuard, **AllowedIPs** có ý nghĩa **cryptokey routing**: lựa chọn peer cho gói đi tới một đích và kiểm tra gói đã giải mã có IP nguồn thuộc prefix được phép của peer tương ứng. Ở **client**, AllowedIPs thường ảnh hưởng những đích được đưa vào tunnel; ở **server**, AllowedIPs cho một client thường là **IP nguồn VPN riêng được cấp cho client**.

**Không cấu hình AllowedIPs trên server bằng toàn bộ mạng private mà client muốn truy cập nếu điều đó làm sai mapping IP nguồn của peer.** Và **không coi AllowedIPs ở client là mạng mà server bắt buộc phải cấp quyền**: gateway/firewall vẫn cần lọc đích mà peer được phép đi tới.

### 8.2. IPsec selectors và mạng được phép

Trong IPsec, traffic selectors định nghĩa traffic được bảo vệ trong SA theo chính sách của các bên. Tùy thiết kế **policy-based** hay **route-based IPsec**, cách selectors và tunnel interface kết hợp với route/ACL có khác biệt. Một tunnel chấp nhận traffic giữa dải A và B **không chứng minh mọi giao thức/cổng trong dải ấy nên được phép**.

Với site-to-site, nên quản lý **prefix selectors/route scope** và **firewall policy** cùng nhau để tránh route được học từ tunnel nhưng đích nhạy cảm bị mở rộng ngoài yêu cầu.

## 9. Xác thực, MFA, chứng chỉ và quyền truy cập sau VPN

### 9.1. Authentication khác authorization

**Authentication (AuthN)** kiểm tra người hoặc thiết bị là ai. **Authorization (AuthZ)** xác định danh tính đó được truy cập tài nguyên nào. Thiết kế VPN tốt cần cả hai:

1. **Kết nối:** xác thực client/gateway và bảo vệ kênh mật mã.
2. **Người dùng:** IAM/IdP, MFA theo mức rủi ro, trạng thái tài khoản/nhóm.
3. **Thiết bị:** chứng chỉ, device compliance/EDR, mã hóa đĩa, cập nhật hệ điều hành nếu chính sách yêu cầu.
4. **Session:** gắn role/entitlement cụ thể và IP pool hoặc identity context cho data plane.
5. **Policy:** chỉ cho phép tới những mạng/dịch vụ tương ứng với entitlement còn hiệu lực.
6. **Ứng dụng:** tiếp tục xác thực/phân quyền theo user, tenant và object.

**MFA thành công không biến thiết bị thành an toàn tuyệt đối**. Tài khoản có thể bị lộ phiên, endpoint có thể bị xâm nhập và các quyền mạng quá rộng vẫn gây rủi ro lateral movement.

### 9.2. Nhóm IAM và sự đồng bộ chính sách

Một nhóm SSO như **VPN-ENGINEERING** không nên chỉ được ánh xạ bằng chuỗi text do client gửi. VPN gateway phải nhận quyết định từ **IdP/RADIUS/NAC tin cậy**, kiểm tra chữ ký/kênh phù hợp và đảm bảo cập nhật khi thành viên nhóm thay đổi.

Khi người dùng bị rút quyền hoặc thiết bị không đạt posture, tổ chức cần quy trình **ngắt session/re-evaluate authorization** phù hợp năng lực nền tảng. Không mặc định đổi nhóm trong directory sẽ ngay lập tức cập nhật mọi session VPN đang mở.

### 9.3. Quyền quản trị đặc biệt

Truy cập **Management** nên dùng nhóm và cơ chế riêng: MFA mạnh, thiết bị managed, approval/JIT nếu thích hợp, bastion, session audit và chỉ dịch vụ quản trị được phê duyệt. Không đưa quản trị viên vào cùng một allow rule **10.0.0.0/8 any port** chỉ vì họ có trách nhiệm vận hành.

## 10. Thiết kế rule theo source, destination, service và identity

### 10.1. Bốn trường bắt buộc

Một rule mạng điển hình cần phân biệt:

- **Nguồn:** role/user/device đã xác minh hoặc pool IP nguồn được gắn cứng với chính sách.
- **Đích:** hostname giải qua gateway phù hợp, VIP, IP hoặc prefix theo service; ưu tiên scope nhỏ khi ổn định.
- **Giao thức/cổng:** TCP, UDP, ICMP/ICMPv6 cần thiết, hoặc điều kiện ứng dụng ở L7.
- **Hành động:** allow/deny, logging và giới hạn thời gian/condition.

**Source IP không phải người dùng.** VPN IP có thể tái cấp, NAT có thể gộp nhiều người và dual-stack có thể cấp hai loại địa chỉ. Nếu dùng pool để tách role, phải kiểm soát **không lẫn pool, không spoof IP nguồn trong tunnel, quản lý lease/session lifecycle và log identity mapping**.

### 10.2. Đặt rule ở đâu?

| Điểm thực thi | Bảo vệ được gì | Giới hạn |
|---|---|---|
| **VPN gateway** | Từ chối ngay traffic từ session không được phép | Phụ thuộc engine có per-user/per-group policy và inspect traffic không |
| **Inter-zone firewall** | Giới hạn từ VPN zone tới App/DB/Management | Phải nằm trên route thực, tránh bypass qua switch/peering |
| **Cloud security group/network ACL** | Bảo vệ workload và subnet cloud | Identity người dùng VPN có thể đã bị NAT; policy cần mapping |
| **Host firewall** | Chặn inbound tới máy đích | Cần quản lý tập trung và không thay lớp network segmentation |
| **Application/API gateway** | Phân quyền cụ thể theo endpoint/action/user | Không thay network ACL bảo vệ DB, SSH hoặc dịch vụ khác |
| **ZTNA/identity-aware gateway** | Cấp quyền theo từng ứng dụng/identity | Cần cấu hình tài nguyên và connector tới đúng backend |

**Tránh một điểm lỗi duy nhất:** nếu policy ở gateway đúng nhưng cloud VPC có route ngang khác, workload có thể vẫn reachable qua một đường phụ. Ngược lại, nếu cloud firewall chỉ lọc theo IP nguồn nhưng gateway NAT tất cả client về một IP, rule không còn phân biệt được employee với admin.

## 11. Ví dụ thiết kế policy dạng giả mã

Đây là **pseudocode phục vụ review**, không phải cấu hình có thể áp thẳng lên WireGuard, strongSwan, OpenVPN, firewall, cloud hoặc hệ điều hành cụ thể.

~~~yaml
vpn_access_policy:
  id: "VPN-REMOTE-ACCESS-009"
  owner: "Network Security"
  policy_version: "v1"
  mode: "identity-and-device-aware"
  default_action: "deny"
  sources:
    employees:
      identity_group: "VPN-EMPLOYEE"
      verified_pool: "10.255.10.0/24"
      mfa_required: true
      managed_device_required: true
    admins:
      identity_group: "VPN-ADMIN"
      verified_pool: "10.255.20.0/24"
      mfa_required: true
      managed_device_required: true
      privileged_session_required: true
  rules:
    - id: "R-EMP-APP"
      source: "employees"
      destination: "10.20.10.15/32"
      protocol: "tcp"
      destination_port: 443
      action: "allow"
    - id: "R-EMP-DNS-UDP"
      source: "employees"
      destination: "10.20.5.53/32"
      protocol: "udp"
      destination_port: 53
      action: "allow"
    - id: "R-EMP-DNS-TCP"
      source: "employees"
      destination: "10.20.5.53/32"
      protocol: "tcp"
      destination_port: 53
      action: "allow"
    - id: "R-ADMIN-BASTION"
      source: "admins"
      destination: "10.20.90.10/32"
      protocol: "tcp"
      destination_port: 443
      action: "allow"
  controls:
    deny_vpn_client_to_database_directly: true
    deny_vpn_client_to_management_except_approved_bastion: true
    prevent_source_ip_spoofing: true
    validate_ipv4_and_ipv6: true
    separate_authn_and_authz_logs: true
    verify_return_routes: true
    require_change_approval: true
    remove_expired_exceptions: true
  validation:
    - "allowed-app-connectivity"
    - "denied-database-connectivity"
    - "denied-management-connectivity"
    - "unauthorized-group-cannot-use-admin-role"
    - "dns-and-identity-services-work"
    - "ipv6-and-split-tunnel-coverage"
~~~

**Lưu ý cách triển khai:** dải nguồn, role và phiên VPN phải có cơ chế liên kết đáng tin. Một số VPN/firewall không hỗ trợ kiểm tra user group ngay trên flow; khi đó cần kiến trúc thay thế như **tách gateway, tách pool theo role, dynamic policy được kiểm soát, microsegmentation hoặc ZTNA**. Không viết rule tham chiếu group tưởng tượng rồi coi như đã được enforcement.

## 12. DNS và split DNS: truy cập đúng tên nhưng không mở quá nhiều mạng

Khi người dùng cần truy cập **orders.internal.example**, hệ thống phải phân giải đúng địa chỉ theo DNS view được phép. Với remote-access VPN, doanh nghiệp có thể dùng **split DNS**: các suffix nội bộ gửi đến resolver doanh nghiệp, các tên khác dùng resolver phù hợp với chính sách. Trong full tunnel có thể định tuyến DNS qua gateway trung tâm.

### 12.1. Các tình huống lỗi

| Vấn đề | Hậu quả | Cần kiểm tra |
|---|---|---|
| Client không nhận DNS server/suffix nội bộ | Không phân giải được app dù route đúng | VPN profile, OS resolver, split DNS |
| Client có DNS nhưng không có quyền hỏi | DNS timeout/SERVFAIL tùy nguồn lỗi | VPN firewall cho UDP/TCP 53, resolver ACL |
| DNS trả IP ở subnet chưa được phép | Tên phân giải được nhưng kết nối bị deny | App owner, IPAM, firewall policy, DNS view |
| Browser/ứng dụng dùng DoH riêng | Truy vấn không qua resolver mong đợi | Endpoint policy, browser policy, routing |
| DNS A hợp lệ nhưng AAAA đi đường khác | Kết nối IPv6 bypass hoặc lỗi | IPv4/IPv6 policy, IPv6 gateway/routes |
| Cloud private DNS/conditional forward sai | Một số site/zone không resolve được | VPC/VNet DNS, conditional forwarder, peering |
| Cùng hostname trong split-horizon views | Hai client nhận IP khác | Thiết kế zone và nguồn DNS có thẩm quyền |

**DNS cho biết địa chỉ, không cấp quyền tới địa chỉ đó.** Không cho phép toàn dải server nội bộ chỉ vì một hostname có thể được resolve ra nhiều IP; nếu dịch vụ cần IP thay đổi động, cân nhắc **application gateway, proxy, service tagging có nguồn đáng tin hoặc ZTNA**.

### 12.2. DNS egress và dữ liệu nhạy cảm

DNS query từ VPN có thể tiết lộ tên host nội bộ và nhu cầu ứng dụng. Giới hạn resolver theo role, quản trị log và retention, không cho client tùy tiện dùng DNS server không tin cậy cho các zone nội bộ nhạy cảm.

Đừng chặn toàn bộ TCP/53 chỉ vì hầu hết query dùng UDP. DNS có thể cần TCP cho các tình huống hợp lệ; DoT/DoH cũng cần được quản lý theo chính sách, không đơn giản bằng một rule UDP.

## 13. IPv6: bảo vệ tương đương IPv4 và tránh đường vòng

Một kiến trúc VPN có thể hoạt động tốt với IPv4 nhưng không xử lý đúng IPv6. Ví dụ client có IPv6 native từ nhà mạng, trong khi VPN chỉ push các IPv4 private routes; một dịch vụ nội bộ có bản ghi AAAA hoặc đường IPv6 riêng có thể đi ngoài tunnel.

### 13.1. Các câu hỏi cần trả lời

1. VPN có hỗ trợ **IPv6 trong tunnel** không và dùng prefix nào?
2. Split tunnel hoặc full tunnel có thực sự áp **route IPv6 phù hợp**, hay mới có route 0.0.0.0/0?
3. Firewall có **IPv6 allow/deny** tương đương IPv4 tại cùng trust boundary không?
4. Có DNS AAAA/split DNS phù hợp, cùng route tới các IPv6 subnet nội bộ không?
5. Có client nào dùng IPv6 link-local/ULA/global ở local network tạo đường ngoài tunnel?
6. Nếu nền tảng không hỗ trợ IPv6 VPN, có chính sách endpoint/egress rõ ràng để tránh unapproved IPv6 paths không?

### 13.2. Không tắt ICMPv6 vô điều kiện

ICMPv6 phục vụ Neighbor Discovery, PMTU và các chức năng quan trọng khác. Firewall phải chặn/cho phép **theo type/code và bối cảnh**, không block tất cả khiến kết nối IPv6 hợp lệ hỏng. Cũng không dùng cách "tắt toàn bộ IPv6" như một giải pháp mặc định cho lỗi VPN IPv6 nếu không có yêu cầu và đánh giá của tổ chức.

### 13.3. Ví dụ ma trận dual-stack

| Luồng | IPv4 | IPv6 | Mục tiêu |
|---|---|---|---|
| Employee → App API | 10.20.10.15 TCP 443 | Địa chỉ IPv6 của app nếu có | Chỉ cho ứng dụng được duyệt |
| Employee → DB | Deny | Deny | Không cho DB direct |
| Admin → Bastion | Allow có điều kiện | Allow có điều kiện nếu hỗ trợ | Quản trị qua đường kiểm soát |
| VPN → Management trực tiếp | Deny | Deny | Không mở management subnet |
| DNS nội bộ | Cho phép resolver cần thiết | Tương ứng nếu resolver IPv6 | Split DNS đúng |

## 14. Overlapping CIDR, NAT và định tuyến hồi đáp

### 14.1. Địa chỉ mạng nhà và doanh nghiệp bị chồng lấn

Ví dụ laptop dùng mạng Wi-Fi tại nhà **192.168.1.0/24**, trong khi doanh nghiệp cũng dùng **192.168.1.0/24** cho một subnet cần truy cập. Client có thể chọn route local thay vì VPN hoặc ngược lại. Đây là **CIDR overlap/routing ambiguity**, không phải lỗi authentication.

Các hướng xử lý phụ thuộc quy mô và chính sách:

- Quy hoạch lại subnet doanh nghiệp bằng IPAM khi có thể.
- Dùng **per-application access / ZTNA** để không phụ thuộc việc route nguyên subnet tới client.
- Thiết kế NAT đặc biệt hoặc mapping service rõ ràng, có giám sát và tài liệu hóa.
- Nếu dùng route cụ thể hơn, phải hiểu longest-prefix match, ảnh hưởng tới local client network và thay đổi qua roaming.

**Không đẩy route rộng tùy tiện như 192.168.0.0/16** nhằm "giúp VPN nhìn thấy tất cả mạng", vì có thể ảnh hưởng mạng local và vô tình tăng bề mặt truy cập.

### 14.2. Đường hồi đáp (return route)

Cho phép luồng từ VPN tới app chưa đủ nếu app/gateway không có route để trả gói về **VPN client address pool**. Có thể dùng route rõ ràng hoặc NAT theo kiến trúc, nhưng phải kiểm tra:

- App có route tới 10.255.10.0/24 qua đúng VPN gateway hay không?
- Firewall stateful có thấy cả hai chiều của phiên TCP/UDP cần thiết không?
- Có ECMP, dual-homing hoặc VPN failover tạo **asymmetric return path** không?
- Nếu dùng SNAT tại gateway, downstream firewall còn nhận diện được role/user không?
- NAT và IP pool có trùng với VPC/VNet hoặc partner network khác không?

### 14.3. Route có nhưng bị chặn là kết quả có thể đúng

Một client có route tới DB subnet nhưng firewall **deny** toàn bộ DB direct theo policy: đây không nhất thiết là lỗi. Mục tiêu thường là **không để user giao tiếp được với DB**, chứ không yêu cầu mọi bảng route phải không chứa prefix DB. Tuy nhiên giảm route quảng bá không cần thiết vẫn có lợi cho sự rõ ràng và giảm bề mặt lỗi.

## 15. Cloud VPN, site-to-site và route propagation

### 15.1. Site-to-site VPN khác remote-access

Site-to-site VPN nối **hai hoặc nhiều miền mạng**. Nó có thể truyền route bằng **BGP** hoặc static routes. Nếu cho phép tự động quảng bá quá rộng, một mạng đối tác có thể được học vào nhiều VPC/VNet, subnet hoặc site mà không có phê duyệt.

Trong site-to-site, giới hạn cần áp dụng cho:

- **Prefix được phép xuất/nhập** ở tunnel/gateway.
- **BGP import/export policy** hoặc static route scope.
- **Route tables và attachments** tại transit/hub/spoke/VRF.
- **Firewall rules** bảo vệ cả subnet và workload.
- **Quyền truy cập dịch vụ ứng dụng**; network path không chứng minh user có quyền.

### 15.2. Trường hợp cloud

Một cloud VPN kết nối vào **Transit Gateway, Virtual WAN, hub VNet hoặc routing appliance** có thể làm route từ site A xuất hiện ở site B. Nhưng một route propagation được phê duyệt có thể là mục tiêu thiết kế, không mặc định là lỗ hổng. Hãy xác định:

1. Attachment/subnet nào học route?
2. Route table association và propagation có phạm vi gì?
3. VPN/BGP neighbor nào là nguồn route?
4. Cloud firewall/security group/NACL có nằm trên đường đi thật không?
5. Có thể tới **management, DB hoặc shared service** ngoài hợp đồng không?

### 15.3. Không coi encryption là segmentation

IPsec bảo vệ gói qua đường mạng giữa hai đầu VPN theo chính sách bảo mật, nhưng **một tunnel được mã hóa vẫn có thể mang traffic không được phép tới subnet nhạy cảm** nếu route/ACL sai. Encryption và least privilege là hai chức năng bổ sung, không thay thế nhau.

## 16. VPN trong kiến trúc Zero Trust và phân đoạn mạng

Nguyên tắc **Zero Trust** không mặc định tin một yêu cầu chỉ vì nó đến từ "inside" hoặc qua VPN. Nguồn request phải được xác thực và đánh giá theo chính sách cho mỗi tài nguyên phù hợp.

### 16.1. VPN truyền thống theo mạng

Client được cấp route tới một hoặc nhiều subnet; firewall giới hạn port/đích. Mô hình vẫn phù hợp trong nhiều môi trường nhưng cần bảo vệ chống lateral movement.

### 16.2. ZTNA/per-application access

User thường được cấp quyền tới **ứng dụng/tài nguyên cụ thể** qua một điểm trung gian xác thực, thay vì có route tự do tới subnet. Điều này giảm bề mặt mạng nhìn thấy, nhưng **connector/proxy phía sau vẫn phải bị giới hạn** để không thể truy cập bất kỳ backend nào thay cho người dùng.

### 16.3. Tầng kiểm soát đề xuất

| Lớp | Kiểm soát |
|---|---|
| Identity | SSO, MFA, group, session lifetime, revocation |
| Device | Certificate, EDR/MDM posture, OS update, disk encryption theo policy |
| Tunnel | Cấu hình mật mã hiện đại, kiểm soát client/server identity, key lifecycle |
| Routing | Push đúng route cần thiết, không quảng bá full private network ngoài mục tiêu |
| Segmentation | VPN zone riêng, firewall default deny tới App/DB/Management |
| Workload | Host firewall, API gateway, service authentication, authorization |
| Monitoring | VPN/auth logs, route/ACL changes, firewall flows, SIEM/NDR alerts |
| Response | Revoke sessions/keys, rollback policy, kiểm tra đường lateral movement |

**Nếu firewall chỉ lọc theo địa chỉ được NAT chung**, hãy kiểm tra cách phân biệt user/role bằng policy phía gateway hoặc service proxy. Một kiến trúc Zero Trust không nên dựa hoàn toàn vào "nằm trong VPN subnet".

## 17. Các lỗi cấu hình làm mở quyền ngoài dự kiến

| Lỗi | Hậu quả | Kiểm soát sửa chữa |
|---|---|---|
| Cho VPN pool vào **10.0.0.0/8 any port** | Nhiều subnet nhạy cảm reachable | Default deny, allow host/service/role cụ thể |
| Chỉ giới hạn pushed routes, gateway vẫn cho mọi traffic | Client có thể đổi route hoặc traffic qua đường khác | Enforce tại gateway/firewall |
| Một VPN group chung cho mọi người | Khó tách quyền employee/admin/partner | IAM roles và policy riêng |
| SNAT mọi người thành một IP rồi filter downstream theo IP | Mất phân biệt người dùng | Per-session policy trước NAT hoặc gateway có identity |
| Rule IPv4 chặt nhưng IPv6 allow rộng | Đường vòng dual-stack | IPv6 policy/route/DNS parity |
| Cho toàn subnet DB vì một API dùng DB | Lateral movement tới DB | Mở API 443; backend tự kết nối DB qua policy riêng |
| Cloud VPN export mọi route từ transit | Partner/remote thấy mạng không cần thiết | BGP/filter/route-table propagation có phạm vi |
| Static route return đi sai firewall | Bypass enforcement, flow state lỗi | Kiểm tra data path hai chiều |
| DNS internal trả IP ngoài danh sách cho phép | App lỗi hoặc nhóm vận hành mở rule quá rộng | Split DNS, policy theo service, IPAM và app gateway |
| Quyền admin tồn tại vĩnh viễn | Tăng tác động khi account bị xâm nhập | JIT, approval, expiration và audit |
| Quyền còn sau khi user rời nhóm | Session cũ vẫn truy cập | Re-evaluate/revoke session theo khả năng |
| ACL gắn sai interface/direction/zone | Rule có nhưng không lọc traffic thật | Test allow/deny từ nguồn đã xác thực |
| Cho phép ICMP/UDP/TCP toàn bộ vì "VPN cần hoạt động" | Mở thêm dịch vụ ngoài scope | Chỉ cho các protocol cần thiết theo thiết kế |
| VPN có failover qua gateway khác nhưng policy không đồng nhất | Quyền mở rộng khi chuyển tuyến | Kiểm thử gateway HA và policy drift |

## 18. Cấu hình kiểm soát theo identity thay vì dựa hoàn toàn vào IP

### 18.1. Dữ liệu tối thiểu cần cho quyết định

Một policy theo user thường cần:

- **User ID đã xác thực**, group/role và thời điểm nhóm được xác nhận.
- **Device ID hoặc certificate identity**, trạng thái compliance nếu có.
- **VPN session ID** và pool IP được cấp, thời điểm bắt đầu/kết thúc.
- **Destination** và giao thức/cổng; policy/rule ID.
- **Risk/session context** (nếu phù hợp): yêu cầu reauth, thiết bị lạ hoặc quyền tạm.

Các thông tin này cần được truyền/đối chiếu qua kênh đáng tin. **Không dùng username ghi trong IP header hoặc HTTP header do client tự tạo** để cấp quyền mạng.

### 18.2. Khi sản phẩm chỉ hỗ trợ ACL theo subnet

Có thể tách VPN pool theo group role và gắn group tại gateway. Nhưng cần đảm bảo:

1. User EMPLOYEE **không thể tự chiếm** IP của pool ADMIN khi tunnel hoạt động.
2. Pool ADMIN được cấp **chỉ sau khi policy xác thực** và chỉ cho session có quyền.
3. Failover/gateway dự phòng giữ đúng mapping và các rule tương ứng.
4. NAT không làm mất phân biệt vai trò khi đi xuống firewall.
5. Khi session kết thúc, lease được thu hồi/ghi log; IP tái sử dụng không làm log hiểu sai người dùng.

Nếu không đáp ứng những điều này, nên dùng **identity-aware enforcement, separate gateway/VRF hoặc ZTNA** thay vì suy rằng mọi traffic tới từ một prefix đều thuộc nhóm đúng.

## 19. Logging và SIEM: chứng minh chính sách đã thực thi

### 19.1. Những nguồn cần tương quan

| Nguồn | Trường hữu ích | Câu hỏi |
|---|---|---|
| **IdP/MFA** | user, group, auth result, device, session | Ai được xác thực và vì sao? |
| **VPN gateway** | tunnel ID, IP pool, connected/disconnected, posture, policy version | Session nào có đường vào protected network? |
| **VPN/firewall flow log** | source, destination, protocol, port, allow/deny, rule ID | Gói nào thực sự được cho qua/chặn? |
| **DNS resolver** | client mapping, domain, answer, time | Client cố truy cập dịch vụ nào? |
| **Cloud flow/security log** | workload/subnet, direction, action | Có route/policy khác cho traffic đi vòng không? |
| **Application/SSO log** | user, request ID, authorization result | Truy cập mạng đã dẫn tới thao tác nghiệp vụ nào? |
| **NDR/IDS/IPS** | anomalous flows, lateral movement indicators | Có mô hình truy cập vượt nhu cầu? |
| **Change management** | config version, owner, thời điểm deploy | Sự cố trùng với policy thay đổi nào? |

### 19.2. Ví dụ event chuẩn hóa minh họa

~~~json
{
  "event_time": "2026-11-28T07:15:42Z",
  "source": "vpn-firewall",
  "vpn_session_id": "session-7c91",
  "identity": "user-123",
  "role": "EMPLOYEE",
  "assigned_vpn_ip": "10.255.10.24",
  "destination_ip": "10.20.30.12",
  "protocol": "tcp",
  "destination_port": 5432,
  "decision": "DENY",
  "policy_id": "VPN-REMOTE-ACCESS-009",
  "rule_id": "DEFAULT-DENY-DB",
  "policy_version": "v1"
}
~~~

Đây chỉ là **schema học tập**. Nền tảng thật có thể không ghi user/role trực tiếp trong firewall log; cần mapping từ VPN session/time hoặc identity engine. Không copy raw access token, cookie, mật khẩu, khóa riêng hoặc dữ liệu khách hàng vào SIEM.

### 19.3. Chỉ số cần giám sát

- **Tỷ lệ phiên VPN có MFA/posture đúng** theo role.
- **Số network/service mà mỗi role có thể reach**, đo qua policy và kiểm thử.
- **Deny events** từ VPN tới DB, Management, dịch vụ không được duyệt; quan sát hành vi lặp bất thường.
- **Policy drift** giữa gateway chính/dự phòng, IPv4/IPv6 và cloud.
- **Số quyền tạm hết hạn chưa thu hồi**, quyền admin không còn owner.
- **Session IP mapping completeness** để điều tra đúng user sau NAT hoặc tái cấp.
- **Sự cố DNS, route, MTU, packet loss, return path** và user-facing service availability.

Không dùng số deny event tăng như bằng chứng chắc chắn bị tấn công. Nó có thể xuất phát từ lỗi DNS, route, ứng dụng retry, một đợt thay đổi policy hoặc kiểm thử được cấp phép.

## 20. Chẩn đoán an toàn trên Linux

Những lệnh sau chỉ **quan sát trạng thái và thử một đích được phép**. Không cần thay route, restart VPN, xóa firewall hoặc scan subnet production để tìm hiểu quyền truy cập.

~~~bash
# Xem interface và địa chỉ tunnel/client hiện có
ip -br address

# Xem route IPv4 và IPv6
ip route
ip -6 route

# Kiểm tra đường dự kiến tới một địa chỉ app được cho phép
ip route get 10.20.10.15

# Kiểm tra đường dự kiến tới một IP DB không được cấp quyền
# Lưu ý: thấy route KHÔNG có nghĩa sẽ kết nối được.
ip route get 10.20.30.12

# Xem resolver configuration theo systemd-resolved nếu có
resolvectl status

# Kiểm tra đúng một endpoint HTTPS thuộc môi trường được phép
curl -sS -I --max-time 5 https://app.internal.example/
~~~

**Giải thích:** kết quả **ip route get** cho biết lựa chọn route cục bộ ở thời điểm truy vấn; nó **không xác thực ACL ở gateway** và cũng không chứng minh tunnel hoạt động end-to-end. Địa chỉ ví dụ có thể không tồn tại trong lab; thay bằng tài sản thử nghiệm đã được cấp quyền.

### 20.1. Kiểm tra một TCP endpoint đã được chuẩn bị

~~~bash
# Kiểm thử đúng một IP/port được tổ chức sở hữu và cho phép
nc -vz -w 3 10.20.10.15 443

# Kiểm tra endpoint dự kiến DENY chỉ trong test plan được phê duyệt
nc -vz -w 3 10.20.30.12 5432
~~~

Nếu một kết nối **timeout/refused**, chưa đủ kết luận firewall VPN đã chặn đúng. Có thể do app không lắng nghe, DNS, host firewall, route hoặc ACL khác. Phải đối chiếu **rule ID/final action** và kiểm tra dịch vụ test đích đang hoạt động. Thử DENY trên tài sản nhạy cảm chỉ khi có **test window, owner và phạm vi rõ**.

## 21. Chẩn đoán an toàn trên Windows

~~~powershell
# Xem IP, interface, DNS và gateway
Get-NetIPConfiguration

# Bảng route IPv4/IPv6
Get-NetRoute

# Cấu hình IP đã cấp cho thiết bị
Get-NetIPAddress

# Chẩn đoán đường đi đến đúng một đích được phép
Test-NetConnection -ComputerName 10.20.10.15 -Port 443 -InformationLevel Detailed

# Kiểm tra DNS server theo adapter
Get-DnsClientServerAddress

# Tham khảo định tuyến theo command-line truyền thống
route print
~~~

**Không lấy việc VPN adapter xuất hiện hoặc giao diện báo Connected làm bằng chứng quyền đã giới hạn**. Phải kiểm tra từ client theo role thực, đo những đích được cho phép và từ chối, và so với log ở enforcement point.

## 22. Ma trận kiểm thử policy mạng qua VPN

Để tránh làm gián đoạn production, dùng **tài khoản/thiết bị test và đích test được cấp phép**, hoặc môi trường staging mô phỏng ACL thật. Không scan rộng hoặc thử brute force giao thức quản trị.

| Test | Nguồn/đích hoặc kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| **T-01** | EMPLOYEE → App HTTPS | Allow | VPN session/flow log, HTTP success |
| **T-02** | EMPLOYEE → DB trực tiếp | Deny | Firewall final deny tại đúng policy |
| **T-03** | EMPLOYEE → Management | Deny | Gateway/inter-zone firewall logs |
| **T-04** | ADMIN → Bastion đúng dịch vụ | Allow có điều kiện | MFA/posture, gateway log, bastion audit |
| **T-05** | EMPLOYEE → Admin bastion | Deny | Role mapping và deny rule |
| **T-06** | PARTNER → API được duyệt | Allow đúng host/service | VPN/gateway/app logs |
| **T-07** | PARTNER → các subnet khác | Deny | Inter-zone policy/flow logs |
| **T-08** | Thiết bị không đáp ứng posture | VPN hoặc resource access bị từ chối | IdP/NAC/VPN policy log |
| **T-09** | User rời nhóm và session cũ còn mở | Quyền được thu hồi theo thời gian/chính sách | Re-evaluation/revocation event |
| **T-10** | Thử route thêm thủ công ở client test | Không vượt được server-side enforcement | Gateway firewall deny; chỉ trong lab |
| **T-11** | Split tunnel với mạng local | Đường local/enterprise đúng thiết kế, không có quyền nội bộ thừa | Route table và egress logs |
| **T-12** | Full tunnel IPv4/IPv6 | Đúng phạm vi, không bỏ sót IPv6 | Routes, external IP/egress policy, flow logs |
| **T-13** | Internal DNS và split DNS | Tên nội bộ resolve đúng, ngoài scope theo chính sách | Resolver configuration, DNS logs |
| **T-14** | Home LAN chồng CIDR internal | Phát hiện overlap và xử lý theo thiết kế | Client route, support case |
| **T-15** | App return path về VPN pool | Luồng được phép thành công và stateful inspection đúng | FIB/route, flow log, app telemetry |
| **T-16** | SNAT tại VPN gateway | Downstream policy không nhận nhầm mọi user cùng role | NAT mapping, identity flow |
| **T-17** | VPN gateway failover | Allow/deny không đổi ngoài dự kiến | Policy hashes/versions, failover test |
| **T-18** | Cloud site-to-site route propagation | Chỉ prefix/phạm vi được phép được học | BGP/route table audit và firewall |
| **T-19** | Quyền tạm hết hạn | Không còn access sau thời điểm được duyệt | Entitlement history và flow deny |
| **T-20** | Đổi config VPN/ACL | Test baseline vẫn đúng, không mở lateral access | Diff, CI policy test, test report |

### 22.1. Test phải có cả trường hợp ALLOW và DENY

Nếu chỉ đo DENY, có thể vô tình **chặn luôn DNS, SSO, ứng dụng hợp lệ**. Nếu chỉ đo ALLOW, có thể bỏ sót **DB/Management được mở ngoài ý muốn**. Ma trận phải có cả hai, và **kiểm tra sau failover hoặc thay policy**.

### 22.2. Phân biệt “route không có” và “policy chặn”

Nếu client không có route tới subnet nhạy cảm, điều này **có thể phù hợp mục tiêu giảm exposure**, nhưng chưa kiểm chứng **server-side deny**. Ở môi trường test có phép, cần xác nhận deny ở gateway/firewall bằng kiểm tra policy và log; tránh suy từ một ping timeout hoặc netcat timeout là hệ thống đã an toàn.

## 23. Runbook triển khai hạn chế mạng truy cập qua VPN

### Bước 1 — Inventory và threat model

Lập danh sách **VPN types/gateways, user roles, identity provider, client pools, subnet/VRF, cloud attachments, ứng dụng, DNS và thiết bị quản trị**. Định nghĩa đâu là tài sản nhạy cảm và các đường có thể bypass VPN firewall.

### Bước 2 — Thu thập nhu cầu thực

Phỏng vấn owner ứng dụng và dùng **flow logs đã được phép** để biết user thật sự cần IP/port nào, bao gồm SSO, DNS, NTP, service discovery và các phụ thuộc. Không suy rằng mọi kết nối đang thấy đều hợp lệ; một ứng dụng sai cấu hình hoặc mã độc cũng có thể tạo traffic.

### Bước 3 — Thiết kế access matrix

Định nghĩa rule theo **verified role + destination service + protocol/port + environment**, default deny; xác định cơ chế truy cập quản trị đặc biệt và thời hạn ngoại lệ. Gắn từng rule với owner/change ticket.

### Bước 4 — Kiểm tra data path hai chiều

Xác minh VPN tunnel, route client, VPN gateway, inter-zone firewall, cloud routes, host firewall và đường return; kiểm tra **NAT và IPv6**, tránh có một gateway dự phòng chưa nhận policy.

### Bước 5 — Pilot và đo tác động

Triển khai trên nhóm test/canary trước, kiểm thử ma trận ALLOW/DENY và đo DNS, application SLI, session disconnects, độ trễ và trải nghiệm người dùng. Có version policy cũ và rollback được phê duyệt.

### Bước 6 — Rollout theo nhóm

Áp policy theo role và nguồn tài sản, tránh đổi tất cả nhóm một lúc. Giám sát deny bất thường, ticket, công cụ quản trị/remote desktop và hiệu năng VPN gateway.

### Bước 7 — Thu hồi ngoại lệ và bảo trì

Khi ứng dụng chuyển subnet, provider thay route, user đổi vai trò hoặc partner contract kết thúc, review và xóa quyền không còn cần. Thực hiện regression sau thay đổi **IdP, VPN firmware, cloud routing, DNS, firewall, IPv6 và gateway HA**.

~~~mermaid
flowchart TD
    A[Inventory VPN/roles/assets] --> B[Threat model và access matrix]
    B --> C[Thiết kế default deny + allow theo service]
    C --> D[Kiểm tra route/NAT/IPv6/return path]
    D --> E[Pilot có test allow + deny]
    E --> F{Đúng quyền và ứng dụng hợp lệ hoạt động?}
    F -- Không --> G[Điều tra log, sửa scope hoặc rollback]
    G --> C
    F -- Có --> H[Rollout có giám sát]
    H --> I[Review entitlement, ngoại lệ và policy drift]
    I --> B
~~~

## 24. Runbook khi phát hiện VPN mở mạng quá rộng

### Tình huống

SOC phát hiện nhiều session thuộc role EMPLOYEE có thể mở kết nối trực tiếp tới subnet Database sau một đợt cập nhật firewall. Đây là **khả năng vượt quyền ở tầng mạng**, dù chưa chứng minh có truy cập dữ liệu trái phép.

### Giai đoạn 1 — Xác nhận và giữ bằng chứng

1. Ghi policy version, change ticket, VPN gateway, user role/pool và phạm vi subnet có thể tiếp cận.
2. Xác minh **đường đi thực**: kết nối qua VPN gateway/firewall nào, có NAT/IPv6 hoặc route dự phòng không.
3. Kiểm tra rule cho phép có **source quá rộng, destination any hoặc zone sai**.
4. So VPN session logs, firewall allow flows và DB/application audit để biết có truy cập thực sự hay chỉ có khả năng kết nối.
5. Giữ log và snapshot cấu hình hợp lệ theo quy trình, không xuất secret/tokens.

### Giai đoạn 2 — Giảm thiểu và khôi phục policy

- Theo mức độ khẩn cấp, áp một **deny rule có phạm vi chính xác** hoặc rollback policy lỗi đã xác minh theo quyền vận hành.
- Giữ luồng nghiệp vụ cần thiết tới API front-end để tránh cắt toàn bộ người dùng.
- Nếu có dấu hiệu tài khoản/thiết bị bị xâm nhập, phối hợp IAM/SOC để **revoke VPN session, rotate/revoke credential/certificate** theo mức rủi ro.
- Kiểm tra gateway HA, IPv6 và cloud route tables có cùng phạm vi mở lỗi không.
- Tránh tạo rule tạm **allow any** để giải quyết ticket trước mắt.

### Giai đoạn 3 — Xác minh

Thực hiện test **EMPLOYEE → App ALLOW** và **EMPLOYEE → DB DENY**, cùng ADMIN/Partner use cases, DNS/SSO và hồi đáp. Kiểm tra flow log và ứng dụng. Chỉ đóng sự cố khi **quyền truy cập mạng và nhu cầu nghiệp vụ đều đúng**.

### Giai đoạn 4 — Hậu kiểm

Xác định nguyên nhân: chính sách match-all, sai thứ tự rule, role mapping, NAT che identity, IPv6 thiếu deny, route mới hoặc thay đổi entitlement. Bổ sung **policy-as-code linting, reviewer, test phủ deny, expiration** và kiểm tra drift tự động.

## 25. Những tình huống thực tế cần phân biệt

### Tình huống A — Employee chỉ có route App nhưng vẫn truy cập DB được

**Quan sát:** client chỉ được push route 10.20.10.0/24, nhưng trong một bài test được duyệt, gói đến DB 10.20.30.12 vẫn tới nơi qua một đường khác.

**Nguyên nhân có thể:** client có default route qua VPN, route bổ sung, NAT/forwarding qua app server hoặc firewall mở any-source. **Bài học:** pushed route không phải enforcement.

### Tình huống B — Admin bật full tunnel rồi không dùng được Internet

**Quan sát:** sau kết nối VPN, Internet web/DNS không hoạt động nhưng app nội bộ vẫn dùng được.

**Khả năng:** chưa có **egress NAT/firewall/DNS** cho Internet qua gateway, hoặc route IPv6 bị xử lý không nhất quán. Khắc phục phải theo mục tiêu full tunnel và egress policy, không mở toàn private network để “sửa mạng”.

### Tình huống C — Cloud VPN hoạt động nhưng user không vào được API

**Quan sát:** route từ client tới App CIDR đúng, tunnel up, nhưng kết nối timeout.

**Khả năng:** cloud security group, host firewall, route hồi đáp tới VPN pool hoặc DNS trỏ sai IP. Cần đối chiếu **firewall deny vs no return path vs application down**.

### Tình huống D — Engineer có quyền Git nhưng nhìn thấy Management

**Quan sát:** sau mở route rộng để dùng Git/CI, kỹ sư có thể reach các IP quản trị cùng subnet hoặc qua shared gateway.

**Nguyên nhân:** dùng subnet-wide allow thay vì **service VIP/host TCP 443**, hoặc có peering/VRF leak. Sửa bằng tách zone/microsegmentation, mở đúng dịch vụ và kiểm thử cả direct management deny.

### Tình huống E — Partner dùng tunnel site-to-site và thấy prefix đối tác khác

**Quan sát:** một peer site-to-site quảng bá hoặc học nhiều route hơn hợp đồng.

**Nguyên nhân:** BGP export/import rộng, route propagation của cloud hub hoặc static route không được giới hạn. Áp prefix/route filtering và firewall đúng zone, xác minh với các bên. Đây có thể là **route leak/segmentation mistake**, không phải chỉ là vấn đề remote-access user.

### Tình huống F — Đổi nhóm IAM nhưng user còn truy cập

**Quan sát:** user rời nhóm ADMIN ở IdP, nhưng session VPN cũ vẫn dùng quyền admin.

**Nguyên nhân có thể:** authorization được snapshot lúc login, token/session chưa hết hạn hoặc gateway chưa revalidate role. Cần **session revocation/re-evaluation** đúng nền tảng và kiểm tra bằng audit log.

### Tình huống G — IPv4 bị chặn, IPv6 vẫn vào được dịch vụ

**Quan sát:** test IPv4 DB direct bị deny, còn IPv6 đích tương ứng reachable.

**Nguyên nhân:** thiếu deny policy IPv6, split DNS trả AAAA, cloud route IPv6 rộng hoặc gateway chỉ quản lý IPv4. Cần test và xử lý dual-stack nhất quán.

### Tình huống H — Kết nối bị từ chối sau NAT dù VPN policy allow

**Quan sát:** gateway cho phép user EMPLOYEE tới app, nhưng firewall sau NAT không nhận diện đúng nguồn và deny.

**Nguyên nhân:** policy downstream sử dụng pool client chưa được chuyển NAT, hoặc NAT chung làm sai role mapping. Không giải quyết bằng allow toàn subnet; sửa **identity propagation/NAT policy**, hoặc áp authorization trước khi NAT.

## 26. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Kết nối VPN thành công nghĩa là được vào mọi subnet.” | Tunnel establishment khác authorization; cần policy theo role và service. |
| “Chỉ push route App thì DB chắc không reachable.” | Client/default/alternate routes vẫn có thể tồn tại; enforce ở gateway/firewall. |
| “Full tunnel là bảo mật hơn trong mọi trường hợp.” | Còn phụ thuộc egress controls, endpoint posture, capacity và IPv6. |
| “Split tunnel làm mất mọi khả năng bảo vệ.” | Có thể bảo vệ bằng endpoint/SSE/ZTNA và policy private network phù hợp. |
| “AllowedIPs ở WireGuard là ACL ứng dụng.” | AllowedIPs thực hiện cryptokey routing/source checks, không thay firewall đích/port. |
| “IPsec traffic selectors thay firewall.” | Selectors xác định traffic protected trong SA; vẫn cần network/application ACL. |
| “MFA đủ để mở toàn bộ 10.0.0.0/8.” | MFA không loại bỏ nhu cầu least privilege và phân đoạn. |
| “Role = tên header client tự gửi.” | Policy phải dựa trên identity source được xác thực. |
| “DNS trả về IP là IP đó được cấp phép.” | DNS là phân giải tên, không phải quyết định quyền truy cập. |
| “IPv4 rule deny là đã chặn cả IPv6.” | Phải kiểm tra IPv6 ACL/route/DNS riêng. |
| “Cloud route propagation mặc định an toàn.” | Cần giới hạn attachments/prefix và firewall ở data path. |
| “Firewall có rule deny là chắc đã chặn.” | Rule chỉ có hiệu lực nếu đúng interface/zone/order và traffic đi qua. |
| “Tất cả user dùng chung NAT IP thì downstream biết từng user.” | Identity có thể bị mất; cần mapping hoặc enforcement trước NAT. |
| “Ping timeout chứng minh tài nguyên không reachable.” | Host firewall/ICMP/route có thể gây timeout; cần evidence ở policy engine. |
| “User rời nhóm là VPN session tự mất quyền lập tức.” | Phụ thuộc session refresh/revocation của sản phẩm. |
| “VPN bảo vệ nội dung nên không cần TLS cho ứng dụng.” | TLS/app authn/authz vẫn cần để bảo vệ từng dịch vụ. |

## 27. Checklist trước khi đưa policy VPN vào production

- [ ] Kiểm kê VPN gateway, mode remote-access/site-to-site, user pool, subnet, VRF, cloud, partner và owner.
- [ ] Mô tả nhu cầu access theo vai trò, danh tính đã xác thực, thiết bị và dịch vụ.
- [ ] Dùng **default deny** tại điểm enforcement phù hợp; chỉ allow đúng destination/service/port.
- [ ] Không cho EMPLOYEE hoặc PARTNER truy cập trực tiếp DB/Management ngoài quyền được phê duyệt.
- [ ] Truy cập ADMIN đi qua đường kiểm soát như bastion hoặc ZTNA, với MFA và audit.
- [ ] Hiểu pushed routes/split tunnel/full tunnel **không thay authorization**.
- [ ] Với WireGuard, phân biệt AllowedIPs phía client và server; có firewall giới hạn đích.
- [ ] Với IPsec, kiểm tra selectors, route-based/policy-based setup và inter-zone ACL.
- [ ] Có kiểm soát anti-spoofing IP nguồn của VPN peer/client và mapping identity → pool chính xác.
- [ ] Policy áp đúng cả **IPv4/IPv6**, kiểm tra DNS A/AAAA và không tạo đường vòng.
- [ ] DNS/split DNS/DoH/DoT phù hợp, chỉ cho client dùng resolver/zone được phép.
- [ ] Kiểm tra route overlap với LAN tại nhà, partner network, VPC/VNet và cloud transit.
- [ ] Đảm bảo return routes, stateful firewall và NAT không làm sai role enforcement.
- [ ] Các vùng App/DB/Management được phân đoạn; workload có host/application authorization.
- [ ] Kiểm tra gateway chính/dự phòng, HA/failover và policy drift.
- [ ] Không dựa vào IP nguồn đã bị NAT làm bằng chứng identity khi thiếu mapping tin cậy.
- [ ] Có session revocation, entitlement expiration và review quyền tạm.
- [ ] Ghi log VPN/AuthN/AuthZ/firewall/app với session ID, role, source, destination và rule ID.
- [ ] Bảo vệ log và thông tin nhạy cảm; không lưu token/credential ở ticket.
- [ ] Ma trận test có **ALLOW và DENY** cho Employee, Admin, Partner, IPv4/IPv6.
- [ ] Mọi thay đổi có owner, ticket, policy version, canary, rollback và regression tests.
- [ ] Giám sát truy cập ngang, policy anomaly, cloud route propagation và các trường hợp bypass.
- [ ] Không scan/đổi route/chỉnh ACL trên production ngoài quy trình được cấp phép.

## 28. Câu hỏi tự kiểm tra

**1. Vì sao VPN đã mã hóa chưa đủ bảo vệ toàn mạng nội bộ?**  
Mã hóa bảo vệ kênh theo VPN protocol; nếu sau khi vào tunnel user được phép kết nối tới mọi subnet, quyền mạng vẫn quá rộng và tạo rủi ro lateral movement.

**2. Route và firewall policy khác nhau ở đâu?**  
Route chọn đường đi tới IP/prefix; firewall policy quyết định gói từ một nguồn có được kết nối tới đích/giao thức/cổng đó hay không.

**3. Vì sao pushed route hẹp không được coi là một biện pháp authorization độc lập?**  
Client có thể có route khác hoặc bị thay đổi cấu hình; gateway/firewall mới phải cưỡng chế không cho traffic ngoài quyền.

**4. Split tunnel và full tunnel ảnh hưởng thế nào đến quyền truy cập private subnet?**  
Chúng chủ yếu quy định traffic qua VPN hay qua đường local. **Cả hai vẫn cần** default deny và allow theo role/service tại protected network.

**5. WireGuard AllowedIPs đã đủ giới hạn DB access chưa?**  
Chưa. AllowedIPs liên quan cryptokey routing và kiểm tra IP nguồn; server-side firewall và authorization vẫn cần hạn chế đích DB/port.

**6. Vì sao nhân viên không nên có route/ACL any-port tới Database?**  
Ứng dụng nên truy cập DB qua backend được phân quyền; mở DB direct tăng rủi ro đánh cắp dữ liệu hoặc lateral movement khi endpoint bị xâm nhập.

**7. Tại sao rule deny IPv4 chưa chắc chặn được IPv6?**  
IPv6 có địa chỉ, route và ACL riêng; client có thể nhận AAAA và kết nối theo stack khác.

**8. Nếu client có route App nhưng kết nối timeout, cần xem gì?**  
VPN auth/session, firewall final action, return route, NAT, DNS, app listening/host firewall và cloud policy để phân biệt nguyên nhân.

**9. Tại sao cùng một VPN NAT IP có thể gây sai phân quyền downstream?**  
Nhiều user có thể xuất hiện dưới cùng IP; firewall chỉ nhìn IP đó không biết ai là ADMIN/EMPLOYEE nếu identity không được truyền/đối chiếu đáng tin.

**10. Làm thế nào đánh giá quyền user đã bị thu hồi thực sự?**  
Kiểm tra IdP group, VPN session lifetime/revocation, policy enforcement và test deny được phép; không chỉ nhìn trạng thái tài khoản ở directory.

**11. Site-to-site VPN route propagation có thể gây rủi ro gì?**  
Prefix của site/partner có thể được quảng bá vào zone không được phép, tạo đường route tới dữ liệu nhạy cảm; cần import/export filters và firewall.

**12. Tại sao cần kiểm thử cả luồng ALLOW và DENY sau khi thay VPN policy?**  
Để chắc tài nguyên hợp lệ vẫn dùng được đồng thời các mạng nhạy cảm không bị mở vượt quyền; chỉ một loại test không đủ chứng minh policy đúng.

## 29. Tài liệu tham khảo

- [NIST SP 800-46 Rev. 2 — Guide to Enterprise Telework, Remote Access, and Bring Your Own Device (BYOD) Security](https://csrc.nist.gov/pubs/sp/800/46/r2/final): bối cảnh bảo vệ remote access và thiết bị từ xa.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): kiểm soát quyền theo tài nguyên và giảm tin cậy ngầm dựa trên vị trí mạng.
- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): nguyên tắc thiết kế và kiểm tra firewall rule.
- [RFC 4301 — Security Architecture for the Internet Protocol](https://www.rfc-editor.org/rfc/rfc4301): IPsec policy, Security Associations và phạm vi bảo vệ IP.
- [RFC 7296 — Internet Key Exchange Protocol Version 2 (IKEv2)](https://www.rfc-editor.org/rfc/rfc7296): thương lượng IPsec SA và traffic selectors.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): nền tảng TLS hiện đại cho các dịch vụ và một số kiến trúc tunnel.
- [WireGuard — Cryptokey Routing](https://www.wireguard.com/#cryptokey-routing): ý nghĩa của AllowedIPs và ánh xạ peer.
- [RFC 1918 — Address Allocation for Private Internets](https://www.rfc-editor.org/rfc/rfc1918): các dải IPv4 private và lưu ý thiết kế địa chỉ mạng.
- [RFC 4193 — Unique Local IPv6 Unicast Addresses](https://www.rfc-editor.org/rfc/rfc4193): IPv6 ULA trong kiến trúc mạng private.
- [RFC 4632 — Classless Inter-domain Routing (CIDR)](https://www.rfc-editor.org/rfc/rfc4632): prefix/routing và nguyên tắc phân chia dải địa chỉ.
- [NIST Cybersecurity Framework 2.0](https://www.nist.gov/cyberframework): quản trị rủi ro, bảo vệ, phát hiện, ứng phó và khôi phục.

**Ghi nhớ:** Muốn giới hạn mạng qua VPN, không chỉ cấu hình tunnel hay danh sách route, mà phải thực thi **ít quyền nhất tại đúng đường truyền**: xác minh danh tính/thiết bị, xác định subnet và dịch vụ thực sự cần, dùng **default deny + allow theo role/đích/cổng**, kiểm soát cả IPv4/IPv6, DNS, NAT, đường hồi đáp và cloud propagation. Đánh giá thành công bằng **cả các kết nối được phép vẫn hoạt động và các kết nối trái quyền bị chặn có bằng chứng**.
