# Ai được phép kết nối vào mạng? Nền tảng Network Access Control

Một thiết bị cắm vào cổng Ethernet, kết nối Wi-Fi hoặc đăng nhập VPN chưa chắc đã được phép truy cập mọi tài nguyên trong tổ chức. Câu hỏi **“Ai được phép kết nối vào mạng?”** thuộc bài toán **Network Access Control (NAC)**: xác định **ai** hoặc **thiết bị nào** yêu cầu kết nối, **được phép vào đâu**, **trong điều kiện nào**, và **cần làm gì khi điều kiện thay đổi**.

Trong học phần **SECURITY_NETWORK_SECURITY**, NAC là một lớp phòng vệ giúp gắn **danh tính và trạng thái thiết bị** với phân đoạn mạng, firewall, VPN, hệ thống giám sát IDS/IPS và chính sách trên hạ tầng cloud. NAC phối hợp với các biện pháp bảo vệ DNS, mạng không dây và xác thực kết nối để hạn chế di chuyển ngang của đối tượng không được phép. Tuy nhiên, **được cấp quyền tham gia mạng không có nghĩa được cấp quyền sử dụng mọi ứng dụng**: từng dịch vụ vẫn phải thực hiện xác thực và phân quyền thích hợp.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **authentication**, **authorization** và **accounting** trong kiểm soát truy cập mạng.
2. Giải thích cách **IEEE 802.1X**, EAP, switch/AP và RADIUS phối hợp trong một phiên xác thực.
3. Nhận biết các phương án kiểm soát truy cập cho **máy công ty, BYOD, khách, thiết bị IoT và người dùng từ xa**.
4. Xây dựng chính sách cấp quyền theo **danh tính, vai trò, trạng thái thiết bị và mức rủi ro**.
5. Diễn giải các quyết định **cho phép, hạn chế, cách ly, từ chối và thu hồi quyền**.
6. Phân tích log và kiểm chứng NAC có hoạt động đúng với thiết kế phân đoạn, VPN và firewall.

## 2. NAC giải quyết vấn đề gì?

Trong một mạng văn phòng không có kiểm soát truy cập phù hợp, chỉ cần biết mật khẩu Wi-Fi chung hoặc kết nối vào một cổng switch đang hoạt động, một thiết bị có thể nhận địa chỉ IP và nhìn thấy những hệ thống cùng mạng. Khi danh sách thiết bị thay đổi liên tục, cách quản lý chỉ bằng địa chỉ MAC, IP hoặc VLAN tĩnh khó duy trì chính sách nhất quán.

NAC đặt một **điểm quyết định và thực thi** trước hoặc trong quá trình cấp kết nối:

~~~text
Người dùng / Thiết bị
         │
         ▼
Điểm truy cập: switch, Wi-Fi AP, gateway VPN
         │
         ├── Thu thập thông tin xác thực / ngữ cảnh
         ▼
Hệ thống xác thực và chính sách
   ├── Danh tính người dùng / thiết bị?
   ├── Vai trò / nhóm / quyền?
   ├── Trạng thái thiết bị / mức tin cậy?
   └── Vị trí, thời gian, mức rủi ro?
         │
         ▼
Quyết định: cho phép / hạn chế / cách ly / từ chối
         │
         ▼
Thực thi tại switch / AP / VPN / firewall
         │
         ▼
Giám sát và đánh giá lại khi điều kiện thay đổi
~~~

NAC có thể được triển khai theo các hình thức khác nhau, từ **802.1X tại tầng liên kết**, kết hợp hệ thống quản lý thiết bị và RADIUS, đến chính sách cấp quyền tại VPN hay một cổng truy cập. Không phải sản phẩm nào cũng thu thập đầy đủ mọi thông tin; cần xem rõ điểm thực thi và mức xác thực mà từng giải pháp hỗ trợ.

### Authentication, Authorization, Accounting (AAA)

| Thành phần | Câu hỏi | Ví dụ trong NAC |
|---|---|---|
| **Authentication (xác thực)** | Bạn là ai, hoặc thiết bị này có danh tính đáng tin không? | Kiểm chứng chứng chỉ thiết bị qua EAP-TLS, xác thực tài khoản từ hệ thống danh tính |
| **Authorization (cấp quyền)** | Danh tính đã xác thực được truy cập tài nguyên nào? | Gán VLAN nhân viên, áp dụng ACL chỉ cho phép DNS, HTTPS nội bộ hoặc máy chủ được phê duyệt |
| **Accounting (ghi nhận phiên)** | Ai đã kết nối, khi nào, từ đâu và trong bao lâu? | Log RADIUS accounting, phiên switch/AP, thời điểm vào/ra, dữ liệu phục vụ điều tra |

**Xác thực thành công không tự động đồng nghĩa với cấp quyền rộng.** Một tài khoản hợp lệ trên thiết bị chưa đáp ứng chính sách có thể chỉ được truy cập mạng khắc phục sự cố. Ngược lại, một kết nối được cho phép vào mạng khách chỉ có quyền hạn hẹp dù người dùng có thể cung cấp email hoặc thông tin đăng ký.

## 3. Những yếu tố quyết định quyền truy cập

Một quyết định NAC chất lượng thường xét nhiều thuộc tính thay vì duy nhất IP hoặc MAC:

| Yếu tố | Minh họa | Giới hạn cần lưu ý |
|---|---|---|
| **Danh tính người dùng** | Nhân viên, quản trị viên, nhà thầu, khách | Tài khoản có thể bị chiếm quyền; nhóm quyền cần đồng bộ và thu hồi đúng lúc |
| **Danh tính thiết bị** | Chứng chỉ máy do tổ chức cấp, hồ sơ đăng ký thiết bị | Chứng chỉ cần quản lý khóa riêng, hạn dùng, thu hồi và vòng đời thiết bị |
| **Trạng thái thiết bị (posture)** | Có mã hóa ổ đĩa, thiết bị được quản lý, phiên bản OS đáp ứng chính sách | Posture là tín hiệu tại thời điểm kiểm tra, không chứng minh thiết bị miễn nhiễm với tấn công |
| **Vai trò hoặc mục đích** | Máy bán hàng, laptop lập trình, camera IP, máy in | Thiết bị cùng mạng vật lý có thể cần những quyền mạng hoàn toàn khác nhau |
| **Điểm kết nối** | Cổng switch, SSID, VLAN, VPN, mạng chi nhánh | Vị trí có thể bị giả mạo hoặc thay đổi; không nên tự xem là danh tính |
| **Bối cảnh rủi ro** | Địa điểm bất thường, thời điểm truy cập, cảnh báo EDR | Cần tránh dùng tín hiệu thiếu tin cậy để tự động cấp quyền quá rộng |
| **Đích và loại lưu lượng** | DNS được quản lý, API nội bộ, dịch vụ quản trị | Cần bổ sung firewall, ACL, định danh ứng dụng và phân quyền tại ứng dụng |

Hai nguyên tắc quan trọng là **least privilege (đặc quyền tối thiểu)** và **default deny (mặc định từ chối các quyền chưa được cho phép)**. Chính sách nên định nghĩa rõ điều kiện được cấp một tập quyền cụ thể và cách xử lý khi hệ thống chưa xác minh được điều kiện ấy.

Ví dụ: nhân viên dùng laptop công ty có chứng chỉ máy hợp lệ, tình trạng thiết bị đạt chuẩn và đăng nhập hợp lệ có thể vào mạng nhân viên. Cùng người đó dùng máy cá nhân không đăng ký có thể chỉ được Internet qua mạng khách hoặc cổng dịch vụ được công ty cho phép. Sự khác biệt bắt nguồn từ **ngữ cảnh và chính sách**, không chỉ từ tên tài khoản.

## 4. Kiến trúc IEEE 802.1X: xác thực trước khi cấp truy cập

**IEEE 802.1X** cung cấp cơ chế **Port-Based Network Access Control** thường dùng trên Ethernet và Wi-Fi Enterprise. Ba vai trò chính:

- **Supplicant:** phần mềm xác thực trên thiết bị muốn kết nối, ví dụ laptop chạy 802.1X client.
- **Authenticator:** switch hoặc access point quản lý cổng/phiên kết nối và truyền thông điệp xác thực.
- **Authentication server:** hệ thống kiểm tra thông tin xác thực và chính sách, thường dùng giao thức **RADIUS**; có thể tích hợp với thư mục người dùng, PKI hoặc nền tảng danh tính khác.

~~~text
Laptop (Supplicant)        Switch/AP (Authenticator)          RADIUS / Policy
        │                           │                               │
        │── EAP over LAN (EAPOL) ──>│                               │
        │<──── EAP exchange ────────│── RADIUS Access-Request ────>│
        │                           │<── Access-Accept / Reject ────│
        │<── Thông báo kết quả ──────│                               │
        │                           │                               │
        │          Nếu được cấp quyền: mở cổng truy cập phù hợp      │
        │───────── Lưu lượng theo VLAN / ACL / policy ──────────────>│
~~~

Sơ đồ là luồng khái quát. Trong thực tế, switch/AP thường đóng gói hoặc chuyển tiếp các **thông điệp EAP** giữa supplicant và máy chủ qua RADIUS. Máy chủ có thể trả thuộc tính để gán VLAN, ACL hoặc vai trò nếu authenticator hỗ trợ. Việc cấp phát quyền còn phụ thuộc cấu hình hệ thống và chính sách của nhà cung cấp.

### 4.1. Trình tự của một lần kết nối

1. Thiết bị cắm dây hoặc liên kết tới SSID Enterprise; authenticator nhận ra một phiên chưa được cấp quyền đầy đủ.
2. Supplicant và authenticator trao đổi **EAPOL/EAP** để bắt đầu xác thực. Trong giai đoạn chưa được cấp quyền, cổng 802.1X kiểm soát lưu lượng thông thường theo cơ chế **controlled port**; không nên hiểu là mọi frame đều bị chặn tuyệt đối.
3. Authenticator gửi dữ liệu xác thực đến authentication server, thường qua RADIUS.
4. Máy chủ kiểm chứng bằng phương thức EAP được cấu hình, sau đó trả kết quả; chính sách NAC có thể cần thêm thông tin thiết bị hoặc thuộc tính người dùng.
5. Nếu được chấp nhận, authenticator kích hoạt kết nối với mức quyền được trả về/cấu hình. Nếu thất bại, thiết bị có thể bị từ chối hoặc được đưa vào vùng hạn chế theo chính sách.
6. Thiết bị có thể bị **reauthentication** hoặc thay đổi quyền khi phiên, danh tính, chứng chỉ, trạng thái thiết bị hay thông tin chính sách thay đổi.

**Lưu ý về giao thức:** EAP là khung trao đổi phương thức xác thực, không phải một loại mật khẩu. **EAPOL** vận chuyển EAP trên LAN giữa supplicant và authenticator. **RADIUS** thường trao đổi thông tin xác thực, cấp quyền và accounting giữa authenticator với server. RADIUS thông thường và RADIUS được bảo vệ bằng TLS (ví dụ RadSec) có đặc tính bảo vệ kênh truyền khác nhau, cần thiết kế theo nền tảng và yêu cầu bảo mật của tổ chức.

### 4.2. EAP-TLS và xác thực bằng chứng chỉ

**EAP-TLS** sử dụng TLS và chứng chỉ để xác thực; khi triển khai cấu hình thích hợp, nó giúp ràng buộc danh tính với việc sở hữu khóa riêng của thiết bị/người dùng và xác minh máy chủ xác thực. Đây là lựa chọn mạnh trong môi trường thiết bị được quản lý vì không phụ thuộc vào việc gửi mật khẩu dùng chung qua Wi-Fi.

Một triển khai EAP-TLS cần:

- **PKI và quy trình cấp chứng chỉ:** ai được cấp, cấp cho người hay máy, lưu khóa riêng ở đâu, khi nào gia hạn hoặc thu hồi.
- **Client phải kiểm tra danh tính máy chủ:** cấu hình CA tin cậy và tên/định danh máy chủ xác thực; nếu bỏ qua xác minh, nguy cơ bị dụ kết nối tới hạ tầng xác thực giả tăng lên.
- **Phân quyền đúng thuộc tính:** có chứng chỉ hợp lệ chưa đủ để được vào mọi VLAN; phải ánh xạ tới thiết bị, vai trò và trạng thái phù hợp.
- **Xử lý chứng chỉ hết hạn/mất thiết bị:** có kênh thu hồi, thay mới và vùng khắc phục có giới hạn để tránh gián đoạn hàng loạt.

Các phương thức khác như PEAP có thể phù hợp với một số hệ thống cũ hoặc ràng buộc thực tế, nhưng cần đánh giá khả năng xác thực máy chủ, loại credential và nguy cơ lộ thông tin khi người dùng cấu hình sai. Không nên quảng bá một phương thức là an toàn chỉ dựa trên tên gọi.

## 5. Thiết kế chính sách: ai được vào mạng nào?

Nên chuyển câu hỏi “ai được phép kết nối” thành **ma trận nguồn–đích–điều kiện** dễ kiểm thử:

| Nhóm kết nối | Điều kiện được chấp nhận | Quyền mạng đề xuất | Nếu không đạt điều kiện |
|---|---|---|---|
| **Laptop nhân viên được quản lý** | Xác thực người dùng/thiết bị hợp lệ, posture đáp ứng chính sách | VLAN/role nhân viên; chỉ truy cập dịch vụ cần thiết | Vùng remediation hoặc từ chối tùy mức rủi ro |
| **Máy quản trị** | Danh tính quản trị, thiết bị được quản lý, xác thực mạnh và chính sách nghiêm ngặt hơn | Chỉ các subnet/cổng quản trị đã phê duyệt | Từ chối quyền quản trị; không cấp VLAN admin mặc định |
| **Thiết bị cá nhân (BYOD)** | Đăng ký theo chính sách hoặc chấp nhận điều khoản mạng khách | Internet và tài nguyên riêng cho BYOD nếu được phép | Mạng khách hạn chế hoặc từ chối |
| **Khách/đối tác ngắn hạn** | Xác thực hoặc phê duyệt tài khoản khách theo chính sách tổ chức | Internet; cô lập khỏi tài nguyên nội bộ | Không kết nối |
| **Máy in/camera/IoT** | Danh tính và cổng/thiết bị được quản lý, đáp ứng quy trình nhập thiết bị | VLAN IoT và ACL chỉ cho phép máy chủ vận hành cần thiết | VLAN cách ly hoặc cổng tắt |
| **Nhân viên từ xa qua VPN** | Danh tính + MFA/phương thức mạnh và kiểm tra trạng thái thiết bị nếu áp dụng | Chỉ các mạng/dịch vụ cần làm việc | Từ chối hoặc hạn chế kết nối VPN |

Ma trận trên là **ví dụ thiết kế**, không phải cấu hình tiêu chuẩn áp dụng cho mọi doanh nghiệp. Những nhãn VLAN và mức kiểm tra cụ thể phải được điều chỉnh theo tài sản, mô hình rủi ro và khả năng của switch/AP/NAC.

### 5.1. Vai trò (role), VLAN và ACL có gì khác nhau?

- **Role** diễn tả nhóm quyền từ góc nhìn chính sách, như employee, contractor, guest hoặc managed-iot.
- **VLAN** phân chia miền liên kết tầng 2. VLAN có thể giúp cô lập một phần lưu lượng nhưng không tự xác thực danh tính hoặc bảo đảm việc chặn lưu lượng định tuyến giữa các VLAN.
- **ACL/firewall rule** thực thi giới hạn nguồn, đích, giao thức, cổng hoặc một số thuộc tính khác theo nền tảng; có thể áp dụng ngay tại cổng, switch, gateway hoặc workload.
- **Ứng dụng** vẫn cần kiểm tra quyền ở cấp người dùng/dịch vụ, đặc biệt khi kết nối đã tới backend.

Ví dụ, cả máy nhân viên và máy quản trị đều có thể vào mạng nội bộ, nhưng chỉ máy quản trị đã xác thực và đủ điều kiện mới được kết nối SSH/RDP tới hệ thống vận hành. Nếu chỉ gán cùng một VLAN “trusted” rồi bỏ qua ACL và phân quyền ứng dụng, NAC sẽ không đạt mục tiêu hạn chế tác động khi một thiết bị bị xâm nhập.

### 5.2. Những quyết định phải được mô tả rõ

Một chính sách tối thiểu nên định nghĩa:

~~~text
ALLOW:
  Danh tính được xác thực, thiết bị đạt điều kiện, vai trò có quyền.
LIMIT / REMEDIATE:
  Danh tính hợp lệ nhưng thiếu cấu hình hoặc cần cập nhật thiết bị.
QUARANTINE:
  Thiết bị đang bị điều tra hoặc có tín hiệu rủi ro cao, vẫn cần kênh hỗ trợ tối thiểu.
DENY:
  Không xác thực được, không có quyền hoặc bị thu hồi quyền.
REVOKE / REEVALUATE:
  Quyền được xét lại khi người dùng nghỉ việc, mất máy, đổi trạng thái hoặc hết phiên.
~~~

**Quarantine** không phải lúc nào cũng là “mất hoàn toàn kết nối”. Trong nhiều thiết kế, VLAN/ACL cách ly có thể cho phép truy cập tối thiểu tới DHCP, DNS, hệ thống cấp chứng chỉ, cập nhật thiết bị hay cổng hỗ trợ để khắc phục. Tập đích này phải được giới hạn cẩn thận để không trở thành đường vòng vào mạng nội bộ.

## 6. Thiết bị không hỗ trợ 802.1X: bài toán IoT và MAB

Máy in cũ, điện thoại IP, thiết bị đo đạc hoặc camera có thể không có supplicant 802.1X phù hợp. Một số hệ thống dùng **MAC Authentication Bypass (MAB)**: switch gửi thông tin MAC tới server kiểm soát để tìm chính sách áp dụng.

**MAB có giới hạn bảo mật rõ ràng:** MAC address có thể bị sao chép hoặc giả mạo. MAB chỉ nên là biện pháp hỗ trợ đối với thiết bị không có khả năng xác thực mạnh, kèm các hạn chế bổ sung:

1. Đăng ký thiết bị với chủ sở hữu, vị trí, cổng và chức năng cụ thể.
2. Tách vào **VLAN/role IoT riêng**, tránh cho phép truy cập trực tiếp toàn bộ mạng nội bộ.
3. Giới hạn kết nối đến đúng dịch vụ quản lý cần thiết bằng ACL/firewall.
4. Kết hợp giám sát MAC-to-port, DHCP snooping/IP Source Guard hoặc kiểm soát tương thích; mỗi biện pháp có phạm vi và điều kiện riêng.
5. Rà soát danh sách thiết bị, quyền truy cập và tuổi đời định kỳ; chuyển sang 802.1X/chứng chỉ khi thiết bị được thay thế hoặc nâng cấp.

Một hệ thống NAC cũng có thể dùng **profiling** từ đặc điểm DHCP, DNS, lưu lượng hoặc thông tin switch để đoán loại thiết bị. Tuy nhiên, profiling là **phân loại theo dấu hiệu**, không phải xác thực danh tính có độ tin cậy tương đương chứng chỉ. Dùng kết quả phân loại để cấp quyền quá rộng là rủi ro.

## 7. Wi-Fi Enterprise, mạng khách và captive portal

### 7.1. Wi-Fi Enterprise

Với Wi-Fi Enterprise, thiết bị có thể dùng 802.1X/EAP cùng chế độ bảo vệ vô tuyến thích hợp. Khi cấu hình đúng, việc xác thực danh tính máy chủ và sử dụng chứng chỉ giúp giảm nguy cơ kết nối tới điểm phát giả mạo chỉ vì SSID trùng tên.

Một SSID **không tự nó là danh tính đã xác thực**. Kẻ tấn công có thể tạo điểm phát có SSID tương tự hoặc trùng với mạng hợp lệ. Phòng vệ gồm cấu hình hồ sơ Wi-Fi được quản lý, xác thực EAP-TLS và xác minh đúng chứng chỉ máy chủ, cùng giám sát điểm phát không được ủy quyền.

### 7.2. Captive portal và mạng khách

**Captive portal** có thể yêu cầu đăng ký, chấp nhận điều khoản hoặc đăng nhập trước khi mở đường Internet. Nó hữu ích cho quản trị truy cập khách, nhưng **không tự thay thế xác thực mạnh của thiết bị**, và không phải mọi captive portal đều bảo vệ toàn bộ lưu lượng vô tuyến.

Mạng khách nên:

- Chỉ được đi tới Internet hoặc những dịch vụ được công bố rõ ràng.
- Được cách ly khỏi máy nhân viên, máy quản trị và thiết bị IoT.
- Có giới hạn phiên, băng thông hoặc thời hạn khi cần.
- Có DNS, DHCP và đường cập nhật hệ thống được cấu hình theo yêu cầu sử dụng.
- Ghi log phù hợp chính sách bảo mật và quyền riêng tư của tổ chức.

Không nên dùng cùng một mật khẩu Wi-Fi chia sẻ lâu dài làm kiểm soát duy nhất cho mạng chứa hệ thống nhạy cảm.

## 8. NAC trong VPN, Zero Trust và cloud

NAC truyền thống thường quyết định thiết bị có thể tham gia **LAN/Wi-Fi**; môi trường hiện đại mở rộng bài toán sang **truy cập từ xa, kết nối giữa ứng dụng và workload cloud**.

### 8.1. VPN remote access

Một VPN có thể xác thực người dùng bằng tài khoản, MFA, chứng chỉ hoặc phương thức tương đương theo cấu hình. Sau khi đăng nhập, VPN thường cấp địa chỉ và tuyến đến các tài nguyên được phép. Vì thế chính sách còn phải quyết định:

- User thuộc nhóm nào và thiết bị có được quản lý không?
- Có được truy cập tài nguyên quản trị hay chỉ ứng dụng nghiệp vụ?
- Người dùng có cần VPN toàn phần hay chỉ một số tuyến/dịch vụ?
- Quyền có được thu hồi khi chứng chỉ hết hạn, tài khoản bị khóa hoặc phiên bị kết thúc không?
- Lưu lượng VPN có được đưa qua firewall/IDS/IPS và ghi log đúng chỗ không?

**Có tunnel VPN được mã hóa không đồng nghĩa mọi truy cập bên trong được tin cậy.** Firewall nội bộ, xác thực ứng dụng, phân quyền và theo dõi hoạt động vẫn cần thiết.

### 8.2. Zero Trust và truy cập theo ứng dụng

Tư duy **Zero Trust** đặt trọng tâm vào việc xác minh rõ ràng danh tính/ngữ cảnh và cấp **quyền tối thiểu đối với tài nguyên**, thay vì mặc định tin cậy mọi thứ nằm trong một mạng riêng. Thiết bị có thể phải đáp ứng thêm chính sách trước khi mở phiên tới ứng dụng cụ thể.

NAC và Zero Trust hỗ trợ nhau: NAC kiểm soát điểm kết nối và trạng thái của thiết bị; các cổng truy cập ứng dụng, identity provider và policy enforcement point tiếp tục kiểm tra quyền truy cập tới dịch vụ. Không thể chỉ bật 802.1X rồi kết luận tổ chức đã triển khai toàn bộ kiến trúc Zero Trust.

### 8.3. Cloud và workload identity

Trong VPC/VNet, một máy ảo hoặc container có địa chỉ IP nội bộ không vì thế mà đáng tin hơn một thực thể khác. Các kiểm soát tương ứng gồm **security group/NSG, network ACL, microsegmentation, danh tính workload và xác thực dịch vụ**, tùy khả năng của nhà cung cấp.

Ví dụ một API chỉ cho phép nhận kết nối từ nhóm workload được xác định trong policy mạng, rồi tiếp tục yêu cầu xác thực dịch vụ bằng danh tính và quyền được cấp. Địa chỉ IP và port có thể thay đổi khi workload được triển khai lại; chính sách gắn với danh tính/nhãn cần được đồng bộ với hạ tầng triển khai.

## 9. Triển khai NAC theo từng giai đoạn

Áp dụng NAC đồng loạt ngay lập tức có thể làm gián đoạn máy tính, Wi-Fi, thiết bị họp trực tuyến, điện thoại IP và các hệ thống đặc biệt. Quy trình triển khai nên thu hẹp rủi ro và cho phép kiểm chứng:

| Giai đoạn | Hoạt động chính | Bằng chứng cần có |
|---|---|---|
| **1. Khảo sát** | Kiểm kê người dùng, thiết bị, VLAN/SSID, cổng switch, hệ thống nhận dạng và tài nguyên | Danh sách thiết bị/owner, luồng truy cập hợp lệ và ngoại lệ |
| **2. Xác định chính sách** | Thiết kế role, điều kiện xác thực, VLAN/ACL, khách/IoT và cách xử lý thất bại | Ma trận quyền theo nguồn, đích, dịch vụ và ngữ cảnh |
| **3. Chuẩn bị hạ tầng** | Kiểm tra switch/AP 802.1X, RADIUS/AAA, PKI, quản lý chứng chỉ và log | Cấu hình mẫu, khả năng tích hợp và quy trình rollback |
| **4. Quan sát trước** | Dùng chế độ monitor/audit khi giải pháp hỗ trợ; theo dõi kết quả giả định mà chưa chặn rộng | Danh sách thiết bị có nguy cơ bị gián đoạn và nguyên nhân |
| **5. Pilot hạn chế** | Áp dụng ở một nhóm người dùng/cổng/SSID có đại diện đủ các loại thiết bị | Tỷ lệ xác thực thành công, lỗi, thời gian kết nối, tác động người dùng |
| **6. Mở rộng có kiểm soát** | Tăng dần vùng áp dụng, cấu hình cảnh báo và hỗ trợ khắc phục | Log quyết định truy cập, báo cáo sự cố và kiểm thử ma trận |
| **7. Duy trì** | Quản trị vòng đời chứng chỉ, quyền nhân viên nghỉ việc, máy mất, thiết bị mới | Rà soát định kỳ, kết quả tái xác thực và quy trình thu hồi |

### Khi RADIUS/PKI gặp sự cố: fail-open hay fail-closed?

Đây là **quyết định kiến trúc về khả năng sẵn sàng và bảo mật**, không có câu trả lời áp dụng cho mọi cổng:

- **Fail-closed:** không cấp quyền mạng thông thường khi không xác thực được. Giảm khả năng truy cập trái phép nhưng có thể làm gián đoạn người dùng và dịch vụ.
- **Fail-open hoặc critical authorization:** một số nền tảng có thể cấp quyền hạn chế hoặc VLAN dự phòng khi máy chủ xác thực không sẵn sàng. Cần định nghĩa **rõ phạm vi quyền**, vì cho phép toàn bộ mạng nội bộ sẽ làm suy yếu NAC nghiêm trọng.
- **HA và dự phòng:** nhiều authentication server, cấu hình thời gian chờ hợp lý và cơ chế giám sát giúp giảm tần suất phải chọn giữa gián đoạn và nới lỏng chính sách.
- **Tài sản trọng yếu/OT:** lựa chọn dự phòng và kiểm soát đổi cấu hình phải được đánh giá cùng đội vận hành; mất kết nối có thể gây tác động lớn đến hoạt động.

Không nên nhầm **RADIUS server không sẵn sàng** với **người dùng xác thực thất bại**: hai trường hợp cần quyết định và log khác nhau. Một hệ thống cố ý cấp quyền hạn chế khi mất AAA vẫn phải được giám sát và phục hồi về chính sách chuẩn khi AAA trở lại.

## 10. Giám sát, phát hiện sai lệch và phản ứng

NAC cần kết nối được với hệ thống logging và giám sát xâm nhập để trả lời các câu hỏi: **ai đã thử kết nối, ở cổng nào, được quyết định gì và có thay đổi quyền giữa phiên không?**

| Nguồn dữ liệu | Ví dụ tín hiệu | Hành động phân tích |
|---|---|---|
| **RADIUS authentication log** | Access-Accept/Reject, phương thức EAP, policy áp dụng | Kiểm tra định danh, lỗi chứng chỉ, sai nhóm hoặc truy cập bất thường |
| **RADIUS accounting / switch session** | Bắt đầu/kết thúc phiên, cổng, VLAN/role, thông tin session | Liên kết phiên thực tế với quyết định cấp quyền |
| **PKI / quản lý thiết bị** | Chứng chỉ hết hạn, bị thu hồi, thiết bị chưa đăng ký, posture không đạt | Kiểm tra lý do và thời điểm thay đổi trạng thái |
| **Firewall / VPN logs** | Kết nối từ role/vùng không mong muốn, truy cập quản trị trái phép | Kiểm tra NAC có thực thi đủ phân đoạn hay không |
| **IDS/IPS / EDR** | Hoạt động quét mạng, dấu hiệu lateral movement, endpoint bị xâm nhập | Đánh giá có cần thay role, cô lập hoặc thu hồi phiên không |
| **Wi-Fi controller / switch log** | MAC di chuyển, nhiều lần xác thực lỗi, AP không được ủy quyền | Phân biệt roaming, lỗi cấu hình, thiết bị mới và hành vi bất thường |

**Ví dụ log giả định (dữ liệu minh họa):**

~~~text
Time:        2026-11-28T08:30:00+07:00
Client:      laptop-employee-17
Access:      switch-01 / port Gi1/0/12
Auth method: EAP-TLS
Auth result: SUCCESS
Device state: COMPLIANT
Policy:      EMPLOYEE-MANAGED
Action:      ALLOW role=employee vlan=120
Session ID:  lab-session-0042
~~~

Một log **SUCCESS** chưa đủ để kết luận firewall đã thực thi đúng mọi ACL hay ứng dụng đã chặn quyền không hợp lệ. Cần đối chiếu giữa **chính sách dự kiến**, **quyết định NAC** và **kết quả lưu lượng thực tế**.

### Quy trình xử lý thiết bị đáng ngờ

1. Kiểm tra tín hiệu từ NAC, IDS/IPS, EDR, switch/AP và chủ sở hữu; tránh cô lập nhầm vì một lần lỗi xác thực hoặc roaming Wi-Fi.
2. Xác định danh tính, chứng chỉ, cổng kết nối, phiên và quyền hiện tại; đối chiếu với sơ đồ luồng hợp lệ.
3. Nếu có cơ sở xác định sự cố, yêu cầu thay đổi quyền hoặc cách ly theo quy trình và khả năng của thiết bị thực thi.
4. Bảo toàn log có thời gian chính xác và lập hồ sơ điều tra; xử lý vòng đời chứng chỉ/tài khoản nếu bị lộ.
5. Khôi phục kết nối sau khi thiết bị đáp ứng điều kiện, rồi theo dõi để xác nhận chính sách hoạt động bình thường.

Tùy nền tảng, việc cập nhật quyền có thể cần ngắt phiên, tái xác thực hoặc dùng cơ chế **Change of Authorization (CoA)**. Không nên mặc định mọi switch và AP đều hỗ trợ chuyển role theo thời gian thực.

## 11. Tình huống thực hành: BYOD cố truy cập hệ thống nội bộ

**Bối cảnh giả định:** Công ty sử dụng Wi-Fi Enterprise cho laptop được quản lý, mạng khách riêng cho thiết bị cá nhân và VLAN quản trị cho nhóm hạ tầng. Một nhân viên đăng nhập bằng danh tính hợp lệ nhưng sử dụng laptop cá nhân chưa đăng ký để truy cập API nội bộ.

Chính sách dự kiến:

| Điều kiện | Quyết định |
|---|---|
| Nhân viên + laptop công ty có chứng chỉ hợp lệ + posture đạt | Cho vào role nhân viên; firewall chỉ cho phép API cần thiết |
| Nhân viên + laptop cá nhân chưa đăng ký | Không cấp role nhân viên; có thể vào mạng khách theo quy định |
| Thiết bị quản trị + tài khoản quản trị + điều kiện xác thực bổ sung | Cấp role quản trị với ACL hạn chế |
| Thiết bị có chứng chỉ bị thu hồi | Từ chối hoặc cách ly theo quy trình |

Một kết quả ghi nhận giả định:

~~~text
Danh tính người dùng:  employee-17     -> hợp lệ
Chứng chỉ thiết bị:    không có loại được tổ chức chấp nhận
Posture:              chưa được đánh giá
Quyết định NAC:       DENY role=employee
Truy cập mạng khách:  ALLOW sau khi đáp ứng chính sách khách
Truy cập API nội bộ:  DENY tại firewall
~~~

### Phân tích kết quả

Quyết định phù hợp với nguyên tắc **không đồng nhất danh tính người dùng và mức tin cậy của thiết bị**. Sau đó nhóm quản trị cần xác minh:

1. Laptop công ty đủ điều kiện có được truy cập API đúng như chính sách không?
2. Máy cá nhân có thực sự không đi được tới IP/cổng API từ mạng khách không?
3. Log của Wi-Fi, NAC và firewall có ghi nhận đủ để giải thích sự khác biệt hay không?
4. Nếu laptop công ty hết hạn chứng chỉ, người dùng có quy trình thay mới hợp lệ mà không bị cấp nhầm quyền rộng không?
5. Nếu nhân viên nghỉ việc hoặc thiết bị bị mất, có thu hồi tài khoản/chứng chỉ và phiên kết nối theo quy trình không?

**Lưu ý thực hành:** Bài tập này có thể đánh giá qua **ma trận chính sách và log mô phỏng**, không nhất thiết phải thử làm sai thông tin xác thực hoặc can thiệp hệ thống thật.

## 12. Cách kiểm tra trạng thái kết nối trên máy được phép quản trị

Các lệnh đọc trạng thái bên dưới giúp người học ghi lại thông tin mạng trước khi đối chiếu với log NAC. Chúng **không tự chứng minh** máy đã dùng EAP-TLS đúng hoặc đã được cấp role theo yêu cầu: kết quả xác thực thực tế cần xác minh từ profile kết nối và hệ thống AAA/switch/AP.

**Linux (nếu có NetworkManager):**

~~~bash
nmcli device status
ip -br addr
ip route
~~~

**Windows (Command Prompt/PowerShell):**

~~~text
ipconfig /all
netsh wlan show interfaces
route print
~~~

**Phiếu quan sát đề xuất:**

~~~text
Loại thiết bị:       [managed / BYOD / guest / IoT]
Kiểu kết nối:       [Ethernet / Wi-Fi / VPN]
Điểm kết nối:       [switch port / SSID / VPN gateway]
Danh tính đã kiểm:  [user / device / cả hai]
Phương thức:        [EAP-TLS / phương thức đã cấu hình]
Policy dự kiến:     [role / VLAN / ACL]
Quyết định NAC:     [allow / limit / quarantine / deny]
Quyền thực tế:      [tài nguyên được phép truy cập]
Bằng chứng:         [log có timestamp, mã phiên, kiểm tra firewall]
Ngoại lệ cần xử lý: [mô tả và người phụ trách]
~~~

Thao tác xác minh nên dùng **hệ thống thử nghiệm và tài khoản được cấp phép**, tránh ghi mật khẩu/khóa riêng hoặc dữ liệu nhạy cảm vào báo cáo.

## 13. Sai lầm thường gặp khi thiết kế NAC

| Sai lầm | Hệ quả | Điều chỉnh |
|---|---|---|
| Coi IP/MAC là danh tính không thể giả mạo | Có thể bị qua mặt hoặc quy sai thiết bị | Ưu tiên xác thực mật mã và đối chiếu hạ tầng |
| Cho toàn bộ người đã đăng nhập vào cùng một VLAN tin cậy | Quyền mạng quá rộng, tăng nguy cơ di chuyển ngang | Role, phân đoạn, ACL, phân quyền từng ứng dụng |
| Triển khai 802.1X nhưng client bỏ qua xác minh chứng chỉ server | Có nguy cơ bị dụ xác thực với hệ thống giả | Phân phối profile chuẩn và xác minh server/CA |
| Dùng MAB như tương đương EAP-TLS | MAC dễ bị sao chép | Chỉ dùng ngoại lệ với quyền IoT tối thiểu |
| Xem posture đạt là bằng chứng máy không nhiễm mã độc | Tín hiệu trạng thái có thể lỗi thời hoặc không đầy đủ | Kết hợp EDR, logging, least privilege, tái đánh giá |
| Captive portal được xem là xác thực thiết bị mạnh | Máy khách có thể vẫn không có danh tính chứng chỉ | Tách mạng khách và giới hạn tài nguyên |
| Chỉ kiểm tra kết quả RADIUS Accept | Quyền thực tế tại switch/firewall có thể sai | Đo cả policy, session, VLAN/ACL và lưu lượng |
| Không xử lý khi RADIUS/PKI mất kết nối | Có thể gián đoạn diện rộng hoặc mở quyền vượt chính sách | Dự phòng AAA, xử lý failover và quyền khẩn cấp tối thiểu |
| Không có quy trình thu hồi chứng chỉ/tài khoản | Máy mất hoặc nhân viên nghỉ vẫn có thể truy cập | Quản lý vòng đời và chấm dứt phiên |
| Cho rằng NAC đủ thay firewall và xác thực ứng dụng | Thiết bị đã vào mạng có thể truy cập ngoài vai trò | Bảo vệ theo nhiều lớp từ kết nối đến dịch vụ |

## 14. Câu hỏi tự kiểm tra

1. Vì sao một người dùng xác thực đúng tài khoản vẫn có thể bị từ chối vào VLAN nhân viên?
2. Ba vai trò **supplicant, authenticator, authentication server** trong 802.1X khác nhau như thế nào?
3. **EAPOL**, **EAP-TLS** và **RADIUS** đảm nhiệm các công việc nào trong quá trình kết nối?
4. VLAN khác ACL ở điểm nào? Vì sao phân đoạn cần cả cấu hình định tuyến/firewall?
5. Tại sao **MAB** nên chỉ là phương án hỗ trợ cho thiết bị không có 802.1X?
6. Nếu RADIUS server mất kết nối, có nên cấp toàn bộ quyền mạng cho thiết bị hiện diện trên cổng không? Những yếu tố nào phải cân nhắc?
7. Một laptop có chứng chỉ hợp lệ nhưng EDR báo bị xâm nhập nên được xử lý theo những bước nào?
8. Khi NAC báo ALLOW nhưng máy vẫn truy cập API bị từ chối, cần kiểm tra những lớp kiểm soát nào trước khi cho rằng NAC bị lỗi?

## 15. Ghi nhớ trọng tâm

**Ai được phép kết nối vào mạng?** Người dùng hoặc thiết bị được cấp kết nối **khi danh tính và ngữ cảnh đáp ứng chính sách**, với mức quyền phù hợp tài sản cần truy cập. **802.1X/EAP, RADIUS và hệ thống NAC** giúp xác thực và đưa ra quyết định tại điểm truy cập; **VLAN, ACL, firewall, VPN và kiểm soát theo ứng dụng** đảm nhiệm việc giới hạn quyền thực tế.

Thiết kế tốt cần chú ý **nhân viên, quản trị viên, khách, BYOD và IoT**; xem xét cả **trạng thái thiết bị, vòng đời chứng chỉ, mất kết nối hệ thống AAA, thu hồi phiên và log điều tra**. Quyền mạng không phải một lựa chọn “có/không” duy nhất: **cho phép, hạn chế, cách ly và thu hồi** là những kết quả khác nhau cần được định nghĩa và kiểm thử. NAC có giá trị khi chính sách được ánh xạ thành quyền có thể thực thi, có thể quan sát và thay đổi kịp thời cùng mức rủi ro.
