# Tin rằng mạng nội bộ luôn an toàn

## 1. Ngộ nhận phổ biến: “Đã ở trong LAN thì có thể tin tưởng”

Một nhân viên mở ứng dụng qua mạng văn phòng. Máy tính của họ có địa chỉ riêng như `10.10.20.34`, kết nối Wi-Fi doanh nghiệp và đi qua firewall biên. Từ đó, đội vận hành dễ suy luận rằng các kết nối xuất phát từ mạng nội bộ đều đáng tin, vì chúng đã “nằm sau firewall”.

**Đây là một giả định nguy hiểm.** Mạng nội bộ chỉ mô tả một vị trí hoặc miền kết nối; nó không chứng minh người dùng là ai, máy có được quản lý hay không, phiên đăng nhập có bị chiếm hay không, tiến trình nào đang tạo kết nối, hoặc hành động đó có được phép hay không.

Một máy nội bộ có thể bị cài mã độc qua phishing, bị khai thác từ ứng dụng, bị đánh cắp phiên VPN, dùng tài khoản dịch vụ quá quyền, bị người có quyền nội bộ lạm dụng hoặc được đưa vào mạng qua cổng Ethernet/Wi-Fi cấu hình sai. Trong cloud, một workload bị chiếm có thể kết nối tới tài nguyên khác trong cùng VPC/VNet mà không cần đi qua firewall Internet. Vì vậy, **“internal” không tương đương “trusted”**.

Bài học này thuộc chương **Sai lầm thường gặp** trong module **SECURITY_NETWORK_SECURITY**. Nội dung kết nối phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, Wi-Fi, cloud, giám sát lưu lượng và mô hình hóa mối đe dọa để sửa tận gốc cách suy nghĩ dựa quá nhiều vào ranh giới mạng.

Sau bài học, người học cần có khả năng:

- Giải thích vì sao vị trí mạng, IP private, NAT, VLAN và VPN không tự tạo danh tính hoặc quyền truy cập.
- Nhận diện các đường xâm nhập và di chuyển ngang trong mạng nội bộ.
- Đặt các câu hỏi đúng khi xét quyền truy cập giữa người dùng, thiết bị, ứng dụng và tài sản.
- Thiết kế bảo vệ nhiều lớp với xác thực, phân quyền, phân đoạn, quản lý thiết bị và giám sát.
- Đề xuất phép thử **được phép/bị cấm** để xác minh chính sách thay vì tin vào sơ đồ mạng.
- Ưu tiên cải thiện theo rủi ro thực tế, giảm tác động vận hành và ghi nhận các điểm mù.

## 2. Tại sao mạng nội bộ từng bị xem là miền đáng tin?

Nhiều kiến trúc truyền thống đặt hệ thống nội bộ phía sau một firewall biên. Internet là “bên ngoài”, còn LAN là “bên trong”. Cách phân chia đó có giá trị nhất định: firewall biên giảm các kết nối không mong muốn từ Internet, VPN tạo kênh truyền được bảo vệ, LAN có thể áp ACL và hệ thống quản trị truy cập tài nguyên theo vùng.

Vấn đề xuất hiện khi một **ranh giới phòng vệ hữu ích** trở thành **quy tắc cấp quyền mặc định**:

- Ứng dụng tin bất kỳ yêu cầu nào từ `10.0.0.0/8`.
- Server chỉ kiểm tra IP nguồn nhưng không xác thực danh tính người gọi.
- Máy trạm người dùng được phép kết nối SMB/RDP/SSH tới nhiều máy chủ.
- VPN có MFA ở bước đăng nhập nhưng sau đó cấp toàn bộ mạng nội bộ.
- Wi-Fi khách hoặc thiết bị IoT được đưa vào cùng VLAN với máy quản trị.
- Cloud security group cho phép kết nối từ toàn bộ VPC vì “đều là mạng riêng”.

Lúc này, attacker chỉ cần đạt được **một chỗ đứng bên trong** rồi có thể khai thác sự tin tưởng ngầm của các hệ thống khác. Cửa Internet có thể được bảo vệ tốt nhưng chuyển động giữa các máy bên trong lại ít được kiểm soát.

**Ranh giới mạng vẫn quan trọng.** Điều cần thay đổi là cách dùng chúng: một vùng mạng giúp giới hạn đường đi và giảm phạm vi ảnh hưởng, còn **quyền truy cập phải gắn với danh tính, chức năng, trạng thái thiết bị, tài sản đích và chính sách hiện hành**.

## 3. Bảy mệnh đề dễ nhầm lẫn

| Khẳng định thường nghe | Điều thực tế có thể đúng | Cách xác minh thay vì suy đoán |
|---|---|---|
| “IP `192.168.x.x` là an toàn” | Đây là dải địa chỉ private, không xác định độ tin cậy của thiết bị hoặc người dùng | Xác thực principal, device identity, nguồn địa chỉ và quyền ứng dụng |
| “Có NAT nên hacker không vào được” | NAT thay đổi địa chỉ/đường đi, không phải cơ chế xác thực hoặc chính sách bảo mật hoàn chỉnh | Kiểm tra firewall state/rule, port forwarding, egress, pivot và truy cập east-west |
| “Đã vào VPN là nhân viên hợp lệ” | Phiên VPN có thể dùng tài khoản/thiết bị bị chiếm; người hợp lệ vẫn có thể thiếu quyền vào tài sản đích | MFA, device posture, quyền theo nhóm/ứng dụng, logging và re-evaluation |
| “Cùng VLAN nên cứ cho nhau kết nối” | VLAN là cơ chế phân tách L2; trong cùng VLAN vẫn có thể cần host firewall, ACL, identity-aware controls | Kiểm tra quyền máy–máy, dịch vụ quản trị, cấu hình switch/AP và lưu lượng thực |
| “Firewall đã chặn Internet rồi” | Lưu lượng east-west trong cùng mạng có thể không đi qua firewall biên | Dựng đường đi thực tế và đặt điểm kiểm soát/telemetry đúng vị trí |
| “Dùng TLS thì không thể bị tấn công” | TLS bảo vệ kênh và có thể xác thực server/client nếu cấu hình đúng; phía đầu cuối hoặc người có credential vẫn có thể bị xâm phạm | Kiểm tra xác thực, phân quyền, certificate validation, session và endpoint |
| “Không thấy cảnh báo IDS nghĩa là không có xâm nhập” | Sensor có thể không thấy lưu lượng nội bộ, lưu lượng mã hóa hoặc kiểu tấn công hợp lệ về giao thức | Đánh giá telemetry coverage, log xác thực, EDR, flow, DNS và thử nghiệm phát hiện |

Một nguy cơ thường gặp là **bảo vệ biên rất mạnh nhưng cấp quyền nội bộ rất rộng**. Nhiều chuỗi tấn công không cần vượt firewall Internet lần thứ hai: chúng dùng tài khoản hợp lệ và dịch vụ quản trị được mở sẵn.

## 4. Chỗ đứng ban đầu xuất hiện bên trong bằng cách nào?

Mạng nội bộ không phải không gian đóng. Có nhiều đường để một kẻ tấn công hoặc thiết bị không đáng tin xuất hiện trên đó.

| Con đường | Ví dụ ở mức phòng thủ | Bài học thiết kế |
|---|---|---|
| **Phishing / social engineering** | Máy trạm nhân viên chạy tệp độc hại, từ đó phát sinh kết nối LAN | Máy trạm cần quyền tối thiểu; phải phát hiện lateral movement |
| **Tài khoản hoặc phiên bị chiếm** | Credential VPN/SSO bị lộ, attacker đăng nhập qua cổng hợp lệ | Xác thực mạnh, bảo vệ phiên, giới hạn quyền theo tài nguyên |
| **Ứng dụng public bị xâm phạm** | Web server trong DMZ bị kiểm soát và cố kết nối database, AD hoặc backup | Phân đoạn DMZ, kiểm soát egress và danh tính ứng dụng |
| **Thiết bị cá nhân/BYOD** | Laptop không đạt chuẩn bảo mật kết nối Wi-Fi hoặc cổng mạng | 802.1X, NAC, mạng riêng và đánh giá trạng thái thiết bị |
| **IoT/OT/printer/camera** | Thiết bị ít được vá hoặc dùng tài khoản mặc định có đường vào cùng LAN | Tách vùng, chỉ cấp luồng cần thiết, giám sát giao thức |
| **Bên thứ ba / nhà cung cấp** | Tài khoản hỗ trợ từ xa có VPN rộng, không hết hạn | Just-in-time access, giới hạn phạm vi, audit và expiry |
| **Workload cloud bị chiếm** | Một VM/pod bị khai thác dùng kết nối nội bộ đến storage hoặc database | Security group, NetworkPolicy, workload identity, least privilege |
| **Người có quyền nội bộ** | Người dùng sử dụng quyền hoặc dữ liệu ngoài phạm vi công việc | Phân quyền, logging, phê duyệt và kiểm soát bất thường |

**Sự xâm nhập có thể xảy ra dù mọi thiết bị đều có IP private.** Vì thế câu hỏi “kẻ xấu có vào LAN được không?” phải được bổ sung bằng “khi một tài khoản, endpoint hoặc workload bên trong bị chiếm, phạm vi truy cập tiếp theo là gì?”.

## 5. Vì sao lateral movement là hậu quả điển hình?

**Lateral movement (di chuyển ngang)** là quá trình mở rộng quyền truy cập từ một chỗ đứng ban đầu sang máy, tài khoản hoặc vùng mạng khác. Nó có thể sử dụng giao thức hoàn toàn hợp lệ như SMB, RDP, SSH, WinRM, RPC, Kerberos, API quản trị hoặc dịch vụ điều phối cloud.

Ví dụ một chuỗi giả định:

~~~mermaid
flowchart LR
  A["Máy trạm bị chiếm"] -->|"SMB/RDP được mở rộng"| B["Máy ứng dụng"]
  B -->|"Dùng quyền dịch vụ quá rộng"| C["Database"]
  B -->|"Kết nối quản trị chưa giới hạn"| D["Backup/Management"]
  E["Firewall Internet"] -.->|"Không quan sát toàn bộ east-west"| B
~~~

Điều kiện khiến chuỗi này dễ xảy ra:

1. Mạng cho máy người dùng kết nối tới cổng quản trị của máy chủ không liên quan.
2. Một tài khoản quản trị hoặc tài khoản dịch vụ có thể đăng nhập trên nhiều máy.
3. Máy chủ tin yêu cầu từ địa chỉ nội bộ mà không kiểm tra quyền ứng dụng.
4. Các vùng mạng không có deny boundary rõ ràng hoặc ACL có rule “any-any”.
5. Không có log cho các phiên giữa máy nội bộ, hoặc chỉ đặt IDS ở cổng Internet.
6. Quyền của máy backup, domain controller, DNS lõi hoặc hệ thống định danh quá rộng.

Không phải mọi kết nối east-west là tấn công. Backup, triển khai phần mềm và tác vụ quản trị hợp lệ có thể tạo các mẫu tương tự. Người điều tra phải tương quan **nguồn → đích → tài khoản → thời gian → kết quả xác thực → hành động** thay vì quy kết từ một TCP connection.

### Bài toán blast radius

Nếu một workstation bị chiếm, attacker **không nên tự động** có đường mạng đến:

- Máy chủ cơ sở dữ liệu có dữ liệu nhạy cảm.
- Hệ thống định danh, domain controller hoặc máy chủ cấp chứng chỉ.
- Hệ thống backup và lưu trữ bản sao bất biến.
- Thiết bị firewall/router/switch ở management VLAN.
- Khóa bí mật, control plane và công cụ triển khai production.

**Blast radius** là phạm vi hậu quả mà một chỗ đứng ban đầu có thể gây ra. Phân đoạn, tách quyền và giám sát làm giảm blast radius ngay cả khi không thể ngăn mọi xâm nhập ban đầu.

## 6. Trust boundary: lập ranh giới theo tài sản và quyền truy cập

Một ranh giới tin cậy (*trust boundary*) xuất hiện tại nơi quyền, danh tính, mức bảo vệ hoặc quyền quản trị thay đổi. Các ranh giới thường cần đánh giá:

- **Internet ↔ DMZ / edge service:** dịch vụ public được phép nhận traffic nào?
- **User / BYOD ↔ application tier:** máy người dùng có cần nói chuyện trực tiếp với máy chủ backend không?
- **Application ↔ database:** chỉ workload nào được kết nối và với tài khoản nào?
- **Guest / IoT ↔ internal:** thiết bị ít tin cậy có được đi đến vùng lõi không?
- **Development ↔ production:** có tồn tại kết nối vì tiện vận hành mà không có chủ sở hữu?
- **VPN ↔ internal:** vào VPN có được coi là có quyền với mọi dịch vụ không?
- **Cloud VPC/VNet ↔ on-prem:** tunnel riêng có bị hiểu nhầm là một miền tin cậy duy nhất không?
- **Workload ↔ management plane:** application host có thể gọi API quản trị, kubelet, cloud metadata hoặc SSH không?

### Ví dụ phân đoạn thay cho mạng phẳng

~~~mermaid
flowchart TD
  U["User VLAN"] -->|"HTTPS/443"| P["Reverse proxy / ứng dụng"]
  P -->|"App protocol theo nhu cầu"| A["Application tier"]
  A -->|"DB protocol giới hạn"| D["Database tier"]
  J["Jump host đã xác thực"] -->|"SSH/RDP quản trị"| A
  J -->|"DBA access có kiểm soát"| D
  G["Guest / BYOD VLAN"] -->|"Internet qua chính sách riêng"| I["Internet"]
  G -.->|"DENY"| D
  U -.->|"DENY quản trị trực tiếp"| D
  U -.->|"DENY"| M["Management VLAN"]
  T["SOC / monitoring"] -->|"Log và telemetry có kiểm soát"| A
~~~

Sơ đồ mô tả **chính sách mong muốn**, không phải bằng chứng hệ thống đã triển khai đúng. Khi kiểm thử cần xét cả đường đi khác như IPv6, VPN, peering cloud, NAT, load balancer và đường failover.

### Ma trận luồng tối thiểu

| Nguồn | Đích | Dịch vụ | Kết quả dự kiến | Vì sao |
|---|---|---|---|---|
| User VLAN | Reverse proxy | HTTPS/443 | Allow | Truy cập ứng dụng được công bố |
| User VLAN | Database | TCP/5432 | Deny | Không có nhu cầu truy cập DB trực tiếp |
| Application tier | Database | TCP/5432 | Allow từ workload được duyệt | Chức năng nghiệp vụ |
| Guest VLAN | Management VLAN | SSH/22, HTTPS admin | Deny | Tách mạng không tin cậy khỏi quản trị |
| Jump host | Thiết bị quản trị | SSH/HTTPS có xác thực | Allow giới hạn | Quản trị có kiểm soát và audit |
| Workstation bất kỳ | Backup/Domain Controller | Cổng quản trị | Deny nếu không thuộc luồng được duyệt | Hạn chế lan truyền và phá hoại |
| Monitoring subnet | Các agent/endpoint cần thiết | Port theo thiết kế | Allow đúng nguồn/đích | Bảo đảm giám sát không phải mở toàn mạng |

Cần kiểm tra các phụ thuộc thật trước khi chặn luồng. Trong môi trường Windows, một số dịch vụ sử dụng RPC và cổng động; việc chặn bừa TCP/445 hoặc dải port cao có thể làm hỏng AD, backup hoặc quản trị. **Mục tiêu là quyền tối thiểu có kiểm chứng**, không phải ngắt mọi kết nối nội bộ.

## 7. Zero Trust: thay giả định tin cậy bằng quyết định truy cập liên tục

**Zero Trust** là cách tiếp cận loại bỏ quyền tin cậy mặc định chỉ vì người dùng hoặc máy đang “ở bên trong”. Mỗi yêu cầu truy cập cần được đánh giá theo chính sách có ngữ cảnh, với phạm vi quyền tối thiểu, giám sát và khả năng thu hồi.

Nó không có nghĩa là mọi request phải hỏi mật khẩu liên tục, hoặc một sản phẩm “Zero Trust” có thể tự động thay thế mọi firewall và phân đoạn. Mục tiêu là áp dụng kiểm soát phù hợp tại **điểm thực thi chính sách** để không phải tin mù quáng vào địa chỉ nguồn.

### Những thuộc tính nên dùng trong quyết định truy cập

| Thuộc tính | Câu hỏi thực hành | Giới hạn |
|---|---|---|
| **User/service identity** | Ai đang thực hiện? Có được xác thực bằng cơ chế phù hợp không? | Credential và token có thể bị đánh cắp |
| **Device identity / posture** | Thiết bị có được quản lý, vá lỗi, mã hóa và bảo vệ endpoint không? | Posture có thể thay đổi sau khi cấp phiên |
| **Resource identity** | Đích là dịch vụ nào, đang ở môi trường nào, độ nhạy ra sao? | IP và hostname có thể thay đổi hoặc bị dùng chung |
| **Requested action** | Chỉ xem dữ liệu hay thao tác quản trị/thay đổi cấu hình? | Mở một cổng không đủ để diễn tả quyền ở lớp ứng dụng |
| **Context** | Thời gian, nguồn, mức rủi ro phiên, cảnh báo và hành vi bất thường? | Tín hiệu ngữ cảnh không bao giờ chính xác tuyệt đối |
| **Policy decision** | Có được phép, bị từ chối, yêu cầu xác minh thêm hay giới hạn quyền? | Cần audit và xử lý lỗi policy engine an toàn |
| **Session lifecycle** | Quyền có hết hạn, được đánh giá lại và thu hồi khi nguy cơ thay đổi không? | Phiên dài, cache và fallback có thể tạo lỗ hổng |

Ví dụ: một kỹ sư hỗ trợ có VPN hợp lệ vẫn chỉ được vào một máy bastion và những server được phân công. Truy cập tới database sản xuất phải yêu cầu quyền riêng và có logging. Nếu thiết bị mất trạng thái tuân thủ, quyền truy cập có thể bị giới hạn theo chính sách thay vì duy trì vô thời hạn.

### Các lớp bảo vệ phối hợp

1. **Xác thực:** MFA, khóa/bí mật được bảo vệ, chứng chỉ thiết bị hoặc workload identity ở nơi phù hợp.
2. **Phân quyền:** RBAC/ABAC, quyền theo ứng dụng, danh tính dịch vụ và nguyên tắc least privilege.
3. **Bảo vệ endpoint:** vá lỗi, EDR, kiểm soát đặc quyền, cấu hình máy trạm/server an toàn.
4. **Phân đoạn:** firewall, security group, host firewall, microsegmentation, VPN policy, NetworkPolicy.
5. **Mã hóa và xác thực đầu cuối:** TLS/mTLS/SSH/IPsec với kiểm tra chứng chỉ và chống downgrade theo chính sách.
6. **Giám sát và phản ứng:** identity logs, flow telemetry, DNS, proxy, IDS/IPS, endpoint logs và quy trình xử lý sự cố.

Các lớp này giảm phụ thuộc vào một yếu tố đơn lẻ. Mất một lớp không nên lập tức cho mọi luồng đi qua.

## 8. Mạng Wi-Fi, BYOD và thiết bị IoT: bên trong không đồng nhất về độ tin cậy

Wi-Fi doanh nghiệp thường có nhiều nhóm thiết bị khác nhau: máy được quản lý, thiết bị cá nhân, khách, camera, máy in, thiết bị hội nghị, cảm biến và thiết bị OT. Đưa các nhóm này vào cùng broadcast domain hoặc cấp full corporate VLAN chỉ vì chúng “ở văn phòng” là cách tạo đường tấn công rộng.

### Phương án phòng vệ

- **SSID/VLAN theo vai trò:** tách employee, guest, IoT/OT và management theo nhu cầu.
- **802.1X/EAP-TLS** cho thiết bị phù hợp, kết hợp NAC để xác định danh tính thiết bị và quyền truy cập. Mức bảo đảm phụ thuộc triển khai chứng chỉ và quản lý lifecycle.
- **Restricted/critical VLAN** khi AAA lỗi nếu tổ chức cho phép; VLAN này chỉ được truy cập rất hạn chế, không mở toàn bộ internal.
- **Client isolation** trong guest/BYOD phù hợp: hạn chế máy khách nói chuyện trực tiếp với nhau.
- **Quản trị AP/controller:** chỉ từ management zone, xác thực mạnh và audit.
- **Không dựa vào MAC address như yếu tố xác thực mạnh:** MAC có thể giả mạo; MAC Authentication Bypass dành cho trường hợp tương thích có kiểm soát.

Một switch port vật lý hay SSID không chứng minh người cắm vào là nhân viên. Chứng minh cần kết hợp **identity, device posture, network authorization và giám sát**.

## 9. VPN không biến thiết bị từ xa thành thiết bị đáng tin

VPN tạo kết nối được bảo vệ qua mạng không tin cậy, nhưng **chỉ riêng tunnel được mã hóa không xác định quyền của mọi ứng dụng nằm sau tunnel**.

Sai lầm điển hình: sau khi người dùng đăng nhập VPN thành công, gateway cấp route đến toàn bộ subnet `10.0.0.0/8`, gồm management, backup, database và hệ thống định danh. Nếu laptop bị chiếm hoặc phiên người dùng bị lạm dụng, attacker có đường mạng đến nhiều tài sản hơn mức cần thiết.

Thiết kế an toàn hơn:

- Chỉ quảng bá route và cho phép traffic đến ứng dụng/tài sản được phân công.
- Áp dụng MFA, xác thực thiết bị, policy dựa trên nhóm/role và kiểm soát sau đăng nhập.
- Tách quyền nhà cung cấp, đội quản trị, nhân viên phổ thông, service account; hạn chế thời gian truy cập đặc quyền.
- Kiểm tra split tunnel, DNS, certificate, trạng thái IdP, thu hồi phiên và cách xử lý khi backend xác thực lỗi.
- Giám sát đăng nhập thiết bị lạ, hành vi tạo nhiều kết nối nội bộ, truy cập lần đầu và các phiên ngoài thông lệ.
- Khi thiết kế HA/failover cho VPN, đảm bảo tuyến dự phòng **giữ chính sách xác thực và phân đoạn**, không chuyển sang cấp quyền rộng để duy trì availability.

VPN vẫn là biện pháp quan trọng để bảo vệ đường truyền; vấn đề nằm ở **quyền mặc định cấp sau khi kết nối thành công**.

## 10. DNS, dịch vụ khám phá và egress: các đường đi ít được chú ý

Nhiều ứng dụng nội bộ phụ thuộc DNS, proxy, directory service, NTP, mDNS/LLMNR, DHCP và các cơ chế discovery. Một máy bị chiếm có thể lợi dụng các kênh hợp lệ để tìm tài sản, giao tiếp với đích không phù hợp hoặc che giấu nguồn truy cập.

### Nguy cơ và kiểm soát

| Thành phần | Ngộ nhận | Biện pháp phòng vệ |
|---|---|---|
| **DNS nội bộ** | “Chỉ query DNS thì không nguy hiểm” | Kiểm soát resolver, log truy vấn, hạn chế recursion, bảo vệ thay đổi zone và giám sát chuỗi truy vấn lạ |
| **DNS public fallback** | “Resolver nội bộ lỗi thì cứ dùng DNS ngoài” | Resolver dự phòng cùng chính sách; giới hạn rò rỉ truy vấn nội bộ và bypass DNS filtering |
| **Multicast discovery** | “Trong LAN cần mở mọi discovery service” | Chỉ bật ở zone cần, giới hạn LLMNR/mDNS/SSDP theo thiết kế và giảm quảng bá không cần thiết |
| **Egress HTTPS** | “HTTPS mã hóa nên outbound nào cũng hợp lệ” | Egress allowlist theo nhu cầu, proxy/identity, TLS metadata và endpoint telemetry khi có thẩm quyền |
| **NTP và đồng bộ thời gian** | “Sai giờ chỉ là lỗi hiển thị” | NTP tin cậy, đồng hồ ổn định để xác thực và liên kết log điều tra |
| **Service discovery trong cloud** | “Private endpoint là an toàn tuyệt đối” | Xác minh principal, policy, routing, DNS và quyền ở control/data plane |

**Flow log và DNS log không tự chứng minh exfiltration.** Một máy gửi nhiều byte hoặc truy vấn tên miền lạ là dấu hiệu cần phân tích thêm: tiến trình tạo traffic, quyền dữ liệu, đích thực, giải mã có thẩm quyền nếu cần và log máy chủ.

Đối với DNS filtering, đừng giả định chỉ chặn UDP/53 là đủ: TCP/53 và encrypted DNS (DoT/DoH) có thể được dùng theo thiết kế hoặc vượt chính sách. Phạm vi kiểm soát cần được xác định rõ, cân nhắc quyền riêng tư và yêu cầu hoạt động.

## 11. Cloud và container: private VPC không tự là vùng tin cậy

Một VPC/VNet hoặc cluster Kubernetes có thể nằm hoàn toàn trong không gian địa chỉ riêng và vẫn chứa nhiều ứng dụng với quyền, dữ liệu và mức độ bảo vệ khác nhau.

### Các sai lầm cụ thể

1. **Security group “allow from VPC CIDR”:** quyền được cấp cho mọi workload trong một phạm vi rộng, kể cả VM mới, môi trường thử nghiệm hoặc máy bị chiếm.
2. **Private subnet ≠ an toàn:** tài nguyên có thể được truy cập qua bastion, peering, VPN, load balancer, endpoint hoặc workload cùng subnet; phải xem đường đi thực tế.
3. **Trust theo IP của pod:** pod có IP động, có thể NAT qua node, bị thay thế hoặc chia sẻ host network; cần danh tính workload và policy đúng phạm vi.
4. **Kubernetes NetworkPolicy chỉ tồn tại trên giấy:** nếu CNI không hỗ trợ enforcement, hoặc còn policy allow khác, quy tắc có thể không cho hiệu quả mong muốn.
5. **Node/VM có quyền cloud quá rộng:** dù cổng ứng dụng bị phân đoạn, workload vẫn có thể gọi API quản trị nhờ instance role hoặc token nếu không được giới hạn.
6. **Cloud peering và hybrid VPN:** kết nối private làm các miền tin cậy liên thông; không nên mặc định hai bên có cùng chính sách.
7. **Auto scaling và drift:** workload mới được tạo có thể không nhận đúng tag, security group, certificate hoặc policy; cần kiểm chứng ngay trong pipeline và lúc runtime.

### Ví dụ chính sách có phạm vi trong cloud

Giả sử ba lớp: `web`, `app`, `db`. Thiết kế mong muốn:

- `web` chỉ nhận HTTPS từ client và gọi API `app` được cấp.
- `app` chỉ gọi DB port của `db` theo workload identity hoặc nguồn đã được quản lý.
- `db` không nhận kết nối trực tiếp từ Internet, guest, user hoặc workload không liên quan.
- API quản trị cloud và cluster có quyền riêng, bảo vệ MFA/workload identity và audit.
- Route failover hoặc instance replacement **không mở đường bypass** firewall và phân đoạn đã quy định.

Cần đối chiếu thực thi ở security group, subnet ACL, host firewall, Kubernetes policy, service mesh và ứng dụng. Một lớp cho phép không chứng minh mọi lớp khác đều an toàn.

## 12. Giám sát lưu lượng nội bộ: đặt sensor đúng nơi

Nếu chỉ đặt IDS ở firewall Internet, đội an ninh có thể nhìn rất rõ các gói từ ngoài vào nhưng không quan sát được phần lớn lưu lượng giữa hai máy trong cùng VLAN, cùng VPC hoặc traffic nội bộ cluster.

Các nguồn dữ liệu có giá trị bổ sung:

| Nguồn | Quan sát được | Hạn chế |
|---|---|---|
| **Firewall/ACL logs** | Quyết định allow/deny tại điểm thực thi, zone và rule | Lưu lượng không đi qua thiết bị đó sẽ không xuất hiện |
| **NetFlow/IPFIX/VPC flow logs** | Quan hệ source/destination, port, bytes, thời gian, chiều | Không thể tự chứng minh danh tính người dùng hoặc dữ liệu cụ thể bị lấy |
| **Zeek/PCAP** | Metadata giao thức, chuỗi kết nối, chi tiết gói khi có quyền quan sát | TLS/SSH và vị trí sensor tạo điểm mù |
| **IDS/IPS** | Chữ ký và hành vi phát hiện trong phạm vi sensor | Alert đơn lẻ không xác nhận tấn công thành công |
| **VPN/IdP/AD/RADIUS** | Danh tính, session, MFA, logon, quyền truy cập | Có thể bị bỏ sót khi attacker dùng phiên có sẵn hoặc log không đủ |
| **EDR/endpoint/system logs** | Tiến trình sinh kết nối, thực thi từ xa, thay đổi service/file | Không có log nếu sensor thiếu hoặc bị can thiệp |
| **DNS/proxy** | Tên miền, nguồn truy vấn, egress qua điểm giám sát | Có thể bỏ sót encrypted DNS hoặc đường đi trực tiếp |
| **Cloud control-plane audit** | Ai thay security group, IAM, route, policy, API resource | Cần liên kết với data-plane và workload logs |

### Các tín hiệu cần ưu tiên

- Một workstation lần đầu kết nối tới nhiều máy chủ qua SMB/RDP/WinRM/SSH.
- Tài khoản dịch vụ đăng nhập tương tác hoặc dùng trên máy khác với baseline.
- Có nhiều lần thất bại xác thực, rồi thành công ở một máy và xuất hiện truy cập tiếp sang máy khác.
- Một application server bắt đầu nói chuyện với management subnet hoặc backup system.
- Rule firewall/security group mới cho phép `0.0.0.0/0`, `::/0` hoặc “any-any”.
- DNS/egress từ máy chứa dữ liệu nhạy cảm đi tới đích không quen thuộc, kèm dấu hiệu bất thường của tiến trình hoặc truy cập dữ liệu.
- VPN session từ thiết bị chưa nhận diện truy cập dải mạng lớn hơn nhu cầu đã phê duyệt.

**Nguyên tắc phân tích:** một dấu hiệu là *candidate*. Tương quan thêm identity, role, change ticket, nguồn/đích theo thời gian, kết quả xác thực và bằng chứng thực thi mới quyết định mức độ tin cậy.

### Ví dụ truy vấn giả mã phát hiện kết nối quản trị mới

~~~sql
-- Minh họa trên bảng đã chuẩn hóa:
-- flow(ts, src_host, dst_host, dst_port, decision)
-- asset(host, role)
-- :t0 là thời điểm đầu cửa sổ quan sát, do người phân tích cấp.
WITH candidates AS (
  SELECT f.src_host, f.dst_host, f.dst_port
  FROM flow f
  JOIN asset s ON s.host = f.src_host
  WHERE f.ts >= :t0
    AND f.ts < :t0 + INTERVAL '15 minutes'
    AND s.role = 'workstation'
    AND f.dst_port IN (22, 445, 3389, 5985, 5986)
    AND f.decision = 'allow'
)
SELECT src_host, COUNT(DISTINCT dst_host) AS distinct_admin_targets
FROM candidates
GROUP BY src_host
HAVING COUNT(DISTINCT dst_host) >= 4;
~~~

Truy vấn này tìm *fan-out* đáng chú ý, **không chứng minh đăng nhập thành công hay lateral movement**. Để giảm dương tính giả cần baseline theo vai trò, danh sách máy quét và hệ thống triển khai hợp lệ, log xác thực trên máy đích và thời gian thay đổi được phê duyệt. Giá trị 4 đích/15 phút chỉ minh họa; không phải ngưỡng phổ quát.

## 13. Phương pháp kiểm chứng: đừng tin chỉ vì thiết kế ghi “deny”

Tài liệu thiết kế có thể mô tả vùng User và DB được tách biệt, nhưng một rule firewall cũ, đường VPN phụ, security group wildcard, peering cloud hoặc route failover vẫn có thể cho phép kết nối. Cần chuyển chính sách thành **phép kiểm thử có chứng cứ**.

### Bảng thử allow và deny

| Test ID | Luồng | Kỳ vọng | Chứng cứ cần tìm |
|---|---|---|---|
| P1 | Workstation hợp lệ → reverse proxy HTTPS | Allow theo authentication của ứng dụng | Kết quả giao dịch + access log |
| P2 | App workload → DB port được phê duyệt | Allow với danh tính đúng | App/DB log + firewall flow |
| P3 | Bastion → máy chủ quản trị theo quyền | Allow sau xác thực và audit | Session log + identity record |
| N1 | User VLAN → DB admin port | Deny | Kết quả test từ đúng source + log enforcement |
| N2 | Guest/IoT → management subnet | Deny | ACL/host firewall + flow log |
| N3 | Workload dev → production DB | Deny nếu không có ngoại lệ được duyệt | Cloud/host firewall logs |
| N4 | VPN user phổ thông → backup controller | Deny | VPN/identity + firewall rule hit |
| N5 | Internet → thiết bị network management | Deny | Edge firewall + kiểm thử từ nguồn phù hợp |

**Cách tiến hành:** chọn host được phép làm nguồn thử, kiểm tra chính xác đích, giao thức, danh tính và thời điểm; kiểm thử ở phạm vi được phê duyệt; đối chiếu log tại enforcement point. Timeout trên client **không tự chứng minh** firewall đã chặn đúng policy — có thể server đang tắt hoặc routing hỏng.

### Ba câu hỏi xác nhận bất biến bảo mật

1. Khi thiết bị hoạt động bình thường, các luồng bị cấm có bị chặn không?
2. Khi một firewall, route, VPN gateway hoặc NAC controller failover, các luồng đó **vẫn bị chặn** chứ?
3. Khi ứng dụng hoặc tài khoản thay đổi, policy có tự mở rộng không đúng phạm vi hay không?

Kiểm thử failover hoặc configuration drift là phần quan trọng của việc xác minh mạng nội bộ an toàn theo thiết kế. **Dự phòng availability không được âm thầm tạo đường truy cập bỏ qua kiểm soát.**

## 14. Case study: máy nhân viên trở thành bàn đạp tới máy chủ

### Bối cảnh

Một doanh nghiệp có bốn vùng:

- `10.10.20.0/24`: workstation của nhân viên.
- `10.10.30.0/24`: application server.
- `10.10.40.0/24`: database và dữ liệu nhạy cảm.
- `10.10.50.0/24`: quản trị và backup.

Firewall Internet triển khai đầy đủ rule chống truy cập từ ngoài, nhưng nội bộ có chính sách quá rộng: “User VLAN → Server VLAN: Allow TCP/445, 3389, 5985 cho thuận tiện hỗ trợ”. Một số tài khoản hỗ trợ có quyền local admin trên nhiều máy chủ.

### Diễn biến giả định

1. Nhân viên mở tệp độc hại; endpoint bị xâm phạm.
2. Thiết bị bắt đầu tạo kết nối quản trị tới nhiều máy chủ nội bộ. Phần lớn kết nối được firewall nội bộ cho phép vì rule nói trên.
3. Một số máy chủ ghi nhận đăng nhập qua mạng bằng tài khoản có quyền rộng; một máy xuất hiện service hoặc tác vụ mới bất thường.
4. Máy chủ đó tiếp tục tạo kết nối sang vùng database và backup.
5. SOC nhìn thấy cảnh báo VPN/Internet tương đối bình thường nhưng phát hiện chuỗi east-west khi đối chiếu flow, Windows logs và EDR.

**Điểm thất bại:** hệ thống đã dùng **vị trí mạng và quyền rộng** để thay cho danh tính/vai trò thực sự. Một endpoint bị chiếm có đường tiến tới nhiều tài sản nhạy cảm.

### Phân tích nguyên nhân gốc

| Bằng chứng | Lỗ hổng kiến trúc | Hành động khắc phục |
|---|---|---|
| Workstation nói chuyện trực tiếp với cổng quản trị server | Không phân đoạn luồng quản trị theo vai trò | Chỉ cho phép từ bastion/jump host hoặc nguồn quản trị đã xác minh |
| Tài khoản hỗ trợ admin trên nhiều máy | Quyền quá rộng, khó giới hạn phạm vi | Tách tài khoản đặc quyền, PAM/JIT và hạn chế nơi được dùng |
| Flow east-west không có cảnh báo | Sensor chỉ tập trung Internet hoặc không có baseline | Thu flow/log nội bộ và correlation theo role/identity |
| Database truy cập được từ ứng dụng không được cấp quyền | Rule app-to-db quá rộng, thiếu xác thực ở DB | Thu hẹp source/destination và quyền DB |
| Backup cùng miền truy cập rộng | Tài sản khôi phục không được cách ly | Phân đoạn backup, hạn chế admin, bảo vệ bản sao |
| Không kiểm tra khi firewall dự phòng nhận traffic | Chính sách HA/route chưa được kiểm chứng | Positive/negative tests trong failover |

### Quy trình ứng phó ban đầu

Sau khi phát hiện dấu hiệu có cơ sở về truy cập trái phép, đội ứng phó xác định phạm vi tài khoản và thiết bị liên quan, bảo toàn log/PCAP/EDR, điều phối cô lập theo runbook, hạn chế quyền bị lạm dụng và kiểm tra các bước nhảy. Những máy chủ chỉ có kết nối TCP **chưa mặc nhiên** được xem là đã bị chiếm. Tình trạng của từng đích phải dựa trên chứng cứ xác thực, tiến trình và hành động.

Sau khôi phục, tổ chức lập lại baseline, xem xét kiểm soát quyền nội bộ, phân đoạn, quản trị từ xa và test khả năng chống di chuyển ngang.

## 15. Lộ trình cải thiện từ mạng tin cậy ngầm sang mạng kiểm soát theo quyền

Không nhất thiết triển khai “Zero Trust” toàn diện trong một lần. Một lộ trình theo rủi ro sẽ giảm outage và giúp đo hiệu quả.

### Giai đoạn 1 — Biết tài sản và đường đi thật

- Lập danh mục workstation, server, IoT, thiết bị mạng, service account, cloud workload, vùng mạng và owner.
- Thu thập dependency và luồng qua firewall, flow logs, ứng dụng, DNS, VPN/IdP.
- Xác định tài sản trọng yếu: identity, backup, database, security control, quản trị mạng.
- Dựng ma trận source–destination–protocol–purpose; đánh dấu quyền rộng và điểm không có logging.

### Giai đoạn 2 — Bịt các khoảng mở rõ ràng

- Đóng cổng quản trị Internet/VLAN người dùng không cần thiết.
- Tách guest/BYOD/IoT khỏi management và tài sản nhạy cảm.
- Giới hạn quyền VPN, tài khoản đặc quyền, service account và đường cloud peering.
- Bật MFA/thiết bị được quản lý ở những điểm có thể.
- Thiết lập bảo vệ endpoint và log nội bộ phù hợp.

### Giai đoạn 3 — Phân đoạn từng vùng và thử có kiểm soát

- Ưu tiên các biên có hậu quả cao như User → Management, App → DB, Guest → Internal.
- Chuyển từ allow rộng sang allow đúng source/target/protocol.
- Triển khai theo canary hoặc policy monitor trước khi enforce ở nơi có hỗ trợ.
- Kiểm tra positive và negative cases, backup, HA/failover, DNS/AD dependency, rollback.
- Không xóa rule chỉ vì ít hit trong một tuần: DR, sao lưu và tác vụ định kỳ có thể chưa xuất hiện.

### Giai đoạn 4 — Giám sát và duy trì

- Phát hiện quan hệ máy–máy mới, đăng nhập đặc quyền bất thường, rule drift và policy exception.
- Gắn owner, expiry/review date cho quyền tồn tại lâu dài.
- Kiểm tra việc cấp quyền khi nhân viên chuyển vai trò, máy bị thay thế và workload mới được tạo.
- Diễn tập giả định một máy đã bị chiếm để đo blast radius còn lại và khả năng phát hiện.
- Đánh giá định kỳ false positive, điểm mù log và chi phí vận hành.

**Thay đổi phải được quản trị như thay đổi an ninh mạng:** có mục đích, đánh giá rủi ro, người phê duyệt, bằng chứng và rollback. Cắt quyền đột ngột không có mapping dependency có thể gây mất dịch vụ, dẫn đến rollback mở rộng quyền hơn trước.

## 16. Những đánh đổi cần hiểu

### 16.1. Phân đoạn càng chặt có phải luôn tốt?

Phân đoạn theo nhu cầu giảm phạm vi tấn công, nhưng nếu áp thiếu bối cảnh sẽ phá ứng dụng, gây khó debug và tăng chi phí vận hành. Cần xây dựng **đơn vị phân đoạn phù hợp**: theo vai trò, ứng dụng, dữ liệu, môi trường, quyền quản trị và luồng thực tế. Không có một số VLAN “chuẩn” cho mọi hệ thống.

### 16.2. Cần kiểm tra mọi packet ở lớp ứng dụng?

Không phải mọi môi trường có thể hoặc nên giải mã toàn bộ TLS. Giải pháp có thể phối hợp metadata, identity, endpoint telemetry, log ứng dụng và kiểm tra tại điểm phù hợp. Các lựa chọn cần cân nhắc hiệu năng, quyền riêng tư, quy định và khả năng vận hành.

### 16.3. MFA có giải quyết hết tin cậy ngầm không?

MFA giảm nhiều rủi ro liên quan credential nhưng không loại trừ phiên bị đánh cắp, thiết bị đã bị chiếm, quyền truy cập rộng hoặc ứng dụng bị lỗi phân quyền. MFA là **một lớp**, cần kết hợp session security, device posture, least privilege và giám sát.

### 16.4. Có cần bỏ firewall biên không?

Không. Firewall biên vẫn quan trọng để giới hạn truy cập inbound/outbound và giảm exposure. Cần bổ sung phân đoạn bên trong, kiểm soát ở host/workload và identity-aware policies. Cách tiếp cận hợp lý là **bảo vệ nhiều lớp**.

### 16.5. Nếu cảm biến không thấy traffic nội bộ thì kết luận gì?

Chỉ có thể kết luận “không quan sát được sự kiện trong phạm vi sensor hiện có”. Tránh biến **thiếu dữ liệu** thành **bằng chứng an toàn**. Khi báo cáo, nêu rõ vùng nào thiếu log, ứng dụng mã hóa, đường cloud và các phép thử chưa thực hiện.

## 17. Checklist đánh giá ngộ nhận “mạng nội bộ luôn an toàn”

- [ ] Có danh mục tài sản, dịch vụ, owner và vùng mạng theo vai trò, thay vì chỉ theo IP/CIDR?
- [ ] Máy trạm thông thường có bị chặn khỏi cổng quản trị server, database, backup và thiết bị mạng?
- [ ] Guest/IoT/BYOD được phân tách, có NAC/802.1X và client isolation phù hợp?
- [ ] Người dùng VPN chỉ có quyền tới những tài sản cần thiết sau xác thực?
- [ ] Phân quyền ở lớp ứng dụng/DB được thực thi, kể cả khi client có IP nội bộ?
- [ ] Tài khoản đặc quyền và service account bị hạn chế nơi dùng, được giám sát và thu hồi khi không cần?
- [ ] Mạng cloud, hybrid, Kubernetes và peering có chính sách riêng theo workload/identity?
- [ ] Có quan sát lưu lượng east-west hoặc log host/identity đủ để nhận diện chuỗi kết nối bất thường?
- [ ] Kiểm soát DNS, outbound HTTPS, proxy, discovery và tuyến dự phòng có được thẩm định?
- [ ] Có positive/negative test từ các vùng thật, kể cả IPv6 nếu triển khai?
- [ ] HA/failover không cho phép đi vòng firewall/NAC/segmentation bắt buộc?
- [ ] Mọi quyền truy cập quan trọng có owner, approval, expiry hoặc lịch rà soát?
- [ ] Khi một máy bị chiếm, tổ chức biết những tài sản nào nó có thể tiếp cận và làm sao kiểm chứng?
- [ ] Có phương án khôi phục/rollback nếu chính sách mới ảnh hưởng ứng dụng hợp lệ?

## 18. Câu hỏi tự kiểm tra

1. Vì sao IP private và NAT không đủ để xác định máy/truy cập “an toàn”? Hãy đưa ví dụ về một máy nội bộ bị chiếm.
2. Phân biệt bảo vệ tại firewall biên và kiểm soát lưu lượng east-west. Tại sao chỉ giám sát north-south không đủ?
3. Một ứng dụng cho phép mọi IP thuộc `10.0.0.0/8` truy cập trang quản trị. Thiếu những kiểm tra gì?
4. Sau khi đăng nhập VPN có MFA, vì sao người dùng vẫn không nên tự động được phép truy cập toàn bộ subnet nội bộ?
5. Hãy chỉ ra ít nhất bốn trust boundary trong một kiến trúc gồm guest Wi-Fi, employee LAN, web, application, database, backup và management.
6. Vì sao một VLAN tách biệt không bảo đảm mạng an toàn khi route/firewall vẫn có rule “allow any” giữa các vùng?
7. Giải thích cách một tài khoản dịch vụ quá quyền có thể làm tăng blast radius của một endpoint bị chiếm.
8. Nếu máy chủ bị chiếm trong VPC private, attacker có thể lạm dụng những quyền nào ngoài kết nối TCP nội bộ?
9. Đề xuất một phép thử **allow** và hai phép thử **deny** để xác minh User VLAN không được đi thẳng vào database.
10. Vì sao flow log chỉ có kết nối TCP/445 chưa đủ kết luận đã xảy ra lateral movement? Những log nào giúp củng cố?
11. Khi RADIUS hoặc VPN IdP lỗi, chính sách nào ngăn việc “fail-open toàn LAN”?
12. Xây dựng lộ trình cải thiện ba giai đoạn cho một doanh nghiệp có mạng phẳng, không có flow nội bộ và nhiều service account dùng chung; giải thích cách hạn chế outage.

**Điểm cần nhớ:** **Vị trí trong LAN chỉ là ngữ cảnh, không phải bằng chứng đáng tin.** Xác thực đúng chủ thể, cấp đúng quyền, giới hạn đường kết nối, giám sát các hoạt động bên trong và kiểm thử những ranh giới đã thiết kế mới giúp mạng nội bộ thực sự có khả năng chống chịu khi một người dùng, endpoint hoặc workload bị xâm phạm.
